"""Local store: downloaded files plus one DuckDB database with every imported country.

Layout (PARLAIBERO_HOME, default ~/.parlaibero):
    data/{ISO}/                 files exactly as deposited in Dataverse
    parlaibero.duckdb           tables `interventions`, `deputies`, `deputies_{iso}`, `datasets`
"""
from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

import duckdb

from . import dataverse
from .catalog import COUNTRIES, document_filename, normalize_iso

HOME = Path(os.environ.get("PARLAIBERO_HOME", Path.home() / ".parlaibero")).expanduser()
DATA = HOME / "data"
DB = HOME / "parlaibero.duckdb"

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

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS interventions (
    country VARCHAR, id_session VARCHAR, id_int VARCHAR, legislature VARCHAR,
    legislative_session VARCHAR, session_number VARCHAR, date DATE, session_type VARCHAR,
    intervention_order INTEGER, speaker_raw VARCHAR, id_dep VARCHAR, speaker_name VARCHAR,
    sex VARCHAR, party VARCHAR, district VARCHAR, dm_speech TINYINT, text VARCHAR,
    n_words INTEGER
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


SCHEMA_VERSION = "3"   # 3: n_words = letter/digit/mark tokens; unigrams + vocab tables


class NoData(RuntimeError):
    pass


@contextmanager
def connect(read_only: bool = True) -> Iterator[duckdb.DuckDBPyConnection]:
    """Read-only connections cannot reach the file system or the network: safe for user SQL."""
    with _LOCK:
        if read_only:
            if not DB.exists():
                raise NoData("No country has been downloaded yet. Use download_country first.")
            con = duckdb.connect(str(DB), read_only=True, config={"enable_external_access": False})
            # never print a progress bar: on an MCP stdio server, stdout is the protocol channel
            con.execute("SET enable_progress_bar = false")
            con.execute("SET lock_configuration = true")
        else:
            HOME.mkdir(parents=True, exist_ok=True)
            con = duckdb.connect(str(DB))
            con.execute("SET enable_progress_bar = false")
            con.execute(SCHEMA)
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
        con = duckdb.connect(str(DB), read_only=True)
        con.execute("SET enable_progress_bar = false")
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
    """Upgrade a database built by an older version: recompute n_words and the word tables."""
    done = []
    with connect(read_only=False) as con:
        isos = [r[0] for r in con.execute("SELECT country FROM datasets ORDER BY 1").fetchall()]
        for iso in isos:
            if progress:
                progress(iso)
            con.execute(f"UPDATE interventions SET n_words = {N_WORDS_SQL} WHERE country = ?", [iso])
            index_country(con, iso)
            done.append(iso)
        con.execute("CHECKPOINT")
    return done


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
    result = import_country(iso, folder, source=f"Harvard Dataverse doi:{doi} v{info['version']}",
                            version=info["version"], title=info["title"])
    result["downloaded_files"] = downloaded
    return result


def import_country(country: str, folder: Path, source: str | None = None,
                   version: str | None = None, title: str | None = None) -> dict:
    """Import {ISO}_interventions.csv and {ISO}_deputies.csv from `folder` (replacing old rows)."""
    iso = normalize_iso(country)
    folder = Path(folder).expanduser()
    inter = folder / f"{iso}_interventions.csv"
    deps = folder / f"{iso}_deputies.csv"
    if not inter.exists():
        raise FileNotFoundError(f"{inter} not found")
    read = (f"read_csv({{path}}, header=true, all_varchar=true, delim=',', quote='\"', "
            f"escape='\"', max_line_size=67108864)")
    cols = ", ".join(
        "TRY_CAST(date AS DATE)" if c == "date" else
        "TRY_CAST(intervention_order AS INTEGER)" if c == "intervention_order" else
        "TRY_CAST(dm_speech AS TINYINT)" if c == "dm_speech" else c
        for c in INTERVENTION_COLUMNS)
    words = N_WORDS_SQL
    with connect(read_only=False) as con:
        con.execute("BEGIN TRANSACTION")
        try:
            con.execute("DELETE FROM interventions WHERE country = ?", [iso])
            con.execute(f"INSERT INTO interventions SELECT {_sql_str(iso)}, {cols}, {words} "
                        f"FROM {read.format(path=_sql_str(str(inter)))}")
            con.execute("DELETE FROM deputies WHERE country = ?", [iso])
            con.execute(f"DROP TABLE IF EXISTS deputies_{iso.lower()}")
            if deps.exists():
                con.execute(f"CREATE TABLE deputies_{iso.lower()} AS SELECT * FROM "
                            f"{read.format(path=_sql_str(str(deps)))}")
                have = {r[0] for r in con.execute(f"DESCRIBE deputies_{iso.lower()}").fetchall()}
                sel = ", ".join(c if c in have else f"NULL AS {c}" for c in DEPUTY_CORE)
                con.execute(f"INSERT INTO deputies SELECT {_sql_str(iso)}, {sel} FROM deputies_{iso.lower()}")
            index_country(con, iso)
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


def import_folder(folder: str) -> list[dict]:
    """Import every {ISO}_interventions.csv found in `folder` or its immediate subfolders."""
    root = Path(folder).expanduser()
    found = sorted(set(root.glob("*_interventions.csv")) | set(root.glob("*/*_interventions.csv")))
    out = []
    for f in found:
        iso = f.name.split("_")[0].upper()
        if iso in COUNTRIES:
            out.append(import_country(iso, f.parent, source=f"local folder {f.parent}"))
    if not out:
        raise FileNotFoundError(f"No {{ISO}}_interventions.csv files found in {root}")
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
