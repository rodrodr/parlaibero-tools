"""Analysis functions behind the MCP tools. Every function reads through store.run_query, i.e.
a read-only, sandboxed DuckDB connection, and returns plain JSON-able structures."""
from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

import duckdb

from . import charts, profile, store
from .catalog import COUNTRIES, normalize_iso
from .textutil import STOPWORDS, fold, parse_terms, search_regex, tokens

# A year is flagged "low base" below either threshold: rates computed on it are noisy.
LOW_BASE_WORDS = 250_000
LOW_BASE_SESSIONS = 10
PORTUGUESE = {"BR", "PT"}
# Turns this long are almost always documents read into the record (reports, bills, lists) that the
# published corpora keep as dm_speech = 1 where the record marks no separator. They distort any
# measure normalised by words, unevenly across countries (≈ half the words in AR).
LONG_TURN = 10_000
# The chair, as printed: "El señor PRESIDENTE", "O Sr. Presidente", "PRESIDENTE (X)", "Presidencia, X"…
# but not the President of the Republic or of the Government.
CHAIR_RX = r"(?i)presid|vicepresid"
NOT_CHAIR_RX = r"(?i)rep[uú]blica|gobierno|governo|conselho de ministros|consejo de ministros|constitucional"


@dataclass
class Filters:
    countries: list[str] | None = None
    date_from: str | None = None
    date_to: str | None = None
    party: str | None = None
    sex: str | None = None
    id_dep: str | None = None
    speech_only: bool = True
    exclude_chair: bool = False
    max_turn_words: int | None = None
    library: int | None = None          # id of a library (library.resolve): only its interventions
    library_name: str | None = None
    extra: dict | None = None           # the profile's extra columns: {column: ILIKE pattern}

    def __post_init__(self):
        if self.countries:
            self.countries = [normalize_iso(c) for c in self.countries]
        if self.sex:
            self.sex = self.sex.upper()[:1]
        if self.extra:
            unknown = set(self.extra) - set(profile.ACTIVE.extra_columns)
            if unknown:
                raise ValueError(f"Unknown filter column(s): {', '.join(sorted(unknown))}")
            self.extra = {k: v for k, v in self.extra.items() if v not in (None, "")} or None

    def where(self, params: list, alias: str = "") -> str:
        a = f"{alias}." if alias else ""
        w = ""
        if self.countries:
            w += f" AND {a}country IN ({', '.join('?' * len(self.countries))})"
            params.extend(self.countries)
        if self.date_from:
            w += f" AND {a}date >= CAST(? AS DATE)"
            params.append(_date(self.date_from, start=True))
        if self.date_to:
            w += f" AND {a}date <= CAST(? AS DATE)"
            params.append(_date(self.date_to, start=False))
        if self.party:
            w += f" AND {a}party ILIKE ?"
            params.append(self.party)
        if self.sex:
            w += f" AND {a}sex = ?"
            params.append(self.sex)
        if self.id_dep:
            w += f" AND {a}id_dep = ?"
            params.append(self.id_dep)
        if self.speech_only:
            w += f" AND {a}dm_speech = 1"
        if self.exclude_chair:
            w += (f" AND NOT (regexp_matches(coalesce({a}speaker_raw, ''), '{CHAIR_RX}') AND NOT "
                  f"regexp_matches(coalesce({a}speaker_raw, ''), '{NOT_CHAIR_RX}'))")
        if self.max_turn_words:
            w += f" AND {a}n_words <= {int(self.max_turn_words)}"
        if self.library is not None:
            w += f" AND {a}id_int IN (SELECT id_int FROM lib.library_items WHERE library_id = {int(self.library)})"
        for col, value in (self.extra or {}).items():
            w += f" AND {a}{col} ILIKE ?"
            params.append(value)
        return w

    def year_bounds(self) -> tuple[int | None, int | None] | None:
        """Year range if the dates fall on year boundaries (so the unigram table can serve)."""
        def ok(d, start):
            if d is None:
                return None
            d = _date(d, start)
            if start and d.endswith("-01-01") or not start and d.endswith("-12-31"):
                return int(d[:4])
            raise ValueError
        try:
            return ok(self.date_from, True), ok(self.date_to, False)
        except ValueError:
            return None

    def unigram_ok(self) -> bool:
        return (self.speech_only and not self.party and not self.id_dep and not self.exclude_chair
                and not self.max_turn_words and self.library is None and not self.extra
                and self.year_bounds() is not None)

    def unigram_where(self, params: list) -> str:
        w = ""
        if self.countries:
            w += f" AND country IN ({', '.join('?' * len(self.countries))})"
            params.extend(self.countries)
        y0, y1 = self.year_bounds()
        if y0:
            w += " AND year >= ?"
            params.append(y0)
        if y1:
            w += " AND year <= ?"
            params.append(y1)
        if self.sex:
            w += " AND sex = ?"
            params.append(self.sex)
        return w


def _date(d: str, start: bool) -> str:
    d = str(d).strip()
    if re.fullmatch(r"\d{4}", d):
        return f"{d}-01-01" if start else f"{d}-12-31"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
        return d
    raise ValueError(f"Dates must be YYYY or YYYY-MM-DD, got {d!r}")


def _q(sql: str, params: list | None = None, max_rows: int = 1_000_000, timeout_s: float = 600):
    cols, rows, _ = store.run_query(sql, params or [], max_rows=max_rows, timeout_s=timeout_s)
    return [dict(zip(cols, r)) for r in rows]


def _long_turn_notes(f: Filters) -> list[str]:
    """Warn when documents read into the record weigh on a word-based measure."""
    if f.max_turn_words:
        return []
    p: list = []
    rows = _q(f"SELECT country, sum(n_words) FILTER (WHERE n_words > {LONG_TURN}) * 1.0 / sum(n_words) AS s "
              f"FROM interventions WHERE true{f.where(p)} GROUP BY 1 ORDER BY 2 DESC", p)
    heavy = [f"{r['country']} {r['s']:.0%}" for r in rows if r["s"] and r["s"] > 0.05]
    if not heavy:
        return []
    return [f"Turns over {LONG_TURN:,} words — mostly documents read into the record, kept as speech when "
            f"the record marks no separator — hold a large share of the words here ({', '.join(heavy)}). "
            f"They inflate word totals and deflate per-million rates. Re-run with max_turn_words="
            f"{LONG_TURN} to check the result does not depend on them."]


