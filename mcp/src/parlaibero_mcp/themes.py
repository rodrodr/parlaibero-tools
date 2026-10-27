"""Reading the themes of a word network (cooccurrence_network): the evidence for each theme, and the checks of what
an agent writes after reading it. The engine prepares and checks; the reading is the agent's, under the protocol of
the resource parlaibero://methods/networks (§ 4). Nothing here calls a language model.

theme_dossier(network): from a saved <library>_words.json it rebuilds the rows and texts the network read and
proves it (each theme's interventions and dominated words must equal the file's). Per theme: core and bridge terms,
links to other themes, who sustains it (speakers, sessions), its profile by year, the words that distinguish each
group inside it (signed G²), a reading sample stratified by group and year with passages cut from the record's text,
and its stability when Leiden is re-run on the saved graph. It writes a codebook template for the agent to fill.

check_codebook(codebook): checks the filled codebook (schema, theme numbers, every anchor's id and verbatim quote
against the record), draws a blind sample of passages to code by hand and by the agent, and with both codings gives
the agreement (Cohen's κ) and each label's share by group with Wilson intervals.

The last step, the report that interprets the themes for the researcher, is report.theme_report.

Themes are numbered from 1, as in the page, the CSV files and the summary (the JSON stores them from 0). Samples are
ordered by a hash of (seed, id_int), so the same seed draws the same sample on any machine.
"""
from __future__ import annotations

import csv
import dataclasses
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

from . import __version__, analysis, cooccurrence as co, leiden, library as libmod, networks, profile, store

SCHEMA = "parlaibero-codebook/1"
VERDICTS = ("theme", "merge", "split", "artefact")
STANCES = ("affirms", "contests", "cites")
ROBUST, FRAGILE = 0.8, 0.5       # mean best Jaccard of a theme over the Leiden re-runs
CONCENTRATED = 0.5               # share of a theme's interventions given by one speaker or held in one session
MIN_QUOTE_WORDS = 5
PASSAGE_CHARS = 900
MIN_GROUP_CODED = 10            # coded passages under which a group's share is marked too few to read
CATCH_ALL = 0.9                  # share of the library a theme touches above which it is probably its definition
PROTOTYPES = 3                   # interventions the network ranks first for a theme (BM25), read before the sample
NO_GROUP = "(no group)"
Z95 = 1.959964

PROTOCOL = """\
Read each theme with theme_dossier(network, theme=k), then fill the codebook file (one entry per theme):
1. verdict: 'theme' (a subject of debate), 'merge' (the same subject as merge_with), 'split' (two subjects: say
   which in the definition) or 'artefact' (procedure, one debate, one speaker, noise of the text).
2. For a theme: a label and a definition in your own words, what is included and what is excluded, and anchors:
   id_int plus a quote copied VERBATIM from a passage (contiguous text, at least five words, without the '…' marks).
3. Frames inside the theme (Entman: problem, cause, evaluation, remedy; a frame need not have all four), each with
   the groups that use it and anchors whose stance says whether the speaker affirms the frame, contests it or only
   cites it. A count of a frame's words cannot tell these apart; the stance can.
4. Base every claim on the dossier's passages; a theme flagged as concentrated or fragile needs saying so.
Then run check_codebook(codebook): it verifies every quote against the record and draws the sample to code.
5. Report: theme_report(codebook) writes a spec template; write the interpretation there for the researcher (figures
   as placeholders, quotes as references to the codebook's anchors) and render it with theme_report(codebook,
   report=spec), which checks both and writes the report as Markdown and HTML."""


# ── loading and rebuilding what the network read ─────────────────────────────

def _absolute(path: str, what: str) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        raise ValueError(f"{what} must be an ABSOLUTE path")
    if not p.exists():
        raise FileNotFoundError(f"{p} does not exist")
    return p


def _load_network(path: str) -> tuple[Path, dict]:
    p = _absolute(path, "network")
    try:
        net = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"{p.name} is not JSON: {e}") from e
    need = {"country", "N", "nodes", "edges", "themes", "parameters", "checksums", "lexicon"}
    if not isinstance(net, dict) or not need <= set(net) or "unit" not in (net.get("parameters") or {}):
        raise ValueError(f"{p.name} is not a word network: the dossier reads the <library>_words.json that "
                         "cooccurrence_network writes (not a comention or mention network)")
    if not net["themes"]:
        raise ValueError(f"{p.name} has no themes to read")
    return p, net


def _filters(net: dict) -> analysis.Filters:
    d = dict(net["parameters"].get("filters") or {})
    name = d.pop("library", None)
    if not name:
        raise ValueError("The network was not built on a library")
    lid, _ = libmod.resolve(name)
    keep = {f.name for f in dataclasses.fields(analysis.Filters)} - {"countries", "library", "library_name"}
    return analysis.Filters(countries=[net["country"]], library=lid, library_name=name,
                            **{k: v for k, v in d.items() if k in keep})


