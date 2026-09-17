"""Append-only SQLite persistence for the economy operator."""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
import json
import os
from pathlib import Path
import sqlite3
from typing import Iterator, Mapping

from .operator_codec import (
    CodecError,
    canonical_dumps,
    canonical_hash,
    run_plan_from_payload,
    snapshot_from_payload,
    snapshot_to_payload,
    verify_content_hash,
    with_content_hash,
)
from .operator_dice import validate_roll_manifest
from .scenarios import ScenarioPackage, load_scenario
from .stockflow import Snapshot, advance


SCHEMA_VERSION = 1


class StoreError(RuntimeError):
    """Raised when durable operator state is absent, conflicted, or corrupt."""


SCHEMA_SQL = """
CREATE TABLE campaign (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    campaign_id TEXT NOT NULL UNIQUE,
    scenario_id TEXT NOT NULL,
    assumption_profile_id TEXT NOT NULL,
    timeline_id TEXT NOT NULL UNIQUE,
    authority_mode TEXT NOT NULL CHECK (authority_mode = 'preview'),
    canonical INTEGER NOT NULL CHECK (canonical = 0),
    scenario_hash TEXT NOT NULL CHECK (length(scenario_hash) = 64),
    scenario_json TEXT NOT NULL,
    current_period INTEGER NOT NULL CHECK (current_period >= 0),
    current_state_hash TEXT NOT NULL CHECK (length(current_state_hash) = 64)
);

CREATE TABLE snapshots (
    state_hash TEXT PRIMARY KEY CHECK (length(state_hash) = 64),
    snapshot_id TEXT NOT NULL,
    timeline_id TEXT NOT NULL,
    period_index INTEGER NOT NULL CHECK (period_index >= 0),
    parent_state_hash TEXT REFERENCES snapshots(state_hash),
    payload_json TEXT NOT NULL,
    UNIQUE (timeline_id, period_index)
);

CREATE TABLE month_runs (
    run_hash TEXT PRIMARY KEY CHECK (length(run_hash) = 64),
    period_index INTEGER NOT NULL UNIQUE CHECK (period_index >= 1),
    request_options_hash TEXT NOT NULL CHECK (length(request_options_hash) = 64),
    request_options_json TEXT NOT NULL,
    parent_state_hash TEXT NOT NULL REFERENCES snapshots(state_hash),
    closing_state_hash TEXT NOT NULL UNIQUE REFERENCES snapshots(state_hash),
    plan_hash TEXT NOT NULL CHECK (length(plan_hash) = 64),
    roll_manifest_hash TEXT NOT NULL CHECK (length(roll_manifest_hash) = 64),
    plan_json TEXT NOT NULL,
    result_json TEXT NOT NULL
);

CREATE TABLE dice_faces (
    run_hash TEXT NOT NULL REFERENCES month_runs(run_hash),
    roll_key TEXT NOT NULL,
    die_index INTEGER NOT NULL CHECK (die_index >= 1),
    sides INTEGER NOT NULL CHECK (sides >= 2),
    face INTEGER NOT NULL CHECK (face >= 1 AND face <= sides),
    method TEXT NOT NULL,
    seed_fingerprint TEXT,
    PRIMARY KEY (run_hash, roll_key, die_index)
);

CREATE TABLE artifacts (
    run_hash TEXT NOT NULL REFERENCES month_runs(run_hash),
    kind TEXT NOT NULL CHECK (kind IN ('report_markdown', 'ledger_preview', 'notion_dry_run')),
    payload TEXT NOT NULL,
    payload_hash TEXT NOT NULL CHECK (length(payload_hash) = 64),
    PRIMARY KEY (run_hash, kind)
);

CREATE TRIGGER snapshots_no_update BEFORE UPDATE ON snapshots
BEGIN SELECT RAISE(ABORT, 'snapshots are append-only'); END;
CREATE TRIGGER snapshots_no_delete BEFORE DELETE ON snapshots
BEGIN SELECT RAISE(ABORT, 'snapshots are append-only'); END;
CREATE TRIGGER month_runs_no_update BEFORE UPDATE ON month_runs
BEGIN SELECT RAISE(ABORT, 'month runs are append-only'); END;
CREATE TRIGGER month_runs_no_delete BEFORE DELETE ON month_runs
BEGIN SELECT RAISE(ABORT, 'month runs are append-only'); END;
CREATE TRIGGER dice_faces_no_update BEFORE UPDATE ON dice_faces
BEGIN SELECT RAISE(ABORT, 'dice receipts are append-only'); END;
CREATE TRIGGER dice_faces_no_delete BEFORE DELETE ON dice_faces
BEGIN SELECT RAISE(ABORT, 'dice receipts are append-only'); END;
CREATE TRIGGER artifacts_no_update BEFORE UPDATE ON artifacts
BEGIN SELECT RAISE(ABORT, 'operator artifacts are append-only'); END;
CREATE TRIGGER artifacts_no_delete BEFORE DELETE ON artifacts
BEGIN SELECT RAISE(ABORT, 'operator artifacts are append-only'); END;
CREATE TRIGGER campaign_identity_no_update BEFORE UPDATE OF
    campaign_id, scenario_id, assumption_profile_id, timeline_id,
    authority_mode, canonical, scenario_hash, scenario_json
ON campaign
BEGIN SELECT RAISE(ABORT, 'campaign identity is immutable'); END;
CREATE TRIGGER campaign_no_delete BEFORE DELETE ON campaign
BEGIN SELECT RAISE(ABORT, 'campaign identity is immutable'); END;
"""

