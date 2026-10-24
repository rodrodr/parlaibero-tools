"""Builds the tutorial site (site/ at the repository root) from the Markdown pages of docs/tutorial.

    uv run --with markdown-it-py python docs/tutorial/web/build.py

The Markdown is the source and reads on its own in GitHub; the site adds what Markdown cannot hold. Directives:
  <!-- eyebrow: TEXT -->   the line above the page title
  <!-- side -->            what follows, up to the first section, goes into the card beside the title
  <!-- viz:ID -->          a chart drawn from web/data/ID.json; the table right after it becomes its data
  <!-- table:ID --> … <!-- /table -->   a table written by datos.py (the markers are skipped here)
  <!-- embed:PATH H -->    an interactive page of the MCP (web/redes/…), H pixels high
  <!-- studies -->         the cards of the four studies
  <!-- reference -->       the tools, from web/data/tools.json
  > **Pide:** … *El agente usa* …        a request to the agent and its call; what follows (code, charts,
  > **Ask:** … *The agent uses* …        tables, images) is the result
  > **Pídelo de una vez:** / **Ask for it all at once:**   one request for a whole study, with a copy button
  > [!NOTE] [!TIP] [!WARNING] [!IMPORTANT]                   callouts
Both languages go into every page; the switch shows one. Needs the data written by datos.py (web/data, web/redes).
"""
import html
import json
import re
import shutil
from pathlib import Path

from markdown_it import MarkdownIt

DOCS = Path(__file__).resolve().parents[1]               # docs/tutorial
WEB = DOCS / "web"
ROOT = DOCS.parents[1]                                     # the repository
SITE = ROOT / "site"
GH = "https://github.com/rodrodr/parlaibero-tools/blob/main/"
md = MarkdownIt("commonmark", {"html": False}).enable("table")
inline = md.renderInline

PAGES = [  # slug, Spanish source, English source, nav label (es, en)
    ("index", "TUTORIAL.md", "TUTORIAL.en.md", "Inicio", "Home"),
    ("bibliotecas", "es/bibliotecas.md", "en/bibliotecas.md", "Bibliotecas", "Libraries"),
    ("feminicidio", "es/feminicidio.md", "en/feminicidio.md", "Feminicidio", "Femicide"),
    ("pandemia", "es/pandemia.md", "en/pandemia.md", "Pandemia", "Pandemic"),
    ("voz", "es/voz.md", "en/voz.md", "Voz y escaños", "Voice and seats"),
    ("marcos", "es/marcos.md", "en/marcos.md", "Marcos", "Frames"),
    ("referencia", "es/referencia.md", "en/referencia.md", "Herramientas", "Tools"),
]
COUNTRIES = ["AR", "BR", "CL", "CO", "CR", "DO", "EC", "ES", "GT", "MX", "PA", "PE", "PT", "PY", "SV", "UY"]
FACTS = json.loads((WEB / "data" / "facts.json").read_text(encoding="utf-8"))
UI = {
    "es": dict(result="Resultado", contents="En esta página", copy="Copiar", copied="Copiado", data="Ver los datos",
               WARNING="Atención", NOTE="Nota", IMPORTANT="Importante", TIP="Consejo", parl="16 parlamentos",
               call="La llamada",
               open_page="Abrir la página completa",
               embed_note="Página que escribe la herramienta, sin los nombres de quienes hablan.",
               names=["Argentina", "Brasil", "Chile", "Colombia", "Costa Rica", "República Dominicana", "Ecuador",
                      "España", "Guatemala", "México", "Panamá", "Perú", "Portugal", "Paraguay", "El Salvador",
                      "Uruguay"],
               foot="Resultados obtenidos con parlaibero-mcp {mcp} sobre {versions} de los conjuntos ParlaIbero de "
                    "Harvard Dataverse (CC BY 4.0); el script casos.py los reproduce. Los ejemplos no nombran a "
                    "personas: las citas omiten a quien habla y las listas de palabras dejan fuera los nombres propios, "
                    "cuya lista se guarda fuera del repositorio.",
               repo="Código en GitHub", pypi="parlaibero-mcp en PyPI", readme="Documentación técnica",
               md="Esta página en Markdown", filter="Busca una herramienta o un parámetro"),
    "en": dict(result="Result", contents="On this page", copy="Copy", copied="Copied", data="Show the data",
               WARNING="Warning", NOTE="Note", IMPORTANT="Important", TIP="Tip", parl="16 parliaments",
               call="The call",
               open_page="Open the full page",
               embed_note="Page written by the tool, without the names of the speakers.",
               names=["Argentina", "Brazil", "Chile", "Colombia", "Costa Rica", "Dominican Republic", "Ecuador",
                      "Spain", "Guatemala", "Mexico", "Panama", "Peru", "Portugal", "Paraguay", "El Salvador",
                      "Uruguay"],
               foot="Results obtained with parlaibero-mcp {mcp} on {versions} of the ParlaIbero datasets in Harvard "
                    "Dataverse (CC BY 4.0); the script casos.py reproduces them. The examples name no one: quotations "
                    "leave out the speaker and word lists leave out proper names, whose list is kept outside the "
                    "repository.",
               repo="Code on GitHub", pypi="parlaibero-mcp on PyPI", readme="Technical documentation",
               md="This page in Markdown", filter="Search a tool or a parameter"),
}
ICONS = {
    "WARNING": '<path d="M10 2.5 18.5 17h-17z"/><path d="M10 8v4"/><circle cx="10" cy="14.5" r=".6"/>',
    "NOTE": '<circle cx="10" cy="10" r="8"/><path d="M10 9v5"/><circle cx="10" cy="6.2" r=".6"/>',
    "IMPORTANT": '<path d="M3 3.5h14v10H8l-4 3v-3H3z"/><path d="M10 6v4"/><circle cx="10" cy="12" r=".6"/>',
    "TIP": '<path d="M7 15h6M8 18h4"/><path d="M10 2.5a5 5 0 0 0-3 9c.6.5 1 1.2 1 2V14h4v-.5c0-.8.4-1.5 1-2a5 5 0 0 0-3-9z"/>',
}
ASK = r"\*\*(Pide|Ask):\*\*\s*(.*?)\s*\*(El agente usa|The agent uses)\*\s*(.*)$"
ONESHOT = r"\*\*(Pídelo de una vez|Ask for it all at once):\*\*\s*(.*)$"
RESULT_KINDS = ("code", "table", "img")


