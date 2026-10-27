"""The report of a theme reading: the agent writes the prose in a spec, the engine fills every figure, takes every
quote from the codebook and checks it against the record, and renders Markdown and HTML. On the synthetic store of
test_cooccurrence.py."""
import json
import re
import string
from pathlib import Path

import pytest

from parlaibero_mcp import report, themes
from test_cooccurrence import br_store, corpus  # noqa: F401  (the synthetic store and its corpus)
from test_themes import words  # noqa: F401  (a word network built on that store)


def _quote(item):
    return " ".join(item["passages"][0].replace("…", "").split()[:8])


@pytest.fixture()
def codebook(words):
    """Every theme with a verdict: theme 1 a theme with one anchor and one frame, the others artefacts."""
    r = themes.theme_dossier(words)
    cb = json.loads(Path(r["codebook"]).read_text(encoding="utf-8"))
    items = [x for x in themes.theme_dossier(words, theme=1)["theme"]["reading"] if x["hits"]]
    a, b = items[0], next(x for x in items[1:] if x["id_int"] != items[0]["id_int"])
    for e in cb["themes"]:
        e.update(verdict="artefact", definition="Procedure.")
    cb["themes"][0].update(verdict="theme", label="Pensions: the system and its reform",
                           definition="The pension system and its reform.",
                           anchors=[{"id_int": a["id_int"], "quote": _quote(a)}],
                           frames=[{"name": "Deficit", "problem": "The system spends more than it collects.",
                                    "groups": ["PT"], "anchors": [{"id_int": b["id_int"], "quote": _quote(b),
                                                                   "stance": "affirms"}]}])
    Path(r["codebook"]).write_text(json.dumps(cb, ensure_ascii=False), encoding="utf-8")
    return {"path": r["codebook"], "theme": a, "frame": b}


def _spec(codebook, tmp_path, **change):
    """A spec filled as an agent would, written to its own file."""
    t = report.theme_report(codebook["path"], language="en", overwrite=True)
    spec = json.loads(Path(t["report"]).read_text(encoding="utf-8"))
    spec.update(title="Pensions in the chamber", lede="Theme 1 dominates {dominated:1} of the {N} interventions.",
                findings=["**Pensions** dominate {dominated_pct:1} of the library, most in {peak_year:1}."],
                next_steps=["Code the blind sample."], reader={"who": "Test", "model": "none", "date": "2026-10-27"},
                residual={"short": "Procedure", "lines": []})
    spec["themes"]["1"].update(about="The pension system.", caveat="A synthetic debate.",
                               lines=[{"text": "It is argued.", "quotes": [codebook["theme"]["id_int"]]}],
                               frames=[{"frame": "Deficit", "text": "Spending exceeds revenue.",
                                        "quotes": [codebook["frame"]["id_int"]]}])
    spec.update(change)
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    return p


def test_the_template_is_written_and_kept(codebook):
    t = report.theme_report(codebook["path"], language="en")
    p = Path(t["report"])
    assert p.name == "lib_report.json" and t["codable"] == [1] and t["artefacts"]
    tpl = json.loads(p.read_text(encoding="utf-8"))
    assert tpl["schema"] == report.SCHEMA and list(tpl["themes"]) == ["1"]
    assert tpl["_placeholders"]["{N}"] == f"{t['N']:,}"
    assert tpl["_quotable"][0]["anchors"][0]["id"] == codebook["theme"]["id_int"]
    p.write_text(json.dumps({**tpl, "title": "my text"}), encoding="utf-8")
    with pytest.raises(FileExistsError, match="may hold your text"):
        report.theme_report(codebook["path"])
    assert json.loads(p.read_text(encoding="utf-8"))["title"] == "my text"          # never clobbered


def test_a_filled_spec_is_rendered_and_every_figure_and_quote_vouched_for(codebook, words, tmp_path):
    r = report.theme_report(codebook["path"], report=str(_spec(codebook, tmp_path)))
    assert r["ok"] and r["errors"] == [] and r["quotes"] == 2 and r["placeholders_filled"] == 4
    assert {Path(x).name for x in r["files"]} == {"spec.md", "spec.html", "spec_check.json"}
    md = (tmp_path / "spec.md").read_text(encoding="utf-8")
    html = (tmp_path / "spec.html").read_text(encoding="utf-8")
    body = re.sub(r"<(style|script)>.*?</\1>", "", html, flags=re.S)
    assert "{" not in md and not re.search(r"\{[A-Za-z_]+[:}]", body)
    assert _quote(codebook["theme"]) in body and _quote(codebook["frame"]) in body
    dossier = themes.theme_dossier(words, theme=1)["theme"]
    n = json.loads(Path(words).read_text(encoding="utf-8"))["N"]
    assert f"Theme 1 dominates {dossier['interventions']['dominated']:,} of the {n:,} interventions." in md
    # every quote printed is an anchor of the codebook, and its seat line names no speaker
    quotes = re.findall(r"^> “(.+)”$", md, re.M)
    assert quotes == [_quote(codebook["theme"]), _quote(codebook["frame"])]
    seats = re.findall(r"^> `(.+)`$", md, re.M)
    assert [s.split(" · ")[0] for s in seats] == [codebook["theme"]["id_int"], codebook["frame"]["id_int"]]
    assert seats[1].endswith("affirms") and not any(re.search(r"\bS\d+\b", s) for s in seats)
    # the weight table counts are the network's: theme 1 as the dossier proves it, and the rows add up to N
    head = md.split("| Theme | Interventions | Share |")[1].split("\n\n")[0]
    rows = [[c.strip() for c in r.strip().strip("|").split("|")] for r in head.strip().splitlines()[1:]]
    assert rows[0][1] == f"{dossier['interventions']['dominated']:,}"
    assert sum(int(r[1].replace(",", "")) for r in rows) == n and rows[-2][0] == "Procedure"   # the spec's label
    assert html.count("<figure") == 3 and html.count("<table>") >= 3 and 'data-theme' in html


