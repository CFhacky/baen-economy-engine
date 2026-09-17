"""Typed, deterministic economic-event envelopes and append-only identity checks."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
import hashlib
import json
import re
from typing import Mapping
from uuid import UUID, uuid5

from .domain import Authority, TemporalState, canonical_decimal


EVENT_NAMESPACE = UUID("0d76d680-5053-5adb-a8c5-7f3ae909d145")
CURRENT_MODEL_VERSION = "economy-0.1"
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
CAMPAIGN_DATE_PRECISIONS = frozenset({"day", "month", "year", "approximate", "unknown"})


class ResolutionStatus(StrEnum):
    PENDING = "pending"
    RESOLVED = "resolved"


class EventPhase(StrEnum):
    SOURCE_LOCK = "source_lock"
    ARRIVAL = "arrival"
    PRODUCTION = "production"
    SHIPMENT = "shipment"
    CONSUMPTION = "consumption"
    MARKET = "market"
    FINANCE = "finance"
    CLOSE = "close"


PHASE_RANK = {phase.value: rank for rank, phase in enumerate(EventPhase)}


@dataclass(frozen=True, slots=True, order=True)
class CampaignDate:
    ordinal: int
    label: str
    year_dr: int | None = None
    month_code: str | None = None
    day: int | None = None
    precision: str = "day"

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or not isinstance(self.ordinal, int):
            raise ValueError("campaign-date ordinal must be an integer")
        _validate_required_text(self.label, "campaign-date label")
        if self.year_dr is not None and (
            isinstance(self.year_dr, bool) or not isinstance(self.year_dr, int)
        ):
            raise ValueError("campaign-date year must be an integer when supplied")
        if self.month_code is not None:
            _validate_required_text(self.month_code, "campaign-date month code")
        if self.day is not None and (
            isinstance(self.day, bool)
            or not isinstance(self.day, int)
            or not 1 <= self.day <= 31
        ):
            raise ValueError("campaign-date day must be an integer from 1 through 31")
        if self.precision not in CAMPAIGN_DATE_PRECISIONS:
            raise ValueError("campaign-date precision is unsupported")


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    schema_version: int
    source_event_key: str
    event_revision: int
    event_id: str
    payload_hash: str
    timeline_id: str
    model_version: str
    campaign_date: CampaignDate
    phase: str
    sequence: int
    authority: Authority
    temporal_state: TemporalState
    resolution_status: ResolutionStatus
    source_ref: str
    event_type: str
    subject_entity_id: str | None
    subject_site_id: str | None
    payload_json: str
    reverses_event_id: str | None = None

    @classmethod
    def create(
        cls,
        *,
        source_event_key: str,
        event_revision: int,
        timeline_id: str,
        model_version: str,
        campaign_date: CampaignDate,
        phase: str,
        sequence: int,
        authority: Authority,
        temporal_state: TemporalState,
        resolution_status: ResolutionStatus,
        source_ref: str,
        event_type: str,
        payload: Mapping[str, object],
        subject_entity_id: str | None = None,
        subject_site_id: str | None = None,
        reverses_event_id: str | None = None,
    ) -> "EventEnvelope":
        if isinstance(event_revision, bool) or not isinstance(event_revision, int) or event_revision < 1:
            raise ValueError("event revision must be positive")
        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 0:
            raise ValueError("event sequence must be a non-negative integer")
        for value, label in (
            (source_event_key, "source event key"),
            (source_ref, "source reference"),
            (timeline_id, "event timeline"),
            (model_version, "event model version"),
            (event_type, "event type"),
        ):
            _validate_required_text(value, label)
        for value, label in (
            (subject_entity_id, "subject entity ID"),
            (subject_site_id, "subject site ID"),
            (reverses_event_id, "reversed event ID"),
        ):
            if value is not None:
                _validate_required_text(value, label)
        if phase not in PHASE_RANK:
            raise ValueError(f"unknown event phase: {phase}")
        payload_json = canonical_json(payload)
        payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        identity = canonical_json(
            [
                timeline_id,
                source_event_key,
                event_revision,
                event_type,
                campaign_date.ordinal,
                sequence,
            ]
        )
        event_id = f"event:{uuid5(EVENT_NAMESPACE, identity)}"
        return cls(
            1, source_event_key, event_revision, event_id, payload_hash,
            timeline_id, model_version, campaign_date, phase, sequence,
            authority, temporal_state, resolution_status, source_ref, event_type,
            subject_entity_id, subject_site_id, payload_json, reverses_event_id,
        )

    @property
    def may_mutate_actual(self) -> bool:
        return (
            self.timeline_id == "actual"
            and self.temporal_state is TemporalState.CURRENT
            and self.resolution_status is ResolutionStatus.RESOLVED
            and self.authority
            in {
                Authority.CANON_IMPORT,
                Authority.USER_RULING,
                Authority.CAMPAIGN_RESOLUTION,
            }
            and self.reverses_event_id is None
        )

    @property
    def may_reverse_actual(self) -> bool:
        """Whether a correction has enough authority to deactivate actual history."""

        return (
            self.timeline_id == "actual"
            and self.temporal_state is TemporalState.CURRENT
            and self.resolution_status is ResolutionStatus.RESOLVED
            and self.authority
            in {
                Authority.CANON_IMPORT,
                Authority.USER_RULING,
                Authority.CAMPAIGN_RESOLUTION,
            }
            and self.reverses_event_id is not None
        )

    def validate_integrity(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError(f"unsupported event schema version: {self.schema_version}")
        if (
            isinstance(self.event_revision, bool)
            or not isinstance(self.event_revision, int)
            or self.event_revision < 1
        ):
            raise ValueError("event revision must be a positive integer")
        if (
            isinstance(self.sequence, bool)
            or not isinstance(self.sequence, int)
            or self.sequence < 0
        ):
            raise ValueError("event sequence must be a non-negative integer")
        for value, label in (
            (self.source_event_key, "source event key"),
            (self.timeline_id, "event timeline"),
            (self.model_version, "event model version"),
            (self.source_ref, "source reference"),
            (self.event_type, "event type"),
        ):
            _validate_required_text(value, label)
        for value, label in (
            (self.subject_entity_id, "subject entity ID"),
            (self.subject_site_id, "subject site ID"),
            (self.reverses_event_id, "reversed event ID"),
        ):
            if value is not None:
                _validate_required_text(value, label)
        if not isinstance(self.campaign_date, CampaignDate):
            raise ValueError("event campaign date has the wrong type")
        if not isinstance(self.authority, Authority):
            raise ValueError("event authority has the wrong type")
        if not isinstance(self.temporal_state, TemporalState):
            raise ValueError("event temporal state has the wrong type")
        if not isinstance(self.resolution_status, ResolutionStatus):
            raise ValueError("event resolution status has the wrong type")
        try:
            payload = json.loads(self.payload_json)
        except json.JSONDecodeError as exc:
            raise ValueError("event payload_json is not valid JSON") from exc
        canonical_payload = canonical_json(payload)
        expected_payload_hash = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
        if canonical_payload != self.payload_json or expected_payload_hash != self.payload_hash:
            raise ValueError("event payload hash or canonical JSON does not match")
        identity = canonical_json(
            [
                self.timeline_id,
                self.source_event_key,
                self.event_revision,
                self.event_type,
                self.campaign_date.ordinal,
                self.sequence,
            ]
        )
        if self.event_id != f"event:{uuid5(EVENT_NAMESPACE, identity)}":
            raise ValueError("event ID does not match its deterministic identity")
        if self.phase not in PHASE_RANK:
            raise ValueError("event has an unknown phase")

    @property
    def integrity_hash(self) -> str:
        """Hash every semantic and provenance field of a validated envelope."""

        self.validate_integrity()
        value = {
            "schema_version": self.schema_version,
            "source_event_key": self.source_event_key,
            "event_revision": self.event_revision,
            "event_id": self.event_id,
            "payload_hash": self.payload_hash,
            "timeline_id": self.timeline_id,
            "model_version": self.model_version,
            "campaign_date": {
                "ordinal": self.campaign_date.ordinal,
                "label": self.campaign_date.label,
                "year_dr": self.campaign_date.year_dr,
                "month_code": self.campaign_date.month_code,
                "day": self.campaign_date.day,
                "precision": self.campaign_date.precision,
            },
            "phase": self.phase,
            "sequence": self.sequence,
            "authority": self.authority.value,
            "temporal_state": self.temporal_state.value,
            "resolution_status": self.resolution_status.value,
            "source_ref": self.source_ref,
            "event_type": self.event_type,
            "subject_entity_id": self.subject_entity_id,
            "subject_site_id": self.subject_site_id,
            "payload_json": self.payload_json,
            "reverses_event_id": self.reverses_event_id,
        }
        return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class EventStore:
    """Append-only identity gate; persistence is added after the Gate-0 schema."""

    def __init__(self) -> None:
        self._events_by_id: dict[str, EventEnvelope] = {}
        self._source_revisions: dict[
            tuple[str, str, str, int], EventEnvelope
        ] = {}
        self._reversed_event_ids: set[str] = set()

    def append(self, event: EventEnvelope) -> None:
        if type(event) is not EventEnvelope:
            raise ValueError("event store accepts only concrete EventEnvelope values")
        event.validate_integrity()
        prior_id = self._events_by_id.get(event.event_id)
        if prior_id is not None:
            if prior_id == event:
                raise ValueError(f"duplicate event already appended: {event.event_id}")
            raise ValueError(f"event ID collision with changed payload: {event.event_id}")
        source_key = (
            event.timeline_id,
            event.model_version,
            event.source_event_key,
            event.event_revision,
        )
        prior_source = self._source_revisions.get(source_key)
        if prior_source is not None:
            raise ValueError(
                f"source event revision already exists with event {prior_source.event_id}"
            )
        if event.event_revision == 1 and event.reverses_event_id is not None:
            raise ValueError("first event revision cannot reverse another event")
        if event.event_revision > 1:
            preceding = self._source_revisions.get(
                (
                    event.timeline_id,
                    event.model_version,
                    event.source_event_key,
                    event.event_revision - 1,
                )
            )
            if preceding is None:
                raise ValueError("event revision has no preceding source revision")
            if event.reverses_event_id != preceding.event_id:
                raise ValueError("correction must explicitly reverse the preceding event")
            if event.timeline_id == "actual" and not event.may_reverse_actual:
                raise ValueError(
                    "actual correction must be current, resolved, and authoritative"
                )
        self._events_by_id[event.event_id] = event
        self._source_revisions[source_key] = event
        if event.reverses_event_id is not None:
            self._reversed_event_ids.add(event.reverses_event_id)

    @property
    def events(self) -> tuple[EventEnvelope, ...]:
        return tuple(
            sorted(
                self._events_by_id.values(),
                key=lambda event: (
                    event.campaign_date.ordinal,
                    PHASE_RANK[event.phase],
                    event.sequence,
                    event.subject_entity_id or "",
                    event.event_id,
                ),
            )
        )

    def contains_exact(self, event: EventEnvelope) -> bool:
        return self._events_by_id.get(event.event_id) == event

    def contains_active(self, event: EventEnvelope) -> bool:
        return self.contains_exact(event) and event.event_id not in self._reversed_event_ids

    def contains_active_ref(self, event_id: str, integrity_hash: str) -> bool:
        event = self._events_by_id.get(event_id)
        return (
            event is not None
            and event.event_id not in self._reversed_event_ids
            and event.integrity_hash == integrity_hash
        )


def canonical_json(value: object) -> str:
    def normalize(item: object) -> object:
        if isinstance(item, Decimal):
            return canonical_decimal(item)
        if isinstance(item, Mapping):
            if any(not isinstance(key, str) for key in item):
                raise TypeError("canonical JSON object keys must be strings")
            return {
                key: normalize(val)
                for key, val in sorted(item.items(), key=lambda pair: pair[0])
            }
        if isinstance(item, (tuple, list)):
            return [normalize(val) for val in item]
        if isinstance(item, (str, int, bool)) or item is None:
            return item
        raise TypeError(f"unsupported canonical JSON value: {type(item).__name__}")

    return json.dumps(normalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _validate_required_text(value: object, label: str) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or CONTROL_RE.search(value)
    ):
        raise ValueError(f"{label} must be non-empty and contain no control characters")
