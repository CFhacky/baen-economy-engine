from __future__ import annotations

from decimal import Context, Decimal, localcontext
from pathlib import Path
import sys
import unittest


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from baen_economy.regional_market import (  # noqa: E402
    DemandBid,
    RegionalMarketError,
    SupplyOffer,
    simulate_market_month,
)
from baen_economy.regional_transport import (  # noqa: E402
    RegionalTransportError,
    RouteCostTerms,
    dispatch_for_delivery,
)
from baen_economy.stockflow import (  # noqa: E402
    Commodity,
    EconomyModel,
    InventoryPosition,
    PricePosition,
    Route,
    Site,
    initial_snapshot,
)


D = Decimal


def _assert_no_floats(test: unittest.TestCase, value: object) -> None:
    if isinstance(value, float):
        test.fail(f"binary float leaked into regional market payload: {value!r}")
    if isinstance(value, dict):
        for nested in value.values():
            _assert_no_floats(test, nested)
    elif isinstance(value, (tuple, list)):
        for nested in value:
            _assert_no_floats(test, nested)


class RegionalMarketScenarioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = EconomyModel(
            commodities=(
                Commodity(
                    "commodity:grain",
                    "Scenario Grain",
                    "ton",
                    D("3"),
                    elasticity=D("0.5"),
                    floor_factor=D("0.5"),
                    ceiling_factor=D("2"),
                ),
            ),
            sites=(
                Site("site:farm", "Scenario Farm", D("0")),
                Site("site:town", "Scenario Town", D("0")),
            ),
            recipes=(),
            routes=(
                Route(
                    "route:farm-town",
                    "site:farm",
                    "site:town",
                    "commodity:grain",
                    D("60"),
                    1,
                    D("0.1"),
                ),
            ),
        )
        self.opening = initial_snapshot(
            self.model,
            timeline_id="scenario:regional-market",
            campaign_ordinal=0,
            campaign_date="Scenario Month 0",
            ruleset_version="regional-market-test-v1",
            inventories=(
                InventoryPosition("site:farm", "commodity:grain", D("100")),
                InventoryPosition("site:town", "commodity:grain", D("10")),
            ),
            prices=(
                PricePosition("site:farm", "commodity:grain", D("2")),
                PricePosition("site:town", "commodity:grain", D("3")),
            ),
        )
        self.offer = SupplyOffer(
            "offer:farm-grain",
            "entity:scenario-farm",
            "site:farm",
            "commodity:grain",
            D("100"),
            "fixture:scenario-input:regional-market",
        )
        self.demand = DemandBid(
            "demand:town-grain",
            "entity:scenario-town-households",
            "site:town",
            "commodity:grain",
            D("100"),
            "fixture:scenario-input:regional-market",
        )
        self.route_cost = RouteCostTerms(
            "route:farm-town",
            D("0.5"),
            carrier_entity_id="entity:scenario-carrier",
        )

    def simulate(self):
        return simulate_market_month(
            self.model,
            self.opening,
            period_index=1,
            campaign_ordinal=1,
            campaign_date="Scenario Month 1",
            supply_offers=(self.offer,),
            demands=(self.demand,),
            route_costs=(self.route_cost,),
            source_ref="fixture:scenario-input:regional-market",
        )

    def test_cross_location_trade_exposes_capacity_loss_cost_shortage_and_price(self) -> None:
        result = self.simulate()
        payload = result.to_payload()

        self.assertEqual(payload["schema"], "tnp.economy.regional-market-month/1")
        self.assertEqual(payload["authority"], "scenario_input")
        self.assertFalse(payload["canonical"])
        self.assertFalse(payload["campaign_time_advanced"])
        self.assertEqual(payload["ledger_postings_created"], 0)
        self.assertEqual(payload["notion_writes_attempted"], 0)

        transport = payload["transport"]
        self.assertEqual(D(transport["quantity_moved"]), D("60"))
        self.assertEqual(D(transport["capacity"]), D("60"))
        usage = transport["route_usage"][0]
        self.assertEqual(D(usage["remaining_capacity"]), D("0"))
        self.assertEqual(D(usage["expected_loss_quantity"]), D("6"))
        self.assertEqual(D(usage["expected_delivered_quantity"]), D("54"))
        self.assertEqual(D(usage["transport_cost_gp"]), D("30"))

        market = payload["market"]
        self.assertEqual(D(market["shortage_quantity"]), D("90"))
        self.assertEqual(D(market["price_before"]), D("3"))
        self.assertEqual(D(market["price_after"]), D("4.350"))
        self.assertGreater(D(market["price_after"]), D(market["price_before"]))
        demand = payload["demand_receipts"][0]
        self.assertEqual(D(demand["requested_quantity"]), D("100"))
        self.assertEqual(D(demand["consumed_quantity"]), D("10"))
        self.assertEqual(D(demand["shortage_quantity"]), D("90"))

        trade = payload["trade_receipts"][0]
        self.assertEqual(trade["seller_entity_id"], "entity:scenario-farm")
        self.assertEqual(trade["buyer_entity_id"], "entity:scenario-town-households")
        self.assertEqual(trade["carrier_entity_id"], "entity:scenario-carrier")
        self.assertEqual(D(trade["goods_value_gp"]), D("120"))
        self.assertEqual(D(trade["transport_cost_gp"]), D("30"))
        self.assertEqual(D(trade["buyer_total_gp"]), D("150"))
        self.assertEqual(trade["delivery_status"], "in_transit")
        self.assertEqual(trade["settlement_status"], "pending_delivery")
        self.assertEqual(trade["arrival_period_index"], 2)

        state = payload["next_market_state"]
        self.assertEqual(state["period_index"], 1)
        self.assertEqual(len(state["transit"]), 1)
        self.assertEqual(D(state["transit"][0]["dispatched_quantity"]), D("60"))
        self.assertEqual(payload["conservation"], [
            {"commodity_id": "commodity:grain", "residual_quantity": "0"}
        ])
        result.snapshot.verify()
        _assert_no_floats(self, payload)

    def test_next_month_arrival_applies_the_expected_physical_loss(self) -> None:
        first = self.simulate()
        second = simulate_market_month(
            self.model,
            first.snapshot,
            period_index=2,
            campaign_ordinal=2,
            campaign_date="Scenario Month 2",
            supply_offers=(),
            demands=(),
            route_costs=(),
            source_ref="fixture:scenario-input:regional-market-month-2",
        )
        inventory = {
            (item.site_id, item.commodity_id): item.quantity
            for item in second.snapshot.inventories
        }
        self.assertEqual(inventory[("site:farm", "commodity:grain")], D("40"))
        self.assertEqual(inventory[("site:town", "commodity:grain")], D("54"))
        self.assertEqual(second.snapshot.transit, ())
        self.assertIn(
            ("commodity:grain", D("0")),
            second.run_result.conservation,
        )
        route_losses = [
            flow
            for flow in second.run_result.flows
            if flow.kind.value == "route_loss"
        ]
        self.assertEqual(len(route_losses), 1)
        self.assertEqual(route_losses[0].quantity, D("6"))

    def test_result_is_deterministic_under_input_order_and_ambient_context(self) -> None:
        second_offer = SupplyOffer(
            "offer:farm-grain-z",
            "entity:scenario-farm-z",
            "site:farm",
            "commodity:grain",
            D("40"),
            "fixture:scenario-input:regional-market",
        )
        first = simulate_market_month(
            self.model,
            self.opening,
            period_index=1,
            campaign_ordinal=1,
            campaign_date="Scenario Month 1",
            supply_offers=(second_offer, self.offer),
            demands=(self.demand,),
            route_costs=(self.route_cost,),
            source_ref="fixture:scenario-input:regional-market",
        )
        with localcontext(Context(prec=4)):
            second = simulate_market_month(
                self.model,
                self.opening,
                period_index=1,
                campaign_ordinal=1,
                campaign_date="Scenario Month 1",
                supply_offers=(self.offer, second_offer),
                demands=(self.demand,),
                route_costs=(self.route_cost,),
                source_ref="fixture:scenario-input:regional-market",
            )
        self.assertEqual(first, second)
        self.assertEqual(first.to_payload(), second.to_payload())

    def test_local_trade_is_delivered_and_cash_settled_without_a_route(self) -> None:
        local_model = EconomyModel(
            commodities=self.model.commodities,
            sites=(Site("site:town", "Scenario Town", D("0")),),
            recipes=(),
            routes=(),
        )
        opening = initial_snapshot(
            local_model,
            timeline_id="scenario:local-market",
            campaign_ordinal=0,
            campaign_date="Scenario Month 0",
            ruleset_version="regional-market-test-v1",
            inventories=(
                InventoryPosition("site:town", "commodity:grain", D("20")),
            ),
            prices=(PricePosition("site:town", "commodity:grain", D("3")),),
        )
        result = simulate_market_month(
            local_model,
            opening,
            period_index=1,
            campaign_ordinal=1,
            campaign_date="Scenario Month 1",
            supply_offers=(
                SupplyOffer(
                    "offer:local-grain",
                    "entity:local-granary",
                    "site:town",
                    "commodity:grain",
                    D("20"),
                    "fixture:scenario-input:local-market",
                ),
            ),
            demands=(
                DemandBid(
                    "demand:local-grain",
                    "entity:local-households",
                    "site:town",
                    "commodity:grain",
                    D("15"),
                    "fixture:scenario-input:local-market",
                ),
            ),
            route_costs=(),
            source_ref="fixture:scenario-input:local-market",
        )
        self.assertEqual(result.demand_receipts[0].shortage_quantity, D("0"))
        self.assertEqual(result.snapshot.inventories[0].quantity, D("5"))
        self.assertEqual(result.route_usage, ())
        self.assertEqual(len(result.trade_receipts), 1)
        trade = result.trade_receipts[0]
        self.assertIsNone(trade.route_id)
        self.assertEqual(trade.delivered_quantity, D("15"))
        self.assertEqual(trade.delivery_status, "delivered")
        self.assertEqual(trade.settlement_status, "settled_cash")
        self.assertEqual(trade.buyer_total_gp, D("45"))

    def test_own_inventory_consumption_is_not_mislabeled_as_a_cash_sale(self) -> None:
        local_model = EconomyModel(
            commodities=self.model.commodities,
            sites=(Site("site:town", "Scenario Town", D("0")),),
            recipes=(),
            routes=(),
        )
        opening = initial_snapshot(
            local_model,
            timeline_id="scenario:self-consumption",
            campaign_ordinal=0,
            campaign_date="Scenario Month 0",
            ruleset_version="regional-market-test-v1",
            inventories=(
                InventoryPosition("site:town", "commodity:grain", D("20")),
            ),
            prices=(PricePosition("site:town", "commodity:grain", D("3")),),
        )
        result = simulate_market_month(
            local_model,
            opening,
            period_index=1,
            campaign_ordinal=1,
            campaign_date="Scenario Month 1",
            supply_offers=(
                SupplyOffer(
                    "offer:self",
                    "entity:same-owner",
                    "site:town",
                    "commodity:grain",
                    D("20"),
                    "fixture:scenario-input:self-consumption",
                ),
            ),
            demands=(
                DemandBid(
                    "demand:self",
                    "entity:same-owner",
                    "site:town",
                    "commodity:grain",
                    D("15"),
                    "fixture:scenario-input:self-consumption",
                ),
            ),
            route_costs=(),
            source_ref="fixture:scenario-input:self-consumption",
        )
        self.assertEqual(result.demand_receipts[0].consumed_quantity, D("15"))
        self.assertEqual(result.trade_receipts, ())

    def test_need_priority_allocates_scarce_local_stock_before_lower_priority(self) -> None:
        demands = (
            DemandBid(
                "demand:low-priority",
                "entity:low-priority",
                "site:town",
                "commodity:grain",
                D("8"),
                "fixture:scenario-input:priority",
                priority=100,
            ),
            DemandBid(
                "demand:high-priority",
                "entity:high-priority",
                "site:town",
                "commodity:grain",
                D("8"),
                "fixture:scenario-input:priority",
                priority=10,
            ),
        )
        result = simulate_market_month(
            self.model,
            self.opening,
            period_index=1,
            campaign_ordinal=1,
            campaign_date="Scenario Month 1",
            supply_offers=(),
            demands=demands,
            route_costs=(),
            source_ref="fixture:scenario-input:priority",
        )
        by_id = {item.demand_id: item for item in result.demand_receipts}
        self.assertEqual(by_id["demand:high-priority"].consumed_quantity, D("8"))
        self.assertEqual(by_id["demand:high-priority"].shortage_quantity, D("0"))
        self.assertEqual(by_id["demand:low-priority"].consumed_quantity, D("2"))
        self.assertEqual(by_id["demand:low-priority"].shortage_quantity, D("6"))

    def test_price_response_obeys_configured_ceiling(self) -> None:
        capped_model = EconomyModel(
            commodities=(
                Commodity(
                    "commodity:grain",
                    "Scenario Grain",
                    "ton",
                    D("3"),
                    elasticity=D("1"),
                    floor_factor=D("0.8"),
                    ceiling_factor=D("1.2"),
                ),
            ),
            sites=(Site("site:town", "Scenario Town", D("0")),),
            recipes=(),
            routes=(),
        )
        opening = initial_snapshot(
            capped_model,
            timeline_id="scenario:capped-price",
            campaign_ordinal=0,
            campaign_date="Scenario Month 0",
            ruleset_version="regional-market-test-v1",
            prices=(PricePosition("site:town", "commodity:grain", D("3")),),
        )
        result = simulate_market_month(
            capped_model,
            opening,
            period_index=1,
            campaign_ordinal=1,
            campaign_date="Scenario Month 1",
            supply_offers=(),
            demands=(
                DemandBid(
                    "demand:capped",
                    "entity:households",
                    "site:town",
                    "commodity:grain",
                    D("100"),
                    "fixture:scenario-input:capped-price",
                ),
            ),
            route_costs=(),
            source_ref="fixture:scenario-input:capped-price",
        )
        self.assertEqual(result.demand_receipts[0].price_after_gp_per_unit, D("3.6"))

    def test_lower_landed_cost_route_is_allocated_first(self) -> None:
        model = EconomyModel(
            commodities=self.model.commodities,
            sites=(
                Site("site:cheap", "Cheap Origin", D("0")),
                Site("site:expensive", "Expensive Origin", D("0")),
                Site("site:town", "Scenario Town", D("0")),
            ),
            recipes=(),
            routes=(
                Route(
                    "route:a-expensive",
                    "site:expensive",
                    "site:town",
                    "commodity:grain",
                    D("20"),
                    1,
                    D("0"),
                ),
                Route(
                    "route:z-cheap",
                    "site:cheap",
                    "site:town",
                    "commodity:grain",
                    D("20"),
                    1,
                    D("0"),
                ),
            ),
        )
        opening = initial_snapshot(
            model,
            timeline_id="scenario:route-choice",
            campaign_ordinal=0,
            campaign_date="Scenario Month 0",
            ruleset_version="regional-market-test-v1",
            inventories=(
                InventoryPosition("site:cheap", "commodity:grain", D("20")),
                InventoryPosition("site:expensive", "commodity:grain", D("20")),
            ),
            prices=(
                PricePosition("site:cheap", "commodity:grain", D("2")),
                PricePosition("site:expensive", "commodity:grain", D("2")),
                PricePosition("site:town", "commodity:grain", D("3")),
            ),
        )
        result = simulate_market_month(
            model,
            opening,
            period_index=1,
            campaign_ordinal=1,
            campaign_date="Scenario Month 1",
            supply_offers=(
                SupplyOffer(
                    "offer:cheap",
                    "entity:cheap",
                    "site:cheap",
                    "commodity:grain",
                    D("20"),
                    "fixture:scenario-input:route-choice",
                ),
                SupplyOffer(
                    "offer:expensive",
                    "entity:expensive",
                    "site:expensive",
                    "commodity:grain",
                    D("20"),
                    "fixture:scenario-input:route-choice",
                ),
            ),
            demands=(
                DemandBid(
                    "demand:town",
                    "entity:town",
                    "site:town",
                    "commodity:grain",
                    D("10"),
                    "fixture:scenario-input:route-choice",
                ),
            ),
            route_costs=(
                RouteCostTerms("route:a-expensive", D("3")),
                RouteCostTerms("route:z-cheap", D("0.5")),
            ),
            source_ref="fixture:scenario-input:route-choice",
        )
        self.assertEqual(len(result.trade_receipts), 1)
        self.assertEqual(result.trade_receipts[0].route_id, "route:z-cheap")
        self.assertEqual(result.trade_receipts[0].dispatched_quantity, D("10"))