def versions(lang):
    v = FACTS["versions"]
    main = max(set(v.values()), key=list(v.values()).count)
    odd = [c for c in COUNTRIES if v[c] != main]
    names = dict(zip(COUNTRIES, UI[lang]["names"]))
    if lang == "es":
        return f"las versiones {main}" + (f" (la {v[odd[0]]} en " + ", ".join(names[c] for c in odd) + ")" if odd else "")
    return f"version {main}" + (f" ({v[odd[0]]} for " + ", ".join(names[c] for c in odd) + ")" if odd else "")


# ---------------------------------------------------------------- parsing
def blocks(lines):
    out, i, n = [], 0, len(lines)
    while i < n:
        line = lines[i]
        s = line.strip()
        if not s or s == "---" or re.match(r"<!-- (table:\S+|/table) -->$", s):
            i += 1
        elif line.startswith("<!--"):
            out.append(("dir", s[4:-3].strip()))
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
        elif re.match(r"#{1,4} ", line):
            level = len(line.split(" ")[0])
            out.append((f"h{level}", line[level + 1:]))
            i += 1
        elif re.match(r"(- |\d+\. )", line):
            buf = []
            while i < n and lines[i].strip() and not lines[i].startswith(("<!--", ">", "|", "```", "#")):
                buf.append(lines[i])
                i += 1
            out.append(("list", "\n".join(buf)))
        else:
            buf = [line]
            i += 1
            # as in CommonMark, only a list that starts at 1 can interrupt a paragraph ("20. " can open a wrapped line)
            while i < n and lines[i].strip() and not re.match(r"(```|>|\||!\[|#|- |1\. |<!--)", lines[i]):
                buf.append(lines[i])
                i += 1
            out.append(("p", "\n".join(buf)))
    return out


