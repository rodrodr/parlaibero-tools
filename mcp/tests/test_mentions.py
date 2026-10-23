"""mention_network on a synthetic chamber: names in both register formats, homonyms resolved by the title's
gender, terms closed by the next legislature, title complements, given names, editorial notes, vocatives,
external actors and the written files. `uv run --with pytest pytest`."""
import csv
import json
from datetime import date
from pathlib import Path

import pytest

from parlaibero_mcp import analysis, library, networks, store

HEADER = store.INTERVENTION_COLUMNS
DEP = ["id_dep", "speaker_name", "first_name", "last_name", "sex", "sex_source", "party", "parliamentary_group",
       "district", "legislature", "start_date", "end_date", "notes"]
REGISTER = [  # 'NAME SURNAME' parliamentary names, as in Brazil
    ["D1", "EDUARDO SOUZA", "", "", "M", "", "PL", "", "", "57", "2023-02-01", "", ""],
    ["D2", "MARIA SOUZA", "", "", "F", "", "PT", "", "", "57", "2023-02-01", "", ""],
    ["D3", "DR. LUIZ TAVARES", "", "", "M", "", "PP", "", "", "57", "2023-02-01", "", ""],
    ["D4", "LUIZ LIMA", "", "", "M", "", "PL", "", "", "57", "2023-02-01", "", ""],
    ["D5", "ZECA DA FEDERAL", "", "", "M", "", "PL", "", "", "57", "2023-02-01", "", ""],
    ["D6", "JOAO ANTIGO", "", "", "M", "", "PT", "", "", "56", "2019-02-01", "", ""],   # no end: closed in 2023
    ["D7", "LUIZ ANTIGO", "", "", "M", "", "PT", "", "", "56", "2019-02-01", "", ""],
]


def row(sess, order, speaker_id, name, party, text, d="2024-03-10"):
    return [f"BR0570{sess:03d}", f"BR0570{sess:03d}{order:05d}", "57", "1", str(sess), d, "ordinaria", str(order),
            name, speaker_id, name, "M", party, "X", "1", text]


