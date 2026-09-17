"""Deterministic regional market allocation around the stock-flow kernel.

This module turns explicit, non-canonical supply offers and demand bids into a
monthly stock-flow plan.  The existing :mod:`baen_economy.stockflow` engine
remains responsible for production, inventory mutation, transit, loss,
consumption, shortages, bounded price response, and conservation.  The regional
layer adds deterministic sourcing across locations and readable trade receipts.

All fixture values entering this module are scenario inputs.  Nothing here can
advance the ``actual`` campaign timeline, post a ledger entry, or write Notion.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from typing import Iterable

from .domain import canonical_decimal
from .regional_transport import (
    RouteCostTerms,
    RouteUsageReceipt,
    dispatch_for_delivery,
    expected_transport_outcome,
    route_usage_receipt,
)
from .stockflow import (
    Commodity,
    EconomyModel,
    Need,
    ProductionOrder,
    Route,
    RunPlan,
    RunResult,
    ShipmentOrder,
    Snapshot,
    FlowKind,
    advance,
)


MARKET_MONTH_SCHEMA = "tnp.economy.regional-market-month/1"
ZERO = Decimal(0)
ONE = Decimal(1)


class RegionalMarketError(ValueError):
    """Raised when scenario inputs cannot produce a safe regional market run."""


def _new_market_context() -> Context:
    return Context(
        prec=40,
        rounding=ROUND_HALF_EVEN,
        Emin=-999999,
        Emax=999999,
        capitals=1,
        clamp=0,
    )


def _require_decimal(value: object, label: str) -> Decimal:
    if type(value) is not Decimal or not value.is_finite():
        raise RegionalMarketError(f"{label} must be a finite Decimal")
    return value


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise RegionalMarketError(f"{label} is required and must be trimmed")
    return value


@dataclass(frozen=True, slots=True, order=True)
class SupplyOffer:
    """Maximum stock one scenario seller makes available during the month."""

    offer_id: str
    seller_entity_id: str
    site_id: str
    commodity_id: str
    offered_quantity: Decimal
    source_ref: str
    authority: str = "scenario_input"
    canonical: bool = False

    def __post_init__(self) -> None:
        for value, label in (
            (self.offer_id, "supply-offer ID"),
            (self.seller_entity_id, "supply-offer seller entity ID"),
            (self.site_id, "supply-offer site ID"),
            (self.commodity_id, "supply-offer commodity ID"),
            (self.source_ref, "supply-offer source reference"),
        ):
            _require_text(value, label)
        quantity = _require_decimal(self.offered_quantity, "offered quantity")
        if quantity < ZERO:
            raise RegionalMarketError("offered quantity cannot be negative")
        if self.authority != "scenario_input" or self.canonical is not False:
            raise RegionalMarketError(
                "supply offers must remain non-canonical scenario inputs"
            )


@dataclass(frozen=True, slots=True, order=True)
class DemandBid:
    """One buyer's explicit monthly demand at one site."""

    demand_id: str
    buyer_entity_id: str
    site_id: str
    commodity_id: str
    quantity: Decimal
    source_ref: str
    reservation_price_gp_per_delivered_unit: Decimal | None = None
    priority: int = 100
    authority: str = "scenario_input"
    canonical: bool = False

    def __post_init__(self) -> None:
        for value, label in (
            (self.demand_id, "demand ID"),
            (self.buyer_entity_id, "demand buyer entity ID"),
            (self.site_id, "demand site ID"),
            (self.commodity_id, "demand commodity ID"),
            (self.source_ref, "demand source reference"),
        ):
            _require_text(value, label)
        quantity = _require_decimal(self.quantity, "demand quantity")
        if quantity <= ZERO:
            raise RegionalMarketError("demand quantity must be positive")
        if self.reservation_price_gp_per_delivered_unit is not None:
            reservation = _require_decimal(
                self.reservation_price_gp_per_delivered_unit,
                "demand reservation price",
            )
            if reservation <= ZERO:
                raise RegionalMarketError("demand reservation price must be positive")
        if type(self.priority) is not int:
            raise RegionalMarketError("demand priority must be an integer")
        if self.authority != "scenario_input" or self.canonical is not False:
            raise RegionalMarketError(
                "demand bids must remain non-canonical scenario inputs"
            )