def _undated_note(f: Filters) -> list[str]:
    """Rows without a date cannot enter a time series: say how many were left out."""
    p: list = []
    rows = _q(f"SELECT country, count(*) AS n, count(DISTINCT id_session) AS s FROM interventions "
              f"WHERE date IS NULL{f.where(p)} GROUP BY 1 ORDER BY 1", p)
    if not rows:
        return []
    return ["Rows without a date are left out of anything by year or period: " +
            ", ".join(f"{r['country']} {r['n']:,} rows in {r['s']} sessions" for r in rows) + "."]


def _scope(f: "Filters") -> list[str]:
    """Countries an analysis touched: the ones asked for, or every loaded one."""
    return f.countries or sorted(store.loaded())


def _versions(isos) -> dict:
    loaded = store.loaded()
    return {i: {"doi": COUNTRIES[i][2], "version": (loaded.get(i) or {}).get("version")} for i in sorted(isos)}


# ── exact counting of terms ───────────────────────────────────────────────────

_NORM = (r"('  ' || array_to_string(regexp_extract_all(strip_accents(lower(text)), '[\pL\pN]+'), '  ') "
         r"|| '  ')")


def _variant_count_rx(variant: str) -> str:
    """RE2 over the normalised text ('  tok  tok  '): one match per whole-token occurrence."""
    parts = []
    for w in variant.split():
        star = w.endswith("*")
        t = tokens(fold(w.rstrip("*")))
        if not t:
            raise ValueError(f"'{variant}' contains no letters or digits")
        body = "  ".join(re.escape(x) for x in t)
        parts.append(body + (r"[\pL\pN]*" if star else ""))
    return " " + "  ".join(parts) + " "


def _series_sql(variants: list[str], params: list) -> tuple[str, str, list]:
    """(prefilter condition, occurrence expression, occurrence params) for a series of summed
    variants. The prefilter params are appended to `params`. One regexp_matches per variant joined
    with OR: a single RE2 alternation of accent-tolerant classes is ~60× slower (38 s vs 0.6 s)."""
    cond = "(" + " OR ".join("regexp_matches(text, ?)" for _ in variants) + ")"
    params.extend(search_regex(v, whole_word=True) for v in variants)
    occ = " + ".join(f"len(regexp_extract_all({_NORM}, ?))" for _ in variants)
    return cond, occ, [_variant_count_rx(v) for v in variants]


# ── ngram viewer ──────────────────────────────────────────────────────────────

def ngram_viewer(terms, f: Filters, split_by_country: bool = False,
                 measure: str = "per_million", smoothing: int = 0, chart_path: str | None = None,
                 title: str | None = None, language: str = "es", overwrite: bool = False) -> dict:
    if measure not in ("per_million", "count", "interventions_pct"):
        raise ValueError("measure must be per_million, count or interventions_pct")
    series_def = parse_terms(terms)
    # denominators: words, interventions and sessions per (country, year) under the same filters
    params: list = []
    den_rows = _q(f"SELECT country, year(date) AS year, sum(n_words) AS words, count(*) AS turns, "
                  f"count(DISTINCT id_session) AS sessions FROM interventions WHERE date IS NOT NULL"
                  f"{f.where(params)} GROUP BY ALL", params)
    if not den_rows:
        raise store.NoData("No rows match these filters in the loaded countries.")
    den = {(r["country"], r["year"]): r for r in den_rows}
    countries = sorted({r["country"] for r in den_rows})
    years = sorted({r["year"] for r in den_rows})
    use_unigrams = f.unigram_ok() and measure != "interventions_pct"

    out_series = []
    for s in series_def:
        counts: dict[tuple, dict] = defaultdict(lambda: {"count": 0, "turns": 0})
        single = all(len(tokens(fold(v.rstrip("*")))) == 1 for v in s["variants"])
        if use_unigrams and single:
            p: list = []
            conds = []
            for v in s["variants"]:
                fv = tokens(fold(v.rstrip("*")))[0] + ("*" if v.endswith("*") else "")
                if fv.endswith("*"):
                    conds.append("fold LIKE ?")
                    p.append(fv[:-1].replace("%", "").replace("_", "") + "%")
                else:
                    conds.append("fold = ?")
                    p.append(fv)
            w = f.unigram_where(p)
            for r in _q(f"SELECT country, year, sum(n) AS c FROM unigrams WHERE ({' OR '.join(conds)}){w} "
                        f"GROUP BY ALL", p):
                counts[(r["country"], r["year"])]["count"] += r["c"]
            method = "unigram index"
        else:
            p = []
            cond, occ, occ_params = _series_sql(s["variants"], p)
            where = f.where(p)
            sql = (f"SELECT country, year, sum(occ) AS c, count(*) FILTER (WHERE occ > 0) AS t FROM ("
                   f"SELECT country, year(date) AS year, {occ} AS occ FROM interventions "
                   f"WHERE {cond}{where}) GROUP BY ALL")
            # the occurrence parameters come first in the SQL text, the prefilter after
            for r in _q(sql, occ_params + p):
                counts[(r["country"], r["year"])]["count"] += r["c"]
                counts[(r["country"], r["year"])]["turns"] += r["t"]
            method = "exact scan"
        groups = [[c] for c in countries] if split_by_country else [countries]
        for g in groups:
            pts = []
            for y in years:
                words = sum(den[(c, y)]["words"] for c in g if (c, y) in den)
                turns = sum(den[(c, y)]["turns"] for c in g if (c, y) in den)
                sess = sum(den[(c, y)]["sessions"] for c in g if (c, y) in den)
                if not words:
                    pts.append({"year": y, "value": None, "count": 0, "words": 0, "sessions": 0, "low_base": True})
                    continue
                cnt = sum(counts[(c, y)]["count"] for c in g)
                tcount = sum(counts[(c, y)]["turns"] for c in g)
                val = (cnt * 1e6 / words if measure == "per_million" else
                       cnt if measure == "count" else tcount * 100 / turns)
                pts.append({"year": y, "value": val, "count": cnt, "words": words, "sessions": sess,
                            "n_countries": sum(1 for c in g if (c, y) in den),
                            "low_base": words < LOW_BASE_WORDS or sess < LOW_BASE_SESSIONS})
            if smoothing:
                raw = [p_["value"] for p_ in pts]
                for i, p_ in enumerate(pts):
                    if raw[i] is None:
                        continue
                    win = [raw[j] for j in range(max(0, i - smoothing), min(len(raw), i + smoothing + 1))
                           if raw[j] is not None]
                    p_["value"] = sum(win) / len(win)
            for p_ in pts:
                if p_["value"] is not None:
                    p_["value"] = round(p_["value"], 3)
            label = (g[0] if split_by_country and len(series_def) == 1 else
                     s["label"] + (f" ({g[0]})" if split_by_country else ""))
            out_series.append({"label": label, "variants": s["variants"], "countries": g,
                               "method": method, "points": pts})

    notes = []
    if not split_by_country and len(countries) > 1:
        notes.append("Pooled series: larger corpora weigh more, and the set of countries changes over the "
                     "years (see n_countries) — part of any trend may be composition. Use "
                     "split_by_country=true to compare countries.")
    if (any(c in PORTUGUESE for c in countries) and any(c not in PORTUGUESE for c in countries)
            and any(len(s["variants"]) == 1 for s in series_def)):
        notes.append("Brazil and Portugal speak Portuguese: a Spanish term will not match there (add the "
                     "Portuguese form with +, e.g. 'corrupción+corrupção').")
    low = sorted({p_["year"] for s in out_series for p_ in s["points"] if p_["low_base"] and p_["words"]})
    if low:
        notes.append(f"Low base (< {LOW_BASE_WORDS:,} words or < {LOW_BASE_SESSIONS} sessions) in: "
                     f"{', '.join(map(str, low))}. Do not read peaks there as trends.")
    if measure != "count":
        notes += _long_turn_notes(f)
    notes += _undated_note(f)
    result = {"terms": [s["label"] for s in series_def], "measure": measure, "smoothing": smoothing,
              "filters": _filters_dict(f),
              "series": out_series, "notes": notes, "datasets": _versions(countries)}
    if chart_path:
        result["chart"] = _ngram_chart(result, chart_path, title, language, overwrite)
    return result


