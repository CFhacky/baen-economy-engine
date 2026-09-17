"""Concrete adapters for the source-bound regional economy vertical slice.

This module is the integration boundary used by :mod:`regional_cli`.  It joins
the audited scenario, deterministic GURPS checks, conserved production,
stock-flow market/transport, and balanced regional finance sidecar.  It has no
Notion client and no canonical-ledger writer.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from decimal import (
    Context,
    Decimal,
    InvalidOperation,
    ROUND_CEILING,
    ROUND_HALF_EVEN,
    localcontext,
)
from pathlib import Path
from typing import Mapping, Sequence

from .regional_cli import MonthRequest, RegionalAdapters, ScenarioRequest
from .regional_domain import (
    InventoryLot,
    LaborRequirement,
    MaterialRequirement,
    ProductionOrder,
    ProductionRecipe,
    RegionalState,
    regional_state_from_dict,
)
from .domain import canonical_decimal
from .regional_finance import simulate_regional_finance
from .regional_market import DemandBid, SupplyOffer, simulate_market_month
from .regional_production import advance_production_month
from .regional_rolls import (
    ExpenseRollInput,
    SectorRollInput,
    roll_regional_month,
)
from .regional_scenario import REGIONAL_SCENARIO_ID, load_regional_scenario
from .regional_transport import RouteCostTerms
from .stockflow import (
    Commodity,
    EconomyModel,
    InventoryPosition,
    PricePosition,
    Route,
    Site,
    initial_snapshot,
)


INTEGRATION_SCHEMA = "tnp.economy.regional-integration/1"
RULESET_VERSION = "baen-regional-market-preview-v1"
ZERO = Decimal(0)
ONE = Decimal(1)


class RegionalIntegrationError(ValueError):
    """Raised when persisted adapter inputs are incomplete or inconsistent."""


def _context() -> Context:
    return Context(
        prec=80,
        rounding=ROUND_HALF_EVEN,
        Emin=-999999,
        Emax=999999,
        capitals=1,
        clamp=0,
    )


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise RegionalIntegrationError(f"{label} must be an object")
    return value


def _objects(value: object, label: str) -> tuple[Mapping[str, object], ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise RegionalIntegrationError(f"{label} must be an array")
    result: list[Mapping[str, object]] = []
    for index, item in enumerate(value, start=1):
        result.append(_mapping(item, f"{label} item {index}"))
    return tuple(result)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise RegionalIntegrationError(f"{label} must be trimmed non-empty text")
    return value


def _decimal(value: object, label: str, *, allow_none: bool = False) -> Decimal | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise RegionalIntegrationError(f"{label} must use exact decimal text")
    try:
        result = value if type(value) is Decimal else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise RegionalIntegrationError(f"{label} must be a finite decimal") from exc
    if not result.is_finite():
        raise RegionalIntegrationError(f"{label} must be a finite decimal")
    return result


def _integer(value: object, label: str) -> int:
    if type(value) is not int:
        raise RegionalIntegrationError(f"{label} must be an integer")
    return value


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _preview_finance_assumptions(
    scenario: Mapping[str, object],
) -> dict[str, object]:
    positions = _objects(scenario.get("opening_positions"), "opening positions")
    bank_id = next(
        _text(item.get("entity_id"), "preview bank")
        for item in positions
        if item.get("entity_type") == "bank"
    )
    businesses = _objects(scenario.get("businesses"), "scenario businesses")
    depositor_id = next(
        _text(item.get("entity_id"), "preview depositor")
        for item in businesses
        if item.get("sector") == "Mining/Quarrying"
    )
    borrower_id = next(
        _text(item.get("entity_id"), "preview borrower")
        for item in businesses
        if item.get("sector") == "Manufacturing"
    )
    return {
        "authority": "integration_preview_assumption",
        "canonical": False,
        "basis": (
            "Invented one-month banking and treasury actions chosen to exercise "
            "balanced deposit, credit, interest, principal, payroll, and tax paths; "
            "they are not Registry facts or campaign rulings."
        ),
        "bank_id": bank_id,
        "depositor_id": depositor_id,
        "borrower_id": borrower_id,
        "treasury_id": "treasury:regional-preview",
        "deposit_fraction_of_realized_receipts": "0.25",
        "working_capital_fraction_of_operating_outflows": "0.50",
        "annual_interest_rate": "0.12",
        "principal_repayment_fraction_of_realized_receipts": "0.10",
        "trade_tax_rate": "0.05",
    }


class _ScenarioAdapter:
    def initialize(self, request: ScenarioRequest) -> Mapping[str, object]:
        with localcontext(_context()):
            return self._initialize(request)

    def _initialize(self, request: ScenarioRequest) -> Mapping[str, object]:
        if request.scenario_id != REGIONAL_SCENARIO_ID:
            raise RegionalIntegrationError(
                f"unsupported regional scenario: {request.scenario_id}"
            )
        root = _project_root()
        scenario_path = request.scenario_path or (
            root / "fixtures" / "regional-scenarios" / "baen-north-preview-v1.json"
        )
        registry_path = request.registry_path or (
            root
            / "fixtures"
            / "registry-snapshots"
            / "business-registry-2026-08-29.json"
        )
        scenario = load_regional_scenario(scenario_path, registry_path)
        normalized = scenario.to_dict()
        state = {
            "schema": INTEGRATION_SCHEMA,
            "period": 0,
            "regional_state": scenario.opening_state().to_dict(),
            "finance_basis": "explicit_noncanonical_opening_positions",
            "finance_assumptions": _preview_finance_assumptions(normalized),
            "notion_writes": 0,
            "canonical_ledger_postings": 0,
        }
        return {"scenario": normalized, "state": state}


def _regional_state(request: MonthRequest, production: Mapping[str, object] | None = None) -> RegionalState:
    if production is not None:
        state = _mapping(production.get("state"), "production state")
        return regional_state_from_dict(
            _mapping(state.get("regional_state"), "production regional state")
        )
    opening = request.opening_state
    if request.period > 1:
        market_state = opening.get("market_transport")
        if isinstance(market_state, Mapping) and isinstance(
            market_state.get("regional_state"), Mapping
        ):
            return regional_state_from_dict(market_state["regional_state"])
        production_state = opening.get("production")
        if isinstance(production_state, Mapping) and isinstance(
            production_state.get("regional_state"), Mapping
        ):
            return regional_state_from_dict(production_state["regional_state"])
    return regional_state_from_dict(
        _mapping(opening.get("regional_state"), "opening regional state")
    )


def _recipes(scenario: Mapping[str, object]) -> tuple[ProductionRecipe, ...]:
    recipes: list[ProductionRecipe] = []
    for item in _objects(scenario.get("recipes"), "scenario recipes"):
        inputs = tuple(
            MaterialRequirement(
                _text(line.get("commodity_id"), "recipe input commodity"),
                _decimal(line.get("quantity_per_batch"), "recipe input quantity"),
            )
            for line in _objects(item.get("inputs"), "recipe inputs")
        )
        outputs = tuple(
            MaterialRequirement(
                _text(line.get("commodity_id"), "recipe output commodity"),
                _decimal(line.get("quantity_per_batch"), "recipe output quantity"),
            )
            for line in _objects(item.get("outputs"), "recipe outputs")
        )
        recipes.append(
            ProductionRecipe(
                recipe_id=_text(item.get("recipe_id"), "recipe ID"),
                operator_id=_text(item.get("operator_id"), "recipe operator"),
                site_id=_text(item.get("site_id"), "recipe site"),
                inputs=inputs,
                outputs=outputs,
                labor_requirements=(
                    LaborRequirement(
                        _text(item.get("labor_class"), "recipe labor class"),
                        _decimal(
                            item.get("worker_days_per_batch"),
                            "recipe worker-days",
                        ),
                    ),
                ),
                max_batches_per_month=_decimal(
                    item.get("max_batches_per_month"), "recipe maximum batches"
                ),
                source_ref=f"scenario:recipe:{_text(item.get('recipe_id'), 'recipe ID')}",
                priority=_integer(item.get("priority"), "recipe priority"),
            )
        )
    return tuple(recipes)


class _ProductionAdapter:
    def simulate(self, request: MonthRequest) -> Mapping[str, object]:
        with localcontext(_context()):
            return self._simulate(request)

    def _simulate(self, request: MonthRequest) -> Mapping[str, object]:
        state = _regional_state(request)
        businesses = _objects(request.scenario.get("businesses"), "scenario businesses")
        sector_counts = Counter(
            _text(item.get("sector"), "business sector") for item in businesses
        )
        rolls = roll_regional_month(
            state_hash=state.state_hash,
            period_index=request.period,
            seed=request.seed_fingerprint,
            sectors=tuple(
                SectorRollInput(sector=sector, revenue_streams=count)
                for sector, count in sorted(sector_counts.items())
            ),
            entities=tuple(
                ExpenseRollInput(
                    entity_id=_text(item.get("entity_id"), "business entity"),
                    employees=_integer(item.get("source_employees"), "business employees"),
                )
                for item in businesses
            ),
            market="stable",
            vara_active=True,
        )
        factor_by_sector = {
            _text(item.get("sector"), "roll sector"): _decimal(
                item.get("revenue_factor"), "roll revenue factor"
            )
            for item in _objects(rolls.get("sector_rolls"), "sector rolls")
        }
        sector_by_entity = {
            _text(item.get("entity_id"), "business entity"): _text(
                item.get("sector"), "business sector"
            )
            for item in businesses
        }
        recipes = _recipes(request.scenario)
        orders: list[ProductionOrder] = []
        with localcontext(_context()):
            for recipe in recipes:
                factor = factor_by_sector[sector_by_entity[recipe.operator_id]]
                requested = min(
                    recipe.max_batches_per_month,
                    recipe.max_batches_per_month * Decimal("0.80") * factor,
                )
                orders.append(ProductionOrder(recipe.recipe_id, requested))
        month = advance_production_month(state, recipes, tuple(orders))
        payload = month.to_dict()
        production_view = {
            "runs": payload["production"]["runs"],
            "active_businesses": sum(
                1
                for item in payload["production"]["runs"]
                if _decimal(item.get("output_produced"), "produced quantity") > ZERO
            ),
            "unit_policy": (
                "inputs and outputs are reported only on unit-specific business receipts; "
                "unlike commodities are never summed"
            ),
        }
        return {
            "production": production_view,
            "labor": payload["labor"],
            "state": {
                "schema": INTEGRATION_SCHEMA,
                "regional_state": payload["next_state"],
                "opening_state_hash": payload["opening_state_hash"],
                "closing_state_hash": payload["closing_state_hash"],
                "rolls": rolls,
                "payroll_events": payload["payroll_events"],
                "conservation": payload["conservation"],
                "notion_writes": 0,
                "canonical_ledger_postings": 0,
            },
            "payroll_events": payload["payroll_events"],
            "conservation": payload["conservation"],
            "rolls": rolls,
        }


def _market_model(
    scenario: Mapping[str, object], state: RegionalState
) -> tuple[EconomyModel, tuple[PricePosition, ...]]:
    prices = _objects(scenario.get("opening_prices"), "opening prices")
    base_by_commodity: dict[str, Decimal] = {}
    for item in prices:
        commodity_id = _text(item.get("commodity_id"), "price commodity")
        amount = _decimal(item.get("amount_gp_per_unit"), "opening price")
        # A commodity-level value is required only as a fallback by the kernel.
        # Price response uses the explicit site PricePosition below, so do not
        # invent a regional maximum as every site's baseline.
        base_by_commodity.setdefault(commodity_id, amount)
    commodities = tuple(
        Commodity(
            commodity_id=item.commodity_id,
            name=item.name,
            unit=item.unit,
            base_price=base_by_commodity[item.commodity_id],
        )
        for item in state.commodities
    )
    sites = tuple(
        Site(
            site_id=_text(item.get("site_id"), "site ID"),
            name=_text(item.get("name"), "site name"),
            labor_capacity=ZERO,
        )
        for item in _objects(scenario.get("sites"), "scenario sites")
    )
    # Zero-period fixture links describe intra-city handling, not stockflow
    # transit.  They remain in the persisted scenario but are not silently
    # rewritten into one-period routes here.
    routes = tuple(
        Route(
            route_id=_text(item.get("route_id"), "route ID"),
            origin_site_id=_text(item.get("origin_site_id"), "route origin"),
            destination_site_id=_text(
                item.get("destination_site_id"), "route destination"
            ),
            commodity_id=_text(item.get("commodity_id"), "route commodity"),
            capacity_per_period=_decimal(
                item.get("capacity_per_month"), "route capacity"
            ),
            travel_periods=_integer(item.get("travel_periods"), "route travel time"),
            loss_rate=_decimal(item.get("loss_rate"), "route loss rate"),
        )
        for item in _objects(scenario.get("routes"), "scenario routes")
        if _integer(item.get("travel_periods"), "route travel time") >= 1
    )
    model = EconomyModel(commodities, sites, (), routes)
    price_positions = tuple(
        PricePosition(
            _text(item.get("site_id"), "price site"),
            _text(item.get("commodity_id"), "price commodity"),
            _decimal(item.get("amount_gp_per_unit"), "opening price"),
        )
        for item in prices
    )
    return model, price_positions


def _inventory_positions(state: RegionalState) -> tuple[InventoryPosition, ...]:
    aggregated: defaultdict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for lot in state.inventories:
        if lot.quantity is None:
            raise RegionalIntegrationError(
                f"market inventory is unresolved: {lot.site_id}/{lot.commodity_id}"
            )
        aggregated[(lot.site_id, lot.commodity_id)] += lot.quantity
    return tuple(
        InventoryPosition(site_id, commodity_id, quantity)
        for (site_id, commodity_id), quantity in sorted(aggregated.items())
        if quantity != ZERO
    )


def _supply_offers(state: RegionalState) -> tuple[SupplyOffer, ...]:
    offers: list[SupplyOffer] = []
    for index, lot in enumerate(sorted(state.inventories), start=1):
        if lot.quantity is None or lot.quantity <= ZERO:
            continue
        offers.append(
            SupplyOffer(
                offer_id=f"offer:{index:04d}:{lot.owner_id}:{lot.commodity_id}",
                seller_entity_id=lot.owner_id,
                site_id=lot.site_id,
                commodity_id=lot.commodity_id,
                offered_quantity=lot.quantity,
                source_ref=lot.source_ref,
            )
        )
    return tuple(offers)


def _demand_bids(scenario: Mapping[str, object]) -> tuple[DemandBid, ...]:
    return tuple(
        DemandBid(
            demand_id=_text(item.get("demand_id"), "demand ID"),
            buyer_entity_id=_text(item.get("buyer_id"), "demand buyer"),
            site_id=_text(item.get("site_id"), "demand site"),
            commodity_id=_text(item.get("commodity_id"), "demand commodity"),
            quantity=_decimal(item.get("quantity"), "demand quantity"),
            source_ref=f"scenario:demand:{_text(item.get('demand_id'), 'demand ID')}",
            reservation_price_gp_per_delivered_unit=_decimal(
                item.get("reservation_price_gp_per_delivered_unit"),
                "demand reservation price",
                allow_none=True,
            ),
            priority=_integer(item.get("priority"), "demand priority"),
        )
        for item in _objects(scenario.get("demands"), "scenario demands")
    )


def _route_costs(scenario: Mapping[str, object]) -> tuple[RouteCostTerms, ...]:
    return tuple(
        RouteCostTerms(
            route_id=_text(item.get("route_id"), "route ID"),
            transport_cost_gp_per_dispatched_unit=_decimal(
                item.get("transport_cost_gp_per_dispatched_unit"),
                "route transport cost",
            ),
            carrier_entity_id=_text(
                item.get("operator_id"), "route operator"
            ),
        )
        for item in _objects(scenario.get("routes"), "scenario routes")
        if _integer(item.get("travel_periods"), "route travel time") >= 1
    )


def _apply_storage_losses(
    state: RegionalState,
) -> tuple[RegionalState, list[dict[str, object]]]:
    rates = {
        item.commodity_id: item.perishable_loss_rate for item in state.commodities
    }
    lots: list[InventoryLot] = []
    receipts: list[dict[str, object]] = []
    with localcontext(_context()):
        for item in state.inventories:
            rate = rates[item.commodity_id]
            if item.quantity is None:
                if rate > ZERO:
                    raise RegionalIntegrationError(
                        f"perishable inventory is unresolved: {item.site_id}/{item.commodity_id}"
                    )
                lots.append(item)
                continue
            loss = item.quantity * rate
            closing = item.quantity - loss
            lots.append(
                InventoryLot(
                    owner_id=item.owner_id,
                    site_id=item.site_id,
                    commodity_id=item.commodity_id,
                    quantity=closing,
                    source_ref=item.source_ref,
                )
            )
            if rate > ZERO and item.quantity > ZERO:
                receipts.append(
                    {
                        "owner_id": item.owner_id,
                        "site_id": item.site_id,
                        "commodity_id": item.commodity_id,
                        "opening_quantity": canonical_decimal(item.quantity),
                        "storage_loss_rate": canonical_decimal(rate),
                        "storage_loss_quantity": canonical_decimal(loss),
                        "closing_before_trade_quantity": canonical_decimal(closing),
                        "residual_quantity": "0",
                        "authority": "scenario_input",
                        "canonical": False,
                    }
                )
    return (
        RegionalState(
            month_index=state.month_index,
            commodities=state.commodities,
            inventories=tuple(sorted(lots)),
            labor_pools=state.labor_pools,
        ),
        receipts,
    )


def _instant_route_transfers(
    scenario: Mapping[str, object],
    state: RegionalState,
    *,
    period: int,
) -> tuple[RegionalState, list[dict[str, object]], list[dict[str, object]]]:
    """Resolve explicit zero-period handling links before the market close.

    The stock-flow kernel correctly forbids zero-period transit.  The fixture's
    zero-period links are instead same-month, same-region handling contracts:
    stock leaves the origin immediately, route loss is recognized immediately,
    and delivered stock is available to the destination's market demand.
    """

    sites = {
        _text(item.get("site_id"), "site ID"): _text(
            item.get("owner_id"), "site owner"
        )
        for item in _objects(scenario.get("sites"), "scenario sites")
    }
    prices = {
        (
            _text(item.get("site_id"), "price site"),
            _text(item.get("commodity_id"), "price commodity"),
        ): _decimal(item.get("amount_gp_per_unit"), "opening price")
        for item in _objects(scenario.get("opening_prices"), "opening prices")
    }
    demands: defaultdict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for item in _objects(scenario.get("demands"), "scenario demands"):
        demands[
            (
                _text(item.get("site_id"), "demand site"),
                _text(item.get("commodity_id"), "demand commodity"),
            )
        ] += _decimal(item.get("quantity"), "demand quantity")

    lots = {item.key: item for item in state.inventories}
    by_site_commodity: dict[tuple[str, str], tuple[str, str, str]] = {}
    for item in state.inventories:
        key = (item.site_id, item.commodity_id)
        if key in by_site_commodity:
            raise RegionalIntegrationError(
                "same-month transfer requires one preview owner per site/commodity"
            )
        by_site_commodity[key] = item.key
    quantities: dict[tuple[str, str, str], Decimal | None] = {
        key: item.quantity for key, item in lots.items()
    }
    route_receipts: list[dict[str, object]] = []
    trade_receipts: list[dict[str, object]] = []
    instant_routes = tuple(
        item
        for item in _objects(scenario.get("routes"), "scenario routes")
        if _integer(item.get("travel_periods"), "route travel time") == 0
    )
    with localcontext(_context()):
        for route in sorted(
            instant_routes,
            key=lambda item: _text(item.get("route_id"), "route ID"),
        ):
            route_id = _text(route.get("route_id"), "route ID")
            origin = _text(route.get("origin_site_id"), "route origin")
            destination = _text(
                route.get("destination_site_id"), "route destination"
            )
            commodity = _text(route.get("commodity_id"), "route commodity")
            origin_key = by_site_commodity.get((origin, commodity))
            if origin_key is None:
                raise RegionalIntegrationError(
                    f"zero-period route {route_id} has no origin inventory"
                )
            available = quantities[origin_key]
            if available is None:
                raise RegionalIntegrationError(
                    f"zero-period route {route_id} has unresolved origin stock"
                )
            destination_key = by_site_commodity.get((destination, commodity))
            destination_quantity = (
                quantities[destination_key]
                if destination_key is not None
                else ZERO
            )
            if destination_quantity is None:
                raise RegionalIntegrationError(
                    f"zero-period route {route_id} has unresolved destination stock"
                )
            capacity = _decimal(route.get("capacity_per_month"), "route capacity")
            demanded = demands.get((destination, commodity))
            loss_rate = _decimal(route.get("loss_rate"), "route loss rate")
            if demanded is not None:
                delivery_shortfall = max(ZERO, demanded - destination_quantity)
                requested = (delivery_shortfall / (ONE - loss_rate)).quantize(
                    Decimal("0.000001"), rounding=ROUND_CEILING
                )
            else:
                requested = capacity
            moved = min(available, capacity, requested)
            if moved <= ZERO:
                continue
            loss = moved * loss_rate
            delivered = moved - loss
            quantities[origin_key] = available - moved
            if destination_key is None:
                owner = sites[destination]
                destination_key = (owner, destination, commodity)
                by_site_commodity[(destination, commodity)] = destination_key
                quantities[destination_key] = delivered
            else:
                quantities[destination_key] = destination_quantity + delivered

            unit_price = prices[(origin, commodity)]
            unit_cost = _decimal(
                route.get("transport_cost_gp_per_dispatched_unit"),
                "route transport cost",
            )
            goods_value = moved * unit_price
            transport_cost = moved * unit_cost
            buyer_total = goods_value + transport_cost
            seller_id = origin_key[0]
            buyer_id = destination_key[0]
            carrier_id = _text(route.get("operator_id"), "route operator")
            route_receipts.append(
                {
                    "route_id": route_id,
                    "commodity_id": commodity,
                    "origin_site_id": origin,
                    "destination_site_id": destination,
                    "carrier_entity_id": carrier_id,
                    "quantity_moved": canonical_decimal(moved),
                    "capacity": canonical_decimal(capacity),
                    "remaining_capacity": canonical_decimal(capacity - moved),
                    "expected_loss_quantity": canonical_decimal(loss),
                    "expected_delivered_quantity": canonical_decimal(delivered),
                    "transport_cost_gp_per_dispatched_unit": canonical_decimal(
                        unit_cost
                    ),
                    "transport_cost_gp": canonical_decimal(transport_cost),
                    "arrival_period_index": period,
                    "movement_kind": "same_month_handling",
                }
            )
            trade_receipts.append(
                {
                    "trade_id": f"trade:handling:{period:08d}:{route_id}",
                    "demand_id": (
                        next(
                            (
                                _text(item.get("demand_id"), "demand ID")
                                for item in _objects(
                                    scenario.get("demands"), "scenario demands"
                                )
                                if item.get("site_id") == destination
                                and item.get("commodity_id") == commodity
                            ),
                            None,
                        )
                    ),
                    "supply_offer_id": f"offer:handling:{route_id}",
                    "seller_entity_id": seller_id,
                    "buyer_entity_id": buyer_id,
                    "carrier_entity_id": carrier_id,
                    "seller_site_id": origin,
                    "buyer_site_id": destination,
                    "commodity_id": commodity,
                    "route_id": route_id,
                    "dispatched_quantity": canonical_decimal(moved),
                    "expected_loss_quantity": canonical_decimal(loss),
                    "delivered_quantity": canonical_decimal(delivered),
                    "goods_unit_price_gp": canonical_decimal(unit_price),
                    "goods_value_gp": canonical_decimal(goods_value),
                    "transport_unit_cost_gp": canonical_decimal(unit_cost),
                    "transport_cost_gp": canonical_decimal(transport_cost),
                    "buyer_total_gp": canonical_decimal(buyer_total),
                    "departure_period_index": period,
                    "arrival_period_index": period,
                    "delivery_status": "delivered",
                    "settlement_status": "settled_cash",
                    "authority": "scenario_input",
                    "canonical": False,
                }
            )

    next_lots: list[InventoryLot] = []
    original_keys = set(lots)
    for key, item in sorted(lots.items()):
        next_lots.append(
            InventoryLot(
                owner_id=item.owner_id,
                site_id=item.site_id,
                commodity_id=item.commodity_id,
                quantity=quantities[key],
                source_ref=item.source_ref,
            )
        )
    for key in sorted(set(quantities) - original_keys):
        owner_id, site_id, commodity_id = key
        next_lots.append(
            InventoryLot(
                owner_id=owner_id,
                site_id=site_id,
                commodity_id=commodity_id,
                quantity=quantities[key],
                source_ref="engine:same-month-handling",
            )
        )
    transferred = RegionalState(
        month_index=state.month_index,
        commodities=state.commodities,
        inventories=tuple(sorted(next_lots)),
        labor_pools=state.labor_pools,
    )
    return transferred, route_receipts, trade_receipts


def _regional_after_market(
    prior: RegionalState,
    market_state: Mapping[str, object],
    scenario: Mapping[str, object],
) -> RegionalState:
    quantities = {
        (
            _text(item.get("site_id"), "market-state site"),
            _text(item.get("commodity_id"), "market-state commodity"),
        ): _decimal(item.get("quantity"), "market-state quantity")
        for item in _objects(market_state.get("inventories"), "market-state inventories")
    }
    site_owner = {
        _text(item.get("site_id"), "site ID"): _text(item.get("owner_id"), "site owner")
        for item in _objects(scenario.get("sites"), "scenario sites")
    }
    lots: list[InventoryLot] = []
    known_keys: set[tuple[str, str]] = set()
    for original in prior.inventories:
        key = (original.site_id, original.commodity_id)
        if key in known_keys:
            raise RegionalIntegrationError(
                "market adapter requires one preview owner per site/commodity"
            )
        known_keys.add(key)
        lots.append(
            InventoryLot(
                owner_id=original.owner_id,
                site_id=original.site_id,
                commodity_id=original.commodity_id,
                quantity=quantities.get(key, ZERO),
                source_ref=original.source_ref,
            )
        )
    for (site_id, commodity_id), quantity in sorted(quantities.items()):
        if (site_id, commodity_id) in known_keys:
            continue
        lots.append(
            InventoryLot(
                owner_id=site_owner[site_id],
                site_id=site_id,
                commodity_id=commodity_id,
                quantity=quantity,
                source_ref="engine:regional-market-arrival",
            )
        )
    return RegionalState(
        month_index=prior.month_index,
        commodities=prior.commodities,
        inventories=tuple(sorted(lots)),
        labor_pools=prior.labor_pools,
    )


class _MarketTransportAdapter:
    def simulate(
        self,
        request: MonthRequest,
        production: Mapping[str, object],
    ) -> Mapping[str, object]:
        with localcontext(_context()):
            return self._simulate(request, production)

    def _simulate(
        self,
        request: MonthRequest,
        production: Mapping[str, object],
    ) -> Mapping[str, object]:
        if request.period != 1:
            raise RegionalIntegrationError(
                "the current vertical slice resolves one source-bound regional month"
            )
        production_state = _regional_state(request, production)
        stored_state, storage_losses = _apply_storage_losses(production_state)
        state, handling_usage, handling_trades = _instant_route_transfers(
            request.scenario,
            stored_state,
            period=request.period,
        )
        model, prices = _market_model(request.scenario, state)
        timeline = _mapping(request.scenario.get("timeline"), "scenario timeline")
        date_label = (
            f"{_text(timeline.get('campaign_date_label'), 'campaign date label')} / "
            f"preview month {request.period}"
        )
        opening = initial_snapshot(
            model,
            timeline_id=_text(timeline.get("timeline_id"), "timeline ID"),
            campaign_ordinal=0,
            campaign_date=_text(
                timeline.get("campaign_date_label"), "campaign date label"
            ),
            ruleset_version=RULESET_VERSION,
            inventories=_inventory_positions(state),
            prices=prices,
        )
        result = simulate_market_month(
            model,
            opening,
            period_index=1,
            campaign_ordinal=1,
            campaign_date=date_label,
            supply_offers=_supply_offers(state),
            demands=_demand_bids(request.scenario),
            route_costs=_route_costs(request.scenario),
            source_ref=f"scenario:{request.scenario.get('normalized_hash', 'unhashed')}",
        )
        payload = result.to_payload()
        route_usage = [*handling_usage, *payload["route_usage"]]
        trade_receipts = [*handling_trades, *payload["trade_receipts"]]
        transport = {
            "active_routes": len(route_usage),
            "route_usage": route_usage,
            "unit_policy": (
                "movement and capacity remain route- and commodity-specific; "
                "unlike units are never summed"
            ),
        }
        next_market_state = _mapping(
            payload.get("next_market_state"), "next market state"
        )
        regional = _regional_after_market(state, next_market_state, request.scenario)
        market_view = dict(payload["market"])
        market_view["storage_loss_receipts"] = storage_losses
        return {
            "transport": transport,
            "market": market_view,
            "state": {
                "schema": INTEGRATION_SCHEMA,
                "regional_state": regional.to_dict(),
                "market_snapshot": dict(next_market_state),
                "trade_receipts": trade_receipts,
                "storage_loss_receipts": storage_losses,
                "zero_period_fixture_routes": [
                    _text(item.get("route_id"), "route ID")
                    for item in _objects(request.scenario.get("routes"), "scenario routes")
                    if _integer(item.get("travel_periods"), "route travel time") == 0
                ],
                "zero_period_route_treatment": "same-month handled, lost, delivered, and settled",
                "notion_writes": 0,
                "canonical_ledger_postings": 0,
            },
            "trade_receipts": trade_receipts,
        }


def _opening_positions(scenario: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "entity_id": _text(item.get("entity_id"), "opening entity"),
            "entity_type": _text(item.get("entity_type"), "opening entity type"),
            "balances": dict(_mapping(item.get("balances"), "opening balances")),
        }
        for item in _objects(scenario.get("opening_positions"), "opening positions")
    )


class _FinanceAdapter:
    def simulate(
        self,
        request: MonthRequest,
        production: Mapping[str, object],
        market_transport: Mapping[str, object],
    ) -> Mapping[str, object]:
        with localcontext(_context()):
            return self._simulate(request, production, market_transport)

    def _simulate(
        self,
        request: MonthRequest,
        production: Mapping[str, object],
        market_transport: Mapping[str, object],
    ) -> Mapping[str, object]:
        if request.period != 1:
            raise RegionalIntegrationError(
                "the current vertical slice resolves one source-bound regional month"
            )
        positions = _opening_positions(request.scenario)
        assumptions = _mapping(
            request.opening_state.get("finance_assumptions"),
            "finance assumptions",
        )
        if (
            assumptions.get("authority") != "integration_preview_assumption"
            or assumptions.get("canonical") is not False
        ):
            raise RegionalIntegrationError(
                "regional finance actions require explicit non-canonical assumptions"
            )
        bank_id = _text(assumptions.get("bank_id"), "finance-assumption bank")
        depositor_id = _text(
            assumptions.get("depositor_id"), "finance-assumption depositor"
        )
        borrower_id = _text(
            assumptions.get("borrower_id"), "finance-assumption borrower"
        )
        production_state = _mapping(production.get("state"), "production state")
        payroll_events = [
            dict(item)
            for item in _objects(
                production_state.get("payroll_events"), "production payroll events"
            )
        ]
        events: list[dict[str, object]] = list(payroll_events)
        payroll_by_entity: defaultdict[str, Decimal] = defaultdict(Decimal)
        for item in payroll_events:
            payroll_by_entity[_text(item.get("entity_id"), "payroll entity")] += _decimal(
                item.get("amount"), "payroll amount"
            )
        market_state = _mapping(market_transport.get("state"), "market state")
        realized_receipts: defaultdict[str, Decimal] = defaultdict(Decimal)
        operating_outflows: defaultdict[str, Decimal] = defaultdict(Decimal)
        realized_trades: list[Mapping[str, object]] = []
        for item in _objects(market_state.get("trade_receipts"), "trade receipts"):
            if (
                item.get("delivery_status") == "delivered"
                and item.get("settlement_status") == "settled_cash"
                and item.get("seller_entity_id") != item.get("buyer_entity_id")
            ):
                seller_id = _text(item.get("seller_entity_id"), "trade seller")
                buyer_id = _text(item.get("buyer_entity_id"), "trade buyer")
                carrier_id = _text(item.get("carrier_entity_id"), "trade carrier")
                goods_amount = _decimal(item.get("goods_value_gp"), "trade goods value")
                transport_amount = _decimal(
                    item.get("transport_cost_gp"), "trade transport cost"
                )
                buyer_total = _decimal(item.get("buyer_total_gp"), "trade value")
                if goods_amount + transport_amount != buyer_total:
                    raise RegionalIntegrationError(
                        "delivered trade goods and carriage do not reconcile"
                    )
                events.append(
                    {
                        "event_id": f"finance:{_text(item.get('trade_id'), 'trade ID')}",
                        "kind": "enterprise_trade",
                        "seller_id": seller_id,
                        "buyer_id": buyer_id,
                        "carrier_id": carrier_id,
                        "amount": canonical_decimal(buyer_total),
                        "goods_amount": canonical_decimal(goods_amount),
                        "transport_amount": canonical_decimal(transport_amount),
                        "treatment": (
                            "expense" if item.get("demand_id") is not None else "inventory"
                        ),
                    }
                )
                realized_receipts[seller_id] += goods_amount
                realized_receipts[carrier_id] += transport_amount
                operating_outflows[buyer_id] += buyer_total
                realized_trades.append(item)
        if not realized_trades:
            raise RegionalIntegrationError(
                "regional close requires at least one delivered inter-business trade"
            )
        with localcontext(_context()):
            deposit_amount = (
                realized_receipts[depositor_id]
                * _decimal(
                    assumptions.get("deposit_fraction_of_realized_receipts"),
                    "deposit fraction",
                )
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
            loan_amount = (
                (
                    operating_outflows[borrower_id]
                    + payroll_by_entity[borrower_id]
                )
                * _decimal(
                    assumptions.get(
                        "working_capital_fraction_of_operating_outflows"
                    ),
                    "working-capital fraction",
                )
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
            principal_repayment = min(
                loan_amount,
                (
                    realized_receipts[borrower_id]
                    * _decimal(
                        assumptions.get(
                            "principal_repayment_fraction_of_realized_receipts"
                        ),
                        "principal-repayment fraction",
                    )
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN),
            )
            tax_amount = (
                realized_receipts[depositor_id]
                * _decimal(assumptions.get("trade_tax_rate"), "trade tax rate")
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
        for value, label in (
            (deposit_amount, "deposit"),
            (loan_amount, "working-capital loan"),
            (principal_repayment, "principal repayment"),
            (tax_amount, "trade tax"),
        ):
            if value <= ZERO:
                raise RegionalIntegrationError(
                    f"realized operations produced no positive {label} amount"
                )
        loan_id = f"loan:regional-preview:{request.period:04d}"
        treasury_id = _text(
            assumptions.get("treasury_id"), "finance-assumption treasury"
        )
        events.extend(
            (
                {
                    "event_id": f"deposit:regional-preview:{request.period:04d}",
                    "kind": "bank_deposit",
                    "bank_id": bank_id,
                    "depositor_id": depositor_id,
                    "amount": canonical_decimal(deposit_amount),
                },
                {
                    "event_id": f"loan-origination:regional-preview:{request.period:04d}",
                    "kind": "loan_origination",
                    "loan_id": loan_id,
                    "bank_id": bank_id,
                    "borrower_id": borrower_id,
                    "amount": canonical_decimal(loan_amount),
                    "annual_interest_rate": _text(
                        assumptions.get("annual_interest_rate"),
                        "interest-rate assumption",
                    ),
                },
                {
                    "event_id": f"loan-interest:regional-preview:{request.period:04d}",
                    "kind": "loan_interest_accrual",
                    "loan_id": loan_id,
                },
                {
                    "event_id": f"loan-principal:regional-preview:{request.period:04d}",
                    "kind": "loan_principal_repayment",
                    "loan_id": loan_id,
                    "amount": canonical_decimal(principal_repayment),
                },
                {
                    "event_id": f"tax-assessment:regional-preview:{request.period:04d}",
                    "kind": "treasury_tax_assessment",
                    "treasury_id": treasury_id,
                    "taxpayer_id": depositor_id,
                    "amount": canonical_decimal(tax_amount),
                },
                {
                    "event_id": f"tax-receipt:regional-preview:{request.period:04d}",
                    "kind": "treasury_tax_receipt",
                    "treasury_id": treasury_id,
                    "taxpayer_id": depositor_id,
                    "amount": canonical_decimal(tax_amount),
                },
            )
        )
        finance = simulate_regional_finance(
            period=f"preview-month-{request.period}",
            opening_positions=positions,
            events=events,
        )
        return {
            "banking": finance["banking"],
            "treasury": finance["treasury"],
            "journal": finance["journal"],
            "state": {
                "schema": INTEGRATION_SCHEMA,
                "finance_state": finance["state"],
                "transactions": finance["transactions"],
                "reports": finance["reports"],
                "safety": finance["safety"],
                "assumption_receipt": dict(assumptions),
                "realized_action_amounts": {
                    "delivered_trade_count": len(realized_trades),
                    "deposit_gp": canonical_decimal(deposit_amount),
                    "working_capital_loan_gp": canonical_decimal(loan_amount),
                    "principal_repayment_gp": canonical_decimal(principal_repayment),
                    "trade_tax_gp": canonical_decimal(tax_amount),
                },
                "notion_writes": 0,
                "canonical_ledger_postings": 0,
            },
        }


def build_adapters() -> RegionalAdapters:
    """Return the real adapters used by the durable regional CLI."""

    return RegionalAdapters(
        scenario=_ScenarioAdapter(),
        production=_ProductionAdapter(),
        market_transport=_MarketTransportAdapter(),
        finance=_FinanceAdapter(),
    )
