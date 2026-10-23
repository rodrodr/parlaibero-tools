"""Runs the tutorial's examples (docs/tutorial/TUTORIAL.md) through the MCP server, the same path an agent uses,
on the data already downloaded, and saves each tool result as JSON next to the charts and network pages.

The user's own state is not touched: libraries and the query log go to a scratch home inside OUT_DIR; the data
are only read from the real database.

    uv run --project mcp python docs/tutorial/ejemplos.py OUT_DIR

Needs BR, ES, AR and MX downloaded (download_country). The tutorial quotes trimmed excerpts of these results;
quotations of speech leave out the speaker's name (public examples use concepts, institutions and roles).
"""
import asyncio
import json
import sys
import time
from pathlib import Path

from parlaibero_mcp import server, store

OUT = Path(sys.argv[1]).expanduser().resolve()
OUT.mkdir(parents=True, exist_ok=True)
store.HOME = OUT / "home"                      # libraries, query log and caches; DB and DATA stay the real ones
store.HOME.mkdir(exist_ok=True)
store.LIBDB = store.HOME / "bibliotecas.duckdb"
store.LOG_DISABLED = False

LIB = "tutorial_previdencia"
LEFT_RIGHT = {"esquerda": ["PT", "PSOL", "PCdoB", "PDT", "PSB", "REDE"],
              "direita": ["PSL", "PL", "PR", "PP", "DEM", "PSC", "PRB", "REPUBLICANOS", "NOVO", "PTB", "PATRIOTA"]}
INSTITUTIONS = [
    {"name": "INSS", "type": "institucion", "pattern": r"\binss\b|instituto nacional do seguro social"},
    {"name": "Congresso Nacional", "type": "institucion", "pattern": r"\bcongresso nacional\b"},
    {"name": "STF", "type": "institucion", "pattern": r"\bstf\b|supremo tribunal federal"},
    {"name": "TCU", "type": "institucion", "pattern": r"\btcu\b|tribunal de contas da uniao"},
    {"name": "Ministério da Fazenda / Economia", "type": "institucion", "pattern": r"ministerio da (fazenda|economia)"},
    {"name": "Banco Central", "type": "institucion", "pattern": r"\bbanco central\b"},
    {"name": "Centrais sindicais", "type": "institucion", "pattern": r"centrais sindicais|central sindical"},
    {"name": "Bancos", "type": "institucion", "pattern": r"\bbancos\b|\bbanqueiros\b"},
    {"name": "Forças Armadas", "type": "institucion", "pattern": r"forcas armadas|\bmilitares\b"},
    {"name": "Tribunais e Judiciário", "type": "institucion", "pattern": r"\bjudiciario\b|\btribunais\b"},
]
# Public examples use concepts, institutions and roles, not named people (docs/PLAN_redes.md §6): the names that the
# library's vocabulary brings in are left out with `exclude`, which is how a user drops terms after reading the themes.
PEOPLE = ["temer", "michel temer", "michel", "loures", "joesley", "joesley batista", "rodrigo", "rodrigo maia", "maia",
          "guedes", "paulo guedes", "bolsonaro", "jair bolsonaro", "lula", "dilma", "meirelles", "henrique meirelles",
          "marun", "cunha", "eduardo cunha", "aecio", "jucá", "moro", "sérgio moro", "arthur", "lira", "rogério marinho",
          "marinho", "samuel moreira", "samuel", "moreira", "ministro paulo guedes", "governo temer", "governo bolsonaro", "saud"]
LIB_SQL = (f"SELECT year(i.date) AS ano, count(*) AS intervencoes FROM interventions i "
           f"WHERE i.id_int IN (SELECT it.id_int FROM lib.library_items it JOIN lib.libraries l "
           f"ON l.id = it.library_id WHERE l.name = '{LIB}') GROUP BY 1 ORDER BY 1")

