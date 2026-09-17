"""Read-only Notion acquisition and lossless row-level census materialization.

DirectNotionAcquisition calls the installed Notion tools through the authorized
host's dispatcher. It exposes no Notion write, HTTP proxy, or model simulator.
The same live responses can be checkpointed as receipts and assembled in CI.
A receipt is evidence of a read, not permission to declare a collection complete.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Callable, Mapping
from urllib.parse import urlparse
from uuid import UUID

SCHEMA = "tnp.economy.live-acquisition/1"
STATES = ("SIMULATED", "CONTEXT_ONLY", "FUTURE", "HISTORICAL", "SUPERSEDED",
          "CONFLICT", "MISSING_MECHANICS", "MISSING_DATA", "UNKNOWN")
PROVENANCE = ("USER-RULED", "SOURCE-DERIVED", "UPSTREAM-ADOPTED", "MODEL-PROPOSED", "UNRESOLVED")
READ_TOOLS = frozenset({"Notion.fetch", "Notion.query-data-sources"})


class AcquisitionError(ValueError):
    """Incomplete or inconsistent acquisition; never silently skip a source."""


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def seal(body: dict, field: str = "source_hash") -> dict:
    return {**body, field: digest(body)}


def page_id(url: str) -> str:
    if not isinstance(url, str) or urlparse(url).hostname not in {"app.notion.com", "www.notion.so", "notion.so"}:
        raise AcquisitionError("source URL must identify an actual Notion page")
    compact = urlparse(url).path.replace("-", "")
    match = re.search(r"([0-9a-fA-F]{32})$", compact)
    if not match:
        raise AcquisitionError(f"invalid Notion page identity: {url}")
    return str(UUID(match.group(1)))


def stable_id(url: str) -> str:
    return "notion:page:" + page_id(url)


def unpack_response(response: Mapping) -> dict:
    """Decode the connector's JSON text wrapper without summarizing its rows."""
    value = dict(response)
    if "text" in value and isinstance(value["text"], str):
        value = json.loads(value["text"])
    if value.get("is_error") or value.get("error") or value.get("truncated"):
        raise AcquisitionError("connector returned an error or truncated response")
    if not isinstance(value.get("results"), list) or type(value.get("has_more")) is not bool:
        raise AcquisitionError("connector pagination/result metadata missing")
    return value


@dataclass(frozen=True)
class CollectionSpec:
    key: str
    data_source_url: str
    title: str
    source_class: str
    title_property: str
    columns: tuple[str, ...]
    numeric_properties: tuple[str, ...] = ()
    relation_properties: tuple[str, ...] = ()
    json_properties: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping) -> "CollectionSpec":
        fields = dict(value)
        for name in ("columns", "numeric_properties", "relation_properties", "json_properties"):
            if name in fields:
                fields[name] = tuple(fields[name])
        result = cls(**fields)
        if not result.data_source_url.startswith("collection://"):
            raise AcquisitionError("missing Notion collection identity")
        UUID(result.data_source_url.removeprefix("collection://"))
        if "url" not in result.columns or result.title_property not in result.columns:
            raise AcquisitionError("collection specification omits identity/title")
        if len(set(result.columns)) != len(result.columns):
            raise AcquisitionError("duplicate source columns")
        return result

    def query(self, after: str, limit: int) -> dict:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise AcquisitionError("batch limit must be 1..100")
        table = '"' + self.data_source_url.replace('"', '""') + '"'
        columns = ",".join('"' + c.replace('"', '""') + '"' for c in self.columns)
        return {"data": {"mode": "sql", "data_source_urls": [self.data_source_url],
                "query": f"SELECT json_group_array(json_array({columns})) AS rows_json FROM "
                         f"(SELECT * FROM {table} WHERE url > ? ORDER BY url LIMIT ?)",
                "params": [after, limit]}}

    def count_query(self) -> dict:
        return {"data": {"mode": "sql", "data_source_urls": [self.data_source_url],
                "query": f'SELECT COUNT(*) AS row_count, COUNT(DISTINCT url) AS distinct_urls FROM "{self.data_source_url}"'}}


