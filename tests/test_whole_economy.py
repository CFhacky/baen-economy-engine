from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from decimal import Decimal, localcontext
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

try:  # Repository layout used by the PR.
    from baen_economy import whole_economy as core
    from baen_economy import whole_economy_cli as cli

    CLI_PACKAGE = "baen_economy"
except ModuleNotFoundError:  # Shared scratch layout used during implementation.
    from economy_impl import whole_economy as core
    from economy_impl import whole_economy_cli as cli

    CLI_PACKAGE = "economy_impl"

# The subprocess acceptance tests launch the CLI by module name. That name has to
# follow whichever package actually imported above, or the tests pass in-process
# and fail out-of-process, which is what happened while both layouts were live.
CLI_MODULE = CLI_PACKAGE + ".whole_economy_cli"


HERE = Path(__file__).resolve().parent
SCENARIO_PATH = next(
    candidate
    for candidate in (
        HERE.parent / "fixtures" / "regional-scenarios" / "baen-north-whole-economy-v1.json",
        HERE / "baen-north-whole-economy-v1.json",
    )
    if candidate.exists()
)
SEED = "whole-economy-three-month-acceptance-seed"
CENT = Decimal("0.01")


def D(value: object) -> Decimal:
    return Decimal(str(value))


def read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"{path} did not contain a JSON object")
    return value


def rows_by(
    rows: list[dict[str, object]], *keys: str
) -> dict[tuple[str, ...], dict[str, object]]:
    result: dict[tuple[str, ...], dict[str, object]] = {}
    for row in rows:
        key = tuple(str(row[name]) for name in keys)
        if key in result:
            raise AssertionError(f"duplicate row key {key}")
        result[key] = row
    return result


def funds(state: dict[str, object], entity_id: str) -> Decimal:
    for raw in state["accounts"]:  # type: ignore[index]
        row = dict(raw)
        if row["entity_id"] == entity_id:
            return D(row.get("cash", "0")) + D(row.get("deposit", "0"))
    return Decimal(0)


def artifact(workspace: Path, month: int, name: str) -> Path:
    return workspace / "months" / f"{month:04d}" / name


