# Rate rulings booked + a correction — 19 Sep 2026 (fourth desk)

Branch `codex/reconcile-standalone-authority-20260917`. No Notion write. No month rolled. PR #1 open.

## 0. What went wrong on the last desk

I reported the Waterdeep unit rate and the Bloodaxe strength as open questions needing rulings. I had queried registry **properties** by SQL and **summary fields** in the Session Logs and Change Log. I had not opened the page bodies. Both answers were sitting in the bodies.

- The Waterdeep page body enumerates *"designed output 100–150/month optimized since Kythorn 1493"* and adds **"Not an open question."** The band was there; only the end was unpicked.
- The Bloodaxe page body carries the full establishment, the location table, and a growth ladder.

Corrected below. The method failure was reading property cells instead of the documents the property cells summarise.

## 1. CORRECTION — the Bloodaxe conflict does not exist

I reported "Bloodaxe 5,000 ruled vs 10,000 on the card" as a live conflict. **Withdrawn.** Canon Change Log 709's 5,000 is the *Forgedeep stationing* line, and the page's own location table shows why:

| Location | Cohorts | Troops |
|---|---|---:|
| Skyreach Castle | 2 (rotating) | 1,000 |
| **Forgedeep** | 6 + 4 training | **5,000** |
| Neverwinter | 2 | 1,000 |
| Gauntlgrym Road | 2 | 1,000 |
| External contracts | 4 | 2,000 |
| **Total** | **20** | **10,000** |

I read a garrison row as a total-strength restatement. **User ruling: 10,000 stands.**

## 2. Bloodaxe — what the body carries that the properties do not

**Establishment:** 20 cohorts. 19 at 480, 1st Cohort double-strength at 800. Squad 10 → Century 80 → Cohort 480 → Legion ~10,000.

**Growth ladder (stated goals, not booked strength):** 6-month **11,000** · 1-year **12,000** · 5-year **15,000**.

**Budget, now booked:** official cover 15,000/mo as a security company against **150,000/mo actual** — personnel 75,000, equipment 25,000, ops/training 20,000, facilities 15,000, reserves/benefits 15,000. Difference laundered through construction contracts. Revenue 30,000/mo = caravan 15,000 + municipal 10,000 + training 5,000. **Net cost to Baen Enterprises ~100,000/mo.** `wage_rate` on `emp:bloodaxe` is now 75,000, SOURCE.

**Legion-level assets outside the cohorts:** Mage Cadre 14, Military Intelligence 250, Marine Corps 200 (→500), Executive Security 100, Devil Liaison 50, Moranth Corps 20 + 100 distributed. Sappers ~1,250. Magically talented ~1,500 (15%).

**Wyrmhelm Wing:** **zero deployed** as of Alturiak 1495. Year 3–5: 20 Chargers + 40 Coursers. Year 10: three wings, 500–800 mature. 30,000 devil troops pending deployment.

**Readiness:** Tier 1 immediate 2,000 · Tier 2 48-hour 4,000 · Tier 3 reserve 2,000 · Tier 4 deployed 2,000, rotating every 3–4 months.

**Collision warning kept:** Inevitable City forces run **separate cohort numbering**. Surface 4th ≠ Inevitable City 4th.

## 3. Waterdeep ruled at 150/month

New table `data/canonical/production_rates.csv` — the thing that was actually missing.

| site | pattern | units/mo | sale | keep | invoice/mo | keep/mo | cost/mo | net | margin |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Waterdeep | Legionnaire | **150** (ruled) | 30,000 | 4,000 | **4,500,000** | 600,000 | 95,900 | 504,100 | 84% |
| Neverwinter | Legionnaire | 12 (sourced, ceiling 15) | 30,000 | 4,000 | 360,000 | 48,000 | 20,000 | 28,000 | 58% |
| Neverwinter | Solar Guard | 2 (sourced) | 100,000 | 80,000 | 200,000 | 160,000 | — | — | — |

`fac:warborn-wd` Monthly Revenue moves **3,000,000 → 4,500,000**. Monthly Cost moves **22,900 → 95,900**, because 22,900 is the wages line only; the page's full model is wages 22,900 + materials 45,000 + facility overhead 15,000 + equipment maintenance 8,000 + security 5,000.