_LABELS = {
    "es": {"per_million": "apariciones por millón de palabras", "count": "apariciones",
           "interventions_pct": "% de intervenciones que lo usan", "smooth": "media móvil de {k} años",
           "low": "año con base escasa (menos de 250 000 palabras o de 10 sesiones)",
           "source": "Fuente: {title}, Harvard Dataverse", "speech": "solo habla parlamentaria",
           "cap": "sin turnos de más de {n} palabras", "chair": "sin la presidencia"},
    "en": {"per_million": "occurrences per million words", "count": "occurrences",
           "interventions_pct": "% of interventions using it", "smooth": "{k}-year moving average",
           "low": "low-base year (under 250,000 words or 10 sessions)",
           "source": "Source: {title}, Harvard Dataverse", "speech": "parliamentary speech only",
           "cap": "turns over {n} words left out", "chair": "chair left out"},
    "pt": {"per_million": "ocorrências por milhão de palavras", "count": "ocorrências",
           "interventions_pct": "% de intervenções que o usam", "smooth": "média móvel de {k} anos",
           "low": "ano com base escassa (menos de 250 000 palavras ou de 10 sessões)",
           "source": "Fonte: {title}, Harvard Dataverse", "speech": "apenas fala parlamentar",
           "cap": "sem turnos de mais de {n} palavras", "chair": "sem a presidência"},
}


def _ngram_chart(result: dict, path: str, title: str | None, language: str, overwrite: bool) -> str:
    L = _LABELS.get(language[:2], _LABELS["es"])
    if len(result["series"]) > charts.MAX_SERIES:
        raise ValueError(f"The chart takes at most {charts.MAX_SERIES} series; got {len(result['series'])}")
    series = {s["label"]: [{"x": p["year"], "y": p["value"], "low": p["low_base"] and p["words"] > 0}
                           for p in s["points"]] for s in result["series"]}
    isos = sorted(result["datasets"])
    sub = [L[result["measure"]]]
    if result["smoothing"]:
        sub.append(L["smooth"].format(k=2 * result["smoothing"] + 1))
    sub.append(", ".join(isos) if len(isos) <= 8 else f"{len(isos)} países")
    if result["filters"].get("speech_only"):
        sub.append(L["speech"])
    if result["filters"].get("max_turn_words"):
        sub.append(L["cap"].format(n=f'{result["filters"]["max_turn_words"]:,}'.replace(",", " ")))
    if result["filters"].get("exclude_chair"):
        sub.append(L["chair"])
    for k in ("party", "sex"):
        if result["filters"].get(k):
            sub.append(f'{k}: {result["filters"][k]}')
    for k, v in (result["filters"].get("extra") or {}).items():
        sub.append(f"{k}: {v}")
    dois = " · ".join(f"{i} doi:{d['doi']}" + (f" v{d['version']}" if d["version"] else "")
                      for i, d in result["datasets"].items())
    source = L["source"].format(title=profile.ACTIVE.title)
    note = f"{source} · {dois}" if len(isos) <= 3 else f"{source} · {len(isos)} datasets"
    low = any(p["low"] for pts in series.values() for p in pts)
    default_title = " · ".join(result["terms"])
    return charts.write_chart(path, series, title or default_title,
                              " · ".join(sub), L[result["measure"]], note, L["low"] if low else None,
                              overwrite)


def _filters_dict(f: Filters) -> dict:
    d = {k: v for k, v in f.__dict__.items() if v not in (None, [], False) or k == "speech_only"}
    if "library" in d:                  # the name is what a reader understands, not the internal id
        d["library"] = d.pop("library_name", d["library"])
    d.pop("library_name", None)
    return d


# ── term counter ──────────────────────────────────────────────────────────────

