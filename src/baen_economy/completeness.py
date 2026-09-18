"""Machine-checkable completeness and readiness proof.

This module deliberately separates:
1. collection/member acquisition,
2. source-record semantic status,
3. finite retained-core review-queue integrity,
4. private source-body review and explicit disposition,
5. driver registry/disposition coverage, and
6. canonical execution readiness.

A green census is never treated as proof that every source body was reviewed.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CENSUS = PROJECT_ROOT / "recovery/LIVE_EMPIRE_SOURCE_CENSUS_EXECUTION_SNAPSHOT_2026-09-17.json"
DEFAULT_EXECUTION_CENSUS = PROJECT_ROOT / "recovery/LIVE_EMPIRE_SOURCE_CENSUS_EXECUTION_2026-09-17.json"
DEFAULT_SEMANTIC = PROJECT_ROOT / "recovery/SOURCE_SEMANTIC_EVIDENCE_2026-09-18.json"
DEFAULT_DRIVERS = PROJECT_ROOT / "recovery/ECONOMY_DRIVER_COVERAGE_2026-09-17.json"
DEFAULT_CLOSE = PROJECT_ROOT / "recovery/EMPIRE_CLOSE_RECOVERY_2026-09-18.json"
DEFAULT_BODY_RECEIPT = PROJECT_ROOT / "recovery/SOURCE_BODY_REVIEW_RECEIPT_2026-09-18.json"
DEFAULT_REVIEW_QUEUE = PROJECT_ROOT / "recovery/SOURCE_REVIEW_QUEUE_2026-09-18.json"

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

# These ten classes are the retained core collection rows in the full execution
# census. Contextual authority records deliberately use other source classes.
CORE_SOURCE_CLASSES = frozenset({
    "business_registry",
    "locations",
    "factions",
    "npcs",
    "shocks_shortages_threats",
    "contracts_orders_obligations_threads",
    "demand_perception_context",
    "inventories_materials_hoards_assets",
    "consequence_ledger_a",
    "consequence_ledger_b",
})

COMPLETE_DRIVER_STATUSES = frozenset({
    "COMPLETE_SOURCE_BACKED",
    "COMPLETE_USER_RULED",
    "COMPLETE_UPSTREAM_ADOPTED",
    "UPSTREAM_ADOPTED",
})

ALLOWED_REVIEW_DISPOSITIONS = frozenset({
    "ECONOMIC_INPUT",
    "ECONOMIC_CONTEXT",
    "NON_ECONOMIC",
    "HISTORICAL_ONLY",
    "FUTURE_ONLY",
    "SUPERSEDED",
    "CONFLICT",
    "MISSING_DATA",
    "MISSING_MECHANICS",
    "NO_BODY_NOT_APPLICABLE",
})

BODY_COMPLETE_STATUSES = frozenset({"REVIEWED", "NO_BODY_NOT_APPLICABLE"})


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


def _normalized_source_id(value: str) -> str:
    return value.replace("-", "").replace("notion:page:", "")


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
        ids.extend(_normalized_source_id(x) for x in source_ids)
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


def _execution_core_records(execution: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = execution.get("records")
    if not isinstance(rows, list):
        raise CompletenessError("full execution census records must be a list")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("sourceClass") not in CORE_SOURCE_CLASSES:
            continue
        stable = row.get("stableSourceId")
        if not isinstance(stable, str) or not stable:
            raise CompletenessError("core execution record lacks stableSourceId")
        if stable in result:
            raise CompletenessError(f"duplicate core stable source ID {stable}")
        result[stable] = row
    return result


def completeness_report(
    *,
    census_path: Path = DEFAULT_CENSUS,
    execution_census_path: Path = DEFAULT_EXECUTION_CENSUS,
    semantic_path: Path = DEFAULT_SEMANTIC,
    drivers_path: Path = DEFAULT_DRIVERS,
    close_path: Path = DEFAULT_CLOSE,
    body_receipt_path: Path = DEFAULT_BODY_RECEIPT,
    review_queue_path: Path = DEFAULT_REVIEW_QUEUE,
) -> dict[str, Any]:
    census = _read_json(census_path)
    execution = _read_json(execution_census_path)
    semantic = _read_json(semantic_path)
    driver_doc = _read_json(drivers_path)
    close = _read_json(close_path)
    body = _read_json(body_receipt_path)
    queue = _read_json(review_queue_path)

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
    semantic_non_unknown = core - current_unknown

    execution_core = _execution_core_records(execution)
    if len(execution_core) != core:
        raise CompletenessError(
            f"full execution census core count {len(execution_core)} does not match retained core {core}"
        )

    queue_records = queue.get("records")
    if queue.get("schema") != "tnp.economy.source-review-queue/1" or not isinstance(queue_records, list):
        raise CompletenessError("source review queue schema/records malformed")
    queue_by_id: dict[str, dict[str, Any]] = {}
    for row in queue_records:
        if not isinstance(row, dict):
            raise CompletenessError("source review queue row must be an object")
        stable = row.get("stable_source_id")
        if not isinstance(stable, str) or not stable:
            raise CompletenessError("source review queue row lacks stable_source_id")
        if stable in queue_by_id:
            raise CompletenessError(f"duplicate review queue stable source ID {stable}")
        queue_by_id[stable] = row

    queue_id_set = set(queue_by_id)
    execution_id_set = set(execution_core)
    queue_inventory_complete = (
        len(queue_by_id) == core
        and queue_id_set == execution_id_set
        and queue.get("retained_core_records") == core
    )
    if not queue_inventory_complete:
        missing = sorted(execution_id_set - queue_id_set)[:20]
        extra = sorted(queue_id_set - execution_id_set)[:20]
        raise CompletenessError(
            f"source review queue does not exactly cover retained core; missing={missing}, extra={extra}"
        )

    expected_semantic_counts: Counter[str] = Counter()
    semantic_mismatches: list[str] = []
    hash_mismatches: list[str] = []
    for stable, source in execution_core.items():
        queue_row = queue_by_id[stable]
        source_hash = source.get("hash")
        if queue_row.get("census_hash") != source_hash:
            hash_mismatches.append(stable)
        expected_status = source.get("coverage")
        normalized = _normalized_source_id(str(source.get("id", stable)))
        if expected_status == "UNKNOWN" and normalized in mapped_ids:
            expected_status = "SOURCE_MAPPED"
        expected_semantic_counts[str(expected_status)] += 1
        if queue_row.get("semantic_status") != expected_status:
            semantic_mismatches.append(stable)
    if hash_mismatches:
        raise CompletenessError(f"review queue census hashes drifted for {len(hash_mismatches)} records")
    if semantic_mismatches:
        raise CompletenessError(
            f"review queue semantic status drifted for {len(semantic_mismatches)} records"
        )
    if expected_semantic_counts.get("UNKNOWN", 0) != current_unknown:
        raise CompletenessError("queue UNKNOWN count disagrees with semantic overlay")

    body_target = body.get("retained_core_target")
    if body_target != core:
        raise CompletenessError("body review target must equal retained core census")

    body_status_counts = Counter(str(row.get("body_review_status")) for row in queue_records)
    body_reviewed = sum(body_status_counts.get(status, 0) for status in BODY_COMPLETE_STATUSES)
    body_unread = core - body_reviewed
    body_review_complete = (
        body.get("tracking_status") == "COMPLETE"
        and body.get("reviewed_retained_core") == core
        and body.get("unread_retained_core") == 0
        and body.get("hashed_body_receipts") == core
        and body_reviewed == core
        and body_unread == 0
    )

    disposition_counts: Counter[str] = Counter()
    undispositioned_records: list[str] = []
    unowned_economic_inputs: list[str] = []
    bad_driver_owners: list[str] = []
    for stable, row in queue_by_id.items():
        disposition = row.get("review_disposition")
        if disposition is None:
            undispositioned_records.append(stable)
            continue
        if disposition not in ALLOWED_REVIEW_DISPOSITIONS:
            raise CompletenessError(f"invalid source review disposition {disposition!r}")
        disposition_counts[disposition] += 1
        owners = row.get("driver_owners", [])
        if not isinstance(owners, list) or not all(isinstance(x, str) for x in owners):
            raise CompletenessError("driver_owners must be a string list")
        if any(owner not in EXPECTED_DRIVER_REGISTRY for owner in owners):
            bad_driver_owners.append(stable)
        if disposition == "ECONOMIC_INPUT" and not owners:
            unowned_economic_inputs.append(stable)
    if bad_driver_owners:
        raise CompletenessError(f"source review queue has invalid driver owners on {len(bad_driver_owners)} rows")
    review_disposition_complete = not undispositioned_records and not unowned_economic_inputs

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

    semantic_status_complete = current_unknown == 0
    coverage_claim_allowed = (
        acquisition_complete
        and queue_inventory_complete
        and semantic_status_complete
        and body_review_complete
        and review_disposition_complete
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
        "schema": "tnp.economy.completeness-report/2",
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
            "source_review_queue_inventory": {
                "pass": queue_inventory_complete,
                "records": len(queue_records),
                "matches_full_execution_census": queue_id_set == execution_id_set,
                "census_hash_mismatches": len(hash_mismatches),
                "semantic_status_mismatches": len(semantic_mismatches),
            },
            "source_record_semantic_status": {
                "pass": semantic_status_complete,
                "retained_core_records": core,
                "non_unknown": semantic_non_unknown,
                "unknown": current_unknown,
                "new_source_mapped_ids": len(mapped_ids),
                "status_counts": dict(sorted(expected_semantic_counts.items())),
                "rule": "UNKNOWN must reach zero; acquisition alone is not review.",
            },
            "source_body_review": {
                "pass": body_review_complete,
                "tracking_status": body.get("tracking_status"),
                "retained_core_target": body_target,
                "reviewed_retained_core": body_reviewed,
                "unread_retained_core": body_unread,
                "body_status_counts": dict(sorted(body_status_counts.items())),
                "historical_checkpoint": body.get("historical_checkpoint"),
                "rule": "Every retained source record needs a body-read receipt or explicit no-body/not-applicable disposition.",
            },
            "source_review_dispositions": {
                "pass": review_disposition_complete,
                "dispositioned": core - len(undispositioned_records),
                "undispositioned": len(undispositioned_records),
                "unowned_economic_inputs": len(unowned_economic_inputs),
                "disposition_counts": dict(sorted(disposition_counts.items())),
                "rule": "Every retained record receives one explicit review disposition; ECONOMIC_INPUT additionally requires one or more driver owners.",
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
                "the finite 1,620-record review queue exactly matches the full execution census",
                "retained-core UNKNOWN semantic status reaches zero",
                "every retained source body has a read receipt or explicit no-body/not-applicable status",
                "every retained source record has an explicit review disposition",
                "every ECONOMIC_INPUT disposition names one or more driver owners",
                "the finite driver registry is intact and every driver has an explicit disposition",
            ],
            "canonical_ready_additionally_requires": [
                "all drivers complete and executable",
                "zero unresolved Empire Close blockers",
                "zero unresolved Empire Close conflicts",
            ],
        },
        "next_required_work": [
            "read the fixed source-review queue instead of starting another unbounded sweep",
            "attach privacy-preserving body revision/hash evidence and a review disposition to each row",
            "route ECONOMIC_INPUT rows to one or more driver owners",
            "keep unresolved values explicit; do not invent balancing numbers",
        ],
    }
