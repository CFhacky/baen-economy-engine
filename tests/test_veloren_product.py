from __future__ import annotations

import os
import tempfile
import unittest

from baen_economy.veloren_product import (
    VELOREN_COMMIT,
    VELOREN_PATCH_VERSION,
    VelorenProductError,
    run_veloren_economy,
)


class VelorenProductTests(unittest.TestCase):
    def test_exact_upstream_and_patch_pin(self):
        self.assertEqual(VELOREN_COMMIT, "e633eb8ca15ae97bb5ef5a039fcf6844e96ad704")
        self.assertEqual(VELOREN_PATCH_VERSION, 1)

    def test_unverified_directory_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(VelorenProductError):
                run_veloren_economy(
                    temp, population=32, food_stock=100, coin_stock=1000, days=30
                )

    def test_invalid_negative_scenario_state_rejected(self):
        with self.assertRaises(ValueError):
            run_veloren_economy(
                ".", population=-1, food_stock=10, coin_stock=10, days=30
            )

    @unittest.skipUnless(
        os.environ.get("VELOREN_CHECKOUT"),
        "actual pinned/patched Veloren checkout is exercised in dedicated CI product job",
    )
    def test_actual_veloren_economy_tick_executes(self):
        result = run_veloren_economy(
            os.environ["VELOREN_CHECKOUT"],
            population=64,
            food_stock=500,
            coin_stock=1000,
            days=30,
            timeout=60,
        )
        self.assertEqual(result.upstream, "Veloren")
        self.assertEqual(result.upstream_commit, VELOREN_COMMIT)
        self.assertEqual(result.patch_version, VELOREN_PATCH_VERSION)
        self.assertGreaterEqual(result.population, 0)
        self.assertGreaterEqual(result.food_stock, 0)
        self.assertGreaterEqual(result.coin_stock, 0)
        self.assertGreater(result.food_price, 0)
        self.assertEqual(result.simulated_days, 30)
        self.assertFalse(result.canonical_time_advanced)


if __name__ == "__main__":
    unittest.main()
