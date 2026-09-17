export type RegistryEntity = {
  id: string;
  title: string;
  sector: string;
  city: string;
  status: string;
  parent: string | null;
  dateOperational: string | null;
  lastUpdated: string | null;
  employees: number | null;
  revenue: number | null;
  cost: number | null;
  capital: number | null;
  hash: string;
  url: string;
};

export type SkipReason = {
  id: string;
  title: string;
  sector: string;
  reason: string;
  coverage: "MISSING_DATA" | "MISSING_MECHANICS" | "FUTURE" | "UNKNOWN";
};
