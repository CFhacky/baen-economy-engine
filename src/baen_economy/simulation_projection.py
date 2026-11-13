"""Parameterized physical-economy projection over source-backed Baen state.

This module is intentionally non-canonical. It fills missing economic minutiae
with explicit MODEL-PROPOSED priors from SIMULATION_PARAMETER_CATALOG, records
every resolved value, and uses those priors to drive the upstream products.

The important distinction is:
- source facts describe campaign state;
- simulation parameters let the model run;
- neither simulation inputs nor outputs become canon automatically.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from .brunnfeld_sidecar import BrunnfeldServiceClient, BrunnfeldSidecarError
from .openttd_product import OpenTTDAdminClient, OpenTTDProductError
from .simulation_parameters import resolve_catalog, resolve_map
from .veloren_product import VelorenProductError, run_veloren_economy


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_INPUTS = (
    PROJECT_ROOT / "recovery/ECONOMY_SOURCE_INPUT_AUTHORITY_2026-09-17.json"
)


class SimulationProjectionError(ValueError):
    pass


def _load_source(path: Path = DEFAULT_SOURCE_INPUTS) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SimulationProjectionError(f"cannot read source authority: {path}: {exc}") from exc
    if payload.get("schema") != "tnp.economy.source-input-authority/1":
        raise SimulationProjectionError("source authority schema is unsupported")
    return payload


def _facts(path: Path = DEFAULT_SOURCE_INPUTS) -> dict[str, dict[str, Any]]:
    payload = _load_source(path)
    result: dict[str, dict[str, Any]] = {}
    for row in payload.get("facts") or []:
        if isinstance(row, dict) and isinstance(row.get("key"), str):
            result[row["key"]] = row
    return result


def _num(facts: Mapping[str, Mapping[str, Any]], key: str) -> float:
    row = facts.get(key)
    if row is None:
        raise SimulationProjectionError(f"missing source fact: {key}")
    value = row.get("value")
    if type(value) is bool or not isinstance(value, (int, float)):
        raise SimulationProjectionError(f"source fact is not numeric: {key}")
    return float(value)


def _settlement_populations(
    *,
    base_physical: Mapping[str, Any],
    params: Mapping[str, float | int],
) -> list[dict[str, Any]]:
    census = {
        str(row["id"]): row
        for row in (base_physical.get("known_state") or {}).get("census") or []
        if isinstance(row, Mapping)
    }
    neverwinter = census.get("neverwinter")
    waterdeep = census.get("waterdeep")
    if not neverwinter or not waterdeep:
        raise SimulationProjectionError("source-backed Neverwinter/Waterdeep census is missing")

    raw_shares = {
        "commoners": float(params["population.commoner_share"]),
        "artisans": float(params["population.artisan_share"]),
        "burghers": float(params["population.burgher_share"]),
        "elites": float(params["population.elite_share"]),
    }
    share_total = sum(raw_shares.values())
    shares = {key: value / share_total for key, value in raw_shares.items()}

    settlements = [
        {
            "id": "neverwinter",
            "name": "Neverwinter",
            "population": int(neverwinter["population"]),
            "population_authority": "SOURCE-DERIVED",
        },
        {
            "id": "waterdeep",
            "name": "Waterdeep",
            "population": int(waterdeep["population"]),
            "population_authority": "SOURCE-DERIVED",
        },
        {
            "id": "forgedeep",
            "name": "Forgedeep",
            "population": int(round(float(params["settlement.forgedeep.population"]))),
            "population_authority": "MODEL-PROPOSED",
        },
    ]
    for row in settlements:
        row["class_shares"] = shares
        row["class_populations"] = {
            key: int(round(row["population"] * share))
            for key, share in shares.items()
        }
    return settlements


def _food_projection(
    *,
    settlements: Sequence[Mapping[str, Any]],
    base_physical: Mapping[str, Any],
    params: Mapping[str, float | int],
) -> dict[str, Any]:
    grain_kg_day = float(params["food.grain_kg_per_person_day"])
    fish_kg_month = float(params["food.preserved_fish_kg_per_person_month"])
    coverage = float(params["inventory.food_coverage_months"])
    budget = float(params["food.household_budget_gp_per_person_month"])

    demand_rows = []
    total_grain = 0.0
    total_fish = 0.0
    total_budget = 0.0
    for settlement in settlements:
        population = int(settlement["population"])
        grain = population * grain_kg_day * 30.0 / 1000.0
        fish = population * fish_kg_month / 1000.0
        cash = population * budget
        total_grain += grain
        total_fish += fish
        total_budget += cash
        demand_rows.append(
            {
                "settlement": settlement["name"],
                "population": population,
                "grain_demand_tons_month": grain,
                "fish_demand_tons_month": fish,
                "food_opening_stock_target_tons": (grain + fish) * coverage,
                "household_food_budget_gp_month": cash,
            }
        )

    known_food = {
        str(row["id"]): row
        for row in (base_physical.get("known_state") or {}).get("food_financials") or []
        if isinstance(row, Mapping)
    }
    agri = known_food.get("agricultural_shelters")
    aqua = known_food.get("aquaculture_network")
    if not agri or not aqua:
        raise SimulationProjectionError("source-backed food staffing is missing")
    grain_supply = int(agri["employees"]) * float(
        params["production.agriculture_tons_per_worker_month"]
    )
    fish_supply = int(aqua["employees"]) * float(
        params["production.aquaculture_tons_per_worker_month"]
    )

    grain_shortage = max(0.0, total_grain - grain_supply)
    fish_shortage = max(0.0, total_fish - fish_supply)
    grain_shortage_ratio = grain_shortage / total_grain if total_grain else 0.0
    fish_shortage_ratio = fish_shortage / total_fish if total_fish else 0.0
    aggregate_shortage = max(grain_shortage_ratio, fish_shortage_ratio)
    elasticity = float(params["market.price_elasticity"])
    price_pressure_index = 1.0 + aggregate_shortage * elasticity

    migration_rate = min(
        float(params["migration.max_monthly_rate"]),
        aggregate_shortage * float(params["migration.shortage_weight"]),
    )

    return {
        "settlements": demand_rows,
        "demand": {
            "grain_tons_month": total_grain,
            "fish_tons_month": total_fish,
            "household_food_budget_gp_month": total_budget,
        },
        "simulated_supply": {
            "grain_tons_month": grain_supply,
            "fish_tons_month": fish_supply,
            "grain_basis": "8 SOURCE-DERIVED Agricultural Shelter staff × MODEL-PROPOSED tons/worker/month",
            "fish_basis": "55 SOURCE-DERIVED aquaculture-network staff × MODEL-PROPOSED tons/worker/month",
        },
        "balance": {
            "grain_shortage_tons": grain_shortage,
            "fish_shortage_tons": fish_shortage,
            "grain_shortage_ratio": grain_shortage_ratio,
            "fish_shortage_ratio": fish_shortage_ratio,
            "price_pressure_index": price_pressure_index,
            "migration_pressure_rate": migration_rate,
        },
    }


def _labor_projection(
    *,
    settlements: Sequence[Mapping[str, Any]],
    base_physical: Mapping[str, Any],
    params: Mapping[str, float | int],
) -> dict[str, Any]:
    participation = float(params["labor.participation_rate"])
    unemployment = float(params["labor.unemployment_rate"])
    rows = []
    total_labor = 0
    total_unemployed = 0
    for settlement in settlements:
        population = int(settlement["population"])
        labor_force = int(round(population * participation))
        unemployed = int(round(labor_force * unemployment))
        rows.append(
            {
                "settlement": settlement["name"],
                "population": population,
                "labor_force": labor_force,
                "unemployed": unemployed,
                "available_employed_capacity": labor_force - unemployed,
            }
        )
        total_labor += labor_force
        total_unemployed += unemployed

    labor_known = (base_physical.get("known_state") or {}).get("labor") or {}
    return {
        "settlements": rows,
        "labor_force_total": total_labor,
        "unemployed_total": total_unemployed,
        "source_admitted_commercial_employees": labor_known.get(
            "admitted_commercial_employees"
        ),
        "untrained_daily_wage_gp": float(params["labor.untrained_daily_wage_gp"]),
        "trained_daily_wage_gp": float(params["labor.trained_daily_wage_gp"]),
        "note": (
            "Commercial Registry headcount is a known subset of employment. It is not "
            "subtracted from population twice or treated as the whole labor market."
        ),
    }


def _route_projection(
    *,
    base_physical: Mapping[str, Any],
    params: Mapping[str, float | int],
    facts: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    tier_by_id = {
        "neverwinter_waterdeep": "heavy",
        "neverwinter_luskan": "heavy",
        "neverwinter_gauntlgrym": "medium",
        "neverwinter_mirabar": "medium",
        "forgedeep_guardians_gate": "medium",
    }
    crossing_param = {
        "heavy": "transport.heavy_corridor_crossings_per_day",
        "medium": "transport.medium_corridor_crossings_per_day",
        "light": "transport.light_spur_crossings_per_day",
    }
    freight_share = float(params["transport.freight_share_of_crossings"])
    payload = float(params["transport.generic_wagon_payload_tons"])
    speed = float(params["transport.standard_wagon_miles_per_day"])
    loss = float(params["transport.route_loss_rate"])
    rows = []
    for route in (base_physical.get("known_state") or {}).get("arterial_routes") or []:
        route_id = str(route["id"])
        tier = tier_by_id.get(route_id, "medium")
        crossings = float(params[crossing_param[tier]])
        distance = float(route["distance_miles"])
        rows.append(
            {
                "id": route_id,
                "route": route["route"],
                "source_distance_miles": distance,
                "tier": tier,
                "simulated_crossings_day": crossings,
                "simulated_freight_share": freight_share,
                "simulated_payload_tons": payload,
                "simulated_capacity_tons_month": crossings * freight_share * payload * 30.0,
                "simulated_transit_days": max(1.0, distance / speed),
                "simulated_loss_rate": loss,
                "authority": {
                    "distance": route.get("authority"),
                    "traffic_capacity_transit_loss": "MODEL-PROPOSED",
                },
            }
        )

    smh_distance = _num(facts, "star_metal_hills.gauntlgrym_route_distance_miles")
    priority_speed = float(params["transport.priority_freight_miles_per_day"])
    rows.append(
        {
            "id": "star_metal_hills_gauntlgrym",
            "route": "Star Metal Hills → Gauntlgrym",
            "source_distance_miles": smh_distance,
            "source_flow_tons_month": _num(
                facts, "star_metal_hills.bauxite_output_tons_per_month"
            ),
            "tier": "light-industrial-spur",
            "simulated_crossings_day": float(
                params["transport.light_spur_crossings_per_day"]
            ),
            "simulated_freight_share": freight_share,
            "simulated_payload_tons": float(
                params["transport.baen_heavy_wagon_payload_tons"]
            ),
            "simulated_capacity_tons_month": float(
                params["transport.light_spur_crossings_per_day"]
            )
            * freight_share
            * float(params["transport.baen_heavy_wagon_payload_tons"])
            * 30.0,
            "simulated_transit_days": max(1.0, smh_distance / priority_speed),
            "simulated_loss_rate": loss,
            "authority": {
                "distance_and_flow": "SOURCE-DERIVED",
                "capacity_transit_loss": "MODEL-PROPOSED",
            },
        }
    )
    return {"routes": rows}


def _bank_projection(
    *,
    facts: Mapping[str, Mapping[str, Any]],
    params: Mapping[str, float | int],
) -> dict[str, Any]:
    loans = _num(facts, "ncf.active_loans_gp")
    ltd = float(params["bank.loan_to_deposit_ratio"])
    reserve_ratio = float(params["bank.reserve_ratio"])
    deposits = loans / ltd
    reserves = deposits * reserve_ratio
    return {
        "source_active_loans_gp": loans,
        "simulated_deposits_gp": deposits,
        "simulated_reserves_gp": reserves,
        "simulated_reserve_ratio": reserve_ratio,
        "simulated_loan_to_deposit_ratio": ltd,
        "authority": {
            "loans": "SOURCE-DERIVED",
            "deposits_reserves_ratios": "MODEL-PROPOSED",
        },
        "note": (
            "This is a simulation balance-sheet prior. It is not the missing NCF "
            "Day-7-Hammer-1495 trial balance and does not establish current liquid cash."
        ),
    }


def _industry_projection(
    *,
    facts: Mapping[str, Mapping[str, Any]],
    params: Mapping[str, float | int],
    base_physical: Mapping[str, Any],
) -> dict[str, Any]:
    silversheen_revenue = _num(
        facts, "silversheen.current_gross_revenue_gp_per_month"
    )
    silversheen_cost = float(
        params["production.silversheen_current_monthly_cost_gp"]
    )
    allocation = float(
        params["production.warborn_aluminum_allocation_tons_per_month"]
    )
    industrial_coverage = float(params["inventory.industrial_coverage_months"])
    lines = []
    for line in base_physical.get("production_lines") or []:
        quantity = float(line["quantity"])
        lines.append(
            {
                "entity": line["entity"],
                "monthly_output": quantity,
                "unit": line["unit"],
                "simulated_opening_inventory_target": quantity * industrial_coverage,
                "inventory_authority": "MODEL-PROPOSED",
            }
        )
    return {
        "production_lines": lines,
        "silversheen": {
            "source_revenue_gp_month": silversheen_revenue,
            "simulated_cost_gp_month": silversheen_cost,
            "simulated_profit_gp_month": silversheen_revenue - silversheen_cost,
            "source_output_tons_month": _num(
                facts, "silversheen.current_output_aluminum_tons_per_month"
            ),
            "simulated_warborn_allocation_tons_month": allocation,
            "allocation_authority": "MODEL-PROPOSED over a SOURCE CONFLICT (30 t/mo vs 20% = 36 t/mo)",
        },
    }


def _openttd_projection(
    *,
    routes: Mapping[str, Any],
) -> dict[str, Any]:
    host = os.environ.get("OPENTTD_ADMIN_HOST")
    port = os.environ.get("OPENTTD_ADMIN_PORT")
    password = os.environ.get("OPENTTD_ADMIN_PASSWORD")
    route = next(
        row for row in routes["routes"] if row["id"] == "star_metal_hills_gauntlgrym"
    )
    request = {
        "cargo_type": 8,
        "pieces": int(round(float(route["source_flow_tons_month"]))),
        "distance_tiles": int(round(float(route["source_distance_miles"]))),
        "days_in_transit": int(math.ceil(float(route["simulated_transit_days"]))),
    }
    if not host or not port or not password:
        return {
            "status": "UNAVAILABLE",
            "blocker": "OpenTTD product environment is not configured",
            "intended_request": request,
        }
    try:
        with OpenTTDAdminClient(
            host, int(port), password=password, timeout=10.0
        ) as client:
            income = client.transport_income(**request)
            snapshot = client.snapshot()
    except (OpenTTDProductError, OSError, ValueError) as exc:
        return {
            "status": "UNAVAILABLE",
            "blocker": str(exc),
            "intended_request": request,
        }
    return {
        "status": "USED_IN_RUN",
        "input": request,
        "transport_income_game_currency": income,
        "upstream_commit": snapshot.upstream_commit,
        "provenance": (
            "SOURCE-DERIVED 800 t/mo ore flow + ~80 mile route; transit days are "
            "MODEL-PROPOSED from the priority-freight speed parameter."
        ),
    }


def _veloren_projection(
    *,
    settlements: Sequence[Mapping[str, Any]],
    food: Mapping[str, Any],
) -> dict[str, Any]:
    checkout = os.environ.get("VELOREN_CHECKOUT")
    demand_by_name = {
        row["settlement"]: row for row in food["settlements"]
    }
    intended = []
    for settlement in settlements:
        demand = demand_by_name[str(settlement["name"])]
        intended.append(
            {
                "settlement": settlement["name"],
                "population": int(settlement["population"]),
                "food_stock": float(demand["food_opening_stock_target_tons"]),
                "coin_stock": float(demand["household_food_budget_gp_month"]),
                "days": 30.0,
            }
        )
    if not checkout:
        return {
            "status": "UNAVAILABLE",
            "blocker": "VELOREN_CHECKOUT is not configured",
            "intended_inputs": intended,
        }
    results = []
    try:
        for row in intended:
            result = run_veloren_economy(
                checkout,
                population=row["population"],
                food_stock=row["food_stock"],
                coin_stock=row["coin_stock"],
                days=row["days"],
                timeout=120.0,
            )
            results.append({"settlement": row["settlement"], **asdict(result)})
    except (VelorenProductError, OSError, ValueError) as exc:
        return {
            "status": "UNAVAILABLE",
            "blocker": str(exc),
            "intended_inputs": intended,
        }
    return {
        "status": "USED_IN_RUN",
        "settlements": results,
        "provenance": (
            "Population is SOURCE-DERIVED for Neverwinter/Waterdeep and MODEL-PROPOSED "
            "for Forgedeep; food/coin stocks are explicit MODEL-PROPOSED simulation priors."
        ),
    }


def _brunnfeld_projection(
    *,
    seed: str,
    settlements: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    url = os.environ.get("BRUNNFELD_URL")
    total_population = sum(int(row["population"]) for row in settlements)
    villages = len(settlements)
    agents = max(7, min(200, math.ceil(total_population / villages / 1000)))
    product_seed = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16)
    intended = {
        "villages": villages,
        "agents_per_village": agents,
        "seed": product_seed,
        "represented_population": total_population,
    }
    if not url:
        return {
            "status": "UNAVAILABLE",
            "blocker": "BRUNNFELD_URL is not configured",
            "intended_input": intended,
        }
    try:
        client = BrunnfeldServiceClient(url)
        generated = client.generate_world(
            villages=villages,
            agents_per_village=agents,
            seed=product_seed,
        )
        snapshot = client.snapshot()
    except (BrunnfeldSidecarError, OSError, ValueError) as exc:
        return {
            "status": "UNAVAILABLE",
            "blocker": str(exc),
            "intended_input": intended,
        }
    return {
        "status": "USED_IN_RUN",
        "input": intended,
        "generation_result": generated,
        "product_villages": len(snapshot.villages),
        "economy_snapshots": len(snapshot.economy),
        "prices": snapshot.prices,
        "marketplace": snapshot.marketplace,
        "upstream_commit": snapshot.upstream_commit,
        "provenance": (
            "Representative agent micro-sample only: one Brunnfeld agent represents "
            "roughly 1,000 residents. Product output is not a literal population count."
        ),
    }


def build_parameterized_projection(
    *,
    seed: str,
    base_physical: Mapping[str, Any],
    source_path: Path = DEFAULT_SOURCE_INPUTS,
) -> dict[str, Any]:
    facts = _facts(source_path)
    resolution = resolve_catalog(seed=seed)
    params = resolve_map(seed=seed)

    settlements = _settlement_populations(
        base_physical=base_physical,
        params=params,
    )
    food = _food_projection(
        settlements=settlements,
        base_physical=base_physical,
        params=params,
    )
    labor = _labor_projection(
        settlements=settlements,
        base_physical=base_physical,
        params=params,
    )
    routes = _route_projection(
        base_physical=base_physical,
        params=params,
        facts=facts,
    )
    banking = _bank_projection(facts=facts, params=params)
    industry = _industry_projection(
        facts=facts,
        params=params,
        base_physical=base_physical,
    )

    products = dict(base_physical.get("products") or {})
    products["openttd"] = _openttd_projection(routes=routes)
    products["veloren"] = _veloren_projection(
        settlements=settlements,
        food=food,
    )
    products["brunnfeld"] = _brunnfeld_projection(
        seed=seed,
        settlements=settlements,
    )

    used_products = [
        name for name, row in products.items()
        if isinstance(row, Mapping) and row.get("status") == "USED_IN_RUN"
    ]

    return {
        "schema": "tnp.economy.parameterized-physical-projection/1",
        "canonical": False,
        "parameter_policy": resolution["policy"],
        "parameter_resolution": resolution,
        "parameter_debt_count": resolution["needs_enumeration_count"],
        "needs_enumeration": resolution["needs_enumeration"],
        "settlements": settlements,
        "food": food,
        "labor": labor,
        "routes": routes,
        "banking": banking,
        "industry": industry,
        "products": products,
        "products_used": used_products,
        "shock_incidence_prior": float(params["shocks.monthly_incidence"]),
        "note": (
            "This projection is allowed to use MODEL-PROPOSED parameters so the "
            "simulation can run. Those values remain explicit enumeration debt and "
            "are never promoted to campaign canon by execution."
        ),
    }
