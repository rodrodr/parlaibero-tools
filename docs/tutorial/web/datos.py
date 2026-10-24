"""Turns the results of casos.py into what the tutorial shows: the data of each chart (web/data/ID.json, one spec per
language), the tables of the Markdown pages (rewritten between <!-- table:ID --> and <!-- /table -->), the figures the
tool draws itself (img/) and the network pages without the speakers' names (web/redes/).

    uv run --project mcp python docs/tutorial/web/datos.py CASOS_OUT

CASOS_OUT is the folder given to casos.py. Every number on the pages comes from here: the prose quotes these tables.
"""
import asyncio
import json
import math
import re
import shutil
import sys
from collections import defaultdict
from datetime import date
from importlib.metadata import version
from pathlib import Path

from parlaibero_mcp import network_html, server

CASOS = Path(sys.argv[1]).expanduser().resolve()
WEB = Path(__file__).resolve().parent
DOCS = WEB.parent
DATA = WEB / "data"
DATA.mkdir(exist_ok=True)
LANGS = ("es", "en")
ALL = ["AR", "BR", "CL", "CO", "CR", "DO", "EC", "ES", "GT", "MX", "PA", "PE", "PT", "PY", "SV", "UY"]
NAME = {
    "es": dict(AR="Argentina", BR="Brasil", CL="Chile", CO="Colombia", CR="Costa Rica", DO="Rep. Dominicana",
               EC="Ecuador", ES="España", GT="Guatemala", MX="México", PA="Panamá", PE="Perú", PT="Portugal",
               PY="Paraguay", SV="El Salvador", UY="Uruguay"),
    "en": dict(AR="Argentina", BR="Brazil", CL="Chile", CO="Colombia", CR="Costa Rica", DO="Dominican Rep.",
               EC="Ecuador", ES="Spain", GT="Guatemala", MX="Mexico", PA="Panama", PE="Peru", PT="Portugal",
               PY="Paraguay", SV="El Salvador", UY="Uruguay"),
}
PAGES = {"feminicidio": ("es/feminicidio.md", "en/feminicidio.md"), "pandemia": ("es/pandemia.md", "en/pandemia.md"),
         "voz": ("es/voz.md", "en/voz.md"), "marcos": ("es/marcos.md", "en/marcos.md"),
         "bibliotecas": ("es/bibliotecas.md", "en/bibliotecas.md"), "index": ("TUTORIAL.md", "TUTORIAL.en.md")}


def J(key):
    d = json.loads((CASOS / "json" / f"{key}.json").read_text(encoding="utf-8"))
    if d["error"]:
        raise SystemExit(f"{key} failed in casos.py: {str(d['result'])[:200]}")
    return d["result"]


def ARGS(key):
    return json.loads((CASOS / "json" / f"{key}.json").read_text(encoding="utf-8"))["arguments"]


def num(v, d=1, lang="es"):
    """1234.5 -> '1.234,5' (es) or '1,234.5' (en); thousands are grouped from 1,000 up."""
    if v is None:
        return "—"
    s = f"{v:,.{d}f}"
    return s.replace(",", "\0").replace(".", ",").replace("\0", ".") if lang == "es" else s


def signed(v, d=2, lang="es"):
    """-0.27 -> '−0,27', 0.62 -> '+0,62': a typographic minus and an explicit plus."""
    return ("+" if v > 0 else "−" if v < 0 else "") + num(abs(v), d, lang)


def pct(v, d=1, lang="es"):
    return "—" if v is None else num(100 * v, d, lang) + (" %" if lang == "es" else "%")


