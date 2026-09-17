"""Append-only local persistence for food-operator preview artifacts.

The store is intentionally narrow.  It can retain and export two kinds of
non-canonical decision support artifact, but it cannot write Notion, advance
campaign state, or post to a ledger.  Every stored request/result pair is
canonical-JSON encoded and bound to an immutable manifest by SHA-256.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from html import escape
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Iterator, Mapping, Sequence

from .operator_codec import CodecError, canonical_dumps, canonical_hash


FOOD_OPS_STORE_SCHEMA_VERSION = 2
FOOD_OPS_BUNDLE_SCHEMA = "tnp.food-ops.store-bundle/1"
FOOD_SECTOR_MONTH = "food_sector_month"
LONGSADDLE_PLAN = "longsaddle_plan"
AQUACULTURE_PLAN = "aquaculture_plan"
CROP_PLAN = "crop_plan"
FOOD_SECTOR_MONTH_SCHEMA = "tnp.food-sector.month-preview/1"
LONGSADDLE_PLAN_SCHEMA = "tnp.food-security.longsaddle-plan/1"
AQUACULTURE_PLAN_SCHEMA = "tnp.food-production.aquaculture-plan/1"
CROP_PLAN_SCHEMA = "tnp.food-production.crop-plan/1"
SUPPORTED_RESULT_SCHEMAS = {
    FOOD_SECTOR_MONTH: FOOD_SECTOR_MONTH_SCHEMA,
    LONGSADDLE_PLAN: LONGSADDLE_PLAN_SCHEMA,
    AQUACULTURE_PLAN: AQUACULTURE_PLAN_SCHEMA,
    CROP_PLAN: CROP_PLAN_SCHEMA,
}

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_SCENARIO_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_HASH_CHECK = "length({name}) = 64 AND {name} NOT GLOB '*[^0-9a-f]*'"
_CATEGORY_NAMES = ("Source", "Assumption", "Derived", "Unknown")
_CATEGORY_ALIASES = {
    "source": "Source",
    "sources": "Source",
    "source_fact": "Source",
    "source_facts": "Source",
    "source_input": "Source",
    "source_inputs": "Source",
    "fact": "Source",
    "facts": "Source",
    "assumption": "Assumption",
    "assumptions": "Assumption",
    "scenario_assumption": "Assumption",
    "scenario_assumptions": "Assumption",
    "user_ruling": "Assumption",
    "user_rulings": "Assumption",
    "gm_ruling": "Assumption",
    "gm_rulings": "Assumption",
    "derived": "Derived",
    "derivation": "Derived",
    "derivations": "Derived",
    "derived_result": "Derived",
    "derived_results": "Derived",
    "calculation": "Derived",
    "calculations": "Derived",
    "outcome": "Derived",
    "outcomes": "Derived",
    "summary": "Derived",
    "unknown": "Unknown",
    "unknowns": "Unknown",
    "still_unknown": "Unknown",
    "unresolved": "Unknown",
    "unresolved_field": "Unknown",
    "unresolved_fields": "Unknown",
}
_CAPABILITY_KEYS = frozenset(
    {
        "notion_write_capability",
        "notion_write_authorized",
        "ledger_write_capability",
        "ledger_post_capability",
        "ledger_post_authorized",
        "canonical_write_capability",
        "write_authorized",
        "posting_authorized",
        "postable",
    }
)


class FoodOpsStoreError(RuntimeError):
    """Raised when food-preview persistence is unsafe or inconsistent."""


@dataclass(frozen=True, slots=True)
class FoodScenarioSummary:
    """Small immutable index record returned by :meth:`list_scenarios`."""

    scenario_id: str
    kind: str
    result_schema: str
    bundle_hash: str
    request_hash: str
    result_hash: str

    def to_dict(self) -> dict[str, str]:
        return {
            "scenario_id": self.scenario_id,
            "kind": self.kind,
            "result_schema": self.result_schema,
            "bundle_hash": self.bundle_hash,
            "request_hash": self.request_hash,
            "result_hash": self.result_hash,
        }


SCHEMA_SQL = f"""
CREATE TABLE store_metadata (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    schema_version INTEGER NOT NULL CHECK (
        schema_version = {FOOD_OPS_STORE_SCHEMA_VERSION}
    ),
    store_kind TEXT NOT NULL CHECK (store_kind = 'food_operator_preview'),
    authority_mode TEXT NOT NULL CHECK (authority_mode = 'preview'),
    canonical INTEGER NOT NULL CHECK (canonical = 0),
    notion_write_capability INTEGER NOT NULL CHECK (notion_write_capability = 0),
    ledger_write_capability INTEGER NOT NULL CHECK (ledger_write_capability = 0),
    ledger_post_capability INTEGER NOT NULL CHECK (ledger_post_capability = 0)
);

