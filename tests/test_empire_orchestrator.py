from __future__ import annotations

import os
from pathlib import Path
import unittest
from unittest.mock import patch

from baen_economy.empire_orchestrator import (
    DEFAULT_CENSUS,
    DEFAULT_SCENARIO,
    rebase_scenario,
    render_empire_month,
    run_empire_month,
    _brunnfeld_check,
    _openttd_check,
    _load_json,
)
from baen_economy import whole_economy


class EmpireOrchestratorTests(unittest.TestCase):
    def test_rebase_uses_live_population_without_hiding_missing_population(self):
        census = _load_json(DEFAULT_CENSUS)
        scenario = whole_economy.load_scenario(DEFAULT_SCENARIO)
        rebased, overrides, blockers = rebase_scenario(scenario, census)
        by_name = {row["name"]: row for row in rebased["settlements"]}
        self.assertEqual(str(by_name["Neverwinter"]["population_total"]), "75000")
        self.assertEqual(str(by_name["Waterdeep"]["population_total"]), "130000")
        self.assertEqual(str(by_name["Forgedeep"]["population_total"]), "8000")
        self.assertTrue(any(row["settlement"] == "Neverwinter" for row in overrides))
        self.assertTrue(any(row["settlement"] == "Forgedeep" for row in blockers))
        self.assertEqual(
            sum(int(row["population"]) for row in by_name["Neverwinter"]["classes"]),
            75000,
        )

    def test_actual_whole_economy_core_runs_from_rebased_source_state(self):
        env = {
            "UNKNOWN_HORIZONS_CHECKOUT": "",
            "FREECOL_CHECKOUT": "",
            "VELOREN_CHECKOUT": "",
            "BRUNNFELD_URL": "",
            "OPENTTD_ADMIN_HOST": "",
            "OPENTTD_ADMIN_PORT": "",
            "OPENTTD_ADMIN_PASSWORD": "",
        }
        with patch.dict(os.environ, env, clear=False):
            payload = run_empire_month(seed="empire-e2e-core")
        self.assertFalse(payload["canonical"])
        self.assertFalse(payload["campaign_time_advanced"])
        self.assertEqual(payload["notion_writes"], 0)
        self.assertEqual(payload["canonical_ledger_postings"], 0)
        self.assertGreater(len(payload["baen_core"]["production"]), 0)
        self.assertGreater(len(payload["baen_core"]["events"]), 0)
        self.assertTrue(payload["integrity"]["physical_conservation"])
        self.assertTrue(payload["integrity"]["ledger_balanced"])
        self.assertIn("Whole-Economy", render_empire_month(payload))

    def test_require_products_fails_instead_of_pretending_product_execution(self):
        env = {
            "UNKNOWN_HORIZONS_CHECKOUT": "",
            "FREECOL_CHECKOUT": "",
            "VELOREN_CHECKOUT": "",
            "BRUNNFELD_URL": "",
            "OPENTTD_ADMIN_HOST": "",
            "OPENTTD_ADMIN_PORT": "",
            "OPENTTD_ADMIN_PASSWORD": "",
        }
        with patch.dict(os.environ, env, clear=False):
            with self.assertRaises(Exception):
                run_empire_month(seed="must-have-products", require_products=True)

    @patch("baen_economy.empire_orchestrator.BrunnfeldServiceClient")
    def test_brunnfeld_mapping_is_used_after_world_generation(self, client_type):
        scenario = whole_economy.load_scenario(DEFAULT_SCENARIO)
        census = _load_json(DEFAULT_CENSUS)
        rebased, _, _ = rebase_scenario(scenario, census)
        client = client_type.return_value
        client.generate_world.return_value = {"ok": True, "villages": 3, "totalAgents": 213}
        snapshot = type("Snapshot", (), {})()
        snapshot.upstream_commit = "brunnfeld-pin"
        snapshot.villages = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        snapshot.economy = []
        snapshot.marketplace = {"orders": []}
        snapshot.prices = {}
        client.snapshot.return_value = snapshot
        result = _brunnfeld_check(rebased, "http://127.0.0.1:3333", "seed")
        self.assertEqual(result["status"], "USED_IN_RUN")
        self.assertEqual(result["mapping"]["brunnfeld_villages"], 3)
        self.assertGreaterEqual(result["mapping"]["total_sample_agents"], 21)

    @patch("baen_economy.empire_orchestrator.OpenTTDAdminClient")
    def test_openttd_requires_an_actually_evaluated_route(self, client_type):
        scenario = whole_economy.load_scenario(DEFAULT_SCENARIO)
        client = client_type.return_value.__enter__.return_value
        snapshot = type("Snapshot", (), {})()
        snapshot.upstream_commit = "openttd-pin"
        snapshot.current_date = 1
        snapshot.companies = ()
        client.snapshot.return_value = snapshot
        client.transport_income.return_value = 123
        core = {
            "route_usage": [
                {"route_id": "route:nw-to-wd-road", "dispatched_quantity": "25"}
            ]
        }
        result = _openttd_check(scenario, core, "127.0.0.1", 3977, "secret")
        self.assertEqual(result["status"], "USED_IN_RUN")
        self.assertGreater(result["routes_evaluated"], 0)
        self.assertEqual(result["details"][0]["evaluations"][0]["income_game_currency"], 123)

        empty = _openttd_check(
            scenario, {"route_usage": []}, "127.0.0.1", 3977, "secret"
        )
        self.assertEqual(empty["status"], "MISSING_MAPPING")

if __name__ == "__main__":
    unittest.main()