def md_table(head, rows, right=()):
    """A Markdown table; columns whose index is in `right` are right-aligned."""
    out = ["| " + " | ".join(head) + " |",
           "|" + "|".join("---:" if i in right else "---" for i in range(len(head))) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


TABLES = defaultdict(dict)        # page -> {(id, lang): markdown}
SPECS = {}


def table(page, vid, by_lang):
    for lang in LANGS:
        TABLES[page][(vid, lang)] = by_lang[lang]


def spec(vid, by_lang):
    SPECS[vid] = by_lang


# Names of people never go on the pages (docs/PLAN_redes.md §6): the exclusion list the word network was built with,
# plus the names that other word lists bring in, kept with it in the local, unversioned nombres.local.json.
LOCAL = DOCS / "nombres.local.json"
if not LOCAL.exists():
    raise SystemExit(f"{LOCAL} is missing: it lists the personal names the pages must not show")
PEOPLE = ({w for w in ARGS("D2_words")["exclude"] for w in [w] + w.split()}
          | set(json.loads(LOCAL.read_text(encoding="utf-8"))["also_hide"]))


def words(items, n=12, key="z"):
    return [w for w in items if w["word"].lower() not in PEOPLE][:n]


# ============================================================ A. feminicidio
def feminicidio():
    a1 = J("A1_counter")["terms"][0]
    series = {s["label"].split("(")[-1].rstrip(")"): s["points"] for s in J("A2_ngram")["series"]}
    starts = {c["iso"]: c["downloaded"]["date_min"] for c in J("Z1_list")["countries"]}
    top = {c: J(f"A4_sessions_{c}")["rows"][0] for c in ALL}
    first = {c: a1["by_country"][c]["first_use"] for c in ALL}
    order = sorted(ALL, key=lambda c: first[c]["date"])

    def raw_peak(c):     # the year with the most uses per million words, unsmoothed
        pts = [p for p in series[c] if p["words"] and not p.get("low_base") and p["year"] <= 2025]
        best = max(pts, key=lambda p: p["count"] / p["words"])
        return best["year"], 1e6 * best["count"] / best["words"], best["count"]

    late = {c for c in ALL if starts[c][:4] >= "2015"}      # El Salvador's corpus starts in 2018
    for lang in LANGS:
        nm = NAME[lang]
        rows = []
        for c in order:
            fu = first[c]
            y, r, n = raw_peak(c)
            t = top[c]
            rows.append([nm[c], fu["date"], fu.get("party") or ("(no vinculado)" if lang == "es" else "(not linked)"),
                         starts[c][:4], num(a1["by_country"][c]["occurrences"], 0, lang), f"{y} ({num(r, 1, lang)})",
                         f"{t['session'].split()[1]} ({num(t['occurrences'], 0, lang)})"])
        head = (["País", "Primer uso", "Partido", "Corpus desde", "Usos", "Año pico (por millón)",
                 "Sesión con más usos (usos)"] if lang == "es" else
                ["Country", "First use", "Party", "Corpus from", "Uses", "Peak year (per million)",
                 "Session with most uses (uses)"])
        TABLES["feminicidio"][("fem_primeros", lang)] = md_table(head, rows, right=(4,))
    spec("fem_primeros", {lang: {
        "type": "timeline",
        "title": "Primer uso de «feminicidio», «femicidio» o «feminicídio» en cada corpus" if lang == "es" else
                 "First use of «feminicidio», «femicidio» or «feminicídio» in each corpus",
        "sub": "El tamaño del punto es el total de usos. Gris: el corpus empieza después de 2015, así que el primer uso "
               "del corpus no es el del país." if lang == "es" else
               "Dot size is the total number of uses. Grey: the corpus starts after 2015, so the corpus's first use is "
               "not the country's.",
        "x_domain": ["2000-01-01", "2026-01-01"], "size": max(a1["by_country"][c]["occurrences"] for c in ALL),
        "aria": "Fecha del primer uso por país" if lang == "es" else "Date of first use by country",
        "rows": [{"label": NAME[lang][c], "date": first[c]["date"], "value": a1["by_country"][c]["occurrences"],
                  "color": "c0" if c in late else "c1",
                  "note": (("corpus desde " if lang == "es" else "corpus from ") + starts[c][:4]) if c in late else None,
                  "tip": f"<b>{NAME[lang][c]} · {first[c]['date']}</b><br>"
                         f"{first[c].get('party') or ('orador no vinculado' if lang == 'es' else 'speaker not linked')}"
                         f"<br>{num(a1['by_country'][c]['occurrences'], 0, lang)} "
                         f"{'usos en total' if lang == 'es' else 'uses in all'}"} for c in order]} for lang in LANGS})

    # small multiples, one per country, in the order of first use
    spec("fem_paneles", {lang: {
        "type": "multiples", "x_domain": [2000, 2025], "y_shared": True, "digits": 1, "y_grid": [50, 100],
        "unit": "por millón" if lang == "es" else "per million",
        "extra": "{v} usos ese año" if lang == "es" else "{v} uses that year",
        "title": "Usos por millón de palabras, año a año (media móvil de tres años)" if lang == "es" else
                 "Uses per million words, year by year (three-year moving average)",
        "sub": "Misma escala en todos los paneles. El punto en la base marca el año de la sesión con más usos." if lang == "es"
               else "Same scale in every panel. The dot on the baseline marks the year of the session with most uses.",
        "aria": "frecuencia anual" if lang == "es" else "yearly frequency",
        "panels": [{"label": NAME[lang][c],
                    "sub": ("1.er uso " if lang == "es" else "first use ") + first[c]["date"][:4],
                    "points": [[p["year"], None if p.get("low_base") or p["value"] is None else round(p["value"], 2),
                                p["count"]] for p in series[c] if 2000 <= p["year"] <= 2025],
                    "marks": [{"x": int(top[c]["session"].split()[1][:4]),
                               "label": ("sesión con más usos: " if lang == "es" else "session with most uses: ")
                                        + top[c]["session"].split()[1]}]} for c in order]} for lang in LANGS})
    for lang in LANGS:
        rows = []
        for c in order:
            pts = {p["year"]: p for p in series[c]}
            rows.append([NAME[lang][c]] + [("—" if pts[y].get("low_base") or pts[y]["value"] is None
                                            else num(pts[y]["value"], 1, lang)) for y in (2005, 2010, 2015, 2020, 2025)])
        TABLES["feminicidio"][("fem_paneles", lang)] = md_table(
            ["País" if lang == "es" else "Country", "2005", "2010", "2015", "2020", "2025"], rows, right=(1, 2, 3, 4, 5))

    # the peak sessions read with get_session: what was on the floor (paraphrased from the session's turns)
    debated = {
        "GT0030024": ("Ley contra el Femicidio y otras Formas de Violencia contra la Mujer, aprobada en la sesión",
                      "The Law against Femicide and other Forms of Violence against Women, passed in the sitting"),
        "PE0060031": ("Proyecto del Ejecutivo, con urgencia, que modifica el artículo 107 del Código Penal; se le "
                      "acumulan otros proyectos de congresistas sobre feminicidio",
                      "An urgent Executive bill amending article 107 of the Penal Code; members' bills on femicide are "
                      "merged into it"),
        "AR0190005": ("Reforma del Código Penal sobre el femicidio, al final de una sesión con otros proyectos",
                      "A Penal Code reform on femicide, at the end of a sitting with other bills"),
        "PA0040593": ("«Proyecto de Femicidio», de 75 artículos, junto a otros puntos del orden del día",
                      "The 'Femicide Bill', 75 articles long, alongside other items on the agenda"),
        "UY0070168": ("Proyecto que hace del femicidio un agravante muy especial del homicidio",
                      "A bill that makes femicide a very special aggravating circumstance of homicide"),
    }
    for lang in LANGS:
        rows = []
        for sid, txt in debated.items():
            c = sid[:2]
            s = J(f"A5_session_{sid}")["session"]
            t = next(r for r in J(f"A4_sessions_{c}")["rows"] if r["session"].endswith(sid))
            rows.append([NAME[lang][c], s["date"], txt[0 if lang == "es" else 1], num(t["occurrences"], 0, lang),
                         num(t["interventions_using"], 0, lang), num(s["turns"], 0, lang)])
        head = (["País", "Sesión", "Qué se debatía", "Usos", "Intervenciones que la usan", "Turnos de la sesión"]
                if lang == "es" else
                ["Country", "Sitting", "What was debated", "Uses", "Interventions using it", "Turns in the sitting"])
        TABLES["feminicidio"][("fem_sesiones", lang)] = md_table(head, rows, right=(3, 4, 5))

    # who says it: women and men, per million words since 2012 (unigrams)
    sx = defaultdict(dict)
    for r in J("A6_sex_sql")["rows"]:
        sx[r["country"]][r["sex"]] = r
    ratio = {c: sx[c]["F"]["per_million"] / sx[c]["M"]["per_million"] for c in ALL}
    by_ratio = sorted(ALL, key=lambda c: -ratio[c])
    spec("fem_sexo", {lang: {
        "type": "dumbbell", "log": True, "domain": [0.1, 120], "ticks": [0.1, 1, 10, 100],
        "a_color": "c0", "b_color": "c2", "ratio_label": "×", "ratio_digits": 1,
        "title": "Usos por millón de palabras de diputadas y diputados, desde 2012" if lang == "es" else
                 "Uses per million words by women and men deputies, since 2012",
        "sub": "Escala logarítmica. A la derecha, cuántas veces más la usan ellas." if lang == "es" else
               "Log scale. On the right, how many times more often women use it.",
        "legend": [{"label": "Diputadas" if lang == "es" else "Women", "color": "c2", "dot": True},
                   {"label": "Diputados" if lang == "es" else "Men", "color": "c0", "dot": True, "hollow": True}],
        "aria": "Frecuencia por sexo y país" if lang == "es" else "Frequency by sex and country",
        "rows": [{"label": NAME[lang][c], "a": sx[c]["M"]["per_million"], "b": sx[c]["F"]["per_million"],
                  "ratio": ratio[c],
                  "tip": f"<b>{NAME[lang][c]}</b><br>{'diputadas' if lang == 'es' else 'women'}: "
                         f"{num(sx[c]['F']['per_million'], 2, lang)} ({num(sx[c]['F']['uses'], 0, lang)} "
                         f"{'usos' if lang == 'es' else 'uses'})<br>{'diputados' if lang == 'es' else 'men'}: "
                         f"{num(sx[c]['M']['per_million'], 2, lang)} ({num(sx[c]['M']['uses'], 0, lang)} "
                         f"{'usos' if lang == 'es' else 'uses'})"} for c in by_ratio]} for lang in LANGS})
    for lang in LANGS:
        rows = [[NAME[lang][c], num(sx[c]["F"]["uses"], 0, lang), num(sx[c]["F"]["per_million"], 2, lang),
                 num(sx[c]["M"]["uses"], 0, lang), num(sx[c]["M"]["per_million"], 2, lang), num(ratio[c], 1, lang)]
                for c in by_ratio]
        head = (["País", "Usos (diputadas)", "Por millón", "Usos (diputados)", "Por millón", "Razón"] if lang == "es"
                else ["Country", "Uses (women)", "Per million", "Uses (men)", "Per million", "Ratio"])
        TABLES["feminicidio"][("fem_sexo", lang)] = md_table(head, rows, right=(1, 2, 3, 4, 5))
    bs = a1["by_sex"]
    for lang in LANGS:
        TABLES["feminicidio"][("fem_sexo_total", lang)] = md_table(
            ["", "Usos" if lang == "es" else "Uses", "Por millón de palabras" if lang == "es" else "Per million words"],
            [[{"F": "Diputadas", "M": "Diputados", "(unlinked)": "Oradores no vinculados"}[k] if lang == "es" else
              {"F": "Women deputies", "M": "Men deputies", "(unlinked)": "Speakers not linked"}[k],
              num(v["occurrences"], 0, lang), num(v["per_million_words"], 2, lang)] for k, v in bs.items()], right=(1, 2))

    # Spain and Portugal: the words they use instead
    lab = {"violencia de género+violência de género": ("género", "gender"),
           "violência doméstica+violencia doméstica": ("doméstica", "domestic"),
           "feminicidio+feminicídio": ("feminicidio", "femicide")}
    ib = J("A7_iberia")["series"]
    colors = {("ES", 0): "c1", ("ES", 1): "c3", ("PT", 0): "c2", ("PT", 1): "c4"}
    keep = []
    for s in ib:
        term, c = s["label"].rsplit(" (", 1)
        c = c.rstrip(")")
        k = list(lab).index(term)
        if k < 2:
            keep.append((c, k, term, s["points"]))
    spec("fem_iberia", {lang: {
        "type": "lines", "x_domain": [1996, 2025], "digits": 1, "height": 300,
        "title": "«Violencia de género» y «violencia doméstica» en España y Portugal, por millón de palabras" if lang == "es"
                 else "'Gender violence' and 'domestic violence' in Spain and Portugal, per million words",
        "sub": "Media móvil de tres años. «Feminicidio» no llega a 1,5 por millón en ninguno de los dos." if lang == "es"
               else "Three-year moving average. 'Femicide' stays below 1.5 per million in both.",
        "aria": "Series anuales" if lang == "es" else "Yearly series",
        "series": [{"label": f"{c} · {lab[term][0 if lang == 'es' else 1]}", "color": colors[(c, k)],
                    "points": [[p["year"], None if p["value"] is None else round(p["value"], 2)] for p in pts
                               if 1996 <= p["year"] <= 2025]} for c, k, term, pts in keep]} for lang in LANGS})
    for lang in LANGS:
        years = (1998, 2002, 2006, 2010, 2014, 2018, 2022, 2025)
        rows = []
        for c, k, term, pts in keep:
            v = {p["year"]: p["value"] for p in pts}
            rows.append([f"{c} · {lab[term][0 if lang == 'es' else 1]}"] + [num(v.get(y), 1, lang) for y in years])
        TABLES["feminicidio"][("fem_iberia", lang)] = md_table(["Serie" if lang == "es" else "Series", *map(str, years)],
                                                               rows, right=tuple(range(1, 9)))

    # Mexico: what goes with the word, before 2012 and after 2015
    early, late_ = J("A8_colloc_mx_early"), J("A8_colloc_mx_late")
    spec("fem_colocaciones", {lang: {
        "type": "diverging", "independent": True, "value_label": "G²",
        "title": "Palabras que acompañan a «feminicidio» en México (ventana de cinco palabras a cada lado)" if lang == "es"
                 else "Words around «feminicidio» in Mexico (a window of five words on each side)",
        "sub": "Longitud: log-verosimilitud (G²), escalada dentro de cada periodo." if lang == "es" else
               "Length: log-likelihood (G²), scaled within each period.",
        "aria": "Colocaciones por periodo" if lang == "es" else "Collocations by period",
        "left": {"title": (f"hasta 2011 · {num(early['total_matching_interventions'], 0, lang)} intervenciones"
                           if lang == "es" else f"to 2011 · {num(early['total_matching_interventions'], 0, lang)} interventions"),
                 "color": "c7", "items": [[w["word"], w["log_likelihood"],
                                           f"{w['near']} {'cerca' if lang == 'es' else 'near'}"] for w in words(early["collocates"], 15)]},
        "right": {"title": (f"desde 2016 · {num(late_['total_matching_interventions'], 0, lang)} intervenciones"
                            if lang == "es" else f"from 2016 · {num(late_['total_matching_interventions'], 0, lang)} interventions"),
                  "color": "c3", "items": [[w["word"], w["log_likelihood"],
                                            f"{w['near']} {'cerca' if lang == 'es' else 'near'}"] for w in words(late_["collocates"], 15)]},
    } for lang in LANGS})
    for lang in LANGS:
        e, l_ = words(early["collocates"], 15), words(late_["collocates"], 15)
        rows = [[i + 1, e[i]["word"] if i < len(e) else "", num(e[i]["log_likelihood"], 0, lang) if i < len(e) else "",
                 l_[i]["word"] if i < len(l_) else "", num(l_[i]["log_likelihood"], 0, lang) if i < len(l_) else ""]
                for i in range(max(len(e), len(l_)))]
        TABLES["feminicidio"][("fem_colocaciones", lang)] = md_table(
            ["", "Hasta 2011", "G²", "Desde 2016", "G²"] if lang == "es" else ["", "To 2011", "G²", "From 2016", "G²"],
            rows, right=(0, 2, 4))
    for lang in ("es", "en"):
        shutil.copy(CASOS / "img" / f"feminicidio_{lang}.svg", DOCS / "img" / f"feminicidio_{lang}.svg")
    totals = {k: a1[k] for k in ("occurrences", "interventions", "sessions", "speakers", "linked_deputies")}
    # a series for the card on the home page: all uses per year, summed over the sixteen chambers
    spark = defaultdict(int)
    for c in ALL:
        for p in series[c]:
            if 2000 <= p["year"] <= 2025:
                spark[p["year"]] += p["count"]
    return totals, sorted(spark.items())


def es_en(lang, es, en):
    return es if lang == "es" else en


def contrast(key, a, b, ca, cb, n=12):
    """The two sides of a distinctive_words result for a diverging chart, without personal names."""
    r = J(key)
    return {"left": {"title": a, "color": ca, "items": [[w["word"], round(w["z"], 1)] for w in words(r["distinctive_of_a"], n)]},
            "right": {"title": b, "color": cb, "items": [[w["word"], round(abs(w["z"]), 1)] for w in words(r["distinctive_of_b"], n)]}}


def contrast_table(key, a, b, lang, n=15):
    r = J(key)
    A, B = words(r["distinctive_of_a"], n), words(r["distinctive_of_b"], n)
    return md_table(["", a, "z", b, "z"], [[i + 1, A[i]["word"], num(A[i]["z"], 1, lang), B[i]["word"],
                                            num(abs(B[i]["z"]), 1, lang)] for i in range(min(len(A), len(B)))],
                    right=(0, 2, 4))


# ============================================================ B. the pandemic
def pandemia():
    b1 = J("B1_counter")["terms"][0]["by_country"]
    sit = {r["country"]: r for r in J("B3b_sittings")["rows"]}
    # the first uses that reading (kwic) showed to be something else; B2b reads on past them
    wrong = {"EC": ("B2_kwic_EC", "B2b_kwic_EC",
                    "el nombre de una organización que empieza por «Covid», en listas de oficios leídas en el pleno "
                    "(también el 2019-10-24)",
                    "the name of an organisation that begins with 'Covid', in lists of letters read into the record "
                    "(again on 2019-10-24)"),
             "SV": ("B2_kwic_SV", None, "una marca de material quirúrgico («Covidien») en una lista de compras",
                    "a brand of surgical supplies ('Covidien') in a purchase list"),
             "GT": ("B2_kwic_GT", "B2b_kwic_GT",
                    "una sesión fechada el 21 de enero de 2020 que habla de «COVID-19» en pasado: la fecha está mal",
                    "a sitting dated 21 January 2020 that speaks of 'COVID-19' in the past tense: the date is wrong")}
    first = {}
    for c in ALL:
        fu = b1[c]["first_use"]
        first[c] = {"date": fu["date"], "party": fu.get("party")}
        if c in wrong:
            k1, k2, *_ = wrong[c]
            bad = J(k1)["lines"][0]["date"]
            good = J(k2)["lines"][0] if k2 else next(l for l in J(k1)["lines"] if l["date"] != bad)
            first[c] = {"date": good["date"], "party": good.get("party"), "wrong": bad}
    order = sorted(ALL, key=lambda c: first[c]["date"])
    x0 = "2019-06-01"

    def gap(c):          # more than three weeks without sittings around the declaration
        a, b = sit[c]["last_before"] or x0, sit[c]["first_after"]
        return [a, b] if (date.fromisoformat(b) - date.fromisoformat(a)).days > 21 else None
    for lang in LANGS:
        rows = []
        for c in order:
            f = first[c]
            note = (es_en(lang, f"falso positivo el {f['wrong']}: ", f"false positive on {f['wrong']}: ")
                    + wrong[c][2 if lang == "es" else 3]) if c in wrong else ""
            rows.append([NAME[lang][c], f["date"], f["party"] or es_en(lang, "(no vinculado)", "(not linked)"),
                         sit[c]["last_before"] or es_en(lang, "(corpus vacío)", "(corpus empty)"), sit[c]["first_after"],
                         num(sit[c]["sessions_120_days"], 0, lang), num(b1[c]["occurrences"], 0, lang), note])
        TABLES["pandemia"][("pan_primeros", lang)] = md_table(
            es_en(lang, ["País", "Primer uso real", "Partido", "Última sesión antes del 11-mar", "Primera después",
                         "Sesiones en 120 días", "Usos hasta 2025", "Lo que se corrigió"],
                  ["Country", "First genuine use", "Party", "Last sitting before 11 Mar", "First after",
                   "Sittings in 120 days", "Uses up to 2025", "What was corrected"]), rows, right=(5, 6))
    spec("pan_primeros", {lang: {
        "type": "timeline", "x_domain": [x0, "2020-10-01"], "months": es_en(
            lang, ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"],
            ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]),
        "ref_date": "2020-03-11", "ref_label": es_en(lang, "11-mar: la OMS declara la pandemia", "11 Mar: WHO declares the pandemic"),
        "size": max(b1[c]["occurrences"] for c in ALL),
        "title": es_en(lang, "Primer uso de «coronavirus» o «covid» en cada pleno",
                       "First use of 'coronavirus' or 'covid' on each floor"),
        "sub": es_en(lang, "Círculo hueco: el primer uso que da term_counter y que la lectura desmiente. Banda gris: semanas sin "
                           "sesiones alrededor de la declaración. El tamaño del punto es el total de usos hasta 2025.",
                     "Hollow circle: the first use term_counter gives, which reading disproves. Grey band: weeks without "
                     "sittings around the declaration. Dot size is the total number of uses up to 2025."),
        "aria": es_en(lang, "Fecha del primer uso por país", "Date of first use by country"),
        "rows": [{"label": NAME[lang][c], "date": first[c]["date"], "value": b1[c]["occurrences"], "color": "c1",
                  "wrong": first[c].get("wrong"),
                  "wrong_tip": (f"<b>{NAME[lang][c]} · {first[c]['wrong']}</b><br>" + wrong[c][2 if lang == "es" else 3])
                               if c in wrong else None,
                  "gap": gap(c),
                  "gap_tip": (f"<b>{NAME[lang][c]}</b><br>" + (
                      es_en(lang, "el corpus no tiene sesiones hasta el ", "the corpus has no sittings until ") + sit[c]["first_after"]
                      if not sit[c]["last_before"] else
                      es_en(lang, "sin sesiones del ", "no sittings from ") + sit[c]["last_before"] + es_en(lang, " al ", " to ")
                      + sit[c]["first_after"])) if gap(c) else None,
                  "tip": f"<b>{NAME[lang][c]} · {first[c]['date']}</b><br>"
                         f"{first[c]['party'] or es_en(lang, 'orador no vinculado', 'speaker not linked')}"
                         f"<br>{num(b1[c]['occurrences'], 0, lang)} {es_en(lang, 'usos hasta 2025', 'uses up to 2025')}"}
                 for c in order]} for lang in LANGS})

    # week by week: the share of interventions that name the disease
    wk = defaultdict(dict)
    for r in J("B3_weekly")["rows"]:
        wk[r["country"]][r["week"]] = r

    def attention(c):
        v = [wk[c][w]["pct"] for w in range(0, 13) if w in wk[c]]
        return sum(v) / len(v) if v else -1
    by_att = sorted(ALL, key=lambda c: -attention(c))
    spec("pan_semanas", {lang: {
        "type": "multiples", "x_domain": [-10, 29], "y_shared": True, "digits": 1, "ref_x": 0,
        "y_grid": [25, 50], "y_grid_unit": " %", "x_ticks": es_en(lang, ["1 ene", "30 sep"], ["1 Jan", "30 Sep"]),
        "x_fmt": es_en(lang, "semana {x}", "week {x}"), "unit": "%",
        "extra": es_en(lang, "{v} intervenciones esa semana", "{v} interventions that week"),
        "empty": es_en(lang, "sin sesiones", "no sittings"),
        "title": es_en(lang, "Parte de las intervenciones que nombran «covid» o «coronavirus», semana a semana, enero–septiembre de 2020",
                       "Share of interventions naming 'covid' or 'coronavirus', week by week, January–September 2020"),
        "sub": es_en(lang, "Semana 0: la de la declaración de la OMS (línea discontinua). Los huecos son semanas sin sesiones. "
                           "Ordenados por la media de las semanas 0 a 12.",
                     "Week 0 is the week of the WHO declaration (dashed line). Gaps are weeks without sittings. Ordered "
                     "by the mean of weeks 0 to 12."),
        "aria": es_en(lang, "porcentaje semanal", "weekly share"),
        "panels": [{"label": NAME[lang][c],
                    "sub": (es_en(lang, "media ", "mean ") + num(attention(c), 1, lang) + " %") if attention(c) >= 0
                    else es_en(lang, "sin sesiones hasta sep.", "no sittings until Sep"),
                    "points": [[w, wk[c][w]["pct"] if w in wk[c] else None, wk[c][w]["interventions"] if w in wk[c] else None]
                               for w in range(-10, 30)]} for c in by_att]} for lang in LANGS})
    for lang in LANGS:
        rows = []
        for c in by_att:
            ws = [w for w in range(0, 13) if w in wk[c]]
            peak = max((wk[c][w] for w in wk[c] if w >= 0), key=lambda r: r["pct"], default=None)
            rows.append([NAME[lang][c], f"{len(ws)} / 13", num(attention(c), 1, lang) if ws else "—",
                         f"{num(peak['pct'], 1, lang)} ({es_en(lang, 'semana', 'week')} {peak['week']})" if peak else "—"])
        TABLES["pandemia"][("pan_semanas", lang)] = md_table(
            es_en(lang, ["País", "Semanas con sesión (0–12)", "Media de las semanas 0–12 (%)", "Semana más alta (%)"],
                  ["Country", "Weeks with sittings (0–12)", "Mean of weeks 0–12 (%)", "Highest week (%)"]), rows, right=(1, 2, 3))

    # the library, described before comparing
    lib = J("B5_describe")
    parts = lib["parts"]
    for lang in LANGS:
        rows = []
        for c in ALL:
            p = parts[c]
            if not p.get("items"):
                rows.append([NAME[lang][c], "0", "—", "—", "—", "—", "—", "—", "—"])
                continue
            rows.append([NAME[lang][c], num(p["items"], 0, lang), num(p["sessions"], 0, lang),
                         f"{p['date_from']} – {p['date_to']}", num(p["speakers"], 0, lang), num(p["words"], 0, lang),
                         num(p["linked_pct"], 1, lang), num(p["women_pct_of_sexed"], 1, lang),
                         num(p["long_turn_words_pct"], 1, lang)])
        TABLES["pandemia"][("pan_biblioteca", lang)] = md_table(
            es_en(lang, ["País", "Intervenciones", "Sesiones", "Fechas", "Oradores", "Palabras", "Vinculadas (%)",
                         "Mujeres (% de las que tienen sexo)", "Palabras en turnos largos (%)"],
                  ["Country", "Interventions", "Sittings", "Dates", "Speakers", "Words", "Linked (%)",
                   "Women (% of those with sex)", "Words in long turns (%)"]), rows, right=(1, 2, 4, 5, 6, 7, 8))
    in_lib = [c for c in ALL if parts[c].get("items")]
    others = [c for c in ARGS("B6_dist_es")["countries"] if c != "ES" and c in in_lib]

    # what each chamber talked about
    for vid, key, a, b in (("pan_es", "B6_dist_es", ("España", "Spain"),
                            (f"las otras {len(others)} cámaras de habla hispana", f"the other {len(others)} Spanish-speaking chambers")),
                           ("pan_ptbr", "B6_dist_pt_br", ("Portugal", "Portugal"), ("Brasil", "Brazil"))):
        spec(vid, {lang: {"type": "diverging", "value_label": "z",
                          "title": es_en(lang, f"Palabras más propias de {a[0]} y de {b[0]} en los debates de la pandemia",
                                         f"Words most typical of {a[1]} and of {b[1]} in the pandemic debates"),
                          "sub": es_en(lang, "Log-odds ponderado (z) en la biblioteca, sin turnos de más de 10.000 palabras "
                                             "y sin nombres de persona.",
                                       "Weighted log-odds (z) in the library, without turns over 10,000 words and "
                                       "without personal names."),
                          "aria": "distinctive words",
                          **contrast(key, a[0 if lang == "es" else 1], b[0 if lang == "es" else 1], "c1", "c0")}
                   for lang in LANGS})
        for lang in LANGS:
            TABLES["pandemia"][(vid, lang)] = contrast_table(key, a[0 if lang == "es" else 1], b[0 if lang == "es" else 1], lang)
    for lang in LANGS:
        TABLES["pandemia"][("pan_pe", lang)] = contrast_table("B6_dist_pe", es_en(lang, "Perú", "Peru"),
                                                              es_en(lang, "las demás", "the others"), lang)

    # women's voice in the pandemic debates and in all the speech of the same months
    vl = {r["country"]: r for r in J("B7_voice_lib")["rows"] if r["group"] == "F"}
    va = {r["country"]: r for r in J("B7_voice_all")["rows"] if r["group"] == "F"}
    keep = [c for c in in_lib if c in vl and parts[c]["items"] >= 100 and vl[c]["speakers"] >= 10]
    keep.sort(key=lambda c: -vl[c]["voice_to_members_ratio"])
    spec("pan_voz", {lang: {
        "type": "dumbbell", "log": True, "domain": [0.3, 2.5], "ticks": [0.5, 1, 2], "ratio_label": es_en(lang, "pandemia", "pandemic"),
        "a_color": "c0", "b_color": "c2", "ratio_digits": 2,
        "title": es_en(lang, "Voz de las diputadas frente a su peso en el registro: debates de la pandemia y todo el discurso",
                       "Women deputies' voice against their weight on the register: pandemic debates and all speech"),
        "sub": es_en(lang, "1 = hablan en proporción a su peso. Escala logarítmica. Solo las cámaras con 100 intervenciones y 10 "
                           "diputadas en la biblioteca.",
                     "1 = they speak in proportion to their weight. Log scale. Only chambers with 100 interventions and 10 "
                     "women in the library."),
        "legend": [{"label": es_en(lang, "Debates de la pandemia", "Pandemic debates"), "color": "c2", "dot": True},
                   {"label": es_en(lang, "Todo el discurso del 10-feb al 9-jul de 2020", "All speech, 10 Feb to 9 Jul 2020"),
                    "color": "c0", "dot": True, "hollow": True}],
        "aria": "voice ratio",
        "rows": [{"label": NAME[lang][c], "a": va[c]["voice_to_members_ratio"], "b": vl[c]["voice_to_members_ratio"],
                  "ratio": vl[c]["voice_to_members_ratio"],
                  "tip": f"<b>{NAME[lang][c]}</b><br>{es_en(lang, 'pandemia', 'pandemic')}: "
                         f"{num(vl[c]['voice_to_members_ratio'], 2, lang)} ({vl[c]['speakers']} {es_en(lang, 'diputadas', 'women')})"
                         f"<br>{es_en(lang, 'todo el discurso', 'all speech')}: {num(va[c]['voice_to_members_ratio'], 2, lang)}"}
                 for c in keep]} for lang in LANGS})
    for lang in LANGS:
        rows = [[NAME[lang][c], num(parts[c]["items"], 0, lang), num(vl[c]["speakers"], 0, lang),
                 pct(vl[c]["members_share"], 1, lang), pct(vl[c]["voice_share"], 1, lang),
                 num(vl[c]["voice_to_members_ratio"], 2, lang), num(va[c]["voice_to_members_ratio"], 2, lang),
                 "" if c in keep else es_en(lang, "fuera del gráfico", "left out of the chart")]
                for c in sorted(vl, key=lambda c: -vl[c]["voice_to_members_ratio"])]
        TABLES["pandemia"][("pan_voz", lang)] = md_table(
            es_en(lang, ["País", "Intervenciones", "Diputadas que hablan", "Peso en el registro", "Voz en la pandemia",
                         "Razón (pandemia)", "Razón (todo)", ""],
                  ["Country", "Interventions", "Women who speak", "Weight on the register", "Voice in the pandemic",
                   "Ratio (pandemic)", "Ratio (all)", ""]), rows, right=(1, 2, 3, 4, 5, 6))
    spark = defaultdict(list)
    for c in ALL:
        for w, r in wk[c].items():
            spark[w].append(r["pct"])
    facts = {"library_items": lib["items"], "library_countries": len(in_lib), "others_es": len(others),
             "first": {c: first[c]["date"] for c in ALL}}
    return facts, sorted((w, sum(v) / len(v)) for w, v in spark.items())


