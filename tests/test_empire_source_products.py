from __future__ import annotations

import json
import unittest
from pathlib import Path

from baen_economy.empire_source_products import (
    ARTERIAL_ROUTE_SPECS,
    CENSUS_SPECS,
    DEFAULT_SOURCE_INPUTS,
    FOOD_AGGREGATE_SPECS,
    FOOD_ENTITY_SPECS,
    PRODUCTION_LINE_SPECS,
    source_known_state,
    source_production_lines,
    source_semantic_domains,
    _map_openttd_source_candidate,
)


class EmpireSourceProductsTests(unittest.TestCase):
    def test_production_lines_are_loaded_from_source_authority(self):
        lines = source_production_lines()
        self.assertEqual(len(lines), 9)
        by_id = {row["id"]: row for row in lines}
        self.assertEqual(by_id["brickworks"]["quantity"], 75000)
        self.assertEqual(by_id["clay_quarries"]["quantity"], 2000)
        self.assertEqual(by_id["silversheen_aluminum"]["quantity"], 180)
        self.assertEqual(by_id["star_metal_hills_bauxite"]["quantity"], 800)
        self.assertEqual(by_id["warborn_neverwinter"]["quantity"], 12)
        self.assertEqual(by_id["warborn_neverwinter"]["maximum"], 15)
        self.assertEqual(by_id["treasury_quarries"]["quantity"], 8000)
        self.assertEqual(by_id["azurite_quarries"]["quantity"], 200)
        self.assertEqual(by_id["western_limestone"]["quantity"], 12000)
        self.assertEqual(by_id["western_sandstone"]["quantity"], 6000)
        for row in lines:
            self.assertEqual(row["authority"], "SOURCE-DERIVED")
            self.assertFalse(row["recipe_invented"])
            self.assertTrue(str(row["source"]["notion_page"]))
            self.assertTrue(str(row["source"]["title"]))

    def test_every_spec_key_exists_in_authority(self):
        payload = json.loads(Path(DEFAULT_SOURCE_INPUTS).read_text(encoding="utf-8"))
        keys = {row["key"] for row in payload["facts"]}
        for spec in PRODUCTION_LINE_SPECS:
            self.assertIn(spec.quantity_key, keys)
            self.assertIn(spec.employees_key, keys)
            if spec.maximum_key:
                self.assertIn(spec.maximum_key, keys)

    def test_silversheen_cost_and_allocation_remain_fail_closed(self):
        payload = json.loads(Path(DEFAULT_SOURCE_INPUTS).read_text(encoding="utf-8"))
        blockers = {row["key"]: row for row in payload["blockers"]}
        self.assertEqual(blockers["silversheen.current_monthly_cost_gp"]["status"], "MISSING_DATA")
        self.assertEqual(blockers["silversheen.warborn_aluminum_allocation"]["status"], "CONFLICT")
        self.assertIn("Do not scale", blockers["silversheen.current_monthly_cost_gp"]["reason"])

    def test_known_state_reports_census_food_and_routes_without_inventing(self):
        state = source_known_state()
        by_id = {row["id"]: row for row in state["census"]}
        self.assertEqual(by_id["neverwinter"]["population"], 75000)
        self.assertEqual(by_id["waterdeep"]["population"], 130000)
        self.assertIsNone(by_id["forgedeep"]["population"])
        self.assertEqual(by_id["forgedeep"]["status"], "MISSING_DATA")
        food = {row["id"]: row for row in state["food_financials"]}
        self.assertEqual(food["agricultural_shelters"]["monthly_revenue_gp"], 1500)
        self.assertEqual(food["blacklake_aquaculture"]["employees"], 15)
        self.assertIsNone(food["blacklake_aquaculture"]["physical_output"])
        self.assertEqual(food["combined_food_financials"]["kind"], "aggregate")
        self.assertEqual(food["combined_food_financials"]["monthly_revenue_gp"], 26500)
        self.assertEqual(len(state["arterial_routes"]), 5)
        for row in state["arterial_routes"]:
            self.assertTrue(row["approximate"])
            self.assertIsNone(row["capacity"])
        joined = " ".join(state["unresolved"])
        self.assertIn("Forgedeep civilian population remains unknown", joined)
        self.assertIn("80,000", joined)
        payload = json.loads(Path(DEFAULT_SOURCE_INPUTS).read_text(encoding="utf-8"))
        keys = {row["key"] for row in payload["facts"]}
        for spec in CENSUS_SPECS:
            self.assertIn(spec["population_key"], keys)
        for spec in FOOD_ENTITY_SPECS + FOOD_AGGREGATE_SPECS:
            self.assertIn(spec["employees_key"], keys)
            self.assertIn(spec["revenue_key"], keys)
        for _route_id, _label, key in ARTERIAL_ROUTE_SPECS:
            self.assertIn(key, keys)

    def test_semantic_domains_map_recovered_evidence_without_closing_real_gaps(self):
        domains = source_semantic_domains()
        finance = domains["finance_banking"]
        finance_known = {row["key"]: row for row in finance["known"]}
        self.assertEqual(finance_known["ncf.active_loans_gp"]["value"], 2300000)
        self.assertEqual(
            finance_known["finance.ncf_active_loan_portfolio"]["value"],
            2300000,
        )
        self.assertEqual(
            finance_known["finance.ncf_active_loan_portfolio"]["source"]["title"],
            "Empire Financial State — Current Reference",
        )
        self.assertFalse(finance["can_execute_balance_sheet"])
        self.assertTrue(
            any(row["key"] == "ncf.current_trial_balance" for row in finance["unresolved"])
        )

        logistics = domains["infrastructure_logistics"]
        logistics_known = {row["key"]: row for row in logistics["known"]}
        self.assertEqual(
            logistics_known["warborn_neverwinter.gauntlgrym_freight_distance_miles"]["value"],
            85,
        )
        self.assertEqual(
            logistics_known["warborn_neverwinter.gauntlgrym_freight_transit_days"]["value"],
            2,
        )
        self.assertTrue(
            any(row["key"] == "arterial.route_capacity" for row in logistics["unresolved"])
        )

        population = domains["population_labour"]
        self.assertIn("not additive", population["aggregation_rule"])
        self.assertTrue(
            any(row["key"] == "forgedeep.current_population" for row in population["unresolved"])
        )

        construction = domains["construction_capital"]
        construction_known = {row["key"]: row for row in construction["known"]}
        self.assertEqual(
            construction_known["forgedeep.city_development.monthly_cost_gp"]["value"],
            15000,
        )
        self.assertTrue(
            any(row["status"] == "MISSING_MECHANICS" for row in construction["unresolved"])
        )

        military = domains["military_contracts"]
        military_known = {row["key"]: row for row in military["known"]}
        self.assertEqual(
            military_known["warborn.contract.priority_legionnaire_units"]["value"],
            5000,
        )
        self.assertEqual(
            military_known["warborn.contract.solar_guard_units"]["value"],
            21,
        )
        self.assertTrue(
            any("headcount" in row["reason"] for row in military["unresolved"])
        )

    def test_openttd_source_candidate_maps_real_steel_but_refuses_unruled_unit_bridge(self):
        mapped = _map_openttd_source_candidate()
        self.assertEqual(mapped["status"], "MAPPED_BLOCKED")
        self.assertFalse(mapped["invoked"])
        self.assertEqual(mapped["source_flow"]["quantity_tons_per_month"], 1.5)
        self.assertEqual(mapped["source_flow"]["distance_miles"], 85)
        self.assertEqual(mapped["source_flow"]["transit_days"], 2)
        self.assertEqual(mapped["upstream_semantics"]["cargo_type"], 9)
        self.assertEqual(mapped["upstream_semantics"]["cargo_label"], "CT_STEEL")
        self.assertEqual(mapped["upstream_semantics"]["cargo_unit"], "tons")
        self.assertEqual(mapped["upstream_semantics"]["authority"], "UPSTREAM-ADOPTED")
        self.assertEqual(
            {row["authority"] for row in mapped["blockers"]},
            {"UNRESOLVED"},
        )
        joined = " ".join(row["reason"] for row in mapped["blockers"])
        self.assertIn("miles", joined)
        self.assertIn("1.5", joined)


if __name__ == "__main__":
    unittest.main()
