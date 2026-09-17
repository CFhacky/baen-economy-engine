"""Read-only Agriculture/Aquaculture monthly financial previews.

The agriculture canon fixture contains seven Registry rows.  This module binds
the monthly preview to the five confirmed, dated commercial rows and keeps the
1498 Orchard Chapel reference and the unconfirmed Lobster King row outside the
calculation.  Every die face and every scenario modifier is returned in the
result; the module has no Notion or ledger write path.
"""

from __future__ import annotations

from decimal import Context, Decimal, ROUND_HALF_UP, localcontext
import hashlib
import hmac
import json
from pathlib import Path
import re
from typing import Mapping, Sequence

from .domain import canonical_decimal
from .operator_codec import canonical_hash
from .operator_dice import classify_3d6


FOOD_SECTOR_BASELINE_SCHEMA = "tnp.economy.food-sector-baseline/1"
FOOD_SECTOR_PREVIEW_SCHEMA = "tnp.food-sector.month-preview/1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANON_PATH = (
    PROJECT_ROOT / "fixtures" / "agriculture" / "agriculture-canon-v1.json"
)

SECTORS = ("Agriculture", "Aquaculture")
CHECKS = ("revenue", "expense")
_CENT = Decimal("0.01")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_MARKET_MODIFIERS = {"boom": 4, "stable": 0, "recession": -2}
_ROW_KEYS = {
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
}
_ASSUMPTION_KEYS = {
    "market",
    "vara_active",
    "revenue_streams",
    "competent_managers",
    "monopoly",
    "excellent_accounting",
    "rapid_expansion",
}
_EXPECTED_INCLUDED = {
    "agricultural-shelter-zones": {
        "name": "Agricultural Shelter Zones",
        "sector": "Agriculture",
        "employees": 8,
        "monthly_revenue_gp": "1500",
        "monthly_cost_gp": "1050",
        "capital_invested_gp": "6000",
        "source_id": "shelters",
    },
    "blacklake-aquaculture": {
        "name": "Blacklake Aquaculture (7 pools)",
        "sector": "Aquaculture",
        "employees": 15,
        "monthly_revenue_gp": "7500",
        "monthly_cost_gp": "5850",
        "capital_invested_gp": "40000",
        "source_id": "blacklake",
    },
    "converted-quarry-aquaculture": {
        "name": "Converted Quarry Aquaculture (5 sites)",
        "sector": "Aquaculture",
        "employees": 20,
        "monthly_revenue_gp": "12500",
        "monthly_cost_gp": "9750",
        "capital_invested_gp": "35000",
        "source_id": "converted-quarry",
    },
    "bg-aquaculture": {
        "name": "BG Aquaculture Pools (3 sites)",
        "sector": "Aquaculture",
        "employees": 12,
        "monthly_revenue_gp": "3333",
        "monthly_cost_gp": "2600",
        "capital_invested_gp": "22000",
        "source_id": "bg-pools",
    },
    "reservoir-fisheries": {
        "name": "Reservoir Fisheries",
        "sector": "Aquaculture",
        "employees": 8,
        "monthly_revenue_gp": "1667",
        "monthly_cost_gp": "1300",
        "capital_invested_gp": "8000",
        "source_id": "reservoir-fisheries",
    },
}
_EXPECTED_EXCLUDED = {
    "orchard-chapel": {
        "name": "Orchard Chapel",
        "sector": "Agriculture",
        "status": "Operational",
        "as_of": "1498 DR",
        "source_id": "orchard-chapel",
        "reason": "later_1498_reference_not_part_of_eleint_1494_baseline",
    },
    "lobster-king": {
        "name": "Lobster King Operations (Baen-Allied)",
        "sector": "Aquaculture",
        "status": "Unconfirmed",
        "as_of": "Eleint 20, 1494",
        "source_id": "lobster-king-registry",
        "reason": "unconfirmed_registry_row",
    },
}
_EXPECTED_TOTALS = {
    "entity_count": 5,
    "staff": 63,
    "monthly_revenue_gp": Decimal("26500"),
    "monthly_cost_gp": Decimal("20550"),
    "monthly_net_gp": Decimal("5950"),
    "capital_invested_gp": Decimal("111000"),
}
_REVENUE_FACTORS = {
    "critical_success": Decimal("1.25"),
    "success_by_5_plus": Decimal("1.15"),
    "success": Decimal("1.05"),
    "exact_target": Decimal("1.00"),
    "failure": Decimal("0.90"),
    "failure_by_5_plus": Decimal("0.80"),
    "critical_failure": Decimal("0.70"),
}
_EXPENSE_FACTORS = {
    "critical_success": Decimal("0.90"),
    "success_by_5_plus": Decimal("1.00"),
    "success": Decimal("1.05"),
    # The expense table has no separate exact row.  Exact target is an
    # ordinary GURPS success and therefore receives the table's +5% result.
    "exact_target": Decimal("1.05"),
    "failure": Decimal("1.15"),
    "failure_by_5_plus": Decimal("1.15"),
    "critical_failure": Decimal("1.25"),
}
_FACTOR_EFFECTS = {
    "revenue": {
        "critical_success": "+25% revenue; opportunity remains ungenerated",
        "success_by_5_plus": "+15% revenue",
        "success": "+5% revenue",
        "exact_target": "revenue as projected",
        "failure": "-10% revenue",
        "failure_by_5_plus": "-20% revenue; complication remains ungenerated",
        "critical_failure": "-30% revenue; crisis remains ungenerated",
    },
    "expense": {
        "critical_success": "-10% cost; efficiency found",
        "success_by_5_plus": "cost as projected",
        "success": "+5% cost",
        "exact_target": "+5% cost (ordinary success under the expense table)",
        "failure": "+15% cost",
        "failure_by_5_plus": "+15% cost (no separate table row)",
        "critical_failure": "+25% cost; embezzlement consequence remains ungenerated",
    },
}


