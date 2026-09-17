"""Source-bound, non-canonical food-production planning surfaces.

The agriculture canon contains useful technical specifications, but it does
not contain current site allocations, opening inventories, acreage, biomass,
feed stocks, or demand.  This module keeps that boundary visible while making
the sourced species and crop catalogues usable in explicit what-if plans.

All scenario quantities arrive as exact decimal text.  The returned payloads
are JSON-safe, hash-addressed, and classified into Source, Assumption, Derived,
and Unknown sections.  There is deliberately no Notion, ledger, dice, or
campaign-clock write path in this module.
"""

from __future__ import annotations

from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
import hashlib
from pathlib import Path
import re
from typing import Mapping

from .agriculture_domain import AgricultureCanon, CropSpecification, SpeciesSpecification
from .agriculture_production import (
    AgriculturePlanningError,
    aquaculture_feed_requirement,
    aquaculture_yield_preview,
    crop_enhancement_preview,
)
from .agriculture_source import (
    DEFAULT_AGRICULTURE_CANON_PATH,
    AgricultureSourceError,
    load_agriculture_canon,
)
from .domain import canonical_decimal
from .operator_codec import canonical_hash
from .source_values import DecimalRange, SourceValueError, exact_decimal


FOOD_PRODUCTION_CATALOG_SCHEMA = "tnp.food-production.catalog/1"
AQUACULTURE_PLAN_SCHEMA = "tnp.food-production.aquaculture-plan/1"
CROP_PLAN_SCHEMA = "tnp.food-production.crop-plan/1"
DEFAULT_CANON_PATH = DEFAULT_AGRICULTURE_CANON_PATH

ZERO = Decimal("0")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

_AQUACULTURE_REQUIRED = {
    "scenario_id",
    "species_id",
    "capacity",
    "capacity_basis",
    "planned_liveweight_output_lb",
    "opening_feed_lb",
    "feed_receipts_lb",
}
_AQUACULTURE_OPTIONAL = {
    "assumed_annual_yield_lb_per_1000_unit",
    "assumed_feed_conversion_ratio",
}
_CROP_REQUIRED = {
    "scenario_id",
    "crop_id",
    "baseline_yield_tons",
    "baseline_fertilizer_tons",
    "opening_food_tons",
    "food_receipts_tons",
    "planned_consumption_tons",
}
_CROP_OPTIONAL = {"assumed_yield_increase"}


class FoodProductionError(ValueError):
    """Raised when a source-bound production request cannot be evaluated."""


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
        or len(value) > 240
        or _CONTROL_RE.search(value) is not None
    ):
        raise FoodProductionError(f"{label} must be clean non-empty text")
    return value


def _exact_nonnegative(value: object, label: str) -> Decimal:
    try:
        result = exact_decimal(value, label=label)
    except SourceValueError as exc:
        raise FoodProductionError(str(exc)) from exc
    if result < ZERO:
        raise FoodProductionError(f"{label} cannot be negative")
    return result


def _range_from_mapping(
    value: object,
    label: str,
    *,
    require_basis: bool = False,
) -> DecimalRange:
    if not isinstance(value, Mapping):
        raise FoodProductionError(f"{label} must be an exact low/high object")
    expected = {"low", "high", "basis"} if require_basis else {"low", "high"}
    if set(value) != expected:
        raise FoodProductionError(
            f"{label} keys must be exactly {sorted(expected)}"
        )
    low = _exact_nonnegative(value["low"], f"{label} low")
    high = _exact_nonnegative(value["high"], f"{label} high")
    basis = _clean_text(value["basis"], f"{label} basis") if require_basis else None
    try:
        return DecimalRange(low, high, basis=basis)
    except SourceValueError as exc:
        raise FoodProductionError(str(exc)) from exc


def _decimal_text(value: Decimal) -> str:
    try:
        return canonical_decimal(value)
    except ValueError as exc:
        raise FoodProductionError(str(exc)) from exc


