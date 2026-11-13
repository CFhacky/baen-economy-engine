# Upstream product integration authority

This document governs how the Baen Economy Engine uses the public simulation products Chad explicitly selected for investigation. It supersedes any wording that treats a small reimplementation of one upstream behavior as equivalent to using that upstream product.

## Rule

Use the **actual upstream product** whenever it exposes a viable library, service, process, plugin, or fork boundary. A Baen-local behavior adapter is acceptable only as a compatibility/cross-check layer or when an upstream product boundary genuinely cannot accept the required state, and it must be labeled as an adaptation rather than a product integration.

No upstream product supplies campaign canon. Population, money, recipes, wages, taxes, yields, reserve ratios, travel losses, and campaign event probabilities still require Baen source authority. Product execution is not canonical adoption.

## Current product matrix

| Upstream | Pinned revision | Product boundary | Baen treatment | Status |
|---|---|---|---|---|
| Mesa | `20841b12559ef920dd4c8263a09fe75ceac7250c` (`4.0.0a0`) | Python library: `mesa.Model`, event queue/schedules, RNG ownership, `DataCollector` | **DIRECT LIBRARY**. Installed from the exact Git commit on Python 3.12 and executed by `mesa_runtime.py`. Python 3.11 remains a supported Baen base runtime without pretending a local scheduler is Mesa. | **IMPLEMENTED / CI-PROVEN** |
| Brunnfeld Agentic World | `e0656ca01630333e26c622ffd4ba4c973b79eebe` | Node/TypeScript product with `npm run server`; published HTTP/SSE API includes `/api/state`, `/api/economy`, `/api/marketplace`, `/api/trades`, `/api/prices`, `/api/villages` | **SERVICE SIDECAR**. Exact checkout is built and booted; Baen consumes its public read API through `brunnfeld_sidecar.py`. Mutating Brunnfeld endpoints are intentionally not exposed as Baen canonical actions. | **IMPLEMENTED / CI-PROVEN** |
| Unknown Horizons | `af9c8ef5c7f6cf9ec0b8c9e7d172c555f2793615` | Full GPL Python game; production classes are real Python objects but normal `horizons.world` bootstrap pulls in FIFE | **SEPARATE PRODUCT PROCESS**. Exact checkout is verified; a child Python process loads the exact upstream `ProductionLine` source file and its real `horizons.constants`, returning JSON to Baen. No production logic is copied into the MIT package. | **IMPLEMENTED / CI-PROVEN** |
| FreeCol | `0a9e3cce950471fa67ae390d1a2fdf179e732092` | GPL Java/Ant full game; builds `FreeCol.jar`; `ProductionInfo`, `GoodsType`, and `AbstractGoods` are public model classes | **JVM PRODUCT HARNESS**. The exact checkout is built with Ant, a tiny temporary caller is compiled against the resulting `FreeCol.jar`, and Baen executes FreeCol's real model objects in a child JVM. No FreeCol production logic is copied into Python. | **IMPLEMENTED / CI-PROVEN** |
| Veloren | `e633eb8ca15ae97bb5ef5a039fcf6844e96ad704` | GPL Rust workspace; economy lives in `veloren-world`; `Economy::tick` is public but the economic state needed for Baen injection is private | **PINNED GPL-SIDE RUST ADAPTER**. The exact checkout receives a deliberately narrow state-injection seam inside the GPL tree; the actual simulation remains Veloren's `Economy::tick`, and Baen reads Veloren's own `EconomyInfo` and `SitePrices` output. | **IMPLEMENTED / CI-PROVEN** |
| OpenTTD | `1aca0b60a8024f295e1d0ad2a3407b3dac838099` | GPL native C++ game with a dedicated-server product and documented admin network explicitly intended for external applications | **HEADLESS PRODUCT / ADMIN API**. CI builds the exact dedicated server, boots it, authenticates through the real admin protocol, and polls live product state/economy packets. Baen does not copy `DeliverGoods` into Python as the product integration. | **IMPLEMENTED / CI-PROVEN** |

