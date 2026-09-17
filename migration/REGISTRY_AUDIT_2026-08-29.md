# Business Registry Audit — 2026-08-29

## Scope and safety

The live Baen Empire Business Registry was queried in full through its Notion data
source (`collection://3c5f887a-4219-4ae6-a18a-82cf2d1841db`). All 90 query-visible
rows were inspected. The database is
[`8ba47f60efe14c839fe14561543e07d1`](https://app.notion.com/p/8ba47f60efe14c839fe14561543e07d1).

This was a read-only audit. No Notion page, property, schema, comment, or relation
was created, updated, moved, archived, or deleted.

## Raw source totals

| Measure | Raw column sum |
|---|---:|
| Rows | 90 |
| Monthly revenue | 1,194,405 gp |
| Monthly cost | 612,259 gp |
| Arithmetic revenue less cost | 582,146 gp |
| Capital invested | 31,086,700 gp |
| Employees | 14,954 |

These figures are diagnostics only. They are **not** a consolidated income
statement, balance sheet, payroll roll, or campaign opening state.

## Status distribution

| Status | Rows | Raw revenue | Raw cost |
|---|---:|---:|---:|
| Operational | 59 | 1,023,703 | 337,020 |
| Under Construction | 12 | 1,969 | 172,639 |
| Scaling | 9 | 168,733 | 101,400 |
| Planning | 6 | 0 | 1,200 |
| Unconfirmed | 3 | 0 | 0 |
| R&D Phase | 1 | 0 | 0 |

## Field completeness

“Present” means the source property contains a value; it does not mean the value
is current, canonical, or suitable for consolidation.

| Property | Present | Missing |
|---|---:|---:|
| Monthly Revenue | 79 | 11 |
| Monthly Cost | 77 | 13 |
| Capital Invested | 75 | 15 |
| Employees | 80 | 10 |
| Profit Margin | 64 | 26 |
| ROI Pct | 62 | 28 |
| Date Operational text | 81 | 9 |
| Last Updated text | 85 | 5 |
| Notion date property | 5 | 85 |
| Last Attended | 46 | 44 |
| Neglect Status | 68 | 22 |
| Source File | 17 | 73 |
| Region | 10 | 80 |
| Known Assets | 7 | 83 |
| Current Activity | 7 | 83 |

## Source-shape distribution

| Sector | Rows | Sector | Rows |
|---|---:|---|---:|
| Infrastructure | 18 | Manufacturing | 13 |
| Banking | 10 | Real Estate | 10 |
| Mining/Quarrying | 7 | Aquaculture | 5 |
| Military | 5 | Trade | 5 |
| Construction | 4 | Education | 4 |
| Intelligence | 3 | Agriculture | 2 |
| Hospitality | 2 | R&D | 2 |

| City / scope | Rows | City / scope | Rows |
|---|---:|---|---:|
| Multi-Region | 28 | Neverwinter | 23 |
| Waterdeep | 13 | Forgedeep | 8 |
| Baldurs Gate | 5 | Luskan | 5 |
| Gauntlgrym | 2 | Northern Sea Gate | 2 |
| Suzail | 2 | Guardian's Gate Ziggurat | 1 |
| Star Metal Hills Mining Complex | 1 |  |  |

These are descriptive counts, not an ownership or consolidation model. In
particular, a `Multi-Region` label cannot substitute for legal-entity or branch
relationships.

## Hierarchy diagnostics

Of 83 populated parent fields, 38 contain only the root marker `—`. The remaining
45 rows use 28 substantive labels. Only four parent values exactly match another
entity title; three additional links resolve after normalizing
hyphen/en-dash/em-dash variants, for seven total. The rest are prose, portfolio
labels, or unresolved names. This is why
the migration requires stable source IDs and an adjudicated relational
`parent_entity_id`, rather than joining on display text.

## Why the raw totals are unsafe

1. **Parent/child overlap.** Northern Crown Financial records 22,000 gp monthly
   revenue while its four branches sum to 23,250 gp revenue, 12,170 gp cost, and
   85 staff. Adding both produces a forbidden 45,250 gp revenue total. The source
   does not resolve which basis controls.
2. **Projection in a current-looking field.** The
   [Zariel Warborn Contract](https://app.notion.com/p/34ce821484b081febf14f062ef3cb91b)
   contributes 747,000 gp—62.54% of raw revenue—but describes that number as
   projected monthly profit at full scale.
3. **Concentrated headcount.** The
   [Bloodaxe Legion](https://app.notion.com/p/321e821484b0812dbba0e10b75086a02)
   contributes 10,000 employees, 66.87% of the raw total. Its costs may also be
   paid through construction subsidiaries, requiring intercompany eliminations.
4. **Mixed dates.** The table combines Hammer 1495 records, eight business rows
   explicitly dated Mirtul 1494, Jörmun-linked 1498 state, later projects,
   real-world edit dates, and undated values. The registry alone does not assign
   those Mirtul rows to a character timeline, and no numeric column has a
   dependable global `as_of` date.
5. **Future capital dominates.** Ten rows whose Date Operational text mentions
   1496 or later contribute 24,485,000 gp, or 78.76% of raw capital. Including a
   separate Waterdeep Warborn row whose 1498 timing appears in notes raises questionable
   future capital to 25,392,000 gp, or 81.68%.
6. **Mixed record kinds.** Businesses, branches, umbrella portfolios, military
   cost centers, construction-in-progress, assets, contracts, JVs, projections,
   and superseded rows share one table and one set of financial columns.
7. **Free-text hierarchy.** Of 83 non-null parent fields, 38 contain only `—`.
   The 45 substantive values use 28 labels, often ownership prose rather than a
   relational parent identifier.
8. **Mixed margin units and bases.** Examples include stored values of `65` where
   the calculated fraction is roughly `0.6505`. A calculated `-4.000` can be a
   legitimate -400% margin when costs exceed revenue, so magnitude alone is not a
   unit error. Other rows disagree without enough evidence to determine whether
   cost, margin, or measurement basis is stale.

## Required migration classification

Every row must receive an adjudicated temporal state and one primary accounting
treatment before it can contribute to the opening state.

| Record class | Default treatment |
|---|---|
| Operating entity | Include realized external flows only when effective |
| Consolidation parent | Presentation roll-up; never add to included children |
| Branch or division | Include at the selected consolidation level |
| JV or external affiliate | Apply an explicit gross/equity/external ruling |
| Asset or cost center | No invented recurring revenue |
| Capital project / CIP | Track budget, commitment, WIP, payable, and payment |
| Contract / instrument | Separate face value, recognition, and settlement |
| Projection / scenario | Forecast only; excluded from current actuals |
| Historical / superseded | Retain provenance; exclude from live totals |

Required independent fields are `effective_from`, `effective_to`, campaign
`as_of`, measurement basis, consolidation method, flow scope, ownership percent,
canonical status, and relational `parent_entity_id`.

## Gate result

The read-only audit is complete. Migration is blocked until the row-by-row
classification docket is accepted. Missing values remain unknown rather than zero,
and no opening cash or consolidated profit figure has been inferred from this table.
