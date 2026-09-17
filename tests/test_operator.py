from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal

PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
sys.path.insert(0, str(SRC))

from baen_economy.operator import (
    _ledger_preview,
    _notion_dry_run,
    _plan_payload,
    _result_semantic_body,
    _roll_manifest_event,
    get_ledger_preview,
    get_notion_dry_run,
    get_report,
    initialize_campaign,
    run_month,
    status,
    verify_database,
    render_report,
)
from baen_economy.operator_codec import canonical_hash, with_content_hash
from baen_economy.operator_dice import classify_3d6, empty_roll_manifest, roll_preview_checks
from baen_economy.operator_store import CampaignStore, StoreError
from baen_economy.scenarios import load_scenario


class OperatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="economy operator ")
        self.addCleanup(self.temporary.cleanup)
        self.database = Path(self.temporary.name) / "laden preview.sqlite"

    def initialize(self, database: Path | None = None) -> Path:
        target = database or self.database
        initialize_campaign(
            target,
            campaign_id="laden-low",
            scenario_id="operation-laden-table",
        )
        return target

    def test_scenario_keeps_source_facts_and_assumptions_separate(self) -> None:
        scenario = load_scenario("operation-laden-table")
        self.assertFalse(scenario.payload["canonical"])
        self.assertEqual(scenario.payload["mode"], "preview")
        self.assertEqual(
            scenario.payload["source_anchor"]["economy_timeline_mapping"],
            "unresolved_CAN-001",
        )
        fact_keys = set(scenario.payload["sourced_facts"])
        assumption_keys = {item["key"] for item in scenario.payload["assumptions"]}
        self.assertNotIn("route_capacity_tons_per_period", fact_keys)
        self.assertIn("route_capacity_tons_per_period", assumption_keys)
        self.assertFalse(scenario.payload["permissions"]["notion_write"])
        self.assertFalse(scenario.payload["permissions"]["ledger_post"])
        self.assertEqual(scenario.opening_snapshot().prices, ())

    def test_two_period_laden_preview_matches_acceptance_numbers(self) -> None:
        self.initialize()
        period_1 = run_month(self.database, period_index=1, commit=True)
        self.assertEqual(period_1["summary"]["shipment_requested_tons"], "1200")
        self.assertEqual(period_1["summary"]["shipment_dispatched_tons"], "900")
        self.assertEqual(period_1["summary"]["shipment_shortfall_tons"], "300")
        self.assertEqual(period_1["summary"]["closing_supplier_tons"], "300")
        self.assertEqual(period_1["summary"]["closing_transit_tons"], "900")
        self.assertEqual(period_1["summary"]["conservation_residual_tons"], "0")
        self.assertEqual(period_1["summary"]["shortage_tons"], "not_modeled")

        period_2 = run_month(self.database, period_index=2, commit=True)
        self.assertEqual(period_2["summary"]["arrived_tons"], "882.00")
        self.assertEqual(period_2["summary"]["transit_loss_tons"], "18.00")
        self.assertEqual(period_2["summary"]["consumed_tons"], "300")
        self.assertEqual(period_2["summary"]["shortage_tons"], "0")
        self.assertEqual(period_2["summary"]["closing_longsaddle_tons"], "582.00")
        self.assertEqual(period_2["summary"]["closing_supplier_tons"], "300")
        self.assertEqual(period_2["summary"]["conservation_residual_tons"], "0.00")
        self.assertEqual(period_2["journal_postings"], 0)
        self.assertEqual(period_2["notion_writes"], 0)
        with CampaignStore.open(self.database) as store:
            self.assertEqual(store.latest_snapshot().prices, ())

    def test_no_commit_is_a_full_dry_run_with_no_history_mutation(self) -> None:
        self.initialize()
        before = status(self.database)["history"]
        preview = run_month(self.database, period_index=1, commit=False)
        after = status(self.database)["history"]
        self.assertFalse(preview["committed"])
        self.assertEqual(before, after)
        committed = run_month(self.database, period_index=1, commit=True)
        self.assertEqual(preview["closing_state_hash"], committed["closing_state_hash"])

    def test_reopen_and_exact_retry_are_durable_and_idempotent(self) -> None:
        self.initialize()
        first = run_month(
            self.database,
            period_index=1,
            commit=True,
            seed="operator-demo-1",
            include_preview_checks=True,
        )
        reopened = status(self.database)
        self.assertEqual(reopened["current_period"], 1)
        before = reopened["history"]
        retry = run_month(
            self.database,
            period_index=1,
            commit=True,
            seed="operator-demo-1",
            include_preview_checks=True,
        )
        self.assertTrue(retry["replayed_existing_commit"])
        self.assertEqual(first["run_hash"], retry["run_hash"])
        self.assertEqual(before, status(self.database)["history"])

    def test_two_concurrent_exact_commits_create_one_descendant(self) -> None:
        self.initialize()

        def commit_once() -> dict[str, object]:
            return run_month(self.database, period_index=1, commit=True)

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: commit_once(), range(2)))
        self.assertEqual({item["run_hash"] for item in outcomes}, {outcomes[0]["run_hash"]})
        self.assertEqual(sum(bool(item["replayed_existing_commit"]) for item in outcomes), 1)
        history = status(self.database)["history"]
        self.assertEqual(history["month_runs"], 1)
        self.assertEqual(history["snapshots"], 2)

    def test_two_concurrent_initializers_leave_one_verified_database(self) -> None:
        def initialize_once() -> str:
            try:
                self.initialize()
                return "initialized"
            except StoreError:
                return "refused"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: initialize_once(), range(2)))
        self.assertCountEqual(outcomes, ["initialized", "refused"])
        self.assertEqual(verify_database(self.database)["status"], "ok")

    def test_retry_with_different_options_is_a_hard_conflict(self) -> None:
        self.initialize()
        run_month(self.database, period_index=1, commit=True)
        with self.assertRaisesRegex(StoreError, "different run options"):
            run_month(
                self.database,
                period_index=1,
                commit=True,
                seed="changed",
                include_preview_checks=True,
            )

    def test_actual_initialization_fails_closed_without_creating_database(self) -> None:
        with self.assertRaisesRegex(StoreError, "actual/canonical initialization is locked"):
            initialize_campaign(
                self.database,
                campaign_id="actual",
                scenario_id="operation-laden-table",
                mode="actual",
            )
        self.assertFalse(self.database.exists())

    def test_ledger_preview_is_nonpostable_and_fabricates_no_transaction(self) -> None:
        self.initialize()
        run_month(self.database, period_index=1, commit=True)
        preview = json.loads(get_ledger_preview(self.database, 1))
        self.assertFalse(preview["postable"])
        self.assertEqual(preview["transactions"], [])
        self.assertEqual(preview["posting_count"], 0)
        self.assertEqual(
            preview["blocked_intents"][0]["accounting_treatment"],
            "prospective liability; never revenue",
        )
        body = dict(preview)
        digest = body.pop("content_hash")
        self.assertEqual(digest, canonical_hash(body))

    def test_notion_dry_run_is_nonexecutable_and_applies_nothing(self) -> None:
        self.initialize()
        run_month(self.database, period_index=1, commit=True)
        proposal = json.loads(get_notion_dry_run(self.database, 1))
        self.assertEqual(proposal["capability"], "review_only")
        self.assertFalse(proposal["write_authorized"])
        self.assertFalse(proposal["write_attempted"])
        self.assertEqual(proposal["applied_count"], 0)
        self.assertEqual(proposal["eligible_items"], [])
        self.assertFalse(proposal["blocked_suggestions"][0]["eligible"])
        serialized = json.dumps(proposal).lower()
        for forbidden in ("authorization bearer", "http method", "api endpoint"):
            self.assertNotIn(forbidden, serialized)

    def test_seeded_dice_record_every_face_target_modifier_margin_and_outcome(self) -> None:
        first = roll_preview_checks(
            campaign_id="laden-low",
            timeline_id="preview:operation-laden-table:illustrative-low-v1",
            period_index=1,
            seed="stable-seed",
        )
        second = roll_preview_checks(
            campaign_id="laden-low",
            timeline_id="preview:operation-laden-table:illustrative-low-v1",
            period_index=1,
            seed="stable-seed",
        )
        self.assertEqual(first, second)
        self.assertEqual(first["campaign_execution_rolls_resolved"], 0)
        for roll in first["rolls"]:
            self.assertEqual(len(roll["dice"]), 3)
            self.assertTrue(all(1 <= face <= 6 for face in roll["dice"]))
            self.assertEqual(roll["total"], sum(roll["dice"]))
            self.assertEqual(
                roll["margin"], roll["effective_target"] - roll["total"]
            )
            self.assertIn("outcome", roll)

    def test_gurps_critical_boundaries_are_skill_dependent(self) -> None:
        self.assertEqual(classify_3d6(total=5, effective_target=15), "critical_success")
        self.assertEqual(classify_3d6(total=6, effective_target=16), "critical_success")
        self.assertEqual(classify_3d6(total=6, effective_target=15), "success_by_5_plus")
        self.assertEqual(classify_3d6(total=17, effective_target=15), "critical_failure")
        self.assertEqual(classify_3d6(total=17, effective_target=16), "failure")
        self.assertEqual(classify_3d6(total=18, effective_target=30), "critical_failure")
        self.assertEqual(classify_3d6(total=16, effective_target=6), "critical_failure")

    def test_no_write_dice_preview_requires_seed_and_then_matches_commit(self) -> None:
        self.initialize()
        with self.assertRaisesRegex(StoreError, "requires --seed"):
            run_month(
                self.database,
                period_index=1,
                commit=False,
                include_preview_checks=True,
            )
        preview = run_month(
            self.database,
            period_index=1,
            commit=False,
            seed="reproducible",
            include_preview_checks=True,
        )
        committed = run_month(
            self.database,
            period_index=1,
            commit=True,
            seed="reproducible",
            include_preview_checks=True,
        )
        self.assertEqual(preview["run_hash"], committed["run_hash"])
        self.assertEqual(preview["closing_state_hash"], committed["closing_state_hash"])

    def test_report_is_prose_first_and_keeps_money_blocked(self) -> None:
        self.initialize()
        run_month(self.database, period_index=1, commit=True)
        run_month(self.database, period_index=2, commit=True)
        report = get_report(self.database, 2)
        self.assertTrue(
            report.startswith(
                "# PREVIEW — NOT CANON — NOT WRITTEN TO NOTION OR THE LEDGER"
            )
        )
        self.assertIn("882.00 tons reached Longsaddle", report)
        self.assertIn("18.00 tons of illustrative loss", report)
        self.assertIn("prospective liability only", report)
        self.assertIn("Journal postings: 0", report)
        self.assertIn("Changes applied: 0", report)
        self.assertIn("## Replay audit", report)

    def test_two_independent_databases_make_identical_seeded_reports(self) -> None:
        other = Path(self.temporary.name) / "second preview.sqlite"
        for database in (self.database, other):
            self.initialize(database)
            run_month(
                database,
                period_index=1,
                commit=True,
                seed="same-1",
                include_preview_checks=True,
            )
            run_month(
                database,
                period_index=2,
                commit=True,
                seed="same-2",
                include_preview_checks=True,
            )
        self.assertEqual(get_report(self.database, 2), get_report(other, 2))

    def test_append_only_triggers_and_snapshot_tamper_verification(self) -> None:
        self.initialize()
        run_month(self.database, period_index=1, commit=True)
        connection = sqlite3.connect(self.database)
        self.addCleanup(connection.close)
        with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
            connection.execute("DELETE FROM month_runs")
        connection.rollback()
        connection.execute("DROP TRIGGER snapshots_no_update")
        connection.execute(
            "UPDATE snapshots SET payload_json = replace(payload_json, '1200', '1201') "
            "WHERE period_index = 0"
        )
        connection.commit()
        with self.assertRaises((StoreError, ValueError)):
            verify_database(self.database)

    def test_campaign_identity_is_immutable_and_missing_trigger_blocks_verify(self) -> None:
        self.initialize()
        connection = sqlite3.connect(self.database)
        self.addCleanup(connection.close)
        with self.assertRaisesRegex(sqlite3.IntegrityError, "identity is immutable"):
            connection.execute("UPDATE campaign SET campaign_id = 'altered'")
        connection.rollback()
        connection.execute("DROP TRIGGER campaign_identity_no_update")
        connection.commit()
        with self.assertRaisesRegex(StoreError, "safeguards are missing"):
            verify_database(self.database)

    def test_commit_rejects_self_hashed_false_result_summary(self) -> None:
        self.initialize()
        with CampaignStore.open(self.database) as store:
            campaign = store.campaign_record()
            scenario = campaign["scenario"]
            parent = store.latest_snapshot()
            plan = scenario.plan(1)
            from baen_economy.stockflow import advance

            execution = advance(scenario.model(), parent, plan)
            dice = empty_roll_manifest()
            semantic = _result_semantic_body(
                campaign=campaign,
                scenario=scenario,
                parent=parent,
                plan=plan,
                result=execution,
                roll_manifest=dice,
            )
            semantic["physical"]["shipment_dispatched_tons"] = "1"
            run_hash = canonical_hash(semantic)
            false_result = with_content_hash({**semantic, "run_hash": run_hash})
            ledger = _ledger_preview(false_result, scenario)
            notion = _notion_dry_run(false_result, scenario)
            with self.assertRaisesRegex(StoreError, "deterministic replay"):
                store.commit_run(
                    period_index=1,
                    expected_parent_hash=parent.state_hash,
                    request_options={
                        "scenario_hash": scenario.scenario_hash,
                        "period_index": 1,
                        "include_preview_checks": False,
                        "rng_mode": "none",
                        "seed_fingerprint": None,
                    },
                    closing_snapshot=execution.snapshot,
                    plan_payload=_plan_payload(plan),
                    result_payload=false_result,
                    roll_manifest=dice,
                    report_markdown=render_report(false_result),
                    ledger_preview=ledger,
                    notion_dry_run=notion,
                )
            self.assertEqual(store.history_counts()["month_runs"], 0)

    def test_commit_rejects_a_self_consistent_but_unauthorized_plan(self) -> None:
        self.initialize()
        with CampaignStore.open(self.database) as store:
            campaign = store.campaign_record()
            scenario = campaign["scenario"]
            parent = store.latest_snapshot()
            expected_plan = scenario.plan(1)
            altered_order = replace(
                expected_plan.shipment_orders[0], requested_quantity=Decimal("1")
            )
            altered_plan = replace(expected_plan, shipment_orders=(altered_order,))
            from baen_economy.stockflow import advance

            execution = advance(scenario.model(), parent, altered_plan)
            dice = empty_roll_manifest()
            semantic = _result_semantic_body(
                campaign=campaign,
                scenario=scenario,
                parent=parent,
                plan=altered_plan,
                result=execution,
                roll_manifest=dice,
            )
            run_hash = canonical_hash(semantic)
            result = with_content_hash({**semantic, "run_hash": run_hash})
            with self.assertRaisesRegex(StoreError, "locked scenario schedule"):
                store.commit_run(
                    period_index=1,
                    expected_parent_hash=parent.state_hash,
                    request_options={
                        "scenario_hash": scenario.scenario_hash,
                        "period_index": 1,
                        "include_preview_checks": False,
                        "rng_mode": "none",
                        "seed_fingerprint": None,
                    },
                    closing_snapshot=execution.snapshot,
                    plan_payload=_plan_payload(altered_plan),
                    result_payload=result,
                    roll_manifest=dice,
                    report_markdown=render_report(result),
                    ledger_preview=_ledger_preview(result, scenario),
                    notion_dry_run=_notion_dry_run(result, scenario),
                )
            self.assertEqual(store.history_counts()["month_runs"], 0)

    def test_commit_rejects_a_different_valid_dice_manifest(self) -> None:
        self.initialize()
        with CampaignStore.open(self.database) as store:
            campaign = store.campaign_record()
            scenario = campaign["scenario"]
            parent = store.latest_snapshot()
            plan = scenario.plan(1)
            from baen_economy.stockflow import advance

            execution = advance(scenario.model(), parent, plan)
            dice = empty_roll_manifest()
            semantic = _result_semantic_body(
                campaign=campaign,
                scenario=scenario,
                parent=parent,
                plan=plan,
                result=execution,
                roll_manifest=dice,
            )
            run_hash = canonical_hash(semantic)
            result = with_content_hash({**semantic, "run_hash": run_hash})
            ledger = _ledger_preview(result, scenario)
            notion = _notion_dry_run(result, scenario)
            different_dice = roll_preview_checks(
                campaign_id="laden-low",
                timeline_id=scenario.timeline_id,
                period_index=1,
                seed="different-valid-manifest",
            )
            with self.assertRaisesRegex(StoreError, "does not match the month result"):
                store.commit_run(
                    period_index=1,
                    expected_parent_hash=parent.state_hash,
                    request_options={
                        "scenario_hash": scenario.scenario_hash,
                        "period_index": 1,
                        "include_preview_checks": False,
                        "rng_mode": "none",
                        "seed_fingerprint": None,
                    },
                    closing_snapshot=execution.snapshot,
                    plan_payload=_plan_payload(plan),
                    result_payload=result,
                    roll_manifest=different_dice,
                    report_markdown=render_report(result),
                    ledger_preview=ledger,
                    notion_dry_run=notion,
                )
            self.assertEqual(store.history_counts()["month_runs"], 0)

    def test_request_options_reject_boolean_period_identity(self) -> None:
        self.initialize()
        with CampaignStore.open(self.database) as store:
            scenario = store.campaign_record()["scenario"]
            with self.assertRaisesRegex(StoreError, "concrete integer"):
                store._validate_request_options(
                    request_options={
                        "scenario_hash": scenario.scenario_hash,
                        "period_index": True,
                        "include_preview_checks": False,
                        "rng_mode": "none",
                        "seed_fingerprint": None,
                    },
                    period_index=1,
                    roll_manifest=empty_roll_manifest(),
                )

    def test_commit_rejects_self_hashed_but_false_dice_arithmetic(self) -> None:
        self.initialize()
        with CampaignStore.open(self.database) as store:
            campaign = store.campaign_record()
            scenario = campaign["scenario"]
            parent = store.latest_snapshot()
            dice = roll_preview_checks(
                campaign_id="laden-low",
                timeline_id=scenario.timeline_id,
                period_index=1,
                seed="false-arithmetic",
            )
            dice["rolls"][0]["total"] = 999
            dice["manifest_hash"] = canonical_hash(
                {key: value for key, value in dice.items() if key != "manifest_hash"}
            )
            plan = scenario.plan(
                1,
                authorizing_events=(_roll_manifest_event(scenario, 1, dice),),
            )
            from baen_economy.stockflow import advance

            execution = advance(scenario.model(), parent, plan)
            semantic = _result_semantic_body(
                campaign=campaign,
                scenario=scenario,
                parent=parent,
                plan=plan,
                result=execution,
                roll_manifest=dice,
            )
            run_hash = canonical_hash(semantic)
            result = with_content_hash({**semantic, "run_hash": run_hash})
            with self.assertRaisesRegex(StoreError, "total, margin, or outcome"):
                store.commit_run(
                    period_index=1,
                    expected_parent_hash=parent.state_hash,
                    request_options={
                        "scenario_hash": scenario.scenario_hash,
                        "period_index": 1,
                        "include_preview_checks": True,
                        "rng_mode": "seeded_preview",
                        "seed_fingerprint": dice["seed_fingerprint"],
                    },
                    closing_snapshot=execution.snapshot,
                    plan_payload=_plan_payload(plan),
                    result_payload=result,
                    roll_manifest=dice,
                    report_markdown=render_report(result),
                    ledger_preview=_ledger_preview(result, scenario),
                    notion_dry_run=_notion_dry_run(result, scenario),
                )
            self.assertEqual(store.history_counts()["month_runs"], 0)

    def test_period_gap_and_extra_profile_month_fail_without_partial_state(self) -> None:
        self.initialize()
        with self.assertRaisesRegex(StoreError, "next runnable period is 1"):
            run_month(self.database, period_index=2, commit=True)
        self.assertEqual(status(self.database)["history"]["month_runs"], 0)
        run_month(self.database, period_index=1, commit=True)
        run_month(self.database, period_index=2, commit=True)
        with self.assertRaisesRegex(ValueError, "defines periods 1 and 2 only"):
            run_month(self.database, period_index=3, commit=True)
        self.assertEqual(status(self.database)["history"]["month_runs"], 2)

    def test_database_cannot_be_placed_in_ledger_tree(self) -> None:
        forbidden = Path(self.temporary.name) / "campaign-finance-ledger" / "state.sqlite"
        with self.assertRaisesRegex(StoreError, "may not be written"):
            self.initialize(forbidden)

    def test_verify_checks_reopened_lineage_and_artifacts(self) -> None:
        self.initialize()
        run_month(self.database, period_index=1, commit=True)
        result = verify_database(self.database)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["snapshot_count"], 2)
        self.assertEqual(result["run_count"], 1)
        self.assertFalse(result["notion_write_capability"])
        self.assertFalse(result["ledger_post_capability"])

    def test_black_box_cli_journey_works_across_processes_with_spaces(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC)
        help_result = self.cli("--help", env=env)
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        for command in (
            "scenarios",
            "init",
            "status",
            "run-month",
            "report",
            "ledger-preview",
            "notion-dry-run",
            "verify",
        ):
            self.assertIn(command, help_result.stdout)
        initialized = self.cli(
            "init", str(self.database), "--campaign", "laden-low", env=env
        )
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        dry = self.cli(
            "run-month", str(self.database), "--period", "1", env=env
        )
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn("DRY RUN — NOT SAVED", dry.stdout)
        committed = self.cli(
            "run-month", str(self.database), "--period", "1", "--commit", env=env
        )
        self.assertEqual(committed.returncode, 0, committed.stderr)
        reopened = self.cli("status", str(self.database), env=env)
        self.assertEqual(json.loads(reopened.stdout)["current_period"], 1)
        report = self.cli("report", str(self.database), "--period", "1", env=env)
        self.assertTrue(report.stdout.startswith("# PREVIEW — NOT CANON"))
        verify = self.cli("verify", str(self.database), env=env)
        self.assertEqual(json.loads(verify.stdout)["status"], "ok")

    def test_black_box_json_and_existing_report_paths_never_traceback(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC)
        self.assertEqual(
            self.cli("init", str(self.database), env=env).returncode,
            0,
        )
        dry = self.cli(
            "run-month",
            str(self.database),
            "--period",
            "1",
            "--roll-preview-checks",
            "--seed",
            "json-safe",
            "--format",
            "json",
            env=env,
        )
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertFalse(json.loads(dry.stdout)["committed"])
        committed = self.cli(
            "run-month",
            str(self.database),
            "--period",
            "1",
            "--commit",
            "--roll-preview-checks",
            "--seed",
            "json-safe",
            "--format",
            "json",
            env=env,
        )
        self.assertEqual(committed.returncode, 0, committed.stderr)
        self.assertTrue(json.loads(committed.stdout)["committed"])
        replayed_report = self.cli(
            "run-month",
            str(self.database),
            "--period",
            "1",
            "--roll-preview-checks",
            "--seed",
            "json-safe",
            "--format",
            "report",
            env=env,
        )
        self.assertEqual(replayed_report.returncode, 0, replayed_report.stderr)
        self.assertTrue(replayed_report.stdout.startswith("# PREVIEW — NOT CANON"))
        self.assertNotIn("Traceback", replayed_report.stderr)

    def cli(self, *arguments: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "baen_economy", *arguments],
            cwd=PROJECT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )


if __name__ == "__main__":
    unittest.main()
