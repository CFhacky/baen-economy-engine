# Finance-Ledger Integration Review

## Dependency

This branch is stacked on draft PR #48, `codex/campaign-finance-ledger`, reviewed
at commit `ac6523d404a099dec624930d757478b5317dd471`. That project supplies useful
policy, a chart, fixtures, and Beancount-shaped journals. The economy engine does
not duplicate those files.

## Accepted boundary

The economy engine owns a typed immutable `JournalEvent` and translates only
resolved finance-phase events already accepted by the append-only `EventStore`.
Each posting requires:

- an event ID, canonical full-envelope and payload hashes, authority, revision,
  timeline, model version, and source reference;
- a Gregorian book date plus a separate campaign-date label;
- at least two postings;
- exact Decimal amounts balanced independently by currency;
- valid Beancount account/currency grammar and an exact match to an immutable
  account-open contract, including allowed currencies and effective open/close
  dates, before entering or exporting a book;
- event-specific semantic signs for deposits, loans, and treasury borrowing;
- a duplicate-event rejection gate.

A correction revision makes the preceding event inactive, but correction events
cannot mutate stock or enter the journal in Gate 0. Explicit reversal and
replacement postings are required before corrected financial effects can be
accepted; this prevents a 100 gp original plus 110 gp correction from appearing
as 210 gp.

Only a `JournalBook` can export an accepted event, preventing direct rendering
from bypassing the chart-of-accounts gate. Beancount remains a validator/export
boundary, not the simulation state store.

## Correct banking treatment locked by tests

The bridge is pinned to the aggregate accounts opened by PR #48, rather than
inventing customer- or currency-suffixed subaccounts:

| Event | Debit | Credit |
|---|---|---|
| Customer deposit | `Assets:NCF:Reserves` | `Liabilities:NCF:Deposits` |
| Deposit-created loan | `Assets:NCF:Loans-Receivable` | `Liabilities:NCF:Deposits` |
| Repayment from deposit | `Liabilities:NCF:Deposits` | `Assets:NCF:Loans-Receivable` principal and `Income:NCF:Interest` interest |
| Treasury borrowing | `Assets:Treasury:Cash` | `Liabilities:Debt:External` |

Treasury borrowing never recognizes revenue or profit.
- Undrawn facilities are commitments, not cash, receivables, or debt.

## Blocking defects in the draft ledger runtime

The dependency's fallback parser is suitable for its current fixtures, not as an
authoritative campaign runtime:

1. fallback parsing fails open on unsupported syntax;
2. account-open validation is not enforced by that path;
3. metadata needed for provenance and campaign dates is discarded;
4. event IDs and idempotency are not enforced;
5. entity, ownership, consolidation, and intercompany eliminations are absent;
6. physical quantities and cost-lot provenance are absent;
7. suspense amounts could be mistaken for spendable funds without a hard gate.

The new bridge closes the first four at its boundary. Consolidation, inventory
valuation, impairment/default, reserve policy, and accepted opening balances remain
Gate 2 work. `bean-check` is not installed in the current runtime, so external
Beancount validation must remain a clearly reported pending check.