@dataclass(frozen=True, slots=True, order=True)
class DemandReceipt:
    """Resolved current-month coverage, shortage, and local price response."""

    demand_id: str
    buyer_entity_id: str
    site_id: str
    commodity_id: str
    priority: int
    requested_quantity: Decimal
    consumed_quantity: Decimal
    shortage_quantity: Decimal
    price_before_gp_per_unit: Decimal
    price_after_gp_per_unit: Decimal
    reservation_price_gp_per_delivered_unit: Decimal | None
    disposition: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.demand_id, "demand-receipt ID"),
            (self.buyer_entity_id, "demand-receipt buyer ID"),
            (self.site_id, "demand-receipt site ID"),
            (self.commodity_id, "demand-receipt commodity ID"),
            (self.disposition, "demand-receipt disposition"),
        ):
            _require_text(value, label)
        if type(self.priority) is not int:
            raise RegionalMarketError("demand-receipt priority must be an integer")
        for value, label in (
            (self.requested_quantity, "requested demand"),
            (self.consumed_quantity, "consumed demand"),
            (self.shortage_quantity, "demand shortage"),
            (self.price_before_gp_per_unit, "price before"),
            (self.price_after_gp_per_unit, "price after"),
        ):
            _require_decimal(value, label)
            if value < ZERO:
                raise RegionalMarketError(f"{label} cannot be negative")
        if self.price_before_gp_per_unit == ZERO or self.price_after_gp_per_unit == ZERO:
            raise RegionalMarketError("market prices must be positive")
        with localcontext(_new_market_context()):
            reconciled_quantity = self.consumed_quantity + self.shortage_quantity
        if reconciled_quantity != self.requested_quantity:
            raise RegionalMarketError(
                "demand receipt must reconcile requested, consumed, and shortage"
            )
        if self.reservation_price_gp_per_delivered_unit is not None:
            _require_decimal(
                self.reservation_price_gp_per_delivered_unit,
                "demand-receipt reservation price",
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "demand_id": self.demand_id,
            "buyer_entity_id": self.buyer_entity_id,
            "site_id": self.site_id,
            "commodity_id": self.commodity_id,
            "priority": self.priority,
            "requested_quantity": canonical_decimal(self.requested_quantity),
            "consumed_quantity": canonical_decimal(self.consumed_quantity),
            "shortage_quantity": canonical_decimal(self.shortage_quantity),
            "price_before_gp_per_unit": canonical_decimal(
                self.price_before_gp_per_unit
            ),
            "price_after_gp_per_unit": canonical_decimal(
                self.price_after_gp_per_unit
            ),
            "reservation_price_gp_per_delivered_unit": (
                canonical_decimal(self.reservation_price_gp_per_delivered_unit)
                if self.reservation_price_gp_per_delivered_unit is not None
                else None
            ),
            "disposition": self.disposition,
        }


