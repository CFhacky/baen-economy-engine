"""One-command operator for the standalone Baen Economy Engine.

This surface is intentionally useful before canonical month execution is open.
It combines the current persisted source census with the source-bound Registry
business preview and reports upstream-product readiness without pretending that
an unmapped product result is campaign state.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from .http_api import run_named_previews, run_registry_preview
from .mesa_runtime import mesa_available
from .empire_orchestrator import (
    DEFAULT_CENSUS as DEFAULT_EXECUTION_CENSUS,
    DEFAULT_SCENARIO,
    EmpireRunError,
    render_empire_month,
    run_empire_month,
)
from .product_stack import ProductStackError, product_environment
from .empire_operations import (
    EmpireBusinessError,
    render_empire_business_report,
    run_empire_business_turn,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CENSUS = (
    PROJECT_ROOT
    / "recovery"
    / "LIVE_EMPIRE_SOURCE_CENSUS_EXECUTION_SNAPSHOT_2026-09-17.json"
)

PRODUCTS = (
    {
        "name": "Mesa",
        "boundary": "direct Python library",
        "mapping": "event scheduling/data collection",
        "status": "runtime-integrated; Empire semantic mapping incomplete",
    },
    {
        "name": "Brunnfeld Agentic World",
        "boundary": "HTTP sidecar service",
        "mapping": "agent/market state",
        "status": "runtime-integrated; Empire semantic mapping incomplete",
    },
    {
        "name": "Unknown Horizons",
        "boundary": "separate pinned Python product process",
        "mapping": "production lines/chains",
        "status": "runtime-integrated; Empire semantic mapping incomplete",
    },
    {
        "name": "FreeCol",
        "boundary": "JVM product harness",
        "mapping": "actual-versus-maximum production",
        "status": "runtime-integrated; Empire semantic mapping incomplete",
    },
    {
        "name": "Veloren",
        "boundary": "pinned GPL-side Rust adapter",
        "mapping": "settlement economy/stocks/prices",
        "status": "runtime-integrated; Empire semantic mapping incomplete",
    },
    {
        "name": "OpenTTD",
        "boundary": "headless dedicated server/admin API",
        "mapping": "transport/company economy telemetry",
        "status": "runtime-integrated; Empire semantic mapping incomplete",
    },
)


class EmpireOperatorError(ValueError):
    pass


def _load_census(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EmpireOperatorError(f"cannot read current census: {path}: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("meta"), dict):
        raise EmpireOperatorError("current census has no meta object")
    if not isinstance(payload.get("collections"), list):
        raise EmpireOperatorError("current census has no collections array")
    return payload


def census_status(path: Path = DEFAULT_CENSUS) -> dict[str, Any]:
    payload = _load_census(path)
    meta = payload["meta"]
    collections = []
    for row in payload["collections"]:
        if not isinstance(row, dict):
            continue
        collections.append(
            {
                "key": row.get("key"),
                "current_live_rows": row.get("rowCount"),
                "retained_captured_rows": row.get("captured"),
                "complete": bool(row.get("complete")),
            }
        )
    current_live = sum(
        int(row["current_live_rows"])
        for row in collections
        if isinstance(row.get("current_live_rows"), int)
    )
    return {
        "schema": "tnp.economy.empire-status/1",
        "campaign_boundary": meta.get("campaignBoundary"),
        "current_live_records": current_live,
        "retained_core_records": meta.get("materializedCore"),
        "stored_records": meta.get("storedRecords"),
        "simulated_records": meta.get("simulated"),
        "canonical_month": "BLOCKED" if int(meta.get("simulated") or 0) == 0 else "UNKNOWN",
        "coverage": meta.get("coverageCore", {}),
        "collections": collections,
        "next_source_batches": meta.get("nextBatch", []),
        "notion_writes": 0,
        "campaign_time_advanced": False,
    }


def _money(value: object) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise EmpireOperatorError(f"preview returned invalid money value: {value!r}") from exc


def _preview_summary(preview: dict[str, Any]) -> dict[str, Any]:
    rows = preview.get("rows")
    if not isinstance(rows, list):
        raise EmpireOperatorError("registry preview returned no rows")
    total_revenue = Decimal("0")
    total_cost = Decimal("0")
    total_net = Decimal("0")
    ranked: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        entity = row.get("entity")
        financials = row.get("financials")
        if not isinstance(entity, dict) or not isinstance(financials, dict):
            continue
        revenue = _money(financials.get("proposed_revenue"))
        cost = _money(financials.get("proposed_cost"))
        net = _money(financials.get("proposed_net"))
        total_revenue += revenue
        total_cost += cost
        total_net += net
        ranked.append(
            {
                "entity": entity.get("name"),
                "sector": entity.get("sector"),
                "status": entity.get("status"),
                "proposed_revenue_gp": format(revenue, "f"),
                "proposed_cost_gp": format(cost, "f"),
                "proposed_net_gp": format(net, "f"),
            }
        )
    ranked.sort(key=lambda item: _money(item["proposed_net_gp"]), reverse=True)
    return {
        "resolved_businesses": len(ranked),
        "skipped_businesses": len(preview.get("skipped") or []),
        "proposed_revenue_gp": format(total_revenue, "f"),
        "proposed_cost_gp": format(total_cost, "f"),
        "proposed_net_gp": format(total_net, "f"),
        "top_positive": ranked[:10],
        "top_negative": list(reversed(ranked[-10:])),
    }


def empire_preview(
    *,
    seed: str,
    month: str,
    market: str = "stable",
    entity: str | None = None,
    census_path: Path = DEFAULT_CENSUS,
) -> dict[str, Any]:
    if not seed.strip():
        raise EmpireOperatorError("seed is required")
    if not month.strip():
        raise EmpireOperatorError("month label is required")
    status = census_status(census_path)
    if entity:
        preview = run_named_previews(
            (entity,), seed=seed, month_label=month, market=market
        )
    else:
        preview = run_registry_preview(seed=seed, month_label=month, market=market)
    summary = _preview_summary(preview)
    return {
        "schema": "tnp.economy.empire-preview/1",
        "mode": "PREVIEW",
        "canonical": False,
        "campaign_boundary": status["campaign_boundary"],
        "campaign_time_advanced": False,
        "notion_writes": 0,
        "seed": seed,
        "month_label": month,
        "market": market,
        "source_state": {
            "current_live_records": status["current_live_records"],
            "retained_core_records": status["retained_core_records"],
            "stored_records": status["stored_records"],
            "simulated_records": status["simulated_records"],
            "canonical_month": status["canonical_month"],
        },
        "business_preview": summary,
        "skipped_businesses": preview.get("skipped", []),
        "upstream_products": [
            {
                **item,
                "available_here": (
                    mesa_available() if item["name"] == "Mesa" else None
                ),
            }
            for item in PRODUCTS
        ],
        "important_limit": (
            "This command is useful now, but it does not yet route each Empire "
            "source class through every upstream product. Runtime integration and "
            "semantic source mapping are separate gates."
        ),
    }


def product_status() -> dict[str, Any]:
    return {
        "schema": "tnp.economy.empire-products/1",
        "products": [
            {
                **item,
                "available_here": (
                    mesa_available() if item["name"] == "Mesa" else None
                ),
            }
            for item in PRODUCTS
        ],
        "meaning": (
            "runtime-integrated means the actual upstream product has a tested "
            "execution boundary; it does not mean campaign source fields have "
            "all been mapped into that product."
        ),
    }


def render_report(payload: dict[str, Any]) -> str:
    state = payload["source_state"]
    business = payload["business_preview"]
    lines = [
        f"# Baen Empire Economy — {payload['month_label']} (PREVIEW — NOT CANON)",
        "",
        f"Campaign boundary: **{payload['campaign_boundary']}**.",
        "Campaign time advanced: **NO**. Notion writes: **0**.",
        "",
        "## Source state",
        "",
        f"- Current live source rows: **{state['current_live_records']}**",
        f"- Retained core source rows: **{state['retained_core_records']}**",
        f"- Total stored records: **{state['stored_records']}**",
        f"- Certified SIMULATED rows: **{state['simulated_records']}**",
        f"- Canonical month: **{state['canonical_month']}**",
        "",
        "## Business preview",
        "",
        f"- Businesses resolved: **{business['resolved_businesses']}**",
        f"- Businesses skipped: **{business['skipped_businesses']}**",
        f"- Proposed revenue: **{business['proposed_revenue_gp']} gp**",
        f"- Proposed cost: **{business['proposed_cost_gp']} gp**",
        f"- Proposed net: **{business['proposed_net_gp']} gp**",
        "",
        "### Largest positive previews",
        "",
    ]
    for row in business["top_positive"][:10]:
        lines.append(
            f"- **{row['entity']}** ({row['sector']}): {row['proposed_net_gp']} gp net"
        )
    lines.extend(["", "### Largest negative previews", ""])
    for row in business["top_negative"][:10]:
        lines.append(
            f"- **{row['entity']}** ({row['sector']}): {row['proposed_net_gp']} gp net"
        )
    lines.extend(
        [
            "",
            "## Upstream product state",
            "",
        ]
    )
    for item in payload["upstream_products"]:
        lines.append(
            f"- **{item['name']}** — {item['boundary']}; {item['status']}."
        )
    lines.extend(
        [
            "",
            "## What this result does *not* claim",
            "",
            "- It is not a canonical campaign month.",
            "- It does not infer missing opening cash, labour, stock, or reserve authority.",
            "- It does not call an upstream product merely to manufacture a result where no source mapping exists.",
            "- The six upstream runtimes are integrated; source-to-product semantic mapping remains the next engineering layer.",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="baen-empire",
        description="One-command Baen Empire economy operator. Preview only; never writes Notion or advances campaign time.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    status = sub.add_parser("status", help="show the current live census and canonical gate")
    status.add_argument("--census", type=Path, default=DEFAULT_CENSUS)

    products = sub.add_parser("products", help="show actual upstream product boundaries and mapping state")
    products.add_argument("--format", choices=("summary", "json"), default="summary")

    run = sub.add_parser(
        "run",
        help="run the source-grounded Hammer-1495 Empire monthly business phase",
    )
    run.add_argument("--seed", required=True)
    run.add_argument(
        "--month",
        default="Day 7 Hammer 1495 DR — monthly preview",
        help="label for the deterministic review artifact; does not advance campaign time",
    )
    run.add_argument(
        "--market",
        choices=("unknown", "stable", "boom", "recession"),
        default="unknown",
        help="optional user-ruling for this preview; unknown applies no market modifier",
    )
    run.add_argument(
        "--vara-active",
        action="store_true",
        help="apply the explicit +3 Vara-active modifier for this preview",
    )
    run.add_argument("--format", choices=("json", "report"), default="report")

    sandbox = sub.add_parser(
        "sandbox",
        help="run the synthetic whole-economy scenario for engine testing only",
    )
    sandbox.add_argument("--seed", required=True)
    sandbox.add_argument("--scenario", type=Path, default=DEFAULT_SCENARIO)
    sandbox.add_argument("--census", type=Path, default=DEFAULT_EXECUTION_CENSUS)
    sandbox.add_argument("--format", choices=("json", "report"), default="report")
    sandbox.add_argument(
        "--no-prepare-products",
        dest="prepare_products",
        action="store_false",
        help="use already configured product checkouts/services instead of acquiring/starting them",
    )
    sandbox.set_defaults(prepare_products=True)
    sandbox.add_argument(
        "--product-root",
        type=Path,
        default=Path(".upstream/baen-product-stack"),
        help="persistent cache for pinned upstream product checkouts/builds",
    )
    sandbox.add_argument("--openttd-baseset", type=Path)
    sandbox.add_argument("--build-jobs", type=int, default=2)

    preview = sub.add_parser("preview", help="run one coherent non-canonical Empire business preview")
    preview.add_argument("--seed", required=True)
    preview.add_argument("--month", required=True)
    preview.add_argument("--market", choices=("boom", "stable", "recession"), default="stable")
    preview.add_argument("--entity", help="optional exact Registry business title; omit for all Registry businesses")
    preview.add_argument("--census", type=Path, default=DEFAULT_CENSUS)
    preview.add_argument("--format", choices=("summary", "json", "report"), default="report")
    return parser


def _json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False))


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "status":
            payload = census_status(args.census)
            _json(payload)
            return 0
        if args.command == "products":
            payload = product_status()
            if args.format == "json":
                _json(payload)
            else:
                print("UPSTREAM PRODUCT RUNTIMES")
                for item in payload["products"]:
                    print(f"- {item['name']}: {item['boundary']} — {item['status']}")
            return 0
        if args.command == "run":
            payload = run_empire_business_turn(
                seed=args.seed,
                month_label=args.month,
                market_condition=args.market,
                vara_active=args.vara_active,
            )
            if args.format == "json":
                _json(payload)
            else:
                print(render_empire_business_report(payload))
            return 0
        if args.command == "sandbox":
            if args.prepare_products:
                with product_environment(
                    args.product_root,
                    openttd_baseset=args.openttd_baseset,
                    build_jobs=args.build_jobs,
                ):
                    payload = run_empire_month(
                        seed=args.seed,
                        census_path=args.census,
                        scenario_path=args.scenario,
                        require_products=True,
                        allow_synthetic_scenario=True,
                    )
            else:
                payload = run_empire_month(
                    seed=args.seed,
                    census_path=args.census,
                    scenario_path=args.scenario,
                    require_products=False,
                    allow_synthetic_scenario=True,
                )
            if args.format == "json":
                _json(payload)
            else:
                print(render_empire_month(payload))
            return 0
        if args.command == "preview":
            payload = empire_preview(
                seed=args.seed,
                month=args.month,
                market=args.market,
                entity=args.entity,
                census_path=args.census,
            )
            if args.format == "json":
                _json(payload)
            elif args.format == "summary":
                business = payload["business_preview"]
                print("BAEN EMPIRE PREVIEW — NOT CANON")
                print(f"Boundary: {payload['campaign_boundary']}")
                print(
                    f"Businesses: {business['resolved_businesses']} resolved / "
                    f"{business['skipped_businesses']} skipped"
                )
                print(
                    f"Revenue {business['proposed_revenue_gp']} gp | "
                    f"Cost {business['proposed_cost_gp']} gp | "
                    f"Net {business['proposed_net_gp']} gp"
                )
                print("Notion writes: 0 | Campaign time advanced: NO")
            else:
                print(render_report(payload))
            return 0
        raise EmpireOperatorError("unknown command")
    except (
        EmpireOperatorError,
        EmpireBusinessError,
        EmpireRunError,
        ProductStackError,
        OSError,
        ValueError,
        TypeError,
        KeyError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