EXAMPLES = [
    # 1. what is there
    ("01_list_countries", "list_countries", {}),
    ("02_coverage_br", "coverage", {"countries": ["BR"], "by": "year", "date_from": "2015-01-01"}),
    ("03_coverage_ar_es", "coverage", {"countries": ["AR", "ES"], "by": "year", "date_from": "2022-01-01",
                                       "date_to": "2023-12-31"}),
    ("04_documentation_br", "get_documentation", {"country": "BR", "document": "known_limitations", "language": "es"}),
    # 2. words over time
    ("05_ngram_fake_news", "ngram_viewer", {"terms": "fake news", "countries": ["BR", "ES", "AR", "MX"],
                                            "split_by_country": True, "date_from": "2010-01-01", "smoothing": 1,
                                            "chart_path": str(OUT / "img" / "ngram_fake_news_es.svg"),
                                            "title": "«fake news» en cuatro parlamentos", "language": "es",
                                            "overwrite": True}),
    ("05b_ngram_fake_news_en", "ngram_viewer", {"terms": "fake news", "countries": ["BR", "ES", "AR", "MX"],
                                                "split_by_country": True, "date_from": "2010-01-01", "smoothing": 1,
                                                "chart_path": str(OUT / "img" / "ngram_fake_news_en.svg"),
                                                "title": "“fake news” in four parliaments", "language": "en",
                                                "overwrite": True}),
    ("06_term_counter", "term_counter", {"terms": "reforma da previdência", "countries": ["BR"]}),
    # 3. who speaks
    ("07_share_of_voice_es", "share_of_voice", {"countries": ["ES"], "by": "sex", "per": "legislature",
                                                "date_from": "2004-01-01", "exclude_chair": True}),
    # 4. what distinguishes two groups
    ("08_distinctive_pt_pl", "distinctive_words", {"field": "party", "a": "PT", "b": "PL", "countries": ["BR"],
                                                   "date_from": "2023-01-01", "date_to": "2025-12-31",
                                                   "exclude_chair": True, "top": 15}),
    # 5. a library and reading in context
    ("09_library_create", "library_create", {"name": LIB, "countries": ["BR"],
                                             "terms": "reforma da previdência+previdência social+aposentadoria*",
                                             "min_occurrences": 2, "date_from": "2016-12-01",
                                             "date_to": "2019-11-30", "exclude_chair": True,
                                             "description": "Reforma da Previdência: da PEC 287/2016 à EC 103/2019"}),
    ("10_library_describe", "library_describe", {"name": LIB}),
    ("11_kwic", "kwic", {"pattern": "regra de transição", "library": LIB, "n": 6, "width": 80}),
    ("12_collocations", "collocations", {"pattern": "privilégio*", "library": LIB, "top": 15}),
    ("13_distinctive_library", "distinctive_words", {"field": "library", "a": LIB, "countries": ["BR"],
                                                     "date_from": "2016-12-01", "date_to": "2019-11-30",
                                                     "exclude_chair": True, "top": 15}),
    # 6. the three networks
    ("14_cooccurrence", "cooccurrence_network", {"library": LIB, "layout": "clusters", "exclude": PEOPLE,
                                                 "output_dir": str(OUT / "redes" / "palavras"), "overwrite": True}),
    ("15_comention", "comention_network", {"library": LIB, "entities": INSTITUTIONS, "groups": LEFT_RIGHT, "min_co": 8,
                                           "layout": "clusters", "output_dir": str(OUT / "redes" / "atores"),
                                           "overwrite": True}),
    ("16_mention", "mention_network", {"library": LIB, "groups": LEFT_RIGHT, "target_scope": "speakers",
                                       "min_mentions": 3, "top_n": 40, "layout": "rings",
                                       "output_dir": str(OUT / "redes" / "mencoes"), "overwrite": True}),
    # 7. reproduce and cite
    ("17_query_sql", "query_sql", {"sql": LIB_SQL}),
    ("18_export_result", "export_result", {"sql": LIB_SQL, "path": str(OUT / "previdencia_por_ano.csv"),
                                           "overwrite": True}),
    ("19_library_export", "library_export", {"name": LIB, "folder": str(OUT / "explorador"), "overwrite": True}),
    ("20_query_log", "query_log", {"last": 30, "methods_path": str(OUT / "metodos.md"), "overwrite": True}),
    ("21_how_to_cite", "how_to_cite", {"country": "BR"}),
]


async def main() -> None:
    (OUT / "img").mkdir(exist_ok=True)
    (OUT / "json").mkdir(exist_ok=True)
    only = set(sys.argv[2:])
    for key, tool, args in EXAMPLES:
        if only and key not in only:
            continue
        t0 = time.time()
        try:
            r = await server._server.call_tool(tool, args)
            text, error = (r.content[0].text if r.content else ""), bool(r.is_error)
        except Exception as e:          # the server raises ToolError for invalid arguments
            text, error = str(e), True
        try:
            data = json.loads(text)
        except ValueError:
            data = text
        (OUT / "json" / f"{key}.json").write_text(json.dumps({"tool": tool, "arguments": args, "error": error,
                                                              "result": data}, ensure_ascii=False, indent=1,
                                                             default=str), encoding="utf-8")
        print(f"{time.time() - t0:6.1f} s  {key}{'  ERROR: ' + text[:200] if error else ''}", flush=True)


asyncio.run(main())
