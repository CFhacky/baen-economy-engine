"""Entity/payroll orchestration around the conserved stock-flow kernel.

This module does not implement a second production simulator.  It translates
source-aware regional contracts into :mod:`baen_economy.stockflow`, represents
each labor class as a finite monthly worker-day stock, runs the existing
conserved kernel, and translates the result back into owner-level inventory,
payroll, and readable production receipts.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
import hashlib

from .domain import canonical_decimal
from .regional_domain import (
    CommoditySpec,
    InventoryLot,
    LaborPool,
    ProductionOrder,
    ProductionRecipe,
    RegionalState,
    canonical_payload_hash,
)
from .stockflow import (
    Commodity as KernelCommodity,
    EconomyModel,
    FlowKind,
    InventoryPosition,
    ProductionOrder as KernelProductionOrder,
    Recipe as KernelRecipe,
    RunPlan,
    SimulationError,
    Site,
    advance as stockflow_advance,
    initial_snapshot,
)


ZERO = Decimal("0")
MONEY_QUANTUM = Decimal("0.01")
REGIONAL_PRODUCTION_RULESET = "tnp.economy.regional-production/1"
_INTERNAL_LABOR_PREFIX = "__regional_internal_labor__:"


def _decimal_context() -> Context:
    return Context(
        prec=40,
        rounding=ROUND_HALF_EVEN,
        Emin=-999999,
        Emax=999999,
        capitals=1,
        clamp=0,
    )


class RegionalProductionError(ValueError):
    """Raised when a regional production request is invalid."""


class UnresolvedProductionInput(RegionalProductionError):
    """Raised when execution would silently replace an unknown with a guess."""


@dataclass(frozen=True, slots=True, order=True)
class MaterialLine:
    commodity_id: str
    unit: str
    quantity: Decimal

    def to_dict(self) -> dict[str, str]:
        return {
            "commodity_id": self.commodity_id,
            "unit": self.unit,
            "quantity": canonical_decimal(self.quantity),
        }


@dataclass(frozen=True, slots=True, order=True)
class LaborLine:
    entity_id: str
    site_id: str
    labor_class: str
    workers: Decimal
    worker_days: Decimal
    wage_gp_per_day: Decimal
    payroll: Decimal

    def to_dict(self) -> dict[str, str]:
        return {
            "entity_id": self.entity_id,
            "site_id": self.site_id,
            "labor_class": self.labor_class,
            "workers": canonical_decimal(self.workers),
            "worker_days": canonical_decimal(self.worker_days),
            "wage_gp_per_day": canonical_decimal(self.wage_gp_per_day),
            "payroll": canonical_decimal(self.payroll),
        }


@dataclass(frozen=True, slots=True)
class ProductionReceipt:
    recipe_id: str
    entity_id: str
    site_id: str
    source_ref: str
    requested_batches: Decimal
    actual_batches: Decimal
    inputs: tuple[MaterialLine, ...]
    outputs: tuple[MaterialLine, ...]
    labor: tuple[LaborLine, ...]
    limiting_factors: tuple[str, ...]

    @property
    def input_consumed(self) -> Decimal:
        return sum((item.quantity for item in self.inputs), ZERO)

    @property
    def output_produced(self) -> Decimal:
        return sum((item.quantity for item in self.outputs), ZERO)

    @property
    def workers(self) -> Decimal:
        return sum((item.workers for item in self.labor), ZERO)

    @property
    def worker_days(self) -> Decimal:
        return sum((item.worker_days for item in self.labor), ZERO)

    @property
    def payroll(self) -> Decimal:
        return sum((item.payroll for item in self.labor), ZERO)

    def to_dict(self) -> dict[str, object]:
        return {
            "recipe_id": self.recipe_id,
            "entity_id": self.entity_id,
            "site_id": self.site_id,
            "source_ref": self.source_ref,
            "requested_batches": canonical_decimal(self.requested_batches),
            "actual_batches": canonical_decimal(self.actual_batches),
            "shortfall_batches": canonical_decimal(
                self.requested_batches - self.actual_batches
            ),
            "input_consumed": canonical_decimal(self.input_consumed),
            "output_produced": canonical_decimal(self.output_produced),
            "workers": canonical_decimal(self.workers),
            "worker_days": canonical_decimal(self.worker_days),
            "payroll": canonical_decimal(self.payroll),
            "inputs": [item.to_dict() for item in self.inputs],
            "outputs": [item.to_dict() for item in self.outputs],
            "labor": [item.to_dict() for item in self.labor],
            "limiting_factors": list(self.limiting_factors),
        }


@dataclass(frozen=True, slots=True, order=True)
class ConservationReceipt:
    commodity_id: str
    unit: str
    opening_known: Decimal
    inputs_consumed: Decimal
    outputs_produced: Decimal
    closing_known: Decimal
    residual: Decimal
    unknown_positions: int

    def to_dict(self) -> dict[str, object]:
        return {
            "commodity_id": self.commodity_id,
            "unit": self.unit,
            "opening_known": canonical_decimal(self.opening_known),
            "inputs_consumed": canonical_decimal(self.inputs_consumed),
            "outputs_produced": canonical_decimal(self.outputs_produced),
            "closing_known": canonical_decimal(self.closing_known),
            "residual": canonical_decimal(self.residual),
            "unknown_positions": self.unknown_positions,
            "scope": "known_positions_only",
        }


@dataclass(frozen=True, slots=True, order=True)
class PayrollEvent:
    event_id: str
    entity_id: str
    amount: Decimal

    def to_dict(self) -> dict[str, str]:
        return {
            "event_id": self.event_id,
            "kind": "payroll",
            "entity_id": self.entity_id,
            "amount": canonical_decimal(self.amount),
        }


@dataclass(frozen=True, slots=True)
class ProductionMonthResult:
    opening_state_hash: str
    closing_state_hash: str
    opening_month_index: int
    closing_month_index: int
    production: tuple[ProductionReceipt, ...]
    conservation: tuple[ConservationReceipt, ...]
    payroll_events: tuple[PayrollEvent, ...]
    next_state: RegionalState
    kernel_opening_hash: str
    kernel_closing_hash: str

    @property
    def input_consumed(self) -> Decimal:
        return sum((item.input_consumed for item in self.production), ZERO)

    @property
    def output_produced(self) -> Decimal:
        return sum((item.output_produced for item in self.production), ZERO)

    @property
    def workers(self) -> Decimal:
        return sum((item.workers for item in self.production), ZERO)

    @property
    def worker_days(self) -> Decimal:
        return sum((item.worker_days for item in self.production), ZERO)

    @property
    def payroll(self) -> Decimal:
        return sum((item.amount for item in self.payroll_events), ZERO)

    @property
    def labor_details(self) -> tuple[LaborLine, ...]:
        return tuple(line for receipt in self.production for line in receipt.labor)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": REGIONAL_PRODUCTION_RULESET,
            "opening_month_index": self.opening_month_index,
            "closing_month_index": self.closing_month_index,
            "opening_state_hash": self.opening_state_hash,
            "closing_state_hash": self.closing_state_hash,
            "kernel_opening_hash": self.kernel_opening_hash,
            "kernel_closing_hash": self.kernel_closing_hash,
            "production": {
                "input_consumed": canonical_decimal(self.input_consumed),
                "output_produced": canonical_decimal(self.output_produced),
                "runs": [item.to_dict() for item in self.production],
                "aggregate_note": (
                    "aggregate quantities are acceptance-view sums; itemized units "
                    "are authoritative"
                ),
            },
            "labor": {
                "workers": canonical_decimal(self.workers),
                "worker_days": canonical_decimal(self.worker_days),
                "payroll": canonical_decimal(self.payroll),
                "details": [item.to_dict() for item in self.labor_details],
            },
            "payroll_events": [item.to_dict() for item in self.payroll_events],
            "conservation": [item.to_dict() for item in self.conservation],
            "next_state": self.next_state.to_dict(),
        }


def advance_production_month(
    state: RegionalState,
    recipes: tuple[ProductionRecipe, ...],
    orders: tuple[ProductionOrder, ...],
) -> ProductionMonthResult:
    """Advance production exactly one month and return a conserved next state.

    Production is bounded by requested batches, monthly recipe capacity,
    owner/site material stock, and every required labor-class pool.  Labor is
    supplied to the stock-flow kernel as non-renewable worker-day inventory for
    this run; the returned :class:`RegionalState` carries the same staffing
    contract into the next month, where its worker-day capacity renews.
    """

    if type(state) is not RegionalState:
        raise RegionalProductionError("production state has the wrong type")
    if type(recipes) is not tuple or any(type(item) is not ProductionRecipe for item in recipes):
        raise RegionalProductionError("recipes must be an immutable ProductionRecipe tuple")
    if type(orders) is not tuple or any(type(item) is not ProductionOrder for item in orders):
        raise RegionalProductionError("orders must be an immutable ProductionOrder tuple")

    with localcontext(_decimal_context()):
        return _advance_production_month(state, recipes, orders)


def receipts_from_stockflow_run(
    run_result,
    *,
    recipes: tuple[ProductionRecipe, ...],
    orders: tuple[ProductionOrder, ...],
    commodities: tuple[CommoditySpec, ...],
    labor_pools: tuple[LaborPool, ...],
) -> tuple[ProductionReceipt, ...]:
    """Translate an already-executed stock-flow run without mutating inventory.

    This is the integration adapter for a regional orchestrator that runs one
    native :func:`stockflow.advance` call containing production, transport, and
    needs.  Material quantities come from that run's conserved flow receipt;
    entity labor/payroll comes from the source-aware recipe and staffing
    metadata supplied here.
    """

    for values, item_type, label in (
        (recipes, ProductionRecipe, "adapter recipes"),
        (orders, ProductionOrder, "adapter production orders"),
        (commodities, CommoditySpec, "adapter commodities"),
        (labor_pools, LaborPool, "adapter labor pools"),
    ):
        if type(values) is not tuple or any(type(item) is not item_type for item in values):
            raise RegionalProductionError(
                f"{label} must be an immutable {item_type.__name__} tuple"
            )
    if not hasattr(run_result, "production") or not hasattr(run_result, "flows"):
        raise RegionalProductionError("adapter requires a stockflow RunResult")

    recipe_by_id = _unique_by(recipes, "recipe_id", "adapter recipe")
    order_by_id = _unique_by(orders, "recipe_id", "adapter order")
    commodity_by_id = _unique_by(commodities, "commodity_id", "adapter commodity")
    labor_by_key = {}
    for pool in labor_pools:
        if pool.key in labor_by_key:
            raise RegionalProductionError(f"duplicate adapter labor pool: {pool.key}")
        labor_by_key[pool.key] = pool

    result_by_id = {}
    for result in run_result.production:
        if result.recipe_id in result_by_id:
            raise RegionalProductionError(
                f"adapter cannot disambiguate repeated recipe result: {result.recipe_id}"
            )
        result_by_id[result.recipe_id] = result
    if set(result_by_id) != set(order_by_id) or set(order_by_id) - set(recipe_by_id):
        raise RegionalProductionError(
            "adapter recipe/order/result identities do not match exactly"
        )

    material_flows: defaultdict[tuple[str, FlowKind], list[MaterialLine]] = defaultdict(list)
    for flow in run_result.flows:
        if flow.kind not in {FlowKind.RECIPE_INPUT, FlowKind.PRODUCTION}:
            continue
        spec = commodity_by_id.get(flow.commodity_id)
        if spec is None:
            # The regional wrapper represents worker-days as private kernel
            # commodities.  They are accounted below as labor, not material.
            continue
        material_flows[(flow.reference_id, flow.kind)].append(
            MaterialLine(flow.commodity_id, spec.unit, flow.quantity)
        )

    receipts: list[ProductionReceipt] = []
    labor_used_by_pool: defaultdict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
    for recipe_id in sorted(
        result_by_id,
        key=lambda value: (recipe_by_id[value].priority, value),
    ):
        recipe = recipe_by_id[recipe_id]
        order = order_by_id[recipe_id]
        result = result_by_id[recipe_id]
        if order.requested_batches is None:
            raise UnresolvedProductionInput(
                f"production depends on unresolved facts: {recipe_id}.requested_batches"
            )
        if recipe.labor_requirements is None:
            raise UnresolvedProductionInput(
                f"production depends on unresolved facts: {recipe_id}.labor_requirements"
            )
        labor_lines: list[LaborLine] = []
        for requirement in recipe.labor_requirements:
            if requirement.worker_days_per_batch is None:
                raise UnresolvedProductionInput(
                    "production depends on unresolved facts: "
                    f"{recipe_id}.labor.{requirement.labor_class}.worker_days_per_batch"
                )
            key = (recipe.operator_id, recipe.site_id, requirement.labor_class)
            pool = labor_by_key.get(key)
            if pool is None or any(
                value is None
                for value in (
                    getattr(pool, "workers", None),
                    getattr(pool, "available_worker_days", None),
                    getattr(pool, "wage_gp_per_day", None),
                )
            ):
                raise UnresolvedProductionInput(
                    "production depends on unresolved facts: "
                    f"{recipe_id}.labor.{requirement.labor_class}.pool"
                )
            used_days = requirement.worker_days_per_batch * result.actual_batches
            labor_used_by_pool[key] += used_days
            if labor_used_by_pool[key] > pool.available_worker_days:
                raise RegionalProductionError(
                    f"stockflow result exceeds {requirement.labor_class} labor capacity"
                )
            labor_lines.append(
                LaborLine(
                    entity_id=recipe.operator_id,
                    site_id=recipe.site_id,
                    labor_class=requirement.labor_class,
                    workers=_workers_used(pool, used_days),
                    worker_days=used_days,
                    wage_gp_per_day=pool.wage_gp_per_day,
                    payroll=_money(used_days * pool.wage_gp_per_day),
                )
            )
        factors = () if result.actual_batches >= order.requested_batches else (
            "stockflow_kernel_bound",
        )
        receipts.append(
            ProductionReceipt(
                recipe_id=recipe.recipe_id,
                entity_id=recipe.operator_id,
                site_id=recipe.site_id,
                source_ref=recipe.source_ref,
                requested_batches=order.requested_batches,
                actual_batches=result.actual_batches,
                inputs=tuple(
                    sorted(material_flows[(recipe_id, FlowKind.RECIPE_INPUT)])
                ),
                outputs=tuple(
                    sorted(material_flows[(recipe_id, FlowKind.PRODUCTION)])
                ),
                labor=tuple(sorted(labor_lines)),
                limiting_factors=factors,
            )
        )
    return tuple(receipts)


def _advance_production_month(
    state: RegionalState,
    recipes: tuple[ProductionRecipe, ...],
    orders: tuple[ProductionOrder, ...],
) -> ProductionMonthResult:
    recipe_by_id = _unique_by(recipes, "recipe_id", "recipe")
    order_by_recipe = _unique_by(orders, "recipe_id", "production order")
    unknown_orders = set(order_by_recipe) - set(recipe_by_id)
    if unknown_orders:
        raise RegionalProductionError(f"orders reference unknown recipes: {sorted(unknown_orders)}")

    ordered_contracts = tuple(
        sorted(
            ((recipe_by_id[recipe_id], order) for recipe_id, order in order_by_recipe.items()),
            key=lambda pair: (pair[0].priority, pair[0].recipe_id),
        )
    )
    commodity_by_id = {item.commodity_id: item for item in state.commodities}
    inventory_by_key = {item.key: item for item in state.inventories}
    labor_by_key = {item.key: item for item in state.labor_pools}

    _validate_executable_contracts(
        ordered_contracts,
        commodity_by_id=commodity_by_id,
        inventory_by_key=inventory_by_key,
        labor_by_key=labor_by_key,
    )

    owner_sites = {
        (item.owner_id, item.site_id) for item in state.inventories
    } | {
        (item.owner_id, item.site_id) for item in state.labor_pools
    } | {
        (recipe.operator_id, recipe.site_id) for recipe, _ in ordered_contracts
    }
    site_to_kernel = {
        pair: _internal_id("site", *pair) for pair in sorted(owner_sites)
    }
    if len(set(site_to_kernel.values())) != len(site_to_kernel):
        raise RegionalProductionError("internal site identity collision")
    kernel_to_site = {value: key for key, value in site_to_kernel.items()}

    labor_token_by_key = {
        key: _INTERNAL_LABOR_PREFIX + _internal_digest(*key)
        for key, pool in labor_by_key.items()
        if _labor_is_referenced(key, ordered_contracts)
    }
    actual_commodity_ids = set(commodity_by_id)
    collisions = actual_commodity_ids & set(labor_token_by_key.values())
    if collisions:
        raise RegionalProductionError(
            f"commodity IDs collide with internal labor tokens: {sorted(collisions)}"
        )
    token_to_labor_key = {value: key for key, value in labor_token_by_key.items()}

    kernel_commodities = [
        KernelCommodity(
            commodity_id=item.commodity_id,
            name=item.name,
            unit=item.unit,
            base_price=None,
            market_price_enabled=False,
        )
        for item in state.commodities
    ]
    kernel_commodities.extend(
        KernelCommodity(
            commodity_id=token,
            name=f"Monthly worker-days: {key[2]}",
            unit="worker-day",
            base_price=None,
            market_price_enabled=False,
        )
        for key, token in sorted(labor_token_by_key.items())
    )

    kernel_sites = tuple(
        Site(
            site_id=kernel_id,
            name=f"{owner_id} at {site_id}",
            labor_capacity=ZERO,
        )
        for (owner_id, site_id), kernel_id in sorted(site_to_kernel.items())
    )
    kernel_recipes = tuple(
        _kernel_recipe(recipe, site_to_kernel, labor_token_by_key)
        for recipe, _ in ordered_contracts
    )
    model = EconomyModel(
        commodities=tuple(sorted(kernel_commodities)),
        sites=kernel_sites,
        recipes=kernel_recipes,
        routes=(),
    )

    opening_positions = [
        InventoryPosition(
            site_id=site_to_kernel[(lot.owner_id, lot.site_id)],
            commodity_id=lot.commodity_id,
            quantity=lot.quantity,
        )
        for lot in state.inventories
        if lot.quantity is not None
    ]
    opening_positions.extend(
        InventoryPosition(
            site_id=site_to_kernel[(pool.owner_id, pool.site_id)],
            commodity_id=labor_token_by_key[key],
            quantity=pool.available_worker_days,
        )
        for key, pool in sorted(labor_by_key.items())
        if key in labor_token_by_key
    )

    opening = initial_snapshot(
        model,
        timeline_id="regional-production-preview",
        campaign_ordinal=state.month_index,
        campaign_date=f"regional-month-{state.month_index}",
        ruleset_version=REGIONAL_PRODUCTION_RULESET,
        inventories=opening_positions,
    )
    plan = RunPlan(
        period_index=1,
        campaign_ordinal=state.month_index + 1,
        campaign_date=f"regional-month-{state.month_index + 1}",
        production_orders=tuple(
            KernelProductionOrder(recipe.recipe_id, order.requested_batches)
            for recipe, order in ordered_contracts
        ),
    )
    try:
        kernel_result = stockflow_advance(model, opening, plan)
    except SimulationError as exc:
        raise RegionalProductionError(f"stock-flow production failed: {exc}") from exc

    kernel_quantities = {
        (position.site_id, position.commodity_id): position.quantity
        for position in kernel_result.snapshot.inventories
    }
    next_state = _next_regional_state(
        state,
        kernel_quantities=kernel_quantities,
        kernel_to_site=kernel_to_site,
        actual_commodity_ids=actual_commodity_ids,
    )
    receipts = _production_receipts(
        ordered_contracts,
        kernel_result=kernel_result,
        commodity_by_id=commodity_by_id,
        labor_by_key=labor_by_key,
        labor_token_by_key=labor_token_by_key,
        kernel_quantities=kernel_quantities,
        site_to_kernel=site_to_kernel,
    )
    conservation = _conservation_receipts(
        state,
        next_state,
        receipts,
        commodity_by_id=commodity_by_id,
    )
    payroll_events = _payroll_events(receipts, state.month_index + 1)

    return ProductionMonthResult(
        opening_state_hash=state.state_hash,
        closing_state_hash=next_state.state_hash,
        opening_month_index=state.month_index,
        closing_month_index=next_state.month_index,
        production=receipts,
        conservation=conservation,
        payroll_events=payroll_events,
        next_state=next_state,
        kernel_opening_hash=opening.state_hash,
        kernel_closing_hash=kernel_result.snapshot.state_hash,
    )


def _validate_executable_contracts(
    contracts,
    *,
    commodity_by_id: dict[str, CommoditySpec],
    inventory_by_key: dict[tuple[str, str, str], InventoryLot],
    labor_by_key: dict[tuple[str, str, str], LaborPool],
) -> None:
    blockers: list[str] = []
    for recipe, order in contracts:
        if order.requested_batches is None:
            blockers.append(f"{recipe.recipe_id}.requested_batches")
        if recipe.max_batches_per_month is None:
            blockers.append(f"{recipe.recipe_id}.max_batches_per_month")
        if recipe.inputs is None:
            blockers.append(f"{recipe.recipe_id}.inputs")
        if recipe.outputs is None:
            blockers.append(f"{recipe.recipe_id}.outputs")
        if recipe.labor_requirements is None:
            blockers.append(f"{recipe.recipe_id}.labor_requirements")
        for role, materials in (("input", recipe.inputs), ("output", recipe.outputs)):
            for material in materials or ():
                if material.quantity_per_batch is None:
                    blockers.append(
                        f"{recipe.recipe_id}.{role}.{material.commodity_id}.quantity_per_batch"
                    )
                if material.commodity_id not in commodity_by_id:
                    blockers.append(
                        f"{recipe.recipe_id}.{role}.{material.commodity_id}.commodity_spec"
                    )
                key = (recipe.operator_id, recipe.site_id, material.commodity_id)
                lot = inventory_by_key.get(key)
                if role == "input" and lot is None:
                    blockers.append(
                        f"{recipe.recipe_id}.input.{material.commodity_id}.opening_inventory"
                    )
                if lot is not None and lot.quantity is None:
                    blockers.append(
                        f"{recipe.recipe_id}.{role}.{material.commodity_id}.opening_inventory"
                    )
        for requirement in recipe.labor_requirements or ():
            if requirement.worker_days_per_batch is None:
                blockers.append(
                    f"{recipe.recipe_id}.labor.{requirement.labor_class}.worker_days_per_batch"
                )
            key = (recipe.operator_id, recipe.site_id, requirement.labor_class)
            pool = labor_by_key.get(key)
            if pool is None:
                blockers.append(
                    f"{recipe.recipe_id}.labor.{requirement.labor_class}.pool"
                )
            else:
                for field, value in (
                    ("workers", pool.workers),
                    ("available_worker_days", pool.available_worker_days),
                    ("wage_gp_per_day", pool.wage_gp_per_day),
                ):
                    if value is None:
                        blockers.append(
                            f"{recipe.recipe_id}.labor.{requirement.labor_class}.{field}"
                        )
    if blockers:
        raise UnresolvedProductionInput(
            "production depends on unresolved facts: " + ", ".join(sorted(set(blockers)))
        )


def _kernel_recipe(recipe, site_to_kernel, labor_token_by_key) -> KernelRecipe:
    material_inputs = tuple(
        (item.commodity_id, item.quantity_per_batch) for item in recipe.inputs
    )
    labor_inputs = tuple(
        (
            labor_token_by_key[(recipe.operator_id, recipe.site_id, item.labor_class)],
            item.worker_days_per_batch,
        )
        for item in recipe.labor_requirements
    )
    return KernelRecipe(
        recipe_id=recipe.recipe_id,
        site_id=site_to_kernel[(recipe.operator_id, recipe.site_id)],
        entity_id=recipe.operator_id,
        inputs=tuple(sorted((*material_inputs, *labor_inputs))),
        outputs=tuple(
            sorted((item.commodity_id, item.quantity_per_batch) for item in recipe.outputs)
        ),
        labor_per_batch=ZERO,
        max_batches=recipe.max_batches_per_month,
        priority=recipe.priority,
    )


def _next_regional_state(
    state: RegionalState,
    *,
    kernel_quantities: dict[tuple[str, str], Decimal],
    kernel_to_site: dict[str, tuple[str, str]],
    actual_commodity_ids: set[str],
) -> RegionalState:
    closing_by_key: dict[tuple[str, str, str], Decimal] = {}
    for (kernel_site_id, commodity_id), quantity in kernel_quantities.items():
        if commodity_id not in actual_commodity_ids:
            continue
        owner_id, site_id = kernel_to_site[kernel_site_id]
        closing_by_key[(owner_id, site_id, commodity_id)] = quantity

    original_by_key = {item.key: item for item in state.inventories}
    lots: list[InventoryLot] = []
    for key, original in sorted(original_by_key.items()):
        if original.quantity is None:
            lots.append(original)
        else:
            lots.append(
                InventoryLot(
                    owner_id=original.owner_id,
                    site_id=original.site_id,
                    commodity_id=original.commodity_id,
                    quantity=closing_by_key.get(key, ZERO),
                    source_ref=original.source_ref,
                )
            )
    for key, quantity in sorted(closing_by_key.items()):
        if key in original_by_key:
            continue
        owner_id, site_id, commodity_id = key
        lots.append(
            InventoryLot(
                owner_id=owner_id,
                site_id=site_id,
                commodity_id=commodity_id,
                quantity=quantity,
                source_ref="engine:regional-production",
            )
        )
    return RegionalState(
        month_index=state.month_index + 1,
        commodities=state.commodities,
        inventories=tuple(sorted(lots)),
        labor_pools=state.labor_pools,
    )


def _production_receipts(
    contracts,
    *,
    kernel_result,
    commodity_by_id,
    labor_by_key,
    labor_token_by_key,
    kernel_quantities,
    site_to_kernel,
) -> tuple[ProductionReceipt, ...]:
    result_by_recipe = {item.recipe_id: item for item in kernel_result.production}
    material_flows: defaultdict[tuple[str, FlowKind], list[MaterialLine]] = defaultdict(list)
    labor_days: dict[tuple[str, str], Decimal] = {}
    token_to_key = {token: key for key, token in labor_token_by_key.items()}
    for flow in kernel_result.flows:
        if flow.kind not in {FlowKind.RECIPE_INPUT, FlowKind.PRODUCTION}:
            continue
        labor_key = token_to_key.get(flow.commodity_id)
        if labor_key is not None:
            labor_days[(flow.reference_id, labor_key[2])] = flow.quantity
            continue
        spec = commodity_by_id[flow.commodity_id]
        material_flows[(flow.reference_id, flow.kind)].append(
            MaterialLine(flow.commodity_id, spec.unit, flow.quantity)
        )

    receipts: list[ProductionReceipt] = []
    for recipe, order in contracts:
        kernel_production = result_by_recipe[recipe.recipe_id]
        labor_lines: list[LaborLine] = []
        for requirement in recipe.labor_requirements:
            key = (recipe.operator_id, recipe.site_id, requirement.labor_class)
            pool = labor_by_key[key]
            used_days = labor_days.get((recipe.recipe_id, requirement.labor_class), ZERO)
            workers_used = _workers_used(pool, used_days)
            payroll = _money(used_days * pool.wage_gp_per_day)
            labor_lines.append(
                LaborLine(
                    entity_id=recipe.operator_id,
                    site_id=recipe.site_id,
                    labor_class=requirement.labor_class,
                    workers=workers_used,
                    worker_days=used_days,
                    wage_gp_per_day=pool.wage_gp_per_day,
                    payroll=payroll,
                )
            )
        factors = _limiting_factors(
            recipe,
            requested=order.requested_batches,
            actual=kernel_production.actual_batches,
            kernel_quantities=kernel_quantities,
            site_to_kernel=site_to_kernel,
            labor_token_by_key=labor_token_by_key,
        )
        receipts.append(
            ProductionReceipt(
                recipe_id=recipe.recipe_id,
                entity_id=recipe.operator_id,
                site_id=recipe.site_id,
                source_ref=recipe.source_ref,
                requested_batches=order.requested_batches,
                actual_batches=kernel_production.actual_batches,
                inputs=tuple(sorted(material_flows[(recipe.recipe_id, FlowKind.RECIPE_INPUT)])),
                outputs=tuple(sorted(material_flows[(recipe.recipe_id, FlowKind.PRODUCTION)])),
                labor=tuple(sorted(labor_lines)),
                limiting_factors=factors,
            )
        )
    return tuple(receipts)


def _limiting_factors(
    recipe,
    *,
    requested,
    actual,
    kernel_quantities,
    site_to_kernel,
    labor_token_by_key,
) -> tuple[str, ...]:
    if actual >= requested:
        return ()
    factors: list[str] = []
    if actual == recipe.max_batches_per_month:
        factors.append("monthly_capacity")
    kernel_site = site_to_kernel[(recipe.operator_id, recipe.site_id)]
    for item in recipe.inputs:
        if kernel_quantities.get((kernel_site, item.commodity_id), ZERO) == ZERO:
            factors.append(f"input:{item.commodity_id}")
    for item in recipe.labor_requirements:
        key = (recipe.operator_id, recipe.site_id, item.labor_class)
        token = labor_token_by_key[key]
        if kernel_quantities.get((kernel_site, token), ZERO) == ZERO:
            factors.append(f"labor:{item.labor_class}")
    if not factors:
        factors.append("stockflow_kernel_bound")
    return tuple(sorted(set(factors)))


def _conservation_receipts(
    opening: RegionalState,
    closing: RegionalState,
    receipts: tuple[ProductionReceipt, ...],
    *,
    commodity_by_id: dict[str, CommoditySpec],
) -> tuple[ConservationReceipt, ...]:
    opening_known: defaultdict[str, Decimal] = defaultdict(Decimal)
    closing_known: defaultdict[str, Decimal] = defaultdict(Decimal)
    unknown_counts: defaultdict[str, int] = defaultdict(int)
    consumed: defaultdict[str, Decimal] = defaultdict(Decimal)
    produced: defaultdict[str, Decimal] = defaultdict(Decimal)
    for lot in opening.inventories:
        if lot.quantity is None:
            unknown_counts[lot.commodity_id] += 1
        else:
            opening_known[lot.commodity_id] += lot.quantity
    for lot in closing.inventories:
        if lot.quantity is not None:
            closing_known[lot.commodity_id] += lot.quantity
    for receipt in receipts:
        for line in receipt.inputs:
            consumed[line.commodity_id] += line.quantity
        for line in receipt.outputs:
            produced[line.commodity_id] += line.quantity

    commodity_ids = (
        set(opening_known)
        | set(closing_known)
        | set(consumed)
        | set(produced)
        | set(unknown_counts)
    )
    conservation: list[ConservationReceipt] = []
    for commodity_id in sorted(commodity_ids):
        residual = (
            opening_known[commodity_id]
            + produced[commodity_id]
            - consumed[commodity_id]
            - closing_known[commodity_id]
        )
        if residual != ZERO:
            raise RegionalProductionError(
                f"regional material conservation failed for {commodity_id}: {residual}"
            )
        conservation.append(
            ConservationReceipt(
                commodity_id=commodity_id,
                unit=commodity_by_id[commodity_id].unit,
                opening_known=opening_known[commodity_id],
                inputs_consumed=consumed[commodity_id],
                outputs_produced=produced[commodity_id],
                closing_known=closing_known[commodity_id],
                residual=residual,
                unknown_positions=unknown_counts[commodity_id],
            )
        )
    return tuple(conservation)


def _payroll_events(
    receipts: tuple[ProductionReceipt, ...], month_index: int
) -> tuple[PayrollEvent, ...]:
    by_entity: defaultdict[str, Decimal] = defaultdict(Decimal)
    for receipt in receipts:
        by_entity[receipt.entity_id] += receipt.payroll
    events: list[PayrollEvent] = []
    for entity_id, amount in sorted(by_entity.items()):
        if amount == ZERO:
            continue
        digest = canonical_payload_hash(
            {
                "kind": "payroll",
                "month_index": month_index,
                "entity_id": entity_id,
                "amount": amount,
            }
        )
        events.append(PayrollEvent(f"regional-payroll:{digest[:20]}", entity_id, amount))
    return tuple(events)


def _workers_used(pool: LaborPool, used_days: Decimal) -> Decimal:
    if used_days == ZERO:
        return ZERO
    if pool.workers == ZERO or pool.available_worker_days == ZERO:
        raise RegionalProductionError("positive worker-days escaped a zero-capacity labor pool")
    worker_days_per_worker = pool.available_worker_days / pool.workers
    return used_days / worker_days_per_worker


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_EVEN)


def _labor_is_referenced(key, contracts) -> bool:
    owner_id, site_id, labor_class = key
    return any(
        recipe.operator_id == owner_id
        and recipe.site_id == site_id
        and any(item.labor_class == labor_class for item in recipe.labor_requirements or ())
        for recipe, _ in contracts
    )


def _internal_digest(*parts: str) -> str:
    payload = "".join(f"{len(part)}:{part}" for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _internal_id(kind: str, *parts: str) -> str:
    return f"regional-{kind}:{_internal_digest(*parts)[:24]}"


def _unique_by(values, attribute: str, label: str) -> dict:
    result = {}
    for item in values:
        key = getattr(item, attribute)
        if key in result:
            raise RegionalProductionError(f"duplicate {label}: {key}")
        result[key] = item
    return result


__all__ = [
    "ConservationReceipt",
    "LaborLine",
    "MaterialLine",
    "PayrollEvent",
    "ProductionMonthResult",
    "ProductionReceipt",
    "RegionalProductionError",
    "UnresolvedProductionInput",
    "advance_production_month",
    "receipts_from_stockflow_run",
]
