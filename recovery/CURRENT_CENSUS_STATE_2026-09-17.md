# Current Census State — 17 September 2026

This note reconciles the standalone repository's recovery artifacts without deleting earlier evidence.

## Current authority

For current source-census counts and membership state, use:

1. `LIVE_EMPIRE_SOURCE_CENSUS_EXECUTION_SNAPSHOT_2026-09-17.json`
2. `LIVE_CENSUS_RECEIPT_2026-09-17.json`
3. the underlying direct live Notion SQL receipts retained in the recovery acquisition directories

The earlier `LIVE_EMPIRE_SOURCE_CENSUS_REPORT_2026-09-17.md` is historical. It records the intermediate 372-row / five-collection checkpoint and must not be used as the current census count.

## Count reconciliation

The ten current live Notion collections contain **1,381 current members**:

| Collection | Current live membership | Retained captured records | Complete |
|---|---:|---:|---|
| Business Registry | 90 | 90 | Yes |
| Locations | 182 | 182 | Yes |
| Factions | 79 | 79 | Yes |
| NPCs | 681 | 920 | Yes |
| Artifacts | 206 | 206 | Yes |
| Threats | 26 | 26 | Yes |
| Plot Threads | 89 | 89 | Yes |
| Public Perception | 7 | 7 | Yes |
| Consequence Ledger A | 11 | 11 | Yes |
| Consequence Ledger B | 10 | 10 | Yes |
| **Total** | **1,381** | **1,620** | **10/10** |

The NPC difference is deliberate provenance retention: **239 NPC pages were captured previously but are no longer members of the current unfiltered live NPC collection**. They remain stored because absence from the current membership query is not proof that their historical source evidence should be erased.

Therefore the current terminology is:

- **1,381 current-live members** — present in the current ten live collections.
- **239 retained former NPC members** — previously captured source pages preserved for provenance.
- **1,620 retained core source records** — 1,381 + 239.
- **7 contextual authority records** — separate non-collection authority findings.
- **1,627 total stored records** — retained core plus contextual authority.

Do not describe all 1,620 retained core records as current-live membership.

## Coverage state

Source acquisition and simulator coverage are separate dimensions.

The September 17 execution snapshot reports:

- `SIMULATED`: 0
- `FUTURE`: 1
- `HISTORICAL`: 1
- `MISSING_DATA`: 1
- `MISSING_MECHANICS`: 1
- `SUPERSEDED`: 3
- `CONFLICT`: 4
- `UNKNOWN`: 1,616

The canonical execution gate therefore remains **closed**. Completing the census does not authorize a canonical month.

## Campaign boundary

The campaign boundary remains **Day 7 Hammer 1495 DR**. No recovery or extraction operation advanced campaign time.

The recovery evidence records **zero Notion writes**, **zero campaign-time advance**, and no merge of private-vault recovery PR #192.

## What comes next

The collection census itself is no longer the next bottleneck. The next work is coverage expansion beyond the ten collection surfaces and source-to-simulator mapping:

1. finance/banking evidence outside the Business Registry;
2. infrastructure/logistics evidence outside the Locations collection;
3. population and labour authority;
4. construction/capital programmes;
5. military formations and standing contracts;
6. record-level mapping from source evidence to executable mechanics, with unresolved authority staying fail-closed.

These are engine-development tasks. They are not instructions to fabricate missing campaign values.
