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
        self.assertEqual(
            result["physical_subsystems"]["status"],
            "DORMANT_UNTIL_SOURCE_BACKED",
        )
        self.assertIn("not invoked", result["physical_subsystems"]["reason"])

    def test_report_is_a_vara_style_review_surface(self):
        result = run_empire_business_turn(seed="report")
        report = render_empire_business_report(result)
        self.assertIn("Baen Empire Monthly Business Phase", report)
        self.assertIn("Sector revenue rolls", report)
        self.assertIn("Expense control", report)
        self.assertIn("Entity complications", report)
        self.assertIn("Vara briefing", report)
        self.assertIn("Notion writes: **0**", report)


if __name__ == "__main__":
    unittest.main()
