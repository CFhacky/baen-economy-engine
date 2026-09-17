"""Behavior-level adaptations from inspected public simulation engines.

This module intentionally reimplements small economic invariants for Baen's
exact-Decimal, fail-closed engine. It does not copy GPL source or import the
upstream packages. Exact pinned sources and licenses live in
``docs/THIRD_PARTY_SOURCES.md``.

Adapted behaviors:
- Veloren: protect internal demand before external trade allocation.
- Brunnfeld Agentic World: available-to-promise excludes reservations.
- Unknown Horizons + FreeCol: distinguish bottleneck-feasible production from
  maximum production capacity.
- OpenTTD: final-delivery accounting pays only accepted cargo; subsidy is a
  separate adjustment rather than hidden inside base value.
- Mesa: scenario time is explicit and event ordering is deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Mapping

from .stockflow import InventoryPosition, Recipe, available_quantity

ZERO = Decimal(0)
ONE = Decimal(1)


class UpstreamAdaptationError(ValueError):
    """Invalid or ambiguous input to an upstream-informed adapter."""


def _decimal(value: object, label: str, *, minimum: Decimal = ZERO) -> Decimal:
    if type(value) is not Decimal or not value.is_finite():
        raise UpstreamAdaptationError(f"{label} must be a finite Decimal")
    if value < minimum:
        raise UpstreamAdaptationError(f"{label} cannot be below {minimum}")
    return value


@dataclass(frozen=True, slots=True)
class ExportAllocation:
    """Local-demand-first allocation for one commodity at one site."""

    on_hand: Decimal
    reserved: Decimal
    local_need: Decimal
    requested_export: Decimal
    route_capacity: Decimal
    protected_local: Decimal
    local_shortfall: Decimal
    exportable_after_local: Decimal
    dispatched_export: Decimal


def allocate_export_after_local_need(
    *,
    on_hand: Decimal,
    reserved: Decimal = ZERO,
    local_need: Decimal,
    requested_export: Decimal,
    route_capacity: Decimal,
) -> ExportAllocation:
    """Protect internal demand before external dispatch.

    Veloren's ``trade_at_site`` calculates internal demand and only exposes stock
    above that demand to trade. Brunnfeld's available-to-promise behavior also
    excludes reservations. Baen combines those ideas with stricter validation:
    reservations may not exceed physical on-hand stock and no shortage is hidden.
    """

    on_hand = _decimal(on_hand, "on-hand quantity")
    reserved = _decimal(reserved, "reserved quantity")
    local_need = _decimal(local_need, "local need")
    requested_export = _decimal(requested_export, "requested export")
    route_capacity = _decimal(route_capacity, "route capacity")
    if reserved > on_hand:
        raise UpstreamAdaptationError("reserved quantity exceeds on-hand stock")

    available = on_hand - reserved
    protected = min(local_need, available)
    shortfall = max(ZERO, local_need - available)
    exportable = max(ZERO, available - protected)
    dispatched = min(requested_export, route_capacity, exportable)
    return ExportAllocation(
        on_hand=on_hand,
        reserved=reserved,
        local_need=local_need,
        requested_export=requested_export,
        route_capacity=route_capacity,
        protected_local=protected,
        local_shortfall=shortfall,
        exportable_after_local=exportable,
        dispatched_export=dispatched,
    )


@dataclass(frozen=True, slots=True)
class ProductionCapacity:
    """Maximum-vs-feasible production with explicit bottlenecks."""

    recipe_id: str
    configured_limit_batches: Decimal
    labor_limit_batches: Decimal
    maximum_batches: Decimal
    input_limit_batches: Decimal
    feasible_batches: Decimal
    limiting_inputs: tuple[str, ...]

    def actual_for(self, requested_batches: Decimal) -> Decimal:
        requested_batches = _decimal(requested_batches, "requested production")
        return min(requested_batches, self.feasible_batches)


def production_capacity(
    recipe: Recipe,
    inventories: Iterable[InventoryPosition],
    *,
    site_labor_capacity: Decimal,
) -> ProductionCapacity:
    """Report maximum capacity separately from current feasible output.

    FreeCol stores actual and maximum production separately. Unknown Horizons
    calculates a production chain's final output at its bottleneck. Baen applies
    those concepts to an existing ``Recipe`` without importing either engine's
    game-specific coefficients.
    """

    if type(recipe) is not Recipe:
        raise UpstreamAdaptationError("recipe must be a concrete Recipe")
    labor = _decimal(site_labor_capacity, "site labor capacity")
    configured = recipe.max_batches
    if recipe.labor_per_batch == ZERO:
        labor_limit = configured
    else:
        labor_limit = labor / recipe.labor_per_batch
    maximum = min(configured, labor_limit)

    positions: dict[tuple[str, str], InventoryPosition] = {}
    for position in inventories:
        if type(position) is not InventoryPosition:
            raise UpstreamAdaptationError("inventories must contain InventoryPosition values")
        key = (position.site_id, position.commodity_id)
        if key in positions:
            raise UpstreamAdaptationError("duplicate inventory position")
        positions[key] = position

    input_capacities: list[tuple[str, Decimal]] = []
    for commodity_id, per_batch in recipe.inputs:
        position = positions.get((recipe.site_id, commodity_id))
        input_capacities.append((commodity_id, available_quantity(position) / per_batch))

    if input_capacities:
        input_limit = min(capacity for _, capacity in input_capacities)
    else:
        input_limit = maximum
    feasible = min(maximum, input_limit)
    limiting = tuple(sorted(
        commodity_id
        for commodity_id, capacity in input_capacities
        if capacity == feasible and feasible < maximum
    ))
    return ProductionCapacity(
        recipe_id=recipe.recipe_id,
        configured_limit_batches=configured,
        labor_limit_batches=labor_limit,
        maximum_batches=maximum,
        input_limit_batches=input_limit,
        feasible_batches=feasible,
        limiting_inputs=limiting,
    )


@dataclass(frozen=True, slots=True)
class DeliverySettlement:
    """Auditable final-delivery settlement for one shipment."""

    shipment_id: str
    dispatched_quantity: Decimal
    accepted_quantity: Decimal
    rejected_quantity: Decimal
    unit_value: Decimal
    base_revenue: Decimal
    subsidy_multiplier: Decimal
    subsidy_amount: Decimal
    total_revenue: Decimal
    distance_units: Decimal
    periods_in_transit: int


def settle_delivery(
    *,
    shipment_id: str,
    dispatched_quantity: Decimal,
    accepted_quantity: Decimal,
    unit_value: Decimal,
    distance_units: Decimal,
    periods_in_transit: int,
    subsidy_multiplier: Decimal = ONE,
) -> DeliverySettlement:
    """Settle accepted cargo and expose rejected cargo separately.

    OpenTTD's ``DeliverGoods`` distinguishes delivered/accepted cargo from cargo
    presented for delivery, records transit context, computes base revenue from
    accepted cargo, then applies subsidy. Baen keeps the same accounting boundary
    while requiring the campaign/scenario to supply its own unit value and subsidy
    multiplier instead of importing OpenTTD's balance constants.
    """

    if not isinstance(shipment_id, str) or not shipment_id.strip():
        raise UpstreamAdaptationError("shipment ID is required")
    dispatched = _decimal(dispatched_quantity, "dispatched quantity")
    accepted = _decimal(accepted_quantity, "accepted quantity")
    unit = _decimal(unit_value, "delivery unit value")
    distance = _decimal(distance_units, "delivery distance")
    subsidy = _decimal(subsidy_multiplier, "subsidy multiplier")
    if type(periods_in_transit) is not int or periods_in_transit < 0:
        raise UpstreamAdaptationError("periods in transit must be a non-negative integer")
    if accepted > dispatched:
        raise UpstreamAdaptationError("accepted quantity cannot exceed dispatched quantity")

    rejected = dispatched - accepted
    base = accepted * unit
    total = base * subsidy
    return DeliverySettlement(
        shipment_id=shipment_id,
        dispatched_quantity=dispatched,
        accepted_quantity=accepted,
        rejected_quantity=rejected,
        unit_value=unit,
        base_revenue=base,
        subsidy_multiplier=subsidy,
        subsidy_amount=total - base,
        total_revenue=total,
        distance_units=distance,
        periods_in_transit=periods_in_transit,
    )


@dataclass(frozen=True, slots=True, order=True)
class ScheduledEconomicEvent:
    """Deterministically ordered economic event at explicit scenario time."""

    time: Decimal
    priority: int
    event_id: str

    def __post_init__(self) -> None:
        _decimal(self.time, "event time")
        if type(self.priority) is not int:
            raise UpstreamAdaptationError("event priority must be an integer")
        if not isinstance(self.event_id, str) or not self.event_id.strip():
            raise UpstreamAdaptationError("event ID is required")


def events_due(
    events: Iterable[ScheduledEconomicEvent],
    *,
    current_time: Decimal,
    until: Decimal,
) -> tuple[ScheduledEconomicEvent, ...]:
    """Return deterministic due-event order without advancing campaign time.

    Mesa owns simulation time explicitly and drains scheduled events up to a
    requested boundary. This adapter only computes due order; the caller remains
    responsible for advancing an authorized scenario/campaign clock.
    """

    current = _decimal(current_time, "current time")
    end = _decimal(until, "end time")
    if end <= current:
        raise UpstreamAdaptationError("end time must be later than current time")
    materialized = tuple(events)
    if any(type(event) is not ScheduledEconomicEvent for event in materialized):
        raise UpstreamAdaptationError("events must be ScheduledEconomicEvent values")
    ids = [event.event_id for event in materialized]
    if len(ids) != len(set(ids)):
        raise UpstreamAdaptationError("duplicate scheduled event ID")
    return tuple(sorted(
        (event for event in materialized if current < event.time <= end),
        key=lambda event: (event.time, event.priority, event.event_id),
    ))
