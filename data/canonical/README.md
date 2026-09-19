# Canonical economic actor tables

Human-diffable authority for the economic actor layer.
SQLite under data/runtime is a build product, not the Git authority.

First slices: Northern Crown Financial and Institut Baen'und.
Campaign boundary: Day 7 Hammer 1495 DR.

## Tables

| file | rows | what it holds |
|---|---:|---|
| actors.csv | 42 | people, institutions, households, workforce pools, programmes |
| relationships.csv | 46 | parent/child as written on the cards, with conflict flags |
| facilities.csv | 90 | one row per Business Registry entity |
| employment.csv | 90 | one row per facility; `consolidation` marks rollups and non-payrolls |
| programmes.csv | 16 | named programmes, product lines, channels and commissions |
| production_rates.csv | 3 | unit rates, sale vs keep, and the monthly arithmetic that follows |
| contracts.csv | 6 | receivables and payables, generic columns, both clocks |
| ownership.csv | 16 | equity, control claims, household holdings |
| accounts.csv | 13 | account shells; most balances UNMODELED |
| loans.csv | 11 | NCF facilities and named loans; `consolidation` guards the 2.3M aggregate |
| transactions.csv | 49 | the full Transaction Ledger; every row Shi'van-clock Day 234-814 |
| canon_rulings.csv | 20 | Canon Change Log entries and engine rulings that bind the tables |
| corrections.csv | 19 | every registry-cell-vs-page-body discrepancy, applied or not |
| unbooked_items.csv | 18 | capital, assets, payables and receivables named on pages and in no money table |
| exposures.csv | 25 | the leverage layer: skimming, blackmail, reporting vectors, capability gaps |
| source_collections.csv | 21 | every known Notion database with row count and census status |

## Rules the tables keep

- **Page bodies before property cells.** All 90 registry bodies have been read
  (`recovery/bodyread/FINDINGS.json`). Property cells are the stale side often
  enough that they are never the sole basis for a money row.
- **Two clocks.** Arik = Day 7 Hammer 1495. Shi'van = Day-numbered 1493-94.
  Never add a Shi'van Day-630 fee onto Arik's month.
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
`recovery/BODYREAD_2026-09-19.md`.

The 2026-09-17 census covered 10 of 21 databases (1,381 of 3,191 live rows).
See `source_collections.csv`.
