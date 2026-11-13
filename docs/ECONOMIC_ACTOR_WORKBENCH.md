# Economic Actor Workbench

## Purpose

The Economic Actor Workbench is the human review surface for bulk economic identity creation. It prevents the project from turning hundreds of actors, accounts, loans, employees, and ownership interests into hundreds of manually maintained Markdown files.

The workbench is **not** the canonical database. It is a generated review artifact over proposed or current structured state.

The first workbench scope is limited to:

1. Northern Crown Financial (NCF)
2. Institut Baen'und

---

## Storage model

Permanent structured state:

```text
data/canonical/*.csv
```

Runtime query/simulation state:

```text
CSV authority -> validation/import -> SQLite runtime
```

Human review:

```text
review/Baen_Economic_Actors_Review.xlsx
```

Generated narrative reports may be produced from structured state for major actors, but Markdown is never the primary database.

---

## Workbook sheets

Initial workbook:

- Summary
- NCF Actors
- NCF Accounts
- NCF Employment
- NCF Ownership
- NCF Loans
- NCF Contracts
- Institut Actors
- Institut Accounts
- Institut Employment
- Institut Programmes
- Institut Customers
- Institut Contracts
- Institut Facilities
- Conflicts
- Needs Ruling
- Initialization

Common review columns:

- Stable ID
- Display Name
- Source ID
- Source Evidence Summary
- Proposed Action
- Provenance
- State Origin
- Current/Proposed Status
- Decision
- Reviewer Note

Allowed decision values:

- APPROVE
- REJECT
- MODIFY
- NEEDS_DISCUSSION

---

## Review philosophy

The user should decide **institutional rules and exceptions**, not manually create every row.

Examples of suitable batch rulings:

- NCF employees receive NCF payroll/current accounts.
- NCF borrowers receive settlement accounts.
- NCF-financed businesses maintain operating accounts.
- Institut salaried personnel are paid through an institutional payroll process.
- Institut research programmes use restricted institutional funds rather than personal researcher accounts.
- Institut customer/client records require an actual commercial, contractual, patronage, tuition, procurement, or service relationship.

Once a rule is approved, the engine may generate the rows that logically follow from source-backed eligibility.

---

## Unknown values

A missing balance does not block creation of an account shell.

A missing salary does not block creation of an employment relationship.

A missing contract amount does not block recognition of a source-backed contract shell.

Unknown values remain blank/null and carry:

```text
state_origin = UNKNOWN
```

They are never silently filled with plausible values.

---

## Import validation

Workbook decisions must be validated before promotion into `data/canonical/`.

Reject at minimum:

- duplicate stable IDs;
- references to nonexistent actors;
- invalid relationship types;
- named employees double-counted on top of source aggregate headcount;
- ownership percentages exceeding lawful totals where percentages are known;
- SOURCE values without supporting source evidence;
- account balances created from unsupported inference;
- loans without lender/borrower linkage;
- customer/client classification based only on social association;
- research funds assigned to personal wealth without authority.

The importer should produce a deterministic change receipt.

---

## First vertical slices

### NCF

Use the workbench to review:

- officers/employees;
- known borrowers;
- known customers/deposit relationships;
- accounts;
- ownership/control;
- trust relationships;
- named facilities;
- unresolved portfolio aggregates;
- bottom-up balance-sheet reconstruction.

### Institut Baen'und

Use the workbench to review:

- institutional leadership;
- named faculty/staff/researchers/specialists;
- employment relationships;
- programmes/cost centers;
- facilities;
- procurement/supplier relationships;
- customers/clients where economically evidenced;
- restricted/research funds;
- NCF/banking relationships where established;
- external contracts and service relationships.

The Institut should default to one institutional actor with programmes/cost centers, not a family of invented businesses.

---

## Output standard

The workbook is useful if a reviewer can answer questions such as:

- Show only proposed NCF accounts.
- Show only Institut customers whose economic relationship is source-backed.
- Show only staff not yet reconciled against aggregate headcount.
- Show only records requiring user rulings.
- Show only UNKNOWN balances.
- Show only conflicts.

The user should not have to inspect all 920 NPCs or maintain individual Markdown files to operate the economic actor layer.