def _range_payload(value: DecimalRange | None) -> dict[str, object] | None:
    if value is None:
        return None
    result: dict[str, object] = {
        "low": _decimal_text(value.low),
        "high": _decimal_text(value.high),
    }
    if value.unit is not None:
        result["unit"] = value.unit
    if value.basis is not None:
        result["basis"] = value.basis
    return result


def _safety_payload() -> dict[str, object]:
    return {
        "planning_only": True,
        "canonical": False,
        "read_only": True,
        "actual_execution_eligible": False,
        "notion_writes": 0,
        "canonical_ledger_postings": 0,
        "dice_rolled": 0,
        "campaign_time_advanced": False,
    }


def _load_context(fixture_path: Path) -> tuple[AgricultureCanon, str, str]:
    if not isinstance(fixture_path, Path):
        raise FoodProductionError("agriculture canon path must be a concrete Path")
    try:
        fixture_bytes = fixture_path.read_bytes()
        canon = load_agriculture_canon(fixture_path)
    except (OSError, AgricultureSourceError, SourceValueError) as exc:
        raise FoodProductionError(f"cannot load agriculture canon: {exc}") from exc
    if (
        canon.notion_access != "read_only"
        or canon.safety.get("notion_writes") != 0
        or canon.safety.get("canonical_ledger_postings") != 0
        or canon.safety.get("dice_rolled") != 0
        or canon.safety.get("campaign_time_advanced") is not False
    ):
        raise FoodProductionError("agriculture canon is not a read-only source")
    return canon, hashlib.sha256(fixture_bytes).hexdigest(), fixture_path.name


def _source_binding(
    canon: AgricultureCanon,
    fixture_sha256: str,
    fixture_name: str,
) -> dict[str, object]:
    return {
        "fixture_name": fixture_name,
        "fixture_schema": canon.schema,
        "fixture_sha256": fixture_sha256,
        "canon_content_hash": canon.content_hash,
        "retrieved_on": canon.retrieved_on,
        "notion_access": canon.notion_access,
    }


def _evidence_payload(canon: AgricultureCanon, source_id: str, source_path: str) -> dict[str, object]:
    try:
        source = canon.sources_by_id[source_id]
    except KeyError as exc:  # Defensive: the strict source loader already checks this.
        raise FoodProductionError(f"unknown source evidence: {source_id}") from exc
    return {
        "source_id": source.source_id,
        "source_path": source_path,
        "title": source.title,
        "url": source.url,
        "authority_class": source.authority_class.value,
    }


def _species_payload(canon: AgricultureCanon, item: SpeciesSpecification) -> dict[str, object]:
    return {
        "species_id": item.species_id,
        "name": item.name,
        "scientific_name": item.scientific_name,
        "zone": item.zone,
        "role": item.role,
        "growth_months": _range_payload(item.growth_months),
        "stocking_density": _range_payload(item.stocking_density),
        "feed_conversion_ratio": _range_payload(item.feed_conversion_ratio),
        "market_gp_per_lb": _range_payload(item.market_gp_per_lb),
        "annual_yield_lb_per_1000_unit": _range_payload(
            item.annual_yield_lb_per_1000_unit
        ),
        "evidence": _evidence_payload(
            canon,
            item.evidence.source_id,
            item.evidence.source_path,
        ),
        "evidence_layer": item.evidence.layer.value,
        "actual_execution_eligible": False,
    }


def _crop_payload(canon: AgricultureCanon, item: CropSpecification) -> dict[str, object]:
    return {
        "crop_id": item.crop_id,
        "name": item.name,
        "crop_class": item.crop_class,
        "yield_increase": _range_payload(item.yield_increase),
        "confirmed_planted": item.confirmed_planted,
        "program_evidence": [
            _evidence_payload(canon, evidence.source_id, evidence.source_path)
            | {"evidence_layer": evidence.layer.value}
            for evidence in canon.crop_program.evidence
        ],
        "actual_execution_eligible": False,
    }


