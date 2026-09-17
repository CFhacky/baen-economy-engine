# Third-Party Sources and Adoption Register

This register is an engineering record, not legal advice. No game asset, data
table, recipe, balance constant, lore, or artwork is imported merely because its
repository is open source.

| Upstream | Pin | License | MVP use |
|---|---|---|---|
| [Brunnfeld Agentic World](https://github.com/marcopatzelt/brunnfeld-agentic-world) | `e0656ca01630333e26c622ffd4ba4c973b79eebe` | MIT | Available-to-promise inventory calculation, adapted and attributed below |
| [Veloren](https://github.com/veloren/veloren) | `e5cfbb3a2b41d785da7a70baccf62c3e59ec2121` | GPL-3.0-or-later | Concepts only; no code or data copied |
| [Unknown Horizons](https://github.com/unknown-horizons/unknown-horizons) | `af9c8ef5c7f6cf9ec0b8c9e7d172c555f2793615` | GPL-2.0-or-later | Concepts only; no code or data copied |
| [Beancount](https://github.com/beancount/beancount) | release `3.2.3`, commit `eeda2aa2a3204ffb980dab11220b2abde5e80b38` | GPL-2.0-only | Optional external CLI validator/export target; not imported |
| [Mesa](https://github.com/mesa/mesa) | `v3.5.1`, commit `e733e8ecb2a162a552c815205da9503d1ed7ce16` | Apache-2.0 | Deferred optional agent-model adapter; not an MVP dependency |

## Adopted component

- Upstream file: [`src/inventory.ts`](https://github.com/marcopatzelt/brunnfeld-agentic-world/blob/e0656ca01630333e26c622ffd4ba4c973b79eebe/src/inventory.ts),
  function `getInventoryQty`.
- Supporting field: [`InventoryItem.reserved`](https://github.com/marcopatzelt/brunnfeld-agentic-world/blob/e0656ca01630333e26c622ffd4ba4c973b79eebe/src/types.ts).
- Local adaptations: `available_quantity` and reservation enforcement in
  `src/baen_economy/stockflow.py`, plus `_available_quantity` in
  `src/baen_economy/whole_economy.py`.
- Preserved behavior: available quantity is `max(0, on_hand - reserved)` and a
  missing item has zero availability.
- Deliberately stricter local rule: negative reservations and reservations above
  on-hand quantity are rejected instead of merely hidden by the zero floor.
- Acceptance tests: `test_available_to_promise_excludes_reserved_stock` and
  `test_reserved_stock_cannot_be_double_spent`.
- Whole-economy application: pledged quantities are excluded from collateral
  availability, recipe inputs, own consumption, local sale, route dispatch, and
  price-relevant opening supply; bank-seized inventory is also excluded from
  price-relevant market supply.

The complete upstream MIT notice is retained in `THIRD_PARTY_NOTICES.md` and is
configured as a packaged license file for built distributions.

## Conceptual influence only

Veloren and Unknown Horizons informed the separation of stocks, recipes,
production constraints, sites, transport, and market behavior. The implementation
in `src/baen_economy/stockflow.py` was independently specified for this project;
no GPL code or data is present.

## External-process boundary

Beancount is not imported as a Python library. The engine emits a plain-text
representation that a separately installed `bean-check` command may validate.
Failure of that external check will block acceptance but cannot rewrite engine or
campaign state.

## Deferred Mesa use

Mesa would be useful later for individual merchant choices, migration, guild
competition, depositor behavior, and Monte Carlo policy experiments. Ring 1 uses
aggregate conserved stock-flow instead; adding autonomous agents now would not
resolve the missing opening facts.

## Gate 1 dependency decision

The Registry importer, SQLite sidecar, business resolver, and banking sandbox use
only the Python standard library and the existing local engine. No additional
upstream was copied or bundled: Mesa requires Python 3.12 and a large numerical
stack without resolving missing campaign facts; Beancount remains an optional
GPL external validator; and the GPL simulation games remain concept-only. The
compatible Brunnfeld MIT available-to-promise adaptation above remains the only
incorporated third-party code component.
