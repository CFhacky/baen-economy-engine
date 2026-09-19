# Economic Actor Model

## Purpose

The Baen Economy Engine needs a persistent economic identity layer between campaign sources and simulation/runtime products. Campaign sources describe people, institutions, businesses, contracts, assets, and relationships; simulation products require durable actors, accounts, balances, obligations, ownership, employment, inventory custody, and transactions.

This layer adds structure without pretending that every missing number was established in play.

The model is designed around three constraints:

1. **Campaign authority remains upstream.** Notion, reviewed source records, Registry records, contracts, ledgers, and user rulings remain the authority for campaign facts.
2. **Economic structure may exist before every quantity is known.** An account, employment relationship, ownership interest, or loan can exist while its opening balance or other numeric fields remain UNKNOWN.
3. **Generated state must never masquerade as source canon.** SOURCE, DERIVED, INITIALIZED, and UNKNOWN state origins remain explicit.

The first production slices are **Northern Crown Financial (NCF)** and **Institut Baen'und**.

---

## 1. Economic actors

An economic actor is any entity capable of owning assets, holding accounts, receiving or paying money, employing people, entering contracts, holding inventory, controlling funds, or owing obligations.

Supported actor types:

- PERSON
- HOUSEHOLD
- BUSINESS
- BANK
- TRUST
- ESTATE
- GUILD
- MILITARY_FORMATION
- GOVERNMENT
- RELIGIOUS_INSTITUTION
- RESEARCH_INSTITUTION
- SETTLEMENT
- OTHER_INSTITUTION

A campaign NPC and an economic actor are not the same record. The NPC remains the campaign identity; the economic actor is the finance/economy identity linked back by stable source ID.

Suggested identifier form:

```text
actor:npc:<stable-source-id>
actor:business:<registry-id>
actor:institution:<stable-id>
actor:household:<uuid>
actor:estate:<uuid>
```

Display names are mutable. Stable IDs are not.

---

## 2. Provenance and state origin

Existing provenance tags remain binding:

- USER-RULED
- SOURCE-DERIVED
- UPSTREAM-ADOPTED
- MODEL-PROPOSED
- UNRESOLVED

Economic records additionally carry a **state origin**:

- SOURCE — directly established campaign fact
- DERIVED — deterministic result of established facts plus an approved rule
- INITIALIZED — simulation-required state created under an approved initialization policy
- UNKNOWN — no lawful value currently exists

Example:

```yaml
account_id: acct:ncf:example
holder_actor_id: actor:npc:example
institution_actor_id: actor:institution:ncf
account_type: PAYROLL_CURRENT
status: ACTIVE
opening_balance:
  value: null
  state_origin: UNKNOWN
provenance: SOURCE-DERIVED
```

The account can therefore exist without inventing a balance.

---

## 3. Economic relevance tiers for NPCs

NPC review is already complete. Do not rediscover or rereview the 920-record corpus. Use the completed review artifacts to identify economically relevant actors.

- **E0 — no economic model required.** No relevant persistent economic participation.
- **E1 — income participant.** Employee, soldier, contractor, artisan, renter, stipend recipient, etc.
- **E2 — account/contract actor.** Bank customer, borrower, lender, leaseholder, merchant, landlord, officer with financial authority.
- **E3 — owner/operator.** Proprietor, shareholder, estate holder, workshop owner, significant transporter, major livestock owner.
- **E4 — systemically important.** Bank officers, treasury officers, major merchants, industrial controllers, trust controllers, infrastructure operators, major institutional administrators.

The tier is a modeling priority, not a social rank.

---

## 4. Core relationships

Economic relationships use a finite vocabulary:

- EMPLOYED_BY / EMPLOYS
- OWNS / CO_OWNS
- OPERATES / MANAGES
- BORROWS_FROM / LENDS_TO
- BANKS_WITH / DEPOSITOR_AT
- LEASES_FROM / LEASES_TO
- RENTS_FROM / RENTS_TO
- SUPPLIES / PURCHASES_FROM
- CONTRACTED_TO
- HOLDS_IN_TRUST / TRUSTEE_FOR / BENEFICIARY_OF
- AUTHORIZED_SIGNER
- CUSTODIAN_OF
- OWNS_INVENTORY
- TRANSPORTS_FOR
- OWES / IS_OWED_BY
- MEMBER_OF_HOUSEHOLD / DEPENDENT_OF / HEIR_TO

Each relationship stores its source evidence, effective status/date where known, provenance, and state origin.

---

## 5. Accounts

A person or institution can control multiple accounts. An actor is never synonymous with an account.

Initial account types:

- CURRENT
- SAVINGS
- PAYROLL
- BUSINESS_OPERATING
- BUSINESS_RESERVE
- ESCROW
- TRUST
- TREASURY
- LOAN
- LINE_OF_CREDIT
- MORTGAGE
- TRADE_CREDIT
- INVESTMENT
- CAPITAL
- BROKERAGE
- CUSTODIAL
- PETTY_CASH
- RESTRICTED_FUND
- RESEARCH_FUND
- OTHER

Account existence and account balance are separate facts.

---

## 6. Employment and payroll

Named workers resolve identity inside existing aggregate headcounts; they do not automatically increase those totals.

Required employment fields include:

