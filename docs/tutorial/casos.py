"""Runs the tutorial's studies (docs/tutorial) through the MCP server, the same path an agent uses, on the data
already downloaded, and saves each tool result as JSON. The site and the Markdown tables are built from these files.

The user's own state is not touched: libraries and the query log go to a scratch home inside OUT_DIR; the data
are only read from the real database.

    uv run --project mcp python docs/tutorial/casos.py OUT_DIR [step ...]

Needs the 16 countries downloaded (parlaibero-mcp download all). The personal names left out of the word network
(politicians named in the debate) and the aliases of the minister in step D9b are read from nombres.local.json next to
this script, which is kept out of the repository: {"exclude": [...], "minister_aliases": [...], "also_hide": [...]}.
Without it the word network keeps those names, D9b is skipped and web/datos.py refuses to write the pages. Some arguments were chosen after reading an
earlier result, as an agent would: the sessions read in step A5 are the peaks of step A4, and the checks of
step B2 follow the first uses of step B1. Those choices are noted next to each step.
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

ALL = ["AR", "BR", "CL", "CO", "CR", "DO", "EC", "ES", "GT", "MX", "PA", "PE", "PT", "PY", "SV", "UY"]
SPANISH = [c for c in ALL if c not in ("BR", "PT")]
FEM = "feminicidio+feminicídio+femicidio"
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
# Names of politicians stay out of the public repository (like docs/anexo_*.tsv): the words left out of the word
# network and the minister's aliases live in nombres.local.json next to this script, which git ignores. Without it the
# word network keeps those names and step D9b is skipped.
LOCAL = Path(__file__).with_name("nombres.local.json")
NAMES = json.loads(LOCAL.read_text(encoding="utf-8")) if LOCAL.exists() else {}
PEOPLE = NAMES.get("exclude", [])
MINISTER_ALIASES = NAMES.get("minister_aliases", [])
WEEKLY_SQL = """
WITH w AS (
  SELECT country, CAST(floor(date_diff('day', DATE '2020-03-11', date) / 7) AS INT) AS week,
         count(*) AS interventions,
         count(*) FILTER (WHERE regexp_matches(lower(text), '\\b(covid|coronavirus)')) AS covid
  FROM interventions
  WHERE dm_speech = 1 AND date BETWEEN DATE '2020-01-01' AND DATE '2020-09-30'
  GROUP BY 1, 2)
SELECT country, week, interventions, covid, round(100.0 * covid / interventions, 1) AS pct
FROM w ORDER BY 1, 2"""
SEX_SQL = """
SELECT country, sex,
       sum(n) FILTER (WHERE fold IN ('feminicidio', 'femicidio')) AS uses,
       sum(n) AS words,
       round(1e6 * coalesce(sum(n) FILTER (WHERE fold IN ('feminicidio', 'femicidio')), 0) / sum(n), 2) AS per_million
FROM unigrams
WHERE year >= 2012 AND sex IN ('F', 'M')
GROUP BY 1, 2 ORDER BY 1, 2"""
TURN_SQL = """
SELECT country, count(*) AS interventions,
       CAST(median(n_words) AS INT) AS median_words,
       CAST(quantile_cont(n_words, 0.9) AS INT) AS p90_words
FROM interventions
WHERE dm_speech = 1 AND date >= DATE '2021-01-01' AND id_dep IS NOT NULL AND id_dep <> ''
GROUP BY 1 ORDER BY median_words DESC"""
SITTINGS_SQL = """
SELECT country,
       max(date) FILTER (WHERE date < DATE '2020-03-11') AS last_before,
       min(date) FILTER (WHERE date >= DATE '2020-03-11') AS first_after,
       count(DISTINCT id_session) FILTER (WHERE date BETWEEN DATE '2020-03-11' AND DATE '2020-07-09') AS sessions_120_days