All six runtime boundaries above were reconfirmed successfully in GitHub Actions run **#254** (`35304371375`) at code head `52f6fb05605e10f5a528eb496501051646411dbd`. The older #115 run remains the historical baseline recorded in the recovery handoff.

## Implemented direct-product files

- `src/baen_economy/mesa_runtime.py`
- `src/baen_economy/brunnfeld_sidecar.py`
- `tools/run_brunnfeld_sidecar.py`
- `src/baen_economy/unknown_horizons_product.py`
- `tools/prepare_unknown_horizons_product.py`
- `src/baen_economy/freecol_product.py`
- `tools/prepare_freecol_product.py`
- `src/baen_economy/veloren_product.py`
- `tools/prepare_veloren_product.py`
- `src/baen_economy/openttd_product.py`
- `tools/prepare_openttd_product.py`
- `tools/probe_openttd_product.py`
- `tests/test_mesa_product_runtime.py`
- `tests/test_brunnfeld_sidecar.py`
- `tests/test_unknown_horizons_product.py`
- `tests/test_freecol_product.py`
- `tests/test_veloren_product.py`
- `tests/test_openttd_product.py`
- `.github/workflows/ci.yml`

## Product execution is not semantic adoption

A green product boundary means Baen can execute the pinned upstream product and obtain its output through the documented or deliberately isolated boundary above. It does **not** mean every mechanic, balance constant, state variable, or default from that product has been adopted into the Baen economy.

Source-to-product mapping remains a separate acceptance problem. Any consequential mapping must still be traceable to campaign/source authority or explicitly labeled as unresolved/model-proposed rather than silently inheriting an upstream default.

### Current Hammer-1495 semantic mapping

The actual source lane now exposes typed mappings for **finance/banking, infrastructure/logistics, population/labour, construction/capital, and military/standing contracts** through `empire_source_products.py`. Record-level coverage is tracked as a separate overlay; it does not rewrite the dated census snapshot and it does not promote any record to SIMULATED.

A concrete OpenTTD candidate now exists: the source authority records approximately **1.5 tons/month of Warborn precision tool steel from the Gauntlgrym partnership**, while the Northern Industrial Yards source records the **85-mile / 2-day Gauntlgrym-Forgedeep freight corridor**. Pinned OpenTTD defines cargo id **9 / `CT_STEEL`** in tons. That semantic join is persisted in `recovery/SOURCE_SEMANTIC_EVIDENCE_2026-09-18.json`.

OpenTTD remains **MAPPED_BLOCKED** on the actual lane. The pinned product income function accepts integer cargo pieces and OpenTTD tile distance; there is no USER-RULED or SOURCE-DERIVED campaign-mile→tile mapping and no adopted rule for converting **1.5 source tons** to integer cargo pieces. The engine therefore refuses to call the product income function rather than silently treating miles as tiles or rounding the shipment.

The semantic coverage overlay currently maps **10 source records**. Nine were verified current members of the live Business Registry or Locations collections and therefore move from census **UNKNOWN** to **SOURCE_MAPPED** in the overlay (**1,616 → 1,607**). The tenth, `Empire Financial State — Current Reference`, retains its explicit **MISSING_DATA** coverage. **SIMULATED remains 0**.

## Compatibility adapters are not products

`src/baen_economy/upstream_adaptations.py` contains independently implemented economic invariants used to preserve existing Baen contracts and to cross-check product behavior. It is **not evidence that any upstream product has been integrated**.

Where a direct product boundary exists for Mesa, Brunnfeld, Unknown Horizons, FreeCol, Veloren, or OpenTTD, product-level work must use that boundary first. Compatibility helpers may remain for stable Baen APIs and cross-checks, but must not be described as the upstream product itself.

## Canon boundary

All upstream-product execution remains preview/research infrastructure until Baen source-to-product mappings and coverage are explicitly accepted. These integrations do not by themselves:

- write Notion;
- post to the canonical ledger;
- advance campaign time;
- run a canonical month;
- turn upstream default values into campaign facts.
