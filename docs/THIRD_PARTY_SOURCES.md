# Third-Party Sources and Adoption Register

This register is an engineering record, not legal advice. No game asset, data
table, recipe, balance constant, lore, or artwork is imported merely because its
repository is open source. GPL projects below are behavior references only: the
Baen implementation is independently written and no GPL source is transplanted.

| Upstream | Inspected pin | License | Engine use |
|---|---|---|---|
| [Brunnfeld Agentic World](https://github.com/marcopatzelt/brunnfeld-agentic-world) | `e0656ca01630333e26c622ffd4ba4c973b79eebe` | MIT | Available-to-promise reservation behavior; local validation is stricter |
| [Veloren](https://github.com/veloren/veloren) | `e633eb8ca15ae97bb5ef5a039fcf6844e96ad704` | GPL-3.0-or-later | Behavior adaptation: internal demand is protected before external trade allocation |
| [Unknown Horizons](https://github.com/unknown-horizons/unknown-horizons) | `af9c8ef5c7f6cf9ec0b8c9e7d172c555f2793615` | GPL-2.0-or-later | Behavior adaptation: production-chain output is constrained by the bottleneck |
| [FreeCol](https://github.com/FreeCol/freecol) | `0a9e3cce950471fa67ae390d1a2fdf179e732092` | GPL-2.0-or-later | Behavior adaptation: maximum production is reported separately from current feasible/actual production |
| [OpenTTD](https://github.com/OpenTTD/OpenTTD) | `1aca0b60a8024f295e1d0ad2a3407b3dac838099` | GPL-2.0 with repository exceptions/notices | Behavior adaptation: final delivery accounts for accepted cargo, then exposes subsidy as a separate adjustment |
| [Mesa](https://github.com/mesa/mesa) | `20841b12559ef920dd4c8263a09fe75ceac7250c` | Apache-2.0 | Behavior adaptation: explicit scenario time and deterministic due-event ordering; no Mesa runtime dependency |
| [Beancount](https://github.com/beancount/beancount) | release `3.2.3`, commit `eeda2aa2a3204ffb980dab11220b2abde5e80b38` | GPL-2.0-only | Optional external CLI validator/export target; not imported |

## Brunnfeld: reservation / available-to-promise

- Inspected file: [`src/inventory.ts`](https://github.com/marcopatzelt/brunnfeld-agentic-world/blob/e0656ca01630333e26c622ffd4ba4c973b79eebe/src/inventory.ts), function `getInventoryQty`.
- Supporting field: [`InventoryItem.reserved`](https://github.com/marcopatzelt/brunnfeld-agentic-world/blob/e0656ca01630333e26c622ffd4ba4c973b79eebe/src/types.ts).
- Existing local adaptations: `available_quantity` and reservation enforcement in `src/baen_economy/stockflow.py`, plus `_available_quantity` in `src/baen_economy/whole_economy.py`.
- Preserved behavior: available quantity is `max(0, on_hand - reserved)` and a missing item has zero availability.
- Stricter Baen rule: negative reservations and reservations above on-hand are rejected rather than silently repaired.
- The complete upstream MIT notice is retained in `THIRD_PARTY_NOTICES.md` and configured as a packaged license file.

## Veloren: local demand before trade

- Inspected file: [`world/src/site/economy/mod.rs`](https://github.com/veloren/veloren/blob/e633eb8ca15ae97bb5ef5a039fcf6844e96ad704/world/src/site/economy/mod.rs), particularly `trade_at_site`.
- Observed behavior: profession demand and universal demand are calculated first; external orders are supplied only from stock above that internal demand.
- Local implementation: `allocate_export_after_local_need` in `src/baen_economy/upstream_adaptations.py`.
- Baen addition: existing reservations are deducted before local demand, the local shortfall is reported explicitly, and route capacity remains an independent cap.
- No Veloren balance constants, goods, labor coefficients, or GPL source are copied.

## Unknown Horizons + FreeCol: bottleneck capacity and actual/max distinction

- Unknown Horizons inspected file: [`horizons/ai/aiplayer/productionchain.py`](https://github.com/unknown-horizons/unknown-horizons/blob/af9c8ef5c7f6cf9ec0b8c9e7d172c555f2793615/horizons/ai/aiplayer/productionchain.py), `ProductionChain._get_chain`, `reserve`, and `get_final_production_level`.
- FreeCol inspected file: [`ProductionInfo.java`](https://github.com/FreeCol/freecol/blob/0a9e3cce950471fa67ae390d1a2fdf179e732092/src/net/sf/freecol/common/model/ProductionInfo.java), which stores production separately from maximum production and exposes production deficits.
- Local implementation: `production_capacity` and `ProductionCapacity` in `src/baen_economy/upstream_adaptations.py`.
- `maximum_batches` is the configured/labor capacity with unlimited material input; `feasible_batches` additionally applies available input bottlenecks. Reserved material is unavailable. Limiting input IDs remain visible.
- No Unknown Horizons or FreeCol recipes, production multipliers, building data, or GPL source are copied.

## OpenTTD: delivery receipt boundary

- Inspected file: [`src/economy.cpp`](https://github.com/OpenTTD/OpenTTD/blob/1aca0b60a8024f295e1d0ad2a3407b3dac838099/src/economy.cpp), `DeliverGoods` and `TriggerIndustryProduction`.
- Observed behavior: accepted cargo is distinct from cargo offered for delivery; company/town statistics and base transport income use accepted cargo; subsidy is applied afterward.
- Local implementation: `settle_delivery` and `DeliverySettlement` in `src/baen_economy/upstream_adaptations.py`.
- Baen does not import OpenTTD's distance/time income curve or subsidy multipliers. Unit value and subsidy multiplier must come from campaign/scenario authority and are recorded separately.

## Mesa: explicit deterministic scenario time

- Inspected file: [`mesa/model.py`](https://github.com/mesa/mesa/blob/20841b12559ef920dd4c8263a09fe75ceac7250c/mesa/model.py), `Model.__init__`, `_wrapped_step`, and `_advance_time`.
- Observed behavior: model time is explicit, scheduled events are processed up to a requested time boundary, and model randomness is scenario-owned/seeded.
- Local implementation: `ScheduledEconomicEvent` and `events_due` in `src/baen_economy/upstream_adaptations.py`.
- The adapter computes deterministic due order only. It does not itself advance campaign time; the existing authority/event system still controls whether a scenario or canonical clock may move.
- No Mesa dependency or NumPy dependency is added.

## Executable acceptance tests

`tests/test_upstream_adaptations.py` proves the adopted behavior at the Baen boundary:

- local demand and reservations are protected before export;
- shortage is surfaced instead of disguised by export;
- export remains route-capacity constrained;
- production reports maximum and bottleneck-feasible capacity separately;
- reserved material constrains current production feasibility;
- delivery revenue is based on accepted cargo only and subsidy is separately visible;
- deterministic events are ordered by explicit scenario time/priority/ID;
- invalid over-reservation, over-acceptance, duplicate event IDs and backward time fail closed.

These tests run inside the standalone repository CI. They are engine code, not a conceptual bibliography.

## External-process boundary

Beancount is not imported as a Python library. The engine emits a plain-text
representation that a separately installed `bean-check` command may validate.
Failure of that external check will block acceptance but cannot rewrite engine or
campaign state.

## What is not imported

No upstream project supplies Baen's starting population, monetary reserve ratio,
wages, taxes, material yields, recipe coefficients, transport loss rates, demand
elasticities, migration rules, or campaign-event probabilities. Those remain
source/canon inputs or explicitly unresolved assumptions. The public repositories
supply inspected implementation patterns; they do not become authority over the
campaign.
