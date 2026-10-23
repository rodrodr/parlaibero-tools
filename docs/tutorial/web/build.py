"""Builds the tutorial web page (one HTML file, Spanish and English) from docs/tutorial/TUTORIAL*.md.

    uv run --with markdown-it-py python docs/tutorial/web/build.py docs/tutorial OUT_DIR \
        EJEMPLOS_OUT/redes/mencoes/tutorial_previdencia_mentions_block_matrix.csv

EJEMPLOS_OUT is the folder given to ejemplos.py; the mention matrix is drawn as a table instead of its screenshot.
"""
import csv
import html
import re
import shutil
import sys
from pathlib import Path

from markdown_it import MarkdownIt

SRC, OUT, MATRIX = (Path(a) for a in sys.argv[1:4])
OUT.mkdir(parents=True, exist_ok=True)
GH = "https://github.com/rodrodr/parlaibero-tools/blob/main/"
LINKS = {"](ejemplos.py)": f"]({GH}docs/tutorial/ejemplos.py)",
         "](../../mcp/README.md)": f"]({GH}mcp/README.md)",
         "](../../mcp/src/parlaibero_mcp/methods_networks.md)": f"]({GH}mcp/src/parlaibero_mcp/methods_networks.md)"}
md = MarkdownIt("commonmark", {"html": False}).enable("table")
inline = md.renderInline

COUNTRIES = ["AR", "BR", "CL", "CO", "CR", "DO", "EC", "ES", "GT", "MX", "PA", "PE", "PT", "PY", "SV", "UY"]
UI = {
    "es": dict(result="Resultado", contents="Contenido", copy="Copiar", copied="Copiado",
               WARNING="Atención", NOTE="Nota", IMPORTANT="Importante", eyebrow="Tutorial · parlaibero-mcp 0.6.0",
               parl="16 parlamentos", groups={"esquerda": "esquerda", "direita": "direita", "rest": "resto"},
               corner="nombra ↓ · nombrado →",
               matrix_caption="Menciones por cada 100 intervenciones del grupo que nombra; entre paréntesis, el "
                              "recuento. Cuanto más intenso el tono, más menciones. «Resto»: oradores fuera de los "
                              "dos grupos.",
               names=["Argentina", "Brasil", "Chile", "Colombia", "Costa Rica", "República Dominicana", "Ecuador",
                      "España", "Guatemala", "México", "Panamá", "Perú", "Portugal", "Paraguay", "El Salvador",
                      "Uruguay"],
               foot="Resultados obtenidos con parlaibero-mcp 0.6.0 sobre las versiones 2.0 de los conjuntos de "
                    "ParlaIbero en Harvard Dataverse (CC BY 4.0). Las citas de discursos omiten el nombre de quien "
                    "habla.",
               repo="Código en GitHub", pypi="parlaibero-mcp en PyPI", readme="Documentación técnica"),
    "en": dict(result="Result", contents="Contents", copy="Copy", copied="Copied",
               WARNING="Warning", NOTE="Note", IMPORTANT="Important", eyebrow="Tutorial · parlaibero-mcp 0.6.0",
               parl="16 parliaments", groups={"esquerda": "esquerda", "direita": "direita", "rest": "rest"},
               corner="names ↓ · named →",
               matrix_caption="Mentions per 100 interventions of the naming group; the count in brackets. The "
                              "deeper the tone, the more mentions. “Rest”: speakers outside the two groups.",
               names=["Argentina", "Brazil", "Chile", "Colombia", "Costa Rica", "Dominican Republic", "Ecuador",
                      "Spain", "Guatemala", "Mexico", "Panama", "Peru", "Portugal", "Paraguay", "El Salvador",
                      "Uruguay"],
               foot="Results obtained with parlaibero-mcp 0.6.0 on the 2.0 versions of the ParlaIbero datasets in "
                    "Harvard Dataverse (CC BY 4.0). Quotations of speeches leave out the speaker's name.",
               repo="Code on GitHub", pypi="parlaibero-mcp on PyPI", readme="Technical documentation"),
}
ICONS = {
    "WARNING": '<path d="M10 2.5 18.5 17h-17z"/><path d="M10 8v4"/><circle cx="10" cy="14.5" r=".6"/>',
    "NOTE": '<circle cx="10" cy="10" r="8"/><path d="M10 9v5"/><circle cx="10" cy="6.2" r=".6"/>',
    "IMPORTANT": '<path d="M3 3.5h14v10H8l-4 3v-3H3z"/><path d="M10 6v4"/><circle cx="10" cy="12" r=".6"/>',
}


