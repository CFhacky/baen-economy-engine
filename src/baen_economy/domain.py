"""Authority-aware domain types shared by import, simulation, and reporting."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class TemporalState(StrEnum):
    CURRENT = "current"
    HISTORICAL = "historical"
    FORWARD_RESOLVED = "forward_resolved"
    PROJECTED = "projected"
    SUPERSEDED = "superseded"
    UNKNOWN = "unknown"


class Authority(StrEnum):
    CANON_IMPORT = "canon_import"
    USER_RULING = "user_ruling"
    CAMPAIGN_RESOLUTION = "campaign_resolution"
    ENGINE_DERIVED = "engine_derived"
    SCENARIO_ASSUMPTION = "scenario_assumption"


class SimulationMode(StrEnum):
    LEGACY = "legacy"
    STOCK_FLOW = "stock_flow"
    COST_CENTER = "cost_center"
    CONSOLIDATION_ONLY = "consolidation_only"
    EXTERNAL = "external"


class AccountingTreatment(StrEnum):
    OPERATING_UNIT = "operating_unit"
    CONSOLIDATION_ONLY = "consolidation_only"
    NON_OPERATING_ASSET = "non_operating_asset"
    COST_CENTER = "cost_center"
    PROJECT = "project"
    FINANCIAL_INSTRUMENT = "financial_instrument"
    SUPERSEDED = "superseded"
    UNKNOWN = "unknown"


def canonical_decimal(value: Decimal) -> str:
    """Serialize a finite Decimal without consulting ambient context settings."""

    if type(value) is not Decimal or not value.is_finite():
        raise ValueError("canonical numeric values must be finite Decimals")
    # Decimal.__str__ is exact; only the context's `capitals` switch can vary its
    # exponent marker. Normalize that marker while retaining scale/significance.
    return str(value).replace("e", "E")


def decimal_or_none(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise TypeError("boolean is not a numeric campaign value")
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("campaign numeric values must be finite")
    return result


@dataclass(frozen=True, slots=True)
class EntityRecord:
    entity_id: str
    name: str
    source_ref: str
    source_record_id: str | None = None
    timeline_id: str | None = None
    effective_ordinal: int | None = None
    temporal_state: TemporalState = TemporalState.UNKNOWN
    treatment: AccountingTreatment = AccountingTreatment.UNKNOWN
    parent_name: str | None = None
    status: str | None = None
    sector: str | None = None
    city: str | None = None
    monthly_revenue: Decimal | None = None
    monthly_cost: Decimal | None = None
    capital_invested: Decimal | None = None
    profit_margin: Decimal | None = None
    date_operational_text: str | None = None
    source_last_updated_text: str | None = None
    as_of_campaign_date: str | None = None
    classification_authority_ref: str | None = None
    classification_rationale: str | None = None

    @property
    def eligible_for_current_operating_totals(self) -> bool:
        return (
            self.temporal_state is TemporalState.CURRENT
            and self.treatment is AccountingTreatment.OPERATING_UNIT
            and isinstance(self.timeline_id, str)
            and bool(self.timeline_id.strip())
            and self.timeline_id == self.timeline_id.strip()
            and type(self.effective_ordinal) is int
            and self.effective_ordinal >= 0
            and isinstance(self.classification_authority_ref, str)
            and bool(self.classification_authority_ref.strip())
            and isinstance(self.classification_rationale, str)
            and bool(self.classification_rationale.strip())
        )

    @property
    def contributes_current_revenue(self) -> bool:
        return self.eligible_for_current_operating_totals

    @property
    def contributes_current_cost(self) -> bool:
        return (
            self.temporal_state is TemporalState.CURRENT
            and isinstance(self.timeline_id, str)
            and bool(self.timeline_id.strip())
            and self.timeline_id == self.timeline_id.strip()
            and type(self.effective_ordinal) is int
            and self.effective_ordinal >= 0
            and isinstance(self.classification_authority_ref, str)
            and bool(self.classification_authority_ref.strip())
            and isinstance(self.classification_rationale, str)
            and bool(self.classification_rationale.strip())
            and self.treatment in {
                AccountingTreatment.OPERATING_UNIT,
                AccountingTreatment.COST_CENTER,
            }
        )


@dataclass(frozen=True, slots=True)
class SimulationAssignment:
    entity_id: str
    timeline_id: str
    period_index: int
    mode: SimulationMode
    source_ref: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.entity_id, "simulation entity ID"),
            (self.timeline_id, "simulation timeline ID"),
            (self.source_ref, "simulation source reference"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{label} is required")
        if type(self.period_index) is not int or self.period_index < 0:
            raise ValueError("simulation period index must be a non-negative integer")
        if not isinstance(self.mode, SimulationMode):
            raise ValueError("simulation mode has the wrong type")


def validate_unique_assignments(assignments: list[SimulationAssignment]) -> None:
    seen: dict[tuple[str, str, int], SimulationMode] = {}
    for assignment in assignments:
        key = (assignment.entity_id, assignment.timeline_id, assignment.period_index)
        prior = seen.get(key)
        if prior is not None:
            raise ValueError(
                f"entity-period cannot use both {prior.value} and {assignment.mode.value}: {key}"
            )
        seen[key] = assignment.mode
