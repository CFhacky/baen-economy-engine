from __future__ import annotations
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from baen_economy.census_acquisition import (AcquisitionError, CollectionSpec,
    DirectNotionAcquisition, assemble, census_diff, digest, materialize,
    stable_id, unpack_response, verify_enumeration)

DS = "collection://11111111-1111-4111-8111-111111111111"
URL1 = "https://app.notion.com/aaaaaaaaaaaa4aaa8aaaaaaaaaaaaaaa"
URL2 = "https://app.notion.com/bbbbbbbbbbbb4bbb8bbbbbbbbbbbbbbb"
COLS = ("url", "Name", "Type", "Population", "Parent Location", "Notes", "Status", "createdTime")
SPEC = CollectionSpec("locations", DS, "Test locations", "locations", "Name", COLS,
                      ("Population",), ("Parent Location",), ())


def row(url=URL1):
    return [url, "No predefined simulation type", "Unknown new type", 0,
            json.dumps([URL2]), "Not a zero population assumption; raw source says zero.", None, "2026-09-17 14:00:00Z"]


def receipt(rows=None, after="", limit=25):
    return {"collection": "locations", "data_source_url": DS,
            "tool": "Notion.query-data-sources", "mode": "sql", "after": after,
            "limit": limit, "response_has_more": False, "columns": list(COLS),
            "rows": [row()] if rows is None else rows}


def proof(n=1, after=URL1):
    return {"start": {"row_count": n, "distinct_urls": n},
            "end": {"row_count": n, "distinct_urls": n},
            "terminal_after": after, "terminal_urls_json": "[]"}


def wrapped(results, more=False):
    return {"text": json.dumps({"results": results, "has_more": more,
                               "data_source_ids": [DS.removeprefix("collection://")]})}


class CensusAcquisitionTests(unittest.TestCase):
    def test_complete_live_call_sequence_reaches_empty_terminal(self):
        calls, saved = [], []
        replies = iter([{}, wrapped([{"row_count": 2, "distinct_urls": 2}]),
                        wrapped([{"rows_json": json.dumps([row()])}]),
                        wrapped([{"rows_json": json.dumps([row(URL2)])}]),
                        wrapped([{"rows_json": "[]"}]),
                        wrapped([{"row_count": 2, "distinct_urls": 2}])])
        def dispatch(tool, args):
            calls.append((tool, args))
            return next(replies)
        receipts, evidence = DirectNotionAcquisition(dispatch, saved.append).acquire(SPEC, 1)
        self.assertEqual(len(calls), 6)
        self.assertEqual(calls[0], ("Notion.fetch", {"id": DS}))
        self.assertEqual(calls[3][1]["data"]["params"], [URL1, 1])
        self.assertEqual(len(saved), 3)  # includes the terminal empty receipt
        self.assertTrue(verify_enumeration(SPEC, receipts, evidence)["enumeration_complete"])

    def test_no_write_tool_can_be_dispatched(self):
        client = DirectNotionAcquisition(lambda *args: self.fail("write reached host"), lambda x: None)
        with self.assertRaises(AcquisitionError):
            client._call("Notion.notion-update-page", {})

    def test_count_only_is_not_enumeration(self):
        self.assertFalse(verify_enumeration(SPEC, [], proof())["enumeration_complete"])

    def test_count_drift_closes_gate_and_retains_rows(self):
        p = proof()
        p["end"]["row_count"] = 2
        result = verify_enumeration(SPEC, [receipt()], p)
        self.assertFalse(result["enumeration_complete"])
        self.assertEqual(result["acquired_count"], 1)

    def test_missing_terminal_evidence_stays_incomplete(self):
        self.assertFalse(verify_enumeration(SPEC, [receipt()], None)["enumeration_complete"])

    def test_missing_keyset_page_rejected(self):
        with self.assertRaises(AcquisitionError):
            verify_enumeration(SPEC, [receipt(after=URL2)], proof())

    def test_truncated_connector_result_rejected(self):
        with self.assertRaises(AcquisitionError):
            unpack_response({"results": [], "has_more": False, "truncated": True})

    def test_duplicate_source_rejected(self):
        with self.assertRaises(AcquisitionError):
            verify_enumeration(SPEC, [receipt([row(), row()])], proof(2))

    def test_unsupported_type_and_nulls_not_dropped(self):
        result = materialize(SPEC, row())
        self.assertEqual(result["coverage_state"], "UNKNOWN")
        self.assertEqual(result["source_properties"]["Type"], "Unknown new type")
        self.assertEqual(result["numeric_properties"]["Population"], 0)
        self.assertIsNone(result["status"])
        self.assertEqual(result["relationships"]["Parent Location"][0]["source_id"], stable_id(URL2))

    def test_source_hash_deterministic_and_detects_content_change(self):
        first = materialize(SPEC, row())
        self.assertEqual(first, materialize(SPEC, row()))
        edited = row()
        edited[5] += " Changed."
        self.assertNotEqual(first["source_hash"], materialize(SPEC, edited)["source_hash"])
        body = {k: v for k, v in first.items() if k != "source_hash"}
        self.assertEqual(first["source_hash"], digest(body))

    def test_json_relation_serializations_normalize_equally(self):
        decoded = row()
        decoded[4] = [URL2]
        self.assertEqual(materialize(SPEC, row()), materialize(SPEC, decoded))

    def test_url_forms_have_same_stable_identity(self):
        self.assertEqual(stable_id(URL1), stable_id(URL1.replace(".com/", ".com/p/") + "?pvs=204"))

    def test_incomplete_collection_never_claims_record_removed(self):
        rec = materialize(SPEC, row())
        previous = {"records": [rec], "snapshot_hash": "a" * 64}
        current = {"records": [], "collections": [{"key": "locations", "enumeration_complete": False}], "snapshot_hash": "b" * 64}
        diff = census_diff(previous, current)
        self.assertEqual(diff["removed"], [])
        self.assertEqual(diff["unobserved_not_removed"], [rec["stable_source_id"]])
        current["collections"][0]["enumeration_complete"] = True
        self.assertEqual(census_diff(previous, current)["removed"], [rec["stable_source_id"]])

    def test_coverage_transition_is_explicit(self):
        before = materialize(SPEC, row())
        after = copy.deepcopy(before)
        after.update(coverage_state="CONFLICT", source_hash="c" * 64)
        diff = census_diff({"records": [before]}, {"records": [after], "collections": [], "snapshot_hash": "d" * 64})
        self.assertEqual(diff["coverage_transitions"][0]["from"], "UNKNOWN")
        self.assertEqual(diff["coverage_transitions"][0]["to"], "CONFLICT")

    def test_bad_row_width_fails_instead_of_losing_property(self):
        with self.assertRaises(AcquisitionError):
            materialize(SPEC, row()[:-1])

    def test_real_zero_row_collection_can_be_enumerated(self):
        self.assertTrue(verify_enumeration(SPEC, [], proof(0, ""))["enumeration_complete"])


if __name__ == "__main__":
    unittest.main()
