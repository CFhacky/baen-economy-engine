from __future__ import annotations

from dataclasses import replace
from decimal import Decimal, getcontext, setcontext
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
sys.path.insert(0, str(SRC))

from baen_economy.food_security import (  # noqa: E402
    DEFAULT_LADEN_FIXTURE_PATH,
    FOOD_SECURITY_SCHEMA,
    FoodSecurityError,
    FoodSecuritySourceError,
    LongsaddleAssumptions,
    ObjectiveStatus,
    ProvenanceKind,
    illustrative_low_v1,
    illustrative_low_v1_assumptions,
    load_longsaddle_source_facts,
    plan_longsaddle_food_security,
    plan_longsaddle_grain,
)
from baen_economy.operator_codec import canonical_hash  # noqa: E402


D = Decimal


def complete_assumptions(**changes: object) -> LongsaddleAssumptions:
    values: dict[str, object] = {
        "assumption_source": "test explicit assumptions",
        "selected_target_tons": D("1200"),
        "supplier_stock_tons": D("1200"),
        "opening_longsaddle_stock_tons": D("0"),
        "demand_tons": D("300"),
        "dispatch_requested_tons": D("1200"),
        "route_capacity_tons_per_trip": D("1200"),
        "route_trips": 1,
        "travel_periods": 1,
        "loss_rate": D("0"),
        "storage_capacity_tons": D("1200"),
        "price_gp_per_ton": D("50"),
        "funding_gp": D("65000"),
    }
    values.update(changes)
    return LongsaddleAssumptions(**values)


class FoodSecuritySourceTests(unittest.TestCase):
    def test_both_fixtures_resolve_the_locked_forward_scenario(self) -> None:
        facts = load_longsaddle_source_facts()

        self.assertEqual(facts.scenario_id, "operation-laden-table")
        self.assertEqual(
            facts.timeline_id,
            "source:operation-laden-table-late-kythorn-1495",
        )
        self.assertEqual(facts.campaign_date, "late Kythorn 1495 DR")
        self.assertEqual(facts.population_mouths, 11000)
        self.assertEqual(facts.longsaddle_population, 11000)
        self.assertEqual(facts.grain_target_low_tons, D("1200"))
        self.assertEqual(facts.grain_target_high_tons, D("1500"))
        self.assertEqual(facts.grain_procured_tons, D("0"))
        self.assertEqual(facts.grain_budget_low_gp, D("65000"))
        self.assertEqual(facts.grain_budget_high_gp, D("95000"))
        self.assertEqual(facts.harvest_window, "Eleint-Marpenoth 1495")
        self.assertEqual(facts.harvest_outcome, "unresolved")
        self.assertFalse(facts.actual_execution_eligible)
        self.assertEqual(len(facts.source_refs), 2)

    def test_project_root_selects_both_reviewed_fixture_paths(self) -> None:
        facts = load_longsaddle_source_facts(project_root=PROJECT)
        self.assertEqual(facts.population_mouths, 11000)

    def test_disagreement_between_fixtures_fails_closed(self) -> None:
        payload = json.loads(DEFAULT_LADEN_FIXTURE_PATH.read_text(encoding="utf-8"))
        payload["population_mouths"] = 10999
        with tempfile.TemporaryDirectory(prefix="food source drift ") as folder:
            changed = Path(folder) / "operation-laden-table.json"
            changed.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(
                FoodSecuritySourceError, "population fixtures disagree"
            ):
                load_longsaddle_source_facts(laden_fixture_path=changed)


