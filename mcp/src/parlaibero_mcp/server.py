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

from . import __version__, analysis, dataverse, library as libmod, store
from .textutil import search_regex
from .catalog import COLLECTION_URL, COUNTRIES, DOCUMENTS, normalize_iso

INSTRUCTIONS = """\
ParlaIbero: plenary speeches of the lower or single chambers of 16 countries (Argentina, Brazil,
Chile, Colombia, Costa Rica, Dominican Republic, Ecuador, Spain, Guatemala, Mexico, Panama, Peru,
Portugal, Paraguay, El Salvador, Uruguay), one row per intervention, linked to a register of
deputies. One dataset and one DOI per country in Harvard Dataverse (CC BY 4.0).

How to work with it:
1. `list_countries` shows what exists and what is already downloaded. Data must be downloaded
   once per country (`download_country`); big countries take 0.5-1.5 GB and a few minutes.
2. Before reading a trend, check the base with `coverage` (sessions, words, linkage, gaps).
   Frequencies over time: `ngram_viewer` (can draw an SVG/HTML chart) and `term_counter` (totals,
   first and last use). Who speaks: `share_of_voice` (voice vs weight in the chamber). What
   distinguishes groups: `distinctive_words`. Close reading: `kwic`, `collocations`,
   `search_text`, `get_intervention`, `get_session`. Anything else: `query_sql` (read-only
   DuckDB, schema in `describe_data`); save results with `export_result`; `query_log` lists what
   was run, for the methods section.
   Libraries (subsets): `library_create` gathers the interventions on a topic, period or group in
   one or SEVERAL countries; every analysis tool then takes `library=` to work inside it.
   `library_describe` says what is in it (size, spread, chair, long turns) before you compare;
   `library_export` writes one file per country for the Diarios Explorer plus an index.
3. Rows with `dm_speech = 0` are not speech (cover page, summaries, vote tallies, reproduced
   documents; `intervention_order = 0` is the session's Prolegomena). Filter `dm_speech = 1`
   to study what was said.
4. Documents read into the record (reports, bills, lists) stay as speech where the record marks
   no separator; they are about half of the words in Argentina and a quarter in Uruguay and
   Mexico. Word-based comparisons between countries must check `coverage` (long_turn_words_pct)
   and be re-run with `max_turn_words=10000`. The chair's procedural turns can dominate group
   comparisons: use `exclude_chair=true` in distinctive_words and share_of_voice.
5. `sex`, `party` and `district` come from the deputy register and are empty when the speaker
   could not be linked (`id_dep` empty: ministers, clerks, collective or anonymous voices).
   Coverage, linkage rates and caveats differ by country: read `get_documentation(country,
   'known_limitations')` and `'corpus_info'` before drawing comparative conclusions.
6. `id_session` / `id_int` are stable within a published version, not across versions: always
   report the dataset version. Cite each country's dataset with its DOI (`how_to_cite`).
"""

logging.getLogger("httpx").setLevel(logging.WARNING)

_server = _Server(name="parlaibero", instructions=INSTRUCTIONS)


# Analysis tools are logged (for query_log) and need the v2 database (token-based n_words).
LOGGED = {"query_sql", "search_text", "term_frequency", "ngram_viewer", "term_counter", "share_of_voice",
          "distinctive_words", "kwic", "collocations", "coverage", "export_result", "get_session",
          "get_intervention", "library_create", "library_edit", "library_combine", "library_describe",
          "library_delete", "library_rebuild", "library_export", "library_import"}


def make_before(logged: set[str], command: str):
    """Before an analysis tool: refuse a database built by an older engine, and log the call."""
    def before(name: str, kwargs: dict) -> None:
        if name in logged:
            if store.DB.exists() and store.schema_version() != store.SCHEMA_VERSION:
                raise ToolError(f"The local database was built by an older version. Run `{command} reindex` in a "
                                f"terminal and try again (it reloads each dataset from the files already on disk, "
                                f"no download).")
            analysis.log_call(name, {k: v for k, v in kwargs.items() if k != "ctx"})
    return before


