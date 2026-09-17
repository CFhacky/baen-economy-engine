import { records } from "../data/census.ts";
import type { CensusRecord } from "../data/census-types.ts";
import { FOOD_BUSINESSES } from "../data/food.ts";
import type { RegistryEntity } from "./types.ts";

export type { RegistryEntity, SkipReason } from "./types.ts";
export { eligibility } from "./eligibility.ts";

function parseFact(record: CensusRecord, key: string): string | null {
  const prefix = `${key}: `;
  const line = record.facts.find((fact) => fact.startsWith(prefix));
  if (!line) return null;
  const raw = line.slice(prefix.length);
  if (raw === "null" || raw === "") return null;
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (parsed == null) return null;
    if (typeof parsed === "string") return parsed;
    return String(parsed);
  } catch {
    return raw.replace(/^"|"$/g, "");
  }
}

export function loadRegistry(): RegistryEntity[] {
  return records
    .filter((record) => record.sourceClass === "business_registry")
    .map((record) => ({
      id: record.id,
      title: record.title,
      sector: parseFact(record, "Sector") ?? "UNKNOWN",
      city: record.region[0] ?? "Unknown",
      status: record.status,
      parent: parseFact(record, "Parent Entity"),
      dateOperational: parseFact(record, "Date Operational") ?? null,
      lastUpdated: parseFact(record, "Last Updated"),
      employees: numberOrNull(record.numbers.Employees),
      revenue: numberOrNull(record.numbers["Monthly Revenue"]),
      cost: numberOrNull(record.numbers["Monthly Cost"]),
      capital: numberOrNull(record.numbers["Capital Invested"]),
      hash: record.hash,
      url: record.url,
    }));
}

function numberOrNull(value: number | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function foodEntities(): RegistryEntity[] {
  const byId = new Map(loadRegistry().map((row) => [row.id, row]));
  return FOOD_BUSINESSES.map((food) => {
    const row = byId.get(food.id);
    return {
      id: food.id,
      title: food.title,
      sector: row?.sector ?? "Aquaculture",
      city: food.city,
      status: "Operational",
      parent: row?.parent ?? null,
      dateOperational: row?.dateOperational ?? "Eleint 1494",
      lastUpdated: row?.lastUpdated ?? "Eleint 1494",
      employees: food.employees,
      revenue: food.revenue,
      cost: food.cost,
      capital: food.capital,
      hash: row?.hash ?? food.id,
      url: row?.url ?? `https://app.notion.com/${food.id.replace(/-/g, "")}`,
    };
  });
}
