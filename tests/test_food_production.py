from __future__ import annotations

import hashlib
from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from baen_economy.food_production import (  # noqa: E402
    AQUACULTURE_PLAN_SCHEMA,
    CROP_PLAN_SCHEMA,
    DEFAULT_CANON_PATH,
    FOOD_PRODUCTION_CATALOG_SCHEMA,
    FoodProductionError,
    food_production_catalog,
    preview_aquaculture_plan,
    preview_crop_plan,
)
from baen_economy.operator_codec import canonical_hash  # noqa: E402


HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def aquaculture_request(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "scenario_id": "tilapia-known-answer",
        "species_id": "tilapia",
        "capacity": "30000",
        "capacity_basis": "cubic_meters",
        "planned_liveweight_output_lb": "25000",
        "opening_feed_lb": "50000",
        "feed_receipts_lb": "5000",
    }
    payload.update(changes)
    return payload


def crop_request(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "scenario_id": "wheat-known-answer",
        "crop_id": "wheat",
        "baseline_yield_tons": "100",
        "baseline_fertilizer_tons": "80",
        "opening_food_tons": "20",
        "food_receipts_tons": "5",
        "planned_consumption_tons": "60",
    }
    payload.update(changes)
    return payload


class FoodProductionCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = food_production_catalog()

    def test_catalog_exposes_every_named_species_and_crop(self) -> None:
        self.assertEqual(self.catalog["schema"], FOOD_PRODUCTION_CATALOG_SCHEMA)
        species = self.catalog["species"]
        crops = self.catalog["crops"]
        self.assertEqual(len(species), 15)
        self.assertEqual(len(crops), 12)
        self.assertEqual(
            {item["species_id"] for item in species},
            {
                "tiger-shrimp",
                "tilapia",
                "freshwater-prawns",
                "pearl-gourami",
                "red-claw-crayfish",
                "littleneck-clams",
                "largemouth-bass",
                "blue-crabs",
                "yellow-perch",
                "freshwater-mussels",
                "rainbow-trout",
                "arctic-char",
                "european-lobster",
                "northern-pike",
                "signal-crayfish",
            },
        )
        self.assertEqual(
            {item["crop_id"] for item in crops},
            {
                "wheat",
                "barley",
                "rye",
                "apple",
                "pear",
                "cherry",
                "leafy-greens",
                "root-vegetables",
                "herbs",
                "specialty-herbs",
                "wine-grapes",
                "tomatoes",
            },
        )
        tilapia = next(item for item in species if item["species_id"] == "tilapia")
        self.assertEqual(tilapia["scientific_name"], "Oreochromis niloticus")
        self.assertEqual(
            tilapia["annual_yield_lb_per_1000_unit"],
            {
                "low": "10000",
                "high": "12000",
                "basis": "cubic_meters",
            },
        )
        tomatoes = next(item for item in crops if item["crop_id"] == "tomatoes")
        self.assertTrue(tomatoes["confirmed_planted"])
        self.assertIsNone(tomatoes["yield_increase"])
        self.assertFalse(tomatoes["actual_execution_eligible"])

    def test_catalog_keeps_physical_state_unknown_and_hash_bound(self) -> None:
        unknowns = self.catalog["unknown_current_physical_inputs"]
        self.assertIn("Opening inventories by site and commodity", unknowns)
        self.assertIn("Aquaculture species allocation within each pond or site", unknowns)
        self.assertIn("Population ration requirements by food class", unknowns)
        boundary = self.catalog["current_actual_boundary"]
        self.assertTrue(boundary["live_freeze"])
        self.assertFalse(boundary["agriculture_month_close_authorized"])
        self.assertFalse(boundary["physical_execution_ready"])
        expected_file_hash = hashlib.sha256(DEFAULT_CANON_PATH.read_bytes()).hexdigest()
        self.assertEqual(
            self.catalog["source_binding"]["fixture_sha256"],
            expected_file_hash,
        )
        body = dict(self.catalog)
        content_hash = body.pop("content_hash")
        self.assertRegex(content_hash, HASH_RE)
        self.assertEqual(content_hash, canonical_hash(body))