def _with_content_hash(body: dict[str, object]) -> dict[str, object]:
    result = dict(body)
    result["content_hash"] = canonical_hash(body)
    return result


def food_production_catalog(
    fixture_path: Path = DEFAULT_CANON_PATH,
) -> dict[str, object]:
    """Return every named species and crop without inventing physical state."""

    canon, fixture_sha256, fixture_name = _load_context(fixture_path)
    body: dict[str, object] = {
        "schema": FOOD_PRODUCTION_CATALOG_SCHEMA,
        "source_binding": _source_binding(canon, fixture_sha256, fixture_name),
        "current_actual_boundary": {
            "campaign_date": canon.current_actual_state.campaign_date,
            "live_freeze": canon.current_actual_state.live_freeze,
            "advance_authorized": canon.current_actual_state.advance_authorized,
            "agriculture_month_close_authorized": (
                canon.current_actual_state.agriculture_month_close_authorized
            ),
            "physical_execution_ready": canon.physical_execution_ready,
        },
        "species": [_species_payload(canon, item) for item in canon.species],
        "crops": [_crop_payload(canon, item) for item in canon.crop_program.crops],
        "crop_program_parameters": {
            "overall_aqua_enhanced_yield_increase": _range_payload(
                canon.crop_program.overall_aqua_enhanced_yield_increase
            ),
            "fertilizer_reduction": _range_payload(
                canon.crop_program.fertilizer_reduction
            ),
            "water_distribution": {
                "capacity_gallons_per_minute": _range_payload(
                    canon.crop_program.water_distribution.capacity_gallons_per_minute
                ),
                "field_range_miles": _range_payload(
                    canon.crop_program.water_distribution.field_range_miles
                ),
            },
        },
        "unknown_current_physical_inputs": list(canon.unresolved_inputs),
        "warning": (
            "Catalogue values are source technical specifications or observed labels; "
            "they are not current site allocations or an executable production month."
        ),
        "safety": _safety_payload(),
    }
    return _with_content_hash(body)


def _validate_request_keys(
    payload: Mapping[str, object],
    required: set[str],
    optional: set[str],
    label: str,
) -> None:
    if not isinstance(payload, Mapping):
        raise FoodProductionError(f"{label} request must be a mapping")
    missing = sorted(required - set(payload))
    extra = sorted(set(payload) - required - optional)
    if missing or extra:
        raise FoodProductionError(
            f"{label} request fields differ; missing={missing}, extra={extra}"
        )


def _species_by_id(canon: AgricultureCanon, species_id: str) -> SpeciesSpecification:
    by_id = {item.species_id: item for item in canon.species}
    try:
        return by_id[species_id]
    except KeyError as exc:
        raise FoodProductionError(f"unknown species_id: {species_id}") from exc


def _crop_by_id(canon: AgricultureCanon, crop_id: str) -> CropSpecification:
    by_id = {item.crop_id: item for item in canon.crop_program.crops}
    try:
        return by_id[crop_id]
    except KeyError as exc:
        raise FoodProductionError(f"unknown crop_id: {crop_id}") from exc


def _effective_species_parameter(
    *,
    source_value: DecimalRange | None,
    supplied_value: object,
    label: str,
    require_basis: bool,
) -> tuple[DecimalRange, str]:
    if source_value is not None:
        if supplied_value is not None:
            raise FoodProductionError(
                f"{label} is source-defined and cannot be overridden in this planner"
            )
        return source_value, "Source"
    if supplied_value is None:
        raise FoodProductionError(
            f"{label} is absent from source; supply an explicit scenario assumption"
        )
    return (
        _range_from_mapping(
            supplied_value,
            f"assumed {label}",
            require_basis=require_basis,
        ),
        "Assumption",
    )


