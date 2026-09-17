# Canon Decision Docket

The engine fails closed on these questions. A decision changes accepted campaign
state, so code must not guess it.

## P0 — required before an opening snapshot

| ID | Decision | Why it blocks |
|---|---|---|
| CAN-001 | Select the economy timeline and opening campaign date | Registry rows span multiple protagonists and years |
| CAN-002 | Define gp/Crown denomination and conversion rules | Amounts cannot be combined without a named exact conversion |
| CAN-003 | Identify the controlling monetary-authority/backing source | Current authority pointers form a superseded circular reference |
| CAN-004 | Rule on the claimed Crown Advantage `25:1` mechanism | Creating spendable value without matching assets/liabilities violates conservation |
| CAN-005 | Accept an NCF opening balance sheet | Registry revenue and stated loan volume do not establish cash, reserves, deposits, equity, or impairment |
| CAN-006 | Accept opening treasury cash or an explicit unknown band | The current material only states an approximately 400,000 gp liquidity gap / 450,000 gp protected target, not exact cash |

The monetary-authority pointer
[`3c2e821484b081c085eecc74c2bcb35b`](https://app.notion.com/p/3c2e821484b081c085eecc74c2bcb35b)
points to superseded page
[`32ce821484b0814dbfebd60ac51ac338`](https://app.notion.com/p/32ce821484b0814dbfebd60ac51ac338),
which points back. Neither wins by traversal order.

## P1 — required before Ring 1 live advancement

| ID | Decision | Current safe behavior |
|---|---|---|
| CAN-101 | Choose NCF parent-summary or branch-bottom-up consolidation | Report 22,000 and 23,250 alternatives; reject 45,250 |
| CAN-102 | Classify NCF reserve deposits and restricted balances | Keep cash, reserves, deposits, guarantees, and commitments distinct |
| CAN-103 | Set Laden Table loan terms and draw timing | Preserve a 200–300K target only; post nothing |
| CAN-104 | Set Laden Table stock, ration, route, loss, and price inputs | Block actual execution; allow labeled preview assumptions |
| CAN-105 | Set Snowfall facility draw and construction-interest policy | Current draw remains zero |
| CAN-106 | Set Snowfall paid-in equity and guarantee custody | Preserve both as unresolved, not spendable cash |
| CAN-107 | Set carrying values for Klauth/other noncash assets | Preserve physical/canonical existence without invented financial basis |
| CAN-108 | Decide which 1496+ district records seed forecasts | Exclude from current actuals |
| CAN-109 | Adjudicate empire-wide revenue/profit ranges | Keep narrative ranges separate from registry raw sums |

## Recorded evidence, not opening balances

- Current narrative revenue: approximately 280,000–320,000 gp/month.
- Current narrative profit: approximately 75,000–90,000 gp/month.
- NCF stated loans: approximately 2.3M gp.
- Hard assets: approximately 18M gp.
- Cumulative deployed capital: approximately 12.5M–30M gp.

These ranges have different bases and confidence. They may appear in a
reconciliation report, but they do not balance one another and are not substituted
for the missing opening ledger.
