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
