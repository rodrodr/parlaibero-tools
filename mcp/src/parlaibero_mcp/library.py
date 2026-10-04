"""Libraries: named, persistent subsets of interventions, of one or several countries.

A library is a set of interventions (`library_items`) grouped in one part per country
(`library_parts`), each part with the edition of that country's data it was built on and the
definitions that built it. They live in their own file (store.LIBDB) and are attached as `lib` to
every connection, so any analysis can be restricted to a library (Filters.library) and query_sql can
join `lib.library_items` with `interventions`.

The explorer (Diarios Explorer) keeps one library per corpus, i.e. per country. A library is written
for it as one `.2replib` file per country plus an index that puts the comparison back together
(`export`), and `.2replib` files written by the explorer can be read back (`import_files`).
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import __version__, store
from .analysis import (CHAIR_RX, LONG_TURN, NOT_CHAIR_RX, PORTUGUESE, Filters, _date, _filters_dict, _q,
                       _series_sql)
from .catalog import COUNTRIES, normalize_iso
from .textutil import parse_terms, search_regex

FORMAT = "2replib/1"
INDEX_FORMAT = "parlaibero-biblioteca/1"
DEFINITION_KEYS = ("terms", "regex", "min_occurrences", "date_from", "date_to", "party", "sex", "id_dep",
                   "speech_only", "exclude_chair", "max_turn_words")
# Below this many interventions in a year, a part's yearly figures are anecdotal.
THIN_YEAR = 5


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _loaded_editions() -> dict[str, str | None]:
    return {iso: d.get("version") for iso, d in store.loaded().items()}


# ── looking libraries up ──────────────────────────────────────────────────────

def _get(name: str) -> dict:
    """The library called `name` (case-insensitive) with its parts, or a readable error."""
    cols, rows, _ = store.run_query("SELECT id, name, description, color, created_at, updated_at FROM lib.libraries "
                                    "WHERE lower(name) = lower(?)", [name])
    if not rows:
        known = [r[0] for r in store.run_query("SELECT name FROM lib.libraries ORDER BY name")[1]]
        raise LookupError(f"No library called {name!r}." + (f" Libraries: {', '.join(known)}." if known else
                                                              " There are no libraries yet: use library_create."))
    lib = dict(zip(cols, rows[0]))
    pcols, prows, _ = store.run_query("SELECT country, edition, doi, definitions FROM lib.library_parts "
                                      "WHERE library_id = ? ORDER BY country", [lib["id"]])
    lib["parts"] = {r[0]: {"edition": r[1], "doi": r[2], "definitions": json.loads(r[3] or "[]")} for r in prows}
    return lib


def resolve(name: str) -> tuple[int, list[str]]:
    """(library id, its countries) for Filters.library. Refuses a library built on another edition
    of the data: its intervention ids would point to other interventions."""
    lib = _get(name)
    loaded = _loaded_editions()
    stale = [f"{c} (library {p['edition']}, loaded {loaded.get(c, 'not loaded')})"
             for c, p in lib["parts"].items() if loaded.get(c) != p["edition"]]
    if stale:
        raise RuntimeError(f"Library {lib['name']!r} was built on other editions of the data: {', '.join(stale)}. "
                           f"Intervention ids are only stable within an edition: run library_rebuild first.")
    return lib["id"], sorted(lib["parts"])


# ── building ──────────────────────────────────────────────────────────────────

def _definition_filters(iso: str, d: dict) -> Filters:
    return Filters([iso], d.get("date_from"), d.get("date_to"), d.get("party"), d.get("sex"), d.get("id_dep"),
                   d.get("speech_only", True), d.get("exclude_chair", False), d.get("max_turn_words"))


def _insert_definition(con, lib_id: int, iso: str, d: dict) -> int:
    """Add to the library the interventions of one country that meet a definition. Returns how many
    interventions matched (some may already have been in the library)."""
    f = _definition_filters(iso, d)
    params: list = []
    where = f.where(params)
    terms = d.get("terms")
    if terms and d.get("regex"):
        cond, occ, occ_params = "regexp_matches(text, ?)", "len(regexp_extract_all(text, ?))", [terms]
        params.insert(0, terms)
    elif terms:
        variants = [v for s in parse_terms(terms) for v in s["variants"]]
        pre: list = []
        cond, occ, occ_params = _series_sql(variants, pre)
        params = pre + params
    else:
        cond, occ, occ_params = "true", "1", []
    # candidates first, then the exact count on them only (pushed into the scan, the count would run
    # on every row of the country)
    con.execute(f"CREATE OR REPLACE TEMP TABLE _cand AS SELECT country, id_int, row_n, text FROM interventions "
                f"WHERE {cond}{where}", params)
    k = int(d.get("min_occurrences") or 1)
    enough, enough_params = (f"{occ} >= {k}", occ_params) if terms and k > 1 else ("true", [])
    n = con.execute(f"SELECT count(*) FROM _cand WHERE {enough}", enough_params).fetchone()[0]
    con.execute(f"""INSERT OR IGNORE INTO lib.library_items
                    SELECT ?, country, id_int, row_n, md5(coalesce(text, '')), '', '[]', 'definition', ?
                    FROM _cand WHERE {enough}
                      AND id_int NOT IN (SELECT id_int FROM lib.library_excl WHERE library_id = ?)""",
                [lib_id, _now()] + enough_params + [lib_id])
    con.execute("DROP TABLE _cand")
    return n


def _upsert_part(con, lib_id: int, iso: str, edition: str | None, definition: dict | None) -> None:
    row = con.execute("SELECT definitions FROM lib.library_parts WHERE library_id = ? AND country = ?",
                      [lib_id, iso]).fetchone()
    defs = json.loads(row[0]) if row else []
    if definition is not None:
        defs.append(definition)
    if row:
        con.execute("UPDATE lib.library_parts SET definitions = ?, edition = ? WHERE library_id = ? AND country = ?",
                    [json.dumps(defs, ensure_ascii=False), edition, lib_id, iso])
    else:
        con.execute("INSERT INTO lib.library_parts VALUES (?, ?, ?, ?, ?)",
                    [lib_id, iso, edition, COUNTRIES[iso][2], json.dumps(defs, ensure_ascii=False)])


def _new_library(con, name: str, description: str, color: str) -> int:
    name = name.strip()
    if not name:
        raise ValueError("A library needs a name.")
    if con.execute("SELECT 1 FROM lib.libraries WHERE lower(name) = lower(?)", [name]).fetchone():
        raise FileExistsError(f"There is already a library called {name!r}: choose another name, or use "
                              f"extend=true to add to it.")
    now = _now()
    return con.execute("INSERT INTO lib.libraries (name, description, color, created_at, updated_at) "
                       "VALUES (?, ?, ?, ?, ?) RETURNING id", [name, description or "", color or "indigo", now, now]
                       ).fetchone()[0]


def _touch(con, lib_id: int) -> None:
    con.execute("UPDATE lib.libraries SET updated_at = ? WHERE id = ?", [_now(), lib_id])


def create(name: str, countries: list[str], terms: str | None = None, regex: bool = False,
           min_occurrences: int = 1, date_from: str | None = None, date_to: str | None = None,
           party: str | None = None, sex: str | None = None, id_dep: str | None = None,
           speech_only: bool = True, exclude_chair: bool = False, max_turn_words: int | None = None,
           event_dates: dict[str, str] | None = None, days_before: int = 0, days_after: int = 0,
           per_country: dict[str, dict] | None = None, label: str | None = None,
           description: str = "", color: str = "indigo", extend: bool = False) -> dict:
    """Create (or, with extend, enlarge) a library: one definition per country, built from the
    shared parameters, the per-country overrides and, if given, a window around each country's event."""
    isos = [normalize_iso(c) for c in countries or []]
    if not isos:
        raise ValueError("Say which countries the library takes (countries=[...]).")
    per = {normalize_iso(k): v for k, v in (per_country or {}).items()}
    events = {normalize_iso(k): v for k, v in (event_dates or {}).items()}
    for k in list(per) + list(events):
        if k not in isos:
            raise ValueError(f"{k} has per-country settings but is not in countries.")
    loaded = _loaded_editions()
    missing = [c for c in isos if c not in loaded]
    if missing:
        raise store.NoData(f"Not downloaded: {', '.join(missing)}. Use download_country first.")
    base = {"terms": terms, "regex": regex, "min_occurrences": min_occurrences, "date_from": date_from,
            "date_to": date_to, "party": party, "sex": sex, "id_dep": id_dep, "speech_only": speech_only,
            "exclude_chair": exclude_chair, "max_turn_words": max_turn_words}
    defs = {}
    for iso in isos:
        d = dict(base)
        for k, v in per.get(iso, {}).items():
            if k not in DEFINITION_KEYS:
                raise ValueError(f"per_country[{iso}]: unknown setting {k!r} (allowed: {', '.join(DEFINITION_KEYS)})")
            d[k] = v
        if iso in events:
            day = date.fromisoformat(_date(events[iso], start=True))
            d["date_from"] = (day - timedelta(days=int(days_before))).isoformat()
            d["date_to"] = (day + timedelta(days=int(days_after))).isoformat()
            d["event"] = {"date": day.isoformat(), "days_before": int(days_before), "days_after": int(days_after)}
        for k in ("date_from", "date_to"):
            if d.get(k):
                _date(d[k], start=k == "date_from")      # validate early
        if d.get("terms") and not d.get("regex"):
            parse_terms(d["terms"])
        if label:
            d["label"] = label
        d = {k: v for k, v in d.items() if v not in (None, False, "") or k == "speech_only"}
        d["created_at"] = _now().isoformat(timespec="seconds")
        defs[iso] = d
    whole = [i for i, d in defs.items() if not any(d.get(k) for k in ("terms", "date_from", "date_to", "party",
                                                                       "sex", "id_dep"))]
    if whole:
        raise ValueError(f"The definition for {', '.join(whole)} takes the whole chamber (no terms, dates, party, "
                         f"sex or deputy). Narrow it down: the analyses already work on the whole corpus.")
    matched = {}
    with store.library_connection() as con:
        con.execute("BEGIN TRANSACTION")
        try:
            row = con.execute("SELECT id FROM lib.libraries WHERE lower(name) = lower(?)", [name.strip()]).fetchone()
            if row and extend:
                lib_id = row[0]
            else:
                lib_id = _new_library(con, name, description, color)
            for iso, d in defs.items():
                matched[iso] = _insert_definition(con, lib_id, iso, d)
                _upsert_part(con, lib_id, iso, loaded[iso], d)
            _touch(con, lib_id)
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    out = describe(name)
    out["matched_by_definition"] = matched
    return out


