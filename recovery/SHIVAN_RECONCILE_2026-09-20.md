# Applying the Shi'van return — 2026-09-20

24 questions went out. All 24 came back, most `SOURCED`, several with more than was asked for.
This is what changed, starting with what I got wrong.

## §1 Four figures I booked this morning were wrong

Not drift. Wrong, by me, and each for the same reason.

| I booked | Reality | Why I was wrong |
|---|---|---|
| Promethean input **2,500,000 gp/month** | The 5,000 is the **Production Trust seed**; per-unit materials are **7 gp** | Read a cell, didn't read the body that defines it |
| IP portfolio **49,000–69,000 gp** | **2,116,000 gp**, binding, six assets, already booked as an asset | Took the S33 preliminary for the settled valuation |
| Amnian 17,200 **unbooked** | **In the Transaction Ledger**, Day 647, Session 29, Confidence Exact | Read the dice register, never checked the ledger |
| Transducer registry-vs-valuation **conflict** | Not a conflict: unit prices (50–400) vs **capitalised patent value** (4–6K) | Compared two different units and called it a contradiction |

The Promethean one is the third instance of a single failure in one cycle: reading property
cells instead of page bodies; inferring the Hell epoch before opening the Boot Page; and now
inferring unit economics from a cell whose meaning was defined in prose beside it. Ruled as
`engine:2026-09-20-cell-without-body`. **A number in a cell is a claim about something, and the
body says about what.**

Also withdrawn: my derived Eye of Dagaz line capacity, which multiplied 12–18 units by a flat
25,000 when the line is tiered (18,000 / 22,000 / 25,000+) and year one is 3–6 units.

## §2 The date spine held, and its verdict was upheld

Eye of Verðandi is resolved: **the day-number is real, 27 Eleasis was the error.** Play used
day-numbers throughout — character sheet, Eye of Jera page, Verðandi Collar page all agree.
Corrected in Notion.

The audit it triggered found a second instance: **Session 32's log carried the same 5-day
drift**, reading "Days 662–672 (26th Eleasis to 6th Eleint)" where the correct span is 1 Eleint
to 11 Eleint. One defect found by the tool, one found by the search the tool caused.

I re-derived every date correction the Shi'van side applied rather than accepting them:

| Day | Claimed | `harptos.py` |
|---|---|---|
| 494 (Promethean Night) | 15 Ches 1493 | **15 Ches 1493** ✓ |
| 495 (Fountain Handshake) | 16 Ches 1493 | **16 Ches 1493** ✓ |
| 499 (Section 22 petition) | 20 Ches 1493 | **20 Ches 1493** ✓ |
| 501 (hearing, won 3–2) | 22 Ches 1493 | **22 Ches 1493** ✓ |
| 548 (showroom lease) | — | **8 Mirtul 1493**, matching the Rosznar anvil's own registry date |

**One refinement.** Their shortcut, "day-of-year = campaign day − 418", is correct **only inside
1493**. Day 494 − 418 = 76, and 15 Ches 1493 is day-of-year 76. But Day 904 − 418 = 486, past the
end of a 365-day year, when 30 Tarsakh 1494 is day-of-year 121. Recorded as
`engine:2026-09-20-day418-is-1493-only` so a later reader doesn't generalise it.

**And a convention the engine needed:** time skips are canonical and were under-logged. A
session whose in-world date is a *range* is a corridor, not a contradiction. The spine must stop
treating those as defects — `engine:2026-09-20-corridors-are-not-conflicts`.

## §3 Block D came back complete — and the annual/monthly distinction is the whole game

All ten lines have volumes. None returned "no volume sourced." But every collection page states
volume **twice**, and the two figures mean different things:

- **Monthly** figures under Production Capacity are **ceilings**
- **Annual** figures in the cross-collection table are **actual output**

The projections prove it. Gentlemen's Revolution: 30 × 4,250 = 127,500, inside its stated
120,000–200,000; its *capacity* of 132–216 units would give 561,000–918,000. Founding: ~6 ×
15,000 = 90,000, matching its own stated figure exactly. **Annual for revenue, monthly for
headroom.** Every line runs at 25–50% of ceiling, and the constraint is almost always Shi'van's
own bench hours. Ruled as `engine:2026-09-20-annual-is-actual`.

**Drift corrected in the same pass:** Evening's Edge retails at **25,000, not 250,000** — the
250,000 was a Baldur's Gate *equipment appraisal* quoted in the row's own Notes. The Suit
Collection's 350 is the Evening Edition *minimum* of five lines, weighted average ~285. Daylight's
1,500 is a *midpoint* of 1,200–1,800.

## §4 The largest unreconciled number in the campaign

The seven fashion and jewellery lines project **805,000–1,310,000 gp/yr** at midpoint.