def _rebuild(net: dict, group_by: str) -> list[dict]:
    """The library's rows of the network's country, in the network's order, with the tokens it counted and the
    themes each one touches; raises if they are not the rows the network read."""
    if group_by not in profile.ACTIVE.groups():
        raise ValueError(f"group_by must be one of {', '.join(profile.ACTIVE.groups())}")
    f = _filters(net)
    iso, p = net["country"], net["parameters"]
    ix = None
    if (p.get("expressions") or {}).get("used"):
        ix, info = networks._expression_index(iso)
        if ix is None or info.get("sha256") != p["expressions"].get("sha256"):
            raise ValueError("The network joined the corpus's multi-word expressions and that table is not available "
                             f"now ({info.get('reason') or 'another table'}): the dossier cannot rebuild what it read")
    params: list = []
    where = f.where(params, alias="i")
    cols, rows, truncated = store.run_query(
        f"SELECT i.row_n, i.id_int, i.id_session, i.date, i.speaker_name, i.party, i.{group_by} AS grp, i.text "
        f"FROM interventions i WHERE true{where} ORDER BY i.country, i.row_n", params,
        max_rows=networks.MAX_ROWS, timeout_s=networks.TIME_BUDGET_S)
    if truncated:
        raise ValueError(f"The library has more than {networks.MAX_ROWS:,} interventions after the filters")
    docs = []
    for r in rows:
        d = dict(zip(cols, r))
        d["text"] = d["text"] or ""
        read = co.speech_text(d["text"])[0] if p.get("speech_only", True) else d["text"]
        d["tokens"] = ix.units_text(read) if ix else co.tokenize(read)
        g = str(d["grp"] or "").strip()
        d["group"] = NO_GROUP if not g or re.fullmatch(r"(\?|sin identificar)", g, re.I) else g   # as the network
        d["year"] = str(d["date"])[:4] if d["date"] else "?"
        docs.append(d)
    _assign(net, docs)
    _self_check(net, docs)
    return docs


def _assign(net: dict, docs: list[dict]) -> None:
    """Themes each intervention touches (distinct terms of each) and the one it is dominated by, with the rule of
    cooccurrence.network: two or more of its terms, the largest share of the theme's terms, no tie."""
    index = {n["term"]: n["i"] for n in net["nodes"]}
    theme_of = [n["theme"] for n in net["nodes"]]
    size = {t["id"]: t["n_terms"] for t in net["themes"]}
    for d in docs:
        present = {index[w] for w in d["tokens"] if w in index}
        per = Counter(theme_of[i] for i in present if theme_of[i] >= 0)
        best, share, tie = -1, 0.0, False
        for c, k in per.items():
            if k < 2:
                continue
            x = k / size[c]
            if x > share:
                best, share, tie = c, x, False
            elif x == share:
                tie = True
        d["themes"] = dict(per)
        d["dominant"] = best if best >= 0 and not tie else -1


def _self_check(net: dict, docs: list[dict]) -> None:
    diffs = []
    if len(docs) != net["N"]:
        diffs.append(f"{len(docs):,} interventions now, {net['N']:,} in the network")
    else:
        for t in net["themes"]:
            touching = sum(1 for d in docs if t["id"] in d["themes"])
            words = sum(len(d["tokens"]) for d in docs if d["dominant"] == t["id"])
            if touching != t["interventions"] or words != t["words_dominated"]:
                diffs.append(f"theme {t['id'] + 1}: {touching} interventions and {words} dominated words now, "
                             f"{t['interventions']} and {t['words_dominated']} in the network")
    if diffs:
        raise ValueError("The library or the data changed since the network was built (" + "; ".join(diffs[:5])
                         + "): build the network again and read the new file")


# ── per theme ─────────────────────────────────────────────────────────────────

def _links(net: dict) -> tuple[dict, dict]:
    """Weight of each term's edges to other themes (or to loose terms, -1), and between pairs of themes."""
    theme_of = [n["theme"] for n in net["nodes"]]
    outside: dict[int, Counter] = defaultdict(Counter)
    between: Counter = Counter()
    for e in net["edges"]:
        a, b, w = e["a"], e["b"], float(e["weight"])
        ta, tb = theme_of[a], theme_of[b]
        if ta != tb:
            outside[a][tb] += w
            outside[b][ta] += w
            if ta >= 0 and tb >= 0:
                between[(min(ta, tb), max(ta, tb))] += w
    return outside, between


def _stability(net: dict, runs: int) -> dict[int, dict]:
    """Leiden re-run on the saved graph: with `runs` seeds (the network's first) at its resolution, and once at 0.6
    and 1.6 times it. Each theme is matched by Jaccard over its terms, not by number. It measures the partition of
    this graph, not the choice of vocabulary; weights are the file's (4 decimals)."""
    V = len(net["nodes"])
    edges = [[e["a"], e["b"], float(e["weight"])] for e in net["edges"]]
    gamma, seed0 = float(net["parameters"]["resolution"]), int(net["parameters"]["seed"])
    themes = {t["id"]: {x["i"] for x in t["terms"]} for t in net["themes"]}

    def parts(gam, seed):
        groups = defaultdict(set)
        for i, c in enumerate(leiden.communities(V, edges, gam, seed)["community"]):
            groups[c].add(i)
        return list(groups.values())

    seeded = [parts(gamma, seed0 + s) for s in range(runs)]
    low, high = parts(gamma * 0.6, seed0), parts(gamma * 1.6, seed0)
    out = {}
    for k, T in themes.items():
        js = [max(len(T & C) / len(T | C) for C in P) for P in seeded]
        mean = sum(js) / len(js)
        hold = max(low, key=lambda C: (len(T & C), -min(C)))
        merges = sorted(j + 1 for j, U in themes.items() if j != k and len(U & hold) >= 0.5 * len(U))
        pieces = sum(1 for C in high if len(T & C) >= max(2, 0.2 * len(T)))
        out[k] = {"label": "robust" if mean >= ROBUST else "fragile" if mean < FRAGILE else "moderate",
                  "mean_jaccard": round(mean, 3), "min_jaccard": round(min(js), 3), "runs": runs,
                  "reproduced": js[0] == 1.0, "at_0.6_resolution_joins": merges,
                  "at_1.6_resolution_pieces": pieces}
    return out


