"""Self-contained interactive HTML pages for the network tools (d3 v7.8.5 from cdnjs).

Data are injected programmatically (networks.embed_json), never typed by hand, and networks._self_check
reads them back from the written file. Text reaches the page only through textContent / d3 .text().

Colour (validated with the dataviz skill's validate_palette.js, 14-oct-2026):
  diverging bias scale, 7 steps, group 1 (orange) ↔ neutral gray ↔ group 2 (blue)
    light: #cf511a #eb6834 #ef906d | #f0efec | #81abe4 #5691dd #2a78d6
    dark:  #d95926 #a75233 #7a4938 | #383835 | #3d597d #3d6fae #3987e5
    every arm: one hue, monotone lightness, gaps ≥ 0.06, near-neutral step ≥ 2:1 on the surface.
  categorical (themes, communities, parties): 30 slots, so that up to 30 groups each have a colour (asked by the
    user; the dataviz skill's default is 8). Slots 1-8 are the reference order (blue, orange, aqua, yellow, magenta,
    green, violet, red; slot 7 lightened to #6250d6 as in the reference); 9-30 were chosen farthest-first in OKLCH
    within the lightness band and the chroma floor, each light colour with its dark step (same hue), and ordered so
    that every adjacent pair passes in both modes (validate_palette.js, 23-oct-2026: worst adjacent CVD ΔE 9.1
    light / 8.4 dark, normal vision 19.6 / 18.7; some slots under 3:1 against the surface, relieved by the labels
    and the tables). With 30 hues not every pair can be told apart: a 31st group and beyond fold into "Other"
    (gray), and names on the discs, sectors and legend, the highlight selector and the twin tables carry identity
    too: colour is never the only channel.
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
 --c1:#2a78d6;--c2:#eb6834;--c3:#1baf7a;--c4:#eda100;--c5:#e87ba4;--c6:#008300;--c7:#6250d6;--c8:#e34948;
 --c9:#1254ac;--c10:#df94cd;--c11:#a31130;--c12:#39b9d6;--c13:#6e399b;--c14:#b0b95f;--c15:#a06cb0;--c16:#d21909;
 --c17:#675ca7;--c18:#ef91a6;--c19:#4f34c9;--c20:#c7187a;--c21:#7985d1;--c22:#bc5365;--c23:#a454e6;--c24:#d07c5b;
 --c25:#dc65e8;--c26:#8b384e;--c27:#7567fe;--c28:#8e158a;--c29:#5e9e5e;--c30:#a14f8f;--c0:#b5b3ad;
 --s0:#86b6ef;--s1:#3987e5;--s2:#256abf;--s3:#184f95;--s4:#0d366b;
 --t0:#0b0b0b;--t1:#0b0b0b;--t2:#ffffff;--t3:#ffffff;--t4:#ffffff;
 --focus:#2a78d6}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])){color-scheme:dark;
 --surface:#1a1a19;--plane:#0d0d0d;--ink:#ffffff;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;
 --ring:rgba(255,255,255,.10);--edge:#c3c2b7;
 --d-3:#d95926;--d-2:#a75233;--d-1:#7a4938;--d0:#383835;--d1:#3d597d;--d2:#3d6fae;--d3:#3987e5;
 --c1:#3987e5;--c2:#d95926;--c3:#199e70;--c4:#c98500;--c5:#d55181;--c6:#008300;--c7:#9085e9;--c8:#e66767;
 --c9:#2060b9;--c10:#be76ad;--c11:#b1243b;--c12:#019fbb;--c13:#7945a8;--c14:#919a3f;--c15:#9764a7;--c16:#d21909;
 --c17:#6a60ab;--c18:#cd7387;--c19:#5843d7;--c20:#c7187a;--c21:#6e79c4;--c22:#b74f61;--c23:#9b4bdd;--c24:#be6c4b;
 --c25:#c54fd1;--c26:#984359;--c27:#6e5ef4;--c28:#9c2796;--c29:#529152;--c30:#a14f8f;--c0:#5c5b57;
 --s0:#184f95;--s1:#256abf;--s2:#3987e5;--s3:#6da7ec;--s4:#9ec5f4;
 --t0:#ffffff;--t1:#ffffff;--t2:#0b0b0b;--t3:#0b0b0b;--t4:#0b0b0b;
 --focus:#3987e5}}
:root[data-theme="dark"]{color-scheme:dark;
 --surface:#1a1a19;--plane:#0d0d0d;--ink:#ffffff;--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;
 --ring:rgba(255,255,255,.10);--edge:#c3c2b7;
 --d-3:#d95926;--d-2:#a75233;--d-1:#7a4938;--d0:#383835;--d1:#3d597d;--d2:#3d6fae;--d3:#3987e5;
 --c1:#3987e5;--c2:#d95926;--c3:#199e70;--c4:#c98500;--c5:#d55181;--c6:#008300;--c7:#9085e9;--c8:#e66767;
 --c9:#2060b9;--c10:#be76ad;--c11:#b1243b;--c12:#019fbb;--c13:#7945a8;--c14:#919a3f;--c15:#9764a7;--c16:#d21909;
 --c17:#6a60ab;--c18:#cd7387;--c19:#5843d7;--c20:#c7187a;--c21:#6e79c4;--c22:#b74f61;--c23:#9b4bdd;--c24:#be6c4b;
 --c25:#c54fd1;--c26:#984359;--c27:#6e5ef4;--c28:#9c2796;--c29:#529152;--c30:#a14f8f;--c0:#5c5b57;
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
.layout.nopanel{grid-template-columns:minmax(0,1fr)}
.layout.nopanel #panel{display:none}
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
svg text.dim{opacity:.15}
.node:focus{outline:none}.node:focus path{stroke:var(--focus);stroke-width:3px}
.link{fill:none;stroke:var(--edge);stroke-linecap:round;pointer-events:none}
.hit{fill:none;stroke:transparent;stroke-width:9px;cursor:pointer}
.guides .ring{fill:none;stroke:var(--grid)}
.guides .sector{stroke:var(--grid)}
.guides .disc{fill:var(--plane);fill-opacity:.55;stroke:var(--grid)}
svg .guides text.ringlab{font-size:10px;fill:var(--muted)}
svg .guides text.sectorlab{font-size:12px;font-weight:600;fill:var(--ink2)}
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
// Network drawing shared by the pages. Semantic zoom: the zoom moves the points, never the marks, so a node,
// a line, a label or an arrowhead keeps its size on screen at every zoom level. Node radius: √ of the size
// variable between MIN_R and the «node size» control; line width: √ of the weight between MIN_W and the
// «edge width» control (thin by default: the weight is read in the tooltip and the tables, not in ink);
// arrowheads have a fixed size, whatever the width of their line.
// Three layouts (the «layout» control; `layout` in the tools):
//   force     force-directed, computed before drawing with a fixed seed;
//   clusters  each group (theme, community, party) laid out on its own with its internal edges, then the groups
//             placed as discs kept apart by a fixed gap, those with more edges between them a little closer;
//   rings     the Diarios Explorer's centrifugal layout (page/23_menciones_red.js): rings by the number of distinct
//             connections among the edges shown (the 3 % most connected in the core, then the next 7 %, 15 %, 30 %
//             and the rest; ties never split), sectors by group, clockwise from 12 by weight, each ordered from the
//             most to the least connected; edges curve towards the centre. The radii grow with √ of the nodes
//             shown beyond 60, so a large network keeps its spacing.
const MIN_R = 2.5, MIN_W = 0.4, ARROW = 6;
const CUTS = [0.03, 0.10, 0.25, 0.55, 1], RADII = [70, 138, 202, 262, 318], GAP_ANGLE = 0.2, CURVE = 0.75, CLUSTER_GAP = 70;
const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;
const f1 = (v) => v.toFixed(1);
function ringBounds(values){                       // fronterasDe of the explorer: quantile cuts moved to the nearest change of value
  const n = values.length, out = []; let prev = 0;
  for (let k = 0; k < CUTS.length - 1; k++){
    const c = Math.max(prev, Math.min(n, Math.round(CUTS[k] * n)));
    let up = c, down = c;
    while (up > prev && up < n && values[up - 1] === values[up]) up--;
    while (down > 0 && down < n && values[down - 1] === values[down]) down++;
    const f = up > prev && (c - up <= down - c || down >= n) ? up : down;
    out.push(f); prev = f; }
  out.push(n); return out; }
function graphView(o){
  const svg = d3.select('#chart');
  const width = () => svg.node().clientWidth || 800, height = () => svg.node().clientHeight || 600;
  const V = DATA.parameters.view || {};
  const ctl = {maxR: +V.max_node_size || 12, maxW: +V.max_edge_width || 1.5, layout: V.layout || 'force'};
  let T = d3.zoomIdentity, live = new Set(o.nodes.map((d) => d.id)), showLabels = false, lastOk = () => true;
  let curve = 0, guide = null, forcePos = null, moving = null;
  svg.attr('viewBox', [0, 0, width(), height()]);
  if (o.directed) svg.append('defs').append('marker').attr('id', 'arrow').attr('markerUnits', 'userSpaceOnUse')
    .attr('viewBox', '0 -4 8 8').attr('refX', 8).attr('refY', 0).attr('markerWidth', ARROW).attr('markerHeight', ARROW)
    .attr('orient', 'auto').append('path').attr('d', 'M0,-4L8,0L0,4').attr('class', 'arrowhead');
  const gg = svg.append('g').attr('class', 'guides').attr('aria-hidden', 'true');   // rings, sectors, discs
  const gl = svg.append('g');
  const link = gl.selectAll('path.link').data(o.links).join('path').attr('class', 'link')
    .attr('stroke-opacity', o.opacity).attr('marker-end', o.directed ? 'url(#arrow)' : null);
  const hit = gl.selectAll('path.hit').data(o.links).join('path').attr('class', 'hit');   // wide, invisible: thin lines stay easy to point at
  const node = svg.append('g').selectAll('g').data(o.nodes).join('g').attr('class', 'node').attr('tabindex', 0)
    .attr('role', 'button').attr('aria-label', o.aria);
  node.append('path');
  const label = svg.append('g').selectAll('text').data(o.nodes).join('text').text((d) => d.name).attr('text-anchor', 'middle');
  let size = o.size, rS, wS;
  const R = (d) => rS(size(d) || 0);
  function scales(){
    rS = d3.scaleSqrt().domain([0, d3.max(o.nodes, size) || 1]).range([MIN_R, Math.max(MIN_R, ctl.maxR)]).clamp(true);
    const [w0, w1] = d3.extent(o.links, o.weight);
    wS = d3.scaleSqrt().domain([w0 || 0, w1 || 1]).range([MIN_W, Math.max(MIN_W, ctl.maxW)]).clamp(true); }
  const X = (d) => T.applyX(d.x), Y = (d) => T.applyY(d.y);
  function edge(l, trim){
    const x1 = X(l.source), y1 = Y(l.source); let x2 = X(l.target), y2 = Y(l.target), qx = null, qy = null;
    if (curve > 0){                                  // control point pulled towards the centre of the rings
      const cx = T.applyX(0), cy = T.applyY(0), mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
      qx = mx + (cx - mx) * curve; qy = my + (cy - my) * curve; }
    if (trim){                                       // the arrow's tip touches the target's edge, along the end tangent
      const sx = qx === null ? x1 : qx, sy = qy === null ? y1 : qy, dx = x2 - sx, dy = y2 - sy;
      const k = Math.min(1, (R(l.target) + 1) / (Math.hypot(dx, dy) || 1)); x2 -= dx * k; y2 -= dy * k; }
    return qx === null ? `M${f1(x1)},${f1(y1)}L${f1(x2)},${f1(y2)}` : `M${f1(x1)},${f1(y1)}Q${f1(qx)},${f1(qy)} ${f1(x2)},${f1(y2)}`; }
  function drawGuides(){
    const k = T.k, cx = T.applyX(0), cy = T.applyY(0), G = guide || {};
    gg.selectAll('circle.ring').data(G.rings || []).join('circle').attr('class', 'ring').attr('cx', cx).attr('cy', cy).attr('r', (r) => r.r * k);
    gg.selectAll('text.ringlab').data((G.rings || []).filter((r) => r.label)).join('text').attr('class', 'ringlab')
      .attr('x', cx).attr('y', (r) => cy - r.r * k + 12).attr('text-anchor', 'middle').text((r) => r.label);
    const rIn = (G.rIn || 0) * k, rOut = (G.rOut || 0) * k;
    gg.selectAll('line.sector').data(G.sectors || []).join('line').attr('class', 'sector')
      .attr('x1', (s) => cx + Math.max(0, rIn - 28) * Math.cos(s.a0)).attr('y1', (s) => cy + Math.max(0, rIn - 28) * Math.sin(s.a0))
      .attr('x2', (s) => cx + (rOut + 12) * Math.cos(s.a0)).attr('y2', (s) => cy + (rOut + 12) * Math.sin(s.a0));
    // sector names outside the rings; one that would overlap another is left to the legend
    const boxes = [], named = [];
    if (G.title){ const w = G.title.length * 5.6 + 8, y = cy - rOut - 30;
      boxes.push({x0: cx - w / 2, x1: cx + w / 2, y0: y - 11, y1: y + 6}); named.push({x: cx, y, anchor: 'middle', name: G.title, cls: 'ringlab'}); }
    for (const sc of G.sectors || []){
      const am = (sc.a0 + sc.a1) / 2, c = Math.cos(am), sn = Math.sin(am), rr = rOut + 18;
      const x = cx + rr * c, y = cy + rr * sn + 4, anchor = c > 0.25 ? 'start' : c < -0.25 ? 'end' : 'middle', w = sc.name.length * 6.6 + 4;
      const x0 = anchor === 'start' ? x : anchor === 'end' ? x - w : x - w / 2, box = {x0, x1: x0 + w, y0: y - 12, y1: y + 3};
      if (boxes.some((b) => box.x0 < b.x1 && box.x1 > b.x0 && box.y0 < b.y1 && box.y1 > b.y0)) continue;
      boxes.push(box); named.push({x, y, anchor, name: sc.name, cls: 'sectorlab'}); }
    gg.selectAll('circle.disc').data(G.discs || []).join('circle').attr('class', 'disc')
      .attr('cx', (c) => T.applyX(c.x)).attr('cy', (c) => T.applyY(c.y)).attr('r', (c) => c.r * k);
    for (const c of G.discs || []) named.push({x: T.applyX(c.x), y: T.applyY(c.y) - c.r * k - 7, anchor: 'middle', name: c.name, cls: 'sectorlab'});
    gg.selectAll('text.gname').data(named).join('text').attr('class', (t) => 'gname ' + t.cls)
      .attr('x', (t) => t.x).attr('y', (t) => t.y).attr('text-anchor', (t) => t.anchor).text((t) => t.name); }
  function render(){
    link.attr('d', (l) => edge(l, o.directed)); hit.attr('d', (l) => edge(l, false));
    node.attr('transform', (d) => `translate(${f1(X(d))},${f1(Y(d))})`);
    if (ctl.layout === 'rings') label.each(function(d){                 // names point outwards from the centre
      const a = d._a === undefined ? -Math.PI / 2 : d._a, c = Math.cos(a), sn = Math.sin(a), off = R(d) + 4;
      this.setAttribute('x', f1(X(d) + c * off)); this.setAttribute('y', f1(Y(d) + sn * off + 4)); this.setAttribute('dy', 0);
      this.setAttribute('text-anchor', c > 0.25 ? 'start' : c < -0.25 ? 'end' : 'middle'); });
    else label.attr('x', X).attr('y', Y).attr('dy', (d) => -R(d) - 4).attr('text-anchor', 'middle');
    drawGuides(); }
  function draw(){ scales();
    node.select('path').attr('d', (d) => d3.symbol(o.shape(d), Math.PI * R(d) ** 2)()).attr('fill', (d) => css(o.fill(d)));
    link.attr('stroke-width', (l) => wS(o.weight(l))); render(); }
  scales();
  const sim = d3.forceSimulation(o.nodes).randomSource(d3.randomLcg(DATA.parameters.seed / 1000 % 1))
    .force('link', d3.forceLink(o.links).id((d) => d.id).distance(o.distance).strength(o.strength))
    .force('charge', d3.forceManyBody().strength(o.charge)).force('center', d3.forceCenter(0, 0))
    .force('x0', d3.forceX(0).strength(0.04)).force('y0', d3.forceY(0).strength(0.06))
    .force('collide', d3.forceCollide().radius((d) => R(d) + 6)).stop();
  for (let i = 0; i < 400; i++) sim.tick();                          // layout computed before drawing: same seed, same picture
  forcePos = new Map(o.nodes.map((d) => [d.id, {x: d.x, y: d.y}]));
  sim.on('tick', render);
  const zoom = d3.zoom().scaleExtent([0.05, 20])
    .filter((ev) => (!ev.touches || ev.touches.length > 1) && !ev.button && (!ev.ctrlKey || ev.type === 'wheel'))  // one finger scrolls the page
    .on('zoom', (ev) => { T = ev.transform; render(); });
  svg.call(zoom);
  // dragging moves the node; only the force layout lets the others follow
  node.call(d3.drag().subject((ev, d) => ({x: X(d), y: Y(d)}))
    .on('start', (ev, d) => { if (ctl.layout !== 'force') return; if (!ev.active) sim.alphaTarget(0.2).restart(); d.fx = d.x; d.fy = d.y; })
    .on('drag', (ev, d) => { if (ctl.layout !== 'force') { d.x = T.invertX(ev.x); d.y = T.invertY(ev.y); render(); return; }
      d.fx = T.invertX(ev.x); d.fy = T.invertY(ev.y); })
    .on('end', (ev, d) => { if (ctl.layout !== 'force') return; if (!ev.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }));
  function fit(animate){ const shown = o.nodes.filter((d) => live.has(d.id)); if (!shown.length) return;
    let [x0, x1] = d3.extent(shown, (d) => d.x), [y0, y1] = d3.extent(shown, (d) => d.y);
    if (guide && guide.rOut){ const r = guide.rOut + 40; x0 = Math.min(x0, -r); x1 = Math.max(x1, r); y0 = Math.min(y0, -r - 20); y1 = Math.max(y1, r); }
    for (const c of (guide && guide.discs) || []){ x0 = Math.min(x0, c.x - c.r); x1 = Math.max(x1, c.x + c.r); y0 = Math.min(y0, c.y - c.r - 16); y1 = Math.max(y1, c.y + c.r); }
    const pad = ctl.maxR + 28;
    const k = Math.max(0.05, Math.min(4, (width() - 2 * pad) / Math.max(1, x1 - x0), (height() - 2 * pad) / Math.max(1, y1 - y0)));
    const t = d3.zoomIdentity.translate(width() / 2, height() / 2).scale(k).translate(-(x0 + x1) / 2, -(y0 + y1) / 2);
    (animate && !REDUCED ? svg.transition().duration(300) : svg).call(zoom.transform, t); }
  // the chart refits when its width changes: window resized, side panel hidden or shown
  const onResize = () => { svg.attr('viewBox', [0, 0, width(), height()]); fit(false); };
  window.addEventListener('resize', onResize);
  if (window.ResizeObserver) { let w0 = width();
    new ResizeObserver(() => { const w = width(); if (w && Math.abs(w - w0) > 1) { w0 = w; onResize(); } }).observe(svg.node()); }

  // ── layouts ──
  const shownLinks = () => o.links.filter((l) => lastOk(l));
  const order = new Map(o.nodes.map((d, i) => [d.id, i]));
  function ringsLayout(){
    const G = o.group(), vis = o.nodes.filter((d) => live.has(d.id)), deg = new Map();
    for (const l of shownLinks()){ deg.set(l.source.id, (deg.get(l.source.id) || 0) + 1); deg.set(l.target.id, (deg.get(l.target.id) || 0) + 1); }
    const m = (d) => deg.get(d.id) || 0;
    const ord = vis.slice().sort((a, b) => m(b) - m(a) || (size(b) || 0) - (size(a) || 0) || order.get(a.id) - order.get(b.id));
    const n = ord.length, bounds = ringBounds(ord.map(m)), ring = new Map(), minRing = RADII.map(() => null);
    ord.forEach((d, r) => { const k = bounds.findIndex((f) => r < f); ring.set(d.id, k); minRing[k] = m(d); });
    const S = Math.max(1, Math.sqrt(n / 60)), radii = RADII.map((r) => r * S);
    const count = new Map(), weight = new Map();
    for (const d of ord){ const g = G.of(d); count.set(g, (count.get(g) || 0) + 1); weight.set(g, (weight.get(g) || 0) + (size(d) || 0)); }
    const groups = [...count.keys()].filter((g) => g !== G.last).sort((a, b) => weight.get(b) - weight.get(a))
      .concat(count.has(G.last) ? [G.last] : []);
    let ang = -Math.PI / 2 + GAP_ANGLE / 2;
    const sectors = groups.map((g) => { const w = (2 * Math.PI - GAP_ANGLE) * count.get(g) / n; const sc = {g, a0: ang, a1: ang + w, name: G.name(g)}; ang += w; return sc; });
    const pos = new Map();
    for (const sc of sectors) for (let k = 0; k < RADII.length; k++){
      const members = ord.filter((d) => ring.get(d.id) === k && G.of(d) === sc.g);       // from the most to the least connected
      const margin = Math.min(0.015, (sc.a1 - sc.a0) * 0.1);
      members.forEach((d, q) => { const a = sc.a0 + margin + (sc.a1 - sc.a0 - 2 * margin) * (q + 0.5) / members.length;
        pos.set(d.id, {x: radii[k] * Math.cos(a), y: radii[k] * Math.sin(a), a}); }); }
    return {pos, guide: {rings: radii.map((r, k) => ({r, label: minRing[k] === null ? '' : `${k === 0 ? 'core · ' : ''}≥ ${fmt(minRing[k])}`})),
      sectors, rIn: radii[0], rOut: radii[radii.length - 1], title: o.ringTitle || 'rings: distinct connections among the edges shown'}}; }
  function clustersLayout(){
    const G = o.group(), raw = G.raw || G.of, vis = o.nodes.filter((d) => live.has(d.id)), links = shownLinks();
    const local = new Map(), discs = [], seed = () => d3.randomLcg(DATA.parameters.seed / 1000 % 1);
    for (const [g, ms] of d3.group(vis, raw)){
      const ids = new Set(ms.map((d) => d.id)), ns = ms.map((d) => ({id: d.id, r: R(d)}));
      const ls = links.filter((l) => ids.has(l.source.id) && ids.has(l.target.id)).map((l) => ({source: l.source.id, target: l.target.id, l}));
      const s = d3.forceSimulation(ns).randomSource(seed())
        .force('link', d3.forceLink(ls).id((d) => d.id).distance((x) => typeof o.distance === 'function' ? o.distance(x.l) : o.distance).strength(o.strength))
        .force('charge', d3.forceManyBody().strength(o.charge)).force('x', d3.forceX(0).strength(0.1)).force('y', d3.forceY(0).strength(0.1))
        .force('collide', d3.forceCollide().radius((d) => d.r + 5)).stop();
      for (let i = 0; i < 300; i++) s.tick();
      const mx = d3.mean(ns, (d) => d.x), my = d3.mean(ns, (d) => d.y);
      let rad = 0; ns.forEach((d) => { d.x -= mx; d.y -= my; rad = Math.max(rad, Math.hypot(d.x, d.y) + d.r); local.set(d.id, d); });
      discs.push({id: g, r: rad + 16, n: ms.length, name: (G.longName || G.name)(g)}); }
    // discs kept apart by a fixed gap; groups with more edges between them pulled a little closer
    const between = new Map();
    for (const l of links){ const a = raw(l.source), b = raw(l.target); if (a === b) continue;
      const [p, q] = String(a) < String(b) ? [a, b] : [b, a], key = `${p}\u0000${q}`;
      const e = between.get(key) || {source: p, target: q, w: 0}; e.w += 1; between.set(key, e); }
    const maxB = d3.max([...between.values()], (e) => e.w) || 1;
    const meta = d3.forceSimulation(discs).randomSource(seed())
      .force('link', d3.forceLink([...between.values()]).id((d) => d.id).distance((e) => e.source.r + e.target.r + CLUSTER_GAP)
        .strength((e) => 0.03 + 0.2 * e.w / maxB))
      .force('charge', d3.forceManyBody().strength(-60)).force('x', d3.forceX(0).strength(0.03)).force('y', d3.forceY(0).strength(0.03))
      .force('collide', d3.forceCollide().radius((d) => d.r + CLUSTER_GAP / 2).strength(1).iterations(4)).stop();
    for (let i = 0; i < 500; i++) meta.tick();
    const at = new Map(discs.map((c) => [c.id, c])), pos = new Map();
    for (const d of vis){ const c = at.get(raw(d)), p = local.get(d.id); pos.set(d.id, {x: c.x + p.x, y: c.y + p.y}); }
    return {pos, guide: {discs: discs.map((c) => ({x: c.x, y: c.y, r: c.r, name: c.name}))}}; }
  function edgeOpacity(){                          // in «separated groups», the edges between groups recede
    const raw = ctl.layout === 'clusters' ? (o.group().raw || o.group().of) : null;
    link.attr('stroke-opacity', (l) => o.opacity(l) * (raw && raw(l.source) !== raw(l.target) ? 0.18 : 1)); }
  function setLayout(mode, animate = true, refit = true){
    if (moving) { moving.stop(); moving = null; }
    if (ctl.layout === 'force' && mode !== 'force') forcePos = new Map(o.nodes.map((d) => [d.id, {x: d.x, y: d.y}]));
    ctl.layout = mode; sim.stop(); o.nodes.forEach((d) => { d.fx = null; d.fy = null; });
    const sel = document.getElementById('layout'); if (sel) sel.value = mode;
    const r = mode === 'rings' ? ringsLayout() : mode === 'clusters' ? clustersLayout() : {pos: forcePos, guide: null};
    const c1 = mode === 'rings' ? CURVE : 0, c0 = curve, from = new Map(o.nodes.map((d) => [d.id, {x: d.x, y: d.y}]));
    o.nodes.forEach((d) => { const p = r.pos.get(d.id); d._a = p ? p.a : undefined; });
    const end = () => { o.nodes.forEach((d) => { const p = r.pos.get(d.id); if (p) { d.x = p.x; d.y = p.y; } });
      curve = c1; guide = r.guide; edgeOpacity(); render(); if (refit) fit(animate); if (o.onLayout) o.onLayout(mode); };
    if (!animate || REDUCED) { end(); return; }
    guide = null;
    const t0 = performance.now(), ease = d3.easeCubicInOut;
    moving = d3.timer(() => { const u = Math.min(1, (performance.now() - t0) / 650), e = ease(u);
      o.nodes.forEach((d) => { const a = from.get(d.id), b = r.pos.get(d.id); if (b) { d.x = a.x + (b.x - a.x) * e; d.y = a.y + (b.y - a.y) * e; } });
      curve = c0 + (c1 - c0) * e; render();
      if (u >= 1) { moving.stop(); moving = null; end(); } }); }

  // names: the first by o.rank always (8 on a phone, 20 otherwise, or o.nLabels); all of them on demand
  const topLabels = new Set(o.nodes.slice().sort((a, b) => o.rank(b) - o.rank(a))
    .slice(0, o.nLabels || (innerWidth < 600 ? 8 : 20)).map((d) => d.id));
  function filter(ok){ lastOk = ok; link.style('display', (l) => ok(l) ? null : 'none'); hit.style('display', (l) => ok(l) ? null : 'none');
    live = new Set(); o.links.forEach((l) => { if (ok(l)) { live.add(l.source.id); live.add(l.target.id); } });
    node.style('display', (d) => live.has(d.id) ? null : 'none');
    label.style('display', (d) => live.has(d.id) && (showLabels || topLabels.has(d.id)) ? null : 'none');
    if (ctl.layout !== 'force') setLayout(ctl.layout, false, false);   // rings and clusters are computed on what is shown
    return live; }
  // controls every page has: layout, node size, edge width, all labels, reset view
  const lIn = document.getElementById('layout');
  if (lIn) { lIn.value = ctl.layout; lIn.addEventListener('change', () => setLayout(lIn.value)); }
  const rIn = document.getElementById('maxr'), wIn = document.getElementById('maxw');
  const rOut = document.getElementById('maxrOut'), wOut = document.getElementById('maxwOut');
  Object.assign(rIn, {min: 4, max: 40, step: 1, value: ctl.maxR}); Object.assign(wIn, {min: 0.5, max: 6, step: 0.1, value: ctl.maxW});
  rOut.textContent = ctl.maxR + ' px'; wOut.textContent = ctl.maxW.toFixed(1) + ' px';
  rIn.addEventListener('input', () => { ctl.maxR = +rIn.value; rOut.textContent = ctl.maxR + ' px'; draw(); });
  wIn.addEventListener('input', () => { ctl.maxW = +wIn.value; wOut.textContent = ctl.maxW.toFixed(1) + ' px'; draw(); });
  document.getElementById('labels').addEventListener('click', (e) => { showLabels = !showLabels;
    e.currentTarget.setAttribute('aria-pressed', String(showLabels)); filter(lastOk); });
  document.getElementById('reset').addEventListener('click', () => fit(true));
  window.addEventListener('themechange', draw);
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', draw);
  draw();
  if (o.onLayout) queueMicrotask(() => o.onLayout(ctl.layout));   // after the page has its handle on the view
  return {node, link, hit, label, sim, fit, draw, filter, R, setSize(f){ size = f; draw(); },
          layout: () => ctl.layout, relayout(){ if (ctl.layout !== 'force') setLayout(ctl.layout, true); }};
}
// The side panel can be hidden to give the network the whole width (remembered in this browser); a click that asks
// for details opens it again.
function panelControl(){
  const lay = document.querySelector('.layout'), b = document.getElementById('panelbtn');
  if (!lay || !b) return () => {};
  const set = (hidden, keep = true) => { lay.classList.toggle('nopanel', hidden); b.textContent = hidden ? 'show panel' : 'hide panel';
    b.setAttribute('aria-expanded', String(!hidden));
    if (keep) try { localStorage.setItem('parlaibero-network-panel', hidden ? 'hidden' : 'shown'); } catch (e) { /* storage off */ } };
  let saved = null;
  try { saved = localStorage.getItem('parlaibero-network-panel'); } catch (e) { /* storage off */ }
  set(saved === 'hidden', false);
  b.addEventListener('click', () => set(!lay.classList.contains('nopanel')));
  return () => { if (lay.classList.contains('nopanel')) set(false); };
}
const openPanel = panelControl();
function themeButton(){
  const b = document.getElementById('theme'); if (!b) return;
  b.addEventListener('click', () => { const r = document.documentElement;
    const cur = r.getAttribute('data-theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    r.setAttribute('data-theme', cur === 'dark' ? 'light' : 'dark'); window.dispatchEvent(new Event('themechange')); });
}
"""

