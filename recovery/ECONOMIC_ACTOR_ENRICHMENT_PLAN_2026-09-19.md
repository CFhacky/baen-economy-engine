# Economic Actor Enrichment Plan — 2026-09-19

Repository: `CFhacky/baen-economy-engine`  
Implementation branch: `codex/reconcile-standalone-authority-20260917`  
Campaign boundary: **Day 7 Hammer 1495 DR**  
PR #1: keep **OPEN / DRAFT / UNMERGED**

## Hard boundaries

- No Notion writes.
- No PR merge without explicit user instruction.
- No campaign-time advance.
- No canonical month simulation.
- Do not restart source discovery.
- Do not rereview the completed 920-NPC ingest.
- Do not invent missing balances, prices, stocks, rates, customers, salaries, or quantities.
- Persist meaningful work to GitHub.
- Read committed results back before claiming completion.

## Starting state

Source review is complete when assembled through the committed NPC merge pipeline:

- retained records: 1,620
- UNMEASURED: 0
- UNKNOWN: 0
- coverage claim allowed: true
- canonical execution readiness: false

The remaining problem is not another source sweep. It is to create coherent economic structure around already-known campaign actors and institutions.

The first two vertical slices are:

1. **Northern Crown Financial (NCF)**
2. **Institut Baen'und**

NCF exercises banking, accounts, loans, deposits, ownership, trusts, and ledgers.  
The Institut exercises institutional employment, customers/clients, programmes, procurement, restricted funds, facilities, and cost centers.

---

## Phase 0 — Read authority

Before creating records, read:

- `docs/ECONOMIC_ACTOR_MODEL.md`
- `docs/ECONOMIC_ACTOR_WORKBENCH.md`
- `docs/AUTHORITY.md`
- `docs/ARCHITECTURE.md`
- `recovery/POST_REVIEW_BLOCKERS_2026-09-19.json`
- `recovery/ECONOMY_DRIVER_COVERAGE_2026-09-17.json`
- completed NPC review/merge artifacts
- relevant Registry, contract, faction, location, and source-body evidence already persisted

Use live Notion read-only only when the required source body is not already available in persisted review evidence and the page is accessible. No writes.

---

## Phase 1 — Common actor substrate

Implement the common model once.

Create or prepare:

```text
data/canonical/
  actors.csv
  relationships.csv
  accounts.csv
  employment.csv
  ownership.csv
  loans.csv
  contracts.csv
  property_interests.csv
  inventory_holdings.csv
```

If the repository's existing data architecture supports a more appropriate equivalent location after inspection, document the move rather than silently scattering files.

Add code sufficient to:

- validate stable actor IDs;
- validate relationship types;
- load canonical tables;
- build/query a SQLite runtime representation;
- preserve provenance and state origin;
- reject unsupported SOURCE claims;
- detect duplicate actors;
- prevent obvious headcount double-counting.

Do not create hundreds of Markdown files.

---

## Phase 2 — NCF vertical slice

Build NCF first.

### Required extraction

From existing reviewed sources, recover and connect:

- NCF institutional actor;
- ownership/control structure;
- named officers and employees;
- known borrowers;
- known loan facilities;
- known customer/depositor relationships;
- business banking relationships;
- trust relationships;
- authorized signers/managers;
- account relationships;
- branch/institution relationships;
- known reserves/assets only where source-backed.

### Account creation rule

An account relationship may exist with UNKNOWN opening balance.

Do not infer balances merely because an account logically exists.

### Bottom-up reconciliation

Produce:

`recovery/NCF_BOTTOM_UP_RECONCILIATION_2026-09-19.json`

It must distinguish:

- source-backed totals;
- named source-backed subrecords;
- mathematically derived aggregate remainder;
- unresolved liabilities/equity/cash/deposits;
- conflicts;
- institutional policy questions requiring user ruling.

The NCF active-loan aggregate may be decomposed only as:

```text
source total - source-backed named facilities = unresolved portfolio remainder
```

Do not invent borrower identities for the remainder.

Do not promote Eleint-1494 branch costs into exact Hammer-1495 current costs.

---

## Phase 3 — Institut Baen'und vertical slice

After the common substrate exists, build the Institut using the same actor layer.

### Institutional actor

Create one Institut Baen'und RESEARCH_INSTITUTION actor unless sources establish legally/economically distinct child entities.

Default internal divisions to programmes/cost centers, not separate businesses.

### Employees and personnel

Identify source-backed:

- leadership;
- administrators;
- faculty;
- researchers;
- artificers;
- specialists;
- field personnel;
- support staff;
- named teams;
- aggregate staff/faculty counts.

Create employment relationships without double-counting named staff on top of an existing aggregate total.

Where an aggregate is source-backed but individuals are not all named, retain an anonymous workforce pool.

### Customers / clients

The Institut may have customers, clients, patrons, students, contract counterparties, buyers, commissioning institutions, or service recipients. These must be derived from actual economic/contractual evidence.

Do **not** classify an NPC as a customer merely because they are:

- a friend or ally;
- a student in a non-economic sense;
- a research subject;
- a faction member;
- associated with an Institut researcher;
- mentioned in the same project.

For every proposed customer/client, record:

- customer actor;
- Institut actor/programme;
- relationship type;
- service/good/contract/patronage basis;
- source evidence;
- known amount/terms if any;
- UNKNOWN where amount/terms are absent.

### Programmes and cost centers

