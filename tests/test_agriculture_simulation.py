from decimal import Decimal, getcontext, setcontext
from pathlib import Path
import json
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from baen_economy.agriculture_simulation import (  # noqa: E402
    PLANNING_ONLY,
    AgriculturePlan,
    AgriculturePlanningError,
    OpeningInventory,
    PeriodFlowAssumption,
    PlanningPeriod,
    StockKey,
    simulate_agriculture,
)


D = Decimal
ZERO = D("0")


def flow(
    key,
    *,
    production="0",
    inbound="0",
    consumption="0",
    outbound="0",
    processing_use="0",
    capacity="1000",
    loss_rate="0",
    absolute_loss=None,
):
    return PeriodFlowAssumption(
        key=key,
        production=None if production is None else D(production),
        inbound=None if inbound is None else D(inbound),
        consumption=None if consumption is None else D(consumption),
        outbound=None if outbound is None else D(outbound),
        processing_use=None if processing_use is None else D(processing_use),
        capacity=None if capacity is None else D(capacity),
        loss_rate=None if loss_rate is None else D(loss_rate),
        absolute_loss=None if absolute_loss is None else D(absolute_loss),
    )


def plan_for(openings, periods):
    return AgriculturePlan(
        scenario_id="user-plan:food-01",
        scenario_name="Explicit food assumptions",
        assumption_source="user:planning-workbench",
        openings=tuple(openings),
        periods=tuple(periods),
    )


