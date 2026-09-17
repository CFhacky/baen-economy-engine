"""Persistent monthly operator built around the deterministic stock-flow kernel."""

from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
import hashlib
from pathlib import Path
import shlex
from typing import Mapping

from .domain import Authority, TemporalState, canonical_decimal
from .events import CampaignDate, EventEnvelope, EventPhase, ResolutionStatus
from .operator_codec import canonical_hash, json_safe, with_content_hash
from .operator_dice import empty_roll_manifest, roll_preview_checks
from .operator_store import CampaignStore, StoreError
from .scenarios import LADEN_PROFILE_ID, ScenarioPackage, load_scenario
from .stockflow import FlowKind, RunPlan, RunResult, Snapshot, advance


OPERATOR_SCHEMA = "tnp.economy.operator-result/1"
LEDGER_BASE_COMMIT = "ac6523d404a099dec624930d757478b5317dd471"


def initialize_campaign(
    database: Path,
    *,
    campaign_id: str,
    scenario_id: str,
    profile_id: str = LADEN_PROFILE_ID,
    mode: str = "preview",
) -> dict[str, object]:
    if mode != "preview":
        raise StoreError(
            "actual/canonical initialization is locked until CAN-001 through CAN-006 "
            "and an authoritative opening event bundle are accepted"
        )
    scenario = load_scenario(scenario_id, profile_id=profile_id)
    with CampaignStore.create(
        database, campaign_id=campaign_id, scenario=scenario
    ) as store:
        opening = store.latest_snapshot()
        return {
            "schema": OPERATOR_SCHEMA,
            "command": "init",
            "status": "initialized",
            "persistence": "local_preview_state",
            "canonical": False,
            "campaign_id": campaign_id,
            "scenario_id": scenario.scenario_id,
            "assumption_profile_id": scenario.profile_id,
            "timeline_id": scenario.timeline_id,
            "opening_snapshot_id": opening.snapshot_id,
            "opening_state_hash": opening.state_hash,
            "current_period": 0,
            "next_action": f"baen-economy run-month {_quoted(database)} --period 1 --commit",
            "notion_write_capability": False,
            "ledger_post_capability": False,
            "warning": "PREVIEW — NOT CAMPAIGN CANON",
        }


def status(database: Path) -> dict[str, object]:
    with CampaignStore.open(database) as store:
        campaign = store.campaign_record()
        latest = store.latest_snapshot()
        current_period = int(campaign["current_period"])
        scenario: ScenarioPackage = campaign["scenario"]
        next_action = (
            f"baen-economy run-month {_quoted(database)} --period {current_period + 1} --commit"
            if current_period < scenario.max_period
            else f"baen-economy report {_quoted(database)} --period latest"
        )
        return {
            "schema": OPERATOR_SCHEMA,
            "command": "status",
            "status": "ready",
            "canonical": False,
            "authority_mode": "preview",
            "campaign_id": campaign["campaign_id"],
            "scenario_id": campaign["scenario_id"],
            "assumption_profile_id": campaign["assumption_profile_id"],
            "scenario_hash": campaign["scenario_hash"],
            "timeline_id": campaign["timeline_id"],
            "current_period": current_period,
            "latest_snapshot_id": latest.snapshot_id,
            "latest_state_hash": latest.state_hash,
            "history": store.history_counts(),
            "next_action": next_action,
            "profile_complete": current_period >= scenario.max_period,
            "notion_write_capability": False,
            "ledger_post_capability": False,
        }


