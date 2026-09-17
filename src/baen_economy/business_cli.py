"""CLI for the source-bound Registry business-preview sidecar."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import sqlite3
import sys
from typing import Mapping, Sequence

from .banking_sandbox import build_positive_banking_sandbox
from .business_capacity import (
    BRICKWORKS_SOURCE_RECORD_ID,
    build_brickworks_partial_capacity,
)
from .business_month import (
    BUSINESS_PROFILE_ID,
    BusinessMonthError,
    find_source_record_id,
    preview_business_month,
    render_business_report,
)
from .business_store import ArtifactValue, BusinessStore, BusinessStoreError
from .operator_codec import json_safe
from .registry_export import RegistryExportError, export_summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="baen-business",
        description=(
            "Persist and inspect source-bound business PREVIEWS. The command has no "
            "Notion write, ledger post, accept-canon, or apply operation."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser(
        "init", help="create an append-only preview database and import one Registry receipt"
    )
    init.add_argument("database", type=Path)
    init.add_argument("registry_export", type=Path)

    registry_import = commands.add_parser(
        "registry-import", help="verify and append another offline Registry receipt"
    )
    registry_import.add_argument("database", type=Path)
    registry_import.add_argument("registry_export", type=Path)

    status = commands.add_parser("status", help="show counts and read/write capability flags")
    status.add_argument("database", type=Path)

    run = commands.add_parser(
        "run-month", help="calculate one entity preview; omit --commit for zero local writes"
    )
    run.add_argument("database", type=Path)
    run.add_argument("--entity", required=True, help="exact case-sensitive Registry title")
    run.add_argument("--month", required=True, help="scenario label; campaign time is not advanced")
    run.add_argument(
        "--seed",
        required=True,
        help=(
            "deterministic replay seed; visible in process arguments and not "
            "persisted raw"
        ),
    )
    run.add_argument("--registry-export-hash", help="use an exact stored export; defaults to latest")
    run.add_argument("--market", choices=("boom", "stable", "recession"), default="stable")
    run.add_argument("--vara-inactive", action="store_true")
    run.add_argument("--revenue-streams", type=_positive_int, default=1)
    run.add_argument("--competent-managers", type=_manager_count, default=0)
    run.add_argument("--monopoly", action="store_true")
    run.add_argument("--excellent-accounting", action="store_true")
    run.add_argument("--rapid-expansion", action="store_true")
    run.add_argument(
        "--commit",
        action="store_true",
        help="append this local non-canonical preview bundle; still writes neither Notion nor ledger",
    )
    run.add_argument("--format", choices=("summary", "json", "report"), default="summary")

    for name, help_text in (
        ("report", "render a stored business report"),
        ("notion-dry-run", "show a stored non-executable, source-bound Notion diff"),
        ("ledger-preview", "show a stored zero-transaction business ledger preview"),
        ("capacity-profile", "show a stored partial capacity profile when available"),
    ):
        item = commands.add_parser(name, help=help_text)
        item.add_argument("database", type=Path)
        item.add_argument("--run", dest="run_hash", help="stored run hash; defaults to latest")

    verify = commands.add_parser(
        "verify", help="verify SQLite, append-only guards, source rows, hashes, and artifacts"
    )
    verify.add_argument("database", type=Path)

    banking = commands.add_parser(
        "banking-sandbox",
        help="render the fixed synthetic 3-transaction positive banking proposal",
    )
    banking.add_argument("--format", choices=("summary", "json"), default="summary")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            with BusinessStore.create_from_export(
                args.database, args.registry_export
            ) as store:
                verified = store.latest_registry_export()
                payload = {
                    "schema": "tnp.business.cli-init/1",
                    "database": str(store.path),
                    "registry": export_summary(verified),
                    "store": store.verify(),
                    "next_command": (
                        f"baen-business run-month {shlex.quote(str(store.path))} "
                        "--entity 'Baen Brickworks' "
                        "--month 'Eleint 1494 preview' --seed choose-a-replay-seed"
                    ),
                }
            _print_json(payload)
            return 0
        if args.command == "registry-import":
            with BusinessStore.open(args.database) as store:
                summary, replayed = store.import_registry_path(args.registry_export)
                summary["replayed_existing_import"] = replayed
                summary["store"] = store.verify()
            _print_json(summary)
            return 0
        if args.command == "status":
            with BusinessStore.open(args.database) as store:
                payload = store.verify()
                payload["database"] = str(store.path)
                payload["counts"] = store.counts()
                try:
                    latest = store.latest_run()
                except BusinessStoreError:
                    payload["latest_run"] = None
                else:
                    payload["latest_run"] = {
                        "run_hash": latest["run_hash"],
                        "entity": latest["result"].get("entity", {}).get("name"),
                        "period_key": latest["period_key"],
                    }
            _print_json(payload)
            return 0
        if args.command == "run-month":
            return _run_month(args)
        if args.command in {
            "report",
            "notion-dry-run",
            "ledger-preview",
            "capacity-profile",
        }:
            with BusinessStore.open(args.database) as store:
                stored = (
                    store.load_run(args.run_hash)
                    if args.run_hash
                    else store.latest_run()
                )
                kind = {
                    "report": "report_markdown",
                    "notion-dry-run": "notion_review_diff",
                    "ledger-preview": "ledger_preview",
                    "capacity-profile": "capacity_profile",
                }[args.command]
                try:
                    artifact = stored["artifacts"][kind]
                except KeyError as exc:
                    raise BusinessStoreError(
                        f"stored run has no {kind.replace('_', ' ')} artifact"
                    ) from exc
            print(artifact["payload"], end="" if artifact["payload"].endswith("\n") else "\n")
            return 0
        if args.command == "verify":
            with BusinessStore.open(args.database) as store:
                _print_json(store.verify())
            return 0
        if args.command == "banking-sandbox":
            payload = build_positive_banking_sandbox()
            if args.format == "json":
                _print_json(payload)
            else:
                print("SYNTHETIC / NON-CANONICAL / NON-POSTABLE BANKING SANDBOX")
                print(
                    f"Proposed: {payload['proposal_transaction_count']} transactions / "
                    f"{payload['proposal_posting_count']} postings"
                )
                print(
                    f"Posted: {payload['posted_transaction_count']} transactions / "
                    f"{payload['posted_posting_count']} postings"
                )
                print(f"Content hash: {payload['content_hash']}")
            return 0
        parser.error("unknown command")
    except (
        BusinessMonthError,
        BusinessStoreError,
        RegistryExportError,
        sqlite3.Error,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _run_month(args: argparse.Namespace) -> int:
    with BusinessStore.open(args.database) as store:
        export = (
            store.load_registry_export(args.registry_export_hash)
            if args.registry_export_hash
            else store.latest_registry_export()
        )
        source_record_id = find_source_record_id(export, args.entity)
        result = preview_business_month(
            export,
            source_record_id,
            args.month,
            args.seed,
            market=args.market,
            vara_active=not args.vara_inactive,
            revenue_streams=args.revenue_streams,
            competent_managers=args.competent_managers,
            monopoly=args.monopoly,
            excellent_accounting=args.excellent_accounting,
            rapid_expansion=args.rapid_expansion,
        )
        report = render_business_report(result)
        artifacts: dict[str, object] = {
            "report_markdown": ArtifactValue(
                "text/markdown; charset=utf-8", report
            ),
            "notion_review_diff": result["notion_review_diff"],
            "ledger_preview": result["ledger_preview"],
            "dice_manifest": result["dice_manifest"],
        }
        if source_record_id == BRICKWORKS_SOURCE_RECORD_ID:
            artifacts["capacity_profile"] = build_brickworks_partial_capacity(
                export
            ).to_dict()
        stored: Mapping[str, object] | None = None
        replayed = False
        if args.commit:
            assumptions = dict(result["assumptions"])
            request = {
                "month_label": args.month,
                "seed_fingerprint": hashlib.sha256(
                    args.seed.encode("utf-8")
                ).hexdigest(),
                "assumptions": assumptions,
                "raw_seed_persisted": False,
            }
            stored, replayed = store.commit_run(
                registry_export_hash=export.export_hash,
                source_record_id=source_record_id,
                profile_id=BUSINESS_PROFILE_ID,
                period_key=args.month,
                request=request,
                result=result,
                artifacts=artifacts,
            )

        envelope = {
            "schema": "tnp.business.cli-run/1",
            "committed_locally": args.commit,
            "replayed_existing_commit": replayed,
            "database": str(store.path),
            "store_run_hash": stored["run_hash"] if stored else None,
            "preview": result,
        }
    if args.format == "json":
        _print_json(envelope)
    elif args.format == "report":
        print(report, end="")
    else:
        financials = result["financials"]
        print("PREVIEW — NOT CANON — ZERO NOTION WRITES — ZERO LEDGER POSTINGS")
        print(
            "Persistence: "
            + ("COMMITTED LOCALLY" if args.commit else "DRY RUN — NOT SAVED")
            + (" (exact retry)" if replayed else "")
        )
        print(f"Entity: {result['entity']['name']} | Scenario month: {args.month}")
        print(
            f"Revenue {financials['proposed_revenue']} GP; cost "
            f"{financials['proposed_cost']} GP; net {financials['proposed_net']} GP."
        )
        if stored:
            print(f"Stored run: {stored['run_hash']}")
        else:
            print("Add --commit to persist this local preview bundle.")
    return 0


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a positive integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def _manager_count(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("manager count must be 0 through 3") from exc
    if not 0 <= parsed <= 3:
        raise argparse.ArgumentTypeError("manager count must be 0 through 3")
    return parsed


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


if __name__ == "__main__":
    raise SystemExit(main())
