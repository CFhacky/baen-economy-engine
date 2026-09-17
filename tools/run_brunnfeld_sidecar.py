#!/usr/bin/env python3
"""Clone/build/run the exact Brunnfeld Agentic World product as a sidecar.

This tool deliberately uses the upstream product itself.  It does not vendor or
translate Brunnfeld's marketplace/production code into Baen.  The checkout is
pinned to the inspected commit and verified before `npm ci` / `npm run server`.

The Brunnfeld product includes Anthropic's SDK and may require its own runtime
credentials for agent execution.  Starting the HTTP server does not grant Baen
permission to advance canonical campaign time.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

REPO = "https://github.com/marcopatzelt/brunnfeld-agentic-world.git"
COMMIT = "e0656ca01630333e26c622ffd4ba4c973b79eebe"


def run(command: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def output(command: list[str], *, cwd: Path | None = None) -> str:
    return subprocess.check_output(command, cwd=cwd, text=True).strip()


def ensure_checkout(path: Path) -> None:
    if not shutil.which("git"):
        raise SystemExit("git is required to acquire the pinned Brunnfeld product")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", REPO, str(path)])
    if not (path / ".git").is_dir():
        raise SystemExit(f"{path} exists but is not a git checkout")
    run(["git", "fetch", "origin", COMMIT], cwd=path)
    run(["git", "checkout", "--detach", COMMIT], cwd=path)
    actual = output(["git", "rev-parse", "HEAD"], cwd=path)
    if actual != COMMIT:
        raise SystemExit(f"Brunnfeld checkout mismatch: expected {COMMIT}, got {actual}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--checkout",
        type=Path,
        default=Path(".upstream/brunnfeld-agentic-world"),
        help="where to keep the detached pinned upstream checkout",
    )
    parser.add_argument("--port", type=int, default=3333)
    parser.add_argument("--skip-install", action="store_true")
    parser.add_argument("--build-only", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit("--port must be 1..65535")
    if not shutil.which("npm"):
        raise SystemExit("npm is required to build/run the Brunnfeld product")

    checkout = args.checkout.resolve()
    ensure_checkout(checkout)
    if not args.skip_install:
        run(["npm", "ci"], cwd=checkout)
    run(["npm", "run", "build"], cwd=checkout)
    if args.build_only:
        print(f"Brunnfeld {COMMIT} built successfully at {checkout}")
        return 0

    env = dict(os.environ, PORT=str(args.port))
    print(f"Starting Brunnfeld {COMMIT} at http://127.0.0.1:{args.port}")
    # Replace this process so signals reach the upstream server directly.
    os.execvpe("npm", ["npm", "run", "server"], env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
