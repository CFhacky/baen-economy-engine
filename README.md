# Baen Economy Engine

Public, standalone, usable **without Grok**.

This repository is the software home of the fail-closed monthly economy engine for **The New Path / Baen Empire**. The private campaign vault and live Notion workspace remain campaign/source authorities; this repository contains the engine, source snapshots/receipts needed for reproducible operation, tests, APIs, and non-canonical preview tooling.

Canonical campaign time remains frozen at **Day 7 Hammer 1495 DR**. Preview months are `scenario_assumption`. They post **zero** canonical ledger entries, write **zero** Notion rows, and do not advance campaign time.

The standalone extraction baseline is `main@dd80d730427967dc78fe7b965b6a6d5875c9f3a2`, extracted from private-vault engine head `2cfb0c5`. Private-vault recovery PR [#192](https://github.com/CFhacky/campaign-development-vault/pull/192) remains provenance/recovery history rather than the software-development home of this package.

## Current source-census state — 17 September 2026

The newest retained census evidence is `recovery/LIVE_EMPIRE_SOURCE_CENSUS_EXECUTION_SNAPSHOT_2026-09-17.json` with receipt `recovery/LIVE_CENSUS_RECEIPT_2026-09-17.json`.

- **1,381** rows are members of the ten current live Notion collections.
- **239** additional NPC pages were captured previously and are retained for provenance even though they are no longer members of the current unfiltered NPC collection.
- Therefore **1,620 retained core source records** are hashed.
- **7** additional contextual authority records are retained separately.
- **1,627 total stored records**.
- All ten identified live collections have complete query-visible property enumeration.
- `SIMULATED = 0`; source acquisition does **not** imply simulator coverage.
- Coverage therefore remains **closed** for canonical month execution.

The old 372-row human recovery report is preserved as historical evidence and is superseded for current counts by [recovery/CURRENT_CENSUS_STATE_2026-09-17.md](recovery/CURRENT_CENSUS_STATE_2026-09-17.md).

## What other apps call

```bash
pip install "git+https://github.com/CFhacky/baen-economy-engine.git"
python -m baen_economy.http_api --host 0.0.0.0 --port 8090
```

```http
GET  /v1/health
GET  /v1/coverage
GET  /v1/openapi.json
POST /v1/preview
POST /v1/canonical   → 409 while coverage is closed
```

```bash
curl -sX POST http://127.0.0.1:8090/v1/preview \
  -H 'content-type: application/json' \
  -d '{"kind":"food","seed":"your-replay-seed"}'
```

`kind` is `food` (five confirmed Agriculture/Aquaculture rows), `registry` (every Registry row, ineligible ones skipped), or `business` (one entity title in `entityId`).

CORS is open (`Access-Control-Allow-Origin: *`). Schema: `tnp.economy.tick-result/1` plus the existing `tnp.business.month-preview/1` row payloads.

## What a preview month does

For each eligible commercial Registry row it:

1. binds source Employees / Monthly Revenue / Monthly Cost cells;
2. rolls Merchant-15 revenue and Administration-16 expense with deterministic HMAC-SHA256-seeded 3d6;
3. applies the GURPS outcome factors;
4. returns proposed gp totals labeled **not canon**.

It will **not** invent opening cash, labour, cities, stock, or missing source facts; consolidate parent and child bank rows without an explicit treatment; treat capital invested as liquidity; advance campaign time; write Notion; or accept a canonical month while the source-to-simulator gate is closed.

## CLI

```bash
PYTHONPATH=src python -m baen_economy.business_cli --help
PYTHONPATH=src python -m baen_economy.food_cli --help
PYTHONPATH=src python -m baen_economy.whole_economy_cli --help
```

`baen-region` still requires `--allow-synthetic-demo` and is **not** the campaign economy.

Python **3.11+**. No third-party runtime dependencies.

## Validation

The public standalone suite is:

```bash
PYTHONPATH=src python tools/run_standalone_tests.py
```

GitHub Actions executes that suite on Python 3.11 and 3.12 and separately verifies the package import surface. The runner prints every excluded inherited check; exclusions are limited to evidence that is intentionally not part of this public checkout, principally the private detailed Registry page-body snapshot, plus one monorepo-publisher assertion that is inapplicable to this standalone repository.

`VALIDATION.md` preserves the detailed August 29 private-vault validation history. [VALIDATION_STANDALONE.md](VALIDATION_STANDALONE.md) records the standalone extraction/reconciliation validation evidence.

The 29 August 2026 90-row Registry export is included. The private detailed page-body fixture is not published here; the standalone suite does not synthesize a replacement or silently call those checks passed.

## Authority boundary

See [docs/AUTHORITY.md](docs/AUTHORITY.md). Source truth stays in the campaign authorities; this repository computes only from evidence it can identify, date, classify, and hash. Unknown is not zero. Projection is not current state. Acquired is not simulated.

## License

MIT. See `LICENSE` and `THIRD_PARTY_NOTICES.md`.
