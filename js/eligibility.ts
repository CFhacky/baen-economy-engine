import { isCommercialSector } from "./business.ts";
import type { RegistryEntity, SkipReason } from "./types.ts";

export function eligibility(entity: RegistryEntity): SkipReason | null {
  if (/unconfirm/i.test(entity.status)) {
    return {
      id: entity.id,
      title: entity.title,
      sector: entity.sector,
      reason: `Status ${entity.status}. Held out of any commercial envelope.`,
      coverage: "UNKNOWN",
    };
  }
  if (entity.status !== "Operational") {
    return {
      id: entity.id,
      title: entity.title,
      sector: entity.sector,
      reason: `Status ${entity.status} is not Operational.`,
      coverage: "UNKNOWN",
    };
  }
  if (!isCommercialSector(entity.sector)) {
    return {
      id: entity.id,
      title: entity.title,
      sector: entity.sector,
      reason: `Sector ${entity.sector} is outside the reviewed commercial allowlist (no Merchant-15 treatment).`,
      coverage: "MISSING_MECHANICS",
    };
  }
  if (entity.employees == null || entity.revenue == null || entity.cost == null) {
    return {
      id: entity.id,
      title: entity.title,
      sector: entity.sector,
      reason: "Missing Employees, Monthly Revenue, or Monthly Cost. Fail-closed; not invented.",
      coverage: "MISSING_DATA",
    };
  }
  if (entity.employees === 200 || entity.employees === 1000) {
    return {
      id: entity.id,
      title: entity.title,
      sector: entity.sector,
      reason: `Employee count ${entity.employees} is ambiguous in the size table.`,
      coverage: "MISSING_MECHANICS",
    };
  }
  if (!entity.dateOperational || entity.dateOperational === "TBD") {
    return {
      id: entity.id,
      title: entity.title,
      sector: entity.sector,
      reason: "Date Operational is empty. Mixed-date figures are not treated as current cash.",
      coverage: "MISSING_DATA",
    };
  }
  if (/\b1496\b/.test(entity.dateOperational) || /\b1496\b/.test(entity.title)) {
    return {
      id: entity.id,
      title: entity.title,
      sector: entity.sector,
      reason: `${entity.dateOperational} is after Day 7 Hammer 1495 DR.`,
      coverage: "FUTURE",
    };
  }
  return null;
}