COMENTION_JS = r"""
const G = DATA.groups;                       // null without groups
const HAS_BIAS = !!(G && G.contrast && G.contrast.length === 2);
const nodes = DATA.nodes.filter((d) => d.in_network).map((d) => ({...d, id: d.name}));
const links = DATA.edges.map((e) => ({...e}));
const SHAPE = {persona: d3.symbolCircle, institucion: d3.symbolSquare};
const SHAPE_LABEL = {persona: 'person', institucion: 'institution'};
const BINS = [-1, -0.6, -0.3, -0.1, 0.1, 0.3, 0.6, 1.0001];          // 7 bins → 7 steps
function biasVar(b){ if (b === null || b === undefined) return '--c0';
  // bias > 0 = group 1 (orange, d-steps negative), < 0 = group 2 (blue)
  const i = BINS.findIndex((x, k) => b >= x && b < BINS[k + 1]); return ['--d3','--d2','--d1','--d0','--d-1','--d-2','--d-3'][i]; }
const commColour = (c) => (c !== null && c < 30) ? `--c${c + 1}` : '--c0';
let colourBy = HAS_BIAS ? 'bias' : 'community';
const fillOf = (d) => colourBy === 'bias' ? biasVar(d.bias) : commColour(d.community);
function commName(c){ const top = DATA.nodes.filter((d) => d.in_network && d.community === c).sort((a, b) => b.n - a.n)[0];
  return `C${c + 1}${top ? ' · ' + top.name : ''}`; }
const coMax = d3.max(links, (d) => d.co) || 1;
const oScale = d3.scaleLinear().domain([DATA.parameters.min_npmi, d3.max(links, (d) => d.npmi) || 1]).range([0.2, 0.75]).clamp(true);
const gv = graphView({nodes, links, directed: false, size: (d) => d.n, shape: (d) => SHAPE[d.type] || d3.symbolCircle,
  fill: fillOf, weight: (l) => l.co, opacity: (l) => oScale(l.npmi), rank: (d) => d.n,
  distance: (l) => 140 - 90 * Math.max(0, l.npmi), strength: 0.4, charge: -260,
  aria: (d) => `${d.name}, ${SHAPE_LABEL[d.type] || d.type}, in ${fmt(d.n)} interventions`,
  // sectors and discs: the Leiden communities (up to 30 coloured, the rest together)
  group: () => ({of: (d) => (d.community !== null && d.community < 30) ? d.community : 'other',
    raw: (d) => d.community === null ? 'other' : d.community, last: 'other',
    name: (k) => k === 'other' ? 'other communities' : commName(k)}),
  onLayout: (mode) => { const b = document.getElementById('split'); if (b) b.disabled = mode !== 'force';
    if (HAS_BIAS && mode !== 'force' && colourBy === 'bias') setColour('community'); }});
const {node, link, hit, sim, label} = gv;
function setColour(v){ colourBy = v; const c = document.getElementById('colour'); if (c) c.value = v; gv.draw(); legend(); }
const colourSel = document.getElementById('colour');
if (!HAS_BIAS) document.getElementById('colourWrap').hidden = true;
colourSel.value = colourBy; colourSel.addEventListener('change', () => setColour(colourSel.value));

// thresholds, split by group, size metric
let minCo = DATA.parameters.min_co, minNpmi = DATA.parameters.min_npmi;
const visible = (l) => l.co >= minCo && l.npmi >= minNpmi;
function applyFilters(){ const live = gv.filter(visible);
  document.getElementById('shown').textContent = `${fmt(live.size)} nodes · ${fmt(links.filter(visible).length)} edges shown`; }
const coIn = document.getElementById('minco'), npIn = document.getElementById('minnpmi');
coIn.min = DATA.parameters.min_co; coIn.max = coMax; coIn.value = minCo;
npIn.min = DATA.parameters.min_npmi; npIn.max = Math.max(DATA.parameters.min_npmi, d3.max(links, (d) => d.npmi) || 1); npIn.step = 0.01; npIn.value = minNpmi;
const outCo = document.getElementById('mincoOut'), outNp = document.getElementById('minnpmiOut');
coIn.addEventListener('input', () => { minCo = +coIn.value; outCo.textContent = fmt(minCo); applyFilters(); });
npIn.addEventListener('input', () => { minNpmi = +npIn.value; outNp.textContent = minNpmi.toFixed(2); applyFilters(); });
outCo.textContent = fmt(minCo); outNp.textContent = minNpmi.toFixed(2);
const splitBtn = document.getElementById('split');
if (!HAS_BIAS) splitBtn.hidden = true;
splitBtn.addEventListener('click', (e) => { const on = e.currentTarget.getAttribute('aria-pressed') !== 'true';
  e.currentTarget.setAttribute('aria-pressed', String(on));
  // group 1 to the left (its colour is on the left of the legend), group 2 to the right
  sim.force('x', on ? d3.forceX((d) => -(d.bias || 0) * 360).strength(0.35) : null).alpha(0.8).restart();
  sim.on('end.fit', () => { gv.fit(true); sim.on('end.fit', null); }); });
document.getElementById('size').addEventListener('change', (e) => { const k = e.target.value; gv.setSize((d) => d[k]); });

// neighbours, tooltip, details
const nbr = new Map(nodes.map((d) => [d.id, new Set([d.id])]));
links.forEach((l) => { nbr.get(l.source.id).add(l.target.id); nbr.get(l.target.id).add(l.source.id); });
function focusNode(d){ const s = nbr.get(d.id); node.classed('dim', (x) => !s.has(x.id)); label.classed('dim', (x) => !s.has(x.id));
  link.classed('dim', (l) => l.source.id !== d.id && l.target.id !== d.id); }
function clearFocus(){ node.classed('dim', false); label.classed('dim', false); link.classed('dim', false); }
function nodeRows(d){ const r = [[fmt(d.n), 'interventions'], [fmt(d.strength), 'weighted degree'], [String(d.degree), 'co-mentioned actors']];
  if (HAS_BIAS && d.bias !== null && d.bias !== undefined) r.push([d.bias.toFixed(2), `bias (+ ${G.contrast[0]}, − ${G.contrast[1]})`]);
  if (d.community !== null) r.push([String(d.community + 1), 'community']); return [[d.name, SHAPE_LABEL[d.type] || d.type], ...r]; }
node.on('mouseenter', (ev, d) => { focusNode(d); showTip(ev, nodeRows(d)); }).on('mousemove', (ev, d) => showTip(ev, nodeRows(d)))
  .on('mouseleave', () => { clearFocus(); hideTip(); })
  .on('focus', (ev, d) => focusNode(d)).on('blur', clearFocus)
  .on('click', (ev, d) => showNode(d)).on('keydown', (ev, d) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); showNode(d); } });
hit.on('mouseenter', (ev, l) => showTip(ev, [[`${l.source.id} – ${l.target.id}`, ''], [fmt(l.co), 'interventions together'],
    [l.npmi.toFixed(3), 'NPMI'], ...(HAS_BIAS ? G.contrast.map((g) => [fmt(l['co_' + g] || 0), 'by ' + g]) : [])]))
  .on('mouseleave', hideTip).on('click', (ev, l) => showEdge(l));
const panel = document.getElementById('panel');
function showNode(d){ openPanel(); panel.replaceChildren(el('h2', {}, d.name),
    el('p', {class:'kv'}, nodeRows(d).slice(1).map(([v, l]) => `${v} ${l}`).join(' · ')));
  for (const k of (DATA.kwic[d.name] || [])) { const box = el('div', {class:'ex'});
    box.append(el('div', {class:'meta'}, [k.date, k.speaker, k.party].filter(Boolean).join(' · ') + ' · ' + k.id_int), kwicLine(k)); panel.append(box); }
  const al = (DATA.alerts || {})[d.name]; if (al) al.forEach((a) => panel.append(el('p', {class:'warn'}, '⚠ ' + a))); }
function showEdge(l){ openPanel(); panel.replaceChildren(el('h2', {}, `${l.source.id} – ${l.target.id}`),
    el('p', {class:'kv'}, `${fmt(l.co)} interventions together · NPMI ${l.npmi.toFixed(3)} · Jaccard ${l.jaccard.toFixed(3)}`));
  for (const x of (l.examples || [])) { const box = el('div', {class:'ex'});
    box.append(el('div', {class:'meta'}, [x.date, x.speaker, x.party].filter(Boolean).join(' · ') + ' · ' + x.id_int));
    if (x.a) box.append(kwicLine(x.a)); if (x.b) box.append(kwicLine(x.b)); panel.append(box); } }

// legend
function legend(){ const lg = document.getElementById('legend'); lg.replaceChildren();
for (const t of [...new Set(nodes.map((d) => d.type))]) { const sp = el('span'); const sv = d3.create('svg').attr('width', 14).attr('height', 14);
  sv.append('path').attr('d', d3.symbol(SHAPE[t] || d3.symbolCircle, 80)()).attr('transform', 'translate(7,7)').attr('fill', 'var(--muted)');
  sp.append(sv.node(), document.createTextNode(' ' + (SHAPE_LABEL[t] || t))); lg.append(sp); }
if (colourBy === 'bias') { const sc = el('span', {class:'scale'}); sc.append(document.createTextNode(G.contrast[0]));
  const bar = el('span', {class:'bar'}); ['--d-3','--d-2','--d-1','--d0','--d1','--d2','--d3'].forEach((v) => { const s = el('span'); s.style.background = `var(${v})`; bar.append(s); });
  sc.append(bar, document.createTextNode(G.contrast[1] + ' (bias: share of each group\'s interventions)')); lg.append(sc); }
else { const comms = [...new Set(nodes.map((d) => d.community))].sort((a, b) => a - b);
  comms.forEach((c) => { const sp = el('span'); const sw = el('span', {class:'sw'}); sw.style.background = `var(${commColour(c)})`;
    sp.append(sw, document.createTextNode(c < 30 ? commName(c) : 'other communities')); lg.append(sp); }); }
lg.append(el('span', {}, 'size = the measure chosen (√, up to «node size») · line width = co (√, up to «edge width») · line opacity = NPMI')); }
legend();

// twin tables
const nodeCols = [{key:'name', label:'actor'}, {key:'type', label:'type'}, {key:'n', label:'n', num:true}]
  .concat(HAS_BIAS ? [...G.contrast, 'rest'].map((g) => ({key:'n_' + g, label:'n ' + g, num:true})).concat([{key:'bias', label:'bias', num:true, digits:3}]) : [])
  .concat([{key:'strength', label:'weighted degree', num:true}, {key:'betweenness', label:'betweenness', num:true, digits:4},
           {key:'community_1', label:'community', num:true}]);
sortableTable(document.getElementById('tnodes'), nodeCols, DATA.nodes.map((d) => ({...d, community_1: d.community === null ? null : d.community + 1})));
const edgeCols = [{key:'source', label:'a'}, {key:'target', label:'b'}, {key:'co', label:'co', num:true}]
  .concat(HAS_BIAS ? [...G.contrast, 'rest'].map((g) => ({key:'co_' + g, label:'co ' + g, num:true})) : [])
  .concat([{key:'npmi', label:'NPMI', num:true, digits:3}, {key:'jaccard', label:'Jaccard', num:true, digits:3}]);
sortableTable(document.getElementById('tedges'), edgeCols, DATA.edges);
applyFilters(); gv.fit(false); themeButton();
"""


