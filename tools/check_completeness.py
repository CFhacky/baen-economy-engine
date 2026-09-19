#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from baen_economy.completeness import completeness_report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report Baen Economy Engine completeness without advancing campaign state."
    )
    parser.add_argument(
        "--require-coverage-complete",
        action="store_true",
        help="exit nonzero unless the coverage proof is complete",
    )
    parser.add_argument(
        "--require-canonical-ready",
        action="store_true",
        help="exit nonzero unless canonical execution readiness is proven",
    )
    args = parser.parse_args()

    report = completeness_report()
    print(json.dumps(report, indent=2, sort_keys=True))

    if args.require_canonical_ready and not report["canonical_execution_ready"]:
        return 3
    if args.require_coverage_complete and not report["coverage_claim_allowed"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
