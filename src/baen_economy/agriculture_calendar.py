"""Fail-closed calendar and temporal-layer gates for agriculture sources.

The agriculture engine has one current-actual campaign date.  Dated evidence
is compared with that immutable anchor, while technical designs and explicitly
undated/later references retain their own layers.  Planning previews require
an explicit, reference-specific selection token and can never mutate or
advance the current-actual state.

This module models the twelve named months of the Calendar of Harptos.  It
does not assign invented exact days to source phrases such as ``late
Kythorn``: those phrases remain inclusive date bands.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AgricultureCalendarError(ValueError):
    """Base error for invalid or unsafe agriculture calendar operations."""


class AmbiguousCampaignDateError(AgricultureCalendarError):
    """Raised when a partial date overlaps the current-actual day."""


class TemporalGateError(AgricultureCalendarError):
    """Raised when evidence is requested through an unsafe temporal gate."""


class RealmsMonth(StrEnum):
    """The twelve named months of the Forgotten Realms calendar."""

    HAMMER = "Hammer"
    ALTURIAK = "Alturiak"
    CHES = "Ches"
    TARSAKH = "Tarsakh"
    MIRTUL = "Mirtul"
    KYTHORN = "Kythorn"
    FLAMERULE = "Flamerule"
    ELEASIS = "Eleasis"
    ELEINT = "Eleint"
    MARPENOTH = "Marpenoth"
    UKTAR = "Uktar"
    NIGHTAL = "Nightal"


REALMS_MONTHS: tuple[RealmsMonth, ...] = (
    RealmsMonth.HAMMER,
    RealmsMonth.ALTURIAK,
    RealmsMonth.CHES,
    RealmsMonth.TARSAKH,
    RealmsMonth.MIRTUL,
    RealmsMonth.KYTHORN,
    RealmsMonth.FLAMERULE,
    RealmsMonth.ELEASIS,
    RealmsMonth.ELEINT,
    RealmsMonth.MARPENOTH,
    RealmsMonth.UKTAR,
    RealmsMonth.NIGHTAL,
)

_MONTH_INDEX = {month: index for index, month in enumerate(REALMS_MONTHS, 1)}


class MonthPart(StrEnum):
    """A source-preserving third of a thirty-day Realms month."""

    EARLY = "early"
    MID = "mid"
    LATE = "late"


_MONTH_PART_DAY_BOUNDS: dict[MonthPart, tuple[int, int]] = {
    MonthPart.EARLY: (1, 10),
    MonthPart.MID: (11, 20),
    MonthPart.LATE: (21, 30),
}


class DateRelation(StrEnum):
    """Interval-aware relation between two campaign date markers."""

    BEFORE = "before"
    EXACT = "exact"
    AFTER = "after"
    OVERLAPS = "overlaps"


@dataclass(frozen=True, slots=True)
class CampaignDate:
    """An exact day or an explicitly partial Realms campaign date.

    ``day`` and ``part`` are mutually exclusive.  Supplying neither preserves
    a whole-month source date instead of silently choosing a day.
    """

    year_dr: int
    month: RealmsMonth
    day: int | None = None
    part: MonthPart | None = None

    def __post_init__(self) -> None:
        if type(self.year_dr) is not int or self.year_dr <= 0:
            raise AgricultureCalendarError("campaign year must be a positive integer")
        if not isinstance(self.month, RealmsMonth):
            raise AgricultureCalendarError("campaign month must be a RealmsMonth")
        if self.day is not None:
            if type(self.day) is not int or not 1 <= self.day <= 30:
                raise AgricultureCalendarError(
                    "a named Realms month day must be an integer from 1 through 30"
                )
            if self.part is not None:
                raise AgricultureCalendarError(
                    "an exact campaign day cannot also have a partial-month label"
                )
        elif self.part is not None and not isinstance(self.part, MonthPart):
            raise AgricultureCalendarError("campaign month part is invalid")

    @classmethod
    def on_day(
        cls, year_dr: int, month: RealmsMonth, day: int
    ) -> CampaignDate:
        """Construct an exact campaign day."""

        return cls(year_dr=year_dr, month=month, day=day)

    @classmethod
    def in_part(
        cls, year_dr: int, month: RealmsMonth, part: MonthPart
    ) -> CampaignDate:
        """Construct an early/mid/late partial-month marker."""

        return cls(year_dr=year_dr, month=month, part=part)

    @classmethod
    def in_month(cls, year_dr: int, month: RealmsMonth) -> CampaignDate:
        """Construct a whole-month marker without inventing an exact day."""

        return cls(year_dr=year_dr, month=month)

    @property
    def is_exact_day(self) -> bool:
        return self.day is not None

    @property
    def day_bounds(self) -> tuple[int, int]:
        if self.day is not None:
            return (self.day, self.day)
        if self.part is not None:
            return _MONTH_PART_DAY_BOUNDS[self.part]
        return (1, 30)

    @property
    def earliest_key(self) -> tuple[int, int, int]:
        return (self.year_dr, _MONTH_INDEX[self.month], self.day_bounds[0])

    @property
    def latest_key(self) -> tuple[int, int, int]:
        return (self.year_dr, _MONTH_INDEX[self.month], self.day_bounds[1])

    @property
    def label(self) -> str:
        if self.day is not None:
            return f"Day {self.day} {self.month.value} {self.year_dr} DR"
        if self.part is not None:
            return f"{self.part.value} {self.month.value} {self.year_dr} DR"
        return f"{self.month.value} {self.year_dr} DR"


def compare_campaign_dates(left: CampaignDate, right: CampaignDate) -> DateRelation:
    """Compare exact or partial dates without collapsing ranges to fake days."""

    if not isinstance(left, CampaignDate) or not isinstance(right, CampaignDate):
        raise AgricultureCalendarError("campaign date comparison requires two dates")
    if left.latest_key < right.earliest_key:
        return DateRelation.BEFORE
    if left.earliest_key > right.latest_key:
        return DateRelation.AFTER
    if (
        left.is_exact_day
        and right.is_exact_day
        and left.earliest_key == right.earliest_key
    ):
        return DateRelation.EXACT
    return DateRelation.OVERLAPS


class ReferenceKind(StrEnum):
    """How a source supplies (or deliberately does not supply) its date."""

    DATED = "dated"
    UNDATED = "undated"
    DECLARED_LATER = "declared_later"
    TECHNICAL = "technical"


class TemporalClass(StrEnum):
    """The only temporal layers exposed to the agriculture engine."""

    CURRENT_ACTUAL = "current_actual"
    HISTORICAL = "historical"
    FORWARD = "forward"
    LATER = "later"
    UNDATED = "undated"
    TECHNICAL = "technical"

    @property
    def eligible_for_current_actual(self) -> bool:
        return self is TemporalClass.CURRENT_ACTUAL


@dataclass(frozen=True, slots=True)
class TemporalReference:
    """A source reference with an explicit treatment for its campaign date."""

    reference_id: str
    kind: ReferenceKind
    campaign_date: CampaignDate | None = None

    def __post_init__(self) -> None:
        _require_clean_text(self.reference_id, "temporal reference ID")
        if not isinstance(self.kind, ReferenceKind):
            raise AgricultureCalendarError("temporal reference kind is invalid")
        if self.campaign_date is not None and not isinstance(
            self.campaign_date, CampaignDate
        ):
            raise AgricultureCalendarError("temporal reference date is invalid")
        if self.kind is ReferenceKind.DATED and self.campaign_date is None:
            raise AgricultureCalendarError("a dated reference requires a campaign date")
        if self.kind is ReferenceKind.UNDATED and self.campaign_date is not None:
            raise AgricultureCalendarError(
                "an undated reference cannot also carry a campaign date"
            )


@dataclass(frozen=True, slots=True)
class PlanningPreviewSelection:
    """Explicit acknowledgement of one source and its non-actual layer."""

    reference_id: str
    selected_layer: TemporalClass
    actual_anchor: CampaignDate
    reason: str

    def __post_init__(self) -> None:
        _require_clean_text(self.reference_id, "preview reference ID")
        _require_clean_text(self.reason, "preview selection reason")
        if not isinstance(self.selected_layer, TemporalClass):
            raise AgricultureCalendarError("preview selected layer is invalid")
        if not isinstance(self.actual_anchor, CampaignDate):
            raise AgricultureCalendarError("preview actual anchor is invalid")
        if not self.actual_anchor.is_exact_day:
            raise AgricultureCalendarError("preview actual anchor must be an exact day")


@dataclass(frozen=True, slots=True)
class PlanningPreviewPermit:
    """Validated, non-mutating permission to calculate one isolated preview."""

    reference_id: str
    layer: TemporalClass
    actual_anchor: CampaignDate
    source_date: CampaignDate | None
    reason: str

    @property
    def may_advance_campaign_time(self) -> bool:
        return False

    @property
    def may_mutate_current_actual(self) -> bool:
        return False


_PLANNING_LAYERS = frozenset(
    {
        TemporalClass.FORWARD,
        TemporalClass.LATER,
        TemporalClass.UNDATED,
        TemporalClass.TECHNICAL,
    }
)


@dataclass(frozen=True, slots=True)
class AgricultureTemporalGate:
    """Classify evidence against one immutable current-actual date.

    Same-year dates after the anchor are ``forward``.  Later campaign years are
    ``later`` by default; ``forward_through_year`` can be raised only when a
    wider forward-scenario horizon is deliberately configured.
    """

    current_actual: CampaignDate
    forward_through_year: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.current_actual, CampaignDate):
            raise AgricultureCalendarError("current actual must be a campaign date")
        if not self.current_actual.is_exact_day:
            raise AgricultureCalendarError("current actual must be an exact campaign day")
        if self.forward_through_year is None:
            object.__setattr__(
                self, "forward_through_year", self.current_actual.year_dr
            )
        elif (
            type(self.forward_through_year) is not int
            or self.forward_through_year < self.current_actual.year_dr
        ):
            raise AgricultureCalendarError(
                "forward scenario horizon cannot precede the current campaign year"
            )

    def classify(self, reference: TemporalReference) -> TemporalClass:
        """Classify a reference without changing the current-actual anchor."""

        if not isinstance(reference, TemporalReference):
            raise AgricultureCalendarError("classification requires a temporal reference")
        if reference.kind is ReferenceKind.TECHNICAL:
            return TemporalClass.TECHNICAL
        if reference.kind is ReferenceKind.UNDATED:
            return TemporalClass.UNDATED
        if reference.kind is ReferenceKind.DECLARED_LATER:
            if reference.campaign_date is not None:
                relation = compare_campaign_dates(
                    reference.campaign_date, self.current_actual
                )
                if relation is not DateRelation.AFTER:
                    raise TemporalGateError(
                        "a declared-later reference has a date that is not after "
                        "the current actual"
                    )
            return TemporalClass.LATER

        # TemporalReference validation guarantees a date for DATED.
        assert reference.campaign_date is not None
        relation = compare_campaign_dates(reference.campaign_date, self.current_actual)
        if relation is DateRelation.EXACT:
            return TemporalClass.CURRENT_ACTUAL
        if relation is DateRelation.BEFORE:
            return TemporalClass.HISTORICAL
        if relation is DateRelation.AFTER:
            if reference.campaign_date.year_dr <= self.forward_through_year:
                return TemporalClass.FORWARD
            return TemporalClass.LATER
        raise AmbiguousCampaignDateError(
            f"{reference.reference_id!r} ({reference.campaign_date.label}) overlaps "
            f"the current-actual day ({self.current_actual.label}); supply an exact "
            "source date or an explicit non-dated treatment"
        )

    def require_current_actual(self, reference: TemporalReference) -> TemporalReference:
        """Return only evidence dated exactly to the current-actual day."""

        layer = self.classify(reference)
        if layer is not TemporalClass.CURRENT_ACTUAL:
            raise TemporalGateError(
                f"{reference.reference_id!r} is {layer.value}, not current_actual"
            )
        return reference

    def select_planning_preview(
        self, reference: TemporalReference, *, reason: str
    ) -> PlanningPreviewSelection:
        """Explicitly select one isolated non-actual reference for preview use."""

        layer = self.classify(reference)
        if layer not in _PLANNING_LAYERS:
            raise TemporalGateError(
                f"{layer.value} evidence cannot be selected as a planning preview"
            )
        return PlanningPreviewSelection(
            reference_id=reference.reference_id,
            selected_layer=layer,
            actual_anchor=self.current_actual,
            reason=reason,
        )

    def require_planning_preview(
        self,
        reference: TemporalReference,
        selection: PlanningPreviewSelection | None,
    ) -> PlanningPreviewPermit:
        """Validate an explicit selection and issue a non-mutating preview permit."""

        layer = self.classify(reference)
        if layer not in _PLANNING_LAYERS:
            raise TemporalGateError(
                f"{layer.value} evidence is not a planning-preview layer"
            )
        if selection is None:
            raise TemporalGateError(
                "planning preview requires an explicit reference selection"
            )
        if not isinstance(selection, PlanningPreviewSelection):
            raise TemporalGateError("planning preview selection has the wrong type")
        if selection.reference_id != reference.reference_id:
            raise TemporalGateError("planning preview selection targets another reference")
        if selection.selected_layer is not layer:
            raise TemporalGateError("planning preview selection layer no longer matches")
        if selection.actual_anchor != self.current_actual:
            raise TemporalGateError("planning preview selection uses another actual anchor")
        return PlanningPreviewPermit(
            reference_id=reference.reference_id,
            layer=layer,
            actual_anchor=self.current_actual,
            source_date=reference.campaign_date,
            reason=selection.reason,
        )


def _require_clean_text(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
    ):
        raise AgricultureCalendarError(f"{label} must be clean non-empty text")
    return value


__all__ = [
    "AgricultureCalendarError",
    "AgricultureTemporalGate",
    "AmbiguousCampaignDateError",
    "CampaignDate",
    "DateRelation",
    "MonthPart",
    "PlanningPreviewPermit",
    "PlanningPreviewSelection",
    "REALMS_MONTHS",
    "RealmsMonth",
    "ReferenceKind",
    "TemporalClass",
    "TemporalGateError",
    "TemporalReference",
    "compare_campaign_dates",
]