CREATE TABLE food_scenarios (
    scenario_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN (
        '{FOOD_SECTOR_MONTH}', '{LONGSADDLE_PLAN}',
        '{AQUACULTURE_PLAN}', '{CROP_PLAN}'
    )),
    result_schema TEXT NOT NULL,
    bundle_hash TEXT NOT NULL UNIQUE CHECK (
        {_HASH_CHECK.format(name='bundle_hash')}
    ),
    request_hash TEXT NOT NULL CHECK ({_HASH_CHECK.format(name='request_hash')}),
    result_hash TEXT NOT NULL CHECK ({_HASH_CHECK.format(name='result_hash')}),
    request_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    authority_mode TEXT NOT NULL CHECK (authority_mode = 'preview'),
    canonical INTEGER NOT NULL CHECK (canonical = 0),
    notion_write_capability INTEGER NOT NULL CHECK (notion_write_capability = 0),
    ledger_write_capability INTEGER NOT NULL CHECK (ledger_write_capability = 0),
    ledger_post_capability INTEGER NOT NULL CHECK (ledger_post_capability = 0)
);

CREATE TRIGGER store_metadata_no_update BEFORE UPDATE ON store_metadata
BEGIN SELECT RAISE(ABORT, 'food store identity is immutable'); END;
CREATE TRIGGER store_metadata_no_delete BEFORE DELETE ON store_metadata
BEGIN SELECT RAISE(ABORT, 'food store identity is immutable'); END;
CREATE TRIGGER store_metadata_no_replace BEFORE INSERT ON store_metadata
WHEN EXISTS (SELECT 1 FROM store_metadata WHERE singleton = NEW.singleton)
BEGIN SELECT RAISE(ABORT, 'food store identity is append-only'); END;