# ============================================================ C. voice and seats
def voz():
    c1 = defaultdict(dict)
    for r in J("C1_year")["rows"]:
        if r["group"] == "F":
            c1[r["country"]][int(r["period"])] = r
    last = {c: max(c1[c]) for c in ALL}
    spec("voz_anual", {lang: {
        "type": "multiples", "x_domain": [2010, 2025], "y_shared": True, "digits": 0, "y_grid": [25, 50],
        "y_grid_unit": " %", "unit": "%", "label2": es_en(lang, "peso en el registro", "weight on the register"),
        "title": es_en(lang, "Parte de las palabras que dicen las diputadas (línea) y su peso en el registro (discontinua)",
                       "Share of the words spoken by women deputies (line) and their weight on the register (dashed)"),
        "sub": es_en(lang, "Por año, sin la presidencia ni los turnos de más de 10.000 palabras. A la derecha, el último año.",
                     "By year, without the chair or turns over 10,000 words. On the right, the last year."),
        "aria": "voice share by year",
        "panels": [{"label": NAME[lang][c],
                    "sub": f"{num(100 * c1[c][last[c]]['voice_share'], 0, lang)} % / {num(100 * c1[c][last[c]]['members_share'], 0, lang)} %",
                    "points": [[y, round(100 * c1[c][y]["voice_share"], 1) if y in c1[c] else None] for y in range(2010, 2026)],
                    "points2": [[y, round(100 * c1[c][y]["members_share"], 1) if y in c1[c] else None] for y in range(2010, 2026)]}
                   for c in ALL]} for lang in LANGS})
    for lang in LANGS:
        years = (2010, 2013, 2016, 2019, 2022, 2025)
        rows = [[NAME[lang][c]] + [(f"{num(100 * c1[c][y]['voice_share'], 0, lang)} / {num(100 * c1[c][y]['members_share'], 0, lang)}"
                                    if y in c1[c] else "—") for y in years] for c in ALL]
        TABLES["voz"][("voz_anual", lang)] = md_table(
            [es_en(lang, "País (voz / registro, %)", "Country (voice / register, %)"), *map(str, years)], rows,
            right=tuple(range(1, 7)))

    c2 = {r["country"]: r for r in J("C2_recent")["rows"] if r["group"] == "F"}
    c3 = {r["country"]: r for r in J("C3_recent_turns")["rows"] if r["group"] == "F"}
    order = sorted(ALL, key=lambda c: -c2[c]["voice_to_members_ratio"])
    spec("voz_reciente", {lang: {
        "type": "dumbbell", "domain": [0, 0.7], "ticks": [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7], "pct": True,
        "a_color": "c0", "b_color": "c2", "ratio_label": es_en(lang, "razón", "ratio"), "ratio_digits": 2,
        "title": es_en(lang, "Diputadas desde 2021: peso en el registro y parte de las palabras",
                       "Women deputies since 2021: weight on the register and share of the words"),
        "sub": es_en(lang, "Sin la presidencia ni los turnos de más de 10.000 palabras. A la derecha, la razón entre las dos.",
                     "Without the chair or turns over 10,000 words. On the right, the ratio of the two."),
        "legend": [{"label": es_en(lang, "Parte de las palabras", "Share of the words"), "color": "c2", "dot": True},
                   {"label": es_en(lang, "Peso en el registro", "Weight on the register"), "color": "c0", "dot": True, "hollow": True}],
        "aria": "voice and seats",
        "rows": [{"label": NAME[lang][c], "a": c2[c]["members_share"], "b": c2[c]["voice_share"],
                  "ratio": c2[c]["voice_to_members_ratio"],
                  "tip": f"<b>{NAME[lang][c]}</b><br>{es_en(lang, 'palabras', 'words')}: {pct(c2[c]['voice_share'], 1, lang)}"
                         f"<br>{es_en(lang, 'turnos', 'turns')}: {pct(c3[c]['voice_share'], 1, lang)}"
                         f"<br>{es_en(lang, 'registro', 'register')}: {pct(c2[c]['members_share'], 1, lang)}"
                         f"<br>{c2[c]['speakers']} {es_en(lang, 'diputadas hablan', 'women speak')}"} for c in order]}
        for lang in LANGS})
    for lang in LANGS:
        rows = [[NAME[lang][c], pct(c2[c]["members_share"], 1, lang), pct(c2[c]["voice_share"], 1, lang),
                 num(c2[c]["voice_to_members_ratio"], 2, lang), pct(c3[c]["voice_share"], 1, lang),
                 num(c2[c]["speakers"], 0, lang), pct(c2[c]["linked_share_of_speech"], 0, lang)] for c in order]
        TABLES["voz"][("voz_reciente", lang)] = md_table(
            es_en(lang, ["País", "Peso en el registro", "Parte de las palabras", "Razón", "Parte de los turnos",
                         "Diputadas que hablan", "Discurso vinculado"],
                  ["Country", "Weight on the register", "Share of the words", "Ratio", "Share of the turns",
                   "Women who speak", "Linked speech"]), rows, right=(1, 2, 3, 4, 5, 6))

    # how each chamber speaks: the length of the turns (own SQL)
    for lang in LANGS:
        TABLES["voz"][("voz_turnos", lang)] = md_table(
            es_en(lang, ["País", "Intervenciones de diputados desde 2021", "Mediana de palabras", "Percentil 90"],
                  ["Country", "Deputies' interventions since 2021", "Median words", "90th percentile"]),
            [[NAME[lang][r["country"]], num(r["interventions"], 0, lang), num(r["median_words"], 0, lang),
              num(r["p90_words"], 0, lang)]
             for r in sorted(J("E1_turns")["rows"], key=lambda r: (-r["median_words"], r["country"]))], right=(1, 2, 3))

    # Mexico: the secretaries of the Mesa speak from the floor
    c4 = defaultdict(dict)
    for r in J("C4_mx_legislature")["rows"]:
        c4[r["period"]][r["group"]] = r
    c8 = defaultdict(dict)
    for r in J("C8_mx_mesa")["rows"]:
        c8[r["legislature"]][r["sex"]] = r
    mx = {}
    for leg in ("LXII", "LXIII", "LXIV", "LXV", "LXVI"):
        f, m = c8[leg]["F"], c8[leg]["M"]
        rest = f["words_rest"] / (f["words_rest"] + m["words_rest"])
        seats = c4[leg]["F"]["members_share"]
        mx[leg] = dict(seats=seats, voice=c4[leg]["F"]["voice_share"], ratio=c4[leg]["F"]["voice_to_members_ratio"],
                       rest=rest, ratio_rest=rest / seats, mesa_f=f["mesa_like"], mesa_m=m["mesa_like"])
    for lang in LANGS:
        TABLES["voz"][("voz_mx", lang)] = md_table(
            es_en(lang, ["Legislatura", "Peso de las diputadas", "Sus palabras", "Razón", "Diputadas / diputados con más de 1.000 turnos",
                         "Sus palabras sin ellos", "Razón sin ellos"],
                  ["Legislature", "Women's weight", "Their words", "Ratio", "Women / men with over 1,000 turns",
                   "Their words without them", "Ratio without them"]),
            [[leg, pct(v["seats"], 1, lang), pct(v["voice"], 1, lang), num(v["ratio"], 2, lang),
              f"{v['mesa_f']} / {v['mesa_m']}", pct(v["rest"], 1, lang), num(v["ratio_rest"], 2, lang)]
             for leg, v in mx.items()], right=(1, 2, 3, 5, 6))
    for vid, key, title in (("voz_mx_palabras", "C5_mx_words", ("México, LXIV legislatura (2018–2021)", "Mexico, 64th legislature (2018–2021)")),
                            ("voz_es_palabras", "C6_es_words", ("España, desde diciembre de 2019", "Spain, since December 2019"))):
        spec(vid, {lang: {"type": "diverging", "value_label": "z",
                          "title": es_en(lang, f"Palabras más propias de diputadas y de diputados · {title[0]}",
                                         f"Words most typical of women and of men deputies · {title[1]}"),
                          "sub": es_en(lang, "Log-odds ponderado (z), sin la presidencia.", "Weighted log-odds (z), without the chair."),
                          "aria": "distinctive words by sex",
                          **contrast(key, es_en(lang, "diputadas", "women"), es_en(lang, "diputados", "men"), "c2", "c0")}
                   for lang in LANGS})
        for lang in LANGS:
            TABLES["voz"][(vid, lang)] = contrast_table(key, es_en(lang, "Diputadas", "Women"), es_en(lang, "Diputados", "Men"), lang)

    # Catalan and Galician on the floor of the Congress
    langs = J("C6b_es_languages")["rows"]
    for lang in LANGS:
        TABLES["voz"][("voz_es_lenguas", lang)] = md_table(
            [es_en(lang, "Año", "Year")] + [str(r["year"]) for r in langs],
            [[es_en(lang, "Intervenciones con «perquè» o «máis»", "Interventions with 'perquè' or 'máis'")]
             + [num(r["interventions"], 0, lang) for r in langs]], right=tuple(range(1, len(langs) + 1)))

    # Spain since August 2023, with the socialist federations together
    c7 = J("C7_es_party")["rows"]
    psoe = [r for r in c7 if "PSOE" in r["group"]]
    for lang in LANGS:
        rows = [[r["group"], num(r["speakers"], 0, lang), num(r["members_on_register"], 0, lang), pct(r["members_share"], 1, lang),
                 pct(r["voice_share"], 1, lang), num(r["voice_to_members_ratio"], 2, lang)]
                for r in sorted(c7, key=lambda r: -r["words"])]
        ms, vs = sum(r["members_share"] for r in psoe), sum(r["voice_share"] for r in psoe)
        rows.append([es_en(lang, "**PSOE con sus federaciones**", "**PSOE with its federations**"),
                     num(sum(r["speakers"] for r in psoe), 0, lang), num(sum(r["members_on_register"] for r in psoe), 0, lang),
                     pct(ms, 1, lang), pct(vs, 1, lang), num(vs / ms, 2, lang)])
        TABLES["voz"][("voz_es_partidos", lang)] = md_table(
            es_en(lang, ["Etiqueta en el registro", "Diputados que hablan", "En el registro", "Peso en el registro",
                         "Parte de las palabras", "Razón"],
                  ["Label on the register", "Deputies who speak", "On the register", "Weight on the register",
                   "Share of the words", "Ratio"]), rows, right=(1, 2, 3, 4, 5))
    spark = [(y, sum(100 * c1[c][y]["voice_share"] for c in ALL if y in c1[c]) / sum(1 for c in ALL if y in c1[c]))
             for y in range(2010, 2026)]
    return {"mx": mx, "psoe": {"members_share": sum(r["members_share"] for r in psoe),
                               "voice_share": sum(r["voice_share"] for r in psoe)}}, spark


