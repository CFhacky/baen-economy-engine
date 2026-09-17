from __future__ import annotations

from decimal import localcontext
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from baen_economy.regional_cli import MonthRequest, ScenarioRequest  # noqa: E402
from baen_economy.regional_engine import build_adapters  # noqa: E402


class RegionalEngineIntegrationTests(unittest.TestCase):
    def run_direct_month(self, precision: int) -> dict[str, object]:
        with localcontext() as context:
            context.prec = precision
            adapters = build_adapters()
            initialized = adapters.scenario.initialize(
                ScenarioRequest(
                    scenario_id="baen-regional-mvp",
                    scenario_path=None,
                    registry_path=None,
                    seed_fingerprint="a" * 64,
                )
            )
            request = MonthRequest(
                scenario=initialized["scenario"],
                opening_state=initialized["state"],
                period=1,
                seed_fingerprint="a" * 64,
            )
            production = adapters.production.simulate(request)
            market = adapters.market_transport.simulate(request, production)
            finance = adapters.finance.simulate(request, production, market)
            result = {
                "initialized": initialized,
                "production": production,
                "market": market,
                "finance": finance,
            }
            json.dumps(result, sort_keys=True, allow_nan=False)
            return result

    def test_complete_adapter_result_ignores_callers_decimal_context(self):
        low_precision = self.run_direct_month(4)
        high_precision = self.run_direct_month(80)
        self.assertEqual(low_precision, high_precision)
        self.assertEqual(
            low_precision["market"]["state"]["regional_state"]["state_hash"],
            high_precision["market"]["state"]["regional_state"]["state_hash"],
        )
        self.assertEqual(
            low_precision["market"]["state"]["market_snapshot"]["state_hash"],
            high_precision["market"]["state"]["market_snapshot"]["state_hash"],
        )

        losses = low_precision["market"]["market"]["storage_loss_receipts"]
        self.assertTrue(losses)
        self.assertEqual(
            {item["commodity_id"] for item in losses},
            {"commodity:grain", "commodity:fish"},
        )
        self.assertTrue(all(item["storage_loss_quantity"] != "0" for item in losses))
        self.assertTrue(all(item["residual_quantity"] == "0" for item in losses))

        blacklake = next(
            item
            for item in low_precision["market"]["market"]["demand_receipts"]
            if item["demand_id"] == "demand:blacklake-grain"
        )
        self.assertEqual(blacklake["price_before_gp_per_unit"], "12")
        self.assertEqual(blacklake["price_after_gp_per_unit"], "18.0000")


if __name__ == "__main__":
    unittest.main()
