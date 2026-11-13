# Four-lane ingest — 19 Sep 2026 (third desk)

Branch `codex/reconcile-standalone-authority-20260917`. No Notion write. No month rolled. PR #1 open.
Boundary: **Day 7 Hammer 1495 DR** — and that boundary is now provably leaking. See §5.

## 0. Headline

The 17 Sep census enumerated **10 collections / 1,381 live rows**. The workspace has **21 databases / 3,191 live rows**.
The census missed **1,810 rows — more than it captured.** `coverage_claim_allowed = false` was measured against a denominator roughly 43% of the real one.

Full inventory now in `data/canonical/source_collections.csv`.

## 1. Transaction Ledger — harvested, all 49 rows

`collection://ae367fe3-d5fd-47db-b4d3-eafb13b9d081` → `data/canonical/transactions.csv`.

Only 5 of these rows had ever reached the engine. **Every one of the 49 is on the Shi'van clock, Day 234 → Day 814. Zero Arik Hammer 1495 rows.** Gross inflow 1,095,340; gross outflow 714,329; 21 recurring rows netting +38,221/month — all Shi'van, none addable to Arik's month.

Three rows are `Estimated`, not `Exact`, and are stamped `state_origin=ESTIMATED`: ESAMT quarterly investment income (~4,200/mo), B&D bespoke commissions (3,300/mo), Observer Network professional tier (−1,800/mo).

What it produced downstream:

**Four NCF facilities that were never in `loans.csv`:**

| loan_id | principal | rate | basis |
|---|---:|---:|---|
| `loan:ncf:institut-capital` | 132,000 | 6% | Day 393 S31 **GM ruling** — 48K workshop + 80K looms + 4K misc as a separate NCF commercial mortgage against Institut cash flow, explicitly **not** ESAMT. 660/mo. |
| `loan:ncf:celestial-compass-estate` | 127,000 | 4% | Day 310 S9. 47–53 Sapphire St. 5,080/yr = ~423/mo, interest-only initially. |
| `loan:ncf:esamt-ruby-facility` | outstanding **454,116** | 4% | Day 733 S41. Ruby-secured. Balance is as of Shi'van Day 733. |
| `loan:ncf:baen-innovations-line` | 50,000 | — | Day 510 S20, approved undrawn. |

**Two sourced opening balances** — the first real ones besides SSAMT's 12,000:
- `acct:trust:esamt-corpus` **1,010,000 gp** — the foundation ruby, flawless extraordinary grade, certified by Master Goldweaver, Day 234 S7.
- `acct:ncf:baen-innovations` 10,000 gp, Day 510 S20.

**ESAMT is not SSAMT.** ESAMT is Shi'van's estate trust (ruby corpus, ruby-secured facility). SSAMT is Scales & Secrets Asset Management Trust (12,000 liquid, Skrix Copper-Scale settlor). Two trusts, two tables, previously one blur. New actor `actor:trust:esamt` booked.

**A live NPC lever:** Day 570 S19 cleared Dorothea Varnilly's 460 gp gambling debt at the Winking Eye. Varnilly is the **NCF Waterdeep Branch Manager**. Flagged for the Veil layer, not actioned.

**A new Institut P&L that contradicts the registry card** — see §4.

## 2. Canon Change Log — 789 rows, 10 binding entries extracted

`collection://83d9b4a3-9489-46e0-b7d5-d17ba224ef68` → `data/canonical/canon_rulings.csv`. 779 rows remain unread.

### The Silversheen conflict is RULED — entry 709

Forgedeep audit, 2026-07-28, "effective at current play position, Hammer 1495 DR":

> **Silversheen ownership tightened to 50 Gauntlgrym / 30 NCF / 20 Baen.**

Both prior records were wrong. `ownership.csv` said NCF 60 / Gauntlgrym 40. The registry card said "NCF 30% / Gauntlgrym 50%" and **omitted the Baen 20% entirely**. `own:ncf-silversheen` is deleted; three ruled rows replace it and sum to 100%.