class DirectNotionAcquisition:
    """Executable tool-host acquisition. The caller supplies installed-tool dispatch.

    call_tool(name, arguments) must invoke that actual connector and return its
    complete response. Tests use an explicitly fake dispatcher; production does not.
    on_receipt can durably persist each completed bounded batch before the next read.
    """
    def __init__(self, call_tool: Callable[[str, dict], Mapping], on_receipt: Callable[[dict], None]):
        self._dispatch = call_tool
        self._persist = on_receipt

    def _call(self, tool: str, arguments: dict) -> Mapping:
        if tool not in READ_TOOLS:
            raise AcquisitionError("Notion writes are prohibited")
        return self._dispatch(tool, arguments)

    def acquire(self, spec: CollectionSpec, limit: int = 25) -> tuple[list[dict], dict]:
        schema = self._call("Notion.fetch", {"id": spec.data_source_url})
        if schema.get("is_error") or schema.get("error"):
            raise AcquisitionError("cannot read live source schema")
        before = unpack_response(self._call("Notion.query-data-sources", spec.count_query()))
        if len(before["results"]) != 1:
            raise AcquisitionError("invalid opening count response")
        receipts, after = [], ""
        while True:
            response = unpack_response(self._call("Notion.query-data-sources", spec.query(after, limit)))
            source_ids = response.get("data_source_ids", [])
            if spec.data_source_url.removeprefix("collection://") not in source_ids:
                raise AcquisitionError("query returned another data source")
            if response["has_more"] or len(response["results"]) != 1:
                raise AcquisitionError("aggregate query response is incomplete")
            rows = json.loads(response["results"][0]["rows_json"])
            receipt = {"collection": spec.key, "data_source_url": spec.data_source_url,
                       "tool": "Notion.query-data-sources", "mode": "sql",
                       "capture_date": datetime.now(timezone.utc).isoformat(),
                       "after": after, "limit": limit, "response_has_more": False,
                       "columns": list(spec.columns), "rows": rows}
            self._persist(receipt)
            if not rows:
                break
            _validate_rows(spec, rows, after, limit)
            receipts.append(receipt)
            after = rows[-1][spec.columns.index("url")]
        end = unpack_response(self._call("Notion.query-data-sources", spec.count_query()))
        if len(end["results"]) != 1:
            raise AcquisitionError("invalid closing count response")
        proof = {"start": before["results"][0], "end": end["results"][0],
                 "terminal_after": after, "terminal_urls_json": "[]"}
        verify_enumeration(spec, receipts, proof)
        return receipts, proof


def _validate_rows(spec: CollectionSpec, rows: list, after: str, limit: int) -> None:
    if not isinstance(rows, list) or len(rows) > limit:
        raise AcquisitionError("invalid bounded row array")
    cursor = after
    for row in rows:
        if not isinstance(row, list) or len(row) != len(spec.columns):
            raise AcquisitionError(f"{spec.key}: row column count mismatch")
        url = row[spec.columns.index("url")]
        page_id(url)
        if url <= cursor:
            raise AcquisitionError("duplicate or out-of-order source URL")
        cursor = url
        digest(row)  # rejects non-finite and unserializable source values


def verify_enumeration(spec: CollectionSpec, receipts: list[dict], proof: Mapping | None) -> dict:
    cursor, rows, identities = "", [], set()
    for receipt in receipts:
        if receipt.get("data_source_url") != spec.data_source_url or receipt.get("collection") != spec.key:
            raise AcquisitionError("receipt source identity mismatch")
        if receipt.get("tool") != "Notion.query-data-sources" or receipt.get("mode") != "sql":
            raise AcquisitionError("receipt is not an installed-connector SQL read")
        if receipt.get("after") != cursor or receipt.get("response_has_more") is not False:
            raise AcquisitionError("missing/incomplete keyset page")
        if "columns" in receipt and tuple(receipt["columns"]) != spec.columns:
            raise AcquisitionError("source column schema drift")
        batch = receipt["rows"]
        _validate_rows(spec, batch, cursor, receipt["limit"])
        for row in batch:
            identity = stable_id(row[spec.columns.index("url")])
            if identity in identities:
                raise AcquisitionError("duplicate stable source identity")
            identities.add(identity)
        rows.extend(batch)
        if batch:
            cursor = batch[-1][spec.columns.index("url")]
    complete = False
    blockers = []
    if proof is None:
        blockers.append("terminal enumeration/count reconciliation has not been captured")
    else:
        counts = [proof.get(side, {}).get(field) for side in ("start", "end")
                  for field in ("row_count", "distinct_urls")]
        if any(type(n) is not int or n < 0 for n in counts):
            raise AcquisitionError("opening/closing count evidence missing")
        terminal = json.loads(proof.get("terminal_urls_json", "null"))
        complete = (all(n == len(rows) for n in counts) and terminal == []
                    and proof.get("terminal_after") == cursor)
        if not complete:
            blockers.append("live counts, acquired IDs, or terminal page do not reconcile")
    return {"rows": rows, "enumeration_complete": complete, "acquired_count": len(rows),
            "last_url": cursor, "ids_hash": digest(sorted(identities)), "blockers": blockers}


def _decode(value: object) -> object:
    if isinstance(value, str) and value.startswith("["):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return value
        if isinstance(parsed, list):
            return parsed
    return value


