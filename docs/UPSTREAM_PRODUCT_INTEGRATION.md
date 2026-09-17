# Upstream product integration authority

This document governs how the Baen Economy Engine uses the public simulation products Chad explicitly selected for investigation. It supersedes any wording that treats a small reimplementation of one upstream behavior as equivalent to using that upstream product.

## Rule

Use the **actual upstream product** whenever it exposes a viable library, service, process, plugin, or fork boundary. A Baen-local behavior adapter is acceptable only when the upstream product cannot practically accept Baen state through a supported boundary, and it must be labeled as an adaptation rather than a product integration.

No upstream product supplies campaign canon. Population, money, recipes, wages, taxes, yields, reserve ratios, travel losses, and campaign event probabilities still require Baen source authority.

## Current product matrix

| Upstream | Pinned revision | Product boundary | Baen treatment | Status |
|---|---|---|---|---|
| Mesa | `20841b12559ef920dd4c8263a09fe75ceac7250c` (`4.0.0a0`) | Python library: `mesa.Model`, event queue/schedules, RNG ownership, `DataCollector` | **DIRECT LIBRARY**. Installed from the exact Git commit on Python 3.12 and executed by `mesa_runtime.py`. Python 3.11 remains a supported Baen base runtime without pretending a local scheduler is Mesa. | **IMPLEMENTED / CI-PROVEN** |
| Brunnfeld Agentic World | `e0656ca01630333e26c622ffd4ba4c973b79eebe` | Node/TypeScript product with `npm run server`; published HTTP/SSE API includes `/api/state`, `/api/economy`, `/api/marketplace`, `/api/trades`, `/api/prices`, `/api/villages` | **SERVICE SIDECAR**. Exact checkout is built and booted; Baen consumes its public read API through `brunnfeld_sidecar.py`. Mutating Brunnfeld endpoints are intentionally not exposed as Baen canonical actions. | **IMPLEMENTED / CI-PROVEN** |
| Unknown Horizons | `af9c8ef5c7f6cf9ec0b8c9e7d172c555f2793615` | Full GPL Python game; production classes are real Python objects but normal `horizons.world` bootstrap pulls in FIFE | **SEPARATE PRODUCT PROCESS**. Exact checkout is verified; a child Python process loads the exact upstream `ProductionLine` source file and its real `horizons.constants`, returning JSON to Baen. No production logic is copied into the MIT package. | **IMPLEMENTED; product CI must be green before this row is called proven** |
| Veloren | `e633eb8ca15ae97bb5ef5a039fcf6844e96ad704` | GPL Rust workspace; economy is part of library crate `veloren-world`; `site::economy::simulate_economy(&mut Index)` is public, `Site::economy_mut()` is public, but core `Economy` fields are private and `Index::new` loads Veloren asset manifests | **PINNED RUST SIDECAR / FORK ADAPTER**, not Python transcription. A real adapter must link the exact `veloren-world` crate, construct/translate valid Veloren world/site state, execute `simulate_economy`, and export results. Until that compiles and executes in CI, local `allocate_export_after_local_need` is only a compatibility adaptation. | **NOT YET PRODUCT-INTEGRATED** |
| FreeCol | `0a9e3cce950471fa67ae390d1a2fdf179e732092` | GPL Java/Ant full game. Inspected economic classes (`ProductionInfo`, `BuildingProductionCalculator`, `MarketWas`) live inside the game model rather than a standalone HTTP/library package designed for foreign state injection | **JVM SIDECAR / PRODUCT HARNESS** is the next viable route. It must build/run the exact FreeCol revision and drive real FreeCol model objects; copying formulas into Python does not count. | **NOT YET PRODUCT-INTEGRATED** |
| OpenTTD | `1aca0b60a8024f295e1d0ad2a3407b3dac838099` | GPL native C++ game. `DeliverGoods` and industry-production logic are internal game functions; OpenTTD supports dedicated-server operation, but no economic-library API has yet been established for Baen state injection | **HEADLESS PRODUCT / NATIVE SIDECAR OR FORK ADAPTER**. A real integration must execute the pinned OpenTTD product or a thin linked adapter against it and expose delivery/economy results. Local `settle_delivery` remains only a compatibility adaptation until that exists. | **NOT YET PRODUCT-INTEGRATED** |

## Implemented direct-product files

- `src/baen_economy/mesa_runtime.py`
- `src/baen_economy/brunnfeld_sidecar.py`
- `tools/run_brunnfeld_sidecar.py`
- `src/baen_economy/unknown_horizons_product.py`
- `tools/prepare_unknown_horizons_product.py`
- `tests/test_mesa_product_runtime.py`
- `tests/test_brunnfeld_sidecar.py`
- `tests/test_unknown_horizons_product.py`
- `.github/workflows/ci.yml`

## Compatibility adapters are not products

`src/baen_economy/upstream_adaptations.py` contains independently implemented economic invariants used while a full product boundary is absent or while preserving an existing Baen execution contract. It is **not evidence that Veloren, FreeCol, OpenTTD, Mesa, Brunnfeld, or Unknown Horizons have been integrated as products**.

Where a direct product integration now exists (Mesa, Brunnfeld, Unknown Horizons), new product-level work should use that boundary first. Compatibility helpers may remain for stable Baen APIs and cross-checks, but must not be described as the upstream product itself.

## Canon boundary

All direct-product execution is preview/research infrastructure until Baen source-to-product mappings and coverage are explicitly accepted. These integrations do not by themselves:

- write Notion;
- post to the canonical ledger;
- advance campaign time;
- run a canonical month;
- turn upstream default values into campaign facts.