def comention_page(res: dict) -> str:
    p = res["parameters"]
    country = res["country"]
    library = (p.get("filters") or {}).get("library") or ""
    title = f"Co-mention network of actors · {library} · {country}"
    s = res["stats"]
    subtitle = (f"{res['N']:,} interventions · {s['nodes']} entities · {s['edges']} edges · co ≥ {p['min_co']}"
                f"{' (automatic)' if p['min_co_auto'] else ''} · NPMI ≥ {p['min_npmi']} · communities: Leiden, seed {p['seed']}")
    groups = res.get("groups")
    body = f"""
<div class="layout">
 <section class="card" aria-label="Network">
  <div class="controls">
   <label>layout <select id="layout"><option value="force">force</option><option value="clusters">separated groups</option>
     <option value="rings">rings (centrifugal)</option></select></label>
   <label id="colourWrap">colour <select id="colour"><option value="bias">bias between groups</option>
     <option value="community">community</option></select></label>
   <label>min co <input type="range" id="minco"><output id="mincoOut"></output></label>
   <label>min NPMI <input type="range" id="minnpmi"><output id="minnpmiOut"></output></label>
   <label>size <select id="size"><option value="n">interventions</option><option value="strength">weighted degree</option>
     <option value="betweenness">betweenness</option></select></label>
   <label>node size <input type="range" id="maxr" aria-label="largest node radius"><output id="maxrOut"></output></label>
   <label>edge width <input type="range" id="maxw" aria-label="widest line"><output id="maxwOut"></output></label>
   <button id="labels" aria-pressed="false">all labels</button>
   <button id="split" aria-pressed="false">separate by group</button>
   <button id="reset">reset view</button>
   <button id="panelbtn" aria-controls="panel" aria-expanded="true">hide panel</button>
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
    return _page(title, subtitle, body, res, COMMON_JS + COMENTION_JS)


WORDS_CSS = r"""
.themes{list-style:none;margin:0;padding:0;max-height:min(62vh,600px);overflow:auto}
.themes li{margin:0}
.themes button{all:unset;box-sizing:border-box;display:flex;gap:8px;align-items:baseline;width:100%;padding:5px 6px;
 border-radius:6px;cursor:pointer;font-size:.86rem;color:var(--ink)}
