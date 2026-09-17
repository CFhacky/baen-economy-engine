"""Side-effect-free, multi-period agriculture inventory planning.

This module evaluates explicit user assumptions.  It does not read or mutate
campaign state, advance a campaign calendar, roll dice, or create financial
postings.  Period labels are display labels only.

For each location/commodity row, the engine applies this balance in order::

    gross available = opening + production + inbound
    usable available = gross available - storage loss
    fulfilled demand = min(usable available, requested uses)
    pre-capacity close = usable available - fulfilled demand
    closing = pre-capacity close - capacity overflow

Storage loss is applied before requested consumption, processing, and outbound
uses.  Storage capacity is applied after those uses.  Because the inputs do not
declare a priority among the three uses, the engine reports only aggregate
fulfilled and unmet demand; it does not invent an allocation priority.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
import hashlib
import json


ZERO = Decimal("0")
ONE = Decimal("1")
AGRICULTURE_PLANNING_SCHEMA = "tnp.economy.agriculture-planning/1"
PLANNING_ONLY = True


class AgriculturePlanningError(ValueError):
    """Raised when assumptions are missing, contradictory, or invalid."""


class AgricultureConservationError(RuntimeError):
    """Raised if an internal row balance does not conserve stock."""


def _require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AgriculturePlanningError(f"{label} is required")
    return value


def _require_nonnegative_decimal(value: object, label: str) -> Decimal:
    # Strictly require Decimal so that an omitted value (None), a float, and an
    # explicit Decimal("0") remain three observably different inputs.
    if type(value) is not Decimal or not value.is_finite():
        raise AgriculturePlanningError(
            f"{label} must be an explicit finite Decimal; missing is not zero"
        )
    if value < ZERO:
        raise AgriculturePlanningError(f"{label} cannot be negative")
    return value


def _decimal_text(value: Decimal) -> str:
    """Return a deterministic, lossless JSON representation for a Decimal."""

    if type(value) is not Decimal or not value.is_finite():
        raise AgriculturePlanningError("canonical values must be finite Decimals")
    return str(value).replace("e", "E")


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True, order=True)
class StockKey:
    """One independently conserved inventory stream."""

    location_id: str
    commodity_id: str
    unit: str

    def __post_init__(self) -> None:
        _require_text(self.location_id, "location ID")
        _require_text(self.commodity_id, "commodity ID")
        _require_text(self.unit, "commodity unit")

    def to_dict(self) -> dict[str, str]:
        return {
            "commodity_id": self.commodity_id,
            "location_id": self.location_id,
            "unit": self.unit,
        }


@dataclass(frozen=True, slots=True, order=True)
class OpeningInventory:
    """Explicit opening inventory assumption for one stock stream."""

    key: StockKey
    quantity: Decimal | None

    def __post_init__(self) -> None:
        if type(self.key) is not StockKey:
            raise AgriculturePlanningError("opening inventory key has the wrong type")
        _require_nonnegative_decimal(self.quantity, "opening inventory")

    def to_dict(self) -> dict[str, object]:
        return {**self.key.to_dict(), "quantity": _decimal_text(self.quantity)}


@dataclass(frozen=True, slots=True)
class PeriodFlowAssumption:
    """All required planning assumptions for one stream and one period.

    Exactly one loss method must be supplied.  ``Decimal("0")`` is an explicit
    zero assumption; ``None`` is missing and is rejected for every required
    numeric field.
    """

    key: StockKey
    production: Decimal | None
    inbound: Decimal | None
    consumption: Decimal | None
    outbound: Decimal | None
    processing_use: Decimal | None
    capacity: Decimal | None
    loss_rate: Decimal | None = None
    absolute_loss: Decimal | None = None

    def __post_init__(self) -> None:
        if type(self.key) is not StockKey:
            raise AgriculturePlanningError("period flow key has the wrong type")
        for value, label in (
            (self.production, "production"),
            (self.inbound, "inbound"),
            (self.consumption, "consumption"),
            (self.outbound, "outbound"),
            (self.processing_use, "processing use"),
            (self.capacity, "storage capacity"),
        ):
            _require_nonnegative_decimal(value, label)

        has_rate = self.loss_rate is not None
        has_absolute = self.absolute_loss is not None
        if has_rate == has_absolute:
            raise AgriculturePlanningError(
                "exactly one of loss_rate or absolute_loss must be supplied"
            )
        if has_rate:
            rate = _require_nonnegative_decimal(self.loss_rate, "loss rate")
            if rate > ONE:
                raise AgriculturePlanningError("loss rate must be in [0, 1]")
        else:
            _require_nonnegative_decimal(self.absolute_loss, "absolute loss")

    @property
    def loss_method(self) -> str:
        return "rate" if self.loss_rate is not None else "absolute"

    def to_dict(self) -> dict[str, object]:
        return {
            **self.key.to_dict(),
            "absolute_loss": (
                None
                if self.absolute_loss is None
                else _decimal_text(self.absolute_loss)
            ),
            "capacity": _decimal_text(self.capacity),
            "consumption": _decimal_text(self.consumption),
            "inbound": _decimal_text(self.inbound),
            "loss_rate": (
                None if self.loss_rate is None else _decimal_text(self.loss_rate)
            ),
            "outbound": _decimal_text(self.outbound),
            "processing_use": _decimal_text(self.processing_use),
            "production": _decimal_text(self.production),
        }


@dataclass(frozen=True, slots=True)
class PlanningPeriod:
    """A numbered planning bucket; its label has no campaign-time semantics."""

    period_index: int
    period_label: str
    flows: tuple[PeriodFlowAssumption, ...]

    def __post_init__(self) -> None:
        if type(self.period_index) is not int or self.period_index < 1:
            raise AgriculturePlanningError("period index must be an integer at least 1")
        _require_text(self.period_label, "period label")
        if type(self.flows) is not tuple or not self.flows:
            raise AgriculturePlanningError("period flows must be a non-empty tuple")
        if any(type(flow) is not PeriodFlowAssumption for flow in self.flows):
            raise AgriculturePlanningError("period flows contain a value of the wrong type")
        keys = [flow.key for flow in self.flows]
        if len(keys) != len(set(keys)):
            raise AgriculturePlanningError(
                f"period {self.period_index} contains a duplicate stock stream"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "flows": [flow.to_dict() for flow in sorted(self.flows, key=lambda x: x.key)],
            "period_index": self.period_index,
            "period_label": self.period_label,
        }


@dataclass(frozen=True, slots=True)
class AgriculturePlan:
    """Complete, explicit user-assumption planning scenario."""

    scenario_id: str
    scenario_name: str
    assumption_source: str
    openings: tuple[OpeningInventory, ...]
    periods: tuple[PlanningPeriod, ...]

    def __post_init__(self) -> None:
        _require_text(self.scenario_id, "scenario ID")
        _require_text(self.scenario_name, "scenario name")
        _require_text(self.assumption_source, "user-assumption source")
        if type(self.openings) is not tuple or not self.openings:
            raise AgriculturePlanningError(
                "opening inventories must be a non-empty tuple"
            )
        if any(type(item) is not OpeningInventory for item in self.openings):
            raise AgriculturePlanningError(
                "opening inventories contain a value of the wrong type"
            )
        opening_keys = [item.key for item in self.openings]
        if len(opening_keys) != len(set(opening_keys)):
            raise AgriculturePlanningError("opening inventory has a duplicate stock stream")

        if type(self.periods) is not tuple or not self.periods:
            raise AgriculturePlanningError("planning periods must be a non-empty tuple")
        if any(type(period) is not PlanningPeriod for period in self.periods):
            raise AgriculturePlanningError(
                "planning periods contain a value of the wrong type"
            )
        indexes = [period.period_index for period in self.periods]
        expected_indexes = list(range(1, len(self.periods) + 1))
        if sorted(indexes) != expected_indexes:
            raise AgriculturePlanningError(
                "period indexes must be unique and contiguous starting at 1"
            )

        expected_keys = set(opening_keys)
        for period in self.periods:
            actual_keys = {flow.key for flow in period.flows}
            missing = sorted(expected_keys - actual_keys)
            unexpected = sorted(actual_keys - expected_keys)
            if missing or unexpected:
                details: list[str] = []
                if missing:
                    details.append(
                        "missing "
                        + ", ".join(
                            f"{key.location_id}/{key.commodity_id}" for key in missing
                        )
                    )
                if unexpected:
                    details.append(
                        "unexpected "
                        + ", ".join(
                            f"{key.location_id}/{key.commodity_id}"
                            for key in unexpected
                        )
                    )
                raise AgriculturePlanningError(
                    f"period {period.period_index} stock streams do not match openings: "
                    + "; ".join(details)
                )

    def to_dict(self) -> dict[str, object]:
        return {
            "assumption_authority": "user_assumption",
            "assumption_source": self.assumption_source,
            "kind": "agriculture_planning_assumptions",
            "openings": [
                opening.to_dict() for opening in sorted(self.openings, key=lambda x: x.key)
            ],
            "periods": [
                period.to_dict()
                for period in sorted(self.periods, key=lambda x: x.period_index)
            ],
            "planning_only": True,
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "schema": AGRICULTURE_PLANNING_SCHEMA,
        }

    def to_json(self) -> str:
        """Serialize assumptions canonically, independent of tuple ordering."""

        return _canonical_json(self.to_dict())

    @property
    def scenario_hash(self) -> str:
        return _sha256(self.to_json())


@dataclass(frozen=True, slots=True)
class AgricultureRowResult:
    period_index: int
    period_label: str
    key: StockKey
    opening_inventory: Decimal
    production: Decimal
    inbound: Decimal
    gross_available: Decimal
    loss_method: str
    loss_rate: Decimal | None
    absolute_loss_assumption: Decimal | None
    loss: Decimal
    usable_available: Decimal
    requested_consumption: Decimal
    requested_processing_use: Decimal
    requested_outbound: Decimal
    total_requested_demand: Decimal
    fulfilled_demand: Decimal
    unmet_demand: Decimal
    capacity: Decimal
    capacity_overflow: Decimal
    closing_inventory: Decimal
    balance_in: Decimal
    balance_out: Decimal
    conservation_residual: Decimal

    @property
    def shortage(self) -> Decimal:
        """Alias for aggregate unmet demand."""

        return self.unmet_demand

    @property
    def conserved(self) -> bool:
        return self.conservation_residual == ZERO

    def to_dict(self) -> dict[str, object]:
        return {
            **self.key.to_dict(),
            "absolute_loss_assumption": (
                None
                if self.absolute_loss_assumption is None
                else _decimal_text(self.absolute_loss_assumption)
            ),
            "capacity": _decimal_text(self.capacity),
            "capacity_overflow": _decimal_text(self.capacity_overflow),
            "closing_inventory": _decimal_text(self.closing_inventory),
            "conservation": {
                "balance_in": _decimal_text(self.balance_in),
                "balance_out": _decimal_text(self.balance_out),
                "passed": self.conserved,
                "residual": _decimal_text(self.conservation_residual),
            },
            "fulfilled_demand": _decimal_text(self.fulfilled_demand),
            "gross_available": _decimal_text(self.gross_available),
            "inbound": _decimal_text(self.inbound),
            "loss": _decimal_text(self.loss),
            "loss_method": self.loss_method,
            "loss_rate": (
                None if self.loss_rate is None else _decimal_text(self.loss_rate)
            ),
            "opening_inventory": _decimal_text(self.opening_inventory),
            "period_index": self.period_index,
            "period_label": self.period_label,
            "production": _decimal_text(self.production),
            "requested_consumption": _decimal_text(self.requested_consumption),
            "requested_outbound": _decimal_text(self.requested_outbound),
            "requested_processing_use": _decimal_text(self.requested_processing_use),
            "shortage": _decimal_text(self.shortage),
            "total_requested_demand": _decimal_text(self.total_requested_demand),
            "unmet_demand": _decimal_text(self.unmet_demand),
            "usable_available": _decimal_text(self.usable_available),
        }


@dataclass(frozen=True, slots=True)
class AgricultureSimulationResult:
    scenario_id: str
    scenario_name: str
    assumption_source: str
    scenario_hash: str
    rows: tuple[AgricultureRowResult, ...]

    @property
    def all_rows_conserved(self) -> bool:
        return all(row.conserved for row in self.rows)

    @property
    def result_hash(self) -> str:
        return _sha256(_canonical_json(self._payload()))

    def _payload(self) -> dict[str, object]:
        final_rows = [
            row
            for row in self.rows
            if row.period_index == max(item.period_index for item in self.rows)
        ]
        return {
            "all_rows_conserved": self.all_rows_conserved,
            "assumption_authority": "user_assumption",
            "assumption_source": self.assumption_source,
            "campaign_time_advanced": False,
            "final_inventory": [
                {
                    **row.key.to_dict(),
                    "quantity": _decimal_text(row.closing_inventory),
                }
                for row in sorted(final_rows, key=lambda x: x.key)
            ],
            "financial_postings_created": False,
            "kind": "agriculture_planning_result",
            "planning_only": True,
            "rows": [row.to_dict() for row in self.rows],
            "scenario_hash": self.scenario_hash,
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "schema": AGRICULTURE_PLANNING_SCHEMA,
        }

    def to_dict(self) -> dict[str, object]:
        payload = self._payload()
        payload["result_hash"] = self.result_hash
        return payload

    def to_json(self) -> str:
        """Serialize the evaluated plan with deterministic field and row order."""

        return _canonical_json(self.to_dict())


def _decimal_context_for(plan: AgriculturePlan) -> Context:
    """Size a fixed context so supplied finite decimals are not rounded.

    The largest possible coefficient in a row comes from aligning quantity
    scales and multiplying gross stock by a loss rate.  The conservative span
    below is deliberately larger than that bound and independent of the
    caller's ambient Decimal context.
    """

    values: list[Decimal] = [opening.quantity for opening in plan.openings]
    for period in plan.periods:
        for flow in period.flows:
            values.extend(
                value
                for value in (
                    flow.production,
                    flow.inbound,
                    flow.consumption,
                    flow.outbound,
                    flow.processing_use,
                    flow.capacity,
                    flow.loss_rate,
                    flow.absolute_loss,
                )
                if value is not None
            )
    maximum_integral = max(max(value.adjusted() + 1, 0) for value in values)
    maximum_fractional = max(max(-value.as_tuple().exponent, 0) for value in values)
    precision = max(
        50,
        maximum_integral
        + maximum_fractional * (len(plan.periods) + 2)
        + len(plan.periods)
        + 20,
    )
    return Context(prec=precision, rounding=ROUND_HALF_EVEN)


def simulate_agriculture(plan: AgriculturePlan) -> AgricultureSimulationResult:
    """Evaluate a planning scenario without mutating any external state."""

    if type(plan) is not AgriculturePlan:
        raise AgriculturePlanningError("plan has the wrong type")

    current_inventory = {opening.key: opening.quantity for opening in plan.openings}
    rows: list[AgricultureRowResult] = []

    with localcontext(_decimal_context_for(plan)):
        for period in sorted(plan.periods, key=lambda item: item.period_index):
            next_inventory: dict[StockKey, Decimal] = {}
            for flow in sorted(period.flows, key=lambda item: item.key):
                opening = current_inventory[flow.key]
                gross = opening + flow.production + flow.inbound
                if flow.loss_rate is not None:
                    loss = gross * flow.loss_rate
                else:
                    loss = flow.absolute_loss
                    if loss > gross:
                        raise AgriculturePlanningError(
                            "absolute loss exceeds gross available stock in "
                            f"period {period.period_index} for "
                            f"{flow.key.location_id}/{flow.key.commodity_id}"
                        )

                usable = gross - loss
                requested = flow.consumption + flow.processing_use + flow.outbound
                fulfilled = min(usable, requested)
                unmet = requested - fulfilled
                pre_capacity_closing = usable - fulfilled
                overflow = max(ZERO, pre_capacity_closing - flow.capacity)
                closing = pre_capacity_closing - overflow
                balance_in = gross
                balance_out = loss + fulfilled + overflow + closing
                residual = balance_in - balance_out
                if residual != ZERO:
                    raise AgricultureConservationError(
                        "stock conservation failed in "
                        f"period {period.period_index} for "
                        f"{flow.key.location_id}/{flow.key.commodity_id}: "
                        f"residual {_decimal_text(residual)}"
                    )

                row = AgricultureRowResult(
                    period_index=period.period_index,
                    period_label=period.period_label,
                    key=flow.key,
                    opening_inventory=opening,
                    production=flow.production,
                    inbound=flow.inbound,
                    gross_available=gross,
                    loss_method=flow.loss_method,
                    loss_rate=flow.loss_rate,
                    absolute_loss_assumption=flow.absolute_loss,
                    loss=loss,
                    usable_available=usable,
                    requested_consumption=flow.consumption,
                    requested_processing_use=flow.processing_use,
                    requested_outbound=flow.outbound,
                    total_requested_demand=requested,
                    fulfilled_demand=fulfilled,
                    unmet_demand=unmet,
                    capacity=flow.capacity,
                    capacity_overflow=overflow,
                    closing_inventory=closing,
                    balance_in=balance_in,
                    balance_out=balance_out,
                    conservation_residual=residual,
                )
                rows.append(row)
                next_inventory[flow.key] = closing
            current_inventory = next_inventory

    return AgricultureSimulationResult(
        scenario_id=plan.scenario_id,
        scenario_name=plan.scenario_name,
        assumption_source=plan.assumption_source,
        scenario_hash=plan.scenario_hash,
        rows=tuple(rows),
    )
