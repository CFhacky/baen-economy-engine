"""Costed transport receipts layered over the stock-flow route kernel.

The stock-flow engine remains the sole authority for inventory mutation, route
capacity, transit timing, and physical loss.  This module adds the market-facing
cost terms and readable receipts that the kernel deliberately does not model.

The allocation vocabulary is informed by common logistics patterns used by
settlement/economy games such as Unknown Horizons and Veloren.  No upstream code
is copied or translated here.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext

from .domain import canonical_decimal
from .stockflow import Route


ZERO = Decimal(0)
ONE = Decimal(1)


class RegionalTransportError(ValueError):
    """Raised when costed route input cannot produce a safe receipt."""


def _new_transport_context() -> Context:
    """Mirror the stock-flow arithmetic policy without using ambient context."""

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
        raise RegionalTransportError(f"{label} must be a finite Decimal")
    return value


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise RegionalTransportError(f"{label} is required and must be trimmed")
    return value


@dataclass(frozen=True, slots=True, order=True)
class RouteCostTerms:
    """Scenario cost overlay for one existing physical route.

    Cost is assessed on dispatched quantity.  This makes the party bearing
    transit loss explicit: goods lost en route still consumed carriage capacity
    and therefore still incur transport cost.
    """

    route_id: str
    transport_cost_gp_per_dispatched_unit: Decimal
    allocation_priority: int = 100
    carrier_entity_id: str | None = None
    authority: str = "scenario_input"
    canonical: bool = False

    def __post_init__(self) -> None:
        _require_text(self.route_id, "route-cost route ID")
        cost = _require_decimal(
            self.transport_cost_gp_per_dispatched_unit,
            "transport cost per dispatched unit",
        )
        if cost < ZERO:
            raise RegionalTransportError("transport cost cannot be negative")
        if self.carrier_entity_id is not None:
            _require_text(self.carrier_entity_id, "route carrier entity ID")
        if type(self.allocation_priority) is not int:
            raise RegionalTransportError("route allocation priority must be an integer")
        if self.authority != "scenario_input" or self.canonical is not False:
            raise RegionalTransportError(
                "route cost terms must remain non-canonical scenario inputs"
            )


@dataclass(frozen=True, slots=True, order=True)
class RouteUsageReceipt:
    """Resolved physical and cost receipt for one route in one period."""

    route_id: str
    commodity_id: str
    origin_site_id: str
    destination_site_id: str
    carrier_entity_id: str | None
    quantity_moved: Decimal
    capacity: Decimal
    expected_loss_quantity: Decimal
    expected_delivered_quantity: Decimal
    transport_cost_gp_per_dispatched_unit: Decimal
    transport_cost_gp: Decimal
    arrival_period_index: int

    def __post_init__(self) -> None:
        for value, label in (
            (self.route_id, "route-usage route ID"),
            (self.commodity_id, "route-usage commodity ID"),
            (self.origin_site_id, "route-usage origin site ID"),
            (self.destination_site_id, "route-usage destination site ID"),
        ):
            _require_text(value, label)
        if self.carrier_entity_id is not None:
            _require_text(self.carrier_entity_id, "route-usage carrier entity ID")
        for value, label in (
            (self.quantity_moved, "route quantity moved"),
            (self.capacity, "route capacity"),
            (self.expected_loss_quantity, "expected route loss"),
            (self.expected_delivered_quantity, "expected route delivery"),
            (
                self.transport_cost_gp_per_dispatched_unit,
                "transport cost per dispatched unit",
            ),
            (self.transport_cost_gp, "transport cost"),
        ):
            _require_decimal(value, label)
            if value < ZERO:
                raise RegionalTransportError(f"{label} cannot be negative")
        if self.quantity_moved > self.capacity:
            raise RegionalTransportError("route movement cannot exceed route capacity")
        with localcontext(_new_transport_context()):
            reconciled_quantity = (
                self.expected_loss_quantity + self.expected_delivered_quantity
            )
        if reconciled_quantity != self.quantity_moved:
            raise RegionalTransportError(
                "route receipt must conserve dispatched quantity across loss and delivery"
            )
        if type(self.arrival_period_index) is not int or self.arrival_period_index < 1:
            raise RegionalTransportError(
                "route arrival period index must be a positive integer"
            )
        with localcontext(_new_transport_context()):
            expected_cost = (
                self.quantity_moved
                * self.transport_cost_gp_per_dispatched_unit
            )
        if self.transport_cost_gp != expected_cost:
            raise RegionalTransportError("route transport cost does not match its terms")

    @property
    def remaining_capacity(self) -> Decimal:
        with localcontext(_new_transport_context()):
            return self.capacity - self.quantity_moved

    def to_payload(self) -> dict[str, object]:
        return {
            "route_id": self.route_id,
            "commodity_id": self.commodity_id,
            "origin_site_id": self.origin_site_id,
            "destination_site_id": self.destination_site_id,
            "carrier_entity_id": self.carrier_entity_id,
            "quantity_moved": canonical_decimal(self.quantity_moved),
            "capacity": canonical_decimal(self.capacity),
            "remaining_capacity": canonical_decimal(self.remaining_capacity),
            "expected_loss_quantity": canonical_decimal(
                self.expected_loss_quantity
            ),
            "expected_delivered_quantity": canonical_decimal(
                self.expected_delivered_quantity
            ),
            "transport_cost_gp_per_dispatched_unit": canonical_decimal(
                self.transport_cost_gp_per_dispatched_unit
            ),
            "transport_cost_gp": canonical_decimal(self.transport_cost_gp),
            "arrival_period_index": self.arrival_period_index,
        }


def expected_transport_outcome(
    route: Route,
    dispatched_quantity: Decimal,
) -> tuple[Decimal, Decimal]:
    """Return ``(loss, delivery)`` under the kernel's Decimal policy."""

    if type(route) is not Route:
        raise RegionalTransportError("expected transport outcome requires a Route")
    moved = _require_decimal(dispatched_quantity, "dispatched quantity")
    if moved < ZERO:
        raise RegionalTransportError("dispatched quantity cannot be negative")
    if moved > route.capacity_per_period:
        raise RegionalTransportError("dispatched quantity exceeds route capacity")
    with localcontext(_new_transport_context()):
        loss = moved * route.loss_rate
        delivery = moved - loss
    return loss, delivery


