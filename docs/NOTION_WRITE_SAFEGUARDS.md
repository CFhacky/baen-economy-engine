# Notion Write Safeguards — Review Gate

Status: **PROPOSED FOR REVIEW — NOT APPROVED OR IMPLEMENTED**

The Gate 1 program has no Notion write adapter, token option, apply command, or
executable mutation payload. The checked-in Registry receipt was obtained through
read-only search/fetch/query operations. Every Registry-bound Gate 1 business
diff is review data and has fixed values of `executable: false`, `write_eligible: false`,
`write_authorized: false`, `write_attempted: false`, and `applied_count: 0`.

This document defines the minimum gate for a possible later writer. It does not
approve one.

## Current evidence boundary

- Database ID: `8ba47f60-efe1-4c83-9fe1-4561543e07d1`.
- Data source: `collection://3c5f887a-4219-4ae6-a18a-82cf2d1841db`.
- Capture: 90 rows, complete terminal pagination receipt, no filter.
- Every row is bound to its page UUID, exact Notion URL, typed row hash, and
  semantic snapshot hash.
- Every consumed property has a type-tagged property hash bound to the source
  schema, snapshot, record, and row.
- The connector capture did not expose durable Notion property IDs for the
  Registry columns. A future writer may not substitute display names for missing
  property IDs without a separately reviewed mapping.
- The five live audit blockers remain source-data blockers; raw Registry totals
  are diagnostic and are never consolidated books.

## Required safeguards before any write-capable code may be merged

1. Chad explicitly approves a named command, exact property allowlist, and exact
   target database/data-source pair after reviewing a sample plan.
2. A fresh read occurs immediately before planning. It must repeat the locked
   database identity, source schema, full pagination, page UUID/URL checks, row
   hashes, property hashes, and value types.
3. Every writable property has a durable Notion property ID, expected Notion
   type, and reviewed encoder. Missing IDs or type drift block the entire plan.
4. Every item uses compare-and-swap preconditions: source snapshot hash, row
   hash, property hash, and exact old value. Any stale value blocks that item;
   best-effort overwrite is forbidden.
5. A plan is immutable and content-hashed. It states the target record, property,
   old value, proposed value, derivation/run hash, authority, and idempotency key.
6. Derived financial values require separately accepted campaign authority and,
   when they represent booked money rather than a forecast, the exact accepted
   ledger commit. A simulation result alone cannot authorize a write.
7. The apply surface accepts only a previously stored, approved plan hash. It
   cannot accept ad-hoc page IDs, property names, values, filters, or URLs.
8. The allowlist excludes identity, status, parentage, source references,
   canonical dates, opening balances, cash, reserves, deposits, debt, and any
   free-form page body unless each category receives a separate approval.
9. A preflight re-reads every target and either applies the complete authorized
   set atomically where the API permits, or records a clearly recoverable partial
   failure. Silent partial success is forbidden.
10. Each attempt records the plan hash, actor approval, request IDs, preflight
    hashes, applied item IDs, API results, and a new post-write read receipt.
11. Retry uses the same idempotency key and proves that already-applied values
    match the approved plan. A changed value requires a new plan and approval.
12. Adversarial tests cover wrong database, stale row/property, type drift,
    duplicate IDs, reordered pages, incomplete pagination, hash tampering,
    partial API failure, retry, and attempted writes outside the allowlist.

## Approval decisions still required

- Which derived properties, if any, may be written.
- Whether a write is allowed for a non-canonical scenario preview (recommended:
  no) or only after campaign acceptance.
- The durable property-ID/type map supplied by a fresh Notion schema read.
- The required ledger binding for financial actuals.
- Who may approve a plan and how that approval is recorded.
- Partial-failure and rollback policy.

Until all of those decisions and tests are accepted, the correct applied count is
zero. Gate 1 deliberately stops at a source-bound, human-reviewable diff.
