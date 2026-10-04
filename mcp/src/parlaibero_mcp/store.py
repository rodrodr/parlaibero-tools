"""Local store: downloaded files plus one DuckDB database with every imported dataset.

Layout (the active profile's home: PARLAIBERO_HOME, default ~/.parlaibero, for ParlaIbero):
    data/{ISO}/                 files exactly as deposited in Dataverse
    parlaibero.duckdb           tables `interventions`, `deputies`, `deputies_{iso}`, `datasets`
    bibliotecas.duckdb          the user's libraries (subsets); kept apart so that re-downloading or
                                re-indexing the data never touches them. Attached as `lib`.
"""
from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

import csv
import hashlib
import json
import sys

import duckdb

from . import dataverse, profile
from .catalog import COUNTRIES, document_filename, normalize_iso

HOME = DATA = DB = LIBDB = Path()


def set_home(home: Path) -> None:
    """Where the active collection keeps its files (profile.activate calls it)."""
    global HOME, DATA, DB, LIBDB
    HOME = Path(home).expanduser()
    DATA = HOME / "data"
    DB = HOME / ("parlaibero.duckdb" if profile.ACTIVE.name == "parlaibero" else f"{profile.ACTIVE.name}.duckdb")
    LIBDB = HOME / "bibliotecas.duckdb"


set_home(profile.ACTIVE.home)

LOG_DISABLED = os.environ.get("PARLAIBERO_LOG", "1") in ("0", "false", "no")

# One DuckDB file can be open read-write OR read-only within a process, never both at once.
_LOCK = threading.RLock()

INTERVENTION_COLUMNS = [
    "id_session", "id_int", "legislature", "legislative_session", "session_number", "date",
    "session_type", "intervention_order", "speaker_raw", "id_dep", "speaker_name", "sex",
    "party", "district", "dm_speech", "text",
]
DEPUTY_CORE = [
    "id_dep", "speaker_name", "first_name", "last_name", "sex", "sex_source", "party",
    "parliamentary_group", "district", "legislature", "start_date", "end_date", "notes",
]

def _extra_columns_ddl() -> str:
    return "".join(f", {name} {typ}" for name, (typ, _, _) in profile.ACTIVE.extra_columns.items())


def schema() -> str:
    """The tables, with the active profile's extra columns at the end of `interventions`."""
    return SCHEMA.replace("n_words INTEGER, row_n BIGINT", "n_words INTEGER, row_n BIGINT" + _extra_columns_ddl())


SCHEMA = f"""
CREATE TABLE IF NOT EXISTS interventions (
    country VARCHAR, id_session VARCHAR, id_int VARCHAR, legislature VARCHAR,
    legislative_session VARCHAR, session_number VARCHAR, date DATE, session_type VARCHAR,
    intervention_order INTEGER, speaker_raw VARCHAR, id_dep VARCHAR, speaker_name VARCHAR,
    sex VARCHAR, party VARCHAR, district VARCHAR, dm_speech TINYINT, text VARCHAR,
    n_words INTEGER, row_n BIGINT
);
CREATE TABLE IF NOT EXISTS deputies (country VARCHAR, {", ".join(c + " VARCHAR" for c in DEPUTY_CORE)});
CREATE TABLE IF NOT EXISTS unigrams (country VARCHAR, year SMALLINT, sex VARCHAR, fold VARCHAR, n BIGINT);
CREATE TABLE IF NOT EXISTS vocab (country VARCHAR, fold VARCHAR, word VARCHAR, n BIGINT);
CREATE TABLE IF NOT EXISTS meta (key VARCHAR PRIMARY KEY, value VARCHAR);
CREATE TABLE IF NOT EXISTS datasets (
    country VARCHAR PRIMARY KEY, doi VARCHAR, title VARCHAR, version VARCHAR, source VARCHAR,
    imported_at TIMESTAMP, n_rows BIGINT, n_speech_rows BIGINT, n_sessions BIGINT,
    date_min DATE, date_max DATE
);
"""


SCHEMA_VERSION = "4"   # 3: n_words = letter/digit/mark tokens; unigrams + vocab tables
                       # 4: row_n = record number in the published CSV (the explorer's speech_id)

