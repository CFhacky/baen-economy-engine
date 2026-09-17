"""Acquire/start the pinned upstream product stack for one Empire preview.

This is orchestration, not campaign authority. It prepares exact upstream
revisions using the repository's existing product-preparation tools, starts the
two service products, exposes their locations through environment variables, and
cleans them up after the Baen preview. Repeated runs reuse already-built product
artifacts when their exact patch markers/binaries are present.
"""
from __future__ import annotations

from contextlib import contextmanager
import importlib
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
from typing import Iterator

from . import mesa_runtime
from .openttd_product import OPENTTD_COMMIT
from .veloren_product import VELOREN_COMMIT, VELOREN_PATCH_VERSION
from .freecol_product import FREECOL_COMMIT
from .unknown_horizons_product import UNKNOWN_HORIZONS_COMMIT
from .brunnfeld_sidecar import BRUNNFELD_COMMIT


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MESA_REQUIREMENT = (
    "Mesa @ git+https://github.com/mesa/mesa.git@"
    "20841b12559ef920dd4c8263a09fe75ceac7250c"
)


class ProductStackError(RuntimeError):
    pass


def _run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    try:
        subprocess.run(command, cwd=cwd, env=env, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ProductStackError("product preparation failed: " + " ".join(command)) from exc


def _head(checkout: Path) -> str | None:
    if not (checkout / ".git").is_dir():
        return None
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=checkout, text=True
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _marker_matches(path: Path, expected: dict[str, object]) -> bool:
    try:
        return json.loads(path.read_text(encoding="utf-8")) == expected
    except (OSError, json.JSONDecodeError):
        return False


def _python_tool(name: str, *args: str) -> None:
    _run([sys.executable, str(PROJECT_ROOT / "tools" / name), *args], cwd=PROJECT_ROOT)


def _ensure_mesa() -> None:
    if mesa_runtime.mesa_available():
        return
    if sys.version_info < (3, 12):
        raise ProductStackError(
            "the pinned Mesa product requires Python 3.12+; run baen-empire "
            "with Python 3.12 for the all-products path"
        )
    _run([sys.executable, "-m", "pip", "install", MESA_REQUIREMENT])
    importlib.reload(mesa_runtime)
    if not mesa_runtime.mesa_available():
        raise ProductStackError("pinned Mesa installed but its runtime is still unavailable")


def _ensure_brunnfeld(root: Path) -> Path:
    checkout = root / "brunnfeld"
    built = checkout / "dist/server.js"
    if _head(checkout) == BRUNNFELD_COMMIT and built.is_file():
        return checkout
    _python_tool(
        "run_brunnfeld_sidecar.py",
        "--checkout", str(checkout),
        "--build-only",
    )
    if _head(checkout) != BRUNNFELD_COMMIT:
        raise ProductStackError("Brunnfeld checkout is not at the pinned commit")
    return checkout


def _ensure_unknown_horizons(root: Path) -> Path:
    checkout = root / "unknown-horizons"
    if _head(checkout) == UNKNOWN_HORIZONS_COMMIT:
        return checkout
    _python_tool("prepare_unknown_horizons_product.py", "--checkout", str(checkout))
    return checkout


def _ensure_freecol(root: Path) -> Path:
    checkout = root / "freecol"
    if _head(checkout) == FREECOL_COMMIT and (checkout / "FreeCol.jar").is_file():
        return checkout
    _python_tool("prepare_freecol_product.py", "--checkout", str(checkout))
    return checkout


def _ensure_veloren(root: Path) -> Path:
    checkout = root / "veloren"
    marker = checkout / ".baen-economy-product-patch.json"
    binary = checkout / "target/debug/examples/baen_economy_bridge"
    expected = {"patch_version": VELOREN_PATCH_VERSION, "upstream_commit": VELOREN_COMMIT}
    if _head(checkout) == VELOREN_COMMIT and binary.is_file() and _marker_matches(marker, expected):
        return checkout
    _python_tool(
        "prepare_veloren_product.py",
        "--checkout", str(checkout),
        "--toolchain", "nightly",
    )
    return checkout


def _ensure_openttd(root: Path, *, jobs: int) -> Path:
    checkout = root / "openttd"
    marker = checkout / ".baen-economy-product-patch.json"
    binary = checkout / "build-baen-dedicated/openttd"
    if os.name == "nt":
        binary = binary.with_suffix(".exe")
    expected = {"patch_version": 1, "upstream_commit": OPENTTD_COMMIT}
    if _head(checkout) == OPENTTD_COMMIT and binary.is_file() and _marker_matches(marker, expected):
        return checkout
    _python_tool(
        "prepare_openttd_product.py",
        "--checkout", str(checkout),
        "--jobs", str(jobs),
    )
    return checkout


def _discover_openttd_baseset(explicit: Path | None) -> Path:
    candidates = []
    if explicit is not None:
        candidates.append(explicit)
    env = os.environ.get("OPENTTD_BASESET_DIR")
    if env:
        candidates.append(Path(env))
    candidates.extend([
        Path("/usr/share/games/openttd/baseset"),
        Path("/usr/local/share/games/openttd/baseset"),
    ])
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved.is_dir():
            return resolved
    raise ProductStackError(
        "OpenTTD base-set directory is required. Install OpenGFX/OpenSFX/OpenMSX "
        "or pass --openttd-baseset PATH."
    )


def _wait_port(port: int, name: str, processes: tuple[subprocess.Popen, ...], timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for process in processes:
            if process.poll() is not None:
                raise ProductStackError(
                    f"{name} dependency exited before its service port opened "
                    f"(code {process.returncode})"
                )
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.25)
    raise ProductStackError(f"{name} service port did not open")


def _terminate(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        process.wait(timeout=5)


def prepare_products(
    root: Path,
    *,
    openttd_baseset: Path | None = None,
    build_jobs: int = 2,
) -> dict[str, Path]:
    if build_jobs < 1:
        raise ProductStackError("build_jobs must be positive")
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    _ensure_mesa()
    return {
        "brunnfeld": _ensure_brunnfeld(root),
        "unknown_horizons": _ensure_unknown_horizons(root),
        "freecol": _ensure_freecol(root),
        "veloren": _ensure_veloren(root),
        "openttd": _ensure_openttd(root, jobs=build_jobs),
        "openttd_baseset": _discover_openttd_baseset(openttd_baseset),
    }


@contextmanager
def product_environment(
    root: Path,
    *,
    openttd_baseset: Path | None = None,
    build_jobs: int = 2,
) -> Iterator[dict[str, Path]]:
    paths = prepare_products(
        root, openttd_baseset=openttd_baseset, build_jobs=build_jobs
    )
    temp = tempfile.TemporaryDirectory(prefix="baen-product-stack-")
    children: list[subprocess.Popen] = []
    old_env = {
        key: os.environ.get(key)
        for key in (
            "UNKNOWN_HORIZONS_CHECKOUT",
            "FREECOL_CHECKOUT",
            "VELOREN_CHECKOUT",
            "BRUNNFELD_URL",
            "OPENTTD_ADMIN_HOST",
            "OPENTTD_ADMIN_PORT",
            "OPENTTD_ADMIN_PASSWORD",
        )
    }
    logs = Path(temp.name)
    try:
        npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
        if npm is None:
            raise ProductStackError("npm is required for the Brunnfeld product")
        br_log = (logs / "brunnfeld.log").open("w", encoding="utf-8")
        br_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        br = subprocess.Popen(
            [npm, "run", "server"],
            cwd=paths["brunnfeld"],
            env=dict(os.environ, PORT="3333"),
            stdout=br_log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=os.name != "nt",
            creationflags=br_flags,
        )
        children.append(br)

        run_dir = logs / "openttd"
        run_dir.mkdir()
        local_baseset = run_dir / "baseset"
        try:
            local_baseset.symlink_to(paths["openttd_baseset"], target_is_directory=True)
        except OSError:
            shutil.copytree(paths["openttd_baseset"], local_baseset)
        version = "[version]\nini_version = 8\n\n"
        (run_dir / "openttd.cfg").write_text(
            version
            + "[network]\nserver_port = 3979\nserver_admin_port = 3977\n"
            + "allow_insecure_admin_login = true\nserver_game_type = local\n"
            + "server_name = Baen Empire Product Stack\n",
            encoding="utf-8",
        )
        admin_secret = "baen-empire-preview"
        (run_dir / "secrets.cfg").write_text(
            version + "[network]\n" + f"admin_password = {admin_secret}\n",
            encoding="utf-8",
        )
        ottd = paths["openttd"] / "build-baen-dedicated/openttd"
        if os.name == "nt":
            ottd = ottd.with_suffix(".exe")
        ot_log = (logs / "openttd.log").open("w", encoding="utf-8")
        ot_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        ot = subprocess.Popen(
            [
                str(ottd), "-D", "127.0.0.1:3979",
                "-c", str(run_dir / "openttd.cfg"),
                "-g", "-G", "424242", "-x", "-d", "net=1",
            ],
            cwd=run_dir,
            stdin=subprocess.DEVNULL,
            stdout=ot_log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=os.name != "nt",
            creationflags=ot_flags,
        )
        children.append(ot)

        _wait_port(3333, "Brunnfeld", tuple(children))
        _wait_port(3977, "OpenTTD admin", tuple(children))

        os.environ["UNKNOWN_HORIZONS_CHECKOUT"] = str(paths["unknown_horizons"])
        os.environ["FREECOL_CHECKOUT"] = str(paths["freecol"])
        os.environ["VELOREN_CHECKOUT"] = str(paths["veloren"])
        os.environ["BRUNNFELD_URL"] = "http://127.0.0.1:3333"
        os.environ["OPENTTD_ADMIN_HOST"] = "127.0.0.1"
        os.environ["OPENTTD_ADMIN_PORT"] = "3977"
        os.environ["OPENTTD_ADMIN_PASSWORD"] = admin_secret
        yield paths
    finally:
        for process in reversed(children):
            _terminate(process)
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        try:
            br_log.close()
        except UnboundLocalError:
            pass
        try:
            ot_log.close()
        except UnboundLocalError:
            pass
        temp.cleanup()