_before = make_before(LOGGED, "parlaibero-mcp")


class _Tools:
    """Register tools so that any failure reaches the agent as a readable ToolError
    (mcp 2.x otherwise reports only "Error executing tool"). Other packages built on this engine
    create their own: Tools(their_server, their_before)."""

    def __init__(self, server=None, before=None):
        self.server = server if server is not None else _server
        self.before = before if before is not None else _before

    def tool(self, **kw):
        def deco(fn):
            if inspect.iscoroutinefunction(fn):
                @functools.wraps(fn)
                async def wrapped(*a, **k):
                    try:
                        self.before(fn.__name__, k)
                        return await fn(*a, **k)
                    except ToolError:
                        raise
                    except Exception as e:
                        raise ToolError(f"{type(e).__name__}: {e}") from e
            else:
                @functools.wraps(fn)
                def wrapped(*a, **k):
                    try:
                        self.before(fn.__name__, k)
                        return fn(*a, **k)
                    except ToolError:
                        raise
                    except Exception as e:
                        raise ToolError(f"{type(e).__name__}: {e}") from e
            self.server.tool(**kw)(wrapped)
            return fn
        return deco

    def resource(self, *a, **kw):
        return self.server.resource(*a, **kw)


Tools = _Tools
Server = _Server


mcp = _Tools()

READ = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
REMOTE_READ = ToolAnnotations(readOnlyHint=True, openWorldHint=True)

Country = Annotated[str, Field(description="ISO2 code (ES, MX, BR…) or country name")]
Countries = Annotated[list[str] | None, Field(
    default=None, description="ISO2 codes to restrict to; omit for every downloaded country")]


def _F(countries=None, date_from=None, date_to=None, party=None, sex=None, id_dep=None,
       speech_only=True, exclude_chair=False, max_turn_words=None, library=None) -> analysis.Filters:
    lib_id = None
    if library:
        lib_id, lib_countries = libmod.resolve(library)
        countries = countries or lib_countries
    return analysis.Filters(countries, date_from, date_to, party, sex, id_dep, speech_only,
                            exclude_chair, max_turn_words, lib_id, library if library else None)


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


# Common parameter types of the analysis tools
DateFrom = Annotated[str | None, Field(description="YYYY or YYYY-MM-DD")]
DateTo = Annotated[str | None, Field(description="YYYY or YYYY-MM-DD (inclusive)")]
Party = Annotated[str | None, Field(description="Party label as an ILIKE pattern, e.g. 'PSOE' or '%Frente%'")]
Sex = Annotated[Literal["M", "F"] | None, Field(description="Speaker's sex (linked deputies only)")]
SpeechOnly = Annotated[bool, Field(description="Only rows with dm_speech = 1 (recommended)")]
Terms = Annotated[str, Field(description="Comma-separated series; '+' sums variants into one series "
                                         "('corrupción+corrupção'); '*' ends a prefix ('democrati*'). "
                                         "Whole words, case- and accent-insensitive.")]
ExcludeChair = Annotated[bool, Field(description="Leave out the presiding officer's turns (procedural "
                                                 "speech: giving the floor, calling votes)")]
MaxTurnWords = Annotated[int | None, Field(ge=100, description="Leave out turns longer than this many "
                                                               "words — mostly documents read into the "
                                                               "record; 10000 is a sensible check")]
OutPath = Annotated[str | None, Field(description="File to write (absolute, or relative to the "
                                                  "client's working directory)")]
