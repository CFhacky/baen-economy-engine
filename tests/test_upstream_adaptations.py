from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from baen_economy.stockflow import InventoryPosition, Recipe
from baen_economy.upstream_adaptations import (
    ScheduledEconomicEvent,
    UpstreamAdaptationError,
    allocate_export_after_local_need,
    events_due,
    production_capacity,
    settle_delivery,
)

D = Decimal


class UpstreamAdaptationTests(unittest.TestCase):
    def test_veloren_local_need_is_protected_before_export(self):
        allocation = allocate_export_after_local_need(
            on_hand=D("100"),
            reserved=D("10"),
            local_need=D("70"),
            requested_export=D("50"),
            route_capacity=D("50"),
        )
        self.assertEqual(allocation.protected_local, D("70"))
        self.assertEqual(allocation.local_shortfall, D("0"))
        self.assertEqual(allocation.exportable_after_local, D("20"))
        self.assertEqual(allocation.dispatched_export, D("20"))

    def test_local_shortage_is_not_hidden_by_export(self):
        allocation = allocate_export_after_local_need(
            on_hand=D("50"), reserved=D("10"), local_need=D("60"),
            requested_export=D("20"), route_capacity=D("20"),
        )
        self.assertEqual(allocation.protected_local, D("40"))
        self.assertEqual(allocation.local_shortfall, D("20"))
        self.assertEqual(allocation.dispatched_export, D("0"))

    def test_export_respects_route_capacity_after_local_need(self):
        allocation = allocate_export_after_local_need(
            on_hand=D("200"), reserved=D("20"), local_need=D("50"),
            requested_export=D("100"), route_capacity=D("30"),
        )
        self.assertEqual(allocation.exportable_after_local, D("130"))
        self.assertEqual(allocation.dispatched_export, D("30"))

    def test_export_rejects_overreservation_instead_of_clamping(self):
        with self.assertRaisesRegex(UpstreamAdaptationError, "exceeds on-hand"):
            allocate_export_after_local_need(
                on_hand=D("10"), reserved=D("11"), local_need=D("0"),
                requested_export=D("0"), route_capacity=D("0"),
            )

    def test_freecol_unknown_horizons_capacity_separates_maximum_and_feasible(self):
        recipe = Recipe(
            "recipe:steel",
            "site:forge",
            "entity:forge",
            (("commodity:ore", D("2")), ("commodity:coal", D("1"))),
            (("commodity:steel", D("1")),),
            D("2"),
            D("10"),
        )
        capacity = production_capacity(
            recipe,
            (
                InventoryPosition("site:forge", "commodity:ore", D("12"), D("2")),
                InventoryPosition("site:forge", "commodity:coal", D("20")),
            ),
            site_labor_capacity=D("16"),
        )
        # Unlimited-input maximum is labor/configuration limited to 8 batches.
        self.assertEqual(capacity.maximum_batches, D("8"))
        # Available ore is 10 after reservation; 2 ore/batch => 5 feasible.
        self.assertEqual(capacity.input_limit_batches, D("5"))
        self.assertEqual(capacity.feasible_batches, D("5"))
        self.assertEqual(capacity.limiting_inputs, ("commodity:ore",))
        self.assertEqual(capacity.actual_for(D("7")), D("5"))

    def test_inputless_recipe_still_reports_labor_and_configured_maximum(self):
        recipe = Recipe(
            "recipe:service", "site:office", "entity:office", (),
            (("commodity:service", D("1")),), D("3"), D("9"),
        )
        capacity = production_capacity(recipe, (), site_labor_capacity=D("15"))
        self.assertEqual(capacity.maximum_batches, D("5"))
        self.assertEqual(capacity.feasible_batches, D("5"))
        self.assertEqual(capacity.limiting_inputs, ())

    def test_delivery_revenue_is_based_only_on_accepted_cargo(self):
        settlement = settle_delivery(
            shipment_id="shipment:grain-1",
            dispatched_quantity=D("100"),
            accepted_quantity=D("80"),
            unit_value=D("2.50"),
            distance_units=D("120"),
            periods_in_transit=3,
            subsidy_multiplier=D("1.5"),
        )
        self.assertEqual(settlement.rejected_quantity, D("20"))
        self.assertEqual(settlement.base_revenue, D("200.00"))
        self.assertEqual(settlement.subsidy_amount, D("100.000"))
        self.assertEqual(settlement.total_revenue, D("300.000"))

    def test_delivery_cannot_accept_more_than_was_dispatched(self):
        with self.assertRaisesRegex(UpstreamAdaptationError, "cannot exceed"):
            settle_delivery(
                shipment_id="shipment:x", dispatched_quantity=D("10"),
                accepted_quantity=D("11"), unit_value=D("1"),
                distance_units=D("1"), periods_in_transit=1,
            )

    def test_mesa_style_due_events_have_explicit_deterministic_order(self):
        events = (
            ScheduledEconomicEvent(D("2"), 20, "event:c"),
            ScheduledEconomicEvent(D("1"), 10, "event:b"),
            ScheduledEconomicEvent(D("1"), 10, "event:a"),
            ScheduledEconomicEvent(D("4"), 0, "event:later"),
        )
        due = events_due(events, current_time=D("0"), until=D("2"))
        self.assertEqual([event.event_id for event in due], ["event:a", "event:b", "event:c"])

    def test_due_event_query_does_not_accept_backwards_time_or_duplicate_ids(self):
        with self.assertRaisesRegex(UpstreamAdaptationError, "later"):
            events_due((), current_time=D("2"), until=D("2"))
        with self.assertRaisesRegex(UpstreamAdaptationError, "duplicate"):
            events_due(
                (ScheduledEconomicEvent(D("1"), 0, "event:x"),
                 ScheduledEconomicEvent(D("2"), 0, "event:x")),
                current_time=D("0"), until=D("3"),
            )


if __name__ == "__main__":
    unittest.main()
