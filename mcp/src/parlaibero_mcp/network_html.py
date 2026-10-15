"""Self-contained interactive HTML pages for the network tools (d3 v7.8.5 from cdnjs).

Data are injected programmatically (networks.embed_json), never typed by hand, and networks._self_check
reads them back from the written file. Text reaches the page only through textContent / d3 .text().

Colour (validated with the dataviz skill's validate_palette.js, 14-oct-2026):
  diverging bias scale, 7 steps, group 1 (orange) ↔ neutral gray ↔ group 2 (blue)
    light: #cf511a #eb6834 #ef906d | #f0efec | #81abe4 #5691dd #2a78d6
    dark:  #d95926 #a75233 #7a4938 | #383835 | #3d597d #3d6fae #3987e5
    every arm: one hue, monotone lightness, gaps ≥ 0.06, near-neutral step ≥ 2:1 on the surface.
  categorical (communities, parties): the reference 8-slot order (blue, orange, aqua, yellow, magenta,
    green, violet, red); a 9th group and beyond fold into "Other" (gray). Shape, labels, the
    highlight selector and the twin table carry identity too: colour is never the only channel.
"""
from __future__ import annotations

import html

from .networks import embed_json

D3 = "https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"

CSS = r"""
:root{color-scheme:light;
 --surface:#fcfcfb;--plane:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;
 --ring:rgba(11,11,11,.10);--edge:#52514e;
 --d-3:#cf511a;--d-2:#eb6834;--d-1:#ef906d;--d0:#f0efec;--d1:#81abe4;--d2:#5691dd;--d3:#2a78d6;
 --c1:#2a78d6;--c2:#eb6834;--c3:#1baf7a;--c4:#eda100;--c5:#e87ba4;--c6:#008300;--c7:#4a3aa7;--c8:#e34948;--c0:#b5b3ad;
 --s0:#86b6ef;--s1:#3987e5;--s2:#256abf;--s3:#184f95;--s4:#0d366b;
 --t0:#0b0b0b;--t1:#0b0b0b;--t2:#ffffff;--t3:#ffffff;--t4:#ffffff;
 --focus:#2a78d6}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])){color-scheme:dark;
 --surface:#1a1a19;--plane:#0d0d0d;--ink:#ffffff;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;
 --ring:rgba(255,255,255,.10);--edge:#c3c2b7;
 --d-3:#d95926;--d-2:#a75233;--d-1:#7a4938;--d0:#383835;--d1:#3d597d;--d2:#3d6fae;--d3:#3987e5;
 --c1:#3987e5;--c2:#d95926;--c3:#199e70;--c4:#c98500;--c5:#d55181;--c6:#008300;--c7:#9085e9;--c8:#e66767;--c0:#5c5b57;
 --s0:#184f95;--s1:#256abf;--s2:#3987e5;--s3:#6da7ec;--s4:#9ec5f4;
 --t0:#ffffff;--t1:#ffffff;--t2:#0b0b0b;--t3:#0b0b0b;--t4:#0b0b0b;
 --focus:#3987e5}}
:root[data-theme="dark"]{color-scheme:dark;
 --surface:#1a1a19;--plane:#0d0d0d;--ink:#ffffff;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;
 --ring:rgba(255,255,255,.10);--edge:#c3c2b7;
 --d-3:#d95926;--d-2:#a75233;--d-1:#7a4938;--d0:#383835;--d1:#3d597d;--d2:#3d6fae;--d3:#3987e5;
 --c1:#3987e5;--c2:#d95926;--c3:#199e70;--c4:#c98500;--c5:#d55181;--c6:#008300;--c7:#9085e9;--c8:#e66767;--c0:#5c5b57;
 --s0:#184f95;--s1:#256abf;--s2:#3987e5;--s3:#6da7ec;--s4:#9ec5f4;
 --t0:#ffffff;--t1:#ffffff;--t2:#0b0b0b;--t3:#0b0b0b;--t4:#0b0b0b;
 --focus:#3987e5}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--plane);color:var(--ink);font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1200px;margin:0 auto;padding:16px}
h1{font-size:1.35rem;margin:0 0 .2rem}
.sub{color:var(--ink2);margin:0 0 1rem;overflow-wrap:anywhere}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:12px;min-width:0}
.controls{display:flex;flex-wrap:wrap;gap:10px 18px;align-items:center;margin-bottom:10px}
.controls label{display:flex;gap:6px;align-items:center;color:var(--ink2);font-size:.88rem}
.controls output{font-variant-numeric:tabular-nums;color:var(--ink);min-width:3.5em}
.controls input[type=range]{width:140px}
button,select{font:inherit;font-size:.86rem;color:var(--ink);background:var(--surface);border:1px solid var(--axis);
 border-radius:6px;padding:4px 10px;cursor:pointer}
button[aria-pressed="true"]{background:var(--grid)}
:focus-visible{outline:2px solid var(--focus);outline-offset:2px}
.layout{display:grid;grid-template-columns:minmax(0,1fr);gap:14px}
@media (min-width:900px){.layout{grid-template-columns:minmax(0,1fr) 320px}}
#chart{width:100%;height:min(72vh,680px);display:block;touch-action:pan-y;background:var(--surface);border-radius:8px}
.legend{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:.82rem;color:var(--ink2);margin-top:8px}
.legend .sw{display:inline-block;width:12px;height:12px;border-radius:2px;margin-right:4px;vertical-align:-2px;
 border:1px solid var(--ring)}
.scale{display:flex;align-items:center;gap:6px}
.scale .bar{display:flex}
.scale .bar span{width:18px;height:12px;border:1px solid var(--surface)}
#panel h2{font-size:1rem;margin:0 0 .4rem}
#panel .kv{color:var(--ink2);font-size:.86rem;margin:.2rem 0 .6rem}
#panel .ex{border-top:1px solid var(--grid);padding:.5rem 0;font-size:.86rem}
#panel .ex .meta{color:var(--muted);font-size:.78rem}
#panel mark{background:transparent;color:var(--ink);font-weight:700;text-decoration:underline}
#panel .hint{color:var(--muted);font-size:.86rem}
.tooltip{position:fixed;pointer-events:none;background:var(--surface);color:var(--ink);border:1px solid var(--ring);
 border-radius:6px;padding:6px 8px;font-size:.82rem;box-shadow:0 2px 10px rgba(0,0,0,.12);max-width:260px;display:none}
.tooltip .v{font-weight:700;font-variant-numeric:tabular-nums}
.tooltip .l{color:var(--ink2)}
details{margin-top:14px}
summary{cursor:pointer;color:var(--ink2)}
.tablewrap{overflow-x:auto;max-width:100%}
table{border-collapse:collapse;font-size:.82rem;width:100%}
th,td{padding:4px 8px;border-bottom:1px solid var(--grid);text-align:left;white-space:nowrap}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
th{cursor:pointer;color:var(--ink2);position:sticky;top:0;background:var(--surface)}
th[aria-sort] ::after{content:""}
footer{color:var(--muted);font-size:.78rem;margin-top:18px;overflow-wrap:anywhere}
.warn{color:var(--ink2);font-size:.84rem;margin:.4rem 0}
svg text{font:11px system-ui,-apple-system,"Segoe UI",sans-serif;fill:var(--ink);paint-order:stroke;stroke:var(--surface);
 stroke-width:3px;stroke-linejoin:round;pointer-events:none}
.node path{stroke:var(--muted);stroke-width:1px;cursor:pointer}
.node.dim,.link.dim{opacity:.12}
.node:focus{outline:none}.node:focus path{stroke:var(--focus);stroke-width:3px}
.link{stroke:var(--edge);cursor:pointer}
@media (forced-colors:active){.node path{forced-color-adjust:none}}
"""