CREATE TRIGGER food_scenarios_no_update BEFORE UPDATE ON food_scenarios
BEGIN SELECT RAISE(ABORT, 'food scenarios are append-only'); END;
CREATE TRIGGER food_scenarios_no_delete BEFORE DELETE ON food_scenarios
BEGIN SELECT RAISE(ABORT, 'food scenarios are append-only'); END;
CREATE TRIGGER food_scenarios_no_replace BEFORE INSERT ON food_scenarios
WHEN EXISTS (
    SELECT 1 FROM food_scenarios
    WHERE scenario_id = NEW.scenario_id OR bundle_hash = NEW.bundle_hash
)
BEGIN SELECT RAISE(ABORT, 'food scenarios are append-only'); END;
"""


def _normalize_schema_sql(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FoodOpsStoreError("food store schema contains an object without SQL")
    return " ".join(value.split())


def _schema_objects(
    connection: sqlite3.Connection,
) -> tuple[tuple[str, str, str, str], ...]:
    rows = connection.execute(
        """
        SELECT type, name, tbl_name, sql
        FROM sqlite_master
        WHERE name NOT LIKE 'sqlite_%'
        ORDER BY type, name
        """
    ).fetchall()
    return tuple(
        (str(row[0]), str(row[1]), str(row[2]), _normalize_schema_sql(row[3]))
        for row in rows
    )


def _expected_schema_objects() -> tuple[tuple[str, str, str, str], ...]:
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(SCHEMA_SQL)
        return _schema_objects(connection)
    finally:
        connection.close()


EXPECTED_SCHEMA_OBJECTS = _expected_schema_objects()


def _find_repository_root() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".git").exists():
            return parent
    return None


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _is_repository_test_or_temp(path: Path, repository_root: Path) -> bool:
    relative = path.relative_to(repository_root)
    allowed_parts = {"test", "tests", "tmp", "temp", ".tmp", ".pytest_cache"}
    return any(part.lower() in allowed_parts for part in relative.parts[:-1])


def validate_food_ops_database_path(path: Path) -> Path:
    """Resolve a database path and keep durable state out of source control."""

    if not isinstance(path, Path):
        raise FoodOpsStoreError("food-operator database path must be a concrete Path")
    resolved = path.expanduser().resolve()
    if resolved.suffix.lower() == ".bean" or "campaign-finance-ledger" in {
        part.lower() for part in resolved.parts
    }:
        raise FoodOpsStoreError(
            "food preview state may not be written into a canonical ledger tree"
        )
    repository_root = _find_repository_root()
    if (
        repository_root is not None
        and _is_relative_to(resolved, repository_root)
        and not _is_repository_test_or_temp(resolved, repository_root)
    ):
        raise FoodOpsStoreError(
            "food-operator databases must live outside the repository "
            "(repository test/temp paths are the only exception)"
        )
    return resolved


class FoodOpsStore:
    """One append-only collection of local food-operation previews."""

    def __init__(self, path: Path, connection: sqlite3.Connection) -> None:
        self.path = path
        self.connection = connection
        self.connection.row_factory = sqlite3.Row

    @classmethod
    def create(cls, path: Path) -> "FoodOpsStore":
        path = validate_food_ops_database_path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            reservation = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise FoodOpsStoreError(
                f"refusing to overwrite existing food-operator database: {path}"
            ) from exc
        os.close(reservation)
        try:
            connection = sqlite3.connect(path, isolation_level=None, timeout=30)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        store = cls(path, connection)
        try:
            store._configure()
            connection.executescript(SCHEMA_SQL)
            store._verify_safeguard_schema()
            with store.immediate_transaction():
                connection.execute(
                    f"PRAGMA user_version = {FOOD_OPS_STORE_SCHEMA_VERSION}"
                )
                connection.execute(
                    """
                    INSERT INTO store_metadata (
                        singleton, schema_version, store_kind, authority_mode,
                        canonical, notion_write_capability,
                        ledger_write_capability, ledger_post_capability
                    ) VALUES (1, ?, 'food_operator_preview', 'preview', 0, 0, 0, 0)
                    """,
                    (FOOD_OPS_STORE_SCHEMA_VERSION,),
                )
            return store
        except Exception:
            connection.close()
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    @classmethod
    def open(cls, path: Path) -> "FoodOpsStore":
        path = validate_food_ops_database_path(path)
        if not path.is_file():
            raise FoodOpsStoreError(f"food-operator database does not exist: {path}")
        connection = sqlite3.connect(path, isolation_level=None, timeout=30)
        store = cls(path, connection)
        try:
            store._configure()
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version != FOOD_OPS_STORE_SCHEMA_VERSION:
                raise FoodOpsStoreError(
                    f"unsupported food-operator database schema {version}; "
                    f"expected {FOOD_OPS_STORE_SCHEMA_VERSION}"
                )
            store.metadata_record()
            store._verify_safeguard_schema()
            return store
        except Exception:
            connection.close()
            raise

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "FoodOpsStore":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def _configure(self) -> None:
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA recursive_triggers = ON")
        self.connection.execute("PRAGMA synchronous = FULL")
        self.connection.execute("PRAGMA journal_mode = DELETE")
        self.connection.execute("PRAGMA busy_timeout = 30000")
        foreign_keys = int(self.connection.execute("PRAGMA foreign_keys").fetchone()[0])
        recursive = int(
            self.connection.execute("PRAGMA recursive_triggers").fetchone()[0]
        )
        if foreign_keys != 1 or recursive != 1:
            raise FoodOpsStoreError(
                "SQLite foreign-key or recursive-trigger enforcement could not be enabled"
            )

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

    def metadata_record(self) -> dict[str, object]:
        try:
            row = self.connection.execute(
                "SELECT * FROM store_metadata WHERE singleton = 1"
            ).fetchone()
        except sqlite3.DatabaseError as exc:
            raise FoodOpsStoreError(f"food-operator database is unreadable: {exc}") from exc
        if row is None:
            raise FoodOpsStoreError("food-operator database has no store metadata")
        record = dict(row)
        expected = {
            "singleton": 1,
            "schema_version": FOOD_OPS_STORE_SCHEMA_VERSION,
            "store_kind": "food_operator_preview",
            "authority_mode": "preview",
            "canonical": 0,
            "notion_write_capability": 0,
            "ledger_write_capability": 0,
            "ledger_post_capability": 0,
        }
        if record != expected:
            raise FoodOpsStoreError("food store metadata violates the safety contract")
        return record

    def _verify_safeguard_schema(self) -> None:
        try:
            actual = _schema_objects(self.connection)
        except sqlite3.DatabaseError as exc:
            raise FoodOpsStoreError(f"food store schema is unreadable: {exc}") from exc
        if actual != EXPECTED_SCHEMA_OBJECTS:
            raise FoodOpsStoreError(
                "food store append-only safeguards are missing or have changed"
            )

    def save_scenario(
        self,
        scenario_id: str,
        kind: str,
        request: Mapping[str, object],
        result: Mapping[str, object],
    ) -> tuple[dict[str, object], bool]:
        """Persist one exact bundle; an exact retry is returned as a no-op."""

        normalized_id = _require_scenario_id(scenario_id)
        expected_schema = _require_kind(kind)
        request_body = _canonical_mapping(request, "food scenario request")
        result_body = _canonical_mapping(result, "food scenario result")
        if result_body.get("schema") != expected_schema:
            raise FoodOpsStoreError(
                f"{kind} result must use schema {expected_schema}"
            )
        _verify_embedded_content_hash(request_body, "food scenario request")
        _verify_embedded_content_hash(result_body, "food scenario result")
        _verify_preview_safety(result_body)

        request_hash = canonical_hash(request_body)
        result_hash = canonical_hash(result_body)
        manifest = {
            "schema": FOOD_OPS_BUNDLE_SCHEMA,
            "scenario_id": normalized_id,
            "kind": kind,
            "result_schema": expected_schema,
            "request_hash": request_hash,
            "result_hash": result_hash,
            "authority_mode": "preview",
            "canonical": False,
            "notion_write_capability": False,
            "ledger_write_capability": False,
            "ledger_post_capability": False,
        }
        bundle_hash = canonical_hash(manifest)
        request_json = canonical_dumps(request_body)
        result_json = canonical_dumps(result_body)
        manifest_json = canonical_dumps(manifest)

        try:
            with self.immediate_transaction():
                self._verify_safeguard_schema()
                existing = self.connection.execute(
                    "SELECT * FROM food_scenarios WHERE scenario_id = ?",
                    (normalized_id,),
                ).fetchone()
                if existing is not None:
                    if (
                        existing["kind"] == kind
                        and existing["result_schema"] == expected_schema
                        and existing["bundle_hash"] == bundle_hash
                        and existing["request_hash"] == request_hash
                        and existing["result_hash"] == result_hash
                        and existing["request_json"] == request_json
                        and existing["result_json"] == result_json
                        and existing["manifest_json"] == manifest_json
                    ):
                        return self._record_from_row(existing), True
                    raise FoodOpsStoreError(
                        "scenario ID is already stored with different immutable content"
                    )
                self.connection.execute(
                    """
                    INSERT INTO food_scenarios (
                        scenario_id, kind, result_schema, bundle_hash,
                        request_hash, result_hash, request_json, result_json,
                        manifest_json, authority_mode, canonical,
                        notion_write_capability, ledger_write_capability,
                        ledger_post_capability
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'preview', 0, 0, 0, 0)
                    """,
                    (
                        normalized_id,
                        kind,
                        expected_schema,
                        bundle_hash,
                        request_hash,
                        result_hash,
                        request_json,
                        result_json,
                        manifest_json,
                    ),
                )
                inserted = self.connection.execute(
                    "SELECT * FROM food_scenarios WHERE scenario_id = ?",
                    (normalized_id,),
                ).fetchone()
                if inserted is None:
                    raise FoodOpsStoreError("food scenario insert was not durable")
                return self._record_from_row(inserted), False
        except FoodOpsStoreError:
            raise
        except sqlite3.DatabaseError as exc:
            raise FoodOpsStoreError(
                f"food scenario save failed atomically: {exc}"
            ) from exc

    def save_food_sector_month(
        self,
        scenario_id: str,
        request: Mapping[str, object],
        result: Mapping[str, object],
    ) -> tuple[dict[str, object], bool]:
        return self.save_scenario(scenario_id, FOOD_SECTOR_MONTH, request, result)

    def save_longsaddle_plan(
        self,
        scenario_id: str,
        request: Mapping[str, object],
        result: Mapping[str, object],
    ) -> tuple[dict[str, object], bool]:
        return self.save_scenario(scenario_id, LONGSADDLE_PLAN, request, result)

    def save_aquaculture_plan(
        self,
        scenario_id: str,
        request: Mapping[str, object],
        result: Mapping[str, object],
    ) -> tuple[dict[str, object], bool]:
        return self.save_scenario(scenario_id, AQUACULTURE_PLAN, request, result)

    def save_crop_plan(
        self,
        scenario_id: str,
        request: Mapping[str, object],
        result: Mapping[str, object],
    ) -> tuple[dict[str, object], bool]:
        return self.save_scenario(scenario_id, CROP_PLAN, request, result)

    def get_scenario(self, scenario_id: str) -> dict[str, object]:
        normalized_id = _require_scenario_id(scenario_id)
        try:
            row = self.connection.execute(
                "SELECT * FROM food_scenarios WHERE scenario_id = ?",
                (normalized_id,),
            ).fetchone()
        except sqlite3.DatabaseError as exc:
            raise FoodOpsStoreError(f"food scenario lookup failed: {exc}") from exc
        if row is None:
            raise FoodOpsStoreError(f"food scenario is missing: {normalized_id}")
        return self._record_from_row(row)

    def load_scenario(self, scenario_id: str) -> dict[str, object]:
        """Compatibility alias using the store's verified get path."""

        return self.get_scenario(scenario_id)

    def list_scenarios(self, kind: str | None = None) -> list[dict[str, str]]:
        if kind is None:
            rows = self.connection.execute(
                "SELECT * FROM food_scenarios ORDER BY rowid"
            ).fetchall()
        else:
            _require_kind(kind)
            rows = self.connection.execute(
                "SELECT * FROM food_scenarios WHERE kind = ? ORDER BY rowid",
                (kind,),
            ).fetchall()
        summaries: list[dict[str, str]] = []
        for row in rows:
            record = self._record_from_row(row)
            summaries.append(
                FoodScenarioSummary(
                    scenario_id=str(record["scenario_id"]),
                    kind=str(record["kind"]),
                    result_schema=str(record["result_schema"]),
                    bundle_hash=str(record["bundle_hash"]),
                    request_hash=str(record["request_hash"]),
                    result_hash=str(record["result_hash"]),
                ).to_dict()
            )
        return summaries

    def counts(self) -> dict[str, int]:
        total = int(self.connection.execute("SELECT count(*) FROM food_scenarios").fetchone()[0])
        counts = {"food_scenarios": total}
        for kind in SUPPORTED_RESULT_SCHEMAS:
            counts[kind] = int(
                self.connection.execute(
                    "SELECT count(*) FROM food_scenarios WHERE kind = ?", (kind,)
                ).fetchone()[0]
            )
        return counts

    def verify(self) -> dict[str, object]:
        """Verify schema guards, SQLite integrity, and every content hash."""

        self._verify_safeguard_schema()
        self.metadata_record()
        quick_check = str(self.connection.execute("PRAGMA quick_check").fetchone()[0])
        if quick_check != "ok":
            raise FoodOpsStoreError(f"SQLite quick check failed: {quick_check}")
        rows = self.connection.execute(
            "SELECT * FROM food_scenarios ORDER BY rowid"
        ).fetchall()
        bundle_hashes: list[str] = []
        for row in rows:
            record = self._record_from_row(row)
            bundle_hashes.append(str(record["bundle_hash"]))
        counts = self.counts()
        return {
            "status": "ok",
            "schema_version": FOOD_OPS_STORE_SCHEMA_VERSION,
            "scenario_count": counts["food_scenarios"],
            "food_sector_month_count": counts[FOOD_SECTOR_MONTH],
            "longsaddle_plan_count": counts[LONGSADDLE_PLAN],
            "aquaculture_plan_count": counts[AQUACULTURE_PLAN],
            "crop_plan_count": counts[CROP_PLAN],
            "bundle_hashes": bundle_hashes,
            "authority_mode": "preview",
            "canonical": False,
            "notion_write_capability": False,
            "ledger_write_capability": False,
            "ledger_post_capability": False,
        }

    def export_markdown(self, scenario_id: str) -> str:
        return render_decision_brief_markdown(self.get_scenario(scenario_id))

    def export_html(self, scenario_id: str) -> str:
        return render_decision_brief_html(self.get_scenario(scenario_id))

    def _record_from_row(self, row: sqlite3.Row) -> dict[str, object]:
        scenario_id = _require_scenario_id(row["scenario_id"])
        kind = str(row["kind"])
        expected_schema = _require_kind(kind)
        request = _load_canonical_json(row["request_json"], "stored food request")
        result = _load_canonical_json(row["result_json"], "stored food result")
        manifest = _load_canonical_json(row["manifest_json"], "stored food manifest")
        if not isinstance(request, Mapping):
            raise FoodOpsStoreError("stored food request is not an object")
        if not isinstance(result, Mapping):
            raise FoodOpsStoreError("stored food result is not an object")
        if not isinstance(manifest, Mapping):
            raise FoodOpsStoreError("stored food manifest is not an object")
        if result.get("schema") != expected_schema:
            raise FoodOpsStoreError("stored food result schema does not match its kind")
        _verify_embedded_content_hash(request, "stored food request")
        _verify_embedded_content_hash(result, "stored food result")
        _verify_preview_safety(result)
        request_hash = canonical_hash(request)
        result_hash = canonical_hash(result)
        expected_manifest = {
            "schema": FOOD_OPS_BUNDLE_SCHEMA,
            "scenario_id": scenario_id,
            "kind": kind,
            "result_schema": expected_schema,
            "request_hash": request_hash,
            "result_hash": result_hash,
            "authority_mode": "preview",
            "canonical": False,
            "notion_write_capability": False,
            "ledger_write_capability": False,
            "ledger_post_capability": False,
        }
        bundle_hash = canonical_hash(expected_manifest)
        expected_scalars = {
            "scenario_id": scenario_id,
            "kind": kind,
            "result_schema": expected_schema,
            "bundle_hash": bundle_hash,
            "request_hash": request_hash,
            "result_hash": result_hash,
            "authority_mode": "preview",
            "canonical": 0,
            "notion_write_capability": 0,
            "ledger_write_capability": 0,
            "ledger_post_capability": 0,
        }
        for key, value in expected_scalars.items():
            if row[key] != value:
                raise FoodOpsStoreError(
                    f"stored food scenario index does not match its payload: {key}"
                )
        if dict(manifest) != expected_manifest:
            raise FoodOpsStoreError("stored food manifest does not match its payload")
        return {
            **expected_scalars,
            "canonical": False,
            "notion_write_capability": False,
            "ledger_write_capability": False,
            "ledger_post_capability": False,
            "request": dict(request),
            "result": dict(result),
            "manifest": dict(manifest),
        }


