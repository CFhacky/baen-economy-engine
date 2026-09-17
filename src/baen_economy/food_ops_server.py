"""Loopback-only HTTP server for the Baen food operations workbench.

The server is deliberately dependency-free and deliberately narrow.  It serves
one local operator application and exposes preview/local-scenario endpoints.  It
has no Notion writer, no campaign-ledger adapter, and no endpoint that advances
campaign state.

Default integration contracts are isolated in :func:`default_bindings` so the
HTTP and security code does not depend on engine implementation details:

* ``food_sector.load_food_sector_baseline() -> Mapping``
* ``food_sector.preview_food_sector_month(*, month_label, seed=None,
  supplied_faces=None, sector_assumptions=None) -> Mapping``
* ``food_security.LongsaddleAssumptions(**values)`` and
  ``food_security.plan_longsaddle_food_security(assumptions) -> result`` where
  ``result.to_dict() -> Mapping``
* ``food_ops_store.FoodOpsStore.create/open(path)`` returning a context manager
  with ``save_scenario``, ``list_scenarios``, ``get_scenario``, ``verify``,
  ``export_markdown``, and ``export_html`` methods.

Tests and alternate front ends can inject :class:`FoodOpsBindings` without
importing any of those modules.  This keeps interface changes confined to one
adapter function rather than leaking them through request handlers.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, fields, is_dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
import sys
import threading
from types import TracebackType
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit
import webbrowser


LOOPBACK_HOST = "127.0.0.1"
DEFAULT_MAX_BODY_BYTES = 256 * 1024
DEFAULT_REQUEST_TIMEOUT_SECONDS = 10.0
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTEXT_PATH = (
    PROJECT_ROOT / "fixtures" / "agriculture" / "food-ops-context-v1.json"
)


def _platform_store_path() -> Path:
    """Choose durable per-user state without placing a database in the repo."""

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "Baen Economy" / "Food Operations.sqlite3"
    xdg_state = os.environ.get("XDG_STATE_HOME")
    root = Path(xdg_state) if xdg_state else Path.home() / ".local" / "state"
    return root / "baen-economy" / "food-operations.sqlite3"


DEFAULT_STORE_PATH = _platform_store_path()

FOOD_SECTOR_KIND = "food_sector_month"
LONGSADDLE_KIND = "longsaddle_plan"
AQUACULTURE_KIND = "aquaculture_plan"
CROP_KIND = "crop_plan"
SCENARIO_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SAFE_EXPORT_NAME = re.compile(r"[^A-Za-z0-9._-]+")
CONTENT_LENGTH = re.compile(r"^[0-9]+$")


class FoodOpsServerError(RuntimeError):
    """Raised for startup or adapter failures that cannot be served safely."""


class ServiceError(RuntimeError):
    """A deliberately public, status-bearing service error."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.public_message = message


@dataclass(frozen=True, slots=True)
class FoodOpsBindings:
    """Pure/local operations used by the request handler.

    Store callbacks must open their own connection (or otherwise be safe for
    concurrent handler threads).  Nothing in this interface authorizes an
    external write.
    """

    bootstrap: Callable[[], Mapping[str, object]]
    preview_food_sector: Callable[[Mapping[str, object]], Mapping[str, object]]
    preview_longsaddle: Callable[[Mapping[str, object]], Mapping[str, object]]
    save_scenario: Callable[
        [str, str, Mapping[str, object], Mapping[str, object]],
        tuple[Mapping[str, object], bool],
    ]
    list_scenarios: Callable[[str | None], Sequence[Mapping[str, object]]]
    load_scenario: Callable[[str], Mapping[str, object]]
    export_markdown: Callable[[str], str]
    export_html: Callable[[str], str]
    verify_store: Callable[[], Mapping[str, object]]
    production_catalog: Callable[[], Mapping[str, object]] | None = None
    preview_aquaculture: Callable[[Mapping[str, object]], Mapping[str, object]] | None = None
    preview_crop: Callable[[Mapping[str, object]], Mapping[str, object]] | None = None


def _required_text(value: object, label: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text")
    result = value.strip()
    if len(result) > maximum or any(ord(character) < 32 for character in result):
        raise ValueError(f"{label} is invalid")
    return result


def _optional_text(value: object, label: str, *, maximum: int = 512) -> str | None:
    if value is None:
        return None
    return _required_text(value, label, maximum=maximum)


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{label} must be a JSON object with text keys")
    return value


def _scenario_id(value: object) -> str:
    result = _required_text(value, "scenario_id", maximum=128)
    if SCENARIO_ID.fullmatch(result) is None:
        raise ValueError(
            "scenario_id may contain only letters, numbers, dot, underscore, colon, and hyphen"
        )
    return result


def _content_length(value: str) -> int:
    if CONTENT_LENGTH.fullmatch(value) is None:
        raise ValueError("Content-Length is not an RFC decimal integer")
    try:
        return int(value, 10)
    except ValueError as exc:
        raise ValueError("Content-Length is too large") from exc


def _normal_kind(value: object) -> str:
    raw = _required_text(value, "kind", maximum=64).lower().replace("-", "_")
    aliases = {
        "food_sector": FOOD_SECTOR_KIND,
        "food_sector_month": FOOD_SECTOR_KIND,
        "food_month": FOOD_SECTOR_KIND,
        "longsaddle": LONGSADDLE_KIND,
        "longsaddle_plan": LONGSADDLE_KIND,
        "longsaddle_food_security": LONGSADDLE_KIND,
        "aquaculture": AQUACULTURE_KIND,
        "aquaculture_plan": AQUACULTURE_KIND,
        "aquaculture_production": AQUACULTURE_KIND,
        "crop": CROP_KIND,
        "crop_plan": CROP_KIND,
        "crop_production": CROP_KIND,
    }
    try:
        return aliases[raw]
    except KeyError as exc:
        raise ValueError(
            "kind must be food_sector_month, longsaddle_plan, aquaculture_plan, or crop_plan"
        ) from exc


def _exact_decimal(value: object, label: str) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError(f"{label} must use exact decimal text or an integer")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label} must be an exact decimal") from exc
    if not result.is_finite():
        raise ValueError(f"{label} must be finite")
    return result