```text
employment_id
employee_actor_id
employer_actor_id
site_id
role
status
compensation_amount
compensation_period
included_in_registry_headcount
payment_account_id
source_id
provenance
state_origin
```

If a 40-person source-backed workforce contains five named NPCs, the correct representation is five named + thirty-five anonymous, not forty + five.

Anonymous workforce pools remain valid first-class economic objects.

---

## 7. Ownership and control

Business, trust, institutional, and personal finances remain separate even where one actor controls several entities.

Ownership records distinguish:

- legal ownership
- beneficial ownership
- voting/control rights
- management authority
- distribution rights
- signatory authority
- custody

Unknown percentages remain UNKNOWN. A remembered range must not be collapsed into an invented midpoint.

Business profit remains business profit until a salary, dividend, owner draw, capital movement, or other explicit transfer moves it to a personal actor.

---

## 8. Loans and banking

Known borrowers become explicit loan objects. Named facilities contribute to the source-backed NCF portfolio total, while the remainder remains an unresolved aggregate.

Example:

```text
source-backed NCF active loans
- named source-backed facilities
= unresolved portfolio aggregate
```

The remainder may be mathematically DERIVED; its borrower identities must not be invented.

Loan records distinguish lender, borrower, principal, outstanding amount, rate, payment frequency, status, delinquency, collateral, and source evidence where available.

---

## 9. NCF institutional slice

NCF is the first finance-heavy implementation slice.

The slice should resolve, where source-backed:

- NCF as an institutional actor
- ownership/control structure
- officers and named employees
- employment relationships
- known borrowers and facilities
- known deposit/customer relationships
- trust relationships
- business/customer banking relationships
- account shells
- named loan receivables
- unresolved portfolio aggregates
- branch/institution authority
- authorized signers/managers
- maximum lawful bottom-up balance-sheet reconstruction

Do not promote old Eleint-1494 branch costs into Hammer 1495 current monthly cost. Do not infer deposits, reserves, liabilities, equity, or cash solely to force a balancing sheet.

---

## 10. Institut Baen'und institutional slice

Institut Baen'und is the first institution-heavy implementation slice.

Treat the Institut as a **RESEARCH_INSTITUTION**, not as a generic business unless a specific operation is source-backed as commercial.

The slice should resolve:

- Institut institutional actor
- leadership and administration
- named faculty, researchers, artificers, specialists, field personnel, and support staff
- known staff/faculty aggregates
- departments/divisions/programmes where source-backed
- laboratories, workshops, archives, field stations, controlled facilities, and other institutional assets
- procurement and supplier relationships
- payroll/employment relationships
- institutional customers/clients where the source establishes a real service, contract, patron, buyer, or external programme relationship
- internal cost centers and restricted/research funds
- banking relationship with NCF if actually established
- cross-links to Warborn/consciousness/artifact/field programmes where source-backed

The Institut must not be exploded into independent businesses merely because it contains multiple departments. Default treatment is one institution with cost centers/programmes until source evidence establishes separate legal/economic entities.

A named research subject, ally, student, or associated NPC is **not automatically a customer**. Customer/client classification requires evidence of an economic or contractual relationship.

---

## 11. Property and inventory

Physical goods need both ownership and custody.

An inventory record may distinguish:

```text
owner_actor_id
custodian_actor_id
location_id
warehouse_id
commodity_id
quantity
unit
acquisition_cost
market_value
provenance
state_origin
```

Production flow is not opening inventory. Revenue is not physical quantity.

---

## 12. Trusts, estates, treasury, and restricted funds

Trust property is separate from trustee property. Estates remain actors where deceased NPC assets/liabilities survive. Institutional funds distinguish owner, beneficiary, custodian, trustee, manager, and signatory.

For the Institut, restricted research funds and programme budgets should use institutional accounts/cost centers rather than being assigned to the personal wealth of the researcher who manages them.

---

## 13. Canonical structured state

The durable human-diffable state belongs under:

```text
data/canonical/
  actors.csv
  relationships.csv
  accounts.csv
  employment.csv
  ownership.csv
  loans.csv
  contracts.csv
  property_interests.csv
  inventory_holdings.csv
```

These tables are the durable structured authority once reviewed and accepted.

SQLite is a runtime build product from these tables. A binary SQLite database is not the sole Git authority.

Markdown profiles are generated views for selected important actors, not the primary data store.

---

## 14. Aggregate pools

Anonymous/unresolved pools are valid and necessary:

```text
borrowers:ncf:unresolved
depositors:ncf:unresolved
workforce:institut:unresolved
households:neverwinter:aggregate
```

As campaign detail identifies actors, named records can be carved out while the aggregate remainder shrinks. The aggregate must continue to reconcile to any source-backed total.

---

## 15. Acceptance rules

The actor layer must:

- preserve stable source IDs and provenance;
- tolerate UNKNOWN balances and quantities;
- never invent a balance to make an account exist;
- keep personal and institutional finances separate;
- keep named workers inside existing aggregate headcounts where appropriate;
- preserve source conflicts explicitly;
- reconcile named financial/physical quantities to source aggregates where possible;
- retain unresolved aggregate remainders rather than inventing identities;
- distinguish source facts, derived state, initialized state, and unknown state;
- perform no Notion writes as part of source enrichment;
- advance no campaign time;
- execute no canonical month.

The economic actor layer exists to add connective structure, not to launder missing information into canon.
