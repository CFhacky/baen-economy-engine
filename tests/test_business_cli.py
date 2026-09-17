from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
FIXTURE = (
    PROJECT / "fixtures" / "registry-snapshots" / "business-registry-2026-08-29.json"
)
LEDGER_ACCOUNTS = PROJECT.parent / "campaign-finance-ledger" / "ledger" / "accounts.bean"


class BusinessCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="business cli path ")
        self.addCleanup(self.temporary.cleanup)
        self.database = Path(self.temporary.name) / "persistent preview.sqlite"
        self.environment = dict(os.environ)
        self.environment["PYTHONPATH"] = str(SRC)

    def command(self, *arguments: object, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "baen_economy.business_cli",
                *(str(argument) for argument in arguments),
            ],
            cwd=PROJECT,
            env=self.environment,
            text=True,
            capture_output=True,
            check=check,
        )

    def initialize(self) -> dict[str, object]:
        result = self.command("init", self.database, FIXTURE)
        return json.loads(result.stdout)

    def test_full_persistent_journey_is_source_bound_and_idempotent(self) -> None:
        fixture_before = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
        ledger_before = (
            hashlib.sha256(LEDGER_ACCOUNTS.read_bytes()).hexdigest()
            if LEDGER_ACCOUNTS.is_file()
            else None
        )
        initialized = self.initialize()
        self.assertEqual(initialized["registry"]["row_count"], 90)
        self.assertEqual(initialized["store"]["business_run_count"], 0)
        self.assertFalse(initialized["store"]["notion_write_capability"])

        arguments = (
            "run-month",
            self.database,
            "--entity",
            "Baen Brickworks",
            "--month",
            "Eleint 1494 CLI preview",
            "--seed",
            "cli-known-private-seed",
        )
        dry = self.command(*arguments, "--format", "json")
        dry_payload = json.loads(dry.stdout)
        self.assertFalse(dry_payload["committed_locally"])
        self.assertIsNone(dry_payload["store_run_hash"])
        self.assertEqual(
            dry_payload["preview"]["financials"]["source_projected_revenue"],
            "3333",
        )
        status = json.loads(self.command("status", self.database).stdout)
        self.assertEqual(status["business_run_count"], 0)

        first = json.loads(
            self.command(*arguments, "--commit", "--format", "json").stdout
        )
        second = json.loads(
            self.command(*arguments, "--commit", "--format", "json").stdout
        )
        self.assertTrue(first["committed_locally"])
        self.assertFalse(first["replayed_existing_commit"])
        self.assertTrue(second["replayed_existing_commit"])
        self.assertEqual(first["store_run_hash"], second["store_run_hash"])
        self.assertNotIn("cli-known-private-seed", self.database.read_bytes().decode("latin1"))

        report = self.command("report", self.database).stdout
        self.assertIn("NOT CANON", report)
        self.assertIn("0 writes attempted", report)
        notion = json.loads(self.command("notion-dry-run", self.database).stdout)
        self.assertFalse(notion["executable"])
        self.assertFalse(notion["write_eligible"])
        self.assertFalse(notion["write_attempted"])
        self.assertEqual(notion["applied_count"], 0)
        self.assertEqual(len(notion["property_diffs"]), 2)
        ledger = json.loads(self.command("ledger-preview", self.database).stdout)
        self.assertFalse(ledger["postable"])
        self.assertEqual(ledger["transaction_count"], 0)
        self.assertEqual(ledger["posting_count"], 0)
        capacity = json.loads(self.command("capacity-profile", self.database).stdout)
        self.assertFalse(capacity["claims"]["actual_production"])
        self.assertFalse(capacity["claims"]["conservation"])
        self.assertIsNone(capacity["unknowns"]["realized_clay_consumption"])
        verified = json.loads(self.command("verify", self.database).stdout)
        self.assertEqual(verified["status"], "ok")
        self.assertEqual(verified["business_run_count"], 1)
        self.assertEqual(verified["business_artifact_count"], 5)

        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), fixture_before)
        if ledger_before is not None:
            self.assertEqual(
                hashlib.sha256(LEDGER_ACCOUNTS.read_bytes()).hexdigest(), ledger_before
            )

    def test_changed_seed_conflicts_and_unknown_entity_fails_without_partial_run(self) -> None:
        self.initialize()
        base = (
            "run-month",
            self.database,
            "--entity",
            "Baen Brickworks",
            "--month",
            "Eleint 1494 conflict preview",
        )
        self.command(*base, "--seed", "first", "--commit")
        conflict = self.command(
            *base, "--seed", "different", "--commit", check=False
        )
        self.assertEqual(conflict.returncode, 2)
        self.assertIn("different immutable content", conflict.stderr)
        missing = self.command(
            "run-month",
            self.database,
            "--entity",
            "Not A Registry Entity",
            "--month",
            "Eleint 1494",
            "--seed",
            "x",
            "--commit",
            check=False,
        )
        self.assertEqual(missing.returncode, 2)
        self.assertIn("exactly one", missing.stderr)
        status = json.loads(self.command("status", self.database).stdout)
        self.assertEqual(status["business_run_count"], 1)

    def test_banking_command_is_positive_but_posted_counts_remain_zero(self) -> None:
        payload = json.loads(
            self.command("banking-sandbox", "--format", "json").stdout
        )
        self.assertEqual(payload["proposal_transaction_count"], 3)
        self.assertEqual(payload["proposal_posting_count"], 7)
        self.assertEqual(payload["posted_transaction_count"], 0)
        self.assertEqual(payload["posted_posting_count"], 0)
        self.assertFalse(payload["postable"])
        self.assertFalse(payload["ledger_post_capability"])


if __name__ == "__main__":
    unittest.main()

