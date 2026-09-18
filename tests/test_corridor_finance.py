from __future__ import annotations

import unittest

from baen_economy.corridor_finance import corridor_finance_snapshot

class CorridorFinanceTests(unittest.TestCase):
    def test_progressive_esamt_interests_do_not_invent_shares_or_transfer_land(self):
        snap = corridor_finance_snapshot()
        interests = snap["land_bank"]["esamt_interests"]
        self.assertTrue(interests["progressive_buy_in_confirmed"])
        self.assertIsNone(interests["day7_percentage"])
        self.assertIsNone(interests["settled_cost_basis_gp"])
        self.assertTrue(interests["manager_is_not_beneficial_owner"])
        self.assertTrue(interests["does_not_transfer_corridor_land_title"])
        self.assertEqual(snap["internal_transport"]["ratified_empire_fleet"], {"Stonebearer": 10, "Groundshaper": 5, "Ironmaw": 5})

    def test_user_ruled_corridor_math_is_not_mistaken_for_net_title(self):
        snap=corridor_finance_snapshot()
        land=snap["land_bank"]
        self.assertEqual(land["half_width_each_side_miles"],"8")
        self.assertEqual(land["full_corridor_width_miles"],"16")
        self.assertEqual(land["operational_network_miles_lower_bound"],"500")
        self.assertEqual(land["gross_strip_square_miles_at_500_mile_floor"],"8000")
        self.assertEqual(land["gross_strip_acres_at_500_mile_floor"],"5120000")
        self.assertTrue(land["not_actual_titled_acreage"])
        self.assertEqual(land["authority"],"SOURCE-DERIVED")

    def test_stonebearer_short_haul_capacity_uses_only_sourced_four_unit_allocation(self):
        snap=corridor_finance_snapshot()
        transport=snap["internal_transport"]
        self.assertFalse(transport["external_sales"])
        self.assertTrue(transport["earthmover_jeep_road_configuration"])
        self.assertEqual(transport["stonebearer_payload_tons"],"15")
        self.assertEqual(transport["brickworks_allocated_stonebearers"],4)
        self.assertEqual(transport["brickworks_short_haul_capacity_tons_per_day_min"],"360")
        self.assertEqual(transport["brickworks_short_haul_capacity_tons_per_day_max"],"420")
        self.assertIn("Empire-wide",transport["unresolved"])
        self.assertIsNone(transport["actual_assigned_tons_per_day"])
        self.assertIsNone(transport["unallocated_transport_capacity_tons_per_day"])

    def test_future_roadrider_does_not_supply_current_earthmover_performance(self):
        transport=corridor_finance_snapshot()["internal_transport"]
        future=transport["roadrider_dedicated_line"]
        self.assertTrue(transport["earthmover_jeep_road_configuration"])
        self.assertFalse(future["available_at_campaign_boundary"])
        self.assertTrue(future["not_earthmover_road_mode_specs"])
        self.assertEqual(future["temporal_scope"],"FORWARD_DESIGN")

    def test_ncf_portfolio_keeps_rate_anchors_without_fake_average_apr(self):
        snap=corridor_finance_snapshot()
        lending=snap["ncf_lending"]
        self.assertEqual(lending["active_loan_principal_gp"],2300000)
        self.assertEqual(lending["monthly_ncf_revenue_gp"],22000)
        self.assertEqual([r["annual_rate_pct"] for r in lending["rate_anchors"]],[8,12])
        self.assertTrue(lending["do_not_infer_average_apr"])

if __name__=="__main__":
    unittest.main()
