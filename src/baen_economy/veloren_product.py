"""Process bridge to the actual pinned Veloren economy.

Veloren's economy is part of the GPL-3.0 `veloren-world` Rust crate.  The
upstream crate exposes the simulation itself but not enough setters to inject an
external economy state.  `tools/prepare_veloren_product.py` therefore applies a
minimal GPL-side patch to the pinned checkout that exposes population/stock
seeding; simulation remains Veloren's existing `Economy::tick` implementation.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess

VELOREN_COMMIT = "e633eb8ca15ae97bb5ef5a039fcf6844e96ad704"
VELOREN_PATCH_VERSION = 1


class VelorenProductError(RuntimeError):
    """The pinned/patched Veloren product cannot execute the requested preview."""


@dataclass(frozen=True, slots=True)
class VelorenEconomyResult:
    upstream: str
    upstream_commit: str
    patch_version: int
    population: int
    food_stock: float
    coin_stock: float
    food_price: float
    simulated_days: float
    canonical_time_advanced: bool = False


def run_veloren_economy(
    checkout: Path | str,
    *,
    population: float,
    food_stock: float,
    coin_stock: float,
    days: float,
    timeout: float = 30.0,
) -> VelorenEconomyResult:
    root = Path(checkout).resolve()
    if any(type(value) not in {int, float} for value in (population, food_stock, coin_stock, days)):
        raise ValueError("Veloren numeric inputs must be int/float")
    if population < 0 or food_stock < 0 or coin_stock < 0 or days <= 0:
        raise ValueError("Veloren stocks/population must be non-negative and days positive")
    if type(timeout) not in {int, float} or timeout <= 0:
        raise ValueError("timeout must be positive")
    try:
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, timeout=timeout
        ).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise VelorenProductError("cannot verify Veloren checkout") from exc
    if head != VELOREN_COMMIT:
        raise VelorenProductError(f"Veloren checkout must be {VELOREN_COMMIT}; found {head}")
    marker_path = root / ".baen-economy-product-patch.json"
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VelorenProductError("Veloren checkout lacks verified Baen GPL-side patch marker") from exc
    if marker != {"patch_version": VELOREN_PATCH_VERSION, "upstream_commit": VELOREN_COMMIT}:
        raise VelorenProductError("Veloren GPL-side patch marker does not match expected revision")
    binary = root / "target/debug/examples/baen_economy_bridge"
    if not binary.is_file():
        raise VelorenProductError("Veloren Baen economy bridge binary has not been built")
    env = dict(
        os.environ,
        VELOREN_ASSETS=str(root / "assets"),
        DISABLE_GIT_LFS_CHECK="true",
    )
    try:
        completed = subprocess.run(
            [str(binary), str(float(population)), str(float(food_stock)),
             str(float(coin_stock)), str(float(days))],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise VelorenProductError("Veloren economy bridge failed to start") from exc
    if completed.returncode != 0:
        raise VelorenProductError("Veloren economy bridge failed: " + completed.stderr.strip())
    line = next(
        (candidate.strip() for candidate in reversed(completed.stdout.splitlines())
         if candidate.startswith("population=")),
        None,
    )
    if line is None:
        raise VelorenProductError("Veloren economy bridge returned no parseable economy result")
    fields = {}
    for pair in line.split(";"):
        if "=" not in pair:
            raise VelorenProductError("Veloren economy result is malformed")
        key, value = pair.split("=", 1)
        fields[key] = value
    required = {"population", "food", "coin", "food_price", "days"}
    if set(fields) != required:
        raise VelorenProductError("Veloren economy result fields changed")
    try:
        return VelorenEconomyResult(
            upstream="Veloren",
            upstream_commit=VELOREN_COMMIT,
            patch_version=VELOREN_PATCH_VERSION,
            population=int(fields["population"]),
            food_stock=float(fields["food"]),
            coin_stock=float(fields["coin"]),
            food_price=float(fields["food_price"]),
            simulated_days=float(fields["days"]),
            canonical_time_advanced=False,
        )
    except ValueError as exc:
        raise VelorenProductError("Veloren economy result contains invalid numeric data") from exc
