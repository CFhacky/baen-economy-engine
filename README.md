# Baen Economy Engine

Public, unique, usable **without Grok**.

This is the fail-closed monthly economy engine for **The New Path / Baen Empire**. Other people and other apps call it over HTTP or import it as a Python package. It is **not** a notes browser.

Canonical campaign time stays frozen at **Day 7 Hammer 1495 DR**. Preview months are `scenario_assumption`. They post **zero** ledger entries and write **zero** Notion rows.

Extracted as a standalone public package from the private campaign vault (engine head `2cfb0c5`). Draft PR [#192](https://github.com/CFhacky/campaign-development-vault/pull/192) is **not** merged.

## What other apps call

```bash
pip install "git+https://github.com/CFhacky/baen-economy-engine.git"

python -m baen_economy.http_api --host 0.0.0.0 --port 8090
```

```http
GET  /v1/health
GET  /v1/coverage
GET  /v1/openapi.json
POST /v1/preview
POST /v1/canonical   → 409
```

```bash
curl -sX POST http://127.0.0.1:8090/v1/preview \
  -H 'content-type: application/json' \
  -d '{"kind":"food","seed":"your-replay-seed"}'
```

`kind` is `food` (five confirmed Agriculture/Aquaculture rows), `registry` (every Registry row, ineligible ones skipped), or `business` (one entity title in `entityId`).

CORS is open (`Access-Control-Allow-Origin: *`).

Schema: `tnp.economy.tick-result/1` plus the existing `tnp.business.month-preview/1` row payloads.

## What a preview month actually does

For each eligible commercial Registry row it:

1. Binds the source Employees / Monthly Revenue / Monthly Cost cells.
2. Rolls Merchant-15 revenue and Administration-16 expense with HMAC-SHA256 seeded 3d6 (same algorithm as the vault engine).
3. Applies the GURPS outcome factors (1.25 … 0.70 revenue, 0.90 … 1.25 expense).
4. Returns proposed gp totals labeled **not canon**.

It will **not**:

- Invent opening cash, labour, or cities.
- Treat parent Northern Crown plus branches as one bank.
- Treat Capital Invested as current liquidity.
- Advance campaign time.
- Write Notion.
- Accept a canonical month while `SIMULATED = 0`.

Unconfirmed rows (Gold Lending House, Lobster King) are held out. Military / Intelligence / Education / R&D are outside the Merchant-15 allowlist. Missing numbers fail closed.

## CLI (unchanged vault entrypoints)

```bash
PYTHONPATH=src python -m baen_economy.business_cli --help
PYTHONPATH=src python -m baen_economy.food_cli --help
PYTHONPATH=src python -m baen_economy.whole_economy_cli --help
```

`baen-region` still requires `--allow-synthetic-demo` and is **not** the campaign economy.

Python **3.11+**. No third-party runtime dependencies.

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

The 29 August 2026 90-row Registry export is included. The 700 KB page-body snapshot is **not** published here (GM prose). Food-baseline tests that hash those bodies will skip/fail unless you restore that fixture locally.

## License

MIT. See `LICENSE` and `THIRD_PARTY_NOTICES.md`.
