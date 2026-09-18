# Baen Economy Engine

Public, standalone, usable **without Grok**.

This repository is the software home of the fail-closed monthly economy engine for **The New Path / Baen Empire**. The private campaign vault and live Notion workspace remain campaign/source authorities; this repository contains the engine, source snapshots/receipts needed for reproducible operation, tests, APIs, and non-canonical preview tooling.

Canonical campaign time remains frozen at **Day 7 Hammer 1495 DR**. The default `baen-empire run` path is now a **source-grounded, non-canonical monthly business-phase preview**: it reads the verified Registry slice and controlling Notion mechanics, posts **zero** canonical ledger entries, writes **zero** Notion rows, and does not advance campaign time. The old stock-flow scenario is retained only under `baen-empire sandbox` and is explicitly synthetic.

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

## Use the browser app

On Windows, double-click:

\`\`\`text
OPEN-BAEN-ECONOMY-APP.cmd
\`\`\`

That launches the local **Baen Economy Engine** application on \`127.0.0.1\` and opens it in your browser. The app is the Empire-level operator rather than a static report: it shows the live source-census state, semantic coverage, the five source→product domains, upstream-product mapping state, known physical/source facts, unresolved gates, and it can execute the controlling source-grounded Hammer-1495 monthly business preview.

The app is deliberately preview-only. It has no Notion-write endpoint, no canonical-ledger endpoint, and no campaign-time advancement path. A successful preview remains review material until explicitly committed in play.

You can also launch it from a shell:

\`\`\`bash
PYTHONPATH=src python -m baen_economy.empire_ops_server --open
\`\`\`

## Use this first

The actual Hammer-1495 operating path is:

```bash
pip install -e .
baen-empire status
baen-empire run --seed "hammer-1495-a"
```

`baen-empire run` follows the campaign's controlling `empire-operations-engine` / `hybrid-business-ops` monthly business phase rather than the synthetic regional macro model:

1. verifies the 90-row Business Registry export;
2. applies the explicit Day-7-Hammer-1495 admission ledger;
3. rolls **once per active commercial sector** using the campaign's Merchant-15 table;
4. rolls the empire Administration expense-control check;
5. selects **3–5 admitted entities** for the campaign d20 complication table;
6. applies only source-known Neglect penalties;
7. produces a zero-write **Vara briefing** and review artifact;
8. reports the five source-backed industrial output lines (Brickworks, Clay Quarries, Silversheen, Star Metal Hills, Warborn Neverwinter) without inventing conversion ratios or inventories;
9. reports Neverwinter 75,000 / Waterdeep 130,000 census, food-sector gp/headcount without physical volumes, five complete arterial distances without freight capacity, and the 1,084 admitted commercial employees without inventing unemployment pools;
10. maps Mesa onto campaign business-phase events, FreeCol onto Warborn 12/15 actual-versus-maximum, and Unknown Horizons onto source-backed production-only lines; a real 1.5 t/mo Warborn precision-steel flow over the 85-mile / 2-day Gauntlgrym corridor is now semantically mapped to OpenTTD's pinned `CT_STEEL` cargo, but OpenTTD remains fail-closed until campaign miles→tiles and fractional tons→integer cargo pieces have authority. Veloren and Brunnfeld remain dormant for missing stocks/prices/demand.

The current admission ledger contains **37 source-admitted operating entities** and **53 excluded/future/unresolved rows**. The source→product semantic layer now also exposes finance/banking, infrastructure/logistics, population/labour, construction/capital, and military/standing-contract domains while keeping unresolved balances, route capacity, Forgedeep population, labour pools, and capital mechanics fail-closed. Its recurring commercial revenue baseline is **299,266 gp/month**, independently inside the Current Financial State authority band of **280,000–320,000 gp/month**. The engine does **not** invent an exact current cash balance or exact consolidated cost where source authority does not provide one; expense/net remain ranges when the books only support ranges. Silversheen's Hammer-1495 180 t/mo × 320 gp/t revenue is admitted; its Eleint 1494 cost table is **not** silently scaled. The Warborn aluminum allocation remains an explicit 30 t/mo vs 20% conflict after that production ruling.

Market condition is unknown by default and therefore supplies no modifier. You may make an explicit preview ruling:

```bash
baen-empire run --seed "hammer-1495-a" --market boom --vara-active
```

Those flags affect that preview only; they do not mutate canon.

### Synthetic / product-stack sandbox

The older regional stock-flow model and the six upstream product runtimes remain useful engineering components, but they are **not** allowed to supply missing campaign facts. They now live behind:

```bash
baen-empire sandbox --seed "sandbox-a"
```

Mesa, Brunnfeld, Unknown Horizons, FreeCol, Veloren, and OpenTTD are invoked in actual campaign work only when their required current inputs are source-backed. A product being runnable is not permission to manufacture Baen state. The default `baen-empire run` path now uses Mesa as an event scheduler for the source-derived business phase when the optional extra is installed; it still will not call OpenTTD, Veloren, or Brunnfeld to fill missing route, stock, or price authority.

The admission and mechanics authority receipts are:

- `recovery/BUSINESS_REGISTRY_ADMISSION_HAMMER_1495.json`
- `recovery/EMPIRE_BUSINESS_MECHANICS_AUTHORITY_2026-09-17.json`
- `recovery/ECONOMY_SOURCE_INPUT_AUTHORITY_2026-09-17.json`
- `recovery/ECONOMY_DRIVER_COVERAGE_2026-09-17.json`

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

## What the actual monthly business phase does

The controlling monthly path does **not** roll every Registry entity independently. It uses the campaign rule as written: one sector revenue roll per active sector, then the empire expense-control roll, then 3–5 entity complication checks and Neglect effects.

The source-admission layer prevents known accounting/timeline errors such as NCF parent+branch double counting, 1496–1498 forward rows entering Hammer 1495, the separately governed ESAMT/Shi'van portfolio being silently folded into Arik's current books, and projected Warborn/Sea Gate/Desertsmouth figures being treated as current recurring revenue.

The current exact consolidated liquid cash, NCF monthly consolidated cost, Silversheen Hammer-1495 cost, and several physical-economy inputs remain unresolved. They are reported as unresolved or ranges; they are not replaced by convenient values.

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
