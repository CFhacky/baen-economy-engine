from decimal import Decimal, getcontext, setcontext
from itertools import permutations
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from baen_economy.stockflow import (  # noqa: E402
    Commodity, EconomyModel, InventoryPosition, Need, PricePosition,
    ProductionOrder, Recipe, Route, RunPlan, ShipmentOrder, Site, TransitLot,
    advance, available_quantity, initial_snapshot,
)
from baen_economy.domain import (  # noqa: E402
    Authority, SimulationAssignment, SimulationMode, TemporalState,
)
from baen_economy.events import (  # noqa: E402
    CampaignDate, EventEnvelope, EventStore, ResolutionStatus,
)


D = Decimal


def authority_event(
    *, key="fixture:production", phase="production", entity_id="entity:farm",
    site_id="site:farm",
    ordinal=1, authority=Authority.CAMPAIGN_RESOLUTION,
    temporal_state=TemporalState.CURRENT,
    resolution_status=ResolutionStatus.RESOLVED,
    payload=None, event_type=None, source_ref=None,
):
    if payload is None:
        payload = {"recipe_id": "recipe:grain", "requested_batches": D("1")}
    return EventEnvelope.create(
        source_event_key=key,
        event_revision=1,
        timeline_id="actual",
        model_version="economy-0.1",
        campaign_date=CampaignDate(ordinal, f"Synthetic {ordinal}"),
        phase=phase,
        sequence=1,
        authority=authority,
        temporal_state=temporal_state,
        resolution_status=resolution_status,
        source_ref=source_ref or f"fixture:{key}",
        event_type=event_type or f"stock.{phase}",
        subject_entity_id=entity_id,
        subject_site_id=site_id,
        payload=payload,
    )


def fixture_model():
    return EconomyModel(
        commodities=(Commodity("commodity:grain", "Grain", "ton", D("1")),),
        sites=(Site("site:farm", "Farm", D("10")), Site("site:town", "Town", D("5"))),
        recipes=(Recipe("recipe:grain", "site:farm", "entity:farm", (), (("commodity:grain", D("100")),), D("10"), D("1")),),
        routes=(Route("route:farm-town", "site:farm", "site:town", "commodity:grain", D("50"), 1, D("0")),),
    )


def empty_actual_opening(model):
    payload = {
        "timeline_id": "actual",
        "campaign_ordinal": 0,
        "campaign_date": "Synthetic 0",
        "inventories": [],
        "prices": [],
        "transit": [],
    }
    event = authority_event(
        key="fixture:empty-opening", phase="source_lock", ordinal=0,
        event_type="stock.opening", payload=payload,
    )
    store = EventStore()
    store.append(event)
    opening = initial_snapshot(
        model, timeline_id="actual", campaign_ordinal=0,
        campaign_date="Synthetic 0", ruleset_version="0.1",
        opening_events=(event,), event_store=store,
    )
    return opening, store