def test_the_three_languages_say_the_same_things():
    keys = {lang: set(L) for lang, L in report.L10N.items()}
    assert keys["es"] == keys["pt"] == keys["en"]
    fields = lambda v: sorted(f for _, f, _, _ in string.Formatter().parse(v) if f) if isinstance(v, str) else v
    for k in keys["en"]:
        if isinstance(report.L10N["en"][k], str):
            assert fields(report.L10N["es"][k]) == fields(report.L10N["pt"][k]) == fields(report.L10N["en"][k]), k


@pytest.mark.parametrize("lang", report.LANGUAGES)
def test_every_language_renders(codebook, tmp_path, lang):
    r = report.theme_report(codebook["path"], report=str(_spec(codebook, tmp_path, language=lang)))
    assert r["ok"], r["errors"]
    md = (tmp_path / "spec.md").read_text(encoding="utf-8")
    html = (tmp_path / "spec.html").read_text(encoding="utf-8")
    assert "{" not in md and f'<html lang="{lang}"' in html and _quote(codebook["frame"]) in md


def test_errors_stop_the_rendering(codebook, tmp_path):
    bad = _spec(codebook, tmp_path, lede="{dominated:7:x} {N:} {nothing}", blocks=[])
    s = json.loads(bad.read_text(encoding="utf-8"))
    s["themes"]["1"]["lines"][0]["quotes"] = ["BR999999", {"id": codebook["theme"]["id_int"], "starts": "nada disso"}]
    s["themes"]["1"]["frames"].append({"frame": "Invented", "text": "x", "quotes": []})
    bad.write_text(json.dumps(s), encoding="utf-8")
    r = report.theme_report(codebook["path"], report=str(bad))
    e = "\n".join(r["errors"])
    assert not r["ok"] and "takes 1 argument" in e and "{N:} is not a placeholder" in e
    assert "{nothing} is not a placeholder" in e and "codable theme 1 is in no block" in e
    assert "BR999999 is not an anchor here" in e and "starting 'nada disso'" in e
    assert "'Invented' is not a frame of theme 1" in e
    assert {Path(x).name for x in r["files"]} == {"spec_check.json"} and not (tmp_path / "spec.md").exists()
    assert json.loads((tmp_path / "spec_check.json").read_text(encoding="utf-8"))["ok"] is False


def test_bare_numbers_and_names_are_warned(codebook, tmp_path):
    p = _spec(codebook, tmp_path, findings=["In 1934 theme 1 had 37 speeches; Sr. Fulano Detal spoke on it."])
    r = report.theme_report(codebook["path"], report=str(p))
    w = "\n".join(r["warnings"])
    assert r["ok"] and "the number 37 is not a placeholder" in w and "1934" not in w and "number 1 " not in w
    assert "'Sr. Fulano Detal' may name a person" in w


def test_merge_and_split_must_be_resolved_first(codebook, tmp_path):
    p = _spec(codebook, tmp_path)
    cb = json.loads(Path(codebook["path"]).read_text(encoding="utf-8"))
    cb["themes"][1]["verdict"] = "merge"
    Path(codebook["path"]).write_text(json.dumps(cb), encoding="utf-8")
    with pytest.raises(ValueError, match="'merge' or 'split'"):
        report.theme_report(codebook["path"], report=str(p))


def test_the_server_tool_passes_its_arguments(codebook, tmp_path):
    from parlaibero_mcp import server as S
    t = S.theme_report(codebook["path"], language="pt", output_dir=str(tmp_path / "tpl"))
    assert Path(t["report"]).parent == tmp_path / "tpl"
    assert json.loads(Path(t["report"]).read_text(encoding="utf-8"))["language"] == "pt"
    r = S.theme_report(codebook["path"], report=str(_spec(codebook, tmp_path)))
    assert r["ok"] and r["quotes"] == 2
