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

The first green public runner revision, before the PR #48 tests were re-enabled from the local bundle, executed **506 tests successfully on Python 3.11 and 506 again on Python 3.12**, followed by a successful import-surface check on both versions.

The runner was then tightened to re-enable the four pinned-chart finance tests. The authoritative result for the current branch head is the GitHub Actions check attached to draft PR #1; do not infer a larger count until that head is green.

## Evidence intentionally absent from the public repository

The private detailed Registry page-body snapshot is not published. It contains GM-prose source bodies and was deliberately excluded from the standalone extraction. Therefore its ten `FoodBaselineTests` checks are not described as passing in the public suite.

That does **not** mean food behavior is untested publicly. The repository still executes the public source/sector/operator/agriculture tests, including source fixture validation, five-business financial envelope behavior, physical unknown handling, production planning, storage/replay, HTTP operator acceptance, and no-write/no-campaign-advance assertions. The omitted page-body checks are specifically evidence-integrity checks against the unpublished source body snapshot.

The historical private-vault validation remains available in `VALIDATION.md` for the environment in which that source was present.

## CI

`.github/workflows/ci.yml` now runs on pushes and pull requests and tests Python 3.11 and 3.12. It:

1. compiles `src`, `tests`, and `tools`;
2. runs the explicit standalone regression contract;
3. imports the public package/API/CLI surface.

The workflow has `contents: read` permission. It does not write Notion, post to a campaign ledger, merge, or advance campaign time.

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

The repository is being validated as executable software. The campaign economy remains fail-closed until source-to-simulator coverage and unresolved authority/data gaps are genuinely closed.
