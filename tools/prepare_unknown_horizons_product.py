#!/usr/bin/env python3
"""Acquire the exact Unknown Horizons product used by Baen's process bridge."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess

REPO = "https://github.com/unknown-horizons/unknown-horizons.git"
COMMIT = "af9c8ef5c7f6cf9ec0b8c9e7d172c555f2793615"


def run(command: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def output(command: list[str], *, cwd: Path | None = None) -> str:
    return subprocess.check_output(command, cwd=cwd, text=True).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, default=Path(".upstream/unknown-horizons"))
    args = parser.parse_args()
    if not shutil.which("git"):
        raise SystemExit("git is required")
    checkout = args.checkout.resolve()
    if not checkout.exists():
        checkout.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", REPO, str(checkout)])
    if not (checkout / ".git").is_dir():
        raise SystemExit(f"{checkout} is not a git checkout")
    run(["git", "fetch", "origin", COMMIT], cwd=checkout)
    run(["git", "checkout", "--detach", COMMIT], cwd=checkout)
    actual = output(["git", "rev-parse", "HEAD"], cwd=checkout)
    if actual != COMMIT:
        raise SystemExit(f"Unknown Horizons checkout mismatch: expected {COMMIT}, got {actual}")
    target = checkout / "horizons/world/production/productionline.py"
    if not target.is_file():
        raise SystemExit("pinned checkout lacks ProductionLine")
    print(f"Unknown Horizons {COMMIT} ready at {checkout}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