def _require_scenario_id(value: object) -> str:
    if not isinstance(value, str) or not _SCENARIO_ID_RE.fullmatch(value):
        raise FoodOpsStoreError(
            "scenario ID must be 1-128 characters using letters, digits, . _ : or -"
        )
    return value


def _require_kind(kind: object) -> str:
    if not isinstance(kind, str) or kind not in SUPPORTED_RESULT_SCHEMAS:
        allowed = ", ".join(sorted(SUPPORTED_RESULT_SCHEMAS))
        raise FoodOpsStoreError(f"food artifact kind must be one of: {allowed}")
    return SUPPORTED_RESULT_SCHEMAS[kind]


def _canonical_mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise FoodOpsStoreError(f"{label} must be an object")
    try:
        encoded = canonical_dumps(value)
    except (CodecError, TypeError, ValueError) as exc:
        raise FoodOpsStoreError(f"{label} is not exact canonical JSON: {exc}") from exc
    decoded = _load_canonical_json(encoded, label)
    if not isinstance(decoded, dict):
        raise FoodOpsStoreError(f"{label} must be an object")
    return decoded


def _load_canonical_json(value: object, label: str) -> object:
    if not isinstance(value, str):
        raise FoodOpsStoreError(f"{label} is not stored as JSON text")

    def no_duplicate_pairs(pairs: Sequence[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in pairs:
            if key in result:
                raise FoodOpsStoreError(f"{label} contains duplicate JSON key {key!r}")
            result[key] = item
        return result

    def reject_float(token: str) -> object:
        raise FoodOpsStoreError(
            f"{label} contains binary-ambiguous JSON number {token}; use exact text"
        )

    try:
        decoded = json.loads(
            value,
            object_pairs_hook=no_duplicate_pairs,
            parse_float=reject_float,
            parse_constant=reject_float,
        )
    except FoodOpsStoreError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise FoodOpsStoreError(f"{label} is invalid JSON: {exc}") from exc
    try:
        if canonical_dumps(decoded) != value:
            raise FoodOpsStoreError(f"{label} is not canonical JSON")
    except CodecError as exc:
        raise FoodOpsStoreError(f"{label} is not canonical JSON: {exc}") from exc
    return decoded


def _verify_embedded_content_hash(payload: Mapping[str, object], label: str) -> None:
    if "content_hash" not in payload:
        return
    content_hash = payload.get("content_hash")
    if not isinstance(content_hash, str) or not _HASH_RE.fullmatch(content_hash):
        raise FoodOpsStoreError(f"{label} has an invalid embedded content hash")
    body = dict(payload)
    del body["content_hash"]
    if canonical_hash(body) != content_hash:
        raise FoodOpsStoreError(f"{label} embedded content hash does not match")


def _verify_preview_safety(value: object, path: str = "result") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in _CAPABILITY_KEYS and item not in (False, 0, None):
                raise FoodOpsStoreError(
                    f"food preview cannot enable write/post capability at {path}.{key}"
                )
            if key == "canonical" and item not in (False, 0, None):
                raise FoodOpsStoreError(
                    f"food preview cannot claim canonical state at {path}.{key}"
                )
            _verify_preview_safety(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _verify_preview_safety(item, f"{path}[{index}]")


def _category_for(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return _CATEGORY_ALIASES.get(normalized)


def _human_label(value: object) -> str:
    text = str(value).replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else "Value"


def _display_scalar(value: object) -> str:
    if value is None:
        return "Not established"
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return str(value)


def _entry_lines(value: object, *, prefix: str = "") -> list[str]:
    if isinstance(value, Mapping):
        preferred = value.get("label") or value.get("name") or value.get("title")
        description = (
            value.get("description")
            or value.get("text")
            or value.get("value")
            or value.get("result")
        )
        if preferred is not None and not isinstance(description, (Mapping, list)):
            return [f"{_display_scalar(preferred)}: {_display_scalar(description)}"]
        lines: list[str] = []
        ignored = {"classification", "authority", "category", "provenance"}
        for key, item in value.items():
            if key in ignored:
                continue
            label = f"{prefix}{_human_label(key)}"
            if isinstance(item, Mapping):
                lines.extend(_entry_lines(item, prefix=f"{label} — "))
            elif isinstance(item, list):
                nested = _entry_lines(item, prefix=f"{label} — ")
                lines.extend(nested or [f"{label}: None recorded"])
            else:
                lines.append(f"{label}: {_display_scalar(item)}")
        return lines
    if isinstance(value, list):
        lines: list[str] = []
        for item in value:
            if isinstance(item, (Mapping, list)):
                lines.extend(_entry_lines(item, prefix=prefix))
            else:
                lines.append(f"{prefix}{_display_scalar(item)}")
        return lines
    return [f"{prefix}{_display_scalar(value)}"]


def _decision_sections(result: Mapping[str, object]) -> dict[str, list[str]]:
    sections = {name: [] for name in _CATEGORY_NAMES}
    consumed: set[str] = set()
    candidates: list[Mapping[str, object]] = []
    decision_brief = result.get("decision_brief")
    if isinstance(decision_brief, Mapping):
        candidates.append(decision_brief)
    provenance = result.get("provenance")
    if isinstance(provenance, Mapping):
        candidates.append(provenance)
    candidates.append(result)

    for candidate in candidates:
        for key, item in candidate.items():
            category = _category_for(key)
            if category is None:
                continue
            sections[category].extend(_entry_lines(item))
            if candidate is result:
                consumed.add(str(key))

    def collect_classified(value: object, *, depth: int = 0) -> None:
        if isinstance(value, Mapping):
            category = next(
                (
                    _category_for(value.get(key))
                    for key in ("classification", "authority", "category", "provenance")
                    if _category_for(value.get(key)) is not None
                ),
                None,
            )
            # A whole preview may carry ``authority=scenario_assumption`` to
            # describe its non-canonical status.  That is not permission to
            # mislabel every source fact and derived value as an assumption.
            if category is not None and depth > 0:
                sections[category].extend(_entry_lines(value))
                return
            for item in value.values():
                collect_classified(item, depth=depth + 1)
        elif isinstance(value, list):
            for item in value:
                collect_classified(item, depth=depth + 1)

    collect_classified(result)
    metadata = {
        "schema",
        "content_hash",
        "mode",
        "canonical",
        "authority",
        "decision_brief",
        "provenance",
        *consumed,
    }
    fallback = {key: value for key, value in result.items() if key not in metadata}
    if not sections["Derived"] and fallback:
        sections["Derived"].extend(_entry_lines(fallback))
    for category in _CATEGORY_NAMES:
        unique: list[str] = []
        seen: set[str] = set()
        for line in sections[category]:
            if line not in seen:
                seen.add(line)
                unique.append(line)
        sections[category] = unique or ["None recorded in this preview."]
    return sections


def _brief_bundle(value: Mapping[str, object]) -> tuple[str, str, str, Mapping[str, object]]:
    result = value.get("result")
    if isinstance(result, Mapping):
        scenario_id = str(value.get("scenario_id", "unspecified"))
        kind = str(value.get("kind", "food_preview"))
        bundle_hash = str(value.get("bundle_hash", "not persisted"))
        return scenario_id, kind, bundle_hash, result
    schema = value.get("schema")
    if schema == FOOD_SECTOR_MONTH_SCHEMA:
        kind = FOOD_SECTOR_MONTH
    elif schema == LONGSADDLE_PLAN_SCHEMA:
        kind = LONGSADDLE_PLAN
    else:
        raise FoodOpsStoreError("decision brief requires a stored bundle or food result")
    return "unspecified", kind, "not persisted", value


def render_decision_brief_markdown(bundle: Mapping[str, object]) -> str:
    """Render a readable Markdown brief without changing the stored artifact."""

    scenario_id, kind, bundle_hash, result = _brief_bundle(bundle)
    sections = _decision_sections(result)
    lines = [
        "# Food Operations Decision Brief",
        "",
        f"- Scenario: `{scenario_id}`",
        f"- Artifact: `{kind}`",
        f"- Bundle hash: `{bundle_hash}`",
        "- Status: local preview; non-canonical; no Notion or ledger write capability",
        "",
    ]
    for category in _CATEGORY_NAMES:
        lines.extend([f"## {category}", ""])
        lines.extend(f"- {line}" for line in sections[category])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_decision_brief_html(bundle: Mapping[str, object]) -> str:
    """Render a standalone, escaped HTML decision brief."""

    scenario_id, kind, bundle_hash, result = _brief_bundle(bundle)
    sections = _decision_sections(result)
    section_html = "\n".join(
        "<section>"
        f"<h2>{escape(category)}</h2>"
        "<ul>"
        + "".join(f"<li>{escape(line)}</li>" for line in sections[category])
        + "</ul></section>"
        for category in _CATEGORY_NAMES
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Food Operations Decision Brief — {escape(scenario_id)}</title>
  <style>
    :root {{ color-scheme: light; font-family: Georgia, serif; }}
    body {{ max-width: 62rem; margin: 0 auto; padding: 2rem; color: #211f1a; background: #f7f2e8; line-height: 1.55; }}
    header, section {{ background: #fffdf7; border: 1px solid #c9bea8; border-radius: .4rem; padding: 1rem 1.25rem; margin: 0 0 1rem; }}
    h1, h2 {{ color: #45351f; margin-top: 0; }}
    dt {{ font-weight: 700; }} dd {{ margin: 0 0 .45rem; overflow-wrap: anywhere; }}
    li + li {{ margin-top: .35rem; }}
    .notice {{ border-left: .35rem solid #8a6a32; padding-left: .75rem; }}
  </style>
</head>
<body>
  <header>
    <h1>Food Operations Decision Brief</h1>
    <dl>
      <dt>Scenario</dt><dd>{escape(scenario_id)}</dd>
      <dt>Artifact</dt><dd>{escape(kind)}</dd>
      <dt>Bundle hash</dt><dd>{escape(bundle_hash)}</dd>
    </dl>
    <p class="notice">Local preview only. Non-canonical. No Notion or ledger write capability.</p>
  </header>
  {section_html}
</body>
</html>
"""


# Short module-level names are useful to callers that already hold a bundle.
export_markdown = render_decision_brief_markdown
export_html = render_decision_brief_html
