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
