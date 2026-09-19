# Canon Change Log — all 789 rows

Date: 2026-09-19. Branch: `codex/reconcile-standalone-authority-20260917`.
Prior pass read the 37 Open Item and 41 Session-blocker rows. This one reads the other 712.

---

## §1 — The headline: there is a second treasury, in a second currency, and it went live the day before the boundary

Entries **608 → 613 → 664 → 710** build it in four steps.

**The Hell Treasury** is an off-ledger soul-coin financial system of the Inevitable City, administered by **Vesper**. Arik authorized it in person at her office on **6 Hammer 1495 DR** — one day before this engine's boundary — and the page was stamped **ACTIVE IN-FICTION** on 2026-07-31.

| | Crowns |
|---|---:|
| Tier 2+3 build | 130,000 |
| — reminted gold via Forgedeep (off-Treasury, outside exposure) | 40,000 |
| — City hoard | 90,000 |
| **Surplus after build** | **637,400** |
| Windfall re-base at authorization | +12,000 |
| Clean yield, Tier 0 | ~293,000 / quarter |

Wash toll cut from a **39% base to 10%** at Tier 3. The page's own comparison: the Tier 0 yield alone *"outperforms Shi'van's ESAMT quarterly income while paying no tax/audit exposure."* Tier 3 is built, so the real figure is higher — the page does not state the uplift and I have not computed one.

The funding hoard is fully traced: the City's 54-City-year standing treasury, rolled as a CR23 double-treasure — 27,970 gp coin + 44,770 gp goods across 49 art pieces = **72,740 gp liquid × 10 = 727,400 Cr**, plus six magic-item slots since routed to the empire.

**Currency of record** (entries 491, 613): 1 soul coin = **~100 gp = ~1,000 Crowns**, so **1 gp = 10 Crowns**. A ~5-Crown figure was player surmise and is retired. The Treasury's own opening state had to be corrected **ten-fold upward** because the original build used ~100 Cr/coin. The anchor that fixed it is Yamilet al-Sevren's **2,400-coin ≈ 2.4M-Crown** personal reserve — ~240,000 gp equivalent, wholly off the empire's books, a large slice of it committed to Operation Silken Reversion.

### The part that matters most for a bookkeeping engine

Entries **609 → 612**. The Treasury's paper trail runs in the **CODEX OPERTUM**, an item-keyed cipher whose key is physically embodied in interchangeable seal-stones on a signet ring — no codebook to steal. Final compartment roster:

- **IN:** Vesper (master set, administrator), Lirien (twin, read in first via the thin-line relay), Arik (twin, issued at authorization).
- **OUT:** **Vara Torsten** — ruled *full blindness, not sanitized awareness*. And **Yamilet** — the empire's sharpest signature-analyst, deliberately kept outside.

**The officer who runs the empire's books does not know one of its treasuries exists.** That is a structural fact about the ledger before it is a story beat, and it now sits in `canon_rulings.csv`.

Booked: `acct:hell:treasury-surplus`, `acct:hell:treasury-yield`, `acct:yamilet:soul-coin-reserve`.

---

## §2 — Three capital page-holes closed

My body-read logged these as holes. The log had them all along.

| entity | figure | entry |
|---|---:|---|
| Northern Sea Gate — full 8-phase build, 1495–1503 | **~9,320,000** | 119 |
| Seven Spires — teardown + bedrock rebuild, 18–24 months | **520,000** | 120 |
| Deep Road Network | 18,700,000 (card already carried it) | 723 |

Neither of the first two goes into a `capital_invested` cell. The 9.32M covers the whole Sea Gate programme, not the Harbor Authority card alone; the 520K is a plan, not evidenced deployment, and the card is blank. Both live in `unbooked_items.csv` with the reasoning attached.

---

## §3 — Other money the tables didn't have

- **Operation Quiet Plate — 448,000 gp.** 8 mage-variant Striders + Smoke runewords at ~56,000/unit including shimmercloak and socket integration (~2,000/suit, cut at fabrication). It carries a deliberate market posture: batch one through three Veil cutouts, then a **standing public-buyer posture** with the Northern Crown trading arm as a known continuous bulk rune buyer — signal-to-noise conversion, price-setting leverage, and a misdirection feed into the Aldric technology race. Chad fiat: **no rune synthesis, ever.** Scarcity is the design.
- **Operation Laden Table — the empire plans to BORROW 200,000–300,000 gp** from Silverymoon and Mirabar lenders, explicitly to knit northern finance into the empire's survival so the lenders cannot afford it to fail. Also NCF's counter-offensive against Nassim im'Dalat.
- **Necrotic Net — 47,400 Crowns** (~4,740 gp), Institut/Veil commission, procured through Vesh.
- **Vesh's Price** — he wants paying in Negative-Plane and demon-restraint material plus first refusal on Hell-side demon salvage, *not* coin. A payable with no gp figure by design, and it turns the Avernus corridor-ecology dice into a live economic consumer.
- **Green Vein Corridor tolls ~1,500 gp/mo** — Hammer 1496, past boundary.

