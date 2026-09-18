"""Source-backed physical production and optional product mapping.

The actual Hammer-1495 path may report industrial quantities that already exist
in campaign authority, and may invoke an upstream product only when that
product's required inputs are source-backed. Products are never substitute
data sources. Unknown conversion ratios, inventories, prices, and route
capacities stay unknown.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from .mesa_runtime import MesaProductEvent, MesaRuntimeUnavailable, mesa_available, run_mesa_preview
from .domain import canonical_decimal
from .openttd_product import OPENTTD_COMMIT


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_INPUTS = (
    PROJECT_ROOT / "recovery/ECONOMY_SOURCE_INPUT_AUTHORITY_2026-09-17.json"
)
DEFAULT_SEMANTIC_EVIDENCE = (
    PROJECT_ROOT / "recovery/SOURCE_SEMANTIC_EVIDENCE_2026-09-18.json"
)
DEFAULT_CENSUS_SNAPSHOT = (
    PROJECT_ROOT / "recovery/LIVE_EMPIRE_SOURCE_CENSUS_EXECUTION_SNAPSHOT_2026-09-17.json"
)


class EmpireSourceProductError(ValueError):
    """Source-backed physical mapping cannot be resolved safely."""


@dataclass(frozen=True, slots=True)
class ProductionLineSpec:
    id: str
    entity: str
    sector: str
    quantity_key: str
    unit: str
    employees_key: str
    unresolved_inputs: tuple[str, ...]
    maximum_key: str | None = None


PRODUCTION_LINE_SPECS: tuple[ProductionLineSpec, ...] = (
    ProductionLineSpec(
        id="treasury_quarries",
        entity="Treasury Stone Quarries",
        sector="Mining/Quarrying",
        quantity_key="treasury_quarries.monthly_output_tons",
        unit="tons stone/month",
        employees_key="treasury_quarries.employees",
        unresolved_inputs=("opening finished-stone inventories are not source-backed",),
    ),
    ProductionLineSpec(
        id="azurite_quarries",
        entity="Azurite Decorative Quarries",
        sector="Mining/Quarrying",
        quantity_key="azurite_quarries.monthly_output_tons",
        unit="tons azurite/month",
        employees_key="azurite_quarries.employees",
        unresolved_inputs=("opening azurite inventories are not source-backed",),
    ),
    ProductionLineSpec(
        id="western_limestone",
        entity="Western Limestone Quarries",
        sector="Mining/Quarrying",
        quantity_key="western_limestone.monthly_output_tons",
        unit="tons limestone/month",
        employees_key="western_limestone.employees",
        unresolved_inputs=("opening limestone inventories are not source-backed",),
    ),
    ProductionLineSpec(
        id="western_sandstone",
        entity="Western Sandstone Quarries",
        sector="Mining/Quarrying",
        quantity_key="western_sandstone.monthly_output_tons",
        unit="tons sandstone/month",
        employees_key="western_sandstone.employees",
        unresolved_inputs=("opening sandstone inventories are not source-backed",),
    ),
    ProductionLineSpec(
        id="brickworks",
        entity="Baen Brickworks",
        sector="Manufacturing",
        quantity_key="brickworks.monthly_output_bricks",
        unit="bricks/month",
        employees_key="brickworks.employees",
        unresolved_inputs=(
            "clay-to-brick conversion coefficient is not source-backed",
            "opening brick and clay inventories are not source-backed",
        ),
    ),
    ProductionLineSpec(
        id="clay_quarries",
        entity="Neverwinter Clay Quarries",
        sector="Mining/Quarrying",
        quantity_key="clay_quarries.monthly_output_tons",
        unit="tons clay/month",
        employees_key="clay_quarries.employees",
        unresolved_inputs=("opening clay inventories are not source-backed",),
    ),
    ProductionLineSpec(
        id="silversheen_aluminum",
        entity="Silversheen Trading (Aluminum)",
        sector="Manufacturing",
        quantity_key="silversheen.current_output_aluminum_tons_per_month",
        unit="tons aluminum/month",
        employees_key="silversheen.employees_forgedeep_processing",
        unresolved_inputs=(
            "Hammer-1495 monthly cost after the 180 t/mo ruling is not restated",
            "bauxite-to-aluminum conversion coefficient is not source-backed",
            "Warborn aluminum allocation is conflicted: 30 t/mo quantity vs 20% of current output",
        ),
    ),
    ProductionLineSpec(
        id="star_metal_hills_bauxite",
        entity="Star Metal Hills",
        sector="Mining/Quarrying",
        quantity_key="star_metal_hills.bauxite_output_tons_per_month",
        unit="tons bauxite/month",
        employees_key="star_metal_hills.employees",
        unresolved_inputs=("opening bauxite inventories are not source-backed",),
    ),
    ProductionLineSpec(
        id="warborn_neverwinter",
        entity="Warborn Production - Neverwinter",
        sector="Manufacturing",
        quantity_key="warborn_neverwinter.legionnaire_output_units_per_month",
        unit="Legionnaire units/month",
        employees_key="warborn_neverwinter.employees",
        maximum_key="warborn_neverwinter.maximum_legionnaire_capacity_units_per_month",
        unresolved_inputs=(
            "Hell-iron and other BOM figures are approximate and are not used as exact recipes",
            "the stated 3-month material buffer is qualitative, not a warehouse count",
        ),
    ),
)

DORMANT_PRODUCTS: tuple[dict[str, str], ...] = (
    {
        "product": "OpenTTD",
        "status": "MAPPED_BLOCKED",
        "reason": (
            "Warborn precision-steel freight is source-mapped to OpenTTD steel semantics, "
            "but no authoritative source/user rule maps campaign miles to OpenTTD tiles or "
            "fractional source tons to OpenTTD integer cargo pieces"
        ),
    },
    {
        "product": "Veloren",
        "status": "NOT_INVOKED",
        "reason": "settlement opening stocks and general commodity prices are not source-backed",
    },
    {
        "product": "Brunnfeld Agentic World",
        "status": "NOT_INVOKED",
        "reason": "agent/market prices and demand quantities are not source-backed",
    },
)

ALLOCATION_CONFLICT = (
    "Silversheen Warborn aluminum allocation: 30 t/mo quantity vs 20% of current "
    "output; they agreed at Eleint 1494 150 t/mo and conflict after the Hammer-1495 "
    "180 t/mo ruling"
)

CENSUS_SPECS: tuple[dict[str, str], ...] = (
    {
        "id": "neverwinter",
        "settlement": "Neverwinter",
        "population_key": "neverwinter.current_population",
        "role": "Arik-side headquarters city",
    },
    {
        "id": "waterdeep",
        "settlement": "Waterdeep",
        "population_key": "waterdeep.current_population",
        "role": "allied trading-partner city",
    },
)

FOOD_ENTITY_SPECS: tuple[dict[str, str], ...] = (
    {
        "id": "agricultural_shelters",
        "entity": "Agricultural Shelter Zones",
        "kind": "entity",
        "employees_key": "agricultural_shelters.employees",
        "revenue_key": "agricultural_shelters.monthly_revenue_gp",
        "cost_key": "agricultural_shelters.monthly_cost_gp",
        "physical_blocker": "agricultural_shelters.physical_output_volume",
    },
    {
        "id": "blacklake_aquaculture",
        "entity": "Blacklake Aquaculture (7 pools)",
        "kind": "entity",
        "employees_key": "blacklake_aquaculture.employees",
        "revenue_key": "blacklake_aquaculture.monthly_revenue_gp",
        "cost_key": "blacklake_aquaculture.monthly_cost_gp",
        "physical_blocker": "blacklake_aquaculture.physical_output_volume",
    },
)

FOOD_AGGREGATE_SPECS: tuple[dict[str, str], ...] = (
    {
        "id": "aquaculture_network",
        "entity": "Aquaculture network (Blacklake + Converted Quarry + BG pools + Reservoir Fisheries)",
        "kind": "aggregate",
        "employees_key": "food_sector.aquaculture_employees",
        "revenue_key": "food_sector.aquaculture_monthly_revenue_gp",
        "note": "Includes the Blacklake entity. Do not add Blacklake on top of this total.",
    },
    {
        "id": "combined_food_financials",
        "entity": "Combined food financials (aquaculture network + Agricultural Shelter Zones)",
        "kind": "aggregate",
        "employees_key": "food_sector.combined_employees",
        "revenue_key": "food_sector.combined_revenue_gp_per_month",
        "note": "Financial layer only. Do not derive physical crop or fish volume from these gp figures.",
    },
)

ARTERIAL_ROUTE_SPECS: tuple[tuple[str, str, str], ...] = (
    (
        "forgedeep_guardians_gate",
        "Forgedeep → Guardian's Gate",
        "arterial.route.forgedeep_guardians_gate.distance_miles",
    ),
    (
        "neverwinter_gauntlgrym",
        "Neverwinter → Gauntlgrym",
        "arterial.route.neverwinter_gauntlgrym.distance_miles",
    ),
    (
        "neverwinter_luskan",
        "Neverwinter → Luskan",
        "arterial.route.neverwinter_luskan.distance_miles",
    ),
    (
        "neverwinter_mirabar",
        "Neverwinter → Mirabar",
        "arterial.route.neverwinter_mirabar.distance_miles",
    ),
    (
        "neverwinter_waterdeep",
        "Neverwinter → Waterdeep",
        "arterial.route.neverwinter_waterdeep.distance_miles",
    ),
)


def _product_number(value: object) -> int | str:
    """Convert upstream numeric output to durable exact operator-safe form."""

    if type(value) is bool:
        raise EmpireSourceProductError("upstream product returned boolean numeric output")
    if type(value) is int:
        return value
    if isinstance(value, float):
        decimal = Decimal(str(value))
        if not decimal.is_finite():
            raise EmpireSourceProductError("upstream product returned non-finite numeric output")
        if decimal == decimal.to_integral_value():
            return int(decimal)
        return canonical_decimal(decimal)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise EmpireSourceProductError("upstream product returned non-finite Decimal")
        if value == value.to_integral_value():
            return int(value)
        return canonical_decimal(value)
    raise EmpireSourceProductError(
        f"unsupported upstream numeric output: {type(value).__name__}"
    )


def _load_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EmpireSourceProductError(f"cannot read source-input authority: {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != "tnp.economy.source-input-authority/1":
        raise EmpireSourceProductError("source-input authority schema is unsupported")
    if payload.get("rule") is None:
        raise EmpireSourceProductError("source-input authority lacks the actual-run rule")
    return payload


def _index_facts(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    facts = payload.get("facts")
    if not isinstance(facts, list):
        raise EmpireSourceProductError("source-input authority has no facts array")
    indexed: dict[str, dict[str, Any]] = {}
    for row in facts:
        if not isinstance(row, dict) or not isinstance(row.get("key"), str):
            raise EmpireSourceProductError("source-input fact is malformed")
        if row.get("authority") not in {"SOURCE-DERIVED", "USER-RULED", "UPSTREAM-ADOPTED"}:
            raise EmpireSourceProductError(f"fact {row['key']} is not admissible for actual execution")
        if row["key"] in indexed:
            raise EmpireSourceProductError(f"duplicate source-input fact: {row['key']}")
        indexed[row["key"]] = row
    return indexed


def _index_blockers(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    blockers = payload.get("blockers")
    if not isinstance(blockers, list):
        raise EmpireSourceProductError("source-input authority has no blockers array")
    indexed: dict[str, dict[str, Any]] = {}
    for row in blockers:
        if not isinstance(row, dict) or not isinstance(row.get("key"), str):
            raise EmpireSourceProductError("source-input blocker is malformed")
        if row["key"] in indexed:
            raise EmpireSourceProductError(f"duplicate source-input blocker: {row['key']}")
        indexed[row["key"]] = row
    return indexed


def _load_facts(path: Path) -> dict[str, dict[str, Any]]:
    return _index_facts(_load_payload(path))


def _exact_number(row: Mapping[str, Any], label: str) -> int | float:
    if "value" not in row:
        raise EmpireSourceProductError(f"{label} has no value")
    value = row["value"]
    if type(value) is bool or type(value) not in {int, float}:
        raise EmpireSourceProductError(f"{label} is not a numeric source value")
    if isinstance(value, float) and value != int(value):
        return value
    return int(value)


def source_production_lines(
    source_path: Path = DEFAULT_SOURCE_INPUTS,
) -> list[dict[str, Any]]:
    facts = _load_facts(source_path)
    lines: list[dict[str, Any]] = []
    for spec in PRODUCTION_LINE_SPECS:
        quantity_row = facts.get(spec.quantity_key)
        employees_row = facts.get(spec.employees_key)
        if quantity_row is None or employees_row is None:
            raise EmpireSourceProductError(f"missing source fact for {spec.id}")
        source = quantity_row.get("source")
        if not isinstance(source, dict) or not source.get("notion_page"):
            raise EmpireSourceProductError(f"{spec.id} quantity lacks Notion provenance")
        line: dict[str, Any] = {
            "id": spec.id,
            "entity": spec.entity,
            "sector": spec.sector,
            "quantity": _exact_number(quantity_row, spec.quantity_key),
            "unit": spec.unit,
            "employees": _exact_number(employees_row, spec.employees_key),
            "authority": quantity_row["authority"],
            "source": {
                "notion_page": source["notion_page"],
                "title": source.get("title"),
                "fact_key": spec.quantity_key,
            },
            "unresolved_inputs": list(spec.unresolved_inputs),
            "recipe_invented": False,
        }
        if spec.maximum_key:
            maximum_row = facts.get(spec.maximum_key)
            if maximum_row is None:
                raise EmpireSourceProductError(f"missing source fact for {spec.maximum_key}")
            line["maximum"] = _exact_number(maximum_row, spec.maximum_key)
            line["maximum_fact_key"] = spec.maximum_key
        lines.append(line)
    return lines


def _source_ref(row: Mapping[str, Any], fact_key: str) -> dict[str, Any]:
    source = row.get("source")
    if not isinstance(source, dict) or not source.get("notion_page"):
        raise EmpireSourceProductError(f"{fact_key} lacks Notion provenance")
    return {
        "notion_page": source["notion_page"],
        "title": source.get("title"),
        "fact_key": fact_key,
    }


def _load_semantic_evidence(path: Path = DEFAULT_SEMANTIC_EVIDENCE) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EmpireSourceProductError(f"cannot read semantic evidence: {path}: {exc}") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != "tnp.economy.source-semantic-evidence/1"
    ):
        raise EmpireSourceProductError("source semantic evidence schema is unsupported")
    if payload.get("campaign_boundary") != "Day 7 Hammer 1495 DR":
        raise EmpireSourceProductError("source semantic evidence campaign boundary drifted")
    if payload.get("notion_writes") != 0:
        raise EmpireSourceProductError("source semantic evidence records an unexpected Notion write")
    return payload


def _fact_snapshot(
    facts: Mapping[str, Mapping[str, Any]],
    key: str,
    *,
    value_field: str = "value",
    unit: str | None = None,
) -> dict[str, Any]:
    row = facts.get(key)
    if row is None:
        raise EmpireSourceProductError(f"missing semantic source fact {key}")
    if value_field not in row:
        raise EmpireSourceProductError(f"{key} lacks {value_field}")
    item: dict[str, Any] = {
        "key": key,
        "value": row[value_field],
        "authority": row["authority"],
        "source": _source_ref(row, key),
    }
    resolved_unit = unit or row.get("unit")
    if resolved_unit:
        item["unit"] = str(resolved_unit)
    if row.get("approximate") is not None:
        item["approximate"] = bool(row.get("approximate"))
    if row.get("note"):
        item["note"] = str(row.get("note"))
    return item


def _blocker_snapshot(
    blockers: Mapping[str, Mapping[str, Any]],
    key: str,
) -> dict[str, Any]:
    row = blockers.get(key)
    if row is None:
        raise EmpireSourceProductError(f"missing semantic blocker {key}")
    source = row.get("source")
    return {
        "key": key,
        "status": str(row.get("status") or "UNRESOLVED"),
        "reason": str(row.get("reason") or "source state is unresolved"),
        "authority": "UNRESOLVED",
        "source": dict(source) if isinstance(source, Mapping) else None,
    }


def _semantic_mapping(evidence: Mapping[str, Any], mapping_id: str) -> dict[str, Any]:
    mappings = evidence.get("mappings")
    if not isinstance(mappings, list):
        raise EmpireSourceProductError("source semantic evidence has no mappings array")
    matches = [
        row
        for row in mappings
        if isinstance(row, dict) and row.get("id") == mapping_id
    ]
    if len(matches) != 1:
        raise EmpireSourceProductError(
            f"semantic mapping {mapping_id} must exist exactly once"
        )
    return dict(matches[0])


def source_semantic_domains(
    source_path: Path = DEFAULT_SOURCE_INPUTS,
    semantic_evidence_path: Path = DEFAULT_SEMANTIC_EVIDENCE,
) -> dict[str, Any]:
    """Project recovered source evidence into economic driver domains.

    This is a semantic mapping layer, not a claim that every mapped fact is
    executable. Known observations and unresolved state remain separate, and
    MODEL-PROPOSED values are never inserted to make a domain complete.
    """

    payload = _load_payload(source_path)
    facts = _index_facts(payload)
    blockers = _index_blockers(payload)
    evidence = _load_semantic_evidence(semantic_evidence_path)
    freight = _semantic_mapping(evidence, "warborn_gauntlgrym_precision_steel_flow")
    contract = _semantic_mapping(evidence, "warborn_zariel_priority_contract")

    conflicts = evidence.get("conflicts")
    if not isinstance(conflicts, list):
        raise EmpireSourceProductError("source semantic evidence has no conflicts array")
    unresolved_context = evidence.get("unresolved_context")
    if not isinstance(unresolved_context, list):
        raise EmpireSourceProductError("source semantic evidence has no unresolved_context array")

    def evidence_unresolved(domain: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for raw in [*conflicts, *unresolved_context]:
            if not isinstance(raw, dict) or raw.get("domain") != domain:
                continue
            rows.append(
                {
                    "key": str(raw.get("id")),
                    "status": str(raw.get("status") or "UNRESOLVED"),
                    "reason": str(raw.get("reason")),
                    "authority": "UNRESOLVED",
                    "source": raw.get("source"),
                }
            )
        return rows

    contract_source = contract.get("source")
    contract_terms = contract.get("terms")
    if not isinstance(contract_source, dict) or not isinstance(contract_terms, dict):
        raise EmpireSourceProductError("Warborn contract semantic evidence is malformed")
    contract_rows = [
        {
            "key": "warborn.contract.priority_legionnaire_units",
            "value": contract_terms["priority_legionnaire_units"],
            "unit": "Legionnaire units",
            "authority": contract["authority"],
            "source": contract_source,
        },
        {
            "key": "warborn.contract.priority_term_months",
            "value": contract_terms["priority_term_months"],
            "unit": "months",
            "authority": contract["authority"],
            "source": contract_source,
        },
        {
            "key": "warborn.contract.solar_guard_units",
            "value": contract_terms["solar_guard_units"],
            "unit": "Solar Guard units",
            "authority": contract["authority"],
            "source": contract_source,
        },
        {
            "key": "warborn.contract.solar_guard_term_months",
            "value": contract_terms["solar_guard_term_months"],
            "unit": "months",
            "authority": contract["authority"],
            "source": contract_source,
        },
    ]

    arterial_route_keys = [key for _route_id, _label, key in ARTERIAL_ROUTE_SPECS]
    return {
        "finance_banking": {
            "status": "PARTIAL_CONFLICT",
            "can_execute_balance_sheet": False,
            "known": [
                _fact_snapshot(facts, "ncf.active_loans_gp", unit="gp"),
                _fact_snapshot(facts, "ncf.employees", unit="employees"),
                _fact_snapshot(facts, "ncf.monthly_revenue_gp", unit="gp/month"),
                _fact_snapshot(
                    facts,
                    "finance.shimmerdeep_liquidity_target",
                    value_field="value_gp",
                    unit="gp protected target",
                ),
            ],
            "unresolved": [
                _blocker_snapshot(blockers, "finance.opening_liquid_cash"),
                _blocker_snapshot(blockers, "ncf.current_monthly_cost_gp"),
                _blocker_snapshot(blockers, "ncf.current_trial_balance"),
                _blocker_snapshot(blockers, "banking.reserve_ratio_current"),
            ],
        },
        "infrastructure_logistics": {
            "status": "PARTIAL_SOURCE_BACKED",
            "known": [
                _fact_snapshot(facts, "arterial.employees", unit="employees"),
                _fact_snapshot(facts, "arterial.monthly_cost_gp", unit="gp/month"),
                _fact_snapshot(facts, "arterial.monthly_revenue_gp", unit="gp/month"),
                *[_fact_snapshot(facts, key, unit="miles") for key in arterial_route_keys],
                _fact_snapshot(
                    facts,
                    "warborn_neverwinter.current_precision_tool_steel_tons_per_month",
                    unit="tons/month",
                ),
                _fact_snapshot(
                    facts,
                    "warborn_neverwinter.gauntlgrym_freight_distance_miles",
                    unit="miles",
                ),
                _fact_snapshot(
                    facts,
                    "warborn_neverwinter.gauntlgrym_freight_transit_days",
                    unit="days",
                ),
            ],
            "semantic_mappings": [freight],
            "unresolved": [
                _blocker_snapshot(blockers, "arterial.route_capacity"),
                *evidence_unresolved("infrastructure_logistics"),
            ],
        },
        "population_labour": {
            "status": "PARTIAL_SOURCE_BACKED",
            "known": [
                _fact_snapshot(facts, "neverwinter.current_population", unit="people"),
                _fact_snapshot(facts, "waterdeep.current_population", unit="people"),
                _fact_snapshot(facts, "ncf.employees", unit="employees"),
                _fact_snapshot(facts, "quarry_network.total_employees", unit="employees"),
                _fact_snapshot(facts, "warborn_neverwinter.employees", unit="employees"),
            ],
            "aggregation_rule": (
                "Named entity headcounts are observations, not additive Empire labour pools. "
                "Do not sum them over the admitted commercial headcount."
            ),
            "unresolved": [
                _blocker_snapshot(blockers, "forgedeep.current_population"),
                _blocker_snapshot(blockers, "labor.empire_wide_occupation_pools"),
                *evidence_unresolved("population_labour"),
            ],
        },
        "construction_capital": {
            "status": "PARTIAL_SOURCE_BACKED",
            "known": [
                _fact_snapshot(
                    facts,
                    "forgedeep.city_development.monthly_cost_gp",
                    unit="gp/month",
                ),
                _fact_snapshot(
                    facts,
                    "forgedeep.city_development.monthly_revenue_gp",
                    unit="gp/month",
                ),
                _fact_snapshot(
                    facts,
                    "finance.hard_asset_portfolio",
                    value_field="value_gp_approx",
                    unit="gp approximate hard assets",
                ),
            ],
            "unresolved": evidence_unresolved("construction_capital"),
        },
        "military_contracts": {
            "status": "PARTIAL_SOURCE_BACKED",
            "known": [
                _fact_snapshot(
                    facts,
                    "warborn_neverwinter.legionnaire_output_units_per_month",
                    unit="Legionnaire units/month",
                ),
                _fact_snapshot(
                    facts,
                    "warborn_neverwinter.maximum_legionnaire_capacity_units_per_month",
                    unit="Legionnaire units/month",
                ),
                _fact_snapshot(
                    facts,
                    "warborn_neverwinter.monthly_cost_gp",
                    unit="gp/month",
                ),
                _fact_snapshot(
                    facts,
                    "warborn_neverwinter.monthly_revenue_gp",
                    unit="gp/month",
                ),
                *contract_rows,
            ],
            "execution_rule": (
                "Standing contract quantities are constraints/reporting facts only. "
                "They do not authorize future facility output or campaign-time advancement."
            ),
            "unresolved": [
                _blocker_snapshot(blockers, "silversheen.warborn_aluminum_allocation"),
                *evidence_unresolved("military_contracts"),
            ],
        },
    }


def source_semantic_coverage(
    domains: Mapping[str, Mapping[str, Any]],
    census_path: Path = DEFAULT_CENSUS_SNAPSHOT,
) -> dict[str, Any]:
    """Overlay executable semantic mapping on the preserved census snapshot.

    The dated census remains immutable recovery evidence. This overlay only
    reclassifies records that have concrete mapped facts in the current engine;
    it does not call them SIMULATED.
    """

    try:
        census = json.loads(census_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EmpireSourceProductError(f"cannot read census snapshot: {census_path}: {exc}") from exc
    stored = census.get("storedCoverage")
    flags = census.get("flags")
    if not isinstance(stored, dict) or not isinstance(flags, list):
        raise EmpireSourceProductError("census snapshot lacks coverage state")

    prior_by_id = {
        str(row.get("id")): str(row.get("coverage"))
        for row in flags
        if isinstance(row, dict) and row.get("id") and row.get("coverage")
    }
    pages: dict[str, dict[str, Any]] = {}
    for domain_name, domain in domains.items():
        if not isinstance(domain, Mapping):
            continue
        for row in domain.get("known") or []:
            if not isinstance(row, Mapping):
                continue
            source = row.get("source")
            if not isinstance(source, Mapping):
                continue
            page_id = source.get("notion_page")
            if not page_id:
                continue
            page_id = str(page_id)
            record = pages.setdefault(
                page_id,
                {
                    "source_record_id": page_id,
                    "title": source.get("title"),
                    "prior_coverage": prior_by_id.get(page_id, "UNKNOWN"),
                    "new_coverage": "SOURCE_MAPPED",
                    "domains": [],
                    "fact_keys": [],
                    "simulated": False,
                },
            )
            if domain_name not in record["domains"]:
                record["domains"].append(domain_name)
            fact_key = row.get("key")
            if fact_key and fact_key not in record["fact_keys"]:
                record["fact_keys"].append(str(fact_key))

    mapped = sorted(pages.values(), key=lambda row: row["source_record_id"])
    moved_from_unknown = sum(row["prior_coverage"] == "UNKNOWN" for row in mapped)
    unknown_before = int(stored.get("UNKNOWN") or 0)
    if moved_from_unknown > unknown_before:
        raise EmpireSourceProductError("semantic coverage overlay exceeds UNKNOWN census count")
    return {
        "status": "PARTIAL_SOURCE_MAPPED",
        "basis": (
            "Unique source pages with concrete runtime semantic facts; dated census "
            "snapshot is preserved and SIMULATED remains zero"
        ),
        "mapped_records": mapped,
        "mapped_record_count": len(mapped),
        "moved_from_unknown": moved_from_unknown,
        "unknown_before": unknown_before,
        "unknown_after_overlay": unknown_before - moved_from_unknown,
        "simulated_before": int(stored.get("SIMULATED") or 0),
        "simulated_after_overlay": 0,
    }


def _map_openttd_source_candidate(
    *,
    source_path: Path = DEFAULT_SOURCE_INPUTS,
    semantic_evidence_path: Path = DEFAULT_SEMANTIC_EVIDENCE,
) -> dict[str, Any]:
    """Bind a real source shipment to OpenTTD semantics without inventing units."""

    facts = _load_facts(source_path)
    evidence = _load_semantic_evidence(semantic_evidence_path)
    freight = _semantic_mapping(evidence, "warborn_gauntlgrym_precision_steel_flow")
    upstream = evidence.get("upstream_semantics")
    if not isinstance(upstream, dict) or not isinstance(upstream.get("openttd"), dict):
        raise EmpireSourceProductError("OpenTTD semantic evidence is missing")
    openttd = dict(upstream["openttd"])
    if openttd.get("commit") != OPENTTD_COMMIT:
        raise EmpireSourceProductError("OpenTTD semantic evidence pin drifted")
    if openttd.get("cargo_type") != 9 or openttd.get("cargo_label") != "CT_STEEL":
        raise EmpireSourceProductError("OpenTTD steel cargo semantics drifted")

    quantity_key = str(freight["quantity_fact_key"])
    distance_key = str(freight["distance_fact_key"])
    transit_key = str(freight["transit_fact_key"])
    quantity = _exact_number(facts[quantity_key], quantity_key)
    distance = _exact_number(facts[distance_key], distance_key)
    transit_days = _exact_number(facts[transit_key], transit_key)
    expected = freight.get("source_values")
    if not isinstance(expected, dict):
        raise EmpireSourceProductError("Warborn freight source values are missing")
    if (
        Decimal(str(expected.get("quantity_tons_per_month"))) != Decimal(str(quantity))
        or Decimal(str(expected.get("distance_miles"))) != Decimal(str(distance))
        or Decimal(str(expected.get("transit_days"))) != Decimal(str(transit_days))
    ):
        raise EmpireSourceProductError(
            "Warborn freight semantic evidence drifted from source authority"
        )

    return {
        "status": "MAPPED_BLOCKED",
        "invoked": False,
        "upstream": "OpenTTD",
        "upstream_commit": OPENTTD_COMMIT,
        "source_flow": {
            "id": freight["id"],
            "commodity": "precision tool steel",
            "quantity_tons_per_month": quantity,
            "distance_miles": distance,
            "transit_days": transit_days,
            "authority": freight["authority"],
            "source": freight["source"],
        },
        "upstream_semantics": {
            "cargo_type": openttd["cargo_type"],
            "cargo_label": openttd["cargo_label"],
            "cargo_unit": openttd["cargo_unit"],
            "income_function": openttd["income_function"],
            "authority": "UPSTREAM-ADOPTED",
            "source_file": openttd["source_file"],
        },
        "blockers": [
            {
                "authority": "UNRESOLVED",
                "kind": "UNIT_BRIDGE",
                "reason": (
                    "No USER-RULED or SOURCE-DERIVED conversion maps campaign miles to "
                    "OpenTTD tile distance. 85 source miles therefore cannot be passed as 85 tiles."
                ),
            },
            {
                "authority": "UNRESOLVED",
                "kind": "FRACTIONAL_CARGO",
                "reason": (
                    "The source shipment is 1.5 tons/month while the pinned OpenTTD income "
                    "entry point accepts integer cargo pieces. No rounding/extrapolation rule is adopted."
                ),
            },
        ],
        "reason": (
            "A real Warborn/Gauntlgrym precision-steel shipment is source-mapped to "
            "OpenTTD's actual steel cargo, but the product is not invoked until the "
            "campaign-to-product unit bridge has authority."
        ),
    }


def source_known_state(
    source_path: Path = DEFAULT_SOURCE_INPUTS,
) -> dict[str, Any]:
    payload = _load_payload(source_path)
    facts = _index_facts(payload)
    blockers = _index_blockers(payload)
    unresolved: list[str] = []

    census: list[dict[str, Any]] = []
    for spec in CENSUS_SPECS:
        row = facts.get(spec["population_key"])
        if row is None:
            raise EmpireSourceProductError(f"missing source fact for {spec['population_key']}")
        census.append(
            {
                "id": spec["id"],
                "settlement": spec["settlement"],
                "role": spec["role"],
                "population": _exact_number(row, spec["population_key"]),
                "status": "SOURCE_BACKED",
                "authority": row["authority"],
                "source": _source_ref(row, spec["population_key"]),
                "note": row.get("note"),
            }
        )
    forgedeep = blockers.get("forgedeep.current_population")
    if forgedeep is None:
        raise EmpireSourceProductError("missing Forgedeep population blocker")
    census.append(
        {
            "id": "forgedeep",
            "settlement": "Forgedeep",
            "role": "chartered underground citadel",
            "population": None,
            "status": str(forgedeep.get("status") or "MISSING_DATA"),
            "reason": str(forgedeep.get("reason")),
            "source": {
                "notion_page": (forgedeep.get("source") or {}).get("notion_page"),
                "title": (forgedeep.get("source") or {}).get("title"),
                "fact_key": "forgedeep.current_population",
            },
        }
    )
    unresolved.append("Forgedeep civilian population remains unknown")
    overview = blockers.get("neverwinter.population_overview_paragraph")
    if overview:
        unresolved.append(str(overview.get("reason")))

    food: list[dict[str, Any]] = []
    for spec in FOOD_ENTITY_SPECS:
        employees = facts.get(spec["employees_key"])
        revenue = facts.get(spec["revenue_key"])
        cost = facts.get(spec["cost_key"])
        if employees is None or revenue is None or cost is None:
            raise EmpireSourceProductError(f"missing food financial facts for {spec['id']}")
        physical = blockers.get(spec["physical_blocker"])
        if physical is None:
            raise EmpireSourceProductError(f"missing physical-output blocker for {spec['id']}")
        food.append(
            {
                "id": spec["id"],
                "entity": spec["entity"],
                "kind": spec["kind"],
                "employees": _exact_number(employees, spec["employees_key"]),
                "monthly_revenue_gp": _exact_number(revenue, spec["revenue_key"]),
                "monthly_cost_gp": _exact_number(cost, spec["cost_key"]),
                "physical_output": None,
                "physical_output_status": str(physical.get("status") or "MISSING_DATA"),
                "authority": revenue["authority"],
                "source": _source_ref(revenue, spec["revenue_key"]),
                "unresolved": str(physical.get("reason")),
            }
        )
        unresolved.append(f"{spec['entity']}: {physical.get('reason')}")
    for spec in FOOD_AGGREGATE_SPECS:
        employees = facts.get(spec["employees_key"])
        revenue = facts.get(spec["revenue_key"])
        if employees is None or revenue is None:
            raise EmpireSourceProductError(f"missing food aggregate facts for {spec['id']}")
        food.append(
            {
                "id": spec["id"],
                "entity": spec["entity"],
                "kind": spec["kind"],
                "employees": _exact_number(employees, spec["employees_key"]),
                "monthly_revenue_gp": _exact_number(revenue, spec["revenue_key"]),
                "physical_output": None,
                "physical_output_status": "NOT_DERIVED",
                "authority": revenue["authority"],
                "source": _source_ref(revenue, spec["revenue_key"]),
                "note": spec["note"],
            }
        )

    routes: list[dict[str, Any]] = []
    for route_id, label, key in ARTERIAL_ROUTE_SPECS:
        row = facts.get(key)
        if row is None:
            raise EmpireSourceProductError(f"missing arterial distance fact {key}")
        routes.append(
            {
                "id": route_id,
                "route": label,
                "distance_miles": _exact_number(row, key),
                "approximate": bool(row.get("approximate")),
                "status": "COMPLETE",
                "capacity": None,
                "authority": row["authority"],
                "source": _source_ref(row, key),
            }
        )
    capacity = blockers.get("arterial.route_capacity")
    if capacity is None:
        raise EmpireSourceProductError("missing arterial capacity blocker")
    unresolved.append(str(capacity.get("reason")))

    return {
        "status": "PARTIAL_SOURCE_BACKED",
        "census": census,
        "food_financials": food,
        "arterial_routes": routes,
        "unresolved": unresolved,
        "reason": (
            "Neverwinter and Waterdeep populations, food-sector gp/headcount, and five "
            "complete arterial distances are SOURCE-DERIVED. Forgedeep occupancy, food "
            "physical volumes, and route freight capacities stay unknown. OpenTTD is "
            "not invoked from distances alone."
        ),
    }


def _mesa_seed(seed: str) -> int:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()[:4]
    return int.from_bytes(digest, "big")


def _severity_priority(severity: str) -> str:
    if severity in {"URGENT"}:
        return "HIGH"
    if severity in {"DEVELOPING", "UNRESOLVED"}:
        return "DEFAULT"
    return "LOW"


def _map_mesa(
    *,
    seed: str,
    month_label: str,
    sector_results: Sequence[Mapping[str, Any]],
    expense_control: Mapping[str, Any],
    complications: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    events: list[MesaProductEvent] = []
    for row in sector_results:
        sector = str(row["sector"])
        events.append(
            MesaProductEvent(
                1,
                "HIGH",
                f"sector:{sector}",
                {
                    "kind": "sector-revenue",
                    "sector": sector,
                    "outcome": row["roll"]["outcome"],
                    "severity": row["severity"],
                    "month_label": month_label,
                },
            )
        )
    expense_roll = expense_control["roll"]
    events.append(
        MesaProductEvent(
            2,
            "DEFAULT",
            "expense-control",
            {
                "kind": "administration-expense",
                "outcome": expense_roll["outcome"],
                "month_label": month_label,
            },
        )
    )
    for row in complications:
        events.append(
            MesaProductEvent(
                3,
                _severity_priority(_severity_for_optional(row.get("final_outcome"))),
                f"entity:{row['source_record_id']}",
                {
                    "kind": "entity-complication",
                    "entity": row["entity"],
                    "raw_d20": row["raw_d20"],
                    "final_outcome": row["final_outcome"],
                    "month_label": month_label,
                },
            )
        )
    if not mesa_available():
        return {
            "status": "UNAVAILABLE",
            "blocker": "pinned Mesa requires Python 3.12 and the optional dependency",
            "intended_events": len(events),
            "intended_event_ids": [event.event_id for event in events],
            "provenance": (
                "Mesa would schedule the SOURCE-DERIVED empire-operations-engine "
                "business-phase events; it is not used to invent shocks"
            ),
        }
    try:
        result = run_mesa_preview(tuple(events), until_tick=3, seed=_mesa_seed(seed))
    except MesaRuntimeUnavailable as exc:
        return {
            "status": "UNAVAILABLE",
            "blocker": str(exc),
            "intended_events": len(events),
        }
    return {
        "status": "USED_IN_RUN",
        "upstream": result.upstream,
        "upstream_commit": result.upstream_commit,
        "upstream_version": result.upstream_version,
        "final_time": result.final_time,
        "executed_event_ids": [event["event_id"] for event in result.executed_events],
        "collected_event_counts": list(result.collected_event_counts),
        "canonical_time_advanced": result.canonical_time_advanced,
        "provenance": (
            "UPSTREAM-ADOPTED Mesa event runtime; scheduled events are the "
            "SOURCE-DERIVED empire-operations-engine business-phase receipts"
        ),
    }


def _severity_for_optional(outcome: object) -> str:
    if outcome in {"crisis"}:
        return "URGENT"
    if outcome in {"complication"}:
        return "DEVELOPING"
    if outcome in {"success", "opportunity"}:
        return "POSITIVE"
    if outcome in {"normal"}:
        return "BACKGROUND"
    return "UNRESOLVED"


def _map_freecol(lines: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    warborn = next(row for row in lines if row["id"] == "warborn_neverwinter")
    actual = {"baen.goods.warborn.legionnaire": int(warborn["quantity"])}
    maximum = {"baen.goods.warborn.legionnaire": int(warborn["maximum"])}
    checkout = os.environ.get("FREECOL_CHECKOUT")
    if not checkout:
        return {
            "status": "UNAVAILABLE",
            "blocker": "FREECOL_CHECKOUT is not configured",
            "source_actual": actual,
            "source_maximum": maximum,
            "provenance": (
                "FreeCol actual-versus-maximum is admissible for Warborn because "
                "both 12 actual and 15 maximum are SOURCE-DERIVED"
            ),
        }
    from .freecol_product import FreeColProductError, run_freecol_production_info

    try:
        result = run_freecol_production_info(checkout, actual=actual, maximum=maximum)
    except (FreeColProductError, OSError, ValueError) as exc:
        return {
            "status": "UNAVAILABLE",
            "blocker": str(exc),
            "source_actual": actual,
            "source_maximum": maximum,
        }
    return {
        "status": "USED_IN_RUN",
        "upstream": result.upstream,
        "upstream_commit": result.upstream_commit,
        "actual": result.actual,
        "maximum": result.maximum,
        "deficits": result.deficits,
        "canonical_time_advanced": result.canonical_time_advanced,
        "provenance": (
            "UPSTREAM-ADOPTED FreeCol ProductionInfo; quantities are SOURCE-DERIVED "
            "Warborn Neverwinter 12 actual vs 15 maximum"
        ),
    }


def _map_unknown_horizons(lines: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    checkout = os.environ.get("UNKNOWN_HORIZONS_CHECKOUT")
    intended = [
        {
            "line_id": index,
            "entity": row["entity"],
            "produced_quantity": row["quantity"],
            "unit": row["unit"],
            "consumed": [],
            "reason_no_consume": list(row["unresolved_inputs"]),
        }
        for index, row in enumerate(lines, 1)
    ]
    if not checkout:
        return {
            "status": "UNAVAILABLE",
            "blocker": "UNKNOWN_HORIZONS_CHECKOUT is not configured",
            "intended_production_only_lines": intended,
            "provenance": (
                "Unknown Horizons may instantiate production-only lines from sourced "
                "outputs; consume coefficients remain unmapped because they are not source-backed"
            ),
        }
    from .unknown_horizons_product import (
        UnknownHorizonsProductError,
        run_unknown_horizons_production_line,
    )

    checked: list[dict[str, Any]] = []
    for index, row in enumerate(lines, 1):
        try:
            result = run_unknown_horizons_production_line(
                checkout,
                line_id=index,
                produces=((index, float(row["quantity"])),),
                consumes=(),
                time=1.0,
            )
        except (UnknownHorizonsProductError, OSError, ValueError) as exc:
            return {
                "status": "UNAVAILABLE",
                "blocker": str(exc),
                "intended_production_only_lines": intended,
            }
        checked.append(
            {
                "line_id": result.line_id,
                "entity": row["entity"],
                "produced": {
                    str(k): _product_number(v) for k, v in result.produced.items()
                },
                "consumed": {
                    str(k): _product_number(v) for k, v in result.consumed.items()
                },
            }
        )
    return {
        "status": "USED_IN_RUN",
        "recipes_checked": len(checked),
        "details": checked,
        "canonical_time_advanced": False,
        "provenance": (
            "UPSTREAM-ADOPTED Unknown Horizons ProductionLine on SOURCE-DERIVED "
            "outputs only; no consume coefficients were invented"
        ),
    }


def map_source_backed_physical_layer(
    *,
    seed: str,
    month_label: str,
    sector_results: Sequence[Mapping[str, Any]],
    expense_control: Mapping[str, Any],
    complications: Sequence[Mapping[str, Any]],
    source_path: Path = DEFAULT_SOURCE_INPUTS,
    semantic_evidence_path: Path = DEFAULT_SEMANTIC_EVIDENCE,
) -> dict[str, Any]:
    lines = source_production_lines(source_path)
    known_state = source_known_state(source_path)
    semantic_domains = source_semantic_domains(source_path, semantic_evidence_path)
    semantic_coverage = source_semantic_coverage(semantic_domains)
    products = {
        "mesa": _map_mesa(
            seed=seed,
            month_label=month_label,
            sector_results=sector_results,
            expense_control=expense_control,
            complications=complications,
        ),
        "freecol": _map_freecol(lines),
        "unknown_horizons": _map_unknown_horizons(lines),
        "openttd": _map_openttd_source_candidate(
            source_path=source_path,
            semantic_evidence_path=semantic_evidence_path,
        ),
        "veloren": {
            "status": "NOT_INVOKED",
            "reason": DORMANT_PRODUCTS[1]["reason"],
        },
        "brunnfeld": {
            "status": "NOT_INVOKED",
            "reason": DORMANT_PRODUCTS[2]["reason"],
        },
    }
    unresolved = [ALLOCATION_CONFLICT]
    unresolved.extend(known_state["unresolved"])
    for row in lines:
        unresolved.extend(f"{row['entity']}: {item}" for item in row["unresolved_inputs"])
    mapped = [
        name
        for name, item in products.items()
        if item.get("status") == "USED_IN_RUN"
    ]
    return {
        "status": "PARTIAL_SOURCE_BACKED",
        "reason": (
            "Known industrial output lines, Neverwinter/Waterdeep census, food-sector "
            "financials, and complete arterial distances are reported from SOURCE-DERIVED "
            "facts. Mesa schedules the campaign business-phase events when installed. "
            "FreeCol/Unknown Horizons may consume sourced industrial outputs when their "
            "checkouts are present. OpenTTD now has a real source shipment mapped to its "
            "actual steel-cargo semantics, but remains fail-closed because campaign miles "
            "and 1.5 source tons do not yet have authoritative OpenTTD unit bridges. Veloren "
            "and Brunnfeld stay dormant. No conversion ratio, inventory, population, or "
            "price was invented."
        ),
        "production_lines": lines,
        "known_state": known_state,
        "semantic_domains": semantic_domains,
        "semantic_coverage": semantic_coverage,
        "products": products,
        "products_used": mapped,
        "dormant": list(DORMANT_PRODUCTS),
        "unresolved": unresolved,
    }