class FoodSecurityAssumptionTests(unittest.TestCase):
    def test_missing_assumptions_remain_none_and_are_not_zero(self) -> None:
        assumptions = LongsaddleAssumptions(
            assumption_source="deliberately incomplete test"
        )
        result = plan_longsaddle_food_security(assumptions)

        self.assertEqual(result.objective_status, ObjectiveStatus.AT_RISK)
        self.assertIsNone(result.requested_tons)
        self.assertIsNone(result.dispatched_tons)
        self.assertIsNone(result.lost_tons)
        self.assertIsNone(result.delivered_tons)
        self.assertIsNone(result.consumed_tons)
        self.assertIsNone(result.closing_tons)
        self.assertIsNone(result.conservation_residual_tons)
        self.assertEqual(result.source_facts.grain_procured_tons, D("0"))
        self.assertEqual(
            result.provenance["supplier_stock_tons"].kind,
            ProvenanceKind.UNKNOWN,
        )
        self.assertIn(
            "zero was not assumed",
            result.provenance["supplier_stock_tons"].basis,
        )
        self.assertIn("supplier_stock_tons", result.decision_brief["Unknown"])
        self.assertEqual(result.to_dict()["assumptions"]["supplier_stock_tons"], None)

    def test_explicit_zero_is_valid_and_observably_different_from_missing(self) -> None:
        result = plan_longsaddle_food_security(
            complete_assumptions(supplier_stock_tons=D("0"))
        )

        self.assertEqual(result.dispatched_tons, D("0"))
        self.assertEqual(result.supplier_gap_tons, D("1200"))
        self.assertEqual(result.lost_tons, D("0"))
        self.assertEqual(result.delivered_tons, D("0"))
        self.assertEqual(result.consumed_tons, D("0"))
        self.assertEqual(result.unmet_demand_tons, D("300"))
        self.assertEqual(result.conservation_residual_tons, D("0"))
        self.assertEqual(result.objective_status, ObjectiveStatus.FAILED)
        self.assertEqual(
            result.provenance["supplier_stock_tons"].kind,
            ProvenanceKind.ASSUMPTION,
        )

    def test_decimal_inputs_are_strict_and_target_stays_in_source_band(self) -> None:
        with self.assertRaisesRegex(FoodSecurityError, "explicit finite Decimal"):
            LongsaddleAssumptions(supplier_stock_tons=1200.0)
        with self.assertRaisesRegex(FoodSecurityError, "travel_periods must be at least 1"):
            LongsaddleAssumptions(travel_periods=0)
        with self.assertRaisesRegex(FoodSecurityError, r"loss_rate must be in \[0, 1\)"):
            LongsaddleAssumptions(loss_rate=D("1"))
        with self.assertRaisesRegex(FoodSecurityError, "1200-1500 ton band"):
            plan_longsaddle_food_security(
                complete_assumptions(selected_target_tons=D("1199"))
            )

    def test_from_mapping_parses_decimal_text_but_rejects_numeric_coercion(self) -> None:
        assumptions = LongsaddleAssumptions.from_mapping(
            {
                "assumption_source": "JSON request",
                "selected_target_tons": "1300.50",
                "route_trips": 3,
                "travel_periods": 2,
            }
        )
        self.assertEqual(assumptions.selected_target_tons, D("1300.50"))
        self.assertEqual(assumptions.route_trips, 3)
        self.assertIsNone(assumptions.supplier_stock_tons)
        with self.assertRaisesRegex(FoodSecurityError, "exact decimal text"):
            LongsaddleAssumptions.from_mapping({"selected_target_tons": 1300})
        with self.assertRaisesRegex(FoodSecurityError, "unknown Longsaddle"):
            LongsaddleAssumptions.from_mapping({"invented_default": "0"})


class FoodSecurityPlanningTests(unittest.TestCase):
    def test_illustrative_low_v1_reproduces_the_known_answer(self) -> None:
        result = illustrative_low_v1()

        self.assertEqual(result.profile_id, "illustrative-low-v1")
        self.assertFalse(result.canonical)
        self.assertEqual(
            result.assumptions.assumption_source,
            "illustrative-low-v1 non-canon scenario assumptions",
        )
        self.assertEqual(result.objective_status, ObjectiveStatus.AT_RISK)
        self.assertEqual(result.requested_tons, D("1200"))
        self.assertEqual(result.route_capacity_tons, D("900"))
        self.assertEqual(result.dispatched_tons, D("900"))
        self.assertEqual(result.dispatch_gap_tons, D("300"))
        self.assertEqual(result.target_gap_tons, D("300"))
        self.assertEqual(result.capacity_gap_tons, D("300"))
        self.assertEqual(result.lost_tons, D("18.00"))
        self.assertEqual(result.route_loss_tons, D("18.00"))
        self.assertEqual(result.delivered_tons, D("882.00"))
        self.assertEqual(result.consumed_tons, D("300"))
        self.assertEqual(result.unmet_demand_tons, D("0"))
        self.assertEqual(result.closing_tons, D("582.00"))
        self.assertEqual(result.closing_longsaddle_tons, D("582.00"))
        self.assertEqual(result.storage_gap_tons, D("0"))
        self.assertEqual(result.conservation_residual_tons, D("0.00"))
        self.assertEqual(result.coverage_periods, D("1.94"))
        self.assertEqual(result.arrival_period, 2)
        self.assertEqual(result.stockout_period, 4)

    def test_complete_feasible_plan_is_met(self) -> None:
        result = plan_longsaddle_grain(complete_assumptions())

        self.assertEqual(result.objective_status, ObjectiveStatus.MET)
        self.assertEqual(result.dispatched_tons, D("1200"))
        self.assertEqual(result.target_gap_tons, D("0"))
        self.assertEqual(result.delivered_tons, D("1200"))
        self.assertEqual(result.consumed_tons, D("300"))
        self.assertEqual(result.closing_tons, D("900"))
        self.assertEqual(result.cost_gap_gp, D("0"))
        self.assertEqual(result.funding_gap_gp, D("0"))
        self.assertEqual(result.conservation_residual_tons, D("0"))

    def test_immediate_food_shortage_is_failed(self) -> None:
        result = plan_longsaddle_food_security(
            complete_assumptions(demand_tons=D("1300"), storage_capacity_tons=D("1500"))
        )

        self.assertEqual(result.consumed_tons, D("1200"))
        self.assertEqual(result.unmet_demand_tons, D("100"))
        self.assertEqual(result.closing_tons, D("0"))
        self.assertEqual(result.stockout_period, 2)
        self.assertEqual(result.objective_status, ObjectiveStatus.FAILED)
        self.assertEqual(result.conservation_residual_tons, D("0"))

    def test_capacity_storage_cost_and_funding_gaps_are_separate(self) -> None:
        assumptions = complete_assumptions(
            supplier_stock_tons=D("1500"),
            route_capacity_tons_per_trip=D("900"),
            demand_tons=D("0"),
            storage_capacity_tons=D("500"),
            price_gp_per_ton=D("110"),
            funding_gp=D("70000"),
        )
        result = plan_longsaddle_food_security(assumptions)

        self.assertEqual(result.capacity_gap_tons, D("300"))
        self.assertEqual(result.dispatch_gap_tons, D("300"))
        self.assertEqual(result.dispatched_tons, D("900"))
        self.assertEqual(result.storage_gap_tons, D("400"))
        self.assertEqual(result.closing_tons, D("500"))
        self.assertEqual(result.estimated_cost_gp, D("99000"))
        self.assertEqual(result.cost_gap_gp, D("4000"))
        self.assertEqual(result.funding_gap_gp, D("29000"))
        self.assertIsNone(result.coverage_periods)
        self.assertIsNone(result.stockout_period)
        self.assertEqual(
            result.provenance["coverage_periods"].kind,
            ProvenanceKind.UNKNOWN,
        )
        self.assertIn("not applicable", result.provenance["coverage_periods"].basis)
        self.assertEqual(result.conservation_residual_tons, D("0"))

    def test_supplier_and_capacity_constraints_do_not_double_count_dispatch(self) -> None:
        result = plan_longsaddle_food_security(
            complete_assumptions(
                supplier_stock_tons=D("800"),
                route_capacity_tons_per_trip=D("900"),
            )
        )
        self.assertEqual(result.supplier_gap_tons, D("400"))
        self.assertEqual(result.capacity_gap_tons, D("300"))
        self.assertEqual(result.dispatched_tons, D("800"))
        self.assertEqual(result.dispatch_gap_tons, D("400"))

    def test_decimal_context_cannot_change_the_result(self) -> None:
        original = getcontext().copy()
        try:
            getcontext().prec = 4
            low_precision = illustrative_low_v1()
            getcontext().prec = 28
            ordinary_precision = illustrative_low_v1()
        finally:
            setcontext(original)
        self.assertEqual(low_precision, ordinary_precision)


