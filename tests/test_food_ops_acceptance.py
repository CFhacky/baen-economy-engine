from __future__ import annotations

import hashlib
import http.client
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from urllib.parse import quote


PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
sys.path.insert(0, str(SRC))

from baen_economy.food_ops_server import start_server  # noqa: E402
from baen_economy.operator_codec import canonical_hash  # noqa: E402


HASH_RE = re.compile(r"^[0-9a-f]{64}$")


class FoodOpsAcceptanceTests(unittest.TestCase):
    """Exercise the shipped app and all four planners over their real HTTP API."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="baen food acceptance ")
        self.store_path = Path(self.temporary.name) / "food-operations.sqlite3"
        self.source_hashes_before = {
            path.relative_to(PROJECT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((PROJECT / "fixtures").rglob("*.json"))
        }
        self.running = start_server(port=0, store_path=self.store_path)

    def tearDown(self) -> None:
        if self.running is not None:
            self.running.close()
        self.temporary.cleanup()

    def request(
        self,
        method: str,
        path: str,
        payload: object | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        body = None
        headers: dict[str, str] = {}
        if payload is not None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            headers = {
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            }
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.running.port, timeout=10
        )
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        response_body = response.read()
        response_headers = {
            key.lower(): value for key, value in response.getheaders()
        }
        status = response.status
        connection.close()
        return status, response_headers, response_body

    def json_request(
        self,
        method: str,
        path: str,
        payload: object | None = None,
    ) -> tuple[int, dict[str, str], dict[str, object]]:
        status, headers, body = self.request(method, path, payload)
        decoded = json.loads(body)
        self.assertIsInstance(decoded, dict)
        return status, headers, decoded

    def preview(self, endpoint: str, request: dict[str, object]) -> dict[str, object]:
        status, _, envelope = self.json_request("POST", endpoint, request)
        self.assertEqual(status, 200, envelope)
        self.assertTrue(envelope["ok"])
        result = envelope["data"]
        self.assertIsInstance(result, dict)
        return result

    def assert_embedded_content_hash(self, result: dict[str, object]) -> None:
        body = dict(result)
        digest = body.pop("content_hash")
        self.assertIsInstance(digest, str)
        self.assertRegex(digest, HASH_RE)
        self.assertEqual(digest, canonical_hash(body))

    def assert_zero_mutation_contract(self, value: object) -> None:
        """All advertised campaign/external mutation switches must remain inert."""

        false_keys = {
            "canonical",
            "notion_write_capability",
            "notion_write_authorized",
            "ledger_write_capability",
            "ledger_post_capability",
            "ledger_post_authorized",
            "canonical_write_capability",
            "campaign_time_advanced",
            "campaign_time_advance_capability",
            "advance_authorized",
            "agriculture_month_close_authorized",
            "actual_execution_eligible",
            "write_authorized",
            "posting_authorized",
            "postable",
        }
        zero_keys = {
            "notion_writes",
            "ledger_transactions",
            "ledger_postings",
            "canonical_ledger_postings",
            "campaign_state_rolls_resolved",
            "dice_rolled",
        }

        def visit(item: object, path: str) -> None:
            if isinstance(item, dict):
                for key, child in item.items():
                    child_path = f"{path}.{key}"
                    if key in false_keys:
                        self.assertIs(
                            child,
                            False,
                            f"mutation capability enabled at {child_path}",
                        )
                    if key in zero_keys:
                        self.assertEqual(
                            child,
                            0,
                            f"mutation count is nonzero at {child_path}",
                        )
                    visit(child, child_path)
            elif isinstance(item, list):
                for index, child in enumerate(item):
                    visit(child, f"{path}[{index}]")

        visit(value, "response")

    def assert_store_hashes(self, record: dict[str, object]) -> None:
        for name in ("request_hash", "result_hash", "bundle_hash"):
            self.assertRegex(record[name], HASH_RE)
        self.assertEqual(record["request_hash"], canonical_hash(record["request"]))
        self.assertEqual(record["result_hash"], canonical_hash(record["result"]))
        self.assertEqual(record["bundle_hash"], canonical_hash(record["manifest"]))
        manifest = record["manifest"]
        self.assertEqual(manifest["request_hash"], record["request_hash"])
        self.assertEqual(manifest["result_hash"], record["result_hash"])
        self.assertFalse(manifest["canonical"])
        self.assertFalse(manifest["notion_write_capability"])
        self.assertFalse(manifest["ledger_write_capability"])
        self.assertFalse(manifest["ledger_post_capability"])

    def restart(self) -> None:
        self.running.close()
        self.running = start_server(port=0, store_path=self.store_path)

    def test_real_operator_end_to_end_and_store_reopen(self) -> None:
        status, headers, app = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["content-type"])
        for visible_text in (
            b"Baen Food-Sector Operator",
            b"Plan Longsaddle",
            b"Plan Fish &amp; Crops",
            b"Preview Food Month",
            b"Saved local scenarios",
            b"Evidence register",
        ):
            self.assertIn(visible_text, app)
        for endpoint in (
            b"/api/longsaddle/preview",
            b"/api/food-sector/preview",
            b"/api/production/aquaculture/preview",
            b"/api/production/crop/preview",
            b"/api/scenarios",
        ):
            self.assertIn(endpoint, app)

        status, _, bootstrap_envelope = self.json_request("GET", "/api/bootstrap")
        self.assertEqual(status, 200)
        bootstrap = bootstrap_envelope["data"]
        totals = bootstrap["food_sector_baseline"]["totals"]
        self.assertEqual(
            totals,
            {
                "entity_count": 5,
                "staff": 63,
                "monthly_revenue_gp": "26500",
                "monthly_cost_gp": "20550",
                "monthly_net_gp": "5950",
                "capital_invested_gp": "111000",
            },
        )
        self.assertEqual(len(bootstrap["species"]), 15)
        self.assertEqual(len(bootstrap["crops"]), 12)
        self.assertEqual(len(bootstrap["production_catalog"]["species"]), 15)
        self.assertEqual(len(bootstrap["production_catalog"]["crops"]), 12)
        self.assertEqual(bootstrap["store"]["scenario_count"], 0)
        self.assert_zero_mutation_contract(bootstrap["safety"])

        status, _, health_envelope = self.json_request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assert_zero_mutation_contract(health_envelope["data"])

        longsaddle_request = {"profile": "illustrative-low-v1"}
        month_seed = "food-operator-http-acceptance-seed"
        month_request = {
            "month_label": "Hammer 1495 acceptance preview",
            "seed": month_seed,
        }
        aquaculture_request = {
            "scenario_id": "tilapia-known-answer",
            "species_id": "tilapia",
            "capacity": "30000",
            "capacity_basis": "cubic_meters",
            "planned_liveweight_output_lb": "25000",
            "opening_feed_lb": "50000",
            "feed_receipts_lb": "5000",
        }
        crop_request = {
            "scenario_id": "wheat-known-answer",
            "crop_id": "wheat",
            "baseline_yield_tons": "100",
            "baseline_fertilizer_tons": "80",
            "opening_food_tons": "20",
            "food_receipts_tons": "5",
            "planned_consumption_tons": "60",
        }

        longsaddle = self.preview("/api/longsaddle/preview", longsaddle_request)
        self.assertEqual(longsaddle["schema"], "tnp.food-security.longsaddle-plan/1")
        self.assertEqual(longsaddle["source_facts"]["population_mouths"], 11000)
        self.assertEqual(longsaddle["source_facts"]["grain_target_tons"], {"low": "1200", "high": "1500"})
        self.assertEqual(longsaddle["source_facts"]["grain_procured_tons"], "0")
        self.assertEqual(longsaddle["requested_tons"], "1200")
        self.assertEqual(longsaddle["dispatched_tons"], "900")
        self.assertEqual(longsaddle["capacity_gap_tons"], "300")
        self.assertEqual(longsaddle["delivered_tons"], "882.00")
        self.assertEqual(longsaddle["lost_tons"], "18.00")
        self.assertEqual(longsaddle["consumed_tons"], "300")
        self.assertEqual(longsaddle["closing_tons"], "582.00")
        self.assertEqual(longsaddle["conservation_residual_tons"], "0.00")

        month = self.preview("/api/food-sector/preview", month_request)
        self.assertEqual(month["schema"], "tnp.food-sector.month-preview/1")
        self.assertEqual(month["safety"]["preview_roll_receipts"], 4)
        receipts = []
        for sector_name in ("Agriculture", "Aquaculture"):
            sector = month["sectors"][sector_name]
            for check in ("revenue", "expense"):
                receipt = sector["rolls"][check]
                receipts.append(receipt)
                self.assertEqual(len(receipt["faces"]), 3)
                self.assertEqual(sum(receipt["faces"]), receipt["total"])
                self.assertEqual(
                    receipt["effective_target"] - receipt["total"],
                    receipt["margin"],
                )
            for entity in sector["entities"]:
                self.assertEqual(
                    entity["revenue_factor"], sector["rolls"]["revenue"]["factor"]
                )
                self.assertEqual(
                    entity["expense_factor"], sector["rolls"]["expense"]["factor"]
                )
        self.assertEqual(len(receipts), 4)
        self.assertEqual(
            month["dice_source"]["seed_fingerprint"],
            hashlib.sha256(month_seed.encode("utf-8")).hexdigest(),
        )
        self.assertNotIn(month_seed, json.dumps(month, sort_keys=True))

        aquaculture = self.preview(
            "/api/production/aquaculture/preview", aquaculture_request
        )
        self.assertEqual(
            aquaculture["schema"], "tnp.food-production.aquaculture-plan/1"
        )
        aqua_derived = aquaculture["derived"]
        self.assertEqual(aqua_derived["annual_yield_lb"]["low"], "300000")
        self.assertEqual(aqua_derived["annual_yield_lb"]["high"], "360000")
        self.assertEqual(aqua_derived["feed_required_lb"]["low"], "42500.0")
        self.assertEqual(aqua_derived["feed_available_lb"], "55000")
        self.assertEqual(aqua_derived["closing_feed_lb"]["low"], "12500.0")
        self.assertEqual(
            aqua_derived["conservation_residual_lb"],
            {"low": "0.0", "high": "0.0"},
        )

        crop = self.preview("/api/production/crop/preview", crop_request)
        self.assertEqual(crop["schema"], "tnp.food-production.crop-plan/1")
        crop_derived = crop["derived"]
        self.assertEqual(crop_derived["enhanced_yield_tons"]["low"], "130.00")
        self.assertEqual(crop_derived["enhanced_yield_tons"]["high"], "135.00")
        self.assertEqual(crop_derived["gross_food_available_tons"]["low"], "155.00")
        self.assertEqual(crop_derived["closing_food_tons"]["low"], "95.00")
        self.assertEqual(crop_derived["closing_food_tons"]["high"], "100.00")
        self.assertEqual(
            crop_derived["conservation_residual_tons"],
            {"low": "0.00", "high": "0.00"},
        )

        cases = (
            (
                "longsaddle-low-http",
                "longsaddle_plan",
                longsaddle_request,
                longsaddle,
            ),
            ("food-month-http", "food_sector_month", month_request, month),
            (
                "tilapia-feed-http",
                "aquaculture_plan",
                aquaculture_request,
                aquaculture,
            ),
            ("wheat-food-http", "crop_plan", crop_request, crop),
        )
        stored: dict[str, dict[str, object]] = {}
        exported_hashes: dict[str, str] = {}
        for scenario_id, kind, request, result in cases:
            with self.subTest(action="save-load-export", scenario=scenario_id):
                self.assert_embedded_content_hash(result)
                self.assert_zero_mutation_contract(result)
                status, _, save_envelope = self.json_request(
                    "POST",
                    "/api/scenarios",
                    {
                        "scenario_id": scenario_id,
                        "kind": kind,
                        "request": request,
                        "result": result,
                    },
                )
                self.assertEqual(status, 201, save_envelope)
                self.assertFalse(save_envelope["data"]["replayed_existing_save"])
                record = save_envelope["data"]["scenario"]
                self.assertEqual(record["scenario_id"], scenario_id)
                self.assertEqual(record["kind"], kind)
                self.assertEqual(record["result"], result)
                self.assert_store_hashes(record)
                self.assert_zero_mutation_contract(record)
                stored[scenario_id] = record

                escaped_id = quote(scenario_id, safe="")
                status, _, load_envelope = self.json_request(
                    "GET", f"/api/scenarios/{escaped_id}"
                )
                self.assertEqual(status, 200)
                self.assertEqual(load_envelope["data"], record)

                status, export_headers, html = self.request(
                    "GET", f"/api/scenarios/{escaped_id}/export/html"
                )
                self.assertEqual(status, 200)
                self.assertIn("text/html", export_headers["content-type"])
                self.assertIn("attachment", export_headers["content-disposition"])
                self.assertIn(b"<!doctype html>", html)
                self.assertIn(scenario_id.encode("utf-8"), html)
                self.assertIn(kind.encode("utf-8"), html)
                self.assertIn(record["bundle_hash"].encode("ascii"), html)
                for heading in (b"Source", b"Assumption", b"Derived", b"Unknown"):
                    self.assertIn(heading, html)
                self.assertIn(b"No Notion or ledger write capability", html)
                exported_hashes[scenario_id] = hashlib.sha256(html).hexdigest()

        month_record = stored["food-month-http"]
        self.assertNotIn(month_seed, json.dumps(month_record, sort_keys=True))
        self.assertEqual(
            month_record["request"]["seed_fingerprint"],
            hashlib.sha256(month_seed.encode("utf-8")).hexdigest(),
        )
        self.assertFalse(month_record["request"]["raw_seed_persisted"])

        status, _, list_envelope = self.json_request("GET", "/api/scenarios")
        self.assertEqual(status, 200)
        self.assertEqual(list_envelope["data"]["count"], 4)
        self.assertEqual(
            {item["kind"] for item in list_envelope["data"]["scenarios"]},
            {
                "longsaddle_plan",
                "food_sector_month",
                "aquaculture_plan",
                "crop_plan",
            },
        )

        self.restart()
        status, _, reopened_envelope = self.json_request("GET", "/api/bootstrap")
        self.assertEqual(status, 200)
        reopened_store = reopened_envelope["data"]["store"]
        self.assertEqual(reopened_store["status"], "ok")
        self.assertEqual(reopened_store["scenario_count"], 4)
        self.assertEqual(reopened_store["food_sector_month_count"], 1)
        self.assertEqual(reopened_store["longsaddle_plan_count"], 1)
        self.assertEqual(reopened_store["aquaculture_plan_count"], 1)
        self.assertEqual(reopened_store["crop_plan_count"], 1)
        self.assertEqual(
            reopened_store["bundle_hashes"],
            [record["bundle_hash"] for record in stored.values()],
        )
        self.assert_zero_mutation_contract(reopened_store)

        for scenario_id, record in stored.items():
            with self.subTest(action="reopen", scenario=scenario_id):
                escaped_id = quote(scenario_id, safe="")
                status, _, load_envelope = self.json_request(
                    "GET", f"/api/scenarios/{escaped_id}"
                )
                self.assertEqual(status, 200)
                self.assertEqual(load_envelope["data"], record)
                self.assert_store_hashes(load_envelope["data"])
                status, _, html = self.request(
                    "GET", f"/api/scenarios/{escaped_id}/export/html"
                )
                self.assertEqual(status, 200)
                self.assertEqual(hashlib.sha256(html).hexdigest(), exported_hashes[scenario_id])

        source_hashes_after = {
            path.relative_to(PROJECT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted((PROJECT / "fixtures").rglob("*.json"))
        }
        self.assertEqual(source_hashes_after, self.source_hashes_before)


if __name__ == "__main__":
    unittest.main()
