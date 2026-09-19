# Third-Party Sources and Adoption Register

This register is an engineering and license-boundary record, not legal advice. No game asset, data table, recipe, balance constant, lore, or artwork is imported merely because its repository is open source.

The current architecture distinguishes two things that were previously conflated:

1. **actual upstream-product execution**, where Baen invokes the pinned library/service/process/JVM/Rust/headless product through an isolated boundary; and
2. **Baen-local compatibility/cross-check adaptations**, which are independently implemented and are not evidence that the upstream product itself is running.

GPL product code is not copied into the MIT Baen Python package. Where a GPL product is executed, it remains in its own checkout/process/JVM/native/Rust boundary. The narrow Veloren injection seam is applied inside the pinned GPL checkout and is built/executed there.

| Upstream | Inspected pin | License | Product boundary now used |
|---|---|---|---|
| [Brunnfeld Agentic World](https://github.com/marcopatzelt/brunnfeld-agentic-world) | `e0656ca01630333e26c622ffd4ba4c973b79eebe` | MIT | Exact Node/TypeScript service sidecar, built and booted with its published HTTP API |
| [Veloren](https://github.com/veloren/veloren) | `e633eb8ca15ae97bb5ef5a039fcf6844e96ad704` | GPL-3.0-or-later | Exact `veloren-world` Rust product with a narrow GPL-side state-injection seam; real `Economy::tick` executes |
| [Unknown Horizons](https://github.com/unknown-horizons/unknown-horizons) | `af9c8ef5c7f6cf9ec0b8c9e7d172c555f2793615` | GPL-2.0-or-later | Exact pinned product source executed in a separate Python process; real `ProductionLine` runs |
| [FreeCol](https://github.com/FreeCol/freecol) | `0a9e3cce950471fa67ae390d1a2fdf179e732092` | GPL-2.0-or-later | Exact checkout builds `FreeCol.jar`; a child JVM executes real model classes |
| [OpenTTD](https://github.com/OpenTTD/OpenTTD) | `1aca0b60a8024f295e1d0ad2a3407b3dac838099` | GPL-2.0 with repository exceptions/notices | Exact dedicated server built/booted; external integration uses the documented admin network |
| [Mesa](https://github.com/mesa/mesa) | `20841b12559ef920dd4c8263a09fe75ceac7250c` | Apache-2.0 | Exact Git revision installed as an optional Python 3.12 dependency and executed directly |
| [Beancount](https://github.com/beancount/beancount) | release `3.2.3`, commit `eeda2aa2a3204ffb980dab11220b2abde5e80b38` | GPL-2.0-only | Optional external CLI validator/export target; not imported |

All six selected simulation products above passed their actual-product paths in GitHub Actions run **#115** (`35280499380`) at Baen code head `c8d5830745f709838a3effe9ac9a4e588cc5f86f`.

## Brunnfeld: service product + reservation / available-to-promise cross-check

- Product boundary: exact checkout is built and booted through `npm run server`; Baen reads Brunnfeld's published `/api/state`, `/api/economy`, `/api/marketplace`, `/api/trades`, `/api/prices`, and `/api/villages` endpoints through `src/baen_economy/brunnfeld_sidecar.py`.
- Inspected file: [`src/inventory.ts`](https://github.com/marcopatzelt/brunnfeld-agentic-world/blob/e0656ca01630333e26c622ffd4ba4c973b79eebe/src/inventory.ts), function `getInventoryQty`.
- Supporting field: [`InventoryItem.reserved`](https://github.com/marcopatzelt/brunnfeld-agentic-world/blob/e0656ca01630333e26c622ffd4ba4c973b79eebe/src/types.ts).
- Existing Baen compatibility behavior: `available_quantity` and reservation enforcement in `src/baen_economy/stockflow.py`, plus `_available_quantity` in `src/baen_economy/whole_economy.py`.
- Preserved invariant: available quantity is `max(0, on_hand - reserved)` and a missing item has zero availability.
- Stricter Baen rule: negative reservations and reservations above on-hand are rejected rather than silently repaired.
- The complete upstream MIT notice is retained in `THIRD_PARTY_NOTICES.md` and configured as a packaged license file.

## Veloren: real Rust economy + local-demand cross-check

- Product boundary: exact pinned `veloren-world` crate is built in the GPL checkout. A deliberately narrow patch exposes the population/stock injection Baen requires; simulation remains the upstream public `Economy::tick`, and output comes from Veloren's own `EconomyInfo` and `SitePrices`.
- Inspected file: [`world/src/site/economy/mod.rs`](https://github.com/veloren/veloren/blob/e633eb8ca15ae97bb5ef5a039fcf6844e96ad704/world/src/site/economy/mod.rs), including `Economy::tick`, `get_information`, `get_site_prices`, and trade behavior.
- Product bridge: `src/baen_economy/veloren_product.py` with checkout/build patching in `tools/prepare_veloren_product.py`.
- Baen compatibility cross-check: `allocate_export_after_local_need` in `src/baen_economy/upstream_adaptations.py`.
- No Veloren balance constants, goods tables, labor coefficients, or source implementation are copied into the MIT Python package.

## Unknown Horizons: real ProductionLine + bottleneck cross-check

- Product boundary: the exact pinned checkout is verified and a child Python process executes the actual upstream `ProductionLine` source file with its real `horizons.constants`. This avoids the normal `horizons.world` bootstrap that pulls FIFE without recreating the production class in Baen.
- Product bridge: `src/baen_economy/unknown_horizons_product.py` and `tools/prepare_unknown_horizons_product.py`.
- Additional inspected file: [`horizons/ai/aiplayer/productionchain.py`](https://github.com/unknown-horizons/unknown-horizons/blob/af9c8ef5c7f6cf9ec0b8c9e7d172c555f2793615/horizons/ai/aiplayer/productionchain.py), including `ProductionChain._get_chain`, `reserve`, and `get_final_production_level`.
- Baen compatibility cross-check: `production_capacity` / `ProductionCapacity` in `src/baen_economy/upstream_adaptations.py`.
- No Unknown Horizons recipes, building data, or GPL production implementation are copied into the MIT Python package.

## FreeCol: real JVM model + actual/max cross-check

- Product boundary: exact checkout is built with Ant into `FreeCol.jar`; a tiny temporary caller is compiled against that jar and executed in a child JVM.
- Product model classes: [`ProductionInfo.java`](https://github.com/FreeCol/freecol/blob/0a9e3cce950471fa67ae390d1a2fdf179e732092/src/net/sf/freecol/common/model/ProductionInfo.java), plus real `GoodsType` and `AbstractGoods` objects.
- Product bridge: `src/baen_economy/freecol_product.py` and `tools/prepare_freecol_product.py`.
- Baen compatibility cross-check: `production_capacity` / `ProductionCapacity` in `src/baen_economy/upstream_adaptations.py` keeps configured maximum capacity distinct from material-constrained feasible capacity.
- No FreeCol recipes, production multipliers, building data, or GPL model implementation are copied into Python.

## OpenTTD: real dedicated product / admin boundary

- Product boundary: the exact pinned OpenTTD revision is compiled as a dedicated server and booted headlessly. Baen connects through OpenTTD's documented admin network, which is explicitly intended for external applications.
- Admin protocol source/description: [`docs/admin_network.md`](https://github.com/OpenTTD/OpenTTD/blob/1aca0b60a8024f295e1d0ad2a3407b3dac838099/docs/admin_network.md), with packet definitions in [`src/network/core/tcp_admin.h`](https://github.com/OpenTTD/OpenTTD/blob/1aca0b60a8024f295e1d0ad2a3407b3dac838099/src/network/core/tcp_admin.h).
- Product bridge: `src/baen_economy/openttd_product.py`; exact build in `tools/prepare_openttd_product.py`; live server probe in `tools/probe_openttd_product.py`.
- Inspected internal economy reference: [`src/economy.cpp`](https://github.com/OpenTTD/OpenTTD/blob/1aca0b60a8024f295e1d0ad2a3407b3dac838099/src/economy.cpp), including `DeliverGoods` and `TriggerIndustryProduction`.
- Baen compatibility cross-check: `settle_delivery` / `DeliverySettlement` in `src/baen_economy/upstream_adaptations.py`.
- Baen does not copy OpenTTD's distance/time income curve or subsidy multipliers into the MIT package. Campaign/scenario values remain separately sourced.

## Mesa: direct Python library + deterministic-time cross-check

- Product boundary: the exact pinned Mesa commit is an optional Python 3.12 dependency and is imported/executed directly in `src/baen_economy/mesa_runtime.py`.
- Inspected file: [`mesa/model.py`](https://github.com/mesa/mesa/blob/20841b12559ef920dd4c8263a09fe75ceac7250c/mesa/model.py), including `Model.__init__`, model time/event scheduling, and RNG ownership.
- Baen uses Mesa's real `Model`, event scheduler/priority queue, RNG initialization, `run_until`, and `DataCollector` in the direct-product path.
- Baen compatibility cross-checks may still use `ScheduledEconomicEvent` / `events_due` in `src/baen_economy/upstream_adaptations.py` for stable local contracts, but those helpers are not Mesa.
- Mesa execution does not itself authorize campaign-time advancement.

## Compatibility acceptance tests

`tests/test_upstream_adaptations.py` proves Baen's independently implemented cross-check invariants:

- local demand and reservations are protected before export;
- shortage is surfaced instead of disguised by export;
- export remains route-capacity constrained;
- production reports maximum and bottleneck-feasible capacity separately;
- reserved material constrains current production feasibility;
- delivery revenue is based on accepted cargo only and subsidy is separately visible;
- deterministic events are ordered by explicit scenario time/priority/ID;
- invalid over-reservation, over-acceptance, duplicate event IDs, and backward time fail closed.

Those tests are useful compatibility contracts. They are not substitutes for the dedicated product jobs described above.

## External-process boundary

Beancount is not imported as a Python library. The engine emits a plain-text representation that a separately installed `bean-check` command may validate. Failure of that external check will block acceptance but cannot rewrite engine or campaign state.

## What is not imported or adopted by default

No upstream project supplies Baen's starting population, monetary reserve ratio, wages, taxes, material yields, recipe coefficients, transport loss rates, demand elasticities, migration rules, or campaign-event probabilities. Those remain source/canon inputs or explicitly unresolved assumptions.

Likewise, proving that an upstream runtime executes does not automatically adopt every upstream mechanic into Baen. Semantic adoption and source-to-product mapping remain separate, explicit, reviewable decisions.
