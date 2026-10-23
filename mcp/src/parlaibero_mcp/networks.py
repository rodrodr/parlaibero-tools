"""Network tools on a library, three kinds that are never mixed:
  - cooccurrence_network: WORDS that occur in the same intervention (or fragment), clustered into themes; the
    engine is cooccurrence.py, a port of the Diarios Explorer's;
  - comention_network: ACTORS (people and institutions) mentioned in the same intervention, by whom;
  - mention_network: who names whom on the floor (directed, between people).
General by construction: any library, any topic, any of the collection's countries; nothing about one country or
one debate is written here.

Definitions of the actor networks, fixed and recorded with every result (plan: docs/PLAN_redes.md):
  - the unit is the intervention; N = interventions of the library after the filters;
  - patterns are regular expressions over lower-case, accent-free text;
  - NPMI = ln(p(ab) / (p(a) p(b))) / −ln p(ab), and 1 when co = N; thresholds compare UNROUNDED values;
  - communities: Leiden (leiden.py, the explorer's algorithm) with a fixed seed.
"""
from __future__ import annotations

import csv
import html as html_mod
import json
import math
import random
import re
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from itertools import combinations
from pathlib import Path

from . import __version__, analysis, cooccurrence as co, leiden, profile, store
from .catalog import COUNTRIES

# Actors only: a word or an idea is a node of cooccurrence_network, never an entity here.
ENTITY_TYPES = {"persona": "persona", "person": "persona", "institucion": "institucion", "institución": "institucion",
                "institution": "institucion"}
NOT_ACTORS = {"concepto", "concept", "tema", "topic", "palabra", "word", "idea", "termo", "término", "termino"}
WORDS_NOT_HERE = ("comention_network takes actors only (people and institutions). Words, ideas and concepts are the "
                  "nodes of cooccurrence_network, which finds them from the library's own vocabulary and clusters "
                  "them into themes; do not mix the two in one network.")
MAX_ENTITIES_HARD = 400
MAX_ROWS = 200_000
TIME_BUDGET_S = 900

# Forms of address and titles, by language: configuration, not code (used to clean candidates and to
# recognise forms of address in mention_network).
TITLES = {
    "es": ["diputado", "diputada", "senador", "senadora", "señor", "señora", "senor", "senora", "señoría", "senoria",
           "honorable", "ministro", "ministra", "presidente", "presidenta", "doctor", "doctora", "don", "doña",
           "representante", "asambleísta", "asambleista", "legislador", "legisladora", "congresista", "concejal"],
    "pt": ["deputado", "deputada", "senador", "senadora", "senhor", "senhora", "excelência", "excelencia", "nobre",
           "ministro", "ministra", "presidente", "presidenta", "doutor", "doutora", "líder", "lider", "relator",
           "relatora", "vereador"],
}
# Only these license a match on a SURNAME alone ("deputado Ferreira", "la diputada Pérez"): they name a
# member of the chamber. 'presidente', 'ministro' or 'señor' do not ("presidente Fulano" is not a
# deputy surnamed Fulano); after them only a full name counts.
LEGISLATIVE_TITLES = {
    "es": ["diputado", "diputada", "representante", "congresista", "asambleista", "asambleísta",
           "legislador", "legisladora", "parlamentario", "parlamentaria"],
    "pt": ["deputado", "deputada", "parlamentar"],
}
# Honorifics: in many chambers members name each other this way ("el señor X", "a senhora X"); they
# license a surname too, and every mention records which kind of title licensed it, so precision can be
# measured separately.
# words that complete a title and are not a name ("deputado FEDERAL Fulano", "diputado NACIONAL Mengano")
TITLE_COMPLEMENTS = {"federal", "estadual", "distrital", "nacional", "provincial", "departamental", "constituinte",
                     "constituyente", "suplente", "electo", "eleito", "electa", "eleita"}
HONORIFICS = {
    "es": ["señor", "señora", "senor", "senora", "sr", "sra", "don", "doña", "dona"],
    "pt": ["senhor", "senhora", "sr", "sra", "dona"],
}
# Whether an honorific alone licenses a surname, by default, per language. MEASURED (14-oct-2026): in Spain
# 'señor X' named a member 95 times out of 96 in three samples (the one error, a regional president, is now
# caught by the 'name that goes on' rule); in Brazil 'sr./senhor X' named ministers, judges or a former president
# as often as members (18/40 right). Portugal was not measured: it inherits the Portuguese default.
# `honorifics=` overrides it.
HONORIFICS_LICENSE = {"es": True, "pt": False}
COURTESY_UNRESOLVABLE = {
    "es": [r"\bsu senoria\b", r"\bsus senorias\b", r"\bel senor diputado\b", r"\bla senora diputada\b",
           r"\bel diputado preopinante\b", r"\bmi colega\b"],
    "pt": [r"\bv\.? ?exa\b", r"\bvossa excelencia\b", r"\bnobre colega\b", r"\bnobre deputad[oa]\b(?! [a-z])",
           r"\bo orador\b"],
}


# ── text helpers ──────────────────────────────────────────────────────────────

def fold(s: str) -> str:
    """Lower case, accents removed: the text the patterns are written for (as strip_accents(lower()))."""
    return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower()) if unicodedata.category(c) != "Mn")


def fold_with_map(raw: str) -> tuple[str, list[int]]:
    """fold(raw) and, for every character of it, its position in raw (to cut KWIC from the original)."""
    out, idx = [], []
    for i, ch in enumerate(raw or ""):
        for c in unicodedata.normalize("NFD", ch.lower()):
            if unicodedata.category(c) != "Mn":
                out.append(c)
                idx.append(i)
    return "".join(out), idx


def _language(iso: str) -> str:
    return "pt" if iso in analysis.PORTUGUESE else "es"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _out_dir(output_dir: str | None) -> Path | None:
    if not output_dir:
        return None
    p = Path(output_dir).expanduser()
    if not p.is_absolute():
        raise ValueError("output_dir must be an absolute path.")
    p.mkdir(parents=True, exist_ok=True)
    return p


def _write(path: Path, data: str, overwrite: bool) -> str:
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists; pass overwrite=true to replace it")
    path.write_text(data, encoding="utf-8")
    return str(path)


def _citation_lines(isos) -> list[str]:
    loaded = store.loaded()
    return [f"{COUNTRIES[i][0]}: {profile.ACTIVE.title}, Harvard Dataverse, https://doi.org/{COUNTRIES[i][2]}"
            + (f", version {loaded.get(i, {}).get('version')}" if loaded.get(i, {}).get("version") else "")
            for i in sorted(isos)]


# ── entities ──────────────────────────────────────────────────────────────────

def _validate_entities(entities: list[dict]) -> list[dict]:
    if not entities:
        raise ValueError("entities is empty")
    if len(entities) > MAX_ENTITIES_HARD:
        raise ValueError(f"At most {MAX_ENTITIES_HARD} entities.")
    out, seen = [], set()
    for k, e in enumerate(entities):
        name = str(e.get("name") or "").strip()
        if not name:
            raise ValueError(f"entity {k + 1} has no name")
        if name in seen:
            raise ValueError(f"two entities are called {name!r}")
        seen.add(name)
        raw_type = str(e.get("type") or "").strip().lower()
        if raw_type in NOT_ACTORS:
            raise ValueError(f"{name}: type {raw_type!r}. {WORDS_NOT_HERE}")
        etype = ENTITY_TYPES.get(raw_type)
        if etype is None:
            raise ValueError(f"{name}: type must be persona or institucion")
        pat = str(e.get("pattern") or "").strip()
        if not pat:
            raise ValueError(f"{name}: empty pattern")
        exc = str(e.get("exclude") or "").strip() or None
        for label, rx in (("pattern", pat), ("exclude", exc)):
            if rx is None:
                continue
            try:
                re.compile(rx)
            except re.error as err:
                raise ValueError(f"{name}: invalid {label} {rx!r} ({err})")
            try:      # the same expression must also be valid RE2 (the prefilter runs in DuckDB)
                store.run_query("SELECT regexp_matches('', ?)", [rx])
            except Exception as err:
                raise ValueError(f"{name}: {label} {rx!r} is not valid RE2 (no look-arounds or back-references): "
                                 f"{str(err)[:120]}")
        out.append({"name": name, "type": etype, "pattern": pat, "exclude": exc,
                    "_rx": re.compile(pat), "_exc": re.compile(exc) if exc else None})
    return out


def _present(text: str, ents: list[dict], candidates: list[int]) -> set[str]:
    """Entities present in a folded text. A match inside an `exclude` match of the same entity does not
    count, and a match contained in a LONGER match of another entity does not count either (so
    'maria pereira' belongs to that entity and not to 'pereira')."""
    spans = []
    for k in candidates:
        e = ents[k]
        ex = [m.span() for m in e["_exc"].finditer(text)] if e["_exc"] else []
        for m in e["_rx"].finditer(text):
            if m.end() == m.start():
                continue
            if any(a <= m.start() < b for a, b in ex):
                continue
            spans.append((m.start(), m.end(), e["name"]))
    keep = set()
    for s in spans:
        if not any(o[2] != s[2] and o[0] <= s[0] and o[1] >= s[1] and (o[1] - o[0]) > (s[1] - s[0]) for o in spans):
            keep.add(s[2])
    return keep


# ── the library's rows ────────────────────────────────────────────────────────

def _rows(f: analysis.Filters, ents: list[dict], group_by: str | None) -> list[dict]:
    """Rows of the library with, for each, the entities whose pattern matches (RE2 prefilter in DuckDB,
    one parallel pass), the group label and the folded text."""
    params: list = []
    where = f.where(params, alias="i")
    gcol = f"i.{group_by}" if group_by else "NULL"
    flags = ", ".join(f"regexp_matches(t, ?) AS m{k}" for k in range(len(ents)))
    sql = (f"WITH r AS (SELECT i.country, i.id_int, i.id_session, i.date, i.speaker_raw, i.speaker_name, i.party, "
           f"{gcol} AS grp, strip_accents(lower(coalesce(i.text, ''))) AS t FROM interventions i WHERE true{where}) "
           f"SELECT country, id_int, id_session, date, speaker_raw, speaker_name, party, grp, t, {flags} FROM r")
    # the filters' parameters come first in the SQL text (inside the CTE), the patterns after
    cols, rows, truncated = store.run_query(sql, params + [e["pattern"] for e in ents], max_rows=MAX_ROWS,
                                            timeout_s=TIME_BUDGET_S)
    if truncated:
        raise ValueError(f"The library has more than {MAX_ROWS:,} interventions after the filters: narrow it down.")
    out = []
    nflag = len(ents)
    for r in rows:
        d = dict(zip(cols[:9], r[:9]))
        d["cand"] = [k for k in range(nflag) if r[9 + k]]
        out.append(d)
    return out


def _resolve_groups(groups: dict | None, group_by: str) -> tuple[list[str], dict[str, str]]:
    """(contrast group names, label → group) with case-insensitive labels."""
    if not groups:
        return [], {}
    if not isinstance(groups, dict):
        raise ValueError("groups must be a map {group: [labels]}, e.g. {'left': ['PT', 'PSOL'], 'right': ['PL']}")
    names = list(groups)
    if len(names) > 2:
        raise ValueError("groups takes at most two contrast groups; every other label goes to 'rest'.")
    if group_by not in profile.ACTIVE.groups():
        raise ValueError(f"group_by must be one of {', '.join(profile.ACTIVE.groups())}")
    m = {}
    for g, labels in groups.items():
        for lab in labels or []:
            key = str(lab).strip().upper()
            if key in m and m[key] != g:
                raise ValueError(f"label {lab!r} is in two groups")
            m[key] = g
    return names, m


# ── graph measures (no dependencies) ──────────────────────────────────────────

