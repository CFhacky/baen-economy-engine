"""Separate JVM bridge to the actual pinned FreeCol product model.

FreeCol is GPL-2.0 and builds a complete ``FreeCol.jar``. Baen does not copy its
production classes. This bridge compiles a tiny temporary Java caller against the
exact upstream jar and executes FreeCol's real ``ProductionInfo``, ``GoodsType``
and ``AbstractGoods`` classes in a child JVM.

Pinned upstream: FreeCol/freecol
commit 0a9e3cce950471fa67ae390d1a2fdf179e732092.

This is preview/validation infrastructure. Resource IDs and quantities passed to
FreeCol remain scenario/source mappings and do not become canonical campaign
facts merely because FreeCol can calculate with them.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Mapping

FREECOL_COMMIT = "0a9e3cce950471fa67ae390d1a2fdf179e732092"


class FreeColProductError(RuntimeError):
    """The exact FreeCol product could not execute the requested model operation."""


@dataclass(frozen=True, slots=True)
class FreeColProductionResult:
    upstream: str
    upstream_commit: str
    actual: dict[str, int]
    maximum: dict[str, int]
    deficits: dict[str, int]
    canonical_time_advanced: bool = False


_JAVA = r'''
import java.util.*;
import net.sf.freecol.common.model.AbstractGoods;
import net.sf.freecol.common.model.GoodsType;
import net.sf.freecol.common.model.ProductionInfo;

public final class BaenFreeColBridge {
    private static String esc(String s) {
        return s.replace("\\", "\\\\").replace("\"", "\\\"");
    }
    private static String mapJson(List<AbstractGoods> goods) {
        StringBuilder b = new StringBuilder("{");
        boolean first = true;
        for (AbstractGoods g : goods) {
            if (!first) b.append(',');
            first = false;
            b.append('"').append(esc(g.getType().getId())).append('"')
             .append(':').append(g.getAmount());
        }
        return b.append('}').toString();
    }
    private static Map<String,Integer> parse(String raw) {
        Map<String,Integer> out = new LinkedHashMap<>();
        if (raw == null || raw.isEmpty()) return out;
        for (String pair : raw.split(",")) {
            String[] bits = pair.split("=", 2);
            if (bits.length != 2 || bits[0].isEmpty()) throw new IllegalArgumentException("bad pair");
            out.put(bits[0], Integer.valueOf(bits[1]));
        }
        return out;
    }
    public static void main(String[] args) {
        Map<String,Integer> actual = parse(args.length > 0 ? args[0] : "");
        Map<String,Integer> maximum = parse(args.length > 1 ? args[1] : "");
        Map<String,GoodsType> types = new LinkedHashMap<>();
        for (String id : actual.keySet()) types.put(id, new GoodsType(id, null));
        for (String id : maximum.keySet()) types.putIfAbsent(id, new GoodsType(id, null));
        ProductionInfo info = new ProductionInfo();
        for (Map.Entry<String,Integer> e : actual.entrySet())
            info.addProduction(new AbstractGoods(types.get(e.getKey()), e.getValue()));
        for (Map.Entry<String,Integer> e : maximum.entrySet())
            info.addMaximumProduction(new AbstractGoods(types.get(e.getKey()), e.getValue()));
        System.out.print("{\"actual\":" + mapJson(info.getProduction())
            + ",\"maximum\":" + mapJson(info.getMaximumProduction())
            + ",\"deficits\":" + mapJson(info.getProductionDeficit()) + "}");
    }
}
'''


def _encode(values: Mapping[str, int], label: str) -> str:
    parts: list[str] = []
    for key in sorted(values):
        amount = values[key]
        if not isinstance(key, str) or not key or any(ch in key for ch in ",="):
            raise ValueError(f"{label} keys must be non-empty text without ',' or '='")
        if type(amount) is not int:
            raise ValueError(f"{label} amounts must be integers")
        parts.append(f"{key}={amount}")
    return ",".join(parts)


def run_freecol_production_info(
    checkout: Path | str,
    *,
    actual: Mapping[str, int],
    maximum: Mapping[str, int],
    timeout: float = 30.0,
) -> FreeColProductionResult:
    """Execute FreeCol's real ``ProductionInfo`` deficit calculation."""

    root = Path(checkout).resolve()
    jar = root / "FreeCol.jar"
    if not jar.is_file():
        raise FreeColProductError("checkout does not contain a built FreeCol.jar")
    try:
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, timeout=timeout
        ).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise FreeColProductError("cannot verify FreeCol checkout") from exc
    if head != FREECOL_COMMIT:
        raise FreeColProductError(f"FreeCol checkout must be {FREECOL_COMMIT}; found {head}")
    javac = shutil.which("javac")
    java = shutil.which("java")
    if not javac or not java:
        raise FreeColProductError("Java JDK is required to execute FreeCol product classes")
    classpath = os.pathsep.join([str(jar), str(root / "jars" / "*")])
    with tempfile.TemporaryDirectory(prefix="baen-freecol-") as temp:
        work = Path(temp)
        source = work / "BaenFreeColBridge.java"
        source.write_text(_JAVA, encoding="utf-8")
        compiled = subprocess.run(
            [javac, "-cp", classpath, str(source)],
            cwd=work, text=True, capture_output=True, timeout=timeout, check=False,
        )
        if compiled.returncode != 0:
            raise FreeColProductError("FreeCol bridge compilation failed: " + compiled.stderr.strip())
        runtime_cp = os.pathsep.join([str(work), classpath])
        executed = subprocess.run(
            [java, "-cp", runtime_cp, "BaenFreeColBridge", _encode(actual, "actual"), _encode(maximum, "maximum")],
            cwd=work, text=True, capture_output=True, timeout=timeout, check=False,
        )
    if executed.returncode != 0:
        raise FreeColProductError("FreeCol product process failed: " + executed.stderr.strip())
    try:
        result = json.loads(executed.stdout)
    except json.JSONDecodeError as exc:
        raise FreeColProductError("FreeCol product returned non-JSON output") from exc
    for field in ("actual", "maximum", "deficits"):
        if not isinstance(result.get(field), dict):
            raise FreeColProductError(f"FreeCol product output lacks {field}")
        result[field] = {str(k): int(v) for k, v in result[field].items()}
    return FreeColProductionResult(
        upstream="FreeCol",
        upstream_commit=FREECOL_COMMIT,
        actual=result["actual"],
        maximum=result["maximum"],
        deficits=result["deficits"],
        canonical_time_advanced=False,
    )
