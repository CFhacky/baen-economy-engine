# CONTINUATION — 18 Sep 2026

This continues `recovery/VERIFIABLE_HANDOFF_2026-09-17.md`. Recovery was not restarted. The synthetic sandbox was not used as campaign state.

## Branch state at start of this continuation

- Repository: `CFhacky/baen-economy-engine`
- Branch: `codex/reconcile-standalone-authority-20260917`
- Head: `cb5449b37ce69eb90e308e2979820a557880d64f`
- PR: #1, OPEN / DRAFT / UNMERGED
- GitHub Actions run #207 was in progress on that head; `empire-actual`, `test (3.11)`, and `test (3.12)` had already succeeded. `sandbox-products-e2e` was still running.

## What this continuation actually did

1. Re-queried live Notion for the remaining driver blockers. Receipt: `recovery/LIVE_SOURCE_REQUERY_2026-09-18.json`.
2. Kept unknown/conflict fail-closed. Exact cash, Forgedeep population, NCF trial balance, inventories, prices, route capacities, and food physical volumes are still missing.
3. Recorded two source conflicts/gaps that were previously implicit:
   - Silversheen Hammer-1495 cost table was not restated after 180 t/mo.
   - Warborn aluminum allocation is 30 t/mo vs 20% of current output.
4. Made the default `baen-empire run` path report the five SOURCE-DERIVED industrial output lines without inventing recipes.
5. Mapped Mesa onto the campaign business-phase events when installed.
6. Mapped FreeCol onto Warborn 12 actual vs 15 maximum when `FREECOL_CHECKOUT` is set.
7. Left OpenTTD, Veloren, and Brunnfeld **NOT_INVOKED** on the actual path.

## Acceptance

The original acceptance condition is **not** met. This is intermediate work: a source-grounded monthly business phase plus known production lines, with upstream products used only where their required current inputs exist.

No Notion writes. No merge. No campaign-time advance. No canonical ledger postings.