Library = Annotated[str | None, Field(description="Name of a library (see library_describe): only its "
                                                  "interventions; countries default to the library's")]


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
                             "n_words (tokens = runs of letters/digits, computed on import), row_n (record number in the "
                             "published CSV; the Diarios Explorer's speech_id).",
            "deputies": "Deputy registers, core columns common to all countries: country, id_dep, "
                        "speaker_name, first_name, last_name, sex, sex_source, party, "
                        "parliamentary_group, district, legislature, start_date, end_date, notes. "
                        "id_dep may repeat across legislatures (one row per term).",
            "deputies_{iso}": "Full register of one country (e.g. deputies_es), with its own extra columns.",
            "datasets": "One row per loaded country: doi, version, source, n_rows, date range.",
            "unigrams": "Word counts of speech rows: country, year, sex, fold (lower-case, accents "
                        "stripped), n. sum(n) equals sum(n_words) of the same speech rows.",
            "vocab": "Display form of each folded word per country: country, fold, word, n.",
            "lib.libraries": "The user's libraries: id, name, description, color, created_at, updated_at.",
            "lib.library_items": "Their interventions: library_id, country, id_int (join with interventions), "
                                 "row_n, fingerprint, note, tags (JSON), origin, added_at.",
            "lib.library_parts": "One row per library and country: edition of the data, doi, definitions (JSON).",
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
            "SELECT i.country, i.party, count(*) FROM lib.library_items l JOIN lib.libraries b ON b.id = "
            "l.library_id JOIN interventions i USING (id_int) WHERE b.name = 'my library' GROUP BY ALL ORDER BY 3 DESC",
        ],
        "tips": "Never SELECT text without LIMIT: the corpus holds millions of rows. Use "
                "regexp_matches(text, '…', 'i') or contains(lower(text), '…') to filter on text. "
                "For word-based comparisons between countries add `n_words <= 10000` (documents read "
                "into the record) and check coverage first.",
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
    library: Library = None,
    regex: bool = False,
    whole_word: Annotated[bool, Field(description="Plain searches: match whole words only")] = False,
    date_from: DateFrom = None,
    date_to: DateTo = None,
    party: Party = None,
    sex: Sex = None,
    id_dep: str | None = None,
    speech_only: SpeechOnly = True,
    limit: Annotated[int, Field(ge=1, le=200)] = 20,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> dict:
    """Find interventions containing a word, phrase or regex, newest first, with a snippet
    around the first match and the total number of matching rows. Plain searches ignore case
    and accents ('nacion' finds 'Nación')."""
    return analysis.search_text(pattern, _F(countries, date_from, date_to, party, sex, id_dep, speech_only,
                                            library=library), regex, whole_word, limit, offset)


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


@mcp.tool(annotations=READ)
def term_frequency(
    pattern: Annotated[str, Field(description="Word or phrase; '+' sums variants, '*' ends a prefix")],
    by: Annotated[Literal[tuple(analysis.GROUPS)], Field(description="Grouping dimension")] = "year",  # type: ignore[valid-type]
    countries: Countries = None,
    library: Library = None,
    date_from: DateFrom = None,
    date_to: DateTo = None,
    party: Party = None,
    sex: Sex = None,
    speech_only: SpeechOnly = True,
    exclude_chair: ExcludeChair = False,
    max_turn_words: MaxTurnWords = None,
    max_rows: Annotated[int, Field(ge=1, le=2000)] = 300,
) -> dict:
    """How often a term is used, grouped by year, decade, country, legislature, party, sex,
    speaker, session type or session: occurrences, interventions using it, total words and
    occurrences per million words. Same counting as ngram_viewer. by='session' lists the sessions
    where the term concentrates — a way to find the date of an event in each chamber."""
    return analysis.term_frequency(pattern, _F(countries, date_from, date_to, party, sex, None, speech_only, exclude_chair, max_turn_words, library),
                                   by, max_rows)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False))
