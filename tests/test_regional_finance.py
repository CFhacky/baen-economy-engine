from decimal import Decimal, getcontext, setcontext
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from baen_economy.regional_finance import (  # noqa: E402
    RegionalFinanceError,
    simulate_regional_finance,
)


OPENING = (
    {
        "entity_id": "enterprise:quarry",
        "entity_type": "enterprise",
        "balances": {"cash": "1000", "inventory": "0"},
    },
    {
        "entity_id": "enterprise:brickworks",
        "entity_type": "enterprise",
        "balances": {"cash": "500"},
    },
    {
        "entity_id": "bank:ncf",
        "entity_type": "bank",
        "balances": {"reserves": "500"},
    },
    {
        "entity_id": "treasury:central",
        "entity_type": "treasury",
        "balances": {"cash": "0"},
    },
)


EVENTS = (
    {
        "event_id": "sale:quarry:01",
        "kind": "enterprise_sale",
        "entity_id": "enterprise:quarry",
        "amount": "600",
    },
    {
        "event_id": "purchase:brickworks:01",
        "kind": "enterprise_purchase",
        "entity_id": "enterprise:brickworks",
        "amount": "200",
        "treatment": "inventory",
    },
    {
        "event_id": "payroll:quarry:01",
        "kind": "payroll",
        "entity_id": "enterprise:quarry",
        "amount": "100",
    },
    {
        "event_id": "deposit:quarry:01",
        "kind": "bank_deposit",
        "bank_id": "bank:ncf",
        "depositor_id": "enterprise:quarry",
        "amount": "500",
    },
    {
        "event_id": "loan:brickworks:01",
        "kind": "loan_origination",
        "loan_id": "loan:ncf-brickworks-01",
        "bank_id": "bank:ncf",
        "borrower_id": "enterprise:brickworks",
        "amount": "1200",
        "annual_interest_rate": "0.12",
    },
    {
        "event_id": "interest:brickworks:01",
        "kind": "loan_interest_accrual",
        "loan_id": "loan:ncf-brickworks-01",
    },
    {
        "event_id": "interest-payment:brickworks:01",
        "kind": "loan_interest_payment",
        "loan_id": "loan:ncf-brickworks-01",
    },
    {
        "event_id": "principal:brickworks:01",
        "kind": "loan_principal_repayment",
        "loan_id": "loan:ncf-brickworks-01",
        "amount": "100",
    },
    {
        "event_id": "default:brickworks:01",
        "kind": "loan_default",
        "loan_id": "loan:ncf-brickworks-01",
        "amount": "200",
    },
    {
        "event_id": "tax-assessment:quarry:01",
        "kind": "treasury_tax_assessment",
        "treasury_id": "treasury:central",
        "taxpayer_id": "enterprise:quarry",
        "amount": "50",
    },
    {
        "event_id": "tax-receipt:quarry:01",
        "kind": "treasury_tax_receipt",
        "treasury_id": "treasury:central",
        "taxpayer_id": "enterprise:quarry",
        "amount": "50",
    },
    {
        "event_id": "treasury-receipt:01",
        "kind": "treasury_receipt",
        "treasury_id": "treasury:central",
        "amount": "20",
    },
)


def run_month():
    return simulate_regional_finance(
        period="1495-01",
        opening_positions=OPENING,
        events=EVENTS,
    )


