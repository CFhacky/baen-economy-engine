"""Source-backed physical production and optional product mapping.

The actual Hammer-1495 path may report industrial quantities that already exist
in campaign authority, and may invoke an upstream product only when that
product's required inputs are source-backed. Products are never substitute
data sources. Unknown conversion ratios, inventories, prices, and route
capacities stay unknown.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from .mesa_runtime import MesaProductEvent, MesaRuntimeUnavailable, mesa_available, run_mesa_preview


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_INPUTS = (
    PROJECT_ROOT / "recovery/ECONOMY_SOURCE_INPUT_AUTHORITY_2026-09-17.json"
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
        "status": "NOT_INVOKED",
        "reason": "route freight capacities and loss rates are not source-backed for the actual month",
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


def _load_facts(path: Path) -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EmpireSourceProductError(f"cannot read source-input authority: {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != "tnp.economy.source-input-authority/1":
        raise EmpireSourceProductError("source-input authority schema is unsupported")
    if payload.get("rule") is None:
        raise EmpireSourceProductError("source-input authority lacks the actual-run rule")
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
                "produced": {str(k): v for k, v in result.produced.items()},
                "consumed": {str(k): v for k, v in result.consumed.items()},
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
) -> dict[str, Any]:
    lines = source_production_lines(source_path)
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
        "openttd": {
            "status": "NOT_INVOKED",
            "reason": DORMANT_PRODUCTS[0]["reason"],
        },
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
            "Known industrial output lines are reported from SOURCE-DERIVED facts. "
            "Mesa schedules the campaign business-phase events when installed. "
            "FreeCol/Unknown Horizons may consume those sourced outputs when their "
            "checkouts are present. OpenTTD, Veloren, and Brunnfeld stay dormant "
            "because route capacities, opening stocks, and market prices are not "
            "source-backed. No conversion ratio, inventory, or price was invented."
        ),
        "production_lines": lines,
        "products": products,
        "products_used": mapped,
        "dormant": list(DORMANT_PRODUCTS),
        "unresolved": unresolved,
    }
