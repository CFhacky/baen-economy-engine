from __future__ import annotations

import copy
from dataclasses import replace
from decimal import Context, Decimal, ROUND_HALF_UP, localcontext
import hashlib
import json
from pathlib import Path
import sys
import unittest


PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
sys.path.insert(0, str(SRC))

from baen_economy.business_dice import roll_business_checks  # noqa: E402
from baen_economy.business_month import (  # noqa: E402
    BusinessMonthError,
    employee_size_modifier,
    expense_factor,
    find_source_record_id,
    preview_business_month,
    revenue_factor,
    validate_business_preview,
)
from baen_economy.operator_codec import canonical_hash  # noqa: E402
from baen_economy.operator_dice import classify_3d6  # noqa: E402
from baen_economy.registry import AuditResult  # noqa: E402
from baen_economy.registry_export import load_registry_export  # noqa: E402


D = Decimal
REGISTRY_EXPORT = (
    PROJECT / "fixtures" / "registry-snapshots" / "business-registry-2026-08-29.json"
)
BRICKWORKS_SOURCE_ID = "notion:321e821484b0816c87fbf0fee22835ad"
MISSING_COST_SOURCE_ID = "notion:392e821484b081efb0a9d73f9b9757d7"
MONTH_LABEL = "Eleint 1494 DR preview"
SEED = "gate1-business-known-answer"
SIZE_MODIFIER = [{"label": "entity size below 50 employees", "value": 2}]