@dataclass(frozen=True, slots=True, order=True)
class TradeReceipt:
    """A priced local delivery or a dispatched cross-location trade."""

    trade_id: str
    demand_id: str
    supply_offer_id: str
    seller_entity_id: str
    buyer_entity_id: str
    carrier_entity_id: str | None
    seller_site_id: str
    buyer_site_id: str
    commodity_id: str
    route_id: str | None
    dispatched_quantity: Decimal
    expected_loss_quantity: Decimal
    delivered_quantity: Decimal
    goods_unit_price_gp: Decimal
    goods_value_gp: Decimal
    transport_unit_cost_gp: Decimal
    transport_cost_gp: Decimal
    buyer_total_gp: Decimal
    departure_period_index: int
    arrival_period_index: int
    delivery_status: str
    settlement_status: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.trade_id, "trade ID"),
            (self.demand_id, "trade demand ID"),
            (self.supply_offer_id, "trade supply-offer ID"),
            (self.seller_entity_id, "trade seller entity ID"),
            (self.buyer_entity_id, "trade buyer entity ID"),
            (self.seller_site_id, "trade seller site ID"),
            (self.buyer_site_id, "trade buyer site ID"),
            (self.commodity_id, "trade commodity ID"),
            (self.delivery_status, "trade delivery status"),
            (self.settlement_status, "trade settlement status"),
        ):
            _require_text(value, label)
        if self.route_id is not None:
            _require_text(self.route_id, "trade route ID")
        if self.carrier_entity_id is not None:
            _require_text(self.carrier_entity_id, "trade carrier entity ID")
        for value, label in (
            (self.dispatched_quantity, "trade dispatched quantity"),
            (self.expected_loss_quantity, "trade expected loss"),
            (self.delivered_quantity, "trade delivered quantity"),
            (self.goods_unit_price_gp, "trade goods unit price"),
            (self.goods_value_gp, "trade goods value"),
            (self.transport_unit_cost_gp, "trade transport unit cost"),
            (self.transport_cost_gp, "trade transport cost"),
            (self.buyer_total_gp, "trade buyer total"),
        ):
            _require_decimal(value, label)
            if value < ZERO:
                raise RegionalMarketError(f"{label} cannot be negative")
        if self.goods_unit_price_gp == ZERO:
            raise RegionalMarketError("trade goods unit price must be positive")
        with localcontext(_new_market_context()):
            reconciled_quantity = (
                self.expected_loss_quantity + self.delivered_quantity
            )
        if self.dispatched_quantity != reconciled_quantity:
            raise RegionalMarketError(
                "trade receipt must conserve dispatched quantity across loss and delivery"
            )
        with localcontext(_new_market_context()):
            expected_goods_value = self.dispatched_quantity * self.goods_unit_price_gp
            expected_transport_cost = (
                self.dispatched_quantity * self.transport_unit_cost_gp
            )
            expected_total = expected_goods_value + expected_transport_cost
        if self.goods_value_gp != expected_goods_value:
            raise RegionalMarketError("trade goods value does not match dispatched quantity")
        if self.transport_cost_gp != expected_transport_cost:
            raise RegionalMarketError("trade transport cost does not match dispatched quantity")
        if self.buyer_total_gp != expected_total:
            raise RegionalMarketError("trade buyer total does not reconcile")
        if (
            type(self.departure_period_index) is not int
            or type(self.arrival_period_index) is not int
            or self.departure_period_index < 1
            or self.arrival_period_index < self.departure_period_index
        ):
            raise RegionalMarketError("trade period indices are invalid")
        if self.route_id is None:
            if self.delivery_status != "delivered" or self.settlement_status != "settled_cash":
                raise RegionalMarketError("local trades must be delivered and cash-settled")
            if self.arrival_period_index != self.departure_period_index:
                raise RegionalMarketError("local trade must arrive in its departure period")
        else:
            if self.delivery_status != "in_transit" or self.settlement_status != "pending_delivery":
                raise RegionalMarketError(
                    "dispatched route trades must remain pending until delivery"
                )
            if self.arrival_period_index <= self.departure_period_index:
                raise RegionalMarketError("route trade must arrive after departure")

    def to_payload(self) -> dict[str, object]:
        return {
            "trade_id": self.trade_id,
            "demand_id": self.demand_id,
            "supply_offer_id": self.supply_offer_id,
            "seller_entity_id": self.seller_entity_id,
            "buyer_entity_id": self.buyer_entity_id,
            "carrier_entity_id": self.carrier_entity_id,
            "seller_site_id": self.seller_site_id,
            "buyer_site_id": self.buyer_site_id,
            "commodity_id": self.commodity_id,
            "route_id": self.route_id,
            "dispatched_quantity": canonical_decimal(self.dispatched_quantity),
            "expected_loss_quantity": canonical_decimal(
                self.expected_loss_quantity
            ),
            "delivered_quantity": canonical_decimal(self.delivered_quantity),
            "goods_unit_price_gp": canonical_decimal(self.goods_unit_price_gp),
            "goods_value_gp": canonical_decimal(self.goods_value_gp),
            "transport_unit_cost_gp": canonical_decimal(
                self.transport_unit_cost_gp
            ),
            "transport_cost_gp": canonical_decimal(self.transport_cost_gp),
            "buyer_total_gp": canonical_decimal(self.buyer_total_gp),
            "departure_period_index": self.departure_period_index,
            "arrival_period_index": self.arrival_period_index,
            "delivery_status": self.delivery_status,
            "settlement_status": self.settlement_status,
        }


