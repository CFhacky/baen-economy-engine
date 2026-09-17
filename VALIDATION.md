# Validation Evidence — Gate 0/1 and Food-Sector Operator

Validation date: 2026-08-29

## Economy-engine regression suite

Command:

```bash
python -m unittest discover -s tests -v
```

Result: **PASS — 436 tests**.

## Real Food-Sector Operator acceptance

Commands:

```bash
PYTHONPATH=src python -m unittest tests.test_food_ops_acceptance -v
PYTHONPATH=src python -m unittest \
  tests.test_food_ops_app tests.test_food_ops_server tests.test_food_ops_store \
  tests.test_food_sector tests.test_food_security tests.test_food_production -v
```

Result: **PASS — 1 full acceptance journey; 78 focused operator tests**.

The acceptance test starts the real loopback server with a temporary durable
store and uses the served HTTP interface. It loads the application and exact
five-business dashboard, asserts 63 staff / 26,500 revenue / 20,550 cost / 5,950
net / 111,000 capital, and receives all 15 species and 12 crops. It previews,
saves, loads, and exports Longsaddle, food-sector month, tilapia/feed, and
wheat/food-stock plans, then restarts the server and verifies the stored bundles.

The Longsaddle known answer is 1,200 requested, 900 dispatched, 300 capacity gap,
18 lost, 882 delivered, 300 consumed, 582 closing, and zero residual. The month
has exactly four fully receipted rolls. Tilapia and wheat known answers verify
feed and food conservation. Embedded content, request, result, manifest, and
bundle hashes all verify; source fixtures remain unchanged; the raw replay seed
is not in SQLite; Notion, ledger, canonical, and campaign-time mutations remain
zero.

## Agriculture source and workbench acceptance

Commands:

```bash
PYTHONPATH=src python -m unittest discover -s tests -p 'test_agriculture*.py' -v
PYTHONPATH=src python -m baen_economy.agriculture_cli build
```

Result: **PASS — 99 agriculture tests**, followed by successful generation of
`reports/Baen-Agriculture-Workbench.html`.

The strict loader accepted 26 linked Notion authorities, seven Registry records,
15 exact named aquaculture species, 12 crop entries, and the Day 7 Hammer 1495
freeze. Tests reject binary floats, missing evidence, broken page identity,
unknown source links, topology/financial drift, missing-versus-zero collapse,
and promotion of forward/design/projected/unconfirmed evidence.

Production, stock-flow, calendar, and logistics tests cover exact yield/feed and
crop ranges, Wyrmhelm carcass profiles, procurement coverage, one-to-many period
inventory carry, capacity overflow, shortage, storage/spoilage, 100/150-ton
barge limits, multi-leg route losses, deterministic hashes, and zero conservation
residual. Every result records `campaign_time_advanced=false` and creates no
financial posting.

The workbench tests exercise all four authority tabs and all three visible
calculators, assert that all assumption fields begin empty, retain every source
link/species/crop/conflict/blocker, verify responsive table reflow, and confirm
the Windows launcher is repo-relative with no Git or pip operation. Its
JavaScript and generated DOM have no duplicate IDs or remote runtime dependency.

## Source-truth food acceptance

Command:

```bash
baen-food report
```

Result: **PASS**. The verifier loaded 90/90 Registry property rows, 90/90
detailed Registry page bodies, and 7/7 Agriculture/Aquaculture records. The five
confirmed commercial rows reproduced 63 employees, 26,500 gp monthly revenue,
20,550 gp monthly cost, 5,950 gp arithmetic net, and 111,000 gp capital.

The report identifies Shelter Zones as greenhouse produce/tomatoes and explicitly
keeps grain, feed, yield, opening stock, routes, demand, prices, and cash unknown.
It records the later three-of-eight damage state and Longsaddle importer context
without scaling the Eleint 1494 financial envelope or resolving any Laden roll.
Tampered page bodies, row hashes, missing evidence, and unreviewed extraction
fields fail closed. Notion writes, ledger postings, dice, and campaign
advancement are all zero.

Covered behavior includes:

- Notion write-operation denial, read-operation allowlisting, exact source locking,
  complete pagination, deep snapshot immutability, and provenance requirements;
