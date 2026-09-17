"""Command-line interface for persistent, preview-only economy operation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import sqlite3
import sys
from typing import Sequence

from .operator import (
    get_ledger_preview,
    get_notion_dry_run,
    get_report,
    initialize_campaign,
    run_month,
    status,
    verify_database,
)
from .operator_codec import CodecError, json_safe
from .operator_store import StoreError
from .scenarios import LADEN_PROFILE_ID, ScenarioError, available_scenarios
from .source_census import coverage_report, load_census_snapshot
from .stockflow import SimulationError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="baen-economy",
        description=(
            "Run a persistent medieval-economy PREVIEW. --commit saves local preview "
            "history; it never accepts canon, posts a ledger, or writes Notion."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("scenarios", help="list bundled source-backed preview scenarios")

    coverage = subparsers.add_parser(
        "coverage-check",
        help="validate a durable live-source census and report its fail-closed gate",
    )
    coverage.add_argument("snapshot", type=Path, help="source-census JSON snapshot")

    init = subparsers.add_parser("init", help="initialize a new local preview database")
    init.add_argument("database", type=Path, help="new SQLite database path")
    init.add_argument("--campaign", default="laden-low", help="local campaign workspace ID")
    init.add_argument("--scenario", default="operation-laden-table")
    init.add_argument("--profile", default=LADEN_PROFILE_ID)
    init.add_argument(
        "--mode",
        choices=("preview", "actual"),
        default="preview",
        help="actual exists only to fail closed until its authority gate is accepted",
    )

    status_parser = subparsers.add_parser(
        "status", help="show current period, hashes, and the next useful command"
    )
    status_parser.add_argument("database", type=Path)

    run = subparsers.add_parser(
        "run-month",
        help="execute the next month; omit --commit for a no-write dry run",
    )
    run.add_argument("database", type=Path)
    run.add_argument("--period", type=int, required=True)
    run.add_argument(
        "--commit",
        action="store_true",
        help="persist local PREVIEW history atomically (does not accept campaign canon)",
    )
    run.add_argument(
        "--roll-preview-checks",
        action="store_true",
        help="record two illustrative 3d6 checks with no campaign or state effect",
    )
    run.add_argument(
        "--seed",
        help=(
            "deterministic preview seed; required for a no-write dice preview so a later "
            "commit can reproduce it; fingerprint is stored, raw seed is not"
        ),
    )
    run.add_argument(
        "--format",
        choices=("summary", "json", "report"),
        default="summary",
    )

    report = subparsers.add_parser("report", help="render a stored prose-first monthly report")
    report.add_argument("database", type=Path)
    report.add_argument("--period", type=_period, default=None, help="positive integer or latest")

    ledger = subparsers.add_parser(
        "ledger-preview", help="show the stored non-postable ledger proposal"
    )
    ledger.add_argument("database", type=Path)
    ledger.add_argument("--period", type=_period, default=None, help="positive integer or latest")

    notion = subparsers.add_parser(
        "notion-dry-run", help="show the stored offline, non-executable Notion proposal"
    )
    notion.add_argument("database", type=Path)
    notion.add_argument("--period", type=_period, default=None, help="positive integer or latest")

    verify = subparsers.add_parser(
        "verify", help="verify SQLite integrity, immutable hashes, and snapshot lineage"
    )
    verify.add_argument("database", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "scenarios":
            payload = {
                "schema": "tnp.economy.scenario-list/1",
                "scenarios": [
                    {
                        "scenario_id": item.scenario_id,
                        "assumption_profile_id": item.profile_id,
                        "title": item.payload["title"],
                        "mode": "preview",
                        "canonical": False,
                        "periods": item.max_period,
                        "scenario_hash": item.scenario_hash,
                    }
                    for item in available_scenarios()
                ],
            }
            _print_json(payload)
            return 0
        if args.command == "coverage-check":
            report = coverage_report(load_census_snapshot(args.snapshot))
            _print_json(report)
            return 0 if report["gate"] == "OPEN" else 2
        if args.command == "init":
            _print_json(
                initialize_campaign(
                    args.database,
                    campaign_id=args.campaign,
                    scenario_id=args.scenario,
                    profile_id=args.profile,
                    mode=args.mode,
                )
            )
            return 0
        if args.command == "status":
            _print_json(status(args.database))
            return 0
        if args.command == "run-month":
            outcome = run_month(
                args.database,
                period_index=args.period,
                commit=args.commit,
                seed=args.seed,
                include_preview_checks=args.roll_preview_checks,
            )
            if args.format == "json":
                _print_json(outcome)
            elif args.format == "report":
                if outcome["committed"]:
                    print(get_report(args.database, args.period), end="")
                else:
                    print(outcome["report_markdown"], end="")
            else:
                _print_run_summary(outcome)
            return 0
        if args.command == "report":
            print(get_report(args.database, args.period), end="")
            return 0
        if args.command == "ledger-preview":
            print(get_ledger_preview(args.database, args.period))
            return 0
        if args.command == "notion-dry-run":
            print(get_notion_dry_run(args.database, args.period))
            return 0
        if args.command == "verify":
            _print_json(verify_database(args.database))
            return 0
        parser.error("unknown command")
    except (StoreError, ScenarioError, SimulationError, CodecError, sqlite3.Error, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _period(value: str) -> int | None:
    if value == "latest":
        return None
    try:
        result = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("period must be a positive integer or latest") from exc
    if result < 1:
        raise argparse.ArgumentTypeError("period must be a positive integer or latest")
    return result


def _print_json(payload: object) -> None:
    print(
        json.dumps(
            json_safe(payload),
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
        )
    )


def _print_run_summary(outcome: dict[str, object]) -> None:
    summary = outcome["summary"]
    persistence = "COMMITTED LOCALLY" if outcome["committed"] else "DRY RUN — NOT SAVED"
    replay = " (existing commit replayed)" if outcome["replayed_existing_commit"] else ""
    print("PREVIEW — NOT CANON — ZERO NOTION WRITES — ZERO LEDGER POSTINGS")
    print(f"Persistence: {persistence}{replay}")
    print(
        f"Period {outcome['period']['index']}: sent {summary['shipment_dispatched_tons']} t, "
        f"arrived {summary['arrived_tons']} t, lost {summary['transit_loss_tons']} t, "
        + (
            "need/consumption/shortage not modeled."
            if summary["need_status"] != "modeled"
            else (
                f"consumed {summary['consumed_tons']} t, "
                f"shortage {summary['shortage_tons']} t."
            )
        )
    )
    print(
        f"Closing: supplier {summary['closing_supplier_tons']} t; Longsaddle "
        f"{summary['closing_longsaddle_tons']} t; transit {summary['closing_transit_tons']} t."
    )
    print(f"Snapshot: {outcome['closing_snapshot_id']}")
    if outcome["committed"]:
        print(
            f"Next: baen-economy report {shlex.quote(str(outcome['database']))} "
            f"--period {outcome['period']['index']}"
        )
    else:
        print("Add --commit to save this local preview state.")


if __name__ == "__main__":
    raise SystemExit(main())
