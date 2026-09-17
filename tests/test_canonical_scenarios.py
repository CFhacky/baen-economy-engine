from decimal import Decimal
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from baen_economy.domain import AccountingTreatment, TemporalState  # noqa: E402
from baen_economy.registry import (  # noqa: E402
    Classification, ConsolidationError, consolidated_monthly_totals, normalize_row,
    stable_source_record_id,
)


D = Decimal
FIXTURES = ROOT / "fixtures" / "canonical-import"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class CanonicalScenarioTests(unittest.TestCase):
    def test_snowfall_current_state_is_approved_but_undrawn(self):
        fixture = load("snowfall-hearthworks.json")
        self.assertEqual(fixture["scenario_id"], "snowfall-hearthworks")
        self.assertEqual(fixture["business_type"], "heating_systems_manufacturer")
        current = fixture["current_anchor"]
        self.assertEqual(current["campaign_date"], "7 Hammer 1495 DR")
        self.assertEqual(D(current["facility_limit_gp"]), D("30000"))
        self.assertEqual(D(current["facility_drawn_gp"]), D("0"))
        self.assertEqual(D(current["monthly_revenue_gp"]), D("0"))
        self.assertEqual(D(current["monthly_cost_gp"]), D("0"))
        self.assertEqual(D(current["veldrin_equity_percent"]), D("75"))
        self.assertEqual(current["timeline_id"], "source:snowfall-hearthworks-hammer-1495")
        self.assertEqual(current["economy_timeline_mapping"], "unresolved_CAN-001")
        self.assertEqual(D(current["ncf_effects_at_anchor"]["revenue_change_gp"]), D("0"))
        self.assertTrue(any("Capital Invested" in item for item in fixture["unresolved"]))

    def test_snowfall_forward_replay_and_finance_arithmetic(self):
        fixture = load("snowfall-hearthworks.json")
        forward = fixture["forward_resolved"]
        self.assertEqual(sum(forward["progress_percent_by_month"]), 105)
        self.assertEqual(forward["opening_date"], "1 Eleint 1495 DR")
        opening = forward["opening_month"]
        authority = forward["opening_month_field_authority"]
        self.assertEqual(authority["revenue_gp"], "canon_import")
        self.assertEqual(authority["operating_profit_before_interest_gp"], "canon_import")
        self.assertEqual(
            authority[
                "cash_remainder_after_payment_before_dues_or_additional_reserves_gp"
            ],
            "canon_import",
        )
        self.assertEqual(authority["first_month_interest_gp"], "engine_derived")
        revenue = D(opening["revenue_gp"])
        cost = D(opening["operating_cost_gp"])
        interest = D(opening["first_month_interest_gp"])
        principal = D(opening["first_month_principal_gp"])
        payment = D(opening["illustrative_full_draw_payment_gp"])
        self.assertEqual(revenue - cost, D(opening["operating_profit_before_interest_gp"]))
        self.assertEqual(revenue - cost - interest, D(opening["accounting_profit_after_interest_gp"]))
        self.assertEqual(interest + principal, payment)
        cash_remainder = opening[
            "cash_remainder_after_payment_before_dues_or_additional_reserves_gp"
        ]
        self.assertEqual(revenue - cost - payment, D(cash_remainder))
        self.assertNotEqual(cash_remainder, opening["accounting_profit_after_interest_gp"])

    def test_laden_table_remains_a_plan_until_rolls_and_missing_inputs_resolve(self):
        fixture = load("operation-laden-table.json")
        snowfall = load("snowfall-hearthworks.json")
        self.assertEqual(fixture["scenario_id"], "operation-laden-table")
        self.assertNotEqual(fixture["scenario_id"], snowfall["scenario_id"])
        self.assertEqual(fixture["operation_type"], "food_relief_and_logistics")
        self.assertEqual(
            fixture["timeline_id"],
            "source:operation-laden-table-late-kythorn-1495",
        )
        self.assertEqual(fixture["economy_timeline_mapping"], "unresolved_CAN-001")
        self.assertEqual(fixture["status"], "Active")
        self.assertEqual(fixture["phase"], "assembly and instruction")
        self.assertEqual(fixture["resolved_execution_rolls"], [])
        self.assertEqual(fixture["resolved_or_source_recorded_transactions"], [])
        self.assertEqual(sum(item["count"] for item in fixture["planned_roll_contracts"]), 7)
        self.assertEqual(fixture["trigger"]["agricultural_shelter_zones_destroyed"], 3)
        self.assertEqual(fixture["local_food_position"], "net_importer")
        self.assertEqual(D(fixture["grain_target_tons"]["low"]), D("1200"))
        self.assertEqual(D(fixture["grain_target_tons"]["high"]), D("1500"))
        self.assertEqual(D(fixture["borrowing_target_gp"]["low"]), D("200000"))
        self.assertEqual(fixture["borrowing_accounting_treatment"]["debtor"], "Baen")
        self.assertEqual(
            fixture["borrowing_accounting_treatment"]["proceeds"],
            "liability_not_revenue",
        )
        self.assertIn("route capacities and travel time", fixture["unresolved"])
        self.assertIn("loan terms, draw timing, currency, rate, maturity and collateral", fixture["unresolved"])

    def test_ncf_uses_branch_basis_without_adding_parent(self):
        fixture = load("ncf-consolidation.json")
        parent_class = Classification(
            TemporalState.CURRENT, AccountingTreatment.CONSOLIDATION_ONLY,
            fixture["source_refs"][0], "umbrella row",
            timeline_id="ncf-import", effective_ordinal=1,
        )
        branch_class = Classification(
            TemporalState.CURRENT, AccountingTreatment.OPERATING_UNIT,
            fixture["source_refs"][0], "branch basis fixture",
            timeline_id="ncf-import", effective_ordinal=1,
        )
        parent = normalize_row(
            {"url": fixture["source_refs"][0], "Entity": fixture["parent"]["name"], "Monthly Revenue": fixture["parent"]["revenue_gp"]},
            {stable_source_record_id(fixture["source_refs"][0]): parent_class},
        )
        rows = [parent]
        for branch, source_ref in zip(fixture["branches"], fixture["source_refs"][1:]):
            rows.append(normalize_row(
                {"url": source_ref, "Entity": branch["name"], "Parent Entity": fixture["parent"]["name"], "Monthly Revenue": branch["revenue_gp"], "Monthly Cost": branch["cost_gp"]},
                {stable_source_record_id(source_ref): branch_class},
            ))
        totals = consolidated_monthly_totals(
            rows, timeline_id="ncf-import", as_of_ordinal=1
        )
        self.assertEqual(totals["monthly_revenue"], D(fixture["branch_totals"]["revenue_gp"]))
        self.assertNotEqual(totals["monthly_revenue"], D(fixture["forbidden_blind_sum_revenue_gp"]))

        parent_summary = normalize_row(
            {
                "url": fixture["source_refs"][0],
                "Entity": fixture["parent"]["name"],
                "Monthly Revenue": fixture["parent"]["revenue_gp"],
            },
            {stable_source_record_id(fixture["source_refs"][0]): branch_class},
        )
        parent_totals = consolidated_monthly_totals(
            [parent_summary], timeline_id="ncf-import", as_of_ordinal=1
        )
        self.assertEqual(parent_totals["monthly_revenue"], D("22000"))

        all_operating = [parent_summary]
        for branch, source_ref in zip(fixture["branches"], fixture["source_refs"][1:]):
            all_operating.append(normalize_row(
                {
                    "url": source_ref,
                    "Entity": branch["name"],
                    "Parent Entity": fixture["parent"]["name"],
                    "Monthly Revenue": branch["revenue_gp"],
                    "Monthly Cost": branch["cost_gp"],
                },
                {stable_source_record_id(source_ref): branch_class},
            ))
        with self.assertRaisesRegex(ConsolidationError, "parent and child"):
            consolidated_monthly_totals(
                all_operating, timeline_id="ncf-import", as_of_ordinal=1
            )


if __name__ == "__main__":
    unittest.main()
