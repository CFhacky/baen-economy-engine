"""Source-grounded monthly Baen Empire business phase.

This is the controlling Hammer-1495 economy path. It follows the campaign's
empire-operations-engine / hybrid-business-ops authority:

1. lock the verified Business Registry export;
2. admit only the explicit Hammer-1495 Arik-side operating slice;
3. roll one 3d6 revenue check per active sector;
4. roll one Administration expense-control check;
5. select 3-5 admitted entities for d20 complication checks;
6. apply only source-known neglect penalties;
7. produce a zero-write Vara briefing and review artifact.

It deliberately does NOT require or invent household baskets, opening commodity
stocks, generic market prices, settlement labour pools, or exact liquid cash.
Those belong to optional physical submodels and remain fail-closed until sourced.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .operator_codec import canonical_hash
from .operator_dice import _die, classify_3d6
from .registry_export import VerifiedRegistryExport, load_registry_export
from .empire_source_products import map_source_backed_physical_layer


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = (
    PROJECT_ROOT / "fixtures/registry-snapshots/business-registry-2026-08-29.json"
)
DEFAULT_ADMISSION = (
    PROJECT_ROOT / "recovery/BUSINESS_REGISTRY_ADMISSION_HAMMER_1495.json"
)
DEFAULT_MECHANICS = (
    PROJECT_ROOT / "recovery/EMPIRE_BUSINESS_MECHANICS_AUTHORITY_2026-09-17.json"
)

SCHEMA = "tnp.economy.empire-business-turn/1"
ACTIVE_SECTORS = (
    "Banking",
    "Construction",
    "Infrastructure",
    "Manufacturing",
    "Mining/Quarrying",
    "Aquaculture",
    "Agriculture",
    "Real Estate",
    "Trade",
    "Hospitality",
)


class EmpireBusinessError(ValueError):
    """The source-grounded business phase cannot be resolved safely."""


@dataclass(frozen=True, slots=True)
class SectorBaseline:
    sector: str
    entity_count: int
    employees: int
    revenue: Decimal
    known_cost: Decimal
    cost_complete: bool


def _money(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise EmpireBusinessError(f"{label} is not an exact decimal") from exc
    if not result.is_finite():
        raise EmpireBusinessError(f"{label} must be finite")
    return result


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EmpireBusinessError(f"cannot read {label}: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise EmpireBusinessError(f"{label} must be a JSON object")
    return payload


def _source_id(row: Mapping[str, object]) -> str:
    page_id = str(row.get("id") or "").replace("-", "").lower()
    if len(page_id) != 32:
        raise EmpireBusinessError("registry row has invalid Notion page identity")
    return f"notion:{page_id}"


def _verify_admission(
    export: VerifiedRegistryExport,
    admission: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, SectorBaseline]]:
    if admission.get("schema") != "tnp.economy.registry-admission/1":
        raise EmpireBusinessError("registry admission schema is unsupported")
    if admission.get("authority") != "SOURCE-DERIVED":
        raise EmpireBusinessError("registry admission is not source-derived")
    admitted = admission.get("admitted")
    excluded = admission.get("excluded")
    if not isinstance(admitted, list) or not isinstance(excluded, list):
        raise EmpireBusinessError("registry admission requires admitted/excluded arrays")

    registry_ids = set(export.rows_by_source_id)
    admission_ids: list[str] = []
    seen_entities: set[str] = set()
    sector_rows: dict[str, list[dict[str, Any]]] = {sector: [] for sector in ACTIVE_SECTORS}

    for record in admitted:
        if not isinstance(record, dict):
            raise EmpireBusinessError("admitted registry record is malformed")
        sid = record.get("source_record_id")
        entity = record.get("entity")
        sector = record.get("sector")
        if not isinstance(sid, str) or sid not in registry_ids:
            raise EmpireBusinessError(f"admitted record has unknown source identity: {sid}")
        if not isinstance(entity, str) or entity in seen_entities:
            raise EmpireBusinessError(f"admitted entity identity is invalid or duplicated: {entity}")
        if sector not in ACTIVE_SECTORS:
            raise EmpireBusinessError(f"admitted entity has non-business sector: {entity}: {sector}")
        source = export.row(sid)
        if source.get("Entity") != entity or source.get("Sector") != sector:
            raise EmpireBusinessError(f"admission identity drifted from Registry: {entity}")
        if source.get("Status") not in {"Operational", "Scaling"}:
            raise EmpireBusinessError(f"admitted row is no longer operating/scaling: {entity}")
        revenue = _money(record.get("monthly_revenue_gp"), f"{entity} revenue")
        if revenue < 0:
            raise EmpireBusinessError(f"{entity} revenue may not be negative")
        revenue_authority = record.get("revenue_authority")
        if revenue_authority == sid:
            if source.get("Monthly Revenue") is None or revenue != _money(
                source.get("Monthly Revenue"), f"{entity} Registry revenue"
            ):
                raise EmpireBusinessError(f"{entity} admission revenue drifted from source row")
        elif not isinstance(revenue_authority, str) or not revenue_authority.startswith("notion:"):
            raise EmpireBusinessError(f"{entity} revenue override lacks source authority")

        cost_value = record.get("monthly_cost_gp")
        if cost_value is not None:
            cost = _money(cost_value, f"{entity} cost")
            if cost < 0:
                raise EmpireBusinessError(f"{entity} cost may not be negative")
            if record.get("cost_authority") == sid and source.get("Monthly Cost") is not None:
                if cost != _money(source.get("Monthly Cost"), f"{entity} Registry cost"):
                    raise EmpireBusinessError(f"{entity} admission cost drifted from source row")

        admission_ids.append(sid)
        seen_entities.add(entity)
        sector_rows[str(sector)].append(record)

    for record in excluded:
        if not isinstance(record, dict):
            raise EmpireBusinessError("excluded registry record is malformed")
        sid = record.get("source_record_id")
        if not isinstance(sid, str) or sid not in registry_ids:
            raise EmpireBusinessError(f"excluded record has unknown source identity: {sid}")
        if not isinstance(record.get("reason"), str) or not str(record["reason"]).strip():
            raise EmpireBusinessError(f"excluded record lacks rationale: {sid}")
        admission_ids.append(sid)

    if len(admission_ids) != len(set(admission_ids)):
        raise EmpireBusinessError("registry admission repeats a source record")
    if set(admission_ids) != registry_ids:
        missing = sorted(registry_ids - set(admission_ids))
        extra = sorted(set(admission_ids) - registry_ids)
        raise EmpireBusinessError(
            f"registry admission does not cover the verified export: missing={missing[:3]} extra={extra[:3]}"
        )

    baselines: dict[str, SectorBaseline] = {}
    total_revenue = Decimal(0)
    total_employees = 0
    for sector in ACTIVE_SECTORS:
        rows = sector_rows[sector]
        revenue = sum(
            (_money(row["monthly_revenue_gp"], f"{sector} revenue") for row in rows),
            Decimal(0),
        )
        known_cost = sum(
            (
                _money(row["monthly_cost_gp"], f"{sector} cost")
                for row in rows
                if row.get("monthly_cost_gp") is not None
            ),
            Decimal(0),
        )
        employees = sum(int(row.get("employees") or 0) for row in rows)
        complete = all(row.get("monthly_cost_gp") is not None for row in rows)
        baselines[sector] = SectorBaseline(
            sector=sector,
            entity_count=len(rows),
            employees=employees,
            revenue=revenue,
            known_cost=known_cost,
            cost_complete=complete,
        )
        total_revenue += revenue
        total_employees += employees

    claimed = _money(admission.get("admitted_monthly_revenue_gp"), "admitted revenue")
    if claimed != total_revenue:
        raise EmpireBusinessError(
            f"registry admission baseline drifted: manifest {claimed} != derived {total_revenue}"
        )
    if int(admission.get("admitted_entity_count") or -1) != len(admitted):
        raise EmpireBusinessError("registry admission entity count drifted")
    if int(admission.get("admitted_employee_count") or -1) != total_employees:
        raise EmpireBusinessError("registry admission employee count drifted")

    cross = admission.get("financial_crosscheck")
    if not isinstance(cross, dict):
        raise EmpireBusinessError("registry admission has no financial cross-check")
    low, high = [
        _money(value, "current recurring revenue range")
        for value in cross.get("current_recurring_revenue_range_gp", [])
    ]
    if not low <= total_revenue <= high:
        raise EmpireBusinessError(
            f"admitted baseline {total_revenue} is outside current financial authority {low}-{high}"
        )
    return list(admitted), list(excluded), baselines


def _stream_modifier(count: int) -> int:
    if count >= 7:
        return 2
    if count >= 4:
        return 1
    return 0


def _market_modifier(condition: str) -> int:
    table = {"unknown": 0, "stable": 0, "boom": 4, "recession": -2}
    try:
        return table[condition]
    except KeyError as exc:
        raise EmpireBusinessError(f"unsupported market condition: {condition}") from exc


def _revenue_factor(outcome: str, mechanics: Mapping[str, Any]) -> Decimal:
    effects = mechanics["revenue_check"]["effects"]
    try:
        return _money(effects[outcome], f"revenue factor {outcome}")
    except KeyError as exc:
        raise EmpireBusinessError(f"missing revenue effect for {outcome}") from exc


def _expense_factor(outcome: str, mechanics: Mapping[str, Any]) -> Decimal:
    effects = mechanics["expense_check"]["effects"]
    try:
        return _money(effects[outcome], f"expense factor {outcome}")
    except KeyError as exc:
        raise EmpireBusinessError(f"missing expense effect for {outcome}") from exc


def _roll_3d6(
    *,
    seed: str,
    snapshot_hash: str,
    month_label: str,
    roll_key: str,
    target: int,
) -> dict[str, Any]:
    faces = [
        _die(
            sides=6,
            seed=seed,
            coordinate=(
                "empire-business-turn",
                snapshot_hash,
                month_label,
                roll_key,
                str(index),
            ),
        )
        for index in range(1, 4)
    ]
    total = sum(faces)
    outcome = classify_3d6(total=total, effective_target=target)
    return {
        "dice": faces,
        "total": total,
        "effective_target": target,
        "margin": target - total,
        "outcome": outcome,
    }


def _expense_size_modifier(employees: int) -> int:
    if employees < 50:
        return 2
    if employees <= 200:
        return 0
    if employees <= 1000:
        return -2
    return -4


def _rank_entities(
    admitted: Sequence[Mapping[str, Any]],
    *,
    seed: str,
    snapshot_hash: str,
    month_label: str,
) -> list[Mapping[str, Any]]:
    key = hashlib.sha256(seed.encode("utf-8")).digest()
    ranked: list[tuple[bytes, Mapping[str, Any]]] = []
    for row in admitted:
        message = "\x1f".join(
            (
                "empire-entity-selection",
                snapshot_hash,
                month_label,
                str(row["source_record_id"]),
            )
        ).encode("utf-8")
        ranked.append((hmac.new(key, message, hashlib.sha256).digest(), row))
    return [row for _, row in sorted(ranked, key=lambda pair: pair[0])]


def _d20_band(value: int) -> str:
    if not 1 <= value <= 20:
        raise EmpireBusinessError("d20 complication value must be 1..20")
    if value <= 3:
        return "crisis"
    if value <= 7:
        return "complication"
    if value <= 14:
        return "normal"
    if value <= 18:
        return "success"
    return "opportunity"


def _entity_complications(
    admitted: Sequence[Mapping[str, Any]],
    *,
    seed: str,
    snapshot_hash: str,
    month_label: str,
) -> list[dict[str, Any]]:
    count = 2 + _die(
        sides=3,
        seed=seed,
        coordinate=("empire-business-turn", snapshot_hash, month_label, "entity-count"),
    )
    selected = _rank_entities(
        admitted, seed=seed, snapshot_hash=snapshot_hash, month_label=month_label
    )[:count]
    results: list[dict[str, Any]] = []
    for row in selected:
        sid = str(row["source_record_id"])
        raw = _die(
            sides=20,
            seed=seed,
            coordinate=("empire-business-turn", snapshot_hash, month_label, sid, "entity-d20"),
        )
        neglect = row.get("neglect_status")
        adjusted: int | None = raw
        final: str | None
        effect: str
        if neglect == "Neglected":
            adjusted = max(1, raw - 4)
            final = _d20_band(adjusted)
            effect = "Neglected: d20 shifted -4 toward crisis per empire-operations-engine."
        elif neglect == "Critical":
            final = "crisis" if raw <= 3 else "complication"
            effect = "Critical: automatic complication; raw 1-3 remains crisis."
        elif neglect in {"Current", "Aging", "Delegated", "N/A"}:
            final = _d20_band(raw)
            effect = "No neglect penalty applies to the source status."
        elif neglect is None or not str(neglect).strip():
            adjusted = None
            final = None
            effect = "Neglect Status is absent; final severity is fail-closed pending source resolution."
        else:
            adjusted = None
            final = None
            effect = f"Unsupported Neglect Status {neglect!r}; final severity is unresolved."
        results.append(
            {
                "source_record_id": sid,
                "entity": row["entity"],
                "sector": row["sector"],
                "neglect_status": neglect,
                "raw_d20": raw,
                "adjusted_d20": adjusted,
                "raw_outcome": _d20_band(raw),
                "final_outcome": final,
                "neglect_effect": effect,
            }
        )
    return results


def _severity_for_sector(outcome: str) -> str:
    table = {
        "critical_failure": "URGENT",
        "failure_by_5_plus": "URGENT",
        "failure": "DEVELOPING",
        "exact_target": "BACKGROUND",
        "success": "BACKGROUND",
        "success_by_5_plus": "POSITIVE",
        "critical_success": "POSITIVE",
    }
    return table[outcome]


def _severity_for_entity(outcome: str | None) -> str:
    if outcome is None:
        return "UNRESOLVED"
    return {
        "crisis": "URGENT",
        "complication": "DEVELOPING",
        "normal": "BACKGROUND",
        "success": "POSITIVE",
        "opportunity": "POSITIVE",
    }[outcome]


def run_empire_business_turn(
    *,
    seed: str,
    month_label: str = "Day 7 Hammer 1495 DR — monthly preview",
    market_condition: str = "unknown",
    vara_active: bool = False,
    registry_path: Path = DEFAULT_REGISTRY,
    admission_path: Path = DEFAULT_ADMISSION,
    mechanics_path: Path = DEFAULT_MECHANICS,
) -> dict[str, Any]:
    if not isinstance(seed, str) or not seed:
        raise EmpireBusinessError("seed is required")
    if not isinstance(month_label, str) or not month_label.strip():
        raise EmpireBusinessError("month label is required")
    if type(vara_active) is not bool:
        raise EmpireBusinessError("vara_active must be boolean")

    export = load_registry_export(registry_path)
    admission = _load_object(admission_path, "Hammer-1495 Registry admission")
    mechanics = _load_object(mechanics_path, "business mechanics authority")
    if mechanics.get("schema") != "tnp.economy.empire-business-mechanics/1":
        raise EmpireBusinessError("business mechanics authority schema is unsupported")
    if mechanics.get("authority") != "SOURCE-DERIVED":
        raise EmpireBusinessError("business mechanics authority is not source-derived")

    admitted, excluded, baselines = _verify_admission(export, admission)
    total_baseline = sum((value.revenue for value in baselines.values()), Decimal(0))
    employee_total = sum(value.employees for value in baselines.values())

    sector_results: list[dict[str, Any]] = []
    total_proposed_revenue = Decimal(0)
    for sector in ACTIVE_SECTORS:
        baseline = baselines[sector]
        modifiers: list[dict[str, Any]] = []
        streams = _stream_modifier(baseline.entity_count)
        if streams:
            modifiers.append(
                {
                    "label": f"{baseline.entity_count} admitted revenue streams",
                    "value": streams,
                    "authority": "UPSTREAM-ADOPTED from hybrid-business-ops; count SOURCE-DERIVED",
                }
            )
        market_mod = _market_modifier(market_condition)
        if market_condition != "unknown":
            modifiers.append(
                {
                    "label": f"market condition: {market_condition}",
                    "value": market_mod,
                    "authority": "USER-RULED for this preview",
                }
            )
        if vara_active:
            modifiers.append(
                {
                    "label": "Vara active",
                    "value": 3,
                    "authority": "USER-RULED for this preview; modifier from hybrid-business-ops",
                }
            )
        target = 15 + sum(int(item["value"]) for item in modifiers)
        roll = _roll_3d6(
            seed=seed,
            snapshot_hash=export.snapshot_hash,
            month_label=month_label,
            roll_key=f"sector:{sector}:revenue",
            target=target,
        )
        factor = _revenue_factor(str(roll["outcome"]), mechanics)
        proposed = (baseline.revenue * factor).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_EVEN
        )
        total_proposed_revenue += proposed
        sector_results.append(
            {
                "sector": sector,
                "entity_count": baseline.entity_count,
                "employees": baseline.employees,
                "baseline_revenue_gp": str(baseline.revenue),
                "known_cost_gp": str(baseline.known_cost),
                "cost_complete": baseline.cost_complete,
                "modifiers": modifiers,
                "roll": roll,
                "revenue_factor": str(factor),
                "proposed_revenue_gp": str(proposed),
                "delta_gp": str(proposed - baseline.revenue),
                "severity": _severity_for_sector(str(roll["outcome"])),
            }
        )

    financial = mechanics.get("current_financial_envelope")
    if not isinstance(financial, dict):
        raise EmpireBusinessError("mechanics authority lacks current financial envelope")
    profit_low, profit_high = [
        _money(value, "current recurring profit range")
        for value in financial["recurring_profit_range_gp"]
    ]
    if profit_low > profit_high:
        raise EmpireBusinessError("current recurring profit range is inverted")
    expense_low = total_baseline - profit_high
    expense_high = total_baseline - profit_low
    if expense_low < 0:
        raise EmpireBusinessError("source-derived implied expense range is invalid")

    expense_modifiers = [
        {
            "label": f"organization size: {employee_total} admitted commercial employees",
            "value": _expense_size_modifier(employee_total),
            "authority": "UPSTREAM-ADOPTED hybrid-business-ops threshold; headcount SOURCE-DERIVED",
        }
    ]
    conditions = mechanics.get("current_conditions")
    if not isinstance(conditions, dict):
        raise EmpireBusinessError("mechanics authority lacks current conditions")
    if conditions.get("rapid_expansion_modifier") is True:
        expense_modifiers.append(
            {
                "label": "rapid expansion",
                "value": -3,
                "authority": str(conditions.get("rapid_expansion_authority")),
                "rationale": str(conditions.get("rapid_expansion_rationale")),
            }
        )
    expense_target = 16 + sum(int(item["value"]) for item in expense_modifiers)
    expense_roll = _roll_3d6(
        seed=seed,
        snapshot_hash=export.snapshot_hash,
        month_label=month_label,
        roll_key="empire:expense-control",
        target=expense_target,
    )
    expense_factor = _expense_factor(str(expense_roll["outcome"]), mechanics)
    proposed_expense_low = (expense_low * expense_factor).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_EVEN
    )
    proposed_expense_high = (expense_high * expense_factor).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_EVEN
    )
    proposed_net_low = total_proposed_revenue - proposed_expense_high
    proposed_net_high = total_proposed_revenue - proposed_expense_low

    complications = _entity_complications(
        admitted,
        seed=seed,
        snapshot_hash=export.snapshot_hash,
        month_label=month_label,
    )

    briefing: dict[str, list[dict[str, Any]]] = {
        "URGENT": [],
        "DEVELOPING": [],
        "POSITIVE": [],
        "BACKGROUND": [],
        "UNRESOLVED": [],
    }
    for row in sector_results:
        briefing[row["severity"]].append(
            {
                "kind": "sector",
                "subject": row["sector"],
                "outcome": row["roll"]["outcome"],
                "delta_gp": row["delta_gp"],
            }
        )
    for row in complications:
        severity = _severity_for_entity(row["final_outcome"])
        briefing[severity].append(
            {
                "kind": "entity",
                "subject": row["entity"],
                "outcome": row["final_outcome"] or row["raw_outcome"],
                "neglect_status": row["neglect_status"],
            }
        )

    unresolved = list(admission.get("unresolved_accounting") or [])
    unresolved.extend(
        f"{row['entity']}: Neglect Status missing/unsupported"
        for row in complications
        if row["final_outcome"] is None
    )

    physical = map_source_backed_physical_layer(
        seed=seed,
        month_label=month_label,
        sector_results=sector_results,
        expense_control={
            "roll": expense_roll,
            "expense_factor": str(expense_factor),
        },
        complications=complications,
    )
    unresolved.extend(physical["unresolved"])

    result: dict[str, Any] = {
        "schema": SCHEMA,
        "mode": "SOURCE_GROUNDED_PREVIEW",
        "canonical": False,
        "campaign_time_advanced": False,
        "notion_writes": 0,
        "canonical_ledger_postings": 0,
        "timeline_id": admission.get("timeline_id"),
        "as_of": admission.get("as_of"),
        "month_label": month_label,
        "seed_fingerprint": hashlib.sha256(seed.encode("utf-8")).hexdigest(),
        "sources": {
            "registry_snapshot_hash": export.snapshot_hash,
            "registry_export_hash": export.export_hash,
            "admission_hash": canonical_hash(admission),
            "mechanics_hash": canonical_hash(mechanics),
        },
        "admission": {
            "admitted_entities": len(admitted),
            "excluded_entities": len(excluded),
            "admitted_employees": employee_total,
            "baseline_revenue_gp": str(total_baseline),
            "financial_crosscheck": admission.get("financial_crosscheck"),
        },
        "sector_results": sector_results,
        "expense_control": {
            "baseline_expense_range_gp": [str(expense_low), str(expense_high)],
            "range_derivation": (
                "admitted Arik-side operating revenue minus the Current Financial State "
                "75,000-90,000 gp recurring-profit range; no exact expense balance is asserted"
            ),
            "modifiers": expense_modifiers,
            "roll": expense_roll,
            "expense_factor": str(expense_factor),
            "proposed_expense_range_gp": [
                str(proposed_expense_low),
                str(proposed_expense_high),
            ],
        },
        "proposed_revenue_gp": str(total_proposed_revenue),
        "proposed_net_range_gp": [
            str(proposed_net_low.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)),
            str(proposed_net_high.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)),
        ],
        "entity_complications": complications,
        "vara_briefing": briefing,
        "unresolved": unresolved,
        "physical_subsystems": physical,
        "authority": {
            "inputs": "SOURCE-DERIVED / USER-RULED only",
            "mechanics": "SOURCE-DERIVED campaign rules; upstream products adopted only when mapped",
            "rolls": "non-canonical deterministic preview until explicitly committed in play",
        },
    }
    result["result_hash"] = canonical_hash(result)
    return result


def render_empire_business_report(payload: Mapping[str, Any]) -> str:
    if payload.get("schema") != SCHEMA:
        raise EmpireBusinessError("cannot render unknown Empire business result")
    lines = [
        f"# Baen Empire Monthly Business Phase — {payload['month_label']}",
        "",
        "**SOURCE-GROUNDED PREVIEW — NOT CANON UNTIL COMMITTED IN PLAY**",
        "",
        f"- Timeline: **{payload['timeline_id']}**",
        f"- Authority boundary: **{payload['as_of']}**",
        f"- Admitted Registry entities: **{payload['admission']['admitted_entities']}**",
        f"- Excluded/future/unresolved Registry entities: **{payload['admission']['excluded_entities']}**",
        f"- Source-reconciled recurring revenue baseline: **{payload['admission']['baseline_revenue_gp']} gp/month**",
        f"- Proposed rolled revenue: **{payload['proposed_revenue_gp']} gp**",
        (
            f"- Proposed net range: **{payload['proposed_net_range_gp'][0]} to "
            f"{payload['proposed_net_range_gp'][1]} gp**"
        ),
        "- Notion writes: **0** · canonical ledger postings: **0** · campaign time advanced: **NO**",
        "",
        "## Sector revenue rolls",
        "",
    ]
    for row in payload["sector_results"]:
        roll = row["roll"]
        lines.append(
            f"- **{row['sector']}** — {row['baseline_revenue_gp']} → "
            f"**{row['proposed_revenue_gp']} gp** ({roll['dice']} = {roll['total']} "
            f"vs {roll['effective_target']}; {roll['outcome']}; {row['severity']})"
        )
    expense = payload["expense_control"]
    eroll = expense["roll"]
    lines.extend(
        [
            "",
            "## Expense control",
            "",
            (
                f"- Source-derived baseline expense range: **{expense['baseline_expense_range_gp'][0]} "
                f"to {expense['baseline_expense_range_gp'][1]} gp**."
            ),
            (
                f"- Administration roll: {eroll['dice']} = {eroll['total']} vs "
                f"{eroll['effective_target']} → **{eroll['outcome']}**."
            ),
            (
                f"- Proposed expense range: **{expense['proposed_expense_range_gp'][0]} "
                f"to {expense['proposed_expense_range_gp'][1]} gp**."
            ),
            "",
            "## Entity complications",
            "",
        ]
    )
    for row in payload["entity_complications"]:
        final = row["final_outcome"] or "UNRESOLVED"
        lines.append(
            f"- **{row['entity']}** — d20 {row['raw_d20']}; neglect "
            f"{row['neglect_status'] or 'UNKNOWN'} → **{final}**."
        )
    lines.extend(["", "## Vara briefing", ""])
    for band in ("URGENT", "DEVELOPING", "POSITIVE", "UNRESOLVED", "BACKGROUND"):
        lines.append(f"### {band}")
        entries = payload["vara_briefing"][band]
        if not entries:
            lines.append("- None.")
        else:
            for row in entries:
                suffix = f" ({row.get('outcome')})" if row.get("outcome") else ""
                lines.append(f"- {row['kind']}: **{row['subject']}**{suffix}")
        lines.append("")
    lines.extend(
        [
            "## Unresolved accounting / source gates",
            "",
        ]
    )
    for item in payload["unresolved"]:
        lines.append(f"- {item}")
    if not payload["unresolved"]:
        lines.append("- None.")
    physical = payload["physical_subsystems"]
    lines.extend(
        [
            "",
            "## Source-backed production lines",
            "",
        ]
    )
    for row in physical.get("production_lines") or []:
        maximum = f"; max {row['maximum']}" if row.get("maximum") is not None else ""
        lines.append(
            f"- **{row['entity']}** — {row['quantity']} {row['unit']}{maximum} "
            f"({row['authority']}; {row['employees']} employees)."
        )
    products = physical.get("products") or {}
    lines.extend(
        [
            "",
            "## Physical subsystem / product mapping",
            "",
            f"- **{physical['status']}** — {physical['reason']}",
            "",
        ]
    )
    for name in ("mesa", "freecol", "unknown_horizons", "openttd", "veloren", "brunnfeld"):
        item = products.get(name) or {}
        status = item.get("status", "UNKNOWN")
        extra = item.get("reason") or item.get("blocker") or item.get("provenance") or ""
        suffix = f" — {extra}" if extra else ""
        lines.append(f"- **{name}**: {status}{suffix}")
    lines.append("")
    return "\n".join(lines)
