# VERIFIABLE HANDOFF — Baen Economy Engine — 17 Sep 2026

This file exists because the chat that performed the recovery/integration work is at context limit. Treat this file and the branch contents as the durable handoff. Do not reconstruct state from chat summaries when GitHub can be read directly.

## Repository state

- Repository: `CFhacky/baen-economy-engine`
- Branch: `codex/reconcile-standalone-authority-20260917`
- Inspected code head before this handoff file: `9cc59803ac5aa12272f4b0fe12086dc3b58e874d`
- PR: #1, OPEN / DRAFT / UNMERGED
- No Notion writes.
- No canonical ledger postings.
- No campaign-time advance.

## What is actually implemented

The default command is now:

```bash
baen-empire run --seed "hammer-1495-a"
```

It no longer executes the synthetic stock-flow scenario.

It calls `src/baen_economy/empire_operations.py`, which implements the campaign's controlling monthly business phase:

1. verifies the 90-row Business Registry export;
2. loads the explicit Hammer-1495 admission ledger;
3. admits only the source-classified Arik-side current commercial slice;
4. rolls one 3d6 revenue check per active sector using the campaign's `empire-operations-engine` / `hybrid-business-ops` rules;
5. rolls the Administration expense-control check;
6. deterministically selects 3-5 admitted entities for d20 complication checks;
7. applies only source-known Neglect penalties;
8. produces a zero-write Vara briefing/review artifact.

The synthetic regional/stock-flow model remains available only under:

```bash
baen-empire sandbox --seed "sandbox-a"
```

It must not be presented as the actual Baen Empire state.

## Verifiable source-grounded admission state

File: `recovery/BUSINESS_REGISTRY_ADMISSION_HAMMER_1495.json`

- 37 admitted current operating entities.
- 53 excluded/future/unresolved rows.
- 1,084 admitted commercial employees.
- 299,266 gp/month admitted recurring commercial revenue.
- Current Financial State cross-check: 280,000-320,000 gp/month.
- Admission manifest explicitly records every exclusion reason.
- NCF child branches/product lines are excluded when the current consolidated parent baseline is used.
- Future/forward rows and parallel 1496-1498/Jormun state are excluded.
- Institut/ESAMT is not silently folded into the Arik-side books.
- Silversheen uses the later Hammer-1495 180 t/month × 320 gp/t ruling = 57,600 gp/month, with explicit provenance rather than pretending the stale Registry cell is current.

## Verifiable authority files

- `recovery/EMPIRE_BUSINESS_MECHANICS_AUTHORITY_2026-09-17.json`
  - campaign monthly sector-roll rules;
  - Merchant-15 revenue table;
  - Administration-16 expense table;
  - entity complication and neglect rules;
  - current finance envelope.

- `recovery/ECONOMY_SOURCE_INPUT_AUTHORITY_2026-09-17.json`
  - source-backed economic facts;
  - explicit missing/conflicted data;
  - actual execution rule: USER-RULED / SOURCE-DERIVED / UPSTREAM-ADOPTED only.

- `recovery/ECONOMY_DRIVER_COVERAGE_2026-09-17.json`
  - driver-level coverage instead of the misleading old "207 assumptions" object count.

## Exact inspected blob SHAs at head 9cc5980

- `src/baen_economy/empire_cli.py` — `b0fa2adeab67bfe58a31c91498853002af1197f4`
- `src/baen_economy/empire_operations.py` — `4e0f48f803c005157775808242941d527dc0f5e6`
- `recovery/BUSINESS_REGISTRY_ADMISSION_HAMMER_1495.json` — `d8cb06d24a04c781b2a3332e3d379a63ca9bf418`
- `recovery/EMPIRE_BUSINESS_MECHANICS_AUTHORITY_2026-09-17.json` — `2404b8adabe4b477553d803f0393c63720027099`
- `recovery/ECONOMY_SOURCE_INPUT_AUTHORITY_2026-09-17.json` — `82f0cdd3d2da5deab9e2f37ca65de4d496e95dab`
- `recovery/ECONOMY_DRIVER_COVERAGE_2026-09-17.json` — `e3b3e172c8b038e4ef60fc5ade1d8fbae41c0498`
- `tests/test_empire_operations.py` — `cfd22e7c0ac587b4379a4c136c9106869c26c3dc`
- `.github/workflows/ci.yml` — `eaaaf97c8caa9b65e99c72445ee9c859ee4dd129`

