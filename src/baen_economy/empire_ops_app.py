"""Mobile-first browser UI for the Baen Empire economy operator."""

APP_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Baen Economy Engine</title>
<style>
:root{
  color-scheme:dark;
  --bg:#091019;--panel:#111a24;--panel2:#162332;--line:#28394a;
  --text:#edf3f8;--muted:#9eafbe;--accent:#79b7ff;--accent2:#2b6fb1;
  --good:#78d6a5;--warn:#f0c36d;--bad:#ef8181;--chip:#1c2b3a
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:linear-gradient(180deg,#08101a,#0b1118 34rem);color:var(--text);font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
button,input,select{font:inherit}
button{cursor:pointer}
header{max-width:1280px;margin:auto;padding:22px 16px 12px}
h1{font-size:29px;margin:0 0 4px} h2{font-size:19px;margin:0 0 12px} h3{font-size:15px;margin:0}
.sub{color:var(--muted);margin:0}
.badges{display:flex;gap:7px;flex-wrap:wrap;margin-top:12px}
.badge{border:1px solid var(--line);background:var(--chip);border-radius:999px;padding:5px 9px;font-size:12px}
.good{color:var(--good)}.warn{color:var(--warn)}.bad{color:var(--bad)}
nav{position:sticky;top:0;z-index:20;background:rgba(9,16,25,.94);backdrop-filter:blur(12px);border-top:1px solid #172433;border-bottom:1px solid var(--line)}
.nav-inner{max-width:1280px;margin:auto;display:flex;overflow:auto;padding:8px 12px;gap:7px}
.nav-btn{width:auto;white-space:nowrap;border:1px solid var(--line);background:#101923;color:var(--muted);border-radius:9px;padding:9px 12px}
.nav-btn.active{background:#17304d;color:var(--text);border-color:#3d6f9d}
main{max-width:1280px;margin:auto;padding:14px 16px 50px}
.view{display:none}.view.active{display:block}
.grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:12px;margin-bottom:12px}
.card{grid-column:span 3;background:rgba(17,26,36,.97);border:1px solid var(--line);border-radius:14px;padding:15px;box-shadow:0 8px 28px rgba(0,0,0,.16)}
.card.half{grid-column:span 6}.card.full{grid-column:1/-1}
.hero{background:linear-gradient(145deg,#132a43,#111a24 60%);border-color:#355d83;padding:19px}
.eyebrow{font-size:12px;text-transform:uppercase;letter-spacing:.09em;color:var(--accent)}
.hero-title{font-size:24px;font-weight:750;margin:3px 0 7px}
.small{font-size:12px;color:var(--muted)}.muted{color:var(--muted)}
.metric{font-size:26px;font-weight:760;margin:3px 0}
.big-action{display:block;width:100%;border:1px solid #4a87bf;background:#1c5c95;color:white;border-radius:11px;padding:14px 16px;font-weight:760;font-size:16px}
.secondary{border:1px solid var(--line);background:#121d28;color:var(--text);border-radius:9px;padding:10px 12px}
.ghost{border:1px solid transparent;background:transparent;color:var(--accent);padding:8px}
.action-row{display:flex;gap:9px;flex-wrap:wrap;margin-top:12px}
.action-row>*{flex:1;min-width:135px}
.quick-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:9px;margin-top:14px}
.quick{border:1px solid var(--line);background:#121d28;color:var(--text);border-radius:11px;padding:13px;text-align:left}
.quick strong{display:block;margin-bottom:3px}.quick span{font-size:12px;color:var(--muted)}
.controls{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
label{display:block;color:var(--muted);font-size:12px;margin-bottom:5px}
input,select{width:100%;border:1px solid var(--line);background:#0d151e;color:var(--text);border-radius:8px;padding:10px}
.checkbox{display:flex;align-items:center;gap:8px;min-height:40px}.checkbox input{width:auto}
details{border:1px solid var(--line);border-radius:11px;background:#0f1822;margin:8px 0;overflow:hidden}
summary{cursor:pointer;list-style:none;padding:13px 14px;font-weight:650;display:flex;justify-content:space-between;gap:12px;align-items:center}
summary::-webkit-details-marker{display:none}
summary:after{content:"▾";color:var(--accent)}
details[open] summary:after{content:"▴"}
.detail-body{border-top:1px solid var(--line);padding:12px 14px}
.status{font-size:12px;border-radius:999px;padding:3px 7px;border:1px solid var(--line);font-weight:500}
.status.good{color:var(--good)}.status.warn{color:var(--warn)}.status.bad{color:var(--bad)}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:8px 7px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600}
.table-wrap{overflow:auto}
.statusline{min-height:21px;margin-top:9px;color:var(--muted)}
.goodtext{color:var(--good)}.warntext{color:var(--warn)}.badtext{color:var(--bad)}
pre{white-space:pre-wrap;word-break:break-word;background:#090e14;border:1px solid var(--line);border-radius:10px;padding:14px;max-height:650px;overflow:auto;color:#dbe6ef}
.saved-card{border:1px solid var(--line);border-radius:11px;padding:12px;margin:8px 0;background:#0f1822}
.saved-head{display:flex;justify-content:space-between;gap:10px}
.link-row{display:flex;gap:12px;flex-wrap:wrap;margin-top:8px}.link-row a{color:var(--accent)}
.hidden{display:none!important}
.advanced{margin-top:12px}
.notice{border-left:3px solid var(--warn);background:#191a17;padding:10px 12px;border-radius:5px;color:#d8d0b9}
#business-empty{padding:20px;text-align:center;color:var(--muted)}
@media(max-width:800px){
  .card,.card.half{grid-column:span 6}.controls{grid-template-columns:1fr 1fr}.quick-grid{grid-template-columns:1fr}
}
@media(max-width:560px){
  header{padding:18px 13px 10px}main{padding:12px 13px 40px}
  .card,.card.half{grid-column:1/-1}.controls{grid-template-columns:1fr}
  .metric{font-size:23px}.hero-title{font-size:21px}.nav-inner{padding-left:9px;padding-right:9px}
}
</style>
</head>
<body>
<header>
  <h1>Baen Economy Engine</h1>
  <p class="sub">Whole-Empire monthly economy operator</p>
  <div class="badges">
    <span class="badge warn" id="canon-badge">Loading campaign gate…</span>
    <span class="badge good">No Notion writes</span>
    <span class="badge good">No canonical postings</span>
  </div>
</header>

<nav>
  <div class="nav-inner">
    <button class="nav-btn active" data-view="home">Home</button>
    <button class="nav-btn" data-view="businesses">Businesses</button>
    <button class="nav-btn" data-view="economy">Economy</button>\n    <button class="nav-btn" data-view="close">Empire Close</button>
    <button class="nav-btn" data-view="sources">Sources & blockers</button>
    <button class="nav-btn" data-view="runs">Saved runs</button>
  </div>
</nav>

<main>
<section class="view active" id="view-home">
  <div class="grid">
    <div class="card full hero">
      <div class="eyebrow">Start here</div>
      <div class="hero-title">Run the current Hammer 1495 economy review</div>
      <p class="muted">Uses the current Day 7 Hammer 1495 source authority. You do not need to type a date or replay seed.</p>
      <div class="action-row">
        <button class="big-action" id="run-current">Run current Hammer 1495</button>
        <button class="secondary" id="roll-again">Roll another preview</button>
      </div>
      <div class="statusline" id="run-status">Ready.</div>

      <details class="advanced">
        <summary>Advanced preview options <span class="small">optional</span></summary>
        <div class="detail-body">
          <div class="controls">
            <div>
              <label for="market">Market ruling</label>
              <select id="market">
                <option value="unknown">Unknown — no modifier</option>
                <option value="stable">Stable</option>
                <option value="boom">Boom</option>
                <option value="recession">Recession</option>
              </select>
            </div>
            <div>
              <label>Optional ruling</label>
              <div class="checkbox"><input type="checkbox" id="vara"><span>Vara active</span></div>
            </div>
            <div>
              <label for="month-select">Review month</label>
              <select id="month-select"></select>
            </div>
            <div>
              <label for="year-select">Year DR</label>
              <input id="year-select" inputmode="numeric" type="number" value="1495" min="1000" max="2000">
            </div>
          </div>
          <div class="controls" style="margin-top:10px">
            <div>
              <label for="day-select">Authority day label</label>
              <select id="day-select"></select>
            </div>
            <div style="grid-column:span 3">
              <label for="seed">Replay seed</label>
              <input id="seed" value="hammer-1495-app-preview-1">
            </div>
          </div>
          <p class="small">Changing the review label does not change the underlying source authority. Current actual source authority remains Day 7 Hammer 1495 DR.</p>
        </div>
      </details>
    </div>
  </div>

  <div class="grid hidden" id="preview-summary">
    <button class="card quick-card" data-view="businesses" style="text-align:left;color:inherit">
      <div class="small">Admitted businesses</div><div class="metric" id="p-admitted">—</div><div class="small">Tap to inspect business results →</div>
    </button>
    <button class="card quick-card" data-view="businesses" style="text-align:left;color:inherit">
      <div class="small">Baseline revenue</div><div class="metric" id="p-baseline">—</div><div class="small">gp / month →</div>
    </button>
    <button class="card quick-card" data-view="businesses" style="text-align:left;color:inherit">
      <div class="small">Rolled revenue</div><div class="metric" id="p-revenue">—</div><div class="small">Tap for sector rolls →</div>
    </button>
    <button class="card quick-card" data-view="businesses" style="text-align:left;color:inherit">
      <div class="small">Proposed net range</div><div class="metric" id="p-net">—</div><div class="small">Preview only →</div>
    </button>
  </div>

  <div class="grid">
    <div class="card full">
      <h2>Open a part of the economy</h2>
      <div class="quick-grid">
        <button class="quick" data-view="businesses"><strong>Businesses</strong><span>Sector rolls, expenses, complications, Vara briefing</span></button>
        <button class="quick" data-view="economy"><strong>Whole economy</strong><span>Population, production, logistics, banking, capital, contracts</span></button>
        <button class="quick" data-view="sources"><strong>Sources & blockers</strong><span>What is known, unresolved, and which upstream products can run</span></button>
        <button class="quick" data-view="runs"><strong>Saved runs</strong><span>Reopen, compare, and export previous monthly previews</span></button>
        <button class="quick" data-view="economy" data-focus="finance_banking"><strong>Finance & banking</strong><span>Loan portfolio, missing books, treasury constraints</span></button>
        <button class="quick" data-view="economy" data-focus="infrastructure_logistics"><strong>Trade & logistics</strong><span>Arterial routes, freight evidence, OpenTTD boundary</span></button>
      </div>
    </div>
  </div>
</section>

<section class="view" id="view-businesses">
  <div class="grid">
    <div class="card full">
      <div style="display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap">
        <div><div class="eyebrow">Monthly business phase</div><h2 style="margin:2px 0 0">Business results</h2></div>
        <button class="secondary" id="run-from-businesses" style="width:auto">Run current month</button>
      </div>
      <div id="business-empty">Run the current month from Home to populate business results.</div>
      <div class="hidden" id="business-results">
        <div id="sector-results"></div>
        <details open><summary>Expense control</summary><div class="detail-body" id="expense-result"></div></details>
        <details><summary>Entity complications</summary><div class="detail-body" id="complication-results"></div></details>
        <details><summary>Vara briefing</summary><div class="detail-body" id="vara-results"></div></details>
      </div>
    </div>
  </div>
</section>

<section class="view" id="view-economy">
  <div class="grid">
    <div class="card full">
      <div class="eyebrow">Whole-Empire systems</div>
      <h2>Economy</h2>
      <p class="muted">Tap any system to inspect what is mapped, what can execute, and what remains blocked.</p>
      <div id="system-lanes">Loading…</div>
    </div>
    <div class="card full">
      <h2>Corridor land, internal transport & NCF lending</h2>
      <div id="corridor-finance">Loading…</div>
    </div>
    <div class="card full">
      <h2>Source → product domains</h2>
      <div id="domains">Loading…</div>
    </div>
    <div class="card full">
      <h2>Known physical/source state</h2>
      <div id="known-state">Loading…</div>
    </div>
  </div>
</section>

<section class="view" id="view-sources">
  <div class="grid">
    <button class="card" data-source-jump="collections" style="text-align:left;color:inherit">
      <div class="small">Current-live source records</div><div class="metric" id="live-count">—</div><div class="small">Tap for collections ↓</div>
    </button>
    <button class="card" data-source-jump="coverage" style="text-align:left;color:inherit">
      <div class="small">Retained core records</div><div class="metric" id="retained-count">—</div><div class="small">Tap for coverage ↓</div>
    </button>
    <button class="card" data-source-jump="coverage" style="text-align:left;color:inherit">
      <div class="small">Source-mapped records</div><div class="metric" id="mapped-count">—</div><div class="small">Semantic overlay ↓</div>
    </button>
    <button class="card" data-source-jump="blockers" style="text-align:left;color:inherit">
      <div class="small">SIMULATED records</div><div class="metric" id="sim-count">—</div><div class="small">Canonical gate remains closed ↓</div>
    </button>

    <div class="card full" id="collections"><h2>Live source collections</h2><div id="collection-list">Loading…</div></div>
    <div class="card full" id="coverage"><h2>Coverage overlay</h2><div id="coverage-detail">Loading…</div></div>
    <div class="card full" id="blockers"><h2>Current unresolved gates</h2><div id="unresolved">Loading…</div></div>
    <div class="card full"><h2>Upstream products</h2><div id="products">Loading…</div></div>
  </div>
</section>


<section class="view" id="view-close">
  <div class="grid">
    <div class="card full hero">
      <div class="eyebrow">Evidence-first recovery</div>
      <div class="hero-title">Day 7 Hammer Empire Close</div>
      <p class="muted">This does not advance time. It separates routine recovery from decisions that actually require you.</p>
      <div class="quick-grid">
        <div class="quick"><strong id="close-accepted">—</strong><span>accepted sourced/calculated values</span></div>
        <div class="quick"><strong id="close-unresolved">—</strong><span>remaining unresolved items</span></div>
        <div class="quick"><strong id="close-user-actions">—</strong><span>decisions that actually require you</span></div>
      </div>
    </div>
    <div class="card full">
      <h2>Execution phases</h2>
      <div id="close-phases">Loading…</div>
    </div>
    <div class="card full">
      <h2>What happens next</h2>
      <p class="muted">Routine recovery proceeds without asking you for numbers. User decisions are separated below.</p>
      <div id="close-actions">Loading…</div>
    </div>
    <div class="card full">
      <h2>Recovered lanes</h2>
      <div id="close-lanes">Loading…</div>
    </div>
  </div>
</section>

<section class="view" id="view-runs">
  <div class="grid">
    <div class="card full">
      <div class="eyebrow">Local preview history</div>
      <h2>Saved monthly previews</h2>
      <p class="muted">After a run, tap <strong>Save this preview</strong>. IDs and labels are generated automatically.</p>
      <div class="action-row">
        <button class="big-action" id="save-current">Save this preview</button>
        <button class="secondary" id="compare-latest">Compare latest two</button>
      </div>
      <div class="statusline" id="save-status">Nothing is saved until you tap Save.</div>
      <div id="saved-runs"></div>
      <pre id="comparison" class="hidden"></pre>
    </div>
  </div>
</section>

<section class="grid hidden" id="report-wrap">
  <div class="card full">
    <div style="display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap">
      <h2 style="margin:0">Full preview report</h2>
      <div class="action-row" style="margin:0">
        <button class="secondary" id="go-businesses">Business view</button>
        <button class="secondary" id="download">Download Markdown</button>
      </div>
    </div>
    <pre id="report"></pre>
  </div>
</section>
</main>

<script>
(function(){
"use strict";
var latestReport="", latestRequest=null, latestResult=null, savedRuns=[], previewCounter=1, bootstrap=null;
var MONTHS=["Hammer","Alturiak","Ches","Tarsakh","Mirtul","Kythorn","Flamerule","Eleasis","Eleint","Marpenoth","Uktar","Nightal"];
function el(id){return document.getElementById(id)}
function esc(v){return String(v==null?"":v).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]})}
function num(v){return new Intl.NumberFormat("en-US").format(Number(v||0))}
function money(v){var n=Number(v);return Number.isFinite(n)?new Intl.NumberFormat("en-US",{maximumFractionDigits:2}).format(n):String(v)}
function slug(v){return String(v).toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"").slice(0,55)}
function statusType(s){s=String(s||"");if(/USED|IMPLEMENTED|SOURCE_MAPPED|SOURCE_BACKED|COMPLETE/.test(s))return"good";if(/BLOCK|UNRESOLVED|UNAVAILABLE|MISSING|CONFLICT|PARTIAL/.test(s))return"warn";return""}
function authorityLabel(){var m=el("month-select").value,y=el("year-select").value,d=el("day-select").value;return "Day "+d+" "+m+" "+y+" DR — monthly preview"}
function autoSeed(){return slug(el("month-select").value+"-"+el("year-select").value+"-preview-"+previewCounter)}

function showView(name){
  document.querySelectorAll(".view").forEach(function(v){v.classList.toggle("active",v.id==="view-"+name)});
  document.querySelectorAll(".nav-btn").forEach(function(b){b.classList.toggle("active",b.dataset.view===name)});
  window.scrollTo({top:0,behavior:"smooth"});
}
document.addEventListener("click",function(e){
  var b=e.target.closest("[data-view]");
  if(b){showView(b.dataset.view);var focus=b.dataset.focus;if(focus){setTimeout(function(){var x=document.getElementById("domain-"+focus);if(x){x.open=true;x.scrollIntoView({behavior:"smooth",block:"start"})}},120)}}
  var j=e.target.closest("[data-source-jump]");
  if(j){var x=document.getElementById(j.dataset.sourceJump);if(x)x.scrollIntoView({behavior:"smooth"})}
});

function initDateControls(){
  el("month-select").innerHTML=MONTHS.map(function(m){return '<option '+(m==="Hammer"?"selected":"")+'>'+m+'</option>'}).join("");
  var days=[];for(var i=1;i<=30;i++)days.push('<option '+(i===7?"selected":"")+'>'+i+'</option>');el("day-select").innerHTML=days.join("");
}

function renderBootstrap(data){
  bootstrap=data;
  var s=data.source_status,c=data.semantic_coverage;
  el("live-count").textContent=num(s.current_live_records);el("retained-count").textContent=num(s.retained_core_records);
  el("mapped-count").textContent=num(c.mapped_record_count);el("sim-count").textContent=num(c.simulated_after_overlay);
  el("canon-badge").textContent="Canonical month: "+s.canonical_month+" · "+(s.campaign_boundary||"Day 7 Hammer 1495 DR");

  var cols=(s.collections||[]).map(function(r){
    return '<details><summary><span>'+esc(r.key||"collection")+'</span><span class="status '+(r.complete?"good":"warn")+'">'+num(r.current_live_rows)+' live</span></summary><div class="detail-body">Retained captured rows: <strong>'+num(r.retained_captured_rows)+'</strong><br>Enumeration complete: <strong>'+(r.complete?"YES":"NO")+'</strong></div></details>'
  }).join("");
  el("collection-list").innerHTML=cols||'<p class="muted">No collection rows returned.</p>';

  el("coverage-detail").innerHTML=
    '<div class="quick-grid"><div class="quick"><strong>'+num(c.mapped_record_count)+' source-mapped</strong><span>'+num(c.moved_from_unknown)+' moved from UNKNOWN</span></div>'+
    '<div class="quick"><strong>'+num(c.unknown_after_overlay)+' UNKNOWN</strong><span>after semantic overlay</span></div>'+
    '<div class="quick"><strong>'+num(c.simulated_after_overlay)+' SIMULATED</strong><span>canonical simulation coverage</span></div></div>';

  var cf=data.corridor_finance||{}, land=cf.land_bank||{}, tr=cf.internal_transport||{}, ln=cf.ncf_lending||{};
  el("corridor-finance").innerHTML=
    '<details open><summary>NCF arterial land bank <span class="status warn">USER-RULED</span></summary><div class="detail-body"><strong>8 miles each side</strong> of the arterial centerline; NCF / controlled shells / subsidiaries are beneficial owners.<br><br>At the sourced <strong>500+ operational network-mile</strong> lower bound, the gross geometric corridor is at least <strong>'+num(land.gross_strip_acres_at_500_mile_floor||0)+' gross strip-acres</strong> before route-overlap subtraction. This is not a unique-acre lower bound and not yet the titled-acre ledger. The older 1,200+ acre Arterial figure is retained as the directly-booked/legacy parcel figure pending consolidation.<br><br><strong>ESAMT:</strong> Shi’van’s progressive buy-in to Arterial and Hunding interests is confirmed. Day-7 percentages, installments and rights remain unresolved. NCF manages the trust; that does not make its investments NCF-owned or transfer corridor land title.</div></details>'+
    '<details><summary>Internal vehicle capacity <span class="status good">INTERNAL ONLY</span></summary><div class="detail-body">Earthmover road/Jeep configuration: <strong>'+(tr.earthmover_jeep_road_configuration?"YES":"NO")+'</strong>. External sales: <strong>'+(tr.external_sales?"YES":"NO")+'</strong>.<br>Stonebearer payload: <strong>'+esc(tr.stonebearer_payload_tons||"—")+' short tons</strong>. Four vehicles at the comparison duty cycle give a <strong>'+esc(tr.brickworks_short_haul_capacity_tons_per_day_min||"—")+'–'+esc(tr.brickworks_short_haul_capacity_tons_per_day_max||"—")+' tons/day benchmark</strong>. Actual assignments include differing trip counts and a backup unit; this is not spare freight capacity. Ratified empire fleet: <strong>'+esc(tr.ratified_empire_fleet.Stonebearer)+' Stonebearers, '+esc(tr.ratified_empire_fleet.Groundshaper)+' Groundshapers, '+esc(tr.ratified_empire_fleet.Ironmaw)+' Ironmaws</strong>. Route capacity still requires assignments and road-mode specifications.<br>The separate Roadrider programme is a later design. Its speed and build rate do not define the current earthmovers.</div></details>'+
    '<details><summary>NCF lending <span class="status warn">PARTIAL BOOK</span></summary><div class="detail-body">Current active loan principal: <strong>'+money(ln.active_loan_principal_gp||0)+' gp</strong>. Current aggregate NCF revenue: <strong>'+money(ln.monthly_ncf_revenue_gp||0)+' gp/month</strong>. Existing rate anchors include <strong>8%</strong> secured facility lending and <strong>12%</strong> voyage finance. The engine deliberately does not infer an average portfolio APR or reserve ratio from these figures.</div></details>';

  var ec=data.empire_close||{};
  el("close-accepted").textContent=num(ec.accepted_values||0);
  el("close-unresolved").textContent=num(ec.unresolved_items||0);
  el("close-user-actions").textContent=num((ec.user_actions||[]).length);
  el("close-phases").innerHTML=(ec.phase_progress||[]).map(function(p){
    var cls=p.status==="IN_PROGRESS"?"warn":(p.status==="COMPLETE"?"good":"");
    return '<details '+(p.status==="IN_PROGRESS"?"open":"")+'><summary><span>Phase '+esc(p.id)+' — '+esc(p.name)+'</span><span class="status '+cls+'">'+esc(p.status)+'</span></summary><div class="detail-body"><strong>Exit:</strong> '+esc(p.exit)+'</div></details>'
  }).join("");
  var ua=ec.user_actions||[],ra=ec.routine_actions||[];
  var userHtml=ua.length?'<h3>Requires Chad</h3>'+ua.map(function(a){return '<div class="notice" style="margin:8px 0"><strong>'+esc(a.label)+'</strong><br><span class="small">'+esc(a.decision||a.method)+'</span><br><span class="small">Unlocks: '+esc((a.unlocks||[]).join(", "))+'</span></div>'}).join(""):'<p class="goodtext">No user decisions required.</p>';
  var routineHtml='<h3 style="margin-top:14px">Routine execution — no user input</h3>'+ra.map(function(a){return '<details><summary><span>'+esc(a.label)+'</span><span class="status good">'+esc(a.method)+'</span></summary><div class="detail-body">Unlocks: '+esc((a.unlocks||[]).join(", "))+(a.note?'<br>'+esc(a.note):'')+'</div></details>'}).join("");
  el("close-actions").innerHTML=userHtml+routineHtml;
  var laneHtml2="";
  Object.keys(ec.lanes||{}).forEach(function(k){
    var l=ec.lanes[k]||{},facts=(l.facts||[]).length+(l.calculated||[]).length,un=(l.unresolved||[]).length,co=(l.conflicts||[]).length;
    laneHtml2+='<details><summary><span>'+esc(k.replace(/_/g," "))+'</span><span class="status '+(un||co?"warn":"good")+'">'+facts+' accepted · '+un+' unresolved'+(co?' · '+co+' conflict':'')+'</span></summary><div class="detail-body">'+
      ((l.facts||[]).map(function(r){return '<div><strong>'+esc(r.key)+'</strong>: '+esc(r.value)+' '+esc(r.unit||'')+' <span class="small">['+esc(r.authority)+']</span></div>'}).join("")||'')+
      ((l.calculated||[]).map(function(r){return '<div><strong>'+esc(r.key)+'</strong>: '+esc(r.value)+' '+esc(r.unit||'')+' <span class="small">['+esc(r.authority)+']</span></div>'}).join("")||'')+
      ((l.conflicts||[]).map(function(r){return '<div class="notice" style="margin-top:8px"><strong>Source conflict: '+esc(r.key)+'</strong><br>'+esc(r.reason||r.note||'Requires source reconciliation')+'</div>'}).join("")||'')+
      ((l.unresolved||[]).map(function(r){return '<div class="notice" style="margin-top:8px"><strong>'+esc(r.key)+'</strong><br>'+esc(r.reason)+'<br><span class="small">Resolution: '+esc(r.method)+'</span></div>'}).join("")||'')+
      '</div></details>';
  });
  el("close-lanes").innerHTML=laneHtml2;

  var lanes=data.system_lanes||{}, laneHtml="";
  Object.keys(lanes).forEach(function(key){
    var r=lanes[key];laneHtml+='<details id="lane-'+esc(key)+'"><summary><span>'+esc(key.replace(/_/g," "))+'</span><span class="status '+statusType(r.status)+'">'+esc(r.status)+'</span></summary><div class="detail-body">'+esc(r.basis)+'</div></details>'
  });
  el("system-lanes").innerHTML=laneHtml;

  var domainHtml="";
  Object.keys(data.semantic_domains||{}).forEach(function(key){
    var d=data.semantic_domains[key]||{},known=Array.isArray(d.known)?d.known:[],unres=Array.isArray(d.unresolved)?d.unresolved:[];
    domainHtml+='<details id="domain-'+esc(key)+'"><summary><span>'+esc(key.replace(/_/g," "))+'</span><span class="status '+(unres.length?"warn":"good")+'">'+known.length+' mapped · '+unres.length+' unresolved</span></summary><div class="detail-body">';
    if(known.length){domainHtml+='<h3>Mapped facts</h3><div class="table-wrap"><table><thead><tr><th>Fact</th><th>Value</th><th>Authority</th></tr></thead><tbody>'+known.map(function(r){return '<tr><td>'+esc(r.key)+'</td><td>'+esc(r.value==null?"—":r.value)+' '+esc(r.unit||"")+'</td><td>'+esc(r.authority||"")+'</td></tr>'}).join("")+'</tbody></table></div>'}
    if(unres.length){domainHtml+='<h3 style="margin-top:12px">Unresolved</h3>'+unres.map(function(r){return '<div class="notice" style="margin:7px 0"><strong>'+esc(r.key||r.status||"Unresolved")+'</strong><br><span class="small">'+esc(r.reason||"")+'</span></div>'}).join("")}
    domainHtml+='</div></details>'
  });
  el("domains").innerHTML=domainHtml;

  var k=data.known_state||{}, census=k.census||[],routes=k.arterial_routes||[],food=k.food_financials||[];
  el("known-state").innerHTML=
    '<details open><summary>Population <span class="status warn">'+census.length+' rows</span></summary><div class="detail-body">'+census.map(function(r){return '<div><strong>'+esc(r.settlement)+'</strong>: '+(r.population==null?'<span class="warntext">UNKNOWN</span>':num(r.population))+'</div>'}).join("")+'</div></details>'+
    '<details><summary>Arterial routes <span class="status warn">'+routes.length+' sourced distances</span></summary><div class="detail-body"><div class="table-wrap"><table>'+routes.map(function(r){return '<tr><td>'+esc(r.route)+'</td><td>'+esc(r.distance_miles)+' mi</td><td>'+(r.capacity==null?'<span class="warntext">capacity unknown</span>':esc(r.capacity))+'</td></tr>'}).join("")+'</table></div></div></details>'+
    '<details><summary>Food sector <span class="status warn">'+food.length+' financial rows</span></summary><div class="detail-body"><div class="table-wrap"><table>'+food.map(function(r){return '<tr><td>'+esc(r.entity)+'</td><td>'+money(r.monthly_revenue_gp)+' gp revenue</td><td>'+(r.physical_output==null?'<span class="warntext">physical output unresolved</span>':esc(r.physical_output))+'</td></tr>'}).join("")+'</table></div></div></details>';

  var unresolved=[];
  (k.unresolved||[]).forEach(function(x){unresolved.push(String(x))});
  Object.keys(data.semantic_domains||{}).forEach(function(key){(data.semantic_domains[key].unresolved||[]).forEach(function(r){unresolved.push((r.key||key)+": "+(r.reason||r.status||"unresolved"))})});
  var seen={},unique=[];unresolved.forEach(function(x){if(!seen[x]){seen[x]=true;unique.push(x)}});
  el("unresolved").innerHTML=unique.map(function(x){return '<details><summary>'+esc(x.split(":")[0])+'<span class="status warn">unresolved</span></summary><div class="detail-body">'+esc(x)+'</div></details>'}).join("")||'<p class="goodtext">No unresolved gates returned.</p>';

  var products=data.products.products||[];
  el("products").innerHTML=products.map(function(p){return '<details><summary><span>'+esc(p.name)+'</span><span class="status '+statusType(p.status)+'">'+esc(p.boundary)+'</span></summary><div class="detail-body"><strong>Current mapping:</strong> '+esc(p.mapping||"")+'<br><br>'+esc(p.status||"")+'</div></details>'}).join("");

  savedRuns=data.saved_runs||[];renderSavedRuns();
}

async function load(){
  initDateControls();
  try{
    var r=await fetch("/api/bootstrap",{headers:{"Accept":"application/json"}}),j=await r.json();
    if(!r.ok||!j.ok)throw new Error((j.error&&j.error.message)||"bootstrap failed");
    renderBootstrap(j.data)
  }catch(err){el("run-status").textContent="App bootstrap failed: "+err.message;el("run-status").className="statusline badtext"}
}

function renderBusinessResult(p){
  el("business-empty").classList.add("hidden");el("business-results").classList.remove("hidden");
  var rows=p.sector_results||[];
  el("sector-results").innerHTML='<div class="table-wrap"><table><thead><tr><th>Sector</th><th>Baseline</th><th>Result</th><th>Roll</th></tr></thead><tbody>'+rows.map(function(r){var q=r.roll||{};return '<tr><td><strong>'+esc(r.sector)+'</strong></td><td>'+money(r.baseline_revenue_gp)+' gp</td><td>'+money(r.proposed_revenue_gp)+' gp</td><td>'+esc(q.dice||"")+' = '+esc(q.total||"")+' · '+esc(q.outcome||"")+'</td></tr>'}).join("")+'</tbody></table></div>';
  var e=p.expense_control||{},er=e.roll||{};
  el("expense-result").innerHTML='<strong>Baseline expense range:</strong> '+esc((e.baseline_expense_range_gp||[]).join(" – "))+' gp<br><strong>Administration roll:</strong> '+esc(er.dice||"")+' = '+esc(er.total||"")+' → '+esc(er.outcome||"")+'<br><strong>Proposed expense range:</strong> '+esc((e.proposed_expense_range_gp||[]).join(" – "))+' gp';
  el("complication-results").innerHTML=(p.entity_complications||[]).map(function(r){return '<div class="saved-card"><strong>'+esc(r.entity)+'</strong><br>d20 '+esc(r.raw_d20)+' → '+esc(r.final_outcome||"UNRESOLVED")+'</div>'}).join("")||'<p class="muted">None.</p>';
  var vh="";Object.keys(p.vara_briefing||{}).forEach(function(band){var arr=p.vara_briefing[band]||[];if(arr.length)vh+='<h3>'+esc(band)+'</h3>'+arr.map(function(r){return '<div>• '+esc(r.kind)+': <strong>'+esc(r.subject)+'</strong></div>'}).join("")});el("vara-results").innerHTML=vh||'<p class="muted">No briefing entries.</p>';
}

async function runPreview(newRoll){
  if(newRoll){previewCounter++;el("seed").value=autoSeed()}
  var body={seed:el("seed").value||autoSeed(),month_label:authorityLabel(),market_condition:el("market").value,vara_active:el("vara").checked};
  el("run-current").disabled=true;el("run-status").textContent="Running source-grounded preview…";el("run-status").className="statusline";
  try{
    var r=await fetch("/api/preview",{method:"POST",headers:{"Content-Type":"application/json","Accept":"application/json"},body:JSON.stringify(body)}),j=await r.json();
    if(!r.ok||!j.ok)throw new Error((j.error&&j.error.message)||"preview failed");
    var p=j.data.result;latestRequest=body;latestResult=p;latestReport=j.data.report;
    el("preview-summary").classList.remove("hidden");el("report-wrap").classList.remove("hidden");
    el("p-admitted").textContent=num(p.admission.admitted_entities);el("p-baseline").textContent=money(p.admission.baseline_revenue_gp);
    el("p-revenue").textContent=money(p.proposed_revenue_gp);el("p-net").textContent=money(p.proposed_net_range_gp[0])+" – "+money(p.proposed_net_range_gp[1]);
    el("report").textContent=latestReport;renderBusinessResult(p);
    el("run-status").textContent="Preview complete. Tap Businesses for the result, or Saved runs to keep it.";el("run-status").className="statusline goodtext"
  }catch(err){el("run-status").textContent="Preview failed closed: "+err.message;el("run-status").className="statusline badtext"}
  finally{el("run-current").disabled=false}
}

function renderSavedRuns(){
  if(!savedRuns.length){el("saved-runs").innerHTML='<p class="muted">No saved previews yet.</p>';return}
  el("saved-runs").innerHTML=savedRuns.map(function(r){var s=r.summary||{};return '<div class="saved-card"><div class="saved-head"><div><strong>'+esc(r.label)+'</strong><div class="small">'+esc(r.run_id)+' · '+esc(r.created_at||"")+'</div></div><div>'+money(s.proposed_revenue_gp||0)+' gp</div></div><div class="small" style="margin-top:6px">Net: '+esc((s.proposed_net_range_gp||[]).join(" – ")||"—")+'</div><div class="link-row"><a href="/api/runs/'+encodeURIComponent(r.run_id)+'/export?format=html" target="_blank">Open report</a><a href="/api/runs/'+encodeURIComponent(r.run_id)+'/export?format=md" target="_blank">Markdown</a><a href="/api/runs/'+encodeURIComponent(r.run_id)+'/export?format=json" target="_blank">JSON</a></div></div>'}).join("")
}
async function refreshRuns(){var r=await fetch("/api/runs"),j=await r.json();if(r.ok&&j.ok){savedRuns=j.data.runs||[];renderSavedRuns()}}
async function saveCurrent(){
  if(!latestRequest){el("save-status").textContent="Run a preview first.";el("save-status").className="statusline warntext";return}
  var period=el("month-select").value+" "+el("year-select").value,base=slug(period),n=1,ids={};savedRuns.forEach(function(r){ids[r.run_id]=true});while(ids[base+"-"+n])n++;
  var runId=base+"-"+n,label=period+" preview "+n;
  try{
    var r=await fetch("/api/runs",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({run_id:runId,label:label,request:latestRequest})}),j=await r.json();
    if(!r.ok||!j.ok)throw new Error((j.error&&j.error.message)||"save failed");
    el("save-status").textContent="Saved as "+label+".";el("save-status").className="statusline goodtext";await refreshRuns()
  }catch(err){el("save-status").textContent="Save failed closed: "+err.message;el("save-status").className="statusline badtext"}
}
async function compareLatest(){
  if(savedRuns.length<2){el("save-status").textContent="Save at least two previews to compare them.";el("save-status").className="statusline warntext";return}
  var left=savedRuns[1].run_id,right=savedRuns[0].run_id;
  try{
    var r=await fetch("/api/compare?left="+encodeURIComponent(left)+"&right="+encodeURIComponent(right)),j=await r.json();
    if(!r.ok||!j.ok)throw new Error((j.error&&j.error.message)||"compare failed");
    el("comparison").classList.remove("hidden");el("comparison").textContent=JSON.stringify(j.data,null,2)
  }catch(err){el("comparison").classList.remove("hidden");el("comparison").textContent="Comparison failed: "+err.message}
}

el("run-current").addEventListener("click",function(){runPreview(false)});
el("roll-again").addEventListener("click",function(){runPreview(true)});
el("run-from-businesses").addEventListener("click",function(){showView("home");setTimeout(function(){runPreview(false)},150)});
el("save-current").addEventListener("click",saveCurrent);
el("compare-latest").addEventListener("click",compareLatest);
el("go-businesses").addEventListener("click",function(){showView("businesses")});
el("download").addEventListener("click",function(){if(!latestReport)return;var blob=new Blob([latestReport],{type:"text/markdown;charset=utf-8"}),a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="Baen-Economy-Preview.md";a.click();setTimeout(function(){URL.revokeObjectURL(a.href)},1000)});
load();
})();
</script>
</body>
</html>
"""
