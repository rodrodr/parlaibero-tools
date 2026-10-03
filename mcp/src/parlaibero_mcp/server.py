"""MCP server exposing the ParlaIbero corpora (Harvard Dataverse) to AI agents."""
import functools
import inspect
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, Any, Literal

import anyio
import anyio.from_thread
from pydantic import Field

try:  # mcp >= 2
    from mcp.server.mcpserver import Context, MCPServer as _Server
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import Context, FastMCP as _Server
    from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import __version__, dataverse, store
from .catalog import COLLECTION_URL, COUNTRIES, DOCUMENTS, normalize_iso

INSTRUCTIONS = """\
ParlaIbero: plenary speeches of the lower or single chambers of 16 countries (Argentina, Brazil,
Chile, Colombia, Costa Rica, Dominican Republic, Ecuador, Spain, Guatemala, Mexico, Panama, Peru,
Portugal, Paraguay, El Salvador, Uruguay), one row per intervention, linked to a register of
deputies. One dataset and one DOI per country in Harvard Dataverse (CC BY 4.0).

How to work with it:
1. `list_countries` shows what exists and what is already downloaded. Data must be downloaded
   once per country (`download_country`); big countries take 0.5-1.5 GB and a few minutes.
2. `describe_data` gives the table schema. Aggregate with `query_sql` (DuckDB SQL, read-only);
   find passages with `search_text`; read them with `get_intervention` / `get_session`;
   compare word use across years, parties or sex with `term_frequency`.
3. Rows with `dm_speech = 0` are not speech (cover page, summaries, vote tallies, reproduced
   documents; `intervention_order = 0` is the session's Prolegomena). Filter `dm_speech = 1`
   to study what was said.
4. `sex`, `party` and `district` come from the deputy register and are empty when the speaker
   could not be linked (`id_dep` empty: ministers, clerks, collective or anonymous voices).
   Coverage, linkage rates and caveats differ by country: read `get_documentation(country,
   'known_limitations')` and `'corpus_info'` before drawing comparative conclusions.
5. `id_session` / `id_int` are stable within a published version, not across versions: always
   report the dataset version. Cite each country's dataset with its DOI (`how_to_cite`).
"""

logging.getLogger("httpx").setLevel(logging.WARNING)

_server = _Server(name="parlaibero", instructions=INSTRUCTIONS)


class _Tools:
    """Register tools so that any failure reaches the agent as a readable ToolError
    (mcp 2.x otherwise reports only "Error executing tool")."""

    def tool(self, **kw):
        def deco(fn):
            if inspect.iscoroutinefunction(fn):
                @functools.wraps(fn)
                async def wrapped(*a, **k):
                    try:
                        return await fn(*a, **k)
                    except ToolError:
                        raise
                    except Exception as e:
                        raise ToolError(f"{type(e).__name__}: {e}") from e
            else:
                @functools.wraps(fn)
                def wrapped(*a, **k):
                    try:
                        return fn(*a, **k)
                    except ToolError:
                        raise
                    except Exception as e:
                        raise ToolError(f"{type(e).__name__}: {e}") from e
            _server.tool(**kw)(wrapped)
            return fn
        return deco

    def resource(self, *a, **kw):
        return _server.resource(*a, **kw)


mcp = _Tools()

READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
REMOTE_READ = ToolAnnotations(readOnlyHint=True, openWorldHint=True)

Country = Annotated[str, Field(description="ISO2 code (ES, MX, BR…) or country name")]
Countries = Annotated[list[str] | None, Field(
    default=None, description="ISO2 codes to restrict to; omit for every downloaded country")]


def _countries_clause(countries: list[str] | None, params: list) -> str:
    if not countries:
        return ""
    isos = [normalize_iso(c) for c in countries]
    params.extend(isos)
    return f" AND country IN ({', '.join('?' * len(isos))})"


def _filters(countries, date_from, date_to, party, sex, id_dep, speech_only, params) -> str:
    where = _countries_clause(countries, params)
    if date_from:
        where += " AND date >= CAST(? AS DATE)"
        params.append(date_from)
    if date_to:
        where += " AND date <= CAST(? AS DATE)"
        params.append(date_to)
    if party:
        where += " AND party ILIKE ?"
        params.append(party)
    if sex:
        where += " AND sex = ?"
        params.append(sex.upper()[:1])
    if id_dep:
        where += " AND id_dep = ?"
        params.append(id_dep)
    if speech_only:
        where += " AND dm_speech = 1"
    return where


