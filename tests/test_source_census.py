from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
sys.path.insert(0, str(SRC))

from baen_economy.source_census import (
    CENSUS_SCHEMA,
    CensusError,
    CensusSnapshot,
    CoverageState,
    DecisionProvenance,
    assert_coverage_gate,
    canonical_hash,
    coverage_report,
    diff_snapshots,
    load_census_snapshot,
)


def hashed_collection(
    *,
    source_id: str = "notion:test",
    complete: bool = True,
    rows: int = 1,
) -> dict[str, object]:
    body = {
        "stable_source_id": source_id,
        "source_url": f"collection://{source_id}",
        "title": source_id,
        "source_class": "businesses_branches",
        "row_count": rows,
        "enumeration_complete": complete,
    }
    return {**body, "source_hash": canonical_hash(body)}


def hashed_record(
    *,
    source_id: str = "record:test",
    state: CoverageState = CoverageState.SIMULATED,
    relevance: str = "active",
) -> dict[str, object]:
    body = {
        "stable_source_id": source_id,
        "source_url": f"https://example.invalid/{source_id}",
        "title": source_id,
        "source_class": "businesses_branches",
        "region_location": "test",
        "effective_date": "Day 7 Hammer 1495 DR",
        "effective_status": "test",
        "direct_relations": [],
        "numeric_properties": {"value": 1},
        "narrative_facts": ["test fact"],
        "simulation_relevance": relevance,
        "coverage_state": state.value,
        "provenance": DecisionProvenance.SOURCE_DERIVED.value,
    }
    return {**body, "source_hash": canonical_hash(body)}


def snapshot_mapping(
    *,
    collection: dict[str, object] | None = None,
    records: list[dict[str, object]] | None = None,
    unknown: int = 0,
) -> dict[str, object]:
    collection = collection or hashed_collection()
    records = records or [hashed_record()]
    body = {
        "schema": CENSUS_SCHEMA,
        "captured_at": "2026-09-17T09:27:00-04:00",
        "campaign_boundary": "Day 7 Hammer 1495 DR",
        "read_mode": "test_read_only",
        "repository_base_sha": "a" * 40,
        "source_collections": [collection],
        "records": records,
        "provisional_row_coverage": {
            "denominator_core_rows": int(collection["row_count"]),
            "SIMULATED": int(collection["row_count"]) - unknown,
            "UNKNOWN": unknown,
            "basis": "test",
        },
        "known_linked_authority_pages_outside_core_collections": 0,
        "notes": ["test"],
        "provenance": [
            {
                "choice": "test choice",
                "tag": DecisionProvenance.USER_RULED.value,
            }
        ],
    }
    return {**body, "snapshot_hash": canonical_hash(body)}


