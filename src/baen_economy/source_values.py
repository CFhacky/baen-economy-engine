"""Exact, provenance-carrying values for source-bound economy inputs.

The economy engine must distinguish a missing value from a reported zero and
must never promote a design, projection, forward scenario, or unconfirmed
claim into current execution state.  These types make that boundary explicit.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Generic, TypeVar


class SourceValueError(ValueError):
    """Raised when a source value loses exactness or provenance."""


class AuthorityClass(StrEnum):
    """Authority classes used by the read-only agriculture canon fixture."""

    RATIFIED_CAMPAIGN_STATE = "ratified_campaign_state"
    OBSERVED_OPERATING_STATE = "observed_operating_state"
    TECHNICAL_DESIGN = "technical_design"
    PROJECTION = "projection"
    UNCONFIRMED = "unconfirmed"


class EvidenceLayer(StrEnum):
    """Temporal/use layer for a claim, separate from its source authority."""

    CURRENT_ACTUAL = "current_actual"
    HISTORICAL_OBSERVATION = "historical_observation"
    FORWARD_SCENARIO = "forward_scenario"
    FUTURE_REFERENCE = "future_reference"
    TECHNICAL_DESIGN = "technical_design"
    PROJECTION = "projection"
    UNCONFIRMED = "unconfirmed"


ACTUAL_AUTHORITIES = frozenset(
    {
        AuthorityClass.RATIFIED_CAMPAIGN_STATE,
        AuthorityClass.OBSERVED_OPERATING_STATE,
    }
)


def exact_decimal(value: object, *, label: str = "source decimal") -> Decimal:
    """Parse exact decimal text, rejecting floats, booleans, NaN, and infinity."""

    if not isinstance(value, str) or not value:
        raise SourceValueError(f"{label} must be exact decimal text")
    try:
        result = Decimal(value)
    except Exception as exc:  # Decimal raises several arithmetic subclasses.
        raise SourceValueError(f"{label} is not valid decimal text") from exc
    if not result.is_finite():
        raise SourceValueError(f"{label} must be finite")
    return result


def optional_exact_decimal(
    value: object, *, label: str = "source decimal"
) -> Decimal | None:
    """Preserve JSON null as missing; never turn it into numeric zero."""

    if value is None:
        return None
    return exact_decimal(value, label=label)


@dataclass(frozen=True, slots=True)
class DecimalRange:
    """An inclusive exact range, optionally carrying a source unit and basis."""

    low: Decimal
    high: Decimal
    unit: str | None = None
    basis: str | None = None

    def __post_init__(self) -> None:
        for value, label in ((self.low, "range low"), (self.high, "range high")):
            if type(value) is not Decimal or not value.is_finite():
                raise SourceValueError(f"{label} must be a finite Decimal")
        if self.low > self.high:
            raise SourceValueError("range low cannot exceed range high")
        for value, label in ((self.unit, "range unit"), (self.basis, "range basis")):
            if value is not None and (
                not isinstance(value, str)
                or not value.strip()
                or value != value.strip()
            ):
                raise SourceValueError(f"{label} must be clean non-empty text")

    @property
    def is_point(self) -> bool:
        return self.low == self.high


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    """A precise pointer to a claim and its authority/temporal treatment."""

    source_id: str
    source_path: str
    authority_class: AuthorityClass
    layer: EvidenceLayer

    def __post_init__(self) -> None:
        for value, label in (
            (self.source_id, "evidence source ID"),
            (self.source_path, "evidence source path"),
        ):
            if (
                not isinstance(value, str)
                or not value.strip()
                or value != value.strip()
            ):
                raise SourceValueError(f"{label} must be clean non-empty text")
        if not isinstance(self.authority_class, AuthorityClass):
            raise SourceValueError("evidence authority class is invalid")
        if not isinstance(self.layer, EvidenceLayer):
            raise SourceValueError("evidence layer is invalid")

    @property
    def eligible_for_current_actual(self) -> bool:
        return (
            self.layer is EvidenceLayer.CURRENT_ACTUAL
            and self.authority_class in ACTUAL_AUTHORITIES
        )


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class SourcedValue(Generic[T]):
    """A value with evidence and an explicit current-execution gate.

    ``None`` means missing/unknown.  It is not interchangeable with a real
    numeric zero.  ``actual_execution_input`` can only be true when every
    evidence reference is current-actual and from an eligible authority.
    """

    value: T | None
    evidence: tuple[EvidenceReference, ...]
    actual_execution_input: bool = False

    def __post_init__(self) -> None:
        if not self.evidence:
            raise SourceValueError("a sourced value requires evidence")
        if any(not isinstance(item, EvidenceReference) for item in self.evidence):
            raise SourceValueError("sourced value evidence has the wrong type")
        if type(self.actual_execution_input) is not bool:
            raise SourceValueError("execution eligibility must be a boolean")
        if self.actual_execution_input:
            if self.value is None:
                raise SourceValueError("a missing value cannot become an execution input")
            if not all(item.eligible_for_current_actual for item in self.evidence):
                raise SourceValueError(
                    "non-current, design, projected, or unconfirmed evidence "
                    "cannot become an actual execution input"
                )

    @property
    def is_missing(self) -> bool:
        return self.value is None

    def require_actual(self) -> T:
        """Return an eligible current input or fail closed."""

        if not self.actual_execution_input or self.value is None:
            raise SourceValueError("source value is not eligible for actual execution")
        return self.value
