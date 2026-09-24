"""Loopback-only browser application for the source-grounded Baen Empire operator."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import sys
import threading
from types import TracebackType
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit
import webbrowser

from .empire_cli import DEFAULT_CENSUS, census_status, product_status
from .corridor_finance import corridor_finance_snapshot
from .empire_close import close_status
from .financial_close import financial_close_snapshot
from .empire_operations import (
    EmpireBusinessError,
    render_empire_business_report,
    run_empire_business_turn,
)
from .empire_source_products import (
    EmpireSourceProductError,
    source_known_state,
    source_semantic_coverage,
    source_semantic_domains,
)
from .empire_ops_app import APP_HTML
from .empire_ops_store import EmpireOpsStore, EmpireOpsStoreError

LOOPBACK_HOST = "127.0.0.1"
CODESPACES_HOST = "0.0.0.0"
DEFAULT_MAX_BODY_BYTES = 256 * 1024
DEFAULT_STORE_PATH = Path.home() / "Documents" / "Baen Economy" / "baen-empire-operator.sqlite"


class EmpireOpsServerError(ValueError):
    pass


def build_bootstrap(*, census_path: Path = DEFAULT_CENSUS) -> dict[str, Any]:
    domains = source_semantic_domains()
    return {
        "schema": "tnp.economy.empire-ops-bootstrap/1",
        "source_status": census_status(census_path),
        "semantic_domains": domains,
        "semantic_coverage": source_semantic_coverage(domains),
        "known_state": source_known_state(),
        "products": product_status(),
        "corridor_finance": corridor_finance_snapshot(),
        "empire_close": close_status(),
        "financial_close": financial_close_snapshot(),
        "system_lanes": {
            "population_labour": {"status": "PARTIAL_SOURCE_MAPPED", "basis": "Neverwinter/Waterdeep census, user-ratified Forgedeep population and admitted commercial labour; settlement-wide labour pools remain unresolved"},
            "production_supply": {"status": "PARTIAL_SOURCE_MAPPED", "basis": "source-backed industrial lines exist; input recipes and opening inventories remain incomplete"},
            "consumption_prices": {"status": "BLOCKED", "basis": "household baskets, general commodity prices, and physical food outputs are not source-backed"},
            "transport_trade": {"status": "PARTIAL_SOURCE_MAPPED", "basis": "five arterial distances and one steel flow are mapped; route capacities/losses and OpenTTD unit bridge remain unresolved"},
            "banking_treasury": {"status": "PARTIAL_SOURCE_MAPPED", "basis": "loan portfolio and financial authority exist; current trial balance, reserves, and exact liquid cash remain unresolved"},
            "migration_shocks": {"status": "BLOCKED", "basis": "migration rates and shock probabilities remain unresolved and are not invented on the actual lane"},
        },
        "safety": {
            "canonical": False,
            "notion_write_capability": False,
            "notion_writes": 0,
            "canonical_ledger_post_capability": False,
            "canonical_ledger_postings": 0,
            "campaign_time_advanced": False,
        },
    }


def run_preview(request: Mapping[str, Any]) -> dict[str, Any]:
    seed = request.get("seed")
    month = request.get("month_label", "Day 7 Hammer 1495 DR — monthly preview")
    market = request.get("market_condition", "unknown")
    vara = request.get("vara_active", False)
    if not isinstance(seed, str) or not seed.strip():
        raise EmpireOpsServerError("seed is required")
    if not isinstance(month, str) or not month.strip():
        raise EmpireOpsServerError("month_label is required")
    if market not in {"unknown", "stable", "boom", "recession"}:
        raise EmpireOpsServerError("market_condition must be unknown, stable, boom, or recession")
    if type(vara) is not bool:
        raise EmpireOpsServerError("vara_active must be boolean")

    result = run_empire_business_turn(
        seed=seed,
        month_label=month,
        market_condition=str(market),
        vara_active=vara,
    )
    return {
        "schema": "tnp.economy.empire-ops-preview/1",
        "result": result,
        "report": render_empire_business_report(result),
        "safety": {
            "canonical": False,
            "notion_writes": 0,
            "canonical_ledger_postings": 0,
            "campaign_time_advanced": False,
            "raw_seed_persisted": False,
        },
    }


class EmpireOpsHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        *,
        app_html: str,
        max_body_bytes: int,
        census_path: Path,
        store_path: Path,
    ) -> None:
        self.app_html = app_html
        self.max_body_bytes = max_body_bytes
        self.census_path = census_path
        self.store = EmpireOpsStore(store_path)
        super().__init__(server_address, EmpireOpsHandler)

    def server_close(self) -> None:
        try:
            self.store.close()
        finally:
            super().server_close()

    @property
    def port(self) -> int:
        return int(self.server_address[1])

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


class EmpireOpsHandler(BaseHTTPRequestHandler):
    server: EmpireOpsHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        return

    def _allowed_request(self) -> bool:
        host = (self.headers.get("Host") or "").split(":", 1)[0].strip("[]").lower()
        allowed_hosts = {"127.0.0.1", "localhost", "::1"}
        if os.environ.get("CODESPACES") == "true":
            domain = os.environ.get("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "").strip().lower()
            if domain and host.endswith("." + domain):
                allowed_hosts.add(host)
        if host not in allowed_hosts:
            self._json_error(
                403,
                "invalid_host",
                "This operator accepts loopback or the authenticated Codespaces forwarded host only.",
            )
            return False
        origin = self.headers.get("Origin")
        if origin:
            parsed = urlsplit(origin)
            origin_host = (parsed.hostname or "").lower()
            if origin_host not in allowed_hosts:
                self._json_error(403, "cross_origin_denied", "Cross-origin requests are denied.")
                return False
        return True

    def _send(
        self,
        status: int,
        body: bytes,
        content_type: str,
        *,
        extra_headers: Mapping[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: object) -> None:
        body = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            default=str,
            separators=(",", ":"),
        ).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _json_error(self, status: int, code: str, message: str) -> None:
        self._json(status, {"ok": False, "error": {"code": code, "message": message}})

    def _read_json(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise EmpireOpsServerError("Content-Length is required")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise EmpireOpsServerError("Content-Length is invalid") from exc
        if length < 0 or length > self.server.max_body_bytes:
            raise EmpireOpsServerError("request body is too large")
        raw = self.rfile.read(length)
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise EmpireOpsServerError("request body must be a JSON object") from exc
        if not isinstance(value, dict):
            raise EmpireOpsServerError("request body must be a JSON object")
        return value

    def do_GET(self) -> None:
        if not self._allowed_request():
            return
        path = urlsplit(self.path).path
        if path in {"/", "/index.html"}:
            self._send(
                200,
                self.server.app_html.encode("utf-8"),
                "text/html; charset=utf-8",
                extra_headers={
                    "Content-Security-Policy": (
                        "default-src 'self'; style-src 'unsafe-inline'; "
                        "script-src 'unsafe-inline'; connect-src 'self'; "
                        "img-src 'self' data:; object-src 'none'; base-uri 'none'"
                    )
                },
            )
            return
        if path == "/api/health":
            self._json(
                200,
                {
                    "ok": True,
                    "data": {
                        "service": "baen-empire-ops",
                        "canonical": False,
                        "notion_writes": 0,
                        "canonical_ledger_postings": 0,
                        "campaign_time_advanced": False,
                    },
                },
            )
            return
        if path == "/api/bootstrap":
            try:
                payload = build_bootstrap(census_path=self.server.census_path)
                payload["saved_runs"] = self.server.store.list_runs()
            except (EmpireSourceProductError, OSError, ValueError) as exc:
                self._json_error(409, "source_state_blocked", str(exc))
                return
            self._json(200, {"ok": True, "data": payload})
            return
        if path == "/api/runs":
            self._json(200, {"ok": True, "data": {"runs": self.server.store.list_runs()}})
            return
        if path.startswith("/api/runs/"):
            tail = path[len("/api/runs/"):]
            if tail.endswith("/export"):
                run_id = tail[:-len("/export")].rstrip("/")
                query = urlsplit(self.path).query
                fmt = "html"
                for part in query.split("&"):
                    if part.startswith("format="):
                        fmt = part.split("=", 1)[1]
                try:
                    content_type, body = self.server.store.export(run_id, fmt)
                except EmpireOpsStoreError as exc:
                    self._json_error(404, "saved_run_not_found", str(exc))
                    return
                self._send(200, body, content_type)
                return
            try:
                row = self.server.store.get(tail)
            except EmpireOpsStoreError as exc:
                self._json_error(404, "saved_run_not_found", str(exc))
                return
            self._json(200, {"ok": True, "data": row})
            return
        if path == "/api/compare":
            query = urlsplit(self.path).query
            params = {}
            for part in query.split("&"):
                if "=" in part:
                    key, value = part.split("=", 1)
                    params[key] = value
            try:
                data = self.server.store.compare(params.get("left"), params.get("right"))
            except EmpireOpsStoreError as exc:
                self._json_error(400, "comparison_blocked", str(exc))
                return
            self._json(200, {"ok": True, "data": data})
            return
        self._json_error(404, "not_found", "Route not found.")

    def do_POST(self) -> None:
        if not self._allowed_request():
            return
        path = urlsplit(self.path).path
        if path == "/api/runs":
            try:
                body = self._read_json()
                request = body.get("request")
                if not isinstance(request, dict):
                    raise EmpireOpsServerError("request must be an object")
                payload = run_preview(request)
                saved = self.server.store.save(
                    run_id=body.get("run_id"),
                    label=body.get("label"),
                    request=request,
                    result=payload["result"],
                    report=payload["report"],
                )
            except EmpireOpsServerError as exc:
                self._json_error(400, "invalid_request", str(exc))
                return
            except EmpireOpsStoreError as exc:
                self._json_error(409, "save_conflict", str(exc))
                return
            except (EmpireBusinessError, EmpireSourceProductError, OSError, ValueError) as exc:
                self._json_error(409, "preview_blocked", str(exc))
                return
            self._json(201, {"ok": True, "data": saved})
            return
        if path != "/api/preview":
            self._json_error(404, "not_found", "Route not found.")
            return
        try:
            request = self._read_json()
            payload = run_preview(request)
        except EmpireOpsServerError as exc:
            self._json_error(400, "invalid_request", str(exc))
            return
        except (EmpireBusinessError, EmpireSourceProductError, OSError, ValueError) as exc:
            self._json_error(409, "preview_blocked", str(exc))
            return
        self._json(200, {"ok": True, "data": payload})


def create_server(
    *,
    host: str = LOOPBACK_HOST,
    port: int = 0,
    census_path: Path = DEFAULT_CENSUS,
    app_html: str = APP_HTML,
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
    store_path: Path = DEFAULT_STORE_PATH,
) -> EmpireOpsHTTPServer:
    codespaces = os.environ.get("CODESPACES") == "true"
    if host != LOOPBACK_HOST and not (codespaces and host == CODESPACES_HOST):
        raise EmpireOpsServerError(
            "the Empire operator may bind 0.0.0.0 only inside GitHub Codespaces; "
            "local runs remain loopback-only"
        )
    if not 0 <= port <= 65535:
        raise EmpireOpsServerError("port must be 0..65535")
    if max_body_bytes <= 0:
        raise EmpireOpsServerError("max_body_bytes must be positive")
    return EmpireOpsHTTPServer(
        (host, port),
        app_html=app_html,
        max_body_bytes=max_body_bytes,
        census_path=census_path,
        store_path=store_path,
    )


class RunningEmpireOpsServer:
    def __init__(self, server: EmpireOpsHTTPServer, thread: threading.Thread) -> None:
        self.server = server
        self.thread = thread
        self._closed = False

    @property
    def port(self) -> int:
        return self.server.port

    @property
    def base_url(self) -> str:
        return self.server.base_url

    def close(self) -> None:
        if self._closed:
            return
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self._closed = True

    def __enter__(self) -> "RunningEmpireOpsServer":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def start_server(**options: object) -> RunningEmpireOpsServer:
    server = create_server(**options)  # type: ignore[arg-type]
    thread = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.05},
        name=f"baen-empire-ops-{server.port}",
        daemon=True,
    )
    thread.start()
    return RunningEmpireOpsServer(server, thread)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="baen-empire-ops",
        description=(
            "Run the Baen Empire economy application. Local use binds to 127.0.0.1; "
            "GitHub Codespaces may bind 0.0.0.0 behind its authenticated private port. "
            "The app cannot write Notion, post the canonical ledger, or advance campaign time."
        ),
    )
    parser.add_argument("--port", type=int, default=0, help="local port; 0 chooses a free port")
    parser.add_argument("--host", default=LOOPBACK_HOST, help="127.0.0.1 locally; 0.0.0.0 only in Codespaces")
    parser.add_argument("--census", type=Path, default=DEFAULT_CENSUS)
    parser.add_argument("--database", "--store", dest="store", type=Path, default=DEFAULT_STORE_PATH)
    parser.add_argument("--open", action="store_true", help="open the app in the default browser")
    parser.add_argument("--max-body-bytes", type=int, default=DEFAULT_MAX_BODY_BYTES)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        server = create_server(
            host=args.host,
            port=args.port,
            census_path=args.census,
            max_body_bytes=args.max_body_bytes,
            store_path=args.store,
        )
    except (EmpireOpsServerError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Baen Economy Engine app: {server.base_url}", flush=True)
    print(
        "Preview-only — Notion writes: 0; canonical ledger postings: 0; campaign time advance: 0",
        flush=True,
    )
    if args.open and not webbrowser.open(server.base_url, new=2):
        print(f"Open {server.base_url} in a browser.", file=sys.stderr, flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
