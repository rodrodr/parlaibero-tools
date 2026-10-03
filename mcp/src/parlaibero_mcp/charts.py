"""Ngram-style line charts written as standalone SVG or HTML, with no plotting dependencies.

Palette: the validated 8-slot categorical palette (light and dark steps), assigned in fixed order.
Three light slots sit below 3:1 contrast on the surface, so every line carries a direct label at
its end (and the HTML version adds a data table): identity never depends on color alone.
"""
from __future__ import annotations

import html
import json
import math
from pathlib import Path

LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
DARK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]
MAX_SERIES = len(LIGHT)

W, H = 960, 560
M_LEFT, M_TOP, M_BOTTOM = 64, 112, 78
LABEL_MAX = 34          # characters of a direct label before it is shortened with "…"


def _right_margin(names) -> int:
    longest = max((len(_short(n)) for n in names), default=10)
    return int(min(300, max(120, 30 + 7.0 * longest)))


def _short(name: str) -> str:
    return name if len(name) <= LABEL_MAX else name[: LABEL_MAX - 1] + "…"
FONT = "Archivo, 'Helvetica Neue', Arial, sans-serif"


def _nice_ticks(lo: float, hi: float, n: int = 5) -> list[float]:
    if hi <= lo:
        hi = lo + 1
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(s * mag for s in (1, 2, 2.5, 5, 10) if s * mag >= raw)
    start = math.floor(lo / step) * step
    ticks, t = [], start
    while t <= hi + step * 0.5:
        ticks.append(round(t, 10))
        t += step
    return ticks


def _fmt(v: float) -> str:
    if v == 0:
        return "0"
    if abs(v) >= 100:
        return f"{v:,.0f}".replace(",", " ")
    if abs(v) >= 10:
        return f"{v:.0f}"
    if abs(v) >= 1:
        return f"{v:.1f}".rstrip("0").rstrip(".")
    return f"{v:.2g}"


def _esc(s: str) -> str:
    return html.escape(str(s), quote=True)


def _legend_rows(series) -> int:
    if len(series) < 2:
        return 0
    rows, lx = 1, M_LEFT
    for name in series:
        wdt = 24 + 7.2 * len(_short(name)) + 22
        if lx > M_LEFT and lx + wdt > W - 16:
            rows, lx = rows + 1, M_LEFT
        lx += wdt
    return rows


def _top(series) -> int:
    return M_TOP + 20 * max(0, _legend_rows(series) - 1)


def _wrap(text: str, chars: int = 116) -> list[str]:
    """Break a ' · '-separated subtitle into lines that fit the chart width."""
    lines, cur = [], ""
    for part in text.split(" · "):
        cand = part if not cur else cur + " · " + part
        if cur and len(cand) > chars:
            lines.append(cur)
            cur = part
        else:
            cur = cand
    return lines + [cur] if cur else lines


def _layout(series: dict[str, list[dict]], m_right: int, extra: int = 0):
    xs = [p["x"] for pts in series.values() for p in pts if p.get("y") is not None]
    ys = [p["y"] for pts in series.values() for p in pts if p.get("y") is not None]
    if not xs:
        raise ValueError("Nothing to plot: every series is empty")
    x0, x1 = min(xs), max(xs)
    if x0 == x1:
        x0, x1 = x0 - 1, x1 + 1
    yt = _nice_ticks(0, max(ys) if ys else 1)
    y1 = yt[-1] or 1
    top = _top(series) + extra
    pw, ph = W - M_LEFT - m_right, H - top - M_BOTTOM

    def sx(x):
        return M_LEFT + (x - x0) / (x1 - x0) * pw

    def sy(y):
        return top + ph - y / y1 * ph

    return x0, x1, yt, sx, sy, pw, ph