def _rows(cols: list[str], rows: list[tuple], max_cell: int | None = None) -> list[dict]:
    out = []
    for r in rows:
        d = {}
        for c, v in zip(cols, r):
            v = store.jsonable(v)
            if max_cell and isinstance(v, str) and len(v) > max_cell:
                v = v[:max_cell] + f"… [{len(v) - max_cell} more chars]"
            d[c] = v
        out.append(d)
    return out


_FOLD = {"a": "aáàâãä", "e": "eéèêë", "i": "iíìîï", "o": "oóòôõö", "u": "uúùûü",
         "c": "cç", "n": "nñ"}
_FOLD_REV = {ch: base for base, chars in _FOLD.items() for ch in chars}


def _search_regex(pattern: str, regex: bool, whole_word: bool = False) -> str:
    """RE2 pattern for DuckDB. Plain text becomes a case- and accent-tolerant literal
    ('nacion' → 'n[aáàâãä]c[iíìîï][oóòôõö]n'), which RE2 matches far faster than folding the
    text itself."""
    if not pattern:
        raise ValueError("Empty search pattern")
    if regex:
        return pattern if pattern.startswith("(?") else "(?i)" + pattern
    out = []
    for ch in pattern.lower():
        base = _FOLD_REV.get(ch)
        if base:
            out.append(f"[{_FOLD[base]}]")
        elif ch.isalnum():
            out.append(ch)
        elif ch.isspace():
            out.append(r"\s+")
        elif ch.isascii():
            out.append("\\" + ch)  # ASCII punctuation: escaped; RE2 rejects escaping anything else
        else:
            out.append(ch)
    body = "".join(out)
    if whole_word:
        body = r"(?:^|[^\pL\pN])" + body + r"(?:$|[^\pL\pN])"
    return "(?i)" + body


def _snippet(text: str, rx: str, width: int = 220) -> str:
    if not text:
        return ""
    try:
        m = re.search(rx.replace("(?i)", "", 1).replace(r"\pL", "\\w").replace(r"\pN", "\\d"),
                      text, re.IGNORECASE)
    except re.error:
        m = None
    if m is None:
        return text[: 2 * width] + ("…" if len(text) > 2 * width else "")
    a, b = max(0, m.start() - width), min(len(text), m.end() + width)
    return ("…" if a else "") + text[a:b] + ("…" if b < len(text) else "")


# ── Catalogue and documentation ───────────────────────────────────────────────

@mcp.tool(annotations=REMOTE_READ)
def list_countries() -> dict:
    """List the 16 ParlaIbero datasets: DOI, published version, size, and whether each one is
    already downloaded locally (with rows, sessions and date range)."""
    local = store.loaded()

    def one(iso: str) -> dict:
        en, name, doi = COUNTRIES[iso]
        item: dict[str, Any] = {"iso": iso, "country": en, "local_name": name, "doi": doi,
                                "url": f"https://doi.org/{doi}"}
        try:
            s = dataverse.summary(doi)
            item.update(title=s["title"], published_version=s["version"],
                        download_mb=round(sum(f["size"] or 0 for f in s["files"]) / 2**20))
        except Exception as e:  # offline: still report what is local
            item["remote_error"] = str(e)
        item["downloaded"] = local.get(iso)
        return item

    with ThreadPoolExecutor(max_workers=8) as ex:
        items = list(ex.map(one, COUNTRIES))
    return {"collection": COLLECTION_URL, "countries": items,
            "data_home": str(store.HOME)}


@mcp.tool(annotations=REMOTE_READ)
def get_documentation(
    country: Country,
    document: Annotated[Literal[tuple(DOCUMENTS)], Field(  # type: ignore[valid-type]
        description="readme (overview, sources, coverage) · data_dictionary (columns) · "
                    "known_limitations (caveats) · process_report (how it was built) · "
                    "corpus_info (machine-readable facts, linkage rates) · match_methods · "
                    "dataset_jsonld (schema.org metadata)")] = "readme",
    language: Annotated[Literal["en", "es", "pt"], Field(
        description="Language of the markdown documents")] = "en",
) -> str:
    """Return a documentation file deposited with a country's dataset. Works before the data
    are downloaded (small files are fetched from Dataverse)."""
    return store.read_document(country, document, language)


