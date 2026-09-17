"""Append-only persistence for source-bound business preview artifacts.

This store is deliberately separate from :mod:`baen_economy.operator_store`.
The existing operator database is a two-period Operation Laden Table state
machine; registry receipts and one-row business previews have a different
identity and lifecycle.  Keeping the stores separate prevents a business
preview from changing Laden replay hashes or weakening its verification path.

The module has no Notion connector, write method, ledger writer, or Beancount
exporter.  It stores only offline registry receipts and local, non-canonical
preview artifacts.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Iterator, Mapping

from .business_capacity import (
    BRICKWORKS_SOURCE_RECORD_ID,
    build_brickworks_partial_capacity,
)
from .business_month import (
    BUSINESS_MONTH_SCHEMA,
    BUSINESS_PROFILE_ID,
    render_business_report,
    validate_business_preview,
)
from .notion_read import BUSINESS_REGISTRY_DATA_SOURCE
from .operator_codec import CodecError, canonical_dumps, canonical_hash
from .registry_export import (
    REGISTRY_EXPECTED_ROW_COUNT,
    REGISTRY_PROPERTY_NAMES,
    RegistryExportError,
    VerifiedRegistryExport,
    verify_registry_export,
)


BUSINESS_STORE_SCHEMA_VERSION = 1
BUSINESS_RUN_BUNDLE_SCHEMA = "tnp.business.store-run-bundle/1"
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_ARTIFACT_KIND_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,79}$")


class BusinessStoreError(RuntimeError):
    """Raised when business-preview persistence is unsafe or inconsistent."""


@dataclass(frozen=True, slots=True)
class ArtifactValue:
    """An explicitly typed artifact accepted by :meth:`BusinessStore.commit_run`."""

    media_type: str
    payload: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.media_type, str)
            or not self.media_type.strip()
            or self.media_type != self.media_type.strip()
        ):
            raise BusinessStoreError("artifact media type must be canonical non-empty text")
        if not isinstance(self.payload, str):
            raise BusinessStoreError("artifact payload must be text")


_HASH_CHECK = "length({name}) = 64 AND {name} NOT GLOB '*[^0-9a-f]*'"


SCHEMA_SQL = f"""
CREATE TABLE store_metadata (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    schema_version INTEGER NOT NULL CHECK (schema_version = {BUSINESS_STORE_SCHEMA_VERSION}),
    store_kind TEXT NOT NULL CHECK (store_kind = 'business_preview'),
    notion_write_capability INTEGER NOT NULL CHECK (notion_write_capability = 0),
    ledger_post_capability INTEGER NOT NULL CHECK (ledger_post_capability = 0)
);

CREATE TABLE registry_snapshots (
    snapshot_hash TEXT PRIMARY KEY CHECK ({_HASH_CHECK.format(name='snapshot_hash')}),
    source_schema_hash TEXT NOT NULL CHECK ({_HASH_CHECK.format(name='source_schema_hash')}),
    data_source_url TEXT NOT NULL CHECK (
        data_source_url = '{BUSINESS_REGISTRY_DATA_SOURCE}'
    ),
    row_count INTEGER NOT NULL CHECK (row_count = {REGISTRY_EXPECTED_ROW_COUNT}),
    property_count INTEGER NOT NULL CHECK (property_count = {len(REGISTRY_PROPERTY_NAMES)}),
    property_names_json TEXT NOT NULL
);

