from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, getcontext
import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from baen_economy.regional_domain import (  # noqa: E402
    CommoditySpec,
    InventoryLot,
    LaborPool,
    LaborRequirement,
    MaterialRequirement,
    ProductionOrder,
    ProductionRecipe,
    RegionalDomainError,
    RegionalState,
    canonical_payload_hash,
    regional_state_from_dict,
)
from baen_economy.regional_production import (  # noqa: E402
    UnresolvedProductionInput,
    advance_production_month,
    receipts_from_stockflow_run,
)
from baen_economy.stockflow import (  # noqa: E402
    Commodity,
    EconomyModel,
    InventoryPosition,
    ProductionOrder as KernelProductionOrder,
    Recipe,
    RunPlan,
    Site,
    advance,
    initial_snapshot,
)


D = Decimal


def brickworks_state(
    *,
    clay=D("2000"),
    bricks=D("0"),
    workers=D("12"),
    worker_days=D("240"),
    wage=D("0.50"),
    extra_inventory=(),
):
    commodities = [
        CommoditySpec("clay", "Prepared clay", "ton", "scenario:brickworks"),
        CommoditySpec("brick", "Fired brick", "brick", "scenario:brickworks"),
    ]
    if extra_inventory:
        commodities.append(
            CommoditySpec("grain", "Stored grain", "bushel", "scenario:unresolved")
        )
    return RegionalState(
        month_index=0,
        commodities=tuple(commodities),
        inventories=(
            InventoryLot(
                "baen-brickworks",
                "neverwinter-brickworks",
                "clay",
                clay,
                "scenario:opening",
            ),
            InventoryLot(
                "baen-brickworks",
                "neverwinter-brickworks",
                "brick",
                bricks,
                "scenario:opening",
            ),
            *extra_inventory,
        ),
        labor_pools=(
            LaborPool(
                "baen-brickworks",
                "neverwinter-brickworks",
                "kiln-workers",
                workers,
                worker_days,
                wage,
                "scenario:staffing",
            ),
        ),
    )


def brick_recipe(
    *,
    clay_per_batch=D("1000"),
    bricks_per_batch=D("37500"),
    labor_per_batch=D("100"),
    max_batches=D("2"),
):
    return ProductionRecipe(
        recipe_id="fire-bricks",
        operator_id="baen-brickworks",
        site_id="neverwinter-brickworks",
        inputs=(MaterialRequirement("clay", clay_per_batch),),
        outputs=(MaterialRequirement("brick", bricks_per_batch),),
        labor_requirements=(LaborRequirement("kiln-workers", labor_per_batch),),
        max_batches_per_month=max_batches,
        source_ref="scenario:brick-recipe",
        priority=10,
    )


def quantity(state, commodity_id):
    return next(
        item.quantity for item in state.inventories if item.commodity_id == commodity_id
    )


