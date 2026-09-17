# Source Scenario Contracts

These contracts state what a fixture may assert. They do not advance a campaign
clock and do not convert a forecast into current canon.

## Snowfall Hearthworks

Sources:

- [Snowfall Hearthworks registry page](https://app.notion.com/p/3c2e821484b081f888a6e1169f9a4df4)
- [Northern Crown Financial](https://app.notion.com/p/2fbe821484b0816ab0b8e7e7ed41fe29)

Source-reported anchor: 7 Hammer 1495 DR on the Snowfall page's Arik-referenced
clock. The fixture uses a scenario-local source lane; mapping it to the surface
economy remains blocked by CAN-001.

- Status is Planning; current revenue and cost are zero.
- Veldrin owns 75%; NCF owns 25% ordinary equity.
- The separate NCF facility limit is 30,000 gp at 8% annual interest.
- The facility is approved but undrawn; at that anchor the source records no NCF
  revenue or active-loan-total change from the facility. This is not an exhaustive
  assertion that every transaction is absent.
- A 5,000 gp completion guarantee is held/restricted, not spendable operating cash.

The formation and opening sequence is `forward_resolved`, not current. Its seven
recorded rolls are `12, 15, 13, 6, 12, 11, 14`; recorded monthly progress totals
105%; formation begins 1 Alturiak and opening is 1 Eleint 1495 DR. The opening
month states 6,900 gp revenue and 6,250 gp operating cost. Under the explicitly
illustrative full-draw case, payment is 608.29 gp: 200 gp interest and 408.29 gp
principal, leaving 450 gp accounting profit after interest but only 41.71 gp cash
after the entire payment. Those two results must never be conflated.

Revenue, operating cost, operating profit before interest, the illustrative
payment, and the stated 41.71 gp remainder before dues or additional reserves are
source-imported. Interest allocation, principal allocation, accounting profit
after interest, and closing principal are explicitly marked `engine_derived`
arithmetic in the fixture.

Unresolved: draw schedule, construction-period interest, paid-in equity, and
custody/accounting treatment of the guarantee. The registry's 30,000 gp `Capital
Invested` property also conflicts semantically with the body's separately undrawn
30,000 gp facility and is not silently treated as paid-in cash.

**Naming invariant:** Snowfall is a heating-systems manufacturer. It is not the
food-relief operation.

## Operation Laden Table

Sources:

- [Operation Laden Table](https://app.notion.com/p/396e821484b0816c9dd3e88e17fc70f1)
- [Longsaddle settlement/economy source](https://app.notion.com/p/348e821484b081a68349ecdc1f0efef8)
- [Agricultural Shelter Zones registry row](https://app.notion.com/p/321e821484b081e09660eacd14973b2f)

Planning anchor: late Kythorn 1495 DR. The fixture retains this in a
scenario-local source lane; mapping it to the opening economy timeline remains
blocked by CAN-001.

- Source status is Active; its phase is assembly and instruction.
- Operation Laden Table itself records the trigger as three of eight agricultural
  shelter zones destroyed. The generic registry row above does not establish
  that Dawnwood-specific trigger.
- Longsaddle has approximately 11,000 mouths and is then a net food importer.
- The first local harvest window is Eleint–Marpenoth; meaningful export surplus
  cannot begin before the 1496 season.
- Grain target is 1,200–1,500 tons at 65,000–95,000 gp including transport.
- Meat/livestock target is 25,000–40,000 gp.
- Embassy and legations are approximately 30,000 gp capital plus 2,000 gp/month.
- Baen's borrowing target is 200,000–300,000 gp; proceeds create a liability and
  are never revenue.
- Departure is planned for early Flamerule; first grain movement for Eleasis.
- The source specifies one embassy Diplomacy check, three loan-syndication rolls,
  one grain Merchant check, one im'Dalat Hidden Lore check, and one d12
  complication roll. Their outcomes are unresolved. No procurement or financing
  transaction is pre-resolved by the cited plan; that is not a complete cash
  audit.

Unresolved: opening inventories, ration rates, seller surplus, route capacities,
travel time, spoilage, handling loss, prices, and all loan contract terms. A
preview may supply visibly labeled assumptions; an actual run must block.

## Northern Crown Financial consolidation

Source: [Northern Crown Financial](https://app.notion.com/p/2fbe821484b0816ab0b8e7e7ed41fe29)
and the four branch pages listed in `fixtures/canonical-import/ncf-consolidation.json`.

- Parent revenue is 22,000 gp/month.
- Four branches sum to 23,250 gp revenue, 12,170 gp cost, and 85 employees.
- Parent plus branches (45,250 gp) is always forbidden.
- Until adjudicated, both parent-summary and bottom-up branch views are reported
  as alternatives; neither is silently selected as the live book.
- Further Luskan subordinate rows may already be included in its branch result.

## Clock isolation

There is no single safe global campaign date. At minimum, Arik, Shi'van, and
Jörmun records occupy different clocks. Every event and opening value therefore
requires a `timeline_id` plus an ordered campaign date. A future-resolved event may
be replayed in its own preview but cannot activate in `actual` before its effective
date.

Clock sources:

- [Resume Router](https://app.notion.com/p/3c4e821484b08106ae12f50082ed43ff)
- [Arik exact resume card](https://app.notion.com/p/3c4e821484b081139b27d87512bc22d9)
- [District Economy](https://app.notion.com/p/37ee821484b0812bb758cf201d8fcb63)

The observed lanes are Arik at Day 7 Hammer 1495, Shi'van at 6 Mirtul 1494,
Jörmun around 1 Uktar 1498, and a separate Drazekh lane. The user's opening
**economic surface date** is therefore an explicit P0 ruling. As a fail-closed
engine policy pending CAN-001—not a quoted source mechanic—a PC's date in Hell
does not silently advance the surface economy.

## Liquidity and opening cash

Sources:

- [Empire Financial State](https://app.notion.com/p/34ce821484b081d7abb5f5d9cf153d72)
- [Cash Reconciliation](https://app.notion.com/p/34ce821484b081c08dd4c3122711cc8e)
- [Klauth liquidation](https://app.notion.com/p/3c4e821484b081abb02ef1390d4a53be)
- [Shimmerdeep](https://app.notion.com/p/34ce821484b081119fd4c41feef5634e)

Exact opening cash is indeterminate. The current control is an approximately
400,000 gp Shimmerdeep/Crown gap and a protected 450,000 gp net-settled target.
Only cleared settlement reduces it; hammer price and receivables are not cash.
Historical Klauth realization is asset conversion and cannot be booked again as
new operating income. Older 800,000 gp cash and -277,000 gp models are not safe
opening values.

## Monetary authority and Crown Advantage

Sources:

- [Current authority pointer](https://app.notion.com/p/3c2e821484b081c085eecc74c2bcb35b)
- [Superseded full body](https://app.notion.com/p/32ce821484b0814dbfebd60ac51ac338)
- [Crown Advantage](https://app.notion.com/p/35ee821484b08166bd87f0cf107b6579)
- [Reserve Expansion](https://app.notion.com/p/34ee821484b08106889fd4ba0ccd23b5)
- [Shimmerdeep Cradle](https://app.notion.com/p/34ce821484b081119fd4c41feef5634e)

The current pointer and superseded page refer back to one another, so traversal
order cannot establish authority. Sources also conflict between a Year-2 70%
backing statement and a Year-2 2.5:1 ratio. The latter arithmetically implies a
40% reserve fraction, but the source does not separately state “Year-2 40%.” A literal 25:1
"production-cost advantage" omits note liabilities and cannot create real goods
or labour. The engine therefore implements none of these claims until ruled.