def ngram_viewer(
    terms: Terms,
    countries: Countries = None,
    library: Library = None,
    split_by_country: Annotated[bool, Field(description="One line per term × country instead of "
                                                        "pooling the countries")] = False,
    measure: Annotated[Literal["per_million", "count", "interventions_pct"], Field(
        description="per_million: occurrences per million words (comparable across years); count: raw "
                    "occurrences; interventions_pct: % of interventions using the term")] = "per_million",
    smoothing: Annotated[int, Field(ge=0, le=10, description="Centred moving average over ±N years "
                                                             "(Google Ngram uses 3)")] = 0,
    date_from: DateFrom = None,
    date_to: DateTo = None,
    party: Party = None,
    sex: Sex = None,
    speech_only: SpeechOnly = True,
    exclude_chair: ExcludeChair = False,
    max_turn_words: MaxTurnWords = None,
    chart_path: Annotated[str | None, Field(description="Write a chart: '.svg' (static figure for papers "
                                                        "and slides) or '.html' (page with hover, dark mode "
                                                        "and data table). At most 8 series.")] = None,
    title: str | None = None,
    language: Annotated[Literal["es", "en", "pt"], Field(description="Language of the chart labels")] = "es",
    overwrite: bool = False,
) -> dict:
    """Google Books Ngram-style viewer: yearly frequency of one or more words or phrases, with
    the base behind every point (words, sessions) and low-base years flagged. Optionally writes
    the chart to an SVG or HTML file."""
    return analysis.ngram_viewer(terms, _F(countries, date_from, date_to, party, sex, None, speech_only, exclude_chair, max_turn_words, library),
                                 split_by_country, measure, smoothing, chart_path, title, language, overwrite)


@mcp.tool(annotations=READ)
def term_counter(
    terms: Terms,
    countries: Countries = None,
    library: Library = None,
    date_from: DateFrom = None,
    date_to: DateTo = None,
    party: Party = None,
    sex: Sex = None,
    speech_only: SpeechOnly = True,
    exclude_chair: ExcludeChair = False,
    max_turn_words: MaxTurnWords = None,
) -> dict:
    """Counter for one or more terms: occurrences, interventions, sessions, speakers, breakdown by
    sex and party (with per-million rates), and the FIRST and LAST use in each country, with the
    intervention id — when a term entered each chamber's vocabulary."""
    return analysis.term_counter(terms, _F(countries, date_from, date_to, party, sex, None, speech_only, exclude_chair, max_turn_words, library))


@mcp.tool(annotations=READ)
def share_of_voice(
    countries: Countries = None,
    library: Library = None,
    by: Annotated[Literal["sex", "party"], Field(description="Group to compare")] = "sex",
    per: Annotated[Literal["legislature", "year", "all"], Field(description="Period")] = "legislature",
    unit: Annotated[Literal["words", "turns"], Field(description="Measure of voice")] = "words",
    date_from: DateFrom = None,
    date_to: DateTo = None,
    exclude_chair: ExcludeChair = False,
    max_turn_words: MaxTurnWords = None,
) -> dict:
    """How much each group speaks compared with its weight in the chamber: share of words (or
    turns) and of speakers among linked deputies, against the group's share of members on the
    register in that period, and their ratio (>1 = speaks more than its weight)."""
    return analysis.share_of_voice(_F(countries, date_from, date_to, exclude_chair=exclude_chair, max_turn_words=max_turn_words, library=library), by, per, unit)


@mcp.tool(annotations=READ)
def distinctive_words(
    field: Annotated[Literal["sex", "party", "period", "country", "id_dep", "library"], Field(
        description="What separates the two groups")],
    a: Annotated[str, Field(description="Group A: 'F', a party label, a period '2000-2010', an ISO2 "
                                        "code, an id_dep or a library name")],
    b: Annotated[str | None, Field(description="Group B, same kind as A; omit for 'everyone else'")] = None,
    countries: Countries = None,
    library: Library = None,
    date_from: DateFrom = None,
    date_to: DateTo = None,
    exclude_chair: ExcludeChair = False,
    max_turn_words: MaxTurnWords = None,
    top: Annotated[int, Field(ge=5, le=200)] = 30,
    min_count: Annotated[int, Field(ge=1)] = 20,
) -> dict:
    """Words that most distinguish group A from group B (weighted log-odds with an informative
    Dirichlet prior, Monroe et al. 2008): e.g. women vs men deputies, one party vs another,
    one period vs another, a library vs the rest of its chambers. Compare within one language."""
    return analysis.distinctive_words(_F(countries, date_from, date_to, exclude_chair=exclude_chair, max_turn_words=max_turn_words, library=library), field, a, b, top, min_count)


