# STATUS — Baen Economy Engine

## Repository role

`CFhacky/baen-economy-engine` is now the software workspace for the Baen Economy Engine. The private `campaign-development-vault` and live Notion workspace remain campaign/source authorities. Private-vault recovery PR #192 is provenance and recovery history, not the primary development lane for this package.

Standalone extraction baseline: `main@dd80d730427967dc78fe7b965b6a6d5875c9f3a2`, extracted from private-vault engine head `2cfb0c5` on 17 September 2026.

Canonical campaign time remains **Day 7 Hammer 1495 DR**. Canonical month execution remains fail-closed.

## Current source census

The latest machine evidence is:

- `recovery/LIVE_EMPIRE_SOURCE_CENSUS_EXECUTION_SNAPSHOT_2026-09-17.json`
- `recovery/LIVE_CENSUS_RECEIPT_2026-09-17.json`
- `recovery/CURRENT_CENSUS_STATE_2026-09-17.md`

Current state:

- **1,381 current-live collection members** across ten Notion collections.
- **239 previously captured NPC pages** retained for provenance although no longer members of the current unfiltered NPC collection.
- **1,620 retained core source records**.
- **7 contextual authority records** retained separately.
- **1,627 total stored records**.
- All ten identified current live collections have complete query-visible property enumeration.
- `SIMULATED = 0`; acquisition completeness is not simulation coverage.
- Coverage remains **CLOSED**.

The older 372-row/five-collection human report is an intermediate checkpoint and is not the current census authority.

## Locked behavioral boundaries

- Campaign facts are never inferred merely to make a model balance.
- `unknown` is not zero.
- Current, historical, projected, superseded, conflicting, and missing states remain distinct.
- Acquired source evidence does not become executable or current merely because it is detailed.
- Parent and child rows cannot both enter consolidated totals without an explicit treatment.
- Quantities and money use decimal arithmetic; binary floating point is barred from authoritative arithmetic.
- Negative inventory, overspent labour, oversubscribed routes, unbalanced postings, and accepted-snapshot mutation are hard failures.
- Notion is read-only from the engine's current authority boundary.
- Canonical campaign time does not advance through recovery, test, preview, or source-ingestion operations.

## Implemented engine capabilities inherited into the standalone package

The extracted package contains the existing registry, business, food, agriculture, regional, whole-economy, operator, HTTP API, audit, and banking-sandbox code from the private-vault engine.

Verified historical capabilities include:

- deterministic preview months and exact replay;
- append-only local preview stores;
- source-bound registry/business previews;
- agriculture source validation, production, stock-flow, calendar, logistics, storage/spoilage, and conservation calculations;
- the Food-Sector Operator and its four workflow types;
- regional/whole-economy synthetic vertical-slice mechanics behind explicit non-canonical flags;
- finance-boundary proposals with zero canonical postings;
- explicit Notion no-write safeguards;
- source/property/row hashing and provenance checks.

These capabilities do **not** by themselves establish current campaign values or open the canonical-month gate.

## Validation state

`VALIDATION.md` records the detailed **29 August 2026 private-vault validation history**, including the 436-test regression suite and focused acceptance paths. It is retained as historical evidence.

This standalone repository previously had no `.github/workflows` directory, so it had no automatic repository-level CI despite containing the extracted test suite. The current reconciliation branch adds a standalone CI workflow. Its GitHub Actions result, once executed, is the current executable validation evidence for this repository.

Until that workflow passes, do not convert the historical 436-test statement into a claim that this exact standalone tree has been freshly revalidated.

## Immediate development queue

The ten-collection census is no longer the next missing deliverable. The recovery snapshot itself identifies the next evidence surfaces:

1. finance/banking evidence outside the Business Registry;
2. infrastructure/logistics evidence outside Locations;
3. population/labour authority;
4. construction/capital programmes;
5. military formations and standing contracts;
6. source-to-simulator coverage mapping and explicit mechanics/data blockers.

The practical target is to move records from `UNKNOWN` to justified executable coverage states without inventing balances, quantities, prices, wages, opening stocks, or campaign events.

## Not canonical or complete

No calculated opening balance, commodity quantity, price, wage, production rate, route capacity, projected facility output, or test-fixture assumption is canonical merely because it appears in this repository.

The engine is a usable standalone software package. The campaign economy is **not** declared canonically executable yet. `/v1/canonical` must remain blocked until the source-to-simulator coverage gate is genuinely satisfied.