@mcp.tool(annotations=REMOTE_READ)
def how_to_cite(country: Country) -> dict:
    """Formatted citation (latest published version) and DOI of a country's dataset."""
    iso = normalize_iso(country)
    doi = COUNTRIES[iso][2]
    return {"country": iso, "doi": doi, "citation": dataverse.citation(doi),
            "license": "CC BY 4.0",
            "note": "Cite each country's dataset you use, with its version: row identifiers "
                    "are only stable within a published version."}


@mcp.tool(annotations=READ)
def describe_data() -> dict:
    """Schema of the local DuckDB tables, the countries loaded, and example queries."""
    return {
        "tables": {
            "interventions": "One row per intervention. Columns: country (ISO2), id_session, id_int, "
                             "legislature, legislative_session, session_number, date (DATE), "
                             "session_type (ordinaria|extraordinaria|solemne|instalación|otros), "
                             "intervention_order (0 = Prolegomena), speaker_raw (as printed), "
                             "id_dep (deputy id, empty if not linked), speaker_name, sex (M|F), "
                             "party, district, dm_speech (1 = speech, 0 = not speech), text, "
                             "n_words (whitespace tokens, computed on import).",
            "deputies": "Deputy registers, core columns common to all countries: country, id_dep, "
                        "speaker_name, first_name, last_name, sex, sex_source, party, "
                        "parliamentary_group, district, legislature, start_date, end_date, notes. "
                        "id_dep may repeat across legislatures (one row per term).",
            "deputies_{iso}": "Full register of one country (e.g. deputies_es), with its own extra columns.",
            "datasets": "One row per loaded country: doi, version, source, n_rows, date range.",
        },
        "loaded": store.loaded(),
        "examples": [
            "SELECT country, year(date) AS y, sum(n_words) AS words FROM interventions "
            "WHERE dm_speech = 1 GROUP BY ALL ORDER BY ALL",
            "SELECT country, sex, round(100.0 * sum(n_words) / sum(sum(n_words)) OVER (PARTITION BY "
            "country), 1) AS pct_words FROM interventions WHERE dm_speech = 1 AND sex IN ('M','F') "
            "GROUP BY country, sex ORDER BY country, sex",
            "SELECT party, count(*) FROM interventions WHERE country = 'ES' AND dm_speech = 1 "
            "AND date BETWEEN '2020-01-01' AND '2020-12-31' GROUP BY 1 ORDER BY 2 DESC",
        ],
        "tips": "Never SELECT text without LIMIT: the corpus holds millions of rows. Use "
                "regexp_matches(text, '…', 'i') or contains(lower(text), '…') to filter on text.",
    }


# ── Getting the data ──────────────────────────────────────────────────────────

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                      idempotentHint=True, openWorldHint=True))
async def download_country(
    ctx: Context,
    country: Country,
    force: Annotated[bool, Field(description="Re-download even if the local copy is current")] = False,
) -> dict:
    """Download a country's dataset from Harvard Dataverse (MD5-verified) and load it into the
    local database. Skips files already current. Large countries (BR, MX, ES, PT, EC) are
    1-1.5 GB: if the client times out, run `parlaibero-mcp download XX` in a terminal instead."""
    iso = normalize_iso(country)

    def progress(name: str, done: int, total: int | None) -> None:
        try:
            anyio.from_thread.run(ctx.report_progress, done, total,
                                  f"{iso} {name}: {done / 2**20:.0f} MB")
        except Exception:
            pass

    result = await anyio.to_thread.run_sync(lambda: store.download_country(iso, force, progress))
    result["citation_doi"] = COUNTRIES[iso][2]
    return result


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False))
def import_from_folder(
    folder: Annotated[str, Field(description="Folder with {ISO}_interventions.csv (and optionally "
                                             "{ISO}_deputies.csv), or with one subfolder per country")],
) -> list[dict]:
    """Load ParlaIbero CSV files that were downloaded by hand from Dataverse."""
    return store.import_folder(folder)


# ── Querying ──────────────────────────────────────────────────────────────────

