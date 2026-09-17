"""Integrity-checked offline receipts for the read-only Business Registry.

The locked receipt proves internal completeness and hash consistency. It is not a
cryptographic attestation from Notion and must not be described as one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Mapping
from urllib.parse import urlsplit
from uuid import UUID

from .notion_read import (
    BUSINESS_REGISTRY_DATA_SOURCE,
    NotionReadSnapshot,
    make_read_snapshot,
)
from .operator_codec import canonical_hash, json_safe
from .registry import AuditResult, stable_source_record_id


REGISTRY_EXPORT_SCHEMA = "tnp.registry.read-export/1"
REGISTRY_DATABASE_ID = "8ba47f60-efe1-4c83-9fe1-4561543e07d1"
REGISTRY_DATABASE_URL = (
    "https://app.notion.com/p/8ba47f60efe14c839fe14561543e07d1?pvs=204"
)
REGISTRY_SOURCE_ID = "3c5f887a-4219-4ae6-a18a-82cf2d1841db"
REGISTRY_EXPECTED_ROW_COUNT = 90
REGISTRY_ORDERED_SOURCE_IDS_HASH = (
    "0d231458d414412f231ae3c568a88dd05b23bacd17acdbb90031b4701521999e"
)
REGISTRY_ROW_HASH_SCHEMA = "tnp.registry.source-row/1"
REGISTRY_PAGE_RECEIPT_SCHEMA = "tnp.registry.query-page-source-ids/1"
REGISTRY_SOURCE_SCHEMA = (
    ("Capital Invested", "decimal_text", True),
    ("City", "text", True),
    ("Current Activity", "text", True),
    ("Date Operational", "text", True),
    ("Disposition", "decimal_text", True),
    ("Employees", "decimal_text", True),
    ("Entity", "text", False),
    ("Known Assets", "text", True),
    ("Last Attended", "text", True),
    ("Last Updated", "text", True),
    ("Leadership", "text", True),
    ("Monthly Cost", "decimal_text", True),
    ("Monthly Revenue", "decimal_text", True),
    ("Neglect Status", "text", True),
    ("Notes", "text", True),
    ("Parent Entity", "text", True),
    ("Profit Margin", "decimal_text", True),
    ("ROI Pct", "decimal_text", True),
    ("Region", "text", True),
    ("Relationship", "text", True),
    ("Sector", "text", True),
    ("Source File", "text", True),
    ("Status", "text", True),
    ("Threat Level", "text", True),
    ("Type", "text", True),
    ("date:Last Updated 1:end", "date_or_datetime_text", True),
    ("date:Last Updated 1:is_datetime", "integer_flag", True),
    ("date:Last Updated 1:start", "date_or_datetime_text", True),
)
REGISTRY_PROPERTY_NAMES = tuple(item[0] for item in REGISTRY_SOURCE_SCHEMA)
_PROPERTY_SCHEMA_BY_NAME = MappingProxyType(
    {name: (source_type, nullable) for name, source_type, nullable in REGISTRY_SOURCE_SCHEMA}
)
REGISTRY_ROW_KEYS = frozenset({"id", "url", "createdTime", *REGISTRY_PROPERTY_NAMES})
DECIMAL_FIELDS = frozenset(
    name for name, source_type, _ in REGISTRY_SOURCE_SCHEMA
    if source_type == "decimal_text"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CREATED_TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}Z$")
_CAPTURED_AT_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$"
)


class RegistryExportError(ValueError):
    """Raised when an export cannot satisfy the locked offline receipt contract."""


@dataclass(frozen=True, slots=True)
class VerifiedRegistryExport:
    """A structurally verified receipt, not proof of live Notion authenticity."""

    read_snapshot: NotionReadSnapshot
    snapshot_hash: str
    export_hash: str
    source_schema_hash: str
    property_names: tuple[str, ...]
    rows_by_source_id: Mapping[str, Mapping[str, object]]
    row_hashes: Mapping[str, str]
    audit: AuditResult

    @property
    def content_hash(self) -> str:
        """Transport-order hash supplied by the offline export receipt."""

        return self.read_snapshot.content_hash

    def row(self, source_record_id: str) -> Mapping[str, object]:
        try:
            return self.rows_by_source_id[source_record_id]
        except KeyError as exc:
            raise RegistryExportError(
                f"registry snapshot has no row {source_record_id}"
            ) from exc

    def property_hash(self, source_record_id: str, property_name: str) -> str:
        if property_name not in self.property_names:
            raise RegistryExportError(f"unknown registry property: {property_name}")
        row = self.row(source_record_id)
        return canonical_hash(
            {
                "schema": "tnp.registry.source-property/1",
                "snapshot_hash": self.snapshot_hash,
                "source_schema_hash": self.source_schema_hash,
                "source_record_id": source_record_id,
                "row_hash": self.row_hashes[source_record_id],
                "property_schema": _property_schema_payload(property_name),
                "source_value": _typed_value(row[property_name]),
            }
        )


def load_registry_export(path: Path) -> VerifiedRegistryExport:
    if not isinstance(path, Path):
        raise RegistryExportError("registry export path must be a concrete Path")
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            parse_float=Decimal,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_reject_duplicate_json_object,
        )
    except RegistryExportError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RegistryExportError(f"cannot read registry export: {exc}") from exc
    return verify_registry_export(payload)


def verify_registry_export(payload: object) -> VerifiedRegistryExport:
    if not isinstance(payload, dict):
        raise RegistryExportError("registry export must be a JSON object")
    expected_keys = {
        "schema",
        "data_source_url",
        "database_id",
        "database_url",
        "captured_at",
        "query",
        "normalization",
        "source_schema",
        "source_schema_hash",
        "property_names",
        "content_hash",
        "rows",
    }
    if set(payload) != expected_keys:
        raise RegistryExportError("registry export keys do not match the locked schema")
    if payload["schema"] != REGISTRY_EXPORT_SCHEMA:
        raise RegistryExportError("registry export schema is unsupported")
    if payload["data_source_url"] != BUSINESS_REGISTRY_DATA_SOURCE:
        raise RegistryExportError("registry export is not from the Business Registry")
    if payload["database_id"] != REGISTRY_DATABASE_ID:
        raise RegistryExportError("registry export database identity is wrong")
    database_url = payload["database_url"]
    if database_url != REGISTRY_DATABASE_URL:
        raise RegistryExportError("registry export database URL is not source-bound")
    captured_at = payload["captured_at"]
    if not isinstance(captured_at, str) or not _CAPTURED_AT_RE.fullmatch(captured_at):
        raise RegistryExportError(
            "registry captured_at must be canonical UTC with millisecond precision"
        )
    try:
        datetime.strptime(captured_at, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as exc:
        raise RegistryExportError("registry captured_at is not a valid UTC instant") from exc

    query = payload["query"]
    if not isinstance(query, dict) or set(query) != {
        "mode", "ordered_by", "pagination_complete", "expected_row_count",
        "data_source_ids", "filter", "page_receipts",
    }:
        raise RegistryExportError("registry query receipt is malformed")
    if (
        query["mode"] != "sql"
        or query["ordered_by"] != ["Entity", "url"]
        or query["pagination_complete"] is not True
        or query["data_source_ids"] != [REGISTRY_SOURCE_ID]
        or query["filter"] is not None
        or type(query["expected_row_count"]) is not int
        or query["expected_row_count"] != REGISTRY_EXPECTED_ROW_COUNT
    ):
        raise RegistryExportError("registry query receipt is incomplete or from the wrong source")

    normalization = payload["normalization"]
    if not isinstance(normalization, dict) or set(normalization) != {
        "decimal_fields", "decimal_encoding", "note",
    }:
        raise RegistryExportError("registry export normalization receipt is malformed")
    if (
        normalization["decimal_fields"] != sorted(DECIMAL_FIELDS)
        or normalization["decimal_encoding"] != "canonical strings"
        or not isinstance(normalization["note"], str)
        or not normalization["note"].strip()
    ):
        raise RegistryExportError("registry decimal normalization contract has drifted")

    property_names = payload["property_names"]
    if property_names != list(REGISTRY_PROPERTY_NAMES):
        raise RegistryExportError("registry property schema has drifted")
    source_schema = payload["source_schema"]
    if source_schema != _source_schema_payload():
        raise RegistryExportError("registry source schema has drifted")
    source_schema_hash = payload["source_schema_hash"]
    if (
        not isinstance(source_schema_hash, str)
        or not _SHA256_RE.fullmatch(source_schema_hash)
        or source_schema_hash != canonical_hash(source_schema)
    ):
        raise RegistryExportError("registry source schema hash does not match")
    rows = payload["rows"]
    if not isinstance(rows, list) or len(rows) != query["expected_row_count"]:
        raise RegistryExportError("registry row count does not match the query receipt")
    if not all(isinstance(row, dict) for row in rows):
        raise RegistryExportError("registry rows must be concrete objects")
    if any(set(row) != REGISTRY_ROW_KEYS for row in rows):
        raise RegistryExportError("registry row properties do not match the locked schema")
    if any(_contains_float(row) for row in rows):
        raise RegistryExportError("binary floating-point values cannot enter registry state")
    for row in rows:
        _validate_row_identity(row)
    ordered_source_ids = tuple(stable_source_record_id(str(row["url"])) for row in rows)
    if len(set(ordered_source_ids)) != len(ordered_source_ids):
        raise RegistryExportError("registry export repeats a source record identity")
    if _page_source_ids_hash(1, ordered_source_ids) != REGISTRY_ORDERED_SOURCE_IDS_HASH:
        raise RegistryExportError(
            "registry rows do not match the locked source ordering receipt"
        )
    expected_content_hash = payload["content_hash"]
    if (
        not isinstance(expected_content_hash, str)
        or not _SHA256_RE.fullmatch(expected_content_hash)
    ):
        raise RegistryExportError("registry export is missing a full content hash")
    snapshot = make_read_snapshot(
        data_source_url=str(payload["data_source_url"]),
        captured_at=captured_at,
        rows=rows,
        expected_row_count=query["expected_row_count"],
        pagination_complete=query["pagination_complete"],
    )
    if snapshot.content_hash != expected_content_hash:
        raise RegistryExportError("registry export content hash does not match its rows")

    rows_by_source_id: dict[str, Mapping[str, object]] = {}
    row_hashes: dict[str, str] = {}
    for row in rows:
        source_record_id = stable_source_record_id(str(row["url"]))
        if source_record_id in rows_by_source_id:
            raise RegistryExportError("registry export repeats a source record identity")
        frozen_row = snapshot.rows[len(rows_by_source_id)]
        rows_by_source_id[source_record_id] = frozen_row
        row_hashes[source_record_id] = canonical_hash(
            {
                "schema": REGISTRY_ROW_HASH_SCHEMA,
                "data_source_url": BUSINESS_REGISTRY_DATA_SOURCE,
                "source_schema_hash": source_schema_hash,
                "source_record_id": source_record_id,
                "source_row": _typed_value(frozen_row),
            }
        )

    _validate_page_receipts(query["page_receipts"], tuple(rows_by_source_id))

    audit = snapshot.audit()
    identity_blockers = {
        "duplicate_entity_name",
        "duplicate_source_record_id",
        "missing_entity",
        "missing_source_record_id",
        "missing_source_ref",
        "self_parent",
        "stable_id_collision",
    }
    if identity_blockers.intersection(issue.code for issue in audit.issues):
        raise RegistryExportError("registry export failed the source-identity audit")

    snapshot_hash = canonical_hash(
        {
            "schema": "tnp.registry.verified-snapshot/1",
            "data_source_url": BUSINESS_REGISTRY_DATA_SOURCE,
            "database_id": REGISTRY_DATABASE_ID,
            "source_schema_hash": source_schema_hash,
            "row_hash_schema": REGISTRY_ROW_HASH_SCHEMA,
            "property_names": list(REGISTRY_PROPERTY_NAMES),
            "rows": [
                {
                    "source_record_id": source_record_id,
                    "row_hash": row_hashes[source_record_id],
                }
                for source_record_id in sorted(row_hashes)
            ],
        }
    )
    export_hash = canonical_hash(payload)
    return VerifiedRegistryExport(
        read_snapshot=snapshot,
        snapshot_hash=snapshot_hash,
        export_hash=export_hash,
        source_schema_hash=source_schema_hash,
        property_names=REGISTRY_PROPERTY_NAMES,
        rows_by_source_id=MappingProxyType(rows_by_source_id),
        row_hashes=MappingProxyType(row_hashes),
        audit=audit,
    )


def _validate_row_identity(row: Mapping[str, object]) -> None:
    page_id = row.get("id")
    url = row.get("url")
    if not isinstance(page_id, str) or not isinstance(url, str):
        raise RegistryExportError("registry row requires string page ID and URL")
    try:
        parsed_page_id = UUID(page_id)
    except ValueError as exc:
        raise RegistryExportError("registry row page ID is not a UUID") from exc
    if page_id != str(parsed_page_id):
        raise RegistryExportError("registry row page ID is not in canonical UUID form")
    normalized_page_id = parsed_page_id.hex
    parsed_url = urlsplit(url)
    if (
        parsed_url.scheme != "https"
        or parsed_url.netloc != "app.notion.com"
        or parsed_url.path != f"/{normalized_page_id}"
        or parsed_url.query
        or parsed_url.fragment
        or stable_source_record_id(url) != f"notion:{normalized_page_id}"
    ):
        raise RegistryExportError("registry row URL and page ID do not identify the same record")
    created_time = row.get("createdTime")
    if (
        not isinstance(created_time, str)
        or not _CREATED_TIME_RE.fullmatch(created_time)
    ):
        raise RegistryExportError("registry row createdTime is not a canonical UTC timestamp")
    try:
        datetime.strptime(created_time, "%Y-%m-%d %H:%M:%SZ")
    except ValueError as exc:
        raise RegistryExportError(
            "registry row createdTime is not a valid UTC timestamp"
        ) from exc
    _validate_property_values(row)


def _validate_property_values(row: Mapping[str, object]) -> None:
    for property_name, source_type, nullable in REGISTRY_SOURCE_SCHEMA:
        value = row[property_name]
        if value is None:
            if not nullable:
                raise RegistryExportError(
                    f"registry property {property_name} may not be null"
                )
            continue
        if source_type == "text":
            if not isinstance(value, str):
                raise RegistryExportError(
                    f"registry text property {property_name} has the wrong type"
                )
            if property_name == "Entity" and not value.strip():
                raise RegistryExportError("registry row has no entity title")
        elif source_type == "decimal_text":
            _validate_decimal_text(property_name, value)
        elif source_type == "date_or_datetime_text":
            _validate_date_or_datetime_text(property_name, value)
        elif source_type == "integer_flag":
            if type(value) is not int or value not in (0, 1):
                raise RegistryExportError(
                    f"registry flag property {property_name} must be exact 0 or 1"
                )
        else:  # The locked source schema makes this branch unreachable.
            raise RegistryExportError(
                f"unsupported registry source type for {property_name}: {source_type}"
            )

    start = row["date:Last Updated 1:start"]
    end = row["date:Last Updated 1:end"]
    is_datetime = row["date:Last Updated 1:is_datetime"]
    if start is None:
        if end is not None or is_datetime is not None:
            raise RegistryExportError(
                "registry machine-date metadata is populated without a start value"
            )
    elif is_datetime is None:
        raise RegistryExportError(
            "registry machine-date start is missing its datetime flag"
        )
    elif is_datetime == 0 and (
        _looks_like_datetime(start)
        or (end is not None and _looks_like_datetime(end))
    ):
        raise RegistryExportError(
            "registry machine-date flag says date-only but contains a datetime"
        )
    elif is_datetime == 1 and (
        not _looks_like_datetime(start)
        or (end is not None and not _looks_like_datetime(end))
    ):
        raise RegistryExportError(
            "registry machine-date flag says datetime but contains a date-only value"
        )


def _validate_decimal_text(property_name: str, value: object) -> None:
    if not isinstance(value, str):
        raise RegistryExportError(
            f"registry decimal property {property_name} is not exact text"
        )
    try:
        parsed = Decimal(value)
    except Exception as exc:  # Decimal raises multiple concrete parse exceptions.
        raise RegistryExportError(
            f"registry decimal property {property_name} is malformed"
        ) from exc
    normalized_value = value.replace("E+", "e+").replace("E-", "e-")
    normalized_parsed = str(parsed).replace("E+", "e+").replace("E-", "e-")
    if not parsed.is_finite() or normalized_parsed != normalized_value:
        raise RegistryExportError(
            f"registry decimal property {property_name} is not in an exact accepted form"
        )


def _validate_date_or_datetime_text(property_name: str, value: object) -> None:
    if not isinstance(value, str) or not value:
        raise RegistryExportError(
            f"registry date property {property_name} is not exact text"
        )
    try:
        if _looks_like_datetime(value):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("datetime has no timezone")
        else:
            date.fromisoformat(value)
    except ValueError as exc:
        raise RegistryExportError(
            f"registry date property {property_name} is malformed"
        ) from exc


def _looks_like_datetime(value: object) -> bool:
    return isinstance(value, str) and "T" in value


def _source_schema_payload() -> dict[str, object]:
    return {
        "schema": "tnp.registry.source-schema/1",
        "identity_basis": "captured_column_names",
        "notion_property_ids_available": False,
        "write_targetable": False,
        "row_metadata": [
            {"name": "id", "source_type": "uuid", "nullable": False},
            {
                "name": "url",
                "source_type": "notion_page_url",
                "nullable": False,
            },
            {
                "name": "createdTime",
                "source_type": "utc_timestamp",
                "nullable": False,
            },
        ],
        "properties": [
            _property_schema_payload(property_name)
            for property_name in REGISTRY_PROPERTY_NAMES
        ],
    }


def _property_schema_payload(property_name: str) -> dict[str, object]:
    try:
        source_type, nullable = _PROPERTY_SCHEMA_BY_NAME[property_name]
    except KeyError as exc:
        raise RegistryExportError(f"unknown registry property: {property_name}") from exc
    return {
        "name": property_name,
        "notion_property_id": None,
        "source_type": source_type,
        "nullable": nullable,
    }


def _validate_page_receipts(
    receipts: object, source_record_ids: tuple[str, ...]
) -> None:
    if not isinstance(receipts, list) or not receipts:
        raise RegistryExportError("registry pagination receipt is missing")
    expected_cursor: str | None = None
    seen_cursors: set[str] = set()
    row_offset = 0
    receipt_keys = {
        "page_index",
        "request_cursor",
        "response_row_count",
        "source_record_ids_hash",
        "has_more",
        "next_cursor",
    }
    for expected_index, receipt in enumerate(receipts, 1):
        if not isinstance(receipt, dict) or set(receipt) != receipt_keys:
            raise RegistryExportError("registry pagination page receipt is malformed")
        response_row_count = receipt["response_row_count"]
        if (
            type(receipt["page_index"]) is not int
            or receipt["page_index"] != expected_index
            or receipt["request_cursor"] != expected_cursor
            or type(response_row_count) is not int
            or response_row_count <= 0
            or type(receipt["has_more"]) is not bool
        ):
            raise RegistryExportError("registry pagination cursor chain is inconsistent")
        page_ids = source_record_ids[row_offset : row_offset + response_row_count]
        if len(page_ids) != response_row_count:
            raise RegistryExportError("registry pagination row counts exceed the export")
        expected_ids_hash = _page_source_ids_hash(expected_index, page_ids)
        if receipt["source_record_ids_hash"] != expected_ids_hash:
            raise RegistryExportError("registry pagination page IDs do not match its rows")
        row_offset += response_row_count

        is_final = expected_index == len(receipts)
        next_cursor = receipt["next_cursor"]
        if is_final:
            if receipt["has_more"] is not False or next_cursor is not None:
                raise RegistryExportError(
                    "registry pagination did not record a terminal page"
                )
        elif (
            receipt["has_more"] is not True
            or not isinstance(next_cursor, str)
            or not next_cursor.strip()
            or next_cursor in seen_cursors
        ):
            raise RegistryExportError("registry pagination cursor chain is incomplete")
        if isinstance(next_cursor, str):
            seen_cursors.add(next_cursor)
        expected_cursor = next_cursor
    if row_offset != len(source_record_ids):
        raise RegistryExportError("registry pagination row counts do not cover the export")


def _page_source_ids_hash(
    page_index: int, source_record_ids: tuple[str, ...]
) -> str:
    return canonical_hash(
        {
            "schema": REGISTRY_PAGE_RECEIPT_SCHEMA,
            "page_index": page_index,
            "source_record_ids": list(source_record_ids),
        }
    )


def _reject_duplicate_json_object(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise RegistryExportError(
                f"registry export contains duplicate JSON object key: {key}"
            )
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise RegistryExportError(
        f"registry export contains a non-finite JSON constant: {value}"
    )


def _contains_float(value: object) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_float(item) for item in value)
    return False


def _typed_value(value: object) -> object:
    """Type-tag source values so text ``"1"`` cannot hash like integer ``1``."""

    if value is None:
        return {"type": "null", "value": None}
    if isinstance(value, bool):
        return {"type": "boolean", "value": value}
    if type(value) is int:
        return {"type": "integer", "value": value}
    if isinstance(value, str):
        return {"type": "string", "value": value}
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise RegistryExportError("typed registry object keys must be strings")
        return {
            "type": "object",
            "value": {
                key: _typed_value(item)
                for key, item in sorted(value.items(), key=lambda pair: pair[0])
            },
        }
    if isinstance(value, (tuple, list)):
        return {"type": "array", "value": [_typed_value(item) for item in value]}
    raise RegistryExportError(f"unsupported typed registry value: {type(value).__name__}")


def export_summary(export: VerifiedRegistryExport) -> dict[str, object]:
    return json_safe(
        {
            "schema": "tnp.registry.verified-summary/1",
            "data_source_url": BUSINESS_REGISTRY_DATA_SOURCE,
            "captured_at": export.read_snapshot.captured_at,
            "row_count": export.read_snapshot.expected_row_count,
            "content_hash": export.content_hash,
            "snapshot_hash": export.snapshot_hash,
            "export_hash": export.export_hash,
            "source_schema_hash": export.source_schema_hash,
            "property_count": len(export.property_names),
            "audit_blockers": export.audit.blocker_count,
            "audit_issues": len(export.audit.issues),
            "raw_totals": export.audit.raw_totals,
            "warning": "Raw totals are diagnostic and are not consolidated campaign books.",
            "verification_scope": (
                "offline receipt integrity and completeness; not a cryptographic "
                "Notion attestation"
            ),
            "notion_write_capability": False,
        }
    )