@dataclass(frozen=True, slots=True)
class MarketMonthResult:
    """Accepted local result of one non-canonical regional market preview."""

    source_ref: str
    period_index: int
    campaign_date: str
    snapshot: Snapshot
    run_result: RunResult
    demand_receipts: tuple[DemandReceipt, ...]
    trade_receipts: tuple[TradeReceipt, ...]
    route_usage: tuple[RouteUsageReceipt, ...]
    authority: str = "scenario_input"
    canonical: bool = False

    def __post_init__(self) -> None:
        _require_text(self.source_ref, "market-result source reference")
        _require_text(self.campaign_date, "market-result campaign date")
        if type(self.period_index) is not int or self.period_index < 1:
            raise RegionalMarketError("market-result period index must be positive")
        if type(self.snapshot) is not Snapshot or type(self.run_result) is not RunResult:
            raise RegionalMarketError("market result requires stock-flow result objects")
        if self.snapshot != self.run_result.snapshot:
            raise RegionalMarketError("market snapshot must be the resolved run snapshot")
        for values, item_type, label in (
            (self.demand_receipts, DemandReceipt, "demand receipts"),
            (self.trade_receipts, TradeReceipt, "trade receipts"),
            (self.route_usage, RouteUsageReceipt, "route-usage receipts"),
        ):
            if type(values) is not tuple or any(type(item) is not item_type for item in values):
                raise RegionalMarketError(f"{label} must be an immutable typed tuple")
        if self.authority != "scenario_input" or self.canonical is not False:
            raise RegionalMarketError(
                "market results must remain non-canonical scenario outputs"
            )

    def to_payload(self) -> dict[str, object]:
        representative = _representative_demand(self.demand_receipts)
        representative_commodity = (
            representative.commodity_id if representative is not None else None
        )
        relevant_routes = tuple(
            item
            for item in self.route_usage
            if item.commodity_id == representative_commodity
        )
        quantity_moved = _sum_decimals(item.quantity_moved for item in relevant_routes)
        capacity = _sum_decimals(item.capacity for item in relevant_routes)
        shortage = _sum_decimals(
            item.shortage_quantity
            for item in self.demand_receipts
            if item.commodity_id == representative_commodity
        )
        demand_payloads = [item.to_payload() for item in self.demand_receipts]
        trade_payloads = [item.to_payload() for item in self.trade_receipts]
        route_payloads = [item.to_payload() for item in self.route_usage]
        return {
            "schema": MARKET_MONTH_SCHEMA,
            "authority": self.authority,
            "canonical": self.canonical,
            "campaign_time_advanced": False,
            "source_ref": self.source_ref,
            "period_index": self.period_index,
            "campaign_date": self.campaign_date,
            "transport": {
                "commodity_id": representative_commodity,
                "quantity_moved": canonical_decimal(quantity_moved),
                "capacity": canonical_decimal(capacity),
                "route_usage": route_payloads,
            },
            "market": {
                "representative_demand_id": (
                    representative.demand_id if representative is not None else None
                ),
                "commodity_id": representative_commodity,
                "shortage_quantity": canonical_decimal(shortage),
                "price_before": (
                    canonical_decimal(representative.price_before_gp_per_unit)
                    if representative is not None
                    else None
                ),
                "price_after": (
                    canonical_decimal(representative.price_after_gp_per_unit)
                    if representative is not None
                    else None
                ),
                "demand_receipts": demand_payloads,
            },
            "demand_receipts": demand_payloads,
            "trade_receipts": trade_payloads,
            "route_usage": route_payloads,
            "next_market_state": _snapshot_payload(self.snapshot),
            "conservation": [
                {
                    "commodity_id": commodity_id,
                    "residual_quantity": canonical_decimal(residual),
                }
                for commodity_id, residual in self.run_result.conservation
            ],
            "ledger_postings_created": 0,
            "notion_writes_attempted": 0,
        }


@dataclass(frozen=True, slots=True)
class _PlannedRouteTrade:
    shipment_id: str
    demand: DemandBid
    offer: SupplyOffer
    route_id: str
    dispatched_quantity: Decimal


def simulate_market_month(
    model: EconomyModel,
    opening: Snapshot,
    *,
    period_index: int,
    campaign_ordinal: int,
    campaign_date: str,
    supply_offers: tuple[SupplyOffer, ...],
    demands: tuple[DemandBid, ...],
    route_costs: tuple[RouteCostTerms, ...],
    source_ref: str,
    production_orders: tuple[ProductionOrder, ...] = (),
) -> MarketMonthResult:
    """Resolve one deterministic, non-canonical regional market month.

    A diagnostic kernel run first identifies stock left after production and
    local needs.  Only that remainder can be exported, which prevents market
    allocation from starving equal-period local consumption.  The final kernel
    run then performs the planned dispatches and revalidates all conservation and
    capacity invariants.
    """

    with localcontext(_new_market_context()):
        return _simulate_market_month(
            model,
            opening,
            period_index=period_index,
            campaign_ordinal=campaign_ordinal,
            campaign_date=campaign_date,
            supply_offers=supply_offers,
            demands=demands,
            route_costs=route_costs,
            source_ref=source_ref,
            production_orders=production_orders,
        )