def term_counter(terms, f: Filters, top_parties: int = 8) -> dict:
    out = []
    for s in parse_terms(terms):
        p: list = []
        cond, occ, occ_params = _series_sql(s["variants"], p)
        where = f.where(p)
        # filter occ > 0 in Python: in SQL the optimizer pushes it into the scan and computes the
        # (expensive) exact count on every row instead of only on the prefiltered ones
        rows = [r for r in _q(f"SELECT country, date, id_int, id_session, id_dep, speaker_raw, "
                              f"speaker_name, sex, party, {occ} AS occ FROM interventions WHERE {cond}{where}",
                              occ_params + p, max_rows=5_000_000) if r["occ"] > 0]
        if not rows:
            out.append({"term": s["label"], "occurrences": 0})
            continue
        dp: list = []
        den_sex = {r["sex"]: r["w"] for r in _q(
            f"SELECT coalesce(sex, '(unlinked)') AS sex, sum(n_words) AS w FROM interventions "
            f"WHERE true{f.where(dp)} GROUP BY 1", dp)}
        dp = []
        den_party = {r["party"]: r["w"] for r in _q(
            f"SELECT coalesce(party, '(unlinked)') AS party, sum(n_words) AS w FROM interventions "
            f"WHERE true{f.where(dp)} GROUP BY 1", dp)}
        occ_sex, occ_party = Counter(), Counter()
        by_country: dict[str, dict] = {}
        for r in rows:
            occ_sex[r["sex"] or "(unlinked)"] += r["occ"]
            occ_party[r["party"] or "(unlinked)"] += r["occ"]
            c = by_country.setdefault(r["country"], {"occurrences": 0, "first": None, "last": None})
            c["occurrences"] += r["occ"]
            if r["date"] is None:      # undated rows count, but cannot be a first or last use
                continue
            if c["first"] is None or (r["date"], r["id_int"]) < (c["first"]["date"], c["first"]["id_int"]):
                c["first"] = r
            if c["last"] is None or (r["date"], r["id_int"]) > (c["last"]["date"], c["last"]["id_int"]):
                c["last"] = r

        def use(r):
            if r is None:
                return None
            return {"date": str(r["date"]), "id_int": r["id_int"],
                    "speaker": r["speaker_name"] or r["speaker_raw"], "party": r["party"]}

        out.append({
            "term": s["label"], "variants": s["variants"],
            "occurrences": sum(r["occ"] for r in rows),
            "interventions": len(rows),
            "sessions": len({r["id_session"] for r in rows}),
            "speakers": len({r["id_dep"] or f'{r["country"]}:{r["speaker_raw"]}' for r in rows}),
            "linked_deputies": len({r["id_dep"] for r in rows if r["id_dep"]}),
            "by_sex": {k: {"occurrences": v, "per_million_words": round(v * 1e6 / den_sex[k], 2)
                           if den_sex.get(k) else None} for k, v in occ_sex.most_common()},
            "top_parties": [{"party": k, "occurrences": v,
                             "per_million_words": round(v * 1e6 / den_party[k], 2) if den_party.get(k) else None}
                            for k, v in occ_party.most_common(top_parties)],
            "by_country": {c: {"occurrences": d["occurrences"], "first_use": use(d["first"]),
                               "last_use": use(d["last"])} for c, d in sorted(by_country.items())},
        })
    return {"filters": _filters_dict(f), "terms": out, "notes": _long_turn_notes(f),
            "note": "Whole-word, case- and accent-insensitive counts. per_million_words divides by all "
                    "words of that sex or party under the same filters. '(unlinked)' = speakers not "
                    "linked to a deputy (ministers, clerks, collective voices).",
            "datasets": _versions({c for t in out for c in t.get("by_country", {})})}


# ── share of voice ────────────────────────────────────────────────────────────

def share_of_voice(f: Filters, by: str = "sex", per: str = "legislature", unit: str = "words") -> dict:
    if by not in profile.ACTIVE.groups():
        raise ValueError(f"by must be one of {', '.join(profile.ACTIVE.groups())}")
    if unit not in ("words", "turns"):
        raise ValueError("unit must be 'words' or 'turns'")
    if per not in ("legislature", "year", "all"):
        raise ValueError("per must be 'legislature', 'year' or 'all'")
    g = by
    period = {"legislature": "legislature", "year": "CAST(year(date) AS VARCHAR)", "all": "'all'"}[per]
    p: list = []
    base = f.where(p)
    rows = _q(f"""
        SELECT country, {period} AS period, min(date) AS d0, max(date) AS d1,
               {g} AS grp, sum(n_words) AS words, count(*) AS turns, count(DISTINCT id_dep) AS speakers
        FROM interventions WHERE id_dep IS NOT NULL AND {g} IS NOT NULL AND date IS NOT NULL{base}
        GROUP BY ALL""", p)
    if not rows:
        raise store.NoData("No linked speech matches these filters.")
    p = []
    base = f.where(p)
    spans = {(r["country"], r["period"]): r for r in _q(f"""
        SELECT country, {period} AS period, min(date) AS d0, max(date) AS d1, sum(n_words) AS all_words,
               sum(n_words) FILTER (WHERE id_dep IS NOT NULL) AS linked_words
        FROM interventions WHERE date IS NOT NULL{base} GROUP BY ALL""", p)}
    # members on the register during each period, by date overlap (works whatever the labels)
    members: dict[tuple, Counter] = defaultdict(Counter)
    isos = sorted({r["country"] for r in rows})
    reg = _q(f"""SELECT country, id_dep, {g} AS grp, TRY_CAST(start_date AS DATE) AS s,
                 coalesce(TRY_CAST(end_date AS DATE), DATE '2999-12-31') AS e
                 FROM deputies WHERE country IN ({', '.join('?' * len(isos))}) AND {g} IS NOT NULL""", isos)
    by_country_reg = defaultdict(list)
    for r in reg:
        if r["s"]:
            by_country_reg[r["country"]].append(r)
    for (c, per_), sp in spans.items():
        seen = {}
        for r in by_country_reg.get(c, []):
            if r["s"] <= sp["d1"] and r["e"] >= sp["d0"]:
                seen.setdefault(r["id_dep"], r["grp"])
        members[(c, per_)] = Counter(seen.values())
    totals = defaultdict(lambda: {"words": 0, "turns": 0, "speakers": 0})
    for r in rows:
        t = totals[(r["country"], r["period"])]
        t["words"] += r["words"]
        t["turns"] += r["turns"]
        t["speakers"] += r["speakers"]
    out = []
    for r in sorted(rows, key=lambda r: (r["country"], spans[(r["country"], r["period"])]["d0"], -r["words"])):
        key = (r["country"], r["period"])
        t, m, sp = totals[key], members[key], spans[key]
        mtot = sum(m.values())
        voice = r[unit] / t[unit] if t[unit] else None
        mshare = m.get(r["grp"], 0) / mtot if mtot else None
        out.append({
            "country": r["country"], "period": r["period"], "from": str(sp["d0"]), "to": str(sp["d1"]),
            "group": r["grp"], unit: r[unit], "voice_share": _r(voice),
            "speakers": r["speakers"], "speakers_share": _r(r["speakers"] / t["speakers"] if t["speakers"] else None),
            "members_on_register": m.get(r["grp"], 0), "members_share": _r(mshare),
            "voice_to_members_ratio": _r(voice / mshare if voice is not None and mshare else None),
            "linked_share_of_speech": _r(sp["linked_words"] / sp["all_words"] if sp["all_words"] else None),
        })
    return {"by": by, "per": per, "unit": unit, "filters": _filters_dict(f), "rows": out,
            "notes": [
                "voice_share: share of the words (or turns) spoken by linked deputies. Speech by unlinked "
                "speakers (ministers, clerks, collective voices) is outside the denominator; "
                "linked_share_of_speech says how much of all speech that leaves in.",
                "members_share: share of distinct deputies on the register whose mandate overlaps the period. "
                "Registers include substitutes and replacements, so this approximates seat share.",
                "voice_to_members_ratio > 1: the group speaks more than its weight on the register.",
            ] + (_long_turn_notes(f) if unit == "words" else [])
              + ([] if f.exclude_chair else ["Chairing the sitting counts as voice here; exclude_chair=true "
                                              "leaves the presiding officer's turns out."])
              + _undated_note(f),
            "datasets": _versions(isos)}


