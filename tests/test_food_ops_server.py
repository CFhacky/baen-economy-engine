from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
import hashlib
import http.client
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock


PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
sys.path.insert(0, str(SRC))

from baen_economy.food_ops_server import (
    AQUACULTURE_KIND,
    CROP_KIND,
    FOOD_SECTOR_KIND,
    LONGSADDLE_KIND,
    FoodOpsBindings,
    FoodOpsServerError,
    build_parser,
    main,
    start_server,
)


class MemoryBindings:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.records: dict[str, dict[str, object]] = {}
        self.food_calls: list[dict[str, object]] = []
        self.longsaddle_calls: list[dict[str, object]] = []
        self.aquaculture_calls: list[dict[str, object]] = []
        self.crop_calls: list[dict[str, object]] = []
        self.saved_requests: list[dict[str, object]] = []

    def bindings(self) -> FoodOpsBindings:
        return FoodOpsBindings(
            bootstrap=lambda: {
                "schema": "test.bootstrap/1",
                "baseline": {"entities": [], "totals": {}},
            },
            preview_food_sector=self.preview_food,
            preview_longsaddle=self.preview_longsaddle,
            save_scenario=self.save,
            list_scenarios=self.listing,
            load_scenario=self.load,
            export_markdown=lambda scenario_id: f"# {scenario_id}\n",
            export_html=lambda scenario_id: f"<!doctype html><title>{scenario_id}</title>",
            verify_store=lambda: {
                "status": "ok",
                "scenario_count": len(self.records),
                "notion_write_capability": False,
                "ledger_post_capability": False,
            },
            production_catalog=lambda: {
                "schema": "tnp.food-production.catalog/1",
                "species": ["tilapia"],
                "crops": ["wheat"],
            },
            preview_aquaculture=self.preview_aquaculture,
            preview_crop=self.preview_crop,
        )

    def preview_food(self, request: Mapping[str, object]) -> dict[str, object]:
        self.food_calls.append(dict(request))
        return {
            "schema": "tnp.food-sector.month-preview/1",
            "month_label": request.get("month_label"),
            "canonical": False,
            "safety": {
                "notion_write_capability": False,
                "ledger_post_capability": False,
            },
        }

    def preview_longsaddle(self, request: Mapping[str, object]) -> dict[str, object]:
        self.longsaddle_calls.append(dict(request))
        return {
            "schema": "tnp.food-security.longsaddle-plan/1",
            "target_tons": request.get("target_tons"),
            "canonical": False,
            "safety": {
                "notion_write_capability": False,
                "ledger_post_capability": False,
            },
        }

    def preview_aquaculture(self, request: Mapping[str, object]) -> dict[str, object]:
        self.aquaculture_calls.append(dict(request))
        return {
            "schema": "tnp.food-production.aquaculture-plan/1",
            "scenario_id": request.get("scenario_id"),
        }

    def preview_crop(self, request: Mapping[str, object]) -> dict[str, object]:
        self.crop_calls.append(dict(request))
        return {
            "schema": "tnp.food-production.crop-plan/1",
            "scenario_id": request.get("scenario_id"),
        }

    def save(
        self,
        scenario_id: str,
        kind: str,
        request: Mapping[str, object],
        result: Mapping[str, object],
    ) -> tuple[dict[str, object], bool]:
        with self.lock:
            normalized_request = dict(request)
            normalized_result = dict(result)
            self.saved_requests.append(normalized_request)
            record = {
                "scenario_id": scenario_id,
                "kind": kind,
                "request": normalized_request,
                "result": normalized_result,
            }
            existing = self.records.get(scenario_id)
            if existing is not None:
                if existing != record:
                    raise ValueError("different immutable content")
                return existing, True
            self.records[scenario_id] = record
            return record, False

    def listing(self, kind: str | None) -> list[dict[str, object]]:
        with self.lock:
            return [
                {
                    "scenario_id": record["scenario_id"],
                    "kind": record["kind"],
                }
                for record in self.records.values()
                if kind is None or record["kind"] == kind
            ]

    def load(self, scenario_id: str) -> dict[str, object]:
        try:
            return self.records[scenario_id]
        except KeyError as exc:
            from baen_economy.food_ops_server import ServiceError

            raise ServiceError(404, "scenario_not_found", "scenario is missing") from exc

class FoodOpsServerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.services = MemoryBindings()
        self.running = start_server(
            port=0,
            bindings=self.services.bindings(),
            app_html="<!doctype html><title>Food Operator Test</title>",
            max_body_bytes=1024,
        )

    def tearDown(self) -> None:
        self.running.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | str | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        payload = body.encode("utf-8") if isinstance(body, str) else body
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.running.port, timeout=5
        )
        request_headers = dict(headers or {})
        if payload is not None and "Content-Length" not in request_headers:
            request_headers["Content-Length"] = str(len(payload))
        connection.request(method, path, body=payload, headers=request_headers)
        response = connection.getresponse()
        data = response.read()
        result_headers = {key.lower(): value for key, value in response.getheaders()}
        connection.close()
        return response.status, result_headers, data

    def json_request(
        self,
        method: str,
        path: str,
        payload: object,
        *,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], dict[str, object]]:
        request_headers = {"Content-Type": "application/json"}
        request_headers.update(headers or {})
        encoded = None if method in {"GET", "HEAD"} else json.dumps(
            payload, separators=(",", ":")
        )
        status, response_headers, body = self.request(
            method,
            path,
            body=encoded,
            headers=request_headers,
        )
        return status, response_headers, json.loads(body)

    def test_loopback_port_app_health_and_clean_shutdown(self) -> None:
        self.assertEqual(self.running.server.server_address[0], "127.0.0.1")
        self.assertGreater(self.running.port, 0)
        self.assertEqual(
            self.running.base_url, f"http://127.0.0.1:{self.running.port}"
        )
        status, headers, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"Food Operator Test", body)
        self.assertIn("default-src 'self'", headers["content-security-policy"])
        self.assertEqual(headers["x-frame-options"], "DENY")

        status, _, payload = self.json_request("GET", "/api/health", {})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        data = payload["data"]
        self.assertEqual(data["port"], self.running.port)
        self.assertFalse(data["notion_write_capability"])
        self.assertFalse(data["canonical_ledger_post_capability"])

        self.running.close()
        self.assertFalse(self.running.thread.is_alive())
        self.running.close()  # Idempotent shutdown.

    def test_non_loopback_host_is_refused_before_bind(self) -> None:
        with self.assertRaisesRegex(FoodOpsServerError, "127.0.0.1"):
            from baen_economy.food_ops_server import create_server

            create_server(
                host="0.0.0.0",
                bindings=self.services.bindings(),
                app_html="<html></html>",
            )

    def test_cli_contract_accepts_database_host_port_and_open(self) -> None:
        arguments = build_parser().parse_args(
            [
                "--database",
                "food-ops-cli.sqlite3",
                "--host",
                "127.0.0.1",
                "--port",
                "0",
                "--open",
            ]
        )
        self.assertEqual(arguments.store, Path("food-ops-cli.sqlite3"))
        self.assertEqual(arguments.host, "127.0.0.1")
        self.assertEqual(arguments.port, 0)
        self.assertTrue(arguments.open)

    def test_cli_interrupt_closes_active_requests_before_listener(self) -> None:
        events: list[str] = []

        class FakeServer:
            base_url = "http://127.0.0.1:41234"
            handler_shutdown_timeout_seconds = 5.0

            def serve_forever(self, *, poll_interval: float) -> None:
                events.append(f"serve:{poll_interval}")
                raise KeyboardInterrupt

            def close_active_requests(self) -> None:
                events.append("close_active")

            def server_close(self) -> None:
                events.append("server_close")

            def wait_for_active_requests(self, timeout: float) -> bool:
                events.append(f"wait:{timeout}")
                return True

        with mock.patch(
            "baen_economy.food_ops_server.create_server", return_value=FakeServer()
        ), mock.patch("builtins.print"):
            self.assertEqual(main(["--database", "unused.sqlite3"]), 0)
        self.assertEqual(
            events,
            ["serve:0.2", "close_active", "server_close", "wait:5.0"],
        )

    def test_static_app_path_is_used_when_renderer_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="food ops static ") as directory:
            root = Path(directory)
            (root / "index.html").write_text(
                "<!doctype html><title>Static Fallback</title>", encoding="utf-8"
            )
            (root / "app.js").write_text("window.staticFallback=true;", encoding="utf-8")
            with mock.patch(
                "baen_economy.food_ops_server._load_default_app",
                side_effect=ImportError("test renderer unavailable"),
            ):
                alternate = start_server(
                    port=0,
                    bindings=self.services.bindings(),
                    app_path=root,
                )
            try:
                connection = http.client.HTTPConnection(
                    "127.0.0.1", alternate.port, timeout=5
                )
                connection.request("GET", "/")
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertIn(b"Static Fallback", response.read())
                connection.close()
                connection = http.client.HTTPConnection(
                    "127.0.0.1", alternate.port, timeout=5
                )
                connection.request("GET", "/app.js")
                response = connection.getresponse()
                self.assertEqual(response.status, 200)
                self.assertIn(b"staticFallback", response.read())
                connection.close()
            finally:
                alternate.close()

            with mock.patch(
                "baen_economy.food_ops_server._load_default_app",
                side_effect=ImportError("test renderer unavailable"),
            ):
                single_file = start_server(
                    port=0,
                    bindings=self.services.bindings(),
                    app_path=root / "index.html",
                )
            try:
                connection = http.client.HTTPConnection(
                    "127.0.0.1", single_file.port, timeout=5
                )
                connection.request("GET", "/app.js")
                response = connection.getresponse()
                self.assertEqual(response.status, 404)
                response.read()
                connection.close()
            finally:
                single_file.close()

    def test_bootstrap_and_preview_routes_use_standard_envelopes(self) -> None:
        status, _, payload = self.json_request("GET", "/api/bootstrap", {})
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["schema"], "test.bootstrap/1")
        self.assertEqual(payload["data"]["saved_scenarios"], [])
        self.assertEqual(payload["data"]["store"]["status"], "ok")
        self.assertEqual(
            payload["data"]["production_catalog"]["species"], ["tilapia"]
        )

        status, _, payload = self.json_request(
            "POST",
            "/api/food-sector/preview",
            {"month_label": "Hammer preview", "seed": "visible only in memory"},
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(
            payload["data"]["schema"], "tnp.food-sector.month-preview/1"
        )
        status, _, payload = self.json_request(
            "POST",
            "/api/longsaddle/preview",
            {"request": {"target_tons": "1200"}},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["target_tons"], "1200")

        status, _, payload = self.json_request(
            "POST",
            "/api/production/aquaculture/preview",
            {"scenario_id": "aqua-1"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            payload["data"]["schema"],
            "tnp.food-production.aquaculture-plan/1",
        )
        status, _, payload = self.json_request(
            "POST",
            "/api/production/crop/preview",
            {"scenario_id": "crop-1"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            payload["data"]["schema"], "tnp.food-production.crop-plan/1"
        )

    def test_rejects_malformed_duplicate_non_object_and_wrong_media_json(self) -> None:
        cases = (
            (b'{"month_label":', "malformed_json"),
            (b'{"month_label":"x","month_label":"y"}', "malformed_json"),
            (b"[]", "json_object_required"),
        )
        for body, code in cases:
            with self.subTest(code=code):
                status, _, raw = self.request(
                    "POST",
                    "/api/food-sector/preview",
                    body=body,
                    headers={"Content-Type": "application/json"},
                )
                payload = json.loads(raw)
                self.assertEqual(status, 400)
                self.assertFalse(payload["ok"])
                self.assertEqual(payload["error"]["code"], code)

        status, _, raw = self.request(
            "POST",
            "/api/food-sector/preview",
            body=b"{}",
            headers={"Content-Type": "text/plain"},
        )
        self.assertEqual(status, 415)
        self.assertEqual(json.loads(raw)["error"]["code"], "unsupported_media_type")

    def test_rejects_oversized_body_without_invoking_engine(self) -> None:
        body = json.dumps({"value": "x" * 1100})
        status, _, raw = self.request(
            "POST",
            "/api/food-sector/preview",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 413)
        self.assertEqual(json.loads(raw)["error"]["code"], "body_too_large")
        self.assertEqual(self.services.food_calls, [])

    def test_pre_read_rejection_closes_connection_without_request_desync(self) -> None:
        client = socket.create_connection(("127.0.0.1", self.running.port), timeout=5)
        self.addCleanup(client.close)
        client.sendall(
            (
                "POST /api/food-sector/preview HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{self.running.port}\r\n"
                "Content-Type: text/plain\r\n"
                "Content-Length: 2\r\n\r\n"
                "{}"
                "GET /api/health HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{self.running.port}\r\n\r\n"
            ).encode("ascii")
        )
        chunks: list[bytes] = []
        while True:
            data = client.recv(65536)
            if not data:
                break
            chunks.append(data)
        response = b"".join(chunks)
        self.assertIn(b"415 Unsupported Media Type", response)
        self.assertIn(b"Connection: close", response)
        self.assertEqual(response.count(b"HTTP/1.1"), 1)
        self.assertEqual(self.services.food_calls, [])

    def test_options_body_is_closed_without_pipelined_execution(self) -> None:
        client = socket.create_connection(("127.0.0.1", self.running.port), timeout=5)
        self.addCleanup(client.close)
        client.sendall(
            (
                "OPTIONS /api/food-sector/preview HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{self.running.port}\r\n"
                "Content-Length: 2\r\n\r\n"
                "{}"
                "GET /api/health HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{self.running.port}\r\n\r\n"
            ).encode("ascii")
        )
        chunks: list[bytes] = []
        while True:
            data = client.recv(65536)
            if not data:
                break
            chunks.append(data)
        response = b"".join(chunks)
        self.assertIn(b"405 Method Not Allowed", response)
        self.assertIn(b"Connection: close", response)
        self.assertEqual(response.count(b"HTTP/1.1"), 1)

    def test_strict_host_origin_and_content_length_framing(self) -> None:
        status, headers, payload = self.json_request(
            "GET",
            "/api/health",
            {},
            headers={"Host": f"localhost:{self.running.port}/not-an-authority"},
        )
        self.assertEqual(status, 403)
        self.assertEqual(headers["connection"], "close")
        self.assertEqual(payload["error"]["code"], "invalid_host")

        duplicate_origin = socket.create_connection(
            ("127.0.0.1", self.running.port), timeout=5
        )
        try:
            duplicate_origin.sendall(
                (
                    "GET /api/health HTTP/1.1\r\n"
                    f"Host: 127.0.0.1:{self.running.port}\r\n"
                    f"Origin: http://127.0.0.1:{self.running.port}\r\n"
                    f"Origin: http://127.0.0.1:{self.running.port}\r\n\r\n"
                ).encode("ascii")
            )
            response = duplicate_origin.recv(65536)
            self.assertIn(b"403 Forbidden", response)
            self.assertIn(b"Connection: close", response)
        finally:
            duplicate_origin.close()

        for invalid_length in ("+2", "1_0", "-1"):
            with self.subTest(content_length=invalid_length):
                client = socket.create_connection(
                    ("127.0.0.1", self.running.port), timeout=5
                )
                try:
                    client.sendall(
                        (
                            "POST /api/food-sector/preview HTTP/1.1\r\n"
                            f"Host: 127.0.0.1:{self.running.port}\r\n"
                            "Content-Type: application/json\r\n"
                            f"Content-Length: {invalid_length}\r\n\r\n"
                        ).encode("ascii")
                    )
                    response = client.recv(65536)
                    self.assertIn(b"400 Bad Request", response)
                    self.assertIn(b"Connection: close", response)
                finally:
                    client.close()

    def test_shutdown_interrupts_and_joins_a_stalled_body_handler(self) -> None:
        client = socket.create_connection(("127.0.0.1", self.running.port), timeout=5)
        self.addCleanup(client.close)
        client.sendall(
            (
                "POST /api/food-sector/preview HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{self.running.port}\r\n"
                "Content-Type: application/json\r\n"
                "Content-Length: 100\r\n\r\n"
                "{"
            ).encode("ascii")
        )
        deadline = time.monotonic() + 2
        while self.running.server.active_request_count == 0 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(self.running.server.active_request_count, 1)

        started = time.monotonic()
        self.running.close()
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 2)
        self.assertFalse(self.running.thread.is_alive())
        self.assertEqual(self.running.server.active_request_count, 0)

    def test_natural_body_timeout_returns_408_and_closes_connection(self) -> None:
        self.running.server.request_timeout_seconds = 0.05
        client = socket.create_connection(("127.0.0.1", self.running.port), timeout=5)
        self.addCleanup(client.close)
        client.sendall(
            (
                "POST /api/food-sector/preview HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{self.running.port}\r\n"
                "Content-Type: application/json\r\n"
                "Content-Length: 20\r\n\r\n"
                "{"
            ).encode("ascii")
        )
        chunks: list[bytes] = []
        while True:
            data = client.recv(65536)
            if not data:
                break
            chunks.append(data)
        response = b"".join(chunks)
        self.assertIn(b"408 Request Timeout", response)
        self.assertIn(b"Connection: close", response)
        self.assertIn(b'"code":"request_timeout"', response)

    def test_blocked_binding_cannot_make_shutdown_wait_without_bound(self) -> None:
        entered = threading.Event()
        release = threading.Event()
        services = MemoryBindings()
        bindings = services.bindings()

        def blocked_preview(request: Mapping[str, object]) -> dict[str, object]:
            entered.set()
            release.wait()
            return services.preview_food(request)

        blocked_bindings = FoodOpsBindings(
            bootstrap=bindings.bootstrap,
            preview_food_sector=blocked_preview,
            preview_longsaddle=bindings.preview_longsaddle,
            save_scenario=bindings.save_scenario,
            list_scenarios=bindings.list_scenarios,
            load_scenario=bindings.load_scenario,
            export_markdown=bindings.export_markdown,
            export_html=bindings.export_html,
            verify_store=bindings.verify_store,
            production_catalog=bindings.production_catalog,
            preview_aquaculture=bindings.preview_aquaculture,
            preview_crop=bindings.preview_crop,
        )
        alternate = start_server(
            port=0,
            bindings=blocked_bindings,
            app_html="<!doctype html><title>Blocked callback</title>",
        )
        alternate.server.handler_shutdown_timeout_seconds = 0.05
        client_done = threading.Event()

        def make_request() -> None:
            connection = http.client.HTTPConnection(
                "127.0.0.1", alternate.port, timeout=2
            )
            try:
                body = b'{"month_label":"x","seed":"x"}'
                connection.request(
                    "POST",
                    "/api/food-sector/preview",
                    body=body,
                    headers={
                        "Content-Type": "application/json",
                        "Content-Length": str(len(body)),
                    },
                )
                connection.getresponse().read()
            except (OSError, http.client.HTTPException):
                pass
            finally:
                connection.close()
                client_done.set()

        client_thread = threading.Thread(target=make_request, daemon=True)
        client_thread.start()
        self.assertTrue(entered.wait(timeout=2))
        started = time.monotonic()
        with self.assertRaisesRegex(FoodOpsServerError, "callback did not return"):
            alternate.close()
        self.assertLess(time.monotonic() - started, 1)
        self.assertFalse(alternate.thread.is_alive())
        release.set()
        self.assertTrue(client_done.wait(timeout=2))
        alternate.close()
        self.assertEqual(alternate.server.active_request_count, 0)

    def test_save_recomputes_redacts_seed_and_supports_list_load_export(self) -> None:
        request = {
            "scenario_id": "food-month-ui-metadata",
            "month_label": "Hammer 1495 preview",
            "seed": "raw-seed-that-must-not-be-stored",
        }
        result = self.services.preview_food(request)
        status, _, payload = self.json_request(
            "POST",
            "/api/scenarios",
            {
                "scenario_id": "food-month-1",
                "kind": FOOD_SECTOR_KIND,
                "request": request,
                "result": result,
            },
        )
        self.assertEqual(status, 201)
        self.assertFalse(payload["data"]["replayed_existing_save"])
        stored = self.services.saved_requests[-1]
        self.assertNotIn("seed", stored)
        self.assertFalse(stored["raw_seed_persisted"])
        self.assertEqual(
            stored["seed_fingerprint"],
            hashlib.sha256(request["seed"].encode("utf-8")).hexdigest(),
        )

        status, _, payload = self.json_request(
            "POST",
            "/api/scenarios",
            {
                "scenario_id": "food-month-1",
                "kind": FOOD_SECTOR_KIND,
                "request": request,
                "result": result,
            },
        )
        self.assertEqual(status, 200)
        self.assertTrue(payload["data"]["replayed_existing_save"])

        status, _, payload = self.json_request("GET", "/api/scenarios", {})
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["count"], 1)
        status, _, payload = self.json_request(
            "GET", "/api/scenarios/food-month-1", {}
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["data"]["scenario_id"], "food-month-1")

        status, headers, body = self.request(
            "GET", "/api/scenarios/food-month-1/export?format=html"
        )
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["content-type"])
        self.assertIn("food-month-1.html", headers["content-disposition"])
        self.assertIn(b"food-month-1", body)

    def test_save_rejects_a_client_result_that_does_not_recompute(self) -> None:
        status, _, payload = self.json_request(
            "POST",
            "/api/scenarios",
            {
                "scenario_id": "tampered",
                "kind": LONGSADDLE_KIND,
                "request": {"target_tons": "1200"},
                "result": {
                    "schema": "tnp.food-security.longsaddle-plan/1",
                    "target_tons": "9999",
                },
            },
        )
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"]["code"], "preview_mismatch")
        self.assertNotIn("tampered", self.services.records)

    def test_production_plans_recompute_and_save_under_distinct_kinds(self) -> None:
        cases = (
            (
                AQUACULTURE_KIND,
                {"scenario_id": "aqua-production-1"},
                "tnp.food-production.aquaculture-plan/1",
            ),
            (
                CROP_KIND,
                {"scenario_id": "crop-production-1"},
                "tnp.food-production.crop-plan/1",
            ),
        )
        for kind, request, schema in cases:
            with self.subTest(kind=kind):
                preview = (
                    self.services.preview_aquaculture(request)
                    if kind == AQUACULTURE_KIND
                    else self.services.preview_crop(request)
                )
                status, _, payload = self.json_request(
                    "POST",
                    "/api/scenarios",
                    {
                        "scenario_id": request["scenario_id"],
                        "kind": kind,
                        "request": request,
                        "result": preview,
                    },
                )
                self.assertEqual(status, 201)
                self.assertEqual(
                    payload["data"]["scenario"]["result"]["schema"], schema
                )
                self.assertEqual(
                    self.services.records[request["scenario_id"]]["kind"], kind
                )

    def test_host_origin_static_traversal_and_write_routes_fail_closed(self) -> None:
        status, _, payload = self.json_request(
            "GET", "/api/health", {}, headers={"Host": "attacker.invalid"}
        )
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"]["code"], "invalid_host")

        status, _, payload = self.json_request(
            "POST",
            "/api/food-sector/preview",
            {"month_label": "x", "seed": "x"},
            headers={"Origin": "https://attacker.invalid"},
        )
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"]["code"], "cross_origin_denied")

        for path in (
            "/api/notion/write",
            "/api/ledger/post",
            "/%2e%2e/secret.txt",
        ):
            status, _, payload = self.json_request("GET", path, {})
            self.assertEqual(status, 404)
            self.assertFalse(payload["ok"])