def _simulate_market_month(
    model: EconomyModel,
    opening: Snapshot,
    *,
    period_index: int,
    campaign_ordinal: int,
    campaign_date: str,
    supply_offers: tuple[SupplyOffer, ...],
    demands: tuple[DemandBid, ...],
    route_costs: tuple[RouteCostTerms, ...],
    source_ref: str,
    production_orders: tuple[ProductionOrder, ...],
) -> MarketMonthResult:

    if type(model) is not EconomyModel or type(opening) is not Snapshot:
        raise RegionalMarketError("market simulation requires an economy model and snapshot")
    if opening.timeline_id == "actual":
        raise RegionalMarketError(
            "regional scenario inputs cannot mutate the actual campaign timeline"
        )
    if type(period_index) is not int or period_index < 1:
        raise RegionalMarketError("market period index must be positive")
    if type(campaign_ordinal) is not int:
        raise RegionalMarketError("market campaign ordinal must be an integer")
    _require_text(campaign_date, "market campaign date")
    _require_text(source_ref, "market source reference")
    for values, item_type, label in (
        (supply_offers, SupplyOffer, "supply offers"),
        (demands, DemandBid, "demand bids"),
        (route_costs, RouteCostTerms, "route costs"),
        (production_orders, ProductionOrder, "production orders"),
    ):
        if type(values) is not tuple or any(type(item) is not item_type for item in values):
            raise RegionalMarketError(f"{label} must be an immutable typed tuple")

    model.validate_snapshot(opening)
    commodities = {item.commodity_id: item for item in model.commodities}
    sites = {item.site_id for item in model.sites}
    routes = {item.route_id: item for item in model.routes}
    offers = tuple(sorted(supply_offers))
    demand_bids = tuple(sorted(demands, key=_demand_sort_key))
    costs = tuple(sorted(route_costs))
    _require_unique((item.offer_id for item in offers), "supply-offer")
    _require_unique((item.demand_id for item in demand_bids), "demand")
    _require_unique((item.route_id for item in costs), "route-cost")

    for offer in offers:
        if offer.site_id not in sites or offer.commodity_id not in commodities:
            raise RegionalMarketError(
                f"supply offer {offer.offer_id} references an unknown site or commodity"
            )
    for demand in demand_bids:
        if demand.site_id not in sites or demand.commodity_id not in commodities:
            raise RegionalMarketError(
                f"demand {demand.demand_id} references an unknown site or commodity"
            )
        if not commodities[demand.commodity_id].market_price_enabled:
            raise RegionalMarketError(
                f"demand {demand.demand_id} uses a commodity without tracked market price"
            )
    terms_by_route = {item.route_id: item for item in costs}
    for route_id in terms_by_route:
        if route_id not in routes:
            raise RegionalMarketError(f"route costs reference unknown route: {route_id}")

    admitted_demands = tuple(
        demand
        for demand in demand_bids
        if _demand_is_admitted(model, opening, demand)
    )
    needs = tuple(
        Need(
            site_id=item.site_id,
            commodity_id=item.commodity_id,
            requested_quantity=item.quantity,
            priority=item.priority,
        )
        for item in admitted_demands
    )
    ordered_production = tuple(
        sorted(
            production_orders,
            key=lambda item: (
                item.recipe_id,
                item.requested_batches,
                item.authorizing_event_id or "",
            ),
        )
    )
    diagnostic = advance(
        model,
        opening,
        RunPlan(
            period_index=period_index,
            campaign_ordinal=campaign_ordinal,
            campaign_date=campaign_date,
            production_orders=ordered_production,
            needs=needs,
        ),
    )
    diagnostic_demands = _allocate_demand_receipts(
        model,
        opening,
        diagnostic,
        demand_bids,
        admitted_demands,
    )

    exportable = defaultdict(Decimal)
    for position in diagnostic.snapshot.inventories:
        exportable[(position.site_id, position.commodity_id)] += (
            position.quantity - position.reserved_quantity
        )
    offer_budgets: dict[str, Decimal] = {}
    for offer in offers:
        key = (offer.site_id, offer.commodity_id)
        budget = min(offer.offered_quantity, exportable[key])
        offer_budgets[offer.offer_id] = budget
        exportable[key] -= budget

    route_remaining = {
        route.route_id: route.capacity_per_period for route in model.routes
    }
    planned: list[_PlannedRouteTrade] = []
    shipment_orders: list[ShipmentOrder] = []
    sequence = 0
    diagnostic_by_id = {item.demand_id: item for item in diagnostic_demands}
    for demand in demand_bids:
        receipt = diagnostic_by_id[demand.demand_id]
        remaining_delivery = receipt.shortage_quantity
        if remaining_delivery == ZERO:
            continue
        candidates: list[tuple[Decimal, int, str, str, SupplyOffer]] = []
        for offer in offers:
            if offer_budgets[offer.offer_id] == ZERO:
                continue
            for route in model.routes:
                terms = terms_by_route.get(route.route_id)
                if terms is None:
                    continue
                if (
                    route.origin_site_id != offer.site_id
                    or route.destination_site_id != demand.site_id
                    or route.commodity_id != demand.commodity_id
                    or offer.commodity_id != demand.commodity_id
                ):
                    continue
                landed_price = _landed_price(
                    model,
                    opening,
                    route,
                    terms,
                )
                if (
                    demand.reservation_price_gp_per_delivered_unit is not None
                    and landed_price > demand.reservation_price_gp_per_delivered_unit
                ):
                    continue
                candidates.append(
                    (
                        landed_price,
                        terms.allocation_priority,
                        route.route_id,
                        offer.offer_id,
                        offer,
                    )
                )
        for _, _, route_id, _, offer in sorted(candidates):
            if remaining_delivery == ZERO:
                break
            route = routes[route_id]
            available = offer_budgets[offer.offer_id]
            remaining_route = route_remaining[route_id]
            dispatched = dispatch_for_delivery(
                route,
                remaining_delivery,
                available_stock=available,
                remaining_capacity=remaining_route,
            )
            if dispatched == ZERO:
                continue
            _, delivered = expected_transport_outcome(route, dispatched)
            sequence += 1
            shipment_id = f"shipment:market:{period_index:08d}:{sequence:06d}"
            shipment_orders.append(
                ShipmentOrder(
                    shipment_id=shipment_id,
                    route_id=route.route_id,
                    commodity_id=route.commodity_id,
                    requested_quantity=dispatched,
                    source_ref=source_ref,
                )
            )
            planned.append(
                _PlannedRouteTrade(
                    shipment_id=shipment_id,
                    demand=demand,
                    offer=offer,
                    route_id=route.route_id,
                    dispatched_quantity=dispatched,
                )
            )
            offer_budgets[offer.offer_id] -= dispatched
            route_remaining[route.route_id] -= dispatched
            remaining_delivery = max(ZERO, remaining_delivery - delivered)

    resolved = advance(
        model,
        opening,
        RunPlan(
            period_index=period_index,
            campaign_ordinal=campaign_ordinal,
            campaign_date=campaign_date,
            production_orders=ordered_production,
            shipment_orders=tuple(shipment_orders),
            needs=needs,
        ),
    )
    shipment_results = {item.shipment_id: item for item in resolved.shipments}
    for item in planned:
        result = shipment_results[item.shipment_id]
        if result.dispatched_quantity != item.dispatched_quantity:
            raise RegionalMarketError(
                "prevalidated market dispatch did not match stock-flow resolution"
            )

    demand_receipts = _allocate_demand_receipts(
        model,
        opening,
        resolved,
        demand_bids,
        admitted_demands,
    )
    cross_trades = _cross_trade_receipts(
        model,
        opening,
        planned,
        routes,
        terms_by_route,
        period_index,
    )
    dispatched_by_offer = defaultdict(Decimal)
    for item in planned:
        dispatched_by_offer[item.offer.offer_id] += item.dispatched_quantity
    local_trades = _local_trade_receipts(
        model,
        opening,
        demand_receipts,
        offers,
        dispatched_by_offer,
        period_index,
    )
    trades = tuple(sorted((*cross_trades, *local_trades)))

    moved_by_route = defaultdict(Decimal)
    for item in planned:
        moved_by_route[item.route_id] += item.dispatched_quantity
    usage = tuple(
        route_usage_receipt(
            routes[route_id],
            terms_by_route[route_id],
            quantity_moved=quantity,
            departure_period_index=period_index,
        )
        for route_id, quantity in sorted(moved_by_route.items())
    )
    return MarketMonthResult(
        source_ref=source_ref,
        period_index=period_index,
        campaign_date=campaign_date,
        snapshot=resolved.snapshot,
        run_result=resolved,
        demand_receipts=demand_receipts,
        trade_receipts=trades,
        route_usage=usage,
    )