def run_month(
    database: Path,
    *,
    period_index: int,
    commit: bool,
    seed: str | None = None,
    include_preview_checks: bool = False,
) -> dict[str, object]:
    if type(period_index) is not int or period_index < 1:
        raise StoreError("period must be a positive integer")
    if seed is not None and not include_preview_checks:
        raise StoreError("--seed requires --roll-preview-checks; no hidden RNG affects stock flow")
    if include_preview_checks and not commit and seed is None:
        raise StoreError(
            "a no-write dice preview requires --seed so the later --commit can reproduce "
            "the exact receipt; a direct committed run may use secure randomness"
        )
    with CampaignStore.open(database) as store:
        campaign = store.campaign_record()
        scenario: ScenarioPackage = campaign["scenario"]
        option_body = {
            "scenario_hash": scenario.scenario_hash,
            "period_index": period_index,
            "include_preview_checks": include_preview_checks,
            "rng_mode": (
                "none"
                if not include_preview_checks
                else ("seeded_preview" if seed is not None else "secure")
            ),
            "seed_fingerprint": (
                hashlib.sha256(seed.encode("utf-8")).hexdigest()
                if seed is not None
                else None
            ),
        }
        request_options_hash = canonical_hash(option_body)
        try:
            existing = store.load_run(period_index)
        except StoreError as exc:
            if "no committed run exists" not in str(exc):
                raise
        else:
            if existing["request_options_hash"] != request_options_hash:
                raise StoreError(
                    f"period {period_index} is already committed with different run options"
                )
            return _command_outcome(
                existing["result"], committed=True, replayed=True, database=database
            )

        parent = store.latest_snapshot()
        current_period = int(campaign["current_period"])
        if parent.period_index != current_period:
            # Another process committed between the campaign-row read and the
            # snapshot read. Resolve the now-existing exact request instead of
            # trying to run period N from its period-N child.
            concurrent = store.load_run(period_index)
            if concurrent["request_options_hash"] != request_options_hash:
                raise StoreError(
                    f"period {period_index} was concurrently committed with different options"
                )
            return _command_outcome(
                concurrent["result"], committed=True, replayed=True, database=database
            )
        if period_index != current_period + 1:
            raise StoreError(
                f"next runnable period is {current_period + 1}; requested {period_index}"
            )
        roll_manifest = (
            roll_preview_checks(
                campaign_id=str(campaign["campaign_id"]),
                timeline_id=scenario.timeline_id,
                period_index=period_index,
                seed=seed,
            )
            if include_preview_checks
            else empty_roll_manifest()
        )
        events = (
            (_roll_manifest_event(scenario, period_index, roll_manifest),)
            if include_preview_checks
            else ()
        )
        plan = scenario.plan(period_index, authorizing_events=events)
        result = advance(scenario.model(), parent, plan)
        plan_payload = _plan_payload(plan)
        semantic = _result_semantic_body(
            campaign=campaign,
            scenario=scenario,
            parent=parent,
            plan=plan,
            result=result,
            roll_manifest=roll_manifest,
        )
        run_hash = canonical_hash(semantic)
        result_payload = with_content_hash({**semantic, "run_hash": run_hash})
        ledger = _ledger_preview(result_payload, scenario)
        notion = _notion_dry_run(result_payload, scenario)
        report = render_report(result_payload)
        if not commit:
            return _command_outcome(
                result_payload,
                committed=False,
                replayed=False,
                database=database,
                report=report,
                ledger=ledger,
                notion=notion,
            )
        committed_payload, replayed = store.commit_run(
            period_index=period_index,
            expected_parent_hash=parent.state_hash,
            request_options=option_body,
            closing_snapshot=result.snapshot,
            plan_payload=plan_payload,
            result_payload=result_payload,
            roll_manifest=roll_manifest,
            report_markdown=report,
            ledger_preview=ledger,
            notion_dry_run=notion,
        )
        return _command_outcome(
            committed_payload,
            committed=True,
            replayed=replayed,
            database=database,
        )


def get_report(database: Path, period_index: int | None = None) -> str:
    with CampaignStore.open(database) as store:
        return store.artifact(period_index, "report_markdown")


def get_ledger_preview(database: Path, period_index: int | None = None) -> str:
    with CampaignStore.open(database) as store:
        return store.artifact(period_index, "ledger_preview")


def get_notion_dry_run(database: Path, period_index: int | None = None) -> str:
    with CampaignStore.open(database) as store:
        return store.artifact(period_index, "notion_dry_run")


def verify_database(database: Path) -> dict[str, object]:
    with CampaignStore.open(database) as store:
        return store.verify()


