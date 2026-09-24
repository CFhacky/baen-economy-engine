# Economy Source Input Authority — 17 September 2026

This file is the source gate for the **actual** Baen Empire economy. The synthetic whole-economy scenario is sandbox-only.

## Rule

Actual execution may consume **USER-RULED**, **SOURCE-DERIVED**, or **UPSTREAM-ADOPTED** inputs. `scenario_assumption` / `MODEL-PROPOSED` values are forbidden from the actual run. Unknown stays unknown.

## Source-backed facts captured in this pass

- Current aggregate revenue: 245,000 gp/month high-confidence historical Arik-side; 280,000–320,000 gp/month medium-confidence realistic current band.
- Current aggregate recurring profit: about 75,000–90,000 gp/month, medium confidence.
- NCF active loan portfolio: 2.3M gp.
- Current liquid cash: **unknown**; the stale 800K gp reserve figure is forbidden.
- Shimmerdeep protected liquidity target: 450K gp net settled (about 400K current gap + 50K buffer).
- Arterial network: 150 staff; 22,000 gp/month revenue; 19,360 gp/month cost; source-backed **approximate** complete-route distances for NW–Luskan (~120), NW–Gauntlgrym (~80), NW–Mirabar (~150), NW–Waterdeep (~300), Forgedeep–Guardian's Gate (~40). Freight capacity/loss remains unknown. Suzail/Baldur's Gate extensions are incomplete and are not treated as current operating routes.
- Brickworks: 30 staff; 75,000 bricks/month; 3,333 gp/month revenue; 2,233 gp/month cost; 21K annual wages.
- Neverwinter Clay Quarries: 12 staff; 2,000 tons/month; 1,500 gp/month cost; internal transfer.
- Agricultural Shelter Zones: 8 staff; 1,500 gp/month revenue; 1,050 gp/month cost. Physical crop volume is unknown.
- Blacklake Aquaculture: 15 staff; 7,500 gp/month revenue; 5,850 gp/month cost. Species/volume unconfirmed.
- Food-sector financial aggregate: aquaculture network 55 staff / 25,000 gp/month plus shelters = 63 staff / 26,500 gp/month. Do not invent tonnage from these gp figures.
- NCF: 85 staff; 22,000 gp/month revenue; 2.3M gp active loans.
- Forgedeep City Development: 15,000 gp/month cost; 0 current municipal revenue.
- Neverwinter current population: **75,000** from the Locations DB Population property. The Overview heading ~80,000 is recorded as a conflict and is not selected.
- Waterdeep current population: **130,000** from the Locations DB Population property.
- Forgedeep current civilian population: **unknown**. LIVE STATE remains unanswered; Year-1 2,000 / decade 50,000 are targets, not current occupancy.

## Hard blockers, not fill-in-the-blank invitations

The current sources do **not** justify exact opening liquid cash, current reserve ratio, Forgedeep population, agricultural tonnage, Blacklake physical output, Brickworks clay-to-brick coefficient, arterial route capacities, opening market prices, empire-wide labour pools, class consumption baskets, migration rates, shock probabilities, market-demand quantities, most inventories, or most opening bank/account balances.

Those fields are therefore blockers for a source-grounded physical month. They are not zero and they are not permission to invent a convenient number.

Machine-readable authority is in `recovery/ECONOMY_SOURCE_INPUT_AUTHORITY_2026-09-17.json`.