class SourceCensusTests(unittest.TestCase):
    def test_complete_simulated_snapshot_opens_gate(self) -> None:
        snapshot = CensusSnapshot.from_mapping(snapshot_mapping())
        report = assert_coverage_gate(snapshot)
        self.assertEqual(report["gate"], "OPEN")
        self.assertEqual(report["raw_core_rows"], 1)
        self.assertEqual(report["coverage_state_counts"], {"SIMULATED": 1})

    def test_repository_base_accepts_git_sha1_not_sha256_content_hash(self) -> None:
        mapping = snapshot_mapping()
        self.assertEqual(
            CensusSnapshot.from_mapping(mapping).repository_base_sha,
            "a" * 40,
        )
        mapping["repository_base_sha"] = "b" * 64
        body = {key: value for key, value in mapping.items() if key != "snapshot_hash"}
        mapping["snapshot_hash"] = canonical_hash(body)
        with self.assertRaisesRegex(CensusError, "Git SHA-1 object ID"):
            CensusSnapshot.from_mapping(mapping)

    def test_incomplete_collection_closes_gate(self) -> None:
        mapping = snapshot_mapping(
            collection=hashed_collection(complete=False),
            unknown=1,
        )
        snapshot = CensusSnapshot.from_mapping(mapping)
        with self.assertRaisesRegex(CensusError, "source collections are not fully enumerated"):
            assert_coverage_gate(snapshot)

    def test_active_conflict_and_missing_mechanics_are_blockers(self) -> None:
        records = [
            hashed_record(source_id="conflict", state=CoverageState.CONFLICT),
            hashed_record(
                source_id="missing",
                state=CoverageState.MISSING_MECHANICS,
            ),
        ]
        snapshot = CensusSnapshot.from_mapping(
            snapshot_mapping(records=records)
        )
        report = coverage_report(snapshot)
        self.assertEqual(report["gate"], "CLOSED")
        self.assertEqual(
            {item["coverage_state"] for item in report["active_blockers"]},
            {"CONFLICT", "MISSING_MECHANICS"},
        )

    def test_future_historical_and_superseded_are_visible_but_not_active(self) -> None:
        records = [
            hashed_record(
                source_id="future",
                state=CoverageState.FUTURE,
                relevance="not_active",
            ),
            hashed_record(
                source_id="historical",
                state=CoverageState.HISTORICAL,
                relevance="not_active",
            ),
            hashed_record(
                source_id="superseded",
                state=CoverageState.SUPERSEDED,
                relevance="not_active",
            ),
        ]
        snapshot = CensusSnapshot.from_mapping(snapshot_mapping(records=records))
        report = assert_coverage_gate(snapshot)
        self.assertEqual(report["gate"], "OPEN")
        self.assertEqual(report["temporal_records"]["FUTURE"], ["future"])
        self.assertEqual(report["temporal_records"]["HISTORICAL"], ["historical"])
        self.assertEqual(report["temporal_records"]["SUPERSEDED"], ["superseded"])

    def test_unknown_core_rows_close_gate_even_without_material_record_blocker(self) -> None:
        collection = hashed_collection(rows=2)
        mapping = snapshot_mapping(collection=collection, unknown=1)
        snapshot = CensusSnapshot.from_mapping(mapping)
        with self.assertRaisesRegex(CensusError, "1 core rows remain UNKNOWN"):
            assert_coverage_gate(snapshot)

    def test_record_mutation_breaks_source_hash(self) -> None:
        mapping = snapshot_mapping()
        mapping["records"][0]["numeric_properties"]["value"] = 2
        body = {key: value for key, value in mapping.items() if key != "snapshot_hash"}
        mapping["snapshot_hash"] = canonical_hash(body)
        with self.assertRaisesRegex(CensusError, "source record hash mismatch"):
            CensusSnapshot.from_mapping(mapping)

    def test_duplicate_record_ids_are_rejected(self) -> None:
        record = hashed_record()
        mapping = snapshot_mapping(records=[record, copy.deepcopy(record)])
        with self.assertRaisesRegex(CensusError, "duplicate source record IDs"):
            CensusSnapshot.from_mapping(mapping)

    def test_snapshot_hash_catches_top_level_mutation(self) -> None:
        mapping = snapshot_mapping()
        mapping["campaign_boundary"] = "wrong"
        with self.assertRaisesRegex(CensusError, "snapshot hash mismatch"):
            CensusSnapshot.from_mapping(mapping)

    def test_diff_reports_added_removed_and_changed_records(self) -> None:
        previous = CensusSnapshot.from_mapping(
            snapshot_mapping(records=[hashed_record(source_id="same"), hashed_record(source_id="gone")])
        )
        changed = hashed_record(source_id="same")
        changed["narrative_facts"] = ["changed fact"]
        changed_body = {key: value for key, value in changed.items() if key != "source_hash"}
        changed["source_hash"] = canonical_hash(changed_body)
        current = CensusSnapshot.from_mapping(
            snapshot_mapping(records=[changed, hashed_record(source_id="new")])
        )
        diff = diff_snapshots(previous, current)
        self.assertEqual(diff["added"], ["new"])
        self.assertEqual(diff["removed"], ["gone"])
        self.assertEqual(diff["changed"], ["same"])
        self.assertEqual(diff["unchanged_count"], 0)

    def test_load_round_trip(self) -> None:
        mapping = snapshot_mapping()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "census.json"
            path.write_text(json.dumps(mapping), encoding="utf-8")
            snapshot = load_census_snapshot(path)
        self.assertEqual(snapshot.schema, CENSUS_SCHEMA)
        self.assertEqual(snapshot.snapshot_hash, mapping["snapshot_hash"])


if __name__ == "__main__":
    unittest.main()