- projection/unknown exclusion and parent/child consolidation failure;
- stable entity IDs, authority, timeline, and simulation-mode isolation;
- deterministic event IDs, full-envelope integrity hashes, authority/phase/type/
  model-version gates, authoritative correction gates, concrete-envelope types,
  inactive reversed revisions, and duplicate rejection;
- input/labour/recipe constraints, inventory reservations, route capacity,
  travel time, losses, consumption, shortages, and price response;
- per-commodity physical conservation; single-commodity route units; fixed Decimal
  context; exact Decimal/index runtime types; order-independent aggregation at
  precision boundaries; and snapshot hashes bound to the model, ruleset, run
  plan, and complete authorizing event envelopes;
- event references and shipment IDs retained in immutable snapshots and rejected
  on replay; the Gate 0 `EventStore` itself is deliberately in-memory;
- exact Decimal finance events accepted only from an append-only event store;
  strict Beancount account/currency/date grammar; immutable account contracts;
  account currency and effective-date enforcement against the pinned PR #48
  chart; balancing by currency; and semantic signs for deposits, loans,
  repayments, and borrowing;
- correction revisions retained for provenance but barred from stock or journal
  mutation until explicit reversal/replacement mechanics exist;
- Snowfall present/future isolation, Laden Table plan preservation, NCF
  consolidation alternatives, and a physical-only synthetic normal-month
  scenario.

## Explicit synthetic regional-demo acceptance

Commands exercised from fresh directories, including paths with spaces:

```bash
baen-region init regional.sqlite --scenario baen-regional-mvp \
  --allow-synthetic-demo --seed regional-acceptance-fixed-seed
baen-region run-month regional.sqlite --commit
baen-region report regional.sqlite --format json
baen-region verify regional.sqlite
```

Result: **PASS** for mechanics only. The fixture selected eight exact Registry
identities and ran five invented producers. Unit-specific receipts showed Construction consuming
20,000 bricks to produce 20 work units, Brickworks consuming 800 source-tons of
clay to produce 30,000 bricks, Aquaculture consuming 30 tons of grain to produce
120 tons of fish, plus quarry and agricultural output. Public summaries do not
add unlike commodity or route units.

The close applied the fixture's one-percent grain and eight-percent fish storage
losses. Same-month handling grossed dispatch for route loss: the Brickworks link
dispatched 50,505.050506 bricks, lost 505.05050506, delivered slightly over
50,000, and satisfied the 50,000-brick construction demand. Clay and completed
work also moved and settled in the same month. Three longer food shipments were
left explicitly in transit for period two. Blacklake's full grain shortage moved
its own site price from 12 to 18 gp/unit; it was not rebased to another site's
price.

Three delivered inter-business trades were journaled once. Goods receipts and
Arterial Road carriage fees were split. Under persisted, explicitly
non-canonical finance rules, realized operating receipts/outflows caused the bank
deposit, working-capital loan, interest accrual, principal repayment, tax
assessment, and tax receipt. The final journal had equal debits and credits and
zero imbalance. Notion writes and canonical-ledger postings were both zero.

The black-box test initializes, commits, closes, reopens, reports, and verifies
two independent SQLite workspaces and compares their complete result and next
state hashes. Ten consecutive fresh replays passed. A direct adapter test also
proved byte-identical output and hashes under caller Decimal precision 4 and 80.

The committed run also generated a self-contained
`regional-Month-1-Report.html` beside the database. Acceptance reopened the exact
file and checked its visible title, noncanonical warning, zero-write boundary,
named businesses, seven or more data tables, all operating sections, and balanced
journal result. It contains no scripts or remote assets. `verify` hash-compares a
fresh deterministic rendering and fails if the human-readable report is changed.

This is not acceptance of a campaign economy. It is one explicit synthetic demo
month only. A second month is not claimed.

The 27 operator-specific tests additionally cover:

- new database initialization, close/reopen, append-only snapshots, atomic local
  preview commits, no-write dry runs, exact retry, changed-option conflict, and
  two concurrent exact commits producing one descendant; concurrent initializers
  leave one verified database;
- exact two-period Laden results, zero conservation residual, source/assumption
  separation, optional auditable dice, exact GURPS critical boundaries, rejection
  of self-hashed false dice arithmetic, deterministic seeded reports, and prose
  inspection;
- actual-mode refusal, period-gap refusal, profile-end refusal, ledger-tree path
  refusal, immutable campaign identity, required append-only triggers, snapshot
  tamper detection, strict plan/event decoding, independent kernel replay, and
  byte regeneration of every derived artifact;
