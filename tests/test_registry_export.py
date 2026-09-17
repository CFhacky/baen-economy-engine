from __future__ import annotations

import copy
from decimal import Context, localcontext
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
sys.path.insert(0, str(SRC))

from baen_economy.notion_read import _content_hash  # noqa: E402
from baen_economy.operator_codec import canonical_hash  # noqa: E402
from baen_economy.registry import stable_source_record_id  # noqa: E402
from baen_economy.registry_export import (  # noqa: E402
    REGISTRY_DATABASE_URL,
    REGISTRY_EXPECTED_ROW_COUNT,
    REGISTRY_PAGE_RECEIPT_SCHEMA,
    REGISTRY_ORDERED_SOURCE_IDS_HASH,
    REGISTRY_ROW_HASH_SCHEMA,
    RegistryExportError,
    _page_source_ids_hash,
    _property_schema_payload,
    _typed_value,
    export_summary,
    load_registry_export,
    verify_registry_export,
)


FIXTURE = (
    PROJECT
    / "fixtures"
    / "registry-snapshots"
    / "business-registry-2026-08-29.json"
)


class RegistryExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def fresh_payload(self) -> dict[str, object]:
        return copy.deepcopy(self.payload)

    def rehash_rows(self, payload: dict[str, object]) -> None:
        payload["content_hash"] = _content_hash(payload["rows"])

    def source_record_ids(self, payload: dict[str, object]) -> tuple[str, ...]:
        return tuple(
            stable_source_record_id(row["url"])
            for row in payload["rows"]
        )

    def test_checked_in_export_is_complete_typed_and_audit_blocked(self) -> None:
        export = load_registry_export(FIXTURE)
        summary = export_summary(export)

        self.assertEqual(export.read_snapshot.expected_row_count, 90)
        self.assertEqual(len(export.rows_by_source_id), 90)
        self.assertEqual(len(export.row_hashes), 90)
        self.assertEqual(len(set(export.row_hashes.values())), 90)
        self.assertEqual(export.audit.blocker_count, 5)
        self.assertEqual(
            export.content_hash,
            "d40285fc31dfee4290a8adb6d336113ba36674b292c27016216baa63afa4fa22",
        )
        self.assertEqual(
            export.source_schema_hash,
            "3e18484d5f06e3530a80e3e50a6e11c3f1e3e9c90fb4da531f95c7c4df6f5562",
        )
        self.assertEqual(
            export.snapshot_hash,
            "a4196a7afaa0102f10d1d5fe752f9842ed17fcee6933ead468446d9343b71f1d",
        )
        self.assertEqual(
            export.export_hash,
            "9c3f74ef052e49e9f1d62b1a76a1d8e3a504baf64566a016f668b06fe7a6f034",
        )
        self.assertEqual(
            export.audit.raw_totals,
            {
                "capital_invested": "31086700",
                "employees": "14954",
                "monthly_cost": "612259",
                "monthly_revenue": "1194405",
            },
        )
        self.assertFalse(summary["notion_write_capability"])
        self.assertIn("not a cryptographic", summary["verification_scope"])
        self.assertFalse(self.payload["source_schema"]["write_targetable"])
        self.assertFalse(
            self.payload["source_schema"]["notion_property_ids_available"]
        )
        self.assertTrue(
            all(
                item["notion_property_id"] is None
                for item in self.payload["source_schema"]["properties"]
            )
        )
        for prohibited in ("write", "update", "apply", "execute"):
            self.assertFalse(hasattr(export, prohibited))

    def test_loader_rejects_duplicate_json_object_keys_at_any_depth(self) -> None:
        text = FIXTURE.read_text(encoding="utf-8")
        duplicated = text.replace(
            '      "Capital Invested": "30000",',
            '      "Capital Invested": "30000",\n'
            '      "Capital Invested": "99999",',
            1,
        )
        with tempfile.TemporaryDirectory(prefix="registry duplicate key ") as folder:
            path = Path(folder) / "duplicate.json"
            path.write_text(duplicated, encoding="utf-8")
            with self.assertRaisesRegex(
                RegistryExportError, "duplicate JSON object key: Capital Invested"
            ):
                load_registry_export(path)

    def test_database_url_is_an_exact_locked_identity(self) -> None:
        self.assertEqual(self.payload["database_url"], REGISTRY_DATABASE_URL)
        for replacement in (
            "https://evil.example/8ba47f60efe14c839fe14561543e07d1",
            "http://app.notion.com/p/8ba47f60efe14c839fe14561543e07d1?pvs=204",
            "https://app.notion.com/p/8ba47f60efe14c839fe14561543e07d1?pvs=999",
        ):
            with self.subTest(replacement=replacement):
                payload = self.fresh_payload()
                payload["database_url"] = replacement
                with self.assertRaisesRegex(RegistryExportError, "database URL"):
                    verify_registry_export(payload)

        for captured_at in (
            "2026-08-29T23:00:00-10:00",
            "2026-08-30T00:00:00+10:00",
            "2026-08-29T10:48:48.579000Z",
        ):
            with self.subTest(captured_at=captured_at):
                payload = self.fresh_payload()
                payload["captured_at"] = captured_at
                with self.assertRaisesRegex(RegistryExportError, "captured_at"):
                    verify_registry_export(payload)

    def test_registry_requires_exactly_ninety_rows(self) -> None:
        fewer = self.fresh_payload()
        fewer["rows"].pop()
        self.rehash_rows(fewer)
        with self.assertRaisesRegex(RegistryExportError, "row count"):
            verify_registry_export(fewer)

        more = self.fresh_payload()
        more["rows"].append(copy.deepcopy(more["rows"][0]))
        self.rehash_rows(more)
        with self.assertRaisesRegex(RegistryExportError, "row count"):
            verify_registry_export(more)
        self.assertEqual(REGISTRY_EXPECTED_ROW_COUNT, 90)

    def test_pagination_receipt_supports_a_verified_cursor_chain(self) -> None:
        payload = self.fresh_payload()
        source_ids = self.source_record_ids(payload)
        payload["query"]["page_receipts"] = [
            {
                "page_index": 1,
                "request_cursor": None,
                "response_row_count": 45,
                "source_record_ids_hash": _page_source_ids_hash(1, source_ids[:45]),
                "has_more": True,
                "next_cursor": "cursor:45",
            },
            {
                "page_index": 2,
                "request_cursor": "cursor:45",
                "response_row_count": 45,
                "source_record_ids_hash": _page_source_ids_hash(2, source_ids[45:]),
                "has_more": False,
                "next_cursor": None,
            },
        ]
        verified = verify_registry_export(payload)
        self.assertEqual(len(verified.rows_by_source_id), 90)

        payload["query"]["page_receipts"][1]["request_cursor"] = "wrong"
        with self.assertRaisesRegex(RegistryExportError, "cursor chain"):
            verify_registry_export(payload)

    def test_pagination_receipt_rejects_missing_filtered_or_unbound_pages(self) -> None:
        mutations = {
            "missing": lambda query: query.update(page_receipts=[]),
            "filtered": lambda query: query.update(filter={"Status": "Operational"}),
            "wrong_ids": lambda query: query["page_receipts"][0].update(
                source_record_ids_hash="0" * 64
            ),
            "unterminated": lambda query: query["page_receipts"][0].update(
                has_more=True, next_cursor="cursor:more"
            ),
            "short_count": lambda query: query["page_receipts"][0].update(
                response_row_count=89
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                payload = self.fresh_payload()
                mutate(payload["query"])
                with self.assertRaises(RegistryExportError):
                    verify_registry_export(payload)

    def test_page_receipt_hash_is_domain_separated_and_order_bound(self) -> None:
        source_ids = self.source_record_ids(self.payload)
        expected = canonical_hash(
            {
                "schema": REGISTRY_PAGE_RECEIPT_SCHEMA,
                "page_index": 1,
                "source_record_ids": list(source_ids),
            }
        )
        self.assertEqual(
            self.payload["query"]["page_receipts"][0]["source_record_ids_hash"],
            expected,
        )
        swapped = (source_ids[1], source_ids[0], *source_ids[2:])
        self.assertNotEqual(expected, _page_source_ids_hash(1, swapped))
        self.assertEqual(expected, REGISTRY_ORDERED_SOURCE_IDS_HASH)

    def test_claimed_order_cannot_be_rewritten_with_its_mutable_receipt(self) -> None:
        payload = self.fresh_payload()
        payload["rows"][0], payload["rows"][1] = (
            payload["rows"][1],
            payload["rows"][0],
        )
        self.rehash_rows(payload)
        source_ids = self.source_record_ids(payload)
        payload["query"]["page_receipts"][0]["source_record_ids_hash"] = (
            _page_source_ids_hash(1, source_ids)
        )
        with self.assertRaisesRegex(RegistryExportError, "locked source ordering"):
            verify_registry_export(payload)

    def test_registry_totals_ignore_the_callers_decimal_context(self) -> None:
        expected = {
            "capital_invested": "31086700",
            "employees": "14954",
            "monthly_cost": "612259",
            "monthly_revenue": "1194405",
        }
        with localcontext(Context(prec=4)):
            self.assertEqual(load_registry_export(FIXTURE).audit.raw_totals, expected)

    def test_source_schema_and_its_hash_are_both_locked(self) -> None:
        payload = self.fresh_payload()
        payload["source_schema_hash"] = "0" * 64
        with self.assertRaisesRegex(RegistryExportError, "source schema hash"):
            verify_registry_export(payload)

        payload = self.fresh_payload()
        payload["source_schema"]["properties"][0]["source_type"] = "text"
        payload["source_schema_hash"] = canonical_hash(payload["source_schema"])
        with self.assertRaisesRegex(RegistryExportError, "source schema has drifted"):
            verify_registry_export(payload)

    def test_nondecimal_property_and_created_time_types_fail_closed(self) -> None:
        mutations = {
            "nested_notes": ("Notes", {"unexpected": ["shape"]}, "text property"),
            "numeric_created": ("createdTime", 7, "createdTime"),
            "boolean_city": ("City", False, "text property"),
        }
        for label, (field, value, message) in mutations.items():
            with self.subTest(label=label):
                payload = self.fresh_payload()
                payload["rows"][0][field] = value
                self.rehash_rows(payload)
                with self.assertRaisesRegex(RegistryExportError, message):
                    verify_registry_export(payload)

    def test_decimal_date_and_flag_encodings_fail_closed(self) -> None:
        mutations = {
            "numeric_decimal": ("Monthly Revenue", 9, "decimal property"),
            "bad_decimal": ("Monthly Revenue", " 9", "accepted form"),
            "boolean_flag": (
                "date:Last Updated 1:is_datetime",
                False,
                "flag property",
            ),
            "bad_date": ("date:Last Updated 1:start", "2026-99-99", "date property"),
        }
        dated_row_index = next(
            index
            for index, row in enumerate(self.payload["rows"])
            if row["date:Last Updated 1:start"] is not None
        )
        for label, (field, value, message) in mutations.items():
            with self.subTest(label=label):
                payload = self.fresh_payload()
                row_index = dated_row_index if field.startswith("date:") else 0
                payload["rows"][row_index][field] = value
                self.rehash_rows(payload)
                with self.assertRaisesRegex(RegistryExportError, message):
                    verify_registry_export(payload)

    def test_machine_date_components_cannot_contradict_each_other(self) -> None:
        payload = self.fresh_payload()
        payload["rows"][0]["date:Last Updated 1:start"] = None
        payload["rows"][0]["date:Last Updated 1:is_datetime"] = 0
        self.rehash_rows(payload)
        with self.assertRaisesRegex(RegistryExportError, "without a start"):
            verify_registry_export(payload)

    def test_duplicate_source_identity_fails_even_with_ninety_rows(self) -> None:
        payload = self.fresh_payload()
        payload["rows"][1]["id"] = payload["rows"][0]["id"]
        payload["rows"][1]["url"] = payload["rows"][0]["url"]
        self.rehash_rows(payload)
        with self.assertRaisesRegex(RegistryExportError, "repeats a source record"):
            verify_registry_export(payload)

    def test_row_uuid_and_page_url_require_canonical_source_forms(self) -> None:
        payload = self.fresh_payload()
        payload["rows"][0]["id"] = payload["rows"][0]["id"].upper()
        self.rehash_rows(payload)
        with self.assertRaisesRegex(RegistryExportError, "canonical UUID"):
            verify_registry_export(payload)

        payload = self.fresh_payload()
        payload["rows"][0]["url"] = payload["rows"][0]["url"].replace(
            "app.notion.com", "app.notion.com:8443"
        )
        self.rehash_rows(payload)
        with self.assertRaisesRegex(RegistryExportError, "same record"):
            verify_registry_export(payload)

    def test_row_and_property_hashes_bind_explicit_schemas_and_types(self) -> None:
        export = load_registry_export(FIXTURE)
        source_record_id = next(iter(export.rows_by_source_id))
        row = export.row(source_record_id)
        expected_row_hash = canonical_hash(
            {
                "schema": REGISTRY_ROW_HASH_SCHEMA,
                "data_source_url": export.read_snapshot.data_source_url,
                "source_schema_hash": export.source_schema_hash,
                "source_record_id": source_record_id,
                "source_row": _typed_value(row),
            }
        )
        self.assertEqual(export.row_hashes[source_record_id], expected_row_hash)
        self.assertNotEqual(
            export.row_hashes[source_record_id], canonical_hash(_typed_value(row))
        )

        property_name = "Monthly Revenue"
        expected_property_hash = canonical_hash(
            {
                "schema": "tnp.registry.source-property/1",
                "snapshot_hash": export.snapshot_hash,
                "source_schema_hash": export.source_schema_hash,
                "source_record_id": source_record_id,
                "row_hash": expected_row_hash,
                "property_schema": _property_schema_payload(property_name),
                "source_value": _typed_value(row[property_name]),
            }
        )
        self.assertEqual(
            export.property_hash(source_record_id, property_name),
            expected_property_hash,
        )
        self.assertNotEqual(_typed_value("1"), _typed_value(1))


if __name__ == "__main__":
    unittest.main()
