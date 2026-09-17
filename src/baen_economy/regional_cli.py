"""Persistent command shell for the regional economy simulation.

The regional engine is deliberately split into four adapters.  Scenario loading,
physical production, market/transport clearing, and finance can evolve without
making the command-line persistence format depend on their internal dataclasses.
Only JSON-safe mappings cross the adapter boundary.

This module owns local preview persistence.  It has no Notion connector and no
canonical-ledger writer.  The two zero counters printed by every command are
therefore facts about this command path, not configuration switches.
"""

from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import dataclass, fields, is_dataclass
from decimal import Decimal
import hashlib
import importlib
import json
from pathlib import Path
import sqlite3
import sys
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence

from .regional_report import default_report_path, render_month_html


SCHEMA_VERSION = "tnp.economy.regional-cli/1"
DEFAULT_SCENARIO_ID = "baen-regional-mvp"
NOTION_WRITES = 0
CANONICAL_LEDGER_POSTINGS = 0


class RegionalCliError(ValueError):
    """Raised when a regional command cannot be completed safely."""


@dataclass(frozen=True, slots=True)
class ScenarioRequest:
    """Stable initialization input passed to a scenario adapter."""

    scenario_id: str
    scenario_path: Path | None
    registry_path: Path | None
    seed_fingerprint: str


@dataclass(frozen=True, slots=True)
class MonthRequest:
    """Stable monthly input passed to simulation adapters."""

    scenario: Mapping[str, object]
    opening_state: Mapping[str, object]
    period: int
    seed_fingerprint: str


class ScenarioAdapter(Protocol):
    """Load a source-bound scenario and construct its opening state."""

    def initialize(self, request: ScenarioRequest) -> Mapping[str, object]:
        """Return ``{"scenario": mapping, "state": mapping}``."""


class ProductionAdapter(Protocol):
    """Advance physical production, labour, and payroll by one month."""

    def simulate(self, request: MonthRequest) -> Mapping[str, object]:
        """Return ``state`` plus normalized ``production`` and ``labor`` sections."""


class MarketTransportAdapter(Protocol):
    """Move goods, clear demand, and apply bounded price response."""

    def simulate(
        self,
        request: MonthRequest,
        production: Mapping[str, object],
    ) -> Mapping[str, object]:
        """Return ``state`` plus normalized ``transport`` and ``market`` sections."""


class FinanceAdapter(Protocol):
    """Resolve bank, treasury, and balanced preview-journal effects."""

    def simulate(
        self,
        request: MonthRequest,
        production: Mapping[str, object],
        market_transport: Mapping[str, object],
    ) -> Mapping[str, object]:
        """Return ``state`` plus normalized bank, treasury, and journal sections."""