def _demand_sort_key(item: DemandBid) -> tuple[int, str, str, str, str]:
    return (
        item.priority,
        item.site_id,
        item.commodity_id,
        item.demand_id,
        item.buyer_entity_id,
    )


def _require_unique(values: Iterable[str], label: str) -> None:
    materialized = list(values)
    if len(materialized) != len(set(materialized)):
        raise RegionalMarketError(f"duplicate {label} identifier")


def _commodity(model: EconomyModel, commodity_id: str) -> Commodity:
    for item in model.commodities:
        if item.commodity_id == commodity_id:
            return item
    raise RegionalMarketError(f"unknown commodity: {commodity_id}")


def _price(
    model: EconomyModel,
    snapshot: Snapshot,
    site_id: str,
    commodity_id: str,
) -> Decimal:
    for item in snapshot.prices:
        if item.site_id == site_id and item.commodity_id == commodity_id:
            return item.amount
    commodity = _commodity(model, commodity_id)
    if not commodity.market_price_enabled or commodity.base_price is None:
        raise RegionalMarketError(
            f"commodity {commodity_id} has no tracked market price"
        )
    return commodity.base_price


def _demand_is_admitted(
    model: EconomyModel,
    opening: Snapshot,
    demand: DemandBid,
) -> bool:
    reservation = demand.reservation_price_gp_per_delivered_unit
    return reservation is None or _price(
        model, opening, demand.site_id, demand.commodity_id
    ) <= reservation