ROWS = [
    row(1, 1, "D4", "LUIZ LIMA", "PL", "O deputado Eduardo Souza disse isso. A deputada Souza discorda dele. "
                                       "O deputado federal Fulano falou."),
    row(1, 2, "D1", "EDUARDO SOUZA", "PL", "Obrigado, Deputado Luiz Lima. (O Sr. Luiz Lima deixa a cadeira da "
                                           "presidência.) Concordo com o que disse o presidente Tibério ontem."),
    row(1, 3, "D2", "MARIA SOUZA", "PT", "O deputado Luiz disse algo. O deputado Joao Antigo falou."),
    row(2, 1, "D2", "MARIA SOUZA", "PT", "O deputado Eduardo Souza mentiu de novo, e o deputado Luiz Lima também."),
    row(2, 2, "D1", "EDUARDO SOUZA", "PL", "O deputado Eduardo Souza disse que a deputada Maria Souza tem razão."),
    row(3, 1, "D4", "LUIZ LIMA", "PL", "Eu digo que o sr. Tavares disse algo."),
]


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "HOME", tmp_path)
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    monkeypatch.setattr(store, "DB", tmp_path / "parlaibero.duckdb")
    monkeypatch.setattr(store, "LIBDB", tmp_path / "bibliotecas.duckdb")
    monkeypatch.setattr(store, "LOG_DISABLED", True)
    folder = tmp_path / "data" / "BR"
    folder.mkdir(parents=True)
    for name, head, rows in (("BR_interventions.csv", HEADER, ROWS), ("BR_deputies.csv", DEP, REGISTER)):
        with open(folder / name, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(head)
            w.writerows(rows)
    store.import_country("BR", folder, source="test", version="2.0", title="BR")
    library.create("camara", ["BR"], terms="deputado, deputada, presidente, eu")
    return tmp_path


def F():
    lid, _ = library.resolve("camara")
    return analysis.Filters(None, library=lid, library_name="camara")


def found(home, text, externals=()):
    full, sur, info = networks._gazetteer("BR", "2024-01-01", "2024-12-31")
    titles = {networks.fold(t) for t in networks.LEGISLATIVE_TITLES["pt"] + networks.HONORIFICS["pt"]}
    exts = [{"key": "ext:" + e, "name": e, "_aliases": [tuple(networks._TOKEN.findall(networks.fold(e)))]}
            for e in externals]
    common = networks._common_words("BR", 20000)
    ms = networks._find_mentions(networks.fold(text), date(2024, 3, 10), titles, full, sur, info, exts, common=common)
    return [(m["alias"], m["candidates"], m["kind"]) for m in ms]


def test_terms_are_closed_by_the_next_legislature(home):
    terms = {r["id_dep"]: r for r in networks._register_terms("BR")}
    assert str(terms["D6"]["e"]) == "2023-01-31"                 # the day before legislature 57 starts
    assert str(terms["D1"]["e"]) == "2999-12-31"                 # the latest legislature stays open
    assert found(home, "o deputado joao antigo falou") == []    # not in office in 2024


def test_gender_of_the_title_resolves_homonyms(home):
    m = found(home, "a deputada souza discorda dele; o deputado souza disse isso")
    assert [c for _, c, _ in m] == [["D2"], ["D1"]]


def test_given_name_after_the_surname_resolves_homonyms(home):
    full, sur, info = networks._gazetteer("BR", "2024-01-01", "2024-12-31")
    m = {"candidates": ["D1", "D2"], "title": None, "end": 0}
    assert networks._disambiguate(m, ", dona maria, votou", info, date(2024, 3, 10)) == "D2"
    assert networks._disambiguate(m, " votou", info, date(2024, 3, 10)) is None


def test_title_complement_and_given_names_are_not_surnames(home):
    assert found(home, "o deputado federal fulano falou") == []          # 'federal' is not Zeca da Federal
    assert found(home, "o deputado luiz disse algo") == []                # 'luiz' is a given name here
    assert found(home, "o deputado tavares disse algo")[0][1] == ["D3"]   # the surname of 'DR. LUIZ TAVARES'


def test_editorial_notes_and_vocatives(home):
    kinds = [k for _, _, k in found(home, "Obrigado, Deputado Luiz Lima. (O Sr. Luiz Lima deixa a cadeira.) "
                                          "Concordo com o deputado Luiz Lima.")]
    assert kinds == ["address", "editorial", "reference"]
    # the second of two coordinated vocatives
    assert [k for _, _, k in found(home, "Deputada Maria Souza e deputado Luiz Lima, escutem.")] == ["address"] * 2


def test_external_actors_are_matched_first(home):
    m = found(home, "o presidente tiberio e o deputado eduardo souza", externals=["Tibério"])
    assert m[0][1] == ["ext:Tibério"] and m[1][1] == ["D1"]


def test_honorifics_license_by_language_default(home):
    # Portuguese: 'o sr. Tavares' does not name the deputy by default (measured in Brazil); honorifics=True does
    def edges(**kw):
        r = networks.mention_network(F(), "speakers", min_mentions=1, formats=[], **kw)["networks"]["BR"]
        return r["honorifics"], {tuple(x[:2]) for x in r["edge_list"]}
    on_default, e_default = edges()
    on_forced, e_forced = edges(honorifics=True)
    assert on_default is False and ("D4", "D3") not in e_default
    assert on_forced is True and ("D4", "D3") in e_forced


def test_network_counts_and_files(home, tmp_path, scripts_parse):
    r = networks.mention_network(F(), "both", [{"name": "Tibério", "aliases": ["presidente Tibério"], "role": "President"}],
                                 min_mentions=1, output_dir=str(tmp_path / "out"), validation_sample=10, layout="rings")
    s = r["networks"]["BR"]
    found_n = s["counts"]["mentions_found"]
    assert found_n["self"] == 1 and found_n["editorial"] == 1 and found_n["address"] == 1
    res = json.loads(Path([f for f in r["files"] if f.endswith(".json")][0]).read_text())
    edges = {(e["source"], e["target"]): e["interventions"] for e in res["edges"]}
    assert edges[("D2", "D1")] == 1 and edges[("D4", "D1")] == 1 and edges[("D4", "D2")] == 1
    assert edges[("D2", "D4")] == 1 and edges[("D1", "D2")] == 1 and edges[("D1", "ext:Tibério")] == 1
    assert ("D1", "D4") not in edges                                     # the vocative is not counted
    html = Path([f for f in r["files"] if f.endswith(".html")][0]).read_text(encoding="utf-8")
    assert '<script id="network-data" type="application/json">' in html and '"layout":"rings"' in html
    assert 'id="layout"' in html and 'id="groupby"' in html
    scripts_parse([f for f in r["files"] if f.endswith(".html")][0])
    assert any(f.endswith("_validation_sample.csv") for f in r["files"])
    with pytest.raises(ValueError, match="absolute"):
        networks.mention_network(F(), output_dir="relative")


# ── opt-in regression on the user's own data ──────────────────────────────────
# The external actors live in a LOCAL file (names of politicians: kept out of the public repository), one per line:
# name<TAB>aliases separated by '|'<TAB>role
EXTERNALS = Path(__import__("os").environ.get("PARLAIBERO_EXTERNALS", Path(__file__).parents[2] / "docs" /
                                              "anexo_golpe_8jan_externos.tsv"))


@pytest.mark.skipif(__import__("os").environ.get("PARLAIBERO_REGRESSION") != "1" or not EXTERNALS.exists(),
                    reason="opt-in: PARLAIBERO_REGRESSION=1, the golpe_8jan library and the local list of externals")
def test_regression_golpe_8jan_mentions():
    lid, _ = library.resolve("golpe_8jan")
    f = analysis.Filters(None, "2023-01-08", None, exclude_chair=True, library=lid, library_name="golpe_8jan")
    ext = [{"name": r["name"], "aliases": [a for a in r["aliases"].split("|") if a], "role": r["role"]}
           for r in csv.DictReader(open(EXTERNALS, encoding="utf-8"), delimiter="\t")]
    s = networks.mention_network(f, "both", ext, groups={"izq": ["PT", "PSOL", "PCdoB", "PV", "REDE", "PSB", "PDT"],
                                                         "pl": ["PL", "NOVO"]}, formats=[])["networks"]["BR"]
    assert (s["N"], s["nodes"], s["edges"], s["reciprocity"]) == (2949, 60, 312, 0.0993)
    assert s["checksums"] == {"sum_interventions": 2408, "sum_mentions": 5112}
    assert s["ei_index"] == {"pl": -0.327, "izq": 0.582, "rest": -0.071}       # between deputies only
    found = s["counts"]["mentions_found"]
    assert (found["resolved"], found["ambiguous"], found["editorial"], found["self"]) == (7549, 10, 370, 39)


def test_silent_deputies_take_their_own_label_or_stay_out(home):
    # D3 is named (honorifics on) but never speaks anywhere: by party it takes the register's party; by sex it has
    # no label, so it stays out of the group matrix and the E-I index and is reported
    by_party = networks.mention_network(F(), "speakers", min_mentions=1, honorifics=True, formats=[])["networks"]["BR"]
    assert by_party["unlabelled"]["people"] == 0
    by_sex = networks.mention_network(F(), "speakers", group_by="sex", min_mentions=1, honorifics=True,
                                      formats=[])["networks"]["BR"]
    assert by_sex["unlabelled"]["people"] == 1 and by_sex["unlabelled"]["interventions"] == 1
    assert all("unlabelled" not in (b["from"], b["to"]) for b in by_sex["block_matrix"])
    with pytest.raises(ValueError, match="group_by"):
        networks.mention_network(F(), group_by="text; DROP TABLE x", formats=[])
