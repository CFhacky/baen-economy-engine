# STATUS — Baen Economy Engine

## Repository role

`CFhacky/baen-economy-engine` is the software workspace for the Baen Economy Engine. The private `campaign-development-vault` and live Notion workspace remain campaign/source authorities. Private-vault recovery PR #192 is provenance and recovery history, not the primary development lane for this package.

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
- Canonical campaign time does not advance through recovery, test, preview, source-ingestion, or upstream-product operations.

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

## Upstream product integration state

At code head `c8d5830745f709838a3effe9ac9a4e588cc5f86f`, GitHub Actions run **#115** (`35280499380`) proves executable runtime boundaries for all six selected upstream products:

- Mesa — direct Python library;
- Brunnfeld Agentic World — Node service sidecar;
- Unknown Horizons — separate pinned Python product process;
- FreeCol — JVM product harness against the real `FreeCol.jar`;
- Veloren — pinned GPL-side Rust adapter executing the real `veloren-world` economy;
- OpenTTD — exact dedicated-server build probed through the documented admin network.

`src/baen_economy/upstream_adaptations.py` remains compatibility/cross-check code only. Its helpers are not evidence of product integration and are not a substitute for the runtime boundaries above.

Product integration is also not canonical semantic adoption. Upstream balances/defaults do not become Baen facts, and source-to-product mappings remain subject to the source/coverage gate.

## Standalone validation state

`VALIDATION.md` remains the detailed **29 August 2026 private-vault validation history** and is not rewritten as if it were freshly executed in this repo.

The first literal full-suite run after extraction executed **511 tests**: **502 passed and 9 errored**. Every error was an extraction boundary, not a failing economy assertion: three Windows launchers had been omitted, four finance checks pointed at the private sibling PR #48 ledger, one food-baseline class required the intentionally unpublished Registry page-body snapshot, and one recovery test asserted the old monorepo workflow path.

The reconciliation branch then:

- restored the three exact Windows launchers from the private-vault extraction source;
- bundled the pinned PR #48 chart as `fixtures/finance/pr48-accounts.bean` rather than inventing a replacement;
- added `.github/workflows/ci.yml` for Python 3.11 and 3.12 plus dedicated upstream-product jobs;
- added `tools/run_standalone_tests.py`, which explicitly lists evidence-only exclusions instead of silently marking them passed;
- retained fail-closed handling for the unpublished private page-body fixture;
- replaced “behavior-inspired means integrated” with actual pinned product boundaries for all six selected upstreams.

The current validated code head is `c8d5830745f709838a3effe9ac9a4e588cc5f86f`. GitHub Actions run **#115** (`35280499380`) is green across the full matrix. Python 3.11 ran **544 tests, 0 failures, 3 skips**. Python 3.12 passed the standalone suite and the exact Mesa dependency path. Brunnfeld, Unknown Horizons, FreeCol, Veloren, and OpenTTD dedicated product jobs also passed.

See `VALIDATION_STANDALONE.md` for the executable evidence.

## Immediate development queue

The source-grounded monthly business phase is the default `baen-empire run` path. Known industrial output lines, Neverwinter/Waterdeep census, food-sector financials, complete arterial distances, and admitted commercial headcount are now reported from source authority. Mesa schedules those business-phase events when installed, and FreeCol may consume Warborn 12/15 when its checkout is present. OpenTTD, Veloren, and Brunnfeld remain dormant on the actual path. Forgedeep occupancy, food physical volumes, and route capacities stay unknown.

Remaining source-to-simulator gaps:

1. exact current liquid cash (still a ~400K Shimmerdeep/Crown gap / 450K protected target, not a cash figure);
2. NCF trial balance / current reserves / consolidated monthly cost;
3. Silversheen Hammer-1495 monthly cost restatement and the 30 t/mo vs 20% Warborn allocation ruling;
4. opening inventories, settlement labour pools, general commodity prices, household baskets;
5. route freight capacities/loss rates;
6. Forgedeep civilian population;
7. food physical outputs;
8. shock probabilities and migration rates.

Do not revive synthetic sandbox values to close those gaps.

## Not canonical or complete

No calculated opening balance, commodity quantity, price, wage, production rate, route capacity, projected facility output, upstream default, or test-fixture assumption is canonical merely because it appears in this repository or executes successfully through an upstream product.

The engine is a usable standalone software package. The campaign economy is **not** declared canonically executable yet. `/v1/canonical` must remain blocked until the source-to-simulator coverage gate is genuinely satisfied.