class FoodSectorError(ValueError):
    """Raised when canon input or preview instructions fail closed."""


def load_food_sector_baseline(
    fixture_path: Path = DEFAULT_CANON_PATH,
) -> dict[str, object]:
    """Load and validate the five-row Registry food baseline."""

    if not isinstance(fixture_path, Path):
        raise FoodSectorError("agriculture canon path must be a concrete Path")
    try:
        fixture_bytes = fixture_path.read_bytes()
        raw = json.loads(fixture_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FoodSectorError(f"cannot read agriculture canon fixture: {exc}") from exc
    if not isinstance(raw, dict):
        raise FoodSectorError("agriculture canon fixture must be an object")
    if raw.get("schema") != "tnp.economy.agriculture-canon/1":
        raise FoodSectorError("agriculture canon fixture schema is unsupported")
    safety = raw.get("safety")
    if (
        not isinstance(safety, dict)
        or safety.get("notion_writes") != 0
        or safety.get("canonical_ledger_postings") != 0
        or safety.get("dice_rolled") != 0
        or safety.get("campaign_time_advanced") is not False
    ):
        raise FoodSectorError("agriculture canon fixture is not a read-only source")

    sources = raw.get("sources")
    if not isinstance(sources, list):
        raise FoodSectorError("agriculture canon fixture sources must be an array")
    source_ids: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise FoodSectorError("agriculture canon source must be an object")
        source_id = _clean_text(source.get("source_id"), "source ID")
        if source_id in source_ids:
            raise FoodSectorError("agriculture canon repeats a source ID")
        source_ids.add(source_id)

    registry_rows = raw.get("registry_entities")
    if not isinstance(registry_rows, list) or len(registry_rows) != 7:
        raise FoodSectorError("agriculture canon must contain exactly seven food rows")
    by_id: dict[str, Mapping[str, object]] = {}
    ordered_ids: list[str] = []
    for index, row in enumerate(registry_rows, start=1):
        if not isinstance(row, dict) or set(row) != _ROW_KEYS:
            raise FoodSectorError(f"food Registry row {index} does not match its schema")
        entity_id = _clean_text(row.get("entity_id"), "food entity ID")
        if entity_id in by_id:
            raise FoodSectorError("agriculture canon repeats a food entity ID")
        if row.get("sector") not in SECTORS:
            raise FoodSectorError("agriculture canon food row has an unsupported sector")
        if row.get("source_id") not in source_ids:
            raise FoodSectorError(f"food row source is missing: {entity_id}")
        by_id[entity_id] = row
        ordered_ids.append(entity_id)
    expected_ids = set(_EXPECTED_INCLUDED) | set(_EXPECTED_EXCLUDED)
    if set(by_id) != expected_ids:
        raise FoodSectorError("agriculture canon food row identities have drifted")

    entities: list[dict[str, object]] = []
    for entity_id in ordered_ids:
        if entity_id not in _EXPECTED_INCLUDED:
            continue
        row = by_id[entity_id]
        expected = _EXPECTED_INCLUDED[entity_id]
        for field, expected_value in expected.items():
            if row.get(field) != expected_value:
                raise FoodSectorError(f"confirmed food row drifted: {entity_id}.{field}")
        if row.get("status") != "Operational" or row.get("as_of") != "Eleint 20, 1494":
            raise FoodSectorError(f"confirmed food row is not the dated baseline: {entity_id}")
        staff = _staff(row.get("employees"), f"{entity_id} employees")
        revenue = _source_decimal(row.get("monthly_revenue_gp"), entity_id, "revenue")
        cost = _source_decimal(row.get("monthly_cost_gp"), entity_id, "cost")
        capital = _source_decimal(row.get("capital_invested_gp"), entity_id, "capital")
        entities.append(
            {
                "entity_id": entity_id,
                "name": row["name"],
                "sector": row["sector"],
                "status": row["status"],
                "as_of": row["as_of"],
                "staff": staff,
                "monthly_revenue_gp": canonical_decimal(revenue),
                "monthly_cost_gp": canonical_decimal(cost),
                "monthly_net_gp": canonical_decimal(_difference(revenue, cost)),
                "capital_invested_gp": canonical_decimal(capital),
                "source_id": row["source_id"],
            }
        )

    excluded: list[dict[str, object]] = []
    for entity_id in ordered_ids:
        if entity_id not in _EXPECTED_EXCLUDED:
            continue
        row = by_id[entity_id]
        expected = _EXPECTED_EXCLUDED[entity_id]
        for field in ("name", "sector", "status", "as_of", "source_id"):
            if row.get(field) != expected[field]:
                raise FoodSectorError(f"excluded food row drifted: {entity_id}.{field}")
        if entity_id == "orchard-chapel":
            if any(
                row.get(field) is not None
                for field in (
                    "employees",
                    "monthly_revenue_gp",
                    "monthly_cost_gp",
                    "capital_invested_gp",
                )
            ):
                raise FoodSectorError("Orchard Chapel 1498 values cannot enter the baseline")
        elif any(
            row.get(field) != expected_value
            for field, expected_value in (
                ("employees", 0),
                ("monthly_revenue_gp", "0"),
                ("monthly_cost_gp", "0"),
                ("capital_invested_gp", "0"),
            )
        ):
            raise FoodSectorError("unconfirmed Lobster King row has drifted")
        excluded.append(
            {
                "entity_id": entity_id,
                "name": row["name"],
                "sector": row["sector"],
                "status": row["status"],
                "as_of": row["as_of"],
                "reason": expected["reason"],
            }
        )

    totals = _entity_totals(entities)
    _validate_expected_totals(totals)
    return {
        "schema": FOOD_SECTOR_BASELINE_SCHEMA,
        "authority": "observed_operating_state",
        "as_of": "Eleint 20, 1494",
        "source_binding": {
            "fixture_schema": raw["schema"],
            "fixture_name": fixture_path.name,
            "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
            "retrieved_on": raw.get("retrieved_on"),
            "notion_access": raw.get("notion_access"),
        },
        "entities": entities,
        "excluded_entities": excluded,
        "totals": _serialize_totals(totals),
        "safety": {
            "read_only": True,
            "notion_writes": 0,
            "canonical_ledger_postings": 0,
            "campaign_time_advanced": False,
        },
    }


def preview_food_sector_month(
    *,
    month_label: str,
    fixture_path: Path = DEFAULT_CANON_PATH,
    seed: str | None = None,
    supplied_faces: Mapping[str, Mapping[str, Sequence[int]]] | None = None,
    sector_assumptions: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, object]:
    """Resolve one visible revenue and expense roll for each food sector.

    Exactly one dice source is required: caller-supplied faces or a non-empty
    deterministic seed.  The returned faces drive only this non-canonical
    preview.
    """

    month = _clean_text(month_label, "month label")
    if (seed is None) == (supplied_faces is None):
        raise FoodSectorError("provide exactly one of deterministic seed or supplied faces")
    baseline = load_food_sector_baseline(fixture_path)
    entities = baseline["entities"]
    if not isinstance(entities, list):  # Defensive guard for internal drift.
        raise FoodSectorError("food baseline entities are malformed")
    assumptions = _normalize_assumptions(sector_assumptions, entities)
    fixture_hash = str(baseline["source_binding"]["fixture_sha256"])

    if seed is not None:
        clean_seed = _clean_text(seed, "deterministic seed")
        method = "hmac_sha256_seeded_preview"
        seed_fingerprint: str | None = hashlib.sha256(
            clean_seed.encode("utf-8")
        ).hexdigest()
        face_map = {
            sector: {
                check: [
                    _seeded_die(
                        seed=clean_seed,
                        coordinate=(
                            FOOD_SECTOR_PREVIEW_SCHEMA,
                            fixture_hash,
                            month,
                            sector,
                            check,
                            str(index),
                        ),
                    )
                    for index in range(1, 4)
                ]
                for check in CHECKS
            }
            for sector in SECTORS
        }
    else:
        method = "caller_supplied_faces"
        seed_fingerprint = None
        face_map = _validate_supplied_faces(supplied_faces)

    sector_results: dict[str, object] = {}
    for sector in SECTORS:
        sector_entities = [entity for entity in entities if entity["sector"] == sector]
        baseline_totals = _entity_totals(sector_entities)
        revenue_modifiers = _revenue_modifiers(assumptions[sector])
        expense_modifiers = _expense_modifiers(
            assumptions[sector], int(baseline_totals["staff"])
        )
        revenue_roll = _roll_receipt(
            check="revenue",
            skill="Merchant",
            base_target=15,
            modifiers=revenue_modifiers,
            faces=face_map[sector]["revenue"],
            method=method,
            seed_fingerprint=seed_fingerprint,
        )
        expense_roll = _roll_receipt(
            check="expense",
            skill="Administration",
            base_target=16,
            modifiers=expense_modifiers,
            faces=face_map[sector]["expense"],
            method=method,
            seed_fingerprint=seed_fingerprint,
        )
        revenue_factor = Decimal(str(revenue_roll["factor"]))
        expense_factor = Decimal(str(expense_roll["factor"]))
        resolved_entities: list[dict[str, object]] = []
        with localcontext(_decimal_context()):
            for entity in sector_entities:
                source_revenue = Decimal(str(entity["monthly_revenue_gp"]))
                source_cost = Decimal(str(entity["monthly_cost_gp"]))
                proposed_revenue = _money(source_revenue * revenue_factor)
                proposed_cost = _money(source_cost * expense_factor)
                resolved_entities.append(
                    {
                        **entity,
                        "revenue_factor": canonical_decimal(revenue_factor),
                        "expense_factor": canonical_decimal(expense_factor),
                        "preview_revenue_gp": canonical_decimal(proposed_revenue),
                        "preview_cost_gp": canonical_decimal(proposed_cost),
                        "preview_net_gp": canonical_decimal(
                            _money(proposed_revenue - proposed_cost)
                        ),
                    }
                )
        preview_totals = _preview_entity_totals(resolved_entities)
        sector_results[sector] = {
            "sector": sector,
            "assumptions": assumptions[sector],
            "baseline": _serialize_totals(baseline_totals),
            "rolls": {
                "revenue": revenue_roll,
                "expense": expense_roll,
            },
            "entities": resolved_entities,
            "preview": _serialize_preview_totals(preview_totals),
        }

    overall_preview = _sum_sector_previews(sector_results)
    safety = {
        "canonical": False,
        "campaign_time_advanced": False,
        "campaign_state_rolls_resolved": 0,
        "preview_roll_receipts": 4,
        "notion_read_only": True,
        "notion_write_capability": False,
        "notion_writes": 0,
        "ledger_write_capability": False,
        "ledger_transactions": 0,
        "ledger_postings": 0,
    }
    dice_source = {
        "method": method,
        "seed_fingerprint": seed_fingerprint,
        "all_faces_disclosed": True,
    }
    body: dict[str, object] = {
        "schema": FOOD_SECTOR_PREVIEW_SCHEMA,
        "mode": "preview",
        "canonical": False,
        "authority": "scenario_assumption",
        "month_label": month,
        "campaign_time_advanced": False,
        "source_binding": baseline["source_binding"],
        "baseline": baseline["totals"],
        "excluded_entities": baseline["excluded_entities"],
        "dice_source": dice_source,
        "sectors": sector_results,
        "preview_totals": _serialize_preview_totals(overall_preview),
        "safety": safety,
        "decision_brief": {
            "Source": {
                "authority": baseline["authority"],
                "as_of": baseline["as_of"],
                "fixture_sha256": baseline["source_binding"]["fixture_sha256"],
                "included_entity_ids": [entity["entity_id"] for entity in entities],
                "excluded_entities": baseline["excluded_entities"],
                "baseline": baseline["totals"],
            },
            "Assumption": {
                "month_label": month,
                "sector_assumptions": assumptions,
                "dice_source": dice_source,
                "binding_scope": "this non-canonical preview only",
            },
            "Derived": {
                "sector_factors": {
                    sector: {
                        "revenue_factor": sector_results[sector]["rolls"]["revenue"]["factor"],
                        "expense_factor": sector_results[sector]["rolls"]["expense"]["factor"],
                    }
                    for sector in SECTORS
                },
                "preview_totals": _serialize_preview_totals(overall_preview),
            },
            "Unknown": {
                "physical_production": "not resolved by this financial preview",
                "canonical_acceptance": "not granted",
                "campaign_date_advance": "not resolved; month label is scenario text only",
                "opportunity_complication_details": "not generated by this focused engine",
            },
        },
        "warnings": [
            "This result is a non-canonical financial preview.",
            "No campaign time was advanced.",
            "No Notion or canonical ledger write capability is present.",
        ],
    }
    body["content_hash"] = canonical_hash(body)
    validate_food_sector_preview(body)
    return body


def validate_food_sector_preview(preview: object) -> None:
    """Validate the preview's visible dice, arithmetic, and write barriers."""

    if not isinstance(preview, dict):
        raise FoodSectorError("food-sector preview must be an object")
    expected_keys = {
        "schema",
        "mode",
        "canonical",
        "authority",
        "month_label",
        "campaign_time_advanced",
        "source_binding",
        "baseline",
        "excluded_entities",
        "dice_source",
        "sectors",
        "preview_totals",
        "safety",
        "decision_brief",
        "warnings",
        "content_hash",
    }
    if set(preview) != expected_keys:
        raise FoodSectorError("food-sector preview keys do not match the schema")
    body = dict(preview)
    supplied_hash = body.pop("content_hash")
    if supplied_hash != canonical_hash(body):
        raise FoodSectorError("food-sector preview content hash does not match")
    if (
        preview["schema"] != FOOD_SECTOR_PREVIEW_SCHEMA
        or preview["mode"] != "preview"
        or preview["canonical"] is not False
        or preview["authority"] != "scenario_assumption"
        or preview["campaign_time_advanced"] is not False
    ):
        raise FoodSectorError("food-sector preview authority flags are inconsistent")
    if set(preview["decision_brief"]) != {"Source", "Assumption", "Derived", "Unknown"}:
        raise FoodSectorError("food-sector decision brief classifications drifted")
    safety = preview["safety"]
    if (
        not isinstance(safety, dict)
        or safety.get("canonical") is not False
        or safety.get("campaign_time_advanced") is not False
        or safety.get("campaign_state_rolls_resolved") != 0
        or safety.get("preview_roll_receipts") != 4
        or safety.get("notion_write_capability") is not False
        or safety.get("notion_writes") != 0
        or safety.get("ledger_write_capability") is not False
        or safety.get("ledger_transactions") != 0
        or safety.get("ledger_postings") != 0
    ):
        raise FoodSectorError("food-sector preview write barriers are inconsistent")
    baseline = _parse_total_mapping(preview["baseline"], "overall baseline")
    _validate_expected_totals(baseline)
    sectors = preview["sectors"]
    if not isinstance(sectors, dict) or tuple(sectors) != SECTORS:
        raise FoodSectorError("food-sector preview must contain both sectors once")
    for sector in SECTORS:
        result = sectors[sector]
        if not isinstance(result, dict) or result.get("sector") != sector:
            raise FoodSectorError("food-sector result identity is malformed")
        rolls = result.get("rolls")
        if not isinstance(rolls, dict) or tuple(rolls) != CHECKS:
            raise FoodSectorError("food-sector result must have one revenue and expense roll")
        expected_roll_specs = {
            "revenue": ("Merchant", 15, _REVENUE_FACTORS),
            "expense": ("Administration", 16, _EXPENSE_FACTORS),
        }
        for check, (skill, base_target, factors) in expected_roll_specs.items():
            roll = rolls[check]
            if not isinstance(roll, dict):
                raise FoodSectorError("food-sector roll receipt is malformed")
            faces = roll.get("faces")
            modifiers = roll.get("modifiers")
            if (
                roll.get("check") != check
                or roll.get("skill") != skill
                or roll.get("base_target") != base_target
                or not _valid_faces(faces)
                or not isinstance(modifiers, list)
            ):
                raise FoodSectorError("food-sector roll identity or faces are malformed")
            modifier_total = 0
            for modifier in modifiers:
                if (
                    not isinstance(modifier, dict)
                    or set(modifier) != {"label", "value"}
                    or not isinstance(modifier["label"], str)
                    or type(modifier["value"]) is not int
                ):
                    raise FoodSectorError("food-sector modifier receipt is malformed")
                modifier_total += modifier["value"]
            total = sum(faces)
            target = base_target + modifier_total
            margin = target - total
            outcome = classify_3d6(total=total, effective_target=target)
            if (
                roll.get("total") != total
                or roll.get("modifier_total") != modifier_total
                or roll.get("effective_target") != target
                or roll.get("margin") != margin
                or roll.get("outcome") != outcome
                or roll.get("factor") != canonical_decimal(factors[outcome])
            ):
                raise FoodSectorError("food-sector roll arithmetic is inconsistent")
        entities = result.get("entities")
        if not isinstance(entities, list) or not entities:
            raise FoodSectorError("food-sector result has no entities")
        revenue_factor = Decimal(str(rolls["revenue"]["factor"]))
        expense_factor = Decimal(str(rolls["expense"]["factor"]))
        for entity in entities:
            if not isinstance(entity, dict) or entity.get("sector") != sector:
                raise FoodSectorError("food-sector entity is malformed")
            with localcontext(_decimal_context()):
                expected_revenue = _money(
                    Decimal(str(entity["monthly_revenue_gp"])) * revenue_factor
                )
                expected_cost = _money(
                    Decimal(str(entity["monthly_cost_gp"])) * expense_factor
                )
                expected_net = _money(expected_revenue - expected_cost)
            if (
                entity.get("revenue_factor") != canonical_decimal(revenue_factor)
                or entity.get("expense_factor") != canonical_decimal(expense_factor)
                or entity.get("preview_revenue_gp") != canonical_decimal(expected_revenue)
                or entity.get("preview_cost_gp") != canonical_decimal(expected_cost)
                or entity.get("preview_net_gp") != canonical_decimal(expected_net)
            ):
                raise FoodSectorError("sector roll was not applied consistently to every entity")
        expected_sector_preview = _preview_entity_totals(entities)
        if result.get("preview") != _serialize_preview_totals(expected_sector_preview):
            raise FoodSectorError("food-sector preview totals do not reconcile")
    expected_overall = _sum_sector_previews(sectors)
    if preview["preview_totals"] != _serialize_preview_totals(expected_overall):
        raise FoodSectorError("overall food-sector preview totals do not reconcile")


def revenue_factor(outcome: str) -> Decimal:
    """Return the exact hybrid-business sector revenue factor."""

    try:
        return _REVENUE_FACTORS[outcome]
    except (KeyError, TypeError) as exc:
        raise FoodSectorError(f"unsupported revenue outcome: {outcome}") from exc


def expense_factor(outcome: str) -> Decimal:
    """Return the exact hybrid-business sector expense factor."""

    try:
        return _EXPENSE_FACTORS[outcome]
    except (KeyError, TypeError) as exc:
        raise FoodSectorError(f"unsupported expense outcome: {outcome}") from exc


def _normalize_assumptions(
    supplied: Mapping[str, Mapping[str, object]] | None,
    entities: Sequence[Mapping[str, object]],
) -> dict[str, dict[str, object]]:
    if supplied is not None and not isinstance(supplied, Mapping):
        raise FoodSectorError("sector assumptions must be an object")
    if supplied is not None and any(sector not in SECTORS for sector in supplied):
        raise FoodSectorError("sector assumptions contain an unknown sector")
    result: dict[str, dict[str, object]] = {}
    for sector in SECTORS:
        entity_count = sum(entity.get("sector") == sector for entity in entities)
        values: dict[str, object] = {
            "market": "stable",
            "vara_active": True,
            # Each independently reported Registry operation is treated as one
            # sector revenue stream unless the caller supplies another count.
            "revenue_streams": entity_count,
            "competent_managers": 0,
            "monopoly": False,
            "excellent_accounting": False,
            "rapid_expansion": False,
        }
        overrides = supplied.get(sector, {}) if supplied is not None else {}
        if not isinstance(overrides, Mapping):
            raise FoodSectorError(f"{sector} assumptions must be an object")
        if any(key not in _ASSUMPTION_KEYS for key in overrides):
            raise FoodSectorError(f"{sector} assumptions contain an unknown field")
        values.update(overrides)
        if values["market"] not in _MARKET_MODIFIERS:
            raise FoodSectorError("market must be boom, stable, or recession")
        for key in (
            "vara_active",
            "monopoly",
            "excellent_accounting",
            "rapid_expansion",
        ):
            if type(values[key]) is not bool:
                raise FoodSectorError(f"{sector} {key} must be a boolean")
        streams = values["revenue_streams"]
        managers = values["competent_managers"]
        if type(streams) is not int or streams < 1:
            raise FoodSectorError("revenue_streams must be a positive integer")
        if type(managers) is not int or not 0 <= managers <= 3:
            raise FoodSectorError("competent_managers must be from 0 through 3")
        result[sector] = values
    return result


def _revenue_modifiers(assumptions: Mapping[str, object]) -> list[dict[str, object]]:
    market = str(assumptions["market"])
    streams = int(assumptions["revenue_streams"])
    if streams >= 7:
        stream_label, stream_value = "7+ revenue streams", 2
    elif streams >= 4:
        stream_label, stream_value = "4-6 revenue streams", 1
    else:
        stream_label, stream_value = "1-3 revenue streams", 0
    return [
        {"label": f"Market {market}", "value": _MARKET_MODIFIERS[market]},
        {"label": stream_label, "value": stream_value},
        {
            "label": "Vara active",
            "value": 3 if assumptions["vara_active"] is True else 0,
        },
        {
            "label": "Competent managers (maximum +3)",
            "value": int(assumptions["competent_managers"]),
        },
        {
            "label": "Monopoly position",
            "value": 2 if assumptions["monopoly"] is True else 0,
        },
    ]


def _expense_modifiers(
    assumptions: Mapping[str, object], staff: int
) -> list[dict[str, object]]:
    size_modifier, size_band = _staff_size_modifier(staff)
    return [
        {"label": f"Sector staff size ({staff}; {size_band})", "value": size_modifier},
        {
            "label": "Excellent accounting",
            "value": 2 if assumptions["excellent_accounting"] is True else 0,
        },
        {
            "label": "Rapid expansion",
            "value": -3 if assumptions["rapid_expansion"] is True else 0,
        },
    ]


def _staff_size_modifier(staff: int) -> tuple[int, str]:
    if type(staff) is not int or staff < 0:
        raise FoodSectorError("sector staff must be a non-negative integer")
    # The source table overlaps at exactly 200 and 1000.  No current food
    # sector lies on either boundary, and the engine refuses to invent a ruling.
    if staff in {200, 1000}:
        raise FoodSectorError(f"sector staff boundary {staff} is ambiguous in the rules")
    if staff < 50:
        return 2, "below 50"
    if staff < 200:
        return 0, "50-200"
    if staff < 1000:
        return -2, "200-1000"
    return -4, "1000+"


def _roll_receipt(
    *,
    check: str,
    skill: str,
    base_target: int,
    modifiers: Sequence[Mapping[str, object]],
    faces: Sequence[int],
    method: str,
    seed_fingerprint: str | None,
) -> dict[str, object]:
    visible_faces = list(faces)
    if not _valid_faces(visible_faces):
        raise FoodSectorError("3d6 receipt must contain exactly three faces from 1 to 6")
    modifier_total = sum(int(modifier["value"]) for modifier in modifiers)
    total = sum(visible_faces)
    effective_target = base_target + modifier_total
    margin = effective_target - total
    outcome = classify_3d6(total=total, effective_target=effective_target)
    factor = revenue_factor(outcome) if check == "revenue" else expense_factor(outcome)
    return {
        "check": check,
        "skill": skill,
        "base_target": base_target,
        "faces": visible_faces,
        "total": total,
        "modifiers": [dict(modifier) for modifier in modifiers],
        "modifier_total": modifier_total,
        "effective_target": effective_target,
        "margin": margin,
        "outcome": outcome,
        "factor": canonical_decimal(factor),
        "factor_effect": _FACTOR_EFFECTS[check][outcome],
        "method": method,
        "seed_fingerprint": seed_fingerprint,
        "binding_scope": "this non-canonical preview only",
    }


def _validate_supplied_faces(
    supplied: Mapping[str, Mapping[str, Sequence[int]]] | None,
) -> dict[str, dict[str, list[int]]]:
    if not isinstance(supplied, Mapping) or set(supplied) != set(SECTORS):
        raise FoodSectorError("supplied faces must contain Agriculture and Aquaculture")
    result: dict[str, dict[str, list[int]]] = {}
    for sector in SECTORS:
        checks = supplied[sector]
        if not isinstance(checks, Mapping) or set(checks) != set(CHECKS):
            raise FoodSectorError(f"{sector} faces must contain revenue and expense")
        result[sector] = {}
        for check in CHECKS:
            faces = checks[check]
            if not _valid_faces(faces):
                raise FoodSectorError(
                    f"{sector} {check} must contain three integer faces from 1 to 6"
                )
            result[sector][check] = list(faces)
    return result


def _valid_faces(value: object) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 3
        and all(type(face) is int and 1 <= face <= 6 for face in value)
    )


