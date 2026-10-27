"""The report of a theme reading: step 5 of the protocol in parlaibero://methods/networks § 4. The agent writes the
interpretation in a spec file; the engine computes every figure from the network, takes every quote from the
codebook and checks it again against the record, and renders the report as Markdown and HTML. Nothing here calls a
language model.

theme_report(codebook) writes a spec template next to the codebook: the themes and frames that can be quoted (their
anchors) and every placeholder the prose can use, with its current value. theme_report(codebook, report=spec)
checks the spec and, without errors, writes <spec>.md and <spec>.html; the check, <spec>_check.json, is rewritten on
every call.

In the prose a number is a placeholder ({dominated:3}, {year:4:1934}…) that the engine fills; a bare number is
reported, because the engine cannot vouch for it. A quote is a reference to an anchor of the codebook (its id_int,
and its first words when the intervention has two anchors there), so the text printed is the anchor's. Seat lines
carry the id, the date, the group and the stance, never the speaker. The verdicts rendered are 'theme' and
'artefact': a 'merge' or a 'split' is resolved in the codebook first, since the figures are the network's.
"""
from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import re
from collections import Counter
from datetime import date
from pathlib import Path

from . import __version__, cooccurrence as co, network_html, networks, profile, store, themes
from .catalog import COUNTRIES

SCHEMA = "parlaibero-report/1"
STABILITY_RUNS = 20              # as theme_dossier's default, so the labels are the dossier's
SPEAKER_CAVEAT = 0.2             # a theme whose first speaker gives this share or more needs a caveat
FEW_IN_SAMPLE = 5                # passages of the blind sample under which a theme's share cannot be read
SHORT_LABEL = 32                 # longest row label of the figures
PLACEHOLDER = re.compile(r"\{([A-Za-z_]+)((?::[^{}:]+)*)\}")
NUMBER = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)*(?!\w|\s*\.?\s*[ªº])")
_UP = "A-ZÁÉÍÓÚÂÊÔÃÕÇÑÜ"
_NAME = rf"(?:\s+(?:de\s+(?:la\s+|los\s+|las\s+)?|da\s+|do\s+|dos\s+)?[{_UP}][\wáéíóúâêôãõçñü-]+)+"
ADDRESS = re.compile(rf"\b(?:Sr|Sra|Sres|Srs|Excmo|Excma|Dr|Dra|Dña|Mr|Mrs|Ms|D)\.({_NAME})"
                     rf"|\b(?:[Ss]eñor(?:es|a)?|[Ss]enhor(?:es|a)?|[Dd]on|[Dd]oña|[Dd]ona)({_NAME})")
ROLES = {"presidente", "presidenta", "ministro", "ministra", "diputado", "diputada", "deputado", "deputada",
         "secretario", "secretaria", "secretário", "secretária", "relator", "relatora", "orador", "oradora",
         "senador", "senadora", "president", "minister", "speaker"}
TOKENS_CSS = network_html.CSS.split("*{box-sizing")[0]    # the engine's colour tokens, light and dark

