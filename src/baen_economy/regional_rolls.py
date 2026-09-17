"""Deterministic GURPS receipts for a regional preview month.

The regional material engine is causal: inventories, labour, routes, and needs
determine what can physically happen.  These rolls supply the campaign's
existing sector-management and expense-control shocks; they do not replace the
stock-flow constraints and they never advance campaign canon.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
from typing import Iterable, Mapping

from .business_month import employee_size_modifier, expense_factor, revenue_factor
from .domain import canonical_decimal
from .operator_codec import canonical_hash
from .operator_dice import _die, classify_3d6


REGIONAL_ROLL_SCHEMA = "tnp.economy.regional-rolls/1"
MARKET_MODIFIERS = {"boom": 4, "stable": 0, "recession": -2}


@dataclass(frozen=True, slots=True, order=True)
class SectorRollInput:
    sector: str
    revenue_streams: int = 1
    competent_managers: int = 0
    monopoly: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.sector, str) or not self.sector.strip():
            raise ValueError("sector name is required")
        if type(self.revenue_streams) is not int or self.revenue_streams < 1:
            raise ValueError("sector revenue streams must be a positive integer")
        if type(self.competent_managers) is not int or not 0 <= self.competent_managers <= 3:
            raise ValueError("competent managers must be an integer from 0 through 3")
        if type(self.monopoly) is not bool:
            raise ValueError("sector monopoly flag must be a boolean")


@dataclass(frozen=True, slots=True, order=True)
class ExpenseRollInput:
    entity_id: str
    employees: int
    excellent_accounting: bool = False
    rapid_expansion: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.entity_id, str) or not self.entity_id.strip():
            raise ValueError("expense-roll entity ID is required")
        if type(self.employees) is not int or self.employees < 0:
            raise ValueError("expense-roll employees must be a non-negative integer")
        if type(self.excellent_accounting) is not bool:
            raise ValueError("excellent-accounting flag must be a boolean")
        if type(self.rapid_expansion) is not bool:
            raise ValueError("rapid-expansion flag must be a boolean")


def roll_regional_month(
    *,
    state_hash: str,
    period_index: int,
    seed: str,
    sectors: Iterable[SectorRollInput],
    entities: Iterable[ExpenseRollInput],
    market: str = "stable",
    vara_active: bool = True,
) -> dict[str, object]:
    """Return replayable sector and entity checks for one preview month."""

    if not isinstance(state_hash, str) or len(state_hash) != 64:
        raise ValueError("regional rolls require a full opening state hash")
    if type(period_index) is not int or period_index < 1:
        raise ValueError("regional roll period must be a positive integer")
    if not isinstance(seed, str) or not seed:
        raise ValueError("regional preview seed must be non-empty text")
    if market not in MARKET_MODIFIERS:
        raise ValueError("market must be boom, stable, or recession")
    if type(vara_active) is not bool:
        raise ValueError("vara_active must be a boolean")

    sector_inputs = tuple(sorted(sectors))
    entity_inputs = tuple(sorted(entities))
    if len({item.sector for item in sector_inputs}) != len(sector_inputs):
        raise ValueError("regional sector rolls must be unique by sector")
    if len({item.entity_id for item in entity_inputs}) != len(entity_inputs):
        raise ValueError("regional expense rolls must be unique by entity")
    fingerprint = hashlib.sha256(seed.encode("utf-8")).hexdigest()

    sector_rolls = [
        _sector_roll(
            item,
            market=market,
            vara_active=vara_active,
            state_hash=state_hash,
            period_index=period_index,
            sampling_key=fingerprint,
        )
        for item in sector_inputs
    ]
    expense_rolls = [
        _expense_roll(
            item,
            state_hash=state_hash,
            period_index=period_index,
            sampling_key=fingerprint,
        )
        for item in entity_inputs
    ]
    body: dict[str, object] = {
        "schema": REGIONAL_ROLL_SCHEMA,
        "authority": "scenario_assumption",
        "canonical": False,
        "binding_scope": "this regional preview month only",
        "state_hash": state_hash,
        "period_index": period_index,
        "market": market,
        "vara_active": vara_active,
        "method": "hmac_sha256_seeded_preview",
        "seed_fingerprint": fingerprint,
        "sector_rolls": sector_rolls,
        "expense_rolls": expense_rolls,
        "campaign_state_rolls_resolved": 0,
    }
    body["manifest_hash"] = canonical_hash(body)
    validate_regional_rolls(body, seed=seed)
    return body


def validate_regional_rolls(manifest: object, *, seed: str | None = None) -> None:
    if not isinstance(manifest, dict):
        raise ValueError("regional roll manifest must be an object")
    required = {
        "schema", "authority", "canonical", "binding_scope", "state_hash",
        "period_index", "market", "vara_active", "method", "seed_fingerprint",
        "sector_rolls", "expense_rolls", "campaign_state_rolls_resolved",
        "manifest_hash",
    }
    if set(manifest) != required:
        raise ValueError("regional roll manifest keys do not match the schema")
    supplied_hash = manifest["manifest_hash"]
    body = {key: value for key, value in manifest.items() if key != "manifest_hash"}
    if supplied_hash != canonical_hash(body):
        raise ValueError("regional roll manifest hash does not match")
    if (
        manifest["schema"] != REGIONAL_ROLL_SCHEMA
        or manifest["authority"] != "scenario_assumption"
        or manifest["canonical"] is not False
        or manifest["binding_scope"] != "this regional preview month only"
        or manifest["method"] != "hmac_sha256_seeded_preview"
        or manifest["campaign_state_rolls_resolved"] != 0
    ):
        raise ValueError("regional roll authority boundary is inconsistent")
    state_hash = manifest["state_hash"]
    period_index = manifest["period_index"]
    fingerprint = manifest["seed_fingerprint"]
    if not isinstance(state_hash, str) or len(state_hash) != 64:
        raise ValueError("regional roll state hash is invalid")
    if type(period_index) is not int or period_index < 1:
        raise ValueError("regional roll period is invalid")
    if not isinstance(fingerprint, str) or len(fingerprint) != 64:
        raise ValueError("regional roll seed fingerprint is invalid")
    if seed is not None and hashlib.sha256(seed.encode("utf-8")).hexdigest() != fingerprint:
        raise ValueError("regional roll seed does not match its fingerprint")
    sampling_key = fingerprint
    for group, coordinate_key in (
        (manifest["sector_rolls"], "sector"),
        (manifest["expense_rolls"], "entity_id"),
    ):
        if not isinstance(group, list):
            raise ValueError("regional roll groups must be arrays")
        identities: list[str] = []
        for roll in group:
            if not isinstance(roll, dict):
                raise ValueError("regional roll receipt must be an object")
            identity = roll.get(coordinate_key)
            if not isinstance(identity, str) or not identity:
                raise ValueError("regional roll receipt identity is missing")
            identities.append(identity)
            faces = roll.get("dice")
            if not isinstance(faces, list) or len(faces) != 3 or any(
                type(face) is not int or not 1 <= face <= 6 for face in faces
            ):
                raise ValueError("regional roll receipt does not contain valid 3d6")
            total = sum(faces)
            target = roll.get("effective_target")
            if type(target) is not int or roll.get("total") != total:
                raise ValueError("regional roll arithmetic is malformed")
            if roll.get("margin") != target - total:
                raise ValueError("regional roll margin is inconsistent")
            if roll.get("outcome") != classify_3d6(total=total, effective_target=target):
                raise ValueError("regional roll outcome is inconsistent")
            if seed is not None:
                kind = "sector" if coordinate_key == "sector" else "expense"
                expected = [
                    _die(
                        sides=6,
                        seed=sampling_key,
                        coordinate=(
                            "regional-month", state_hash, str(period_index),
                            kind, identity, str(index),
                        ),
                    )
                    for index in range(1, 4)
                ]
                if faces != expected:
                    raise ValueError("regional roll faces do not replay")
        if identities != sorted(identities) or len(identities) != len(set(identities)):
            raise ValueError("regional roll receipts are not uniquely sorted")


def _sector_roll(
    item: SectorRollInput,
    *,
    market: str,
    vara_active: bool,
    state_hash: str,
    period_index: int,
    sampling_key: str,
) -> dict[str, object]:
    modifiers = [{"label": f"Market {market}", "value": MARKET_MODIFIERS[market]}]
    if item.revenue_streams >= 7:
        modifiers.append({"label": "7+ revenue streams", "value": 2})
    elif item.revenue_streams >= 4:
        modifiers.append({"label": "4-6 revenue streams", "value": 1})
    if vara_active:
        modifiers.append({"label": "Vara active", "value": 3})
    if item.competent_managers:
        modifiers.append({"label": "Competent managers", "value": item.competent_managers})
    if item.monopoly:
        modifiers.append({"label": "Monopoly position", "value": 2})
    roll = _roll(
        kind="sector",
        identity=item.sector,
        base_target=15,
        modifiers=modifiers,
        state_hash=state_hash,
        period_index=period_index,
        sampling_key=sampling_key,
    )
    factor = revenue_factor(str(roll["outcome"]), int(roll["margin"]))
    return {
        "sector": item.sector,
        "target_authority": "hybrid-business-ops Merchant-15 sector revenue table",
        **roll,
        "revenue_factor": canonical_decimal(factor),
    }


def _expense_roll(
    item: ExpenseRollInput,
    *,
    state_hash: str,
    period_index: int,
    sampling_key: str,
) -> dict[str, object]:
    modifiers = [
        {"label": f"Entity size ({item.employees} employees)", "value": employee_size_modifier(item.employees)}
    ]
    if item.excellent_accounting:
        modifiers.append({"label": "Excellent accounting", "value": 2})
    if item.rapid_expansion:
        modifiers.append({"label": "Rapid expansion", "value": -3})
    roll = _roll(
        kind="expense",
        identity=item.entity_id,
        base_target=16,
        modifiers=modifiers,
        state_hash=state_hash,
        period_index=period_index,
        sampling_key=sampling_key,
    )
    factor = expense_factor(str(roll["outcome"]), int(roll["margin"]))
    return {
        "entity_id": item.entity_id,
        "employees": item.employees,
        "target_authority": "hybrid-business-ops Administration-16 expense table",
        **roll,
        "expense_factor": canonical_decimal(factor),
    }


def _roll(
    *,
    kind: str,
    identity: str,
    base_target: int,
    modifiers: list[Mapping[str, object]],
    state_hash: str,
    period_index: int,
    sampling_key: str,
) -> dict[str, object]:
    faces = [
        _die(
            sides=6,
            seed=sampling_key,
            coordinate=(
                "regional-month", state_hash, str(period_index), kind, identity, str(index)
            ),
        )
        for index in range(1, 4)
    ]
    modifier_total = sum(int(item["value"]) for item in modifiers)
    target = base_target + modifier_total
    total = sum(faces)
    return {
        "dice": faces,
        "total": total,
        "base_target": base_target,
        "modifiers": [dict(item) for item in modifiers],
        "modifier_total": modifier_total,
        "effective_target": target,
        "margin": target - total,
        "outcome": classify_3d6(total=total, effective_target=target),
    }
