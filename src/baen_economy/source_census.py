"""Canonical live-source census records, validation, coverage, and diffing.

Live read-only acquisition is implemented in ``source_census_acquisition``.  This
module owns the durable evidence format, hashes, coverage gate, and snapshot diff.
Neither module exposes a Notion write operation.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


CENSUS_SCHEMA = "tnp.economy.source-census/1"
DIFF_SCHEMA = "tnp.economy.source-census-diff/1"


class CensusError(ValueError):
    """Raised when census evidence is malformed or coverage cannot open safely."""


class CoverageState(StrEnum):
    SIMULATED = "SIMULATED"
    CONTEXT_ONLY = "CONTEXT_ONLY"
    FUTURE = "FUTURE"
    HISTORICAL = "HISTORICAL"
    SUPERSEDED = "SUPERSEDED"
    CONFLICT = "CONFLICT"
    MISSING_MECHANICS = "MISSING_MECHANICS"
    MISSING_DATA = "MISSING_DATA"
    UNKNOWN = "UNKNOWN"


class DecisionProvenance(StrEnum):
    USER_RULED = "USER-RULED"
    SOURCE_DERIVED = "SOURCE-DERIVED"
    UPSTREAM_ADOPTED = "UPSTREAM-ADOPTED"
    MODEL_PROPOSED = "MODEL-PROPOSED"
    UNRESOLVED = "UNRESOLVED"


BLOCKING_ACTIVE_STATES = frozenset(
    {
        CoverageState.CONFLICT,
        CoverageState.MISSING_MECHANICS,
        CoverageState.MISSING_DATA,
        CoverageState.UNKNOWN,
    }
)


def canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class SourceCollection:
    stable_source_id: str
    source_url: str
    title: str
    source_class: str
    row_count: int
    enumeration_complete: bool
    source_hash: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SourceCollection":
        _require_fields(
            value,
            {
                "stable_source_id",
                "source_url",
                "title",
                "source_class",
                "row_count",
                "enumeration_complete",
                "source_hash",
            },
            "source collection",
        )
        result = cls(
            stable_source_id=_nonempty(value["stable_source_id"], "stable_source_id"),
            source_url=_nonempty(value["source_url"], "source_url"),
            title=_nonempty(value["title"], "title"),
            source_class=_nonempty(value["source_class"], "source_class"),
            row_count=_nonnegative_int(value["row_count"], "row_count"),
            enumeration_complete=_strict_bool(
                value["enumeration_complete"], "enumeration_complete"
            ),
            source_hash=_sha256_text(value["source_hash"], "source_hash"),
        )
        if result.source_hash != canonical_hash(result.semantic_body()):
            raise CensusError(
                f"source collection hash mismatch: {result.stable_source_id}"
            )
        return result

    def semantic_body(self) -> dict[str, object]:
        return {
            "stable_source_id": self.stable_source_id,
            "source_url": self.source_url,
            "title": self.title,
            "source_class": self.source_class,
            "row_count": self.row_count,
            "enumeration_complete": self.enumeration_complete,
        }


@dataclass(frozen=True)
class SourceRecord:
    stable_source_id: str
    source_url: str
    title: str
    source_class: str
    region_location: str
    effective_date: str
    effective_status: str
    direct_relations: tuple[str, ...]
    numeric_properties: Mapping[str, object]
    narrative_facts: tuple[str, ...]
    simulation_relevance: str
    coverage_state: CoverageState
    provenance: DecisionProvenance
    source_hash: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SourceRecord":
        _require_fields(
            value,
            {
                "stable_source_id",
                "source_url",
                "title",
                "source_class",
                "region_location",
                "effective_date",
                "effective_status",
                "direct_relations",
                "numeric_properties",
                "narrative_facts",
                "simulation_relevance",
                "coverage_state",
                "provenance",
                "source_hash",
            },
            "source record",
        )
        try:
            coverage_state = CoverageState(value["coverage_state"])
        except (TypeError, ValueError) as exc:
            raise CensusError(
                f"invalid coverage state for {value.get('stable_source_id', '<unknown>')}"
            ) from exc
        try:
            provenance = DecisionProvenance(value["provenance"])
        except (TypeError, ValueError) as exc:
            raise CensusError(
                f"invalid provenance for {value.get('stable_source_id', '<unknown>')}"
            ) from exc
        numeric = value["numeric_properties"]
        if not isinstance(numeric, Mapping):
            raise CensusError("numeric_properties must be an object")
        _validate_json_value(dict(numeric), "numeric_properties")
        result = cls(
            stable_source_id=_nonempty(value["stable_source_id"], "stable_source_id"),
            source_url=_nonempty(value["source_url"], "source_url"),
            title=_nonempty(value["title"], "title"),
            source_class=_nonempty(value["source_class"], "source_class"),
            region_location=_nonempty(value["region_location"], "region_location"),
            effective_date=_nonempty(value["effective_date"], "effective_date"),
            effective_status=_nonempty(value["effective_status"], "effective_status"),
            direct_relations=_string_sequence(
                value["direct_relations"], "direct_relations"
            ),
            numeric_properties=dict(numeric),
            narrative_facts=_string_sequence(
                value["narrative_facts"], "narrative_facts"
            ),
            simulation_relevance=_nonempty(
                value["simulation_relevance"], "simulation_relevance"
            ),
            coverage_state=coverage_state,
            provenance=provenance,
            source_hash=_sha256_text(value["source_hash"], "source_hash"),
        )
        if result.source_hash != canonical_hash(result.semantic_body()):
            raise CensusError(f"source record hash mismatch: {result.stable_source_id}")
        return result

    def semantic_body(self) -> dict[str, object]:
        return {
            "stable_source_id": self.stable_source_id,
            "source_url": self.source_url,
            "title": self.title,
            "source_class": self.source_class,
            "region_location": self.region_location,
            "effective_date": self.effective_date,
            "effective_status": self.effective_status,
            "direct_relations": list(self.direct_relations),
            "numeric_properties": dict(self.numeric_properties),
            "narrative_facts": list(self.narrative_facts),
            "simulation_relevance": self.simulation_relevance,
            "coverage_state": self.coverage_state.value,
            "provenance": self.provenance.value,
        }


@dataclass(frozen=True)
class CensusSnapshot:
    schema: str
    captured_at: str
    campaign_boundary: str
    read_mode: str
    repository_base_sha: str
    source_collections: tuple[SourceCollection, ...]
    records: tuple[SourceRecord, ...]
    provisional_row_coverage: Mapping[str, object]
    known_linked_authority_pages_outside_core_collections: int
    notes: tuple[str, ...]
    provenance: tuple[Mapping[str, str], ...]
    snapshot_hash: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CensusSnapshot":
        _require_fields(
            value,
            {
                "schema",
                "captured_at",
                "campaign_boundary",
                "read_mode",
                "repository_base_sha",
                "source_collections",
                "records",
                "provisional_row_coverage",
                "known_linked_authority_pages_outside_core_collections",
                "notes",
                "provenance",
                "snapshot_hash",
            },
            "census snapshot",
        )
        if value["schema"] != CENSUS_SCHEMA:
            raise CensusError(f"unsupported census schema: {value['schema']!r}")
        collections_raw = value["source_collections"]
        records_raw = value["records"]
        if not _is_array(collections_raw):
            raise CensusError("source_collections must be an array")
        if not _is_array(records_raw):
            raise CensusError("records must be an array")
        collections = tuple(
            SourceCollection.from_mapping(item) for item in collections_raw
        )
        records = tuple(SourceRecord.from_mapping(item) for item in records_raw)
        _reject_duplicate_ids(
            [item.stable_source_id for item in collections], "source collection"
        )
        _reject_duplicate_ids(
            [item.stable_source_id for item in records], "source record"
        )
        row_coverage = value["provisional_row_coverage"]
        if not isinstance(row_coverage, Mapping):
            raise CensusError("provisional_row_coverage must be an object")
        _validate_row_coverage(row_coverage)

        provenance_raw = value["provenance"]
        if not _is_array(provenance_raw):
            raise CensusError("provenance must be an array")
        provenance: list[Mapping[str, str]] = []
        for item in provenance_raw:
            if not isinstance(item, Mapping):
                raise CensusError("provenance entries must be objects")
            choice = _nonempty(item.get("choice"), "provenance.choice")
            tag = _nonempty(item.get("tag"), "provenance.tag")
            try:
                DecisionProvenance(tag)
            except ValueError as exc:
                raise CensusError(f"invalid provenance tag: {tag}") from exc
            provenance.append({"choice": choice, "tag": tag})

        result = cls(
            schema=CENSUS_SCHEMA,
            captured_at=_nonempty(value["captured_at"], "captured_at"),
            campaign_boundary=_nonempty(
                value["campaign_boundary"], "campaign_boundary"
            ),
            read_mode=_nonempty(value["read_mode"], "read_mode"),
            repository_base_sha=_git_sha1_text(
                value["repository_base_sha"], "repository_base_sha"
            ),
            source_collections=collections,
            records=records,
            provisional_row_coverage=dict(row_coverage),
            known_linked_authority_pages_outside_core_collections=_nonnegative_int(
                value["known_linked_authority_pages_outside_core_collections"],
                "known_linked_authority_pages_outside_core_collections",
            ),
            notes=_string_sequence(value["notes"], "notes"),
            provenance=tuple(provenance),
            snapshot_hash=_sha256_text(value["snapshot_hash"], "snapshot_hash"),
        )
        if result.snapshot_hash != canonical_hash(result.semantic_body()):
            raise CensusError("census snapshot hash mismatch")
        return result

    def semantic_body(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "captured_at": self.captured_at,
            "campaign_boundary": self.campaign_boundary,
            "read_mode": self.read_mode,
            "repository_base_sha": self.repository_base_sha,
            "source_collections": [
                {**item.semantic_body(), "source_hash": item.source_hash}
                for item in self.source_collections
            ],
            "records": [
                {**item.semantic_body(), "source_hash": item.source_hash}
                for item in self.records
            ],
            "provisional_row_coverage": dict(self.provisional_row_coverage),
            "known_linked_authority_pages_outside_core_collections": (
                self.known_linked_authority_pages_outside_core_collections
            ),
            "notes": list(self.notes),
            "provenance": [dict(item) for item in self.provenance],
        }


def load_census_snapshot(path: Path) -> CensusSnapshot:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CensusError(f"cannot read census snapshot {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise CensusError("census snapshot root must be an object")
    return CensusSnapshot.from_mapping(value)


def coverage_report(snapshot: CensusSnapshot) -> dict[str, object]:
    state_counts = Counter(item.coverage_state.value for item in snapshot.records)
    class_counts = Counter(item.source_class for item in snapshot.records)
    incomplete = [
        item.stable_source_id
        for item in snapshot.source_collections
        if not item.enumeration_complete
    ]
    active_blockers = [
        {
            "stable_source_id": item.stable_source_id,
            "title": item.title,
            "coverage_state": item.coverage_state.value,
        }
        for item in snapshot.records
        if item.simulation_relevance == "active"
        and item.coverage_state in BLOCKING_ACTIVE_STATES
    ]
    temporal = {
        state.value: [
            item.stable_source_id
            for item in snapshot.records
            if item.coverage_state == state
        ]
        for state in (
            CoverageState.FUTURE,
            CoverageState.HISTORICAL,
            CoverageState.SUPERSEDED,
        )
    }
    gate_open = (
        not incomplete
        and not active_blockers
        and snapshot.provisional_row_coverage.get("UNKNOWN", 0) == 0
    )
    return {
        "schema": "tnp.economy.coverage-report/1",
        "captured_at": snapshot.captured_at,
        "campaign_boundary": snapshot.campaign_boundary,
        "raw_core_rows": sum(item.row_count for item in snapshot.source_collections),
        "source_collection_count": len(snapshot.source_collections),
        "material_record_count": len(snapshot.records),
        "record_class_counts": dict(sorted(class_counts.items())),
        "coverage_state_counts": dict(sorted(state_counts.items())),
        "provisional_row_coverage": dict(snapshot.provisional_row_coverage),
        "incomplete_collections": incomplete,
        "active_blockers": active_blockers,
        "temporal_records": temporal,
        "gate": "OPEN" if gate_open else "CLOSED",
    }


def assert_coverage_gate(snapshot: CensusSnapshot) -> dict[str, object]:
    report = coverage_report(snapshot)
    if report["gate"] == "OPEN":
        return report
    reasons: list[str] = []
    if report["incomplete_collections"]:
        reasons.append(
            f"{len(report['incomplete_collections'])} source collections are not fully enumerated"
        )
    if report["active_blockers"]:
        reasons.append(
            f"{len(report['active_blockers'])} active source records have blocking coverage"
        )
    unknown = snapshot.provisional_row_coverage.get("UNKNOWN", 0)
    if unknown:
        reasons.append(f"{unknown} core rows remain UNKNOWN")
    raise CensusError("coverage gate CLOSED: " + "; ".join(reasons))


def diff_snapshots(
    previous: CensusSnapshot, current: CensusSnapshot
) -> dict[str, object]:
    prev = {item.stable_source_id: item for item in previous.records}
    curr = {item.stable_source_id: item for item in current.records}
    added = sorted(curr.keys() - prev.keys())
    removed = sorted(prev.keys() - curr.keys())
    changed = sorted(
        key for key in curr.keys() & prev.keys()
        if curr[key].source_hash != prev[key].source_hash
    )
    unchanged = sorted(
        key for key in curr.keys() & prev.keys()
        if curr[key].source_hash == prev[key].source_hash
    )
    prev_collections = {
        item.stable_source_id: item for item in previous.source_collections
    }
    curr_collections = {
        item.stable_source_id: item for item in current.source_collections
    }
    collection_changes = {
        key: {
            "previous_rows": prev_collections[key].row_count
            if key in prev_collections else None,
            "current_rows": curr_collections[key].row_count
            if key in curr_collections else None,
            "previous_complete": prev_collections[key].enumeration_complete
            if key in prev_collections else None,
            "current_complete": curr_collections[key].enumeration_complete
            if key in curr_collections else None,
        }
        for key in sorted(prev_collections.keys() | curr_collections.keys())
        if (
            key not in prev_collections
            or key not in curr_collections
            or prev_collections[key].source_hash != curr_collections[key].source_hash
        )
    }
    body = {
        "schema": DIFF_SCHEMA,
        "previous_snapshot_hash": previous.snapshot_hash,
        "current_snapshot_hash": current.snapshot_hash,
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged_count": len(unchanged),
        "collection_changes": collection_changes,
    }
    return {**body, "diff_hash": canonical_hash(body)}


def _validate_row_coverage(value: Mapping[str, object]) -> None:
    denominator = _nonnegative_int(
        value.get("denominator_core_rows"), "denominator_core_rows"
    )
    counted = 0
    for state in CoverageState:
        if state.value in value:
            counted += _nonnegative_int(value[state.value], state.value)
    if counted > denominator:
        raise CensusError("provisional row coverage exceeds denominator")
    basis = value.get("basis")
    if basis is not None:
        _nonempty(basis, "basis")


def _require_fields(
    value: Mapping[str, Any], required: set[str], object_name: str
) -> None:
    missing = sorted(required.difference(value))
    if missing:
        raise CensusError(f"{object_name} missing fields: {', '.join(missing)}")


def _nonempty(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CensusError(f"{field} must be a non-empty string")
    return value


def _sha256_text(value: object, field: str) -> str:
    text = _nonempty(value, field)
    if len(text) != 64 or not _lower_hex(text):
        raise CensusError(f"{field} must be a lowercase sha256 hex digest")
    return text


def _git_sha1_text(value: object, field: str) -> str:
    text = _nonempty(value, field)
    if len(text) != 40 or not _lower_hex(text):
        raise CensusError(f"{field} must be a lowercase 40-hex Git SHA-1 object ID")
    return text


def _lower_hex(text: str) -> bool:
    return all(ch in "0123456789abcdef" for ch in text)


def _nonnegative_int(value: object, field: str) -> int:
    if type(value) is not int or value < 0:
        raise CensusError(f"{field} must be a non-negative integer")
    return value


def _strict_bool(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise CensusError(f"{field} must be a boolean")
    return value


def _is_array(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _string_sequence(value: object, field: str) -> tuple[str, ...]:
    if not _is_array(value):
        raise CensusError(f"{field} must be an array")
    return tuple(_nonempty(item, field) for item in value)


def _reject_duplicate_ids(values: Sequence[str], kind: str) -> None:
    duplicates = sorted(item for item, count in Counter(values).items() if count > 1)
    if duplicates:
        raise CensusError(f"duplicate {kind} IDs: {', '.join(duplicates)}")


def _validate_json_value(value: object, field: str) -> None:
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise CensusError(f"{field} must contain finite JSON values") from exc
