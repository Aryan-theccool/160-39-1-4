"""A single-page console so the service can be exercised without a frontend.

Part 6 is the Next.js UI; this is not that. It is a ~150-line page served by the
API itself, with no build step and no CDN dependency, so that ``/`` shows
something usable the moment the server starts -- which matters in a preview
environment where only the port is exposed.

Every request uses a **relative** path (``/api/v1/...``). An absolute
``http://localhost:8000`` would fail for any browser that is not on the same
machine as the server, which is the normal case when the server runs in a
container.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from ..deps import get_services
from ..services import AppServices

router = APIRouter(tags=["console"])

_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BIS Standards API console</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
         max-width: 62rem; margin: 0 auto; padding: 1.5rem; line-height: 1.5; }
  h1 { font-size: 1.35rem; margin-bottom: .25rem; }
  .sub { color: #777; font-size: .87rem; margin-bottom: 1.25rem; }
  .status { display: inline-block; padding: .15rem .5rem; border-radius: 4px;
            font-size: .8rem; font-weight: 600; }
  .status.ok { background: #e6f4ea; color: #12602b; }
  .status.degraded { background: #fef7e0; color: #8a5a00; }
  .status.unavailable { background: #fce8e6; color: #a50e0e; }
  fieldset { border: 1px solid #ddd; border-radius: 6px; margin: 0 0 1rem; padding: .75rem 1rem; }
  legend { font-weight: 600; font-size: .85rem; padding: 0 .35rem; }
  input[type=text] { width: 100%; padding: .45rem .6rem; font-size: .95rem;
                     border: 1px solid #bbb; border-radius: 4px; box-sizing: border-box; }
  select, input[type=number] { padding: .35rem .5rem; border: 1px solid #bbb; border-radius: 4px; }
  button { padding: .45rem .9rem; font-size: .9rem; border-radius: 4px; cursor: pointer;
           border: 1px solid #0b5cad; background: #0b5cad; color: #fff; margin-top: .5rem; }
  button:hover { background: #094a8c; }
  button.ghost { background: transparent; color: #0b5cad; }
  pre { background: #f6f8fa; border: 1px solid #e1e4e8; border-radius: 6px; padding: .75rem;
        overflow: auto; max-height: 26rem; font-size: .82rem; }
  .row { display: flex; gap: .5rem; flex-wrap: wrap; align-items: end; }
  .muted { color: #777; font-size: .82rem; }
  .warn { color: #8a5a00; }
  .bar { height: .55rem; border-radius: 3px; background: #eee; overflow: hidden; margin: .35rem 0; }
  .bar > span { display: block; height: 100%; background: #0b5cad; }
</style>
</head>
<body>
<h1>BIS Standards API</h1>
<p class="sub">
  <span id="health" class="status">loading…</span>
  <span id="health-detail" class="muted"></span>
</p>

<fieldset>
  <legend>Search (retrieval only, no LLM)</legend>
  <div class="row">
    <div style="flex:1;min-width:16rem">
      <input type="text" id="q" value="water pipe for potable supplies"
             placeholder="e.g. drinking water quality">
    </div>
    <button onclick="doSearch()">Search</button>
  </div>
</fieldset>

<fieldset>
  <legend>Recommend (grounded answer with citations)</legend>
  <div class="row">
    <div style="flex:1;min-width:16rem">
      <input type="text" id="rq" value="What standard covers drinking water quality?"
             placeholder="ask a question">
    </div>
    <button onclick="doRecommend()">Ask</button>
  </div>
</fieldset>

<fieldset>
  <legend>Compliance check (QCO)</legend>
  <div class="row">
    <div style="flex:1;min-width:14rem">
      <input type="text" id="product" value="33 grade ordinary Portland cement"
             placeholder="product description">
    </div>
    <div style="flex:1;min-width:10rem">
      <input type="text" id="standards" value="IS 269:1989"
             placeholder="standards in use, comma separated">
    </div>
    <button onclick="doCompliance()">Check</button>
  </div>
</fieldset>

<pre id="out">Ready. Response appears here.</pre>
<p class="muted">
  Full schema: <a href="/docs">/docs</a> &nbsp;·&nbsp;
  <a href="/api/v1/health">/api/v1/health</a> &nbsp;·&nbsp;
  <a href="/api/v1/standards">/api/v1/standards</a>
</p>

<script>
const out = document.getElementById('out');
function show(label, data) {
  out.textContent = label + "\\n\\n" +
    (typeof data === 'string' ? data : JSON.stringify(data, null, 2));
}

async function call(path, options) {
  const started = performance.now();
  try {
    const res = await fetch(path, options);          // relative: works behind any host
    const text = await res.text();
    const ms = Math.round(performance.now() - started);
    let body;
    try { body = JSON.parse(text); } catch (e) { body = text; }
    if (!res.ok) {
      show("HTTP " + res.status + " (" + ms + "ms)  " + path, body);
      return null;
    }
    return { body, ms };
  } catch (err) {
    show("network error  " + path, String(err));
    return null;
  }
}

async function doSearch() {
  const q = document.getElementById('q').value.trim();
  if (!q) return;
  const r = await call('/api/v1/search?q=' + encodeURIComponent(q) + '&limit=5');
  if (!r) return;
  const b = r.body;
  let text = b.results.length + " result(s) in " + b.took_ms + "ms (server) / "
             + r.ms + "ms (total)\\nintent: " + b.intent + "  reranker: " + b.reranker + "\\n";
  for (const [i, hit] of b.results.entries()) {
    const found = Object.entries(hit.found_by || {}).map(([k, v]) => k + "#" + v).join(" ");
    text += "\\n" + (i + 1) + ". " + hit.designation + (hit.is_current ? "" : "  [SUPERSEDED]")
          + "\\n   " + hit.title + "\\n   score " + hit.score + "   found by " + found
          + "\\n   " + hit.text.slice(0, 160) + "\\n";
  }
  if (b.notes && b.notes.length) text += "\\nnotes: " + b.notes.join(" | ");
  show("GET /api/v1/search?q=" + q, text);
}

async function doRecommend() {
  const q = document.getElementById('rq').value.trim();
  if (!q) return;
  const r = await call('/api/v1/recommend', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: q, top_k: 5, include_passages: false })
  });
  if (!r) return;
  const b = r.body;
  let text = "mode: " + b.mode + "  generator: " + b.generator
           + "  grounded: " + b.grounded + "  (" + b.took_ms + "ms)\\n\\n" + b.answer;
  if (b.citations && b.citations.length) {
    text += "\\n\\nCitations:\\n";
    for (const c of b.citations) {
      text += "  - " + c.designation + " — " + c.title
            + (c.is_current ? "" : "  [SUPERSEDED by " + c.superseded_by + "]") + "\\n";
    }
  }
  if (b.warnings && b.warnings.length) text += "\\nWarnings:\\n  " + b.warnings.join("\\n  ");
  if (b.unsupported_citations && b.unsupported_citations.length) {
    text += "\\nUNVERIFIED citations: " + b.unsupported_citations.join(", ");
  }
  show("POST /api/v1/recommend", text);
}

async function doCompliance() {
  const product = document.getElementById('product').value.trim();
  const standards = document.getElementById('standards').value
      .split(',').map(s => s.trim()).filter(Boolean);
  const r = await call('/api/v1/compliance/check', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ product_description: product, standards: standards })
  });
  if (!r) return;
  const b = r.body;
  let text = b.grade + "   score " + b.compliance_score + "   (" + b.took_ms + "ms)\\n"
           + "QCO list: " + b.qco_source + (b.qco_verified ? " (verified)" : " (UNVERIFIED)")
           + "\\n\\nstatus: " + b.compliance_status
           + "\\nmandatory missing: " + (b.mandatory_missing.length ? b.mandatory_missing.join(", ") : "none")
           + "\\nsuperseded in use: " + (b.superseded_used.length
              ? b.superseded_used.map(s => s.used + " -> " + s.replace_with).join(", ") : "none")
           + "\\n\\nAction items:\\n";
  for (const [i, a] of b.action_items.entries()) text += "  " + (i + 1) + ". " + a + "\\n";
  if (b.grade_capped_by) text += "\\ngrade capped: " + b.grade_capped_by;
  show("POST /api/v1/compliance/check", text);
}

async function loadHealth() {
  const r = await call('/api/v1/health');
  const badge = document.getElementById('health');
  const detail = document.getElementById('health-detail');
  if (!r) { badge.textContent = "unreachable"; badge.className = "status unavailable"; return; }
  const b = r.body;
  badge.textContent = b.status;
  badge.className = "status " + b.status;
  const c = b.corpus || {}, rt = b.retrieval || {};
  detail.textContent = (c.standards || 0) + " standards · " + (c.chunks || 0) + " chunks · "
    + "dense " + (rt.dense_enabled ? "on" : "off") + " · "
    + (b.issues && b.issues.length ? b.issues.length + " issue(s)" : "no issues");
  healthPercent(b.compliance_score);
}
function healthPercent() { /* placeholder: nothing to chart here */ }
loadHealth();
</script>
</body>
</html>
"""


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def console(services: AppServices = Depends(get_services)) -> HTMLResponse:
    return HTMLResponse(_PAGE)
