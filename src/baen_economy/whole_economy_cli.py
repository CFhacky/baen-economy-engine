"""Append-only command line workspace for the whole-economy vertical slice.

The simulation core is deliberately stateless.  This module gives it a durable,
auditable local boundary without adding any Notion writer or canonical-ledger
adapter.  A workspace is a sealed scenario plus an immutable directory for each
committed month::

    workspace.json
    scenario.json
    months/0000/state.json
    months/0001/state.json
    months/0001/result.json
    months/0001/report.html

Every verification replays the complete history from the stored seed
fingerprint.  The raw seed is never written to disk.
"""

from __future__ import annotations

import argparse
from decimal import Decimal
from html import escape
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Mapping, Sequence

try:  # Support both ``python -m economy_impl.whole_economy_cli`` and direct use.
    from . import whole_economy as core
except ImportError:  # pragma: no cover - exercised by direct-script smoke tests.
    import whole_economy as core  # type: ignore[no-redef]


WORKSPACE_SCHEMA = "baen.whole-economy-workspace/1"
METADATA_NAME = "workspace.json"
SCENARIO_NAME = "scenario.json"
MONTHS_NAME = "months"
STATE_NAME = "state.json"
RESULT_NAME = "result.json"
REPORT_NAME = "report.html"
NOTION_WRITES = 0
CANONICAL_LEDGER_POSTINGS = 0
_MONTH_DIRECTORY = re.compile(r"^[0-9]{4}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_DECIMAL_TOKEN = re.compile(r"(?<![\w.])[-+]?\d+\.\d+(?![\w.])")
_LARGE_INTEGER_TOKEN = re.compile(r"(?<![\w:./-])[-+]?[1-9]\d{3,}(?![\w:./-])")


class WorkspaceError(ValueError):
    """Raised when persistence is incomplete, ambiguous, or has been changed."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="whole-economy",
        description=(
            "Run an append-only medieval regional-economy PREVIEW. It makes "
            "zero Notion writes and zero canonical campaign-ledger postings."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    initialize = commands.add_parser(
        "init", help="seal a scenario and create its month-zero state"
    )
    initialize.add_argument("workspace", type=Path)
    initialize.add_argument("--scenario", type=Path, required=True)
    initialize.add_argument("--seed", required=True)

    run = commands.add_parser(
        "run-month", help="simulate the next month; --commit appends it"
    )
    run.add_argument("workspace", type=Path)
    run.add_argument("--commit", action="store_true")

    report = commands.add_parser(
        "report", help="return or export a committed human-readable HTML report"
    )
    report.add_argument("workspace", type=Path)
    report.add_argument("--period", type=_positive_int)
    report.add_argument("--output", type=Path)

    boot = commands.add_parser(
        "boot",
        help=(
            "silently gate-check sealed campaign operations and surface only "
            "those matched by explicit played-canon evidence"
        ),
    )
    boot.add_argument("workspace", type=Path)
    boot.add_argument(
        "--played-context",
        type=Path,
        help=(
            "read-only structured played-canon event file; prose is never "
            "inferred and a missing file leaves dormant operations invisible"
        ),
    )

    verify = commands.add_parser(
        "verify", help="verify hashes, continuity, reports, and deterministic replay"
    )
    verify.add_argument("workspace", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            payload = initialize_workspace(
                args.workspace, scenario_path=args.scenario, seed=args.seed
            )
        elif args.command == "run-month":
            payload = run_workspace_month(args.workspace, commit=args.commit)
        elif args.command == "report":
            payload = report_workspace(
                args.workspace, period=args.period, output=args.output
            )
        elif args.command == "boot":
            played_context = (
                core.load_played_context(args.played_context)
                if args.played_context is not None
                else None
            )
            payload = boot_workspace(args.workspace, played_context=played_context)
        elif args.command == "verify":
            payload = verify_workspace(args.workspace)
        else:  # pragma: no cover - argparse enforces the command set.
            parser.error("unknown command")
            return 2
    except (WorkspaceError, core.EconomyError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.command == "boot" and payload.get("activation_matched") is False:
        # Dormant operations are intentionally invisible.  Exit successfully
        # without printing their existence, title, ID, facts, or decisions.
        return 0
    print(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))
    return 0


def initialize_workspace(
    workspace: Path,
    *,
    scenario_path: Path,
    seed: str,
) -> dict[str, object]:
    """Create a new workspace as one atomic directory rename."""

    workspace = _new_workspace_path(workspace)
    if not isinstance(seed, str) or not seed or seed != seed.strip():
        raise WorkspaceError("seed must be non-empty trimmed text")
    scenario = core.load_scenario(scenario_path.resolve())
    scenario_hash = _payload_hash(scenario)
    seed_fingerprint = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    opening_state = core.initial_state(scenario)
    _assert_state(opening_state, expected_month=0)

    metadata_body: dict[str, object] = {
        "schema": WORKSPACE_SCHEMA,
        "scenario_id": scenario["scenario_id"],
        "scenario_hash": scenario_hash,
        "opening_state_hash": opening_state["state_hash"],
        "seed_fingerprint": seed_fingerprint,
        "canonical": False,
        "notion_writes": NOTION_WRITES,
        "canonical_ledger_postings": CANONICAL_LEDGER_POSTINGS,
    }
    metadata = dict(metadata_body)
    metadata["metadata_hash"] = _payload_hash(metadata_body)

    workspace.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{workspace.name}.initializing-", dir=str(workspace.parent)
        )
    )
    try:
        months = staging / MONTHS_NAME
        month_zero = months / _month_name(0)
        month_zero.mkdir(parents=True)
        _write_new_json(staging / METADATA_NAME, metadata)
        _write_new_json(staging / SCENARIO_NAME, scenario)
        _write_new_json(month_zero / STATE_NAME, opening_state)
        if workspace.exists() or workspace.is_symlink():
            raise WorkspaceError(f"workspace already exists: {workspace}")
        staging.rename(workspace)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    return _envelope(
        "init",
        workspace,
        scenario_id=str(scenario["scenario_id"]),
        month=0,
        state_hash=str(opening_state["state_hash"]),
        seed_fingerprint=seed_fingerprint,
        initialized=True,
    )


def run_workspace_month(workspace: Path, *, commit: bool) -> dict[str, object]:
    """Resolve the next month, optionally appending one atomic month directory."""

    verified = _open_and_verify(workspace)
    scenario = verified["scenario"]
    current_state = verified["latest_state"]
    metadata = verified["metadata"]
    current_month = int(verified["latest_month"])
    next_month = current_month + 1
    bundle = core.run_month(
        scenario, current_state, str(metadata["seed_fingerprint"])
    )
    result = _mapping(bundle.get("result"), "simulation result")
    next_state = _mapping(bundle.get("next_state"), "next state")
    _assert_result(
        result,
        expected_month=next_month,
        input_state_hash=str(current_state["state_hash"]),
        next_state_hash=str(next_state.get("state_hash")),
    )
    _assert_state(next_state, expected_month=next_month)
    report_html = _render_html(result)

    state_path: Path | None = None
    result_path: Path | None = None
    report_path: Path | None = None
    if commit:
        months_path = Path(verified["workspace"]) / MONTHS_NAME
        final = months_path / _month_name(next_month)
        if final.exists() or final.is_symlink():
            raise WorkspaceError(f"refusing to overwrite committed month: {final}")
        staging = Path(
            tempfile.mkdtemp(
                prefix=f".{_month_name(next_month)}.committing-",
                dir=str(months_path),
            )
        )
        try:
            _write_new_json(staging / STATE_NAME, next_state)
            _write_new_json(staging / RESULT_NAME, result)
            _write_new_text(staging / REPORT_NAME, report_html)
            if final.exists() or final.is_symlink():
                raise WorkspaceError(f"refusing to overwrite committed month: {final}")
            staging.rename(final)
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise
        state_path = final / STATE_NAME
        result_path = final / RESULT_NAME
        report_path = final / REPORT_NAME

    return _envelope(
        "run-month",
        Path(verified["workspace"]),
        scenario_id=str(metadata["scenario_id"]),
        month=next_month,
        committed=commit,
        input_state_hash=str(result["input_state_hash"]),
        state_hash=str(next_state["state_hash"]),
        result_hash=str(result["result_hash"]),
        state_path=str(state_path) if state_path else None,
        result_path=str(result_path) if result_path else None,
        report_path=str(report_path) if report_path else None,
        event_count=len(_list(result.get("events"), "result events")),
        decision_count=len(
            _list(result.get("available_decisions"), "available decisions")
        ),
    )


def report_workspace(
    workspace: Path,
    *,
    period: int | None = None,
    output: Path | None = None,
) -> dict[str, object]:
    """Return a stored report and optionally export an exact new copy."""

    verified = _open_and_verify(workspace)
    latest_month = int(verified["latest_month"])
    if latest_month < 1:
        raise WorkspaceError("no committed month is available to report")
    selected = latest_month if period is None else period
    if selected < 1 or selected > latest_month:
        raise WorkspaceError(
            f"report period {selected} is outside committed range 1..{latest_month}"
        )
    month_path = Path(verified["workspace"]) / MONTHS_NAME / _month_name(selected)
    result = _read_canonical_json(month_path / RESULT_NAME, "monthly result")
    html = _render_html(_mapping(result, "monthly result"))
    stored_path = month_path / REPORT_NAME
    destination = stored_path
    exported = False
    if output is not None:
        candidate = output.resolve()
        if candidate.suffix.lower() not in {".html", ".htm"}:
            raise WorkspaceError("report output must end in .html or .htm")
        if _is_within(candidate, Path(verified["workspace"])) and candidate != stored_path:
            raise WorkspaceError(
                "custom reports cannot be written inside the sealed workspace"
            )
        destination = candidate
        if destination.exists() or destination.is_symlink():
            try:
                if destination.is_file() and destination.read_text(encoding="utf-8") == html:
                    exported = False
                else:
                    raise WorkspaceError(
                        f"refusing to overwrite report output: {destination}"
                    )
            except UnicodeError as exc:
                raise WorkspaceError(
                    f"refusing to overwrite non-text report output: {destination}"
                ) from exc
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            _write_new_text(destination, html)
            exported = True

    return _envelope(
        "report",
        Path(verified["workspace"]),
        scenario_id=str(verified["metadata"]["scenario_id"]),
        month=selected,
        state_hash=str(result["next_state_hash"]),
        result_hash=str(result["result_hash"]),
        report_path=str(destination),
        exported=exported,
        covers={
            "what_changed": True,
            "where": True,
            "why": True,
            "available_decisions": True,
        },
    )


def boot_workspace(
    workspace: Path,
    *,
    played_context: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Silently gate-check and surface only played-canon-activated operations."""

    verified = _open_and_verify(workspace)
    state = _mapping(verified["latest_state"], "latest state")
    sealed_operations = [
        dict(_mapping(operation, "pending operation"))
        for operation in _list(state.get("pending_operations"), "state pending operations")
    ]
    operations = core.surface_pending_operations(sealed_operations, played_context)
    fact_requests = [
        dict(_mapping(request, "pending operation fact request"))
        for operation in operations
        for request in _list(
            operation.get("required_fact_requests"),
            "pending operation fact requests",
        )
    ]
    decision_gates = [
        dict(_mapping(gate, "pending operation decision gate"))
        for operation in operations
        for gate in _list(
            operation.get("decision_gates"),
            "pending operation decision gates",
        )
    ]
    return _envelope(
        "boot",
        Path(verified["workspace"]),
        scenario_id=str(verified["metadata"]["scenario_id"]),
        latest_month=int(verified["latest_month"]),
        state_hash=str(state["state_hash"]),
        campaign_advanced=False,
        activation_matched=bool(operations),
        operation_count=len(operations),
        pending_operations=operations,
        required_fact_requests=fact_requests,
        decision_gates=decision_gates,
        execution_authorized=False,
        briefing=_operation_brief(operations),
    )


def verify_workspace(workspace: Path) -> dict[str, object]:
    """Public verification envelope for a complete deterministic replay."""

    verified = _open_and_verify(workspace)
    return _envelope(
        "verify",
        Path(verified["workspace"]),
        scenario_id=str(verified["metadata"]["scenario_id"]),
        valid=True,
        run_count=int(verified["latest_month"]),
        latest_month=int(verified["latest_month"]),
        state_hash=str(verified["latest_state"]["state_hash"]),
        checks={
            "metadata_hash": True,
            "scenario_hash": True,
            "contiguous_months": True,
            "state_hashes": True,
            "result_hashes": True,
            "state_lineage": True,
            "deterministic_replay": True,
            "readable_reports": True,
            "safety_boundary": True,
        },
    )


def _open_and_verify(workspace: Path) -> dict[str, object]:
    workspace = _existing_workspace_path(workspace)
    expected_root = {METADATA_NAME, SCENARIO_NAME, MONTHS_NAME}
    actual_root = {item.name for item in workspace.iterdir()}
    if actual_root != expected_root:
        raise WorkspaceError(
            f"workspace entries changed; expected {sorted(expected_root)}, got {sorted(actual_root)}"
        )

    metadata = _mapping(
        _read_canonical_json(workspace / METADATA_NAME, "workspace metadata"),
        "workspace metadata",
    )
    _verify_metadata(metadata)
    scenario = _mapping(
        _read_canonical_json(workspace / SCENARIO_NAME, "scenario"), "scenario"
    )
    core.validate_scenario(scenario)
    if _payload_hash(scenario) != metadata["scenario_hash"]:
        raise WorkspaceError("scenario hash does not match sealed metadata")
    if scenario.get("scenario_id") != metadata["scenario_id"]:
        raise WorkspaceError("scenario ID does not match sealed metadata")

    months_path = workspace / MONTHS_NAME
    if months_path.is_symlink() or not months_path.is_dir():
        raise WorkspaceError("months path must be a real directory")
    entries = sorted(months_path.iterdir(), key=lambda item: item.name)
    if not entries:
        raise WorkspaceError("workspace has no month-zero state")
    if any(
        item.is_symlink()
        or not item.is_dir()
        or _MONTH_DIRECTORY.fullmatch(item.name) is None
        for item in entries
    ):
        raise WorkspaceError("months contains an unexpected or unsafe entry")
    month_numbers = [int(item.name) for item in entries]
    expected_numbers = list(range(month_numbers[-1] + 1))
    if month_numbers != expected_numbers:
        raise WorkspaceError(
            f"month directories contain a gap: {month_numbers}"
        )

    month_zero = entries[0]
    if {item.name for item in month_zero.iterdir()} != {STATE_NAME}:
        raise WorkspaceError("month zero must contain only state.json")
    opening_state = _mapping(
        _read_canonical_json(month_zero / STATE_NAME, "month-zero state"),
        "month-zero state",
    )
    _assert_state(opening_state, expected_month=0)
    expected_opening = core.initial_state(scenario)
    if core.canonical_json(opening_state) != core.canonical_json(expected_opening):
        raise WorkspaceError("month-zero state is not the scenario's exact opening state")
    if opening_state["state_hash"] != metadata["opening_state_hash"]:
        raise WorkspaceError("opening state hash does not match sealed metadata")

    previous_state = opening_state
    for month_number, month_path in enumerate(entries[1:], start=1):
        required = {STATE_NAME, RESULT_NAME, REPORT_NAME}
        actual = {item.name for item in month_path.iterdir()}
        if actual != required:
            raise WorkspaceError(
                f"month {month_number} entries changed; expected {sorted(required)}, got {sorted(actual)}"
            )
        state = _mapping(
            _read_canonical_json(month_path / STATE_NAME, f"month {month_number} state"),
            f"month {month_number} state",
        )
        result = _mapping(
            _read_canonical_json(month_path / RESULT_NAME, f"month {month_number} result"),
            f"month {month_number} result",
        )
        _assert_state(state, expected_month=month_number)
        _assert_result(
            result,
            expected_month=month_number,
            input_state_hash=str(previous_state["state_hash"]),
            next_state_hash=str(state["state_hash"]),
        )
        expected_markdown = core.render_report(result)
        if result.get("report_markdown") != expected_markdown:
            raise WorkspaceError(
                f"month {month_number} embedded report does not match its result"
            )
        expected_html = _render_html(result)
        report_path = month_path / REPORT_NAME
        if report_path.is_symlink() or not report_path.is_file():
            raise WorkspaceError(f"month {month_number} report is missing or unsafe")
        if report_path.read_text(encoding="utf-8") != expected_html:
            raise WorkspaceError(f"month {month_number} HTML report was changed")

        replay = core.run_month(
            scenario, previous_state, str(metadata["seed_fingerprint"])
        )
        replay_result = _mapping(replay.get("result"), "replayed result")
        replay_state = _mapping(replay.get("next_state"), "replayed state")
        if core.canonical_json(replay_result) != core.canonical_json(result):
            raise WorkspaceError(
                f"month {month_number} result fails deterministic replay"
            )
        if core.canonical_json(replay_state) != core.canonical_json(state):
            raise WorkspaceError(
                f"month {month_number} state fails deterministic replay"
            )
        previous_state = state

    return {
        "workspace": workspace,
        "metadata": metadata,
        "scenario": scenario,
        "latest_month": month_numbers[-1],
        "latest_state": previous_state,
    }


def _verify_metadata(metadata: Mapping[str, object]) -> None:
    expected = {
        "schema",
        "scenario_id",
        "scenario_hash",
        "opening_state_hash",
        "seed_fingerprint",
        "canonical",
        "notion_writes",
        "canonical_ledger_postings",
        "metadata_hash",
    }
    if set(metadata) != expected:
        raise WorkspaceError("workspace metadata fields changed")
    if metadata.get("schema") != WORKSPACE_SCHEMA:
        raise WorkspaceError(f"workspace schema must be {WORKSPACE_SCHEMA}")
    if metadata.get("canonical") is not False:
        raise WorkspaceError("workspace must remain explicitly non-canonical")
    if metadata.get("notion_writes") != 0:
        raise WorkspaceError("workspace claims a Notion write")
    if metadata.get("canonical_ledger_postings") != 0:
        raise WorkspaceError("workspace claims a canonical ledger posting")
    for field in (
        "scenario_hash",
        "opening_state_hash",
        "seed_fingerprint",
        "metadata_hash",
    ):
        if not isinstance(metadata.get(field), str) or not _HEX_64.fullmatch(
            str(metadata[field])
        ):
            raise WorkspaceError(f"metadata {field} must be a lowercase SHA-256")
    body = {key: value for key, value in metadata.items() if key != "metadata_hash"}
    if _payload_hash(body) != metadata["metadata_hash"]:
        raise WorkspaceError("workspace metadata hash does not match its payload")


def _assert_state(state: Mapping[str, object], *, expected_month: int) -> None:
    if state.get("schema") != core.STATE_SCHEMA:
        raise WorkspaceError(f"state schema must be {core.STATE_SCHEMA}")
    if state.get("canonical") is not False:
        raise WorkspaceError("state must remain explicitly non-canonical")
    if state.get("month") != expected_month:
        raise WorkspaceError(
            f"state month is {state.get('month')!r}, expected {expected_month}"
        )
    digest = state.get("state_hash")
    if not isinstance(digest, str) or not _HEX_64.fullmatch(digest):
        raise WorkspaceError("state hash must be a lowercase SHA-256")
    if core.state_hash(state) != digest:
        raise WorkspaceError("state hash does not match state payload")


def _assert_result(
    result: Mapping[str, object],
    *,
    expected_month: int,
    input_state_hash: str,
    next_state_hash: str,
) -> None:
    if result.get("schema") != core.RESULT_SCHEMA:
        raise WorkspaceError(f"result schema must be {core.RESULT_SCHEMA}")
    if result.get("canonical") is not False:
        raise WorkspaceError("result must remain explicitly non-canonical")
    if result.get("month") != expected_month:
        raise WorkspaceError(
            f"result month is {result.get('month')!r}, expected {expected_month}"
        )
    if result.get("input_state_hash") != input_state_hash:
        raise WorkspaceError("result input state hash breaks state lineage")
    if result.get("next_state_hash") != next_state_hash:
        raise WorkspaceError("result next state hash breaks state lineage")
    digest = result.get("result_hash")
    if not isinstance(digest, str) or not _HEX_64.fullmatch(digest):
        raise WorkspaceError("result hash must be a lowercase SHA-256")
    if core.state_hash(result) != digest:
        raise WorkspaceError("result hash does not match result payload")
    checks = _mapping(result.get("checks"), "result checks")
    if checks.get("notion_writes") != 0:
        raise WorkspaceError("result claims a Notion write")
    if checks.get("canonical_ledger_postings") != 0:
        raise WorkspaceError("result claims a canonical ledger posting")
    if checks.get("campaign_advanced") is not False:
        raise WorkspaceError("result claims to advance campaign time")
    for field in (
        "physical_conservation",
        "nonnegative_balances",
        "ledger_balanced",
        "deposit_liabilities_reconcile",
    ):
        if checks.get(field) is not True:
            raise WorkspaceError(f"result failed required check: {field}")


def _render_html(result: Mapping[str, object]) -> str:
    """Render a concise deterministic HTML view over the exact result JSON.

    The core renderer remains authoritative for the detailed narrative.  This
    presentation layer adds a source-field-backed overview, rounds numeric
    prose for legibility, and collapses exhaustive lists.  It never mutates a
    simulation field; the committed ``result.json`` retains full precision.
    """

    markdown = core.render_report(result)
    required_sections = (
        "## What changed, where, and why",
        "## Available decisions",
        "## Integrity",
        "## Limits",
    )
    missing = [heading for heading in required_sections if heading not in markdown]
    if missing:
        raise WorkspaceError(
            f"core report omitted required user-visible sections: {missing}"
        )
    events = _list(result.get("events"), "result events")
    decisions = _list(result.get("available_decisions"), "available decisions")
    overview = _executive_summary_fragment(result)
    body = _markdown_fragment(
        markdown,
        collapsed_sections={
            "What changed, where, and why": f"{len(events):,} detailed events",
            "Pending campaign operations": (
                f"{len(_list(result.get('pending_operations'), 'pending operations')):,} queued"
            ),
            "Available decisions": f"{len(decisions):,} decisions",
        },
    )
    month = escape(str(result.get("month", "—")))
    result_hash = escape(str(result.get("result_hash", "pending")))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Regional Economy — Month {month}</title>
  <style>
    :root {{ color-scheme:light; --ink:#211b16; --muted:#6d6258; --paper:#f4ecdc; --panel:#fffaf0; --line:#d1bea0; --gold:#9b6a1b; --red:#8f2d2d; --green:#2f684b; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; color:var(--ink); background:var(--paper); font:16px/1.55 Georgia,serif; }}
    header {{ padding:28px max(22px,calc((100vw - 1080px)/2)); color:#fffaf0; background:#211b16; border-bottom:5px solid var(--gold); }}
    header p {{ margin:7px 0 0; }}
    .badges {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:14px; }}
    .badge {{ padding:6px 10px; border:1px solid #a9977d; border-radius:999px; font:700 12px Arial,sans-serif; }}
    .warn {{ background:var(--red); }} .safe {{ background:var(--green); }}
    main {{ max-width:1080px; margin:auto; padding:28px 22px 56px; }}
    h1 {{ font-size:clamp(30px,5vw,48px); line-height:1.1; }}
    h2 {{ margin:18px 0 12px; padding-bottom:7px; border-bottom:2px solid var(--line); }}
    ul {{ padding-left:24px; }} li {{ margin:9px 0; }}
    section {{ padding:4px 18px 16px; margin:18px 0; background:var(--panel); border:1px solid var(--line); border-radius:8px; }}
    .overview {{ padding-bottom:20px; }}
    .metric-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin:14px 0 22px; }}
    .metric {{ min-height:92px; padding:13px 14px; background:#fff; border:1px solid var(--line); border-radius:7px; }}
    .metric strong {{ display:block; color:var(--gold); font:700 28px/1.05 Arial,sans-serif; }}
    .metric span {{ display:block; margin-top:7px; color:var(--muted); font:700 12px/1.25 Arial,sans-serif; letter-spacing:.02em; text-transform:uppercase; }}
    .brief {{ display:grid; gap:8px; padding:0; list-style:none; }}
    .brief li {{ margin:0; padding:10px 12px; background:#fff; border-left:4px solid var(--gold); }}
    .detail-section {{ padding:0; }}
    details > summary {{ display:flex; align-items:baseline; justify-content:space-between; gap:16px; padding:17px 18px; cursor:pointer; font-weight:700; }}
    details > summary::marker {{ color:var(--gold); }}
    details[open] > summary {{ border-bottom:1px solid var(--line); }}
    .summary-title {{ font-size:21px; }}
    .summary-count {{ flex:none; color:var(--muted); font:700 12px Arial,sans-serif; text-transform:uppercase; }}
    .detail-body {{ max-height:70vh; overflow:auto; padding:4px 20px 18px; scrollbar-gutter:stable; }}
    .precision-note {{ color:var(--muted); font-size:13px; }}
    footer {{ margin-top:32px; padding-top:14px; border-top:1px solid var(--line); color:var(--muted); font-size:12px; }}
    code {{ overflow-wrap:anywhere; }}
    @media (max-width:600px) {{ details > summary {{ align-items:flex-start; flex-direction:column; gap:4px; }} .detail-body {{ max-height:none; }} }}
    @media print {{ body {{ background:white; }} section {{ break-inside:avoid; }} details:not([open]) > .detail-body {{ display:block; }} }}
  </style>
</head>
<body>
  <header>
    <strong>Whole-economy vertical slice</strong>
    <p>What changed, where, why, and the decisions now available.</p>
    <div class="badges">
      <span class="badge warn">PREVIEW — NOT CANON</span>
      <span class="badge safe">Notion writes: 0</span>
      <span class="badge safe">Canonical ledger postings: 0</span>
    </div>
  </header>
  <main>
    {overview}
    {body}
    <footer>
      Display values are rounded for readability; the committed <code>result.json</code>
      retains every exact value. Result hash: <code>{result_hash}</code>
    </footer>
  </main>
</body>
</html>
"""


def _executive_summary_fragment(result: Mapping[str, object]) -> str:
    """Build a compact overview from explicit monthly result fields."""

    shocks = _rows(result, "shocks")
    production = _rows(result, "production")
    market = _rows(result, "market")
    trades = _rows(result, "trade")
    obligations = _rows(result, "land_and_fiscal_obligations")
    banking = _rows(result, "banking")
    migrations = _rows(result, "migration")
    decisions = _rows(result, "available_decisions")
    active_shocks = [row for row in shocks if row.get("active") is True]
    shortages = [
        row
        for row in market
        if _decimal_or_zero(row.get("shortage_primary_equivalent")) > 0
    ]
    metrics = (
        ("Active shocks", len(active_shocks)),
        ("Production runs", len(production)),
        ("Trades", len(trades)),
        ("Shortage cases", len(shortages)),
        ("Obligations", len(obligations)),
        ("Bank actions", len(banking)),
        ("Migration flows", len(migrations)),
        ("Decisions", len(decisions)),
    )
    cards = "\n      ".join(
        f'<div class="metric"><strong>{value:,}</strong><span>{escape(label)}</span></div>'
        for label, value in metrics
    )
    briefs = "\n      ".join(
        f"<li>{_inline_markdown(line)}</li>"
        for line in _brief_lines(
            active_shocks=active_shocks,
            production=production,
            shortages=shortages,
            trades=trades,
            obligations=obligations,
            banking=banking,
            migrations=migrations,
            decisions=decisions,
            month=result.get("month"),
        )
    )
    return f"""<section class="overview">
      <h2>Executive summary</h2>
      <div class="metric-grid">
      {cards}
      </div>
      <h2>What changed, where, and why — at a glance</h2>
      <ul class="brief">
      {briefs}
      </ul>
      <p class="precision-note">Counts and statements above come directly from this month's exact result fields. Detailed events and decisions remain available below.</p>
    </section>"""


def _brief_lines(
    *,
    active_shocks: list[Mapping[str, object]],
    production: list[Mapping[str, object]],
    shortages: list[Mapping[str, object]],
    trades: list[Mapping[str, object]],
    obligations: list[Mapping[str, object]],
    banking: list[Mapping[str, object]],
    migrations: list[Mapping[str, object]],
    decisions: list[Mapping[str, object]],
    month: object,
) -> list[str]:
    lines: list[str] = []

    shock_places = _grouped_labels(active_shocks, "settlement_id")
    effect_names = sorted(
        {
            _human_label(effect)
            for row in active_shocks
            for effect in (
                row.get("effects", {}).keys()
                if isinstance(row.get("effects"), Mapping)
                else ()
            )
        }
    )
    if active_shocks:
        lines.append(
            f"**Shocks:** {len(active_shocks):,} active across {shock_places}; "
            f"their modeled effects changed {', '.join(effect_names) or 'operating constraints'}."
        )
    else:
        lines.append("**Shocks:** none were active this month.")

    production_places = _grouped_labels(production, "settlement_id")
    constrained = sum(bool(row.get("limiting_factors")) for row in production)
    lines.append(
        f"**Production:** {len(production):,} runs across {production_places}; "
        f"{constrained:,} reported a limiting factor."
    )

    if shortages:
        shortage_total = sum(
            (
                _decimal_or_zero(row.get("shortage_primary_equivalent"))
                for row in shortages
            ),
            Decimal(0),
        )
        shortage_places = _grouped_labels(shortages, "settlement_id")
        shortage_goods = _grouped_labels(shortages, "commodity_id")
        lines.append(
            f"**Shortages:** {len(shortages):,} demand lines left "
            f"{_display_decimal(shortage_total)} primary-equivalent units unmet in "
            f"{shortage_places}, affecting {shortage_goods}."
        )
    else:
        lines.append(
            "**Shortages:** no demand line ended with an unmet primary-equivalent quantity."
        )

    routed = sum(row.get("origin") != row.get("destination") for row in trades)
    unsettled = sum(row.get("status") != "delivered-and-settled" for row in trades)
    lines.append(
        f"**Trade:** {len(trades):,} transactions, including {routed:,} cross-settlement "
        f"movements; {unsettled:,} were not settled in month {month}."
    )

    overdue = [
        row
        for row in obligations
        if _decimal_or_zero(row.get("arrears")) > 0
        or _decimal_or_zero(row.get("paid")) < _decimal_or_zero(row.get("due"))
    ]
    due_total = sum(
        (_decimal_or_zero(row.get("due")) for row in obligations), Decimal(0)
    )
    lines.append(
        f"**Obligations:** {len(obligations):,} assessments totaling "
        f"{_display_decimal(due_total)} gp; {len(overdue):,} ended unpaid or in arrears."
    )

    bank_labels = _grouped_labels(banking, "action")
    defaulted = sum(row.get("status") == "defaulted" for row in banking)
    lines.append(
        f"**Banking:** {len(banking):,} actions ({bank_labels}); "
        f"{defaulted:,} carried a defaulted status."
    )

    migrant_total = sum(
        (_decimal_or_zero(row.get("migrants")) for row in migrations), Decimal(0)
    )
    routes = ", ".join(
        f"{_human_label(row.get('origin'))} → {_human_label(row.get('destination'))}"
        for row in migrations[:4]
    )
    if len(migrations) > 4:
        routes += f", +{len(migrations) - 4:,} more"
    lines.append(
        f"**Migration:** {_display_decimal(migrant_total)} people moved in "
        f"{len(migrations):,} flows{f' ({routes})' if routes else ''}."
    )

    decision_names = [
        str(row.get("summary"))
        for row in decisions[:4]
        if isinstance(row.get("summary"), str)
    ]
    decision_preview = "; ".join(decision_names)
    if len(decisions) > len(decision_names):
        decision_preview += f"; +{len(decisions) - len(decision_names):,} more"
    lines.append(
        f"**Decision queue:** {len(decisions):,} available"
        f"{f' — {decision_preview}.' if decision_preview else '.'}"
    )
    return lines


def _rows(result: Mapping[str, object], field: str) -> list[Mapping[str, object]]:
    rows = _list(result.get(field), f"result {field}")
    if any(not isinstance(row, Mapping) for row in rows):
        raise WorkspaceError(f"result {field} must contain only JSON objects")
    return [row for row in rows if isinstance(row, Mapping)]


def _operation_brief(operations: Sequence[Mapping[str, object]]) -> str:
    if not operations:
        return ""
    lines = [
        "# Campaign operation boot",
        "",
        "Read-only handoff: no operation was executed, no campaign time advanced, and no Notion or canonical-ledger write was made.",
    ]
    for operation in operations:
        lines.extend(
            [
                "",
                f"## {operation.get('title')}",
                "",
                f"- Status: {operation.get('status')}",
                f"- Boot trigger: {operation.get('boot_trigger')}",
                f"- Play trigger: {operation.get('play_trigger')}",
                f"- Current boundary: {operation.get('current_boundary')}",
                "- Execution authorized: no",
                "",
                "### Required facts",
                "",
            ]
        )
        for request in _list(
            operation.get("required_fact_requests"),
            "pending operation fact requests",
        ):
            row = _mapping(request, "pending operation fact request")
            lines.append(
                f"- [{row.get('status')}] {row.get('question')} "
                f"Owner: {row.get('owner')}; due: {row.get('due')}."
            )
        lines.extend(["", "### Decision gates", ""])
        for gate in _list(
            operation.get("decision_gates"),
            "pending operation decision gates",
        ):
            row = _mapping(gate, "pending operation decision gate")
            lines.append(
                f"- {row.get('decision')} Authority: {row.get('authority')}; "
                f"when: {row.get('when')}."
            )
    return "\n".join(lines) + "\n"


def _grouped_labels(rows: Sequence[Mapping[str, object]], field: str) -> str:
    counts: dict[str, int] = {}
    for row in rows:
        label = _human_label(row.get(field))
        counts[label] = counts.get(label, 0) + 1
    if not counts:
        return "no recorded locations"
    return ", ".join(
        f"{label} ({count:,})"
        for label, count in sorted(
            counts.items(), key=lambda item: (-item[1], item[0])
        )
    )


def _human_label(value: object) -> str:
    if value is None or value == "":
        return "regional / unspecified"
    text = str(value).rsplit(":", 1)[-1].replace("_", " ").replace("-", " ")
    return text[:1].upper() + text[1:]


def _decimal_or_zero(value: object) -> Decimal:
    if isinstance(value, bool) or value is None:
        return Decimal(0)
    try:
        return Decimal(str(value))
    except Exception as exc:
        raise WorkspaceError(
            f"expected a decimal-compatible result value, got {value!r}"
        ) from exc


def _display_decimal(value: Decimal) -> str:
    """Format an exact Decimal for display without changing the source value."""

    if not value.is_finite():
        raise WorkspaceError("cannot display a non-finite decimal")
    if value == 0:
        return "0"
    magnitude = abs(value)
    if magnitude >= 1:
        places = 2
    elif magnitude >= Decimal("0.01"):
        places = 3
    elif magnitude >= Decimal("0.0001"):
        places = 4
    else:
        mantissa, exponent = f"{value:.3E}".split("E")
        mantissa = mantissa.rstrip("0").rstrip(".")
        return f"{mantissa}E{int(exponent):+d}"
    rendered = f"{value:,.{places}f}".rstrip("0").rstrip(".")
    return "0" if rendered in {"-0", "+0"} else rendered


def _format_numeric_tokens(value: str) -> str:
    def replace_decimal(match: re.Match[str]) -> str:
        try:
            return _display_decimal(Decimal(match.group(0)))
        except Exception:
            return match.group(0)

    rounded = _DECIMAL_TOKEN.sub(replace_decimal, value)
    return _LARGE_INTEGER_TOKEN.sub(
        lambda match: f"{int(match.group(0)):,}", rounded
    )


def _markdown_fragment(
    markdown: str,
    *,
    collapsed_sections: Mapping[str, str] | None = None,
) -> str:
    lines = markdown.splitlines()
    output: list[str] = []
    in_list = False
    section_open = False
    details_open = False
    collapsed_sections = collapsed_sections or {}

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            output.append("</ul>")
            in_list = False

    def close_section() -> None:
        nonlocal section_open, details_open
        close_list()
        if details_open:
            output.extend(["</div>", "</details>"])
            details_open = False
        if section_open:
            output.append("</section>")
            section_open = False

    for raw in lines:
        if raw.startswith("# "):
            close_section()
            output.append(f"<h1>{_inline_markdown(raw[2:])}</h1>")
        elif raw.startswith("## "):
            close_section()
            heading = raw[3:]
            is_collapsed = heading in collapsed_sections
            output.append(
                '<section class="detail-section">' if is_collapsed else "<section>"
            )
            section_open = True
            if is_collapsed:
                output.extend(
                    [
                        "<details>",
                        "<summary>",
                        f'<span class="summary-title">{_inline_markdown(heading)}</span>',
                        f'<span class="summary-count">{escape(collapsed_sections[heading])}</span>',
                        "</summary>",
                        '<div class="detail-body">',
                    ]
                )
                details_open = True
            else:
                output.append(f"<h2>{_inline_markdown(heading)}</h2>")
        elif raw.startswith("- "):
            if not in_list:
                output.append("<ul>")
                in_list = True
            output.append(f"<li>{_inline_markdown(raw[2:])}</li>")
        elif raw.strip():
            close_list()
            output.append(f"<p>{_inline_markdown(raw)}</p>")
        else:
            close_list()
    close_section()
    return "\n    ".join(output)


def _inline_markdown(value: str) -> str:
    safe = escape(_format_numeric_tokens(value))
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", safe)


def _read_canonical_json(path: Path, label: str) -> object:
    if path.is_symlink() or not path.is_file():
        raise WorkspaceError(f"{label} is missing or is not a regular file: {path}")
    text = path.read_text(encoding="utf-8")
    try:
        value = json.loads(
            text,
            parse_float=Decimal,
            parse_int=int,
            parse_constant=lambda token: (_ for _ in ()).throw(
                WorkspaceError(f"non-finite JSON value in {label}: {token}")
            ),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except json.JSONDecodeError as exc:
        raise WorkspaceError(f"could not decode {label}: {exc}") from exc
    expected = core.canonical_json(value) + "\n"
    if text != expected:
        raise WorkspaceError(f"{label} is not the exact canonical JSON artifact")
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise WorkspaceError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _write_new_json(path: Path, value: object) -> None:
    _write_new_text(path, core.canonical_json(value) + "\n")


def _write_new_text(path: Path, value: str) -> None:
    if path.exists() or path.is_symlink():
        raise WorkspaceError(f"refusing to overwrite existing artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())


def _payload_hash(value: object) -> str:
    return hashlib.sha256(core.canonical_json(value).encode("utf-8")).hexdigest()


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise WorkspaceError(f"{label} must be a JSON object")
    return value


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise WorkspaceError(f"{label} must be a JSON array")
    return value


def _month_name(month: int) -> str:
    if month < 0 or month > 9999:
        raise WorkspaceError("month is outside supported append-only range 0..9999")
    return f"{month:04d}"


def _new_workspace_path(path: Path) -> Path:
    if path.is_symlink() or path.exists():
        raise WorkspaceError(f"workspace already exists: {path.resolve()}")
    return path.resolve()


def _existing_workspace_path(path: Path) -> Path:
    if path.is_symlink():
        raise WorkspaceError("workspace cannot be a symbolic link")
    resolved = path.resolve()
    if not resolved.is_dir():
        raise WorkspaceError(f"workspace does not exist: {resolved}")
    return resolved


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _positive_int(value: str) -> int:
    try:
        result = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("period must be a positive integer") from exc
    if result < 1:
        raise argparse.ArgumentTypeError("period must be a positive integer")
    return result


def _envelope(
    command: str,
    workspace: Path,
    *,
    scenario_id: str,
    **extra: object,
) -> dict[str, object]:
    return {
        "ok": True,
        "command": command,
        "workspace_path": str(workspace.resolve()),
        "scenario_id": scenario_id,
        "canonical": False,
        "notion_writes": NOTION_WRITES,
        "canonical_ledger_postings": CANONICAL_LEDGER_POSTINGS,
        **extra,
    }


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "WorkspaceError",
    "build_parser",
    "boot_workspace",
    "initialize_workspace",
    "main",
    "report_workspace",
    "run_workspace_month",
    "verify_workspace",
]