def _r(v, n=4):
    return None if v is None else round(v, n)


# ── distinctive words ─────────────────────────────────────────────────────────

def distinctive_words(f: Filters, field: str, a: str, b: str | None = None, top: int = 30,
                      min_count: int = 20, alpha0: float = 1000.0) -> dict:
    """Weighted log-odds ratio with an informative Dirichlet prior (Monroe, Colaresi & Quinn 2008)."""
    field = field.lower()
    fields = ("party", "period", "country", "id_dep", "library") + (("sex",) if profile.ACTIVE.has_sex else ()) \
        + tuple(profile.ACTIVE.extra_columns)
    if field not in fields:
        raise ValueError(f"field must be one of {', '.join(fields)}")
    if field == "library":
        from . import library as _lib     # late: library imports this module
        lib_a, isos_a = _lib.resolve(a)
        lib_b, isos_b = _lib.resolve(b) if b not in (None, "", "rest") else (None, [])
        if not f.countries:               # 'rest' = the rest of the library's own chambers
            f.countries = sorted(set(isos_a) | set(isos_b))

    def cond(value: str, params: list, alias="") -> str:
        if field == "library":
            lid = lib_a if value == a else lib_b
            return f"{alias}id_int IN (SELECT id_int FROM lib.library_items WHERE library_id = {int(lid)})"
        col = f"{alias}{field}" if field != "period" else f"{alias}year"
        if field == "period":
            y0, _, y1 = str(value).partition("-")
            params.extend([int(y0), int(y1 or y0)])
            return f"{col} BETWEEN ? AND ?" if alias != "i." else "year(i.date) BETWEEN ? AND ?"
        if field == "party" or field in profile.ACTIVE.extra_columns:
            params.append(value)
            return f"{col} ILIKE ?"
        params.append(normalize_iso(value) if field == "country" else
                      value.upper()[:1] if field == "sex" else value)
        return f"{col} = ?"

    use_uni = field in ("sex", "period", "country") and f.unigram_ok()
    p: list = []
    if use_uni:
        ca = cond(a, p)
        cb = f"NOT ({cond(a, p)})" if b in (None, "", "rest") else cond(b, p)
        w = f.unigram_where(p)
        counts_sql = f"""SELECT u.fold AS f, sum(n) FILTER (WHERE {ca}) AS ya, sum(n) FILTER (WHERE {cb}) AS yb,
                         NULL AS word FROM unigrams u WHERE true{w} GROUP BY 1"""
    else:
        ca = cond(a, p, "i.")
        cb = f"NOT ({cond(a, p, 'i.')})" if b in (None, "", "rest") else cond(b, p, "i.")
        w = f.where(p, alias="i")
        counts_sql = f"""SELECT strip_accents(w) AS f, sum(n) FILTER (WHERE g = 'a') AS ya,
                         sum(n) FILTER (WHERE g = 'b') AS yb, arg_max(w, n) AS word FROM (
                           SELECT g, w, count(*) AS n FROM (
                             SELECT CASE WHEN {ca} THEN 'a' WHEN {cb} THEN 'b' END AS g,
                                    unnest(regexp_extract_all(lower(i.text), '[\\pL\\pN]+')) AS w
                             FROM interventions i WHERE true{w})
                           WHERE g IS NOT NULL GROUP BY ALL) GROUP BY 1"""
    k = int(top)
    sql = f"""
        WITH c AS ({counts_sql}),
        t AS (SELECT sum(coalesce(ya, 0)) AS na, sum(coalesce(yb, 0)) AS nb FROM c),
        s AS (
          SELECT c.f, c.word, coalesce(ya, 0) AS ya0, coalesce(yb, 0) AS yb0, t.na, t.nb,
                 {alpha0} * (coalesce(ya, 0) + coalesce(yb, 0)) / (t.na + t.nb) AS al
          FROM c, t WHERE coalesce(ya, 0) + coalesce(yb, 0) >= {int(min_count)} AND length(c.f) >= 2
            AND NOT regexp_full_match(c.f, '[0-9]+')),
        z AS (
          SELECT f, word, ya0, yb0, na, nb,
                 (ln((ya0 + al) / (na + {alpha0} - ya0 - al)) - ln((yb0 + al) / (nb + {alpha0} - yb0 - al)))
                   / sqrt(1 / (ya0 + al) + 1 / (yb0 + al)) AS z FROM s),
        top AS ((SELECT *, 'a' AS side FROM z ORDER BY z DESC LIMIT {k})
                UNION ALL (SELECT *, 'b' AS side FROM z ORDER BY z ASC LIMIT {k}))
        SELECT side, coalesce(top.word, (SELECT arg_max(v.word, v.n) FROM vocab v WHERE v.fold = top.f), top.f)
                 AS word, ya0 AS count_a, yb0 AS count_b,
               round(ya0 * 1e6 / na, 2) AS per_million_a, round(yb0 * 1e6 / nb, 2) AS per_million_b,
               round(z, 2) AS z, na, nb
        FROM top ORDER BY side, abs(z) DESC"""
    rows = _q(sql, p, max_rows=2 * k)
    if not rows:
        raise store.NoData("No words for these groups and filters.")
    na, nb = rows[0]["na"], rows[0]["nb"]
    for r in rows:
        del r["na"], r["nb"]
    notes = ["Method: weighted log-odds ratio with an informative Dirichlet prior (Monroe, Colaresi & "
             f"Quinn 2008, 'Fightin' Words'), prior = pooled frequencies, alpha0 = {alpha0:g}. |z| > 1.96 "
             "is the usual threshold; with corpora this size most of the top words clear it by far."]
    if field not in ("period", "country", "id_dep", "library") and not f.exclude_chair:
        notes.append("The chair's procedural speech (calling votes, giving the floor) can dominate a group "
                     "— e.g. when the Speaker is a woman, 'votación' turns up as a women's word. Re-run "
                     "with exclude_chair=true.")
    notes += _long_turn_notes(f)
    if field == "country" and len({x in PORTUGUESE for x in (normalize_iso(a), normalize_iso(b or a))}) > 1:
        notes.append("You are comparing a Spanish- and a Portuguese-language corpus: the result is mostly language.")
    return {"field": field, "a": a, "b": b or "rest", "filters": _filters_dict(f),
            "words_a": na, "words_b": nb, "method": "unigram index" if use_uni else "exact scan",
            "distinctive_of_a": [{k_: v for k_, v in r.items() if k_ != "side"} for r in rows if r["side"] == "a"],
            "distinctive_of_b": [{k_: v for k_, v in r.items() if k_ != "side"} for r in rows if r["side"] == "b"],
            "notes": notes, "datasets": _versions(_scope(f))}