# Libraries live in their own file. An item is a row of `interventions` (id_int is unique across
# countries: it starts with the ISO code); row_n is kept so a library can be written for the
# explorer, and the md5 of the text (fingerprint) so it can be found again in a later edition.
LIB_SCHEMA = """
CREATE SEQUENCE IF NOT EXISTS library_id_seq;
CREATE TABLE IF NOT EXISTS libraries (
    id INTEGER PRIMARY KEY DEFAULT nextval('library_id_seq'), name VARCHAR UNIQUE NOT NULL,
    description VARCHAR DEFAULT '', color VARCHAR DEFAULT 'indigo',
    created_at TIMESTAMP, updated_at TIMESTAMP
);
CREATE TABLE IF NOT EXISTS library_parts (
    library_id INTEGER, country VARCHAR, edition VARCHAR, doi VARCHAR,
    definitions VARCHAR DEFAULT '[]',
    PRIMARY KEY (library_id, country)
);
CREATE TABLE IF NOT EXISTS library_items (
    library_id INTEGER, country VARCHAR, id_int VARCHAR, row_n BIGINT, fingerprint VARCHAR,
    note VARCHAR DEFAULT '', tags VARCHAR DEFAULT '[]', origin VARCHAR, added_at TIMESTAMP,
    PRIMARY KEY (library_id, id_int)
);
CREATE TABLE IF NOT EXISTS library_excl (
    library_id INTEGER, country VARCHAR, id_int VARCHAR, fingerprint VARCHAR,
    PRIMARY KEY (library_id, id_int)
);
"""


class NoData(RuntimeError):
    pass


@contextmanager
def connect(read_only: bool = True) -> Iterator[duckdb.DuckDBPyConnection]:
    """Read-only connections cannot reach the file system or the network: safe for user SQL."""
    with _LOCK:
        if read_only:
            if not DB.exists():
                raise NoData("No country has been downloaded yet. Use download_country first.")
            _ensure_libdb()
            con = duckdb.connect(str(DB), read_only=True)
            # never print a progress bar: on an MCP stdio server, stdout is the protocol channel
            con.execute("SET enable_progress_bar = false")
            con.execute(f"ATTACH {_sql_str(str(LIBDB))} AS lib (READ_ONLY)")
            # attach first, then close every door: no other file, no network, no settings change
            con.execute("SET enable_external_access = false")
            con.execute("SET lock_configuration = true")
        else:
            HOME.mkdir(parents=True, exist_ok=True)
            con = duckdb.connect(str(DB))
            con.execute("SET enable_progress_bar = false")
            con.execute(schema())
        try:
            yield con
        finally:
            con.close()


@contextmanager
def export_connection(directory: Path) -> Iterator[duckdb.DuckDBPyConnection]:
    """Read-only connection that may write files only inside `directory` (for COPY … TO)."""
    with _LOCK:
        if not DB.exists():
            raise NoData("No country has been downloaded yet. Use download_country first.")
        _ensure_libdb()
        con = duckdb.connect(str(DB), read_only=True)
        con.execute("SET enable_progress_bar = false")
        con.execute(f"ATTACH {_sql_str(str(LIBDB))} AS lib (READ_ONLY)")
        # order matters: allow the folder first, then close external access and lock the settings
        con.execute("SET allowed_directories = ?", [[str(Path(directory).resolve()) + os.sep]])
        con.execute("SET enable_external_access = false")
        con.execute("SET lock_configuration = true")
        try:
            yield con
        finally:
            con.close()