def blocks(lines):
    """Splits markdown lines into typed blocks; the tutorial only uses a handful of constructs."""
    out, i, n = [], 0, len(lines)
    while i < n:
        line = lines[i]
        if not line.strip() or line.strip() == "---":
            i += 1
        elif line.startswith("```"):
            j, buf = i + 1, []
            while not lines[j].startswith("```"):
                buf.append(lines[j])
                j += 1
            out.append(("code", line[3:].strip(), "\n".join(buf)))
            i = j + 1
        elif line.startswith(">"):
            buf = []
            while i < n and lines[i].startswith(">"):
                buf.append(re.sub(r"^> ?", "", lines[i]))
                i += 1
            out.append(quote(buf))
        elif line.startswith("|"):
            buf = []
            while i < n and lines[i].startswith("|"):
                buf.append(lines[i])
                i += 1
            out.append(("table", "\n".join(buf)))
        elif line.startswith("!["):
            m = re.match(r"!\[(.*)\]\((.*)\)", line)
            out.append(("img", m[1], m[2]))
            i += 1
        elif line.startswith("## "):
            out.append(("h2", line[3:]))
            i += 1
        elif line.startswith("### "):
            out.append(("h3", line[4:]))
            i += 1
        elif re.match(r"(- |\d+\. )", line):
            buf = []
            while i < n and lines[i].strip():
                buf.append(lines[i])
                i += 1
            out.append(("list", "\n".join(buf)))
        else:
            buf = [line]
            i += 1
            while i < n and lines[i].strip() and not re.match(r"(```|>|\||!\[|#|- |\d+\. )", lines[i]):
                buf.append(lines[i])
                i += 1
            out.append(("p", "\n".join(buf)))
    return out


def quote(buf):
    m = re.match(r"\[!(\w+)\]", buf[0])
    if m:
        return ("alert", m[1], "\n".join(buf[1:]))
    text = " ".join(x.strip() for x in buf if x.strip())
    m = re.match(r"\*\*(Pide|Ask):\*\*\s*(.*?)\s*\*(El agente usa|The agent uses)\*\s*(.*)$", text)
    return ("ask", *m.groups()) if m else ("quote", text)


def pre_html(lang, content, ui):
    copy = (f'<button type="button" class="copy" data-done="{ui["copied"]}">{ui["copy"]}</button>'
            if lang in ("bash", "json", "sql") else "")
    return f'<div class="pre" data-lang="{lang}">{copy}<pre><code>{html.escape(content)}</code></pre></div>'


def table_html(text):
    return f'<div class="tablewrap">{md.render(text)}</div>'


def svg_html(src, lang):
    s = (SRC / src).read_text(encoding="utf-8")
    s = (s.replace('id="t"', f'id="{lang}-fig-t"').replace('id="d"', f'id="{lang}-fig-d"')
          .replace('aria-labelledby="t d"', f'aria-labelledby="{lang}-fig-t {lang}-fig-d"'))
    s = re.sub(r'(<svg[^>]*?) width="\d+" height="\d+"', r"\1", s, count=1)
    return f'<figure class="fig fig-svg">{s}</figure>'


