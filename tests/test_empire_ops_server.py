from __future__ import annotations

import http.client
import json
import tempfile
import unittest
from pathlib import Path

from baen_economy.empire_ops_server import create_server, start_server


class EmpireOpsServerTests(unittest.TestCase):
    def request(self, running, method: str, path: str, payload: object | None = None, headers=None):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request_headers = dict(headers or {})
        if body is not None:
            request_headers["Content-Type"] = "application/json"
            request_headers["Content-Length"] = str(len(body))
        connection = http.client.HTTPConnection("127.0.0.1", running.port, timeout=30)
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        raw = response.read()
        result_headers = {key.lower(): value for key, value in response.getheaders()}
        connection.close()
        return response.status, result_headers, raw

    def test_loopback_only(self):
        with self.assertRaises(ValueError):
            create_server(host="0.0.0.0")

    def test_codespaces_host_is_allowed_only_inside_codespaces(self):
        import os
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "empire.sqlite"
            with patch.dict(
                os.environ,
                {
                    "CODESPACES": "true",
                    "GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN": "app.github.dev",
                },
                clear=False,
            ):
                server = create_server(
                    host="0.0.0.0",
                    port=0,
                    store_path=database,
                )
                server.server_close()

        with self.assertRaises(ValueError):
            create_server(host="0.0.0.0")

    def test_app_and_bootstrap_expose_real_source_state(self):
        with tempfile.TemporaryDirectory() as directory, start_server(port=0, store_path=Path(directory) / "empire.sqlite") as running:
            status, headers, raw = self.request(running, "GET", "/")
            self.assertEqual(status, 200)
            self.assertIn("text/html", headers["content-type"])
            self.assertIn(b"Baen Economy Engine", raw)
            self.assertIn(b"Run current Hammer 1495", raw)
            self.assertIn(b"Businesses", raw)
            self.assertIn(b"Saved runs", raw)
            self.assertIn(b"Advanced preview options", raw)

            status, _, raw = self.request(running, "GET", "/api/bootstrap")
            self.assertEqual(status, 200, raw.decode("utf-8", errors="replace"))
            data = json.loads(raw)["data"]
            self.assertEqual(data["source_status"]["current_live_records"], 1381)
            self.assertEqual(data["source_status"]["retained_core_records"], 1620)
            self.assertEqual(data["source_status"]["simulated_records"], 0)
            self.assertEqual(data["source_status"]["canonical_month"], "BLOCKED")
            self.assertGreaterEqual(data["semantic_coverage"]["mapped_record_count"], 10)
            self.assertEqual(data["semantic_coverage"]["simulated_after_overlay"], 0)
            self.assertEqual(
                set(data["semantic_domains"]),
                {
                    "finance_banking",
                    "infrastructure_logistics",
                    "population_labour",
                    "construction_capital",
                    "military_contracts",
                },
            )
            self.assertEqual(len(data["products"]["products"]), 6)
            self.assertFalse(data["safety"]["notion_write_capability"])
            self.assertFalse(data["safety"]["canonical_ledger_post_capability"])

    def test_preview_runs_controlling_empire_business_path(self):
        raw_seed = "app-integration-seed-must-not-persist"
        with tempfile.TemporaryDirectory() as directory, start_server(port=0, store_path=Path(directory) / "empire.sqlite") as running:
            status, _, raw = self.request(
                running,
                "POST",
                "/api/preview",
                {
                    "seed": raw_seed,
                    "month_label": "Day 7 Hammer 1495 DR — app test",
                    "market_condition": "unknown",
                    "vara_active": False,
                },
            )
            self.assertEqual(status, 200, raw.decode("utf-8", errors="replace"))
            payload = json.loads(raw)["data"]
            result = payload["result"]
            self.assertEqual(result["schema"], "tnp.economy.empire-business-turn/1")
            self.assertEqual(result["admission"]["admitted_entities"], 37)
            self.assertEqual(result["admission"]["baseline_revenue_gp"], "299266")
            self.assertEqual(result["notion_writes"], 0)
            self.assertEqual(result["canonical_ledger_postings"], 0)
            self.assertFalse(result["campaign_time_advanced"])
            self.assertIn("Baen Empire Monthly Business Phase", payload["report"])
            self.assertFalse(payload["safety"]["raw_seed_persisted"])
            self.assertNotIn(raw_seed, raw.decode("utf-8", errors="replace"))

    def test_save_reopen_compare_and_export_through_http(self):
        raw_seed = "http-save-seed-not-persisted"
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "empire.sqlite"
            request = {
                "seed": raw_seed,
                "month_label": "Day 7 Hammer 1495 DR — saved app test",
                "market_condition": "unknown",
                "vara_active": False,
            }
            with start_server(port=0, store_path=database) as running:
                for run_id, seed in (("app-a", raw_seed), ("app-b", "second-http-seed")):
                    payload = dict(request, seed=seed)
                    status, _, raw = self.request(
                        running,
                        "POST",
                        "/api/runs",
                        {"run_id": run_id, "label": run_id, "request": payload},
                    )
                    self.assertEqual(status, 201, raw.decode("utf-8", errors="replace"))
                self.assertNotIn(raw_seed.encode(), database.read_bytes())
                status, _, raw = self.request(running, "GET", "/api/runs")
                self.assertEqual(status, 200)
                self.assertEqual(len(json.loads(raw)["data"]["runs"]), 2)
                status, _, raw = self.request(
                    running, "GET", "/api/compare?left=app-a&right=app-b"
                )
                self.assertEqual(status, 200)
                self.assertEqual(
                    json.loads(raw)["data"]["schema"],
                    "tnp.economy.empire-ops-comparison/1",
                )
                status, headers, raw = self.request(
                    running, "GET", "/api/runs/app-a/export?format=html"
                )
                self.assertEqual(status, 200)
                self.assertIn("text/html", headers["content-type"])
                self.assertIn(b"Baen Empire Monthly Business Phase", raw)

            with start_server(port=0, store_path=database) as reopened:
                status, _, raw = self.request(reopened, "GET", "/api/runs/app-a")
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(raw)["data"]["run_id"], "app-a")

    def test_invalid_preview_and_unsafe_routes_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory, start_server(port=0, store_path=Path(directory) / "empire.sqlite") as running:
            status, _, raw = self.request(
                running,
                "POST",
                "/api/preview",
                {"seed": "", "market_condition": "unknown", "vara_active": False},
            )
            self.assertEqual(status, 400)
            self.assertEqual(json.loads(raw)["error"]["code"], "invalid_request")

            for path in ("/api/notion/write", "/api/ledger/post", "/api/canonical"):
                status, _, raw = self.request(running, "POST", path, {})
                self.assertEqual(status, 404)
                self.assertFalse(json.loads(raw)["ok"])

            status, _, raw = self.request(
                running,
                "GET",
                "/api/health",
                headers={"Host": "attacker.invalid"},
            )
            self.assertEqual(status, 403)
            self.assertEqual(json.loads(raw)["error"]["code"], "invalid_host")


if __name__ == "__main__":
    unittest.main()