CREATE TABLE registry_rows (
    snapshot_hash TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    row_hash TEXT NOT NULL CHECK ({_HASH_CHECK.format(name='row_hash')}),
    entity_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    row_json TEXT NOT NULL,
    PRIMARY KEY (snapshot_hash, source_record_id),
    UNIQUE (snapshot_hash, source_record_id, row_hash),
    FOREIGN KEY (snapshot_hash) REFERENCES registry_snapshots(snapshot_hash)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE registry_exports (
    export_hash TEXT PRIMARY KEY CHECK ({_HASH_CHECK.format(name='export_hash')}),
    snapshot_hash TEXT NOT NULL,
    source_schema_hash TEXT NOT NULL CHECK ({_HASH_CHECK.format(name='source_schema_hash')}),
    content_hash TEXT NOT NULL CHECK ({_HASH_CHECK.format(name='content_hash')}),
    data_source_url TEXT NOT NULL CHECK (
        data_source_url = '{BUSINESS_REGISTRY_DATA_SOURCE}'
    ),
    captured_at TEXT NOT NULL,
    row_count INTEGER NOT NULL CHECK (row_count = {REGISTRY_EXPECTED_ROW_COUNT}),
    property_count INTEGER NOT NULL CHECK (property_count = {len(REGISTRY_PROPERTY_NAMES)}),
    export_json TEXT NOT NULL,
    UNIQUE (export_hash, snapshot_hash),
    UNIQUE (data_source_url, captured_at),
    FOREIGN KEY (snapshot_hash) REFERENCES registry_snapshots(snapshot_hash)
);

CREATE TABLE business_runs (
    run_hash TEXT PRIMARY KEY CHECK ({_HASH_CHECK.format(name='run_hash')}),
    request_hash TEXT NOT NULL CHECK ({_HASH_CHECK.format(name='request_hash')}),
    result_hash TEXT NOT NULL CHECK ({_HASH_CHECK.format(name='result_hash')}),
    registry_export_hash TEXT NOT NULL,
    registry_snapshot_hash TEXT NOT NULL,
    registry_source_schema_hash TEXT NOT NULL CHECK (
        {_HASH_CHECK.format(name='registry_source_schema_hash')}
    ),
    source_record_id TEXT NOT NULL,
    source_row_hash TEXT NOT NULL CHECK ({_HASH_CHECK.format(name='source_row_hash')}),
    profile_id TEXT NOT NULL,
    period_key TEXT NOT NULL,
    request_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    artifact_count INTEGER NOT NULL CHECK (artifact_count >= 1),
    canonical INTEGER NOT NULL CHECK (canonical = 0),
    notion_writes INTEGER NOT NULL CHECK (notion_writes = 0),
    ledger_posts INTEGER NOT NULL CHECK (ledger_posts = 0),
    UNIQUE (registry_export_hash, source_record_id, profile_id, period_key),
    FOREIGN KEY (registry_export_hash, registry_snapshot_hash)
        REFERENCES registry_exports(export_hash, snapshot_hash),
    FOREIGN KEY (registry_snapshot_hash, source_record_id, source_row_hash)
        REFERENCES registry_rows(snapshot_hash, source_record_id, row_hash)
);

CREATE TABLE business_artifacts (
    run_hash TEXT NOT NULL,
    kind TEXT NOT NULL,
    media_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    payload_hash TEXT NOT NULL CHECK ({_HASH_CHECK.format(name='payload_hash')}),
    PRIMARY KEY (run_hash, kind),
    FOREIGN KEY (run_hash) REFERENCES business_runs(run_hash)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE TRIGGER store_metadata_no_update BEFORE UPDATE ON store_metadata
BEGIN SELECT RAISE(ABORT, 'business store identity is immutable'); END;
CREATE TRIGGER store_metadata_no_delete BEFORE DELETE ON store_metadata
BEGIN SELECT RAISE(ABORT, 'business store identity is immutable'); END;
CREATE TRIGGER store_metadata_no_replace BEFORE INSERT ON store_metadata
WHEN EXISTS (SELECT 1 FROM store_metadata WHERE singleton = NEW.singleton)
BEGIN SELECT RAISE(ABORT, 'business store identity is append-only'); END;

CREATE TRIGGER registry_snapshots_no_update BEFORE UPDATE ON registry_snapshots
BEGIN SELECT RAISE(ABORT, 'registry snapshots are append-only'); END;
CREATE TRIGGER registry_snapshots_no_delete BEFORE DELETE ON registry_snapshots
BEGIN SELECT RAISE(ABORT, 'registry snapshots are append-only'); END;
CREATE TRIGGER registry_snapshots_no_replace BEFORE INSERT ON registry_snapshots
WHEN EXISTS (
    SELECT 1 FROM registry_snapshots WHERE snapshot_hash = NEW.snapshot_hash
)
BEGIN SELECT RAISE(ABORT, 'registry snapshots are append-only'); END;
CREATE TRIGGER registry_snapshot_requires_rows BEFORE INSERT ON registry_snapshots
WHEN (
    SELECT count(*) FROM registry_rows
    WHERE snapshot_hash = NEW.snapshot_hash
) != NEW.row_count
BEGIN SELECT RAISE(ABORT, 'registry snapshot row set is incomplete'); END;

CREATE TRIGGER registry_rows_no_update BEFORE UPDATE ON registry_rows
BEGIN SELECT RAISE(ABORT, 'registry rows are append-only'); END;
CREATE TRIGGER registry_rows_no_delete BEFORE DELETE ON registry_rows
BEGIN SELECT RAISE(ABORT, 'registry rows are append-only'); END;
CREATE TRIGGER registry_rows_no_replace BEFORE INSERT ON registry_rows
WHEN EXISTS (
    SELECT 1 FROM registry_rows
    WHERE snapshot_hash = NEW.snapshot_hash
      AND source_record_id = NEW.source_record_id
)
BEGIN SELECT RAISE(ABORT, 'registry rows are append-only'); END;
CREATE TRIGGER registry_rows_no_late_insert BEFORE INSERT ON registry_rows
WHEN EXISTS (
    SELECT 1 FROM registry_snapshots
    WHERE snapshot_hash = NEW.snapshot_hash
)
BEGIN SELECT RAISE(ABORT, 'sealed registry snapshot cannot gain rows'); END;

CREATE TRIGGER registry_exports_no_update BEFORE UPDATE ON registry_exports
BEGIN SELECT RAISE(ABORT, 'registry export receipts are append-only'); END;
CREATE TRIGGER registry_exports_no_delete BEFORE DELETE ON registry_exports
BEGIN SELECT RAISE(ABORT, 'registry export receipts are append-only'); END;
CREATE TRIGGER registry_exports_no_replace BEFORE INSERT ON registry_exports
WHEN EXISTS (
    SELECT 1 FROM registry_exports
    WHERE export_hash = NEW.export_hash
       OR (data_source_url = NEW.data_source_url AND captured_at = NEW.captured_at)
)
BEGIN SELECT RAISE(ABORT, 'registry export receipts are append-only'); END;

CREATE TRIGGER business_runs_no_update BEFORE UPDATE ON business_runs
BEGIN SELECT RAISE(ABORT, 'business runs are append-only'); END;
CREATE TRIGGER business_runs_no_delete BEFORE DELETE ON business_runs
BEGIN SELECT RAISE(ABORT, 'business runs are append-only'); END;
CREATE TRIGGER business_runs_no_replace BEFORE INSERT ON business_runs
WHEN EXISTS (
    SELECT 1 FROM business_runs
    WHERE run_hash = NEW.run_hash
       OR (
           registry_export_hash = NEW.registry_export_hash
           AND source_record_id = NEW.source_record_id
           AND profile_id = NEW.profile_id
           AND period_key = NEW.period_key
       )
)
BEGIN SELECT RAISE(ABORT, 'business runs are append-only'); END;
CREATE TRIGGER business_run_requires_artifacts BEFORE INSERT ON business_runs
WHEN (
    SELECT count(*) FROM business_artifacts
    WHERE run_hash = NEW.run_hash
) != NEW.artifact_count
BEGIN SELECT RAISE(ABORT, 'business run artifact bundle is incomplete'); END;

CREATE TRIGGER business_artifacts_no_update BEFORE UPDATE ON business_artifacts
BEGIN SELECT RAISE(ABORT, 'business artifacts are append-only'); END;
CREATE TRIGGER business_artifacts_no_delete BEFORE DELETE ON business_artifacts
BEGIN SELECT RAISE(ABORT, 'business artifacts are append-only'); END;
CREATE TRIGGER business_artifacts_no_replace BEFORE INSERT ON business_artifacts
WHEN EXISTS (
    SELECT 1 FROM business_artifacts
    WHERE run_hash = NEW.run_hash AND kind = NEW.kind
)
BEGIN SELECT RAISE(ABORT, 'business artifacts are append-only'); END;
CREATE TRIGGER business_artifacts_no_late_insert BEFORE INSERT ON business_artifacts
WHEN EXISTS (
    SELECT 1 FROM business_runs
    WHERE run_hash = NEW.run_hash
)
BEGIN SELECT RAISE(ABORT, 'sealed business run cannot gain artifacts'); END;
"""


def _normalize_schema_sql(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BusinessStoreError("business schema contains an object without SQL")
    return " ".join(value.split())


def _schema_objects(connection: sqlite3.Connection) -> tuple[tuple[str, str, str, str], ...]:
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


def _build_expected_schema_objects() -> tuple[tuple[str, str, str, str], ...]:
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(SCHEMA_SQL)
        return _schema_objects(connection)
    finally:
        connection.close()


EXPECTED_SCHEMA_OBJECTS = _build_expected_schema_objects()
REQUIRED_TRIGGERS = frozenset(
    name for kind, name, _table, _sql in EXPECTED_SCHEMA_OBJECTS if kind == "trigger"
)


def validate_business_database_path(path: Path) -> Path:
    """Resolve a safe local state path outside the campaign ledger tree."""

    if not isinstance(path, Path):
        raise BusinessStoreError("business database path must be a concrete Path")
    resolved = path.expanduser().resolve()
    if resolved.suffix == ".bean" or "campaign-finance-ledger" in resolved.parts:
        raise BusinessStoreError(
            "business preview state may not be written into the campaign-finance-ledger tree"
        )
    return resolved


class BusinessStore:
    """An append-only registry and business-preview workspace."""

    def __init__(self, path: Path, connection: sqlite3.Connection) -> None:
        self.path = path
        self.connection = connection
        self.connection.row_factory = sqlite3.Row

    @classmethod
    def create(
        cls,
        path: Path,
        *,
        registry_payload: Mapping[str, object] | None = None,
    ) -> "BusinessStore":
        """Create a new store, optionally importing one receipt atomically.

        If schema creation, metadata insertion, or the optional import fails,
        the newly reserved file is removed before the exception is returned.
        """

        verified: VerifiedRegistryExport | None = None
        canonical_payload: dict[str, object] | None = None
        if registry_payload is not None:
            canonical_payload, verified = _verify_registry_payload(registry_payload)
        path = validate_business_database_path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            reservation = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise BusinessStoreError(f"refusing to overwrite existing database: {path}") from exc
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
                connection.execute(f"PRAGMA user_version = {BUSINESS_STORE_SCHEMA_VERSION}")
                connection.execute(
                    """
                    INSERT INTO store_metadata (
                        singleton, schema_version, store_kind,
                        notion_write_capability, ledger_post_capability
                    ) VALUES (1, ?, 'business_preview', 0, 0)
                    """,
                    (BUSINESS_STORE_SCHEMA_VERSION,),
                )
                if verified is not None and canonical_payload is not None:
                    store._import_verified(canonical_payload, verified)
            return store
        except Exception:
            connection.close()
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    @classmethod
    def create_from_export(cls, path: Path, export_path: Path) -> "BusinessStore":
        return cls.create(path, registry_payload=_load_registry_payload(export_path))

    @classmethod
    def open(cls, path: Path) -> "BusinessStore":
        path = validate_business_database_path(path)
        if not path.is_file():
            raise BusinessStoreError(f"business database does not exist: {path}")
        connection = sqlite3.connect(path, isolation_level=None, timeout=30)
        store = cls(path, connection)
        try:
            store._configure()
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version != BUSINESS_STORE_SCHEMA_VERSION:
                raise BusinessStoreError(
                    f"unsupported business database schema {version}; "
                    f"expected {BUSINESS_STORE_SCHEMA_VERSION}"
                )
            store.metadata_record()
            store._verify_safeguard_schema()
            return store
        except Exception:
            connection.close()
            raise

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "BusinessStore":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def _configure(self) -> None:
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA recursive_triggers = ON")
        self.connection.execute("PRAGMA synchronous = FULL")
        self.connection.execute("PRAGMA journal_mode = DELETE")
        self.connection.execute("PRAGMA busy_timeout = 30000")
        enabled = int(self.connection.execute("PRAGMA foreign_keys").fetchone()[0])
        recursive = int(
            self.connection.execute("PRAGMA recursive_triggers").fetchone()[0]
        )
        if enabled != 1 or recursive != 1:
            raise BusinessStoreError(
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
            raise BusinessStoreError(f"business database is unreadable: {exc}") from exc
        if row is None:
            raise BusinessStoreError("business database has no store metadata")
        record = dict(row)
        if (
            record.get("schema_version") != BUSINESS_STORE_SCHEMA_VERSION
            or record.get("store_kind") != "business_preview"
            or record.get("notion_write_capability") != 0
            or record.get("ledger_post_capability") != 0
        ):
            raise BusinessStoreError("business store metadata violates the safety contract")
        return record

    def _verify_safeguard_schema(self) -> None:
        """Require the exact reviewed tables and trigger bodies, not just names."""

        try:
            foreign_keys = int(
                self.connection.execute("PRAGMA foreign_keys").fetchone()[0]
            )
            recursive = int(
                self.connection.execute("PRAGMA recursive_triggers").fetchone()[0]
            )
            actual = _schema_objects(self.connection)
        except sqlite3.DatabaseError as exc:
            raise BusinessStoreError(f"business safeguard schema is unreadable: {exc}") from exc
        if foreign_keys != 1 or recursive != 1:
            raise BusinessStoreError("append-only connection safeguards are disabled")
        if actual != EXPECTED_SCHEMA_OBJECTS:
            raise BusinessStoreError(
                "append-only safeguards are missing or their SQL has drifted"
            )

    def import_registry_path(self, path: Path) -> tuple[dict[str, object], bool]:
        return self.import_registry(_load_registry_payload(path))

    def import_registry(
        self, payload: Mapping[str, object]
    ) -> tuple[dict[str, object], bool]:
        """Append a verified offline registry receipt.

        An exact retry returns the already verified receipt.  A different
        payload claiming the same source capture time is an immutable conflict.
        """

        canonical_payload, verified = _verify_registry_payload(payload)
        try:
            with self.immediate_transaction():
                self._verify_safeguard_schema()
                return self._import_verified(canonical_payload, verified)
        except sqlite3.DatabaseError as exc:
            raise BusinessStoreError(f"registry import failed atomically: {exc}") from exc

    def _import_verified(
        self,
        payload: dict[str, object],
        verified: VerifiedRegistryExport,
    ) -> tuple[dict[str, object], bool]:
        existing = self.connection.execute(
            "SELECT export_hash, export_json FROM registry_exports WHERE export_hash = ?",
            (verified.export_hash,),
        ).fetchone()
        if existing is not None:
            if existing["export_json"] != canonical_dumps(payload):
                raise BusinessStoreError(
                    "registry export hash is already stored with different immutable content"
                )
            loaded = self.load_registry_export(verified.export_hash)
            if loaded.export_hash != verified.export_hash:
                raise BusinessStoreError("stored exact registry retry does not match")
            return self._registry_summary(loaded), True

        capture = self.connection.execute(
            """
            SELECT export_hash FROM registry_exports
            WHERE data_source_url = ? AND captured_at = ?
            """,
            (BUSINESS_REGISTRY_DATA_SOURCE, verified.read_snapshot.captured_at),
        ).fetchone()
        if capture is not None:
            raise BusinessStoreError(
                "registry capture is already stored with different immutable content"
            )

        snapshot_row = self.connection.execute(
            "SELECT snapshot_hash FROM registry_snapshots WHERE snapshot_hash = ?",
            (verified.snapshot_hash,),
        ).fetchone()
        if snapshot_row is None:
            for source_record_id in sorted(verified.rows_by_source_id):
                row = verified.rows_by_source_id[source_record_id]
                entity_name = row.get("Entity")
                source_url = row.get("url")
                if not isinstance(entity_name, str) or not isinstance(source_url, str):
                    raise BusinessStoreError("verified registry row lost its source identity")
                self.connection.execute(
                    """
                    INSERT INTO registry_rows (
                        snapshot_hash, source_record_id, row_hash,
                        entity_name, source_url, row_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        verified.snapshot_hash,
                        source_record_id,
                        verified.row_hashes[source_record_id],
                        entity_name,
                        source_url,
                        canonical_dumps(row),
                    ),
                )
            self.connection.execute(
                """
                INSERT INTO registry_snapshots (
                    snapshot_hash, source_schema_hash, data_source_url, row_count,
                    property_count, property_names_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    verified.snapshot_hash,
                    verified.source_schema_hash,
                    BUSINESS_REGISTRY_DATA_SOURCE,
                    verified.read_snapshot.expected_row_count,
                    len(verified.property_names),
                    canonical_dumps(list(verified.property_names)),
                ),
            )
        else:
            self._verify_snapshot_rows(verified)

        self.connection.execute(
            """
            INSERT INTO registry_exports (
                export_hash, snapshot_hash, source_schema_hash, content_hash, data_source_url,
                captured_at, row_count, property_count, export_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                verified.export_hash,
                verified.snapshot_hash,
                verified.source_schema_hash,
                verified.content_hash,
                BUSINESS_REGISTRY_DATA_SOURCE,
                verified.read_snapshot.captured_at,
                verified.read_snapshot.expected_row_count,
                len(verified.property_names),
                canonical_dumps(payload),
            ),
        )
        return self._registry_summary(verified), False

    def load_registry_export(self, export_hash: str) -> VerifiedRegistryExport:
        _require_hash(export_hash, "registry export hash")
        row = self.connection.execute(
            "SELECT * FROM registry_exports WHERE export_hash = ?", (export_hash,)
        ).fetchone()
        if row is None:
            raise BusinessStoreError(f"registry export is missing: {export_hash}")
        payload = _load_json_text(row["export_json"], "stored registry export")
        try:
            verified = verify_registry_export(payload)
        except (RegistryExportError, CodecError, ValueError) as exc:
            raise BusinessStoreError(f"stored registry export is invalid: {exc}") from exc
        if canonical_dumps(payload) != row["export_json"]:
            raise BusinessStoreError("stored registry export is not canonical JSON")
        if (
            verified.export_hash != row["export_hash"]
            or verified.snapshot_hash != row["snapshot_hash"]
            or verified.source_schema_hash != row["source_schema_hash"]
            or verified.content_hash != row["content_hash"]
            or verified.read_snapshot.data_source_url != row["data_source_url"]
            or verified.read_snapshot.captured_at != row["captured_at"]
            or verified.read_snapshot.expected_row_count != row["row_count"]
            or len(verified.property_names) != row["property_count"]
        ):
            raise BusinessStoreError("stored registry export index does not match its payload")
        self._verify_snapshot_rows(verified)
        return verified

    def _verify_snapshot_rows(self, verified: VerifiedRegistryExport) -> None:
        snapshot = self.connection.execute(
            "SELECT * FROM registry_snapshots WHERE snapshot_hash = ?",
            (verified.snapshot_hash,),
        ).fetchone()
        if snapshot is None:
            raise BusinessStoreError("verified export has no persisted semantic snapshot")
        expected_property_names = canonical_dumps(list(verified.property_names))
        if (
            snapshot["source_schema_hash"] != verified.source_schema_hash
            or snapshot["data_source_url"] != BUSINESS_REGISTRY_DATA_SOURCE
            or snapshot["row_count"] != verified.read_snapshot.expected_row_count
            or snapshot["property_count"] != len(verified.property_names)
            or snapshot["property_names_json"] != expected_property_names
        ):
            raise BusinessStoreError("stored registry snapshot metadata has drifted")
        rows = self.connection.execute(
            """
            SELECT source_record_id, row_hash, entity_name, source_url, row_json
            FROM registry_rows WHERE snapshot_hash = ? ORDER BY source_record_id
            """,
            (verified.snapshot_hash,),
        ).fetchall()
        if len(rows) != verified.read_snapshot.expected_row_count:
            raise BusinessStoreError("stored registry snapshot row count has drifted")
        actual_ids = {str(row["source_record_id"]) for row in rows}
        if actual_ids != set(verified.rows_by_source_id):
            raise BusinessStoreError("stored registry snapshot row identity set has drifted")
        for stored in rows:
            source_record_id = str(stored["source_record_id"])
            source = verified.rows_by_source_id[source_record_id]
            expected_json = canonical_dumps(source)
            if (
                stored["row_hash"] != verified.row_hashes[source_record_id]
                or stored["entity_name"] != source["Entity"]
                or stored["source_url"] != source["url"]
                or stored["row_json"] != expected_json
            ):
                raise BusinessStoreError(
                    f"stored registry row has drifted: {source_record_id}"
                )

    def commit_run(
        self,
        *,
        registry_export_hash: str,
        source_record_id: str,
        profile_id: str,
        period_key: str,
        request: Mapping[str, object],
        result: Mapping[str, object],
        artifacts: Mapping[str, object],
    ) -> tuple[dict[str, object], bool]:
        """Atomically append one source-bound non-canonical preview bundle."""

        _require_hash(registry_export_hash, "registry export hash")
        _require_text(source_record_id, "source record ID")
        _require_text(profile_id, "business profile ID")
        _require_text(period_key, "business period key")
        if not isinstance(request, Mapping):
            raise BusinessStoreError("business run request must be an object")
        if not isinstance(result, Mapping):
            raise BusinessStoreError("business run result must be an object")
        try:
            request_options = _load_json_text(
                canonical_dumps(dict(request)), "business run request options"
            )
            result_body = _load_json_text(
                canonical_dumps(dict(result)), "business run result"
            )
        except (CodecError, TypeError, ValueError) as exc:
            raise BusinessStoreError(
                f"business run request or result is not canonicalizable: {exc}"
            ) from exc
        if result_body.get("canonical") is not False:
            raise BusinessStoreError(
                "business run result must be explicitly non-canonical"
            )
        normalized_artifacts = _normalize_artifacts(artifacts)

        verified = self.load_registry_export(registry_export_hash)
        if source_record_id not in verified.rows_by_source_id:
            raise BusinessStoreError(
                f"registry export has no source row {source_record_id}"
            )
        snapshot_hash = verified.snapshot_hash
        row_hash = verified.row_hashes[source_record_id]
        bound_request = {
            "schema": "tnp.business.store-request/1",
            "registry_export_hash": registry_export_hash,
            "registry_snapshot_hash": snapshot_hash,
            "registry_source_schema_hash": verified.source_schema_hash,
            "source_record_id": source_record_id,
            "source_row_hash": row_hash,
            "profile_id": profile_id,
            "period_key": period_key,
            "options": request_options,
        }
        request_hash = canonical_hash(bound_request)
        _validate_month_bundle_semantics(
            verified=verified,
            source_record_id=source_record_id,
            profile_id=profile_id,
            period_key=period_key,
            request_options=request_options,
            result=result_body,
            artifacts=normalized_artifacts,
        )
        result_hash = canonical_hash(result_body)
        artifact_manifest = [
            {
                "kind": kind,
                "media_type": artifact.media_type,
                "payload_hash": _text_hash(artifact.payload),
            }
            for kind, artifact in sorted(normalized_artifacts.items())
        ]
        manifest = {
            "schema": BUSINESS_RUN_BUNDLE_SCHEMA,
            "registry_export_hash": registry_export_hash,
            "registry_snapshot_hash": snapshot_hash,
            "registry_source_schema_hash": verified.source_schema_hash,
            "source_record_id": source_record_id,
            "source_row_hash": row_hash,
            "profile_id": profile_id,
            "period_key": period_key,
            "request_hash": request_hash,
            "result_hash": result_hash,
            "artifacts": artifact_manifest,
        }
        run_hash = canonical_hash(manifest)
        request_json = canonical_dumps(bound_request)
        result_json = canonical_dumps(result_body)
        manifest_json = canonical_dumps(manifest)
        expected_artifacts = {
            kind: {
                "media_type": artifact.media_type,
                "payload": artifact.payload,
                "payload_hash": _text_hash(artifact.payload),
            }
            for kind, artifact in normalized_artifacts.items()
        }

        try:
            with self.immediate_transaction():
                self._verify_safeguard_schema()
                existing = self.connection.execute(
                    """
                    SELECT run_hash FROM business_runs
                    WHERE registry_export_hash = ? AND source_record_id = ?
                      AND profile_id = ? AND period_key = ?
                    """,
                    (registry_export_hash, source_record_id, profile_id, period_key),
                ).fetchone()
                if existing is not None:
                    if existing["run_hash"] != run_hash:
                        raise BusinessStoreError(
                            "business period is already committed with different immutable content"
                        )
                    loaded = self.load_run(run_hash)
                    if (
                        canonical_dumps(loaded["request"]) != request_json
                        or canonical_dumps(loaded["result"]) != result_json
                        or canonical_dumps(loaded["manifest"]) != manifest_json
                        or loaded["artifacts"] != expected_artifacts
                    ):
                        raise BusinessStoreError(
                            "business run hash is already stored with different immutable content"
                        )
                    return loaded, True
                collision = self.connection.execute(
                    "SELECT 1 FROM business_runs WHERE run_hash = ?", (run_hash,)
                ).fetchone()
                if collision is not None:
                    raise BusinessStoreError("business run hash collides with another logical run")

                # Artifacts are inserted before their parent.  The deferred FK
                # and the parent finalization trigger make the bundle atomic and
                # prevent any artifact from being appended after sealing.
                for kind, artifact in sorted(normalized_artifacts.items()):
                    self.connection.execute(
                        """
                        INSERT INTO business_artifacts (
                            run_hash, kind, media_type, payload, payload_hash
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            run_hash,
                            kind,
                            artifact.media_type,
                            artifact.payload,
                            _text_hash(artifact.payload),
                        ),
                    )
                self.connection.execute(
                    """
                    INSERT INTO business_runs (
                        run_hash, request_hash, result_hash,
                        registry_export_hash, registry_snapshot_hash,
                        registry_source_schema_hash,
                        source_record_id, source_row_hash, profile_id, period_key,
                        request_json, result_json, manifest_json, artifact_count,
                        canonical, notion_writes, ledger_posts
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0)
                    """,
                    (
                        run_hash,
                        request_hash,
                        result_hash,
                        registry_export_hash,
                        snapshot_hash,
                        verified.source_schema_hash,
                        source_record_id,
                        row_hash,
                        profile_id,
                        period_key,
                        request_json,
                        result_json,
                        manifest_json,
                        len(normalized_artifacts),
                    ),
                )
            return self.load_run(run_hash), False
        except sqlite3.DatabaseError as exc:
            raise BusinessStoreError(f"business run commit failed atomically: {exc}") from exc

    def load_run(self, run_hash: str) -> dict[str, object]:
        _require_hash(run_hash, "business run hash")
        row = self.connection.execute(
            "SELECT * FROM business_runs WHERE run_hash = ?", (run_hash,)
        ).fetchone()
        if row is None:
            raise BusinessStoreError(f"business run is missing: {run_hash}")
        request = _load_json_text(row["request_json"], "stored business request")
        result = _load_json_text(row["result_json"], "stored business result")
        manifest = _load_json_text(row["manifest_json"], "stored business manifest")
        if (
            canonical_dumps(request) != row["request_json"]
            or canonical_dumps(result) != row["result_json"]
            or canonical_dumps(manifest) != row["manifest_json"]
        ):
            raise BusinessStoreError("stored business run JSON is not canonical")
        if canonical_hash(request) != row["request_hash"]:
            raise BusinessStoreError("stored business request hash does not match")
        if canonical_hash(result) != row["result_hash"]:
            raise BusinessStoreError("stored business result hash does not match")
        if result.get("canonical") is not False:
            raise BusinessStoreError(
                "stored business result is not explicitly non-canonical"
            )

        artifacts: dict[str, dict[str, str]] = {}
        artifact_manifest: list[dict[str, str]] = []
        artifact_rows = self.connection.execute(
            """
            SELECT kind, media_type, payload, payload_hash
            FROM business_artifacts WHERE run_hash = ? ORDER BY kind
            """,
            (run_hash,),
        ).fetchall()
        if len(artifact_rows) != row["artifact_count"]:
            raise BusinessStoreError("stored business artifact count does not match")
        for artifact in artifact_rows:
            payload = str(artifact["payload"])
            payload_hash = _text_hash(payload)
            if payload_hash != artifact["payload_hash"]:
                raise BusinessStoreError("stored business artifact hash does not match")
            kind = str(artifact["kind"])
            media_type = str(artifact["media_type"])
            artifacts[kind] = {
                "media_type": media_type,
                "payload": payload,
                "payload_hash": payload_hash,
            }
            artifact_manifest.append(
                {
                    "kind": kind,
                    "media_type": media_type,
                    "payload_hash": payload_hash,
                }
            )
        expected_manifest = {
            "schema": BUSINESS_RUN_BUNDLE_SCHEMA,
            "registry_export_hash": row["registry_export_hash"],
            "registry_snapshot_hash": row["registry_snapshot_hash"],
            "registry_source_schema_hash": row["registry_source_schema_hash"],
            "source_record_id": row["source_record_id"],
            "source_row_hash": row["source_row_hash"],
            "profile_id": row["profile_id"],
            "period_key": row["period_key"],
            "request_hash": row["request_hash"],
            "result_hash": row["result_hash"],
            "artifacts": artifact_manifest,
        }
        if manifest != expected_manifest or canonical_hash(expected_manifest) != run_hash:
            raise BusinessStoreError("stored business run manifest or hash does not match")
        expected_request = {
            "schema": "tnp.business.store-request/1",
            "registry_export_hash": row["registry_export_hash"],
            "registry_snapshot_hash": row["registry_snapshot_hash"],
            "registry_source_schema_hash": row["registry_source_schema_hash"],
            "source_record_id": row["source_record_id"],
            "source_row_hash": row["source_row_hash"],
            "profile_id": row["profile_id"],
            "period_key": row["period_key"],
            "options": request.get("options"),
        }
        if request != expected_request or not isinstance(request.get("options"), dict):
            raise BusinessStoreError("stored business request binding does not match its index")
        if row["canonical"] != 0 or row["notion_writes"] != 0 or row["ledger_posts"] != 0:
            raise BusinessStoreError("stored business run violates preview-only safeguards")
        verified = self.load_registry_export(str(row["registry_export_hash"]))
        _validate_month_bundle_semantics(
            verified=verified,
            source_record_id=str(row["source_record_id"]),
            profile_id=str(row["profile_id"]),
            period_key=str(row["period_key"]),
            request_options=request["options"],
            result=result,
            artifacts={
                kind: ArtifactValue(value["media_type"], value["payload"])
                for kind, value in artifacts.items()
            },
        )
        return {
            "run_hash": run_hash,
            "request_hash": str(row["request_hash"]),
            "result_hash": str(row["result_hash"]),
            "registry_export_hash": str(row["registry_export_hash"]),
            "registry_snapshot_hash": str(row["registry_snapshot_hash"]),
            "registry_source_schema_hash": str(row["registry_source_schema_hash"]),
            "source_record_id": str(row["source_record_id"]),
            "source_row_hash": str(row["source_row_hash"]),
            "profile_id": str(row["profile_id"]),
            "period_key": str(row["period_key"]),
            "request": request,
            "result": result,
            "manifest": manifest,
            "artifacts": artifacts,
            "canonical": False,
            "notion_writes": 0,
            "ledger_posts": 0,
        }

    def latest_registry_export(self) -> VerifiedRegistryExport:
        """Load the most recently captured verified registry receipt."""

        row = self.connection.execute(
            """
            SELECT export_hash FROM registry_exports
            ORDER BY captured_at DESC, export_hash DESC LIMIT 1
            """
        ).fetchone()
        if row is None:
            raise BusinessStoreError("business store has no registry export")
        return self.load_registry_export(str(row["export_hash"]))

    def latest_run(self) -> dict[str, object]:
        """Load the last locally committed immutable business bundle."""

        row = self.connection.execute(
            "SELECT run_hash FROM business_runs ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
        if row is None:
            raise BusinessStoreError("business store has no committed run")
        return self.load_run(str(row["run_hash"]))

    def artifact(self, run_hash: str, kind: str) -> str:
        """Return one verified stored artifact payload for operator display."""

        if not isinstance(kind, str) or not _ARTIFACT_KIND_RE.fullmatch(kind):
            raise BusinessStoreError(f"invalid business artifact kind: {kind!r}")
        run = self.load_run(run_hash)
        try:
            artifact = run["artifacts"][kind]
        except KeyError as exc:
            raise BusinessStoreError(
                f"business run is missing its {kind} artifact"
            ) from exc
        return str(artifact["payload"])

    def counts(self) -> dict[str, int]:
        return {
            table: int(
                self.connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            )
            for table in (
                "registry_snapshots",
                "registry_rows",
                "registry_exports",
                "business_runs",
                "business_artifacts",
            )
        }

    def verify(self) -> dict[str, object]:
        """Verify SQLite integrity, immutable guards, and every semantic hash."""

        try:
            integrity = str(self.connection.execute("PRAGMA integrity_check").fetchone()[0])
            foreign_keys = self.connection.execute("PRAGMA foreign_key_check").fetchall()
            self.metadata_record()
            self._verify_safeguard_schema()

            export_rows = self.connection.execute(
                "SELECT export_hash FROM registry_exports ORDER BY export_hash"
            ).fetchall()
            verified_by_snapshot: dict[str, VerifiedRegistryExport] = {}
            for export_row in export_rows:
                verified = self.load_registry_export(str(export_row["export_hash"]))
                prior = verified_by_snapshot.get(verified.snapshot_hash)
                if prior is not None and (
                    prior.row_hashes != verified.row_hashes
                    or prior.property_names != verified.property_names
                ):
                    raise BusinessStoreError(
                        "one semantic snapshot has conflicting registry receipts"
                    )
                verified_by_snapshot[verified.snapshot_hash] = verified

            snapshot_rows = self.connection.execute(
                "SELECT snapshot_hash FROM registry_snapshots ORDER BY snapshot_hash"
            ).fetchall()
            snapshot_hashes = {str(row["snapshot_hash"]) for row in snapshot_rows}
            if snapshot_hashes != set(verified_by_snapshot):
                raise BusinessStoreError(
                    "registry snapshot exists without exactly verified export provenance"
                )

            run_rows = self.connection.execute(
                "SELECT run_hash FROM business_runs ORDER BY run_hash"
            ).fetchall()
            for run_row in run_rows:
                run = self.load_run(str(run_row["run_hash"]))
                verified = self.load_registry_export(run["registry_export_hash"])
                source_record_id = run["source_record_id"]
                if (
                    run["registry_snapshot_hash"] != verified.snapshot_hash
                    or run["registry_source_schema_hash"]
                    != verified.source_schema_hash
                    or source_record_id not in verified.rows_by_source_id
                    or run["source_row_hash"] != verified.row_hashes[source_record_id]
                ):
                    raise BusinessStoreError(
                        "business run is not bound to its exact verified source row"
                    )
                _validate_month_bundle_semantics(
                    verified=verified,
                    source_record_id=str(source_record_id),
                    profile_id=str(run["profile_id"]),
                    period_key=str(run["period_key"]),
                    request_options=run["request"]["options"],
                    result=run["result"],
                    artifacts={
                        kind: ArtifactValue(
                            value["media_type"], value["payload"]
                        )
                        for kind, value in run["artifacts"].items()
                    },
                )

            if integrity != "ok" or foreign_keys:
                raise BusinessStoreError(
                    "SQLite integrity or foreign-key verification failed"
                )
            counts = self.counts()
            return {
                "schema": "tnp.business.store-verification/1",
                "status": "ok",
                "sqlite_integrity": integrity,
                "foreign_key_violations": len(foreign_keys),
                "schema_version": BUSINESS_STORE_SCHEMA_VERSION,
                "registry_snapshot_count": counts["registry_snapshots"],
                "registry_row_count": counts["registry_rows"],
                "registry_export_count": counts["registry_exports"],
                "business_run_count": counts["business_runs"],
                "business_artifact_count": counts["business_artifacts"],
                "canonical": False,
                "notion_write_capability": False,
                "ledger_post_capability": False,
            }
        except sqlite3.DatabaseError as exc:
            raise BusinessStoreError(f"business database verification failed: {exc}") from exc

    @staticmethod
    def _registry_summary(verified: VerifiedRegistryExport) -> dict[str, object]:
        return {
            "schema": "tnp.business.registry-import/1",
            "status": "verified_and_persisted",
            "export_hash": verified.export_hash,
            "snapshot_hash": verified.snapshot_hash,
            "source_schema_hash": verified.source_schema_hash,
            "content_hash": verified.content_hash,
            "captured_at": verified.read_snapshot.captured_at,
            "row_count": verified.read_snapshot.expected_row_count,
            "property_count": len(verified.property_names),
            "canonical": False,
            "notion_write_capability": False,
        }


def _normalize_artifacts(artifacts: Mapping[str, object]) -> dict[str, ArtifactValue]:
    if not isinstance(artifacts, Mapping) or not artifacts:
        raise BusinessStoreError("business run requires at least one artifact")
    normalized: dict[str, ArtifactValue] = {}
    for kind, value in artifacts.items():
        if not isinstance(kind, str) or not _ARTIFACT_KIND_RE.fullmatch(kind):
            raise BusinessStoreError(f"invalid business artifact kind: {kind!r}")
        if isinstance(value, ArtifactValue):
            artifact = value
        elif isinstance(value, str):
            artifact = ArtifactValue("text/plain; charset=utf-8", value)
        else:
            try:
                artifact = ArtifactValue("application/json", canonical_dumps(value))
            except (CodecError, TypeError, ValueError) as exc:
                raise BusinessStoreError(
                    f"business artifact {kind} is not canonicalizable"
                ) from exc
        normalized[kind] = artifact
    return normalized


def _validate_month_bundle_semantics(
    *,
    verified: VerifiedRegistryExport,
    source_record_id: str,
    profile_id: str,
    period_key: str,
    request_options: Mapping[str, object],
    result: Mapping[str, object],
    artifacts: Mapping[str, ArtifactValue],
) -> None:
    """Tie recognized monthly artifacts to their verified semantic result."""

    has_month_schema = result.get("schema") == BUSINESS_MONTH_SCHEMA
    has_month_profile = profile_id == BUSINESS_PROFILE_ID
    if not has_month_schema and not has_month_profile:
        return
    if not has_month_schema or not has_month_profile:
        raise BusinessStoreError(
            "business month result is invalid: reviewed profile and schema must match"
        )
    try:
        concrete_result = dict(result)
        validate_business_preview(concrete_result, export=verified)
        if period_key != concrete_result["month_label"]:
            raise ValueError("business month period does not match the result")
        if not isinstance(request_options, Mapping) or set(request_options) != {
            "month_label",
            "seed_fingerprint",
            "assumptions",
            "raw_seed_persisted",
        }:
            raise ValueError("business month request does not match the locked schema")
        manifest = concrete_result["dice_manifest"]
        if not isinstance(manifest, dict):
            raise ValueError("business month result has no dice receipt")
        seed_fingerprint = request_options["seed_fingerprint"]
        if (
            request_options["month_label"] != concrete_result["month_label"]
            or request_options["assumptions"] != concrete_result["assumptions"]
            or not isinstance(seed_fingerprint, str)
            or not _HASH_RE.fullmatch(seed_fingerprint)
            or seed_fingerprint != manifest.get("seed_fingerprint")
            or request_options["raw_seed_persisted"] is not False
        ):
            raise ValueError("business month request does not match its result")
    except ValueError as exc:
        raise BusinessStoreError(f"business month result is invalid: {exc}") from exc
    entity = concrete_result.get("entity")
    if not isinstance(entity, dict) or entity.get("source_record_id") != source_record_id:
        raise BusinessStoreError(
            "business month result does not identify the persisted source row"
        )
    expected: dict[str, ArtifactValue] = {
        "report_markdown": ArtifactValue(
            "text/markdown; charset=utf-8",
            render_business_report(concrete_result),
        ),
        "notion_review_diff": ArtifactValue(
            "application/json",
            canonical_dumps(concrete_result["notion_review_diff"]),
        ),
        "ledger_preview": ArtifactValue(
            "application/json",
            canonical_dumps(concrete_result["ledger_preview"]),
        ),
        "dice_manifest": ArtifactValue(
            "application/json",
            canonical_dumps(concrete_result["dice_manifest"]),
        ),
    }
    if source_record_id == BRICKWORKS_SOURCE_RECORD_ID:
        expected["capacity_profile"] = ArtifactValue(
            "application/json",
            canonical_dumps(build_brickworks_partial_capacity(verified).to_dict()),
        )
    if dict(artifacts) != expected:
        raise BusinessStoreError(
            "business month artifacts do not exactly match the verified result bundle"
        )


def _verify_registry_payload(
    payload: Mapping[str, object],
) -> tuple[dict[str, object], VerifiedRegistryExport]:
    if not isinstance(payload, Mapping):
        raise BusinessStoreError("registry export payload must be an object")
    concrete = dict(payload)
    try:
        verified = verify_registry_export(concrete)
        # Round-trip through the canonical codec now, before any database write.
        canonical = _load_json_text(canonical_dumps(concrete), "canonical registry export")
    except (RegistryExportError, CodecError, TypeError, ValueError) as exc:
        raise BusinessStoreError(f"registry export verification failed: {exc}") from exc
    return canonical, verified


def _load_registry_payload(path: Path) -> dict[str, object]:
    if not isinstance(path, Path):
        raise BusinessStoreError("registry export path must be a concrete Path")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BusinessStoreError(f"cannot read registry export: {exc}") from exc
    return _load_json_text(text, "registry export", parse_decimal=True, reject_duplicates=True)


def _load_json_text(
    value: object,
    label: str,
    *,
    parse_decimal: bool = False,
    reject_duplicates: bool = False,
) -> dict[str, object]:
    if not isinstance(value, str):
        raise BusinessStoreError(f"{label} is not stored as text")

    def object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = item
        return result

    try:
        payload = json.loads(
            value,
            parse_float=Decimal if parse_decimal else _reject_float,
            parse_constant=_reject_constant,
            object_pairs_hook=object_pairs if reject_duplicates else None,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise BusinessStoreError(f"{label} is invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise BusinessStoreError(f"{label} must be a JSON object")
    return payload


def _reject_float(value: str) -> object:
    raise ValueError(f"binary float is prohibited in business state: {value}")


def _reject_constant(value: str) -> object:
    raise ValueError(f"non-finite number is prohibited in business state: {value}")


def _require_hash(value: object, label: str) -> str:
    if not isinstance(value, str) or not _HASH_RE.fullmatch(value):
        raise BusinessStoreError(f"{label} must be a lowercase SHA-256 hash")
    return value


def _require_text(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise BusinessStoreError(
            f"{label} must be canonical non-empty text without controls"
        )
    return value


def _text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
