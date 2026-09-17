"""Command-line entry point for the verified food source baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from .food_baseline import (
    DEFAULT_EXTRACTION_PATH,
    DEFAULT_LADEN_PATH,
    DEFAULT_PAGE_SNAPSHOT_PATH,
    DEFAULT_REGISTRY_PATH,
    FoodBaselineError,
    load_food_source_baseline,
)
from .food_report import write_food_baseline_html


DEFAULT_REPORT = (
    Path(__file__).resolve().parents[2]
    / "reports"
    / "Baen-Food-Source-Baseline.html"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="baen-food",
        description=(
            "Verify and open the source-truth Baen food baseline. "
            "This command rolls no dice and writes nothing to Notion."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    report = commands.add_parser("report", help="create the readable HTML baseline")
    report.add_argument("output", type=Path, nargs="?", default=DEFAULT_REPORT)
    report.add_argument("--json-output", type=Path)
    report.add_argument("--format", choices=("summary", "json"), default="summary")
    verify = commands.add_parser("verify", help="verify all source bindings")
    verify.add_argument("--format", choices=("summary", "json"), default="summary")
    for command in (report, verify):
        command.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
        command.add_argument(
            "--page-snapshot", type=Path, default=DEFAULT_PAGE_SNAPSHOT_PATH
        )
        command.add_argument("--extraction", type=Path, default=DEFAULT_EXTRACTION_PATH)
        command.add_argument("--laden", type=Path, default=DEFAULT_LADEN_PATH)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = load_food_source_baseline(
            registry_path=args.registry,
            page_snapshot_path=args.page_snapshot,
            extraction_path=args.extraction,
            laden_path=args.laden,
        )
        if args.command == "report":
            output = write_food_baseline_html(payload, args.output)
            if args.json_output:
                args.json_output.parent.mkdir(parents=True, exist_ok=True)
                args.json_output.write_text(
                    json.dumps(payload, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            result = dict(payload)
            result["html_report_path"] = str(output)
        else:
            result = payload
        if args.format == "json":
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            coverage = payload["coverage"]
            totals = payload["commercial_food_baseline"]
            print("BAEN FOOD SOURCE BASELINE: VERIFIED")
            print(
                f"Source coverage: {coverage['registry_property_rows']}/90 rows, "
                f"{coverage['registry_page_bodies']}/90 page bodies, "
                f"{coverage['food_rows']}/7 food records"
            )
            print(
                f"Last-known commercial envelope: {totals['employees']} employees; "
                f"{totals['monthly_revenue_gp']} gp revenue; "
                f"{totals['monthly_cost_gp']} gp cost; "
                f"{totals['monthly_net_gp']} gp net"
            )
            print("Physical execution: BLOCKED — missing values remain UNKNOWN")
            print("Notion writes: 0 | Canonical ledger postings: 0 | Dice rolled: 0")
            if args.command == "report":
                print(f"Readable report: {output}")
        return 0
    except (FoodBaselineError, OSError, ValueError, TypeError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