def _feed_balance(required: DecimalRange, available: Decimal) -> dict[str, object]:
    with localcontext(_context()):
        consumed_at_low = min(required.low, available)
        consumed_at_high = min(required.high, available)
        closing_at_low = available - consumed_at_low
        closing_at_high = available - consumed_at_high
        shortfall_at_low = required.low - consumed_at_low
        shortfall_at_high = required.high - consumed_at_high
        residual_at_low = available - consumed_at_low - closing_at_low
        residual_at_high = available - consumed_at_high - closing_at_high
    if residual_at_low != ZERO or residual_at_high != ZERO:
        raise FoodProductionError("internal feed conservation failure")
    if available >= required.high:
        status = "sufficient_for_full_range"
    elif available >= required.low:
        status = "sufficient_for_lower_bound_only"
    else:
        status = "shortfall_across_range"
    return {
        "status": status,
        "feed_available_lb": _decimal_text(available),
        "feed_consumed_lb": _range_payload(
            DecimalRange(consumed_at_low, consumed_at_high, unit="lb")
        ),
        "closing_feed_lb": _range_payload(
            DecimalRange(closing_at_high, closing_at_low, unit="lb")
        ),
        "feed_shortfall_lb": _range_payload(
            DecimalRange(shortfall_at_low, shortfall_at_high, unit="lb")
        ),
        "conservation_residual_lb": {
            "low": _decimal_text(residual_at_low),
            "high": _decimal_text(residual_at_high),
        },
    }