def _allocate_demand_receipts(
    model: EconomyModel,
    opening: Snapshot,
    result: RunResult,
    all_demands: tuple[DemandBid, ...],
    admitted_demands: tuple[DemandBid, ...],
) -> tuple[DemandReceipt, ...]:
    admitted_ids = {item.demand_id for item in admitted_demands}
    groups: defaultdict[tuple[int, str, str], list[DemandBid]] = defaultdict(list)
    for item in admitted_demands:
        groups[(item.priority, item.site_id, item.commodity_id)].append(item)
    sorted_keys = sorted(groups)
    if len(result.needs) != len(sorted_keys):
        raise RegionalMarketError("stock-flow need receipts do not match market demands")
    consumed_by_demand = defaultdict(Decimal)
    for key, need_result in zip(sorted_keys, result.needs, strict=True):
        priority, site_id, commodity_id = key
        if (
            need_result.site_id != site_id
            or need_result.commodity_id != commodity_id
        ):
            raise RegionalMarketError("stock-flow need ordering did not replay deterministically")
        remaining_consumed = need_result.consumed_quantity
        for demand in sorted(groups[key], key=_demand_sort_key):
            consumed = min(demand.quantity, remaining_consumed)
            consumed_by_demand[demand.demand_id] = consumed
            remaining_consumed -= consumed
        if remaining_consumed != ZERO:
            raise RegionalMarketError("stock-flow consumed quantity could not be allocated")

    receipts: list[DemandReceipt] = []
    for demand in all_demands:
        before = _price(model, opening, demand.site_id, demand.commodity_id)
        admitted = demand.demand_id in admitted_ids
        consumed = consumed_by_demand[demand.demand_id] if admitted else ZERO
        after = (
            _price(model, result.snapshot, demand.site_id, demand.commodity_id)
            if admitted
            else before
        )
        shortage = demand.quantity - consumed
        if not admitted:
            disposition = "reservation_price_below_local_market"
        elif shortage > ZERO:
            disposition = "partially_filled" if consumed > ZERO else "unfilled"
        else:
            disposition = "filled"
        receipts.append(
            DemandReceipt(
                demand_id=demand.demand_id,
                buyer_entity_id=demand.buyer_entity_id,
                site_id=demand.site_id,
                commodity_id=demand.commodity_id,
                priority=demand.priority,
                requested_quantity=demand.quantity,
                consumed_quantity=consumed,
                shortage_quantity=shortage,
                price_before_gp_per_unit=before,
                price_after_gp_per_unit=after,
                reservation_price_gp_per_delivered_unit=(
                    demand.reservation_price_gp_per_delivered_unit
                ),
                disposition=disposition,
            )
        )
    return tuple(sorted(receipts))


def _landed_price(
    model: EconomyModel,
    opening: Snapshot,
    route: Route,
    terms: RouteCostTerms,
) -> Decimal:
    origin_site_id = route.origin_site_id
    commodity_id = route.commodity_id
    loss_rate = route.loss_rate
    with localcontext(_new_market_context()) as context:
        dispatched_unit_cost = (
            _price(model, opening, origin_site_id, commodity_id)
            + terms.transport_cost_gp_per_dispatched_unit
        )
        return context.divide(dispatched_unit_cost, ONE - loss_rate)


def _cross_trade_receipts(
    model: EconomyModel,
    opening: Snapshot,
    planned: list[_PlannedRouteTrade],
    routes: dict[str, Route],
    terms_by_route: dict[str, RouteCostTerms],
    period_index: int,
) -> tuple[TradeReceipt, ...]:
    receipts: list[TradeReceipt] = []
    for item in planned:
        route = routes[item.route_id]
        terms = terms_by_route[item.route_id]
        loss, delivered = expected_transport_outcome(
            route, item.dispatched_quantity
        )
        unit_price = _price(
            model, opening, route.origin_site_id, route.commodity_id
        )
        with localcontext(_new_market_context()):
            goods_value = item.dispatched_quantity * unit_price
            transport_cost = (
                item.dispatched_quantity
                * terms.transport_cost_gp_per_dispatched_unit
            )
            buyer_total = goods_value + transport_cost
        receipts.append(
            TradeReceipt(
                trade_id=f"trade:{item.shipment_id}",
                demand_id=item.demand.demand_id,
                supply_offer_id=item.offer.offer_id,
                seller_entity_id=item.offer.seller_entity_id,
                buyer_entity_id=item.demand.buyer_entity_id,
                carrier_entity_id=terms.carrier_entity_id,
                seller_site_id=item.offer.site_id,
                buyer_site_id=item.demand.site_id,
                commodity_id=item.demand.commodity_id,
                route_id=route.route_id,
                dispatched_quantity=item.dispatched_quantity,
                expected_loss_quantity=loss,
                delivered_quantity=delivered,
                goods_unit_price_gp=unit_price,
                goods_value_gp=goods_value,
                transport_unit_cost_gp=(
                    terms.transport_cost_gp_per_dispatched_unit
                ),
                transport_cost_gp=transport_cost,
                buyer_total_gp=buyer_total,
                departure_period_index=period_index,
                arrival_period_index=period_index + route.travel_periods,
                delivery_status="in_transit",
                settlement_status="pending_delivery",
            )
        )
    return tuple(receipts)


