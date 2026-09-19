"""Strict EventStore-bound bridge to the Beancount-style campaign ledger."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
import json
import re
from typing import Iterable, Mapping

from .events import CURRENT_MODEL_VERSION, EventEnvelope, EventStore


ACCOUNT_RE = re.compile(
    r"^(?:Assets|Liabilities|Equity|Income|Expenses)(?::[A-Z0-9][A-Za-z0-9-]*)+$"
)
CURRENCY_RE = re.compile(r"^[A-Z](?:[A-Z0-9._'-]*[A-Z0-9])?$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
def _new_finance_decimal_context() -> Context:
    return Context(
        prec=40,
        rounding=ROUND_HALF_EVEN,
        Emin=-999999,
        Emax=999999,
        capitals=1,
        clamp=0,
    )

SOURCE_EVENT_TYPES = {
    "finance.bank_deposit": "bank_deposit",
    "finance.loan_credit": "loan_credit",
    "finance.loan_repayment": "loan_repayment_from_deposit",
    "finance.treasury_borrowing": "treasury_borrowing",
}
EXPECTED_ENTITY = {
    "bank_deposit": "entity:northern-crown-financial",
    "loan_credit": "entity:northern-crown-financial",
    "loan_repayment_from_deposit": "entity:northern-crown-financial",
    "treasury_borrowing": "entity:central-treasury",
}
EXPECTED_NARRATION = {
    "bank_deposit": "Deposit received",
    "loan_credit": "Loan credited to borrower deposit",
    "loan_repayment_from_deposit": "Loan principal and interest paid from deposit",
    "treasury_borrowing": "Borrowing proceeds cleared",
}
PAYLOAD_KEYS = {
    "finance.bank_deposit": frozenset({"amount", "currency", "customer_slug"}),
    "finance.loan_credit": frozenset({"amount", "currency", "borrower_slug"}),
    "finance.loan_repayment": frozenset(
        {"principal", "interest", "currency", "borrower_slug"}
    ),
    "finance.treasury_borrowing": frozenset({"amount", "currency", "lender_slug"}),
}


class JournalError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AccountOpen:
    currencies: tuple[str, ...]
    opened_on: str
    closed_on: str | None = None

    def __post_init__(self) -> None:
        if type(self.currencies) is not tuple:
            raise JournalError("opened-account currencies must be an immutable tuple")
        if not self.currencies or len(self.currencies) != len(set(self.currencies)):
            raise JournalError("opened account requires unique allowed currencies")
        for currency in self.currencies:
            _validate_currency(currency)
        opened = _parse_book_date(self.opened_on, "account opened_on")
        if self.closed_on is not None:
            closed = _parse_book_date(self.closed_on, "account closed_on")
            if closed <= opened:
                raise JournalError("account close date must follow its open date")


@dataclass(frozen=True, slots=True, order=True)
class Posting:
    account: str
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        _validate_account(self.account)
        _validate_currency(self.currency)
        if not isinstance(self.amount, Decimal) or not self.amount.is_finite():
            raise JournalError("posting amount must be a finite Decimal")


@dataclass(frozen=True, slots=True)
class JournalEvent:
    source_event: EventEnvelope
    book_date: str
    entity_id: str
    payee: str
    narration: str
    postings: tuple[Posting, ...]

    def __post_init__(self) -> None:
        if type(self.source_event) is not EventEnvelope:
            raise JournalError("journal source must be a concrete EventEnvelope")
        if type(self.postings) is not tuple:
            raise JournalError("journal postings must be an immutable tuple")
        if any(type(posting) is not Posting for posting in self.postings):
            raise JournalError("journal postings must contain concrete Posting values")

    @property
    def event_id(self) -> str:
        return self.source_event.event_id

    @property
    def source_ref(self) -> str:
        return self.source_event.source_ref

    @property
    def campaign_date(self) -> str:
        return self.source_event.campaign_date.label

    @property
    def event_type(self) -> str:
        try:
            return SOURCE_EVENT_TYPES[self.source_event.event_type]
        except KeyError as exc:
            raise JournalError(
                f"unsupported finance source event type: {self.source_event.event_type}"
            ) from exc

    def validate(
        self, chart: Mapping[str, AccountOpen]
    ) -> None:
        self.source_event.validate_integrity()
        if not self.source_event.may_mutate_actual:
            raise JournalError("finance source event may not mutate the canonical actual book")
        if self.source_event.phase != "finance":
            raise JournalError("finance source event must use the finance phase")
        if self.source_event.model_version != CURRENT_MODEL_VERSION:
            raise JournalError("finance source event uses an unsupported model version")
        event_type = self.event_type
        expected_entity = EXPECTED_ENTITY[event_type]
        if self.entity_id != expected_entity or self.source_event.subject_entity_id != expected_entity:
            raise JournalError("finance event entity does not match its source-event contract")
        expected_payee, expected_narration = _expected_header(self.source_event)
        if self.payee != expected_payee or self.narration != expected_narration:
            raise JournalError("finance payee or narration does not match its source payload")
        _validate_text(self.event_id, "event ID")
        _validate_text(self.source_ref, "source reference")
        _validate_text(self.campaign_date, "campaign date")
        _validate_text(self.payee, "payee")
        _validate_text(self.narration, "narration")
        if not ISO_DATE_RE.fullmatch(self.book_date):
            raise JournalError("book_date must be an ISO date; campaign_date is stored separately")
        parsed_book_date = _parse_book_date(self.book_date, "book_date")
        if not chart:
            raise JournalError("an opened-account set is required for validation")
        for posting in self.postings:
            account_open = chart.get(posting.account)
            if account_open is None:
                raise JournalError(f"posting uses unopened account: {posting.account}")
            opened_on = date.fromisoformat(account_open.opened_on)
            if parsed_book_date < opened_on:
                raise JournalError(f"posting predates account opening: {posting.account}")
            if (
                account_open.closed_on is not None
                and parsed_book_date >= date.fromisoformat(account_open.closed_on)
            ):
                raise JournalError(f"posting is on or after account closure: {posting.account}")
            if posting.currency not in account_open.currencies:
                raise JournalError(
                    f"posting currency {posting.currency} is not opened for {posting.account}"
                )
        expected = _expected_postings(self.source_event)
        if tuple(sorted(self.postings)) != tuple(sorted(expected)):
            raise JournalError(
                f"{event_type} postings do not exactly match the source payload and accounting contract"
            )
        totals: dict[str, Decimal] = {}
        with localcontext(_new_finance_decimal_context()):
            for posting in self.postings:
                totals[posting.currency] = (
                    totals.get(posting.currency, Decimal(0)) + posting.amount
                )
        unbalanced = {currency: amount for currency, amount in totals.items() if amount != 0}
        if unbalanced:
            raise JournalError(f"event {self.event_id} is unbalanced: {unbalanced}")


class JournalBook:
    def __init__(
        self,
        chart: Mapping[str, AccountOpen],
        accepted_event_store: EventStore,
        events: Iterable[JournalEvent] = (),
    ) -> None:
        if type(accepted_event_store) is not EventStore:
            raise JournalError("journal book requires the concrete EventStore acceptance gate")
        if not isinstance(chart, Mapping):
            raise JournalError("journal chart must map each account to an open-account contract")
        validated_chart: dict[str, AccountOpen] = {}
        for account, account_open in chart.items():
            _validate_account(account)
            if type(account_open) is not AccountOpen:
                raise JournalError("journal chart entries must be AccountOpen contracts")
            validated_chart[account] = account_open
        self._chart = validated_chart
        if not self._chart:
            raise JournalError("journal book requires a non-empty opened-account set")
        self._accepted_event_store = accepted_event_store
        self._events: dict[str, JournalEvent] = {}
        for event in events:
            self.post(event)

    def post(self, event: JournalEvent) -> None:
        self._assert_all_sources_active()
        if type(event) is not JournalEvent:
            raise JournalError("journal book accepts only concrete JournalEvent values")
        if not self._accepted_event_store.contains_active(event.source_event):
            raise JournalError("finance source event is not active in the EventStore")
        event.validate(self._chart)
        if event.event_id in self._events:
            raise JournalError(f"duplicate event ID: {event.event_id}")
        self._events[event.event_id] = event

    def render(self, event_id: str) -> str:
        self._assert_all_sources_active()
        try:
            event = self._events[event_id]
        except KeyError as exc:
            raise JournalError("only an event already validated in this book may be exported") from exc
        if not self._accepted_event_store.contains_active(event.source_event):
            raise JournalError("finance source event is no longer active in the EventStore")
        event.validate(self._chart)
        return _render_beancount(event)

    @property
    def events(self) -> tuple[JournalEvent, ...]:
        self._assert_all_sources_active()
        return tuple(self._events[key] for key in sorted(self._events))

    def position_report(
        self, opening_balances: Mapping[tuple[str, str], Decimal | None]
    ) -> dict[str, object]:
        """Read accepted movements without treating unknown opening balances as zero.

        Balances use signed journal amounts (debit positive). The supplied
        openings must precede this book's event window. This does not post,
        authorize spending, or infer uncharted accounts or opening equity.
        """
        pairs = {(account, currency) for account, spec in self._chart.items()
                 for currency in spec.currencies}
        if not isinstance(opening_balances, Mapping) or set(opening_balances) - pairs:
            raise JournalError("opening balances must reference opened account/currency pairs")
        for value in opening_balances.values():
            if value is not None and (type(value) is not Decimal or not value.is_finite()):
                raise JournalError("opening balances must be finite Decimals or unknown")
        events = self.events  # also rejects corrected/inactive sources
        with localcontext(_new_finance_decimal_context()):
            movements = {pair: Decimal(0) for pair in pairs}
            for event in events:
                event.validate(self._chart)
                for posting in event.postings:
                    movements[posting.account, posting.currency] += posting.amount
            rows = []
            for account, currency in sorted(pairs):
                opening = opening_balances.get((account, currency))
                movement = movements[account, currency]
                rows.append({
                    "account": account, "currency": currency,
                    "opening": None if opening is None else str(opening),
                    "movement": str(movement),
                    "closing": None if opening is None else str(opening + movement),
                })
        return {
            "scope": "Only opened accounts and accepted events in this book",
            "event_count": len(events),
            "source_event_ids": [event.event_id for event in events],
            "accounts": rows,
            "opening_complete": all(row["opening"] is not None for row in rows),
            "postings_created": 0,
        }

    def _assert_all_sources_active(self) -> None:
        inactive = [
            event_id
            for event_id, event in self._events.items()
            if not self._accepted_event_store.contains_active(event.source_event)
        ]
        if inactive:
            raise JournalError(
                "journal contains inactive corrected source events and requires "
                f"explicit reversal/replacement: {sorted(inactive)}"
            )


def ncf_deposit(*, source_event: EventEnvelope, book_date: str) -> JournalEvent:
    payload = _payload(source_event, "finance.bank_deposit")
    customer = _payload_slug(payload, "customer_slug")
    return JournalEvent(
        source_event, book_date, "entity:northern-crown-financial", customer,
        "Deposit received", _expected_postings(source_event),
    )


def ncf_loan_credit(*, source_event: EventEnvelope, book_date: str) -> JournalEvent:
    payload = _payload(source_event, "finance.loan_credit")
    borrower = _payload_slug(payload, "borrower_slug")
    return JournalEvent(
        source_event, book_date, "entity:northern-crown-financial", borrower,
        "Loan credited to borrower deposit", _expected_postings(source_event),
    )


def ncf_loan_repayment_from_deposit(
    *, source_event: EventEnvelope, book_date: str
) -> JournalEvent:
    payload = _payload(source_event, "finance.loan_repayment")
    borrower = _payload_slug(payload, "borrower_slug")
    return JournalEvent(
        source_event, book_date, "entity:northern-crown-financial", borrower,
        "Loan principal and interest paid from deposit", _expected_postings(source_event),
    )


def treasury_borrowing(*, source_event: EventEnvelope, book_date: str) -> JournalEvent:
    payload = _payload(source_event, "finance.treasury_borrowing")
    lender = _payload_slug(payload, "lender_slug")
    return JournalEvent(
        source_event, book_date, "entity:central-treasury", lender,
        "Borrowing proceeds cleared", _expected_postings(source_event),
    )


def render_beancount(book: JournalBook, event_id: str) -> str:
    """Export only through a book that has already enforced its exact chart."""

    return book.render(event_id)


def _expected_postings(source_event: EventEnvelope) -> tuple[Posting, ...]:
    with localcontext(_new_finance_decimal_context()):
        return _expected_postings_fixed(source_event)


def _expected_postings_fixed(source_event: EventEnvelope) -> tuple[Posting, ...]:
    payload = _payload(source_event, source_event.event_type)
    currency = _payload_currency(payload)
    event_type = SOURCE_EVENT_TYPES.get(source_event.event_type)
    if event_type == "bank_deposit":
        amount = _positive_amount(payload, "amount")
        _payload_slug(payload, "customer_slug")
        return (
            Posting("Assets:NCF:Reserves", amount, currency),
            Posting("Liabilities:NCF:Deposits", -amount, currency),
        )
    if event_type == "loan_credit":
        amount = _positive_amount(payload, "amount")
        _payload_slug(payload, "borrower_slug")
        return (
            Posting("Assets:NCF:Loans-Receivable", amount, currency),
            Posting("Liabilities:NCF:Deposits", -amount, currency),
        )
    if event_type == "loan_repayment_from_deposit":
        principal = _nonnegative_amount(payload, "principal")
        interest = _nonnegative_amount(payload, "interest")
        if principal + interest <= 0:
            raise JournalError("repayment principal and interest cannot both be zero")
        _payload_slug(payload, "borrower_slug")
        return (
            Posting("Liabilities:NCF:Deposits", principal + interest, currency),
            Posting("Assets:NCF:Loans-Receivable", -principal, currency),
            Posting("Income:NCF:Interest", -interest, currency),
        )
    if event_type == "treasury_borrowing":
        amount = _positive_amount(payload, "amount")
        _payload_slug(payload, "lender_slug")
        return (
            Posting("Assets:Treasury:Cash", amount, currency),
            Posting("Liabilities:Debt:External", -amount, currency),
        )
    raise JournalError(f"unsupported finance source event type: {source_event.event_type}")


def _expected_header(source_event: EventEnvelope) -> tuple[str, str]:
    payload = _payload(source_event, source_event.event_type)
    event_type = SOURCE_EVENT_TYPES[source_event.event_type]
    if event_type == "bank_deposit":
        payee = _payload_slug(payload, "customer_slug")
    elif event_type in {"loan_credit", "loan_repayment_from_deposit"}:
        payee = _payload_slug(payload, "borrower_slug")
    else:
        payee = _payload_slug(payload, "lender_slug")
    return payee, EXPECTED_NARRATION[event_type]


def _payload(source_event: EventEnvelope, expected_type: str) -> Mapping[str, object]:
    source_event.validate_integrity()
    if source_event.event_type != expected_type:
        raise JournalError(
            f"expected source event {expected_type}, got {source_event.event_type}"
        )
    value = json.loads(source_event.payload_json)
    if not isinstance(value, dict):
        raise JournalError("finance source payload must be an object")
    try:
        expected_keys = PAYLOAD_KEYS[expected_type]
    except KeyError as exc:
        raise JournalError(f"unsupported finance source event type: {expected_type}") from exc
    if set(value) != expected_keys:
        raise JournalError(
            f"finance source payload keys must be exactly {sorted(expected_keys)}"
        )
    return value


def _payload_currency(payload: Mapping[str, object]) -> str:
    value = payload.get("currency")
    if not isinstance(value, str):
        raise JournalError("finance payload currency must be a string")
    _validate_currency(value)
    return value


def _payload_slug(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not SLUG_RE.fullmatch(value):
        raise JournalError(f"finance payload {key} must be a lowercase hyphenated slug")
    return value


def _payload_decimal(payload: Mapping[str, object], key: str) -> Decimal:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise JournalError(f"finance payload {key} must be an exact decimal string or integer")
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise JournalError(f"finance payload {key} is not a Decimal") from exc
    if not amount.is_finite():
        raise JournalError(f"finance payload {key} must be finite")
    return amount


def _positive_amount(payload: Mapping[str, object], key: str) -> Decimal:
    amount = _payload_decimal(payload, key)
    if amount <= 0:
        raise JournalError(f"finance payload {key} must be positive")
    return amount


def _nonnegative_amount(payload: Mapping[str, object], key: str) -> Decimal:
    amount = _payload_decimal(payload, key)
    if amount < 0:
        raise JournalError(f"finance payload {key} must be non-negative")
    return amount


def _validate_account(account: str) -> None:
    if not isinstance(account, str) or not ACCOUNT_RE.fullmatch(account):
        raise JournalError(f"invalid Beancount account: {account!r}")


def _validate_currency(currency: str) -> None:
    if not isinstance(currency, str) or len(currency) > 24 or not CURRENCY_RE.fullmatch(currency):
        raise JournalError(f"invalid Beancount currency: {currency!r}")


def _validate_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip() or CONTROL_RE.search(value):
        raise JournalError(f"{label} must be non-empty and contain no control characters")


def _parse_book_date(value: str, label: str) -> date:
    if not isinstance(value, str) or not ISO_DATE_RE.fullmatch(value):
        raise JournalError(f"{label} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise JournalError(f"{label} must be a valid Gregorian date") from exc
    if not 1700 <= parsed.year <= 2099:
        raise JournalError(f"{label} must be within Beancount's supported 1700-2099 range")
    return parsed


def _render_beancount(event: JournalEvent) -> str:
    lines = [
        f'{event.book_date} * "{_escape(event.payee)}" "{_escape(event.narration)}"',
        f'  event_id: "{_escape(event.event_id)}"',
        f'  source_event_schema: "{event.source_event.schema_version}"',
        f'  source_event_integrity_hash: "{event.source_event.integrity_hash}"',
        f'  source_event_key: "{_escape(event.source_event.source_event_key)}"',
        f'  source_event_revision: "{event.source_event.event_revision}"',
        f'  reverses_event_id: "{_escape(event.source_event.reverses_event_id or "")}"',
        f'  source_event_type: "{_escape(event.source_event.event_type)}"',
        f'  source_event_phase: "{_escape(event.source_event.phase)}"',
        f'  source_event_sequence: "{event.source_event.sequence}"',
        f'  temporal_state: "{_escape(event.source_event.temporal_state.value)}"',
        f'  resolution_status: "{_escape(event.source_event.resolution_status.value)}"',
        f'  timeline_id: "{_escape(event.source_event.timeline_id)}"',
        f'  model_version: "{_escape(event.source_event.model_version)}"',
        f'  campaign_ordinal: "{event.source_event.campaign_date.ordinal}"',
        f'  campaign_precision: "{_escape(event.source_event.campaign_date.precision)}"',
        f'  campaign_year_dr: "{event.source_event.campaign_date.year_dr if event.source_event.campaign_date.year_dr is not None else ""}"',
        f'  campaign_month_code: "{_escape(event.source_event.campaign_date.month_code or "")}"',
        f'  campaign_day: "{event.source_event.campaign_date.day if event.source_event.campaign_date.day is not None else ""}"',
        f'  campaign_date: "{_escape(event.campaign_date)}"',
        f'  entity_id: "{_escape(event.entity_id)}"',
        f'  subject_site_id: "{_escape(event.source_event.subject_site_id or "")}"',
        f'  event_type: "{_escape(event.event_type)}"',
        f'  authority: "{_escape(event.source_event.authority.value)}"',
        f'  payload_hash: "{event.source_event.payload_hash}"',
        f'  source_ref: "{_escape(event.source_ref)}"',
    ]
    lines.extend(
        f"  {posting.account} {_fixed_decimal(posting.amount)} {posting.currency}"
        for posting in event.postings
    )
    return "\n".join(lines) + "\n"


def _fixed_decimal(value: Decimal) -> str:
    return format(value, "f")


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