FROM interventions
WHERE date BETWEEN DATE '2019-10-01' AND DATE '2020-12-31'
GROUP BY 1 ORDER BY 1"""
MESA_SQL = """
WITH d AS (
  SELECT legislature, sex, id_dep, count(*) AS turns, sum(n_words) AS words
  FROM interventions
  WHERE country = 'MX' AND legislature IN ('LXII', 'LXIII', 'LXIV', 'LXV', 'LXVI') AND dm_speech = 1
    AND sex IN ('F', 'M') AND n_words <= 10000
  GROUP BY 1, 2, 3)
SELECT legislature, sex, count(*) AS deputies,
       count(*) FILTER (WHERE turns > 1000) AS mesa_like,
       sum(words) AS words,
       sum(words) FILTER (WHERE turns <= 1000) AS words_rest
FROM d GROUP BY 1, 2 ORDER BY 1, 2"""
LANG_SQL = """
SELECT year(date) AS year, count(*) AS interventions
FROM interventions
WHERE country = 'ES' AND dm_speech = 1 AND date >= DATE '2019-01-01'
  AND regexp_matches(lower(text), '\\b(perquè|máis)\\b')
GROUP BY 1 ORDER BY 1"""
FOUR = ["CO", "PE", "EC", "CL"]
MIGRA = "migrante*, migraci*, migratori*, inmigra*, refugiad*"
MIGRA_RX = r"\b(migrante|migraci|migratori|inmigra|refugiad)"
# a migration word and «venezolano» in the same sentence (no full stop, colon, semicolon, ? or ! between them)
SENTENCE_RX = (r"(?i)\b(migrante|migraci|migratori|inmigra|refugiad)[^.;:?!]{0,200}\bvenezolan"
               r"|\bvenezolan[^.;:?!]{0,200}\b(migrante|migraci|migratori|inmigra|refugiad)")
READINGS_SQL = """
SELECT id_int FROM interventions
WHERE country IN ('CO', 'PE', 'EC', 'CL') AND n_words > 10000 AND regexp_matches(speaker_raw, '(?i)secretari')"""
LONG_SQL = """
SELECT i.country, i.date, i.n_words, i.speaker_raw
FROM lib.library_items li
JOIN lib.libraries l ON l.id = li.library_id
JOIN interventions i ON i.country = li.country AND i.id_int = li.id_int
WHERE l.name = 'migracion_venezolana' AND i.n_words > 10000
ORDER BY 1, 2"""
SESSIONS_SQL = """
SELECT li.country, i.id_session, min(i.date) AS date, count(*) AS interventions
FROM lib.library_items li
JOIN lib.libraries l ON l.id = li.library_id
JOIN interventions i ON i.country = li.country AND i.id_int = li.id_int
WHERE l.name = 'migracion_venezolana'
GROUP BY 1, 2
QUALIFY row_number() OVER (PARTITION BY li.country ORDER BY count(*) DESC, min(i.date)) <= 3
ORDER BY 1, 4 DESC"""
LIB_YEARS_SQL = """
WITH lib AS (
  SELECT l.name AS library, li.country, year(i.date) AS year, count(*) AS items
  FROM lib.library_items li
  JOIN lib.libraries l ON l.id = li.library_id
  JOIN interventions i ON i.country = li.country AND i.id_int = li.id_int
  WHERE l.name IN ('migracion_y_venezuela', 'migracion_venezolana')
  GROUP BY 1, 2, 3),
base AS (
  SELECT country, year(date) AS year, count(DISTINCT id_session) AS sessions, count(*) AS interventions
  FROM interventions
  WHERE dm_speech = 1 AND country IN ('CO', 'PE', 'EC', 'CL') AND date >= DATE '2015-01-01'
  GROUP BY 1, 2)
SELECT n.library, b.country, b.year, b.sessions, b.interventions, coalesce(lib.items, 0) AS items,
       round(1000.0 * coalesce(lib.items, 0) / b.interventions, 2) AS per_1000
