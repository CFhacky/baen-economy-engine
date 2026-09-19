#!/usr/bin/env python3
"""Merge existing NPC body-ingest batches into SOURCE_REVIEW_QUEUE_2026-09-18.json.

Reads the already-committed G1-G3 and remaining A/B/C receipts. Does not invent
classifications. Safe to replay.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
QUEUE = ROOT / "SOURCE_REVIEW_QUEUE_2026-09-18.json"
BATCHES = [
    ROOT / "NPC_BODY_INGEST_BATCH_G1_2026-09-19.json",
    ROOT / "NPC_BODY_INGEST_BATCH_G2_2026-09-19.json",
    ROOT / "NPC_BODY_INGEST_BATCH_G3_2026-09-19.json",
    ROOT / "NPC_BODY_INGEST_REMAINING_A_2026-09-19.json",
    ROOT / "NPC_BODY_INGEST_REMAINING_B_2026-09-19.json",
    ROOT / "NPC_BODY_INGEST_REMAINING_C_2026-09-19.json",
]

def _counts(records):
    sem = Counter(r.get("semantic_status") or "UNKNOWN" for r in records)
    body = Counter(r.get("body_review_status") or "UNMEASURED" for r in records)
    disp = Counter(r.get("review_disposition") or "UNREVIEWED" for r in records)
    return {
        "semantic_status_counts": {
            "SOURCE_MAPPED": sem.get("SOURCE_MAPPED", 0),
            "FUTURE": sem.get("FUTURE", 0),
            "CONFLICT": sem.get("CONFLICT", 0),
            "SUPERSEDED": sem.get("SUPERSEDED", 0),
            "MISSING_DATA": sem.get("MISSING_DATA", 0),
            "CONTEXT_ONLY": sem.get("CONTEXT_ONLY", 0),
            "HISTORICAL": sem.get("HISTORICAL", 0),
            "UNKNOWN": sem.get("UNKNOWN", 0),
        },
        "body_review_status_counts": {
            "REVIEWED": body.get("REVIEWED", 0),
            "NO_BODY_NOT_APPLICABLE": body.get("NO_BODY_NOT_APPLICABLE", 0),
            "UNMEASURED": body.get("UNMEASURED", 0),
        },
        "review_disposition_counts": {
            "ECONOMIC_INPUT": disp.get("ECONOMIC_INPUT", 0),
            "FUTURE_ONLY": disp.get("FUTURE_ONLY", 0),
            "CONFLICT": disp.get("CONFLICT", 0),
            "SUPERSEDED": disp.get("SUPERSEDED", 0),
            "MISSING_DATA": disp.get("MISSING_DATA", 0),
            "ECONOMIC_CONTEXT": disp.get("ECONOMIC_CONTEXT", 0),
            "NO_BODY_NOT_APPLICABLE": disp.get("NO_BODY_NOT_APPLICABLE", 0),
            "HISTORICAL_ONLY": disp.get("HISTORICAL_ONLY", 0),
            "NON_ECONOMIC": disp.get("NON_ECONOMIC", 0),
            "UNREVIEWED": disp.get("UNREVIEWED", 0),
        },
    }

def main() -> None:
    patches = {}
    for path in BATCHES:
        payload = json.loads(path.read_text())
        for row in payload["records"]:
            patches[row["source_id"]] = (path.name, row)
    queue = json.loads(QUEUE.read_text())
    applied = 0
    for rec in queue["records"]:
        hit = patches.get(rec["source_id"])
        if hit is None:
            continue
        fn, src = hit
        rec["review_disposition"] = src["review_disposition"]
        rec["semantic_status"] = src["semantic_status"]
        rec["body_review_status"] = src.get("body_review_status", "REVIEWED")
        rec["driver_owners"] = list(src.get("driver_owners") or [])
        notes = list(src.get("review_notes") or [])
        tag = f"NPC body ingest merge 2026-09-19 from {fn}."
        if tag not in notes:
            notes.append(tag)
        rec["review_notes"] = notes
        if src.get("body_revision"):
            rec["body_revision"] = src["body_revision"]
        if src.get("body_hash"):
            rec["body_hash"] = src["body_hash"]
        applied += 1
    if applied != 141:
        raise SystemExit(f"applied {applied} != 141")
    counts = _counts(queue["records"])
    queue["captured_at"] = "2026-09-19"
    queue.update(counts)
    QUEUE.write_text(json.dumps(queue, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"applied": applied, **counts}, indent=2))

if __name__ == "__main__":
    main()