def _ids_from(id_ints: list[str] | None, sql: str | None) -> list[str]:
    ids = list(id_ints or [])
    if sql:
        # user SQL runs on the sandboxed, read-only connection, never on the write one
        cols, rows, truncated = store.run_query(sql, max_rows=2_000_000, timeout_s=600)
        if "id_int" not in cols:
            raise ValueError("The query must return a column called id_int.")
        if truncated:
            raise ValueError("The query returns more than 2,000,000 rows: narrow it down.")
        k = cols.index("id_int")
        ids += [r[k] for r in rows]
    if not ids:
        raise ValueError("Give id_ints or a sql query that returns id_int.")
    return list(dict.fromkeys(str(i) for i in ids if i))


def add(name: str, id_ints: list[str] | None = None, sql: str | None = None) -> dict:
    """Add interventions by id (directly or from a query). Countries new to the library get a part."""
    lib = _get(name)
    ids = _ids_from(id_ints, sql)
    loaded = _loaded_editions()
    with store.library_connection() as con:
        found = con.execute("SELECT country, count(*) FROM interventions WHERE id_int IN (SELECT unnest(?::VARCHAR[])) "
                            "GROUP BY 1", [ids]).fetchall()
        n_found = sum(n for _, n in found)
        con.execute("BEGIN TRANSACTION")
        before = con.execute("SELECT count(*) FROM lib.library_items WHERE library_id = ?", [lib["id"]]).fetchone()[0]
        con.execute("""INSERT OR IGNORE INTO lib.library_items
                       SELECT ?, country, id_int, row_n, md5(coalesce(text, '')), '', '[]', 'manual', ?
                       FROM interventions WHERE id_int IN (SELECT unnest(?::VARCHAR[]))""", [lib["id"], _now(), ids])
        # an intervention added by hand is no longer excluded
        con.execute("DELETE FROM lib.library_excl WHERE library_id = ? AND id_int IN (SELECT unnest(?::VARCHAR[]))",
                    [lib["id"], ids])
        for iso, _ in found:
            if iso not in lib["parts"]:
                _upsert_part(con, lib["id"], iso, loaded.get(iso), {"manual": True,
                                                                     "created_at": _now().isoformat(timespec="seconds")})
        after = con.execute("SELECT count(*) FROM lib.library_items WHERE library_id = ?", [lib["id"]]).fetchone()[0]
        _touch(con, lib["id"])
        con.execute("COMMIT")
    return {"library": lib["name"], "requested": len(ids), "found": n_found, "not_found": len(ids) - n_found,
            "added": after - before, "items": after}


