from dataclasses import replace
from decimal import Decimal, getcontext, setcontext
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
PR48_ACCOUNTS = ROOT.parent / "campaign-finance-ledger" / "ledger" / "accounts.bean"

from baen_economy.domain import Authority, TemporalState  # noqa: E402
from baen_economy.events import (  # noqa: E402
    CampaignDate, EventEnvelope, EventStore, ResolutionStatus,
)
from baen_economy.finance import (  # noqa: E402
    AccountOpen, JournalBook, JournalError, JournalEvent, Posting, ncf_deposit,
    ncf_loan_credit, ncf_loan_repayment_from_deposit, render_beancount,
    treasury_borrowing,
)


D = Decimal


ENTITY_BY_TYPE = {
    "finance.bank_deposit": "entity:northern-crown-financial",
    "finance.loan_credit": "entity:northern-crown-financial",
    "finance.loan_repayment": "entity:northern-crown-financial",
    "finance.treasury_borrowing": "entity:central-treasury",
}


def source_event(
    event_type="finance.bank_deposit",
    payload=None,
    *,
    key="fixture:finance-1",
    authority=Authority.CAMPAIGN_RESOLUTION,
    temporal_state=TemporalState.CURRENT,
    resolution_status=ResolutionStatus.RESOLVED,
    source_ref="fixture:finance",
    event_revision=1,
    reverses_event_id=None,
    model_version="economy-0.1",
):
    if payload is None:
        payload = {"amount": D("1000"), "currency": "GP", "customer_slug": "merchant-one"}
    return EventEnvelope.create(
        source_event_key=key,
        event_revision=event_revision,
        timeline_id="actual",
        model_version=model_version,
        campaign_date=CampaignDate(1, "Synthetic 1"),
        phase="finance",
        sequence=1,
        authority=authority,
        temporal_state=temporal_state,
        resolution_status=resolution_status,
        source_ref=source_ref,
        event_type=event_type,
        subject_entity_id=ENTITY_BY_TYPE.get(event_type, "entity:northern-crown-financial"),
        payload=payload,
        reverses_event_id=reverses_event_id,
    )


def accepted_store(event):
    store = EventStore()
    store.append(event)
    return store


def chart_for(event):
    chart = {}
    for posting in event.postings:
        chart.setdefault(posting.account, set()).add(posting.currency)
    return {
        account: AccountOpen(tuple(sorted(currencies)), "2026-01-01")
        for account, currencies in chart.items()
    }


def pr48_chart():
    chart = {}
    for raw_line in PR48_ACCOUNTS.read_text(encoding="utf-8").splitlines():
        parts = raw_line.split()
        if len(parts) >= 4 and parts[1] == "open":
            chart[parts[2]] = AccountOpen(tuple(parts[3].split(",")), parts[0])
    return chart