.themes button:hover,.themes button[aria-pressed="true"]{background:var(--grid)}
.themes button:focus-visible{outline:2px solid var(--focus);outline-offset:1px}
.themes .sw{display:inline-block;width:10px;height:10px;border-radius:2px;flex:none;border:1px solid var(--ring)}
.themes .k{color:var(--muted);font-variant-numeric:tabular-nums;min-width:1.6em}
.themes .p{margin-left:auto;color:var(--ink2);font-variant-numeric:tabular-nums}
.terms{font-size:.86rem;color:var(--ink2);margin:.3rem 0 .6rem}
.bars{display:grid;grid-template-columns:auto 1fr auto;gap:2px 8px;font-size:.8rem;align-items:center;margin:.3rem 0 .6rem}
.bars [role=listitem]{display:block}
.bars .b{display:block;height:8px;border-radius:2px;background:var(--c1);min-width:1px}
.bars .v{font-variant-numeric:tabular-nums;color:var(--ink2)}
.back{margin-bottom:.5rem}
"""

WORDS_JS = r"""
const themes = DATA.themes;
const nodes = DATA.nodes.filter((d) => d.degree > 0).map((d) => ({...d, id: d.term, name: d.display}));
const links = DATA.edges.map((e) => ({...e}));
const byTerm = new Map(nodes.map((d) => [d.id, d]));
const themeColour = (t) => (t !== null && t >= 0 && t < 30) ? `--c${t + 1}` : '--c0';
const themeName = (t) => t >= 0 ? `${t + 1}. ${themes[t].label}` : 'loose term';
let sizeKey = 'freq';
const [g0, g1] = d3.extent(links, (l) => l.g2);
const oScale = d3.scaleLog().domain([Math.max(1, g0 || 1), Math.max(2, g1 || 2)]).range([0.18, 0.7]).clamp(true);
const firsts = new Set(themes.flatMap((t) => t.terms.slice(0, 3).map((x) => x.term)));
const gv = graphView({nodes, links, directed: false, size: (d) => d[sizeKey],
  shape: (d) => d.expression ? d3.symbolDiamond : d3.symbolCircle, fill: (d) => themeColour(d.theme),
  weight: (l) => l.weight, opacity: (l) => oScale(l.g2), rank: (d) => (firsts.has(d.id) ? 1e15 : 0) + d.freq,
  nLabels: innerWidth < 600 ? 12 : Math.min(60, 3 * themes.length),
  distance: (l) => Math.max(25, Math.min(120, 120 / Math.sqrt(l.weight))), strength: 0.5, charge: -150,
  aria: (d) => `${d.display}, ${themeName(d.theme)}, ${fmt(d.freq)} times in the library`,
  // sectors: every coloured theme (up to 30), loose terms together; discs: every theme, and the loose terms
  group: () => ({of: (d) => d.theme >= 0 && d.theme < 30 ? d.theme : 'other', raw: (d) => d.theme >= 0 ? d.theme : 'loose', last: 'other',
    name: (k) => k === 'other' ? 'loose terms and other themes' : k === 'loose' ? 'loose terms' : `${k + 1} · ${themes[k].terms[0].display}`,
    longName: (k) => k === 'loose' ? 'loose terms' : k === 'other' ? 'other' : `${k + 1}. ${themes[k].label}`})});
