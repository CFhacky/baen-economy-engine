from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from baen_economy.regional_cli import (
    FinanceAdapter,
    MarketTransportAdapter,
    MonthRequest,
    ProductionAdapter,
    RegionalAdapters,
    ScenarioAdapter,
    ScenarioRequest,
    main,
)


class FakeScenario(ScenarioAdapter):
    def initialize(self, request: ScenarioRequest) -> dict[str, object]:
        return {
            "scenario": {
                "scenario_id": request.scenario_id,
                "source": "unit-test-adapter",
            },
            "state": {
                "inventories": {"clay": "100", "bricks": "0"},
                "prices": {"bricks": "0.10"},
                "bank": {"deposits": "1000", "loan_principal": "500"},
                "treasury": {"cash": "100"},
            },
        }


class FakeProduction(ProductionAdapter):
    def simulate(self, request: MonthRequest) -> dict[str, object]:
        return {
            "production": {
                "input_consumed": "50",
                "output_produced": "5000",
            },
            "labor": {"workers": 20, "payroll": "80.00"},
            "state": {
                "inventories": {"clay": "50", "bricks": "5000"},
                "workers": 20,
                "payroll_paid": "80.00",
            },
        }


class FakeMarketTransport(MarketTransportAdapter):
    def simulate(
        self,
        request: MonthRequest,
        production: dict[str, object],
    ) -> dict[str, object]:
        return {
            "transport": {"quantity_moved": "3000", "capacity": "4000"},
            "market": {
                "shortage_quantity": "1000",
                "price_before": "0.10",
                "price_after": "0.12",
                "demand_receipts": [
                    {
                        "shortage_quantity": "1000",
                        "price_before_gp_per_unit": "0.10",
                        "price_after_gp_per_unit": "0.12",
                    }
                ],
            },
            "state": {
                "delivered_bricks": "3000",
                "shortage_bricks": "1000",
                "brick_price": "0.12",
            },
        }


class FakeFinance(FinanceAdapter):
    def simulate(
        self,
        request: MonthRequest,
        production: dict[str, object],
        market_transport: dict[str, object],
    ) -> dict[str, object]:
        return {
            "banking": {
                "deposit_change": "200.00",
                "interest_accrued": "5.00",
                "principal_repaid": "25.00",
            },
            "treasury": {"receipts_total": "30.00"},
            "journal": {
                "balanced": True,
                "total_debits": "340.00",
                "total_credits": "340.00",
                "imbalance": "0",
            },
            "state": {
                "deposits": "1200.00",
                "loan_principal": "475.00",
                "treasury_cash": "130.00",
            },
        }


ADAPTERS = RegionalAdapters(
    scenario=FakeScenario(),
    production=FakeProduction(),
    market_transport=FakeMarketTransport(),
    finance=FakeFinance(),
)


class RegionalCliUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="regional cli unit ")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.database = self.root / "campaign state.sqlite"

    def command(
        self,
        *arguments: object,
        adapters: RegionalAdapters | None = ADAPTERS,
    ) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            return_code = main(
                [str(argument) for argument in arguments], adapters=adapters
            )
        return return_code, stdout.getvalue(), stderr.getvalue()

    def json_command(self, *arguments: object) -> dict[str, object]:
        code, stdout, stderr = self.command(*arguments, "--format", "json")
        self.assertEqual(code, 0, stderr)
        return json.loads(stdout)

    def initialize(self, *, seed: str = "known-regional-seed") -> dict[str, object]:
        return self.json_command(
            "init",
            self.database,
            "--scenario",
            "baen-regional-mvp",
            "--seed",
            seed,
        )

    def test_fresh_directory_full_persistent_user_path(self) -> None:
        initialized = self.initialize()
        self.assertTrue(initialized["initialized"])
        self.assertEqual(initialized["period"], 0)
        self.assertEqual(initialized["notion_writes"], 0)
        self.assertEqual(initialized["canonical_ledger_postings"], 0)
        self.assertTrue(Path(initialized["scenario_path"]).is_file())
        self.assertTrue(Path(initialized["state_path"]).is_file())

        run = self.json_command("run-month", self.database, "--commit")
        self.assertTrue(run["committed"])
        self.assertTrue(run["changed"])
        self.assertNotEqual(run["prior_state_hash"], run["next_state_hash"])
        self.assertTrue(Path(run["state_path"]).is_file())
        self.assertTrue(Path(run["output_path"]).is_file())
        html_report = Path(run["html_report_path"])
        self.assertTrue(html_report.is_file())
        self.assertEqual(html_report.parent, self.database.parent.resolve())
        rendered = html_report.read_text(encoding="utf-8")
        self.assertIn("<!doctype html>", rendered)
        self.assertIn("Production and labour", rendered)
        self.assertIn("Accounting and safety check", rendered)
        self.assertIn("Notion writes: 0", rendered)
        self.assertNotIn("<script", rendered.lower())
        result = run["result"]
        self.assertEqual(
            set(result),
            {
                "schema_version",
                "scenario_id",
                "period",
                "canonical",
                "notion_writes",
                "canonical_ledger_postings",
                "production",
                "labor",
                "transport",
                "market",
                "banking",
                "treasury",
                "journal",
            },
        )
        self.assertEqual(result["production"]["input_consumed"], "50")
        self.assertEqual(result["labor"]["payroll"], "80.00")
        self.assertEqual(result["transport"]["quantity_moved"], "3000")
        self.assertEqual(
            result["market"]["demand_receipts"][0]["price_after_gp_per_unit"],
            "0.12",
        )
        self.assertTrue(result["journal"]["balanced"])

        report = self.json_command("report", self.database)
        self.assertEqual(report["period"], 1)
        self.assertEqual(report["state_hash"], run["next_state_hash"])
        self.assertEqual(report["latest_result"], result)
        self.assertEqual(Path(report["html_report_path"]), html_report)
        verified = self.json_command("verify", self.database)
        self.assertTrue(verified["valid"])
        self.assertEqual(verified["run_count"], 1)
        self.assertTrue(all(verified["checks"].values()))

    def test_simulate_month_alias_and_dry_run_do_not_mutate(self) -> None:
        initialized = self.initialize()
        dry = self.json_command("simulate-month", self.database)
        self.assertFalse(dry["committed"])
        self.assertNotEqual(dry["prior_state_hash"], dry["next_state_hash"])
        self.assertIsNone(dry["state_path"])
        self.assertIsNone(dry["output_path"])
        verified = self.json_command("verify", self.database)
        self.assertEqual(verified["run_count"], 0)
        self.assertEqual(verified["state_hash"], initialized["state_hash"])

    def test_seed_mismatch_fails_without_partial_month(self) -> None:
        self.initialize()
        code, stdout, stderr = self.command(
            "run-month",
            self.database,
            "--seed",
            "wrong-seed",
            "--commit",
            "--format",
            "json",
        )
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("seed does not match", stderr)
        verified = self.json_command("verify", self.database)
        self.assertEqual(verified["run_count"], 0)

    def test_same_seed_and_inputs_are_reproducible_across_databases(self) -> None:
        first = self.initialize(seed="replay-seed")
        first_run = self.json_command("run-month", self.database, "--commit")
        other = self.root / "other.sqlite"
        second = self.json_command(
            "init", other, "--scenario", "baen-regional-mvp", "--seed", "replay-seed"
        )
        second_run = self.json_command("run-month", other, "--commit")
        self.assertEqual(first["state_hash"], second["state_hash"])
        self.assertEqual(first_run["result_hash"], second_run["result_hash"])
        self.assertEqual(first_run["next_state_hash"], second_run["next_state_hash"])

    def test_human_report_exposes_safety_and_operating_results(self) -> None:
        self.initialize()
        self.json_command("run-month", self.database, "--commit")
        code, stdout, stderr = self.command("report", self.database)
        self.assertEqual(code, 0, stderr)
        self.assertIn("Notion writes: 0", stdout)
        self.assertIn("Canonical ledger postings: 0", stdout)
        self.assertIn(
            "Production: 0 active businesses; unit-specific input/output receipts stored",
            stdout,
        )
        self.assertIn("Journal balanced: True", stdout)
        self.assertIn("Readable report:", stdout)

    def test_report_writes_a_custom_double_clickable_html_file(self) -> None:
        self.initialize()
        self.json_command("run-month", self.database, "--commit")
        readable = self.root / "My Readable Economy Report.html"
        payload = self.json_command(
            "report", self.database, "--output", readable
        )
        self.assertEqual(Path(payload["html_report_path"]), readable.resolve())
        self.assertTrue(readable.is_file())
        rendered = readable.read_text(encoding="utf-8")
        self.assertIn("Baen Regional Economy", rendered)
        self.assertIn("PREVIEW — NOT CANON", rendered)
        self.assertIn("Business, banking, and treasury", rendered)

    def test_verify_detects_tampered_readable_report(self) -> None:
        self.initialize()
        run = self.json_command("run-month", self.database, "--commit")
        Path(run["html_report_path"]).write_text(
            "<html>misleading report</html>", encoding="utf-8"
        )
        verified = self.json_command("verify", self.database)
        self.assertFalse(verified["valid"])
        self.assertFalse(verified["checks"]["readable_reports"])

    def test_verify_detects_tampered_output_artifact(self) -> None:
        self.initialize()
        run = self.json_command("run-month", self.database, "--commit")
        Path(run["output_path"]).write_text("{}\n", encoding="utf-8")
        verified = self.json_command("verify", self.database)
        self.assertFalse(verified["valid"])
        self.assertFalse(verified["checks"]["durable_artifacts"])

    def test_existing_database_is_not_overwritten(self) -> None:
        self.initialize()
        before = self.database.read_bytes()
        code, _, stderr = self.command(
            "init", self.database, "--seed", "another", "--format", "json"
        )
        self.assertEqual(code, 2)
        self.assertIn("database already exists", stderr)
        self.assertEqual(before, self.database.read_bytes())

    def test_verify_detects_database_hash_tampering(self) -> None:
        self.initialize()
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "UPDATE state_snapshot SET state_json = ? WHERE period = 0", ("{}",)
            )
        verified = self.json_command("verify", self.database)
        self.assertFalse(verified["valid"])
        self.assertFalse(verified["checks"]["state_hashes"])


if __name__ == "__main__":
    unittest.main()
