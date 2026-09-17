"""Source-bound Longsaddle grain-security planning.

This module is a non-mutating decision surface for the ratified late-Kythorn
1495 forward scenario.  It reads and cross-checks both reviewed source
fixtures, then evaluates only values supplied as explicit planning
assumptions.  A missing assumption remains ``None`` and makes each dependent
result unknown; it is never converted to numeric zero.

The physical route uses the same :class:`~baen_economy.stockflow.Route`
contract as the stock-flow engine.  Destination consumption and closing
storage use :func:`~baen_economy.agriculture_simulation.simulate_agriculture`.
The wrapper adds the decision-specific source, cost, funding, coverage, and
field-provenance views that those lower-level engines do not own.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_FLOOR, ROUND_HALF_EVEN, localcontext
from enum import StrEnum
import json
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from .agriculture_simulation import (
    AgriculturePlan,
    OpeningInventory,
    PeriodFlowAssumption,
    PlanningPeriod,
    StockKey,
    simulate_agriculture,
)
from .agriculture_source import (
    DEFAULT_AGRICULTURE_CANON_PATH,
    PROJECT_ROOT,
    load_agriculture_canon,
)
from .operator_codec import canonical_hash
from .source_values import exact_decimal
from .stockflow import Route


ZERO = Decimal("0")
ONE = Decimal("1")
FOOD_SECURITY_SCHEMA = "tnp.food-security.longsaddle-plan/1"
DEFAULT_LADEN_FIXTURE_PATH = (
    PROJECT_ROOT / "fixtures" / "canonical-import" / "operation-laden-table.json"
)


class FoodSecurityError(ValueError):
    """Raised when a source contract or explicit assumption is invalid."""


class FoodSecuritySourceError(FoodSecurityError):
    """Raised when either reviewed fixture has drifted or contradicts the other."""


class ObjectiveStatus(StrEnum):
    """Decision status for the supplied planning assumptions."""

    MET = "met"
    AT_RISK = "at_risk"
    FAILED = "failed"


class ProvenanceKind(StrEnum):
    """The four decision-brief authority buckets."""

    SOURCE = "Source"
    ASSUMPTION = "Assumption"
    DERIVED = "Derived"
    UNKNOWN = "Unknown"


def _context() -> Context:
    return Context(
        prec=50,
        rounding=ROUND_HALF_EVEN,
        Emin=-999999,
        Emax=999999,
        capitals=1,
        clamp=0,
    )


def _clean_text(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
    ):
        raise FoodSecurityError(f"{label} must be clean non-empty text")
    return value


def _optional_nonnegative_decimal(value: object, label: str) -> Decimal | None:
    if value is None:
        return None
    if type(value) is not Decimal or not value.is_finite():
        raise FoodSecurityError(
            f"{label} must be an explicit finite Decimal or None; missing is not zero"
        )
    if value < ZERO:
        raise FoodSecurityError(f"{label} cannot be negative")
    return value


def _optional_nonnegative_int(value: object, label: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise FoodSecurityError(
            f"{label} must be an explicit non-negative integer or None"
        )
    return value


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if type(value) is not Decimal or not value.is_finite():
        raise FoodSecurityError("result serialization requires finite Decimals")
    return str(value).replace("e", "E")


def _json_value(value: object) -> object:
    if type(value) is Decimal:
        return _decimal_text(value)
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


def _read_json(path: Path, label: str) -> Mapping[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FoodSecuritySourceError(f"cannot read {label}: {path}") from exc
    if not isinstance(raw, dict):
        raise FoodSecuritySourceError(f"{label} must contain a JSON object")
    return raw


def _source_decimal(value: object, label: str) -> Decimal:
    try:
        return exact_decimal(value, label=label)
    except ValueError as exc:
        raise FoodSecuritySourceError(str(exc)) from exc


def _source_range(value: object, label: str) -> tuple[Decimal, Decimal]:
    if not isinstance(value, Mapping) or set(value) != {"low", "high"}:
        raise FoodSecuritySourceError(f"{label} must contain exact low/high values")
    low = _source_decimal(value["low"], f"{label} low")
    high = _source_decimal(value["high"], f"{label} high")
    if low > high:
        raise FoodSecuritySourceError(f"{label} low cannot exceed high")
    return low, high


@dataclass(frozen=True, slots=True)
class FieldProvenance:
    """Why one source, assumption, result, or unknown field exists."""

    kind: ProvenanceKind
    basis: str
    source_ids: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ProvenanceKind):
            raise FoodSecurityError("field provenance kind is invalid")
        _clean_text(self.basis, "field provenance basis")
        for values, label in (
            (self.source_ids, "field provenance source IDs"),
            (self.dependencies, "field provenance dependencies"),
        ):
            if type(values) is not tuple or any(
                not isinstance(item, str) or not item for item in values
            ):
                raise FoodSecurityError(f"{label} must be an immutable text tuple")

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "basis": self.basis,
            "source_ids": list(self.source_ids),
            "dependencies": list(self.dependencies),
        }


@dataclass(frozen=True, slots=True)
class LongsaddleSourceFacts:
    """Cross-checked facts from the two reviewed late-Kythorn fixtures."""

    scenario_id: str
    timeline_id: str
    campaign_date: str
    population_mouths: int
    grain_target_low_tons: Decimal
    grain_target_high_tons: Decimal
    grain_procured_tons: Decimal
    grain_budget_low_gp: Decimal
    grain_budget_high_gp: Decimal
    harvest_window: str
    harvest_outcome: str
    actual_execution_eligible: bool
    source_refs: tuple[str, ...]

    @property
    def longsaddle_population(self) -> int:
        return self.population_mouths

    def to_dict(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "timeline_id": self.timeline_id,
            "campaign_date": self.campaign_date,
            "temporal_scope": "ratified_forward_scenario_not_current_actual",
            "actual_execution_eligible": self.actual_execution_eligible,
            "population_mouths": self.population_mouths,
            "grain_target_tons": {
                "low": _decimal_text(self.grain_target_low_tons),
                "high": _decimal_text(self.grain_target_high_tons),
            },
            "grain_procured_tons": _decimal_text(self.grain_procured_tons),
            "grain_budget_with_transport_gp": {
                "low": _decimal_text(self.grain_budget_low_gp),
                "high": _decimal_text(self.grain_budget_high_gp),
            },
            "harvest_window": self.harvest_window,
            "harvest_outcome": self.harvest_outcome,
            "source_refs": list(self.source_refs),
        }


def load_longsaddle_source_facts(
    *,
    project_root: Path | None = None,
    agriculture_canon_path: Path | None = None,
    laden_fixture_path: Path | None = None,
) -> LongsaddleSourceFacts:
    """Load both fixtures and fail closed unless their locked facts agree."""

    if project_root is not None:
        project_root = Path(project_root)
        if agriculture_canon_path is None:
            agriculture_canon_path = (
                project_root
                / "fixtures"
                / "agriculture"
                / "agriculture-canon-v1.json"
            )
        if laden_fixture_path is None:
            laden_fixture_path = (
                project_root
                / "fixtures"
                / "canonical-import"
                / "operation-laden-table.json"
            )
    canon_path = Path(agriculture_canon_path or DEFAULT_AGRICULTURE_CANON_PATH)
    laden_path = Path(laden_fixture_path or DEFAULT_LADEN_FIXTURE_PATH)

    try:
        canon = load_agriculture_canon(canon_path)
    except ValueError as exc:
        raise FoodSecuritySourceError(
            f"agriculture canon did not validate: {exc}"
        ) from exc
    laden = _read_json(laden_path, "Operation Laden canonical-import fixture")
    forward = canon.forward_k1495_state

    if laden.get("fixture_class") != "CAN-IMPORT":
        raise FoodSecuritySourceError("Operation Laden fixture class has drifted")
    if laden.get("authority") != "canon_import":
        raise FoodSecuritySourceError("Operation Laden authority has drifted")
    if laden.get("scenario_id") != "operation-laden-table":
        raise FoodSecuritySourceError("Operation Laden scenario ID has drifted")
    if laden.get("timeline_id") != "source:operation-laden-table-late-kythorn-1495":
        raise FoodSecuritySourceError("Operation Laden timeline ID has drifted")
    if laden.get("planning_date") != "Late Kythorn 1495 DR":
        raise FoodSecuritySourceError("Operation Laden planning date has drifted")
    if forward.campaign_date != "late Kythorn 1495 DR":
        raise FoodSecuritySourceError("agriculture forward date has drifted")
    if forward.actual_execution_eligible:
        raise FoodSecuritySourceError("forward scenario cannot become current actual")

    population = laden.get("population_mouths")
    if type(population) is not int or population != forward.longsaddle_population:
        raise FoodSecuritySourceError("Longsaddle population fixtures disagree")
    laden_target = _source_range(laden.get("grain_target_tons"), "Laden grain target")
    canon_target = (
        forward.grain_procurement_target_tons.low,
        forward.grain_procurement_target_tons.high,
    )
    if laden_target != canon_target:
        raise FoodSecuritySourceError("Longsaddle grain-target fixtures disagree")
    laden_budget = _source_range(
        laden.get("grain_including_transport_gp"),
        "Laden grain and transport budget",
    )
    canon_budget = (
        forward.grain_budget_with_transport_gp.low,
        forward.grain_budget_with_transport_gp.high,
    )
    if laden_budget != canon_budget:
        raise FoodSecuritySourceError("Longsaddle grain-budget fixtures disagree")
    if forward.grain_procured_tons != ZERO:
        raise FoodSecuritySourceError("forward procured grain is no longer locked at zero")
    if laden.get("resolved_or_source_recorded_transactions") != []:
        raise FoodSecuritySourceError(
            "Operation Laden unexpectedly contains a resolved transaction"
        )
    if forward.longsaddle_first_harvest_window != "Eleint-Marpenoth 1495":
        raise FoodSecuritySourceError("Longsaddle first-harvest window has drifted")
    if forward.longsaddle_first_harvest_outcome != "unresolved":
        raise FoodSecuritySourceError("Longsaddle first-harvest outcome is no longer unresolved")
    laden_harvest = laden.get("first_harvest_window")
    if laden_harvest != "Eleint-Marpenoth 1495 DR if successful":
        raise FoodSecuritySourceError("Operation Laden harvest window has drifted")

    source_refs = laden.get("source_refs")
    if (
        not isinstance(source_refs, list)
        or not source_refs
        or any(not isinstance(item, str) or not item for item in source_refs)
    ):
        raise FoodSecuritySourceError("Operation Laden source references are invalid")

    expected = {
        "population": 11000,
        "target": (Decimal("1200"), Decimal("1500")),
        "budget": (Decimal("65000"), Decimal("95000")),
    }
    if population != expected["population"]:
        raise FoodSecuritySourceError("Longsaddle population no longer equals 11,000")
    if canon_target != expected["target"]:
        raise FoodSecuritySourceError("Longsaddle target no longer equals 1,200-1,500 tons")
    if canon_budget != expected["budget"]:
        raise FoodSecuritySourceError("Longsaddle budget no longer equals 65,000-95,000 gp")

    return LongsaddleSourceFacts(
        scenario_id="operation-laden-table",
        timeline_id="source:operation-laden-table-late-kythorn-1495",
        campaign_date=forward.campaign_date,
        population_mouths=population,
        grain_target_low_tons=canon_target[0],
        grain_target_high_tons=canon_target[1],
        grain_procured_tons=forward.grain_procured_tons,
        grain_budget_low_gp=canon_budget[0],
        grain_budget_high_gp=canon_budget[1],
        harvest_window=forward.longsaddle_first_harvest_window,
        harvest_outcome=forward.longsaddle_first_harvest_outcome,
        actual_execution_eligible=False,
        source_refs=tuple(source_refs),
    )


_DECIMAL_ASSUMPTION_FIELDS = (
    "selected_target_tons",
    "supplier_stock_tons",
    "opening_longsaddle_stock_tons",
    "demand_tons",
    "dispatch_requested_tons",
    "route_capacity_tons_per_trip",
    "loss_rate",
    "storage_capacity_tons",
    "price_gp_per_ton",
    "funding_gp",
)
_INTEGER_ASSUMPTION_FIELDS = ("route_trips", "travel_periods")
_ALL_ASSUMPTION_FIELDS = _DECIMAL_ASSUMPTION_FIELDS + _INTEGER_ASSUMPTION_FIELDS


@dataclass(frozen=True, slots=True)
class LongsaddleAssumptions:
    """Explicit scenario inputs; ``None`` is unknown, not an implicit zero."""

    assumption_source: str = "user-supplied planning assumptions"
    selected_target_tons: Decimal | None = None
    supplier_stock_tons: Decimal | None = None
    opening_longsaddle_stock_tons: Decimal | None = None
    demand_tons: Decimal | None = None
    dispatch_requested_tons: Decimal | None = None
    route_capacity_tons_per_trip: Decimal | None = None
    route_trips: int | None = None
    travel_periods: int | None = None
    loss_rate: Decimal | None = None
    storage_capacity_tons: Decimal | None = None
    price_gp_per_ton: Decimal | None = None
    funding_gp: Decimal | None = None

    def __post_init__(self) -> None:
        _clean_text(self.assumption_source, "assumption source")
        for field_name in _DECIMAL_ASSUMPTION_FIELDS:
            _optional_nonnegative_decimal(getattr(self, field_name), field_name)
        _optional_nonnegative_int(self.route_trips, "route_trips")
        travel = _optional_nonnegative_int(self.travel_periods, "travel_periods")
        if travel is not None and travel < 1:
            raise FoodSecurityError("travel_periods must be at least 1")
        if self.loss_rate is not None and self.loss_rate >= ONE:
            raise FoodSecurityError("loss_rate must be in [0, 1)")

    @property
    def missing_fields(self) -> tuple[str, ...]:
        return tuple(
            field_name
            for field_name in _ALL_ASSUMPTION_FIELDS
            if getattr(self, field_name) is None
        )

    @property
    def target_tons(self) -> Decimal | None:
        return self.selected_target_tons

    @property
    def dispatch_tons(self) -> Decimal | None:
        return self.dispatch_requested_tons

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"assumption_source": self.assumption_source}
        for field_name in _DECIMAL_ASSUMPTION_FIELDS:
            payload[field_name] = _decimal_text(getattr(self, field_name))
        for field_name in _INTEGER_ASSUMPTION_FIELDS:
            payload[field_name] = getattr(self, field_name)
        return payload

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "LongsaddleAssumptions":
        """Parse exact decimal text from a JSON-style request mapping."""

        if not isinstance(payload, Mapping):
            raise FoodSecurityError("assumption payload must be a mapping")
        allowed = {"assumption_source", *_ALL_ASSUMPTION_FIELDS}
        unexpected = set(payload) - allowed
        if unexpected:
            raise FoodSecurityError(
                f"unknown Longsaddle assumption fields: {sorted(unexpected)}"
            )
        values: dict[str, object] = {
            "assumption_source": payload.get(
                "assumption_source", "user-supplied planning assumptions"
            )
        }
        for field_name in _DECIMAL_ASSUMPTION_FIELDS:
            raw = payload.get(field_name)
            if raw is None:
                values[field_name] = None
            else:
                try:
                    values[field_name] = exact_decimal(raw, label=field_name)
                except ValueError as exc:
                    raise FoodSecurityError(str(exc)) from exc
        for field_name in _INTEGER_ASSUMPTION_FIELDS:
            values[field_name] = payload.get(field_name)
        return cls(**values)


@dataclass(frozen=True, slots=True)
class LongsaddleFoodSecurityResult:
    """One source-aware, side-effect-free grain-security preview."""

    source_facts: LongsaddleSourceFacts
    assumptions: LongsaddleAssumptions
    profile_id: str | None
    canonical: bool
    objective_status: ObjectiveStatus
    requested_tons: Decimal | None
    route_capacity_tons: Decimal | None
    dispatched_tons: Decimal | None
    dispatch_gap_tons: Decimal | None
    target_gap_tons: Decimal | None
    supplier_gap_tons: Decimal | None
    capacity_gap_tons: Decimal | None
    lost_tons: Decimal | None
    delivered_tons: Decimal | None
    delivered_target_gap_tons: Decimal | None
    storage_gap_tons: Decimal | None
    consumed_tons: Decimal | None
    unmet_demand_tons: Decimal | None
    closing_tons: Decimal | None
    estimated_cost_gp: Decimal | None
    cost_gap_gp: Decimal | None
    funding_gap_gp: Decimal | None
    coverage_periods: Decimal | None
    arrival_period: int | None
    stockout_period: int | None
    conservation_residual_tons: Decimal | None
    provenance: Mapping[str, FieldProvenance]

    def __post_init__(self) -> None:
        if not isinstance(self.source_facts, LongsaddleSourceFacts):
            raise FoodSecurityError("result source facts are invalid")
        if not isinstance(self.assumptions, LongsaddleAssumptions):
            raise FoodSecurityError("result assumptions are invalid")
        if not isinstance(self.objective_status, ObjectiveStatus):
            raise FoodSecurityError("result objective status is invalid")
        if self.canonical is not False:
            raise FoodSecurityError("Longsaddle planner results cannot be canonical")
        if self.profile_id is not None:
            _clean_text(self.profile_id, "profile ID")
        object.__setattr__(self, "provenance", MappingProxyType(dict(self.provenance)))

    @property
    def route_loss_tons(self) -> Decimal | None:
        return self.lost_tons

    @property
    def closing_longsaddle_tons(self) -> Decimal | None:
        return self.closing_tons

    @property
    def shipment_shortfall_tons(self) -> Decimal | None:
        return self.dispatch_gap_tons

    def _flat_values(self) -> dict[str, object]:
        facts = self.source_facts
        values: dict[str, object] = {
            "scenario_id": facts.scenario_id,
            "timeline_id": facts.timeline_id,
            "campaign_date": facts.campaign_date,
            "population_mouths": facts.population_mouths,
            "source_target_low_tons": facts.grain_target_low_tons,
            "source_target_high_tons": facts.grain_target_high_tons,
            "grain_procured_tons": facts.grain_procured_tons,
            "source_budget_low_gp": facts.grain_budget_low_gp,
            "source_budget_high_gp": facts.grain_budget_high_gp,
            "harvest_window": facts.harvest_window,
            "harvest_outcome": facts.harvest_outcome,
            "harvest_result_tons": None,
        }
        values.update(
            {
                field_name: getattr(self.assumptions, field_name)
                for field_name in _ALL_ASSUMPTION_FIELDS
            }
        )
        values.update(
            {
                "objective_status": self.objective_status,
                "requested_tons": self.requested_tons,
                "route_capacity_tons": self.route_capacity_tons,
                "dispatched_tons": self.dispatched_tons,
                "dispatch_gap_tons": self.dispatch_gap_tons,
                "target_gap_tons": self.target_gap_tons,
                "supplier_gap_tons": self.supplier_gap_tons,
                "capacity_gap_tons": self.capacity_gap_tons,
                "lost_tons": self.lost_tons,
                "delivered_tons": self.delivered_tons,
                "delivered_target_gap_tons": self.delivered_target_gap_tons,
                "storage_gap_tons": self.storage_gap_tons,
                "consumed_tons": self.consumed_tons,
                "unmet_demand_tons": self.unmet_demand_tons,
                "closing_tons": self.closing_tons,
                "estimated_cost_gp": self.estimated_cost_gp,
                "cost_gap_gp": self.cost_gap_gp,
                "funding_gap_gp": self.funding_gap_gp,
                "coverage_periods": self.coverage_periods,
                "arrival_period": self.arrival_period,
                "stockout_period": self.stockout_period,
                "conservation_residual_tons": self.conservation_residual_tons,
            }
        )
        return values

    @property
    def decision_brief(self) -> Mapping[str, Mapping[str, object]]:
        """Return exact Source/Assumption/Derived/Unknown classifications."""

        sections: dict[str, dict[str, object]] = {
            kind.value: {} for kind in ProvenanceKind
        }
        values = self._flat_values()
        for field_name, receipt in self.provenance.items():
            value = _json_value(values.get(field_name))
            if receipt.kind is ProvenanceKind.UNKNOWN:
                sections[receipt.kind.value][field_name] = {
                    "value": value,
                    "reason": receipt.basis,
                    "dependencies": list(receipt.dependencies),
                }
            else:
                sections[receipt.kind.value][field_name] = value
        return MappingProxyType(
            {
                section: MappingProxyType(dict(items))
                for section, items in sections.items()
            }
        )

    def to_dict(self) -> dict[str, object]:
        metrics = {
            "objective_status": self.objective_status.value,
            "requested_tons": _decimal_text(self.requested_tons),
            "route_capacity_tons": _decimal_text(self.route_capacity_tons),
            "dispatched_tons": _decimal_text(self.dispatched_tons),
            "dispatch_gap_tons": _decimal_text(self.dispatch_gap_tons),
            "target_gap_tons": _decimal_text(self.target_gap_tons),
            "supplier_gap_tons": _decimal_text(self.supplier_gap_tons),
            "capacity_gap_tons": _decimal_text(self.capacity_gap_tons),
            "lost_tons": _decimal_text(self.lost_tons),
            "delivered_tons": _decimal_text(self.delivered_tons),
            "delivered_target_gap_tons": _decimal_text(
                self.delivered_target_gap_tons
            ),
            "storage_gap_tons": _decimal_text(self.storage_gap_tons),
            "consumed_tons": _decimal_text(self.consumed_tons),
            "unmet_demand_tons": _decimal_text(self.unmet_demand_tons),
            "closing_tons": _decimal_text(self.closing_tons),
            "estimated_cost_gp": _decimal_text(self.estimated_cost_gp),
            "cost_gap_gp": _decimal_text(self.cost_gap_gp),
            "funding_gap_gp": _decimal_text(self.funding_gap_gp),
            "coverage_periods": _decimal_text(self.coverage_periods),
            "arrival_period": self.arrival_period,
            "stockout_period": self.stockout_period,
            "conservation_residual_tons": _decimal_text(
                self.conservation_residual_tons
            ),
        }
        body = {
            "schema": FOOD_SECURITY_SCHEMA,
            "planning_only": True,
            "campaign_time_advanced": False,
            "canonical": False,
            "profile_id": self.profile_id,
            "source_facts": self.source_facts.to_dict(),
            "assumptions": self.assumptions.to_dict(),
            **metrics,
            "provenance": {
                field_name: receipt.to_dict()
                for field_name, receipt in self.provenance.items()
            },
            "decision_brief": {
                section: dict(items)
                for section, items in self.decision_brief.items()
            },
        }
        body["content_hash"] = canonical_hash(body)
        return body


def _source_provenance() -> dict[str, FieldProvenance]:
    both = ("agriculture-canon-v1", "operation-laden-table")
    agriculture = ("agriculture-canon-v1",)
    laden = ("operation-laden-table",)
    return {
        "scenario_id": FieldProvenance(
            ProvenanceKind.SOURCE, "Operation Laden canonical-import identity.", laden
        ),
        "timeline_id": FieldProvenance(
            ProvenanceKind.SOURCE, "Operation Laden late-Kythorn source timeline.", laden
        ),
        "campaign_date": FieldProvenance(
            ProvenanceKind.SOURCE,
            "Cross-checked late-Kythorn 1495 forward-scenario date; not current actual.",
            both,
        ),
        "population_mouths": FieldProvenance(
            ProvenanceKind.SOURCE, "Cross-checked Longsaddle population.", both
        ),
        "source_target_low_tons": FieldProvenance(
            ProvenanceKind.SOURCE, "Cross-checked procurement target lower bound.", both
        ),
        "source_target_high_tons": FieldProvenance(
            ProvenanceKind.SOURCE, "Cross-checked procurement target upper bound.", both
        ),
        "grain_procured_tons": FieldProvenance(
            ProvenanceKind.SOURCE,
            "Forward scenario reports zero procured; this is not an opening-stock default.",
            agriculture,
        ),
        "source_budget_low_gp": FieldProvenance(
            ProvenanceKind.SOURCE, "Cross-checked grain-plus-transport budget lower bound.", both
        ),
        "source_budget_high_gp": FieldProvenance(
            ProvenanceKind.SOURCE, "Cross-checked grain-plus-transport budget upper bound.", both
        ),
        "harvest_window": FieldProvenance(
            ProvenanceKind.SOURCE, "First-harvest window stated by both fixtures.", both
        ),
        "harvest_outcome": FieldProvenance(
            ProvenanceKind.SOURCE, "Agriculture canon explicitly says unresolved.", agriculture
        ),
        "harvest_result_tons": FieldProvenance(
            ProvenanceKind.UNKNOWN,
            "The Eleint-Marpenoth harvest outcome is unresolved; no harvest tonnage was inferred.",
            agriculture,
            ("harvest_outcome",),
        ),
    }


def _missing_basis(
    assumptions: LongsaddleAssumptions, dependencies: tuple[str, ...]
) -> str:
    missing = [name for name in dependencies if getattr(assumptions, name) is None]
    if missing:
        return (
            "Requires explicit assumptions for "
            + ", ".join(missing)
            + "; missing values were not treated as zero."
        )
    return "The result is not applicable under the supplied explicit assumptions."


def plan_longsaddle_food_security(
    assumptions: LongsaddleAssumptions,
    *,
    project_root: Path | None = None,
    agriculture_canon_path: Path | None = None,
    laden_fixture_path: Path | None = None,
    profile_id: str | None = None,
) -> LongsaddleFoodSecurityResult:
    """Evaluate one explicit, non-canonical Longsaddle grain plan.

    ``failed`` means the supplied physical plan cannot satisfy its immediate
    demand (or moves none of a positive request).  ``met`` requires a complete
    assumption set, full target dispatch, satisfied demand, no closing-storage
    overflow, and no budget or funding gap.  Every other case is ``at_risk``,
    including an otherwise plausible plan with unresolved inputs.
    """

    if not isinstance(assumptions, LongsaddleAssumptions):
        raise FoodSecurityError("planner requires LongsaddleAssumptions")
    if profile_id is not None:
        _clean_text(profile_id, "profile ID")
    facts = load_longsaddle_source_facts(
        project_root=project_root,
        agriculture_canon_path=agriculture_canon_path,
        laden_fixture_path=laden_fixture_path,
    )
    selected_target = assumptions.selected_target_tons
    if selected_target is not None and not (
        facts.grain_target_low_tons
        <= selected_target
        <= facts.grain_target_high_tons
    ):
        raise FoodSecurityError(
            "selected_target_tons must remain within the sourced 1200-1500 ton band"
        )

    provenance = _source_provenance()
    for field_name in _ALL_ASSUMPTION_FIELDS:
        value = getattr(assumptions, field_name)
        if value is None:
            provenance[field_name] = FieldProvenance(
                ProvenanceKind.UNKNOWN,
                f"No explicit {field_name} assumption was supplied; zero was not assumed.",
                dependencies=(field_name,),
            )
        else:
            provenance[field_name] = FieldProvenance(
                ProvenanceKind.ASSUMPTION,
                f"Explicit planning input from {assumptions.assumption_source}.",
            )

    requested = assumptions.dispatch_requested_tons

    capacity_dependencies = ("route_capacity_tons_per_trip", "route_trips")
    if all(getattr(assumptions, name) is not None for name in capacity_dependencies):
        with localcontext(_context()):
            route_capacity = (
                assumptions.route_capacity_tons_per_trip
                * Decimal(assumptions.route_trips)
            )
    else:
        route_capacity = None

    if requested is not None and assumptions.supplier_stock_tons is not None:
        supplier_gap = max(ZERO, requested - assumptions.supplier_stock_tons)
    else:
        supplier_gap = None
    if requested is not None and route_capacity is not None:
        capacity_gap = max(ZERO, requested - route_capacity)
    else:
        capacity_gap = None

    dispatch_dependencies = (
        "dispatch_requested_tons",
        "supplier_stock_tons",
        "route_capacity_tons_per_trip",
        "route_trips",
    )
    if all(getattr(assumptions, name) is not None for name in dispatch_dependencies):
        dispatched = min(requested, assumptions.supplier_stock_tons, route_capacity)
        with localcontext(_context()):
            dispatch_gap = requested - dispatched
    else:
        dispatched = None
        dispatch_gap = None

    if selected_target is not None and dispatched is not None:
        target_gap = max(ZERO, selected_target - dispatched)
    else:
        target_gap = None

    # Reuse the stock-flow route contract when its complete set is known.  This
    # validates capacity, travel, and loss under the same rules as durable runs.
    if (
        route_capacity is not None
        and assumptions.travel_periods is not None
        and assumptions.loss_rate is not None
    ):
        Route(
            route_id="route:longsaddle-food-security-preview",
            origin_site_id="site:explicit-supplier",
            destination_site_id="site:longsaddle",
            commodity_id="commodity:grain",
            capacity_per_period=route_capacity,
            travel_periods=assumptions.travel_periods,
            loss_rate=assumptions.loss_rate,
        )

    if dispatched is not None and assumptions.loss_rate is not None:
        with localcontext(_context()):
            lost = dispatched * assumptions.loss_rate
            delivered = dispatched - lost
    else:
        lost = None
        delivered = None
    if selected_target is not None and delivered is not None:
        delivered_target_gap = max(ZERO, selected_target - delivered)
    else:
        delivered_target_gap = None

    destination_dependencies = (
        "opening_longsaddle_stock_tons",
        "demand_tons",
        "storage_capacity_tons",
    )
    if delivered is not None and all(
        getattr(assumptions, name) is not None for name in destination_dependencies
    ):
        key = StockKey("site:longsaddle", "commodity:grain", "ton")
        destination_plan = AgriculturePlan(
            scenario_id="longsaddle-food-security-preview",
            scenario_name="Longsaddle grain arrival and demand",
            assumption_source=assumptions.assumption_source,
            openings=(OpeningInventory(key, assumptions.opening_longsaddle_stock_tons),),
            periods=(
                PlanningPeriod(
                    1,
                    "arrival-period demand and closing storage",
                    (
                        PeriodFlowAssumption(
                            key=key,
                            production=ZERO,
                            inbound=delivered,
                            consumption=assumptions.demand_tons,
                            outbound=ZERO,
                            processing_use=ZERO,
                            capacity=assumptions.storage_capacity_tons,
                            absolute_loss=ZERO,
                        ),
                    ),
                ),
            ),
        )
        row = simulate_agriculture(destination_plan).rows[0]
        storage_gap = row.capacity_overflow
        consumed = row.fulfilled_demand
        unmet_demand = row.unmet_demand
        closing = row.closing_inventory
        destination_residual = row.conservation_residual
    else:
        storage_gap = None
        consumed = None
        unmet_demand = None
        closing = None
        destination_residual = None

    if dispatched is not None and assumptions.price_gp_per_ton is not None:
        with localcontext(_context()):
            estimated_cost = dispatched * assumptions.price_gp_per_ton
            cost_gap = max(ZERO, estimated_cost - facts.grain_budget_high_gp)
    else:
        estimated_cost = None
        cost_gap = None
    if estimated_cost is not None and assumptions.funding_gp is not None:
        with localcontext(_context()):
            funding_gap = max(ZERO, estimated_cost - assumptions.funding_gp)
    else:
        funding_gap = None

    if assumptions.travel_periods is None:
        arrival_period = None
    else:
        arrival_period = assumptions.travel_periods + 1

    coverage_dependencies = ("demand_tons",)
    if closing is not None and assumptions.demand_tons is not None:
        if assumptions.demand_tons == ZERO:
            coverage = None
        else:
            with localcontext(_context()):
                coverage = closing / assumptions.demand_tons
    else:
        coverage = None

    if (
        arrival_period is not None
        and coverage is not None
        and unmet_demand is not None
    ):
        if unmet_demand > ZERO:
            stockout_period = arrival_period
        else:
            with localcontext(_context()):
                full_periods = int(
                    coverage.to_integral_value(rounding=ROUND_FLOOR)
                )
            stockout_period = arrival_period + full_periods + 1
    else:
        stockout_period = None

    if (
        dispatched is not None
        and lost is not None
        and delivered is not None
        and destination_residual is not None
        and assumptions.opening_longsaddle_stock_tons is not None
        and storage_gap is not None
        and consumed is not None
        and closing is not None
    ):
        with localcontext(_context()):
            conservation_residual = (
                assumptions.opening_longsaddle_stock_tons
                + dispatched
                - lost
                - storage_gap
                - consumed
                - closing
            )
        if conservation_residual != ZERO or destination_residual != ZERO:
            raise FoodSecurityError("Longsaddle plan failed physical conservation")
    else:
        conservation_residual = None

    complete = not assumptions.missing_fields
    if (
        (unmet_demand is not None and unmet_demand > ZERO)
        or (
            requested is not None
            and requested > ZERO
            and dispatched is not None
            and dispatched == ZERO
        )
    ):
        objective = ObjectiveStatus.FAILED
    elif (
        complete
        and target_gap == ZERO
        and storage_gap == ZERO
        and unmet_demand == ZERO
        and cost_gap == ZERO
        and funding_gap == ZERO
    ):
        objective = ObjectiveStatus.MET
    else:
        objective = ObjectiveStatus.AT_RISK

    derived_specs: dict[str, tuple[object, str, tuple[str, ...]]] = {
        "objective_status": (
            objective,
            "Decision rule combines assumption completeness, target dispatch, immediate demand, storage, budget, and funding.",
            _ALL_ASSUMPTION_FIELDS,
        ),
        "requested_tons": (
            requested,
            "The explicit dispatch request is reported without substituting the selected target.",
            ("dispatch_requested_tons",),
        ),
        "route_capacity_tons": (
            route_capacity,
            "route_capacity_tons_per_trip * route_trips",
            capacity_dependencies,
        ),
        "dispatched_tons": (
            dispatched,
            "min(dispatch_requested_tons, supplier_stock_tons, route_capacity_tons)",
            dispatch_dependencies,
        ),
        "dispatch_gap_tons": (
            dispatch_gap,
            "dispatch_requested_tons - dispatched_tons",
            dispatch_dependencies,
        ),
        "target_gap_tons": (
            target_gap,
            "max(selected_target_tons - dispatched_tons, 0)",
            ("selected_target_tons", *dispatch_dependencies),
        ),
        "supplier_gap_tons": (
            supplier_gap,
            "max(dispatch_requested_tons - supplier_stock_tons, 0)",
            ("dispatch_requested_tons", "supplier_stock_tons"),
        ),
        "capacity_gap_tons": (
            capacity_gap,
            "max(dispatch_requested_tons - route_capacity_tons, 0)",
            ("dispatch_requested_tons", *capacity_dependencies),
        ),
        "lost_tons": (
            lost,
            "dispatched_tons * loss_rate",
            (*dispatch_dependencies, "loss_rate"),
        ),
        "delivered_tons": (
            delivered,
            "dispatched_tons - lost_tons",
            (*dispatch_dependencies, "loss_rate"),
        ),
        "delivered_target_gap_tons": (
            delivered_target_gap,
            "max(selected_target_tons - delivered_tons, 0)",
            ("selected_target_tons", *dispatch_dependencies, "loss_rate"),
        ),
        "storage_gap_tons": (
            storage_gap,
            "Closing-stock overflow after the arrival-period demand, using agriculture_simulation.",
            (*dispatch_dependencies, "loss_rate", *destination_dependencies),
        ),
        "consumed_tons": (
            consumed,
            "min(opening stock + delivered grain, demand), using agriculture_simulation.",
            (*dispatch_dependencies, "loss_rate", *destination_dependencies),
        ),
        "unmet_demand_tons": (
            unmet_demand,
            "demand_tons - consumed_tons",
            (*dispatch_dependencies, "loss_rate", *destination_dependencies),
        ),
        "closing_tons": (
            closing,
            "Opening + delivered - consumed - closing-storage overflow.",
            (*dispatch_dependencies, "loss_rate", *destination_dependencies),
        ),
        "estimated_cost_gp": (
            estimated_cost,
            "dispatched_tons * price_gp_per_ton",
            (*dispatch_dependencies, "price_gp_per_ton"),
        ),
        "cost_gap_gp": (
            cost_gap,
            "max(estimated_cost_gp - sourced 95,000 gp budget ceiling, 0)",
            (*dispatch_dependencies, "price_gp_per_ton"),
        ),
        "funding_gap_gp": (
            funding_gap,
            "max(estimated_cost_gp - funding_gp, 0)",
            (*dispatch_dependencies, "price_gp_per_ton", "funding_gp"),
        ),
        "coverage_periods": (
            coverage,
            (
                "closing_tons / demand_tons; zero demand makes coverage not applicable."
                if assumptions.demand_tons == ZERO
                else "closing_tons / demand_tons"
            ),
            (*dispatch_dependencies, "loss_rate", *destination_dependencies),
        ),
        "arrival_period": (
            arrival_period,
            "travel_periods + 1, with dispatch identified as period 1.",
            ("travel_periods",),
        ),
        "stockout_period": (
            stockout_period,
            "First post-arrival demand period that cannot be fully covered if no replenishment occurs.",
            (
                *dispatch_dependencies,
                "travel_periods",
                "loss_rate",
                *destination_dependencies,
            ),
        ),
        "conservation_residual_tons": (
            conservation_residual,
            "opening Longsaddle stock + dispatched - route loss - storage overflow - consumed - closing",
            (*dispatch_dependencies, "loss_rate", *destination_dependencies),
        ),
    }
    for field_name, (value, basis, dependencies) in derived_specs.items():
        if value is None:
            provenance[field_name] = FieldProvenance(
                ProvenanceKind.UNKNOWN,
                _missing_basis(assumptions, dependencies),
                dependencies=dependencies,
            )
        else:
            provenance[field_name] = FieldProvenance(
                ProvenanceKind.DERIVED,
                basis,
                dependencies=dependencies,
            )

    return LongsaddleFoodSecurityResult(
        source_facts=facts,
        assumptions=assumptions,
        profile_id=profile_id,
        canonical=False,
        objective_status=objective,
        requested_tons=requested,
        route_capacity_tons=route_capacity,
        dispatched_tons=dispatched,
        dispatch_gap_tons=dispatch_gap,
        target_gap_tons=target_gap,
        supplier_gap_tons=supplier_gap,
        capacity_gap_tons=capacity_gap,
        lost_tons=lost,
        delivered_tons=delivered,
        delivered_target_gap_tons=delivered_target_gap,
        storage_gap_tons=storage_gap,
        consumed_tons=consumed,
        unmet_demand_tons=unmet_demand,
        closing_tons=closing,
        estimated_cost_gp=estimated_cost,
        cost_gap_gp=cost_gap,
        funding_gap_gp=funding_gap,
        coverage_periods=coverage,
        arrival_period=arrival_period,
        stockout_period=stockout_period,
        conservation_residual_tons=conservation_residual,
        provenance=provenance,
    )


def illustrative_low_v1_assumptions() -> LongsaddleAssumptions:
    """Return the complete, explicitly non-canonical known-answer profile."""

    return LongsaddleAssumptions(
        assumption_source="illustrative-low-v1 non-canon scenario assumptions",
        selected_target_tons=Decimal("1200"),
        supplier_stock_tons=Decimal("1200"),
        opening_longsaddle_stock_tons=Decimal("0"),
        demand_tons=Decimal("300"),
        dispatch_requested_tons=Decimal("1200"),
        route_capacity_tons_per_trip=Decimal("900"),
        route_trips=1,
        travel_periods=1,
        loss_rate=Decimal("0.02"),
        storage_capacity_tons=Decimal("1200"),
        price_gp_per_ton=Decimal("54.1667"),
        funding_gp=Decimal("65000"),
    )


def illustrative_low_v1(
    *,
    project_root: Path | None = None,
    agriculture_canon_path: Path | None = None,
    laden_fixture_path: Path | None = None,
) -> LongsaddleFoodSecurityResult:
    """Run the reviewed 1,200/900/882/582 non-canon acceptance example."""

    return plan_longsaddle_food_security(
        illustrative_low_v1_assumptions(),
        project_root=project_root,
        agriculture_canon_path=agriculture_canon_path,
        laden_fixture_path=laden_fixture_path,
        profile_id="illustrative-low-v1",
    )


# Short public alias for callers that name the commodity-specific operation.
plan_longsaddle_grain = plan_longsaddle_food_security


__all__ = [
    "DEFAULT_LADEN_FIXTURE_PATH",
    "FOOD_SECURITY_SCHEMA",
    "FieldProvenance",
    "FoodSecurityError",
    "FoodSecuritySourceError",
    "LongsaddleAssumptions",
    "LongsaddleFoodSecurityResult",
    "LongsaddleSourceFacts",
    "ObjectiveStatus",
    "ProvenanceKind",
    "illustrative_low_v1",
    "illustrative_low_v1_assumptions",
    "load_longsaddle_source_facts",
    "plan_longsaddle_food_security",
    "plan_longsaddle_grain",
]
