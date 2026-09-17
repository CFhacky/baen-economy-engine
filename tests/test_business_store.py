from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
sys.path.insert(0, str(SRC))

from baen_economy.business_store import (  # noqa: E402
    ArtifactValue,
    BusinessStore,
    BusinessStoreError,
)
from baen_economy.business_capacity import build_brickworks_partial_capacity  # noqa: E402
from baen_economy.business_month import (  # noqa: E402
    BUSINESS_PROFILE_ID,
    preview_business_month,
    render_business_report,
)
from baen_economy.notion_read import (  # noqa: E402
    BUSINESS_REGISTRY_DATA_SOURCE,
    make_read_snapshot,
)
from baen_economy.operator_codec import canonical_hash  # noqa: E402
from baen_economy.registry_export import verify_registry_export  # noqa: E402


FIXTURE = (
    PROJECT
    / "fixtures"
    / "registry-snapshots"
    / "business-registry-2026-08-29.json"
)
BRICKWORKS = "notion:321e821484b0816c87fbf0fee22835ad"


def fixture_payload() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def changed_valid_capture(payload: dict[str, object]) -> dict[str, object]:
    changed = deepcopy(payload)
    for row in changed["rows"]:
        if row["Entity"] == "Baen Brickworks":
            row["Monthly Cost"] = "2234"
            break
    changed["content_hash"] = make_read_snapshot(
        data_source_url=changed["data_source_url"],
        captured_at=changed["captured_at"],
        rows=changed["rows"],
        expected_row_count=changed["query"]["expected_row_count"],
        pagination_complete=changed["query"]["pagination_complete"],
    ).content_hash
    verify_registry_export(changed)
    return changed


class BusinessStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="business store ")
        self.addCleanup(self.temporary.cleanup)
        self.database = Path(self.temporary.name) / "business preview.sqlite"
        self.payload = fixture_payload()
        self.verified = verify_registry_export(self.payload)

    def create_with_registry(self) -> BusinessStore:
        return BusinessStore.create(self.database, registry_payload=self.payload)

    def commit_sample(self, store: BusinessStore, *, net: str = "1100"):
        return store.commit_run(
            registry_export_hash=self.verified.export_hash,
            source_record_id=BRICKWORKS,
            profile_id="brickworks-source-month-v1",
            period_key="eleint-1494-source-baseline",
            request={"seed_fingerprint": "1" * 64, "mode": "preview"},
            result={
                "schema": "tnp.business.store-test-preview/1",
                "canonical": False,
                "monthly_revenue_gp": "3333",
                "monthly_cost_gp": "2233",
                "net_gp": net,
            },
            artifacts={
                "report_markdown": ArtifactValue(
                    "text/markdown; charset=utf-8", "# PREVIEW\n"
                ),
                "notion_review_diff": {
                    "schema": "tnp.notion.row-property-review/1",
                    "write_authorized": False,
                    "applied_count": 0,
                },
            },
        )

    def real_month_arguments(self) -> dict[str, object]:
        month = "Eleint 1494 store preview"
        seed = "store-request-binding-seed"
        result = preview_business_month(
            self.verified,
            BRICKWORKS,
            month,
            seed,
            vara_active=False,
        )
        return {
            "registry_export_hash": self.verified.export_hash,
            "source_record_id": BRICKWORKS,
            "profile_id": BUSINESS_PROFILE_ID,
            "period_key": month,
            "request": {
                "month_label": month,
                "seed_fingerprint": hashlib.sha256(seed.encode()).hexdigest(),
                "assumptions": deepcopy(result["assumptions"]),
                "raw_seed_persisted": False,
            },
            "result": result,
            "artifacts": {
                "report_markdown": ArtifactValue(
                    "text/markdown; charset=utf-8", render_business_report(result)
                ),
                "notion_review_diff": result["notion_review_diff"],
                "ledger_preview": result["ledger_preview"],
                "dice_manifest": result["dice_manifest"],
                "capacity_profile": build_brickworks_partial_capacity(
                    self.verified
                ).to_dict(),
            },
        }

    def test_atomic_create_imports_exact_snapshot_and_all_rows(self) -> None:
        with self.create_with_registry() as store:
            loaded = store.load_registry_export(self.verified.export_hash)
            self.assertEqual(loaded.snapshot_hash, self.verified.snapshot_hash)
            self.assertEqual(
                loaded.source_schema_hash, self.verified.source_schema_hash
            )
            self.assertEqual(loaded.row_hashes, self.verified.row_hashes)
            self.assertEqual(
                store.latest_registry_export().export_hash,
                self.verified.export_hash,
            )
            self.assertEqual(
                store.counts(),
                {
                    "registry_snapshots": 1,
                    "registry_rows": 90,
                    "registry_exports": 1,
                    "business_runs": 0,
                    "business_artifacts": 0,
                },
            )
            verification = store.verify()
            self.assertEqual(verification["status"], "ok")
            self.assertEqual(verification["registry_row_count"], 90)
            self.assertFalse(verification["notion_write_capability"])
            self.assertFalse(verification["ledger_post_capability"])

    def test_exact_registry_retry_is_a_noop(self) -> None:
        with self.create_with_registry() as store:
            before = store.counts()
            summary, replayed = store.import_registry(self.payload)
            self.assertTrue(replayed)
            self.assertEqual(summary["export_hash"], self.verified.export_hash)
            self.assertEqual(store.counts(), before)

    def test_same_capture_with_changed_content_is_an_immutable_conflict(self) -> None:
        changed = changed_valid_capture(self.payload)
        with self.create_with_registry() as store:
            before = store.counts()
            with self.assertRaisesRegex(BusinessStoreError, "already stored"):
                store.import_registry(changed)
            self.assertEqual(store.counts(), before)
            self.assertEqual(store.verify()["status"], "ok")

    def test_failed_atomic_create_removes_new_database(self) -> None:
        incomplete = deepcopy(self.payload)
        incomplete["rows"] = incomplete["rows"][:-1]
        with self.assertRaises(BusinessStoreError):
            BusinessStore.create(self.database, registry_payload=incomplete)
        self.assertFalse(self.database.exists())

    def test_duplicate_json_key_is_rejected_before_import(self) -> None:
        export = Path(self.temporary.name) / "duplicate.json"
        source = FIXTURE.read_text(encoding="utf-8")
        source = source.replace(
            '"schema": "tnp.registry.read-export/1",',
            '"schema": "tnp.registry.read-export/1",\n  "schema": "tnp.registry.read-export/1",',
            1,
        )
        export.write_text(source, encoding="utf-8")
        with BusinessStore.create(self.database) as store:
            with self.assertRaisesRegex(BusinessStoreError, "duplicate JSON key"):
                store.import_registry_path(export)
            self.assertEqual(store.counts()["registry_exports"], 0)

    def test_snapshot_and_rows_are_append_only_and_sealed(self) -> None:
        with self.create_with_registry() as store:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
                store.connection.execute(
                    "UPDATE registry_rows SET entity_name = 'Altered'"
                )
            store.connection.rollback()
            raw = sqlite3.connect(self.database)
            self.addCleanup(raw.close)
            self.assertEqual(raw.execute("PRAGMA recursive_triggers").fetchone()[0], 0)
            with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
                raw.execute(
                    """
                    INSERT OR REPLACE INTO registry_exports (
                        export_hash, snapshot_hash, source_schema_hash, content_hash,
                        data_source_url, captured_at, row_count, property_count, export_json
                    )
                    SELECT export_hash, snapshot_hash, source_schema_hash, ?,
                           data_source_url, captured_at, row_count, property_count, export_json
                    FROM registry_exports LIMIT 1
                    """,
                    ("0" * 64,),
                )
            raw.rollback()
            self.assertEqual(store.verify()["status"], "ok")
            with self.assertRaisesRegex(sqlite3.IntegrityError, "sealed"):
                store.connection.execute(
                    """
                    INSERT INTO registry_rows (
                        snapshot_hash, source_record_id, row_hash,
                        entity_name, source_url, row_json
                    ) VALUES (?, 'notion:late', ?, 'Late', 'https://app.notion.com/late', '{}')
                    """,
                    (self.verified.snapshot_hash, "0" * 64),
                )
            store.connection.rollback()

    def test_business_bundle_is_hash_bound_persisted_and_idempotent(self) -> None:
        with self.create_with_registry() as store:
            first, replayed = self.commit_sample(store)
            self.assertFalse(replayed)
            self.assertEqual(first["source_record_id"], BRICKWORKS)
            self.assertEqual(
                first["source_row_hash"], self.verified.row_hashes[BRICKWORKS]
            )
            self.assertEqual(
                first["registry_source_schema_hash"],
                self.verified.source_schema_hash,
            )
            self.assertEqual(set(first["artifacts"]), {
                "report_markdown", "notion_review_diff"
            })
            self.assertEqual(store.latest_run()["run_hash"], first["run_hash"])
            self.assertEqual(
                store.artifact(first["run_hash"], "report_markdown"),
                "# PREVIEW\n",
            )
            with self.assertRaisesRegex(BusinessStoreError, "missing its absent"):
                store.artifact(first["run_hash"], "absent")
            retry, replayed = self.commit_sample(store)
            self.assertTrue(replayed)
            self.assertEqual(first["run_hash"], retry["run_hash"])
            self.assertEqual(store.counts()["business_runs"], 1)
            self.assertEqual(store.counts()["business_artifacts"], 2)
            self.assertEqual(store.verify()["status"], "ok")

    def test_changed_business_result_for_same_period_is_rejected_atomically(self) -> None:
        with self.create_with_registry() as store:
            self.commit_sample(store)
            before = store.counts()
            with self.assertRaisesRegex(BusinessStoreError, "different immutable content"):
                self.commit_sample(store, net="999")
            self.assertEqual(store.counts(), before)

    def test_unknown_source_row_cannot_enter_a_business_run(self) -> None:
        with self.create_with_registry() as store:
            with self.assertRaisesRegex(BusinessStoreError, "no source row"):
                store.commit_run(
                    registry_export_hash=self.verified.export_hash,
                    source_record_id="notion:00000000000000000000000000000000",
                    profile_id="fixture",
                    period_key="one",
                    request={},
                    result={"canonical": False},
                    artifacts={"result": {}},
                )
            self.assertEqual(store.counts()["business_runs"], 0)

    def test_business_result_must_be_explicitly_non_canonical(self) -> None:
        with self.create_with_registry() as store:
            for result in ({}, {"canonical": True}, {"canonical": 0}):
                with self.subTest(result=result):
                    with self.assertRaisesRegex(
                        BusinessStoreError, "explicitly non-canonical"
                    ):
                        store.commit_run(
                            registry_export_hash=self.verified.export_hash,
                            source_record_id=BRICKWORKS,
                            profile_id="fixture",
                            period_key="one",
                            request={},
                            result=result,
                            artifacts={"result": {}},
                        )
            with self.assertRaisesRegex(BusinessStoreError, "month result is invalid"):
                store.commit_run(
                    registry_export_hash=self.verified.export_hash,
                    source_record_id=BRICKWORKS,
                    profile_id="fixture",
                    period_key="semantic-forgery",
                    request={},
                    result={
                        "schema": "tnp.business.month-preview/1",
                        "canonical": False,
                    },
                    artifacts={"result": {}},
                )
            with self.assertRaisesRegex(BusinessStoreError, "profile and schema"):
                store.commit_run(
                    registry_export_hash=self.verified.export_hash,
                    source_record_id=BRICKWORKS,
                    profile_id=BUSINESS_PROFILE_ID,
                    period_key="schema-bypass",
                    request={},
                    result={
                        "schema": "tnp.business.store-test-preview/1",
                        "canonical": False,
                    },
                    artifacts={"result": {}},
                )
            decimal_count = self.real_month_arguments()
            decimal_count["result"]["campaign_state_rolls_resolved"] = Decimal(0)
            result_body = dict(decimal_count["result"])
            result_body.pop("content_hash")
            decimal_count["result"]["content_hash"] = canonical_hash(result_body)
            with self.assertRaisesRegex(
                BusinessStoreError, "business month result is invalid"
            ):
                store.commit_run(**decimal_count)
            self.assertEqual(store.counts()["business_runs"], 0)
            self.assertEqual(store.counts()["business_artifacts"], 0)

    def test_month_request_profile_and_period_must_match_the_result(self) -> None:
        mutations = {
            "profile": lambda args: args.update(profile_id="unreviewed-profile"),
            "period": lambda args: args.update(period_key="wrong period"),
            "request month": lambda args: args["request"].update(
                month_label="wrong month"
            ),
            "seed fingerprint": lambda args: args["request"].update(
                seed_fingerprint="0" * 64
            ),
            "raw seed flag": lambda args: args["request"].update(
                raw_seed_persisted=True
            ),
            "extra option": lambda args: args["request"].update(
                posting_approved=True
            ),
        }
        with self.create_with_registry() as store:
            for label, mutate in mutations.items():
                with self.subTest(label=label):
                    arguments = self.real_month_arguments()
                    mutate(arguments)
                    with self.assertRaisesRegex(
                        BusinessStoreError, "business month result is invalid"
                    ):
                        store.commit_run(**arguments)
            arguments = self.real_month_arguments()
            arguments["request"]["assumptions"]["market"] = "boom"
            with self.assertRaisesRegex(
                BusinessStoreError, "business month result is invalid"
            ):
                store.commit_run(**arguments)
            self.assertEqual(store.counts()["business_runs"], 0)

    def test_latest_helpers_reject_an_empty_store(self) -> None:
        with BusinessStore.create(self.database) as store:
            with self.assertRaisesRegex(BusinessStoreError, "no registry export"):
                store.latest_registry_export()
            with self.assertRaisesRegex(BusinessStoreError, "no committed run"):
                store.latest_run()

    def test_business_runs_and_artifacts_are_append_only_and_sealed(self) -> None:
        with self.create_with_registry() as store:
            run, _ = self.commit_sample(store)
            with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
                store.connection.execute(
                    "UPDATE business_runs SET result_hash = ? WHERE run_hash = ?",
                    ("f" * 64, run["run_hash"]),
                )
            store.connection.rollback()
            with self.assertRaisesRegex(sqlite3.IntegrityError, "sealed"):
                store.connection.execute(
                    """
                    INSERT INTO business_artifacts (
                        run_hash, kind, media_type, payload, payload_hash
                    ) VALUES (?, 'late', 'text/plain', 'x', ?)
                    """,
                    (run["run_hash"], "0" * 64),
                )
            store.connection.rollback()

    def test_verify_detects_missing_guard_before_trusting_payloads(self) -> None:
        with self.create_with_registry() as store:
            store.connection.execute("DROP TRIGGER registry_exports_no_update")
            store.connection.execute(
                "UPDATE registry_exports SET content_hash = ?",
                ("0" * 64,),
            )
            with self.assertRaisesRegex(BusinessStoreError, "safeguards are missing"):
                store.verify()

    def test_same_name_noop_guard_is_rejected_before_verify_or_append(self) -> None:
        with self.create_with_registry() as store:
            store.connection.execute("DROP TRIGGER registry_rows_no_update")
            store.connection.execute(
                """
                CREATE TRIGGER registry_rows_no_update
                BEFORE UPDATE ON registry_rows
                BEGIN SELECT 1; END
                """
            )
            with self.assertRaisesRegex(BusinessStoreError, "SQL has drifted"):
                store.verify()
            with self.assertRaisesRegex(BusinessStoreError, "SQL has drifted"):
                store.import_registry(self.payload)
            with self.assertRaisesRegex(BusinessStoreError, "SQL has drifted"):
                self.commit_sample(store)

        alternate = Path(self.temporary.name) / "recursive trigger state.sqlite"
        with BusinessStore.create(alternate, registry_payload=self.payload) as store:
            self.assertEqual(
                store.connection.execute("PRAGMA recursive_triggers").fetchone()[0],
                1,
            )
            store.connection.execute("PRAGMA recursive_triggers = OFF")
            with self.assertRaisesRegex(BusinessStoreError, "safeguards are disabled"):
                store.verify()

    def test_verify_detects_registry_index_tamper_with_guards_present(self) -> None:
        with self.create_with_registry() as store:
            store.connection.execute("DROP TRIGGER registry_exports_no_update")
            store.connection.execute(
                "UPDATE registry_exports SET content_hash = ?",
                ("0" * 64,),
            )
            store.connection.execute(
                """
                CREATE TRIGGER registry_exports_no_update
                BEFORE UPDATE ON registry_exports
                BEGIN SELECT RAISE(ABORT, 'registry export receipts are append-only'); END
                """
            )
            with self.assertRaisesRegex(BusinessStoreError, "index"):
                store.verify()

    def test_concurrent_exact_run_commits_one_bundle(self) -> None:
        with self.create_with_registry():
            pass

        def commit_once() -> tuple[str, bool]:
            with BusinessStore.open(self.database) as store:
                run, replayed = self.commit_sample(store)
                return run["run_hash"], replayed

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: commit_once(), range(2)))
        self.assertEqual({item[0] for item in outcomes}, {outcomes[0][0]})
        self.assertEqual(sum(item[1] for item in outcomes), 1)
        with BusinessStore.open(self.database) as store:
            self.assertEqual(store.counts()["business_runs"], 1)
            self.assertEqual(store.verify()["status"], "ok")

    def test_database_path_cannot_target_ledger_tree(self) -> None:
        forbidden = (
            Path(self.temporary.name)
            / "campaign-finance-ledger"
            / "business.sqlite"
        )
        with self.assertRaisesRegex(BusinessStoreError, "may not be written"):
            BusinessStore.create(forbidden)


if __name__ == "__main__":
    unittest.main()