class FoodSecurityProvenanceTests(unittest.TestCase):
    def test_every_result_field_has_source_assumption_derived_or_unknown_provenance(self) -> None:
        result = illustrative_low_v1()
        expected_sections = {"Source", "Assumption", "Derived", "Unknown"}
        self.assertEqual(set(result.decision_brief), expected_sections)
        self.assertEqual(
            result.provenance["population_mouths"].kind,
            ProvenanceKind.SOURCE,
        )
        self.assertEqual(
            result.provenance["selected_target_tons"].kind,
            ProvenanceKind.ASSUMPTION,
        )
        self.assertEqual(
            result.provenance["dispatched_tons"].kind,
            ProvenanceKind.DERIVED,
        )
        self.assertEqual(
            result.provenance["harvest_result_tons"].kind,
            ProvenanceKind.UNKNOWN,
        )
        for field_name in (
            "objective_status",
            "requested_tons",
            "dispatched_tons",
            "lost_tons",
            "delivered_tons",
            "consumed_tons",
            "closing_tons",
            "capacity_gap_tons",
            "storage_gap_tons",
            "cost_gap_gp",
            "funding_gap_gp",
            "coverage_periods",
            "stockout_period",
            "conservation_residual_tons",
        ):
            self.assertIn(field_name, result.provenance)

    def test_serialized_contract_is_hash_bound_and_non_canonical(self) -> None:
        payload = illustrative_low_v1().to_dict()
        digest = payload.pop("content_hash")

        self.assertEqual(payload["schema"], FOOD_SECURITY_SCHEMA)
        self.assertEqual(payload["schema"], "tnp.food-security.longsaddle-plan/1")
        self.assertTrue(payload["planning_only"])
        self.assertFalse(payload["canonical"])
        self.assertFalse(payload["campaign_time_advanced"])
        self.assertEqual(digest, canonical_hash(payload))
        self.assertEqual(
            set(payload["decision_brief"]),
            {"Source", "Assumption", "Derived", "Unknown"},
        )
        self.assertEqual(payload["requested_tons"], "1200")
        self.assertEqual(payload["dispatched_tons"], "900")
        self.assertEqual(payload["lost_tons"], "18.00")
        self.assertEqual(payload["delivered_tons"], "882.00")
        self.assertEqual(payload["consumed_tons"], "300")
        self.assertEqual(payload["closing_tons"], "582.00")
        self.assertEqual(payload["conservation_residual_tons"], "0.00")

    def test_assumption_helper_is_explicitly_non_canon(self) -> None:
        assumptions = illustrative_low_v1_assumptions()
        self.assertIn("non-canon", assumptions.assumption_source)
        result = plan_longsaddle_food_security(assumptions)
        self.assertFalse(result.canonical)
        self.assertIsNone(result.profile_id)


if __name__ == "__main__":
    unittest.main()
