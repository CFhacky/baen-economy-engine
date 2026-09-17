import { meta } from "../data/snapshot.ts";
import {
  CAMPAIGN_BOUNDARY,
  DEFAULT_ASSUMPTIONS,
  TICK_RESULT_SCHEMA,
  expenseFactor,
  expenseModifiers,
  money,
  revenueFactor,
  revenueModifiers,
  type MonthAssumptions,
} from "./business.ts";
import { canonicalHash } from "./crypto.ts";
import { rollBusinessChecks, type DiceRoll } from "./dice.ts";
import { eligibility } from "./eligibility.ts";
import { foodEntities, loadRegistry } from "./registry.ts";
import type { RegistryEntity, SkipReason } from "./types.ts";

export type TickKind = "food" | "registry" | "business" | "canonical";

export type TickRequest = {
  kind: TickKind;
  seed: string;
  monthLabel: string;
  entityId?: string;
  assumptions?: Partial<MonthAssumptions>;
};

export type TickRow = {
  id: string;
  title: string;
  sector: string;
  city: string;
  parent: string | null;
  dateOperational: string | null;
  source: { employees: number; revenue: number; cost: number; capital: number | null };
  dice: { revenue: DiceRoll; expense: DiceRoll };
  factors: { revenue: number; expense: number };
  proposed: { revenue: number; cost: number; net: number };
};

export type TickEnvelope = {
  entities: number;
  staff: number;
  sourceRevenue: number;
  sourceCost: number;
  sourceNet: number;
  proposedRevenue: number;
  proposedCost: number;
  proposedNet: number;
  capital: number;
  unconsolidated: true;
  note: string;
};

export type TickResult = {
  schema: typeof TICK_RESULT_SCHEMA;
  mode: "preview" | "refused";
  canonical: false;
  kind: TickKind;
  monthLabel: string;
  campaignBoundary: string;
  campaignTimeAdvanced: false;
  simulatedCertified: 0;
  authority: "scenario_assumption";
  seedFingerprint: string;
  snapshotHash: string;
  assumptions: MonthAssumptions;
  rows: TickRow[];
  skipped: SkipReason[];
  envelope: TickEnvelope | null;
  ledger: {
    schema: "tnp.business.zero-ledger-preview/1";
    postable: false;
    ledger_post_capability: false;
    transaction_count: 0;
    posting_count: 0;
    transactions: [];
    reason: string;
  };
  notion: {
    write_attempted: false;
    write_eligible: false;
    write_authorized: false;
    applied_count: 0;
  };
  warnings: string[];
  blockers?: string[];
  contentHash: string;
};

const LEDGER_REASON =
  "Registry business outcomes remain proposed scenario values until separately accepted by campaign authority and translated into canonical source events.";

const WARNINGS = [
  "This is a deterministic scenario preview, not campaign canon.",
  "The Registry was read only; zero Notion writes were attempted.",
  "No journal transactions or postings were created.",
  "Parent and child banking rows are listed separately and are not a consolidated P&L.",
  "Capital Invested is not opening cash. Mixed-date source figures are not current liquidity.",
];

export function refuseCanonicalMonth(): Omit<TickResult, "contentHash"> & { contentHash?: string } {
  return {
    schema: TICK_RESULT_SCHEMA,
    mode: "refused",
    canonical: false,
    kind: "canonical",
    monthLabel: CAMPAIGN_BOUNDARY,
    campaignBoundary: CAMPAIGN_BOUNDARY,
    campaignTimeAdvanced: false,
    simulatedCertified: 0,
    authority: "scenario_assumption",
    seedFingerprint: "",
    snapshotHash: meta.snapshotHash,
    assumptions: DEFAULT_ASSUMPTIONS,
    rows: [],
    skipped: [],
    envelope: null,
    ledger: {
      schema: "tnp.business.zero-ledger-preview/1",
      postable: false,
      ledger_post_capability: false,
      transaction_count: 0,
      posting_count: 0,
      transactions: [],
      reason: LEDGER_REASON,
    },
    notion: {
      write_attempted: false,
      write_eligible: false,
      write_authorized: false,
      applied_count: 0,
    },
    warnings: WARNINGS,
    blockers: [
      `SIMULATED=${meta.simulated}. Coverage is closed.`,
      "No live opening cash snapshot.",
      "Labour has no dedicated collection.",
      "NCF parent/branch consolidation is unresolved.",
      "Physical inventories, routes, and prices are not current.",
      "PR #192 is not merged. Notion write path is absent.",
    ],
  };
}

