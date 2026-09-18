"""Deterministic resolution of non-canonical simulation parameters.

Campaign facts and user rulings remain authoritative elsewhere. This module only
resolves MODEL-PROPOSED priors that allow the simulator to run when a detail has
not yet been enumerated in campaign canon.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import math
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = (
    PROJECT_ROOT / "recovery/SIMULATION_PARAMETER_CATALOG_2026-09-17.json"
)


class SimulationParameterError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ResolvedParameter:
    id: str
    value: float | int
    unit: str
    authority: str
    confidence: str
    sensitivity: str
    needs_enumeration: bool
    basis: tuple[str, ...]
    distribution: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "value": self.value,
            "unit": self.unit,
            "authority": self.authority,
            "confidence": self.confidence,
            "sensitivity": self.sensitivity,
            "needs_enumeration": self.needs_enumeration,
            "basis": list(self.basis),
            "distribution": self.distribution,
        }


def load_catalog(path: Path = DEFAULT_CATALOG) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SimulationParameterError(f"cannot read parameter catalog: {path}: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != "tnp.economy.simulation-parameter-catalog/1":
        raise SimulationParameterError("simulation parameter catalog schema is unsupported")
    params = payload.get("parameters")
    if not isinstance(params, list) or not params:
        raise SimulationParameterError("simulation parameter catalog has no parameters")
    seen: set[str] = set()
    for row in params:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            raise SimulationParameterError("simulation parameter entry is malformed")
        if row["id"] in seen:
            raise SimulationParameterError(f"duplicate simulation parameter: {row['id']}")
        seen.add(row["id"])
    return payload


def _u01(seed: str, parameter_id: str, draw: int = 0) -> float:
    key = hashlib.sha256(seed.encode("utf-8")).digest()
    message = f"baen-sim-parameter\x1f{parameter_id}\x1f{draw}".encode("utf-8")
    digest = hmac.new(key, message, hashlib.sha256).digest()
    number = int.from_bytes(digest[:8], "big")
    return (number + 0.5) / (2**64)


def _triangular(u: float, low: float, mode: float, high: float) -> float:
    if not low <= mode <= high or low == high:
        raise SimulationParameterError("triangular parameter requires low <= mode <= high and low < high")
    c = (mode - low) / (high - low)
    if u < c:
        return low + math.sqrt(u * (high - low) * (mode - low))
    return high - math.sqrt((1 - u) * (high - low) * (high - mode))


def _numeric(value: object, label: str) -> float:
    if type(value) is bool or not isinstance(value, (int, float)):
        raise SimulationParameterError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise SimulationParameterError(f"{label} must be finite")
    return result


def resolve_parameter(
    parameter_id: str,
    *,
    seed: str,
    catalog_path: Path = DEFAULT_CATALOG,
) -> ResolvedParameter:
    if not seed:
        raise SimulationParameterError("seed is required")
    payload = load_catalog(catalog_path)
    row = next((item for item in payload["parameters"] if item["id"] == parameter_id), None)
    if row is None:
        raise SimulationParameterError(f"unknown simulation parameter: {parameter_id}")

    distribution = str(row.get("distribution") or "")
    if distribution == "triangular":
        low = _numeric(row.get("low"), f"{parameter_id}.low")
        mode = _numeric(row.get("mode"), f"{parameter_id}.mode")
        high = _numeric(row.get("high"), f"{parameter_id}.high")
        value: float | int = _triangular(_u01(seed, parameter_id), low, mode, high)
    elif distribution == "uniform":
        low = _numeric(row.get("low"), f"{parameter_id}.low")
        high = _numeric(row.get("high"), f"{parameter_id}.high")
        if low > high:
            raise SimulationParameterError("uniform parameter requires low <= high")
        value = low + _u01(seed, parameter_id) * (high - low)
    elif distribution == "choice":
        choices = row.get("choices")
        weights = row.get("weights")
        if not isinstance(choices, list) or not choices:
            raise SimulationParameterError(f"{parameter_id} has no choices")
        if weights is None:
            weights = [1.0] * len(choices)
        if not isinstance(weights, list) or len(weights) != len(choices):
            raise SimulationParameterError(f"{parameter_id} weights do not match choices")
        numeric_weights = [_numeric(v, f"{parameter_id}.weight") for v in weights]
        if any(v < 0 for v in numeric_weights) or sum(numeric_weights) <= 0:
            raise SimulationParameterError(f"{parameter_id} weights are invalid")
        u = _u01(seed, parameter_id) * sum(numeric_weights)
        cumulative = 0.0
        selected = choices[-1]
        for choice, weight in zip(choices, numeric_weights, strict=True):
            cumulative += weight
            if u <= cumulative:
                selected = choice
                break
        if type(selected) is bool or not isinstance(selected, (int, float)):
            raise SimulationParameterError(f"{parameter_id} choices must be numeric")
        value = selected
    elif distribution == "fixed":
        value = _numeric(row.get("value"), f"{parameter_id}.value")
    else:
        raise SimulationParameterError(f"unsupported distribution for {parameter_id}: {distribution}")

    # Preserve integers when the catalog is integer-valued and the resolved value lands on one.
    if distribution in {"choice", "fixed"} and isinstance(value, float) and value.is_integer():
        value = int(value)

    basis = row.get("basis") or []
    if not isinstance(basis, list) or not all(isinstance(item, str) for item in basis):
        raise SimulationParameterError(f"{parameter_id} basis must be a string list")
    return ResolvedParameter(
        id=parameter_id,
        value=value,
        unit=str(row.get("unit") or ""),
        authority=str(row.get("authority") or "MODEL-PROPOSED"),
        confidence=str(row.get("confidence") or "unknown"),
        sensitivity=str(row.get("sensitivity") or "unknown"),
        needs_enumeration=bool(row.get("needs_enumeration")),
        basis=tuple(basis),
        distribution=distribution,
    )


def resolve_catalog(
    *,
    seed: str,
    catalog_path: Path = DEFAULT_CATALOG,
) -> dict[str, Any]:
    payload = load_catalog(catalog_path)
    resolved = [
        resolve_parameter(row["id"], seed=seed, catalog_path=catalog_path).to_dict()
        for row in payload["parameters"]
    ]
    debt = [row for row in resolved if row["needs_enumeration"]]
    return {
        "schema": "tnp.economy.simulation-parameter-resolution/1",
        "seed_fingerprint": hashlib.sha256(seed.encode("utf-8")).hexdigest(),
        "parameter_count": len(resolved),
        "needs_enumeration_count": len(debt),
        "parameters": resolved,
        "needs_enumeration": [row["id"] for row in debt],
        "policy": payload["policy"],
    }


def resolve_map(
    *,
    seed: str,
    catalog_path: Path = DEFAULT_CATALOG,
) -> dict[str, float | int]:
    resolved = resolve_catalog(seed=seed, catalog_path=catalog_path)
    return {row["id"]: row["value"] for row in resolved["parameters"]}
