# Programmes + employment ingest — 19 Sep 2026 (second desk)

Engine branch: `codex/reconcile-standalone-authority-20260917`
Campaign boundary: **Day 7 Hammer 1495 DR**. No month rolled. No Notion write. PR #1 stays open.
Registry read: **one** SQL pass over `collection://3c5f887a-4219-4ae6-a18a-82cf2d1841db`, all 90 rows, full property set.
Skill authority read first: `CFhacky/campaign-development-vault` `.claude-plugin/marketplace.json` → `skills/empire-operations-engine/SKILL.md` Step 0.

## 1. facilities.csv — verified, not rewritten

All 90 rows checked cell-by-cell against the live registry properties (Employees, Monthly Revenue, Monthly Cost, Capital Invested, Status, Sector, City, Neglect Status). **Zero drift.** No edits made.

The previous desk's note that Waterdeep Warborn Monthly Revenue reads `0` is now stale: the live property is **3,000,000** and `facilities.csv` already carries it. The card still says capacity 100–150 frames — that band conflict stays open, below.

## 2. employment.csv — 19 rows → 90 rows

One row per registry facility. `wage_rate` and `wage_state` left blank on every row — no card states a wage, and the Neverwinter Warborn 8,900 wages figure in the old implementation plan was **not** written over the 20,000 cost box.

| | count |
|---|---:|
| rows | 90 |
| headcount_state = SOURCE | 80 |
| headcount_state = UNKNOWN (card carries no Employees value) | 10 |
| wage_rate populated | 0 |

New `consolidation` column, so double-counting is visible rather than silent:

- `PARENT_ROLLUP` (1) — `emp:ncf-parent`. **85 = 35 + 30 + 12 + 8 exactly.** Headcount reconciles bottom-up. Revenue does not: branches sum 23,250 against parent 22,000. Parent wins on revenue; branches stay historical.
- `CHILD_OF_ROLLUP` (4) — the four NCF branches. Inside the 85.
- `ROLLUP_AMBIGUOUS` (2) — Thorn & Silver (10) and Verification Services (5). Both name NCF Luskan as Parent Entity. Neither card says whether those 15 sit inside Luskan's 30. Not resolved.
- `UNCONFIRMED_DO_NOT_BOOK` (3) — Gold Lending House, Lobster King, Waterdeep Information Brokerage. Carried for visibility only.
- `NOT_A_PAYROLL` (3) — Bloodaxe Legion (10,000 roster against 150,000/mo), Devil Academy (2,000 against a 2,000/mo box), Zariel Warborn Contract (contract card, Employees 0; delivery headcount lives on the two plants).
- `EXTERNAL_PARENT` (1) — Dock Ward Security Corp, Parent Entity Peri Ops.
- `SUPERSEDED` (1) — the older Guardian's Gate Settlement variant.
- `STANDALONE` (75).

The 10 UNKNOWN-headcount rows are Arterial Road Crystal Network, Crownsite Canal Property BG, Crystal Gardens, Neverwinter Wood Canal, Orchard Chapel, Sea Gate Harbor Authority, Sea Gate Shipyard, Seven Spires Estate, SSAMT, Thundertree Waystation. Empty stays empty. Unknown is not zero.

## 3. programmes.csv — new file, 13 rows

Every row carries a page URL or a ratified recovery artifact. No programme invented to fill a shape.

| programme_id | status | state_origin | money on the row |
|---|---|---|---|
| `prog:warborn-line-a` | ACTIVE | SOURCE | none — see note |
| `prog:warborn-line-b` | ACTIVE_CATALOG | SOURCE | UNRECONCILED |
| `prog:burning-gate` | R&D_PHASE | SOURCE | 800,000 capital; 0/0 |
| `prog:nafnfestr-wyrmhelm` | OPERATIONAL | SOURCE | 150,000 capital; 0 / 2,000 |
| `prog:promethean-husteem` | ACTIVE | SOURCE | 1,140/mo |
| `prog:promethean-rosznar` | ACTIVE | SOURCE | 2,760/mo |
| `prog:tissage-stelmane` | IN_PROGRESS | SOURCE | ~25,000/mo (APPROX_SOURCE) |
| `prog:tissage-protection-line` | ACTIVE | SOURCE | none |
| `prog:tissage-amnian-collection` | IN_DEVELOPMENT | SOURCE | none |
| `prog:stonefire-armor-plate` | UNDER_CONSTRUCTION | SOURCE | 42,700 capital; 1,479 / 1,909 |
| `prog:snowfall-dock-works` | FORMATION | SOURCE | 30,000 staged; 0/0 |
| `prog:heavy-machinery` | ADOPTED | USER_RULED | 237,500 envelope; 38,500/mo |
| `prog:light-vehicle` | NAMED | UNKNOWN | none |