def remove(name: str, id_ints: list[str] | None = None, sql: str | None = None) -> dict:
    """Take interventions out. They are remembered as excluded, so rebuilding the library from its
    definitions does not bring them back."""
    lib = _get(name)
    ids = _ids_from(id_ints, sql)
    with store.library_connection() as con:
        con.execute("BEGIN TRANSACTION")
        con.execute("""INSERT OR IGNORE INTO lib.library_excl
                       SELECT library_id, country, id_int, fingerprint FROM lib.library_items
                       WHERE library_id = ? AND id_int IN (SELECT unnest(?::VARCHAR[]))""", [lib["id"], ids])
        n = con.execute("DELETE FROM lib.library_items WHERE library_id = ? AND id_int IN "
                        "(SELECT unnest(?::VARCHAR[]))", [lib["id"], ids]).fetchone()[0]
        left = con.execute("SELECT count(*) FROM lib.library_items WHERE library_id = ?", [lib["id"]]).fetchone()[0]
        _touch(con, lib["id"])
        con.execute("COMMIT")
    return {"library": lib["name"], "removed": n, "items": left}


def note(name: str, id_int: str, note_text: str | None = None, tags: list[str] | None = None) -> dict:
    lib = _get(name)
    sets, params = [], []
    if note_text is not None:
        sets.append("note = ?")
        params.append(note_text)
    if tags is not None:
        sets.append("tags = ?")
        params.append(json.dumps([str(t) for t in tags], ensure_ascii=False))
    if not sets:
        raise ValueError("Give a note, tags, or both.")
    with store.library_connection() as con:
        n = con.execute(f"UPDATE lib.library_items SET {', '.join(sets)} WHERE library_id = ? AND id_int = ?",
                        params + [lib["id"], id_int]).fetchone()[0]
        if not n:
            raise LookupError(f"{id_int} is not in library {lib['name']!r}.")
        _touch(con, lib["id"])
    return {"library": lib["name"], "id_int": id_int, "note": note_text, "tags": tags}


def combine(name: str, a: str, b: str, op: str, description: str = "", color: str = "indigo") -> dict:
    """A new library from two others: union, intersection or difference (in a, not in b)."""
    if op not in ("union", "intersection", "difference"):
        raise ValueError("op must be union, intersection or difference")
    la, lb = _get(a), _get(b)
    pick = {"union": "SELECT id_int FROM A UNION SELECT id_int FROM B",
            "intersection": "SELECT id_int FROM A INTERSECT SELECT id_int FROM B",
            "difference": "SELECT id_int FROM A EXCEPT SELECT id_int FROM B"}[op]
    with store.library_connection() as con:
        con.execute("BEGIN TRANSACTION")
        try:
            lib_id = _new_library(con, name, description, color)
            # notes and tags: those of a, else those of b
            con.execute(f"""INSERT INTO lib.library_items
                WITH A AS (SELECT * FROM lib.library_items WHERE library_id = ?),
                     B AS (SELECT * FROM lib.library_items WHERE library_id = ?),
                     K AS ({pick})
                SELECT ?, coalesce(A.country, B.country), K.id_int, coalesce(A.row_n, B.row_n),
                       coalesce(A.fingerprint, B.fingerprint),
                       CASE WHEN coalesce(A.note, '') <> '' THEN A.note ELSE coalesce(B.note, '') END,
                       CASE WHEN coalesce(A.tags, '[]') <> '[]' THEN A.tags ELSE coalesce(B.tags, '[]') END,
                       'combined', ?
                FROM K LEFT JOIN A USING (id_int) LEFT JOIN B USING (id_int)""",
                        [la["id"], lb["id"], lib_id, _now()])
            for iso in [r[0] for r in con.execute("SELECT DISTINCT country FROM lib.library_items WHERE library_id = ?",
                                                  [lib_id]).fetchall()]:
                ed = (la["parts"].get(iso) or lb["parts"].get(iso) or {}).get("edition")
                _upsert_part(con, lib_id, iso, ed, {"combined": op, "a": la["name"], "b": lb["name"],
                                                    "created_at": _now().isoformat(timespec="seconds")})
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    return describe(name)


