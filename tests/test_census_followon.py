from __future__ import annotations
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
from baen_economy.source_census import CensusSnapshot, SourceRecord, coverage_report
from baen_economy.source_census_acquisition import AcquisitionError, CollectionSpec, stable_id, verify_receipts

spec = importlib.util.spec_from_file_location("followon_materializer", PROJECT / "tools/materialize_live_census.py")
materializer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(materializer)


class FollowonCensusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.outputs = materializer.build()
        cls.manifest = json.loads(cls.outputs[materializer.RECOVERY / "LIVE_CENSUS_ACQUISITION_MANIFEST_2026-09-17.json"])
        cls.snapshot = CensusSnapshot.from_mapping(json.loads(cls.outputs[materializer.LATEST]))
        cls.factions = [r for r in cls.snapshot.records if r.source_class == "factions"]

    def test_all_required_records_plus_79_factions_are_materialized(self):
        self.assertEqual(self.manifest["complete_collections"], {
            "business_registry": 90, "locations": 182, "consequence_ledger_a": 11,
            "consequence_ledger_b": 10, "factions": 79})
        self.assertEqual(self.manifest["live_materialized_records"], 372)
        self.assertEqual(len(self.factions), 79)
        self.assertEqual(len({r.stable_source_id for r in self.snapshot.records}), 379)

    def test_previous_293_records_and_context_are_unchanged(self):
        before = CensusSnapshot.from_mapping(json.loads(self.outputs[materializer.FOLLOWON_PREVIOUS]))
        current = {r.stable_source_id: r for r in self.snapshot.records}
        self.assertEqual(len(before.records), 300)
        for record in before.records:
            self.assertEqual(record.source_hash, current[record.stable_source_id].source_hash)

    def test_diff_against_preceding_checkpoint_is_79_added_not_372(self):
        diff = json.loads(self.outputs[materializer.RECOVERY / "LIVE_EMPIRE_SOURCE_CENSUS_DIFF_2026-09-17.json"])
        self.assertEqual(len(diff["added"]), 79)
        self.assertEqual(diff["changed"], [])
        self.assertEqual(diff["removed"], [])
        self.assertEqual(diff["unchanged_count"], 300)

    def test_all_hashes_validate_and_tombstone_is_retained(self):
        for record in self.factions:
            SourceRecord.from_mapping({**record.semantic_body(), "source_hash": record.source_hash})
        tombstone = next(r for r in self.factions if "[TRASH" in r.title)
        self.assertEqual(tombstone.coverage_state.value, "UNKNOWN")
        self.assertEqual(tombstone.effective_status, "Active")
        blank = next(r for r in self.factions if r.title == "Bloodaxe Legion Mage Cadre")
        self.assertIn("Notes: null", blank.narrative_facts)

    def test_faction_formal_relations_are_not_lost(self):
        covenant = next(r for r in self.factions if r.title == "The Moonflower Covenant")
        self.assertEqual(len(covenant.direct_relations), 14)
        self.assertIn(stable_id("https://app.notion.com/3dde821484b081cfba06d70d5f524d9c"), covenant.direct_relations)
        iron = next(r for r in self.factions if r.title == "Iron Sovereignty")
        self.assertEqual(iron.numeric_properties["Disposition"], -7)

    def test_coverage_stays_closed_and_does_not_invent_simulation(self):
        report = coverage_report(self.snapshot)
        self.assertEqual(report["gate"], "CLOSED")
        self.assertEqual(len(report["incomplete_collections"]), 5)
        self.assertEqual(self.manifest["core_coverage_counts"]["UNKNOWN"], 368)
        self.assertEqual(self.manifest["core_coverage_counts"]["SIMULATED"], 0)
        self.assertEqual(self.manifest["unmaterialized_core_rows"], 1009)

    def test_extra_collection_never_enters_ledger_reconciliation(self):
        ledger = json.loads(self.outputs[materializer.RECOVERY / "CONSEQUENCE_LEDGER_RECONCILIATION_2026-09-17.json"])
        self.assertEqual((ledger["raw_rows"], ledger["linked_pairs"], ledger["unmatched_a"], ledger["unmatched_b"]), (21, 7, 4, 3))
        self.assertEqual({r["collection"] for r in ledger["rows"]}, {"consequence_ledger_a", "consequence_ledger_b"})

    def test_missing_followon_page_or_live_membership_change_fails_closed(self):
        raw = materializer.RAW
        paths = sorted(raw.glob("factions.[0-9][0-9][0-9].json"))
        pages = [json.loads(p.read_text()) for p in paths]
        proof = json.loads((raw / "factions.proof.json").read_text())
        spec = CollectionSpec("factions", proof["data_source_url"], tuple(pages[0]["columns"]), "Name")
        self.assertEqual(len(verify_receipts(spec, pages, proof)), 79)
        with self.assertRaises(AcquisitionError):
            verify_receipts(spec, pages[:-1], proof)
        bad_proof = copy.deepcopy(proof)
        bad_proof["initial_ordered_ids"] = "0" * 32 + " " + proof["initial_ordered_ids"]
        with self.assertRaises(AcquisitionError):
            verify_receipts(spec, pages, bad_proof)

    def test_repeated_generation_is_byte_identical(self):
        self.assertEqual(self.outputs, materializer.build())


if __name__ == "__main__":
    unittest.main()