class AquacultureProductionPlanTests(unittest.TestCase):
    def test_tilapia_known_answer_yield_feed_and_conservation(self) -> None:
        result = preview_aquaculture_plan(aquaculture_request())
        self.assertEqual(result["schema"], AQUACULTURE_PLAN_SCHEMA)
        derived = result["derived"]
        self.assertEqual(
            derived["annual_yield_lb"],
            {
                "low": "300000",
                "high": "360000",
                "unit": "lb",
                "basis": "annual_technical_preview",
            },
        )
        self.assertEqual(
            derived["monthly_average_yield_lb"]["low"], "25000"
        )
        self.assertEqual(
            derived["monthly_average_yield_lb"]["high"], "30000"
        )
        self.assertEqual(derived["feed_required_lb"]["low"], "42500.0")
        self.assertEqual(derived["feed_available_lb"], "55000")
        self.assertEqual(derived["closing_feed_lb"]["low"], "12500.0")
        self.assertEqual(derived["feed_shortfall_lb"]["high"], "0.0")
        self.assertEqual(
            derived["conservation_residual_lb"],
            {"low": "0.0", "high": "0.0"},
        )
        self.assertEqual(derived["status"], "sufficient_for_full_range")
        self.assertEqual(
            set(result["decision_brief"]),
            {"Source", "Assumption", "Derived", "Unknown"},
        )
        self.assertIn(
            "current_biomass_mortality_and_harvest_schedule",
            result["decision_brief"]["Unknown"],
        )

    def test_source_null_parameters_require_explicit_labeled_assumptions(self) -> None:
        request = aquaculture_request(
            scenario_id="pearl-gourami-assumption",
            species_id="pearl-gourami",
            capacity="1000",
            planned_liveweight_output_lb="400",
            opening_feed_lb="1000",
            feed_receipts_lb="0",
            assumed_annual_yield_lb_per_1000_unit={
                "low": "4000",
                "high": "5000",
                "basis": "cubic_meters",
            },
            assumed_feed_conversion_ratio={"low": "1.8", "high": "2.0"},
        )
        result = preview_aquaculture_plan(request)
        parameters = result["effective_technical_parameters"]
        self.assertEqual(
            parameters["annual_yield_lb_per_1000_unit"]["origin"], "Assumption"
        )
        self.assertEqual(parameters["feed_conversion_ratio"]["origin"], "Assumption")
        self.assertEqual(result["derived"]["feed_required_lb"]["low"], "720.0")
        self.assertEqual(result["derived"]["feed_required_lb"]["high"], "800.0")
        self.assertEqual(result["derived"]["closing_feed_lb"]["low"], "200.0")
        self.assertEqual(result["derived"]["closing_feed_lb"]["high"], "280.0")

    def test_missing_override_float_extra_field_and_basis_mismatch_fail_closed(self) -> None:
        with self.assertRaisesRegex(FoodProductionError, "absent from source"):
            preview_aquaculture_plan(
                aquaculture_request(species_id="pearl-gourami")
            )
        with self.assertRaisesRegex(FoodProductionError, "exact decimal text"):
            preview_aquaculture_plan(aquaculture_request(capacity=30000.0))
        with self.assertRaisesRegex(FoodProductionError, r"extra=\['site_id'\]"):
            preview_aquaculture_plan(aquaculture_request(site_id="invented"))
        with self.assertRaisesRegex(FoodProductionError, "does not match"):
            preview_aquaculture_plan(
                aquaculture_request(capacity_basis="square_meters")
            )
        with self.assertRaisesRegex(FoodProductionError, "cannot be overridden"):
            preview_aquaculture_plan(
                aquaculture_request(
                    assumed_feed_conversion_ratio={"low": "1", "high": "1"}
                )
            )