REQUIRED_TRIGGERS = frozenset(
    {
        "snapshots_no_update",
        "snapshots_no_delete",
        "month_runs_no_update",
        "month_runs_no_delete",
        "dice_faces_no_update",
        "dice_faces_no_delete",
        "artifacts_no_update",
        "artifacts_no_delete",
        "campaign_identity_no_update",
        "campaign_no_delete",
    }
)


def validate_database_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.suffix == ".bean" or "campaign-finance-ledger" in resolved.parts:
        raise StoreError(
            "operator state may not be written into the campaign-finance-ledger tree"
        )
    return resolved


class CampaignStore:
    """One preview campaign per explicitly named SQLite database."""

    def __init__(self, path: Path, connection: sqlite3.Connection) -> None:
        self.path = path
        self.connection = connection
        self.connection.row_factory = sqlite3.Row

    @classmethod
    def create(
        cls,
        path: Path,
        *,
        campaign_id: str,
        scenario: ScenarioPackage,
    ) -> "CampaignStore":
        path = validate_database_path(path)
        if not campaign_id.strip():
            raise StoreError("campaign ID is required")
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            reservation = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise StoreError(f"refusing to overwrite existing database: {path}") from exc
        os.close(reservation)
        try:
            connection = sqlite3.connect(path, isolation_level=None)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        store = cls(path, connection)
        try:
            store._configure()
            # ``executescript`` owns its transaction boundary under sqlite3.
            # If any later initialization step fails, the new file is removed
            # before control returns to the caller.
            connection.executescript(SCHEMA_SQL)
            with store.immediate_transaction():
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                opening = scenario.opening_snapshot()
                scenario_json = canonical_dumps(scenario.payload)
                connection.execute(
                    """
                    INSERT INTO campaign (
                        singleton, campaign_id, scenario_id, assumption_profile_id,
                        timeline_id, authority_mode, canonical, scenario_hash,
                        scenario_json, current_period, current_state_hash
                    ) VALUES (1, ?, ?, ?, ?, 'preview', 0, ?, ?, 0, ?)
                    """,
                    (
                        campaign_id,
                        scenario.scenario_id,
                        scenario.profile_id,
                        scenario.timeline_id,
                        scenario.scenario_hash,
                        scenario_json,
                        opening.state_hash,
                    ),
                )
                store._insert_snapshot(opening)
            return store
        except Exception:
            connection.close()
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    @classmethod
    def open(cls, path: Path) -> "CampaignStore":
        path = validate_database_path(path)
        if not path.is_file():
            raise StoreError(f"campaign database does not exist: {path}")
        connection = sqlite3.connect(path, isolation_level=None)
        store = cls(path, connection)
        try:
            store._configure()
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version != SCHEMA_VERSION:
                raise StoreError(
                    f"unsupported campaign database schema {version}; expected {SCHEMA_VERSION}"
                )
            store.campaign_record()
            return store
        except Exception:
            connection.close()
            raise

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "CampaignStore":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def _configure(self) -> None:
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA synchronous = FULL")
        self.connection.execute("PRAGMA journal_mode = DELETE")
        enabled = int(self.connection.execute("PRAGMA foreign_keys").fetchone()[0])
        if enabled != 1:
            raise StoreError("SQLite foreign-key enforcement could not be enabled")

    @contextmanager
    def immediate_transaction(self) -> Iterator[None]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except Exception:
            self.connection.execute("ROLLBACK")
            raise
        else:
            self.connection.execute("COMMIT")

    def campaign_record(self) -> dict[str, object]:
        try:
            row = self.connection.execute("SELECT * FROM campaign WHERE singleton = 1").fetchone()
        except sqlite3.DatabaseError as exc:
            raise StoreError(f"campaign database is unreadable: {exc}") from exc
        if row is None:
            raise StoreError("campaign database has no initialized campaign")
        payload = _load_json(row["scenario_json"], "stored scenario")
        if canonical_hash(payload) != row["scenario_hash"]:
            raise StoreError("stored scenario payload has been altered")
        scenario = load_scenario(
            row["scenario_id"],
            profile_id=row["assumption_profile_id"],
            stored_payload=payload,
        )
        if scenario.scenario_hash != row["scenario_hash"]:
            raise StoreError("stored scenario hash is inconsistent")
        result = dict(row)
        result["scenario"] = scenario
        return result

    def latest_snapshot(self) -> Snapshot:
        campaign = self.campaign_record()
        return self.load_snapshot(str(campaign["current_state_hash"]))

    def load_snapshot(self, state_hash: str) -> Snapshot:
        row = self.connection.execute(
            "SELECT * FROM snapshots WHERE state_hash = ?", (state_hash,)
        ).fetchone()
        if row is None:
            raise StoreError(f"snapshot is missing: {state_hash}")
        payload = _load_json(row["payload_json"], "stored snapshot")
        snapshot = snapshot_from_payload(payload)
        if (
            snapshot.state_hash != row["state_hash"]
            or snapshot.snapshot_id != row["snapshot_id"]
            or snapshot.timeline_id != row["timeline_id"]
            or snapshot.period_index != row["period_index"]
            or snapshot.parent_hash != row["parent_state_hash"]
        ):
            raise StoreError("stored snapshot index does not match its verified payload")
        return snapshot

    def load_run(self, period_index: int | None = None) -> dict[str, object]:
        if period_index is None:
            row = self.connection.execute(
                "SELECT * FROM month_runs ORDER BY period_index DESC LIMIT 1"
            ).fetchone()
        else:
            row = self.connection.execute(
                "SELECT * FROM month_runs WHERE period_index = ?", (period_index,)
            ).fetchone()
        if row is None:
            label = "latest" if period_index is None else str(period_index)
            raise StoreError(f"no committed run exists for period {label}")
        result = _load_json(row["result_json"], "stored month result")
        verify_content_hash(result, label="stored month result")
        if result.get("run_hash") != row["run_hash"]:
            raise StoreError("stored run hash does not match its result payload")
        semantic = dict(result)
        semantic.pop("content_hash", None)
        semantic_run_hash = semantic.pop("run_hash", None)
        if semantic_run_hash != canonical_hash(semantic):
            raise StoreError("stored run hash does not match its semantic result")
        plan = _load_json(row["plan_json"], "stored run plan")
        if canonical_hash(plan) != row["plan_hash"]:
            raise StoreError("stored run plan hash does not match its payload")
        request_options = _load_json(
            row["request_options_json"], "stored request options"
        )
        if canonical_hash(request_options) != row["request_options_hash"]:
            raise StoreError("stored request-options hash does not match its payload")
        record = dict(row)
        record["result"] = result
        record["plan"] = plan
        record["request_options"] = request_options
        return record

    def artifact(self, period_index: int | None, kind: str) -> str:
        run = self.load_run(period_index)
        row = self.connection.execute(
            "SELECT payload, payload_hash FROM artifacts WHERE run_hash = ? AND kind = ?",
            (run["run_hash"], kind),
        ).fetchone()
        if row is None:
            raise StoreError(f"stored run is missing its {kind} artifact")
        payload = str(row["payload"])
        if _text_hash(payload) != row["payload_hash"]:
            raise StoreError(f"stored {kind} artifact has been altered")
        if kind != "report_markdown":
            parsed = _load_json(payload, kind)
            verify_content_hash(parsed, label=kind)
        return payload

    def commit_run(
        self,
        *,
        period_index: int,
        expected_parent_hash: str,
        request_options: Mapping[str, object],
        closing_snapshot: Snapshot,
        plan_payload: Mapping[str, object],
        result_payload: Mapping[str, object],
        roll_manifest: Mapping[str, object],
        report_markdown: str,
        ledger_preview: Mapping[str, object],
        notion_dry_run: Mapping[str, object],
    ) -> tuple[dict[str, object], bool]:
        """Atomically append one month, returning ``(result, replayed)``."""

        plan_json = canonical_dumps(plan_payload)
        plan_hash = canonical_hash(plan_payload)
        request_options_json = canonical_dumps(request_options)
        request_options_hash = canonical_hash(request_options)
        result_json = canonical_dumps(result_payload)
        ledger_json = canonical_dumps(ledger_preview)
        notion_json = canonical_dumps(notion_dry_run)
        run_hash = result_payload.get("run_hash")
        if not isinstance(run_hash, str) or len(run_hash) != 64:
            raise StoreError("month result is missing its full run hash")
        verify_content_hash(result_payload, label="month result")
        verify_content_hash(ledger_preview, label="ledger preview")
        verify_content_hash(notion_dry_run, label="Notion dry run")
        try:
            validate_roll_manifest(roll_manifest)
        except ValueError as exc:
            raise StoreError(f"invalid dice manifest: {exc}") from exc
        result_dice = result_payload.get("dice")
        replay = result_payload.get("replay")
        if not isinstance(result_dice, Mapping) or not isinstance(replay, Mapping):
            raise StoreError("month result is missing dice or replay provenance")
        if canonical_dumps(result_dice) != canonical_dumps(roll_manifest):
            raise StoreError("commit dice manifest does not match the month result")
        if replay.get("roll_manifest_hash") != roll_manifest.get("manifest_hash"):
            raise StoreError("result replay provenance has the wrong dice manifest hash")
        self._validate_request_options(
            request_options=request_options,
            period_index=period_index,
            roll_manifest=roll_manifest,
        )
        self._validate_execution_bundle(
            expected_parent_hash=expected_parent_hash,
            closing_snapshot=closing_snapshot,
            plan_payload=plan_payload,
            result_payload=result_payload,
            report_markdown=report_markdown,
            ledger_preview=ledger_preview,
            notion_dry_run=notion_dry_run,
        )

        with self.immediate_transaction():
            existing = self.connection.execute(
                "SELECT * FROM month_runs WHERE period_index = ?", (period_index,)
            ).fetchone()
            if existing is not None:
                if existing["request_options_hash"] != request_options_hash:
                    raise StoreError(
                        f"period {period_index} is already committed with different run options"
                    )
                stored = self.load_run(period_index)["result"]
                return stored, True
            campaign = self.connection.execute(
                "SELECT current_period, current_state_hash FROM campaign WHERE singleton = 1"
            ).fetchone()
            if campaign is None:
                raise StoreError("campaign disappeared during commit")
            if campaign["current_state_hash"] != expected_parent_hash:
                raise StoreError("stale parent snapshot; another month was committed first")
            if campaign["current_period"] + 1 != period_index:
                raise StoreError("month commits must advance exactly one period")
            self._insert_snapshot(closing_snapshot)
            self.connection.execute(
                """
                INSERT INTO month_runs (
                    run_hash, period_index, request_options_hash, parent_state_hash,
                    closing_state_hash, plan_hash, roll_manifest_hash,
                    request_options_json, plan_json, result_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_hash,
                    period_index,
                    request_options_hash,
                    expected_parent_hash,
                    closing_snapshot.state_hash,
                    plan_hash,
                    roll_manifest["manifest_hash"],
                    request_options_json,
                    plan_json,
                    result_json,
                ),
            )
            for roll in roll_manifest.get("rolls", []):
                if not isinstance(roll, Mapping):
                    raise StoreError("dice manifest contains a malformed roll")
                faces = roll.get("dice")
                if not isinstance(faces, list):
                    raise StoreError("dice manifest roll is missing individual faces")
                for index, face in enumerate(faces, 1):
                    self.connection.execute(
                        """
                        INSERT INTO dice_faces (
                            run_hash, roll_key, die_index, sides, face, method,
                            seed_fingerprint
                        ) VALUES (?, ?, ?, 6, ?, ?, ?)
                        """,
                        (
                            run_hash,
                            roll["roll_key"],
                            index,
                            face,
                            roll["method"],
                            roll.get("seed_fingerprint"),
                        ),
                    )
            for kind, payload in (
                ("report_markdown", report_markdown),
                ("ledger_preview", ledger_json),
                ("notion_dry_run", notion_json),
            ):
                self.connection.execute(
                    "INSERT INTO artifacts (run_hash, kind, payload, payload_hash) VALUES (?, ?, ?, ?)",
                    (run_hash, kind, payload, _text_hash(payload)),
                )
            self.connection.execute(
                "UPDATE campaign SET current_period = ?, current_state_hash = ? WHERE singleton = 1",
                (period_index, closing_snapshot.state_hash),
            )
        return dict(result_payload), False

    def _insert_snapshot(self, snapshot: Snapshot) -> None:
        payload = snapshot_to_payload(snapshot)
        self.connection.execute(
            """
            INSERT INTO snapshots (
                state_hash, snapshot_id, timeline_id, period_index,
                parent_state_hash, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.state_hash,
                snapshot.snapshot_id,
                snapshot.timeline_id,
                snapshot.period_index,
                snapshot.parent_hash,
                canonical_dumps(payload),
            ),
        )

    def _validate_execution_bundle(
        self,
        *,
        expected_parent_hash: str,
        closing_snapshot: Snapshot,
        plan_payload: Mapping[str, object],
        result_payload: Mapping[str, object],
        report_markdown: str,
        ledger_preview: Mapping[str, object],
        notion_dry_run: Mapping[str, object],
    ) -> None:
        """Replay a proposed/stored bundle and compare every derived artifact."""

        # Local import avoids weakening the operator/store dependency boundary
        # while still giving persistence an independent semantic replay gate.
        from .operator import (
            _ledger_preview,
            _notion_dry_run,
            _result_semantic_body,
            _roll_manifest_event,
            render_report,
        )

        campaign = self.campaign_record()
        scenario: ScenarioPackage = campaign["scenario"]
        parent = self.load_snapshot(expected_parent_hash)
        plan = run_plan_from_payload(plan_payload)
        dice = result_payload.get("dice")
        if not isinstance(dice, Mapping):
            raise StoreError("month result is missing its dice manifest")
        try:
            validate_roll_manifest(dict(dice))
        except ValueError as exc:
            raise StoreError(f"invalid result dice manifest: {exc}") from exc
        expected_events = (
            (_roll_manifest_event(scenario, plan.period_index, dice),)
            if dice.get("rolls")
            else ()
        )
        expected_plan = scenario.plan(
            plan.period_index, authorizing_events=expected_events
        )
        if plan != expected_plan:
            raise StoreError("stored run plan does not match the locked scenario schedule")
        if plan.authorizing_events:
            if len(plan.authorizing_events) != 1:
                raise StoreError("preview plan may contain at most one dice-manifest event")
            event_payload = _load_json(
                plan.authorizing_events[0].payload_json,
                "stored dice-manifest event payload",
            )
            if canonical_dumps(event_payload) != canonical_dumps(dice):
                raise StoreError("dice manifest does not match its plan authorizing event")
        elif dice.get("rolls"):
            raise StoreError("resolved preview dice are not bound into the run plan")
        recomputed = advance(scenario.model(), parent, plan)
        if (
            recomputed.snapshot.state_hash != closing_snapshot.state_hash
            or recomputed.snapshot != closing_snapshot
            or closing_snapshot.parent_hash != parent.state_hash
            or closing_snapshot.period_index != plan.period_index
            or closing_snapshot.input_hash is None
        ):
            raise StoreError("closing snapshot does not match deterministic plan replay")
        semantic = _result_semantic_body(
            campaign=campaign,
            scenario=scenario,
            parent=parent,
            plan=plan,
            result=recomputed,
            roll_manifest=dice,
        )
        expected_run_hash = canonical_hash(semantic)
        expected_result = with_content_hash({**semantic, "run_hash": expected_run_hash})
        if canonical_dumps(expected_result) != canonical_dumps(result_payload):
            raise StoreError("stored month result does not match deterministic replay")
        expected_ledger = _ledger_preview(expected_result, scenario)
        expected_notion = _notion_dry_run(expected_result, scenario)
        expected_report = render_report(expected_result)
        if canonical_dumps(expected_ledger) != canonical_dumps(ledger_preview):
            raise StoreError("ledger preview does not match deterministic replay")
        if canonical_dumps(expected_notion) != canonical_dumps(notion_dry_run):
            raise StoreError("Notion dry run does not match deterministic replay")
        if expected_report != report_markdown:
            raise StoreError("monthly report does not match deterministic replay")

    def _validate_request_options(
        self,
        *,
        request_options: Mapping[str, object],
        period_index: int,
        roll_manifest: Mapping[str, object],
    ) -> None:
        expected_keys = {
            "scenario_hash",
            "period_index",
            "include_preview_checks",
            "rng_mode",
            "seed_fingerprint",
        }
        if set(request_options) != expected_keys:
            raise StoreError("request options do not match the operator schema")
        campaign = self.campaign_record()
        rolls = roll_manifest.get("rolls")
        if not isinstance(rolls, list):
            raise StoreError("dice manifest rolls must be an array")
        include_checks = request_options.get("include_preview_checks")
        if type(include_checks) is not bool or include_checks != bool(rolls):
            raise StoreError("request roll option does not match the dice manifest")
        option_period = request_options.get("period_index")
        if type(option_period) is not int:
            raise StoreError("request period must be a concrete integer")
        expected_mode = "none"
        if include_checks:
            expected_mode = (
                "seeded_preview"
                if roll_manifest.get("method") == "hmac_sha256_seeded_preview"
                else "secure"
            )
        if (
            request_options.get("scenario_hash") != campaign["scenario_hash"]
            or option_period != period_index
            or request_options.get("rng_mode") != expected_mode
            or request_options.get("seed_fingerprint")
            != roll_manifest.get("seed_fingerprint")
        ):
            raise StoreError("request options are not bound to this scenario, period, and dice")

    def history_counts(self) -> dict[str, int]:
        return {
            table: int(self.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
            for table in ("snapshots", "month_runs", "dice_faces", "artifacts")
        }

    def verify(self) -> dict[str, object]:
        integrity = str(self.connection.execute("PRAGMA integrity_check").fetchone()[0])
        foreign_keys = self.connection.execute("PRAGMA foreign_key_check").fetchall()
        campaign = self.campaign_record()
        scenario: ScenarioPackage = campaign["scenario"]
        if (
            campaign["scenario_id"] != scenario.scenario_id
            or campaign["assumption_profile_id"] != scenario.profile_id
            or campaign["timeline_id"] != scenario.timeline_id
            or campaign["authority_mode"] != "preview"
            or campaign["canonical"] != 0
        ):
            raise StoreError("campaign identity does not match its stored scenario")
        trigger_rows = self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger'"
        ).fetchall()
        triggers = {str(row["name"]) for row in trigger_rows}
        missing_triggers = REQUIRED_TRIGGERS - triggers
        if missing_triggers:
            raise StoreError(
                f"append-only safeguards are missing: {sorted(missing_triggers)}"
            )
        rows = self.connection.execute(
            "SELECT state_hash, period_index, parent_state_hash FROM snapshots ORDER BY period_index"
        ).fetchall()
        if not rows or rows[0]["period_index"] != 0 or rows[0]["parent_state_hash"] is not None:
            raise StoreError("snapshot lineage has no valid opening snapshot")
        prior_hash: str | None = None
        for expected_period, row in enumerate(rows):
            if row["period_index"] != expected_period:
                raise StoreError("snapshot lineage has a period gap")
            if expected_period and row["parent_state_hash"] != prior_hash:
                raise StoreError("snapshot lineage parent hash is broken")
            snapshot = self.load_snapshot(row["state_hash"])
            if snapshot.timeline_id != campaign["timeline_id"]:
                raise StoreError("snapshot timeline does not match campaign identity")
            scenario.model().validate_snapshot(snapshot)
            prior_hash = row["state_hash"]
        run_rows = self.connection.execute(
            "SELECT * FROM month_runs ORDER BY period_index"
        ).fetchall()
        for expected_period, row in enumerate(run_rows, 1):
            if row["period_index"] != expected_period:
                raise StoreError("month run history has a period gap")
            run = self.load_run(expected_period)
            result = run["result"]
            replay = result.get("replay")
            period = result.get("period")
            physical = result.get("physical")
            dice = result.get("dice")
            if not all(
                isinstance(item, Mapping) for item in (replay, period, physical, dice)
            ):
                raise StoreError("stored result is missing replay-verification sections")
            if (
                period.get("index") != expected_period
                or result.get("campaign_id") != campaign["campaign_id"]
                or result.get("scenario_id") != campaign["scenario_id"]
                or result.get("assumption_profile_id")
                != campaign["assumption_profile_id"]
                or result.get("timeline_id") != campaign["timeline_id"]
                or replay.get("parent_state_hash") != row["parent_state_hash"]
                or replay.get("closing_state_hash") != row["closing_state_hash"]
                or replay.get("plan_hash") != row["plan_hash"]
                or replay.get("roll_manifest_hash") != row["roll_manifest_hash"]
            ):
                raise StoreError("stored run index does not match its result provenance")
            self._validate_request_options(
                request_options=run["request_options"],
                period_index=expected_period,
                roll_manifest=dice,
            )
            residual = physical.get("conservation_residual_tons")
            try:
                residual_value = Decimal(str(residual))
            except Exception as exc:
                raise StoreError("stored conservation result is malformed") from exc
            if not residual_value.is_finite() or residual_value != 0:
                raise StoreError("stored run does not have zero material residual")
            manifest_body = dict(dice)
            manifest_hash = manifest_body.pop("manifest_hash", None)
            if manifest_hash != canonical_hash(manifest_body):
                raise StoreError("stored dice manifest hash does not match")
            try:
                validate_roll_manifest(dict(dice))
            except ValueError as exc:
                raise StoreError(f"stored dice manifest is invalid: {exc}") from exc
            stored_faces = self.connection.execute(
                """
                SELECT roll_key, die_index, sides, face, method, seed_fingerprint
                FROM dice_faces WHERE run_hash = ? ORDER BY roll_key, die_index
                """,
                (row["run_hash"],),
            ).fetchall()
            expected_faces = []
            for roll in dice.get("rolls", []):
                if not isinstance(roll, Mapping) or not isinstance(roll.get("dice"), list):
                    raise StoreError("stored dice roll is malformed")
                expected_faces.extend(
                    (
                        roll.get("roll_key"),
                        index,
                        6,
                        face,
                        roll.get("method"),
                        roll.get("seed_fingerprint"),
                    )
                    for index, face in enumerate(roll["dice"], 1)
                )
            actual_faces = [tuple(face) for face in stored_faces]
            if sorted(expected_faces) != actual_faces:
                raise StoreError("stored normalized dice faces do not match the result")
            self.artifact(expected_period, "report_markdown")
            ledger = _load_json(
                self.artifact(expected_period, "ledger_preview"), "ledger preview"
            )
            notion = _load_json(
                self.artifact(expected_period, "notion_dry_run"), "Notion dry run"
            )
            if ledger.get("run_hash") != row["run_hash"] or notion.get("run_hash") != row["run_hash"]:
                raise StoreError("stored proposal artifact is bound to the wrong run")
            self._validate_execution_bundle(
                expected_parent_hash=str(row["parent_state_hash"]),
                closing_snapshot=self.load_snapshot(str(row["closing_state_hash"])),
                plan_payload=run["plan"],
                result_payload=result,
                report_markdown=self.artifact(expected_period, "report_markdown"),
                ledger_preview=ledger,
                notion_dry_run=notion,
            )
        if int(campaign["current_period"]) != len(run_rows):
            raise StoreError("campaign current period does not match run history")
        if campaign["current_state_hash"] != prior_hash:
            raise StoreError("campaign current snapshot does not match lineage tip")
        if integrity != "ok" or foreign_keys:
            raise StoreError("SQLite integrity or foreign-key verification failed")
        return {
            "schema": "tnp.economy.verification/1",
            "status": "ok",
            "sqlite_integrity": integrity,
            "foreign_key_violations": len(foreign_keys),
            "scenario_hash_verified": True,
            "snapshot_count": len(rows),
            "run_count": len(run_rows),
            "current_period": int(campaign["current_period"]),
            "current_state_hash": str(campaign["current_state_hash"]),
            "canonical": False,
            "notion_write_capability": False,
            "ledger_post_capability": False,
        }


def _load_json(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, str):
        raise StoreError(f"{label} is not stored as text")
    try:
        payload = json.loads(value, parse_float=_reject_float, parse_constant=_reject_constant)
    except (json.JSONDecodeError, ValueError) as exc:
        raise StoreError(f"{label} is invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise StoreError(f"{label} must be a JSON object")
    return payload


def _reject_float(value: str) -> object:
    raise ValueError(f"binary float is prohibited in operator state: {value}")


def _reject_constant(value: str) -> object:
    raise ValueError(f"non-finite number is prohibited in operator state: {value}")


def _text_hash(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()
