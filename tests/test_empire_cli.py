from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from baen_economy.empire_cli import census_status, empire_preview, product_status, render_report


class EmpireCliTests(unittest.TestCase):
    def census(self):
        return {
            "meta": {
                "campaignBoundary": "Day 7 Hammer 1495 DR",
                "materializedCore": 1620,
                "storedRecords": 1627,
                "simulated": 0,
                "coverageCore": {"UNKNOWN": 1616},
                "nextBatch": ["population_labour"],
            },
            "collections": [
                {"key": "business_registry", "rowCount": 90, "captured": 90, "complete": True},
                {"key": "npcs", "rowCount": 681, "captured": 920, "complete": True},
            ],
        }

    def write_census(self, root: Path) -> Path:
        path = root / "census.json"
        path.write_text(json.dumps(self.census()), encoding="utf-8")
        return path

    def test_status_distinguishes_current_live_from_retained(self):
        with tempfile.TemporaryDirectory() as temp:
            status = census_status(self.write_census(Path(temp)))
        self.assertEqual(status["current_live_records"], 771)
        self.assertEqual(status["retained_core_records"], 1620)
        self.assertEqual(status["stored_records"], 1627)
        self.assertEqual(status["canonical_month"], "BLOCKED")
        self.assertFalse(status["campaign_time_advanced"])

    @patch("baen_economy.empire_cli.run_registry_preview")
    def test_preview_gives_one_empire_report_without_claiming_canon(self, run_registry):
        run_registry.return_value = {
            "rows": [
                {
                    "entity": {"name": "A", "sector": "Trade", "status": "Operational"},
                    "financials": {
                        "proposed_revenue": "100",
                        "proposed_cost": "40",
                        "proposed_net": "60",
                    },
                },
                {
                    "entity": {"name": "B", "sector": "Military", "status": "Operational"},
                    "financials": {
                        "proposed_revenue": "25",
                        "proposed_cost": "75",
                        "proposed_net": "-50",
                    },
                },
            ],
            "skipped": [{"title": "C", "reason": "not eligible"}],
        }
        with tempfile.TemporaryDirectory() as temp:
            payload = empire_preview(
                seed="s",
                month="Hammer 1495 preview",
                census_path=self.write_census(Path(temp)),
            )
        self.assertFalse(payload["canonical"])
        self.assertEqual(payload["business_preview"]["resolved_businesses"], 2)
        self.assertEqual(payload["business_preview"]["skipped_businesses"], 1)
        self.assertEqual(payload["business_preview"]["proposed_revenue_gp"], "125")
        self.assertEqual(payload["business_preview"]["proposed_cost_gp"], "115")
        self.assertEqual(payload["business_preview"]["proposed_net_gp"], "10")
        self.assertFalse(payload["campaign_time_advanced"])
        self.assertEqual(payload["notion_writes"], 0)
        report = render_report(payload)
        self.assertIn("Baen Empire Economy", report)
        self.assertIn("not canon", report.lower())
        self.assertIn("source-to-product semantic mapping", report)

    def test_products_are_explicit_about_mapping_gap(self):
        payload = product_status()
        self.assertEqual(len(payload["products"]), 6)
        self.assertTrue(all("semantic mapping incomplete" in row["status"] for row in payload["products"]))

    def test_actual_repository_empire_preview_resolves_real_registry(self):
        payload = empire_preview(
            seed="empire-operator-ci",
            month="Hammer 1495 preview",
        )
        self.assertEqual(payload["source_state"]["current_live_records"], 1381)
        self.assertEqual(payload["source_state"]["retained_core_records"], 1620)
        self.assertEqual(payload["source_state"]["stored_records"], 1627)
        self.assertGreater(payload["business_preview"]["resolved_businesses"], 0)
        self.assertEqual(payload["notion_writes"], 0)
        self.assertFalse(payload["campaign_time_advanced"])
        self.assertFalse(payload["canonical"])
        self.assertIn("Baen Empire Economy", render_report(payload))


if __name__ == "__main__":
    unittest.main()
