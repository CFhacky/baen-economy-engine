"""Source-bound agriculture and aquaculture baseline.

This module does not simulate a month.  It verifies the complete read-only
Registry property export, the complete read-only Registry page-body snapshot,
and a narrowly reviewed extraction manifest.  Missing physical values remain
None and block execution.
"""

from __future__ import annotations

from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Mapping

from .domain import canonical_decimal
from .operator_codec import canonical_hash
from .registry_export import load_registry_export


FOOD_BASELINE_SCHEMA = "tnp.economy.food-source-baseline/1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY_PATH = (
    PROJECT_ROOT
    / "fixtures"
    / "registry-snapshots"
    / "business-registry-2026-08-29.json"
)
DEFAULT_PAGE_SNAPSHOT_PATH = (
    PROJECT_ROOT
    / "fixtures"
    / "source-snapshots"
    / "business-registry-page-bodies-2026-08-29.json"
)
DEFAULT_EXTRACTION_PATH = (
    PROJECT_ROOT
    / "fixtures"
    / "source-snapshots"
    / "food-economy-extraction-v1.json"
)
DEFAULT_LADEN_PATH = (
    PROJECT_ROOT
    / "fixtures"
    / "canonical-import"
    / "operation-laden-table.json"
)

EXPECTED_COMMERCIAL_TOTALS = {
    "entity_count": 5,
    "employees": 63,
    "monthly_revenue_gp": Decimal("26500"),
    "monthly_cost_gp": Decimal("20550"),
    "monthly_net_gp": Decimal("5950"),
    "capital_invested_gp": Decimal("111000"),
}

PHYSICAL_FIELDS = (
    "site_topology",
    "opening_inventory",
    "monthly_output_quantities",
    "production_inputs",
    "feed_composition",
    "feed_quantity",
    "spoilage_and_mortality",
    "routes_and_capacities",
    "prices",
    "customer_demand",
)


class FoodBaselineError(ValueError):
    """Raised when source coverage drifts or an unknown is made executable."""


def _exact_keys(
    value: Mapping[str, object], expected: set[str], label: str
) -> None:
    if set(value) != expected:
        raise FoodBaselineError(
            f"{label} keys do not match the reviewed source-extraction schema"
        )


def _load_json(path: Path, label: str) -> object:
    if not isinstance(path, Path):
        raise FoodBaselineError(f"{label} path must be a concrete Path")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FoodBaselineError(f"cannot read {label}: {exc}") from exc


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise FoodBaselineError(f"{label} must be an object")
    return value