def _assert_no_binary_floats(test: unittest.TestCase, value: object) -> None:
    if isinstance(value, float):
        test.fail(f"binary float leaked into business preview: {value!r}")
    if isinstance(value, dict):
        for item in value.values():
            _assert_no_binary_floats(test, item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _assert_no_binary_floats(test, item)


class BusinessMonthMechanicsTests(unittest.TestCase):
    def test_gurps_critical_and_margin_boundaries(self) -> None:
        cases = (
            (3, -20, "critical_success"),
            (4, -20, "critical_success"),
            (5, 14, "success_by_5_plus"),
            (5, 15, "critical_success"),
            (6, 15, "success_by_5_plus"),
            (6, 16, "critical_success"),
            (15, 15, "exact_target"),
            (17, 15, "critical_failure"),
            (17, 16, "failure"),
            (18, 30, "critical_failure"),
            (16, 6, "critical_failure"),
        )
        for total, target, expected in cases:
            with self.subTest(total=total, target=target):
                self.assertEqual(
                    classify_3d6(total=total, effective_target=target), expected
                )

    def test_revenue_result_factors_are_exact_decimals(self) -> None:
        cases = (
            ("critical_success", 0, "1.25"),
            ("success_by_5_plus", 5, "1.15"),
            ("success", 1, "1.05"),
            ("exact_target", 0, "1.00"),
            ("failure", -1, "0.90"),
            ("failure_by_5_plus", -5, "0.80"),
            ("critical_failure", -1, "0.70"),
        )
        for outcome, margin, expected in cases:
            with self.subTest(outcome=outcome, margin=margin):
                actual = revenue_factor(outcome, margin)
                self.assertIs(type(actual), Decimal)
                self.assertEqual(actual, D(expected))

    def test_expense_result_factors_are_exact_decimals(self) -> None:
        cases = (
            ("critical_success", 0, "0.90"),
            ("success_by_5_plus", 5, "1.00"),
            ("success", 1, "1.05"),
            ("exact_target", 0, "1.05"),
            ("failure", -1, "1.15"),
            ("failure_by_5_plus", -5, "1.15"),
            ("critical_failure", -1, "1.25"),
        )
        for outcome, margin, expected in cases:
            with self.subTest(outcome=outcome, margin=margin):
                actual = expense_factor(outcome, margin)
                self.assertIs(type(actual), Decimal)
                self.assertEqual(actual, D(expected))

    def test_result_factors_reject_unknown_or_inconsistent_inputs(self) -> None:
        for function in (revenue_factor, expense_factor):
            with self.subTest(function=function.__name__, case="unknown"):
                with self.assertRaises((BusinessMonthError, ValueError)):
                    function("invented_result", 0)
            with self.subTest(function=function.__name__, case="boolean margin"):
                with self.assertRaises((BusinessMonthError, ValueError, TypeError)):
                    function("success", True)
            with self.subTest(function=function.__name__, case="misclassified success"):
                with self.assertRaises((BusinessMonthError, ValueError)):
                    function("success", 5)
            with self.subTest(function=function.__name__, case="misclassified exact"):
                with self.assertRaises((BusinessMonthError, ValueError)):
                    function("exact_target", 1)

    def test_employee_size_boundaries_reject_source_table_overlaps(self) -> None:
        accepted = {
            0: 2,
            49: 2,
            D("48"): 2,
            50: 0,
            199: 0,
            201: -2,
            999: -2,
            1001: -4,
            100_000: -4,
        }
        for employees, expected in accepted.items():
            with self.subTest(employees=employees):
                self.assertEqual(employee_size_modifier(employees), expected)

        for employees in (200, 1000):
            with self.subTest(ambiguous=employees):
                with self.assertRaisesRegex(
                    (BusinessMonthError, ValueError), "ambiguous|200|1000"
                ):
                    employee_size_modifier(employees)

        for employees in (-1, True, D("49.5"), D("NaN")):
            with self.subTest(invalid=employees):
                with self.assertRaises((BusinessMonthError, ValueError, TypeError)):
                    employee_size_modifier(employees)


class BusinessMonthPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.export = load_registry_export(REGISTRY_EXPORT)

    def preview(self, *, month_label: str = MONTH_LABEL) -> dict[str, object]:
        return preview_business_month(
            self.export,
            source_record_id=BRICKWORKS_SOURCE_ID,
            month_label=month_label,
            seed=SEED,
            market="stable",
            vara_active=False,
            revenue_streams=1,
            competent_managers=0,
            monopoly=False,
            excellent_accounting=False,
            rapid_expansion=False,
        )

    def test_seeded_business_dice_have_a_source_bound_known_answer(self) -> None:
        # A fixed synthetic snapshot identity keeps this algorithm vector stable even
        # when the checked-in registry capture is deliberately refreshed.
        dice_snapshot_hash = "a" * 64
        first = roll_business_checks(
            snapshot_hash=dice_snapshot_hash,
            source_record_id=BRICKWORKS_SOURCE_ID,
            month_label=MONTH_LABEL,
            seed=SEED,
            revenue_modifiers=[],
            expense_modifiers=SIZE_MODIFIER,
        )
        second = roll_business_checks(
            snapshot_hash=dice_snapshot_hash,
            source_record_id=BRICKWORKS_SOURCE_ID,
            month_label=MONTH_LABEL,
            seed=SEED,
            revenue_modifiers=[],
            expense_modifiers=SIZE_MODIFIER,
        )
        self.assertEqual(first, second)
        self.assertEqual(first["campaign_state_rolls_resolved"], 0)
        self.assertEqual(first["seed_fingerprint"], hashlib.sha256(SEED.encode()).hexdigest())
        rolls = {roll["roll_key"]: roll for roll in first["rolls"]}
        self.assertEqual(rolls["revenue"]["dice"], [1, 2, 3])
        self.assertEqual(rolls["revenue"]["effective_target"], 15)
        self.assertEqual(rolls["revenue"]["margin"], 9)
        self.assertEqual(rolls["revenue"]["outcome"], "success_by_5_plus")
        self.assertEqual(rolls["expense"]["dice"], [4, 3, 5])
        self.assertEqual(rolls["expense"]["effective_target"], 18)
        self.assertEqual(rolls["expense"]["margin"], 6)
        self.assertEqual(rolls["expense"]["outcome"], "success_by_5_plus")
        self.assertNotIn(SEED, json.dumps(first, sort_keys=True))

        for bad_seed in (None, ""):
            with self.subTest(bad_seed=bad_seed):
                with self.assertRaises(ValueError):
                    roll_business_checks(
                        snapshot_hash=dice_snapshot_hash,
                        source_record_id=BRICKWORKS_SOURCE_ID,
                        month_label=MONTH_LABEL,
                        seed=bad_seed,
                        revenue_modifiers=[],
                        expense_modifiers=SIZE_MODIFIER,
                    )

    def test_month_preview_is_deterministic_and_uses_exact_source_amounts(self) -> None:
        first = self.preview()
        second = self.preview()
        self.assertEqual(first, second)
        self.assertEqual(first["schema"], "tnp.business.month-preview/1")
        self.assertFalse(first["canonical"])
        self.assertEqual(first["mode"], "preview")
        self.assertEqual(first["authority"], "scenario_assumption")
        self.assertFalse(first["campaign_time_advanced"])
        self.assertEqual(first["campaign_state_rolls_resolved"], 0)
        self.assertEqual(len(first["content_hash"]), 64)
        financials = first["financials"]
        self.assertEqual(financials["source_projected_revenue"], "3333")
        self.assertEqual(financials["source_projected_cost"], "2233")
        self.assertEqual(
            first["source_binding"]["properties"]["Employees"]["source_value"],
            "30",
        )
        rolls = {roll["roll_key"]: roll for roll in first["dice_manifest"]["rolls"]}
        expected_revenue_factor = revenue_factor(
            rolls["revenue"]["outcome"], rolls["revenue"]["margin"]
        )
        expected_expense_factor = expense_factor(
            rolls["expense"]["outcome"], rolls["expense"]["margin"]
        )
        expected_revenue = (D("3333") * expected_revenue_factor).quantize(
            D("0.01"), rounding=ROUND_HALF_UP
        )
        expected_cost = (D("2233") * expected_expense_factor).quantize(
            D("0.01"), rounding=ROUND_HALF_UP
        )
        self.assertEqual(
            D(str(financials["revenue_factor"])), expected_revenue_factor
        )
        self.assertEqual(
            D(str(financials["expense_factor"])), expected_expense_factor
        )
        self.assertEqual(
            D(str(financials["proposed_revenue"])), expected_revenue
        )
        self.assertEqual(D(str(financials["proposed_cost"])), expected_cost)
        self.assertEqual(
            D(str(financials["proposed_net"])),
            (expected_revenue - expected_cost).quantize(
                D("0.01"), rounding=ROUND_HALF_UP
            ),
        )
        _assert_no_binary_floats(self, first)
        self.assertNotIn(SEED, json.dumps(first, sort_keys=True))

        with localcontext(Context(prec=4)):
            constrained = self.preview()
        self.assertEqual(constrained, first)

    def test_scenario_options_generate_only_allowlisted_modifier_receipts(self) -> None:
        result = preview_business_month(
            self.export,
            BRICKWORKS_SOURCE_ID,
            MONTH_LABEL,
            SEED,
            market="boom",
            vara_active=True,
            revenue_streams=7,
            competent_managers=3,
            monopoly=True,
            excellent_accounting=True,
            rapid_expansion=True,
        )
        self.assertEqual(
            result["assumptions"],
            {
                "market": "boom",
                "vara_active": True,
                "revenue_streams": 7,
                "competent_managers": 3,
                "monopoly": True,
                "excellent_accounting": True,
                "rapid_expansion": True,
            },
        )
        rolls = {roll["roll_key"]: roll for roll in result["dice_manifest"]["rolls"]}
        self.assertEqual(
            rolls["revenue"]["modifiers"],
            [
                {"label": "Market boom", "value": 4},
                {"label": "7+ revenue streams", "value": 2},
                {"label": "Vara active", "value": 3},
                {"label": "Competent managers", "value": 3},
                {"label": "Monopoly position", "value": 2},
            ],
        )
        self.assertEqual(rolls["revenue"]["modifier_total"], 14)
        self.assertEqual(
            rolls["expense"]["modifiers"],
            [
                {"label": "Entity size (30 employees)", "value": 2},
                {"label": "Excellent accounting", "value": 2},
                {"label": "Rapid expansion", "value": -3},
            ],
        )
        self.assertEqual(rolls["expense"]["modifier_total"], 1)
        self.assertNotEqual(result["content_hash"], self.preview()["content_hash"])

    def test_revenue_stream_boundaries_and_option_types_fail_closed(self) -> None:
        expected_stream_modifier = {
            1: None,
            3: None,
            4: ("4-6 revenue streams", 1),
            6: ("4-6 revenue streams", 1),
            7: ("7+ revenue streams", 2),
        }
        for streams, expected in expected_stream_modifier.items():
            with self.subTest(streams=streams):
                result = preview_business_month(
                    self.export,
                    BRICKWORKS_SOURCE_ID,
                    MONTH_LABEL,
                    SEED,
                    vara_active=False,
                    revenue_streams=streams,
                )
                revenue_roll = next(
                    roll
                    for roll in result["dice_manifest"]["rolls"]
                    if roll["roll_key"] == "revenue"
                )
                stream_receipts = [
                    (item["label"], item["value"])
                    for item in revenue_roll["modifiers"]
                    if "revenue streams" in item["label"]
                ]
                self.assertEqual(stream_receipts, [] if expected is None else [expected])

        invalid_options = (
            {"market": "inflation"},
            {"vara_active": 1},
            {"monopoly": "yes"},
            {"revenue_streams": 0},
            {"revenue_streams": True},
            {"competent_managers": -1},
            {"competent_managers": 4},
            {"competent_managers": True},
        )
        for options in invalid_options:
            with self.subTest(options=options):
                with self.assertRaises(BusinessMonthError):
                    preview_business_month(
                        self.export,
                        BRICKWORKS_SOURCE_ID,
                        MONTH_LABEL,
                        SEED,
                        **options,
                    )

        with self.assertRaises(TypeError):
            preview_business_month(
                self.export,
                BRICKWORKS_SOURCE_ID,
                MONTH_LABEL,
                SEED,
                revenue_modifiers=[],
            )

    def test_preview_binds_snapshot_row_and_every_consumed_property(self) -> None:
        result = self.preview()
        binding = result["source_binding"]
        self.assertEqual(binding["export_hash"], self.export.export_hash)
        self.assertEqual(binding["snapshot_hash"], self.export.snapshot_hash)
        self.assertEqual(binding["source_schema_hash"], self.export.source_schema_hash)
        self.assertEqual(binding["transport_content_hash"], self.export.content_hash)
        self.assertEqual(result["entity"]["source_record_id"], BRICKWORKS_SOURCE_ID)
        self.assertEqual(
            binding["row_hash"], self.export.row_hashes[BRICKWORKS_SOURCE_ID]
        )
        expected_hashes = {
            name: self.export.property_hash(BRICKWORKS_SOURCE_ID, name)
            for name in (
                "Entity",
                "Status",
                "Sector",
                "Employees",
                "Monthly Revenue",
                "Monthly Cost",
                "Date Operational",
                "Last Updated",
            )
        }
        self.assertEqual(
            {
                name: receipt["property_hash"]
                for name, receipt in binding["properties"].items()
            },
            expected_hashes,
        )

        changed_month = self.preview(month_label="Marpenoth 1494 DR preview")
        self.assertNotEqual(result["content_hash"], changed_month["content_hash"])

    def test_missing_source_or_required_amount_fails_closed(self) -> None:
        with self.assertRaises((BusinessMonthError, ValueError, KeyError)):
            preview_business_month(
                self.export,
                source_record_id="notion:" + "0" * 32,
                month_label=MONTH_LABEL,
                seed=SEED,
                vara_active=False,
            )

        for entity_name in ("Castle Operations", "The Veil"):
            with self.subTest(noncommercial=entity_name):
                source_id = find_source_record_id(self.export, entity_name)
                with self.assertRaisesRegex(
                    BusinessMonthError, "commercial-sector allowlist"
                ):
                    preview_business_month(
                        self.export,
                        source_record_id=source_id,
                        month_label=MONTH_LABEL,
                        seed=SEED,
                        vara_active=False,
                    )
        audited_name = "Faske & Halloran"
        audited_source_id = find_source_record_id(self.export, audited_name)
        stripped_audit = AuditResult(
            row_count=self.export.audit.row_count,
            field_counts=self.export.audit.field_counts,
            raw_totals=self.export.audit.raw_totals,
            issues=tuple(
                issue
                for issue in self.export.audit.issues
                if issue.entity != audited_name
            ),
        )
        forged_source = replace(self.export, audit=stripped_audit)
        forged_preview = preview_business_month(
            forged_source,
            source_record_id=audited_source_id,
            month_label=MONTH_LABEL,
            seed=SEED,
            vara_active=False,
        )
        with self.assertRaisesRegex(BusinessMonthError, "audit issues"):
            validate_business_preview(forged_preview, export=self.export)
        # SSAMT has no source monthly amounts. Unknown must not become zero.
        with self.assertRaisesRegex(
            (BusinessMonthError, ValueError),
            "Monthly Revenue|monthly revenue|Monthly Cost|monthly cost|unknown|audit issues",
        ):
            preview_business_month(
                self.export,
                source_record_id=MISSING_COST_SOURCE_ID,
                month_label=MONTH_LABEL,
                seed=SEED,
                vara_active=False,
            )

    def test_notion_diff_is_source_bound_review_data_and_ineligible_to_write(self) -> None:
        result = self.preview()
        proposal = result["notion_review_diff"]
        self.assertEqual(proposal["schema"], "tnp.business.notion-review-diff/1")
        self.assertFalse(proposal["executable"])
        self.assertTrue(proposal["review_eligible"])
        self.assertFalse(proposal["write_eligible"])
        self.assertFalse(proposal["write_authorized"])
        self.assertFalse(proposal["write_attempted"])
        self.assertEqual(proposal["applied_count"], 0)
        self.assertEqual(proposal["source_snapshot_hash"], self.export.snapshot_hash)
        self.assertEqual(proposal["target_source_record_id"], BRICKWORKS_SOURCE_ID)
        self.assertEqual(
            proposal["source_row_hash"], self.export.row_hashes[BRICKWORKS_SOURCE_ID]
        )
        self.assertEqual(len(proposal["diff_hash"]), 64)
        self.assertTrue(proposal["blockers"])
        property_diffs = {
            item["property_name"]: item for item in proposal["property_diffs"]
        }
        self.assertEqual(set(property_diffs), {"Monthly Revenue", "Monthly Cost"})
        for property_name, item in property_diffs.items():
            with self.subTest(property_name=property_name):
                self.assertEqual(
                    item["source_property_hash"],
                    self.export.property_hash(BRICKWORKS_SOURCE_ID, property_name),
                )
                self.assertEqual(
                    item["source_value"],
                    self.export.row(BRICKWORKS_SOURCE_ID)[property_name],
                )
                self.assertIn("proposed_value", item)
                self.assertIs(type(item["changed"]), bool)

    def test_preview_attempts_zero_notion_writes_and_zero_ledger_postings(self) -> None:
        before = hashlib.sha256(REGISTRY_EXPORT.read_bytes()).hexdigest()
        result = self.preview()
        after = hashlib.sha256(REGISTRY_EXPORT.read_bytes()).hexdigest()
        self.assertEqual(before, after)
        self.assertFalse(result["notion_review_diff"]["write_attempted"])
        ledger = result["ledger_preview"]
        self.assertFalse(ledger["postable"])
        self.assertFalse(ledger["ledger_post_capability"])
        self.assertEqual(ledger["transaction_count"], 0)
        self.assertEqual(ledger["posting_count"], 0)
        self.assertEqual(ledger["transactions"], [])

    def test_self_hashed_source_write_and_posting_tamper_still_fail_verification(self) -> None:
        original = self.preview()
        body = dict(original)
        supplied_hash = body.pop("content_hash")
        self.assertEqual(supplied_hash, canonical_hash(body))
        validate_business_preview(original, export=self.export)

        attacks = []
        wrong_source = copy.deepcopy(original)
        wrong_source["source_binding"]["row_hash"] = "0" * 64
        attacks.append(wrong_source)

        write_enabled = copy.deepcopy(original)
        write_enabled["notion_review_diff"]["write_authorized"] = True
        write_enabled["notion_review_diff"]["write_attempted"] = True
        write_enabled["notion_review_diff"]["applied_count"] = 1
        attacks.append(write_enabled)

        fabricated_posting = copy.deepcopy(original)
        fabricated_posting["ledger_preview"]["posting_count"] = 1
        fabricated_posting["ledger_preview"]["transactions"] = [
            {"invented": "posting"}
        ]
        attacks.append(fabricated_posting)

        altered_diff = copy.deepcopy(original)
        altered_diff["notion_review_diff"]["property_diffs"][0][
            "proposed_value"
        ] = "999999"
        diff_body = dict(altered_diff["notion_review_diff"])
        diff_body.pop("diff_hash")
        altered_diff["notion_review_diff"]["diff_hash"] = canonical_hash(diff_body)
        attacks.append(altered_diff)

        altered_factor = copy.deepcopy(original)
        altered_factor["financials"]["revenue_factor"] = "1.00"
        altered_factor["financials"]["proposed_revenue"] = "3333.00"
        altered_factor["financials"]["proposed_net"] = "1100.00"
        for item in altered_factor["notion_review_diff"]["property_diffs"]:
            if item["property_name"] == "Monthly Revenue":
                item["proposed_value"] = "3333.00"
                item["changed"] = False
        diff_body = dict(altered_factor["notion_review_diff"])
        diff_body.pop("diff_hash")
        altered_factor["notion_review_diff"]["diff_hash"] = canonical_hash(diff_body)
        attacks.append(altered_factor)

        noncanonical_source_text = copy.deepcopy(original)
        noncanonical_source_text["financials"]["source_projected_revenue"] = (
            "003333.000"
        )
        attacks.append(noncanonical_source_text)

        noncanonical_factor_text = copy.deepcopy(original)
        factor = noncanonical_factor_text["financials"]["revenue_factor"]
        noncanonical_factor_text["financials"]["revenue_factor"] = f"{factor}0"
        attacks.append(noncanonical_factor_text)

        for entity_field, value in (
            ("status", "Preview Approved"),
            ("sector", "Military"),
            ("source_last_updated", "1499-01-01"),
        ):
            altered_entity = copy.deepcopy(original)
            altered_entity["entity"][entity_field] = value
            attacks.append(altered_entity)

        altered_month = copy.deepcopy(original)
        altered_month["month_label"] = "Marpenoth 1494 DR preview"
        attacks.append(altered_month)

        expanded_assumptions = copy.deepcopy(original)
        expanded_assumptions["assumptions"]["posting_approved"] = True
        attacks.append(expanded_assumptions)

        expanded_ledger = copy.deepcopy(original)
        expanded_ledger["ledger_preview"]["posting_approved"] = True
        attacks.append(expanded_ledger)

        rewritten_reason = copy.deepcopy(original)
        rewritten_reason["ledger_preview"]["reason"] = "Posting approved"
        attacks.append(rewritten_reason)

        removed_warnings = copy.deepcopy(original)
        removed_warnings["warnings"] = []
        attacks.append(removed_warnings)

        swapped_rolls = copy.deepcopy(original)
        swapped_rolls["dice_manifest"]["rolls"].reverse()
        dice_body = dict(swapped_rolls["dice_manifest"])
        dice_body.pop("manifest_hash")
        swapped_rolls["dice_manifest"]["manifest_hash"] = canonical_hash(dice_body)
        attacks.append(swapped_rolls)

        swapped_diffs = copy.deepcopy(original)
        swapped_diffs["notion_review_diff"]["property_diffs"].reverse()
        diff_body = dict(swapped_diffs["notion_review_diff"])
        diff_body.pop("diff_hash")
        swapped_diffs["notion_review_diff"]["diff_hash"] = canonical_hash(diff_body)
        attacks.append(swapped_diffs)

        false_preview_count = copy.deepcopy(original)
        false_preview_count["campaign_state_rolls_resolved"] = False
        attacks.append(false_preview_count)

        false_dice_count = copy.deepcopy(original)
        false_dice_count["dice_manifest"]["campaign_state_rolls_resolved"] = False
        dice_body = dict(false_dice_count["dice_manifest"])
        dice_body.pop("manifest_hash")
        false_dice_count["dice_manifest"]["manifest_hash"] = canonical_hash(dice_body)
        attacks.append(false_dice_count)

        false_ledger_count = copy.deepcopy(original)
        false_ledger_count["ledger_preview"]["transaction_count"] = False
        attacks.append(false_ledger_count)

        false_diff_count = copy.deepcopy(original)
        false_diff_count["notion_review_diff"]["applied_count"] = False
        diff_body = dict(false_diff_count["notion_review_diff"])
        diff_body.pop("diff_hash")
        false_diff_count["notion_review_diff"]["diff_hash"] = canonical_hash(diff_body)
        attacks.append(false_diff_count)

        for attack in attacks:
            with self.subTest(attack=attack):
                semantic = dict(attack)
                semantic.pop("content_hash", None)
                attack["content_hash"] = canonical_hash(semantic)
                with self.assertRaises(BusinessMonthError):
                    validate_business_preview(attack, export=self.export)


if __name__ == "__main__":
    unittest.main()
