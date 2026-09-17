"""Canonical JSON codecs for durable operator state."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from decimal import Decimal
from enum import Enum
import hashlib
import json
from typing import Mapping

from .domain import (
    Authority,
    SimulationAssignment,
    SimulationMode,
    TemporalState,
    canonical_decimal,
)
from .events import CampaignDate, EventEnvelope, ResolutionStatus
from .stockflow import (
    InventoryPosition,
    Need,
    PricePosition,
    ProductionOrder,
    RunPlan,
    ShipmentOrder,
    Snapshot,
    TransitLot,
)


class CodecError(ValueError):
    """Raised when persisted operator data is malformed or has drifted."""


def json_safe(value: object) -> object:
    """Return a canonical-JSON-safe tree without binary floating-point values."""

    if isinstance(value, Decimal):
        return canonical_decimal(value)
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return json_safe(asdict(value))
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise CodecError("canonical JSON mapping keys must be strings")
        return {
            key: json_safe(item)
            for key, item in sorted(value.items(), key=lambda pair: pair[0])
        }
    if isinstance(value, (tuple, list)):
        return [json_safe(item) for item in value]
    if isinstance(value, float):
        raise CodecError("binary floating-point values cannot enter operator state")
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise CodecError(f"unsupported operator value: {type(value).__name__}")


def canonical_dumps(value: object) -> str:
    return json.dumps(
        json_safe(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def canonical_hash(value: object) -> str:
    return hashlib.sha256(canonical_dumps(value).encode("utf-8")).hexdigest()


def with_content_hash(body: Mapping[str, object]) -> dict[str, object]:
    if "content_hash" in body:
        raise CodecError("content_hash must be added by the codec")
    result = dict(body)
    result["content_hash"] = canonical_hash(body)
    return result


def verify_content_hash(payload: Mapping[str, object], *, label: str) -> None:
    content_hash = payload.get("content_hash")
    if not isinstance(content_hash, str) or len(content_hash) != 64:
        raise CodecError(f"{label} is missing a full content hash")
    body = dict(payload)
    del body["content_hash"]
    if canonical_hash(body) != content_hash:
        raise CodecError(f"{label} content hash does not match its payload")


def snapshot_to_payload(snapshot: Snapshot) -> dict[str, object]:
    snapshot.verify()
    return {
        "schema": "tnp.economy.snapshot-storage/1",
        "timeline_id": snapshot.timeline_id,
        "period_index": snapshot.period_index,
        "campaign_ordinal": snapshot.campaign_ordinal,
        "campaign_date": snapshot.campaign_date,
        "ruleset_version": snapshot.ruleset_version,
        "ruleset_hash": snapshot.ruleset_hash,
        "model_hash": snapshot.model_hash,
        "input_hash": snapshot.input_hash,
        "parent_hash": snapshot.parent_hash,
        "inventories": [
            {
                "site_id": item.site_id,
                "commodity_id": item.commodity_id,
                "quantity": canonical_decimal(item.quantity),
                "reserved_quantity": canonical_decimal(item.reserved_quantity),
            }
            for item in snapshot.inventories
        ],
        "prices": [
            {
                "site_id": item.site_id,
                "commodity_id": item.commodity_id,
                "amount": canonical_decimal(item.amount),
            }
            for item in snapshot.prices
        ],
        "transit": [
            {
                "shipment_id": item.shipment_id,
                "route_id": item.route_id,
                "commodity_id": item.commodity_id,
                "origin_site_id": item.origin_site_id,
                "destination_site_id": item.destination_site_id,
                "quantity": canonical_decimal(item.quantity),
                "arrival_period_index": item.arrival_period_index,
                "loss_rate": canonical_decimal(item.loss_rate),
            }
            for item in snapshot.transit
        ],
        "applied_event_refs": [list(item) for item in snapshot.applied_event_refs],
        "applied_shipment_ids": list(snapshot.applied_shipment_ids),
        "snapshot_id": snapshot.snapshot_id,
        "state_hash": snapshot.state_hash,
    }


def snapshot_from_payload(payload: Mapping[str, object]) -> Snapshot:
    try:
        _exact_keys(
            payload,
            {
                "schema",
                "timeline_id",
                "period_index",
                "campaign_ordinal",
                "campaign_date",
                "ruleset_version",
                "ruleset_hash",
                "model_hash",
                "input_hash",
                "parent_hash",
                "inventories",
                "prices",
                "transit",
                "applied_event_refs",
                "applied_shipment_ids",
                "snapshot_id",
                "state_hash",
            },
            "snapshot",
        )
        if payload.get("schema") != "tnp.economy.snapshot-storage/1":
            raise CodecError("snapshot storage schema is unsupported")
        inventories = tuple(
            InventoryPosition(
                str(item["site_id"]),
                str(item["commodity_id"]),
                _decimal(item["quantity"], "inventory quantity"),
                _decimal(item["reserved_quantity"], "reserved inventory quantity"),
            )
            for item in _objects(
                payload.get("inventories"),
                "snapshot inventories",
                {"site_id", "commodity_id", "quantity", "reserved_quantity"},
            )
        )
        prices = tuple(
            PricePosition(
                str(item["site_id"]),
                str(item["commodity_id"]),
                _decimal(item["amount"], "price amount"),
            )
            for item in _objects(
                payload.get("prices"),
                "snapshot prices",
                {"site_id", "commodity_id", "amount"},
            )
        )
        transit = tuple(
            TransitLot(
                shipment_id=str(item["shipment_id"]),
                route_id=str(item["route_id"]),
                commodity_id=str(item["commodity_id"]),
                origin_site_id=str(item["origin_site_id"]),
                destination_site_id=str(item["destination_site_id"]),
                quantity=_decimal(item["quantity"], "transit quantity"),
                arrival_period_index=_integer(
                    item["arrival_period_index"], "transit arrival period"
                ),
                loss_rate=_decimal(item["loss_rate"], "transit loss rate"),
            )
            for item in _objects(
                payload.get("transit"),
                "snapshot transit",
                {
                    "shipment_id",
                    "route_id",
                    "commodity_id",
                    "origin_site_id",
                    "destination_site_id",
                    "quantity",
                    "arrival_period_index",
                    "loss_rate",
                },
            )
        )
        applied_refs_raw = payload.get("applied_event_refs")
        if not isinstance(applied_refs_raw, list) or any(
            not isinstance(item, list)
            or len(item) != 2
            or any(not isinstance(part, str) for part in item)
            for item in applied_refs_raw
        ):
            raise CodecError("snapshot applied event references are malformed")
        shipment_ids = payload.get("applied_shipment_ids")
        if not isinstance(shipment_ids, list) or any(
            not isinstance(item, str) for item in shipment_ids
        ):
            raise CodecError("snapshot applied shipment IDs are malformed")
        snapshot = Snapshot(
            timeline_id=_text(payload.get("timeline_id"), "snapshot timeline"),
            period_index=_integer(payload.get("period_index"), "snapshot period"),
            campaign_ordinal=_integer(
                payload.get("campaign_ordinal"), "snapshot campaign ordinal"
            ),
            campaign_date=_text(payload.get("campaign_date"), "snapshot campaign date"),
            ruleset_version=_text(
                payload.get("ruleset_version"), "snapshot ruleset version"
            ),
            ruleset_hash=_text(payload.get("ruleset_hash"), "snapshot ruleset hash"),
            model_hash=_text(payload.get("model_hash"), "snapshot model hash"),
            input_hash=_optional_text(payload.get("input_hash"), "snapshot input hash"),
            parent_hash=_optional_text(payload.get("parent_hash"), "snapshot parent hash"),
            inventories=inventories,
            prices=prices,
            transit=transit,
            applied_event_refs=tuple(tuple(item) for item in applied_refs_raw),
            applied_shipment_ids=tuple(shipment_ids),
            snapshot_id=_text(payload.get("snapshot_id"), "snapshot ID"),
            state_hash=_text(payload.get("state_hash"), "snapshot state hash"),
        )
        snapshot.verify()
        return snapshot
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, CodecError):
            raise
        raise CodecError(f"stored snapshot is malformed: {exc}") from exc


def run_plan_from_payload(payload: Mapping[str, object]) -> RunPlan:
    """Strictly reconstruct a stored plan for independent deterministic replay."""

    try:
        _exact_keys(
            payload,
            {
                "schema",
                "period_index",
                "campaign_ordinal",
                "campaign_date",
                "production_orders",
                "shipment_orders",
                "needs",
                "authorizing_events",
                "simulation_assignments",
            },
            "run plan",
        )
        if payload.get("schema") != "tnp.economy.run-plan-storage/1":
            raise CodecError("run-plan storage schema is unsupported")
        production = tuple(
            ProductionOrder(
                recipe_id=_text(item.get("recipe_id"), "production recipe ID"),
                requested_batches=_decimal(
                    item.get("requested_batches"), "requested production batches"
                ),
                authorizing_event_id=_optional_text(
                    item.get("authorizing_event_id"), "production authorizing event"
                ),
            )
            for item in _objects(
                payload.get("production_orders"),
                "production orders",
                {"recipe_id", "requested_batches", "authorizing_event_id"},
            )
        )
        shipments = tuple(
            ShipmentOrder(
                shipment_id=_text(item.get("shipment_id"), "shipment ID"),
                route_id=_text(item.get("route_id"), "shipment route ID"),
                commodity_id=_text(item.get("commodity_id"), "shipment commodity ID"),
                requested_quantity=_decimal(
                    item.get("requested_quantity"), "requested shipment quantity"
                ),
                source_ref=_text(item.get("source_ref"), "shipment source reference"),
                authorizing_event_id=_optional_text(
                    item.get("authorizing_event_id"), "shipment authorizing event"
                ),
            )
            for item in _objects(
                payload.get("shipment_orders"),
                "shipment orders",
                {
                    "shipment_id",
                    "route_id",
                    "commodity_id",
                    "requested_quantity",
                    "source_ref",
                    "authorizing_event_id",
                },
            )
        )
        needs = tuple(
            Need(
                site_id=_text(item.get("site_id"), "need site ID"),
                commodity_id=_text(item.get("commodity_id"), "need commodity ID"),
                requested_quantity=_decimal(
                    item.get("requested_quantity"), "requested need quantity"
                ),
                priority=_integer(item.get("priority"), "need priority"),
                authorizing_event_id=_optional_text(
                    item.get("authorizing_event_id"), "need authorizing event"
                ),
            )
            for item in _objects(
                payload.get("needs"),
                "needs",
                {
                    "site_id",
                    "commodity_id",
                    "requested_quantity",
                    "priority",
                    "authorizing_event_id",
                },
            )
        )
        events = tuple(
            _event_from_payload(item)
            for item in _objects(
                payload.get("authorizing_events"),
                "authorizing events",
                {
                    "schema_version",
                    "source_event_key",
                    "event_revision",
                    "event_id",
                    "payload_hash",
                    "timeline_id",
                    "model_version",
                    "campaign_date",
                    "phase",
                    "sequence",
                    "authority",
                    "temporal_state",
                    "resolution_status",
                    "source_ref",
                    "event_type",
                    "subject_entity_id",
                    "subject_site_id",
                    "payload_json",
                    "reverses_event_id",
                },
            )
        )
        assignments = tuple(
            SimulationAssignment(
                entity_id=_text(item.get("entity_id"), "assignment entity ID"),
                timeline_id=_text(item.get("timeline_id"), "assignment timeline ID"),
                period_index=_integer(item.get("period_index"), "assignment period"),
                mode=SimulationMode(_text(item.get("mode"), "assignment mode")),
                source_ref=_text(item.get("source_ref"), "assignment source reference"),
            )
            for item in _objects(
                payload.get("simulation_assignments"),
                "simulation assignments",
                {"entity_id", "timeline_id", "period_index", "mode", "source_ref"},
            )
        )
        return RunPlan(
            period_index=_integer(payload.get("period_index"), "run-plan period"),
            campaign_ordinal=_integer(
                payload.get("campaign_ordinal"), "run-plan campaign ordinal"
            ),
            campaign_date=_text(payload.get("campaign_date"), "run-plan campaign date"),
            production_orders=production,
            shipment_orders=shipments,
            needs=needs,
            authorizing_events=events,
            simulation_assignments=assignments,
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, CodecError):
            raise
        raise CodecError(f"stored run plan is malformed: {exc}") from exc


def _event_from_payload(payload: Mapping[str, object]) -> EventEnvelope:
    campaign_date_payload = payload.get("campaign_date")
    if not isinstance(campaign_date_payload, Mapping):
        raise CodecError("event campaign date must be an object")
    _exact_keys(
        campaign_date_payload,
        {"ordinal", "label", "year_dr", "month_code", "day", "precision"},
        "event campaign date",
    )
    event = EventEnvelope(
        schema_version=_integer(payload.get("schema_version"), "event schema version"),
        source_event_key=_text(payload.get("source_event_key"), "source event key"),
        event_revision=_integer(payload.get("event_revision"), "event revision"),
        event_id=_text(payload.get("event_id"), "event ID"),
        payload_hash=_text(payload.get("payload_hash"), "event payload hash"),
        timeline_id=_text(payload.get("timeline_id"), "event timeline"),
        model_version=_text(payload.get("model_version"), "event model version"),
        campaign_date=CampaignDate(
            ordinal=_integer(campaign_date_payload.get("ordinal"), "event date ordinal"),
            label=_text(campaign_date_payload.get("label"), "event date label"),
            year_dr=_optional_integer(campaign_date_payload.get("year_dr"), "event year"),
            month_code=_optional_text(
                campaign_date_payload.get("month_code"), "event month code"
            ),
            day=_optional_integer(campaign_date_payload.get("day"), "event day"),
            precision=_text(campaign_date_payload.get("precision"), "event date precision"),
        ),
        phase=_text(payload.get("phase"), "event phase"),
        sequence=_integer(payload.get("sequence"), "event sequence"),
        authority=Authority(_text(payload.get("authority"), "event authority")),
        temporal_state=TemporalState(
            _text(payload.get("temporal_state"), "event temporal state")
        ),
        resolution_status=ResolutionStatus(
            _text(payload.get("resolution_status"), "event resolution status")
        ),
        source_ref=_text(payload.get("source_ref"), "event source reference"),
        event_type=_text(payload.get("event_type"), "event type"),
        subject_entity_id=_optional_text(
            payload.get("subject_entity_id"), "event subject entity ID"
        ),
        subject_site_id=_optional_text(
            payload.get("subject_site_id"), "event subject site ID"
        ),
        payload_json=_text(payload.get("payload_json"), "event payload JSON"),
        reverses_event_id=_optional_text(
            payload.get("reverses_event_id"), "reversed event ID"
        ),
    )
    event.validate_integrity()
    return event


def _objects(
    value: object, label: str, expected_keys: set[str]
) -> list[Mapping[str, object]]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise CodecError(f"{label} must be an array of objects")
    for item in value:
        _exact_keys(item, expected_keys, label)
    return value


def _exact_keys(value: Mapping[str, object], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise CodecError(
            f"{label} keys do not match the storage schema; "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )


def _decimal(value: object, label: str) -> Decimal:
    if not isinstance(value, str):
        raise CodecError(f"{label} must be a canonical decimal string")
    try:
        result = Decimal(value)
    except Exception as exc:  # Decimal raises several implementation exceptions.
        raise CodecError(f"{label} is not a decimal") from exc
    if not result.is_finite() or canonical_decimal(result) != value:
        raise CodecError(f"{label} is not a canonical finite decimal")
    return result


def _integer(value: object, label: str) -> int:
    if type(value) is not int:
        raise CodecError(f"{label} must be an integer")
    return value


def _optional_integer(value: object, label: str) -> int | None:
    if value is None:
        return None
    return _integer(value, label)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CodecError(f"{label} is required")
    return value


def _optional_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _text(value, label)
