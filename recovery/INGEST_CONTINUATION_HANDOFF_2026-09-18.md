# BAEN ECONOMY ENGINE — SOURCE INGEST CONTINUATION HANDOFF — 2026-09-18

Repository: `CFhacky/baen-economy-engine`
Branch: `codex/reconcile-standalone-authority-20260917`
Draft PR: #1
Head at handoff: `af95cedb20efc02f3e449ee65e4726844c9ea738`

## Hard constraints
- PR remains OPEN / DRAFT / UNMERGED.
- DO NOT MERGE without Chad's explicit instruction.
- DO NOT write to Notion.
- DO NOT advance campaign time.
- DO NOT simulate a canonical month.
- Continue ingestion from the persisted queue; do not restart discovery and do not ask Chad to restate prior facts.

## Task that is in progress
Exhaustively ingest the retained source bodies behind the Empire Source Census and disposition every retained record so completeness is machine-checkable.

Primary queue:
- `recovery/SOURCE_REVIEW_QUEUE_2026-09-18.json`

Completeness/runtime guard:
- `src/baen_economy/completeness.py`
- `tools/check_completeness.py`
- `recovery/COMPLETENESS_ACCEPTANCE_2026-09-18.md`

Body review receipt:
- `recovery/SOURCE_BODY_REVIEW_RECEIPT_2026-09-18.json`

## Last verified persisted queue state before handoff
- Retained core records: 1,620
- REVIEWED bodies: 387
- UNMEASURED bodies: 1,233
- Semantic UNKNOWN: 1,230
- SOURCE_MAPPED: 235
- CONFLICT: 12
- SUPERSEDED: 126
- MISSING_DATA: 4
- FUTURE: 10
- CONTEXT_ONLY: 3

### By source class
- business_registry: 90 / 90 reviewed — COMPLETE
- locations: 182 / 182 reviewed — COMPLETE
- inventories_materials_hoards_assets: 115 / 206 reviewed — 91 remaining
- factions: 0 / 79 reviewed — 79 remaining
- consequence_ledger_a: 0 / 11 reviewed — 11 remaining
- consequence_ledger_b: 0 / 10 reviewed — 10 remaining
- npcs: 0 / 920 reviewed — 920 remaining
- shocks_shortages_threats: 0 / 26 reviewed — 26 remaining
- contracts_orders_obligations_threads: 0 / 89 reviewed — 89 remaining
- demand_perception_context: 0 / 7 reviewed — 7 remaining

## Existing ingestion receipts / substantive findings
Earlier targeted batches:
- `recovery/SOURCE_REVIEW_BATCH_001_2026-09-18.json`
- `recovery/SOURCE_REVIEW_BATCH_002_2026-09-18.json`
- `recovery/SOURCE_REVIEW_BATCH_003_2026-09-18.json`
- `recovery/NCF_SOURCE_BODY_FINDINGS_2026-09-18.json`
- `recovery/RESOURCE_EXTRACTION_BODY_FINDINGS_2026-09-18.json`

Bulk receipts include:
- Business Registry ingest receipts (D1 onward) — Business Registry now fully ingested.
- Locations ingest receipts — Locations now fully ingested.
- Artifact/inventory ingest receipts through at least batch A7; latest verified head message before this handoff was in the Artifact ingest lane.

Important recovered facts already persisted:
- NCF trial-balance gap is real: exact current reserves, deposits, liabilities and equity were not found in the reviewed finance bodies.
- Four old NCF branch costs sum to 12,170 gp/month but are Eleint-1494-era and must not be promoted to exact Day-7 Hammer-1495 current cost.
- No quantified Day-7 opening physical stock-on-hand was recovered from resource pages; production flow != inventory.
- Old consolidation claims of 2 dedicated stone barges and 50+ heavy wagons were quarantined because that consolidation conflicts with live Registry authority.
- Timber source explicitly says Baen currently owns none of its scaled timber supply; Dawnwood is only a seed sawmill; barge acquisition/build is future.
- Brickworks body explicitly confirms four Stonebearers BW-1 through BW-4 allocated across Brickworks / Clay / Treasury hauling; this corroborates the existing 4-of-10 Stonebearer allocation in `MACHINERY_PROGRAMME_2026-09-18.json`.
- Shi'van / ESAMT staged Arterial + Hunding buy-in remains unresolved as an exact current percentage. User recollection is roughly 12–15% at current date; later date is full acquisition of the family share. Do not invent 13.5%. Obvious ESAMT/Hunding pages did not expose the exact current staged percentage.

## Execution rule
DO THE INGEST. Do not spend another long turn designing meta-frameworks.

For each remaining source record:
1. Fetch the live Notion body read-only.
2. Require full fetch (`truncated=false`, zero unknown blocks) before marking REVIEWED.
3. Persist revision timestamp + SHA-256 body digest, not private GM prose.
4. Assign explicit disposition:
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
5. For ECONOMIC_INPUT, assign one or more engine driver owners.
6. Update the persisted queue in meaningful bulk batches.
7. Continue autonomously until the retained queue is exhausted or a real tool/access blocker occurs.

## Recommended continuation order
1. Finish remaining 91 `inventories_materials_hoards_assets`.
2. Ingest 89 `contracts_orders_obligations_threads`.
3. Ingest 26 `shocks_shortages_threats`.
4. Ingest 21 consequence-ledger rows.
5. Ingest 7 demand/perception rows.
6. Ingest 79 factions.
7. Ingest 920 NPCs last, using bulk deterministic classification plus targeted deeper extraction for economically relevant NPC bodies.

## Reporting cadence
Do not narrate every batch. Report only substantial checkpoints, e.g. after a whole source class closes or after ~100+ records, unless a material contradiction is found.

## Acceptance condition
Do not claim source completeness until:
- all 1,620 retained records have body-read/no-body receipts,
- UNKNOWN = 0,
- every record has an explicit disposition,
- every ECONOMIC_INPUT record has driver ownership,
- the driver registry remains intact.

Canonical execution readiness is a separate stricter gate and remains CLOSED until economy blockers are resolved.
