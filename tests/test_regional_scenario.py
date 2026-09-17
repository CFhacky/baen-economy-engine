from copy import deepcopy
from dataclasses import FrozenInstanceError
from decimal import Decimal
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from baen_economy.operator_codec import canonical_hash  # noqa: E402
from baen_economy.regional_domain import (  # noqa: E402
    ProductionOrder,
    regional_state_from_dict,
)
from baen_economy.regional_production import advance_production_month  # noqa: E402
from baen_economy.regional_scenario import (  # noqa: E402
    REGIONAL_PROFILE_ID,
    REGIONAL_SCENARIO_ID,
    RegionalScenarioError,
    load_regional_scenario,
)


SCENARIO = ROOT / "fixtures" / "regional-scenarios" / "baen-north-preview-v1.json"
REGISTRY = (
    ROOT
    / "fixtures"
    / "registry-snapshots"
    / "business-registry-2026-08-29.json"
)


class RegionalScenarioTests(unittest.TestCase):
    def load(self):
        return load_regional_scenario(SCENARIO, REGISTRY)

    def test_loads_source_bound_interconnected_opening_slice(self):
        scenario = self.load()

        self.assertEqual(scenario.scenario_id, REGIONAL_SCENARIO_ID)
        self.assertEqual(scenario.assumption_profile_id, REGIONAL_PROFILE_ID)
        self.assertFalse(scenario.canonical)
        self.assertEqual(scenario.timeline.month_index, 0)
        self.assertTrue(scenario.timeline.timeline_id.startswith("preview:"))
        self.assertEqual(len(scenario.businesses), 8)
        self.assertEqual(
            {item.sector for item in scenario.businesses},
            {
                "Mining/Quarrying",
                "Manufacturing",
                "Agriculture",
                "Aquaculture",
                "Infrastructure",
                "Construction",
                "Trade",
                "Banking",
            },
        )
        brickworks = scenario.business("entity:baen-brickworks")
        self.assertEqual(brickworks.name, "Baen Brickworks")
        self.assertEqual(brickworks.monthly_revenue_gp, Decimal("3333"))
        self.assertEqual(brickworks.monthly_cost_gp, Decimal("2233"))
        self.assertEqual(brickworks.employees, 30)
        self.assertEqual(
            sum(item.monthly_revenue_gp for item in scenario.businesses),
            Decimal("53916"),
        )
        self.assertEqual(
            sum(item.monthly_cost_gp for item in scenario.businesses),
            Decimal("42051"),
        )
        self.assertEqual(sum(item.employees for item in scenario.businesses), 380)
        self.assertEqual(len(scenario.commodities), 5)
        self.assertEqual(len(scenario.inventories), 11)
        self.assertEqual(len(scenario.recipes), 5)
        self.assertEqual(len(scenario.routes), 6)
        self.assertEqual(len(scenario.demands), 5)

    def test_business_facts_are_derived_not_restated_by_scenario_fixture(self):
        raw = json.loads(SCENARIO.read_text(encoding="utf-8"))
        for selected in raw["selected_source_records"]:
            self.assertEqual(set(selected), {"source_record_id", "row_hash"})
            self.assertNotIn("Entity", selected)
            self.assertNotIn("name", selected)
            self.assertNotIn("monthly_revenue_gp", selected)
            self.assertNotIn("monthly_cost_gp", selected)
            self.assertNotIn("employees", selected)

        scenario = self.load()
        bank = scenario.business("entity:northern-crown-financial-neverwinter")
        self.assertEqual(bank.name, "Northern Crown Financial - Neverwinter")
        self.assertEqual(bank.sector, "Banking")
        self.assertEqual(bank.monthly_revenue_gp, Decimal("10000"))
        self.assertEqual(bank.monthly_cost_gp, Decimal("5200"))
        self.assertEqual(bank.employees, 35)
        banking_pool = next(
            item for item in scenario.labor_pools if item.owner_id == bank.entity_id
        )
        self.assertEqual(banking_pool.workers, bank.employees)
        self.assertEqual(banking_pool.available_worker_days, Decimal("700"))

    def test_every_runnable_input_is_explicitly_noncanonical(self):
        raw = json.loads(SCENARIO.read_text(encoding="utf-8"))
        assumptions = raw["assumptions"]
        self.assertEqual(assumptions["authority"], "scenario_input")
        self.assertIs(assumptions["canonical"], False)
        for category in (
            "business_roles",
            "commodities",
            "sites",
            "inventories",
            "labor_pools",
            "recipes",
            "routes",
            "demands",
            "opening_prices",
            "opening_positions",
        ):
            self.assertTrue(assumptions[category])
            for item in assumptions[category]:
                self.assertEqual(item["authority"], "scenario_input")
                self.assertIs(item["canonical"], False)
                self.assertTrue(item["basis"].strip())
        self.assertEqual(
            raw["permissions"],
            {
                "notion_write": False,
                "ledger_post": False,
                "campaign_advance": False,
                "canonical_state_update": False,
            },
        )
        self.assertFalse(any(scenario_id.startswith("treasury:") for scenario_id in (
            item.entity_id for item in self.load().opening_positions
        )))

    def test_opening_state_and_recipes_execute_a_real_conserved_production_month(self):
        scenario = self.load()
        opening = scenario.opening_state()
        reopened = regional_state_from_dict(opening.to_dict())
        self.assertEqual(opening, reopened)
        self.assertEqual(opening.state_hash, reopened.state_hash)
        self.assertEqual(opening.month_index, 0)
        self.assertEqual(len(opening.commodities), 5)
        self.assertEqual(len(opening.inventories), 11)
        self.assertEqual(len(opening.labor_pools), 8)

        recipes = scenario.production_recipes()
        orders = tuple(
            ProductionOrder(item.recipe_id, item.max_batches_per_month)
            for item in recipes
        )
        result = advance_production_month(opening, recipes, orders)
        self.assertEqual(result.opening_month_index, 0)
        self.assertEqual(result.closing_month_index, 1)
        self.assertEqual(result.input_consumed, Decimal("20830"))
        self.assertEqual(result.output_produced, Decimal("31840"))
        self.assertEqual(result.worker_days, Decimal("1290"))
        self.assertEqual(result.payroll, Decimal("553.50"))
        actual = {item.recipe_id: item.actual_batches for item in result.production}
        self.assertEqual(
            actual,
            {
                "recipe:complete-construction-work": Decimal("20"),
                "recipe:extract-clay": Decimal("15"),
                "recipe:fire-bricks": Decimal("40"),
                "recipe:produce-grain": Decimal("10"),
                "recipe:raise-fish": Decimal("15"),
            },
        )
        self.assertNotEqual(result.opening_state_hash, result.closing_state_hash)

    def test_normalized_payload_is_complete_json_safe_and_stable(self):
        scenario = self.load()
        payload = scenario.to_dict()
        expected_sections = {
            "businesses",
            "business_roles",
            "commodities",
            "sites",
            "inventories",
            "labor_pools",
            "recipes",
            "routes",
            "demands",
            "opening_prices",
            "opening_positions",
            "permissions",
        }
        self.assertTrue(expected_sections.issubset(payload))
        json.dumps(payload, allow_nan=False)
        supplied_hash = payload.pop("normalized_hash")
        self.assertEqual(supplied_hash, canonical_hash(payload))
        self.assertEqual(supplied_hash, scenario.to_dict()["normalized_hash"])
        self.assertEqual(
            payload["businesses"][1]["source_monthly_revenue_gp"], "3333"
        )
        self.assertEqual(
            payload["businesses"][1]["financial_semantics"],
            "source_benchmark_not_opening_cash_or_automatic_transaction",
        )

    def test_registry_and_selected_row_hash_drift_fail_closed(self):
        raw = json.loads(SCENARIO.read_text(encoding="utf-8"))

        wrong_binding = deepcopy(raw)
        wrong_binding["registry_binding"]["content_hash"] = "0" * 64
        path = self.write_rehashed(wrong_binding)
        try:
            with self.assertRaisesRegex(RegionalScenarioError, "content hash has drifted"):
                load_regional_scenario(path, REGISTRY)
        finally:
            path.unlink()

        wrong_row = deepcopy(raw)
        wrong_row["selected_source_records"][0]["row_hash"] = "0" * 64
        path = self.write_rehashed(wrong_row)
        try:
            with self.assertRaisesRegex(RegionalScenarioError, "row .* has drifted"):
                load_regional_scenario(path, REGISTRY)
        finally:
            path.unlink()

    def test_relabelled_or_dangling_assumptions_fail_closed(self):
        raw = json.loads(SCENARIO.read_text(encoding="utf-8"))
        relabelled = deepcopy(raw)
        relabelled["assumptions"]["recipes"][0]["canonical"] = True
        path = self.write_rehashed(relabelled)
        try:
            with self.assertRaisesRegex(RegionalScenarioError, "non-canonical"):
                load_regional_scenario(path, REGISTRY)
        finally:
            path.unlink()

        dangling = deepcopy(raw)
        dangling["assumptions"]["demands"][0]["site_id"] = "site:missing"
        path = self.write_rehashed(dangling)
        try:
            with self.assertRaisesRegex(RegionalScenarioError, "unknown ID"):
                load_regional_scenario(path, REGISTRY)
        finally:
            path.unlink()

    def test_json_numeric_decimals_and_duplicate_keys_are_rejected(self):
        raw = json.loads(SCENARIO.read_text(encoding="utf-8"))
        numeric = deepcopy(raw)
        numeric["assumptions"]["inventories"][0]["quantity"] = 1.5
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "numeric.json"
            path.write_text(json.dumps(numeric), encoding="utf-8")
            with self.assertRaisesRegex(RegionalScenarioError, "use exact text"):
                load_regional_scenario(path, REGISTRY)

            duplicate = Path(temporary) / "duplicate.json"
            duplicate.write_text('{"schema":"x","schema":"y"}', encoding="utf-8")
            with self.assertRaisesRegex(RegionalScenarioError, "repeats JSON key"):
                load_regional_scenario(duplicate, REGISTRY)

    def test_scenario_and_source_businesses_are_immutable(self):
        scenario = self.load()
        with self.assertRaises(FrozenInstanceError):
            scenario.timeline.month_index = 2
        with self.assertRaises(FrozenInstanceError):
            scenario.businesses[0].employees = 999
        with self.assertRaises(TypeError):
            scenario.permissions["notion_write"] = True

    def write_rehashed(self, payload):
        body = deepcopy(payload)
        body.pop("content_hash", None)
        payload = deepcopy(body)
        payload["content_hash"] = canonical_hash(body)
        temporary = TemporaryDirectory()
        # Keep the TemporaryDirectory alive through the returned Path.
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / SCENARIO.name
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path


if __name__ == "__main__":
    unittest.main()
