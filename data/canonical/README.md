# Canonical economic actor tables

Human-diffable authority for the economic actor layer.
SQLite under data/runtime is a build product, not the Git authority.

First slices: Northern Crown Financial and Institut Baen'und.
Campaign boundary: Day 7 Hammer 1495 DR.

## Tables

| file | rows | what it holds |
|---|---:|---|
| actors.csv | 38 | people, institutions, households, workforce pools, programmes |
| relationships.csv | 46 | parent/child as written on the cards, with conflict flags |
| facilities.csv | 90 | one row per Business Registry entity, registry properties only |
| employment.csv | 90 | one row per facility; `consolidation` marks rollups and non-payrolls |
| programmes.csv | 15 | named programmes, product lines, channels and commissions |
| contracts.csv | 6 | receivables and payables, generic columns, both clocks |
| ownership.csv | 16 | equity, control claims, household holdings |
| accounts.csv | 13 | account shells; most balances UNMODELED |
| loans.csv | 7 | NCF facilities plus the unresolved portfolio remainder |
| transactions.csv | 49 | the full Transaction Ledger; every row Shi'van-clock Day 234-814 |
| canon_rulings.csv | 10 | Canon Change Log entries that bind the engine, incl. AHEAD_OF_BOUNDARY flags |
| source_collections.csv | 21 | every known Notion database with row count and census status |

`wage_rate` stays blank unless a page states a wage. Empty cells stay empty; unknown is not zero.
Receipts for the last two ingests: `recovery/REGISTRY_PROPERTY_INGEST_2026-09-19.md`, `recovery/PROGRAMMES_EMPLOYMENT_INGEST_2026-09-19.md`.

The 2026-09-17 census covered 10 of 21 databases (1,381 of 3,191 live rows). See `source_collections.csv` and `recovery/FOUR_LANE_INGEST_2026-09-19.md`.