## Relevant commit chain

- `f2ae61677ad34d46c91ab52605cea94aafd67637` — implement source-grounded Empire monthly business phase
- `375c40239c84f0a369eb2f53d5555e7af745a380` — distinguish current Silversheen ruling from stale Registry property
- `d507516c31c9dfa4e8d1d08dd639501f516129ac` — tests for source-grounded Empire phase
- `38c53cbf278b2bfcf877eb634718f002a3019d0c` — make `baen-empire run` execute the controlling Registry business phase
- `e6b7a8a0842bec73e8588d9d0c5f92e3b6540ab7` — CLI tests
- `324b962619a16e71658676e33f2f39e971823eb6` — separate source-grounded CI from sandbox CI
- `177776d65cc619f5dddc02041e4444b38e87e9eb` — README corrected to describe source-grounded run
- `9cc59803ac5aa12272f4b0fe12086dc3b58e874d` — CI assertion fix for literal Markdown matches

## Validation status at handoff creation

At inspected head `9cc59803...`, GitHub Actions run #205 / `35293101918` was IN PROGRESS.

Do **not** claim the new source-grounded path is CI-green unless the exact current head/run is checked after reading this file.

The earlier synthetic all-product stack had green runs, but that is not evidence that the source-grounded Empire business phase is correct.

## What is still NOT finished

This is critical: the original requested engine is **not fully complete yet**.

The current default monthly business phase is source-grounded. The broader physical economy is not yet fully source-grounded because current authority is still missing/conflicted for some drivers, including:

- exact current liquid cash;
- current consolidated NCF monthly cost / trial balance / reserve treatment;
- current Silversheen monthly cost after the Hammer-1495 production ruling;
- broad opening inventories;
- settlement-wide labour pools/unemployment;
- general opening commodity prices;
- household/social-class consumption baskets;
- route freight capacities/loss rates;
- Forgedeep current civilian population;
- Blacklake/agriculture physical output volumes;
- migration rates;
- shock probabilities.

Unknown means unknown. Do not revive the old synthetic values to "complete" the model.

## Upstream public-GitHub products

Actual runtime boundaries exist and were separately proven for:

- Mesa
- Brunnfeld Agentic World
- Unknown Horizons
- FreeCol
- Veloren
- OpenTTD

They remain real engine components. They must only run in actual campaign execution when the current Baen source state supplies the inputs their domain needs. They are not substitute data sources.

The all-product synthetic testbed remains useful under `baen-empire sandbox`; it is not campaign truth.

## Required next work

1. Check the exact branch head and CI before editing.
2. Read this handoff plus the four source/admission/coverage files above.
3. Do not return to the old "207 assumptions" framing.
4. Continue replacing unresolved economic drivers from live Notion/GitHub authority.
5. Use the campaign's existing empire-operations-engine as the controlling monthly business model.
6. Integrate upstream products into actual execution only where source-backed inputs exist.
7. Keep unknown/conflict fail-closed rather than inventing values.
8. No Notion writes, no merge, no campaign-time advance unless explicitly authorized.
9. Do not call the overall recovery finished until the original acceptance condition is actually met.

## Acceptance condition

The requested result is a Baen Economy Engine that can take the actual current campaign state and produce the monthly Empire result using the campaign's real mechanics and the real upstream products where applicable, without invented state, hidden synthetic defaults, double-counting, future-timeline contamination, or manual juggling by the user.

Anything short of that is intermediate work and must be labeled as such.
