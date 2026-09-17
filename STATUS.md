# STATUS — Baen Economy Engine

## Current state

The Gate 0/1 foundation and the agriculture-engine revision are in draft PR #65
on `codex/baen-economy-engine-mvp`. The branch is deliberately
stacked on draft PR #48 (`codex/campaign-finance-ledger`) because that PR already
owns the accounting foundation. No Notion write has occurred.

The earlier regional month is now classified only as a synthetic mechanics demo
and is disabled by default. The campaign-facing path is now an interactive local
Food-Sector Operator. It validates the dated source corpus, exposes all named
species/crops as usable planning inputs, and saves/reopens/exports non-canonical
scenarios without changing the live Day 7 Hammer 1495 state.

## Locked decisions

- Campaign facts are never inferred merely to make a model balance.
- Current, historical, projected, superseded, and unknown values remain distinct.
- Parent and child rows cannot both enter consolidated totals without an explicit
  treatment.
- Quantities and money use decimal arithmetic; binary floating point is forbidden.
- Resolved runs are deterministic from the accepted parent snapshot, model,
  ruleset, run plan, and complete authorizing-event envelopes, including
  provenance and authority.
- Negative inventory, overspent labour, oversubscribed routes, unbalanced postings,
  and mutation of an accepted snapshot are hard failures.
- Notion integration is read-only until a separate acceptance gate is approved.

## Implemented and verified locally

- `OPEN-BAEN-FOOD-OPERATOR.cmd` starts a loopback-only browser application from
  the project directory and persists only local preview scenarios under the
  user's Documents folder.
- The dashboard uses exactly five confirmed food businesses: 63 staff, 26,500 gp
  revenue, 20,550 gp cost, 5,950 gp arithmetic net, and 111,000 gp capital.
- The Longsaddle planner reproduces the 1,200 requested / 900 dispatched / 18
  lost / 882 delivered / 300 consumed / 582 closing / zero-residual low case.
- The physical-production planners expose all 15 named species and all 12 crops;
  source technical parameters are locked while capacity, feed, baseline yield,
  opening stocks, receipts, and consumption remain explicit assumptions.
- The monthly preview resolves exactly one visible revenue and expense receipt
  per Agriculture/Aquaculture sector and displays every die, modifier, target,
  margin, factor, effect, and per-entity application.
- All four workflow kinds save to an append-only, hash-verified local SQLite
  store and can be reopened, compared, and exported as printable HTML.
- A real four-workflow HTTP smoke test saved, reopened, and exported all four
  plans; the raw replay seed was absent from the database.

- The complete 90-row registry was queried read-only and a diagnostic audit was
  recorded. Its exact offline receipt, query/page receipt, source schema, 90
  typed rows, and row/property hashes are now verified and persistable. Its raw
  sums are explicitly barred from consolidated use.
- All 90 detailed Registry page bodies were captured read-only and identity-bound
  to the 90-row receipt. None is treated as mechanically current merely because
  it was captured.
- `baen-food report` verifies all seven Agriculture/Aquaculture records. The five
  confirmed commercial rows reproduce 63 employees, 26,500 gp monthly revenue,
  20,550 gp monthly cost, 5,950 gp arithmetic net, and 111,000 gp capital as a
  last-known Eleint 1494 pre-crisis envelope.
- The live agriculture audit cross-references Business, Location, Plot Thread,
  Artifact, Financial, System Reference, and Active+ Faction Beliefs records. It
  binds 26 linked authorities, 15 exact aquaculture species, 12 crop entries,
  Longsaddle, Ravencrest, Orchard Chapel, Forgedeep, Wyrmhelm, Anauroch, roads,
  canals, storage, and threat context without flattening their dates.
- Shelter outputs are restricted to sourced greenhouse produce and tomatoes,
  with Longsaddle separately identifying shelter-zone cold-frame vegetables.
  Wheat/barley/rye and aquaculture feed ratios are retained as technical design
  facts rather than falsely assigned to the shelters.
- The current actual boundary is Day 7 Hammer 1495. Late Kythorn 1495, Day 904,
  and Eleint 1498 facts are separately gated. The later Kythorn state records
  three of eight zones destroyed, Longsaddle as an 11,000-person net importer,
  a 1,200–1,500-ton procurement target, zero procured tons, and zero resolved
  outcomes.
- Exact agriculture calculators cover yield/feed ranges, crop enhancement,
  fertilizer reduction, procurement coverage, Wyrmhelm carcass demand,
  multi-period stock flow, shortages, overflow, route capacity/loss, barges,
  storage, spoilage, and conservation. Every calculation is planning-only.
- The older Agriculture and Food Baseline launchers redirect to the interactive
  Food-Sector Operator; the evidence-only HTML workbench remains available by CLI.
