from __future__ import annotations

import copy
from decimal import Context, Decimal, localcontext
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
sys.path.insert(0, str(SRC))

from baen_economy.food_sector import (  # noqa: E402
    DEFAULT_CANON_PATH,
    FoodSectorError,
    expense_factor,
    load_food_sector_baseline,
    preview_food_sector_month,
    revenue_factor,
    validate_food_sector_preview,
)


FACES = {
    "Agriculture": {
        "revenue": [3, 3, 4],
        "expense": [5, 5, 5],
    },
    "Aquaculture": {
        "revenue": [4, 5, 6],
        "expense": [6, 6, 6],
    },
}
NO_REVENUE_BONUS = {
    "Agriculture": {"vara_active": False, "revenue_streams": 1},
    "Aquaculture": {"vara_active": False, "revenue_streams": 1},
}


def _assert_no_floats(test: unittest.TestCase, value: object) -> None:
    if isinstance(value, float):
        test.fail(f"binary float leaked into food-sector preview: {value!r}")
    if isinstance(value, dict):
        for item in value.values():
            _assert_no_floats(test, item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _assert_no_floats(test, item)


class FoodSectorBaselineTests(unittest.TestCase):
    def test_loads_exact_confirmed_registry_baseline(self) -> None:
        baseline = load_food_sector_baseline()

        self.assertEqual(baseline["schema"], "tnp.economy.food-sector-baseline/1")
        self.assertEqual(baseline["authority"], "observed_operating_state")
        self.assertEqual(baseline["as_of"], "Eleint 20, 1494")
        self.assertEqual(
            baseline["totals"],
            {
                "entity_count": 5,
                "staff": 63,
                "monthly_revenue_gp": "26500",
                "monthly_cost_gp": "20550",
                "monthly_net_gp": "5950",
                "capital_invested_gp": "111000",
            },
        )
        self.assertEqual(
            [entity["name"] for entity in baseline["entities"]],
            [
                "Agricultural Shelter Zones",
                "Blacklake Aquaculture (7 pools)",
                "Converted Quarry Aquaculture (5 sites)",
                "BG Aquaculture Pools (3 sites)",
                "Reservoir Fisheries",
            ],
        )
        self.assertEqual(
            {entity["sector"] for entity in baseline["entities"]},
            {"Agriculture", "Aquaculture"},
        )

    def test_excludes_later_orchard_and_unconfirmed_lobster_king(self) -> None:
        excluded = load_food_sector_baseline()["excluded_entities"]
        self.assertEqual(
            [item["name"] for item in excluded],
            ["Orchard Chapel", "Lobster King Operations (Baen-Allied)"],
        )
        by_name = {item["name"]: item for item in excluded}
        self.assertEqual(by_name["Orchard Chapel"]["as_of"], "1498 DR")
        self.assertEqual(
            by_name["Orchard Chapel"]["reason"],
            "later_1498_reference_not_part_of_eleint_1494_baseline",
        )
        self.assertEqual(
            by_name["Lobster King Operations (Baen-Allied)"]["status"],
            "Unconfirmed",
        )
        self.assertEqual(
            by_name["Lobster King Operations (Baen-Allied)"]["reason"],
            "unconfirmed_registry_row",
        )

    def test_source_fixture_drift_fails_closed(self) -> None:
        fixture = json.loads(DEFAULT_CANON_PATH.read_text(encoding="utf-8"))
        confirmed = copy.deepcopy(fixture)
        confirmed["registry_entities"][0]["monthly_revenue_gp"] = "1501"
        orchard = copy.deepcopy(fixture)
        orchard_row = next(
            row
            for row in orchard["registry_entities"]
            if row["entity_id"] == "orchard-chapel"
        )
        orchard_row["as_of"] = "Eleint 20, 1494"

        with tempfile.TemporaryDirectory() as folder:
            confirmed_path = Path(folder) / "confirmed.json"
            orchard_path = Path(folder) / "orchard.json"
            confirmed_path.write_text(json.dumps(confirmed), encoding="utf-8")
            orchard_path.write_text(json.dumps(orchard), encoding="utf-8")
            with self.assertRaisesRegex(FoodSectorError, "confirmed food row drifted"):
                load_food_sector_baseline(confirmed_path)
            with self.assertRaisesRegex(FoodSectorError, "excluded food row drifted"):
                load_food_sector_baseline(orchard_path)


class FoodSectorMechanicsTests(unittest.TestCase):
    def test_skill_factor_tables_are_exact_decimals(self) -> None:
        revenue_expected = {
            "critical_success": "1.25",
            "success_by_5_plus": "1.15",
            "success": "1.05",
            "exact_target": "1.00",
            "failure": "0.90",
            "failure_by_5_plus": "0.80",
            "critical_failure": "0.70",
        }
        expense_expected = {
            "critical_success": "0.90",
            "success_by_5_plus": "1.00",
            "success": "1.05",
            "exact_target": "1.05",
            "failure": "1.15",
            "failure_by_5_plus": "1.15",
            "critical_failure": "1.25",
        }
        for outcome, expected in revenue_expected.items():
            with self.subTest(table="revenue", outcome=outcome):
                factor = revenue_factor(outcome)
                self.assertIs(type(factor), Decimal)
                self.assertEqual(factor, Decimal(expected))
        for outcome, expected in expense_expected.items():
            with self.subTest(table="expense", outcome=outcome):
                factor = expense_factor(outcome)
                self.assertIs(type(factor), Decimal)
                self.assertEqual(factor, Decimal(expected))

    def test_supplied_faces_drive_one_shared_roll_per_sector(self) -> None:
        preview = preview_food_sector_month(
            month_label="Hammer 1495 financial preview",
            supplied_faces=FACES,
            sector_assumptions=NO_REVENUE_BONUS,
        )

        self.assertEqual(preview["schema"], "tnp.food-sector.month-preview/1")
        agriculture = preview["sectors"]["Agriculture"]
        aquaculture = preview["sectors"]["Aquaculture"]
        self.assertEqual(agriculture["rolls"]["revenue"]["faces"], [3, 3, 4])
        self.assertEqual(agriculture["rolls"]["revenue"]["base_target"], 15)
        self.assertEqual(agriculture["rolls"]["revenue"]["skill"], "Merchant")
        self.assertEqual(agriculture["rolls"]["revenue"]["effective_target"], 15)
        self.assertEqual(agriculture["rolls"]["revenue"]["margin"], 5)
        self.assertEqual(
            agriculture["rolls"]["revenue"]["outcome"], "success_by_5_plus"
        )
        self.assertEqual(agriculture["rolls"]["revenue"]["factor"], "1.15")
        self.assertEqual(agriculture["rolls"]["expense"]["base_target"], 16)
        self.assertEqual(agriculture["rolls"]["expense"]["skill"], "Administration")
        self.assertEqual(agriculture["rolls"]["expense"]["effective_target"], 18)
        self.assertEqual(agriculture["rolls"]["expense"]["factor"], "1.05")

        self.assertEqual(aquaculture["rolls"]["revenue"]["faces"], [4, 5, 6])
        self.assertEqual(aquaculture["rolls"]["revenue"]["margin"], 0)
        self.assertEqual(aquaculture["rolls"]["revenue"]["outcome"], "exact_target")
        self.assertEqual(aquaculture["rolls"]["revenue"]["factor"], "1.00")
        self.assertEqual(aquaculture["rolls"]["expense"]["faces"], [6, 6, 6])
        self.assertEqual(
            aquaculture["rolls"]["expense"]["outcome"], "critical_failure"
        )
        self.assertEqual(aquaculture["rolls"]["expense"]["factor"], "1.25")

        self.assertEqual(len(agriculture["entities"]), 1)
        self.assertEqual(len(aquaculture["entities"]), 4)
        self.assertTrue(
            all(entity["revenue_factor"] == "1.00" for entity in aquaculture["entities"])
        )
        self.assertTrue(
            all(entity["expense_factor"] == "1.25" for entity in aquaculture["entities"])
        )
        self.assertEqual(
            preview["preview_totals"],
            {
                "entity_count": 5,
                "staff": 63,
                "monthly_revenue_gp": "26725.00",
                "monthly_cost_gp": "25477.50",
                "monthly_net_gp": "1247.50",
                "capital_invested_gp": "111000",
            },
        )
        self.assertEqual(
            sum(len(result["rolls"]) for result in preview["sectors"].values()),
            4,
        )
        validate_food_sector_preview(preview)

    def test_all_expense_modifiers_and_revenue_modifiers_are_visible(self) -> None:
        assumptions = {
            sector: {
                "market": "boom",
                "vara_active": True,
                "revenue_streams": 7,
                "competent_managers": 3,
                "monopoly": True,
                "excellent_accounting": True,
                "rapid_expansion": True,
            }
            for sector in ("Agriculture", "Aquaculture")
        }
        preview = preview_food_sector_month(
            month_label="Modifier receipt",
            supplied_faces=FACES,
            sector_assumptions=assumptions,
        )
        agriculture = preview["sectors"]["Agriculture"]["rolls"]
        aquaculture = preview["sectors"]["Aquaculture"]["rolls"]
        self.assertEqual(
            agriculture["revenue"]["modifiers"],
            [
                {"label": "Market boom", "value": 4},
                {"label": "7+ revenue streams", "value": 2},
                {"label": "Vara active", "value": 3},
                {"label": "Competent managers (maximum +3)", "value": 3},
                {"label": "Monopoly position", "value": 2},
            ],
        )
        self.assertEqual(agriculture["revenue"]["modifier_total"], 14)
        self.assertEqual(
            agriculture["expense"]["modifiers"],
            [
                {"label": "Sector staff size (8; below 50)", "value": 2},
                {"label": "Excellent accounting", "value": 2},
                {"label": "Rapid expansion", "value": -3},
            ],
        )
        self.assertEqual(agriculture["expense"]["modifier_total"], 1)
        self.assertEqual(aquaculture["expense"]["modifier_total"], -1)


class FoodSectorSafetyTests(unittest.TestCase):
    def test_seeded_preview_is_deterministic_and_discloses_every_face(self) -> None:
        seed = "food-sector-known-seed-do-not-echo"
        first = preview_food_sector_month(
            month_label="Hammer 1495 deterministic preview", seed=seed
        )
        second = preview_food_sector_month(
            month_label="Hammer 1495 deterministic preview", seed=seed
        )
        self.assertEqual(first, second)
        self.assertEqual(first["dice_source"]["method"], "hmac_sha256_seeded_preview")
        self.assertEqual(
            first["dice_source"]["seed_fingerprint"],
            hashlib.sha256(seed.encode("utf-8")).hexdigest(),
        )
        self.assertTrue(first["dice_source"]["all_faces_disclosed"])
        self.assertNotIn(seed, json.dumps(first, sort_keys=True))
        for sector in ("Agriculture", "Aquaculture"):
            for check in ("revenue", "expense"):
                self.assertEqual(len(first["sectors"][sector]["rolls"][check]["faces"]), 3)

        # Defaults are explicit: Vara is active and four Registry operations
        # count as four Aquaculture revenue streams.
        self.assertEqual(
            first["sectors"]["Agriculture"]["rolls"]["revenue"]["effective_target"],
            18,
        )
        self.assertEqual(
            first["sectors"]["Aquaculture"]["rolls"]["revenue"]["effective_target"],
            19,
        )
        self.assertEqual(
            first["sectors"]["Agriculture"]["rolls"]["expense"]["effective_target"],
            18,
        )
        self.assertEqual(
            first["sectors"]["Aquaculture"]["rolls"]["expense"]["effective_target"],
            16,
        )

    def test_result_is_noncanonical_inert_and_classified_for_export(self) -> None:
        preview = preview_food_sector_month(
            month_label="Read-only receipt",
            supplied_faces=FACES,
            sector_assumptions=NO_REVENUE_BONUS,
        )
        self.assertFalse(preview["canonical"])
        self.assertFalse(preview["campaign_time_advanced"])
        self.assertEqual(
            preview["safety"],
            {
                "canonical": False,
                "campaign_time_advanced": False,
                "campaign_state_rolls_resolved": 0,
                "preview_roll_receipts": 4,
                "notion_read_only": True,
                "notion_write_capability": False,
                "notion_writes": 0,
                "ledger_write_capability": False,
                "ledger_transactions": 0,
                "ledger_postings": 0,
            },
        )
        self.assertEqual(
            set(preview["decision_brief"]),
            {"Source", "Assumption", "Derived", "Unknown"},
        )
        self.assertEqual(preview["decision_brief"]["Source"]["baseline"], preview["baseline"])
        self.assertEqual(
            preview["decision_brief"]["Derived"]["preview_totals"],
            preview["preview_totals"],
        )
        body = dict(preview)
        content_hash = body.pop("content_hash")
        from baen_economy.operator_codec import canonical_hash  # noqa: E402

        self.assertEqual(content_hash, canonical_hash(body))
        _assert_no_floats(self, preview)

    def test_engine_owns_decimal_context(self) -> None:
        normal = preview_food_sector_month(
            month_label="Context-independent preview",
            supplied_faces=FACES,
            sector_assumptions=NO_REVENUE_BONUS,
        )
        with localcontext(Context(prec=3)):
            constrained = preview_food_sector_month(
                month_label="Context-independent preview",
                supplied_faces=FACES,
                sector_assumptions=NO_REVENUE_BONUS,
            )
        self.assertEqual(normal, constrained)

    def test_dice_and_assumption_inputs_fail_closed(self) -> None:
        with self.assertRaisesRegex(FoodSectorError, "exactly one"):
            preview_food_sector_month(month_label="Missing dice")
        with self.assertRaisesRegex(FoodSectorError, "exactly one"):
            preview_food_sector_month(
                month_label="Two dice sources", seed="seed", supplied_faces=FACES
            )
        malformed = copy.deepcopy(FACES)
        malformed["Agriculture"]["revenue"] = [1, 2, True]
        with self.assertRaisesRegex(FoodSectorError, "integer faces"):
            preview_food_sector_month(
                month_label="Bad faces", supplied_faces=malformed
            )
        with self.assertRaisesRegex(FoodSectorError, "unknown field"):
            preview_food_sector_month(
                month_label="Bad assumptions",
                supplied_faces=FACES,
                sector_assumptions={"Agriculture": {"invented_bonus": 99}},
            )

    def test_validator_rejects_tampered_roll(self) -> None:
        preview = preview_food_sector_month(
            month_label="Tamper test",
            supplied_faces=FACES,
            sector_assumptions=NO_REVENUE_BONUS,
        )
        tampered = copy.deepcopy(preview)
        tampered["sectors"]["Aquaculture"]["rolls"]["revenue"]["factor"] = "9.99"
        with self.assertRaisesRegex(FoodSectorError, "content hash"):
            validate_food_sector_preview(tampered)


if __name__ == "__main__":
    unittest.main()