def _concentration(tdocs: list[dict]) -> dict:
    n = len(tdocs)
    sp = Counter(d["speaker_name"] for d in tdocs if d["speaker_name"])
    se = Counter(d["id_session"] for d in tdocs if d["id_session"])
    top_sp, n_sp = sp.most_common(1)[0] if sp else (None, 0)
    top_se, n_se = se.most_common(1)[0] if se else (None, 0)
    out = {"interventions": n, "speakers": len(sp), "sessions": len(se),
           "top_speaker": top_sp, "top_speaker_share": round(n_sp / n, 3) if n else 0,
           "top_session": top_se, "top_session_share": round(n_se / n, 3) if n else 0, "flags": []}
    if n and n_sp / n >= CONCENTRATED:
        out["flags"].append(f"one speaker gives {n_sp / n:.0%} of its interventions")
    if n and n_se / n >= CONCENTRATED:
        out["flags"].append(f"one session holds {n_se / n:.0%} of its interventions")
    return out


def _years(tdocs: list[dict], docs: list[dict]) -> list[dict]:
    all_y = Counter(d["year"] for d in docs)
    th_y = Counter(d["year"] for d in tdocs)
    return [{"year": y, "interventions": th_y[y], "pct_of_year": round(100 * th_y[y] / all_y[y], 1)}
            for y in sorted(all_y) if th_y[y]]


def _group_words(tdocs: list[dict], lang: str, g2_min: float, top: int = 12, min_docs: int = 5,
                 min_freq: int = 5) -> list[dict]:
    """Inside the theme's interventions: the content words each group says more than the rest of the theme
    (signed G², the network's threshold), for groups with at least `min_docs` interventions."""
    kind = co.type_of(lang)
    words: dict[str, Counter] = defaultdict(Counter)
    tokens, ndocs = Counter(), Counter()
    for d in tdocs:
        g = d["group"]
        ndocs[g] += 1
        tokens[g] += len(d["tokens"])
        words[g].update(w for w in d["tokens"] if kind(w) == 2)
    total = Counter()
    for c in words.values():
        total.update(c)
    T = sum(tokens.values())
    out = []
    for g in sorted(ndocs, key=lambda g: (-ndocs[g], g)):
        c, rest = tokens[g], T - tokens[g]
        if ndocs[g] < min_docs or rest <= 0 or c <= 0:
            continue
        rows = []
        for w, a in words[g].items():
            if a < min_freq:
                continue
            g2 = co.g2_signed(a, total[w] - a, c, rest)
            if g2 >= g2_min:
                rows.append({"term": w, "freq": a, "rest_of_theme": total[w] - a, "g2": round(g2, 2)})
        rows.sort(key=lambda x: (-x["g2"], x["term"]))
        out.append({"group": g, "interventions": ndocs[g], "words": c, "distinctive": rows[:top]})
    return out


# ── passages and samples ──────────────────────────────────────────────────────

def _order(seed: int, id_int) -> str:
    return hashlib.sha256(f"{seed}:{id_int}".encode()).hexdigest()


def _round_robin(docs: list[dict], n: int, seed: int, key) -> list[dict]:
    """One from each stratum in turn (largest strata first), each stratum in hash order: spread, not proportion."""
    strata = defaultdict(list)
    for d in docs:
        strata[key(d)].append(d)
    for s in strata.values():
        s.sort(key=lambda d: _order(seed, d["id_int"]))
    order = sorted(strata, key=lambda s: (-len(strata[s]), str(s)))
    out, cur = [], dict.fromkeys(order, 0)
    while len(out) < n:
        took = False
        for s in order:
            if len(out) < n and cur[s] < len(strata[s]):
                out.append(strata[s][cur[s]])
                cur[s] += 1
                took = True
        if not took:
            break
    return out


def _proportional(docs: list[dict], n: int, seed: int, key) -> tuple[list[dict], dict]:
    """A sample allocated to the strata in proportion to their size (largest remainder, so it weighs itself: a
    small stratum may get none), each stratum in hash order. Returns the sample and each stratum's (size, drawn)."""
    strata = defaultdict(list)
    for d in docs:
        strata[key(d)].append(d)
    for s in strata.values():
        s.sort(key=lambda d: _order(seed, d["id_int"]))
    total, n = len(docs), min(n, len(docs))
    if not total or not n:
        return [], {}
    raw = {s: n * len(v) / total for s, v in strata.items()}
    quota = {s: int(raw[s]) for s in strata}
    for s in sorted(strata, key=lambda s: (-(raw[s] - int(raw[s])), str(s))):
        if sum(quota.values()) >= n:
            break
        if quota[s] < len(strata[s]):
            quota[s] += 1
    out = [d for s in sorted(strata, key=str) for d in strata[s][:quota[s]]]
    out.sort(key=lambda d: _order(seed, d["id_int"]))
    return out, {s: (len(strata[s]), quota[s]) for s in strata}


def _token_spans(text: str) -> list[tuple[int, int, str]]:
    t = text.lower()
    rx = co.TOKEN_FULL if co.RARE.search(t) else co.TOKEN_SIMPLE
    return [(m.start(), m.end(), w if (w := m.group()).isascii() else co.fold_token(w)) for m in rx.finditer(t)]


def _hits(spans, terms) -> list[tuple[int, int]]:
    single = {t for t in terms if " " not in t}
    multi = [t.split(" ") for t in terms if " " in t]
    words = [w for _, _, w in spans]
    out = []
    for i, w in enumerate(words):
        if w in single:
            out.append((i, i))
        for m in multi:
            if words[i:i + len(m)] == m:
                out.append((i, i + len(m) - 1))
    return out


