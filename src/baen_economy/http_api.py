"""Stdlib HTTP JSON API for other apps. Zero Notion writes. Canonical month refused."""

from __future__ import annotations

from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .business_month import (
    BUSINESS_MONTH_SCHEMA,
    BusinessMonthError,
    find_source_record_id,
    preview_business_month,
)
from .food_baseline import EXPECTED_COMMERCIAL_TOTALS
from .registry_export import load_registry_export


API_VERSION = "0.3.0"
TICK_SCHEMA = "tnp.economy.tick-result/1"
CAMPAIGN_BOUNDARY = "Day 7 Hammer 1495 DR"
FOOD_TITLES = (
    "Converted Quarry Aquaculture (5 sites)",
    "Blacklake Aquaculture (7 pools)",
    "BG Aquaculture Pools (3 sites)",
    "Agricultural Shelter Zones",
    "Reservoir Fisheries",
)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = (
    PROJECT_ROOT / "fixtures" / "registry-snapshots" / "business-registry-2026-08-29.json"
)

_CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "content-type",
    "Cache-Control": "no-store",
}


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def coverage_payload() -> dict[str, Any]:
    return {
        "engine": "baen-economy-engine",
        "version": API_VERSION,
        "campaignBoundary": CAMPAIGN_BOUNDARY,
        "simulated": 0,
        "canonicalMonth": "refused",
        "foodEnvelope": {
            "employees": int(EXPECTED_COMMERCIAL_TOTALS["employees"]),
            "monthly_revenue_gp": str(EXPECTED_COMMERCIAL_TOTALS["monthly_revenue_gp"]),
            "monthly_cost_gp": str(EXPECTED_COMMERCIAL_TOTALS["monthly_cost_gp"]),
            "monthly_net_gp": str(EXPECTED_COMMERCIAL_TOTALS["monthly_net_gp"]),
            "asOf": "Eleint 1494 pre-crisis envelope",
        },
    }


def canonical_refused() -> dict[str, Any]:
    return {
        "schema": TICK_SCHEMA,
        "mode": "refused",
        "canonical": False,
        "kind": "canonical",
        "campaignBoundary": CAMPAIGN_BOUNDARY,
        "campaignTimeAdvanced": False,
        "simulatedCertified": 0,
        "blockers": [
            "SIMULATED=0. Coverage is closed.",
            "No live opening cash snapshot.",
            "Labour has no dedicated collection.",
            "NCF parent/branch consolidation is unresolved.",
            "PR #192 is not merged. Notion write path is absent.",
        ],
        "ledger": {"postable": False, "transaction_count": 0, "posting_count": 0},
        "notion": {"write_attempted": False, "applied_count": 0},
    }


def run_named_previews(
    titles: tuple[str, ...],
    *,
    seed: str,
    month_label: str,
    market: str = "stable",
) -> dict[str, Any]:
    export = load_registry_export(DEFAULT_REGISTRY)
    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for title in titles:
        try:
            source_id = find_source_record_id(export, title)
            preview = preview_business_month(
                export,
                source_id,
                month_label,
                seed,
                market=market,
            )
            rows.append(_jsonable(preview))
        except (BusinessMonthError, Exception) as exc:
            skipped.append({"title": title, "reason": str(exc)})
    return {
        "schema": TICK_SCHEMA,
        "mode": "preview",
        "canonical": False,
        "campaignBoundary": CAMPAIGN_BOUNDARY,
        "campaignTimeAdvanced": False,
        "simulatedCertified": 0,
        "seed": seed,
        "monthLabel": month_label,
        "resolved": len(rows),
        "rows": rows,
        "skipped": skipped,
        "ledger": {"postable": False, "transaction_count": 0, "posting_count": 0},
        "notion": {"write_attempted": False, "applied_count": 0},
        "warnings": [
            "This is a deterministic scenario preview, not campaign canon.",
            "Parent and child banking rows are not a consolidated P&L.",
            "Capital Invested is not opening cash.",
        ],
    }


def run_registry_preview(*, seed: str, month_label: str, market: str = "stable") -> dict[str, Any]:
    export = load_registry_export(DEFAULT_REGISTRY)
    titles = tuple(str(row["Entity"]) for row in export.rows_by_source_id.values())
    return run_named_previews(titles, seed=seed, month_label=month_label, market=market)


class TickHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return

    def _write(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for key, value in _CORS.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        for key, value in _CORS.items():
            self.send_header(key, value)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path in {"/", "/v1", "/v1/health"}:
            self._write(200, {"ok": True, **coverage_payload()})
            return
        if path == "/v1/coverage":
            self._write(200, coverage_payload())
            return
        if path in {"/v1/openapi.json", "/openapi.json"}:
            self._write(200, _openapi())
            return
        self._write(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path.rstrip("/")
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
            if not isinstance(body, dict):
                raise ValueError("JSON body must be an object")
        except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
            self._write(400, {"error": str(exc)})
            return
        seed = str(body.get("seed") or "preview-seed")
        market = str(body.get("market") or "stable")
        try:
            if path == "/v1/canonical":
                self._write(409, canonical_refused())
                return
            if path == "/v1/preview":
                kind = str(body.get("kind") or "food")
                if kind == "food":
                    payload = run_named_previews(
                        FOOD_TITLES,
                        seed=seed,
                        month_label=str(body.get("monthLabel") or "Eleint 1494 preview"),
                        market=market,
                    )
                    self._write(200, payload)
                    return
                if kind == "registry":
                    payload = run_registry_preview(
                        seed=seed,
                        month_label=str(body.get("monthLabel") or "Hammer 1495 non-canonical preview"),
                        market=market,
                    )
                    self._write(200, payload)
                    return
                if kind == "business":
                    title = str(body.get("entityId") or body.get("entity") or "")
                    if not title:
                        self._write(400, {"error": "entityId is required for kind=business"})
                        return
                    payload = run_named_previews(
                        (title,),
                        seed=seed,
                        month_label=str(body.get("monthLabel") or "Hammer 1495 non-canonical preview"),
                        market=market,
                    )
                    self._write(200, payload)
                    return
                self._write(400, {"error": "kind must be food, registry, or business"})
                return
            self._write(404, {"error": "not found"})
        except Exception as exc:  # noqa: BLE001
            self._write(400, {"error": str(exc)})


def _openapi() -> dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Baen Economy Engine",
            "version": API_VERSION,
            "description": "Fail-closed monthly economy tick. Preview only. Canonical months return 409.",
        },
        "paths": {
            "/v1/health": {"get": {"summary": "Liveness"}},
            "/v1/coverage": {"get": {"summary": "Coverage gate"}},
            "/v1/preview": {"post": {"summary": "Non-canonical preview month"}},
            "/v1/canonical": {"post": {"summary": "Always 409 while SIMULATED=0"}},
        },
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Baen economy tick HTTP API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), TickHandler)
    print(f"baen-tick listening on http://{args.host}:{args.port}/v1/health", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
