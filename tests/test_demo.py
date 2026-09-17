import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from baen_economy.demo import run_synthetic_normal_month  # noqa: E402


class DemoTests(unittest.TestCase):
    def test_synthetic_normal_month_is_conserved_and_deterministic(self):
        first = run_synthetic_normal_month()
        second = run_synthetic_normal_month()
        self.assertEqual(first, second)
        self.assertFalse(first["canonical"])
        self.assertEqual(first["period_1"]["dispatched_tons"], "50")
        self.assertEqual(first["period_1"]["route_shortfall_tons"], "30")
        self.assertEqual(first["period_2"]["shortage_tons"], "10")
        self.assertEqual(first["period_1"]["conservation_residual_tons"], "0")
        self.assertEqual(first["period_2"]["conservation_residual_tons"], "0")


if __name__ == "__main__":
    unittest.main()