def _array(value: object, label: str) -> tuple[object, ...]:
    if not isinstance(value, list):
        raise FoodBaselineError(f"{label} must be an array")
    return tuple(value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FoodBaselineError(f"{label} must be non-empty text")
    return value


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError as exc:
        raise FoodBaselineError(f"cannot hash source snapshot: {exc}") from exc


def _decimal_or_none(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise FoodBaselineError("source finance must use exact decimal text")
    result = Decimal(str(value))
    if not result.is_finite():
        raise FoodBaselineError("source finance must be finite")
    return result


def _integer_or_none(value: object) -> int | None:
    amount = _decimal_or_none(value)
    if amount is None:
        return None
    integral = int(amount)
    if Decimal(integral) != amount or integral < 0:
        raise FoodBaselineError("source employees must be a non-negative integer")
    return integral


def _number(value: Decimal | None) -> str | None:
    return None if value is None else canonical_decimal(value)


def _page_index(snapshot: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    pages = _array(snapshot.get("pages"), "page snapshot pages")
    result: dict[str, Mapping[str, object]] = {}
    for index, raw in enumerate(pages, start=1):
        page = _mapping(raw, f"page snapshot item {index}")
        source_id = _text(page.get("source_record_id"), "page source record ID")
        if source_id in result:
            raise FoodBaselineError("page snapshot repeats a source record")
        if not isinstance(page.get("source_text"), str) or not page["source_text"]:
            raise FoodBaselineError(f"page snapshot body is empty: {source_id}")
        result[source_id] = page
    return result


def load_food_source_baseline(
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    page_snapshot_path: Path = DEFAULT_PAGE_SNAPSHOT_PATH,
    extraction_path: Path = DEFAULT_EXTRACTION_PATH,
    laden_path: Path = DEFAULT_LADEN_PATH,
) -> dict[str, object]:
    """Verify and return the current source-truth food baseline."""

    registry = load_registry_export(registry_path)
    page_snapshot = _mapping(
        _load_json(page_snapshot_path, "Registry page-body snapshot"),
        "Registry page-body snapshot",
    )
    extraction = _mapping(
        _load_json(extraction_path, "food extraction"),
        "food extraction",
    )
    laden = _mapping(_load_json(laden_path, "Operation Laden Table"), "Laden Table")

    if page_snapshot.get("schema") != "tnp.registry.page-body-snapshot/1":
        raise FoodBaselineError("Registry page-body snapshot schema is unsupported")
    if extraction.get("schema") != "tnp.economy.food-source-extraction/1":
        raise FoodBaselineError("food extraction schema is unsupported")
    _exact_keys(
        extraction,
        {
            "schema",
            "authority",
            "registry_export_content_hash",
            "page_body_snapshot_sha256",
            "notion_writes",
            "warning",
            "entities",
        },
        "food extraction",
    )
    if page_snapshot.get("notion_writes") != 0 or extraction.get("notion_writes") != 0:
        raise FoodBaselineError("source inputs must record zero Notion writes")
    if page_snapshot.get("registry_export_content_hash") != registry.content_hash:
        raise FoodBaselineError("page bodies are not bound to this Registry export")
    if extraction.get("registry_export_content_hash") != registry.content_hash:
        raise FoodBaselineError("food extraction is not bound to this Registry export")
    expected_page_sha = _text(
        extraction.get("page_body_snapshot_sha256"),
        "expected page-body snapshot hash",
    )
    if _sha256_file(page_snapshot_path) != expected_page_sha:
        raise FoodBaselineError("Registry page-body snapshot hash has drifted")

    page_by_source = _page_index(page_snapshot)
    registry_ids = set(registry.rows_by_source_id)
    if (
        page_snapshot.get("row_count") != 90
        or page_snapshot.get("page_body_count") != 90
        or len(page_by_source) != 90
        or set(page_by_source) != registry_ids
    ):
        raise FoodBaselineError("Registry page-body coverage is not exactly 90 of 90")

    food_ids = {
        source_id
        for source_id, row in registry.rows_by_source_id.items()
        if row.get("Sector") in {"Agriculture", "Aquaculture"}
    }
    extraction_rows = _array(extraction.get("entities"), "food extraction entities")
    if len(extraction_rows) != 7:
        raise FoodBaselineError("food extraction must contain all seven food rows")

    entities: list[dict[str, object]] = []
    extracted_ids: set[str] = set()
    commercial: list[dict[str, object]] = []
    for index, raw in enumerate(extraction_rows, start=1):
        spec = _mapping(raw, f"food extraction item {index}")
        _exact_keys(
            spec,
            {
                "source_record_id",
                "row_hash",
                "page_body_sha256",
                "classification",
                "financial_inclusion",
                "known_outputs",
                "required_evidence",
                "source_claims",
                "gm_only_claims",
                "physical_unknowns",
            },
            f"food extraction item {index}",
        )
        source_id = _text(spec.get("source_record_id"), "food source record ID")
        if source_id in extracted_ids:
            raise FoodBaselineError("food extraction repeats a source record")
        extracted_ids.add(source_id)
        if source_id not in registry.rows_by_source_id:
            raise FoodBaselineError(f"food source is absent from Registry: {source_id}")
        row = registry.rows_by_source_id[source_id]
        page = page_by_source[source_id]
        if registry.row_hashes[source_id] != spec.get("row_hash"):
            raise FoodBaselineError(f"food Registry row hash has drifted: {row['Entity']}")
        page_text = str(page["source_text"])
        if _sha256_bytes(page_text.encode("utf-8")) != spec.get("page_body_sha256"):
            raise FoodBaselineError(f"food page body has drifted: {row['Entity']}")
        for evidence in _array(spec.get("required_evidence"), "required evidence"):
            token = _text(evidence, "required evidence token")
            if token not in page_text:
                raise FoodBaselineError(
                    f"required source evidence is absent for {row['Entity']}: {token}"
                )

        revenue = _decimal_or_none(row.get("Monthly Revenue"))
        cost = _decimal_or_none(row.get("Monthly Cost"))
        capital = _decimal_or_none(row.get("Capital Invested"))
        employees = _integer_or_none(row.get("Employees"))
        net = None if revenue is None or cost is None else revenue - cost
        entity = {
            "source_record_id": source_id,
            "source_url": str(row["url"]),
            "row_hash": registry.row_hashes[source_id],
            "page_body_sha256": str(spec["page_body_sha256"]),
            "name": str(row["Entity"]),
            "sector": str(row["Sector"]),
            "city": row.get("City"),
            "status": row.get("Status"),
            "leadership": row.get("Leadership"),
            "neglect_status": row.get("Neglect Status"),
            "last_updated": row.get("Last Updated"),
            "date_operational": row.get("Date Operational"),
            "classification": str(spec["classification"]),
            "financial_inclusion": str(spec["financial_inclusion"]),
            "reported_finance": {
                "employees": employees,
                "monthly_revenue_gp": _number(revenue),
                "monthly_cost_gp": _number(cost),
                "monthly_net_gp": _number(net),
                "capital_invested_gp": _number(capital),
                "opening_cash_gp": None,
            },
            "known_outputs": list(_array(spec.get("known_outputs"), "known outputs")),
            "source_claims": list(_array(spec.get("source_claims"), "source claims")),
            "gm_only_claims": list(
                _array(spec.get("gm_only_claims"), "GM-only claims")
            ),
            "physical_state": {field: None for field in PHYSICAL_FIELDS},
            "physical_unknowns": list(
                _array(spec.get("physical_unknowns"), "physical unknowns")
            ),
            "mechanically_executable": False,
        }
        entities.append(entity)
        if entity["financial_inclusion"] == "last_known_pre_crisis_baseline":
            if (
                row.get("Status") != "Operational"
                or row.get("Last Updated") != "Eleint 20, 1494"
                or None in (revenue, cost, capital, employees)
            ):
                raise FoodBaselineError(
                    f"commercial baseline source status has drifted: {row['Entity']}"
                )
            commercial.append(entity)

    if extracted_ids != food_ids:
        missing = sorted(food_ids - extracted_ids)
        extra = sorted(extracted_ids - food_ids)
        raise FoodBaselineError(
            f"food extraction does not match all Registry food rows; "
            f"missing={missing}, extra={extra}"
        )

    totals = {
        "entity_count": len(commercial),
        "employees": sum(
            int(item["reported_finance"]["employees"]) for item in commercial
        ),
        "monthly_revenue_gp": sum(
            Decimal(str(item["reported_finance"]["monthly_revenue_gp"]))
            for item in commercial
        ),
        "monthly_cost_gp": sum(
            Decimal(str(item["reported_finance"]["monthly_cost_gp"]))
            for item in commercial
        ),
        "capital_invested_gp": sum(
            Decimal(str(item["reported_finance"]["capital_invested_gp"]))
            for item in commercial
        ),
    }
    totals["monthly_net_gp"] = (
        totals["monthly_revenue_gp"] - totals["monthly_cost_gp"]
    )
    if totals != EXPECTED_COMMERCIAL_TOTALS:
        raise FoodBaselineError(
            "commercial food baseline changed and requires source review"
        )

    trigger = _mapping(laden.get("trigger"), "Laden Table trigger")
    resolved_rolls = _array(
        laden.get("resolved_execution_rolls"), "Laden resolved execution rolls"
    )
    transactions = _array(
        laden.get("resolved_or_source_recorded_transactions"),
        "Laden resolved transactions",
    )
    if resolved_rolls or transactions:
        raise FoodBaselineError(
            "Laden Table now contains resolved activity and requires a new review"
        )
    if (
        trigger.get("agricultural_shelter_zones_destroyed") != 3
        or trigger.get("agricultural_shelter_zones_total") != 8
        or laden.get("local_food_position") != "net_importer"
        or laden.get("population_mouths") != 11000
    ):
        raise FoodBaselineError("Kythorn food-crisis source facts have drifted")

    baseline = {
        "schema": FOOD_BASELINE_SCHEMA,
        "mode": "source_truth_read_only",
        "simulation_ready": False,
        "observed_baseline_ready": True,
        "baseline_status": "last_known_eleint_1494_pre_crisis_operating_envelope",
        "warning": (
            "This is a verified source baseline, not a simulated month. "
            "Physical quantities remain UNKNOWN rather than zero."
        ),
        "coverage": {
            "registry_property_rows": 90,
            "registry_property_rows_total": 90,
            "registry_page_bodies": 90,
            "registry_page_bodies_total": 90,
            "food_rows": 7,
            "food_rows_total": 7,
            "commercial_baseline_rows": 5,
            "mechanically_executed_rows": 0,
        },
        "commercial_food_baseline": {
            "as_of": "Eleint 20, 1494",
            "status": "last_known_pre_crisis_baseline_not_current_k1495_books",
            "entity_count": totals["entity_count"],
            "employees": totals["employees"],
            "monthly_revenue_gp": canonical_decimal(totals["monthly_revenue_gp"]),
            "monthly_cost_gp": canonical_decimal(totals["monthly_cost_gp"]),
            "monthly_net_gp": canonical_decimal(totals["monthly_net_gp"]),
            "capital_invested_gp": canonical_decimal(
                totals["capital_invested_gp"]
            ),
            "opening_cash_gp": None,
        },
        "entities": sorted(entities, key=lambda item: str(item["name"])),
        "later_k1495_crisis_context": {
            "timeline_id": laden.get("timeline_id"),
            "planning_date": laden.get("planning_date"),
            "shelter_zones_destroyed": 3,
            "shelter_zones_total": 8,
            "remaining_not_reported_destroyed": 5,
            "remaining_operational_inference_allowed": False,
            "topology_conflict": (
                "The source does not establish whether the eight Dawnwood-margin "
                "zones are the whole Multi-Region Registry entity or one subset."
            ),
            "longsaddle_population_mouths": 11000,
            "longsaddle_food_position": "net_importer",
            "first_harvest_window": laden.get("first_harvest_window"),
            "first_meaningful_export_surplus": laden.get(
                "first_meaningful_export_surplus"
            ),
            "grain_procurement_target_tons": laden.get("grain_target_tons"),
            "grain_target_is_plan_not_inventory": True,
            "resolved_execution_roll_count": 0,
            "resolved_transaction_count": 0,
        },
        "execution_blockers": [
            "opening state for the live Day 7 Hammer 1495 branch",
            "whether the eight Dawnwood zones are the whole shelter network or a subset",
            "zone and site identities, locations, and condition",
            "site-by-site crop assignment, acreage, yield, and harvest calendar",
            "opening physical inventories",
            "aquaculture species allocation, feed supply, cohorts, and volume by site",
            "storage, spoilage, mortality, and processing conversions",
            "local consumption and customer demand",
            "allocated routes, travel schedules, handling loss, and title-transfer terms",
            "physical prices and inventory cost basis",
            "financial reconciliation between physical flows and Registry benchmarks",
        ],
        "rejected_synthetic_substitutions": [
            "generic feed-and-food grain assigned to the shelter zones",
            "invented opening grain, fish, brick, clay, and cash balances",
            "invented crop and fish recipes",
            "invented worker-days and wages",
            "invented spoilage, routes, capacities, loss, demand, and prices",
            "invented deposits, loans, repayment fractions, and trade tax",
        ],
        "safety": {
            "notion_write_capability": False,
            "notion_writes": 0,
            "canonical_ledger_post_capability": False,
            "canonical_ledger_postings": 0,
            "dice_rolled": 0,
            "campaign_time_advanced": False,
        },
        "provenance": {
            "registry_export_content_hash": registry.content_hash,
            "registry_snapshot_hash": registry.snapshot_hash,
            "registry_export_hash": registry.export_hash,
            "page_body_snapshot_sha256": expected_page_sha,
            "food_extraction_hash": canonical_hash(extraction),
            "laden_source_refs": list(_array(laden.get("source_refs"), "Laden sources")),
        },
    }
    baseline["baseline_hash"] = canonical_hash(baseline)
    return baseline
