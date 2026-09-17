"""Pure normalization boundary for read-only Notion connector results.

This module intentionally exposes no write operation. Gate 0 callers must obtain
query results outside the engine and pass them in as plain mappings.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from types import MappingProxyType
from typing import Iterable, Mapping

from .domain import canonical_decimal
from .registry import AuditResult, audit_rows


class NotionWriteProhibited(PermissionError):
    pass


BUSINESS_REGISTRY_DATA_SOURCE = "collection://3c5f887a-4219-4ae6-a18a-82cf2d1841db"
READ_OPERATIONS = frozenset(
    {
        "query",
        "search",
        "fetch",
        "retrieve",
        "get",
        "list",
        "read",
        "data_sources.query",
        "databases.query",
        "pages.retrieve",
    }
)


def assert_operation_allowed(operation: str) -> None:
    normalized = operation.strip().lower()
    if normalized not in READ_OPERATIONS:
        raise NotionWriteProhibited(
            f"Notion operation {operation!r} is not on the construction-mode read allowlist"
        )


@dataclass(frozen=True, slots=True)
class NotionReadSnapshot:
    data_source_url: str
    captured_at: str
    rows: tuple[Mapping[str, object], ...]
    expected_row_count: int
    content_hash: str

    def audit(self) -> AuditResult:
        self.verify()
        return audit_rows(self.rows)

    def verify(self) -> None:
        if self.data_source_url != BUSINESS_REGISTRY_DATA_SOURCE:
            raise ValueError("Notion snapshot source is not the authorized Business Registry")
        _parse_captured_at(self.captured_at)
        if (
            isinstance(self.expected_row_count, bool)
            or not isinstance(self.expected_row_count, int)
            or self.expected_row_count < 0
            or len(self.rows) != self.expected_row_count
        ):
            raise ValueError("Notion snapshot row count does not match its completeness claim")
        if self.content_hash != _content_hash(self.rows):
            raise ValueError("Notion snapshot content hash does not match its rows")


def make_read_snapshot(
    *, data_source_url: str, captured_at: str, rows: Iterable[Mapping[str, object]],
    expected_row_count: int, pagination_complete: bool,
) -> NotionReadSnapshot:
    if data_source_url != BUSINESS_REGISTRY_DATA_SOURCE:
        raise ValueError("Notion source is not the authorized Business Registry data source")
    _parse_captured_at(captured_at)
    if pagination_complete is not True:
        raise ValueError("registry snapshot is incomplete; pagination did not finish")
    materialized = tuple(dict(row) for row in rows)
    if (
        isinstance(expected_row_count, bool)
        or not isinstance(expected_row_count, int)
        or expected_row_count < 0
        or len(materialized) != expected_row_count
    ):
        raise ValueError(
            f"registry snapshot row count {len(materialized)} does not match expected {expected_row_count}"
        )
    frozen = tuple(_freeze(row) for row in materialized)
    snapshot = NotionReadSnapshot(
        data_source_url,
        captured_at,
        frozen,
        expected_row_count,
        _content_hash(frozen),
    )
    snapshot.verify()
    return snapshot


def _parse_captured_at(captured_at: str) -> datetime:
    if not isinstance(captured_at, str):
        raise ValueError("captured_at must be a valid ISO timestamp")
    try:
        captured = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("captured_at must be a valid ISO timestamp") from exc
    if captured.tzinfo is None:
        raise ValueError("captured_at must include a timezone")
    return captured


def _content_hash(rows: Iterable[Mapping[str, object]]) -> str:
    canonical = json.dumps(
        _json_safe(tuple(rows)),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _json_safe(value: object) -> object:
    if isinstance(value, Decimal):
        return canonical_decimal(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"unsupported Notion snapshot value: {type(value).__name__}")