def delete(name: str, confirm: bool = False) -> dict:
    lib = _get(name)
    if not confirm:
        n = store.run_query("SELECT count(*) FROM lib.library_items WHERE library_id = ?", [lib["id"]])[1][0][0]
        return {"library": lib["name"], "items": n, "deleted": False,
                "note": "Nothing deleted. Deleting cannot be undone (export it first if in doubt): call again "
                        "with confirm=true."}
    with store.library_connection() as con:
        con.execute("BEGIN TRANSACTION")
        for t in ("library_items", "library_excl", "library_parts"):
            con.execute(f"DELETE FROM lib.{t} WHERE library_id = ?", [lib["id"]])
        con.execute("DELETE FROM lib.libraries WHERE id = ?", [lib["id"]])
        con.execute("COMMIT")
    return {"library": lib["name"], "deleted": True}


def list_libraries() -> dict:
    cols, rows, _ = store.run_query("""
        SELECT l.name, l.description, l.updated_at, count(i.id_int) AS items,
               string_agg(DISTINCT i.country, ', ' ORDER BY i.country) AS countries
        FROM lib.libraries l LEFT JOIN lib.library_items i ON i.library_id = l.id
        GROUP BY ALL ORDER BY l.name""", max_rows=10_000)
    return {"libraries": [{k: store.jsonable(v) for k, v in zip(cols, r)} for r in rows],
            "file": str(store.LIBDB)}


# ── describing ────────────────────────────────────────────────────────────────

def describe(name: str) -> dict:
    """Per country: how much there is, how it is spread over time and speakers, what share is
    the chair or documents read into the record, and which edition it was built on."""
    lib = _get(name)
    loaded = _loaded_editions()
    rows = _q(f"""
        SELECT i.country, count(*) AS items, count(DISTINCT i.id_session) AS sessions,
               min(i.date) AS date_from, max(i.date) AS date_to,
               count(DISTINCT coalesce(i.id_dep, i.speaker_raw)) AS speakers,
               sum(i.n_words) AS words,
               round(100.0 * count(*) FILTER (WHERE i.id_dep IS NOT NULL) / count(*), 1) AS linked_pct,
               round(100.0 * count(*) FILTER (WHERE i.sex = 'F') / nullif(count(*) FILTER (WHERE i.sex IS NOT NULL), 0), 1)
                 AS women_pct_of_sexed,
               round(100.0 * coalesce(sum(i.n_words) FILTER (WHERE i.n_words > {LONG_TURN}), 0)
                 / nullif(sum(i.n_words), 0), 1) AS long_turn_words_pct,
               round(100.0 * coalesce(sum(i.n_words) FILTER (WHERE regexp_matches(coalesce(i.speaker_raw, ''),
                 '{CHAIR_RX}') AND NOT regexp_matches(coalesce(i.speaker_raw, ''), '{NOT_CHAIR_RX}')), 0)
                 / nullif(sum(i.n_words), 0), 1) AS chair_words_pct,
               count(*) FILTER (WHERE i.dm_speech = 0) AS not_speech,
               count(*) FILTER (WHERE i.date IS NULL) AS undated,
               count(*) FILTER (WHERE l.note <> '' OR l.tags <> '[]') AS annotated
        FROM lib.library_items l JOIN interventions i ON i.id_int = l.id_int
        WHERE l.library_id = ? GROUP BY 1 ORDER BY 1""", [lib["id"]])
    years = defaultdict(dict)
    for r in _q("""SELECT i.country, year(i.date) AS y, count(*) AS n FROM lib.library_items l
                   JOIN interventions i ON i.id_int = l.id_int WHERE l.library_id = ? AND i.date IS NOT NULL
                   GROUP BY ALL ORDER BY ALL""", [lib["id"]]):
        years[r["country"]][r["y"]] = r["n"]
    total = _q("SELECT country, count(*) AS n FROM lib.library_items WHERE library_id = ? GROUP BY 1", [lib["id"]])
    in_lib = {r["country"]: r["n"] for r in total}
    parts = {}
    for r in rows:
        c = r.pop("country")
        r["date_from"], r["date_to"] = store.jsonable(r["date_from"]), store.jsonable(r["date_to"])
        p = lib["parts"].get(c, {})
        r["thin_years"] = [y for y, n in years[c].items() if n < THIN_YEAR]
        r["items_per_year"] = years[c]
        r["edition"] = p.get("edition")
        r["edition_loaded"] = loaded.get(c)
        r["definitions"] = p.get("definitions", [])
        r["not_found_in_data"] = in_lib.get(c, 0) - r["items"]
        parts[c] = r
    for c, p in lib["parts"].items():      # parts whose items are all gone (other edition, removed)
        if c not in parts:
            parts[c] = {"items": 0, "edition": p["edition"], "edition_loaded": loaded.get(c),
                        "definitions": p["definitions"], "not_found_in_data": in_lib.get(c, 0)}
    return {"library": lib["name"], "description": lib["description"], "color": lib["color"],
            "created_at": store.jsonable(lib["created_at"]), "updated_at": store.jsonable(lib["updated_at"]),
            "items": sum(in_lib.values()), "countries": sorted(parts), "parts": parts,
            "notes": _describe_notes(parts), "datasets": {c: {"doi": COUNTRIES[c][2], "version": p.get("edition")}
                                                         for c, p in sorted(parts.items())},
            "file": str(store.LIBDB)}


