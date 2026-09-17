import { hmacSha256, sha256Bytes, sha256Utf8Hex } from "./crypto.ts";

export const BUSINESS_DICE_SCHEMA = "tnp.business.dice-manifest/1";
export const DICE_METHOD = "hmac_sha256_seeded_preview";

export type DiceOutcome =
  | "critical_success"
  | "success_by_5_plus"
  | "success"
  | "exact_target"
  | "failure"
  | "failure_by_5_plus"
  | "critical_failure";

export type DiceModifier = { label: string; value: number };

export type DiceRoll = {
  roll_key: string;
  label: string;
  dice: [number, number, number];
  total: number;
  base_target: number;
  target_authority: string;
  modifiers: DiceModifier[];
  modifier_total: number;
  effective_target: number;
  margin: number;
  outcome: DiceOutcome;
  method: typeof DICE_METHOD;
  seed_fingerprint: string;
  effect: string;
};

export function classify3d6(total: number, effectiveTarget: number): DiceOutcome {
  if (!Number.isInteger(total) || total < 3 || total > 18) {
    throw new Error("3d6 total must be an integer from 3 through 18");
  }
  if (!Number.isInteger(effectiveTarget)) throw new Error("effective target must be an integer");
  const margin = effectiveTarget - total;
  if (total <= 4 || (total === 5 && effectiveTarget >= 15) || (total === 6 && effectiveTarget >= 16)) {
    return "critical_success";
  }
  if (total === 18 || (total === 17 && effectiveTarget <= 15) || margin <= -10) {
    return "critical_failure";
  }
  if (total === 17) return "failure";
  if (margin >= 5) return "success_by_5_plus";
  if (margin > 0) return "success";
  if (margin === 0) return "exact_target";
  if (margin <= -5) return "failure_by_5_plus";
  return "failure";
}

export async function hmacDie(sides: number, seed: string, coordinate: string[]): Promise<number> {
  if (!Number.isInteger(sides) || sides < 2) throw new Error("die must have at least two sides");
  const modulus = 2 ** 64;
  const limit = modulus - (modulus % sides);
  const message = new TextEncoder().encode(coordinate.join("\u001f"));
  const key = await sha256Bytes(new TextEncoder().encode(seed));
  let attempt = 0;
  while (true) {
    const payload = new TextEncoder().encode(`\u001f${attempt}`);
    const joined = new Uint8Array(message.length + payload.length);
    joined.set(message, 0);
    joined.set(payload, message.length);
    const digest = await hmacSha256(key, joined);
    const sample = readU64(digest);
    if (sample < limit) return Number(sample % BigInt(sides)) + 1;
    attempt += 1;
  }
}

function readU64(digest: Uint8Array): bigint {
  const view = new DataView(digest.buffer, digest.byteOffset, digest.byteLength);
  return view.getBigUint64(0, false);
}

export async function roll3d6(seed: string, coordinatePrefix: string[]): Promise<[number, number, number]> {
  const faces: number[] = [];
  for (let index = 1; index <= 3; index += 1) {
    faces.push(await hmacDie(6, seed, [...coordinatePrefix, String(index)]));
  }
  return faces as [number, number, number];
}

export async function seedFingerprint(seed: string): Promise<string> {
  if (!seed) throw new Error("business preview seed must be non-empty text");
  return sha256Utf8Hex(seed);
}

export async function rollBusinessChecks(args: {
  snapshotHash: string;
  sourceRecordId: string;
  monthLabel: string;
  seed: string;
  revenueModifiers: DiceModifier[];
  expenseModifiers: DiceModifier[];
}): Promise<{
  schema: typeof BUSINESS_DICE_SCHEMA;
  authority: "scenario_assumption";
  binding_scope: string;
  campaign_state_rolls_resolved: 0;
  method: typeof DICE_METHOD;
  seed_fingerprint: string;
  rolls: DiceRoll[];
  warning: string;
}> {
  const fingerprint = await seedFingerprint(args.seed);
  const rolls = [
    await makeRoll({
      rollKey: "revenue",
      label: "Sector revenue check",
      baseTarget: 15,
      targetAuthority: "hybrid-business-ops Merchant-15 sector revenue table",
      modifiers: args.revenueModifiers,
      snapshotHash: args.snapshotHash,
      sourceRecordId: args.sourceRecordId,
      monthLabel: args.monthLabel,
      fingerprint,
    }),
    await makeRoll({
      rollKey: "expense",
      label: "Entity expense-control check",
      baseTarget: 16,
      targetAuthority: "hybrid-business-ops Administration-16 expense table",
      modifiers: args.expenseModifiers,
      snapshotHash: args.snapshotHash,
      sourceRecordId: args.sourceRecordId,
      monthLabel: args.monthLabel,
      fingerprint,
    }),
  ];
  return {
    schema: BUSINESS_DICE_SCHEMA,
    authority: "scenario_assumption",
    binding_scope: "this persisted non-canonical registry preview only",
    campaign_state_rolls_resolved: 0,
    method: DICE_METHOD,
    seed_fingerprint: fingerprint,
    rolls,
    warning:
      "These rolls determine only this preview. They do not advance campaign canon, alter the Business Registry, or authorize ledger postings.",
  };
}

async function makeRoll(args: {
  rollKey: string;
  label: string;
  baseTarget: number;
  targetAuthority: string;
  modifiers: DiceModifier[];
  snapshotHash: string;
  sourceRecordId: string;
  monthLabel: string;
  fingerprint: string;
}): Promise<DiceRoll> {
  const dice = await roll3d6(args.fingerprint, [
    "business-month",
    args.snapshotHash,
    args.sourceRecordId,
    args.monthLabel,
    args.rollKey,
  ]);
  const modifierTotal = args.modifiers.reduce((sum, item) => sum + item.value, 0);
  const total = dice[0] + dice[1] + dice[2];
  const effectiveTarget = args.baseTarget + modifierTotal;
  return {
    roll_key: args.rollKey,
    label: args.label,
    dice,
    total,
    base_target: args.baseTarget,
    target_authority: args.targetAuthority,
    modifiers: args.modifiers,
    modifier_total: modifierTotal,
    effective_target: effectiveTarget,
    margin: effectiveTarget - total,
    outcome: classify3d6(total, effectiveTarget),
    method: DICE_METHOD,
    seed_fingerprint: args.fingerprint,
    effect: "drives only the stored non-canonical preview",
  };
}
