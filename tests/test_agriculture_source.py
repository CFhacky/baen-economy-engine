from __future__ import annotations

import copy
from decimal import Decimal
import json
from pathlib import Path
import sys
import tempfile
from types import MappingProxyType
import unittest


PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
sys.path.insert(0, str(SRC))

from baen_economy.agriculture_source import (  # noqa: E402
    DEFAULT_AGRICULTURE_CANON_PATH,
    AgricultureSourceError,
    load_agriculture_canon,
)
from baen_economy.source_values import (  # noqa: E402
    AuthorityClass,
    DecimalRange,
    EvidenceLayer,
    EvidenceReference,
    SourceValueError,
    SourcedValue,
)


class AgricultureSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = json.loads(DEFAULT_AGRICULTURE_CANON_PATH.read_text(encoding="utf-8"))
        cls.canon = load_agriculture_canon()

    def load_changed(self, change) -> object:
        payload = copy.deepcopy(self.raw)
        change(payload)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "agriculture.json"
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return load_agriculture_canon(path)

    def assert_rejected(self, change, message: str) -> None:
        with self.assertRaisesRegex(AgricultureSourceError, message):
            self.load_changed(change)

    def test_live_boundary_is_day7_and_forward_state_is_not_current(self) -> None:
        current = self.canon.current_actual_state
        forward = self.canon.forward_k1495_state
        self.assertEqual(
            current.campaign_date, "Day 7 Hammer 1495 DR, midday Hell-cycle"
        )
        self.assertTrue(current.live_freeze)
        self.assertFalse(current.advance_authorized)
        self.assertFalse(current.agriculture_month_close_authorized)
        self.assertEqual(current.evidence.layer, EvidenceLayer.CURRENT_ACTUAL)
        self.assertEqual(current.evidence.source_id, "arik-live-freeze")
        self.assertEqual(forward.campaign_date, "late Kythorn 1495 DR")
        self.assertEqual(
            forward.temporal_class,
            "ratified_forward_scenario_not_current_actual",
        )
        self.assertFalse(forward.actual_execution_eligible)
        self.assertTrue(
            all(item.layer is EvidenceLayer.FORWARD_SCENARIO for item in forward.evidence)
        )
        self.assertFalse(self.canon.actual_month_close_allowed)
        self.assertFalse(self.canon.physical_execution_ready)

    def test_exact_decimal_ranges_and_named_species_survive_import(self) -> None:
        tilapia = self.canon.species_by_name["Tilapia"]
        self.assertEqual(tilapia.scientific_name, "Oreochromis niloticus")
        self.assertIsInstance(tilapia.growth_months, DecimalRange)
        self.assertEqual(tilapia.growth_months.low, Decimal("6"))
        self.assertEqual(tilapia.growth_months.high, Decimal("8"))
        self.assertEqual(tilapia.stocking_density.unit, "fish_per_cubic_meter")
        self.assertEqual(
            self.canon.confirmed_production.converted_quarry.confirmed_species,
            ("Tilapia",),
        )
        self.assertEqual(
            self.canon.confirmed_production.reservoir_fisheries.confirmed_outputs,
            ("fish", "trout", "salmon"),
        )
        self.assertFalse(tilapia.actual_execution_eligible)

    def test_named_crop_program_does_not_promote_design_options(self) -> None:
        crops = self.canon.crops_by_name
        self.assertEqual(len(crops), 12)
        self.assertIn("Neverwinter Wine Grapes", crops)
        self.assertIn("Aqua-Enhanced Specialty Herbs", crops)
        planted = [crop.name for crop in crops.values() if crop.confirmed_planted]
        self.assertEqual(planted, ["Tomatoes"])
        self.assertFalse(self.canon.crop_program.actual_execution_eligible)

    def test_missing_is_not_zero(self) -> None:
        shelters = self.canon.confirmed_production.shelters
        self.assertIsNone(shelters.baseline_physical_yield)
        self.assertEqual(self.canon.forward_k1495_state.grain_procured_tons, Decimal("0"))
        by_id = {item.entity_id: item for item in self.canon.registry_entities}
        self.assertIsNone(by_id["orchard-chapel"].monthly_revenue_gp)
        self.assertEqual(by_id["lobster-king"].monthly_revenue_gp, Decimal("0"))

    def test_forward_zero_cannot_be_required_as_current_actual(self) -> None:
        fact = self.canon.forward_grain_procured_fact()
        self.assertEqual(fact.value, Decimal("0"))
        self.assertFalse(fact.actual_execution_input)
        with self.assertRaisesRegex(SourceValueError, "not eligible"):
            fact.require_actual()

    def test_projected_and_unconfirmed_evidence_cannot_be_actual_input(self) -> None:
        for authority, layer in (
            (AuthorityClass.PROJECTION, EvidenceLayer.PROJECTION),
            (AuthorityClass.UNCONFIRMED, EvidenceLayer.UNCONFIRMED),
            (AuthorityClass.RATIFIED_CAMPAIGN_STATE, EvidenceLayer.FORWARD_SCENARIO),
        ):
            evidence = EvidenceReference("source", "test/path", authority, layer)
            with self.assertRaisesRegex(SourceValueError, "cannot become"):
                SourcedValue(Decimal("1"), (evidence,), actual_execution_input=True)

    def test_commercial_reference_totals_are_exact(self) -> None:
        baseline = [
            item
            for item in self.canon.registry_entities
            if item.status == "Operational" and item.as_of == "Eleint 20, 1494"
        ]
        self.assertEqual(len(baseline), 5)
        self.assertEqual(sum(item.employees or 0 for item in baseline), 63)
        self.assertEqual(
            sum((item.monthly_revenue_gp for item in baseline), Decimal("0")),
            Decimal("26500"),
        )
        self.assertEqual(
            sum((item.monthly_cost_gp for item in baseline), Decimal("0")),
            Decimal("20550"),
        )

    def test_nmwc_topology_and_yield_totals_reconcile_but_are_not_actual(self) -> None:
        topology = self.canon.nmwc_topology
        self.assertEqual(sum(item.ponds for item in self.canon.nmwc_pond_groups), 10)
        self.assertEqual(
            sum(
                (item.annual_yield_lb for item in self.canon.nmwc_pond_groups),
                Decimal("0"),
            ),
            Decimal("101000"),
        )
        self.assertEqual(
            topology.capacity_each_cubic_meters * topology.ponds,
            topology.total_capacity_cubic_meters,
        )
        self.assertFalse(topology.day7_hammer1495_execution_eligible)
        self.assertFalse(topology.actual_execution_eligible)

    def test_additive_source_sections_are_preserved_as_immutable_raw_json(self) -> None:
        self.assertEqual(
            set(self.canon.additive_sections),
            {
                "dated_agricultural_systems",
                "logistics_reference",
                "faction_beliefs_cross_reference",
            },
        )
        self.assertIsInstance(self.canon.additive_sections, MappingProxyType)
        dated = self.canon.additive_sections["dated_agricultural_systems"]
        self.assertIsInstance(dated, tuple)
        self.assertEqual(dated[0]["system_id"], "ravencrest-estate")
        self.assertFalse(dated[0]["day7_hammer1495_execution_eligible"])
        linked = self.canon.confirmed_production.shelters.additive_fields[
            "linked_confirmed_outputs"
        ]
        self.assertEqual(linked[0]["name"], "cold-frame vegetables")
        self.assertEqual(linked[0]["source_id"], "longsaddle")
        later_lobster = self.canon.confirmed_production.additive_sections[
            "lobster_king_later_authority"
        ]
        self.assertEqual(later_lobster["weekly_output_tons"], "2")

    def test_new_additive_root_section_is_tolerated_and_preserved(self) -> None:
        changed = self.load_changed(
            lambda payload: payload.__setitem__(
                "future_reviewed_section", {"claim": "preserved", "amount": "1.25"}
            )
        )
        self.assertEqual(
            changed.additive_sections["future_reviewed_section"]["claim"],
            "preserved",
        )

    def test_unknown_key_inside_typed_species_fails_closed(self) -> None:
        self.assert_rejected(
            lambda payload: payload["species"][0].__setitem__("invented_yield", "999"),
            "species 1 keys differ",
        )

    def test_generic_species_replacement_is_rejected(self) -> None:
        self.assert_rejected(
            lambda payload: payload["species"][1].__setitem__("name", "Fish"),
            "lost its canonical",
        )

    def test_source_url_must_match_exact_page_id(self) -> None:
        self.assert_rejected(
            lambda payload: payload["sources"][0].__setitem__(
                "url", "https://app.notion.com/p/00000000000000000000000000000000"
            ),
            "does not identify its exact Notion page",
        )

    def test_unknown_source_reference_in_additive_section_is_rejected(self) -> None:
        self.assert_rejected(
            lambda payload: payload["dated_agricultural_systems"][0].__setitem__(
                "source_id", "invented-source"
            ),
            "cites an unknown source",
        )

    def test_current_date_and_forward_eligibility_fail_closed(self) -> None:
        self.assert_rejected(
            lambda payload: payload["current_actual_state"].__setitem__(
                "campaign_date", "late Kythorn 1495 DR"
            ),
            "current actual campaign date",
        )
        self.assert_rejected(
            lambda payload: payload["forward_k1495_state"].__setitem__(
                "actual_execution_eligible", True
            ),
            "cannot be actual",
        )

    def test_financial_and_topology_totals_fail_closed(self) -> None:
        self.assert_rejected(
            lambda payload: payload["registry_entities"][0].__setitem__(
                "monthly_revenue_gp", "1501"
            ),
            "totals do not reconcile",
        )
        self.assert_rejected(
            lambda payload: payload["nmwc_topology"].__setitem__(
                "total_annual_yield_lb", "101001"
            ),
            "yields do not match total",
        )

    def test_safety_boundary_is_literal(self) -> None:
        self.assertEqual(
            dict(self.canon.safety),
            {
                "notion_writes": 0,
                "canonical_ledger_postings": 0,
                "dice_rolled": 0,
                "campaign_time_advanced": False,
            },
        )
        self.assert_rejected(
            lambda payload: payload["safety"].__setitem__("notion_writes", 1),
            "unsafe side effects",
        )

    def test_binary_float_in_additive_section_is_rejected(self) -> None:
        self.assert_rejected(
            lambda payload: payload.__setitem__("unsafe_addition", {"value": 1.25}),
            "inexact binary float",
        )

    def test_canonical_hash_is_order_independent_and_content_sensitive(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "reordered.json"
            path.write_text(
                json.dumps(dict(reversed(list(self.raw.items()))), ensure_ascii=False),
                encoding="utf-8",
            )
            reordered = load_agriculture_canon(path)
        self.assertEqual(reordered.content_hash, self.canon.content_hash)
        changed = self.load_changed(
            lambda payload: payload.__setitem__(
                "warning", payload["warning"] + " Reviewed content change."
            )
        )
        self.assertNotEqual(changed.content_hash, self.canon.content_hash)
        self.assertRegex(self.canon.content_hash, r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