L10N = {
    "es": {
        "thousands": ".", "decimal": ",", "pct": " %", "q": ("«", "»"), "and": "y", "nor": "ni",
        "interventions": "intervenciones", "theme": "tema", "reading_by": "lectura",
        "unknown_reader": "un lector sin identificar",
        "in_brief": "En pocas palabras", "box": "Qué está medido, qué es lectura y qué falta",
        "measured": "**Medido por la red, sin interpretar.** Qué palabras aparecen juntas, qué temas forman, cuántas "
                    "intervenciones domina cada tema, en qué años y en qué grupos, y si los temas reaparecen al repetir "
                    "el cálculo con otras semillas y resoluciones (la estabilidad). Un tema **domina** una intervención "
                    "cuando reúne más palabras de ella que ningún otro tema, y al menos dos distintas. No es lo mismo "
                    "que «trata de»: una intervención puede tocar varios temas y la domina uno solo.",
        "reading": "**Lectura.** Las etiquetas, las definiciones, los marcos (con sus cuatro funciones: problema, "
                   "causa, evaluación y remedio, según Entman) y la postura de cada cita (afirma, discute o cita el "
                   "marco). Las ha escrito {reader} después de leer el dossier de cada tema. Las {quotes} citas de "
                   "este informe se comprobaron literalmente contra el acta al generarlo y se reproducen tal como "
                   "están en el texto digitalizado, erratas incluidas.",
        "missing": "**Falta.** Que una persona y un agente en un contexto nuevo codifiquen a ciegas una muestra de "
                   "pasajes, para medir su acuerdo (κ de Cohen) y el peso de cada tema y marco con su intervalo.",
        "missing_sample": " La muestra tiene {n} pasajes.",
        "missing_few": " En ella, {themes} tienen menos de {m} pasajes cada uno: para medirlos haría falta una muestra "
                       "mayor.",
        "missing_few_1": " En ella, {themes} tiene menos de {m} pasajes: para medirlo haría falta una muestra mayor.",
        "kappa": "**Medido después.** Una persona y un agente codificaron a ciegas {n} pasajes: acuerdo en el tema, "
                 "κ = {kt}; en el marco, κ = {kf}. Los pesos de cada tema y marco, con su intervalo, están en {file}.",
        "h_weight": "¿Cuánto pesa cada tema?", "h_years": "¿Cuándo se habló de cada tema?", "h_themes": "Los temas",
        "h_groups": "¿Quién habla de qué?", "h_residual": "Lo que queda fuera", "h_method": "Cómo se ha hecho",
        "h_next": "Próximos pasos", "h_files": "Anexo: de dónde sale cada cosa",
        "f_weight": "Intervenciones que domina cada tema",
        "f_weight_sub": "De {N} intervenciones. La barra de arriba es el todo, en tres partes; debajo, cada tema.",
        "f_years": "Parte de las intervenciones de cada año que domina cada tema",
        "f_years_sub": "En %. Debajo de cada año, cuántas intervenciones tiene.",
        "f_groups": "Parte de las intervenciones de cada grupo que domina cada tema",
        "f_groups_sub": "En %. Grupos ({col}) con {m} intervenciones o más; debajo de cada uno, cuántas tiene.",
        "n_years_hidden": "Años con menos de {m} intervenciones, que no se muestran: {list}. ",
        "n_cells": "Las celdas vacías no tienen ninguna intervención dominada por el tema. Clases por quintiles; se "
                   "rotula el valor más alto de cada fila.",
        "n_groups": "Una cuota alta puede deberse a pocos oradores muy activos, y un grupo pequeño se apoya en pocos "
                    "casos. ",
        "source": "Fuente: {file} ({library}, {country}). Calculado por {engine} el {day}.",
        "seg": ("Temas", "Artefactos", "Ningún tema"), "table": "Ver los datos en una tabla",
        "col_theme": "Tema", "col_n": "Intervenciones", "col_share": "Parte",
        "seat_theme": "tema {k} · {d} intervenciones ({p}) · {c} de ellas en {y} · estabilidad {s}, {lab}",
        "seat_speaker": " · un orador da el {x}",
        "stab": {"robust": "robusta", "moderate": "moderada", "fragile": "frágil"},
        "stance": {"affirms": "afirma", "contests": "discute", "cites": "cita"},
        "frame": "Marco {q0}{name}{q1}.", "careful": "Para leerlo con cuidado:", "terms": "Palabras del tema:",
        "residual": "Los temas que la lectura juzgó artefactos dominan {r} intervenciones ({rp}); en {n} ({np}) no "
                    "domina ningún tema.",
        "residual_terms": "Palabras del tema {k}: {terms}.",
        "m_library": "**La biblioteca:** {N} intervenciones de «{library}» ({country}){speech}.",
        "m_speech": ", solo su habla",
        "m_network": "**La red de palabras:** los {vocabulary} términos más característicos de la biblioteca frente "
                     "al resto del corpus{exclude}. Dos términos se unen cuando aparecen juntos en una {unit} más de "
                     "lo que daría el azar (G² de Dunning ≥ {g2}) y el vínculo está entre los {neighbours} más fuertes "
                     "de alguno de los dos; el algoritmo de Leiden (resolución {gamma}, semilla {seed}) agrupa los "
                     "términos en temas.",
        "m_exclude": ", sin {terms}", "m_unit": "intervención", "m_fragment": "ventana de {n} palabras",
        "m_dossier": "**El dossier:** para cada tema, sus palabras, años, grupos, estabilidad ({runs} repeticiones de "
                     "Leiden) y una muestra de intervenciones para leer, con pasajes cortados del acta.",
        "m_codebook": "**La lectura:** el codebook, con veredicto, etiqueta, definición, qué se incluye y qué no, "
                      "marcos y citas literales con su postura.",
        "m_check": "**La comprobación:** `check_codebook` verifica cada cita contra el acta y saca la muestra que se "
                   "codificará a ciegas.",
        "m_report": "**Este informe:** la interpretación es de quien leyó; `theme_report` calcula cada cifra a partir "
                    "de la red, toma cada cita del codebook y la vuelve a comprobar contra el acta.",
        "data": "**Datos.** {citation}. Los identificadores de las citas son los de esa versión: en otra versión no "
                "designan la misma intervención.",
        "files": ("Qué", "Archivo"),
        "file_rows": ("Red de palabras", "Codebook", "Comprobación del codebook", "Texto del informe (de quien lee)"),
        "mode": ("Modo: del sistema", "Modo: oscuro", "Modo: claro"),
    },
    "pt": {
        "thousands": ".", "decimal": ",", "pct": " %", "q": ("“", "”"), "and": "e", "nor": "nem",
        "interventions": "intervenções", "theme": "tema", "reading_by": "leitura",
        "unknown_reader": "um leitor não identificado",
        "in_brief": "Em poucas palavras", "box": "O que é medido, o que é leitura e o que falta",
        "measured": "**Medido pela rede, sem interpretar.** Que palavras aparecem juntas, que temas formam, quantas "
                    "intervenções cada tema domina, em que anos e em que grupos, e se os temas reaparecem ao repetir o "
                    "cálculo com outras sementes e resoluções (a estabilidade). Um tema **domina** uma intervenção "
                    "quando reúne mais palavras dela do que qualquer outro tema, e pelo menos duas distintas. Não é o "
                    "mesmo que “trata de”: uma intervenção pode tocar vários temas e só um a domina.",
        "reading": "**Leitura.** Os rótulos, as definições, os enquadramentos (com as suas quatro funções: problema, "
                   "causa, avaliação e solução, segundo Entman) e a posição de cada citação (afirma, contesta ou cita "
                   "o enquadramento). Escreveu-os {reader} depois de ler o dossiê de cada tema. As {quotes} citações "
                   "deste relatório foram verificadas literalmente contra o registro ao gerá-lo e são reproduzidas "
                   "como estão no texto digitalizado, com os seus erros.",
        "missing": "**Falta.** Que uma pessoa e um agente num contexto novo codifiquem às cegas uma amostra de "
                   "passagens, para medir a sua concordância (κ de Cohen) e o peso de cada tema e enquadramento com o "
                   "seu intervalo.",
        "missing_sample": " A amostra tem {n} passagens.",
        "missing_few": " Nela, {themes} têm menos de {m} passagens cada um: para medi-los seria preciso uma amostra "
                       "maior.",
        "missing_few_1": " Nela, {themes} tem menos de {m} passagens: para medi-lo seria preciso uma amostra maior.",
        "kappa": "**Medido depois.** Uma pessoa e um agente codificaram às cegas {n} passagens: concordância no tema, "
                 "κ = {kt}; no enquadramento, κ = {kf}. Os pesos de cada tema e enquadramento, com o seu intervalo, "
                 "estão em {file}.",
        "h_weight": "Quanto pesa cada tema?", "h_years": "Quando se falou de cada tema?", "h_themes": "Os temas",
        "h_groups": "Quem fala de quê?", "h_residual": "O que fica de fora", "h_method": "Como foi feito",
        "h_next": "Próximos passos", "h_files": "Anexo: de onde vem cada coisa",
        "f_weight": "Intervenções que cada tema domina",
        "f_weight_sub": "De {N} intervenções. A barra de cima é o todo, em três partes; abaixo, cada tema.",
        "f_years": "Parte das intervenções de cada ano que cada tema domina",
        "f_years_sub": "Em %. Abaixo de cada ano, quantas intervenções tem.",
        "f_groups": "Parte das intervenções de cada grupo que cada tema domina",
        "f_groups_sub": "Em %. Grupos ({col}) com {m} intervenções ou mais; abaixo de cada um, quantas tem.",
        "n_years_hidden": "Anos com menos de {m} intervenções, que não se mostram: {list}. ",
        "n_cells": "As células vazias não têm nenhuma intervenção dominada pelo tema. Classes por quintis; rotula-se "
                   "o valor mais alto de cada linha.",
        "n_groups": "Uma parte alta pode dever-se a poucos oradores muito ativos, e um grupo pequeno apoia-se em "
                    "poucos casos. ",
        "source": "Fonte: {file} ({library}, {country}). Calculado por {engine} em {day}.",
        "seg": ("Temas", "Artefatos", "Nenhum tema"), "table": "Ver os dados numa tabela",
        "col_theme": "Tema", "col_n": "Intervenções", "col_share": "Parte",
        "seat_theme": "tema {k} · {d} intervenções ({p}) · {c} delas em {y} · estabilidade {s}, {lab}",
        "seat_speaker": " · um orador dá {x}",
        "stab": {"robust": "robusta", "moderate": "moderada", "fragile": "frágil"},
        "stance": {"affirms": "afirma", "contests": "contesta", "cites": "cita"},
        "frame": "Enquadramento {q0}{name}{q1}.", "careful": "Para ler com cuidado:", "terms": "Palavras do tema:",
        "residual": "Os temas que a leitura julgou artefatos dominam {r} intervenções ({rp}); em {n} ({np}) nenhum "
                    "tema domina.",
        "residual_terms": "Palavras do tema {k}: {terms}.",
        "m_library": "**A biblioteca:** {N} intervenções de “{library}” ({country}){speech}.",
        "m_speech": ", só a sua fala",
        "m_network": "**A rede de palavras:** os {vocabulary} termos mais característicos da biblioteca frente ao "
                     "resto do corpus{exclude}. Dois termos ligam-se quando aparecem juntos numa {unit} mais do que o "
                     "acaso daria (G² de Dunning ≥ {g2}) e a ligação está entre as {neighbours} mais fortes de algum "
                     "dos dois; o algoritmo de Leiden (resolução {gamma}, semente {seed}) agrupa os termos em temas.",
        "m_exclude": ", sem {terms}", "m_unit": "intervenção", "m_fragment": "janela de {n} palavras",
        "m_dossier": "**O dossiê:** para cada tema, as suas palavras, anos, grupos, estabilidade ({runs} repetições "
                     "de Leiden) e uma amostra de intervenções para ler, com passagens cortadas do registro.",
        "m_codebook": "**A leitura:** o codebook, com veredito, rótulo, definição, o que se inclui e o que não, "
                      "enquadramentos e citações literais com a sua posição.",
        "m_check": "**A verificação:** `check_codebook` verifica cada citação contra o registro e tira a amostra que "
                   "será codificada às cegas.",
        "m_report": "**Este relatório:** a interpretação é de quem leu; `theme_report` calcula cada número a partir da "
                    "rede, toma cada citação do codebook e volta a verificá-la contra o registro.",
        "data": "**Dados.** {citation}. Os identificadores das citações são os dessa versão: noutra versão não designam "
                "a mesma intervenção.",
        "files": ("O quê", "Arquivo"),
        "file_rows": ("Rede de palavras", "Codebook", "Verificação do codebook", "Texto do relatório (de quem lê)"),
        "mode": ("Modo: do sistema", "Modo: escuro", "Modo: claro"),
    },
    "en": {
        "thousands": ",", "decimal": ".", "pct": "%", "q": ("“", "”"), "and": "and", "nor": "or",
        "interventions": "interventions", "theme": "theme", "reading_by": "reading",
        "unknown_reader": "an unidentified reader",
        "in_brief": "In brief", "box": "What is measured, what is reading and what is missing",
        "measured": "**Measured by the network, not interpreted.** Which words occur together, which themes they form, "
                    "how many interventions each theme dominates, in which years and groups, and whether the themes "
                    "come back when the clustering is run again with other seeds and resolutions (stability). A theme "
                    "**dominates** an intervention when it holds more of its words than any other theme, and at least "
                    "two distinct ones. That is not “is about”: an intervention can touch several themes and only one "
                    "dominates it.",
        "reading": "**Reading.** The labels, the definitions, the frames (with their four functions: problem, cause, "
                   "evaluation and remedy, after Entman) and each quote's stance (affirms, contests or cites the "
                   "frame). They were written by {reader} after reading each theme's dossier. The {quotes} quotes of "
                   "this report were checked verbatim against the record when it was built and are reproduced as "
                   "they stand in the digitised text, errors included.",
        "missing": "**Missing.** A blind coding of a sample of passages by a person and by an agent in a fresh context, "
                   "to measure their agreement (Cohen's κ) and each theme's and frame's share with its interval.",
        "missing_sample": " The sample has {n} passages.",
        "missing_few": " In it, {themes} have fewer than {m} passages each: measuring them needs a larger sample.",
        "missing_few_1": " In it, {themes} has fewer than {m} passages: measuring it needs a larger sample.",
        "kappa": "**Measured since.** A person and an agent coded {n} passages blind: agreement on the theme, "
                 "κ = {kt}; on the frame, κ = {kf}. Each theme's and frame's share, with its interval, is in {file}.",
        "h_weight": "How much does each theme weigh?", "h_years": "When was each theme debated?",
        "h_themes": "The themes", "h_groups": "Who speaks about what?", "h_residual": "What is left out",
        "h_method": "How it was made", "h_next": "Next steps", "h_files": "Annex: where each thing comes from",
        "f_weight": "Interventions each theme dominates",
        "f_weight_sub": "Of {N} interventions. The top bar is the whole, in three parts; below, each theme.",
        "f_years": "Share of each year's interventions that each theme dominates",
        "f_years_sub": "In %. Under each year, how many interventions it has.",
        "f_groups": "Share of each group's interventions that each theme dominates",
        "f_groups_sub": "In %. Groups ({col}) with {m} interventions or more; under each, how many it has.",
        "n_years_hidden": "Years with fewer than {m} interventions, not shown: {list}. ",
        "n_cells": "Empty cells have no intervention dominated by the theme. Classes by quintiles; the highest value "
                   "of each row is labelled.",
        "n_groups": "A high share can come from a few very active speakers, and a small group rests on few cases. ",
        "source": "Source: {file} ({library}, {country}). Computed by {engine} on {day}.",
        "seg": ("Themes", "Artefacts", "No theme"), "table": "See the data as a table",
        "col_theme": "Theme", "col_n": "Interventions", "col_share": "Share",
        "seat_theme": "theme {k} · {d} interventions ({p}) · {c} of them in {y} · stability {s}, {lab}",
        "seat_speaker": " · one speaker gives {x}",
        "stab": {"robust": "robust", "moderate": "moderate", "fragile": "fragile"},
        "stance": {"affirms": "affirms", "contests": "contests", "cites": "cites"},
        "frame": "Frame {q0}{name}{q1}.", "careful": "Read with care:", "terms": "The theme's words:",
        "residual": "The themes the reading judged artefacts dominate {r} interventions ({rp}); no theme dominates "
                    "{n} ({np}).",
        "residual_terms": "Words of theme {k}: {terms}.",
        "m_library": "**The library:** {N} interventions of “{library}” ({country}){speech}.",
        "m_speech": ", their speech only",
        "m_network": "**The word network:** the library's {vocabulary} most characteristic terms against the rest of "
                     "the corpus{exclude}. Two terms are linked when they occur together in an {unit} more than chance "
                     "would give (Dunning's G² ≥ {g2}) and the link is among the {neighbours} strongest of either; "
                     "the Leiden algorithm (resolution {gamma}, seed {seed}) clusters the terms into themes.",
        "m_exclude": ", without {terms}", "m_unit": "intervention", "m_fragment": "window of {n} words",
        "m_dossier": "**The dossier:** for each theme, its words, years, groups, stability ({runs} Leiden re-runs) and "
                     "a sample of interventions to read, with passages cut from the record.",
        "m_codebook": "**The reading:** the codebook, with verdict, label, definition, what is included and what is "
                      "not, frames and verbatim quotes with their stance.",
        "m_check": "**The check:** `check_codebook` verifies every quote against the record and draws the sample to "
                   "code blind.",
        "m_report": "**This report:** the interpretation is the reader's; `theme_report` computes every figure from the "
                    "network, takes every quote from the codebook and checks it again against the record.",
        "data": "**Data.** {citation}. The quotes' identifiers are those of that version: in another version they do "
                "not name the same intervention.",
        "files": ("What", "File"),
        "file_rows": ("Word network", "Codebook", "Codebook check", "Report text (the reader's)"),
        "mode": ("Mode: system", "Mode: dark", "Mode: light"),
    },
}
LANGUAGES = tuple(L10N)


