#!/usr/bin/env python3
"""Apply NPC body-ingest merge patch into SOURCE_REVIEW_QUEUE_2026-09-18.json."""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
QUEUE = ROOT / "SOURCE_REVIEW_QUEUE_2026-09-18.json"
PATCH = ROOT / "NPC_BODY_INGEST_QUEUE_MERGE_2026-09-19.json"

def main() -> None:
    queue = json.loads(QUEUE.read_text())
    patch = json.loads(PATCH.read_text())
    by_id = {row["source_id"]: row for row in patch["records"]}
    applied = 0
    for rec in queue["records"]:
        src = by_id.get(rec["source_id"])
        if src is None:
            continue
        rec["review_disposition"] = src["review_disposition"]
        rec["semantic_status"] = src["semantic_status"]
        rec["body_review_status"] = src["body_review_status"]
        rec["driver_owners"] = list(src.get("driver_owners") or [])
        rec["review_notes"] = list(src.get("review_notes") or [])
        if src.get("body_revision"):
            rec["body_revision"] = src["body_revision"]
        if src.get("body_hash"):
            rec["body_hash"] = src["body_hash"]
        applied += 1
    if applied != patch["record_count"]:
        raise SystemExit(f"applied {applied} != patch {patch['record_count']}")
    sem = Counter(r.get("semantic_status") or "UNKNOWN" for r in queue["records"])
    body = Counter(r.get("body_review_status") or "UNMEASURED" for r in queue["records"])
    disp = Counter(r.get("review_disposition") or "UNREVIEWED" for r in queue["records"])
    queue["captured_at"] = "2026-09-19"
    queue["semantic_status_counts"] = {
        "SOURCE_MAPPED": sem.get("SOURCE_MAPPED", 0),
        "FUTURE": sem.get("FUTURE", 0),
        "CONFLICT": sem.get("CONFLICT", 0),
        "SUPERSEDED": sem.get("SUPERSEDED", 0),
        "MISSING_DATA": sem.get("MISSING_DATA", 0),
        "CONTEXT_ONLY": sem.get("CONTEXT_ONLY", 0),
        "HISTORICAL": sem.get("HISTORICAL", 0),
        "UNKNOWN": sem.get("UNKNOWN", 0),
    }
    queue["body_review_status_counts"] = {
        "REVIEWED": body.get("REVIEWED", 0),
        "NO_BODY_NOT_APPLICABLE": body.get("NO_BODY_NOT_APPLICABLE", 0),
        "UNMEASURED": body.get("UNMEASURED", 0),
    }
    queue["review_disposition_counts"] = {
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
    }
    QUEUE.write_text(json.dumps(queue, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({
        "applied": applied,
        "body_review_status_counts": queue["body_review_status_counts"],
        "semantic_status_counts": queue["semantic_status_counts"],
        "review_disposition_counts": queue["review_disposition_counts"],
    }, indent=2))

if __name__ == "__main__":
    main()
