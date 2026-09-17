"""Deterministic stock-flow simulation with explicit conservation checks."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from enum import StrEnum
import hashlib
import json
from typing import Iterable, Mapping

from .domain import (
    SimulationAssignment,
    SimulationMode,
    canonical_decimal,
    validate_unique_assignments,
)
from .events import (
    CURRENT_MODEL_VERSION,
    EventEnvelope,
    EventPhase,
    EventStore,
    canonical_json,
)


ZERO = Decimal(0)
ONE = Decimal(1)
ENGINE_RULESET_SCHEMA = "tnp.economy.stockflow/1"


def _new_engine_decimal_context() -> Context:
    """Return a fresh, externally unmodifiable arithmetic policy for one run."""

    return Context(
        prec=40,
        rounding=ROUND_HALF_EVEN,
        Emin=-999999,
        Emax=999999,
        capitals=1,
        clamp=0,
    )


def _is_sha256(value: str) -> bool:
    """Return whether *value* is a lowercase hexadecimal SHA-256 digest."""
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


class SimulationError(ValueError):
    pass


def _require_decimal(value: object, label: str) -> Decimal:
    """Reject implicit numeric coercion before values enter replay state."""

    if type(value) is not Decimal or not value.is_finite():
        raise SimulationError(f"{label} must be a finite Decimal")
    return value


def _require_int(value: object, label: str, *, minimum: int | None = None) -> int:
    if type(value) is not int or (minimum is not None and value < minimum):
        qualifier = f" at least {minimum}" if minimum is not None else ""
        raise SimulationError(f"{label} must be an integer{qualifier}")
    return value


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SimulationError(f"{label} is required")
    return value


def _require_concrete_tuple(
    value: object, item_type: type[object], label: str
) -> tuple[object, ...]:
    if type(value) is not tuple:
        raise SimulationError(f"{label} must be an immutable tuple")
    if any(type(item) is not item_type for item in value):
        raise SimulationError(f"{label} contains a value of the wrong type")
    return value


class FlowKind(StrEnum):
    ARRIVAL = "arrival"
    ROUTE_LOSS = "route_loss"
    RECIPE_INPUT = "recipe_input"
    PRODUCTION = "production"
    DISPATCH = "dispatch"
    CONSUMPTION = "consumption"


@dataclass(frozen=True, slots=True, order=True)
class Commodity:
    commodity_id: str
    name: str
    unit: str
    base_price: Decimal | None
    elasticity: Decimal = Decimal("0.50")
    floor_factor: Decimal = Decimal("0.25")
    ceiling_factor: Decimal = Decimal("4.00")
    market_price_enabled: bool = True

    def __post_init__(self) -> None:
        for value, label in (
            (self.elasticity, "commodity elasticity"),
            (self.floor_factor, "commodity floor factor"),
            (self.ceiling_factor, "commodity ceiling factor"),
        ):
            _require_decimal(value, label)
        if not all(
            isinstance(value, str) and value.strip()
            for value in (self.commodity_id, self.name, self.unit)
        ):
            raise SimulationError("commodity ID, name, and unit are required")
        if type(self.market_price_enabled) is not bool:
            raise SimulationError("commodity market-price flag must be a boolean")
        if self.market_price_enabled:
            _require_decimal(self.base_price, "commodity base price")
            if self.base_price <= ZERO:
                raise SimulationError("tracked commodity price must be positive")
        elif self.base_price is not None:
            raise SimulationError("untracked commodity price must be explicit unknown, not zero")
        if self.floor_factor <= ZERO:
            raise SimulationError("commodity price floor must be positive")
        if self.ceiling_factor < self.floor_factor:
            raise SimulationError("commodity price ceiling cannot be below floor")
        if self.elasticity < ZERO:
            raise SimulationError("commodity elasticity cannot be negative")


@dataclass(frozen=True, slots=True, order=True)
class Site:
    site_id: str
    name: str
    labor_capacity: Decimal

    def __post_init__(self) -> None:
        _require_decimal(self.labor_capacity, "site labor capacity")
        if self.labor_capacity < ZERO:
            raise SimulationError("site labor capacity cannot be negative")


@dataclass(frozen=True, slots=True)
class Recipe:
    recipe_id: str
    site_id: str
    entity_id: str
    inputs: tuple[tuple[str, Decimal], ...]
    outputs: tuple[tuple[str, Decimal], ...]
    labor_per_batch: Decimal
    max_batches: Decimal
    priority: int = 100

    def __post_init__(self) -> None:
        for pairs, label in (
            (self.inputs, "recipe inputs"),
            (self.outputs, "recipe outputs"),
        ):
            if type(pairs) is not tuple or any(
                type(pair) is not tuple
                or len(pair) != 2
                or not isinstance(pair[0], str)
                for pair in pairs
            ):
                raise SimulationError(f"{label} must be immutable commodity/Decimal pairs")
        _require_decimal(self.labor_per_batch, "recipe labor per batch")
        _require_decimal(self.max_batches, "recipe maximum batches")
        _require_int(self.priority, "recipe priority")
        if self.labor_per_batch < ZERO or self.max_batches < ZERO:
            raise SimulationError("recipe labor and maximum batches cannot be negative")
        for _, quantity in (*self.inputs, *self.outputs):
            _require_decimal(quantity, "recipe input/output quantity")
            if quantity <= ZERO:
                raise SimulationError("recipe input/output quantities must be positive")
        if not self.outputs:
            raise SimulationError("recipe must produce at least one output")


@dataclass(frozen=True, slots=True, order=True)
class Route:
    route_id: str
    origin_site_id: str
    destination_site_id: str
    commodity_id: str
    capacity_per_period: Decimal
    travel_periods: int
    loss_rate: Decimal = ZERO

    def __post_init__(self) -> None:
        _require_decimal(self.capacity_per_period, "route capacity")
        _require_decimal(self.loss_rate, "route loss rate")
        _require_int(self.travel_periods, "route travel periods", minimum=1)
        if self.capacity_per_period < ZERO:
            raise SimulationError("route capacity cannot be negative")
        if self.travel_periods < 1:
            raise SimulationError("route travel time must be at least one period")
        if not (ZERO <= self.loss_rate < ONE):
            raise SimulationError("route loss rate must be in [0, 1)")


@dataclass(frozen=True, slots=True, order=True)
class InventoryPosition:
    site_id: str
    commodity_id: str
    quantity: Decimal
    reserved_quantity: Decimal = ZERO

    def __post_init__(self) -> None:
        _require_decimal(self.quantity, "inventory quantity")
        _require_decimal(self.reserved_quantity, "reserved inventory quantity")
        if self.quantity < ZERO or self.reserved_quantity < ZERO:
            raise SimulationError("inventory and reservation quantities cannot be negative")
        if self.reserved_quantity > self.quantity:
            raise SimulationError("reserved inventory cannot exceed on-hand inventory")


def available_quantity(position: InventoryPosition | None) -> Decimal:
    """Return unreserved stock available to promise, or zero for a missing item.

    Adapted from Brunnfeld's MIT-licensed ``getInventoryQty`` behavior. See
    ``THIRD_PARTY_NOTICES.md`` and ``docs/THIRD_PARTY_SOURCES.md``.
    """

    if position is None:
        return ZERO
    return max(ZERO, position.quantity - position.reserved_quantity)


@dataclass(frozen=True, slots=True, order=True)
class PricePosition:
    site_id: str
    commodity_id: str
    amount: Decimal

    def __post_init__(self) -> None:
        _require_decimal(self.amount, "price amount")
        if self.amount <= ZERO:
            raise SimulationError("snapshot prices must be positive")


@dataclass(frozen=True, slots=True, order=True)
class TransitLot:
    shipment_id: str
    route_id: str
    commodity_id: str
    origin_site_id: str
    destination_site_id: str
    quantity: Decimal
    arrival_period_index: int
    loss_rate: Decimal

    def __post_init__(self) -> None:
        _require_decimal(self.quantity, "transit quantity")
        _require_decimal(self.loss_rate, "transit loss rate")
        _require_int(
            self.arrival_period_index, "transit arrival period index", minimum=1
        )
        if not all(
            (
                self.shipment_id,
                self.route_id,
                self.commodity_id,
                self.origin_site_id,
                self.destination_site_id,
            )
        ):
            raise SimulationError("transit lot identifiers are required")
        if self.quantity <= ZERO:
            raise SimulationError("transit quantity must be positive")
        if self.arrival_period_index < 1:
            raise SimulationError("transit arrival period must be positive")
        if not (ZERO <= self.loss_rate < ONE):
            raise SimulationError("transit loss rate must be in [0, 1)")


@dataclass(frozen=True, slots=True, order=True)
class ProductionOrder:
    recipe_id: str
    requested_batches: Decimal
    authorizing_event_id: str | None = None

    def __post_init__(self) -> None:
        _require_decimal(self.requested_batches, "requested production batches")


@dataclass(frozen=True, slots=True, order=True)
class ShipmentOrder:
    shipment_id: str
    route_id: str
    commodity_id: str
    requested_quantity: Decimal
    source_ref: str
    authorizing_event_id: str | None = None

    def __post_init__(self) -> None:
        _require_decimal(self.requested_quantity, "requested shipment quantity")


@dataclass(frozen=True, slots=True, order=True)
class Need:
    site_id: str
    commodity_id: str
    requested_quantity: Decimal
    priority: int = 100
    authorizing_event_id: str | None = None

    def __post_init__(self) -> None:
        _require_decimal(self.requested_quantity, "requested need quantity")
        _require_int(self.priority, "need priority")


@dataclass(frozen=True, slots=True)
class RunPlan:
    period_index: int
    campaign_ordinal: int
    campaign_date: str
    production_orders: tuple[ProductionOrder, ...] = ()
    shipment_orders: tuple[ShipmentOrder, ...] = ()
    needs: tuple[Need, ...] = ()
    authorizing_events: tuple[EventEnvelope, ...] = ()
    simulation_assignments: tuple[SimulationAssignment, ...] = ()

    def __post_init__(self) -> None:
        _require_int(self.period_index, "run period index", minimum=1)
        _require_int(self.campaign_ordinal, "run campaign ordinal")
        _require_text(self.campaign_date, "run campaign-date label")
        for values, item_type, label in (
            (self.production_orders, ProductionOrder, "run production orders"),
            (self.shipment_orders, ShipmentOrder, "run shipment orders"),
            (self.needs, Need, "run needs"),
            (self.authorizing_events, EventEnvelope, "run authorizing events"),
            (
                self.simulation_assignments,
                SimulationAssignment,
                "run simulation assignments",
            ),
        ):
            _require_concrete_tuple(values, item_type, label)


@dataclass(frozen=True, slots=True, order=True)
class MaterialFlow:
    kind: FlowKind
    site_id: str
    commodity_id: str
    quantity: Decimal
    reference_id: str

    def __post_init__(self) -> None:
        _require_decimal(self.quantity, "material-flow quantity")


@dataclass(frozen=True, slots=True, order=True)
class ProductionResult:
    recipe_id: str
    requested_batches: Decimal
    actual_batches: Decimal

    def __post_init__(self) -> None:
        _require_decimal(self.requested_batches, "production-result requested batches")
        _require_decimal(self.actual_batches, "production-result actual batches")

    @property
    def shortfall_batches(self) -> Decimal:
        return self.requested_batches - self.actual_batches


@dataclass(frozen=True, slots=True, order=True)
class ShipmentResult:
    shipment_id: str
    requested_quantity: Decimal
    dispatched_quantity: Decimal

    def __post_init__(self) -> None:
        _require_decimal(self.requested_quantity, "shipment-result requested quantity")
        _require_decimal(self.dispatched_quantity, "shipment-result dispatched quantity")

    @property
    def shortfall_quantity(self) -> Decimal:
        return self.requested_quantity - self.dispatched_quantity


@dataclass(frozen=True, slots=True, order=True)
class NeedResult:
    site_id: str
    commodity_id: str
    requested_quantity: Decimal
    consumed_quantity: Decimal

    def __post_init__(self) -> None:
        _require_decimal(self.requested_quantity, "need-result requested quantity")
        _require_decimal(self.consumed_quantity, "need-result consumed quantity")

    @property
    def shortage_quantity(self) -> Decimal:
        return self.requested_quantity - self.consumed_quantity


@dataclass(frozen=True, slots=True)
class Snapshot:
    timeline_id: str
    period_index: int
    campaign_ordinal: int
    campaign_date: str
    ruleset_version: str
    ruleset_hash: str
    model_hash: str
    input_hash: str | None
    parent_hash: str | None
    inventories: tuple[InventoryPosition, ...]
    prices: tuple[PricePosition, ...]
    transit: tuple[TransitLot, ...]
    applied_event_refs: tuple[tuple[str, str], ...]
    applied_shipment_ids: tuple[str, ...]
    snapshot_id: str
    state_hash: str

    def verify(self) -> None:
        for values, item_type, label in (
            (self.inventories, InventoryPosition, "snapshot inventories"),
            (self.prices, PricePosition, "snapshot prices"),
            (self.transit, TransitLot, "snapshot transit"),
        ):
            _require_concrete_tuple(values, item_type, label)
        if type(self.applied_event_refs) is not tuple or any(
            type(ref) is not tuple
            or len(ref) != 2
            or any(not isinstance(value, str) for value in ref)
            for ref in self.applied_event_refs
        ):
            raise SimulationError(
                "snapshot applied-event references must be immutable string pairs"
            )
        if type(self.applied_shipment_ids) is not tuple or any(
            not isinstance(value, str) for value in self.applied_shipment_ids
        ):
            raise SimulationError(
                "snapshot applied-shipment IDs must be an immutable string tuple"
            )
        if not self.timeline_id.strip() or not self.campaign_date.strip():
            raise SimulationError("snapshot timeline and campaign-date label are required")
        _require_int(self.period_index, "snapshot period index", minimum=0)
        _require_int(self.campaign_ordinal, "snapshot campaign ordinal")
        for label, digest in (
            ("ruleset", self.ruleset_hash),
            ("model", self.model_hash),
        ):
            if not _is_sha256(digest):
                raise SimulationError(f"snapshot {label} hash is invalid")
        if self.input_hash is not None and not _is_sha256(self.input_hash):
            raise SimulationError("snapshot input hash is invalid")
        if self.period_index == 0 and self.parent_hash is not None:
            raise SimulationError("opening snapshot cannot have a parent hash")
        if self.period_index > 0 and not _is_sha256(self.parent_hash):
            raise SimulationError("non-opening snapshot requires a valid parent hash")
        expected = _snapshot_hash(replace(self, snapshot_id="", state_hash=""))
        if expected != self.state_hash or self.snapshot_id != f"snapshot:{expected[:16]}":
            raise SimulationError("snapshot hash does not match immutable contents")
        for position in self.inventories:
            if type(position) is not InventoryPosition:
                raise SimulationError("snapshot inventory has the wrong type")
            _require_decimal(position.quantity, "snapshot inventory quantity")
            _require_decimal(
                position.reserved_quantity, "snapshot reserved inventory quantity"
            )
            # InventoryPosition validates both non-negativity and reservation
            # coverage at construction time. Repeat the explicit invariant here
            # to make snapshot verification fail closed after deserialization.
            if position.quantity < ZERO or position.reserved_quantity < ZERO:
                raise SimulationError("snapshot contains negative inventory or reservation")
            if position.reserved_quantity > position.quantity:
                raise SimulationError("snapshot reservation exceeds on-hand inventory")
        inventory_keys = [(item.site_id, item.commodity_id) for item in self.inventories]
        if len(inventory_keys) != len(set(inventory_keys)):
            raise SimulationError("snapshot contains duplicate inventory positions")
        price_keys = [(item.site_id, item.commodity_id) for item in self.prices]
        if len(price_keys) != len(set(price_keys)):
            raise SimulationError("snapshot contains duplicate price positions")
        for price in self.prices:
            if type(price) is not PricePosition:
                raise SimulationError("snapshot price has the wrong type")
            _require_decimal(price.amount, "snapshot price amount")
        event_ids = [event_id for event_id, _ in self.applied_event_refs]
        if len(event_ids) != len(set(event_ids)):
            raise SimulationError("snapshot contains duplicate applied event IDs")
        for event_id, integrity_hash in self.applied_event_refs:
            if not event_id.startswith("event:") or not _is_sha256(integrity_hash):
                raise SimulationError("snapshot contains an invalid applied event reference")
        if len(self.applied_shipment_ids) != len(set(self.applied_shipment_ids)):
            raise SimulationError("snapshot contains duplicate applied shipment IDs")
        for lot in self.transit:
            if type(lot) is not TransitLot:
                raise SimulationError("snapshot transit lot has the wrong type")
            _require_decimal(lot.quantity, "snapshot transit quantity")
            _require_decimal(lot.loss_rate, "snapshot transit loss rate")
            _require_int(
                lot.arrival_period_index,
                "snapshot transit arrival period index",
                minimum=1,
            )
            if lot.quantity < ZERO:
                raise SimulationError("snapshot contains negative in-transit quantity")

    @property
    def applied_event_ids(self) -> tuple[str, ...]:
        return tuple(event_id for event_id, _ in self.applied_event_refs)


@dataclass(frozen=True, slots=True)
class RunResult:
    snapshot: Snapshot
    flows: tuple[MaterialFlow, ...]
    production: tuple[ProductionResult, ...]
    shipments: tuple[ShipmentResult, ...]
    needs: tuple[NeedResult, ...]
    labor_used: tuple[tuple[str, Decimal], ...]
    conservation: tuple[tuple[str, Decimal], ...]


@dataclass(frozen=True, slots=True)
class EconomyModel:
    commodities: tuple[Commodity, ...]
    sites: tuple[Site, ...]
    recipes: tuple[Recipe, ...]
    routes: tuple[Route, ...]
    model_version: str = CURRENT_MODEL_VERSION

    def __post_init__(self) -> None:
        for values, item_type, label in (
            (self.commodities, Commodity, "model commodities"),
            (self.sites, Site, "model sites"),
            (self.recipes, Recipe, "model recipes"),
            (self.routes, Route, "model routes"),
        ):
            _require_concrete_tuple(values, item_type, label)

    def validate(self) -> None:
        if not isinstance(self.model_version, str) or not self.model_version.strip():
            raise SimulationError("economy model version is required")
        commodity_ids = _unique_ids((item.commodity_id for item in self.commodities), "commodity")
        site_ids = _unique_ids((item.site_id for item in self.sites), "site")
        recipe_ids = _unique_ids((item.recipe_id for item in self.recipes), "recipe")
        route_ids = _unique_ids((item.route_id for item in self.routes), "route")
        del recipe_ids, route_ids
        for recipe in self.recipes:
            if recipe.site_id not in site_ids:
                raise SimulationError(f"unknown recipe site: {recipe.site_id}")
            unknown = {cid for cid, _ in (*recipe.inputs, *recipe.outputs)} - commodity_ids
            if unknown:
                raise SimulationError(f"unknown recipe commodities: {sorted(unknown)}")
        for route in self.routes:
            if route.origin_site_id not in site_ids or route.destination_site_id not in site_ids:
                raise SimulationError(f"route {route.route_id} references an unknown site")
            if route.commodity_id not in commodity_ids:
                raise SimulationError(f"route {route.route_id} references an unknown commodity")

    def validate_snapshot(self, snapshot: Snapshot) -> None:
        self.validate()
        snapshot.verify()
        commodities = {item.commodity_id: item for item in self.commodities}
        sites = {item.site_id for item in self.sites}
        routes = {item.route_id: item for item in self.routes}
        for position in snapshot.inventories:
            if position.site_id not in sites or position.commodity_id not in commodities:
                raise SimulationError("snapshot inventory references an unknown site or commodity")
        for price in snapshot.prices:
            if price.site_id not in sites or price.commodity_id not in commodities:
                raise SimulationError("snapshot price references an unknown site or commodity")
            if price.amount <= ZERO:
                raise SimulationError("snapshot prices must be positive")
        transit_ids: set[str] = set()
        for lot in snapshot.transit:
            if lot.shipment_id in transit_ids:
                raise SimulationError("snapshot contains duplicate transit shipment IDs")
            transit_ids.add(lot.shipment_id)
            route = routes.get(lot.route_id)
            if route is None:
                raise SimulationError("snapshot transit references an unknown route")
            if (
                lot.commodity_id != route.commodity_id
                or lot.origin_site_id != route.origin_site_id
                or lot.destination_site_id != route.destination_site_id
                or lot.loss_rate != route.loss_rate
            ):
                raise SimulationError("snapshot transit does not match its route contract")
            if lot.arrival_period_index <= snapshot.period_index:
                raise SimulationError("snapshot retains a transit lot already due to arrive")


def _unique_ids(values: Iterable[str], label: str) -> set[str]:
    materialized = list(values)
    if len(set(materialized)) != len(materialized):
        raise SimulationError(f"duplicate {label} identifier")
    return set(materialized)


def initial_snapshot(
    model: EconomyModel,
    *,
    timeline_id: str,
    campaign_ordinal: int,
    campaign_date: str,
    ruleset_version: str,
    inventories: Iterable[InventoryPosition] = (),
    prices: Iterable[PricePosition] = (),
    transit: Iterable[TransitLot] = (),
    opening_events: Iterable[EventEnvelope] = (),
    event_store: EventStore | None = None,
) -> Snapshot:
    _require_text(timeline_id, "opening timeline")
    _require_int(campaign_ordinal, "opening campaign ordinal")
    _require_text(campaign_date, "opening campaign-date label")
    _require_text(ruleset_version, "opening ruleset version")
    materialized_inventory = tuple(sorted(inventories))
    materialized_prices = tuple(sorted(prices))
    materialized_transit = tuple(sorted(transit))
    materialized_events = tuple(opening_events)
    if timeline_id == "actual":
        if not materialized_events:
            raise SimulationError("actual opening state requires authoritative opening events")
        if type(event_store) is not EventStore:
            raise SimulationError("actual opening events require an accepted event store")
        for event in materialized_events:
            if not event.may_mutate_actual or event.campaign_date.ordinal != campaign_ordinal:
                raise SimulationError("actual opening event is not resolved/current/authoritative at the opening date")
            if event.campaign_date.label != campaign_date:
                raise SimulationError("actual opening event date label does not match the opening snapshot")
            if not event_store.contains_active(event):
                raise SimulationError("actual opening event is not accepted by the event store")
            if event.model_version != model.model_version:
                raise SimulationError("actual opening event model version does not match the economy model")
        _validate_actual_opening_payload(
            timeline_id=timeline_id,
            campaign_ordinal=campaign_ordinal,
            campaign_date=campaign_date,
            inventories=materialized_inventory,
            prices=materialized_prices,
            transit=materialized_transit,
            events=materialized_events,
        )
    event_refs = _validated_event_refs(materialized_events)
    snapshot = _seal(
        Snapshot(
            timeline_id=timeline_id,
            period_index=0,
            campaign_ordinal=campaign_ordinal,
            campaign_date=campaign_date,
            ruleset_version=ruleset_version,
            ruleset_hash=_ruleset_hash(ruleset_version),
            model_hash=_model_hash(model),
            input_hash=_canonical_hash({"opening_events": event_refs}),
            parent_hash=None,
            inventories=materialized_inventory,
            prices=materialized_prices,
            transit=materialized_transit,
            applied_event_refs=event_refs,
            applied_shipment_ids=tuple(sorted({lot.shipment_id for lot in materialized_transit})),
            snapshot_id="",
            state_hash="",
        )
    )
    model.validate_snapshot(snapshot)
    return snapshot


def advance(
    model: EconomyModel,
    parent: Snapshot,
    plan: RunPlan,
    *,
    event_store: EventStore | None = None,
) -> RunResult:
    with localcontext(_new_engine_decimal_context()):
        return _advance(model, parent, plan, event_store=event_store)


def _advance(
    model: EconomyModel,
    parent: Snapshot,
    plan: RunPlan,
    *,
    event_store: EventStore | None,
) -> RunResult:
    model.validate_snapshot(parent)
    model_hash = _model_hash(model)
    if parent.model_hash != model_hash:
        raise SimulationError("snapshot model hash does not match the supplied economy model")
    if parent.ruleset_hash != _ruleset_hash(parent.ruleset_version):
        raise SimulationError("snapshot ruleset hash does not match its ruleset version")
    if plan.period_index != parent.period_index + 1:
        raise SimulationError("run must advance exactly one period from its parent")
    if plan.campaign_ordinal <= parent.campaign_ordinal:
        raise SimulationError("campaign ordinal must advance monotonically")
    event_refs = _validated_event_refs(plan.authorizing_events)
    event_ids = tuple(event_id for event_id, _ in event_refs)
    already_applied = set(parent.applied_event_ids) & set(event_ids)
    if already_applied:
        raise SimulationError(f"resolved events already applied: {sorted(already_applied)}")
    if parent.timeline_id == "actual":
        _validate_actual_plan(model, parent, plan, event_store=event_store)
    plan_hash = _plan_hash(plan)

    commodities = {item.commodity_id: item for item in model.commodities}
    sites = {item.site_id: item for item in model.sites}
    recipes = {item.recipe_id: item for item in model.recipes}
    routes = {item.route_id: item for item in model.routes}
    inventory = defaultdict(Decimal, {(p.site_id, p.commodity_id): p.quantity for p in parent.inventories})
    reserved = defaultdict(Decimal, {(p.site_id, p.commodity_id): p.reserved_quantity for p in parent.inventories})
    prices = {(p.site_id, p.commodity_id): p.amount for p in parent.prices}
    labor_remaining = {site.site_id: site.labor_capacity for site in model.sites}
    labor_used = defaultdict(Decimal)
    flows: list[MaterialFlow] = []
    transit: list[TransitLot] = []
    opening_by_commodity = _commodity_totals(parent.inventories, parent.transit)

    losses = defaultdict(Decimal)
    for lot in sorted(parent.transit):
        if lot.arrival_period_index <= plan.period_index:
            lost = lot.quantity * lot.loss_rate
            delivered = lot.quantity - lost
            inventory[(lot.destination_site_id, lot.commodity_id)] += delivered
            flows.append(MaterialFlow(FlowKind.ARRIVAL, lot.destination_site_id, lot.commodity_id, delivered, lot.shipment_id))
            if lost:
                losses[lot.commodity_id] += lost
                flows.append(MaterialFlow(FlowKind.ROUTE_LOSS, lot.destination_site_id, lot.commodity_id, lost, lot.shipment_id))
        else:
            transit.append(lot)

    production_results: list[ProductionResult] = []
    recipe_batches_used = defaultdict(Decimal)
    produced = defaultdict(Decimal)
    recipe_inputs = defaultdict(Decimal)
    for order in sorted(
        plan.production_orders,
        key=lambda item: (
            recipes[item.recipe_id].priority if item.recipe_id in recipes else 10**9,
            item.recipe_id,
            item.requested_batches,
            item.authorizing_event_id or "",
        ),
    ):
        if order.requested_batches < ZERO:
            raise SimulationError("requested production cannot be negative")
        recipe = recipes.get(order.recipe_id)
        if recipe is None:
            raise SimulationError(f"unknown recipe: {order.recipe_id}")
        remaining_recipe_capacity = recipe.max_batches - recipe_batches_used[recipe.recipe_id]
        feasible = min(order.requested_batches, max(ZERO, remaining_recipe_capacity))
        if recipe.labor_per_batch:
            feasible = min(feasible, labor_remaining[recipe.site_id] / recipe.labor_per_batch)
        for commodity_id, per_batch in recipe.inputs:
            key = (recipe.site_id, commodity_id)
            feasible = min(feasible, (inventory[key] - reserved[key]) / per_batch)
        feasible = max(ZERO, feasible)
        for commodity_id, per_batch in recipe.inputs:
            quantity = per_batch * feasible
            inventory[(recipe.site_id, commodity_id)] -= quantity
            recipe_inputs[commodity_id] += quantity
            flows.append(MaterialFlow(FlowKind.RECIPE_INPUT, recipe.site_id, commodity_id, quantity, recipe.recipe_id))
        for commodity_id, per_batch in recipe.outputs:
            quantity = per_batch * feasible
            inventory[(recipe.site_id, commodity_id)] += quantity
            produced[commodity_id] += quantity
            flows.append(MaterialFlow(FlowKind.PRODUCTION, recipe.site_id, commodity_id, quantity, recipe.recipe_id))
        used = recipe.labor_per_batch * feasible
        labor_remaining[recipe.site_id] -= used
        labor_used[recipe.site_id] += used
        recipe_batches_used[recipe.recipe_id] += feasible
        production_results.append(ProductionResult(recipe.recipe_id, order.requested_batches, feasible))

    route_used = defaultdict(Decimal)
    shipment_results: list[ShipmentResult] = []
    shipment_ids = set()
    for order in sorted(plan.shipment_orders):
        if order.requested_quantity < ZERO:
            raise SimulationError("requested shipment cannot be negative")
        if order.shipment_id in shipment_ids or order.shipment_id in parent.applied_shipment_ids:
            raise SimulationError(f"duplicate shipment ID: {order.shipment_id}")
        shipment_ids.add(order.shipment_id)
        route = routes.get(order.route_id)
        if route is None:
            raise SimulationError(f"unknown route: {order.route_id}")
        if order.commodity_id not in commodities:
            raise SimulationError(f"unknown commodity: {order.commodity_id}")
        if order.commodity_id != route.commodity_id:
            raise SimulationError(
                f"route {route.route_id} capacity is declared for {route.commodity_id}, "
                f"not {order.commodity_id}"
            )
        stock_key = (route.origin_site_id, order.commodity_id)
        available_stock = inventory[stock_key] - reserved[stock_key]
        remaining_capacity = route.capacity_per_period - route_used[route.route_id]
        dispatched = min(order.requested_quantity, available_stock, remaining_capacity)
        dispatched = max(ZERO, dispatched)
        inventory[(route.origin_site_id, order.commodity_id)] -= dispatched
        route_used[route.route_id] += dispatched
        if dispatched:
            transit.append(
                TransitLot(
                    shipment_id=order.shipment_id,
                    route_id=route.route_id,
                    commodity_id=order.commodity_id,
                    origin_site_id=route.origin_site_id,
                    destination_site_id=route.destination_site_id,
                    quantity=dispatched,
                    arrival_period_index=plan.period_index + route.travel_periods,
                    loss_rate=route.loss_rate,
                )
            )
            flows.append(MaterialFlow(FlowKind.DISPATCH, route.origin_site_id, order.commodity_id, dispatched, order.shipment_id))
        shipment_results.append(ShipmentResult(order.shipment_id, order.requested_quantity, dispatched))

    need_results: list[NeedResult] = []
    consumed = defaultdict(Decimal)
    aggregated_needs: defaultdict[tuple[int, str, str], Decimal] = defaultdict(Decimal)
    for need in sorted(
        plan.needs,
        key=lambda item: (
            item.priority,
            item.site_id,
            item.commodity_id,
            item.requested_quantity,
            item.authorizing_event_id or "",
        ),
    ):
        if need.requested_quantity < ZERO:
            raise SimulationError("requested need cannot be negative")
        if need.site_id not in sites or need.commodity_id not in commodities:
            raise SimulationError("need references unknown site or commodity")
        aggregated_needs[(need.priority, need.site_id, need.commodity_id)] += need.requested_quantity
    for (priority, site_id, commodity_id), requested_quantity in sorted(aggregated_needs.items()):
        if requested_quantity == ZERO:
            continue
        stock_key = (site_id, commodity_id)
        available = inventory[stock_key] - reserved[stock_key]
        actual = min(requested_quantity, available)
        inventory[stock_key] -= actual
        consumed[commodity_id] += actual
        if actual:
            flows.append(MaterialFlow(FlowKind.CONSUMPTION, site_id, commodity_id, actual, f"need:{priority}"))
        need_results.append(NeedResult(site_id, commodity_id, requested_quantity, actual))
        if commodities[commodity_id].market_price_enabled:
            current_price = prices.get(
                (site_id, commodity_id), commodities[commodity_id].base_price
            )
            prices[(site_id, commodity_id)] = _price_after_need(
                commodities[commodity_id],
                requested_quantity,
                actual,
                inventory[stock_key] - reserved[stock_key],
                current_price,
            )

    for value in inventory.values():
        if value < ZERO:
            raise SimulationError("negative inventory escaped stock constraints")
    for key, reserved_quantity in reserved.items():
        if reserved_quantity < ZERO or reserved_quantity > inventory[key]:
            raise SimulationError("invalid reservation escaped stock constraints")
    if any(value < ZERO for value in labor_remaining.values()):
        raise SimulationError("negative labor escaped production constraints")
    if any(route_used[rid] > routes[rid].capacity_per_period for rid in route_used):
        raise SimulationError("route capacity was oversubscribed")

    inventory_positions = tuple(sorted(
        InventoryPosition(site_id, commodity_id, quantity, reserved[(site_id, commodity_id)])
        for (site_id, commodity_id), quantity in inventory.items()
        if quantity != ZERO
    ))
    closing_by_commodity = _commodity_totals(inventory_positions, transit)
    commodity_ids = set(opening_by_commodity) | set(closing_by_commodity) | set(produced) | set(recipe_inputs) | set(consumed) | set(losses)
    residuals = []
    for commodity_id in sorted(commodity_ids):
        expected = (
            opening_by_commodity[commodity_id]
            + produced[commodity_id]
            - recipe_inputs[commodity_id]
            - consumed[commodity_id]
            - losses[commodity_id]
        )
        residual = expected - closing_by_commodity[commodity_id]
        residuals.append((commodity_id, residual))
        if residual != ZERO:
            raise SimulationError(f"material conservation failed for {commodity_id}: {residual}")

    child = _seal(
        Snapshot(
            timeline_id=parent.timeline_id,
            period_index=plan.period_index,
            campaign_ordinal=plan.campaign_ordinal,
            campaign_date=plan.campaign_date,
            ruleset_version=parent.ruleset_version,
            ruleset_hash=parent.ruleset_hash,
            model_hash=model_hash,
            input_hash=plan_hash,
            parent_hash=parent.state_hash,
            inventories=inventory_positions,
            prices=tuple(sorted(PricePosition(site, commodity, amount) for (site, commodity), amount in prices.items())),
            transit=tuple(sorted(transit)),
            applied_event_refs=tuple(sorted((*parent.applied_event_refs, *event_refs))),
            applied_shipment_ids=tuple(sorted((*parent.applied_shipment_ids, *shipment_ids))),
            snapshot_id="",
            state_hash="",
        )
    )
    model.validate_snapshot(child)
    return RunResult(
        snapshot=child,
        flows=tuple(flows),
        production=tuple(production_results),
        shipments=tuple(shipment_results),
        needs=tuple(need_results),
        labor_used=tuple(sorted(labor_used.items())),
        conservation=tuple(residuals),
    )


def _commodity_totals(
    inventories: Iterable[InventoryPosition], transit: Iterable[TransitLot]
) -> defaultdict[str, Decimal]:
    totals: defaultdict[str, Decimal] = defaultdict(Decimal)
    for position in inventories:
        totals[position.commodity_id] += position.quantity
    for lot in transit:
        totals[lot.commodity_id] += lot.quantity
    return totals


def _price_after_need(
    commodity: Commodity,
    requested: Decimal,
    consumed: Decimal,
    closing_stock: Decimal,
    current_price: Decimal | None,
) -> Decimal:
    if not commodity.market_price_enabled or commodity.base_price is None:
        raise SimulationError("market-price response requested for an untracked commodity")
    _require_decimal(current_price, "current market price")
    if current_price <= ZERO:
        raise SimulationError("current market price must be positive")
    if requested == ZERO:
        return current_price
    shortage = (requested - consumed) / requested
    surplus_coverage = min(ONE, closing_stock / requested)
    factor = ONE + commodity.elasticity * shortage - commodity.elasticity * Decimal("0.25") * surplus_coverage
    factor = max(commodity.floor_factor, min(commodity.ceiling_factor, factor))
    return current_price * factor


def _seal(snapshot: Snapshot) -> Snapshot:
    digest = _snapshot_hash(snapshot)
    sealed = replace(snapshot, snapshot_id=f"snapshot:{digest[:16]}", state_hash=digest)
    sealed.verify()
    return sealed


def _snapshot_hash(snapshot: Snapshot) -> str:
    payload = asdict(snapshot)
    payload.pop("snapshot_id", None)
    payload.pop("state_hash", None)
    return _canonical_hash(payload)


def _normalize_for_hash(value: object) -> object:
    if isinstance(value, Decimal):
        try:
            return canonical_decimal(value)
        except ValueError as exc:
            raise SimulationError(
                "non-finite Decimal cannot enter a deterministic hash"
            ) from exc
    if isinstance(value, (tuple, list)):
        return [_normalize_for_hash(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return _normalize_for_hash(asdict(value))
    if isinstance(value, dict):
        return {
            str(key): _normalize_for_hash(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise SimulationError(f"unsupported deterministic hash value: {type(value).__name__}")


def _canonical_hash(value: object) -> str:
    payload = json.dumps(
        _normalize_for_hash(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _ruleset_hash(ruleset_version: str) -> str:
    if not ruleset_version.strip():
        raise SimulationError("ruleset version is required")
    context = _new_engine_decimal_context()
    return _canonical_hash(
        {
            "engine_schema": ENGINE_RULESET_SCHEMA,
            "ruleset_version": ruleset_version,
            "decimal_context": {
                "prec": context.prec,
                "rounding": context.rounding,
                "emin": context.Emin,
                "emax": context.Emax,
                "capitals": context.capitals,
                "clamp": context.clamp,
                "traps": sorted(
                    signal.__name__
                    for signal, enabled in context.traps.items()
                    if enabled
                ),
            },
        }
    )


def _model_hash(model: EconomyModel) -> str:
    model.validate()
    return _canonical_hash(
        {
            "commodities": [asdict(item) for item in sorted(model.commodities)],
            "sites": [asdict(item) for item in sorted(model.sites)],
            "recipes": [
                asdict(item) for item in sorted(model.recipes, key=lambda item: item.recipe_id)
            ],
            "routes": [asdict(item) for item in sorted(model.routes)],
            "model_version": model.model_version,
        }
    )


def _validated_event_refs(
    events: Iterable[EventEnvelope],
) -> tuple[tuple[str, str], ...]:
    refs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for event in events:
        if type(event) is not EventEnvelope:
            raise SimulationError(
                "authorizing events must be concrete EventEnvelope values"
            )
        event.validate_integrity()
        if event.event_id in seen:
            raise SimulationError(f"duplicate authorizing event: {event.event_id}")
        seen.add(event.event_id)
        refs.append((event.event_id, event.integrity_hash))
    return tuple(sorted(refs))


def _plan_hash(plan: RunPlan) -> str:
    production = sorted(
        (asdict(item) for item in plan.production_orders),
        key=lambda item: (
            str(item["recipe_id"]),
            _canonical_sort_text(item["requested_batches"]),
            str(item["authorizing_event_id"] or ""),
        ),
    )
    shipments = sorted(
        (asdict(item) for item in plan.shipment_orders),
        key=lambda item: str(item["shipment_id"]),
    )
    needs = sorted(
        (asdict(item) for item in plan.needs),
        key=lambda item: (
            int(item["priority"]),
            str(item["site_id"]),
            str(item["commodity_id"]),
            _canonical_sort_text(item["requested_quantity"]),
            str(item["authorizing_event_id"] or ""),
        ),
    )
    assignments = sorted(
        (asdict(item) for item in plan.simulation_assignments),
        key=lambda item: (
            str(item["entity_id"]),
            str(item["timeline_id"]),
            int(item["period_index"]),
        ),
    )
    return _canonical_hash(
        {
            "period_index": plan.period_index,
            "campaign_ordinal": plan.campaign_ordinal,
            "campaign_date": plan.campaign_date,
            "production_orders": production,
            "shipment_orders": shipments,
            "needs": needs,
            "authorizing_event_refs": _validated_event_refs(plan.authorizing_events),
            "simulation_assignments": assignments,
        }
    )


def _validate_actual_plan(
    model: EconomyModel,
    parent: Snapshot,
    plan: RunPlan,
    *,
    event_store: EventStore | None,
) -> None:
    events = {event.event_id: event for event in plan.authorizing_events}
    if type(event_store) is not EventStore:
        raise SimulationError("actual advancement requires an accepted event store")
    for event_id, integrity_hash in parent.applied_event_refs:
        if not event_store.contains_active_ref(event_id, integrity_hash):
            raise SimulationError(
                "actual parent snapshot references an inactive or unavailable event"
            )
    for event in events.values():
        if not event_store.contains_active(event):
            raise SimulationError("actual authorizing event is not accepted by the event store")
        if not event.may_mutate_actual:
            raise SimulationError(f"event may not mutate actual state: {event.event_id}")
        if event.model_version != model.model_version:
            raise SimulationError("actual authorizing event model version does not match the economy model")
        if event.campaign_date.ordinal != plan.campaign_ordinal:
            raise SimulationError("actual authorizing event date must equal the run campaign ordinal")
        if event.campaign_date.label != plan.campaign_date:
            raise SimulationError("actual authorizing event date label must equal the run campaign date")

    validate_unique_assignments(list(plan.simulation_assignments))
    assignments: dict[str, SimulationAssignment] = {}
    for assignment in plan.simulation_assignments:
        if (
            assignment.timeline_id != parent.timeline_id
            or assignment.period_index != plan.period_index
            or not assignment.source_ref.strip()
        ):
            raise SimulationError("simulation assignment does not match the actual entity-period")
        assignments[assignment.entity_id] = assignment

    used_events: set[str] = set()
    recipes = {recipe.recipe_id: recipe for recipe in model.recipes}
    routes = {route.route_id: route for route in model.routes}

    def require_authority(
        event_id: str | None,
        *,
        phase: str,
        expected_entity_id: str | None = None,
        expected_site_id: str | None = None,
        allowed_modes: frozenset[SimulationMode] = frozenset({SimulationMode.STOCK_FLOW}),
    ) -> EventEnvelope:
        if not event_id or event_id not in events:
            raise SimulationError("actual mutation lacks its validated authorizing event")
        event = events[event_id]
        if event.phase != phase:
            raise SimulationError(f"authorizing event {event_id} has the wrong phase")
        if event.event_type != f"stock.{phase}":
            raise SimulationError(f"authorizing event {event_id} has the wrong stock event type")
        entity_id = expected_entity_id or event.subject_entity_id
        if not entity_id or event.subject_entity_id != entity_id:
            raise SimulationError("authorizing event subject does not match the mutated entity")
        if expected_site_id is not None and event.subject_site_id != expected_site_id:
            raise SimulationError("authorizing event site does not match the mutated site")
        assignment = assignments.get(entity_id)
        if assignment is None or assignment.mode not in allowed_modes:
            raise SimulationError("actual entity-period lacks the required simulation-mode assignment")
        if event_id in used_events:
            raise SimulationError("one authorizing event cannot silently authorize multiple mutations")
        used_events.add(event_id)
        return event

    for order in plan.production_orders:
        recipe = recipes.get(order.recipe_id)
        if recipe is None:
            raise SimulationError(f"unknown recipe: {order.recipe_id}")
        event = require_authority(
            order.authorizing_event_id,
            phase="production",
            expected_entity_id=recipe.entity_id,
            expected_site_id=recipe.site_id,
        )
        _require_event_payload(event, {
            "recipe_id": order.recipe_id,
            "requested_batches": canonical_decimal(order.requested_batches),
        })
    for order in plan.shipment_orders:
        route = routes.get(order.route_id)
        if route is None:
            raise SimulationError(f"unknown route: {order.route_id}")
        event = require_authority(
            order.authorizing_event_id,
            phase="shipment",
            expected_site_id=route.origin_site_id,
        )
        _require_event_payload(event, {
            "shipment_id": order.shipment_id,
            "route_id": order.route_id,
            "commodity_id": order.commodity_id,
            "requested_quantity": canonical_decimal(order.requested_quantity),
        })
    for need in plan.needs:
        event = require_authority(
            need.authorizing_event_id,
            phase="consumption",
            expected_site_id=need.site_id,
            allowed_modes=frozenset({SimulationMode.STOCK_FLOW, SimulationMode.COST_CENTER}),
        )
        _require_event_payload(event, {
            "site_id": need.site_id,
            "commodity_id": need.commodity_id,
            "requested_quantity": canonical_decimal(need.requested_quantity),
            "priority": need.priority,
        })
    if set(events) != used_events:
        raise SimulationError("actual run contains an unused authorizing event")


def _validate_actual_opening_payload(
    *,
    timeline_id: str,
    campaign_ordinal: int,
    campaign_date: str,
    inventories: tuple[InventoryPosition, ...],
    prices: tuple[PricePosition, ...],
    transit: tuple[TransitLot, ...],
    events: tuple[EventEnvelope, ...],
) -> None:
    if len(events) != 1:
        raise SimulationError("actual opening state requires one complete opening event")
    event = events[0]
    if event.phase != EventPhase.SOURCE_LOCK or event.event_type != "stock.opening":
        raise SimulationError("actual opening state requires a stock.opening source-lock event")
    expected_payload = {
        "timeline_id": timeline_id,
        "campaign_ordinal": campaign_ordinal,
        "campaign_date": campaign_date,
        "inventories": [
            {
                "site_id": item.site_id,
                "commodity_id": item.commodity_id,
                "quantity": canonical_decimal(item.quantity),
                "reserved_quantity": canonical_decimal(item.reserved_quantity),
            }
            for item in inventories
        ],
        "prices": [
            {
                "site_id": item.site_id,
                "commodity_id": item.commodity_id,
                "amount": canonical_decimal(item.amount),
            }
            for item in prices
        ],
        "transit": [
            {
                "shipment_id": item.shipment_id,
                "route_id": item.route_id,
                "commodity_id": item.commodity_id,
                "origin_site_id": item.origin_site_id,
                "destination_site_id": item.destination_site_id,
                "quantity": canonical_decimal(item.quantity),
                "arrival_period_index": item.arrival_period_index,
                "loss_rate": canonical_decimal(item.loss_rate),
            }
            for item in transit
        ],
    }
    if event.payload_json != canonical_json(expected_payload):
        raise SimulationError("actual opening event payload does not match the complete opening state")


def _require_event_payload(event: EventEnvelope, expected: Mapping[str, object]) -> None:
    payload = json.loads(event.payload_json)
    if not isinstance(payload, dict):
        raise SimulationError("authorizing event payload must be an object")
    if event.payload_json != canonical_json(expected):
        raise SimulationError("authorizing event payload does not match the exact stock contract")


def _canonical_sort_text(value: object) -> str:
    return canonical_decimal(value) if isinstance(value, Decimal) else str(value)
