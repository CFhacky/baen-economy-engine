from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from baen_economy.empire_close import EmpireCloseError, close_status, load_close_recovery

class EmpireCloseTests(unittest.TestCase):
    def test_audit_notes_cannot_introduce_extra_authority_classes(self):
        with tempfile.TemporaryDirectory() as td:
            payload = load_close_recovery()
            payload["recovery_notes"][0]["authority"] = "SYSTEM"
            path = Path(td) / "recovery.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(EmpireCloseError):
                load_close_recovery(path)

    def test_close_is_zero_time_and_exposes_real_action_queue(self):
        result=close_status()
        self.assertFalse(result["canonical"])
        self.assertFalse(result["campaign_time_advanced"])
        self.assertFalse(result["ready_for_canonical_month"])
        self.assertGreater(result["accepted_values"],20)
        self.assertGreater(result["unresolved_items"],5)
        self.assertEqual({r["id"] for r in result["user_actions"]},{"crownworks"})
        self.assertIn("fleet-roster",{r["id"] for r in result["routine_actions"]})

    def test_current_rail_does_not_promote_future_deep_road(self):
        result=close_status()
        rail=result["lanes"]["rail"]
        row={r["key"]:r for r in rail["facts"]}["deep_road.day7_hammer_operational"]
        self.assertIs(row["value"],False)
        self.assertEqual(row["authority"],"SOURCE-DERIVED")

    def test_canal_has_sourced_vessel_constants_but_not_fake_current_fleet(self):
        result=close_status()
        lane=result["lanes"]["canal_waterway"]
        facts={row["key"]:row for row in lane["facts"]}
        self.assertEqual(facts["hunding.standard_canal_barge.cargo_tons"]["value"],100)
        self.assertEqual(facts["hunding.heavy_ore_carrier.cargo_tons"]["value"],150)
        self.assertEqual(facts["hunding.lock.standard_transit_minutes_min"]["value"],25)
        self.assertTrue(any(row["key"]=="hunding.current_barge_fleet" for row in lane["unresolved"]))

    def test_western_quarry_barges_are_not_silently_promoted_to_hunding_class(self):
        result=close_status()
        lane=result["lanes"]["conventional_freight"]
        facts={row["key"]:row for row in lane["facts"]}
        self.assertEqual(
            facts["western_limestone.barge_capacity_status"]["value"],
            "TWO_BARGES_CONFIRMED_CAPACITY_NOT_IDENTIFIED",
        )

    def test_affiliated_nrtc_capacity_is_recovered_without_calling_it_empire_owned(self):
        result=close_status()
        facts={row["key"]:row for row in result["lanes"]["conventional_freight"]["facts"]}
        self.assertEqual(facts["nrtc.current_wagon_count"]["value"],4)
        self.assertIn("Affiliated commercial capacity",facts["nrtc.current_wagon_count"]["note"])

    def test_ncf_parent_revenue_precedence_closes_stale_branch_rollup_discrepancy(self):
        result=close_status()
        lane=result["lanes"]["ncf_finance"]
        self.assertFalse(any(row["key"]=="ncf.monthly_revenue_total" for row in lane.get("conflicts",[])))
        resolved={row["key"]:row for row in lane["resolved_discrepancies"]}
        self.assertEqual(resolved["ncf.monthly_revenue_total"]["selected_value_gp_per_month"],22000)

    def test_ncf_named_loans_do_not_fill_unknown_portfolio(self):
        result=close_status()
        lane=result["lanes"]["ncf_finance"]
        calc={r["key"]:r for r in lane["calculated"]}
        self.assertEqual(calc["ncf.named_active_loans_recovered_gp"]["value"],30000)
        self.assertTrue(any(r["key"]=="ncf.remaining_loan_book_2270000_gp" for r in lane["unresolved"]))

    def test_empire_close_reuses_strict_agriculture_runtime_instead_of_inventing_food_state(self):
        result=close_status()
        food=result["lanes"]["food"]
        self.assertEqual(
            food["existing_runtime"]["fixture"],
            "fixtures/agriculture/agriculture-canon-v1.json",
        )
        facts={row["key"]:row for row in food["facts"]}
        self.assertEqual(
            facts["agricultural_shelters.confirmed_outputs"]["value"],
            ["greenhouse produce","tomatoes","year-round tomatoes"],
        )
        self.assertEqual(facts["converted_quarry.confirmed_species"]["value"],["Tilapia"])
        self.assertTrue(any(row["key"]=="blacklake.species_allocation_within_7_pools" for row in food["unresolved"]))
        self.assertFalse(food["existing_runtime"]["current_month_advance_authorized"])

    def test_sourcebook_research_routes_through_new_path_engine_first(self):
        result=close_status()
        # The close payload is validated by the loader; the routing document is
        # an execution procedure, not a campaign fact.
        import json
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        raw=json.loads((root/"recovery/EMPIRE_CLOSE_RECOVERY_2026-09-18.json").read_text(encoding="utf-8"))
        routing=raw["sourcebook_routing"]
        self.assertEqual(routing["new_path_engine_repo"],"CFhacky/the-new-path-engine")
        self.assertLess(
            routing["order"].index("NEW_PATH_ENGINE_BOOK_RAW"),
            routing["order"].index("EXTERNAL_RESEARCH"),
        )
        self.assertEqual(routing["book_raw_authority"],"UPSTREAM-ADOPTED")

    def test_neverwinter_stonebearer_mentions_reconcile_to_one_four_unit_shared_fleet(self):
        result=close_status()
        lane=result["lanes"]["heavy_machinery"]
        facts={row["key"]:row for row in lane["facts"]}
        self.assertEqual(facts["neverwinter.stonebearer_shared_fleet_units"]["value"],4)
        self.assertIn("do not double-count",facts["neverwinter.stonebearer_shared_fleet_units"]["note"])
        self.assertEqual(lane["ratified_programme"]["day7_fleet"]["Stonebearer"], 10)

    def test_heavy_machinery_line_exists_but_rate_and_total_fleet_remain_uninvented(self):
        result=close_status()
        lane=result["lanes"]["heavy_machinery"]
        facts={row["key"]:row for row in lane["facts"]}
        self.assertEqual(facts["heavy_machinery.production_parent"]["value"],"Gauntlgrym Tools Partnership")
        self.assertTrue(facts["heavy_machinery.stonebearer_line_exists"]["value"])
        self.assertTrue(facts["forgedeep.heavy_machinery_workshops_exist"]["value"])
        self.assertTrue(facts["heavy_machinery.production_active_by_day7_hammer_1495"]["value"])
        self.assertEqual(facts["heavy_machinery.production_active_by_day7_hammer_1495"]["authority"],"USER-RULED")
        methods={row["key"]:row["method"] for row in lane["unresolved"]}
        self.assertNotIn("empire.heavy_machinery.current_roster", methods)
        self.assertNotIn("empire.heavy_machinery.current_build_rate", methods)

    def test_dedicated_barges_are_not_promoted_to_baen_owned_fleet(self):
        result=close_status()
        canal=result["lanes"]["canal_waterway"]
        facts={row["key"]:row for row in canal["facts"]}
        self.assertFalse(facts["empire.owned_barge_fleet_explicitly_established"]["value"])
        self.assertEqual(facts["empire.owned_barge_fleet_explicitly_established"]["authority"],"USER-RULED")

    def test_phase_one_is_complete_and_remaining_system_gaps_are_classified(self):
        result=close_status()
        phases={row["id"]:row for row in result["phase_progress"]}
        self.assertEqual(phases[1]["status"],"COMPLETE")
        self.assertEqual(phases[2]["status"],"IN_PROGRESS")
        gaps=result["lanes"]["system_gaps"]
        methods={row["key"]:row["method"] for row in gaps["unresolved"]}
        self.assertEqual(methods["opening_inventories"],"PHYSICAL_COUNT_OR_PERPETUAL_INVENTORY_RECONSTRUCTION")
        self.assertEqual(methods["market.opening_prices"],"SOURCEBOOK_ANCHORS_PLUS_LOCAL_MARKET_RECOVERY")
        self.assertIn("shock_probabilities",methods)

    def test_non_executable_fact_fails_closed(self):
        for authority in ("MODEL-PROPOSED", "UNRESOLVED", "CALCULATED", "ROLLED-AND-BOUND"):
            with self.subTest(authority=authority), tempfile.TemporaryDirectory() as td:
                payload=load_close_recovery()
                payload["lanes"]["heavy_machinery"]["facts"].append(
                    {"key":"bad","value":99,"authority":authority}
                )
                path=Path(td)/"bad.json"
                path.write_text(json.dumps(payload),encoding="utf-8")
                with self.assertRaises(EmpireCloseError):
                    load_close_recovery(path)

    def test_recovered_machine_cost_is_not_a_production_history(self):
        lane=close_status()["lanes"]["heavy_machinery"]
        facts={row["key"]:row for row in lane["facts"]}
        self.assertEqual(facts["brickworks.stonebearer_equipped_batch_cost_gp"]["value"],32000)
        self.assertFalse(lane["source_recovery"]["original_machine_document_recovered"])
        self.assertTrue(any(r["key"]=="heavy_machinery.first_acceptance_date" for r in lane["resolved_items"]))
        self.assertEqual(lane["ratified_programme"]["origin_authority"], "MODEL-PROPOSED")

    def test_ratified_fleet_reconciles_deliveries_allocation_and_factory_bottlenecks(self):
        programme = load_close_recovery()["lanes"]["heavy_machinery"]["ratified_programme"]
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(programme, json.loads((root / "recovery/MACHINERY_PROGRAMME_2026-09-18.json").read_text()))
        for chassis, count in programme["day7_fleet"].items():
            self.assertEqual(sum(row[chassis] for row in programme["production_history"]), count)
            self.assertEqual(sum(row[chassis] for row in programme["allocation"].values()), count)
        for function, staff_key in (("assembly", "assembly_fitters"), ("kit", "kit_fabricators"), ("integration", "integration"), ("acceptance", "acceptance")):
            hours = sum(n * programme["hours_per_unit"][c][function] for c, n in programme["regular_monthly_capacity"].items())
            self.assertLessEqual(hours, 160 * programme["factory_positions"][staff_key])
        self.assertFalse(programme["automatic_delivery"])
        self.assertIsNone(programme["component_bom"]["raw_material_masses"])
        self.assertEqual(programme["costs"]["day7_cash_debit_gp"], 0)

    def test_approved_population_draw_is_stable_and_preserves_historical_450(self):
        lane = load_close_recovery()["lanes"]["forgedeep"]
        rows = {r["key"]: r for r in lane["facts"]}
        receipt = lane["resolution_receipt"]
        self.assertEqual(receipt["draw_count"], 1)
        self.assertEqual(receipt["value"], receipt["minimum"] + receipt["offset"])
        self.assertLessEqual(receipt["value"], receipt["maximum"])
        self.assertEqual(rows["forgedeep.population_eleint_1494"]["value"], 450)
        self.assertEqual(rows["forgedeep.current_population_day7_hammer"]["value"], 1599)
        self.assertFalse(close_status()["ready_for_canonical_month"])

    def test_historical_loans_and_warehouse_capacity_do_not_create_opening_assets(self):
        lanes=close_status()["lanes"]
        for loan in lanes["ncf_finance"]["historical_loan_evidence"]:
            self.assertIsNone(loan["day7_principal_gp"])
            self.assertFalse(loan["included_in_day7_named_loan_total"])
        warehouse=lanes["warehouse_inventory"]
        self.assertEqual(warehouse["conflicts"][0]["key"],"waterdeep.warehouse.net_storage_geometry")
        self.assertTrue(any(r["key"]=="warehouse.day7_inventory" for r in warehouse["unresolved"]))

if __name__=="__main__":
    unittest.main()