def quote(buf):
    m = re.match(r"\[!(\w+)\]", buf[0])
    if m:
        return ("alert", m[1], "\n".join(buf[1:]))
    text = " ".join(x.strip() for x in buf if x.strip())
    m = re.match(ASK, text)
    if m:
        return ("ask", *m.groups())
    m = re.match(ONESHOT, text)
    if m:
        return ("oneshot", m[1], m[2])
    return ("quote", text)


def fix_links(text, src):
    """Links between the Markdown pages become links between the site's pages; links to other repository files go to
    GitHub; images keep their path, resolved later."""
    here = (DOCS / src).parent
    pages = {(DOCS / p[i]).resolve(): p[0] for p in PAGES for i in (1, 2)}
    lang = "en" if src.startswith("en/") or src.endswith(".en.md") else "es"

    def section(anchor):      # GitHub's anchor of "## 2. Title" is "2-title"; the site's is "es-2"
        m = re.match(r"(\d+)-", anchor)
        return f"{lang}-{m[1]}" if m else anchor

    def repl(m):
        label, target = m[1], m[2]
        if target.startswith("#"):
            return f"[{label}](#{section(target[1:])})"
        if target.startswith(("http", "mailto:")):
            return m[0]
        path, _, anchor = target.partition("#")
        full = (here / path).resolve()
        if full in pages:
            return f"[{label}]({pages[full]}.html{'#' + section(anchor) if anchor else ''})"
        try:
            return f"[{label}]({GH}{full.relative_to(ROOT).as_posix()})"
        except ValueError:
            return m[0]
    return re.sub(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)\)", repl, text)


