"""Evidence-first Day-7 Hammer Empire Close recovery surface."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CLOSE_RECOVERY = PROJECT_ROOT / "recovery/EMPIRE_CLOSE_RECOVERY_2026-09-18.json"

class EmpireCloseError(ValueError):
    pass

_ACCEPTED = {"SOURCE-DERIVED","USER-RULED","CALCULATED","ROLLED-AND-BOUND","UPSTREAM-ADOPTED"}

def load_close_recovery(path: Path = DEFAULT_CLOSE_RECOVERY) -> dict[str, Any]:
    try:
        payload=json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EmpireCloseError(f"cannot read Empire Close recovery: {exc}") from exc
    if payload.get("schema")!="tnp.economy.empire-close-recovery/1":
        raise EmpireCloseError("unsupported Empire Close recovery schema")
    if payload.get("canonical") is not False or payload.get("campaign_time_advanced") is not False:
        raise EmpireCloseError("Empire Close recovery must remain non-canonical and zero-time")
    _validate_authority(payload)
    return payload

def _validate_authority(payload: Mapping[str, Any]) -> None:
    lanes=payload.get("lanes")
    if not isinstance(lanes,dict):
        raise EmpireCloseError("lanes must be an object")
    for lane_name,lane in lanes.items():
        if not isinstance(lane,dict):
            raise EmpireCloseError(f"lane {lane_name} must be an object")
        for field in ("facts","calculated"):
            rows=lane.get(field,[])
            if not isinstance(rows,list):
                raise EmpireCloseError(f"{lane_name}.{field} must be a list")
            for row in rows:
                if not isinstance(row,dict):
                    raise EmpireCloseError(f"{lane_name}.{field} row must be an object")
                authority=row.get("authority")
                if authority not in _ACCEPTED:
                    raise EmpireCloseError(f"{lane_name}.{field} contains non-executable authority {authority!r}")
        for row in lane.get("unresolved",[]):
            if not isinstance(row,dict) or not row.get("method") or not row.get("reason"):
                raise EmpireCloseError(f"{lane_name} unresolved row lacks method/reason")

def close_status(path: Path = DEFAULT_CLOSE_RECOVERY) -> dict[str, Any]:
    data=load_close_recovery(path)
    lanes=data["lanes"]
    accepted=0
    unresolved=0
    conflicts=0
    for lane in lanes.values():
        accepted += len(lane.get("facts",[])) + len(lane.get("calculated",[]))
        unresolved += len(lane.get("unresolved",[]))
        conflicts += len(lane.get("conflicts",[]))
    queue=data["action_queue"]
    return {
        "schema":"tnp.economy.empire-close-status/1",
        "campaign_boundary":data["campaign_boundary"],
        "accepted_values":accepted,
        "unresolved_items":unresolved,
        "conflicts":conflicts,
        "phase_progress":data["phases"],
        "lanes":lanes,
        "action_queue":queue,
        "user_actions":[row for row in queue if row.get("user_action_required") is True],
        "routine_actions":[row for row in queue if row.get("user_action_required") is False],
        "ready_for_canonical_month":False,
        "canonical":False,
        "campaign_time_advanced":False,
        "notion_writes":0,
    }
