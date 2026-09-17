"""Source-bound capacity envelopes that deliberately cannot execute production.

The live Business Registry gives Baen Brickworks and the Neverwinter Clay
Quarries monthly capacity/throughput statements, but it does not give the
material ratio, opening inventories, cost-consolidation treatment, or a ruled
surface-economy date needed for a conserved production run.  This module keeps
the useful source facts while making those absences machine-visible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
import re
from typing import Mapping, Protocol

from .operator_codec import canonical_hash, json_safe


CAPACITY_PROFILE_SCHEMA = "tnp.business.partial-capacity/1"
BRICKWORKS_SOURCE_RECORD_ID = "notion:321e821484b0816c87fbf0fee22835ad"
CLAY_QUARRY_SOURCE_RECORD_ID = "notion:321e821484b081c69bdec30dd49bc5b6"
BRICKWORKS_CAPACITY_PER_MONTH = Decimal("75000")
CLAY_QUARRY_CAPACITY_PER_MONTH = Decimal("2000")

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_BINDING_PROPERTIES = (
    "Date Operational",
    "Employees",
    "Entity",
    "Last Updated",
    "Monthly Cost",
    "Monthly Revenue",
    "Notes",
    "Parent Entity",
    "Status",
)


class CapacityProfileError(ValueError):
    """Raised when a partial-capacity profile is not bound to its sources."""


class RegistrySnapshot(Protocol):
    """Hash-bearing read snapshot interface supplied by ``registry_export``."""

    snapshot_hash: str
    row_hashes: Mapping[str, str]

    def row(self, source_record_id: str) -> Mapping[str, object]: ...

    def property_hash(self, source_record_id: str, property_name: str) -> str: ...


@dataclass(frozen=True, slots=True, order=True)
class CapacityBlocker:
    code: str
    detail: str

    def __post_init__(self) -> None:
        if not self.code.strip() or not self.detail.strip():
            raise CapacityProfileError("capacity blocker requires code and detail")


CAPACITY_BLOCKERS = (
    CapacityBlocker(
        "missing_clay_to_brick_ratio",
        "No source states clay consumed, yield, or reject loss per brick batch.",
    ),
    CapacityBlocker(
        "missing_opening_inventory",
        "Opening clay, work-in-progress, and finished-brick inventories are unknown.",
    ),
    CapacityBlocker(
        "unresolved_cost_consolidation",
        "The source does not say whether Brickworks monthly cost includes Clay Quarry cost.",
    ),
    CapacityBlocker(
        "unruled_surface_economy_date",
        "No accepted surface-economy timeline and effective opening date binds these rows.",
    ),
)


@dataclass(frozen=True, slots=True)
class RegistrySourceBinding:
    snapshot_hash: str
    source_record_id: str
    row_hash: str
    property_hashes: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        _require_sha256(self.snapshot_hash, "registry snapshot hash")
        _require_sha256(self.row_hash, "registry row hash")
        if self.source_record_id not in {
            BRICKWORKS_SOURCE_RECORD_ID,
            CLAY_QUARRY_SOURCE_RECORD_ID,
        }:
            raise CapacityProfileError("capacity binding has an unauthorized source record")
        names = [name for name, _ in self.property_hashes]
        if tuple(names) != _BINDING_PROPERTIES or len(set(names)) != len(names):
            raise CapacityProfileError("capacity property bindings do not match the locked set")
        for name, digest in self.property_hashes:
            if not name.strip():
                raise CapacityProfileError("capacity property binding has no property name")
            _require_sha256(digest, f"registry property hash for {name}")

    def property_hash(self, property_name: str) -> str:
        try:
            return dict(self.property_hashes)[property_name]
        except KeyError as exc:
            raise CapacityProfileError(
                f"capacity binding has no property hash for {property_name}"
            ) from exc

    def to_dict(self) -> dict[str, object]:
        return {
            "snapshot_hash": self.snapshot_hash,
            "source_record_id": self.source_record_id,
            "row_hash": self.row_hash,
            "property_hashes": dict(self.property_hashes),
        }


@dataclass(frozen=True, slots=True)
class SourceCapacityClaim:
    source: RegistrySourceBinding
    commodity_id: str
    unit: str
    capacity_per_month: Decimal
    source_property: str = "Notes"
    realized_quantity: None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if not self.commodity_id.strip() or not self.unit.strip():
            raise CapacityProfileError("capacity claim requires commodity and unit")
        if type(self.capacity_per_month) is not Decimal or not self.capacity_per_month.is_finite():
            raise CapacityProfileError("capacity must be a finite Decimal")
        if self.capacity_per_month <= 0:
            raise CapacityProfileError("capacity must be positive")
        if self.source_property != "Notes":
            raise CapacityProfileError("capacity claim must remain bound to Registry Notes")
        self.source.property_hash(self.source_property)

    def to_dict(self) -> dict[str, object]:
        return json_safe(
            {
                "source": self.source.to_dict(),
                "commodity_id": self.commodity_id,
                "unit": self.unit,
                "period": "month",
                "capacity_per_month": self.capacity_per_month,
                "source_property": self.source_property,
                "source_property_hash": self.source.property_hash(self.source_property),
                "realized_quantity": self.realized_quantity,
                "semantics": "source-reported capacity/throughput envelope only",
            }
        )


@dataclass(frozen=True, slots=True)
class BrickworksPartialCapacityProfile:
    snapshot_hash: str
    brickworks: SourceCapacityClaim
    clay_quarry: SourceCapacityClaim
    blockers: tuple[CapacityBlocker, ...] = field(
        default=CAPACITY_BLOCKERS, init=False
    )
    realized_brick_production: None = field(default=None, init=False)
    realized_clay_extraction: None = field(default=None, init=False)
    realized_clay_consumption: None = field(default=None, init=False)
    opening_clay_inventory: None = field(default=None, init=False)
    opening_work_in_progress: None = field(default=None, init=False)
    opening_brick_inventory: None = field(default=None, init=False)
    actual_production_claimed: bool = field(default=False, init=False)
    conservation_claimed: bool = field(default=False, init=False)
    execution_authorized: bool = field(default=False, init=False)

    def verify(self) -> None:
        _require_sha256(self.snapshot_hash, "capacity-profile snapshot hash")
        if (
            self.brickworks.source.snapshot_hash != self.snapshot_hash
            or self.clay_quarry.source.snapshot_hash != self.snapshot_hash
        ):
            raise CapacityProfileError("capacity claims do not share one registry snapshot")
        if (
            self.brickworks.source.source_record_id != BRICKWORKS_SOURCE_RECORD_ID
            or self.brickworks.commodity_id != "brick"
            or self.brickworks.unit != "brick"
            or self.brickworks.capacity_per_month != BRICKWORKS_CAPACITY_PER_MONTH
        ):
            raise CapacityProfileError("Brickworks capacity claim has drifted")
        if (
            self.clay_quarry.source.source_record_id != CLAY_QUARRY_SOURCE_RECORD_ID
            or self.clay_quarry.commodity_id != "clay"
            or self.clay_quarry.unit != "source ton"
            or self.clay_quarry.capacity_per_month != CLAY_QUARRY_CAPACITY_PER_MONTH
        ):
            raise CapacityProfileError("Clay Quarry capacity claim has drifted")
        if self.blockers != CAPACITY_BLOCKERS:
            raise CapacityProfileError("partial-capacity blockers have drifted")
        nullable_values = (
            self.brickworks.realized_quantity,
            self.clay_quarry.realized_quantity,
            self.realized_brick_production,
            self.realized_clay_extraction,
            self.realized_clay_consumption,
            self.opening_clay_inventory,
            self.opening_work_in_progress,
            self.opening_brick_inventory,
        )
        if any(value is not None for value in nullable_values):
            raise CapacityProfileError("partial-capacity unknowns must remain null")
        if (
            self.actual_production_claimed
            or self.conservation_claimed
            or self.execution_authorized
        ):
            raise CapacityProfileError("partial-capacity profile cannot authorize execution")

    def to_dict(self) -> dict[str, object]:
        self.verify()
        body: dict[str, object] = {
            "schema": CAPACITY_PROFILE_SCHEMA,
            "mode": "partial_capacity_only",
            "snapshot_hash": self.snapshot_hash,
            "capacity_claims": {
                "brickworks": self.brickworks.to_dict(),
                "clay_quarry": self.clay_quarry.to_dict(),
            },
            "unknowns": {
                "realized_brick_production": self.realized_brick_production,
                "realized_clay_extraction": self.realized_clay_extraction,
                "realized_clay_consumption": self.realized_clay_consumption,
                "opening_clay_inventory": self.opening_clay_inventory,
                "opening_work_in_progress": self.opening_work_in_progress,
                "opening_brick_inventory": self.opening_brick_inventory,
            },
            "claims": {
                "actual_production": self.actual_production_claimed,
                "conservation": self.conservation_claimed,
                "execution_authorized": self.execution_authorized,
            },
            "blockers": [
                {"code": blocker.code, "detail": blocker.detail}
                for blocker in self.blockers
            ],
            "warning": (
                "Capacity is not realized production. No material conservation, "
                "inventory movement, operating close, or ledger posting is asserted."
            ),
        }
        result = json_safe(body)
        assert isinstance(result, dict)
        result["profile_hash"] = canonical_hash(body)
        return result


def build_brickworks_partial_capacity(
    registry_snapshot: RegistrySnapshot,
) -> BrickworksPartialCapacityProfile:
    """Build the non-executing profile from a verified Registry snapshot.

    The two source rows and their capacity-bearing ``Notes`` values are locked
    exactly. Any source drift requires a new audit instead of a best-effort parse.
    """

    snapshot_hash = getattr(registry_snapshot, "snapshot_hash", None)
    _require_sha256(snapshot_hash, "registry snapshot hash")
    brickworks_binding = _bind_source(
        registry_snapshot,
        source_record_id=BRICKWORKS_SOURCE_RECORD_ID,
        expected_entity="Baen Brickworks",
        expected_notes="75k bricks/month. Fed by Neverwinter Clay Quarries.",
    )
    clay_binding = _bind_source(
        registry_snapshot,
        source_record_id=CLAY_QUARRY_SOURCE_RECORD_ID,
        expected_entity="Neverwinter Clay Quarries",
        expected_notes="2k tons/mo. Internal transfer.",
    )
    profile = BrickworksPartialCapacityProfile(
        snapshot_hash=snapshot_hash,
        brickworks=SourceCapacityClaim(
            brickworks_binding,
            commodity_id="brick",
            unit="brick",
            capacity_per_month=BRICKWORKS_CAPACITY_PER_MONTH,
        ),
        clay_quarry=SourceCapacityClaim(
            clay_binding,
            commodity_id="clay",
            unit="source ton",
            capacity_per_month=CLAY_QUARRY_CAPACITY_PER_MONTH,
        ),
    )
    profile.verify()
    return profile


def _bind_source(
    registry_snapshot: RegistrySnapshot,
    *,
    source_record_id: str,
    expected_entity: str,
    expected_notes: str,
) -> RegistrySourceBinding:
    try:
        row = registry_snapshot.row(source_record_id)
    except Exception as exc:
        raise CapacityProfileError(
            f"registry snapshot is missing required source {source_record_id}"
        ) from exc
    if not isinstance(row, Mapping):
        raise CapacityProfileError("registry source row must be a mapping")
    if row.get("Entity") != expected_entity:
        raise CapacityProfileError("registry source identity or entity title has drifted")
    if row.get("Notes") != expected_notes:
        raise CapacityProfileError("registry capacity Notes have drifted; re-audit required")
    try:
        row_hash = registry_snapshot.row_hashes[source_record_id]
    except (AttributeError, KeyError, TypeError) as exc:
        raise CapacityProfileError("registry source row has no supplied row hash") from exc
    _require_sha256(row_hash, "registry row hash")
    property_hashes: list[tuple[str, str]] = []
    for property_name in _BINDING_PROPERTIES:
        if property_name not in row:
            raise CapacityProfileError(
                f"registry source row is missing property {property_name}"
            )
        try:
            digest = registry_snapshot.property_hash(source_record_id, property_name)
        except Exception as exc:
            raise CapacityProfileError(
                f"registry source row has no supplied hash for {property_name}"
            ) from exc
        _require_sha256(digest, f"registry property hash for {property_name}")
        property_hashes.append((property_name, digest))
    return RegistrySourceBinding(
        snapshot_hash=registry_snapshot.snapshot_hash,
        source_record_id=source_record_id,
        row_hash=row_hash,
        property_hashes=tuple(property_hashes),
    )


def _require_sha256(value: object, label: str) -> None:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise CapacityProfileError(f"{label} must be a full lowercase SHA-256 digest")