def _cut(text: str, spans, lo: int, hi: int) -> str:
    s = " ".join(text[spans[lo][0]:spans[hi][1]].split())
    more = hi < len(spans) - 1
    if len(s) > PASSAGE_CHARS:
        s, more = s[:PASSAGE_CHARS].rsplit(" ", 1)[0], True
    return ("… " if lo > 0 else "") + s + (" …" if more else "")


def passages(text: str, terms, k: int = 2, window: int = 40) -> tuple[list[str], int]:
    """Up to k passages of the record's text around the densest clusters of the given (folded) terms, located on
    the original text (not the segmented one), so that a quote copied from them is found in the record. Returns
    the passages and the number of hits; without hits, the start of the text."""
    spans = _token_spans(text)
    if not spans:
        return [], 0
    hits = _hits(spans, terms)
    if not hits:
        return [_cut(text, spans, 0, min(len(spans), 2 * window) - 1)], 0
    chosen, used = [], [False] * len(hits)
    for _ in range(k):
        best = None
        for j, (a, b) in enumerate(hits):
            lo, hi = max(0, a - window), min(len(spans) - 1, b + window)
            if used[j] or any(not (hi < x or lo > y) for x, y in chosen):
                continue
            score = sum(1 for x, y in hits if x >= lo and y <= hi)
            if best is None or score > best[0]:
                best = (score, lo, hi)
        if best is None:
            break
        _, lo, hi = best
        chosen.append((lo, hi))
        for j, (x, y) in enumerate(hits):
            if x >= lo and y <= hi:
                used[j] = True
    return [_cut(text, spans, lo, hi) for lo, hi in sorted(chosen)], len(hits)


# ── theme_dossier ─────────────────────────────────────────────────────────────

_CACHE: dict[tuple, dict] = {}


def _write_same(path: Path, data: str, overwrite: bool) -> str:
    """Write, unless the file exists with other content and overwrite is false (the dossier is deterministic: the
    same network and options give the same file)."""
    if path.exists() and not overwrite and path.read_text(encoding="utf-8") != data:
        raise FileExistsError(f"{path} already exists with other content; pass overwrite=true to replace it")
    path.write_text(data, encoding="utf-8")
    return str(path)


def _build(path: Path, net: dict, sample: int, n_passages: int, window: int, group_by: str, runs: int,
           seed: int) -> dict:
    docs = _rebuild(net, group_by)
    iso = net["country"]
    lang = co.language_of(iso)
    by_row = {d["row_n"]: d for d in docs}
    display = {n["term"]: n["display"] for n in net["nodes"]}
    outside, between = _links(net)
    stab = _stability(net, runs)
    g2_min = float(net["parameters"].get("g2_min") or 10.83)
    node = {n["i"]: n for n in net["nodes"]}
    themes = []
    for t in net["themes"]:
        k = t["id"]
        terms = [x["term"] for x in t["terms"]]
        tdocs, basis = [d for d in docs if d["dominant"] == k], "dominated by the theme"
        if not tdocs:
            tdocs, basis = [d for d in docs if d["themes"].get(k, 0) >= 2], "two or more of its terms"
        if not tdocs:
            tdocs, basis = [d for d in docs if d["themes"].get(k)], "any of its terms"
        bridges = []
        for x in t["terms"]:
            o = outside.get(x["i"])
            if not o:
                continue
            ext = sum(o.values())
            to = [j + 1 for j, _ in sorted(((j, w) for j, w in o.items() if j >= 0), key=lambda z: -z[1])[:2]]
            bridges.append({"term": x["display"], "outside_weight": round(ext, 3),
                            "outside_share": round(ext / node[x["i"]]["strength"], 3) if node[x["i"]]["strength"] else 0,
                            "links_to_themes": to})
        bridges.sort(key=lambda b: (-b["outside_weight"], b["term"]))
        linked = sorted(((b if a == k else a, w) for (a, b), w in between.items() if k in (a, b)), key=lambda z: -z[1])
        protos = [by_row[x["id"]] for x in t["reading"][:PROTOTYPES] if x["id"] in by_row]
        seen = {d["id_int"] for d in protos}
        strat = _round_robin([d for d in tdocs if d["id_int"] not in seen], sample, seed,
                             key=lambda d: (d["group"], d["year"]))
        reading = []
        for why, d in [("ranked first by the network (BM25)", d) for d in protos] + \
                      [("stratified by group and year", d) for d in strat]:
            ps, nh = passages(d["text"], terms, n_passages, window)
            reading.append({"id_int": d["id_int"], "date": str(d["date"]) if d["date"] else None,
                            "speaker": d["speaker_name"], "group": d["group"], "words": len(d["tokens"]),
                            "theme_terms": d["themes"].get(k, 0), "hits": nh, "why": why, "passages": ps})
        themes.append({
            "theme": k + 1, "page_label": t["label"], "n_terms": t["n_terms"], "g2_mean": t["g2_mean"],
            "pct_interventions": t["pct_interventions"], "weight_pct": t["weight_pct"],
            "core_terms": [{"term": x["display"], "internal_strength": x["internal_strength"],
                            "g2": node[x["i"]]["g2_lexicon"]} for x in t["terms"][:15]],
            "bridge_terms": bridges[:5],
            "linked_themes": [{"theme": j + 1, "weight": round(w, 3)} for j, w in linked[:3]],
            "interventions": {"touching": t["interventions"], "dominated": sum(1 for d in docs if d["dominant"] == k),
                              "read_here": len(tdocs), "basis": basis},
            "notes": [f"it touches {t['interventions'] / net['N']:.0%} of the library's interventions: probably the "
                      "words that define the library; leave them out with exclude and build the network again"]
                     if t["interventions"] >= CATCH_ALL * net["N"] else [],
            "concentration": _concentration(tdocs),
            "years": _years(tdocs, docs),
            "groups": _group_words(tdocs, lang, g2_min),
            "stability": stab[k],
            "reading": reading,
        })
    shown = networks._display_forms(iso, sorted({x["term"] for th in themes for g in th["groups"]
                                                 for x in g["distinctive"] if " " not in x["term"]}))
    for th in themes:
        for g in th["groups"]:
            for x in g["distinctive"]:
                x["term"] = display.get(x["term"]) or shown.get(x["term"]) or x["term"]
    p = net["parameters"]
    return {
        "network": str(path), "library": p["filters"].get("library"), "country": iso, "N": net["N"],
        "checksums": net["checksums"],
        "self_check": f"the {net['N']:,} interventions and every theme's interventions and dominated words equal "
                      "the network's",
        "options": {"sample": sample, "passages": n_passages, "window": window, "group_by": group_by,
                    "stability_runs": runs, "seed": seed},
        "network_parameters": {k: p.get(k) for k in ("vocabulary", "unit", "fragment", "neighbours", "resolution",
                                                       "seed", "g2_min", "exclude", "speech_only")},
        "thresholds": {"robust": f"mean Jaccard ≥ {ROBUST}", "fragile": f"mean Jaccard < {FRAGILE}",
                       "concentrated": f"one speaker or session ≥ {CONCENTRATED:.0%} of its interventions",
                       "group_words": f"signed G² ≥ {g2_min} against the rest of the theme, ≥ 5 occurrences, groups "
                                      "with ≥ 5 interventions"},
        "themes": themes, "protocol": PROTOCOL, "engine": f"parlaibero-mcp {__version__}",
    }


