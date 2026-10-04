"""Libraries on a tiny synthetic corpus: no network, no downloaded data. `uv run --with pytest pytest`.

The compatibility with the explorer itself is checked against its real engine by the explorer's own
test (diaries_explorer/explorer_src/test/ida_y_vuelta_mcp.mjs), with published CSV files."""
import csv
import json

import pytest

from parlaibero_mcp import analysis, library, store
from parlaibero_mcp.server import _F

HEADER = store.INTERVENTION_COLUMNS
ROWS = [
    # id_session, id_int, legislature, period, number, date, type, order, speaker_raw, id_dep, name, sex, party,
    # district, dm_speech, text
    ["SV0010001", "SV001000100000", "1", "1", "1", "2020-03-01", "ordinaria", "0", "", "", "", "", "", "", "0",
     "Sumario de la sesión. Aborto en el orden del día."],
    ["SV0010001", "SV001000100001", "1", "1", "1", "2020-03-01", "ordinaria", "1", "PRESIDENTE", "d1", "Ana Pérez",
     "F", "A", "X", "1", "Tiene la palabra el diputado."],
    ["SV0010001", "SV001000100002", "1", "1", "1", "2020-03-01", "ordinaria", "2", " DIPUTADO GÓMEZ ", "d2",
     "Luis Gómez", "M", "B", "X", "1", "El aborto, el aborto y otra vez el aborto:\nun debate necesario."],
    ["SV0010002", "SV001000200001", "1", "1", "2", "2020-06-10", "ordinaria", "1", "MINISTRA", "", "", "", "", "",
     "1", "Una sola mención del aborto en un informe."],
    ["SV0010002", "SV001000200002", "1", "1", "2", "2020-06-10", "ordinaria", "2", "DIPUTADA RUIZ", "d3",
     "Eva Ruiz", "F", "A", "Y", "1", "Hablemos de presupuesto, no de otra cosa."],
    ["SV0010003", "SV001000300001", "1", "1", "3", "2021-01-15", "ordinaria", "1", "DIPUTADA RUIZ", "d3",
     "Eva Ruiz", "F", "A", "Y", "1", "El aborto no es delito, dijo; el aborto terapéutico existe."],
]
SOURCE = {"titulo": "ParlaIbero-SV: Parliamentary Speeches from El Salvador (2018-2025)",
          "autores": [{"nombre": "Rodrigues-Silveira, Rodrigo", "afiliacion": "Universidad de Salamanca"},
                      {"nombre": "Martínez Osorio, Sofía Anabel", "afiliacion": "Universidad de Salamanca"}],
          "anio": 2026, "editor": "Harvard Dataverse", "doi": "10.7910/DVN/MUJU6A",
          "url": "https://doi.org/10.7910/DVN/MUJU6A", "version_cita": "V2", "edition": "2.0",
          "licencia": "CC BY 4.0", "licencia_url": "http://creativecommons.org/licenses/by/4.0",
          "cita": 'Rodrigues-Silveira, Rodrigo; Martínez Osorio, Sofía Anabel, 2026, "ParlaIbero-SV: Parliamentary '
                  'Speeches from El Salvador (2018-2025)", https://doi.org/10.7910/DVN/MUJU6A, Harvard Dataverse, V2'}


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "HOME", tmp_path)
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    monkeypatch.setattr(store, "DB", tmp_path / "parlaibero.duckdb")
    monkeypatch.setattr(store, "LIBDB", tmp_path / "bibliotecas.duckdb")
    monkeypatch.setattr(store, "LOG_DISABLED", True)
    folder = tmp_path / "data" / "SV"
    folder.mkdir(parents=True)
    with open(folder / "SV_interventions.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        w.writerows(ROWS)
    (folder / ".source.json").write_text(json.dumps(SOURCE), encoding="utf-8")
    store.import_country("SV", folder, source="test", version="2.0", title="SV")
    return tmp_path


def _ids(name):
    return sorted(r[0] for r in store.run_query(
        "SELECT l.id_int FROM lib.library_items l JOIN lib.libraries b ON b.id = l.library_id WHERE b.name = ?",
        [name])[1])


def test_row_n_is_the_record_number(home):
    rows = store.run_query("SELECT row_n, id_int FROM interventions ORDER BY row_n")[1]
    assert [r[1] for r in rows] == [r[1] for r in ROWS] and [r[0] for r in rows] == list(range(1, len(ROWS) + 1))


def test_row_check_refuses_a_different_file(home, monkeypatch):
    monkeypatch.setattr(store, "csv_id_sequence_digest", lambda p: (len(ROWS), "not the same"))
    with pytest.raises(RuntimeError, match="row numbers"):
        store.import_country("SV", home / "data" / "SV", version="2.0")


def test_create_with_min_occurrences_and_library_filter(home):
    r = library.create("aborto", ["SV"], terms="aborto*", min_occurrences=2)
    assert _ids("aborto") == ["SV001000100002", "SV001000300001"]      # 3 and 2 uses; the 1-use rows stay out
    assert r["parts"]["SV"]["edition"] == "2.0"
    f = _F(library="ABORTO")                                            # names are case-insensitive
    counts = analysis.term_counter("aborto", f)["terms"][0]
    assert counts["occurrences"] == 5 and counts["interventions"] == 2
    assert not f.unigram_ok()                                           # the index cannot see a library


def test_whole_chamber_is_refused(home):
    with pytest.raises(ValueError, match="whole chamber"):
        library.create("todo", ["SV"])


def test_event_window(home):
    r = library.create("evento", ["SV"], terms="aborto*", event_dates={"SV": "2020-03-01"}, days_before=5,
                       days_after=5)
    d = r["parts"]["SV"]["definitions"][0]
    assert (d["date_from"], d["date_to"], d["event"]["date"]) == ("2020-02-25", "2020-03-06", "2020-03-01")
    assert _ids("evento") == ["SV001000100002"]


def test_remove_note_rebuild(home):
    library.create("aborto", ["SV"], terms="aborto*")
    assert len(_ids("aborto")) == 3
    library.remove("aborto", ["SV001000200001"])
    library.note("aborto", "SV001000100002", "a favor", ["posición"])
    r = library.rebuild("aborto")["by_country"]["SV"]
    assert r["items_now"] == 2 and r["lost"] == 0                       # the exclusion survives the rebuild
    note = store.run_query("SELECT note, tags FROM lib.library_items WHERE id_int = 'SV001000100002'")[1][0]
    assert note == ("a favor", '["posición"]')


def test_combine(home):
    library.create("a", ["SV"], terms="aborto*")
    library.create("b", ["SV"], terms="presupuesto, aborto*", date_from="2020-06-01")
    assert _ids(library.combine("i", "a", "b", "intersection")["library"]) == ["SV001000200001", "SV001000300001"]
    assert _ids(library.combine("d", "a", "b", "difference")["library"]) == ["SV001000100002"]


def test_export_for_the_explorer_and_back(home, tmp_path):
    library.create("aborto", ["SV"], terms="aborto*", speech_only=False, date_to="2020-12-31")
    library.note("aborto", "SV001000100002", "nota", ["t"])
    r = library.export("aborto", str(tmp_path / "out"), table_format="csv")
    bundle = json.loads(open(r["files"][0], encoding="utf-8").read())
    assert list(bundle) == ["format", "exported_at", "corpus", "fuente", "collection", "items"]
    assert bundle["format"] == "2replib/1" and bundle["corpus"] == "Diarios_SV"
    assert bundle["fuente"]["cita"] == SOURCE["cita"]                   # the explorer recognises its own source
    assert bundle["fuente"]["cita_corta"] == "Rodrigues-Silveira y Martínez Osorio (2026), ParlaIbero-SV, doi:10.7910/DVN/MUJU6A"
    items = {it["speech_id"]: it for it in bundle["items"]}
    assert sorted(items) == [1, 3, 4]                                    # row numbers, in file order
    assert items[1]["speaker"] == "SUMARIO" and items[1]["rep_name"] == "Sin identificar"
    assert items[3]["speaker"] == "DIPUTADO GÓMEZ" and items[3]["note"] == "nota" and items[3]["tags"] == ["t"]
    assert r["table"]["rows"] == 3
    back = library.import_files([r["index"]])
    assert back["library"] == "aborto (importada)" and back["by_country"]["SV"]["imported"] == 3
    assert _ids("aborto (importada)") == _ids("aborto")


def test_import_reports_what_does_not_match(home, tmp_path):
    library.create("aborto", ["SV"], terms="aborto*")
    path = library.export("aborto", str(tmp_path / "out"))["files"][0]
    bundle = json.loads(open(path, encoding="utf-8").read())
    bundle["items"][0]["speaker"] = "OTRO"
    bundle["items"].append({"speech_id": 999})
    (tmp_path / "bad.2replib").write_text(json.dumps(bundle), encoding="utf-8")
    r = library.import_files([str(tmp_path / "bad.2replib")], name="mala")["by_country"]["SV"]
    assert (r["imported"], r["mismatched"], r["not_in_data"]) == (2, 1, 1)
    bundle["fuente"]["version"] = "V1"
    (tmp_path / "old.2replib").write_text(json.dumps(bundle), encoding="utf-8")
    with pytest.raises(RuntimeError, match="other interventions"):
        library.import_files([str(tmp_path / "old.2replib")], name="vieja")


def test_stale_library_is_refused(home):
    library.create("aborto", ["SV"], terms="aborto*")
    with store.library_connection() as con:
        con.execute("UPDATE lib.library_parts SET edition = '1.0'")
    with pytest.raises(RuntimeError, match="library_rebuild"):
        _F(library="aborto")


def test_slug_like_the_explorer():
    assert library.slug("Aborto: España · Perú (2020)") == "aborto_espana_peru_2020"
    assert library.slug("con") == "con_"
