#!/usr/bin/env python3
"""Materialize direct Notion connector receipts; never simulate or write Notion.

LiveNotionCensusAcquirer/authorized host tools perform acquisition. This is the
reproducible publication stage, NOT another live read or a source replacement.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
from baen_economy.source_census import (CensusSnapshot, CoverageState, canonical_hash,
    coverage_report, diff_snapshots)
from baen_economy.source_census_acquisition import (AcquisitionError, CollectionSpec,
    normalize_record, page_id, stable_id, verify_receipts)

RECOVERY = PROJECT / "recovery"
RAW = RECOVERY / "acquisition" / "20260917"
LATEST = RECOVERY / "LIVE_EMPIRE_SOURCE_CENSUS_2026-09-17.json"
PREVIOUS = RECOVERY / "PRECEDING_EMPIRE_SOURCE_CENSUS_2026-09-17.json"
FOLLOWON_PREVIOUS = RECOVERY / "PRECEDING_FOLLOWON_CENSUS_2026-09-17.json"
MANDATE_REF = "recovery/ECONOMY_EXECUTION_MANDATE_2026-09-17.txt@codex/recovery-execution-kit-20260917"
KEYS = ("business_registry", "locations", "consequence_ledger_a", "consequence_ledger_b")
FOLLOWON_KEYS = ("factions", "npcs", "artifacts", "threats", "plot_threads", "public_perception")
TITLES = {"business_registry": "Entity", "locations": "Name",
          "consequence_ledger_a": "Commitment", "consequence_ledger_b": "Commitment",
          "factions": "Name", "npcs": "Name", "artifacts": "Name", "threats": "Name",
          "plot_threads": "Thread", "public_perception": "City"}
PAIRS = (
    ("charter", "323e821484b08146a6edc334fb99592d", "323e821484b081bd8195cc09b1652d1d",
     "SOURCE-DERIVED", "explicit_supersession",
     "A is explicitly closed as a bookkeeping duplicate of B, not fulfilled in-world. B remains Pending. The A page's live rich-text Notes explicitly mentions B."),
    ("gauntlgrym", "323e821484b081e7a912fe3389a5f75a", "323e821484b081ed8ab7ed48df5c2d07",
     "MODEL-PROPOSED", "UNRESOLVED",
     "Candidate same engineering obligation: A Overdue/45 days, B Upcoming/0. Preserve both; do not recompute a clock or pick a winner."),
    ("zariel", "323e821484b081999808c4cb7a0fb555", "323e821484b08122ae2be1bebef4c027",
     "MODEL-PROPOSED", "UNRESOLVED",
     "Candidate related production obligation. B specifies 200,000 units and ahead-of-schedule text; A is generic milestones. Do not conflate total, priority order, or facility output."),
    ("timber", "323e821484b081a5ab8ce281286128a1", "323e821484b081578f0fd10c1910e8df",
     "MODEL-PROPOSED", "compatible_candidate_overlap",
     "Both Pending; similar before-winter 1494 target. B adds the Planning entity and seed sawmill. No current-month resolution inferred."),
    ("coronal", "323e821484b081b59e37ea05de7941b4", "323e821484b081af9a0ccc0f8a23586d",
     "MODEL-PROPOSED", "compatible_candidate_overlap",
     "Both Upcoming at autumn equinox 1494. B explicitly disallows delegation. An old deadline is not evidence that attendance or failure occurred."),
    ("civic", "323e821484b081d69a15e4ad05af6f0c", "323e821484b08118a899ee4de3c6e713",
     "MODEL-PROPOSED", "UNRESOLVED",
     "A names Harvest Remembrance on Marpenoth 15; B is a standing civic expectation with a next ceremony. Occurrence-versus-series treatment is not user-ratified."),
    ("mila", "323e821484b081db885ed9acb18225b8", "323e821484b0814ab3ccdcd7434d99ae",
     "MODEL-PROPOSED", "compatible_candidate_overlap",
     "Both Instinct Only; an intelligence warning is not an executed investigation or a realized economic event."),
)


def read_json(path: Path) -> Any:
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise AcquisitionError("duplicate JSON property: " + key)
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs)


def dump(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"


def seal(body: dict[str, Any], key: str) -> dict[str, Any]:
    return {**body, key: canonical_hash(body)}


def reconcile(raw: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    rows = {page_id(row["url"]): (collection, row)
            for collection in ("consequence_ledger_a", "consequence_ledger_b") for row in raw[collection]}
    paired: dict[str, str] = {}
    links = []
    for name, left, right, tag, resolution, explanation in PAIRS:
        if left not in rows or right not in rows:
            raise AcquisitionError("ledger reconciliation references an uncaptured row")
        a, b = rows[left][1], rows[right][1]
        paired[left], paired[right] = right, left
        links.append({"link_id": name, "left_source_id": stable_id(a["url"]),
            "right_source_id": stable_id(b["url"]), "link_provenance": tag,
            "resolution": resolution, "explanation": explanation,
            "source_property_differences": {
                key: {"A": a.get(key), "B": b.get(key)} for key in sorted(set(a) | set(b))
                if key not in {"url", "createdTime"} and a.get(key) != b.get(key)},
            "active_record_override": stable_id(b["url"]) if name == "charter" else None,
            "notion_mutation": False, "campaign_event": False})
    inventory = []
    for identifier, (collection, row) in sorted(rows.items()):
        partner = paired.get(identifier)
        inventory.append({"stable_source_id": stable_id(row["url"]),
            "source_url": row["url"], "collection": collection, "title": row["Commitment"],
            "source_properties": row, "raw_properties_sha256": canonical_hash(row),
            "partner_source_id": stable_id(rows[partner][1]["url"]) if partner else None,
            "disposition": "linked_without_deletion" if partner else "retained_unmatched",
            "temporal_resolution": "UNRESOLVED; no deadline or overdue counter advanced"})
    return seal({"schema": "tnp.economy.consequence-reconciliation/1",
        "capture_date": "2026-09-17", "raw_rows": len(rows), "linked_pairs": len(links),
        "unmatched_a": sum(1 for i, (c, _) in rows.items() if c == KEYS[2] and i not in paired),
        "unmatched_b": sum(1 for i, (c, _) in rows.items() if c == KEYS[3] and i not in paired),
        "source_explicit_supersessions": 1, "canonical_deduplication_performed": False,
        "rows": inventory, "links": links,
        "blockers": ["Gauntlgrym overdue/upcoming conflict", "Zariel contract quantity/scope",
                     "Standing civic series versus dated occurrence",
                     "Apprenticeship row says Pending while Notes describe a future proposal",
                     "Cross-calendar anchoring and deadline histories"]}, "reconciliation_hash")


def build(include_extensions: bool = True) -> dict[Path, str]:
    original_payload = read_json(PREVIOUS if PREVIOUS.exists() else LATEST)
    original = CensusSnapshot.from_mapping(original_payload)
    proofs_payload = read_json(RAW / "enumeration_proofs.json")
    if proofs_payload.get("has_more") is not False:
        raise AcquisitionError("final membership proof response is incomplete")
    proofs = {p["collection"]: p for p in proofs_payload["proofs"]}
    if len(proofs) != len(proofs_payload["proofs"]) or set(proofs) != set(KEYS):
        raise AcquisitionError("required initial collection proof set is incomplete or duplicated")
    extra_proof_files = {}
    if include_extensions:
        for key in FOLLOWON_KEYS:
            proof_path = RAW / (key + ".proof.json")
            pages = sorted(RAW.glob(key + ".[0-9][0-9][0-9].json"))
            if proof_path.exists():
                value = read_json(proof_path)
                if value.get("has_more") is not False or value.get("collection") != key:
                    raise AcquisitionError(key + ": incomplete or mismatched follow-on proof")
                proofs[key] = value
                extra_proof_files[str(proof_path.relative_to(PROJECT))] = hashlib.sha256(proof_path.read_bytes()).hexdigest()
            elif pages:
                raise AcquisitionError(key + ": captured pages retained, but collection proof is incomplete")
    keys = tuple(key for key in (*KEYS, *FOLLOWON_KEYS) if key in proofs)
    records, raw, receipts, per_record, specs = [], {}, [], [], {}
    conflicts = {PAIRS[1][1], PAIRS[1][2]}
    for key in keys:
        paths = sorted(RAW.glob(key + ".[0-9][0-9][0-9].json"))
        if not paths:
            raise AcquisitionError(key + ": missing captured pages")
        if [p.name for p in paths] != [f"{key}.{i:03d}.json" for i in range(len(paths))]:
            raise AcquisitionError(key + ": missing numbered receipt")
        batches = [read_json(p) for p in paths]
        spec = CollectionSpec(key, proofs[key]["data_source_url"], tuple(batches[0]["columns"]), TITLES[key])
        specs[key] = spec
        raw[key] = verify_receipts(spec, batches, proofs[key])
        source_paths = {page_id(row[0]): str(path.relative_to(PROJECT))
                        for path, batch in zip(paths, batches, strict=True) for row in batch["rows"]}
        for path, batch in zip(paths, batches, strict=True):
            receipts.append({"path": str(path.relative_to(PROJECT)), "collection": key,
                "rows": len(batch["rows"]), "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "semantic_sha256": canonical_hash(batch), "after": batch["after"]})
        for row in raw[key]:
            record = normalize_record(spec, row)
            if page_id(row["url"]) in conflicts:
                record.pop("source_hash")
                record["coverage_state"] = "CONFLICT"
                record["source_hash"] = canonical_hash(record)
            records.append(record)
            per_record.append({"stable_source_id": record["stable_source_id"],
                "source_url": row["url"], "collection": key,
                "receipt_path": source_paths[page_id(row["url"])],
                "raw_properties_sha256": canonical_hash(row), "source_hash": record["source_hash"],
                "page_body_acquired": False, "property_evidence": "live Notion SQL projection",
                "source_provenance": "SOURCE-DERIVED", "coverage_assignment_provenance":
                    "UNRESOLVED" if record["coverage_state"] == "CONFLICT" else
                    ("SOURCE-DERIVED" if record["coverage_state"] == "SUPERSEDED" else "MODEL-PROPOSED")})
    captured_count = sum(len(rows) for rows in raw.values())
    if captured_count != sum(p["final_count"] for p in proofs.values()):
        raise AcquisitionError("materialized count does not equal live enumeration")
    collections, found = [], set()
    by_url = {spec.data_source_url: key for key, spec in specs.items()}
    for old in original.source_collections:
        body = old.semantic_body()
        key = by_url.get(body["source_url"])
        if key is not None:
            found.add(key)
            body.update(row_count=len(raw[key]), enumeration_complete=True, source_class=key)
        collections.append(seal(body, "source_hash"))
    if found != set(keys):
        raise AcquisitionError("baseline does not contain every acquired collection")
    denominator = sum(c["row_count"] for c in collections)
    core_counts = {state.value: 0 for state in CoverageState}
    core_counts.update(Counter(r["coverage_state"] for r in records))
    unmaterialized = denominator - captured_count
    if unmaterialized < 0:
        raise AcquisitionError("captured rows exceed source denominator")
    provisional = dict(core_counts)
    provisional["UNKNOWN"] += unmaterialized
    provisional.update(denominator_core_rows=denominator,
        basis="Actual per-record coverage plus explicit UNKNOWN for unmaterialized collections; no carried-forward aggregate SIMULATED claim")
    contextual = [{**r.semantic_body(), "source_hash": r.source_hash} for r in original.records]
    body = {"schema": original.schema, "captured_at": "2026-09-17",
        "campaign_boundary": original.campaign_boundary, "read_mode": "direct_live_Notion_SQL_receipts_read_only",
        "repository_base_sha": original.repository_base_sha, "source_collections": collections,
        "records": sorted(contextual + records, key=lambda r: r["stable_source_id"]),
        "provisional_row_coverage": provisional,
        "known_linked_authority_pages_outside_core_collections": original.known_linked_authority_pages_outside_core_collections,
        "notes": [
            f"{captured_count} actual live core records; {len(contextual)} preceding contextual records retained separately.",
            "Enumeration completeness means all query-visible SQL rows matched final ordered membership, not all page bodies or archived partitions.",
            "SQL rich-text projections can omit mentions/formatting. Explicit relation columns are preserved. Page-body enrichment remains queued.",
            "Capture date is known; a fabricated precise source capture timestamp is not supplied. Collection reads are not an atomic Notion transaction.",
            "Real-world Last Updated values and campaign dates remain distinct source facts; no mixed-calendar number is treated as current by default.",
            "The preceding aggregate claim of seven simulated core rows is retired: no identity-level source-to-simulator mapping supported it.",
            "Ledger A's charter Fulfilled status is a source-explicit bookkeeping supersession, not an in-world completion event.",
            "No source record is dropped because it lacks a simulation type. UNKNOWN is unadjudicated coverage, not a missing captured row."],
        "provenance": [
            {"choice": "Live census first; no month, Notion write, merge or campaign-time advance: " + MANDATE_REF, "tag": "USER-RULED"},
            {"choice": "Core properties and membership from direct live Notion connector receipts", "tag": "SOURCE-DERIVED"},
            {"choice": "Stable page UUIDs, conservative UNKNOWN classification, acquisition checkpoint protocol", "tag": "MODEL-PROPOSED"},
            {"choice": "Gauntlgrym ledger states, contract scope, monetary authority and mixed timelines", "tag": "UNRESOLVED"}]}
    payload = seal(body, "snapshot_hash")
    snapshot = CensusSnapshot.from_mapping(payload)
    report = coverage_report(snapshot)
    if report["gate"] != "CLOSED":
        raise AcquisitionError("recovery coverage unexpectedly opened")
    diff_previous_payload = original_payload
    if extra_proof_files:
        if FOLLOWON_PREVIOUS.exists():
            diff_previous_payload = read_json(FOLLOWON_PREVIOUS)
        else:
            candidate = read_json(LATEST)
            candidate_snapshot = CensusSnapshot.from_mapping(candidate)
            candidate_classes = {r.source_class for r in candidate_snapshot.records}
            if not set(KEYS).issubset(candidate_classes) or any(k in candidate_classes for k in FOLLOWON_KEYS):
                raise AcquisitionError("follow-on batch requires the preceding persisted four-collection census")
            diff_previous_payload = candidate
    diff_previous = CensusSnapshot.from_mapping(diff_previous_payload)
    diff = diff_snapshots(diff_previous, snapshot)
    reconciliation = reconcile(raw)
    manifest = seal({"schema": "tnp.economy.live-acquisition-manifest/1", "capture_date": "2026-09-17",
        "live_tool": "Notion.query-data-sources", "notion_writes": 0, "campaign_months_run": 0,
        "live_materialized_records": captured_count, "retained_contextual_records": len(contextual),
        "unmaterialized_core_rows": unmaterialized, "core_coverage_counts": core_counts,
        "all_record_coverage_counts": report["coverage_state_counts"],
        "complete_collections": {key: len(raw[key]) for key in keys},
        "incomplete_collections": report["incomplete_collections"],
        "enumeration_proof_file_sha256": hashlib.sha256((RAW / "enumeration_proofs.json").read_bytes()).hexdigest(),
        "additional_enumeration_proof_files": extra_proof_files,
        "snapshot_hash": snapshot.snapshot_hash, "previous_snapshot_hash": diff_previous.snapshot_hash,
        "receipt_files": receipts, "records": per_record,
        "limitations": ["SQL query-visible partition; archived partition not independently enumerated",
            "Notes/Garrison/etc. are narrative properties; full page bodies are not yet acquired",
            "Membership validated; concurrent in-place property edits across pages are not atomically excluded",
            f"The {len(collections)-len(keys)} unenumerated collection counts and seven context records remain baseline evidence, not refreshed in this batch"]}, "manifest_hash")
    remaining = [key for key in FOLLOWON_KEYS if key not in keys]
    lines = ["# Live Empire Source Census — 17 September 2026", "", "## Verified acquisition", "",
        f"**{captured_count} live source rows materialized and hashed.** {len(keys)} collections fully enumerated against independent live UUID manifests. No simulation ran.", "",
        "| Collection | Captured | Membership complete |", "|---|---:|---|"]
    lines += [f"| {key} | {len(raw[key])} | Yes |" for key in keys]
    lines += ["", f"Whole identified core: {denominator} rows; {captured_count} materialized; {unmaterialized} not yet materialized. {len(keys)} of {len(collections)} collections complete. {len(contextual)} retained contextual records are additional, not newly fetched core records.",
        "", "## Coverage — CLOSED", "", "| State | Materialized core | All stored records (including prior context) |", "|---|---:|---:|"]
    lines += [f"| {s.value} | {core_counts[s.value]} | {report['coverage_state_counts'].get(s.value, 0)} |" for s in CoverageState]
    lines += ["", "No core row is certified SIMULATED merely because it was acquired. Existing engine mechanics remain unchanged.",
        "", "## Diff against preceding durable snapshot", "",
        f"Added records: {len(diff['added'])}; changed: {len(diff['changed'])}; removed: {len(diff['removed'])}; unchanged: {diff['unchanged_count']}; collection changes: {len(diff['collection_changes'])}.",
        "Added means newly materialized evidence, not newly created in Notion and not a campaign event.",
        "", "## Consequence Ledgers", "",
        f"All {reconciliation['raw_rows']} rows retained. Seven reviewed links: one explicit supersession, three compatible candidate overlaps, three unresolved pairings. Four A-only and three B-only records remain visible. No canonical deduplication.",
        "The charter A-row is a bookkeeping duplicate; B remains pending. Gauntlgrym has Overdue/45 versus Upcoming/0. Zariel's 200,000-unit scope and the standing civic/dated ceremony distinction remain unresolved.",
        "", "## Evidence boundaries and next batch", "",
        "Live Notion connector receipts are the source. This report is reproducibly generated from those receipts; regeneration does not claim another live query.",
        "Selected database properties, including narrative Notes/Garrison fields and formal relations, are retained verbatim. SQL mention/formatting loss is disclosed; full page-body enrichment and the archived partition are not claimed complete.",
        "Default UNKNOWN coverage is MODEL-PROPOSED fail-closed handling. Facts are SOURCE-DERIVED; only explicit source supersession is resolved here. Financial totals are not promoted to current liquidity or profit.",
        "Next queued acquisition classes, in order: " + ", ".join(remaining) + ". Then page-body evidence and source-to-simulator coverage mapping, without advancing time.",
        "", "## Every materialized core record", "", "| Source ID | Class | Title | Coverage | SHA-256 |", "|---|---|---|---|---|"]
    for r in sorted(records, key=lambda r: (r["source_class"], r["stable_source_id"])):
        title = r["title"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {r['stable_source_id']} | {r['source_class']} | {title} | {r['coverage_state']} | `{r['source_hash']}` |")
    ledger_lines = ["# Consequence Ledger reconciliation — read only", "",
        "All 21 records retained; no clock tick, canonical deduplication, or Notion edit.", ""]
    for link in reconciliation["links"]:
        ledger_lines += [f"## {link['link_id']} — {link['resolution']}",
            f"Provenance: **{link['link_provenance']}**. {link['explanation']}",
            f"A: `{link['left_source_id']}`; B: `{link['right_source_id']}`.", ""]
    ledger_lines += ["## Complete row inventory", "", "| Source ID | Ledger | Commitment | Raw status | Partner |", "|---|---|---|---|---|"]
    for r in reconciliation["rows"]:
        ledger_lines.append(f"| {r['stable_source_id']} | {r['collection']} | {r['title']} | {r['source_properties']['Status']} | {r['partner_source_id'] or 'Unmatched — retained'} |")
    outputs = {PREVIOUS: dump(original_payload), LATEST: dump(payload),
        RECOVERY / "LIVE_EMPIRE_SOURCE_CENSUS_REPORT_2026-09-17.md": "\n".join(lines) + "\n",
        RECOVERY / "LIVE_EMPIRE_SOURCE_CENSUS_DIFF_2026-09-17.json": dump(diff),
        RECOVERY / "LIVE_CENSUS_ACQUISITION_MANIFEST_2026-09-17.json": dump(manifest),
        RECOVERY / "CONSEQUENCE_LEDGER_RECONCILIATION_2026-09-17.json": dump(reconciliation),
        RECOVERY / "CONSEQUENCE_LEDGER_RECONCILIATION_2026-09-17.md": "\n".join(ledger_lines) + "\n"}
    if extra_proof_files:
        outputs[FOLLOWON_PREVIOUS] = dump(diff_previous_payload)
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify deterministic persisted outputs without writing")
    args = parser.parse_args()
    outputs = build()
    for path, content in outputs.items():
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                raise AcquisitionError("persisted output differs: " + str(path.relative_to(PROJECT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    manifest = json.loads(outputs[RECOVERY / "LIVE_CENSUS_ACQUISITION_MANIFEST_2026-09-17.json"])
    print(json.dumps({"live_materialized_records": manifest["live_materialized_records"],
        "complete_collections": manifest["complete_collections"], "snapshot_hash": manifest["snapshot_hash"],
        "core_coverage_counts": manifest["core_coverage_counts"], "gate": "CLOSED",
        "output_files": [str(p.relative_to(PROJECT)) for p in outputs]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())