# ---------------------------------------------------------------- rendering
class Page:
    def __init__(self, slug, src, lang):
        self.slug, self.src, self.lang, self.ui = slug, src, lang, UI[lang]

    # -- single blocks
    def pre(self, lang_code, content):
        copy = ""
        if lang_code in ("bash", "json", "sql", "toml"):
            copy = f'<button type="button" class="copy" data-done="{self.ui["copied"]}">{self.ui["copy"]}</button>'
        return f'<div class="pre" data-lang="{lang_code}">{copy}<pre><code>{html.escape(content)}</code></pre></div>'

    @staticmethod
    def table(text):
        return f'<div class="tablewrap">{md.render(text)}</div>'

    def img(self, alt, src):
        full = ((DOCS / self.src).parent / src).resolve()
        rel = full.relative_to(DOCS)
        (SITE / rel.parent).mkdir(parents=True, exist_ok=True)
        shutil.copy(full, SITE / rel)
        return (f'<figure class="viz fig-img"><img src="{rel.as_posix()}" alt="{html.escape(alt)}" loading="lazy">'
                f'<figcaption class="viz-note">{inline(alt)}</figcaption></figure>')

    def viz(self, vid, table):
        spec = json.loads((WEB / "data" / f"{vid}.json").read_text(encoding="utf-8"))[self.lang]
        head = f'<p class="viz-title">{html.escape(spec["title"])}</p>' if spec.get("title") else ""
        if spec.get("sub"):
            head += f'<p class="viz-sub">{html.escape(spec["sub"])}</p>'
        if spec["type"] == "html":               # a table already drawn by datos.py (heat maps)
            body = spec["html"]
        else:
            data = json.dumps(spec, ensure_ascii=False).replace("</", "<\\/")
            body = f'<div class="viz-mount"></div><script type="application/json">{data}</script>'
        details = ""
        if table:
            details = (f'<details class="viz-data"><summary>{self.ui["data"]}</summary>'
                       f'{self.table(table)}</details>')
        note = f'<p class="viz-note">{inline(spec["note"])}</p>' if spec.get("note") else ""
        return (f'<figure class="viz" id="{self.lang}-viz-{vid}"><div class="viz-body">{head}{body}</div>'
                f'{note}{details}</figure>')

    def embed(self, arg):
        path, _, h = arg.partition(" ")
        (SITE / Path(path).parent).mkdir(parents=True, exist_ok=True)
        shutil.copy(WEB / path, SITE / path)
        return (f'<figure class="viz embed"><iframe class="frame-embed" src="{path}" style="height:{int(h or 720)}px" '
                f'loading="lazy" title="{html.escape(Path(path).stem)}"></iframe><div class="embed-bar">'
                f'<span>{self.ui["embed_note"]}</span><a href="{path}" target="_blank" rel="noopener">'
                f'{self.ui["open_page"]} ↗</a></div></figure>')

    def ask(self, b, call_code="", results=(), legend=False):
        _, k_ask, ask, k_tool, tool = b
        tool_html = inline(tool).replace("<code>", '<code class="tool">', 1)
        out = ""
        if results:
            name = re.match(r"`([^`]+)`", tool)
            tag = f"<code>{html.escape(name[1])}</code>" if name else ""
            out = (f'<div class="ex-out"><div class="ex-out-h"><span>{self.ui["result"]}</span>{tag}</div>'
                   f'{"".join(results)}</div>')
        return (f'<div class="ex{" legend" if legend else ""}"><div class="ex-ask"><span class="ex-k">{k_ask}</span>'
                f'<p class="ex-q">{inline(ask)}</p></div><div class="ex-agent"><p class="ex-call">'
                f'<span class="ex-k">{k_tool}</span> {tool_html}</p>{call_code}{out}</div></div>')

    def oneshot(self, b):
        return (f'<div class="oneshot"><span class="ex-k">{b[1]}</span>'
                f'<button type="button" class="copy" data-done="{self.ui["copied"]}">{self.ui["copy"]}</button>'
                f'<p class="ex-q">{inline(b[2])}</p></div>')

    def alert(self, kind, body):
        return (f'<aside class="callout {kind.lower()}"><svg viewBox="0 0 20 20" width="20" height="20" fill="none" '
                f'stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round" '
                f'aria-hidden="true">{ICONS[kind]}</svg><div><span class="callout-k">{self.ui[kind]}</span>'
                f'{md.render(body)}</div></aside>')

    @staticmethod
    def steps(text):
        """A numbered list whose items end in tool names in parentheses becomes a stepped path."""
        items = []
        for it in re.split(r"\n(?=\d+\. )", text):
            it = " ".join(x.strip() for x in re.sub(r"^\d+\.\s*", "", it).split("\n"))
            m = re.match(r"(.*?)\s*\(((?:`[^`]*`(?:,\s*|\s+y\s+|\s+and\s+)?)+)\)\s*$", it)
            if not m:
                return None
            items.append(f'<li><p class="step-q">{inline(m[1])}</p><p class="step-t">{inline(m[2])}</p></li>')
        return f'<ol class="steps">{"".join(items)}</ol>'

    def studies(self):
        cards = json.loads((WEB / "data" / "studies.json").read_text(encoding="utf-8"))[self.lang]
        out = []
        for c in cards:
            spark = ""
            if c.get("spark"):
                pts = c["spark"]
                top = max(v for _, v in pts) or 1
                x0, x1 = pts[0][0], pts[-1][0]
                path = " ".join(f"{'M' if i == 0 else 'L'}{(x - x0) / ((x1 - x0) or 1) * 300:.1f},"
                                f"{50 - v / top * 44:.1f}" for i, (x, v) in enumerate(pts))
                spark = (f'<svg viewBox="0 0 300 54" preserveAspectRatio="none" aria-hidden="true">'
                         f'<path d="{path} L300,54 L0,54 Z" style="fill:var(--accent);opacity:.12"/>'
                         f'<path d="{path}" style="fill:none;stroke:var(--accent);stroke-width:1.6" '
                         f'vector-effect="non-scaling-stroke"/></svg>')
            tools = "".join(f"<code>{t}</code>" for t in c["tools"])
            out.append(f'<a class="study" href="{c["slug"]}.html"><p class="eyebrow">{c["eyebrow"]}</p>'
                       f'<h3>{c["title"]}</h3><p>{c["text"]}</p>{spark}<div class="tools-used">{tools}</div></a>')
        return f'<div class="studies">{"".join(out)}</div>'

    def reference(self):
        data = json.loads((WEB / "data" / "tools.json").read_text(encoding="utf-8"))
        es = self.lang == "es"
        out = [f'<div class="ref-filter"><input type="search" placeholder="{self.ui["filter"]}" '
               f'aria-label="{self.ui["filter"]}"></div><p class="ref-none" hidden>'
               f'{"Ninguna herramienta coincide." if es else "No tool matches."}</p>']
        for group in data["groups"]:
            out.append(f'<h2 class="ref-group" id="{self.lang}-g-{group["id"]}">{html.escape(group[self.lang])}</h2>')
            for t in group["tools"]:
                rows = "".join(f'<tr><td><code>{p["name"]}</code></td><td>{html.escape(p["kind"])}</td>'
                               f'<td>{html.escape(p["description"])}</td></tr>' for p in t["params"])
                params = ""
                if t["params"]:
                    head = ("parámetro", "valor", "qué hace") if es else ("parameter", "value", "what it does")
                    params = (f'<div class="tablewrap"><table class="params"><thead><tr><th>{head[0]}</th>'
                              f'<th>{head[1]}</th><th>{head[2]}</th></tr></thead><tbody>{rows}</tbody></table></div>')
                ex = ""
                if t.get("example"):
                    k_ask, k_tool = ("Pide", "El agente usa") if es else ("Ask", "The agent uses")
                    ex = self.ask(("ask", k_ask, t["example"][self.lang], k_tool, f"`{t['name']}`"))
                used = ""
                if t.get("used_in"):
                    used = ('<p class="tool-used">' + ("Se usa en: " if es else "Used in: ")
                            + ", ".join(f'<a href="{u["page"]}.html#{self.lang}-{u["section"]}">{html.escape(u[self.lang])}</a>'
                                        for u in t["used_in"]) + "</p>")
                out.append(f'<details class="tool-card" id="{self.lang}-tool-{t["name"]}"><summary><code>{t["name"]}'
                           f'</code><span>{html.escape(t["summary"][self.lang])}</span></summary><div class="tool-body">'
                           f'<p class="tool-desc" lang="en"><span class="tool-k">{"Lo que lee el agente" if es else "What the agent reads"}</span>'
                           f'{html.escape(t["description"])}</p>{used}{ex}{params}</div></details>')
        return "".join(out)

    def block(self, b, legend=False):
        kind = b[0]
        if kind == "p":
            return md.render(b[1])
        if kind == "list":
            if re.match(r"\d+\. ", b[1]):
                return self.steps(b[1]) or md.render(b[1])
            return md.render(b[1])
        if kind == "table":
            return self.table(b[1])
        if kind == "code":
            return self.pre(b[1], b[2])
        if kind == "img":
            return self.img(b[1], b[2])
        if kind == "alert":
            return self.alert(b[1], b[2])
        if kind == "ask":
            return self.ask(b, legend=legend)
        if kind == "oneshot":
            return self.oneshot(b)
        if kind == "h4":
            return f"<h4>{inline(b[1])}</h4>"
        if kind == "quote":
            return f"<blockquote>{md.render(b[1])}</blockquote>"
        if kind == "dir":
            if b[1].startswith("embed:"):
                return self.embed(b[1][6:].strip())
            if b[1] == "studies":
                return self.studies()
            if b[1] == "reference":
                return self.reference()
            return ""
        raise ValueError(kind)

    def side_block(self, b):
        if b[0] == "p" and re.fullmatch(r"\*\*[^*]+\*\*", b[1].strip()):
            return f'<p class="side-k">{inline(b[1].strip()[2:-2])}</p>'
        if b[0] == "list" and re.match(r"\d+\. ", b[1]):
            items = [re.sub(r"^\d+\.\s*", "", x) for x in re.split(r"\n(?=\d+\. )", b[1])]
            return '<ol class="chain">' + "".join(f"<li><span>{inline(x)}</span></li>" for x in items) + "</ol>"
        return self.block(b, legend=True)

    # -- a whole page
    def render(self):
        text = fix_links((DOCS / self.src).read_text(encoding="utf-8"), self.src)
        bl = blocks(text.split("\n"))
        title, eyebrow, lede, side = "", "", "", None
        i = 0
        while i < len(bl) and bl[i][0] != "h2" and bl[i] != ("dir", "reference"):   # masthead: all before the first section
            b = bl[i]
            if b[0] == "h1":
                title = b[1]
            elif b[0] == "dir" and b[1].startswith("eyebrow:"):
                eyebrow = b[1].split(":", 1)[1].strip()
            elif b[0] == "dir" and b[1] == "side":
                side = ""
            elif b[0] == "p" and b[1].startswith("*[") and b[1].rstrip().endswith("*"):
                pass                                     # links to the other language and the index: the bar has them
            elif side is not None:
                side += self.side_block(b)
            else:
                lede += self.block(b)
            i += 1
        body, toc, open_section = [], [], False
        bl = bl[i:]
        i = 0
        while i < len(bl):
            b = bl[i]
            if b[0] == "h2":
                m = re.match(r"(\d+)\. (.*)", b[1])
                num, name = (m[1], m[2]) if m else (None, b[1])
                hid = f"{self.lang}-{num or re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:40]}"
                body.append(("</section>" if open_section else "") + f'<section class="sec"><h2 id="{hid}">'
                            + (f'<span class="num">§ {num}</span>' if num else "") + f"<span>{inline(name)}</span></h2>")
                open_section = True
                toc.append((hid, num or "·", name))
            elif b[0] == "h3":
                m = re.match(r"(\d+\.\d+) (.*)", b[1])
                num, name = (m[1], m[2]) if m else ("", b[1])
                hid = f"{self.lang}-" + (num.replace(".", "-") if m else re.sub(r"[^a-z0-9]+", "-", name.lower())[:40])
                body.append(f'<h3 id="{hid}">' + (f'<span class="num">{num}</span>' if m else "") + f"{inline(name)}</h3>")
            elif b[0] == "ask":
                j, call_code, res = i + 1, "", []
                if j < len(bl) and bl[j][0] == "code" and b[4].rstrip().endswith(":"):
                    call_code = self.pre(bl[j][1], bl[j][2])      # the query is part of the call, not of the result
                    j += 1
                while j < len(bl) and (bl[j][0] in RESULT_KINDS or (bl[j][0] == "dir" and bl[j][1].startswith(("viz:", "embed:")))):
                    r = bl[j]
                    if r[0] == "dir" and r[1].startswith("viz:"):
                        table = bl[j + 1][1] if j + 1 < len(bl) and bl[j + 1][0] == "table" else None
                        res.append(self.viz(r[1][4:].strip(), table))
                        j += 2 if table else 1
                        continue
                    res.append(self.block(r))
                    j += 1
                body.append(self.ask(b, call_code, res))
                i = j
                continue
            elif b[0] == "dir" and b[1].startswith("viz:"):
                table = bl[i + 1][1] if i + 1 < len(bl) and bl[i + 1][0] == "table" else None
                body.append(self.viz(b[1][4:].strip(), table))
                i += 2 if table else 1
                continue
            elif b[0] == "dir" and b[1] == "reference":     # the groups of tools go into the contents
                body.append(self.block(b))
                groups = json.loads((WEB / "data" / "tools.json").read_text(encoding="utf-8"))["groups"]
                toc += [(f"{self.lang}-g-{g['id']}", str(k), g[self.lang]) for k, g in enumerate(groups, 1)]
            else:
                body.append(self.block(b))
            i += 1
        if open_section:
            body.append("</section>")
        ui = self.ui
        toc_html = "".join(f'<li><a href="#{hid}"><span class="n">{num}</span><span>{inline(name)}</span></a></li>'
                           for hid, num, name in toc)
        parl = ""
        if self.slug == "index":
            parl = (f'<div class="parl"><span class="parl-k">{ui["parl"]}</span>'
                    + "".join(f'<abbr title="{n}">{c}</abbr>' for c, n in zip(COUNTRIES, ui["names"])) + "</div>")
        side_html = f'<aside class="side-card">{side}</aside>' if side else ""
        foot = ui["foot"].format(mcp=FACTS["mcp_version"], versions=versions(self.lang))
        hidden = " hidden" if self.lang == "en" else ""
        return title, f"""<div class="lang" id="lang-{self.lang}" lang="{self.lang}"{hidden}>
<header class="mast"><div class="wrap mast-grid{'' if side_html else ' single'}">
<div class="mast-text">{f'<p class="eyebrow">{eyebrow}</p>' if eyebrow else ''}<h1>{inline(title)}</h1>
<div class="lede">{lede}</div>{parl}</div>{side_html}
</div></header>
<div class="wrap shell">
<details class="toc" open><summary>{ui["contents"]}</summary><ol>{toc_html}</ol></details>
<main class="doc" id="{self.lang}-main">{"".join(body)}</main>
</div>
<footer class="foot"><div class="wrap"><p>{foot}</p><p class="foot-links">
<a href="https://github.com/rodrodr/parlaibero-tools">{ui["repo"]}</a>
<a href="https://pypi.org/project/parlaibero-mcp/">{ui["pypi"]}</a>
<a href="{GH}mcp/README.md">{ui["readme"]}</a>
<a href="{GH}docs/tutorial/{self.src}">{ui["md"]}</a></p></div></footer>
</div>"""