def _describe_notes(parts: dict) -> list[str]:
    notes = []
    stale = [c for c, p in parts.items() if p.get("edition") != p.get("edition_loaded")]
    if stale:
        notes.append(f"Built on another edition of the data: {', '.join(stale)}. Run library_rebuild before "
                     f"analysing or exporting it.")
    lost = {c: p["not_found_in_data"] for c, p in parts.items() if p.get("not_found_in_data")}
    if lost:
        notes.append("Items no longer found in the loaded data: " + ", ".join(f"{c} {n}" for c, n in lost.items()))
    full = {c: p for c, p in parts.items() if p.get("items")}
    if len(full) > 1:
        sizes = sorted((p["items"], c) for c, p in full.items())
        if sizes[-1][0] >= 10 * sizes[0][0]:
            notes.append(f"Parts differ in size by more than ten times ({sizes[0][1]} {sizes[0][0]:,}, "
                         f"{sizes[-1][1]} {sizes[-1][0]:,}): compare rates within each chamber, not pooled counts.")
        windows = {c: sorted({(d.get("date_from"), d.get("date_to")) for d in p.get("definitions", [])
                              if "date_from" in d or "date_to" in d}) for c, p in full.items()}
        if len({tuple(w) for w in windows.values()}) > 1:
            aligned = any("event" in d for p in full.values() for d in p.get("definitions", []))
            notes.append("The parts were defined on different time windows" +
                         (" (aligned on each country's event)" if aligned else "") +
                         ": part of a difference between countries can be time. Observed spans: " +
                         ", ".join(f"{c} {p['date_from']}…{p['date_to']}" for c, p in full.items()) + ".")
        if len({c in PORTUGUESE for c in full}) > 1:
            notes.append("Spanish- and Portuguese-language chambers: the terms must be given in both languages "
                         "(check each part's definition), and word lists compare languages as much as debates.")
        notes.append("Comparing countries: the analyses report each country separately by default "
                     "(split_by_country in ngram_viewer). The same words do not have to mean the same thing in "
                     "two chambers: read examples from each part (kwic with library=…) before comparing.")
    heavy = [f"{c} {p['long_turn_words_pct']}%" for c, p in full.items() if (p.get("long_turn_words_pct") or 0) > 20]
    if heavy:
        notes.append(f"Turns over {LONG_TURN:,} words (mostly documents read into the record) hold a large share of "
                     f"the words: {', '.join(heavy)}. Use max_turn_words={LONG_TURN} in word-based measures.")
    chair = [f"{c} {p['chair_words_pct']}%" for c, p in full.items() if (p.get("chair_words_pct") or 0) > 25]
    if chair:
        notes.append(f"The chair speaks a large share of the words: {', '.join(chair)}. Use exclude_chair=true "
                     f"when comparing groups.")
    thin = {c: p["thin_years"] for c, p in full.items() if p.get("thin_years")}
    if thin:
        notes.append(f"Years with fewer than {THIN_YEAR} interventions (anecdotal if read as a trend): " +
                     "; ".join(f"{c} {', '.join(map(str, ys[:12]))}{'…' if len(ys) > 12 else ''}"
                               for c, ys in thin.items()))
    return notes


# ── rebuilding after a new edition ────────────────────────────────────────────

def rebuild(name: str) -> dict:
    """Rebuild each part on the edition now loaded: definitions are run again; items added by hand,
    combined or imported are found again by the md5 of their text; notes and tags follow their text;
    exclusions are kept. Reports what came in and what was lost."""
    lib = _get(name)
    loaded = _loaded_editions()
    missing = [c for c in lib["parts"] if c not in loaded]
    if missing:
        raise store.NoData(f"Not downloaded: {', '.join(missing)}.")
    report = {}
    with store.library_connection() as con:
        con.execute("BEGIN TRANSACTION")
        try:
            old = con.execute("SELECT country, id_int, fingerprint, note, tags, origin FROM lib.library_items "
                              "WHERE library_id = ?", [lib["id"]]).fetchall()
            excl = con.execute("SELECT country, fingerprint FROM lib.library_excl WHERE library_id = ?",
                               [lib["id"]]).fetchall()
            con.execute("DELETE FROM lib.library_items WHERE library_id = ?", [lib["id"]])
            con.execute("DELETE FROM lib.library_excl WHERE library_id = ?", [lib["id"]])
            # exclusions, found again by fingerprint
            con.execute("""INSERT OR IGNORE INTO lib.library_excl
                           SELECT ?, i.country, i.id_int, e.fp FROM interventions i
                           JOIN (SELECT unnest(?::VARCHAR[]) AS c, unnest(?::VARCHAR[]) AS fp) e
                             ON i.country = e.c AND md5(coalesce(i.text, '')) = e.fp""",
                        [lib["id"], [c for c, _ in excl], [f for _, f in excl]])
            for iso, part in lib["parts"].items():
                for d in part["definitions"]:
                    if any(k in d for k in ("terms", "date_from", "date_to", "party", "sex", "id_dep")) \
                            and "combined" not in d and "manual" not in d and "imported" not in d:
                        _insert_definition(con, lib["id"], iso, d)
            keep = [r for r in old if r[5] != "definition"]
            if keep:
                con.execute("""INSERT OR IGNORE INTO lib.library_items
                               SELECT ?, i.country, i.id_int, i.row_n, k.fp, '', '[]', k.origin, ?
                               FROM interventions i
                               JOIN (SELECT unnest(?::VARCHAR[]) AS c, unnest(?::VARCHAR[]) AS fp,
                                            unnest(?::VARCHAR[]) AS origin) k
                                 ON i.country = k.c AND md5(coalesce(i.text, '')) = k.fp""",
                            [lib["id"], _now(), [r[0] for r in keep], [r[2] for r in keep], [r[5] for r in keep]])
            notes = [r for r in old if r[3] or r[4] != "[]"]
            if notes:
                con.execute("""UPDATE lib.library_items AS t SET note = n.note, tags = n.tags
                               FROM (SELECT unnest(?::VARCHAR[]) AS fp, unnest(?::VARCHAR[]) AS note,
                                            unnest(?::VARCHAR[]) AS tags) n
                               WHERE t.library_id = ? AND t.fingerprint = n.fp""",
                            [[r[2] for r in notes], [r[3] for r in notes], [r[4] for r in notes], lib["id"]])
            new = con.execute("SELECT country, fingerprint FROM lib.library_items WHERE library_id = ?",
                              [lib["id"]]).fetchall()
            for iso in lib["parts"]:
                before = {r[2] for r in old if r[0] == iso}
                after = {f for c, f in new if c == iso}
                report[iso] = {"edition_before": lib["parts"][iso]["edition"], "edition_now": loaded[iso],
                               "items_before": len(before), "items_now": len(after),
                               "kept": len(before & after), "came_in": len(after - before), "lost": len(before - after),
                               "notes_lost": sum(1 for r in notes if r[0] == iso and r[2] not in after)}
                con.execute("UPDATE lib.library_parts SET edition = ? WHERE library_id = ? AND country = ?",
                            [loaded[iso], lib["id"], iso])
            _touch(con, lib["id"])
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    return {"library": lib["name"], "by_country": report,
            "note": "Items are matched across editions by the md5 of their text: an intervention whose text was "
                    "corrected in the new edition counts as lost (and its definition may bring it back in)."}