class FinanceTests(unittest.TestCase):
    def test_deposit_creates_asset_and_liability_not_income(self):
        source = source_event()
        event = ncf_deposit(source_event=source, book_date="2026-01-01")
        accounts = {posting.account for posting in event.postings}
        self.assertIn("Assets:NCF:Reserves", accounts)
        self.assertIn("Liabilities:NCF:Deposits", accounts)
        self.assertFalse(any(account.startswith("Income:") for account in accounts))

    def test_created_loan_credits_deposit_liability(self):
        source = source_event(
            "finance.loan_credit",
            {"amount": D("600"), "currency": "GP", "borrower_slug": "borrower-one"},
        )
        event = ncf_loan_credit(source_event=source, book_date="2026-01-02")
        self.assertEqual(sum((posting.amount for posting in event.postings), D("0")), D("0"))
        self.assertEqual(event.postings[0].amount, D("600"))
        self.assertEqual(event.postings[1].amount, D("-600"))

    def test_treasury_borrowing_is_exactly_cash_and_debt(self):
        source = source_event(
            "finance.treasury_borrowing",
            {"amount": D("250000"), "currency": "GP", "lender_slug": "external-lender"},
        )
        event = treasury_borrowing(source_event=source, book_date="2026-01-03")
        self.assertEqual(len(event.postings), 2)
        self.assertFalse(any(posting.account.startswith("Income:") for posting in event.postings))
        self.assertIn("Liabilities:Debt:External", {p.account for p in event.postings})

    def test_principal_repayment_is_separate_from_interest(self):
        source = source_event(
            "finance.loan_repayment",
            {"principal": D("100"), "interest": D("10"), "currency": "GP", "borrower_slug": "borrower-one"},
        )
        event = ncf_loan_repayment_from_deposit(source_event=source, book_date="2026-01-04")
        values = {posting.account: posting.amount for posting in event.postings}
        self.assertEqual(values["Liabilities:NCF:Deposits"], D("110"))
        self.assertEqual(values["Assets:NCF:Loans-Receivable"], D("-100"))
        self.assertEqual(values["Income:NCF:Interest"], D("-10"))

    def test_unresolved_or_scenario_source_cannot_post(self):
        for source in (
            source_event(resolution_status=ResolutionStatus.PENDING),
            source_event(key="fixture:scenario", authority=Authority.SCENARIO_ASSUMPTION),
            source_event(key="fixture:forward", temporal_state=TemporalState.FORWARD_RESOLVED),
        ):
            event = ncf_deposit(source_event=source, book_date="2026-01-01")
            book = JournalBook(chart_for(event), accepted_store(source))
            with self.assertRaisesRegex(JournalError, "may not mutate"):
                book.post(event)

    def test_unknown_source_event_type_is_rejected(self):
        source = source_event("finance.bank_deposti")
        store = accepted_store(source)
        event = JournalEvent(
            source, "2026-01-01", "entity:northern-crown-financial", "X", "Typo",
            (Posting("Assets:NCF:Reserves:GP", D("1"), "GP"), Posting("Liabilities:NCF:Deposits:X", D("-1"), "GP")),
        )
        book = JournalBook(chart_for(event), store)
        with self.assertRaisesRegex(JournalError, "unsupported"):
            book.post(event)

    def test_extra_income_posting_cannot_hide_short_debt(self):
        source = source_event(
            "finance.treasury_borrowing",
            {"amount": D("100"), "currency": "GP", "lender_slug": "lender"},
        )
        valid = treasury_borrowing(source_event=source, book_date="2026-01-03")
        bad = replace(valid, postings=(
            Posting("Assets:Treasury:Cash:GP", D("100"), "GP"),
            Posting("Liabilities:Treasury:Notes-Payable:Lender", D("-90"), "GP"),
            Posting("Income:Treasury:Borrowing-Gain", D("-10"), "GP"),
        ))
        book = JournalBook(chart_for(bad), accepted_store(source))
        with self.assertRaisesRegex(JournalError, "exactly match"):
            book.post(bad)

    def test_wrong_entity_is_rejected(self):
        source = source_event()
        valid = ncf_deposit(source_event=source, book_date="2026-01-01")
        bad = replace(valid, entity_id="entity:central-treasury")
        book = JournalBook(chart_for(bad), accepted_store(source))
        with self.assertRaisesRegex(JournalError, "entity"):
            book.post(bad)

    def test_unaccepted_and_duplicate_source_events_are_rejected(self):
        source = source_event()
        event = ncf_deposit(source_event=source, book_date="2026-01-01")
        book = JournalBook(chart_for(event), EventStore())
        with self.assertRaisesRegex(JournalError, "not active"):
            book.post(event)
        accepted = JournalBook(chart_for(event), accepted_store(source), [event])
        with self.assertRaisesRegex(JournalError, "duplicate event"):
            accepted.post(event)
        fake_store = type("AlwaysActive", (), {"contains_active": lambda self, value: True})()
        with self.assertRaisesRegex(JournalError, "concrete EventStore"):
            JournalBook(chart_for(event), fake_store, [event])

    def test_duck_typed_journal_and_mutable_postings_are_rejected(self):
        source = source_event()
        valid = ncf_deposit(source_event=source, book_date="2026-01-01")
        fake = type(
            "FakeJournal",
            (),
            {
                "source_event": source,
                "event_id": source.event_id,
                "validate": lambda self, chart: None,
                "postings": (Posting("Assets:Evil", D("999"), "GP"),),
            },
        )()
        book = JournalBook(chart_for(valid), accepted_store(source))
        with self.assertRaisesRegex(JournalError, "concrete JournalEvent"):
            book.post(fake)
        with self.assertRaisesRegex(JournalError, "immutable tuple"):
            JournalEvent(
                source,
                "2026-01-01",
                "entity:northern-crown-financial",
                "merchant-one",
                "Deposit received",
                list(valid.postings),
            )

    def test_unopened_account_cannot_post_or_export(self):
        source = source_event()
        event = ncf_deposit(source_event=source, book_date="2026-01-01")
        book = JournalBook(
            {"Assets:NCF:Reserves": AccountOpen(("GP",), "2026-01-01")},
            accepted_store(source),
        )
        with self.assertRaisesRegex(JournalError, "unopened account"):
            book.post(event)
        with self.assertRaisesRegex(JournalError, "already validated"):
            render_beancount(book, event.event_id)

    def test_invalid_beancount_account_currency_and_amount_are_rejected(self):
        with self.assertRaisesRegex(JournalError, "account"):
            Posting("Assets::Bad", D("1"), "GP")
        with self.assertRaisesRegex(JournalError, "currency"):
            Posting("Assets:Treasury:Cash", D("1"), "gp")
        with self.assertRaisesRegex(JournalError, "finite Decimal"):
            Posting("Assets:Treasury:Cash", 1, "GP")

    def test_invalid_gregorian_book_date_and_control_text_are_rejected(self):
        source = source_event()
        event = ncf_deposit(source_event=source, book_date="2026-02-29")
        book = JournalBook(chart_for(event), accepted_store(source))
        with self.assertRaisesRegex(JournalError, "valid Gregorian"):
            book.post(event)
        for book_date in ("1495-01-01", "2100-01-01"):
            ranged = ncf_deposit(source_event=source, book_date=book_date)
            with self.assertRaisesRegex(JournalError, "1700-2099"):
                JournalBook(chart_for(ranged), accepted_store(source)).post(ranged)
        with self.assertRaisesRegex(ValueError, "control"):
            source_event(key="fixture:control", source_ref="fixture:bad\nref")

    def test_beancount_export_preserves_provenance_and_fixed_point_numbers(self):
        source = source_event(payload={
            "amount": D("1E+3"), "currency": "GP", "customer_slug": "merchant-one"
        })
        event = ncf_deposit(source_event=source, book_date="2026-01-01")
        book = JournalBook(chart_for(event), accepted_store(source), [event])
        rendered = render_beancount(book, event.event_id)
        self.assertIn(f'event_id: "{source.event_id}"', rendered)
        self.assertIn('source_event_schema: "1"', rendered)
        self.assertIn(
            f'source_event_integrity_hash: "{source.integrity_hash}"', rendered
        )
        self.assertIn('source_event_revision: "1"', rendered)
        self.assertIn('source_event_type: "finance.bank_deposit"', rendered)
        self.assertIn('source_event_phase: "finance"', rendered)
        self.assertIn('source_event_sequence: "1"', rendered)
        self.assertIn('temporal_state: "current"', rendered)
        self.assertIn('resolution_status: "resolved"', rendered)
        self.assertIn('timeline_id: "actual"', rendered)
        self.assertIn('model_version: "economy-0.1"', rendered)
        self.assertIn('campaign_ordinal: "1"', rendered)
        self.assertIn('campaign_date: "Synthetic 1"', rendered)
        self.assertIn('entity_id: "entity:northern-crown-financial"', rendered)
        self.assertIn('event_type: "bank_deposit"', rendered)
        self.assertIn(f'payload_hash: "{source.payload_hash}"', rendered)
        self.assertIn("Assets:NCF:Reserves 1000 GP", rendered)
        self.assertNotIn("1E+3", rendered)

    def test_corrected_finance_event_cannot_double_post(self):
        original = source_event(
            payload={"amount": "100", "currency": "GP", "customer_slug": "merchant-one"},
            key="fixture:corrected-deposit",
        )
        correction = source_event(
            payload={"amount": "110", "currency": "GP", "customer_slug": "merchant-one"},
            key="fixture:corrected-deposit", event_revision=2,
            reverses_event_id=original.event_id,
        )
        store = EventStore()
        store.append(original)
        original_journal = ncf_deposit(source_event=original, book_date="2026-01-01")
        correction_journal = ncf_deposit(source_event=correction, book_date="2026-01-02")
        book = JournalBook(chart_for(original_journal), store, [original_journal])
        store.append(correction)
        with self.assertRaisesRegex(JournalError, "inactive corrected"):
            _ = book.events
        with self.assertRaisesRegex(JournalError, "inactive corrected"):
            book.render(original_journal.event_id)

        fresh = JournalBook(chart_for(correction_journal), store)
        with self.assertRaisesRegex(JournalError, "may not mutate"):
            fresh.post(correction_journal)

    def test_finance_payload_schema_is_exact(self):
        extra = source_event(payload={
            "amount": "100", "currency": "GP", "customer_slug": "merchant-one",
            "fee": "5",
        })
        with self.assertRaisesRegex(JournalError, "keys must be exactly"):
            ncf_deposit(source_event=extra, book_date="2026-01-01")
        wrong_specific = source_event(
            "finance.loan_credit",
            {"amount": "100", "currency": "GP", "customer_slug": "merchant-one"},
        )
        with self.assertRaisesRegex(JournalError, "keys must be exactly"):
            ncf_loan_credit(source_event=wrong_specific, book_date="2026-01-01")

    def test_payee_and_narration_cannot_diverge_from_source(self):
        source = source_event()
        valid = ncf_deposit(source_event=source, book_date="2026-01-01")
        book = JournalBook(chart_for(valid), accepted_store(source))
        with self.assertRaisesRegex(JournalError, "payee or narration"):
            book.post(replace(valid, payee="someone-else", narration="Different"))

    def test_finance_model_version_must_match_the_bridge(self):
        source = source_event(model_version="unrelated-model-999")
        event = ncf_deposit(source_event=source, book_date="2026-01-01")
        with self.assertRaisesRegex(JournalError, "model version"):
            JournalBook(chart_for(event), accepted_store(source)).post(event)

    def test_bridge_posts_against_the_pinned_pr48_chart(self):
        sources_and_events = []
        deposit_source = source_event(key="fixture:chart-deposit")
        sources_and_events.append((
            deposit_source,
            ncf_deposit(source_event=deposit_source, book_date="2026-01-01"),
        ))
        credit_source = source_event(
            "finance.loan_credit",
            {"amount": "600", "currency": "GP", "borrower_slug": "borrower-one"},
            key="fixture:chart-credit",
        )
        sources_and_events.append((
            credit_source,
            ncf_loan_credit(source_event=credit_source, book_date="2026-01-02"),
        ))
        repayment_source = source_event(
            "finance.loan_repayment",
            {
                "principal": "100", "interest": "10", "currency": "GP",
                "borrower_slug": "borrower-one",
            },
            key="fixture:chart-repayment",
        )
        sources_and_events.append((
            repayment_source,
            ncf_loan_repayment_from_deposit(
                source_event=repayment_source, book_date="2026-01-03"
            ),
        ))
        borrowing_source = source_event(
            "finance.treasury_borrowing",
            {"amount": "1000", "currency": "GP", "lender_slug": "lender"},
            key="fixture:chart-borrowing",
        )
        sources_and_events.append((
            borrowing_source,
            treasury_borrowing(source_event=borrowing_source, book_date="2026-01-04"),
        ))
        store = EventStore()
        for source, _ in sources_and_events:
            store.append(source)
        book = JournalBook(
            pr48_chart(), store, [event for _, event in sources_and_events]
        )
        self.assertEqual(len(book.events), 4)

    def test_opened_account_currency_is_enforced(self):
        source = source_event(payload={
            "amount": "100", "currency": "CR", "customer_slug": "merchant-one"
        })
        event = ncf_deposit(source_event=source, book_date="2026-01-01")
        with self.assertRaisesRegex(JournalError, "not opened"):
            JournalBook(pr48_chart(), accepted_store(source)).post(event)

    def test_pinned_chart_open_date_is_enforced(self):
        source = source_event()
        event = ncf_deposit(source_event=source, book_date="2025-12-31")
        with self.assertRaisesRegex(JournalError, "predates account opening"):
            JournalBook(pr48_chart(), accepted_store(source)).post(event)

    def test_finance_decimal_context_is_engine_owned(self):
        source = source_event(
            "finance.loan_repayment",
            {
                "principal": "999.99",
                "interest": "0.02",
                "currency": "GP",
                "borrower_slug": "borrower-one",
            },
            key="fixture:context-repayment",
        )
        original = getcontext().copy()
        try:
            getcontext().prec = 2
            low = ncf_loan_repayment_from_deposit(
                source_event=source, book_date="2026-01-02"
            )
            low_book = JournalBook(chart_for(low), accepted_store(source), [low])
            low_render = low_book.render(low.event_id)
            getcontext().prec = 28
            normal = ncf_loan_repayment_from_deposit(
                source_event=source, book_date="2026-01-02"
            )
            normal_book = JournalBook(
                chart_for(normal), accepted_store(source), [normal]
            )
            normal_render = normal_book.render(normal.event_id)
        finally:
            setcontext(original)
        self.assertEqual(low, normal)
        self.assertEqual(low_render, normal_render)

    def test_account_open_contract_is_deeply_immutable(self):
        with self.assertRaisesRegex(JournalError, "immutable tuple"):
            AccountOpen(["GP"], "2026-01-01")


if __name__ == "__main__":
    unittest.main()