def _overview(th: dict) -> dict:
    return {"theme": th["theme"], "page_label": th["page_label"], "n_terms": th["n_terms"],
            "interventions": th["interventions"], "notes": th["notes"],
            "core_terms": [x["term"] for x in th["core_terms"][:8]],
            "bridge_terms": [x["term"] for x in th["bridge_terms"][:3]], "linked_themes": th["linked_themes"],
            "concentration": {k: th["concentration"][k] for k in ("speakers", "sessions", "top_speaker_share",
                                                                 "top_session_share", "flags")},
            "stability": {k: th["stability"][k] for k in ("label", "mean_jaccard", "reproduced",
                                                          "at_0.6_resolution_joins", "at_1.6_resolution_pieces")},
            "groups": [{"group": g["group"], "interventions": g["interventions"],
                        "distinctive": [x["term"] for x in g["distinctive"][:5]]} for g in th["groups"]],
            "reading_sample": len(th["reading"])}


def _template(dossier: dict) -> dict:
    return {
        "schema": SCHEMA,
        "network": {"file": dossier["network"], "library": dossier["library"], "country": dossier["country"],
                    "N": dossier["N"], "checksums": dossier["checksums"]},
        "reader": {"who": "", "model": "", "date": "", "notes": ""},
        "values": {"verdict": list(VERDICTS), "stance": list(STANCES)},
        "themes": [{"theme": th["theme"], "page_label": th["page_label"], "verdict": "", "merge_with": [],
                    "label": "", "definition": "", "include": "", "exclude": "", "anchors": [], "frames": []}
                   for th in dossier["themes"]],
        "example_entry": {
            "theme": 0, "verdict": "theme", "merge_with": [], "label": "…", "definition": "…", "include": "…",
            "exclude": "…", "anchors": [{"id_int": "…", "quote": "five or more words copied verbatim"}],
            "frames": [{"name": "…", "problem": "…", "cause": "…", "evaluation": "…", "remedy": "…",
                        "groups": ["…"], "anchors": [{"id_int": "…", "quote": "…", "stance": "affirms"}]}]},
    }


def _markdown(dz: dict) -> str:
    L = [f"# Theme dossier · {dz['library']} · {dz['country']}", "",
         f"Network: `{dz['network']}`. Self-check: {dz['self_check']}.", "", "## How to read it", "", dz["protocol"], ""]
    for th in dz["themes"]:
        c, s = th["concentration"], th["stability"]
        L += [f"## Theme {th['theme']} · {th['page_label']}", "",
              f"{th['n_terms']} terms · {th['interventions']['touching']} interventions touch it, "
              f"{th['interventions']['dominated']} are dominated by it · stability: {s['label']} (mean Jaccard "
              f"{s['mean_jaccard']} over {s['runs']} seeds; at 0.6γ joins {s['at_0.6_resolution_joins'] or 'no other'}; "
              f"at 1.6γ {s['at_1.6_resolution_pieces']} piece(s))", "",
              *[x for n in th["notes"] for x in (f"**Note:** {n}.", "")],
              "**Core terms:** " + ", ".join(x["term"] for x in th["core_terms"]), "",
              "**Bridge terms:** " + (", ".join(f"{x['term']} (→ {', '.join(map(str, x['links_to_themes'])) or 'loose'})"
                                                for x in th["bridge_terms"]) or "none"), "",
              f"**Who sustains it** ({th['interventions']['basis']}): {c['speakers']} speakers, {c['sessions']} "
              f"sessions; the first speaker gives {c['top_speaker_share']:.0%}, the first session holds "
              f"{c['top_session_share']:.0%}." + (" **" + "; ".join(c["flags"]) + ".**" if c["flags"] else ""), "",
              "**By year:** " + ", ".join(f"{y['year']} {y['interventions']} ({y['pct_of_year']} %)" for y in th["years"]),
              ""]
        if th["groups"]:
            L += ["**Words of each group inside the theme:**", ""]
            L += [f"- {g['group']} ({g['interventions']}): " + (", ".join(x["term"] for x in g["distinctive"]) or "—")
                  for g in th["groups"]]
            L.append("")
        L += ["### Reading", ""]
        for r in th["reading"]:
            L.append(f"**{r['id_int']}** · {r['date']} · {r['speaker'] or '—'} · {r['group']} · {r['words']} words · "
                     f"{r['why']}")
            L += [f"> {p}" for p in r["passages"]]
            L.append("")
    return "\n".join(L)