KEEP = re.compile(r"(<pre[\s\S]*?</pre>|<code[\s\S]*?</code>|<script[\s\S]*?</script>|<[^>]+>)")


def nbsp(body):
    """'25 %' and '§ 2' never break across lines; code, scripts and tags are left alone."""
    parts = KEEP.split(body)
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r"(?<=\d) (?=%)", "\u00a0", parts[i]).replace("§ ", "§\u00a0")
    return "".join(parts)


def page_html(slug, titles, es, en, pages):
    links = []
    for p in pages:
        current = ' aria-current="page"' if p[0] == slug else ""
        links.append(f'<a href="{p[0]}.html"{current}><span data-l="es">{p[3]}</span><span data-l="en">{p[4]}</span></a>')
    full = {}
    for l in ("es", "en"):
        plain = re.sub(r"[*`]", "", titles[l])
        full[l] = plain if slug == "index" else f"{plain} · ParlaIbero"
    title = full["es"]
    return f"""<!doctype html>
<html lang="es" data-title-es="{html.escape(full['es'])}" data-title-en="{html.escape(full['en'])}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{html.escape(title)}</title>
<meta name="description" content="Tutorial de parlaibero-mcp: cuatro estudios con los plenos de 16 parlamentos iberoamericanos, hechos desde un agente. A tutorial for parlaibero-mcp.">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%2316694e'/%3E%3Ctext x='16' y='23' font-size='20' text-anchor='middle' fill='white' font-family='Georgia'%3E%C2%B6%3C/text%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Newsreader:opsz,wght@6..72,400;6..72,500&family=Public+Sans:wght@400;500;600;700&display=swap">
<link rel="stylesheet" href="assets/site.css">
</head>
<body>
<a class="skip" href="#es-main">Ir al contenido · Skip to content</a>
<header class="bar"><div class="wrap">
  <a class="brand" href="index.html"><span class="brand-mark" aria-hidden="true">¶</span><span class="brand-text">ParlaIbero</span></a>
  <nav class="nav" aria-label="Tutorial">{"".join(links)}</nav>
  <div class="switch" role="group" aria-label="Idioma · Language">
    <button type="button" data-set-lang="es" aria-pressed="true">ES</button>
    <button type="button" data-set-lang="en" aria-pressed="false">EN</button>
  </div>
</div></header>
{es}
{en}
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
<script src="assets/site.js"></script>
</body>
</html>
"""


def main():
    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / "assets").mkdir(parents=True)
    for f in (WEB / "assets").iterdir():
        shutil.copy(f, SITE / "assets" / f.name)
    (SITE / ".nojekyll").write_text("")
    pages = [p for p in PAGES if (DOCS / p[1]).exists()]
    for slug, es_src, en_src, *_ in pages:
        if not (DOCS / en_src).exists():
            print(f"  ! {en_src} missing: the Spanish page stands in")
            en_src = es_src
        t_es, es = Page(slug, es_src, "es").render()
        t_en, en = Page(slug, en_src, "en").render()
        (SITE / f"{slug}.html").write_text(page_html(slug, {"es": t_es, "en": t_en}, nbsp(es), nbsp(en), pages),
                                           encoding="utf-8")
        print(f"site/{slug}.html")


if __name__ == "__main__":
    main()