def _page(title: str, subtitle: str, body: str, data, script: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{CSS}</style>
</head>
<body>
<main>
<h1>{html.escape(title)}</h1>
<p class="sub">{html.escape(subtitle)}</p>
{body}
</main>
<div class="tooltip" id="tip" role="status" aria-live="polite"></div>
<script id="network-data" type="application/json">{embed_json(data)}</script>
<script src="{D3}"></script>
<script>{script}</script>
</body>
</html>
"""


COMMON_JS = r"""
const DATA = JSON.parse(document.getElementById('network-data').textContent);
const fmt = d3.format(',');
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const tip = document.getElementById('tip');
function showTip(ev, rows){
  tip.replaceChildren();
  for (const [v, l] of rows){ const p = document.createElement('div');
    const a = document.createElement('span'); a.className='v'; a.textContent = v;
    const b = document.createElement('span'); b.className='l'; b.textContent = ' ' + l;
    p.append(a, b); tip.append(p); }
  tip.style.display = 'block';
  const x = Math.min(ev.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
  const y = Math.min(ev.clientY + 14, window.innerHeight - tip.offsetHeight - 8);
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
}
function hideTip(){ tip.style.display = 'none'; }
function el(tag, attrs={}, text){ const e = document.createElement(tag);
  for (const [k,v] of Object.entries(attrs)) e.setAttribute(k, v); if (text !== undefined) e.textContent = text; return e; }
function kwicLine(k){ const p = el('div');
  p.append(document.createTextNode('…' + (k.left || '')), el('mark', {}, k.match || ''), document.createTextNode((k.right || '') + '…'));
  return p; }
function sortableTable(container, columns, rows){
  const wrap = el('div', {class:'tablewrap'}); const t = el('table'); const thead = el('thead'); const tr = el('tr');
  let key = null, dir = -1;
  columns.forEach((c) => { const th = el('th', {scope:'col', tabindex:'0', class: c.num ? 'n' : ''}, c.label);
    const go = () => { dir = key === c.key ? -dir : -1; key = c.key;
      tr.querySelectorAll('th').forEach((x) => x.removeAttribute('aria-sort'));
      th.setAttribute('aria-sort', dir < 0 ? 'descending' : 'ascending'); fill(); };
    th.addEventListener('click', go); th.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
    tr.append(th); });
  thead.append(tr); t.append(thead); const tb = el('tbody'); t.append(tb);
  function fill(){ const rs = rows.slice(); if (key) rs.sort((a,b) => { const x = a[key], y = b[key];
      return (x === y ? 0 : (x === null || x === undefined) ? 1 : (y === null || y === undefined) ? -1 : (x > y ? 1 : -1)) * dir; });
    tb.replaceChildren(...rs.map((r) => { const row = el('tr');
      columns.forEach((c) => { let v = r[c.key]; if (typeof v === 'number' && c.digits !== undefined) v = v.toFixed(c.digits);
        else if (typeof v === 'number') v = fmt(v); row.append(el('td', {class: c.num ? 'n' : ''}, v === null || v === undefined ? '' : String(v))); });
      return row; })); }
  fill(); wrap.append(t); container.append(wrap);
}
function themeButton(){
  const b = document.getElementById('theme'); if (!b) return;
  b.addEventListener('click', () => { const r = document.documentElement;
    const cur = r.getAttribute('data-theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    r.setAttribute('data-theme', cur === 'dark' ? 'light' : 'dark'); window.dispatchEvent(new Event('themechange')); });
}
"""

COOC_JS = r"""
const G = DATA.groups;                       // null without groups
const HAS_BIAS = !!(G && G.contrast && G.contrast.length === 2);
const nodes = DATA.nodes.filter((d) => d.in_network).map((d) => ({...d, id: d.name}));
const links = DATA.edges.map((e) => ({...e}));
const byId = new Map(nodes.map((d) => [d.id, d]));
const SHAPE = {concepto: d3.symbolCircle, institucion: d3.symbolSquare, persona: d3.symbolDiamond};
const SHAPE_LABEL = {concepto: 'concept', institucion: 'institution', persona: 'person'};
const BINS = [-1, -0.6, -0.3, -0.1, 0.1, 0.3, 0.6, 1.0001];          // 7 bins → 7 steps
function biasVar(b){ if (b === null || b === undefined) return '--c0';
  // bias > 0 = group 1 (orange, d-steps negative), < 0 = group 2 (blue)
  const i = BINS.findIndex((x, k) => b >= x && b < BINS[k + 1]); return ['--d3','--d2','--d1','--d0','--d-1','--d-2','--d-3'][i]; }
const commColour = (c) => (c !== null && c < 8) ? `--c${c + 1}` : '--c0';
function fillOf(d){ return css(HAS_BIAS ? biasVar(d.bias) : commColour(d.community)); }

const svg = d3.select('#chart'); const width = () => svg.node().clientWidth || 800, height = () => svg.node().clientHeight || 600;
function setViewBox(){ svg.attr('viewBox', [-width() / 2, -height() / 2, width(), height()]); }
setViewBox();
const root = svg.append('g');
const zoom = d3.zoom().scaleExtent([0.3, 6])
  .filter((ev) => !ev.touches || ev.touches.length > 1)              // one finger scrolls the page
  .on('zoom', (ev) => root.attr('transform', ev.transform));
svg.call(zoom);
const coMax = d3.max(links, (d) => d.co) || 1;
const wScale = d3.scaleSqrt().domain([DATA.parameters.min_co, coMax]).range([0.8, 7]);
const oScale = d3.scaleLinear().domain([DATA.parameters.min_npmi, d3.max(links, (d) => d.npmi) || 1]).range([0.25, 0.9]).clamp(true);
let sizeKey = 'n';
const rScale = () => d3.scaleSqrt().domain([0, d3.max(nodes, (d) => d[sizeKey] || 0) || 1]).range([4, 26]);

const link = root.append('g').selectAll('line').data(links).join('line').attr('class', 'link')
  .attr('stroke-width', (d) => wScale(d.co)).attr('stroke-opacity', (d) => oScale(d.npmi));
const node = root.append('g').selectAll('g').data(nodes).join('g').attr('class', 'node').attr('tabindex', 0)
  .attr('role', 'button').attr('aria-label', (d) => `${d.name}, ${SHAPE_LABEL[d.type]}, in ${fmt(d.n)} interventions`);
node.append('path');
const label = root.append('g').selectAll('text').data(nodes).join('text').text((d) => d.name).attr('dy', -10)
  .attr('text-anchor', 'middle');
function drawNodes(){ const r = rScale();
  node.select('path').attr('d', (d) => d3.symbol(SHAPE[d.type] || d3.symbolCircle, Math.PI * r(d[sizeKey] || 0) ** 2)())
    .attr('fill', fillOf);
  label.attr('dy', (d) => -r(d[sizeKey] || 0) - 4); }
drawNodes();

const sim = d3.forceSimulation(nodes).randomSource(d3.randomLcg(DATA.parameters.seed / 1000 % 1))
  .force('link', d3.forceLink(links).id((d) => d.id).distance((d) => 140 - 90 * Math.max(0, d.npmi)).strength(0.4))
  .force('charge', d3.forceManyBody().strength(-260))
  .force('center', d3.forceCenter(0, 0))
  .force('x0', d3.forceX(0).strength(0.04)).force('y0', d3.forceY(0).strength(0.06))
  .force('collide', d3.forceCollide().radius((d) => rScale()(d[sizeKey] || 0) + 6)).stop();
for (let i = 0; i < 400; i++) sim.tick();                           // layout computed before drawing: same seed, same picture
function render(){
  link.attr('x1', (d) => d.source.x).attr('y1', (d) => d.source.y).attr('x2', (d) => d.target.x).attr('y2', (d) => d.target.y);
  node.attr('transform', (d) => `translate(${d.x},${d.y})`); label.attr('x', (d) => d.x).attr('y', (d) => d.y); }
sim.on('tick', render); render();
function fit(animate){ const shown = nodes.filter((d) => node.filter((x) => x === d).style('display') !== 'none');
  if (!shown.length) return; const pad = 40;
  const [x0, x1] = d3.extent(shown, (d) => d.x), [y0, y1] = d3.extent(shown, (d) => d.y);
  const k = Math.min(3, 0.95 / Math.max((x1 - x0 + 2 * pad) / width(), (y1 - y0 + 2 * pad) / height()));
  const t = d3.zoomIdentity.scale(k).translate(-(x0 + x1) / 2, -(y0 + y1) / 2);
  (animate ? svg.transition().duration(300) : svg).call(zoom.transform, t); }
window.addEventListener('resize', () => { setViewBox(); fit(false); });
node.call(d3.drag().on('start', (ev, d) => { if (!ev.active) sim.alphaTarget(0.2).restart(); d.fx = d.x; d.fy = d.y; })
  .on('drag', (ev, d) => { d.fx = ev.x; d.fy = ev.y; }).on('end', (ev, d) => { if (!ev.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }));

// thresholds, labels, split by group, size metric
let minCo = DATA.parameters.min_co, minNpmi = DATA.parameters.min_npmi;
const visible = (l) => l.co >= minCo && l.npmi >= minNpmi;
function applyFilters(){ link.style('display', (l) => visible(l) ? null : 'none');
  const live = new Set(); links.forEach((l) => { if (visible(l)) { live.add(l.source.id); live.add(l.target.id); } });
  node.style('display', (d) => live.has(d.id) ? null : 'none'); label.style('display', (d) => live.has(d.id) && (showLabels || topLabels.has(d.id)) ? null : 'none');
  document.getElementById('shown').textContent = `${fmt(live.size)} nodes · ${fmt(links.filter(visible).length)} edges shown`; }
// names: the biggest nodes always (8 on a phone, 20 otherwise); all of them on demand
let showLabels = false;
const topLabels = new Set(nodes.slice().sort((a, b) => b.n - a.n).slice(0, innerWidth < 600 ? 8 : 20).map((d) => d.id));
const coIn = document.getElementById('minco'), npIn = document.getElementById('minnpmi');
coIn.min = DATA.parameters.min_co; coIn.max = coMax; coIn.value = minCo;
npIn.min = DATA.parameters.min_npmi; npIn.max = Math.max(DATA.parameters.min_npmi, d3.max(links, (d) => d.npmi) || 1); npIn.step = 0.01; npIn.value = minNpmi;
const outCo = document.getElementById('mincoOut'), outNp = document.getElementById('minnpmiOut');
coIn.addEventListener('input', () => { minCo = +coIn.value; outCo.textContent = fmt(minCo); applyFilters(); });
npIn.addEventListener('input', () => { minNpmi = +npIn.value; outNp.textContent = minNpmi.toFixed(2); applyFilters(); });
outCo.textContent = fmt(minCo); outNp.textContent = minNpmi.toFixed(2);
document.getElementById('labels').addEventListener('click', (e) => { showLabels = !showLabels;
  e.currentTarget.setAttribute('aria-pressed', String(showLabels)); applyFilters(); });
const splitBtn = document.getElementById('split');
if (!HAS_BIAS) splitBtn.hidden = true;
splitBtn.addEventListener('click', (e) => { const on = e.currentTarget.getAttribute('aria-pressed') !== 'true';
  e.currentTarget.setAttribute('aria-pressed', String(on));
  sim.force('x', on ? d3.forceX((d) => width() / 2 - (d.bias || 0) * width() * 0.36).strength(0.35) : null).alpha(0.8).restart(); });
document.getElementById('size').addEventListener('change', (e) => { sizeKey = e.target.value; drawNodes();
  sim.force('collide', d3.forceCollide().radius((d) => rScale()(d[sizeKey] || 0) + 6)).alpha(0.4).restart(); });
document.getElementById('reset').addEventListener('click', () => fit(true));
sim.on('end', () => fit(true));
window.addEventListener('themechange', drawNodes);
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', drawNodes);

// neighbours, tooltip, details
const nbr = new Map(nodes.map((d) => [d.id, new Set([d.id])]));
links.forEach((l) => { nbr.get(l.source.id || l.source).add(l.target.id || l.target); nbr.get(l.target.id || l.target).add(l.source.id || l.source); });
function focusNode(d){ const s = nbr.get(d.id); node.classed('dim', (x) => !s.has(x.id));
  link.classed('dim', (l) => l.source.id !== d.id && l.target.id !== d.id); }
function clearFocus(){ node.classed('dim', false); link.classed('dim', false); }
function nodeRows(d){ const r = [[fmt(d.n), 'interventions'], [fmt(d.strength), 'weighted degree'], [String(d.degree), 'co-mentioned entities']];
  if (HAS_BIAS && d.bias !== null && d.bias !== undefined) r.push([d.bias.toFixed(2), `bias (+ ${G.contrast[0]}, − ${G.contrast[1]})`]);
  if (d.community !== null) r.push([String(d.community + 1), 'community']); return [[d.name, SHAPE_LABEL[d.type]], ...r]; }
node.on('mouseenter', (ev, d) => { focusNode(d); showTip(ev, nodeRows(d)); }).on('mousemove', (ev, d) => showTip(ev, nodeRows(d)))
  .on('mouseleave', () => { clearFocus(); hideTip(); })
  .on('focus', (ev, d) => focusNode(d)).on('blur', clearFocus)
  .on('click', (ev, d) => showNode(d)).on('keydown', (ev, d) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); showNode(d); } });
link.on('mouseenter', (ev, l) => showTip(ev, [[`${l.source.id} – ${l.target.id}`, ''], [fmt(l.co), 'interventions together'],
    [l.npmi.toFixed(3), 'NPMI'], ...(HAS_BIAS ? G.contrast.map((g) => [fmt(l['co_' + g] || 0), 'by ' + g]) : [])]))
  .on('mouseleave', hideTip).on('click', (ev, l) => showEdge(l));
const panel = document.getElementById('panel');
function showNode(d){ panel.replaceChildren(el('h2', {}, d.name),
    el('p', {class:'kv'}, nodeRows(d).slice(1).map(([v, l]) => `${v} ${l}`).join(' · ')));
  for (const k of (DATA.kwic[d.name] || [])) { const box = el('div', {class:'ex'});
    box.append(el('div', {class:'meta'}, [k.date, k.speaker, k.party].filter(Boolean).join(' · ') + ' · ' + k.id_int), kwicLine(k)); panel.append(box); }
  const al = (DATA.alerts || {})[d.name]; if (al) al.forEach((a) => panel.append(el('p', {class:'warn'}, '⚠ ' + a))); }
function showEdge(l){ panel.replaceChildren(el('h2', {}, `${l.source.id} – ${l.target.id}`),
    el('p', {class:'kv'}, `${fmt(l.co)} interventions together · NPMI ${l.npmi.toFixed(3)} · Jaccard ${l.jaccard.toFixed(3)}`));
  for (const x of (l.examples || [])) { const box = el('div', {class:'ex'});
    box.append(el('div', {class:'meta'}, [x.date, x.speaker, x.party].filter(Boolean).join(' · ') + ' · ' + x.id_int));
    if (x.a) box.append(kwicLine(x.a)); if (x.b) box.append(kwicLine(x.b)); panel.append(box); } }

// legend
const lg = document.getElementById('legend');
for (const [t, s] of Object.entries(SHAPE_LABEL)) { const sp = el('span'); const sv = d3.create('svg').attr('width', 14).attr('height', 14);
  sv.append('path').attr('d', d3.symbol(SHAPE[t], 80)()).attr('transform', 'translate(7,7)').attr('fill', 'var(--muted)');
  sp.append(sv.node(), document.createTextNode(' ' + s)); lg.append(sp); }
if (HAS_BIAS) { const sc = el('span', {class:'scale'}); sc.append(document.createTextNode(G.contrast[0]));
  const bar = el('span', {class:'bar'}); ['--d-3','--d-2','--d-1','--d0','--d1','--d2','--d3'].forEach((v) => { const s = el('span'); s.style.background = `var(${v})`; bar.append(s); });
  sc.append(bar, document.createTextNode(G.contrast[1] + ' (bias: share of each group\'s interventions)')); lg.append(sc); }
else { const comms = [...new Set(nodes.map((d) => d.community))].sort((a, b) => a - b);
  comms.forEach((c) => { const sp = el('span'); const sw = el('span', {class:'sw'}); sw.style.background = `var(${commColour(c)})`;
    sp.append(sw, document.createTextNode(c < 8 ? `community ${c + 1}` : 'other communities')); lg.append(sp); }); }
lg.append(el('span', {}, 'size = ' + 'interventions (√) · edge width = co · edge opacity = NPMI'));

// twin tables
const nodeCols = [{key:'name', label:'entity'}, {key:'type', label:'type'}, {key:'n', label:'n', num:true}]
  .concat(HAS_BIAS ? [...G.contrast, 'rest'].map((g) => ({key:'n_' + g, label:'n ' + g, num:true})).concat([{key:'bias', label:'bias', num:true, digits:3}]) : [])
  .concat([{key:'strength', label:'weighted degree', num:true}, {key:'betweenness', label:'betweenness', num:true, digits:4},
           {key:'community_1', label:'community', num:true}]);
sortableTable(document.getElementById('tnodes'), nodeCols, DATA.nodes.map((d) => ({...d, community_1: d.community === null ? null : d.community + 1})));
const edgeCols = [{key:'source', label:'a'}, {key:'target', label:'b'}, {key:'co', label:'co', num:true}]
  .concat(HAS_BIAS ? [...G.contrast, 'rest'].map((g) => ({key:'co_' + g, label:'co ' + g, num:true})) : [])
  .concat([{key:'npmi', label:'NPMI', num:true, digits:3}, {key:'jaccard', label:'Jaccard', num:true, digits:3}]);
sortableTable(document.getElementById('tedges'), edgeCols, DATA.edges);
applyFilters(); fit(false); themeButton();
"""


def cooccurrence_page(res: dict) -> str:
    p = res["parameters"]
    country = res["country"]
    library = (p.get("filters") or {}).get("library") or ""
    title = f"Co-mention network · {library} · {country}"
    s = res["stats"]
    subtitle = (f"{res['N']:,} interventions · {s['nodes']} entities · {s['edges']} edges · co ≥ {p['min_co']}"
                f"{' (automatic)' if p['min_co_auto'] else ''} · NPMI ≥ {p['min_npmi']} · communities: Leiden, seed {p['seed']}")
    groups = res.get("groups")
    body = f"""
<div class="layout">
 <section class="card" aria-label="Network">
  <div class="controls">
   <label>min co <input type="range" id="minco"><output id="mincoOut"></output></label>
   <label>min NPMI <input type="range" id="minnpmi"><output id="minnpmiOut"></output></label>
   <label>size <select id="size"><option value="n">interventions</option><option value="strength">weighted degree</option>
     <option value="betweenness">betweenness</option></select></label>
   <button id="labels" aria-pressed="false">all labels</button>
   <button id="split" aria-pressed="false">separate by group</button>
   <button id="reset">reset view</button>
   <button id="theme" aria-label="switch light or dark theme">theme</button>
  </div>
  <svg id="chart" role="img" aria-label="Network of entities mentioned together; the same data are in the tables below"></svg>
  <div class="legend" id="legend"></div>
  <p class="sub" id="shown" aria-live="polite"></p>
 </section>
 <aside class="card" id="panel" aria-live="polite"><p class="hint">Hover or focus an entity to highlight its
  neighbours; click it (or press Enter) to read examples. Click an edge to read interventions where both appear.
  One finger scrolls the page; pinch or use the mouse wheel to zoom.</p></aside>
</div>
<details><summary>Entities (table)</summary><div id="tnodes"></div></details>
<details><summary>Edges (table)</summary><div id="tedges"></div></details>
<footer>
 <p><strong>How to read it.</strong> co = interventions where both entities appear (volume). NPMI = how much more
 than chance they appear together, from −1 to 1 (affinity); thresholds use the unrounded value. Read them
 separately: a large co with a low NPMI is two frequent entities, not an association.
 {('Bias = (n₁/N₁ − n₂/N₂)/(n₁/N₁ + n₂/N₂): positive leans to ' + html.escape(groups['contrast'][0]) +
   ', negative to ' + html.escape(groups['contrast'][1]) + '. The groups were defined by the user.') if groups and len(groups.get('contrast') or []) == 2 else ''}</p>
 <p>Data: {' · '.join(html.escape(c) for c in res['citation'])}. CC BY 4.0.</p>
 <p>Generated with {html.escape(p['engine'])} on {html.escape(p['generated'])}.</p>
</footer>"""
    return _page(title, subtitle, body, res, COMMON_JS + COOC_JS)


MENTION_CSS = r"""
.heat td.cell{text-align:right;font-variant-numeric:tabular-nums;min-width:70px}
.heat th{position:static}
.views{display:flex;gap:6px;margin-bottom:8px}
.arrowhead{fill:var(--edge)}
"""

MENTION_JS = r"""
const groupsOrder = [...new Set(DATA.nodes.map((d) => d.group))]
  .sort((a, b) => d3.sum(DATA.nodes.filter((x) => x.group === b), (x) => x.in_strength + x.out_strength)
                - d3.sum(DATA.nodes.filter((x) => x.group === a), (x) => x.in_strength + x.out_strength));
const slot = new Map(groupsOrder.filter((g) => g !== 'external').slice(0, 8).map((g, i) => [g, `--c${i + 1}`]));
const colourOf = (g) => g === 'external' ? '--muted' : (slot.get(g) || '--c0');
const nodes = DATA.nodes.map((d) => ({...d}));
const links = DATA.edges.map((e) => ({...e}));
const svg = d3.select('#chart'); const width = () => svg.node().clientWidth || 800, height = () => svg.node().clientHeight || 600;
function setViewBox(){ svg.attr('viewBox', [-width() / 2, -height() / 2, width(), height()]); } setViewBox();
svg.append('defs').append('marker').attr('id', 'arrow').attr('viewBox', '0 -4 8 8').attr('refX', 8).attr('refY', 0)
  .attr('markerWidth', 6).attr('markerHeight', 6).attr('orient', 'auto').append('path').attr('d', 'M0,-4L8,0L0,4').attr('class', 'arrowhead');
const root = svg.append('g');
const zoom = d3.zoom().scaleExtent([0.3, 6]).filter((ev) => !ev.touches || ev.touches.length > 1)
  .on('zoom', (ev) => root.attr('transform', ev.transform)); svg.call(zoom);
const r = d3.scaleSqrt().domain([0, d3.max(nodes, (d) => d.in_strength) || 1]).range([4, 24]);
const w = d3.scaleSqrt().domain([1, d3.max(links, (d) => d.interventions) || 1]).range([0.8, 5]);
const link = root.append('g').selectAll('line').data(links).join('line').attr('class', 'link')
  .attr('stroke-width', (d) => w(d.interventions)).attr('stroke-opacity', 0.55).attr('marker-end', 'url(#arrow)');
const node = root.append('g').selectAll('g').data(nodes).join('g').attr('class', 'node').attr('tabindex', 0).attr('role', 'button')
  .attr('aria-label', (d) => `${d.name}, ${d.group}, mentioned in ${fmt(d.in_strength)} interventions, mentions others in ${fmt(d.out_strength)}`);
node.append('path');
const label = root.append('g').selectAll('text').data(nodes).join('text').text((d) => d.name).attr('text-anchor', 'middle');
function draw(){ node.select('path').attr('d', (d) => d3.symbol(d.kind === 'external' ? d3.symbolSquare : d3.symbolCircle,
    Math.PI * r(d.in_strength) ** 2)()).attr('fill', (d) => css(colourOf(d.group)));
  label.attr('dy', (d) => -r(d.in_strength) - 4); }
draw(); window.addEventListener('themechange', draw); matchMedia('(prefers-color-scheme: dark)').addEventListener('change', draw);
const sim = d3.forceSimulation(nodes).randomSource(d3.randomLcg(DATA.parameters.seed / 1000 % 1))
  .force('link', d3.forceLink(links).id((d) => d.id).distance(120).strength(0.25))
  .force('charge', d3.forceManyBody().strength(-280)).force('center', d3.forceCenter(0, 0))
  .force('x0', d3.forceX(0).strength(0.05)).force('y0', d3.forceY(0).strength(0.07))
  .force('collide', d3.forceCollide().radius((d) => r(d.in_strength) + 8)).stop();
for (let i = 0; i < 400; i++) sim.tick();
function trim(l){ const dx = l.target.x - l.source.x, dy = l.target.y - l.source.y, len = Math.hypot(dx, dy) || 1, k = (r(l.target.in_strength) + 3) / len;
  return [l.target.x - dx * k, l.target.y - dy * k]; }
function render(){ link.attr('x1', (d) => d.source.x).attr('y1', (d) => d.source.y)
    .attr('x2', (d) => trim(d)[0]).attr('y2', (d) => trim(d)[1]);
  node.attr('transform', (d) => `translate(${d.x},${d.y})`); label.attr('x', (d) => d.x).attr('y', (d) => d.y); }
sim.on('tick', render); render();
node.call(d3.drag().on('start', (ev, d) => { if (!ev.active) sim.alphaTarget(0.2).restart(); d.fx = d.x; d.fy = d.y; })
  .on('drag', (ev, d) => { d.fx = ev.x; d.fy = ev.y; }).on('end', (ev, d) => { if (!ev.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }));
function fit(animate){ const shown = nodes.filter((d) => node.filter((x) => x === d).style('display') !== 'none'); if (!shown.length) return;
  const pad = 40, [x0, x1] = d3.extent(shown, (d) => d.x), [y0, y1] = d3.extent(shown, (d) => d.y);
  const k = Math.min(3, 0.95 / Math.max((x1 - x0 + 2 * pad) / width(), (y1 - y0 + 2 * pad) / height()));
  (animate ? svg.transition().duration(300) : svg).call(zoom.transform, d3.zoomIdentity.scale(k).translate(-(x0 + x1) / 2, -(y0 + y1) / 2)); }
window.addEventListener('resize', () => { setViewBox(); fit(false); });

// filters
let minM = DATA.parameters.min_mentions, fromGroup = '', showExt = true, showDep = true, showLabels = false;
const topLabels = new Set(nodes.slice().sort((a, b) => (b.in_strength + b.out_strength) - (a.in_strength + a.out_strength))
  .slice(0, innerWidth < 600 ? 8 : 20).map((d) => d.id));
const mIn = document.getElementById('minm'); mIn.min = DATA.parameters.min_mentions; mIn.max = d3.max(links, (d) => d.interventions) || 1; mIn.value = minM;
const mOut = document.getElementById('minmOut'); mOut.textContent = fmt(minM);
const gSel = document.getElementById('from'); groupsOrder.filter((g) => g !== 'external').forEach((g) => gSel.append(el('option', {value: g}, g)));
const byId = new Map(nodes.map((d) => [d.id, d]));
const linkOk = (l) => l.interventions >= minM && (!fromGroup || l.source.group === fromGroup)
  && (showExt || (l.source.kind !== 'external' && l.target.kind !== 'external')) && (showDep || (l.target.kind === 'external'));
function apply(){ link.style('display', (l) => linkOk(l) ? null : 'none');
  const live = new Set(); links.forEach((l) => { if (linkOk(l)) { live.add(l.source.id); live.add(l.target.id); } });
  node.style('display', (d) => live.has(d.id) ? null : 'none'); label.style('display', (d) => live.has(d.id) && (showLabels || topLabels.has(d.id)) ? null : 'none');
  document.getElementById('shown').textContent = `${fmt(live.size)} people · ${fmt(links.filter(linkOk).length)} directed edges shown`; }
mIn.addEventListener('input', () => { minM = +mIn.value; mOut.textContent = fmt(minM); apply(); });
gSel.addEventListener('change', () => { fromGroup = gSel.value; apply(); });
document.getElementById('ext').addEventListener('change', (e) => { showExt = e.target.checked; apply(); });
document.getElementById('dep').addEventListener('change', (e) => { showDep = e.target.checked; apply(); });
document.getElementById('labels').addEventListener('click', (e) => { showLabels = !showLabels; e.currentTarget.setAttribute('aria-pressed', String(showLabels)); apply(); });
document.getElementById('reset').addEventListener('click', () => fit(true));

// neighbours, tooltip, details
function focusNode(d){ const s = new Set([d.id]); links.forEach((l) => { if (l.source.id === d.id) s.add(l.target.id); if (l.target.id === d.id) s.add(l.source.id); });
  node.classed('dim', (x) => !s.has(x.id)); link.classed('dim', (l) => l.source.id !== d.id && l.target.id !== d.id); }
function clearFocus(){ node.classed('dim', false); link.classed('dim', false); }
const rows = (d) => [[d.name, d.group + (d.role ? ' · ' + d.role : '')], [fmt(d.in_strength), 'interventions mention them'],
  [fmt(d.out_strength), 'interventions where they mention others'], [String(d.pagerank), 'PageRank']];
node.on('mouseenter', (ev, d) => { focusNode(d); showTip(ev, rows(d)); }).on('mousemove', (ev, d) => showTip(ev, rows(d)))
  .on('mouseleave', () => { clearFocus(); hideTip(); }).on('focus', (ev, d) => focusNode(d)).on('blur', clearFocus)
  .on('click', (ev, d) => showNode(d)).on('keydown', (ev, d) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); showNode(d); } });
link.on('mouseenter', (ev, l) => showTip(ev, [[`${l.source.name} → ${l.target.name}`, ''], [fmt(l.interventions), 'interventions'],
    [fmt(l.mentions), 'mentions'], [fmt(l.sessions), 'sessions']])).on('mouseleave', hideTip).on('click', (ev, l) => showEdge(l));
const panel = document.getElementById('panel');
function list(title, items){ if (!items.length) return document.createTextNode(''); const box = el('div', {class:'ex'}); box.append(el('div', {class:'meta'}, title));
  const ul = el('ul'); items.slice(0, 8).forEach(([n, v]) => ul.append(el('li', {}, `${n} — ${fmt(v)}`))); box.append(ul); return box; }
function showNode(d){ const inn = links.filter((l) => l.target.id === d.id).map((l) => [l.source.name, l.interventions]).sort((a, b) => b[1] - a[1]);
  const out = links.filter((l) => l.source.id === d.id).map((l) => [l.target.name, l.interventions]).sort((a, b) => b[1] - a[1]);
  panel.replaceChildren(el('h2', {}, d.name), el('p', {class:'kv'}, rows(d).slice(1).map(([v, l]) => `${v} ${l}`).join(' · ')),
    list('Mentioned most by', inn), list('Mentions most', out)); }
function showEdge(l){ panel.replaceChildren(el('h2', {}, `${l.source.name} → ${l.target.name}`),
    el('p', {class:'kv'}, `${fmt(l.interventions)} interventions · ${fmt(l.mentions)} mentions · ${fmt(l.sessions)} sessions`));
  (l.examples || []).forEach((x) => { const box = el('div', {class:'ex'}); box.append(el('div', {class:'meta'}, x.id_int), kwicLine(x)); panel.append(box); }); }

// legend
const lg = document.getElementById('legend');
groupsOrder.forEach((g) => { const sp = el('span'); const sw = el('span', {class:'sw'}); sw.style.background = `var(${colourOf(g)})`;
  if (g === 'external') sw.style.borderRadius = '0'; sp.append(sw, document.createTextNode(g === 'external' ? 'external actors (square)'
    : (slot.has(g) ? g : g + ' (other)'))); lg.append(sp); });
lg.append(el('span', {}, 'size = interventions that mention them (√) · arrow = who mentions whom · width = interventions'));

// heat map group → group (also its own table)
const heat = document.getElementById('heat');
// senders are the groups that speak; external actors only receive (their own column, outside the colour scale,
// because they would flatten the comparison between the chamber's groups)
const senders = [...new Set(DATA.block_matrix.map((b) => b.from))].filter((g) => g !== 'external');
const hasExt = DATA.block_matrix.some((b) => b.to === 'external');
const cols = [...senders, ...new Set(DATA.block_matrix.map((b) => b.to).filter((g) => g !== 'external' && !senders.includes(g)))];
const val = new Map(DATA.block_matrix.map((b) => [b.from + '\u0000' + b.to, b]));
const maxv = d3.max(DATA.block_matrix.filter((b) => b.to !== 'external'), (b) => b.per_100_interventions) || 1;
const t = el('table', {class:'heat'}); const hr = el('tr'); hr.append(el('th', {scope:'col'}, 'from \\ to'));
cols.forEach((g) => hr.append(el('th', {scope:'col'}, g))); if (hasExt) hr.append(el('th', {scope:'col'}, 'external actors'));
t.append(hr);
senders.forEach((ga) => { const tr = el('tr'); tr.append(el('th', {scope:'row'}, ga));
  [...cols, ...(hasExt ? ['external'] : [])].forEach((gb) => { const b = val.get(ga + '\u0000' + gb);
    const td = el('td', {class:'cell'}, b ? `${b.per_100_interventions.toFixed(1)} (${fmt(b.mentions)})` : '—');
    if (b && gb !== 'external') { const i = Math.min(4, Math.floor(5 * b.per_100_interventions / maxv));
      td.style.background = `var(--s${i})`; td.style.color = `var(--t${i})`; td.dataset.step = i; }
    tr.append(td); }); t.append(tr); });
heat.append(el('p', {class:'sub'}, 'Mentions per 100 interventions of the sending group (count in brackets), in five ' +
  'steps from the lowest to the highest value between the chamber\'s groups; in the dark theme, lighter = more.' +
  (hasExt ? ' Mentions of external actors are in the last column, uncoloured.' : '')), t);
document.getElementById('vgraph').addEventListener('click', () => { document.getElementById('graphview').hidden = false; heat.hidden = true;
  document.getElementById('vgraph').setAttribute('aria-pressed', 'true'); document.getElementById('vheat').setAttribute('aria-pressed', 'false'); fit(false); });
document.getElementById('vheat').addEventListener('click', () => { document.getElementById('graphview').hidden = true; heat.hidden = false;
  document.getElementById('vgraph').setAttribute('aria-pressed', 'false'); document.getElementById('vheat').setAttribute('aria-pressed', 'true'); });

// twin tables
sortableTable(document.getElementById('tnodes'), [{key:'name', label:'person'}, {key:'group', label:'group'}, {key:'kind', label:'kind'},
  {key:'in_strength', label:'mentioned in', num:true}, {key:'out_strength', label:'mentions others in', num:true},
  {key:'pagerank', label:'PageRank', num:true, digits:4}, {key:'community', label:'community', num:true}], DATA.nodes);
sortableTable(document.getElementById('tedges'), [{key:'source_name', label:'from'}, {key:'target_name', label:'to'},
  {key:'interventions', label:'interventions', num:true}, {key:'mentions', label:'mentions', num:true}, {key:'sessions', label:'sessions', num:true}], DATA.edges);
apply(); fit(false); themeButton();
"""


def mention_page(res: dict) -> str:
    p = res["parameters"]
    s = res["stats"]
    library = (p.get("filters") or {}).get("library") or ""
    title = f"Mention network · {library} · {res['country']}"
    subtitle = (f"{res['N']:,} interventions · {s['nodes']} people · {s['edges']} directed edges · counted: "
                f"{', '.join(p['mention_kinds'])} · min {p['min_mentions']} interventions per edge · reciprocity "
                f"{s['reciprocity']}")
    body = f"""
<div class="layout">
 <section class="card" aria-label="Network">
  <div class="views"><button id="vgraph" aria-pressed="true">network</button><button id="vheat" aria-pressed="false">group → group</button>
   <button id="theme" aria-label="switch light or dark theme">theme</button></div>
  <div id="graphview">
   <div class="controls">
    <label>min interventions <input type="range" id="minm"><output id="minmOut"></output></label>
    <label>from group <select id="from"><option value="">all</option></select></label>
    <label><input type="checkbox" id="dep" checked> deputies</label>
    <label><input type="checkbox" id="ext" checked> external actors</label>
    <button id="labels" aria-pressed="false">all labels</button><button id="reset">reset view</button>
   </div>
   <svg id="chart" role="img" aria-label="Directed network of who mentions whom; the same data are in the tables below"></svg>
   <div class="legend" id="legend"></div>
   <p class="sub" id="shown" aria-live="polite"></p>
  </div>
  <div id="heat" hidden></div>
 </section>
 <aside class="card" id="panel" aria-live="polite"><p class="hint">Hover or focus a person to highlight who they
  mention and who mentions them; click (or Enter) for their main senders and receivers. Click an arrow to read
  examples. One finger scrolls the page; pinch or use the mouse wheel to zoom.</p></aside>
</div>
<details><summary>People (table)</summary><div id="tnodes"></div></details>
<details><summary>Directed edges (table)</summary><div id="tedges"></div></details>
<footer>
 <p><strong>How to read it.</strong> An arrow A → B counts the interventions of A that mention B by full name, or by
 surname after a title (legislative or honorific), among the deputies in office that day. Counted here:
 {html.escape(', '.join(p['mention_kinds']))} ('reference' = talking about someone; 'address' = speaking to them).
 Mentions that matched several deputies are listed apart (ambiguous), never assigned at random; forms with no name
 («V. Exa.», «Su Señoría») cannot be resolved and are only counted.</p>
 <p>{html.escape(_coverage_line(res))}</p>
 <p>Data: {' · '.join(html.escape(c) for c in res['citation'])}. CC BY 4.0.</p>
 <p>Generated with {html.escape(p['engine'])} on {html.escape(p['generated'])}.</p>
</footer>"""
    return _page(title, subtitle, body, res, COMMON_JS + MENTION_JS).replace("</style>", MENTION_CSS + "</style>", 1)


def _coverage_line(res: dict) -> str:
    c, f = res["coverage"], res["counts"]["mentions_found"]
    n = lambda k: f"{f.get(k, 0):,}"
    return (f"Register: {c['deputies_in_register_for_the_period']:,} deputies in office in the period. Library: "
            f"{c['library_speakers']:,} speakers, {c['linked_speakers']:,} linked to the register, "
            f"{c['linked_speakers_in_gazetteer']:,} with usable names. Mentions found: {n('reference')} talking about "
            f"someone, {n('address')} speaking to someone, {n('editorial')} in the record's notes (not counted), "
            f"{n('self')} self-mentions, {n('ambiguous')} ambiguous (listed apart); "
            f"{res['counts']['unresolvable_courtesy_forms']:,} forms of address with no name.")
