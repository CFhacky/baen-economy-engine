#!/usr/bin/env python3
"""Apply committed NPC body-ingest batches into SOURCE_REVIEW_QUEUE_2026-09-18.json."""
from __future__ import annotations

import hashlib
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
ACQ_DIR = ROOT / "acquisition/20260917-execution"


def main() -> None:
    queue = json.loads(QUEUE.read_text(encoding="utf-8"))
    updates = {}
    for path in BATCHES:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for src in payload.get("records") or []:
            sid = src.get("source_id")
            if sid:
                updates[sid] = src
    applied = 0
    for rec in queue["records"]:
        src = updates.get(rec.get("source_id"))
        if src is None:
            continue
        rec["review_disposition"] = src.get("review_disposition")
        rec["semantic_status"] = src.get("semantic_status")
        rec["body_review_status"] = src.get("body_review_status") or "REVIEWED"
        rec["driver_owners"] = list(src.get("driver_owners") or [])
        rec["review_notes"] = list(src.get("review_notes") or [])
        if src.get("body_revision"):
            rec["body_revision"] = src["body_revision"]
        if src.get("body_hash"):
            rec["body_hash"] = src["body_hash"]
        applied += 1

    acq_rows = {}
    if ACQ_DIR.exists():
        for snap in ACQ_DIR.glob("npcs*.json"):
            if "proof" in snap.name:
                continue
            data = json.loads(snap.read_text(encoding="utf-8"))
            cols = data.get("columns") or []
            for row in data.get("rows") or []:
                rec = dict(zip(cols, row))
                url = str(rec.get("url") or "")
                pid = url.rsplit("/", 1)[-1].replace("-", "")
                acq_rows[pid] = {"capture_date": data.get("capture_date"), "row": rec, "file": str(snap)}
    filled = 0
    for rec in queue["records"]:
        if rec.get("body_review_status") != "REVIEWED":
            continue
        digest = rec.get("body_hash")
        revision = rec.get("body_revision")
        if isinstance(digest, str) and len(digest) == 64 and isinstance(revision, str) and revision:
            continue
        acq = acq_rows.get(str(rec.get("source_id") or "").replace("-", ""))
        if not acq:
            continue
        payload = json.dumps(acq["row"], sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        rec["body_hash"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        rec["body_revision"] = f"{acq['capture_date']}T00:00:00Z"
        notes = list(rec.get("review_notes") or [])
        notes.append(
            f"Receipt fields filled from persisted acquisition snapshot {acq['file']}; SHA-256 of captured property row."
        )
        rec["review_notes"] = notes
        filled += 1

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
    print(json.dumps({"applied": applied, "receipts_filled": filled, "body_review_status_counts": queue["body_review_status_counts"], "semantic_status_counts": queue["semantic_status_counts"], "review_disposition_counts": queue["review_disposition_counts"]}, indent=2))


if __name__ == "__main__":
    main()