const {node, link, hit, label} = gv;
gv.filter(() => true);
document.getElementById('shown').textContent = `${fmt(nodes.length)} terms · ${fmt(links.length)} edges · ${themes.length} themes`;

// highlight: a theme, or a term and its neighbours
let current = null;
function showTheme(t){ current = t;
  node.classed('dim', (d) => t !== null && d.theme !== t); label.classed('dim', (d) => t !== null && d.theme !== t);
  link.classed('dim', (l) => t !== null && !(l.source.theme === t && l.target.theme === t));
  document.querySelectorAll('.themes button').forEach((b) => b.setAttribute('aria-pressed', String(+b.dataset.t === t)));
  sel.value = t === null ? '' : String(t); }
const nbr = new Map(nodes.map((d) => [d.id, new Set([d.id])]));
links.forEach((l) => { nbr.get(l.source.id).add(l.target.id); nbr.get(l.target.id).add(l.source.id); });
function focusNode(d){ const s = nbr.get(d.id); node.classed('dim', (x) => !s.has(x.id)); label.classed('dim', (x) => !s.has(x.id));
  link.classed('dim', (l) => l.source.id !== d.id && l.target.id !== d.id); }
const restore = () => showTheme(current);
const nodeRows = (d) => [[d.display, themeName(d.theme)], [fmt(d.freq), 'times in the library'],
  [fmt(d.df_intervention), 'interventions'], [d.g2_lexicon.toFixed(1), 'G² in the lexicon'],
  [String(d.degree), 'neighbours'], [d.strength.toFixed(1), 'strength (Σ obs/exp)']];