@dataclass(frozen=True, slots=True)
class RegionalAdapters:
    """Dependency-injection boundary used by the CLI and black-box tests."""

    scenario: ScenarioAdapter
    production: ProductionAdapter
    market_transport: MarketTransportAdapter
    finance: FinanceAdapter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="baen-region",
        description=(
            "Run the synthetic regional mechanics demo. It is not the Baen "
            "campaign economy, writes zero Notion values, and posts zero entries "
            "to the canonical campaign ledger. Use baen-food report for the "
            "source-truth food baseline."
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser(
        "init", help="initialize a durable regional scenario and opening state"
    )
    init.add_argument("database", type=Path)
    init.add_argument("--scenario", default=DEFAULT_SCENARIO_ID)
    init.add_argument("--scenario-path", type=Path)
    init.add_argument("--registry-path", type=Path)
    init.add_argument(
        "--allow-synthetic-demo",
        action="store_true",
        help=(
            "explicitly opt into invented stocks, recipes, routes, prices, "
            "cash, banking, and tax inputs for mechanics testing only"
        ),
    )
    init.add_argument(
        "--seed",
        required=True,
        help=(
            "deterministic replay seed; only its SHA-256 fingerprint is retained"
        ),
    )
    init.add_argument(
        "--state-dir",
        type=Path,
        help="snapshot artifact directory; defaults beside the database",
    )
    init.add_argument(
        "--output-dir",
        type=Path,
        help="monthly result directory; defaults beside the database",
    )
    init.add_argument("--format", choices=("summary", "json"), default="summary")

    for command in ("run-month", "simulate-month"):
        run = commands.add_parser(
            command,
            help=(
                "simulate the next month; add --commit to persist its changed state"
            ),
        )
        run.add_argument("database", type=Path)
        run.add_argument(
            "--commit",
            action="store_true",
            help="atomically persist the local preview and its JSON artifacts",
        )
        run.add_argument(
            "--seed",
            help="optional replay check; must match the initialization seed",
        )
        run.add_argument("--format", choices=("summary", "json"), default="summary")

    report = commands.add_parser(
        "report", help="render the latest committed regional month"
    )
    report.add_argument("database", type=Path)
    report.add_argument("--period", type=_positive_int)
    report.add_argument(
        "--output",
        type=Path,
        help=(
            "readable HTML destination; defaults to DATABASE-Month-N-Report.html "
            "beside the database"
        ),
    )
    report.add_argument("--format", choices=("summary", "json"), default="summary")

    verify = commands.add_parser(
        "verify", help="verify state lineage, hashes, and durable JSON artifacts"
    )
    verify.add_argument("database", type=Path)
    verify.add_argument("--format", choices=("summary", "json"), default="summary")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    adapters: RegionalAdapters | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            if adapters is None and not args.allow_synthetic_demo:
                raise RegionalCliError(
                    "the executable regional scenario is a synthetic mechanics "
                    "demo and is disabled by default; run 'baen-food report' for "
                    "your source-truth economy, or pass --allow-synthetic-demo "
                    "only when you deliberately want invented test inputs"
                )
            payload = initialize_workspace(
                args.database,
                scenario_id=args.scenario,
                scenario_path=args.scenario_path,
                registry_path=args.registry_path,
                seed=args.seed,
                state_dir=args.state_dir,
                output_dir=args.output_dir,
                adapters=adapters,
            )
            _emit(payload, args.format, _render_init_summary)
            return 0
        if args.command in {"run-month", "simulate-month"}:
            payload = simulate_month(
                args.database,
                commit=args.commit,
                seed=args.seed,
                adapters=adapters,
            )
            _emit(payload, args.format, _render_month_summary)
            return 0
        if args.command == "report":
            payload = report_workspace(
                args.database,
                period=args.period,
                html_output=args.output,
            )
            _emit(payload, args.format, _render_report)
            return 0
        if args.command == "verify":
            payload = verify_workspace(args.database)
            _emit(payload, args.format, _render_verify_summary)
            return 0
        parser.error("unknown command")
    except (ValueError, sqlite3.Error, OSError, KeyError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def initialize_workspace(
    database: Path,
    *,
    scenario_id: str,
    scenario_path: Path | None,
    registry_path: Path | None,
    seed: str,
    state_dir: Path | None = None,
    output_dir: Path | None = None,
    adapters: RegionalAdapters | None = None,
) -> dict[str, object]:
    """Create a new SQLite catalog and an inspectable period-zero snapshot."""

    database = database.resolve()
    if database.exists():
        raise RegionalCliError(f"database already exists: {database}")
    if not scenario_id.strip():
        raise RegionalCliError("scenario ID must not be empty")
    if not seed:
        raise RegionalCliError("seed must not be empty")
    scenario_path = _optional_existing_path(scenario_path, "scenario")
    registry_path = _optional_existing_path(registry_path, "registry")
    state_dir = (state_dir or database.with_name(f"{database.name}.states")).resolve()
    output_dir = (output_dir or database.with_name(f"{database.name}.outputs")).resolve()
    if state_dir == output_dir:
        raise RegionalCliError("state and output directories must be different")

    bundle = adapters or load_default_adapters()
    seed_fingerprint = _hash_text(seed)
    initialized = _require_mapping(
        bundle.scenario.initialize(
            ScenarioRequest(
                scenario_id=scenario_id,
                scenario_path=scenario_path,
                registry_path=registry_path,
                seed_fingerprint=seed_fingerprint,
            )
        ),
        "scenario initialization",
    )
    scenario = _require_mapping(initialized.get("scenario"), "scenario")
    opening_state = dict(_require_mapping(initialized.get("state"), "opening state"))
    opening_state["period"] = 0
    _assert_json_value(scenario, "scenario")
    _assert_json_value(opening_state, "opening state")
    scenario_json = _canonical_json(scenario)
    state_json = _canonical_json(opening_state)
    scenario_hash = _hash_text(scenario_json)
    state_hash = _hash_text(state_json)

    database.parent.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    scenario_artifact_path = state_dir / "scenario.json"
    state_path = state_dir / "period-0000.json"
    for label, artifact in (
        ("scenario", scenario_artifact_path),
        ("opening-state", state_path),
    ):
        if artifact.exists():
            raise RegionalCliError(f"{label} artifact already exists: {artifact}")

    connection: sqlite3.Connection | None = None
    try:
        connection = _connect(database)
        _create_schema(connection)
        with connection:
            metadata = {
                "schema_version": SCHEMA_VERSION,
                "scenario_id": scenario_id,
                "scenario_path": str(scenario_path) if scenario_path else "",
                "registry_path": str(registry_path) if registry_path else "",
                "seed_fingerprint": seed_fingerprint,
                "state_dir": str(state_dir),
                "output_dir": str(output_dir),
                "scenario_artifact_path": str(scenario_artifact_path),
            }
            connection.executemany(
                "INSERT INTO metadata(key, value) VALUES (?, ?)", metadata.items()
            )
            connection.execute(
                "INSERT INTO scenario(singleton, payload_json, payload_hash, "
                "artifact_path) VALUES (1, ?, ?, ?)",
                (scenario_json, scenario_hash, str(scenario_artifact_path)),
            )
            connection.execute(
                "INSERT INTO state_snapshot(period, prior_state_hash, state_json, "
                "state_hash, artifact_path) VALUES (0, NULL, ?, ?, ?)",
                (state_json, state_hash, str(state_path)),
            )
        _write_exact_json(scenario_artifact_path, scenario)
        _write_exact_json(state_path, opening_state)
    except Exception:
        if connection is not None:
            connection.close()
        if database.exists():
            database.unlink()
        for artifact in (scenario_artifact_path, state_path):
            if artifact.exists():
                artifact.unlink()
        raise
    else:
        connection.close()

    return _base_envelope(
        command="init",
        database=database,
        scenario_id=scenario_id,
        seed_fingerprint=seed_fingerprint,
        extra={
            "initialized": True,
            "period": 0,
            "scenario_hash": scenario_hash,
            "scenario_path": str(scenario_artifact_path),
            "scenario_source_path": str(scenario_path) if scenario_path else None,
            "state_hash": state_hash,
            "state_path": str(state_path),
            "output_path": None,
            "state_dir": str(state_dir),
            "output_dir": str(output_dir),
        },
    )


def simulate_month(
    database: Path,
    *,
    commit: bool,
    seed: str | None = None,
    adapters: RegionalAdapters | None = None,
) -> dict[str, object]:
    """Simulate the next month and optionally append it to the durable history."""

    database = _existing_database(database)
    bundle = adapters or load_default_adapters()
    with closing(_connect(database)) as connection:
        metadata = _metadata(connection)
        if seed is not None and _hash_text(seed) != metadata["seed_fingerprint"]:
            raise RegionalCliError("seed does not match the initialized replay seed")
        scenario = _decode_json_row(
            connection.execute(
                "SELECT payload_json FROM scenario WHERE singleton = 1"
            ).fetchone(),
            "scenario",
        )
        row = connection.execute(
            "SELECT period, state_json, state_hash FROM state_snapshot "
            "ORDER BY period DESC LIMIT 1"
        ).fetchone()
        if row is None:
            raise RegionalCliError("database has no opening state")
        opening_period = _exact_int(row["period"], "opening period")
        opening_state = _require_mapping(
            json.loads(str(row["state_json"])), "opening state"
        )
        prior_state_hash = str(row["state_hash"])
        period = opening_period + 1
        request = MonthRequest(
            scenario=MappingProxyType(dict(scenario)),
            opening_state=MappingProxyType(dict(opening_state)),
            period=period,
            seed_fingerprint=metadata["seed_fingerprint"],
        )

        production = _require_mapping(
            bundle.production.simulate(request), "production result"
        )
        market_transport = _require_mapping(
            bundle.market_transport.simulate(request, production),
            "market/transport result",
        )
        finance = _require_mapping(
            bundle.finance.simulate(request, production, market_transport),
            "finance result",
        )
        result, next_state = _normalize_month_result(
            request,
            production=production,
            market_transport=market_transport,
            finance=finance,
        )
        result_json = _canonical_json(result)
        result_hash = _hash_text(result_json)
        state_json = _canonical_json(next_state)
        next_state_hash = _hash_text(state_json)
        if next_state_hash == prior_state_hash:
            raise RegionalCliError("simulation produced no changed next state")

        output_path: Path | None = None
        state_path: Path | None = None
        if commit:
            output_path = Path(metadata["output_dir"]) / f"period-{period:04d}.json"
            state_path = Path(metadata["state_dir"]) / f"period-{period:04d}.json"
            if output_path.exists() or state_path.exists():
                raise RegionalCliError(
                    "refusing to overwrite an existing monthly state or output artifact"
                )
            with connection:
                connection.execute(
                    "INSERT INTO state_snapshot(period, prior_state_hash, state_json, "
                    "state_hash, artifact_path) VALUES (?, ?, ?, ?, ?)",
                    (
                        period,
                        prior_state_hash,
                        state_json,
                        next_state_hash,
                        str(state_path),
                    ),
                )
                connection.execute(
                    "INSERT INTO month_run(period, prior_state_hash, next_state_hash, "
                    "result_json, result_hash, artifact_path) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        period,
                        prior_state_hash,
                        next_state_hash,
                        result_json,
                        result_hash,
                        str(output_path),
                    ),
                )
            try:
                _write_exact_json(state_path, next_state)
                _write_exact_json(output_path, result)
            except Exception:
                with connection:
                    connection.execute("DELETE FROM month_run WHERE period = ?", (period,))
                    connection.execute(
                        "DELETE FROM state_snapshot WHERE period = ?", (period,)
                    )
                for artifact in (state_path, output_path):
                    if artifact.exists():
                        artifact.unlink()
                raise

    payload = _base_envelope(
        command="run-month",
        database=database,
        scenario_id=metadata["scenario_id"],
        seed_fingerprint=metadata["seed_fingerprint"],
        extra={
            "committed": commit,
            "period": period,
            "prior_state_hash": prior_state_hash,
            "next_state_hash": next_state_hash,
            "changed": True,
            "result_hash": result_hash,
            "state_path": str(state_path) if state_path else None,
            "output_path": str(output_path) if output_path else None,
            "html_report_path": None,
            "result": result,
        },
    )
    if commit:
        report_path = default_report_path(database, period)
        report_payload = {
            **payload,
            "scenario": scenario,
            "state": next_state,
            "latest_result": result,
            "state_hash": next_state_hash,
        }
        _write_exact_text(report_path, render_month_html(report_payload))
        payload["html_report_path"] = str(report_path)
    return payload


def report_workspace(
    database: Path,
    *,
    period: int | None = None,
    html_output: Path | None = None,
) -> dict[str, object]:
    """Return a committed result and write its human-readable HTML report."""

    database = _existing_database(database)
    with closing(_connect(database)) as connection:
        metadata = _metadata(connection)
        if period is None:
            run = connection.execute(
                "SELECT * FROM month_run ORDER BY period DESC LIMIT 1"
            ).fetchone()
        else:
            run = connection.execute(
                "SELECT * FROM month_run WHERE period = ?", (period,)
            ).fetchone()
        if run is None:
            raise RegionalCliError("no committed regional month is available to report")
        selected_period = _exact_int(run["period"], "report period")
        state = _decode_json_row(
            connection.execute(
                "SELECT state_json FROM state_snapshot WHERE period = ?",
                (selected_period,),
            ).fetchone(),
            "state snapshot",
        )
        result = _require_mapping(json.loads(str(run["result_json"])), "stored result")
        scenario = _decode_json_row(
            connection.execute(
                "SELECT payload_json FROM scenario WHERE singleton = 1"
            ).fetchone(),
            "scenario",
        )
    payload = _base_envelope(
        command="report",
        database=database,
        scenario_id=metadata["scenario_id"],
        seed_fingerprint=metadata["seed_fingerprint"],
        extra={
            "period": selected_period,
            "state_hash": str(run["next_state_hash"]),
            "state": state,
            "scenario": scenario,
            "latest_result": result,
            "output_path": str(run["artifact_path"]),
            "html_report_path": None,
        },
    )
    report_path = (
        html_output.resolve()
        if html_output is not None
        else default_report_path(database, selected_period)
    )
    if report_path.suffix.lower() not in {".html", ".htm"}:
        raise RegionalCliError("readable report output must end in .html or .htm")
    _write_exact_text(report_path, render_month_html(payload))
    payload["html_report_path"] = str(report_path)
    return payload


def verify_workspace(database: Path) -> dict[str, object]:
    """Verify SQLite integrity, hash lineage, and exact external artifacts."""

    database = _existing_database(database)
    checks = {
        "sqlite_integrity": False,
        "scenario_hash": False,
        "state_hashes": False,
        "state_lineage": False,
        "result_hashes": False,
        "durable_artifacts": False,
        "readable_reports": False,
        "safety_boundary": False,
    }
    with closing(_connect(database)) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        checks["sqlite_integrity"] = bool(integrity and integrity[0] == "ok")
        metadata = _metadata(connection)
        scenario = connection.execute(
            "SELECT payload_json, payload_hash, artifact_path FROM scenario "
            "WHERE singleton = 1"
        ).fetchone()
        if scenario is None:
            raise RegionalCliError("database has no scenario record")
        checks["scenario_hash"] = _hash_text(str(scenario["payload_json"])) == str(
            scenario["payload_hash"]
        )

        state_rows = connection.execute(
            "SELECT * FROM state_snapshot ORDER BY period"
        ).fetchall()
        run_rows = connection.execute("SELECT * FROM month_run ORDER BY period").fetchall()
        if not state_rows or _exact_int(state_rows[0]["period"], "opening period") != 0:
            raise RegionalCliError("state history does not begin at period zero")
        state_hashes_ok = True
        lineage_ok = True
        artifacts_ok = _artifact_matches(
            Path(str(scenario["artifact_path"])), str(scenario["payload_json"])
        )
        previous_hash: str | None = None
        for expected_period, row in enumerate(state_rows):
            actual_period = _exact_int(row["period"], "state period")
            state_hash = str(row["state_hash"])
            state_hashes_ok &= actual_period == expected_period
            state_hashes_ok &= _hash_text(str(row["state_json"])) == state_hash
            prior = row["prior_state_hash"]
            lineage_ok &= prior == previous_hash
            artifacts_ok &= _artifact_matches(
                Path(str(row["artifact_path"])), str(row["state_json"])
            )
            previous_hash = state_hash
        checks["state_hashes"] = state_hashes_ok
        checks["state_lineage"] = lineage_ok

        result_hashes_ok = len(run_rows) == len(state_rows) - 1
        readable_reports_ok = True
        scenario_payload = _require_mapping(
            json.loads(str(scenario["payload_json"])), "scenario"
        )
        for expected_period, row in enumerate(run_rows, start=1):
            actual_period = _exact_int(row["period"], "run period")
            result_hashes_ok &= actual_period == expected_period
            result_hashes_ok &= _hash_text(str(row["result_json"])) == str(
                row["result_hash"]
            )
            result_hashes_ok &= str(row["prior_state_hash"]) == str(
                state_rows[expected_period - 1]["state_hash"]
            )
            result_hashes_ok &= str(row["next_state_hash"]) == str(
                state_rows[expected_period]["state_hash"]
            )
            artifacts_ok &= _artifact_matches(
                Path(str(row["artifact_path"])), str(row["result_json"])
            )
            stored_result = _require_mapping(
                json.loads(str(row["result_json"])), "stored result"
            )
            stored_state = _require_mapping(
                json.loads(str(state_rows[expected_period]["state_json"])),
                "stored state",
            )
            report_payload = _base_envelope(
                command="report",
                database=database,
                scenario_id=metadata["scenario_id"],
                seed_fingerprint=metadata["seed_fingerprint"],
                extra={
                    "period": expected_period,
                    "state_hash": str(row["next_state_hash"]),
                    "state": stored_state,
                    "scenario": scenario_payload,
                    "latest_result": stored_result,
                    "output_path": str(row["artifact_path"]),
                    "html_report_path": str(
                        default_report_path(database, expected_period)
                    ),
                },
            )
            readable_reports_ok &= _text_matches(
                default_report_path(database, expected_period),
                render_month_html(report_payload),
            )
        checks["result_hashes"] = result_hashes_ok
        checks["durable_artifacts"] = artifacts_ok
        checks["readable_reports"] = readable_reports_ok
        checks["safety_boundary"] = (
            NOTION_WRITES == 0 and CANONICAL_LEDGER_POSTINGS == 0
        )
        valid = all(checks.values())
        latest_state_hash = str(state_rows[-1]["state_hash"])

    return _base_envelope(
        command="verify",
        database=database,
        scenario_id=metadata["scenario_id"],
        seed_fingerprint=metadata["seed_fingerprint"],
        extra={
            "valid": valid,
            "checks": checks,
            "state_hash": latest_state_hash,
            "run_count": len(run_rows),
        },
    )


def load_default_adapters() -> RegionalAdapters:
    """Load the concrete regional modules through narrow compatibility wrappers.

    The imports are intentionally lazy so ``--help`` and stored ``report`` /
    ``verify`` commands do not require simulation modules to be imported.
    """

    try:
        integration = importlib.import_module(".regional_engine", __package__)
    except ImportError as exc:
        raise RegionalCliError(
            "regional simulation adapters are unavailable; expected "
            "baen_economy.regional_engine.build_adapters()"
        ) from exc
    factory = getattr(integration, "build_adapters", None)
    if not callable(factory):
        raise RegionalCliError(
            "regional_engine must expose callable build_adapters()"
        )
    bundle = factory()
    if not isinstance(bundle, RegionalAdapters):
        required = ("scenario", "production", "market_transport", "finance")
        if not all(hasattr(bundle, name) for name in required):
            raise RegionalCliError(
                "build_adapters() did not return scenario, production, "
                "market_transport, and finance adapters"
            )
        bundle = RegionalAdapters(*(getattr(bundle, name) for name in required))
    return bundle


def _normalize_month_result(
    request: MonthRequest,
    *,
    production: Mapping[str, object],
    market_transport: Mapping[str, object],
    finance: Mapping[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    sections = {
        "production": _required_section(production, "production"),
        "labor": _required_section(production, "labor"),
        "transport": _required_section(market_transport, "transport"),
        "market": _required_section(market_transport, "market"),
        "banking": _required_section(finance, "banking"),
        "treasury": _required_section(finance, "treasury"),
        "journal": _required_section(finance, "journal"),
    }
    next_state = dict(request.opening_state)
    next_state["period"] = request.period
    for name, payload in (
        ("production", production),
        ("market_transport", market_transport),
        ("finance", finance),
    ):
        state = payload.get("state")
        next_state[name] = dict(_require_mapping(state, f"{name} state"))
    result: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "scenario_id": str(request.scenario.get("scenario_id", DEFAULT_SCENARIO_ID)),
        "period": request.period,
        "canonical": False,
        "notion_writes": NOTION_WRITES,
        "canonical_ledger_postings": CANONICAL_LEDGER_POSTINGS,
        **sections,
    }
    _assert_json_value(result, "monthly result")
    _assert_json_value(next_state, "next state")
    return result, next_state


def _required_section(payload: Mapping[str, object], key: str) -> Mapping[str, object]:
    return dict(_require_mapping(payload.get(key), f"{key} section"))


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        ) STRICT;
        CREATE TABLE scenario (
            singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
            payload_json TEXT NOT NULL,
            payload_hash TEXT NOT NULL CHECK(length(payload_hash) = 64),
            artifact_path TEXT NOT NULL
        ) STRICT;
        CREATE TABLE state_snapshot (
            period INTEGER PRIMARY KEY CHECK(period >= 0),
            prior_state_hash TEXT,
            state_json TEXT NOT NULL,
            state_hash TEXT NOT NULL UNIQUE CHECK(length(state_hash) = 64),
            artifact_path TEXT NOT NULL
        ) STRICT;
        CREATE TABLE month_run (
            period INTEGER PRIMARY KEY CHECK(period > 0),
            prior_state_hash TEXT NOT NULL CHECK(length(prior_state_hash) = 64),
            next_state_hash TEXT NOT NULL UNIQUE CHECK(length(next_state_hash) = 64),
            result_json TEXT NOT NULL,
            result_hash TEXT NOT NULL UNIQUE CHECK(length(result_hash) = 64),
            artifact_path TEXT NOT NULL,
            FOREIGN KEY(period) REFERENCES state_snapshot(period),
            FOREIGN KEY(next_state_hash) REFERENCES state_snapshot(state_hash)
        ) STRICT;
        """
    )


def _connect(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(database))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _metadata(connection: sqlite3.Connection) -> dict[str, str]:
    metadata = {
        str(row["key"]): str(row["value"])
        for row in connection.execute("SELECT key, value FROM metadata")
    }
    required = {
        "schema_version",
        "scenario_id",
        "seed_fingerprint",
        "state_dir",
        "output_dir",
    }
    missing = sorted(required - metadata.keys())
    if missing:
        raise RegionalCliError(f"database metadata is missing: {', '.join(missing)}")
    if metadata["schema_version"] != SCHEMA_VERSION:
        raise RegionalCliError(
            f"unsupported regional database schema: {metadata['schema_version']}"
        )
    return metadata


def _base_envelope(
    *,
    command: str,
    database: Path,
    scenario_id: str,
    seed_fingerprint: str,
    extra: Mapping[str, object],
) -> dict[str, object]:
    return {
        "command": command,
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "notion_writes": NOTION_WRITES,
        "canonical_ledger_postings": CANONICAL_LEDGER_POSTINGS,
        "database_path": str(database),
        "scenario_id": scenario_id,
        "seed_fingerprint": seed_fingerprint,
        **extra,
    }


def _emit(payload: Mapping[str, object], format_name: str, renderer: Any) -> None:
    if format_name == "json":
        print(json.dumps(_json_safe(payload), indent=2, sort_keys=True, allow_nan=False))
    else:
        print(renderer(payload), end="")


def _render_init_summary(payload: Mapping[str, object]) -> str:
    return (
        "REGIONAL PREVIEW INITIALIZED — NOT CANON\n"
        "Notion writes: 0 | Canonical ledger postings: 0\n"
        f"Scenario: {payload['scenario_id']} | Period: 0\n"
        f"Opening state: {payload['state_hash']}\n"
        f"State artifact: {payload['state_path']}\n"
    )


def _render_month_summary(payload: Mapping[str, object]) -> str:
    result = _require_mapping(payload["result"], "monthly result")
    production = _require_mapping(result["production"], "production section")
    labor = _require_mapping(result["labor"], "labor section")
    transport = _require_mapping(result["transport"], "transport section")
    market = _require_mapping(result["market"], "market section")
    banking = _require_mapping(result["banking"], "banking section")
    treasury = _require_mapping(result["treasury"], "treasury section")
    journal = _require_mapping(result["journal"], "journal section")
    runs = production.get("runs")
    active_entities: set[str] = set()
    if isinstance(runs, list):
        for item in runs:
            if not isinstance(item, Mapping):
                continue
            try:
                active = Decimal(str(item.get("output_produced", "0"))) > 0
            except Exception:
                active = False
            if active and isinstance(item.get("entity_id"), str):
                active_entities.add(str(item["entity_id"]))
    price_before = market.get(
        "price_before_gp_per_unit", market.get("price_before")
    )
    price_after = market.get(
        "price_after_gp_per_unit", market.get("price_after")
    )
    route_usage = transport.get("route_usage")
    if isinstance(route_usage, list):
        transport_summary = (
            f"{len(route_usage)} active route receipts; unit-specific quantities stored"
        )
    else:
        transport_summary = (
            f"{transport.get('quantity_moved')} / {transport.get('capacity')}"
        )
    persistence = "COMMITTED LOCALLY" if payload["committed"] else "DRY RUN — NOT SAVED"
    readable_line = (
        f"Readable report: {payload['html_report_path']}\n"
        if payload.get("html_report_path")
        else ""
    )
    return (
        "REGIONAL MONTH PREVIEW — NOT CANON\n"
        "Notion writes: 0 | Canonical ledger postings: 0\n"
        f"Period {payload['period']} | {persistence}\n"
        f"Production: {len(active_entities)} active businesses; "
        "unit-specific input/output receipts stored\n"
        f"Labour: {labor.get('workers')} workers; payroll {labor.get('payroll')}\n"
        f"Transport: {transport_summary}\n"
        f"Market: shortage {market.get('shortage_quantity')}; price "
        f"{price_before} -> {price_after} GP/unit\n"
        f"Bank: deposits {banking.get('deposit_change')}; interest "
        f"{banking.get('interest_accrued')}; principal repaid "
        f"{banking.get('principal_repaid')}\n"
        f"Treasury receipts: {treasury.get('receipts_total')}\n"
        f"Journal balanced: {journal.get('balanced')} | debits "
        f"{journal.get('total_debits')} | credits {journal.get('total_credits')}\n"
        + readable_line
        + f"State: {payload['prior_state_hash']} -> {payload['next_state_hash']}\n"
    )


def _render_report(payload: Mapping[str, object]) -> str:
    monthly = {
        **payload,
        "committed": True,
        "prior_state_hash": "stored",
        "next_state_hash": payload["state_hash"],
        "result": payload["latest_result"],
    }
    return _render_month_summary(monthly)


def _render_verify_summary(payload: Mapping[str, object]) -> str:
    state = "VALID" if payload["valid"] else "INVALID"
    checks = _require_mapping(payload["checks"], "verification checks")
    detail = ", ".join(f"{key}={str(value).lower()}" for key, value in checks.items())
    return (
        f"REGIONAL PREVIEW DATABASE: {state}\n"
        "Notion writes: 0 | Canonical ledger postings: 0\n"
        f"Runs: {payload['run_count']} | State: {payload['state_hash']}\n"
        f"Checks: {detail}\n"
    )


def _decode_json_row(row: sqlite3.Row | None, label: str) -> Mapping[str, object]:
    if row is None:
        raise RegionalCliError(f"database has no {label}")
    return _require_mapping(json.loads(str(row[0])), label)


def _artifact_matches(path: Path, canonical_json: str) -> bool:
    if not path.is_file():
        return False
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return _canonical_json(value) == canonical_json


def _text_matches(path: Path, expected: str) -> bool:
    try:
        return path.is_file() and path.read_text(encoding="utf-8") == expected
    except OSError:
        return False


def _write_exact_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(_json_safe(value), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _write_exact_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def _canonical_json(value: object) -> str:
    return json.dumps(
        _json_safe(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def _json_safe(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _json_safe(getattr(value, item.name)) for item in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    raise RegionalCliError(f"value is not JSON-safe: {type(value).__name__}")


def _assert_json_value(value: object, label: str) -> None:
    try:
        _canonical_json(value)
    except (RegionalCliError, TypeError, ValueError) as exc:
        raise RegionalCliError(f"{label} is not canonical JSON: {exc}") from exc


def _require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise RegionalCliError(f"{label} must be a mapping")
    return value


def _exact_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RegionalCliError(f"{label} must be an integer")
    return value


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be a positive integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def _optional_existing_path(path: Path | None, label: str) -> Path | None:
    if path is None:
        return None
    resolved = path.resolve()
    if not resolved.is_file():
        raise RegionalCliError(f"{label} path is not a file: {resolved}")
    return resolved


def _existing_database(database: Path) -> Path:
    database = database.resolve()
    if not database.is_file():
        raise RegionalCliError(f"regional database does not exist: {database}")
    return database


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
