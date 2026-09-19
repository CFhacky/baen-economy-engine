from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from baen_economy.empire_ops_store import EmpireOpsStore, EmpireOpsStoreError


class EmpireOpsStoreTests(unittest.TestCase):
    def test_append_only_save_reopen_compare_export_and_seed_redaction(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empire.sqlite"
            raw_seed = "never-store-this-seed"
            result_a = {
                "schema": "tnp.economy.empire-business-turn/1",
                "canonical": False,
                "campaign_time_advanced": False,
                "notion_writes": 0,
                "canonical_ledger_postings": 0,
                "month_label": "Hammer A",
                "seed_fingerprint": "abc123",
                "result_hash": "hash-a",
                "admission": {"admitted_entities": 37, "baseline_revenue_gp": "299266"},
                "proposed_revenue_gp": "300000",
                "proposed_net_range_gp": ["70000", "85000"],
                "sector_results": [{"sector": "Banking", "proposed_revenue_gp": "10000"}],
            }
            request_a = {
                "seed": raw_seed,
                "month_label": "Hammer A",
                "market_condition": "unknown",
                "vara_active": False,
            }
            store = EmpireOpsStore(path)
            saved = store.save(
                run_id="hammer-a",
                label="Hammer A",
                request=request_a,
                result=result_a,
                report="# report A",
            )
            self.assertFalse(saved["request"]["raw_seed_persisted"])
            self.assertNotIn("seed", saved["request"])
            self.assertNotIn(raw_seed.encode(), path.read_bytes())
            replay = store.save(
                run_id="hammer-a",
                label="Hammer A",
                request=request_a,
                result=result_a,
                report="# report A",
            )
            self.assertTrue(replay["replayed_existing_save"])
            with self.assertRaises(EmpireOpsStoreError):
                store.save(
                    run_id="hammer-a",
                    label="changed",
                    request=request_a,
                    result=result_a,
                    report="# report A",
                )

            result_b = {
                **result_a,
                "month_label": "Hammer B",
                "seed_fingerprint": "def456",
                "result_hash": "hash-b",
                "proposed_revenue_gp": "310000",
                "sector_results": [{"sector": "Banking", "proposed_revenue_gp": "11000"}],
            }
            store.save(
                run_id="hammer-b",
                label="Hammer B",
                request={**request_a, "seed": "other", "month_label": "Hammer B"},
                result=result_b,
                report="# report B",
            )
            comparison = store.compare("hammer-a", "hammer-b")
            self.assertFalse(comparison["same_result_hash"])
            self.assertTrue(comparison["sector_changes"][0]["changed"])
            content_type, exported = store.export("hammer-a", "html")
            self.assertIn("text/html", content_type)
            self.assertIn(b"report A", exported)
            store.close()

            reopened = EmpireOpsStore(path)
            self.assertEqual(len(reopened.list_runs()), 2)
            self.assertEqual(reopened.get("hammer-a")["label"], "Hammer A")
            reopened.close()


if __name__ == "__main__":
    unittest.main()
