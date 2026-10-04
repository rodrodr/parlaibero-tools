"""Collection profiles: what makes the engine serve ONE collection of corpora.

The engine (store, analysis, library) is the same for every collection; a profile says which datasets
exist, how their CSV files are read and mapped to the canonical columns, which extra columns can be
filtered and compared, where the local store lives and how libraries are named for the explorer.
ParlaIbero is the default profile. Another package (luz-mcp) defines its own and calls `activate`
before anything else: one process serves one collection.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# The 16 canonical columns of a ParlaIbero CSV, in file order.
CANONICAL = [
    "id_session", "id_int", "legislature", "legislative_session", "session_number", "date",
    "session_type", "intervention_order", "speaker_raw", "id_dep", "speaker_name", "sex",
    "party", "district", "dm_speech", "text",
]


@dataclass
class Profile:
    name: str                                   # short id: 'parlaibero', 'luz'
    title: str                                  # for people: 'ParlaIbero'
    datasets: dict[str, tuple[str, str, str]]   # code → (English name, local name, DOI)
    collection_url: str
    home_env: str                               # environment variable that moves the store
    default_home: str                           # '~/.parlaibero'
    interventions_file: Callable[[str], str] = lambda code: f"{code}_interventions.csv"
    deputies_file: Callable[[str], str | None] = lambda code: f"{code}_deputies.csv"
    delimiter: str = ","
    # SQL expression for each canonical column over the raw CSV (read all_varchar); missing → the
    # column of the same name
    column_sql: dict[str, str] = field(default_factory=dict)
    # extra columns of `interventions`: name → (SQL type, SQL expression over the raw CSV, description)
    extra_columns: dict[str, tuple[str, str, str]] = field(default_factory=dict)
    # the column of the published file that numbers its records, and the same key in the table, so
    # that row_n can be checked against an independent reading of the file
    row_key_csv: str = "id_int"
    row_key_sql: str = "id_int"
    has_sex: bool = True
    # columns usable as groups (share_of_voice, distinctive_words, term_frequency); sex is added if has_sex
    group_columns: tuple[str, ...] = ("party",)
    # the explorer's corpus name for a dataset (its libraries are kept under that name)
    explorer_corpus: Callable[[str], str] = lambda code: f"Diarios_{code}"
    explorer_name: str = "Diarios Explorer"
    explorer_url: str = "https://rodrodr.github.io/parlaibero-explorer/"
    # extra checks or tables after a dataset is imported: hook(con, code, folder)
    after_import: Callable | None = None
    package: str = "parlaibero-mcp"
    repository: str = "https://github.com/rodrodr/parlaibero-tools"

    @property
    def home(self) -> Path:
        return Path(os.environ.get(self.home_env, Path(self.default_home).expanduser())).expanduser()

    def groups(self) -> tuple[str, ...]:
        return (("sex",) if self.has_sex else ()) + tuple(self.group_columns)


def _parlaibero() -> Profile:
    from .catalog import COLLECTION_URL, PARLAIBERO
    return Profile(name="parlaibero", title="ParlaIbero", datasets=dict(PARLAIBERO),
                   collection_url=COLLECTION_URL, home_env="PARLAIBERO_HOME", default_home="~/.parlaibero")


ACTIVE: Profile = _parlaibero()


def activate(p: Profile) -> Profile:
    """Make `p` the collection this process serves. Call it before any other engine function."""
    global ACTIVE
    from . import catalog, store
    ACTIVE = p
    # the catalogue is a shared dict that every module imported by name: refill it in place
    catalog.COUNTRIES.clear()
    catalog.COUNTRIES.update(p.datasets)
    store.set_home(p.home)
    return p
