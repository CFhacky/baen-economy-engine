from __future__ import annotations

import http.client
import json
import unittest

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

    def test_app_and_bootstrap_expose_real_source_state(self):
        with start_server(port=0) as running:
            status, headers, raw = self.request(running, "GET", "/")
            self.assertEqual(status, 200)
            self.assertIn("text/html", headers["content-type"])
            self.assertIn(b"Baen Economy Engine", raw)
            self.assertIn(b"Source", raw)

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
        with start_server(port=0) as running:
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

    def test_invalid_preview_and_unsafe_routes_fail_closed(self):
        with start_server(port=0) as running:
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