class _Unknown(ValueError):
    pass


# ── the codebook, the network and what the report can say ────────────────────

def _load(codebook: str, group_by: str) -> tuple:
    cpath = themes._absolute(codebook, "codebook")
    raw = cpath.read_bytes()
    try:
        cb = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"{cpath.name} is not JSON: {e}") from e
    if cb.get("schema") != themes.SCHEMA:
        raise ValueError(f"{cpath.name} is not a codebook ({themes.SCHEMA})")
    npath, net = themes._load_network(str((cb.get("network") or {}).get("file") or ""))
    if (cb.get("network") or {}).get("checksums") != net["checksums"]:
        raise ValueError(f"{npath.name} is no longer the network this codebook was written for (checksums differ)")
    entries = {e.get("theme"): e for e in cb.get("themes") or [] if isinstance(e, dict)}
    ids = [t["id"] + 1 for t in net["themes"]]
    missing = [k for k in ids if not (entries.get(k) or {}).get("verdict")]
    if missing:
        raise ValueError(f"theme(s) {missing} have no verdict: finish the codebook and check it with check_codebook "
                         "before writing the report")
    odd = [k for k in ids if entries[k]["verdict"] not in ("theme", "artefact")]
    if odd:
        raise ValueError(f"theme(s) {odd} are 'merge' or 'split': resolve them in the codebook first (the report's "
                         "figures are the network's themes; to count two subjects apart, build the network again)")
    docs = themes._rebuild(net, group_by)
    return cpath, hashlib.sha256(raw).hexdigest(), cb, npath, net, entries, docs


def _periods(iso: str, docs: list[dict]) -> dict[str, str]:
    ids = [str(d["id_int"]) for d in docs]
    _, rows, _ = store.run_query("SELECT id_int, legislature FROM interventions WHERE country = ? AND id_int IN "
                                 "(SELECT unnest(?::VARCHAR[]))", [iso, ids], max_rows=len(ids) + 5)
    return {str(i): str(p) for i, p in rows if p not in (None, "")}


def _facts(net: dict, entries: dict, docs: list[dict]) -> dict:
    ids = [t["id"] + 1 for t in net["themes"]]
    per = _periods(net["country"], docs)
    F = {"N": len(docs), "ids": ids, "subjects": [k for k in ids if entries[k]["verdict"] == "theme"],
         "artefacts": [k for k in ids if entries[k]["verdict"] == "artefact"],
         "dom": Counter(), "years": Counter(), "groups": Counter(), "periods": Counter(),
         "by_year": {k: Counter() for k in [0] + ids}, "by_group": {k: Counter() for k in [0] + ids},
         "by_period": {k: Counter() for k in [0] + ids},
         "touching": {t["id"] + 1: t["interventions"] for t in net["themes"]}}
    for d in docs:
        k = d["dominant"] + 1                                   # 0: no theme dominates
        p = per.get(str(d["id_int"]))
        F["dom"][k] += 1
        F["years"][d["year"]] += 1
        F["groups"][d["group"]] += 1
        F["by_year"][k][d["year"]] += 1
        F["by_group"][k][d["group"]] += 1
        if p:
            F["periods"][p] += 1
            F["by_period"][k][p] += 1
    stab = themes._stability(net, STABILITY_RUNS)
    F["stability"] = {k: stab[k - 1] for k in ids}
    F["concentration"] = {k: themes._concentration([d for d in docs if d["dominant"] == k - 1]) for k in ids}
    F["covered"] = sum(F["dom"][k] for k in F["subjects"])
    F["residual"] = sum(F["dom"][k] for k in F["artefacts"])
    F["none"] = F["dom"][0]
    return F


def _int(x: int, L: dict) -> str:
    return f"{x:,}".replace(",", L["thousands"])


def _dec(x: float, k: int, L: dict) -> str:
    return f"{x:.{k}f}".replace(".", L["decimal"])


def _pct(a: float, b: float, k: int, L: dict) -> str:
    return _dec(100 * a / b if b else 0.0, k, L) + L["pct"]


def _themes_of(arg: str, F: dict) -> list[int]:
    try:
        ks = [int(x) for x in str(arg).split("+")]
    except ValueError:
        raise _Unknown(f"needs theme numbers ({arg!r})") from None
    bad = [k for k in ks if k not in F["ids"]]
    if bad:
        raise _Unknown(f"names theme(s) {bad}, not in the network (1-{len(F['ids'])})")
    return ks


def _value(name: str, args: list[str], F: dict, L: dict) -> str:
    """The text of one placeholder; _Unknown if the engine has no such figure."""
    need = {"N": 0, "covered": 0, "covered_pct": 0, "residual": 0, "residual_pct": 0, "none": 0, "none_pct": 0,
            "dominated": 1, "dominated_pct": 1, "dominated_pct_covered": 1, "touching_pct": 1, "stability": 1,
            "top_speaker": 1, "peak_year": 1, "peak_count": 1, "speakers": 1, "year_n": 1, "group_n": 1,
            "period_n": 1, "year": 2, "year_count": 2, "group": 2, "group_count": 2, "period": 2, "period_count": 2}
    if name not in need:
        raise _Unknown("is not a placeholder of the report (see _placeholders in the template)")
    if len(args) != need[name]:
        raise _Unknown(f"takes {need[name]} argument(s) after ':'")
    N = F["N"]
    if name == "N":
        return _int(N, L)
    if name in ("covered", "residual", "none"):
        return _int(F[name], L)
    if name in ("covered_pct", "residual_pct", "none_pct"):
        return _pct(F[name[:-4]], N, 0, L)
    for key, count in (("year_n", "years"), ("group_n", "groups"), ("period_n", "periods")):
        if name == key:
            if args[0] not in F[count]:
                raise _Unknown(f"names {args[0]!r}, which has no interventions in the library")
            return _int(F[count][args[0]], L)
    ks = _themes_of(args[0], F)
    d = sum(F["dom"][k] for k in ks)
    if name == "dominated":
        return _int(d, L)
    if name == "dominated_pct":
        return _pct(d, N, 0, L)
    if name == "dominated_pct_covered":
        return _pct(d, F["covered"], 0, L)
    if len(ks) > 1 and name not in ("year", "year_count", "group", "group_count", "period", "period_count"):
        raise _Unknown("takes one theme")
    k = ks[0]
    if name == "touching_pct":
        return _pct(F["touching"][k], N, 0, L)
    if name == "stability":
        return _dec(F["stability"][k]["mean_jaccard"], 2, L)
    if name == "top_speaker":
        return _pct(F["concentration"][k]["top_speaker_share"], 1, 0, L)
    if name == "speakers":
        return _int(F["concentration"][k]["speakers"], L)
    if name in ("peak_year", "peak_count"):
        by = F["by_year"][k]
        if not by:
            raise _Unknown("names a theme that dominates no intervention")
        y = max(sorted(by), key=lambda y: by[y])
        return y if name == "peak_year" else _int(by[y], L)
    table, total = {"year": ("by_year", "years"), "year_count": ("by_year", "years"),
                    "group": ("by_group", "groups"), "group_count": ("by_group", "groups"),
                    "period": ("by_period", "periods"), "period_count": ("by_period", "periods")}[name]
    at = args[1]
    if at not in F[total]:
        raise _Unknown(f"names {at!r}, which has no interventions in the library")
    c = sum(F[table][j][at] for j in ks)
    return _int(c, L) if name.endswith("_count") else _pct(c, F[total][at], 1, L)


def _placeholders(F: dict, L: dict) -> dict[str, str]:
    keys = ["N", "covered", "covered_pct", "residual", "residual_pct", "none", "none_pct"]
    for k in F["ids"]:
        keys += [f"{x}:{k}" for x in ("dominated", "dominated_pct", "dominated_pct_covered", "touching_pct",
                                      "stability", "top_speaker", "speakers")]
        if F["by_year"][k]:
            keys += [f"peak_year:{k}", f"peak_count:{k}"]
        keys += [f"{x}:{k}:{y}" for y in sorted(F["years"]) for x in ("year", "year_count")]
        keys += [f"{x}:{k}:{g}" for g in sorted(F["groups"]) for x in ("group", "group_count")]
        keys += [f"{x}:{k}:{p}" for p in sorted(F["periods"]) for x in ("period", "period_count")]
    keys += [f"year_n:{y}" for y in sorted(F["years"])] + [f"group_n:{g}" for g in sorted(F["groups"])]
    keys += [f"period_n:{p}" for p in sorted(F["periods"])]
    out = {}
    for key in keys:
        name, *args = key.split(":", 2)
        out["{" + key + "}"] = _value(name, args, F, L)
    return out