def _seeded_die(*, seed: str, coordinate: tuple[str, ...]) -> int:
    """Generate a stable unbiased d6 from an explicit seed and coordinate."""

    modulus = 1 << 64
    limit = modulus - (modulus % 6)
    key = hashlib.sha256(seed.encode("utf-8")).digest()
    message = "\x1f".join(coordinate).encode("utf-8")
    attempt = 0
    while True:
        digest = hmac.new(
            key,
            message + b"\x1f" + str(attempt).encode("ascii"),
            hashlib.sha256,
        ).digest()
        sample = int.from_bytes(digest[:8], "big")
        if sample < limit:
            return (sample % 6) + 1
        attempt += 1


def _source_decimal(value: object, entity_id: str, label: str) -> Decimal:
    if not isinstance(value, str) or not value:
        raise FoodSectorError(f"{entity_id} {label} must be exact decimal text")
    try:
        result = Decimal(value)
    except Exception as exc:
        raise FoodSectorError(f"{entity_id} {label} is malformed") from exc
    if not result.is_finite() or result < 0:
        raise FoodSectorError(f"{entity_id} {label} must be finite and non-negative")
    return result


def _staff(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise FoodSectorError(f"{label} must be a non-negative integer")
    return value


def _entity_totals(entities: Sequence[Mapping[str, object]]) -> dict[str, object]:
    with localcontext(_decimal_context()):
        revenue = sum(
            (Decimal(str(entity["monthly_revenue_gp"])) for entity in entities),
            Decimal("0"),
        )
        cost = sum(
            (Decimal(str(entity["monthly_cost_gp"])) for entity in entities),
            Decimal("0"),
        )
        capital = sum(
            (Decimal(str(entity["capital_invested_gp"])) for entity in entities),
            Decimal("0"),
        )
        net = revenue - cost
    return {
        "entity_count": len(entities),
        "staff": sum(int(entity["staff"]) for entity in entities),
        "monthly_revenue_gp": revenue,
        "monthly_cost_gp": cost,
        "monthly_net_gp": net,
        "capital_invested_gp": capital,
    }


def _preview_entity_totals(
    entities: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    with localcontext(_decimal_context()):
        revenue = sum(
            (Decimal(str(entity["preview_revenue_gp"])) for entity in entities),
            Decimal("0"),
        )
        cost = sum(
            (Decimal(str(entity["preview_cost_gp"])) for entity in entities),
            Decimal("0"),
        )
        capital = sum(
            (Decimal(str(entity["capital_invested_gp"])) for entity in entities),
            Decimal("0"),
        )
        net = revenue - cost
    return {
        "entity_count": len(entities),
        "staff": sum(int(entity["staff"]) for entity in entities),
        "monthly_revenue_gp": revenue,
        "monthly_cost_gp": cost,
        "monthly_net_gp": net,
        "capital_invested_gp": capital,
    }


def _sum_sector_previews(sectors: Mapping[str, object]) -> dict[str, object]:
    parsed = [
        _parse_preview_total_mapping(sectors[sector]["preview"], f"{sector} preview")
        for sector in SECTORS
    ]
    with localcontext(_decimal_context()):
        revenue = sum(
            (Decimal(str(item["monthly_revenue_gp"])) for item in parsed), Decimal("0")
        )
        cost = sum(
            (Decimal(str(item["monthly_cost_gp"])) for item in parsed), Decimal("0")
        )
        capital = sum(
            (Decimal(str(item["capital_invested_gp"])) for item in parsed), Decimal("0")
        )
        net = revenue - cost
    return {
        "entity_count": sum(int(item["entity_count"]) for item in parsed),
        "staff": sum(int(item["staff"]) for item in parsed),
        "monthly_revenue_gp": revenue,
        "monthly_cost_gp": cost,
        "monthly_net_gp": net,
        "capital_invested_gp": capital,
    }


def _serialize_totals(totals: Mapping[str, object]) -> dict[str, object]:
    return {
        "entity_count": int(totals["entity_count"]),
        "staff": int(totals["staff"]),
        "monthly_revenue_gp": canonical_decimal(Decimal(totals["monthly_revenue_gp"])),
        "monthly_cost_gp": canonical_decimal(Decimal(totals["monthly_cost_gp"])),
        "monthly_net_gp": canonical_decimal(Decimal(totals["monthly_net_gp"])),
        "capital_invested_gp": canonical_decimal(Decimal(totals["capital_invested_gp"])),
    }


def _serialize_preview_totals(totals: Mapping[str, object]) -> dict[str, object]:
    return _serialize_totals(totals)


def _parse_total_mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != set(_EXPECTED_TOTALS):
        raise FoodSectorError(f"{label} is malformed")
    try:
        parsed = {
            "entity_count": value["entity_count"],
            "staff": value["staff"],
            "monthly_revenue_gp": Decimal(str(value["monthly_revenue_gp"])),
            "monthly_cost_gp": Decimal(str(value["monthly_cost_gp"])),
            "monthly_net_gp": Decimal(str(value["monthly_net_gp"])),
            "capital_invested_gp": Decimal(str(value["capital_invested_gp"])),
        }
    except Exception as exc:
        raise FoodSectorError(f"{label} contains malformed decimals") from exc
    if type(parsed["entity_count"]) is not int or type(parsed["staff"]) is not int:
        raise FoodSectorError(f"{label} counts must be integers")
    return parsed


def _parse_preview_total_mapping(value: object, label: str) -> dict[str, object]:
    return _parse_total_mapping(value, label)


def _validate_expected_totals(totals: Mapping[str, object]) -> None:
    if any(totals[key] != expected for key, expected in _EXPECTED_TOTALS.items()):
        raise FoodSectorError("confirmed food baseline does not reconcile to canonical totals")


def _money(value: Decimal) -> Decimal:
    with localcontext(_decimal_context()):
        return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _difference(left: Decimal, right: Decimal) -> Decimal:
    with localcontext(_decimal_context()):
        return left - right


def _decimal_context() -> Context:
    return Context(prec=64, rounding=ROUND_HALF_UP)


def _clean_text(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or _CONTROL_RE.search(value)
    ):
        raise FoodSectorError(f"{label} must be non-empty clean text")
    return value
