"""Machine-checkable completeness and readiness proof.

This module deliberately separates:
1. census acquisition,
2. source-record semantic disposition,
3. private source-body review coverage,
4. driver registry/disposition coverage, and
5. canonical execution readiness.

A green census is never treated as proof that every source body was reviewed.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CENSUS = PROJECT_ROOT / "recovery/LIVE_EMPIRE_SOURCE_CENSUS_EXECUTION_SNAPSHOT_2026-09-17.json"
DEFAULT_SEMANTIC = PROJECT_ROOT / "recovery/SOURCE_SEMANTIC_EVIDENCE_2026-09-18.json"
DEFAULT_DRIVERS = PROJECT_ROOT / "recovery/ECONOMY_DRIVER_COVERAGE_2026-09-17.json"
DEFAULT_CLOSE = PROJECT_ROOT / "recovery/EMPIRE_CLOSE_RECOVERY_2026-09-18.json"
DEFAULT_BODY_RECEIPT = PROJECT_ROOT / "recovery/SOURCE_BODY_REVIEW_RECEIPT_2026-09-18.json"

EXPECTED_DRIVER_REGISTRY = frozenset({
    "business_financial_flows",
    "industrial_production",
    "population",
    "opening_liquidity",
    "banking_balance_sheet",
    "inventories",
    "labor_supply",
    "trade_routes",
    "market_prices",
    "food_supply",
    "household_consumption",
    "credit_origination",
    "tax_rent_tithe_obligations",
    "migration",
    "exogenous_shocks",
    "event_scheduling",
})

COMPLETE_DRIVER_STATUSES = frozenset({
    "COMPLETE_SOURCE_BACKED",
    "COMPLETE_USER_RULED",
    "COMPLETE_UPSTREAM_ADOPTED",
    "UPSTREAM_ADOPTED",
})


class CompletenessError(ValueError):
    pass


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CompletenessError(f"cannot read completeness evidence {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CompletenessError(f"completeness evidence must be an object: {path}")
    return value


def _mapped_source_ids(semantic: dict[str, Any]) -> set[str]:
    membership = semantic.get("current_collection_membership", {}).get("collections", {})
    if not isinstance(membership, dict):
        raise CompletenessError("semantic current_collection_membership.collections must be an object")
    ids: list[str] = []
    for collection in membership.values():
        if not isinstance(collection, dict):
            raise CompletenessError("semantic collection membership row must be an object")
        source_ids = collection.get("source_record_ids", [])
        if not isinstance(source_ids, list) or not all(isinstance(x, str) and x for x in source_ids):
            raise CompletenessError("semantic source_record_ids must be nonempty strings")
        ids.extend(source_ids)
    if len(ids) != len(set(ids)):
        raise CompletenessError("semantic mapped source IDs must be unique")
    return set(ids)


def _close_gap_counts(close: dict[str, Any]) -> tuple[int, int]:
    lanes = close.get("lanes")
    if not isinstance(lanes, dict):
        raise CompletenessError("Empire Close lanes must be an object")
    unresolved = 0
    conflicts = 0
    for lane in lanes.values():
        if not isinstance(lane, dict):
            raise CompletenessError("Empire Close lane must be an object")
        unresolved += len(lane.get("unresolved", []))
        conflicts += len(lane.get("conflicts", []))
    return unresolved, conflicts


def completeness_report(
    *,
    census_path: Path = DEFAULT_CENSUS,
    semantic_path: Path = DEFAULT_SEMANTIC,
    drivers_path: Path = DEFAULT_DRIVERS,
    close_path: Path = DEFAULT_CLOSE,
    body_receipt_path: Path = DEFAULT_BODY_RECEIPT,
) -> dict[str, Any]:
    census = _read_json(census_path)
    semantic = _read_json(semantic_path)
    driver_doc = _read_json(drivers_path)
    close = _read_json(close_path)
    body = _read_json(body_receipt_path)

    meta = census.get("meta", {})
    collections = census.get("collections", [])
    if not isinstance(meta, dict) or not isinstance(collections, list):
        raise CompletenessError("census meta/collections malformed")

    core = meta.get("materializedCore")
    stored = meta.get("storedRecords")
    identified = meta.get("identifiedCore")
    not_materialized = meta.get("notMaterialized")
    baseline_unknown = meta.get("coverageCore", {}).get("UNKNOWN")
    if not all(type(v) is int and v >= 0 for v in (core, stored, identified, not_materialized, baseline_unknown)):
        raise CompletenessError("census counts must be nonnegative integers")
    if core != identified:
        raise CompletenessError("materializedCore and identifiedCore disagree")
    if baseline_unknown > core:
        raise CompletenessError("baseline UNKNOWN cannot exceed retained core")

    acquisition_complete = (
        not_materialized == 0
        and core == identified
        and all(
            isinstance(row, dict)
            and row.get("complete") is True
            and type(row.get("rowCount")) is int
            and type(row.get("captured")) is int
            and row["captured"] >= row["rowCount"]
            for row in collections
        )
    )

    mapped_ids = _mapped_source_ids(semantic)
    if len(mapped_ids) > baseline_unknown:
        raise CompletenessError("semantic mapped IDs exceed baseline UNKNOWN population")
    current_unknown = baseline_unknown - len(mapped_ids)
    reviewed_core = core - current_unknown

    body_target = body.get("retained_core_target")
    if body_target != core:
        raise CompletenessError("body review target must equal retained core census")
    reviewed_bodies = body.get("reviewed_retained_core")
    unread_bodies = body.get("unread_retained_core")
    body_review_complete = (
        body.get("tracking_status") == "COMPLETE"
        and type(reviewed_bodies) is int
        and type(unread_bodies) is int
        and reviewed_bodies == core
        and unread_bodies == 0
    )

    drivers = driver_doc.get("drivers")
    if not isinstance(drivers, list):
        raise CompletenessError("drivers must be a list")
    by_name: dict[str, dict[str, Any]] = {}
    for row in drivers:
        if not isinstance(row, dict) or not isinstance(row.get("driver"), str):
            raise CompletenessError("driver row malformed")
        name = row["driver"]
        if name in by_name:
            raise CompletenessError(f"duplicate driver {name}")
        by_name[name] = row

    actual_drivers = frozenset(by_name)
    driver_registry_complete = actual_drivers == EXPECTED_DRIVER_REGISTRY
    missing_drivers = sorted(EXPECTED_DRIVER_REGISTRY - actual_drivers)
    unexpected_drivers = sorted(actual_drivers - EXPECTED_DRIVER_REGISTRY)

    undisposed_drivers = []
    incomplete_drivers = []
    blocked_drivers = []
    for name, row in sorted(by_name.items()):
        status = row.get("status")
        blocks = row.get("blocks", [])
        can_execute = row.get("can_execute")
        if not isinstance(status, str) or not isinstance(blocks, list) or type(can_execute) is not bool:
            undisposed_drivers.append(name)
            continue
        if not can_execute:
            blocked_drivers.append(name)
        if status not in COMPLETE_DRIVER_STATUSES or blocks:
            incomplete_drivers.append(name)

    driver_dispositions_complete = not undisposed_drivers
    canonical_driver_ready = (
        driver_registry_complete
        and driver_dispositions_complete
        and not incomplete_drivers
        and all(row.get("can_execute") is True for row in by_name.values())
    )

    unresolved_close, conflict_close = _close_gap_counts(close)
    close_zero_time = (
        close.get("canonical") is False
        and close.get("campaign_time_advanced") is False
        and close.get("notion_writes") == 0
    )
    if not close_zero_time:
        raise CompletenessError("Empire Close evidence crossed a locked recovery boundary")

    semantic_disposition_complete = current_unknown == 0
    coverage_claim_allowed = (
        acquisition_complete
        and semantic_disposition_complete
        and body_review_complete
        and driver_registry_complete
        and driver_dispositions_complete
    )
    canonical_execution_ready = (
        coverage_claim_allowed
        and canonical_driver_ready
        and unresolved_close == 0
        and conflict_close == 0
    )

    return {
        "schema": "tnp.economy.completeness-report/1",
        "campaign_boundary": meta.get("campaignBoundary"),
        "coverage_claim_allowed": coverage_claim_allowed,
        "canonical_execution_ready": canonical_execution_ready,
        "gates": {
            "collection_acquisition": {
                "pass": acquisition_complete,
                "collections": len(collections),
                "retained_core_records": core,
                "stored_records_including_context": stored,
                "not_materialized": not_materialized,
            },
            "source_record_semantic_disposition": {
                "pass": semantic_disposition_complete,
                "retained_core_records": core,
                "reviewed_or_explicitly_disposed": reviewed_core,
                "unknown": current_unknown,
                "new_source_mapped_ids": len(mapped_ids),
                "rule": "UNKNOWN must reach zero; acquisition alone is not review.",
            },
            "source_body_review": {
                "pass": body_review_complete,
                "tracking_status": body.get("tracking_status"),
                "retained_core_target": body_target,
                "reviewed_retained_core": reviewed_bodies,
                "unread_retained_core": unread_bodies,
                "rule": "Every retained source record needs a body-read receipt or explicit no-body/not-applicable disposition.",
            },
            "driver_registry": {
                "pass": driver_registry_complete,
                "expected": len(EXPECTED_DRIVER_REGISTRY),
                "present": len(actual_drivers),
                "missing": missing_drivers,
                "unexpected": unexpected_drivers,
            },
            "driver_dispositions": {
                "pass": driver_dispositions_complete,
                "undisposed": undisposed_drivers,
                "incomplete": incomplete_drivers,
                "blocked": blocked_drivers,
            },
            "empire_close": {
                "pass_for_coverage": True,
                "unresolved_items": unresolved_close,
                "conflicts": conflict_close,
                "canonical_driver_ready": canonical_driver_ready,
            },
            "locked_boundaries": {
                "pass": close_zero_time,
                "notion_writes": 0,
                "campaign_time_advanced": False,
                "canonical_month_executed": False,
            },
        },
        "proof_standard": {
            "coverage_complete_when": [
                "all collection members/materialized records reconcile",
                "retained-core UNKNOWN count is zero",
                "every retained source body has a read/disposition receipt without publishing private prose",
                "the finite driver registry is intact",
                "every driver has an explicit disposition",
            ],
            "canonical_ready_additionally_requires": [
                "all drivers complete and executable",
                "zero unresolved Empire Close blockers",
                "zero unresolved Empire Close conflicts",
            ],
        },
        "next_required_work": [
            "build privacy-preserving body-read receipts for all retained core source records",
            "classify every remaining UNKNOWN source record instead of doing ad-hoc sweeps",
            "route ECONOMIC_INPUT records to one or more driver/mechanic owners",
            "keep unresolved values explicit; do not invent balancing numbers",
        ],
    }
