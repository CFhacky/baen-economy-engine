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

## Rulings (2026-11-13)

The owner ruled the six P0 items on 2026-11-13 by adopting the evidence-backed proposals below (prepared from the native Notion export of 12 Nov 2026). Opening amounts remain provisional until the NCF vault and deposit figures exist and the first played month sets treasury cash; the engine stays fail-closed until an accepted opening fixture replaces this proposal. Fixture: `fixtures/canonical-import/opening-hammer-1495-proposed.json`; ledger proposal in campaign-development-vault `projects/in-progress/campaign-finance-ledger/docs/OPENING_SNAPSHOT_PROPOSAL_HAMMER_1495.md`.

| ID | Ruling | Status |
|---|---|---|
| CAN-001 | Open the Arik-side empire book at Day 7 Hammer 1495 DR (the engine's own boundary and ruling D1). Shi'van's trust, Institut and personal finances are a separate book at her lane (Day 911 / 6 Mirtul 1494). Jörmun's Crown of Eight Springs stays tracked, not consolidated (D9). Forward commissions (1502-1506) stay out of both. | RULED 2026-11-13: owner adopted the proposed answer (Chad, in conversation). |
| CAN-002 | Keep the books in gp only. No exact gp/Crown conversion rule was found in the pages read; none is applied. | RULED 2026-11-13: owner adopted the proposed answer (Chad, in conversation). |
| CAN-003 | The two monetary-authority pages point at each other (pointer loop recorded by the engine and by the Eastern finance screen). No reserve ratio or backing rule is applied until one page is named controlling. | RULED 2026-11-13: owner adopted the proposed answer (Chad, in conversation). |
| CAN-004 | Not applied. Creating spendable value without matching assets is refused by the engine; the books follow that. | RULED 2026-11-13: owner adopted the proposed answer (Chad, in conversation). |
| CAN-005 | Post 2,300,000 loans receivable as provisional. Deposits, reserves, notes outstanding and equity stay UNKNOWN. Use the parent's 22,000/mo as consolidated banking revenue (branches sum to 23,250; never 45,250). | RULED 2026-11-13: owner adopted the proposed answer (Chad, in conversation). |
| CAN-006 | Do not post a cash figure. Record the evidence band: 320,000-490,000 before old commitments (bridge test), and the current authority of a roughly 400,000 shortfall against a 450,000 protected target (22 Aug 2026). The Klauth hoard is carried at stated value as assets, not cash. | RULED 2026-11-13: owner adopted the proposed answer (Chad, in conversation). |