# ── the explorer's format ─────────────────────────────────────────────────────

def slug(s: str) -> str:
    """The explorer's file-name slug: no accents, [^a-zA-Z0-9]+ → _, 60 characters, lower case."""
    t = "".join(ch for ch in unicodedata.normalize("NFD", s or "") if unicodedata.category(ch) != "Mn")
    t = re.sub(r"[^a-zA-Z0-9]+", "_", t).strip("_")[:60].lower()
    return t + "_" if re.fullmatch(r"con|prn|aux|nul|com[1-9]|lpt[1-9]", t) else t


def _short_citation(rec: dict) -> str:
    """cita_corta of the explorer: «<first author> et al. (<year>), <title before ':'>, doi:…»."""
    authors = [a["nombre"].strip() for a in rec.get("autores") or [] if a.get("nombre")]
    first = authors[0].split(",")[0] if authors else rec.get("editor") or ""
    who = f"{first} et al." if len(authors) > 2 else (" y ".join(a.split(",")[0] for a in authors) or first)
    year = rec.get("anio") if rec.get("anio") is not None else "s. f."
    doi = f"doi:{rec['doi']}" if rec.get("doi") else rec.get("url", "")
    return ", ".join(x for x in [f"{who} ({year})", (rec.get("titulo") or "").split(":")[0], doi] if x)


def _source_block(rec: dict) -> dict:
    """The `fuente` block of a .2replib (the explorer's metadatos(), in its key order)."""
    pairs = [("declarada", True), ("cita", rec["cita"]), ("cita_corta", _short_citation(rec)),
             ("titulo", rec.get("titulo")), ("autores", rec.get("autores") or []), ("anio", rec.get("anio")),
             ("editor", rec.get("editor")), ("doi", rec.get("doi")), ("url", rec.get("url")),
             ("version", rec.get("version_cita")), ("licencia", rec.get("licencia")),
             ("licencia_url", rec.get("licencia_url"))]
    return {k: v for k, v in pairs if v not in (None, "", [])}


# The explorer's display conventions (worker/04_worker__transformar.js, 05_worker__construir.js): values are
# stripped; an empty name is «Sin identificar»; a turn without a speaker is the session summary (order 0)
# or «COMENTARIOS». Written the same way here, a library reads the same in both tools.
SIN_IDENTIFICAR = "Sin identificar"


def _explorer_speaker(speaker_raw, order) -> str:
    v = (speaker_raw or "").strip()
    if v:
        return v
    return "SUMARIO" if order in (0, None) else "COMENTARIOS"


def _explorer_name(speaker_name) -> str:
    return (speaker_name or "").strip() or SIN_IDENTIFICAR


