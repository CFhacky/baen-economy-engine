# The GM-layer census — 2026-09-20

## §0 Why this pass existed

Six databases were carried as UNCENSUSED: Deferred Dice (282), Faction Beliefs (57),
Creation Registry (41), Shadow Events (35), Kingdoms & Factions (12), Character Sheets (10).
437 rows the engine had never opened. This pass opened them.

It found nine, not six. The GM-Only Layer hub lists three databases that appear on no prior
list at all: **World-Move Register**, **Development Ledger — Children of the Line**, and
**NPC Personality Axis State — Arik Arc**. A census that only counts what a previous census
listed is not a census. All three are now in `source_collections.csv`.

One note on method, against myself: I spent four tool calls hunting for data-source IDs
through search and a 110,000-character index page. `source_collections.csv` — a file in this
repository — already held every one of them, including the Kingdoms & Factions ID the Notion
index omits. The engine knew. I did not read the engine first.

## §1 The Creation Registry is a product ledger, and it was missing

The single material finding. 41 rows with `Market Value`, `Material Cost`, `Sale Status`,
phase progress, client and completion stamp. It is a product, IP and commission ledger that
the economy engine has never carried. Now `data/canonical/products.csv`.

| | |
|---|---|
| Market value booked (SOURCE + PROJECTION) | **1,044,400 gp** |
| Material cost booked | **537,825 gp** |
| Market-value page holes | **8 rows** |
| Live product lines with no unit volume | **9** |

**Zero is not a price.** The registry uses `0` and empty interchangeably for two incompatible
things. Phantom's Embrace is 0 because it will never be sold — a deliberate nil standing
against 200,000 gp of consumed material. The Promethean Device is 0 because nobody has priced
a mass-market patent product that is ramping to 500 units a month. Summing that column is
wrong in both directions. `products.csv` carries `market_value_state` beside every figure:
SOURCE, PROJECTION, NOT_PRICED, PAGE_HOLE, TOMBSTONE, UNKNOWN. Ruled as
`engine:2026-09-20-zero-is-not-a-price`.

The largest unpriced number in the campaign now has a row: the Promethean Device at 5,000 gp
of materials per unit, ramping to 500 units per month, is **2,500,000 gp/month of input**
against a market value of zero.

### Three pieces built for Arik, on Arik's calendar

Shi'van's registry contains cross-lane obligations nobody was tracking as such:

- **Mantle of Many Roads (Nine Anchors)** — Eleasis 1495 DR, 5,000 gp materials.
  **This lands inside the Reserved Interval**, at +213 days between the Hammer 1495 shelf and
  the Ches 1496 crossing. A Shi'van-side obligation falling in Arik's suspended year.
- **Frostvein** — late 1497 DR, 1,800 gp. Past the Crossing, before Jörmun's 1498 position.
- **Lambda Slime Suit (Apex Substrate)** — three dated milestones on one row: shard acquisition
  Kythorn 1499, bonding Hammer 1502, Khem-Ruur deployment Ches 1502. 37,000 gp materials.
  The furthest-forward dated item the engine carries.

## §2 The date primitive earned itself

Two registry rows state a day-number and a Harptos date **in the same cell**. Both are
independent tests of the Day 904 = 30 Tarsakh 1494 epoch, written by pages that had nothing
to do with setting it.

- **Seren's Collar** — "Day 612 / 12th of Flamerule, 1493 DR". `harptos.py` returns
  12 Flamerule 1493 for Day 612. **Exact.** The SHIVAN epoch is now sourced *and*
  independently corroborated. Ruled as `engine:2026-09-20-shivan-epoch-corroborated`.
- **Eye of Verðandi** — "27th Eleasis 1493 (Day 663)". Day 663 is **2 Eleint 1493**.
  27 Eleasis 1493 is **Day 658**. The two halves of one cell disagree by five days.

Because the epoch holds under the first test, the error in the second is inside the row, not
in the arithmetic. Logged `cor:prd-verdandi-date`, UNRESOLVED_CONFLICT — a GM ruling on which
half is real, not something the engine should quietly pick.

This is the first defect the date spine found on its own that no human had noticed. It is
also the reason the spine exists.

## §3 Deferred Dice — 282 rows, and what they actually are

Not an economic table. Nine rows out of 282 carry money. But the structural read matters:

| Status | Rows |
|---|---|
| Resolved | 118 |
| **Waiting** | **112** |
| **Rolled, not resolved** | **41** |
| **No status at all** | **11** |

**Five dice are rolled and were never delivered.** The outcome exists; no session ever landed
it. Kenafin's replacement handler contacting Yulara; Dunwell resolving the Rhys Callan
investigation; Dunwell connecting that investigation to Shi'van; Thorfinn's archival results
from the Mirabar Hall of Grafts; the Gralhund family meeting where Violet takes the chair.
RECORDED_NOT_APPLIED.

**Eleven rows carry no Status, no Trigger Condition and no Session.** All are recent Hell-arc
and Menzoberranzan entries — STORMFALL, the Tiamat consort-ring scrying, Pale Knell, Ash Veil,
Adaptive Wings, Frightful Presence, Iliphar Mizzrym's report, Szerith Phaeran's observation
window, the Anauroch cult queries, Bahamut outreach, the peer chromatic arrival. Three of them
carry a time window buried in the Subject prose instead of in a field: *4–5 tendays*,
*10–40 Hell-day window from session close*, *~half-year*. Those are schedulable now that the
lanes exist; they are not scheduled.

**Seven near-duplicate pairs sit in the Rolled bucket alone** — the same die recorded twice,
which risks being resolved twice.

Money found: the Pemberton-Chase IP valuation (**49,000–69,000 gp**, itemised), the Amnian
first delivery (**net 17,200 gp** after a 200 gp Cowled Wizards assessment), Barker Phase One
(**10,000–16,000 gp**), and one armed Arik-lane exposure — **Vesh's Price**, a standing
demon-material supply and Tier 2 clearing-house formalization with no price, no term and no
recorded counterparty terms.

## §4 What the other five are, so nobody reads them again expecting money

- **Shadow Events** (35) — an intelligence-state register: Event / True Status / Known By /
  Believed By / Resolution Trigger. No money fields. Structurally it is the same shape as
  `exposures.csv` and is the right upstream source if exposure modelling is extended.
- **Faction Beliefs** (57) — political intent. No money fields. Operational commitments appear
  in prose only, so it can seed employment but carries no figures.
- **Character Sheets** (10) — GURPS/D&D stat state. No money. Worth one note: its
  `Campaign Day` column is another day-number surface and belongs to the SHIVAN lane.
- **World-Move Register** — **one row**, not 35. S074, Arik, ~Day 5 Hammer 1495, four moves.
  The structure exists; the practice did not survive past a single session.
- **Kingdoms & Factions** (12) — still unread. The only database on the original list not
  opened this sitting. Named here rather than quietly dropped.

## §5 What changed in the tables

| File | Change |
|---|---|
| `products.csv` | **NEW.** 41 rows, the whole Creation Registry |
| `events.csv` | +6 — three Arik-bound deliveries, two Lambda milestones, one epoch anchor |
| `unbooked_items.csv` | +5 — IP valuation, Amnian net, Barker Phase One, Vesh's Price, Dagaz capacity |
| `corrections.csv` | +8 — the Verðandi date conflict, the zero-price holes, three dice-register hygiene findings |
| `canon_rulings.csv` | +2 |
| `source_collections.csv` | 6 statuses updated, 5 collections added |

All 20 canonical tables parse with uniform column counts. `harptos.py` 36/36.
`runway.py audit` is clean but for the one known upstream wording flag — the same
"Day 7 Hammer 1495" phrasing annotated on the Notion boot page today.

## §6 Still open, and whose it is

**Needs a GM ruling, not an engine guess:**
- Eye of Verðandi: Day 663 or 27 Eleasis. One of them is wrong.
- Baen'und Prosthetics is typed `Product Line` and flagged `Never For Sale`. Both cannot hold.
- The Blackwatch Lane Showroom Lease row announces its own migration to the Locations DB and
  still holds a 1,500 gp cost here. Possible double-count.
- Eleven dice with no status: are they armed or are they notes?

**Engine work, not yet done:**
- Kingdoms & Factions (12 rows) unread.
- Development Ledger and NPC Personality Axis unread.
- The three time windows buried in dice Subject prose are not on the spine.
- Nine live product lines have prices and no volumes, so no line revenue can be derived.