def theme_dossier(network: str, theme: int | None = None, sample: int = 10, n_passages: int = 2, window: int = 40,
                  group_by: str = "party", stability_runs: int = 20, seed: int = 1, output_dir: str | None = None,
                  overwrite: bool = False) -> dict:
    """The evidence for reading each theme of a saved word network (see the module docstring). Without `theme`
    it writes the dossier (JSON and Markdown) and a codebook template, and returns the overview; with `theme` it
    returns that theme's full dossier, passages included."""
    path, net = _load_network(network)
    if not 1 <= int(stability_runs) <= 100:
        raise ValueError("stability_runs must be between 1 and 100")
    if theme is not None and not 1 <= int(theme) <= len(net["themes"]):
        raise ValueError(f"theme must be between 1 and {len(net['themes'])} (the page's numbers)")
    out_dir = networks._out_dir(output_dir) if output_dir else path.parent
    key = (str(path), path.stat().st_mtime_ns, int(sample), int(n_passages), int(window), group_by,
           int(stability_runs), int(seed))
    if key not in _CACHE:
        _CACHE.clear()
        _CACHE[key] = _build(path, net, int(sample), int(n_passages), int(window), group_by, int(stability_runs),
                             int(seed))
    dz = _CACHE[key]
    if theme is not None:
        return {"theme": dz["themes"][int(theme) - 1], "self_check": dz["self_check"], "thresholds": dz["thresholds"],
                "protocol": dz["protocol"]}
    stem = path.stem[:-len("_words")] if path.stem.endswith("_words") else path.stem
    files = [_write_same(out_dir / f"{stem}_dossier.json", json.dumps(dz, ensure_ascii=False, indent=1, default=str),
                         overwrite),
             _write_same(out_dir / f"{stem}_dossier.md", _markdown(dz), overwrite)]
    cb = out_dir / f"{stem}_codebook.json"
    notes = []
    if cb.exists() and not overwrite:
        notes.append(f"{cb.name} already exists and was kept (it may hold your reading); overwrite=true replaces it")
    else:
        files.append(networks._write(cb, json.dumps(_template(dz), ensure_ascii=False, indent=1), True))
    return {"network": dz["network"], "library": dz["library"], "country": dz["country"], "N": dz["N"],
            "self_check": dz["self_check"], "themes": [_overview(th) for th in dz["themes"]],
            "thresholds": dz["thresholds"], "files": files, "codebook": str(cb), "notes": notes,
            "next": "Read each theme with theme_dossier(network, theme=k), fill the codebook, then check_codebook.",
            "protocol": dz["protocol"]}


# ── check_codebook ────────────────────────────────────────────────────────────

def wilson(x: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval of a proportion x/n."""
    if n <= 0:
        return (0.0, 1.0)
    p = x / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, mid - half), min(1.0, mid + half))


def cohen_kappa(a: list, b: list) -> dict:
    """Agreement of two codings of the same items: observed share, Cohen's κ (None when chance agreement is 1)."""
    n = len(a)
    if not n:
        return {"n": 0, "agreement": None, "kappa": None}
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return {"n": n, "agreement": round(po, 4), "kappa": round((po - pe) / (1 - pe), 4) if pe < 1 else None}


def _norm(s: str) -> str:
    return " ".join(str(s or "").split())


def _quote_status(quote: str, text: str) -> str:
    q, t = _norm(quote), _norm(text)
    if not q:
        return "empty"
    if q in t:
        return "verbatim"
    if co.fold(q) in co.fold(t):
        return "case or accents differ"
    return "not found"


def _validate(cb: dict, n_themes: int) -> tuple[list[str], list[str], list[dict], dict]:
    """Schema errors, warnings, every anchor (with where it is), and the themes and frames that can be coded."""
    errors, warnings, anchors = [], [], []
    if cb.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA!r}")
    entries = cb.get("themes")
    if not isinstance(entries, list) or not entries:
        errors.append("themes must be a non-empty list")
        return errors, warnings, anchors, {"themes": [], "frames": []}
    seen, labels, frames, codable, status = set(), Counter(), Counter(), [], Counter()
    for e in entries:
        k = e.get("theme")
        where = f"theme {k}"
        if not isinstance(k, int) or not 1 <= k <= n_themes:
            errors.append(f"{where}: not a theme of the network (1-{n_themes})")
            continue
        if k in seen:
            errors.append(f"{where}: listed twice")
        seen.add(k)
        v = e.get("verdict") or ""
        if not v:
            status["incomplete"] += 1
            continue
        if v not in VERDICTS:
            errors.append(f"{where}: verdict must be one of {', '.join(VERDICTS)}")
            continue
        status[v] += 1
        if v == "merge":
            mw = e.get("merge_with") or []
            if not mw or any(not isinstance(j, int) or not 1 <= j <= n_themes or j == k for j in mw):
                errors.append(f"{where}: merge needs merge_with, other themes of the network")
        if v in ("theme", "split"):
            for fld in ("label", "definition"):
                if not _norm(e.get(fld)):
                    errors.append(f"{where}: {fld} is empty")
        if v == "theme":
            codable.append(k)
            labels[_norm(e.get("label")).lower()] += 1
            if not e.get("anchors"):
                errors.append(f"{where}: a theme needs anchors (id_int and a verbatim quote)")
        for a in e.get("anchors") or []:
            anchors.append({**a, "theme": k, "where": where})
        for fr in e.get("frames") or []:
            name = _norm(fr.get("name"))
            fw = f"{where}, frame {name or '?'}"
            if not name:
                errors.append(f"{where}: a frame without a name")
                continue
            frames[name.lower()] += 1
            if not any(_norm(fr.get(x)) for x in ("problem", "cause", "evaluation", "remedy")):
                errors.append(f"{fw}: none of problem, cause, evaluation or remedy is written")
            if not fr.get("anchors"):
                errors.append(f"{fw}: no anchors")
            if v != "theme":
                warnings.append(f"{fw}: frames of a theme whose verdict is {v!r} cannot be coded")
            for a in fr.get("anchors") or []:
                if a.get("stance") not in STANCES:
                    errors.append(f"{fw}: stance must be one of {', '.join(STANCES)}")
                anchors.append({**a, "theme": k, "where": fw})
    if status["incomplete"]:
        warnings.append(f"{status['incomplete']} theme(s) still without a verdict")
    errors += [f"label {x!r} used by two themes" for x, n in labels.items() if x and n > 1]
    errors += [f"frame name {x!r} used twice: codes refer to frames by name" for x, n in frames.items() if n > 1]
    names = [_norm(fr.get("name")) for e in entries if e.get("verdict") == "theme" for fr in e.get("frames") or []
             if _norm(fr.get("name"))]
    return errors, warnings, anchors, {"themes": sorted(codable), "frames": names, "verdicts": dict(status)}