FROM base b
CROSS JOIN (VALUES ('migracion_y_venezuela'), ('migracion_venezolana')) n(library)
LEFT JOIN lib ON lib.library = n.library AND lib.country = b.country AND lib.year = b.year
ORDER BY 1, 2, 3"""
# the debates of the topic: in the sittings with three or more interventions of the library, everything between the
# first and the last, without the chair; what the library leaves out there is read to measure its coverage
CONTEXT_SQL = """
WITH items AS (
  SELECT i.country, i.id_session, i.id_int, i.intervention_order
  FROM lib.library_items li
  JOIN lib.libraries l ON l.id = li.library_id
  JOIN interventions i ON i.country = li.country AND i.id_int = li.id_int
  WHERE l.name = 'migracion_venezolana'),
debates AS (
  SELECT country, id_session, min(intervention_order) AS first, max(intervention_order) AS last
  FROM items GROUP BY 1, 2 HAVING count(*) >= 3),
outside AS (
  SELECT i.* FROM interventions i
  JOIN debates d ON i.country = d.country AND i.id_session = d.id_session
   AND i.intervention_order BETWEEN d.first AND d.last
  WHERE i.dm_speech = 1 AND NOT regexp_matches(coalesce(i.speaker_raw, ''), '(?i)presid')
    AND i.id_int NOT IN (SELECT id_int FROM items))
"""
CONTEXT_COUNT_SQL = CONTEXT_SQL + """SELECT o.country, count(DISTINCT o.id_session) AS sessions,
       (SELECT count(*) FROM items i JOIN debates d ON i.country = d.country AND i.id_session = d.id_session
        WHERE i.country = o.country) AS in_library,
       count(*) AS outside, count(*) FILTER (WHERE o.n_words >= 50) AS outside_50_words_or_more,
       count(*) FILTER (WHERE regexp_matches(o.text, '(?i)venezolan|venezuela')) AS outside_naming_venezuela
