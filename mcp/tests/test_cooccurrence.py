"""Word co-occurrence network: parity with the Diarios Explorer, whose own engine (keyness, expressions, partition,
leiden, coocurrencia) runs here in Node on a synthetic corpus with a stub of its SQL layer; and the MCP tool on the
synthetic store of test_networks.py."""
from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from parlaibero_mcp import cooccurrence as co

EXPLORER = Path(os.environ.get("EXPLORER_SRC", Path.home() / "Dropbox/Apps/diaries_explorer/explorer_src"))
NEEDS_NODE = pytest.mark.skipif(not (shutil.which("node") and (EXPLORER / "worker/35b_engine__coocurrencia.js").exists()),
                                reason="needs node and the explorer source")

# ── a synthetic Portuguese corpus with topics, expressions, lists and stage directions ─────────────────────────────
TOPICS = [
    ["previdência", "aposentadoria", "reforma", "trabalhadores", "contribuição", "benefício", "idade", "regime",
     "servidores", "déficit", "seguridade", "pensão"],
    ["juros", "banco", "inflação", "dívida", "mercado", "crédito", "taxa", "economia", "investimento", "câmbio",
     "fiscal", "superávit"],
    ["segurança", "violência", "polícia", "crime", "armas", "presídios", "facções", "homicídios", "tráfico",
     "milícias", "penas", "delegacias"],
    ["escola", "professores", "universidade", "ensino", "alunos", "educação", "creches", "pesquisa", "bolsas",
     "currículo", "merenda", "vagas"],
]
TOPIC_EXPRS = [["reforma da previdência", "regime geral de previdência"], ["taxa de juros", "banco central"],
               ["segurança pública", "crime organizado"], ["ensino médio"]]
EXPRS = [e for x in TOPIC_EXPRS for e in x]
FILLER = ["o", "a", "de", "da", "do", "que", "não", "para", "com", "uma", "os", "nos", "senhor", "presidente",
          "governo", "país", "brasil", "deputado", "vamos", "aqui", "hoje", "estado", "todos", "dois", "mil", "2019"]
PARTIES = ["PT", "PL", "PSOL", "MDB", "NOVO", None, "", "Sin identificar"]


def _doc(rng: random.Random, topics: list[int]) -> str:
    words = []
    for _ in range(rng.randint(15, 90)):
        r = rng.random()
        if r < 0.45:
            words.append(rng.choice(TOPICS[rng.choice(topics)]))
        elif r < 0.52:
            words.append(rng.choice(TOPIC_EXPRS[rng.choice(topics)] if rng.random() < 0.8 else EXPRS))
        else:
            words.append(rng.choice(FILLER))
        if rng.random() < 0.12:
            words[-1] += rng.choice([",", ".", ";", " —", "!", "?"])
    t = " ".join(words)
    if rng.random() < 0.2:
        t += " (Palmas.) " + " ".join(rng.choice(FILLER) for _ in range(5))
    if rng.random() < 0.15:
        t += "\nVOTARAM SIM OS SENHORES DEPUTADOS JOÃO DA SILVA E MARIA\n" + rng.choice(TOPICS[topics[0]])
    if rng.random() < 0.1:
        t += "      tabela      " + rng.choice(EXPRS)
    if rng.random() < 0.1:
        t = t.replace("ã", "ã")                   # a decomposed accent
    return t[0].upper() + t[1:]


def corpus(seed: int = 7, n: int = 700):
    rng = random.Random(seed)
    docs = []
    for k in range(n):
        lib = k % 2 == 0
        topics = [rng.choice([0, 1])] if lib and rng.random() < 0.7 else [rng.randrange(4)]
        if rng.random() < 0.3:
            topics.append(rng.randrange(4))
        docs.append({"id": 1000 + k, "speech": _doc(rng, topics), "party": rng.choice(PARTIES), "lib": lib,
                     "speaker": f"S{k % 37}", "rep_name": None})
    return docs


def expression_rows(texts) -> list:
    """Package rows [forma, mostrar, n_tokens, n_palabras, frecuencia, …] with the corpus frequencies."""
    forms = [co.fold(e) for e in EXPRS]
    rows = [[f, (e if e != f else 0), len(f.split()), 0, 0, 0, 0, 0, 0] for f, e in zip(forms, EXPRS)]
    ix = co.ExpressionIndex(rows, "BR")
    for i, n in ix.count(texts).items():
        rows[i][4] = n
    return rows


