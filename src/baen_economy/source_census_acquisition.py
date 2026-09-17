"""Read-only Notion acquisition through the authorized host's actual tool invoker.

The host supplies ``invoke(tool_name, arguments)`` bound to its connected Notion
capability, not a local HTTP proxy. Only fetch and read-only SQL are emitted.
``acquire_collection`` executes live calls, checkpoints every bounded page, then
requires an independent final membership manifest. Offline receipt verification
is a separate operation; it must never be described as a new live acquisition.

Provenance: acquisition/no-dropped-record requirements USER-RULED; this transport
contract and conservative UNKNOWN classification policy MODEL-PROPOSED. Source
properties are SOURCE-DERIVED and never executable instructions or simulation.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import re
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from .source_census import CensusError, SourceRecord, canonical_hash


class AcquisitionError(CensusError):
    """Incomplete or inconsistent evidence: retain checkpoints and fail closed."""


READ_TOOLS = frozenset({"Notion.fetch", "Notion.query-data-sources"})
RELATIONS = frozenset({
    "Controller", "Parent Location", "Sub-Locations", "Faction", "Location",
    "Related NPCs", "Related Faction", "Connected NPCs", "Connected Factions",
    "Key NPCs", "Holder",
})
NUMBERS = frozenset({
    "Capital Invested", "Monthly Revenue", "Monthly Cost", "Employees",
    "Profit Margin", "ROI Pct", "Disposition", "Population", "Days Overdue",
    "Escalation Clock", "Completion", "Active Rumors", "CR", "GURPS CP", "Level",
})


@dataclass(frozen=True)
class CollectionSpec:
    key: str
    data_source_url: str
    columns: tuple[str, ...]
    title_property: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", self.key):
            raise AcquisitionError("invalid collection key")
        if not self.data_source_url.startswith("collection://"):
            raise AcquisitionError("expected a fetched collection:// identifier")
        try:
            UUID(self.data_source_url.removeprefix("collection://"))
        except ValueError as exc:
            raise AcquisitionError("invalid collection UUID") from exc
        if len(set(self.columns)) != len(self.columns):
            raise AcquisitionError("duplicate column names")
        if "url" not in self.columns or self.title_property not in self.columns:
            raise AcquisitionError("source URL and title columns are required")
        if any(not isinstance(c, str) or not c for c in self.columns):
            raise AcquisitionError("invalid column name")


def _q(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def page_query(spec: CollectionSpec, after: str | None, limit: int) -> dict[str, Any]:
    if type(limit) is not int or not 1 <= limit <= 100:
        raise AcquisitionError("page limit must be an integer from 1 to 100")
    predicate = " WHERE url > ?" if after is not None else ""
    query = (
        "SELECT json_group_array(json_array(" + ", ".join(map(_q, spec.columns))
        + ")) AS rows_json FROM (SELECT * FROM " + _q(spec.data_source_url)
        + predicate + " ORDER BY url LIMIT " + str(limit) + ")"
    )
    return {"data": {"mode": "sql", "data_source_urls": [spec.data_source_url],
                     "query": query, "params": [after] if after is not None else []}}


def manifest_query(spec: CollectionSpec, after: str | None = None) -> dict[str, Any]:
    query = (
        "SELECT COUNT(*) AS final_count, COUNT(DISTINCT url) AS unique_count, "
        "GROUP_CONCAT(substr(url,-32),' ') AS ordered_ids, "
        "SUM(CASE WHEN url > ? THEN 1 ELSE 0 END) AS tail_rows FROM "
        "(SELECT url FROM " + _q(spec.data_source_url) + " ORDER BY url)"
    )
    return {"data": {"mode": "sql", "data_source_urls": [spec.data_source_url],
                     "query": query, "params": [after or ""]}}


def unwrap_query(response: Any, spec: CollectionSpec) -> dict[str, Any]:
    """Decode the connected tool's JSON text wrapper; reject truncation/errors."""
    for _ in range(5):
        if isinstance(response, str):
            try:
                response = json.loads(response)
            except json.JSONDecodeError as exc:
                raise AcquisitionError("query response is not complete JSON") from exc
            continue
        if not isinstance(response, Mapping):
            raise AcquisitionError("query response is not an object")
        if response.get("is_error") or response.get("error") or response.get("truncated"):
            raise AcquisitionError("Notion returned an error or truncated evidence")
        if "results" in response:
            break
        if "text" in response:
            response = response["text"]
            continue
        raise AcquisitionError("query response lacks results")
    if not isinstance(response, Mapping) or not isinstance(response.get("results"), list):
        raise AcquisitionError("query results are missing")
    if response.get("has_more") is not False:
        raise AcquisitionError("bounded SQL response is incomplete")
    expected_id = spec.data_source_url.removeprefix("collection://")
    if expected_id not in response.get("data_source_ids", []):
        raise AcquisitionError("response does not identify the requested source")
    return dict(response)


