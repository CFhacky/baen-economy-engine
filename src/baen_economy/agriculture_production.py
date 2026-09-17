"""Source-faithful physical planning calculators for agriculture.

These calculators turn explicit physical inputs into exact ``DecimalRange``
previews.  They do not mutate campaign state, resolve a month, post a ledger
entry, or promote technical design values into current-actual facts.

Important boundaries:

* ``None`` is missing and raises :class:`MissingPlanningInput`; it is never
  converted to numeric zero.
* Binary floats are rejected.  Callers must supply :class:`~decimal.Decimal`
  values or :class:`~baen_economy.source_values.DecimalRange` values.
* Annual aquaculture output divided by twelve is an average planning rate,
  not a claim about harvest cadence.
* The Wyrmhelm carcass profiles preserve the independently sourced daily and
  annual approximations.  The engine does not force them to reconcile by
  silently changing either value.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from enum import StrEnum

from .source_values import DecimalRange


ZERO = Decimal("0")
ONE = Decimal("1")
TWELVE = Decimal("12")
THOUSAND = Decimal("1000")


def _decimal_context() -> Context:
    return Context(
        prec=40,
        rounding=ROUND_HALF_EVEN,
        Emin=-999999,
        Emax=999999,
        capitals=1,
        clamp=0,
    )


class AgriculturePlanningError(ValueError):
    """Base error for invalid physical planning inputs."""


class MissingPlanningInput(AgriculturePlanningError):
    """Raised when a calculator would otherwise replace unknown with zero."""


def _clean_text(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
    ):
        raise AgriculturePlanningError(f"{label} must be clean non-empty text")
    return value


def _nonnegative_range(
    value: Decimal | DecimalRange | None,
    *,
    label: str,
    unit: str | None = None,
    basis: str | None = None,
) -> DecimalRange:
    if value is None:
        raise MissingPlanningInput(f"{label} is required; missing is not zero")
    if type(value) is Decimal:
        if not value.is_finite():
            raise AgriculturePlanningError(f"{label} must be finite")
        result = DecimalRange(value, value, unit=unit, basis=basis)
    elif isinstance(value, DecimalRange):
        result = value
    else:
        raise AgriculturePlanningError(
            f"{label} must be a Decimal or DecimalRange; floats are not accepted"
        )
    if result.low < ZERO:
        raise AgriculturePlanningError(f"{label} cannot be negative")
    return result


def _ratio_range(
    value: DecimalRange | None,
    *,
    label: str,
    at_most_one: bool,
) -> DecimalRange:
    result = _nonnegative_range(value, label=label)
    if at_most_one and result.high > ONE:
        raise AgriculturePlanningError(f"{label} cannot exceed 1")
    return result


def _multiply_ranges(
    left: DecimalRange,
    right: DecimalRange,
    *,
    unit: str | None,
    basis: str | None,
) -> DecimalRange:
    # All public callers validate non-negative inputs, so endpoint
    # multiplication is monotonic and does not need a four-product search.
    with localcontext(_decimal_context()):
        return DecimalRange(
            left.low * right.low,
            left.high * right.high,
            unit=unit,
            basis=basis,
        )


@dataclass(frozen=True, slots=True)
class AquacultureYieldPreview:
    capacity: DecimalRange
    capacity_basis: str
    intensity_lb_per_1000_unit_year: DecimalRange
    annual_yield_lb: DecimalRange
    monthly_average_yield_lb: DecimalRange
    planning_only: bool = True

    @property
    def actual_execution_eligible(self) -> bool:
        return False


def aquaculture_annual_yield(
    capacity: Decimal | DecimalRange | None,
    intensity_lb_per_1000_unit_year: DecimalRange | None,
    *,
    capacity_basis: str,
) -> DecimalRange:
    """Calculate technical annual output from capacity and source intensity.

    ``capacity_basis`` must match the intensity's ``basis`` when the latter is
    populated (for example, ``"cubic_meters"`` or ``"square_meters"``).
    """

    clean_basis = _clean_text(capacity_basis, label="capacity basis")
    capacity_range = _nonnegative_range(
        capacity,
        label="aquaculture capacity",
        unit=clean_basis,
    )
    intensity = _nonnegative_range(
        intensity_lb_per_1000_unit_year,
        label="annual yield intensity",
    )
    if intensity.basis is not None and intensity.basis != clean_basis:
        raise AgriculturePlanningError(
            "capacity basis does not match annual yield intensity basis"
        )
    if capacity_range.unit is not None and capacity_range.unit != clean_basis:
        raise AgriculturePlanningError(
            "capacity range unit does not match capacity basis"
        )

    with localcontext(_decimal_context()):
        capacity_thousands = DecimalRange(
            capacity_range.low / THOUSAND,
            capacity_range.high / THOUSAND,
        )
    return _multiply_ranges(
        capacity_thousands,
        intensity,
        unit="lb",
        basis="annual_technical_preview",
    )


def aquaculture_monthly_yield(
    annual_yield_lb: Decimal | DecimalRange | None,
) -> DecimalRange:
    """Return annual output divided by twelve as a monthly average.

    This is deliberately not a harvest calendar or cohort schedule.
    """

    annual = _nonnegative_range(annual_yield_lb, label="annual aquaculture yield")
    with localcontext(_decimal_context()):
        return DecimalRange(
            annual.low / TWELVE,
            annual.high / TWELVE,
            unit="lb",
            basis="monthly_average_from_annual_preview",
        )


def aquaculture_yield_preview(
    capacity: Decimal | DecimalRange | None,
    intensity_lb_per_1000_unit_year: DecimalRange | None,
    *,
    capacity_basis: str,
) -> AquacultureYieldPreview:
    """Build an annual and monthly-average technical yield preview."""

    clean_basis = _clean_text(capacity_basis, label="capacity basis")
    capacity_range = _nonnegative_range(
        capacity,
        label="aquaculture capacity",
        unit=clean_basis,
    )
    intensity = _nonnegative_range(
        intensity_lb_per_1000_unit_year,
        label="annual yield intensity",
    )
    annual = aquaculture_annual_yield(
        capacity_range,
        intensity,
        capacity_basis=clean_basis,
    )
    return AquacultureYieldPreview(
        capacity=capacity_range,
        capacity_basis=clean_basis,
        intensity_lb_per_1000_unit_year=intensity,
        annual_yield_lb=annual,
        monthly_average_yield_lb=aquaculture_monthly_yield(annual),
    )


def aquaculture_feed_requirement(
    liveweight_output_lb: Decimal | DecimalRange | None,
    feed_conversion_ratio: DecimalRange | None,
) -> DecimalRange:
    """Calculate feed mass from liveweight output and an explicit FCR.

    A sourced zero FCR remains a real zero (appropriate for a specification
    that explicitly records no formulated feed).  A missing FCR raises instead
    of receiving that treatment.
    """

    output = _nonnegative_range(
        liveweight_output_lb,
        label="liveweight output",
    )
    fcr = _nonnegative_range(
        feed_conversion_ratio,
        label="feed conversion ratio",
    )
    return _multiply_ranges(
        output,
        fcr,
        unit="lb",
        basis="feed_required_for_liveweight_output",
    )


def crop_enhanced_yield(
    baseline_yield: Decimal | DecimalRange | None,
    yield_increase: DecimalRange | None,
) -> DecimalRange:
    """Apply a source uplift range to an explicit baseline crop yield."""

    baseline = _nonnegative_range(baseline_yield, label="baseline crop yield")
    increase = _ratio_range(
        yield_increase,
        label="crop yield increase",
        at_most_one=False,
    )
    multiplier = DecimalRange(ONE + increase.low, ONE + increase.high)
    return _multiply_ranges(
        baseline,
        multiplier,
        unit=baseline.unit,
        basis="technical_aqua_enhanced_yield",
    )


def crop_fertilizer_requirement(
    baseline_fertilizer: Decimal | DecimalRange | None,
    fertilizer_reduction: DecimalRange | None,
) -> DecimalRange:
    """Calculate remaining fertilizer after a source reduction range."""

    baseline = _nonnegative_range(
        baseline_fertilizer,
        label="baseline fertilizer requirement",
    )
    reduction = _ratio_range(
        fertilizer_reduction,
        label="fertilizer reduction",
        at_most_one=True,
    )
    # Greater reduction means less remaining fertilizer; reverse endpoints.
    remaining_multiplier = DecimalRange(
        ONE - reduction.high,
        ONE - reduction.low,
    )
    return _multiply_ranges(
        baseline,
        remaining_multiplier,
        unit=baseline.unit,
        basis="technical_fertilizer_after_reduction",
    )


@dataclass(frozen=True, slots=True)
class CropEnhancementPreview:
    baseline_yield: DecimalRange
    yield_increase: DecimalRange
    enhanced_yield: DecimalRange
    baseline_fertilizer: DecimalRange
    fertilizer_reduction: DecimalRange
    fertilizer_required: DecimalRange
    planning_only: bool = True

    @property
    def actual_execution_eligible(self) -> bool:
        return False


def crop_enhancement_preview(
    *,
    baseline_yield: Decimal | DecimalRange | None,
    yield_increase: DecimalRange | None,
    baseline_fertilizer: Decimal | DecimalRange | None,
    fertilizer_reduction: DecimalRange | None,
) -> CropEnhancementPreview:
    """Build crop output and fertilizer previews from explicit baselines."""

    baseline_output = _nonnegative_range(
        baseline_yield,
        label="baseline crop yield",
    )
    output_increase = _ratio_range(
        yield_increase,
        label="crop yield increase",
        at_most_one=False,
    )
    baseline_input = _nonnegative_range(
        baseline_fertilizer,
        label="baseline fertilizer requirement",
    )
    input_reduction = _ratio_range(
        fertilizer_reduction,
        label="fertilizer reduction",
        at_most_one=True,
    )
    return CropEnhancementPreview(
        baseline_yield=baseline_output,
        yield_increase=output_increase,
        enhanced_yield=crop_enhanced_yield(baseline_output, output_increase),
        baseline_fertilizer=baseline_input,
        fertilizer_reduction=input_reduction,
        fertilizer_required=crop_fertilizer_requirement(
            baseline_input,
            input_reduction,
        ),
    )


class DragonOccupancyMode(StrEnum):
    ONE_WARMOTHER = "one_warmother"
    FULL_RATED_OCCUPANCY = "full_rated_occupancy"


WYRMHELM_FOOD_SOURCE_REF = (
    "notion:34ce8214-84b0-812f-8577-d4d37289da9f#food-system-certification"
)


@dataclass(frozen=True, slots=True)
class DragonCarcassProfile:
    mode: DragonOccupancyMode
    approximate_daily_usable_carcass_lb: DecimalRange
    approximate_annual_usable_carcass_tons: DecimalRange
    minimum_routine_reserve_tons: DecimalRange
    preferred_high_tempo_reserve_tons: DecimalRange | None
    source_ref: str = WYRMHELM_FOOD_SOURCE_REF
    temporal_note: str = "future/reference planning profile; not Day 7 Hammer actual"

    @property
    def actual_execution_eligible(self) -> bool:
        return False


DRAGON_CARCASS_PROFILES = {
    DragonOccupancyMode.ONE_WARMOTHER: DragonCarcassProfile(
        mode=DragonOccupancyMode.ONE_WARMOTHER,
        approximate_daily_usable_carcass_lb=DecimalRange(
            Decimal("577"), Decimal("577"), unit="lb", basis="per_day"
        ),
        approximate_annual_usable_carcass_tons=DecimalRange(
            Decimal("105"), Decimal("105"), unit="tons", basis="per_year"
        ),
        minimum_routine_reserve_tons=DecimalRange(
            Decimal("13"), Decimal("13"), unit="tons", basis="45_day_minimum"
        ),
        preferred_high_tempo_reserve_tons=None,
    ),
    DragonOccupancyMode.FULL_RATED_OCCUPANCY: DragonCarcassProfile(
        mode=DragonOccupancyMode.FULL_RATED_OCCUPANCY,
        approximate_daily_usable_carcass_lb=DecimalRange(
            Decimal("928"), Decimal("928"), unit="lb", basis="per_day"
        ),
        approximate_annual_usable_carcass_tons=DecimalRange(
            Decimal("169"), Decimal("169"), unit="tons", basis="per_year"
        ),
        minimum_routine_reserve_tons=DecimalRange(
            Decimal("21"), Decimal("21"), unit="tons", basis="routine_minimum"
        ),
        preferred_high_tempo_reserve_tons=DecimalRange(
            Decimal("42"), Decimal("42"), unit="tons", basis="high_tempo_preferred"
        ),
    ),
}


@dataclass(frozen=True, slots=True)
class DragonCarcassDemandPreview:
    profile: DragonCarcassProfile
    horizon_days: Decimal
    horizon_usable_carcass_lb: DecimalRange
    planning_only: bool = True

    @property
    def actual_execution_eligible(self) -> bool:
        return False


def dragon_carcass_demand(
    mode: DragonOccupancyMode | str,
    *,
    horizon_days: Decimal | None,
) -> DragonCarcassDemandPreview:
    """Scale the sourced approximate daily demand over explicit days.

    The separately sourced annual tonnage stays on ``profile`` as its own
    approximation.  It is not derived from, or overwritten by, this horizon.
    """

    if horizon_days is None:
        raise MissingPlanningInput("dragon demand horizon days is required")
    if type(horizon_days) is not Decimal or not horizon_days.is_finite():
        raise AgriculturePlanningError(
            "dragon demand horizon days must be a finite Decimal"
        )
    if horizon_days < ZERO:
        raise AgriculturePlanningError("dragon demand horizon days cannot be negative")
    try:
        canonical_mode = DragonOccupancyMode(mode)
    except (TypeError, ValueError) as exc:
        raise AgriculturePlanningError("unknown dragon occupancy mode") from exc
    profile = DRAGON_CARCASS_PROFILES[canonical_mode]
    horizon_range = DecimalRange(horizon_days, horizon_days)
    demand = _multiply_ranges(
        profile.approximate_daily_usable_carcass_lb,
        horizon_range,
        unit="lb",
        basis="planning_horizon_from_approximate_daily_source",
    )
    return DragonCarcassDemandPreview(
        profile=profile,
        horizon_days=horizon_days,
        horizon_usable_carcass_lb=demand,
    )


@dataclass(frozen=True, slots=True)
class ProcurementCoveragePreview:
    target_quantity: DecimalRange
    procured_quantity: DecimalRange
    coverage_fraction: DecimalRange
    remaining_shortfall: DecimalRange
    possibly_meets_target: bool
    definitely_meets_target: bool
    planning_only: bool = True

    @property
    def actual_execution_eligible(self) -> bool:
        return False


def procurement_coverage(
    procured_quantity: Decimal | DecimalRange | None,
    target_quantity: Decimal | DecimalRange | None,
) -> ProcurementCoveragePreview:
    """Compare procured quantity with an explicit non-zero target range."""

    procured = _nonnegative_range(
        procured_quantity,
        label="procured quantity",
    )
    target = _nonnegative_range(target_quantity, label="procurement target")
    if target.low <= ZERO:
        raise AgriculturePlanningError(
            "procurement target low must be greater than zero"
        )
    if (
        procured.unit is not None
        and target.unit is not None
        and procured.unit != target.unit
    ):
        raise AgriculturePlanningError("procured and target units do not match")

    with localcontext(_decimal_context()):
        coverage = DecimalRange(
            procured.low / target.high,
            procured.high / target.low,
            unit="fraction",
            basis="procured_divided_by_target_range",
        )
        shortfall = DecimalRange(
            max(target.low - procured.high, ZERO),
            max(target.high - procured.low, ZERO),
            unit=target.unit or procured.unit,
            basis="remaining_procurement_shortfall",
        )
    return ProcurementCoveragePreview(
        target_quantity=target,
        procured_quantity=procured,
        coverage_fraction=coverage,
        remaining_shortfall=shortfall,
        possibly_meets_target=procured.high >= target.low,
        definitely_meets_target=procured.low >= target.high,
    )
