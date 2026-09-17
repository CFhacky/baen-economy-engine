"""End-to-end non-canonical Baen Empire month orchestration.

The Baen whole-economy model remains the authority/reconciliation layer.  This
module rebases source-backed facts before execution, runs one complete month,
then (when the pinned products are available) executes the real upstream product
boundaries as cross-check/subsystem evidence.  No product default is promoted to
campaign canon merely because it executes.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal, ROUND_FLOOR
import json
import os
from pathlib import Path
from typing import Any, Mapping

from . import whole_economy
from .brunnfeld_sidecar import BrunnfeldServiceClient
from .freecol_product import run_freecol_production_info
from .mesa_runtime import MesaProductEvent, mesa_available, run_mesa_preview
from .openttd_product import OpenTTDAdminClient
from .unknown_horizons_product import run_unknown_horizons_production_line
from .veloren_product import run_veloren_economy


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CENSUS = PROJECT_ROOT / "recovery/LIVE_EMPIRE_SOURCE_CENSUS_EXECUTION_2026-09-17.json"
DEFAULT_SCENARIO = PROJECT_ROOT / "fixtures/regional-scenarios/baen-north-whole-economy-v1.json"


class EmpireRunError(ValueError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EmpireRunError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EmpireRunError(f"{path} must contain an object")
    return value


def _census_population(census: Mapping[str, Any]) -> dict[str, Decimal]:
    result: dict[str, Decimal] = {}
    records = census.get("records")
    if not isinstance(records, list):
        raise EmpireRunError("execution census has no records")
    for record in records:
        if not isinstance(record, Mapping) or record.get("sourceClass") != "locations":
            continue
        numbers = record.get("numbers")
        if not isinstance(numbers, Mapping):
            continue
        population = numbers.get("Population")
        if isinstance(population, bool) or not isinstance(population, (int, float)):
            continue
        if population <= 0:
            continue
        title = record.get("title")
        if isinstance(title, str) and title:
            result[title] = Decimal(str(population))
    return result


def _integer_rebalance(values: list[Decimal], target: Decimal) -> list[Decimal]:
    if target != target.to_integral_value() or target < 0:
        raise EmpireRunError("source population must be a non-negative integer")
    if not values or any(v < 0 for v in values):
        raise EmpireRunError("scenario social-class populations are invalid")
    total = sum(values, Decimal("0"))
    if total <= 0:
        raise EmpireRunError("cannot rebase a settlement with zero scenario population")
    target_int = int(target)
    raw = [(v / total) * target for v in values]
    floor = [int(v.to_integral_value(rounding=ROUND_FLOOR)) for v in raw]
    remainder = target_int - sum(floor)
    order = sorted(
        range(len(raw)),
        key=lambda i: (raw[i] - Decimal(floor[i]), -i),
        reverse=True,
    )
    for i in order[:remainder]:
        floor[i] += 1
    return [Decimal(v) for v in floor]


def rebase_scenario(
    scenario: Mapping[str, object],
    census: Mapping[str, Any],
) -> tuple[dict[str, object], list[dict[str, Any]], list[dict[str, Any]]]:
    """Replace only facts the live census actually supplies.

    Class shares remain MODEL-PROPOSED because the census only supplies total
    settlement population. Missing totals remain scenario assumptions and are
    returned as blockers rather than invented.
    """
    result = deepcopy(dict(scenario))
    populations = _census_population(census)
    overrides: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    settlements = result.get("settlements")
    if not isinstance(settlements, list):
        raise EmpireRunError("scenario settlements missing")
    for settlement in settlements:
        if not isinstance(settlement, dict):
            raise EmpireRunError("scenario settlement is not an object")
        name = settlement.get("name")
        classes = settlement.get("classes")
        if not isinstance(name, str) or not isinstance(classes, list) or not classes:
            raise EmpireRunError("scenario settlement lacks name/classes")
        old_values = [Decimal(str(row["population"])) for row in classes]
        source_total = populations.get(name)
        if source_total is None:
            blockers.append({
                "kind": "MISSING_DATA",
                "field": "population_total",
                "settlement": name,
                "retained_value": str(settlement.get("population_total")),
                "provenance": "UNRESOLVED",
                "reason": "live census has no positive current population for this settlement; existing value remains scenario_assumption",
            })
            continue
        new_values = _integer_rebalance(old_values, source_total)
        old_total = sum(old_values, Decimal("0"))
        for row, value in zip(classes, new_values, strict=True):
            row["population"] = value
            row["authority"] = "MODEL-PROPOSED"
            row["canonical"] = False
        settlement["population_total"] = source_total
        settlement["population_authority"] = "SOURCE-DERIVED"
        settlement["class_share_authority"] = "MODEL-PROPOSED"
        settlement["canonical"] = False
        overrides.append({
            "field": "population_total",
            "settlement": name,
            "from": str(old_total),
            "to": str(source_total),
            "provenance": "SOURCE-DERIVED",
            "class_distribution": "MODEL-PROPOSED proportional preservation of the existing preview shares",
        })
    refs = result.get("source_refs")
    if isinstance(refs, list):
        ref = "recovery/LIVE_EMPIRE_SOURCE_CENSUS_EXECUTION_2026-09-17.json"
        if ref not in refs:
            refs.append(ref)
    whole_economy.validate_scenario(result)
    return result, overrides, blockers


def _phase_events(seed: str) -> tuple[MesaProductEvent, ...]:
    phases = (
        ("shocks", "HIGH"), ("arrivals", "DEFAULT"), ("credit", "DEFAULT"),
        ("production", "DEFAULT"), ("storage", "DEFAULT"), ("markets", "DEFAULT"),
        ("obligations", "DEFAULT"), ("debt", "DEFAULT"), ("migration", "LOW"),
    )
    return tuple(
        MesaProductEvent(i, priority, f"baen:{seed}:{name}", {"phase": name})
        for i, (name, priority) in enumerate(phases, 1)
    )


def _commodity_ids(scenario: Mapping[str, object]) -> dict[str, int]:
    commodities = scenario.get("commodities")
    if not isinstance(commodities, list):
        raise EmpireRunError("scenario commodities missing")
    names = sorted(str(row["id"]) for row in commodities if isinstance(row, Mapping))
    return {name: i + 1 for i, name in enumerate(names)}


def _unknown_horizons_check(scenario: Mapping[str, object], checkout: str) -> dict[str, Any]:
    ids = _commodity_ids(scenario)
    recipes = scenario.get("recipes")
    if not isinstance(recipes, list):
        raise EmpireRunError("scenario recipes missing")
    checked = []
    for index, recipe in enumerate(recipes, 1):
        if not isinstance(recipe, Mapping):
            raise EmpireRunError("scenario recipe is not an object")
        outputs = recipe.get("outputs") or {}
        inputs = recipe.get("inputs") or {}
        result = run_unknown_horizons_production_line(
            checkout,
            line_id=index,
            produces=tuple((ids[str(k)], float(Decimal(str(v)))) for k, v in sorted(outputs.items())),
            consumes=tuple((ids[str(k)], -float(Decimal(str(v)))) for k, v in sorted(inputs.items())),
            time=1.0,
        )
        checked.append({
            "recipe_id": recipe.get("id"),
            "line_id": result.line_id,
            "produced": {k: v for k, v in result.produced.items()},
            "consumed": {k: v for k, v in result.consumed.items()},
        })
    return {
        "status": "USED_IN_RUN",
        "provenance": "UPSTREAM-ADOPTED product execution; scenario recipe coefficients remain MODEL-PROPOSED unless source-backed",
        "recipes_checked": len(checked),
        "details": checked,
    }


def _freecol_check(scenario: Mapping[str, object], core_result: Mapping[str, Any], checkout: str) -> dict[str, Any]:
    scale = Decimal("1000")
    actual: dict[str, Decimal] = {}
    for receipt in core_result.get("production", []):
        if not isinstance(receipt, Mapping):
            continue
        outputs = receipt.get("outputs") or {}
        for commodity, amount in outputs.items():
            actual[str(commodity)] = actual.get(str(commodity), Decimal("0")) + Decimal(str(amount))
    maximum: dict[str, Decimal] = {}
    recipes = scenario.get("recipes")
    if not isinstance(recipes, list):
        raise EmpireRunError("scenario recipes missing")
    for recipe in recipes:
        if not isinstance(recipe, Mapping):
            continue
        max_batches = Decimal(str(recipe.get("max_batches")))
        for commodity, per_batch in (recipe.get("outputs") or {}).items():
            key = str(commodity)
            maximum[key] = maximum.get(key, Decimal("0")) + max_batches * Decimal(str(per_batch))
    actual_i = {f"baen.goods.{k}": int((v * scale).to_integral_value()) for k, v in actual.items()}
    maximum_i = {f"baen.goods.{k}": int((v * scale).to_integral_value()) for k, v in maximum.items()}
    result = run_freecol_production_info(checkout, actual=actual_i, maximum=maximum_i)
    return {
        "status": "USED_IN_RUN",
        "scale": 1000,
        "actual": result.actual,
        "maximum": result.maximum,
        "deficits": result.deficits,
        "provenance": "UPSTREAM-ADOPTED actual/max model; Baen quantities scaled by 1000 for integer JVM goods amounts",
    }


def _entity_settlements(scenario: Mapping[str, object]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for recipe in scenario.get("recipes", []):
        if isinstance(recipe, Mapping):
            result.setdefault(str(recipe["entity_id"]), set()).add(str(recipe["settlement_id"]))
    return result


def _veloren_inputs(scenario: Mapping[str, object]) -> list[dict[str, Any]]:
    entity_sites = _entity_settlements(scenario)
    opening = scenario.get("opening_state")
    if not isinstance(opening, Mapping):
        raise EmpireRunError("scenario opening_state missing")
    food: dict[str, Decimal] = {}
    for row in opening.get("inventories", []):
        if not isinstance(row, Mapping) or row.get("commodity_id") not in {"grain", "fish"}:
            continue
        site = str(row.get("settlement_id"))
        food[site] = food.get(site, Decimal("0")) + Decimal(str(row.get("quantity")))
    coin: dict[str, Decimal] = {}
    for row in opening.get("accounts", []):
        if not isinstance(row, Mapping):
            continue
        entity = str(row.get("entity_id"))
        sites: set[str] = set()
        if entity.startswith("households:") or entity.startswith("treasury:"):
            parts = entity.split(":")
            if len(parts) >= 2:
                sites.add(parts[1])
        sites |= entity_sites.get(entity, set())
        # Do not duplicate one ambiguous entity account across several settlements.
        if len(sites) != 1:
            continue
        site = next(iter(sites))
        coin[site] = coin.get(site, Decimal("0")) + Decimal(str(row.get("cash", 0))) + Decimal(str(row.get("deposit", 0)))
    result = []
    for settlement in scenario.get("settlements", []):
        if not isinstance(settlement, Mapping):
            continue
        site = str(settlement["id"])
        result.append({
            "settlement_id": site,
            "name": settlement["name"],
            "population": Decimal(str(settlement["population_total"])),
            "food_stock": food.get(site, Decimal("0")),
            "coin_stock": coin.get(site, Decimal("0")),
            "input_provenance": {
                "population": settlement.get("population_authority", settlement.get("authority", "scenario_assumption")),
                "food_stock": "MODEL-PROPOSED scenario opening inventory",
                "coin_stock": "MODEL-PROPOSED unambiguous scenario account allocation",
            },
        })
    return result


def _veloren_check(scenario: Mapping[str, object], checkout: str) -> dict[str, Any]:
    rows = []
    for source in _veloren_inputs(scenario):
        result = run_veloren_economy(
            checkout,
            population=float(source["population"]),
            food_stock=float(source["food_stock"]),
            coin_stock=float(source["coin_stock"]),
            days=30.0,
            timeout=120.0,
        )
        rows.append({
            "settlement_id": source["settlement_id"],
            "name": source["name"],
            "inputs": {
                "population": str(source["population"]),
                "food_stock": str(source["food_stock"]),
                "coin_stock": str(source["coin_stock"]),
            },
            "input_provenance": source["input_provenance"],
            "veloren_output": asdict(result),
        })
    return {
        "status": "USED_IN_RUN",
        "settlements_checked": len(rows),
        "details": rows,
        "provenance": "UPSTREAM-ADOPTED Veloren economy execution; opening stocks/cash remain explicit scenario assumptions",
    }


def _brunnfeld_check(url: str) -> dict[str, Any]:
    snapshot = BrunnfeldServiceClient(url).snapshot()
    return {
        "status": "CONNECTED_PRODUCT_ONLY",
        "upstream_commit": snapshot.upstream_commit,
        "villages": len(snapshot.villages) if isinstance(snapshot.villages, list) else None,
        "economy_snapshots": len(snapshot.economy) if isinstance(snapshot.economy, list) else None,
        "provenance": "UPSTREAM-ADOPTED runtime boundary; Baen-state import into Brunnfeld is not yet defined",
        "blocker": "Brunnfeld's published generator accepts village/agent counts but not the Baen census state model; do not treat its native world as Empire totals.",
    }


def _openttd_check(host: str, port: int, password: str) -> dict[str, Any]:
    with OpenTTDAdminClient(host, port, password=password, timeout=10.0) as client:
        snapshot = client.snapshot()
    return {
        "status": "CONNECTED_PRODUCT_ONLY",
        "upstream_commit": snapshot.upstream_commit,
        "date": snapshot.current_date,
        "company_economy_records": [asdict(row) for row in snapshot.companies],
        "provenance": "UPSTREAM-ADOPTED runtime boundary; Baen route-state injection is not exposed by the admin protocol",
        "blocker": "OpenTTD admin API reports economy state but does not create Baen routes/vehicles; Baen core route model remains active until a source-mapped product adapter exists.",
    }


def run_empire_month(
    *,
    seed: str,
    census_path: Path = DEFAULT_CENSUS,
    scenario_path: Path = DEFAULT_SCENARIO,
    require_products: bool = False,
) -> dict[str, Any]:
    if not seed:
        raise EmpireRunError("seed is required")
    census = _load_json(census_path)
    scenario = whole_economy.load_scenario(scenario_path)
    rebased, overrides, blockers = rebase_scenario(scenario, census)
    opening = whole_economy.initial_state(rebased)
    month = whole_economy.run_month(rebased, opening, seed)
    result = month["result"]
    products: dict[str, Any] = {}

    if mesa_available():
        mesa = run_mesa_preview(_phase_events(seed), until_tick=9, seed=17)
        products["mesa"] = {
            "status": "USED_IN_RUN",
            "upstream_commit": mesa.upstream_commit,
            "final_time": mesa.final_time,
            "executed_events": list(mesa.executed_events),
            "provenance": "UPSTREAM-ADOPTED event runtime; phase definitions are Baen engine phases",
        }
    else:
        products["mesa"] = {"status": "UNAVAILABLE", "blocker": "pinned Mesa requires Python 3.12 and the optional dependency"}
        if require_products:
            raise EmpireRunError(products["mesa"]["blocker"])

    uh = os.environ.get("UNKNOWN_HORIZONS_CHECKOUT")
    if uh:
        products["unknown_horizons"] = _unknown_horizons_check(rebased, uh)
    else:
        products["unknown_horizons"] = {"status": "UNAVAILABLE", "blocker": "UNKNOWN_HORIZONS_CHECKOUT is not configured"}
        if require_products:
            raise EmpireRunError(products["unknown_horizons"]["blocker"])

    fc = os.environ.get("FREECOL_CHECKOUT")
    if fc:
        products["freecol"] = _freecol_check(rebased, result, fc)
    else:
        products["freecol"] = {"status": "UNAVAILABLE", "blocker": "FREECOL_CHECKOUT is not configured"}
        if require_products:
            raise EmpireRunError(products["freecol"]["blocker"])

    vel = os.environ.get("VELOREN_CHECKOUT")
    if vel:
        products["veloren"] = _veloren_check(rebased, vel)
    else:
        products["veloren"] = {"status": "UNAVAILABLE", "blocker": "VELOREN_CHECKOUT is not configured"}
        if require_products:
            raise EmpireRunError(products["veloren"]["blocker"])

    br = os.environ.get("BRUNNFELD_URL")
    if br:
        products["brunnfeld"] = _brunnfeld_check(br)
    else:
        products["brunnfeld"] = {"status": "UNAVAILABLE", "blocker": "BRUNNFELD_URL is not configured"}
        if require_products:
            raise EmpireRunError(products["brunnfeld"]["blocker"])

    oh = os.environ.get("OPENTTD_ADMIN_HOST")
    op = os.environ.get("OPENTTD_ADMIN_PORT")
    pw = os.environ.get("OPENTTD_ADMIN_PASSWORD")
    if oh and op and pw:
        products["openttd"] = _openttd_check(oh, int(op), pw)
    else:
        products["openttd"] = {"status": "UNAVAILABLE", "blocker": "OpenTTD admin connection is not configured"}
        if require_products:
            raise EmpireRunError(products["openttd"]["blocker"])

    for name, item in products.items():
        if item.get("status") == "CONNECTED_PRODUCT_ONLY":
            blockers.append({
                "kind": "MISSING_MECHANICS",
                "product": name,
                "provenance": "UNRESOLVED",
                "reason": item.get("blocker"),
            })

    return {
        "schema": "tnp.economy.empire-end-to-end-preview/1",
        "canonical": False,
        "campaign_boundary": census.get("meta", {}).get("campaignBoundary"),
        "campaign_time_advanced": False,
        "notion_writes": 0,
        "canonical_ledger_postings": 0,
        "source_snapshot_hash": census.get("meta", {}).get("snapshotHash"),
        "scenario_id": rebased["scenario_id"],
        "source_overrides": overrides,
        "blockers": blockers,
        "baen_core": result,
        "products": products,
        "integrity": result.get("checks"),
    }


def render_empire_month(payload: Mapping[str, Any]) -> str:
    core = payload["baen_core"]
    checks = core["checks"]
    lines = [
        f"# Baen Empire — Whole-Economy Month {core['month']} (PREVIEW — NOT CANON)",
        "",
        f"Campaign boundary: **{payload['campaign_boundary']}**.",
        "Notion writes: **0**. Canonical ledger postings: **0**. Campaign time advanced: **NO**.",
        "",
        "## What actually ran",
        "",
        f"- Baen whole-economy core: **{len(core.get('production', []))} production receipts**, **{len(core.get('trade', []))} trade receipts**, **{len(core.get('banking', []))} banking receipts**, **{len(core.get('migration', []))} migration receipts**.",
    ]
    for name, item in payload["products"].items():
        lines.append(f"- **{name}**: {item.get('status')}.")
    lines.extend(["", "## Source rebasing", ""])
    for row in payload["source_overrides"]:
        lines.append(f"- **{row['settlement']} population**: {row['from']} → {row['to']} ({row['provenance']}); class split remains {row['class_distribution']}.")
    lines.extend(["", "## Integrity", ""])
    for key in (
        "physical_conservation", "nonnegative_balances", "ledger_balanced",
        "deposit_liabilities_reconcile", "interest_receivables_reconcile",
        "collateral_assets_reconcile", "bank_balance_sheets_balance",
    ):
        lines.append(f"- {key}: **{'PASS' if checks.get(key) else 'FAIL'}**")
    lines.extend(["", "## Remaining blockers", ""])
    if payload["blockers"]:
        for blocker in payload["blockers"]:
            label = blocker.get("settlement") or blocker.get("product") or blocker.get("field") or blocker.get("kind")
            lines.append(f"- **{label}** — {blocker.get('reason')}")
    else:
        lines.append("- None.")
    lines.extend(["", "## Baen core report", "", core["report_markdown"]])
    return "\n".join(lines)