class StockFlowTests(unittest.TestCase):
    def test_actual_state_requires_validated_authority_and_mode(self):
        model = fixture_model()
        opening, store = empty_actual_opening(model)
        with self.assertRaisesRegex(ValueError, "authorizing event"):
            advance(model, opening, RunPlan(
                1, 1, "Synthetic 1",
                production_orders=(ProductionOrder("recipe:grain", D("1")),),
            ), event_store=store)

        scenario = authority_event(authority=Authority.SCENARIO_ASSUMPTION)
        store.append(scenario)
        assignment = SimulationAssignment(
            "entity:farm", "actual", 1, SimulationMode.STOCK_FLOW, "fixture:mode"
        )
        with self.assertRaisesRegex(ValueError, "may not mutate actual"):
            advance(model, opening, RunPlan(
                1, 1, "Synthetic 1",
                production_orders=(ProductionOrder("recipe:grain", D("1"), scenario.event_id),),
                authorizing_events=(scenario,), simulation_assignments=(assignment,),
            ), event_store=store)

        resolved = authority_event(key="fixture:resolved")
        store.append(resolved)
        result = advance(model, opening, RunPlan(
            1, 1, "Synthetic 1",
            production_orders=(ProductionOrder("recipe:grain", D("1"), resolved.event_id),),
            authorizing_events=(resolved,), simulation_assignments=(assignment,),
        ), event_store=store)
        self.assertEqual(result.production[0].actual_batches, D("1"))
        self.assertIn((resolved.event_id, resolved.integrity_hash), result.snapshot.applied_event_refs)

        mismatched = authority_event(key="fixture:mismatch", payload={
            "recipe_id": "recipe:grain", "requested_batches": D("999")
        })
        store.append(mismatched)
        with self.assertRaisesRegex(ValueError, "payload does not match"):
            advance(model, opening, RunPlan(
                1, 1, "Synthetic 1",
                production_orders=(ProductionOrder("recipe:grain", D("1"), mismatched.event_id),),
                authorizing_events=(mismatched,), simulation_assignments=(assignment,),
            ), event_store=store)

    def test_actual_opening_stock_requires_authoritative_event(self):
        model = fixture_model()
        inventory = (InventoryPosition("site:farm", "commodity:grain", D("1")),)
        with self.assertRaisesRegex(ValueError, "opening state requires"):
            initial_snapshot(
                model, timeline_id="actual", campaign_ordinal=0,
                campaign_date="Synthetic 0", ruleset_version="0.1",
            )
        with self.assertRaisesRegex(ValueError, "opening state requires"):
            initial_snapshot(
                model, timeline_id="actual", campaign_ordinal=0,
                campaign_date="Synthetic 0", ruleset_version="0.1",
                inventories=inventory,
            )

        contradictory_date = EventEnvelope.create(
            source_event_key="fixture:opening-date", event_revision=1,
            timeline_id="actual", model_version=model.model_version,
            campaign_date=CampaignDate(0, "Contradictory Date"),
            phase="source_lock", sequence=1,
            authority=Authority.CAMPAIGN_RESOLUTION,
            temporal_state=TemporalState.CURRENT,
            resolution_status=ResolutionStatus.RESOLVED,
            source_ref="fixture:opening-date", event_type="stock.opening",
            payload={
                "timeline_id": "actual", "campaign_ordinal": 0,
                "campaign_date": "Synthetic 0", "inventories": [],
                "prices": [], "transit": [],
            },
        )
        contradictory_store = EventStore()
        contradictory_store.append(contradictory_date)
        with self.assertRaisesRegex(ValueError, "date label"):
            initial_snapshot(
                model, timeline_id="actual", campaign_ordinal=0,
                campaign_date="Synthetic 0", ruleset_version="0.1",
                opening_events=(contradictory_date,), event_store=contradictory_store,
            )

        payload = {
            "timeline_id": "actual",
            "campaign_ordinal": 0,
            "campaign_date": "Synthetic 0",
            "inventories": [{
                "site_id": "site:farm", "commodity_id": "commodity:grain",
                "quantity": "1", "reserved_quantity": "0",
            }],
            "prices": [],
            "transit": [],
        }
        opening_event = authority_event(
            key="fixture:opening", phase="source_lock", ordinal=0,
            event_type="stock.opening", payload=payload,
        )
        store = EventStore()
        store.append(opening_event)
        opened = initial_snapshot(
            model, timeline_id="actual", campaign_ordinal=0,
            campaign_date="Synthetic 0", ruleset_version="0.1",
            inventories=inventory, opening_events=(opening_event,), event_store=store,
        )
        self.assertEqual(opened.inventories, inventory)

        mismatched = authority_event(
            key="fixture:opening-mismatch", phase="source_lock", ordinal=0,
            event_type="stock.opening", payload={**payload, "inventories": []},
        )
        store.append(mismatched)
        with self.assertRaisesRegex(ValueError, "does not match"):
            initial_snapshot(
                model, timeline_id="actual", campaign_ordinal=0,
                campaign_date="Synthetic 0", ruleset_version="0.1",
                inventories=inventory, opening_events=(mismatched,), event_store=store,
            )

    def test_invalid_snapshot_references_prices_and_transit_fail_closed(self):
        model = fixture_model()
        with self.assertRaisesRegex(ValueError, "prices must be positive"):
            initial_snapshot(
                model, timeline_id="surface:preview", campaign_ordinal=0,
                campaign_date="Synthetic 0", ruleset_version="0.1",
                prices=(PricePosition("site:farm", "commodity:grain", D("-1")),),
            )
        with self.assertRaisesRegex(ValueError, "unknown route"):
            initial_snapshot(
                model, timeline_id="surface:preview", campaign_ordinal=0,
                campaign_date="Synthetic 0", ruleset_version="0.1",
                transit=(TransitLot(
                    "shipment:x", "route:unknown", "commodity:grain",
                    "site:farm", "site:town", D("10"), 1, D("0"),
                ),),
            )
        with self.assertRaisesRegex(ValueError, "loss rate"):
            TransitLot(
                "shipment:x", "route:farm-town", "commodity:grain",
                "site:farm", "site:town", D("10"), 1, D("-1"),
            )

    def test_decimal_context_cannot_change_results_or_hashes(self):
        model = fixture_model()
        opening = initial_snapshot(
            model, timeline_id="surface:preview", campaign_ordinal=0,
            campaign_date="Synthetic 0", ruleset_version="0.1",
            inventories=(InventoryPosition("site:town", "commodity:grain", D("1")),),
        )
        plan = RunPlan(
            1, 1, "Synthetic 1",
            needs=(Need("site:town", "commodity:grain", D("3")),),
        )
        original = getcontext().copy()
        try:
            getcontext().prec = 4
            low_precision = advance(model, opening, plan)
            getcontext().prec = 28
            normal_precision = advance(model, opening, plan)
        finally:
            setcontext(original)
        self.assertEqual(low_precision, normal_precision)

    def test_decimal_capitals_cannot_change_model_or_snapshot_hashes(self):
        original = getcontext().copy()
        try:
            getcontext().capitals = 0
            lower_model = EconomyModel(
                commodities=(
                    Commodity("commodity:grain", "Grain", "ton", D("1E+20")),
                ),
                sites=(Site("site:town", "Town", D("1")),),
                recipes=(),
                routes=(),
            )
            lower_opening = initial_snapshot(
                lower_model,
                timeline_id="surface:preview",
                campaign_ordinal=0,
                campaign_date="Synthetic 0",
                ruleset_version="0.1",
                inventories=(
                    InventoryPosition("site:town", "commodity:grain", D("1E+20")),
                ),
            )
            lower_result = advance(
                lower_model,
                lower_opening,
                RunPlan(
                    1,
                    1,
                    "Synthetic 1",
                    needs=(Need("site:town", "commodity:grain", D("1")),),
                ),
            )
            getcontext().capitals = 1
            upper_model = EconomyModel(
                commodities=(
                    Commodity("commodity:grain", "Grain", "ton", D("1E+20")),
                ),
                sites=(Site("site:town", "Town", D("1")),),
                recipes=(),
                routes=(),
            )
            upper_opening = initial_snapshot(
                upper_model,
                timeline_id="surface:preview",
                campaign_ordinal=0,
                campaign_date="Synthetic 0",
                ruleset_version="0.1",
                inventories=(
                    InventoryPosition("site:town", "commodity:grain", D("1E+20")),
                ),
            )
            upper_result = advance(
                upper_model,
                upper_opening,
                RunPlan(
                    1,
                    1,
                    "Synthetic 1",
                    needs=(Need("site:town", "commodity:grain", D("1")),),
                ),
            )
        finally:
            setcontext(original)
        self.assertEqual(lower_opening.model_hash, upper_opening.model_hash)
        self.assertEqual(lower_opening.state_hash, upper_opening.state_hash)
        self.assertEqual(lower_result, upper_result)
        lower_result.snapshot.verify()

    def test_replay_numeric_state_requires_finite_decimals(self):
        with self.assertRaisesRegex(ValueError, "finite Decimal"):
            InventoryPosition("site:farm", "commodity:grain", 1)
        with self.assertRaisesRegex(ValueError, "finite Decimal"):
            Commodity("commodity:grain", "Grain", "ton", 1)
        with self.assertRaisesRegex(ValueError, "finite Decimal"):
            ProductionOrder("recipe:grain", 1)
        with self.assertRaisesRegex(ValueError, "finite Decimal"):
            Need("site:farm", "commodity:grain", True)

    def test_replay_indices_reject_booleans(self):
        model = fixture_model()
        with self.assertRaisesRegex(ValueError, "opening campaign ordinal"):
            initial_snapshot(
                model,
                timeline_id="surface:preview",
                campaign_ordinal=False,
                campaign_date="Synthetic 0",
                ruleset_version="0.1",
            )
        with self.assertRaisesRegex(ValueError, "run period index"):
            RunPlan(True, 1, "Synthetic 1")
        with self.assertRaisesRegex(ValueError, "simulation period index"):
            SimulationAssignment(
                "entity:farm", "actual", True, SimulationMode.STOCK_FLOW, "fixture"
            )

    def test_run_plan_rejects_one_shot_or_wrong_typed_collections(self):
        order = ProductionOrder("recipe:grain", D("1"))
        with self.assertRaisesRegex(ValueError, "immutable tuple"):
            RunPlan(
                1,
                1,
                "Synthetic 1",
                production_orders=(item for item in (order,)),
            )
        with self.assertRaisesRegex(ValueError, "wrong type"):
            RunPlan(1, 1, "Synthetic 1", production_orders=("not-an-order",))
        with self.assertRaisesRegex(ValueError, "model commodities.*immutable tuple"):
            EconomyModel(
                (item for item in fixture_model().commodities),
                fixture_model().sites,
                (),
                (),
            )

    def test_model_hash_blocks_replay_with_changed_rules(self):
        model = fixture_model()
        opening = initial_snapshot(
            model, timeline_id="surface:preview", campaign_ordinal=0,
            campaign_date="Synthetic 0", ruleset_version="0.1",
        )
        changed = EconomyModel(
            model.commodities,
            (Site("site:farm", "Farm", D("11")), model.sites[1]),
            model.recipes,
            model.routes,
        )
        with self.assertRaisesRegex(ValueError, "model hash"):
            advance(changed, opening, RunPlan(1, 1, "Synthetic 1"))

    def test_equal_priority_needs_are_aggregated_order_independently(self):
        model = fixture_model()
        opening = initial_snapshot(
            model, timeline_id="surface:preview", campaign_ordinal=0,
            campaign_date="Synthetic 0", ruleset_version="0.1",
            inventories=(InventoryPosition("site:town", "commodity:grain", D("10")),),
        )
        need_a = Need("site:town", "commodity:grain", D("8"))
        need_b = Need("site:town", "commodity:grain", D("12"))
        first = advance(model, opening, RunPlan(1, 1, "Synthetic 1", needs=(need_a, need_b)))
        second = advance(model, opening, RunPlan(1, 1, "Synthetic 1", needs=(need_b, need_a)))
        self.assertEqual(first, second)
        self.assertEqual(first.needs[0].requested_quantity, D("20"))

    def test_need_aggregation_is_order_independent_at_decimal_precision_boundary(self):
        model = fixture_model()
        opening = initial_snapshot(
            model,
            timeline_id="surface:preview",
            campaign_ordinal=0,
            campaign_date="Synthetic 0",
            ruleset_version="0.1",
            inventories=(
                InventoryPosition("site:town", "commodity:grain", D("2E40")),
            ),
        )
        needs = (
            Need("site:town", "commodity:grain", D("1E40")),
            Need("site:town", "commodity:grain", D("6")),
            Need("site:town", "commodity:grain", D("6")),
        )
        results = [
            advance(model, opening, RunPlan(1, 1, "Synthetic 1", needs=ordering))
            for ordering in permutations(needs)
        ]
        self.assertEqual(len({result.snapshot.input_hash for result in results}), 1)
        self.assertEqual(len({result.snapshot.state_hash for result in results}), 1)
        self.assertTrue(all(result == results[0] for result in results))

    def test_route_rejects_a_different_commodity_unit(self):
        model = fixture_model()
        with self.assertRaisesRegex(ValueError, "unit"):
            Commodity("commodity:blank", "Blank", " ", D("1"))
        mixed = EconomyModel(
            (*model.commodities, Commodity("commodity:tools", "Tools", "crate", D("5"))),
            model.sites, model.recipes, model.routes,
        )
        opening = initial_snapshot(
            mixed, timeline_id="surface:preview", campaign_ordinal=0,
            campaign_date="Synthetic 0", ruleset_version="0.1",
            inventories=(InventoryPosition("site:farm", "commodity:tools", D("5")),),
        )
        with self.assertRaisesRegex(ValueError, "declared for"):
            advance(mixed, opening, RunPlan(
                1, 1, "Synthetic 1",
                shipment_orders=(ShipmentOrder(
                    "shipment:tools", "route:farm-town", "commodity:tools", D("5"), "fixture"
                ),),
            ))

    def test_duplicate_opening_inventory_position_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate inventory"):
            initial_snapshot(
                fixture_model(),
                timeline_id="surface:preview",
                campaign_ordinal=0,
                campaign_date="Synthetic 0",
                ruleset_version="0.1",
                inventories=(
                    InventoryPosition("site:farm", "commodity:grain", D("10")),
                    InventoryPosition("site:farm", "commodity:grain", D("5")),
                ),
            )

    def test_snapshot_rejects_mutable_nested_collections(self):
        opening = initial_snapshot(
            fixture_model(),
            timeline_id="surface:preview",
            campaign_ordinal=0,
            campaign_date="Synthetic 0",
            ruleset_version="0.1",
        )
        from dataclasses import replace

        with self.assertRaisesRegex(ValueError, "snapshot inventories.*immutable tuple"):
            replace(opening, inventories=[]).verify()

    def test_available_to_promise_excludes_reserved_stock(self):
        position = InventoryPosition(
            "site:farm", "commodity:grain", D("10"), D("4")
        )
        self.assertEqual(available_quantity(position), D("6"))
        self.assertEqual(available_quantity(None), D("0"))
        with self.assertRaisesRegex(ValueError, "reserved inventory"):
            InventoryPosition("site:farm", "commodity:grain", D("10"), D("12"))

    def test_reserved_stock_cannot_be_double_spent(self):
        model = fixture_model()
        opening = initial_snapshot(
            model,
            timeline_id="surface:preview",
            campaign_ordinal=0,
            campaign_date="Synthetic 0",
            ruleset_version="0.1",
            inventories=(
                InventoryPosition(
                    "site:farm", "commodity:grain", D("50"), D("30")
                ),
            ),
        )
        result = advance(
            model,
            opening,
            RunPlan(
                1,
                1,
                "Synthetic 1",
                shipment_orders=(
                    ShipmentOrder(
                        "shipment:reserved",
                        "route:farm-town",
                        "commodity:grain",
                        D("50"),
                        "fixture",
                    ),
                ),
            ),
        )
        self.assertEqual(result.shipments[0].dispatched_quantity, D("20"))
        self.assertEqual(result.snapshot.inventories[0].quantity, D("30"))
        self.assertEqual(result.snapshot.inventories[0].reserved_quantity, D("30"))

    def test_production_dispatch_and_consumption_conserve_goods(self):
        model = fixture_model()
        opening = initial_snapshot(model, timeline_id="surface:preview", campaign_ordinal=0, campaign_date="Synthetic 0", ruleset_version="0.1")
        month1 = advance(model, opening, RunPlan(
            1, 1, "Synthetic 1",
            production_orders=(ProductionOrder("recipe:grain", D("1")),),
            shipment_orders=(ShipmentOrder("shipment:1", "route:farm-town", "commodity:grain", D("80"), "fixture"),),
            needs=(Need("site:farm", "commodity:grain", D("20")),),
        ))
        self.assertEqual(month1.shipments[0].dispatched_quantity, D("50"))
        self.assertEqual(month1.shipments[0].shortfall_quantity, D("30"))
        self.assertEqual(dict(month1.conservation)["commodity:grain"], D("0"))
        self.assertEqual(month1.snapshot.inventories[0].quantity, D("30"))
        self.assertEqual(month1.snapshot.transit[0].quantity, D("50"))

        month2 = advance(model, month1.snapshot, RunPlan(
            2, 2, "Synthetic 2", needs=(Need("site:town", "commodity:grain", D("40")),),
        ))
        positions = {(p.site_id, p.commodity_id): p.quantity for p in month2.snapshot.inventories}
        self.assertEqual(positions[("site:farm", "commodity:grain")], D("30"))
        self.assertEqual(positions[("site:town", "commodity:grain")], D("10"))
        self.assertFalse(month2.snapshot.transit)
        self.assertEqual(dict(month2.conservation)["commodity:grain"], D("0"))

    def test_shipment_does_not_arrive_in_dispatch_period(self):
        model = fixture_model()
        opening = initial_snapshot(
            model,
            timeline_id="surface:preview", campaign_date="Synthetic 0", ruleset_version="0.1",
            campaign_ordinal=0,
            inventories=(InventoryPosition("site:farm", "commodity:grain", D("50")),),
        )
        result = advance(model, opening, RunPlan(
            1, 1, "Synthetic 1",
            shipment_orders=(ShipmentOrder("shipment:1", "route:farm-town", "commodity:grain", D("50"), "fixture"),),
            needs=(Need("site:town", "commodity:grain", D("40")),),
        ))
        self.assertEqual(result.needs[0].consumed_quantity, D("0"))
        self.assertEqual(result.needs[0].shortage_quantity, D("40"))

    def test_lower_supply_cannot_lower_shortage_price(self):
        model = fixture_model()
        def price_with_stock(stock):
            opening = initial_snapshot(
                model,
                timeline_id="surface:preview", campaign_date="Synthetic 0", ruleset_version="0.1",
                campaign_ordinal=0,
                inventories=(InventoryPosition("site:town", "commodity:grain", D(stock)),),
            )
            result = advance(model, opening, RunPlan(1, 1, "Synthetic 1", needs=(Need("site:town", "commodity:grain", D("100")),)))
            return result.snapshot.prices[0].amount
        self.assertGreater(price_with_stock("25"), price_with_stock("50"))

    def test_identical_replay_has_identical_snapshot_hash(self):
        model = fixture_model()
        opening = initial_snapshot(model, timeline_id="surface:preview", campaign_ordinal=0, campaign_date="Synthetic 0", ruleset_version="0.1")
        plan = RunPlan(1, 1, "Synthetic 1", production_orders=(ProductionOrder("recipe:grain", D("1")),))
        first = advance(model, opening, plan)
        second = advance(model, opening, plan)
        self.assertEqual(first.snapshot.state_hash, second.snapshot.state_hash)
        self.assertEqual(first, second)

    def test_campaign_ordinal_must_advance(self):
        model = fixture_model()
        opening = initial_snapshot(model, timeline_id="surface:preview", campaign_ordinal=0, campaign_date="Synthetic 0", ruleset_version="0.1")
        first = advance(model, opening, RunPlan(1, 1, "Synthetic 1"))
        with self.assertRaisesRegex(ValueError, "campaign ordinal"):
            advance(model, first.snapshot, RunPlan(2, 1, "Synthetic 1 again"))

    def test_authorizing_event_cannot_be_applied_twice(self):
        model = fixture_model()
        opening, store = empty_actual_opening(model)
        event = authority_event()
        store.append(event)
        assignment = SimulationAssignment(
            "entity:farm", "actual", 1, SimulationMode.STOCK_FLOW, "fixture:mode"
        )
        first = advance(model, opening, RunPlan(
            1, 1, "Synthetic 1",
            production_orders=(ProductionOrder("recipe:grain", D("1"), event.event_id),),
            authorizing_events=(event,), simulation_assignments=(assignment,),
        ), event_store=store)
        with self.assertRaisesRegex(ValueError, "already applied"):
            advance(model, first.snapshot, RunPlan(
                2, 2, "Synthetic 2",
                production_orders=(ProductionOrder("recipe:grain", D("1"), event.event_id),),
                authorizing_events=(event,),
            ), event_store=store)

    def test_reversed_event_cannot_authorize_actual_mutation(self):
        model = fixture_model()
        opening, store = empty_actual_opening(model)
        original = authority_event(key="fixture:corrected-production")
        correction = EventEnvelope.create(
            source_event_key="fixture:corrected-production", event_revision=2,
            timeline_id="actual", model_version=model.model_version,
            campaign_date=CampaignDate(1, "Synthetic 1"), phase="production",
            sequence=1, authority=Authority.CAMPAIGN_RESOLUTION,
            temporal_state=TemporalState.CURRENT,
            resolution_status=ResolutionStatus.RESOLVED,
            source_ref="fixture:correction", event_type="stock.production",
            subject_entity_id="entity:farm", subject_site_id="site:farm",
            payload={"recipe_id": "recipe:grain", "requested_batches": D("2")},
            reverses_event_id=original.event_id,
        )
        store.append(original)
        store.append(correction)
        assignment = SimulationAssignment(
            "entity:farm", "actual", 1, SimulationMode.STOCK_FLOW, "fixture:mode"
        )
        with self.assertRaisesRegex(ValueError, "not accepted"):
            advance(model, opening, RunPlan(
                1, 1, "Synthetic 1",
                production_orders=(ProductionOrder(
                    "recipe:grain", D("1"), original.event_id
                ),),
                authorizing_events=(original,), simulation_assignments=(assignment,),
            ), event_store=store)

    def test_full_event_provenance_changes_replay_hash(self):
        model = fixture_model()
        opening = initial_snapshot(
            model, timeline_id="surface:preview", campaign_ordinal=0,
            campaign_date="Synthetic 0", ruleset_version="0.1",
        )
        first = authority_event(key="fixture:provenance", source_ref="fixture:A")
        second = authority_event(
            key="fixture:provenance", source_ref="fixture:B",
            authority=Authority.USER_RULING,
        )
        self.assertEqual(first.event_id, second.event_id)
        self.assertEqual(first.payload_hash, second.payload_hash)
        self.assertNotEqual(first.integrity_hash, second.integrity_hash)
        first_result = advance(model, opening, RunPlan(
            1, 1, "Synthetic 1", authorizing_events=(first,)
        ))
        second_result = advance(model, opening, RunPlan(
            1, 1, "Synthetic 1", authorizing_events=(second,)
        ))
        self.assertNotEqual(first_result.snapshot.input_hash, second_result.snapshot.input_hash)
        self.assertNotEqual(first_result.snapshot.state_hash, second_result.snapshot.state_hash)

    def test_actual_authority_requires_stock_type_and_matching_model(self):
        model = fixture_model()
        opening, store = empty_actual_opening(model)
        assignment = SimulationAssignment(
            "entity:farm", "actual", 1, SimulationMode.STOCK_FLOW, "fixture:mode"
        )
        wrong_type = authority_event(
            key="fixture:wrong-type", event_type="narrative.victory"
        )
        store.append(wrong_type)
        with self.assertRaisesRegex(ValueError, "stock event type"):
            advance(model, opening, RunPlan(
                1, 1, "Synthetic 1",
                production_orders=(ProductionOrder(
                    "recipe:grain", D("1"), wrong_type.event_id
                ),),
                authorizing_events=(wrong_type,),
                simulation_assignments=(assignment,),
            ), event_store=store)

        wrong_model = EventEnvelope.create(
            source_event_key="fixture:wrong-model", event_revision=1,
            timeline_id="actual", model_version="unrelated-model-999",
            campaign_date=CampaignDate(1, "Synthetic 1"), phase="production",
            sequence=1, authority=Authority.CAMPAIGN_RESOLUTION,
            temporal_state=TemporalState.CURRENT,
            resolution_status=ResolutionStatus.RESOLVED,
            source_ref="fixture:wrong-model", event_type="stock.production",
            subject_entity_id="entity:farm", subject_site_id="site:farm",
            payload={"recipe_id": "recipe:grain", "requested_batches": D("1")},
        )
        store.append(wrong_model)
        with self.assertRaisesRegex(ValueError, "model version"):
            advance(model, opening, RunPlan(
                1, 1, "Synthetic 1",
                production_orders=(ProductionOrder(
                    "recipe:grain", D("1"), wrong_model.event_id
                ),),
                authorizing_events=(wrong_model,),
                simulation_assignments=(assignment,),
            ), event_store=store)

        extra_payload = authority_event(
            key="fixture:extra-payload",
            payload={
                "recipe_id": "recipe:grain", "requested_batches": D("1"),
                "unmodeled_output_tons": "999",
            },
        )
        store.append(extra_payload)
        with self.assertRaisesRegex(ValueError, "exact stock contract"):
            advance(model, opening, RunPlan(
                1, 1, "Synthetic 1",
                production_orders=(ProductionOrder(
                    "recipe:grain", D("1"), extra_payload.event_id
                ),),
                authorizing_events=(extra_payload,),
                simulation_assignments=(assignment,),
            ), event_store=store)

        wrong_site = authority_event(
            key="fixture:wrong-site", site_id="site:town"
        )
        store.append(wrong_site)
        with self.assertRaisesRegex(ValueError, "site does not match"):
            advance(model, opening, RunPlan(
                1, 1, "Synthetic 1",
                production_orders=(ProductionOrder(
                    "recipe:grain", D("1"), wrong_site.event_id
                ),),
                authorizing_events=(wrong_site,),
                simulation_assignments=(assignment,),
            ), event_store=store)

    def test_same_recipe_order_is_deterministic(self):
        model = fixture_model()
        opening = initial_snapshot(
            model, timeline_id="surface:preview", campaign_ordinal=0,
            campaign_date="Synthetic 0", ruleset_version="0.1",
        )
        first_order = ProductionOrder("recipe:grain", D("0.75"), "event:z")
        second_order = ProductionOrder("recipe:grain", D("0.50"), "event:a")
        first = advance(model, opening, RunPlan(
            1, 1, "Synthetic 1", production_orders=(first_order, second_order)
        ))
        second = advance(model, opening, RunPlan(
            1, 1, "Synthetic 1", production_orders=(second_order, first_order)
        ))
        self.assertEqual(first, second)

    def test_shipment_id_cannot_be_reused_after_arrival(self):
        model = fixture_model()
        opening = initial_snapshot(
            model,
            timeline_id="surface:preview", campaign_date="Synthetic 0", ruleset_version="0.1",
            campaign_ordinal=0,
            inventories=(InventoryPosition("site:farm", "commodity:grain", D("100")),),
        )
        first = advance(model, opening, RunPlan(
            1, 1, "Synthetic 1",
            shipment_orders=(ShipmentOrder("shipment:x", "route:farm-town", "commodity:grain", D("10"), "fixture"),),
        ))
        second = advance(model, first.snapshot, RunPlan(2, 2, "Synthetic 2"))
        with self.assertRaisesRegex(ValueError, "duplicate shipment"):
            advance(model, second.snapshot, RunPlan(
                3, 3, "Synthetic 3",
                shipment_orders=(ShipmentOrder("shipment:x", "route:farm-town", "commodity:grain", D("10"), "fixture"),),
            ))

    def test_recipe_period_cap_applies_across_multiple_orders(self):
        model = fixture_model()
        opening = initial_snapshot(
            model, timeline_id="surface:preview", campaign_ordinal=0,
            campaign_date="Synthetic 0", ruleset_version="0.1"
        )
        result = advance(model, opening, RunPlan(
            1, 1, "Synthetic 1",
            production_orders=(
                ProductionOrder("recipe:grain", D("1")),
                ProductionOrder("recipe:grain", D("1")),
            ),
        ))
        self.assertEqual(sum((item.actual_batches for item in result.production), D("0")), D("1"))

    def test_recipe_is_constrained_by_input_and_labor(self):
        model = EconomyModel(
            commodities=(
                Commodity("commodity:ore", "Ore", "ton", D("2")),
                Commodity("commodity:tools", "Tools", "crate", D("5")),
            ),
            sites=(Site("site:works", "Works", D("5")),),
            recipes=(Recipe(
                "recipe:tools", "site:works", "entity:works",
                (("commodity:ore", D("4")),), (("commodity:tools", D("1")),),
                D("2"), D("10"),
            ),),
            routes=(),
        )
        input_limited = initial_snapshot(
            model, timeline_id="surface:preview", campaign_ordinal=0,
            campaign_date="Synthetic 0", ruleset_version="0.1",
            inventories=(InventoryPosition("site:works", "commodity:ore", D("6")),),
        )
        result = advance(model, input_limited, RunPlan(
            1, 1, "Synthetic 1",
            production_orders=(ProductionOrder("recipe:tools", D("10")),),
        ))
        self.assertEqual(result.production[0].actual_batches, D("1.5"))

        labor_limited = initial_snapshot(
            model, timeline_id="surface:preview", campaign_ordinal=0,
            campaign_date="Synthetic 0", ruleset_version="0.1",
            inventories=(InventoryPosition("site:works", "commodity:ore", D("100")),),
        )
        result = advance(model, labor_limited, RunPlan(
            1, 1, "Synthetic 1",
            production_orders=(ProductionOrder("recipe:tools", D("10")),),
        ))
        self.assertEqual(result.production[0].actual_batches, D("2.5"))
        self.assertEqual(dict(result.labor_used)["site:works"], D("5"))

    def test_nonzero_route_loss_is_explicit_and_conserved(self):
        model = fixture_model()
        lossy = EconomyModel(
            model.commodities,
            model.sites,
            model.recipes,
            (Route(
                "route:farm-town", "site:farm", "site:town", "commodity:grain",
                D("50"), 1, D("0.10"),
            ),),
        )
        opening = initial_snapshot(
            lossy, timeline_id="surface:preview", campaign_ordinal=0,
            campaign_date="Synthetic 0", ruleset_version="0.1",
            inventories=(InventoryPosition("site:farm", "commodity:grain", D("50")),),
        )
        dispatched = advance(lossy, opening, RunPlan(
            1, 1, "Synthetic 1",
            shipment_orders=(ShipmentOrder(
                "shipment:loss", "route:farm-town", "commodity:grain", D("50"), "fixture"
            ),),
        ))
        arrived = advance(lossy, dispatched.snapshot, RunPlan(2, 2, "Synthetic 2"))
        town_stock = next(item.quantity for item in arrived.snapshot.inventories if item.site_id == "site:town")
        self.assertEqual(town_stock, D("45.00"))
        self.assertEqual(dict(arrived.conservation)["commodity:grain"], D("0.00"))


if __name__ == "__main__":
    unittest.main()
