# Canon Change Log + GM Consequence Ledger — harvest

Date: 2026-09-19. Branch: `codex/reconcile-standalone-authority-20260917`.

---

## §0 — The headline

**The empire has had a canonical financial anchor page since 24 April 2026 and this engine had never opened it.**

Canon Change Log entries **9** and **10**, both Session-blockers, point at:

- **📊 Empire Financial State — Current Reference** (`34ce821484b081d7abb5f5d9cf153d72`) — *"This page supersedes the Kythorn-1494-anchored figures in BAEN_EMPIRE_COMPREHENSIVE_BUSINESS_OVERVIEW for all current-play decisions. Load this at session start when financial context is needed."*
- **💰 Cash Position Reconciliation — Hammer-Alturiak 1495 DR** (`34ce821484b081c08dd4c3122711cc8e`) — its child.

Every one of my "accounts.csv carries no balances, this is a page hole" notes was wrong for the same reason the wage notes were wrong: I had not opened the page.

---

## §1 — The empire's balance sheet at the boundary

`accounts.csv` gains three rows that did not exist:

| account | amount | state |
|---|---:|---|
| `acct:household:liquid-position` | **−400,000** | SOURCE |
| `acct:household:klauth-hoard-remaining` | 1,700,000–2,700,000 | SOURCE_RANGE |
| `acct:household:hard-assets` | ~18,000,000 | APPROX_SOURCE |

**The liquidity position.** The 22 Aug 2026 override callout on the Cash Position page sets current authority: a **~400,000 gp Shimmerdeep/Crown liquidity gap** against a **protected 450,000 gp net-settled target** including operating buffer. Its own −277,000 arithmetic is explicitly retained as a superseded model. That model's sensitivity band still reads:

| Klauth gem liquidation | liquid position |
|---|---:|
| Aggressive (80% over 9mo) | +73,000 |
| Midpoint (67%) | −277,000 |
| Slow (50%) | −807,000 |
| **Held (0%)** | **−2,277,000** |

And the page says plainly: *"If gems are substantially un-liquidated, the empire is operating at a 2M+ gp deficit supported only by the NCF lending engine and the continuing monthly operating profit."*

This is what my earlier 450,000 gate was measuring against. Against ~18M of hard assets and 1.7–2.7M of monetizable hoard, **the empire at Day 7 Hammer 1495 is asset-rich and cash-poor** — and 2,300,000 of the NCF loan book, which `loans.csv` already carries, is the thing holding it up.

Other headline figures now on record: MRR 245,000 (Eleint-20 snapshot) / 280,000–320,000 realistic current; monthly profit ~75,000–90,000 at a 31% margin; Jörmun-arc running a −30 to −450/mo shortfall; cumulative deployed 12.5M conservative / 30M upper band; GURPS Wealth Level Filthy Rich (×100).

---

## §2 — The Warborn rollup confirms the rate table independently

The anchor page carries a **WARBORN ROLLUP block dated 19 Sep 2026** tabulating exactly what `production_rates.csv` already holds:

| Line | Frames/mo | In | Keep |
|---|---:|---:|---:|
| Neverwinter (sourced) | 12 | 360,000 | 48,000 |
| Waterdeep at card low | 100 | 3,000,000 | 400,000 |
| **Waterdeep at card high** | **150** | **4,500,000** | **600,000** |
| Both plants | 162 | 4,860,000 | 648,000 |

First tranche 5,000 Legionnaire + 21 Solar Guard = **152,100,000 invoices / 21,680,000 keep**. 6,440,000/mo is network pace at 208 frames, not a Hammer 1495 deposit.

It also names a hazard I had not guarded against: **the 245,000 headline MRR already contains Neverwinter as 48,000 "revenue" — which is the keep, not the invoice.** Replace that 48,000 with 360,000 before adding Waterdeep, or you triple-count. Recorded as `corr:mrr:headline`.

---

## §3 — Applied

- **`fac:athenaeum` capital 200,000 → 500,000.** Chad ruled it on 2026-08-26 (Tracker canonical, canon entry `3c8e8214-84b0-8185`). I had it flagged as an open conflict purely because I had not read the page.
- **Castle Operations = Skyreach**, per the user's ruling. `facilities.csv` gains a `consolidation` column: `fac:skyreach` is `PRIMARY_OF:fac:castle-ops`, `fac:castle-ops` is `DUPLICATE_OF:fac:skyreach`, and the shared 5,200 gp/mo is counted once. Both rows kept, because the live registry still carries two cards. Two things the ruling doesn't settle, now logged as `corr:castle-skyreach:headcount`: the headcount is 80 on one card and 28 on the other, and the Skyreach body ties cost to crew size (6/28/100 → 1,900/8,500/26,500), so the shared 5,200 matches no crew tier on either card.

## §4 — Recorded, not applied

