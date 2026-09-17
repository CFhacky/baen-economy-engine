"""Bundled, explicitly non-canonical operator scenarios.

The runnable values in this module are assumption profiles.  They are kept
separate from ``fixtures/canonical-import`` so that making a preview executable
cannot silently add facts to campaign canon.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
from types import MappingProxyType
from typing import Mapping

from .events import CURRENT_MODEL_VERSION, canonical_json
from .stockflow import (
    Commodity,
    EconomyModel,
    InventoryPosition,
    Need,
    Route,
    RunPlan,
    ShipmentOrder,
    Site,
    Snapshot,
    initial_snapshot,
)


SCENARIO_SCHEMA = "tnp.economy.operator-scenario/1"
RULESET_VERSION = "economy-operator-0.1.0"
LADEN_SCENARIO_ID = "operation-laden-table"
LADEN_PROFILE_ID = "illustrative-low-v1"


class ScenarioError(ValueError):
    """Raised when an operator scenario is unavailable or internally invalid."""


@dataclass(frozen=True, slots=True)
class ScenarioPackage:
    """Frozen scenario facts, assumptions, and operator permissions."""

    payload: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", _freeze(self.payload))

    @property
    def scenario_id(self) -> str:
        return str(self.payload["scenario_id"])

    @property
    def profile_id(self) -> str:
        return str(self.payload["assumption_profile_id"])

    @property
    def timeline_id(self) -> str:
        return str(self.payload["timeline_id"])

    @property
    def scenario_hash(self) -> str:
        return hashlib.sha256(canonical_json(self.payload).encode("utf-8")).hexdigest()

    @property
    def max_period(self) -> int:
        return int(self.payload["max_period"])

    def model(self) -> EconomyModel:
        assumptions = _assumption_values(self.payload)
        return EconomyModel(
            commodities=(
                Commodity(
                    "commodity:grain",
                    "Grain",
                    "ton",
                    None,
                    elasticity=Decimal("0"),
                    market_price_enabled=False,
                ),
            ),
            sites=(
                Site("site:illustrative-supplier", "Illustrative supplier", Decimal("0")),
                Site("site:longsaddle", "Longsaddle", Decimal("0")),
            ),
            recipes=(),
            routes=(
                Route(
                    "route:illustrative-supplier-longsaddle",
                    "site:illustrative-supplier",
                    "site:longsaddle",
                    "commodity:grain",
                    Decimal(assumptions["route_capacity_tons_per_period"]),
                    int(assumptions["travel_periods"]),
                    Decimal(assumptions["loss_rate"]),
                ),
            ),
            model_version=CURRENT_MODEL_VERSION,
        )

    def opening_snapshot(self) -> Snapshot:
        assumptions = _assumption_values(self.payload)
        return initial_snapshot(
            self.model(),
            timeline_id=self.timeline_id,
            campaign_ordinal=0,
            campaign_date=str(assumptions["opening_date_placement"]),
            ruleset_version=RULESET_VERSION,
            inventories=(
                InventoryPosition(
                    "site:illustrative-supplier",
                    "commodity:grain",
                    Decimal(assumptions["opening_supplier_stock_tons"]),
                ),
            ),
        )

    def plan(self, period_index: int, *, authorizing_events: tuple = ()) -> RunPlan:
        assumptions = _assumption_values(self.payload)
        if period_index == 1:
            return RunPlan(
                period_index=1,
                campaign_ordinal=1,
                campaign_date="Eleasis 1495 DR (illustrative dispatch period 1)",
                shipment_orders=(
                    ShipmentOrder(
                        "shipment:laden-preview:1",
                        "route:illustrative-supplier-longsaddle",
                        "commodity:grain",
                        Decimal(assumptions["selected_target_tons"]),
                        "fixture:canonical-import/operation-laden-table.json + "
                        "assumption-profile:illustrative-low-v1",
                    ),
                ),
                authorizing_events=authorizing_events,
            )
        if period_index == 2:
            return RunPlan(
                period_index=2,
                campaign_ordinal=2,
                campaign_date="Eleint 1495 DR (illustrative arrival period 2)",
                needs=(
                    Need(
                        "site:longsaddle",
                        "commodity:grain",
                        Decimal(assumptions["monthly_need_tons"]),
                    ),
                ),
                authorizing_events=authorizing_events,
            )
        raise ScenarioError(
            f"{self.scenario_id}/{self.profile_id} defines periods 1 and 2 only; "
            "additional months require an approved assumption profile"
        )


def _laden_payload() -> dict[str, object]:
    return {
        "schema": SCENARIO_SCHEMA,
        "scenario_id": LADEN_SCENARIO_ID,
        "assumption_profile_id": LADEN_PROFILE_ID,
        "title": "Operation Laden Table — illustrative low case",
        "mode": "preview",
        "canonical": False,
        "timeline_id": "preview:operation-laden-table:illustrative-low-v1",
        "max_period": 2,
        "source_anchor": {
            "fixture": "fixtures/canonical-import/operation-laden-table.json",
            "timeline_id": "source:operation-laden-table-late-kythorn-1495",
            "planning_date": "Late Kythorn 1495 DR",
            "economy_timeline_mapping": "unresolved_CAN-001",
            "source_refs": [
                "https://app.notion.com/p/396e821484b0816c9dd3e88e17fc70f1",
                "https://app.notion.com/p/348e821484b081a68349ecdc1f0efef8",
            ],
        },
        "sourced_facts": {
            "status": "Active; assembly and instruction",
            "population_mouths": 11000,
            "local_food_position": "net_importer",
            "grain_target_tons": {"low": "1200", "high": "1500"},
            "grain_including_transport_gp": {"low": "65000", "high": "95000"},
            "borrowing_target_gp": {"low": "200000", "high": "300000"},
            "borrowing_treatment": "liability_not_revenue",
            "departure_window": "Early Flamerule 1495 DR",
            "first_grain_movement": "Eleasis 1495 DR",
            "binding_execution_rolls_pending": 7,
            "source_recorded_procurement_or_financing_transactions": 0,
            "transaction_scope": (
                "The cited plan records no completed procurement or financing settlement; "
                "this is not a complete cash audit."
            ),
        },
        "assumptions": [
            {
                "key": "selected_target_tons",
                "value": "1200",
                "basis": "Select the source's lower target bound for an illustrative case.",
            },
            {
                "key": "delivery_scope",
                "value": "Longsaddle-only illustrative logistics slice",
                "basis": (
                    "Assumes the full selected target enters this route; does not allocate "
                    "the source plan's shelter-zone or strategic-reserve shares."
                ),
            },
            {
                "key": "opening_date_placement",
                "value": "End of Flamerule 1495 DR (illustrative pre-dispatch opening)",
                "basis": (
                    "Places the hypothetical opening immediately before the source's "
                    "Eleasis first-grain-movement window; the Late Kythorn source anchor "
                    "remains a separate planning date."
                ),
            },
            {
                "key": "period_1_local_provisioning_scope",
                "value": "outside this cargo slice",
                "basis": (
                    "Longsaddle local consumption before the first arrival is unresolved, "
                    "so period 1 reports need and shortage as not modeled rather than zero."
                ),
            },
            {
                "key": "opening_supplier_stock_tons",
                "value": "1200",
                "basis": "Illustrative stock; seller availability is unresolved in the source.",
            },
            {
                "key": "route_capacity_tons_per_period",
                "value": "900",
                "basis": "Illustrative capacity; route capacity is unresolved in the source.",
            },
            {
                "key": "travel_periods",
                "value": 1,
                "basis": "Illustrative travel time; travel duration is unresolved in the source.",
            },
            {
                "key": "loss_rate",
                "value": "0.02",
                "basis": "Illustrative handling loss; spoilage/loss is unresolved in the source.",
            },
            {
                "key": "monthly_need_tons",
                "value": "300",
                "basis": "Lower 1,200-ton target divided over four illustrative bridge months.",
            },
            {
                "key": "illustrative_planning_basis_gp_per_ton",
                "value": "54.1667",
                "basis": "65,000 gp / 1,200 tons; includes transport and is NOT a market or settlement price.",
            },
        ],
        "permissions": {
            "notion_write": False,
            "ledger_post": False,
            "live_dice": False,
            "promote_to_actual": False,
        },
        "unresolved": [
            "campaign economy timeline mapping (CAN-001)",
            "opening food inventories and seller stock",
            "ration and consumption rates",
            "route capacities and travel time",
            "spoilage and handling loss",
            "procurement price and settlement",
            "loan lender, currency, rate, maturity, collateral, and draw timing",
            "opening cash and accepted ledger migration band",
            "all seven binding execution rolls",
        ],
    }


def _assumption_values(payload: Mapping[str, object]) -> dict[str, object]:
    assumptions = payload.get("assumptions")
    if not isinstance(assumptions, (list, tuple)):
        raise ScenarioError("scenario assumptions must be an array")
    values: dict[str, object] = {}
    for assumption in assumptions:
        if not isinstance(assumption, Mapping):
            raise ScenarioError("scenario assumption must be an object")
        key = assumption.get("key")
        if not isinstance(key, str) or not key or key in values:
            raise ScenarioError("scenario assumption keys must be unique non-empty strings")
        values[key] = assumption.get("value")
    required = {
        "selected_target_tons",
        "opening_supplier_stock_tons",
        "route_capacity_tons_per_period",
        "travel_periods",
        "loss_rate",
        "monthly_need_tons",
        "illustrative_planning_basis_gp_per_ton",
        "opening_date_placement",
        "period_1_local_provisioning_scope",
    }
    missing = required - values.keys()
    if missing:
        raise ScenarioError(f"scenario assumptions are missing: {sorted(missing)}")
    return values


def available_scenarios() -> tuple[ScenarioPackage, ...]:
    """Return every bundled operator scenario in stable order."""

    return (ScenarioPackage(_laden_payload()),)


def load_scenario(
    scenario_id: str,
    *,
    profile_id: str = LADEN_PROFILE_ID,
    stored_payload: Mapping[str, object] | None = None,
) -> ScenarioPackage:
    """Load and validate a bundled or persisted scenario package."""

    if stored_payload is not None:
        package = ScenarioPackage(dict(stored_payload))
        if package.payload.get("schema") != SCENARIO_SCHEMA:
            raise ScenarioError("stored scenario has an unsupported schema")
        if package.scenario_id != scenario_id or package.profile_id != profile_id:
            raise ScenarioError("stored scenario identity does not match campaign metadata")
        _assumption_values(package.payload)
        package.model().validate()
        return package
    for package in available_scenarios():
        if package.scenario_id == scenario_id and package.profile_id == profile_id:
            package.model().validate()
            return package
    raise ScenarioError(f"unknown scenario/profile: {scenario_id}/{profile_id}")


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value