# ============================================================ D. frames: the pension reform
def marcos():
    lib = J("D1_library")["parts"]["BR"]
    months = {r["month"]: r for r in J("D1b_months")["rows"]}
    allm = [f"{y}-{m:02d}" for y in range(2016, 2020) for m in range(1, 13) if "2016-12" <= f"{y}-{m:02d}" <= "2019-11"]
    spec("mar_meses", {lang: {
        "type": "bars", "digits": 0,
        "title": es_en(lang, "Intervenciones de la biblioteca, mes a mes", "Interventions in the library, month by month"),
        "sub": es_en(lang, "Consulta SQL sobre las tablas de la biblioteca. Los meses vacíos son recesos.",
                     "An SQL query on the library's tables. Empty months are recesses."),
        "aria": "monthly interventions",
        "unit": es_en(lang, "intervenciones", "interventions"),
        "extra": es_en(lang, "{v} sesiones", "{v} sittings"),
        "ticks": {m: m[:4] for m in allm if m.endswith("-01")},
        "bars": [[m, months[m]["interventions"] if m in months else 0, months[m]["sessions"] if m in months else 0]
                 for m in allm]} for lang in LANGS})
    for lang in LANGS:
        rows = []
        for y in ("2016", "2017", "2018", "2019"):
            ms = [r for m, r in months.items() if m.startswith(y)]
            top = max(ms, key=lambda r: r["interventions"])
            rows.append([y, num(sum(r["interventions"] for r in ms), 0, lang), f"{top['month']} ({num(top['interventions'], 0, lang)})"])
        TABLES["marcos"][("mar_meses", lang)] = md_table(
            es_en(lang, ["Año", "Intervenciones", "Mes con más (intervenciones)"], ["Year", "Interventions", "Busiest month (interventions)"]),
            rows, right=(1,))

    net = J("D2_words")["networks"]["BR"]
    for lang in LANGS:
        rows = [[t["theme"], ", ".join([x for x in t["terms"] if x.lower() not in PEOPLE][:8]), num(t["pct_interventions"], 1, lang),
                 ", ".join(p for p, _ in t["parties_most"][:3]), ", ".join(p for p, _ in t["parties_least"][:3])]
                for t in net["themes"]]
        TABLES["marcos"][("mar_temas", lang)] = md_table(
            es_en(lang, ["Tema", "Términos más característicos", "Intervenciones con el tema (%)", "Partidos que más lo usan",
                         "Los que menos"],
                  ["Theme", "Most characteristic terms", "Interventions with the theme (%)", "Parties that use it most",
                   "Those that use it least"]), rows, right=(0, 2))
    for vid, key, a, b, ttl, sub in (
            ("mar_periodo", "D3_period", "2016–2017", "2019",
             ("Palabras más propias de cada reforma: la de 2016–2017 y la de 2019", "Words most typical of each reform: 2016–2017 and 2019"),
             ("Log-odds ponderado (z) en la biblioteca, sin la presidencia; sin nombres de persona.",
              "Weighted log-odds (z) in the library, without the chair; personal names left out.")),
            ("mar_pt_psl", "D4_pt_psl", "PT", "PSL",
             ("Palabras más propias del PT y del PSL en el debate de 2019", "Words most typical of PT and PSL in the 2019 debate"),
             ("Log-odds ponderado (z) en la biblioteca, 2019, sin la presidencia; sin nombres de persona.",
              "Weighted log-odds (z) in the library, 2019, without the chair; personal names left out."))):
        spec(vid, {lang: {"type": "diverging", "value_label": "z", "title": ttl[0 if lang == "es" else 1],
                          "sub": sub[0 if lang == "es" else 1], "aria": "distinctive words",
                          **contrast(key, a, b, "c7", "c4", n=14)} for lang in LANGS})
        for lang in LANGS:
            TABLES["marcos"][(vid, lang)] = contrast_table(key, a, b, lang)

    phrase = {r["party"].split(" ", 1)[1]: r for r in J("D6_phrase_party")["rows"]}
    for lang in LANGS:
        rows = []
        for p in ("PT", "PSOL", "PSL", "NOVO"):
            col = J(f"D5_colloc_{p}")
            ph = phrase.get(p, {"occurrences": 0, "per_million_words": 0})
            rows.append([p, num(col["total_matching_interventions"], 0, lang), ", ".join(c["word"] for c in col["collocates"][:6]),
                         num(ph["occurrences"], 0, lang), num(ph["per_million_words"], 1, lang)])
        TABLES["marcos"][("mar_privilegios", lang)] = md_table(
            es_en(lang, ["Partido", "Intervenciones con «privilégio*»", "Palabras que lo acompañan", "«Combater (os) privilégios»", "Por millón"],
                  ["Party", "Interventions with 'privilégio*'", "Words around it", "'Combater (os) privilégios'", "Per million"]),
            rows, right=(1, 3, 4))
        top = sorted(phrase.values(), key=lambda r: -r["occurrences"])[:6]
        TABLES["marcos"][("mar_frase", lang)] = md_table(
            es_en(lang, ["Partido", "Usos", "Intervenciones", "Palabras del partido en la biblioteca", "Por millón"],
                  ["Party", "Uses", "Interventions", "The party's words in the library", "Per million"]),
            [[r["party"].split(" ", 1)[1], num(r["occurrences"], 0, lang), num(r["interventions_using"], 0, lang),
              num(r["total_words"], 0, lang), num(r["per_million_words"], 1, lang)] for r in top], right=(1, 2, 3, 4))
    for lang in LANGS:
        TABLES["marcos"][("mar_kwic", lang)] = md_table(
            es_en(lang, ["Fecha", "Partido", "Contexto"], ["Date", "Party", "Context"]),
            [[l["date"], l["party"], f"…{l['left'].strip()[-80:]} **{l['match']}** {l['right'].strip()[:80]}…".replace("|", "/")]
             for l in J("D7_kwic")["lines"]])

    # institutions mentioned together, and the bias of each between left and right
    co = json.loads((CASOS / "redes" / "atores" / "previdencia_comention.json").read_text(encoding="utf-8"))
    for lang in LANGS:
        rows = [[n["name"], num(n["n"], 0, lang), num(n["n_esquerda"], 0, lang), num(n["n_direita"], 0, lang),
                 num(n["n_rest"], 0, lang), num(n["bias"], 2, lang)] for n in sorted(co["nodes"], key=lambda n: -n["n"])]
        TABLES["marcos"][("mar_actores", lang)] = md_table(
            es_en(lang, ["Institución", "Intervenciones", "Izquierda", "Derecha", "Resto", "Sesgo"],
                  ["Institution", "Interventions", "Left", "Right", "Rest", "Bias"]), rows, right=(1, 2, 3, 4, 5))

    # who names whom, before and after declaring the minister
    def matrix(key):
        n = J(key)["networks"]["BR"]
        return {(r["from"], r["to"]): r for r in n["block_matrix"]}, n["ei_index"]
    before, ei0 = matrix("D9_mentions")
    after, ei1 = matrix("D9b_minister")
    lab = {"es": {"esquerda": "izquierda", "direita": "derecha", "rest": "resto", "external": "ministro"},
           "en": {"esquerda": "left", "direita": "right", "rest": "rest", "external": "minister"}}
    top = max(r["per_100_interventions"] for m in (before, after) for r in m.values())

    def heat(m, cols, lang):
        head = "".join(f"<th>{lab[lang][c]}</th>" for c in cols)
        body = ""
        for a in ("esquerda", "direita", "rest"):
            cells = ""
            for b in cols:
                r = m.get((a, b))
                if not r:
                    cells += '<td class="cell qn">·</td>'
                    continue
                q = min(4, int(4 * r["per_100_interventions"] / top + 0.5))
                cells += (f'<td class="cell q{q}">{num(r["per_100_interventions"], 1, lang)}'
                          f'<small> ({r["mentions"]})</small></td>')
            body += f"<tr><th>{lab[lang][a]}</th>{cells}</tr>"
        corner = es_en(lang, "nombra ↓ · nombrado →", "names ↓ · named →")
        return f'<table class="heat"><thead><tr><th>{corner}</th>{head}</tr></thead><tbody>{body}</tbody></table>'
    spec("mar_mencoes", {lang: {
        "type": "html",
        "title": es_en(lang, "Menciones por cada 100 intervenciones del grupo que nombra (entre paréntesis, el recuento)",
                       "Mentions per 100 interventions of the naming group (count in brackets)"),
        "sub": es_en(lang, "Arriba, la red tal como sale; abajo, la misma red con el ministro declarado como actor externo. "
                           "E-I: de −1 (solo nombra a los suyos) a +1 (solo a los demás).",
                     "Top: the network as it comes out; bottom: the same network with the minister declared as an external "
                     "actor. E-I runs from −1 (names only its own) to +1 (only the others)."),
        "html": ('<div class="heat-pair"><div><p class="heat-k">' + es_en(lang, "Sin declarar al ministro", "Minister not declared")
                 + f' · E-I {lab[lang]["esquerda"]} {signed(ei0["esquerda"], 2, lang)}</p>'
                 + heat(before, ("esquerda", "direita", "rest"), lang)
                 + '</div><div><p class="heat-k">' + es_en(lang, "Con el ministro declarado", "Minister declared")
                 + f' · E-I {lab[lang]["esquerda"]} {signed(ei1["esquerda"], 2, lang)}</p>'
                 + heat(after, ("esquerda", "direita", "rest", "external"), lang) + "</div></div>")} for lang in LANGS})
    for lang in LANGS:
        rows = [[lab[lang][a], lab[lang][b], num(before[(a, b)]["mentions"], 0, lang) if (a, b) in before else "—",
                 num(after[(a, b)]["mentions"], 0, lang) if (a, b) in after else "—"] for (a, b) in sorted(set(before) | set(after))]
        rows += [["E-I", lab[lang][g], signed(ei0[g], 2, lang), signed(ei1[g], 2, lang)] for g in ("esquerda", "direita", "rest")]
        TABLES["marcos"][("mar_mencoes", lang)] = md_table(
            es_en(lang, ["Nombra", "Nombrado", "Sin declarar al ministro", "Con el ministro declarado"],
                  ["Names", "Named", "Minister not declared", "Minister declared"]), rows, right=(2, 3))
    m0, m1 = J("D9_mentions")["networks"]["BR"], J("D9b_minister")["networks"]["BR"]
    facts = {"items": lib["items"], "sessions": lib["sessions"], "speakers": lib["speakers"], "words": lib["words"],
             "themes": len(net["themes"]), "nodes": net["nodes"], "edges": net["edges"], "groups_n": co["groups"]["N_by_group"],
             "homonym_mentions": m0["top_receivers"][0][1], "minister_mentions": m1["top_receivers"][0][1],
             "ei_before": ei0, "ei_after": ei1, "counts": m0["counts"]}
    # the network pages, without the speakers' names
    (WEB / "redes").mkdir(exist_ok=True)
    w = json.loads((CASOS / "redes" / "palavras" / "previdencia_words.json").read_text(encoding="utf-8"))
    for v in w["metadata"].values():
        v["speaker"] = ""
    if w.get("parameters", {}).get("exclude"):     # the page carries its arguments, and the exclusion list is of names
        w["parameters"]["exclude"] = [f"({len(w['parameters']['exclude'])} personal names, not published)"]
    (WEB / "redes" / "palavras.html").write_text(network_html.words_page(w), encoding="utf-8")
    co["kwic"] = {k: [] for k in co.get("kwic", {})}
    for e in co["edges"]:
        e["examples"] = []
    (WEB / "redes" / "atores.html").write_text(network_html.comention_page(co), encoding="utf-8")
    return facts, [(i, months[m]["interventions"] if m in months else 0) for i, m in enumerate(allm)]


