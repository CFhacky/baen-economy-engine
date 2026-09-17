from dataclasses import FrozenInstanceError
import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from baen_economy.agriculture_calendar import (  # noqa: E402
    AgricultureCalendarError,
    AgricultureTemporalGate,
    AmbiguousCampaignDateError,
    CampaignDate,
    DateRelation,
    MonthPart,
    PlanningPreviewSelection,
    REALMS_MONTHS,
    RealmsMonth,
    ReferenceKind,
    TemporalClass,
    TemporalGateError,
    TemporalReference,
    compare_campaign_dates,
)


CURRENT = CampaignDate.on_day(1495, RealmsMonth.HAMMER, 7)


def dated(reference_id: str, campaign_date: CampaignDate) -> TemporalReference:
    return TemporalReference(reference_id, ReferenceKind.DATED, campaign_date)


class CampaignDateTests(unittest.TestCase):
    def test_calendar_has_all_twelve_realms_months_in_order(self) -> None:
        self.assertEqual(
            tuple(month.value for month in REALMS_MONTHS),
            (
                "Hammer",
                "Alturiak",
                "Ches",
                "Tarsakh",
                "Mirtul",
                "Kythorn",
                "Flamerule",
                "Eleasis",
                "Eleint",
                "Marpenoth",
                "Uktar",
                "Nightal",
            ),
        )
        self.assertEqual(len(set(REALMS_MONTHS)), 12)

    def test_exact_partial_and_whole_month_markers_keep_their_precision(self) -> None:
        exact = CampaignDate.on_day(1495, RealmsMonth.HAMMER, 7)
        late = CampaignDate.in_part(1495, RealmsMonth.KYTHORN, MonthPart.LATE)
        month = CampaignDate.in_month(1498, RealmsMonth.ELEINT)

        self.assertEqual(exact.day_bounds, (7, 7))
        self.assertEqual(exact.label, "Day 7 Hammer 1495 DR")
        self.assertEqual(late.day_bounds, (21, 30))
        self.assertEqual(late.label, "late Kythorn 1495 DR")
        self.assertEqual(month.day_bounds, (1, 30))
        self.assertEqual(month.label, "Eleint 1498 DR")

    def test_date_validation_rejects_invalid_or_invented_fields(self) -> None:
        invalid = (
            lambda: CampaignDate.on_day(True, RealmsMonth.HAMMER, 7),
            lambda: CampaignDate.on_day(1495, "Hammer", 7),  # type: ignore[arg-type]
            lambda: CampaignDate.on_day(1495, RealmsMonth.HAMMER, False),
            lambda: CampaignDate.on_day(1495, RealmsMonth.HAMMER, 0),
            lambda: CampaignDate.on_day(1495, RealmsMonth.HAMMER, 31),
            lambda: CampaignDate(
                1495, RealmsMonth.HAMMER, day=7, part=MonthPart.EARLY
            ),
            lambda: CampaignDate(
                1495, RealmsMonth.HAMMER, part="late"  # type: ignore[arg-type]
            ),
        )
        for build in invalid:
            with self.subTest(build=build), self.assertRaises(
                AgricultureCalendarError
            ):
                build()

    def test_interval_comparison_does_not_invent_a_day_for_late_kythorn(self) -> None:
        late_kythorn = CampaignDate.in_part(
            1495, RealmsMonth.KYTHORN, MonthPart.LATE
        )
        eleint_1494 = CampaignDate.in_month(1494, RealmsMonth.ELEINT)

        self.assertEqual(
            compare_campaign_dates(late_kythorn, CURRENT), DateRelation.AFTER
        )
        self.assertEqual(
            compare_campaign_dates(eleint_1494, CURRENT), DateRelation.BEFORE
        )
        self.assertEqual(
            compare_campaign_dates(CURRENT, CURRENT), DateRelation.EXACT
        )
        self.assertEqual(
            compare_campaign_dates(
                CampaignDate.in_part(1495, RealmsMonth.HAMMER, MonthPart.EARLY),
                CURRENT,
            ),
            DateRelation.OVERLAPS,
        )

    def test_campaign_dates_are_immutable(self) -> None:
        with self.assertRaises(FrozenInstanceError):
            CURRENT.day = 8  # type: ignore[misc]


class AgricultureTemporalGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gate = AgricultureTemporalGate(CURRENT)

    def test_exact_live_freeze_is_the_only_current_actual_date(self) -> None:
        reference = dated("arik-live-freeze", CURRENT)

        self.assertEqual(
            self.gate.classify(reference), TemporalClass.CURRENT_ACTUAL
        )
        self.assertIs(self.gate.require_current_actual(reference), reference)
        self.assertTrue(TemporalClass.CURRENT_ACTUAL.eligible_for_current_actual)
        self.assertFalse(TemporalClass.FORWARD.eligible_for_current_actual)

    def test_eleint_1494_is_historical(self) -> None:
        reference = dated(
            "registry-eleint-1494",
            CampaignDate.in_month(1494, RealmsMonth.ELEINT),
        )

        self.assertEqual(self.gate.classify(reference), TemporalClass.HISTORICAL)
        with self.assertRaisesRegex(TemporalGateError, "historical"):
            self.gate.require_current_actual(reference)

    def test_late_kythorn_1495_is_forward_not_current(self) -> None:
        reference = dated(
            "operation-laden",
            CampaignDate.in_part(1495, RealmsMonth.KYTHORN, MonthPart.LATE),
        )

        self.assertEqual(self.gate.classify(reference), TemporalClass.FORWARD)
        with self.assertRaisesRegex(TemporalGateError, "forward"):
            self.gate.require_current_actual(reference)

    def test_eleint_1498_is_later_not_forward_or_current(self) -> None:
        reference = dated(
            "water-empire-eleint-1498",
            CampaignDate.in_month(1498, RealmsMonth.ELEINT),
        )

        self.assertEqual(self.gate.classify(reference), TemporalClass.LATER)

    def test_explicit_undated_and_declared_later_references_remain_separate(self) -> None:
        undated = TemporalReference("orchard-undated", ReferenceKind.UNDATED)
        day_904 = TemporalReference(
            "ravencrest-day-904", ReferenceKind.DECLARED_LATER
        )

        self.assertEqual(self.gate.classify(undated), TemporalClass.UNDATED)
        self.assertEqual(self.gate.classify(day_904), TemporalClass.LATER)

    def test_technical_design_stays_technical_even_when_the_document_is_dated(self) -> None:
        reference = TemporalReference(
            "aquaculture-technical",
            ReferenceKind.TECHNICAL,
            CampaignDate.in_month(1498, RealmsMonth.ELEINT),
        )

        self.assertEqual(self.gate.classify(reference), TemporalClass.TECHNICAL)

    def test_partial_hammer_date_overlapping_day_7_fails_closed(self) -> None:
        reference = dated(
            "hammer-1495-unspecified",
            CampaignDate.in_month(1495, RealmsMonth.HAMMER),
        )

        with self.assertRaisesRegex(
            AmbiguousCampaignDateError, "supply an exact source date"
        ):
            self.gate.classify(reference)

    def test_declared_later_with_nonlater_date_is_a_source_contradiction(self) -> None:
        reference = TemporalReference(
            "contradiction",
            ReferenceKind.DECLARED_LATER,
            CampaignDate.in_month(1494, RealmsMonth.ELEINT),
        )

        with self.assertRaisesRegex(TemporalGateError, "not after"):
            self.gate.classify(reference)

    def test_reference_and_gate_validation_fail_closed(self) -> None:
        invalid = (
            lambda: TemporalReference("dated-without-date", ReferenceKind.DATED),
            lambda: TemporalReference(
                "undated-with-date", ReferenceKind.UNDATED, CURRENT
            ),
            lambda: TemporalReference(" bad-id", ReferenceKind.UNDATED),
            lambda: AgricultureTemporalGate(
                CampaignDate.in_month(1495, RealmsMonth.HAMMER)
            ),
            lambda: AgricultureTemporalGate(CURRENT, forward_through_year=1494),
            lambda: AgricultureTemporalGate(CURRENT, forward_through_year=True),
        )
        for build in invalid:
            with self.subTest(build=build), self.assertRaises(
                AgricultureCalendarError
            ):
                build()

    def test_planning_preview_refuses_implicit_selection(self) -> None:
        reference = dated(
            "operation-laden",
            CampaignDate.in_part(1495, RealmsMonth.KYTHORN, MonthPart.LATE),
        )

        with self.assertRaisesRegex(TemporalGateError, "explicit"):
            self.gate.require_planning_preview(reference, None)

    def test_explicit_selection_permits_only_isolated_nonmutating_preview(self) -> None:
        references = (
            dated(
                "operation-laden",
                CampaignDate.in_part(1495, RealmsMonth.KYTHORN, MonthPart.LATE),
            ),
            dated(
                "water-empire",
                CampaignDate.in_month(1498, RealmsMonth.ELEINT),
            ),
            TemporalReference("aquaculture-spec", ReferenceKind.TECHNICAL),
            TemporalReference("orchard-undated", ReferenceKind.UNDATED),
        )

        for reference in references:
            with self.subTest(reference=reference.reference_id):
                before = self.gate.current_actual
                selection = self.gate.select_planning_preview(
                    reference, reason="isolated operator-selected planning preview"
                )
                permit = self.gate.require_planning_preview(reference, selection)
                self.assertEqual(permit.reference_id, reference.reference_id)
                self.assertEqual(permit.layer, self.gate.classify(reference))
                self.assertFalse(permit.may_advance_campaign_time)
                self.assertFalse(permit.may_mutate_current_actual)
                self.assertEqual(self.gate.current_actual, before)
                self.assertEqual(self.gate.current_actual, CURRENT)

    def test_current_and_historical_evidence_cannot_become_planning_previews(self) -> None:
        current = dated("arik-live-freeze", CURRENT)
        historical = dated(
            "registry-eleint-1494",
            CampaignDate.in_month(1494, RealmsMonth.ELEINT),
        )

        for reference in (current, historical):
            with self.subTest(reference=reference.reference_id), self.assertRaisesRegex(
                TemporalGateError, "cannot be selected"
            ):
                self.gate.select_planning_preview(reference, reason="invalid attempt")

    def test_preview_token_is_bound_to_reference_layer_and_actual_anchor(self) -> None:
        laden = dated(
            "operation-laden",
            CampaignDate.in_part(1495, RealmsMonth.KYTHORN, MonthPart.LATE),
        )
        other = dated(
            "another-forward-reference",
            CampaignDate.in_month(1495, RealmsMonth.MIRTUL),
        )
        selection = self.gate.select_planning_preview(
            laden, reason="explicit Laden preview"
        )

        with self.assertRaisesRegex(TemporalGateError, "another reference"):
            self.gate.require_planning_preview(other, selection)

        wrong_layer = PlanningPreviewSelection(
            laden.reference_id,
            TemporalClass.LATER,
            CURRENT,
            "deliberately wrong layer",
        )
        with self.assertRaisesRegex(TemporalGateError, "layer no longer matches"):
            self.gate.require_planning_preview(laden, wrong_layer)

        wrong_anchor = PlanningPreviewSelection(
            laden.reference_id,
            TemporalClass.FORWARD,
            CampaignDate.on_day(1495, RealmsMonth.HAMMER, 8),
            "deliberately wrong anchor",
        )
        with self.assertRaisesRegex(TemporalGateError, "another actual anchor"):
            self.gate.require_planning_preview(laden, wrong_anchor)

    def test_wider_forward_horizon_requires_deliberate_gate_configuration(self) -> None:
        eleint_1498 = dated(
            "water-empire",
            CampaignDate.in_month(1498, RealmsMonth.ELEINT),
        )

        self.assertEqual(self.gate.classify(eleint_1498), TemporalClass.LATER)
        widened = AgricultureTemporalGate(CURRENT, forward_through_year=1498)
        self.assertEqual(widened.classify(eleint_1498), TemporalClass.FORWARD)


if __name__ == "__main__":
    unittest.main()
