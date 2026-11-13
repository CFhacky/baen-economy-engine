# Completeness Acceptance Standard — 18 September 2026

## Why this exists

The source census and the economy's semantic coverage answer different questions.

A collection count such as **90/90 Business Registry** proves that the collection membership/properties were acquired. It does **not** prove that every page body was read, that every economically relevant statement was classified, or that every source fact has a mechanic/driver owner.

That distinction is now enforced by code in `src/baen_economy/completeness.py`.

## Current machine result

At the current branch state:

- collection acquisition: **PASS**
  - 10 collections represented;
  - 1,620 retained core source records;
  - 1,627 stored records including 7 contextual authority records;
  - 0 identified core records left unmaterialized.
- source-record semantic disposition: **FAIL**
  - 33 / 1,620 retained core records are currently non-UNKNOWN after semantic overlay plus completed body-review batches 001–003;
  - **1,587 remain UNKNOWN**;
  - the 9 current-live semantic mappings in `SOURCE_SEMANTIC_EVIDENCE_2026-09-18.json` are counted only because that artifact explicitly says they move from UNKNOWN.
- exhaustive source-body review: **IN PROGRESS / 23 OF 1,620 REVIEWED**
  - the standalone repo intentionally does not publish the private detailed Registry body snapshot;
  - no checked-in receipt currently proves that all 1,620 retained source bodies were read and dispositioned;
  - selective live-source requeries do not count as exhaustive coverage.
- finite economy-driver registry: **PASS**
  - the current registry contains the 16 driver classes already used by `ECONOMY_DRIVER_COVERAGE_2026-09-17.json`;
  - dropping or silently adding a driver makes the registry gate fail.
- driver disposition presence: **PASS**
  - every current driver has an explicit status;
  - this does not mean every driver is executable or complete.
- canonical readiness: **FAIL**
  - missing/partial drivers, Empire Close unresolved items, and conflicts remain;
  - no canonical month is authorized.

Therefore:

- **coverage_claim_allowed = false**
- **canonical_execution_ready = false**

## Two separate acceptance questions

### A. “Did we actually get everything?”

This is a **coverage-completeness** question.

The answer may become **yes** only when all of these are true:

1. collection/member acquisition reconciles;
2. retained-core UNKNOWN count is zero;
3. every retained source record has a body-read receipt or an explicit no-body/not-applicable disposition;
4. the finite driver registry is intact;
5. every driver has an explicit disposition.

A record may legitimately end as:

- ECONOMIC_INPUT
- ECONOMIC_CONTEXT
- NON_ECONOMIC
- HISTORICAL_ONLY
- FUTURE_ONLY
- SUPERSEDED
- CONFLICT
- MISSING_DATA
- MISSING_MECHANICS
- NO_BODY_NOT_APPLICABLE

The crucial rule is that no retained record may remain silently unreviewed.

### B. “Can the engine run the canonical economy month?”

That is a stricter **execution-readiness** question.

Coverage completeness is necessary but not sufficient. Canonical execution additionally requires all blocking drivers to be complete/executable and the Empire Close to have no unresolved blocking items or unresolved conflicts.

## Privacy-preserving body review

Private GM prose does not need to be published into this standalone repository.

The body-review receipt may store only:

- stable source/page ID;
- source revision / last-edited timestamp;
- body hash when a body exists;
- review disposition;
- economic domains/driver owners when relevant;
- conflict/unresolved references;
- reviewer/provenance method.

The actual prose remains in the private source system.

`recovery/SOURCE_BODY_REVIEW_RECEIPT_2026-09-18.json` is deliberately marked `NOT_YET_EXHAUSTIVELY_MEASURED` until that receipt set exists.

## Operator command

Run:

```bash
python tools/check_completeness.py
```

To make a CI/operator step fail unless source coverage has genuinely closed:

```bash
python tools/check_completeness.py --require-coverage-complete
```

To fail unless canonical execution readiness has also closed:

```bash
python tools/check_completeness.py --require-canonical-ready
```

The default command is read-only and returns the evidence state without advancing time.

## What replaces repeated “sweeps”

The next recovery work is finite:

1. enumerate the retained-core source IDs;
2. attach one privacy-preserving body-read/disposition receipt to every ID;
3. route every ECONOMIC_INPUT record to one or more driver/mechanic owners;
4. leave genuine unknown values unresolved instead of filling them with plausible values;
5. rerun the completeness report;
6. stop only when UNKNOWN and unread/unmeasured coverage reach zero.

This means future remembered facts become either:

- evidence that an already-reviewed receipt was classified incorrectly, which is a specific auditable defect; or
- evidence that a source changed after its recorded revision/hash, which is a source-drift event.

They are no longer an unbounded instruction to “search again and hope.”


## Batch 001 — Arterial / registry body review

The first fixed-queue batch is persisted as `recovery/SOURCE_REVIEW_BATCH_001_2026-09-18.json`.

- 4 source bodies were fetched read-only from live Notion;
- all 4 were complete (`truncated=false`, zero unknown blocks);
- all 4 have revision timestamps and SHA-256 body digests;
- Arterial Road Network and Arterial Township Development are `ECONOMIC_INPUT`;
- Arterial Road Crystal Network and the Hammer-1496 Housing Portfolio are `ECONOMIC_CONTEXT` because their body state is temporally unsafe for Day-7 opening-state use;
- UNKNOWN fell from 1,607 to **1,604** without inventing a value.


## Batch 002 — NCF finance body review

Eight finance bodies were read and hashed. The batch did **not** discover a hidden complete NCF balance sheet.

- parent current authority: 22,000 gp/month revenue, 2.3M gp active loan portfolio, 85 staff;
- exact reserves, deposits, total liabilities and equity remain absent;
- four Eleint-1494 branch rows sum to 23,250 gp/month revenue and 12,170 gp/month cost, but the newer parent revenue authority already proves that roll-up stale; the cost sum is retained only as a historical baseline;
- SSAMT's 12,000 gp corpus is client trust property, not NCF-owned reserves;
- Gold Lending House remains explicitly unconfirmed and is not booked;
- UNKNOWN fell from 1,604 to **1,597** without filling any balance-sheet hole with a guess.


## Batch 003 — resources / inventory body review

Eleven bodies were reviewed across live quarries, Brickworks, timber and older consolidation artifacts. Live per-entity operating flows are now separated from unsafe consolidations. The pass found **no quantified opening stock-on-hand**. It also quarantined uncorroborated “2 stone barges / 50+ wagons” fleet claims, confirmed the current timber supply gap, and independently corroborated the existing four-Stonebearer Brickworks allocation. UNKNOWN is now **1,587**.