class RegionalMarketValidationTests(unittest.TestCase):
    def test_numeric_inputs_reject_binary_float_boolean_and_nonfinite_values(self) -> None:
        with self.assertRaisesRegex(RegionalMarketError, "finite Decimal"):
            SupplyOffer(
                "offer:x",
                "entity:x",
                "site:x",
                "commodity:x",
                1.0,
                "fixture:scenario-input",
            )
        with self.assertRaisesRegex(RegionalMarketError, "finite Decimal"):
            DemandBid(
                "demand:x",
                "entity:x",
                "site:x",
                "commodity:x",
                D("NaN"),
                "fixture:scenario-input",
            )
        with self.assertRaisesRegex(RegionalTransportError, "finite Decimal"):
            RouteCostTerms("route:x", True)
        with self.assertRaisesRegex(RegionalMarketError, "positive"):
            DemandBid(
                "demand:zero",
                "entity:x",
                "site:x",
                "commodity:x",
                D("0"),
                "fixture:scenario-input",
            )

    def test_scenario_inputs_cannot_be_relabelled_canonical(self) -> None:
        with self.assertRaisesRegex(RegionalMarketError, "non-canonical"):
            SupplyOffer(
                "offer:x",
                "entity:x",
                "site:x",
                "commodity:x",
                D("1"),
                "fixture:scenario-input",
                canonical=True,
            )
        with self.assertRaisesRegex(RegionalTransportError, "non-canonical"):
            RouteCostTerms(
                "route:x",
                D("1"),
                authority="campaign_resolution",
            )

    def test_dispatch_planning_respects_stock_capacity_and_loss(self) -> None:
        route = Route(
            "route:x",
            "site:a",
            "site:b",
            "commodity:grain",
            D("50"),
            1,
            D("0.2"),
        )
        limited = dispatch_for_delivery(
            route,
            D("100"),
            available_stock=D("40"),
            remaining_capacity=D("30"),
        )
        self.assertEqual(limited, D("30"))
        targeted = dispatch_for_delivery(
            route,
            D("20"),
            available_stock=D("40"),
            remaining_capacity=D("30"),
        )
        self.assertEqual(targeted, D("25"))


if __name__ == "__main__":
    unittest.main()