@mcp.tool(annotations=READ)
def kwic(
    pattern: Annotated[str, Field(description="Word or phrase ('*' ends a prefix), or RE2 regex if regex=true")],
    countries: Countries = None,
    library: Library = None,
    regex: bool = False,
    whole_word: bool = True,
    date_from: DateFrom = None,
    date_to: DateTo = None,
    party: Party = None,
    sex: Sex = None,
    n: Annotated[int, Field(ge=1, le=500, description="Interventions to sample")] = 40,
    width: Annotated[int, Field(ge=20, le=300, description="Characters of context on each side")] = 70,
    order: Annotated[Literal["random", "newest", "oldest"], Field(
        description="random gives a representative sample (reproducible with seed)")] = "random",
    seed: int = 1,
) -> dict:
    """Keyword in context: concordance lines (left context · match · right context) from a
    sample of the interventions that use the term, for close reading."""
    return analysis.kwic(pattern, _F(countries, date_from, date_to, party, sex, library=library), regex, whole_word,
                         n, width, order, seed)


@mcp.tool(annotations=READ)
def collocations(
    pattern: Annotated[str, Field(description="Word or phrase ('*' ends a prefix)")],
    countries: Countries = None,
    library: Library = None,
    date_from: DateFrom = None,
    date_to: DateTo = None,
    party: Party = None,
    sex: Sex = None,
    exclude_chair: ExcludeChair = False,
    max_turn_words: MaxTurnWords = None,
    window: Annotated[int, Field(ge=1, le=20, description="Tokens on each side")] = 5,
    top: Annotated[int, Field(ge=5, le=200)] = 30,
    min_count: Annotated[int, Field(ge=2)] = 5,
    sample: Annotated[int, Field(ge=100, le=50000, description="Interventions sampled")] = 5000,
    exclude_stopwords: bool = True,
) -> dict:
    """Words that keep company with a term: over-represented within ±window tokens of it
    (Dunning log-likelihood). Run with different dates to see how a term's associations shift."""
    return analysis.collocations(pattern, _F(countries, date_from, date_to, party, sex, exclude_chair=exclude_chair, max_turn_words=max_turn_words, library=library), window, top,
                                 min_count, sample, exclude_stopwords)


@mcp.tool(annotations=REMOTE_READ)
def coverage(
    countries: Countries = None,
    library: Library = None,
    by: Annotated[Literal["year", "legislature"], Field(description="Period")] = "year",
    date_from: DateFrom = None,
    date_to: DateTo = None,
) -> dict:
    """Data-quality check before interpreting a trend: sessions, rows, speech words, linked and
    sex-known shares per period, missing years and low-base periods, plus each corpus's
    linkage figures. Call it before comparing countries or reading peaks."""
    return analysis.coverage(_F(countries, date_from, date_to, library=library), by)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False))
def export_result(
    sql: Annotated[str, Field(description="One SELECT over the tables in describe_data")],
    path: Annotated[str, Field(description="Output file, .csv or .parquet (absolute, or relative to "
                                           "the client's working directory)")],
    format: Annotated[Literal["csv", "parquet"] | None, Field(description="Defaults to the extension")] = None,
    overwrite: bool = False,
) -> dict:
    """Save the full result of a query to CSV or Parquet, to continue in R, Python or Stata.
    Only the destination folder can be written (or read); nothing else on disk is reachable."""
    return analysis.export_result(sql, path, format, overwrite)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False))
