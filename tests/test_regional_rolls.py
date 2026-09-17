from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from baen_economy.operator_codec import canonical_hash  # noqa: E402
from baen_economy.regional_rolls import (  # noqa: E402
    ExpenseRollInput,
    SectorRollInput,
    roll_regional_month,
    validate_regional_rolls,
)


class RegionalRollTests(unittest.TestCase):
    def manifest(self) -> dict[str, object]:
        return roll_regional_month(
            state_hash="a" * 64,
            period_index=1,
            seed="regional-test-seed",
            sectors=(
                SectorRollInput("Manufacturing", revenue_streams=4, competent_managers=1),
                SectorRollInput("Mining/Quarrying"),
            ),
            entities=(
                ExpenseRollInput("baen-brickworks", 30),
                ExpenseRollInput("clay-quarries", 12),
            ),
        )

    def test_rolls_are_deterministic_sorted_and_skill_receipted(self) -> None:
        first = self.manifest()
        second = self.manifest()
        self.assertEqual(first, second)
        self.assertEqual(
            [item["sector"] for item in first["sector_rolls"]],
            ["Manufacturing", "Mining/Quarrying"],
        )
        self.assertEqual(
            [item["entity_id"] for item in first["expense_rolls"]],
            ["baen-brickworks", "clay-quarries"],
        )
        manufacturing = first["sector_rolls"][0]
        self.assertEqual(manufacturing["base_target"], 15)
        self.assertEqual(manufacturing["modifier_total"], 5)
        self.assertIn("Merchant-15", manufacturing["target_authority"])
        self.assertIn("revenue_factor", manufacturing)
        self.assertIn("Administration-16", first["expense_rolls"][0]["target_authority"])
        self.assertEqual(first["campaign_state_rolls_resolved"], 0)
        self.assertNotIn("regional-test-seed", repr(first))
        validate_regional_rolls(first, seed="regional-test-seed")

    def test_replay_rejects_self_rehashed_dice_tamper(self) -> None:
        payload = copy.deepcopy(self.manifest())
        faces = payload["sector_rolls"][0]["dice"]
        faces[0] = 1 if faces[0] != 1 else 2
        roll = payload["sector_rolls"][0]
        roll["total"] = sum(faces)
        roll["margin"] = roll["effective_target"] - roll["total"]
        from baen_economy.operator_dice import classify_3d6

        roll["outcome"] = classify_3d6(
            total=roll["total"], effective_target=roll["effective_target"]
        )
        body = {key: value for key, value in payload.items() if key != "manifest_hash"}
        payload["manifest_hash"] = canonical_hash(body)
        with self.assertRaisesRegex(ValueError, "do not replay"):
            validate_regional_rolls(payload, seed="regional-test-seed")

    def test_ambiguous_employee_band_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            roll_regional_month(
                state_hash="b" * 64,
                period_index=1,
                seed="seed",
                sectors=(SectorRollInput("Manufacturing"),),
                entities=(ExpenseRollInput("ambiguous", 200),),
            )


if __name__ == "__main__":
    unittest.main()
