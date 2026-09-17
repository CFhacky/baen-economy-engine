"""Readable source-truth report for the Baen food economy."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from html import escape
from pathlib import Path
from typing import Mapping, Sequence


def _text(value: object) -> str:
    return "UNKNOWN" if value is None else str(value)


def _money(value: object) -> str:
    if value is None:
        return "UNKNOWN"
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return f"{value} gp"
    if amount == amount.to_integral_value():
        return f"{amount:,.0f} gp"
    return f"{amount:,f}".rstrip("0").rstrip(".") + " gp"


def _items(values: Sequence[object]) -> str:
    return "".join(f"<li>{escape(_text(item))}</li>" for item in values)


def render_food_baseline_html(payload: Mapping[str, object]) -> str:
    coverage = payload["coverage"]
    totals = payload["commercial_food_baseline"]
    crisis = payload["later_k1495_crisis_context"]
    safety = payload["safety"]
    provenance = payload["provenance"]

    rows: list[str] = []
    detail_sections: list[str] = []
    gm_sections: list[str] = []
    for entity in payload["entities"]:
        finance = entity["reported_finance"]
        inclusion = str(entity["financial_inclusion"]).replace("_", " ")
        outputs = ", ".join(entity["known_outputs"]) or "UNKNOWN"
        rows.append(
            "<tr>"
            f"<td><a href=\"{escape(str(entity['source_url']))}\">"
            f"{escape(str(entity['name']))}</a></td>"
            f"<td>{escape(str(entity['classification']).replace('_', ' '))}"
            f"<br><span class=\"fine\">{escape(inclusion)}</span></td>"
            f"<td>{escape(_text(finance['employees']))}</td>"
            f"<td>Revenue: {escape(_money(finance['monthly_revenue_gp']))}<br>"
            f"Cost: {escape(_money(finance['monthly_cost_gp']))}<br>"
            f"Net: {escape(_money(finance['monthly_net_gp']))}</td>"
            f"<td>{escape(outputs)}</td>"
            "</tr>"
        )
        detail_sections.append(
            "<section class=\"entity\">"
            f"<h3>{escape(str(entity['name']))}</h3>"
            f"<p class=\"meta\">{escape(str(entity['city']))} · "
            f"{escape(str(entity['status']))} · last updated "
            f"{escape(_text(entity['last_updated']))}</p>"
            f"<p><strong>Sourced outputs:</strong> {escape(outputs)}</p>"
            f"<ul>{_items(entity['source_claims'])}</ul>"
            "<p><strong>Physical values still blocked:</strong></p>"
            f"<ul>{_items(entity['physical_unknowns'])}</ul>"
            "</section>"
        )
        if entity["gm_only_claims"]:
            gm_sections.append(
                f"<h3>{escape(str(entity['name']))}</h3>"
                f"<ul>{_items(entity['gm_only_claims'])}</ul>"
            )

    blockers = _items(payload["execution_blockers"])
    rejected = _items(payload["rejected_synthetic_substitutions"])
    css = """
    :root { color-scheme: dark; --bg:#11151a; --panel:#1b222a; --ink:#edf2f7;
      --muted:#aab8c5; --line:#34424f; --gold:#f0c76e; --red:#ff837a;
      --green:#80d4a4; --blue:#8dc8ff; }
    * { box-sizing:border-box; }
    body { margin:0; background:linear-gradient(145deg,#0b0f13,#18212a);
      color:var(--ink); font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif; }
    main { max-width:1220px; margin:auto; padding:34px 24px 70px; }
    h1,h2,h3 { line-height:1.15; }
    h1 { margin:8px 0; font-size:clamp(30px,5vw,54px); }
    h2 { margin-top:38px; color:var(--gold); }
    h3 { margin-bottom:6px; }
    .eyebrow { color:var(--gold); text-transform:uppercase; letter-spacing:.14em;
      font-weight:800; }
    .truth { border:2px solid var(--green); background:#10241b; padding:18px;
      border-radius:12px; font-size:18px; }
    .warning { border-left:5px solid var(--red); background:#2a1819; padding:16px; }
    .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr));
      gap:12px; margin:22px 0; }
    .card,.entity,details { background:var(--panel); border:1px solid var(--line);
      border-radius:12px; padding:16px; }
    .card strong { display:block; font-size:26px; color:var(--blue); }
    .card span,.meta,.fine { color:var(--muted); }
    table { width:100%; border-collapse:collapse; background:var(--panel);
      border:1px solid var(--line); }
    th,td { padding:10px; border-bottom:1px solid var(--line); text-align:left;
      vertical-align:top; }
    th { color:var(--gold); position:sticky; top:0; background:#1b222a; }
    a { color:var(--blue); }
    .scroll { overflow:auto; border-radius:12px; }
    .entities { display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr));
      gap:14px; }
    code { word-break:break-all; color:var(--green); }
    summary { cursor:pointer; color:var(--gold); font-weight:700; }
    @media print { body { background:white; color:black; } .card,.entity,details,table
      { background:white; border-color:#bbb; } .fine,.meta { color:#444; } }
    """
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Baen Food Economy — Source-Truth Baseline</title><style>{css}</style></head>
<body><main>
<p class="eyebrow">Source-truth baseline · zero simulation</p>
<h1>Baen Food Economy</h1>
<p class="truth"><strong>Your data is present.</strong> All 90 Registry rows and
all 90 detailed Registry page bodies are loaded. This report uses the seven
Agriculture/Aquaculture rows and preserves missing physical quantities as
<strong>UNKNOWN</strong>, never zero.</p>
<p class="warning"><strong>The correction:</strong> Agricultural Shelter Zones
are sourced as climate-controlled produce and tomato greenhouses, with
Longsaddle separately naming cold-frame vegetables. The wider live corpus also
names wheat, barley, rye, fifteen aquaculture species, and species-specific feed
ratios. What remains unsupported is assigning grain or feed production to the
shelter zones themselves.</p>
<p class="warning"><strong>Physical execution: BLOCKED.</strong> Missing values
remain UNKNOWN until a source or explicit campaign ruling supplies them.</p>

<div class="cards">
  <div class="card"><strong>{coverage['registry_property_rows']}/90</strong><br><span>Registry property rows</span></div>
  <div class="card"><strong>{coverage['registry_page_bodies']}/90</strong><br><span>detailed page bodies</span></div>
  <div class="card"><strong>{coverage['food_rows']}/7</strong><br><span>food-sector records</span></div>
  <div class="card"><strong>{totals['employees']}</strong><br><span>reported employees</span></div>
  <div class="card"><strong>{_money(totals['monthly_revenue_gp'])}</strong><br><span>reported monthly revenue</span></div>
  <div class="card"><strong>{_money(totals['monthly_cost_gp'])}</strong><br><span>reported monthly cost</span></div>
  <div class="card"><strong>{_money(totals['monthly_net_gp'])}</strong><br><span>arithmetic monthly net</span></div>
</div>
<p class="fine">The financial envelope is last-known Eleint 20, 1494 and
pre-crisis. It is not opening cash and is not silently advanced to Kythorn 1495.</p>

<h2>Every food-sector record</h2>
<div class="scroll"><table>
<thead><tr><th>Entity</th><th>Class / treatment</th><th>Staff</th>
<th>Reported finance / month</th><th>Sourced outputs</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>

<h2>Later Kythorn 1495 crisis state</h2>
<div class="cards">
  <div class="card"><strong>{crisis['shelter_zones_destroyed']}/{crisis['shelter_zones_total']}</strong><span>Dawnwood-margin zones destroyed</span></div>
  <div class="card"><strong>{crisis['longsaddle_population_mouths']}</strong><span>Longsaddle mouths; net importer</span></div>
  <div class="card"><strong>{crisis['grain_procurement_target_tons']['low']}–{crisis['grain_procurement_target_tons']['high']} tons</strong><span>planned grain target, not purchased stock</span></div>
  <div class="card"><strong>0</strong><span>resolved execution rolls or transactions</span></div>
</div>
<p class="warning">{escape(str(crisis['topology_conflict']))}
Five zones are only “not reported destroyed”; they are not assumed operational
or equal in capacity.</p>

<h2>Source-grounded entity detail</h2>
<div class="entities">{''.join(detail_sections)}</div>

<h2>Why a canonical month close is blocked</h2>
<p>Technical and user-assumption previews can run, but a canonical month close
cannot manufacture opening stock, site allocations, executed deliveries, or
cash. These execution inputs remain missing:</p><ul>{blockers}</ul>

<h2>Removed from the campaign default</h2>
<ul>{rejected}</ul>

<details><summary>GM-only operating facts retained but not auto-posted</summary>
{''.join(gm_sections)}
<p class="fine">These facts are visibility-gated. They do not become ordinary
revenue, cost, loss, or player-facing knowledge merely because the source
snapshot contains them.</p></details>

<h2>Safety and provenance</h2>
<p>Notion writes: <strong>{safety['notion_writes']}</strong> · canonical ledger
postings: <strong>{safety['canonical_ledger_postings']}</strong> · dice rolled:
<strong>{safety['dice_rolled']}</strong> · campaign time advanced:
<strong>{str(safety['campaign_time_advanced']).lower()}</strong></p>
<p class="fine">Baseline hash: <code>{escape(str(payload['baseline_hash']))}</code><br>
Registry export: <code>{escape(str(provenance['registry_export_content_hash']))}</code><br>
Page-body snapshot: <code>{escape(str(provenance['page_body_snapshot_sha256']))}</code></p>
</main></body></html>"""


def write_food_baseline_html(
    payload: Mapping[str, object], output: Path
) -> Path:
    destination = output.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_food_baseline_html(payload), encoding="utf-8")
    return destination
