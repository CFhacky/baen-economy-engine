#!/usr/bin/env python3
"""CI-only launcher for one all-products Baen Empire preview.

All upstream checkouts must already be prepared. This helper starts the two
service products (Brunnfeld and OpenTTD), runs the same empire orchestrator used
by baen-empire, writes the combined report, and tears the services down.
"""
from __future__ import annotations

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
from baen_economy.empire_orchestrator import render_empire_month, run_empire_month


def wait_port(port: int, name: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.25)
    raise RuntimeError(f"{name} port did not open")


def main() -> int:
    required = {
        "BRUNNFELD_CHECKOUT",
        "UNKNOWN_HORIZONS_CHECKOUT",
        "FREECOL_CHECKOUT",
        "VELOREN_CHECKOUT",
        "OPENTTD_CHECKOUT",
        "OPENTTD_BASESET_DIR",
    }
    missing = sorted(name for name in required if not os.environ.get(name))
    if missing:
        raise SystemExit("missing product paths: " + ", ".join(missing))

    brunnfeld = Path(os.environ["BRUNNFELD_CHECKOUT"]).resolve()
    openttd = Path(os.environ["OPENTTD_CHECKOUT"]).resolve()
    baseset = Path(os.environ["OPENTTD_BASESET_DIR"]).resolve()
    if not baseset.is_dir():
        raise SystemExit(f"OpenTTD base-set directory is missing: {baseset}")

    children: list[subprocess.Popen] = []
    with tempfile.TemporaryDirectory(prefix="baen-e2e-products-") as temp:
        tempdir = Path(temp)

        brunnfeld_log = (tempdir / "brunnfeld.log").open("w", encoding="utf-8")
        br_env = dict(os.environ, PORT="3333")
        br = subprocess.Popen(
            ["npm", "run", "server"],
            cwd=brunnfeld,
            env=br_env,
            stdout=brunnfeld_log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        children.append(br)

        ottd_root = tempdir / "openttd"
        ottd_root.mkdir()
        local_baseset = ottd_root / "baseset"
        try:
            local_baseset.symlink_to(baseset, target_is_directory=True)
        except OSError:
            shutil.copytree(baseset, local_baseset)
        version = "[version]\nini_version = 8\n\n"
        (ottd_root / "openttd.cfg").write_text(
            version
            + "[network]\n"
            + "server_port = 3979\n"
            + "server_admin_port = 3977\n"
            + "allow_insecure_admin_login = true\n"
            + "server_game_type = local\n"
            + "server_name = Baen Empire E2E\n",
            encoding="utf-8",
        )
        admin_secret = "baen-e2e-admin"
        (ottd_root / "secrets.cfg").write_text(
            version + "[network]\n" + f"admin_password = {admin_secret}\n",
            encoding="utf-8",
        )
        ottd_log = (tempdir / "openttd.log").open("w", encoding="utf-8")
        binary = openttd / "build-baen-dedicated" / "openttd"
        ot = subprocess.Popen(
            [
                str(binary), "-D", "127.0.0.1:3979",
                "-c", str(ottd_root / "openttd.cfg"),
                "-g", "-G", "424242", "-x", "-d", "net=1",
            ],
            cwd=ottd_root,
            stdin=subprocess.DEVNULL,
            stdout=ottd_log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        children.append(ot)

        try:
            wait_port(3333, "Brunnfeld")
            wait_port(3977, "OpenTTD admin")
            os.environ["BRUNNFELD_URL"] = "http://127.0.0.1:3333"
            os.environ["OPENTTD_ADMIN_HOST"] = "127.0.0.1"
            os.environ["OPENTTD_ADMIN_PORT"] = "3977"
            os.environ["OPENTTD_ADMIN_PASSWORD"] = admin_secret
            payload = run_empire_month(seed="hammer-1495-e2e", require_products=True)

            statuses = {name: row.get("status") for name, row in payload["products"].items()}
            if set(statuses) != {"mesa", "brunnfeld", "unknown_horizons", "freecol", "veloren", "openttd"}:
                raise RuntimeError("product result set is incomplete")
            incomplete = {name: value for name, value in statuses.items() if value != "USED_IN_RUN"}
            if incomplete:
                raise RuntimeError(
                    "one or more upstream products did not consume mapped Baen input: "
                    + json.dumps(incomplete, sort_keys=True)
                )
            checks = payload["integrity"]
            for key in (
                "physical_conservation",
                "nonnegative_balances",
                "ledger_balanced",
                "deposit_liabilities_reconcile",
                "interest_receivables_reconcile",
                "collateral_assets_reconcile",
                "bank_balance_sheets_balance",
            ):
                if not checks.get(key):
                    raise RuntimeError(f"Baen whole-economy integrity failed: {key}")

            reports = PROJECT / "reports"
            reports.mkdir(exist_ok=True)
            json_path = reports / "Empire-E2E-Preview.json"
            md_path = reports / "Empire-E2E-Preview.md"
            json_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n",
                encoding="utf-8",
            )
            md_path.write_text(render_empire_month(payload), encoding="utf-8")
            print(json.dumps({
                "ok": True,
                "product_statuses": statuses,
                "production_receipts": len(payload["baen_core"].get("production", [])),
                "trade_receipts": len(payload["baen_core"].get("trade", [])),
                "banking_receipts": len(payload["baen_core"].get("banking", [])),
                "migration_receipts": len(payload["baen_core"].get("migration", [])),
                "blockers": payload["blockers"],
                "report": str(md_path),
            }, indent=2, sort_keys=True))
            print(md_path.read_text(encoding="utf-8"))
        finally:
            for child in reversed(children):
                if child.poll() is None:
                    try:
                        os.killpg(child.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
            for child in reversed(children):
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    child.wait(timeout=5)
            brunnfeld_log.close()
            ottd_log.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