Recover source-backed institutional subdivisions such as research programmes, laboratories, workshops, archives, field operations, Warborn/consciousness/artifact work, or other named programmes.

Represent them as institutional programmes/cost centers unless a source establishes separate legal ownership.

### Facilities/assets

Link source-backed laboratories, workshops, archives, field stations, controlled sites, equipment pools, and other institutional assets to the Institut or appropriate programme.

Ownership and custody remain distinct.

### Funding and accounts

Identify source-backed:

- institutional funding sources;
- grants/patronage;
- contracts;
- procurement;
- restricted funds;
- research funds;
- NCF banking relationships;
- payroll mechanisms.

If a banking relationship exists but balances do not, create account shells with UNKNOWN balances.

Do not assign research funds to a researcher's personal wealth.

### Institut reconciliation output

Produce:

`recovery/INSTITUT_ECONOMIC_RECONCILIATION_2026-09-19.json`

At minimum report:

- institutional actors created;
- named employees linked;
- aggregate employee/faculty pools retained;
- programmes/cost centers;
- customers/clients proposed and evidence basis;
- contracts;
- facilities/assets;
- accounts/funds;
- procurement/supplier links;
- cross-links to NCF;
- unresolved quantities;
- conflicts;
- user rulings required.

---

## Phase 4 — Candidate and review artifacts

Generate:

`recovery/NPC_ECONOMIC_ACTOR_CANDIDATES_2026-09-19.json`

The candidate file is not another NPC review. It routes already-reviewed actors into the economic model.

Each row should state:

- stable NPC/source ID;
- proposed economic tier E0-E4;
- evidence summary;
- proposed actor/relationship/account/employment/ownership actions;
- affected institution (NCF, Institut, both, or other);
- provenance;
- state origin;
- whether a user ruling is required.

Generate:

`review/Baen_Economic_Actors_Review.xlsx`

Initial workbook scope is NCF + Institut only.

Use the sheet and validation contract defined in `docs/ECONOMIC_ACTOR_WORKBENCH.md`.

---

## Phase 5 — Decision docket

Do not ask the user hundreds of per-NPC questions.

Prepare a compact institutional decision docket for policies that unlock many rows.

Examples for NCF:

- employee payroll/current-account policy;
- borrower settlement-account policy;
- financed-business operating-account policy;
- business/owner account separation;
- trust segregation;
- branch cash/reserve treatment where not already governed.

Examples for Institut:

- institutional payroll mechanism;
- whether salaried staff normally receive accounts through a named bank where source context supports it;
- treatment of research programmes as restricted funds/cost centers;
- student/customer distinction;
- external commissioned-research/service relationship treatment;
- internal versus external procurement rules.

Use `docs/CANON_DECISION_DOCKET.md` conventions where applicable.

---

## Phase 6 — Promote reviewed structure

After user decisions:

- validate workbook decisions;
- update canonical CSV tables;
- produce a deterministic change receipt;
- build/rebuild SQLite runtime state;
- verify actor and relationship references;
- verify headcount reconciliation;
- verify loan/aggregate reconciliation;
- verify ownership/control constraints;
- preserve UNKNOWN quantities rather than filling them.

---

## Phase 7 — Gap classification

Produce:

`recovery/ECONOMIC_IDENTITY_GAPS_2026-09-19.json`

Classify every remaining material gap as one of:

- USER_RULING_REQUIRED
- DERIVABLE
- INITIALIZATION_REQUIRED
- GENUINELY_MISSING_SOURCE
- MECHANIC_REQUIRED
- CONFLICT

This file becomes the handoff from economic identity enrichment to later initialization/mechanics work.

---

## Required repository outputs for this milestone

```text
docs/ECONOMIC_ACTOR_MODEL.md
docs/ECONOMIC_ACTOR_WORKBENCH.md
recovery/ECONOMIC_ACTOR_ENRICHMENT_PLAN_2026-09-19.md

recovery/NPC_ECONOMIC_ACTOR_CANDIDATES_2026-09-19.json
recovery/NCF_BOTTOM_UP_RECONCILIATION_2026-09-19.json
recovery/INSTITUT_ECONOMIC_RECONCILIATION_2026-09-19.json
recovery/ECONOMIC_IDENTITY_GAPS_2026-09-19.json

data/canonical/actors.csv
data/canonical/relationships.csv
data/canonical/accounts.csv
data/canonical/employment.csv
data/canonical/ownership.csv
data/canonical/loans.csv
data/canonical/contracts.csv

review/Baen_Economic_Actors_Review.xlsx
```

Property/inventory tables may be added in the same milestone if real source-backed records are found; do not create meaningless empty complexity merely to satisfy a filename list.

---

## Acceptance

This phase is successful when:

- the common actor model is implemented once;
- NCF and Institut are represented as distinct institutional actors;
- source-backed NCF officers/employees/borrowers/customers/relationships are connected;
- source-backed Institut leadership/employees/programmes/customers/contracts/facilities are connected;
- customer classification is evidence-based;
- named employees reconcile inside source-backed aggregate staffing;
- account shells may exist with UNKNOWN balances;
- business/institutional/personal finances remain separate;
- named financial totals reconcile to source aggregates or explicit discrepancy records;
- unresolved aggregates remain explicit;
- no unsupported quantities are invented;
- conflicts remain conflicts;
- the Excel workbook is generated as a review surface, not treated as sole authority;
- no Notion write occurs;
- no campaign time advances;
- no canonical month executes;
- PR #1 remains unmerged.

Report only substantial checkpoints or real blockers during execution.