RUNNER = r"""import fs from 'node:fs'; import vm from 'node:vm';
const [E, fx] = [process.argv[2], JSON.parse(fs.readFileSync(process.argv[3], 'utf8'))];
const W = E + '/worker/';
globalThis.R2 = {}; globalThis.N_ = (s) => s; globalThis.__ = (s, ...a) => String(s).replace(/\{(\d+)\}/g, (_, i) => a[+i]);
for (const f of ['08_engine__py__core.js','09_engine__py__json.js','10_engine__py__re.js','12_engine__py__heap.js',
  '14_engine__generated__constantes.js','15_engine__generated__vacias.js','04_worker__transformar.js']) vm.runInThisContext(fs.readFileSync(W + f, 'utf8'));
const byId = new Map(fx.docs.map((d) => [d.id, d]));
const varint = (v) => { const b = []; do { b.unshift(v & 0x7f); v = Math.floor(v / 128); } while (v > 0);
  for (let i = 0; i < b.length - 1; i++) b[i] |= 0x80; return b; };
R2.sql = {
  filas(bd, sql, p = []) {
    if (sql.includes('FROM expresiones')) return fx.expr.map((r, k) => ({id: k + 1, forma: r[0], mostrar: r[1] === 0 ? r[0] : r[1], frecuencia: r[4], intervenciones: 3}));
    if (sql.startsWith('SELECT id, speaker, rep_name, speech FROM speeches')) return p.filter((i) => byId.has(i)).map((i) => byId.get(i));
    if (sql.startsWith('SELECT id, party FROM speeches')) return p.filter((i) => byId.has(i)).map((i) => ({id: i, party: byId.get(i).party}));
    if (sql.startsWith('SELECT id, date, speaker')) return p.map((i) => ({id: i, date: null, speaker: null, rep_name: null, party: null, session_type: null}));
    throw new Error('unexpected SQL ' + sql);
  },
  valor(bd, sql) {
    if (sql.includes("key = 'pais'")) return fx.country;
    if (sql.includes("key = 'expresiones'")) return null;
    if (sql.includes('_data WHERE id = 1')) return Uint8Array.from([...varint(1), ...varint(fx.corpus_tokens)]);
    throw new Error('unexpected SQL ' + sql);
  },
  tuplas(bd, sql, p = []) { return p.filter((t) => fx.reference[t] !== undefined).map((t) => [t, fx.reference[t]]); },
  ejecutar() {}, columna() { return []; },
};
R2.datos = {vacias_lengua: JSON.parse(fs.readFileSync(E + '/datos/palabras_vacias.json', 'utf8'))};
for (const f of ['34_engine__keyness.js','34a_engine__expresiones.js','35_engine__partition.js','35a_engine__leiden.js',
  '35b_engine__coocurrencia.js']) vm.runInThisContext(fs.readFileSync(W + f, 'utf8'));
const K = R2.keyness, EX = R2.expresiones, P = R2.partition;
const ix = EX.cargar({db: {}});
const out = {tok: fx.strings.map((s) => [K.tokenize(s), K.tokenize_tramos(s), P.particion_rapida(s),
  EX.unidadesTexto(ix, s), [...EX.contar(ix, [s])]]), runs: []};
(async () => {
  const ids = fx.docs.filter((d) => d.lib).map((d) => d.id);
  for (const o of fx.options) {
    const ctx = {db: {}, sqlite3: {}, nucleo: {pais: fx.country}};
    const lex = await P.keynessColeccion(ctx, ids, Object.assign({solo_discurso: false}, {limit: 2000, limit_negative: 200, min_freq: 5}));
    const red = await R2.coocurrencia.red(ctx, ids, Object.assign({solo_discurso: false}, o));
    out.runs.push({lex: lex.terms.map((t) => ({term: t.term, display: t.display, freq: t.freq, freq_ref: t.freq_ref, g2: t.g2, expresion: !!t.expresion})),
      ntok: lex.metrics.tokens, red});
  }
  process.stdout.write(JSON.stringify(out));
})().catch((e) => { console.error(e); process.exit(1); });
"""

