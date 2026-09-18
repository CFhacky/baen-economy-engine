from __future__ import annotations

import json
import unittest
from pathlib import Path

from baen_economy.empire_source_products import (
    DEFAULT_SOURCE_INPUTS,
    PRODUCTION_LINE_SPECS,
    source_production_lines,
)


class EmpireSourceProductsTests(unittest.TestCase):
    def test_production_lines_are_loaded_from_source_authority(self):
        lines = source_production_lines()
        self.assertEqual(len(lines), 5)
        by_id = {row["id"]: row for row in lines}
        self.assertEqual(by_id["brickworks"]["quantity"], 75000)
        self.assertEqual(by_id["clay_quarries"]["quantity"], 2000)
        self.assertEqual(by_id["silversheen_aluminum"]["quantity"], 180)
        self.assertEqual(by_id["star_metal_hills_bauxite"]["quantity"], 800)
        self.assertEqual(by_id["warborn_neverwinter"]["quantity"], 12)
        self.assertEqual(by_id["warborn_neverwinter"]["maximum"], 15)
        for row in lines:
            self.assertEqual(row["authority"], "SOURCE-DERIVED")
            self.assertFalse(row["recipe_invented"])
            self.assertTrue(str(row["source"]["notion_page"]))
            self.assertTrue(str(row["source"]["title"]))

    def test_every_spec_key_exists_in_authority(self):
        payload = json.loads(Path(DEFAULT_SOURCE_INPUTS).read_text(encoding="utf-8"))
        keys = {row["key"] for row in payload["facts"]}
        for spec in PRODUCTION_LINE_SPECS:
            self.assertIn(spec.quantity_key, keys)
            self.assertIn(spec.employees_key, keys)
            if spec.maximum_key:
                self.assertIn(spec.maximum_key, keys)

    def test_silversheen_cost_and_allocation_remain_fail_closed(self):
        payload = json.loads(Path(DEFAULT_SOURCE_INPUTS).read_text(encoding="utf-8"))
        blockers = {row["key"]: row for row in payload["blockers"]}
        self.assertEqual(blockers["silversheen.current_monthly_cost_gp"]["status"], "MISSING_DATA")
        self.assertEqual(blockers["silversheen.warborn_aluminum_allocation"]["status"], "CONFLICT")
        self.assertIn("Do not scale", blockers["silversheen.current_monthly_cost_gp"]["reason"])


if __name__ == "__main__":
    unittest.main()