export async function runPreviewMonth(request: TickRequest): Promise<TickResult> {
  if (request.kind === "canonical") {
    const refused = refuseCanonicalMonth();
    const { contentHash: _omit, ...body } = refused;
    void _omit;
    return { ...body, contentHash: await canonicalHash(body) };
  }

  const assumptions: MonthAssumptions = { ...DEFAULT_ASSUMPTIONS, ...request.assumptions };
  if (!request.seed.trim()) throw new Error("seed must be non-empty text");
  if (!request.monthLabel.trim()) throw new Error("monthLabel must be non-empty text");

  const pool = request.kind === "food" ? foodEntities() : loadRegistry();
  let selected = pool;
  if (request.kind === "business") {
    if (!request.entityId) throw new Error("business preview requires entityId");
    selected = pool.filter((row) => row.id === request.entityId || row.title === request.entityId);
    if (selected.length !== 1) throw new Error("entityId must identify exactly one Registry row");
  }

  const skipped: SkipReason[] = [];
  const eligible: RegistryEntity[] = [];
  for (const entity of selected) {
    const block = eligibility(entity);
    if (block) skipped.push(block);
    else eligible.push(entity);
  }

  const rows: TickRow[] = [];
  for (const entity of eligible) {
    rows.push(await resolveRow(entity, request.monthLabel, request.seed, assumptions));
  }

  const envelope = buildEnvelope(rows);
  const body: Omit<TickResult, "contentHash"> = {
    schema: TICK_RESULT_SCHEMA,
    mode: "preview",
    canonical: false,
    kind: request.kind,
    monthLabel: request.monthLabel,
    campaignBoundary: CAMPAIGN_BOUNDARY,
    campaignTimeAdvanced: false,
    simulatedCertified: 0,
    authority: "scenario_assumption",
    seedFingerprint: rows[0]?.dice.revenue.seed_fingerprint ?? (await canonicalHash({ seed: request.seed })),
    snapshotHash: meta.snapshotHash,
    assumptions,
    rows,
    skipped,
    envelope,
    ledger: {
      schema: "tnp.business.zero-ledger-preview/1",
      postable: false,
      ledger_post_capability: false,
      transaction_count: 0,
      posting_count: 0,
      transactions: [],
      reason: LEDGER_REASON,
    },
    notion: {
      write_attempted: false,
      write_eligible: false,
      write_authorized: false,
      applied_count: 0,
    },
    warnings: WARNINGS,
  };
  return { ...body, contentHash: await canonicalHash(body) };
}

async function resolveRow(
  entity: RegistryEntity,
  monthLabel: string,
  seed: string,
  assumptions: MonthAssumptions,
): Promise<TickRow> {
  const employees = entity.employees ?? 0;
  const revenue = entity.revenue ?? 0;
  const cost = entity.cost ?? 0;
  const dice = await rollBusinessChecks({
    snapshotHash: meta.snapshotHash,
    sourceRecordId: `notion:page:${entity.id.replace(/-/g, "")}`,
    monthLabel,
    seed,
    revenueModifiers: revenueModifiers(assumptions),
    expenseModifiers: expenseModifiers(assumptions, employees),
  });
  const revRoll = dice.rolls[0];
  const expRoll = dice.rolls[1];
  const revF = revenueFactor(revRoll.outcome);
  const expF = expenseFactor(expRoll.outcome);
  const proposedRevenue = money(revenue * revF);
  const proposedCost = money(cost * expF);
  return {
    id: entity.id,
    title: entity.title,
    sector: entity.sector,
    city: entity.city,
    parent: entity.parent,
    dateOperational: entity.dateOperational,
    source: { employees, revenue, cost, capital: entity.capital },
    dice: { revenue: revRoll, expense: expRoll },
    factors: { revenue: revF, expense: expF },
    proposed: { revenue: proposedRevenue, cost: proposedCost, net: money(proposedRevenue - proposedCost) },
  };
}

function buildEnvelope(rows: TickRow[]): TickEnvelope {
  const staff = rows.reduce((sum, row) => sum + row.source.employees, 0);
  const sourceRevenue = money(rows.reduce((sum, row) => sum + row.source.revenue, 0));
  const sourceCost = money(rows.reduce((sum, row) => sum + row.source.cost, 0));
  const proposedRevenue = money(rows.reduce((sum, row) => sum + row.proposed.revenue, 0));
  const proposedCost = money(rows.reduce((sum, row) => sum + row.proposed.cost, 0));
  const capital = money(rows.reduce((sum, row) => sum + (row.source.capital ?? 0), 0));
  return {
    entities: rows.length,
    staff,
    sourceRevenue,
    sourceCost,
    sourceNet: money(sourceRevenue - sourceCost),
    proposedRevenue,
    proposedCost,
    proposedNet: money(proposedRevenue - proposedCost),
    capital,
    unconsolidated: true,
    note: "Raw unconsolidated sum of resolved rows. Parent/child banking is not a bank. Capital is not cash.",
  };
}