def _anchors(entry: dict, frame: str | None = None) -> list[dict]:
    """The anchors a quote can name: a frame's, or (frame None) the theme's and all its frames'."""
    out = []
    if frame is None:
        out += [{**a, "stance": None} for a in entry.get("anchors") or []]
    for fr in entry.get("frames") or []:
        if frame is None or themes._norm(fr.get("name")).lower() == themes._norm(frame).lower():
            out += [{**a, "stance": a.get("stance") if frame is not None else None} for a in fr.get("anchors") or []]
    return out


def _starts(quote: str, n: int = 8) -> str:
    return " ".join(themes._norm(quote).split()[:n])


def _short(entry: dict) -> str:
    lab = themes._norm(entry.get("label")) or themes._norm(entry.get("page_label")) or f"{entry.get('theme')}"
    return re.split(r"[:,;(]", lab)[0].strip()


def _core_terms(net: dict, k: int, n: int = 15) -> list[str]:
    t = next(t for t in net["themes"] if t["id"] == k - 1)
    return [x["display"] for x in t["terms"][:n]]


# ── the template ──────────────────────────────────────────────────────────────

HELP = {
    "prose": "Write every text in the report's language. **bold** and `code` are kept; nothing else is markup.",
    "numbers": "A figure is a placeholder that the engine fills: {dominated:3}, {dominated_pct:3}, {year:4:1934} "
               "(share of that year's interventions), {group:3:<group>}, {period:5:<legislature>}, {dominated:3+2} "
               "(several themes). _placeholders lists them all with their current values. A bare number is reported "
               "as a warning: the engine cannot vouch for it (years, ordinals such as 6.ª and a theme's number after "
               "the word theme are let through).",
    "figures": "min_year and min_group leave out of the heatmaps the years and groups with fewer interventions (the "
               "note under each figure lists them). labels gives a group a shorter column head, {\"<group>\": "
               "\"<head>\"}, two lines of about 11 characters at most (\\n breaks the line); the tables keep the "
               "full names.",
    "quotes": "A quote is a reference to an anchor of the codebook: its id_int, or {\"id\": id_int, \"starts\": "
              "\"its first words\"} when the intervention has two anchors there. In a frame, that frame's anchors; "
              "in a theme's lines, the theme's or any of its frames'; in residual, those of the artefacts. "
              "_quotable lists them.",
    "engine": "The engine writes the seat lines, the box on what is measured and what is reading, the figures and "
              "their titles, each theme's words, the method, the citation and the files. omit_terms drops words "
              "from the lists of a theme's words (a name that slipped into the vocabulary).",
    "themes": "blocks orders the codable themes (each once); for each one: short (the figures' label, at most 32 "
              "characters), about (what the theme is), lines (paragraphs, each with quotes), frames (each frame of "
              "the codebook to discuss: frame, text, quotes) and caveat (needed when the theme is moderate or "
              "fragile or one speaker gives a fifth or more of it). residual: short (the figures' label for what "
              "the artefacts hold, in the reader's words; by default the word artefacts) and lines.",
}


def _template(cpath: Path, sha: str, cb: dict, net: dict, entries: dict, F: dict, group_by: str, lang: str) -> dict:
    L = L10N[lang]
    quotable = []
    for k in F["ids"]:
        e = entries[k]
        quotable.append({"theme": k, "verdict": e["verdict"], "label": e.get("label") or e.get("page_label"),
                         "anchors": [{"id": a.get("id_int"), "starts": _starts(a.get("quote"))}
                                     for a in e.get("anchors") or []],
                         "frames": [{"name": fr.get("name"),
                                     "anchors": [{"id": a.get("id_int"), "starts": _starts(a.get("quote")),
                                                  "stance": a.get("stance")} for a in fr.get("anchors") or []]}
                                    for fr in e.get("frames") or []]})
    return {
        "schema": SCHEMA,
        "codebook": {"file": str(cpath), "sha256": sha},
        "group_by": group_by, "language": lang,
        "figures": {"min_year": 10, "min_group": 30, "labels": {}},
        "reader": {k: (cb.get("reader") or {}).get(k, "") for k in ("who", "model", "date")},
        "omit_terms": [],
        "title": "", "lede": "", "findings": [""],
        "after_figures": {"weight": "", "years": "", "groups": ""},
        "blocks": [{"title": "", "themes": F["subjects"]}],
        "themes": {str(k): {"short": _short(entries[k]), "about": "", "lines": [],
                            "frames": [{"frame": fr.get("name"), "text": "", "quotes": []}
                                       for fr in entries[k].get("frames") or []], "caveat": ""}
                   for k in F["subjects"]},
        "residual": {"short": "", "lines": []},
        "method_notes": [], "next_steps": [""],
        "_help": HELP,
        "_quotable": quotable,
        "_placeholders": _placeholders(F, L),
    }


# ── checking the spec ─────────────────────────────────────────────────────────

class _Spec:
    """Fills the prose (placeholders, bare numbers, names) and resolves the quotes, collecting errors and
    warnings with where they are."""

    def __init__(self, F: dict, L: dict, docs: dict):
        self.F, self.L, self.docs = F, L, docs
        self.errors, self.warnings, self.placeholders, self.quotes = [], [], 0, []

    def text(self, value, where: str, required: bool = False) -> str:
        if value is not None and not isinstance(value, str):
            self.errors.append(f"{where}: must be text")
            return ""
        s = themes._norm(value)
        if required and not s:
            self.errors.append(f"{where}: is empty")
        rest = PLACEHOLDER.sub(" ", s)
        for m in NUMBER.finditer(rest):
            n, before = m.group(), rest[:m.start()].rstrip().lower()
            if before.endswith((self.L["theme"], self.L["theme"] + "s")):          # a theme's number, not a figure
                continue
            if not (re.fullmatch(r"\d{4}", n) and 1500 <= int(n) <= 2100):
                self.warnings.append(f"{where}: the number {n} is not a placeholder (the engine cannot vouch for it)")
        self._names(s, where)

        def fill(m):
            try:
                v = _value(m.group(1), [a for a in m.group(2).split(":")[1:]], self.F, self.L)
            except _Unknown as e:
                self.errors.append(f"{where}: {m.group(0)} {e}")
                return m.group(0)
            self.placeholders += 1
            return v
        done = PLACEHOLDER.sub(fill, s)
        for m in re.finditer(r"\{[^{}]*\}", PLACEHOLDER.sub(" ", s)):
            self.errors.append(f"{where}: {m.group(0)} is not a placeholder (name:theme:value, see _placeholders)")
        return done

    def _names(self, s: str, where: str) -> None:
        for m in ADDRESS.finditer(s):
            words = (m.group(1) or m.group(2) or "").split()
            if {w.lower() for w in words} - ROLES - {"de", "la", "los", "las", "da", "do", "dos"}:
                self.warnings.append(f"{where}: {m.group(0).strip()!r} may name a person")

    def quote(self, ref, pool: list[dict], where: str) -> dict | None:
        if isinstance(ref, str):
            ref = {"id": ref}
        if not isinstance(ref, dict) or not (ref.get("id") or ref.get("id_int")):
            self.errors.append(f"{where}: a quote is an id_int or {{\"id\": …, \"starts\": …}}")
            return None
        i, starts = str(ref.get("id") or ref.get("id_int")), themes._norm(ref.get("starts"))
        cands = [a for a in pool if str(a.get("id_int")) == i]
        if starts:
            cands = [a for a in cands if co.fold(themes._norm(a.get("quote"))).startswith(co.fold(starts))]
        if not cands:
            self.errors.append(f"{where}: {i} is not an anchor here" + (f" starting {starts!r}" if starts else "")
                               + " (see _quotable)")
            return None
        if len({themes._norm(a.get("quote")) for a in cands}) > 1:
            self.errors.append(f"{where}: {i} has {len(cands)} anchors here: add 'starts' with the first words")
            return None
        a, d = cands[0], self.docs.get(i)
        if d is None:
            self.errors.append(f"{where}: {i} is not in the library the network was built on")
            return None
        st = themes._quote_status(a.get("quote"), d["text"])
        if st != "verbatim":
            self.errors.append(f"{where}: the anchor's quote in {i} is {st} in the record (check the codebook)")
            return None
        self._names(themes._norm(a.get("quote")), f"{where}, quote {i}")
        seat = f"{i} · {str(d['date'])[:10] if d['date'] else '?'} · {d['group']}"
        if a.get("stance"):
            seat += f" · {self.L['stance'].get(a['stance'], a['stance'])}"
        self.quotes.append(i)
        return {"quote": themes._norm(a.get("quote")), "seat": seat}

    def quotes_of(self, refs, pool: list[dict], where: str) -> list[dict]:
        if refs is None:
            return []
        if not isinstance(refs, list):
            self.errors.append(f"{where}: quotes must be a list")
            return []
        return [q for j, r in enumerate(refs) if (q := self.quote(r, pool, f"{where}, quote {j + 1}"))]


def _texts(spec: dict, key: str, S: _Spec, where: str) -> list[str]:
    v = spec.get(key) or []
    if not isinstance(v, list):
        S.errors.append(f"{where}: must be a list of texts")
        return []
    return [t for j, x in enumerate(v) if (t := S.text(x, f"{where} {j + 1}"))]


def _lines(v, pool: list[dict], S: _Spec, where: str) -> list[tuple[str, list[dict]]]:
    if not v:
        return []
    if not isinstance(v, list):
        S.errors.append(f"{where}: must be a list of {{text, quotes}}")
        return []
    out = []
    for j, x in enumerate(v):
        w = f"{where} {j + 1}"
        if not isinstance(x, dict):
            S.errors.append(f"{w}: must be {{text, quotes}}")
            continue
        out.append((S.text(x.get("text"), w), S.quotes_of(x.get("quotes"), pool, w)))
    return out


