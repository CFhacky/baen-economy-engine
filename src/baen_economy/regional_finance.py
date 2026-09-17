"""Operating finance sidecar for a deterministic regional economy month.

The module deliberately accepts and returns plain mappings.  It is not an
adapter to :mod:`baen_economy.finance`, has no file-writing surface, and cannot
post to the canonical campaign ledger.  Signed posting amounts use the usual
accounting convention: debits are positive and credits are negative.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
import re
from typing import Mapping, Sequence

from .domain import canonical_decimal


REGIONAL_FINANCE_SCHEMA = "tnp.economy.regional-finance-preview/1"
_ACCOUNT_TYPES = frozenset({"asset", "contra_asset", "liability", "equity", "income", "expense"})
_ENTITY_TYPES = frozenset({"enterprise", "bank", "treasury"})
_ENTITY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,127}$")
_EVENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._/-]{0,159}$")
_CURRENCY_RE = re.compile(r"^[A-Z][A-Z0-9._'-]{0,11}$")
_MONEY_QUANTUM = Decimal("0.01")


def _new_decimal_context() -> Context:
    return Context(
        prec=80,
        rounding=ROUND_HALF_EVEN,
        Emin=-999999,
        Emax=999999,
        capitals=1,
        clamp=0,
    )


class RegionalFinanceError(ValueError):
    """Raised when a proposed sidecar event cannot be booked exactly."""


@dataclass(frozen=True, slots=True)
class _Posting:
    entity_id: str
    entity_type: str
    account: str
    account_type: str
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        _identifier(self.entity_id, "posting entity_id")
        if self.entity_type not in _ENTITY_TYPES:
            raise RegionalFinanceError("posting entity_type is unsupported")
        if not isinstance(self.account, str) or not self.account or self.account.strip() != self.account:
            raise RegionalFinanceError("posting account must be canonical non-empty text")
        if self.account_type not in _ACCOUNT_TYPES:
            raise RegionalFinanceError("posting account_type is unsupported")
        if type(self.amount) is not Decimal or not self.amount.is_finite() or self.amount == 0:
            raise RegionalFinanceError("posting amount must be a finite non-zero Decimal")
        _currency(self.currency)

    def payload(self) -> dict[str, str]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "account": self.account,
            "account_type": self.account_type,
            "amount": canonical_decimal(self.amount),
            "currency": self.currency,
        }


@dataclass(frozen=True, slots=True)
class _Transaction:
    transaction_id: str
    kind: str
    activity: str
    postings: tuple[_Posting, ...]

    def __post_init__(self) -> None:
        _event_identifier(self.transaction_id, "transaction_id")
        if not isinstance(self.kind, str) or not self.kind:
            raise RegionalFinanceError("transaction kind is required")
        if self.activity not in {"opening", "operating", "financing", "treasury", "credit_loss"}:
            raise RegionalFinanceError("transaction activity is unsupported")
        if type(self.postings) is not tuple or len(self.postings) < 2:
            raise RegionalFinanceError("transaction requires at least two immutable postings")

        totals: dict[str, Decimal] = defaultdict(Decimal)
        entity_totals: dict[tuple[str, str], Decimal] = defaultdict(Decimal)
        with localcontext(_new_decimal_context()):
            for posting in self.postings:
                if type(posting) is not _Posting:
                    raise RegionalFinanceError("transaction contains an invalid posting")
                totals[posting.currency] += posting.amount
                entity_totals[(posting.entity_id, posting.currency)] += posting.amount
        if any(total != 0 for total in totals.values()):
            raise RegionalFinanceError(f"transaction {self.transaction_id} is not balanced")
        if any(total != 0 for total in entity_totals.values()):
            raise RegionalFinanceError(
                f"transaction {self.transaction_id} does not balance for every bookkeeping entity"
            )

    def payload(self) -> dict[str, object]:
        debits = sum((posting.amount for posting in self.postings if posting.amount > 0), Decimal(0))
        credits = -sum((posting.amount for posting in self.postings if posting.amount < 0), Decimal(0))
        return {
            "transaction_id": self.transaction_id,
            "kind": self.kind,
            "activity": self.activity,
            "balanced": debits == credits,
            "debits": canonical_decimal(debits),
            "credits": canonical_decimal(credits),
            "postings": [posting.payload() for posting in self.postings],
        }


@dataclass(slots=True)
class _Loan:
    loan_id: str
    bank_id: str
    borrower_id: str
    annual_interest_rate: Decimal
    originated: Decimal
    principal_outstanding: Decimal
    interest_accrued: Decimal = Decimal(0)
    interest_paid: Decimal = Decimal(0)
    principal_repaid: Decimal = Decimal(0)
    default_exposure: Decimal = Decimal(0)


class _Engine:
    def __init__(self, period: str, currency: str) -> None:
        if not isinstance(period, str) or not period or period.strip() != period:
            raise RegionalFinanceError("period must be canonical non-empty text")
        self.period = period
        self.currency = _currency(currency)
        self.entity_types: dict[str, str] = {}
        self.balances: dict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
        self.transactions: list[_Transaction] = []
        self.transaction_ids: set[str] = set()
        self.loans: dict[str, _Loan] = {}
        self.metrics: dict[str, Decimal] = defaultdict(Decimal)
        self.opening_settlement_cash = Decimal(0)
        self.opening_customer_deposits = Decimal(0)

    def register(self, entity_id: object, entity_type: str) -> str:
        entity = _identifier(entity_id, "entity_id")
        if entity_type not in _ENTITY_TYPES:
            raise RegionalFinanceError(f"unsupported entity type: {entity_type}")
        previous = self.entity_types.get(entity)
        if previous is not None and previous != entity_type:
            raise RegionalFinanceError(f"entity {entity} changes bookkeeping type")
        self.entity_types[entity] = entity_type
        return entity

    def balance(self, entity_id: str, account: str, account_type: str) -> Decimal:
        return self.balances[(entity_id, account, account_type)]

    def require_asset(self, entity_id: str, account: str, amount: Decimal) -> None:
        available = self.balance(entity_id, account, "asset")
        if available < amount:
            raise RegionalFinanceError(
                f"{entity_id} has insufficient {account}: needs {canonical_decimal(amount)}, "
                f"has {canonical_decimal(available)}"
            )

    def require_credit_balance(
        self, entity_id: str, account: str, account_type: str, amount: Decimal
    ) -> None:
        available = -self.balance(entity_id, account, account_type)
        if available < amount:
            raise RegionalFinanceError(
                f"{entity_id} has insufficient {account} balance: needs "
                f"{canonical_decimal(amount)}, has {canonical_decimal(available)}"
            )

    def add(
        self,
        transaction_id: str,
        kind: str,
        activity: str,
        postings: Sequence[_Posting],
    ) -> None:
        if transaction_id in self.transaction_ids:
            raise RegionalFinanceError(f"duplicate event_id: {transaction_id}")
        transaction = _Transaction(transaction_id, kind, activity, tuple(postings))
        with localcontext(_new_decimal_context()):
            for posting in transaction.postings:
                key = (posting.entity_id, posting.account, posting.account_type)
                self.balances[key] += posting.amount
        self.transactions.append(transaction)
        self.transaction_ids.add(transaction_id)

    def post(self, entity_id: str, account: str, account_type: str, amount: Decimal) -> _Posting:
        return _Posting(
            entity_id,
            self.entity_types[entity_id],
            account,
            account_type,
            amount,
            self.currency,
        )


def simulate_regional_finance(
    *,
    period: str,
    opening_positions: Sequence[Mapping[str, object]] = (),
    events: Sequence[Mapping[str, object]] = (),
    currency: str = "GP",
) -> dict[str, object]:
    """Book one deterministic regional month and return review-only reports.

    ``opening_positions`` and ``events`` are intentionally JSON-shaped domain
    mappings.  Amounts may be exact decimal strings, integers, or ``Decimal``
    objects.  Binary floating-point values are rejected.
    """

    if isinstance(opening_positions, (str, bytes)) or not isinstance(opening_positions, Sequence):
        raise RegionalFinanceError("opening_positions must be a sequence of mappings")
    if isinstance(events, (str, bytes)) or not isinstance(events, Sequence):
        raise RegionalFinanceError("events must be a sequence of mappings")
    engine = _Engine(period, currency)
    # Own the Decimal context for the entire booking and reporting pass.  This
    # covers report aggregation as well as individual transaction arithmetic.
    with localcontext(_new_decimal_context()):
        _book_opening_positions(engine, opening_positions)
        engine.opening_settlement_cash = _settlement_cash(engine)
        engine.opening_customer_deposits = _customer_deposits(engine)
        for raw_event in events:
            _book_event(engine, raw_event)
        return _result(engine)


def _book_opening_positions(
    engine: _Engine, positions: Sequence[Mapping[str, object]]
) -> None:
    seen: set[str] = set()
    allowed = {
        "enterprise": {"cash": "asset", "inventory": "asset"},
        "bank": {"reserves": "asset"},
        "treasury": {"cash": "asset"},
    }
    for index, raw in enumerate(positions, start=1):
        item = _mapping(raw, f"opening position {index}")
        _exact_keys(item, {"entity_id", "entity_type", "balances"}, set(), f"opening position {index}")
        entity_type = item["entity_type"]
        if not isinstance(entity_type, str) or entity_type not in _ENTITY_TYPES:
            raise RegionalFinanceError("opening entity_type is unsupported")
        entity = engine.register(item["entity_id"], entity_type)
        if entity in seen:
            raise RegionalFinanceError(f"duplicate opening position for {entity}")
        seen.add(entity)
        balances = _mapping(item["balances"], f"opening balances for {entity}")
        unknown = set(balances) - set(allowed[entity_type])
        if unknown:
            raise RegionalFinanceError(f"unsupported opening accounts for {entity}: {sorted(unknown)}")
        postings: list[_Posting] = []
        total = Decimal(0)
        with localcontext(_new_decimal_context()):
            for account in sorted(balances):
                amount = _amount(balances[account], f"opening {entity} {account}", allow_zero=True)
                if amount == 0:
                    continue
                postings.append(engine.post(entity, account, allowed[entity_type][account], amount))
                total += amount
        if not postings:
            continue
        postings.append(engine.post(entity, "opening_equity", "equity", -total))
        engine.add(f"opening:{index}:{entity}", "opening_balance", "opening", postings)


def _book_event(engine: _Engine, raw: Mapping[str, object]) -> None:
    event = _mapping(raw, "finance event")
    if "kind" not in event:
        raise RegionalFinanceError("finance event is missing kind")
    kind = event["kind"]
    if not isinstance(kind, str):
        raise RegionalFinanceError("finance event kind must be text")
    handlers = {
        "enterprise_sale": _enterprise_sale,
        "enterprise_purchase": _enterprise_purchase,
        "enterprise_trade": _enterprise_trade,
        "payroll": _payroll,
        "bank_deposit": _bank_deposit,
        "loan_origination": _loan_origination,
        "loan_interest_accrual": _loan_interest_accrual,
        "loan_interest_payment": _loan_interest_payment,
        "loan_principal_repayment": _loan_principal_repayment,
        "loan_default": _loan_default,
        "treasury_tax_assessment": _treasury_tax_assessment,
        "treasury_tax_receipt": _treasury_tax_receipt,
        "treasury_receipt": _treasury_receipt,
    }
    try:
        handler = handlers[kind]
    except KeyError as exc:
        raise RegionalFinanceError(f"unsupported finance event kind: {kind}") from exc
    handler(engine, event)


def _enterprise_sale(engine: _Engine, event: Mapping[str, object]) -> None:
    _exact_keys(event, {"event_id", "kind", "entity_id", "amount"}, {"settlement", "bank_id"}, "enterprise_sale")
    event_id = _event_identifier(event["event_id"], "event_id")
    entity = engine.register(event["entity_id"], "enterprise")
    amount = _amount(event["amount"], "sale amount")
    settlement, bank_id, account = _settlement(engine, event, entity, incoming=True)
    postings = [
        engine.post(entity, account, "asset", amount),
        engine.post(entity, "sales_revenue", "income", -amount),
    ]
    if settlement == "bank_deposit":
        assert bank_id is not None
        postings.extend(
            (
                engine.post(bank_id, "reserves", "asset", amount),
                engine.post(bank_id, "customer_deposits", "liability", -amount),
            )
        )
    engine.add(event_id, "enterprise_sale", "operating", postings)


def _enterprise_purchase(engine: _Engine, event: Mapping[str, object]) -> None:
    _exact_keys(
        event,
        {"event_id", "kind", "entity_id", "amount"},
        {"settlement", "bank_id", "treatment"},
        "enterprise_purchase",
    )
    event_id = _event_identifier(event["event_id"], "event_id")
    entity = engine.register(event["entity_id"], "enterprise")
    amount = _amount(event["amount"], "purchase amount")
    treatment = event.get("treatment", "inventory")
    if treatment not in {"inventory", "expense"}:
        raise RegionalFinanceError("purchase treatment must be inventory or expense")
    settlement, bank_id, account = _settlement(engine, event, entity, incoming=False)
    debit_account = "inventory" if treatment == "inventory" else "purchase_expense"
    debit_type = "asset" if treatment == "inventory" else "expense"
    postings = [
        engine.post(entity, debit_account, debit_type, amount),
        engine.post(entity, account, "asset", -amount),
    ]
    postings.extend(_external_bank_outflow(engine, settlement, bank_id, amount))
    engine.add(event_id, "enterprise_purchase", "operating", postings)


def _enterprise_trade(engine: _Engine, event: Mapping[str, object]) -> None:
    """Settle one delivered internal trade without inventing external cash."""

    _exact_keys(
        event,
        {"event_id", "kind", "seller_id", "buyer_id", "amount"},
        {
            "settlement",
            "bank_id",
            "treatment",
            "goods_amount",
            "transport_amount",
            "carrier_id",
        },
        "enterprise_trade",
    )
    event_id = _event_identifier(event["event_id"], "event_id")
    seller = engine.register(event["seller_id"], "enterprise")
    buyer = engine.register(event["buyer_id"], "enterprise")
    if seller == buyer:
        raise RegionalFinanceError("enterprise_trade requires different buyer and seller")
    amount = _amount(event["amount"], "trade amount")
    component_keys = {"goods_amount", "transport_amount", "carrier_id"}
    present_components = component_keys.intersection(event)
    if present_components and present_components != component_keys:
        raise RegionalFinanceError(
            "trade goods/transport/carrier fields must be supplied together"
        )
    if present_components:
        goods_amount = _amount(event["goods_amount"], "trade goods amount")
        transport_amount = _amount(
            event["transport_amount"], "trade transport amount", allow_zero=True
        )
        if goods_amount + transport_amount != amount:
            raise RegionalFinanceError(
                "trade goods and transport components do not equal buyer total"
            )
        carrier = engine.register(event["carrier_id"], "enterprise")
    else:
        goods_amount = amount
        transport_amount = Decimal(0)
        carrier = None
    treatment = event.get("treatment", "expense")
    if treatment not in {"inventory", "expense"}:
        raise RegionalFinanceError("trade treatment must be inventory or expense")
    settlement = event.get("settlement", "cash")
    if settlement == "cash":
        seller_account = buyer_account = "cash"
    elif settlement == "bank_deposit":
        bank = engine.register(event.get("bank_id"), "bank")
        seller_account = buyer_account = f"bank_deposit:{bank}"
    else:
        raise RegionalFinanceError("trade settlement must be cash or bank_deposit")
    engine.require_asset(buyer, buyer_account, amount)
    debit_account = "inventory" if treatment == "inventory" else "purchase_expense"
    debit_type = "asset" if treatment == "inventory" else "expense"
    postings = [
        engine.post(seller, seller_account, "asset", goods_amount),
        engine.post(seller, "sales_revenue", "income", -goods_amount),
        engine.post(buyer, debit_account, debit_type, amount),
        engine.post(buyer, buyer_account, "asset", -amount),
    ]
    if transport_amount:
        assert carrier is not None
        postings.extend(
            (
                engine.post(carrier, seller_account, "asset", transport_amount),
                engine.post(carrier, "transport_revenue", "income", -transport_amount),
            )
        )
    engine.add(
        event_id,
        "enterprise_trade",
        "operating",
        postings,
    )


def _payroll(engine: _Engine, event: Mapping[str, object]) -> None:
    _exact_keys(event, {"event_id", "kind", "entity_id", "amount"}, {"settlement", "bank_id"}, "payroll")
    event_id = _event_identifier(event["event_id"], "event_id")
    entity = engine.register(event["entity_id"], "enterprise")
    amount = _amount(event["amount"], "payroll amount")
    settlement, bank_id, account = _settlement(engine, event, entity, incoming=False)
    postings = [
        engine.post(entity, "payroll_expense", "expense", amount),
        engine.post(entity, account, "asset", -amount),
    ]
    postings.extend(_external_bank_outflow(engine, settlement, bank_id, amount))
    engine.add(event_id, "payroll", "operating", postings)


def _bank_deposit(engine: _Engine, event: Mapping[str, object]) -> None:
    _exact_keys(event, {"event_id", "kind", "bank_id", "depositor_id", "amount"}, set(), "bank_deposit")
    event_id = _event_identifier(event["event_id"], "event_id")
    bank = engine.register(event["bank_id"], "bank")
    depositor = _register_nonbank(engine, event["depositor_id"], "depositor_id")
    amount = _amount(event["amount"], "deposit amount")
    engine.require_asset(depositor, "cash", amount)
    engine.add(
        event_id,
        "bank_deposit",
        "financing",
        (
            engine.post(bank, "reserves", "asset", amount),
            engine.post(bank, "customer_deposits", "liability", -amount),
            engine.post(depositor, f"bank_deposit:{bank}", "asset", amount),
            engine.post(depositor, "cash", "asset", -amount),
        ),
    )
    engine.metrics["deposits_received"] += amount


def _loan_origination(engine: _Engine, event: Mapping[str, object]) -> None:
    _exact_keys(
        event,
        {"event_id", "kind", "loan_id", "bank_id", "borrower_id", "amount", "annual_interest_rate"},
        set(),
        "loan_origination",
    )
    event_id = _event_identifier(event["event_id"], "event_id")
    loan_id = _event_identifier(event["loan_id"], "loan_id")
    if loan_id in engine.loans:
        raise RegionalFinanceError(f"duplicate loan_id: {loan_id}")
    bank = engine.register(event["bank_id"], "bank")
    borrower = engine.register(event["borrower_id"], "enterprise")
    amount = _amount(event["amount"], "loan principal")
    rate = _rate(event["annual_interest_rate"], "annual_interest_rate")
    engine.add(
        event_id,
        "loan_origination",
        "financing",
        (
            engine.post(bank, f"loans_receivable:{loan_id}", "asset", amount),
            engine.post(bank, "customer_deposits", "liability", -amount),
            engine.post(borrower, f"bank_deposit:{bank}", "asset", amount),
            engine.post(borrower, f"loan_payable:{loan_id}", "liability", -amount),
        ),
    )
    engine.loans[loan_id] = _Loan(loan_id, bank, borrower, rate, amount, amount)
    engine.metrics["loan_originations"] += amount


def _loan_interest_accrual(engine: _Engine, event: Mapping[str, object]) -> None:
    _exact_keys(event, {"event_id", "kind", "loan_id"}, set(), "loan_interest_accrual")
    event_id = _event_identifier(event["event_id"], "event_id")
    loan = _loan(engine, event["loan_id"])
    if loan.principal_outstanding <= 0:
        raise RegionalFinanceError("interest cannot accrue on a repaid loan")
    with localcontext(_new_decimal_context()):
        amount = (loan.principal_outstanding * loan.annual_interest_rate / Decimal(12)).quantize(
            _MONEY_QUANTUM, rounding=ROUND_HALF_EVEN
        )
    if amount <= 0:
        raise RegionalFinanceError("monthly loan interest rounds to zero")
    engine.add(
        event_id,
        "loan_interest_accrual",
        "financing",
        (
            engine.post(loan.bank_id, f"interest_receivable:{loan.loan_id}", "asset", amount),
            engine.post(loan.bank_id, "interest_income", "income", -amount),
            engine.post(loan.borrower_id, "interest_expense", "expense", amount),
            engine.post(loan.borrower_id, f"interest_payable:{loan.loan_id}", "liability", -amount),
        ),
    )
    loan.interest_accrued += amount
    engine.metrics["interest_accrued"] += amount


def _loan_interest_payment(engine: _Engine, event: Mapping[str, object]) -> None:
    _exact_keys(event, {"event_id", "kind", "loan_id"}, {"amount"}, "loan_interest_payment")
    event_id = _event_identifier(event["event_id"], "event_id")
    loan = _loan(engine, event["loan_id"])
    amount = (
        loan.interest_accrued
        if "amount" not in event
        else _amount(event["amount"], "interest payment")
    )
    if amount <= 0 or amount > loan.interest_accrued:
        raise RegionalFinanceError("interest payment exceeds accrued unpaid interest")
    deposit_account = f"bank_deposit:{loan.bank_id}"
    engine.require_asset(loan.borrower_id, deposit_account, amount)
    engine.require_credit_balance(loan.bank_id, "customer_deposits", "liability", amount)
    engine.add(
        event_id,
        "loan_interest_payment",
        "financing",
        (
            engine.post(loan.bank_id, "customer_deposits", "liability", amount),
            engine.post(loan.bank_id, f"interest_receivable:{loan.loan_id}", "asset", -amount),
            engine.post(loan.borrower_id, f"interest_payable:{loan.loan_id}", "liability", amount),
            engine.post(loan.borrower_id, deposit_account, "asset", -amount),
        ),
    )
    loan.interest_accrued -= amount
    loan.interest_paid += amount
    engine.metrics["interest_received"] += amount


def _loan_principal_repayment(engine: _Engine, event: Mapping[str, object]) -> None:
    _exact_keys(event, {"event_id", "kind", "loan_id", "amount"}, set(), "loan_principal_repayment")
    event_id = _event_identifier(event["event_id"], "event_id")
    loan = _loan(engine, event["loan_id"])
    amount = _amount(event["amount"], "principal repayment")
    if amount > loan.principal_outstanding:
        raise RegionalFinanceError("principal repayment exceeds outstanding principal")
    deposit_account = f"bank_deposit:{loan.bank_id}"
    engine.require_asset(loan.borrower_id, deposit_account, amount)
    engine.require_credit_balance(loan.bank_id, "customer_deposits", "liability", amount)
    postings = [
        engine.post(loan.bank_id, "customer_deposits", "liability", amount),
        engine.post(loan.bank_id, f"loans_receivable:{loan.loan_id}", "asset", -amount),
        engine.post(loan.borrower_id, f"loan_payable:{loan.loan_id}", "liability", amount),
        engine.post(loan.borrower_id, deposit_account, "asset", -amount),
    ]
    # Cash recovered after a provision reduces both the allowance and the
    # credit-loss expense.  This keeps ending default exposure bounded by the
    # remaining principal instead of leaving a stale or negative net loan.
    allowance_reversal = min(amount, loan.default_exposure)
    if allowance_reversal:
        postings.extend(
            (
                engine.post(
                    loan.bank_id,
                    f"loan_loss_allowance:{loan.loan_id}",
                    "contra_asset",
                    allowance_reversal,
                ),
                engine.post(
                    loan.bank_id,
                    "credit_loss_expense",
                    "expense",
                    -allowance_reversal,
                ),
            )
        )
    engine.add(
        event_id,
        "loan_principal_repayment",
        "financing",
        postings,
    )
    loan.principal_outstanding -= amount
    loan.principal_repaid += amount
    loan.default_exposure -= allowance_reversal
    engine.metrics["principal_repaid"] += amount


def _loan_default(engine: _Engine, event: Mapping[str, object]) -> None:
    _exact_keys(event, {"event_id", "kind", "loan_id"}, {"amount"}, "loan_default")
    event_id = _event_identifier(event["event_id"], "event_id")
    loan = _loan(engine, event["loan_id"])
    unprovided = loan.principal_outstanding - loan.default_exposure
    amount = unprovided if "amount" not in event else _amount(event["amount"], "default exposure")
    if amount <= 0 or amount > unprovided:
        raise RegionalFinanceError("default exposure exceeds unprovided outstanding principal")
    engine.add(
        event_id,
        "loan_default",
        "credit_loss",
        (
            engine.post(loan.bank_id, "credit_loss_expense", "expense", amount),
            engine.post(loan.bank_id, f"loan_loss_allowance:{loan.loan_id}", "contra_asset", -amount),
        ),
    )
    loan.default_exposure += amount
    engine.metrics["default_exposure"] += amount


def _treasury_tax_assessment(engine: _Engine, event: Mapping[str, object]) -> None:
    _exact_keys(
        event,
        {"event_id", "kind", "treasury_id", "taxpayer_id", "amount"},
        set(),
        "treasury_tax_assessment",
    )
    event_id = _event_identifier(event["event_id"], "event_id")
    treasury = engine.register(event["treasury_id"], "treasury")
    taxpayer = engine.register(event["taxpayer_id"], "enterprise")
    amount = _amount(event["amount"], "tax assessment")
    engine.add(
        event_id,
        "treasury_tax_assessment",
        "treasury",
        (
            engine.post(taxpayer, "tax_expense", "expense", amount),
            engine.post(taxpayer, f"tax_payable:{treasury}", "liability", -amount),
            engine.post(treasury, f"taxes_receivable:{taxpayer}", "asset", amount),
            engine.post(treasury, "tax_revenue", "income", -amount),
        ),
    )
    engine.metrics["tax_assessed"] += amount


def _treasury_tax_receipt(engine: _Engine, event: Mapping[str, object]) -> None:
    _exact_keys(
        event,
        {"event_id", "kind", "treasury_id", "taxpayer_id", "amount"},
        {"settlement", "bank_id"},
        "treasury_tax_receipt",
    )
    event_id = _event_identifier(event["event_id"], "event_id")
    treasury = engine.register(event["treasury_id"], "treasury")
    taxpayer = engine.register(event["taxpayer_id"], "enterprise")
    amount = _amount(event["amount"], "tax receipt")
    if -engine.balance(taxpayer, f"tax_payable:{treasury}", "liability") < amount:
        raise RegionalFinanceError("tax receipt exceeds taxpayer tax payable")
    if engine.balance(treasury, f"taxes_receivable:{taxpayer}", "asset") < amount:
        raise RegionalFinanceError("tax receipt exceeds treasury tax receivable")
    settlement = event.get("settlement", "cash")
    if settlement == "cash":
        taxpayer_account = treasury_account = "cash"
        engine.require_asset(taxpayer, taxpayer_account, amount)
    elif settlement == "bank_deposit":
        bank = engine.register(event.get("bank_id"), "bank")
        taxpayer_account = treasury_account = f"bank_deposit:{bank}"
        engine.require_asset(taxpayer, taxpayer_account, amount)
    else:
        raise RegionalFinanceError("tax settlement must be cash or bank_deposit")
    engine.add(
        event_id,
        "treasury_tax_receipt",
        "treasury",
        (
            engine.post(taxpayer, f"tax_payable:{treasury}", "liability", amount),
            engine.post(taxpayer, taxpayer_account, "asset", -amount),
            engine.post(treasury, treasury_account, "asset", amount),
            engine.post(treasury, f"taxes_receivable:{taxpayer}", "asset", -amount),
        ),
    )
    engine.metrics["tax_receipts"] += amount
    engine.metrics["treasury_receipts"] += amount


def _treasury_receipt(engine: _Engine, event: Mapping[str, object]) -> None:
    _exact_keys(
        event,
        {"event_id", "kind", "treasury_id", "amount"},
        {"settlement", "bank_id"},
        "treasury_receipt",
    )
    event_id = _event_identifier(event["event_id"], "event_id")
    treasury = engine.register(event["treasury_id"], "treasury")
    amount = _amount(event["amount"], "treasury receipt")
    settlement, bank_id, account = _settlement(engine, event, treasury, incoming=True)
    postings = [
        engine.post(treasury, account, "asset", amount),
        engine.post(treasury, "other_receipts", "income", -amount),
    ]
    if settlement == "bank_deposit":
        assert bank_id is not None
        postings.extend(
            (
                engine.post(bank_id, "reserves", "asset", amount),
                engine.post(bank_id, "customer_deposits", "liability", -amount),
            )
        )
    engine.add(event_id, "treasury_receipt", "operating", postings)
    engine.metrics["other_treasury_receipts"] += amount
    engine.metrics["treasury_receipts"] += amount


def _settlement(
    engine: _Engine,
    event: Mapping[str, object],
    entity_id: str,
    *,
    incoming: bool,
) -> tuple[str, str | None, str]:
    settlement = event.get("settlement", "cash")
    if settlement == "cash":
        account = "cash"
        bank = None
    elif settlement == "bank_deposit":
        bank = engine.register(event.get("bank_id"), "bank")
        account = f"bank_deposit:{bank}"
    else:
        raise RegionalFinanceError("settlement must be cash or bank_deposit")
    if not incoming:
        engine.require_asset(entity_id, account, _amount(event["amount"], "settlement amount"))
    return settlement, bank, account


def _external_bank_outflow(
    engine: _Engine, settlement: str, bank_id: str | None, amount: Decimal
) -> tuple[_Posting, ...]:
    if settlement != "bank_deposit":
        return ()
    assert bank_id is not None
    engine.require_credit_balance(bank_id, "customer_deposits", "liability", amount)
    engine.require_asset(bank_id, "reserves", amount)
    return (
        engine.post(bank_id, "customer_deposits", "liability", amount),
        engine.post(bank_id, "reserves", "asset", -amount),
    )


def _result(engine: _Engine) -> dict[str, object]:
    transactions = [transaction.payload() for transaction in engine.transactions]
    total_debits = Decimal(0)
    total_credits = Decimal(0)
    with localcontext(_new_decimal_context()):
        for transaction in engine.transactions:
            for posting in transaction.postings:
                if posting.amount > 0:
                    total_debits += posting.amount
                else:
                    total_credits -= posting.amount
    imbalance = total_debits - total_credits
    gross = _statement_totals(engine)
    entities = [
        _entity_statement(engine, entity_id)
        for entity_id in sorted(engine.entity_types)
    ]
    consolidated = _consolidated_statement(engine, gross)
    cash_flow = _cash_flow(engine)
    ending_deposits = _customer_deposits(engine)
    gross_loans = sum((loan.principal_outstanding for loan in engine.loans.values()), Decimal(0))
    allowance = sum((loan.default_exposure for loan in engine.loans.values()), Decimal(0))
    treasury_cash = sum(
        (
            amount
            for (entity, account, account_type), amount in engine.balances.items()
            if engine.entity_types[entity] == "treasury" and account == "cash" and account_type == "asset"
        ),
        Decimal(0),
    )
    tax_receivable = sum(
        (
            amount
            for (entity, account, account_type), amount in engine.balances.items()
            if engine.entity_types[entity] == "treasury"
            and account.startswith("taxes_receivable:")
            and account_type == "asset"
        ),
        Decimal(0),
    )
    result = {
        "schema": REGIONAL_FINANCE_SCHEMA,
        "mode": "simulation_sidecar",
        "period": engine.period,
        "currency": engine.currency,
        "canonical": False,
        "notion_writes": 0,
        "canonical_ledger_postings": 0,
        "safety": {
            "notion_write_capability": False,
            "notion_writes": 0,
            "canonical_ledger_post_capability": False,
            "canonical_ledger_postings": 0,
        },
        "transactions": transactions,
        "journal": {
            "balanced": imbalance == 0 and all(item["balanced"] for item in transactions),
            "transaction_count": len(transactions),
            "posting_count": sum(len(transaction.postings) for transaction in engine.transactions),
            "total_debits": canonical_decimal(total_debits),
            "total_credits": canonical_decimal(total_credits),
            "imbalance": canonical_decimal(imbalance),
        },
        "banking": {
            "deposit_change": canonical_decimal(
                ending_deposits - engine.opening_customer_deposits
            ),
            "deposits_received": canonical_decimal(engine.metrics["deposits_received"]),
            "loan_originations": canonical_decimal(engine.metrics["loan_originations"]),
            "interest_accrued": canonical_decimal(engine.metrics["interest_accrued"]),
            "interest_received": canonical_decimal(engine.metrics["interest_received"]),
            "principal_repaid": canonical_decimal(engine.metrics["principal_repaid"]),
            "default_exposure": canonical_decimal(allowance),
            "ending_customer_deposits": canonical_decimal(ending_deposits),
            "ending_gross_loans": canonical_decimal(gross_loans),
            "ending_net_loans": canonical_decimal(gross_loans - allowance),
        },
        "treasury": {
            "tax_assessed": canonical_decimal(engine.metrics["tax_assessed"]),
            "tax_receipts": canonical_decimal(engine.metrics["tax_receipts"]),
            "other_receipts": canonical_decimal(engine.metrics["other_treasury_receipts"]),
            "receipts_total": canonical_decimal(engine.metrics["treasury_receipts"]),
            "ending_tax_receivable": canonical_decimal(tax_receivable),
            "ending_cash": canonical_decimal(treasury_cash),
        },
        "reports": {
            "balance_sheet": consolidated,
            "income_statement": {
                "income": consolidated["income"],
                "expenses": consolidated["expenses"],
                "net_income": consolidated["net_income"],
                "monthly_surplus": consolidated["net_income"],
            },
            "cash_flow": cash_flow,
            "entities": entities,
        },
        "loan_portfolio": [_loan_payload(engine.loans[key]) for key in sorted(engine.loans)],
        "ending_balances": _balance_payload(engine),
    }
    result["state"] = {
        "schema": "tnp.economy.regional-finance-state/1",
        "period": engine.period,
        "currency": engine.currency,
        "entity_types": [
            {"entity_id": entity, "entity_type": engine.entity_types[entity]}
            for entity in sorted(engine.entity_types)
        ],
        "balances": result["ending_balances"],
        "loans": result["loan_portfolio"],
    }
    if not result["journal"]["balanced"]:
        raise RegionalFinanceError("regional sidecar journal failed its final balance check")
    if Decimal(consolidated["equation_imbalance"]) != 0:
        raise RegionalFinanceError("consolidated balance sheet failed to reconcile")
    if not cash_flow["reconciles"]:
        raise RegionalFinanceError("consolidated cash-flow report failed to reconcile")
    return result


def _statement_totals(engine: _Engine) -> dict[str, Decimal]:
    totals = defaultdict(Decimal)
    for (_entity, _account, account_type), amount in engine.balances.items():
        totals[account_type] += amount
    asset_gross = totals["asset"]
    contra_assets = -totals["contra_asset"]
    liabilities = -totals["liability"]
    equity = -totals["equity"]
    income = -totals["income"]
    expenses = totals["expense"]
    return {
        "assets_gross": asset_gross,
        "contra_assets": contra_assets,
        "assets_net": asset_gross - contra_assets,
        "liabilities": liabilities,
        "equity": equity,
        "income": income,
        "expenses": expenses,
        "net_income": income - expenses,
    }


def _entity_statement(engine: _Engine, entity_id: str) -> dict[str, object]:
    totals = defaultdict(Decimal)
    for (entity, _account, account_type), amount in engine.balances.items():
        if entity == entity_id:
            totals[account_type] += amount
    assets = totals["asset"] + totals["contra_asset"]
    liabilities = -totals["liability"]
    equity = -totals["equity"]
    income = -totals["income"]
    expenses = totals["expense"]
    net_income = income - expenses
    imbalance = assets - liabilities - equity - net_income
    if imbalance != 0:
        raise RegionalFinanceError(f"entity balance sheet does not reconcile: {entity_id}")
    return {
        "entity_id": entity_id,
        "entity_type": engine.entity_types[entity_id],
        "assets": canonical_decimal(assets),
        "liabilities": canonical_decimal(liabilities),
        "equity": canonical_decimal(equity),
        "income": canonical_decimal(income),
        "expenses": canonical_decimal(expenses),
        "net_income": canonical_decimal(net_income),
        "equation_imbalance": "0",
    }


def _consolidated_statement(engine: _Engine, gross: Mapping[str, Decimal]) -> dict[str, object]:
    deposit_assets = _sum_accounts(engine, "asset", "bank_deposit:")
    deposit_liabilities = -_sum_exact_account(engine, "liability", "customer_deposits")
    loan_assets = _sum_accounts(engine, "asset", "loans_receivable:")
    loan_liabilities = -_sum_accounts(engine, "liability", "loan_payable:")
    interest_assets = _sum_accounts(engine, "asset", "interest_receivable:")
    interest_liabilities = -_sum_accounts(engine, "liability", "interest_payable:")
    tax_assets = _sum_accounts(engine, "asset", "taxes_receivable:")
    tax_liabilities = -_sum_accounts(engine, "liability", "tax_payable:")
    allowance = -_sum_accounts(engine, "contra_asset", "loan_loss_allowance:")
    interest_income = -_sum_exact_account(engine, "income", "interest_income")
    interest_expense = _sum_exact_account(engine, "expense", "interest_expense")
    tax_income = -_sum_exact_account(engine, "income", "tax_revenue")
    tax_expense = _sum_exact_account(engine, "expense", "tax_expense")
    credit_loss_expense = _sum_exact_account(engine, "expense", "credit_loss_expense")
    for left, right, label in (
        (deposit_assets, deposit_liabilities, "bank deposits"),
        (loan_assets, loan_liabilities, "loan principal"),
        (interest_assets, interest_liabilities, "accrued interest"),
        (tax_assets, tax_liabilities, "tax receivables"),
        (interest_income, interest_expense, "interest income/expense"),
        (tax_income, tax_expense, "tax income/expense"),
        (allowance, credit_loss_expense, "credit-loss allowance"),
    ):
        if left != right:
            raise RegionalFinanceError(f"consolidation mismatch for {label}")
    assets = gross["assets_net"] - deposit_assets - loan_assets - interest_assets - tax_assets + allowance
    liabilities = gross["liabilities"] - deposit_liabilities - loan_liabilities - interest_liabilities - tax_liabilities
    income = gross["income"] - interest_income - tax_income
    expenses = gross["expenses"] - interest_expense - tax_expense - credit_loss_expense
    net_income = income - expenses
    imbalance = assets - liabilities - gross["equity"] - net_income
    return {
        "scope": "regional_entities_with_internal_financial_claims_eliminated",
        "assets": canonical_decimal(assets),
        "liabilities": canonical_decimal(liabilities),
        "equity": canonical_decimal(gross["equity"]),
        "income": canonical_decimal(income),
        "expenses": canonical_decimal(expenses),
        "net_income": canonical_decimal(net_income),
        "equation_imbalance": canonical_decimal(imbalance),
        "eliminations": {
            "bank_deposits": canonical_decimal(deposit_assets),
            "loan_principal": canonical_decimal(loan_assets),
            "accrued_interest": canonical_decimal(interest_assets),
            "tax_receivables": canonical_decimal(tax_assets),
            "credit_loss_allowance": canonical_decimal(allowance),
            "interest_income_and_expense": canonical_decimal(interest_income),
            "tax_income_and_expense": canonical_decimal(tax_income),
        },
    }


def _cash_flow(engine: _Engine) -> dict[str, object]:
    by_activity: dict[str, Decimal] = defaultdict(Decimal)
    with localcontext(_new_decimal_context()):
        for transaction in engine.transactions:
            if transaction.activity == "opening":
                continue
            for posting in transaction.postings:
                if posting.account == "cash" or (
                    posting.entity_type == "bank" and posting.account == "reserves"
                ):
                    by_activity[transaction.activity] += posting.amount
    ending = _settlement_cash(engine)
    change = ending - engine.opening_settlement_cash
    classified = sum(by_activity.values(), Decimal(0))
    return {
        "opening_settlement_cash": canonical_decimal(engine.opening_settlement_cash),
        "operating": canonical_decimal(by_activity["operating"]),
        "financing": canonical_decimal(by_activity["financing"]),
        "treasury": canonical_decimal(by_activity["treasury"]),
        "credit_loss": canonical_decimal(by_activity["credit_loss"]),
        "net_change": canonical_decimal(classified),
        "ending_settlement_cash": canonical_decimal(ending),
        "reconciliation_imbalance": canonical_decimal(change - classified),
        "reconciles": change == classified,
    }


def _settlement_cash(engine: _Engine) -> Decimal:
    return sum(
        (
            amount
            for (entity, account, account_type), amount in engine.balances.items()
            if account_type == "asset"
            and (account == "cash" or (engine.entity_types[entity] == "bank" and account == "reserves"))
        ),
        Decimal(0),
    )


def _customer_deposits(engine: _Engine) -> Decimal:
    return -sum(
        (
            amount
            for (entity, account, account_type), amount in engine.balances.items()
            if engine.entity_types[entity] == "bank"
            and account == "customer_deposits"
            and account_type == "liability"
        ),
        Decimal(0),
    )


def _balance_payload(engine: _Engine) -> list[dict[str, str]]:
    rows = []
    for (entity_id, account, account_type), amount in sorted(engine.balances.items()):
        if amount == 0:
            continue
        normal = "debit" if account_type in {"asset", "expense"} else "credit"
        rows.append(
            {
                "entity_id": entity_id,
                "entity_type": engine.entity_types[entity_id],
                "account": account,
                "account_type": account_type,
                "normal_balance": normal,
                "signed_balance": canonical_decimal(amount),
                "display_balance": canonical_decimal(amount if normal == "debit" else -amount),
                "currency": engine.currency,
            }
        )
    return rows


def _loan_payload(loan: _Loan) -> dict[str, str]:
    return {
        "loan_id": loan.loan_id,
        "bank_id": loan.bank_id,
        "borrower_id": loan.borrower_id,
        "annual_interest_rate": canonical_decimal(loan.annual_interest_rate),
        "originated": canonical_decimal(loan.originated),
        "principal_repaid": canonical_decimal(loan.principal_repaid),
        "principal_outstanding": canonical_decimal(loan.principal_outstanding),
        "interest_unpaid": canonical_decimal(loan.interest_accrued),
        "interest_paid": canonical_decimal(loan.interest_paid),
        "default_exposure": canonical_decimal(loan.default_exposure),
        "net_exposure": canonical_decimal(loan.principal_outstanding - loan.default_exposure),
    }


def _sum_accounts(engine: _Engine, account_type: str, prefix: str) -> Decimal:
    return sum(
        (
            amount
            for (_entity, account, kind), amount in engine.balances.items()
            if kind == account_type and account.startswith(prefix)
        ),
        Decimal(0),
    )


def _sum_exact_account(engine: _Engine, account_type: str, account_name: str) -> Decimal:
    return sum(
        (
            amount
            for (_entity, account, kind), amount in engine.balances.items()
            if kind == account_type and account == account_name
        ),
        Decimal(0),
    )


def _loan(engine: _Engine, loan_id: object) -> _Loan:
    key = _event_identifier(loan_id, "loan_id")
    try:
        return engine.loans[key]
    except KeyError as exc:
        raise RegionalFinanceError(f"unknown loan_id: {key}") from exc


def _register_nonbank(engine: _Engine, value: object, label: str) -> str:
    entity = _identifier(value, label)
    known = engine.entity_types.get(entity)
    if known == "bank":
        raise RegionalFinanceError(f"{label} cannot identify a bank")
    return engine.register(entity, known or "enterprise")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise RegionalFinanceError(f"{label} must be a mapping")
    if any(not isinstance(key, str) for key in value):
        raise RegionalFinanceError(f"{label} keys must be text")
    return value


def _exact_keys(
    mapping: Mapping[str, object],
    required: set[str],
    optional: set[str],
    label: str,
) -> None:
    missing = required - set(mapping)
    unknown = set(mapping) - required - optional
    if missing:
        raise RegionalFinanceError(f"{label} is missing fields: {sorted(missing)}")
    if unknown:
        raise RegionalFinanceError(f"{label} has unsupported fields: {sorted(unknown)}")


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not _ENTITY_ID_RE.fullmatch(value):
        raise RegionalFinanceError(f"{label} must be a canonical identifier")
    return value


def _event_identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not _EVENT_ID_RE.fullmatch(value):
        raise RegionalFinanceError(f"{label} must be a canonical event identifier")
    return value


def _currency(value: object) -> str:
    if not isinstance(value, str) or not _CURRENCY_RE.fullmatch(value):
        raise RegionalFinanceError("currency must be a canonical uppercase code")
    return value


def _amount(value: object, label: str, *, allow_zero: bool = False) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise RegionalFinanceError(f"{label} must not use binary floating point")
    if type(value) is Decimal:
        result = value
    elif type(value) is int:
        result = Decimal(value)
    elif isinstance(value, str) and value and value.strip() == value:
        try:
            result = Decimal(value)
        except Exception as exc:
            raise RegionalFinanceError(f"{label} is not an exact decimal") from exc
    else:
        raise RegionalFinanceError(f"{label} must be a Decimal, integer, or exact decimal string")
    if not result.is_finite() or result < 0 or (result == 0 and not allow_zero):
        qualifier = "non-negative" if allow_zero else "positive"
        raise RegionalFinanceError(f"{label} must be a finite {qualifier} amount")
    if len(result.as_tuple().digits) > 60:
        raise RegionalFinanceError(f"{label} exceeds the exact-decimal precision contract")
    return result


def _rate(value: object, label: str) -> Decimal:
    result = _amount(value, label, allow_zero=True)
    if result > 1:
        raise RegionalFinanceError(f"{label} must be a decimal fraction from 0 through 1")
    return result
