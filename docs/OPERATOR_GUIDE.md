# Economy Operator Guide

The operator is a persistent, local **preview** workflow around the deterministic
stock-flow kernel. A local commit saves an immutable SQLite descendant; it does
not accept campaign canon, post a ledger transaction, or write Notion.

## Open the Food-Sector Operator

This is the default campaign-facing path:

```bash
PYTHONPATH=src python -m baen_economy.food_ops_server \
  --database /durable/path/baen-food-operator.sqlite --open
```

On Windows, double-click `OPEN-BAEN-FOOD-OPERATOR.cmd`. It finds or creates the
project-local Python environment, creates a local append-only scenario database
under `Documents\Baen Economy`, and opens the operator in the default browser.
Keep the launcher window open while using the operator; close it or press Ctrl+C
to stop the local server. It does not run Git, install packages, contact Notion,
post the campaign ledger, or advance campaign time.

The operator provides four runnable planning paths:

1. **Longsaddle grain security** — locks the sourced population, target, budget,
   procurement state, and harvest window; incomplete assumptions remain UNKNOWN.
2. **Aquaculture and feed** — exposes all 15 named species, their sourced yield
   intensities and feed ratios, and exact feed-stock conservation.
3. **Crops and food stock** — exposes all 12 crop entries, sourced yield uplifts
   and fertilizer reduction, and exact food-stock conservation.
4. **Food-sector month** — uses the five confirmed Registry businesses and one
   fully receipted Merchant/Administration roll per sector.

Each result shows Source, Assumption, Derived, and Unknown sections. Save stores
an immutable local preview; Open, Compare, and Export work from the Rulings tab.
These actions never accept campaign canon.

`OPEN-BAEN-AGRICULTURE.cmd` and `OPEN-BAEN-FOOD-BASELINE.cmd` are compatibility
shortcuts that redirect to the Food-Sector Operator. The older evidence-only
workbench is still available with:

```bash
PYTHONPATH=src python -m baen_economy.agriculture_cli open
```

## First runnable workflow

From this project directory:

```bash
python -m pip install -e .

baen-economy scenarios
baen-economy init /durable/path/laden-preview.sqlite --campaign laden-low

baen-economy run-month /durable/path/laden-preview.sqlite \
  --period 1 --commit --roll-preview-checks --seed gm-preview-1

baen-economy run-month /durable/path/laden-preview.sqlite \
  --period 2 --commit --roll-preview-checks --seed gm-preview-2

baen-economy report /durable/path/laden-preview.sqlite --period 2
baen-economy ledger-preview /durable/path/laden-preview.sqlite --period 2
baen-economy notion-dry-run /durable/path/laden-preview.sqlite --period 2
baen-economy verify /durable/path/laden-preview.sqlite
```

Choose a durable state path outside the repository's ledger tree. Runtime
SQLite, WAL, and SHM files are state, not source artifacts, and must not be
committed.

## Explicit synthetic regional mechanics demo

This is not the campaign economy. It exists to test conservation, transit,
market, and bookkeeping kernels with invented inputs.

From this project directory:

```bash
python -m pip install -e .

baen-region init /durable/path/regional-preview.sqlite \
  --scenario baen-regional-mvp \
  --allow-synthetic-demo \
  --seed "choose-a-replay-seed"

baen-region run-month /durable/path/regional-preview.sqlite --commit
baen-region report /durable/path/regional-preview.sqlite
baen-region verify /durable/path/regional-preview.sqlite
```

### What the operator opens

The `.sqlite` file is internal audit and replay state. It is not meant to be read
directly. After `run-month --commit`, the program automatically creates this
ordinary file beside it:

```text
regional-preview-Month-1-Report.html
```

Double-click the HTML file to read the month in a browser. It contains a
plain-language overview and tables for production, labour, transport, losses,
markets, business results, banking, treasury, and accounting integrity. It uses
no remote assets or scripts.

For an already committed database, recreate the readable file with:

```bash
baen-region report /durable/path/regional-preview.sqlite
```

The command prints `Readable report:` followed by the exact filename. A custom
destination is also available:

```bash
baen-region report /durable/path/regional-preview.sqlite \
  --output /durable/path/Baen-Month-1.html
```

`baen-region` is an opt-in synthetic demonstration. It uses eight exact Registry
identities and invented scenario inputs for opening
inventory, labour availability, recipes, route terms, demand, prices, opening
cash, and finance behavior. It records unit-specific production and route
receipts; it never sums bricks, tons, and work units into a purported physical
total.

The current command resolves exactly one month. Same-month Neverwinter handling
links deliver and settle during that close. Grain/fish shipments with one-period
travel remain in transit, so a second `run-month` fails closed until the
period-two arrival/settlement slice exists. A local preview commit changes only
the selected SQLite database, its adjacent machine-audit JSON artifacts, and its
human-readable HTML report. It writes neither Notion nor the canonical campaign
ledger.

Omit `--commit` to execute a no-write dry run. Repeating an exact committed
period returns its stored result without appending another snapshot. A different
seed or roll option for an already committed period is a hard conflict.

`--roll-preview-checks` records Vara's Administration-16 and Merchant-15 3d6
receipts from the separate hybrid-business-operations mechanics profile, not
the Laden source. Every die, target, modifier, total, margin, and outcome is stored.
These optional checks are illustrative only: they do not resolve the operation's
seven binding campaign rolls or affect physical or financial state. Omitting a
seed uses secure randomness; supplying a seed uses stable HMAC-SHA256 rejection
sampling and stores only the seed fingerprint.

A no-write run with preview checks requires a seed so adding `--commit` can save
the exact same dice-bound snapshot. A direct committed run may omit the seed and
will draw once from secure randomness, then preserve the accepted faces.

## Bundled source-backed preview

`operation-laden-table / illustrative-low-v1` keeps source facts separate from
assumptions. It selects the source's 1,200-ton low target, then explicitly
assumes that the full selection enters a Longsaddle-only logistics slice without
allocating the plan's shelter-zone or strategic-reserve shares, 1,200 tons of
supplier stock, a 900-ton monthly route, one-period travel, 2% loss, and a
300-ton illustrative monthly need. Dispatch begins in illustrative Eleasis and
arrival occurs in illustrative Eleint, consistent with the source's first grain
movement window. The hypothetical opening is placed at end-Flamerule, separate
from the Late Kythorn source planning anchor. Pre-arrival local provisioning is
outside the cargo slice, so period 1 does not report a fictitious zero shortage.

The two persisted periods demonstrate:

| Result | Tons |
|---|---:|
| Requested / dispatched / capacity shortfall | 1,200 / 900 / 300 |
| Arrived / transit loss | 882 / 18 |
| Consumed / shortage | 300 / 0 |
| Supplier / Longsaddle closing stock | 300 / 582 |
| Conservation residual | 0 |

The displayed 54.1667 gp/ton value is only `65,000 / 1,200`, including
transport. It is not a market price, settlement price, or inventory valuation.

## Banking boundary

The Laden source records a 200,000–300,000 gp borrowing target, but no lender,
currency, rate, maturity, collateral, draw, procurement settlement, or accepted
opening cash. Therefore the correct ledger preview has zero transactions and
zero postings. It records the borrowing as a prospective liability—not revenue—
and lists the missing terms as blockers.

The strict actual-only `JournalBook` remains unchanged. Stock movement never
becomes revenue, cost, profit, a payable, or cash merely because it occurred in
the physical model.

## Notion boundary

`notion-dry-run` reads the already stored run and emits pure review data. The
artifact has fixed `write_authorized: false`, `write_attempted: false`, and
`applied_count: 0`. Without a verified registry snapshot and approved property
map/write policy, its human-readable operational note is blocked and ineligible.

There is no connector, token option, endpoint option, apply command, sync
command, or write adapter in this package.

