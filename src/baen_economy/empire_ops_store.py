"""Append-only local persistence for the Baen Empire browser operator."""
from __future__ import annotations

from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
import sqlite3
import threading
from typing import Any, Mapping

from .operator_codec import canonical_hash

SCHEMA = "tnp.economy.empire-ops-store/1"
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


class EmpireOpsStoreError(ValueError):
    pass


def _json_text(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        default=str,
        separators=(",", ":"),
    )


def _validate_run_id(value: object) -> str:
    if not isinstance(value, str) or not RUN_ID_RE.fullmatch(value):
        raise EmpireOpsStoreError(
            "run_id must be 1-80 characters using letters, numbers, dot, underscore, or hyphen"
        )
    return value


def _safe_request(request: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "month_label": request.get("month_label"),
        "market_condition": request.get("market_condition", "unknown"),
        "vara_active": bool(request.get("vara_active", False)),
        "seed_fingerprint": result.get("seed_fingerprint"),
        "raw_seed_persisted": False,
    }


def _summary(result: Mapping[str, Any]) -> dict[str, Any]:
    admission = result.get("admission") or {}
    return {
        "schema": result.get("schema"),
        "month_label": result.get("month_label"),
        "admitted_entities": admission.get("admitted_entities"),
        "baseline_revenue_gp": admission.get("baseline_revenue_gp"),
        "proposed_revenue_gp": result.get("proposed_revenue_gp"),
        "proposed_net_range_gp": result.get("proposed_net_range_gp"),
        "result_hash": result.get("result_hash"),
        "canonical": bool(result.get("canonical")),
        "notion_writes": result.get("notion_writes"),
        "canonical_ledger_postings": result.get("canonical_ledger_postings"),
        "campaign_time_advanced": bool(result.get("campaign_time_advanced")),
    }


class EmpireOpsStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.execute("PRAGMA journal_mode = WAL")
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                label TEXT NOT NULL,
                request_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                report_md TEXT NOT NULL,
                manifest_hash TEXT NOT NULL
            );
            """
        )
        self._db.execute(
            "INSERT OR IGNORE INTO meta(key,value) VALUES('schema',?)",
            (SCHEMA,),
        )
        self._db.commit()
        row = self._db.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
        if row is None or row["value"] != SCHEMA:
            raise EmpireOpsStoreError("Empire operator store schema is unsupported")

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def save(
        self,
        *,
        run_id: object,
        label: object,
        request: Mapping[str, Any],
        result: Mapping[str, Any],
        report: str,
    ) -> dict[str, Any]:
        identifier = _validate_run_id(run_id)
        if not isinstance(label, str) or not label.strip():
            raise EmpireOpsStoreError("label is required")
        safe_request = _safe_request(request, result)
        result_copy = json.loads(_json_text(result))
        payload_for_hash = {
            "run_id": identifier,
            "label": label.strip(),
            "request": safe_request,
            "result": result_copy,
            "report": report,
        }
        manifest_hash = canonical_hash(payload_for_hash)
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        with self._lock:
            existing = self._db.execute(
                "SELECT * FROM runs WHERE run_id=?",
                (identifier,),
            ).fetchone()
            if existing is not None:
                if existing["manifest_hash"] != manifest_hash:
                    raise EmpireOpsStoreError(
                        f"run_id {identifier!r} already exists with different content"
                    )
                return {**self._row(existing), "replayed_existing_save": True}
            self._db.execute(
                """
                INSERT INTO runs(
                    run_id,created_at,label,request_json,result_json,report_md,manifest_hash
                ) VALUES(?,?,?,?,?,?,?)
                """,
                (
                    identifier,
                    now,
                    label.strip(),
                    _json_text(safe_request),
                    _json_text(result_copy),
                    report,
                    manifest_hash,
                ),
            )
            self._db.commit()
            row = self._db.execute("SELECT * FROM runs WHERE run_id=?", (identifier,)).fetchone()
            assert row is not None
            return {**self._row(row), "replayed_existing_save": False}

    def list_runs(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM runs ORDER BY created_at DESC, run_id DESC"
            ).fetchall()
        return [
            {
                "run_id": row["run_id"],
                "created_at": row["created_at"],
                "label": row["label"],
                "manifest_hash": row["manifest_hash"],
                "summary": _summary(json.loads(row["result_json"])),
            }
            for row in rows
        ]

    def get(self, run_id: object) -> dict[str, Any]:
        identifier = _validate_run_id(run_id)
        with self._lock:
            row = self._db.execute("SELECT * FROM runs WHERE run_id=?", (identifier,)).fetchone()
        if row is None:
            raise EmpireOpsStoreError(f"saved run not found: {identifier}")
        return self._row(row)

    def _row(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "run_id": row["run_id"],
            "created_at": row["created_at"],
            "label": row["label"],
            "request": json.loads(row["request_json"]),
            "result": json.loads(row["result_json"]),
            "report": row["report_md"],
            "manifest_hash": row["manifest_hash"],
            "summary": _summary(json.loads(row["result_json"])),
        }

    def compare(self, left: object, right: object) -> dict[str, Any]:
        a = self.get(left)
        b = self.get(right)
        ar = a["result"]
        br = b["result"]
        sector_a = {row["sector"]: row for row in ar.get("sector_results", [])}
        sector_b = {row["sector"]: row for row in br.get("sector_results", [])}
        sectors = []
        for name in sorted(set(sector_a) | set(sector_b)):
            av = sector_a.get(name, {}).get("proposed_revenue_gp")
            bv = sector_b.get(name, {}).get("proposed_revenue_gp")
            sectors.append(
                {
                    "sector": name,
                    "left_proposed_revenue_gp": av,
                    "right_proposed_revenue_gp": bv,
                    "changed": av != bv,
                }
            )
        return {
            "schema": "tnp.economy.empire-ops-comparison/1",
            "left": a["summary"],
            "right": b["summary"],
            "sector_changes": sectors,
            "same_result_hash": ar.get("result_hash") == br.get("result_hash"),
            "authority": "comparison of saved non-canonical preview artifacts only",
        }

    def export(self, run_id: object, fmt: str) -> tuple[str, bytes]:
        row = self.get(run_id)
        if fmt == "json":
            return (
                "application/json; charset=utf-8",
                (_json_text(row) + "\n").encode("utf-8"),
            )
        if fmt in {"md", "markdown"}:
            return ("text/markdown; charset=utf-8", row["report"].encode("utf-8"))
        if fmt == "html":
            title = html.escape(f"Baen Economy — {row['label']}")
            report = html.escape(row["report"])
            document = (
                "<!doctype html><meta charset='utf-8'><title>"
                + title
                + "</title><style>body{max-width:1100px;margin:40px auto;padding:0 20px;"
                + "font:15px/1.5 system-ui;background:#0b0f14;color:#e8eef5}"
                + "pre{white-space:pre-wrap;background:#121923;border:1px solid #263442;"
                + "padding:20px;border-radius:12px}</style><h1>"
                + title
                + "</h1><p>Saved preview artifact. Not canon; no Notion write, ledger post, "
                + "or campaign-time advance occurred.</p><pre>"
                + report
                + "</pre>"
            )
            return ("text/html; charset=utf-8", document.encode("utf-8"))
        raise EmpireOpsStoreError("format must be html, md, or json")
