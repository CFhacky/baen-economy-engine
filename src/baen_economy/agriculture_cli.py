"""Build and open the offline Baen agriculture workbench."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Mapping, Sequence
import webbrowser

from .agriculture_report import write_agriculture_workbench_html
from .agriculture_source import load_agriculture_canon as validate_agriculture_canon


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = PROJECT_ROOT / "fixtures" / "agriculture" / "agriculture-canon-v1.json"
DEFAULT_REPORT = PROJECT_ROOT / "reports" / "Baen-Agriculture-Workbench.html"


class AgricultureWorkbenchError(ValueError):
    """The source fixture cannot safely drive the workbench."""


def load_agriculture_canon(path: Path = DEFAULT_SOURCE) -> Mapping[str, object]:
    source = path.expanduser().resolve()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AgricultureWorkbenchError(f"invalid agriculture JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise AgricultureWorkbenchError("agriculture fixture must contain a JSON object")
    if payload.get("schema") != "tnp.economy.agriculture-canon/1":
        raise AgricultureWorkbenchError(
            "unsupported agriculture fixture schema; expected "
            "tnp.economy.agriculture-canon/1"
        )
    required = {
        "sources",
        "registry_entities",
        "current_actual_state",
        "forward_k1495_state",
        "species",
        "crop_program",
        "known_conflicts",
        "unresolved_inputs",
    }
    missing = sorted(required - payload.keys())
    if missing:
        raise AgricultureWorkbenchError(
            "agriculture fixture is missing required fields: " + ", ".join(missing)
        )
    # The typed source loader fails closed on floats, unsafe side effects,
    # timeline promotion, broken source links, and physical-total drift.  The
    # raw mapping is retained only because the HTML also renders additive,
    # source-linked sections that are deliberately outside the v1 typed core.
    validate_agriculture_canon(source)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="baen-agriculture",
        description=(
            "Build or open the read-only, offline Baen agriculture workbench. "
            "This command writes nothing to Notion and advances no campaign time."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("build", "build the self-contained HTML workbench"),
        ("open", "rebuild and open the self-contained HTML workbench"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
        command.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = load_agriculture_canon(args.source)
        report = write_agriculture_workbench_html(payload, args.output)
        print(f"Baen agriculture workbench built: {report}")
        print("Current actual remains frozen; Notion writes: 0; campaign advance: 0")
        if args.command == "open":
            opened = webbrowser.open(report.as_uri(), new=2)
            if not opened:
                raise AgricultureWorkbenchError(
                    f"the browser did not accept the report; open it manually: {report}"
                )
            print(f"Opened in your browser: {report}")
        return 0
    except (AgricultureWorkbenchError, OSError, TypeError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