@mcp.tool(annotations=READ)
def query_sql(
    sql: Annotated[str, Field(description="DuckDB SQL over the tables in describe_data")],
    max_rows: Annotated[int, Field(ge=1, le=5000)] = 200,
    max_cell_chars: Annotated[int, Field(ge=50, le=100000,
                                         description="Truncate long text cells")] = 1000,
    timeout_s: Annotated[int, Field(ge=1, le=600)] = 120,
) -> dict:
    """Run a read-only SQL query (DuckDB dialect). The connection cannot write, read other
    files or reach the network."""
    cols, rows, truncated = store.run_query(sql, max_rows=max_rows, timeout_s=timeout_s)
    return {"columns": cols, "rows": _rows(cols, rows, max_cell_chars), "truncated": truncated}


@mcp.tool(annotations=READ)
def search_text(
    pattern: Annotated[str, Field(description="Word or phrase (or RE2 regular expression if regex=true)")],
    countries: Countries = None,
    regex: bool = False,
    whole_word: Annotated[bool, Field(description="Plain searches: match whole words only")] = False,
    date_from: Annotated[str | None, Field(description="YYYY-MM-DD")] = None,
    date_to: Annotated[str | None, Field(description="YYYY-MM-DD")] = None,
    party: Annotated[str | None, Field(description="Party label (ILIKE pattern, e.g. 'PSOE' or '%Frente%')")] = None,
    sex: Annotated[Literal["M", "F"] | None, Field(description="Speaker's sex (only linked deputies)")] = None,
    id_dep: str | None = None,
    speech_only: Annotated[bool, Field(description="Only rows with dm_speech = 1")] = True,
    limit: Annotated[int, Field(ge=1, le=200)] = 20,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> dict:
    """Find interventions containing a word, phrase or regex, newest first, with a snippet
    around the first match and the total number of matching rows. Plain searches ignore case
    and accents ('nacion' finds 'Nación')."""
    rx = _search_regex(pattern, regex, whole_word)
    params: list = [rx]
    where = "regexp_matches(text, ?)" + _filters(countries, date_from, date_to, party, sex, id_dep,
                                                 speech_only, params)
    _, total, _ = store.run_query(f"SELECT count(*) FROM interventions WHERE {where}", params)
    _, ids, _ = store.run_query(
        f"SELECT id_int FROM interventions WHERE {where} ORDER BY date DESC, id_int "
        f"LIMIT {int(limit)} OFFSET {int(offset)}", params, max_rows=limit)
    hits = []
    if ids:
        id_list = [r[0] for r in ids]
        cols, rows, _ = store.run_query(
            f"SELECT country, id_int, id_session, date, speaker_name, speaker_raw, party, sex, n_words, "
            f"text FROM interventions WHERE id_int IN ({', '.join('?' * len(id_list))})", id_list,
            max_rows=limit)
        by_id = {r[1]: dict(zip(cols, r)) for r in rows}
        for i in id_list:
            d = by_id[i]
            d["snippet"] = _snippet(d.pop("text") or "", rx)
            hits.append({k: store.jsonable(v) for k, v in d.items()})
    return {"regex_used": rx, "total_matching_rows": total[0][0], "returned": len(hits),
            "offset": offset, "hits": hits}


@mcp.tool(annotations=READ)
def get_intervention(
    id_int: Annotated[str, Field(description="Intervention id, e.g. ES0140012300045")],
    context: Annotated[int, Field(ge=0, le=20, description="Also return N turns before and after")] = 0,
) -> dict:
    """Full text and metadata of one intervention, optionally with surrounding turns."""
    cols, rows, _ = store.run_query(
        "SELECT i.* FROM interventions i JOIN (SELECT id_session, intervention_order FROM "
        "interventions WHERE id_int = ?) t ON i.id_session = t.id_session AND i.intervention_order "
        "BETWEEN t.intervention_order - ? AND t.intervention_order + ? ORDER BY i.intervention_order",
        [id_int, context, context], max_rows=2 * context + 50)
    if not rows:
        return {"error": f"No intervention with id_int {id_int!r} in the loaded countries."}
    return {"id_int": id_int, "turns": _rows(cols, rows)}


@mcp.tool(annotations=READ)
def get_session(
    id_session: Annotated[str, Field(description="Session id, e.g. ES0140012")],
    include_text: Annotated[bool, Field(description="Full text of every turn (can be long)")] = False,
    max_rows: Annotated[int, Field(ge=1, le=2000)] = 300,
) -> dict:
    """Metadata and the ordered list of turns of a session (speaker, party, words, first
    words of each turn, or the full text)."""
    text = "text" if include_text else "left(text, 160) AS opening"
    cols, rows, truncated = store.run_query(
        f"SELECT intervention_order, id_int, speaker_raw, speaker_name, id_dep, party, sex, "
        f"dm_speech, n_words, {text} FROM interventions WHERE id_session = ? "
        f"ORDER BY intervention_order", [id_session], max_rows=max_rows)
    if not rows:
        return {"error": f"No session {id_session!r} in the loaded countries."}
    mcols, mrows, _ = store.run_query(
        "SELECT country, legislature, legislative_session, session_number, date, session_type, "
        "count(*) AS turns, sum(n_words) FILTER (WHERE dm_speech = 1) AS speech_words "
        "FROM interventions WHERE id_session = ? GROUP BY ALL", [id_session])
    return {"session": _rows(mcols, mrows)[0], "turns": _rows(cols, rows), "truncated": truncated}


GROUPS = {
    "year": "year(date)",
    "decade": "(year(date) // 10) * 10",
    "country": "country",
    "legislature": "country || ' ' || legislature",
    "party": "country || ' ' || coalesce(party, '(unlinked)')",
    "sex": "coalesce(sex, '(unlinked)')",
    "speaker": "country || ' ' || coalesce(speaker_name, speaker_raw)",
    "session_type": "session_type",
}


@mcp.tool(annotations=READ)
def term_frequency(
    pattern: Annotated[str, Field(description="Word or phrase (or regex if regex=true)")],
    by: Annotated[Literal[tuple(GROUPS)], Field(description="Grouping dimension")] = "year",  # type: ignore[valid-type]
    countries: Countries = None,
    regex: bool = False,
    whole_word: bool = False,
    date_from: Annotated[str | None, Field(description="YYYY-MM-DD")] = None,
    date_to: Annotated[str | None, Field(description="YYYY-MM-DD")] = None,
    party: str | None = None,
    sex: Literal["M", "F"] | None = None,
    speech_only: bool = True,
    max_rows: Annotated[int, Field(ge=1, le=2000)] = 300,
) -> dict:
    """How often a term is used, by year, party, sex, speaker…: occurrences, interventions
    using it, total words, and occurrences per million words (to compare groups of different
    size). Plain patterns are case- and accent-insensitive."""
    rx = _search_regex(pattern, regex, whole_word)
    # regexp_matches is a cheap pre-filter; every row stays in, so total_words is the full denominator
    occ = "CASE WHEN regexp_matches(text, ?) THEN len(regexp_extract_all(text, ?)) ELSE 0 END"
    params: list = [rx, rx]
    where = _filters(countries, date_from, date_to, party, sex, None, speech_only, params)
    sql = (f"WITH t AS (SELECT {GROUPS[by]} AS grp, n_words, {occ} AS occ "
           f"FROM interventions WHERE text IS NOT NULL{where}) "
           f"SELECT grp AS {by}, sum(occ) AS occurrences, count(*) FILTER (WHERE occ > 0) AS "
           f"interventions_using, sum(n_words) AS total_words, "
           f"round(sum(occ) * 1e6 / nullif(sum(n_words), 0), 2) AS per_million_words "
           f"FROM t GROUP BY grp ORDER BY grp")
    cols, rows, truncated = store.run_query(sql, params, max_rows=max_rows, timeout_s=600)
    return {"pattern": pattern, "regex_used": rx, "by": by, "rows": _rows(cols, rows),
            "truncated": truncated}


@mcp.resource("parlaibero://about", mime_type="text/markdown")
def about() -> str:
    """What ParlaIbero is and how this server works."""
    lines = [f"# ParlaIbero MCP server {__version__}", "", INSTRUCTIONS, "", "## Datasets", ""]
    for iso, (en, _, doi) in COUNTRIES.items():
        lines.append(f"- {iso} · {en} · https://doi.org/{doi}")
    lines += ["", f"Local data: `{store.HOME}`", f"Collection: {COLLECTION_URL}"]
    return "\n".join(lines)


def main() -> None:
    _server.run()