# ── concordances and collocations ─────────────────────────────────────────────

def _py_regex(pattern: str, regex: bool, whole_word: bool) -> re.Pattern:
    if regex:
        return re.compile(pattern.replace("(?i)", ""), re.IGNORECASE)
    rx = search_regex(pattern, False, whole_word)[4:]
    rx = (rx.replace(r"(?:^|[^\pL\pN])", r"(?<![^\W_])").replace(r"(?:$|[^\pL\pN])", r"(?![^\W_])")
            .replace(r"[^\pL\pN]+", r"[\W_]+").replace(r"[\pL\pN]*", r"[^\W_]*")
            .replace(r"\pM*", "[\u0300-\u036f]*"))
    return re.compile(rx, re.IGNORECASE)


def _snippet(text: str, rx: re.Pattern, width: int = 220) -> str:
    if not text:
        return ""
    m = rx.search(text)
    if m is None:
        return text[: 2 * width] + ("…" if len(text) > 2 * width else "")
    a, b = max(0, m.start() - width), min(len(text), m.end() + width)
    return ("…" if a else "") + text[a:b] + ("…" if b < len(text) else "")


def search_text(pattern: str, f: Filters, regex: bool = False, whole_word: bool = False, limit: int = 20,
                offset: int = 0) -> dict:
    """Interventions matching a word, phrase or regex, newest first, with a snippet around the
    first match and the total number of matching rows."""
    rx = search_regex(pattern, regex, whole_word)
    params: list = [rx]
    where = "regexp_matches(text, ?)" + f.where(params)
    _, total, _ = store.run_query(f"SELECT count(*) FROM interventions WHERE {where}", params)
    _, ids, _ = store.run_query(
        f"SELECT id_int FROM interventions WHERE {where} ORDER BY date DESC, id_int "
        f"LIMIT {int(limit)} OFFSET {int(offset)}", params, max_rows=limit)
    hits = []
    py_rx = _py_regex(pattern, regex, whole_word)
    if ids:
        id_list = [r[0] for r in ids]
        extra = "".join(f", {c}" for c in profile.ACTIVE.extra_columns)
        cols, rows, _ = store.run_query(
            f"SELECT country, id_int, id_session, date, speaker_name, speaker_raw, party, sex{extra}, n_words, "
            f"text FROM interventions WHERE id_int IN ({', '.join('?' * len(id_list))})", id_list,
            max_rows=limit)
        by_id = {r[1]: dict(zip(cols, r)) for r in rows}
        for i in id_list:
            d = by_id[i]
            d["snippet"] = _snippet(d.pop("text") or "", py_rx)
            hits.append({k: store.jsonable(v) for k, v in d.items()})
    return {"regex_used": rx, "total_matching_rows": total[0][0], "returned": len(hits),
            "offset": offset, "hits": hits}


def _matching_sample(pattern, f: Filters, regex, whole_word, n, order, seed, cols):
    p: list = [search_regex(pattern, regex, whole_word)]
    where = "regexp_matches(text, ?)" + f.where(p)
    total = _q(f"SELECT count(*) AS n FROM interventions WHERE {where}", list(p))[0]["n"]
    order_sql = {"random": f"hash(id_int || '{int(seed)}')", "newest": "date DESC, id_int",
                 "oldest": "date, id_int"}[order]
    rows = _q(f"SELECT {cols} FROM interventions WHERE {where} ORDER BY {order_sql} LIMIT {int(n)}", p)
    return total, rows


def kwic(pattern: str, f: Filters, regex: bool = False, whole_word: bool = True, n: int = 40,
         width: int = 70, order: str = "random", seed: int = 1, per_intervention: int = 2) -> dict:
    total, rows = _matching_sample(pattern, f, regex, whole_word, n, order, seed,
                                   "country, id_int, date, speaker_name, speaker_raw, party, text")
    rx = _py_regex(pattern, regex, whole_word)
    lines = []
    for r in rows:
        text = re.sub(r"\s+", " ", r["text"] or "")
        for m in list(rx.finditer(text))[:per_intervention]:
            lines.append({"id_int": r["id_int"], "date": str(r["date"]), "country": r["country"],
                          "speaker": r["speaker_name"] or r["speaker_raw"], "party": r["party"],
                          "left": text[max(0, m.start() - width):m.start()],
                          "match": m.group(0), "right": text[m.end():m.end() + width]})
    view = "\n".join(f"{l['date']} {l['country']} | {l['left']:>{width}} [[{l['match']}]] {l['right']}"
                     for l in lines)
    return {"pattern": pattern, "total_matching_interventions": total, "sampled_interventions": len(rows),
            "order": order, "lines": lines, "text_view": view, "datasets": _versions(_scope(f))}