# ============================================================ the home page and the tools
# ============================================================ G. a library from scratch (the guide)
FOUR = ["CL", "CO", "EC", "PE"]
# The samples of casos.py G8 and G10 (20 interventions per chamber, seed 1), read by hand: how many talk about
# Venezuelan migrants. A new edition of the data needs a new reading.
READ = {"migracion_y_venezuela": {"CL": 16, "CO": 17, "EC": 6, "PE": 18},
        "migracion_venezolana": {"CL": 20, "CO": 20, "EC": 19, "PE": 20}}
DEFINING = re.compile(r"^(venezolan|venezuela|migra|inmigra|emigra|refugiad)")
# What the library leaves out, read by hand (casos.py G18b, G16b, G17c; 20 each): how many of the 20 name venezolan* or
# Venezuela anywhere in their full text (not only in the kwic line or the 900 characters shown), and then three classes:
# talks about Venezuelan migrants and names them somewhere in the intervention / talks about migration without saying
# where from / another topic, Venezuela's politics or procedure. Those naming Venezuela are read whole.
FUERA = {"perdidas": (20, 16, 3, 1), "contexto_CL": (7, 3, 4, 13), "contexto_CO": (3, 3, 4, 13),
         "contexto_EC": (4, 2, 0, 18), "contexto_PE": (7, 7, 7, 6), "colchane": (3, 3, 12, 5), "movilidad": (3, 0, 2, 18),
         "extranjeros": (0, 0, 4, 16)}