---

## §4 — Rules of record that were in no table

- **Expenditure authority: 100,000 gp** (entry 453). Vara's anticipatory-seal protocol runs against the 27:1 Avernus command latency — decisions under 100,000 are dated both ways and taken without waiting for Arik.
- **Echo-Crystal Capacitor pricing** (entry 104) was **50–100× too high** on first pass and "broke 3.5e economy." Corrected: ~100 gp/charge market, about half to craft in-house — Field ~500, Standard ~2,500, Pillar ~12,000. Recorded so the retired figures can't creep back.
- **Hunding schedule pulled forward** (453/455). Kalnar's crew hit soft Maerth stratum on the Tethford reach: the hard section cuts in ~5 weeks, not 3 months. Arik's call — **hold the announced completion at the same public clock** so as not to tip the Dalelands, and bank the windfall as a survey beyond the charter line plus a fort and garrison. The casus belli ripens on the old schedule; the rock buys a wall, not speed.

---

## §5 — Corrections and confirmations

- **Bloodaxe 10,000 confirmed.** The card had been all zeros before entry 443 filled it; a later remediation corrected the Notes from ~3,000 to 10,000. Structure checks: 20 cohorts at 480, 1st at 800, plus 1,250 sappers and a 250-strong Military Intelligence Branch under Electra al-Rashid.
- **Selah Thorn is pensioned** — "Broken for Good" — and **Lirien Nightwalker is now the direct principal** of Thorn & Silver, having been NCF deputy from inception. The 10,000 @ 8% buyout loan stays on the books with a flag; no page says what happened to the debt on her pensioning.
- **Athenaeum Director is Serapha Moonfire** (Wizard 17, released from Klauth's 400-year stasis) — *not* Caelynn Hartsong the Green Regent, who had been sharing the bare title "Lady Moonfire."
- **Campaign Lane Router is stale** on the Shi'van clock: it reads ~late 1493 against the live Day 911 / 6 Mirtul 1494.

---

## §6 — Three new exposures

- **Dispater's desk** is named the Hell Treasury's sharpest discovery vector — and it has already fired once. On the S074 close sweep his attention rolled 16 and cashed as a **records pull**: the Iron Tower copied the full Storm Kingdom file from Bel's court. The off-ledger treasury sits under the one desk most likely to find it.
- **Oressa Talavera**, Sembian Council Seat 6 — the largest independent banking operation in Sembia and NCF's direct competitor, who *"reads people through transaction patterns."* The one antagonist positioned to notice what the empire's money does rather than what its people say.
- **Aldric's geographic chokepoint.** Iron Sovereignty territory sits astride the Nether Mountains corridor between Mirabar and Mithral Hall, and he has already **underbid the Adbar/Mithral Hall supply contracts at a loss** to wedge in. Forward troops 850, up from 800. He has industrially replicated Arik's coronation-gift armour as the **Steelgaze Pattern**; the empire's ceramic counter is **Emberscale** — which is what Stonefire Ceramics' hidden armour-plate line actually feeds.

---

## §7 — What the log is

789 rows. The large majority are NPC, artifact and mechanics construction — dragon breeding resolution, stat conversions, module builds, naming rulings. The economically loaded rows cluster hard in two bands: **1–150** (the April 2026 registry build) and **600–680** (the Hell-side economy). Saying so is part of the answer: there was no third anchor page hiding in the middle.

---

## §8 — Still open

- Deferred Dice (282), Faction Beliefs (57), Creation Registry (41), Shadow Events (35), Kingdoms & Factions (12), Character Sheets (10) — uncensused.
- 19 `UNRESOLVED_CONFLICT` and flagged rows in `corrections.csv`.
- The 1496-vs-Hammer-1495 clock split still needs a stated reconciliation before any month rolls.
- Canonical month CLOSED. No Notion writes. PR #1 open, draft, unmerged.

**540 canonical rows. Zero dangling references.**
