"""Strict loader for the read-only Baen agriculture canon fixture.

The loader is intentionally fail-closed.  The version-1 fixture is a reviewed
contract: unknown keys, missing evidence, temporal conflation, rounded floats,
renamed species/crops, inconsistent totals, or unsafe side effects all reject
the import instead of being guessed through.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Mapping

from .agriculture_domain import (
    AgricultureCanon,
    BgPoolsProduction,
    BlacklakeProduction,
    BlacklakeWorkforce,
    ConfirmedProduction,
    ConvertedQuarryProduction,
    CropProgram,
    CropSpecification,
    CurrentActualState,
    ForwardAgricultureState,
    KnownConflict,
    NMWCTopology,
    OrchardProduction,
    PondGroup,
    RegistryEntity,
    ReservoirProduction,
    ShelterProduction,
    SourceDocument,
    SpeciesSpecification,
    WaterDistribution,
)
from .operator_codec import canonical_hash
from .source_values import (
    AuthorityClass,
    DecimalRange,
    EvidenceLayer,
    EvidenceReference,
    SourceValueError,
    exact_decimal,
    optional_exact_decimal,
)


AGRICULTURE_CANON_SCHEMA = "tnp.economy.agriculture-canon/1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_AGRICULTURE_CANON_PATH = (
    PROJECT_ROOT / "fixtures" / "agriculture" / "agriculture-canon-v1.json"
)


class AgricultureSourceError(SourceValueError):
    """Raised when agriculture source canon is malformed or unsafe."""


_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_PAGE_ID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
_NOTION_URL = re.compile(r"^https://app\.notion\.com/p/([0-9a-f]{32})$")

_ROOT_KEYS = {
    "schema",
    "retrieved_on",
    "notion_access",
    "campaign_focus",
    "warning",
    "safety",
    "authority_order",
    "sources",
    "registry_entities",
    "current_actual_state",
    "forward_k1495_state",
    "confirmed_production",
    "nmwc_pond_groups",
    "nmwc_topology",
    "species",
    "crop_program",
    "known_conflicts",
    "unresolved_inputs",
}

_EXPECTED_SOURCE_IDS = {
    "registry",
    "shelters",
    "blacklake",
    "converted-quarry",
    "bg-pools",
    "reservoir-fisheries",
    "orchard-chapel",
    "lobster-king-registry",
    "nmwc-complete",
    "water-empire",
    "aquaculture-technical",
    "arik-live-freeze",
    "laden",
    "longsaddle",
}

_EXPECTED_SPECIES = {
    "tiger-shrimp": ("Tiger Shrimp", "Penaeus monodon"),
    "tilapia": ("Tilapia", "Oreochromis niloticus"),
    "freshwater-prawns": ("Freshwater Prawns", "Macrobrachium rosenbergii"),
    "pearl-gourami": ("Pearl Gourami", "Trichogaster leerii"),
    "red-claw-crayfish": ("Red Claw Crayfish", "Cherax quadricarinatus"),
    "littleneck-clams": ("Littleneck Clams", "Leukoma staminea"),
    "largemouth-bass": ("Largemouth Bass", "Micropterus salmoides"),
    "blue-crabs": ("Blue Crabs", "Callinectes sapidus"),
    "yellow-perch": ("Yellow Perch", "Perca flavescens"),
    "freshwater-mussels": ("Freshwater Mussels", "Anodonta cygnea"),
    "rainbow-trout": ("Rainbow Trout", "Oncorhynchus mykiss"),
    "arctic-char": ("Arctic Char", "Salvelinus alpinus"),
    "european-lobster": ("European Lobster", "Homarus gammarus"),
    "northern-pike": ("Northern Pike", "Esox lucius"),
    "signal-crayfish": ("Signal Crayfish", "Pacifastacus leniusculus"),
}

_EXPECTED_CROPS = {
    "wheat": "Wheat",
    "barley": "Barley",
    "rye": "Rye",
    "apple": "Apple Trees",
    "pear": "Pear Trees",
    "cherry": "Cherry Trees",
    "leafy-greens": "Leafy Greens",
    "root-vegetables": "Root Vegetables",
    "herbs": "Herbs",
    "specialty-herbs": "Aqua-Enhanced Specialty Herbs",
    "wine-grapes": "Neverwinter Wine Grapes",
    "tomatoes": "Tomatoes",
}


def _object(
    value: object,
    label: str,
    expected_keys: set[str],
    *,
    allow_extra: bool = False,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise AgricultureSourceError(f"{label} must be an object")
    if (not allow_extra and set(value) != expected_keys) or (
        allow_extra and not expected_keys.issubset(value)
    ):
        missing = sorted(expected_keys - set(value))
        extra = sorted(set(value) - expected_keys)
        raise AgricultureSourceError(
            f"{label} keys differ from schema; missing={missing}, extra={extra}"
        )
    if any(not isinstance(key, str) for key in value):
        raise AgricultureSourceError(f"{label} keys must be text")
    return value


def _array(value: object, label: str) -> tuple[object, ...]:
    if not isinstance(value, list):
        raise AgricultureSourceError(f"{label} must be an array")
    return tuple(value)


def _text(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
    ):
        raise AgricultureSourceError(f"{label} must be clean non-empty text")
    return value


def _slug(value: object, label: str) -> str:
    result = _text(value, label)
    if _ID.fullmatch(result) is None:
        raise AgricultureSourceError(f"{label} must be a lowercase slug")
    return result


def _boolean(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise AgricultureSourceError(f"{label} must be a boolean")
    return value


def _integer(value: object, label: str, *, nullable: bool = False) -> int | None:
    if value is None and nullable:
        return None
    if type(value) is not int or value < 0:
        raise AgricultureSourceError(f"{label} must be a non-negative integer")
    return value


def _strings(value: object, label: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    rows = _array(value, label)
    result = tuple(_text(item, f"{label} item") for item in rows)
    if not result and not allow_empty:
        raise AgricultureSourceError(f"{label} cannot be empty")
    if len(set(result)) != len(result):
        raise AgricultureSourceError(f"{label} cannot contain duplicates")
    return result


def _range(
    value: object,
    label: str,
    *,
    unit_key: str | None = None,
    basis_key: str | None = None,
) -> DecimalRange:
    keys = {"low", "high"}
    if unit_key is not None:
        keys.add(unit_key)
    if basis_key is not None:
        keys.add(basis_key)
    item = _object(value, label, keys)
    return DecimalRange(
        exact_decimal(item["low"], label=f"{label} low"),
        exact_decimal(item["high"], label=f"{label} high"),
        unit=_text(item[unit_key], f"{label} unit") if unit_key else None,
        basis=_text(item[basis_key], f"{label} basis") if basis_key else None,
    )


def _optional_range(
    value: object,
    label: str,
    *,
    unit_key: str | None = None,
    basis_key: str | None = None,
) -> DecimalRange | None:
    if value is None:
        return None
    return _range(value, label, unit_key=unit_key, basis_key=basis_key)


def _read_json(path: Path) -> Mapping[str, object]:
    if not isinstance(path, Path):
        raise AgricultureSourceError("agriculture canon path must be a concrete Path")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AgricultureSourceError(f"cannot read agriculture canon: {exc}") from exc
    return _object(raw, "agriculture canon", _ROOT_KEYS, allow_extra=True)


def _freeze_json(value: object, label: str) -> object:
    """Validate and deeply freeze additive JSON without interpreting it."""

    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise AgricultureSourceError(f"{label} has a non-text key")
        return MappingProxyType(
            {key: _freeze_json(item, f"{label}/{key}") for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(
            _freeze_json(item, f"{label}/{index}")
            for index, item in enumerate(value)
        )
    if isinstance(value, float):
        raise AgricultureSourceError(f"{label} contains an inexact binary float")
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise AgricultureSourceError(f"{label} contains unsupported JSON data")


def _authority(value: object, label: str) -> AuthorityClass:
    try:
        return AuthorityClass(_text(value, label))
    except ValueError as exc:
        raise AgricultureSourceError(f"{label} is unsupported") from exc


def _default_layer(authority: AuthorityClass) -> EvidenceLayer:
    if authority is AuthorityClass.TECHNICAL_DESIGN:
        return EvidenceLayer.TECHNICAL_DESIGN
    if authority is AuthorityClass.PROJECTION:
        return EvidenceLayer.PROJECTION
    if authority is AuthorityClass.UNCONFIRMED:
        return EvidenceLayer.UNCONFIRMED
    return EvidenceLayer.HISTORICAL_OBSERVATION


def _validate_source_documents(
    value: object,
) -> tuple[tuple[SourceDocument, ...], dict[str, SourceDocument]]:
    rows = _array(value, "sources")
    documents: list[SourceDocument] = []
    by_id: dict[str, SourceDocument] = {}
    page_ids: set[str] = set()
    for index, raw in enumerate(rows, start=1):
        item = _object(
            raw,
            f"source {index}",
            {"source_id", "title", "url", "page_id", "authority_class"},
        )
        source_id = _slug(item["source_id"], f"source {index} ID")
        if source_id in by_id:
            raise AgricultureSourceError(f"duplicate source ID: {source_id}")
        page_id = _text(item["page_id"], f"source {source_id} page ID")
        if _PAGE_ID.fullmatch(page_id) is None:
            raise AgricultureSourceError(f"source {source_id} has invalid Notion page ID")
        url = _text(item["url"], f"source {source_id} URL")
        match = _NOTION_URL.fullmatch(url)
        if match is None or match.group(1) != page_id.replace("-", ""):
            raise AgricultureSourceError(
                f"source {source_id} URL does not identify its exact Notion page"
            )
        if page_id in page_ids:
            raise AgricultureSourceError(f"duplicate Notion page ID: {page_id}")
        page_ids.add(page_id)
        document = SourceDocument(
            source_id=source_id,
            title=_text(item["title"], f"source {source_id} title"),
            url=url,
            page_id=page_id,
            authority_class=_authority(
                item["authority_class"], f"source {source_id} authority"
            ),
        )
        documents.append(document)
        by_id[source_id] = document
    if not _EXPECTED_SOURCE_IDS.issubset(by_id):
        raise AgricultureSourceError("version-1 core source set is incomplete")
    return tuple(documents), by_id


def _validate_generic_source_links(
    value: object,
    sources: Mapping[str, SourceDocument],
    *,
    path: str = "root",
) -> None:
    """Validate evidence links inside typed and preserved additive sections."""

    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}/{key}"
            if key == "source_id" or (
                key.endswith("_source_id") and key != "data_source_id"
            ):
                if not isinstance(child, str) or child not in sources:
                    raise AgricultureSourceError(
                        f"{child_path} cites an unknown source: {child!r}"
                    )
            elif key == "source_ids":
                if not isinstance(child, list) or any(
                    not isinstance(item, str) or item not in sources for item in child
                ):
                    raise AgricultureSourceError(
                        f"{child_path} contains an unknown source"
                    )
            _validate_generic_source_links(child, sources, path=child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_generic_source_links(child, sources, path=f"{path}/{index}")


def _evidence(
    source_id: object,
    path: str,
    sources: Mapping[str, SourceDocument],
    *,
    layer: EvidenceLayer | None = None,
) -> EvidenceReference:
    key = _slug(source_id, f"{path} source ID")
    try:
        source = sources[key]
    except KeyError as exc:
        raise AgricultureSourceError(f"{path} cites unknown source: {key}") from exc
    return EvidenceReference(
        source_id=key,
        source_path=path,
        authority_class=source.authority_class,
        layer=layer or _default_layer(source.authority_class),
    )


def _source_evidence_list(
    value: object,
    path: str,
    sources: Mapping[str, SourceDocument],
    *,
    layer: EvidenceLayer,
) -> tuple[EvidenceReference, ...]:
    ids = _strings(value, f"{path} source IDs")
    return tuple(_evidence(item, path, sources, layer=layer) for item in ids)


def _registry_entities(
    value: object, sources: Mapping[str, SourceDocument]
) -> tuple[RegistryEntity, ...]:
    rows = _array(value, "registry entities")
    entities: list[RegistryEntity] = []
    seen: set[str] = set()
    for index, raw in enumerate(rows, start=1):
        item = _object(
            raw,
            f"registry entity {index}",
            {
                "entity_id",
                "name",
                "sector",
                "status",
                "as_of",
                "employees",
                "monthly_revenue_gp",
                "monthly_cost_gp",
                "capital_invested_gp",
                "source_id",
            },
        )
        entity_id = _slug(item["entity_id"], f"registry entity {index} ID")
        if entity_id in seen:
            raise AgricultureSourceError(f"duplicate registry entity: {entity_id}")
        seen.add(entity_id)
        as_of = _text(item["as_of"], f"registry entity {entity_id} as-of")
        evidence = _evidence(
            item["source_id"],
            f"registry_entities/{entity_id}",
            sources,
            layer=(
                EvidenceLayer.UNCONFIRMED
                if _text(item["status"], "registry status") == "Unconfirmed"
                else EvidenceLayer.FUTURE_REFERENCE
                if as_of == "1498 DR"
                else EvidenceLayer.HISTORICAL_OBSERVATION
            ),
        )
        entity = RegistryEntity(
            entity_id=entity_id,
            name=_text(item["name"], f"registry entity {entity_id} name"),
            sector=_text(item["sector"], f"registry entity {entity_id} sector"),
            status=_text(item["status"], f"registry entity {entity_id} status"),
            as_of=as_of,
            employees=_integer(
                item["employees"], f"registry entity {entity_id} employees", nullable=True
            ),
            monthly_revenue_gp=optional_exact_decimal(
                item["monthly_revenue_gp"], label=f"{entity_id} monthly revenue"
            ),
            monthly_cost_gp=optional_exact_decimal(
                item["monthly_cost_gp"], label=f"{entity_id} monthly cost"
            ),
            capital_invested_gp=optional_exact_decimal(
                item["capital_invested_gp"], label=f"{entity_id} capital invested"
            ),
            evidence=evidence,
        )
        if entity.sector not in {"Agriculture", "Aquaculture"}:
            raise AgricultureSourceError(f"{entity_id} has an invalid agriculture sector")
        entities.append(entity)

    expected_entity_ids = {
        "agricultural-shelter-zones",
        "orchard-chapel",
        "blacklake-aquaculture",
        "converted-quarry-aquaculture",
        "bg-aquaculture",
        "reservoir-fisheries",
        "lobster-king",
    }
    if seen != expected_entity_ids:
        raise AgricultureSourceError("version-1 Registry entity set is incomplete")

    baseline = [
        item
        for item in entities
        if item.status == "Operational" and item.as_of == "Eleint 20, 1494"
    ]
    if len(baseline) != 5 or any(
        item.employees is None
        or item.monthly_revenue_gp is None
        or item.monthly_cost_gp is None
        or item.capital_invested_gp is None
        for item in baseline
    ):
        raise AgricultureSourceError("commercial reference baseline is incomplete")
    employees = sum(item.employees or 0 for item in baseline)
    revenue = sum((item.monthly_revenue_gp for item in baseline), start=exact_decimal("0"))
    cost = sum((item.monthly_cost_gp for item in baseline), start=exact_decimal("0"))
    capital = sum((item.capital_invested_gp for item in baseline), start=exact_decimal("0"))
    if (employees, revenue, cost, revenue - cost, capital) != (
        63,
        exact_decimal("26500"),
        exact_decimal("20550"),
        exact_decimal("5950"),
        exact_decimal("111000"),
    ):
        raise AgricultureSourceError("commercial reference totals do not reconcile")
    return tuple(entities)


def _current_actual(
    value: object, sources: Mapping[str, SourceDocument]
) -> CurrentActualState:
    item = _object(
        value,
        "current actual state",
        {
            "campaign_date",
            "live_freeze",
            "advance_authorized",
            "agriculture_month_close_authorized",
            "source_id",
        },
    )
    result = CurrentActualState(
        campaign_date=_text(item["campaign_date"], "current campaign date"),
        live_freeze=_boolean(item["live_freeze"], "current live freeze"),
        advance_authorized=_boolean(
            item["advance_authorized"], "current advance authorization"
        ),
        agriculture_month_close_authorized=_boolean(
            item["agriculture_month_close_authorized"],
            "current agriculture month-close authorization",
        ),
        evidence=_evidence(
            item["source_id"],
            "current_actual_state",
            sources,
            layer=EvidenceLayer.CURRENT_ACTUAL,
        ),
    )
    if result.campaign_date != "Day 7 Hammer 1495 DR, midday Hell-cycle":
        raise AgricultureSourceError("current actual campaign date has drifted")
    if result.evidence.source_id != "arik-live-freeze":
        raise AgricultureSourceError("current actual state cites the wrong authority")
    if (
        not result.live_freeze
        or result.advance_authorized
        or result.agriculture_month_close_authorized
    ):
        raise AgricultureSourceError("current live freeze or authorization boundary changed")
    return result


def _forward_state(
    value: object, sources: Mapping[str, SourceDocument]
) -> ForwardAgricultureState:
    item = _object(
        value,
        "forward Kythorn state",
        {
            "campaign_date",
            "temporal_class",
            "actual_execution_eligible",
            "shelter_zones_total",
            "shelter_zones_destroyed",
            "shelter_zones_not_reported_destroyed",
            "surviving_zones_confirmed_operational",
            "destroyed_zone_ids",
            "longsaddle_population",
            "longsaddle_food_position",
            "longsaddle_first_full_planting",
            "longsaddle_k1495_harvestable_output",
            "longsaddle_first_harvest_window",
            "longsaddle_first_harvest_outcome",
            "first_meaningful_export_surplus",
            "meat_self_sufficiency",
            "meat_export",
            "grain_procurement_target_tons",
            "grain_procured_tons",
            "meat_and_livestock_budget_gp",
            "grain_budget_with_transport_gp",
            "execution_rolls_resolved",
            "transactions_resolved",
            "source_ids",
        },
    )
    destroyed_ids_raw = item["destroyed_zone_ids"]
    destroyed_ids = (
        None
        if destroyed_ids_raw is None
        else _strings(destroyed_ids_raw, "destroyed shelter zone IDs", allow_empty=True)
    )
    result = ForwardAgricultureState(
        campaign_date=_text(item["campaign_date"], "forward campaign date"),
        temporal_class=_text(item["temporal_class"], "forward temporal class"),
        actual_execution_eligible=_boolean(
            item["actual_execution_eligible"], "forward execution eligibility"
        ),
        shelter_zones_total=_integer(item["shelter_zones_total"], "shelter total") or 0,
        shelter_zones_destroyed=_integer(
            item["shelter_zones_destroyed"], "shelters destroyed"
        ) or 0,
        shelter_zones_not_reported_destroyed=_integer(
            item["shelter_zones_not_reported_destroyed"],
            "shelters not reported destroyed",
        ) or 0,
        surviving_zones_confirmed_operational=_integer(
            item["surviving_zones_confirmed_operational"],
            "confirmed operational survivors",
            nullable=True,
        ),
        destroyed_zone_ids=destroyed_ids,
        longsaddle_population=_integer(
            item["longsaddle_population"], "Longsaddle population"
        ) or 0,
        longsaddle_food_position=_text(
            item["longsaddle_food_position"], "Longsaddle food position"
        ),
        longsaddle_first_full_planting=_text(
            item["longsaddle_first_full_planting"], "Longsaddle first planting"
        ),
        longsaddle_k1495_harvestable_output=exact_decimal(
            item["longsaddle_k1495_harvestable_output"],
            label="Longsaddle Kythorn harvestable output",
        ),
        longsaddle_first_harvest_window=_text(
            item["longsaddle_first_harvest_window"], "Longsaddle harvest window"
        ),
        longsaddle_first_harvest_outcome=_text(
            item["longsaddle_first_harvest_outcome"], "Longsaddle harvest outcome"
        ),
        first_meaningful_export_surplus=_text(
            item["first_meaningful_export_surplus"], "first export surplus"
        ),
        meat_self_sufficiency=_text(
            item["meat_self_sufficiency"], "meat self-sufficiency"
        ),
        meat_export=_text(item["meat_export"], "meat export"),
        grain_procurement_target_tons=_range(
            item["grain_procurement_target_tons"], "grain procurement target"
        ),
        grain_procured_tons=exact_decimal(
            item["grain_procured_tons"], label="grain procured"
        ),
        meat_and_livestock_budget_gp=_range(
            item["meat_and_livestock_budget_gp"], "meat/livestock budget"
        ),
        grain_budget_with_transport_gp=_range(
            item["grain_budget_with_transport_gp"], "grain/transport budget"
        ),
        execution_rolls_resolved=_integer(
            item["execution_rolls_resolved"], "forward execution rolls"
        ) or 0,
        transactions_resolved=_integer(
            item["transactions_resolved"], "forward transactions"
        ) or 0,
        evidence=_source_evidence_list(
            item["source_ids"],
            "forward_k1495_state",
            sources,
            layer=EvidenceLayer.FORWARD_SCENARIO,
        ),
    )
    if result.temporal_class != "ratified_forward_scenario_not_current_actual":
        raise AgricultureSourceError("forward state temporal class is unsafe")
    if result.actual_execution_eligible:
        raise AgricultureSourceError("forward scenario cannot be actual execution input")
    if (
        result.shelter_zones_destroyed
        + result.shelter_zones_not_reported_destroyed
        != result.shelter_zones_total
    ):
        raise AgricultureSourceError("forward shelter-zone counts do not reconcile")
    if (
        result.destroyed_zone_ids is not None
        and len(result.destroyed_zone_ids) != result.shelter_zones_destroyed
    ):
        raise AgricultureSourceError("destroyed shelter IDs do not match destroyed count")
    if (
        result.surviving_zones_confirmed_operational is not None
        and result.surviving_zones_confirmed_operational
        > result.shelter_zones_not_reported_destroyed
    ):
        raise AgricultureSourceError("confirmed survivors exceed possible survivors")
    if result.execution_rolls_resolved != 0 or result.transactions_resolved != 0:
        raise AgricultureSourceError("unresolved forward operation cannot contain resolutions")
    return result


def _confirmed_production(
    value: object, sources: Mapping[str, SourceDocument]
) -> ConfirmedProduction:
    item = _object(
        value,
        "confirmed production",
        {
            "shelters",
            "blacklake",
            "converted_quarry",
            "bg_pools",
            "reservoir_fisheries",
            "orchard_chapel_1498",
        },
        allow_extra=True,
    )
    core_keys = {
        "shelters",
        "blacklake",
        "converted_quarry",
        "bg_pools",
        "reservoir_fisheries",
        "orchard_chapel_1498",
    }
    shelters_raw = _object(
        item["shelters"],
        "shelter production",
        {"outputs", "third_greenhouse_yield_vs_expected", "baseline_physical_yield", "source_id"},
        allow_extra=True,
    )
    shelter_core_keys = {
        "outputs",
        "third_greenhouse_yield_vs_expected",
        "baseline_physical_yield",
        "source_id",
    }
    shelters = ShelterProduction(
        outputs=_strings(shelters_raw["outputs"], "shelter outputs"),
        third_greenhouse_yield_vs_expected=_range(
            shelters_raw["third_greenhouse_yield_vs_expected"],
            "third greenhouse yield versus expected",
        ),
        baseline_physical_yield=optional_exact_decimal(
            shelters_raw["baseline_physical_yield"],
            label="shelter baseline physical yield",
        ),
        evidence=_evidence(
            shelters_raw["source_id"],
            "confirmed_production/shelters",
            sources,
            layer=EvidenceLayer.HISTORICAL_OBSERVATION,
        ),
        additive_fields={
            key: _freeze_json(value, f"confirmed_production/shelters/{key}")
            for key, value in shelters_raw.items()
            if key not in shelter_core_keys
        },
    )
    if shelters.outputs != ("greenhouse produce", "tomatoes", "year-round tomatoes"):
        raise AgricultureSourceError("shelter outputs lost their exact canonical labels")
    if shelters.baseline_physical_yield is not None:
        raise AgricultureSourceError("unknown shelter baseline yield cannot be invented")

    blacklake_raw = _object(
        item["blacklake"],
        "Blacklake production",
        {"pool_count", "outputs", "workforce", "source_id"},
    )
    workforce_raw = _object(
        blacklake_raw["workforce"],
        "Blacklake workforce",
        {"farm_manager", "fish_handlers", "processing_workers", "transport", "security"},
    )
    workforce = BlacklakeWorkforce(
        **{
            key: _integer(workforce_raw[key], f"Blacklake workforce {key}") or 0
            for key in workforce_raw
        }
    )
    blacklake = BlacklakeProduction(
        pool_count=_integer(blacklake_raw["pool_count"], "Blacklake pool count") or 0,
        outputs=_strings(blacklake_raw["outputs"], "Blacklake outputs"),
        workforce=workforce,
        evidence=_evidence(
            blacklake_raw["source_id"],
            "confirmed_production/blacklake",
            sources,
            layer=EvidenceLayer.HISTORICAL_OBSERVATION,
        ),
    )
    if workforce.total != 15:
        raise AgricultureSourceError("Blacklake workforce does not reconcile to Registry")

    quarry_raw = _object(
        item["converted_quarry"],
        "converted quarry production",
        {"site_count", "confirmed_species", "evidence", "source_id"},
    )
    quarry = ConvertedQuarryProduction(
        site_count=_integer(quarry_raw["site_count"], "converted quarry site count") or 0,
        confirmed_species=_strings(
            quarry_raw["confirmed_species"], "converted quarry confirmed species"
        ),
        evidence_text=_text(quarry_raw["evidence"], "converted quarry evidence text"),
        evidence=_evidence(
            quarry_raw["source_id"],
            "confirmed_production/converted_quarry",
            sources,
            layer=EvidenceLayer.HISTORICAL_OBSERVATION,
        ),
    )

    bg_raw = _object(
        item["bg_pools"],
        "BG pools production",
        {"site_count", "confirmed_outputs", "water_quality_complication", "source_id"},
    )
    bg_pools = BgPoolsProduction(
        site_count=_integer(bg_raw["site_count"], "BG pools site count") or 0,
        confirmed_outputs=_strings(bg_raw["confirmed_outputs"], "BG confirmed outputs"),
        water_quality_complication=_text(
            bg_raw["water_quality_complication"], "BG water quality complication"
        ),
        evidence=_evidence(
            bg_raw["source_id"],
            "confirmed_production/bg_pools",
            sources,
            layer=EvidenceLayer.HISTORICAL_OBSERVATION,
        ),
    )

    reservoir_raw = _object(
        item["reservoir_fisheries"],
        "reservoir production",
        {"site_count", "confirmed_outputs", "operating_specialty", "source_ids"},
    )
    reservoir = ReservoirProduction(
        site_count=_integer(
            reservoir_raw["site_count"], "reservoir site count", nullable=True
        ),
        confirmed_outputs=_strings(
            reservoir_raw["confirmed_outputs"], "reservoir confirmed outputs"
        ),
        operating_specialty=_text(
            reservoir_raw["operating_specialty"], "reservoir operating specialty"
        ),
        evidence=_source_evidence_list(
            reservoir_raw["source_ids"],
            "confirmed_production/reservoir_fisheries",
            sources,
            layer=EvidenceLayer.HISTORICAL_OBSERVATION,
        ),
    )

    orchard_raw = _object(
        item["orchard_chapel_1498"],
        "Orchard Chapel production",
        {
            "temporal_class",
            "acreage",
            "outputs",
            "processing",
            "annual_revenue_gp",
            "source_ids",
        },
    )
    orchard = OrchardProduction(
        temporal_class=_text(
            orchard_raw["temporal_class"], "Orchard Chapel temporal class"
        ),
        acreage=exact_decimal(orchard_raw["acreage"], label="Orchard Chapel acreage"),
        outputs=_strings(orchard_raw["outputs"], "Orchard Chapel outputs"),
        processing=_strings(
            orchard_raw["processing"], "Orchard Chapel processing"
        ),
        annual_revenue_gp=exact_decimal(
            orchard_raw["annual_revenue_gp"], label="Orchard Chapel annual revenue"
        ),
        evidence=_source_evidence_list(
            orchard_raw["source_ids"],
            "confirmed_production/orchard_chapel_1498",
            sources,
            layer=EvidenceLayer.FUTURE_REFERENCE,
        ),
    )
    if orchard.temporal_class != "later_than_day7_hammer1495":
        raise AgricultureSourceError("Orchard Chapel later state was backdated")
    return ConfirmedProduction(
        shelters=shelters,
        blacklake=blacklake,
        converted_quarry=quarry,
        bg_pools=bg_pools,
        reservoir_fisheries=reservoir,
        orchard_chapel_1498=orchard,
        additive_sections={
            key: _freeze_json(value, f"confirmed_production/{key}")
            for key, value in item.items()
            if key not in core_keys
        },
    )


def _pond_groups(
    value: object, sources: Mapping[str, SourceDocument]
) -> tuple[PondGroup, ...]:
    rows = _array(value, "NMWC pond groups")
    result: list[PondGroup] = []
    seen: set[str] = set()
    for index, raw in enumerate(rows, start=1):
        item = _object(
            raw,
            f"NMWC pond group {index}",
            {
                "group_id",
                "temporal_class",
                "ponds",
                "temperature_f_low",
                "temperature_f_high",
                "species_labels",
                "annual_yield_lb",
                "source_id",
            },
        )
        group_id = _slug(item["group_id"], f"pond group {index} ID")
        if group_id in seen:
            raise AgricultureSourceError(f"duplicate pond group: {group_id}")
        seen.add(group_id)
        result.append(
            PondGroup(
                group_id=group_id,
                temporal_class=_text(
                    item["temporal_class"], f"pond group {group_id} temporal class"
                ),
                ponds=_integer(item["ponds"], f"pond group {group_id} count") or 0,
                temperature_f=DecimalRange(
                    exact_decimal(
                        item["temperature_f_low"], label=f"{group_id} low temperature"
                    ),
                    exact_decimal(
                        item["temperature_f_high"], label=f"{group_id} high temperature"
                    ),
                    unit="degrees_fahrenheit",
                ),
                species_labels=_strings(
                    item["species_labels"], f"pond group {group_id} species"
                ),
                annual_yield_lb=exact_decimal(
                    item["annual_yield_lb"], label=f"pond group {group_id} annual yield"
                ),
                evidence=_evidence(
                    item["source_id"], f"nmwc_pond_groups/{group_id}", sources
                ),
            )
        )
    if seen != {"warm", "moderate", "cool"}:
        raise AgricultureSourceError("NMWC pond groups must be warm, moderate, and cool")
    if any(
        item.temporal_class != "technical_capacity_not_day7_hammer1495_actual"
        for item in result
    ):
        raise AgricultureSourceError("NMWC pond group was promoted into current actual")
    return tuple(result)


def _topology(
    value: object, sources: Mapping[str, SourceDocument]
) -> NMWCTopology:
    item = _object(
        value,
        "NMWC topology",
        {
            "ponds",
            "temporal_class",
            "day7_hammer1495_execution_eligible",
            "capacity_each_cubic_meters",
            "total_capacity_cubic_meters",
            "total_capacity_approx_gallons",
            "continuous_harvest_design",
            "total_annual_yield_lb",
            "source_ids",
        },
    )
    evidence_ids = _strings(item["source_ids"], "NMWC topology source IDs")
    evidence = tuple(
        _evidence(source_id, "nmwc_topology", sources) for source_id in evidence_ids
    )
    result = NMWCTopology(
        temporal_class=_text(item["temporal_class"], "NMWC topology temporal class"),
        day7_hammer1495_execution_eligible=_boolean(
            item["day7_hammer1495_execution_eligible"],
            "NMWC topology Day 7 execution eligibility",
        ),
        ponds=_integer(item["ponds"], "NMWC topology pond count") or 0,
        capacity_each_cubic_meters=exact_decimal(
            item["capacity_each_cubic_meters"], label="NMWC per-pond capacity"
        ),
        total_capacity_cubic_meters=exact_decimal(
            item["total_capacity_cubic_meters"], label="NMWC total capacity"
        ),
        total_capacity_approx_gallons=exact_decimal(
            item["total_capacity_approx_gallons"], label="NMWC approximate gallons"
        ),
        continuous_harvest_design=_boolean(
            item["continuous_harvest_design"], "NMWC continuous harvest design"
        ),
        total_annual_yield_lb=exact_decimal(
            item["total_annual_yield_lb"], label="NMWC total annual yield"
        ),
        evidence=evidence,
    )
    if (
        result.temporal_class != "later_or_technical_not_day7_hammer1495_actual"
        or result.day7_hammer1495_execution_eligible
    ):
        raise AgricultureSourceError("NMWC topology was promoted into current actual")
    return result


def _species(
    value: object, sources: Mapping[str, SourceDocument]
) -> tuple[SpeciesSpecification, ...]:
    rows = _array(value, "species")
    result: list[SpeciesSpecification] = []
    seen: set[str] = set()
    names: set[str] = set()
    for index, raw in enumerate(rows, start=1):
        item = _object(
            raw,
            f"species {index}",
            {
                "species_id",
                "name",
                "scientific_name",
                "zone",
                "role",
                "growth_months",
                "stocking_density",
                "feed_conversion_ratio",
                "market_gp_per_lb",
                "annual_yield_lb_per_1000_unit",
                "source_id",
            },
        )
        species_id = _slug(item["species_id"], f"species {index} ID")
        name = _text(item["name"], f"species {species_id} name")
        scientific_name = _text(
            item["scientific_name"], f"species {species_id} scientific name"
        )
        if species_id in seen or name in names:
            raise AgricultureSourceError(f"duplicate species identity: {species_id}")
        seen.add(species_id)
        names.add(name)
        if _EXPECTED_SPECIES.get(species_id) != (name, scientific_name):
            raise AgricultureSourceError(
                f"species {species_id} lost its canonical common/scientific name"
            )
        zone = _text(item["zone"], f"species {species_id} zone")
        role = _text(item["role"], f"species {species_id} role")
        if zone not in {"warm", "moderate", "cool"} or role not in {"primary", "specialty"}:
            raise AgricultureSourceError(f"species {species_id} classification is invalid")
        result.append(
            SpeciesSpecification(
                species_id=species_id,
                name=name,
                scientific_name=scientific_name,
                zone=zone,
                role=role,
                growth_months=_range(item["growth_months"], f"{species_id} growth months"),
                stocking_density=_range(
                    item["stocking_density"],
                    f"{species_id} stocking density",
                    unit_key="unit",
                ),
                feed_conversion_ratio=_optional_range(
                    item["feed_conversion_ratio"], f"{species_id} feed conversion ratio"
                ),
                market_gp_per_lb=_range(
                    item["market_gp_per_lb"], f"{species_id} market price"
                ),
                annual_yield_lb_per_1000_unit=_optional_range(
                    item["annual_yield_lb_per_1000_unit"],
                    f"{species_id} annual yield",
                    basis_key="basis",
                ),
                evidence=_evidence(
                    item["source_id"],
                    f"species/{species_id}",
                    sources,
                    layer=EvidenceLayer.TECHNICAL_DESIGN,
                ),
            )
        )
    if seen != set(_EXPECTED_SPECIES):
        raise AgricultureSourceError("version-1 named species set is incomplete")
    return tuple(result)


def _crop_program(
    value: object, sources: Mapping[str, SourceDocument]
) -> CropProgram:
    item = _object(
        value,
        "crop program",
        {
            "overall_aqua_enhanced_yield_increase",
            "fertilizer_reduction",
            "water_distribution",
            "crops",
            "source_ids",
        },
    )
    water_raw = _object(
        item["water_distribution"],
        "crop water distribution",
        {"capacity_gallons_per_minute", "field_range_miles"},
    )
    crops: list[CropSpecification] = []
    seen: set[str] = set()
    names: set[str] = set()
    for index, raw in enumerate(_array(item["crops"], "crops"), start=1):
        crop = _object(
            raw,
            f"crop {index}",
            {"crop_id", "name", "class", "yield_increase", "confirmed_planted"},
        )
        crop_id = _slug(crop["crop_id"], f"crop {index} ID")
        name = _text(crop["name"], f"crop {crop_id} name")
        if crop_id in seen or name in names:
            raise AgricultureSourceError(f"duplicate crop identity: {crop_id}")
        seen.add(crop_id)
        names.add(name)
        if _EXPECTED_CROPS.get(crop_id) != name:
            raise AgricultureSourceError(f"crop {crop_id} lost its canonical name")
        crops.append(
            CropSpecification(
                crop_id=crop_id,
                name=name,
                crop_class=_text(crop["class"], f"crop {crop_id} class"),
                yield_increase=_optional_range(
                    crop["yield_increase"], f"crop {crop_id} yield increase"
                ),
                confirmed_planted=_boolean(
                    crop["confirmed_planted"], f"crop {crop_id} planted status"
                ),
            )
        )
    if seen != set(_EXPECTED_CROPS):
        raise AgricultureSourceError("version-1 named crop set is incomplete")
    planted = [crop.crop_id for crop in crops if crop.confirmed_planted]
    if planted != ["tomatoes"]:
        raise AgricultureSourceError(
            "technical crop options cannot be promoted to confirmed planting"
        )
    evidence_ids = _strings(item["source_ids"], "crop program source IDs")
    evidence = tuple(_evidence(source_id, "crop_program", sources) for source_id in evidence_ids)
    return CropProgram(
        overall_aqua_enhanced_yield_increase=_range(
            item["overall_aqua_enhanced_yield_increase"],
            "overall aqua-enhanced yield increase",
        ),
        fertilizer_reduction=_range(
            item["fertilizer_reduction"], "fertilizer reduction"
        ),
        water_distribution=WaterDistribution(
            capacity_gallons_per_minute=_range(
                water_raw["capacity_gallons_per_minute"],
                "water distribution capacity",
            ),
            field_range_miles=_range(
                water_raw["field_range_miles"], "water distribution field range"
            ),
        ),
        crops=tuple(crops),
        evidence=evidence,
    )


def _conflicts(value: object) -> tuple[KnownConflict, ...]:
    result: list[KnownConflict] = []
    seen: set[str] = set()
    for index, raw in enumerate(_array(value, "known conflicts"), start=1):
        item = _object(
            raw,
            f"known conflict {index}",
            {"conflict_id", "description", "blocking_for"},
        )
        conflict_id = _slug(item["conflict_id"], f"known conflict {index} ID")
        if conflict_id in seen:
            raise AgricultureSourceError(f"duplicate known conflict: {conflict_id}")
        seen.add(conflict_id)
        result.append(
            KnownConflict(
                conflict_id=conflict_id,
                description=_text(item["description"], f"conflict {conflict_id} description"),
                blocking_for=_strings(item["blocking_for"], f"conflict {conflict_id} blockers"),
            )
        )
    expected = {
        "pond-topology",
        "pond-temperature",
        "physical-vs-financial-revenue",
        "shelter-topology",
    }
    if not expected.issubset(seen):
        raise AgricultureSourceError("version-1 core conflict set is incomplete")
    return tuple(result)


def _validate_cross_references(canon: AgricultureCanon) -> None:
    species_by_name = canon.species_by_name
    for group in canon.nmwc_pond_groups:
        for label in group.species_labels:
            if label not in species_by_name:
                raise AgricultureSourceError(
                    f"pond group uses unnamed or generic species label: {label}"
                )
            if species_by_name[label].zone != group.group_id:
                raise AgricultureSourceError(
                    f"species {label} is assigned to the wrong temperature group"
                )
    for label in canon.confirmed_production.converted_quarry.confirmed_species:
        if label not in species_by_name:
            raise AgricultureSourceError(
                f"converted quarry uses unnamed or generic species label: {label}"
            )

    pond_count = sum(group.ponds for group in canon.nmwc_pond_groups)
    annual_yield = sum(
        (group.annual_yield_lb for group in canon.nmwc_pond_groups),
        start=exact_decimal("0"),
    )
    if pond_count != canon.nmwc_topology.ponds:
        raise AgricultureSourceError("NMWC pond-group counts do not match topology")
    if annual_yield != canon.nmwc_topology.total_annual_yield_lb:
        raise AgricultureSourceError("NMWC pond-group yields do not match total")
    if (
        canon.nmwc_topology.capacity_each_cubic_meters
        * canon.nmwc_topology.ponds
        != canon.nmwc_topology.total_capacity_cubic_meters
    ):
        raise AgricultureSourceError("NMWC pond capacity does not reconcile")

    if canon.confirmed_production.blacklake.pool_count != 7:
        raise AgricultureSourceError("Blacklake pool count does not match its source")
    if canon.confirmed_production.converted_quarry.site_count != 5:
        raise AgricultureSourceError("converted quarry site count does not match its source")
    if canon.confirmed_production.bg_pools.site_count != 3:
        raise AgricultureSourceError("BG pool site count does not match its source")


def load_agriculture_canon(
    path: Path = DEFAULT_AGRICULTURE_CANON_PATH,
) -> AgricultureCanon:
    """Load and validate the source-bound agriculture canon.

    This is a read-only operation.  It performs no Notion writes, ledger
    postings, dice rolls, or campaign-time advancement.
    """

    raw = _read_json(path)
    if raw["schema"] != AGRICULTURE_CANON_SCHEMA:
        raise AgricultureSourceError("agriculture canon schema is unsupported")
    if raw["notion_access"] != "read_only":
        raise AgricultureSourceError("agriculture canon must remain read-only")

    safety = _object(
        raw["safety"],
        "agriculture safety",
        {
            "notion_writes",
            "canonical_ledger_postings",
            "dice_rolled",
            "campaign_time_advanced",
        },
    )
    if (
        _integer(safety["notion_writes"], "Notion writes") != 0
        or _integer(safety["canonical_ledger_postings"], "ledger postings") != 0
        or _integer(safety["dice_rolled"], "dice rolled") != 0
        or _boolean(safety["campaign_time_advanced"], "time advanced")
    ):
        raise AgricultureSourceError("agriculture source import records unsafe side effects")

    order_values = _strings(raw["authority_order"], "authority order")
    authority_order = tuple(_authority(item, "authority order item") for item in order_values)
    if authority_order != (
        AuthorityClass.RATIFIED_CAMPAIGN_STATE,
        AuthorityClass.OBSERVED_OPERATING_STATE,
        AuthorityClass.TECHNICAL_DESIGN,
        AuthorityClass.PROJECTION,
        AuthorityClass.UNCONFIRMED,
    ):
        raise AgricultureSourceError("authority order has drifted")

    sources, source_index = _validate_source_documents(raw["sources"])
    _validate_generic_source_links(raw, source_index)
    current_actual_state = _current_actual(raw["current_actual_state"], source_index)
    forward_state = _forward_state(raw["forward_k1495_state"], source_index)
    if current_actual_state.campaign_date == forward_state.campaign_date:
        raise AgricultureSourceError("current actual and forward campaign dates were conflated")

    pond_groups = _pond_groups(raw["nmwc_pond_groups"], source_index)
    topology = _topology(raw["nmwc_topology"], source_index)
    species = _species(raw["species"], source_index)
    crop_program = _crop_program(raw["crop_program"], source_index)
    unresolved = _strings(raw["unresolved_inputs"], "unresolved inputs")
    if len(unresolved) != 13:
        raise AgricultureSourceError("version-1 unresolved-input docket is incomplete")

    canon = AgricultureCanon(
        schema=_text(raw["schema"], "agriculture schema"),
        retrieved_on=_text(raw["retrieved_on"], "retrieval date"),
        notion_access=_text(raw["notion_access"], "Notion access"),
        campaign_focus=_text(raw["campaign_focus"], "campaign focus"),
        warning=_text(raw["warning"], "authority warning"),
        safety=dict(safety),
        authority_order=authority_order,
        sources=sources,
        registry_entities=_registry_entities(raw["registry_entities"], source_index),
        current_actual_state=current_actual_state,
        forward_k1495_state=forward_state,
        confirmed_production=_confirmed_production(
            raw["confirmed_production"], source_index
        ),
        nmwc_pond_groups=pond_groups,
        nmwc_topology=topology,
        species=species,
        crop_program=crop_program,
        known_conflicts=_conflicts(raw["known_conflicts"]),
        unresolved_inputs=unresolved,
        additive_sections={
            key: _freeze_json(value, f"agriculture canon/{key}")
            for key, value in raw.items()
            if key not in _ROOT_KEYS
        },
        content_hash=canonical_hash(raw),
    )
    _validate_cross_references(canon)
    return canon
