"""Read-only financial close: partial evidence is never a balanced opening book."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext, Context
import json
from pathlib import Path
from typing import Any

from .corridor_finance import corridor_finance_snapshot
from .empire_close import load_close_recovery
from .domain import canonical_decimal

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FINANCIAL_CLOSE = ROOT / "recovery/FINANCIAL_CLOSE_2026-09-18.json"
ACCEPTED = {"USER-RULED", "SOURCE-DERIVED", "UPSTREAM-ADOPTED"}


class FinancialCloseError(ValueError):
    pass


def _amount(value: object) -> Decimal:
    if type(value) not in (str, int):
        raise FinancialCloseError("money must be an exact decimal string or integer")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise FinancialCloseError("invalid money") from exc
    if not result.is_finite() or result < 0:
        raise FinancialCloseError("money must be finite and nonnegative")
    return result


def settlement_progress(target: dict[str, Any], receipts: list[dict[str, Any]]) -> dict[str, Any]:
    """Count only evidenced net settlements for this target; no ledger writes."""
    if target.get("authority") not in ACCEPTED or not target.get("source"):
        raise FinancialCloseError("target lacks accepted authority/source")
    target_amount = _amount(target["amount_gp"])
    seen = set()
    admitted = []
    excluded = []
    with localcontext(Context(prec=40)):
        total = Decimal(0)
        for row in receipts:
            receipt_id = row.get("id")
            if not isinstance(receipt_id, str) or not receipt_id or receipt_id in seen:
                raise FinancialCloseError("settlement receipt IDs must be unique and nonempty")
            seen.add(receipt_id)
            if row.get("status") != "NET_SETTLED" or row.get("target_id") != target["id"]:
                excluded.append(receipt_id)
                continue
            if (row.get("authority") not in ACCEPTED or not row.get("source")
                    or row.get("temporal_scope") != "CURRENT_OPERATION"):
                raise FinancialCloseError("settled receipt lacks current accepted evidence")
            total += _amount(row.get("net_settled_gp"))
            admitted.append(receipt_id)
        return {"target_gp": canonical_decimal(target_amount),
                "net_settled_gp": canonical_decimal(total),
                "remaining_gp": canonical_decimal(max(Decimal(0), target_amount - total)),
                "surplus_gp": canonical_decimal(max(Decimal(0), total - target_amount)),
                "admitted_receipt_ids": admitted, "excluded_receipt_ids": excluded,
                "scope": "This operation only; not total empire cash",
                "postings_created": 0}


def financial_close_snapshot(path: Path = DEFAULT_FINANCIAL_CLOSE) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FinancialCloseError("cannot read financial close evidence") from exc
    if (data.get("schema") != "tnp.economy.financial-close/1"
            or data.get("campaign_boundary") != "Day 7 Hammer 1495 DR"):
        raise FinancialCloseError("financial close schema or campaign boundary mismatch")
    close = load_close_recovery()
    lane = close["lanes"]["ncf_finance"]
    facts = {r["key"]: r for r in lane["facts"]}
    loans = []
    for slug, borrower in (("dockworkers_guild", "Dockworkers Guild"),
                           ("selah_thorn", "Selah Thorn"),
                           ("swiftfingers", "Captain Philo Swiftfingers")):
        principal = facts[f"loan.{slug}.principal_gp"]
        rate = facts[f"loan.{slug}.rate_pct"]
        if principal["authority"] not in ACCEPTED or rate["authority"] not in ACCEPTED:
            raise FinancialCloseError("loan register contains unaccepted authority")
        loans.append({"id": slug, "borrower": borrower, "status": "ACTIVE_SOURCE_ANCHOR",
                      "principal_gp": canonical_decimal(_amount(principal["value"])),
                      "annual_rate_percent": rate["value"], "source": principal["source"],
                      "authority": principal["authority"], "repayment_schedule": None,
                      "settled_interest_gp": None})
    portfolio = _amount(facts["ncf.active_loan_portfolio_gp"]["value"])
    with localcontext(Context(prec=40)):
        named = sum((_amount(r["principal_gp"]) for r in loans), Decimal(0))
        if named > portfolio:
            raise FinancialCloseError("named loans exceed parent portfolio")
        residual = portfolio - named
    corridor = corridor_finance_snapshot()
    accounts = [
        {"account": "Assets:NCF:Loans-Receivable", "amount_gp": canonical_decimal(portfolio),
         "authority": facts["ncf.active_loan_portfolio_gp"]["authority"],
         "source": facts["ncf.active_loan_portfolio_gp"]["source"]},
        *[{"account": account, "amount_gp": None, "authority": "UNRESOLVED"}
          for account in ("Assets:NCF:Reserves", "Assets:NCF:Other",
                          "Liabilities:NCF:Deposits", "Liabilities:NCF:Other",
                          "Equity:NCF:Capital-And-Retained-Earnings")],
    ]
    land = corridor["land_bank"]
    interests = land["esamt_interests"]
    return {
        "schema": "tnp.economy.financial-close-status/1",
        "campaign_boundary": data["campaign_boundary"],
        "status": "INCOMPLETE_OPENING_BOOK",
        "loans": {"parent_principal_gp": canonical_decimal(portfolio),
                  "named_principal_gp": canonical_decimal(named),
                  "unitemized_principal_gp": canonical_decimal(residual),
                  "aggregate_includes_named": True, "active": loans,
                  "approved_undrawn": [{"borrower": "Snowfall Hearthworks",
                      "facility_gp": facts["snowfall.approved_facility_gp"]["value"],
                      "principal_drawn_gp": "0", "annual_rate_percent": 8,
                      "source": facts["snowfall.approved_facility_gp"]["source"]}],
                  "historical_unreconciled": lane["historical_loan_evidence"],
                  "average_apr": None, "interest_receipts_gp": None},
        "trial_balance": {"scope": "NCF parent only; no treasury/client consolidation",
                          "accounts": accounts, "balanced": None,
                          "assets_total_gp": None, "liabilities_total_gp": None,
                          "equity_total_gp": None, "balancing_plug_created": False},
        "treasury": {"opening_liquid_cash_gp": None, "closing_liquid_cash_gp": None,
                     "post_boundary_cash_delta_gp": None,
                     "reason": "No complete opening balance or accepted post-boundary journal attached",
                     "delta_capability": "JournalBook.position_report preserves unknown openings"},
        "protected_liquidity": settlement_progress(data["protected_target"], data["settlement_evidence"]),
        "liquidity_evidence": data["liquidity_evidence"],
        "land_register": [{"id": "arterial-corridor-envelope", "record_kind": "COLLECTION_NOT_PARCEL",
            "legal_titleholder": None, "beneficial_owner": land["beneficial_owner"],
            "gross_strip_acres": land["gross_strip_acres_at_500_mile_floor"],
            "unique_titled_acres": None, "cost_basis_gp": None, "appraisal_gp": None,
            "leases": None, "mineral_rights": None, "timber_rights": None,
            "water_rights": None, "liens": None, "unrealized_appreciation_gp": None,
            "realized_gain_gp": None, "sale_proceeds_settled_gp": None,
            "source": "User corridor ruling 2026-09-18; Arterial Road Network",
            "valuation_included_in_operating_cash": False}],
        "client_interests": {"beneficiary": interests["beneficiary"],
            "vehicle": "ESAMT", "manager": interests["manager"],
            "included_in_ncf_owned_assets": False,
            "arterial_percentage": None, "hunding_percentage": None,
            "hunding_recollection": interests["hunding_current_stake_recollection"],
            "hunding_full_acquisition": interests["hunding_acquisition_completion"],
            "settled_cost_basis_gp": None, "rights_scope": None},
        "can_authorize_capital_from_this_report": False,
        "canonical": False, "notion_writes": 0, "canonical_ledger_postings": 0,
        "campaign_time_advanced": False,
    }
