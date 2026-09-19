#!/usr/bin/env python3
"""Execute the complete non-canonical Empire preview with all product runtimes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from baen_economy.empire_orchestrator import render_empire_month, run_empire_month


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", default="empire-e2e-ci")
    parser.add_argument("--json-output", type=Path, default=PROJECT / "reports/Empire-E2E-Preview.json")
    parser.add_argument("--report-output", type=Path, default=PROJECT / "reports/Empire-E2E-Preview.md")
    args = parser.parse_args()

    payload = run_empire_month(seed=args.seed, require_products=True)
    required = {"mesa", "brunnfeld", "unknown_horizons", "freecol", "veloren", "openttd"}
    if set(payload["products"]) != required:
        raise SystemExit("product result set is incomplete")
    unavailable = {name: row for name, row in payload["products"].items() if row.get("status") == "UNAVAILABLE"}
    if unavailable:
        raise SystemExit("upstream product unavailable: " + json.dumps(unavailable, sort_keys=True))
    checks = payload["integrity"]
    required_checks = (
        "physical_conservation",
        "nonnegative_balances",
        "ledger_balanced",
        "deposit_liabilities_reconcile",
        "interest_receivables_reconcile",
        "collateral_assets_reconcile",
        "bank_balance_sheets_balance",
    )
    failed = [name for name in required_checks if not checks.get(name)]
    if failed:
        raise SystemExit("Baen whole-economy integrity failed: " + ", ".join(failed))
    if payload["canonical"] or payload["campaign_time_advanced"] or payload["notion_writes"]:
        raise SystemExit("preview crossed canonical safety boundary")

    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n", encoding="utf-8")
    args.report_output.write_text(render_empire_month(payload), encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "schema": payload["schema"],
        "scenario_id": payload["scenario_id"],
        "source_overrides": payload["source_overrides"],
        "blocker_count": len(payload["blockers"]),
        "product_status": {name: row["status"] for name, row in payload["products"].items()},
        "production_receipts": len(payload["baen_core"].get("production", [])),
        "trade_receipts": len(payload["baen_core"].get("trade", [])),
        "banking_receipts": len(payload["baen_core"].get("banking", [])),
        "migration_receipts": len(payload["baen_core"].get("migration", [])),
        "json_output": str(args.json_output),
        "report_output": str(args.report_output),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
