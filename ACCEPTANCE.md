# Acceptance Contract

## Requested outcome

A playable, deterministic medieval/high-fantasy regional economy that preserves
campaign canon, conserves material quantities, constrains activity by labour and
transport, records banking correctly, and can feed existing empire-operation
briefings without spreadsheet jargon.

## Destination

- Repository: `CFhacky/campaign-development-vault`
- Branch: `codex/baen-economy-engine-mvp`
- Project: `projects/in-progress/baen-economy-engine/`
- Accounting prerequisite: draft PR #48 / `codex/campaign-finance-ledger`

## Authority order

1. Chad's explicit rulings.
2. Current canonical Notion pages and the live Business Registry.
3. Accepted project authority files and source-backed campaign records.
4. Accepted finance-ledger balances for an approved migration band.
5. Sourcebook mechanics and cited external simulation references.
6. Engine-derived results.
7. Synthetic fixtures, which never become canon merely by passing tests.

## Objective checks

1. The live registry is read in full without mutation.
2. Unknown and contradictory values remain flagged rather than guessed.
3. Projection and superseded rows are excluded from current consolidated totals.
4. Parent/child consolidation cannot double-count a flow.
5. Every material movement balances from opening stock through closing stock.
6. Inventory, labour, and route capacity cannot fall below zero.
7. Every financial event balances by currency.
8. Deposits remain bank liabilities; commitments remain distinct from cash paid.
9. An identical accepted parent snapshot, model, ruleset, run plan, and exact set
   of full authorizing-event envelopes reproduce the same hash.
10. Accepted snapshots are immutable and new runs create descendants.
11. Notion writes are impossible in construction mode.
12. Normal month, Snowfall Hearthworks, Laden Table, and NCF scenarios pass their
    distinct accepted tests; Snowfall must never be mislabeled as the food bridge.
13. A new SQLite workspace can initialize, dry-run, atomically commit, close,
    reopen, report, and verify a source-backed Laden Table preview.
14. Exact committed retry is a durable no-op; changed options for the same period,
    period gaps, tampered state, and attempts to initialize `actual` fail closed.
15. Every optional 3d6 receipt preserves individual faces, target, modifiers,
    total, margin, outcome, method, and seed fingerprint while resolving zero
    campaign execution rolls.
16. The two-period illustrative low case dispatches 900 of 1,200 tons, delivers
    882 after 18 tons loss, consumes 300, closes Longsaddle at 582, and has zero
    physical-conservation residual.
17. The Laden ledger proposal contains zero transactions/postings and treats the
    unresolved 200,000–300,000 gp borrowing target as prospective debt, never
    revenue.
18. The Notion proposal is pure review data with no write capability, no attempted
    write, zero applied changes, and blockers for every suggested observation.
19. The checked-in Registry receipt proves an unfiltered 90-row terminal query,
    canonical UTC capture time, locked source schema, strict value types, UUID/URL
    identity, duplicate-key rejection, and typed row/property hash lineage without
    claiming cryptographic attestation from Notion.
20. A separate SQLite sidecar imports all 90 rows atomically, seals snapshots and
    artifacts append-only, reopens, retries exact content idempotently, detects
    conflicts/tampering, rejects changed or same-name no-op guard SQL and
    `INSERT OR REPLACE` conflicts before an append, and verifies foreign keys and
    semantic hashes.
21. A seeded one-entity business preview uses only allowlisted mechanics modifiers,
    applies Merchant-15 only to reviewed commercial sectors, preserves exact source
    values, records and replay-checks every 3d6 face and outcome, creates no journal
    transaction, and cross-binds its request/profile/period/result and each
    suggested Registry value to its original property hash.
22. Employee counts exactly 200 or 1,000 fail closed until the overlapping size
    bands receive a ruling; unknown revenue/cost and audited rows are not coerced
    into a run.
23. The positive banking sandbox contains exactly three balanced proposals and
    seven postings with deposits as liabilities, principal separated from interest,
    and zero actual postings; actual journal admission rejects the scenario events.
24. The Brickworks profile makes no realized-production or conservation claim and
    retains nulls for the missing material ratio and opening inventories.
25. A fresh, explicitly opted-in synthetic `baen-region` workspace executes one
   mechanics-demo regional month
    with at least two active businesses, same-entity input/output conversion,
    workers and payroll, the Brickworks → Construction link, route capacity/loss,
    perishable storage, shortage-driven site-local pricing, and a changed durable
    state hash.
26. At least one delivered inter-business trade appears both in market receipts
    and exactly balanced `enterprise_trade` books; goods and carrier revenue are
    separated. Bank deposit/loan/interest/principal and treasury tax values are
    caused by the realized receipt/outflow rules recorded in the opening preview,
    not fixed hidden outputs.
27. Two independent regional workspaces replay byte-identically, verification
    succeeds after process restart, caller Decimal precision cannot change the
    result, raw seed text is not persisted, and Notion/canonical posting counts
    remain zero.
28. A committed regional month automatically creates a self-contained HTML file
    beside the database. A user can open it directly and read the monthly overview,
    named businesses, production, labour, transport, storage loss, markets,
    banking, treasury, entity statements, and accounting integrity without
   inspecting SQLite or JSON. Verification detects a changed report.
29. The source-truth food path loads exactly 90/90 Registry rows, 90/90 detailed
   page bodies, and 7/7 Agriculture/Aquaculture records.
