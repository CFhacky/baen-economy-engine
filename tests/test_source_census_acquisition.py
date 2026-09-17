from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
from baen_economy.source_census import CensusError, CensusSnapshot, SourceRecord, canonical_hash, coverage_report
from baen_economy.source_census_acquisition import (
    AcquisitionError, CollectionSpec, LiveNotionCensusAcquirer, decode_batch,
    manifest_query, normalize_record, page_id, page_query, stable_id, unwrap_query, verify_receipts,
)

SOURCE = "collection://4b453810-16af-43eb-86ff-927da765a17f"
COLUMNS = ("url", "Name", "Status", "Population", "Notes", "Controller", "createdTime")
SPEC = CollectionSpec("locations", SOURCE, COLUMNS, "Name")


def row(index=1):
    return {"url": "https://app.notion.com/" + f"{index:032x}", "Name": f"Source {index}",
            "Status": "Controlled", "Population": None, "Notes": "Narrative source text",
            "Controller": '["https://app.notion.com/00000000000000000000000000000009"]',
            "createdTime": "2026-09-17T12:00:00Z"}


def response(results, **kwargs):
    return {"text": json.dumps({"results": results, "has_more": False,
        "data_source_ids": [SOURCE.removeprefix("collection://")], **kwargs})}


class FakeDirectTools:
    def __init__(self, records):
        self.rows = records
        self.calls = []
        self.checkpoints = []

    def invoke(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "Notion.fetch":
            return {"text": "test schema", "truncated": False}
        if name != "Notion.query-data-sources":
            raise AssertionError("unexpected mutation tool")
        data = arguments["data"]
        if "COUNT(*)" in data["query"]:
            after = data["params"][0]
            return response([{"final_count": len(self.rows), "unique_count": len(self.rows),
                "ordered_ids": " ".join(page_id(r["url"]) for r in self.rows),
                "tail_rows": sum(r["url"] > after for r in self.rows)}])
        after = data["params"][0] if data["params"] else ""
        selected = [r for r in self.rows if r["url"] > after][:2]
        return response([{"rows_json": json.dumps([[r[c] for c in COLUMNS] for r in selected])}])

    def save(self, name, value):
        self.checkpoints.append((name, copy.deepcopy(value)))


class LiveCensusAcquisitionTests(unittest.TestCase):
    def acquire(self, records=None):
        tools = FakeDirectTools(records if records is not None else [row(1), row(2), row(3)])
        outcome = LiveNotionCensusAcquirer(tools.invoke, tools.save, page_size=2).acquire_collection(SPEC)
        return tools, outcome

    def test_direct_live_dispatch_and_checkpointed_keyset_enumeration(self):
        tools, outcome = self.acquire()
        self.assertTrue(outcome["enumeration_complete"])
        self.assertEqual(len(outcome["records"]), 3)
        self.assertEqual({name for name, _ in tools.calls}, {"Notion.fetch", "Notion.query-data-sources"})
        self.assertEqual([n for n, _ in tools.checkpoints],
                         ["locations.schema", "locations.000", "locations.001", "locations.proof"])
        self.assertEqual(outcome["proof"]["tail_rows"], 0)

    def test_empty_collection_enumerates_without_manufacturing_a_record(self):
        _, outcome = self.acquire([])
        self.assertEqual(outcome["records"], [])
        self.assertTrue(outcome["enumeration_complete"])

    def test_missing_batch_fails_final_membership(self):
        _, result = self.acquire()
        with self.assertRaises(AcquisitionError):
            verify_receipts(SPEC, result["batches"][:1], result["proof"])

    def test_duplicate_page_or_broken_cursor_fails_closed(self):
        _, result = self.acquire()
        batches = copy.deepcopy(result["batches"])
        batches[1]["after"] = None
        with self.assertRaises(AcquisitionError):
            verify_receipts(SPEC, batches, result["proof"])

    def test_membership_churn_with_unchanged_count_is_detected(self):
        _, result = self.acquire()
        proof = dict(result["proof"], initial_ordered_ids="different initial membership")
        with self.assertRaises(AcquisitionError):
            verify_receipts(SPEC, result["batches"], proof)

    def test_nonzero_tail_refuses_complete_claim(self):
        _, result = self.acquire()
        with self.assertRaises(AcquisitionError):
            verify_receipts(SPEC, result["batches"], dict(result["proof"], tail_rows=1))

    def test_wrong_source_and_truncated_query_responses_are_rejected(self):
        for payload in (response([], has_more=True), response([], truncated=True),
                        response([], data_source_ids=["wrong"]), {"text": "{broken"}):
            with self.subTest(payload=payload), self.assertRaises(AcquisitionError):
                unwrap_query(payload, SPEC)

    def test_failure_keeps_completed_checkpoints(self):
        tools = FakeDirectTools([row(1), row(2), row(3)])
        original = tools.invoke
        def failing(name, arguments):
            if name == "Notion.query-data-sources" and arguments["data"].get("params") == [row(2)["url"]] and "COUNT(*)" not in arguments["data"]["query"]:
                return response([], truncated=True)
            return original(name, arguments)
        with self.assertRaises(AcquisitionError):
            LiveNotionCensusAcquirer(failing, tools.save, page_size=2).acquire_collection(SPEC)
        self.assertIn("locations.000", [n for n, _ in tools.checkpoints])
        self.assertEqual(tools.checkpoints[-1][0], "locations.failure")
        self.assertFalse(tools.checkpoints[-1][1]["enumeration_complete"])

    def test_mutation_tool_is_never_dispatched(self):
        calls = []
        acquirer = LiveNotionCensusAcquirer(lambda *args: calls.append(args), lambda *args: None)
        with self.assertRaises(AcquisitionError):
            acquirer._call("Notion.notion-update-page", {"page_id": "forbidden"})
        self.assertEqual(calls, [])

    def test_unknown_type_is_retained_with_null_numeric_and_narrative_facts(self):
        record = normalize_record(SPEC, row())
        self.assertEqual(record["coverage_state"], "UNKNOWN")
        self.assertIsNone(record["numeric_properties"]["Population"])
        self.assertIn('Notes: "Narrative source text"', record["narrative_facts"])
        self.assertIn("Population: null", record["narrative_facts"])
        self.assertEqual(record["direct_relations"], [stable_id("https://app.notion.com/" + "0" * 31 + "9")])
        self.assertIn("UNRESOLVED", record["effective_date"])
        SourceRecord.from_mapping(record)

    def test_source_identity_ignores_url_query_and_host_spelling(self):
        source = row()["url"]
        self.assertEqual(stable_id(source), stable_id(source + "?pvs=204"))
        self.assertEqual(stable_id(source), stable_id(source.replace("app.notion.com", "www.notion.so")))

    def test_identical_properties_have_identical_hashes(self):
        self.assertEqual(normalize_record(SPEC, row()), normalize_record(SPEC, copy.deepcopy(row())))

    def test_full_content_hash_cannot_be_git_sha1(self):
        record = normalize_record(SPEC, row())
        record["source_hash"] = "a" * 40
        with self.assertRaises(CensusError):
            SourceRecord.from_mapping(record)

    def test_nonfinite_numbers_and_missing_columns_are_rejected(self):
        for bad in (dict(row(), Population=float("nan")), {"url": row()["url"]}):
            with self.assertRaises(AcquisitionError):
                normalize_record(SPEC, bad)

    def test_page_size_validation_and_parameter_binding(self):
        for size in (0, 101, True):
            with self.assertRaises(AcquisitionError):
                page_query(SPEC, None, size)
        request = page_query(SPEC, "untrusted' input", 25)
        self.assertNotIn("untrusted", request["data"]["query"])
        self.assertEqual(request["data"]["params"], ["untrusted' input"])

    def test_actual_live_receipts_materialize_all_required_records(self):
        spec = importlib.util.spec_from_file_location("materialize_live_census", PROJECT / "tools/materialize_live_census.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        # This test keeps the initial required milestone independently reproducible.
        # Follow-on collection integration has its own live receipt regressions.
        outputs = module.build(include_extensions=False)
        manifest = json.loads(outputs[module.RECOVERY / "LIVE_CENSUS_ACQUISITION_MANIFEST_2026-09-17.json"])
        self.assertEqual(manifest["complete_collections"], {"business_registry": 90, "locations": 182,
            "consequence_ledger_a": 11, "consequence_ledger_b": 10})
        self.assertEqual(manifest["live_materialized_records"], 293)
        self.assertEqual(len({r["stable_source_id"] for r in manifest["records"]}), 293)
        snapshot = CensusSnapshot.from_mapping(json.loads(outputs[module.LATEST]))
        self.assertEqual(coverage_report(snapshot)["gate"], "CLOSED")
        self.assertEqual(manifest["core_coverage_counts"]["SIMULATED"], 0)
        reconciliation = json.loads(outputs[module.RECOVERY / "CONSEQUENCE_LEDGER_RECONCILIATION_2026-09-17.json"])
        self.assertEqual((len(reconciliation["rows"]), len(reconciliation["links"])), (21, 7))
        self.assertEqual((reconciliation["unmatched_a"], reconciliation["unmatched_b"]), (4, 3))
        diff = json.loads(outputs[module.RECOVERY / "LIVE_EMPIRE_SOURCE_CENSUS_DIFF_2026-09-17.json"])
        self.assertEqual((len(diff["added"]), len(diff["removed"])), (293, 0))
        self.assertEqual(outputs, module.build(include_extensions=False))


if __name__ == "__main__":
    unittest.main()