class FoodOpsServerIntegrationTests(unittest.TestCase):
    def request(
        self,
        running,
        method: str,
        path: str,
        payload: object | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {} if body is None else {
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
        }
        connection = http.client.HTTPConnection("127.0.0.1", running.port, timeout=15)
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        data = response.read()
        response_headers = {key.lower(): value for key, value in response.getheaders()}
        connection.close()
        return response.status, response_headers, data

    def test_real_app_engines_store_reopen_and_exports(self) -> None:
        with tempfile.TemporaryDirectory(prefix="food ops server integration ") as directory:
            database = Path(directory) / "food-operations.sqlite3"
            with start_server(port=0, store_path=database) as running:
                status, _, app = self.request(running, "GET", "/")
                self.assertEqual(status, 200)
                self.assertIn(b"Baen Food-Sector Operator", app)

                status, _, raw = self.request(running, "GET", "/api/bootstrap")
                self.assertEqual(status, 200, raw.decode("utf-8", errors="replace"))
                bootstrap = json.loads(raw)["data"]
                self.assertEqual(len(bootstrap["baseline"]["entities"]), 5)
                self.assertEqual(bootstrap["baseline"]["totals"]["staff"], 63)
                self.assertEqual(
                    bootstrap["baseline"]["totals"]["monthly_net_gp"], "5950"
                )
                self.assertEqual(len(bootstrap["gm_only_clocks"]), 5)
                self.assertEqual(len(bootstrap["known_operational_issues"]), 1)
                self.assertEqual(len(bootstrap["species"]), 15)
                self.assertEqual(len(bootstrap["crops"]), 12)
                self.assertEqual(len(bootstrap["production_catalog"]["species"]), 15)
                self.assertEqual(len(bootstrap["production_catalog"]["crops"]), 12)
                self.assertFalse(bootstrap["safety"]["notion_write_capability"])

                food_request = {
                    "scenario_id": "real-food-ui",
                    "month_label": "Hammer 1495 local preview",
                    "seed": "real-integration-seed-never-persist",
                    "sector_assumptions": {
                        "Agriculture": {
                            "market": "stable",
                            "vara_active": True,
                            "revenue_streams": 1,
                            "competent_managers": 0,
                            "monopoly": False,
                            "excellent_accounting": False,
                            "rapid_expansion": False,
                        },
                        "Aquaculture": {
                            "market": "stable",
                            "vara_active": True,
                            "revenue_streams": 4,
                            "competent_managers": 0,
                            "monopoly": False,
                            "excellent_accounting": False,
                            "rapid_expansion": False,
                        },
                    },
                }
                status, _, raw = self.request(
                    running, "POST", "/api/food-sector/preview", food_request
                )
                self.assertEqual(status, 200, raw.decode("utf-8", errors="replace"))
                food_result = json.loads(raw)["data"]
                self.assertEqual(food_result["schema"], "tnp.food-sector.month-preview/1")
                self.assertEqual(set(food_result["decision_brief"]), {"Source", "Assumption", "Derived", "Unknown"})
                self.assertEqual(food_result["safety"]["notion_writes"], 0)

                save_payload = {
                    "scenario_id": "real-food-1",
                    "kind": FOOD_SECTOR_KIND,
                    "request": food_request,
                    "result": food_result,
                }
                status, _, raw = self.request(
                    running, "POST", "/api/scenarios", save_payload
                )
                self.assertEqual(status, 201, raw.decode("utf-8", errors="replace"))
                self.assertNotIn(
                    b"real-integration-seed-never-persist", database.read_bytes()
                )

                longsaddle_request = {
                    "scenario_id": "real-longsaddle-ui",
                    "scenario_name": "Illustrative low route case",
                    "target_tons": "1200",
                    "supplier_stock_tons": "900",
                    "opening_stock_tons": "0",
                    "demand_tons": "300",
                    "dispatch_tons": "900",
                    "route_capacity_tons_per_trip": "150",
                    "trips": 6,
                    "travel_periods": 1,
                    "transport_loss_percent": "2",
                    "storage_capacity_tons": "1200",
                    "price_gp_per_ton": "50",
                    "funding_gp": "65000",
                }
                status, _, raw = self.request(
                    running, "POST", "/api/longsaddle/preview", longsaddle_request
                )
                self.assertEqual(status, 200, raw.decode("utf-8", errors="replace"))
                longsaddle_result = json.loads(raw)["data"]
                self.assertEqual(
                    longsaddle_result["schema"],
                    "tnp.food-security.longsaddle-plan/1",
                )
                self.assertEqual(
                    Decimal(longsaddle_result["delivered_tons"]), Decimal("882")
                )
                self.assertEqual(
                    Decimal(longsaddle_result["closing_tons"]), Decimal("582")
                )
                self.assertEqual(
                    Decimal(longsaddle_result["conservation_residual_tons"]),
                    Decimal("0"),
                )

                status, _, raw = self.request(
                    running,
                    "POST",
                    "/api/scenarios",
                    {
                        "scenario_id": "real-longsaddle-1",
                        "kind": LONGSADDLE_KIND,
                        "request": longsaddle_request,
                        "result": longsaddle_result,
                    },
                )
                self.assertEqual(status, 201, raw.decode("utf-8", errors="replace"))
                status, headers, exported = self.request(
                    running,
                    "GET",
                    "/api/scenarios/real-longsaddle-1/export?format=html",
                )
                self.assertEqual(status, 200)
                self.assertIn("text/html", headers["content-type"])
                self.assertIn(b"longsaddle_plan", exported)

                production_cases = (
                    (
                        AQUACULTURE_KIND,
                        "/api/production/aquaculture/preview",
                        {
                            "scenario_id": "real-aquaculture-1",
                            "species_id": "tilapia",
                            "capacity": "1000",
                            "capacity_basis": "cubic_meters",
                            "planned_liveweight_output_lb": "900",
                            "opening_feed_lb": "1600",
                            "feed_receipts_lb": "0",
                        },
                        "tnp.food-production.aquaculture-plan/1",
                    ),
                    (
                        CROP_KIND,
                        "/api/production/crop/preview",
                        {
                            "scenario_id": "real-crop-1",
                            "crop_id": "wheat",
                            "baseline_yield_tons": "100",
                            "baseline_fertilizer_tons": "20",
                            "opening_food_tons": "10",
                            "food_receipts_tons": "0",
                            "planned_consumption_tons": "100",
                        },
                        "tnp.food-production.crop-plan/1",
                    ),
                )
                for kind, route, request, schema in production_cases:
                    status, _, raw = self.request(running, "POST", route, request)
                    self.assertEqual(status, 200, raw.decode("utf-8", errors="replace"))
                    result = json.loads(raw)["data"]
                    self.assertEqual(result["schema"], schema)
                    self.assertEqual(
                        set(result["decision_brief"]),
                        {"Source", "Assumption", "Derived", "Unknown"},
                    )
                    status, _, raw = self.request(
                        running,
                        "POST",
                        "/api/scenarios",
                        {
                            "scenario_id": request["scenario_id"],
                            "kind": kind,
                            "request": request,
                            "result": result,
                        },
                    )
                    self.assertEqual(
                        status, 201, raw.decode("utf-8", errors="replace")
                    )

            # Reopening uses a fresh SQLite connection and retains all four kinds.
            with start_server(
                port=0,
                store_path=database,
                app_html="<!doctype html><title>Reopen</title>",
            ) as reopened:
                status, _, raw = self.request(reopened, "GET", "/api/scenarios")
                self.assertEqual(status, 200)
                listing = json.loads(raw)["data"]
                self.assertEqual(listing["count"], 4)
                status, _, raw = self.request(
                    reopened, "GET", "/api/scenarios/real-food-1"
                )
                self.assertEqual(status, 200)
                stored = json.loads(raw)["data"]
                self.assertFalse(stored["request"]["raw_seed_persisted"])
                self.assertNotIn("seed", stored["request"])
                status, _, raw = self.request(
                    reopened,
                    "POST",
                    "/api/scenarios",
                    {
                        "scenario_id": "real-food-1",
                        "kind": FOOD_SECTOR_KIND,
                        "request": stored["request"],
                        "result": stored["result"],
                    },
                )
                self.assertEqual(status, 200, raw.decode("utf-8", errors="replace"))
                self.assertTrue(json.loads(raw)["data"]["replayed_existing_save"])


if __name__ == "__main__":
    unittest.main()