OPTIONS = [
    {"vocabulario": 40},
    {"vocabulario": 60, "unidad": "fragmento", "fragmento": 7, "resolucion": 1.6, "semilla": 3},
    {"vocabulario": 50, "expresiones": False, "vecinos": 4, "excluir": ["Previdência", "brasil"]},
    {"vocabulario": 250, "resolucion": 0.6},
]
PY_OPTIONS = {"vocabulario": "vocabulary", "unidad": "unit", "fragmento": "fragment", "resolucion": "resolution",
              "semilla": "seed", "vecinos": "neighbours", "excluir": "exclude", "expresiones": "expressions"}


@pytest.fixture(scope="module")
def explorer_run(tmp_path_factory):
    if not (shutil.which("node") and (EXPLORER / "worker/35b_engine__coocurrencia.js").exists()):
        pytest.skip("needs node and the explorer source")
    tmp = tmp_path_factory.mktemp("explorer")
    docs = corpus()
    texts = [d["speech"] for d in docs]
    reference, total = co.count_terms(texts)
    rng = random.Random(3)
    strings = [_doc(rng, [rng.randrange(4)]) for _ in range(60)] + [
        "Ação, «Câmara» dos Deputados; São Paulo!", "ão  cora̧ão", "xy z", "   ", "",
        "O SR. PRESIDENTE (Fulano de Tal) - VOTARAM SIM OS DEPUTADOS\nreforma da previdência      banco central",
        "taxa de juros do banco central e da reforma da previdência; regime geral de previdência social"]
    fx = {"docs": docs, "country": "BR", "reference": reference, "corpus_tokens": total, "expr": expression_rows(texts),
          "options": OPTIONS, "strings": strings}
    (tmp / "fx.json").write_text(json.dumps(fx, ensure_ascii=False), encoding="utf-8")
    (tmp / "run.mjs").write_text(RUNNER, encoding="utf-8")
    r = subprocess.run(["node", str(tmp / "run.mjs"), str(EXPLORER), str(tmp / "fx.json")], capture_output=True,
                       text=True, check=True)
    return fx, json.loads(r.stdout)


def test_tokens_stretches_partition_and_expressions(explorer_run):
    fx, js = explorer_run
    ix = co.ExpressionIndex(fx["expr"], "BR")
    for s, (tok, tramos, part, units, counts) in zip(fx["strings"], js["tok"]):
        assert co.tokenize(s) == tok
        assert co.tokenize_stretches(s) == tramos
        spans, excl = co.fast_partition(s)
        assert [list(x) for x in spans] == part[0] and excl == part[1]
        assert ix.units_text(s) == units
        assert [[k, v] for k, v in ix.count([s]).items()] == counts


def _lexicon(fx, ix):
    lib = [d for d in fx["docs"] if d["lib"]]
    counts, c = co.count_terms(d["speech"] for d in lib)
    lex = co.keyness(counts, c, fx["corpus_tokens"], fx["reference"], 5, 10.83, 2000, 200)
    co.add_expressions(lex, ix, [d["speech"] for d in lib], 5, 2000, 200)
    return lex


def test_lexicon_parity(explorer_run):
    fx, js = explorer_run
    lex = _lexicon(fx, co.ExpressionIndex(fx["expr"], "BR"))
    got = [(t["term"], t["freq"], t["freq_ref"], t["g2"], bool(t.get("expression"))) for t in lex["terms"]]
    want = [(t["term"], t["freq"], t["freq_ref"], t["g2"], t["expresion"]) for t in js["runs"][0]["lex"]]
    assert got == want and lex["tokens"] == js["runs"][0]["ntok"]
    assert any(t.get("expression") for t in lex["terms"])


def _same(a, b, path=""):
    """Equal, with floats to 1e-9 (log1p may differ in the last bit between V8 and the C library)."""
    if isinstance(a, float) or isinstance(b, float):
        assert a is not None and b is not None and abs(a - b) <= 1e-9 * max(1, abs(a)), path
    elif isinstance(a, dict):
        assert set(a) == set(b), (path, set(a) ^ set(b))
        for k in a:
            _same(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list):
        assert len(a) == len(b), (path, len(a), len(b))
        for k, (x, y) in enumerate(zip(a, b)):
            _same(x, y, f"{path}[{k}]")
    else:
        assert a == b, (path, a, b)


