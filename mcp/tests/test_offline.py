"""Tests that need neither the network nor downloaded data: `uv run --with pytest pytest`."""
import unicodedata

import duckdb
import pytest

from parlaibero_mcp import charts
from parlaibero_mcp.analysis import Filters, _NORM, _variant_count_rx
from parlaibero_mcp.catalog import COUNTRIES, document_filename, normalize_iso
from parlaibero_mcp.textutil import fold, parse_terms, search_regex, tokens


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
    ("democrati*", "la democratización", True),
])
def test_search_regex_matches_in_duckdb(pattern, text, hit):
    rx = search_regex(pattern)
    assert duckdb.sql("SELECT regexp_matches(?, ?)", params=[text, rx]).fetchone()[0] is hit


@pytest.mark.parametrize("text,hit", [("la nación.", True), ("nacional", False), ("nación", True)])
def test_whole_word(text, hit):
    rx = search_regex("nacion", whole_word=True)
    assert duckdb.sql("SELECT regexp_matches(?, ?)", params=[text, rx]).fetchone()[0] is hit


def _exact(variant: str, text: str) -> int:
    return duckdb.sql(f"SELECT len(regexp_extract_all({_NORM}, ?)) FROM (SELECT ? AS text)",
                      params=[_variant_count_rx(variant), text]).fetchone()[0]


@pytest.mark.parametrize("variant,text,n", [
    ("no", "No, no y NO.", 3),                       # consecutive repeats are all counted
    ("corrupción", "corrupcion, CORRUPCIÓN y anticorrupción", 2),
    ("golpe de estado", "golpe de Estado; golpe, de estado", 2),
    ("democrati*", "democracia, democratizar, democratización", 2),
    ("covid-19", "la covid 19 y el COVID-19", 2),
])
def test_exact_count(variant, text, n):
    assert _exact(variant, text) == n


def test_decomposed_accent_is_one_token():
    decomposed = unicodedata.normalize("NFD", "corrupção")
    assert tokens(decomposed) == ["corrupção"]
    assert fold(decomposed) == "corrupcao"
    assert _exact("corrupção", f"a {decomposed} e a corrupção") == 2


def test_parse_terms():
    assert parse_terms("a, b+c ,d*") == [
        {"label": "a", "variants": ["a"]}, {"label": "b+c", "variants": ["b", "c"]},
        {"label": "d*", "variants": ["d*"]}]
    with pytest.raises(ValueError):
        parse_terms("de*mocracia")


def test_filters_year_bounds():
    assert Filters(date_from="2000", date_to="2010").year_bounds() == (2000, 2010)
    assert Filters(date_from="2000-01-01").unigram_ok()
    assert not Filters(date_from="2000-03-15").unigram_ok()
    assert not Filters(party="PP").unigram_ok()


def test_chart_svg(tmp_path):
    series = {"a": [{"x": 2000, "y": 1.0}, {"x": 2001, "y": None}, {"x": 2002, "y": 3.0, "low": True}],
              "b": [{"x": 2000, "y": 2.0}, {"x": 2001, "y": 2.5}, {"x": 2002, "y": 2.0}]}
    p = charts.write_chart(str(tmp_path / "c.svg"), series, "T", "sub", "y", "note", "low")
    svg = open(p).read()
    assert svg.startswith("<svg") and "polyline" in svg and "hollow" in svg
    with pytest.raises(FileExistsError):
        charts.write_chart(p, series, "T", "sub", "y", "note")
    h = charts.write_chart(str(tmp_path / "c.html"), series, "T", "sub", "y", "note")
    assert "<table>" in open(h).read()