class AgricultureSimulationTests(unittest.TestCase):
    def test_three_periods_carry_closing_stock_and_conserve_every_row(self):
        grain = StockKey("longsaddle", "grain", "ton")
        plan = plan_for(
            [OpeningInventory(grain, D("100"))],
            [
                PlanningPeriod(1, "Planning period 1", (
                    flow(grain, production="50", consumption="80"),
                )),
                PlanningPeriod(2, "Planning period 2", (
                    flow(grain, production="10", inbound="20", consumption="50"),
                )),
                PlanningPeriod(3, "Planning period 3", (
                    flow(
                        grain,
                        production="40",
                        consumption="25",
                        processing_use="5",
                        outbound="10",
                    ),
                )),
            ],
        )

        result = simulate_agriculture(plan)

        self.assertEqual(
            [row.opening_inventory for row in result.rows],
            [D("100"), D("70"), D("50")],
        )
        self.assertEqual(
            [row.closing_inventory for row in result.rows],
            [D("70"), D("50"), D("50")],
        )
        self.assertTrue(result.all_rows_conserved)
        self.assertTrue(all(row.conservation_residual == ZERO for row in result.rows))

    def test_capacity_overflow_is_explicit_and_conserved(self):
        apples = StockKey("orchard-chapel", "apples", "ton")
        result = simulate_agriculture(plan_for(
            [OpeningInventory(apples, D("100"))],
            [PlanningPeriod(1, "Harvest", (
                flow(apples, production="100", capacity="50"),
            ))],
        ))

        row = result.rows[0]
        self.assertEqual(row.gross_available, D("200"))
        self.assertEqual(row.capacity_overflow, D("150"))
        self.assertEqual(row.closing_inventory, D("50"))
        self.assertTrue(row.conserved)

    def test_shortage_reports_unmet_aggregate_demand_without_invented_priority(self):
        fish = StockKey("blacklake", "rainbow-trout", "lb")
        result = simulate_agriculture(plan_for(
            [OpeningInventory(fish, D("10"))],
            [PlanningPeriod(1, "Demand stress", (
                flow(
                    fish,
                    consumption="15",
                    processing_use="3",
                    outbound="2",
                ),
            ))],
        ))

        row = result.rows[0]
        self.assertEqual(row.total_requested_demand, D("20"))
        self.assertEqual(row.fulfilled_demand, D("10"))
        self.assertEqual(row.unmet_demand, D("10"))
        self.assertEqual(row.shortage, D("10"))
        self.assertEqual(row.closing_inventory, ZERO)
        self.assertTrue(row.conserved)

    def test_rate_and_absolute_loss_are_supported(self):
        prawns = StockKey("water-empire", "freshwater-prawns", "lb")
        rate_result = simulate_agriculture(plan_for(
            [OpeningInventory(prawns, D("100"))],
            [PlanningPeriod(1, "Rate loss", (
                flow(prawns, production="50", loss_rate="0.10"),
            ))],
        ))
        self.assertEqual(rate_result.rows[0].loss, D("15.00"))
        self.assertEqual(rate_result.rows[0].closing_inventory, D("135.00"))

        absolute_result = simulate_agriculture(plan_for(
            [OpeningInventory(prawns, D("100"))],
            [PlanningPeriod(1, "Absolute loss", (
                flow(prawns, loss_rate=None, absolute_loss="7.5"),
            ))],
        ))
        self.assertEqual(absolute_result.rows[0].loss, D("7.5"))
        self.assertEqual(absolute_result.rows[0].closing_inventory, D("92.5"))

    def test_rate_loss_compounds_exactly_across_periods(self):
        mussels = StockKey("blacklake", "freshwater-mussels", "lb")
        plan = plan_for(
            [OpeningInventory(mussels, D("1"))],
            [
                PlanningPeriod(index, f"P{index}", (
                    flow(mussels, loss_rate="0.1"),
                ))
                for index in range(1, 4)
            ],
        )

        result = simulate_agriculture(plan)
        self.assertEqual(
            [row.closing_inventory for row in result.rows],
            [D("0.9"), D("0.81"), D("0.729")],
        )
        self.assertTrue(result.all_rows_conserved)

    def test_missing_is_rejected_while_explicit_zero_is_valid(self):
        grain = StockKey("longsaddle", "grain", "ton")
        with self.assertRaisesRegex(AgriculturePlanningError, "missing is not zero"):
            OpeningInventory(grain, None)
        with self.assertRaisesRegex(AgriculturePlanningError, "missing is not zero"):
            flow(grain, production=None)
        with self.assertRaisesRegex(AgriculturePlanningError, "missing is not zero"):
            flow(grain, capacity=None)

        explicit_zero = simulate_agriculture(plan_for(
            [OpeningInventory(grain, ZERO)],
            [PlanningPeriod(1, "Explicit zeros", (flow(grain, capacity="0"),))],
        ))
        self.assertEqual(explicit_zero.rows[0].closing_inventory, ZERO)
        self.assertEqual(explicit_zero.rows[0].unmet_demand, ZERO)

    def test_negative_and_contradictory_loss_assumptions_fail_closed(self):
        grain = StockKey("longsaddle", "grain", "ton")
        with self.assertRaisesRegex(AgriculturePlanningError, "cannot be negative"):
            flow(grain, production="-1")
        with self.assertRaisesRegex(AgriculturePlanningError, "exactly one"):
            flow(grain, loss_rate=None, absolute_loss=None)
        with self.assertRaisesRegex(AgriculturePlanningError, "exactly one"):
            flow(grain, loss_rate="0", absolute_loss="0")
        with self.assertRaisesRegex(AgriculturePlanningError, "loss rate must be"):
            flow(grain, loss_rate="1.01")

        invalid_runtime_plan = plan_for(
            [OpeningInventory(grain, D("5"))],
            [PlanningPeriod(1, "Impossible absolute loss", (
                flow(grain, loss_rate=None, absolute_loss="6"),
            ))],
        )
        with self.assertRaisesRegex(AgriculturePlanningError, "exceeds gross available"):
            simulate_agriculture(invalid_runtime_plan)

    def test_every_opened_stream_requires_an_explicit_row_every_period(self):
        grain = StockKey("longsaddle", "grain", "ton")
        fish = StockKey("blacklake", "rainbow-trout", "lb")
        with self.assertRaisesRegex(AgriculturePlanningError, "missing blacklake"):
            plan_for(
                [OpeningInventory(grain, D("0")), OpeningInventory(fish, D("0"))],
                [PlanningPeriod(1, "Incomplete", (flow(grain),))],
            )

    def test_hash_and_serialization_are_deterministic_under_input_ordering(self):
        grain = StockKey("longsaddle", "grain", "ton")
        fish = StockKey("blacklake", "rainbow-trout", "lb")
        opening_items = [OpeningInventory(grain, D("20")), OpeningInventory(fish, D("30"))]
        period_rows = {
            1: [flow(grain, consumption="2"), flow(fish, consumption="3")],
            2: [flow(grain, production="4"), flow(fish, production="5")],
            3: [flow(grain, inbound="6"), flow(fish, inbound="7")],
        }

        canonical_outputs = set()
        scenario_hashes = set()
        result_hashes = set()
        for opening_order in (opening_items, list(reversed(opening_items))):
            period_objects = [
                PlanningPeriod(index, f"P{index}", tuple(rows))
                for index, rows in period_rows.items()
            ]
            for period_order in (period_objects, list(reversed(period_objects))):
                rows_reversed = [
                    PlanningPeriod(
                        period.period_index,
                        period.period_label,
                        tuple(reversed(period.flows)),
                    )
                    for period in period_order
                ]
                plan = plan_for(opening_order, rows_reversed)
                result = simulate_agriculture(plan)
                canonical_outputs.add(result.to_json())
                scenario_hashes.add(result.scenario_hash)
                result_hashes.add(result.result_hash)

        self.assertEqual(len(canonical_outputs), 1)
        self.assertEqual(len(scenario_hashes), 1)
        self.assertEqual(len(result_hashes), 1)
        payload = json.loads(next(iter(canonical_outputs)))
        self.assertEqual(payload["scenario_hash"], next(iter(scenario_hashes)))
        self.assertEqual(payload["result_hash"], next(iter(result_hashes)))
        self.assertTrue(all(row["conservation"]["passed"] for row in payload["rows"]))

    def test_decimal_results_ignore_callers_ambient_context(self):
        grain = StockKey("longsaddle", "grain", "ton")
        plan = plan_for(
            [OpeningInventory(grain, D("123456789.123456789"))],
            [PlanningPeriod(1, "Exact", (
                flow(grain, production="0.000000001", loss_rate="0.123456789"),
            ))],
        )
        original = getcontext().copy()
        try:
            low = original.copy()
            low.prec = 6
            setcontext(low)
            first = simulate_agriculture(plan).to_json()
            high = original.copy()
            high.prec = 70
            setcontext(high)
            second = simulate_agriculture(plan).to_json()
        finally:
            setcontext(original)
        self.assertEqual(first, second)

    def test_result_is_explicitly_planning_only(self):
        grain = StockKey("longsaddle", "grain", "ton")
        plan = plan_for(
            [OpeningInventory(grain, D("1"))],
            [PlanningPeriod(1, "P1", (flow(grain),))],
        )
        before = plan.to_json()
        payload = simulate_agriculture(plan).to_dict()

        self.assertTrue(PLANNING_ONLY)
        self.assertTrue(payload["planning_only"])
        self.assertFalse(payload["campaign_time_advanced"])
        self.assertFalse(payload["financial_postings_created"])
        self.assertEqual(plan.to_json(), before)


if __name__ == "__main__":
    unittest.main()
