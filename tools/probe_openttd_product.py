#!/usr/bin/env python3
"""Boot the exact pinned OpenTTD dedicated product and probe its admin API."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
from baen_economy.openttd_product import OpenTTDAdminClient, OPENTTD_COMMIT


def wait_port(host: str, port: int, process: subprocess.Popen, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"OpenTTD exited early with code {process.returncode}")
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("OpenTTD admin port did not open")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--baseset-dir", type=Path, required=True)
    parser.add_argument("--admin-port", type=int, default=3977)
    parser.add_argument("--server-port", type=int, default=3979)
    parser.add_argument("--password", default="baen-ci-admin")
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()
    for value in (args.admin_port, args.server_port):
        if not 1 <= value <= 65535:
            raise SystemExit("ports must be 1..65535")
    checkout = args.checkout.resolve()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=checkout, text=True).strip()
    if head != OPENTTD_COMMIT:
        raise SystemExit(f"OpenTTD checkout mismatch: expected {OPENTTD_COMMIT}, got {head}")
    binary = checkout / "build-baen-dedicated" / "openttd"
    if not binary.is_file():
        raise SystemExit("OpenTTD dedicated binary has not been built")
    baseset = args.baseset_dir.resolve()
    if not baseset.is_dir():
        raise SystemExit(f"base-set directory does not exist: {baseset}")

    with tempfile.TemporaryDirectory(prefix="baen-openttd-") as temp:
        root = Path(temp)
        config = root / "openttd.cfg"
        secrets = root / "secrets.cfg"
        local_baseset = root / "baseset"
        try:
            local_baseset.symlink_to(baseset, target_is_directory=True)
        except OSError:
            shutil.copytree(baseset, local_baseset)
        config.write_text(
            "[network]\n"
            f"server_port = {args.server_port}\n"
            f"server_admin_port = {args.admin_port}\n"
            "allow_insecure_admin_login = true\n"
            "server_game_type = local\n"
            "server_name = Baen OpenTTD Product Probe\n",
            encoding="utf-8",
        )
        secrets.write_text(
            "[network]\n" f"admin_password = {args.password}\n",
            encoding="utf-8",
        )
        command = [
            str(binary),
            "-D", f"127.0.0.1:{args.server_port}",
            "-c", str(config),
            "-g",
            "-G", "424242",
            "-x",
            "-d", "net=1",
        ]
        process = subprocess.Popen(
            command,
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            wait_port("127.0.0.1", args.admin_port, process, args.timeout)
            with OpenTTDAdminClient(
                "127.0.0.1", args.admin_port, password=args.password, timeout=5.0
            ) as client:
                snapshot = client.snapshot()
            result = {
                "upstream": snapshot.upstream,
                "upstream_commit": snapshot.upstream_commit,
                "protocol_version": snapshot.protocol_version,
                "server_name": snapshot.server_name,
                "revision": snapshot.revision,
                "dedicated": snapshot.dedicated,
                "generation_seed": snapshot.generation_seed,
                "landscape": snapshot.landscape,
                "start_date": snapshot.start_date,
                "map_width": snapshot.map_width,
                "map_height": snapshot.map_height,
                "current_date": snapshot.current_date,
                "company_economy_records": [asdict(company) for company in snapshot.companies],
                "rcon_output": list(snapshot.rcon_output),
                "canonical_time_advanced": snapshot.canonical_time_advanced,
            }
            print(json.dumps(result, indent=2, sort_keys=True))
            if not snapshot.dedicated:
                raise RuntimeError("OpenTTD product did not report dedicated-server mode")
            if snapshot.upstream_commit != OPENTTD_COMMIT:
                raise RuntimeError("OpenTTD result commit mismatch")
            if snapshot.canonical_time_advanced:
                raise RuntimeError("OpenTTD preview incorrectly claims canonical time advancement")
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
            output = process.stdout.read() if process.stdout is not None else ""
            if process.returncode not in (0, -signal.SIGTERM):
                print(output, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
