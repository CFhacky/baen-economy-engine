"""Source-locked opening scenarios for the runnable regional economy slice.

Business identities and reported operating figures are derived at load time
from the verified 90-row Business Registry export.  Commodity definitions,
recipes, inventories, labour availability, routes, demand, prices, and opening
cash are deliberately separate, non-canonical scenario inputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path, PurePosixPath
import re
from types import MappingProxyType
from typing import Mapping

from .operator_codec import CodecError, canonical_hash, json_safe, verify_content_hash
from .registry import stable_entity_id
from .registry_export import RegistryExportError, load_registry_export


REGIONAL_SCENARIO_SCHEMA = "tnp.economy.regional-scenario/1"
REGIONAL_SCENARIO_ID = "baen-regional-mvp"
REGIONAL_PROFILE_ID = "baen-north-preview-v1"
SCENARIO_AUTHORITY = "scenario_input"
REGISTRY_FIXTURE_PATH = (
    "fixtures/registry-snapshots/business-registry-2026-08-29.json"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?::[a-z0-9][a-z0-9-]*)+$")
_SOURCE_ID_RE = re.compile(r"^notion:[0-9a-f]{32}$")


class RegionalScenarioError(ValueError):
    """Raised when an opening scenario or its Registry binding has drifted."""


@dataclass(frozen=True, slots=True)
class SourceBusiness:
    """A selected business whose factual fields come only from the Registry."""

    source_record_id: str
    source_row_hash: str
    source_ref: str
    entity_id: str
    name: str
    sector: str
    city: str
    status: str
    monthly_revenue_gp: Decimal
    monthly_cost_gp: Decimal
    employees: int

    def __post_init__(self) -> None:
        _require_source_id(self.source_record_id, "business source record")
        _require_sha256(self.source_row_hash, "business source row hash")
        _require_text(self.source_ref, "business source reference")
        _require_id(self.entity_id, "business entity")
        for value, label in (
            (self.name, "business name"),
            (self.sector, "business sector"),
            (self.city, "business city"),
            (self.status, "business status"),
        ):
            _require_text(value, label)
        _require_decimal(self.monthly_revenue_gp, "business monthly revenue", minimum=0)
        _require_decimal(self.monthly_cost_gp, "business monthly cost", minimum=0)
        if type(self.employees) is not int or self.employees < 0:
            raise RegionalScenarioError("business employees must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class ScenarioTimeline:
    timeline_id: str
    month_index: int
    campaign_date_label: str
    basis: str


@dataclass(frozen=True, slots=True)
class BusinessRole:
    source_record_id: str
    entity_id: str
    role: str
    basis: str


@dataclass(frozen=True, slots=True)
class CommodityAssumption:
    commodity_id: str
    name: str
    unit: str
    perishable_loss_rate: Decimal
    basis: str


@dataclass(frozen=True, slots=True)
class SiteAssumption:
    site_id: str
    source_record_id: str
    owner_id: str
    name: str
    basis: str


@dataclass(frozen=True, slots=True)
class InventoryAssumption:
    inventory_id: str
    source_record_id: str
    owner_id: str
    site_id: str
    commodity_id: str
    quantity: Decimal
    basis: str


@dataclass(frozen=True, slots=True)
class LaborPoolAssumption:
    labor_pool_id: str
    source_record_id: str
    owner_id: str
    site_id: str
    labor_class: str
    workers: int
    available_worker_days: Decimal
    wage_gp_per_day: Decimal
    basis: str


@dataclass(frozen=True, slots=True)
class MaterialAmount:
    commodity_id: str
    quantity_per_batch: Decimal


@dataclass(frozen=True, slots=True)
class RecipeAssumption:
    recipe_id: str
    source_record_id: str
    operator_id: str
    site_id: str
    inputs: tuple[MaterialAmount, ...]
    outputs: tuple[MaterialAmount, ...]
    labor_class: str
    worker_days_per_batch: Decimal
    max_batches_per_month: Decimal
    priority: int
    basis: str


@dataclass(frozen=True, slots=True)
class RouteAssumption:
    route_id: str
    source_record_id: str
    operator_id: str
    origin_site_id: str
    destination_site_id: str
    commodity_id: str
    capacity_per_month: Decimal
    travel_periods: int
    loss_rate: Decimal
    transport_cost_gp_per_dispatched_unit: Decimal
    basis: str


@dataclass(frozen=True, slots=True)
class DemandAssumption:
    demand_id: str
    source_record_id: str
    buyer_id: str
    site_id: str
    commodity_id: str
    quantity: Decimal
    reservation_price_gp_per_delivered_unit: Decimal | None
    priority: int
    basis: str


@dataclass(frozen=True, slots=True)
class OpeningPriceAssumption:
    price_id: str
    site_id: str
    commodity_id: str
    amount_gp_per_unit: Decimal
    basis: str


@dataclass(frozen=True, slots=True)
class OpeningPositionAssumption:
    source_record_id: str
    entity_id: str
    entity_type: str
    balances: tuple[tuple[str, Decimal], ...]
    basis: str

    def balance(self, account: str) -> Decimal:
        try:
            return dict(self.balances)[account]
        except KeyError as exc:
            raise RegionalScenarioError(
                f"opening position for {self.entity_id} has no {account} balance"
            ) from exc


@dataclass(frozen=True, slots=True)
class RegionalScenario:
    """Fully verified source selection plus an executable assumption overlay."""

    scenario_id: str
    assumption_profile_id: str
    payload_hash: str
    registry_content_hash: str
    registry_snapshot_hash: str
    registry_export_hash: str
    registry_source_schema_hash: str
    timeline: ScenarioTimeline
    businesses: tuple[SourceBusiness, ...]
    business_roles: tuple[BusinessRole, ...]
    commodities: tuple[CommodityAssumption, ...]
    sites: tuple[SiteAssumption, ...]
    inventories: tuple[InventoryAssumption, ...]
    labor_pools: tuple[LaborPoolAssumption, ...]
    recipes: tuple[RecipeAssumption, ...]
    routes: tuple[RouteAssumption, ...]
    demands: tuple[DemandAssumption, ...]
    opening_prices: tuple[OpeningPriceAssumption, ...]
    opening_positions: tuple[OpeningPositionAssumption, ...]
    permissions: Mapping[str, bool]
    warning: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "permissions", MappingProxyType(dict(self.permissions)))

    @property
    def canonical(self) -> bool:
        return False

    def business(self, entity_id: str) -> SourceBusiness:
        for business in self.businesses:
            if business.entity_id == entity_id:
                return business
        raise RegionalScenarioError(f"scenario has no selected business {entity_id}")

    def business_from_source(self, source_record_id: str) -> SourceBusiness:
        for business in self.businesses:
            if business.source_record_id == source_record_id:
                return business
        raise RegionalScenarioError(
            f"scenario has no selected Registry record {source_record_id}"
        )

    def to_dict(self) -> dict[str, object]:
        """Return a complete normalized payload for durable local persistence.

        This payload contains the already verified Registry-derived fields and
        every typed scenario input needed by production, market, transport, and
        finance adapters.  Reloading it never requires a Notion request.
        """

        body: dict[str, object] = {
            "schema": "tnp.economy.regional-scenario-normalized/1",
            "scenario_id": self.scenario_id,
            "assumption_profile_id": self.assumption_profile_id,
            "canonical": False,
            "fixture_content_hash": self.payload_hash,
            "registry_binding": {
                "content_hash": self.registry_content_hash,
                "snapshot_hash": self.registry_snapshot_hash,
                "export_hash": self.registry_export_hash,
                "source_schema_hash": self.registry_source_schema_hash,
            },
            "timeline": {
                "timeline_id": self.timeline.timeline_id,
                "month_index": self.timeline.month_index,
                "campaign_date_label": self.timeline.campaign_date_label,
                "basis": self.timeline.basis,
            },
            "businesses": [
                {
                    "source_record_id": item.source_record_id,
                    "source_row_hash": item.source_row_hash,
                    "source_ref": item.source_ref,
                    "entity_id": item.entity_id,
                    "name": item.name,
                    "sector": item.sector,
                    "city": item.city,
                    "status": item.status,
                    "source_monthly_revenue_gp": item.monthly_revenue_gp,
                    "source_monthly_cost_gp": item.monthly_cost_gp,
                    "source_employees": item.employees,
                    "financial_semantics": "source_benchmark_not_opening_cash_or_automatic_transaction",
                }
                for item in self.businesses
            ],
            "business_roles": [
                {
                    "source_record_id": item.source_record_id,
                    "entity_id": item.entity_id,
                    "role": item.role,
                    "basis": item.basis,
                }
                for item in self.business_roles
            ],
            "commodities": [
                {
                    "commodity_id": item.commodity_id,
                    "name": item.name,
                    "unit": item.unit,
                    "perishable_loss_rate": item.perishable_loss_rate,
                    "basis": item.basis,
                }
                for item in self.commodities
            ],
            "sites": [
                {
                    "site_id": item.site_id,
                    "source_record_id": item.source_record_id,
                    "owner_id": item.owner_id,
                    "name": item.name,
                    "basis": item.basis,
                }
                for item in self.sites
            ],
            "inventories": [
                {
                    "inventory_id": item.inventory_id,
                    "source_record_id": item.source_record_id,
                    "owner_id": item.owner_id,
                    "site_id": item.site_id,
                    "commodity_id": item.commodity_id,
                    "quantity": item.quantity,
                    "basis": item.basis,
                }
                for item in self.inventories
            ],
            "labor_pools": [
                {
                    "labor_pool_id": item.labor_pool_id,
                    "source_record_id": item.source_record_id,
                    "owner_id": item.owner_id,
                    "site_id": item.site_id,
                    "labor_class": item.labor_class,
                    "source_workers": item.workers,
                    "available_worker_days": item.available_worker_days,
                    "wage_gp_per_day": item.wage_gp_per_day,
                    "basis": item.basis,
                }
                for item in self.labor_pools
            ],
            "recipes": [
                {
                    "recipe_id": item.recipe_id,
                    "source_record_id": item.source_record_id,
                    "operator_id": item.operator_id,
                    "site_id": item.site_id,
                    "inputs": [
                        {
                            "commodity_id": amount.commodity_id,
                            "quantity_per_batch": amount.quantity_per_batch,
                        }
                        for amount in item.inputs
                    ],
                    "outputs": [
                        {
                            "commodity_id": amount.commodity_id,
                            "quantity_per_batch": amount.quantity_per_batch,
                        }
                        for amount in item.outputs
                    ],
                    "labor_class": item.labor_class,
                    "worker_days_per_batch": item.worker_days_per_batch,
                    "max_batches_per_month": item.max_batches_per_month,
                    "priority": item.priority,
                    "basis": item.basis,
                }
                for item in self.recipes
            ],
            "routes": [
                {
                    "route_id": item.route_id,
                    "source_record_id": item.source_record_id,
                    "operator_id": item.operator_id,
                    "origin_site_id": item.origin_site_id,
                    "destination_site_id": item.destination_site_id,
                    "commodity_id": item.commodity_id,
                    "capacity_per_month": item.capacity_per_month,
                    "travel_periods": item.travel_periods,
                    "loss_rate": item.loss_rate,
                    "transport_cost_gp_per_dispatched_unit": item.transport_cost_gp_per_dispatched_unit,
                    "basis": item.basis,
                }
                for item in self.routes
            ],
            "demands": [
                {
                    "demand_id": item.demand_id,
                    "source_record_id": item.source_record_id,
                    "buyer_id": item.buyer_id,
                    "site_id": item.site_id,
                    "commodity_id": item.commodity_id,
                    "quantity": item.quantity,
                    "reservation_price_gp_per_delivered_unit": item.reservation_price_gp_per_delivered_unit,
                    "priority": item.priority,
                    "basis": item.basis,
                }
                for item in self.demands
            ],
            "opening_prices": [
                {
                    "price_id": item.price_id,
                    "site_id": item.site_id,
                    "commodity_id": item.commodity_id,
                    "amount_gp_per_unit": item.amount_gp_per_unit,
                    "basis": item.basis,
                }
                for item in self.opening_prices
            ],
            "opening_positions": [
                {
                    "source_record_id": item.source_record_id,
                    "entity_id": item.entity_id,
                    "entity_type": item.entity_type,
                    "balances": dict(item.balances),
                    "basis": item.basis,
                }
                for item in self.opening_positions
            ],
            "permissions": dict(self.permissions),
            "warning": self.warning,
        }
        result = json_safe(body)
        assert isinstance(result, dict)
        result["normalized_hash"] = canonical_hash(body)
        return result

    def opening_state(self):
        """Build the production kernel's period-zero state.

        The import is local so the source/fixture audit remains usable even when
        only the scenario layer is being inspected.
        """

        from .regional_domain import (  # Local import avoids a module cycle.
            CommoditySpec,
            InventoryLot,
            LaborPool,
            RegionalState,
        )

        return RegionalState(
            month_index=self.timeline.month_index,
            commodities=tuple(
                CommoditySpec(
                    commodity_id=item.commodity_id,
                    name=item.name,
                    unit=item.unit,
                    source_ref=_assumption_ref("commodity", item.commodity_id),
                    perishable_loss_rate=item.perishable_loss_rate,
                )
                for item in self.commodities
            ),
            inventories=tuple(
                InventoryLot(
                    owner_id=item.owner_id,
                    site_id=item.site_id,
                    commodity_id=item.commodity_id,
                    quantity=item.quantity,
                    source_ref=_assumption_ref("inventory", item.inventory_id),
                )
                for item in self.inventories
            ),
            labor_pools=tuple(
                LaborPool(
                    owner_id=item.owner_id,
                    site_id=item.site_id,
                    labor_class=item.labor_class,
                    workers=Decimal(item.workers),
                    available_worker_days=item.available_worker_days,
                    wage_gp_per_day=item.wage_gp_per_day,
                    source_ref=_assumption_ref("labor", item.labor_pool_id),
                )
                for item in self.labor_pools
            ),
        )

    def production_recipes(self):
        """Build strict production-domain recipes from scenario inputs."""

        from .regional_domain import (
            LaborRequirement,
            MaterialRequirement,
            ProductionRecipe,
        )

        return tuple(
            ProductionRecipe(
                recipe_id=item.recipe_id,
                operator_id=item.operator_id,
                site_id=item.site_id,
                inputs=tuple(
                    MaterialRequirement(
                        commodity_id=amount.commodity_id,
                        quantity_per_batch=amount.quantity_per_batch,
                    )
                    for amount in item.inputs
                ),
                outputs=tuple(
                    MaterialRequirement(
                        commodity_id=amount.commodity_id,
                        quantity_per_batch=amount.quantity_per_batch,
                    )
                    for amount in item.outputs
                ),
                labor_requirements=(
                    LaborRequirement(
                        labor_class=item.labor_class,
                        worker_days_per_batch=item.worker_days_per_batch,
                    ),
                ),
                max_batches_per_month=item.max_batches_per_month,
                source_ref=_assumption_ref("recipe", item.recipe_id),
                priority=item.priority,
            )
            for item in self.recipes
        )


def load_regional_scenario(
    scenario_path: Path,
    registry_path: Path,
) -> RegionalScenario:
    """Load a non-canonical scenario and fail closed on any Registry drift."""

    if not isinstance(scenario_path, Path) or not isinstance(registry_path, Path):
        raise RegionalScenarioError("scenario and registry paths must be concrete Paths")
    payload = _load_json(scenario_path)
    _exact_keys(
        payload,
        {
            "schema",
            "scenario_id",
            "assumption_profile_id",
            "mode",
            "canonical",
            "registry_binding",
            "selected_source_records",
            "assumptions",
            "permissions",
            "warning",
            "content_hash",
        },
        "regional scenario",
    )
    if payload["schema"] != REGIONAL_SCENARIO_SCHEMA:
        raise RegionalScenarioError("regional scenario schema is unsupported")
    if (
        payload["scenario_id"] != REGIONAL_SCENARIO_ID
        or payload["assumption_profile_id"] != REGIONAL_PROFILE_ID
    ):
        raise RegionalScenarioError("regional scenario identity is unsupported")
    if payload["mode"] != "preview" or payload["canonical"] is not False:
        raise RegionalScenarioError("regional scenario must remain a non-canonical preview")
    try:
        verify_content_hash(payload, label="regional scenario")
    except CodecError as exc:
        raise RegionalScenarioError(str(exc)) from exc

    permissions = _permissions(payload["permissions"])
    warning = _text(payload["warning"], "regional scenario warning")
    try:
        registry = load_registry_export(registry_path)
    except RegistryExportError as exc:
        raise RegionalScenarioError(f"Registry export failed verification: {exc}") from exc
    _verify_registry_binding(payload["registry_binding"], registry, registry_path)

    selected = _selected_records(payload["selected_source_records"])
    businesses = tuple(_source_business(registry, item) for item in selected)
    by_source = {business.source_record_id: business for business in businesses}
    if len(by_source) != len(businesses):
        raise RegionalScenarioError("regional scenario repeats a selected source record")

    assumptions = _mapping(payload["assumptions"], "scenario assumptions")
    _exact_keys(
        assumptions,
        {
            "authority",
            "canonical",
            "warning",
            "timeline",
            "business_roles",
            "commodities",
            "sites",
            "inventories",
            "labor_pools",
            "recipes",
            "routes",
            "demands",
            "opening_prices",
            "opening_positions",
        },
        "scenario assumptions",
    )
    if (
        assumptions["authority"] != SCENARIO_AUTHORITY
        or assumptions["canonical"] is not False
    ):
        raise RegionalScenarioError(
            "scenario assumptions must be explicit non-canonical scenario inputs"
        )
    _text(assumptions["warning"], "scenario assumption warning")

    timeline = _timeline(assumptions["timeline"])
    roles = tuple(
        _business_role(item, by_source)
        for item in _objects(assumptions["business_roles"], "business roles")
    )
    commodities = tuple(
        _commodity(item)
        for item in _objects(assumptions["commodities"], "commodities")
    )
    sites = tuple(
        _site(item, by_source)
        for item in _objects(assumptions["sites"], "sites")
    )
    inventories = tuple(
        _inventory(item, by_source)
        for item in _objects(assumptions["inventories"], "inventories")
    )
    labor_pools = tuple(
        _labor_pool(item, by_source)
        for item in _objects(assumptions["labor_pools"], "labor pools")
    )
    recipes = tuple(
        _recipe(item, by_source)
        for item in _objects(assumptions["recipes"], "recipes")
    )
    routes = tuple(
        _route(item, by_source)
        for item in _objects(assumptions["routes"], "routes")
    )
    demands = tuple(
        _demand(item, by_source)
        for item in _objects(assumptions["demands"], "demands")
    )
    opening_prices = tuple(
        _opening_price(item)
        for item in _objects(assumptions["opening_prices"], "opening prices")
    )
    opening_positions = tuple(
        _opening_position(item, by_source)
        for item in _objects(assumptions["opening_positions"], "opening positions")
    )

    _verify_references(
        businesses=businesses,
        roles=roles,
        commodities=commodities,
        sites=sites,
        inventories=inventories,
        labor_pools=labor_pools,
        recipes=recipes,
        routes=routes,
        demands=demands,
        opening_prices=opening_prices,
        opening_positions=opening_positions,
    )
    return RegionalScenario(
        scenario_id=REGIONAL_SCENARIO_ID,
        assumption_profile_id=REGIONAL_PROFILE_ID,
        payload_hash=_text(payload["content_hash"], "scenario content hash"),
        registry_content_hash=registry.content_hash,
        registry_snapshot_hash=registry.snapshot_hash,
        registry_export_hash=registry.export_hash,
        registry_source_schema_hash=registry.source_schema_hash,
        timeline=timeline,
        businesses=businesses,
        business_roles=roles,
        commodities=commodities,
        sites=sites,
        inventories=inventories,
        labor_pools=labor_pools,
        recipes=recipes,
        routes=routes,
        demands=demands,
        opening_prices=opening_prices,
        opening_positions=opening_positions,
        permissions=permissions,
        warning=warning,
    )


def _load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            parse_float=_reject_float,
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except RegionalScenarioError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RegionalScenarioError(f"cannot read regional scenario: {exc}") from exc
    if not isinstance(payload, dict):
        raise RegionalScenarioError("regional scenario must be a JSON object")
    return payload


def _verify_registry_binding(binding_value, registry, registry_path: Path) -> None:
    binding = _mapping(binding_value, "Registry binding")
    _exact_keys(
        binding,
        {
            "fixture_path",
            "row_count",
            "captured_at",
            "content_hash",
            "snapshot_hash",
            "export_hash",
            "source_schema_hash",
        },
        "Registry binding",
    )
    fixture_path = _text(binding["fixture_path"], "Registry fixture path")
    if PurePosixPath(fixture_path) != PurePosixPath(REGISTRY_FIXTURE_PATH):
        raise RegionalScenarioError("regional scenario points at the wrong Registry fixture")
    if registry_path.name != PurePosixPath(REGISTRY_FIXTURE_PATH).name:
        raise RegionalScenarioError("supplied Registry fixture filename is not source-bound")
    expected = {
        "row_count": registry.read_snapshot.expected_row_count,
        "captured_at": registry.read_snapshot.captured_at,
        "content_hash": registry.content_hash,
        "snapshot_hash": registry.snapshot_hash,
        "export_hash": registry.export_hash,
        "source_schema_hash": registry.source_schema_hash,
    }
    for key, actual in expected.items():
        if binding[key] != actual:
            raise RegionalScenarioError(
                f"Registry {key.replace('_', ' ')} has drifted; re-audit the scenario"
            )


def _selected_records(value) -> tuple[Mapping[str, object], ...]:
    records = _objects(value, "selected source records")
    if not records:
        raise RegionalScenarioError("regional scenario selects no Registry businesses")
    result: list[Mapping[str, object]] = []
    seen: set[str] = set()
    for item in records:
        _exact_keys(item, {"source_record_id", "row_hash"}, "selected source record")
        source_id = _text(item["source_record_id"], "selected source record ID")
        _require_source_id(source_id, "selected source record")
        row_hash = _text(item["row_hash"], "selected source row hash")
        _require_sha256(row_hash, "selected source row hash")
        if source_id in seen:
            raise RegionalScenarioError("selected source records contain a duplicate")
        seen.add(source_id)
        result.append(MappingProxyType({"source_record_id": source_id, "row_hash": row_hash}))
    return tuple(result)


def _source_business(registry, selected: Mapping[str, object]) -> SourceBusiness:
    source_id = str(selected["source_record_id"])
    expected_row_hash = str(selected["row_hash"])
    try:
        row = registry.row(source_id)
        actual_row_hash = registry.row_hashes[source_id]
    except (RegistryExportError, KeyError) as exc:
        raise RegionalScenarioError(
            f"selected Registry record {source_id} is missing"
        ) from exc
    if actual_row_hash != expected_row_hash:
        raise RegionalScenarioError(
            f"selected Registry row {source_id} has drifted; re-audit required"
        )
    name = _text(row.get("Entity"), "Registry Entity")
    employees_decimal = _source_decimal(row.get("Employees"), "Registry Employees")
    integral = employees_decimal.to_integral_value()
    if employees_decimal != integral:
        raise RegionalScenarioError("Registry Employees is not a whole-person count")
    return SourceBusiness(
        source_record_id=source_id,
        source_row_hash=actual_row_hash,
        source_ref=_text(row.get("url"), "Registry row URL"),
        entity_id=stable_entity_id(name),
        name=name,
        sector=_text(row.get("Sector"), "Registry Sector"),
        city=_text(row.get("City"), "Registry City"),
        status=_text(row.get("Status"), "Registry Status"),
        monthly_revenue_gp=_source_decimal(
            row.get("Monthly Revenue"), "Registry Monthly Revenue"
        ),
        monthly_cost_gp=_source_decimal(
            row.get("Monthly Cost"), "Registry Monthly Cost"
        ),
        employees=int(integral),
    )


def _timeline(value) -> ScenarioTimeline:
    item = _assumption(value, {"timeline_id", "month_index", "campaign_date_label"}, "timeline")
    timeline_id = _text(item["timeline_id"], "scenario timeline ID")
    if not timeline_id.startswith("preview:"):
        raise RegionalScenarioError("scenario timeline must remain in a preview lane")
    month_index = _integer(item["month_index"], "scenario month index", minimum=0)
    if month_index != 0:
        raise RegionalScenarioError("opening scenario must start at month index zero")
    return ScenarioTimeline(
        timeline_id,
        month_index,
        _text(item["campaign_date_label"], "scenario campaign-date label"),
        str(item["basis"]),
    )


def _business_role(value, by_source: Mapping[str, SourceBusiness]) -> BusinessRole:
    item = _assumption(value, {"source_record_id", "role"}, "business role")
    business = _business_ref(item["source_record_id"], by_source, "business role")
    return BusinessRole(
        business.source_record_id,
        business.entity_id,
        _text(item["role"], "business role"),
        str(item["basis"]),
    )


def _commodity(value) -> CommodityAssumption:
    item = _assumption(
        value,
        {"commodity_id", "name", "unit", "perishable_loss_rate"},
        "commodity",
    )
    commodity_id = _text(item["commodity_id"], "commodity ID")
    _require_id(commodity_id, "commodity")
    return CommodityAssumption(
        commodity_id,
        _text(item["name"], "commodity name"),
        _text(item["unit"], "commodity unit"),
        _decimal(item["perishable_loss_rate"], "commodity perishable loss rate", minimum=0, maximum=1, maximum_exclusive=True),
        str(item["basis"]),
    )


def _site(value, by_source: Mapping[str, SourceBusiness]) -> SiteAssumption:
    item = _assumption(value, {"site_id", "source_record_id"}, "site")
    business = _business_ref(item["source_record_id"], by_source, "site")
    site_id = _text(item["site_id"], "site ID")
    _require_id(site_id, "site")
    return SiteAssumption(
        site_id,
        business.source_record_id,
        business.entity_id,
        business.name,
        str(item["basis"]),
    )


def _inventory(value, by_source: Mapping[str, SourceBusiness]) -> InventoryAssumption:
    item = _assumption(
        value,
        {"inventory_id", "source_record_id", "site_id", "commodity_id", "quantity"},
        "inventory",
    )
    business = _business_ref(item["source_record_id"], by_source, "inventory")
    inventory_id = _text(item["inventory_id"], "inventory ID")
    _require_id(inventory_id, "inventory")
    return InventoryAssumption(
        inventory_id,
        business.source_record_id,
        business.entity_id,
        _text(item["site_id"], "inventory site"),
        _text(item["commodity_id"], "inventory commodity"),
        _decimal(item["quantity"], "inventory quantity", minimum=0),
        str(item["basis"]),
    )


def _labor_pool(value, by_source: Mapping[str, SourceBusiness]) -> LaborPoolAssumption:
    item = _assumption(
        value,
        {"labor_pool_id", "source_record_id", "site_id", "labor_class", "available_worker_days", "wage_gp_per_day"},
        "labor pool",
    )
    business = _business_ref(item["source_record_id"], by_source, "labor pool")
    pool_id = _text(item["labor_pool_id"], "labor-pool ID")
    _require_id(pool_id, "labor pool")
    return LaborPoolAssumption(
        pool_id,
        business.source_record_id,
        business.entity_id,
        _text(item["site_id"], "labor-pool site"),
        _text(item["labor_class"], "labor class"),
        business.employees,
        _decimal(item["available_worker_days"], "available worker-days", minimum=0),
        _decimal(item["wage_gp_per_day"], "daily wage", minimum=0),
        str(item["basis"]),
    )


def _recipe(value, by_source: Mapping[str, SourceBusiness]) -> RecipeAssumption:
    item = _assumption(
        value,
        {"recipe_id", "source_record_id", "site_id", "inputs", "outputs", "labor_class", "worker_days_per_batch", "max_batches_per_month", "priority"},
        "recipe",
    )
    business = _business_ref(item["source_record_id"], by_source, "recipe")
    recipe_id = _text(item["recipe_id"], "recipe ID")
    _require_id(recipe_id, "recipe")
    inputs = _material_amounts(item["inputs"], f"{recipe_id} inputs", allow_empty=True)
    outputs = _material_amounts(item["outputs"], f"{recipe_id} outputs", allow_empty=False)
    return RecipeAssumption(
        recipe_id,
        business.source_record_id,
        business.entity_id,
        _text(item["site_id"], "recipe site"),
        inputs,
        outputs,
        _text(item["labor_class"], "recipe labor class"),
        _decimal(item["worker_days_per_batch"], "recipe worker-days", minimum=0, minimum_exclusive=True),
        _decimal(item["max_batches_per_month"], "recipe monthly batch limit", minimum=0, minimum_exclusive=True),
        _integer(item["priority"], "recipe priority", minimum=0),
        str(item["basis"]),
    )


def _material_amounts(value, label: str, *, allow_empty: bool) -> tuple[MaterialAmount, ...]:
    items = _objects(value, label)
    if not items and not allow_empty:
        raise RegionalScenarioError(f"{label} must not be empty")
    result: list[MaterialAmount] = []
    seen: set[str] = set()
    for item in items:
        _exact_keys(item, {"commodity_id", "quantity_per_batch"}, label)
        commodity_id = _text(item["commodity_id"], f"{label} commodity")
        if commodity_id in seen:
            raise RegionalScenarioError(f"{label} repeats commodity {commodity_id}")
        seen.add(commodity_id)
        result.append(MaterialAmount(
            commodity_id,
            _decimal(item["quantity_per_batch"], f"{label} quantity", minimum=0, minimum_exclusive=True),
        ))
    return tuple(result)


def _route(value, by_source: Mapping[str, SourceBusiness]) -> RouteAssumption:
    item = _assumption(
        value,
        {"route_id", "source_record_id", "origin_site_id", "destination_site_id", "commodity_id", "capacity_per_month", "travel_periods", "loss_rate", "transport_cost_gp_per_dispatched_unit"},
        "route",
    )
    business = _business_ref(item["source_record_id"], by_source, "route")
    route_id = _text(item["route_id"], "route ID")
    _require_id(route_id, "route")
    return RouteAssumption(
        route_id,
        business.source_record_id,
        business.entity_id,
        _text(item["origin_site_id"], "route origin"),
        _text(item["destination_site_id"], "route destination"),
        _text(item["commodity_id"], "route commodity"),
        _decimal(item["capacity_per_month"], "route capacity", minimum=0, minimum_exclusive=True),
        _integer(item["travel_periods"], "route travel periods", minimum=0),
        _decimal(item["loss_rate"], "route loss rate", minimum=0, maximum=1, maximum_exclusive=True),
        _decimal(item["transport_cost_gp_per_dispatched_unit"], "route dispatched-unit cost", minimum=0),
        str(item["basis"]),
    )


def _demand(value, by_source: Mapping[str, SourceBusiness]) -> DemandAssumption:
    item = _assumption(
        value,
        {"demand_id", "source_record_id", "site_id", "commodity_id", "quantity", "reservation_price_gp_per_delivered_unit", "priority"},
        "demand",
    )
    business = _business_ref(item["source_record_id"], by_source, "demand")
    demand_id = _text(item["demand_id"], "demand ID")
    _require_id(demand_id, "demand")
    raw_price = item["reservation_price_gp_per_delivered_unit"]
    price = None if raw_price is None else _decimal(
        raw_price,
        "demand reservation price",
        minimum=0,
        minimum_exclusive=True,
    )
    return DemandAssumption(
        demand_id,
        business.source_record_id,
        business.entity_id,
        _text(item["site_id"], "demand site"),
        _text(item["commodity_id"], "demand commodity"),
        _decimal(item["quantity"], "demand quantity", minimum=0, minimum_exclusive=True),
        price,
        _integer(item["priority"], "demand priority", minimum=0),
        str(item["basis"]),
    )


def _opening_price(value) -> OpeningPriceAssumption:
    item = _assumption(
        value,
        {"price_id", "site_id", "commodity_id", "amount_gp_per_unit"},
        "opening price",
    )
    price_id = _text(item["price_id"], "opening-price ID")
    _require_id(price_id, "opening price")
    return OpeningPriceAssumption(
        price_id,
        _text(item["site_id"], "opening-price site"),
        _text(item["commodity_id"], "opening-price commodity"),
        _decimal(item["amount_gp_per_unit"], "opening price", minimum=0, minimum_exclusive=True),
        str(item["basis"]),
    )


def _opening_position(value, by_source: Mapping[str, SourceBusiness]) -> OpeningPositionAssumption:
    item = _assumption(
        value,
        {"source_record_id", "entity_type", "balances"},
        "opening financial position",
    )
    business = _business_ref(item["source_record_id"], by_source, "opening position")
    entity_type = _text(item["entity_type"], "opening-position entity type")
    if entity_type not in {"enterprise", "bank"}:
        raise RegionalScenarioError("opening-position entity type is unsupported")
    if (business.sector == "Banking") != (entity_type == "bank"):
        raise RegionalScenarioError("opening-position entity type contradicts Registry sector")
    balances_value = _mapping(item["balances"], "opening-position balances")
    if not balances_value:
        raise RegionalScenarioError("opening position has no balances")
    balances: list[tuple[str, Decimal]] = []
    for account, raw in sorted(balances_value.items()):
        _require_text(account, "opening-position account")
        balances.append((account, _decimal(raw, f"opening {account} balance", minimum=0)))
    return OpeningPositionAssumption(
        business.source_record_id,
        business.entity_id,
        entity_type,
        tuple(balances),
        str(item["basis"]),
    )


def _verify_references(
    *,
    businesses,
    roles,
    commodities,
    sites,
    inventories,
    labor_pools,
    recipes,
    routes,
    demands,
    opening_prices,
    opening_positions,
) -> None:
    source_ids = {item.source_record_id for item in businesses}
    entity_ids = {item.entity_id for item in businesses}
    if len(source_ids) != len(businesses) or len(entity_ids) != len(businesses):
        raise RegionalScenarioError("selected Registry businesses are not uniquely identified")
    required_sectors = {
        "Mining/Quarrying",
        "Manufacturing",
        "Agriculture",
        "Aquaculture",
        "Infrastructure",
        "Construction",
        "Trade",
        "Banking",
    }
    if {item.sector for item in businesses} != required_sectors:
        raise RegionalScenarioError("regional scenario no longer spans the locked sector slice")

    _unique((item.source_record_id for item in roles), "business role source")
    if {item.source_record_id for item in roles} != source_ids:
        raise RegionalScenarioError("every selected business requires exactly one scenario role")
    commodity_ids = _unique((item.commodity_id for item in commodities), "commodity")
    site_ids = _unique((item.site_id for item in sites), "site")
    if {item.source_record_id for item in sites} != source_ids:
        raise RegionalScenarioError("every selected business requires exactly one scenario site")
    site_owners = {item.site_id: item.owner_id for item in sites}

    _unique((item.inventory_id for item in inventories), "inventory")
    _unique(
        (f"{item.site_id}|{item.commodity_id}" for item in inventories),
        "inventory site/commodity",
    )
    for item in inventories:
        _reference(item.site_id, site_ids, "inventory site")
        _reference(item.commodity_id, commodity_ids, "inventory commodity")
        if site_owners[item.site_id] != item.owner_id:
            raise RegionalScenarioError("inventory owner does not own its scenario site")

    _unique((item.labor_pool_id for item in labor_pools), "labor pool")
    if {item.source_record_id for item in labor_pools} != source_ids:
        raise RegionalScenarioError("every selected business requires one labor pool")
    labor_keys: set[tuple[str, str]] = set()
    for item in labor_pools:
        _reference(item.site_id, site_ids, "labor-pool site")
        if site_owners[item.site_id] != item.owner_id:
            raise RegionalScenarioError("labor-pool owner does not own its scenario site")
        if item.available_worker_days > Decimal(item.workers * 20):
            raise RegionalScenarioError(
                "available worker-days exceed the profile's 20-day-per-worker assumption"
            )
        key = (item.site_id, item.labor_class)
        if key in labor_keys:
            raise RegionalScenarioError("labor pools repeat a site/labor class")
        labor_keys.add(key)

    _unique((item.recipe_id for item in recipes), "recipe")
    for item in recipes:
        _reference(item.site_id, site_ids, "recipe site")
        if site_owners[item.site_id] != item.operator_id:
            raise RegionalScenarioError("recipe operator does not own its scenario site")
        if (item.site_id, item.labor_class) not in labor_keys:
            raise RegionalScenarioError("recipe has no matching labor pool")
        for amount in (*item.inputs, *item.outputs):
            _reference(amount.commodity_id, commodity_ids, "recipe commodity")

    _unique((item.route_id for item in routes), "route")
    for item in routes:
        _reference(item.origin_site_id, site_ids, "route origin")
        _reference(item.destination_site_id, site_ids, "route destination")
        if item.origin_site_id == item.destination_site_id:
            raise RegionalScenarioError("route origin and destination must differ")
        _reference(item.commodity_id, commodity_ids, "route commodity")

    _unique((item.demand_id for item in demands), "demand")
    for item in demands:
        _reference(item.site_id, site_ids, "demand site")
        _reference(item.commodity_id, commodity_ids, "demand commodity")
        if site_owners[item.site_id] != item.buyer_id:
            raise RegionalScenarioError("demand buyer does not own its scenario site")

    _unique((item.price_id for item in opening_prices), "opening price")
    _unique(
        (f"{item.site_id}|{item.commodity_id}" for item in opening_prices),
        "opening-price site/commodity",
    )
    for item in opening_prices:
        _reference(item.site_id, site_ids, "opening-price site")
        _reference(item.commodity_id, commodity_ids, "opening-price commodity")

    _unique((item.source_record_id for item in opening_positions), "opening position source")
    if {item.source_record_id for item in opening_positions} != source_ids:
        raise RegionalScenarioError("every selected business requires an opening position")


def _assumption(value, data_keys: set[str], label: str) -> Mapping[str, object]:
    item = _mapping(value, label)
    _exact_keys(item, {*data_keys, "authority", "canonical", "basis"}, label)
    if item["authority"] != SCENARIO_AUTHORITY or item["canonical"] is not False:
        raise RegionalScenarioError(
            f"{label} must be labeled as a non-canonical scenario input"
        )
    _text(item["basis"], f"{label} basis")
    return item


def _business_ref(value, by_source: Mapping[str, SourceBusiness], label: str) -> SourceBusiness:
    source_id = _text(value, f"{label} source record")
    try:
        return by_source[source_id]
    except KeyError as exc:
        raise RegionalScenarioError(
            f"{label} references unselected Registry record {source_id}"
        ) from exc


def _permissions(value) -> Mapping[str, bool]:
    permissions = _mapping(value, "scenario permissions")
    expected = {
        "notion_write": False,
        "ledger_post": False,
        "campaign_advance": False,
        "canonical_state_update": False,
    }
    if permissions != expected:
        raise RegionalScenarioError("regional scenario permissions must remain fully read-only")
    return expected


def _mapping(value, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise RegionalScenarioError(f"{label} must be an object with string keys")
    return value


def _objects(value, label: str) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise RegionalScenarioError(f"{label} must be an array of objects")
    return tuple(value)


def _exact_keys(value: Mapping[str, object], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise RegionalScenarioError(f"{label} keys do not match the locked schema")


def _text(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise RegionalScenarioError(f"{label} must be non-empty exact text")
    return value


def _integer(value, label: str, *, minimum: int | None = None) -> int:
    if type(value) is not int:
        raise RegionalScenarioError(f"{label} must be an exact integer")
    if minimum is not None and value < minimum:
        raise RegionalScenarioError(f"{label} is below its allowed minimum")
    return value


def _source_decimal(value, label: str) -> Decimal:
    if not isinstance(value, str):
        raise RegionalScenarioError(f"{label} must be exact Registry decimal text")
    return _decimal(value, label, minimum=0)


def _decimal(
    value,
    label: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
    minimum_exclusive: bool = False,
    maximum_exclusive: bool = False,
) -> Decimal:
    if not isinstance(value, str):
        raise RegionalScenarioError(f"{label} must be exact decimal text")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise RegionalScenarioError(f"{label} is malformed") from exc
    if not result.is_finite() or str(result) != value:
        raise RegionalScenarioError(f"{label} is not canonical finite decimal text")
    if minimum is not None:
        bound = Decimal(minimum)
        if result < bound or (minimum_exclusive and result == bound):
            raise RegionalScenarioError(f"{label} is below its allowed minimum")
    if maximum is not None:
        bound = Decimal(maximum)
        if result > bound or (maximum_exclusive and result == bound):
            raise RegionalScenarioError(f"{label} is above its allowed maximum")
    return result


def _require_decimal(value, label: str, *, minimum: int | None = None) -> None:
    if type(value) is not Decimal or not value.is_finite():
        raise RegionalScenarioError(f"{label} must be a finite Decimal")
    if minimum is not None and value < Decimal(minimum):
        raise RegionalScenarioError(f"{label} is below its allowed minimum")


def _require_id(value: str, label: str) -> None:
    if not _ID_RE.fullmatch(value):
        raise RegionalScenarioError(f"{label} ID is not canonical")


def _require_source_id(value: str, label: str) -> None:
    if not _SOURCE_ID_RE.fullmatch(value):
        raise RegionalScenarioError(f"{label} ID is not a canonical Notion source ID")


def _require_sha256(value: str, label: str) -> None:
    if not _SHA256_RE.fullmatch(value):
        raise RegionalScenarioError(f"{label} must be a lowercase SHA-256 digest")


def _require_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise RegionalScenarioError(f"{label} must be non-empty text")


def _unique(values, label: str) -> set[str]:
    materialized = list(values)
    result = set(materialized)
    if len(result) != len(materialized):
        raise RegionalScenarioError(f"regional scenario repeats {label} IDs")
    return result


def _reference(value: str, available: set[str], label: str) -> None:
    if value not in available:
        raise RegionalScenarioError(f"{label} references unknown ID {value}")


def _assumption_ref(kind: str, item_id: str) -> str:
    return f"scenario:{REGIONAL_PROFILE_ID}:{kind}:{item_id}"


def _reject_float(value: str):
    raise RegionalScenarioError(
        f"regional scenario contains a binary/JSON decimal number: {value}; use exact text"
    )


def _reject_constant(value: str):
    raise RegionalScenarioError(f"regional scenario contains non-finite constant {value}")


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RegionalScenarioError(f"regional scenario repeats JSON key {key}")
        result[key] = value
    return result


__all__ = [
    "REGIONAL_PROFILE_ID",
    "REGIONAL_SCENARIO_ID",
    "REGIONAL_SCENARIO_SCHEMA",
    "RegionalScenario",
    "RegionalScenarioError",
    "SourceBusiness",
    "load_regional_scenario",
]