def matrix_html(lang, ui):
    rows = list(csv.DictReader(MATRIX.open(encoding="utf-8")))
    vals = {(r["from"], r["to"]): (float(r["per_100_interventions"]), int(r["mentions"])) for r in rows}
    lo, hi = min(v[0] for v in vals.values()), max(v[0] for v in vals.values())
    groups = ["direita", "esquerda", "rest"]
    fmt = (lambda v: f"{v:.1f}".replace(".", ",")) if lang == "es" else (lambda v: f"{v:.1f}")
    head = "".join(f'<th scope="col">{ui["groups"][g]}</th>' for g in groups)
    body = []
    for a in groups:
        cells = []
        for b in groups:
            if (a, b) in vals:
                v, c = vals[(a, b)]
                q = min(4, int((v - lo) / (hi - lo) * 5))
                cells.append(f'<td class="q{q}">{fmt(v)} <span>({c})</span></td>')
            else:
                cells.append('<td class="qn">—</td>')
        body.append(f'<tr><th scope="row">{ui["groups"][a]}</th>{"".join(cells)}</tr>')
    return (f'<figure class="fig fig-matrix"><div class="tablewrap"><table class="matrix"><thead><tr>'
            f'<th class="corner">{ui["corner"]}</th>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'
            f'<figcaption>{ui["matrix_caption"]}</figcaption></figure>')


def img_html(alt, src, lang, ui):
    if src.endswith(".svg"):
        return svg_html(src, lang)
    if "menciones_grupos" in src:
        return matrix_html(lang, ui)
    shutil.copy(SRC / src, OUT / src)
    return (f'<figure class="fig"><img src="{src}" width="1280" height="860" alt="{html.escape(alt)}" loading="lazy">'
            f'<figcaption>{inline(alt)}</figcaption></figure>')


def ask_html(b, results, lang, ui, legend=False):
    _, k_ask, ask, k_tool, tool = b
    tool_html = inline(tool)
    if tool.startswith("`"):
        tool_html = tool_html.replace("<code>", '<code class="tool">', 1)
    out = ""
    if results:
        name = re.match(r"`([^`]+)`", tool)
        parts = []
        for r in results:
            if r[0] == "code":
                parts.append(pre_html(r[1], r[2], ui))
            elif r[0] == "table":
                parts.append(table_html(r[1]))
            else:
                parts.append(img_html(r[1], r[2], lang, ui))
        out = (f'<div class="ex-out"><div class="ex-out-h"><span>{ui["result"]}</span>'
               f'{f"<code>{html.escape(name[1])}</code>" if name else ""}</div>{"".join(parts)}</div>')
    return (f'<div class="ex{" legend" if legend else ""}"><div class="ex-ask"><span class="ex-k">{k_ask}</span>'
            f'<p class="ex-q">{inline(ask)}</p></div><div class="ex-agent"><p class="ex-call">'
            f'<span class="ex-k">{k_tool}</span> {tool_html}</p>{out}</div></div>')


def steps_html(text):
    items = []
    for it in re.split(r"\n(?=\d+\. )", text):
        it = " ".join(x.strip() for x in re.sub(r"^\d+\.\s*", "", it).split("\n"))
        m = re.match(r"(.*?)\s*\(((?:`[^`]*`(?:,\s*)?)+)\)\s*$", it)
        items.append(f'<li><p class="step-q">{inline(m[1])}</p><p class="step-t">{inline(m[2])}</p></li>')
    return f'<ol class="steps">{"".join(items)}</ol>'


def tools_html(text):
    rows = []
    for r in text.split("\n")[2:]:
        k, v = (c.strip() for c in r.strip().strip("|").split("|"))
        rows.append(f'<div class="tools-row"><div class="tools-k">{inline(k)}</div>'
                    f'<div class="tools-v">{inline(v)}</div></div>')
    return f'<div class="tools">{"".join(rows)}</div>'