def query_log(
    last: Annotated[int, Field(ge=1, le=5000)] = 50,
    methods_path: Annotated[str | None, Field(description="Also write a Markdown methods note (datasets "
                                                          "with DOI and version + every analysis run)")] = None,
    overwrite: bool = False,
) -> dict:
    """The analyses run so far (tool, parameters, dataset versions), for reproducibility. Can
    write a methods appendix ready to adapt."""
    return analysis.query_log(last, methods_path, overwrite)


# ── Libraries (subsets) ───────────────────────────────────────────────────────

WRITE_LOCAL = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
LibName = Annotated[str, Field(description="Library name (case-insensitive)")]


@mcp.tool(annotations=WRITE_LOCAL)
def library_create(
    name: LibName,
    countries: Annotated[list[str], Field(description="ISO2 codes of the chambers it takes (one or several)")],
    terms: Annotated[str | None, Field(description="An intervention enters if it uses ANY of these: comma- or "
                                                   "'+'-separated, '*' ends a prefix, whole words, case- and "
                                                   "accent-insensitive. Give Spanish AND Portuguese forms when "
                                                   "BR or PT are in ('corrupción+corrupção')")] = None,
    regex: Annotated[bool, Field(description="terms is one RE2 regular expression")] = False,
    min_occurrences: Annotated[int, Field(ge=1, le=100, description="Times the terms must appear in the "
                                                                   "intervention: 2-3 keeps those that DISCUSS "
                                                                   "the topic, not those that mention it")] = 1,
    date_from: DateFrom = None,
    date_to: DateTo = None,
    party: Party = None,
    sex: Sex = None,
    id_dep: str | None = None,
    speech_only: SpeechOnly = True,
    exclude_chair: ExcludeChair = False,
    max_turn_words: MaxTurnWords = None,
    event_dates: Annotated[dict[str, str] | None, Field(
        description="Align on an event: {ISO2: 'YYYY-MM-DD'} per country; each country's window becomes "
                    "event − days_before … event + days_after (stored as plain dates). To find the dates: "
                    "term_counter (first use per chamber) or term_frequency(by='session')")] = None,
    days_before: Annotated[int, Field(ge=0, le=36500)] = 0,
    days_after: Annotated[int, Field(ge=0, le=36500)] = 0,
    per_country: Annotated[dict[str, dict] | None, Field(
        description="Per-country overrides of the settings above, e.g. {'BR': {'terms': 'aborto+interrupção "
                    "da gravidez'}, 'ES': {'date_from': '2010'}}")] = None,
    label: Annotated[str | None, Field(description="Common concept the parts share ('abortion'), recorded in "
                                                   "every country's definition")] = None,
    description: str = "",
    color: Annotated[str, Field(description="Colour in the explorer")] = "indigo",
    extend: Annotated[bool, Field(description="Add to an existing library of that name instead of failing")] = False,
) -> dict:
    """Create a library: a named, saved subset of interventions — on a topic, in a period, of a group —
    from one or SEVERAL countries, for focused and comparative analysis. Each country gets its own
    definition (terms, filters, time window), recorded with the edition of the data. Returns the
    description of what was gathered (see library_describe). Then pass library=<name> to any analysis
    tool. Equivalent terms across countries are the user's claim: say so when reporting."""
    return libmod.create(name, countries, terms, regex, min_occurrences, date_from, date_to, party, sex, id_dep,
                         speech_only, exclude_chair, max_turn_words, event_dates, days_before, days_after,
                         per_country, label, description, color, extend)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False))