class RegionalProductionTests(unittest.TestCase):
    def test_full_month_consumes_inputs_produces_outputs_pays_labor_and_advances(self):
        state = brickworks_state()
        result = advance_production_month(
            state,
            (brick_recipe(),),
            (ProductionOrder("fire-bricks", D("2")),),
        )

        self.assertEqual(result.opening_month_index, 0)
        self.assertEqual(result.closing_month_index, 1)
        self.assertEqual(result.next_state.month_index, 1)
        self.assertEqual(quantity(result.next_state, "clay"), D("0"))
        self.assertEqual(quantity(result.next_state, "brick"), D("75000"))

        run = result.production[0]
        self.assertEqual(run.requested_batches, D("2"))
        self.assertEqual(run.actual_batches, D("2"))
        self.assertEqual(run.input_consumed, D("2000"))
        self.assertEqual(run.output_produced, D("75000"))
        self.assertEqual(run.worker_days, D("200"))
        self.assertEqual(run.workers, D("10"))
        self.assertEqual(run.payroll, D("100.00"))
        self.assertEqual(run.limiting_factors, ())

        payload = result.to_dict()
        self.assertEqual(payload["production"]["input_consumed"], "2000")
        self.assertEqual(payload["production"]["output_produced"], "75000")
        self.assertEqual(payload["labor"]["workers"], "10")
        self.assertEqual(payload["labor"]["payroll"], "100.00")
        self.assertEqual(payload["payroll_events"][0]["kind"], "payroll")
        self.assertEqual(payload["payroll_events"][0]["amount"], "100.00")
        self.assertNotEqual(result.opening_state_hash, result.closing_state_hash)
        self.assertEqual(result.opening_state_hash, state.state_hash)
        self.assertEqual(result.closing_state_hash, result.next_state.state_hash)
        self.assertEqual(len(result.kernel_opening_hash), 64)
        self.assertEqual(len(result.kernel_closing_hash), 64)

    def test_every_material_conservation_residual_is_exact_zero(self):
        result = advance_production_month(
            brickworks_state(),
            (brick_recipe(),),
            (ProductionOrder("fire-bricks", D("2")),),
        )
        by_commodity = {item.commodity_id: item for item in result.conservation}

        self.assertEqual(by_commodity["clay"].opening_known, D("2000"))
        self.assertEqual(by_commodity["clay"].inputs_consumed, D("2000"))
        self.assertEqual(by_commodity["clay"].closing_known, D("0"))
        self.assertEqual(by_commodity["brick"].outputs_produced, D("75000"))
        self.assertTrue(all(item.residual == D("0") for item in result.conservation))

    def test_production_is_bounded_independently_by_input_labor_and_capacity(self):
        cases = (
            (
                "input",
                brickworks_state(clay=D("1500")),
                brick_recipe(),
                D("1.5"),
                "input:clay",
            ),
            (
                "labor",
                brickworks_state(worker_days=D("120")),
                brick_recipe(),
                D("1.2"),
                "labor:kiln-workers",
            ),
            (
                "capacity",
                brickworks_state(),
                brick_recipe(max_batches=D("1")),
                D("1"),
                "monthly_capacity",
            ),
        )
        for label, state, recipe, expected, factor in cases:
            with self.subTest(label=label):
                result = advance_production_month(
                    state,
                    (recipe,),
                    (ProductionOrder("fire-bricks", D("2")),),
                )
                self.assertEqual(result.production[0].actual_batches, expected)
                self.assertIn(factor, result.production[0].limiting_factors)
                self.assertTrue(all(item.residual == 0 for item in result.conservation))

    def test_shared_material_and_labor_cannot_be_oversubscribed(self):
        state = brickworks_state(clay=D("1000"), worker_days=D("100"))
        first = replace(
            brick_recipe(max_batches=D("1")),
            recipe_id="priority-bricks",
            priority=1,
        )
        second = replace(
            brick_recipe(max_batches=D("1")),
            recipe_id="later-bricks",
            priority=2,
        )
        result = advance_production_month(
            state,
            (second, first),
            (
                ProductionOrder("later-bricks", D("1")),
                ProductionOrder("priority-bricks", D("1")),
            ),
        )
        by_recipe = {item.recipe_id: item for item in result.production}

        self.assertEqual(by_recipe["priority-bricks"].actual_batches, D("1"))
        self.assertEqual(by_recipe["later-bricks"].actual_batches, D("0"))
        self.assertEqual(quantity(result.next_state, "clay"), D("0"))
        self.assertEqual(quantity(result.next_state, "brick"), D("37500"))
        self.assertEqual(result.worker_days, D("100"))
        self.assertTrue(all(item.residual == 0 for item in result.conservation))

    def test_referenced_unknowns_fail_closed_instead_of_becoming_zero(self):
        with self.assertRaisesRegex(UnresolvedProductionInput, "opening_inventory"):
            advance_production_month(
                brickworks_state(clay=None),
                (brick_recipe(),),
                (ProductionOrder("fire-bricks", D("1")),),
            )
        with self.assertRaisesRegex(UnresolvedProductionInput, "quantity_per_batch"):
            advance_production_month(
                brickworks_state(),
                (brick_recipe(clay_per_batch=None),),
                (ProductionOrder("fire-bricks", D("1")),),
            )
        with self.assertRaisesRegex(UnresolvedProductionInput, "wage_gp_per_day"):
            advance_production_month(
                brickworks_state(wage=None),
                (brick_recipe(),),
                (ProductionOrder("fire-bricks", D("1")),),
            )
        with self.assertRaisesRegex(UnresolvedProductionInput, "requested_batches"):
            advance_production_month(
                brickworks_state(),
                (brick_recipe(),),
                (ProductionOrder("fire-bricks", None),),
            )

    def test_unreferenced_unknown_inventory_is_preserved(self):
        unknown = InventoryLot(
            "granary",
            "neverwinter",
            "grain",
            None,
            "canon:quantity-unresolved",
        )
        result = advance_production_month(
            brickworks_state(extra_inventory=(unknown,)),
            (brick_recipe(),),
            (ProductionOrder("fire-bricks", D("1")),),
        )
        preserved = next(
            item for item in result.next_state.inventories if item.commodity_id == "grain"
        )
        self.assertIsNone(preserved.quantity)
        self.assertEqual(preserved.source_ref, "canon:quantity-unresolved")

    def test_state_and_contracts_reject_implicit_numeric_coercion_and_duplicates(self):
        with self.assertRaisesRegex(RegionalDomainError, "finite Decimal"):
            InventoryLot("owner", "site", "clay", 1, "scenario:test")
        with self.assertRaisesRegex(RegionalDomainError, "finite Decimal"):
            MaterialRequirement("clay", 1.0)
        with self.assertRaisesRegex(RegionalDomainError, "immutable tuple"):
            RegionalState(0, [], (), ())

        state = brickworks_state()
        with self.assertRaisesRegex(RegionalDomainError, "duplicate regional inventory"):
            RegionalState(
                month_index=0,
                commodities=state.commodities,
                inventories=(state.inventories[0], state.inventories[0]),
                labor_pools=state.labor_pools,
            )

    def test_results_are_immutable_and_deterministic_across_ambient_decimal_contexts(self):
        state = brickworks_state(clay=D("1500"))
        recipe = brick_recipe()
        order = ProductionOrder("fire-bricks", D("2"))
        original_precision = getcontext().prec
        original_capitals = getcontext().capitals
        try:
            getcontext().prec = 6
            getcontext().capitals = 0
            first = advance_production_month(state, (recipe,), (order,))
            getcontext().prec = 60
            getcontext().capitals = 1
            second = advance_production_month(state, (recipe,), (order,))
        finally:
            getcontext().prec = original_precision
            getcontext().capitals = original_capitals

        self.assertEqual(first.to_dict(), second.to_dict())
        with self.assertRaises(FrozenInstanceError):
            first.next_state.month_index = 9

    def test_persisted_next_state_round_trips_and_tampering_is_rejected(self):
        result = advance_production_month(
            brickworks_state(),
            (brick_recipe(),),
            (ProductionOrder("fire-bricks", D("1")),),
        )
        payload = result.next_state.to_dict()
        reopened = regional_state_from_dict(payload)
        self.assertEqual(reopened, result.next_state)
        self.assertEqual(reopened.state_hash, result.closing_state_hash)

        tampered = dict(payload)
        tampered["month_index"] = 99
        with self.assertRaisesRegex(RegionalDomainError, "hash does not match"):
            regional_state_from_dict(tampered)

        malformed = dict(payload)
        malformed["inventories"] = [dict(item) for item in payload["inventories"]]
        malformed["inventories"][0]["quantity"] = 1
        malformed_body = dict(malformed)
        del malformed_body["state_hash"]
        malformed["state_hash"] = canonical_payload_hash(malformed_body)
        with self.assertRaisesRegex(RegionalDomainError, "decimal string"):
            regional_state_from_dict(malformed)

    def test_public_adapter_translates_one_native_stockflow_run_without_mutation(self):
        model = EconomyModel(
            commodities=(
                Commodity("brick", "Fired brick", "brick", None, market_price_enabled=False),
                Commodity("clay", "Prepared clay", "ton", None, market_price_enabled=False),
            ),
            sites=(Site("works", "Brickworks", D("240")),),
            recipes=(
                Recipe(
                    "fire-bricks",
                    "works",
                    "baen-brickworks",
                    (("clay", D("1000")),),
                    (("brick", D("37500")),),
                    D("100"),
                    D("2"),
                ),
            ),
            routes=(),
        )
        opening = initial_snapshot(
            model,
            timeline_id="regional-preview",
            campaign_ordinal=0,
            campaign_date="month-0",
            ruleset_version="adapter-test/1",
            inventories=(InventoryPosition("works", "clay", D("2000")),),
        )
        native = advance(
            model,
            opening,
            RunPlan(
                period_index=1,
                campaign_ordinal=1,
                campaign_date="month-1",
                production_orders=(KernelProductionOrder("fire-bricks", D("2")),),
            ),
        )
        native_hash_before_adapter = native.snapshot.state_hash
        receipts = receipts_from_stockflow_run(
            native,
            recipes=(brick_recipe(),),
            orders=(ProductionOrder("fire-bricks", D("2")),),
            commodities=brickworks_state().commodities,
            labor_pools=brickworks_state().labor_pools,
        )

        self.assertEqual(receipts[0].input_consumed, D("2000"))
        self.assertEqual(receipts[0].output_produced, D("75000"))
        self.assertEqual(receipts[0].workers, D("10"))
        self.assertEqual(receipts[0].payroll, D("100.00"))
        self.assertEqual(native.snapshot.state_hash, native_hash_before_adapter)


if __name__ == "__main__":
    unittest.main()
