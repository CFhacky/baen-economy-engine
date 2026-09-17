"""Read-only Business Registry normalization and contradiction detection."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
import hashlib
import re
from typing import Iterable, Mapping, Sequence
from urllib.parse import unquote, urlsplit, urlunsplit

from .domain import (
    AccountingTreatment,
    EntityRecord,
    TemporalState,
    canonical_decimal,
    decimal_or_none,
)


_SLUG_RE = re.compile(r"[^a-z0-9]+")
_DASH_RE = re.compile(r"[\u2010-\u2015\u2212]+")
_ROOT_PARENT_SENTINELS = frozenset({"", "-", "none", "n/a", "na", "null"})
_PROJECTION_RE = re.compile(
    r"\b(projected|projection|forecast|target|at[- ]scale|full capacity|"
    r"when complete|planned revenue|potential revenue)\b",
    re.IGNORECASE,
)


class ConsolidationError(ValueError):
    """Raised instead of silently double-counting a parent and its child."""


@dataclass(frozen=True, slots=True)
class Classification:
    temporal_state: TemporalState
    treatment: AccountingTreatment
    authority_ref: str
    rationale: str
    timeline_id: str | None = None
    effective_ordinal: int | None = None

    def __post_init__(self) -> None:
        if not self.authority_ref.strip() or not self.rationale.strip():
            raise ValueError("classification requires an authority reference and rationale")
        if self.timeline_id is not None and self.timeline_id != self.timeline_id.strip():
            raise ValueError("classification timeline must not contain outer whitespace")
        if self.effective_ordinal is not None and (
            isinstance(self.effective_ordinal, bool)
            or not isinstance(self.effective_ordinal, int)
            or self.effective_ordinal < 0
        ):
            raise ValueError("classification effective ordinal must be a non-negative integer")
        if self.temporal_state is TemporalState.CURRENT and (
            not self.timeline_id or self.effective_ordinal is None
        ):
            raise ValueError("current classification requires a timeline and effective ordinal")


@dataclass(frozen=True, slots=True)
class AuditIssue:
    severity: str
    code: str
    entity: str
    source_ref: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AuditResult:
    row_count: int
    field_counts: dict[str, dict[str, int]]
    raw_totals: dict[str, str]
    issues: tuple[AuditIssue, ...]

    @property
    def blocker_count(self) -> int:
        return sum(issue.severity == "blocker" for issue in self.issues)


def stable_entity_id(name: str) -> str:
    slug = _SLUG_RE.sub("-", name.strip().lower()).strip("-")
    if not slug:
        raise ValueError("entity name cannot produce an empty stable identifier")
    return f"entity:{slug}"


def stable_source_record_id(source_ref: str) -> str:
    parsed = urlsplit(source_ref.strip())
    for segment in reversed([item for item in unquote(parsed.path).split("/") if item]):
        compact = segment.replace("-", "").lower()
        match = re.search(r"([0-9a-f]{32})$", compact)
        if match:
            return f"notion:{match.group(1)}"
    canonical_fallback = urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), "", "")
    )
    digest = hashlib.sha256(canonical_fallback.encode("utf-8")).hexdigest()[:24]
    return f"source:{digest}"


def canonical_name_key(name: str) -> str:
    normalized = _DASH_RE.sub("-", name.casefold())
    normalized = re.sub(r"\s*-\s*", "-", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _parent_or_none(value: object) -> str | None:
    text = _text_or_none(value)
    if text is None:
        return None
    sentinel = canonical_name_key(text)
    if sentinel in _ROOT_PARENT_SENTINELS:
        return None
    return text


def normalize_row(
    row: Mapping[str, object],
    classifications: Mapping[str, Classification] | None = None,
) -> EntityRecord:
    """Normalize one connector row without inferring temporal/accounting truth."""

    name = str(row.get("Entity") or "").strip()
    if not name:
        raise ValueError("registry row has no Entity title")
    source_url = str(row.get("url") or "").strip()
    source_ref = str(source_url or row.get("Source File") or "").strip()
    if not source_ref:
        raise ValueError(f"registry row {name!r} has no source reference")
    entity_id = stable_entity_id(name)
    source_record_id = stable_source_record_id(source_url) if source_url else None
    classification_map = classifications or {}
    classification = (
        classification_map.get(source_record_id) if source_record_id is not None else None
    )
    monthly_revenue = decimal_or_none(row.get("Monthly Revenue"))
    monthly_cost = decimal_or_none(row.get("Monthly Cost"))
    capital_invested = decimal_or_none(row.get("Capital Invested"))
    profit_margin = decimal_or_none(row.get("Profit Margin"))
    source_marks_superseded = (
        "superseded" in name.casefold()
        or "superseded" in str(row.get("Notes") or "").casefold()
        or "superseded" in str(row.get("Status") or "").casefold()
        or "superseded" in str(row.get("Current Activity") or "").casefold()
    )
    if (
        classification is not None
        and classification.temporal_state is TemporalState.CURRENT
        and source_marks_superseded
    ):
        raise ValueError("superseded source material cannot be classified as current")
    searchable = " ".join(
        str(row.get(field) or "")
        for field in ("Date Operational", "Current Activity", "Known Assets", "Notes")
    )
    if (
        classification is not None
        and classification.temporal_state is TemporalState.CURRENT
        and _PROJECTION_RE.search(searchable)
        and any(
            value not in (None, Decimal(0))
            for value in (monthly_revenue, monthly_cost, capital_invested)
        )
    ):
        raise ValueError("projected source values cannot be classified as current")
    temporal_state = (
        classification.temporal_state if classification else TemporalState.UNKNOWN
    )
    treatment = (
        classification.treatment if classification else AccountingTreatment.UNKNOWN
    )
    return EntityRecord(
        entity_id=entity_id,
        name=name,
        source_ref=source_ref,
        source_record_id=source_record_id,
        timeline_id=(classification.timeline_id if classification else None),
        effective_ordinal=(classification.effective_ordinal if classification else None),
        temporal_state=temporal_state,
        treatment=treatment,
        parent_name=_parent_or_none(row.get("Parent Entity")),
        status=_text_or_none(row.get("Status")),
        sector=_text_or_none(row.get("Sector")),
        city=_text_or_none(row.get("City")),
        monthly_revenue=monthly_revenue,
        monthly_cost=monthly_cost,
        capital_invested=capital_invested,
        profit_margin=profit_margin,
        date_operational_text=_text_or_none(row.get("Date Operational")),
        source_last_updated_text=_text_or_none(row.get("Last Updated")),
        as_of_campaign_date=_text_or_none(row.get("As Of Campaign Date")),
        classification_authority_ref=(classification.authority_ref if classification else None),
        classification_rationale=(classification.rationale if classification else None),
    )


def normalize_rows(
    rows: Iterable[Mapping[str, object]],
    classifications: Mapping[str, Classification] | None = None,
) -> tuple[EntityRecord, ...]:
    materialized = list(rows)
    audit = audit_rows(materialized)
    identity_blockers = {
        "missing_entity", "missing_source_ref", "duplicate_entity_name",
        "missing_source_record_id", "duplicate_source_record_id",
        "stable_id_collision", "self_parent",
    }
    blocking = [issue for issue in audit.issues if issue.code in identity_blockers]
    if blocking:
        codes = ", ".join(sorted({issue.code for issue in blocking}))
        raise ValueError(f"registry identity audit failed closed: {codes}")
    return tuple(normalize_row(row, classifications) for row in materialized)


def _text_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _sum_field(rows: Sequence[Mapping[str, object]], field: str) -> Decimal:
    total = Decimal(0)
    for row in rows:
        value = decimal_or_none(row.get(field))
        if value is not None:
            total += value
    return total


def audit_rows(rows: Iterable[Mapping[str, object]]) -> AuditResult:
    """Audit rows under an engine-owned decimal context.

    Callers may change the process-wide Decimal context.  Source receipt totals
    and contradiction checks must remain identical regardless.
    """

    materialized = list(rows)
    with localcontext(Context(prec=64, rounding=ROUND_HALF_EVEN)):
        return _audit_materialized_rows(materialized)


def _audit_materialized_rows(
    materialized: Sequence[Mapping[str, object]],
) -> AuditResult:
    issues: list[AuditIssue] = []
    field_counts: dict[str, dict[str, int]] = {}
    for field in ("Status", "Sector", "City", "Neglect Status"):
        counts = Counter(str(row.get(field) or "<missing>") for row in materialized)
        field_counts[field] = dict(sorted(counts.items()))

    names: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    stable_ids: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    source_record_ids: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    by_name: dict[str, Mapping[str, object]] = {}
    children: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in materialized:
        name = str(row.get("Entity") or "").strip()
        source_url = str(row.get("url") or "").strip()
        ref = str(source_url or row.get("Source File") or "").strip()
        if not name:
            issues.append(AuditIssue("blocker", "missing_entity", "<missing>", ref, "Row has no Entity title."))
            continue
        if not ref:
            issues.append(AuditIssue(
                "blocker", "missing_source_ref", name, "",
                "Row has no Notion URL or Source File reference.",
            ))
        if not source_url:
            issues.append(AuditIssue(
                "blocker", "missing_source_record_id", name, ref,
                "Row has no Notion record URL and cannot receive an identity-bound classification.",
            ))
        else:
            source_record_ids[stable_source_record_id(source_url)].append(row)
        names[name.casefold()].append(row)
        stable_ids[stable_entity_id(name)].append(row)
        by_name[canonical_name_key(name)] = row
        parent = _parent_or_none(row.get("Parent Entity"))
        if parent:
            children[canonical_name_key(parent)].append(row)
            if canonical_name_key(parent) == canonical_name_key(name):
                issues.append(AuditIssue("blocker", "self_parent", name, ref, "Entity names itself as parent."))

        margin = decimal_or_none(row.get("Profit Margin"))
        revenue = decimal_or_none(row.get("Monthly Revenue"))
        cost = decimal_or_none(row.get("Monthly Cost"))
        if margin is not None and revenue not in (None, Decimal(0)) and cost is not None:
            expected = (revenue - cost) / revenue
            if abs(expected - margin) > Decimal("0.01"):
                issues.append(AuditIssue(
                    "blocker" if abs(margin) > 1 else "warning",
                    "margin_arithmetic_mismatch", name, ref,
                    f"Recorded margin {margin} differs from revenue/cost result {expected.quantize(Decimal('0.0001'))}.",
                ))
        elif margin is not None and abs(margin) > 1:
            issues.append(AuditIssue(
                "warning", "margin_basis_unknown", name, ref,
                f"Profit Margin {margin} may be a percentage or an unbounded loss ratio; revenue/cost cannot resolve it.",
            ))
        searchable = " ".join(
            str(row.get(field) or "")
            for field in ("Date Operational", "Current Activity", "Known Assets", "Notes")
        )
        if revenue not in (None, Decimal(0)) and _PROJECTION_RE.search(searchable):
            issues.append(AuditIssue(
                "warning", "projection_in_current_field", name, ref,
                "A populated Monthly Revenue row contains projection/capacity language.",
            ))
        if str(row.get("Status") or "") == "Operational" and not str(row.get("Date Operational") or "").strip():
            issues.append(AuditIssue(
                "warning", "operational_without_date", name, ref,
                "Operational row has no Date Operational value.",
            ))
        operational_text = str(row.get("Date Operational") or "")
        if re.search(r"\b(?:149[6-9]|15\d\d)\b", operational_text):
            issues.append(AuditIssue(
                "warning", "future_dated_row", name, ref,
                f"Date Operational {operational_text!r} requires an explicit timeline/as-of classification.",
            ))
        if any(
            "superseded" in str(row.get(field) or "").casefold()
            for field in ("Entity", "Notes", "Status", "Current Activity")
        ):
            issues.append(AuditIssue(
                "blocker", "superseded_row", name, ref,
                "Superseded material must be retained for provenance but excluded from current totals.",
            ))

    for same_name_rows in names.values():
        if len(same_name_rows) > 1:
            name = str(same_name_rows[0].get("Entity"))
            issues.append(AuditIssue(
                "blocker", "duplicate_entity_name", name,
                str(same_name_rows[0].get("url") or ""),
                f"{len(same_name_rows)} rows share the same case-insensitive entity name.",
            ))

    for entity_id, same_id_rows in stable_ids.items():
        distinct_names = {str(row.get("Entity") or "").casefold() for row in same_id_rows}
        if len(distinct_names) > 1:
            issues.append(AuditIssue(
                "blocker", "stable_id_collision", str(same_id_rows[0].get("Entity")),
                str(same_id_rows[0].get("url") or ""),
                f"{len(same_id_rows)} distinct names normalize to {entity_id}.",
            ))

    for source_record_id, same_source_rows in source_record_ids.items():
        if len(same_source_rows) > 1:
            issues.append(AuditIssue(
                "blocker", "duplicate_source_record_id",
                str(same_source_rows[0].get("Entity") or "<missing>"),
                str(same_source_rows[0].get("url") or ""),
                f"{len(same_source_rows)} rows share source identity {source_record_id}.",
            ))

    for parent_key, child_rows in children.items():
        parent = by_name.get(parent_key)
        if parent is None:
            first = child_rows[0]
            issues.append(AuditIssue(
                "warning", "unresolved_parent", str(first.get("Parent Entity")),
                str(first.get("url") or ""),
                f"Referenced by {len(child_rows)} child row(s), but no matching parent row exists.",
            ))
            continue
        parent_revenue = decimal_or_none(parent.get("Monthly Revenue")) or Decimal(0)
        child_revenue = sum(
            (decimal_or_none(child.get("Monthly Revenue")) or Decimal(0) for child in child_rows),
            Decimal(0),
        )
        if parent_revenue and child_revenue:
            issues.append(AuditIssue(
                "blocker", "parent_child_flow_overlap", str(parent.get("Entity")),
                str(parent.get("url") or ""),
                f"Parent records {parent_revenue} revenue while {len(child_rows)} children record {child_revenue}; consolidation treatment is required.",
            ))

    return AuditResult(
        row_count=len(materialized),
        field_counts=field_counts,
        raw_totals={
            "capital_invested": canonical_decimal(_sum_field(materialized, "Capital Invested")),
            "monthly_revenue": canonical_decimal(_sum_field(materialized, "Monthly Revenue")),
            "monthly_cost": canonical_decimal(_sum_field(materialized, "Monthly Cost")),
            "employees": canonical_decimal(_sum_field(materialized, "Employees")),
        },
        issues=tuple(sorted(issues, key=lambda issue: (issue.severity != "blocker", issue.code, issue.entity))),
    )


def consolidated_monthly_totals(
    records: Iterable[EntityRecord], *, timeline_id: str, as_of_ordinal: int,
) -> dict[str, Decimal | None]:
    if not isinstance(timeline_id, str) or not timeline_id.strip():
        raise ConsolidationError("consolidation timeline is required")
    if timeline_id != timeline_id.strip():
        raise ConsolidationError("consolidation timeline must not contain outer whitespace")
    if (
        isinstance(as_of_ordinal, bool)
        or not isinstance(as_of_ordinal, int)
        or as_of_ordinal < 0
    ):
        raise ConsolidationError("consolidation as-of ordinal must be a non-negative integer")
    materialized = list(records)
    for record in materialized:
        _validate_consolidation_record(record)
    known_timelines = {
        record.timeline_id for record in materialized if record.timeline_id is not None
    }
    if timeline_id not in known_timelines:
        raise ConsolidationError(f"unknown consolidation timeline: {timeline_id}")
    entity_ids = [record.entity_id for record in materialized]
    source_ids = [record.source_record_id for record in materialized if record.source_record_id]
    if len(entity_ids) != len(set(entity_ids)) or len(source_ids) != len(set(source_ids)):
        raise ConsolidationError("duplicate stable entity or source identity in consolidation input")

    all_names = {canonical_name_key(record.name) for record in materialized}
    unresolved_parents = [
        record for record in materialized
        if record.parent_name and canonical_name_key(record.parent_name) not in all_names
    ]
    if unresolved_parents:
        names = ", ".join(sorted(record.parent_name or "" for record in unresolved_parents))
        raise ConsolidationError(f"unresolved substantive parent identity: {names}")

    scoped = [
        record for record in materialized
        if record.timeline_id == timeline_id
        and record.effective_ordinal is not None
        and record.effective_ordinal <= as_of_ordinal
    ]
    eligible = [record for record in scoped if record.contributes_current_revenue or record.contributes_current_cost]
    eligible_names = {canonical_name_key(record.name) for record in eligible}
    conflicts = [
        record
        for record in eligible
        if record.parent_name and canonical_name_key(record.parent_name) in eligible_names
    ]
    if conflicts:
        pairs = ", ".join(f"{record.parent_name} -> {record.name}" for record in conflicts)
        raise ConsolidationError(f"eligible parent and child would both consolidate: {pairs}")
    revenue_records = [record for record in scoped if record.contributes_current_revenue]
    cost_records = [record for record in scoped if record.contributes_current_cost]

    def complete_sum(rows: list[EntityRecord], field: str) -> Decimal | None:
        values = [getattr(record, field) for record in rows]
        if any(value is None for value in values):
            return None
        return sum((value for value in values if value is not None), Decimal(0))

    return {
        "monthly_revenue": complete_sum(revenue_records, "monthly_revenue"),
        "monthly_cost": complete_sum(cost_records, "monthly_cost"),
    }


def _validate_consolidation_record(record: object) -> None:
    """Recheck normalized-record invariants at the public calculation boundary."""

    if type(record) is not EntityRecord:
        raise ConsolidationError(
            "consolidation accepts only concrete normalized EntityRecord values"
        )
    if not isinstance(record.source_record_id, str) or not record.source_record_id.strip():
        raise ConsolidationError("every consolidation record requires a stable source identity")
    for value, label in (
        (record.entity_id, "entity ID"),
        (record.name, "entity name"),
        (record.source_ref, "source reference"),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ConsolidationError(f"consolidation record {label} is required")
    if not isinstance(record.temporal_state, TemporalState):
        raise ConsolidationError("consolidation record temporal state has the wrong type")
    if not isinstance(record.treatment, AccountingTreatment):
        raise ConsolidationError("consolidation record treatment has the wrong type")
    if record.timeline_id is not None and (
        not isinstance(record.timeline_id, str)
        or not record.timeline_id.strip()
        or record.timeline_id != record.timeline_id.strip()
    ):
        raise ConsolidationError("record timeline must be a canonical non-empty string")
    if record.effective_ordinal is not None and (
        type(record.effective_ordinal) is not int or record.effective_ordinal < 0
    ):
        raise ConsolidationError(
            "record effective ordinal must be a non-negative integer"
        )
    for field in (
        "monthly_revenue",
        "monthly_cost",
        "capital_invested",
        "profit_margin",
    ):
        value = getattr(record, field)
        if value is not None and (type(value) is not Decimal or not value.is_finite()):
            raise ConsolidationError(f"record {field} must be a finite Decimal or unknown")
    if record.temporal_state is TemporalState.CURRENT:
        if record.timeline_id is None or record.effective_ordinal is None:
            raise ConsolidationError(
                "current record requires a timeline and effective ordinal"
            )
        if not all(
            isinstance(value, str) and bool(value.strip())
            for value in (
                record.classification_authority_ref,
                record.classification_rationale,
            )
        ):
            raise ConsolidationError(
                "current record requires accepted classification provenance"
            )
        source_shape = " ".join(
            value
            for value in (
                record.name,
                record.status or "",
                record.date_operational_text or "",
            )
            if isinstance(value, str)
        )
        if "superseded" in source_shape.casefold():
            raise ConsolidationError(
                "superseded source material cannot enter current consolidation"
            )
        if (
            _PROJECTION_RE.search(source_shape)
            and any(
                value not in (None, Decimal(0))
                for value in (
                    record.monthly_revenue,
                    record.monthly_cost,
                    record.capital_invested,
                )
            )
        ):
            raise ConsolidationError(
                "projected source values cannot enter current consolidation"
            )
