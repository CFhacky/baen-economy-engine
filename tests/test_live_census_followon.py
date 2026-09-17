from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
from baen_economy.source_census import SourceRecord, canonical_hash, load_census_snapshot
from baen_economy.source_census_acquisition import (
    AcquisitionError, CollectionSpec, normalize_record, stable_id, verify_receipts,
)

FRESH = PROJECT / "recovery/acquisition/20260917-execution"
CANONICAL = PROJECT / "recovery/acquisition/20260917"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def captured():
    pages = [read(p) for p in sorted(FRESH.glob("factions.[0-9][0-9][0-9].json"))]
    proof = read(FRESH / "factions.proof.json")
    spec = CollectionSpec("factions", proof["data_source_url"], tuple(pages[0]["columns"]), "Name")
    return spec, pages, proof, verify_receipts(spec, pages, proof)


class LiveFollowonCensusTests(unittest.TestCase):
    def test_all_79_fresh_factions_have_verified_membership(self):
        spec, pages, proof, rows = captured()
        self.assertEqual(len(rows), 79)
        self.assertEqual(len({r["url"] for r in rows}), 79)
        self.assertEqual(proof["initial_count"], proof["final_count"])
        self.assertEqual(proof["tail_rows"], 0)
        self.assertEqual([len(p["rows"]) for p in pages], [25, 25, 29])

    def test_every_fresh_record_is_hashed_and_retains_threat_level(self):
        spec, _, _, rows = captured()
        for row in rows:
            with self.subTest(source=row["url"]):
                result = normalize_record(spec, row)
                SourceRecord.from_mapping(result)
                self.assertEqual(result["stable_source_id"], stable_id(row["url"]))
                self.assertEqual(result["source_hash"], canonical_hash({k: v for k, v in result.items() if k != "source_hash"}))
                self.assertIn("Threat Level: " + json.dumps(row["Threat Level"], ensure_ascii=True), result["narrative_facts"])
                self.assertEqual(len(result["narrative_facts"]), len(spec.columns) - 1)

    def test_untyped_and_tombstone_factions_are_not_dropped(self):
        spec, _, _, rows = captured()
        untyped = [r for r in rows if r["Type"] is None]
        tombstones = [r for r in rows if "DO NOT USE" in (r["Name"] or "")]
        self.assertTrue(untyped)
        self.assertTrue(tombstones)
        for row in untyped + tombstones:
            result = normalize_record(spec, row)
            self.assertEqual(result["source_class"], "factions")
            self.assertIn(result["coverage_state"], {"UNKNOWN", "SUPERSEDED"})
            self.assertEqual(result["source_url"], row["url"])

    def test_missing_live_row_fails_closed(self):
        spec, pages, proof, _ = captured()
        bad = copy.deepcopy(pages)
        bad[-1]["rows"].pop()
        with self.assertRaises(AcquisitionError):
            verify_receipts(spec, bad, proof)

    def test_false_terminal_membership_fails_closed(self):
        spec, pages, proof, _ = captured()
        bad = {**proof, "tail_rows": 1}
        with self.assertRaises(AcquisitionError):
            verify_receipts(spec, pages, bad)

    def test_publisher_uses_complete_fresh_property_schema(self):
        spec, _, _, fresh = captured()
        pages = [read(p) for p in sorted(CANONICAL.glob("factions.[0-9][0-9][0-9].json"))]
        proof = read(CANONICAL / "factions.proof.json")
        canonical = verify_receipts(spec, pages, proof)
        self.assertEqual(canonical, fresh)
        snapshot = load_census_snapshot(PROJECT / "recovery/LIVE_EMPIRE_SOURCE_CENSUS_2026-09-17.json")
        materialized = {r.stable_source_id: r for r in snapshot.records if r.source_class == "factions"}
        self.assertEqual(len(materialized), 79)
        for row in fresh:
            record = normalize_record(spec, row)
            self.assertEqual(materialized[record["stable_source_id"]].source_hash, record["source_hash"])

    def test_publication_and_pr_cannot_share_concurrency_group(self):
        workflow = (PROJECT.parents[2] / ".github/workflows/baen-economy-engine.yml").read_text()
        group = next(line for line in workflow.splitlines() if line.strip().startswith("group: baen-census-"))
        self.assertIn("github.event_name", group)
        self.assertIn("github.event_name == 'push'", workflow)
        self.assertIn("refs/heads/codex/baen-economy-recovery-census-20260917", workflow)


if __name__ == "__main__":
    unittest.main()
