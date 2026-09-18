from __future__ import annotations

import unittest

from baen_economy.empire_operations import (
    ACTIVE_SECTORS,
    DEFAULT_ADMISSION,
    DEFAULT_MECHANICS,
    DEFAULT_REGISTRY,
    render_empire_business_report,
    run_empire_business_turn,
)


class EmpireOperationsTests(unittest.TestCase):
    def test_source_grounded_registry_slice_is_complete_and_reconciled(self):
        result = run_empire_business_turn(seed="source-grounded-acceptance")
        self.assertEqual(result["admission"]["admitted_entities"], 37)
        self.assertEqual(result["admission"]["excluded_entities"], 53)
        self.assertEqual(result["admission"]["admitted_employees"], 1084)
        self.assertEqual(result["admission"]["baseline_revenue_gp"], "299266")
        self.assertTrue(
            result["admission"]["financial_crosscheck"]["within_current_revenue_range"]
        )
        self.assertEqual(
            [row["sector"] for row in result["sector_results"]],
            list(ACTIVE_SECTORS),
        )

    def test_actual_turn_is_deterministic_and_source_bound(self):
        first = run_empire_business_turn(seed="replay-me")
        second = run_empire_business_turn(seed="replay-me")
        changed = run_empire_business_turn(seed="different-seed")
        self.assertEqual(first, second)
        self.assertNotEqual(first["result_hash"], changed["result_hash"])
        self.assertEqual(first["notion_writes"], 0)
        self.assertEqual(first["canonical_ledger_postings"], 0)
        self.assertFalse(first["campaign_time_advanced"])
        self.assertFalse(first["canonical"])

    def test_no_exact_cash_or_fake_consolidated_cost_is_asserted(self):
        result = run_empire_business_turn(seed="ranges-not-fakes")
        expense = result["expense_control"]
        self.assertEqual(expense["baseline_expense_range_gp"], ["209266", "224266"])
        self.assertIsInstance(result["proposed_net_range_gp"], list)
        self.assertEqual(len(result["proposed_net_range_gp"]), 2)
        self.assertIn(
            "Northern Crown Financial current consolidated monthly cost",
            result["unresolved"],
        )
        self.assertIn(
            "Silversheen Hammer-1495 current monthly cost",
            result["unresolved"],
        )

    def test_ncf_and_silversheen_current_authority_do_not_double_count(self):
        result = run_empire_business_turn(seed="accounting-admission")
        banking = next(row for row in result["sector_results"] if row["sector"] == "Banking")
        manufacturing = next(
            row for row in result["sector_results"] if row["sector"] == "Manufacturing"
        )
        self.assertEqual(banking["entity_count"], 1)
        self.assertEqual(banking["baseline_revenue_gp"], "22000")
        self.assertEqual(manufacturing["entity_count"], 5)
        self.assertEqual(manufacturing["baseline_revenue_gp"], "116017")

    def test_entity_phase_selects_three_to_five_and_never_invents_neglect(self):
        result = run_empire_business_turn(seed="entity-phase")
        rows = result["entity_complications"]
        self.assertGreaterEqual(len(rows), 3)
        self.assertLessEqual(len(rows), 5)
        for row in rows:
            self.assertGreaterEqual(row["raw_d20"], 1)
            self.assertLessEqual(row["raw_d20"], 20)
            if not row["neglect_status"]:
                self.assertIsNone(row["final_outcome"])
                self.assertIsNone(row["adjusted_d20"])

    def test_market_and_vara_modifiers_require_explicit_preview_inputs(self):
        baseline = run_empire_business_turn(seed="modifiers")
        explicit = run_empire_business_turn(
            seed="modifiers",
            market_condition="boom",
            vara_active=True,
        )
        for row in baseline["sector_results"]:
            labels = [modifier["label"] for modifier in row["modifiers"]]
            self.assertFalse(any("market condition" in label for label in labels))
            self.assertNotIn("Vara active", labels)
        for row in explicit["sector_results"]:
            labels = [modifier["label"] for modifier in row["modifiers"]]
            self.assertIn("market condition: boom", labels)
            self.assertIn("Vara active", labels)

    def test_physical_products_are_components_not_fake_data_sources(self):
        result = run_empire_business_turn(seed="product-boundary")
        physical = result["physical_subsystems"]
        self.assertEqual(physical["status"], "PARTIAL_SOURCE_BACKED")
        self.assertFalse(
            any(row["recipe_invented"] for row in physical["production_lines"])
        )
        ids = [row["id"] for row in physical["production_lines"]]
        self.assertEqual(
            ids,
            [
                "treasury_quarries",
                "azurite_quarries",
                "western_limestone",
                "western_sandstone",
                "brickworks",
                "clay_quarries",
                "silversheen_aluminum",
                "star_metal_hills_bauxite",
                "warborn_neverwinter",
            ],
        )
        warborn = next(row for row in physical["production_lines"] if row["id"] == "warborn_neverwinter")
        self.assertEqual(warborn["quantity"], 12)
        self.assertEqual(warborn["maximum"], 15)
        brick = next(row for row in physical["production_lines"] if row["id"] == "brickworks")
        self.assertEqual(brick["quantity"], 75000)
        self.assertTrue(any("clay-to-brick" in item for item in brick["unresolved_inputs"]))
        silversheen = next(
            row for row in physical["production_lines"] if row["id"] == "silversheen_aluminum"
        )
        self.assertEqual(silversheen["quantity"], 180)
        products = physical["products"]
        self.assertIn(products["mesa"]["status"], {"USED_IN_RUN", "UNAVAILABLE"})
        self.assertIn(products["freecol"]["status"], {"USED_IN_RUN", "UNAVAILABLE"})
        self.assertIn(products["unknown_horizons"]["status"], {"USED_IN_RUN", "UNAVAILABLE"})
        self.assertEqual(products["openttd"]["status"], "MAPPED_BLOCKED")
        self.assertEqual(products["veloren"]["status"], "NOT_INVOKED")
        self.assertEqual(products["brunnfeld"]["status"], "NOT_INVOKED")
        self.assertIn(
            "unit bridge",
            products["openttd"]["reason"],
        )
        mesa = products["mesa"]
        event_ids = mesa.get("executed_event_ids") or mesa.get("intended_event_ids") or []
        self.assertTrue(any(item.startswith("sector:") for item in event_ids))
        self.assertIn("expense-control", event_ids)
        self.assertFalse(any("shock" in item or "migration" in item for item in event_ids))
        self.assertIn(
            "Silversheen Warborn aluminum allocation",
            " ".join(result["unresolved"]),
        )
        known = physical["known_state"]
        census = {row["id"]: row for row in known["census"]}
        self.assertEqual(census["neverwinter"]["population"], 75000)
        self.assertEqual(census["waterdeep"]["population"], 130000)
        self.assertIsNone(census["forgedeep"]["population"])
        self.assertEqual(known["labor"]["admitted_commercial_employees"], 1084)
        self.assertEqual(len(known["arterial_routes"]), 5)
        self.assertTrue(
            all(row["physical_output"] is None for row in known["food_financials"])
        )
        domains = physical["semantic_domains"]
        self.assertEqual(domains["finance_banking"]["status"], "PARTIAL_CONFLICT")
        self.assertEqual(
            domains["infrastructure_logistics"]["status"],
            "PARTIAL_SOURCE_BACKED",
        )
        self.assertEqual(domains["population_labour"]["status"], "PARTIAL_SOURCE_BACKED")
        self.assertEqual(domains["construction_capital"]["status"], "PARTIAL_SOURCE_BACKED")
        self.assertEqual(domains["military_contracts"]["status"], "PARTIAL_SOURCE_BACKED")

    def test_report_is_a_vara_style_review_surface(self):
        result = run_empire_business_turn(seed="report")
        report = render_empire_business_report(result)
        self.assertIn("Baen Empire Monthly Business Phase", report)
        self.assertIn("Sector revenue rolls", report)
        self.assertIn("Expense control", report)
        self.assertIn("Entity complications", report)
        self.assertIn("Vara briefing", report)
        self.assertIn("Notion writes: **0**", report)
        self.assertIn("Source-backed production lines", report)
        self.assertIn("Baen Brickworks", report)
        self.assertIn("Warborn Production - Neverwinter", report)
        self.assertIn("Source-backed census", report)
        self.assertIn("Food financials (no physical volumes)", report)
        self.assertIn("Arterial route register", report)
        self.assertIn("Entity labor snapshot", report)
        self.assertIn("Source → product semantic domains", report)
        self.assertIn("Finance / Banking", report)
        self.assertIn("ncf.active_loans_gp", report)
        self.assertIn("warborn.contract.priority_legionnaire_units", report)
        self.assertIn("Forgedeep", report)


if __name__ == "__main__":
    unittest.main()
