#!/usr/bin/env python3
"""Run real validation and save inspectable receipts; never run a campaign month."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone

PROJECT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT / "recovery/validation/20260917"


def run(name: str, command: list[str], env: dict[str, str]) -> dict:
    result = subprocess.run(command, cwd=PROJECT, env=env, text=True,
                            capture_output=True, timeout=600, check=False)
    text = result.stdout + result.stderr
    print("\n=== " + name + " ===\n" + text, flush=True)
    path = OUTPUT / (name + ".txt")
    path.write_text(text, encoding="utf-8")
    match = re.search(r"Ran (\d+) tests? in", text)
    return {"name": name, "command": command, "returncode": result.returncode,
            "tests_run": int(match.group(1)) if match else None,
            "log_path": str(path.relative_to(PROJECT)),
            "log_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONPATH=str(PROJECT / "src"))
    suites = [run("focused-census", [sys.executable, "-m", "unittest", "discover",
        "-s", "tests", "-p", "test_*census*.py", "-v"], env),
        run("engine-suite", [sys.executable, "-m", "unittest", "discover",
        "-s", "tests", "-p", "test_*.py"], env)]
    check = subprocess.run([sys.executable, "tools/materialize_live_census.py", "--check"],
        cwd=PROJECT, env=env, text=True, capture_output=True, timeout=120, check=False)
    print("=== deterministic regeneration ===\n" + check.stdout + check.stderr, flush=True)
    coverage = subprocess.run([sys.executable, "-m", "baen_economy.operator_cli", "coverage-check",
        "recovery/LIVE_EMPIRE_SOURCE_CENSUS_2026-09-17.json"], cwd=PROJECT, env=env,
        text=True, capture_output=True, timeout=120, check=False)
    coverage_path = OUTPUT / "coverage-check.json"
    coverage_path.write_text(coverage.stdout, encoding="utf-8")
    try:
        report = json.loads(coverage.stdout)
    except json.JSONDecodeError:
        report = {"gate": "INVALID", "error": coverage.stderr}
    expected_closed = coverage.returncode == 2 and report.get("gate") == "CLOSED"
    passed = all(s["returncode"] == 0 for s in suites) and check.returncode == 0 and expected_closed
    input_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip()
    tracked_files = [*sorted((PROJECT / "src").rglob("*.py")),
                     *sorted((PROJECT / "tests").rglob("*.py")),
                     *sorted((PROJECT / "tools").glob("*.py"))]
    code_hashes = {str(p.relative_to(PROJECT)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in tracked_files}
    acquisition = json.loads((PROJECT / "recovery/LIVE_CENSUS_ACQUISITION_MANIFEST_2026-09-17.json").read_text())
    result = {"schema": "tnp.economy.census-validation/1", "passed": passed,
        "validated_at": datetime.now(timezone.utc).isoformat(), "input_commit_sha": input_sha,
        "scope": "Exact checked-out source plus generated census outputs; synthetic unit fixtures are not campaign-time advancement",
        "suites": suites, "deterministic_regeneration": {"returncode": check.returncode,
            "passed": check.returncode == 0},
        "coverage_check": {"returncode": coverage.returncode, "expected_returncode": 2,
            "gate": report.get("gate"), "passed": expected_closed,
            "path": str(coverage_path.relative_to(PROJECT)),
            "sha256": hashlib.sha256(coverage_path.read_bytes()).hexdigest()},
        "live_materialized_records": acquisition["live_materialized_records"],
        "collection_enumeration": acquisition["complete_collections"],
        "snapshot_hash": acquisition["snapshot_hash"],
        "core_coverage_counts": acquisition["core_coverage_counts"],
        "source_and_test_file_sha256": code_hashes,
        "notion_writes": 0, "campaign_month_operations": 0}
    (OUTPUT / "verification.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "source_and_test_file_sha256"}, indent=2), flush=True)
    return 0 if passed else 1

if __name__ == "__main__":
    raise SystemExit(main())