node.on('mouseenter', (ev, d) => { focusNode(d); showTip(ev, nodeRows(d)); }).on('mousemove', (ev, d) => showTip(ev, nodeRows(d)))
  .on('mouseleave', () => { restore(); hideTip(); }).on('focus', (ev, d) => focusNode(d)).on('blur', restore)
  .on('click', (ev, d) => showNode(d)).on('keydown', (ev, d) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); showNode(d); } });
hit.on('mouseenter', (ev, l) => showTip(ev, [[`${l.source.display} – ${l.target.display}`, ''], [fmt(l.co), 'units together'],
    [l.expected.toFixed(1), 'expected by chance'], [l.weight.toFixed(2), 'association strength (obs/exp)'], [l.g2.toFixed(1), 'G²']]))
  .on('mouseleave', hideTip);

// side panel: the list of themes, a theme, a term
const panel = document.getElementById('panel');
const sel = document.getElementById('theme-select');
themes.forEach((t) => sel.append(el('option', {value: String(t.id)}, `${t.id + 1}. ${t.label}`)));
sel.addEventListener('change', () => { const v = sel.value; if (v === '') { showTheme(null); listThemes(); } else openTheme(+v); });
function listThemes(){ const ul = el('ul', {class: 'themes'});
  themes.forEach((t) => { const b = el('button', {type: 'button', 'aria-pressed': 'false'}); b.dataset.t = t.id;
    const sw = el('span', {class: 'sw'}); sw.style.background = `var(${themeColour(t.id)})`;
    b.append(sw, el('span', {class: 'k'}, String(t.id + 1)), el('span', {}, t.label), el('span', {class: 'p'}, t.pct_interventions + ' %'));
    b.addEventListener('click', () => openTheme(t.id)); const li = el('li'); li.append(b); ul.append(li); });
  panel.replaceChildren(el('h2', {}, 'Themes'), el('p', {class: 'hint'}, 'Ordered by how characteristic their terms are of ' +
    'the library (mean G² in the lexicon); the number on the right is the share of interventions that use any of its terms.'), ul);
  if ((DATA.loose_terms || []).length) panel.append(el('p', {class: 'terms'}, 'Loose terms: ' + DATA.loose_terms.map((x) => x.display).join(', '))); }
function back(){ const b = el('button', {type: 'button', class: 'back'}, '← all themes');
  b.addEventListener('click', () => { showTheme(null); listThemes(); }); return b; }
const meta = (id) => DATA.metadata[String(id)] || {};
function readingList(rows){ const box = el('div');
  rows.forEach((x) => { const m = meta(x.id); const d = el('div', {class: 'ex'});
    d.append(el('div', {class: 'meta'}, [m.date, m.speaker, m.party, m.id_int].filter(Boolean).join(' · ') + ` · score ${x.score}`),
      el('div', {}, x.terms.map((t) => t.tf > 1 ? `${t.display} ×${t.tf}` : t.display).join(', '))); box.append(d); });
  return box; }
function openTheme(k){ const t = themes[k]; showTheme(k); openPanel();
  const big = new Set(DATA.parties.top.filter((x) => x.words >= 0.01 * DATA.parties.words_total).map((x) => x.party));
  const rates = t.parties.top.filter((x) => big.has(x.party) && x.per_1000 !== null).sort((a, b) => b.per_1000 - a.per_1000);
  const mx = d3.max(rates, (x) => x.per_1000) || 1;
  const bars = el('div', {class: 'bars', role: 'list', 'aria-label': 'words of the theme per 1,000 words of each party'});
  rates.forEach((x) => { const b = el('span', {class: 'b'}); b.style.width = (100 * x.per_1000 / mx).toFixed(1) + '%';
    const cell = el('span', {role: 'listitem'}); cell.append(b);
    bars.append(el('span', {}, x.party), cell, el('span', {class: 'v'}, x.per_1000.toFixed(1))); });
  panel.replaceChildren(back(), el('h2', {}, `${t.id + 1}. ${t.label}`),
    el('p', {class: 'kv'}, `${t.n_terms} terms · ${t.pct_interventions} % of the interventions · ${t.weight_pct} % of the words ` +
      `in interventions it dominates · mean G² ${t.g2_mean}`),
    el('p', {class: 'terms'}, t.terms.map((x) => x.display).join(', ')),
    el('h2', {}, 'Parties'), el('p', {class: 'hint'}, 'Words of the theme per 1,000 words the party says in the library ' +
      '(parties with at least 1 % of the words).'), bars,
    el('h2', {}, 'Read first'), el('p', {class: 'hint'}, 'The interventions that concentrate the theme\'s vocabulary (BM25).'),
    readingList(t.reading.slice(0, 10))); }
