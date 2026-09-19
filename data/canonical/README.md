# Canonical economic actor tables

Human-diffable authority for the economic actor layer.
SQLite under data/runtime is a build product, not the Git authority.

First slices: Northern Crown Financial and Institut Baen'und.
Campaign boundary: Day 7 Hammer 1495 DR.

## Tables

| file | rows | what it holds |
|---|---:|---|
| actors.csv | 35 | people, institutions, households, workforce pools, programmes |
| relationships.csv | 46 | parent/child as written on the cards, with conflict flags |
| facilities.csv | 90 | one row per Business Registry entity, registry properties only |
| employment.csv | 90 | one row per facility; `consolidation` marks rollups and non-payrolls |
| programmes.csv | 13 | named programmes, product lines, channels and commissions |
| contracts.csv | 6 | receivables and payables, generic columns, both clocks |
| ownership.csv | 14 | equity, control claims, household holdings |
| accounts.csv | 11 | account shells; most balances UNMODELED |
| loans.csv | 3 | NCF facilities plus the unresolved portfolio remainder |

`wage_rate` stays blank unless a page states a wage. Empty cells stay empty; unknown is not zero.
Receipts for the last two ingests: `recovery/REGISTRY_PROPERTY_INGEST_2026-09-19.md`, `recovery/PROGRAMMES_EMPLOYMENT_INGEST_2026-09-19.md`.
