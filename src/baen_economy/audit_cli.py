"""Offline, read-only Business Registry export audit command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping, Sequence

from .registry import audit_rows


def audit_export(payload: object) -> dict[str, object]:
    """Audit an already-exported JSON payload without any connector capability."""

    rows: object
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, Mapping):
        rows = payload.get("rows", payload.get("results"))
    else:
        rows = None
    if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
        raise ValueError("registry export must be a JSON row array or an object with rows/results")

    audit = audit_rows(rows)
    return {
        "schema": "tnp.registry.audit/1",
        "row_count": audit.row_count,
        "blocker_count": audit.blocker_count,
        "field_counts": audit.field_counts,
        "raw_totals": audit.raw_totals,
        "issues": [issue.to_dict() for issue in audit.issues],
        "warning": "raw_totals are diagnostic and are not consolidated campaign books",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit a read-only JSON export of the Baen Business Registry"
    )
    parser.add_argument("export", type=Path, help="JSON array or object containing rows/results")
    args = parser.parse_args(argv)
    payload = json.loads(args.export.read_text(encoding="utf-8"))
    print(json.dumps(audit_export(payload), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
