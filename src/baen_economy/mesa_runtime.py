"""Direct integration with the pinned Mesa simulation product.

This is intentionally different from :mod:`baen_economy.upstream_adaptations`.
Mesa is a Python simulation framework with a usable library boundary, so Baen
uses the actual product here rather than copying its scheduler/data collector.

The exact inspected/pinned upstream is Mesa commit
``20841b12559ef920dd4c8263a09fe75ceac7250c`` (Mesa 4.0.0a0, Apache-2.0).
That revision requires Python >= 3.12, so this runtime is optional.  The base
Baen package remains importable on Python 3.11; callers that choose Mesa must
install the ``mesa`` extra and run on Python 3.12+.

This module is preview/scenario infrastructure only.  Calling it never grants
permission to advance the canonical campaign clock or post to the canonical
ledger.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from importlib import import_module
from importlib.util import find_spec
from typing import Mapping, Sequence

MESA_COMMIT = "20841b12559ef920dd4c8263a09fe75ceac7250c"
MESA_VERSION = "4.0.0a0"


class MesaRuntimeUnavailable(RuntimeError):
    """The pinned Mesa product is not installed or is the wrong revision family."""


@dataclass(frozen=True, slots=True)
class MesaProductEvent:
    """One event submitted to Mesa's own event scheduler."""

    tick: int
    priority: str
    event_id: str
    payload: Mapping[str, object]

    def __post_init__(self) -> None:
        if type(self.tick) is not int or self.tick < 0:
            raise ValueError("Mesa event tick must be a non-negative integer")
        if self.priority not in {"HIGH", "DEFAULT", "LOW"}:
            raise ValueError("Mesa event priority must be HIGH, DEFAULT, or LOW")
        if not isinstance(self.event_id, str) or not self.event_id.strip():
            raise ValueError("Mesa event_id is required")
        if not isinstance(self.payload, Mapping):
            raise ValueError("Mesa event payload must be a mapping")


@dataclass(frozen=True, slots=True)
class MesaProductRun:
    """Read-only result returned after Mesa runs a preview horizon."""

    upstream: str
    upstream_commit: str
    upstream_version: str
    final_time: int
    executed_events: tuple[dict[str, object], ...]
    collected_event_counts: tuple[int, ...]
    canonical_time_advanced: bool = False


def mesa_available() -> bool:
    """Return whether an importable Mesa installation is present."""

    return find_spec("mesa") is not None


def _load_mesa():
    if not mesa_available():
        raise MesaRuntimeUnavailable(
            "Mesa is not installed. On Python 3.12+, install baen-economy-engine[mesa]."
        )
    mesa = import_module("mesa")
    version = getattr(mesa, "__version__", None)
    if version != MESA_VERSION:
        raise MesaRuntimeUnavailable(
            f"Baen expects pinned Mesa {MESA_VERSION} from {MESA_COMMIT}; found {version!r}."
        )
    return mesa, import_module("mesa.time")


def run_mesa_preview(
    events: Sequence[MesaProductEvent],
    *,
    until_tick: int,
    seed: int = 0,
) -> MesaProductRun:
    """Run a deterministic preview using Mesa's actual Model/Event/DataCollector.

    Mesa owns event storage, priority ordering, model time, RNG initialization,
    event execution, and data collection.  Baen supplies only source/campaign
    events and reads the resulting preview trace.
    """

    if isinstance(events, (str, bytes)) or not isinstance(events, Sequence):
        raise ValueError("events must be a sequence of MesaProductEvent values")
    if type(until_tick) is not int or until_tick < 0:
        raise ValueError("until_tick must be a non-negative integer")
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    materialized = tuple(events)
    if any(type(event) is not MesaProductEvent for event in materialized):
        raise ValueError("events must contain only MesaProductEvent values")
    ids = [event.event_id for event in materialized]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate Mesa event_id")
    if any(event.tick > until_tick for event in materialized):
        raise ValueError("event lies beyond requested preview horizon")

    mesa, mesa_time = _load_mesa()
    priority = {
        "HIGH": mesa_time.Priority.HIGH,
        "DEFAULT": mesa_time.Priority.DEFAULT,
        "LOW": mesa_time.Priority.LOW,
    }

    class _BaenMesaModel(mesa.Model):
        def __init__(self) -> None:
            super().__init__(rng=seed)
            self.executed_events: list[dict[str, object]] = []
            self.event_count = 0
            # DataCollector is Mesa's product, not a copied Baen implementation.
            self.collector = mesa.DataCollector(
                model_reporters={"event_count": "event_count"}
            )
            # Mesa stores callbacks weakly.  Keep partials strongly referenced
            # for the lifetime of this preview model.
            self.callbacks: list[object] = []

        def record_event(self, event: MesaProductEvent) -> None:
            self.executed_events.append(
                {
                    "event_id": event.event_id,
                    "tick": int(self.time),
                    "priority": event.priority,
                    "payload": dict(event.payload),
                }
            )
            self.event_count += 1
            self.collector.collect(self)

    model = _BaenMesaModel()

    # Schedule in canonical deterministic input order.  Mesa itself owns the
    # event queue and priority/time execution semantics after submission.
    for event in sorted(materialized, key=lambda value: (value.tick, value.event_id)):
        callback = partial(model.record_event, event)
        model.callbacks.append(callback)
        model.schedule_event(callback, at=event.tick, priority=priority[event.priority])

    model.run_until(until_tick)
    counts = tuple(int(value) for value in model.collector.model_vars["event_count"])
    return MesaProductRun(
        upstream="Mesa",
        upstream_commit=MESA_COMMIT,
        upstream_version=MESA_VERSION,
        final_time=int(model.time),
        executed_events=tuple(model.executed_events),
        collected_event_counts=counts,
        canonical_time_advanced=False,
    )
