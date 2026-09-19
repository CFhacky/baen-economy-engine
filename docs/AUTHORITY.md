# Authority and State Boundary

## Why this exists

The live registry currently mixes entities, assets, projects, parent organizations,
branches, historical facts, current operations, and projections. A calculation is
not trustworthy until each value has both a temporal state and an accounting
treatment.

## Temporal state

Every imported value is one of:

- `current` — asserted to apply at the chosen opening date;
- `historical` — true for an earlier dated state;
- `projected` — forecast, target, capacity-at-scale, or planned result;
- `superseded` — replaced by a later authority;
- `unknown` — insufficient evidence to classify.

Only `current` values may enter current-period simulation. `unknown` is excluded
and reported; it is not treated as zero.

For agriculture, the selected current boundary is exactly **Day 7 Hammer 1495
DR, midday Hell-cycle**. Late Kythorn 1495 is a ratified forward scenario;
Ravencrest Day 904 and Eleint 1498 infrastructure are later references;
aquaculture species/yield tables are technical design. They remain visible and
usable for explicitly selected non-mutating previews, but none can become Day 7
opening inventory merely because it is detailed.

## Accounting treatment

Every entity/value is one of:

- `operating_unit` — contributes realized operating flows;
- `consolidation_only` — umbrella presentation, never summed with its children;
- `non_operating_asset` — valuation/holding, not recurring revenue by default;
- `cost_center` — consumes resources but is not automatically a business;
- `project` — tracks budget, commitment, WIP, payable, and payment separately;
- `financial_instrument` — asset or liability governed by its contract;
- `superseded` — retained for provenance but excluded;
- `unknown` — blocked from totals pending classification.

## Calculation and write boundary

The read adapter may ingest Notion query results. The engine may emit a proposed
derived-state diff. No adapter in Gate 0 has a write method. A later writer must be
a separate allowlisted component with dry-run default, provenance fields,
idempotency keys, and an accepted rollback test.

Gate 1 strengthens the proposed diff with exact export/snapshot/row/property
hashes, but does not change its authority. The current source-schema receipt also
marks itself `write_targetable: false` because durable Notion property IDs were
not available. The complete, still-unapproved future gate is specified in
`docs/NOTION_WRITE_SAFEGUARDS.md`.


## Economic actor state origin

Economic-identity records use the existing provenance vocabulary and also carry a separate state-origin classification:

- `SOURCE` — directly established by campaign/source authority;
- `DERIVED` — deterministically calculated from authoritative facts plus an approved rule;
- `INITIALIZED` — simulation-required opening state created under an explicitly approved initialization policy;
- `UNKNOWN` — no lawful value currently exists.

State origin does not replace provenance. A record can be `SOURCE-DERIVED` provenance and still contain UNKNOWN fields.

Economic structure may exist before every quantity is known. For example, a source-backed employment or banking relationship may justify an account shell without justifying an opening account balance. Missing values remain UNKNOWN rather than being inferred for convenience.

Named actors must reconcile beneath source-backed aggregates. Identifying a named employee within an existing workforce does not increase the aggregate headcount. Identifying named loans within a source-backed portfolio reduces the unresolved aggregate remainder; it does not create new total lending.

Institutional, business, trust, estate, programme, and personal finances remain distinct unless authority explicitly establishes otherwise. Management, custody, signatory power, trusteeship, and ownership are separate concepts.

The first economic-identity implementations are Northern Crown Financial and Institut Baen'und. Institut customers/clients require actual economic or contractual evidence; social association, research participation, or faction membership alone is insufficient.
