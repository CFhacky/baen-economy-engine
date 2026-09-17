from collections import defaultdict
from decimal import Decimal, getcontext, setcontext
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
PR48_ACCOUNTS = ROOT.parent / "campaign-finance-ledger" / "ledger" / "accounts.bean"

from baen_economy import banking_sandbox as sandbox  # noqa: E402
from baen_economy.domain import Authority, TemporalState  # noqa: E402
from baen_economy.events import EventStore, ResolutionStatus  # noqa: E402
from baen_economy.finance import (  # noqa: E402
    JournalBook,
    JournalError,
    render_beancount,
)
from baen_economy.operator_codec import (  # noqa: E402
    canonical_dumps,
    verify_content_hash,
)


EXPECTED_TRANSACTIONS = (
    (
        "finance.bank_deposit",
        "bank_deposit",
        (
            ("Assets:NCF:Reserves", "asset", "1000", "GP"),
            ("Liabilities:NCF:Deposits", "liability", "-1000", "GP"),
        ),
    ),
    (
        "finance.loan_credit",
        "loan_credit",
        (
            ("Assets:NCF:Loans-Receivable", "asset", "600", "GP"),
            ("Liabilities:NCF:Deposits", "liability", "-600", "GP"),
        ),
    ),
    (
        "finance.loan_repayment",
        "loan_repayment_from_deposit",
        (
            ("Liabilities:NCF:Deposits", "liability", "110", "GP"),
            ("Assets:NCF:Loans-Receivable", "asset", "-100", "GP"),
            ("Income:NCF:Interest", "income", "-10", "GP"),
        ),
    ),
)


