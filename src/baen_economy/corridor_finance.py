"""Corridor land-bank, internal transport, and NCF lending calculations.

This module performs arithmetic on source/user-ruled inputs only. It does not
invent parcel prices, title geometry, reserve ratios, fleet counts, or loan terms.
"""
from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AUTHORITY = PROJECT_ROOT / "recovery/CORRIDOR_FINANCE_AUTHORITY_2026-09-18.json"

class CorridorFinanceError(ValueError):
    pass

def _load(path: Path = DEFAULT_AUTHORITY) -> dict[str, Any]:
    try:
        payload=json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CorridorFinanceError(f"cannot read corridor finance authority: {exc}") from exc
    if payload.get("schema")!="tnp.economy.corridor-finance-authority/1":
        raise CorridorFinanceError("unsupported corridor finance authority schema")
    return payload

def _index(rows: object) -> dict[str, Mapping[str, Any]]:
    if not isinstance(rows,list):
        raise CorridorFinanceError("authority rows must be a list")
    result={}
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get("key"),str):
            raise CorridorFinanceError("malformed authority row")
        result[row["key"]]=row
    return result

def corridor_land_bank_summary(path: Path = DEFAULT_AUTHORITY) -> dict[str, Any]:
    data=_load(path)
    rules=_index(data["user_rules"])
    facts=_index(data["source_observations"])
    half=Decimal(str(rules["arterial.land_bank.half_width_each_side_miles"]["value"]))
    miles=Decimal(str(facts["arterial.operational_network_miles_lower_bound"]["value"]))
    full_width=half*2
    square_miles=miles*full_width
    gross_acres=square_miles*Decimal("640")
    return {
        "status":"PARTIAL_USER_RULED",
        "beneficial_owner":"Northern Crown Financial / NCF-controlled shells and subsidiaries",
        "half_width_each_side_miles":str(half),
        "full_corridor_width_miles":str(full_width),
        "operational_network_miles_lower_bound":str(miles),
        "gross_corridor_square_miles_lower_bound":str(square_miles),
        "gross_corridor_acres_lower_bound":str(gross_acres),
        "legacy_direct_arterial_acres_lower_bound":facts["arterial.legacy_direct_owned_acres"]["value"],
        "authority":"USER-RULED + SOURCE-DERIVED arithmetic",
        "not_actual_titled_acreage":True,
        "reason":"Gross corridor envelope is calculable now; consolidated titled acres require de-overlapped segment geometry and title reconciliation."
    }

def internal_transport_summary(path: Path = DEFAULT_AUTHORITY) -> dict[str, Any]:
    data=_load(path)
    rules=_index(data["user_rules"])
    facts=_index(data["source_observations"])
    payload_tons=Decimal(str(facts["stonebearer.payload_lb"]["value"]))/Decimal("2000")
    fleet=Decimal(str(facts["stonebearer.brickworks_allocated_units"]["value"]))
    trips_min=Decimal(str(facts["stonebearer.short_haul_trips_per_day_min"]["value"]))
    trips_max=Decimal(str(facts["stonebearer.short_haul_trips_per_day_max"]["value"]))
    return {
        "status":"PARTIAL_SOURCE_BACKED",
        "external_sales":rules["transport.internal_vehicle.external_sales"]["value"],
        "earthmover_jeep_road_configuration":rules["transport.earthmover.jeep_road_configuration"]["value"],
        "stonebearer_payload_tons":str(payload_tons),
        "brickworks_allocated_stonebearers":int(fleet),
        "brickworks_short_haul_capacity_tons_per_day_min":str(payload_tons*fleet*trips_min),
        "brickworks_short_haul_capacity_tons_per_day_max":str(payload_tons*fleet*trips_max),
        "loaded_speed_mph":facts["stonebearer.loaded_speed_mph"]["value"],
        "empty_speed_mph":facts["stonebearer.empty_speed_mph"]["value"],
        "roadrider_dedicated_line":{
            "cargo_lb":facts["roadrider.cargo_lb"]["value"],
            "road_speed_mph":facts["roadrider.road_speed_mph"]["value"],
            "core_endurance_hours":facts["roadrider.core_endurance_hours"]["value"],
            "initial_units_per_month":facts["roadrider.initial_production_units_per_month"]["value"],
            "mature_units_per_month":facts["roadrider.mature_production_units_per_month"]["value"],
        },
        "unresolved":"Empire-wide current earthmover count/build rate and route-specific assignment remain to be recovered; do not multiply the four-unit Brickworks allocation into a whole-empire fleet."
    }

def ncf_lending_summary(path: Path = DEFAULT_AUTHORITY) -> dict[str, Any]:
    data=_load(path)
    facts=_index(data["source_observations"])
    return {
        "status":"PARTIAL_SOURCE_BACKED",
        "active_loan_principal_gp":facts["ncf.active_loan_portfolio_gp"]["value"],
        "monthly_ncf_revenue_gp":facts["ncf.monthly_revenue_gp"]["value"],
        "rate_anchors":[
            {
                "kind":"secured staged facility",
                "annual_rate_pct":facts["ncf.rate_anchor.snowfall_secured_facility_pct"]["value"],
                "status":"approved_not_drawn_day_7_hammer",
            },
            {
                "kind":"voyage finance / cargo-rights collateral",
                "annual_rate_pct":facts["ncf.rate_anchor.swiftfingers_voyage_pct"]["value"],
                "status":"active_good_standing",
            }
        ],
        "do_not_infer_average_apr":True,
        "reason":"NCF's 22,000 gp/month aggregate revenue contains non-interest banking services and cannot be divided by the 2.3M loan book as if all revenue were interest."
    }

def corridor_finance_snapshot(path: Path = DEFAULT_AUTHORITY) -> dict[str, Any]:
    data=_load(path)
    return {
        "schema":"tnp.economy.corridor-finance-snapshot/1",
        "campaign_boundary":data["campaign_boundary"],
        "land_bank":corridor_land_bank_summary(path),
        "internal_transport":internal_transport_summary(path),
        "ncf_lending":ncf_lending_summary(path),
        "unresolved":data["unresolved"],
        "canonical":False,
        "notion_writes":0,
        "campaign_time_advanced":False,
    }
