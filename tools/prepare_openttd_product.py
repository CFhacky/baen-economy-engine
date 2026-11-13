#!/usr/bin/env python3
"""Acquire/build pinned OpenTTD with the narrow GPL-side Baen transport seam.

The patch does not reimplement OpenTTD transport economics. It registers one
server console command that calls OpenTTD's existing GetTransportedGoodsIncome
so Baen can submit route/cargo preview inputs through the real product over rcon.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess

REPO = "https://github.com/OpenTTD/OpenTTD.git"
COMMIT = "1aca0b60a8024f295e1d0ad2a3407b3dac838099"
PATCH_VERSION = 1

INCLUDE_MARKER = '#include "engine_func.h"\n'
INCLUDE_INSERT = '#include "engine_func.h"\n#include "economy_func.h"\n'

FUNCTION_MARKER = '#ifdef _DEBUG\n/******************\n *  debug commands\n ******************/\n'
FUNCTION_INSERT = r'''/** Baen GPL-side adapter: call OpenTTD's real cargo-income function. */
static bool ConBaenTransportIncome(std::span<std::string_view> argv)
{
	if (argv.empty()) {
		IConsolePrint(CC_HELP, "Calculate OpenTTD transport income. Usage: 'baen_transport_income <cargo-id> <pieces> <distance-tiles> <days-in-transit>'.");
		return true;
	}
	if (argv.size() != 5) return false;

	auto cargo = ParseType<CargoType>(argv[1]);
	auto pieces = ParseType<uint>(argv[2]);
	auto distance = ParseType<uint>(argv[3]);
	auto days = ParseType<uint32_t>(argv[4]);
	if (!cargo.has_value() || !pieces.has_value() || !distance.has_value() || !days.has_value()) {
		IConsolePrint(CC_ERROR, "baen_transport_income requires four non-negative integer arguments.");
		return true;
	}

	uint64_t periods64 = static_cast<uint64_t>(*days) * 2 / 5;
	uint16_t periods = static_cast<uint16_t>(std::min<uint64_t>(periods64, UINT16_MAX));
	Money income = GetTransportedGoodsIncome(*pieces, *distance, periods, *cargo);
	IConsolePrint(
		CC_DEFAULT,
		"BAEN_TRANSPORT_INCOME cargo={} pieces={} distance={} days={} income={}",
		static_cast<uint>(*cargo), *pieces, *distance, *days, income
	);
	return true;
}

'''

REGISTER_MARKER = '	IConsole::CmdRegister("getsysdate",              ConGetSysDate);\n'
REGISTER_INSERT = REGISTER_MARKER + '	IConsole::CmdRegister("baen_transport_income", ConBaenTransportIncome, ConHookServerOrNoNetwork);\n'


def run(command: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def output(command: list[str], *, cwd: Path | None = None) -> str:
    return subprocess.check_output(command, cwd=cwd, text=True).strip()


def patch_checkout(checkout: Path) -> None:
    path = checkout / "src/console_cmds.cpp"
    text = path.read_text(encoding="utf-8")
    if INCLUDE_INSERT not in text:
        if INCLUDE_MARKER not in text:
            raise SystemExit("OpenTTD include patch marker changed; refusing fuzzy patch")
        text = text.replace(INCLUDE_MARKER, INCLUDE_INSERT, 1)
    if "static bool ConBaenTransportIncome" not in text:
        if FUNCTION_MARKER not in text:
            raise SystemExit("OpenTTD function patch marker changed; refusing fuzzy patch")
        text = text.replace(FUNCTION_MARKER, FUNCTION_INSERT + FUNCTION_MARKER, 1)
    if 'CmdRegister("baen_transport_income"' not in text:
        if REGISTER_MARKER not in text:
            raise SystemExit("OpenTTD registration patch marker changed; refusing fuzzy patch")
        text = text.replace(REGISTER_MARKER, REGISTER_INSERT, 1)
    path.write_text(text, encoding="utf-8")
    (checkout / ".baen-economy-product-patch.json").write_text(
        json.dumps({"upstream_commit": COMMIT, "patch_version": PATCH_VERSION}, sort_keys=True) + "\n",
        encoding="utf-8",
    )


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
    run(["git", "checkout", "--detach", "--force", COMMIT], cwd=checkout)
    run(["git", "reset", "--hard", COMMIT], cwd=checkout)
    run(["git", "clean", "-fdx"], cwd=checkout)
    actual = output(["git", "rev-parse", "HEAD"], cwd=checkout)
    if actual != COMMIT:
        raise SystemExit(f"OpenTTD checkout mismatch: expected {COMMIT}, got {actual}")
    patch_checkout(checkout)
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
    print(f"OpenTTD {COMMIT} patched product ready at {binary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
