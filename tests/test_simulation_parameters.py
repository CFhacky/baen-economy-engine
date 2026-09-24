from __future__ import annotations

import unittest

from baen_economy.simulation_parameters import resolve_catalog, resolve_parameter


class SimulationParameterTests(unittest.TestCase):
    def test_catalog_resolves_all_parameters_and_preserves_debt(self):
        result = resolve_catalog(seed="parameter-catalog-a")
        self.assertEqual(result["parameter_count"], 34)
        self.assertEqual(result["needs_enumeration_count"], 34)
        self.assertEqual(
            len(set(row["id"] for row in result["parameters"])),
            34,
        )

    def test_same_seed_is_reproducible_and_other_seed_changes_draws(self):
        first = resolve_catalog(seed="same")
        second = resolve_catalog(seed="same")
        other = resolve_catalog(seed="other")
        self.assertEqual(first, second)
        self.assertNotEqual(
            [row["value"] for row in first["parameters"]],
            [row["value"] for row in other["parameters"]],
        )

    def test_forgedeep_population_rejects_old_8000_synthetic_value(self):
        row = resolve_parameter("settlement.forgedeep.population", seed="forgedeep")
        self.assertGreaterEqual(row.value, 700)
        self.assertLessEqual(row.value, 1600)
        self.assertNotEqual(row.value, 8000)
        self.assertTrue(row.needs_enumeration)

    def test_warborn_allocation_runs_both_competing_claims(self):
        seen = {
            resolve_parameter(
                "production.warborn_aluminum_allocation_tons_per_month",
                seed=f"claim-{index}",
            ).value
            for index in range(100)
        }
        self.assertEqual(seen, {30, 36})

    def test_silversheen_cost_is_a_range_not_old_cost_copy(self):
        values = [
            resolve_parameter(
                "production.silversheen_current_monthly_cost_gp",
                seed=f"silversheen-{index}",
            ).value
            for index in range(20)
        ]
        self.assertTrue(all(33100 <= value <= 34500 for value in values))
        self.assertNotIn(29040, values)


if __name__ == "__main__":
    unittest.main()
