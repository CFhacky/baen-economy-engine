"""Source-aware value objects for the regional-economy vertical slice.

The regional layer deliberately distinguishes a known zero from an unknown
quantity.  A finite :class:`~decimal.Decimal` is known; ``None`` is an
unresolved campaign fact.  The production orchestrator will preserve
unreferenced unknowns and reject any attempt to execute a recipe that depends
on one.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from typing import Mapping

from .domain import canonical_decimal


ZERO = Decimal("0")
ONE = Decimal("1")


class RegionalDomainError(ValueError):
    """Raised when regional state is ambiguous or structurally invalid."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise RegionalDomainError(f"{label} must be a non-empty trimmed string")
    return value


def _decimal_or_unknown(
    value: object,
    label: str,
    *,
    minimum: Decimal = ZERO,
    strictly_positive: bool = False,
) -> Decimal | None:
    if value is None:
        return None
    if type(value) is not Decimal or not value.is_finite():
        raise RegionalDomainError(
            f"{label} must be a finite Decimal or explicit unknown (None)"
        )
    if strictly_positive and value <= minimum:
        raise RegionalDomainError(f"{label} must be positive")
    if not strictly_positive and value < minimum:
        raise RegionalDomainError(f"{label} cannot be below {minimum}")
    return value


def _concrete_tuple(value: object, item_type: type[object], label: str) -> tuple:
    if type(value) is not tuple or any(type(item) is not item_type for item in value):
        raise RegionalDomainError(f"{label} must be an immutable tuple of {item_type.__name__}")
    return value


def _json_safe(value: object) -> object:
    if isinstance(value, Decimal):
        return canonical_decimal(value)
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise RegionalDomainError("canonical regional mappings require string keys")
        return {
            key: _json_safe(item)
            for key, item in sorted(value.items(), key=lambda pair: pair[0])
        }
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float):
        raise RegionalDomainError("binary floating-point values cannot enter regional state")
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise RegionalDomainError(f"unsupported regional value: {type(value).__name__}")