- zero-transaction/non-postable ledger proposals and offline/unapproved/zero-write
  Notion proposals;
- a black-box multi-process CLI journey using a database path containing spaces.

The Gate 1 additions cover:

- 16 adversarial Registry receipt tests: duplicate JSON keys, strict database and
  page identity, canonical UTC capture time, terminal/cursor pagination receipts,
  an independently locked source ordering, source-schema and typed-value drift, UUID/URL mismatch,
  semantic row/property hashes, exact 90-row completeness, and totals that ignore
  the caller's Decimal context;
- 18 append-only sidecar tests: atomic import, exact retry, capture conflict,
  90-row sealing, exact reviewed table/trigger SQL, recursive-trigger enforcement,
  external `INSERT OR REPLACE` rejection, mutation preflight,
  request/profile/period/result binding, source-bound bundles, concurrent commit,
  reopen, tamper detection, and full integrity/foreign-key verification;
- 14 monthly business tests: GURPS critical and effect boundaries, seeded known
  answers and replay binding, required deterministic seeds, allowlisted modifiers and
  commercial sectors, engine-owned Decimal arithmetic, ambiguous size boundaries,
  source/property lineage, inert Notion diffs, and self-rehashed tampering;
- 10 positive banking tests proving exact three-transaction/seven-posting
  semantics, per-currency balance, liability/income signs, deterministic output,
  zero actual postings, and rejection by the actual-only journal;
- five Brickworks capacity tests retaining the two source envelopes while keeping
  all unsupported quantities null and conservation/execution false;
- three black-box `baen-business` journeys covering paths with spaces, dry-run,
  commit, reopen, exact retry, changed-seed conflict, report/diff/ledger/capacity
  retrieval, raw-seed non-persistence, and no source/ledger file mutation.

## Persistent operator acceptance path

Commands exercised in fresh temporary state:

```bash
PYTHONPATH=src python -m baen_economy init "/tmp/operator path/laden.sqlite" --campaign laden-low
PYTHONPATH=src python -m baen_economy run-month "/tmp/operator path/laden.sqlite" --period 1 --commit --roll-preview-checks --seed demo-1
PYTHONPATH=src python -m baen_economy run-month "/tmp/operator path/laden.sqlite" --period 2 --commit --roll-preview-checks --seed demo-2
PYTHONPATH=src python -m baen_economy report "/tmp/operator path/laden.sqlite" --period 2
PYTHONPATH=src python -m baen_economy ledger-preview "/tmp/operator path/laden.sqlite" --period 2
PYTHONPATH=src python -m baen_economy notion-dry-run "/tmp/operator path/laden.sqlite" --period 2
PYTHONPATH=src python -m baen_economy verify "/tmp/operator path/laden.sqlite"
```

Result: **PASS** on Python 3.12.13 / SQLite 3.53.1. The reopened report showed
900 tons dispatched in period 1; 882 delivered, 18 lost, 300 consumed, no
shortage, 582 at Longsaddle, and zero residual in period 2. It also showed all
individual optional 3d6 faces/targets/modifiers/margins, zero binding campaign
rolls resolved, zero financial postings, and zero Notion writes.

An exact period retry returned the stored run without changing snapshot, run,
dice, or artifact row counts. `verify` returned SQLite integrity `ok`, zero
foreign-key violations, and verified scenario/snapshot/run/artifact lineage.

## User-visible simulation smoke test

Command:

```bash
PYTHONPATH=src python -m baen_economy.demo
```

Result: **PASS**. The explicitly non-canonical run produced 100 tons, capped an
80-ton shipment at 50, left 50 tons in transit for one period, then delivered and
consumed 50 of 60 requested tons. It reported a 10-ton shortage, a displayed
54.1667 gp/ton shortage price, and zero physical-conservation residual in both
periods. Repeated execution produced identical snapshot hashes.

## Finance-ledger prerequisite

Commands run in `../campaign-finance-ledger`:

```bash
python -m unittest discover -s tests -v
python tools/campaign_ledger.py validate ledger/main.bean
```

Results: **PASS — 8 tests** and **PASS — 12 balanced transactions**.

The current runtime does not have `bean-check` installed. A fresh external
Beancount 3.2.3 validation is therefore pending; the dependency's own evidence
records a prior real-parser pass, but this branch does not misreport that as a new
run.

