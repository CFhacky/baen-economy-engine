# HANDOFF TO THE SHI'VAN PROJECT — 2026-09-20
## From: baen-economy-engine bookkeeping. Purpose: answer 24 questions, return one block.

You are being asked to **resolve open bookkeeping questions**, not to play, not to advance any
clock, and not to write anything to Notion. Read the live pages, answer what the sources say,
and stop.

### Rules for this task

1. **Read the live Notion pages. Do not answer any number from model memory.** Every figure
   below came out of a live page this morning; if your page now says something different, say so.
2. **"Unknown" and "the page does not say" are correct answers.** Do not invent gold, volumes,
   dates or prices. A page hole recorded as a page hole is worth more than a plausible guess.
3. **No Notion writes.** No new rows, no edits, no status changes. Especially not the Canon
   Change Log or Session Logs — those are the historical record.
4. **Do not advance campaign time.** No session numbering, no Phase 0, no world moves.
5. If answering something requires a GM decision rather than a lookup, mark it `NEEDS_CHAD` and
   say what the decision is between. Don't decide it for him.

### Source IDs you'll need

| Thing | Data source |
|---|---|
| Shi'van Creation Registry | `collection://23327d85-0663-47e8-8032-f436b31a28d8` |
| Deferred Dice | `collection://da0db9c0-9fb7-4ddf-aff5-f1ac55979873` |
| Transaction Ledger | `collection://ae367fe3-d5fd-47db-b4d3-eafb13b9d081` |
| Business Registry | `collection://3c5f887a-4219-4ae6-a18a-82cf2d1841db` |
| Locations | `collection://4b453810-16af-43eb-86ff-927da765a17f` |

SQL over a data source returns **property cells only**. Page bodies need a `fetch`. Several of
these answers are in bodies, not cells.

---

## BLOCK A — The date conflict (answer this one first)

The Shi'van lane epoch is `Day 904 = 30 Tarsakh 1494 DR`. It is confirmed: **Seren's Collar**
states "Day 612 / 12th of Flamerule, 1493 DR" and Day 612 resolves to 12 Flamerule 1493 exactly.

**Eye of Verðandi (Original)** states its completion as **"27th Eleasis 1493 (Day 663)"**.
Those two do not agree. Under the confirmed epoch:
- Day 663 = **2 Eleint 1493 DR**
- 27 Eleasis 1493 DR = **Day 658**

Five days apart, inside one cell. The epoch holds, so the error is inside that row.

**A1.** Which half is real — the day-number (Day 663 / 2 Eleint) or the calendar date
(27 Eleasis / Day 658)? Check the Eye of Verðandi page body and any session log or prose scene
covering that completion. If both appear in play, say which one play actually used.

---

## BLOCK B — Three registry rows that contradict themselves