The books say the Institut runs **28,000 gp/month** steady-state — protection 15,000 + high
fashion 6,000 + specialty 4,000 + licensing 1,500. Four of the seven lines are Institut-produced
and belong inside that **6,000/month = 72,000/yr**. Their own pages project **535,000–880,000**.
A seven- to twelve-fold gap inside one entity's own books. The three jewellery lines sit on the
B&D side, where the ledger books 3,300 gp/month = 39,600/yr against 270,000–430,000 of projection.

Two readings, and the engine cannot pick between them by itself:
- **(a)** The collection pages are launch-era catalogue copy describing capacity; the ledger is
  realised. Then Block D was never a gap and the ledger stands.
- **(b)** The ledger under-books by an order of magnitude, the Institut is really north of 70,000
  gp/month, and **every monthly business roll since Session 31 has run against the wrong base.**

**Pending a ruling the engine carries the ledger** and types the collection figures as capacity
(`engine:2026-09-20-ledger-over-catalogue`). The basis is that all the collection pages carry
"Status at Day 592" footers, while the Product Catalog (Day ~737, the most recent financial
document) ties the protection line out to its 15,000/mo ledger figure *exactly* — it was written
to reconcile and it does. But it stops before the fashion collections, which is precisely where
the gap sits.

## §5 A fabricated number that survived its own correction

Deferred Dice row `373e8214-84b0-81c1` carried a Pemberton-Chase valuation of "385,000 gp total."
**Invented by a prior assistant.** Caught by Chad at the time. The correction was applied to
three other pages — and not to that page body, where it survived and was re-quoted back at him
during this audit.

Kept in `corrections.csv` as a standing caution rather than just deleted. **A corrected error
that is not corrected everywhere is a live error with a delay fuse.** The binding total is
2,116,000.

## §6 The three Arik-bound pieces are not liabilities

All three are **Concept**, Session Log empty, Actual Completion empty, no in-play commitment
anywhere. Design documents, not obligations. Retyped from `HELD` to `ASPIRATIONAL` — they stay on
the spine so the dates aren't lost, but the engine does not carry them as scheduled liabilities.

The Lambda Suit's 37,000 gp material cost is **retired by the row's own Notes** — the
Ghaunadar-shard component is non-substitutable. Insurance valuation 5,000,000+ gp.

The Mantle's placement inside the Reserved Interval looks **inherited**, not chosen: both its
start (Hammer–Alturiak 1495) and target (Eleasis 1495) sit inside the suspended window, bracketing
a six-month craft entirely within it. A deliberate placement wouldn't do that.

## §7 New to the tables

**Accounts (+5).** ESAMT IP portfolio 2,116,000 · borrowing capacity 6,900,000 · outstanding
454,116 · liquid ~795,000 · Golden Griffin GG-1493-0315-SB, 440 gp at 3% monthly compounded since
Day 494, **never drawn, ~646–665 gp at Day 905**.

**Contracts (+2).** Rosznar 60/40 on net profits, territorial to Waterdeep city limits. Husteem
60/40 on the noble channel only.

**Exposures (+3).**
- **Article V** commits 2,000 units/month by Midsummer. Actual output is 376 — **19%**. Marcus
  Rosznar has held a documented lever since the founding night. Note the cause: *not* the Rosznar
  exclusive, which is territorial only and explicitly leaves international rights open. Export was
  never blocked, only never pursued — three noble houses registered interest on Day 494 and none
  has been called on in 411 days.
- **Fuel monopoly.** Patents WD-494-005 (sealed) and WD-494-006 give a razor-and-blades monopoly
  that has existed on paper since Day 494 and has never been priced or booked.
- **Gerard**, the Golden Griffin driver, has known her home address for 411 days and was never
  vetted.

**Resolved:** Cassalanter paid 240 gp (client supplied the crystals — no liability). Blackwatch
double-count confirmed and zeroed. Phantom's Embrace 200,000 is real but imputed, zero cash —
materials "gathered through friendship rather than commerce." Thorfinn delivered. Gralhund
superseded and closed. Eight duplicate dice pairs, not seven.

All 20 tables parse uniform. `harptos.py` 36/36. `runway.py audit` clean but for the one known
upstream wording flag.

## §8 Still open

**Needs a ruling:** the Institut revenue gap (§4) · Yggdrasil 25,000 vs 185,000 · Prosthetics
Type once pricing is decided · Summer Crown's two conflicting blocker lists · Navigator's Case
sale status vs booked greenhouse revenue · Pemberton-Chase fee 750 vs 400 booked, possibly
double-counted against the 33/mo revaluation · Gralhund council Day 690 vs 717 · Kenafin handler:
consumed by the Korr pipeline or still owed · Mantle rebase · fuel cartridge price · Golden
Griffin tab disposition · Presentation Pattern channel.

**Genuinely unrecorded:** Rosznar Floating Anvil cost (Rosznar-side, never written down) ·
Session 16 figures · what the 80,000 gp at Day 814 bought · Lamp Post unit price to the city.

**Still mine:** Kingdoms & Factions (12 rows) · Development Ledger · NPC Personality Axis.
