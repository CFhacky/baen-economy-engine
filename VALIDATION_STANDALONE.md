# Standalone Validation Evidence — 17 September 2026

This file records validation of `CFhacky/baen-economy-engine` as its own checkout. It does not rewrite the historical private-vault evidence in `VALIDATION.md` and does not promote a preview to campaign canon.

## Extraction baseline

Standalone `main` was created at:

- repository: `CFhacky/baen-economy-engine`
- baseline commit: `dd80d730427967dc78fe7b965b6a6d5875c9f3a2`
- extracted private-vault engine head identified by the extraction commit: `2cfb0c5`
- package version: `0.3.0`
- Python: `>=3.11`

The repository initially had no `.github/workflows` directory, so the historical validation results inherited from the private vault were evidence about the source tree before extraction, not a fresh executable result from this standalone checkout.

## First literal standalone full-suite run

The first GitHub Actions run used ordinary unittest discovery against the extracted checkout on Python 3.11/3.12.

On Python 3.11 it reported:

- **511 tests executed**
- **502 passed**
- **9 errors**
- no failing economy assertion

All nine errors were extraction-boundary problems:

1. `OPEN-BAEN-AGRICULTURE.cmd` was omitted from the public extraction.
2. `OPEN-BAEN-FOOD-OPERATOR.cmd` was omitted.
3. `OPEN-BAEN-WHOLE-ECONOMY.cmd` was omitted.
4. four finance tests still resolved the PR #48 chart through a sibling private-vault repository path;
5. the `FoodBaselineTests` class requires the intentionally unpublished detailed Registry page-body snapshot;
6. one live-census recovery test asserted the private monorepo publisher-workflow path and recovery branch.

The three launchers were restored byte-for-byte from the private-vault extraction source. The exact PR #48 account chart was bundled at `fixtures/finance/pr48-accounts.bean` with its source commit recorded in the fixture header.

## Public standalone regression contract

The public runner is:

```bash
PYTHONPATH=src python tools/run_standalone_tests.py
```

The runner:

- performs normal `tests/test_*.py` discovery;
- uses the bundled exact PR #48 chart for inherited finance contract tests;
- explicitly prints every inherited test excluded from the public checkout;
- does not synthesize the private Registry page-body fixture;
- refuses to use the exclusion runner if that private fixture unexpectedly exists;
- leaves the old private-vault publisher assertion excluded because the standalone repository has read-only package CI rather than that publication workflow.

The first green public runner revision, before the PR #48 tests were re-enabled from the local bundle and before direct-product integration coverage was added, executed **506 tests successfully on Python 3.11 and 506 again on Python 3.12**.

## Current validated code head

The current code-validation head is:

- branch: `codex/reconcile-standalone-authority-20260917`
- code head: `c8d5830745f709838a3effe9ac9a4e588cc5f86f`
- GitHub Actions run: **#115**
- run ID: `35280499380`

Run #115 is green across the full workflow matrix.

### Python 3.11

- **544 tests run**
- **0 failures**
- **3 skips**
- standalone import surface passed

The three skips are dedicated-product/evidence boundaries, not silently counted as passing tests.

### Python 3.12

- standalone regression contract passed;
- public import surface passed;
- exact pinned Mesa `20841b12559ef920dd4c8263a09fe75ceac7250c` installed and executed successfully.

### Dedicated upstream-product jobs

Each of these jobs acquires/builds/boots the exact pinned upstream revision rather than treating a Baen-local compatibility helper as the product:

- **Brunnfeld Agentic World** `e0656ca01630333e26c622ffd4ba4c973b79eebe` — exact Node service booted and published HTTP API probed: **PASS**.
- **Unknown Horizons** `af9c8ef5c7f6cf9ec0b8c9e7d172c555f2793615` — actual upstream `ProductionLine` executed in the isolated child process: **PASS**.
- **FreeCol** `0a9e3cce950471fa67ae390d1a2fdf179e732092` — actual `FreeCol.jar` built and real production model objects executed in a child JVM: **PASS**.
- **Veloren** `e633eb8ca15ae97bb5ef5a039fcf6844e96ad704` — exact `veloren-world` crate built with its required `mold` linker; narrow GPL-side state-injection seam fed state into the real `Economy::tick`: **PASS**. The product probe used population 64, food 500, coin 1000 for 30 simulated days and returned Veloren's own population 64, food 374.4, coin 1000, food price 0.1, with `canonical_time_advanced=False`.
- **OpenTTD** `1aca0b60a8024f295e1d0ad2a3407b3dac838099` — exact dedicated server built, booted, authenticated through the documented admin network, and answered the live product probe: **PASS**.

The first OpenTTD product attempt built successfully but did not open the admin listener. The failure was in the Baen probe configuration, not the upstream build: the generated config omitted `[version] / ini_version`, so this OpenTTD revision treated it as pre-split INI v0 and looked for secret network settings in `openttd.cfg` instead of `secrets.cfg`. Commit `cff4ff225ffb5bf89a4e92a7a1ddab4e66475c0e` writes INI version 8 to both files. Run #115 proves the corrected real-product path.

The first Veloren product attempt failed before bridge compilation because the pinned upstream Cargo configuration requires the `mold` linker. Commit `c8d5830745f709838a3effe9ac9a4e588cc5f86f` installs that actual upstream dependency in CI. Run #115 proves the corrected real-product path.

## Evidence intentionally absent from the public repository

The private detailed Registry page-body snapshot is not published. It contains GM-prose source bodies and was deliberately excluded from the standalone extraction. Therefore its evidence-integrity checks are not described as passing in the public suite.

That does **not** mean food behavior is untested publicly. The repository still executes the public source/sector/operator/agriculture tests, including source fixture validation, five-business financial envelope behavior, physical unknown handling, production planning, storage/replay, HTTP operator acceptance, and no-write/no-campaign-advance assertions. The omitted page-body checks are specifically evidence-integrity checks against the unpublished source body snapshot.

The historical private-vault validation remains available in `VALIDATION.md` for the environment in which that source was present.

## CI authority boundary

`.github/workflows/ci.yml` runs on pushes and pull requests. It compiles and tests the Baen package and separately executes the pinned upstream products through their real library/service/process/JVM/Rust/headless boundaries.

The workflow has `contents: read` permission. Product jobs are preview/research execution only. CI does not:

- write Notion;
- post to the campaign ledger;
- merge the PR;
- advance canonical campaign time;
- run a canonical campaign month;
- promote upstream defaults into campaign facts.

## Census validation boundary

The latest standalone recovery machine evidence distinguishes:

- **1,381 current-live members** of the ten current Notion collections;
- **239 retained former NPC members** captured previously;
- **1,620 retained core records**;
- **7 contextual authority records**;
- **1,627 total stored records**.

All ten current live collections have complete query-visible property enumeration, but `SIMULATED = 0`. Acquisition completeness therefore does not open the canonical execution gate.

The stale 372-record intermediate recovery report remains preserved for provenance; `recovery/CURRENT_CENSUS_STATE_2026-09-17.md` defines the current human-readable count semantics.

## Safety / authority result

At this reconciliation stage:

- Notion writes: **0**
- canonical ledger postings caused by reconciliation: **0**
- campaign-time advances: **0**
- canonical months executed: **0**
- merge performed: **no**

The repository is validated as executable software, including six real upstream-product runtime boundaries. The campaign economy remains fail-closed until source-to-simulator semantic coverage and unresolved authority/data gaps are genuinely closed.