**B2.** **Baen'und Prosthetics** is typed `Product Line` and flagged `Never For Sale` in the same
row. Which field is wrong? (A deliberately non-commercial prosthetics programme is plausible,
which would make Type the error — but confirm, don't assume.)

**B3.** **"⚠️ MIGRATED — Blackwatch Lane Showroom Lease"** announces its own migration to the
Locations DB in its title and still holds a **1,500 gp material cost** in the Creation Registry.
Does the Locations DB row also carry that 1,500? If yes it is double-counted and the registry
copy should be zeroed. Check both.

**B4.** **Yggdrasil Seed Orb** is Complete, a live Product Line, market value 25,000 gp, and its
**Material Cost cell is empty**. What is it?

---

## BLOCK C — Eight products with no price

These all carry `Market Value` empty or zero while being real products. Zero is not a price; the
engine treats these as page holes. For each: **what is the unit market value, or is it genuinely
not priced yet?**

**C5. Promethean Device (Standard Model)** — the big one. Status Construction, phase 3/4, market
"Mass market + noble market", materials **5,000 gp/unit**, ramp stated as **"50 units by 25th
Ches, 500/month by Tarsakh"** with no year. At 500 units/month that is 2,500,000 gp/month of
*input* against a market value of zero. Need: (a) unit sale price, (b) which year that ramp is in,
(c) whether the 50-unit milestone has been hit in play.

**C6. Promethean Lamp Post** — Design stage, every numeric field empty. Price and materials.

**C7. Rosznar Floating Anvil — Production Line Upgrade** — Complete, dated 8th Mirtul 1493 DR,
partner Rosznar Manufacturing. A completed capex event with **no cost recorded anywhere**. What
did the upgrade cost and who paid?

**C8. Violet's Ward-Flow Transducer** — registry blank, but the **Pemberton-Chase IP valuation
prices the transducer at 4,000–6,000 gp**. Adopt the valuation figure, or is the registry
tracking something different?

**C9. Institut Protection Garments** — Construction, no numbers. Cross-references the
"Veil Procurement Timeline — Institut Protective Fashion & Evening's Edge" page
(`338e8214-84b0-81dd-a547-c9cc52c1bb23`) — that body may hold the figures.

**C10. The Navigator's Case (Cigarillo Line)** — Construction, no numbers.

**C11. Silk Road Collection (Eastern Micro-Coil Goldwork)** — Concept. Ties to Operation Lacquer
Road / Kara-Tur sourcing. Any costing yet?

**C12. Baen'und Summer Crown (Noble Pattern Hall Ventilator)** — Concept, blocked on a Ghondian
engineering partnership that does not exist. Confirm it is blocked and unpriced rather than
simply unfilled. Its own spec page is `346e8214-84b0-8127-849d-d8e6dbe95752`.

---

## BLOCK D — The largest single gap: ten live lines with a price and no volume

Ten product lines are `Complete` and in active production with a stated unit market value and
**no unit volume anywhere**. Without volume, none of them can produce a revenue line, so the
Institut's actual income is unrepresentable.

| Line | Unit mv | Unit mc |
|---|---|---|
| Evening's Edge (Classic) | 250,000 | 800 |
| Daedalus Heart (Item Class / Patent) | 40,000 | 15,000 |
| Yggdrasil Seed Orb | 25,000 | (empty) |
| The Founding Collection | 15,000 | 3,500 |
| The Scepter & Shadow Collection | 12,000 | 3,000 |
| The Verdant Court Collection | 8,000 | 1,500 |
| The Gentlemen's Revolution Collection | 4,250 | 700 |
| The Midnight Collection (Vampire Trend) | 2,500 | 300 |
| The Daylight Collection | 1,500 | 275 |
| The Baen'und Suit Collection (5-Line) | 350 | 50 |

**D1.** For each line, **units per month or per year**, and whether that is a sourced figure or a
GM estimate. Several rows say "capacity-limited" or "within scarcity limits" — if a cap exists,
give the cap. If no source states a volume for a line, say `NO VOLUME SOURCED` for that line
rather than estimating.

**D2.** Are any of these ten lines **dormant or discontinued**? The Midnight Collection is
described as peaking during the Silverymoon anxiety trend — has that demand collapsed?

**D3. Eye of Dagaz** is Concept at phase 0/5, priced 25,000 gp, with a stated cadence of
"12–18 selected recipients per year" and first units due Q4 1493. **Has a single unit shipped?**
If the line is live, that is 300,000–450,000 gp/yr and it is booked nowhere.

---

## BLOCK E — Realised money that never reached the ledger

**E1.** **Amnian first delivery (Marcel's international debut), ~Day 647.** Deferred Dice records
d20=3 COMPLICATION: 12 of 14 pieces accepted, Tessa's 2 returned as "competent reproductions",
Cowled Wizards took a 200 gp assessment fee, **net 17,200 gp**. Does that 17,200 appear in the
Transaction Ledger or any entity's book? If not, whose book should it land in?

**E2.** **Pemberton-Chase IP valuation, ~Day 676–680.** d20=12 GOOD, total **49,000–69,000 gp**:
ward-threading 6–9K/yr, six-node limiter 14–18K, eight-node tunable 22–28K, transducer 4–6K,
Dagaz methodology 3–5K. Three recommendations attached — IP licensing separation, personal trust,
quarterly council presentation. **Were any of the three actioned in play?** And should the
portfolio be booked as an asset, or is it an appraisal only?

**E3.** **Barker road assessment, ~Day 620–625.** d6=5 excellent, 12-page survey, referrals to
**Treasury Quarries Ltd** and **Baen Construction**, Phase One costed **10,000–16,000 gp**.
Neither referral appears in either entity's book. Did the work proceed, and on whose account?

**E4.** **Triune Chainmail** was "originally a Cassalanter commission; retained". Materials
5,000 gp. **Was the Cassalanter commission ever paid for?** If money changed hands and the piece
was kept, there is a liability.

**E5.** **Phantom's Embrace** consumed **200,000 gp of materials** and is valued at zero as a
personal piece. Confirm the 200,000 is real material spend and not a valuation typo — it is the
single largest materials figure in the registry.

---

## BLOCK F — Five dice rolled and never delivered

These five have a Status of `Rolled` — the outcome exists — and an **empty Session Resolved**.
No session ever landed them. For each: **has it since been delivered in play, is it still
pending, or is it dead?**

- **F1.** Kenafin replacement handler makes contact with Yulara
- **F2.** Dunwell resolves the Rhys Callan investigation
- **F3.** Dunwell connects the Rhys investigation to Shi'van
- **F4.** Thorfinn archival search results from Mirabar Hall of Grafts
- **F5.** Gralhund family meeting — Violet takes the chair

Also: the Rolled bucket contains **seven near-duplicate pairs** (Firth thumbprint pattern-match /
pattern-read; three Second Margaster probe rows; two Masked Lord sender escalation rows; two
Stormwind-Pharyn harmonisation rows; two Vesper survival rows; two Feast of the Moon guest-list
rows). **F6.** Confirm these are duplicates and say which row of each pair is the live one, so
the same die is not resolved twice.

---

## BLOCK G — Three pieces Shi'van is building for Arik

The Creation Registry carries three items whose client is "Arik Baen (brother)", dated on Arik's
calendar, not Shi'van's:

- **Mantle of Many Roads (Nine Anchors)** — Eleasis 1495 DR, 5,000 gp materials
- **Frostvein** — late 1497 DR, 1,800 gp materials
- **Lambda Slime Suit (Apex Substrate)** — shard acquisition Kythorn 1499, bonding Hammer 1502,
  Khem-Ruur deployment Ches 1502, 37,000 gp materials

**G1.** Are these **committed obligations** or aspirational design docs? It changes whether the
engine carries them as scheduled liabilities.

**G2.** The Mantle lands **Eleasis 1495**, which falls inside Arik's suspended Reserved Interval
(between the Hammer 1495 snapshot and the Ches 1496 Black Sluice crossing). Is that date chosen
deliberately, or inherited from an older timeline before the interval was set?

**G3.** None of the three has a market value, only a material cost. Is that deliberate because
they are gifts, or unfilled?

---

## RETURN FORMAT — paste this back exactly

One line per question. Keep the IDs. Anything you cannot answer, mark `UNKNOWN` — that is a real
answer and I will record it as a page hole.

```
A1  | <answer> | SRC: <page or db + where> | <SOURCED|RULED|NEEDS_CHAD|UNKNOWN>
B2  | ...
...
D1  | Evening's Edge: <n>/yr ; Daedalus Heart: <n>/yr ; ... (one per line above)
...
G3  | ...
```

`SOURCED` = a live page says it. `RULED` = Chad decided it in this session. `NEEDS_CHAD` = it is a
decision, not a lookup — say what the options are. `UNKNOWN` = nothing says.

If you find that a figure quoted above **no longer matches the live page**, flag it as
`DRIFT: <old> -> <new>` on that line. That matters as much as the answer.

---

## Not yours — do not chase these

Four open items belong to Arik's arc and go to the Arik project, not here: the eleven
status-less Deferred Dice rows (STORMFALL, Tiamat consort-ring, Pale Knell, Ash Veil, Adaptive
Wings, Frightful Presence, plus the Menzoberranzan entries), Vesh's Price / the Tier 2
clearing-house, the ARIK_HELL epoch question, and the Kingdoms & Factions census.
