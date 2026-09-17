#!/usr/bin/env python3
"""Acquire and build the exact OpenTTD dedicated-server product used by Baen."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess

REPO = "https://github.com/OpenTTD/OpenTTD.git"
COMMIT = "1aca0b60a8024f295e1d0ad2a3407b3dac838099"


def run(command: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def output(command: list[str], *, cwd: Path | None = None) -> str:
    return subprocess.check_output(command, cwd=cwd, text=True).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, default=Path(".upstream/openttd"))
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()
    if args.jobs < 1:
        raise SystemExit("--jobs must be positive")
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
        raise SystemExit(f"OpenTTD checkout mismatch: expected {COMMIT}, got {actual}")
    build = checkout / "build-baen-dedicated"
    if not args.skip_build:
        if not shutil.which("cmake"):
            raise SystemExit("cmake is required")
        run([
            "cmake", "-S", str(checkout), "-B", str(build),
            "-DOPTION_DEDICATED=ON", "-DCMAKE_BUILD_TYPE=Release",
            "-DOPTION_USE_ASSERTS=ON",
        ])
        run(["cmake", "--build", str(build), "--target", "openttd", "-j", str(args.jobs)])
    binary = build / "openttd"
    if not binary.is_file():
        raise SystemExit(f"OpenTTD dedicated binary was not produced: {binary}")
    print(f"OpenTTD {COMMIT} ready at {binary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