Rules held on these rows:

- Line A and Line B are separate books and must not re-merge on registry cards. Line A: Legionnaire sale 30,000 / build 6,000 / **keep 4,000**; Solar Guard sale 100,000 / build 20,000 / keep 80,000. First pile invoice 152,100,000, keep 21,680,000. Line B prestige patterns (Storm Lord / Tactical / Silent Storm) price at 150,000 / 400,000 / 200,000+ and are unreconciled with the Line A sheet — left unreconciled on purpose.
- `prog:warborn-line-a` carries **no** monthly revenue cell. The registry Zariel card's 360,000 is Neverwinter invoices only — not the Waterdeep band, not the 6,440,000 network target.
- Burning Gate 30, Wyrmhelm 15, Stonefire 67 are the *same* headcounts as their employment rows. Noted on each row so a consolidator cannot add them twice.
- `prog:heavy-machinery` is `USER_RULED`, not SOURCE. The 237,500 historical envelope is not a Day-7 debit and not an NCF loan. Its 1,100 gp/month wage total sits inside the equipment allowances and must not be added again.
- `prog:snowfall-dock-works` is resolved *forward* to 1 Eleint 1495 without the live clock moving. Not Day-7 operating revenue.
- Shi'van-clock rows (`SHIVAN_DAY_500`, `SHIVAN`) must not be added onto Arik's Hammer 1495 month.

## 4. Conflicts left visible (unchanged plus one new)

1. Silversheen parent text **NCF 30 / Gauntlgrym 50** vs `ownership.csv` **NCF 60 / Gauntlgrym 40**. Still live on the card. No winner picked.
2. Waterdeep Warborn revenue cell 3,000,000 floor vs hall text 100–150 frame band (high end 4,500,000 at sale; 400,000–600,000 at keep).
3. Zariel registry Monthly Revenue 360,000 = Neverwinter only.
4. NCF parent 22,000 vs four branch rows summing 23,250. Parent wins.
5. **NEW** — Tissage card states a Stelmane commission "~25K/mo contract uplift" while the same card's Monthly Revenue cell reads 28,000 total. Whether the uplift is inside that 28,000 or on top of it is not stated. Recorded as `APPROX_SOURCE`, not resolved.
6. **NEW** — Thorn & Silver (10) and Verification Services (5) both name NCF Luskan as parent; Luskan's own card says 30. Containment unstated.

## 5. Referential integrity

`actors.csv` 35, `relationships.csv` 46, `accounts.csv` 11, `employment.csv` 90, `ownership.csv` 14, `loans.csv` 3, `contracts.csv` 6, `facilities.csv` 90, `programmes.csv` 13. Every `employment.facility_id`, `programmes.host_facility_id` and `programmes.parent_actor_id` resolves. **Zero dangling references.**

## 6. Named but deliberately not written

- **Hall Program** — the handoff flagged it "if sourced". Nothing in the persisted evidence or the registry properties names a programme by that title. The Waterdeep hall page body was not read this sitting. Not invented.
- **Threadbaum Model 1494-L "Whisper"** — it is its own registry entity, so it stays a facility row (`fac:whisper`), not a programme.
- Gauntlgrym 1,000/frame soul-bind — implementation plan still says negotiating.

## 7. Still not done

- Body-hash receipts for the 1,587 UNKNOWN retained-core records.
- NCF opening reserves / liabilities / equity — absent on the pages, not a question for the user to answer by inventing a sheet.
- Payroll and settlement ledgers — account shells only, per `CANON_RULING_WARBORN_PAYROLL_2026-09-19.md`.
- Wage rates — no card states one.
- `property_interests.csv`, `inventory_holdings.csv` — no source-backed rows found; not created empty.
- Monthly 3d6 phase — forbidden until a month crosses. Canonical month stays **CLOSED**.