def collocations(pattern: str, f: Filters, window: int = 5, top: int = 30, min_count: int = 5,
                 sample: int = 5000, exclude_stopwords: bool = True, seed: int = 1) -> dict:
    """Words over-represented within ±window tokens of the term, against the rest of the same
    interventions (Dunning log-likelihood)."""
    parts = pattern.split()
    if not parts:
        raise ValueError("Empty pattern")
    t_tokens = [fold(w) for w in parts]
    total, rows = _matching_sample(pattern, f, False, True, sample, "random", seed, "text")

    def is_term_at(toks, i):
        for k, tt in enumerate(t_tokens):
            if i + k >= len(toks):
                return False
            if tt.endswith("*"):
                if not toks[i + k].startswith(tt[:-1]):
                    return False
            elif toks[i + k] != tt:
                return False
        return True

    near, far, display = Counter(), Counter(), defaultdict(Counter)
    hits = 0
    for r in rows:
        raw = tokens(r["text"])
        toks = [fold(x) for x in raw]
        for x, y in zip(toks, raw):
            display[x][y] += 1
        in_win = [False] * len(toks)
        is_term = [False] * len(toks)
        for i in range(len(toks)):
            if is_term_at(toks, i):
                hits += 1
                for k in range(len(t_tokens)):
                    is_term[i + k] = True
                for j in range(max(0, i - window), min(len(toks), i + len(t_tokens) + window)):
                    in_win[j] = True
        for x, w, t in zip(toks, in_win, is_term):
            if t or (exclude_stopwords and x in STOPWORDS) or len(x) < 2 or x.isdigit():
                continue
            (near if w else far)[x] += 1
    n_near, n_far = sum(near.values()), sum(far.values())
    out = []
    for w, a in near.items():
        if a < min_count:
            continue
        b = far.get(w, 0)
        e_near = (a + b) * n_near / (n_near + n_far)
        e_far = (a + b) * n_far / (n_near + n_far)
        if a <= e_near:
            continue
        g2 = 2 * (a * math.log(a / e_near) + (b * math.log(b / e_far) if b else 0))
        out.append({"word": display[w].most_common(1)[0][0], "near": a, "elsewhere": b,
                    "per_thousand_near": round(a * 1000 / n_near, 2),
                    "per_thousand_elsewhere": round(b * 1000 / n_far, 2) if n_far else None,
                    "log_likelihood": round(g2, 1)})
    out.sort(key=lambda x: -x["log_likelihood"])
    return {"pattern": pattern, "window": window, "total_matching_interventions": total,
            "sampled_interventions": len(rows), "term_occurrences_in_sample": hits,
            "collocates": out[:top], "datasets": _versions(_scope(f)),
            "note": "Dunning log-likelihood of each word inside the window versus elsewhere in the same "
                    "interventions; G² > 10.8 ≈ p < 0.001. Run twice with different dates to compare periods."}


# ── coverage ──────────────────────────────────────────────────────────────────

def coverage(f: Filters, by: str = "year") -> dict:
    period = {"year": "year(date)", "legislature": "legislature"}[by]
    p: list = []
    f2 = Filters(f.countries, f.date_from, f.date_to, f.party, f.sex, f.id_dep, speech_only=False,
                 exclude_chair=f.exclude_chair, max_turn_words=f.max_turn_words, library=f.library,
                 library_name=f.library_name)
    rows = _q(f"""SELECT country, {period} AS period, min(date) AS d0, max(date) AS d1,
                  count(DISTINCT id_session) AS sessions, count(*) AS rows,
                  count(*) FILTER (WHERE dm_speech = 1) AS speech_rows,
                  sum(n_words) FILTER (WHERE dm_speech = 1) AS speech_words,
                  round(100.0 * count(*) FILTER (WHERE dm_speech = 1 AND id_dep IS NOT NULL)
                        / nullif(count(*) FILTER (WHERE dm_speech = 1), 0), 1) AS linked_pct,
                  round(100.0 * count(*) FILTER (WHERE dm_speech = 1 AND sex IS NOT NULL)
                        / nullif(count(*) FILTER (WHERE dm_speech = 1), 0), 1) AS sex_known_pct,
                  round(100.0 * sum(n_words) FILTER (WHERE dm_speech = 1 AND n_words > {LONG_TURN})
                        / nullif(sum(n_words) FILTER (WHERE dm_speech = 1), 0), 1) AS long_turn_words_pct
                  FROM interventions WHERE date IS NOT NULL{f2.where(p)} GROUP BY ALL ORDER BY country, d0""", p)
    if not rows:
        raise store.NoData("No rows match these filters.")
    per_country = defaultdict(list)
    for r in rows:
        r["low_base"] = (r["speech_words"] or 0) < LOW_BASE_WORDS or r["sessions"] < LOW_BASE_SESSIONS
        r["d0"], r["d1"] = str(r["d0"]), str(r["d1"])
        per_country[r["country"]].append(r)
    summary = {}
    for c, rs in per_country.items():
        info = {}
        if by == "year":
            ys = sorted(r["period"] for r in rs)
            info["missing_years"] = [y for y in range(ys[0], ys[-1] + 1) if y not in set(ys)]
            words = [r["speech_words"] or 0 for r in rs]
            info["median_words_per_year"] = int(median(words))
        info["low_base_periods"] = [r["period"] for r in rs if r["low_base"]]
        tot = sum(r["speech_words"] or 0 for r in rs)
        info["long_turn_words_pct"] = round(sum((r["long_turn_words_pct"] or 0) * (r["speech_words"] or 0)
                                                for r in rs) / tot, 1) if tot else None
        try:
            ci = json.loads(store.read_document(c, "corpus_info"))
            lk = ci.get("linkage", {})
            info["corpus_linkage"] = {k: lk.get(k) for k in ("gross", "effective") if k in lk}
        except Exception:
            pass
        summary[c] = info
    return {"by": by, "filters": _filters_dict(f), "summary": summary, "rows": rows,
            "datasets": _versions(per_country),
            "notes": ["linked_pct: speech rows with an id_dep (gross linkage). corpus_linkage.effective "
                      "discounts speakers who cannot hold a seat; read known_limitations for each country.",
                      f"low_base: under {LOW_BASE_WORDS:,} speech words or {LOW_BASE_SESSIONS} sessions.",
                      f"long_turn_words_pct: share of speech words in turns over {LONG_TURN:,} words, mostly "
                      "documents read into the record and kept as speech where the record marks no "
                      "separator. Word-based comparisons between countries depend on it."] + _undated_note(f2)}


