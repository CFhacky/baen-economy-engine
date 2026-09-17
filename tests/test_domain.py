from decimal import Decimal
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from baen_economy.domain import (  # noqa: E402
    AccountingTreatment,
    EntityRecord,
    SimulationAssignment,
    SimulationMode,
    TemporalState,
    decimal_or_none,
    validate_unique_assignments,
)


class DomainTests(unittest.TestCase):
    def test_decimal_conversion_never_uses_binary_float_math(self):
        self.assertEqual(decimal_or_none(0.1), Decimal("0.1"))
        with self.assertRaisesRegex(ValueError, "finite"):
            decimal_or_none("NaN")

    def test_unknown_is_excluded_not_treated_as_zero(self):
        row = EntityRecord("entity:x", "X", "notion:x")
        self.assertIsNone(row.monthly_revenue)
        self.assertFalse(row.eligible_for_current_operating_totals)

    def test_only_current_operating_values_consolidate(self):
        row = EntityRecord(
            "entity:x",
            "X",
            "notion:x",
            temporal_state=TemporalState.CURRENT,
            treatment=AccountingTreatment.OPERATING_UNIT,
            timeline_id="actual",
            effective_ordinal=1,
            monthly_revenue=Decimal("10"),
            classification_authority_ref="ruling:test",
            classification_rationale="domain fixture",
        )
        self.assertTrue(row.eligible_for_current_operating_totals)
        projected = EntityRecord(
            "entity:y",
            "Y",
            "notion:y",
            temporal_state=TemporalState.PROJECTED,
            treatment=AccountingTreatment.OPERATING_UNIT,
            monthly_revenue=Decimal("999"),
        )
        self.assertFalse(projected.eligible_for_current_operating_totals)

    def test_entity_period_cannot_be_legacy_and_stock_flow(self):
        assignments = [
            SimulationAssignment("entity:x", "actual", 1, SimulationMode.LEGACY, "fixture:a"),
            SimulationAssignment("entity:x", "actual", 1, SimulationMode.STOCK_FLOW, "fixture:b"),
        ]
        with self.assertRaisesRegex(ValueError, "cannot use both"):
            validate_unique_assignments(assignments)


if __name__ == "__main__":
    unittest.main()