def _write(path: Path, data: bytes, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists; pass overwrite=true to replace it")
    path.write_bytes(data)


def export(name: str, folder: str, table_format: str | None = None, overwrite: bool = False) -> dict:
    """One .2replib per country (the explorer imports each with that country's CSV loaded), an
    index that puts the comparison back together, and optionally the items with their metadata."""
    lib_id, isos = resolve(name)           # refuses a library built on another edition
    lib = _get(name)
    out = Path(folder).expanduser()
    if not out.is_absolute():
        out = Path.cwd() / out
    out.mkdir(parents=True, exist_ok=True)
    base = slug(lib["name"]) or "biblioteca"
    stamp = datetime.now().isoformat(timespec="seconds")
    files, parts, warnings = [], [], []
    for iso in isos:
        edition = lib["parts"][iso]["edition"]
        rec = store.source_record(iso, edition)
        if edition is None:
            warnings.append(f"{iso} was imported from a local folder with no version: the explorer will number the "
                            f"rows of the file it loads; use the same file.")
        rows = _q("""SELECT l.row_n, l.note, l.tags, i.date, i.speaker_name, i.speaker_raw, i.intervention_order
                     FROM lib.library_items l JOIN interventions i ON i.id_int = l.id_int
                     WHERE l.library_id = ? AND l.country = ? ORDER BY l.row_n""", [lib_id, iso])
        if not rows:
            continue
        cols = {"fuente_cita": _short_citation(rec), "fuente_doi": rec.get("url") or ""}
        country = COUNTRIES[iso][1]
        payload = {
            "format": FORMAT, "exported_at": stamp, "corpus": f"Diarios_{iso}", "fuente": _source_block(rec),
            "collection": {
                "name": f"{lib['name']} · {country} ({iso})",
                "description": ((lib["description"] + "\n\n") if lib["description"] else "") +
                               f"{country} ({iso}): importar con {iso}_interventions.csv, {rec.get('version_cita') or ''} "
                               f"(doi:{COUNTRIES[iso][2]}), cargado. Parte de la biblioteca «{lib['name']}» "
                               f"(parlaibero-mcp {__version__}).",
                "color": lib["color"]},
            "items": [{"speech_id": r["row_n"], "note": r["note"] or "", "tags": json.loads(r["tags"] or "[]"),
                       "date": store.jsonable(r["date"]), "rep_name": _explorer_name(r["speaker_name"]),
                       "speaker": _explorer_speaker(r["speaker_raw"], r["intervention_order"]), **cols}
                      for r in rows],
        }
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        path = out / f"{base}_{iso}.2replib"
        _write(path, data, overwrite)
        files.append(str(path))
        parts.append({"country": iso, "file": path.name, "items": len(rows), "edition": edition,
                      "doi": COUNTRIES[iso][2], "version_cita": rec.get("version_cita"),
                      "definitions": lib["parts"][iso]["definitions"], "sha256": hashlib.sha256(data).hexdigest()})
    index = {"format": INDEX_FORMAT, "exported_at": stamp, "exported_by": f"parlaibero-mcp {__version__}",
             "name": lib["name"], "description": lib["description"], "color": lib["color"], "time": "calendar",
             "parts": parts,
             "how_to_use": "Each .2replib is one country's part, for the explorer (Diarios Explorer): load that "
                           "country's CSV, then 'Importar .2replib…'. The explorer does not check which country a "
                           "file belongs to: import each file only with its own country's CSV loaded. "
                           "parlaibero-mcp library_import reads this index and rebuilds the whole library."}
    ipath = out / f"{base}.parlaibero-biblioteca.json"
    _write(ipath, json.dumps(index, ensure_ascii=False, indent=2).encode("utf-8"), overwrite)
    result = {"library": lib["name"], "folder": str(out), "index": str(ipath), "files": files,
              "items": {p["country"]: p["items"] for p in parts}, "warnings": warnings,
              "note": "Import each .2replib in the explorer ONLY with its own country's CSV loaded: the explorer "
                      "does not check, and a file imported on another country's corpus points to unrelated "
                      "interventions."}
    if table_format:
        result["table"] = _export_table(lib_id, out / f"{base}.{table_format}", table_format, overwrite)
    return result


def _export_table(lib_id: int, path: Path, fmt: str, overwrite: bool) -> dict:
    if fmt not in ("csv", "parquet"):
        raise ValueError("table_format must be csv or parquet")
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists; pass overwrite=true to replace it")
    body = (f"SELECT i.*, l.note AS library_note, l.tags AS library_tags, l.origin AS library_origin "
            f"FROM lib.library_items l JOIN interventions i ON i.id_int = l.id_int "
            f"WHERE l.library_id = {int(lib_id)} ORDER BY i.country, i.row_n")
    target = "'" + str(path).replace("'", "''") + "'"
    opts = "FORMAT CSV, HEADER" if fmt == "csv" else "FORMAT PARQUET"
    with store.export_connection(path.parent) as con:
        con.execute(f"COPY ({body}) TO {target} ({opts})")
        n = con.execute(f"SELECT count(*) FROM ({body})").fetchone()[0]
    return {"path": str(path), "format": fmt, "rows": n}


# ── importing ─────────────────────────────────────────────────────────────────

def _country_of(payload: dict) -> str:
    m = re.fullmatch(r"Diarios_([A-Z]{2})", str(payload.get("corpus") or ""))
    if m and m.group(1) in COUNTRIES:
        return m.group(1)
    doi = str((payload.get("fuente") or {}).get("doi") or "")
    for iso, (_, _, d) in COUNTRIES.items():
        if d.lower() == doi.lower():
            return iso
    raise ValueError(f"Cannot tell which country this library belongs to (corpus {payload.get('corpus')!r}).")


def _read_bundle(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if payload.get("format") != FORMAT:
        raise ValueError(f"{path.name}: not a {FORMAT} library (format {payload.get('format')!r}).")
    if not isinstance(payload.get("items"), list):
        raise ValueError(f"{path.name}: «items» must be a list.")
    for k, it in enumerate(payload["items"], 1):
        sid = it.get("speech_id") if isinstance(it, dict) else None
        if isinstance(sid, bool) or not str(sid).strip().isdigit():
            raise ValueError(f"{path.name}: item {k} has no valid speech_id.")
    return payload


def import_files(paths: list[str], name: str | None = None, force: bool = False) -> dict:
    """Read .2replib files (one per country) or a library index, check every item against the
    loaded data (row number → intervention, then date and speaker), and create one library."""
    files: list[tuple[Path, str | None]] = []       # (file, expected sha256)
    index = None
    for p in paths:
        p = Path(p).expanduser()
        if p.is_dir():
            idx = sorted(p.glob("*.parlaibero-biblioteca.json"))
            if len(idx) == 1:
                p = idx[0]
            else:
                files += [(f, None) for f in sorted(p.glob("*.2replib"))]
                continue
        if p.name.endswith(".parlaibero-biblioteca.json"):
            index = json.loads(p.read_text(encoding="utf-8"))
            if index.get("format") != INDEX_FORMAT:
                raise ValueError(f"{p.name}: not a {INDEX_FORMAT} index.")
            files += [(p.parent / part["file"], part.get("sha256")) for part in index["parts"]]
        else:
            files.append((p, None))
    if not files:
        raise FileNotFoundError("No .2replib files found.")
    loaded = _loaded_editions()
    bundles = {}
    problems = []
    for path, sha in files:
        if sha and hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            problems.append(f"{path.name}: changed since the index was written (sha256 differs).")
        payload = _read_bundle(path)
        iso = _country_of(payload)
        if iso in bundles:
            raise ValueError(f"Two files for {iso}: {bundles[iso][0].name} and {path.name}.")
        if iso not in loaded:
            raise store.NoData(f"{path.name} belongs to {iso}, which is not downloaded. Use download_country first.")
        v = str((payload.get("fuente") or {}).get("version") or "")
        if v and loaded[iso] and v.lstrip("Vv").split(".")[0] != str(loaded[iso]).split(".")[0]:
            msg = (f"{path.name} was written on {iso} {v}, and {iso} {loaded[iso]} is loaded: its row numbers point "
                   f"to other interventions.")
            if not force:
                raise RuntimeError(msg + " Load the same version, or pass force=true to import the items whose date "
                                         "and speaker still match.")
            problems.append(msg)
        bundles[iso] = (path, payload)
    if problems and not force:
        raise RuntimeError(" ".join(problems) + " Pass force=true to import anyway.")
    first = next(iter(bundles.values()))[1]
    lib_name = name or (index or {}).get("name") or re.sub(r"( · .*\([A-Z]{2}\))?( \(importada\))*$", "",
                                                            first["collection"].get("name") or "Biblioteca importada")
    description = (index or {}).get("description") if index else first["collection"].get("description", "")
    color = (index or {}).get("color") or first["collection"].get("color") or "indigo"
    report = {}
    with store.library_connection() as con:
        con.execute("BEGIN TRANSACTION")
        try:
            if not name:            # like the explorer: an imported copy never overwrites, it is "(importada)"
                taken = {r[0].lower() for r in con.execute("SELECT name FROM lib.libraries").fetchall()}
                base, k = lib_name, 1
                while lib_name.lower() in taken:
                    lib_name = f"{base} (importada)" + (f" {k}" if k > 1 else "")
                    k += 1
            lib_id = _new_library(con, lib_name, description or "", color)
            for iso, (path, payload) in bundles.items():
                items = payload["items"]
                rows = {r[0]: r for r in con.execute(
                    "SELECT row_n, id_int, date, speaker_raw, intervention_order FROM interventions "
                    "WHERE country = ? AND row_n IN (SELECT unnest(?::BIGINT[]))",
                    [iso, [int(str(it["speech_id"]).strip()) for it in items]]).fetchall()}
                ok, mismatched, missing = [], [], []
                for it in items:
                    sid = int(str(it["speech_id"]).strip())
                    r = rows.get(sid)
                    if r is None:
                        missing.append(sid)
                        continue
                    bad = []
                    if it.get("date") not in (None, "") and str(it["date"]) != store.jsonable(r[2]):
                        bad.append(f"date {it['date']} ≠ {store.jsonable(r[2])}")
                    if it.get("speaker") not in (None, "") and it["speaker"] != _explorer_speaker(r[3], r[4]):
                        bad.append(f"speaker {it['speaker']!r} ≠ {_explorer_speaker(r[3], r[4])!r}")
                    if bad:         # never imported: the row is not the intervention the file meant
                        mismatched.append({"speech_id": sid, "id_int": r[1], "differences": bad})
                        continue
                    tags = it.get("tags") if isinstance(it.get("tags"), list) else []
                    ok.append((r[1], it.get("note") if isinstance(it.get("note"), str) else "",
                               json.dumps([t for t in tags if isinstance(t, str)], ensure_ascii=False)))
                if ok:
                    con.execute("""INSERT OR IGNORE INTO lib.library_items
                                   SELECT ?, i.country, i.id_int, i.row_n, md5(coalesce(i.text, '')), k.note, k.tags,
                                          'imported', ?
                                   FROM interventions i JOIN (SELECT unnest(?::VARCHAR[]) AS id_int,
                                        unnest(?::VARCHAR[]) AS note, unnest(?::VARCHAR[]) AS tags) k USING (id_int)""",
                                [lib_id, _now(), [o[0] for o in ok], [o[1] for o in ok], [o[2] for o in ok]])
                part_def = {"imported": path.name, "created_at": _now().isoformat(timespec="seconds")}
                if index:
                    src = next((p for p in index["parts"] if p["country"] == iso), {})
                    part_def["definitions_in_index"] = src.get("definitions", [])
                _upsert_part(con, lib_id, iso, loaded[iso], part_def)
                report[iso] = {"file": path.name, "items_in_file": len(items), "imported": len(ok),
                               "mismatched": len(mismatched), "not_in_data": len(missing),
                               "mismatch_examples": mismatched[:10], "missing_examples": missing[:10]}
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    result = {"library": lib_name, "by_country": report, "problems": problems}
    if any(r["mismatched"] or r["not_in_data"] for r in report.values()):
        result["note"] = ("Some items did not match the loaded data (mismatched: the row exists but its date or "
                          "speaker differ; not_in_data: no such row). They were left out: most likely the file "
                          "was written on another version of the data.")
    return result