def _read_spec(spec: dict, F: dict, entries: dict, net: dict, docs: dict, cb_sha: str, names: set[str]) -> tuple:
    """Errors, warnings and the resolved content of a spec."""
    lang = spec.get("language")
    errors = []
    if spec.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA!r}")
    if lang not in L10N:
        errors.append(f"language must be one of {', '.join(LANGUAGES)}")
        lang = "en"
    L = L10N[lang]
    S = _Spec(F, L, docs)
    S.errors += errors
    if (spec.get("codebook") or {}).get("sha256") != cb_sha:
        S.warnings.append("the codebook changed since this spec was drafted: quotes are taken from it as it is now")
    out = {"language": lang, "title": S.text(spec.get("title"), "title", True),
           "lede": S.text(spec.get("lede"), "lede", True),
           "findings": _texts(spec, "findings", S, "finding"),
           "after": {k: S.text((spec.get("after_figures") or {}).get(k), f"after_figures.{k}")
                     for k in ("weight", "years", "groups")},
           "method_notes": _texts(spec, "method_notes", S, "method note"),
           "next_steps": _texts(spec, "next_steps", S, "next step")}
    if not out["findings"]:
        S.errors.append("findings: write at least one")
    fig = spec.get("figures") or {}
    try:
        out["min_year"], out["min_group"] = int(fig.get("min_year", 10)), int(fig.get("min_group", 30))
    except (TypeError, ValueError):
        S.errors.append("figures: min_year and min_group must be whole numbers")
        out["min_year"], out["min_group"] = 10, 30
    labels = fig.get("labels") or {}
    if not isinstance(labels, dict) or not all(isinstance(v, str) and v.strip() for v in labels.values()):
        S.errors.append("figures.labels: must be {\"<group>\": \"<column head>\"}")
        labels = {}
    S.warnings += [f"figures.labels: {g!r} is not a group of {spec.get('group_by') or 'the report'}"
                   for g in labels if g not in F["groups"]]
    out["labels"] = {g: "\n".join(themes._norm(x) for x in v.split("\n")[:2]) for g, v in labels.items()}
    omit = {co.fold(str(x)) for x in spec.get("omit_terms") or []}
    out["terms"] = {k: [t for t in _core_terms(net, k) if co.fold(t) not in omit] for k in F["ids"]}
    for k in F["ids"]:
        hit = sorted(t for t in out["terms"][k] if co.fold(t) in names)
        if hit:
            S.warnings.append(f"theme {k}: {', '.join(hit)} also occur in speakers' names; if one is a name, put it "
                              "in omit_terms")
    # blocks: every codable theme once
    blocks, seen = [], Counter()
    for j, b in enumerate(spec.get("blocks") or []):
        w = f"block {j + 1}"
        if not isinstance(b, dict) or not isinstance(b.get("themes"), list):
            S.errors.append(f"{w}: must be {{title, themes}}")
            continue
        ks = []
        for k in b["themes"]:
            if k not in F["subjects"]:
                S.errors.append(f"{w}: {k!r} is not a codable theme ({F['subjects']})")
                continue
            seen[k] += 1
            ks.append(k)
        blocks.append((S.text(b.get("title"), f"{w} title"), ks))
    S.errors += [f"blocks: theme {k} is listed {n} times" for k, n in seen.items() if n > 1]
    S.errors += [f"blocks: codable theme {k} is in no block" for k in F["subjects"] if not seen[k]]
    out["blocks"] = blocks
    # each theme
    body = spec.get("themes") or {}
    if not isinstance(body, dict):
        S.errors.append("themes: must be an object keyed by theme number")
        body = {}
    S.errors += [f"themes: {k!r} is not a codable theme" for k in body if k not in {str(x) for x in F["subjects"]}]
    out["themes"] = {}
    for k in F["subjects"]:
        w, e, x = f"theme {k}", entries[k], body.get(str(k)) or {}
        short = themes._norm(x.get("short")) or _short(e)
        if len(short) > SHORT_LABEL:
            S.warnings.append(f"{w}: short has more than {SHORT_LABEL} characters; the figures' rows will be wide")
        frames = []
        for j, fr in enumerate(x.get("frames") or []):
            fw = f"{w}, frame {j + 1}"
            name = themes._norm((fr or {}).get("frame"))
            own = next((f for f in e.get("frames") or [] if themes._norm(f.get("name")).lower() == name.lower()), None)
            if own is None:
                S.errors.append(f"{fw}: {name!r} is not a frame of theme {k} in the codebook")
                continue
            frames.append((themes._norm(own.get("name")), S.text(fr.get("text"), fw, True),
                           S.quotes_of(fr.get("quotes"), _anchors(e, own.get("name")), fw)))
        told = {f[0].lower() for f in frames}
        S.warnings += [f"{w}: frame {themes._norm(f.get('name'))!r} of the codebook is not in the report"
                       for f in e.get("frames") or [] if themes._norm(f.get("name")).lower() not in told]
        caveat = S.text(x.get("caveat"), f"{w} caveat")
        st, c = F["stability"][k], F["concentration"][k]
        if not caveat and (st["label"] != "robust" or c["top_speaker_share"] >= SPEAKER_CAVEAT or c["flags"]):
            S.warnings.append(f"{w}: it is {st['label']} or one speaker gives {c['top_speaker_share']:.0%} of it, "
                              "and its caveat is empty")
        out["themes"][k] = {"label": themes._norm(e.get("label")), "short": short,
                            "about": S.text(x.get("about"), f"{w} about", True),
                            "lines": _lines(x.get("lines"), _anchors(e), S, f"{w} line"),
                            "frames": frames, "caveat": caveat}
    pool = [a for k in F["artefacts"] for a in _anchors(entries[k])]
    out["residual"] = _lines((spec.get("residual") or {}).get("lines"), pool, S, "residual line")
    short = S.text((spec.get("residual") or {}).get("short"), "residual short")
    if len(short) > SHORT_LABEL:
        S.warnings.append(f"residual short has more than {SHORT_LABEL} characters; the figure's label will be long")
    out["seg"] = (L["seg"][0], short or L["seg"][1], L["seg"][2])
    if not (spec.get("reader") or {}).get("who") and not (spec.get("reader") or {}).get("model"):
        S.warnings.append("reader: say who read the themes (who, model, date)")
    out["reader"] = spec.get("reader") or {}
    return S, out


# ── the document ──────────────────────────────────────────────────────────────

def _reader(r: dict, L: dict, day: bool = True) -> str:
    who, model, when = (themes._norm(r.get(k)) for k in ("who", "model", "date"))
    s = who or model or L["unknown_reader"]
    if who and model and model not in who:
        s += f" ({model})"
    return s + (f", {when}" if day and when else "")


def _join(items: list[str], word: str) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} {word} {items[-1]}"


def _citation(iso: str) -> str:
    f = store.country_dir(iso) / ".source.json"
    if f.exists():
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
            if rec.get("cita"):
                return rec["cita"]
        except json.JSONDecodeError:
            pass
    return networks._citation_lines([iso])[0]