def _betweenness(nodes: list[str], edges: list[tuple[str, str, float]]) -> dict[str, float]:
    """Weighted betweenness (Brandes 2001), distance = 1 / weight, normalised to [0, 1] (undirected)."""
    import heapq
    adj = defaultdict(list)
    for a, b, w in edges:
        adj[a].append((b, 1.0 / w))
        adj[b].append((a, 1.0 / w))
    bc = dict.fromkeys(nodes, 0.0)
    for s in nodes:
        stack, pred = [], defaultdict(list)
        sigma = dict.fromkeys(nodes, 0.0)
        sigma[s] = 1.0
        dist: dict[str, float] = {}
        seen = {s: 0.0}
        q = [(0.0, 0, s)]
        c = 1
        while q:
            d, _, v = heapq.heappop(q)
            if v in dist:
                continue
            dist[v] = d
            stack.append(v)
            for u, l in sorted(adj[v]):
                du = d + l
                if u not in dist and (u not in seen or du < seen[u] - 1e-12):
                    seen[u] = du
                    heapq.heappush(q, (du, c, u))
                    c += 1
                    sigma[u] = 0.0
                    pred[u] = []
                if u not in dist and abs(du - seen[u]) <= 1e-12:
                    sigma[u] += sigma[v]
                    pred[u].append(v)
        delta = dict.fromkeys(nodes, 0.0)
        while stack:
            w = stack.pop()
            for v in pred[w]:
                delta[v] += sigma[v] / sigma[w] * (1 + delta[w])
            if w != s:
                bc[w] += delta[w]
    n = len(nodes)
    scale = 1.0 / ((n - 1) * (n - 2)) if n > 2 else 1.0
    return {v: round(b * scale, 6) for v, b in bc.items()}     # each pair counted twice (undirected) → /(n−1)(n−2)


def _npmi(co: int, na: int, nb: int, N: int) -> float:
    p = co / N
    if p >= 1:
        return 1.0
    return math.log(p / ((na / N) * (nb / N))) / (-math.log(p))


# ── ambiguity report ──────────────────────────────────────────────────────────

def _literals(pattern: str) -> list[str]:
    """Rough literal alternatives of a pattern (for the alerts): split on |, drop regex syntax."""
    out = []
    for alt in re.split(r"\|", pattern):
        lit = re.sub(r"\\[bBsSwWdD]|[\^\$\(\)\[\]\?\*\+\{\}\\.]|\d+,?\d*\}", " ", alt)
        lit = re.sub(r"\s+", " ", lit).strip()
        if lit:
            out.append(lit)
    return out


def _alerts(ents: list[dict], iso: str, date_min, date_max, raw: dict[str, str],
            present_ids: dict[str, list[str]]) -> dict[str, list[str]]:
    """Automatic warnings per entity, from rules (no hand-made list):
      - short pattern (< 5 characters) or an acronym;
      - persons and institutions: the word is mostly written in LOWER case in this library, i.e. it is
        also an ordinary word ('supremo', 'lira');
      - a surname shared by several deputies in office in the library's period."""
    surnames = Counter()
    try:
        rows = store.run_query("""SELECT DISTINCT id_dep, coalesce(last_name, speaker_name) FROM deputies
                                  WHERE country = ? AND TRY_CAST(start_date AS DATE) <= CAST(? AS DATE)
                                    AND coalesce(TRY_CAST(end_date AS DATE), DATE '2999-12-31') >= CAST(? AS DATE)""",
                               [iso, str(date_max), str(date_min)], max_rows=200_000)[1]
        for _, name in rows:
            for tok in set(re.findall(r"[a-z]+", fold(name or ""))):
                if len(tok) > 2:
                    surnames[tok] += 1
    except Exception:
        pass
    out = {}
    for e in ents:
        warn = []
        for lit in _literals(e["pattern"]):
            single = " " not in lit
            low = cap = allcaps = 0
            if single:            # how the word is written in this library: lower case, Capitalised, ALL CAPS
                rx = re.compile(r"(?<![\w])" + re.escape(lit) + r"(?![\w])")
                for i in present_ids.get(e["name"], [])[:100]:
                    text = raw.get(i) or ""
                    folded, idx = fold_with_map(text)
                    for m in rx.finditer(folded):
                        word = text[idx[m.start()]: idx[m.end() - 1] + 1]
                        if word.isupper() and len(word) > 1:
                            allcaps += 1
                        elif word[:1].isupper():
                            cap += 1
                        elif word[:1].islower():
                            low += 1
            total = low + cap + allcaps
            if len(lit.replace(" ", "")) < 5 and not (total >= 10 and allcaps / total >= 0.8):
                warn.append(f"short pattern '{lit}': check the examples")
            if single and total >= 10 and low / total > 0.5:
                warn.append(f"'{lit}' is written in lower case {round(100 * low / total)}% of the time here: "
                            f"it is also an ordinary word")
            if single and surnames.get(lit, 0) >= 2:
                warn.append(f"'{lit}' is the surname of {surnames[lit]} deputies in office in the period")
        if warn:
            out[e["name"]] = sorted(set(warn))
    return out


def _kwic(raw_texts: dict[str, str], ent: dict, ids: list[str], k: int, rng: random.Random, width: int = 90) -> list[dict]:
    pick = sorted(ids) if len(ids) <= k else sorted(rng.sample(sorted(ids), k))
    out = []
    for i in pick:
        raw = raw_texts.get(i) or ""
        folded, idx = fold_with_map(raw)
        m = ent["_rx"].search(folded)
        if not m or not idx:
            continue
        a, b = idx[m.start()], idx[min(m.end(), len(idx)) - 1] + 1
        left = re.sub(r"\s+", " ", raw[max(0, a - width):a])
        right = re.sub(r"\s+", " ", raw[b:b + width])
        out.append({"id_int": i, "left": left, "match": raw[a:b], "right": right})
    return out


def _raw_texts(ids: list[str]) -> dict[str, str]:
    out = {}
    for k in range(0, len(ids), 500):
        chunk = ids[k:k + 500]
        cols, rows, _ = store.run_query(f"SELECT id_int, text FROM interventions WHERE id_int IN "
                                        f"({', '.join('?' * len(chunk))})", chunk, max_rows=len(chunk))
        out.update({r[0]: r[1] for r in rows})
    return out


# ── comention_network: actors mentioned together ──────────────────────────────

LAYOUTS = ("force", "clusters", "rings")


def _view(max_node_size: float, max_edge_width: float, layout: str = "force") -> dict:
    """Defaults of the page's «layout», «node size» and «edge width» controls (px on screen, at any zoom)."""
    if layout not in LAYOUTS:
        raise ValueError(f"layout must be one of {', '.join(LAYOUTS)}")
    if not 4 <= max_node_size <= 40:
        raise ValueError("max_node_size must be between 4 and 40 (px of radius)")
    if not 0.5 <= max_edge_width <= 6:
        raise ValueError("max_edge_width must be between 0.5 and 6 (px)")
    return {"max_node_size": max_node_size, "max_edge_width": max_edge_width, "layout": layout}


def comention_network(f: analysis.Filters, entities: list[dict] | None = None, groups: dict | None = None,
                      group_by: str = "party", min_co: int | None = None, min_npmi: float = 0.10,
                      max_nodes: int = 60, max_entities: int = 150, kwic_per_entity: int = 5, seed: int = 1,
                      output_dir: str | None = None, formats: list[str] | None = None, overwrite: bool = False,
                      pooled: bool = False, max_candidates: int = 60, max_node_size: float = 12,
                      max_edge_width: float = 1.5, layout: str = "force") -> dict:
    """Co-mention network of actors in a library (see the module docstring for the definitions)."""
    if f.library is None:
        raise ValueError("comention_network needs a library (library=…)")
    view = _view(max_node_size, max_edge_width, layout)
    if not entities:
        return candidates(f, max_candidates, seed)
    if len(entities) > max_entities:
        raise ValueError(f"{len(entities)} entities: more than max_entities={max_entities}. Narrow the list "
                         f"(or raise max_entities up to {MAX_ENTITIES_HARD}).")
    t0 = time.time()
    ents = _validate_entities(entities)
    gnames, gmap = _resolve_groups(groups, group_by)
    rows = _rows(f, ents, group_by if gnames else "party")
    if not rows:
        raise store.NoData("The library has no interventions under these filters.")
    by_country = defaultdict(list)
    for r in rows:
        by_country["ALL" if pooled else r["country"]].append(r)
    formats = [x.lower() for x in (formats or ["html", "csv", "json", "md"])]
    out_dir = _out_dir(output_dir)
    results = {}
    for iso, part in sorted(by_country.items()):
        results[iso] = _one_network(iso, part, ents, gnames, gmap, group_by, min_co, min_npmi, max_nodes,
                                    kwic_per_entity, seed, f)
        results[iso]["parameters"]["view"] = view
    files = []
    if out_dir:
        from . import network_html
        base = store_slug(f.library_name or "library") + "_comention"
        for iso, res in results.items():
            stem = base + ("" if len(results) == 1 else f"_{iso}")
            files += _write_outputs(out_dir, stem, res, formats, overwrite, network_html.comention_page)
    summary = {iso: _summary(res) for iso, res in results.items()}
    notes = []
    if len(results) > 1:
        notes.append("One network per country (the default for a library with several countries): N, groups and bias "
                     "are computed within each chamber. pooled=true joins them.")
    if any(c in analysis.PORTUGUESE for c in by_country) and any(c not in analysis.PORTUGUESE for c in by_country):
        notes.append("Spanish- and Portuguese-language chambers: every pattern needs the forms of both languages.")
    notes += analysis._long_turn_notes(f)
    return {"library": f.library_name, "networks": summary, "files": files, "notes": notes,
            "seconds": round(time.time() - t0, 1), "datasets": analysis._versions(r["country"] for r in rows)}


def store_slug(s: str) -> str:
    from .library import slug
    return slug(s) or "library"