def render(lang, text):
    ui = UI[lang]
    for a, b in LINKS.items():
        text = text.replace(a, b)
    lines = text.split("\n")
    title = lines[0].lstrip("# ").split(": ", 1)[1]
    k = next(i for i, l in enumerate(lines) if l.strip() in ("**Contenido**", "**Contents**"))
    s = next(i for i, l in enumerate(lines) if l.startswith("## "))
    intro = blocks([l for l in lines[1:k] if not l.startswith("*[")])
    lede, howto = intro[0], intro[1:]
    howto_html = "".join(ask_html(b, [], lang, ui, legend=True) if b[0] == "ask" else md.render(b[1])
                         for b in howto)

    body, toc, sec, i = [], [], None, 0
    bl = blocks(lines[s:])
    while i < len(bl):
        b = bl[i]
        if b[0] == "h2":
            num, name = re.match(r"(\d+)\. (.*)", b[1]).groups()
            sec = num
            body.append(("</section>" if toc else "") + f'<section class="sec"><h2 id="{lang}-{num}">'
                        f'<span class="num">§ {num}</span><span>{inline(name)}</span></h2>')
            toc.append((f"{lang}-{num}", num, name, 2))
        elif b[0] == "h3":
            num, name = re.match(r"(\d+\.\d+) (.*)", b[1]).groups()
            hid = f"{lang}-{num.replace('.', '-')}"
            body.append(f'<h3 id="{hid}"><span class="num">{num}</span> {inline(name)}</h3>')
            toc.append((hid, num, name, 3))
        elif b[0] == "ask":
            res, j = [], i + 1
            while j < len(bl) and bl[j][0] in ("code", "table", "img"):
                res.append(bl[j])
                j += 1
            body.append(ask_html(b, res, lang, ui))
            i = j
            continue
        elif b[0] == "alert":
            kind = b[1]
            body.append(f'<aside class="callout {kind.lower()}"><svg viewBox="0 0 20 20" width="20" height="20" '
                        f'fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" '
                        f'stroke-linecap="round" aria-hidden="true">{ICONS[kind]}</svg><div>'
                        f'<span class="callout-k">{ui[kind]}</span>{md.render(b[2])}</div></aside>')
        elif b[0] == "code":
            body.append(pre_html(b[1], b[2], ui))
        elif b[0] == "table":
            body.append(tools_html(b[1]) if sec == "10" else table_html(b[1]))
        elif b[0] == "img":
            body.append(img_html(b[1], b[2], lang, ui))
        elif b[0] == "list" and sec == "9":
            body.append(steps_html(b[1]))
        else:
            body.append(md.render(b[1]))
        i += 1
    body.append("</section>")

    toc_html = "".join(
        f'<li class="{"sub" if lvl == 3 else ""}"><a href="#{hid}"><span class="n">{num}</span>'
        f'<span>{inline(name)}</span></a></li>' for hid, num, name, lvl in toc)
    parl = "".join(f'<abbr title="{n}">{c}</abbr>' for c, n in zip(COUNTRIES, ui["names"]))
    return f"""<div class="lang" id="lang-{lang}" lang="{lang}"{' hidden' if lang == 'en' else ''}>
<header class="mast"><div class="wrap mast-grid">
<div class="mast-text"><p class="eyebrow">{ui["eyebrow"]}</p><h1>{inline(title)}</h1>
<div class="lede">{md.render(lede[1])}</div>
<div class="parl"><span class="parl-k">{ui["parl"]}</span>{parl}</div></div>
<aside class="howto">{howto_html}</aside>
</div></header>
<div class="wrap shell">
<details class="toc" open><summary>{ui["contents"]}</summary><ol>{toc_html}</ol></details>
<main class="doc">{"".join(body)}</main>
</div>
<footer class="foot"><div class="wrap"><p>{ui["foot"]}</p><p class="foot-links">
<a href="https://github.com/rodrodr/parlaibero-tools">{ui["repo"]}</a>
<a href="https://pypi.org/project/parlaibero-mcp/">{ui["pypi"]}</a>
<a href="{GH}mcp/README.md">{ui["readme"]}</a></p></div></footer>
</div>"""


(OUT / "img").mkdir(exist_ok=True)
es = render("es", (SRC / "TUTORIAL.md").read_text(encoding="utf-8"))
en = render("en", (SRC / "TUTORIAL.en.md").read_text(encoding="utf-8"))
page = (Path(__file__).with_name("template.html").read_text(encoding="utf-8")
        .replace("<!--ES-->", es).replace("<!--EN-->", en))
(OUT / "tutorial_parlaibero.html").write_text(page, encoding="utf-8")
print(len(page), "bytes")
