"""Word co-occurrence network and themes of a library, ported line by line from the Diarios Explorer
(explorer_src/worker/35b_engine__coocurrencia.js and the parts of 34_engine__keyness.js, 34a_engine__expresiones.js
and 35_engine__partition.js it uses), so that the MCP and the explorer give the same network for the same texts.
tests/test_cooccurrence.py runs the explorer's own code in Node and compares.

  1. Vocabulary: the library's lexicon (signed G² of Dunning against the rest of the country's corpus, |G²| ≥ 10.83,
     freq ≥ 5, the 2,000 most over-used), in G² order, without numbers (digits or numerals written out), the
     language's Snowball stopwords (Portuguese for BR and PT, Spanish otherwise; 'estado', 'estados' kept) and the
     terms the user excludes; the first `vocabulary` terms (250).
  2. Text: speech only (parenthetical stage directions and upper-case lines out) or full; tokens: lower case, runs
     of letters and digits, accents folded; multi-word expressions of the corpus (detected once by the explorer over
     the whole country) joined into one token, so each is one node.
  3. Unit of context: the intervention, or consecutive fragments of N tokens within it.
  4. Signed G² on the 2×2 table of units; edges with positive association and G² ≥ 10.83 that are among the k
     highest-G² neighbours of either end; weight = association strength, observed / expected (van Eck & Waltman
     2009): the G² decides which edges exist, the strength how much they weigh.
  5. Leiden (leiden.py, the explorer's algorithm) with resolution γ and a fixed seed: each community of 3 terms or
     more is a theme; smaller ones are listed as loose terms.
  6. Per theme: its terms by internal strength, the interventions that contain any, the words of the interventions
     it dominates, the theme's words said by each party (with the party's words in the whole library, a rate per
     1,000 words) and a reading list (BM25, k1 = 1.2, b = 0.75, with ln(1 + G²) as the term weight).
Deviations from the explorer, recorded with every result (cooccurrence_network in networks.py):
  - reference counts come from the MCP's interventions table (every row of the country, like the explorer's
    FTS5 index, with DuckDB's tokenizer: 0.0001 % fewer tokens in Brazil);
  - speech-only text always uses the explorer's fast segmentation (it uses its full Diario parser below 25 million
    characters; that parser is not ported);
  - displayed forms are the country's most frequent written form (the explorer samples the library's).
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from . import leiden

LEX = json.loads((Path(__file__).parent / "explorer_lexicon.json").read_text(encoding="utf-8"))

DEFAULTS = {"speech_only": True, "unit": "intervention", "fragment": 20, "vocabulary": 250, "neighbours": 10,
            "resolution": 1.0, "seed": 1, "g2_min": 10.83, "exclude": [], "expressions": True}
LEXICON = {"limit": 2000, "limit_negative": 200, "min_freq": 5}       # the ones the explorer's page asks for
MIN_FREQ = LEX["keyness"]["min_freq"]
THRESHOLD = LEX["keyness"]["threshold"]
ZERO = LEX["keyness"]["zero_correction"]
READ_THEME = 25            # best-scored interventions returned per theme
READ_GLOBAL = 200          # … and in the whole library
READ_VARIED = 100          # varied selection: the best of each theme in turn
BM25_K1, BM25_B = 1.2, 0.75
MIN_THEME = 3              # a community of fewer terms is not a theme: listed apart, as loose terms
MAX_TOKENS = 7             # longest expression
PORTUGUESE = {"BR", "PT"}


# ── rounding as in JavaScript ─────────────────────────────────────────────────

def js_round(x: float, d: int = 4):
    """Math.round(x · 10^d) / 10^d: halves go up (Python's round goes to even)."""
    if not math.isfinite(x):
        return x
    y = x * 10 ** d
    r = math.floor(y)
    return (r + 1 if y - r >= 0.5 else r) / 10 ** d


def _js_len(w: str) -> int:
    """String length in UTF-16 code units, as JavaScript counts it."""
    return len(w) if w.isascii() else len(w.encode("utf-16-le")) // 2


# ── tokens (keyness.js) ───────────────────────────────────────────────────────

_DIAC_CP = frozenset(LEX["diacritics_cp"])
_DIAC = "".join(chr(c) for c in sorted(_DIAC_CP))
_PU = LEX["private_use"]
_SPECIAL = LEX["special_folding"]
TOKEN_SIMPLE = re.compile(r"[^\W_]+")
TOKEN_FULL = re.compile(f"(?:[^\\W_]|[{_PU}])(?:[^\\W_]|[{_PU}{_DIAC}])*")
RARE = re.compile(f"[{_PU}{_DIAC}]")
# Signs that separate stretches: an expression does not cross sentence or clause punctuation, quotes, brackets,
# line breaks or tabs, or gaps of 6 or more spaces (table columns in the transcripts).
CUT_SIGNS = ".,;:!?¿¡()[]{}«»\"“”„–—…•|\n\r\t"
_CUT = frozenset(CUT_SIGNS)
RX_CUT = re.compile("[" + "".join(re.escape(c) for c in CUT_SIGNS) + "]+| {6,}")


@lru_cache(maxsize=8192)
def _fold_char(ch: str) -> str:
    if ch in _SPECIAL:
        return _SPECIAL[ch]
    if ord(ch) in _DIAC_CP:
        return ""
    d = unicodedata.normalize("NFD", ch)
    if len(d) > 1 and ord(d[0]) < 0x80 and all(unicodedata.category(x) == "Mn" for x in d[1:]):
        return d[0]
    return ch


def _strip_marks(s: str) -> str:
    return "".join(ch if ord(ch) < 0x80 else _fold_char(ch) for ch in s)


@lru_cache(maxsize=200_000)
def fold_token(w: str) -> str:
    return _strip_marks(w)


def fold(s: str) -> str:
    """Lower case and no diacritics, like the terms of the explorer's FTS5 index."""
    s = (s or "").lower()
    return s if s.isascii() else _strip_marks(s)


def raw_tokens(text: str) -> list[str]:
    """Tokens in lower case, not yet folded."""
    t = (text or "").lower()
    return TOKEN_FULL.findall(t) if RARE.search(t) else TOKEN_SIMPLE.findall(t)


def tokenize(text: str) -> list[str]:
    return [w if w.isascii() else fold_token(w) for w in raw_tokens(text)]


def _raw_stretches(text: str) -> list[list[str]]:
    t = (text or "").lower()
    out: list[list[str]] = []
    if RARE.search(t):
        for s in RX_CUT.split(t):
            x = TOKEN_FULL.findall(s)
            if x:
                out.append(x)
        return out
    cur: list[str] = []
    end = 0
    for m in TOKEN_SIMPLE.finditer(t):
        if cur:
            gap = t[end:m.start()]
            if "      " in gap or any(c in _CUT for c in gap):
                out.append(cur)
                cur = []
        cur.append(m.group())
        end = m.end()
    if cur:
        out.append(cur)
    return out


def tokenize_stretches(text: str) -> list[list[str]]:
    """tokenize by stretches that do not cross a cut sign: [[folded token, …], …]."""
    return [[w if w.isascii() else fold_token(w) for w in s] for s in _raw_stretches(text)]


def count_terms(texts) -> tuple[dict[str, int], int]:
    raw: dict[str, int] = {}
    n = 0
    for t in texts:
        toks = raw_tokens(t)
        n += len(toks)
        for w in toks:
            raw[w] = raw.get(w, 0) + 1
    out: dict[str, int] = {}
    for w, k in raw.items():
        f = w if w.isascii() else fold_token(w)
        out[f] = out.get(f, 0) + k
    return out, n


# ── speech only, fast segmentation (partition.js: particionRapida) ────────────

RX_STAGE = re.compile(r"\([^()\n]{1,400}\)")
RX_UPPER = re.compile(r"[A-ZÁÉÍÓÚÑÃÕÇÀÈÌÒÙÂÊÔÜ]")
RX_LOWER = re.compile(r"[a-záéíóúñãõçàèìòùâêôü]")


def fast_partition(text: str) -> tuple[list[tuple[int, int]], dict[str, int]]:
    """Prose spans of a text and the tokens left out by category: parenthetical stage directions and upper-case
    lines (≥ 8 upper-case letters and more than three times the lower-case ones: vote lists, headers)."""
    n = len(text)
    out = [(m.start(), m.end(), "acotaciones") for m in RX_STAGE.finditer(text)]
    start = 0
    while start < n:
        end = text.find("\n", start)
        if end < 0:
            end = n
        if end - start >= 8:
            line = text[start:end]
            up = len(RX_UPPER.findall(line))
            if up >= 8 and up > 3 * len(RX_LOWER.findall(line)):
                out.append((start, end, "listas"))
        start = end + 1
    if not out:
        return [(0, n)], {}
    out.sort(key=lambda x: (x[0], x[1]))
    prose, excl, pos = [], {}, 0
    for a, b, cat in out:
        if b <= pos:
            continue
        a2 = max(a, pos)
        if a2 > pos:
            prose.append((pos, a2))
        k = len(raw_tokens(text[a2:b]))
        if k:
            excl[cat] = excl.get(cat, 0) + k
        pos = b
    if pos < n:
        prose.append((pos, n))
    return prose, excl


def speech_text(text: str) -> tuple[str, dict[str, int]]:
    text = text or ""
    spans, excl = fast_partition(text)
    if len(spans) == 1 and spans[0] == (0, len(text)):
        return text, excl
    return "\n".join(text[a:b] for a, b in spans), excl


# ── statistics (keyness.js) ───────────────────────────────────────────────────

def _xlog(o: float, e: float) -> float:
    return o * math.log1p((o - e) / e) if o > 0 else 0.0


def g2_signed(a: float, b: float, c: float, d: float) -> float:
    """Signed log-likelihood G² of the full 2×2 table: + over-use, − under-use."""
    n = c + d
    k = a + b
    e11 = c * k / n
    e12 = d * k / n
    g2 = 2.0 * (_xlog(a, e11) + _xlog(b, e12) + _xlog(c - a, c - e11) + _xlog(d - b, d - e12))
    g2 = g2 if math.isnan(g2) else max(g2, 0.0)
    return g2 if a * d >= b * c else -g2


def log_ratio(a: float, b: float, c: float, d: float) -> float:
    x = a if a > 0 else ZERO
    y = b if b > 0 else ZERO
    return math.log2((x / c) / (y / d))


KEYNESS_STOPWORDS = frozenset(LEX["keyness"]["stopwords"])


def keyness(counts: dict[str, int], c: int, corpus_tokens: int, reference: dict[str, int],
            min_freq: int = MIN_FREQ, threshold: float = THRESHOLD, limit: int | None = None,
            limit_negative: int = 50) -> dict:
    """The library's lexicon against the rest of the corpus (corpus − library). `reference`: term → count in the
    whole corpus, for the terms with freq ≥ min_freq. Terms counted more often in the library than in the corpus
    (a tokenizer difference) get a reference of 0 and are reported."""
    d = corpus_tokens - c
    out = {"tokens": c, "corpus_tokens": corpus_tokens, "reference_tokens": d, "min_freq": min_freq,
           "threshold": threshold, "terms": [], "negative": [], "excluded": {"stopwords": 0, "one_char": 0},
           "incoherent": [], "candidates": 0}
    if c == 0 or d <= 0:
        return out
    cand = sorted(t for t, k in counts.items() if k >= min_freq)
    out["candidates"] = len(cand)
    pos, neg = [], []
    for term in cand:
        fa = counts[term]
        tot = reference.get(term, 0)
        if tot < fa:
            out["incoherent"].append(term)
        fb = max(0, tot - fa)
        g2 = g2_signed(fa, fb, c, d)
        if not abs(g2) >= threshold:
            continue
        if term in KEYNESS_STOPWORDS:
            out["excluded"]["stopwords"] += 1
            continue
        if len(term) == 1:
            out["excluded"]["one_char"] += 1
            continue
        row = {"term": term, "freq": fa, "freq_ref": fb, "g2": round(g2, 2), "log_ratio": round(log_ratio(fa, fb, c, d), 2)}
        (pos if g2 > 0 else neg).append(row)
    pos.sort(key=lambda x: (-x["g2"], x["term"]))
    neg.sort(key=lambda x: (x["g2"], x["term"]))
    out["n_positive"], out["n_negative"] = len(pos), len(neg)
    out["terms"] = pos[:limit] if limit else pos
    out["negative"] = neg[:limit_negative] if limit_negative else []
    return out


def add_expressions(res: dict, ix: "ExpressionIndex", texts, min_freq: int = MIN_FREQ, limit: int | None = None,
                    limit_negative: int = 50) -> None:
    """Adds the expressions with significant G² to the lexicon, with the same columns as the words (partition.js:
    anadirExpresiones). Reference: the expression's frequency in the corpus minus the library's."""
    counts = ix.count(texts)
    c, d = res["tokens"], res["reference_tokens"]
    pos, neg = [], []
    if c > 0 and d > 0:
        for i, fa in counts.items():
            if fa < min_freq:
                continue
            fb = max(0, ix.freq[i] - fa)
            g2 = g2_signed(fa, fb, c, d)
            if not abs(g2) >= res["threshold"]:
                continue
            row = {"term": ix.forms[i], "display": ix.display[i], "freq": fa, "freq_ref": fb, "g2": round(g2, 2),
                   "log_ratio": round(log_ratio(fa, fb, c, d), 2), "expression": True}
            (pos if g2 > 0 else neg).append(row)
    res["terms"] = sorted(res["terms"] + pos, key=lambda x: (-x["g2"], x["term"]))
    if limit:
        res["terms"] = res["terms"][:limit]
    res["negative"] = sorted(res["negative"] + neg, key=lambda x: (x["g2"], x["term"]))
    if limit_negative:
        res["negative"] = res["negative"][:limit_negative]
    res["expressions"] = {"inventory": ix.n, "in_library": len(counts), "significant": len(pos) + len(neg),
                          "over_used": len(pos)}


# ── language lists (expresiones.js) ───────────────────────────────────────────

def language_of(country: str) -> str:
    return "pt" if str(country or "").upper() in PORTUGUESE else "es"


@lru_cache(maxsize=4)
def stopwords_of(lang: str) -> frozenset:
    ent = LEX["snowball"]["lenguas"][lang]
    keep = {fold(w) for w in ent.get("excepciones", [])}
    return frozenset(w for w in (fold(x) for x in ent["palabras"]) if w not in keep)


def stopwords_source(lang: str) -> dict:
    s = LEX["snowball"]
    e = s["lenguas"][lang]
    return {"language": lang, "source": s["fuente"], "web": s["web"], "license": s["licencia"],
            "copyright": s.get("copyright"), "url": e["url"], "n": e["n"], "kept": e.get("excepciones", []),
            "consulted": s.get("consultado")}


@lru_cache(maxsize=4)
def numerals_of(lang: str) -> frozenset:
    return frozenset(LEX["numerals"][lang])


@lru_cache(maxsize=4)
def connectors_of(lang: str) -> frozenset:
    return frozenset(fold(w) for w in LEX["connectors"][lang])


_DIGITS = re.compile(r"[0-9]+")


def type_of(lang: str):
    """0 cuts a candidate (stopword that is not a connector, number, word under 3 letters), 1 connector, 2 content."""
    stop, num, con = stopwords_of(lang), numerals_of(lang), connectors_of(lang)

    @lru_cache(maxsize=200_000)
    def t(w: str) -> int:
        if _js_len(w) >= 3 and w not in stop and w not in num and not (ord(w[0]) < 58 and _DIGITS.fullmatch(w)):
            return 2
        return 1 if w in con else 0
    return t


class ExpressionIndex:
    """The corpus's multi-word expressions, as the explorer stores them (precomputed package rows, in id order)."""

    def __init__(self, rows: list, country: str, meta: dict | None = None):
        self.forms = [r[0] for r in rows]
        self.display = [r[0] if r[1] == 0 else r[1] for r in rows]
        self.freq = [int(r[4]) for r in rows]
        self.n = len(rows)
        self.meta = meta or {}
        self.index = {f: i for i, f in enumerate(self.forms)}
        self.type = type_of(language_of(country))

    def units(self, tk: list[str], out: list | None = None) -> list[str]:
        """Tokens of a stretch with the expressions joined: the fewest units and, among equals, the longest
        (sum of squared lengths), by dynamic programming from the right."""
        out = [] if out is None else out
        n = len(tk)
        ti = [self.type(w) for w in tk]
        cost = [0] * (n + 1)
        points = [0] * (n + 1)
        fin = [0] * n
        ex = [-1] * n
        idx = self.index
        for i in range(n - 1, -1, -1):
            c0, p0, f0, e0 = 1 + cost[i + 1], 1 + points[i + 1], i, -1
            if ti[i] == 2:
                for j in range(i + 1, min(n, i + MAX_TOKENS)):
                    tj = ti[j]
                    if tj == 0:
                        break
                    if tj != 2:
                        continue
                    k = idx.get(" ".join(tk[i:j + 1]))
                    if k is None:
                        continue
                    L = j - i + 1
                    c, p = 1 + cost[j + 1], L * L + points[j + 1]
                    if c < c0 or (c == c0 and p > p0):
                        c0, p0, f0, e0 = c, p, j, k
            cost[i], points[i], fin[i], ex[i] = c0, p0, f0, e0
        i = 0
        while i < n:
            out.append(self.forms[ex[i]] if ex[i] >= 0 else tk[i])
            i = fin[i] + 1
        return out

    def units_text(self, text: str) -> list[str]:
        out: list[str] = []
        for tk in tokenize_stretches(text):
            self.units(tk, out)
        return out

    def count(self, texts) -> dict[int, int]:
        """Occurrences of each expression, ALL of them (also inside a longer one), like the corpus frequency it is
        compared with in the lexicon."""
        n: dict[int, int] = {}
        idx = self.index
        for tx in texts:
            for tk in tokenize_stretches(tx):
                if len(tk) < 2:
                    continue
                ti = [self.type(w) for w in tk]
                L = len(tk)
                for i in range(L):
                    if ti[i] != 2:
                        continue
                    for j in range(i + 1, min(L, i + MAX_TOKENS)):
                        t = ti[j]
                        if t == 0:
                            break
                        if t == 2:
                            k = idx.get(" ".join(tk[i:j + 1]))
                            if k is not None:
                                n[k] = n.get(k, 0) + 1
        return dict(sorted(n.items()))


# ── the network (coocurrencia.js: red) ────────────────────────────────────────

def _bm25_insert(lst: list, top: int, score: float, d: int, doc_ids: list) -> None:
    if len(lst) >= top and score <= lst[-1][0]:
        return
    k = len(lst)
    lst.append(None)
    while k > 0 and (lst[k - 1][0] < score or (lst[k - 1][0] == score and doc_ids[lst[k - 1][1]] > doc_ids[d])):
        lst[k] = lst[k - 1]
        k -= 1
    lst[k] = [score, d]
    if len(lst) > top:
        lst.pop()


def _count_pairs(units: list[list[int]], V: int) -> dict[tuple[int, int], int]:
    """Co-occurrence counts of the vocabulary's pairs over the units (each a sorted list of distinct term ids).
    Counted in DuckDB (exact integers): a library of 100,000 interventions has hundreds of millions of pairs."""
    import duckdb
    u_col, t_col = [], []
    for k, u in enumerate(units):
        if len(u) > 1:
            u_col.extend([k] * len(u))
            t_col.extend(u)
    if not u_col:
        return {}
    con = duckdb.connect()
    try:
        con.execute("CREATE TABLE u AS SELECT unnest(?::INTEGER[]) AS unit, unnest(?::INTEGER[]) AS t", [u_col, t_col])
        rows = con.execute("SELECT a.t, b.t, count(*) FROM u a JOIN u b ON a.unit = b.unit AND a.t < b.t "
                           "GROUP BY ALL").fetchall()
    finally:
        con.close()
    return {(i, j): int(n) for i, j, n in rows}


def network(docs: list[dict], lexicon_terms: list[dict], country: str, options: dict | None = None,
            ix: ExpressionIndex | None = None) -> dict:
    """The network of a library. docs: [{id, text, party}] in ascending id order, text already chosen (speech only
    or full); lexicon_terms: the lexicon's over-used terms in order ({term, display, freq, g2, expression})."""
    o = {**DEFAULTS, **(options or {})}
    lang = language_of(country)
    stop = stopwords_of(lang)
    numerals = numerals_of(lang)
    exclude = {fold(str(w)) for w in (o["exclude"] or []) if fold(str(w))}
    dropped = {"stopwords": 0, "numbers": 0, "excluded": 0}
    vocab = []
    for x in lexicon_terms:
        if len(vocab) >= o["vocabulary"]:
            break
        w = x["term"]
        if not w or _js_len(w) < 2:
            continue
        if _DIGITS.fullmatch(w) or w in numerals:
            dropped["numbers"] += 1
            continue
        if w in stop:
            dropped["stopwords"] += 1
            continue
        if w in exclude:
            dropped["excluded"] += 1
            continue
        if x.get("expression") and not ix:
            continue
        vocab.append({"term": w, "display": x.get("display") or w, "freq": int(x.get("freq") or 0),
                      "g2": float(x.get("g2") or 0), "expression": bool(x.get("expression"))})
    V = len(vocab)
    base = {"vocabulary": {"available": len(lexicon_terms), "used": V, "dropped": dropped},
            "expressions": {"joined": ix is not None, "inventory": ix.n if ix else 0}}
    if V < 3:
        return {**base, "nodes": [], "edges": [], "themes": [], "loose_terms": [], "stats": {"interventions": len(docs)},
                "warning": "The library has too few characteristic terms to build a co-occurrence network."}
    ids = {v["term"]: i for i, v in enumerate(vocab)}

    # units of context and term presence
    df_unit = [0] * V
    df_doc = [0] * V
    units: list[list[int]] = []
    doc_ids, doc_terms, doc_tf, doc_tokens, doc_party = [], [], [], [], []
    n_tokens = 0
    fragment = o["unit"] == "fragment"
    F = int(o["fragment"])
    for doc in docs:
        toks = ix.units_text(doc["text"]) if ix else tokenize(doc["text"])
        n_tokens += len(toks)
        pos = [ids.get(w, -1) for w in toks]
        tf: dict[int, int] = {}
        for v in pos:
            if v >= 0:
                tf[v] = tf.get(v, 0) + 1                      # dict order = order of first appearance
        in_doc = list(tf)
        for i in in_doc:
            df_doc[i] += 1
        doc_ids.append(doc["id"])
        doc_terms.append(in_doc)
        doc_tf.append([min(65535, tf[i]) for i in in_doc])
        doc_tokens.append(len(toks))
        doc_party.append(doc.get("party"))
        if fragment:
            for a in range(0, len(toks), F):
                seen = sorted({v for v in pos[a:a + F] if v >= 0})
                for i in seen:
                    df_unit[i] += 1
                units.append(seen)
        else:
            present = sorted(in_doc)
            for i in present:
                df_unit[i] += 1
            units.append(present)
    N = len(units)
    co = _count_pairs(units, V)

    # association and pruning by neighbours
    cand = []                       # [i, j, co, expected, g2, strength]
    for (i, j) in sorted(co):
        a = co[(i, j)]
        e = df_unit[i] * df_unit[j] / N
        if not a > e:
            continue
        g2 = g2_signed(a, df_unit[j] - a, df_unit[i], N - df_unit[i])
        if not g2 >= o["g2_min"]:
            continue
        cand.append([i, j, a, e, g2, a / e])
    by_node: list[list[int]] = [[] for _ in range(V)]
    for k, c in enumerate(cand):
        by_node[c[0]].append(k)
        by_node[c[1]].append(k)
    keep = [False] * len(cand)
    for lst in by_node:
        lst.sort(key=lambda k: (-cand[k][4], cand[k][0], cand[k][1]))
        for k in lst[:o["neighbours"]]:
            keep[k] = True
    edges = [c for k, c in enumerate(cand) if keep[k]]

    # communities
    lei = leiden.communities(V, [[c[0], c[1], c[5]] for c in edges], o["resolution"], o["seed"])
    com = lei["community"]
    strength, internal, degree = [0.0] * V, [0.0] * V, [0] * V
    for i, j, _, _, _, w in edges:
        strength[i] += w
        strength[j] += w
        degree[i] += 1
        degree[j] += 1
        if com[i] == com[j]:
            internal[i] += w
            internal[j] += w
    nc = lei["n_communities"]
    members: list[list[int]] = [[] for _ in range(nc)]
    for i in range(V):
        members[com[i]].append(i)
    for m in members:
        m.sort(key=lambda i: (-internal[i], -vocab[i]["g2"], i))

    # coverage, BM25 by theme and global, parties
    coverage = [0] * nc
    weight_term = [math.log1p(max(0.0, v["g2"])) for v in vocab]
    mean_len = (sum(doc_tokens) / len(doc_tokens)) if doc_tokens else 1
    top_theme: list[list] = [[] for _ in range(nc)]
    top_global: list = []
    parties: list[str] = []
    party_id: dict[str, int] = {}
    pq_of = []
    for p in doc_party:
        raw = "" if p is None else str(p).strip()
        if not raw or re.fullmatch(r"(\?|sin identificar)", raw, re.I):
            pq_of.append(-1)
            continue
        q = party_id.get(raw)
        if q is None:
            q = party_id[raw] = len(parties)
            parties.append(raw)
        pq_of.append(q)
    n_part = len(parties)
    by_theme = [[0] * n_part for _ in range(nc)]
    words_theme = [[0.0] * n_part for _ in range(nc)]
    total_party = [0] * n_part
    words_party = [0.0] * n_part
    with_party = 0
    words_with_party = 0.0
    words_total = 0.0
    size_theme = [0] * nc
    for i in range(V):
        if com[i] >= 0:
            size_theme[com[i]] += 1
    n_theme = [0] * nc
    words_dominated = [0.0] * nc
    words_no_theme = 0.0
    score_theme = [0.0] * nc
    touched: list[int] = []
    for d in range(len(doc_ids)):
        pq = pq_of[d]
        words_total += doc_tokens[d]
        if pq >= 0:
            total_party[pq] += 1
            with_party += 1
            words_party[pq] += doc_tokens[d]
            words_with_party += doc_tokens[d]
        norm = BM25_K1 * (1 - BM25_B + BM25_B * doc_tokens[d] / mean_len)
        glob = 0.0
        for i, tf in zip(doc_terms[d], doc_tf[d]):
            part = weight_term[i] * tf * (BM25_K1 + 1) / (tf + norm)
            glob += part
            c = com[i]
            if score_theme[c] == 0 and n_theme[c] == 0:
                touched.append(c)
            score_theme[c] += part
            n_theme[c] += 1
            if pq >= 0:
                words_theme[c][pq] += tf
        dom_c, dom_f, tie = -1, 0.0, False
        for c in touched:
            if n_theme[c] < 2 or size_theme[c] < MIN_THEME:
                continue
            f = n_theme[c] / size_theme[c]
            if f > dom_f:
                dom_c, dom_f, tie = c, f, False
            elif f == dom_f:
                tie = True
        if dom_c >= 0 and not tie:
            words_dominated[dom_c] += doc_tokens[d]
        else:
            words_no_theme += doc_tokens[d]
        for c in touched:
            coverage[c] += 1
            if pq >= 0:
                by_theme[c][pq] += 1
            _bm25_insert(top_theme[c], READ_THEME, score_theme[c], d, doc_ids)
            score_theme[c] = 0.0
            n_theme[c] = 0
        touched.clear()
        if glob > 0:
            _bm25_insert(top_global, READ_GLOBAL, glob, d, doc_ids)

    def terms_of(d, theme=None, mx=8):
        norm = BM25_K1 * (1 - BM25_B + BM25_B * doc_tokens[d] / mean_len)
        out = []
        for i, tf in zip(doc_terms[d], doc_tf[d]):
            if theme is not None and com[i] != theme:
                continue
            out.append((weight_term[i] * tf * (BM25_K1 + 1) / (tf + norm), i, tf))
        out.sort(key=lambda x: (-x[0], x[1]))
        return [{"display": vocab[i]["display"], "tf": tf} for _, i, tf in out[:mx]]

    def row(x, theme=None):
        s, d = x
        return {"id": doc_ids[d], "score": js_round(s, 3), "words": doc_tokens[d], "terms": terms_of(d, theme)}

    def split(count, words, top):
        lst, total, total_w = [], 0, 0.0
        for q in range(n_part):
            w = words[q] if words else 0
            if not count[q] and not w:
                continue
            lst.append({"party": parties[q], "n": count[q], "words": int(js_round(w, 0))})
            total += count[q]
            total_w += w
        lst.sort(key=lambda x: (-x["words"], -x["n"], x["party"]))
        rest = lst[top:]
        return {"with_party": total, "words": int(js_round(total_w, 0)), "top": lst[:top],
                "others": {"n": sum(x["n"] for x in rest), "words": sum(x["words"] for x in rest), "parties": len(rest)}
                if rest else None}

    weight_total = 0.0
    weight_internal = [0.0] * nc
    for i, j, _, _, _, w in edges:
        weight_total += w
        if com[i] == com[j]:
            weight_internal[com[i]] += w
    themes = []
    for c, m in enumerate(members):
        g2sum = 0.0
        for i in m:
            g2sum += vocab[i]["g2"]
        themes.append({
            "id": c, "label": " · ".join(vocab[i]["display"] for i in m[:3]), "n_terms": len(m),
            "g2_lexicon": js_round(g2sum, 1), "g2_mean": js_round(g2sum / max(1, len(m)), 1),
            "terms": [{"i": i, "term": vocab[i]["term"], "display": vocab[i]["display"],
                       "expression": vocab[i]["expression"], "internal_strength": js_round(internal[i], 3)} for i in m],
            "interventions": coverage[c],
            "pct_interventions": js_round(100 * coverage[c] / len(doc_ids), 1) if doc_ids else 0,
            "words_dominated": int(js_round(words_dominated[c], 0)),
            "weight_pct": js_round(100 * words_dominated[c] / words_total, 1) if words_total else 0,
            "internal_weight": js_round(weight_internal[c], 3),
            "parties": split(by_theme[c], words_theme[c], 60),
            "reading": [row(x, c) for x in top_theme[c]],
        })
    themes.sort(key=lambda t: (-t["g2_mean"], -t["interventions"], t["id"]))
    loose = [t for th in themes if th["n_terms"] < MIN_THEME for t in th["terms"]]
    themes = [t for t in themes if t["n_terms"] >= MIN_THEME]
    renum = [-1] * nc
    for k, t in enumerate(themes):
        renum[t["id"]] = k
        t["id"] = k

    glob_rows = [row(x) for x in top_global]
    varied, used, cursor = [], set(), [0] * len(themes)
    while len(varied) < READ_VARIED:
        some = False
        for k in range(len(themes)):
            if len(varied) >= READ_VARIED:
                break
            lst = themes[k]["reading"]
            while cursor[k] < len(lst) and lst[cursor[k]]["id"] in used:
                cursor[k] += 1
            if cursor[k] >= len(lst):
                continue
            x = lst[cursor[k]]
            cursor[k] += 1
            used.add(x["id"])
            some = True
            varied.append({"theme": k, **x})
        if not some:
            break

    nodes = [{"i": i, "term": v["term"], "display": v["display"], "expression": v["expression"], "freq": v["freq"],
              "g2_lexicon": js_round(v["g2"], 2), "df_unit": df_unit[i], "df_intervention": df_doc[i],
              "theme": renum[com[i]], "strength": js_round(strength[i], 3), "degree": degree[i]}
             for i, v in enumerate(vocab)]
    out_edges = [{"a": i, "b": j, "co": a, "expected": js_round(e, 3), "g2": js_round(g2, 2), "weight": js_round(w, 4)}
                 for i, j, a, e, g2, w in edges]
    n_pairs = V * (V - 1) // 2
    return {
        **base, "nodes": nodes, "edges": out_edges, "themes": themes, "loose_terms": loose,
        "parties": {"interventions": len(doc_ids), "words_total": int(js_round(words_total, 0)),
                    "words_with_party": int(js_round(words_with_party, 0)), **split(total_party, words_party, 60)},
        "reading": {"global": glob_rows, "varied": varied, "mean_length": js_round(mean_len, 1),
                    "method": {"formula": "BM25", "k1": BM25_K1, "b": BM25_B,
                               "term_weight": "ln(1 + G² of the term in the lexicon)"}},
        "stats": {"words_no_theme": int(js_round(words_no_theme, 0)),
                  "pct_no_theme": js_round(100 * words_no_theme / words_total, 1) if words_total else 0,
                  "interventions": len(doc_ids), "units": N, "tokens": n_tokens, "possible_pairs": n_pairs,
                  "observed_pairs": len(co), "density": js_round(len(co) / n_pairs, 4) if n_pairs else 0,
                  "significant_edges": len(cand), "kept_edges": len(edges), "themes": len(themes),
                  "leiden_communities": nc, "loose_terms": len(loose), "modularity": js_round(lei["modularity"], 4),
                  "quality": js_round(lei["quality"], 4), "total_weight": js_round(weight_total, 3)},
        "leiden": lei["parameters"],
    }