30. The five confirmed commercial food rows reproduce 63 employees, 26,500 gp
   monthly revenue, 20,550 gp monthly cost, 5,950 gp arithmetic net, and 111,000
   gp capital as a last-known Eleint 1494 pre-crisis envelope.
31. Agricultural Shelter Zones expose sourced greenhouse produce and tomatoes,
   while Longsaddle separately exposes shelter-zone cold-frame vegetables. The
   broader technical programme retains wheat, barley, rye, fifteen named species,
   and feed ratios without assigning them to an unsupported site.
32. Orchard Chapel's 1498 location authority retains its crops, processing, and
   5,000 gp/year while remaining outside Day 7 Hammer execution. The Lobster King
   Registry row and later detailed authority remain visibly conflicted rather
   than either being erased or silently consolidated.
33. The later Kythorn context preserves three of eight shelter zones destroyed,
   Longsaddle as an 11,000-person net importer, the 1,200–1,500-ton procurement
   plan as a plan, and zero resolved execution outcomes.
34. Tampered page bodies, row hashes, missing evidence, or an unreviewed numeric
   extraction field fail closed.
35. The invented regional scenario is disabled by default and cannot initialize
   without an explicit synthetic-demo flag.
36. The strict agriculture fixture validates 26 source documents, seven Registry
   entities, fifteen exact named aquaculture species, twelve exact crop entries,
   source URL/page-ID identity, internal references, exact decimal text, safety
   zeroes, and deterministic content hashing.
37. Day 7 Hammer 1495 is the only current-actual date. Late Kythorn 1495,
   Eleint 1498, Day 904, technical, projected, and undated references cannot be
   admitted to current execution and require an explicit non-mutating preview
   selection where applicable.
38. Agriculture planning calculations preserve missing-versus-zero, exact
   Decimal arithmetic, multi-period inventory carry, shortages, overflow,
   spoilage, route loss/capacity, storage capacity, and zero conservation
   residuals while creating zero campaign-time or financial mutations.
39. The self-contained Agriculture Workbench exposes four separate authority
   layers, all named species and crops, dated larger systems, logistics evidence,
   Faction Beliefs results, contradictions, blockers, and functioning yield/feed,
   crop-uplift, and inventory calculators.
40. Every workbench assumption input starts blank, the Windows launcher is
   repository-relative and performs no Git/pip operation, and the generated HTML
   opens without requiring the user to read SQLite, JSON, or terminal output.
41. The browser operator loads the exact five-business food envelope and exposes
   all fifteen named species and twelve crop entries as selectable source-bound
   inputs rather than generic fish/crop placeholders.
42. Longsaddle, aquaculture/feed, crop/food-stock, and sector-month previews each
   run through the real local HTTP boundary and classify Source, Assumption,
   Derived, and Unknown without Notion, ledger, or campaign-time mutation.
43. The food-sector month makes exactly four visible receipts—revenue and expense
   for Agriculture and Aquaculture—and shows every face, base target, modifier,
   effective target, total, margin, outcome, factor, effect, and per-entity result.
44. All four workflow kinds save append-only, reopen after server restart, compare,
   and export readable HTML; request/result/manifest/bundle hashes verify and raw
   deterministic seeds are not persisted.
45. The one-click Windows launcher starts only a loopback server, stores scenario
   data outside the repository, and does not require the user to read a SQLite
   file or run Git/pip/Notion commands.

## Conditions that block acceptance

Any invented opening cash presented as source fact/canon, unbalanced posting,
negative stock, unconstrained shipment, silent timeline merge, parent/child
double count, nondeterministic replay, unreadable operator output, or unapproved
Notion mutation is blocking.

## Whole-economy regional vertical-slice addendum

These checks govern the new `OPEN-BAEN-WHOLE-ECONOMY.cmd` path. Machine
verification is not Chad's acceptance and does not make the scenario canonical.

- [x] Settlement populations and four class-specific household baskets persist.
- [x] Tenure, acres, rent, feudal dues, tithes, taxes, and treasury receipts run.
- [x] Agriculture, extraction, crafts/manufacturing, construction, and services run.
- [x] Occupation capacity, payroll, employment, wages, and bounded migration run.
- [x] Demand, substitution, cash-constrained clearing, shortages, and prices persist.
- [x] Routes enforce carrier, capacity, travel, toll, loss, prepayment, and arrival.
- [x] Entity and treasury accounts change only through realized transfers.
- [x] Deposits, reserves, loans, collateral pledges, interest, repayment, and default run.
- [x] Weather, harvest, war, monster, political, infrastructure, and policy shocks run.
- [x] One command advances one hash-chained month across the joined regional loop.
- [x] HTML states what changed, where, why, integrity results, and available decisions.
- [x] Brunnfeld's pinned MIT available-to-promise method excludes pledged stock at
      production, consumption, trade, routing, credit, and price-supply boundaries.
- [x] A fresh three-month user-visible run reopens and verifies without network access.
- [ ] Couple acreage to agricultural capacity and yield.
- [ ] Age, service, relieve, or enforce arrears through the ledger.
- [ ] Move household funds with migrants and use occupation-specific wage signals.
- [ ] Liquidate seized collateral and connect bank operating cash to regulated equity.
- [ ] Obtain Chad's user-visible acceptance and any canon/ruling approvals.