## Registry business-preview sidecar

The `baen-business` command uses a separate append-only SQLite database so a
Registry business preview cannot change Operation Laden replay hashes.

```bash
baen-business init /durable/path/business-preview.sqlite \
  fixtures/registry-snapshots/business-registry-2026-08-29.json

baen-business run-month /durable/path/business-preview.sqlite \
  --entity "Baen Brickworks" \
  --month "Eleint 1494 preview" \
  --seed "choose-a-replay-seed"

# Repeat with --commit only after inspecting the dry run.
baen-business run-month /durable/path/business-preview.sqlite \
  --entity "Baen Brickworks" \
  --month "Eleint 1494 preview" \
  --seed "choose-a-replay-seed" --commit

baen-business report /durable/path/business-preview.sqlite
baen-business notion-dry-run /durable/path/business-preview.sqlite
baen-business ledger-preview /durable/path/business-preview.sqlite
baen-business capacity-profile /durable/path/business-preview.sqlite
baen-business verify /durable/path/business-preview.sqlite
```

The seed is used for deterministic HMAC-SHA256 dice sampling. Only its SHA-256
fingerprint is stored in the sidecar; the raw seed is not. The `--seed` value is
still visible in shell history and process arguments, and its fingerprint is the
effective replay key, so this is reproducibility—not secret-storage protection.
The default scenario uses
Merchant-15 for revenue and Administration-16 for expense control, with only the
governing mechanics' named options exposed. Employee counts exactly 200 or 1,000
fail closed because the source size bands overlap at those boundaries.

Merchant-15 is currently limited to the reviewed commercial sectors Agriculture,
Aquaculture, Banking, Construction, Hospitality, Infrastructure, Manufacturing,
Mining/Quarrying, Real Estate, and Trade. Education, Intelligence, Military, R&D,
and any unknown sector require a separate mechanics/accounting ruling and fail
closed.

Each run operates on one exact Operational row. It binds the export, semantic
snapshot, row, and every consumed property hash; refuses rows with Registry audit
issues or missing revenue/cost/employees/dates; uses exact Decimal arithmetic;
and stores the dice receipt, report, zero-transaction ledger preview, and inert
Notion diff as one immutable bundle. Exact retry is a no-op; changed options or
seed for the same entity/month are a conflict.

For this separate Registry business sidecar, open, append, and verify compare the
exact reviewed table and trigger SQL, require recursive triggers and foreign keys,
and reject both same-name no-op guards and `INSERT OR REPLACE` conflicts.

For Baen Brickworks, `capacity-profile` reports only the source envelopes of
75,000 bricks/month and 2,000 source-tons of clay/month. Realized production,
clay consumption, and opening inventories remain null. No conservation claim is
made until the missing recipe ratio, inventory, cost-consolidation treatment,
and surface-economy date are ruled.

## Positive banking sandbox

```bash
baen-business banking-sandbox --format json
```

This fixed synthetic proposal demonstrates a 1,000 gp deposit, a 600 gp loan
credited to a borrower deposit, and repayment of 100 gp principal plus 10 gp
interest. It contains three balanced proposed transactions and seven postings,
but zero posted transactions and zero posted postings. It establishes flow
deltas only—not opening balances, reserve adequacy, lending capacity, or
spendable Crown funds. The actual-only `JournalBook` still rejects every source
event in the sandbox.

See `docs/NOTION_WRITE_SAFEGUARDS.md` for the unapproved future write gate.

## Failure behavior

- `--mode actual` fails closed until CAN-001–006 and an authoritative opening
  event bundle are accepted.
- Periods must be committed consecutively.
- The bundled assumption profile defines only periods 1 and 2.
- SQLite foreign keys, full snapshot hashes, content hashes, parent lineage,
  normalized dice faces, artifact/run bindings, and conservation are rechecked
  by `verify`.
- Snapshots, runs, dice receipts, and artifacts have database triggers that
  reject update and delete operations.