def _check_anchors(anchors: list[dict], docs: dict, theme_ids: dict) -> tuple[dict, list[str], list[str]]:
    counts, errors, warnings = Counter(), [], []
    missing = sorted({str(a.get("id_int")) for a in anchors if str(a.get("id_int")) not in docs})
    texts = {}
    if missing:
        _, rows, _ = store.run_query("SELECT id_int, text FROM interventions WHERE id_int IN "
                                     "(SELECT unnest(?::VARCHAR[]))", [missing], max_rows=len(missing) + 5)
        texts = {str(i): t or "" for i, t in rows}
    for a in anchors:
        i, w = str(a.get("id_int")), a["where"]
        counts["checked"] += 1
        d = docs.get(i)
        if d is None:
            if i in texts:
                counts["outside_library"] += 1
                errors.append(f"{w}: {i} is not in the library the network was built on")
            else:
                counts["unknown_id"] += 1
                errors.append(f"{w}: {i} is not an intervention of the loaded data")
            continue
        st = _quote_status(a.get("quote"), d["text"])
        counts[st] += 1
        if st != "verbatim":
            errors.append(f"{w}: quote in {i} {st}" + (" (no '…': quote one contiguous stretch)" if
                                                       "…" in str(a.get("quote")) or "..." in str(a.get("quote")) else ""))
        elif len(_norm(a.get("quote")).split()) < MIN_QUOTE_WORDS:
            warnings.append(f"{w}: quote in {i} has fewer than {MIN_QUOTE_WORDS} words")
        if not d["themes"].get(theme_ids[a["theme"]]):
            counts["outside_theme"] += 1
            warnings.append(f"{w}: {i} has none of the theme's terms")
    return dict(counts), errors, warnings


