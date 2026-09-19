# Canonical economic actor tables

Human-diffable authority for the economic actor layer.
SQLite under data/runtime is a build product, not the Git authority.

First slices: Northern Crown Financial and Institut Baen'und.
Campaign boundary: the **Departure Shelf**, Day 7 Hammer 1495 DR.
Live play sits past **the Crossing** (1496 DR) with a suspended interval between.

## Tables

| file | rows | what it holds |
|---|---:|---|
| timeline.csv | 21 | the two stamps, the Reserved Interval, its carry rules and landing zone |
| actors.csv | 45 | people, institutions, households, workforce pools, programmes |
| relationships.csv | 46 | parent/child as written on the cards, with conflict flags |
| facilities.csv | 90 | one row per Business Registry entity |
| employment.csv | 90 | one row per facility; `consolidation` marks rollups and non-payrolls |
| programmes.csv | 16 | named programmes, product lines, channels and commissions |
| production_rates.csv | 3 | unit rates, sale vs keep, and the monthly arithmetic that follows |
| contracts.csv | 6 | receivables and payables, generic columns, both clocks |
| ownership.csv | 16 | equity, control claims, household holdings |
| accounts.csv | 19 | the liquidity position, the Klauth pool, the Hell Treasury (Crowns) |
| loans.csv | 11 | NCF facilities and named loans; `consolidation` guards the 2.3M aggregate |
| transactions.csv | 49 | the full Transaction Ledger; every row Shi'van-clock Day 234-814 |
| canon_rulings.csv | 34 | Canon Change Log entries and engine rulings that bind the tables |
| corrections.csv | 37 | every registry-cell-vs-page-body discrepancy, applied or not |
| unbooked_items.csv | 35 | capital, assets, payables and receivables named on pages and in no money table |
| exposures.csv | 29 | the leverage layer: skimming, blackmail, reporting vectors, capability gaps |
| source_collections.csv | 21 | every known Notion database with row count and census status |

## Rules the tables keep

- **Page bodies before property cells.** All 90 registry bodies have been read
  (`recovery/bodyread/FINDINGS.json`). Property cells are the stale side often
  enough that they are never the sole basis for a money row.
- **Two clocks, and one reserved interval.** Arik's economy is stamped at the
  **Departure Shelf**, Day 7 Hammer 1495. Shi'van is Day-numbered 1493-94
  (currently Day 911 / 6 Mirtul 1494). Jorumn runs ~Uktar 1498. Never add one
  lane's fee onto another's month.
- **The Reserved Interval is SUSPENDED.** Twelve months of surface time sit
  between the Departure Shelf and **the Crossing** (1496 DR, month unpinned),
  left unwritten on purpose. Nothing in it advances by elapsed time - no
  profit, no clock, no construction, no neglect. Only played sessions move
  state. A 1496 stamp is a post-Crossing reading, not stale data; a 1498 stamp
  is the Jorumn lane. See `timeline.csv`.
- **`wage_rate` stays blank unless a page states a wage.** Empty cells stay
  empty; unknown is not zero.
- **A number is applied only when its paired numbers come with it.** Where a
  correction would fabricate margin (see `corr:silversheen:revenue`), it is
  recorded in `corrections.csv` and the cell is left internally consistent at
  its own stamp. Recording is not punting; back-solving is simulation.
- **`consolidation` columns exist so nothing is summed twice** - branch payrolls
  into parents, named loans into the 2.3M aggregate, Castle Operations against
  Skyreach.
- **Unconfirmed entities are not booked.** Gold Lending House, Lobster King and
  Waterdeep Information Brokerage carry phantom figures from a Campaign Manager
  artifact; they stay at zero.

Receipts: `recovery/REGISTRY_PROPERTY_INGEST_2026-09-19.md`,
`recovery/PROGRAMMES_EMPLOYMENT_INGEST_2026-09-19.md`,
`recovery/FOUR_LANE_INGEST_2026-09-19.md`,
`recovery/RATE_RULINGS_2026-09-19.md`,
`recovery/BODYREAD_2026-09-19.md`,
`recovery/LOGS_INGEST_2026-09-19.md`,
`recovery/CHANGELOG_FULL_2026-09-19.md`.

Census: the Business Registry (all 90 page bodies), the Canon Change Log (all
789 rows) and the GM Consequence Ledger (272) are fully read. Six databases
remain uncensused - see `source_collections.csv`.
