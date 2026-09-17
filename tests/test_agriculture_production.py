from decimal import Decimal
import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from baen_economy.agriculture_production import (  # noqa: E402
    AgriculturePlanningError,
    DragonOccupancyMode,
    MissingPlanningInput,
    aquaculture_annual_yield,
    aquaculture_feed_requirement,
    aquaculture_monthly_yield,
    aquaculture_yield_preview,
    crop_enhanced_yield,
    crop_enhancement_preview,
    crop_fertilizer_requirement,
    dragon_carcass_demand,
    procurement_coverage,
)
from baen_economy.source_values import DecimalRange  # noqa: E402


D = Decimal


class AgricultureProductionTests(unittest.TestCase):
    def test_aquaculture_yield_from_capacity_and_source_intensity(self):
        intensity = DecimalRange(
            D("10000"),
            D("12000"),
            unit="lb",
            basis="cubic_meters",
        )
        preview = aquaculture_yield_preview(
            D("30000"),
            intensity,
            capacity_basis="cubic_meters",
        )

        self.assertEqual(
            preview.annual_yield_lb,
            DecimalRange(
                D("300000"),
                D("360000"),
                unit="lb",
                basis="annual_technical_preview",
            ),
        )
        self.assertEqual(preview.monthly_average_yield_lb.low, D("25000"))
        self.assertEqual(preview.monthly_average_yield_lb.high, D("30000"))
        self.assertTrue(preview.planning_only)
        self.assertFalse(preview.actual_execution_eligible)

    def test_aquaculture_capacity_range_propagates_uncertainty(self):
        annual = aquaculture_annual_yield(
            DecimalRange(D("1000"), D("2000"), unit="square_meters"),
            DecimalRange(
                D("3500"), D("4000"), basis="square_meters"
            ),
            capacity_basis="square_meters",
        )
        self.assertEqual((annual.low, annual.high), (D("3500"), D("8000")))
        monthly = aquaculture_monthly_yield(annual)
        self.assertEqual(
            monthly.low,
            D("291.6666666666666666666666666666666666667"),
        )
        self.assertEqual(
            monthly.high,
            D("666.6666666666666666666666666666666666667"),
        )

    def test_aquaculture_rejects_basis_mismatch_and_negative_capacity(self):
        intensity = DecimalRange(
            D("1"), D("2"), basis="cubic_meters"
        )
        with self.assertRaisesRegex(AgriculturePlanningError, "does not match"):
            aquaculture_annual_yield(
                D("1000"), intensity, capacity_basis="square_meters"
            )
        with self.assertRaisesRegex(AgriculturePlanningError, "cannot be negative"):
            aquaculture_annual_yield(
                D("-1"), intensity, capacity_basis="cubic_meters"
            )

    def test_feed_range_multiplies_output_and_fcr_extremes(self):
        feed = aquaculture_feed_requirement(
            DecimalRange(D("100"), D("120"), unit="lb"),
            DecimalRange(D("1.6"), D("2")),
        )
        self.assertEqual((feed.low, feed.high), (D("160.0"), D("240")))

    def test_explicit_zero_fcr_is_not_missing_fcr(self):
        zero_feed = aquaculture_feed_requirement(
            D("100"), DecimalRange(D("0"), D("0"))
        )
        self.assertEqual((zero_feed.low, zero_feed.high), (D("0"), D("0")))
        with self.assertRaisesRegex(MissingPlanningInput, "missing is not zero"):
            aquaculture_feed_requirement(D("100"), None)

    def test_crop_enhanced_yield_requires_baseline(self):
        with self.assertRaisesRegex(MissingPlanningInput, "baseline crop yield"):
            crop_enhanced_yield(None, DecimalRange(D("0.25"), D("0.40")))
        result = crop_enhanced_yield(
            DecimalRange(D("100"), D("120"), unit="tons"),
            DecimalRange(D("0.25"), D("0.40")),
        )
        self.assertEqual((result.low, result.high), (D("125.00"), D("168.00")))
        self.assertEqual(result.unit, "tons")

    def test_fertilizer_reduction_reverses_range_endpoints(self):
        required = crop_fertilizer_requirement(
            D("100"), DecimalRange(D("0.40"), D("0.60"))
        )
        self.assertEqual((required.low, required.high), (D("40.00"), D("60.00")))
        with self.assertRaisesRegex(AgriculturePlanningError, "cannot exceed 1"):
            crop_fertilizer_requirement(
                D("100"), DecimalRange(D("0.40"), D("1.01"))
            )

    def test_combined_crop_preview_is_planning_only(self):
        preview = crop_enhancement_preview(
            baseline_yield=D("100"),
            yield_increase=DecimalRange(D("0.30"), D("0.35")),
            baseline_fertilizer=D("80"),
            fertilizer_reduction=DecimalRange(D("0.40"), D("0.60")),
        )
        self.assertEqual(
            (preview.enhanced_yield.low, preview.enhanced_yield.high),
            (D("130.00"), D("135.00")),
        )
        self.assertEqual(
            (preview.fertilizer_required.low, preview.fertilizer_required.high),
            (D("32.00"), D("48.00")),
        )
        self.assertFalse(preview.actual_execution_eligible)

    def test_dragon_profiles_preserve_sourced_daily_and_annual_values(self):
        one = dragon_carcass_demand(
            DragonOccupancyMode.ONE_WARMOTHER,
            horizon_days=D("45"),
        )
        self.assertEqual(one.profile.approximate_daily_usable_carcass_lb.low, D("577"))
        self.assertEqual(one.profile.approximate_annual_usable_carcass_tons.low, D("105"))
        self.assertEqual(one.profile.minimum_routine_reserve_tons.low, D("13"))
        self.assertEqual(one.horizon_usable_carcass_lb.low, D("25965"))
        self.assertFalse(one.actual_execution_eligible)

        full = dragon_carcass_demand(
            "full_rated_occupancy",
            horizon_days=D("45"),
        )
        self.assertEqual(full.profile.approximate_daily_usable_carcass_lb.low, D("928"))
        self.assertEqual(full.profile.approximate_annual_usable_carcass_tons.low, D("169"))
        self.assertEqual(full.profile.minimum_routine_reserve_tons.low, D("21"))
        self.assertEqual(full.profile.preferred_high_tempo_reserve_tons.low, D("42"))
        self.assertEqual(full.horizon_usable_carcass_lb.low, D("41760"))

    def test_dragon_demand_requires_explicit_decimal_horizon(self):
        with self.assertRaises(MissingPlanningInput):
            dragon_carcass_demand("one_warmother", horizon_days=None)
        with self.assertRaisesRegex(AgriculturePlanningError, "finite Decimal"):
            dragon_carcass_demand("one_warmother", horizon_days=45)  # type: ignore[arg-type]
        with self.assertRaisesRegex(AgriculturePlanningError, "unknown"):
            dragon_carcass_demand("invented", horizon_days=D("45"))

    def test_procurement_zero_is_real_zero_and_missing_is_not_zero(self):
        target = DecimalRange(D("1200"), D("1500"), unit="tons")
        result = procurement_coverage(D("0"), target)
        self.assertEqual(
            (result.coverage_fraction.low, result.coverage_fraction.high),
            (D("0"), D("0")),
        )
        self.assertEqual(
            (result.remaining_shortfall.low, result.remaining_shortfall.high),
            (D("1200"), D("1500")),
        )
        self.assertFalse(result.possibly_meets_target)
        self.assertFalse(result.definitely_meets_target)
        with self.assertRaisesRegex(MissingPlanningInput, "missing is not zero"):
            procurement_coverage(None, target)

    def test_procurement_range_exposes_uncertain_target_coverage(self):
        result = procurement_coverage(
            DecimalRange(D("1300"), D("1300"), unit="tons"),
            DecimalRange(D("1200"), D("1500"), unit="tons"),
        )
        self.assertEqual(
            result.coverage_fraction.low,
            D("0.8666666666666666666666666666666666666667"),
        )
        self.assertEqual(
            result.coverage_fraction.high,
            D("1.083333333333333333333333333333333333333"),
        )
        self.assertEqual(
            (result.remaining_shortfall.low, result.remaining_shortfall.high),
            (D("0"), D("200")),
        )
        self.assertTrue(result.possibly_meets_target)
        self.assertFalse(result.definitely_meets_target)

    def test_float_inputs_and_zero_target_are_rejected(self):
        with self.assertRaisesRegex(AgriculturePlanningError, "floats"):
            aquaculture_monthly_yield(0.1)  # type: ignore[arg-type]
        with self.assertRaisesRegex(AgriculturePlanningError, "greater than zero"):
            procurement_coverage(D("1"), D("0"))


if __name__ == "__main__":
    unittest.main()