def wilson(k, n, z=1.96):
    """95 % interval for a share read in a sample of n."""
    c, h = (k + z * z / 2) / (n + z * z), z * math.sqrt(k * (n - k) / n + z * z / 4) / (n + z * z)
    return max(0.0, c - h), min(1.0, c + h)


def bibliotecas():
    g1 = J("G1_terms")["terms"]
    for lang in LANGS:
        rows = [[f"`{t['term'].replace('+', ' + ')}`"] + [num(t["by_country"][c]["occurrences"], 0, lang) for c in FOUR]
                + [num(t["interventions"], 0, lang)] for t in g1]
        TABLES["bibliotecas"][("bib_terminos", lang)] = md_table(
            [es_en(lang, "Término", "Term")] + [NAME[lang][c] for c in FOUR]
            + [es_en(lang, "Intervenciones (las cuatro)", "Interventions (all four)")], rows, right=(1, 2, 3, 4, 5))

    thresholds = {k: J(f"G3_migra_{k}") for k in (1, 2, 3)}
    for lang in LANGS:
        rows = [[es_en(lang, f"{k} o más", f"{k} or more")] + [num(r["parts"][c]["items"], 0, lang) for c in FOUR]
                + [num(r["items"], 0, lang)] for k, r in thresholds.items()]
        TABLES["bibliotecas"][("bib_umbral", lang)] = md_table(
            [es_en(lang, "Menciones por intervención", "Mentions per intervention")] + [NAME[lang][c] for c in FOUR]
            + ["Total"], rows, right=(1, 2, 3, 4, 5))

    first, second = J("G6_combine"), J("G9_sentence")
    for lang in LANGS:
        rows = [[NAME[lang][c], num(first["parts"][c]["items"], 0, lang), f"{READ['migracion_y_venezuela'][c]} / 20",
                 num(second["parts"][c]["items"], 0, lang), f"{READ['migracion_venezolana'][c]} / 20"] for c in FOUR]
        rows.append(["**Total**", num(first["items"], 0, lang), "", num(second["items"], 0, lang), ""])
        TABLES["bibliotecas"][("bib_definiciones", lang)] = md_table(
            es_en(lang, ["País", "Primera: intervenciones", "Primera: de 20 leídas, sobre migrantes venezolanos",
                         "Segunda: intervenciones", "Segunda: de 20 leídas, sobre migrantes venezolanos"],
                  ["Country", "First: interventions", "First: of 20 read, about Venezuelan migrants",
                   "Second: interventions", "Second: of 20 read, about Venezuelan migrants"]), rows, right=(1, 2, 3, 4))

    final = J("G10d_describe")
    for lang in LANGS:
        rows = []
        for c in FOUR:
            p = final["parts"][c]
            rows.append([NAME[lang][c], num(p["items"], 0, lang), num(p["sessions"], 0, lang),
                         f"{p['date_from']} – {p['date_to']}", num(p["speakers"], 0, lang), num(p["words"], 0, lang),
                         num(p["linked_pct"], 1, lang), num(p["women_pct_of_sexed"], 1, lang),
                         num(p["long_turn_words_pct"], 1, lang)])
        TABLES["bibliotecas"][("bib_describe", lang)] = md_table(
            es_en(lang, ["País", "Intervenciones", "Sesiones", "Fechas", "Oradores", "Palabras", "Vinculadas (%)",
                         "Mujeres (% de las que tienen sexo)", "Palabras en turnos largos (%)"],
                  ["Country", "Interventions", "Sittings", "Dates", "Speakers", "Words", "Linked (%)",
                   "Women (% of those with sex)", "Words in long turns (%)"]), rows, right=(1, 2, 4, 5, 6, 7, 8))

    # year by year, per thousand interventions of the chamber, with both definitions
    yr = defaultdict(dict)
    for r in J("G11_years")["rows"]:
        yr[(r["library"], r["country"])][r["year"]] = r
    years = sorted({y for d in yr.values() for y in d})
    rate = lambda lib, c, y: yr[(lib, c)][y]["per_1000"]
    spec("bib_anual", {lang: {
        "type": "multiples", "x_domain": [years[0], years[-1]], "y_shared": False, "digits": 2, "no_area": False,
        "unit": es_en(lang, "por mil", "per thousand"), "label2": es_en(lang, "primera definición", "first definition"),
        "extra": es_en(lang, "{v} intervenciones (segunda definición)", "{v} interventions (second definition)"),
        "title": es_en(lang, "Intervenciones sobre la migración venezolana por cada mil intervenciones del pleno, año a año",
                       "Interventions on Venezuelan migration per thousand interventions of the floor, year by year"),
        "sub": es_en(lang, "Cada panel tiene su propia escala: compara la forma dentro de cada cámara, no la altura entre "
                           "cámaras.",
                     "Each panel has its own scale: compare the shape within each chamber, not the height across "
                     "chambers."),
        "legend": [{"label": es_en(lang, "segunda definición: en la misma frase", "second definition: in the same sentence"),
                    "color": "c1"},
                   {"label": es_en(lang, "primera: migración y Venezuela en la intervención",
                                   "first: migration and Venezuela in the intervention"), "color": "fg3", "dash": True}],
        "aria": es_en(lang, "intervenciones por mil, año a año", "interventions per thousand, year by year"),
        "panels": [{"label": NAME[lang][c],
                    "sub": es_en(lang, "máximo ", "highest ") + str(max(years, key=lambda y: rate("migracion_venezolana", c, y))),
                    "points": [[y, rate("migracion_venezolana", c, y), yr[("migracion_venezolana", c)][y]["items"]]
                               for y in years],
                    "points2": [[y, rate("migracion_y_venezuela", c, y)] for y in years]} for c in FOUR]}
        for lang in LANGS})
    for lang in LANGS:
        rows = []
        for c in FOUR:
            for lib, label in (("migracion_venezolana", es_en(lang, "segunda", "second")),
                               ("migracion_y_venezuela", es_en(lang, "primera", "first"))):
                rows.append([f"{NAME[lang][c]} ({label})"] + [num(rate(lib, c, y), 2, lang) for y in years])
        TABLES["bibliotecas"][("bib_anual", lang)] = md_table(
            [es_en(lang, "País (definición)", "Country (definition)")] + [str(y) for y in years], rows,
            right=tuple(range(1, len(years) + 1)))

    # what distinguishes the debate within each chamber: the defining terms and personal names left out
    for lang in LANGS:
        rows = []
        for c in FOUR:
            items = [w for w in J(f"G12_dist_{c}")["distinctive_of_a"] if not DEFINING.match(w["word"].lower())]
            rows.append([NAME[lang][c], ", ".join(w["word"] for w in words(items, 15))])
        TABLES["bibliotecas"][("bib_palabras", lang)] = md_table(
            es_en(lang, ["País", "Palabras que distinguen el debate del resto de su cámara, de más a menos"],
                  ["Country", "Words that set the debate apart from the rest of its chamber, most first"]), rows)

    # beyond the keywords: the rest of each debate, and what stays outside read by hand
    context = {r["country"]: r for r in J("G16_context")["rows"]}
    for lang in LANGS:
        rows = [[NAME[lang][c], num(r["sessions"], 0, lang), num(r["in_library"], 0, lang), num(r["outside"], 0, lang),
                 num(r["outside_50_words_or_more"], 0, lang)] for c, r in context.items()]
        TABLES["bibliotecas"][("bib_contexto", lang)] = md_table(
            es_en(lang, ["País", "Sesiones", "En la biblioteca", "Fuera", "Fuera, de 50 palabras o más"],
                  ["Country", "Sittings", "In the library", "Outside", "Outside, 50 words or more"]), rows, right=(1, 2, 3, 4))
    lost_lib = J("G18_lost")
    lost = lost_lib["parts"]
    new = {name: {"items": J(f"G17_{name}")["items"], "outside": J(f"G17b_{name}_fuera")["items"],
                  "naming": J(f"G17d_{name}_venez")["items"]} for name in ("colchane", "movilidad", "extranjeros")}
    # (key, label, outside, how many of them name Venezuela: a ceiling for the first class)
    places = [("perdidas", ("Lo que la segunda definición deja fuera de la primera, Chile",
                            "What the second definition leaves out of the first, Chile"),
               lost["CL"]["items"], lost["CL"]["items"])]
    places += [(f"contexto_{c}", (f"El resto de los debates, {NAME['es'][c]}", f"The rest of the debates, {NAME['en'][c]}"),
                context[c]["outside"], context[c]["outside_naming_venezuela"]) for c in FOUR]
    places += [(name, (f"{w}, {NAME['es'][c]}", f"{w}, {NAME['en'][c]}"), new[name]["outside"], new[name]["naming"])
               for name, c, w in (("colchane", "CL", "*Colchane*"), ("movilidad", "EC", "*movilidad humana*"),
                                  ("extranjeros", "PE", "`extranjero*`"))]
    # the first class has to name Venezuela, so its share is estimated among the sampled ones that do, and scaled to
    # all those outside that do; with none in the sample, all that is known is the ceiling
    bounds = {}
    for key, _, outside, naming in places:
        named_read, on_topic = FUERA[key][:2]
        lo, hi = wilson(on_topic, named_read) if named_read else (0.0, 1.0)
        bounds[key] = [round(lo * naming), round(hi * naming)]
    for lang in LANGS:
        rows = [[label[LANGS.index(lang)], num(outside, 0, lang), num(naming, 0, lang)]
                + [str(v) for v in FUERA[key]] + [f"{num(bounds[key][0], 0, lang)}–{num(bounds[key][1], 0, lang)}"]
                for key, label, outside, naming in places]
        TABLES["bibliotecas"][("bib_fuera", lang)] = md_table(
            es_en(lang, ["Dónde", "Fuera", "Nombran Venezuela", "De 20 leídas: nombran Venezuela",
                         "migrantes venezolanos", "migración sin decir de dónde", "otro tema",
                         "Migrantes venezolanos fuera (intervalo del 95 %)"],
                  ["Where", "Outside", "Name Venezuela", "Of 20 read: name Venezuela", "Venezuelan migrants",
                   "migration without saying where from", "another topic", "Venezuelan migrants outside (95% interval)"]),
            rows, right=(1, 2, 3, 4, 5, 6, 7))
    in_cl = final["parts"]["CL"]["items"]
    coverage_cl = [round(100 * in_cl / (in_cl + bounds["perdidas"][1])), round(100 * in_cl / (in_cl + bounds["perdidas"][0]))]

    sessions = defaultdict(list)
    for r in J("G11b_sessions")["rows"]:
        sessions[r["country"]].append(r)
    floor = {c: {y: yr[("migracion_venezolana", c)][y]["interventions"] for y in years} for c in FOUR}
    return {"lost": {"total": lost_lib["items"], **{c: p["items"] for c, p in lost.items()}}, "new_words": new,
            "fuera_bounds": bounds, "coverage_cl_pct": coverage_cl, "first": first["items"], "second": second["items"], "final": final["items"],
            "once": J("G4_once")["items"], "venezuela": J("G5_venez")["items"], "removed": J("G10b_remove")["removed"],
            "kwic_totals": {k: J(k)["total_matching_interventions"] for k in
                            ("G2_kwic_desplazad", "G2_kwic_venez", "G2_kwic_migrante_EC", "G11c_kwic_CO", "G12b_kwic_gc898")},
            "long_turn_words_pct": {"first": {c: J("G7_describe")["parts"][c]["long_turn_words_pct"] for c in FOUR},
                                    "second": {c: second["parts"][c]["long_turn_words_pct"] for c in FOUR}},
            # country, date and length only: the speaker is a role, said in the prose
            "long_turns": [[r["country"], r["date"], r["n_words"]] for r in J("G10a_long")["rows"]],
            "floor_interventions": floor, "top_sessions": {c: sessions[c][0] for c in FOUR}}