FROM outside o GROUP BY 1 ORDER BY 1"""
CONTEXT_SAMPLE_SQL = CONTEXT_SQL + """SELECT country, date, id_int, n_words, text
FROM outside
QUALIFY row_number() OVER (PARTITION BY country ORDER BY md5(id_int)) <= 20
ORDER BY 1, 2"""
# words of the debate that the definition does not contain (from G12), each tested in its chamber
NEW_WORDS = [("colchane", "CL", "colchane"), ("movilidad", "EC", "movilidad humana"), ("extranjeros", "PE", "extranjero*")]
LIB_MONTHS_SQL = """
SELECT strftime(i.date, '%Y-%m') AS month, count(*) AS interventions, count(DISTINCT i.id_session) AS sessions
FROM lib.library_items li
JOIN lib.libraries l ON l.id = li.library_id
JOIN interventions i ON i.country = li.country AND i.id_int = li.id_int
WHERE l.name = 'previdencia'
GROUP BY 1 ORDER BY 1"""

STEPS = [
    # ---- A. «feminicidio»: how a concept enters sixteen chambers
    ("A1_counter", "term_counter", {"terms": FEM, "max_turn_words": 10000}),
    ("A2_ngram", "ngram_viewer", {"terms": FEM, "split_by_country": True, "date_from": "2000", "smoothing": 1,
                                  "max_turn_words": 10000}),
    ("A2_ngram_svg_es", "ngram_viewer", {"terms": FEM, "countries": ["MX", "BR", "CL", "PE", "EC", "CO"],
                                         "split_by_country": True, "date_from": "2000", "smoothing": 1,
                                         "max_turn_words": 10000, "chart_path": str(OUT / "img" / "feminicidio_es.svg"),
                                         "title": "«feminicidio» en seis parlamentos", "language": "es", "overwrite": True}),
    ("A2_ngram_svg_en", "ngram_viewer", {"terms": FEM, "countries": ["MX", "BR", "CL", "PE", "EC", "CO"],
                                         "split_by_country": True, "date_from": "2000", "smoothing": 1,
                                         "max_turn_words": 10000, "chart_path": str(OUT / "img" / "feminicidio_en.svg"),
                                         "title": "“femicide” in six parliaments", "language": "en", "overwrite": True}),
    *[(f"A4_sessions_{c}", "term_frequency", {"pattern": FEM, "by": "session", "countries": [c], "max_turn_words": 10000,
                                              "max_rows": 5}) for c in ALL],
    # the peak sessions of A4 that open the debate of a bill: read who spoke and what was on the floor
    *[(f"A5_session_{s}", "get_session", {"id_session": s, "max_rows": 400})
      for s in ["GT0030024", "PE0060031", "AR0190005", "PA0040593", "UY0070168"]],
    ("A6_sex_sql", "query_sql", {"sql": SEX_SQL}),
    ("A7_iberia", "ngram_viewer", {"terms": "violencia de género+violência de género, violência doméstica+violencia doméstica, "
                                            "feminicidio+feminicídio", "countries": ["ES", "PT"], "split_by_country": True,
                                   "date_from": "1996", "smoothing": 1}),
    ("A8_colloc_mx_early", "collocations", {"pattern": "feminicidio*", "countries": ["MX"], "date_to": "2011",
                                            "max_turn_words": 10000, "top": 15}),
    ("A8_colloc_mx_late", "collocations", {"pattern": "feminicidio*", "countries": ["MX"], "date_from": "2016",
                                           "max_turn_words": 10000, "top": 15}),
    # ---- B. the pandemic: one event, sixteen floors
    ("B1_counter", "term_counter", {"terms": "coronavirus+covid*", "date_from": "2019-06-01"}),
    # the three first uses of B1 that come before the outbreak or before the disease had its name
    *[(f"B2_kwic_{c}", "kwic", {"pattern": r"\b(covid|coronavirus)", "regex": True, "countries": [c],
                                "date_from": "2019-06-01", "order": "oldest", "n": 3, "width": 70})
      for c in ["EC", "SV", "GT"]],
    # after reading B2: the next uses, past the false positives
    ("B2b_kwic_EC", "kwic", {"pattern": r"\b(covid|coronavirus)", "regex": True, "countries": ["EC"],
                             "date_from": "2020-01-01", "order": "oldest", "n": 2, "width": 70}),
    ("B2b_kwic_GT", "kwic", {"pattern": r"\b(covid|coronavirus)", "regex": True, "countries": ["GT"],
                             "date_from": "2020-01-22", "order": "oldest", "n": 2, "width": 70}),
    ("B3_weekly", "query_sql", {"sql": WEEKLY_SQL, "max_rows": 2000}),
    # B3 has empty weeks: when did each chamber stop sitting, and when did it come back?
    ("B3b_sittings", "query_sql", {"sql": SITTINGS_SQL}),
    ("B4_library", "library_create", {"name": "pandemia", "countries": ALL, "terms": "coronavirus+covid+pandemia",
                                      "min_occurrences": 2, "event_dates": {c: "2020-03-11" for c in ALL},
                                      "days_before": 30, "days_after": 120, "exclude_chair": True, "label": "COVID-19",
                                      "description": "Pandemia: 30 días antes y 120 después de la declaración de la OMS"}),
    ("B5_describe", "library_describe", {"name": "pandemia"}),
    # library_describe (B5) warns that long turns hold 58 % of Mexico's words here: hence max_turn_words
    ("B6_dist_es", "distinctive_words", {"field": "country", "a": "ES", "library": "pandemia", "countries": SPANISH,
                                         "max_turn_words": 10000, "top": 15}),
    ("B6_dist_pe", "distinctive_words", {"field": "country", "a": "PE", "library": "pandemia", "countries": SPANISH,
                                         "max_turn_words": 10000, "top": 15}),
    ("B6_dist_pt_br", "distinctive_words", {"field": "country", "a": "PT", "b": "BR", "library": "pandemia",
                                            "max_turn_words": 10000, "top": 15}),
    ("B7_voice_lib", "share_of_voice", {"library": "pandemia", "by": "sex", "per": "all", "max_turn_words": 10000}),
    ("B7_voice_all", "share_of_voice", {"by": "sex", "per": "all", "date_from": "2020-02-10", "date_to": "2020-07-09",
                                        "exclude_chair": True, "max_turn_words": 10000}),
    # ---- C. voice and seats
    ("C1_year", "share_of_voice", {"by": "sex", "per": "year", "date_from": "2010-01-01", "exclude_chair": True,
                                   "max_turn_words": 10000}),
    ("C2_recent", "share_of_voice", {"by": "sex", "per": "all", "date_from": "2021-01-01", "exclude_chair": True,
                                     "max_turn_words": 10000}),
    ("C3_recent_turns", "share_of_voice", {"by": "sex", "per": "all", "unit": "turns", "date_from": "2021-01-01",
                                           "exclude_chair": True, "max_turn_words": 10000}),
    ("C4_mx_legislature", "share_of_voice", {"countries": ["MX"], "by": "sex", "per": "legislature",
                                             "date_from": "2012-09-01", "exclude_chair": True, "max_turn_words": 10000}),
    ("C5_mx_words", "distinctive_words", {"field": "sex", "a": "F", "b": "M", "countries": ["MX"],
                                          "date_from": "2018-09-01", "date_to": "2021-08-31", "exclude_chair": True,
                                          "max_turn_words": 10000, "top": 15}),
    ("C6_es_words", "distinctive_words", {"field": "sex", "a": "F", "b": "M", "countries": ["ES"],
                                          "date_from": "2019-12-03", "exclude_chair": True, "top": 15}),
    # C6 brings Catalan and Galician words: interventions with «perquè» (Catalan) or «máis» (Galician), year by year
    ("C6b_es_languages", "query_sql", {"sql": LANG_SQL}),
    # C5 shows the Mesa's formulas among the women's words: leave out the deputies who speak like the Mesa
    ("C8_mx_mesa", "query_sql", {"sql": MESA_SQL}),
    # from the day after the constitutive sitting: on 2023-08-17 the register holds both the outgoing and the incoming
    # deputies, and those of the outgoing legislature would count as members of the new one
    ("C7_es_party", "share_of_voice", {"countries": ["ES"], "by": "party", "per": "all", "date_from": "2023-08-18",
                                       "exclude_chair": True}),
    # ---- D. interpretive frames: the pension reform
    ("D1_library", "library_create", {"name": "previdencia", "countries": ["BR"],
                                      "terms": "reforma da previdência+previdência social+aposentadoria*",
                                      "min_occurrences": 2, "date_from": "2016-12-01", "date_to": "2019-11-30",
                                      "exclude_chair": True,
                                      "description": "Reforma da Previdência: da PEC 287/2016 à EC 103/2019"}),
    # the libraries are tables too: the library month by month, with SQL
    ("D1b_months", "query_sql", {"sql": LIB_MONTHS_SQL}),
    ("D2_words", "cooccurrence_network", {"library": "previdencia", "layout": "clusters", "exclude": PEOPLE,
                                          "output_dir": str(OUT / "redes" / "palavras"), "overwrite": True}),
    ("D3_period", "distinctive_words", {"field": "period", "a": "2016-2017", "b": "2019-2019", "library": "previdencia",
                                        "exclude_chair": True, "top": 25}),
    ("D4_pt_psl", "distinctive_words", {"field": "party", "a": "PT", "b": "PSL", "library": "previdencia",
                                        "date_from": "2019-01-01", "exclude_chair": True, "top": 25}),
    *[(f"D5_colloc_{p}", "collocations", {"pattern": "privilégio*", "library": "previdencia", "party": p, "top": 12,
                                          "min_count": 3}) for p in ["PT", "PSOL", "PSL", "NOVO"]],
    ("D6_phrase_party", "term_frequency", {"pattern": "combater privilégios+combater os privilégios", "by": "party",
                                           "library": "previdencia"}),
    ("D7_kwic", "kwic", {"pattern": "combater privilégios", "library": "previdencia", "party": "PT", "n": 6, "width": 90}),
    ("D8_actors", "comention_network", {"library": "previdencia", "entities": INSTITUTIONS, "groups": LEFT_RIGHT,
                                        "min_co": 8, "layout": "clusters", "output_dir": str(OUT / "redes" / "atores"),
                                        "overwrite": True}),
    ("D9_mentions", "mention_network", {"library": "previdencia", "groups": LEFT_RIGHT, "target_scope": "speakers",
                                        "min_mentions": 3, "top_n": 40, "layout": "rings",
                                        "output_dir": str(OUT / "redes" / "mencoes"), "overwrite": True}),
    # the most mentioned "deputy" of the left in D9 shares a name with the Minister of the Economy: declare the
    # minister as an external actor (matched first) and build the network again
    ("D9b_minister", "mention_network", {"library": "previdencia", "groups": LEFT_RIGHT, "target_scope": "both",
                                         "external_actors": [{"name": "Ministro da Economia", "role": "ministro",
                                                              "aliases": MINISTER_ALIASES + ["Ministro da Economia"]}],
                                         "min_mentions": 3, "top_n": 40, "layout": "rings",
                                         "output_dir": str(OUT / "redes" / "mencoes_ministro"), "overwrite": True}),
    # ---- E. beyond the tools: own indicators, export, cite
    ("E1_turns", "query_sql", {"sql": TURN_SQL}),
    ("E2_export", "export_result", {"sql": WEEKLY_SQL, "path": str(OUT / "pandemia_semanal.parquet"), "format": "parquet",
                                    "overwrite": True}),
    ("E3_lib_export", "library_export", {"name": "pandemia", "folder": str(OUT / "explorador"), "table_format": "csv",
                                         "overwrite": True}),
    ("E4_log", "query_log", {"last": 200, "methods_path": str(OUT / "metodos.md"), "overwrite": True}),
    *[(f"E5_cite_{c}", "how_to_cite", {"country": c}) for c in ALL],
    # ---- the basics, on the home page
    ("Z1_list", "list_countries", {}),
    ("Z2_coverage", "coverage", {"countries": ["AR", "ES", "UY", "MX"], "by": "year", "date_from": "2022-01-01",
                                 "date_to": "2023-12-31"}),
    # ---- G. a library from scratch (the guide): Venezuelan migration in four chambers since 2015
    ("G1_terms", "term_counter", {"terms": MIGRA + ", desplazad*, venezolan*+venezuela", "countries": FOUR,
                                  "date_from": "2015-01-01"}),
    # G1 brings three surprises, read before defining anything: «desplazados» in Colombia, «venezolanos» alone, and
    # three and a half times more «migrantes» in Ecuador than in Chile
    ("G2_kwic_desplazad", "kwic", {"pattern": "desplazad*", "countries": ["CO"], "date_from": "2015-01-01", "n": 12,
                                   "width": 90}),
    ("G2_kwic_venez", "kwic", {"pattern": "venezolan*", "countries": FOUR, "date_from": "2015-01-01", "n": 16,
                               "width": 90}),
    ("G2_kwic_migrante_EC", "kwic", {"pattern": "migrante*", "countries": ["EC"], "date_from": "2015-01-01", "n": 12,
                                     "width": 90}),
    *[(f"G3_migra_{k}", "library_create", {"name": name, "countries": FOUR, "terms": MIGRA, "min_occurrences": k,
                                           "date_from": "2015-01-01", "exclude_chair": True, "label": "migración",
                                           "description": f"Migración: {k} o más menciones, desde 2015"})
      for k, name in [(1, "migracion_1"), (2, "migracion"), (3, "migracion_3")]],
    ("G4_once", "library_combine", {"name": "una_mencion", "a": "migracion_1", "b": "migracion", "op": "difference"}),
    ("G4_kwic_once", "kwic", {"pattern": MIGRA_RX, "regex": True, "library": "una_mencion", "n": 20, "width": 90}),
    ("G5_venez", "library_create", {"name": "venezuela", "countries": FOUR, "terms": "venezolan*+venezuela",
                                    "date_from": "2015-01-01", "exclude_chair": True, "label": "Venezuela",
                                    "description": "Venezuela o venezolanos, desde 2015"}),
    ("G6_combine", "library_combine", {"name": "migracion_y_venezuela", "a": "migracion", "b": "venezuela",
                                       "op": "intersection",
                                       "description": "Migración (2 o más menciones) y Venezuela en la misma intervención"}),
    ("G7_describe", "library_describe", {"name": "migracion_y_venezuela"}),
    # where and how Venezuela is named in each sampled intervention (all of them talk of migration twice or more)
    *[(f"G8_kwic_{c}", "kwic", {"pattern": r"\b(venezolan|venezuela)", "regex": True,
                                "library": "migracion_y_venezuela", "countries": [c], "n": 20, "width": 90})
      for c in FOUR],
    # read by hand, of the 20 sampled in each chamber, those that talk about Venezuelan migrants: CL 16, CO 17, PE 18,
    # EC 6 (G10, same test: CL 20, CO 20, PE 20, EC 19); the samples depend on seed=1 and on the library, so a new
    # edition of the data needs a new reading
    # after reading G8: in Ecuador most interventions speak of Ecuadorians abroad and name Venezuela elsewhere (a list
    # of countries, a treaty), so the second definition asks for both words in the same sentence
    ("G9_sentence", "library_create", {"name": "migracion_venezolana", "countries": FOUR, "terms": SENTENCE_RX,
                                       "regex": True, "date_from": "2015-01-01", "exclude_chair": True,
                                       "label": "migración venezolana",
                                       "description": "Una palabra de migración y «venezolano» en la misma frase, "
                                                      "desde 2015"}),
    *[(f"G10_kwic_{c}", "kwic", {"pattern": SENTENCE_RX, "regex": True, "library": "migracion_venezolana",
                                 "countries": [c], "n": 20, "width": 60}) for c in FOUR],
    # library_describe (G9) gives Ecuador's long turns 87.6 % of the part's words: reading them, the eight are reports
    # read out by the secretary (they go), and Peru's two are speeches of the executive (they stay)
    ("G10a_long", "query_sql", {"sql": LONG_SQL}),
    ("G10b_remove", "library_edit", {"name": "migracion_venezolana", "action": "remove", "sql": READINGS_SQL}),
    ("G10c_note", "library_edit", {"name": "migracion_venezolana", "action": "note", "id_ints": ["CO006001600043"],
                                   "note": "Proposición que crea la comisión accidental de seguimiento a la crisis "
                                           "migratoria venezolana",
                                   "tags": ["hito", "comisión accidental"]}),
    ("G10d_describe", "library_describe", {"name": "migracion_venezolana"}),
    ("G11_years", "query_sql", {"sql": LIB_YEARS_SQL, "max_rows": 200}),
    # G11: one year can be one session; and Colombia's part almost vanishes from 2022: what is said of Venezuela then
    ("G11b_sessions", "query_sql", {"sql": SESSIONS_SQL}),
    ("G11c_kwic_CO", "kwic", {"pattern": "venezolan*", "countries": ["CO"], "date_from": "2022-07-20", "n": 15,
                              "width": 80}),
    *[(f"G12_dist_{c}", "distinctive_words", {"field": "library", "a": "migracion_venezolana", "countries": [c],
                                              "date_from": "2015-01-01", "exclude_chair": True,
                                              "max_turn_words": 10000, "top": 40}) for c in FOUR],
    # G12 brings «gc898» and «corrigió» among Colombia's words: how many interventions use them?
    ("G12b_kwic_gc898", "kwic", {"pattern": "gc898", "library": "migracion_venezolana", "n": 5, "width": 70}),
    ("G13_rebuild", "library_rebuild", {"name": "migracion_venezolana"}),
    ("G14_export", "library_export", {"name": "migracion_venezolana", "folder": str(OUT / "explorador_migracion"),
                                      "table_format": "csv", "overwrite": True}),
    ("G15_delete_dry", "library_delete", {"name": "migracion_1"}),
    *[(f"G15_delete_{n}", "library_delete", {"name": n, "confirm": True}) for n in ["migracion_1", "migracion_3",
                                                                                    "una_mencion"]],
    # ---- beyond the keywords: what the library leaves out (the guide's § 9)
    ("G16_context", "query_sql", {"sql": CONTEXT_COUNT_SQL}),
    # G16b, G17c and G18b read by hand in three classes: talks about Venezuelan migrants and names them anywhere in the
    # intervention / about migration without saying from where / another topic or procedure. The text shown is cut (900
    # characters here, a kwic line there): those whose full text names Venezuela are read whole. Counts in
    # web/datos.py, FUERA; a new edition needs a new reading
    ("G16b_context_sample", "query_sql", {"sql": CONTEXT_SAMPLE_SQL, "max_rows": 100, "max_cell_chars": 900}),
    *[step for name, c, terms in NEW_WORDS for step in [
        (f"G17_{name}", "library_create", {"name": name, "countries": [c], "terms": terms, "date_from": "2015-01-01",
                                           "exclude_chair": True}),
        (f"G17b_{name}_fuera", "library_combine", {"name": f"{name}_fuera", "a": name, "b": "migracion_venezolana",
                                                   "op": "difference"}),
        (f"G17c_{name}_kwic", "kwic", {"pattern": terms, "library": f"{name}_fuera", "n": 20, "width": 120}),
        # a ceiling that needs no reading: speaking of Venezuelan migrants takes naming them
        (f"G17d_{name}_venez", "library_combine", {"name": f"{name}_venez", "a": f"{name}_fuera", "b": "venezuela",
                                                   "op": "intersection"})]],
    ("G18_lost", "library_combine", {"name": "perdidas", "a": "migracion_y_venezuela", "b": "migracion_venezolana",
                                     "op": "difference"}),
    ("G18b_lost_kwic_CL", "kwic", {"pattern": r"\b(venezolan|venezuela)", "regex": True, "library": "perdidas",
                                   "countries": ["CL"], "n": 20, "width": 120}),
    *[(f"G19_delete_{n}", "library_delete", {"name": n, "confirm": True})
      for name, _, _ in NEW_WORDS for n in (name, f"{name}_fuera", f"{name}_venez")],
    ("G19_delete_perdidas", "library_delete", {"name": "perdidas", "confirm": True}),
]


async def main() -> None:
    (OUT / "img").mkdir(exist_ok=True)
    (OUT / "json").mkdir(exist_ok=True)
    only = set(sys.argv[2:])
    if not NAMES:
        print(f"  ! {LOCAL.name} not found: the word network keeps personal names and D9b_minister is skipped")
    for key, tool, args in STEPS:
        if only and not any(key.startswith(o) for o in only):
            continue
        if key == "D9b_minister" and not MINISTER_ALIASES:
            continue
        if key.startswith("G") and tool in ("library_create", "library_combine"):   # a rerun starts clean
            try:
                await server._server.call_tool("library_delete", {"name": args["name"], "confirm": True})
            except Exception:
                pass
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