def svg_chart(series: dict[str, list[dict]], title: str, subtitle: str, y_label: str,
              note: str, low_base_note: str | None = None) -> str:
    """series: name → [{"x": year, "y": value or None, "low": bool}], at most 8 series."""
    if len(series) > MAX_SERIES:
        raise ValueError(f"At most {MAX_SERIES} series per chart; split the rest into another chart")
    m_right = _right_margin(series)
    sub_lines = _wrap(subtitle)
    extra = 18 * (len(sub_lines) - 1)
    x0, x1, yt, sx, sy, pw, ph = _layout(series, m_right, extra)
    top = _top(series) + extra
    o: list[str] = []
    o.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
             f'role="img" aria-labelledby="t d" font-family="{FONT}" class="pi-chart">')
    o.append(f'<title id="t">{_esc(title)}</title><desc id="d">{_esc(subtitle)}. {_esc(note)}</desc>')
    o.append('<style>.pi-chart{--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--grid:#e6e5e0;--axis:#a3a29c;'
             + "".join(f"--s{i}:{c};" for i, c in enumerate(LIGHT)) + "}"
             '.pi-chart .bg{fill:var(--surface)}.pi-chart .t1{fill:var(--ink);font-size:20px;font-weight:700}'
             '.pi-chart .t2{fill:var(--ink2);font-size:14px}.pi-chart .tick{fill:var(--ink2);font-size:12px}'
             '.pi-chart .grid{stroke:var(--grid);stroke-width:1}.pi-chart .axis{stroke:var(--axis);stroke-width:1}'
             '.pi-chart .lab{fill:var(--ink);font-size:13px}.pi-chart .note{fill:var(--ink2);font-size:11px}'
             + "".join(f".pi-chart .c{i}{{stroke:var(--s{i})}}.pi-chart .f{i}{{fill:var(--s{i})}}"
                       for i in range(MAX_SERIES))
             + '.pi-chart .hollow{fill:var(--surface);stroke-width:2}</style>')
    o.append(f'<rect class="bg" width="{W}" height="{H}"/>')
    o.append(f'<text class="t1" x="{M_LEFT}" y="34">{_esc(title)}</text>')
    for k, line in enumerate(sub_lines):
        o.append(f'<text class="t2" x="{M_LEFT}" y="{56 + 18 * k}">{_esc(line)}</text>')
    # legend (always present for >= 2 series), wrapped onto as many rows as needed
    if len(series) >= 2:
        lx, ly = M_LEFT, 80 + extra
        for i, name in enumerate(series):
            wdt = 24 + 7.2 * len(_short(name)) + 22
            if lx > M_LEFT and lx + wdt > W - 16:
                lx, ly = M_LEFT, ly + 20
            o.append(f'<line class="c{i}" x1="{lx}" y1="{ly}" x2="{lx + 18}" y2="{ly}" stroke-width="3" '
                     f'stroke-linecap="round"/>')
            o.append(f'<text class="lab" x="{lx + 24}" y="{ly + 4}">{_esc(_short(name))}</text>')
            lx += wdt
    # grid + y axis
    for t in yt:
        y = sy(t)
        o.append(f'<line class="grid" x1="{M_LEFT}" y1="{y:.1f}" x2="{M_LEFT + pw}" y2="{y:.1f}"/>')
        o.append(f'<text class="tick" x="{M_LEFT - 8}" y="{y + 4:.1f}" text-anchor="end">{_fmt(t)}</text>')
    o.append(f'<text class="tick" x="{M_LEFT}" y="{top - 10}">{_esc(y_label)}</text>')
    # x axis
    span = x1 - x0
    step = next(s for s in (1, 2, 5, 10, 20, 25, 50) if span / s <= 12)
    o.append(f'<line class="axis" x1="{M_LEFT}" y1="{top + ph}" x2="{M_LEFT + pw}" y2="{top + ph}"/>')
    for x in range(math.ceil(x0 / step) * step, int(x1) + 1, step):
        o.append(f'<text class="tick" x="{sx(x):.1f}" y="{top + ph + 20}" text-anchor="middle">{x}</text>')
    # lines: a gap (y None) breaks the line instead of drawing through it
    ends = []
    for i, (name, pts) in enumerate(series.items()):
        seg: list[str] = []
        segs = []
        for p in pts:
            if p.get("y") is None:
                if seg:
                    segs.append(seg)
                seg = []
            else:
                seg.append(f"{sx(p['x']):.1f},{sy(p['y']):.1f}")
        if seg:
            segs.append(seg)
        for s in segs:
            if len(s) == 1:
                x, y = s[0].split(",")
                o.append(f'<circle class="f{i}" cx="{x}" cy="{y}" r="3"/>')
            else:
                o.append(f'<polyline class="c{i}" fill="none" stroke-width="2" stroke-linejoin="round" '
                         f'stroke-linecap="round" points="{" ".join(s)}"/>')
        for p in pts:
            if p.get("y") is not None and p.get("low"):
                o.append(f'<circle class="c{i} hollow" cx="{sx(p["x"]):.1f}" cy="{sy(p["y"]):.1f}" r="4"/>')
        last = next((p for p in reversed(pts) if p.get("y") is not None), None)
        if last:
            ends.append([sy(last["y"]), i, name, sx(last["x"])])
    # direct labels at the line ends, nudged apart so they never collide
    ends.sort()
    for k in range(1, len(ends)):
        if ends[k][0] - ends[k - 1][0] < 16:
            ends[k][0] = ends[k - 1][0] + 16
    for y, i, name, x in ends:
        o.append(f'<circle class="f{i}" cx="{M_LEFT + pw + 10}" cy="{y:.1f}" r="4"/>')
        o.append(f'<text class="lab" x="{M_LEFT + pw + 18}" y="{y + 4:.1f}">{_esc(_short(name))}</text>')
    ny = H - 34
    if low_base_note:
        o.append(f'<circle class="hollow" cx="{M_LEFT + 4}" cy="{ny - 4}" r="4" style="stroke:var(--ink2)"/>')
        o.append(f'<text class="note" x="{M_LEFT + 14}" y="{ny}">{_esc(low_base_note)}</text>')
        ny += 16
    o.append(f'<text class="note" x="{M_LEFT}" y="{ny}">{_esc(note)}</text>')
    o.append("</svg>")
    return "\n".join(o)


