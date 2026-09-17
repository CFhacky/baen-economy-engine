#!/usr/bin/env python3
"""Acquire and build the exact FreeCol product used by Baen's JVM bridge."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess

REPO = "https://github.com/FreeCol/freecol.git"
COMMIT = "0a9e3cce950471fa67ae390d1a2fdf179e732092"


def run(command: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def output(command: list[str], *, cwd: Path | None = None) -> str:
    return subprocess.check_output(command, cwd=cwd, text=True).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, default=Path(".upstream/freecol"))
    parser.add_argument("--skip-build", action="store_true")
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
        raise SystemExit(f"FreeCol checkout mismatch: expected {COMMIT}, got {actual}")
    if not args.skip_build:
        if not shutil.which("ant"):
            raise SystemExit("Ant is required to build FreeCol")
        run(["ant", "package"], cwd=checkout)
    jar = checkout / "FreeCol.jar"
    if not jar.is_file():
        raise SystemExit("FreeCol.jar was not produced")
    print(f"FreeCol {COMMIT} ready at {checkout}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