def _sql_str(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def _ensure_libdb() -> None:
    if not LIBDB.exists():
        HOME.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect(str(LIBDB))
        try:
            con.execute(LIB_SCHEMA)
        finally:
            con.close()


@contextmanager
def library_connection() -> Iterator[duckdb.DuckDBPyConnection]:
    """Write connection for the library functions (never for user SQL): the libraries attached
    read-write as `lib`, the data read-only and as the default catalog, so the same SQL (and the
    same Filters.where) runs here and on the sandboxed connection."""
    with _LOCK:
        if not DB.exists():
            raise NoData("No country has been downloaded yet. Use download_country first.")
        HOME.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect()
        con.execute("SET enable_progress_bar = false")
        con.execute(f"ATTACH {_sql_str(str(LIBDB))} AS lib")
        con.execute("USE lib")
        con.execute(LIB_SCHEMA)
        con.execute(f"ATTACH {_sql_str(str(DB))} AS pi (READ_ONLY)")
        con.execute("USE pi")
        try:
            yield con
        finally:
            con.close()


# A word is a maximal run of letters, digits and combining marks (so a decomposed 'ç' does not
# split it): the same definition as the unigram table and the exact counts.
N_WORDS_SQL = r"coalesce(len(regexp_extract_all(text, '[\pL\pN\pM]+')), 0)"


def index_country(con: duckdb.DuckDBPyConnection, iso: str) -> None:
    """(Re)build the unigram counts (speech rows, by year and sex, accent-folded) and the
    display vocabulary of one country. ~5 s for 150 million words."""
    con.execute("DELETE FROM unigrams WHERE country = ?", [iso])
    con.execute("DELETE FROM vocab WHERE country = ?", [iso])
    con.execute(r"""CREATE OR REPLACE TEMP TABLE _w AS
        SELECT year(date) AS y, sex, w, count(*) AS n FROM (
            SELECT date, sex, unnest(regexp_extract_all(lower(text), '[\pL\pN\pM]+')) AS w
            FROM interventions WHERE country = ? AND dm_speech = 1)
        GROUP BY ALL""", [iso])
    con.execute("INSERT INTO unigrams SELECT ?, y, sex, strip_accents(w), sum(n) FROM _w GROUP BY ALL", [iso])
    con.execute("""INSERT INTO vocab SELECT ?, f, arg_max(w, n), sum(n) FROM (
        SELECT strip_accents(w) AS f, w, sum(n) AS n FROM _w GROUP BY ALL) GROUP BY f""", [iso])
    con.execute("DROP TABLE _w")
    con.execute("INSERT OR REPLACE INTO meta VALUES ('schema_version', ?)", [SCHEMA_VERSION])


def reindex_all(progress=None) -> list[str]:
    """Upgrade a database built by an older version. Every country is loaded again from the files
    already on disk (no download): that recomputes n_words, the word tables and row_n."""
    with connect(read_only=False) as con:
        try:
            con.execute("ALTER TABLE interventions ADD COLUMN IF NOT EXISTS row_n BIGINT")
        except duckdb.Error:
            pass
        sets = con.execute("SELECT country, source, version, title FROM datasets ORDER BY 1").fetchall()
    done = []
    for iso, source, version, title in sets:
        folder = _source_folder(iso, source)
        if folder is None:
            raise FileNotFoundError(f"{iso}: the CSV files are no longer on disk. Run `parlaibero-mcp download "
                                    f"{iso}` (or import_from_folder) to load it again.")
        if progress:
            progress(iso)
        import_country(iso, folder, source=source, version=version, title=title)
        done.append(iso)
    with connect(read_only=False) as con:
        con.execute("INSERT OR REPLACE INTO meta VALUES ('schema_version', ?)", [SCHEMA_VERSION])
        con.execute("CHECKPOINT")
    return done


def _source_folder(iso: str, source: str | None) -> Path | None:
    """Where a loaded country's CSV files are: the download folder, or the folder it was imported from."""
    candidates = [country_dir(iso)]
    if source and source.startswith("local folder "):
        candidates.insert(0, Path(source[len("local folder "):]))
    return next((c for c in candidates if (c / profile.ACTIVE.interventions_file(iso)).exists()), None)


def schema_version() -> str | None:
    if not DB.exists():
        return None
    with connect() as con:
        try:
            r = con.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        except duckdb.CatalogException:
            return "1"
    return r[0] if r else "1"


def country_dir(iso: str) -> Path:
    return DATA / iso


# ── Download & import ─────────────────────────────────────────────────────────

def download_country(country: str, force: bool = False,
                     progress: Callable[[str, int, int | None], None] | None = None) -> dict:
    """Download every file of a country's dataset (verifying MD5) and import it into DuckDB."""
    iso = normalize_iso(country)
    doi = COUNTRIES[iso][2]
    info = dataverse.summary(doi)
    folder = country_dir(iso)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = folder / ".version"
    current = stamp.read_text().strip() if stamp.exists() else None
    downloaded = []
    for f in info["files"]:
        dest = folder / f["filename"]
        if dest.exists() and not force and current == info["version"] and \
                (f["size"] is None or dest.stat().st_size == f["size"]):
            continue
        cb = (lambda done, total, name=f["filename"]: progress(name, done, total)) if progress else None
        dataverse.download(f["id"], dest, f["md5"], cb)
        downloaded.append(f["filename"])
    stamp.write_text(info["version"])
    # the bibliographic record of exactly this edition, for library exports (works offline later)
    (folder / ".source.json").write_text(json.dumps(dataverse.source_record(doi), ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    result = import_country(iso, folder, source=f"Harvard Dataverse doi:{doi} v{info['version']}",
                            version=info["version"], title=info["title"])
    result["downloaded_files"] = downloaded
    return result


def _canonical_select() -> str:
    """The canonical columns over the raw CSV, mapped by the active profile."""
    p = profile.ACTIVE
    out = []
    for c in INTERVENTION_COLUMNS:
        e = p.column_sql.get(c, c)
        out.append(f"TRY_CAST({e} AS DATE)" if c == "date" else
                   f"TRY_CAST({e} AS INTEGER)" if c == "intervention_order" else
                   f"TRY_CAST({e} AS TINYINT)" if c == "dm_speech" else e)
    return ", ".join(out)


def import_country(country: str, folder: Path, source: str | None = None,
                   version: str | None = None, title: str | None = None) -> dict:
    """Import a dataset's interventions (and, if the profile has them, deputies) from `folder`,
    replacing its old rows."""
    p = profile.ACTIVE
    iso = normalize_iso(country)
    folder = Path(folder).expanduser()
    inter = folder / p.interventions_file(iso)
    dname = p.deputies_file(iso)
    deps = folder / dname if dname else None
    if not inter.exists():
        raise FileNotFoundError(f"{inter} not found")
    delim = p.delimiter.replace("'", "''")
    read = (f"read_csv({{path}}, header=true, all_varchar=true, delim='{delim}', quote='\"', "
            f"escape='\"', max_line_size=67108864)")
    cols = _canonical_select()
    extra = "".join(f", {expr}" for _, (_, expr, _) in p.extra_columns.items())
    # the word count runs on the raw CSV, where the text column may have another name
    words = N_WORDS_SQL.replace("regexp_extract_all(text,", f"regexp_extract_all({p.column_sql.get('text', 'text')},")
    with connect(read_only=False) as con:
        con.execute("BEGIN TRANSACTION")
        try:
            con.execute("DELETE FROM interventions WHERE country = ?", [iso])
            # row_n: DuckDB keeps the file order (preserve_insertion_order); checked below against an
            # independent reading of the file, the way the explorer numbers it
            con.execute(f"INSERT INTO interventions SELECT {_sql_str(iso)}, {cols}, {words}, "
                        f"row_number() OVER (){extra} FROM {read.format(path=_sql_str(str(inter)))}")
            check_row_numbers(con, iso, inter)
            con.execute("DELETE FROM deputies WHERE country = ?", [iso])
            con.execute(f"DROP TABLE IF EXISTS deputies_{iso.lower()}")
            if deps is not None and deps.exists():
                con.execute(f"CREATE TABLE deputies_{iso.lower()} AS SELECT * FROM "
                            f"{read.format(path=_sql_str(str(deps)))}")
                have = {r[0] for r in con.execute(f"DESCRIBE deputies_{iso.lower()}").fetchall()}
                sel = ", ".join(c if c in have else f"NULL AS {c}" for c in DEPUTY_CORE)
                con.execute(f"INSERT INTO deputies SELECT {_sql_str(iso)}, {sel} FROM deputies_{iso.lower()}")
            index_country(con, iso)
            if p.after_import:
                p.after_import(con, iso, folder)
            stats = con.execute(
                "SELECT count(*), sum(CASE WHEN dm_speech = 1 THEN 1 ELSE 0 END), "
                "count(DISTINCT id_session), min(date), max(date) FROM interventions WHERE country = ?",
                [iso]).fetchone()
            con.execute("DELETE FROM datasets WHERE country = ?", [iso])
            con.execute("INSERT INTO datasets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [
                iso, COUNTRIES[iso][2], title, version, source or f"local folder {folder}",
                datetime.now(timezone.utc).replace(tzinfo=None), *stats])
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    return {"country": iso, "rows": stats[0], "speech_rows": stats[1], "sessions": stats[2],
            "date_min": str(stats[3]), "date_max": str(stats[4]), "version": version}


def csv_id_sequence_digest(path: Path) -> tuple[int, str]:
    """(records, sha256 of the record key column in file order), read with Python's csv module and
    counted as the explorer counts them: the header and blank lines are not records."""
    csv.field_size_limit(sys.maxsize)
    h = hashlib.sha256()
    n = 0
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = csv.reader(fh, delimiter=profile.ACTIVE.delimiter)
        header = next(rows)
        k = header.index(profile.ACTIVE.row_key_csv)
        for row in rows:
            if not row:
                continue
            n += 1
            h.update(row[k].encode("utf-8") + b"\n")
    return n, h.hexdigest()


def check_row_numbers(con: duckdb.DuckDBPyConnection, iso: str, path: Path) -> None:
    """row_n must be the record number of the published file: the explorer's speech_id."""
    n, digest = csv_id_sequence_digest(path)
    h = hashlib.sha256()
    cur = con.execute(f"SELECT {profile.ACTIVE.row_key_sql} FROM interventions WHERE country = ? ORDER BY row_n",
                      [iso])
    m = 0
    while batch := cur.fetchmany(100_000):
        for (i,) in batch:
            h.update((i or "").encode("utf-8") + b"\n")
        m += len(batch)
    if (m, h.hexdigest()) != (n, digest):
        raise RuntimeError(f"{iso}: the row numbers do not follow the file ({m:,} rows loaded, {n:,} records "
                           f"in {path.name}). Nothing was imported.")


def import_folder(folder: str) -> list[dict]:
    """Import every dataset whose interventions file is in `folder` or its immediate subfolders."""
    root = Path(folder).expanduser()
    out = []
    for iso in COUNTRIES:
        name = profile.ACTIVE.interventions_file(iso)
        f = next((f for f in [root / name, *sorted(root.glob(f"*/{name}"))] if f.exists()), None)
        if f is not None:
            out.append(import_country(iso, f.parent, source=f"local folder {f.parent}"))
    if not out:
        raise FileNotFoundError(f"No interventions files ({profile.ACTIVE.interventions_file('XX')}) found in {root}")
    return out


def remove_country(country: str) -> None:
    iso = normalize_iso(country)
    with connect(read_only=False) as con:
        con.execute("DELETE FROM interventions WHERE country = ?", [iso])
        con.execute("DELETE FROM deputies WHERE country = ?", [iso])
        con.execute(f"DROP TABLE IF EXISTS deputies_{iso.lower()}")
        con.execute("DELETE FROM unigrams WHERE country = ?", [iso])
        con.execute("DELETE FROM vocab WHERE country = ?", [iso])
        con.execute("DELETE FROM datasets WHERE country = ?", [iso])
        con.execute("CHECKPOINT")


# ── Reading ───────────────────────────────────────────────────────────────────

def loaded() -> dict[str, dict]:
    if not DB.exists():
        return {}
    try:
        with connect() as con:
            rows = con.execute("SELECT * FROM datasets ORDER BY country").fetchall()
            names = [d[0] for d in con.description]
    except duckdb.IOException:
        return {}
    return {r[0]: {k: (str(v) if v is not None and not isinstance(v, (int, float, str)) else v)
                   for k, v in zip(names, r)} for r in rows}


def run_query(sql: str, params: list | None = None, max_rows: int = 200,
              timeout_s: float = 60.0) -> tuple[list[str], list[tuple], bool]:
    """Run SQL on a read-only, sandboxed connection. Returns (columns, rows, truncated)."""
    with connect() as con:
        timer = threading.Timer(timeout_s, con.interrupt)
        timer.start()
        try:
            cur = con.execute(sql, params or [])
            if cur.description is None:
                return [], [], False
            cols = [d[0] for d in cur.description]
            rows = cur.fetchmany(max_rows + 1)
        except duckdb.InterruptException:
            raise TimeoutError(f"Query cancelled after {timeout_s:.0f} s. Add filters or LIMIT.")
        finally:
            timer.cancel()
    return cols, rows[:max_rows], len(rows) > max_rows


def source_record(iso: str, edition: str | None) -> dict:
    """Bibliographic record of the loaded edition of a country (saved at download time; fetched
    from Dataverse when missing and it describes the same edition)."""
    f = country_dir(iso) / ".source.json"
    if f.exists():
        rec = json.loads(f.read_text(encoding="utf-8"))
        if edition is None or rec.get("edition") == edition:
            return rec
    rec = dataverse.source_record(COUNTRIES[iso][2])
    if edition is not None and rec.get("edition") != edition:
        raise RuntimeError(f"{iso}: the loaded data are version {edition}, but Dataverse now publishes "
                           f"{rec.get('edition')}. Download the country again before exporting for the explorer, "
                           f"which loads the published version.")
    country_dir(iso).mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec


def read_document(country: str, doc: str, language: str = "en") -> str:
    iso = normalize_iso(country)
    name = document_filename(doc, language)
    local = country_dir(iso) / name
    if local.exists():
        return local.read_text(encoding="utf-8")
    info = dataverse.summary(COUNTRIES[iso][2])
    f = next((f for f in info["files"] if f["filename"] == name), None)
    if f is None:
        raise FileNotFoundError(f"{name} is not part of the {iso} dataset")
    return dataverse.fetch_text(f["id"])


def jsonable(v: Any) -> Any:
    if v is None or isinstance(v, (int, float, str, bool)):
        return v
    return str(v)
