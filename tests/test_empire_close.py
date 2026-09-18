from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from baen_economy.empire_close import EmpireCloseError, close_status, load_close_recovery

class EmpireCloseTests(unittest.TestCase):
    def test_close_is_zero_time_and_exposes_real_action_queue(self):
        result=close_status()
        self.assertFalse(result["canonical"])
        self.assertFalse(result["campaign_time_advanced"])
        self.assertFalse(result["ready_for_canonical_month"])
        self.assertGreater(result["accepted_values"],20)
        self.assertGreater(result["unresolved_items"],5)
        self.assertEqual({r["id"] for r in result["user_actions"]},{"forgedeep-pop","crownworks"})
        self.assertIn("fleet-roster",{r["id"] for r in result["routine_actions"]})

    def test_current_rail_does_not_promote_future_deep_road(self):
        result=close_status()
        rail=result["lanes"]["rail"]
        row={r["key"]:r for r in rail["facts"]}["deep_road.day7_hammer_operational"]
        self.assertIs(row["value"],False)
        self.assertEqual(row["authority"],"SOURCE-DERIVED")

    def test_canal_has_sourced_vessel_constants_but_not_fake_current_fleet(self):
        result=close_status()
        lane=result["lanes"]["canal_waterway"]
        facts={row["key"]:row for row in lane["facts"]}
        self.assertEqual(facts["hunding.standard_canal_barge.cargo_tons"]["value"],100)
        self.assertEqual(facts["hunding.heavy_ore_carrier.cargo_tons"]["value"],150)
        self.assertEqual(facts["hunding.lock.standard_transit_minutes_min"]["value"],25)
        self.assertTrue(any(row["key"]=="hunding.current_barge_fleet" for row in lane["unresolved"]))

    def test_western_quarry_barges_are_not_silently_promoted_to_hunding_class(self):
        result=close_status()
        lane=result["lanes"]["conventional_freight"]
        facts={row["key"]:row for row in lane["facts"]}
        self.assertEqual(
            facts["western_limestone.barge_capacity_status"]["value"],
            "TWO_BARGES_CONFIRMED_CAPACITY_NOT_IDENTIFIED",
        )

    def test_affiliated_nrtc_capacity_is_recovered_without_calling_it_empire_owned(self):
        result=close_status()
        facts={row["key"]:row for row in result["lanes"]["conventional_freight"]["facts"]}
        self.assertEqual(facts["nrtc.current_wagon_count"]["value"],4)
        self.assertIn("Affiliated commercial capacity",facts["nrtc.current_wagon_count"]["note"])

    def test_ncf_parent_revenue_precedence_closes_stale_branch_rollup_discrepancy(self):
        result=close_status()
        lane=result["lanes"]["ncf_finance"]
        self.assertFalse(any(row["key"]=="ncf.monthly_revenue_total" for row in lane.get("conflicts",[])))
        resolved={row["key"]:row for row in lane["resolved_discrepancies"]}
        self.assertEqual(resolved["ncf.monthly_revenue_total"]["selected_value_gp_per_month"],22000)

    def test_ncf_named_loans_do_not_fill_unknown_portfolio(self):
        result=close_status()
        lane=result["lanes"]["ncf_finance"]
        calc={r["key"]:r for r in lane["calculated"]}
        self.assertEqual(calc["ncf.named_active_loans_recovered_gp"]["value"],30000)
        self.assertTrue(any(r["key"]=="ncf.remaining_loan_book_2270000_gp" for r in lane["unresolved"]))

    def test_non_executable_fact_fails_closed(self):
        payload=load_close_recovery()
        payload["lanes"]["heavy_machinery"]["facts"].append(
            {"key":"bad","value":99,"authority":"MODEL-PROPOSED"}
        )
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"bad.json"
            path.write_text(json.dumps(payload),encoding="utf-8")
            with self.assertRaises(EmpireCloseError):
                load_close_recovery(path)

if __name__=="__main__":
    unittest.main()