class RegionalFinanceTests(unittest.TestCase):
    def test_operating_month_exposes_required_bank_treasury_and_safety_outcomes(self) -> None:
        result = run_month()
        self.assertEqual(result["schema"], "tnp.economy.regional-finance-preview/1")
        self.assertEqual(result["mode"], "simulation_sidecar")
        self.assertFalse(result["canonical"])
        self.assertEqual(result["notion_writes"], 0)
        self.assertEqual(result["canonical_ledger_postings"], 0)
        self.assertEqual(
            result["safety"],
            {
                "notion_write_capability": False,
                "notion_writes": 0,
                "canonical_ledger_post_capability": False,
                "canonical_ledger_postings": 0,
            },
        )
        self.assertEqual(result["banking"]["deposits_received"], "500")
        self.assertEqual(result["banking"]["deposit_change"], "1588.00")
        self.assertEqual(result["banking"]["loan_originations"], "1200")
        self.assertEqual(result["banking"]["interest_accrued"], "12.00")
        self.assertEqual(result["banking"]["interest_received"], "12.00")
        self.assertEqual(result["banking"]["principal_repaid"], "100")
        self.assertEqual(result["banking"]["default_exposure"], "200")
        self.assertEqual(result["banking"]["ending_gross_loans"], "1100")
        self.assertEqual(result["banking"]["ending_net_loans"], "900")
        self.assertEqual(result["treasury"]["tax_assessed"], "50")
        self.assertEqual(result["treasury"]["receipts_total"], "70")
        self.assertEqual(result["treasury"]["ending_cash"], "70")
        self.assertEqual(result["state"]["schema"], "tnp.economy.regional-finance-state/1")
        self.assertEqual(result["state"]["balances"], result["ending_balances"])
        self.assertEqual(result["state"]["loans"], result["loan_portfolio"])

    def test_every_transaction_and_complete_journal_balance_exactly(self) -> None:
        result = run_month()
        journal = result["journal"]
        self.assertTrue(journal["balanced"])
        self.assertEqual(journal["total_debits"], journal["total_credits"])
        self.assertEqual(journal["imbalance"], "0.00")
        self.assertEqual(journal["transaction_count"], len(OPENING) - 1 + len(EVENTS))
        self.assertGreater(journal["posting_count"], journal["transaction_count"] * 2)
        for transaction in result["transactions"]:
            self.assertTrue(transaction["balanced"])
            self.assertEqual(transaction["debits"], transaction["credits"])
            totals = {}
            for posting in transaction["postings"]:
                key = posting["entity_id"]
                totals[key] = totals.get(key, Decimal(0)) + Decimal(posting["amount"])
            self.assertTrue(all(total == 0 for total in totals.values()))

    def test_loan_entries_are_balance_sheet_financing_not_fake_revenue(self) -> None:
        result = run_month()
        transactions = {item["kind"]: item for item in result["transactions"]}
        origination = transactions["loan_origination"]
        self.assertFalse(
            any(posting["account_type"] in {"income", "expense"} for posting in origination["postings"])
        )
        accrual = transactions["loan_interest_accrual"]
        self.assertEqual(
            {(p["account"], p["amount"]) for p in accrual["postings"]},
            {
                ("interest_receivable:loan:ncf-brickworks-01", "12.00"),
                ("interest_income", "-12.00"),
                ("interest_expense", "12.00"),
                ("interest_payable:loan:ncf-brickworks-01", "-12.00"),
            },
        )
        portfolio = result["loan_portfolio"][0]
        self.assertEqual(portfolio["principal_outstanding"], "1100")
        self.assertEqual(portfolio["interest_unpaid"], "0.00")
        self.assertEqual(portfolio["net_exposure"], "900")

    def test_consolidated_statements_eliminate_internal_financial_claims(self) -> None:
        result = run_month()
        balance_sheet = result["reports"]["balance_sheet"]
        self.assertEqual(balance_sheet["assets"], "2520.00")
        self.assertEqual(balance_sheet["liabilities"], "0.00")
        self.assertEqual(balance_sheet["equity"], "2000")
        self.assertEqual(balance_sheet["net_income"], "520.00")
        self.assertEqual(balance_sheet["equation_imbalance"], "0.00")
        self.assertEqual(balance_sheet["eliminations"]["bank_deposits"], "1588.00")
        self.assertEqual(balance_sheet["eliminations"]["loan_principal"], "1100")
        income = result["reports"]["income_statement"]
        self.assertEqual(
            income,
            {
                "income": "620.00",
                "expenses": "100.00",
                "net_income": "520.00",
                "monthly_surplus": "520.00",
            },
        )
        cash_flow = result["reports"]["cash_flow"]
        self.assertTrue(cash_flow["reconciles"])
        self.assertEqual(cash_flow["opening_settlement_cash"], "2000")
        self.assertEqual(cash_flow["net_change"], "320")
        self.assertEqual(cash_flow["ending_settlement_cash"], "2320")
        self.assertEqual(cash_flow["reconciliation_imbalance"], "0")

    def test_external_bank_settlement_moves_reserves_and_deposit_liability(self) -> None:
        opening = (
            {"entity_id": "enterprise:mill", "entity_type": "enterprise", "balances": {"cash": "0"}},
            {"entity_id": "bank:ncf", "entity_type": "bank", "balances": {"reserves": "100"}},
        )
        events = (
            {
                "event_id": "sale:mill:bank",
                "kind": "enterprise_sale",
                "entity_id": "enterprise:mill",
                "amount": "80",
                "settlement": "bank_deposit",
                "bank_id": "bank:ncf",
            },
            {
                "event_id": "payroll:mill:bank",
                "kind": "payroll",
                "entity_id": "enterprise:mill",
                "amount": "30",
                "settlement": "bank_deposit",
                "bank_id": "bank:ncf",
            },
        )
        result = simulate_regional_finance(period="1495-02", opening_positions=opening, events=events)
        self.assertEqual(result["banking"]["ending_customer_deposits"], "50")
        balances = {(row["entity_id"], row["account"]): row["signed_balance"] for row in result["ending_balances"]}
        self.assertEqual(balances[("bank:ncf", "reserves")], "150")
        self.assertEqual(balances[("enterprise:mill", "bank_deposit:bank:ncf")], "50")

    def test_delivered_internal_trade_transfers_cash_and_books_both_enterprises_once(self) -> None:
        result = simulate_regional_finance(
            period="1495-02",
            opening_positions=(
                {
                    "entity_id": "enterprise:quarry",
                    "entity_type": "enterprise",
                    "balances": {"cash": "10"},
                },
                {
                    "entity_id": "enterprise:brickworks",
                    "entity_type": "enterprise",
                    "balances": {"cash": "100"},
                },
            ),
            events=(
                {
                    "event_id": "trade:clay:01",
                    "kind": "enterprise_trade",
                    "seller_id": "enterprise:quarry",
                    "buyer_id": "enterprise:brickworks",
                    "amount": "40",
                    "treatment": "expense",
                },
            ),
        )
        trade = next(item for item in result["transactions"] if item["kind"] == "enterprise_trade")
        self.assertEqual(len(trade["postings"]), 4)
        self.assertEqual(result["reports"]["cash_flow"]["net_change"], "0")
        self.assertEqual(result["reports"]["income_statement"]["net_income"], "0")
        balances = {
            (row["entity_id"], row["account"]): row["signed_balance"]
            for row in result["ending_balances"]
        }
        self.assertEqual(balances[("enterprise:quarry", "cash")], "50")
        self.assertEqual(balances[("enterprise:brickworks", "cash")], "60")

    def test_trade_splits_goods_receipts_from_known_carrier_fee(self) -> None:
        result = simulate_regional_finance(
            period="1495-02",
            opening_positions=(
                {
                    "entity_id": "enterprise:buyer",
                    "entity_type": "enterprise",
                    "balances": {"cash": "100"},
                },
            ),
            events=(
                {
                    "event_id": "trade:delivered:01",
                    "kind": "enterprise_trade",
                    "seller_id": "enterprise:seller",
                    "buyer_id": "enterprise:buyer",
                    "carrier_id": "enterprise:carrier",
                    "amount": "75",
                    "goods_amount": "60",
                    "transport_amount": "15",
                    "treatment": "expense",
                },
            ),
        )
        balances = {
            (row["entity_id"], row["account"]): row["signed_balance"]
            for row in result["ending_balances"]
        }
        self.assertEqual(balances[("enterprise:seller", "cash")], "60")
        self.assertEqual(balances[("enterprise:carrier", "cash")], "15")
        self.assertEqual(balances[("enterprise:carrier", "transport_revenue")], "-15")
        self.assertEqual(balances[("enterprise:buyer", "cash")], "25")
        self.assertEqual(result["reports"]["cash_flow"]["net_change"], "0")
        with self.assertRaisesRegex(RegionalFinanceError, "supplied together"):
            simulate_regional_finance(
                period="1495-02",
                opening_positions=(),
                events=(
                    {
                        "event_id": "trade:bad:01",
                        "kind": "enterprise_trade",
                        "seller_id": "enterprise:seller",
                        "buyer_id": "enterprise:buyer",
                        "amount": "75",
                        "goods_amount": "60",
                    },
                ),
            )

    def test_outflows_cannot_overdraw_cash_or_deposits(self) -> None:
        with self.assertRaisesRegex(RegionalFinanceError, "insufficient cash"):
            simulate_regional_finance(
                period="1495-01",
                opening_positions=(
                    {"entity_id": "enterprise:mill", "entity_type": "enterprise", "balances": {"cash": "10"}},
                ),
                events=(
                    {"event_id": "payroll:1", "kind": "payroll", "entity_id": "enterprise:mill", "amount": "11"},
                ),
            )
        with self.assertRaisesRegex(RegionalFinanceError, "insufficient bank_deposit"):
            simulate_regional_finance(
                period="1495-01",
                opening_positions=(
                    {"entity_id": "bank:ncf", "entity_type": "bank", "balances": {"reserves": "100"}},
                ),
                events=(
                    {
                        "event_id": "loan:1",
                        "kind": "loan_origination",
                        "loan_id": "loan:1",
                        "bank_id": "bank:ncf",
                        "borrower_id": "enterprise:mill",
                        "amount": "20",
                        "annual_interest_rate": "0.12",
                    },
                    {
                        "event_id": "payroll:1",
                        "kind": "payroll",
                        "entity_id": "enterprise:mill",
                        "amount": "1",
                        "settlement": "bank_deposit",
                        "bank_id": "bank:ncf",
                    },
                    {"event_id": "principal:1", "kind": "loan_principal_repayment", "loan_id": "loan:1", "amount": "20"},
                ),
            )

    def test_tax_receipts_and_loan_repayments_cannot_exceed_open_items(self) -> None:
        with self.assertRaisesRegex(RegionalFinanceError, "tax receipt exceeds"):
            simulate_regional_finance(
                period="1495-01",
                opening_positions=(
                    {"entity_id": "enterprise:mill", "entity_type": "enterprise", "balances": {"cash": "100"}},
                ),
                events=(
                    {
                        "event_id": "tax:1",
                        "kind": "treasury_tax_assessment",
                        "treasury_id": "treasury:central",
                        "taxpayer_id": "enterprise:mill",
                        "amount": "10",
                    },
                    {
                        "event_id": "tax-pay:1",
                        "kind": "treasury_tax_receipt",
                        "treasury_id": "treasury:central",
                        "taxpayer_id": "enterprise:mill",
                        "amount": "11",
                    },
                ),
            )

    def test_repayment_after_default_reverses_allowance_without_negative_exposure(self) -> None:
        result = simulate_regional_finance(
            period="1495-01",
            events=(
                {
                    "event_id": "loan:1",
                    "kind": "loan_origination",
                    "loan_id": "loan:1",
                    "bank_id": "bank:ncf",
                    "borrower_id": "enterprise:mill",
                    "amount": "100",
                    "annual_interest_rate": "0",
                },
                {"event_id": "default:1", "kind": "loan_default", "loan_id": "loan:1", "amount": "80"},
                {
                    "event_id": "principal:1",
                    "kind": "loan_principal_repayment",
                    "loan_id": "loan:1",
                    "amount": "30",
                },
            ),
        )
        self.assertEqual(result["banking"]["ending_gross_loans"], "70")
        self.assertEqual(result["banking"]["default_exposure"], "50")
        self.assertEqual(result["banking"]["ending_net_loans"], "20")
        self.assertEqual(result["reports"]["balance_sheet"]["equation_imbalance"], "0")
        with self.assertRaisesRegex(RegionalFinanceError, "principal repayment exceeds"):
            simulate_regional_finance(
                period="1495-01",
                opening_positions=(),
                events=(
                    {
                        "event_id": "loan:1",
                        "kind": "loan_origination",
                        "loan_id": "loan:1",
                        "bank_id": "bank:ncf",
                        "borrower_id": "enterprise:mill",
                        "amount": "20",
                        "annual_interest_rate": "0.12",
                    },
                    {"event_id": "principal:1", "kind": "loan_principal_repayment", "loan_id": "loan:1", "amount": "21"},
                ),
            )

    def test_invalid_or_ambiguous_input_fails_closed(self) -> None:
        bad_events = (
            {"event_id": "x", "kind": "payroll", "entity_id": "enterprise:x", "amount": 1.5},
        )
        with self.assertRaisesRegex(RegionalFinanceError, "binary floating point"):
            simulate_regional_finance(period="1495-01", events=bad_events)
        with self.assertRaisesRegex(RegionalFinanceError, "unsupported finance event kind"):
            simulate_regional_finance(period="1495-01", events=({"event_id": "x", "kind": "magic_money"},))
        with self.assertRaisesRegex(RegionalFinanceError, "duplicate event_id"):
            simulate_regional_finance(
                period="1495-01",
                opening_positions=(
                    {"entity_id": "enterprise:x", "entity_type": "enterprise", "balances": {"cash": "10"}},
                ),
                events=(
                    {"event_id": "same", "kind": "payroll", "entity_id": "enterprise:x", "amount": "1"},
                    {"event_id": "same", "kind": "payroll", "entity_id": "enterprise:x", "amount": "1"},
                ),
            )

    def test_result_is_deterministic_json_and_ignores_ambient_decimal_context(self) -> None:
        original = getcontext().copy()
        try:
            getcontext().prec = 3
            first = run_month()
            getcontext().prec = 28
            second = run_month()
        finally:
            setcontext(original)
        self.assertEqual(first, second)
        self.assertEqual(json.loads(json.dumps(first, sort_keys=True)), first)


if __name__ == "__main__":
    unittest.main()
