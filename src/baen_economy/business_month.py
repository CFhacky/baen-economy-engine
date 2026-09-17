"""Source-bound, non-canonical monthly business previews.

The resolver deliberately operates on one verified Registry row at a time.  It
does not consolidate parent/child entities, advance campaign time, post a
journal, or expose a Notion write path.
"""

from __future__ import annotations

from decimal import Context, Decimal, ROUND_HALF_UP, localcontext
import re
from typing import Mapping

from .business_dice import roll_business_checks, validate_business_manifest
from .domain import canonical_decimal
from .operator_codec import canonical_hash
from .registry_export import RegistryExportError, VerifiedRegistryExport


BUSINESS_MONTH_SCHEMA = "tnp.business.month-preview/1"
BUSINESS_PROFILE_ID = "gurps-business-month-v1"
NOTION_DIFF_SCHEMA = "tnp.business.notion-review-diff/1"
BUSINESS_LEDGER_SCHEMA = "tnp.business.zero-ledger-preview/1"
_CENT = Decimal("0.01")
_MARKET_MODIFIERS = {"boom": 4, "stable": 0, "recession": -2}
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_NOTION_SOURCE_ID_RE = re.compile(r"^notion:([0-9a-f]{32})$")
_ENTITY_KEYS = {
    "name",
    "source_record_id",
    "source_url",
    "status",
    "sector",
    "source_last_updated",
}
_SOURCE_BINDING_KEYS = {
    "export_hash",
    "snapshot_hash",
    "source_schema_hash",
    "transport_content_hash",
    "row_hash",
    "properties",
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
_CONSUMED_PROPERTIES = (
    "Entity",
    "Status",
    "Sector",
    "Employees",
    "Monthly Revenue",
    "Monthly Cost",
    "Date Operational",
    "Last Updated",
)
# Merchant-15 is an operating-business check.  These are the source sectors
# reviewed for that treatment; state, military, intelligence, education, and
# research operations require a separate accounting/mechanics ruling.
COMMERCIAL_SECTORS = frozenset(
    {
        "Agriculture",
        "Aquaculture",
        "Banking",
        "Construction",
        "Hospitality",
        "Infrastructure",
        "Manufacturing",
        "Mining/Quarrying",
        "Real Estate",
        "Trade",
    }
)


class BusinessMonthError(ValueError):
    """Raised when a Registry row or preview request is not safe to resolve."""


def find_source_record_id(export: VerifiedRegistryExport, entity_name: str) -> str:
    """Resolve exactly one source row by its case-sensitive Registry title."""

    _clean_text(entity_name, "entity name")
    matches = [
        source_id
        for source_id, row in export.rows_by_source_id.items()
        if row["Entity"] == entity_name
    ]
    if len(matches) != 1:
        raise BusinessMonthError(
            f"entity title must identify exactly one Registry row; found {len(matches)}"
        )
    return matches[0]


def employee_size_modifier(employees: int | Decimal) -> int:
    """Return the Administration modifier, failing at ambiguous source bounds."""

    if isinstance(employees, bool):
        raise BusinessMonthError("employee count must be a whole non-negative number")
    value = Decimal(employees)
    if not value.is_finite() or value < 0 or value != value.to_integral_value():
        raise BusinessMonthError("employee count must be a whole non-negative number")
    count = int(value)
    # The governing table says both 50-200/200-1000 and 200-1000/1000+.
    # Exact boundary rulings are therefore deliberately not inferred.
    if count in {200, 1000}:
        raise BusinessMonthError(
            f"employee count {count} is ambiguous in the governing size table"
        )
    if count < 50:
        return 2
    if count < 200:
        return 0
    if count < 1000:
        return -2
    return -4


def revenue_factor(outcome: str, margin: int | None = None) -> Decimal:
    _validate_outcome_margin(outcome, margin)
    factors = {
        "critical_success": Decimal("1.25"),
        "success_by_5_plus": Decimal("1.15"),
        "success": Decimal("1.05"),
        "exact_target": Decimal("1.00"),
        "failure": Decimal("0.90"),
        "failure_by_5_plus": Decimal("0.80"),
        "critical_failure": Decimal("0.70"),
    }
    try:
        return factors[outcome]
    except KeyError as exc:
        raise BusinessMonthError(f"unsupported revenue outcome: {outcome}") from exc


def expense_factor(outcome: str, margin: int | None = None) -> Decimal:
    _validate_outcome_margin(outcome, margin)
    factors = {
        "critical_success": Decimal("0.90"),
        "success_by_5_plus": Decimal("1.00"),
        "success": Decimal("1.05"),
        # An exact roll is a normal GURPS success.  The expense table has no
        # separate exact row, so its ordinary-success +5% rule applies.
        "exact_target": Decimal("1.05"),
        "failure": Decimal("1.15"),
        # The expense table has no separate failure-by-5 row.
        "failure_by_5_plus": Decimal("1.15"),
        "critical_failure": Decimal("1.25"),
    }
    try:
        return factors[outcome]
    except KeyError as exc:
        raise BusinessMonthError(f"unsupported expense outcome: {outcome}") from exc


def preview_business_month(
    export: VerifiedRegistryExport,
    source_record_id: str,
    month_label: str,
    seed: str,
    *,
    market: str = "stable",
    vara_active: bool = True,
    revenue_streams: int = 1,
    competent_managers: int = 0,
    monopoly: bool = False,
    excellent_accounting: bool = False,
    rapid_expansion: bool = False,
) -> dict[str, object]:
    """Resolve a deterministic, locally reviewable preview for one entity."""

    if not isinstance(export, VerifiedRegistryExport):
        raise BusinessMonthError("business preview requires a verified Registry export")
    _clean_text(source_record_id, "source record ID")
    _clean_text(month_label, "month label")
    _clean_text(seed, "deterministic seed")
    if market not in _MARKET_MODIFIERS:
        raise BusinessMonthError("market must be boom, stable, or recession")
    for value, label in (
        (vara_active, "vara_active"),
        (monopoly, "monopoly"),
        (excellent_accounting, "excellent_accounting"),
        (rapid_expansion, "rapid_expansion"),
    ):
        if type(value) is not bool:
            raise BusinessMonthError(f"{label} must be a boolean")
    if type(revenue_streams) is not int or revenue_streams < 1:
        raise BusinessMonthError("revenue_streams must be a positive integer")
    if type(competent_managers) is not int or not 0 <= competent_managers <= 3:
        raise BusinessMonthError("competent_managers must be an integer from 0 through 3")

    try:
        row = export.row(source_record_id)
    except RegistryExportError as exc:
        raise BusinessMonthError(str(exc)) from exc
    _validate_eligible_row(export, source_record_id, row)
    revenue = _source_decimal(row, "Monthly Revenue")
    cost = _source_decimal(row, "Monthly Cost")
    employees = _source_decimal(row, "Employees")

    revenue_modifiers = [
        {"label": f"Market {market}", "value": _MARKET_MODIFIERS[market]},
    ]
    if revenue_streams >= 7:
        revenue_modifiers.append({"label": "7+ revenue streams", "value": 2})
    elif revenue_streams >= 4:
        revenue_modifiers.append({"label": "4-6 revenue streams", "value": 1})
    if vara_active:
        revenue_modifiers.append({"label": "Vara active", "value": 3})
    if competent_managers:
        revenue_modifiers.append(
            {"label": "Competent managers", "value": competent_managers}
        )
    if monopoly:
        revenue_modifiers.append({"label": "Monopoly position", "value": 2})

    expense_modifiers = [
        {
            "label": f"Entity size ({canonical_decimal(employees)} employees)",
            "value": employee_size_modifier(employees),
        }
    ]
    if excellent_accounting:
        expense_modifiers.append({"label": "Excellent accounting", "value": 2})
    if rapid_expansion:
        expense_modifiers.append({"label": "Rapid expansion", "value": -3})

    dice = roll_business_checks(
        snapshot_hash=export.snapshot_hash,
        source_record_id=source_record_id,
        month_label=month_label,
        seed=seed,
        revenue_modifiers=revenue_modifiers,
        expense_modifiers=expense_modifiers,
    )
    roll_by_key = {str(item["roll_key"]): item for item in dice["rolls"]}
    revenue_roll = roll_by_key["revenue"]
    expense_roll = roll_by_key["expense"]
    rev_factor = revenue_factor(
        str(revenue_roll["outcome"]), int(revenue_roll["margin"])
    )
    cost_factor = expense_factor(
        str(expense_roll["outcome"]), int(expense_roll["margin"])
    )
    with localcontext(_new_business_decimal_context()):
        proposed_revenue = _money(revenue * rev_factor)
        proposed_cost = _money(cost * cost_factor)
        proposed_net = _money(proposed_revenue - proposed_cost)

    source_properties = {
        property_name: {
            "source_value": row[property_name],
            "property_hash": export.property_hash(source_record_id, property_name),
        }
        for property_name in _CONSUMED_PROPERTIES
    }
    notion_diff = _notion_review_diff(
        export=export,
        source_record_id=source_record_id,
        row=row,
        proposed_revenue=proposed_revenue,
        proposed_cost=proposed_cost,
    )
    ledger_preview = {
        "schema": BUSINESS_LEDGER_SCHEMA,
        "postable": False,
        "ledger_post_capability": False,
        "transaction_count": 0,
        "posting_count": 0,
        "transactions": [],
        "reason": (
            "Registry business outcomes remain proposed scenario values until separately "
            "accepted by campaign authority and translated into canonical source events."
        ),
    }
    assumptions = {
        "market": market,
        "vara_active": vara_active,
        "revenue_streams": revenue_streams,
        "competent_managers": competent_managers,
        "monopoly": monopoly,
        "excellent_accounting": excellent_accounting,
        "rapid_expansion": rapid_expansion,
    }
    body: dict[str, object] = {
        "schema": BUSINESS_MONTH_SCHEMA,
        "mode": "preview",
        "canonical": False,
        "authority": "scenario_assumption",
        "month_label": month_label,
        "campaign_time_advanced": False,
        "campaign_state_rolls_resolved": 0,
        "entity": {
            "name": row["Entity"],
            "source_record_id": source_record_id,
            "source_url": row["url"],
            "status": row["Status"],
            "sector": row["Sector"],
            "source_last_updated": row["Last Updated"],
        },
        "source_binding": {
            "export_hash": export.export_hash,
            "snapshot_hash": export.snapshot_hash,
            "source_schema_hash": export.source_schema_hash,
            "transport_content_hash": export.content_hash,
            "row_hash": export.row_hashes[source_record_id],
            "properties": source_properties,
        },
        "assumptions": assumptions,
        "dice_manifest": dice,
        "financials": {
            "currency": "GP",
            "source_projected_revenue": canonical_decimal(revenue),
            "source_projected_cost": canonical_decimal(cost),
            "revenue_factor": canonical_decimal(rev_factor),
            "expense_factor": canonical_decimal(cost_factor),
            "proposed_revenue": canonical_decimal(proposed_revenue),
            "proposed_cost": canonical_decimal(proposed_cost),
            "proposed_net": canonical_decimal(proposed_net),
        },
        "ledger_preview": ledger_preview,
        "notion_review_diff": notion_diff,
        "warnings": [
            "This is a deterministic scenario preview, not campaign canon.",
            "The Registry was read only; zero Notion writes were attempted.",
            "No journal transactions or postings were created.",
        ],
    }
    body["content_hash"] = canonical_hash(body)
    validate_business_preview(body, export=export)
    return body


def validate_business_preview(
    preview: object, *, export: VerifiedRegistryExport | None = None
) -> None:
    """Verify the immutable hash and the preview's no-mutation invariants."""

    if not isinstance(preview, dict):
        raise BusinessMonthError("business preview must be a concrete object")
    required = {
        "schema",
        "mode",
        "canonical",
        "authority",
        "month_label",
        "campaign_time_advanced",
        "campaign_state_rolls_resolved",
        "entity",
        "source_binding",
        "assumptions",
        "dice_manifest",
        "financials",
        "ledger_preview",
        "notion_review_diff",
        "warnings",
        "content_hash",
    }
    if set(preview) != required:
        raise BusinessMonthError("business preview keys do not match the schema")
    body = dict(preview)
    supplied_hash = body.pop("content_hash")
    if supplied_hash != canonical_hash(body):
        raise BusinessMonthError("business preview content hash does not match")
    if (
        preview["schema"] != BUSINESS_MONTH_SCHEMA
        or preview["mode"] != "preview"
        or preview["canonical"] is not False
        or preview["authority"] != "scenario_assumption"
        or preview["campaign_time_advanced"] is not False
        or type(preview["campaign_state_rolls_resolved"]) is not int
        or preview["campaign_state_rolls_resolved"] != 0
    ):
        raise BusinessMonthError("business preview authority flags are inconsistent")
    source = preview["source_binding"]
    entity = preview["entity"]
    assumptions = preview["assumptions"]
    if not all(isinstance(item, dict) for item in (source, entity, assumptions)):
        raise BusinessMonthError("business preview source, entity, or assumptions malformed")
    _clean_text(preview["month_label"], "month label")
    _validate_entity_and_source_receipts(entity, source)
    _validate_assumptions(assumptions)
    try:
        validate_business_manifest(
            preview["dice_manifest"],
            revenue_modifiers=_expected_revenue_modifiers(assumptions),
            expense_modifiers=_expected_expense_modifiers(assumptions, source),
            snapshot_hash=source["snapshot_hash"],
            source_record_id=entity["source_record_id"],
            month_label=preview["month_label"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise BusinessMonthError(f"business dice receipt is invalid: {exc}") from exc
    ledger = preview["ledger_preview"]
    if (
        not isinstance(ledger, dict)
        or set(ledger)
        != {
            "schema",
            "postable",
            "ledger_post_capability",
            "transaction_count",
            "posting_count",
            "transactions",
            "reason",
        }
        or ledger.get("schema") != BUSINESS_LEDGER_SCHEMA
        or ledger.get("postable") is not False
        or ledger.get("ledger_post_capability") is not False
        or type(ledger.get("transaction_count")) is not int
        or ledger.get("transaction_count") != 0
        or type(ledger.get("posting_count")) is not int
        or ledger.get("posting_count") != 0
        or ledger.get("transactions") != []
        or ledger.get("reason")
        != (
            "Registry business outcomes remain proposed scenario values until separately "
            "accepted by campaign authority and translated into canonical source events."
        )
    ):
        raise BusinessMonthError("business preview must contain a zero-posting ledger")
    diff = preview["notion_review_diff"]
    if (
        not isinstance(diff, dict)
        or diff.get("schema") != NOTION_DIFF_SCHEMA
        or diff.get("executable") is not False
        or diff.get("write_eligible") is not False
        or diff.get("write_authorized") is not False
        or diff.get("write_attempted") is not False
        or type(diff.get("applied_count")) is not int
        or diff.get("applied_count") != 0
    ):
        raise BusinessMonthError("business preview Notion diff is not safely inert")
    _validate_financial_arithmetic(preview)
    _validate_notion_diff(preview)
    if preview["warnings"] != [
        "This is a deterministic scenario preview, not campaign canon.",
        "The Registry was read only; zero Notion writes were attempted.",
        "No journal transactions or postings were created.",
    ]:
        raise BusinessMonthError("business preview warnings drifted")
    if export is not None:
        _validate_source_binding(preview, export)


def render_business_report(preview: Mapping[str, object]) -> str:
    validate_business_preview(dict(preview))
    entity = preview["entity"]
    financials = preview["financials"]
    diff = preview["notion_review_diff"]
    return (
        "# Business Month Preview — NOT CANON\n\n"
        f"- Entity: {entity['name']}\n"
        f"- Scenario month: {preview['month_label']} (campaign time not advanced)\n"
        f"- Proposed revenue: {financials['proposed_revenue']} GP\n"
        f"- Proposed cost: {financials['proposed_cost']} GP\n"
        f"- Proposed net: {financials['proposed_net']} GP\n"
        "- Ledger: 0 transactions / 0 postings\n"
        "- Notion: 0 writes attempted / 0 applied\n\n"
        f"Review diff: {diff['diff_hash']}\n"
    )


def _notion_review_diff(
    *,
    export: VerifiedRegistryExport,
    source_record_id: str,
    row: Mapping[str, object],
    proposed_revenue: Decimal,
    proposed_cost: Decimal,
) -> dict[str, object]:
    property_diffs = []
    for property_name, proposed in (
        ("Monthly Revenue", proposed_revenue),
        ("Monthly Cost", proposed_cost),
    ):
        property_diffs.append(
            {
                "property_name": property_name,
                "source_value": row[property_name],
                "source_property_hash": export.property_hash(
                    source_record_id, property_name
                ),
                "proposed_value": canonical_decimal(proposed),
                "changed": Decimal(str(row[property_name])) != proposed,
            }
        )
    body: dict[str, object] = {
        "schema": NOTION_DIFF_SCHEMA,
        "target_data_source": export.read_snapshot.data_source_url,
        "target_record_url": row["url"],
        "target_source_record_id": source_record_id,
        "source_snapshot_hash": export.snapshot_hash,
        "source_row_hash": export.row_hashes[source_record_id],
        "property_diffs": property_diffs,
        "review_eligible": True,
        "executable": False,
        "write_eligible": False,
        "write_authorized": False,
        "write_attempted": False,
        "applied_count": 0,
        "blockers": [
            "construction_mode_notion_read_only",
            "campaign_authority_has_not_accepted_preview_values",
            "no_write_adapter_is_present",
        ],
    }
    body["diff_hash"] = canonical_hash(body)
    return body


def _validate_eligible_row(
    export: VerifiedRegistryExport,
    source_record_id: str,
    row: Mapping[str, object],
) -> None:
    if row["Status"] != "Operational":
        raise BusinessMonthError("only an Operational Registry row can be previewed")
    if row["Sector"] not in COMMERCIAL_SECTORS:
        raise BusinessMonthError(
            "Registry sector is not in the reviewed commercial-sector allowlist"
        )
    for field in ("Sector", "Date Operational", "Last Updated"):
        if not isinstance(row[field], str) or not row[field].strip():
            raise BusinessMonthError(f"Registry row requires a source-backed {field}")
    for field in ("Monthly Revenue", "Monthly Cost", "Employees"):
        value = _source_decimal(row, field)
        if value < 0:
            raise BusinessMonthError(f"Registry row has a negative {field}")
    row_url = row["url"]
    issues = [
        issue
        for issue in export.audit.issues
        if issue.entity == row["Entity"] or issue.source_ref == row_url
    ]
    if issues:
        codes = ", ".join(sorted({item.code for item in issues}))
        raise BusinessMonthError(f"Registry audit issues block this row: {codes}")
    if source_record_id not in export.row_hashes:
        raise BusinessMonthError("Registry source binding is incomplete")


def _source_decimal(row: Mapping[str, object], field: str) -> Decimal:
    value = row[field]
    if not isinstance(value, str):
        raise BusinessMonthError(f"Registry row requires exact text for {field}")
    try:
        result = Decimal(value)
    except Exception as exc:
        raise BusinessMonthError(f"Registry row has malformed {field}") from exc
    if not result.is_finite():
        raise BusinessMonthError(f"Registry row has non-finite {field}")
    return result


def _money(value: Decimal) -> Decimal:
    with localcontext(_new_business_decimal_context()):
        return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _new_business_decimal_context() -> Context:
    """Return the engine-owned context used for exact monetary arithmetic."""

    return Context(prec=64, rounding=ROUND_HALF_UP)


def _clean_text(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or _CONTROL_RE.search(value)
    ):
        raise BusinessMonthError(f"{label} must be non-empty clean text")
    return value


def _validate_outcome_margin(outcome: str, margin: int | None) -> None:
    if not isinstance(outcome, str):
        raise BusinessMonthError("dice outcome must be text")
    if margin is not None and type(margin) is not int:
        raise BusinessMonthError("dice margin must be an integer")
    if margin is None:
        return
    # Natural 3/4/5/6 and 17/18 results can override the apparent margin, so
    # only categories whose names fully determine the margin are checked here.
    compatible = {
        "success_by_5_plus": margin >= 5,
        "success": 1 <= margin <= 4,
        "exact_target": margin == 0,
        "failure_by_5_plus": margin <= -5,
    }
    if outcome in compatible and not compatible[outcome]:
        raise BusinessMonthError("dice outcome and margin are inconsistent")


def _expected_revenue_modifiers(assumptions: Mapping[str, object]) -> list[dict[str, object]]:
    market = assumptions["market"]
    streams = assumptions["revenue_streams"]
    managers = assumptions["competent_managers"]
    result: list[dict[str, object]] = [
        {"label": f"Market {market}", "value": _MARKET_MODIFIERS[str(market)]}
    ]
    if int(streams) >= 7:
        result.append({"label": "7+ revenue streams", "value": 2})
    elif int(streams) >= 4:
        result.append({"label": "4-6 revenue streams", "value": 1})
    if assumptions["vara_active"] is True:
        result.append({"label": "Vara active", "value": 3})
    if int(managers):
        result.append({"label": "Competent managers", "value": int(managers)})
    if assumptions["monopoly"] is True:
        result.append({"label": "Monopoly position", "value": 2})
    return result


def _expected_expense_modifiers(
    assumptions: Mapping[str, object], source_binding: Mapping[str, object]
) -> list[dict[str, object]]:
    properties = source_binding.get("properties")
    if not isinstance(properties, dict):
        raise BusinessMonthError("business source property receipt is malformed")
    employee_receipt = properties.get("Employees")
    if not isinstance(employee_receipt, dict):
        raise BusinessMonthError("business employee property receipt is malformed")
    employees = Decimal(str(employee_receipt["source_value"]))
    result: list[dict[str, object]] = [
        {
            "label": f"Entity size ({canonical_decimal(employees)} employees)",
            "value": employee_size_modifier(employees),
        }
    ]
    if assumptions["excellent_accounting"] is True:
        result.append({"label": "Excellent accounting", "value": 2})
    if assumptions["rapid_expansion"] is True:
        result.append({"label": "Rapid expansion", "value": -3})
    return result


def _validate_financial_arithmetic(preview: Mapping[str, object]) -> None:
    financials = preview["financials"]
    if not isinstance(financials, dict) or set(financials) != {
        "currency",
        "source_projected_revenue",
        "source_projected_cost",
        "revenue_factor",
        "expense_factor",
        "proposed_revenue",
        "proposed_cost",
        "proposed_net",
    }:
        raise BusinessMonthError("business financial result is malformed")
    try:
        source_revenue = Decimal(str(financials["source_projected_revenue"]))
        source_cost = Decimal(str(financials["source_projected_cost"]))
        rev_factor = Decimal(str(financials["revenue_factor"]))
        cost_factor = Decimal(str(financials["expense_factor"]))
        proposed_revenue = Decimal(str(financials["proposed_revenue"]))
        proposed_cost = Decimal(str(financials["proposed_cost"]))
        proposed_net = Decimal(str(financials["proposed_net"]))
    except Exception as exc:
        raise BusinessMonthError("business financial result contains invalid decimals") from exc
    with localcontext(_new_business_decimal_context()):
        expected_source_revenue = _bound_source_decimal(preview, "Monthly Revenue")
        expected_source_cost = _bound_source_decimal(preview, "Monthly Cost")
        expected_rev_factor = revenue_factor(
            str(_roll_receipt(preview, "revenue")["outcome"]),
            int(_roll_receipt(preview, "revenue")["margin"]),
        )
        expected_cost_factor = expense_factor(
            str(_roll_receipt(preview, "expense")["outcome"]),
            int(_roll_receipt(preview, "expense")["margin"]),
        )
        expected_proposed_revenue = _money(
            expected_source_revenue * expected_rev_factor
        )
        expected_proposed_cost = _money(expected_source_cost * expected_cost_factor)
        expected_proposed_net = _money(
            expected_proposed_revenue - expected_proposed_cost
        )
        expected_values = {
            "source_projected_revenue": expected_source_revenue,
            "source_projected_cost": expected_source_cost,
            "revenue_factor": expected_rev_factor,
            "expense_factor": expected_cost_factor,
            "proposed_revenue": expected_proposed_revenue,
            "proposed_cost": expected_proposed_cost,
            "proposed_net": expected_proposed_net,
        }
        if any(
            type(financials[name]) is not str
            or financials[name] != canonical_decimal(value)
            for name, value in expected_values.items()
        ):
            raise BusinessMonthError(
                "business financial decimals must use their exact derived text"
            )
        if (
            financials["currency"] != "GP"
            or source_revenue != expected_source_revenue
            or source_cost != expected_source_cost
            or rev_factor != expected_rev_factor
            or cost_factor != expected_cost_factor
            or proposed_revenue != expected_proposed_revenue
            or proposed_cost != expected_proposed_cost
            or proposed_net != expected_proposed_net
        ):
            raise BusinessMonthError("business financial arithmetic does not reconcile")


def _validate_notion_diff(preview: Mapping[str, object]) -> None:
    diff = preview["notion_review_diff"]
    source = preview["source_binding"]
    entity = preview["entity"]
    financials = preview["financials"]
    if not all(isinstance(item, dict) for item in (diff, source, entity, financials)):
        raise BusinessMonthError("business Notion diff binding is malformed")
    expected_keys = {
        "schema",
        "target_data_source",
        "target_record_url",
        "target_source_record_id",
        "source_snapshot_hash",
        "source_row_hash",
        "property_diffs",
        "review_eligible",
        "executable",
        "write_eligible",
        "write_authorized",
        "write_attempted",
        "applied_count",
        "blockers",
        "diff_hash",
    }
    if set(diff) != expected_keys:
        raise BusinessMonthError("business Notion diff keys do not match the schema")
    body = dict(diff)
    supplied_hash = body.pop("diff_hash")
    if supplied_hash != canonical_hash(body):
        raise BusinessMonthError("business Notion diff hash does not match")
    if (
        diff["target_data_source"]
        != "collection://3c5f887a-4219-4ae6-a18a-82cf2d1841db"
        or diff["target_record_url"] != entity.get("source_url")
        or diff["target_source_record_id"] != entity.get("source_record_id")
        or diff["source_snapshot_hash"] != source.get("snapshot_hash")
        or diff["source_row_hash"] != source.get("row_hash")
        or diff["review_eligible"] is not True
        or diff["blockers"]
        != [
            "construction_mode_notion_read_only",
            "campaign_authority_has_not_accepted_preview_values",
            "no_write_adapter_is_present",
        ]
    ):
        raise BusinessMonthError("business Notion diff source or blocker binding drifted")
    property_diffs = diff["property_diffs"]
    if not isinstance(property_diffs, list) or len(property_diffs) != 2:
        raise BusinessMonthError("business Notion diff must contain two reviewed properties")
    expected_proposed = {
        "Monthly Revenue": financials["proposed_revenue"],
        "Monthly Cost": financials["proposed_cost"],
    }
    if [
        item.get("property_name") if isinstance(item, dict) else None
        for item in property_diffs
    ] != list(expected_proposed):
        raise BusinessMonthError(
            "business Notion property diffs are not in their canonical order"
        )
    seen: set[str] = set()
    properties = source.get("properties")
    if not isinstance(properties, dict):
        raise BusinessMonthError("business Notion diff has no source-property receipts")
    for item in property_diffs:
        if not isinstance(item, dict) or set(item) != {
            "property_name",
            "source_value",
            "source_property_hash",
            "proposed_value",
            "changed",
        }:
            raise BusinessMonthError("business Notion property diff is malformed")
        name = item["property_name"]
        if not isinstance(name, str) or name not in expected_proposed or name in seen:
            raise BusinessMonthError("business Notion property diff identity drifted")
        seen.add(name)
        receipt = properties.get(name)
        if not isinstance(receipt, dict):
            raise BusinessMonthError("business Notion diff lost a property receipt")
        before = receipt.get("source_value")
        after = expected_proposed[name]
        try:
            changed = Decimal(str(before)) != Decimal(str(after))
        except Exception as exc:
            raise BusinessMonthError("business Notion diff has malformed numeric values") from exc
        if (
            item["source_value"] != before
            or item["source_property_hash"] != receipt.get("property_hash")
            or item["proposed_value"] != after
            or item["changed"] is not changed
        ):
            raise BusinessMonthError("business Notion property diff does not reconcile")
    if seen != set(expected_proposed):
        raise BusinessMonthError("business Notion diff property set is incomplete")


def _roll_receipt(preview: Mapping[str, object], roll_key: str) -> Mapping[str, object]:
    manifest = preview.get("dice_manifest")
    if not isinstance(manifest, dict) or not isinstance(manifest.get("rolls"), list):
        raise BusinessMonthError("business dice manifest is malformed")
    matches = [
        item
        for item in manifest["rolls"]
        if isinstance(item, dict) and item.get("roll_key") == roll_key
    ]
    if len(matches) != 1:
        raise BusinessMonthError(f"business dice manifest has no unique {roll_key} roll")
    return matches[0]


def _bound_source_decimal(preview: Mapping[str, object], name: str) -> Decimal:
    source = preview.get("source_binding")
    if not isinstance(source, dict) or not isinstance(source.get("properties"), dict):
        raise BusinessMonthError("business source-property receipts are malformed")
    receipt = source["properties"].get(name)
    if not isinstance(receipt, dict):
        raise BusinessMonthError(f"business source-property receipt is missing {name}")
    try:
        result = Decimal(str(receipt["source_value"]))
    except Exception as exc:
        raise BusinessMonthError(f"business source-property receipt has malformed {name}") from exc
    if not result.is_finite():
        raise BusinessMonthError(f"business source-property receipt has non-finite {name}")
    return result


def _validate_source_binding(
    preview: Mapping[str, object], export: VerifiedRegistryExport
) -> None:
    source = preview["source_binding"]
    entity = preview["entity"]
    if not isinstance(source, dict) or not isinstance(entity, dict):
        raise BusinessMonthError("business source binding is malformed")
    source_id = entity.get("source_record_id")
    if not isinstance(source_id, str):
        raise BusinessMonthError("business source record ID is malformed")
    row = export.row(source_id)
    if (
        source.get("export_hash") != export.export_hash
        or source.get("snapshot_hash") != export.snapshot_hash
        or source.get("source_schema_hash") != export.source_schema_hash
        or source.get("transport_content_hash") != export.content_hash
        or source.get("row_hash") != export.row_hashes[source_id]
        or entity.get("name") != row["Entity"]
        or entity.get("source_url") != row["url"]
        or entity.get("status") != row["Status"]
        or entity.get("sector") != row["Sector"]
        or entity.get("source_last_updated") != row["Last Updated"]
    ):
        raise BusinessMonthError("business preview no longer matches its Registry source")
    _validate_eligible_row(export, source_id, row)
    properties = source.get("properties")
    if not isinstance(properties, dict):
        raise BusinessMonthError("business source properties are malformed")
    for name, receipt in properties.items():
        if (
            name not in export.property_names
            or not isinstance(receipt, dict)
            or receipt.get("source_value") != row[name]
            or receipt.get("property_hash") != export.property_hash(source_id, name)
        ):
            raise BusinessMonthError("business source property receipt does not match")


def _validate_assumptions(assumptions: Mapping[str, object]) -> None:
    if set(assumptions) != _ASSUMPTION_KEYS:
        raise BusinessMonthError("business assumptions do not match the locked schema")
    if assumptions["market"] not in _MARKET_MODIFIERS:
        raise BusinessMonthError("business market assumption is unsupported")
    for name in (
        "vara_active",
        "monopoly",
        "excellent_accounting",
        "rapid_expansion",
    ):
        if type(assumptions[name]) is not bool:
            raise BusinessMonthError(f"business assumption {name} must be boolean")
    streams = assumptions["revenue_streams"]
    managers = assumptions["competent_managers"]
    if type(streams) is not int or streams < 1:
        raise BusinessMonthError("business revenue streams must be a positive integer")
    if type(managers) is not int or not 0 <= managers <= 3:
        raise BusinessMonthError("business competent managers must be from 0 through 3")


def _validate_entity_and_source_receipts(
    entity: Mapping[str, object], source: Mapping[str, object]
) -> None:
    if set(entity) != _ENTITY_KEYS:
        raise BusinessMonthError("business entity does not match the locked schema")
    if set(source) != _SOURCE_BINDING_KEYS:
        raise BusinessMonthError("business source binding does not match the locked schema")
    for name in (
        "export_hash",
        "snapshot_hash",
        "source_schema_hash",
        "transport_content_hash",
        "row_hash",
    ):
        if not isinstance(source[name], str) or not _SHA256_RE.fullmatch(source[name]):
            raise BusinessMonthError(f"business source binding has malformed {name}")
    for name in ("name", "source_record_id", "source_url", "status", "sector"):
        _clean_text(entity[name], f"entity {name}")
    if not isinstance(entity["source_last_updated"], str) or not entity[
        "source_last_updated"
    ]:
        raise BusinessMonthError("entity source_last_updated must be non-empty text")
    source_id_match = _NOTION_SOURCE_ID_RE.fullmatch(entity["source_record_id"])
    if (
        source_id_match is None
        or entity["source_url"]
        != f"https://app.notion.com/{source_id_match.group(1)}"
    ):
        raise BusinessMonthError("business entity URL and source record ID disagree")
    properties = source["properties"]
    if not isinstance(properties, dict) or set(properties) != set(_CONSUMED_PROPERTIES):
        raise BusinessMonthError("business source-property set is incomplete or expanded")
    for name in _CONSUMED_PROPERTIES:
        receipt = properties[name]
        if (
            not isinstance(receipt, dict)
            or set(receipt) != {"source_value", "property_hash"}
            or not isinstance(receipt["property_hash"], str)
            or not _SHA256_RE.fullmatch(receipt["property_hash"])
        ):
            raise BusinessMonthError(f"business source-property receipt is malformed: {name}")
    entity_receipts = {
        "name": "Entity",
        "status": "Status",
        "sector": "Sector",
        "source_last_updated": "Last Updated",
    }
    for entity_name, property_name in entity_receipts.items():
        if entity[entity_name] != properties[property_name]["source_value"]:
            raise BusinessMonthError("business entity identity drifted from source receipts")