## Structural checks

Commands:

```bash
python -m compileall -q src tests
python -m json.tool fixtures/canonical-import/snowfall-hearthworks.json
python -m json.tool fixtures/canonical-import/operation-laden-table.json
python -m json.tool fixtures/canonical-import/ncf-consolidation.json
git diff --cached --check
```

Result: **PASS**.

## Third-party notice packaging

The final project was built twice with the pinned local Setuptools 84.0.0 backend
and `SOURCE_DATE_EPOCH=1787980000`. Both builds produced the identical wheel
SHA-256
`0676ee10a19879844c520987af7cfef5f30eda1797ff667f8a3075ecad1ccb8a`.
The wheel contains
`baen_economy_engine-0.2.0.dist-info/licenses/THIRD_PARTY_NOTICES.md`; its bytes
match the source notice exactly (SHA-256
`ccdcbcc93656cbfb23376e5ea8a04698e4405c2cb5ac25a92fa8d4d0ca6f109e`).
No network dependency was used for this check. The operator remains standard
library only (`argparse`, `sqlite3`, `hashlib`, `hmac`, and `secrets`); no new
third-party notice is required.

The wheel was installed with `--no-index --no-deps` into a fresh virtual
environment. Its 33 package modules expose `baen-economy`, `baen-business`,
`baen-registry-audit`, and `baen-region`; the installed banking sandbox ran with zero posted
entries. Metadata has no `Requires-Dist`. The wheel excludes the private Registry
JSON, tests, SQLite/WAL/SHM/database files, ledger files, and credentials. Python
3.12.13 was tested; a Python 3.11 executable was not available in this runtime.
The repository owner must still choose a first-party distribution license before
any public release; the packaged MIT text covers only the attributed Brunnfeld
adaptation.

Because the private scenario and Registry fixtures are deliberately excluded from
the wheel, installed `baen-region init` was exercised with explicit
`--scenario-path` and `--registry-path` arguments pointing at the private checkout.
The installed command committed the month, created the readable HTML report, and
passed all database and readable-report verification checks. The documented
editable-install workflow finds those private checkout fixtures automatically.

## Live-source audit

The Business Registry query returned and audited all 90 visible rows through the
read-only Notion boundary. The documented raw sums independently matched the
audit result. No Notion write operation was called. Row-level migration remains
blocked pending the decisions in `docs/CANON_DECISION_DOCKET.md`.

The persisted offline receipt has transport hash
`d40285fc31dfee4290a8adb6d336113ba36674b292c27016216baa63afa4fa22`,
semantic snapshot hash
`a4196a7afaa0102f10d1d5fe752f9842ed17fcee6933ead468446d9343b71f1d`,
source-schema hash
`3e18484d5f06e3530a80e3e50a6e11c3f1e3e9c90fb4da531f95c7c4df6f5562`,
and export hash
`9c3f74ef052e49e9f1d62b1a76a1d8e3a504baf64566a016f668b06fe7a6f034`.
These are offline-receipt integrity values, not a Notion signature.

## Registry business sidecar smoke test

The black-box path initialized a new SQLite database with all 90 rows, performed
a no-write Brickworks dry run, committed the same run, returned an exact retry as
a no-op, reopened and verified the store, retrieved the four user-facing
artifacts, and verified all five stored artifacts. The stored run contained zero
journal transactions/postings and zero Notion writes.
The fixed CLI-test seed produced proposed revenue/cost/net of 3,499.65 / 2,233.00 /
1,266.65 gp for that explicitly non-canonical preview. The number is a test
result, not a campaign actual.

The separate banking sandbox content hash was
`2f59e686eb9dff90d5732d816aa0efc964a28576a0230cb0ec77707b185ea00c`:
three proposed transactions, seven proposed postings, and zero posted entries.

## Acceptance boundary

This evidence validates the Gate 0 foundation, synthetic demonstration,
source-anchored but explicitly non-canonical Laden operator preview, verified
offline Registry receipt, deterministic non-canonical business sidecar,
capacity-only Brickworks profile, and positive non-postable banking sandbox. It
does not validate a live campaign opening snapshot, canonical Ring 1 commodity
stocks, a resolved purchase/loan, a write-eligible Registry-bound Notion diff,
or a reconciled NCF/treasury opening balance.