def _nonnegative_integer(value: object, label: str) -> int | None:
    amount = _exact_decimal(value, label)
    if amount is None:
        return None
    result = int(amount)
    if Decimal(result) != amount or result < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return result


def _food_sector_adapter(request: Mapping[str, object]) -> Mapping[str, object]:
    """Adapt JSON to the food-sector engine without exposing fixture paths."""

    from .food_sector import preview_food_sector_month

    assumptions = request.get("sector_assumptions", request.get("assumptions"))
    if assumptions is not None:
        assumptions = _mapping(assumptions, "sector_assumptions")
    supplied_faces = request.get("supplied_faces")
    if supplied_faces is not None:
        supplied_faces = _mapping(supplied_faces, "supplied_faces")
    result = preview_food_sector_month(
        month_label=_required_text(request.get("month_label"), "month_label"),
        seed=_optional_text(request.get("seed"), "seed"),
        supplied_faces=supplied_faces,
        sector_assumptions=assumptions,
    )
    return _mapping(result, "food-sector preview result")


def _longsaddle_adapter(request: Mapping[str, object]) -> Mapping[str, object]:
    """Adapt JSON to the typed Longsaddle planner.

    Empty UI fields become ``None``.  Decimal fields remain exact and the two
    count fields remain integers.  A named illustrative profile is supported
    only when explicitly requested and remains labelled non-canonical by the
    planner.
    """

    from .food_security import (
        LongsaddleAssumptions,
        illustrative_low_v1,
        plan_longsaddle_food_security,
    )

    profile = request.get("profile")
    if profile is not None:
        normalized = _required_text(profile, "profile").lower().replace("_", "-")
        if normalized != "illustrative-low-v1":
            raise ValueError("unknown Longsaddle profile")
        if any(key not in {"profile", "schema"} for key in request):
            raise ValueError("an illustrative profile cannot be mixed with assumptions")
        result = illustrative_low_v1()
        payload = result.to_dict() if hasattr(result, "to_dict") else result
        return _mapping(payload, "Longsaddle preview result")

    raw_source = request.get("assumptions", request)
    raw_source = _mapping(raw_source, "Longsaddle assumptions")
    aliases = {
        "target_tons": "selected_target_tons",
        "opening_stock_tons": "opening_longsaddle_stock_tons",
        "dispatch_tons": "dispatch_requested_tons",
        "trips": "route_trips",
    }
    metadata = {"schema", "scenario_id", "scenario_name"}
    raw: dict[str, object] = {}
    for key, value in raw_source.items():
        if key in metadata:
            continue
        normalized_key = aliases.get(key, key)
        if normalized_key in raw:
            raise ValueError(f"Longsaddle assumption is supplied twice: {normalized_key}")
        raw[normalized_key] = value
    if "transport_loss_percent" in raw:
        if "loss_rate" in raw:
            raise ValueError("supply either transport_loss_percent or loss_rate, not both")
        percent = _exact_decimal(raw.pop("transport_loss_percent"), "transport_loss_percent")
        raw["loss_rate"] = None if percent is None else percent / Decimal("100")
    if not is_dataclass(LongsaddleAssumptions):
        raise FoodOpsServerError("LongsaddleAssumptions must be a dataclass")
    field_names = {item.name for item in fields(LongsaddleAssumptions)}
    unknown = sorted(set(raw) - field_names)
    if unknown:
        raise ValueError("unknown Longsaddle assumption fields: " + ", ".join(unknown))

    integer_fields = {"route_trips", "travel_periods"}
    text_fields = {"assumption_source"}
    values: dict[str, object] = {}
    for item in fields(LongsaddleAssumptions):
        value = raw.get(item.name)
        if item.name in integer_fields:
            values[item.name] = _nonnegative_integer(value, item.name)
        elif item.name in text_fields:
            values[item.name] = (
                "local operator assumption"
                if value in (None, "")
                else _required_text(value, item.name)
            )
        else:
            values[item.name] = _exact_decimal(value, item.name)
    assumptions = LongsaddleAssumptions(**values)
    result = plan_longsaddle_food_security(assumptions)
    payload = result.to_dict() if hasattr(result, "to_dict") else result
    return _mapping(payload, "Longsaddle preview result")


def _open_store_context(store_class: type, store_path: Path) -> AbstractContextManager[Any]:
    return store_class.open(store_path)