Same entry also rules **Silversheen output 180 t/mo at Hammer 1495** (150 = Eleint 1494 baseline; the location page's 120 is retired) → `prog:silversheen-aluminium`. No price per tonne is stated anywhere, so no gold was derived from the tonnage.

Same entry surfaces two more conflicts it does **not** resolve:
- **Bloodaxe Legion stationing 5,000** (6 garrison + 4 training cohorts) + 300 Cradle detail — against the registry card's **10,000**. Left visible.
- **Kalnar Stonebrow's role corrected** from "erroneous NCF Director" to Chief Infrastructure Engineer / Baen-Gauntlgrym Liaison. The NCF parent card's Known Assets field **still reads "Kalnar Stonebrow (director)"** and is stale.

### Zariel scope is 40× larger than the book — entry 548

> **Total scope 200,000 Legionnaire frames.** The 5,000 + 21 Solar Guard is the **first tranche only**, deadline ~late 1496. First-tranche performance gates the remaining 195,000. Multi-generational — 50+ years at projected scale.

The entry prices that at "~800M gp at 4,000/unit" — which is 200,000 × **keep**, not sale. At the 30,000 sale price the same scope invoices ~6.0 billion. **The exact 4,000-vs-30,000 confusion the handoff warned about is present in the canon log itself.** Both figures recorded on `prog:warborn-line-a`; neither adopted.

### A Day-7 programme with no registry card — entries 744/745/746

Warborn engineering trade school, stamped "Day 7, Hammer 1495 DR — no time advance", so it sits exactly on the boundary. 100-acre tract on the north bank of the Neverwinter River opposite Thundertree. Paid vocational pipeline; doubles as the contingent Mighty Servant of Leuk-O quarantine campus. **No Business Registry entity, no headcount, no fees, no capital.** Booked as `prog:warborn-engineering-school` with everything blank.

## 3. Session Logs + Prose Scenes — scanned, and the answer is negative

- Session Logs `a5071385-…`: **81 rows, S001–S078, 9 arcs.** Warborn/Silversheen keyword sweep returns 4 rows, all narrative (Elena Drakmoor into the Silent Storm frame; the Iron Court demonstration; a "Warborn quality issue" mention). **No production counts.**
- Prose Scenes `cc6940d9-…`: **182 rows.** Warborn / frame / Silversheen sweep returns 8 scenes, all Hell-arc demonstration and soul-transfer narrative. **No production counts.**

**So the Waterdeep Warborn unit rate is a ruling gap, not an unread page.** Canon Change Log entry 789 says it outright — *"Waterdeep unit rate not invented. Neverwinter 12/mo 48k remains only sourced site rate."* I predicted prose would likely close this. It does not, and now that is proven across 263 rows rather than assumed. The 3,000,000 revenue cell stays a floor with no measured rate behind it, and it needs a ruling from you, not another read.

Live pointer recovered while doing this: **Arik ~Day 5 Hammer 1495 DR** (Avernus, Skyreach over the Inevitable City, S074 by Date Played) and **Shi'van Day 911 / 6 Mirtul 1494 DR** (S073, Session 44). The Transaction Ledger stops at Day 814 — **97 Shi'van days of played time carry no ledger rows.**

## 4. Conflicts — two resolved, four new

**Resolved:** Silversheen ownership (entry 709). Tissage/Stelmane partially — Day 234 shows a real 10,000 gp Duchess Stelmane commission received into ESAMT, so Stelmane is a confirmed paying counterparty; the card's "~25K/mo uplift" is still not reconciled against the card's own 28,000 total.

**New, all left visible:**

1. **Institut P&L.** Transaction Ledger Day 500 books Institut gross revenue **45,000/mo** (20K protection, 15K high fashion, 8K technical, 2K consulting) and operating cost **12,000/mo**. The registry Tissage card says **28,000 / 17,500**. Nearly a 2× revenue gap on the same business. Both recorded.
2. **Bloodaxe headcount** — 5,000 ruled vs 10,000 on the card.
3. **NCF parent Known Assets** names Kalnar Stonebrow as director; entry 709 calls that erroneous and corrected.
4. **Boundary leakage** — §5.

## 5. The boundary is leaking, and it is in facilities.csv right now

The Change Log shows Arik-lane play resolved **past** Day 7 Hammer 1495, and some of that forward state is already sitting in the registry cards this engine reads as Day-7 truth:

| ruling | in-world date | what it put in the table |
|---|---|---|
| cl:97 | Alturiak 1495 | ~410,000 gp Klaúth art float realised — very likely the "~400k gap / 450k target" on the Cash Position page |
| cl:100 | Alturiak 1495 | that float deployed to lock Adbar + Mithral Hall against an Aldric underbid |
| cl:253 | **Hammer 1496** | Baen Real Estate consolidated — which is why `fac:housing-portfolio` Date Operational reads "1494 DR; current state Hammer 1496 DR" |
| cl:283 | Hammer 1496 | Green Vein complete Marpenoth 1495, tolls ~1,500 gp/mo |
| cl:709 | — | Formicorps banded as **1496 forward canon** — `fac:formicorps` is a forward row |

All five are marked `AHEAD_OF_BOUNDARY` in `canon_rulings.csv` and **none is booked**. But `facilities.csv` is currently a mix of Day-7 states and Hammer-1496 states with nothing distinguishing them. That is a bigger integrity problem than any single missing number, and it needs a boundary ruling before a canonical month can ever run.

## 6. Tables now

| file | rows | |
|---|---:|---|
| actors.csv | 38 | +3 (ESAMT trust, Baen Innovations, Gauntlgrym) |
| facilities.csv | 90 | unchanged |
| employment.csv | 90 | unchanged |
| programmes.csv | 15 | +2, Line A amended |
| transactions.csv | **49** | **new** |
| canon_rulings.csv | **10** | **new** |
| source_collections.csv | **21** | **new** |
| loans.csv | 7 | +4 |
| accounts.csv | 13 | +2 |
| ownership.csv | 16 | Silversheen ruled |
| contracts.csv | 6 | unchanged |
| relationships.csv | 46 | unchanged |

**401 canonical rows. Zero dangling references. Silversheen sums to 100%.**

## 7. Still open

- 779 Canon Change Log rows unread. That is the richest remaining lane and it is pure ruling history.
- GM Consequence Ledger (272) — a **third** consequence ledger, distinct from A and B. Never censused.
- Deferred Dice (282) — pending rolls with trigger conditions, several likely economic.
- Faction Beliefs (57) — distinct from "The New Path - Factions"; the empire-ops skill cross-references it and the engine has never read it.
- Creation Registry (41), Shadow Events (35), Kingdoms & Factions (12), Character Sheets (10).
- Days 815–911 of Shi'van play carry no Transaction Ledger rows.
- **Needs your ruling, not a read:** Waterdeep Warborn unit rate; the Day-7 vs Hammer-1496 boundary; Institut 45,000 vs 28,000; Bloodaxe 5,000 vs 10,000; whether the ~410k Klaúth float becomes an opening balance.
- Unchanged: NCF reserves/equity absent, no wage rates on any page, canonical month **CLOSED**.
