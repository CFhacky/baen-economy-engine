from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/"recovery/SOURCEBOOK_ECONOMIC_CONSTANTS_2026-09-18.json"

class SourcebookEconomicConstantsTests(unittest.TestCase):
    def setUp(self):
        self.payload=json.loads(PATH.read_text(encoding="utf-8"))

    def test_all_rows_stay_inside_adopted_authority_with_sourcebook_provenance(self):
        self.assertEqual(self.payload["authority"],"UPSTREAM-ADOPTED")
        self.assertEqual(self.payload["provenance_kind"],"SOURCEBOOK_RAW")

    def test_forgotten_realms_trade_example_matches_generic_35_anchor(self):
        rows={}
        for source in self.payload["sources"]:
            for fact in source["facts"]:
                rows[fact["key"]]=fact
        self.assertEqual(rows["fr.silver_marches.flour_gp_per_lb"]["value"],0.02)
        self.assertEqual(rows["dnd35.trade.flour_gp_per_lb"]["value"],0.02)
        self.assertEqual(rows["fr.silver_marches.salt_gp_per_lb"]["value"],5)
        self.assertEqual(rows["dnd35.trade.salt_gp_per_lb"]["value"],5)

    def test_cross_system_currency_and_st_conversion_are_explicitly_forbidden(self):
        joined=" ".join(self.payload["model_guardrails"])
        self.assertIn("Do not combine currencies",joined)
        self.assertIn("Do not convert GURPS 3e draft-horse ST directly",joined)

if __name__=="__main__":
    unittest.main()