# ── export and query log ──────────────────────────────────────────────────────

def export_result(sql: str, path: str, fmt: str | None = None, overwrite: bool = False) -> dict:
    stmts = duckdb.extract_statements(sql)
    if len(stmts) != 1 or stmts[0].type != duckdb.StatementType.SELECT:
        raise ValueError("export_result takes exactly one SELECT (or WITH … SELECT) statement")
    out = Path(path).expanduser()
    if not out.is_absolute():
        out = Path.cwd() / out
    fmt = (fmt or out.suffix.lstrip(".")).lower()
    if fmt not in ("csv", "parquet"):
        raise ValueError("format must be csv or parquet (or use a .csv / .parquet path)")
    if out.exists() and not overwrite:
        raise FileExistsError(f"{out} already exists; pass overwrite=true to replace it")
    out.parent.mkdir(parents=True, exist_ok=True)
    body = stmts[0].query.strip().rstrip(";")
    target = "'" + str(out).replace("'", "''") + "'"
    opts = "FORMAT CSV, HEADER" if fmt == "csv" else "FORMAT PARQUET"
    with store.export_connection(out.parent) as con:
        con.execute(f"COPY ({body}) TO {target} ({opts})")
        n = con.execute(f"SELECT count(*) FROM ({body})").fetchone()[0]
    return {"path": str(out), "format": fmt, "rows": n}


def log_call(tool: str, args: dict) -> None:
    if store.LOG_DISABLED:
        return
    try:
        entry = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tool": tool,
                 "args": {k: v for k, v in args.items() if v not in (None, [], "")},
                 "datasets": {k: v.get("version") for k, v in store.loaded().items()
                              if not args.get("countries")
                              or k in {normalize_iso(c) for c in args["countries"]}}}
        store.HOME.mkdir(parents=True, exist_ok=True)
        with (store.HOME / "query_log.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def query_log(last: int = 50, methods_path: str | None = None, overwrite: bool = False) -> dict:
    f = store.HOME / "query_log.jsonl"
    entries = []
    if f.exists():
        entries = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()][-last:]
    result = {"log_file": str(f), "entries": entries}
    if methods_path:
        isos = sorted({k for e in entries for k in e.get("datasets", {})})
        p = profile.ACTIVE
        lines = ["# Data and queries", "",
                 f"Data: {p.title} (Harvard Dataverse, CC BY 4.0)" +
                 (", one dataset per country:" if p.name == "parlaibero" else ":"), ""]
        for i in isos:
            v = next((e["datasets"][i] for e in reversed(entries) if e["datasets"].get(i)), None)
            lines.append(f"- {COUNTRIES[i][0]}: https://doi.org/{COUNTRIES[i][2]}" + (f", version {v}" if v else ""))
        lines += ["", f"Analyses run with {p.package} ({p.repository}):", ""]
        for e in entries:
            lines.append(f"- {e['time']} · `{e['tool']}` · `{json.dumps(e['args'], ensure_ascii=False)}`")
        out = Path(methods_path).expanduser()
        if not out.is_absolute():
            out = Path.cwd() / out
        if out.exists() and not overwrite:
            raise FileExistsError(f"{out} already exists; pass overwrite=true to replace it")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result["methods_file"] = str(out)
    return result


# ── term frequency by group ───────────────────────────────────────────────────

GROUPS = {
    "year": "year(date)",
    "decade": "(year(date) // 10) * 10",
    "country": "country",
    "legislature": "country || ' ' || legislature",
    "party": "country || ' ' || coalesce(party, '(unlinked)')",
    "sex": "coalesce(sex, '(unlinked)')",
    "speaker": "country || ' ' || coalesce(speaker_name, speaker_raw)",
    "session_type": "session_type",
    # to find a country's event: the sessions where a term concentrates
    "session": "country || ' ' || coalesce(CAST(date AS VARCHAR), '?') || ' ' || id_session",
}


def groups() -> dict[str, str]:
    """GROUPS, without sex if the collection has none, plus the profile's extra columns."""
    g = {k: v for k, v in GROUPS.items() if k != "sex" or profile.ACTIVE.has_sex}
    for col in profile.ACTIVE.extra_columns:
        g[col] = f"coalesce({col}, '(unlinked)')"
    return g


def term_frequency(pattern: str, f: Filters, by: str = "year", max_rows: int = 300) -> dict:
    """Same whole-word, accent-insensitive count as ngram_viewer, grouped by any dimension."""
    G = groups()
    if by not in G:
        raise ValueError(f"by must be one of {', '.join(G)}")
    s = parse_terms(pattern.replace(",", "+"))[0]
    pre: list = []
    cond, occ, occ_params = _series_sql(s["variants"], pre)
    p: list = []
    w = f.where(p)
    sql = (f"WITH t AS (SELECT {G[by]} AS grp, n_words, CASE WHEN {cond} "
           f"THEN {occ} ELSE 0 END AS occ FROM interventions WHERE text IS NOT NULL{w}) "
           f"SELECT grp AS {by}, sum(occ) AS occurrences, count(*) FILTER (WHERE occ > 0) AS "
           f"interventions_using, sum(n_words) AS total_words, "
           f"round(sum(occ) * 1e6 / nullif(sum(n_words), 0), 2) AS per_million_words "
           f"FROM t GROUP BY grp " + ("HAVING sum(occ) > 0 " if by == "session" else "") + "ORDER BY " +
           ("occurrences DESC, grp" if by in ("speaker", "party", "session") else "grp"))
    rows = _q(sql, pre + occ_params + p, max_rows=max_rows)
    return {"term": s["label"], "variants": s["variants"], "by": by, "filters": _filters_dict(f),
            "rows": [{k: store.jsonable(v) for k, v in r.items()} for r in rows],
            "note": "Whole-word, case- and accent-insensitive; '+' sums variants, '*' ends a prefix.",
            "datasets": _versions(_scope(f))}
