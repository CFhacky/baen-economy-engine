from __future__ import annotations

import unittest

from baen_economy.completeness import EXPECTED_DRIVER_REGISTRY, completeness_report


class CompletenessTests(unittest.TestCase):
    def test_acquisition_is_not_misreported_as_completeness(self):
        report = completeness_report()
        acquisition = report["gates"]["collection_acquisition"]
        semantic = report["gates"]["source_record_semantic_disposition"]
        bodies = report["gates"]["source_body_review"]

        self.assertTrue(acquisition["pass"])
        self.assertEqual(acquisition["retained_core_records"], 1620)
        self.assertEqual(acquisition["not_materialized"], 0)

        self.assertFalse(semantic["pass"])
        self.assertEqual(semantic["reviewed_or_explicitly_disposed"], 13)
        self.assertEqual(semantic["unknown"], 1607)
        self.assertEqual(semantic["new_source_mapped_ids"], 9)

        self.assertFalse(bodies["pass"])
        self.assertEqual(bodies["tracking_status"], "NOT_YET_EXHAUSTIVELY_MEASURED")
        self.assertIsNone(bodies["reviewed_retained_core"])
        self.assertIsNone(bodies["unread_retained_core"])

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