def library_edit(
    name: LibName,
    action: Annotated[Literal["add", "remove", "note"], Field(
        description="add / remove interventions (by id_ints or by a query), or note one (note and/or tags)")],
    id_ints: Annotated[list[str] | None, Field(description="Intervention ids")] = None,
    sql: Annotated[str | None, Field(description="add/remove: a read-only SELECT returning a column id_int, "
                                                 "e.g. after reading kwic or search_text results")] = None,
    note: Annotated[str | None, Field(description="note: text attached to the intervention (id_ints[0])")] = None,
    tags: Annotated[list[str] | None, Field(description="note: tags attached to the intervention")] = None,
) -> dict:
    """Refine a library by hand: add or remove interventions, or attach a note and tags to one.
    Removed interventions stay excluded when the library is rebuilt from its definitions."""
    if action == "add":
        return libmod.add(name, id_ints, sql)
    if action == "remove":
        return libmod.remove(name, id_ints, sql)
    if not id_ints or len(id_ints) != 1:
        raise ValueError("note takes exactly one id in id_ints")
    return libmod.note(name, id_ints[0], note, tags)


@mcp.tool(annotations=WRITE_LOCAL)
def library_combine(
    name: Annotated[str, Field(description="Name of the NEW library")],
    a: LibName,
    b: LibName,
    op: Annotated[Literal["union", "intersection", "difference"], Field(
        description="union (in either), intersection (in both), difference (in a, not in b)")],
    description: str = "",
) -> dict:
    """A new library from two existing ones (notes and tags travel with the interventions)."""
    return libmod.combine(name, a, b, op, description)


@mcp.tool(annotations=READ)
def library_describe(
    name: Annotated[str | None, Field(description="Library name; omit to list every library")] = None,
) -> dict:
    """What is in a library, per country: interventions, sessions, dates, speakers, words, linkage,
    share of the chair and of very long turns, years too thin to read as trends, the definitions
    and the data edition — with warnings for comparing countries. Call it before analysing."""
    return libmod.list_libraries() if not name else libmod.describe(name)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False))
def library_delete(
    name: LibName,
    confirm: Annotated[bool, Field(description="Must be true: deleting cannot be undone")] = False,
) -> dict:
    """Delete a library (only the library: the data are not touched). Without confirm=true it only
    says what would be deleted."""
    return libmod.delete(name, confirm)


@mcp.tool(annotations=WRITE_LOCAL)
def library_rebuild(name: LibName) -> dict:
    """After downloading a new edition of a country: rebuild the library on it. Definitions run
    again; interventions added by hand, combined or imported, and their notes, are found again by
    their text; exclusions are kept. Reports what came in and what was lost, per country."""
    return libmod.rebuild(name)


@mcp.tool(annotations=WRITE_LOCAL)
def library_export(
    name: LibName,
    folder: Annotated[str, Field(description="Destination folder (absolute, or relative to the client's "
                                             "working directory)")],
    table_format: Annotated[Literal["csv", "parquet"] | None, Field(
        description="Also write every intervention of the library with its metadata, note and tags")] = None,
    overwrite: bool = False,
) -> dict:
    """Export for the Diarios Explorer: one .2replib per country (the explorer holds one country at a
    time) plus an index (.parlaibero-biblioteca.json) that library_import uses to rebuild the whole
    comparative library. Each file must be imported in the explorer with ITS country's CSV loaded."""
    return libmod.export(name, folder, table_format, overwrite)


@mcp.tool(annotations=WRITE_LOCAL)
def library_import(
    paths: Annotated[list[str], Field(description=".2replib files exported by the explorer (one per country), "
                                                  "an index .parlaibero-biblioteca.json, or a folder")],
    name: Annotated[str | None, Field(description="Name of the new library (default: the one in the files)")] = None,
    force: Annotated[bool, Field(description="Import even when the files were written on another version of "
                                             "the data (only items whose date and speaker still match)")] = False,
) -> dict:
    """Bring libraries made in the Diarios Explorer into the MCP — several countries' files become one
    comparative library. Every item is checked against the loaded data (row → intervention, then
    its date and speaker); whatever does not match is reported, not translated silently."""
    return libmod.import_files(paths, name, force)


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
