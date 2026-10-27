"""Reading the themes of a word network: the dossier rebuilds what the network read and proves it, cuts passages
that hold the theme's words and draws the same sample with the same seed; the codebook check finds invented quotes
and ids outside the library, and measures agreement. On the synthetic store of test_cooccurrence.py."""
import csv
import json
from pathlib import Path

import pytest

from parlaibero_mcp import analysis, cooccurrence as co, library, networks, themes
from test_cooccurrence import br_store, corpus  # noqa: F401  (the synthetic store and its corpus)


@pytest.fixture()
def words(br_store, tmp_path):
    lid, _ = library.resolve("lib")
    f = analysis.Filters(None, library=lid, library_name="lib")
    r = networks.cooccurrence_network(f, vocabulary=50, neighbours=4, expressions=False,
                                      output_dir=str(tmp_path / "net"))
    themes._CACHE.clear()
    return next(x for x in r["files"] if x.endswith("_words.json"))


def _net(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_dossier_rebuilds_what_the_network_read(words):
    net = _net(words)
    r = themes.theme_dossier(words)
    assert "equal the network's" in r["self_check"] and r["N"] == net["N"]
    assert [t["theme"] for t in r["themes"]] == [t["id"] + 1 for t in net["themes"]]   # the page's numbers
    assert {Path(x).name for x in r["files"]} == {"lib_dossier.json", "lib_dossier.md", "lib_codebook.json"}
    one = themes.theme_dossier(words, theme=1)["theme"]
    t0 = net["themes"][0]
    terms = {x["term"] for x in t0["terms"]}
    rank = [net["metadata"][str(x["id"])]["id_int"] for x in t0["reading"][:themes.PROTOTYPES]]
    assert [x["id_int"] for x in one["reading"][:len(rank)]] == rank                # BM25's first, then the sample
    assert len(one["reading"]) == len(rank) + 10
    for x in one["reading"]:
        if x["hits"]:                                                               # every passage holds the theme
            assert all(set(co.tokenize(p)) & terms for p in x["passages"])
        assert all(len(p) <= themes.PASSAGE_CHARS + 4 for p in x["passages"])
    assert one["stability"]["label"] in ("robust", "moderate", "fragile") and one["stability"]["runs"] == 20
    assert one["interventions"]["touching"] == t0["interventions"]
    assert one["groups"] and all(g["interventions"] >= 5 for g in one["groups"])
    assert one["concentration"]["flags"]                                            # the store has one session


def test_passages_are_cut_from_the_record():
    text = "Primeira frase sem nada. (Palmas.) A reforma da previdência e o déficit; depois outra coisa qualquer."
    ps, n = themes.passages(text, ["previdencia", "deficit"], k=2, window=3)
    assert n == 2 and len(ps) == 1 and "previdência e o déficit" in ps[0] and ps[0].startswith("… ")
    ps, n = themes.passages(text, ["ausente"], k=2, window=3)
    assert n == 0 and ps == [" ".join(text.split()[:6]) + " …"]


def test_dossier_is_deterministic_and_refuses_what_it_cannot_prove(words, tmp_path):
    a = [x["id_int"] for x in themes.theme_dossier(words, theme=1)["theme"]["reading"]]
    themes._CACHE.clear()
    assert [x["id_int"] for x in themes.theme_dossier(words, theme=1)["theme"]["reading"]] == a
    themes.theme_dossier(words)
    themes.theme_dossier(words)                                     # same content: no FileExistsError
    with pytest.raises(ValueError, match="between 1 and"):
        themes.theme_dossier(words, theme=99)
    with pytest.raises(ValueError, match="ABSOLUTE"):
        themes.theme_dossier("net/lib_words.json")
    other = tmp_path / "x.json"
    other.write_text('{"nodes": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="not a word network"):
        themes.theme_dossier(str(other))
    net = _net(words)
    net["themes"][0]["interventions"] += 1                          # as if the library had changed
    changed = tmp_path / "changed_words.json"
    changed.write_text(json.dumps(net), encoding="utf-8")
    with pytest.raises(ValueError, match="changed since the network was built"):
        themes.theme_dossier(str(changed))


def test_an_empty_codebook_is_not_ok(words):
    r = themes.check_codebook(themes.theme_dossier(words)["codebook"], sample_size=10)
    assert r["errors"] == [] and r["complete"] is False and r["ok"] is False


def _filled(words, tmp_path):
    r = themes.theme_dossier(words)
    cb = json.loads(Path(r["codebook"]).read_text(encoding="utf-8"))
    one = themes.theme_dossier(words, theme=1)["theme"]
    item = next(x for x in one["reading"] if x["hits"])
    quote = " ".join(item["passages"][0].replace("…", "").split()[:8])
    outside = next(f"BR{k:06d}" for k, d in enumerate(corpus()) if not d["lib"])
    e1, e2 = cb["themes"][0], cb["themes"][1]
    e1.update(verdict="theme", label="Pensions", definition="The pension system and its reform.",
              anchors=[{"id_int": item["id_int"], "quote": quote},
                       {"id_int": item["id_int"], "quote": "estas palavras não aparecem em intervenção alguma"},
                       {"id_int": outside, "quote": "qualquer coisa dita fora da biblioteca"}],
              frames=[{"name": "Deficit", "problem": "The system spends more than it collects.", "groups": ["PT"],
                       "anchors": [{"id_int": item["id_int"], "quote": quote, "stance": "affirms"}]}])
    e2.update(verdict="artefact", definition="Procedure.")
    Path(r["codebook"]).write_text(json.dumps(cb, ensure_ascii=False), encoding="utf-8")
    return r["codebook"]


def test_codebook_check_finds_invented_quotes_and_draws_a_blind_sample(words, tmp_path):
    cb = _filled(words, tmp_path)
    r = themes.check_codebook(cb, sample_size=20)
    assert not r["ok"] and r["complete"] is True                               # both themes have a verdict
    assert r["anchors"]["verbatim"] == 2 and r["anchors"]["not found"] == 1 and r["anchors"]["outside_library"] == 1
    assert any("not in the library" in e for e in r["errors"]) and any("not found" in e for e in r["errors"])
    assert r["codable"] == {"themes": [1], "frames": ["Deficit"]} and r["verdicts"]["artefact"] == 1
    assert r["sample"]["size"] == 20 and len(r["sample"]["strata"]) >= 5
    names = {Path(x).name for x in r["files"]}
    stem = Path(cb).stem
    assert {f"{stem}_sample.csv", f"{stem}_key.csv", f"{stem}_coding_human.csv", f"{stem}_coding_agent.csv"} <= names
    with open(Path(cb).with_name(f"{stem}_sample.csv"), encoding="utf-8") as fh:
        head = next(csv.reader(fh))
    assert head == ["sample", "id_int", "date", "passage"]                     # blind: no group, no theme
    again = themes.check_codebook(cb, sample_size=20)
    assert set(again["sample"]["kept"]) >= {f"{stem}_coding_human.csv"}         # never clobbered without overwrite
    c = json.loads(Path(cb).read_text(encoding="utf-8"))
    c["themes"][0]["verdict"] = "tema"
    c["themes"][0]["frames"][0]["anchors"][0]["stance"] = "supports"
    Path(cb).write_text(json.dumps(c), encoding="utf-8")
    errs = themes.check_codebook(cb, sample_size=20)["errors"]
    assert any("verdict must be one of" in e for e in errs)


def test_links_between_themes():
    net = {"nodes": [{"theme": 0}, {"theme": 0}, {"theme": 1}, {"theme": -1}],
           "edges": [{"a": 0, "b": 1, "weight": 1}, {"a": 1, "b": 2, "weight": 0.5}, {"a": 0, "b": 3, "weight": 0.25}]}
    outside, between = themes._links(net)
    assert outside[1] == {1: 0.5} and outside[2] == {0: 0.5} and outside[0] == {-1: 0.25} and 3 in outside
    assert dict(between) == {(0, 1): 0.5}                          # loose terms are not a theme


def test_the_sample_weighs_itself_and_small_groups_are_not_read():
    docs = [{"id_int": f"A{i}", "group": "big"} for i in range(100)] + \
           [{"id_int": f"S{i}", "group": f"small{i}"} for i in range(30)]
    sample, strata = themes._proportional(docs, 20, 1, key=lambda d: d["group"])
    assert len(sample) == 20 and strata["big"] == (100, 16)                 # 20 × 100/130 = 15.4, largest remainder
    assert sum(k for _, k in strata.values()) == 20 and sum(1 for g, (_, k) in strata.items() if k) == 5
    coded = [{"theme": "1" if i % 4 == 0 else "none"} for i in range(20)]
    prev = themes._prevalence(sample, coded, strata, "theme")[0]
    assert prev["library"]["wilson_95"] == [round(x, 4) for x in themes.wilson(5, 20)]   # pooled over the sample
    assert all(r["too_few"] for r in prev["by_group"] if r["coded"] < themes.MIN_GROUP_CODED)
    assert not next(r for r in prev["by_group"] if r["group"] == "big")["too_few"]


def test_the_server_tools_pass_their_arguments(words):
    from parlaibero_mcp import server as S
    one = S.theme_dossier(words, theme=2, sample=4, passages=1, window=15, stability_runs=3)["theme"]
    assert one["theme"] == 2 and one["stability"]["runs"] == 3 and len(one["reading"]) <= themes.PROTOTYPES + 4
    assert all(len(x["passages"]) == 1 for x in one["reading"])
    cb = S.theme_dossier(words)["codebook"]
    r = S.check_codebook(cb, sample_size=7, seed=3)
    assert r["sample"]["size"] == 7 and r["sample"]["seed"] == 3 and "passage" in r["sample"]["unit"]


def test_kappa_and_wilson_by_hand():
    k = themes.cohen_kappa([1, 1, 0, 0], [1, 0, 0, 0])                         # po 0.75, pe 0.5
    assert k == {"n": 4, "agreement": 0.75, "kappa": 0.5}
    lo, hi = themes.wilson(5, 10)
    assert (round(lo, 4), round(hi, 4)) == (0.2366, 0.7634)
    assert themes.cohen_kappa(["a", "a"], ["a", "a"])["kappa"] is None          # chance agreement is 1


def test_agreement_and_prevalence_from_the_two_codings(words, tmp_path):
    cb = _filled(words, tmp_path)
    r = themes.check_codebook(cb, sample_size=20)
    stem = Path(cb).stem
    with open(Path(cb).with_name(f"{stem}_key.csv"), encoding="utf-8") as fh:
        key = list(csv.DictReader(fh))
    human = [("1", "deficit", "affirms") if x["dominant_theme"] == "1" else ("none", "none", "") for x in key]
    agent = [h if i % 5 else ("none", "none", "") for i, h in enumerate(human)]     # the agent misses every fifth
    paths = {}
    for who, codes in (("human", human), ("agent", agent)):
        p = Path(cb).with_name(f"{stem}_coding_{who}.csv")
        with open(p, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["sample", "id_int", "theme", "frame", "stance", "notes"])
            for x, (t, f, s) in zip(key, codes):
                w.writerow([x["sample"], x["id_int"], t, f, s, ""])
        paths[who] = str(p)
    out = themes.check_codebook(cb, sample_size=20, human=paths["human"], agent=paths["agent"])
    want = themes.cohen_kappa([h[0] for h in human], [a[0] for a in agent])
    assert {k: out["agreement"]["theme"][k] for k in ("n", "agreement", "kappa")} == want
    prev = out["prevalence"]["human"]["theme"]
    if any(h[0] == "1" for h in human):
        row = prev[0]["by_group"][0]
        assert row["wilson_95"] == [round(x, 4) for x in themes.wilson(row["with_label"], row["coded"])]
        lib = prev[0]["library"]
        assert lib["wilson_95"] == [round(x, 4) for x in themes.wilson(lib["with_label"], lib["coded"])]
    with pytest.raises(ValueError, match="does not hold this sample"):
        themes.check_codebook(cb, sample_size=19, human=paths["human"], agent=paths["agent"])
