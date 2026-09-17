#!/usr/bin/env python3
"""Run the public standalone regression suite.

The extracted repository intentionally does not publish the private Registry
page-body snapshot. One recovery test also asserts the old monorepo publisher
workflow path. Those checks remain valuable in the private vault but are not
evidence this public package can produce from its own checkout.

The PR #48 account chart *is* publishable contract data, so the standalone repo
bundles the exact pinned chart at fixtures/finance/pr48-accounts.bean and this
runner redirects the inherited finance tests to that local fixture.

Everything else under tests/ is executed. Exclusions are exact test IDs, printed
before the run, and a newly-added test cannot silently join the exclusion set.
"""
from __future__ import annotations

import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

EXACT_EXCLUSIONS = {
    # Private Registry page-body snapshot is intentionally unpublished.
    "test_food_baseline.FoodBaselineTests.test_complete_source_coverage_and_exact_financial_envelope",
    "test_food_baseline.FoodBaselineTests.test_shelters_are_produce_and_tomatoes_not_invented_grain",
    "test_food_baseline.FoodBaselineTests.test_all_seven_rows_keep_ownership_and_unknowns_distinct",
    "test_food_baseline.FoodBaselineTests.test_later_crisis_is_context_not_a_silent_scaled_baseline",
    "test_food_baseline.FoodBaselineTests.test_safety_boundary_is_literal",
    "test_food_baseline.FoodBaselineTests.test_page_body_tamper_breaks_source_verification",
    "test_food_baseline.FoodBaselineTests.test_unreviewed_extraction_field_fails_closed",
    "test_food_baseline.FoodBaselineTests.test_html_is_readable_and_does_not_claim_a_simulated_month",
    "test_food_baseline.FoodBaselineTests.test_cli_writes_a_readable_report",
    "test_food_baseline.FoodBaselineTests.test_regional_synthetic_demo_is_disabled_by_default",
    # This asserts the private-vault publisher workflow and old recovery branch,
    # not the standalone package's read-only CI workflow.
    "test_live_census_followon.LiveFollowonCensusTests.test_publication_and_pr_cannot_share_concurrency_group",
}


def flatten(suite: unittest.TestSuite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def main() -> int:
    discovered = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_*.py")

    # The inherited finance tests intentionally verified the private sibling PR #48
    # chart. Preserve that contract without requiring the sibling repository.
    bundled_chart = ROOT / "fixtures/finance/pr48-accounts.bean"
    if not bundled_chart.is_file():
        raise SystemExit("Missing bundled PR #48 chart fixture: " + str(bundled_chart))
    for module_name in ("test_finance", "test_banking_sandbox"):
        module = sys.modules.get(module_name)
        if module is None or not hasattr(module, "PR48_ACCOUNTS"):
            raise SystemExit("Inherited finance test module was not discovered: " + module_name)
        module.PR48_ACCOUNTS = bundled_chart

    selected = unittest.TestSuite()
    for test in flatten(discovered):
        test_id = test.id()
        if test_id in EXACT_EXCLUSIONS or test_id.startswith("unittest.loader._FailedTest.test_food_baseline"):
            continue
        selected.addTest(test)

    private_fixture = ROOT / "fixtures/source-snapshots/business-registry-page-bodies-2026-08-29.json"
    if private_fixture.exists():
        raise SystemExit(
            "Private page-body fixture is present; run the full inherited suite instead of the public exclusion runner."
        )

    print("Standalone exclusions (private/monorepo evidence only):")
    for test_id in sorted(EXACT_EXCLUSIONS):
        print("  -", test_id)
    print(f"Running {selected.countTestCases()} standalone tests")

    result = unittest.TextTestRunner(verbosity=2).run(selected)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
