"""Deterministic, non-postable positive banking proposal fixture.

This module deliberately has no file-writing, JournalBook, or Beancount export
surface.  It exercises the finance translators with synthetic preview events and
returns review-only JSON data; the same events remain ineligible for the actual
campaign journal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from types import MappingProxyType
from typing import Callable, Mapping

from .domain import Authority, TemporalState, canonical_decimal
from .events import (
    CURRENT_MODEL_VERSION,
    CampaignDate,
    EventEnvelope,
    EventPhase,
    EventStore,
    ResolutionStatus,
)
from .finance import (
    AccountOpen,
    JournalEvent,
    ncf_deposit,
    ncf_loan_credit,
    ncf_loan_repayment_from_deposit,
)
from .operator_codec import canonical_dumps, with_content_hash


SANDBOX_ID = "ncf-positive-banking-v1"
SANDBOX_TITLE = "NCF Positive Banking Sandbox — Synthetic / Non-Canonical"
SANDBOX_TIMELINE_ID = "preview:banking-sandbox:positive-v1"
SANDBOX_SOURCE_REF = "sandbox:ncf-positive-banking-v1"
SANDBOX_SCHEMA = "tnp.economy.banking-sandbox-preview/1"
LEDGER_BASE_COMMIT = "ac6523d404a099dec624930d757478b5317dd471"
CHART_SHA256 = "c4b4578dd008be99b094845fc3e9db718326ade4f0c6ed86b9071cc13ae05940"
NCF_ENTITY_ID = "entity:northern-crown-financial"
GP = "GP"
ACCOUNT_OPEN_DATE = "2026-01-01"


def _new_decimal_context() -> Context:
    return Context(
        prec=40,
        rounding=ROUND_HALF_EVEN,
        Emin=-999999,
        Emax=999999,
        capitals=1,
        clamp=0,
    )


_ACCOUNT_ORDER = (
    "Assets:NCF:Reserves",
    "Assets:NCF:Loans-Receivable",
    "Liabilities:NCF:Deposits",
    "Income:NCF:Interest",
)
_ACCOUNT_TYPES = MappingProxyType(
    {
        "Assets:NCF:Reserves": "asset",
        "Assets:NCF:Loans-Receivable": "asset",
        "Liabilities:NCF:Deposits": "liability",
        "Income:NCF:Interest": "income",
    }
)
_NORMAL_BALANCES = MappingProxyType(
    {
        "Assets:NCF:Reserves": "debit",
        "Assets:NCF:Loans-Receivable": "debit",
        "Liabilities:NCF:Deposits": "credit",
        "Income:NCF:Interest": "credit",
    }
)
_SANDBOX_CHART = MappingProxyType(
    {
        account: AccountOpen((GP,), ACCOUNT_OPEN_DATE)
        for account in _ACCOUNT_ORDER
    }
)


@dataclass(frozen=True, slots=True)
class _TransactionSpec:
    key: str
    source_event_type: str
    proposal_event_type: str
    book_date: str
    campaign_label: str
    payee: str
    narration: str
    payload: Mapping[str, object]
    factory: Callable[..., JournalEvent]
    expected_postings: tuple[tuple[str, str], ...]


_TRANSACTION_SPECS = (
    _TransactionSpec(
        key="deposit",
        source_event_type="finance.bank_deposit",
        proposal_event_type="bank_deposit",
        book_date="2026-01-01",
        campaign_label="Synthetic banking sandbox day 1",
        payee="merchant-one",
        narration="Deposit received",
        payload=MappingProxyType(
            {"amount": "1000", "currency": GP, "customer_slug": "merchant-one"}
        ),
        factory=ncf_deposit,
        expected_postings=(
            ("Assets:NCF:Reserves", "1000"),
            ("Liabilities:NCF:Deposits", "-1000"),
        ),
    ),
    _TransactionSpec(
        key="loan-credit",
        source_event_type="finance.loan_credit",
        proposal_event_type="loan_credit",
        book_date="2026-01-02",
        campaign_label="Synthetic banking sandbox day 2",
        payee="builder-one",
        narration="Loan credited to borrower deposit",
        payload=MappingProxyType(
            {"amount": "600", "currency": GP, "borrower_slug": "builder-one"}
        ),
        factory=ncf_loan_credit,
        expected_postings=(
            ("Assets:NCF:Loans-Receivable", "600"),
            ("Liabilities:NCF:Deposits", "-600"),
        ),
    ),
    _TransactionSpec(
        key="repayment",
        source_event_type="finance.loan_repayment",
        proposal_event_type="loan_repayment_from_deposit",
        book_date="2026-01-03",
        campaign_label="Synthetic banking sandbox day 3",
        payee="builder-one",
        narration="Loan principal and interest paid from deposit",
        payload=MappingProxyType(
            {
                "principal": "100",
                "interest": "10",
                "currency": GP,
                "borrower_slug": "builder-one",
            }
        ),
        factory=ncf_loan_repayment_from_deposit,
        expected_postings=(
            ("Liabilities:NCF:Deposits", "110"),
            ("Assets:NCF:Loans-Receivable", "-100"),
            ("Income:NCF:Interest", "-10"),
        ),
    ),
)

_EXPECTED_CUMULATIVE = MappingProxyType(
    {
        "Assets:NCF:Reserves": Decimal("1000"),
        "Assets:NCF:Loans-Receivable": Decimal("500"),
        "Liabilities:NCF:Deposits": Decimal("-1490"),
        "Income:NCF:Interest": Decimal("-10"),
    }
)


def build_positive_banking_sandbox() -> dict[str, object]:
    """Return the content-hashed, review-only positive banking proposal."""

    journal_events = _build_journal_events()
    transactions: list[dict[str, object]] = []
    source_event_refs: list[dict[str, object]] = []
    cumulative = {account: Decimal(0) for account in _ACCOUNT_ORDER}
    proposal_totals: dict[str, Decimal] = {}

    with localcontext(_new_decimal_context()):
        for index, (spec, event) in enumerate(
            zip(_TRANSACTION_SPECS, journal_events, strict=True), start=1
        ):
            transaction, totals = _validated_transaction_payload(index, spec, event)
            transactions.append(transaction)
            source_event_refs.append(
                {
                    "event_id": event.event_id,
                    "integrity_hash": event.source_event.integrity_hash,
                    "source_event_key": event.source_event.source_event_key,
                    "source_ref": event.source_ref,
                }
            )
            for posting in event.postings:
                cumulative[posting.account] += posting.amount
            for currency, amount in totals.items():
                proposal_totals[currency] = proposal_totals.get(currency, Decimal(0)) + amount

    if cumulative != dict(_EXPECTED_CUMULATIVE):
        raise ValueError("banking sandbox cumulative account semantics drifted")
    if any(amount != 0 for amount in proposal_totals.values()):
        raise ValueError("banking sandbox proposal is not balanced by currency")

    posting_count = sum(len(event.postings) for event in journal_events)
    if len(transactions) != 3 or posting_count != 7:
        raise ValueError("banking sandbox must contain exactly 3 transactions and 7 postings")

    body = {
        "schema": SANDBOX_SCHEMA,
        "sandbox_id": SANDBOX_ID,
        "title": SANDBOX_TITLE,
        "status": "preview_only",
        "mode": "synthetic_noncanonical",
        "canonical": False,
        "proposal_only": True,
        "postable": False,
        "ledger_post_capability": False,
        "ledger_write_attempted": False,
        "beancount_exported": False,
        "timeline_id": SANDBOX_TIMELINE_ID,
        "authority": Authority.SCENARIO_ASSUMPTION.value,
        "temporal_state": TemporalState.PROJECTED.value,
        "resolution_status": ResolutionStatus.RESOLVED.value,
        "currency": GP,
        "finance_bridge_version": "tnp.economy.finance/1",
        "ledger_base_commit": LEDGER_BASE_COMMIT,
        "chart_contract": {
            "source": "campaign-finance-ledger/ledger/accounts.bean",
            "sha256": CHART_SHA256,
            "accounts": [
                {
                    "account": account,
                    "account_type": _ACCOUNT_TYPES[account],
                    "normal_balance": _NORMAL_BALANCES[account],
                    "currencies": list(_SANDBOX_CHART[account].currencies),
                    "opened_on": _SANDBOX_CHART[account].opened_on,
                }
                for account in _ACCOUNT_ORDER
            ],
        },
        "source_event_refs": source_event_refs,
        "transactions": transactions,
        "proposal_transaction_count": len(transactions),
        "proposal_posting_count": posting_count,
        "posted_transaction_count": 0,
        "posted_posting_count": 0,
        "totals_by_currency": [
            {
                "currency": currency,
                "amount": canonical_decimal(amount),
            }
            for currency, amount in sorted(proposal_totals.items())
        ],
        "cumulative_account_deltas": [
            {
                "account": account,
                "account_type": _ACCOUNT_TYPES[account],
                "amount": canonical_decimal(cumulative[account]),
                "currency": GP,
            }
            for account in _ACCOUNT_ORDER
        ],
        "warning": (
            "SYNTHETIC NON-CANONICAL PROPOSAL. These balanced deltas are not opening "
            "balances, lending capacity, reserve-ratio evidence, or ledger entries."
        ),
    }
    return with_content_hash(body)


def render_positive_banking_sandbox_json() -> str:
    """Return deterministic canonical JSON without reading or writing a ledger."""

    return canonical_dumps(build_positive_banking_sandbox())


def _build_journal_events() -> tuple[JournalEvent, ...]:
    source_store = EventStore()
    events: list[JournalEvent] = []
    for index, spec in enumerate(_TRANSACTION_SPECS, start=1):
        source_event = EventEnvelope.create(
            source_event_key=f"{SANDBOX_SOURCE_REF}:{spec.key}",
            event_revision=1,
            timeline_id=SANDBOX_TIMELINE_ID,
            model_version=CURRENT_MODEL_VERSION,
            campaign_date=CampaignDate(index, spec.campaign_label),
            phase=EventPhase.FINANCE.value,
            sequence=index,
            authority=Authority.SCENARIO_ASSUMPTION,
            temporal_state=TemporalState.PROJECTED,
            resolution_status=ResolutionStatus.RESOLVED,
            source_ref=SANDBOX_SOURCE_REF,
            event_type=spec.source_event_type,
            subject_entity_id=NCF_ENTITY_ID,
            payload=spec.payload,
        )
        source_store.append(source_event)
        events.append(spec.factory(source_event=source_event, book_date=spec.book_date))
    return tuple(events)


def _validated_transaction_payload(
    index: int,
    spec: _TransactionSpec,
    event: JournalEvent,
) -> tuple[dict[str, object], dict[str, Decimal]]:
    source = event.source_event
    source.validate_integrity()
    if source.may_mutate_actual:
        raise ValueError("banking sandbox source unexpectedly became actual-postable")
    if (
        source.timeline_id != SANDBOX_TIMELINE_ID
        or source.authority is not Authority.SCENARIO_ASSUMPTION
        or source.temporal_state is not TemporalState.PROJECTED
        or source.resolution_status is not ResolutionStatus.RESOLVED
        or source.phase != EventPhase.FINANCE.value
        or source.model_version != CURRENT_MODEL_VERSION
        or source.subject_entity_id != NCF_ENTITY_ID
        or source.reverses_event_id is not None
    ):
        raise ValueError("banking sandbox source authority contract drifted")
    if (
        source.event_type != spec.source_event_type
        or event.event_type != spec.proposal_event_type
        or event.entity_id != NCF_ENTITY_ID
        or event.payee != spec.payee
        or event.narration != spec.narration
        or event.book_date != spec.book_date
    ):
        raise ValueError("banking sandbox transaction identity or header drifted")

    actual_postings = tuple(
        (posting.account, posting.amount, posting.currency) for posting in event.postings
    )
    expected_postings = tuple(
        (account, Decimal(amount), GP) for account, amount in spec.expected_postings
    )
    if actual_postings != expected_postings:
        raise ValueError("banking sandbox posting semantics drifted")

    parsed_book_date = date.fromisoformat(event.book_date)
    totals: dict[str, Decimal] = {}
    for posting in event.postings:
        account_open = _SANDBOX_CHART.get(posting.account)
        if account_open is None:
            raise ValueError(f"banking sandbox uses unopened account: {posting.account}")
        if posting.currency not in account_open.currencies:
            raise ValueError("banking sandbox posting currency is not open for its account")
        if parsed_book_date < date.fromisoformat(account_open.opened_on):
            raise ValueError("banking sandbox posting predates its account opening")
        totals[posting.currency] = totals.get(posting.currency, Decimal(0)) + posting.amount
    if not totals or any(amount != 0 for amount in totals.values()):
        raise ValueError("banking sandbox transaction is not balanced by currency")

    return (
        {
            "proposal_index": index,
            "postable": False,
            "event_id": event.event_id,
            "source_event_integrity_hash": source.integrity_hash,
            "source_event_key": source.source_event_key,
            "source_event_type": source.event_type,
            "event_type": event.event_type,
            "book_date": event.book_date,
            "campaign_date": event.campaign_date,
            "entity_id": event.entity_id,
            "payee": event.payee,
            "narration": event.narration,
            "payload_hash": source.payload_hash,
            "source_ref": event.source_ref,
            "postings": [
                {
                    "account": posting.account,
                    "account_type": _ACCOUNT_TYPES[posting.account],
                    "amount": canonical_decimal(posting.amount),
                    "currency": posting.currency,
                }
                for posting in event.postings
            ],
            "totals_by_currency": [
                {"currency": currency, "amount": canonical_decimal(amount)}
                for currency, amount in sorted(totals.items())
            ],
        },
        totals,
    )


__all__ = [
    "build_positive_banking_sandbox",
    "render_positive_banking_sandbox_json",
]