def _one_network(iso, rows, ents, gnames, gmap, group_by, min_co, min_npmi, max_nodes, kwic_k, seed, f) -> dict:
    N = len(rows)
    min_co_used = int(min_co) if min_co is not None else max(5, round(N / 120))
    # group of each row
    def group_of(r):
        if not gnames:
            return None
        return gmap.get(str(r["grp"] or "").strip().upper(), "rest")
    Ng = Counter(group_of(r) for r in rows) if gnames else Counter()
    unmapped = Counter(str(r["grp"] or "(none)") for r in rows if gnames and group_of(r) == "rest")
    present_ids = defaultdict(list)
    n_by_group = defaultdict(Counter)
    party_n = defaultdict(Counter)
    co = Counter()
    co_g = defaultdict(Counter)
    co_ids = defaultdict(list)
    meta = {}
    for r in rows:
        if not r["cand"]:
            continue
        found = _present(r["t"], ents, r["cand"])
        if not found:
            continue
        g = group_of(r)
        for e in found:
            present_ids[e].append(r["id_int"])
            if g:
                n_by_group[e][g] += 1
            party_n[e][r["party"] or "(none)"] += 1
        meta[r["id_int"]] = (str(r["date"]), r["speaker_name"] or r["speaker_raw"], r["party"])
        for a, b in combinations(sorted(found), 2):
            co[(a, b)] += 1
            co_ids[(a, b)].append(r["id_int"])
            if g:
                co_g[(a, b)][g] += 1
    n = {e: len(v) for e, v in present_ids.items()}
    edges_all = []
    for (a, b), c in co.items():
        npmi = _npmi(c, n[a], n[b], N)
        edges_all.append({"source": a, "target": b, "co": c, "npmi": npmi,
                          "jaccard": c / (n[a] + n[b] - c),
                          **({f"co_{g}": co_g[(a, b)].get(g, 0) for g in gnames + ["rest"]} if gnames else {})})
    kept = [e for e in edges_all if e["co"] >= min_co_used and e["npmi"] >= min_npmi]
    nodes_in = sorted({x for e in kept for x in (e["source"], e["target"])}, key=lambda x: (-n[x], x))
    dropped_nodes = []
    if len(nodes_in) > max_nodes:
        dropped_nodes = nodes_in[max_nodes:]
        keep = set(nodes_in[:max_nodes])
        kept = [e for e in kept if e["source"] in keep and e["target"] in keep]
        nodes_in = [x for x in nodes_in if x in keep]
    kept.sort(key=lambda e: (-e["co"], e["source"], e["target"]))
    # communities and centralities on the kept graph (weight = co)
    idx = {x: i for i, x in enumerate(nodes_in)}
    lres = leiden.communities(len(nodes_in), [[idx[e["source"]], idx[e["target"]], e["co"]] for e in kept], 1.0, seed)
    btw = _betweenness(nodes_in, [(e["source"], e["target"], e["co"]) for e in kept])
    strength = Counter()
    degree = Counter()
    for e in kept:
        for x in (e["source"], e["target"]):
            strength[x] += e["co"]
            degree[x] += 1
    etype = {e["name"]: e["type"] for e in ents}
    nodes = []
    for e in ents:
        name = e["name"]
        row = {"name": name, "type": e["type"], "n": n.get(name, 0), "in_network": name in idx,
               "community": lres["community"][idx[name]] if name in idx else None,
               "degree": degree.get(name, 0), "strength": strength.get(name, 0),
               "betweenness": btw.get(name, 0.0) if name in idx else None}
        if gnames:
            for g in gnames + ["rest"]:
                row[f"n_{g}"] = n_by_group[name].get(g, 0)
            if len(gnames) == 2 and all(Ng.get(g) for g in gnames):
                r1 = n_by_group[name].get(gnames[0], 0) / Ng[gnames[0]]
                r2 = n_by_group[name].get(gnames[1], 0) / Ng[gnames[1]]
                row["bias"] = round((r1 - r2) / (r1 + r2), 4) if (r1 + r2) > 0 else None
        row["top_parties"] = dict(party_n[name].most_common(8))
        nodes.append(row)
    rng = random.Random(seed)
    sample_ids = {e["name"]: present_ids.get(e["name"], []) for e in ents}
    edge_pick = {(e["source"], e["target"]): (co_ids[(e["source"], e["target"])] if len(co_ids[(e["source"], e["target"])]) <= 3
                  else sorted(random.Random(f"{seed}:{e['source']}|{e['target']}").sample(
                      sorted(co_ids[(e["source"], e["target"])]), 3))) for e in kept}
    need = sorted({i for ids in edge_pick.values() for i in ids} | {i for name, ids in sample_ids.items() for i in
                   (ids if len(ids) <= kwic_k else random.Random(f"{seed}:{name}").sample(sorted(ids), kwic_k))}
                  | {i for e in ents for i in present_ids.get(e["name"], [])[:100]})
    raw = _raw_texts(need)
    kwic = {e["name"]: _kwic(raw, e, sample_ids[e["name"]], kwic_k, random.Random(f"{seed}:{e['name']}"))
            for e in ents}
    by_name = {e["name"]: e for e in ents}
    for e in kept:
        ex = []
        for i in edge_pick[(e["source"], e["target"])]:
            ka = _kwic({i: raw.get(i)}, by_name[e["source"]], [i], 1, rng, 70)
            kb = _kwic({i: raw.get(i)}, by_name[e["target"]], [i], 1, rng, 70)
            d, who, party = meta.get(i, (None, None, None))
            ex.append({"id_int": i, "date": d, "speaker": who, "party": party,
                       "a": ka[0] if ka else None, "b": kb[0] if kb else None})
        e["examples"] = ex
    for name, lines in kwic.items():
        for line in lines:
            d, who, party = meta.get(line["id_int"], (None, None, None))
            line.update(date=d, speaker=who, party=party)
    dates = [r["date"] for r in rows if r["date"] is not None]
    alerts = _alerts(ents, iso, min(dates) if dates else "1900-01-01", max(dates) if dates else "2999-12-31",
                     raw, present_ids) if iso != "ALL" else {}
    chance = [e for e in kept if e["npmi"] >= 0.3 and e["co"] < 2 * min_co_used]
    for name, k in n.items():
        if k > 0.8 * N:
            alerts.setdefault(name, []).append(
                f"present in {round(100 * k / N)}% of the library: it is close to the library's own subject, so its "
                f"NPMI with anything is near 0 (it co-occurs by construction). Its co counts are still meaningful.")
    for e in edges_all:
        e["npmi"] = round(e["npmi"], 6)
        e["jaccard"] = round(e["jaccard"], 6)
    nn = len(nodes_in)
    return {
        "country": iso, "N": N, "groups": {"by": group_by, "contrast": gnames,
                                           "N_by_group": dict(Ng), "unmapped_labels": dict(unmapped.most_common())}
        if gnames else None,
        "parameters": {"min_co": min_co_used, "min_co_auto": min_co is None, "min_npmi": min_npmi,
                       "max_nodes": max_nodes, "seed": seed, "unit": "intervention",
                       "filters": analysis._filters_dict(f), "communities": lres["parameters"],
                       "betweenness": "weighted, distance = 1/co, normalised", "engine": f"parlaibero-mcp {__version__}",
                       "generated": _now()},
        "nodes": nodes, "edges": kept,
        "stats": {"nodes": nn, "edges": len(kept), "density": round(2 * len(kept) / (nn * (nn - 1)), 4) if nn > 1 else None,
                  "communities": lres["n_communities"] if nn else 0, "modularity": round(lres["modularity"], 4) if nn else None,
                  "entities_never_found": [e["name"] for e in ents if not n.get(e["name"])],
                  "nodes_dropped_by_max_nodes": dropped_nodes},
        "checksums": {"sum_co": sum(e["co"] for e in kept), "sum_npmi": round(sum(e["npmi"] for e in kept), 6),
                      **({f"sum_co_{g}": sum(e.get(f"co_{g}", 0) for e in kept) for g in gnames + ["rest"]}
                         if gnames else {})},
        "kwic": kwic, "alerts": alerts,
        "chance_edges": [{"source": e["source"], "target": e["target"], "co": e["co"], "npmi": round(e["npmi"], 3)}
                         for e in chance],
        "citation": _citation_lines([iso] if iso != "ALL" else {r["country"] for r in rows}),
    }


def _summary(res: dict) -> dict:
    """What the agent reads: sizes, top edges by volume and by affinity, the most biased, centralities, warnings."""
    nodes = [x for x in res["nodes"] if x["in_network"]]
    edges = res["edges"]
    out = {"N": res["N"], **res["stats"], "parameters": {k: res["parameters"][k] for k in ("min_co", "min_co_auto",
                                                                                         "min_npmi", "max_nodes")},
           "checksums": res["checksums"],
           "top_edges_by_co": [(e["source"], e["target"], e["co"], round(e["npmi"], 3)) for e in edges[:15]],
           "top_edges_by_npmi": [(e["source"], e["target"], e["co"], round(e["npmi"], 3)) for e in
                                 sorted(edges, key=lambda e: (-e["npmi"], -e["co"]))[:15]],
           "top_nodes_by_strength": [(x["name"], x["strength"], x["n"]) for x in
                                     sorted(nodes, key=lambda x: (-x["strength"], x["name"]))[:15]],
           "top_nodes_by_betweenness": [(x["name"], x["betweenness"]) for x in
                                        sorted(nodes, key=lambda x: (-(x["betweenness"] or 0), x["name"]))[:10]],
           "communities": {c: [x["name"] for x in nodes if x["community"] == c]
                           for c in sorted({x["community"] for x in nodes})},
           "alerts": res["alerts"], "chance_edges": res["chance_edges"][:15]}
    if res["groups"]:
        g1, g2 = (res["groups"]["contrast"] + [None, None])[:2]
        b = [x for x in nodes if x.get("bias") is not None]
        if g1 and g2:
            out["most_biased_to_" + g1] = [(x["name"], x["bias"], x["n"]) for x in sorted(b, key=lambda x: -x["bias"])[:8]]
            out["most_biased_to_" + g2] = [(x["name"], x["bias"], x["n"]) for x in sorted(b, key=lambda x: x["bias"])[:8]]
            share = []
            for e in edges:
                if e["co"]:
                    share.append((e["source"], e["target"], e["co"], round(e.get(f"co_{g1}", 0) / e["co"], 3),
                                  round(e.get(f"co_{g2}", 0) / e["co"], 3)))
            out[f"edges_most_{g1}"] = sorted(share, key=lambda s: -s[3])[:8]
            out[f"edges_most_{g2}"] = sorted(share, key=lambda s: -s[4])[:8]
        out["groups"] = res["groups"]
    out["reading"] = ("co counts interventions where both entities appear (volume); NPMI measures how much more than "
                      "chance they appear together (affinity, −1…1). Read them separately: a big co with low NPMI "
                      "is two frequent entities, not an association.")
    return out


# ── outputs ───────────────────────────────────────────────────────────────────

def _write_outputs(out_dir: Path, stem: str, res: dict, formats: list[str], overwrite: bool, page) -> list[str]:
    files = []
    if "csv" in formats:
        nodes = res["nodes"]
        keys = [k for k in nodes[0] if k != "top_parties"] if nodes else []
        files.append(_write_csv(out_dir / f"{stem}_nodes.csv", keys, nodes, overwrite))
        ekeys = [k for k in res["edges"][0] if k != "examples"] if res["edges"] else ["source", "target", "co", "npmi",
                                                                                        "jaccard"]
        files.append(_write_csv(out_dir / f"{stem}_edges.csv", ekeys, res["edges"], overwrite))
    if "json" in formats:
        files.append(_write(out_dir / f"{stem}.json", json.dumps(res, ensure_ascii=False, indent=1, default=str),
                            overwrite))
    if "md" in formats:
        files.append(_write(out_dir / f"{stem}_summary.md", _markdown(res), overwrite))
    if "html" in formats:
        path = out_dir / f"{stem}.html"
        files.append(_write(path, page(res), overwrite))
        _self_check(path, res)
    return files


def _write_csv(path: Path, keys: list[str], rows: list[dict], overwrite: bool) -> str:
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists; pass overwrite=true to replace it")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(keys)
        for r in rows:
            w.writerow([r.get(k) for k in keys])
    return str(path)


def embed_json(data) -> str:
    """JSON safe inside <script>: '</' and the line separators are escaped."""
    s = json.dumps(data, ensure_ascii=False, default=str, separators=(",", ":"))
    return s.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def _self_check(path: Path, res: dict) -> None:
    """Read the written HTML back and compare its embedded data with the computed result."""
    text = path.read_text(encoding="utf-8")
    m = re.search(r'<script id="network-data" type="application/json">(.*?)</script>', text, re.S)
    if not m:
        raise RuntimeError(f"{path}: no embedded data block")
    data = json.loads(m.group(1))
    edges = data["edges"]
    got = {"sum_co": sum(e["co"] for e in edges), "sum_npmi": round(sum(e["npmi"] for e in edges), 6)}
    for k in res["checksums"]:
        if k.startswith("sum_co_"):
            got[k] = sum(e.get(k[4:], 0) for e in edges)
    if any(got[k] != res["checksums"][k] for k in got):
        path.unlink(missing_ok=True)
        raise RuntimeError(f"Self-check failed: the HTML data {got} differ from the computed {res['checksums']}. "
                           f"The file was not kept.")


def _markdown(res: dict) -> str:
    s = _summary(res)
    L = [f"# Co-mention network of actors · {res['country']}", "",
         f"- Interventions (N): {res['N']:,}", f"- Nodes: {s['nodes']} · edges: {s['edges']} · density: {s['density']}",
         f"- Thresholds: co ≥ {s['parameters']['min_co']}"
         + (" (automatic: max(5, N/120))" if s['parameters']['min_co_auto'] else "")
         + f", NPMI ≥ {s['parameters']['min_npmi']} (unrounded)",
         f"- Communities (Leiden, seed {res['parameters']['seed']}): {s['communities']} · modularity {s['modularity']}",
         f"- Checksums: {json.dumps(res['checksums'], ensure_ascii=False)}", "",
         "## Top edges by co (volume)", "", "| a | b | co | NPMI |", "|---|---|---:|---:|"]
    L += [f"| {a} | {b} | {c} | {p} |" for a, b, c, p in s["top_edges_by_co"]]
    L += ["", "## Top edges by NPMI (affinity)", "", "| a | b | co | NPMI |", "|---|---|---:|---:|"]
    L += [f"| {a} | {b} | {c} | {p} |" for a, b, c, p in s["top_edges_by_npmi"]]
    for k, v in s.items():
        if k.startswith("most_biased_to_"):
            L += ["", f"## Most biased towards {k[15:]}", ""] + [f"- {a}: {b} (n = {c})" for a, b, c in v]
    L += ["", "## Communities", ""] + [f"- {c}: {', '.join(v)}" for c, v in s["communities"].items()]
    if s["alerts"]:
        L += ["", "## Ambiguity alerts", ""] + [f"- **{k}**: {'; '.join(v)}" for k, v in s["alerts"].items()]
    if s["chance_edges"]:
        L += ["", "## High NPMI, low co (may be chance)", ""] + [f"- {e['source']} – {e['target']}: co {e['co']}, "
                                                                f"NPMI {e['npmi']}" for e in s["chance_edges"]]
    L += ["", "## Reading", "", s["reading"], "", "## Data", ""] + [f"- {c}" for c in res["citation"]]
    L += ["", f"Generated with {res['parameters']['engine']} on {res['parameters']['generated']}."]
    return "\n".join(L) + "\n"


# ── auto mode: candidate entities ─────────────────────────────────────────────

MONTHS = {"enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "setiembre",
          "octubre", "noviembre", "diciembre", "janeiro", "fevereiro", "marco", "maio", "junho", "julho", "setembro",
          "outubro", "novembro", "dezembro"}