class CropProductionPlanTests(unittest.TestCase):
    def test_wheat_known_answer_output_fertilizer_food_and_conservation(self) -> None:
        result = preview_crop_plan(crop_request())
        self.assertEqual(result["schema"], CROP_PLAN_SCHEMA)
        derived = result["derived"]
        self.assertEqual(derived["enhanced_yield_tons"]["low"], "130.00")
        self.assertEqual(derived["enhanced_yield_tons"]["high"], "135.00")
        self.assertEqual(derived["fertilizer_required_tons"]["low"], "32.00")
        self.assertEqual(derived["fertilizer_required_tons"]["high"], "48.00")
        self.assertEqual(derived["gross_food_available_tons"]["low"], "155.00")
        self.assertEqual(derived["gross_food_available_tons"]["high"], "160.00")
        self.assertEqual(derived["closing_food_tons"]["low"], "95.00")
        self.assertEqual(derived["closing_food_tons"]["high"], "100.00")
        self.assertEqual(derived["food_shortfall_tons"]["high"], "0")
        self.assertEqual(
            derived["conservation_residual_tons"],
            {"low": "0.00", "high": "0.00"},
        )
        self.assertEqual(derived["food_status"], "sufficient_across_range")
        self.assertIn(
            "current_site_and_acreage_allocation",
            result["decision_brief"]["Unknown"],
        )

    def test_source_null_crop_uplift_requires_explicit_assumption(self) -> None:
        with self.assertRaisesRegex(FoodProductionError, "absent from source"):
            preview_crop_plan(crop_request(crop_id="tomatoes"))
        result = preview_crop_plan(
            crop_request(
                scenario_id="tomato-assumption",
                crop_id="tomatoes",
                assumed_yield_increase={"low": "0.10", "high": "0.20"},
            )
        )
        self.assertTrue(result["selection"]["confirmed_planted"])
        self.assertFalse(result["selection"]["actual_execution_eligible"])
        self.assertEqual(
            result["effective_technical_parameters"]["yield_increase"]["origin"],
            "Assumption",
        )
        self.assertEqual(result["derived"]["enhanced_yield_tons"]["low"], "110.00")
        self.assertEqual(result["derived"]["enhanced_yield_tons"]["high"], "120.00")

    def test_source_crop_uplift_cannot_be_silently_overridden(self) -> None:
        with self.assertRaisesRegex(FoodProductionError, "cannot be overridden"):
            preview_crop_plan(
                crop_request(
                    assumed_yield_increase={"low": "9", "high": "10"}
                )
            )


class FoodProductionSafetyTests(unittest.TestCase):
    def test_every_surface_is_non_mutating_and_hash_addressed(self) -> None:
        payloads = (
            food_production_catalog(),
            preview_aquaculture_plan(aquaculture_request()),
            preview_crop_plan(crop_request()),
        )
        for payload in payloads:
            safety = payload["safety"]
            self.assertTrue(safety["planning_only"])
            self.assertFalse(safety["canonical"])
            self.assertTrue(safety["read_only"])
            self.assertFalse(safety["actual_execution_eligible"])
            self.assertEqual(safety["notion_writes"], 0)
            self.assertEqual(safety["canonical_ledger_postings"], 0)
            self.assertEqual(safety["dice_rolled"], 0)
            self.assertFalse(safety["campaign_time_advanced"])
            body = dict(payload)
            content_hash = body.pop("content_hash")
            self.assertRegex(content_hash, HASH_RE)
            self.assertEqual(content_hash, canonical_hash(body))
        for payload in payloads[1:]:
            self.assertRegex(payload["hashes"]["input_sha256"], HASH_RE)
            self.assertRegex(payload["hashes"]["source_fixture_sha256"], HASH_RE)
            self.assertRegex(
                payload["hashes"]["source_canon_content_hash"], HASH_RE
            )


if __name__ == "__main__":
    unittest.main()
