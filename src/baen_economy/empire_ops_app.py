"""Single-page local browser UI for the Baen Empire economy operator."""

APP_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Baen Economy Engine</title>
<style>
:root {
  color-scheme: dark;
  --bg:#0b0f14; --panel:#121923; --panel2:#17212d; --line:#263442;
  --text:#e8eef5; --muted:#9aa9b7; --good:#70d6a0; --warn:#f0c36a;
  --bad:#ef7f7f; --accent:#7db7ff; --chip:#1d2b39;
}
*{box-sizing:border-box}
body{margin:0;background:linear-gradient(180deg,#091018 0,#0b0f14 28rem);color:var(--text);font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{padding:28px 24px 18px;max-width:1440px;margin:auto}
h1{margin:0 0 6px;font-size:32px;letter-spacing:.2px}
h2{font-size:18px;margin:0 0 14px} h3{font-size:14px;margin:0 0 8px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}
p{margin:6px 0}.sub{color:var(--muted);max-width:900px}
.badges{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
.badge,.chip{display:inline-block;border:1px solid var(--line);background:var(--chip);padding:5px 9px;border-radius:999px;font-size:12px}
.badge.good{color:var(--good)} .badge.warn{color:var(--warn)} .badge.bad{color:var(--bad)}
main{max-width:1440px;margin:auto;padding:0 24px 36px}
.grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:14px;margin-bottom:14px}
.card{grid-column:span 3;background:rgba(18,25,35,.96);border:1px solid var(--line);border-radius:13px;padding:16px;box-shadow:0 8px 28px rgba(0,0,0,.18)}
.card.wide{grid-column:span 6}.card.full{grid-column:1/-1}.metric{font-size:27px;font-weight:700;margin:2px 0}.label{color:var(--muted);font-size:12px}
.controls{display:grid;grid-template-columns:2fr 2fr 1fr auto auto;gap:10px;align-items:end}
label{display:block;color:var(--muted);font-size:12px;margin-bottom:5px}
input,select,button{width:100%;border:1px solid var(--line);background:#0e151d;color:var(--text);padding:10px 11px;border-radius:8px;font:inherit}
button{cursor:pointer;background:#17304d;border-color:#2e5f91;font-weight:650}
button.secondary{background:#131c26;border-color:var(--line)}
button:disabled{opacity:.55;cursor:wait}
.checkbox{display:flex;align-items:center;gap:8px;height:40px}.checkbox input{width:auto}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:8px 7px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-weight:600}
.domain{padding:11px 0;border-bottom:1px solid var(--line)}.domain:last-child{border-bottom:0}
.domain-title{display:flex;justify-content:space-between;gap:10px;font-weight:650}
.small{font-size:12px;color:var(--muted)}
ul.clean{list-style:none;padding:0;margin:0}ul.clean li{padding:8px 0;border-bottom:1px solid var(--line)}ul.clean li:last-child{border-bottom:0}
pre{white-space:pre-wrap;word-break:break-word;background:#090e14;border:1px solid var(--line);padding:15px;border-radius:9px;max-height:620px;overflow:auto;color:#d7e2ec}
.statusline{min-height:22px;color:var(--muted);margin-top:8px}
.goodtext{color:var(--good)}.warntext{color:var(--warn)}.badtext{color:var(--bad)}
.hidden{display:none}
@media(max-width:1000px){.card,.card.wide{grid-column:span 6}.controls{grid-template-columns:1fr 1fr}.controls>div{min-width:0}}
@media(max-width:650px){header,main{padding-left:14px;padding-right:14px}.card,.card.wide{grid-column:1/-1}.controls{grid-template-columns:1fr}.metric{font-size:23px}}
</style>
</head>
<body>
<header>
  <h1>Baen Economy Engine</h1>
  <p class="sub">Empire operator for the current Hammer 1495 source state. This application exposes what is known, what is mapped, what is still blocked, and lets you run a deterministic non-canonical business-phase preview.</p>
  <div class="badges">
    <span class="badge warn" id="canon-badge">Canonical month: loading…</span>
    <span class="badge good">Notion writes: 0</span>
    <span class="badge good">Canonical ledger posts: 0</span>
    <span class="badge good">Campaign time advance: 0</span>
  </div>
</header>
<main>
  <section class="grid">
    <div class="card"><div class="label">Current-live source records</div><div class="metric" id="live-count">—</div><div class="small">Ten live collections</div></div>
    <div class="card"><div class="label">Retained core records</div><div class="metric" id="retained-count">—</div><div class="small">Including provenance-retained NPC pages</div></div>
    <div class="card"><div class="label">Source-mapped records</div><div class="metric" id="mapped-count">—</div><div class="small">Semantic overlay, not simulated</div></div>
    <div class="card"><div class="label">SIMULATED records</div><div class="metric" id="sim-count">—</div><div class="small">Canonical coverage remains fail-closed</div></div>
  </section>

  <section class="grid">
    <div class="card full">
      <h2>Run source-grounded monthly business preview</h2>
      <div class="controls">
        <div><label for="seed">Replay seed</label><input id="seed" value="hammer-1495-app-preview"></div>
        <div><label for="month">Review label</label><input id="month" value="Day 7 Hammer 1495 DR — monthly preview"></div>
        <div><label for="market">Market ruling</label><select id="market"><option value="unknown">Unknown / no modifier</option><option value="stable">Stable</option><option value="boom">Boom</option><option value="recession">Recession</option></select></div>
        <div><label>Optional ruling</label><div class="checkbox"><input type="checkbox" id="vara"><span>Vara active</span></div></div>
        <div><label>&nbsp;</label><button id="run">Run preview</button></div>
      </div>
      <div class="statusline" id="run-status">No preview run in this browser session.</div>
    </div>
  </section>

  <section class="grid hidden" id="preview-summary">
    <div class="card"><div class="label">Admitted businesses</div><div class="metric" id="p-admitted">—</div><div class="small">Current source-admitted operating entities</div></div>
    <div class="card"><div class="label">Baseline revenue</div><div class="metric" id="p-baseline">—</div><div class="small">gp / month</div></div>
    <div class="card"><div class="label">Rolled revenue</div><div class="metric" id="p-revenue">—</div><div class="small">preview gp</div></div>
    <div class="card"><div class="label">Proposed net range</div><div class="metric" id="p-net">—</div><div class="small">preview only</div></div>
  </section>

  <section class="grid">
    <div class="card wide">
      <h2>Source → product semantic domains</h2>
      <div id="domains">Loading…</div>
    </div>
    <div class="card wide">
      <h2>Upstream products</h2>
      <div id="products">Loading…</div>
    </div>
  </section>

  <section class="grid">
    <div class="card wide">
      <h2>Known physical/source state</h2>
      <div id="known-state">Loading…</div>
    </div>
    <div class="card wide">
      <h2>Current unresolved gates</h2>
      <ul class="clean" id="unresolved"><li>Loading…</li></ul>
    </div>
  </section>

  <section class="grid hidden" id="report-wrap">
    <div class="card full">
      <div style="display:flex;justify-content:space-between;gap:12px;align-items:center">
        <h2 style="margin:0">Preview report</h2>
        <button class="secondary" id="download" style="width:auto">Download report</button>
      </div>
      <pre id="report"></pre>
    </div>
  </section>
</main>
<script>
(function(){
  "use strict";
  var latestReport = "";
  function el(id){ return document.getElementById(id); }
  function esc(value){ return String(value == null ? "" : value).replace(/[&<>"']/g,function(c){return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c];}); }
  function num(value){ return new Intl.NumberFormat("en-US").format(Number(value || 0)); }
  function money(value){ var n=Number(value); return Number.isFinite(n) ? new Intl.NumberFormat("en-US",{maximumFractionDigits:2}).format(n) : String(value); }
  function statusClass(status){ status=String(status||""); if(status.indexOf("USED")>=0||status.indexOf("IMPLEMENTED")>=0)return "goodtext"; if(status.indexOf("BLOCK")>=0||status.indexOf("UNRESOLVED")>=0||status.indexOf("UNAVAILABLE")>=0)return "warntext"; return ""; }

  function renderBootstrap(data){
    var s=data.source_status, c=data.semantic_coverage;
    el("live-count").textContent=num(s.current_live_records);
    el("retained-count").textContent=num(s.retained_core_records);
    el("mapped-count").textContent=num(c.mapped_record_count);
    el("sim-count").textContent=num(c.simulated_after_overlay);
    el("canon-badge").textContent="Canonical month: "+s.canonical_month;
    el("canon-badge").className="badge "+(s.canonical_month==="BLOCKED"?"warn":"bad");

    var dhtml="";
    Object.keys(data.semantic_domains).forEach(function(key){
      var d=data.semantic_domains[key]||{}, known=Array.isArray(d.known)?d.known:[], unresolved=Array.isArray(d.unresolved)?d.unresolved:[];
      dhtml += '<div class="domain"><div class="domain-title"><span>'+esc(key.replace(/_/g," "))+'</span><span class="small">'+known.length+' mapped · '+unresolved.length+' unresolved</span></div>';
      if(known.length){ dhtml += '<div class="small">'+known.slice(0,3).map(function(r){return esc(r.key);}).join(" · ")+(known.length>3?" · …":"")+'</div>'; }
      dhtml += '</div>';
    });
    el("domains").innerHTML=dhtml||'<span class="small">No domains returned.</span>';

    var phtml='<table><thead><tr><th>Product</th><th>Boundary</th><th>Current mapping state</th></tr></thead><tbody>';
    (data.products.products||[]).forEach(function(p){
      phtml += '<tr><td><strong>'+esc(p.name)+'</strong></td><td>'+esc(p.boundary)+'</td><td class="'+statusClass(p.status)+'">'+esc(p.status)+'</td></tr>';
    });
    el("products").innerHTML=phtml+'</tbody></table>';

    var k=data.known_state||{}, census=k.census||[], routes=k.arterial_routes||[], food=k.food_financials||[];
    var kh='<div class="domain"><div class="domain-title"><span>Population</span><span class="small">'+census.length+' settlement rows</span></div><div class="small">';
    kh += census.map(function(r){return esc(r.settlement)+": "+(r.population==null?"UNKNOWN":num(r.population));}).join(" · ")+'</div></div>';
    kh += '<div class="domain"><div class="domain-title"><span>Arterial routes</span><span class="small">'+routes.length+' sourced distances</span></div><div class="small">Freight capacities remain unknown unless separately sourced.</div></div>';
    kh += '<div class="domain"><div class="domain-title"><span>Food sector</span><span class="small">'+food.length+' financial/source rows</span></div><div class="small">Physical outputs remain distinct from financial evidence.</div></div>';
    el("known-state").innerHTML=kh;

    var unresolved=[];
    (k.unresolved||[]).forEach(function(x){unresolved.push(x);});
    Object.keys(data.semantic_domains).forEach(function(key){
      var d=data.semantic_domains[key]||{};
      (d.unresolved||[]).forEach(function(r){unresolved.push((r.key||key)+": "+(r.reason||r.status||"unresolved"));});
    });
    var unique=[]; var seen={};
    unresolved.forEach(function(x){x=String(x);if(!seen[x]){seen[x]=true;unique.push(x);}});
    el("unresolved").innerHTML=unique.slice(0,24).map(function(x){return "<li>"+esc(x)+"</li>";}).join("") || "<li>None returned.</li>";
  }

  async function load(){
    try{
      var r=await fetch("/api/bootstrap",{headers:{"Accept":"application/json"}});
      var j=await r.json();
      if(!r.ok||!j.ok) throw new Error((j.error&&j.error.message)||"bootstrap failed");
      renderBootstrap(j.data);
    }catch(err){
      el("run-status").textContent="App bootstrap failed: "+err.message;
      el("run-status").className="statusline badtext";
    }
  }

  async function runPreview(){
    var button=el("run"); button.disabled=true;
    el("run-status").textContent="Running source-grounded preview…"; el("run-status").className="statusline";
    try{
      var body={seed:el("seed").value,month_label:el("month").value,market_condition:el("market").value,vara_active:el("vara").checked};
      var r=await fetch("/api/preview",{method:"POST",headers:{"Content-Type":"application/json","Accept":"application/json"},body:JSON.stringify(body)});
      var j=await r.json();
      if(!r.ok||!j.ok) throw new Error((j.error&&j.error.message)||"preview failed");
      var p=j.data.result;
      el("preview-summary").classList.remove("hidden");
      el("report-wrap").classList.remove("hidden");
      el("p-admitted").textContent=num(p.admission.admitted_entities);
      el("p-baseline").textContent=money(p.admission.baseline_revenue_gp);
      el("p-revenue").textContent=money(p.proposed_revenue_gp);
      el("p-net").textContent=money(p.proposed_net_range_gp[0])+" – "+money(p.proposed_net_range_gp[1]);
      latestReport=j.data.report;
      el("report").textContent=latestReport;
      el("run-status").textContent="Preview complete. No canonical state was changed.";
      el("run-status").className="statusline goodtext";
    }catch(err){
      el("run-status").textContent="Preview failed closed: "+err.message;
      el("run-status").className="statusline badtext";
    }finally{ button.disabled=false; }
  }

  el("run").addEventListener("click",runPreview);
  el("download").addEventListener("click",function(){
    if(!latestReport)return;
    var blob=new Blob([latestReport],{type:"text/markdown;charset=utf-8"});
    var a=document.createElement("a"); a.href=URL.createObjectURL(blob); a.download="Baen-Economy-Preview.md"; a.click(); setTimeout(function(){URL.revokeObjectURL(a.href);},1000);
  });
  load();
})();
</script>
</body>
</html>
"""
