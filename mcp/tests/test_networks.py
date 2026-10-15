"""Network tools: synthetic, offline tests, the Leiden parity with the explorer (when Node and the
explorer's source are present) and an opt-in regression on a real library (PARLAIBERO_REGRESSION=1).
`uv run --with pytest pytest`."""
import csv
import json
import math
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from parlaibero_mcp import analysis, leiden, library, networks, store

HEADER = store.INTERVENTION_COLUMNS


def row(iso, sess, order, date, speaker, party, text, dm=1):
    return [f"{iso}0010{sess:03d}", f"{iso}0010{sess:03d}{order:05d}", "1", "1", str(sess), date, "ordinaria",
            str(order), speaker, f"{iso}-{speaker}", speaker.title(), "F", party, "X", str(dm), text]


SV = [
    row("SV", 1, 1, "2020-01-10", "DIPUTADO UNO", "A", "La Corte Suprema y el Gobierno discutieron el presupuesto."),
    row("SV", 1, 2, "2020-01-10", "DIPUTADA DOS", "B", "El Gobierno ataca a la Corte Suprema; Eduardo Pérez lo sabe."),
    row("SV", 1, 3, "2020-01-10", "DIPUTADO TRES", "A", "Pérez y la Corte Suprema, otra vez el Gobierno."),
    row("SV", 2, 1, "2020-02-10", "DIPUTADA DOS", "B", "Presupuesto, presupuesto. </script><b>x</b> sin más."),
    row("SV", 2, 2, "2020-02-10", "DIPUTADO UNO", "C", "Habla Eduardo Pérez del presupuesto y de la Corte Suprema."),
    row("SV", 2, 3, "2020-02-10", "DIPUTADO TRES", "A", "Nada que ver con nada."),
]
ES = [
    row("ES", 1, 1, "2020-03-01", "SEÑOR UNO", "P1", "El Gobierno y la Corte Suprema, y el presupuesto del Gobierno."),
    row("ES", 1, 2, "2020-03-01", "SEÑORA DOS", "P2", "La Corte Suprema no aprueba el presupuesto."),
]


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "HOME", tmp_path)
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    monkeypatch.setattr(store, "DB", tmp_path / "parlaibero.duckdb")
    monkeypatch.setattr(store, "LIBDB", tmp_path / "bibliotecas.duckdb")
    monkeypatch.setattr(store, "LOG_DISABLED", True)
    for iso, rows in (("SV", SV), ("ES", ES)):
        folder = tmp_path / "data" / iso
        folder.mkdir(parents=True)
        with open(folder / f"{iso}_interventions.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(HEADER)
            w.writerows(rows)
        store.import_country(iso, folder, source="test", version="2.0", title=iso)
    library.create("todo", ["SV", "ES"], terms="corte, presupuesto, nada, gobierno")
    return tmp_path


ENTS = [
    {"name": "Corte", "type": "institucion", "pattern": r"corte suprema"},
    {"name": "Gobierno", "type": "institucion", "pattern": r"\bgobierno\b"},
    {"name": "presupuesto", "type": "concepto", "pattern": r"\bpresupuesto"},
    {"name": "Pérez", "type": "persona", "pattern": r"\bperez\b"},
    {"name": "Eduardo Pérez", "type": "persona", "pattern": r"eduardo perez"},
]


def F(**kw):
    lid, isos = library.resolve("todo")
    return analysis.Filters(kw.pop("countries", None), library=lid, library_name="todo", **kw)


def net(home, **kw):
    r = networks.cooccurrence_network(F(countries=kw.pop("countries", None)), kw.pop("entities", ENTS),
                                      min_co=kw.pop("min_co", 1), min_npmi=kw.pop("min_npmi", -1), formats=[], **kw)
    return r


def test_present_longest_and_exclude():
    e = [{"name": "B", "type": "persona", "pattern": r"\bpereira\b", "exclude": r"joao\s+pereira",
          "_rx": None}, {"name": "EB", "type": "persona", "pattern": r"maria\s+pereira"}]
    import re
    for x in e:
        x["_rx"] = re.compile(x["pattern"])
        x["_exc"] = re.compile(x["exclude"]) if x.get("exclude") else None
    assert networks._present("maria pereira falou", e, [0, 1]) == {"EB"}            # longest wins
    assert networks._present("joao pereira falou", e, [0, 1]) == set()               # exclude
    assert networks._present("pereira e maria pereira", e, [0, 1]) == {"B", "EB"}  # both, separately


def test_counts_npmi_and_per_country(home):
    r = net(home)
    assert set(r["networks"]) == {"SV", "ES"}                     # one network per country by default
    sv = r["networks"]["SV"]
    assert sv["N"] == 6
    edges = {(a, b): (c, p) for a, b, c, p in sv["top_edges_by_co"]}   # checked against the definition by hand
    # SV: Corte in rows 1,2,3,5 (4); Gobierno 1,2,3 (3); co = 3; N = 6
    expected = (math.log((3 / 6) / ((4 / 6) * (3 / 6)))) / (-math.log(3 / 6))
    assert edges[("Corte", "Gobierno")][0] == 3
    assert abs(edges[("Corte", "Gobierno")][1] - round(expected, 3)) < 1e-9
    # 'Eduardo Pérez' (rows 2, 5) is not counted as 'Pérez', which is only row 3
    nodes = {x[0]: x[2] for x in sv["top_nodes_by_strength"]}
    assert nodes["Eduardo Pérez"] == 2
    assert r["networks"]["ES"]["N"] == 2


def test_npmi_is_one_when_always_together():
    assert networks._npmi(5, 5, 5, 5) == 1.0
    assert networks._npmi(1, 1, 1, 10) == pytest.approx(1.0)


def test_groups_and_bias(home):
    r = net(home, countries=["SV"], groups={"g1": ["a"], "g2": ["b"]})
    s = r["networks"]["SV"]
    assert s["groups"]["N_by_group"] == {"g1": 3, "g2": 2, "rest": 1}
    assert s["groups"]["unmapped_labels"] == {"C": 1}             # reported, not guessed
    with pytest.raises(ValueError, match="two contrast groups"):
        net(home, groups={"a": ["A"], "b": ["B"], "c": ["C"]})


def test_auto_mode_builds_nothing(home, tmp_path):
    r = networks.cooccurrence_network(F(), None, output_dir=str(tmp_path / "out"))
    assert r["mode"] == "auto" and r["candidates"]
    assert not (tmp_path / "out").exists()


def test_auto_candidates_skip_forms_of_address_and_notes(home):
    names = {c["name"] for c in networks.cooccurrence_network(F(), None)["candidates"] if "name" in c}
    assert "Corte Suprema" in names
    assert not any(n.lower().startswith(("el ", "la ", "de ")) for n in names)


def test_invalid_pattern_and_relative_dir(home):
    with pytest.raises(ValueError, match="RE2"):
        net(home, entities=[{"name": "x", "pattern": r"(?<=a)b"}, {"name": "y", "pattern": "c"}])
    with pytest.raises(ValueError, match="absolute"):
        networks.cooccurrence_network(F(), ENTS, min_co=1, output_dir="relative/dir")


def test_html_escapes_and_self_check(home, tmp_path):
    ents = ENTS + [{"name": "script", "type": "concepto", "pattern": r"sin mas"}]
    r = networks.cooccurrence_network(F(countries=["SV"]), ents, min_co=1, min_npmi=-1,
                                      output_dir=str(tmp_path / "o"), kwic_per_entity=5)
    page = Path([f for f in r["files"] if f.endswith(".html")][0]).read_text(encoding="utf-8")
    assert "</script><b>" not in page                                # the speech's </script> cannot close the tag
    data = json.loads(page.split('type="application/json">')[1].split("</script>")[0])
    assert sum(e["co"] for e in data["edges"]) == r["networks"]["SV"]["checksums"]["sum_co"]
    # a tampered page fails the self-check and is removed
    res = json.loads(Path([f for f in r["files"] if f.endswith(".json")][0]).read_text())
    bad = tmp_path / "o" / "bad.html"
    bad.write_text(page.replace('"co":3', '"co":30', 1), encoding="utf-8")
    with pytest.raises(RuntimeError, match="Self-check"):
        networks._self_check(bad, res)
    assert not bad.exists()


def test_leiden_is_deterministic():
    edges = [[0, 1, 3], [1, 2, 3], [0, 2, 3], [3, 4, 3], [4, 5, 3], [3, 5, 3], [2, 3, 0.5]]
    a = leiden.communities(6, edges, seed=7)
    assert a == leiden.communities(6, edges, seed=7)
    assert a["community"][0] == a["community"][1] == a["community"][2] != a["community"][3]
    assert leiden.communities(4, [])["community"] == [0, 1, 2, 3]


EXPLORER_LEIDEN = Path(os.environ.get("EXPLORER_LEIDEN", Path.home() / "Dropbox/Apps/diaries_explorer/explorer_src/"
                                      "worker/35a_engine__leiden.js"))


@pytest.mark.skipif(not (shutil.which("node") and EXPLORER_LEIDEN.exists()), reason="needs node and the explorer source")
def test_leiden_parity_with_the_explorer(tmp_path):
    import random
    rng = random.Random(42)
    cases = []
    for _ in range(25):
        n = rng.choice([5, 12, 30, 80, 200])
        p = rng.choice([0.03, 0.1, 0.3])
        edges = [[u, v, rng.choice([1, 2, 3, 0.5, 7.25])] for u in range(n) for v in range(u + 1, n) if rng.random() < p]
        cases.append({"n": n, "edges": edges, "seed": rng.randint(1, 2**31), "res": rng.choice([0.5, 1.0, 1.5])})
    (tmp_path / "cases.json").write_text(json.dumps(cases))
    runner = tmp_path / "run.mjs"
    runner.write_text("""import fs from 'node:fs'; import vm from 'node:vm'; globalThis.R2 = {};
vm.runInThisContext(fs.readFileSync(process.argv[2], 'utf8'));
const cs = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
process.stdout.write(JSON.stringify(cs.map((c) => { const r = R2.leiden.comunidades({n: c.n, aristas: c.edges}, {semilla: c.seed, resolucion: c.res});
  return {com: Array.from(r.comunidad), q: r.calidad, it: r.iteraciones}; })));""")
    js = json.loads(subprocess.run(["node", str(runner), str(EXPLORER_LEIDEN), str(tmp_path / "cases.json")],
                                   capture_output=True, text=True, check=True).stdout)
    for c, j in zip(cases, js):
        p = leiden.communities(c["n"], c["edges"], c["res"], c["seed"])
        assert p["community"] == j["com"] and p["iterations"] == j["it"] and abs(p["quality"] - j["q"]) < 1e-12


# ── opt-in regression on the user's own data ──────────────────────────────────
ANNEX = Path(os.environ.get("PARLAIBERO_ANNEX", Path(__file__).parents[2] / "docs" / "anexo_golpe_8jan.tsv"))


@pytest.mark.skipif(os.environ.get("PARLAIBERO_REGRESSION") != "1" or not ANNEX.exists(),
                    reason="opt-in: PARLAIBERO_REGRESSION=1, the golpe_8jan library and the local annex")
def test_regression_golpe_8jan():
    ents = [{"name": r["name"], "type": r["type"], "pattern": r["pattern"], "exclude": r["exclude"] or None}
            for r in csv.DictReader(open(ANNEX, encoding="utf-8"), delimiter="\t")]
    lid, _ = library.resolve("golpe_8jan")
    f = analysis.Filters(None, "2023-01-08", None, exclude_chair=True, library=lid, library_name="golpe_8jan")
    s = networks.cooccurrence_network(f, ents, {"izq": ["PT", "PSOL", "PCdoB", "PV", "REDE", "PSB", "PDT"],
                                                "pl": ["PL", "NOVO"]}, formats=[])["networks"]["BR"]
    assert (s["N"], s["edges"], s["parameters"]["min_co"]) == (2949, 181, 25)
    assert s["checksums"]["sum_co"] == 18986 and s["checksums"]["sum_co_izq"] == 12054
    assert s["checksums"]["sum_co_pl"] == 5453 and round(s["checksums"]["sum_npmi"], 3) == 34.517