def render_report(payload: Mapping[str, object]) -> str:
    facts = payload["source_facts"]
    assumptions = payload["assumptions"]
    physical = payload["physical"]
    finance = payload["finance"]
    dice = payload["dice"]
    audit = payload["replay"]
    period = payload["period"]
    need_line = (
        f"- Needed / consumed / shortage: {physical['need_requested_tons']} / "
        f"{physical['consumed_tons']} / {physical['shortage_tons']} tons."
        if physical["need_status"] == "modeled"
        else (
            "- Need, consumption, and shortage are not modeled in this period; "
            "the preview makes no zero-shortage claim."
        )
    )
    lines = [
        "# PREVIEW — NOT CANON — NOT WRITTEN TO NOTION OR THE LEDGER",
        "",
        f"Operation Laden Table, period {period['index']}: {period['campaign_date']}",
        "",
        _vara_briefing(payload),
        "",
        "## What the source actually establishes",
        "",
        f"- Longsaddle has {facts['population_mouths']:,} mouths and is a net food importer.",
        f"- The grain target is {facts['grain_target_tons']['low']}–{facts['grain_target_tons']['high']} tons.",
        f"- Grain plus transport is a {facts['grain_including_transport_gp']['low']}–{facts['grain_including_transport_gp']['high']} gp planning band.",
        f"- The {facts['borrowing_target_gp']['low']}–{facts['borrowing_target_gp']['high']} gp borrowing target would be debt, not revenue.",
        (
            f"- The cited plan resolves none of its {facts['binding_execution_rolls_pending']} "
            "binding execution rolls and records no completed procurement or financing "
            "settlement; this is not a complete cash audit."
        ),
        "",
        "## Illustrative assumptions (not source facts)",
        "",
        "| Assumption | Value | Why it is here |",
        "|---|---:|---|",
    ]
    for item in assumptions:
        lines.append(f"| {item['key']} | {item['value']} | {item['basis']} |")
    lines.extend(
        [
            "",
            "## Physical result",
            "",
            f"- Opening grain across stock and transit: {physical['opening_total_tons']} tons.",
            f"- Shipment requested / dispatched / capacity shortfall: {physical['shipment_requested_tons']} / {physical['shipment_dispatched_tons']} / {physical['shipment_shortfall_tons']} tons.",
            f"- Arrived / lost in transit: {physical['arrived_tons']} / {physical['transit_loss_tons']} tons.",
            need_line,
            f"- Closing supplier / Longsaddle / in transit: {physical['closing_supplier_tons']} / {physical['closing_longsaddle_tons']} / {physical['closing_transit_tons']} tons.",
            f"- Conservation residual: {physical['conservation_residual_tons']} tons (must be zero).",
            f"- Displayed planning basis: {physical['planning_basis_gp_per_ton']} gp/ton. This is not a market price or ledger valuation.",
            "",
            "## Dice receipt",
            "",
        ]
    )
    rolls = dice["rolls"]
    if not rolls:
        lines.append("No dice were rolled. All seven binding operation rolls remain pending.")
    else:
        lines.extend(
            [
                (
                    "These are optional illustrative management checks from the separate "
                    "hybrid-business-operations profile; their targets are not Laden source "
                    "facts, and they do not resolve campaign rolls or change the result."
                ),
                "",
                "| Check | Dice | Target | Modifiers | Total | Margin | Outcome |",
                "|---|---|---:|---:|---:|---:|---|",
            ]
        )
        for roll in rolls:
            faces = "+".join(str(face) for face in roll["dice"])
            lines.append(
                f"| {roll['label']} | {faces} | {roll['base_target']} | "
                f"{roll['modifier_total']:+d} | {roll['total']} | {roll['margin']:+d} | "
                f"{roll['outcome']} |"
            )
    lines.extend(
        [
            "",
            "## Business and banking",
            "",
            "This preview models physical relief logistics only. Revenue, operating cost, profit, cash, and loan balances remain unknown because no sale, purchase settlement, loan draw, or opening balance has been resolved.",
            "",
            f"- Journal transactions: {finance['journal_transaction_count']}.",
            f"- Journal postings: {finance['journal_posting_count']}.",
            f"- Borrowing target: {finance['borrowing_target_gp']['low']}–{finance['borrowing_target_gp']['high']} gp, prospective liability only.",
            "- Blocked by: " + "; ".join(finance["blocking_gates"]) + ".",
            "",
            "## Notion safety",
            "",
            "No connector is present. No write was attempted. The stored dry run contains one review note, but it is ineligible until a verified registry snapshot, property map, write policy, and explicit approval exist.",
            "",
            "- Writes attempted: 0.",
            "- Changes applied: 0.",
            "- Write authorization: false.",
            "",
            "## Unresolved before campaign use",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in payload["blockers"])
    lines.extend(
        [
            "",
            "## Replay audit",
            "",
            f"- Timeline: `{payload['timeline_id']}`",
            f"- Scenario hash: `{audit['scenario_hash']}`",
            f"- Parent state: `{audit['parent_state_hash']}`",
            f"- Plan hash: `{audit['plan_hash']}`",
            f"- Dice manifest: `{audit['roll_manifest_hash']}`",
            f"- Closing state: `{audit['closing_state_hash']}`",
            f"- Run hash: `{payload['run_hash']}`",
            "",
        ]
    )
    return "\n".join(lines)


def _result_semantic_body(
    *,
    campaign: Mapping[str, object],
    scenario: ScenarioPackage,
    parent: Snapshot,
    plan: RunPlan,
    result: RunResult,
    roll_manifest: Mapping[str, object],
) -> dict[str, object]:
    facts = scenario.payload["sourced_facts"]
    assumptions = scenario.payload["assumptions"]
    shipment_requested = sum(
        (item.requested_quantity for item in result.shipments), Decimal("0")
    )
    shipment_dispatched = sum(
        (item.dispatched_quantity for item in result.shipments), Decimal("0")
    )
    needs_requested = sum((item.requested_quantity for item in result.needs), Decimal("0"))
    consumed = sum((item.consumed_quantity for item in result.needs), Decimal("0"))
    needs_modeled = bool(result.needs)
    flows = _flow_totals(result)
    opening_total = _grain_total(parent)
    closing_supplier = _inventory_at(result.snapshot, "site:illustrative-supplier")
    closing_longsaddle = _inventory_at(result.snapshot, "site:longsaddle")
    closing_transit = sum((item.quantity for item in result.snapshot.transit), Decimal("0"))
    planning_basis = Decimal(
        next(
            str(item["value"])
            for item in assumptions
            if item["key"] == "illustrative_planning_basis_gp_per_ton"
        )
    )
    conservation = dict(result.conservation).get("commodity:grain", Decimal("0"))
    plan_payload = _plan_payload(plan)
    return {
        "schema": "tnp.economy.month-result/1",
        "authority_mode": "preview",
        "canonical": False,
        "persistence_meaning": "local preview state only; not canon acceptance",
        "campaign_id": campaign["campaign_id"],
        "scenario_id": scenario.scenario_id,
        "assumption_profile_id": scenario.profile_id,
        "timeline_id": scenario.timeline_id,
        "period": {
            "index": plan.period_index,
            "campaign_ordinal": plan.campaign_ordinal,
            "campaign_date": plan.campaign_date,
        },
        "source_anchor": scenario.payload["source_anchor"],
        "source_facts": facts,
        "assumptions": assumptions,
        "physical": {
            "opening_total_tons": canonical_decimal(opening_total),
            "shipment_requested_tons": canonical_decimal(shipment_requested),
            "shipment_dispatched_tons": canonical_decimal(shipment_dispatched),
            "shipment_shortfall_tons": canonical_decimal(
                shipment_requested - shipment_dispatched
            ),
            "arrived_tons": canonical_decimal(flows[FlowKind.ARRIVAL]),
            "transit_loss_tons": canonical_decimal(flows[FlowKind.ROUTE_LOSS]),
            "need_status": "modeled" if needs_modeled else "not_modeled_this_period",
            "need_requested_tons": (
                canonical_decimal(needs_requested) if needs_modeled else "not_modeled"
            ),
            "consumed_tons": canonical_decimal(consumed) if needs_modeled else "not_modeled",
            "shortage_tons": (
                canonical_decimal(needs_requested - consumed)
                if needs_modeled
                else "not_modeled"
            ),
            "closing_supplier_tons": canonical_decimal(closing_supplier),
            "closing_longsaddle_tons": canonical_decimal(closing_longsaddle),
            "closing_transit_tons": canonical_decimal(closing_transit),
            "planning_basis_gp_per_ton": canonical_decimal(planning_basis),
            "planning_basis_is_market_price": False,
            "conservation_residual_tons": canonical_decimal(conservation),
            "flows": json_safe(result.flows),
            "closing_inventories": json_safe(result.snapshot.inventories),
            "closing_transit": json_safe(result.snapshot.transit),
        },
        "business_scope": {
            "physical_logistics_modeled": True,
            "revenue": "unknown_not_modeled",
            "operating_cost": "unknown_not_modeled",
            "profit": "unknown_not_modeled",
            "cash": "unknown_no_accepted_opening",
        },
        "finance": {
            "journal_transaction_count": 0,
            "journal_posting_count": 0,
            "borrowing_target_gp": facts["borrowing_target_gp"],
            "borrowing_treatment": "prospective_liability_not_revenue",
            "blocking_gates": [
                "no resolved lender or currency",
                "no resolved rate, maturity, collateral, or draw date",
                "no resolved procurement price or settlement",
                "no accepted opening cash or ledger migration band",
            ],
        },
        "dice": roll_manifest,
        "notion": {
            "write_capability": False,
            "write_attempted": False,
            "applied_count": 0,
        },
        "blockers": scenario.payload["unresolved"],
        "replay": {
            "scenario_hash": scenario.scenario_hash,
            "parent_snapshot_id": parent.snapshot_id,
            "parent_state_hash": parent.state_hash,
            "model_hash": result.snapshot.model_hash,
            "ruleset_hash": result.snapshot.ruleset_hash,
            "plan_hash": canonical_hash(plan_payload),
            "roll_manifest_hash": roll_manifest["manifest_hash"],
            "closing_snapshot_id": result.snapshot.snapshot_id,
            "closing_state_hash": result.snapshot.state_hash,
        },
    }


def _plan_payload(plan: RunPlan) -> dict[str, object]:
    return {
        "schema": "tnp.economy.run-plan-storage/1",
        "period_index": plan.period_index,
        "campaign_ordinal": plan.campaign_ordinal,
        "campaign_date": plan.campaign_date,
        "production_orders": json_safe(plan.production_orders),
        "shipment_orders": json_safe(plan.shipment_orders),
        "needs": json_safe(plan.needs),
        "authorizing_events": json_safe(plan.authorizing_events),
        "simulation_assignments": json_safe(plan.simulation_assignments),
    }


def _roll_manifest_event(
    scenario: ScenarioPackage,
    period_index: int,
    manifest: Mapping[str, object],
) -> EventEnvelope:
    plan_without_event = scenario.plan(period_index)
    return EventEnvelope.create(
        source_event_key=f"operator-preview-rolls:{scenario.profile_id}:{period_index}",
        event_revision=1,
        timeline_id=scenario.timeline_id,
        model_version=scenario.model().model_version,
        campaign_date=CampaignDate(
            plan_without_event.campaign_ordinal,
            plan_without_event.campaign_date,
            year_dr=1495,
            precision="month",
        ),
        phase=EventPhase.SOURCE_LOCK.value,
        sequence=0,
        authority=Authority.SCENARIO_ASSUMPTION,
        temporal_state=TemporalState.PROJECTED,
        resolution_status=ResolutionStatus.RESOLVED,
        source_ref=f"operator-preview:{scenario.scenario_hash}",
        event_type="operator.preview_roll_manifest",
        subject_entity_id="entity:baen-enterprises",
        payload=dict(manifest),
    )


def _ledger_preview(
    result: Mapping[str, object], scenario: ScenarioPackage
) -> dict[str, object]:
    finance = result["finance"]
    body = {
        "schema": "tnp.economy.ledger-preview/1",
        "status": "preview_only",
        "postable": False,
        "run_hash": result["run_hash"],
        "scenario_hash": scenario.scenario_hash,
        "timeline_id": scenario.timeline_id,
        "state_hash": result["replay"]["closing_state_hash"],
        "finance_bridge_version": "tnp.economy.finance/1",
        "ledger_base_commit": LEDGER_BASE_COMMIT,
        "chart_sha256": "not_evaluated_no_transactions",
        "source_event_refs": [],
        "transactions": [],
        "totals_by_currency": [],
        "transaction_count": 0,
        "posting_count": 0,
        "blocked_intents": [
            {
                "intent": "borrowing target",
                "amount_gp": finance["borrowing_target_gp"],
                "accounting_treatment": "prospective liability; never revenue",
                "blocking_gates": finance["blocking_gates"][:2],
            },
            {
                "intent": "grain procurement and transport",
                "amount_gp": scenario.payload["sourced_facts"]["grain_including_transport_gp"],
                "accounting_treatment": "planning band only; no payable or cash event",
                "blocking_gates": finance["blocking_gates"][2:],
            },
        ],
        "warning": (
            "Stock movement is not a sale or settlement. This artifact cannot enter "
            "JournalBook and no ledger file was read or changed."
        ),
    }
    return with_content_hash(body)


def _notion_dry_run(
    result: Mapping[str, object], scenario: ScenarioPackage
) -> dict[str, object]:
    physical = result["physical"]
    body = {
        "schema": "tnp.notion.proposal/1",
        "capability": "review_only",
        "write_authorized": False,
        "approval_state": "unapproved",
        "write_attempted": False,
        "applied_count": 0,
        "run_hash": result["run_hash"],
        "timeline_id": scenario.timeline_id,
        "source_registry_snapshot": "not_supplied",
        "candidate_count": 1,
        "blocked_count": 1,
        "eligible_count": 0,
        "eligible_items": [],
        "blocked_suggestions": [
            {
                "operation": "suggest_replace",
                "logical_field": "monthly_operational_summary",
                "before": {"status": "unknown_without_verified_registry_snapshot"},
                "suggested_after": {
                    "type": "text",
                    "value": (
                        f"Illustrative period {result['period']['index']}: "
                        f"{physical['shipment_dispatched_tons']} tons dispatched, "
                        f"{physical['arrived_tons']} arrived, "
                        f"{physical['transit_loss_tons']} lost, and "
                        f"{physical['closing_longsaddle_tons']} remain at Longsaddle."
                    ),
                },
                "authority": "scenario_assumption_and_engine_derived",
                "eligible": False,
                "blocking_reasons": [
                    "noncanonical_source",
                    "verified_registry_snapshot_absent",
                    "source_record_and_row_hash_absent",
                    "field_mapping_unapproved",
                    "write_policy_unapproved",
                ],
            }
        ],
        "warning": (
            "Pure data review artifact: it contains no transport configuration, "
            "credential, connector request, or executable write instruction."
        ),
    }
    return with_content_hash(body)


def _command_outcome(
    result: Mapping[str, object],
    *,
    committed: bool,
    replayed: bool,
    database: Path,
    report: str | None = None,
    ledger: Mapping[str, object] | None = None,
    notion: Mapping[str, object] | None = None,
) -> dict[str, object]:
    outcome = {
        "schema": OPERATOR_SCHEMA,
        "command": "run-month",
        "status": "committed" if committed else "dry_run_not_saved",
        "committed": committed,
        "replayed_existing_commit": replayed,
        "persistence": "local_preview_state" if committed else "none",
        "canonical": False,
        "database": str(database),
        "campaign_id": result["campaign_id"],
        "scenario_id": result["scenario_id"],
        "assumption_profile_id": result["assumption_profile_id"],
        "timeline_id": result["timeline_id"],
        "period": result["period"],
        "run_hash": result["run_hash"],
        "closing_snapshot_id": result["replay"]["closing_snapshot_id"],
        "closing_state_hash": result["replay"]["closing_state_hash"],
        "summary": result["physical"],
        "journal_postings": 0,
        "notion_writes": 0,
        "warning": "PREVIEW — NOT CAMPAIGN CANON",
    }
    if report is not None:
        outcome["report_markdown"] = report
    if ledger is not None:
        outcome["ledger_preview"] = ledger
    if notion is not None:
        outcome["notion_dry_run"] = notion
    return outcome


def _flow_totals(result: RunResult) -> dict[FlowKind, Decimal]:
    totals = {kind: Decimal("0") for kind in FlowKind}
    for flow in result.flows:
        totals[flow.kind] += flow.quantity
    return totals


def _grain_total(snapshot: Snapshot) -> Decimal:
    return sum(
        (
            item.quantity
            for item in snapshot.inventories
            if item.commodity_id == "commodity:grain"
        ),
        Decimal("0"),
    ) + sum(
        (item.quantity for item in snapshot.transit if item.commodity_id == "commodity:grain"),
        Decimal("0"),
    )


def _inventory_at(snapshot: Snapshot, site_id: str) -> Decimal:
    return sum(
        (
            item.quantity
            for item in snapshot.inventories
            if item.site_id == site_id and item.commodity_id == "commodity:grain"
        ),
        Decimal("0"),
    )


def _vara_briefing(payload: Mapping[str, object]) -> str:
    physical = payload["physical"]
    if payload["period"]["index"] == 1:
        return (
            f"Vara's preview: the first movement can carry {physical['shipment_dispatched_tons']} "
            f"tons. The illustrative route limit leaves {physical['shipment_shortfall_tons']} "
            "tons at the supplier, and none has reached Longsaddle yet. Do not spend against "
            "the borrowing target: it is unresolved debt capacity, not income."
        )
    coverage = Decimal(str(physical["closing_longsaddle_tons"])) / Decimal("300")
    return (
        f"Vara's preview: {physical['arrived_tons']} tons reached Longsaddle after "
        f"{physical['transit_loss_tons']} tons of illustrative loss. After this month's "
        f"{physical['consumed_tons']}-ton need, {physical['closing_longsaddle_tons']} tons remain "
        f"(about {coverage.quantize(Decimal('0.01'))} illustrative months). The next decision "
        "is whether to resolve the real procurement, route, ration, and financing terms."
    )


def _quoted(path: Path) -> str:
    return shlex.quote(str(path))