def _local_trade_receipts(
    model: EconomyModel,
    opening: Snapshot,
    demands: tuple[DemandReceipt, ...],
    offers: tuple[SupplyOffer, ...],
    dispatched_by_offer: dict[str, Decimal],
    period_index: int,
) -> tuple[TradeReceipt, ...]:
    offer_remaining = {
        item.offer_id: max(
            ZERO,
            item.offered_quantity - dispatched_by_offer[item.offer_id],
        )
        for item in offers
    }
    receipts: list[TradeReceipt] = []
    sequence = 0
    for demand in sorted(demands):
        remaining = demand.consumed_quantity
        if remaining == ZERO:
            continue
        candidates = sorted(
            item
            for item in offers
            if item.site_id == demand.site_id
            and item.commodity_id == demand.commodity_id
            and item.seller_entity_id != demand.buyer_entity_id
            and offer_remaining[item.offer_id] > ZERO
        )
        for offer in candidates:
            if remaining == ZERO:
                break
            delivered = min(remaining, offer_remaining[offer.offer_id])
            if delivered == ZERO:
                continue
            unit_price = _price(
                model, opening, demand.site_id, demand.commodity_id
            )
            with localcontext(_new_market_context()):
                goods_value = delivered * unit_price
            sequence += 1
            receipts.append(
                TradeReceipt(
                    trade_id=f"trade:local:{period_index:08d}:{sequence:06d}",
                    demand_id=demand.demand_id,
                    supply_offer_id=offer.offer_id,
                    seller_entity_id=offer.seller_entity_id,
                    buyer_entity_id=demand.buyer_entity_id,
                    carrier_entity_id=None,
                    seller_site_id=offer.site_id,
                    buyer_site_id=demand.site_id,
                    commodity_id=demand.commodity_id,
                    route_id=None,
                    dispatched_quantity=delivered,
                    expected_loss_quantity=ZERO,
                    delivered_quantity=delivered,
                    goods_unit_price_gp=unit_price,
                    goods_value_gp=goods_value,
                    transport_unit_cost_gp=ZERO,
                    transport_cost_gp=ZERO,
                    buyer_total_gp=goods_value,
                    departure_period_index=period_index,
                    arrival_period_index=period_index,
                    delivery_status="delivered",
                    settlement_status="settled_cash",
                )
            )
            offer_remaining[offer.offer_id] -= delivered
            remaining -= delivered
    return tuple(receipts)


def _representative_demand(
    receipts: tuple[DemandReceipt, ...],
) -> DemandReceipt | None:
    if not receipts:
        return None
    return min(
        receipts,
        key=lambda item: (
            -item.shortage_quantity,
            item.priority,
            item.demand_id,
        ),
    )


def _sum_decimals(values: Iterable[Decimal]) -> Decimal:
    with localcontext(_new_market_context()):
        total = ZERO
        for value in values:
            total += _require_decimal(value, "market summary quantity")
        return total


def _snapshot_payload(snapshot: Snapshot) -> dict[str, object]:
    return {
        "snapshot_id": snapshot.snapshot_id,
        "state_hash": snapshot.state_hash,
        "timeline_id": snapshot.timeline_id,
        "period_index": snapshot.period_index,
        "campaign_ordinal": snapshot.campaign_ordinal,
        "campaign_date": snapshot.campaign_date,
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
                "price_gp_per_unit": canonical_decimal(item.amount),
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
                "dispatched_quantity": canonical_decimal(item.quantity),
                "arrival_period_index": item.arrival_period_index,
                "loss_rate": canonical_decimal(item.loss_rate),
            }
            for item in snapshot.transit
        ],
    }
