import type { DiceOutcome } from "./dice.ts";

export const BUSINESS_MONTH_SCHEMA = "tnp.business.month-preview/1";
export const TICK_RESULT_SCHEMA = "tnp.economy.tick-result/1";
export const CAMPAIGN_BOUNDARY = "Day 7 Hammer 1495 DR";

export const COMMERCIAL_SECTORS = [
  "Agriculture",
  "Aquaculture",
  "Banking",
  "Construction",
  "Hospitality",
  "Infrastructure",
  "Manufacturing",
  "Mining/Quarrying",
  "Real Estate",
  "Trade",
] as const;

export type CommercialSector = (typeof COMMERCIAL_SECTORS)[number];

export const MARKET_MODIFIERS = { boom: 4, stable: 0, recession: -2 } as const;
export type Market = keyof typeof MARKET_MODIFIERS;

export type MonthAssumptions = {
  market: Market;
  varaActive: boolean;
  revenueStreams: number;
  competentManagers: number;
  monopoly: boolean;
  excellentAccounting: boolean;
  rapidExpansion: boolean;
};

export const DEFAULT_ASSUMPTIONS: MonthAssumptions = {
  market: "stable",
  varaActive: true,
  revenueStreams: 1,
  competentManagers: 0,
  monopoly: false,
  excellentAccounting: false,
  rapidExpansion: false,
};

export function employeeSizeModifier(employees: number): number {
  if (!Number.isInteger(employees) || employees < 0) {
    throw new Error("employee count must be a whole non-negative number");
  }
  if (employees === 200 || employees === 1000) {
    throw new Error(`employee count ${employees} is ambiguous in the governing size table`);
  }
  if (employees < 50) return 2;
  if (employees < 200) return 0;
  if (employees < 1000) return -2;
  return -4;
}

export function revenueFactor(outcome: DiceOutcome): number {
  const factors: Record<DiceOutcome, number> = {
    critical_success: 1.25,
    success_by_5_plus: 1.15,
    success: 1.05,
    exact_target: 1.0,
    failure: 0.9,
    failure_by_5_plus: 0.8,
    critical_failure: 0.7,
  };
  return factors[outcome];
}

export function expenseFactor(outcome: DiceOutcome): number {
  const factors: Record<DiceOutcome, number> = {
    critical_success: 0.9,
    success_by_5_plus: 1.0,
    success: 1.05,
    exact_target: 1.05,
    failure: 1.15,
    failure_by_5_plus: 1.15,
    critical_failure: 1.25,
  };
  return factors[outcome];
}

/** ROUND_HALF_UP to 0.01, matching the Python business-month Decimal context. */
export function money(value: number): number {
  const scaled = value * 100;
  const rounded = scaled >= 0 ? Math.floor(scaled + 0.5) : Math.ceil(scaled - 0.5);
  return rounded / 100;
}

export function revenueModifiers(assumptions: MonthAssumptions) {
  const result = [{ label: `Market ${assumptions.market}`, value: MARKET_MODIFIERS[assumptions.market] }];
  if (assumptions.revenueStreams >= 7) result.push({ label: "7+ revenue streams", value: 2 });
  else if (assumptions.revenueStreams >= 4) result.push({ label: "4-6 revenue streams", value: 1 });
  if (assumptions.varaActive) result.push({ label: "Vara active", value: 3 });
  if (assumptions.competentManagers) {
    result.push({ label: "Competent managers", value: assumptions.competentManagers });
  }
  if (assumptions.monopoly) result.push({ label: "Monopoly position", value: 2 });
  return result;
}

export function expenseModifiers(assumptions: MonthAssumptions, employees: number) {
  const result = [
    {
      label: `Entity size (${String(employees)} employees)`,
      value: employeeSizeModifier(employees),
    },
  ];
  if (assumptions.excellentAccounting) result.push({ label: "Excellent accounting", value: 2 });
  if (assumptions.rapidExpansion) result.push({ label: "Rapid expansion", value: -3 });
  return result;
}

export function isCommercialSector(sector: string): sector is CommercialSector {
  return (COMMERCIAL_SECTORS as readonly string[]).includes(sector);
}
