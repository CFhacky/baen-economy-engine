from decimal import Decimal, getcontext, setcontext
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from baen_economy.agriculture_logistics import (  # noqa: E402
    AgricultureLogisticsError,
    MissingLogisticsInput,
    OwnershipStatus,
    RouteLeg,
    RouteMode,
    ShipmentPlan,
    StorageFacility,
    barge_100_ton_spec,
    heavy_barge_150_ton_spec,
    plan_logistics,
    plan_route,
)
from baen_economy.source_values import (  # noqa: E402
    AuthorityClass,
    EvidenceLayer,
    EvidenceReference,
    SourcedValue,
)


D = Decimal


TECHNICAL_REF = EvidenceReference(
    source_id="fixture:technical",
    source_path="fixture://technical/specification",
    authority_class=AuthorityClass.TECHNICAL_DESIGN,
    layer=EvidenceLayer.TECHNICAL_DESIGN,
)
SCENARIO_REF = EvidenceReference(
    source_id="fixture:scenario",
    source_path="fixture://scenario/plan",
    authority_class=AuthorityClass.PROJECTION,
    layer=EvidenceLayer.FORWARD_SCENARIO,
)
NEVERWINTER_ICE_HOUSE_REF = EvidenceReference(
    source_id="fixture:neverwinter-ice-house",
    source_path="fixture://source-reference/neverwinter-20-ton-ice-house",
    authority_class=AuthorityClass.OBSERVED_OPERATING_STATE,
    layer=EvidenceLayer.HISTORICAL_OBSERVATION,
)


def sv(value, ref=SCENARIO_REF):
    return SourcedValue(value=value, evidence=(ref,), actual_execution_input=False)


def route_leg(
    *,
    leg_id="leg:road",
    origin="site:origin",
    destination="site:destination",
    mode=RouteMode.ROAD,
    capacity=D("100"),
    trips=2,
    loss=D("0.10"),
    duration=None,
    distance=None,
    speed=None,
):
    return RouteLeg(
        leg_id=leg_id,
        origin_site_id=origin,
        destination_site_id=destination,
        mode=mode,
        capacity_tons_per_trip=sv(capacity),
        trips_available=sv(trips),
        loss_rate=sv(loss),
        transit_duration_days=None if duration is None else sv(duration),
        distance_miles=None if distance is None else sv(distance),
        speed_miles_per_day=None if speed is None else sv(speed),
    )


def shipment(*, quantity=D("260"), cold=D("100"), legs=None):
    if legs is None:
        legs = (route_leg(),)
    return ShipmentPlan(
        shipment_id="shipment:grain",
        commodity_id="commodity:grain",
        requested_quantity_tons=sv(quantity),
        cold_storage_requested_tons=sv(cold),
        route_legs=legs,
    )


def storage(
    *,
    total=D("150"),
    cold=D("80"),
    opening=D("20"),
    opening_cold=D("10"),
    ambient_rate=D("0.10"),
    cold_rate=D("0.02"),
    ownership=OwnershipStatus.BAEN_OWNED,
    owner="entity:baen-enterprises",
):
    return StorageFacility(
        facility_id="storage:destination",
        name="Destination Storehouse",
        owner_entity_id=owner,
        ownership_status=ownership,
        holding_period_label="source-defined planning period",
        total_capacity_tons=sv(total),
        cold_capacity_tons=sv(cold),
        opening_inventory_tons=sv(opening),
        opening_cold_inventory_tons=sv(opening_cold),
        ambient_spoilage_rate=sv(ambient_rate),
        cold_spoilage_rate=sv(cold_rate),
    )