function showNode(d){ openPanel(); const ns = links.filter((l) => l.source.id === d.id || l.target.id === d.id)
    .map((l) => [l.source.id === d.id ? l.target : l.source, l]).sort((a, b) => b[1].weight - a[1].weight);
  const ul = el('ul'); ns.slice(0, 15).forEach(([x, l]) => ul.append(el('li', {}, `${x.display} — ${l.weight.toFixed(2)} (${fmt(l.co)} together)`)));
  panel.replaceChildren(back(), el('h2', {}, d.display), el('p', {class: 'kv'}, nodeRows(d).slice(1).map(([v, l]) => `${v} ${l}`).join(' · ')),
    el('p', {class: 'kv'}, themeName(d.theme)), el('div', {class: 'meta'}, 'Strongest neighbours (association strength)'), ul); }
listThemes();
document.getElementById('size').addEventListener('change', (e) => { const k = e.target.value; gv.setSize((d) => d[k]); });

// legend
const lg = document.getElementById('legend');
themes.slice(0, 30).forEach((t) => { const sp = el('span'); const sw = el('span', {class: 'sw'}); sw.style.background = `var(${themeColour(t.id)})`;
  sp.append(sw, document.createTextNode(`${t.id + 1}. ${t.label}`)); lg.append(sp); });
if (themes.length > 30 || (DATA.loose_terms || []).length) { const sp = el('span'); const sw = el('span', {class: 'sw'});
  sw.style.background = 'var(--c0)'; sp.append(sw, document.createTextNode(themes.length > 30 ? 'other themes and loose terms' : 'loose terms')); lg.append(sp); }
lg.append(el('span', {}, 'circle = word · diamond = expression · size = the measure chosen (√, up to «node size») · line width = ' +
  'association strength (√, up to «edge width») · opacity = G²'));

// twin tables
sortableTable(document.getElementById('tthemes'), [{key: 'k', label: 'theme', num: true}, {key: 'label', label: 'label'},
  {key: 'n_terms', label: 'terms', num: true}, {key: 'pct_interventions', label: '% interventions', num: true, digits: 1},
  {key: 'weight_pct', label: '% words dominated', num: true, digits: 1}, {key: 'g2_mean', label: 'mean G²', num: true, digits: 1},
  {key: 'all', label: 'all its terms'}], themes.map((t) => ({...t, k: t.id + 1, all: t.terms.map((x) => x.display).join(', ')})));
sortableTable(document.getElementById('tnodes'), [{key: 'display', label: 'term'}, {key: 'k', label: 'theme', num: true},
  {key: 'freq', label: 'frequency', num: true}, {key: 'g2_lexicon', label: 'G² lexicon', num: true, digits: 1},
  {key: 'df_intervention', label: 'interventions', num: true}, {key: 'degree', label: 'neighbours', num: true},
  {key: 'strength', label: 'strength', num: true, digits: 2}], DATA.nodes.map((d) => ({...d, k: d.theme >= 0 ? d.theme + 1 : null})));
sortableTable(document.getElementById('tedges'), [{key: 'a_', label: 'a'}, {key: 'b_', label: 'b'}, {key: 'co', label: 'together', num: true},
  {key: 'expected', label: 'expected', num: true, digits: 1}, {key: 'weight', label: 'strength', num: true, digits: 2},
  {key: 'g2', label: 'G²', num: true, digits: 1}], DATA.edges.map((e) => ({...e, a_: DATA.nodes[e.a].display, b_: DATA.nodes[e.b].display})));
gv.fit(false); themeButton();
"""


MENTION_CSS = r"""
.heat td.cell{text-align:right;font-variant-numeric:tabular-nums;min-width:70px}
.heat th{position:static}
.views{display:flex;gap:6px;margin-bottom:8px}
.arrowhead{fill:var(--edge);fill-opacity:.75}
"""

MENTION_JS = r"""
const groupsOrder = [...new Set(DATA.nodes.map((d) => d.group))]
  .sort((a, b) => d3.sum(DATA.nodes.filter((x) => x.group === b), (x) => x.in_strength + x.out_strength)
                - d3.sum(DATA.nodes.filter((x) => x.group === a), (x) => x.in_strength + x.out_strength));
const slot = new Map(groupsOrder.filter((g) => g !== 'external').slice(0, 30).map((g, i) => [g, `--c${i + 1}`]));
const colourOf = (g) => g === 'external' ? '--muted' : (slot.get(g) || '--c0');
const nodes = DATA.nodes.map((d) => ({...d}));
const links = DATA.edges.map((e) => ({...e}));
let groupBy = 'group';
const commColour = (c) => (c !== null && c !== undefined && c < 30) ? `--c${c + 1}` : '--c0';
function commName(c){ const top = nodes.filter((d) => d.community === c).sort((a, b) => b.in_strength - a.in_strength)[0];
  return `C${c + 1}${top ? ' · ' + top.name : ''}`; }
const gv = graphView({nodes, links, directed: true, size: (d) => d.in_strength,
  shape: (d) => d.kind === 'external' ? d3.symbolSquare : d3.symbolCircle,
  fill: (d) => groupBy === 'group' ? colourOf(d.group) : commColour(d.community),
  // sectors and discs: the party (up to 30 coloured, external actors, the rest together) or the Leiden community
  group: () => groupBy === 'group'
    ? {of: (d) => d.group === 'external' ? 'external' : slot.has(d.group) ? d.group : 'other', raw: (d) => d.group, last: 'other',
       name: (k) => k === 'external' ? 'external actors' : k === 'other' ? 'other groups' : k}
    : {of: (d) => (d.community !== null && d.community !== undefined && d.community < 30) ? d.community : 'other',
       raw: (d) => d.community === null || d.community === undefined ? 'other' : d.community, last: 'other',
       name: (k) => k === 'other' ? 'other communities' : commName(k)},
  weight: (l) => l.interventions, opacity: () => 0.5, rank: (d) => d.in_strength + d.out_strength,
  distance: 120, strength: 0.25, charge: -280,
  aria: (d) => `${d.name}, ${d.group}, mentioned in ${fmt(d.in_strength)} interventions, mentions others in ${fmt(d.out_strength)}`});
const {node, link, hit, label} = gv;

// filters
let minM = DATA.parameters.min_mentions, fromGroup = '', showExt = true, showDep = true;
const mIn = document.getElementById('minm'); mIn.min = DATA.parameters.min_mentions; mIn.max = d3.max(links, (d) => d.interventions) || 1; mIn.value = minM;
const mOut = document.getElementById('minmOut'); mOut.textContent = fmt(minM);
const gSel = document.getElementById('from'); groupsOrder.filter((g) => g !== 'external').forEach((g) => gSel.append(el('option', {value: g}, g)));
const byId = new Map(nodes.map((d) => [d.id, d]));
const linkOk = (l) => l.interventions >= minM && (!fromGroup || l.source.group === fromGroup)
  && (showExt || (l.source.kind !== 'external' && l.target.kind !== 'external')) && (showDep || (l.target.kind === 'external'));
function apply(){ const live = gv.filter(linkOk);
  document.getElementById('shown').textContent = `${fmt(live.size)} people · ${fmt(links.filter(linkOk).length)} directed edges shown`; }
mIn.addEventListener('input', () => { minM = +mIn.value; mOut.textContent = fmt(minM); apply(); });
gSel.addEventListener('change', () => { fromGroup = gSel.value; apply(); });
document.getElementById('ext').addEventListener('change', (e) => { showExt = e.target.checked; apply(); });
document.getElementById('dep').addEventListener('change', (e) => { showDep = e.target.checked; apply(); });

// neighbours, tooltip, details
function focusNode(d){ const s = new Set([d.id]); links.forEach((l) => { if (l.source.id === d.id) s.add(l.target.id); if (l.target.id === d.id) s.add(l.source.id); });
  node.classed('dim', (x) => !s.has(x.id)); label.classed('dim', (x) => !s.has(x.id)); link.classed('dim', (l) => l.source.id !== d.id && l.target.id !== d.id); }
function clearFocus(){ node.classed('dim', false); label.classed('dim', false); link.classed('dim', false); }
const rows = (d) => [[d.name, d.group + (d.role ? ' · ' + d.role : '')], [fmt(d.in_strength), 'interventions mention them'],
  [fmt(d.out_strength), 'interventions where they mention others'], [String(d.pagerank), 'PageRank']];
