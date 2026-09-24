from copy import deepcopy
import unittest

from baen_economy.financial_close import (
    FinancialCloseError, financial_close_snapshot, settlement_progress,
)


class FinancialCloseTests(unittest.TestCase):
    def test_partial_book_does_not_add_parent_and_children_or_invent_equity(self):
        result = financial_close_snapshot()
        loans = result["loans"]
        self.assertEqual(loans["parent_principal_gp"], "2300000")
        self.assertEqual(loans["named_principal_gp"], "30000")
        self.assertEqual(loans["unitemized_principal_gp"], "2270000")
        self.assertEqual(loans["approved_undrawn"][0]["principal_drawn_gp"], "0")
        self.assertTrue(all(r["day7_principal_gp"] is None for r in loans["historical_unreconciled"]))
        self.assertIsNone(result["trial_balance"]["balanced"])
        self.assertIsNone(result["trial_balance"]["equity_total_gp"])
        self.assertFalse(result["trial_balance"]["balancing_plug_created"])
        self.assertIsNone(result["treasury"]["opening_liquid_cash_gp"])

    def test_client_interests_and_land_appraisal_are_not_bank_cash(self):
        result = financial_close_snapshot()
        self.assertFalse(result["client_interests"]["included_in_ncf_owned_assets"])
        self.assertIsNone(result["client_interests"]["hunding_percentage"])
        land = result["land_register"][0]
        self.assertEqual(land["record_kind"], "COLLECTION_NOT_PARCEL")
        self.assertEqual(land["gross_strip_acres"], "5120000")
        self.assertIsNone(land["unique_titled_acres"])
        self.assertIsNone(land["cost_basis_gp"])
        self.assertIsNone(land["mineral_rights"])
        self.assertFalse(land["valuation_included_in_operating_cash"])
        self.assertFalse(result["can_authorize_capital_from_this_report"])

    def test_unplayed_auction_preserves_target_and_excludes_old_liquidation(self):
        result = financial_close_snapshot()
        cash = result["protected_liquidity"]
        self.assertEqual(cash["net_settled_gp"], "0")
        self.assertEqual(cash["remaining_gp"], "450000")
        self.assertIn("klauth-prior-clean-art-liquidation", cash["excluded_receipt_ids"])
        self.assertFalse(result["campaign_time_advanced"])
        self.assertEqual(result["canonical_ledger_postings"], 0)

    def test_only_current_net_settlement_reduces_target(self):
        target = {"id": "test", "amount_gp": "450000", "authority": "USER-RULED", "source": "test"}
        settled = {"id": "a", "target_id": "test", "status": "NET_SETTLED",
                   "net_settled_gp": "9700.25", "temporal_scope": "CURRENT_OPERATION",
                   "authority": "SOURCE-DERIVED", "source": "test receipt"}
        receivable = dict(settled, id="b", status="RECEIVABLE", net_settled_gp="100000")
        other = dict(settled, id="c", target_id="other")
        result = settlement_progress(target, [settled, receivable, other])
        self.assertEqual(result["remaining_gp"], "440299.75")
        self.assertEqual(result["excluded_receipt_ids"], ["b", "c"])
        for field, value in (("authority", "MODEL-PROPOSED"), ("temporal_scope", "HISTORICAL"),
                             ("source", ""), ("net_settled_gp", "NaN"),
                             ("net_settled_gp", -1), ("net_settled_gp", 1.2)):
            row = deepcopy(settled)
            row[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(FinancialCloseError):
                settlement_progress(target, [row])
        with self.assertRaises(FinancialCloseError):
            settlement_progress(target, [settled, settled])


if __name__ == "__main__":
    unittest.main()