def _sample(cpath: Path, F: dict, out: dict, L: dict) -> str:
    """The box's last paragraph, from check_codebook's files next to the codebook, if they are there."""
    check, key = cpath.with_name(f"{cpath.stem}_check.json"), cpath.with_name(f"{cpath.stem}_key.csv")
    rep = {}
    if check.exists():
        try:
            rep = json.loads(check.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            rep = {}
        if rep.get("codebook") != str(cpath):
            rep = {}
    ag = rep.get("agreement")
    if ag and ag.get("theme", {}).get("n"):
        k = lambda f: _dec(ag[f]["kappa"], 2, L) if ag.get(f, {}).get("kappa") is not None else "—"
        return L["kappa"].format(n=ag["theme"]["n"], kt=k("theme"), kf=k("frame"), file=f"`{check.name}`")
    s = L["missing"]
    if rep.get("sample", {}).get("size"):
        s += L["missing_sample"].format(n=rep["sample"]["size"])
        if key.exists():
            with open(key, newline="", encoding="utf-8") as fh:
                n = Counter(r.get("dominant_theme") for r in csv.DictReader(fh))
            few = [k for k in F["subjects"] if n[str(k)] < FEW_IN_SAMPLE]
            if few:
                names = [f"{L['theme']} {k} ({out['themes'][k]['short']})" for k in few]
                s += L["missing_few" if len(few) > 1 else "missing_few_1"].format(themes=_join(names, L["and"]),
                                                                               m=FEW_IN_SAMPLE)
    return s


def _document(out: dict, F: dict, net: dict, entries: dict, files: dict, cpath: Path, n_quotes: int) -> list:
    L, N = L10N[out["language"]], F["N"]
    p = net["parameters"]
    iso, lib = net["country"], (p.get("filters") or {}).get("library")
    years = sorted(y for y in F["years"] if y != "?")
    doc = []
    add = lambda *x: doc.append(x)
    add("seat", f"{profile.ACTIVE.title} · {lib} · {iso} · {_int(N, L)} {L['interventions']}"
                + (f" ({years[0]}–{years[-1]})" if years else "") + f" · {Path(files['network']).name} · "
                f"{L['reading_by']}: {_reader(out['reader'], L)} · parlaibero-mcp {__version__}")
    add("h1", out["title"])
    add("lede", out["lede"])
    add("h2", L["in_brief"])
    add("ul", out["findings"])
    add("box", L["box"], [L["measured"], L["reading"].format(reader=_reader(out["reader"], L, day=False), quotes=n_quotes),
                          _sample(cpath, F, out, L)])
    add("h2", L["h_weight"])
    add("figure", "weight")
    if out["after"]["weight"]:
        add("p", out["after"]["weight"])
    add("h2", L["h_years"])
    add("figure", "years")
    if out["after"]["years"]:
        add("p", out["after"]["years"])
    add("h2", L["h_themes"])
    for title, ks in out["blocks"]:
        if title:
            add("h3b", title)
        for k in ks:
            t, st, c = out["themes"][k], F["stability"][k], F["concentration"][k]
            by = F["by_year"][k]
            y = max(sorted(by), key=lambda y: by[y]) if by else "?"
            seat = L["seat_theme"].format(k=k, d=_int(F["dom"][k], L), p=_pct(F["dom"][k], N, 0, L),
                                          c=_int(by.get(y, 0), L), y=y, s=_dec(st["mean_jaccard"], 2, L),
                                          lab=L["stab"][st["label"]])
            if c["top_speaker_share"] >= SPEAKER_CAVEAT:
                seat += L["seat_speaker"].format(x=_pct(c["top_speaker_share"], 1, 0, L))
            add("h3", t["label"])
            add("seat", seat)
            add("p", t["about"])
            for text, qs in t["lines"]:
                if text:
                    add("p", text)
                for q in qs:
                    add("quote", q)
            for name, text, qs in t["frames"]:
                add("frame", L["frame"].format(q0=L["q"][0], name=name, q1=L["q"][1]), text)
                for q in qs:
                    add("quote", q)
            if t["caveat"]:
                add("careful", t["caveat"])
            add("terms", ", ".join(out["terms"][k]))
    add("h2", L["h_groups"])
    add("figure", "groups")
    if out["after"]["groups"]:
        add("p", out["after"]["groups"])
    if F["artefacts"] or F["none"]:
        add("h2", L["h_residual"])
        add("p", L["residual"].format(r=_int(F["residual"], L), rp=_pct(F["residual"], N, 0, L), n=_int(F["none"], L),
                                      np=_pct(F["none"], N, 0, L)))
        for k in F["artefacts"]:
            add("p", L["residual_terms"].format(k=k, terms=", ".join(out["terms"][k])))
        for text, qs in out["residual"]:
            if text:
                add("p", text)
            for q in qs:
                add("quote", q)
    add("h2", L["h_method"])
    exclude = p.get("exclude") or []
    unit = L["m_unit"] if p.get("unit") == "intervention" else L["m_fragment"].format(n=p.get("fragment"))
    add("ol", [L["m_library"].format(N=_int(N, L), library=lib, country=COUNTRIES.get(iso, (iso,))[0],
                                     speech=L["m_speech"] if p.get("speech_only", True) else ""),
               L["m_network"].format(vocabulary=p.get("vocabulary"), unit=unit, g2=_dec(float(p.get("g2_min") or 10.83),
                                                                                         2, L),
                                     neighbours=p.get("neighbours"), gamma=_dec(float(p.get("resolution")), 1, L),
                                     seed=p.get("seed"),
                                     exclude=L["m_exclude"].format(terms=_join([f"{L['q'][0]}{x}{L['q'][1]}"
                                                                                   for x in exclude], L["nor"]))
                                     if exclude else ""),
               L["m_dossier"].format(runs=STABILITY_RUNS), L["m_codebook"], L["m_check"], L["m_report"]])
    for x in out["method_notes"]:
        add("p", x)
    add("p", L["data"].format(citation=_citation(iso)))
    if out["next_steps"]:
        add("h2", L["h_next"])
        add("ul", out["next_steps"])
    add("h2", L["h_files"])
    add("files", [(L["file_rows"][j], files[k]) for j, k in enumerate(("network", "codebook", "check", "spec"))
                  if files.get(k)])
    return doc


# ── figures ───────────────────────────────────────────────────────────────────

def _cuts(values) -> list[float]:
    v = sorted(x for x in values if x > 0)
    return [v[min(len(v) - 1, int(len(v) * q))] for q in (0.2, 0.4, 0.6, 0.8)] if v else [1, 1, 1, 1]


def _class(x: float, cuts: list[float]) -> int:
    return sum(x >= c for c in cuts)


def _two_lines(s: str, width: int = 11) -> tuple[str, str]:
    if "\n" in s:
        a, b = s.split("\n", 1)
        return a, b
    if len(s) <= width or " " not in s:
        return s, ""
    spaces = [i for i, ch in enumerate(s) if ch == " "]
    i = min(spaces, key=lambda i: abs(i - len(s) / 2))
    return s[:i], s[i + 1:]


def _figures(out: dict, F: dict, net: dict, files: dict, group_by: str) -> dict:
    L, N = L10N[out["language"]], F["N"]
    rows = sorted(F["subjects"], key=lambda k: (-F["dom"][k], k))
    short = {k: out["themes"][k]["short"] for k in rows}
    shown_y = [y for y in sorted(F["years"]) if y != "?" and F["years"][y] >= out["min_year"]]
    hidden_y = [y for y in sorted(F["years"]) if y not in shown_y]
    shown_g = [g for g, n in sorted(F["groups"].items(), key=lambda z: (-z[1], z[0]))
               if n >= out["min_group"] and g != themes.NO_GROUP]
    yv = {(k, y): F["by_year"][k][y] / F["years"][y] for k in rows for y in shown_y}
    gv = {(k, g): F["by_group"][k][g] / F["groups"][g] for k in rows for g in shown_g}
    source = L["source"].format(file=Path(files["network"]).name, library=(net["parameters"].get("filters") or {})
                                .get("library"), country=net["country"], engine=f"parlaibero-mcp {__version__}",
                                day=date.today().isoformat())
    hide = L["n_years_hidden"].format(m=out["min_year"], list=", ".join(f"{y} ({F['years'][y]})" for y in hidden_y)) \
        if hidden_y else ""
    return {
        "weight": {"title": L["f_weight"], "sub": L["f_weight_sub"].format(N=_int(N, L)), "note": source,
                   "rows": rows, "short": short, "seg": out["seg"]},
        "years": {"title": L["f_years"], "sub": L["f_years_sub"], "note": hide + L["n_cells"], "rows": rows,
                  "short": short, "cols": shown_y, "n": {y: F["years"][y] for y in shown_y}, "vals": yv,
                  "cuts": _cuts(yv.values())},
        "groups": {"title": L["f_groups"], "sub": L["f_groups_sub"].format(col=group_by, m=out["min_group"]),
                   "note": L["n_groups"] + L["n_cells"], "rows": rows, "short": short, "cols": shown_g,
                   "heads": {g: out["labels"].get(g, str(g)) for g in shown_g},
                   "n": {g: F["groups"][g] for g in shown_g}, "vals": gv, "cuts": _cuts(gv.values())},
    }


# ── Markdown ──────────────────────────────────────────────────────────────────

def _md_table(head: list[str], rows: list[list[str]], left: int = 1) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" if i < left else "---:" for i in range(len(head))) + "|"]
    return "\n".join(out + ["| " + " | ".join(r) + " |" for r in rows])


def _table(key: str, fg: dict, F: dict, L: dict) -> tuple[list[str], list[list[str]]]:
    f, N = fg[key], F["N"]
    if key == "weight":
        rows = [[f["short"][k], _int(F["dom"][k], L), _pct(F["dom"][k], N, 0, L)] for k in f["rows"]]
        rows += [[f["seg"][1], _int(F["residual"], L), _pct(F["residual"], N, 0, L)],
                 [f["seg"][2], _int(F["none"], L), _pct(F["none"], N, 0, L)]]
        return [L["col_theme"], L["col_n"], L["col_share"]], rows
    head = [L["col_theme"]] + [f"{c} ({_int(f['n'][c], L)})" for c in f["cols"]]
    return head, [[f["short"][k]] + [_pct(f["vals"][k, c], 1, 1, L) for c in f["cols"]] for k in f["rows"]]


def _markdown(doc: list, fg: dict, F: dict, L: dict) -> str:
    out = []
    for kind, *x in doc:
        if kind == "seat":
            out += [f"`{x[0]}`", ""]
        elif kind == "h1":
            out += [f"# {x[0]}", ""]
        elif kind in ("h2", "h3b", "h3"):
            out += [f"{dict(h2='##', h3b='###', h3='####')[kind]} {x[0]}", ""]
        elif kind in ("lede", "p"):
            out += [x[0], ""]
        elif kind == "ul":
            out += [f"- {t}" for t in x[0]] + [""]
        elif kind == "ol":
            out += [f"{i}. {t}" for i, t in enumerate(x[0], 1)] + [""]
        elif kind == "box":
            out += [f"> **{x[0]}**", ">"] + [y for t in x[1] for y in (f"> {t}", ">")][:-1] + [""]
        elif kind == "figure":
            f = fg[x[0]]
            head, rows = _table(x[0], fg, F, L)
            out += [f"**{f['title']}.** {f['sub']}", "", _md_table(head, rows), "", f"*{f['note']}*", ""]
        elif kind == "frame":
            out += [f"**{x[0]}** {x[1]}", ""]
        elif kind == "quote":
            out += [f"> {L['q'][0]}{x[0]['quote']}{L['q'][1]}", f"> `{x[0]['seat']}`", ""]
        elif kind == "careful":
            out += [f"*{L['careful']}* {x[0]}", ""]
        elif kind == "terms":
            out += [f"{L['terms']} {x[0]}.", ""]
        elif kind == "files":
            out += [_md_table(list(L["files"]), [[a, f"`{b}`"] for a, b in x[0]], left=2), ""]
    return "\n".join(out).rstrip() + "\n"


# ── HTML ──────────────────────────────────────────────────────────────────────

def _inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    return re.sub(r"`(.+?)`", r"<code>\1</code>", s)


def _fmt(x: float, L: dict) -> str:
    return _dec(100 * x, 1, L)


def _least(W: int) -> int:
    """The narrowest a figure is drawn: below three quarters of its size its labels would be too small to read,
    so the figure scrolls sideways instead."""
    return max(520, round(.75 * W))


def _svg_weight(f: dict, F: dict, L: dict) -> str:
    W, LW, BW, N = 760, 260, 410, F["N"]
    rows, top, rh, bh = f["rows"], 96, 30, 14
    H = top + rh * len(rows) + 8
    o = [f'<svg viewBox="0 0 {W} {H}" style="min-width:{_least(W)}px" role="img" '
         f'aria-label="{html.escape(f["title"])}">']
    x = 0.0
    parts = [(f["seg"][0], F["covered"], "seg-theme"), (f["seg"][1], F["residual"], "seg-art"),
             (f["seg"][2], F["none"], "seg-none")]
    for j, (name, v, cls) in enumerate(parts):
        w = (W - 2) * v / N if N else 0
        if v:
            o.append(f'<rect class="{cls}" x="{x + 1:.1f}" y="8" width="{max(w - 2, 1):.1f}" height="22" rx="2" '
                     f'data-tip="{html.escape(name)}: {_int(v, L)} ({_pct(v, N, 0, L)})"/>')
            tx, ta = (x + w - 1, "end") if j == len(parts) - 1 else (x + 1, "start")
            o.append(f'<text x="{tx:.1f}" y="48" text-anchor="{ta}">{html.escape(name)}</text>')
            o.append(f'<text class="val" x="{tx:.1f}" y="66" text-anchor="{ta}">{_int(v, L)} · {_pct(v, N, 0, L)}</text>')
        x += w
    o.append(f'<line class="rule" x1="0" x2="{W}" y1="80" y2="80"/>')
    mx = max([F["dom"][k] for k in rows] + [1])
    for i, k in enumerate(rows):
        y, w = top + i * rh, BW * F["dom"][k] / mx
        o.append(f'<text x="{LW - 10}" y="{y + rh / 2 + 4}" text-anchor="end">{html.escape(f["short"][k])}</text>')
        o.append(f'<rect class="bar" x="{LW}" y="{y + (rh - bh) / 2}" width="{max(w, 1):.1f}" height="{bh}" rx="2" '
                 f'data-tip="{html.escape(f["short"][k])}: {_int(F["dom"][k], L)} ({_pct(F["dom"][k], F["N"], 0, L)})"/>')
        o.append(f'<text class="val" x="{LW + w + 8:.1f}" y="{y + rh / 2 + 4}">{_int(F["dom"][k], L)}</text>')
    o.append("</svg>")
    return "".join(o)


def _svg_heat(f: dict, L: dict) -> str:
    heads = {c: _two_lines(f.get("heads", {}).get(c, str(c))) for c in f["cols"]}
    longest = max([len(s) for a, b in heads.values() for s in (a, b)] + [4])
    cw, ch, lw = min(100, max(56, 7 * longest + 14)), 32, 250
    W, top = lw + cw * len(f["cols"]) + 4, 56
    H = top + ch * len(f["rows"]) + 4
    o = [f'<svg viewBox="0 0 {W} {H}" style="min-width:{_least(W)}px" role="img" '
         f'aria-label="{html.escape(f["title"])}">']
    for j, c in enumerate(f["cols"]):
        cx = lw + j * cw + cw / 2
        a, b = heads[c]
        o.append(f'<text x="{cx}" y="{14 if b else 28}" text-anchor="middle">{html.escape(a)}</text>')
        if b:
            o.append(f'<text x="{cx}" y="28" text-anchor="middle">{html.escape(b)}</text>')
        o.append(f'<text class="n" x="{cx}" y="46" text-anchor="middle">{_int(f["n"][c], L)}</text>')
    for i, k in enumerate(f["rows"]):
        y = top + i * ch
        row = [f["vals"][k, c] for c in f["cols"]]
        peak = max(range(len(row)), key=lambda j: row[j]) if row and max(row) > 0 else -1
        o.append(f'<text x="{lw - 10}" y="{y + ch / 2 + 4}" text-anchor="end">{html.escape(f["short"][k])}</text>')
        for j, c in enumerate(f["cols"]):
            v, x = row[j], lw + j * cw
            tip = html.escape(f"{f['short'][k]} · {c}: {_pct(v, 1, 1, L)}")
            if v == 0:
                o.append(f'<rect class="empty" x="{x + 1.5}" y="{y + 1.5}" width="{cw - 3}" height="{ch - 3}" rx="1" '
                         f'data-tip="{tip}"/>')
                continue
            q = _class(v, f["cuts"])
            o.append(f'<rect class="s{q}" x="{x + 1}" y="{y + 1}" width="{cw - 2}" height="{ch - 2}" rx="1" '
                     f'data-tip="{tip}"/>')
            if j == peak:
                o.append(f'<text class="cell t{q}" x="{x + cw / 2}" y="{y + ch / 2 + 4}" text-anchor="middle">'
                         f'{_fmt(v, L)}</text>')
    o.append("</svg>")
    return "".join(o)


def _legend(f: dict, L: dict) -> str:
    vals = [v for v in f["vals"].values() if v > 0]
    if not vals:
        return ""
    edges = [min(vals)] + f["cuts"] + [max(vals)]
    items = ['<span class="key"><i class="sw empty"></i>0</span>']
    items += [f'<span class="key"><i class="sw s{c}"></i>{_fmt(edges[c], L)}–{_fmt(edges[c + 1], L)}</span>'
              for c in range(5)]
    return '<p class="legend">' + "".join(items) + "</p>"


def _html_figure(key: str, fg: dict, F: dict, L: dict) -> str:
    f = fg[key]
    if key == "weight":
        chart = _svg_weight(f, F, L)
        legend = ('<p class="legend">' + "".join(f'<span class="key"><i class="sw {c}"></i>{html.escape(n)}</span>'
                                                 for n, c in zip(f["seg"], ("seg-theme", "seg-art", "seg-none")))
                  + "</p>")
    else:
        chart, legend = _svg_heat(f, L), _legend(f, L)
    head, rows = _table(key, fg, F, L)
    table = ("<table><thead><tr>" + "".join(f'<th scope="col">{html.escape(h)}</th>' for h in head)
             + "</tr></thead><tbody>" + "".join("<tr>" + f'<th scope="row">{html.escape(r[0])}</th>'
                                                 + "".join(f"<td>{html.escape(c)}</td>" for c in r[1:]) + "</tr>"
                                                 for r in rows) + "</tbody></table>")
    return (f'<figure class="fig" id="fig-{key}"><figcaption><p class="fig-title">{html.escape(f["title"])}</p>'
            f'<p class="fig-sub">{html.escape(f["sub"])}</p></figcaption>{legend}<div class="canvas">{chart}</div>'
            f'<details class="data"><summary>{html.escape(L["table"])}</summary>{table}</details>'
            f'<p class="fig-note">{html.escape(f["note"])}</p></figure>')


CSS = """
*,*::before,*::after{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--plane);color:var(--ink);font:17px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif;
font-variant-numeric:tabular-nums}
.page{max-width:72rem;margin:0 auto;padding:clamp(1.25rem,4vw,3rem) clamp(1rem,3vw,2.5rem) 4rem}
.col{max-width:40rem;margin-inline:auto}
header.bar{display:flex;justify-content:flex-end;max-width:52rem;margin:0 auto 1rem}
button.mode{font:inherit;font-size:.9rem;color:var(--ink2);background:var(--surface);border:1px solid var(--axis);
border-radius:6px;padding:.4em .9em;min-height:2.75rem;cursor:pointer}
button.mode:hover{color:var(--ink)}
:focus-visible{outline:3px solid var(--focus);outline-offset:3px}
.seat{font:12.5px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;color:var(--ink2);margin:0 0 .75rem;
overflow-wrap:anywhere}
h1{font-size:clamp(1.9rem,1.3rem + 2.6vw,3rem);line-height:1.1;letter-spacing:-.015em;margin:0 0 1.2rem;text-wrap:balance}
h2{font-size:clamp(1.4rem,1.1rem + 1.2vw,2rem);line-height:1.2;margin:3.5rem 0 1rem;text-wrap:balance}
h3{font-size:1.2rem;line-height:1.3;margin:2.6rem 0 .4rem;text-wrap:balance}
h3.block{font-size:clamp(1.15rem,1rem + .6vw,1.45rem);color:var(--ink2);margin:3rem 0 0;padding-top:1.2rem;
border-top:1px solid var(--axis)}
.lede{font-size:1.18rem;line-height:1.5;color:var(--ink2)}
p{margin:0 0 .9rem}
ul,ol{padding-left:1.2em;margin:0 0 1rem}
li{margin-bottom:.5rem}
code{font:.85em ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:var(--surface);padding:.05em .3em;
border-radius:3px}
.box{background:var(--surface);border:1px solid var(--grid);border-left:3px solid var(--c1);padding:1.1rem 1.3rem .4rem;
margin:2.4rem 0}
.box .box-title{font-weight:650;margin-bottom:.6rem}
.frame{margin:1.3rem 0 .5rem}
blockquote{margin:.4rem 0 1.1rem;padding-left:1rem;border-left:2px solid var(--axis)}
blockquote p{font-style:italic;margin:0 0 .2rem}
blockquote .seat{margin:0;font-style:normal}
.careful{font-size:.95rem;color:var(--ink2);margin:1rem 0 .5rem}
.careful b{color:var(--ink)}
.terms{font-size:.9rem;color:var(--ink2);margin:.3rem 0 0}
.fig{margin:1.8rem auto 2.2rem;max-width:52rem}
.fig-title{font-weight:650;font-size:1.1rem;line-height:1.3;margin:0 0 .15rem}
.fig-sub{color:var(--ink2);font-size:.95rem;margin:0 0 .5rem}
.fig-note{font-size:.88rem;color:var(--ink2);margin:.5rem 0 0}
.canvas{overflow-x:auto;-webkit-overflow-scrolling:touch}
.canvas svg{display:block;width:100%;height:auto}
svg text{font:14px system-ui,-apple-system,"Segoe UI",sans-serif;fill:var(--ink2)}
svg text.val{fill:var(--ink)}
svg text.n{font:11.5px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;fill:var(--ink2)}
svg text.cell{font:12px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
svg .rule{stroke:var(--axis);stroke-width:1}
.bar,.seg-theme{fill:var(--c1)}
.seg-art{fill:var(--grid);stroke:var(--muted);stroke-width:1}
.seg-none,.empty{fill:none;stroke:var(--muted);stroke-width:1}
.s0{fill:var(--s0)}.s1{fill:var(--s1)}.s2{fill:var(--s2)}.s3{fill:var(--s3)}.s4{fill:var(--s4)}
.t0{fill:var(--t0)}.t1{fill:var(--t1)}.t2{fill:var(--t2)}.t3{fill:var(--t3)}.t4{fill:var(--t4)}
[data-tip]:hover{stroke:var(--ink);stroke-width:1.5}
.legend{display:flex;flex-wrap:wrap;gap:.35rem 1rem;font:12px ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
color:var(--ink2);margin:0 0 .5rem}
.key{display:inline-flex;align-items:center;gap:.4rem}
.sw{display:inline-block;width:.95rem;height:.75rem;border-radius:2px}
.sw.s0{background:var(--s0)}.sw.s1{background:var(--s1)}.sw.s2{background:var(--s2)}.sw.s3{background:var(--s3)}
.sw.s4{background:var(--s4)}.sw.seg-theme{background:var(--c1)}.sw.seg-art{background:var(--grid);
border:1px solid var(--muted)}.sw.seg-none,.sw.empty{border:1px solid var(--muted)}
details.data summary{cursor:pointer;color:var(--ink2);font-size:.95rem;padding:.6rem 0}
.data table,.files table{border-collapse:collapse;font-size:.9rem;width:100%;display:block;overflow-x:auto}
.data th,.data td,.files th,.files td{padding:.3rem .55rem;border-bottom:1px solid var(--grid);text-align:right;
white-space:nowrap}
.data th[scope="row"],.data thead th:first-child,.files th,.files td{text-align:left}
.files td{white-space:normal;overflow-wrap:anywhere}
.data thead th,.files thead th{font-size:.8rem;color:var(--ink2);font-weight:500}
#tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--plane);border-radius:4px;
padding:.4rem .65rem;font-size:.88rem;line-height:1.35;max-width:22rem;z-index:10}
#tip[hidden]{display:none}
@media (forced-colors:active){.bar,.seg-theme,.s0,.s1,.s2,.s3,.s4{fill:CanvasText}}
@media print{button.mode,#tip{display:none}}
"""

JS = """
(function(){
  var root=document.documentElement,b=document.querySelector('button.mode'),k='parlaibero-report-mode',
      names=JSON.parse(b.getAttribute('data-names'));
  function label(){var t=root.getAttribute('data-theme');b.textContent=t==='dark'?names[1]:t==='light'?names[2]:names[0];}
  try{var s=localStorage.getItem(k);if(s)root.setAttribute('data-theme',s);}catch(e){}
  label();
  b.addEventListener('click',function(){var t=root.getAttribute('data-theme'),n=t==='dark'?'light':t==='light'?null:'dark';
    if(n)root.setAttribute('data-theme',n);else root.removeAttribute('data-theme');
    try{n?localStorage.setItem(k,n):localStorage.removeItem(k);}catch(e){} label();});
  var tip=document.getElementById('tip');
  document.addEventListener('pointermove',function(e){var t=e.target.closest&&e.target.closest('[data-tip]');
    if(!t){tip.hidden=true;return;} tip.textContent=t.getAttribute('data-tip');tip.hidden=false;
    var x=e.clientX+14,y=e.clientY+14,w=tip.offsetWidth,h=tip.offsetHeight;
    if(x+w>innerWidth-8)x=e.clientX-w-14; if(y+h>innerHeight-8)y=e.clientY-h-14;
    tip.style.left=x+'px';tip.style.top=y+'px';});
  document.addEventListener('keydown',function(e){if(e.key==='Escape')tip.hidden=true;});
})();
"""


def _html(doc: list, fg: dict, F: dict, L: dict, lang: str, title: str) -> str:
    body, in_col = [], False
    for kind, *x in doc:
        if kind == "figure":
            if in_col:
                body.append("</div>")
                in_col = False
            body.append(_html_figure(x[0], fg, F, L))
            continue
        if not in_col:
            body.append('<div class="col">')
            in_col = True
        if kind == "seat":
            body.append(f'<p class="seat">{html.escape(x[0])}</p>')
        elif kind in ("h1", "h2", "h3"):
            body.append(f"<{kind}>{_inline(x[0])}</{kind}>")
        elif kind == "h3b":
            body.append(f'<h3 class="block">{_inline(x[0])}</h3>')
        elif kind == "lede":
            body.append(f'<p class="lede">{_inline(x[0])}</p>')
        elif kind == "p":
            body.append(f"<p>{_inline(x[0])}</p>")
        elif kind in ("ul", "ol"):
            body.append(f"<{kind}>" + "".join(f"<li>{_inline(t)}</li>" for t in x[0]) + f"</{kind}>")
        elif kind == "box":
            body.append(f'<aside class="box" aria-label="{html.escape(x[0])}"><p class="box-title">{html.escape(x[0])}'
                        "</p>" + "".join(f"<p>{_inline(t)}</p>" for t in x[1]) + "</aside>")
        elif kind == "frame":
            body.append(f'<p class="frame"><strong>{html.escape(x[0])}</strong> {_inline(x[1])}</p>')
        elif kind == "quote":
            body.append(f'<blockquote><p>{L["q"][0]}{html.escape(x[0]["quote"])}{L["q"][1]}</p>'
                        f'<p class="seat">{html.escape(x[0]["seat"])}</p></blockquote>')
        elif kind == "careful":
            body.append(f'<p class="careful"><b>{html.escape(L["careful"])}</b> {_inline(x[0])}</p>')
        elif kind == "terms":
            body.append(f'<p class="terms">{html.escape(L["terms"])} {html.escape(x[0])}</p>')
        elif kind == "files":
            body.append('<div class="files"><table><thead><tr>' + "".join(f'<th scope="col">{html.escape(h)}</th>'
                                                                         for h in L["files"]) + "</tr></thead><tbody>"
                        + "".join(f"<tr><td>{html.escape(a)}</td><td><code>{html.escape(b)}</code></td></tr>"
                                  for a, b in x[0]) + "</tbody></table></div>")
    if in_col:
        body.append("</div>")
    names = html.escape(json.dumps(list(L["mode"]), ensure_ascii=False))
    return (f'<!doctype html>\n<html lang="{lang}">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">\n'
            f'<title>{html.escape(re.sub(r"[*`]", "", title))}</title>\n'
            f"<style>{TOKENS_CSS}{CSS}</style>\n</head>\n<body>\n<div class=\"page\">\n"
            f'<header class="bar"><button class="mode" type="button" data-names="{names}">{html.escape(L["mode"][0])}'
            f"</button></header>\n<main>\n{''.join(body)}\n</main>\n</div>\n"
            f'<div id="tip" role="status" hidden></div>\n<script>{JS}</script>\n</body>\n</html>\n')


# ── theme_report ──────────────────────────────────────────────────────────────

def _shown(path: Path, base: Path) -> str:
    try:
        return os.path.relpath(path, base)
    except ValueError:
        return str(path)


def theme_report(codebook: str, report: str | None = None, group_by: str = "party", language: str | None = None,
                 output_dir: str | None = None, overwrite: bool = False) -> dict:
    """Without `report`, writes the spec template for the agent's interpretation (see the module docstring); with
    `report`, checks the spec and, without errors, renders it as Markdown and HTML."""
    if report is None:
        cpath, sha, cb, npath, net, entries, docs = _load(codebook, group_by)
        lang = language or co.language_of(net["country"])
        if lang not in L10N:
            raise ValueError(f"language must be one of {', '.join(LANGUAGES)}")
        F = _facts(net, entries, docs)
        out_dir = networks._out_dir(output_dir) if output_dir else cpath.parent
        stem = npath.stem[:-len("_words")] if npath.stem.endswith("_words") else npath.stem
        path = out_dir / f"{stem}_report.json"
        if path.exists() and not overwrite:
            raise FileExistsError(f"{path} already exists and may hold your text; pass report= to render it, or "
                                  "overwrite=true to start again")
        tpl = _template(cpath, sha, cb, net, entries, F, group_by, lang)
        networks._write(path, json.dumps(tpl, ensure_ascii=False, indent=1), True)
        return {"report": str(path), "codebook": str(cpath), "network": str(npath), "N": F["N"],
                "codable": F["subjects"], "artefacts": F["artefacts"], "help": HELP,
                "placeholders": len(tpl["_placeholders"]),
                "next": f"Write the interpretation in {path.name} (title, lede, findings, blocks, themes, residual, "
                        "next_steps), then theme_report(codebook, report=that file)."}
    spath = themes._absolute(report, "report")
    try:
        spec = json.loads(spath.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"{spath.name} is not JSON: {e}") from e
    if not isinstance(spec, dict):
        raise ValueError(f"{spath.name} is not a report spec ({SCHEMA})")
    gb = spec.get("group_by") or group_by
    cpath, sha, cb, npath, net, entries, docs = _load(codebook, gb)
    F = _facts(net, entries, docs)
    by_id = {str(d["id_int"]): d for d in docs}
    names = {w for d in docs if d["speaker_name"] for w in co.tokenize(d["speaker_name"]) if len(w) >= 3}
    S, out = _read_spec(spec, F, entries, net, by_id, sha, names)
    out_dir = networks._out_dir(output_dir) if output_dir else spath.parent
    check = cpath.with_name(f"{cpath.stem}_check.json")
    files = {"network": _shown(npath, out_dir), "codebook": _shown(cpath, out_dir),
             "check": _shown(check, out_dir) if check.exists() else None, "spec": _shown(spath, out_dir)}
    result = {"report": str(spath), "codebook": str(cpath), "network": str(npath), "codebook_sha256": sha,
              "ok": not S.errors, "errors": S.errors, "warnings": S.warnings,
              "placeholders_filled": S.placeholders, "quotes": len(S.quotes),
              "quotes_checked": "every quote is a codebook anchor found verbatim in the record now"}
    written = []
    if not S.errors:
        L = L10N[out["language"]]
        doc = _document(out, F, net, entries, files, cpath, len(S.quotes))
        fg = _figures(out, F, net, files, gb)
        written += [networks._write(out_dir / f"{spath.stem}.md", _markdown(doc, fg, F, L), True),
                    networks._write(out_dir / f"{spath.stem}.html", _html(doc, fg, F, L, out["language"],
                                                                          out["title"]), True)]
    written.append(networks._write(out_dir / f"{spath.stem}_check.json",
                                   json.dumps(result, ensure_ascii=False, indent=1), True))
    result["files"] = written
    if S.errors:
        result["next"] = ("Nothing was rendered (a .md or .html beside the spec is from an earlier run): fix the "
                          "errors in the spec (or the codebook) and run it again.")
    return result