def preview_aquaculture_plan(
    payload: Mapping[str, object],
    *,
    fixture_path: Path = DEFAULT_CANON_PATH,
) -> dict[str, object]:
    """Evaluate one explicit aquaculture yield-and-feed what-if plan."""

    _validate_request_keys(
        payload,
        _AQUACULTURE_REQUIRED,
        _AQUACULTURE_OPTIONAL,
        "aquaculture",
    )
    canon, fixture_sha256, fixture_name = _load_context(fixture_path)
    scenario_id = _clean_text(payload["scenario_id"], "scenario_id")
    species_id = _clean_text(payload["species_id"], "species_id")
    capacity_basis = _clean_text(payload["capacity_basis"], "capacity_basis")
    capacity = _exact_nonnegative(payload["capacity"], "capacity")
    planned_output = _exact_nonnegative(
        payload["planned_liveweight_output_lb"],
        "planned_liveweight_output_lb",
    )
    opening_feed = _exact_nonnegative(payload["opening_feed_lb"], "opening_feed_lb")
    feed_receipts = _exact_nonnegative(payload["feed_receipts_lb"], "feed_receipts_lb")
    species = _species_by_id(canon, species_id)

    annual_intensity, intensity_origin = _effective_species_parameter(
        source_value=species.annual_yield_lb_per_1000_unit,
        supplied_value=payload.get("assumed_annual_yield_lb_per_1000_unit"),
        label="annual_yield_lb_per_1000_unit",
        require_basis=True,
    )
    fcr, fcr_origin = _effective_species_parameter(
        source_value=species.feed_conversion_ratio,
        supplied_value=payload.get("assumed_feed_conversion_ratio"),
        label="feed_conversion_ratio",
        require_basis=False,
    )
    try:
        yield_preview = aquaculture_yield_preview(
            capacity,
            annual_intensity,
            capacity_basis=capacity_basis,
        )
        feed_required = aquaculture_feed_requirement(planned_output, fcr)
    except AgriculturePlanningError as exc:
        raise FoodProductionError(str(exc)) from exc

    with localcontext(_context()):
        feed_available = opening_feed + feed_receipts
    feed_balance = _feed_balance(feed_required, feed_available)
    monthly = yield_preview.monthly_average_yield_lb
    if planned_output < monthly.low:
        output_position = "below_source_monthly_average_range"
    elif planned_output > monthly.high:
        output_position = "above_source_monthly_average_range"
    else:
        output_position = "within_source_monthly_average_range"

    normalized_request: dict[str, object] = {
        "scenario_id": scenario_id,
        "species_id": species_id,
        "capacity": _decimal_text(capacity),
        "capacity_basis": capacity_basis,
        "planned_liveweight_output_lb": _decimal_text(planned_output),
        "opening_feed_lb": _decimal_text(opening_feed),
        "feed_receipts_lb": _decimal_text(feed_receipts),
        "assumed_annual_yield_lb_per_1000_unit": (
            _range_payload(annual_intensity) if intensity_origin == "Assumption" else None
        ),
        "assumed_feed_conversion_ratio": (
            _range_payload(fcr) if fcr_origin == "Assumption" else None
        ),
    }
    derived: dict[str, object] = {
        "annual_yield_lb": _range_payload(yield_preview.annual_yield_lb),
        "monthly_average_yield_lb": _range_payload(
            yield_preview.monthly_average_yield_lb
        ),
        "planned_output_position": output_position,
        "feed_required_lb": _range_payload(feed_required),
        **feed_balance,
    }
    source_values = {
        "species_identity": {
            "species_id": species.species_id,
            "name": species.name,
            "scientific_name": species.scientific_name,
            "zone": species.zone,
            "role": species.role,
        },
        "growth_months": _range_payload(species.growth_months),
        "stocking_density": _range_payload(species.stocking_density),
        "source_annual_yield_lb_per_1000_unit": _range_payload(
            species.annual_yield_lb_per_1000_unit
        ),
        "source_feed_conversion_ratio": _range_payload(
            species.feed_conversion_ratio
        ),
        "evidence": _evidence_payload(
            canon,
            species.evidence.source_id,
            species.evidence.source_path,
        ),
    }
    assumption_values = {
        key: value
        for key, value in normalized_request.items()
        if value is not None
    }
    unknown = {
        "current_site_allocation": {
            "value": None,
            "reason": "No source assigns this species or capacity to a current site.",
        },
        "current_opening_feed_stock": {
            "value": None,
            "reason": "The supplied opening feed is a scenario assumption, not a current fact.",
        },
        "current_biomass_mortality_and_harvest_schedule": {
            "value": None,
            "reason": "The agriculture canon explicitly leaves cohorts, biomass, mortality, and harvest schedule unresolved.",
        },
        "current_feed_formula_supply_price_and_storage": {
            "value": None,
            "reason": "The agriculture canon explicitly leaves these feed facts unresolved.",
        },
        "actual_month_result": {
            "value": None,
            "reason": "The current state is frozen and agriculture month close is not authorized.",
        },
    }
    body: dict[str, object] = {
        "schema": AQUACULTURE_PLAN_SCHEMA,
        "scenario_id": scenario_id,
        "canonical": False,
        "planning_only": True,
        "source_binding": _source_binding(canon, fixture_sha256, fixture_name),
        "selection": _species_payload(canon, species),
        "assumptions": normalized_request,
        "effective_technical_parameters": {
            "annual_yield_lb_per_1000_unit": {
                "value": _range_payload(annual_intensity),
                "origin": intensity_origin,
            },
            "feed_conversion_ratio": {
                "value": _range_payload(fcr),
                "origin": fcr_origin,
            },
        },
        "derived": derived,
        "decision_brief": {
            "Source": source_values,
            "Assumption": assumption_values,
            "Derived": derived,
            "Unknown": unknown,
        },
        "hashes": {
            "source_fixture_sha256": fixture_sha256,
            "source_canon_content_hash": canon.content_hash,
            "input_sha256": canonical_hash(normalized_request),
        },
        "safety": _safety_payload(),
    }
    return _with_content_hash(body)


