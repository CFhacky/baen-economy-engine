from decimal import Decimal, getcontext, setcontext
from dataclasses import replace
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from baen_economy.domain import (  # noqa: E402
    AccountingTreatment, EntityRecord, TemporalState,
)
from baen_economy.audit_cli import audit_export  # noqa: E402
from baen_economy.notion_read import (  # noqa: E402
    BUSINESS_REGISTRY_DATA_SOURCE, NotionWriteProhibited,
    assert_operation_allowed,
    make_read_snapshot,
)
from baen_economy.registry import (  # noqa: E402
    Classification,
    ConsolidationError,
    audit_rows,
    consolidated_monthly_totals,
    normalize_row, normalize_rows,
    stable_source_record_id,
)


def source_classification(source_ref, classification):
    return {stable_source_record_id(source_ref): classification}


class RegistryTests(unittest.TestCase):
    def test_offline_audit_export_is_stable_and_warns_against_raw_totals(self):
        result = audit_export({"rows": [{"url": "notion:x", "Entity": "X", "Monthly Revenue": 9}]})
        self.assertEqual(result["schema"], "tnp.registry.audit/1")
        self.assertEqual(result["row_count"], 1)
        self.assertEqual(result["raw_totals"]["monthly_revenue"], "9")
        self.assertIn("not consolidated", result["warning"])

    def test_read_snapshot_has_no_write_surface(self):
        snapshot = make_read_snapshot(
            data_source_url=BUSINESS_REGISTRY_DATA_SOURCE,
            captured_at="2026-08-29T00:00:00Z", rows=[], expected_row_count=0,
            pagination_complete=True,
        )
        self.assertFalse(hasattr(snapshot, "write"))
        self.assertFalse(hasattr(snapshot, "update"))
        with self.assertRaises(NotionWriteProhibited):
            assert_operation_allowed("update")
        with self.assertRaises(NotionWriteProhibited):
            assert_operation_allowed("pages.bulk_update")
        with self.assertRaises(NotionWriteProhibited):
            assert_operation_allowed("apply_template")
        assert_operation_allowed("query")

    def test_read_snapshot_is_deeply_immutable_complete_and_source_locked(self):
        source = {"url": "notion:x", "Entity": "X", "Monthly Revenue": 1, "nested": {"x": [1]}}
        snapshot = make_read_snapshot(
            data_source_url=BUSINESS_REGISTRY_DATA_SOURCE,
            captured_at="2026-08-29T00:00:00Z", rows=[source], expected_row_count=1,
            pagination_complete=True,
        )
        source["Monthly Revenue"] = 999
        self.assertEqual(snapshot.audit().raw_totals["monthly_revenue"], "1")
        with self.assertRaises(TypeError):
            snapshot.rows[0]["Monthly Revenue"] = 2
        self.assertEqual(len(snapshot.content_hash), 64)
        with self.assertRaisesRegex(ValueError, "content hash"):
            replace(snapshot, content_hash="0" * 64).audit()
        with self.assertRaisesRegex(ValueError, "row count"):
            replace(snapshot, expected_row_count=2).audit()
        with self.assertRaisesRegex(ValueError, "authorized Business Registry"):
            make_read_snapshot(
                data_source_url="collection://wrong", captured_at="2026-08-29T00:00:00Z",
                rows=[], expected_row_count=0, pagination_complete=True,
            )
        with self.assertRaisesRegex(ValueError, "pagination"):
            make_read_snapshot(
                data_source_url=BUSINESS_REGISTRY_DATA_SOURCE,
                captured_at="2026-08-29T00:00:00Z", rows=[], expected_row_count=0,
                pagination_complete=False,
            )

    def test_read_snapshot_decimal_hash_ignores_ambient_capitals(self):
        original = getcontext().copy()
        try:
            getcontext().capitals = 0
            lower = make_read_snapshot(
                data_source_url=BUSINESS_REGISTRY_DATA_SOURCE,
                captured_at="2026-08-29T00:00:00Z",
                rows=[{"url": "notion:x", "Entity": "X", "value": Decimal("1E+20")}],
                expected_row_count=1,
                pagination_complete=True,
            )
            getcontext().capitals = 1
            upper = make_read_snapshot(
                data_source_url=BUSINESS_REGISTRY_DATA_SOURCE,
                captured_at="2026-08-29T00:00:00Z",
                rows=[{"url": "notion:x", "Entity": "X", "value": Decimal("1E+20")}],
                expected_row_count=1,
                pagination_complete=True,
            )
        finally:
            setcontext(original)
        self.assertEqual(lower.content_hash, upper.content_hash)

    def test_distinct_names_cannot_silently_share_a_stable_id(self):
        audit = audit_rows([
            {"url": "notion:a", "Entity": "A & B"},
            {"url": "notion:b", "Entity": "A-B"},
        ])
        self.assertIn("stable_id_collision", {issue.code for issue in audit.issues})
        with self.assertRaisesRegex(ValueError, "stable_id_collision"):
            normalize_rows([
                {"url": "notion:a", "Entity": "A & B"},
                {"url": "notion:b", "Entity": "A-B"},
            ])

    def test_equivalent_notion_urls_share_one_source_identity(self):
        page_id = "34ce821484b081febf14f062ef3cb91b"
        plain = f"https://www.notion.so/{page_id}"
        decorated = f"https://app.notion.com/p/Zariel-{page_id}?pvs=204#section"
        self.assertEqual(stable_source_record_id(plain), stable_source_record_id(decorated))
        rows = [
            {"url": plain, "Entity": "First Name"},
            {"url": decorated, "Entity": "Renamed Duplicate"},
        ]
        self.assertIn(
            "duplicate_source_record_id", {issue.code for issue in audit_rows(rows).issues}
        )
        with self.assertRaisesRegex(ValueError, "duplicate_source_record_id"):
            normalize_rows(rows)

    def test_audit_flags_margin_units_projection_and_parent_overlap(self):
        rows = [
            {
                "url": "notion:parent",
                "Entity": "NCF",
                "Monthly Revenue": 100,
                "Monthly Cost": 40,
                "Profit Margin": 60,
                "Status": "Operational",
                "Notes": "Projected full capacity",
            },
            {
                "url": "notion:child",
                "Entity": "NCF Neverwinter",
                "Parent Entity": "NCF",
                "Monthly Revenue": 25,
                "Monthly Cost": 10,
                "Profit Margin": 0.6,
                "Status": "Operational",
            },
        ]
        audit = audit_rows(rows)
        codes = {issue.code for issue in audit.issues}
        self.assertIn("margin_arithmetic_mismatch", codes)
        self.assertIn("projection_in_current_field", codes)
        self.assertIn("parent_child_flow_overlap", codes)
        self.assertEqual(audit.raw_totals["monthly_revenue"], "125")

    def test_unclassified_row_remains_excluded(self):
        row = normalize_row({"url": "notion:x", "Entity": "X", "Monthly Revenue": 9})
        self.assertFalse(row.eligible_for_current_operating_totals)

    def test_normalization_requires_source_provenance(self):
        with self.assertRaisesRegex(ValueError, "source reference"):
            normalize_row({"Entity": "Unprovenanced"})

    def test_explicit_classification_enables_total(self):
        raw = {"url": "notion:x", "Entity": "X", "Monthly Revenue": 9, "Monthly Cost": 3}
        classification = Classification(
            TemporalState.CURRENT,
            AccountingTreatment.OPERATING_UNIT,
            "ruling:test",
            "synthetic fixture",
            timeline_id="test", effective_ordinal=1,
        )
        record = normalize_row(raw, source_classification("notion:x", classification))
        self.assertEqual(record.classification_authority_ref, "ruling:test")
        totals = consolidated_monthly_totals([record], timeline_id="test", as_of_ordinal=1)
        self.assertEqual(totals["monthly_revenue"], Decimal("9"))

    def test_entity_name_key_cannot_authorize_a_source_record(self):
        classification = Classification(
            TemporalState.CURRENT, AccountingTreatment.OPERATING_UNIT,
            "ruling:test", "synthetic fixture",
            timeline_id="test", effective_ordinal=1,
        )
        record = normalize_row(
            {"url": "notion:x", "Entity": "X", "Monthly Revenue": 9},
            {"entity:x": classification},
        )
        self.assertFalse(record.eligible_for_current_operating_totals)

    def test_classification_timeline_and_ordinal_are_strict(self):
        for ordinal in (-1, True, "1"):
            with self.assertRaisesRegex(ValueError, "ordinal"):
                Classification(
                    TemporalState.CURRENT, AccountingTreatment.OPERATING_UNIT,
                    "ruling:test", "invalid ordinal", timeline_id="test",
                    effective_ordinal=ordinal,
                )
        with self.assertRaisesRegex(ValueError, "whitespace"):
            Classification(
                TemporalState.CURRENT, AccountingTreatment.OPERATING_UNIT,
                "ruling:test", "invalid timeline", timeline_id=" test",
                effective_ordinal=1,
            )

    def test_missing_value_on_current_row_remains_unknown(self):
        classification = Classification(
            TemporalState.CURRENT, AccountingTreatment.OPERATING_UNIT,
            "ruling:test", "synthetic fixture",
            timeline_id="test", effective_ordinal=1,
        )
        record = normalize_row(
            {"url": "notion:x", "Entity": "X", "Monthly Revenue": 9, "Monthly Cost": None},
            source_classification("notion:x", classification),
        )
        totals = consolidated_monthly_totals([record], timeline_id="test", as_of_ordinal=1)
        self.assertEqual(totals["monthly_revenue"], Decimal("9"))
        self.assertIsNone(totals["monthly_cost"])

    def test_cost_center_adds_cost_but_financial_principal_adds_no_flow(self):
        cost_center = normalize_row(
            {"url": "notion:cost", "Entity": "Cost", "Monthly Cost": 150},
            source_classification("notion:cost", Classification(
                TemporalState.CURRENT, AccountingTreatment.COST_CENTER,
                "ruling:test", "synthetic cost center",
                timeline_id="test", effective_ordinal=1,
            )),
        )
        instrument = normalize_row(
            {"url": "notion:instrument", "Entity": "Instrument", "Monthly Revenue": 1000, "Monthly Cost": 2},
            source_classification("notion:instrument", Classification(
                TemporalState.CURRENT, AccountingTreatment.FINANCIAL_INSTRUMENT,
                "ruling:test", "principal is not an operating flow",
                timeline_id="test", effective_ordinal=1,
            )),
        )
        totals = consolidated_monthly_totals(
            [cost_center, instrument], timeline_id="test", as_of_ordinal=1
        )
        self.assertEqual(totals["monthly_revenue"], Decimal("0"))
        self.assertEqual(totals["monthly_cost"], Decimal("150"))

    def test_em_dash_parent_alias_cannot_evade_overlap_guard(self):
        classification = Classification(
            TemporalState.CURRENT, AccountingTreatment.OPERATING_UNIT,
            "ruling:test", "synthetic fixture",
            timeline_id="test", effective_ordinal=1,
        )
        parent = normalize_row(
            {"url": "notion:luskan", "Entity": "Northern Crown Financial - Luskan", "Monthly Revenue": 9583},
            source_classification("notion:luskan", classification),
        )
        child = normalize_row(
            {"url": "notion:service", "Entity": "Verification Services", "Parent Entity": "Northern Crown Financial — Luskan", "Monthly Revenue": 2917},
            source_classification("notion:service", classification),
        )
        with self.assertRaisesRegex(ConsolidationError, "parent and child"):
            consolidated_monthly_totals([parent, child], timeline_id="test", as_of_ordinal=1)

    def test_root_dash_is_not_a_substantive_parent(self):
        row = normalize_row({"url": "notion:x", "Entity": "X", "Parent Entity": "—"})
        self.assertIsNone(row.parent_name)

    def test_consolidation_refuses_eligible_parent_and_child(self):
        classification = Classification(
            TemporalState.CURRENT,
            AccountingTreatment.OPERATING_UNIT,
            "ruling:test",
            "synthetic fixture",
            timeline_id="test", effective_ordinal=1,
        )
        parent = normalize_row(
            {"url": "notion:p", "Entity": "Parent", "Monthly Revenue": 10},
            source_classification("notion:p", classification),
        )
        child = normalize_row(
            {"url": "notion:c", "Entity": "Child", "Parent Entity": "Parent", "Monthly Revenue": 5},
            source_classification("notion:c", classification),
        )
        with self.assertRaises(ConsolidationError):
            consolidated_monthly_totals([parent, child], timeline_id="test", as_of_ordinal=1)

    def test_mathematically_valid_large_loss_margin_is_not_a_unit_error(self):
        audit = audit_rows([{
            "url": "notion:loss", "Entity": "Loss", "Monthly Revenue": 30,
            "Monthly Cost": 150, "Profit Margin": -4,
        }])
        self.assertNotIn("margin_arithmetic_mismatch", {issue.code for issue in audit.issues})

    def test_known_projection_future_and_superseded_shapes_are_flagged(self):
        audit = audit_rows([
            {
                "url": "https://app.notion.com/p/34ce821484b081febf14f062ef3cb91b",
                "Entity": "Zariel Warborn Contract", "Monthly Revenue": 747000,
                "Notes": "Projected monthly profit at full scale",
            },
            {
                "url": "notion:future", "Entity": "Future Facility",
                "Status": "Operational", "Date Operational": "1498 DR",
            },
            {
                "url": "notion:old", "Entity": "[SUPERSEDED] Guardian's Gate Settlement",
                "Monthly Cost": 3000,
            },
        ])
        codes = {issue.code for issue in audit.issues}
        self.assertIn("projection_in_current_field", codes)
        self.assertIn("future_dated_row", codes)
        self.assertIn("superseded_row", codes)

    def test_superseded_source_cannot_be_classified_current(self):
        classification = Classification(
            TemporalState.CURRENT, AccountingTreatment.OPERATING_UNIT,
            "ruling:test", "synthetic fixture",
            timeline_id="test", effective_ordinal=1,
        )
        with self.assertRaisesRegex(ValueError, "superseded"):
            normalize_row(
                {"url": "notion:old", "Entity": "[SUPERSEDED] Old Business"},
                source_classification("notion:old", classification),
            )
        for marker in (
            {"Status": "Superseded"},
            {"Current Activity": "Superseded by replacement"},
        ):
            with self.assertRaisesRegex(ValueError, "superseded"):
                normalize_row(
                    {"url": "notion:old", "Entity": "Old Business", **marker},
                    source_classification("notion:old", classification),
                )

    def test_projection_cannot_be_classified_current(self):
        source_ref = "https://app.notion.com/p/34ce821484b081febf14f062ef3cb91b"
        classification = Classification(
            TemporalState.CURRENT, AccountingTreatment.OPERATING_UNIT,
            "ruling:test", "must not override projected source values",
            timeline_id="test", effective_ordinal=1,
        )
        with self.assertRaisesRegex(ValueError, "projected"):
            normalize_row(
                {
                    "url": source_ref,
                    "Entity": "Zariel Warborn Contract",
                    "Monthly Revenue": 747000,
                    "Notes": "Projected monthly profit at full scale",
                },
                source_classification(source_ref, classification),
            )

    def test_consolidation_rejects_handmade_record_without_source_identity(self):
        record = EntityRecord(
            "entity:x", "X", "fixture:x",
            timeline_id="test", effective_ordinal=1,
            temporal_state=TemporalState.CURRENT,
            treatment=AccountingTreatment.OPERATING_UNIT,
            monthly_revenue=Decimal("9"), monthly_cost=Decimal("3"),
        )
        with self.assertRaisesRegex(ConsolidationError, "source identity"):
            consolidated_monthly_totals([record], timeline_id="test", as_of_ordinal=1)

    def test_consolidation_revalidates_handmade_current_records(self):
        valid = normalize_row(
            {"url": "notion:x", "Entity": "X", "Monthly Revenue": 9, "Monthly Cost": 3},
            source_classification("notion:x", Classification(
                TemporalState.CURRENT, AccountingTreatment.OPERATING_UNIT,
                "ruling:test", "boundary fixture", timeline_id="test",
                effective_ordinal=1,
            )),
        )
        for ordinal in (-1, True, "1"):
            with self.assertRaisesRegex(ConsolidationError, "ordinal"):
                consolidated_monthly_totals(
                    [replace(valid, effective_ordinal=ordinal)],
                    timeline_id="test",
                    as_of_ordinal=1,
                )
        with self.assertRaisesRegex(ConsolidationError, "classification provenance"):
            consolidated_monthly_totals(
                [replace(valid, classification_authority_ref=None)],
                timeline_id="test",
                as_of_ordinal=1,
            )
        with self.assertRaisesRegex(ConsolidationError, "superseded"):
            consolidated_monthly_totals(
                [replace(valid, name="[SUPERSEDED] Manual")],
                timeline_id="test",
                as_of_ordinal=1,
            )
        with self.assertRaisesRegex(ConsolidationError, "finite Decimal"):
            consolidated_monthly_totals(
                [replace(valid, monthly_revenue=9)],
                timeline_id="test",
                as_of_ordinal=1,
            )

    def test_consolidation_is_scoped_to_timeline_and_as_of_ordinal(self):
        current = normalize_row(
            {"url": "notion:x", "Entity": "X", "Monthly Revenue": 9, "Monthly Cost": 3},
            source_classification("notion:x", Classification(
                TemporalState.CURRENT, AccountingTreatment.OPERATING_UNIT,
                "ruling:test", "timeline test", timeline_id="arik", effective_ordinal=5,
            )),
        )
        before = consolidated_monthly_totals([current], timeline_id="arik", as_of_ordinal=4)
        self.assertEqual(before, {"monthly_revenue": Decimal("0"), "monthly_cost": Decimal("0")})
        with self.assertRaisesRegex(ConsolidationError, "unknown"):
            consolidated_monthly_totals([current], timeline_id="jormun", as_of_ordinal=99)
        with self.assertRaisesRegex(ConsolidationError, "whitespace"):
            consolidated_monthly_totals([current], timeline_id=" arik", as_of_ordinal=5)
        with self.assertRaisesRegex(ConsolidationError, "non-negative"):
            consolidated_monthly_totals([current], timeline_id="arik", as_of_ordinal=-1)


if __name__ == "__main__":
    unittest.main()
