"""User-facing, dependency-free Baen food-sector operator application.

The page is served by :mod:`baen_economy.food_ops_server`.  It is deliberately
an operator surface rather than a second source report: known values arrive
from the read-only bootstrap endpoint, assumptions are entered only inside a
named workflow, and every result can be saved or exported locally.
"""

from __future__ import annotations

from pathlib import Path


def render_food_ops_app() -> str:
    """Return the complete local operator UI."""

    return _HTML


def write_food_ops_app(path: str | Path) -> Path:
    """Write the operator UI for inspection or packaging."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_food_ops_app(), encoding="utf-8")
    return destination


_HTML = r'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Baen Food-Sector Operator</title>
  <style>
    :root {
      color-scheme: dark;
      --ink:#eef2ee; --muted:#aeb9b0; --panel:#151b18; --panel2:#1c2520;
      --line:#3d4a42; --green:#72d39b; --gold:#e5bd69; --red:#ff8c82;
      --blue:#81b7e8; --amber:#2c2415; --source:#183126; --derived:#172b38;
      --unknown:#2f1d1d; --shadow:0 16px 45px rgba(0,0,0,.28);
    }
    * { box-sizing:border-box; }
    html { scroll-behavior:smooth; }
    body { margin:0; background:#0c100e; color:var(--ink); font:16px/1.5 system-ui,-apple-system,Segoe UI,sans-serif; }
    button,input,select { font:inherit; }
    a { color:#9dcef6; }
    header { position:sticky; top:0; z-index:10; background:rgba(12,16,14,.96); border-bottom:1px solid var(--line); backdrop-filter:blur(10px); }
    .mast { max-width:1280px; margin:auto; padding:1rem 1.25rem .8rem; display:flex; gap:1rem; align-items:center; justify-content:space-between; }
    .brand h1 { font-size:1.1rem; margin:0; letter-spacing:.04em; }
    .brand p { margin:.1rem 0 0; color:var(--muted); font-size:.85rem; }
    .badge { display:inline-flex; align-items:center; gap:.45rem; padding:.4rem .65rem; border:1px solid #49745b; border-radius:999px; color:var(--green); background:#102219; font-size:.82rem; white-space:nowrap; }
    nav { max-width:1280px; margin:auto; padding:0 1.25rem .85rem; display:flex; gap:.4rem; overflow:auto; }
    nav button { border:1px solid var(--line); color:var(--muted); background:transparent; border-radius:8px; padding:.55rem .8rem; white-space:nowrap; cursor:pointer; }
    nav button[aria-selected="true"] { color:#10140f; background:var(--gold); border-color:var(--gold); font-weight:750; }
    main { max-width:1280px; margin:auto; padding:1.4rem 1.25rem 5rem; }
    .view[hidden] { display:none; }
    .hero { display:grid; grid-template-columns:1.5fr 1fr; gap:1rem; align-items:stretch; margin-bottom:1.25rem; }
    .panel,.card { border:1px solid var(--line); background:var(--panel); border-radius:12px; box-shadow:var(--shadow); }
    .panel { padding:1.25rem; }
    .hero h2 { font-size:clamp(1.7rem,4vw,3rem); line-height:1.05; margin:.2rem 0 .65rem; }
    .hero p { max-width:68ch; color:var(--muted); }
    .eyebrow { color:var(--gold); font-weight:800; letter-spacing:.09em; font-size:.78rem; text-transform:uppercase; }
    .actions { display:flex; flex-wrap:wrap; gap:.6rem; margin-top:1rem; }
    button.primary,button.secondary,button.danger { cursor:pointer; border-radius:8px; padding:.68rem .9rem; font-weight:750; }
    button.primary { background:var(--gold); color:#12140f; border:1px solid var(--gold); }
    button.secondary { background:#202a24; color:var(--ink); border:1px solid #526158; }
    button.danger { background:#3a1d1c; color:#ffd8d4; border:1px solid #85453f; }
    button:disabled { opacity:.45; cursor:not-allowed; }
    .kpis { display:grid; grid-template-columns:repeat(5,minmax(140px,1fr)); gap:.75rem; margin:1rem 0 1.4rem; }
    .kpi { padding:1rem; border:1px solid var(--line); background:var(--panel2); border-radius:10px; }
    .kpi span { color:var(--muted); display:block; font-size:.82rem; }
    .kpi strong { display:block; font-size:1.45rem; margin-top:.18rem; }
    .section-head { display:flex; align-items:end; justify-content:space-between; gap:1rem; margin:1.6rem 0 .75rem; }
    .section-head h2,.section-head h3 { margin:0; }
    .section-head p { margin:0; color:var(--muted); }
    .table-wrap { overflow:auto; border:1px solid var(--line); border-radius:10px; }
    table { width:100%; border-collapse:collapse; min-width:760px; background:var(--panel); }
    th,td { text-align:left; padding:.72rem .8rem; border-bottom:1px solid #2d3831; vertical-align:top; }
    th { color:var(--gold); font-size:.78rem; text-transform:uppercase; letter-spacing:.05em; background:#111613; }
    td.num,th.num { text-align:right; font-variant-numeric:tabular-nums; }
    tr:last-child td { border-bottom:0; }
    .stale { color:#ffd08a; }
    .grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.8rem; }
    .issue { padding:1rem; border:1px solid var(--line); border-left:4px solid var(--red); border-radius:10px; background:var(--panel); }
    .issue.known { border-left-color:var(--gold); }
    .issue h3 { margin:0 0 .35rem; font-size:1rem; }
    .issue p { margin:.35rem 0; color:var(--muted); }
    .issue .knowledge { color:var(--blue); font-size:.78rem; font-weight:750; text-transform:uppercase; }
    .source-box { border:1px solid #355d46; background:var(--source); border-radius:10px; padding:1rem; }
    .source-box h3 { margin-top:0; }
    .source-grid { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:.7rem; }
    .source-fact { border-left:3px solid var(--green); padding:.55rem .7rem; background:rgba(0,0,0,.14); }
    .source-fact span { display:block; color:var(--muted); font-size:.78rem; }
    .source-fact strong { font-size:1.1rem; }
    form { margin-top:1rem; }
    fieldset { border:1px solid var(--line); border-radius:10px; padding:1rem; margin:0 0 1rem; background:var(--panel); }
    legend { color:var(--gold); font-weight:800; padding:0 .4rem; }
    .fields { display:grid; grid-template-columns:repeat(3,minmax(180px,1fr)); gap:.8rem; }
    label { display:grid; gap:.28rem; color:var(--muted); font-size:.86rem; }
    label small { color:#89958d; }
    input,select { width:100%; border:1px solid #526158; border-radius:7px; color:var(--ink); background:#0f1512; padding:.62rem .68rem; }
    input:focus,select:focus,button:focus-visible { outline:3px solid rgba(229,189,105,.35); outline-offset:2px; }
    .assumption { border-left:4px solid var(--gold); background:var(--amber); }
    .assumption-note { color:#f1ce86; font-size:.83rem; margin-top:0; }
    .result { margin-top:1rem; border:1px solid #41687e; background:var(--derived); padding:1rem; border-radius:10px; }
    .result[hidden] { display:none; }
    .status { display:inline-block; border-radius:999px; padding:.32rem .58rem; font-weight:850; font-size:.78rem; text-transform:uppercase; }
    .status.met { background:#163724; color:#86e7aa; }
    .status.risk { background:#423315; color:#f5ce78; }
    .status.failed { background:#421e1d; color:#ffaaa1; }
    .status.preview { background:#1c3447; color:#9ed2fb; }
    .provenance { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.65rem; margin-top:1rem; }
    .prov { padding:.75rem; border-radius:8px; border:1px solid var(--line); min-width:0; }
    .prov h4 { margin:0 0 .35rem; }
    .prov pre { white-space:pre-wrap; overflow-wrap:anywhere; font:12px/1.45 ui-monospace,Consolas,monospace; margin:0; color:var(--muted); }
    .prov.source { background:var(--source); }.prov.derived { background:var(--derived); }.prov.unknown { background:var(--unknown); }.prov.assumed { background:var(--amber); }
    .error { color:#ffb1a9; background:#3b1d1c; border:1px solid #7d403b; border-radius:8px; padding:.75rem; }
    .notice { color:var(--muted); border:1px dashed var(--line); padding:.8rem; border-radius:8px; }
    .saved-list { display:grid; gap:.55rem; }
    .saved { display:flex; gap:.7rem; align-items:center; justify-content:space-between; border:1px solid var(--line); border-radius:8px; padding:.7rem; background:var(--panel); }
    details { border:1px solid var(--line); border-radius:9px; padding:.7rem .85rem; margin:.6rem 0; background:var(--panel); }
    summary { cursor:pointer; color:var(--gold); font-weight:750; }
    code { color:#b9d9f1; overflow-wrap:anywhere; }
    footer { color:var(--muted); border-top:1px solid var(--line); padding:1.2rem; text-align:center; }
    @media(max-width:900px){.hero,.grid{grid-template-columns:1fr}.kpis{grid-template-columns:repeat(2,1fr)}.source-grid,.fields,.provenance{grid-template-columns:1fr 1fr}.mast{align-items:flex-start}.brand p{display:none}}
    @media(max-width:580px){main{padding-inline:.8rem}.mast,nav{padding-inline:.8rem}.kpis,.source-grid,.fields,.provenance{grid-template-columns:1fr}.hero h2{font-size:2rem}.saved{align-items:flex-start;flex-direction:column}}
    @media print { header,.no-print,button { display:none!important; } body{background:white;color:black}.view[hidden]{display:none}.view:not([hidden]){display:block}.panel,.card,.result,.source-box,fieldset{box-shadow:none;background:white;color:black;border-color:#777}a{color:black}.provenance{grid-template-columns:repeat(2,1fr)} }
  </style>
</head>
<body>
<header>
  <div class="mast">
    <div class="brand"><h1>Baen Food-Sector Operator</h1><p>Source-bound planning and monthly business previews</p></div>
    <span class="badge">● Read-only · no Notion or ledger writes</span>
  </div>
  <nav aria-label="Operator sections">
    <button data-view="dashboard" aria-selected="true">Dashboard</button>
    <button data-view="longsaddle" aria-selected="false">Plan Longsaddle</button>
    <button data-view="production" aria-selected="false">Plan Fish &amp; Crops</button>
    <button data-view="month" aria-selected="false">Preview Food Month</button>
    <button data-view="rulings" aria-selected="false">Open Rulings</button>
    <button data-view="evidence" aria-selected="false">Evidence</button>
  </nav>
</header>
<main>
  <section class="view" id="view-dashboard">
    <div class="hero">
      <article class="panel">
        <p class="eyebrow">Operating surface</p>
        <h2>Decisions first. Sources remain attached.</h2>
        <p>This screen uses the five confirmed food-sector Registry rows as a dated operating envelope. It does not pretend that Eleint 1494 finances are Day 7 Hammer 1495 physical inventory.</p>
        <div class="actions no-print"><button class="primary" data-go="longsaddle">Plan Longsaddle grain</button><button class="secondary" data-go="production">Plan fish or crops</button><button class="secondary" data-go="month">Preview a food-sector month</button></div>
      </article>
      <aside class="panel">
        <p class="eyebrow">Authority boundary</p>
        <p><strong>Live campaign:</strong> <span id="campaign-date">Loading…</span></p>
        <p><strong>Registry envelope:</strong> <span id="registry-date">Loading…</span></p>
        <p class="stale">A preview never advances time. Binding rolls and canonical month close require explicit acceptance.</p>
      </aside>
    </div>
    <div class="kpis" id="baseline-kpis" aria-label="Food sector baseline"></div>
    <div class="section-head"><div><h2>Confirmed operating businesses</h2><p>Historical Registry values included in the food-sector envelope.</p></div></div>
    <div class="table-wrap"><table><thead><tr><th>Entity</th><th>Sector</th><th>As of</th><th class="num">Staff</th><th class="num">Revenue</th><th class="num">Cost</th><th class="num">Net</th></tr></thead><tbody id="business-rows"><tr><td colspan="7">Loading source-bound baseline…</td></tr></tbody></table></div>
    <div class="section-head"><div><h2>Known operational decisions</h2><p>Visible to operations now; no automatic modifier is invented.</p></div></div>
    <div class="grid" id="known-issues"></div>
    <div class="section-head"><div><h2>GM clocks</h2><p>Kept separate from Vara’s knowledge and from automatic mechanical effects.</p></div></div>
    <div class="grid" id="gm-clocks"></div>
  </section>

  <section class="view" id="view-longsaddle" hidden>
    <p class="eyebrow">Forward scenario · late Kythorn 1495 · non-canon until accepted</p>
    <h2>Longsaddle grain-security plan</h2>
    <p>Known facts are locked. Editable values below are named planning assumptions, not replacements for campaign canon.</p>
    <section class="source-box">
      <h3>Locked source facts</h3>
      <div class="source-grid">
        <div class="source-fact"><span>Population</span><strong>11,000</strong></div>
        <div class="source-fact"><span>Procurement target</span><strong>1,200–1,500 t</strong></div>
        <div class="source-fact"><span>Already procured</span><strong>0 t</strong></div>
        <div class="source-fact"><span>Budget, grain + transport</span><strong>65,000–95,000 gp</strong></div>
        <div class="source-fact"><span>First harvest</span><strong>Eleint–Marpenoth</strong></div>
      </div>
      <p><a href="https://app.notion.com/p/396e821484b0816c9dd3e88e17fc70f1" target="_blank" rel="noreferrer">Operation Laden Table</a> · <a href="https://app.notion.com/p/348e821484b081a68349ecdc1f0efef8" target="_blank" rel="noreferrer">Longsaddle Valley</a></p>
    </section>
    <form id="longsaddle-form">
      <fieldset class="assumption"><legend>Plan assumptions</legend><p class="assumption-note">Every field is scenario-specific. Blank means unresolved; it never becomes zero.</p>
        <div class="fields">
          <label>Scenario name<input id="ls-name" required placeholder="e.g. Low procurement case"></label>
          <label>Target grain (tons)<small>Sourced target range: 1,200–1,500</small><input id="ls-target" type="number" min="1200" max="1500" step="any"></label>
          <label>Supplier stock available (tons)<input id="ls-supplier" type="number" min="0" step="any"></label>
          <label>Opening Longsaddle stock (tons)<input id="ls-opening" type="number" min="0" step="any"></label>
          <label>Consumption before first harvest (tons)<input id="ls-demand" type="number" min="0" step="any"></label>
          <label>Planned dispatch (tons)<input id="ls-dispatch" type="number" min="0" step="any"></label>
          <label>Route capacity per trip (tons)<input id="ls-route-capacity" type="number" min="0" step="any"></label>
          <label>Trips available<input id="ls-trips" type="number" min="0" step="1"></label>
          <label>Travel periods<input id="ls-travel" type="number" min="1" step="1"></label>
          <label>Transport loss (%)<input id="ls-loss" type="number" min="0" max="99.999999" step="any"></label>
          <label>Longsaddle storage capacity (tons)<input id="ls-storage" type="number" min="0" step="any"></label>
          <label>Price including transport (gp/ton)<input id="ls-price" type="number" min="0" step="any"></label>
          <label>Funding available (gp)<input id="ls-funding" type="number" min="0" step="any"></label>
        </div>
      </fieldset>
      <div class="actions no-print"><button type="button" class="secondary" id="load-low">Load illustrative low case</button><button type="submit" class="primary">Run plan</button></div>
    </form>
    <div id="longsaddle-error" aria-live="assertive"></div>
    <section class="result" id="longsaddle-result" hidden aria-live="polite"></section>
  </section>

  <section class="view" id="view-production" hidden>
    <p class="eyebrow">Physical production planning · source parameters + explicit assumptions</p>
    <h2>Fish, feed, crops, and food inventory</h2>
    <p>This is where the named species and crop programme become usable. Technical yields and feed ratios stay attached to their sources; site capacity, current biomass, acreage, opening inventory, and demand remain explicit scenario inputs because the campaign sources do not establish them.</p>
    <div class="grid">
      <form id="aquaculture-form">
        <fieldset><legend>Aquaculture and feed plan</legend>
          <div class="fields">
            <label>Scenario name<input id="aq-name" required placeholder="e.g. Blacklake tilapia capacity case"></label>
            <label>Species<select id="aq-species" required><option value="">Loading 15 named species…</option></select></label>
            <label>Capacity basis<select id="aq-basis" required><option value="cubic_meters">Cubic metres</option><option value="square_meters">Square metres</option></select></label>
            <label>Planned capacity<input id="aq-capacity" type="number" min="0" step="any" required></label>
            <label>Planned liveweight output (lb)<input id="aq-output" type="number" min="0" step="any" required></label>
            <label>Opening feed (lb)<input id="aq-opening-feed" type="number" min="0" step="any" required></label>
            <label>Feed receipts (lb)<input id="aq-feed-receipts" type="number" min="0" step="any" required></label>
          </div>
          <details class="assumption"><summary>Only if the selected source field is UNKNOWN</summary><p class="assumption-note">These do not overwrite the source catalogue. Leave blank when the selected species already has the parameter.</p><div class="fields">
            <label>Assumed annual intensity low<input id="aq-yield-low" type="number" min="0" step="any"></label>
            <label>Assumed annual intensity high<input id="aq-yield-high" type="number" min="0" step="any"></label>
            <label>Assumed intensity basis<select id="aq-yield-basis"><option value="cubic_meters">Cubic metres</option><option value="square_meters">Square metres</option></select></label>
            <label>Assumed feed ratio low<input id="aq-fcr-low" type="number" min="0" step="any"></label>
            <label>Assumed feed ratio high<input id="aq-fcr-high" type="number" min="0" step="any"></label>
          </div></details>
          <div id="aq-source-card" class="notice">Choose a species to see its sourced parameters.</div>
          <div class="actions no-print"><button type="submit" class="primary">Run aquaculture plan</button></div>
        </fieldset>
      </form>
      <form id="crop-form">
        <fieldset><legend>Crop and food-stock plan</legend>
          <div class="fields">
            <label>Scenario name<input id="crop-name" required placeholder="e.g. Longsaddle wheat uplift case"></label>
            <label>Crop<select id="crop-id" required><option value="">Loading 12 crop entries…</option></select></label>
            <label>Baseline harvest (tons)<input id="crop-baseline" type="number" min="0" step="any" required></label>
            <label>Baseline fertilizer (tons)<input id="crop-fertilizer" type="number" min="0" step="any" required></label>
            <label>Opening food stock (tons)<input id="crop-opening" type="number" min="0" step="any" required></label>
            <label>Food receipts (tons)<input id="crop-receipts" type="number" min="0" step="any" required></label>
            <label>Planned consumption (tons)<input id="crop-consumption" type="number" min="0" step="any" required></label>
          </div>
          <details class="assumption"><summary>Only if sourced yield uplift is UNKNOWN</summary><p class="assumption-note">Leave blank when the crop already has a sourced technical uplift.</p><div class="fields">
            <label>Assumed uplift low (decimal)<input id="crop-uplift-low" type="number" min="0" step="any" placeholder="e.g. 0.20"></label>
            <label>Assumed uplift high (decimal)<input id="crop-uplift-high" type="number" min="0" step="any" placeholder="e.g. 0.30"></label>
          </div></details>
          <div id="crop-source-card" class="notice">Choose a crop to see its sourced parameters.</div>
          <div class="actions no-print"><button type="submit" class="primary">Run crop plan</button></div>
        </fieldset>
      </form>
    </div>
    <div id="production-error" aria-live="assertive"></div>
    <section class="result" id="production-result" hidden aria-live="polite"></section>
  </section>

  <section class="view" id="view-month" hidden>
    <p class="eyebrow">GURPS business preview · read-only</p>
    <h2>Food-sector month preview</h2>
    <p>One revenue roll is made for Agriculture and one for Aquaculture, then applied to every confirmed entity in that sector. The preview records every face, target, modifier, margin, and factor. It is not a binding campaign roll.</p>
    <form id="month-form">
      <fieldset><legend>Preview identity</legend><div class="fields">
        <label>Month label<input id="month-label" required value="Day 7 Hammer 1495 planning preview"></label>
        <label>Replay seed<small>Required unless all four 3d6 receipts are supplied below</small><input id="month-seed" placeholder="Used only for this reproducible preview"></label>
      </div></fieldset>
      <div class="grid">
        <fieldset class="assumption" data-sector="Agriculture"><legend>Agriculture assumptions</legend><div class="fields sector-fields">
          <label>Market<select data-key="market"><option value="stable">Stable</option><option value="boom">Boom</option><option value="recession">Recession</option></select></label>
          <label>Revenue streams<input data-key="revenue_streams" type="number" min="1" step="1" value="1"></label>
          <label>Competent managers (0–3)<input data-key="competent_managers" type="number" min="0" max="3" step="1" value="0"></label>
          <label><span>Vara active</span><select data-key="vara_active"><option value="true">Yes</option><option value="false">No</option></select></label>
          <label><span>Monopoly position</span><select data-key="monopoly"><option value="false">No</option><option value="true">Yes</option></select></label>
          <label><span>Excellent accounting</span><select data-key="excellent_accounting"><option value="false">No</option><option value="true">Yes</option></select></label>
          <label><span>Rapid expansion</span><select data-key="rapid_expansion"><option value="false">No</option><option value="true">Yes</option></select></label>
          <label>Supplied revenue faces<small>Comma-separated 3d6; supply all four rolls or none</small><input data-key="revenue_faces" placeholder="e.g. 3,4,5"></label>
          <label>Supplied expense faces<small>Comma-separated 3d6; supply all four rolls or none</small><input data-key="expense_faces" placeholder="e.g. 2,3,4"></label>
        </div></fieldset>
        <fieldset class="assumption" data-sector="Aquaculture"><legend>Aquaculture assumptions</legend><div class="fields sector-fields">
          <label>Market<select data-key="market"><option value="stable">Stable</option><option value="boom">Boom</option><option value="recession">Recession</option></select></label>
          <label>Revenue streams<input data-key="revenue_streams" type="number" min="1" step="1" value="4"></label>
          <label>Competent managers (0–3)<input data-key="competent_managers" type="number" min="0" max="3" step="1" value="0"></label>
          <label><span>Vara active</span><select data-key="vara_active"><option value="true">Yes</option><option value="false">No</option></select></label>
          <label><span>Monopoly position</span><select data-key="monopoly"><option value="false">No</option><option value="true">Yes</option></select></label>
          <label><span>Excellent accounting</span><select data-key="excellent_accounting"><option value="false">No</option><option value="true">Yes</option></select></label>
          <label><span>Rapid expansion</span><select data-key="rapid_expansion"><option value="false">No</option><option value="true">Yes</option></select></label>
          <label>Supplied revenue faces<small>Comma-separated 3d6; supply all four rolls or none</small><input data-key="revenue_faces" placeholder="e.g. 3,4,5"></label>
          <label>Supplied expense faces<small>Comma-separated 3d6; supply all four rolls or none</small><input data-key="expense_faces" placeholder="e.g. 2,3,4"></label>
        </div></fieldset>
      </div>
      <div class="actions no-print"><button type="button" class="secondary" id="generate-seed">Generate replay seed</button><button type="submit" class="primary">Run non-canon preview</button></div>
    </form>
    <div id="month-error" aria-live="assertive"></div>
    <section class="result" id="month-result" hidden aria-live="polite"></section>
  </section>

  <section class="view" id="view-rulings" hidden>
    <p class="eyebrow">Only genuine gaps</p><h2>Open rulings and source work</h2>
    <p>These are not thirteen undifferentiated blockers. Each item states what it affects and whether a source, ruling, or in-world audit can resolve it.</p>
    <div id="ruling-list"></div>
    <div class="section-head"><div><h2>Saved local scenarios</h2><p>Review, reopen, compare, or export without touching Notion.</p></div><button class="secondary no-print" id="refresh-saved">Refresh</button></div>
    <div class="saved-list" id="saved-list"><p class="notice">No saved scenarios loaded.</p></div>
    <section class="result" id="compare-result" hidden></section>
  </section>

  <section class="view" id="view-evidence" hidden>
    <p class="eyebrow">Audit appendix</p><h2>Evidence register</h2>
    <p>The old workbench belongs here: useful for auditing, not mistaken for the operator itself.</p>
    <div id="evidence-summary" class="kpis"></div>
    <div id="evidence-list"></div>
  </section>
</main>
<footer>Local planning application · Notion writes 0 · ledger postings 0 · campaign time advanced no</footer>
<script>
'use strict';
let bootstrap = null;
let currentResult = null;
let currentRequest = null;
let currentKind = null;
const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const numberText = (v,digits=4) => {
  if(v===null || v===undefined || v==='' || v==='UNKNOWN') return 'UNKNOWN';
  const parsed=Number(v); return Number.isFinite(parsed)?parsed.toLocaleString(undefined,{maximumFractionDigits:digits}):String(v);
};
const money = (v) => { const text=numberText(v,2); return text==='UNKNOWN'?'UNKNOWN':`${text} gp`; };
const qty = (v,u='t') => { const text=numberText(v,4); return text==='UNKNOWN'?'UNKNOWN':`${text} ${u}`; };
const dataOf = (payload) => payload && payload.data !== undefined ? payload.data : payload;

async function api(path, options={}) {
  const response = await fetch(path, {headers:{'Content-Type':'application/json'}, ...options});
  let payload;
  try { payload = await response.json(); } catch (_) { throw new Error('Operator returned an unreadable response.'); }
  if (!response.ok || payload.ok === false) throw new Error(payload.error?.message || payload.error || payload.message || `Request failed (${response.status})`);
  return dataOf(payload);
}

function showView(name) {
  document.querySelectorAll('.view').forEach(view => view.hidden = view.id !== `view-${name}`);
  document.querySelectorAll('nav button').forEach(button => button.setAttribute('aria-selected', String(button.dataset.view === name)));
  history.replaceState(null,'',`#${name}`);
  if (name === 'rulings') refreshSaved();
  window.scrollTo({top:0,behavior:'smooth'});
}
document.querySelectorAll('nav button').forEach(button => button.addEventListener('click',()=>showView(button.dataset.view)));
document.querySelectorAll('[data-go]').forEach(button => button.addEventListener('click',()=>showView(button.dataset.go)));

function baselineData() {
  return bootstrap?.baseline || bootstrap?.food_sector_baseline || bootstrap?.snapshot || bootstrap || {};
}
function renderBootstrap() {
  const base = baselineData();
  const totals = base.totals || bootstrap?.totals || {};
  const entities = base.entities || base.records || bootstrap?.entities || [];
  $('campaign-date').textContent = bootstrap?.campaign_date || bootstrap?.current_actual_state?.campaign_date || 'Day 7 Hammer 1495 DR (source freeze)';
  $('registry-date').textContent = base.as_of || bootstrap?.registry_as_of || 'Eleint 20, 1494 (last-known envelope)';
  const kpis = [
    ['Staff', totals.employees ?? totals.staff ?? 'UNKNOWN'],
    ['Revenue / month', money(totals.monthly_revenue_gp ?? totals.revenue_gp)],
    ['Cost / month', money(totals.monthly_cost_gp ?? totals.cost_gp)],
    ['Arithmetic net', money(totals.monthly_net_gp ?? totals.net_gp)],
    ['Invested capital', money(totals.capital_invested_gp ?? totals.capital_gp)]
  ];
  $('baseline-kpis').innerHTML = kpis.map(([l,v])=>`<div class="kpi"><span>${esc(l)}</span><strong>${esc(v)}</strong></div>`).join('');
  $('business-rows').innerHTML = entities.length ? entities.map(entity => {
    const revenue = entity.monthly_revenue_gp ?? entity.revenue_gp;
    const cost = entity.monthly_cost_gp ?? entity.cost_gp;
    const net = entity.monthly_net_gp ?? (revenue !== undefined && cost !== undefined ? Number(revenue)-Number(cost) : null);
    return `<tr><td><strong>${esc(entity.name || entity.entity)}</strong></td><td>${esc(entity.sector)}</td><td class="stale">${esc(entity.as_of || entity.source_last_updated)}</td><td class="num">${esc(entity.employees ?? entity.staff)}</td><td class="num">${esc(money(revenue))}</td><td class="num">${esc(money(cost))}</td><td class="num">${esc(money(net))}</td></tr>`;
  }).join('') : '<tr><td colspan="7">The server returned no eligible source rows.</td></tr>';
  const context = bootstrap?.operational_context || bootstrap?.context || {};
  renderIssues('known-issues', context.known_operational_issues || bootstrap?.known_operational_issues || [], true);
  renderIssues('gm-clocks', context.gm_only_clocks || bootstrap?.gm_only_clocks || [], false);
  renderProductionCatalog();
  renderRulings(bootstrap?.rulings || bootstrap?.unresolved_inputs || []);
  renderEvidence();
}
function renderIssues(target, issues, known) {
  $(target).innerHTML = issues.length ? issues.map(item => `<article class="issue ${known?'known':''}"><span class="knowledge">${esc(item.knowledge || (known?'Operationally known':'GM-only'))}</span><h3>${esc(item.title)}</h3><p>${esc(item.decision_needed || item.trigger || item.status)}</p>${item.source_url?`<a href="${esc(item.source_url)}" target="_blank" rel="noreferrer">Open source</a>`:''}</article>`).join('') : '<p class="notice">No source-bound issues were returned.</p>';
}
function renderRulings(rulings) {
  const fallback = [
    ['Pond topology','GM ruling or site survey','Establish whether the technical ten NMWC ponds overlap Blacklake’s seven pools.','Unlocks network totals and site allocation.'],
    ['Current species allocation','Source or in-world audit','Record which species and cohorts occupy each current pool.','Unlocks feed, harvest, and disease modeling.'],
    ['Shelter acreage and crops','Source or in-world audit','Identify surviving zones, acreage, crop allocation, and baseline yield.','Unlocks physical greenhouse output.'],
    ['Opening inventories and feed','Opening-state audit','Measure food, biomass, feed, seed, and storage by site.','Unlocks the first conserved physical month.'],
    ['Demand and ration policy','Campaign ruling','Set population demand by food class and priority.','Unlocks shortages and coverage dates.'],
    ['Opening cash and ledgers','Finance gate','Approve a source-backed opening financial state.','Unlocks canonical settlement; previews remain available without it.']
  ];
  const items = rulings.length ? rulings.map((r,i)=>[r.title || r.name || `Open item ${i+1}`,r.resolution_type || r.classification || 'Source or ruling',r.description || r.text || String(r),r.unlocks || 'Relevant calculations only']) : fallback;
  $('ruling-list').innerHTML = items.map(([title,type,desc,unlock])=>`<details><summary>${esc(title)} · ${esc(type)}</summary><p>${esc(desc)}</p><p><strong>Unlocks:</strong> ${esc(unlock)}</p></details>`).join('');
}
function renderEvidence() {
  const sources = bootstrap?.sources || bootstrap?.evidence?.sources || [];
  const species = bootstrap?.production_catalog?.species || bootstrap?.species || bootstrap?.evidence?.species || [];
  const crops = bootstrap?.production_catalog?.crops || bootstrap?.crops || bootstrap?.crop_program?.crops || bootstrap?.evidence?.crops || [];
  $('evidence-summary').innerHTML = [['Notion authorities',sources.length],['Named species',species.length],['Crop entries',crops.length],['Notion writes',0],['Ledger postings',0]].map(([l,v])=>`<div class="kpi"><span>${esc(l)}</span><strong>${esc(v)}</strong></div>`).join('');
  const sourceHtml = sources.length ? `<div class="table-wrap"><table><thead><tr><th>Source</th><th>Authority</th><th>ID</th></tr></thead><tbody>${sources.map(s=>`<tr><td>${s.url?`<a href="${esc(s.url)}" target="_blank" rel="noreferrer">${esc(s.title || s.name || s.source_id)}</a>`:esc(s.title || s.name || s.source_id)}</td><td>${esc(s.authority || s.authority_class || s.temporal_class)}</td><td><code>${esc(s.page_id || s.id || s.source_id)}</code></td></tr>`).join('')}</tbody></table></div>` : '<p class="notice">Source details are available in the agriculture evidence report.</p>';
  $('evidence-list').innerHTML = `<details open><summary>Source bindings (${sources.length})</summary>${sourceHtml}</details><details><summary>Species catalogue (${species.length})</summary><pre>${esc(JSON.stringify(species,null,2))}</pre></details><details><summary>Crop programme (${crops.length})</summary><pre>${esc(JSON.stringify(crops,null,2))}</pre></details>`;
}

function productionCatalog() {
  return bootstrap?.production_catalog || bootstrap?.food_production_catalog || {};
}
function renderProductionCatalog() {
  const catalog=productionCatalog();
  const speciesRaw=catalog.species || bootstrap?.species || [];
  const cropsRaw=catalog.crops || bootstrap?.crops || bootstrap?.crop_program?.crops || [];
  const species=Array.isArray(speciesRaw)?speciesRaw:[];
  const crops=Array.isArray(cropsRaw)?cropsRaw:[];
  $('aq-species').innerHTML='<option value="">Choose a named species</option>'+species.map(item=>`<option value="${esc(item.species_id || item.id)}">${esc(item.name)} · ${esc(item.zone || 'zone unknown')}</option>`).join('');
  $('crop-id').innerHTML='<option value="">Choose a crop entry</option>'+crops.map(item=>`<option value="${esc(item.crop_id || item.id)}">${esc(item.name)} · ${esc(item.crop_class || item.class || 'class unknown')}</option>`).join('');
  const showSpecies=()=>{
    const item=species.find(row=>(row.species_id||row.id)===$('aq-species').value);
    if(!item){$('aq-source-card').textContent='Choose a species to see its sourced parameters.';return}
    const intensity=item.annual_yield_lb_per_1000_unit;
    if(intensity?.basis) $('aq-basis').value=intensity.basis;
    for(const id of ['aq-yield-low','aq-yield-high','aq-yield-basis']){ $(id).disabled=Boolean(intensity); if(intensity) $(id).value=''; }
    const fcr=item.feed_conversion_ratio;
    for(const id of ['aq-fcr-low','aq-fcr-high']){ $(id).disabled=Boolean(fcr); if(fcr) $(id).value=''; }
    $('aq-source-card').innerHTML=`<strong>${esc(item.name)}</strong> · ${esc(item.scientific_name || '')}<br>Zone: ${esc(item.zone)} · role: ${esc(item.role)}<br>Annual yield intensity: <code>${esc(JSON.stringify(intensity))}</code><br>Feed conversion ratio: <code>${esc(JSON.stringify(item.feed_conversion_ratio))}</code><br><span class="stale">Technical specification; current site allocation remains UNKNOWN.</span>`;
  };
  const showCrop=()=>{
    const item=crops.find(row=>(row.crop_id||row.id)===$('crop-id').value);
    if(!item){$('crop-source-card').textContent='Choose a crop to see its sourced parameters.';return}
    const uplift=item.yield_increase;
    for(const id of ['crop-uplift-low','crop-uplift-high']){ $(id).disabled=Boolean(uplift); if(uplift) $(id).value=''; }
    $('crop-source-card').innerHTML=`<strong>${esc(item.name)}</strong> · ${esc(item.crop_class || item.class)}<br>Sourced technical yield uplift: <code>${esc(JSON.stringify(item.yield_increase))}</code><br>Confirmed planted at a current site: <strong>${item.confirmed_planted===true?'yes':'no'}</strong><br><span class="stale">A crop specification is not an acreage or opening-harvest claim.</span>`;
  };
  $('aq-species').addEventListener('change',showSpecies);
  $('crop-id').addEventListener('change',showCrop);
}

function scenarioId(prefix,name) {
  const slug=name.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-|-$/g,'').slice(0,70) || 'scenario';
  return `${prefix}:${slug}:${Date.now()}`;
}
function optionalRange(lowId,highId,basisId=null) {
  const low=$(lowId).value.trim(), high=$(highId).value.trim();
  if(!low&&!high) return null;
  if(!low||!high) throw new Error('Both low and high values are required for an assumed range.');
  const value={low,high}; if(basisId) value.basis=$(basisId).value; return value;
}
function displayMetric(value) {
  if(value===null||value===undefined) return 'UNKNOWN';
  if(typeof value==='object' && value.low!==undefined && value.high!==undefined) return `${value.low}–${value.high}${value.unit?' '+value.unit:''}`;
  if(typeof value==='object') return JSON.stringify(value);
  return String(value);
}
function renderProduction(result,title) {
  const derived=result.derived || result.derived_results || result.results || {};
  const metrics=Object.entries(derived).filter(([,value])=>typeof value!=='object'||value===null||value.low!==undefined).slice(0,12);
  $('production-result').hidden=false;
  $('production-result').innerHTML=`<div class="section-head"><div><span class="status preview">Non-canon production plan</span><h3>${esc(title)}</h3></div><div class="actions no-print"><button class="secondary" onclick="saveCurrent()">Save locally</button><button class="secondary" onclick="window.print()">Print</button></div></div><div class="kpis">${metrics.map(([key,value])=>`<div class="kpi"><span>${esc(key.replaceAll('_',' '))}</span><strong>${esc(displayMetric(value))}</strong></div>`).join('')}</div>${provenanceHtml(result)}`;
}
$('aquaculture-form').addEventListener('submit',async event=>{
  event.preventDefault(); $('production-error').innerHTML='';
  try {
    const name=$('aq-name').value.trim(); if(!name) throw new Error('Scenario name is required.');
    const request={scenario_id:scenarioId('aquaculture',name),species_id:$('aq-species').value,capacity:numberValue('aq-capacity'),capacity_basis:$('aq-basis').value,planned_liveweight_output_lb:numberValue('aq-output'),opening_feed_lb:numberValue('aq-opening-feed'),feed_receipts_lb:numberValue('aq-feed-receipts')};
    if(!request.species_id) throw new Error('Choose one of the sourced species.');
    const intensity=optionalRange('aq-yield-low','aq-yield-high','aq-yield-basis'); if(intensity) request.assumed_annual_yield_lb_per_1000_unit=intensity;
    const fcr=optionalRange('aq-fcr-low','aq-fcr-high'); if(fcr) request.assumed_feed_conversion_ratio=fcr;
    const result=await api('/api/production/aquaculture/preview',{method:'POST',body:JSON.stringify(request)});
    currentRequest=request; currentResult=result; currentKind='aquaculture_plan'; renderProduction(result,name);
  } catch(error){ $('production-error').innerHTML=`<p class="error">${esc(error.message)}</p>`; }
});
$('crop-form').addEventListener('submit',async event=>{
  event.preventDefault(); $('production-error').innerHTML='';
  try {
    const name=$('crop-name').value.trim(); if(!name) throw new Error('Scenario name is required.');
    const request={scenario_id:scenarioId('crop',name),crop_id:$('crop-id').value,baseline_yield_tons:numberValue('crop-baseline'),baseline_fertilizer_tons:numberValue('crop-fertilizer'),opening_food_tons:numberValue('crop-opening'),food_receipts_tons:numberValue('crop-receipts'),planned_consumption_tons:numberValue('crop-consumption')};
    if(!request.crop_id) throw new Error('Choose one of the sourced crop entries.');
    const uplift=optionalRange('crop-uplift-low','crop-uplift-high'); if(uplift) request.assumed_yield_increase=uplift;
    const result=await api('/api/production/crop/preview',{method:'POST',body:JSON.stringify(request)});
    currentRequest=request; currentResult=result; currentKind='crop_plan'; renderProduction(result,name);
  } catch(error){ $('production-error').innerHTML=`<p class="error">${esc(error.message)}</p>`; }
});

function numberValue(id) { const value=$(id).value.trim(); if(value==='') throw new Error(`${$(id).closest('label').firstChild.textContent.trim()} is unresolved.`); return value; }
function optionalValue(id,asInteger=false) { const value=$(id).value.trim(); return value===''?null:(asInteger?Number(value):value); }
function loadLowCase() {
  const values = { 'ls-name':'Illustrative low case','ls-target':'1200','ls-supplier':'1200','ls-opening':'0','ls-demand':'300','ls-dispatch':'1200','ls-route-capacity':'900','ls-trips':'1','ls-travel':'1','ls-loss':'2','ls-storage':'1200','ls-price':'54.1667','ls-funding':'65000' };
  Object.entries(values).forEach(([id,value])=>$(id).value=value);
}
$('load-low').addEventListener('click',loadLowCase);

function longsaddleRequest() {
  return {
    scenario_id:`longsaddle-${Date.now()}`,
    scenario_name:$('ls-name').value.trim(),
    target_tons:optionalValue('ls-target'), supplier_stock_tons:optionalValue('ls-supplier'),
    opening_stock_tons:optionalValue('ls-opening'), demand_tons:optionalValue('ls-demand'),
    dispatch_tons:optionalValue('ls-dispatch'), route_capacity_tons_per_trip:optionalValue('ls-route-capacity'),
    trips:optionalValue('ls-trips',true), travel_periods:optionalValue('ls-travel',true),
    transport_loss_percent:optionalValue('ls-loss'), storage_capacity_tons:optionalValue('ls-storage'),
    price_gp_per_ton:optionalValue('ls-price'), funding_gp:optionalValue('ls-funding')
  };
}
$('longsaddle-form').addEventListener('submit',async event=>{
  event.preventDefault(); $('longsaddle-error').innerHTML='';
  try {
    const request=longsaddleRequest(); const result=await api('/api/longsaddle/preview',{method:'POST',body:JSON.stringify(request)});
    currentRequest=request; currentResult=result; currentKind='longsaddle_plan'; renderLongsaddle(result);
  } catch(error) { $('longsaddle-error').innerHTML=`<p class="error">${esc(error.message)}</p>`; }
});
function derivedOf(result) { return result.derived || result.results || result.outcome || result; }
function readAny(obj, keys, fallback='UNKNOWN') { for(const key of keys){ if(obj && obj[key]!==undefined && obj[key]!==null) return obj[key]; } return fallback; }
function renderLongsaddle(result) {
  const d=derivedOf(result); const status=String(readAny(d,['status','objective_status','assessment'],'at risk')).toLowerCase();
  const klass=status.includes('met')?'met':status.includes('fail')?'failed':'risk';
  const metrics=[
    ['Requested',readAny(d,['target_tons','requested_tons'])],['Dispatched',readAny(d,['dispatched_tons','dispatch_tons'])],['Capacity gap',readAny(d,['capacity_gap_tons'])],
    ['Lost',readAny(d,['lost_tons','transport_loss_tons'])],['Delivered',readAny(d,['delivered_tons'])],['Consumed',readAny(d,['consumed_tons','demand_fulfilled_tons'])],
    ['Closing stock',readAny(d,['closing_stock_tons','closing_tons'])],['Funding gap',readAny(d,['funding_gap_gp'])],['Conservation residual',readAny(d,['conservation_residual_tons','conservation_residual'])]
  ];
  $('longsaddle-result').hidden=false;
  $('longsaddle-result').innerHTML=`<div class="section-head"><div><span class="status ${klass}">${esc(status)}</span><h3>${esc(currentRequest?.scenario_name || 'Longsaddle plan')}</h3></div><div class="actions no-print"><button class="secondary" onclick="saveCurrent()">Save locally</button><button class="secondary" onclick="window.print()">Print</button></div></div><div class="kpis">${metrics.map(([l,v])=>`<div class="kpi"><span>${esc(l)}</span><strong>${esc(l.includes('Funding')?money(v):qty(v,'t'))}</strong></div>`).join('')}</div>${provenanceHtml(result)}`;
}

function parseFaces(value) {
  const text=value.trim(); if(!text) return null; const faces=text.split(',').map(x=>Number(x.trim()));
  if(faces.length!==3 || faces.some(x=>!Number.isInteger(x)||x<1||x>6)) throw new Error('Each supplied roll must contain exactly three faces from 1 through 6.');
  return faces;
}
function sectorAssumptions(fieldset) {
  const out={}; fieldset.querySelectorAll('[data-key]').forEach(input=>{
    let value=input.value; const key=input.dataset.key;
    if(['vara_active','monopoly','excellent_accounting','rapid_expansion'].includes(key)) value=value==='true';
    if(['revenue_streams','competent_managers'].includes(key)) value=Number(value);
    if(['revenue_faces','expense_faces'].includes(key)) value=parseFaces(value);
    out[key]=value;
  }); return out;
}
$('generate-seed').addEventListener('click',()=>{ const bytes=new Uint32Array(3); crypto.getRandomValues(bytes); $('month-seed').value=`food-preview-${Array.from(bytes).map(x=>x.toString(16)).join('-')}`; });
$('month-form').addEventListener('submit',async event=>{
  event.preventDefault(); $('month-error').innerHTML='';
  try {
    const request={scenario_id:`food-month-${Date.now()}`,month_label:$('month-label').value.trim(),sector_assumptions:{}};
    if(!request.month_label) throw new Error('Month label is required.');
    const supplied={}; let suppliedCount=0;
    document.querySelectorAll('fieldset[data-sector]').forEach(fs=>{ const sector=fs.dataset.sector; const values=sectorAssumptions(fs); supplied[sector]={revenue:values.revenue_faces,expense:values.expense_faces}; suppliedCount += values.revenue_faces?1:0; suppliedCount += values.expense_faces?1:0; delete values.revenue_faces; delete values.expense_faces; request.sector_assumptions[sector]=values; });
    if(suppliedCount===0){ request.seed=$('month-seed').value.trim(); if(!request.seed) throw new Error('Generate or enter a replay seed, or supply all four 3d6 receipts.'); }
    else if(suppliedCount===4){ request.supplied_faces=supplied; }
    else { throw new Error('Supply all four 3d6 receipts or leave all four blank and use a replay seed.'); }
    const result=await api('/api/food-sector/preview',{method:'POST',body:JSON.stringify(request)});
    currentRequest=request; currentResult=result; currentKind='food_sector_month'; renderMonth(result);
  } catch(error) { $('month-error').innerHTML=`<p class="error">${esc(error.message)}</p>`; }
});
function renderMonth(result) {
  const sectors=result.sectors || result.sector_results || derivedOf(result).sectors || {};
  const cards=Object.entries(sectors).map(([name,s])=>{
    const rev=s.revenue_roll || s.rolls?.revenue || {}; const exp=s.expense_roll || s.rolls?.expense || {};
    const receipt=(label,roll)=>`<details open><summary>${esc(label)} · ${esc(roll.outcome)} · factor ${esc(roll.factor)}</summary><p><strong>${esc(roll.skill)}</strong> base ${esc(roll.base_target)} ${esc((roll.faces||[]).join(' + '))} = ${esc(roll.total)} · modifiers ${esc(roll.modifier_total)} · effective target ${esc(roll.effective_target ?? roll.target)} · margin ${esc(roll.margin)}</p><ul>${(roll.modifiers||[]).map(item=>`<li>${esc(item.label)}: ${Number(item.value)>=0?'+':''}${esc(item.value)}</li>`).join('')}</ul><p>${esc(roll.factor_effect)}</p></details>`;
    const entities=s.entities || [];
    const entityTable=entities.length?`<div class="table-wrap"><table><thead><tr><th>Entity</th><th class="num">Source revenue</th><th class="num">Preview revenue</th><th class="num">Source cost</th><th class="num">Preview cost</th><th class="num">Preview net</th></tr></thead><tbody>${entities.map(entity=>`<tr><td>${esc(entity.name)}</td><td class="num">${esc(money(entity.monthly_revenue_gp))}</td><td class="num">${esc(money(entity.preview_revenue_gp))}</td><td class="num">${esc(money(entity.monthly_cost_gp))}</td><td class="num">${esc(money(entity.preview_cost_gp))}</td><td class="num">${esc(money(entity.preview_net_gp))}</td></tr>`).join('')}</tbody></table></div>`:'';
    return `<article class="panel"><p class="eyebrow">${esc(name)}</p><h3>${esc(money(s.proposed_net_gp ?? s.net_gp ?? s.preview?.preview_net_gp ?? s.totals?.proposed_net_gp))} proposed net</h3>${receipt('Revenue roll',rev)}${receipt('Expense roll',exp)}${entityTable}</article>`;
  }).join('');
  $('month-result').hidden=false; $('month-result').innerHTML=`<div class="section-head"><div><span class="status preview">Non-canon preview</span><h3>${esc(currentRequest?.month_label)}</h3></div><div class="actions no-print"><button class="secondary" onclick="saveCurrent()">Save locally</button><button class="secondary" onclick="window.print()">Print</button></div></div><div class="grid">${cards || `<pre>${esc(JSON.stringify(result,null,2))}</pre>`}</div>${provenanceHtml(result)}`;
}
function provenanceHtml(result) {
  const brief=result.decision_brief || {};
  const sections=[['Source',brief.Source || result.source || result.sources || {} ,'source'],['Assumption',brief.Assumption || result.assumptions || currentRequest || {},'assumed'],['Derived',brief.Derived || result.derived || result.results || {},'derived'],['Unknown',brief.Unknown || result.unknowns || result.unresolved || [],'unknown']];
  return `<div class="provenance">${sections.map(([title,value,klass])=>`<article class="prov ${klass}"><h4>${title}</h4><pre>${esc(JSON.stringify(value,null,2))}</pre></article>`).join('')}</div>`;
}

async function saveCurrent() {
  if(!currentResult) return;
  const id=currentRequest.scenario_id || `${currentKind}-${Date.now()}`;
  try { await api('/api/scenarios',{method:'POST',body:JSON.stringify({scenario_id:id,kind:currentKind,request:currentRequest,result:currentResult})}); alert(`Saved ${id}`); }
  catch(error){ alert(`Save failed: ${error.message}`); }
}
window.saveCurrent=saveCurrent;
async function refreshSaved() {
  try {
    const payload=await api('/api/scenarios'); const items=Array.isArray(payload)?payload:(payload.scenarios||payload.items||[]);
    $('saved-list').innerHTML=items.length?items.map(item=>{ const id=item.scenario_id||item.id; return `<article class="saved"><div><strong>${esc(id)}</strong><br><span>${esc(item.kind||item.artifact_kind||'scenario')} · ${esc(item.created_at||'saved locally')}</span></div><div class="actions no-print"><button class="secondary" onclick="openSaved('${esc(id)}')">Open</button><button class="secondary" onclick="exportSaved('${esc(id)}')">Export</button><label><span>Compare</span><input type="checkbox" class="compare-box" value="${esc(id)}"></label></div></article>`;}).join('')+'<div class="actions no-print"><button class="secondary" onclick="compareSelected()">Compare selected</button></div>':'<p class="notice">No locally saved scenarios yet.</p>';
  } catch(error){ $('saved-list').innerHTML=`<p class="error">${esc(error.message)}</p>`; }
}
$('refresh-saved').addEventListener('click',refreshSaved);
async function openSaved(id) {
  try { const item=await api(`/api/scenarios/${encodeURIComponent(id)}`); currentResult=item.result||item.payload?.result||item; currentRequest=item.request||item.payload?.request||{}; currentKind=item.kind||item.artifact_kind; if(String(currentKind).includes('longsaddle')){showView('longsaddle');renderLongsaddle(currentResult)}else if(String(currentKind).includes('aquaculture')||String(currentKind).includes('crop')){showView('production');renderProduction(currentResult,currentRequest.scenario_id||id)}else{showView('month');renderMonth(currentResult)} } catch(error){alert(error.message)}
}
function exportSaved(id){ window.open(`/api/scenarios/${encodeURIComponent(id)}/export?format=html`,'_blank','noopener'); }
function comparisonValues(item){ const result=item.result||item; return result.derived || result.preview_totals || result.results || result.sectors || result; }
function flattenValues(value,prefix='',out={}){ if(value && typeof value==='object' && !Array.isArray(value)){ for(const [key,item] of Object.entries(value)){ const path=prefix?`${prefix}.${key}`:key; if(item && typeof item==='object' && !Array.isArray(item) && item.low===undefined) flattenValues(item,path,out); else out[path]=displayMetric(item); } } return out; }
async function compareSelected(){
  const ids=Array.from(document.querySelectorAll('.compare-box:checked')).map(x=>x.value); if(ids.length!==2){alert('Select exactly two scenarios.');return}
  try{
    const [a,b]=await Promise.all(ids.map(id=>api(`/api/scenarios/${encodeURIComponent(id)}`))); const av=flattenValues(comparisonValues(a)), bv=flattenValues(comparisonValues(b)); const keys=Array.from(new Set([...Object.keys(av),...Object.keys(bv)])).sort();
    $('compare-result').hidden=false; $('compare-result').innerHTML=`<h3>Decision comparison</h3><div class="table-wrap"><table><thead><tr><th>Metric</th><th>${esc(ids[0])}</th><th>${esc(ids[1])}</th><th>Changed?</th></tr></thead><tbody>${keys.map(key=>`<tr><td>${esc(key)}</td><td>${esc(av[key]??'—')}</td><td>${esc(bv[key]??'—')}</td><td>${av[key]===bv[key]?'same':'changed'}</td></tr>`).join('')}</tbody></table></div>`;
  }catch(error){alert(error.message)}
}
window.openSaved=openSaved; window.exportSaved=exportSaved; window.compareSelected=compareSelected;

async function start() {
  try { bootstrap=await api('/api/bootstrap'); renderBootstrap(); const initial=location.hash.slice(1); if(['dashboard','longsaddle','production','month','rulings','evidence'].includes(initial)) showView(initial); }
  catch(error){ $('business-rows').innerHTML=`<tr><td colspan="7"><p class="error">The operator server could not load its source-bound state: ${esc(error.message)}</p></td></tr>`; }
}
start();
</script>
</body>
</html>'''
