"""Source-aware agriculture transport and storage planning.

This module is deliberately a planning surface, not an execution engine.  It
does not create routes, choose speeds, supply loss rates, assume ownership, or
mutate campaign state.  Every numeric planning input is a :class:`SourcedValue`;
``None`` therefore remains an evidenced unknown instead of becoming zero.

The planner conserves a requested lot across four explicit destinations:
quantity held for lack of route capacity, route loss, destination overflow,
and quantity retained after source-supplied storage spoilage.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_CEILING, ROUND_HALF_EVEN, localcontext
from enum import StrEnum

from .source_values import SourcedValue


ZERO = Decimal("0")
ONE = Decimal("1")


class AgricultureLogisticsError(ValueError):
    """Raised when a logistics preview would rely on an unsupported value."""


class MissingLogisticsInput(AgricultureLogisticsError):
    """Raised when a required value is unknown rather than explicitly zero."""


class RouteMode(StrEnum):
    ROAD = "road"
    CANAL = "canal"


class OwnershipStatus(StrEnum):
    BAEN_OWNED = "baen_owned"
    THIRD_PARTY = "third_party"
    UNKNOWN = "unknown"


def _context() -> Context:
    return Context(
        prec=40,
        rounding=ROUND_HALF_EVEN,
        Emin=-999999,
        Emax=999999,
        capitals=1,
        clamp=0,
    )


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise AgricultureLogisticsError(f"{label} must be clean non-empty text")
    return value


def _source_value(value: object, label: str) -> SourcedValue[object]:
    if not isinstance(value, SourcedValue):
        raise AgricultureLogisticsError(f"{label} must be a SourcedValue")
    return value


def _decimal(
    source: SourcedValue[Decimal],
    label: str,
    *,
    allow_missing: bool = True,
) -> Decimal | None:
    sourced = _source_value(source, label)
    value = sourced.value
    if value is None:
        if allow_missing:
            return None
        raise MissingLogisticsInput(f"{label} is unknown; zero was not assumed")
    if type(value) is not Decimal or not value.is_finite():
        raise AgricultureLogisticsError(f"{label} must be a finite Decimal")
    return value


def _nonnegative_decimal(
    source: SourcedValue[Decimal],
    label: str,
    *,
    allow_missing: bool = True,
) -> Decimal | None:
    value = _decimal(source, label, allow_missing=allow_missing)
    if value is not None and value < ZERO:
        raise AgricultureLogisticsError(f"{label} cannot be negative")
    return value


def _positive_decimal(
    source: SourcedValue[Decimal],
    label: str,
    *,
    allow_missing: bool = True,
) -> Decimal | None:
    value = _decimal(source, label, allow_missing=allow_missing)
    if value is not None and value <= ZERO:
        raise AgricultureLogisticsError(f"{label} must be greater than zero")
    return value


def _rate(
    source: SourcedValue[Decimal],
    label: str,
    *,
    allow_missing: bool = True,
) -> Decimal | None:
    value = _decimal(source, label, allow_missing=allow_missing)
    if value is not None and not ZERO <= value <= ONE:
        raise AgricultureLogisticsError(f"{label} must be between zero and one")
    return value


def _nonnegative_int(
    source: SourcedValue[int],
    label: str,
    *,
    allow_missing: bool = True,
) -> int | None:
    sourced = _source_value(source, label)
    value = sourced.value
    if value is None:
        if allow_missing:
            return None
        raise MissingLogisticsInput(f"{label} is unknown; zero was not assumed")
    if type(value) is not int or value < 0:
        raise AgricultureLogisticsError(f"{label} must be a non-negative integer")
    return value


@dataclass(frozen=True, slots=True)
class VehicleCapacitySpecification:
    """A caller-supplied, evidenced per-trip vehicle or vessel capacity."""

    designation: str
    mode: RouteMode
    capacity_tons_per_trip: SourcedValue[Decimal]

    def __post_init__(self) -> None:
        _text(self.designation, "capacity designation")
        if not isinstance(self.mode, RouteMode):
            raise AgricultureLogisticsError("capacity mode must be road or canal")
        _positive_decimal(
            self.capacity_tons_per_trip,
            "vehicle capacity tons per trip",
        )


def barge_100_ton_spec(
    *, capacity_tons_per_trip: SourcedValue[Decimal]
) -> VehicleCapacitySpecification:
    """Validate, rather than invent, a source-backed 100-ton canal barge spec."""

    value = _positive_decimal(
        capacity_tons_per_trip,
        "100-ton barge capacity",
        allow_missing=False,
    )
    if value != Decimal("100"):
        raise AgricultureLogisticsError(
            "the 100-ton barge helper requires an evidenced value of exactly 100"
        )
    return VehicleCapacitySpecification(
        designation="100-ton barge",
        mode=RouteMode.CANAL,
        capacity_tons_per_trip=capacity_tons_per_trip,
    )


def heavy_barge_150_ton_spec(
    *, capacity_tons_per_trip: SourcedValue[Decimal]
) -> VehicleCapacitySpecification:
    """Validate, rather than invent, a source-backed 150-ton heavy barge spec."""

    value = _positive_decimal(
        capacity_tons_per_trip,
        "150-ton heavy barge capacity",
        allow_missing=False,
    )
    if value != Decimal("150"):
        raise AgricultureLogisticsError(
            "the 150-ton heavy-barge helper requires an evidenced value of exactly 150"
        )
    return VehicleCapacitySpecification(
        designation="150-ton heavy barge",
        mode=RouteMode.CANAL,
        capacity_tons_per_trip=capacity_tons_per_trip,
    )


@dataclass(frozen=True, slots=True)
class RouteLeg:
    """One explicitly supplied road or canal leg.

    Timing is optional.  ``transit_duration_days`` is used when supplied;
    otherwise duration is calculated only when both distance and speed are
    supplied.  No route lookup or default speed exists here.
    """

    leg_id: str
    origin_site_id: str
    destination_site_id: str
    mode: RouteMode
    capacity_tons_per_trip: SourcedValue[Decimal]
    trips_available: SourcedValue[int]
    loss_rate: SourcedValue[Decimal]
    transit_duration_days: SourcedValue[Decimal] | None = None
    distance_miles: SourcedValue[Decimal] | None = None
    speed_miles_per_day: SourcedValue[Decimal] | None = None

    def __post_init__(self) -> None:
        for value, label in (
            (self.leg_id, "route leg ID"),
            (self.origin_site_id, "route origin site ID"),
            (self.destination_site_id, "route destination site ID"),
        ):
            _text(value, label)
        if self.origin_site_id == self.destination_site_id:
            raise AgricultureLogisticsError(
                "route origin and destination must be different"
            )
        if not isinstance(self.mode, RouteMode):
            raise AgricultureLogisticsError("route mode must be road or canal")
        _nonnegative_decimal(
            self.capacity_tons_per_trip, "route capacity tons per trip"
        )
        _nonnegative_int(self.trips_available, "route trips available")
        _rate(self.loss_rate, "route loss rate")
        if self.transit_duration_days is not None:
            _nonnegative_decimal(
                self.transit_duration_days, "route transit duration days"
            )
        if self.distance_miles is not None:
            _nonnegative_decimal(self.distance_miles, "route distance miles")
        if self.speed_miles_per_day is not None:
            _positive_decimal(self.speed_miles_per_day, "route speed miles per day")
        # When all timing inputs are known, contradictory claims fail closed.
        explicit = self._known_optional_decimal(
            self.transit_duration_days, "route transit duration days"
        )
        distance = self._known_optional_decimal(
            self.distance_miles, "route distance miles"
        )
        speed = self._known_optional_decimal(
            self.speed_miles_per_day, "route speed miles per day"
        )
        if explicit is not None and distance is not None and speed is not None:
            with localcontext(_context()):
                calculated = distance / speed
            if calculated != explicit:
                raise AgricultureLogisticsError(
                    "explicit route duration conflicts with supplied distance and speed"
                )

    @staticmethod
    def _known_optional_decimal(
        value: SourcedValue[Decimal] | None, label: str
    ) -> Decimal | None:
        if value is None:
            return None
        return _decimal(value, label)

    @property
    def calculated_transit_days(self) -> Decimal | None:
        explicit = self._known_optional_decimal(
            self.transit_duration_days, "route transit duration days"
        )
        if explicit is not None:
            return explicit
        distance = self._known_optional_decimal(
            self.distance_miles, "route distance miles"
        )
        speed = self._known_optional_decimal(
            self.speed_miles_per_day, "route speed miles per day"
        )
        if distance is None or speed is None:
            return None
        with localcontext(_context()):
            return distance / speed


@dataclass(frozen=True, slots=True)
class StorageFacility:
    """Destination capacity and lot-specific holding-loss assumptions.

    Cold capacity is a subset of total capacity.  Rates apply only to the newly
    admitted lot for ``holding_period_label``; opening inventory consumes space
    but is not itself aged by this preview.
    """

    facility_id: str
    name: str
    owner_entity_id: str
    ownership_status: OwnershipStatus
    holding_period_label: str
    total_capacity_tons: SourcedValue[Decimal]
    cold_capacity_tons: SourcedValue[Decimal]
    opening_inventory_tons: SourcedValue[Decimal]
    opening_cold_inventory_tons: SourcedValue[Decimal]
    ambient_spoilage_rate: SourcedValue[Decimal]
    cold_spoilage_rate: SourcedValue[Decimal]

    def __post_init__(self) -> None:
        for value, label in (
            (self.facility_id, "storage facility ID"),
            (self.name, "storage facility name"),
            (self.owner_entity_id, "storage owner entity ID"),
            (self.holding_period_label, "storage holding-period label"),
        ):
            _text(value, label)
        if not isinstance(self.ownership_status, OwnershipStatus):
            raise AgricultureLogisticsError("storage ownership status is invalid")
        total = _nonnegative_decimal(
            self.total_capacity_tons, "total storage capacity tons"
        )
        cold = _nonnegative_decimal(
            self.cold_capacity_tons, "cold storage capacity tons"
        )
        opening = _nonnegative_decimal(
            self.opening_inventory_tons, "opening storage inventory tons"
        )
        opening_cold = _nonnegative_decimal(
            self.opening_cold_inventory_tons,
            "opening cold-storage inventory tons",
        )
        _rate(self.ambient_spoilage_rate, "ambient spoilage rate")
        _rate(self.cold_spoilage_rate, "cold spoilage rate")
        if total is not None and cold is not None and cold > total:
            raise AgricultureLogisticsError(
                "cold storage capacity cannot exceed total storage capacity"
            )
        if total is not None and opening is not None and opening > total:
            raise AgricultureLogisticsError(
                "opening inventory cannot exceed total storage capacity"
            )
        if cold is not None and opening_cold is not None and opening_cold > cold:
            raise AgricultureLogisticsError(
                "opening cold inventory cannot exceed cold capacity"
            )
        if (
            opening is not None
            and opening_cold is not None
            and opening_cold > opening
        ):
            raise AgricultureLogisticsError(
                "opening cold inventory cannot exceed total opening inventory"
            )


@dataclass(frozen=True, slots=True)
class ShipmentPlan:
    shipment_id: str
    commodity_id: str
    requested_quantity_tons: SourcedValue[Decimal]
    cold_storage_requested_tons: SourcedValue[Decimal]
    route_legs: tuple[RouteLeg, ...]

    def __post_init__(self) -> None:
        _text(self.shipment_id, "shipment ID")
        _text(self.commodity_id, "shipment commodity ID")
        requested = _nonnegative_decimal(
            self.requested_quantity_tons, "requested shipment tons"
        )
        cold = _nonnegative_decimal(
            self.cold_storage_requested_tons,
            "requested cold-storage tons",
        )
        if requested is not None and cold is not None and cold > requested:
            raise AgricultureLogisticsError(
                "requested cold-storage quantity cannot exceed shipment quantity"
            )
        if not self.route_legs:
            raise AgricultureLogisticsError(
                "shipment plan requires at least one explicit route leg"
            )
        if any(not isinstance(leg, RouteLeg) for leg in self.route_legs):
            raise AgricultureLogisticsError("shipment route has an invalid leg")
        ids = [leg.leg_id for leg in self.route_legs]
        if len(ids) != len(set(ids)):
            raise AgricultureLogisticsError("shipment route leg IDs must be unique")
        for previous, current in zip(self.route_legs, self.route_legs[1:]):
            if previous.destination_site_id != current.origin_site_id:
                raise AgricultureLogisticsError(
                    "shipment route legs must form a contiguous path"
                )


@dataclass(frozen=True, slots=True)
class RouteLegReceipt:
    leg_id: str
    mode: RouteMode
    incoming_tons: Decimal
    capacity_tons_per_trip: Decimal
    trips_available: int
    required_trips: int | None
    trip_requirement_status: str
    trips_scheduled: int
    dispatched_tons: Decimal
    held_tons: Decimal
    route_loss_tons: Decimal
    arrived_tons: Decimal
    transit_days: Decimal | None

    def __post_init__(self) -> None:
        _text(self.leg_id, "route receipt leg ID")
        if not isinstance(self.mode, RouteMode):
            raise AgricultureLogisticsError("route receipt mode is invalid")
        for value, label in (
            (self.incoming_tons, "route incoming tons"),
            (self.capacity_tons_per_trip, "route per-trip capacity"),
            (self.dispatched_tons, "route dispatched tons"),
            (self.held_tons, "route held tons"),
            (self.route_loss_tons, "route loss tons"),
            (self.arrived_tons, "route arrival tons"),
        ):
            if type(value) is not Decimal or not value.is_finite() or value < ZERO:
                raise AgricultureLogisticsError(
                    f"{label} must be a finite non-negative Decimal"
                )
        if type(self.trips_available) is not int or self.trips_available < 0:
            raise AgricultureLogisticsError("route trips available is invalid")
        if self.required_trips is not None and (
            type(self.required_trips) is not int or self.required_trips < 0
        ):
            raise AgricultureLogisticsError("route required trips is invalid")
        if type(self.trips_scheduled) is not int or self.trips_scheduled < 0:
            raise AgricultureLogisticsError("route trips scheduled is invalid")
        if self.trips_scheduled > self.trips_available:
            raise AgricultureLogisticsError(
                "scheduled trips cannot exceed available trips"
            )
        _text(self.trip_requirement_status, "trip requirement status")
        if self.transit_days is not None and (
            type(self.transit_days) is not Decimal
            or not self.transit_days.is_finite()
            or self.transit_days < ZERO
        ):
            raise AgricultureLogisticsError(
                "route receipt transit days must be non-negative or unknown"
            )
        with localcontext(_context()):
            if self.dispatched_tons + self.held_tons != self.incoming_tons:
                raise AgricultureLogisticsError(
                    "route receipt does not conserve incoming quantity"
                )
            if self.route_loss_tons + self.arrived_tons != self.dispatched_tons:
                raise AgricultureLogisticsError(
                    "route receipt does not conserve dispatched quantity"
                )


@dataclass(frozen=True, slots=True)
class RoutePlanReceipt:
    shipment_id: str
    requested_tons: Decimal
    legs: tuple[RouteLegReceipt, ...]
    held_for_capacity_tons: Decimal
    route_loss_tons: Decimal
    destination_arrival_tons: Decimal
    total_transit_days: Decimal | None
    conservation_residual_tons: Decimal

    def __post_init__(self) -> None:
        _text(self.shipment_id, "route-plan shipment ID")
        if not self.legs:
            raise AgricultureLogisticsError("route-plan receipt requires legs")
        for value, label in (
            (self.requested_tons, "route requested tons"),
            (self.held_for_capacity_tons, "route held tons"),
            (self.route_loss_tons, "total route loss tons"),
            (self.destination_arrival_tons, "destination arrival tons"),
        ):
            if type(value) is not Decimal or not value.is_finite() or value < ZERO:
                raise AgricultureLogisticsError(
                    f"{label} must be a finite non-negative Decimal"
                )
        if type(self.conservation_residual_tons) is not Decimal:
            raise AgricultureLogisticsError(
                "route conservation residual must be a Decimal"
            )
        if self.conservation_residual_tons != ZERO:
            raise AgricultureLogisticsError("route plan failed conservation")


@dataclass(frozen=True, slots=True)
class StorageReceipt:
    facility_id: str
    owner_entity_id: str
    ownership_status: OwnershipStatus
    arrived_tons: Decimal
    available_capacity_tons: Decimal
    admitted_tons: Decimal
    overflow_tons: Decimal
    cold_requested_tons: Decimal
    cold_stored_before_loss_tons: Decimal
    ambient_stored_before_loss_tons: Decimal
    cold_capacity_shortfall_tons: Decimal
    cold_spoilage_tons: Decimal
    ambient_spoilage_tons: Decimal
    retained_after_spoilage_tons: Decimal
    conservation_residual_tons: Decimal

    def __post_init__(self) -> None:
        _text(self.facility_id, "storage receipt facility ID")
        _text(self.owner_entity_id, "storage receipt owner entity ID")
        if not isinstance(self.ownership_status, OwnershipStatus):
            raise AgricultureLogisticsError(
                "storage receipt ownership status is invalid"
            )
        for value in (
            self.arrived_tons,
            self.available_capacity_tons,
            self.admitted_tons,
            self.overflow_tons,
            self.cold_requested_tons,
            self.cold_stored_before_loss_tons,
            self.ambient_stored_before_loss_tons,
            self.cold_capacity_shortfall_tons,
            self.cold_spoilage_tons,
            self.ambient_spoilage_tons,
            self.retained_after_spoilage_tons,
        ):
            if type(value) is not Decimal or not value.is_finite() or value < ZERO:
                raise AgricultureLogisticsError(
                    "storage receipt quantities must be finite non-negative Decimals"
                )
        if type(self.conservation_residual_tons) is not Decimal:
            raise AgricultureLogisticsError(
                "storage conservation residual must be a Decimal"
            )
        if self.conservation_residual_tons != ZERO:
            raise AgricultureLogisticsError("storage plan failed conservation")


@dataclass(frozen=True, slots=True)
class LogisticsPlanReceipt:
    """Non-mutating result for one sourced shipment planning preview."""

    shipment_id: str
    route: RoutePlanReceipt
    storage: StorageReceipt
    held_for_capacity_tons: Decimal
    route_loss_tons: Decimal
    storage_overflow_tons: Decimal
    storage_spoilage_tons: Decimal
    retained_after_storage_tons: Decimal
    conservation_residual_tons: Decimal
    preview_only: bool = True

    def __post_init__(self) -> None:
        _text(self.shipment_id, "logistics receipt shipment ID")
        if self.preview_only is not True:
            raise AgricultureLogisticsError(
                "agriculture logistics receipts must remain preview-only"
            )
        if type(self.conservation_residual_tons) is not Decimal:
            raise AgricultureLogisticsError(
                "logistics conservation residual must be a Decimal"
            )
        if self.conservation_residual_tons != ZERO:
            raise AgricultureLogisticsError("logistics plan failed conservation")


def _trip_requirement(quantity: Decimal, per_trip: Decimal) -> tuple[int | None, str]:
    if quantity == ZERO:
        return 0, "not_required"
    if per_trip == ZERO:
        return None, "impossible_zero_capacity"
    with localcontext(_context()):
        quotient = quantity / per_trip
        required = int(quotient.to_integral_value(rounding=ROUND_CEILING))
    return required, "calculated"


def plan_route(shipment: ShipmentPlan) -> RoutePlanReceipt:
    """Plan source-limited movement across every explicit route leg."""

    if not isinstance(shipment, ShipmentPlan):
        raise AgricultureLogisticsError("route planning requires a ShipmentPlan")
    requested = _nonnegative_decimal(
        shipment.requested_quantity_tons,
        "requested shipment tons",
        allow_missing=False,
    )
    incoming = requested
    receipts: list[RouteLegReceipt] = []
    held_total = ZERO
    loss_total = ZERO
    known_total_days = ZERO
    timing_complete = True

    for leg in shipment.route_legs:
        capacity = _nonnegative_decimal(
            leg.capacity_tons_per_trip,
            f"route {leg.leg_id} capacity tons per trip",
            allow_missing=False,
        )
        trips_available = _nonnegative_int(
            leg.trips_available,
            f"route {leg.leg_id} trips available",
            allow_missing=False,
        )
        loss_rate = _rate(
            leg.loss_rate,
            f"route {leg.leg_id} loss rate",
            allow_missing=False,
        )
        required_trips, requirement_status = _trip_requirement(incoming, capacity)
        with localcontext(_context()):
            available_capacity = capacity * Decimal(trips_available)
            dispatched = min(incoming, available_capacity)
            held = incoming - dispatched
            loss = dispatched * loss_rate
            arrived = dispatched - loss
        if required_trips is None:
            scheduled = 0
        else:
            scheduled = min(required_trips, trips_available)
        duration = leg.calculated_transit_days
        if duration is None:
            timing_complete = False
        else:
            with localcontext(_context()):
                known_total_days += duration
        receipts.append(
            RouteLegReceipt(
                leg_id=leg.leg_id,
                mode=leg.mode,
                incoming_tons=incoming,
                capacity_tons_per_trip=capacity,
                trips_available=trips_available,
                required_trips=required_trips,
                trip_requirement_status=requirement_status,
                trips_scheduled=scheduled,
                dispatched_tons=dispatched,
                held_tons=held,
                route_loss_tons=loss,
                arrived_tons=arrived,
                transit_days=duration,
            )
        )
        with localcontext(_context()):
            held_total += held
            loss_total += loss
        incoming = arrived

    with localcontext(_context()):
        residual = requested - held_total - loss_total - incoming
    return RoutePlanReceipt(
        shipment_id=shipment.shipment_id,
        requested_tons=requested,
        legs=tuple(receipts),
        held_for_capacity_tons=held_total,
        route_loss_tons=loss_total,
        destination_arrival_tons=incoming,
        total_transit_days=known_total_days if timing_complete else None,
        conservation_residual_tons=residual,
    )


def plan_storage(
    facility: StorageFacility,
    *,
    arrived_tons: Decimal,
    cold_requested_tons: Decimal,
) -> StorageReceipt:
    """Allocate one arriving lot, retaining overflow as an explicit quantity."""

    if not isinstance(facility, StorageFacility):
        raise AgricultureLogisticsError("storage planning requires a StorageFacility")
    if type(arrived_tons) is not Decimal or not arrived_tons.is_finite():
        raise AgricultureLogisticsError("storage arrival must be a finite Decimal")
    if type(cold_requested_tons) is not Decimal or not cold_requested_tons.is_finite():
        raise AgricultureLogisticsError(
            "storage cold request must be a finite Decimal"
        )
    if arrived_tons < ZERO or cold_requested_tons < ZERO:
        raise AgricultureLogisticsError("storage quantities cannot be negative")

    total_capacity = _nonnegative_decimal(
        facility.total_capacity_tons,
        "total storage capacity tons",
        allow_missing=False,
    )
    cold_capacity = _nonnegative_decimal(
        facility.cold_capacity_tons,
        "cold storage capacity tons",
        allow_missing=False,
    )
    opening = _nonnegative_decimal(
        facility.opening_inventory_tons,
        "opening storage inventory tons",
        allow_missing=False,
    )
    opening_cold = _nonnegative_decimal(
        facility.opening_cold_inventory_tons,
        "opening cold-storage inventory tons",
        allow_missing=False,
    )

    with localcontext(_context()):
        available = total_capacity - opening
        cold_available = cold_capacity - opening_cold
        admitted = min(arrived_tons, available)
        overflow = arrived_tons - admitted
        # Cold-requested goods receive first claim on admitted and cold space.
        requested_in_admitted = min(cold_requested_tons, admitted)
        cold_stored = min(requested_in_admitted, cold_available)
        ambient_stored = admitted - cold_stored
        cold_shortfall = requested_in_admitted - cold_stored

    if cold_stored == ZERO:
        cold_rate = ZERO
    else:
        cold_rate = _rate(
            facility.cold_spoilage_rate,
            "cold spoilage rate",
            allow_missing=False,
        )
    if ambient_stored == ZERO:
        ambient_rate = ZERO
    else:
        ambient_rate = _rate(
            facility.ambient_spoilage_rate,
            "ambient spoilage rate",
            allow_missing=False,
        )

    with localcontext(_context()):
        cold_loss = cold_stored * cold_rate
        ambient_loss = ambient_stored * ambient_rate
        retained = admitted - cold_loss - ambient_loss
        residual = arrived_tons - overflow - cold_loss - ambient_loss - retained
    return StorageReceipt(
        facility_id=facility.facility_id,
        owner_entity_id=facility.owner_entity_id,
        ownership_status=facility.ownership_status,
        arrived_tons=arrived_tons,
        available_capacity_tons=available,
        admitted_tons=admitted,
        overflow_tons=overflow,
        cold_requested_tons=min(cold_requested_tons, arrived_tons),
        cold_stored_before_loss_tons=cold_stored,
        ambient_stored_before_loss_tons=ambient_stored,
        cold_capacity_shortfall_tons=cold_shortfall,
        cold_spoilage_tons=cold_loss,
        ambient_spoilage_tons=ambient_loss,
        retained_after_spoilage_tons=retained,
        conservation_residual_tons=residual,
    )


def plan_logistics(
    shipment: ShipmentPlan,
    destination_storage: StorageFacility,
) -> LogisticsPlanReceipt:
    """Return a fully conserved route-and-storage planning preview."""

    route = plan_route(shipment)
    cold_requested = _nonnegative_decimal(
        shipment.cold_storage_requested_tons,
        "requested cold-storage tons",
        allow_missing=False,
    )
    storage = plan_storage(
        destination_storage,
        arrived_tons=route.destination_arrival_tons,
        cold_requested_tons=min(cold_requested, route.destination_arrival_tons),
    )
    with localcontext(_context()):
        storage_loss = storage.cold_spoilage_tons + storage.ambient_spoilage_tons
        residual = (
            route.requested_tons
            - route.held_for_capacity_tons
            - route.route_loss_tons
            - storage.overflow_tons
            - storage_loss
            - storage.retained_after_spoilage_tons
        )
    return LogisticsPlanReceipt(
        shipment_id=shipment.shipment_id,
        route=route,
        storage=storage,
        held_for_capacity_tons=route.held_for_capacity_tons,
        route_loss_tons=route.route_loss_tons,
        storage_overflow_tons=storage.overflow_tons,
        storage_spoilage_tons=storage_loss,
        retained_after_storage_tons=storage.retained_after_spoilage_tons,
        conservation_residual_tons=residual,
    )