def _effective_crop_uplift(
    crop: CropSpecification,
    supplied_value: object,
) -> tuple[DecimalRange, str]:
    if crop.yield_increase is not None:
        if supplied_value is not None:
            raise FoodProductionError(
                "yield_increase is source-defined for this crop and cannot be overridden"
            )
        return crop.yield_increase, "Source"
    if supplied_value is None:
        raise FoodProductionError(
            "yield_increase is absent from source for this crop; supply an explicit "
            "assumed_yield_increase scenario range"
        )
    return _range_from_mapping(
        supplied_value,
        "assumed_yield_increase",
    ), "Assumption"


def _food_balance(
    *,
    opening: Decimal,
    receipts: Decimal,
    production: DecimalRange,
    planned_consumption: Decimal,
) -> dict[str, object]:
    with localcontext(_context()):
        gross_at_low = opening + receipts + production.low
        gross_at_high = opening + receipts + production.high
        fulfilled_at_low = min(planned_consumption, gross_at_low)
        fulfilled_at_high = min(planned_consumption, gross_at_high)
        closing_at_low = gross_at_low - fulfilled_at_low
        closing_at_high = gross_at_high - fulfilled_at_high
        shortfall_at_low_output = planned_consumption - fulfilled_at_low
        shortfall_at_high_output = planned_consumption - fulfilled_at_high
        residual_at_low = gross_at_low - fulfilled_at_low - closing_at_low
        residual_at_high = gross_at_high - fulfilled_at_high - closing_at_high
    if residual_at_low != ZERO or residual_at_high != ZERO:
        raise FoodProductionError("internal food conservation failure")
    if shortfall_at_low_output == ZERO:
        status = "sufficient_across_range"
    elif shortfall_at_high_output == ZERO:
        status = "sufficient_at_upper_output_only"
    else:
        status = "shortfall_across_range"
    return {
        "food_status": status,
        "gross_food_available_tons": _range_payload(
            DecimalRange(gross_at_low, gross_at_high, unit="tons")
        ),
        "fulfilled_consumption_tons": _range_payload(
            DecimalRange(fulfilled_at_low, fulfilled_at_high, unit="tons")
        ),
        "closing_food_tons": _range_payload(
            DecimalRange(closing_at_low, closing_at_high, unit="tons")
        ),
        "food_shortfall_tons": _range_payload(
            DecimalRange(
                shortfall_at_high_output,
                shortfall_at_low_output,
                unit="tons",
            )
        ),
        "conservation_residual_tons": {
            "low": _decimal_text(residual_at_low),
            "high": _decimal_text(residual_at_high),
        },
    }