def _from_js(red):
    """The explorer's result in the MCP's keys."""
    split = lambda r: {"with_party": r["con_partido"], "words": r["palabras"],
                       "top": [{"party": x["p"], "n": x["n"], "words": x["pal"]} for x in r["lista"]],
                       "others": None if not r["otros"] else {"n": r["otros"]["n"], "words": r["otros"]["pal"],
                                                               "parties": r["otros"]["partidos"]}}
    row = lambda x: {"id": x["id"], "score": x["puntuacion"], "words": x["palabras"], "terms": x["terminos"]}
    term = lambda t: {"i": t["i"], "term": t["term"], "display": t["display"], "expression": t["expresion"],
                      "internal_strength": t["fuerza_interna"]}
    e = red["estadisticas"]
    return {
        "nodes": [{"i": n["i"], "term": n["term"], "display": n["display"], "expression": n["expresion"], "freq": n["freq"],
                   "g2_lexicon": n["g2_lexico"], "df_unit": n["df_unidad"], "df_intervention": n["df_intervencion"],
                   "theme": n["comunidad"], "strength": n["fuerza"], "degree": n["grado"]} for n in red["nodos"]],
        "edges": [{"a": x["a"], "b": x["b"], "co": x["co"], "expected": x["esperado"], "g2": x["g2"], "weight": x["fuerza"]}
                  for x in red["aristas"]],
        "themes": [{"id": t["id"], "label": t["etiqueta"], "n_terms": t["n_terminos"], "g2_lexicon": t["g2_lexico"],
                    "g2_mean": t["g2_medio"], "terms": [term(x) for x in t["terminos"]], "interventions": t["intervenciones"],
                    "pct_interventions": t["porcentaje"], "words_dominated": t["palabras_dominadas"],
                    "weight_pct": t["peso"], "internal_weight": t["peso_interno"], "parties": split(t["partidos"]),
                    "reading": [row(x) for x in t["lectura"]]} for t in red["comunidades"]],
        "loose_terms": [term(x) for x in red["sueltos"]],
        "parties": {"interventions": red["partidos"]["intervenciones"], "words_total": red["partidos"]["palabras_totales"],
                    "words_with_party": red["partidos"]["palabras_con_partido"], **split(red["partidos"])},
        "global": [row(x) for x in red["lectura"]["global"]],
        "varied": [{"theme": x["tema"], **row(x)} for x in red["lectura"]["variada"]],
        "stats": {"words_no_theme": e["palabras_sin_tema"], "pct_no_theme": e["pct_sin_tema"],
                  "interventions": e["n_intervenciones"], "units": e["n_unidades"], "tokens": e["tokens"],
                  "possible_pairs": e["pares_posibles"], "observed_pairs": e["pares_observados"], "density": e["densidad"],
                  "significant_edges": e["aristas_significativas"], "kept_edges": e["aristas_conservadas"],
                  "themes": e["n_comunidades"], "leiden_communities": e["n_comunidades_leiden"],
                  "loose_terms": e["n_sueltos"], "modularity": e["modularidad"], "quality": e["calidad"],
                  "total_weight": e["peso_total"]},
        "dropped": red["vocabulario"]["descartados"],
    }


@pytest.mark.parametrize("k", range(len(OPTIONS)))
def test_network_parity(explorer_run, k):
    fx, js = explorer_run
    run = js["runs"][k]
    o = {PY_OPTIONS[a]: {"fragmento": "fragment"}.get(v, v) if a == "unidad" else v for a, v in OPTIONS[k].items()}
    ix = co.ExpressionIndex(fx["expr"], "BR") if o.get("expressions", True) else None
    lex_terms = [{"term": t["term"], "display": t["display"], "freq": t["freq"], "g2": t["g2"],
                  "expression": t["expresion"]} for t in run["lex"]]
    docs = [{"id": d["id"], "text": d["speech"], "party": d["party"]} for d in fx["docs"] if d["lib"]]
    py = co.network(docs, lex_terms, "BR", o, ix)
    want = _from_js(run["red"])
    got = {k2: py[k2] for k2 in ("nodes", "edges", "themes", "loose_terms", "parties", "stats")}
    got["global"], got["varied"] = py["reading"]["global"], py["reading"]["varied"]
    got["dropped"] = {"vacias": py["vocabulary"]["dropped"]["stopwords"], "cifras": py["vocabulary"]["dropped"]["numbers"],
                      "excluidos": py["vocabulary"]["dropped"]["excluded"]}
    assert len(want["themes"]) >= 2 and want["stats"]["kept_edges"] > 10
    _same(got, want)