class AgricultureLogisticsTests(unittest.TestCase):
    def test_capacity_arrival_storage_spoilage_and_full_conservation(self):
        result = plan_logistics(shipment(), storage())

        leg = result.route.legs[0]
        self.assertEqual(leg.required_trips, 3)
        self.assertEqual(leg.trip_requirement_status, "calculated")
        self.assertEqual(leg.trips_scheduled, 2)
        self.assertEqual(leg.dispatched_tons, D("200"))
        self.assertEqual(leg.held_tons, D("60"))
        self.assertEqual(leg.route_loss_tons, D("20.00"))
        self.assertEqual(leg.arrived_tons, D("180.00"))

        stored = result.storage
        self.assertEqual(stored.available_capacity_tons, D("130"))
        self.assertEqual(stored.admitted_tons, D("130"))
        self.assertEqual(stored.overflow_tons, D("50.00"))
        self.assertEqual(stored.cold_stored_before_loss_tons, D("70"))
        self.assertEqual(stored.ambient_stored_before_loss_tons, D("60"))
        self.assertEqual(stored.cold_capacity_shortfall_tons, D("30"))
        self.assertEqual(stored.cold_spoilage_tons, D("1.40"))
        self.assertEqual(stored.ambient_spoilage_tons, D("6.00"))
        self.assertEqual(stored.retained_after_spoilage_tons, D("122.60"))
        self.assertEqual(result.conservation_residual_tons, D("0.00"))
        self.assertTrue(result.preview_only)
        self.assertEqual(
            result.held_for_capacity_tons
            + result.route_loss_tons
            + result.storage_overflow_tons
            + result.storage_spoilage_tons
            + result.retained_after_storage_tons,
            D("260.00"),
        )

    def test_two_leg_route_tracks_intermediate_holds_and_losses(self):
        road = route_leg(
            leg_id="leg:road",
            origin="site:farm",
            destination="site:canal-head",
            capacity=D("100"),
            trips=2,
            loss=D("0.10"),
            duration=D("2"),
        )
        canal = route_leg(
            leg_id="leg:canal",
            origin="site:canal-head",
            destination="site:city",
            mode=RouteMode.CANAL,
            capacity=D("50"),
            trips=3,
            loss=D("0.20"),
            distance=D("90"),
            speed=D("30"),
        )
        result = plan_route(shipment(quantity=D("300"), cold=D("0"), legs=(road, canal)))

        self.assertEqual(result.legs[0].held_tons, D("100"))
        self.assertEqual(result.legs[0].arrived_tons, D("180.00"))
        self.assertEqual(result.legs[1].incoming_tons, D("180.00"))
        self.assertEqual(result.legs[1].required_trips, 4)
        self.assertEqual(result.legs[1].held_tons, D("30.00"))
        self.assertEqual(result.legs[1].route_loss_tons, D("30.00"))
        self.assertEqual(result.held_for_capacity_tons, D("130.00"))
        self.assertEqual(result.route_loss_tons, D("50.00"))
        self.assertEqual(result.destination_arrival_tons, D("120.00"))
        self.assertEqual(result.total_transit_days, D("5"))
        self.assertEqual(result.conservation_residual_tons, D("0.00"))

    def test_timing_remains_unknown_when_speed_or_duration_is_not_supplied(self):
        leg = route_leg(distance=D("90"))
        result = plan_route(shipment(quantity=D("10"), cold=D("0"), legs=(leg,)))
        self.assertIsNone(leg.calculated_transit_days)
        self.assertIsNone(result.total_transit_days)

    def test_explicit_duration_and_derived_duration_must_not_conflict(self):
        with self.assertRaisesRegex(AgricultureLogisticsError, "duration conflicts"):
            route_leg(duration=D("2"), distance=D("90"), speed=D("30"))

        matching = route_leg(duration=D("3"), distance=D("90"), speed=D("30"))
        self.assertEqual(matching.calculated_transit_days, D("3"))

    def test_missing_capacity_is_not_treated_as_zero(self):
        leg = route_leg(capacity=None)
        with self.assertRaisesRegex(MissingLogisticsInput, "unknown; zero was not assumed"):
            plan_route(shipment(quantity=D("10"), cold=D("0"), legs=(leg,)))

    def test_missing_trips_and_loss_each_fail_closed(self):
        missing_trips = route_leg(trips=None)
        with self.assertRaisesRegex(MissingLogisticsInput, "trips available is unknown"):
            plan_route(
                shipment(quantity=D("10"), cold=D("0"), legs=(missing_trips,))
            )

        missing_loss = route_leg(loss=None)
        with self.assertRaisesRegex(MissingLogisticsInput, "loss rate is unknown"):
            plan_route(
                shipment(quantity=D("10"), cold=D("0"), legs=(missing_loss,))
            )

    def test_explicit_zero_capacity_is_a_known_closed_route(self):
        leg = route_leg(capacity=D("0"), trips=7, loss=D("0"))
        result = plan_route(shipment(quantity=D("25"), cold=D("0"), legs=(leg,)))
        receipt = result.legs[0]
        self.assertIsNone(receipt.required_trips)
        self.assertEqual(receipt.trip_requirement_status, "impossible_zero_capacity")
        self.assertEqual(receipt.trips_scheduled, 0)
        self.assertEqual(receipt.dispatched_tons, D("0"))
        self.assertEqual(receipt.held_tons, D("25"))
        self.assertEqual(result.destination_arrival_tons, D("0"))
        self.assertEqual(result.conservation_residual_tons, D("0"))

    def test_barge_helpers_require_exact_source_backed_specs(self):
        standard = barge_100_ton_spec(
            capacity_tons_per_trip=sv(D("100"), TECHNICAL_REF)
        )
        heavy = heavy_barge_150_ton_spec(
            capacity_tons_per_trip=sv(D("150"), TECHNICAL_REF)
        )
        self.assertEqual(standard.mode, RouteMode.CANAL)
        self.assertEqual(standard.capacity_tons_per_trip.evidence, (TECHNICAL_REF,))
        self.assertEqual(heavy.capacity_tons_per_trip.value, D("150"))

        with self.assertRaises(TypeError):
            barge_100_ton_spec()  # type: ignore[call-arg]
        with self.assertRaisesRegex(AgricultureLogisticsError, "exactly 100"):
            barge_100_ton_spec(capacity_tons_per_trip=sv(D("99"), TECHNICAL_REF))
        with self.assertRaisesRegex(MissingLogisticsInput, "unknown"):
            heavy_barge_150_ton_spec(capacity_tons_per_trip=sv(None, TECHNICAL_REF))

    def test_neverwinter_20_ton_ice_house_remains_third_party_reference(self):
        ice_house = StorageFacility(
            facility_id="storage:neverwinter-ice-house",
            name="Neverwinter Ice House",
            owner_entity_id="entity:neverwinter",
            ownership_status=OwnershipStatus.THIRD_PARTY,
            holding_period_label="fixture planning period",
            total_capacity_tons=sv(D("20"), NEVERWINTER_ICE_HOUSE_REF),
            cold_capacity_tons=sv(D("20"), NEVERWINTER_ICE_HOUSE_REF),
            opening_inventory_tons=sv(D("0"), NEVERWINTER_ICE_HOUSE_REF),
            opening_cold_inventory_tons=sv(D("0"), NEVERWINTER_ICE_HOUSE_REF),
            ambient_spoilage_rate=sv(D("0.10"), SCENARIO_REF),
            cold_spoilage_rate=sv(D("0.05"), SCENARIO_REF),
        )
        leg = route_leg(capacity=D("30"), trips=1, loss=D("0"))
        result = plan_logistics(
            shipment(quantity=D("30"), cold=D("30"), legs=(leg,)),
            ice_house,
        )
        self.assertEqual(result.storage.ownership_status, OwnershipStatus.THIRD_PARTY)
        self.assertEqual(result.storage.owner_entity_id, "entity:neverwinter")
        self.assertNotEqual(result.storage.owner_entity_id, "entity:baen-enterprises")
        self.assertEqual(result.storage.admitted_tons, D("20"))
        self.assertEqual(result.storage.overflow_tons, D("10"))
        self.assertEqual(result.storage.retained_after_spoilage_tons, D("19.00"))

    def test_missing_spoilage_rate_is_not_zero_but_explicit_zero_is_supported(self):
        leg = route_leg(capacity=D("10"), trips=1, loss=D("0"))
        plan = shipment(quantity=D("10"), cold=D("0"), legs=(leg,))
        with self.assertRaisesRegex(MissingLogisticsInput, "spoilage rate is unknown"):
            plan_logistics(plan, storage(ambient_rate=None, cold=D("0"), opening_cold=D("0")))

        no_spoilage = plan_logistics(
            plan,
            storage(
                ambient_rate=D("0"),
                cold_rate=None,
                cold=D("0"),
                opening_cold=D("0"),
            ),
        )
        self.assertEqual(no_spoilage.storage_spoilage_tons, D("0"))
        self.assertEqual(no_spoilage.retained_after_storage_tons, D("10"))

    def test_invalid_values_and_unsupported_modes_are_rejected(self):
        with self.assertRaisesRegex(AgricultureLogisticsError, "finite Decimal"):
            route_leg(capacity=100.0)
        with self.assertRaisesRegex(AgricultureLogisticsError, "between zero and one"):
            route_leg(loss=D("1.01"))
        with self.assertRaisesRegex(AgricultureLogisticsError, "road or canal"):
            route_leg(mode="river")
        with self.assertRaisesRegex(AgricultureLogisticsError, "cold storage capacity"):
            storage(total=D("20"), cold=D("21"), opening=D("0"), opening_cold=D("0"))

    def test_noncontiguous_or_implicit_route_is_rejected(self):
        with self.assertRaisesRegex(AgricultureLogisticsError, "at least one explicit"):
            shipment(quantity=D("1"), cold=D("0"), legs=())
        first = route_leg(origin="site:a", destination="site:b")
        second = route_leg(
            leg_id="leg:second", origin="site:c", destination="site:d"
        )
        with self.assertRaisesRegex(AgricultureLogisticsError, "contiguous"):
            shipment(quantity=D("1"), cold=D("0"), legs=(first, second))

    def test_decimal_context_does_not_change_planning_result(self):
        original = getcontext().copy()
        try:
            getcontext().prec = 4
            low_precision = plan_logistics(shipment(), storage())
            getcontext().prec = 28
            normal_precision = plan_logistics(shipment(), storage())
        finally:
            setcontext(original)
        self.assertEqual(low_precision, normal_precision)


if __name__ == "__main__":
    unittest.main()