def inicio():
    z1 = J("Z1_list")["countries"]
    for lang in LANGS:
        rows = [[NAME[lang][c["iso"]], f"{c['downloaded']['date_min'][:4]}–{c['downloaded']['date_max'][:4]}",
                 num(c["downloaded"]["n_sessions"], 0, lang), num(c["downloaded"]["n_speech_rows"], 0, lang),
                 c["downloaded"]["version"], f"[{c['doi']}]({c['url']})"] for c in z1]
        rows.append(["**Total**", "", num(sum(c["downloaded"]["n_sessions"] for c in z1), 0, lang),
                     num(sum(c["downloaded"]["n_speech_rows"] for c in z1), 0, lang), "", ""])
        TABLES["index"][("ini_corpus", lang)] = md_table(
            es_en(lang, ["País", "Años", "Sesiones", "Intervenciones de discurso", "Versión", "DOI"],
                  ["Country", "Years", "Sittings", "Speech interventions", "Version", "DOI"]), rows, right=(2, 3))
    cov = J("Z2_coverage")["summary"]
    for lang in LANGS:
        TABLES["index"][("ini_cobertura", lang)] = md_table(
            es_en(lang, ["País", "Palabras al año (mediana)", "Palabras en turnos de más de 10.000 (%)", "Discurso vinculado (%)"],
                  ["Country", "Words a year (median)", "Words in turns over 10,000 (%)", "Linked speech (%)"]),
            [[NAME[lang][c], num(v["median_words_per_year"], 0, lang), num(v["long_turn_words_pct"], 1, lang),
              num(100 * v["corpus_linkage"]["gross"], 1, lang)] for c, v in cov.items()], right=(1, 2, 3))
    return {"sessions": sum(c["downloaded"]["n_sessions"] for c in z1),
            "speech_rows": sum(c["downloaded"]["n_speech_rows"] for c in z1),
            "years": [min(c["downloaded"]["date_min"][:4] for c in z1), max(c["downloaded"]["date_max"][:4] for c in z1)],
            "export_rows": J("E2_export")["rows"], "explorer_files": len(J("E3_lib_export")["files"])}