def _read_coding(path: str, sample: list[dict], codes: dict, who: str) -> list[dict]:
    p = _absolute(path, who)
    with open(p, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    want = [(str(i + 1), str(d["id_int"])) for i, d in enumerate(sample)]
    got = [(str(r.get("sample", "")).strip(), str(r.get("id_int", "")).strip()) for r in rows]
    if got != want:
        raise ValueError(f"{p.name} does not hold this sample (same rows, same order): draw it with the same seed and "
                         "sample_size")
    themes, frames = {str(k) for k in codes["themes"]} | {"none"}, {f.lower() for f in codes["frames"]} | {"none"}
    out = []
    for r in rows:
        t = str(r.get("theme", "")).strip().lower()
        f = _norm(r.get("frame")).lower()
        s = str(r.get("stance", "")).strip().lower()
        bad = [x for x, ok in ((f"theme {t!r}", t in themes), (f"frame {f!r}", f in frames),
                               (f"stance {s!r}", (s in STANCES) if f not in ("", "none") else s == "")) if not ok]
        if bad:
            raise ValueError(f"{p.name}, sample {r['sample']}: " + ", ".join(bad) + " (themes: codable numbers or "
                             "'none'; frames: a frame's name or 'none'; stance only with a frame)")
        out.append({"theme": t, "frame": f, "stance": s})
    return out


def _prevalence(sample: list[dict], coded: list[dict], strata: dict, field: str) -> list[dict]:
    """Share of each label over the sample (it weighs itself) and by group, with Wilson 95 % intervals; a group
    with fewer than MIN_GROUP_CODED coded passages is marked too few to read."""
    out = []
    for lab in sorted({c[field] for c in coded} - {"", "none"}):
        rows = []
        for g in sorted(strata, key=lambda g: (-strata[g][0], g)):
            idx = [i for i, d in enumerate(sample) if d["group"] == g]
            if not idx:
                continue
            x = sum(1 for i in idx if coded[i][field] == lab)
            lo, hi = wilson(x, len(idx))
            rows.append({"group": g, "coded": len(idx), "with_label": x, "share": round(x / len(idx), 4),
                         "wilson_95": [round(lo, 4), round(hi, 4)], "too_few": len(idx) < MIN_GROUP_CODED})
        x = sum(1 for c in coded if c[field] == lab)
        lo, hi = wilson(x, len(coded))
        out.append({"label": lab, "library": {"coded": len(coded), "with_label": x, "share": round(x / len(coded), 4),
                                              "wilson_95": [round(lo, 4), round(hi, 4)]}, "by_group": rows})
    return out


def check_codebook(codebook: str, sample_size: int = 60, seed: int = 1, human: str | None = None,
                   agent: str | None = None, group_by: str = "party", output_dir: str | None = None,
                   overwrite: bool = False) -> dict:
    """Checks a codebook filled after reading the dossier (see the module docstring). Without codings it writes
    the blind sample and the two empty coding files; with both `human` and `agent` it measures their agreement and
    the labels' shares by group. The report is rewritten on every call; the sample and coding files only with
    overwrite=true."""
    cpath = _absolute(codebook, "codebook")
    try:
        cb = json.loads(cpath.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"{cpath.name} is not JSON: {e}") from e
    if (human is None) != (agent is None):
        raise ValueError("Pass both codings (human and agent) or neither")
    npath, net = _load_network(str((cb.get("network") or {}).get("file") or ""))
    if (cb.get("network") or {}).get("checksums") != net["checksums"]:
        raise ValueError(f"{npath.name} is no longer the network this codebook was written for (checksums differ)")
    out_dir = networks._out_dir(output_dir) if output_dir else cpath.parent
    errors, warnings, anchors, codes = _validate(cb, len(net["themes"]))
    docs = {str(d["id_int"]): d for d in _rebuild(net, group_by)}
    ids = {t["id"] + 1: t["id"] for t in net["themes"]}
    counts, e2, w2 = _check_anchors([a for a in anchors if a["theme"] in ids], docs, ids)
    errors += e2
    warnings += w2
    terms = sorted({n["term"] for n in net["nodes"] if n["theme"] >= 0})
    ordered = sorted(docs.values(), key=lambda d: d["row_n"])
    sample, strata = _proportional(ordered, int(sample_size), int(seed), key=lambda d: d["group"])
    stem = cpath.stem
    files = []
    srows, krows = [], []
    for i, d in enumerate(sample):
        ps, _ = passages(d["text"], terms, 1, 60)
        srows.append({"sample": i + 1, "id_int": d["id_int"], "date": str(d["date"]) if d["date"] else "",
                      "passage": ps[0] if ps else ""})
        krows.append({"sample": i + 1, "id_int": d["id_int"], "group": d["group"],
                      "dominant_theme": d["dominant"] + 1 if d["dominant"] >= 0 else "",
                      "stratum_size": strata[d["group"]][0], "stratum_drawn": strata[d["group"]][1]})
    blank = [{"sample": r["sample"], "id_int": r["id_int"], "theme": "", "frame": "", "stance": "", "notes": ""}
             for r in srows]
    plan = [(f"{stem}_sample.csv", ["sample", "id_int", "date", "passage"], srows),
            (f"{stem}_key.csv", ["sample", "id_int", "group", "dominant_theme", "stratum_size", "stratum_drawn"], krows),
            (f"{stem}_coding_human.csv", ["sample", "id_int", "theme", "frame", "stance", "notes"], blank),
            (f"{stem}_coding_agent.csv", ["sample", "id_int", "theme", "frame", "stance", "notes"], blank)]
    kept = []
    for name, keys, rows in plan:
        if (out_dir / name).exists() and not overwrite:
            kept.append(name)
        else:
            files.append(networks._write_csv(out_dir / name, keys, rows, True))
    complete = not codes.get("verdicts", {}).get("incomplete")
    result = {"codebook": str(cpath), "network": str(npath), "ok": not errors and complete, "complete": complete,
              "errors": errors, "warnings": warnings,
              "verdicts": codes.get("verdicts", {}), "codable": {"themes": codes["themes"], "frames": codes["frames"]},
              "anchors": counts,
              "sample": {"size": len(sample), "seed": int(seed), "strata": {g: {"size": n, "drawn": k}
                                                                            for g, (n, k) in sorted(strata.items())},
                         "kept": kept,
                         "unit": "the passage shown for each sampled intervention (one, where the themes' words "
                                 "are densest), not the whole intervention: shares are shares of these passages",
                         "instructions": "Code each passage blind, the person and the agent apart, each in its own "
                                         "file: theme = the number of a codable theme or 'none'; frame = a codable "
                                         "frame's name or 'none'; stance (affirms, contests, cites) only with a "
                                         "frame. The agent codes in a fresh context, without the key, the dossier "
                                         "or the other coder's file; the key (groups, dominant theme) is for "
                                         "nobody who codes."},
              "next": "Code the sample (human=, agent=) for the agreement; then theme_report(codebook) writes the "
                      "template of the report that interprets the themes."}
    if human is not None:
        h = _read_coding(human, sample, codes, "human")
        a = _read_coding(agent, sample, codes, "agent")
        result["agreement"] = {f: {**cohen_kappa([x[f] for x in h], [x[f] for x in a]),
                                   "disagreements": [{"sample": i + 1, "human": x[f], "agent": y[f]}
                                                     for i, (x, y) in enumerate(zip(h, a)) if x[f] != y[f]][:20]}
                               for f in ("theme", "frame", "stance")}
        result["prevalence"] = {"human": {f: _prevalence(sample, h, strata, f) for f in ("theme", "frame")},
                                "agent": {f: _prevalence(sample, a, strata, f) for f in ("theme", "frame")}}
    report = json.dumps(result, ensure_ascii=False, indent=1, default=str)
    files.append(networks._write(out_dir / f"{stem}_check.json", report, True))
    result["files"] = files
    return result
