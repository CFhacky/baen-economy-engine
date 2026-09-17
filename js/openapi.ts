export const OPENAPI = {
  openapi: "3.1.0",
  info: {
    title: "Baen Month Engine",
    version: "0.3.0",
    description:
      "Fail-closed monthly economy tick for The New Path / Baen Empire. Preview months are scenario_assumption. Canonical months are refused. Zero Notion writes. Zero ledger postings. Other apps may call these HTTP endpoints with CORS enabled.",
  },
  servers: [{ url: "/api/v1" }],
  paths: {
    "/health": {
      get: {
        summary: "Liveness",
        responses: { "200": { description: "Engine is up" } },
      },
    },
    "/coverage": {
      get: {
        summary: "Coverage gate",
        responses: { "200": { description: "SIMULATED count and blockers" } },
      },
    },
    "/registry": {
      get: {
        summary: "Business Registry rows used by the tick",
        responses: { "200": { description: "90 source rows plus eligibility" } },
      },
    },
    "/preview": {
      post: {
        summary: "Run a non-canonical preview month",
        requestBody: {
          required: true,
          content: {
            "application/json": {
              schema: {
                type: "object",
                required: ["kind", "seed"],
                properties: {
                  kind: { enum: ["food", "registry", "business"] },
                  seed: { type: "string" },
                  monthLabel: { type: "string" },
                  entityId: { type: "string", description: "Required when kind=business" },
                  assumptions: {
                    type: "object",
                    properties: {
                      market: { enum: ["boom", "stable", "recession"] },
                      varaActive: { type: "boolean" },
                      revenueStreams: { type: "integer" },
                      competentManagers: { type: "integer" },
                      monopoly: { type: "boolean" },
                      excellentAccounting: { type: "boolean" },
                      rapidExpansion: { type: "boolean" },
                    },
                  },
                },
              },
            },
          },
        },
        responses: {
          "200": { description: "tnp.economy.tick-result/1" },
          "400": { description: "Malformed request" },
        },
      },
    },
    "/canonical": {
      post: {
        summary: "Canonical month (always refused while SIMULATED=0)",
        responses: { "409": { description: "Coverage closed" } },
      },
    },
  },
} as const;
