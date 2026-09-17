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

## Public upstream products

The integration rule is explicit: **use the actual upstream product when it exposes a viable library, service, process, plugin, or fork boundary.** A small independently written helper is not treated as equivalent to integrating the product.

All six selected upstreams now have actual-product runtime boundaries implemented and CI-proven at code head `c8d5830745f709838a3effe9ac9a4e588cc5f86f` in GitHub Actions run **#115** (`35280499380`):

- **Mesa** `20841b12559ef920dd4c8263a09fe75ceac7250c` — **direct Python library** on Python 3.12. `src/baen_economy/mesa_runtime.py` executes Mesa's real `Model`, event queue/priority system, RNG initialization, `run_until`, and `DataCollector`.
- **Brunnfeld Agentic World** `e0656ca01630333e26c622ffd4ba4c973b79eebe` — **Node service sidecar**. The exact checkout is built and booted with `npm run server`; Baen reads its published state/economy/market API.
- **Unknown Horizons** `af9c8ef5c7f6cf9ec0b8c9e7d172c555f2793615` — **separate pinned product process**. A child Python process executes the actual upstream `ProductionLine` implementation without copying its production logic into Baen.
- **FreeCol** `0a9e3cce950471fa67ae390d1a2fdf179e732092` — **JVM product harness**. CI builds the real `FreeCol.jar` and executes FreeCol's real `ProductionInfo`, `GoodsType`, and `AbstractGoods` model objects.
- **Veloren** `e633eb8ca15ae97bb5ef5a039fcf6844e96ad704` — **pinned GPL-side Rust adapter**. The exact checkout receives only the narrow state-injection seam needed to feed Baen state; the simulation itself remains Veloren's real `Economy::tick`, with Veloren `EconomyInfo`/`SitePrices` read back out.
- **OpenTTD** `1aca0b60a8024f295e1d0ad2a3407b3dac838099` — **headless dedicated product through the documented admin API**. CI builds the exact native server, boots it, authenticates through the real admin network, and polls the live product rather than copying `DeliverGoods` into Python.

The authoritative status and boundary for all six products is [docs/UPSTREAM_PRODUCT_INTEGRATION.md](docs/UPSTREAM_PRODUCT_INTEGRATION.md). Exact source locations and engineering/license-boundary notes remain in [docs/THIRD_PARTY_SOURCES.md](docs/THIRD_PARTY_SOURCES.md).

`src/baen_economy/upstream_adaptations.py` remains a compatibility/cross-check layer. Its helpers are **not** themselves evidence that the associated product is integrated. Product-level work uses the actual product boundary first.

A proven runtime boundary also does **not** mean every upstream mechanic or default has been adopted into canonical Baen state. Source-to-product semantic mapping remains separately gated by campaign/source authority.

No upstream project dictates Baen populations, prices, wages, taxes, reserve ratios, yields, loss rates, recipes, or campaign probabilities.

## CLI

```bash
PYTHONPATH=src python -m baen_economy.business_cli --help
PYTHONPATH=src python -m baen_economy.food_cli --help
PYTHONPATH=src python -m baen_economy.whole_economy_cli --help
```

`baen-region` still requires `--allow-synthetic-demo` and is **not** the campaign economy.

Python **3.11+** for the base engine. Mesa direct-product integration is optional and requires Python **3.12+** because the pinned Mesa revision itself requires it.

## Validation

The public standalone suite is:

```bash
PYTHONPATH=src python tools/run_standalone_tests.py
```

At code head `c8d5830745f709838a3effe9ac9a4e588cc5f86f`, GitHub Actions run **#115** (`35280499380`) is green across the full matrix. Python 3.11 ran **544 tests, 0 failures, 3 skips**; Python 3.12 also passed the standalone suite and exact Mesa dependency path. Dedicated product jobs passed for Brunnfeld, Unknown Horizons, FreeCol, Veloren, and OpenTTD.

The runner prints every excluded inherited check; exclusions are limited to evidence intentionally absent from this public checkout, principally the private detailed Registry page-body snapshot, plus the monorepo-publisher assertion that is inapplicable to this standalone repository.

`VALIDATION.md` preserves the detailed August 29 private-vault validation history. [VALIDATION_STANDALONE.md](VALIDATION_STANDALONE.md) records the standalone extraction/reconciliation validation evidence.

The 29 August 2026 90-row Registry export is included. The private detailed page-body fixture is not published here; the standalone suite does not synthesize a replacement or silently call those checks passed.

## Authority boundary

See [docs/AUTHORITY.md](docs/AUTHORITY.md). Source truth stays in the campaign authorities; this repository computes only from evidence it can identify, date, classify, and hash. Unknown is not zero. Projection is not current state. Acquired is not simulated.

## License

MIT. See `LICENSE` and `THIRD_PARTY_NOTICES.md`.
