"""Typed, authority-aware domain model for the Baen agriculture canon."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping

from .source_values import (
    AuthorityClass,
    DecimalRange,
    EvidenceReference,
    SourcedValue,
)


@dataclass(frozen=True, slots=True)
class SourceDocument:
    source_id: str
    title: str
    url: str
    page_id: str
    authority_class: AuthorityClass


@dataclass(frozen=True, slots=True)
class RegistryEntity:
    entity_id: str
    name: str
    sector: str
    status: str
    as_of: str
    employees: int | None
    monthly_revenue_gp: Decimal | None
    monthly_cost_gp: Decimal | None
    capital_invested_gp: Decimal | None
    evidence: EvidenceReference

    @property
    def monthly_net_gp(self) -> Decimal | None:
        if self.monthly_revenue_gp is None or self.monthly_cost_gp is None:
            return None
        return self.monthly_revenue_gp - self.monthly_cost_gp

    @property
    def actual_execution_eligible(self) -> bool:
        # Registry entries are dated reference rows, not the live Day 7 state.
        return False


@dataclass(frozen=True, slots=True)
class CurrentActualState:
    campaign_date: str
    live_freeze: bool
    advance_authorized: bool
    agriculture_month_close_authorized: bool
    evidence: EvidenceReference


@dataclass(frozen=True, slots=True)
class ForwardAgricultureState:
    campaign_date: str
    temporal_class: str
    actual_execution_eligible: bool
    shelter_zones_total: int
    shelter_zones_destroyed: int
    shelter_zones_not_reported_destroyed: int
    surviving_zones_confirmed_operational: int | None
    destroyed_zone_ids: tuple[str, ...] | None
    longsaddle_population: int
    longsaddle_food_position: str
    longsaddle_first_full_planting: str
    longsaddle_k1495_harvestable_output: Decimal
    longsaddle_first_harvest_window: str
    longsaddle_first_harvest_outcome: str
    first_meaningful_export_surplus: str
    meat_self_sufficiency: str
    meat_export: str
    grain_procurement_target_tons: DecimalRange
    grain_procured_tons: Decimal
    meat_and_livestock_budget_gp: DecimalRange
    grain_budget_with_transport_gp: DecimalRange
    execution_rolls_resolved: int
    transactions_resolved: int
    evidence: tuple[EvidenceReference, ...]


@dataclass(frozen=True, slots=True)
class ShelterProduction:
    outputs: tuple[str, ...]
    third_greenhouse_yield_vs_expected: DecimalRange
    baseline_physical_yield: Decimal | None
    evidence: EvidenceReference
    additive_fields: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "additive_fields", MappingProxyType(dict(self.additive_fields))
        )

    @property
    def actual_execution_eligible(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class BlacklakeWorkforce:
    farm_manager: int
    fish_handlers: int
    processing_workers: int
    transport: int
    security: int

    @property
    def total(self) -> int:
        return (
            self.farm_manager
            + self.fish_handlers
            + self.processing_workers
            + self.transport
            + self.security
        )


@dataclass(frozen=True, slots=True)
class BlacklakeProduction:
    pool_count: int
    outputs: tuple[str, ...]
    workforce: BlacklakeWorkforce
    evidence: EvidenceReference

    @property
    def actual_execution_eligible(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class ConvertedQuarryProduction:
    site_count: int
    confirmed_species: tuple[str, ...]
    evidence_text: str
    evidence: EvidenceReference

    @property
    def actual_execution_eligible(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class BgPoolsProduction:
    site_count: int
    confirmed_outputs: tuple[str, ...]
    water_quality_complication: str
    evidence: EvidenceReference

    @property
    def actual_execution_eligible(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class ReservoirProduction:
    site_count: int | None
    confirmed_outputs: tuple[str, ...]
    operating_specialty: str
    evidence: tuple[EvidenceReference, ...]

    @property
    def actual_execution_eligible(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class OrchardProduction:
    temporal_class: str
    acreage: Decimal
    outputs: tuple[str, ...]
    processing: tuple[str, ...]
    annual_revenue_gp: Decimal
    evidence: tuple[EvidenceReference, ...]

    @property
    def actual_execution_eligible(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class ConfirmedProduction:
    shelters: ShelterProduction
    blacklake: BlacklakeProduction
    converted_quarry: ConvertedQuarryProduction
    bg_pools: BgPoolsProduction
    reservoir_fisheries: ReservoirProduction
    orchard_chapel_1498: OrchardProduction
    additive_sections: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "additive_sections", MappingProxyType(dict(self.additive_sections))
        )


@dataclass(frozen=True, slots=True)
class PondGroup:
    group_id: str
    temporal_class: str
    ponds: int
    temperature_f: DecimalRange
    species_labels: tuple[str, ...]
    annual_yield_lb: Decimal
    evidence: EvidenceReference

    @property
    def actual_execution_eligible(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class NMWCTopology:
    temporal_class: str
    day7_hammer1495_execution_eligible: bool
    ponds: int
    capacity_each_cubic_meters: Decimal
    total_capacity_cubic_meters: Decimal
    total_capacity_approx_gallons: Decimal
    continuous_harvest_design: bool
    total_annual_yield_lb: Decimal
    evidence: tuple[EvidenceReference, ...]

    @property
    def actual_execution_eligible(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class SpeciesSpecification:
    species_id: str
    name: str
    scientific_name: str
    zone: str
    role: str
    growth_months: DecimalRange
    stocking_density: DecimalRange
    feed_conversion_ratio: DecimalRange | None
    market_gp_per_lb: DecimalRange
    annual_yield_lb_per_1000_unit: DecimalRange | None
    evidence: EvidenceReference

    @property
    def actual_execution_eligible(self) -> bool:
        # These are technical specifications, not observed pond assignments.
        return False


@dataclass(frozen=True, slots=True)
class CropSpecification:
    crop_id: str
    name: str
    crop_class: str
    yield_increase: DecimalRange | None
    confirmed_planted: bool


@dataclass(frozen=True, slots=True)
class WaterDistribution:
    capacity_gallons_per_minute: DecimalRange
    field_range_miles: DecimalRange


@dataclass(frozen=True, slots=True)
class CropProgram:
    overall_aqua_enhanced_yield_increase: DecimalRange
    fertilizer_reduction: DecimalRange
    water_distribution: WaterDistribution
    crops: tuple[CropSpecification, ...]
    evidence: tuple[EvidenceReference, ...]

    @property
    def actual_execution_eligible(self) -> bool:
        # Crop uplift figures are design claims.  The observed tomato planting
        # remains evidence, but the mixed program is not an executable recipe.
        return False


@dataclass(frozen=True, slots=True)
class KnownConflict:
    conflict_id: str
    description: str
    blocking_for: tuple[str, ...]

    @property
    def actual_execution_eligible(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class AgricultureCanon:
    schema: str
    retrieved_on: str
    notion_access: str
    campaign_focus: str
    warning: str
    safety: Mapping[str, object]
    authority_order: tuple[AuthorityClass, ...]
    sources: tuple[SourceDocument, ...]
    registry_entities: tuple[RegistryEntity, ...]
    current_actual_state: CurrentActualState
    forward_k1495_state: ForwardAgricultureState
    confirmed_production: ConfirmedProduction
    nmwc_pond_groups: tuple[PondGroup, ...]
    nmwc_topology: NMWCTopology
    species: tuple[SpeciesSpecification, ...]
    crop_program: CropProgram
    known_conflicts: tuple[KnownConflict, ...]
    unresolved_inputs: tuple[str, ...]
    additive_sections: Mapping[str, object]
    content_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "safety", MappingProxyType(dict(self.safety)))
        object.__setattr__(
            self, "additive_sections", MappingProxyType(dict(self.additive_sections))
        )

    @property
    def sources_by_id(self) -> Mapping[str, SourceDocument]:
        return MappingProxyType({item.source_id: item for item in self.sources})

    @property
    def species_by_name(self) -> Mapping[str, SpeciesSpecification]:
        # Exact canonical labels are keys.  No "fish" replacement layer exists.
        return MappingProxyType({item.name: item for item in self.species})

    @property
    def crops_by_name(self) -> Mapping[str, CropSpecification]:
        return MappingProxyType({item.name: item for item in self.crop_program.crops})

    @property
    def actual_month_close_allowed(self) -> bool:
        return (
            not self.current_actual_state.live_freeze
            and self.current_actual_state.advance_authorized
            and self.current_actual_state.agriculture_month_close_authorized
        )

    @property
    def physical_execution_ready(self) -> bool:
        return self.actual_month_close_allowed and not self.unresolved_inputs

    def forward_grain_procured_fact(self) -> SourcedValue[Decimal]:
        """Expose the forward zero without allowing it into current actual state."""

        return SourcedValue(
            value=self.forward_k1495_state.grain_procured_tons,
            evidence=self.forward_k1495_state.evidence,
            actual_execution_input=False,
        )
