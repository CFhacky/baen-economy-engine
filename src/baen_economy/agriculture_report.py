"""Self-contained, source-labelled agriculture planning workbench."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from html import escape
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence


def _text(value: object) -> str:
    """Render missing values explicitly rather than turning them into zero."""

    if value is None:
        return "UNKNOWN"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _number(value: object) -> str:
    if value is None:
        return "UNKNOWN"
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return str(value)
    if number == number.to_integral_value():
        return f"{number:,.0f}"
    return f"{number:,.4f}".rstrip("0").rstrip(".")


def _money(value: object) -> str:
    return "UNKNOWN" if value is None else f"{_number(value)} gp"


def _range(value: object, suffix: str = "") -> str:
    if not isinstance(value, Mapping):
        return "UNKNOWN"
    low = value.get("low")
    high = value.get("high")
    if low is None or high is None:
        return "UNKNOWN"
    rendered = _number(low) if str(low) == str(high) else f"{_number(low)}–{_number(high)}"
    return rendered + suffix


def _percent_range(value: object) -> str:
    if not isinstance(value, Mapping):
        return "UNKNOWN"
    try:
        low = Decimal(str(value["low"])) * 100
        high = Decimal(str(value["high"])) * 100
    except (InvalidOperation, KeyError):
        return "UNKNOWN"
    rendered = _number(low) if low == high else f"{_number(low)}–{_number(high)}"
    return rendered + "%"


def _plain_value(value: object) -> str:
    """Turn nested fixture values into readable text without hiding subfields."""

    if isinstance(value, Mapping):
        if "low" in value and "high" in value:
            return _range(value)
        return "; ".join(
            f"{str(key).replace('_', ' ')}: {_plain_value(child)}"
            for key, child in value.items()
        ) or "UNKNOWN"
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return "; ".join(_plain_value(item) for item in value) or "UNKNOWN"
    return _text(value)


def _source_map(payload: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    sources = payload.get("sources", [])
    if not isinstance(sources, Sequence):
        return {}
    return {
        str(source.get("source_id")): source
        for source in sources
        if isinstance(source, Mapping) and source.get("source_id")
    }


def _source_links(
    source_ids: object,
    sources: Mapping[str, Mapping[str, object]],
) -> str:
    if isinstance(source_ids, str):
        identifiers: Iterable[object] = (source_ids,)
    elif isinstance(source_ids, Sequence):
        identifiers = source_ids
    else:
        identifiers = ()
    links: list[str] = []
    for identifier in identifiers:
        source_id = str(identifier)
        source = sources.get(source_id)
        if source is None:
            links.append(f"<span>{escape(source_id)}</span>")
            continue
        title = escape(str(source.get("title", source_id)))
        url = escape(str(source.get("url", "")), quote=True)
        authority = escape(str(source.get("authority_class", "unknown")).replace("_", " "))
        links.append(
            f'<a href="{url}" target="_blank" rel="noreferrer">{title}</a>'
            f'<span class="source-class">{authority}</span>'
        )
    return "<br>".join(links) if links else "UNKNOWN"


def _cell(label: str, value: object, *, css_class: str = "") -> str:
    class_attribute = f' class="{escape(css_class, quote=True)}"' if css_class else ""
    return (
        f'<td data-label="{escape(label, quote=True)}"{class_attribute}>'
        f"{value}</td>"
    )


def _fact_list(values: Mapping[str, object]) -> str:
    rows: list[str] = []
    for key, value in values.items():
        if key in {"source_id", "source_ids", "temporal_class"}:
            continue
        label = key.replace("_", " ").capitalize()
        rendered = _plain_value(value)
        rows.append(
            f"<dt>{escape(label)}</dt><dd>{escape(rendered)}</dd>"
        )
    return "".join(rows)


def render_agriculture_workbench_html(payload: Mapping[str, object]) -> str:
    """Render a dependency-free workbench with source truth and sandbox maths."""

    sources = _source_map(payload)
    current = payload.get("current_actual_state", {})
    forward = payload.get("forward_k1495_state", {})
    confirmed = payload.get("confirmed_production", {})
    registry = payload.get("registry_entities", [])
    species = payload.get("species", [])
    crop_program = payload.get("crop_program", {})
    crops = crop_program.get("crops", []) if isinstance(crop_program, Mapping) else []
    conflicts = payload.get("known_conflicts", [])
    blockers = payload.get("unresolved_inputs", [])
    topology = payload.get("nmwc_topology", {})
    pond_groups = payload.get("nmwc_pond_groups", [])
    safety = payload.get("safety", {})
    dated_systems = payload.get("dated_agricultural_systems", [])
    logistics = payload.get("logistics_reference", {})
    faction_beliefs = payload.get("faction_beliefs_cross_reference", {})

    if not isinstance(current, Mapping):
        current = {}
    if not isinstance(forward, Mapping):
        forward = {}
    if not isinstance(confirmed, Mapping):
        confirmed = {}
    if not isinstance(registry, Sequence):
        registry = []
    if not isinstance(species, Sequence):
        species = []
    if not isinstance(crops, Sequence):
        crops = []
    if not isinstance(conflicts, Sequence):
        conflicts = []
    if not isinstance(blockers, Sequence):
        blockers = []
    if not isinstance(topology, Mapping):
        topology = {}
    if not isinstance(pond_groups, Sequence):
        pond_groups = []
    if not isinstance(safety, Mapping):
        safety = {}
    if not isinstance(dated_systems, Sequence):
        dated_systems = []
    if not isinstance(logistics, Mapping):
        logistics = {}
    if not isinstance(faction_beliefs, Mapping):
        faction_beliefs = {}

    business_rows: list[str] = []
    for entity in registry:
        if not isinstance(entity, Mapping):
            continue
        revenue = entity.get("monthly_revenue_gp")
        cost = entity.get("monthly_cost_gp")
        net: object = None
        if revenue is not None and cost is not None:
            try:
                net = Decimal(str(revenue)) - Decimal(str(cost))
            except InvalidOperation:
                net = None
        business_rows.append(
            "<tr>"
            + _cell("Business / record", f"<strong>{escape(_text(entity.get('name')))}</strong>")
            + _cell("Sector", escape(_text(entity.get("sector"))))
            + _cell("Status", escape(_text(entity.get("status"))))
            + _cell("As of", escape(_text(entity.get("as_of"))), css_class="nowrap")
            + _cell("Staff", escape(_number(entity.get("employees"))), css_class="number")
            + _cell(
                "Reported finance / month",
                f"Revenue {_money(entity.get('monthly_revenue_gp'))}<br>"
                f"Cost {_money(entity.get('monthly_cost_gp'))}<br>"
                f"Arithmetic net {_money(net)}",
                css_class="number",
            )
            + _cell("Capital", escape(_money(entity.get("capital_invested_gp"))), css_class="number")
            + _cell("Source", _source_links(entity.get("source_id"), sources))
            + "</tr>"
        )

    observed_cards: list[str] = []
    for operation_id, operation in confirmed.items():
        if not isinstance(operation, Mapping):
            continue
        temporal = str(operation.get("temporal_class", ""))
        if temporal.startswith("later_") or operation_id in {
            "orchard_chapel_1498",
            "lobster_king_later_authority",
        }:
            continue
        source_ids = operation.get("source_ids", operation.get("source_id"))
        linked_outputs = operation.get("linked_confirmed_outputs", [])
        if isinstance(linked_outputs, Sequence) and not isinstance(
            linked_outputs, (str, bytes)
        ):
            linked_source_ids = [
                item.get("source_id")
                for item in linked_outputs
                if isinstance(item, Mapping) and item.get("source_id")
            ]
            if linked_source_ids:
                base_ids = [source_ids] if isinstance(source_ids, str) else list(source_ids or [])
                source_ids = base_ids + linked_source_ids
        observed_cards.append(
            '<article class="record">'
            f"<h3>{escape(operation_id.replace('_', ' ').title())}</h3>"
            f'<dl class="facts">{_fact_list(operation)}</dl>'
            f'<p class="sources"><strong>Source:</strong><br>{_source_links(source_ids, sources)}</p>'
            "</article>"
        )

    dated_system_cards: list[str] = []
    for system in dated_systems:
        if not isinstance(system, Mapping):
            continue
        source_ids = system.get("source_ids", system.get("source_id"))
        dated_system_cards.append(
            '<article class="record later-record">'
            f'<p class="status-label">{escape(_text(system.get("temporal_class")).replace("_", " "))}</p>'
            f'<h3>{escape(_text(system.get("name")))}</h3>'
            f'<dl class="facts">{_fact_list(system)}</dl>'
            f'<p class="sources"><strong>Source:</strong><br>{_source_links(source_ids, sources)}</p>'
            "</article>"
        )

    road_rows: list[str] = []
    road_distances = logistics.get("arterial_road_distances_miles", [])
    if isinstance(road_distances, Sequence):
        for route in road_distances:
            if not isinstance(route, Mapping):
                continue
            road_rows.append(
                "<tr>"
                + _cell("From", escape(_text(route.get("from"))))
                + _cell("To", escape(_text(route.get("to"))))
                + _cell("Distance", escape(f"{_number(route.get('distance'))} miles"), css_class="number")
                + _cell("Source", _source_links(logistics.get("road_source_id"), sources))
                + "</tr>"
            )

    logistics_cards: list[str] = []
    for logistics_id in ("hunding_canal", "neverwinter_ice_house"):
        reference = logistics.get(logistics_id)
        if not isinstance(reference, Mapping):
            continue
        logistics_cards.append(
            '<article class="record later-record">'
            f"<h3>{escape(logistics_id.replace('_', ' ').title())}</h3>"
            f'<dl class="facts">{_fact_list(reference)}</dl>'
            f'<p class="sources"><strong>Source:</strong><br>{_source_links(reference.get("source_id"), sources)}</p>'
            "</article>"
        )

    faction_threat = faction_beliefs.get("external_operational_threat", {})
    if not isinstance(faction_threat, Mapping):
        faction_threat = {}
    direct_contacts = faction_beliefs.get("direct_aquaculture_or_food_contact_points", [])
    direct_contact_text = (
        _plain_value(direct_contacts)
        if isinstance(direct_contacts, Sequence) and direct_contacts
        else "None returned by the live Active+ query"
    )

    later_cards: list[str] = []
    for operation_id, operation in confirmed.items():
        if not isinstance(operation, Mapping):
            continue
        temporal = str(operation.get("temporal_class", ""))
        if not temporal.startswith("later_") and operation_id not in {
            "orchard_chapel_1498",
            "lobster_king_later_authority",
        }:
            continue
        source_ids = operation.get("source_ids", operation.get("source_id"))
        later_cards.append(
            '<article class="record later-record">'
            f'<p class="status-label">{escape(temporal.replace("_", " "))}</p>'
            f"<h3>{escape(operation_id.replace('_', ' ').title())}</h3>"
            f'<dl class="facts">{_fact_list(operation)}</dl>'
            f'<p class="sources"><strong>Source:</strong><br>{_source_links(source_ids, sources)}</p>'
            "</article>"
        )

    species_rows: list[str] = []
    for item in species:
        if not isinstance(item, Mapping):
            continue
        density = item.get("stocking_density")
        density_text = _range(density)
        if isinstance(density, Mapping) and density.get("unit"):
            density_text += " " + str(density["unit"]).replace("_", " ")
        yield_value = item.get("annual_yield_lb_per_1000_unit")
        yield_text = _range(yield_value, " lb/year")
        if isinstance(yield_value, Mapping) and yield_value.get("basis"):
            yield_text += f" per 1,000 {yield_value['basis']}"
        species_rows.append(
            "<tr>"
            + _cell(
                "Species",
                f"<strong>{escape(_text(item.get('name')))}</strong><br>"
                f"<em>{escape(_text(item.get('scientific_name')))}</em>",
            )
            + _cell("Zone / role", f"{escape(_text(item.get('zone')))} / {escape(_text(item.get('role')))}")
            + _cell("Growth", escape(_range(item.get("growth_months"), " months")), css_class="number")
            + _cell("Stocking density", escape(density_text), css_class="number")
            + _cell("FCR", escape(_range(item.get("feed_conversion_ratio"))), css_class="number")
            + _cell("Market", escape(_range(item.get("market_gp_per_lb"), " gp/lb")), css_class="number")
            + _cell("Technical annual yield", escape(yield_text), css_class="number")
            + _cell("Source", _source_links(item.get("source_id"), sources))
            + "</tr>"
        )

    crop_rows: list[str] = []
    for item in crops:
        if not isinstance(item, Mapping):
            continue
        # The design appendix is the row-level authority for the crop catalogue.
        # Shelter evidence applies only to the confirmed tomato row; showing the
        # shelter page beside wheat/barley/rye would recreate the prior false
        # assignment the workbench exists to prevent.
        row_sources: object = (
            "shelters" if item.get("crop_id") == "tomatoes" else "aquaculture-technical"
        )
        crop_rows.append(
            "<tr>"
            + _cell("Crop", f"<strong>{escape(_text(item.get('name')))}</strong>")
            + _cell("Class", escape(_text(item.get("class")).replace("_", " ")))
            + _cell("Sourced yield uplift", escape(_percent_range(item.get("yield_increase"))), css_class="number")
            + _cell(
                "Confirmed planted",
                "Yes" if item.get("confirmed_planted") is True else "No — technical catalogue only",
            )
            + _cell("Source", _source_links(row_sources, sources))
            + "</tr>"
        )

    pond_rows: list[str] = []
    for group in pond_groups:
        if not isinstance(group, Mapping):
            continue
        pond_rows.append(
            "<tr>"
            + _cell("Group", f"<strong>{escape(_text(group.get('group_id')).title())}</strong>")
            + _cell("Ponds", escape(_number(group.get("ponds"))), css_class="number")
            + _cell(
                "Temperature",
                escape(f"{_number(group.get('temperature_f_low'))}–{_number(group.get('temperature_f_high'))} °F"),
                css_class="number",
            )
            + _cell("Species labels", escape(", ".join(str(value) for value in group.get("species_labels", []))))
            + _cell("Technical annual yield", escape(f"{_number(group.get('annual_yield_lb'))} lb/year"), css_class="number")
            + _cell("Source", _source_links(group.get("source_id"), sources))
            + "</tr>"
        )

    conflict_cards: list[str] = []
    for conflict in conflicts:
        if not isinstance(conflict, Mapping):
            continue
        blocking_for = conflict.get("blocking_for", [])
        rendered_blocks = ", ".join(str(item).replace("_", " ") for item in blocking_for)
        conflict_cards.append(
            '<article class="conflict">'
            f"<h3>{escape(_text(conflict.get('conflict_id')).replace('_', ' ').title())}</h3>"
            f"<p>{escape(_text(conflict.get('description')))}</p>"
            f'<p class="blocked-by"><strong>Blocks:</strong> {escape(rendered_blocks)}</p>'
            "</article>"
        )

    source_rows: list[str] = []
    for source in payload.get("sources", []):
        if not isinstance(source, Mapping):
            continue
        source_rows.append(
            "<tr>"
            + _cell("Source", _source_links(source.get("source_id"), sources))
            + _cell("Authority", escape(_text(source.get("authority_class")).replace("_", " ")))
            + _cell("Page ID", f"<code>{escape(_text(source.get('page_id')))}</code>")
            + "</tr>"
        )

    blocker_items = "".join(f"<li>{escape(_text(item))}</li>" for item in blockers)
    forward_sources = _source_links(forward.get("source_ids", forward.get("source_id")), sources)
    current_source = _source_links(current.get("source_id"), sources)
    technical_sources = _source_links(topology.get("source_ids"), sources)
    grain_target = _range(forward.get("grain_procurement_target_tons"), " tons")
    meat_budget = _range(forward.get("meat_and_livestock_budget_gp"), " gp")
    grain_budget = _range(forward.get("grain_budget_with_transport_gp"), " gp")
    species_for_script = [item for item in species if isinstance(item, Mapping)]
    crops_for_script = [item for item in crops if isinstance(item, Mapping)]
    calculator_json = json.dumps(
        {"species": species_for_script, "crops": crops_for_script},
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")

    css = r"""
    :root {
      color-scheme: dark;
      --bg: #0d1211; --surface: #151d1a; --surface-2: #1b2721;
      --ink: #f2f0e8; --muted: #b5c0b8; --line: #3b4a41;
      --gold: #e3bc68; --green: #80cf9d; --red: #ff9289; --blue: #93c9ee;
      --focus: #ffd982;
    }
    * { box-sizing: border-box; }
    html { background: var(--bg); }
    body { margin: 0; min-width: 0; overflow-x: hidden; color: var(--ink);
      background: radial-gradient(circle at 80% -10%, #25372a 0, transparent 38%), var(--bg);
      font: 16px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }
    a { color: var(--blue); overflow-wrap: anywhere; }
    button, input, select { font: inherit; }
    button, input, select { min-height: 42px; }
    button:focus-visible, input:focus-visible, select:focus-visible, a:focus-visible {
      outline: 3px solid var(--focus); outline-offset: 2px; }
    main { width: min(1400px, 100%); margin: 0 auto; padding: clamp(18px, 4vw, 44px); }
    h1, h2, h3 { line-height: 1.18; }
    h1 { margin: .2rem 0 .6rem; font-size: clamp(2rem, 5vw, 4rem); }
    h2 { margin: 2.2rem 0 .8rem; color: var(--gold); font-size: clamp(1.4rem, 3vw, 2rem); }
    h3 { margin: 0 0 .55rem; }
    p { max-width: 82ch; }
    .eyebrow { color: var(--gold); text-transform: uppercase; letter-spacing: .12em; font-weight: 700; }
    .lede { color: var(--muted); font-size: 1.05rem; }
    .freeze { margin: 1.4rem 0; padding: clamp(18px, 3vw, 30px); border: 2px solid var(--green);
      background: #10231a; border-radius: 12px; }
    .freeze strong { display: block; color: var(--green); font-size: clamp(1.35rem, 3vw, 2rem); }
    .freeze p { margin: .4rem 0 0; }
    .status-strip { display: flex; gap: .6rem 1.2rem; flex-wrap: wrap; padding: .8rem 0;
      color: var(--muted); border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
    .status-strip strong { color: var(--ink); }
    .tabs { display: flex; flex-wrap: wrap; gap: .5rem; margin: 1.5rem 0; }
    .tab { border: 1px solid var(--line); border-radius: 8px; padding: .65rem .9rem;
      color: var(--ink); background: var(--surface); cursor: pointer; }
    .tab[aria-selected="true"] { color: #111; background: var(--gold); border-color: var(--gold); }
    [role="tabpanel"][hidden] { display: none; }
    .notice { border-left: 5px solid var(--gold); padding: .8rem 1rem; background: #262114; }
    .danger { border-left-color: var(--red); background: #2a1717; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(300px, 100%), 1fr)); gap: 1rem; }
    .record, .calculator, .conflict, .metric { min-width: 0; padding: 1rem;
      border: 1px solid var(--line); border-radius: 10px; background: var(--surface); }
    .later-record { border-color: #6a5a33; }
    .status-label, .source-class { color: var(--gold); text-transform: uppercase;
      letter-spacing: .06em; font-size: .78rem; }
    .source-class { display: inline-block; margin-left: .35rem; color: var(--muted); }
    .sources { color: var(--muted); font-size: .9rem; }
    .facts { display: grid; grid-template-columns: minmax(130px, .8fr) minmax(0, 1.2fr); gap: .35rem 1rem; }
    .facts dt { color: var(--muted); }
    .facts dd { margin: 0; overflow-wrap: anywhere; }
    .metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(185px, 100%), 1fr)); gap: .8rem; }
    .metric strong { display: block; color: var(--blue); font-size: 1.45rem; overflow-wrap: anywhere; }
    .metric span { color: var(--muted); }
    .table-wrap { max-width: 100%; overflow-x: auto; border: 1px solid var(--line); border-radius: 10px; }
    table { width: 100%; border-collapse: collapse; background: var(--surface); }
    th, td { padding: .75rem; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; overflow-wrap: anywhere; }
    th { color: var(--gold); background: var(--surface-2); }
    tr:last-child td { border-bottom: 0; }
    .number { font-variant-numeric: tabular-nums; }
    .nowrap { white-space: nowrap; }
    .conflict { border-left: 5px solid var(--red); }
    .blocked-by { color: var(--red); }
    .blockers { columns: 2 340px; padding-left: 1.25rem; }
    .blockers li { break-inside: avoid; margin-bottom: .45rem; }
    .calculator-label { color: var(--gold); font-weight: 700; letter-spacing: .04em; }
    .calculator .fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(205px, 100%), 1fr)); gap: .8rem; }
    label { display: grid; gap: .3rem; color: var(--muted); }
    input, select { width: 100%; min-width: 0; padding: .55rem .65rem; color: var(--ink);
      background: #0e1512; border: 1px solid #607066; border-radius: 6px; }
    .action { margin-top: 1rem; padding: .65rem 1rem; color: #111; background: var(--gold);
      border: 0; border-radius: 7px; cursor: pointer; font-weight: 700; }
    .result { margin-top: 1rem; padding: .9rem; background: #0f1a15; border-left: 4px solid var(--green); }
    .result[role="alert"] { border-left-color: var(--red); }
    .formula { color: var(--muted); font-size: .88rem; }
    code { color: var(--green); overflow-wrap: anywhere; }
    details { margin-top: 1.5rem; }
    summary { color: var(--gold); cursor: pointer; font-weight: 700; min-height: 42px; }
    footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid var(--line); color: var(--muted); }
    @media (max-width: 760px) {
      main { padding: 18px 14px 40px; }
      .tabs { display: grid; grid-template-columns: 1fr 1fr; }
      .tab { width: 100%; }
      .table-wrap { overflow: visible; border: 0; }
      table, tbody, tr, td { display: block; width: 100%; }
      thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
      tr { margin-bottom: .8rem; border: 1px solid var(--line); border-radius: 8px; background: var(--surface); }
      td { display: grid; grid-template-columns: minmax(105px, .72fr) minmax(0, 1.28fr); gap: .65rem;
        padding: .65rem; border-bottom: 1px solid var(--line); }
      td::before { content: attr(data-label); color: var(--gold); font-weight: 700; }
      .nowrap { white-space: normal; }
      .facts { grid-template-columns: 1fr; }
      .facts dd { margin-bottom: .5rem; }
    }
    @media (max-width: 420px) {
      .tabs { grid-template-columns: 1fr; }
      td { grid-template-columns: 1fr; gap: .2rem; }
    }
    @media print {
      :root { color-scheme: light; --bg:#fff; --surface:#fff; --surface-2:#f2efe7; --ink:#111;
        --muted:#444; --line:#aaa; --gold:#654b10; --green:#155d34; --red:#8b1e19; --blue:#164f73; }
      body { background: #fff; }
      .tabs, .calculator { display: none; }
      [role="tabpanel"][hidden] { display: block; }
      a { color: #164f73; }
    }
    """

    javascript = r"""
    (() => {
      "use strict";
      const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
      function selectTab(tab) {
        tabs.forEach((candidate) => {
          const selected = candidate === tab;
          candidate.setAttribute('aria-selected', String(selected));
          document.getElementById(candidate.getAttribute('aria-controls')).hidden = !selected;
        });
        tab.focus();
      }
      tabs.forEach((tab, index) => {
        tab.addEventListener('click', () => selectTab(tab));
        tab.addEventListener('keydown', (event) => {
          if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
          event.preventDefault();
          let next = index;
          if (event.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length;
          if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
          if (event.key === 'Home') next = 0;
          if (event.key === 'End') next = tabs.length - 1;
          selectTab(tabs[next]);
        });
      });

      const data = JSON.parse(document.getElementById('calculator-data').textContent);
      const number = (value) => Number(value);
      const format = (value, digits = 2) => Number(value).toLocaleString(undefined, {
        maximumFractionDigits: digits
      });
      const range = (value) => value ? `${value.low}${value.low === value.high ? '' : `–${value.high}`}` : 'UNKNOWN';
      const validNonnegative = (input) => input.value.trim() !== '' &&
        Number.isFinite(number(input.value)) && number(input.value) >= 0;

      const speciesSelect = document.getElementById('aqua-species');
      data.species.forEach((species) => {
        const option = document.createElement('option');
        option.value = species.species_id;
        option.textContent = `${species.name} — ${species.zone}`;
        speciesSelect.append(option);
      });
      function updateAquaBasis() {
        const species = data.species.find((item) => item.species_id === speciesSelect.value);
        const basis = species && species.annual_yield_lb_per_1000_unit
          ? species.annual_yield_lb_per_1000_unit.basis : 'sourced yield basis';
        document.getElementById('aqua-basis').textContent = basis.replaceAll('_', ' ');
      }
      speciesSelect.addEventListener('change', updateAquaBasis);
      updateAquaBasis();
      document.getElementById('aqua-calculate').addEventListener('click', () => {
        const result = document.getElementById('aqua-result');
        const capacity = document.getElementById('aqua-capacity');
        const utilization = document.getElementById('aqua-utilization');
        if (!validNonnegative(capacity) || !validNonnegative(utilization) || number(utilization.value) > 100) {
          result.setAttribute('role', 'alert');
          result.textContent = 'Enter non-negative capacity and utilization from 0 to 100%.';
          return;
        }
        result.setAttribute('role', 'status');
        const species = data.species.find((item) => item.species_id === speciesSelect.value);
        const sourcedYield = species.annual_yield_lb_per_1000_unit;
        if (!sourcedYield) {
          result.innerHTML = `<strong>No sourced annual yield for ${species.name}.</strong><br>` +
            'Capacity can be entered, but this fixture does not authorize an output estimate.';
          return;
        }
        const factor = number(capacity.value) / 1000 * number(utilization.value) / 100;
        const outputLow = number(sourcedYield.low) * factor;
        const outputHigh = number(sourcedYield.high) * factor;
        let feed = 'UNKNOWN — no sourced FCR';
        if (species.feed_conversion_ratio) {
          const feedLow = outputLow * number(species.feed_conversion_ratio.low);
          const feedHigh = outputHigh * number(species.feed_conversion_ratio.high);
          feed = `${format(feedLow)}–${format(feedHigh)} lb/year`;
        }
        const price = species.market_gp_per_lb;
        const revenue = price
          ? `${format(outputLow * number(price.low))}–${format(outputHigh * number(price.high))} gp/year`
          : 'UNKNOWN';
        result.innerHTML = `<strong>${species.name}: ${format(outputLow)}–${format(outputHigh)} lb/year</strong><br>` +
          `Feed requirement: ${feed}<br>Gross price envelope: ${revenue}<br>` +
          `<span class="formula">Sourced inputs: yield ${range(sourcedYield)} lb/year per 1,000 ` +
          `${sourcedYield.basis.replaceAll('_', ' ')}; FCR ${range(species.feed_conversion_ratio)}; ` +
          `market ${range(price)} gp/lb. Capacity and utilization are USER ASSUMPTIONS.</span>`;
      });

      const cropSelect = document.getElementById('crop-name');
      data.crops.forEach((crop) => {
        const option = document.createElement('option');
        option.value = crop.crop_id;
        option.textContent = crop.name;
        cropSelect.append(option);
      });
      document.getElementById('crop-calculate').addEventListener('click', () => {
        const result = document.getElementById('crop-result');
        const baseline = document.getElementById('crop-baseline');
        if (!validNonnegative(baseline)) {
          result.setAttribute('role', 'alert');
          result.textContent = 'Enter a non-negative baseline yield.';
          return;
        }
        result.setAttribute('role', 'status');
        const crop = data.crops.find((item) => item.crop_id === cropSelect.value);
        const unit = document.getElementById('crop-unit').value;
        if (!crop.yield_increase) {
          result.innerHTML = `<strong>No crop-specific uplift is sourced for ${crop.name}.</strong><br>` +
            'The baseline remains a user assumption and no enhanced result is calculated.';
          return;
        }
        const base = number(baseline.value);
        const low = base * (1 + number(crop.yield_increase.low));
        const high = base * (1 + number(crop.yield_increase.high));
        result.innerHTML = `<strong>${format(low)}–${format(high)} ${unit}</strong><br>` +
          `Increment: ${format(low - base)}–${format(high - base)} ${unit}<br>` +
          `<span class="formula">Sourced technical uplift: ${format(number(crop.yield_increase.low) * 100)}–` +
          `${format(number(crop.yield_increase.high) * 100)}%. Baseline yield and unit are USER ASSUMPTIONS.</span>`;
      });

      document.getElementById('inventory-calculate').addEventListener('click', () => {
        const result = document.getElementById('inventory-result');
        const inputs = ['inventory-opening', 'inventory-production', 'inventory-receipts',
          'inventory-demand', 'inventory-loss', 'inventory-months'].map((id) => document.getElementById(id));
        if (inputs.some((input) => !validNonnegative(input)) || number(inputs[4].value) > 100 ||
            number(inputs[5].value) < 1 || number(inputs[5].value) > 24) {
          result.setAttribute('role', 'alert');
          result.textContent = 'Use non-negative values, loss from 0 to 100%, and 1–24 months.';
          return;
        }
        result.setAttribute('role', 'status');
        let opening = number(inputs[0].value);
        const production = number(inputs[1].value);
        const receipts = number(inputs[2].value);
        const demand = number(inputs[3].value);
        const lossRate = number(inputs[4].value) / 100;
        const months = Math.floor(number(inputs[5].value));
        const unit = document.getElementById('inventory-unit').value;
        const rows = [];
        let totalUnmet = 0;
        for (let month = 1; month <= months; month += 1) {
          const beforeLoss = opening + production + receipts;
          const loss = beforeLoss * lossRate;
          const usable = Math.max(0, beforeLoss - loss);
          const consumed = Math.min(usable, demand);
          const unmet = Math.max(0, demand - usable);
          const closing = Math.max(0, usable - demand);
          totalUnmet += unmet;
          rows.push(`<tr><td data-label="Month">${month}</td><td data-label="Opening">${format(opening)}</td>` +
            `<td data-label="Production">${format(production)}</td><td data-label="Receipts">${format(receipts)}</td>` +
            `<td data-label="Loss">${format(loss)}</td><td data-label="Consumed">${format(consumed)}</td>` +
            `<td data-label="Unmet">${format(unmet)}</td><td data-label="Closing">${format(closing)}</td></tr>`);
          opening = closing;
        }
        result.innerHTML = `<strong>Closing after month ${months}: ${format(opening)} ${unit}; ` +
          `total unmet demand: ${format(totalUnmet)} ${unit}</strong>` +
          `<div class="table-wrap"><table><thead><tr><th>Month</th><th>Opening</th><th>Production</th>` +
          `<th>Receipts</th><th>Loss</th><th>Consumed</th><th>Unmet</th><th>Closing</th></tr></thead>` +
          `<tbody>${rows.join('')}</tbody></table></div>` +
          `<p class="formula">Every value in this inventory preview is a USER ASSUMPTION. ` +
          `Formula: closing = max(0, opening + production + receipts − loss − demand). No campaign state is changed.</p>`;
      });
    })();
    """

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="Source-labelled Baen agriculture workbench with non-canon planning previews">
<title>Baen Agriculture Workbench</title>
<style>{css}</style>
</head>
<body>
<main>
  <header>
    <p class="eyebrow">Read-only agriculture engine · source-grounded</p>
    <h1>Baen Agriculture Workbench</h1>
    <p class="lede">Your agriculture and aquaculture records are present here—including every named species and crop. Dates and authority classes stay separate.</p>
    <div class="freeze">
      <strong>CURRENT ACTUAL: {escape(_text(current.get('campaign_date')))}</strong>
      <p>LIVE FREEZE · NO CAMPAIGN ADVANCE · NO AGRICULTURE MONTH CLOSE</p>
      <p>This workbench does not move the clock, roll dice, post a ledger entry, or write to Notion.</p>
      <p class="sources">Authority: {current_source}</p>
    </div>
    <div class="status-strip" aria-label="Safety state">
      <span>Notion writes <strong>{escape(_number(safety.get('notion_writes')))}</strong></span>
      <span>Canonical ledger postings <strong>{escape(_number(safety.get('canonical_ledger_postings')))}</strong></span>
      <span>Dice rolled <strong>{escape(_number(safety.get('dice_rolled')))}</strong></span>
      <span>Campaign time advanced <strong>{escape(_text(safety.get('campaign_time_advanced')))}</strong></span>
    </div>
    <div class="metrics" aria-label="Source coverage">
      <div class="metric"><strong>{len(sources)}</strong><span>linked Notion authorities</span></div>
      <div class="metric"><strong>{len(species_for_script)}</strong><span>named aquaculture species</span></div>
      <div class="metric"><strong>{len(crops_for_script)}</strong><span>named crop entries</span></div>
      <div class="metric"><strong>{len(dated_system_cards)}</strong><span>larger dated food systems</span></div>
    </div>
    <p class="notice"><strong>Runnable now:</strong> open <em>Technical Design</em> for aquaculture yield/feed, crop-uplift, and multi-month inventory previews. Assumption fields begin empty; the workbench will not substitute zero for missing data.</p>
  </header>

  <nav class="tabs" role="tablist" aria-label="Agriculture authority layers">
    <button class="tab" id="tab-current" type="button" role="tab" aria-selected="true" aria-controls="panel-current">Current Actual</button>
    <button class="tab" id="tab-forward" type="button" role="tab" aria-selected="false" aria-controls="panel-forward">Forward Kythorn 1495</button>
    <button class="tab" id="tab-later" type="button" role="tab" aria-selected="false" aria-controls="panel-later">Later References</button>
    <button class="tab" id="tab-technical" type="button" role="tab" aria-selected="false" aria-controls="panel-technical">Technical Design</button>
  </nav>

  <section id="panel-current" role="tabpanel" aria-labelledby="tab-current">
    <p class="notice"><strong>Current actual is frozen.</strong> The business figures below retain their own “as of” dates. They are not opening cash, physical stock, or an automatic Day 7 Hammer month.</p>
    <h2>Business and allied registry records</h2>
    <p>Status and ownership wording is preserved: an unconfirmed allied record is not silently treated as an owned operating business.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>Business / record</th><th>Sector</th><th>Status</th><th>As of</th><th>Staff</th><th>Reported finance / month</th><th>Capital</th><th>Source</th></tr></thead>
      <tbody>{''.join(business_rows)}</tbody>
    </table></div>

    <h2>Observed production facts</h2>
    <p class="notice">These are source facts, not a claim that current Hammer output quantities are known. Missing quantities remain <strong>UNKNOWN</strong>, never zero.</p>
    <div class="grid">{''.join(observed_cards)}</div>

    <h2>Faction Beliefs cross-reference</h2>
    <div class="record">
      <dl class="facts">
        <dt>Live query completed</dt><dd>{escape(_text(faction_beliefs.get('queried_live')))}</dd>
        <dt>Query scope</dt><dd>{escape(_text(faction_beliefs.get('query_scope')))}</dd>
        <dt>Direct food / aquaculture contact points</dt><dd>{escape(direct_contact_text)}</dd>
        <dt>Representation gap</dt><dd>{escape(_text(faction_beliefs.get('representation_gap')))}</dd>
        <dt>External operational threat</dt><dd>{escape(_text(faction_threat.get('description')))}</dd>
        <dt>Threat source</dt><dd>{_source_links(faction_threat.get('source_id'), sources)}</dd>
      </dl>
      <p class="notice danger">The Iron Sovereignty reference is threat context. It is not converted into an invented production loss.</p>
    </div>

    <h2>Blocked current inputs</h2>
    <p>A canonical physical month cannot close until these values are sourced or explicitly ruled. The planning tools in Technical Design do not fill them in.</p>
    <ul class="blockers">{blocker_items}</ul>

    <h2>Contradictions kept visible</h2>
    <div class="grid">{''.join(conflict_cards)}</div>
  </section>

  <section id="panel-forward" role="tabpanel" aria-labelledby="tab-forward" hidden>
    <p class="notice"><strong>RATIFIED FORWARD SCENARIO — NOT CURRENT ACTUAL.</strong> Nothing here is backdated into Hammer 1495 or posted as a completed transaction.</p>
    <div class="metrics">
      <div class="metric"><strong>{escape(_text(forward.get('campaign_date')))}</strong><span>scenario date</span></div>
      <div class="metric"><strong>{escape(_number(forward.get('shelter_zones_destroyed')))} / {escape(_number(forward.get('shelter_zones_total')))}</strong><span>shelter zones destroyed</span></div>
      <div class="metric"><strong>{escape(_number(forward.get('longsaddle_population')))}</strong><span>Longsaddle population / mouths</span></div>
      <div class="metric"><strong>{escape(grain_target)}</strong><span>grain procurement target</span></div>
      <div class="metric"><strong>{escape(_number(forward.get('grain_procured_tons')))} tons</strong><span>grain actually procured in this unresolved scenario</span></div>
      <div class="metric"><strong>{escape(_text(forward.get('longsaddle_k1495_harvestable_output')))}</strong><span>Kythorn harvestable output</span></div>
    </div>
    <h2>Forward conditions</h2>
    <dl class="facts">
      <dt>Longsaddle food position</dt><dd>{escape(_text(forward.get('longsaddle_food_position')))}</dd>
      <dt>First full planting</dt><dd>{escape(_text(forward.get('longsaddle_first_full_planting')))}</dd>
      <dt>First harvest window</dt><dd>{escape(_text(forward.get('longsaddle_first_harvest_window')))}</dd>
      <dt>First harvest outcome</dt><dd>{escape(_text(forward.get('longsaddle_first_harvest_outcome')))}</dd>
      <dt>First meaningful export surplus</dt><dd>{escape(_text(forward.get('first_meaningful_export_surplus')))}</dd>
      <dt>Meat self-sufficiency</dt><dd>{escape(_text(forward.get('meat_self_sufficiency')))}</dd>
      <dt>Meat export</dt><dd>{escape(_text(forward.get('meat_export')))}</dd>
      <dt>Meat and livestock budget</dt><dd>{escape(meat_budget)}</dd>
      <dt>Grain budget with transport</dt><dd>{escape(grain_budget)}</dd>
      <dt>Execution rolls resolved</dt><dd>{escape(_number(forward.get('execution_rolls_resolved')))}</dd>
      <dt>Transactions resolved</dt><dd>{escape(_number(forward.get('transactions_resolved')))}</dd>
      <dt>Authority</dt><dd>{forward_sources}</dd>
    </dl>
    <p class="notice danger">Five shelter zones are “not reported destroyed,” not confirmed operational. Their capacity cannot be scaled as five-eighths without a ruling.</p>
  </section>

  <section id="panel-later" role="tabpanel" aria-labelledby="tab-later" hidden>
    <p class="notice"><strong>LATER-DATED OR UNDATED DETAILED REFERENCES.</strong> These facts remain available without being inserted into Day 7 Hammer 1495.</p>
    <div class="grid">{''.join(later_cards) if later_cards else '<p>No later operation records are present in this fixture.</p>'}</div>
    <h2>Dated agricultural systems</h2>
    <p>These four systems preserve their own dates, doctrine status, and unresolved claims. None is eligible to execute as Day 7 Hammer opening state.</p>
    <div class="grid">{''.join(dated_system_cards) if dated_system_cards else '<p>No dated system references are present in this fixture.</p>'}</div>

    <h2>Food-logistics capabilities</h2>
    <p class="notice">Capabilities are not allocated shipments. Canal, ice-house, and road facts do not create food inventory or reserve transport capacity.</p>
    <div class="grid">{''.join(logistics_cards)}</div>
    <div class="table-wrap"><table>
      <thead><tr><th>From</th><th>To</th><th>Distance</th><th>Source</th></tr></thead>
      <tbody>{''.join(road_rows)}</tbody>
    </table></div>
    <h2>Why this layer exists</h2>
    <p>Orchard Chapel’s 1498 record and the Lobster King’s richer authority are useful, but their effective dates do not authorize backdating. The Registry’s older unconfirmed Lobster King row remains visible in Current Actual so the conflict is not erased.</p>
  </section>

  <section id="panel-technical" role="tabpanel" aria-labelledby="tab-technical" hidden>
    <p class="notice"><strong>TECHNICAL DESIGN — NOT CANON EXECUTION.</strong> Catalogue values support transparent “what-if” planning. They do not prove that a species is stocked, a crop is planted, or a pond exists at the current freeze.</p>
    <h2>NMWC technical capacity lane</h2>
    <div class="metrics">
      <div class="metric"><strong>{escape(_number(topology.get('ponds')))}</strong><span>designed ponds</span></div>
      <div class="metric"><strong>{escape(_number(topology.get('capacity_each_cubic_meters')))} m³</strong><span>capacity per pond</span></div>
      <div class="metric"><strong>{escape(_number(topology.get('total_capacity_cubic_meters')))} m³</strong><span>total designed capacity</span></div>
      <div class="metric"><strong>{escape(_number(topology.get('total_annual_yield_lb')))} lb/year</strong><span>grouped technical yield</span></div>
    </div>
    <p class="sources">Technical sources: {technical_sources}</p>
    <div class="table-wrap"><table>
      <thead><tr><th>Group</th><th>Ponds</th><th>Temperature</th><th>Species labels</th><th>Technical annual yield</th><th>Source</th></tr></thead>
      <tbody>{''.join(pond_rows)}</tbody>
    </table></div>

    <h2>Planning calculators</h2>
    <p>Every result remains in the browser. It is not saved to the fixture, Notion, campaign state, or a ledger.</p>
    <div class="grid">
      <section class="calculator" aria-labelledby="aqua-heading">
        <p class="calculator-label">TECHNICAL PREVIEW · USER ASSUMPTIONS</p>
        <h3 id="aqua-heading">Aquaculture capacity + feed</h3>
        <div class="fields">
          <label>Species<select id="aqua-species"></select></label>
          <label>Capacity (<span id="aqua-basis">sourced yield basis</span>)<input id="aqua-capacity" type="number" min="0" step="any" placeholder="Required user assumption"></label>
          <label>Utilization (%)<input id="aqua-utilization" type="number" min="0" max="100" step="any" placeholder="Required user assumption"></label>
        </div>
        <button class="action" id="aqua-calculate" type="button">Calculate technical preview</button>
        <div class="result" id="aqua-result" role="status" aria-live="polite">Choose a species and calculate. Capacity and utilization are user assumptions.</div>
      </section>

      <section class="calculator" aria-labelledby="crop-heading">
        <p class="calculator-label">TECHNICAL PREVIEW · USER ASSUMPTIONS</p>
        <h3 id="crop-heading">Crop yield uplift</h3>
        <div class="fields">
          <label>Crop<select id="crop-name"></select></label>
          <label>Baseline yield<input id="crop-baseline" type="number" min="0" step="any" placeholder="Required user assumption"></label>
          <label>Unit<select id="crop-unit"><option>lb</option><option>tons</option><option>bushels</option></select></label>
        </div>
        <button class="action" id="crop-calculate" type="button">Calculate technical preview</button>
        <div class="result" id="crop-result" role="status" aria-live="polite">Choose a crop and calculate. The baseline and unit are user assumptions.</div>
      </section>
    </div>

    <section class="calculator" aria-labelledby="inventory-heading">
      <p class="calculator-label">PLANNING SANDBOX · ALL VALUES USER ASSUMPTIONS · NOT CANON</p>
      <h3 id="inventory-heading">Monthly inventory flow</h3>
      <div class="fields">
        <label>Opening inventory<input id="inventory-opening" type="number" min="0" step="any" placeholder="Required user assumption"></label>
        <label>Production / month<input id="inventory-production" type="number" min="0" step="any" placeholder="Required user assumption"></label>
        <label>Receipts / month<input id="inventory-receipts" type="number" min="0" step="any" placeholder="Required user assumption"></label>
        <label>Demand / month<input id="inventory-demand" type="number" min="0" step="any" placeholder="Required user assumption"></label>
        <label>Storage loss / month (%)<input id="inventory-loss" type="number" min="0" max="100" step="any" placeholder="Required user assumption"></label>
        <label>Months (1–24)<input id="inventory-months" type="number" min="1" max="24" step="1" placeholder="Required user assumption"></label>
        <label>Unit<select id="inventory-unit"><option>lb</option><option>tons</option><option>bushels</option><option>units</option></select></label>
      </div>
      <button class="action" id="inventory-calculate" type="button">Run inventory preview</button>
      <div class="result" id="inventory-result" role="status" aria-live="polite">Enter assumptions to preview up to 24 months. No campaign state is changed.</div>
    </section>

    <h2>Complete species catalogue</h2>
    <p>These are exact technical inputs from the cited design source. A catalogue entry is not proof of current stocking.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>Species</th><th>Zone / role</th><th>Growth</th><th>Stocking density</th><th>FCR</th><th>Market</th><th>Technical annual yield</th><th>Source</th></tr></thead>
      <tbody>{''.join(species_rows)}</tbody>
    </table></div>

    <h2>Complete crop catalogue</h2>
    <p>Shelter Zones explicitly produce tomatoes. Other entries are technical crop-program values unless their row says confirmed planted.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>Crop</th><th>Class</th><th>Sourced yield uplift</th><th>Confirmed planted</th><th>Source</th></tr></thead>
      <tbody>{''.join(crop_rows)}</tbody>
    </table></div>
    <p class="formula">Overall aqua-enhanced yield increase: {escape(_percent_range(crop_program.get('overall_aqua_enhanced_yield_increase') if isinstance(crop_program, Mapping) else None))}. Fertilizer reduction: {escape(_percent_range(crop_program.get('fertilizer_reduction') if isinstance(crop_program, Mapping) else None))}.</p>
  </section>

  <details>
    <summary>All live Notion source bindings ({len(sources)})</summary>
    <p>The fixture was retrieved {escape(_text(payload.get('retrieved_on')))} with Notion access marked <strong>{escape(_text(payload.get('notion_access')).replace('_', ' '))}</strong>.</p>
    <div class="table-wrap"><table><thead><tr><th>Source</th><th>Authority</th><th>Page ID</th></tr></thead><tbody>{''.join(source_rows)}</tbody></table></div>
  </details>

  <footer>
    <p><strong>Authority rule:</strong> {escape(_text(payload.get('warning')))}</p>
    <p>Fixture schema: <code>{escape(_text(payload.get('schema')))}</code></p>
  </footer>
</main>
<script id="calculator-data" type="application/json">{calculator_json}</script>
<script>{javascript}</script>
</body>
</html>"""


def write_agriculture_workbench_html(
    payload: Mapping[str, object], output: Path
) -> Path:
    """Write the workbench and return its absolute path."""

    destination = output.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        render_agriculture_workbench_html(payload), encoding="utf-8"
    )
    return destination