def materialize(spec: CollectionSpec, row: list) -> dict:
    """Retain every source property, including null, zero and unsupported kinds."""
    _validate_rows(spec, [row], "", 1)
    properties = dict(zip(spec.columns, row, strict=True))
    for name in (*spec.relation_properties, *spec.json_properties):
        properties[name] = _decode(properties.get(name))
    relations = {}
    for name in spec.relation_properties:
        value = properties.get(name)
        if value is None:
            relations[name] = None
        elif isinstance(value, list) and all(isinstance(x, str) for x in value):
            relations[name] = [{"source_id": stable_id(url), "url": url} for url in value]
        else:
            raise AcquisitionError(f"unreadable native relation property: {name}")
    title = properties.get(spec.title_property)
    if not isinstance(title, str) or not title.strip():
        title = "[UNTITLED SOURCE] " + page_id(properties["url"])
    numeric = {name: properties.get(name) for name in spec.numeric_properties}
    for name, number in numeric.items():
        if number is not None and (type(number) not in (int, float)):
            raise AcquisitionError(f"non-numeric source property {name}")
    dates = {key: value for key, value in properties.items()
             if key.startswith("date:") or key in {"Date Operational", "Last Updated", "Last Attended",
                 "Date Created", "Date Resolved", "Deadline", "createdTime"}}
    facts = {key: value for key, value in properties.items() if key in
             {"Notes", "Current Activity", "Known Assets", "Garrison", "Context", "Cascade Effects",
              "Consequence If Broken", "Pressure Target", "Recipient", "Leadership", "Parent Entity"}}
    # A literal superseded title is source evidence. Other temporal relevance is
    # intentionally not guessed from creation/edit timestamps or one future year.
    superseded = title.upper().startswith("[SUPERSEDED")
    raw = {"data_source_url": spec.data_source_url, "properties": properties}
    body = {"stable_source_id": stable_id(properties["url"]),
            "source_url": properties["url"], "source_class": spec.source_class,
            "collection": spec.key, "title": title,
            "region_location": {name: properties.get(name) for name in ("City", "Region", "Parent Location")},
            "relationships": relations,
            "text_relationships": {name: properties.get(name) for name in ("Parent Entity", "Leadership", "Recipient") if name in properties},
            "dates": dates, "status": properties.get("Status"),
            "numeric_properties": numeric, "narrative_facts": facts,
            "simulation_relevance": "superseded" if superseded else "UNRESOLVED",
            "coverage_state": "SUPERSEDED" if superseded else "UNKNOWN",
            "provenance": "SOURCE-DERIVED", "coverage_provenance": "SOURCE-DERIVED" if superseded else "MODEL-PROPOSED",
            "source_properties": properties, "raw_source_hash": digest(raw),
            "content_scope": "SQL property projection; page body and faithful rich-text not yet acquired"}
    return seal(body)


def to_legacy(record: Mapping) -> dict:
    """Compatibility view for existing coverage-check; detailed record is retained."""
    body = {"stable_source_id": record["stable_source_id"], "source_url": record["source_url"],
            "title": record["title"], "source_class": record["source_class"],
            "region_location": json.dumps(record["region_location"], sort_keys=True, ensure_ascii=True),
            "effective_date": json.dumps(record["dates"], sort_keys=True, ensure_ascii=True),
            "effective_status": record["status"] or "UNRESOLVED",
            "direct_relations": sorted({item["url"] for values in record["relationships"].values() for item in (values or [])}),
            "numeric_properties": record["numeric_properties"],
            "narrative_facts": [f"{key}: {value}" for key, value in record["narrative_facts"].items() if value is not None]
                + ["Acquisition content scope: " + record["content_scope"], "Detailed source record SHA-256: " + record["source_hash"]],
            "simulation_relevance": "not_active" if record["coverage_state"] == "SUPERSEDED" else "active",
            "coverage_state": record["coverage_state"], "provenance": record["provenance"]}
    return seal(body)


def census_diff(previous: Mapping, current: Mapping) -> dict:
    prev = {r["stable_source_id"]: r for r in previous.get("records", [])}
    curr = {r["stable_source_id"]: r for r in current["records"]}
    added, absent = sorted(curr.keys() - prev.keys()), sorted(prev.keys() - curr.keys())
    complete = {c["key"] for c in current["collections"] if c["enumeration_complete"]}
    removed = [key for key in absent if prev[key].get("collection") in complete]
    unresolved = [key for key in absent if key not in removed]
    changed = [key for key in sorted(prev.keys() & curr.keys()) if prev[key]["source_hash"] != curr[key]["source_hash"]]
    transitions = [{"source_id": key, "from": prev[key]["coverage_state"], "to": curr[key]["coverage_state"]}
                   for key in changed if prev[key]["coverage_state"] != curr[key]["coverage_state"]]
    body = {"schema": "tnp.economy.live-census-diff/1",
            "previous_snapshot_hash": previous.get("snapshot_hash"), "current_snapshot_hash": current["snapshot_hash"],
            "added": added, "removed": removed, "changed": changed,
            "unobserved_not_removed": unresolved, "coverage_transitions": transitions,
            "unchanged_count": len(prev.keys() & curr.keys()) - len(changed),
            "meaning": "Added means newly materialized in this census, not newly created in campaign time."}
    return seal(body, "diff_hash")