def preview_crop_plan(
    payload: Mapping[str, object],
    *,
    fixture_path: Path = DEFAULT_CANON_PATH,
) -> dict[str, object]:
    """Evaluate one explicit crop-output and food-inventory what-if plan."""

    _validate_request_keys(payload, _CROP_REQUIRED, _CROP_OPTIONAL, "crop")
    canon, fixture_sha256, fixture_name = _load_context(fixture_path)
    scenario_id = _clean_text(payload["scenario_id"], "scenario_id")
    crop_id = _clean_text(payload["crop_id"], "crop_id")
    baseline_yield = _exact_nonnegative(
        payload["baseline_yield_tons"], "baseline_yield_tons"
    )
    baseline_fertilizer = _exact_nonnegative(
        payload["baseline_fertilizer_tons"], "baseline_fertilizer_tons"
    )
    opening_food = _exact_nonnegative(
        payload["opening_food_tons"], "opening_food_tons"
    )
    food_receipts = _exact_nonnegative(
        payload["food_receipts_tons"], "food_receipts_tons"
    )
    planned_consumption = _exact_nonnegative(
        payload["planned_consumption_tons"], "planned_consumption_tons"
    )
    crop = _crop_by_id(canon, crop_id)
    uplift, uplift_origin = _effective_crop_uplift(
        crop,
        payload.get("assumed_yield_increase"),
    )
    try:
        enhancement = crop_enhancement_preview(
            baseline_yield=DecimalRange(
                baseline_yield,
                baseline_yield,
                unit="tons",
                basis="explicit_scenario_baseline",
            ),
            yield_increase=uplift,
            baseline_fertilizer=DecimalRange(
                baseline_fertilizer,
                baseline_fertilizer,
                unit="tons",
                basis="explicit_scenario_baseline",
            ),
            fertilizer_reduction=canon.crop_program.fertilizer_reduction,
        )
    except AgriculturePlanningError as exc:
        raise FoodProductionError(str(exc)) from exc
    food_balance = _food_balance(
        opening=opening_food,
        receipts=food_receipts,
        production=enhancement.enhanced_yield,
        planned_consumption=planned_consumption,
    )

    normalized_request: dict[str, object] = {
        "scenario_id": scenario_id,
        "crop_id": crop_id,
        "baseline_yield_tons": _decimal_text(baseline_yield),
        "baseline_fertilizer_tons": _decimal_text(baseline_fertilizer),
        "opening_food_tons": _decimal_text(opening_food),
        "food_receipts_tons": _decimal_text(food_receipts),
        "planned_consumption_tons": _decimal_text(planned_consumption),
        "assumed_yield_increase": (
            _range_payload(uplift) if uplift_origin == "Assumption" else None
        ),
    }
    derived: dict[str, object] = {
        "enhanced_yield_tons": _range_payload(enhancement.enhanced_yield),
        "fertilizer_required_tons": _range_payload(
            enhancement.fertilizer_required
        ),
        **food_balance,
    }
    source_values = {
        "crop_identity": {
            "crop_id": crop.crop_id,
            "name": crop.name,
            "crop_class": crop.crop_class,
            "confirmed_planted": crop.confirmed_planted,
        },
        "source_yield_increase": _range_payload(crop.yield_increase),
        "source_fertilizer_reduction": _range_payload(
            canon.crop_program.fertilizer_reduction
        ),
        "program_evidence": [
            _evidence_payload(canon, evidence.source_id, evidence.source_path)
            for evidence in canon.crop_program.evidence
        ],
    }
    assumption_values = {
        key: value
        for key, value in normalized_request.items()
        if value is not None
    }
    unknown = {
        "current_site_and_acreage_allocation": {
            "value": None,
            "reason": "No current acreage or site allocation was inferred for this crop.",
        },
        "current_baseline_physical_yield": {
            "value": None,
            "reason": "The supplied baseline yield is a scenario assumption, not a current fact.",
        },
        "current_opening_food_stock": {
            "value": None,
            "reason": "The supplied opening food is a scenario assumption, not a current fact.",
        },
        "current_population_demand": {
            "value": None,
            "reason": "The supplied consumption is a scenario assumption; current demand by food class is unresolved.",
        },
        "actual_month_result": {
            "value": None,
            "reason": "The current state is frozen and agriculture month close is not authorized.",
        },
    }
    body: dict[str, object] = {
        "schema": CROP_PLAN_SCHEMA,
        "scenario_id": scenario_id,
        "canonical": False,
        "planning_only": True,
        "source_binding": _source_binding(canon, fixture_sha256, fixture_name),
        "selection": _crop_payload(canon, crop),
        "assumptions": normalized_request,
        "effective_technical_parameters": {
            "yield_increase": {
                "value": _range_payload(uplift),
                "origin": uplift_origin,
            },
            "fertilizer_reduction": {
                "value": _range_payload(canon.crop_program.fertilizer_reduction),
                "origin": "Source",
            },
        },
        "derived": derived,
        "decision_brief": {
            "Source": source_values,
            "Assumption": assumption_values,
            "Derived": derived,
            "Unknown": unknown,
        },
        "hashes": {
            "source_fixture_sha256": fixture_sha256,
            "source_canon_content_hash": canon.content_hash,
            "input_sha256": canonical_hash(normalized_request),
        },
        "safety": _safety_payload(),
    }
    return _with_content_hash(body)