def dispatch_for_delivery(
    route: Route,
    desired_delivery_quantity: Decimal,
    *,
    available_stock: Decimal,
    remaining_capacity: Decimal,
) -> Decimal:
    """Plan the largest safe dispatch that does not intentionally over-deliver.

    The result is constrained by the caller's available stock and the remaining
    physical capacity of the route.  Division is performed inside a fixed
    context, so ambient process settings cannot alter allocation.
    """

    if type(route) is not Route:
        raise RegionalTransportError("dispatch planning requires a Route")
    desired = _require_decimal(desired_delivery_quantity, "desired delivery")
    stock = _require_decimal(available_stock, "available route stock")
    capacity = _require_decimal(remaining_capacity, "remaining route capacity")
    if desired < ZERO or stock < ZERO or capacity < ZERO:
        raise RegionalTransportError("dispatch planning quantities cannot be negative")
    maximum = min(stock, capacity, route.capacity_per_period)
    if desired == ZERO or maximum == ZERO:
        return ZERO

    with localcontext(_new_transport_context()) as context:
        survival = ONE - route.loss_rate
        maximum_delivery = maximum - (maximum * route.loss_rate)
        if maximum_delivery <= desired:
            return maximum
        dispatched = context.divide(desired, survival)
        if dispatched > maximum:
            dispatched = maximum
        loss = dispatched * route.loss_rate
        delivered = dispatched - loss
        # A rounded quotient can land one representable step above the desired
        # delivery. Step down until the receipt does not over-allocate demand.
        while delivered > desired:
            dispatched = context.next_minus(dispatched)
            loss = dispatched * route.loss_rate
            delivered = dispatched - loss
        return max(ZERO, dispatched)


def route_usage_receipt(
    route: Route,
    terms: RouteCostTerms,
    *,
    quantity_moved: Decimal,
    departure_period_index: int,
) -> RouteUsageReceipt:
    """Build and validate one route receipt from resolved kernel movement."""

    if type(route) is not Route or type(terms) is not RouteCostTerms:
        raise RegionalTransportError("route usage requires Route and RouteCostTerms")
    if terms.route_id != route.route_id:
        raise RegionalTransportError("route cost terms do not match the physical route")
    if type(departure_period_index) is not int or departure_period_index < 1:
        raise RegionalTransportError("departure period index must be positive")
    moved = _require_decimal(quantity_moved, "route quantity moved")
    loss, delivery = expected_transport_outcome(route, moved)
    with localcontext(_new_transport_context()):
        transport_cost = moved * terms.transport_cost_gp_per_dispatched_unit
    return RouteUsageReceipt(
        route_id=route.route_id,
        commodity_id=route.commodity_id,
        origin_site_id=route.origin_site_id,
        destination_site_id=route.destination_site_id,
        carrier_entity_id=terms.carrier_entity_id,
        quantity_moved=moved,
        capacity=route.capacity_per_period,
        expected_loss_quantity=loss,
        expected_delivered_quantity=delivery,
        transport_cost_gp_per_dispatched_unit=(
            terms.transport_cost_gp_per_dispatched_unit
        ),
        transport_cost_gp=transport_cost,
        arrival_period_index=departure_period_index + route.travel_periods,
    )
