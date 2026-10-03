"""Tests that need neither the network nor downloaded data: `uv run --with pytest pytest`."""
import duckdb
import pytest

from parlaibero_mcp.catalog import COUNTRIES, document_filename, normalize_iso
from parlaibero_mcp.server import _search_regex


def test_catalog_has_16_countries():
    assert len(COUNTRIES) == 16
    assert all(doi.startswith("10.7910/DVN/") for _, _, doi in COUNTRIES.values())


@pytest.mark.parametrize("given,iso", [("es", "ES"), ("España", "ES"), ("Brazil", "BR"), ("brasil", "BR")])
def test_normalize_iso(given, iso):
    assert normalize_iso(given) == iso


def test_normalize_iso_rejects_unknown():
    with pytest.raises(ValueError):
        normalize_iso("Atlantis")


def test_document_filenames():
    assert document_filename("readme", "es") == "README_es.md"
    assert document_filename("known_limitations", "en") == "known_limitations.md"
    assert document_filename("corpus_info", "pt") == "corpus_info.json"


@pytest.mark.parametrize("pattern,text,hit", [
    ("nacion", "la NACIÓN entera", True),
    ("Nación", "la nacion entera", True),
    ("golpe de estado", "un golpe\nde  Estado", True),
    ("corrupción", "anticorrupción", True),
    ("¿qué?", "dijo ¿Qué? y calló", True),
    ("50%", "subió un 50% más", True),
    ("nacion", "nacional", True),
])
def test_search_regex_matches_in_duckdb(pattern, text, hit):
    rx = _search_regex(pattern, regex=False)
    assert duckdb.sql("SELECT regexp_matches(?, ?)", params=[text, rx]).fetchone()[0] is hit


@pytest.mark.parametrize("text,hit", [("la nación.", True), ("nacional", False), ("nación", True)])
def test_whole_word(text, hit):
    rx = _search_regex("nacion", regex=False, whole_word=True)
    assert duckdb.sql("SELECT regexp_matches(?, ?)", params=[text, rx]).fetchone()[0] is hit