_CAP = re.compile(r"(?<![\w])([A-ZÁÉÍÓÚÂÊÔÃÕÇÑÜ][\wÁÉÍÓÚÂÊÔÃÕÇÑÜáéíóúâêôãõçñü\-]+"
                  r"(?:\s+(?:de|da|do|dos|das|del|de la|y|e)?\s*[A-ZÁÉÍÓÚÂÊÔÃÕÇÑÜ][\wÁÉÍÓÚÂÊÔÃÕÇÑÜáéíóúâêôãõçñü\-]+){0,3})")
_ACR = re.compile(r"(?<![\w])([A-Z][A-Z0-9]{1,6})(?![\w])")


def candidates(f: analysis.Filters, max_candidates: int = 60, seed: int = 1, sample: int = 4000) -> dict:
    """Mode auto: propose actors (proper names and acronyms), with their share of a sample. Nothing is built until
    the user confirms a list. Words are not proposed: they are the nodes of cooccurrence_network."""
    params: list = []
    where = f.where(params, alias="i")
    cols, rows, _ = store.run_query(f"SELECT i.country, i.id_int, i.text FROM interventions i WHERE true{where} "
                                    f"ORDER BY hash(i.id_int || '{int(seed)}') LIMIT {int(sample)}", params,
                                    max_rows=sample, timeout_s=TIME_BUDGET_S)
    if not rows:
        raise store.NoData("The library has no interventions under these filters.")
    langs = {_language(r[0]) for r in rows}
    # forms of address are not entities: titles, honorifics and their plurals and abbreviations
    titles = {fold(t) for lang in langs for t in TITLES[lang] + HONORIFICS[lang] + LEGISLATIVE_TITLES[lang]} | {
        "sres", "sras", "srs", "senores", "senoras", "senhores", "senhoras", "diputados", "diputadas", "deputados",
        "deputadas", "excmo", "excma", "ilmo", "ilma", "exmo", "exma", "srta", "dr", "dra", "dres", "exa", "exas",
        "excelencia", "excelencias", "senoria", "senorias", "parlamentares", "parlamentarios", "colegas"}
    edge_words = PARTICLES | {"el", "la", "los", "las", "o", "a", "os", "as", "un", "una", "uns", "umas", "al",
                              "ao", "en", "em", "por", "para", "con", "com"}
    from .textutil import STOPWORDS
    cap_doc, low_doc = Counter(), Counter()
    acr_doc = Counter()
    display = defaultdict(Counter)
    for _, _, text in rows:
        text = _EDITORIAL.sub(" ", text or "")                # the record's notes ('(Risas)') are not speech
        caps = set()
        for m in _CAP.finditer(text):
            words = [w for w in m.group(1).split() if fold(w).strip(".") not in titles]
            while words and fold(words[0]) in edge_words:     # 'El …', 'de Agricultura' once 'Ministro' is out
                words = words[1:]
            while words and fold(words[-1]) in edge_words:
                words = words[:-1]
            if not words:
                continue
            phrase = " ".join(words)
            key = fold(phrase)
            if len(words) == 1 and (key in STOPWORDS or len(key) < 3 or key in MONTHS):
                continue                                      # a month alone, never inside a name ('Marco Civil')
            caps.add(key)
            display[key][phrase] += 1
        for k in caps:
            cap_doc[k] += 1
        for k in {fold(w) for w in re.findall(r"\b\w+\b", text) if w.islower()}:
            low_doc[k] += 1
        for a in {m.group(1) for m in _ACR.finditer(text)}:
            if fold(a) not in titles:
                acr_doc[a] += 1
    S = len(rows)
    proper = [(k, v) for k, v in cap_doc.items() if v >= max(3, S // 400)
              and (" " in k or low_doc.get(k, 0) < 0.3 * v)]           # mostly capitalised: a name, not a word
    out = []
    for k, v in sorted(proper, key=lambda kv: -kv[1])[: max_candidates]:
        out.append({"name": display[k].most_common(1)[0][0], "type": "persona or institucion",
                    "pattern": r"\b" + r"\s+".join(re.escape(w) for w in k.split()) + r"\b",
                    "share_of_sample": round(v / S, 4), "source": "proper name"})
    for a, v in sorted(acr_doc.items(), key=lambda kv: -kv[1])[: max_candidates // 3]:
        if v >= max(3, S // 400) and low_doc.get(fold(a), 0) < 0.3 * v:
            out.append({"name": a, "type": "institucion", "pattern": r"\b" + re.escape(fold(a)) + r"\b",
                        "share_of_sample": round(v / S, 4), "source": "acronym"})
    seen, uniq = set(), []
    for c in out:
        key = c.get("pattern")
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)
    return {"mode": "auto", "library": f.library_name, "sampled_interventions": S, "languages": sorted(langs),
            "candidates": uniq[: max_candidates + 30],
            "next": "Nothing has been built. Review the candidates (merge variants, fix types, add `exclude` where "
                    "a longer name contains a shorter one, drop what is not a person or an institution), then call "
                    "comention_network again with entities=[{name, type: persona|institucion, pattern, exclude?}]. "
                    "Patterns are regular expressions over lower-case, accent-free text (RE2 syntax: no "
                    "look-arounds). For the words and themes of the library use cooccurrence_network."}


# ── mention_network ───────────────────────────────────────────────────────────

PARTICLES = {"de", "da", "do", "dos", "das", "del", "la", "las", "los", "y", "e", "van", "von", "di"}
# a title preceded by one of these is talked ABOUT ("o deputado X disse", "el diputado X dijo")
REFERENCE_LEAD = {"o", "a", "os", "as", "do", "da", "dos", "das", "ao", "aos", "pelo", "pela", "no", "na", "com",
                  "el", "la", "los", "las", "del", "al", "por", "para", "que", "con", "como", "segun", "sobre"}
SECOND_PERSON = re.compile(r"\bv\.? ?exa\b|\bvossa excelencia\b|\bvoce\b|\busted\b|\bsu senoria\b|\bvuestra\b|"
                           r"\bv\.? ?s\.?\b|\bsenoria\b")
FEMININE_TITLES = {"deputada", "diputada", "senhora", "senora", "ministra", "senadora", "presidenta", "doutora",
                   "doctora", "dona", "legisladora", "relatora", "asambleista"}
_TOKEN = re.compile(r"[a-z0-9]+")


def _name_parts(name: str, lang: str = "pt") -> tuple[list[str], list[str]]:
    """(given names, surnames) from a register name without separate name fields: 'APELLIDO APELLIDO, NOMBRE'
    in any language; without a comma, in Portuguese the parliamentary name ('DR. LUIZ TAVARES'), where only the
    last word is surely a surname and the words before it may be ranks, titles or given names, and in Spanish
    'NOMBRE APELLIDO APELLIDO', where the first word is the given name."""
    n = fold(name or "")
    if "," in n:
        last, first = n.split(",", 1)
        return _TOKEN.findall(first), _TOKEN.findall(last)
    toks = _TOKEN.findall(n)
    if len(toks) <= 1:
        return [], toks
    if lang == "pt":
        return toks[:-1], toks[-1:]
    return toks[:1], toks[1:]


def _register_terms(iso: str) -> list[dict]:
    """The country's register with every term closed: a missing end date (common for the last term of a
    deputy who left) is the day before the NEXT legislature of the register begins; only the latest
    legislature stays open. General: uses nothing but the register itself."""
    cols, data, _ = store.run_query("""SELECT id_dep, speaker_name, first_name, last_name, party, sex, legislature,
                                             TRY_CAST(start_date AS DATE) s, TRY_CAST(end_date AS DATE) e
                                      FROM deputies WHERE country = ? AND TRY_CAST(start_date AS DATE) IS NOT NULL""",
                                   [iso], max_rows=500_000)
    rows = [dict(zip(cols, r)) for r in data]
    starts = {}
    for r in rows:
        lg = r["legislature"]
        starts[lg] = min(starts.get(lg, r["s"]), r["s"])
    order = sorted(starts, key=lambda lg: starts[lg])
    nxt = {lg: (starts[order[k + 1]] if k + 1 < len(order) else None) for k, lg in enumerate(order)}
    from datetime import date as _date, timedelta
    for r in rows:
        if r["e"] is None:
            n = nxt.get(r["legislature"])
            r["e"] = (n - timedelta(days=1)) if n and n > r["s"] else _date(2999, 12, 31)
    return rows


def _name_roles(register: list[dict], lang: str = "pt") -> tuple[Counter, Counter]:
    """How often each word is a GIVEN name and how often a SURNAME in the whole register. A word used mostly
    as a given name ('luiz', 'maria', 'pedro') is never a surname alias on its own: a title + it names
    someone else."""
    given_like, last_like = Counter(), Counter()
    for r in register:
        g, sname = _name_parts(r["speaker_name"], lang)
        if r.get("first_name"):
            g = _TOKEN.findall(fold(r["first_name"]))
        if r.get("last_name"):
            sname = _TOKEN.findall(fold(r["last_name"]))
        for t in set(g):
            given_like[t] += 1
        for t in set(sname):
            last_like[t] += 1
    return given_like, last_like


def _gazetteer(iso: str, date_min, date_max) -> tuple[dict, dict, dict]:
    """Aliases of the deputies in office in the period.
    full: alias (≥ 2 tokens, valid anywhere) → {deputy}; surname: alias valid only after a title → {deputy};
    info: id_dep → {name, party, sex, terms}."""
    from datetime import date as _date
    lo = _date.fromisoformat(str(date_min)[:10])
    hi = _date.fromisoformat(str(date_max)[:10])
    common = {r[0] for r in store.run_query("SELECT fold FROM vocab WHERE country = ? ORDER BY n DESC LIMIT 5000",
                                            [iso], max_rows=5000)[1]}
    register = _register_terms(iso)
    parties = {fold(r["party"]) for r in register if r["party"]}
    lang = _language(iso)
    given_like, last_like = _name_roles(register, lang)
    info: dict = {}
    full, surname = defaultdict(set), defaultdict(set)
    for d in register:
        if not d["id_dep"] or d["s"] > hi or d["e"] < lo:
            continue
        i = d["id_dep"]
        rec = info.setdefault(i, {"name": d["speaker_name"], "party": d["party"], "sex": d["sex"], "terms": []})
        rec["terms"].append((d["s"], d["e"], d["party"]))
        given, sur = _name_parts(d["speaker_name"], lang)
        if d.get("first_name") or d.get("last_name"):
            given = _TOKEN.findall(fold(d.get("first_name") or "")) or given
            sur = _TOKEN.findall(fold(d.get("last_name") or "")) or sur
        sur_core = [t for t in sur if t not in PARTICLES]
        rec.setdefault("given", set()).update(t for t in given if len(t) >= 3 and t not in PARTICLES)
        whole = _TOKEN.findall(fold((d["speaker_name"] or "").replace(",", " ")))
        cands_full = set()
        if len(whole) >= 2:
            cands_full.add(" ".join(whole))                                     # the name as registered
        if given and sur:
            cands_full.add(" ".join(given + sur))                               # given + all surnames
            if sur_core:
                cands_full.add(" ".join(given[:1] + sur_core[:1]))              # first given + first surname
        for a in cands_full:
            if len(a.split()) >= 2:
                full[a].add(i)
        # after a title only: the surnames, the first surname, the last word of the name. Never a phrase that
        # starts with a particle ('do pt', 'da federal'), a party acronym or one of the 5,000 commonest words.
        comma = "," in (d["speaker_name"] or "") or bool(d.get("last_name"))
        # the surnames as written, and the one used alone: the FIRST in Spanish ('García' for García Pérez; the
        # second alone is not how a member is named), the first or the LAST in Portuguese
        cands = {" ".join(sur), " ".join(sur_core), sur_core[0] if sur_core else ""}
        if lang == "pt" and sur_core:
            cands.add(sur_core[-1])
        if not comma and lang == "pt" and len(whole) >= 3 and whole[-2] not in PARTICLES:
            cands.add(" ".join(whole[-2:]))                                     # 'luiz tavares'
        for a in cands:
            first = a.split()[0] if a else ""
            single = " " not in a
            if not a or len(a.replace(" ", "")) < 3 or first not in PARTICLES and a in parties or first in PARTICLES:
                continue
            if single and (a in TITLE_COMPLEMENTS or a in given_like and given_like[a] > last_like.get(a, 0)):
                continue                                                        # 'federal'; 'luiz', 'pedro'
            # a common word is kept only when it is one of the name's own surnames ('lira', 'pereira'); the
            # words of the register name that follow a particle as a nickname were already caught above
            name_words = sur_core if comma or lang != "pt" else [t for t in (whole[1:] or whole) if t not in PARTICLES]
            if single and a in common and a not in name_words:
                continue                                                        # a common word, not a surname
            surname[a].add(i)
    return dict(full), dict(surname), info


def _in_office(info: dict, ids, day) -> list[str]:
    if day is None:
        return sorted(ids)
    return sorted(i for i in ids if any(s <= day <= e for s, e, _ in info[i]["terms"]))


def _party_at(info: dict, i: str, day) -> str | None:
    for s, e, p in info.get(i, {}).get("terms", []):
        if day is None or s <= day <= e:
            return p
    return info.get(i, {}).get("party")


_EDITORIAL = re.compile(r"\([^()]{0,1500}\)")
POSSESSIVE_RELIGIOUS = {"nosso", "nossa", "nuestro", "nuestra"}
GENDERED_TITLES = {"deputado", "deputada", "diputado", "diputada", "senhor", "senhora", "senor", "senora", "sr", "sra",
                   "don", "dona", "legislador", "legisladora", "parlamentario", "parlamentaria"}
PLURAL_VOCATIVES = {"senorias", "senores", "senoras", "diputados", "diputadas", "deputados", "deputadas", "colegas",
                    "senhores", "senhoras", "parlamentares", "companeros", "companheiros"}
GREETING = {"obrigado", "obrigada", "parabens", "gracias", "muchas", "felicito", "felicidades", "bem", "bom",
            "buenas", "buenos", "bienvenido", "bienvenida", "sim", "nao", "si", "no", "agora", "ahora"}


def _common_words(iso: str, n: int) -> set[str]:
    return {r[0] for r in store.run_query("SELECT fold FROM vocab WHERE country = ? ORDER BY n DESC LIMIT ?",
                                          [iso, n], max_rows=n)[1]}


def _find_mentions(text: str, day, lang_titles: set[str], full: dict, surname: dict, info: dict, externals: list[dict],
                   max_len: int = 5, common: set[str] | None = None, surnames: set[str] | None = None,
                   common_core: frozenset = frozenset()) -> list[dict]:
    """Mentions in a folded text: [{start, end, alias, candidates, title, kind, external}].
    kind 'editorial' = inside the record's own notes in brackets ('(O Sr. X deixa a cadeira…)',
    '(El señor X: ¡Bravo!)'): the speaker did not say it."""
    toks = [(m.group(0), m.start(), m.end()) for m in _TOKEN.finditer(text)]
    out = []
    used = [False] * len(toks)
    words = [t[0] for t in toks]
    # the surname of each external actor's NAME ('Fulano de Tal' → 'tal'), not every alias word
    ext_words = {_TOKEN.findall(fold(ext["name"]))[-1] for ext in externals if _TOKEN.findall(fold(ext["name"]))}
    # externals first (the user's names win over register aliases at the same place)
    for ext in externals:
        for alias in ext["_aliases"]:
            k = len(alias)
            for j in range(len(words) - k + 1):
                if tuple(words[j:j + k]) == alias and not any(used[j:j + k]):
                    for q in range(j, j + k):
                        used[q] = True
                    out.append({"start": toks[j][1], "end": toks[j + k - 1][2], "alias": " ".join(alias),
                                "candidates": [ext["key"]], "title": None, "external": True})
    j = 0
    while j < len(words):
        if used[j]:
            j += 1
            continue
        hit = None
        title = words[j] if words[j] in lang_titles else None
        start = j + 1 if title else j
        if title and start < len(words) and words[start] in TITLE_COMPLEMENTS:
            start += 1                                                          # 'deputado federal X'
        for k in range(max_len, 0, -1):                                         # longest alias first
            if start + k > len(words) or any(used[start:start + k]):
                continue
            a = " ".join(words[start:start + k])
            ids = full.get(a) if k >= 2 else None
            by_surname = False
            if not ids and title:
                ids = surname.get(a)
                by_surname = bool(ids)
            if ids and by_surname and (j and words[j - 1] in POSSESSIVE_RELIGIOUS or a in ext_words):
                # 'nosso Senhor Jesus' is no title; a surname shared with an external actor the user named
                # ('o sr. X' with the former president X declared) needs the full name
                ids = None
            if ids and by_surname and common is not None and start + k < len(words):
                # the name goes on with another surname or a word that is not common: someone else who
                # shares a name ('sr. Pedro Cid' is not a deputy surnamed Pedro; 'señor Moreno Ruiz' is not one surnamed Moreno)
                nxt, gap = words[start + k], text[toks[start + k - 1][2]:toks[start + k][1]]
                if gap.strip() == "" and nxt not in PARTICLES and not nxt.isdigit() and (
                        nxt not in common or nxt in (surnames or ()) and nxt not in common_core):
                    ids = None
            if ids and title and title in GENDERED_TITLES:
                want = "F" if title in FEMININE_TITLES else "M"
                ids = [i for i in ids if (info[i].get("sex") or want).upper()[:1] == want] or None
            if ids:
                ids = _in_office(info, ids, day)
                if ids:
                    hit = (start, k, a, ids)
                    break
        if hit:
            s0, k, a, ids = hit
            first = j if title else s0
            for q in range(first, s0 + k):
                used[q] = True
            out.append({"start": toks[first][1], "end": toks[s0 + k - 1][2], "alias": a, "candidates": ids,
                        "title": title, "external": False})
            j = s0 + k
        else:
            j += 1
    notes = [(m.start(), m.end()) for m in _EDITORIAL.finditer(text)]
    for m in out:
        if any(s <= m["start"] and m["end"] <= e for s, e in notes):
            m["kind"] = "editorial"
        else:
            m["kind"] = _mention_kind(text, m, lang_titles)
    return out


ADDRESS_WORDS = {"presidente", "presidenta", "excelentissimo", "excelentissima", "excelentisimo", "excelentisima",
                 "dignissimo", "dignissima", "nobre", "querido", "querida", "caro", "cara", "estimado", "estimada",
                 "colega", "prezado", "prezada", "companheiro", "companheira", "companero", "companera", "lider", "meu", "minha", "mi",
                 "senhor", "senhora", "senor", "senora", "sr", "sra", "don", "dona", "ministro", "ministra"}


def _mention_kind(text: str, m: dict, lang_titles=frozenset()) -> str:
    """'address' (speaking TO someone: a vocative, or the second person right after) or 'reference'
    (speaking ABOUT someone). A vocative is the name with its forms of address ('grato, digníssimo
    presidente X'; 'caro colega deputado X'; 'Sr. Presidente, Deputado X') between a boundary (the start,
    a punctuation mark, a greeting) and a punctuation mark, the end, or another vocative ('…, deputado X e
    deputada Y, …')."""
    base = max(0, m["start"] - 100)
    before_toks = list(_TOKEN.finditer(text[base:m["start"]]))
    q = len(before_toks)
    stop = set(lang_titles) | ADDRESS_WORDS
    while q and before_toks[q - 1].group(0) in stop:
        q -= 1
    lead_end = base + (before_toks[q - 1].end() if q else 0)
    prev = before_toks[q - 1].group(0) if q else ""
    span = text[lead_end:m["start"]]                                    # from the lead word to the name
    after = text[m["end"]:m["end"] + 80]
    punct = bool(re.search(r"[,.;:!?¡¿(\-—]", span))
    if prev in REFERENCE_LEAD and not punct:
        return "reference"
    opens = (not q and m["start"] < 100) or punct or prev in GREETING
    if not opens and prev in ("e", "y") and q:
        # the second of two vocatives: 'Señora X y señor Y, …'; 'Señorías y señora X, …'
        pre = text[max(0, base + before_toks[q - 1].start() - 60):base + before_toks[q - 1].start()]
        words_before = _TOKEN.findall(pre)
        titles_re = "|".join(sorted(stop))
        opens = bool(words_before and words_before[-1] in PLURAL_VOCATIVES) or bool(
            re.search(r"(?:^|[,.;:!?¡¿]\s*)(?:(?:" + titles_re + r")\s+)+[a-z]+(?:\s+[a-z]+){0,3}\s*$", pre)) or bool(
            re.search(r"(?:^|[,.;:!?¡¿]\s*)(?:(?:" + titles_re + r")\s*)+$", pre))        # 'Presidente e deputado X,'

    closes = bool(re.match(r"\s*(?:[,.;:!?)\-—]|$)", after)) or bool(
        re.match(r"\s+(?:e|y)\s+(?:" + "|".join(sorted(stop)) + r")\b", after))
    if (opens and closes) or SECOND_PERSON.search(after[:60]):
        return "address"
    return "reference"


def _disambiguate(m: dict, text: str, info: dict, day) -> str | None:
    """One deputy for an ambiguous alias: the title's gender, then a given name or a party acronym written right
    after the name. Otherwise None: the mention is listed apart, never guessed."""
    c = m["candidates"]
    if len(c) == 1:
        return c[0]
    if m["title"]:
        want = "F" if m["title"] in FEMININE_TITLES else "M"
        same = [i for i in c if (info[i].get("sex") or "").upper()[:1] == want]
        if len(same) == 1:
            return same[0]
        c = same or c
    # the given name written right after the surname: 'el diputado Durán, don Eduardo'; 'deputado Silva, João'
    after = _TOKEN.findall(fold(text[m["end"]:m["end"] + 30]))[:3]
    by_given = [i for i in c if info[i].get("given") and info[i]["given"] & set(after)]
    if len(by_given) == 1:
        return by_given[0]
    near = fold(text[m["end"]:m["end"] + 40])
    by_party = [i for i in c if (_party_at(info, i, day) or "") and
                re.search(r"\b" + re.escape(fold(_party_at(info, i, day))) + r"\b", near)]
    if len(by_party) == 1:
        return by_party[0]
    return None


def _pagerank(nodes: list[str], edges: dict[tuple[str, str], float], d: float = 0.85, it: int = 200) -> dict:
    n = len(nodes)
    if not n:
        return {}
    out_w = Counter()
    for (a, b), w in edges.items():
        out_w[a] += w
    pr = dict.fromkeys(nodes, 1 / n)
    for _ in range(it):
        nxt = dict.fromkeys(nodes, (1 - d) / n)
        dangling = sum(pr[v] for v in nodes if not out_w[v])
        for v in nodes:
            nxt[v] += d * dangling / n
        for (a, b), w in edges.items():
            nxt[b] += d * pr[a] * w / out_w[a]
        delta = sum(abs(nxt[v] - pr[v]) for v in nodes)
        pr = nxt
        if delta < 1e-12:
            break
    return {v: round(p, 6) for v, p in pr.items()}


def mention_network(f: analysis.Filters, target_scope: str = "both", external_actors: list[dict] | None = None,
                    mention_kinds: list[str] | None = None, groups: dict | None = None, group_by: str = "party",
                    min_mentions: int = 2, min_speakers: int = 1, top_n: int = 60, seed: int = 1,
                    validation_sample: int = 0, output_dir: str | None = None, formats: list[str] | None = None,
                    overwrite: bool = False, honorifics: bool | None = None, max_node_size: float = 12,
                    max_edge_width: float = 1.5, layout: str = "force") -> dict:
    """Directed network of who (speaker) mentions whom (another deputy of the chamber, or an external
    actor given by the user), one per country. Definitions in the module docstring and the plan."""
    if f.library is None:
        raise ValueError("mention_network needs a library (library=…)")
    view = _view(max_node_size, max_edge_width, layout)
    if target_scope not in ("speakers", "external", "both"):
        raise ValueError("target_scope must be speakers, external or both")
    kinds = set(mention_kinds or ["reference"])
    if not kinds <= {"reference", "address"}:
        raise ValueError("mention_kinds takes 'reference' and/or 'address'")
    if target_scope != "speakers" and not external_actors and target_scope == "external":
        raise ValueError("target_scope='external' needs external_actors=[{name, aliases, role}]")
    t0 = time.time()
    exts = []
    for k, e in enumerate(external_actors or []):
        name = str(e.get("name") or "").strip()
        if not name:
            raise ValueError(f"external actor {k + 1} has no name")
        aliases = [name] + [str(a) for a in (e.get("aliases") or [])]
        exts.append({"key": "ext:" + name, "name": name, "role": e.get("role"),
                     "_aliases": sorted({tuple(_TOKEN.findall(fold(a))) for a in aliases if _TOKEN.findall(fold(a))},
                                        key=lambda a: -len(a))})
    if group_by not in profile.ACTIVE.groups():
        raise ValueError(f"group_by must be one of {', '.join(profile.ACTIVE.groups())}")
    gnames, gmap = _resolve_groups(groups, group_by)
    params: list = []
    where = f.where(params, alias="i")
    cols, rows, truncated = store.run_query(
        f"SELECT i.country, i.id_int, i.id_session, i.date, i.id_dep, i.speaker_raw, i.speaker_name, i.party, "
        f"i.{group_by} AS grp, strip_accents(lower(coalesce(i.text, ''))) AS t "
        f"FROM interventions i WHERE true{where}", params, max_rows=MAX_ROWS, timeout_s=TIME_BUDGET_S)
    if truncated:
        raise ValueError(f"The library has more than {MAX_ROWS:,} interventions after the filters: narrow it down.")
    if not rows:
        raise store.NoData("The library has no interventions under these filters.")
    by_country = defaultdict(list)
    for r in rows:
        by_country[r[0]].append(dict(zip(cols, r)))
    formats = [x.lower() for x in (formats or ["html", "csv", "json", "md"])]
    out_dir = _out_dir(output_dir)
    results = {}
    for iso, part in sorted(by_country.items()):
        results[iso] = _one_mention_network(iso, part, exts, target_scope, kinds, gnames, gmap, group_by, honorifics,
                                            min_mentions, min_speakers, top_n, seed, validation_sample, f)
        results[iso]["parameters"]["view"] = view
    files = []
    if out_dir:
        from . import network_html
        base = store_slug(f.library_name or "library") + "_mentions"
        for iso, res in results.items():
            stem = base + ("" if len(results) == 1 else f"_{iso}")
            files += _write_mention_outputs(out_dir, stem, res, formats, overwrite,
                                            getattr(network_html, "mention_page", None))
    return {"library": f.library_name, "networks": {iso: _mention_summary(r) for iso, r in results.items()},
            "files": files, "seconds": round(time.time() - t0, 1),
            "notes": ["One network per country: a speaker can only mention, on the floor, the members of their own "
                      "chamber; external actors can be shared."] if len(results) > 1 else [],
            "datasets": analysis._versions(results)}


def _one_mention_network(iso, rows, exts, target_scope, kinds, gnames, gmap, group_by, honorifics, min_mentions,
                         min_speakers,
                         top_n, seed, validation_sample, f) -> dict:
    lang = _language(iso)
    use_honorifics = HONORIFICS_LICENSE.get(lang, False) if honorifics is None else honorifics
    honorific = {fold(t) for t in HONORIFICS[lang]} if use_honorifics else set()
    titles = {fold(t) for t in LEGISLATIVE_TITLES[lang]} | honorific
    dates = [r["date"] for r in rows if r["date"] is not None]
    dmin, dmax = (min(dates), max(dates)) if dates else (None, None)
    full, surname, info = _gazetteer(iso, dmin or "1900-01-01", dmax or "2999-12-31")
    common = _common_words(iso, 20000)
    common_core = frozenset(_common_words(iso, 500))
    surnames_all = {t for t, c in _name_roles(_register_terms(iso), lang)[1].items() if c}
    courtesy = [re.compile(p) for p in COURTESY_UNRESOLVABLE[lang]]
    edges = defaultdict(lambda: {"interventions": set(), "mentions": 0, "sessions": set(), "examples": []})
    ambiguous, courtesy_n = [], 0
    found_n = Counter()
    speakers = {}
    validation = []

    def speaker_key(r):
        return r["id_dep"] or ("raw:" + (r["speaker_name"] or r["speaker_raw"] or "?"))
    for r in rows:
        src = speaker_key(r)
        speakers.setdefault(src, {"name": r["speaker_name"] or r["speaker_raw"], "party": r["party"],
                                  "grp": r["grp"], "linked": bool(r["id_dep"]), "turns": 0})
        speakers[src]["turns"] += 1
        text = r["t"]
        courtesy_n += sum(len(c.findall(text)) for c in courtesy)
        ms = _find_mentions(text, r["date"], titles, full if target_scope != "external" else {},
                            surname if target_scope != "external" else {}, info,
                            exts if target_scope != "speakers" else [], common=common,
                            surnames=surnames_all, common_core=common_core)
        for m in ms:
            found_n[m["kind"]] += 1
            if m["kind"] not in kinds:
                continue
            target = m["candidates"][0] if m["external"] else _disambiguate(m, text, info, r["date"])
            if target is None:
                ambiguous.append({"id_int": r["id_int"], "date": str(r["date"]), "speaker": speakers[src]["name"],
                                  "alias": m["alias"], "title": m["title"],
                                  "candidates": "; ".join(f"{i} {info[i]['name']}" for i in m["candidates"]),
                                  "context": text[max(0, m["start"] - 80):m["end"] + 80]})
                found_n["ambiguous"] += 1
                continue
            if target == src:
                found_n["self"] += 1
                continue
            e = edges[(src, target)]
            e["interventions"].add(r["id_int"])
            e["mentions"] += 1
            e["sessions"].add(r["id_session"])
            e["examples"].append((r["id_int"], m["start"], m["end"]))
            found_n["resolved"] += 1
            validation.append({"id_int": r["id_int"], "date": str(r["date"]), "speaker": speakers[src]["name"],
                               "target": info[target]["name"] if target in info else target[4:],
                               "alias": m["alias"], "title": m["title"], "kind": m["kind"],
                               "licensed_by": ("full name" if not m["title"] else
                                               "honorific" if m["title"] in honorific else "legislative title"),
                               "context": text[max(0, m["start"] - 100):m["end"] + 100]})
    # nodes and filtering
    E = {k: v for k, v in edges.items() if len(v["interventions"]) >= min_mentions}
    senders_of = defaultdict(set)
    for (a, b) in E:
        senders_of[b].add(a)
    E = {k: v for k, v in E.items() if len(senders_of[k[1]]) >= min_speakers}
    instr, outstr = Counter(), Counter()
    for (a, b), v in E.items():
        w = len(v["interventions"])
        instr[b] += w
        outstr[a] += w
    ranked = sorted(set(instr) | set(outstr), key=lambda x: (-(instr[x] + outstr[x]), str(x)))
    keep = set(ranked[:top_n])
    E = {k: v for k, v in E.items() if k[0] in keep and k[1] in keep}
    nodes = sorted({x for k in E for x in k}, key=lambda x: (-(instr[x] + outstr[x]), str(x)))
    W = {k: len(v["interventions"]) for k, v in E.items()}
    pr = _pagerank(nodes, W)
    idx = {x: i for i, x in enumerate(nodes)}
    sym = Counter()
    for (a, b), w in W.items():
        sym[tuple(sorted((idx[a], idx[b])))] += w
    lres = leiden.communities(len(nodes), [[a, b, w] for (a, b), w in sym.items()], 1.0, seed)
    # reciprocity among people who could answer (both speak in the library): arrows to external actors or to
    # silent deputies can never be returned
    WS = [(a, b) for (a, b) in W if a in speakers and b in speakers]
    recip = round(sum(1 for (a, b) in WS if (b, a) in W) / len(WS), 4) if WS else None

    def label_of(x):
        if x.startswith("ext:"):
            return x[4:]
        if x in info:
            return info[x]["name"]
        return speakers.get(x, {}).get("name") or x

    # a deputy who is named but does not speak in the library takes the label they carry when speaking anywhere
    # in the chamber in the period (the commonest); with no turn at all, the register's party for group_by=party,
    # otherwise 'unlabelled', which stays out of the E-I index and the group matrix
    silent = sorted({x for x in nodes if not x.startswith("ext:") and x not in speakers and x in info})
    silent_label = {}
    if silent:
        ph = ", ".join("?" for _ in silent)
        silent_label = {r[0]: r[1] for r in store.run_query(
            f"SELECT id_dep, mode({group_by}) FROM interventions WHERE country = ? AND id_dep IN ({ph}) "
            f"AND {group_by} IS NOT NULL AND date BETWEEN ? AND ? GROUP BY 1",
            [iso, *silent, str(dmin), str(dmax)], max_rows=len(silent))[1]} if dmin else {}
        for x in silent:
            if x not in silent_label and group_by == "party":
                silent_label[x] = _party_at(info, x, dmax)

    def group_of(x, day=None):
        if x.startswith("ext:"):
            return "external"
        lab = speakers[x]["grp"] if x in speakers else silent_label.get(x)
        if lab is None:
            return "unlabelled"
        if not gnames:
            return str(lab)
        return gmap.get(str(lab).strip().upper(), "rest")
    node_rows = []
    for x in nodes:
        node_rows.append({"id": x, "name": label_of(x), "kind": "external" if x.startswith("ext:") else
                          ("speaker" if x in speakers else "mentioned deputy"),
                          "party": (speakers.get(x, {}).get("party") or (info.get(x, {}).get("party")))
                          if not x.startswith("ext:") else None,
                          "role": next((e["role"] for e in exts if e["key"] == x), None),
                          "group": group_of(x), "in_strength": instr[x], "out_strength": outstr[x],
                          "pagerank": pr.get(x), "community": lres["community"][idx[x]]})
    # block matrix: mentions from group A to group B, per intervention of group A
    turns_by_group = Counter()
    for r in rows:
        turns_by_group[group_of(speaker_key(r))] += 1
    block = defaultdict(Counter)
    unlabelled_w, unlabelled_people = 0, {x for x in nodes if group_of(x) == "unlabelled"}
    for (a, b), w in W.items():
        if group_of(a) == "unlabelled" or group_of(b) == "unlabelled":
            unlabelled_w += w                       # no label in the library or the chamber: not in any group
            continue
        block[group_of(a)][group_of(b)] += w
    block_rows = [{"from": ga, "to": gb, "mentions": w, "per_100_interventions": round(100 * w / turns_by_group[ga], 3)
                   if turns_by_group[ga] else None} for ga, row in sorted(block.items()) for gb, w in sorted(row.items())]
    ei = {}
    for g in block:
        # between deputies only: mentions of external actors are neither in-group nor out-group
        internal = block[g].get(g, 0)
        external = sum(w for gb, w in block[g].items() if gb not in (g, "external"))
        ei[g] = round((external - internal) / (external + internal), 3) if internal + external else None
    asym = []
    for (a, b), w in W.items():
        back = W.get((b, a), 0)
        # only between people who SPEAK in the library: an external actor or a silent deputy cannot answer
        if b not in speakers or a not in speakers:
            continue
        if w >= max(5, min_mentions) and back <= w / 5:
            asym.append({"from": label_of(a), "to": label_of(b), "a_to_b": w, "b_to_a": back})
    asym.sort(key=lambda x: -x["a_to_b"])
    # examples per edge (seeded), and the validation sample
    rng = random.Random(seed)
    raw = {r["id_int"]: r["t"] for r in rows}
    edge_rows = []
    for (a, b), v in sorted(E.items(), key=lambda kv: (-len(kv[1]["interventions"]), str(kv[0]))):
        ex = v["examples"] if len(v["examples"]) <= 3 else random.Random(f"{seed}:{a}>{b}").sample(v["examples"], 3)
        edge_rows.append({"source": a, "target": b, "source_name": label_of(a), "target_name": label_of(b),
                          "interventions": len(v["interventions"]), "mentions": v["mentions"],
                          "sessions": len(v["sessions"]),
                          "examples": [{"id_int": i, "left": raw[i][max(0, s - 90):s], "match": raw[i][s:e],
                                        "right": raw[i][e:e + 90]} for i, s, e in sorted(ex)]})
    sample = sorted(rng.sample(validation, validation_sample), key=lambda x: x["id_int"]) \
        if validation_sample and len(validation) > validation_sample else (validation if validation_sample else [])
    # coverage of the gazetteer
    linked = [s for s, d in speakers.items() if d["linked"]]
    with_alias = [s for s in linked if s in info]
    return {
        "country": iso, "N": len(rows),
        "parameters": {"target_scope": target_scope, "mention_kinds": sorted(kinds), "honorifics": use_honorifics,
                       "min_mentions": min_mentions,
                       "min_speakers": min_speakers, "top_n": top_n, "seed": seed, "group_by": group_by,
                       "groups": {"contrast": gnames} if gnames else None, "filters": analysis._filters_dict(f),
                       "communities": lres["parameters"], "engine": f"parlaibero-mcp {__version__}",
                       "generated": _now(), "language": lang},
        "coverage": {"deputies_in_register_for_the_period": len(info), "library_speakers": len(speakers),
                     "linked_speakers": len(linked), "linked_speakers_in_gazetteer": len(with_alias),
                     "aliases_full": len(full), "aliases_after_title": len(surname)},
        "counts": {"mentions_found": dict(found_n), "unresolvable_courtesy_forms": courtesy_n,
                   "ambiguous": len(ambiguous)},
        "nodes": node_rows, "edges": edge_rows,
        "stats": {"nodes": len(nodes), "edges": len(W), "reciprocity": round(recip, 4) if recip is not None else None,
                  "communities": lres["n_communities"] if nodes else 0},
        "block_matrix": block_rows, "ei_index": ei, "asymmetric_pairs": asym[:20],
        "unlabelled": {"people": len(unlabelled_people), "interventions": unlabelled_w,
                       "note": f"people with no {group_by} label anywhere in the period: left out of the group "
                               f"matrix and the E-I index"},
        "ambiguous": ambiguous, "validation_sample": sample,
        "checksums": {"sum_interventions": sum(e["interventions"] for e in edge_rows),
                      "sum_mentions": sum(e["mentions"] for e in edge_rows)},
        "citation": _citation_lines([iso]),
    }


def _mention_summary(res: dict) -> dict:
    nodes = res["nodes"]
    return {"N": res["N"], **res["stats"], "honorifics": res["parameters"]["honorifics"],
            "edge_list": [(e["source"], e["target"], e["interventions"]) for e in res["edges"]],
            "coverage": res["coverage"], "counts": res["counts"],
            "top_receivers": [(x["name"], x["in_strength"], x["group"]) for x in
                              sorted(nodes, key=lambda x: (-x["in_strength"], x["name"]))[:15]],
            "top_senders": [(x["name"], x["out_strength"], x["group"]) for x in
                            sorted(nodes, key=lambda x: (-x["out_strength"], x["name"]))[:15]],
            "top_pagerank": [(x["name"], x["pagerank"]) for x in
                             sorted(nodes, key=lambda x: (-(x["pagerank"] or 0), x["name"]))[:10]],
            "block_matrix": res["block_matrix"], "ei_index": res["ei_index"], "unlabelled": res["unlabelled"],
            "asymmetric_pairs": res["asymmetric_pairs"][:10], "checksums": res["checksums"],
            "reading": ("Edge A→B = interventions of A that mention B (by name, or surname after a title). "
                        "'reference' = talking ABOUT someone; 'address' = speaking TO them. Mentions that could "
                        "not be resolved to one person are in the ambiguous list, never assigned at random.")}


def _write_mention_outputs(out_dir: Path, stem: str, res: dict, formats, overwrite, page) -> list[str]:
    files = []
    if "csv" in formats:
        nk = list(res["nodes"][0]) if res["nodes"] else ["id", "name"]
        files.append(_write_csv(out_dir / f"{stem}_nodes.csv", nk, res["nodes"], overwrite))
        ek = [k for k in (res["edges"][0] if res["edges"] else {"source": 0, "target": 0}) if k != "examples"]
        files.append(_write_csv(out_dir / f"{stem}_edges.csv", ek, res["edges"], overwrite))
        files.append(_write_csv(out_dir / f"{stem}_block_matrix.csv", ["from", "to", "mentions", "per_100_interventions"],
                                res["block_matrix"], overwrite))
        if res["ambiguous"]:
            files.append(_write_csv(out_dir / f"{stem}_ambiguas.csv", list(res["ambiguous"][0]), res["ambiguous"],
                                    overwrite))
        if res["validation_sample"]:
            keys = list(res["validation_sample"][0]) + ["correct_target (y/n)", "correct_kind (y/n)"]
            files.append(_write_csv(out_dir / f"{stem}_validation_sample.csv", keys, res["validation_sample"], overwrite))
    if "json" in formats:
        files.append(_write(out_dir / f"{stem}.json", json.dumps(res, ensure_ascii=False, indent=1, default=str),
                            overwrite))
    if "md" in formats:
        s = _mention_summary(res)
        L = [f"# Mention network · {res['country']}", "", f"- Interventions (N): {res['N']:,}",
             f"- Nodes: {s['nodes']} · edges: {s['edges']} · reciprocity: {s['reciprocity']}",
             f"- Kinds counted: {', '.join(res['parameters']['mention_kinds'])} · min_mentions "
             f"{res['parameters']['min_mentions']}", f"- Coverage: {json.dumps(res['coverage'])}",
             f"- Mentions: {json.dumps(res['counts'])}", "", "## Top receivers", ""]
        L += [f"- {n}: {w} ({g})" for n, w, g in s["top_receivers"]]
        L += ["", "## Top senders", ""] + [f"- {n}: {w} ({g})" for n, w, g in s["top_senders"]]
        L += ["", "## Group → group", "", "| from | to | mentions | per 100 interventions |", "|---|---|---:|---:|"]
        L += [f"| {b['from']} | {b['to']} | {b['mentions']} | {b['per_100_interventions']} |" for b in s["block_matrix"]]
        L += ["", "## E-I index (−1 = only own group, +1 = only others)", ""] + [f"- {g}: {v}" for g, v in
                                                                                s["ei_index"].items()]
        if s["asymmetric_pairs"]:
            L += ["", "## Strongly asymmetric pairs", ""] + [f"- {a['from']} → {a['to']}: {a['a_to_b']} (back: "
                                                              f"{a['b_to_a']})" for a in s["asymmetric_pairs"]]
        L += ["", "## Reading", "", s["reading"], "", "## Data", ""] + [f"- {c}" for c in res["citation"]]
        files.append(_write(out_dir / f"{stem}_summary.md", "\n".join(L) + "\n", overwrite))
    if "html" in formats:
        path = out_dir / f"{stem}.html"
        files.append(_write(path, page(res), overwrite))
        text = path.read_text(encoding="utf-8")
        m = re.search(r'<script id="network-data" type="application/json">(.*?)</script>', text, re.S)
        data = json.loads(m.group(1))
        got = {"sum_interventions": sum(e["interventions"] for e in data["edges"]),
               "sum_mentions": sum(e["mentions"] for e in data["edges"])}
        if got != res["checksums"]:
            path.unlink(missing_ok=True)
            raise RuntimeError(f"Self-check failed: HTML {got} vs computed {res['checksums']}; file not kept.")
    return files


# ── cooccurrence_network: words and themes ────────────────────────────────────

# The multi-word expressions of each corpus are detected once, over the whole country, by the Diarios Explorer
# (tools/expresiones_precalculadas.py) and published next to its page; they are valid for one dataset version.
EXPRESSIONS_URL = "https://rodrodr.github.io/parlaibero-explorer/expresiones/"
EXPRESSIONS_VERSION = 2               # VERSION of the explorer's engine/expresiones.js that cooccurrence.py ports
_EXPRESSIONS: dict[str, tuple] = {}
DEVIATIONS = [
    "Reference counts come from every row of the country in the MCP's database (the explorer reads its FTS5 index of "
    "the same rows; the two tokenizers differ by about one token in a million).",
    "Speech only uses the explorer's fast segmentation (parenthetical stage directions and upper-case lines out) for "
    "any library; the explorer applies its full parser of the record below 25 million characters.",
    "Rows the corpus marks as not speech (dm_speech = 0) are not in the library's text.",
    "Displayed forms are the country's most frequent written form of each word.",
]


def cooccurrence_network(f: analysis.Filters, vocabulary: int = 250, unit: str = "intervention", fragment: int = 20,
                         neighbours: int = 10, resolution: float = 1.0, seed: int = 1, g2_min: float = 10.83,
                         exclude: list[str] | None = None, expressions: bool = True, speech_only: bool = True,
                         output_dir: str | None = None, formats: list[str] | None = None, overwrite: bool = False,
                         max_node_size: float = 12, max_edge_width: float = 1.5, layout: str = "force",
                         entities=None) -> dict:
    """Word co-occurrence network and themes of a library, one per country (cooccurrence.py: the Diarios
    Explorer's method)."""
    if entities:
        raise ValueError("cooccurrence_network is the network of WORDS: it finds them in the library's vocabulary "
                         "and clusters them into themes, and takes no entities. For people and institutions mentioned "
                         "in the same intervention use comention_network; for who names whom, mention_network.")
    if f.library is None:
        raise ValueError("cooccurrence_network needs a library (library=…)")
    if unit not in ("intervention", "fragment"):
        raise ValueError("unit must be 'intervention' or 'fragment'")
    if not 3 <= int(vocabulary) <= 500:
        raise ValueError("vocabulary must be between 3 and 500 terms")
    view = _view(max_node_size, max_edge_width, layout)
    t0 = time.time()
    opts = {"vocabulary": int(vocabulary), "unit": unit, "fragment": int(fragment), "neighbours": int(neighbours),
            "resolution": float(resolution), "seed": int(seed), "g2_min": float(g2_min), "exclude": list(exclude or [])}
    params: list = []
    where = f.where(params, alias="i")
    cols, rows, truncated = store.run_query(
        f"SELECT i.country, i.row_n, i.id_int, i.date, i.speaker_name, i.party, i.text FROM interventions i "
        f"WHERE true{where} ORDER BY i.country, i.row_n", params, max_rows=MAX_ROWS, timeout_s=TIME_BUDGET_S)
    if truncated:
        raise ValueError(f"The library has more than {MAX_ROWS:,} interventions after the filters: narrow it down.")
    if not rows:
        raise store.NoData("The library has no interventions under these filters.")
    by_country = defaultdict(list)
    for r in rows:
        by_country[r[0]].append(dict(zip(cols, r)))
    formats = [x.lower() for x in (formats or ["html", "csv", "json", "md"])]
    out_dir = _out_dir(output_dir)
    results = {iso: _word_network(iso, part, opts, expressions, speech_only, f, view)
               for iso, part in sorted(by_country.items())}
    files = []
    if out_dir:
        from . import network_html
        base = store_slug(f.library_name or "library") + "_words"
        for iso, res in results.items():
            stem = base + ("" if len(results) == 1 else f"_{iso}")
            files += _write_word_outputs(out_dir, stem, res, formats, overwrite, network_html.words_page)
    notes = []
    if len(results) > 1:
        notes.append("One network per country: the vocabulary is each chamber's lexicon against its own corpus.")
    notes += analysis._long_turn_notes(f)
    return {"library": f.library_name, "networks": {iso: _word_summary(r) for iso, r in results.items()},
            "files": files, "notes": notes, "seconds": round(time.time() - t0, 1),
            "datasets": analysis._versions(results)}


def _reference_counts(iso: str, terms: list[str]) -> tuple[dict[str, int], int]:
    """Occurrences in every row of the country of the given folded terms, and the country's total of tokens."""
    if not terms:
        return {}, 0
    tok = r"regexp_extract_all(lower(coalesce(text, '')), '[\pL\pN\pM]+')"
    _, rows, _ = store.run_query(
        f"SELECT f, count(*) FROM (SELECT strip_accents(x) AS f FROM (SELECT unnest({tok}) AS x FROM interventions "
        f"WHERE country = ?)) WHERE f IN (SELECT unnest(?::VARCHAR[])) GROUP BY f", [iso, terms],
        max_rows=len(terms) + 10, timeout_s=TIME_BUDGET_S)
    _, tot, _ = store.run_query(f"SELECT sum(len({tok})) FROM interventions WHERE country = ?", [iso],
                                timeout_s=TIME_BUDGET_S)
    return {f: int(n) for f, n in rows}, int(tot[0][0] or 0)


def _display_forms(iso: str, terms: list[str]) -> dict[str, str]:
    if not terms:
        return {}
    _, rows, _ = store.run_query("SELECT fold, word FROM vocab WHERE country = ? AND fold IN (SELECT unnest(?::VARCHAR[]))",
                                 [iso, terms], max_rows=len(terms) + 10)
    return {f: w for f, w in rows}


def _expression_index(iso: str) -> tuple:
    """The explorer's precomputed expressions for the loaded dataset of a country: (index or None, record). Cached
    under the MCP's home; checked against the dataset's DOI, version and file size and the package's SHA-256."""
    if iso in _EXPRESSIONS:
        return _EXPRESSIONS[iso]
    import gzip
    import hashlib
    from . import dataverse
    info = {"source": EXPRESSIONS_URL, "used": False}
    cache = store.HOME / "cache" / "expresiones"
    try:
        cache.mkdir(parents=True, exist_ok=True)
        with dataverse._client(timeout=60) as cl:
            r = cl.get(EXPRESSIONS_URL + "indice.json")
            r.raise_for_status()
            index = r.json()
            if index.get("version_expresiones") != EXPRESSIONS_VERSION:
                raise ValueError(f"the published tables are of version {index.get('version_expresiones')}, this "
                                 f"engine reads version {EXPRESSIONS_VERSION}")
            e = (index.get("paises") or {}).get(iso)
            if not e:
                raise ValueError(f"no table for {iso}")
            loaded = store.loaded().get(iso) or {}
            built, have = e.get("dataverse") or {}, {"doi": COUNTRIES[iso][2], "version": loaded.get("version")}
            if built.get("doi") != have["doi"] or str(built.get("version")) != str(have["version"]):
                raise ValueError(f"the table was built for {built.get('doi')} v{built.get('version')}; the loaded "
                                 f"dataset is {have['doi']} v{have['version']}")
            csv_file = store.DATA / iso / e["csv"]["nombre"]
            if csv_file.exists() and csv_file.stat().st_size != e["csv"]["bytes"]:
                raise ValueError(f"{csv_file.name} has {csv_file.stat().st_size:,} bytes; the table was built from "
                                 f"one of {e['csv']['bytes']:,}")
            path = cache / e["archivo"]
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != e["sha256"]:
                r = cl.get(EXPRESSIONS_URL + e["archivo"])
                r.raise_for_status()
                if hashlib.sha256(r.content).hexdigest() != e["sha256"]:
                    raise ValueError("the downloaded table does not match the SHA-256 of the index")
                path.write_bytes(r.content)
        pq = json.loads(gzip.decompress(path.read_bytes()))
        if pq.get("version") != EXPRESSIONS_VERSION or pq.get("columnas", [])[:5] != ["forma", "mostrar", "n_tokens",
                                                                                     "n_palabras", "frecuencia"]:
            raise ValueError("the table does not have the expected version or columns")
        ix = co.ExpressionIndex(pq["filas"], iso, pq.get("meta"))
        info.update(used=True, expressions=ix.n, file=e["archivo"], sha256=e["sha256"], built_for=e["dataverse"],
                    generated=index.get("generado"), detection=pq.get("meta"))
        _EXPRESSIONS[iso] = (ix, info)
    except Exception as err:      # offline, another version of the data…: the network is built without expressions
        info["reason"] = f"expressions not used: {err}"
        _EXPRESSIONS[iso] = (None, info)
    return _EXPRESSIONS[iso]


def _word_network(iso, rows, opts, use_expressions, speech_only, f, view) -> dict:
    texts, excluded = [], Counter()
    for r in rows:
        if speech_only:
            t, ex = co.speech_text(r["text"] or "")
            excluded.update(ex)
        else:
            t = r["text"] or ""
        texts.append(t)
    counts, c = co.count_terms(texts)
    reference, corpus_tokens = _reference_counts(iso, sorted(t for t, k in counts.items()
                                                             if k >= co.LEXICON["min_freq"]))
    lex = co.keyness(counts, c, corpus_tokens, reference, co.LEXICON["min_freq"], co.THRESHOLD,
                     co.LEXICON["limit"], co.LEXICON["limit_negative"])
    ix, expr_info = _expression_index(iso) if use_expressions else (None, {"used": False, "reason": "expressions=false"})
    if ix:
        co.add_expressions(lex, ix, texts, co.LEXICON["min_freq"], co.LEXICON["limit"], co.LEXICON["limit_negative"])
    shown = _display_forms(iso, [t["term"] for t in lex["terms"][:600] if not t.get("expression")])
    terms = [{"term": t["term"], "display": t.get("display") or shown.get(t["term"]) or t["term"], "freq": t["freq"],
              "g2": t["g2"], "expression": bool(t.get("expression"))} for t in lex["terms"]]
    docs = [{"id": r["row_n"], "text": t, "party": r["party"]} for r, t in zip(rows, texts)]
    net = co.network(docs, terms, iso, opts, ix)
    for e in net["edges"]:
        e["source"], e["target"] = net["nodes"][e["a"]]["term"], net["nodes"][e["b"]]["term"]
    party_words = {x["party"]: x["words"] for x in (net.get("parties") or {}).get("top", [])}
    for t in net["themes"]:
        for x in t["parties"]["top"]:
            pw = party_words.get(x["party"])
            x["party_words"] = pw
            x["per_1000"] = round(1000 * x["words"] / pw, 3) if pw else None
    meta = {r["row_n"]: r for r in rows}
    read = {x["id"] for x in net.get("reading", {}).get("global", [])} | {
        x["id"] for t in net["themes"] for x in t["reading"]}
    lang = co.language_of(iso)
    return {
        "country": iso, "N": len(rows), **net,
        "metadata": {str(i): {"id_int": meta[i]["id_int"], "date": str(meta[i]["date"]) if meta[i]["date"] else None,
                              "speaker": meta[i]["speaker_name"], "party": meta[i]["party"]} for i in sorted(read)},
        "lexicon": {"tokens": c, "corpus_tokens": corpus_tokens, "reference_tokens": lex["reference_tokens"],
                    "candidates": lex["candidates"], "over_used": lex.get("n_positive", 0),
                    "with_expressions": lex.get("expressions"), "incoherent_terms": len(lex["incoherent"]),
                    "text_tokens_left_out": dict(excluded)},
        "parameters": {**opts, "speech_only": speech_only, "text": "speech only (fast segmentation)" if speech_only
                       else "full text", "lexicon": dict(co.LEXICON, threshold=co.THRESHOLD),
                       "stopwords": co.stopwords_source(lang), "expressions": expr_info, "filters": analysis._filters_dict(f),
                       "method": "port of the Diarios Explorer's engine/coocurrencia.js (parlaibero-explorer)",
                       "deviations": DEVIATIONS, "engine": f"parlaibero-mcp {__version__}", "generated": _now(),
                       "view": view},
        "checksums": {"sum_co": sum(e["co"] for e in net["edges"]), "sum_weight": round(sum(e["weight"] for e in net["edges"]), 4),
                      "nodes": len(net["nodes"]), "themes": len(net["themes"])},
        "citation": _citation_lines([iso]),
    }


def _word_summary(res: dict) -> dict:
    """What the agent reads: the themes with their terms, coverage and parties, and how the network was made."""
    if not res["themes"]:
        return {"N": res["N"], "warning": res.get("warning") or "No themes.", "vocabulary": res["vocabulary"],
                "parameters": res["parameters"]}
    big = {x["party"] for x in res["parties"]["top"] if x["words"] >= 0.01 * max(1, res["parties"]["words_total"])}
    themes = []
    for t in res["themes"]:
        rates = sorted((x for x in t["parties"]["top"] if x["party"] in big and x["per_1000"] is not None),
                       key=lambda x: -x["per_1000"])
        themes.append({"theme": t["id"] + 1, "label": t["label"], "n_terms": t["n_terms"],
                       "terms": [x["display"] for x in t["terms"][:15]], "pct_interventions": t["pct_interventions"],
                       "pct_words_dominated": t["weight_pct"], "g2_mean": t["g2_mean"],
                       "parties_most": [(x["party"], x["per_1000"]) for x in rates[:4]],
                       "parties_least": [(x["party"], x["per_1000"]) for x in rates[-3:]],
                       "read_first": [res["metadata"][str(x["id"])]["id_int"] for x in t["reading"][:3]]})
    s = res["stats"]
    return {"N": res["N"], "vocabulary": res["vocabulary"], "nodes": len([n for n in res["nodes"] if n["degree"]]),
            "edges": s["kept_edges"], "themes": themes, "loose_terms": [x["display"] for x in res["loose_terms"]],
            "stats": s, "lexicon": res["lexicon"], "expressions": res["parameters"]["expressions"],
            "checksums": res["checksums"],
            "reading": ("Themes are communities of words that occur together in the same intervention more than chance "
                        "(signed G² ≥ 10.83, each term's strongest neighbours). Themes are ordered by how characteristic "
                        "their terms are of the library (mean G² in the lexicon). A party's rate is the theme's words per "
                        "1,000 words that party says in the library (parties with at least 1 % of the words). "
                        "read_first: the interventions that concentrate the theme's vocabulary (BM25)."),
            "notes": res["parameters"]["deviations"]}


def _write_word_outputs(out_dir: Path, stem: str, res: dict, formats: list[str], overwrite: bool, page) -> list[str]:
    files = []
    if "csv" in formats:
        nkeys = ["term", "display", "expression", "theme", "freq", "g2_lexicon", "df_unit", "df_intervention",
                 "strength", "degree"]
        files.append(_write_csv(out_dir / f"{stem}_nodes.csv", nkeys, [{**n, "theme": n["theme"] + 1 if n["theme"] >= 0
                                                                         else None} for n in res["nodes"]], overwrite))
        files.append(_write_csv(out_dir / f"{stem}_edges.csv", ["source", "target", "co", "expected", "g2", "weight"],
                                res["edges"], overwrite))
        files.append(_write_csv(out_dir / f"{stem}_themes.csv",
                                ["theme", "label", "n_terms", "g2_mean", "interventions", "pct_interventions",
                                 "weight_pct", "terms"],
                                [{**t, "theme": t["id"] + 1, "terms": ", ".join(x["display"] for x in t["terms"])}
                                 for t in res["themes"]], overwrite))
    if "json" in formats:
        files.append(_write(out_dir / f"{stem}.json", json.dumps(res, ensure_ascii=False, indent=1, default=str),
                            overwrite))
    if "md" in formats:
        files.append(_write(out_dir / f"{stem}_summary.md", _word_markdown(res), overwrite))
    if "html" in formats:
        path = out_dir / f"{stem}.html"
        files.append(_write(path, page(res), overwrite))
        text = path.read_text(encoding="utf-8")
        m = re.search(r'<script id="network-data" type="application/json">(.*?)</script>', text, re.S)
        data = json.loads(m.group(1)) if m else {"edges": []}
        got = {"sum_co": sum(e["co"] for e in data["edges"]), "sum_weight": round(sum(e["weight"] for e in data["edges"]), 4),
               "nodes": len(data.get("nodes", [])), "themes": len(data.get("themes", []))}
        if got != res["checksums"]:
            path.unlink(missing_ok=True)
            raise RuntimeError(f"Self-check failed: the HTML data {got} differ from the computed {res['checksums']}. "
                               f"The file was not kept.")
    return files


def _word_markdown(res: dict) -> str:
    s = _word_summary(res)
    p = res["parameters"]
    L = [f"# Word co-occurrence network and themes · {res['country']}", "",
         f"- Interventions: {res['N']:,} · vocabulary: {res['vocabulary']['used']} terms · edges: {res['stats']['kept_edges']}"
         f" · themes: {res['stats']['themes']} · modularity {res['stats']['modularity']}",
         f"- Unit: {p['unit']}{' of ' + str(p['fragment']) + ' tokens' if p['unit'] == 'fragment' else ''} · neighbours "
         f"k = {p['neighbours']} · G² ≥ {p['g2_min']} · Leiden γ = {p['resolution']}, seed {p['seed']}",
         f"- Text: {p['text']} · stopwords: {p['stopwords']['source']} ({p['stopwords']['language']}, "
         f"{p['stopwords']['license']}) · expressions: "
         + (f"{p['expressions']['expressions']:,} of the corpus" if p["expressions"].get("used")
            else p["expressions"].get("reason", "no")), "", "## Themes", ""]
    for t in s.get("themes", []):
        L += [f"### {t['theme']}. {t['label']}", "",
              f"{t['n_terms']} terms · {t['pct_interventions']} % of the interventions · {t['pct_words_dominated']} % of "
              f"the words in interventions it dominates · mean G² {t['g2_mean']}", "",
              "Terms: " + ", ".join(t["terms"]), "",
              "Parties that say it most (per 1,000 of their words): " + ", ".join(f"{a} {b}" for a, b in t["parties_most"]),
              "", "Read first: " + ", ".join(t["read_first"]), ""]
    if s.get("loose_terms"):
        L += ["## Loose terms", "", ", ".join(s["loose_terms"]), ""]
    L += ["## Reading", "", s.get("reading", ""), "", "## Method", "", p["method"] + ".", ""]
    L += [f"- {d}" for d in p["deviations"]]
    L += ["", "## Data", ""] + [f"- {c}" for c in res["citation"]]
    L += ["", f"Generated with {p['engine']} on {p['generated']}."]
    return "\n".join(L) + "\n"