**All Solar Guard production is Neverwinter, not Waterdeep.** 3 weeks per unit, 2/month max, concurrent with Legionnaire work.

## 4. Wage rates exist after all

I previously reported that no page states a wage. Wrong — both plant bodies carry full role tables. `wage_rate` is now populated and SOURCE on three rows:

- `emp:warborn-nw` **8,900/mo** across 77 heads (~116 gp/worker) — 1 Master Engineer 300, 4 Senior Machinists 800, 12 Precision Machinists 1,800, 20 Assembly Specialists 2,000, 30 Junior Workers 1,800, 10 QC 1,200, Security 1,000. The page names this the empire-wide payroll baseline.
- `emp:warborn-wd` **22,900/mo** across 200 heads — 2/8/30/60/80/20 + security. Headcount is the design complement, not a counted payroll tape.
- `emp:bloodaxe` **75,000/mo**.

Both wage lines sit **inside** their cost boxes, not on top of them.

## 5. The contract still does not close

- Waterdeep 150 + Neverwinter 12 = **162 Legionnaire/month**
- Required: 5,000 ÷ 24 = **208.33/month**
- **Shortfall 46.33/month.** At Neverwinter's 15/mo ceiling: 165, still 43.33 short.
- Network invoice at 162/mo: **4,860,000** + Solar Guard 200,000
- The old plan assigned the remainder to Forgedeep (~50/mo by month 24). Forgedeep is not booked live.
- The 6,440,000 figure reconciles exactly at contract pace: 208 × 30,000 + 2 × 100,000. It was never a competing model — it is the *required* rate, not the *achieved* one.
- Neverwinter page also names 747,000 gp/mo profit at full network scale.

## 6. Silversheen allocation reconciled

STATUS.md listed "Silversheen 30 t/mo vs 20% Warborn allocation" as an unruled conflict. It is not two figures. The Neverwinter page says *"Aluminum: 30 tons/month allocation from Silversheen Trading (20% of current output)"* — **30 t is 20% of 150 t/mo**, the Eleint 1494 baseline. At the Hammer 1495 ruled output of **180 t/mo** (Change Log 709), the same 20% share is **36 t/mo**.

Same rule, two output stamps. The only open part is whether the fixed 30 t or the floating 20% governs at Hammer 1495.

## 7. Also on the bodies, recorded not booked

- Waterdeep planned capital stack **1,127,000** (Phase 1 site 220,000 + Phase 2 equipment 457,000 + stockpile 250,000 + working capital 200,000). Registry Capital Invested still reads **907,000** — the older estimate, deliberately not overwritten.
- Waterdeep material plan at 208 network units/mo: Hell iron 167 t/mo with a 1,000 t six-month buffer, aluminium 30 t, tool steel 25 t, copper 5 t, bronze 4 t, silver 0.8 t, crystals 2,000, oils 800 gal, abrasives 8 t.
- Neverwinter holds a 3-month material buffer as backup site; Hell iron arrives ~40 t/week via Inevitable City gates.
- Seliara Frostwind is named a single point of failure across Warborn, Eternal Dancers, Stride and Power Armor.
- "Crown Advantage": a Legionnaire at 4,000 Crowns costs ~160 oz gold-equivalent against 4,000 oz for a competitor — a 25:1 production-cost advantage. Doctrine, not a booked line.

## 8. Tables

`actors 38 · relationships 46 · accounts 13 · employment 90 · ownership 16 · loans 7 · contracts 6 · facilities 90 · programmes 16 · transactions 49 · canon_rulings 12 · source_collections 21 · production_rates 3` — **407 rows, zero dangling references.**

## 9. Still open

- The 46/month contract shortfall — Forgedeep is the planned answer and is not booked.
- Waterdeep capital 907,000 vs 1,127,000.
- Whether Silversheen's Warborn allocation is fixed 30 t or floating 20%.
- Day-7 vs Hammer-1496 boundary leakage (unchanged from the last receipt).
- Institut 45,000 vs 28,000 (unchanged).
- 779 Canon Change Log rows still unread; GM Consequence Ledger 272, Deferred Dice 282, Faction Beliefs 57 still uncensused.
- **Method change:** page bodies before property cells, on every entity that matters. The registry properties are summaries of the documents, and the documents carry the tables.