def page_id(url: str) -> str:
    if not isinstance(url, str):
        raise AcquisitionError("source URL is not a string")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in {
        "app.notion.com", "www.notion.so", "notion.so"
    }:
        raise AcquisitionError("record URL is not a Notion HTTPS page")
    match = re.search(r"([0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})$", parsed.path)
    if not match:
        raise AcquisitionError("record URL has no full page UUID")
    return UUID(match.group(1)).hex


def stable_id(url: str) -> str:
    return "notion:page:" + str(UUID(page_id(url)))


def decode_batch(batch: Mapping[str, Any], spec: CollectionSpec) -> list[dict[str, Any]]:
    if batch.get("tool") != "Notion.query-data-sources" or batch.get("mode") != "sql":
        raise AcquisitionError("batch is not a direct Notion SQL receipt")
    if batch.get("data_source_url") != spec.data_source_url or batch.get("collection") != spec.key:
        raise AcquisitionError("batch belongs to a different source")
    if batch.get("response_has_more") is not False:
        raise AcquisitionError("batch response is incomplete")
    if tuple(batch.get("columns", ())) != spec.columns:
        raise AcquisitionError("batch columns changed; reconcile schema before continuing")
    rows = batch.get("rows")
    if not isinstance(rows, list):
        raise AcquisitionError("batch rows are missing")
    limit = batch.get("limit")
    if type(limit) is not int or not 1 <= limit <= 100 or len(rows) > limit:
        raise AcquisitionError("batch exceeds its requested limit")
    decoded = []
    for row in rows:
        if not isinstance(row, list) or len(row) != len(spec.columns):
            raise AcquisitionError("row width does not match column schema")
        record = dict(zip(spec.columns, row, strict=True))
        page_id(record["url"])
        try:
            json.dumps(record, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise AcquisitionError("record contains non-finite or non-JSON data") from exc
        decoded.append(record)
    return decoded


def verify_receipts(spec: CollectionSpec, batches: Sequence[Mapping[str, Any]],
                    proof: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Verify actual receipt membership, not manually asserted aggregate counts."""
    if proof.get("collection") != spec.key or proof.get("data_source_url") != spec.data_source_url:
        raise AcquisitionError("enumeration proof belongs to a different collection")
    if proof.get("tail_rows") != 0:
        raise AcquisitionError("source has unenumerated trailing rows")
    expected = proof.get("final_count")
    if type(expected) is not int or expected < 0:
        raise AcquisitionError("invalid final count")
    for key in ("initial_count", "initial_unique_count", "unique_count"):
        if type(proof.get(key)) is not int or proof[key] != expected:
            raise AcquisitionError("source membership count changed or includes duplicate URLs")
    ids = (proof.get("ordered_ids") or "").split()
    if len(ids) != expected or len(set(ids)) != expected:
        raise AcquisitionError("membership manifest is incomplete or duplicated")
    records: list[dict[str, Any]] = []
    after = None
    for batch in batches:
        if batch.get("after") != after:
            raise AcquisitionError("broken keyset checkpoint chain")
        decoded = decode_batch(batch, spec)
        urls = [item["url"] for item in decoded]
        if urls != sorted(urls) or len(set(urls)) != len(urls):
            raise AcquisitionError("page is unordered or duplicated")
        if after is not None and any(url <= after for url in urls):
            raise AcquisitionError("keyset cursor did not advance")
        records.extend(decoded)
        if urls:
            after = urls[-1]
    captured = [page_id(item["url"]) for item in records]
    if captured != ids:
        raise AcquisitionError("captured records do not equal live final membership")
    if "initial_ordered_ids" in proof and proof["initial_ordered_ids"] != proof.get("ordered_ids"):
        raise AcquisitionError("source membership changed during live acquisition")
    return records


class LiveNotionCensusAcquirer:
    """Bounded direct-tool acquisition, with durable checkpoints before next call.

    ``invoke`` is the authorized host's Notion tool dispatcher. The assistant's
    current connector session executes the same requests directly; Actions only
    transforms those receipts and does not impersonate a live Notion connection.
    """
    def __init__(self, invoke: Callable[[str, dict[str, Any]], Any],
                 checkpoint: Callable[[str, Mapping[str, Any]], None], *, page_size: int = 25):
        if type(page_size) is not int or not 1 <= page_size <= 100:
            raise AcquisitionError("page size outside 1..100")
        self.invoke = invoke
        self.checkpoint = checkpoint
        self.page_size = page_size

    def _call(self, name: str, arguments: dict[str, Any]) -> Any:
        if name not in READ_TOOLS:
            raise AcquisitionError("Notion write or unsupported tool prohibited")
        return self.invoke(name, arguments)

    def _manifest(self, spec: CollectionSpec, after: str | None = None) -> dict[str, Any]:
        result = unwrap_query(self._call("Notion.query-data-sources", manifest_query(spec, after)), spec)
        if len(result["results"]) != 1:
            raise AcquisitionError("expected exactly one manifest row")
        return result["results"][0]

    def acquire_collection(self, spec: CollectionSpec) -> dict[str, Any]:
        batches = []
        captured_at = datetime.now(timezone.utc).isoformat()
        try:
            schema = self._call("Notion.fetch", {"id": spec.data_source_url})
            if isinstance(schema, Mapping) and (schema.get("is_error") or schema.get("truncated")):
                raise AcquisitionError("cannot completely fetch source schema")
            self.checkpoint(spec.key + ".schema", {"response": schema, "captured_at": captured_at})
            initial = self._manifest(spec)
            after = None
            # The bound catches a repeated/non-advancing server cursor immediately.
            for index in range(initial["final_count"] // self.page_size + 2):
                args = page_query(spec, after, self.page_size)
                result = unwrap_query(self._call("Notion.query-data-sources", args), spec)
                if len(result["results"]) != 1 or "rows_json" not in result["results"][0]:
                    raise AcquisitionError("bounded response lacks row payload")
                try:
                    rows = json.loads(result["results"][0]["rows_json"] or "[]")
                except (TypeError, json.JSONDecodeError) as exc:
                    raise AcquisitionError("row payload truncated or invalid") from exc
                batch = {"collection": spec.key, "data_source_url": spec.data_source_url,
                         "capture_date": captured_at[:10], "captured_at": captured_at,
                         "tool": "Notion.query-data-sources", "mode": "sql",
                         "after": after, "limit": self.page_size, "response_has_more": False,
                         "columns": list(spec.columns), "rows": rows, "request": args}
                decoded = decode_batch(batch, spec)
                if decoded and (decoded != sorted(decoded, key=lambda r: r["url"]) or
                                (after is not None and decoded[0]["url"] <= after)):
                    raise AcquisitionError("live keyset cursor did not advance")
                self.checkpoint(f"{spec.key}.{index:03d}", batch)
                batches.append(batch)
                if decoded:
                    after = decoded[-1]["url"]
                if len(decoded) < self.page_size:
                    break
            final = self._manifest(spec, after)
            proof = {**final, "collection": spec.key, "data_source_url": spec.data_source_url,
                     "initial_count": initial["final_count"],
                     "initial_unique_count": initial["unique_count"],
                     "initial_ordered_ids": initial.get("ordered_ids")}
            if proof["final_count"] == 0 and proof.get("tail_rows") is None:
                proof["tail_rows"] = 0
            records = verify_receipts(spec, batches, proof)
            self.checkpoint(spec.key + ".proof", proof)
            return {"enumeration_complete": True, "records": records, "proof": proof,
                    "batches": batches, "captured_at": captured_at}
        except Exception as exc:
            self.checkpoint(spec.key + ".failure", {
                "enumeration_complete": False, "completed_pages": len(batches),
                "error": str(exc), "captured_at": captured_at,
            })
            raise AcquisitionError(f"{spec.key}: acquisition incomplete: {exc}") from exc


def normalize_record(spec: CollectionSpec, row: Mapping[str, Any]) -> dict[str, Any]:
    """Materialize every row, retaining all fields even without a simulator type.

    Dates stay in their own namespaces. SQL rich text can lose mention links;
    this receipt never claims that page bodies or rich-text mentions were fetched.
    """
    if set(row) != set(spec.columns):
        raise AcquisitionError("record properties differ from acquisition schema")
    url = row["url"]
    title = row.get(spec.title_property)
    if not isinstance(title, str) or not title.strip():
        title = "[UNTITLED SOURCE " + page_id(url) + "]"
    numeric = {}
    for name, value in row.items():
        if name in NUMBERS:
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
                raise AcquisitionError(f"{name}: expected a finite number or explicit null")
            numeric[name] = value
    relations = []
    for name in sorted(RELATIONS.intersection(row)):
        value = row[name]
        if value is None:
            continue
        if isinstance(value, str) and value.startswith("["):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise AcquisitionError(f"{name}: incomplete relation JSON") from exc
        if isinstance(value, list):
            for target in value:
                if isinstance(target, str) and target.startswith("https://"):
                    relations.append(stable_id(target))
    # Every original column is retained verbatim as labeled JSON, including nulls.
    facts = [name + ": " + json.dumps(row[name], ensure_ascii=True, allow_nan=False)
             for name in spec.columns if name != "url"]
    state = "SUPERSEDED" if "[SUPERSEDED" in title.upper() else "UNKNOWN"
    notes = row.get("Notes") or ""
    if spec.key.startswith("consequence_ledger") and "DUPLICATE" in notes and "superseded" in notes.lower():
        state = "SUPERSEDED"
    body = {
        "stable_source_id": stable_id(url), "source_url": url, "title": title,
        "source_class": spec.key,
        "region_location": row.get("City") or row.get("Region") or "UNRESOLVED",
        "effective_date": row.get("Date Operational") or row.get("Date Created") or
                          "UNRESOLVED; real-world metadata is not a campaign date",
        "effective_status": row.get("Status") or "UNRESOLVED",
        "direct_relations": sorted(set(relations)), "numeric_properties": numeric,
        "narrative_facts": facts,
        "simulation_relevance": "not_active" if state == "SUPERSEDED" else "active",
        "coverage_state": state, "provenance": "SOURCE-DERIVED",
    }
    result = {**body, "source_hash": canonical_hash(body)}
    SourceRecord.from_mapping(result)
    return result