node.on('mouseenter', (ev, d) => { focusNode(d); showTip(ev, rows(d)); }).on('mousemove', (ev, d) => showTip(ev, rows(d)))
  .on('mouseleave', () => { clearFocus(); hideTip(); }).on('focus', (ev, d) => focusNode(d)).on('blur', clearFocus)
  .on('click', (ev, d) => showNode(d)).on('keydown', (ev, d) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); showNode(d); } });
hit.on('mouseenter', (ev, l) => showTip(ev, [[`${l.source.name} → ${l.target.name}`, ''], [fmt(l.interventions), 'interventions'],
    [fmt(l.mentions), 'mentions'], [fmt(l.sessions), 'sessions']])).on('mouseleave', hideTip).on('click', (ev, l) => showEdge(l));
const panel = document.getElementById('panel');
function list(title, items){ if (!items.length) return document.createTextNode(''); const box = el('div', {class:'ex'}); box.append(el('div', {class:'meta'}, title));
  const ul = el('ul'); items.slice(0, 8).forEach(([n, v]) => ul.append(el('li', {}, `${n} — ${fmt(v)}`))); box.append(ul); return box; }
function showNode(d){ openPanel(); const inn = links.filter((l) => l.target.id === d.id).map((l) => [l.source.name, l.interventions]).sort((a, b) => b[1] - a[1]);
  const out = links.filter((l) => l.source.id === d.id).map((l) => [l.target.name, l.interventions]).sort((a, b) => b[1] - a[1]);
  panel.replaceChildren(el('h2', {}, d.name), el('p', {class:'kv'}, rows(d).slice(1).map(([v, l]) => `${v} ${l}`).join(' · ')),
    list('Mentioned most by', inn), list('Mentions most', out)); }
function showEdge(l){ openPanel(); panel.replaceChildren(el('h2', {}, `${l.source.name} → ${l.target.name}`),
    el('p', {class:'kv'}, `${fmt(l.interventions)} interventions · ${fmt(l.mentions)} mentions · ${fmt(l.sessions)} sessions`));
  (l.examples || []).forEach((x) => { const box = el('div', {class:'ex'}); box.append(el('div', {class:'meta'}, x.id_int), kwicLine(x)); panel.append(box); }); }

// legend
function legend(){ const lg = document.getElementById('legend'); lg.replaceChildren();
if (groupBy === 'group') groupsOrder.forEach((g) => { const sp = el('span'); const sw = el('span', {class:'sw'}); sw.style.background = `var(${colourOf(g)})`;
  if (g === 'external') sw.style.borderRadius = '0'; sp.append(sw, document.createTextNode(g === 'external' ? 'external actors (square)'
    : (slot.has(g) ? g : g + ' (other)'))); lg.append(sp); });
else [...new Set(nodes.map((d) => d.community))].filter((c) => c !== null && c !== undefined).sort((a, b) => a - b).forEach((c) => {
  const sp = el('span'); const sw = el('span', {class:'sw'}); sw.style.background = `var(${commColour(c)})`;
  sp.append(sw, document.createTextNode(c < 30 ? commName(c) : 'other communities')); lg.append(sp); });
lg.append(el('span', {}, 'size = interventions that mention them (√, up to «node size») · arrow = who mentions whom · ' +
  'line width = interventions (√, up to «edge width»)')); }
legend();
const gbSel = document.getElementById('groupby');
gbSel.addEventListener('change', () => { groupBy = gbSel.value; gv.draw(); legend(); gv.relayout(); });

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
  document.getElementById('vgraph').setAttribute('aria-pressed', 'true'); document.getElementById('vheat').setAttribute('aria-pressed', 'false'); gv.fit(false); });
document.getElementById('vheat').addEventListener('click', () => { document.getElementById('graphview').hidden = true; heat.hidden = false;
  document.getElementById('vgraph').setAttribute('aria-pressed', 'false'); document.getElementById('vheat').setAttribute('aria-pressed', 'true'); });

// twin tables
sortableTable(document.getElementById('tnodes'), [{key:'name', label:'person'}, {key:'group', label:'group'}, {key:'kind', label:'kind'},
  {key:'in_strength', label:'mentioned in', num:true}, {key:'out_strength', label:'mentions others in', num:true},
  {key:'pagerank', label:'PageRank', num:true, digits:4}, {key:'community', label:'community', num:true}], DATA.nodes);
sortableTable(document.getElementById('tedges'), [{key:'source_name', label:'from'}, {key:'target_name', label:'to'},
  {key:'interventions', label:'interventions', num:true}, {key:'mentions', label:'mentions', num:true}, {key:'sessions', label:'sessions', num:true}], DATA.edges);
apply(); gv.fit(false); themeButton();
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
    <label>layout <select id="layout"><option value="force">force</option><option value="clusters">separated groups</option>
      <option value="rings">rings (centrifugal)</option></select></label>
    <label>groups <select id="groupby"><option value="group">party (colour)</option>
      <option value="community">community</option></select></label>
    <label>min interventions <input type="range" id="minm"><output id="minmOut"></output></label>
    <label>from group <select id="from"><option value="">all</option></select></label>
    <label><input type="checkbox" id="dep" checked> deputies</label>
    <label><input type="checkbox" id="ext" checked> external actors</label>
    <label>node size <input type="range" id="maxr" aria-label="largest node radius"><output id="maxrOut"></output></label>
    <label>edge width <input type="range" id="maxw" aria-label="widest line"><output id="maxwOut"></output></label>
    <button id="labels" aria-pressed="false">all labels</button><button id="reset">reset view</button>
    <button id="panelbtn" aria-controls="panel" aria-expanded="true">hide panel</button>
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


def words_page(res: dict) -> str:
    p = res["parameters"]
    library = (p.get("filters") or {}).get("library") or ""
    title = f"Word co-occurrence network · {library} · {res['country']}"
    s = res["stats"]
    unit = "intervention" if p["unit"] == "intervention" else f"fragments of {p['fragment']} tokens"
    subtitle = (f"{res['N']:,} interventions · {res['vocabulary']['used']} terms · {s['kept_edges']} edges · "
                f"{s['themes']} themes · unit: {unit} · k = {p['neighbours']} neighbours · G² ≥ {p['g2_min']} · "
                f"Leiden γ = {p['resolution']}, seed {p['seed']}")
    sw = p["stopwords"]
    ex = p["expressions"]
    body = f"""
<div class="layout">
 <section class="card" aria-label="Network">
  <div class="controls">
   <label>layout <select id="layout"><option value="force">force</option><option value="clusters">separated groups</option>
     <option value="rings">rings (centrifugal)</option></select></label>
   <label>theme <select id="theme-select"><option value="">all</option></select></label>
   <label>size <select id="size"><option value="freq">frequency</option><option value="strength">strength</option>
     <option value="g2_lexicon">G² in the lexicon</option></select></label>
   <label>node size <input type="range" id="maxr" aria-label="largest node radius"><output id="maxrOut"></output></label>
   <label>edge width <input type="range" id="maxw" aria-label="widest line"><output id="maxwOut"></output></label>
   <button id="labels" aria-pressed="false">all labels</button>
   <button id="reset">reset view</button>
   <button id="panelbtn" aria-controls="panel" aria-expanded="true">hide panel</button>
   <button id="theme" aria-label="switch light or dark theme">theme</button>
  </div>
  <svg id="chart" role="img" aria-label="Network of the library's characteristic words, coloured by theme; the same data are in the tables below"></svg>
  <div class="legend" id="legend"></div>
  <p class="sub" id="shown" aria-live="polite"></p>
 </section>
 <aside class="card" id="panel" aria-live="polite"></aside>
</div>
<details><summary>Themes (table)</summary><div id="tthemes"></div></details>
<details><summary>Terms (table)</summary><div id="tnodes"></div></details>
<details><summary>Edges (table)</summary><div id="tedges"></div></details>
<footer>
 <p><strong>How it is made.</strong> The nodes are the library's most characteristic words and expressions: its lexicon
 against the rest of the country's corpus (signed G², the {p['vocabulary']} most over-used), without numbers and without
 the {html.escape(sw['source'])} stopwords of the language ({html.escape(sw['language'])}, {html.escape(sw['license'])}).
 Two terms are joined when they occur in the same {html.escape(unit)} more often than chance (G² ≥ {p['g2_min']}) and the
 edge is among the {p['neighbours']} strongest of either term; its width is the association strength, observed / expected.
 Themes are Leiden communities of three terms or more. {'Multi-word expressions of the corpus are one node each.' if ex.get('used') else html.escape(ex.get('reason') or '')}</p>
 <p><strong>Method.</strong> {html.escape(p['method'])}. Differences: {html.escape(' '.join(p['deviations']))}</p>
 <p>Data: {' · '.join(html.escape(c) for c in res['citation'])}. CC BY 4.0. Stopwords: {html.escape(sw.get('url') or '')}
 ({html.escape(sw.get('copyright') or '')}).</p>
 <p>Generated with {html.escape(p['engine'])} on {html.escape(p['generated'])}.</p>
</footer>"""
    return _page(title, subtitle, body, res, COMMON_JS + WORDS_JS).replace("</style>", WORDS_CSS + "</style>", 1)