- **Warborn Waterdeep capital.** Anchor page says 1,127,000 (three times). The live registry card, re-queried today, says 907,000. **907,000 + 220,000 — the Phase 1 site figure both pages name — = 1,127,000 exactly.** The decomposition is my arithmetic, not a stated reconciliation, so the cell stands and the reading goes in `corrections.csv`.
- **Formicorps: three figures for one entity.** Registry card 2,500,000; anchor deployment schedule ~1,050,000; anchor Top-10 list "total startup 1,400,000". A 1,450,000 gap — the largest single unexplained capital discrepancy in the set.
- **Hunding: 50,000 on the card against ~1,550,000 deployed** (1,050,000 canal + 500,000 mechanism), with a third reading in the Eleint-20 "Canal Completion 2,000,000" commitment the page itself says to verify with Vara.
- **Verdant Cascades** 32,000 vs 80,000 — the page's own read is "both likely correct at different dates."
- **Zariel contract card** reads 360,000/mo, the anchor's table reads 747,000. The anchor separately warns against treating 747k or 6.4M as Hammer 1495 deposits. 360,000 stands — and must not be added to `fac:warborn-nw`'s 360,000, which is the same gold.

## §5 — Unbooked money found

Nine new rows in `unbooked_items.csv`. The ones that matter:

- **Guardian's Gate Level 1 — 2,000,000 gp deployed and active, with NO Business Registry card.** The only Guardian's Gate row in the registry is `[SUPERSEDED] Guardian's Gate Settlement (older variant)` at 30,000. `facilities.csv` structurally cannot carry the empire's largest active construction. Levels 2–4 are a further 3,250,000, held until liquidation clears.
- **Warborn Waterdeep Phase 2 equipment, 457,000 gp** — gated on Zariel first settlement, and it is the capacity the 200,000-frame contract needs.
- **The southern investor's 2,500,000 gp offer**, apparently declined on intelligence-liability grounds, with — in the page's own words — *"no project file canonizes the decline."* A 2.5M decision with no decision record. The Cash Position page recommends re-opening it structured as a deposit rather than equity.
- **Klauth art liquidation, 800,000 gp** — the single named remedy for the live gap, "rebuilds 500K+ operating buffer within 60 days." Recommended, not executed.
- From the Consequence Ledger: an **ESAMT draw of 127,016 gp** (three commitments funded — flagged as possibly the same event as the 127,000 Celestial Compass loan, 16 gp apart); the **B. Taranis polo commission, 14,400 gp**; the **Amphail acquisition**, pre-locked ESAMT authorization with no amount, firing on next surfacing, against Quentin Shaw buying up Dessarin corridor waystations on a 6-day window; and **bonded agreements for 8 staff at +10% wages** going live ~Day 780.

The Amnian diplomatic contract (14 pieces, 90-day delivery) is also now on record — and it is the "active institutional commission" that explains the Tissage 45,000–47,000 spread against its 28,000 steady state.

---

## §6 — Jarlaxle's feed has already been cashed

`exp:tinkle:split-fountain` is escalated from `PASSIVE_OBSERVER` to **`ACTIVE_LEVERAGE / FIRED`**.

Canon Change Log 778: the Shadow Gate Network was rolled forward from a stale 45% Eleint 1494 snapshot — *construction clocks had never fired in play* — to **92.9% with six nodes live** at Day 7 Hammer 1495. Baldur's Gate, Silverymoon and Suzail all came operational across Marpenoth–Nightal. Exposure rolled quiet all four months.

The leak was not the network. **Jarlaxle's quarterly d6 came up 6 — LEVERAGES DIRECTLY — adjudicated as Tinkle Brassworth's technical feed on the Baldur's Gate anchor contract, with the approach landing on Lirien in Nightal carrying an offer about Suzail.** Unresolved, pending a scene.

Put beside the board seat on the Northern Crown Banking Syndicate, the Dagny re-tasking to Cormyr, the harbour drift clause, and the NHH adverse-possession claim whose principal may be "Bregan D'aerthe financial interests" — that is four separate instruments, and one of them has now been used.

---

## §7 — What the Consequence Ledger actually is

272 rows, enumerated by Status/Severity/Timeline; every Active Crisis and Arc-Level row read, plus every Commercial-type Active and Queued row.

It is **a narrative pressure register, not a money table**, and it is Shi'van-weighted. Saying so is the finding; there was no point force-fitting it into the economy.

The live Arik-side crises at the boundary are Tiamat's: **a peer chromatic dragon in transit to Avernus on a ~30 Hell-day arrival**, and **three consort-ring scrying programs closing on Arik's name inside a 10–40 Hell-day window** — broad-volume over the Inevitable City, not on Skyreach specifically, because she does not yet know the location. That is the pressure the closed canonical month is sitting under.

---

## §8 — Still open

- **748 Canon Change Log rows** below the Open-Item and Session-blocker tiers remain unread. The two that mattered most are now in.
- Deferred Dice (282), Faction Beliefs (57), Creation Registry (41), Shadow Events (35), Kingdoms & Factions (12), Character Sheets (10) still uncensused.
- Arik's surface calendar reads **1496 DR** per entry 749 (he is in the Hells; Black Sluice crossing), while entry 787 of 2026-09-17 confirms *"the Day 7 Hammer 1495 DR / Skyreach live boundary is unmoved."* Both are true and they need a stated reconciliation before any month is rolled.
- The 12 `UNRESOLVED_CONFLICT` rows in `corrections.csv`.
- Canonical month stays CLOSED. No Notion writes. PR #1 open, draft, unmerged.

**514 canonical rows. Zero dangling references.**
