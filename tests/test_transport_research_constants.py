from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/"recovery/TRANSPORT_RESEARCH_CONSTANTS_2026-09-18.json"

class TransportResearchConstantsTests(unittest.TestCase):
    def test_comparators_are_upstream_adopted_not_campaign_fleet_facts(self):
        payload=json.loads(PATH.read_text(encoding="utf-8"))
        rows={row["key"]:row for row in payload["comparators"]}
        self.assertEqual(rows["historical.conestoga.max_cargo_tons"]["value"],5)
        self.assertEqual(rows["historical.conestoga.team_horses"]["value"],6)
        self.assertEqual(rows["historical.conestoga.miles_per_day"]["value"],15)
        self.assertTrue(all(row["authority"]=="UPSTREAM-ADOPTED" for row in rows.values()))
        self.assertTrue(any("20–40 ton" in rule for rule in payload["guardrails"]))

if __name__=="__main__":
    unittest.main()