# ── the MCP tool on a store built from the same corpus ────────────────────────
@pytest.fixture()
def br_store(tmp_path, monkeypatch):
    import csv as _csv
    from parlaibero_mcp import library, store
    monkeypatch.setattr(store, "HOME", tmp_path)
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    monkeypatch.setattr(store, "DB", tmp_path / "parlaibero.duckdb")
    monkeypatch.setattr(store, "LIBDB", tmp_path / "bibliotecas.duckdb")
    monkeypatch.setattr(store, "LOG_DISABLED", True)
    folder = tmp_path / "data" / "BR"
    folder.mkdir(parents=True)
    docs = corpus()
    with open(folder / "BR_interventions.csv", "w", newline="", encoding="utf-8") as fh:
        w = _csv.writer(fh)
        w.writerow(store.INTERVENTION_COLUMNS)
        for k, d in enumerate(docs):
            w.writerow(["BR001", f"BR{k:06d}", "1", "1", "1", "2020-01-10", "ordinaria", str(k + 1), d["speaker"],
                        f"BR-{d['speaker']}", d["speaker"], "F", d["party"] or "", "X", "1", d["speech"]])
    store.import_country("BR", folder, source="test", version="2.0", title="BR")
    ids = ", ".join(f"'BR{k:06d}'" for k, d in enumerate(docs) if d["lib"])
    library.create_from_query("lib", f"SELECT id_int FROM interventions WHERE id_int IN ({ids})")
    return docs


def test_tool_matches_the_explorer_on_the_same_corpus(explorer_run, br_store, tmp_path, scripts_parse):
    from parlaibero_mcp import analysis, library, networks
    fx, js = explorer_run
    lid, _ = library.resolve("lib")
    f = analysis.Filters(None, library=lid, library_name="lib")
    r = networks.cooccurrence_network(f, vocabulary=50, neighbours=4, exclude=["Previdência", "brasil"],
                                      expressions=False, speech_only=False, output_dir=str(tmp_path / "o"))
    res = json.loads(Path([x for x in r["files"] if x.endswith(".json")][0]).read_text(encoding="utf-8"))
    want = _from_js(js["runs"][2]["red"])              # the same options, run by the explorer
    strip = lambda ns: [{k: v for k, v in n.items() if k != "display"} for n in ns]
    _same(strip(res["nodes"]), strip(want["nodes"]))
    _same([{k: v for k, v in e.items() if k not in ("source", "target")} for e in res["edges"]], want["edges"])
    _same([[x["term"] for x in t["terms"]] for t in res["themes"]], [[x["term"] for x in t["terms"]] for t in want["themes"]])
    plain = lambda p: {**p, "top": [{k: v for k, v in x.items() if k not in ("per_1000", "party_words")} for x in p["top"]]}
    _same([plain(t["parties"]) for t in res["themes"]], [t["parties"] for t in want["themes"]])
    _same([[x["score"] for x in t["reading"]] for t in res["themes"]], [[x["score"] for x in t["reading"]] for t in want["themes"]])
    assert res["lexicon"]["incoherent_terms"] == 0
    s = r["networks"]["BR"]
    assert s["themes"] and s["themes"][0]["read_first"] and s["expressions"]["reason"] == "expressions=false"
    page = Path([x for x in r["files"] if x.endswith(".html")][0]).read_text(encoding="utf-8")
    assert "Word co-occurrence network" in page and 'id="theme-select"' in page and 'id="layout"' in page
    scripts_parse([x for x in r["files"] if x.endswith(".html")][0])
    assert {Path(x).name for x in r["files"]} >= {"lib_words.html", "lib_words_nodes.csv", "lib_words_edges.csv",
                                                  "lib_words_themes.csv", "lib_words_summary.md"}
