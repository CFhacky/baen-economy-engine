"""Runnable, explicitly non-canonical two-period economy demonstration."""

from __future__ import annotations

from decimal import Decimal
import json

from .stockflow import (
    Commodity,
    EconomyModel,
    Need,
    ProductionOrder,
    Recipe,
    Route,
    RunPlan,
    ShipmentOrder,
    Site,
    advance,
    initial_snapshot,
)


D = Decimal


def run_synthetic_normal_month() -> dict[str, object]:
    """Run a deterministic two-period miniature without asserting campaign canon."""

    model = EconomyModel(
        commodities=(Commodity("commodity:grain", "Grain", "ton", D("50")),),
        sites=(
            Site("site:source-farm", "Synthetic source farm", D("10")),
            Site("site:relief-town", "Synthetic relief town", D("5")),
        ),
        recipes=(
            Recipe(
                "recipe:grain-harvest",
                "site:source-farm",
                "entity:synthetic-farm",
                (),
                (("commodity:grain", D("100")),),
                D("10"),
                D("1"),
            ),
        ),
        routes=(
            Route(
                "route:farm-town",
                "site:source-farm",
                "site:relief-town",
                "commodity:grain",
                D("50"),
                1,
                D("0"),
            ),
        ),
    )
    opening = initial_snapshot(
        model,
        timeline_id="acceptance:synthetic-normal-month",
        campaign_ordinal=0,
        campaign_date="Synthetic opening",
        ruleset_version="economy-0.1.0",
    )
    dispatch = advance(
        model,
        opening,
        RunPlan(
            1,
            1,
            "Synthetic period 1",
            production_orders=(ProductionOrder("recipe:grain-harvest", D("1")),),
            shipment_orders=(
                ShipmentOrder(
                    "shipment:synthetic-grain-1",
                    "route:farm-town",
                    "commodity:grain",
                    D("80"),
                    "fixture:synthetic-normal-month",
                ),
            ),
            needs=(Need("site:source-farm", "commodity:grain", D("20")),),
        ),
    )
    arrival = advance(
        model,
        dispatch.snapshot,
        RunPlan(
            2,
            2,
            "Synthetic period 2",
            needs=(Need("site:relief-town", "commodity:grain", D("60")),),
        ),
    )
    town_need = arrival.needs[0]
    town_price = next(
        price.amount
        for price in arrival.snapshot.prices
        if price.site_id == "site:relief-town" and price.commodity_id == "commodity:grain"
    )
    return {
        "schema": "tnp.economy.demo/1",
        "canonical": False,
        "timeline_id": opening.timeline_id,
        "opening_snapshot": opening.snapshot_id,
        "dispatch_snapshot": dispatch.snapshot.snapshot_id,
        "closing_snapshot": arrival.snapshot.snapshot_id,
        "period_1": {
            "produced_tons": "100",
            "requested_shipment_tons": "80",
            "dispatched_tons": str(dispatch.shipments[0].dispatched_quantity),
            "route_shortfall_tons": str(dispatch.shipments[0].shortfall_quantity),
            "source_consumption_tons": str(dispatch.needs[0].consumed_quantity),
            "in_transit_tons": str(dispatch.snapshot.transit[0].quantity),
            "conservation_residual_tons": str(dict(dispatch.conservation)["commodity:grain"]),
        },
        "period_2": {
            "requested_relief_tons": str(town_need.requested_quantity),
            "delivered_and_consumed_tons": str(town_need.consumed_quantity),
            "shortage_tons": str(town_need.shortage_quantity),
            "closing_price_gp_per_ton": str(town_price.quantize(D("0.0001"))),
            "conservation_residual_tons": str(dict(arrival.conservation)["commodity:grain"]),
        },
    }


def main() -> int:
    print(json.dumps(run_synthetic_normal_month(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