def tree_receipt(root: Path) -> list[tuple[str, str]]:
    return [
        (
            path.relative_to(root).as_posix(),
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def played_event(
    event_id: str,
    *,
    subject_id: str = "arik",
    event_type: str = "physical_arrival",
    location_id: str = "forgedeep",
    canonical: bool = True,
    played: bool = True,
    source_text: str = "Played canonical text establishes that Arik physically landed in Forgedeep.",
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "subject_id": subject_id,
        "event_type": event_type,
        "location_id": location_id,
        "canonical": canonical,
        "played": played,
        "source_ref": f"session:{event_id}",
        "source_text": source_text,
    }


def played_context(*events: dict[str, object]) -> dict[str, object]:
    return {"schema": core.PLAYED_CONTEXT_SCHEMA, "events": list(events)}


class WholeEconomyAcceptanceTests(unittest.TestCase):
    """User-visible acceptance through the durable three-month boundary."""

    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(
            prefix="baen whole economy acceptance path with spaces "
        )
        cls.root = Path(cls.temporary.name)
        cls.workspace = cls.root / "first campaign workspace"
        cls.scenario = core.load_scenario(SCENARIO_PATH)
        cls.initial_envelope = cli.initialize_workspace(
            cls.workspace,
            scenario_path=SCENARIO_PATH,
            seed=SEED,
        )
        cls.run_envelopes = [
            cli.run_workspace_month(cls.workspace, commit=True) for _ in range(3)
        ]
        cls.verification = cli.verify_workspace(cls.workspace)
        cls.states = [
            read_json(artifact(cls.workspace, month, "state.json"))
            for month in range(4)
        ]
        cls.results = [
            read_json(artifact(cls.workspace, month, "result.json"))
            for month in range(1, 4)
        ]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def assert_safe_envelope(self, payload: dict[str, object]) -> None:
        self.assertIs(payload.get("ok"), True)
        self.assertIs(payload.get("canonical"), False)
        self.assertEqual(payload.get("notion_writes"), 0)
        self.assertEqual(payload.get("canonical_ledger_postings"), 0)

    def test_return_operation_is_structured_player_gated_and_hash_carried(self) -> None:
        operations = self.scenario["pending_operations"]
        self.assertEqual(len(operations), 1)
        operation = operations[0]
        self.assertEqual(operation["operation_id"], "economic-return:forgedeep-v1")
        self.assertEqual(operation["status"], "pending")
        gate = operation["activation_gate"]
        self.assertEqual(gate["visibility"], "silent_until_matched")
        self.assertEqual(gate["evidence_authority"], "played_canonical_text")
        self.assertEqual(gate["activation_policy"], "once_per_operation_id")
        self.assertIs(gate["activate_once"], True)
        self.assertIs(gate["auto_execute"], False)
        self.assertIs(gate["auto_resolve"], False)
        self.assertEqual(
            gate["required_events"],
            [
                {
                    "subject_id": "arik",
                    "event_type": "physical_arrival",
                    "location_id": "forgedeep",
                }
            ],
        )
        self.assertEqual(
            gate["suppressed_contexts"],
            [
                "Avernus",
                "Black Sluice",
                "Tethford",
                "travel before physical arrival at Forgedeep",
            ],
        )
        authority = operation["decision_authority"]
        self.assertEqual(authority["holder"], "player")
        self.assertIs(authority["may_execute_without_approval"], False)
        self.assertIs(authority["may_advance_campaign_time"], False)
        self.assertIs(authority["may_write_notion"], False)
        requests = operation["required_fact_requests"]
        self.assertGreaterEqual(len(requests), 10)
        self.assertEqual(
            len({row["request_id"] for row in requests}), len(requests)
        )
        self.assertEqual(len({row["fact_key"] for row in requests}), len(requests))
        self.assertTrue(all(row["status"] == "unresolved" for row in requests))

        for state in self.states:
            self.assertEqual(state["pending_operations"], operations)
        for result in self.results:
            self.assertEqual(result["pending_operations"], [])
            self.assertNotIn(operation["title"], result["report_markdown"])
            self.assertNotIn("## Pending campaign operations", result["report_markdown"])
            self.assertFalse(
                any(
                    operation["operation_id"] in json.dumps(entry, sort_keys=True)
                    for entry in result["ledger"]
                )
            )

    def test_return_operation_schema_rejects_prose_only_or_self_authorizing_payloads(self) -> None:
        variants = []
        prose_only = deepcopy(self.scenario)
        prose_only["pending_operations"][0]["required_fact_requests"] = [
            "get better facts"
        ]
        variants.append(("prose-only facts", prose_only))
        self_authorizing = deepcopy(self.scenario)
        self_authorizing["pending_operations"][0]["decision_authority"][
            "may_execute_without_approval"
        ] = True
        variants.append(("self-authorizing", self_authorizing))
        time_advancing = deepcopy(self.scenario)
        time_advancing["pending_operations"][0]["decision_authority"][
            "may_advance_campaign_time"
        ] = True
        variants.append(("time-advancing", time_advancing))
        notion_writing = deepcopy(self.scenario)
        notion_writing["pending_operations"][0]["decision_authority"][
            "may_write_notion"
        ] = True
        variants.append(("notion-writing", notion_writing))
        visible_early = deepcopy(self.scenario)
        visible_early["pending_operations"][0]["activation_gate"][
            "visibility"
        ] = "always"
        variants.append(("visible-before-arrival", visible_early))
        auto_execute = deepcopy(self.scenario)
        auto_execute["pending_operations"][0]["activation_gate"][
            "auto_execute"
        ] = True
        variants.append(("automatic-execution", auto_execute))
        auto_resolve = deepcopy(self.scenario)
        auto_resolve["pending_operations"][0]["activation_gate"][
            "auto_resolve"
        ] = True
        variants.append(("automatic-resolution", auto_resolve))
        repeatable = deepcopy(self.scenario)
        repeatable["pending_operations"][0]["activation_gate"][
            "activate_once"
        ] = False
        variants.append(("repeatable-activation", repeatable))

        for label, scenario in variants:
            with self.subTest(label=label), self.assertRaises(core.EconomyError):
                core.validate_scenario(scenario)

    def test_boot_is_fresh_process_idempotent_offline_and_read_only(self) -> None:
        before = tree_receipt(self.workspace)
        with patch("socket.create_connection", side_effect=AssertionError("network")), patch.object(
            socket.socket, "connect", side_effect=AssertionError("network")
        ), patch.object(cli, "_write_new_text", side_effect=AssertionError("write")), patch.object(
            cli, "run_workspace_month", side_effect=AssertionError("month execution")
        ):
            first = cli.boot_workspace(self.workspace)
            second = cli.boot_workspace(self.workspace)
        self.assertEqual(first, second)
        self.assert_safe_envelope(first)
        self.assertIs(first["campaign_advanced"], False)
        self.assertIs(first["execution_authorized"], False)
        self.assertIs(first["activation_matched"], False)
        self.assertEqual(first["latest_month"], 3)
        self.assertEqual(first["state_hash"], self.states[-1]["state_hash"])
        self.assertEqual(first["operation_count"], 0)
        self.assertEqual(first["pending_operations"], [])
        self.assertEqual(first["required_fact_requests"], [])
        self.assertEqual(first["decision_gates"], [])
        self.assertEqual(first["briefing"], "")
        self.assertNotIn(
            self.scenario["pending_operations"][0]["title"],
            json.dumps(first, sort_keys=True),
        )
        self.assertEqual(before, tree_receipt(self.workspace))

        env = dict(os.environ)
        # Derive the import root from the package that actually imported, rather
        # than assuming it sits beside tests/. Under the repository's src layout it
        # does not, and hardcoding HERE.parent left the CLI unimportable in the
        # subprocess while the in-process tests passed.
        package_parent = str(Path(core.__file__).resolve().parent.parent)
        env["PYTHONPATH"] = (
            package_parent
            if not env.get("PYTHONPATH")
            else package_parent + os.pathsep + env["PYTHONPATH"]
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                CLI_MODULE,
                "boot",
                str(self.workspace),
            ],
            cwd=self.root,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.stdout, "")
        self.assertEqual(completed.stderr, "")
        self.assertEqual(before, tree_receipt(self.workspace))

    def test_gate_rejects_every_prelanding_context_and_free_text_hint(self) -> None:
        operation = self.scenario["pending_operations"][0]
        rejected = (
            played_context(),
            played_context(
                played_event(
                    "avernus",
                    location_id="avernus",
                    source_text="Arik remains in Avernus and intends to reach Forgedeep.",
                )
            ),
            played_context(
                played_event(
                    "black-sluice",
                    location_id="black-sluice",
                    source_text="Arik reaches the Black Sluice on the road to Forgedeep.",
                )
            ),
            played_context(
                played_event(
                    "tethford",
                    location_id="tethford",
                    source_text="Arik is in Tethford before travel to Forgedeep.",
                )
            ),
            played_context(
                played_event(
                    "travel",
                    event_type="travel",
                    source_text="Arik is travelling toward Forgedeep.",
                )
            ),
            played_context(
                played_event(
                    "gorge-team",
                    subject_id="gorge-team",
                    source_text="The gorge team lands; Arik remains elsewhere.",
                )
            ),
            played_context(
                played_event(
                    "portal-crossing",
                    event_type="portal_crossing",
                    source_text="Arik crosses a portal on the route to Forgedeep.",
                )
            ),
            played_context(
                played_event(
                    "approach",
                    event_type="approach",
                    source_text="Arik approaches Forgedeep but has not landed.",
                )
            ),
            played_context(
                played_event(
                    "airspace",
                    event_type="airspace_entry",
                    location_id="forgedeep-airspace",
                    source_text="Arik enters Forgedeep airspace but has not landed.",
                )
            ),
            played_context(
                played_event(
                    "expected-arrival",
                    event_type="expected_arrival",
                    source_text="Arik is expected to arrive in Forgedeep.",
                )
            ),
            played_context(
                played_event(
                    "remote-contact",
                    event_type="remote_contact",
                    source_text="Arik contacts Forgedeep remotely from Avernus.",
                )
            ),
            played_context(played_event("unplayed", played=False)),
            played_context(played_event("noncanonical", canonical=False)),
            played_context(played_event("wrong-subject", subject_id="vara")),
        )
        for context in rejected:
            with self.subTest(context=context):
                boot = cli.boot_workspace(self.workspace, played_context=context)
                self.assertIs(boot["activation_matched"], False)
                self.assertEqual(boot["operation_count"], 0)
                self.assertEqual(boot["pending_operations"], [])
                self.assertEqual(boot["briefing"], "")
                self.assertNotIn(operation["title"], json.dumps(boot, sort_keys=True))

    def test_physical_forgedeep_landing_activates_once_without_resolution(self) -> None:
        operation = self.scenario["pending_operations"][0]
        context = played_context(
            played_event("landing-002"),
            played_event("landing-001"),
        )
        before = tree_receipt(self.workspace)
        with patch("socket.create_connection", side_effect=AssertionError("network")), patch.object(
            socket.socket, "connect", side_effect=AssertionError("network")
        ), patch.object(cli, "_write_new_text", side_effect=AssertionError("write")), patch.object(
            cli, "_write_new_json", side_effect=AssertionError("write")
        ), patch.object(
            cli, "run_workspace_month", side_effect=AssertionError("month execution")
        ):
            boot = cli.boot_workspace(self.workspace, played_context=context)
            repeated = cli.boot_workspace(self.workspace, played_context=context)
        self.assertEqual(boot, repeated)
        self.assert_safe_envelope(boot)
        self.assertIs(boot["activation_matched"], True)
        self.assertEqual(boot["operation_count"], 1)
        self.assertEqual(len(boot["pending_operations"]), 1)
        active = boot["pending_operations"][0]
        self.assertEqual(active["operation_id"], operation["operation_id"])
        self.assertEqual(
            active["activation"]["activation_id"],
            "activation:economic-return:forgedeep-v1",
        )
        self.assertEqual(active["activation"]["matched_event_ids"], ["landing-001"])
        self.assertIs(active["activation"]["automatic_execution"], False)
        self.assertIs(active["activation"]["automatic_resolution"], False)
        self.assertEqual(
            boot["required_fact_requests"], operation["required_fact_requests"]
        )
        self.assertEqual(boot["decision_gates"], operation["decision_gates"])
        self.assertIn(operation["title"], boot["briefing"])
        for request in operation["required_fact_requests"]:
            self.assertIn(request["question"], boot["briefing"])
            self.assertEqual(request["status"], "unresolved")
        self.assertIs(boot["execution_authorized"], False)
        self.assertIs(boot["campaign_advanced"], False)
        self.assertEqual(before, tree_receipt(self.workspace))
        for state in self.states:
            self.assertEqual(state["pending_operations"], [operation])
        for result in self.results:
            self.assertFalse(
                any(
                    operation["operation_id"] in json.dumps(entry, sort_keys=True)
                    for entry in result["ledger"]
                )
            )

    def test_cli_played_context_file_surfaces_only_after_exact_landing(self) -> None:
        context_path = self.root / "played landing context.json"
        context_path.write_text(
            json.dumps(played_context(played_event("landing-cli"))),
            encoding="utf-8",
        )
        env = dict(os.environ)
        # Derive the import root from the package that actually imported, rather
        # than assuming it sits beside tests/. Under the repository's src layout it
        # does not, and hardcoding HERE.parent left the CLI unimportable in the
        # subprocess while the in-process tests passed.
        package_parent = str(Path(core.__file__).resolve().parent.parent)
        env["PYTHONPATH"] = (
            package_parent
            if not env.get("PYTHONPATH")
            else package_parent + os.pathsep + env["PYTHONPATH"]
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                CLI_MODULE,
                "boot",
                str(self.workspace),
                "--played-context",
                str(context_path),
            ],
            cwd=self.root,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["operation_count"], 1)
        self.assertEqual(
            payload["pending_operations"][0]["activation"]["activation_id"],
            "activation:economic-return:forgedeep-v1",
        )

    def test_malformed_or_duplicate_played_context_fails_closed(self) -> None:
        malformed = played_context(played_event("bad"))
        malformed["schema"] = "wrong"
        duplicate = played_context(
            played_event("duplicate"),
            played_event("duplicate"),
        )
        missing_marker = played_context(played_event("missing-marker"))
        del missing_marker["events"][0]["played"]
        for context in (malformed, duplicate, missing_marker):
            with self.subTest(context=context), self.assertRaises(core.EconomyError):
                cli.boot_workspace(self.workspace, played_context=context)

    def test_three_committed_months_chain_hashes_replay_and_reports(self) -> None:
        self.assert_safe_envelope(self.initial_envelope)
        self.assertEqual(self.initial_envelope["month"], 0)
        self.assertEqual(len(self.run_envelopes), 3)
        prior_hash = str(self.initial_envelope["state_hash"])
        for month, (envelope, result, state) in enumerate(
            zip(self.run_envelopes, self.results, self.states[1:]), start=1
        ):
            with self.subTest(month=month):
                self.assert_safe_envelope(envelope)
                self.assertEqual(envelope["month"], month)
                self.assertIs(envelope["committed"], True)
                self.assertEqual(result["input_state_hash"], prior_hash)
                self.assertEqual(result["next_state_hash"], state["state_hash"])
                self.assertEqual(result["result_hash"], envelope["result_hash"])
                self.assertEqual(core.state_hash(state), state["state_hash"])
                self.assertEqual(core.state_hash(result), result["result_hash"])
                prior_hash = str(state["state_hash"])

                html_path = artifact(self.workspace, month, "report.html")
                html = html_path.read_text(encoding="utf-8")
                for visible in (
                    "Whole-economy vertical slice",
                    f"Regional Economy — Month {month}",
                    "PREVIEW — NOT CANON",
                    "What changed, where, and why",
                    "Available decisions",
                    "Physical conservation: <strong>PASS</strong>",
                    "Balanced economic ledger: <strong>PASS</strong>",
                    "Notion writes: 0",
                    "Canonical ledger postings: 0",
                ):
                    self.assertIn(visible, html)
                dormant_operation = self.scenario["pending_operations"][0]
                self.assertNotIn("Pending campaign operations", html)
                self.assertNotIn(dormant_operation["title"], html)
                self.assertNotIn(dormant_operation["operation_id"], html)
                for request in dormant_operation["required_fact_requests"]:
                    self.assertNotIn(request["question"], html)
                self.assertNotIn("<script", html.lower())
                self.assertTrue(result["events"])
                self.assertTrue(result["available_decisions"])

        self.assert_safe_envelope(self.verification)
        self.assertIs(self.verification["valid"], True)
        self.assertEqual(self.verification["run_count"], 3)
        self.assertTrue(all(self.verification["checks"].values()))
        report = cli.report_workspace(self.workspace, period=3)
        self.assert_safe_envelope(report)
        self.assertEqual(
            report["covers"],
            {
                "what_changed": True,
                "where": True,
                "why": True,
                "available_decisions": True,
            },
        )

    def test_deterministic_replay_is_byte_identical_in_an_independent_workspace(self) -> None:
        second = self.root / "second independent campaign workspace"
        second_init = cli.initialize_workspace(
            second, scenario_path=SCENARIO_PATH, seed=SEED
        )
        second_runs = [cli.run_workspace_month(second, commit=True) for _ in range(3)]
        second_verify = cli.verify_workspace(second)
        self.assertEqual(second_init["state_hash"], self.initial_envelope["state_hash"])
        self.assertEqual(
            second_init["seed_fingerprint"], self.initial_envelope["seed_fingerprint"]
        )
        self.assertIs(second_verify["valid"], True)
        for month, (first_run, second_run) in enumerate(
            zip(self.run_envelopes, second_runs), start=1
        ):
            with self.subTest(month=month):
                self.assertEqual(first_run["result_hash"], second_run["result_hash"])
                self.assertEqual(first_run["state_hash"], second_run["state_hash"])
                for name in ("state.json", "result.json", "report.html"):
                    self.assertEqual(
                        artifact(self.workspace, month, name).read_bytes(),
                        artifact(second, month, name).read_bytes(),
                    )

    def test_physical_conservation_and_money_balance_hold_each_month(self) -> None:
        commodity_ids = {str(row["id"]) for row in self.scenario["commodities"]}
        for month, (result, state) in enumerate(
            zip(self.results, self.states[1:]), start=1
        ):
            with self.subTest(month=month):
                checks = result["checks"]
                self.assertIs(checks["physical_conservation"], True)
                self.assertIs(checks["nonnegative_balances"], True)
                self.assertIs(checks["ledger_balanced"], True)
                receipts = {
                    str(row["commodity_id"]): row
                    for row in checks["physical_receipts"]
                }
                self.assertEqual(set(receipts), commodity_ids)
                for commodity_id, receipt in receipts.items():
                    with self.subTest(month=month, commodity=commodity_id):
                        residual = D(receipt["residual"])
                        tolerance = D(receipt["tolerance"])
                        self.assertIs(receipt["within_tolerance"], True)
                        self.assertLessEqual(abs(residual), tolerance)
                        with localcontext() as context:
                            context.prec = 60
                            self.assertEqual(
                                D(receipt["opening_plus_produced"])
                                - D(receipt["closing_plus_uses_and_losses"]),
                                residual,
                            )
                self.assertTrue(
                    all(D(row["quantity"]) >= 0 for row in state["inventories"])
                )
                self.assertTrue(
                    all(
                        D(row.get("cash", "0")) >= 0
                        and D(row.get("deposit", "0")) >= 0
                        for row in state["accounts"]
                    )
                )
                total_debits = Decimal(0)
                total_credits = Decimal(0)
                for transaction in result["ledger"]:
                    debits = sum(
                        (D(posting["debit"]) for posting in transaction["postings"]),
                        Decimal(0),
                    )
                    credits = sum(
                        (D(posting["credit"]) for posting in transaction["postings"]),
                        Decimal(0),
                    )
                    self.assertEqual(debits, credits)
                    self.assertEqual(debits, D(transaction["debits"]))
                    self.assertEqual(credits, D(transaction["credits"]))
                    total_debits += debits
                    total_credits += credits
                self.assertGreater(total_debits, 0)
                self.assertEqual(total_debits, total_credits)
                self.assertEqual(total_debits, D(checks["total_debits"]))
                self.assertEqual(total_credits, D(checks["total_credits"]))

    def test_population_class_demand_substitution_and_migration_are_real_flows(self) -> None:
        class_rules = {
            (str(settlement["id"]), str(social_class["id"])): social_class
            for settlement in self.scenario["settlements"]
            for social_class in settlement["classes"]
        }
        positive_substitution = False
        regional_population = sum(
            (D(row["population"]) for row in self.states[0]["populations"]),
            Decimal(0),
        )
        for month, (before, result, after) in enumerate(
            zip(self.states, self.results, self.states[1:]), start=1
        ):
            class_demands = [row for row in result["market"] if row["class_id"]]
            self.assertEqual(len(class_demands), len(class_rules) * 2)
            for demand in class_demands:
                key = (str(demand["settlement_id"]), str(demand["class_id"]))
                rule = class_rules[key]
                commodity = str(demand["commodity_id"])
                self.assertEqual(D(demand["per_person_quantity"]), D(rule["basket"][commodity]))
                self.assertEqual(
                    D(demand["requested_primary_equivalent"]),
                    D(demand["population"]) * D(demand["per_person_quantity"]),
                )
                self.assertEqual(
                    D(demand["requested_primary_equivalent"]),
                    D(demand["consumed_primary_equivalent"])
                    + D(demand["shortage_primary_equivalent"]),
                )
                for substitution in demand["substitutions"]:
                    quantity = D(substitution["quantity_consumed"])
                    ratio = D(substitution["ratio"])
                    with localcontext() as context:
                        context.prec = 50
                        self.assertEqual(
                            D(substitution["primary_equivalent"]), quantity / ratio
                        )
                    positive_substitution |= quantity > 0

            before_population = rows_by(before["populations"], "settlement_id", "class_id")
            after_population = rows_by(after["populations"], "settlement_id", "class_id")
            expected = {key: D(row["population"]) for key, row in before_population.items()}
            for movement in result["migration"]:
                migrants = D(movement["migrants"])
                self.assertGreater(migrants, 0)
                source = (str(movement["origin"]), str(movement["class_id"]))
                destination = (
                    str(movement["destination"]),
                    str(movement["class_id"]),
                )
                expected[source] -= migrants
                expected[destination] += migrants
            self.assertEqual(
                {key: D(row["population"]) for key, row in after_population.items()},
                expected,
            )
            self.assertEqual(
                sum((D(row["population"]) for row in after["populations"]), Decimal(0)),
                regional_population,
            )
            for occupation in {str(row["occupation"]) for row in before["labor"]}:
                before_workers = sum(
                    (
                        D(row["workers"])
                        for row in before["labor"]
                        if row["occupation"] == occupation
                    ),
                    Decimal(0),
                )
                after_workers = sum(
                    (
                        D(row["workers"])
                        for row in after["labor"]
                        if row["occupation"] == occupation
                    ),
                    Decimal(0),
                )
                self.assertEqual(before_workers, after_workers)
            for pool in after["labor"]:
                workers = D(pool["workers"])
                employed_workers = D(pool.get("employed_workers", "0"))
                employed_days = D(pool.get("employed_worker_days", "0"))
                self.assertGreaterEqual(workers, 0)
                self.assertGreaterEqual(employed_workers, 0)
                self.assertLessEqual(employed_workers, workers)
                self.assertGreaterEqual(employed_days, 0)
                self.assertLessEqual(employed_days, workers * core.DAYS_PER_MONTH)
        self.assertTrue(positive_substitution, "no class actually consumed a substitute")
        self.assertTrue(any(result["migration"] for result in self.results))

    def test_land_rent_dues_tithes_taxes_and_treasuries_reconcile(self) -> None:
        tenure_rules = {str(row["id"]): row for row in self.scenario["tenures"]}
        expected_kinds = {"rent", "feudal_due", "tithe", "tax"}
        treasury_ids = {str(row["treasury_id"]) for row in self.scenario["tenures"]}
        for month, (before, result, after) in enumerate(
            zip(self.states, self.results, self.states[1:]), start=1
        ):
            obligations = result["land_and_fiscal_obligations"]
            self.assertEqual(len(obligations), len(tenure_rules) * 4)
            self.assertEqual({str(row["kind"]) for row in obligations}, expected_kinds)
            active_tax_delta = defaultdict(Decimal)
            for shock in result["shocks"]:
                if shock["active"] and "tax_rate_delta" in shock["effects"]:
                    targets = (
                        treasury_ids
                        if shock.get("settlement_id") is None
                        else {
                            str(rule["treasury_id"])
                            for rule in tenure_rules.values()
                            if rule["settlement_id"] == shock["settlement_id"]
                        }
                    )
                    for treasury_id in targets:
                        active_tax_delta[treasury_id] += D(
                            shock["effects"]["tax_rate_delta"]
                        )
            for receipt in obligations:
                rule = tenure_rules[str(receipt["tenure_id"])]
                kind = str(receipt["kind"])
                gross = D(receipt["assessment_base"])
                if kind == "rent":
                    expected_due = D(rule["acres"]) * D(rule["rent_per_acre"])
                    expected_recipient = rule["landlord_id"]
                elif kind == "feudal_due":
                    expected_due = gross * D(rule["feudal_due_rate"])
                    expected_recipient = rule["landlord_id"]
                elif kind == "tithe":
                    expected_due = gross * D(rule["tithe_rate"])
                    expected_recipient = rule["church_id"]
                else:
                    rate = min(
                        Decimal(1),
                        max(
                            Decimal(0),
                            D(rule["tax_rate"])
                            + active_tax_delta[str(rule["treasury_id"])],
                        ),
                    )
                    expected_due = gross * rate
                    expected_recipient = rule["treasury_id"]
                self.assertEqual(D(receipt["due"]), expected_due.quantize(CENT))
                self.assertEqual(receipt["recipient_id"], expected_recipient)
                self.assertEqual(
                    D(receipt["due"]), D(receipt["paid"]) + D(receipt["arrears"])
                )

            for treasury_id in treasury_ids:
                ledger_delta = Decimal(0)
                for transaction in result["ledger"]:
                    for posting in transaction["postings"]:
                        if posting["account"] == f"Assets:{treasury_id}:Funds":
                            ledger_delta += D(posting["debit"]) - D(posting["credit"])
                self.assertEqual(
                    funds(after, treasury_id) - funds(before, treasury_id),
                    ledger_delta,
                )

    def test_nonfarm_chain_services_labor_payroll_and_wages_persist(self) -> None:
        required_kinds = {
            "agriculture",
            "aquaculture",
            "extraction",
            "manufacturing",
            "construction",
            "service",
        }
        chain = (
            "recipe:clay-extraction",
            "recipe:brickworks",
            "recipe:baen-construction",
        )
        positive_chain_steps = set()
        for month, (before, result, after) in enumerate(
            zip(self.states, self.results, self.states[1:]), start=1
        ):
            production = {str(row["recipe_id"]): row for row in result["production"]}
            self.assertTrue(required_kinds.issubset({str(row["kind"]) for row in production.values()}))
            for recipe_id in chain:
                if D(production[recipe_id]["batches"]) > 0:
                    positive_chain_steps.add(recipe_id)
                    self.assertTrue(production[recipe_id]["outputs"])
            if D(production["recipe:clay-extraction"]["batches"]) > 0:
                self.assertGreater(
                    D(production["recipe:clay-extraction"]["outputs"]["clay"]), 0
                )
            if D(production["recipe:brickworks"]["batches"]) > 0:
                self.assertGreater(
                    D(production["recipe:brickworks"]["inputs"]["clay"]), 0
                )
                self.assertGreater(
                    D(production["recipe:brickworks"]["outputs"]["bricks"]), 0
                )
            if D(production["recipe:baen-construction"]["batches"]) > 0:
                self.assertGreater(
                    D(production["recipe:baen-construction"]["inputs"]["bricks"]), 0
                )
            self.assertTrue(
                any(
                    row["kind"] == "service"
                    and D(row["batches"]) > 0
                    and row["outputs"]
                    for row in production.values()
                )
            )

            payroll = sum((D(row["payroll"]) for row in production.values()), Decimal(0))
            booked_payroll = sum(
                (
                    D(posting["debit"])
                    for row in result["ledger"]
                    if row["kind"] == "payroll"
                    for posting in row["postings"]
                    if str(posting["account"]).endswith(":Funds")
                ),
                Decimal(0),
            )
            self.assertGreater(payroll, 0)
            self.assertEqual(payroll, booked_payroll)
            before_labor = rows_by(before["labor"], "settlement_id", "occupation")
            after_labor = rows_by(after["labor"], "settlement_id", "occupation")
            for receipt in result["labor"]:
                key = (str(receipt["settlement_id"]), str(receipt["occupation"]))
                workers = D(receipt["workers"])
                worker_days = D(receipt["worker_days"])
                self.assertLessEqual(worker_days, workers * core.DAYS_PER_MONTH)
                with localcontext() as context:
                    context.prec = 50
                    self.assertEqual(
                        D(receipt["employed_workers"]),
                        worker_days / core.DAYS_PER_MONTH,
                    )
                self.assertEqual(D(receipt["wage_before"]), D(before_labor[key]["wage"]))
                with localcontext() as context:
                    context.prec = 50
                    utilization = (
                        Decimal(0)
                        if workers == 0
                        else worker_days / (workers * core.DAYS_PER_MONTH)
                    )
                    expected_wage = max(
                        Decimal("0.01"),
                        D(receipt["wage_before"])
                        * (
                            Decimal(1)
                            + (utilization - Decimal("0.80")) * Decimal("0.05")
                        ),
                    )
                self.assertEqual(D(receipt["wage_after"]), expected_wage)
                self.assertEqual(D(after_labor[key]["wage"]), expected_wage)
        self.assertEqual(positive_chain_steps, set(chain))

    def test_prices_trade_tolls_travel_arrivals_and_spoilage_roll_forward(self) -> None:
        commodity_rules = {str(row["id"]): row for row in self.scenario["commodities"]}
        route_rules = {str(row["id"]): row for row in self.scenario["routes"]}
        saw_price_change = False
        saw_route_loss = False
        saw_arrival = False
        saw_storage_loss = False
        for month, (before, result, after) in enumerate(
            zip(self.states, self.results, self.states[1:]), start=1
        ):
            before_prices = rows_by(before["prices"], "settlement_id", "commodity_id")
            after_prices = rows_by(after["prices"], "settlement_id", "commodity_id")
            self.assertEqual(set(before_prices), set(after_prices))
            for key, row in after_prices.items():
                price = D(row["price"])
                rule = commodity_rules[key[1]]
                self.assertGreaterEqual(price, D(rule["min_price"]))
                self.assertLessEqual(price, D(rule["max_price"]))
                saw_price_change |= price != D(before_prices[key]["price"])

            capacity_multiplier = defaultdict(lambda: Decimal(1))
            for shock in result["shocks"]:
                if shock["active"] and "route_capacity_multiplier" in shock["effects"]:
                    capacity_multiplier[str(shock.get("settlement_id"))] *= D(
                        shock["effects"]["route_capacity_multiplier"]
                    )
            for usage in result["route_usage"]:
                rule = route_rules[str(usage["route_id"])]
                capacity = D(rule["capacity"]) * capacity_multiplier[str(rule["origin"])]
                self.assertGreaterEqual(D(usage["dispatched_quantity"]), 0)
                self.assertLessEqual(D(usage["dispatched_quantity"]), capacity)

            route_dues = defaultdict(Decimal)
            for trade in result["trade"]:
                with localcontext() as context:
                    context.prec = 50
                    self.assertEqual(
                        D(trade["dispatched_quantity"]),
                        D(trade["delivered_quantity"]) + D(trade["route_loss"]),
                    )
                saw_route_loss |= D(trade["route_loss"]) > 0
                route_id = trade.get("route_id")
                if route_id:
                    rule = route_rules[str(route_id)]
                    self.assertEqual(
                        int(trade["arrival_month"]),
                        int(trade["departure_month"]) + int(rule["travel_months"]),
                    )
                    self.assertEqual(
                        D(trade["carrier_fee"]),
                        (D(trade["dispatched_quantity"]) * D(rule["carrier_cost_per_unit"])).quantize(CENT),
                    )
                    self.assertEqual(
                        D(trade["toll"]),
                        (D(trade["dispatched_quantity"]) * D(rule["toll_per_unit"])).quantize(CENT),
                    )
                    origin_price = D(
                        before_prices[(str(trade["origin"]), str(trade["commodity_id"]))][
                            "price"
                        ]
                    )
                    self.assertEqual(
                        D(trade["goods_value"]),
                        (D(trade["delivered_quantity"]) * origin_price).quantize(CENT),
                    )
                    total_due = (
                        D(trade["goods_value"])
                        + D(trade["carrier_fee"])
                        + D(trade["toll"])
                    )
                    route_dues[str(trade["route_id"])] += total_due
            for route_id, total_due in route_dues.items():
                paid = sum(
                    (
                        D(posting["credit"])
                        for transaction in result["ledger"]
                        if transaction["summary"]
                        == f"Prepayment of {route_id} shipment"
                        for posting in transaction["postings"]
                        if str(posting["account"]).endswith(":Funds")
                    ),
                    Decimal(0),
                )
                self.assertEqual(paid, total_due)

            due = [
                row
                for row in before["in_transit"]
                if int(row["arrival_month"]) <= month
            ]
            arrival_events = {
                str(event["summary"]).split()[0]
                for event in result["events"]
                if event["kind"] == "shipment-arrival"
            }
            held_events = {
                str(event["summary"]).split()[0]
                for event in result["events"]
                if event["kind"] == "shipment-held"
            }
            remaining_ids = {str(row["shipment_id"]) for row in after["in_transit"]}
            for lot in due:
                shipment_id = str(lot["shipment_id"])
                self.assertIn(shipment_id, arrival_events | held_events)
                if shipment_id in arrival_events:
                    self.assertNotIn(shipment_id, remaining_ids)
                    settlement_kinds = {
                        str(txn["kind"])
                        for txn in result["ledger"]
                        if shipment_id in str(txn["summary"])
                    }
                    if lot.get("settlement_status") == "prepaid":
                        self.assertFalse(settlement_kinds)
                    else:
                        self.assertIn("trade-goods", settlement_kinds)
                        self.assertIn("carrier-fee", settlement_kinds)
                        self.assertIn("route-toll", settlement_kinds)
                    saw_arrival = True
            saw_storage_loss |= any(
                event["kind"] == "spoilage" for event in result["events"]
            )
        self.assertTrue(saw_price_change)
        self.assertTrue(saw_route_loss)
        self.assertTrue(saw_arrival)
        self.assertTrue(saw_storage_loss)

    def test_bank_deposits_reserves_collateral_interest_repayment_and_default(self) -> None:
        request_by_month = defaultdict(list)
        for request in self.scenario["credit_requests"]:
            request_by_month[int(request["month"])].append(request)
        for month, result in enumerate(self.results, start=1):
            originated = {
                str(row["loan_id"]): row
                for row in result["banking"]
                if row["action"] == "originated"
            }
            self.assertEqual(
                set(originated),
                {str(row["loan_id"]) for row in request_by_month[month]},
            )
            for loan_id, receipt in originated.items():
                transaction = next(
                    row
                    for row in result["ledger"]
                    if row["kind"] == "loan-origination" and loan_id in row["summary"]
                )
                amount = D(receipt["amount"])
                self.assertEqual(D(transaction["debits"]), amount * 2)
                self.assertEqual(D(transaction["credits"]), amount * 2)
                accounts = {str(row["account"]) for row in transaction["postings"]}
                self.assertTrue(any(":Loans:" in account for account in accounts))
                self.assertTrue(any(":Deposits" in account for account in accounts))
                self.assertGreaterEqual(D(receipt["collateral_value"]), amount)

            for service in (
                row for row in result["banking"] if row["action"] == "serviced"
            ):
                self.assertGreater(D(service["interest_accrued"]), 0)
                self.assertGreaterEqual(D(service["interest_paid"]), 0)
                self.assertLessEqual(
                    D(service["interest_paid"]), D(service["interest_due"])
                )
                self.assertGreaterEqual(D(service["principal_paid"]), 0)
                self.assertLessEqual(
                    D(service["principal_paid"]), D(service["principal_due"])
                )
                if service["status"] != "defaulted":
                    self.assertEqual(
                        D(service["interest_due"]),
                        D(service["interest_paid"])
                        + D(service["interest_carried_forward"]),
                    )

        final_state = self.states[-1]
        self.assertTrue(final_state["loans"])
        terminal_statuses = {str(loan["status"]) for loan in final_state["loans"]}
        self.assertEqual(terminal_statuses, {"defaulted", "repaid"})
        for loan in final_state["loans"]:
            self.assertEqual(D(loan["principal"]), 0)
            self.assertEqual(D(loan.get("accrued_interest", "0")), 0)
            self.assertIs(loan.get("collateral_released"), True)
            self.assertLessEqual(
                D(loan["collateral_released_quantity"]),
                D(loan["collateral_quantity"]),
            )
            owner_rows = [
                row
                for row in final_state["inventories"]
                if row["owner_id"] == loan["collateral_owner_id"]
                and row["settlement_id"] == loan["collateral_settlement_id"]
                and row["commodity_id"] == loan["collateral_commodity_id"]
            ]
            self.assertTrue(owner_rows)
            self.assertEqual(
                sum((D(row.get("pledged_quantity", "0")) for row in owner_rows), Decimal(0)),
                0,
            )
            bank_collateral = [
                row
                for row in final_state["inventories"]
                if row["owner_id"] == loan["bank_id"]
                and row["settlement_id"] == loan["collateral_settlement_id"]
                and row["commodity_id"] == loan["collateral_commodity_id"]
            ]
            seized = sum(
                (D(row["quantity"]) for row in bank_collateral), Decimal(0)
            )
            if loan["status"] == "defaulted":
                self.assertGreater(seized, 0)
            else:
                self.assertEqual(loan["status"], "repaid")

        account_rows = final_state["accounts"]
        for check in self.results[-1]["checks"]["bank_checks"]:
            bank_id = str(check["bank_id"])
            deposits = sum(
                (
                    D(row.get("deposit", "0"))
                    for row in account_rows
                    if row.get("bank_id") == bank_id
                ),
                Decimal(0),
            )
            self.assertEqual(deposits, D(check["deposit_liability"]))
            self.assertEqual(deposits, D(check["depositor_balances"]))
            self.assertGreaterEqual(D(check["reserves"]), D(check["required_reserves"]))
            self.assertIs(check["reserve_compliant"], True)

    def test_unpaid_interest_is_carried_and_reconciles_until_payment_or_default(self) -> None:
        scenario = deepcopy(self.scenario)
        loan_id = "loan:shimmerdeep-opening-capital"
        borrower = "entity:shimmerdeep-cradle"
        bank_id = "entity:ncf-waterdeep"
        for account in scenario["opening_state"]["accounts"]:
            if account["entity_id"] == borrower:
                account["cash"] = "0"
                account["deposit"] = "0"
        for bank in scenario["opening_state"]["banks"]:
            if bank["bank_id"] == bank_id:
                bank["other_assets"] = str(D(bank["other_assets"]) - Decimal("5000"))
        for loan in scenario["opening_state"]["loans"]:
            if loan["loan_id"] == loan_id:
                loan["default_after_missed"] = "99"
                loan["collateral_quantity"] = "150"

        opening = core.initial_state(scenario)
        outcome = core.run_month(scenario, opening, "interest-carry-seed")
        result = outcome["result"]
        next_state = outcome["next_state"]
        receipt = next(
            row for row in result["banking"] if row.get("loan_id") == loan_id
        )
        loan = next(row for row in next_state["loans"] if row["loan_id"] == loan_id)
        bank_check = next(
            row
            for row in result["checks"]["bank_checks"]
            if row["bank_id"] == bank_id
        )

        self.assertEqual(receipt["status"], "delinquent")
        self.assertGreater(D(receipt["interest_accrued"]), 0)
        self.assertEqual(D(receipt["interest_paid"]), 0)
        self.assertEqual(
            D(receipt["interest_carried_forward"]), D(receipt["interest_due"])
        )
        self.assertEqual(
            D(loan["accrued_interest"]), D(receipt["interest_carried_forward"])
        )
        self.assertEqual(loan["missed_payments"], 1)
        self.assertEqual(
            D(bank_check["interest_receivable"]), D(loan["accrued_interest"])
        )
        self.assertIs(bank_check["interest_receivable_reconciles"], True)
        self.assertTrue(
            any(
                transaction["kind"] == "interest-accrual"
                and loan_id in transaction["summary"]
                for transaction in result["ledger"]
            )
        )
        self.assertFalse(
            any(
                transaction["kind"] == "interest-payment"
                and loan_id in transaction["summary"]
                for transaction in result["ledger"]
            )
        )

    def test_arrival_is_held_when_deposits_exist_but_interbank_reserves_do_not(self) -> None:
        scenario = deepcopy(self.scenario)
        buyer_id = "households:waterdeep:commoners"
        bank_id = "entity:ncf-waterdeep"
        shipment_id = "shipment:opening:grain-to-waterdeep"
        for account in scenario["opening_state"]["accounts"]:
            if account["entity_id"] == buyer_id:
                account["cash"] = "0"
        for bank in scenario["opening_state"]["banks"]:
            if bank["bank_id"] == bank_id:
                original_reserves = D(bank["reserves"])
                bank["reserves"] = "100"
                bank["other_assets"] = str(
                    D(bank["other_assets"]) + original_reserves - Decimal("100")
                )

        opening = core.initial_state(scenario)
        buyer = next(row for row in opening["accounts"] if row["entity_id"] == buyer_id)
        bank = next(row for row in opening["banks"] if row["bank_id"] == bank_id)
        lot = next(
            row for row in opening["in_transit"] if row["shipment_id"] == shipment_id
        )
        total_due = D(lot["goods_value"]) + D(lot["carrier_fee"]) + D(lot["toll"])
        external_due = D(lot["goods_value"]) + D(lot["carrier_fee"])
        self.assertGreaterEqual(D(buyer["cash"]) + D(buyer["deposit"]), total_due)
        self.assertLess(D(bank["reserves"]), external_due)

        outcome = core.run_month(scenario, opening, "reserve-arrival-seed")
        result = outcome["result"]
        held = next(
            row
            for row in outcome["next_state"]["in_transit"]
            if row["shipment_id"] == shipment_id
        )
        self.assertEqual(held["status"], "held_at_destination_unpaid")
        self.assertTrue(
            any(
                event["kind"] == "shipment-held"
                and event["summary"].startswith(shipment_id)
                for event in result["events"]
            )
        )
        self.assertFalse(
            any(shipment_id in transaction["summary"] for transaction in result["ledger"])
        )
        self.assertTrue(
            any(
                decision["decision_id"] == f"settle:{shipment_id}"
                for decision in result["available_decisions"]
            )
        )
        bank_check = next(
            row
            for row in result["checks"]["bank_checks"]
            if row["bank_id"] == bank_id
        )
        self.assertIs(bank_check["reserve_compliant"], False)
        self.assertIs(result["checks"]["ledger_balanced"], True)

    def test_all_seven_shock_types_are_scheduled_applied_and_causal(self) -> None:
        expected = {
            "weather",
            "harvest",
            "war",
            "monster",
            "political",
            "infrastructure",
            "policy",
        }
        self.assertEqual({str(row["type"]) for row in self.scenario["shocks"]}, expected)
        scheduled = {
            month: {
                str(row["type"])
                for row in self.scenario["shocks"]
                if month in {int(value) for value in row.get("months", [month])}
            }
            for month in range(1, 4)
        }
        active_across_window = set()
        for month, result in enumerate(self.results, start=1):
            receipts = result["shocks"]
            self.assertEqual({str(row["type"]) for row in receipts}, expected)
            self.assertEqual(len({str(row["shock_id"]) for row in receipts}), 7)
            self.assertTrue(all(str(row["source_ref"]).strip() for row in receipts))
            active = {str(row["type"]) for row in receipts if row["active"]}
            eligible = {str(row["type"]) for row in receipts if row["eligible"]}
            self.assertEqual(eligible, scheduled[month])
            self.assertEqual(active, scheduled[month])
            active_across_window.update(active)
            for receipt in receipts:
                self.assertEqual(receipt["active"], receipt["eligible"])
                self.assertLess(D(receipt["draw"]), D(receipt["probability"]))
            event_kinds = {str(row["kind"]) for row in result["events"]}
            for shock_type in scheduled[month]:
                self.assertIn(f"shock:{shock_type}", event_kinds)
            for shock_type in expected - scheduled[month]:
                self.assertNotIn(f"shock:{shock_type}", event_kinds)

            production = {str(row["recipe_id"]): row for row in result["production"]}
            expected_nw_grain = Decimal("0.85") if "harvest" in active else Decimal(1)
            self.assertEqual(
                D(production["recipe:nw-grain"]["shock_multiplier"]),
                expected_nw_grain,
            )
            self.assertEqual(D(production["recipe:wd-grain"]["shock_multiplier"]), Decimal(1))
            self.assertEqual(D(production["recipe:fd-grain"]["shock_multiplier"]), Decimal(1))
            if "policy" in active:
                self.assertTrue(
                    any(row["kind"] == "loan-default" for row in result["events"])
                )
            if "weather" in active:
                self.assertTrue(any(row["kind"] == "spoilage" for row in result["events"]))
        self.assertEqual(active_across_window, expected)

    def test_no_network_notion_or_canonical_write_path_is_required(self) -> None:
        isolated = self.root / "offline no-network workspace"
        raw_seed = "raw-seed-must-never-be-persisted"
        blocked = AssertionError("network access attempted by offline economy path")
        with patch("socket.create_connection", side_effect=blocked), patch.object(
            socket.socket, "connect", side_effect=blocked
        ):
            envelopes = [
                cli.initialize_workspace(
                    isolated, scenario_path=SCENARIO_PATH, seed=raw_seed
                )
            ]
            envelopes.extend(
                cli.run_workspace_month(isolated, commit=True) for _ in range(3)
            )
            envelopes.append(cli.verify_workspace(isolated))
        for envelope in envelopes:
            self.assert_safe_envelope(envelope)
        for result_path in sorted(isolated.rglob("result.json")):
            result = read_json(result_path)
            self.assertEqual(result["checks"]["notion_writes"], 0)
            self.assertEqual(result["checks"]["canonical_ledger_postings"], 0)
            self.assertIs(result["checks"]["campaign_advanced"], False)
        for path in isolated.rglob("*"):
            if path.is_file():
                self.assertNotIn(raw_seed.encode("utf-8"), path.read_bytes())

    def test_windows_launcher_uses_package_mode_to_avoid_stdlib_shadowing(self) -> None:
        launcher_path = next(
            candidate
            for candidate in (
                HERE.parent / "OPEN-BAEN-WHOLE-ECONOMY.cmd",
                HERE / "OPEN-BAEN-WHOLE-ECONOMY.cmd",
            )
            if candidate.exists()
        )
        launcher = launcher_path.read_text(encoding="utf-8")
        self.assertIn('set "PYTHONPATH=%REPO_ROOT%src"', launcher)
        self.assertEqual(
            launcher.count("-m baen_economy.whole_economy_cli"), 4
        )
        self.assertIn(
            '-m baen_economy.whole_economy_cli boot "%WORKSPACE%"', launcher
        )
        self.assertIn("whole-economy-preview-v3", launcher)
        self.assertNotIn("Loading the sealed campaign operation queue", launcher)
        self.assertNotIn("Silently checking sealed campaign activation gates", launcher)
        self.assertNotIn('%PYTHON_CMD% "%CLI%"', launcher)

    def test_state_payload_tampering_is_rejected_before_replay(self) -> None:
        tampered = self.root / "tampered campaign workspace"
        shutil.copytree(self.workspace, tampered)
        path = artifact(tampered, 2, "state.json")
        state = read_json(path)
        state["populations"][0]["population"] = str(
            D(state["populations"][0]["population"]) + 1
        )
        path.write_text(core.canonical_json(state) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(cli.WorkspaceError, "state hash"):
            cli.verify_workspace(tampered)

    def test_run_month_requires_an_exact_state_seal_and_rejects_result_hashes(self) -> None:
        unsealed = deepcopy(self.states[0])
        unsealed.pop("state_hash")
        with self.assertRaisesRegex(core.EconomyError, "must carry a state hash seal"):
            core.run_month(self.scenario, unsealed, SEED)

        wrong_kind = deepcopy(self.states[0])
        wrong_kind["result_hash"] = "0" * 64
        wrong_kind["state_hash"] = core.state_hash(wrong_kind)
        with self.assertRaisesRegex(core.EconomyError, "unexpected result hash"):
            core.run_month(self.scenario, wrong_kind, SEED)

    def test_fully_repaid_loan_cannot_default_under_a_certain_shock(self) -> None:
        scenario = deepcopy(self.scenario)
        loan = scenario["opening_state"]["loans"][0]
        bank = next(
            row
            for row in scenario["opening_state"]["banks"]
            if row["bank_id"] == loan["bank_id"]
        )
        original_principal = D(loan["principal"])
        loan["principal"] = "10"
        loan["annual_rate"] = "0"
        loan["scheduled_principal"] = "10"
        loan["remaining_months"] = "1"
        loan["default_after_missed"] = "1"
        bank["other_assets"] = str(
            D(bank["other_assets"]) + original_principal - Decimal("10")
        )
        policy = next(row for row in scenario["shocks"] if row["type"] == "policy")
        policy["months"] = [1]
        policy["probability"] = "1"
        policy["effects"]["default_risk_delta"] = "1"

        opening = core.initial_state(scenario)
        outcome = core.run_month(scenario, opening, "certain-default-shock")
        closing_loan = next(
            row
            for row in outcome["next_state"]["loans"]
            if row["loan_id"] == loan["loan_id"]
        )
        receipt = next(
            row
            for row in outcome["result"]["banking"]
            if row.get("loan_id") == loan["loan_id"]
            and row.get("action") == "serviced"
        )

        self.assertEqual(closing_loan["status"], "repaid")
        self.assertEqual(receipt["status"], "repaid")
        self.assertEqual(D(closing_loan["principal"]), 0)
        self.assertEqual(D(closing_loan["accrued_interest"]), 0)
        self.assertIs(closing_loan["collateral_released"], True)
        self.assertFalse(
            any(
                event["kind"] == "loan-default"
                and loan["loan_id"] in event["summary"]
                for event in outcome["result"]["events"]
            )
        )

    def test_pledged_stock_is_not_counted_as_price_relevant_market_supply(self) -> None:
        scenario = deepcopy(self.scenario)
        loan = scenario["opening_state"]["loans"][0]
        loan["collateral_owner_id"] = "entity:institut-tissage-arcanique"
        loan["collateral_settlement_id"] = "waterdeep"
        loan["collateral_commodity_id"] = "wool"
        loan["collateral_quantity"] = "400"

        opening = core.initial_state(scenario)
        wool_before = next(
            row
            for row in opening["prices"]
            if row["settlement_id"] == "waterdeep"
            and row["commodity_id"] == "wool"
        )
        outcome = core.run_month(scenario, opening, "pledged-supply-price-seed")
        wool_after = next(
            row
            for row in outcome["next_state"]["prices"]
            if row["settlement_id"] == "waterdeep"
            and row["commodity_id"] == "wool"
        )

        self.assertEqual(D(wool_after["price"]), D(wool_before["price"]))
        self.assertFalse(
            any(
                trade["commodity_id"] == "wool"
                for trade in outcome["result"]["trade"]
            )
        )

    def test_scenario_object_key_order_cannot_change_a_replay(self) -> None:
        first = deepcopy(self.scenario)
        second = deepcopy(self.scenario)
        first_recipe = next(
            row for row in first["recipes"] if row["id"] == "recipe:nw-grain"
        )
        second_recipe = next(
            row for row in second["recipes"] if row["id"] == "recipe:nw-grain"
        )
        first_recipe["labor"] = {"farm": "3", "craft": "1"}
        second_recipe["labor"] = {"craft": "1", "farm": "3"}

        self.assertEqual(core.state_hash(first), core.state_hash(second))
        first_opening = core.initial_state(first)
        second_opening = core.initial_state(second)
        self.assertEqual(first_opening, second_opening)
        first_outcome = core.run_month(first, first_opening, "key-order-replay-seed")
        second_outcome = core.run_month(
            second, second_opening, "key-order-replay-seed"
        )

        self.assertEqual(
            first_outcome["result"]["result_hash"],
            second_outcome["result"]["result_hash"],
        )
        self.assertEqual(
            first_outcome["next_state"]["state_hash"],
            second_outcome["next_state"]["state_hash"],
        )
        self.assertEqual(
            core.canonical_json(first_outcome),
            core.canonical_json(second_outcome),
        )

    def test_state_is_bound_to_exact_scenario_and_scenario_tampering_is_rejected(self) -> None:
        changed_scenario = deepcopy(self.scenario)
        changed_scenario["source_refs"] = [
            *changed_scenario["source_refs"],
            "acceptance-probe:changed-scenario-payload",
        ]
        with self.assertRaisesRegex(core.EconomyError, "exact scenario payload"):
            core.run_month(changed_scenario, self.states[0], SEED)

        tampered = self.root / "tampered scenario workspace"
        shutil.copytree(self.workspace, tampered)
        scenario_path = tampered / "scenario.json"
        scenario = read_json(scenario_path)
        scenario["source_refs"].append("acceptance-probe:workspace-tamper")
        scenario_path.write_text(
            core.canonical_json(scenario) + "\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(cli.WorkspaceError, "scenario hash"):
            cli.verify_workspace(tampered)


if __name__ == "__main__":
    unittest.main()