class PositiveBankingSandboxTests(unittest.TestCase):
    def test_identity_is_separate_synthetic_and_nonpostable(self) -> None:
        proposal = sandbox.build_positive_banking_sandbox()
        self.assertEqual(proposal["schema"], "tnp.economy.banking-sandbox-preview/1")
        self.assertEqual(proposal["sandbox_id"], "ncf-positive-banking-v1")
        self.assertIn("Synthetic / Non-Canonical", proposal["title"])
        self.assertEqual(proposal["status"], "preview_only")
        self.assertEqual(proposal["mode"], "synthetic_noncanonical")
        self.assertFalse(proposal["canonical"])
        self.assertTrue(proposal["proposal_only"])
        self.assertFalse(proposal["postable"])
        self.assertFalse(proposal["ledger_post_capability"])
        self.assertFalse(proposal["ledger_write_attempted"])
        self.assertFalse(proposal["beancount_exported"])
        self.assertEqual(
            proposal["timeline_id"], "preview:banking-sandbox:positive-v1"
        )
        self.assertNotIn("operation-laden-table", canonical_dumps(proposal))

    def test_exact_three_transactions_and_seven_postings(self) -> None:
        proposal = sandbox.build_positive_banking_sandbox()
        self.assertEqual(proposal["proposal_transaction_count"], 3)
        self.assertEqual(proposal["proposal_posting_count"], 7)
        self.assertEqual(proposal["posted_transaction_count"], 0)
        self.assertEqual(proposal["posted_posting_count"], 0)
        self.assertEqual(len(proposal["transactions"]), 3)
        self.assertEqual(len(proposal["source_event_refs"]), 3)

        for index, (transaction, expected) in enumerate(
            zip(proposal["transactions"], EXPECTED_TRANSACTIONS, strict=True), start=1
        ):
            source_type, proposal_type, postings = expected
            self.assertEqual(transaction["proposal_index"], index)
            self.assertFalse(transaction["postable"])
            self.assertEqual(transaction["source_event_type"], source_type)
            self.assertEqual(transaction["event_type"], proposal_type)
            self.assertEqual(
                tuple(
                    (
                        posting["account"],
                        posting["account_type"],
                        posting["amount"],
                        posting["currency"],
                    )
                    for posting in transaction["postings"]
                ),
                postings,
            )

    def test_every_transaction_and_the_whole_proposal_balance_by_currency(self) -> None:
        proposal = sandbox.build_positive_banking_sandbox()
        for transaction in proposal["transactions"]:
            totals = defaultdict(Decimal)
            for posting in transaction["postings"]:
                totals[posting["currency"]] += Decimal(posting["amount"])
            self.assertEqual(dict(totals), {"GP": Decimal("0")})
            self.assertEqual(
                transaction["totals_by_currency"],
                [{"currency": "GP", "amount": "0"}],
            )
        self.assertEqual(
            proposal["totals_by_currency"],
            [{"currency": "GP", "amount": "0"}],
        )

    def test_cumulative_bank_liability_and_revenue_semantics(self) -> None:
        proposal = sandbox.build_positive_banking_sandbox()
        deltas = {
            item["account"]: Decimal(item["amount"])
            for item in proposal["cumulative_account_deltas"]
        }
        self.assertEqual(
            deltas,
            {
                "Assets:NCF:Reserves": Decimal("1000"),
                "Assets:NCF:Loans-Receivable": Decimal("500"),
                "Liabilities:NCF:Deposits": Decimal("-1490"),
                "Income:NCF:Interest": Decimal("-10"),
            },
        )
        self.assertEqual(
            deltas["Assets:NCF:Reserves"]
            + deltas["Assets:NCF:Loans-Receivable"]
            + deltas["Liabilities:NCF:Deposits"]
            + deltas["Income:NCF:Interest"],
            Decimal("0"),
        )
        accounts = set(deltas)
        self.assertFalse(any(account.startswith("Equity:") for account in accounts))
        self.assertFalse(any(account.startswith("Expenses:") for account in accounts))
        self.assertNotIn("Assets:Treasury:Cash", accounts)
        self.assertNotIn("Liabilities:NCF:Notes-Outstanding", accounts)

    def test_deposit_and_loan_draw_are_not_revenue(self) -> None:
        transactions = sandbox.build_positive_banking_sandbox()["transactions"]
        for transaction in transactions[:2]:
            self.assertFalse(
                any(
                    posting["account"].startswith("Income:")
                    for posting in transaction["postings"]
                )
            )
        loan_accounts = {
            posting["account"] for posting in transactions[1]["postings"]
        }
        self.assertEqual(
            loan_accounts,
            {"Assets:NCF:Loans-Receivable", "Liabilities:NCF:Deposits"},
        )
        self.assertNotIn("Assets:NCF:Reserves", loan_accounts)
        repayment = {
            posting["account"]: posting["amount"]
            for posting in transactions[2]["postings"]
        }
        self.assertEqual(repayment["Assets:NCF:Loans-Receivable"], "-100")
        self.assertEqual(repayment["Income:NCF:Interest"], "-10")

    def test_chart_contract_matches_the_existing_pr48_gp_accounts(self) -> None:
        proposal = sandbox.build_positive_banking_sandbox()
        self.assertEqual(
            hashlib.sha256(PR48_ACCOUNTS.read_bytes()).hexdigest(),
            proposal["chart_contract"]["sha256"],
        )
        opened = {}
        for raw_line in PR48_ACCOUNTS.read_text(encoding="utf-8").splitlines():
            parts = raw_line.split()
            if len(parts) >= 4 and parts[1] == "open":
                opened[parts[2]] = (parts[0], tuple(parts[3].split(",")))
        chart_accounts = proposal["chart_contract"]["accounts"]
        self.assertEqual(
            [item["account"] for item in chart_accounts],
            [
                "Assets:NCF:Reserves",
                "Assets:NCF:Loans-Receivable",
                "Liabilities:NCF:Deposits",
                "Income:NCF:Interest",
            ],
        )
        for item in chart_accounts:
            self.assertEqual(opened[item["account"]], ("2026-01-01", ("GP",)))

    def test_preview_sources_are_triple_blocked_from_the_actual_book(self) -> None:
        events = sandbox._build_journal_events()
        store = EventStore()
        for event in events:
            store.append(event.source_event)
            self.assertEqual(event.source_event.authority, Authority.SCENARIO_ASSUMPTION)
            self.assertEqual(event.source_event.temporal_state, TemporalState.PROJECTED)
            self.assertEqual(
                event.source_event.resolution_status, ResolutionStatus.RESOLVED
            )
            self.assertNotEqual(event.source_event.timeline_id, "actual")
            self.assertFalse(event.source_event.may_mutate_actual)

        book = JournalBook(sandbox._SANDBOX_CHART, store)
        for event in events:
            with self.assertRaisesRegex(JournalError, "may not mutate"):
                book.post(event)
            with self.assertRaisesRegex(JournalError, "already validated"):
                render_beancount(book, event.event_id)
        self.assertEqual(book.events, ())

    def test_canonical_json_and_content_hash_are_deterministic(self) -> None:
        first = sandbox.build_positive_banking_sandbox()
        second = sandbox.build_positive_banking_sandbox()
        self.assertEqual(first, second)
        verify_content_hash(first, label="positive banking sandbox")
        rendered = sandbox.render_positive_banking_sandbox_json()
        self.assertEqual(rendered, canonical_dumps(first))
        self.assertEqual(json.loads(rendered), first)

    def test_decimal_output_ignores_the_ambient_decimal_context(self) -> None:
        original = getcontext().copy()
        try:
            getcontext().prec = 2
            low_precision = sandbox.render_positive_banking_sandbox_json()
            getcontext().prec = 28
            normal_precision = sandbox.render_positive_banking_sandbox_json()
        finally:
            setcontext(original)
        self.assertEqual(low_precision, normal_precision)

    def test_generation_exposes_no_post_render_or_file_write_surface(self) -> None:
        self.assertFalse(hasattr(sandbox, "JournalBook"))
        self.assertFalse(hasattr(sandbox, "render_beancount"))
        blocked = AssertionError("sandbox attempted filesystem mutation")
        with (
            patch.object(Path, "write_text", side_effect=blocked),
            patch.object(Path, "write_bytes", side_effect=blocked),
            patch.object(Path, "touch", side_effect=blocked),
        ):
            proposal = sandbox.build_positive_banking_sandbox()
            rendered = sandbox.render_positive_banking_sandbox_json()
        self.assertFalse(proposal["ledger_write_attempted"])
        self.assertFalse(proposal["beancount_exported"])
        self.assertEqual(json.loads(rendered), proposal)


if __name__ == "__main__":
    unittest.main()