- Snowfall Hearthworks, Operation Laden Table, and NCF source contracts are frozen
  as `CAN-IMPORT` fixtures with unresolved facts preserved.
- Typed normalization, deterministic event identity, append-only revision checks,
  physical stock flow, conservation, route/labour constraints, snapshots, replay,
  and a strict finance bridge are implemented.
- Draft finance-ledger PR #48 was independently reviewed; the new engine exports
  to its Beancount-style boundary but does not adopt its fallback parser as an
  authoritative runtime.
- `baen-economy` now initializes and reopens an append-only SQLite preview,
  dry-runs or atomically commits a month, returns exact retries idempotently,
  renders a prose-first Vara report, and verifies hashes/lineage/artifacts.
- The Operation Laden Table `illustrative-low-v1` profile runs two periods and
  reproduces 900 tons dispatched, 882 delivered, 18 lost, 300 consumed, 582 at
  Longsaddle, and zero conservation residual.
- Optional management checks record every 3d6 face, target, modifier, margin,
  outcome, method, and seed fingerprint but resolve none of the seven binding
  campaign rolls and have no state or finance effect.
- Laden banking remains correctly blocked at zero postings: its 200,000–300,000
  gp target is prospective debt, not revenue, and no draw or settlement exists.
- The offline Notion artifact is review-only, unapproved, applies zero changes,
  and has no connector or write API.
- `baen-business` creates a separate append-only Registry sidecar, resolves a
  deterministic one-row Merchant-15/Administration-16 monthly preview, persists
  an exact bundle, reopens/retries/verifies it, and emits a source-property-bound
  two-field Notion review diff with zero write-eligible or applied items. Merchant-15
  is restricted to a reviewed commercial-sector allowlist; military,
  intelligence, education, and R&D rows fail closed.
- Baen Brickworks has a deliberately partial physical profile: 75,000 bricks and
  2,000 source-tons of clay per month are retained as source capacity envelopes,
  while realized output/consumption/inventory and conservation remain blocked.
- The positive NCF sandbox produces three balanced proposed transactions and
  seven proposed postings for deposit, loan-credit, and repayment semantics.
  Posted counts remain zero and the actual journal rejects the scenario events.
- The open-source adoption register pins every evaluated upstream and separates
  copied/adapted code from concepts and external validation.
- With explicit `--allow-synthetic-demo`, `baen-region` runs a mechanics fixture
  across eight source-identified Registry businesses. Five businesses produce
  using invented scenario inputs; the month consumes inputs and
  labour, applies grain/fish storage loss, moves clay/bricks/construction work
  through same-month handling links, dispatches food on one-period routes, clears
  local demand, records shortages, and responds from site-local prices.
- Three delivered inter-business trades enter the sidecar journal once, with
  goods revenue separated from Arterial Road carriage revenue. Deposit, working-
  capital loan, interest, principal, and tax amounts are derived from realized
  receipts/outflows under explicit non-canonical rules rather than fixed demo
  values.
- The regional database initializes, commits, reopens, reports, verifies, and
  replays identically across independent workspaces and ambient Decimal contexts.
- `PYTHONPATH=src python -m unittest discover -s tests` passes 436 tests.

## In flight

- maintainer review of draft PR #65;
- user-visible acceptance of the new Food-Sector Operator;
- source/ruling completion for opening inventories, site-by-site allocations,
  Longsaddle acreage and rations, aquaculture biomass/feed stocks, storage
  allocation, and executed deliveries before the first canonical physical month;
- period-two arrival/settlement and rolling price/finance state for any later
  approved executable scenario;
- canon rulings and migration classifications listed in the decision docket.
- review of `docs/NOTION_WRITE_SAFEGUARDS.md`; the current build still has no
  writer.

## Not yet canonical or complete

No calculated opening balance, commodity quantity, price, wage, production rate,
or route capacity is canonical merely because it appears in a test fixture or
locally committed preview. Actual campaign advancement remains blocked until Chad
accepts the canon/migration decisions and binding rolls are resolved.

## Whole-economy vertical-slice candidate — 2026-08-29

A separate, double-clickable regional simulator now runs repeated monthly
transitions and readable reports. It covers all thirteen categories in the
request-compliance audit at vertical-slice depth, with exact replay seals,
physical conservation, double-entry checks, and zero Notion/canonical writes.
The fixture binds sixteen exact Registry identities while marking every executable
quantity that lacks canon authority as a non-canonical scenario assumption.

This does not close the project. Acreage-to-yield, arrears enforcement, migrant
wealth transfer, occupation-specific wage pull, and collateral liquidation remain
open; Chad's user-visible acceptance remains required.
