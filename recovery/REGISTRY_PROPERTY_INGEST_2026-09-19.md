# Registry property ingest — 19 Sep 2026

Source: Notion Business Registry `collection://3c5f887a-4219-4ae6-a18a-82cf2d1841db`  
Skill: `skills/empire-operations-engine/SKILL.md` Step 0  
Engine branch: `codex/reconcile-standalone-authority-20260917`  
Method: SQL query of live properties. Bodies not re-read for this file.

## What was written into Git

- `data/canonical/facilities.csv` — NCF parent+branches, Gold Lending House, Silversheen, Tissage card, Burning Gate, both Warborn plants, Zariel contract card
- `data/canonical/contracts.csv` — Line A Zariel only

## Step 0 snapshot from that query

Unconfirmed (do not book):
- Gold Lending House
- Lobster King Operations
- Waterdeep Information Brokerage

Neglected found in this filter:
- Arterial Road Crystal Network (Operational, no employees/revenue/cost on the property row)

No Critical rows in the filtered query.

Warborn Waterdeep registry property: Employees 200, Monthly Revenue **0**, Monthly Cost 22900.  
Warborn Neverwinter registry property: Employees 77, Monthly Revenue **360000**, Monthly Cost 20000.  
Zariel contract registry property: Monthly Revenue **360000**, Monthly Cost 22900.

## Not done in this commit

- Full 70+ entity dump into facilities.csv
- employment.csv / relationships.csv / programmes.csv
- Body-hash receipts for unread pages
- Canonical month still CLOSED