def assemble(directory: Path, control: Mapping) -> dict:
    """Reconstruct a census from actual bounded live-call receipts, fail closed."""
    records, collections = [], []
    expected = control["expected_collection_keys"]
    if len(set(expected)) != len(expected):
        raise AcquisitionError("duplicate collection scope")
    specs = {value["key"]: CollectionSpec.from_mapping(value) for value in control["specs"]}
    for key in expected:
        if key not in specs:
            collections.append({"key": key, "acquired_count": 0, "enumeration_complete": False,
                                "blockers": ["collection acquisition not started"]})
            continue
        spec = specs[key]
        paths = sorted(directory.glob(f"{key}.[0-9][0-9][0-9].json"))
        receipts = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
        for number, path in enumerate(paths):
            if path.name != f"{key}.{number:03d}.json":
                raise AcquisitionError("missing numbered acquisition batch")
        result = verify_enumeration(spec, receipts, control.get("enumeration_evidence", {}).get(key))
        source_records = [materialize(spec, row) for row in result.pop("rows")]
        records.extend(source_records)
        collections.append({"key": key, "data_source_url": spec.data_source_url,
                            "source_class": spec.source_class, "title": spec.title,
                            **result, "receipt_files": [path.name for path in paths],
                            "receipt_hashes": {path.name: digest(receipt) for path, receipt in zip(paths, receipts, strict=True)}})
    identities = [record["stable_source_id"] for record in records]
    if len(set(identities)) != len(identities):
        raise AcquisitionError("one source identity appears in multiple acquired collections")
    counts = dict(sorted(Counter(record["coverage_state"] for record in records).items()))
    body = {"schema": SCHEMA, "repository_base_sha": control["repository_base_sha"],
            "captured_at": control["captured_at"], "campaign_boundary": control["campaign_boundary"],
            "collections": collections, "records": sorted(records, key=lambda x: x["stable_source_id"]),
            "materialized_record_count": len(records), "coverage_state_counts": counts,
            "enumeration_complete": all(c["enumeration_complete"] for c in collections),
            "gate": "CLOSED", "notion_writes": 0, "campaign_time_advanced": False,
            "provenance": [{"choice": "Live enumeration; retain every source; no Notion write or simulation", "tag": "USER-RULED"},
                           {"choice": "Raw Notion properties", "tag": "SOURCE-DERIVED"},
                           {"choice": "Unassessed coverage remains UNKNOWN; no temporal inference from edit dates", "tag": "MODEL-PROPOSED"}],
            "limits": ["SQL text can lose native mention/link/format metadata.",
                       "Page-body acquisition is tracked separately; property enumeration does not claim full-page audit.",
                       "No source record is SIMULATED merely because it was acquired."]}
    return seal(body, "snapshot_hash")


def render_report(snapshot: Mapping, diff: Mapping) -> str:
    lines = ["# Live Empire Source Census — acquisition report", "",
             f"Boundary: {snapshot['campaign_boundary']}. No campaign-time advance.",
             f"Materialized hashed records: **{snapshot['materialized_record_count']}**. Coverage gate: **CLOSED**.",
             "", "| Collection | Hashed records | Enumeration complete | Blockers |", "|---|---:|---|---|"]
    for row in snapshot["collections"]:
        lines.append(f"| {row['key']} | {row['acquired_count']} | {row['enumeration_complete']} | {'; '.join(row['blockers'])} |")
    lines += ["", "## Coverage", "", json.dumps(snapshot["coverage_state_counts"], sort_keys=True), "",
              "## Census diff", "", f"Added {len(diff['added'])}; changed {len(diff['changed'])}; removed {len(diff['removed'])}; unchanged {diff['unchanged_count']}; unobserved/not removed {len(diff['unobserved_not_removed'])}.",
              diff["meaning"], "", "## Acquisition limits", ""]
    lines.extend("- " + limit for limit in snapshot["limits"])
    lines += ["", "## Per-record coverage", "", "| Source | Title | Class | State |", "|---|---|---|---|"]
    for record in snapshot["records"]:
        title = record["title"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {record['stable_source_id']} | [{title}]({record['source_url']}) | {record['source_class']} | {record['coverage_state']} |")
    return "\n".join(lines) + "\n"
