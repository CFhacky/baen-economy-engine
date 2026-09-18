from __future__ import annotations

import unittest

from baen_economy.completeness import EXPECTED_DRIVER_REGISTRY, completeness_report


class CompletenessTests(unittest.TestCase):
    def test_acquisition_is_not_misreported_as_completeness(self):
        report = completeness_report()
        acquisition = report["gates"]["collection_acquisition"]
        queue = report["gates"]["source_review_queue_inventory"]
        semantic = report["gates"]["source_record_semantic_status"]
        bodies = report["gates"]["source_body_review"]
        dispositions = report["gates"]["source_review_dispositions"]

        self.assertTrue(acquisition["pass"])
        self.assertEqual(acquisition["retained_core_records"], 1620)
        self.assertEqual(acquisition["not_materialized"], 0)

        self.assertTrue(queue["pass"])
        self.assertEqual(queue["records"], 1620)
        self.assertTrue(queue["matches_full_execution_census"])
        self.assertEqual(queue["census_hash_mismatches"], 0)
        self.assertEqual(queue["semantic_status_mismatches"], 0)

        self.assertFalse(semantic["pass"])
        self.assertEqual(semantic["non_unknown"], 13)
        self.assertEqual(semantic["unknown"], 1607)
        self.assertEqual(semantic["new_source_mapped_ids"], 9)
        self.assertEqual(
            semantic["status_counts"],
            {"CONFLICT": 2, "SOURCE_MAPPED": 9, "SUPERSEDED": 2, "UNKNOWN": 1607},
        )

        self.assertFalse(bodies["pass"])
        self.assertEqual(bodies["tracking_status"], "QUEUE_MATERIALIZED_REVIEW_NOT_STARTED")
        self.assertEqual(bodies["reviewed_retained_core"], 0)
        self.assertEqual(bodies["unread_retained_core"], 1620)
        self.assertEqual(bodies["body_status_counts"], {"UNMEASURED": 1620})
        self.assertEqual(bodies["historical_checkpoint"]["page_body_acquired_false"], 372)

        self.assertFalse(dispositions["pass"])
        self.assertEqual(dispositions["dispositioned"], 0)
        self.assertEqual(dispositions["undispositioned"], 1620)

        self.assertFalse(report["coverage_claim_allowed"])
        self.assertFalse(report["canonical_execution_ready"])

    def test_finite_driver_registry_is_present_and_still_blocked(self):
        report = completeness_report()
        registry = report["gates"]["driver_registry"]
        dispositions = report["gates"]["driver_dispositions"]

        self.assertTrue(registry["pass"])
        self.assertEqual(registry["expected"], len(EXPECTED_DRIVER_REGISTRY))
        self.assertEqual(registry["present"], len(EXPECTED_DRIVER_REGISTRY))
        self.assertEqual(registry["missing"], [])
        self.assertEqual(registry["unexpected"], [])
        self.assertTrue(dispositions["pass"])
        self.assertIn("opening_liquidity", dispositions["blocked"])
        self.assertIn("inventories", dispositions["blocked"])
        self.assertIn("trade_routes", dispositions["incomplete"])
        self.assertFalse(report["gates"]["empire_close"]["canonical_driver_ready"])

    def test_locked_recovery_boundaries_remain_green(self):
        report = completeness_report()
        locked = report["gates"]["locked_boundaries"]
        self.assertTrue(locked["pass"])
        self.assertEqual(locked["notion_writes"], 0)
        self.assertFalse(locked["campaign_time_advanced"])
        self.assertFalse(locked["canonical_month_executed"])


if __name__ == "__main__":
    unittest.main()
