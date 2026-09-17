from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


PROJECT = Path(__file__).resolve().parents[1]
FIXTURE = PROJECT / "fixtures" / "agriculture" / "agriculture-canon-v1.json"


EXPECTED_SPECIES = {
    "Tiger Shrimp",
    "Tilapia",
    "Freshwater Prawns",
    "Pearl Gourami",
    "Red Claw Crayfish",
    "Littleneck Clams",
    "Largemouth Bass",
    "Blue Crabs",
    "Yellow Perch",
    "Freshwater Mussels",
    "Rainbow Trout",
    "Arctic Char",
    "European Lobster",
    "Northern Pike",
    "Signal Crayfish",
}


class AgricultureCanonAcceptanceTests(unittest.TestCase):
    """Fail closed when the source-grounded agriculture boundary regresses."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.sources = {
            source["source_id"]: source for source in cls.fixture["sources"]
        }

    def test_current_actual_is_frozen_at_day_7_hammer_1495(self) -> None:
        actual = self.fixture["current_actual_state"]
        self.assertEqual(
            actual["campaign_date"], "Day 7 Hammer 1495 DR, midday Hell-cycle"
        )
        self.assertTrue(actual["live_freeze"])
        self.assertFalse(actual["advance_authorized"])
        self.assertFalse(actual["agriculture_month_close_authorized"])
        self.assertEqual(actual["source_id"], "arik-live-freeze")
        self.assertEqual(
            self.sources[actual["source_id"]]["authority_class"],
            "ratified_campaign_state",
        )

    def test_forward_kythorn_scenario_cannot_execute_as_current_actual(self) -> None:
        forward = self.fixture["forward_k1495_state"]
        self.assertEqual(forward["campaign_date"], "late Kythorn 1495 DR")
        self.assertEqual(
            forward["temporal_class"],
            "ratified_forward_scenario_not_current_actual",
        )
        self.assertFalse(forward["actual_execution_eligible"])
        self.assertNotEqual(
            forward["campaign_date"],
            self.fixture["current_actual_state"]["campaign_date"],
        )

    def test_all_fifteen_exact_aquaculture_species_survive(self) -> None:
        species = self.fixture["species"]
        self.assertEqual(len(species), 15)
        self.assertEqual({item["name"] for item in species}, EXPECTED_SPECIES)
        self.assertEqual(len({item["species_id"] for item in species}), 15)
        self.assertTrue(
            all(item["source_id"] == "aquaculture-technical" for item in species)
        )

    def test_technical_designs_are_not_promoted_to_observed_or_actual(self) -> None:
        self.assertEqual(
            self.sources["aquaculture-technical"]["authority_class"],
            "technical_design",
        )
        self.assertEqual(
            self.sources["nmwc-complete"]["authority_class"], "technical_design"
        )
        self.assertEqual(
            self.sources["water-empire"]["authority_class"], "projection"
        )
        topology = self.fixture["nmwc_topology"]
        self.assertEqual(
            topology["temporal_class"],
            "later_or_technical_not_day7_hammer1495_actual",
        )
        self.assertFalse(topology["day7_hammer1495_execution_eligible"])
        for group in self.fixture["nmwc_pond_groups"]:
            self.assertEqual(
                group["temporal_class"],
                "technical_capacity_not_day7_hammer1495_actual",
            )
        self.assertFalse(
            any(
                entity["source_id"] in {"aquaculture-technical", "nmwc-complete"}
                for entity in self.fixture["registry_entities"]
            )
        )

    def test_shelters_are_tomatoes_and_produce_not_grain_or_feed(self) -> None:
        shelters = self.fixture["confirmed_production"]["shelters"]
        self.assertEqual(
            shelters["outputs"],
            ["greenhouse produce", "tomatoes", "year-round tomatoes"],
        )
        normalized_outputs = " ".join(shelters["outputs"]).casefold()
        self.assertNotIn("grain", normalized_outputs)
        self.assertNotIn("feed", normalized_outputs)
        self.assertIsNone(shelters["baseline_physical_yield"])

    def test_broader_crop_program_keeps_named_grain_fruit_greens_and_herbs(self) -> None:
        crops = {crop["crop_id"]: crop for crop in self.fixture["crop_program"]["crops"]}
        self.assertTrue({"wheat", "barley", "rye"} <= crops.keys())
        self.assertTrue({"apple", "pear", "cherry"} <= crops.keys())
        self.assertTrue(
            {"leafy-greens", "root-vegetables", "herbs", "specialty-herbs"}
            <= crops.keys()
        )
        self.assertTrue(all(crops[crop]["class"] == "grain" for crop in ("wheat", "barley", "rye")))
        self.assertTrue(
            all(
                crops[crop]["confirmed_planted"] is False
                for crop in ("wheat", "barley", "rye")
            )
        )
        self.assertTrue(crops["tomatoes"]["confirmed_planted"])

    def test_procurement_is_a_plan_with_no_resolved_purchase(self) -> None:
        forward = self.fixture["forward_k1495_state"]
        self.assertEqual(
            forward["grain_procurement_target_tons"],
            {"low": "1200", "high": "1500"},
        )
        self.assertEqual(forward["grain_procured_tons"], "0")
        self.assertEqual(forward["execution_rolls_resolved"], 0)
        self.assertEqual(forward["transactions_resolved"], 0)

    def test_lobster_king_conflict_remains_visible_and_not_backdated(self) -> None:
        registry = next(
            entity
            for entity in self.fixture["registry_entities"]
            if entity["entity_id"] == "lobster-king"
        )
        later = self.fixture["confirmed_production"]["lobster_king_later_authority"]
        self.assertEqual(registry["status"], "Unconfirmed")
        self.assertEqual(registry["source_id"], "lobster-king-registry")
        self.assertEqual(
            self.sources[registry["source_id"]]["authority_class"], "unconfirmed"
        )
        self.assertEqual(later["status"], "Active ally")
        self.assertEqual(
            later["temporal_class"],
            "later_detailed_authority_not_backdated_to_day7_hammer1495",
        )
        self.assertEqual(
            self.sources[later["source_id"]]["authority_class"],
            "observed_operating_state",
        )

    def test_pool_count_and_temperature_conflicts_remain_visible(self) -> None:
        conflicts = {
            conflict["conflict_id"]: conflict
            for conflict in self.fixture["known_conflicts"]
        }
        self.assertIn("pond-topology", conflicts)
        self.assertRegex(conflicts["pond-topology"]["description"], r"\b7\b.*\b10\b")
        self.assertIn("network_total_without_double_counting", conflicts["pond-topology"]["blocking_for"])
        self.assertIn("pond-temperature", conflicts)
        temperature = conflicts["pond-temperature"]["description"]
        self.assertIn("70-85 F", temperature)
        self.assertIn("warm, moderate, and cool", temperature)
        self.assertIn(
            "pond_by_pond_biological_simulation",
            conflicts["pond-temperature"]["blocking_for"],
        )

    def test_unknown_nulls_are_not_collapsed_into_observed_zeroes(self) -> None:
        entities = {
            entity["entity_id"]: entity
            for entity in self.fixture["registry_entities"]
        }
        self.assertIsNone(entities["orchard-chapel"]["employees"])
        self.assertIsNone(entities["orchard-chapel"]["monthly_revenue_gp"])
        self.assertEqual(entities["lobster-king"]["employees"], 0)
        self.assertEqual(entities["lobster-king"]["monthly_revenue_gp"], "0")
        self.assertIsNone(
            self.fixture["confirmed_production"]["reservoir_fisheries"]["site_count"]
        )
        self.assertIsNone(
            self.fixture["forward_k1495_state"]["destroyed_zone_ids"]
        )
        self.assertEqual(self.fixture["forward_k1495_state"]["transactions_resolved"], 0)
        species = {item["species_id"]: item for item in self.fixture["species"]}
        self.assertIsNone(species["pearl-gourami"]["feed_conversion_ratio"])
        self.assertEqual(
            species["littleneck-clams"]["feed_conversion_ratio"],
            {"low": "0", "high": "0"},
        )

    def test_source_links_and_all_internal_source_references_are_valid(self) -> None:
        notion_url = re.compile(r"https://app\.notion\.com/p/([0-9a-f]{32})\Z")
        self.assertEqual(len(self.sources), len(self.fixture["sources"]))
        self.assertEqual(len({source["page_id"] for source in self.sources.values()}), len(self.sources))
        for source in self.sources.values():
            match = notion_url.fullmatch(source["url"])
            self.assertIsNotNone(match, source["url"])
            self.assertEqual(match.group(1), source["page_id"].replace("-", ""))

        referenced: set[str] = set()

        def collect(value: object) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    if key == "source_id" and isinstance(child, str):
                        referenced.add(child)
                    elif key == "source_ids" and isinstance(child, list):
                        referenced.update(item for item in child if isinstance(item, str))
                    collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)

        collect(self.fixture)
        self.assertEqual(referenced - self.sources.keys(), set())

    def test_fixture_records_zero_mutations_rolls_and_time_advance(self) -> None:
        self.assertEqual(
            self.fixture["safety"],
            {
                "notion_writes": 0,
                "canonical_ledger_postings": 0,
                "dice_rolled": 0,
                "campaign_time_advanced": False,
            },
        )
        self.assertEqual(self.fixture["notion_access"], "read_only")


if __name__ == "__main__":
    unittest.main()
