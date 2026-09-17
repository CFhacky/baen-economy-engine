"""Separate-process bridge to the actual Unknown Horizons production product.

Unknown Horizons is GPL-2.0-or-later and ships as a full Python game rather than
an embeddable service.  Baen therefore does not copy ``ProductionLine`` or import
it into the MIT engine process.  Instead, this module executes the exact pinned
upstream checkout in a child Python process and exchanges JSON.

Pinned upstream: unknown-horizons/unknown-horizons
commit af9c8ef5c7f6cf9ec0b8c9e7d172c555f2793615.

The bridge currently exposes the real ``horizons.world.production.productionline.ProductionLine``
contract.  It is preview/validation infrastructure only and cannot advance the
canonical campaign clock.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Iterable

UNKNOWN_HORIZONS_COMMIT = "af9c8ef5c7f6cf9ec0b8c9e7d172c555f2793615"


class UnknownHorizonsProductError(RuntimeError):
    """The pinned Unknown Horizons product could not execute the requested model."""


@dataclass(frozen=True, slots=True)
class UnknownHorizonsProductionLine:
    """Output read from the actual upstream ``ProductionLine`` instance."""

    upstream: str
    upstream_commit: str
    line_id: int
    time: float
    production: dict[int, float]
    produced: dict[int, float]
    consumed: dict[int, float]
    units: dict[int, float]
    canonical_time_advanced: bool = False


_BRIDGE = r'''
import json
import sys
from horizons.world.production.productionline import ProductionLine

payload = json.load(sys.stdin)
line = ProductionLine(payload["line_id"], payload["data"])
json.dump({
    "line_id": line.id,
    "time": line.time,
    "production": line.production,
    "produced": line.produced_res,
    "consumed": line.consumed_res,
    "units": line.unit_production,
}, sys.stdout, sort_keys=True)
'''


def _pairs(values: Iterable[tuple[int, float]], label: str) -> list[list[float | int]]:
    result: list[list[float | int]] = []
    seen: set[int] = set()
    for resource, amount in values:
        if type(resource) is not int or resource < 0:
            raise ValueError(f"{label} resource IDs must be non-negative integers")
        if resource in seen:
            raise ValueError(f"duplicate {label} resource ID: {resource}")
        seen.add(resource)
        if type(amount) not in {int, float}:
            raise ValueError(f"{label} amounts must be numeric")
        result.append([resource, amount])
    return result


def run_unknown_horizons_production_line(
    checkout: Path | str,
    *,
    line_id: int,
    produces: Iterable[tuple[int, float]] = (),
    consumes: Iterable[tuple[int, float]] = (),
    time: float = 1.0,
    python: str | None = None,
    timeout: float = 20.0,
) -> UnknownHorizonsProductionLine:
    """Instantiate the real pinned Unknown Horizons ``ProductionLine``.

    ``checkout`` must be a detached checkout at the pinned commit.  The function
    validates its Git HEAD before executing upstream code.  Resource values are
    deliberately generic; Baen source-to-resource mapping remains a separate,
    explicit authority decision.
    """

    root = Path(checkout).resolve()
    if type(line_id) is not int or line_id < 0:
        raise ValueError("line_id must be a non-negative integer")
    if type(time) not in {int, float} or time <= 0:
        raise ValueError("production time must be positive")
    if type(timeout) not in {int, float} or timeout <= 0:
        raise ValueError("timeout must be positive")
    if not (root / "horizons/world/production/productionline.py").is_file():
        raise UnknownHorizonsProductError("checkout does not contain Unknown Horizons ProductionLine")
    try:
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, timeout=timeout
        ).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise UnknownHorizonsProductError("cannot verify Unknown Horizons checkout") from exc
    if head != UNKNOWN_HORIZONS_COMMIT:
        raise UnknownHorizonsProductError(
            f"Unknown Horizons checkout must be {UNKNOWN_HORIZONS_COMMIT}; found {head}"
        )

    payload = {
        "line_id": line_id,
        "data": {
            "time": time,
            "produces": _pairs(produces, "produces"),
            "consumes": _pairs(consumes, "consumes"),
        },
    }
    executable = python or sys.executable
    with tempfile.TemporaryDirectory(prefix="baen-uh-") as temp:
        env = dict(os.environ)
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(root) if not existing else str(root) + os.pathsep + existing
        # Keep any UH user-directory initialization out of the caller's profile.
        env["UH_USER_DIR"] = temp
        try:
            completed = subprocess.run(
                [executable, "-c", _BRIDGE],
                input=json.dumps(payload),
                text=True,
                capture_output=True,
                env=env,
                cwd=root,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise UnknownHorizonsProductError("Unknown Horizons child process failed to start") from exc
    if completed.returncode != 0:
        raise UnknownHorizonsProductError(
            "Unknown Horizons product process failed: " + completed.stderr.strip()
        )
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise UnknownHorizonsProductError("Unknown Horizons returned non-JSON output") from exc

    def integer_keyed(name: str) -> dict[int, float]:
        value = result.get(name)
        if not isinstance(value, dict):
            raise UnknownHorizonsProductError(f"Unknown Horizons result lacks {name}")
        return {int(key): float(amount) for key, amount in value.items()}

    return UnknownHorizonsProductionLine(
        upstream="Unknown Horizons",
        upstream_commit=UNKNOWN_HORIZONS_COMMIT,
        line_id=int(result["line_id"]),
        time=float(result["time"]),
        production=integer_keyed("production"),
        produced=integer_keyed("produced"),
        consumed=integer_keyed("consumed"),
        units=integer_keyed("units"),
        canonical_time_advanced=False,
    )