GROUPS = [
    ("datos", "Datos, cobertura y cita", "Data, coverage and citation",
     ["list_countries", "download_country", "import_from_folder", "coverage", "describe_data", "get_documentation", "how_to_cite"]),
    ("frecuencias", "Frecuencias", "Frequencies", ["ngram_viewer", "term_counter", "term_frequency"]),
    ("grupos", "Grupos: quién habla y cómo", "Groups: who speaks and how", ["share_of_voice", "distinctive_words"]),
    ("lectura", "Lectura", "Reading", ["kwic", "collocations", "search_text", "get_intervention", "get_session"]),
    ("bibliotecas", "Bibliotecas", "Libraries",
     ["library_create", "library_describe", "library_edit", "library_combine", "library_export", "library_import",
      "library_rebuild", "library_delete"]),
    ("redes", "Redes", "Networks", ["cooccurrence_network", "comention_network", "mention_network"]),
    ("sql", "SQL, exportación y registro", "SQL, export and log", ["query_sql", "export_result", "query_log"]),
]
STUDY_PAGES = {"feminicidio": ("Feminicidio", "Femicide"), "pandemia": ("Pandemia", "Pandemic"),
               "voz": ("Voz y escaños", "Voice and seats"), "marcos": ("Marcos", "Frames"),
               "bibliotecas": ("Bibliotecas", "Libraries"), "index": ("Inicio", "Home")}


def used_in():
    """Where each tool appears in a request of the pages ('El agente usa `tool`'), section by section."""
    out = defaultdict(list)
    for page, (src, _) in PAGES.items():
        path = DOCS / src
        if not path.exists():
            continue
        sec = None
        for line in path.read_text(encoding="utf-8").split("\n"):
            m = re.match(r"## (\d+)\. ", line)
            if m:
                sec = m[1]
            elif sec and "*El agente usa*" in line:
                for t in re.findall(r"`([a-z_]+)`", line.split("*El agente usa*", 1)[1]):
                    u = {"page": page, "section": sec, "es": f"{STUDY_PAGES[page][0]} § {sec}", "en": f"{STUDY_PAGES[page][1]} § {sec}"}
                    if u not in out[t]:
                        out[t].append(u)
    return out


def herramientas():
    texts = json.loads((WEB / "herramientas.json").read_text(encoding="utf-8"))
    tools = {t.name: t for t in asyncio.run(server._server.list_tools())}
    grouped = [n for g in GROUPS for n in g[3]]
    if set(tools) != set(grouped) or set(tools) != set(texts):
        raise SystemExit(f"tools and groups differ: {sorted(set(tools) ^ set(grouped))} {sorted(set(tools) ^ set(texts))}")
    where = used_in()
    out = {"groups": []}
    for gid, es, en, names in GROUPS:
        group = {"id": gid, "es": es, "en": en, "tools": []}
        for n in names:
            t = tools[n]
            params = []
            for k, v in (t.input_schema.get("properties") or {}).items():
                opts = v.get("anyOf", [v])
                enum = next((x["enum"] for x in opts if x.get("enum")), None)
                kind = " | ".join(map(str, enum)) if enum else " | ".join(x["type"] for x in opts if x.get("type") not in (None, "null"))
                if v.get("default") not in (None, [], {}, ""):
                    kind += f" = {json.dumps(v['default'], ensure_ascii=False)}"
                params.append({"name": k, "kind": kind, "description": " ".join((v.get("description") or "").split())})
            desc = " ".join((t.description or "").split("\n\n")[0].split())
            group["tools"].append({"name": n, "description": desc, "params": params, "used_in": where.get(n, []), **texts[n]})
        out["groups"].append(group)
    (DATA / "tools.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(tools)


STUDIES = [
    ("feminicidio", ("Estudio 1 · Difusión", "Study 1 · Diffusion"),
     ("Cómo entra una palabra en dieciséis parlamentos", "How a word enters sixteen parliaments"),
     ("Cuándo llega «feminicidio» a cada cámara, qué ley la trae, quién la dice y con qué palabras.",
      "When 'femicide' reaches each chamber, which law brings it, who says it and with which words."),
     ["term_counter", "ngram_viewer", "term_frequency", "get_session", "query_sql", "collocations"]),
    ("pandemia", ("Estudio 2 · Un acontecimiento", "Study 2 · An event"),
     ("Un virus, dieciséis plenos", "One virus, sixteen floors"),
     ("Cómo reaccionó cada parlamento a la COVID-19: primeros usos y sus falsos positivos, semanas sin sesiones, una "
      "biblioteca de quince países.",
      "How each parliament reacted to COVID-19: first uses and their false positives, weeks without sittings, a library "
      "of fifteen countries."),
     ["term_counter", "kwic", "query_sql", "library_create", "library_describe", "distinctive_words", "share_of_voice"]),
    ("voz", ("Estudio 3 · Representación", "Study 3 · Representation"),
     ("Quién habla y cuánto pesa", "Who speaks, and how much they weigh"),
     ("La voz de las diputadas frente a su peso en el registro, y tres trampas que la cambian: la Mesa, las etiquetas y la "
      "forma de los turnos.",
      "Women deputies' voice against their weight on the register, and three traps that change it: the Mesa, the labels "
      "and the shape of the turns."),
     ["share_of_voice", "distinctive_words", "query_sql"]),
    ("marcos", ("Estudio 4 · Marcos", "Study 4 · Frames"),
     ("Combatir privilegios: la reforma de las pensiones en Brasil", "Fighting privileges: Brazil's pension reform"),
     ("Temas, marcos en disputa, instituciones que se nombran juntas y quién nombra a quién, con un homónimo que invierte "
      "la conclusión.",
      "Themes, contested frames, institutions named together and who names whom, with a homonym that reverses the "
      "conclusion."),
     ["library_create", "cooccurrence_network", "distinctive_words", "collocations", "kwic", "comention_network", "mention_network"]),
]


def studies(sparks):
    out = {lang: [] for lang in LANGS}
    for slug, eyebrow, title, text, tools in STUDIES:
        for i, lang in enumerate(LANGS):
            out[lang].append({"slug": slug, "eyebrow": eyebrow[i], "title": title[i], "text": text[i], "tools": tools,
                              "spark": [[x, round(v, 3)] for x, v in sparks[slug]]})
    (DATA / "studies.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


# ============================================================ writing
def write_tables():
    for page, items in TABLES.items():
        for i, lang in enumerate(LANGS):
            path = DOCS / PAGES[page][i]
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            for (vid, l), md in items.items():
                if l != lang:
                    continue
                pat = re.compile(rf"(<!-- table:{vid} -->\n).*?(\n<!-- /table -->)", re.S)
                if not pat.search(text):
                    print(f"  ! {path.name}: no table:{vid}")
                    continue
                text = pat.sub(lambda m: m[1] + md + m[2], text)
            path.write_text(text, encoding="utf-8")


def main():
    fem_totals, fem_spark = feminicidio()
    pan_facts, pan_spark = pandemia()
    voz_facts, voz_spark = voz()
    mar_facts, mar_spark = marcos()
    bib_facts = bibliotecas()
    ini_facts = inicio()
    for vid, by_lang in SPECS.items():
        (DATA / f"{vid}.json").write_text(json.dumps(by_lang, ensure_ascii=False, indent=1), encoding="utf-8")
    write_tables()
    n_tools = herramientas()
    studies({"feminicidio": fem_spark, "pandemia": pan_spark, "voz": voz_spark, "marcos": mar_spark})
    facts = {"mcp_version": version("parlaibero-mcp"),
             "versions": {c["iso"]: c["downloaded"]["version"] for c in J("Z1_list")["countries"]},
             "tools": n_tools, "corpus": ini_facts, "feminicidio": fem_totals, "pandemia": pan_facts, "voz": voz_facts,
             "marcos": mar_facts, "bibliotecas": bib_facts}
    (DATA / "facts.json").write_text(json.dumps(facts, ensure_ascii=False, indent=1))
    print(f"{len(SPECS)} charts, {sum(len(v) for v in TABLES.values())} tables, {n_tools} tools")
    if "--show" in sys.argv:
        only = sys.argv[sys.argv.index("--show") + 1:] or list(TABLES)
        for page, items in TABLES.items():
            if page not in only:
                continue
            for (vid, lang), md in items.items():
                if lang == "es":
                    print(f"\n== {page} · {vid}\n{md}")


if __name__ == "__main__":
    main()