def default_bindings(store_path: Path = DEFAULT_STORE_PATH) -> FoodOpsBindings:
    """Load the default engines and prepare a local append-only scenario store.

    Imports occur here, never at module import, so missing or revised engine
    modules cannot prevent tests from injecting a compatible service boundary.
    The store is opened per operation because :class:`ThreadingHTTPServer` may
    dispatch simultaneous requests.
    """

    from .agriculture_cli import load_agriculture_canon
    from .food_ops_store import FoodOpsStore, FoodOpsStoreError
    from .food_production import (
        food_production_catalog,
        preview_aquaculture_plan,
        preview_crop_plan,
    )
    from .food_sector import load_food_sector_baseline

    target = Path(store_path).expanduser().resolve()
    if target.suffix.lower() == ".bean" or "campaign-finance-ledger" in target.parts:
        raise FoodOpsServerError("food operations state cannot use the campaign ledger")
    if target.exists():
        try:
            with FoodOpsStore.open(target) as store:
                store.verify()
        except FoodOpsStoreError as exc:
            raise FoodOpsServerError(f"cannot open food operations store: {exc}") from exc
    else:
        try:
            with FoodOpsStore.create(target) as store:
                store.verify()
        except FoodOpsStoreError as exc:
            raise FoodOpsServerError(f"cannot create food operations store: {exc}") from exc

    def with_store(callback: Callable[[Any], Any]) -> Any:
        try:
            with _open_store_context(FoodOpsStore, target) as store:
                return callback(store)
        except FoodOpsStoreError:
            raise

    def bootstrap() -> Mapping[str, object]:
        baseline = dict(load_food_sector_baseline())
        entities = baseline.get("entities")
        if isinstance(entities, list):
            baseline["entities"] = [
                {
                    **dict(item),
                    "employees": item.get("employees", item.get("staff")),
                }
                if isinstance(item, Mapping)
                else item
                for item in entities
            ]
        agriculture = dict(load_agriculture_canon())
        try:
            context_raw = json.loads(DEFAULT_CONTEXT_PATH.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise FoodOpsServerError(f"cannot load food operations context: {exc}") from exc
        context = _mapping(context_raw, "food operations context")
        if (
            context.get("schema") != "tnp.economy.food-ops-context/1"
            or context.get("notion_access") != "read_only"
        ):
            raise FoodOpsServerError("food operations context is not the reviewed read-only fixture")
        unresolved = agriculture.get("unresolved_inputs", [])
        if not isinstance(unresolved, list):
            raise FoodOpsServerError("agriculture unresolved-input docket is malformed")
        rulings = [
            {
                "title": f"Open input {index}",
                "resolution_type": "Source or GM ruling",
                "description": item,
                "unlocks": "Only calculations that depend on this input",
            }
            for index, item in enumerate(unresolved, start=1)
            if isinstance(item, str)
        ]
        crop_program = agriculture.get("crop_program", {})
        crops = (
            crop_program.get("crops", [])
            if isinstance(crop_program, Mapping)
            else []
        )
        return {
            "schema": "tnp.food-ops.bootstrap/1",
            "baseline": baseline,
            "food_sector_baseline": baseline,
            "food_sector": baseline,
            "agriculture": agriculture,
            "campaign_date": (
                agriculture.get("current_actual_state", {}).get("campaign_date")
                if isinstance(agriculture.get("current_actual_state"), Mapping)
                else None
            ),
            "current_actual_state": agriculture.get("current_actual_state"),
            "operational_context": {
                "schema": context.get("schema"),
                "warnings": context.get("warnings", []),
                "known_operational_issues": context.get(
                    "known_operational_issues", []
                ),
                "gm_only_clocks": context.get("gm_only_clocks", []),
            },
            "known_operational_issues": context.get(
                "known_operational_issues", []
            ),
            "gm_only_clocks": context.get("gm_only_clocks", []),
            "rulings": rulings,
            "unresolved_inputs": unresolved,
            "sources": agriculture.get("sources", []),
            "species": agriculture.get("species", []),
            "crops": crops,
            "crop_program": agriculture.get("crop_program", {}),
            "safety": {
                "mode": "preview",
                "notion_write_capability": False,
                "canonical_ledger_post_capability": False,
                "campaign_time_advance_capability": False,
            },
        }

    def save(
        scenario_id: str,
        kind: str,
        request: Mapping[str, object],
        result: Mapping[str, object],
    ) -> tuple[Mapping[str, object], bool]:
        try:
            record, replayed = with_store(
                lambda store: store.save_scenario(
                    scenario_id, kind, request, result
                )
            )
            return _mapping(record, "stored scenario"), bool(replayed)
        except FoodOpsStoreError as exc:
            raise ServiceError(409, "scenario_conflict", str(exc)) from exc

    def listing(kind: str | None) -> Sequence[Mapping[str, object]]:
        try:
            rows = with_store(lambda store: store.list_scenarios(kind=kind))
            if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
                raise FoodOpsServerError("scenario store returned an invalid listing")
            return rows
        except FoodOpsStoreError as exc:
            raise ServiceError(500, "store_error", str(exc)) from exc

    def load(scenario_id: str) -> Mapping[str, object]:
        try:
            return _mapping(
                with_store(lambda store: store.get_scenario(scenario_id)),
                "stored scenario",
            )
        except FoodOpsStoreError as exc:
            message = str(exc)
            missing = any(
                token in message.lower()
                for token in ("not found", "unknown", "missing")
            )
            status = 404 if missing else 500
            code = "scenario_not_found" if status == 404 else "store_error"
            raise ServiceError(status, code, message) from exc

    def export(scenario_id: str, method_name: str) -> str:
        try:
            value = with_store(
                lambda store: getattr(store, method_name)(scenario_id)
            )
            if not isinstance(value, str):
                raise FoodOpsServerError("scenario export must be text")
            return value
        except FoodOpsStoreError as exc:
            message = str(exc)
            missing = any(
                token in message.lower()
                for token in ("not found", "unknown", "missing")
            )
            status = 404 if missing else 500
            code = "scenario_not_found" if status == 404 else "store_error"
            raise ServiceError(status, code, message) from exc

    def verify() -> Mapping[str, object]:
        try:
            return _mapping(with_store(lambda store: store.verify()), "store verification")
        except FoodOpsStoreError as exc:
            raise ServiceError(500, "store_error", str(exc)) from exc

    return FoodOpsBindings(
        bootstrap=bootstrap,
        preview_food_sector=_food_sector_adapter,
        preview_longsaddle=_longsaddle_adapter,
        save_scenario=save,
        list_scenarios=listing,
        load_scenario=load,
        export_markdown=lambda scenario_id: export(scenario_id, "export_markdown"),
        export_html=lambda scenario_id: export(scenario_id, "export_html"),
        verify_store=verify,
        production_catalog=food_production_catalog,
        preview_aquaculture=lambda request: _mapping(
            preview_aquaculture_plan(request), "aquaculture production preview"
        ),
        preview_crop=lambda request: _mapping(
            preview_crop_plan(request), "crop production preview"
        ),
    )


def _duplicate_safe_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> object:
    raise ValueError(f"invalid JSON number: {value}")


def _json_safe(value: object, *, label: str = "response") -> object:
    """Return a JSON-safe value while preserving exact Decimal values as text."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise TypeError(f"{label} contains a non-finite decimal")
        return format(value, "f")
    if isinstance(value, float):
        raise TypeError(f"{label} contains binary floating-point data")
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{label} contains a non-text object key")
            result[key] = _json_safe(item, label=f"{label}/{key}")
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [
            _json_safe(item, label=f"{label}/{index}")
            for index, item in enumerate(value)
        ]
    raise TypeError(f"{label} contains unsupported data: {type(value).__name__}")


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            _json_safe(value),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _request_for_persistence(request: Mapping[str, object]) -> dict[str, object]:
    """Remove a raw deterministic seed while retaining its replay identity."""

    stored = dict(request)
    seed = stored.pop("seed", None)
    if seed is not None:
        clean_seed = _required_text(seed, "seed")
        stored["seed_fingerprint"] = hashlib.sha256(
            clean_seed.encode("utf-8")
        ).hexdigest()
        stored["raw_seed_persisted"] = False
    return stored


def _safe_static_file(root: Path, request_path: str) -> Path | None:
    decoded = unquote(request_path)
    if "\x00" in decoded or "\\" in decoded:
        return None
    relative = decoded.lstrip("/") or "index.html"
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    return candidate


def _load_default_app() -> str:
    from .food_ops_app import render_food_ops_app

    rendered = render_food_ops_app()
    if not isinstance(rendered, str) or not rendered.strip():
        raise FoodOpsServerError("render_food_ops_app() returned no HTML")
    return rendered


class FoodOpsHTTPServer(ThreadingHTTPServer):
    """Threaded server carrying immutable request-handler configuration."""

    daemon_threads = True
    allow_reuse_address = True
    block_on_close = False

    def __init__(
        self,
        server_address: tuple[str, int],
        bindings: FoodOpsBindings,
        *,
        app_html: str | None,
        static_root: Path | None,
        max_body_bytes: int,
        request_timeout_seconds: float,
    ) -> None:
        self.bindings = bindings
        self.app_html = app_html
        self.static_root = static_root
        self.max_body_bytes = max_body_bytes
        self.request_timeout_seconds = request_timeout_seconds
        self._active_condition = threading.Condition()
        self._active_requests: set[socket.socket] = set()
        self.handler_shutdown_timeout_seconds = 5.0
        super().__init__(server_address, FoodOpsRequestHandler, bind_and_activate=True)

    @property
    def port(self) -> int:
        return int(self.server_address[1])

    @property
    def base_url(self) -> str:
        return f"http://{LOOPBACK_HOST}:{self.port}"

    @property
    def active_request_count(self) -> int:
        with self._active_condition:
            return len(self._active_requests)

    def get_request(self) -> tuple[socket.socket, object]:
        request, address = super().get_request()
        # A stalled local client must not hold a handler forever.  Normal UI
        # bodies are tiny and complete immediately.
        request.settimeout(self.request_timeout_seconds)
        with self._active_condition:
            self._active_requests.add(request)
        return request, address

    def shutdown_request(self, request: socket.socket) -> None:
        try:
            super().shutdown_request(request)
        finally:
            with self._active_condition:
                self._active_requests.discard(request)
                self._active_condition.notify_all()

    def close_active_requests(self) -> None:
        """Interrupt blocked handlers before a bounded callback drain."""

        with self._active_condition:
            requests = tuple(self._active_requests)
        for request in requests:
            try:
                request.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                request.close()
            except OSError:
                pass

    def wait_for_active_requests(self, timeout: float) -> bool:
        """Wait a bounded time for accepted handlers to leave their callbacks."""

        with self._active_condition:
            return self._active_condition.wait_for(
                lambda: not self._active_requests,
                timeout=timeout,
            )

    def handle_error(self, request: object, client_address: object) -> None:
        # A peer disconnect or shutdown-triggered socket close is expected.  API
        # exceptions are converted to JSON by the handler before reaching here.
        return None


class FoodOpsRequestHandler(BaseHTTPRequestHandler):
    """Small same-origin JSON API and static application handler."""

    protocol_version = "HTTP/1.1"
    server_version = "BaenFoodOps"
    sys_version = ""

    @property
    def food_server(self) -> FoodOpsHTTPServer:
        return self.server  # type: ignore[return-value]

    def version_string(self) -> str:
        return self.server_version

    def log_message(self, format: str, *args: object) -> None:
        # The embedding CLI reports its URL.  Routine requests should not bury
        # that useful line in BaseHTTPRequestHandler's stderr chatter.
        return None

    def handle_expect_100(self) -> bool:
        self.close_connection = True
        self._error(417, "expectation_failed", "Expect requests are not supported")
        return False

    def _security_headers(self, *, api: bool) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store" if api else "no-cache")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; "
            "form-action 'self'; connect-src 'self'; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'",
        )

    def _send_bytes(
        self,
        status: int,
        body: bytes,
        content_type: str,
        *,
        api: bool,
        disposition: str | None = None,
    ) -> None:
        self.send_response(status)
        self._security_headers(api=api)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if self.close_connection:
            self.send_header("Connection", "close")
        if disposition is not None:
            self.send_header("Content-Disposition", disposition)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, data: object, *, disposition: str | None = None) -> None:
        self._send_bytes(
            status,
            _json_bytes({"ok": True, "data": data}),
            "application/json; charset=utf-8",
            api=True,
            disposition=disposition,
        )

    def _error(self, status: int, code: str, message: str) -> None:
        self._send_bytes(
            status,
            _json_bytes(
                {
                    "ok": False,
                    "error": {"code": code, "message": message},
                }
            ),
            "application/json; charset=utf-8",
            api=True,
        )

    def _authority_is_local(self, value: str) -> bool:
        try:
            parsed = urlsplit("//" + value)
            port = parsed.port
        except ValueError:
            return False
        if parsed.username is not None or parsed.password is not None:
            return False
        if parsed.path or parsed.query or parsed.fragment:
            return False
        if parsed.hostname not in {LOOPBACK_HOST, "localhost"}:
            return False
        return port in {None, self.food_server.port}

    def _request_is_local(self) -> bool:
        hosts = self.headers.get_all("Host", failobj=[])
        if len(hosts) != 1 or not self._authority_is_local(hosts[0]):
            self.close_connection = True
            self._error(403, "invalid_host", "Host must be this localhost server")
            return False
        origins = self.headers.get_all("Origin", failobj=[])
        if len(origins) > 1:
            self.close_connection = True
            self._error(403, "cross_origin_denied", "Multiple Origin headers are denied")
            return False
        if origins:
            origin = origins[0]
            try:
                parsed = urlsplit(origin)
                origin_port = parsed.port
            except ValueError:
                parsed = None
                origin_port = None
            if (
                parsed is None
                or parsed.scheme != "http"
                or parsed.hostname not in {LOOPBACK_HOST, "localhost"}
                or origin_port != self.food_server.port
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or bool(parsed.query)
                or bool(parsed.fragment)
            ):
                self.close_connection = True
                self._error(403, "cross_origin_denied", "Cross-origin requests are denied")
                return False
        return True

    def _read_json_object(self) -> Mapping[str, object]:
        transfer = self.headers.get("Transfer-Encoding")
        if transfer is not None:
            self.close_connection = True
            raise ServiceError(400, "unsupported_transfer_encoding", "Transfer-Encoding is not supported")
        lengths = self.headers.get_all("Content-Length", failobj=[])
        if len(lengths) != 1:
            self.close_connection = True
            raise ServiceError(411, "length_required", "Exactly one Content-Length header is required")
        try:
            length = _content_length(lengths[0])
        except ValueError as exc:
            self.close_connection = True
            raise ServiceError(400, "invalid_content_length", "Content-Length is invalid") from exc
        if length > self.food_server.max_body_bytes:
            self.close_connection = True
            raise ServiceError(
                413,
                "body_too_large",
                f"JSON body exceeds {self.food_server.max_body_bytes} bytes",
            )
        media_type, *parameters = self.headers.get("Content-Type", "").split(";")
        if media_type.strip().lower() != "application/json":
            self.close_connection = True
            raise ServiceError(415, "unsupported_media_type", "Content-Type must be application/json")
        for parameter in parameters:
            name, separator, value = parameter.partition("=")
            if separator and name.strip().lower() == "charset" and value.strip().strip('"').lower() not in {"utf-8", "utf8"}:
                self.close_connection = True
                raise ServiceError(415, "unsupported_charset", "JSON must be UTF-8")
        try:
            raw = self.rfile.read(length)
        except socket.timeout as exc:
            self.close_connection = True
            raise ServiceError(
                408, "request_timeout", "Timed out while reading the JSON body"
            ) from exc
        except OSError as exc:
            self.close_connection = True
            raise ServiceError(
                400, "incomplete_body", "Request body could not be read"
            ) from exc
        if len(raw) != length:
            self.close_connection = True
            raise ServiceError(400, "incomplete_body", "Request body ended early")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ServiceError(400, "invalid_utf8", "JSON body is not valid UTF-8") from exc
        try:
            value = json.loads(
                text,
                object_pairs_hook=_duplicate_safe_object,
                parse_float=Decimal,
                parse_constant=_reject_constant,
            )
        except (json.JSONDecodeError, ValueError) as exc:
            raise ServiceError(400, "malformed_json", f"Malformed JSON: {exc}") from exc
        if not isinstance(value, Mapping):
            raise ServiceError(400, "json_object_required", "JSON body must be an object")
        return value

    def _reject_get_body(self) -> bool:
        if self.headers.get("Transfer-Encoding") is not None:
            self._error(400, "unexpected_body", "GET and HEAD requests cannot use a body")
            self.close_connection = True
            return False
        lengths = self.headers.get_all("Content-Length", failobj=[])
        if not lengths:
            return True
        if len(lengths) != 1:
            self._error(400, "invalid_content_length", "Content-Length is invalid")
            self.close_connection = True
            return False
        try:
            length = _content_length(lengths[0])
        except ValueError:
            length = -1
        if length != 0:
            self._error(400, "unexpected_body", "GET and HEAD requests cannot use a body")
            self.close_connection = True
            return False
        return True

    def _execute(self, callback: Callable[[], None]) -> None:
        try:
            callback()
        except ServiceError as exc:
            self._error(exc.status, exc.code, exc.public_message)
        except (ValueError, TypeError, KeyError) as exc:
            self._error(422, "invalid_request", str(exc))
        except Exception:
            self._error(500, "internal_error", "The local operator could not complete the request")

    def do_OPTIONS(self) -> None:
        if not self._request_is_local():
            return
        self.close_connection = True
        self._error(405, "method_not_allowed", "Cross-origin preflight is not supported")

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        if not self._request_is_local():
            return
        if not self._reject_get_body():
            return
        parsed = urlsplit(self.path)
        path = parsed.path.rstrip("/") or "/"

        if path in {"/health", "/api/health"}:
            self._json(
                200,
                {
                    "status": "ok",
                    "bind": LOOPBACK_HOST,
                    "port": self.food_server.port,
                    "mode": "preview",
                    "notion_write_capability": False,
                    "canonical_ledger_post_capability": False,
                    "campaign_time_advance_capability": False,
                },
            )
            return
        if path == "/api/bootstrap":
            self._execute(self._get_bootstrap)
            return
        if path == "/api/scenarios":
            self._execute(lambda: self._list_scenarios(parsed.query))
            return
        if path.startswith("/api/scenarios/"):
            self._execute(lambda: self._get_scenario_path(path, parsed.query))
            return
        if path.startswith("/api/"):
            self._error(404, "not_found", "API endpoint not found")
            return
        self._serve_static(parsed.path)

    def do_POST(self) -> None:
        if not self._request_is_local():
            return
        path = urlsplit(self.path).path.rstrip("/") or "/"
        routes: dict[str, Callable[[Mapping[str, object]], None]] = {
            "/api/food-sector/preview": self._preview_food_sector,
            "/api/longsaddle/preview": self._preview_longsaddle,
            "/api/production/aquaculture/preview": self._preview_aquaculture,
            "/api/production/crop/preview": self._preview_crop,
            "/api/scenarios": self._save_scenario,
            "/api/scenarios/save": self._save_scenario,
        }
        route = routes.get(path)
        if route is None:
            self.close_connection = True
            self._error(404, "not_found", "API endpoint not found")
            return

        def execute() -> None:
            route(self._read_json_object())

        self._execute(execute)

    def do_PUT(self) -> None:
        self._method_not_allowed()

    def do_PATCH(self) -> None:
        self._method_not_allowed()

    def do_DELETE(self) -> None:
        self._method_not_allowed()

    def _method_not_allowed(self) -> None:
        if self._request_is_local():
            self.close_connection = True
            self._error(405, "method_not_allowed", "This endpoint is read/preview/local-save only")

    def _get_bootstrap(self) -> None:
        payload = dict(_mapping(self.food_server.bindings.bootstrap(), "bootstrap"))
        payload["saved_scenarios"] = list(self.food_server.bindings.list_scenarios(None))
        payload["store"] = self.food_server.bindings.verify_store()
        if self.food_server.bindings.production_catalog is not None:
            payload["production_catalog"] = self.food_server.bindings.production_catalog()
        self._json(200, payload)

    def _list_scenarios(self, query: str) -> None:
        values = parse_qs(query, keep_blank_values=True, strict_parsing=False)
        unknown = sorted(set(values) - {"kind"})
        if unknown or any(len(items) != 1 for items in values.values()):
            raise ValueError("scenario list query is invalid")
        kind = None
        if "kind" in values and values["kind"][0]:
            kind = _normal_kind(values["kind"][0])
        rows = list(self.food_server.bindings.list_scenarios(kind))
        self._json(200, {"scenarios": rows, "count": len(rows)})

    def _get_scenario_path(self, path: str, query: str) -> None:
        suffix = path[len("/api/scenarios/") :]
        parts = suffix.split("/")
        if len(parts) not in {1, 2, 3}:
            raise ServiceError(404, "not_found", "Scenario endpoint not found")
        scenario_id = _scenario_id(unquote(parts[0]))
        if len(parts) == 1:
            if query:
                raise ValueError("scenario load does not accept query parameters")
            self._json(200, self.food_server.bindings.load_scenario(scenario_id))
            return
        if parts[1] != "export":
            raise ServiceError(404, "not_found", "Scenario endpoint not found")
        if len(parts) == 3:
            if query:
                raise ValueError("export format cannot be supplied twice")
            export_format = parts[2].lower()
        else:
            values = parse_qs(query, keep_blank_values=True)
            if set(values) - {"format"} or len(values.get("format", [])) != 1:
                raise ValueError("export requires exactly one format parameter")
            export_format = values["format"][0].lower()
        filename = SAFE_EXPORT_NAME.sub("-", scenario_id).strip(".-") or "scenario"
        if export_format == "json":
            self._json(
                200,
                self.food_server.bindings.load_scenario(scenario_id),
                disposition=f'attachment; filename="{filename}.json"',
            )
        elif export_format == "markdown":
            body = self.food_server.bindings.export_markdown(scenario_id).encode("utf-8")
            self._send_bytes(
                200,
                body,
                "text/markdown; charset=utf-8",
                api=True,
                disposition=f'attachment; filename="{filename}.md"',
            )
        elif export_format == "html":
            body = self.food_server.bindings.export_html(scenario_id).encode("utf-8")
            self._send_bytes(
                200,
                body,
                "text/html; charset=utf-8",
                api=True,
                disposition=f'attachment; filename="{filename}.html"',
            )
        else:
            raise ValueError("export format must be json, markdown, or html")

    @staticmethod
    def _request_payload(body: Mapping[str, object]) -> Mapping[str, object]:
        if "request" not in body:
            return body
        if set(body) != {"request"}:
            raise ValueError("preview wrapper may contain only request")
        return _mapping(body["request"], "request")

    def _preview_food_sector(self, body: Mapping[str, object]) -> None:
        request = self._request_payload(body)
        result = self.food_server.bindings.preview_food_sector(request)
        self._json(200, result)

    def _preview_longsaddle(self, body: Mapping[str, object]) -> None:
        request = self._request_payload(body)
        result = self.food_server.bindings.preview_longsaddle(request)
        self._json(200, result)

    def _preview_aquaculture(self, body: Mapping[str, object]) -> None:
        callback = self.food_server.bindings.preview_aquaculture
        if callback is None:
            raise ServiceError(
                503,
                "production_preview_unavailable",
                "Aquaculture production preview is unavailable",
            )
        request = self._request_payload(body)
        self._json(200, callback(request))

    def _preview_crop(self, body: Mapping[str, object]) -> None:
        callback = self.food_server.bindings.preview_crop
        if callback is None:
            raise ServiceError(
                503,
                "production_preview_unavailable",
                "Crop production preview is unavailable",
            )
        request = self._request_payload(body)
        self._json(200, callback(request))

    def _save_scenario(self, body: Mapping[str, object]) -> None:
        allowed = {"scenario_id", "kind", "request", "result"}
        unknown = sorted(set(body) - allowed)
        if unknown:
            raise ValueError("unknown save fields: " + ", ".join(unknown))
        scenario_id = _scenario_id(body.get("scenario_id"))
        kind = _normal_kind(body.get("kind"))
        request = _mapping(body.get("request"), "request")
        stored_request = _request_for_persistence(request)
        supplied = (
            _mapping(body["result"], "result") if "result" in body else None
        )

        # A reopened seeded scenario deliberately contains only a fingerprint,
        # not the raw seed.  Permit an exact immutable retry by comparing it to
        # the already verified local bundle; changed content still falls
        # through to recomputation/conflict handling.
        try:
            existing = self.food_server.bindings.load_scenario(scenario_id)
        except ServiceError as exc:
            if exc.status != 404:
                raise
            existing = None
        if isinstance(existing, Mapping):
            existing_request = existing.get("request")
            existing_result = existing.get("result")
            exact_result = supplied is None or (
                isinstance(existing_result, Mapping)
                and _json_safe(supplied) == _json_safe(existing_result)
            )
            if (
                existing.get("kind") == kind
                and isinstance(existing_request, Mapping)
                and isinstance(existing_result, Mapping)
                and _json_safe(stored_request) == _json_safe(existing_request)
                and exact_result
            ):
                record, replayed = self.food_server.bindings.save_scenario(
                    scenario_id, kind, existing_request, existing_result
                )
                self._json(
                    200,
                    {
                        "scenario": record,
                        "replayed_existing_save": replayed,
                    },
                )
                return

        if kind == FOOD_SECTOR_KIND:
            computed = self.food_server.bindings.preview_food_sector(request)
        elif kind == LONGSADDLE_KIND:
            computed = self.food_server.bindings.preview_longsaddle(request)
        elif kind == AQUACULTURE_KIND:
            callback = self.food_server.bindings.preview_aquaculture
            if callback is None:
                raise ServiceError(
                    503,
                    "production_preview_unavailable",
                    "Aquaculture production preview is unavailable",
                )
            computed = callback(request)
        else:
            callback = self.food_server.bindings.preview_crop
            if callback is None:
                raise ServiceError(
                    503,
                    "production_preview_unavailable",
                    "Crop production preview is unavailable",
                )
            computed = callback(request)
        if supplied is not None:
            if _json_safe(supplied) != _json_safe(computed):
                raise ServiceError(
                    409,
                    "preview_mismatch",
                    "Supplied result does not match a fresh preview of this request",
                )
        record, replayed = self.food_server.bindings.save_scenario(
            scenario_id, kind, stored_request, computed
        )
        self._json(
            200 if replayed else 201,
            {
                "scenario": record,
                "replayed_existing_save": replayed,
            },
        )

    def _serve_static(self, request_path: str) -> None:
        if request_path in {"", "/"} and self.food_server.app_html is not None:
            self._send_bytes(
                200,
                self.food_server.app_html.encode("utf-8"),
                "text/html; charset=utf-8",
                api=False,
            )
            return
        root = self.food_server.static_root
        if root is None:
            self._error(404, "not_found", "Application asset not found")
            return
        target = _safe_static_file(root, request_path)
        if target is None:
            self._error(404, "not_found", "Application asset not found")
            return
        try:
            body = target.read_bytes()
        except OSError:
            self._error(500, "asset_error", "Application asset could not be read")
            return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {
            "application/javascript",
            "application/json",
            "image/svg+xml",
        }:
            content_type += "; charset=utf-8"
        self._send_bytes(200, body, content_type, api=False)


def create_server(
    *,
    host: str = LOOPBACK_HOST,
    port: int = 0,
    bindings: FoodOpsBindings | None = None,
    store_path: Path = DEFAULT_STORE_PATH,
    app_path: Path | None = None,
    app_html: str | None = None,
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
) -> FoodOpsHTTPServer:
    """Bind a server to ``127.0.0.1`` and return it without starting its loop.

    ``port=0`` asks the operating system to choose an available port.  The
    selected value is available through ``server.port`` and ``server.base_url``.
    If no explicit HTML is supplied, ``food_ops_app.render_food_ops_app()`` is
    used.  ``app_path`` is a fallback file/directory for deployments that supply
    static content separately.
    """

    if host != LOOPBACK_HOST:
        raise FoodOpsServerError("host must be 127.0.0.1; network exposure is disabled")
    if type(port) is not int or not 0 <= port <= 65535:
        raise FoodOpsServerError("port must be an integer from 0 through 65535")
    if type(max_body_bytes) is not int or not 1024 <= max_body_bytes <= 16 * 1024 * 1024:
        raise FoodOpsServerError("max_body_bytes must be from 1024 through 16777216")
    if (
        isinstance(request_timeout_seconds, bool)
        or not isinstance(request_timeout_seconds, (int, float))
        or not 0.05 <= request_timeout_seconds <= 300
    ):
        raise FoodOpsServerError(
            "request_timeout_seconds must be from 0.05 through 300"
        )

    static_root: Path | None = None
    fallback_html: str | None = None
    if app_path is not None:
        candidate = Path(app_path).expanduser().resolve()
        if candidate.is_dir():
            static_root = candidate
            index = candidate / "index.html"
            if index.is_file():
                fallback_html = index.read_text(encoding="utf-8")
        elif candidate.is_file():
            fallback_html = candidate.read_text(encoding="utf-8")
            # A single supplied HTML file does not authorize serving its
            # siblings.  Deploy a directory when separate assets are intended.
            static_root = None
        else:
            raise FoodOpsServerError(f"application path does not exist: {candidate}")

    resolved_html = app_html
    if resolved_html is None:
        try:
            resolved_html = _load_default_app()
        except (ImportError, AttributeError) as exc:
            if fallback_html is None:
                raise FoodOpsServerError(
                    "food_ops_app is unavailable and no static application was supplied"
                ) from exc
            resolved_html = fallback_html
    if not isinstance(resolved_html, str) or not resolved_html.strip():
        raise FoodOpsServerError("application HTML must be non-empty text")

    resolved_bindings = bindings if bindings is not None else default_bindings(store_path)
    return FoodOpsHTTPServer(
        (LOOPBACK_HOST, port),
        resolved_bindings,
        app_html=resolved_html,
        static_root=static_root,
        max_body_bytes=max_body_bytes,
        request_timeout_seconds=float(request_timeout_seconds),
    )


class RunningFoodOpsServer:
    """Background server handle with idempotent, clean shutdown."""

    def __init__(self, server: FoodOpsHTTPServer, thread: threading.Thread) -> None:
        self.server = server
        self.thread = thread
        self._closed = False
        self._shutdown_started = False

    @property
    def port(self) -> int:
        return self.server.port

    @property
    def base_url(self) -> str:
        return self.server.base_url

    def close(self) -> None:
        if self._closed:
            return
        if not self._shutdown_started:
            self._shutdown_started = True
            self.server.shutdown()
            self.server.close_active_requests()
            self.server.server_close()
            self.thread.join(timeout=5)
        if self.thread.is_alive():
            raise FoodOpsServerError("food operations server did not stop cleanly")
        if not self.server.wait_for_active_requests(
            self.server.handler_shutdown_timeout_seconds
        ):
            raise FoodOpsServerError(
                "food operations server stopped accepting requests, but an engine "
                "callback did not return before the shutdown deadline"
            )
        self._closed = True

    def __enter__(self) -> "RunningFoodOpsServer":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def start_server(**options: object) -> RunningFoodOpsServer:
    """Create and start a daemon-thread server for embedding or tests."""

    server = create_server(**options)  # type: ignore[arg-type]
    thread = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": 0.05},
        name=f"baen-food-ops-{server.port}",
        daemon=True,
    )
    thread.start()
    return RunningFoodOpsServer(server, thread)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="baen-food-ops-server",
        description=(
            "Run the local Baen food operator. It binds only 127.0.0.1, "
            "writes only its local scenario store, and cannot write Notion or the ledger."
        ),
    )
    parser.add_argument("--port", type=int, default=0, help="local port; 0 chooses a free port")
    parser.add_argument(
        "--host",
        default=LOOPBACK_HOST,
        help="must remain 127.0.0.1",
    )
    parser.add_argument(
        "--database",
        "--store",
        dest="store",
        type=Path,
        default=DEFAULT_STORE_PATH,
    )
    parser.add_argument("--app", type=Path, help="fallback HTML file or static directory")
    parser.add_argument(
        "--open",
        action="store_true",
        help="open the local operator in the default browser after binding",
    )
    parser.add_argument(
        "--max-body-bytes",
        type=int,
        default=DEFAULT_MAX_BODY_BYTES,
    )
    parser.add_argument(
        "--request-timeout-seconds",
        type=float,
        default=DEFAULT_REQUEST_TIMEOUT_SECONDS,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        server = create_server(
            host=args.host,
            port=args.port,
            store_path=args.store,
            app_path=args.app,
            max_body_bytes=args.max_body_bytes,
            request_timeout_seconds=args.request_timeout_seconds,
        )
    except (FoodOpsServerError, OSError, UnicodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Baen Food Operations: {server.base_url}", flush=True)
    print("Local preview/save only — Notion writes: 0; ledger postings: 0", flush=True)
    if args.open and not webbrowser.open(server.base_url, new=2):
        print(
            f"The browser did not accept the request; open {server.base_url}",
            file=sys.stderr,
            flush=True,
        )
    shutdown_clean = True
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.close_active_requests()
        server.server_close()
        shutdown_clean = server.wait_for_active_requests(
            server.handler_shutdown_timeout_seconds
        )
        if not shutdown_clean:
            print(
                "error: an engine callback did not return before the shutdown deadline",
                file=sys.stderr,
            )
    return 0 if shutdown_clean else 3


if __name__ == "__main__":
    raise SystemExit(main())
