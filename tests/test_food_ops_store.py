from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
sys.path.insert(0, str(SRC))

from baen_economy.food_ops_store import (  # noqa: E402
    AQUACULTURE_PLAN,
    AQUACULTURE_PLAN_SCHEMA,
    CROP_PLAN,
    CROP_PLAN_SCHEMA,
    FOOD_SECTOR_MONTH,
    FOOD_SECTOR_MONTH_SCHEMA,
    LONGSADDLE_PLAN,
    LONGSADDLE_PLAN_SCHEMA,
    FoodOpsStore,
    FoodOpsStoreError,
    export_html,
    export_markdown,
    validate_food_ops_database_path,
)
from baen_economy.food_sector import preview_food_sector_month  # noqa: E402
from baen_economy.operator_codec import canonical_hash  # noqa: E402


def sector_request() -> dict[str, object]:
    return {
        "campaign_date": "7 Hammer 1495 DR",
        "seed_fingerprint": hashlib.sha256(b"test-sector-seed").hexdigest(),
        "raw_seed_persisted": False,
        "sectors": ["Agriculture", "Aquaculture"],
    }


def sector_result() -> dict[str, object]:
    return {
        "schema": FOOD_SECTOR_MONTH_SCHEMA,
        "mode": "preview",
        "canonical": False,
        "decision_brief": {
            "Source": [
                {"label": "Employees", "value": 63},
                {"label": "Monthly revenue", "value": "26500 gp"},
            ],
            "Assumption": ["Vara actively supervises Agriculture"],
            "Derived": [
                {"label": "Proposed net", "value": "5950 gp"},
            ],
            "Unknown": ["Whether the pond and pool inventories overlap"],
        },
        "rolls": [
            {
                "sector": "Agriculture",
                "faces": [3, 4, 2],
                "target": 15,
                "margin": 6,
                "outcome": "success",
            }
        ],
        "notion_write_capability": False,
        "ledger_post_capability": False,
    }


def longsaddle_request() -> dict[str, object]:
    return {
        "population": 11000,
        "required_tons_low": "1200",
        "required_tons_high": "1500",
        "procured_tons": "0",
    }


def longsaddle_result() -> dict[str, object]:
    body: dict[str, object] = {
        "schema": LONGSADDLE_PLAN_SCHEMA,
        "mode": "preview",
        "canonical": False,
        "source_facts": {
            "population": 11000,
            "budget_gp": "65000-95000",
        },
        "assumptions": {
            "shipment_loss_rate": "0.02",
        },
        "derived_results": {
            "arriving_tons": "882.00",
            "financing_gap_gp": "12500.00",
        },
        "unknowns": ["Exact opening stock"],
    }
    body["content_hash"] = canonical_hash(body)
    return body


def production_result(schema: str, selection: str) -> dict[str, object]:
    body: dict[str, object] = {
        "schema": schema,
        "planning_only": True,
        "canonical": False,
        "selection": selection,
        "decision_brief": {
            "Source": {"selection": selection},
            "Assumption": {"capacity": "1000"},
            "Derived": {"output": {"low": "100", "high": "120"}},
            "Unknown": {"current_site_allocation": None},
        },
        "safety": {
            "notion_write_capability": False,
            "ledger_write_capability": False,
            "campaign_time_advanced": False,
        },
    }
    body["content_hash"] = canonical_hash(body)
    return body


class FoodOpsStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="food ops store ")
        self.addCleanup(self.temporary.cleanup)
        self.database = Path(self.temporary.name) / "food previews.sqlite"

    def test_create_has_explicit_zero_write_capabilities(self) -> None:
        with FoodOpsStore.create(self.database) as store:
            self.assertEqual(
                store.metadata_record(),
                {
                    "singleton": 1,
                    "schema_version": 2,
                    "store_kind": "food_operator_preview",
                    "authority_mode": "preview",
                    "canonical": 0,
                    "notion_write_capability": 0,
                    "ledger_write_capability": 0,
                    "ledger_post_capability": 0,
                },
            )
            self.assertEqual(
                store.counts(),
                {
                    "food_scenarios": 0,
                    FOOD_SECTOR_MONTH: 0,
                    LONGSADDLE_PLAN: 0,
                    AQUACULTURE_PLAN: 0,
                    CROP_PLAN: 0,
                },
            )
            verification = store.verify()
            self.assertEqual(verification["status"], "ok")
            self.assertFalse(verification["canonical"])
            self.assertFalse(verification["notion_write_capability"])
            self.assertFalse(verification["ledger_write_capability"])
            self.assertFalse(verification["ledger_post_capability"])

    def test_both_artifact_kinds_are_hash_bound_listed_and_reopened(self) -> None:
        with FoodOpsStore.create(self.database) as store:
            sector, replayed = store.save_food_sector_month(
                "food:hammer-1495",
                sector_request(),
                sector_result(),
            )
            self.assertFalse(replayed)
            plan, replayed = store.save_longsaddle_plan(
                "longsaddle:low-case",
                longsaddle_request(),
                longsaddle_result(),
            )
            self.assertFalse(replayed)
            self.assertEqual(sector["kind"], FOOD_SECTOR_MONTH)
            self.assertEqual(plan["kind"], LONGSADDLE_PLAN)
            self.assertEqual(
                sector["request_hash"], canonical_hash(sector_request())
            )
            self.assertEqual(
                plan["result_hash"], canonical_hash(longsaddle_result())
            )
            self.assertEqual(
                sector["bundle_hash"], canonical_hash(sector["manifest"])
            )
            self.assertEqual(
                [item["scenario_id"] for item in store.list_scenarios()],
                ["food:hammer-1495", "longsaddle:low-case"],
            )
            self.assertEqual(
                [item["scenario_id"] for item in store.list_scenarios(LONGSADDLE_PLAN)],
                ["longsaddle:low-case"],
            )
            self.assertEqual(store.verify()["scenario_count"], 2)

        with FoodOpsStore.open(self.database) as reopened:
            loaded = reopened.get_scenario("food:hammer-1495")
            self.assertEqual(loaded["result"], sector_result())
            self.assertEqual(
                reopened.load_scenario("longsaddle:low-case")["bundle_hash"],
                plan["bundle_hash"],
            )

    def test_real_food_sector_preview_round_trips_and_exports(self) -> None:
        seed = "store integration seed"
        result = preview_food_sector_month(
            month_label="Hammer 1495 food preview",
            seed=seed,
        )
        request = {
            "month_label": "Hammer 1495 food preview",
            "seed_fingerprint": hashlib.sha256(seed.encode("utf-8")).hexdigest(),
            "raw_seed_persisted": False,
        }
        with FoodOpsStore.create(self.database) as store:
            saved, replayed = store.save_food_sector_month(
                "food:real-engine-preview", request, result
            )
            self.assertFalse(replayed)
            self.assertEqual(saved["result"], result)
            markdown = store.export_markdown("food:real-engine-preview")
            self.assertIn("Monthly revenue gp: 26500", markdown)
            self.assertIn("Physical production: not resolved", markdown)
            self.assertEqual(store.verify()["status"], "ok")

    def test_exact_retry_is_noop_but_changed_content_is_conflict(self) -> None:
        with FoodOpsStore.create(self.database) as store:
            first, replayed = store.save_scenario(
                "food:hammer-1495",
                FOOD_SECTOR_MONTH,
                sector_request(),
                sector_result(),
            )
            self.assertFalse(replayed)
            retry, replayed = store.save_scenario(
                "food:hammer-1495",
                FOOD_SECTOR_MONTH,
                sector_request(),
                sector_result(),
            )
            self.assertTrue(replayed)
            self.assertEqual(retry, first)
            changed = sector_result()
            changed["rolls"][0]["faces"] = [6, 6, 6]
            before = store.counts()
            with self.assertRaisesRegex(
                FoodOpsStoreError, "different immutable content"
            ):
                store.save_scenario(
                    "food:hammer-1495",
                    FOOD_SECTOR_MONTH,
                    sector_request(),
                    changed,
                )
            self.assertEqual(store.counts(), before)
            with self.assertRaisesRegex(
                FoodOpsStoreError, "different immutable content"
            ):
                store.save_scenario(
                    "food:hammer-1495",
                    LONGSADDLE_PLAN,
                    longsaddle_request(),
                    longsaddle_result(),
                )
            self.assertEqual(store.verify()["scenario_count"], 1)

    def test_aquaculture_and_crop_plans_round_trip_and_export(self) -> None:
        with FoodOpsStore.create(self.database) as store:
            aquaculture, replayed = store.save_aquaculture_plan(
                "aquaculture:tilapia",
                {"scenario_id": "aquaculture:tilapia", "species_id": "tilapia"},
                production_result(AQUACULTURE_PLAN_SCHEMA, "Tilapia"),
            )
            self.assertFalse(replayed)
            crop, replayed = store.save_crop_plan(
                "crop:wheat",
                {"scenario_id": "crop:wheat", "crop_id": "wheat"},
                production_result(CROP_PLAN_SCHEMA, "Wheat"),
            )
            self.assertFalse(replayed)
            self.assertEqual(aquaculture["kind"], AQUACULTURE_PLAN)
            self.assertEqual(crop["kind"], CROP_PLAN)
            self.assertIn("Tilapia", store.export_html("aquaculture:tilapia"))
            self.assertIn("Wheat", store.export_markdown("crop:wheat"))
            verification = store.verify()
            self.assertEqual(verification["aquaculture_plan_count"], 1)
            self.assertEqual(verification["crop_plan_count"], 1)

    def test_invalid_kind_schema_float_and_capability_are_rejected(self) -> None:
        with FoodOpsStore.create(self.database) as store:
            with self.assertRaisesRegex(FoodOpsStoreError, "kind must be one of"):
                store.save_scenario(
                    "wrong:kind", "food", {}, sector_result()
                )
            with self.assertRaisesRegex(FoodOpsStoreError, "must use schema"):
                store.save_scenario(
                    "wrong:schema",
                    FOOD_SECTOR_MONTH,
                    {},
                    longsaddle_result(),
                )
            with self.assertRaisesRegex(FoodOpsStoreError, "binary floating-point"):
                store.save_food_sector_month(
                    "wrong:float", {"loss_rate": 0.02}, sector_result()
                )
            unsafe = sector_result()
            unsafe["notion_write_capability"] = True
            with self.assertRaisesRegex(FoodOpsStoreError, "cannot enable"):
                store.save_food_sector_month("wrong:notion", {}, unsafe)
            canonical = sector_result()
            canonical["canonical"] = True
            with self.assertRaisesRegex(FoodOpsStoreError, "cannot claim canonical"):
                store.save_food_sector_month("wrong:canonical", {}, canonical)
            forged = longsaddle_result()
            forged["derived_results"]["arriving_tons"] = "999"
            with self.assertRaisesRegex(FoodOpsStoreError, "content hash does not match"):
                store.save_longsaddle_plan("wrong:hash", {}, forged)
            self.assertEqual(store.counts()["food_scenarios"], 0)

    def test_rows_are_append_only_and_insert_or_replace_cannot_bypass_guards(self) -> None:
        with FoodOpsStore.create(self.database) as store:
            saved, _ = store.save_food_sector_month(
                "food:hammer-1495", sector_request(), sector_result()
            )
            with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
                store.connection.execute(
                    "UPDATE food_scenarios SET result_hash = ? WHERE scenario_id = ?",
                    ("0" * 64, saved["scenario_id"]),
                )
            store.connection.rollback()
            with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
                store.connection.execute(
                    "DELETE FROM food_scenarios WHERE scenario_id = ?",
                    (saved["scenario_id"],),
                )
            store.connection.rollback()
            with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
                store.connection.execute(
                    """
                    INSERT OR REPLACE INTO food_scenarios
                    SELECT * FROM food_scenarios WHERE scenario_id = ?
                    """,
                    (saved["scenario_id"],),
                )
            store.connection.rollback()
            self.assertEqual(store.verify()["status"], "ok")

    def test_verify_rejects_missing_or_same_name_noop_guard(self) -> None:
        with FoodOpsStore.create(self.database) as store:
            store.connection.execute("DROP TRIGGER food_scenarios_no_update")
            with self.assertRaisesRegex(FoodOpsStoreError, "safeguards are missing"):
                store.verify()
            store.connection.execute(
                """
                CREATE TRIGGER food_scenarios_no_update BEFORE UPDATE ON food_scenarios
                BEGIN SELECT 1; END
                """
            )
            with self.assertRaisesRegex(FoodOpsStoreError, "safeguards are missing"):
                store.save_food_sector_month(
                    "food:hammer-1495", sector_request(), sector_result()
                )

    def test_verify_detects_payload_tamper_after_exact_guard_is_restored(self) -> None:
        with FoodOpsStore.create(self.database) as store:
            store.save_food_sector_month(
                "food:hammer-1495", sector_request(), sector_result()
            )
            store.connection.execute("DROP TRIGGER food_scenarios_no_update")
            store.connection.execute(
                "UPDATE food_scenarios SET result_hash = ?",
                ("0" * 64,),
            )
            store.connection.execute(
                """
                CREATE TRIGGER food_scenarios_no_update BEFORE UPDATE ON food_scenarios
                BEGIN SELECT RAISE(ABORT, 'food scenarios are append-only'); END
                """
            )
            with self.assertRaisesRegex(FoodOpsStoreError, "does not match"):
                store.verify()

    def test_markdown_and_html_are_standalone_labelled_and_escaped(self) -> None:
        result = sector_result()
        result["decision_brief"]["Unknown"] = ["Water <script>alert(1)</script>"]
        with FoodOpsStore.create(self.database) as store:
            saved, _ = store.save_food_sector_month(
                "food:brief", sector_request(), result
            )
            markdown = store.export_markdown("food:brief")
            html = store.export_html("food:brief")
            for heading in ("Source", "Assumption", "Derived", "Unknown"):
                self.assertIn(f"## {heading}", markdown)
                self.assertIn(f"<h2>{heading}</h2>", html)
            self.assertIn("Employees: 63", markdown)
            self.assertIn("Proposed net: 5950 gp", markdown)
            self.assertTrue(html.startswith("<!doctype html>"))
            self.assertIn("<meta charset=\"utf-8\">", html)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
            self.assertNotIn("<script>alert(1)</script>", html)
            self.assertEqual(export_markdown(saved), markdown)
            self.assertEqual(export_html(saved), html)

    def test_export_falls_back_to_readable_derived_fields(self) -> None:
        minimal = {
            "schema": FOOD_SECTOR_MONTH_SCHEMA,
            "canonical": False,
            "net_gp": "5950",
            "businesses": [{"name": "Blacklake Fisheries", "net_gp": "2000"}],
        }
        markdown = export_markdown(minimal)
        self.assertIn("## Source\n\n- None recorded in this preview.", markdown)
        self.assertIn("Net gp: 5950", markdown)
        self.assertIn("Blacklake Fisheries", markdown)

    def test_path_guard_keeps_durable_database_out_of_repository(self) -> None:
        with self.assertRaisesRegex(FoodOpsStoreError, "outside the repository"):
            validate_food_ops_database_path(PROJECT / "food-ops.sqlite")
        allowed = PROJECT / "tests" / "temp" / "food-ops.sqlite"
        self.assertEqual(validate_food_ops_database_path(allowed), allowed.resolve())
        with self.assertRaisesRegex(FoodOpsStoreError, "canonical ledger"):
            validate_food_ops_database_path(
                Path(self.temporary.name)
                / "campaign-finance-ledger"
                / "food.sqlite"
            )

    def test_missing_invalid_id_and_existing_file_are_rejected(self) -> None:
        with self.assertRaisesRegex(FoodOpsStoreError, "does not exist"):
            FoodOpsStore.open(self.database)
        with FoodOpsStore.create(self.database) as store:
            with self.assertRaisesRegex(FoodOpsStoreError, "scenario ID"):
                store.get_scenario("contains a space")
            with self.assertRaisesRegex(FoodOpsStoreError, "is missing"):
                store.get_scenario("missing:scenario")
        with self.assertRaisesRegex(FoodOpsStoreError, "refusing to overwrite"):
            FoodOpsStore.create(self.database)

    def test_concurrent_exact_retry_commits_one_bundle(self) -> None:
        FoodOpsStore.create(self.database).close()

        def save_once() -> tuple[str, bool]:
            with FoodOpsStore.open(self.database) as store:
                record, replayed = store.save_food_sector_month(
                    "food:concurrent", sector_request(), sector_result()
                )
                return str(record["bundle_hash"]), replayed

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: save_once(), range(2)))
        self.assertEqual(len({item[0] for item in outcomes}), 1)
        self.assertEqual(sorted(item[1] for item in outcomes), [False, True])
        with FoodOpsStore.open(self.database) as store:
            self.assertEqual(store.verify()["scenario_count"], 1)


if __name__ == "__main__":
    unittest.main()
