from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
sys.path.insert(0, str(SRC))

from baen_economy.food_baseline import (  # noqa: E402
    DEFAULT_EXTRACTION_PATH,
    DEFAULT_PAGE_SNAPSHOT_PATH,
    FoodBaselineError,
    load_food_source_baseline,
)
from baen_economy.food_cli import main as food_main  # noqa: E402
from baen_economy.food_report import render_food_baseline_html  # noqa: E402
from baen_economy.regional_cli import main as regional_main  # noqa: E402


class FoodBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = load_food_source_baseline()

    def by_name(self, name: str) -> dict[str, object]:
        return next(item for item in self.payload["entities"] if item["name"] == name)

    def test_complete_source_coverage_and_exact_financial_envelope(self) -> None:
        self.assertEqual(
            self.payload["coverage"],
            {
                "registry_property_rows": 90,
                "registry_property_rows_total": 90,
                "registry_page_bodies": 90,
                "registry_page_bodies_total": 90,
                "food_rows": 7,
                "food_rows_total": 7,
                "commercial_baseline_rows": 5,
                "mechanically_executed_rows": 0,
            },
        )
        self.assertEqual(
            self.payload["commercial_food_baseline"],
            {
                "as_of": "Eleint 20, 1494",
                "status": "last_known_pre_crisis_baseline_not_current_k1495_books",
                "entity_count": 5,
                "employees": 63,
                "monthly_revenue_gp": "26500",
                "monthly_cost_gp": "20550",
                "monthly_net_gp": "5950",
                "capital_invested_gp": "111000",
                "opening_cash_gp": None,
            },
        )

    def test_shelters_are_produce_and_tomatoes_not_invented_grain(self) -> None:
        shelters = self.by_name("Agricultural Shelter Zones")
        self.assertEqual(
            shelters["known_outputs"],
            ["greenhouse produce", "tomatoes, including year-round tomatoes"],
        )
        self.assertIn("grain production", shelters["physical_unknowns"])
        self.assertIn("feed production", shelters["physical_unknowns"])
        self.assertFalse(shelters["mechanically_executable"])
        self.assertTrue(all(value is None for value in shelters["physical_state"].values()))
        self.assertEqual(
            shelters["reported_finance"]["monthly_revenue_gp"], "1500"
        )
        self.assertEqual(shelters["reported_finance"]["monthly_cost_gp"], "1050")
        self.assertIsNone(shelters["reported_finance"]["opening_cash_gp"])

    def test_all_seven_rows_keep_ownership_and_unknowns_distinct(self) -> None:
        self.assertEqual(len(self.payload["entities"]), 7)
        orchard = self.by_name("Orchard Chapel")
        lobster = self.by_name("Lobster King Operations (Baen-Allied)")
        self.assertEqual(orchard["classification"], "patronage_community_asset")
        self.assertEqual(orchard["financial_inclusion"], "excluded_unknown_finance")
        self.assertEqual(lobster["classification"], "unconfirmed_allied_entity")
        self.assertEqual(lobster["financial_inclusion"], "excluded_unconfirmed")
        self.assertIsNone(orchard["reported_finance"]["monthly_revenue_gp"])
        self.assertEqual(lobster["reported_finance"]["monthly_revenue_gp"], "0")

    def test_later_crisis_is_context_not_a_silent_scaled_baseline(self) -> None:
        crisis = self.payload["later_k1495_crisis_context"]
        self.assertEqual(crisis["shelter_zones_destroyed"], 3)
        self.assertEqual(crisis["shelter_zones_total"], 8)
        self.assertEqual(crisis["remaining_not_reported_destroyed"], 5)
        self.assertFalse(crisis["remaining_operational_inference_allowed"])
        self.assertEqual(crisis["longsaddle_food_position"], "net_importer")
        self.assertEqual(crisis["resolved_execution_roll_count"], 0)
        self.assertEqual(crisis["resolved_transaction_count"], 0)

    def test_safety_boundary_is_literal(self) -> None:
        self.assertFalse(self.payload["simulation_ready"])
        self.assertTrue(self.payload["observed_baseline_ready"])
        self.assertEqual(
            self.payload["safety"],
            {
                "notion_write_capability": False,
                "notion_writes": 0,
                "canonical_ledger_post_capability": False,
                "canonical_ledger_postings": 0,
                "dice_rolled": 0,
                "campaign_time_advanced": False,
            },
        )

    def test_page_body_tamper_breaks_source_verification(self) -> None:
        payload = json.loads(DEFAULT_PAGE_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        payload["pages"][0]["source_text"] += "\ntampered"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "pages.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(FoodBaselineError, "snapshot hash"):
                load_food_source_baseline(page_snapshot_path=path)

    def test_unreviewed_extraction_field_fails_closed(self) -> None:
        extraction = json.loads(DEFAULT_EXTRACTION_PATH.read_text(encoding="utf-8"))
        extraction["entities"][0]["invented_monthly_tons"] = "999"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "extraction.json"
            path.write_text(json.dumps(extraction), encoding="utf-8")
            with self.assertRaisesRegex(FoodBaselineError, "keys do not match"):
                load_food_source_baseline(extraction_path=path)

    def test_html_is_readable_and_does_not_claim_a_simulated_month(self) -> None:
        html = render_food_baseline_html(self.payload)
        self.assertIn("Your data is present.", html)
        self.assertIn("All 90 Registry rows", html)
        self.assertIn("tomato greenhouses", html)
        self.assertIn("names wheat, barley, rye, fifteen aquaculture species", html)
        self.assertIn("assigning grain or feed production", html)
        self.assertIn("shelter zones themselves", html)
        self.assertIn("Physical execution: BLOCKED", html)
        self.assertNotIn("<script", html.lower())

    def test_cli_writes_a_readable_report(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "food.html"
            self.assertEqual(food_main(["report", str(output)]), 0)
            self.assertTrue(output.is_file())
            self.assertIn("Baen Food Economy", output.read_text(encoding="utf-8"))

    def test_regional_synthetic_demo_is_disabled_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / "regional.sqlite3"
            code = regional_main(["init", str(database), "--seed", "test"])
            self.assertEqual(code, 2)
            self.assertFalse(database.exists())


if __name__ == "__main__":
    unittest.main()
