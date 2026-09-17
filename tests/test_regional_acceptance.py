from __future__ import annotations

from decimal import Context, Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Iterable, Mapping
import unittest


PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
SCENARIO_ID = "baen-regional-mvp"
SEED = "regional-acceptance-fixed-seed"


def _decimal(value: object, label: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise AssertionError(f"{label} must be a finite decimal, got {value!r}")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise AssertionError(f"{label} must be a finite decimal, got {value!r}") from exc
    if not result.is_finite():
        raise AssertionError(f"{label} must be finite, got {value!r}")
    return result


def _objects(value: object) -> Iterable[Mapping[str, object]]:
    """Yield every JSON object so assertions remain about outcomes, not layout depth."""

    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _objects(child)


def _records_with(
    value: object, *required_keys: str
) -> list[Mapping[str, object]]:
    required = set(required_keys)
    return [record for record in _objects(value) if required.issubset(record)]


class RegionalEconomyUserAcceptanceTests(unittest.TestCase):
    """Exercise the regional economy exactly through its durable CLI boundary."""

    maxDiff = None

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(
            prefix="baen regional acceptance path with spaces "
        )
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.working_directory = self.root / "operator working directory"
        self.working_directory.mkdir()
        self.environment = dict(os.environ)
        existing_pythonpath = self.environment.get("PYTHONPATH")
        self.environment["PYTHONPATH"] = (
            str(SRC)
            if not existing_pythonpath
            else str(SRC) + os.pathsep + existing_pythonpath
        )

    def cli(self, *arguments: object) -> dict[str, object]:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "baen_economy.regional_cli",
                *(str(argument) for argument in arguments),
            ],
            cwd=self.working_directory,
            env=self.environment,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            msg=(
                f"regional CLI failed: {' '.join(map(str, arguments))}\n"
                f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
            ),
        )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            self.fail(
                "regional CLI did not return one JSON document\n"
                f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}\n{exc}"
            )
        self.assertIsInstance(payload, dict)
        return payload

    def assert_envelope(
        self,
        payload: Mapping[str, object],
        *,
        command: str,
        database: Path,
    ) -> None:
        self.assertEqual(payload.get("command"), command)
        self.assertIs(payload.get("ok"), True)
        self.assertEqual(payload.get("scenario_id"), SCENARIO_ID)
        self.assertEqual(payload.get("notion_writes"), 0)
        self.assertEqual(payload.get("canonical_ledger_postings"), 0)
        self.assertEqual(Path(str(payload.get("database_path"))).resolve(), database.resolve())
        self.assertIsInstance(payload.get("seed_fingerprint"), str)
        self.assertNotEqual(payload.get("seed_fingerprint"), "")
        self.assertNotIn(SEED, json.dumps(payload, sort_keys=True))

    def initialize(self, database: Path) -> dict[str, object]:
        payload = self.cli(
            "init",
            database,
            "--scenario",
            SCENARIO_ID,
            "--allow-synthetic-demo",
            "--seed",
            SEED,
            "--format",
            "json",
        )
        self.assert_envelope(payload, command="init", database=database)
        self.assertIs(payload.get("initialized"), True)
        self.assertIsInstance(payload.get("state_hash"), str)
        self.assertEqual(len(str(payload["state_hash"])), 64)
        self.assertTrue(database.is_file())
        self.assertGreater(database.stat().st_size, 0)
        return payload

    def run_month(self, database: Path) -> dict[str, object]:
        payload = self.cli("run-month", database, "--commit", "--format", "json")
        self.assert_envelope(payload, command="run-month", database=database)
        self.assertIs(payload.get("committed"), True)
        self.assertIs(payload.get("changed"), True)
        self.assertNotEqual(payload.get("prior_state_hash"), payload.get("next_state_hash"))
        self.assertIsInstance(payload.get("result"), dict)
        return payload

    def assert_month_has_real_economic_activity(
        self, result: Mapping[str, object]
    ) -> None:
        for section in (
            "production",
            "labor",
            "transport",
            "market",
            "banking",
            "treasury",
            "journal",
        ):
            self.assertIn(section, result, f"monthly result is missing {section!r}")

        production = _records_with(
            result["production"],
            "entity_id",
            "input_consumed",
            "output_produced",
        )
        self.assertTrue(production, "no production receipt exposes inputs and outputs")
        self.assertTrue(
            any(
                _decimal(record["input_consumed"], "input_consumed") > 0
                and _decimal(record["output_produced"], "output_produced") > 0
                for record in production
            ),
            "no business consumed an input and produced an output",
        )
        active_producers = {
            str(record["entity_id"])
            for record in _records_with(
                result["production"], "entity_id", "output_produced"
            )
            if _decimal(record["output_produced"], "output_produced") > 0
        }
        self.assertGreaterEqual(
            len(active_producers),
            2,
            "the alleged regional month contains fewer than two active businesses",
        )

        # The named vertical slice is a clay -> brick -> construction chain, not
        # merely several unrelated producers.  Opening construction stock must
        # not hide a discarded Brickworks-to-construction route.
        brick_routes = _records_with(
            result["transport"], "route_id", "quantity_moved"
        )
        brick_demands = _records_with(
            result["market"], "demand_id", "consumed_quantity"
        )
        self.assertTrue(
            any(
                record["route_id"] == "route:bricks-to-construction"
                and _decimal(record["quantity_moved"], "brick route movement") > 0
                for record in brick_routes
            )
            or any(
                record["demand_id"] == "demand:construction-bricks"
                and _decimal(record["consumed_quantity"], "brick demand consumption")
                > 0
                for record in brick_demands
            ),
            "Brickworks output never reaches the downstream construction business",
        )

        labor = _records_with(result["labor"], "workers", "payroll")
        self.assertTrue(labor, "labor section exposes no workers/payroll receipt")
        self.assertTrue(
            any(
                _decimal(record["workers"], "workers") > 0
                and _decimal(record["payroll"], "payroll") > 0
                for record in labor
            ),
            "the month employed no workers or paid no payroll",
        )

        movements = _records_with(
            result["transport"], "quantity_moved", "capacity"
        )
        self.assertTrue(movements, "transport section exposes no movement/capacity receipt")
        moved_within_capacity = False
        for movement in movements:
            moved = _decimal(movement["quantity_moved"], "quantity_moved")
            capacity = _decimal(movement["capacity"], "capacity")
            self.assertGreaterEqual(moved, 0)
            self.assertGreater(capacity, 0)
            self.assertLessEqual(moved, capacity)
            moved_within_capacity = moved_within_capacity or moved > 0
        self.assertTrue(moved_within_capacity, "no goods moved during the month")

        responses = _records_with(
            result["market"],
            "shortage_quantity",
            "price_before_gp_per_unit",
            "price_after_gp_per_unit",
        )
        self.assertTrue(responses, "market section exposes no shortage/price receipt")
        self.assertTrue(
            any(
                _decimal(record["shortage_quantity"], "shortage_quantity") > 0
                and _decimal(
                    record["price_after_gp_per_unit"], "price_after_gp_per_unit"
                )
                > _decimal(
                    record["price_before_gp_per_unit"], "price_before_gp_per_unit"
                )
                for record in responses
            ),
            "no shortage caused an observable upward price response",
        )

        banking = result["banking"]
        self.assertIsInstance(banking, dict)
        deposit_change = _decimal(banking.get("deposit_change"), "deposit_change")
        interest = _decimal(banking.get("interest_accrued"), "interest_accrued")
        principal = _decimal(banking.get("principal_repaid"), "principal_repaid")
        self.assertNotEqual(deposit_change, 0, "customer deposits did not change")
        self.assertTrue(
            interest > 0 or principal > 0,
            "loans generated neither interest nor principal behavior",
        )

        treasury = result["treasury"]
        self.assertIsInstance(treasury, dict)
        self.assertGreater(
            _decimal(treasury.get("receipts_total"), "receipts_total"),
            0,
            "the treasury received nothing",
        )

        journal = result["journal"]
        self.assertIsInstance(journal, dict)
        self.assertIs(journal.get("balanced"), True)
        debits = _decimal(journal.get("total_debits"), "total_debits")
        credits = _decimal(journal.get("total_credits"), "total_credits")
        self.assertGreater(debits, 0)
        self.assertEqual(debits, credits)
        self.assertEqual(_decimal(journal.get("imbalance"), "imbalance"), 0)

        self.assertEqual(result.get("notion_writes"), 0)
        self.assertEqual(result.get("canonical_ledger_postings"), 0)

    def assert_operating_trade_reaches_the_books(
        self,
        state: Mapping[str, object],
        result: Mapping[str, object],
    ) -> None:
        delivered_trades = [
            record
            for record in _records_with(
                state,
                "trade_id",
                "seller_entity_id",
                "buyer_entity_id",
                "delivery_status",
                "settlement_status",
            )
            if record["seller_entity_id"] != record["buyer_entity_id"]
            and record["delivery_status"] == "delivered"
            and record["settlement_status"] == "settled_cash"
        ]
        self.assertTrue(
            delivered_trades,
            "the month contains no delivered, settled trade between businesses",
        )
        booked_trades = [
            record
            for record in _records_with(state, "transaction_id", "kind", "postings")
            if record["kind"] == "enterprise_trade"
        ]
        self.assertTrue(
            booked_trades,
            "the balanced books omit every delivered inter-business trade",
        )

        finance_state = state.get("finance")
        self.assertIsInstance(finance_state, dict)
        assumption = finance_state.get("assumption_receipt")
        actions = finance_state.get("realized_action_amounts")
        self.assertIsInstance(assumption, dict)
        self.assertIsInstance(actions, dict)
        self.assertIs(assumption.get("canonical"), False)
        self.assertEqual(
            assumption.get("authority"), "integration_preview_assumption"
        )
        self.assertEqual(actions.get("delivered_trade_count"), len(delivered_trades))

        depositor_id = str(assumption["depositor_id"])
        borrower_id = str(assumption["borrower_id"])
        depositor_receipts = sum(
            (
                _decimal(trade["goods_value_gp"], "depositor trade receipt")
                for trade in delivered_trades
                if trade["seller_entity_id"] == depositor_id
            ),
            Decimal(0),
        )
        borrower_receipts = sum(
            (
                _decimal(trade["goods_value_gp"], "borrower trade receipt")
                for trade in delivered_trades
                if trade["seller_entity_id"] == borrower_id
            ),
            Decimal(0),
        )
        borrower_trade_outflows = sum(
            (
                _decimal(trade["buyer_total_gp"], "borrower trade outflow")
                for trade in delivered_trades
                if trade["buyer_entity_id"] == borrower_id
            ),
            Decimal(0),
        )
        borrower_payroll = sum(
            (
                _decimal(line["payroll"], "borrower payroll")
                for line in _records_with(
                    result["labor"], "entity_id", "payroll"
                )
                if line["entity_id"] == borrower_id
            ),
            Decimal(0),
        )
        with localcontext(
            Context(
                prec=80,
                rounding=ROUND_HALF_EVEN,
                Emin=-999999,
                Emax=999999,
            )
        ):
            cent = Decimal("0.01")
            expected_deposit = (
                depositor_receipts
                * _decimal(
                    assumption["deposit_fraction_of_realized_receipts"],
                    "deposit fraction",
                )
            ).quantize(cent)
            expected_tax = (
                depositor_receipts
                * _decimal(assumption["trade_tax_rate"], "trade tax rate")
            ).quantize(cent)
            expected_principal = (
                borrower_receipts
                * _decimal(
                    assumption["principal_repayment_fraction_of_realized_receipts"],
                    "principal repayment fraction",
                )
            ).quantize(cent)
            expected_loan = (
                (borrower_trade_outflows + borrower_payroll)
                * _decimal(
                    assumption["working_capital_fraction_of_operating_outflows"],
                    "working-capital fraction",
                )
            ).quantize(cent)

        self.assertEqual(
            _decimal(actions["deposit_gp"], "derived deposit"), expected_deposit
        )
        self.assertEqual(
            _decimal(actions["trade_tax_gp"], "derived trade tax"), expected_tax
        )
        self.assertEqual(
            _decimal(actions["principal_repayment_gp"], "derived principal"),
            expected_principal,
        )
        self.assertEqual(
            _decimal(actions["working_capital_loan_gp"], "derived loan"),
            expected_loan,
        )
        self.assertEqual(
            _decimal(result["banking"]["deposits_received"], "bank deposits"),
            expected_deposit,
        )
        self.assertEqual(
            _decimal(result["banking"]["loan_originations"], "loan originations"),
            expected_loan,
        )
        self.assertEqual(
            _decimal(result["banking"]["principal_repaid"], "principal repaid"),
            expected_principal,
        )
        self.assertEqual(
            _decimal(result["treasury"]["receipts_total"], "treasury receipts"),
            expected_tax,
        )

    def test_explicit_synthetic_demo_is_durable_and_deterministic(self) -> None:
        first_database = self.root / "first campaign workspace" / "regional state.sqlite"
        second_database = self.root / "second campaign workspace" / "regional state.sqlite"
        first_database.parent.mkdir()
        second_database.parent.mkdir()
        self.assertIn(" ", str(self.working_directory))
        self.assertIn(" ", str(first_database))

        first_init = self.initialize(first_database)
        first_run = self.run_month(first_database)
        self.assertEqual(first_run["prior_state_hash"], first_init["state_hash"])
        self.assert_month_has_real_economic_activity(first_run["result"])
        readable_report = Path(str(first_run.get("html_report_path")))
        self.assertTrue(readable_report.is_file())
        self.assertEqual(readable_report.parent, first_database.parent.resolve())
        html = readable_report.read_text(encoding="utf-8")
        for visible_text in (
            "Baen Regional Economy — Month 1",
            "PREVIEW — NOT CANON",
            "Month at a glance",
            "Production and labour",
            "Neverwinter Clay Quarries",
            "Baen Brickworks",
            "Transport and losses",
            "Demand, shortages, and prices",
            "Business, banking, and treasury",
            "Accounting and safety check",
            "PASS — journal balances exactly.",
            "Notion writes: 0",
            "Canonical ledger postings: 0",
        ):
            self.assertIn(visible_text, html)
        self.assertGreaterEqual(html.count("<table>"), 7)
        self.assertNotIn("<script", html.lower())
        self.assertNotIn("src=\"http", html.lower())
        self.assertNotIn("href=\"http", html.lower())

        # A fresh process reopens the durable state and renders the committed result.
        report = self.cli("report", first_database, "--format", "json")
        self.assert_envelope(report, command="report", database=first_database)
        self.assertEqual(report.get("state_hash"), first_run["next_state_hash"])
        self.assertEqual(report.get("latest_result"), first_run["result"])
        self.assertIsInstance(report.get("state"), dict)
        self.assert_operating_trade_reaches_the_books(
            report["state"], first_run["result"]
        )
        self.assertIsNotNone(report.get("period"))
        self.assertEqual(
            Path(str(report.get("html_report_path"))), readable_report
        )

        verification = self.cli("verify", first_database, "--format", "json")
        self.assert_envelope(verification, command="verify", database=first_database)
        self.assertIs(verification.get("valid"), True)
        self.assertEqual(verification.get("run_count"), 1)
        self.assertEqual(verification.get("state_hash"), first_run["next_state_hash"])
        checks = verification.get("checks")
        self.assertIsInstance(checks, dict)
        self.assertTrue(checks)
        self.assertTrue(all(value is True for value in checks.values()))

        # A second independent workspace proves replay determinism rather than
        # merely rereading the first process's persisted response.
        second_init = self.initialize(second_database)
        second_run = self.run_month(second_database)
        self.assertEqual(second_init["state_hash"], first_init["state_hash"])
        self.assertEqual(
            second_init["seed_fingerprint"], first_init["seed_fingerprint"]
        )
        self.assertEqual(second_run["prior_state_hash"], first_run["prior_state_hash"])
        self.assertEqual(second_run["next_state_hash"], first_run["next_state_hash"])
        self.assertEqual(second_run["result"], first_run["result"])


if __name__ == "__main__":
    unittest.main()