def html_page(svg: str, series: dict[str, list[dict]], title: str, y_label: str, note: str) -> str:
    """Wrap the SVG in a page with dark mode, a hover read-out and the data table."""
    years = sorted({p["x"] for pts in series.values() for p in pts})
    table = {name: {p["x"]: p.get("y") for p in pts} for name, pts in series.items()}
    head = "".join(f"<th>{_esc(n)}</th>" for n in series)
    body = "".join(
        f"<tr><th>{y}</th>" + "".join(
            f"<td>{'' if table[n].get(y) is None else _fmt(table[n][y])}</td>" for n in series) + "</tr>"
        for y in years)
    dark = "".join(f"--s{i}:{c};" for i, c in enumerate(DARK))
    data = json.dumps({"years": years, "series": {n: [table[n].get(y) for y in years] for n in series}})
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title>
<style>
:root{{--page:#f7f6f3;--ink:#0b0b0b;--ink2:#52514e}}
@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{--page:#121211;--ink:#fff;--ink2:#c3c2b7}}
 :root:not([data-theme="light"]) .pi-chart{{--surface:#1a1a19!important;--ink:#fff!important;--ink2:#c3c2b7!important;
 --grid:#33332f!important;--axis:#6b6a64!important;{dark.replace(";", "!important;")}}}}}
body{{margin:0;padding:16px;background:var(--page);color:var(--ink);font-family:{FONT}}}
main{{max-width:{W}px;margin:0 auto}} svg{{width:100%;height:auto;display:block}}
#tip{{min-height:1.4em;font-size:13px;color:var(--ink2);margin:6px 0}}
details{{margin-top:12px;font-size:13px}} table{{border-collapse:collapse;margin-top:8px}}
th,td{{padding:2px 10px;text-align:right;border-bottom:1px solid #8884}} thead th{{position:sticky;top:0;background:var(--page)}}
</style></head><body><main>
{svg}
<div id="tip" aria-live="polite">Pasa el cursor sobre el gráfico para leer los valores de cada año.</div>
<details><summary>Datos ({_esc(y_label)})</summary><table><thead><tr><th>año</th>{head}</tr></thead><tbody>{body}</tbody></table></details>
</main>
<script>
const D={data};const svg=document.querySelector('svg.pi-chart');const tip=document.getElementById('tip');
const pts=[...svg.querySelectorAll('polyline')];
svg.addEventListener('mousemove',e=>{{const r=svg.getBoundingClientRect();const vx=(e.clientX-r.left)/r.width*{W};
 const x0={M_LEFT},x1={W - _right_margin(series)};if(vx<x0||vx>x1){{return}}
 const t=(vx-x0)/(x1-x0);const y=Math.round(D.years[0]+t*(D.years[D.years.length-1]-D.years[0]));
 const i=D.years.indexOf(y);if(i<0)return;
 tip.textContent=y+' · '+Object.entries(D.series).map(([n,v])=>n+': '+(v[i]==null?'—':(+v[i]).toLocaleString('es-ES',{{maximumFractionDigits:2}}))).join(' · ');}});
</script></body></html>"""


def write_chart(path: str, series, title, subtitle, y_label, note, low_base_note=None,
                overwrite: bool = False) -> str:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    if p.suffix.lower() not in (".svg", ".html"):
        raise ValueError("chart_path must end in .svg (figure for papers/slides) or .html (interactive page)")
    if p.exists() and not overwrite:
        raise FileExistsError(f"{p} already exists; pass overwrite=true to replace it")
    p.parent.mkdir(parents=True, exist_ok=True)
    svg = svg_chart(series, title, subtitle, y_label, note, low_base_note)
    p.write_text(svg if p.suffix.lower() == ".svg" else html_page(svg, series, title, y_label, note),
                 encoding="utf-8")
    return str(p)