def canonical_payload_hash(value: object) -> str:
    """Return the deterministic SHA-256 receipt for a JSON-safe value tree."""

    payload = json.dumps(
        _json_safe(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _exact_keys(value: object, expected: set[str], label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise RegionalDomainError(f"{label} must be an object with string keys")
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise RegionalDomainError(
            f"{label} keys do not match schema; missing={missing}, extra={extra}"
        )
    return value


def _decimal_text_or_unknown(value: object, label: str) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or value != value.strip():
        raise RegionalDomainError(f"{label} must be an exact decimal string or null")
    try:
        result = Decimal(value)
    except Exception as exc:  # Decimal exposes several InvalidOperation subclasses.
        raise RegionalDomainError(f"{label} is not an exact decimal string") from exc
    if not result.is_finite() or canonical_decimal(result) != value:
        raise RegionalDomainError(f"{label} is not canonical finite Decimal text")
    return result


@dataclass(frozen=True, slots=True, order=True)
class CommoditySpec:
    commodity_id: str
    name: str
    unit: str
    source_ref: str
    perishable_loss_rate: Decimal = ZERO

    def __post_init__(self) -> None:
        _text(self.commodity_id, "commodity ID")
        _text(self.name, "commodity name")
        _text(self.unit, "commodity unit")
        _text(self.source_ref, "commodity source reference")
        if _decimal_or_unknown(self.perishable_loss_rate, "perishable loss rate") is None:
            raise RegionalDomainError("perishable loss rate cannot be unknown")
        if self.perishable_loss_rate >= ONE:
            raise RegionalDomainError("perishable loss rate must be in [0, 1)")

    def to_dict(self) -> dict[str, object]:
        return {
            "commodity_id": self.commodity_id,
            "name": self.name,
            "unit": self.unit,
            "source_ref": self.source_ref,
            "perishable_loss_rate": canonical_decimal(self.perishable_loss_rate),
        }


@dataclass(frozen=True, slots=True, order=True)
class InventoryLot:
    owner_id: str
    site_id: str
    commodity_id: str
    quantity: Decimal | None
    source_ref: str

    def __post_init__(self) -> None:
        _text(self.owner_id, "inventory owner ID")
        _text(self.site_id, "inventory site ID")
        _text(self.commodity_id, "inventory commodity ID")
        _text(self.source_ref, "inventory source reference")
        _decimal_or_unknown(self.quantity, "inventory quantity")

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.owner_id, self.site_id, self.commodity_id)

    def to_dict(self) -> dict[str, object]:
        return {
            "owner_id": self.owner_id,
            "site_id": self.site_id,
            "commodity_id": self.commodity_id,
            "quantity": (
                None if self.quantity is None else canonical_decimal(self.quantity)
            ),
            "source_ref": self.source_ref,
        }


@dataclass(frozen=True, slots=True, order=True)
class LaborPool:
    owner_id: str
    site_id: str
    labor_class: str
    workers: Decimal | None
    available_worker_days: Decimal | None
    wage_gp_per_day: Decimal | None
    source_ref: str

    def __post_init__(self) -> None:
        _text(self.owner_id, "labor owner ID")
        _text(self.site_id, "labor site ID")
        _text(self.labor_class, "labor class")
        _text(self.source_ref, "labor source reference")
        _decimal_or_unknown(self.workers, "labor worker count")
        _decimal_or_unknown(self.available_worker_days, "available worker-days")
        _decimal_or_unknown(self.wage_gp_per_day, "worker-day wage")
        if (
            self.workers is not None
            and self.workers == ZERO
            and self.available_worker_days not in {None, ZERO}
        ):
            raise RegionalDomainError("zero workers cannot supply positive worker-days")

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.owner_id, self.site_id, self.labor_class)

    def to_dict(self) -> dict[str, object]:
        return {
            "owner_id": self.owner_id,
            "site_id": self.site_id,
            "labor_class": self.labor_class,
            "workers": None if self.workers is None else canonical_decimal(self.workers),
            "available_worker_days": (
                None
                if self.available_worker_days is None
                else canonical_decimal(self.available_worker_days)
            ),
            "wage_gp_per_day": (
                None
                if self.wage_gp_per_day is None
                else canonical_decimal(self.wage_gp_per_day)
            ),
            "source_ref": self.source_ref,
        }


@dataclass(frozen=True, slots=True, order=True)
class MaterialRequirement:
    commodity_id: str
    quantity_per_batch: Decimal | None

    def __post_init__(self) -> None:
        _text(self.commodity_id, "recipe commodity ID")
        _decimal_or_unknown(
            self.quantity_per_batch,
            "material quantity per batch",
            strictly_positive=True,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "commodity_id": self.commodity_id,
            "quantity_per_batch": (
                None
                if self.quantity_per_batch is None
                else canonical_decimal(self.quantity_per_batch)
            ),
        }


@dataclass(frozen=True, slots=True, order=True)
class LaborRequirement:
    labor_class: str
    worker_days_per_batch: Decimal | None

    def __post_init__(self) -> None:
        _text(self.labor_class, "recipe labor class")
        _decimal_or_unknown(
            self.worker_days_per_batch,
            "worker-days per batch",
            strictly_positive=True,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "labor_class": self.labor_class,
            "worker_days_per_batch": (
                None
                if self.worker_days_per_batch is None
                else canonical_decimal(self.worker_days_per_batch)
            ),
        }


@dataclass(frozen=True, slots=True)
class ProductionRecipe:
    recipe_id: str
    operator_id: str
    site_id: str
    inputs: tuple[MaterialRequirement, ...] | None
    outputs: tuple[MaterialRequirement, ...] | None
    labor_requirements: tuple[LaborRequirement, ...] | None
    max_batches_per_month: Decimal | None
    source_ref: str
    priority: int = 100

    def __post_init__(self) -> None:
        _text(self.recipe_id, "recipe ID")
        _text(self.operator_id, "recipe operator ID")
        _text(self.site_id, "recipe site ID")
        _text(self.source_ref, "recipe source reference")
        if self.inputs is not None:
            _concrete_tuple(self.inputs, MaterialRequirement, "recipe inputs")
            _unique(
                (item.commodity_id for item in self.inputs),
                "recipe input commodity",
            )
        if self.outputs is not None:
            _concrete_tuple(self.outputs, MaterialRequirement, "recipe outputs")
            _unique(
                (item.commodity_id for item in self.outputs),
                "recipe output commodity",
            )
            if not self.outputs:
                raise RegionalDomainError("a known recipe must produce an output")
        if self.labor_requirements is not None:
            _concrete_tuple(
                self.labor_requirements,
                LaborRequirement,
                "recipe labor requirements",
            )
            _unique(
                (item.labor_class for item in self.labor_requirements),
                "recipe labor class",
            )
        _decimal_or_unknown(
            self.max_batches_per_month,
            "recipe monthly batch capacity",
        )
        if type(self.priority) is not int:
            raise RegionalDomainError("recipe priority must be an integer")

    def to_dict(self) -> dict[str, object]:
        return {
            "recipe_id": self.recipe_id,
            "operator_id": self.operator_id,
            "site_id": self.site_id,
            "inputs": (
                None if self.inputs is None else [item.to_dict() for item in self.inputs]
            ),
            "outputs": (
                None
                if self.outputs is None
                else [item.to_dict() for item in self.outputs]
            ),
            "labor_requirements": (
                None
                if self.labor_requirements is None
                else [item.to_dict() for item in self.labor_requirements]
            ),
            "max_batches_per_month": (
                None
                if self.max_batches_per_month is None
                else canonical_decimal(self.max_batches_per_month)
            ),
            "source_ref": self.source_ref,
            "priority": self.priority,
        }


@dataclass(frozen=True, slots=True, order=True)
class ProductionOrder:
    recipe_id: str
    requested_batches: Decimal | None

    def __post_init__(self) -> None:
        _text(self.recipe_id, "production-order recipe ID")
        _decimal_or_unknown(self.requested_batches, "requested production batches")

    def to_dict(self) -> dict[str, object]:
        return {
            "recipe_id": self.recipe_id,
            "requested_batches": (
                None
                if self.requested_batches is None
                else canonical_decimal(self.requested_batches)
            ),
        }


@dataclass(frozen=True, slots=True)
class RegionalState:
    month_index: int
    commodities: tuple[CommoditySpec, ...]
    inventories: tuple[InventoryLot, ...]
    labor_pools: tuple[LaborPool, ...]

    def __post_init__(self) -> None:
        if type(self.month_index) is not int or self.month_index < 0:
            raise RegionalDomainError("regional month index must be a non-negative integer")
        _concrete_tuple(self.commodities, CommoditySpec, "regional commodities")
        _concrete_tuple(self.inventories, InventoryLot, "regional inventories")
        _concrete_tuple(self.labor_pools, LaborPool, "regional labor pools")
        commodity_ids = _unique(
            (item.commodity_id for item in self.commodities),
            "regional commodity",
        )
        _unique((item.key for item in self.inventories), "regional inventory key")
        _unique((item.key for item in self.labor_pools), "regional labor-pool key")
        unknown_inventory_commodities = {
            item.commodity_id for item in self.inventories
        } - commodity_ids
        if unknown_inventory_commodities:
            raise RegionalDomainError(
                "inventories reference unknown commodities: "
                f"{sorted(unknown_inventory_commodities)}"
            )
        # Canonicalize immutable collections once so a persisted/reopened state
        # compares equal to the in-memory state that produced it.
        object.__setattr__(self, "commodities", tuple(sorted(self.commodities)))
        object.__setattr__(self, "inventories", tuple(sorted(self.inventories)))
        object.__setattr__(self, "labor_pools", tuple(sorted(self.labor_pools)))

    @property
    def period_index(self) -> int:
        """Compatibility name for callers that label a month as a period."""

        return self.month_index

    @property
    def state_hash(self) -> str:
        return canonical_payload_hash(self._body_dict())

    def _body_dict(self) -> dict[str, object]:
        return {
            "schema": "tnp.economy.regional-state/1",
            "month_index": self.month_index,
            "commodities": [
                item.to_dict() for item in sorted(self.commodities)
            ],
            "inventories": [
                item.to_dict() for item in sorted(self.inventories)
            ],
            "labor_pools": [
                item.to_dict() for item in sorted(self.labor_pools)
            ],
        }

    def to_dict(self) -> dict[str, object]:
        body = self._body_dict()
        body["state_hash"] = self.state_hash
        return body


def regional_state_from_dict(payload: Mapping[str, object]) -> RegionalState:
    """Reopen a persisted regional state after exact schema/hash verification."""

    root = _exact_keys(
        payload,
        {
            "schema",
            "month_index",
            "commodities",
            "inventories",
            "labor_pools",
            "state_hash",
        },
        "regional state",
    )
    if root["schema"] != "tnp.economy.regional-state/1":
        raise RegionalDomainError("regional state schema is unsupported")
    supplied_hash = root["state_hash"]
    if (
        not isinstance(supplied_hash, str)
        or len(supplied_hash) != 64
        or any(character not in "0123456789abcdef" for character in supplied_hash)
    ):
        raise RegionalDomainError("regional state hash is not a lowercase SHA-256 digest")
    body = dict(root)
    del body["state_hash"]
    if canonical_payload_hash(body) != supplied_hash:
        raise RegionalDomainError("regional state hash does not match its payload")
    month_index = root["month_index"]
    if type(month_index) is not int:
        raise RegionalDomainError("regional month index must be an integer")

    commodities_raw = root["commodities"]
    inventories_raw = root["inventories"]
    labor_raw = root["labor_pools"]
    for values, label in (
        (commodities_raw, "regional commodities"),
        (inventories_raw, "regional inventories"),
        (labor_raw, "regional labor pools"),
    ):
        if not isinstance(values, list):
            raise RegionalDomainError(f"{label} must be a JSON list")

    commodities = tuple(
        CommoditySpec(
            commodity_id=_text(item["commodity_id"], "commodity ID"),
            name=_text(item["name"], "commodity name"),
            unit=_text(item["unit"], "commodity unit"),
            source_ref=_text(item["source_ref"], "commodity source reference"),
            perishable_loss_rate=_known_decimal_text(
                item["perishable_loss_rate"], "perishable loss rate"
            ),
        )
        for raw in commodities_raw
        for item in (
            _exact_keys(
                raw,
                {
                    "commodity_id",
                    "name",
                    "unit",
                    "source_ref",
                    "perishable_loss_rate",
                },
                "commodity",
            ),
        )
    )
    inventories = tuple(
        InventoryLot(
            owner_id=_text(item["owner_id"], "inventory owner ID"),
            site_id=_text(item["site_id"], "inventory site ID"),
            commodity_id=_text(item["commodity_id"], "inventory commodity ID"),
            quantity=_decimal_text_or_unknown(item["quantity"], "inventory quantity"),
            source_ref=_text(item["source_ref"], "inventory source reference"),
        )
        for raw in inventories_raw
        for item in (
            _exact_keys(
                raw,
                {"owner_id", "site_id", "commodity_id", "quantity", "source_ref"},
                "inventory lot",
            ),
        )
    )
    labor_pools = tuple(
        LaborPool(
            owner_id=_text(item["owner_id"], "labor owner ID"),
            site_id=_text(item["site_id"], "labor site ID"),
            labor_class=_text(item["labor_class"], "labor class"),
            workers=_decimal_text_or_unknown(item["workers"], "labor worker count"),
            available_worker_days=_decimal_text_or_unknown(
                item["available_worker_days"], "available worker-days"
            ),
            wage_gp_per_day=_decimal_text_or_unknown(
                item["wage_gp_per_day"], "worker-day wage"
            ),
            source_ref=_text(item["source_ref"], "labor source reference"),
        )
        for raw in labor_raw
        for item in (
            _exact_keys(
                raw,
                {
                    "owner_id",
                    "site_id",
                    "labor_class",
                    "workers",
                    "available_worker_days",
                    "wage_gp_per_day",
                    "source_ref",
                },
                "labor pool",
            ),
        )
    )
    state = RegionalState(month_index, commodities, inventories, labor_pools)
    if state.state_hash != supplied_hash:
        raise RegionalDomainError("reconstructed regional state hash drifted")
    return state


def _known_decimal_text(value: object, label: str) -> Decimal:
    result = _decimal_text_or_unknown(value, label)
    if result is None:
        raise RegionalDomainError(f"{label} cannot be null")
    return result


def _unique(values, label: str) -> set:
    materialized = list(values)
    if len(materialized) != len(set(materialized)):
        raise RegionalDomainError(f"duplicate {label}")
    return set(materialized)


__all__ = [
    "CommoditySpec",
    "InventoryLot",
    "LaborPool",
    "LaborRequirement",
    "MaterialRequirement",
    "ProductionOrder",
    "ProductionRecipe",
    "RegionalDomainError",
    "RegionalState",
    "canonical_payload_hash",
    "regional_state_from_dict",
]
