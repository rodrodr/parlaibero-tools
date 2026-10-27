# Changelog

## 0.6.1 · 2026-10-27

Reading the themes of a word network, in three tools: the engine prepares the evidence, checks the reading and
renders the report; the reading and the interpretation are the agent's. No language model is called by the server.
A patch release, so that luz-mcp's pin (`>=0.6.1,<0.7`) takes it; luz-mcp 0.5.0 offers the same three tools.

- **`theme_dossier`** reads a saved `<library>_words.json`, rebuilds the rows, text and tokens the network read and
  proves it (the interventions and every theme's interventions and dominated words must equal the file's, or it
  refuses). Per theme: core and bridge terms, linked themes, who sustains it (speakers, sessions; one of either
  with half or more is flagged), profile by year, the words each group says more inside the theme (signed G²),
  stability when Leiden is re-run on the saved graph (20 seeds, and 0.6 and 1.6 times the resolution; Jaccard over
  terms), and a reading sample: the network's first 3 by BM25, then one per group and year in turn, ordered by a
  hash of (seed, id_int), with passages cut from the record's text. Writes the dossier (JSON, Markdown) and a
  codebook template; `theme=k` returns one theme's full dossier through the tool.
- **`check_codebook`** checks the filled codebook (verdict, label, definition, anchors; frames with problem, cause,
  evaluation, remedy and the stance of each anchor: affirms, contests, cites): schema, theme numbers, and every
  anchor against the record (id in the library, quote verbatim, theme's words present). Draws a blind sample in
  proportion to the groups, with two empty coding files (a person, the agent); with both coded, Cohen's κ for
  theme, frame and stance, and each label's share by group with Wilson 95 % intervals.
- **`theme_report`** is the protocol's step 5: a report that interprets the themes for the researcher. Without a spec
  it writes a template (`<library>_report.json`, never replaced) with the quotable anchors and every placeholder and
  its value. With `report=` it checks the agent's spec:
  - errors: an unknown placeholder or stray braces; a quote that is not an anchor of that theme or frame, or is no
    longer verbatim; a codable theme missing or repeated; a frame not in the codebook; empty required text; merge or
    split verdicts; a changed network;
  - warnings: bare numbers; a missing caveat on a fragile or one-speaker theme; names after a courtesy title; theme
    words that occur in speakers' names; frames left out.

  Without errors it writes `.md` and `.html`: the seat line of every quote (never the speaker), the box on what is
  measured, what is reading and what is missing, three figures with their tables (weight, by year, by group), core
  terms, method, citation and files. A `_check.json` is written on every call. Spanish, Portuguese and English.
- `check_codebook` says what comes next (`next`): code the sample, then `theme_report`.
- Methods: `parlaibero://methods/networks` § 4 (Drawing, Outputs and Cite are now §§ 5-7), with «The report», and
  the report's files in § 6.
- Tests: `tests/test_themes.py` (the dossier equals the network on the synthetic store; passages hold the theme's
  words; samples are deterministic; invented quotes and ids outside the library are found; κ and Wilson by hand)
  and `tests/test_report.py` (the template is kept; unknown placeholders, invented quotes and missing themes stop the
  rendering; bare numbers are warned; every quote printed is an anchor; seat lines carry no speaker; the figures'
  counts are the network's; the three languages have the same strings and all render).

## 0.6.0 · 2026-10-23 · publicada en PyPI

Three network tools that are never mixed, and pages whose ink follows the data.

- **`cooccurrence_network` is now the network of WORDS** and their themes: the Diarios Explorer's method
  (`engine/coocurrencia.js`), ported line by line in `cooccurrence.py`: the library's lexicon against the rest of
  the country's corpus (signed G²), the corpus's multi-word expressions as one node (the explorer's precomputed
  tables, checked against the loaded dataset), Snowball stopwords, signed G² ≥ 10.83 with each term's k strongest
  neighbours, association strength as the weight, Leiden themes, party rates per 1,000 words and BM25 reading
  lists. `tests/test_cooccurrence.py` runs the explorer's own code in Node and compares tokens, segmentation,
  expressions, lexicon and the whole network; the tool gives the explorer's network on the same corpus.
- **The actor network is now `comention_network`** (it was `cooccurrence_network`): people and institutions only.
  `type: concepto` is refused with a pointer to `cooccurrence_network`, and the candidates no longer include the
  library's distinctive words. Calling `cooccurrence_network` with `entities` raises an error that points here.
- **Drawing** (all three pages): the zoom moves the points, not the marks, so nodes, labels, lines and arrowheads
  keep their size on screen; node radius is capped by a «node size» control (12 px by default, `max_node_size`);
  lines are thin, capped by an «edge width» control (1.5 px, `max_edge_width`), with the weight in the tooltip and
  opacity; arrowheads have a fixed size whatever the line's width; thin lines keep a wide invisible band to point at.
- **Three layouts** in every network page, switchable there and chosen with `layout`: `force`; `clusters`, each
  group as a named disc kept apart from the others; `rings`, the Diarios Explorer's centrifugal layout (rings by
  number of connections, sectors by theme, community or party), ported from `page/23_menciones_red.js`.
- **Thirty colours** for themes, communities and parties (it was 8 and gray), validated in both themes; names on
  discs, sectors and legends carry identity too.
- The side panel of every network page can be hidden («hide panel») to give the network the whole width; the page
  remembers the choice in the browser and opens the panel again when a click asks for details. Without the panel
  the chart also grows in height, the «separated groups» discs spread to the chart's shape, and the view fit
  leaves room for the group names.
- A test parses every inline script of the three pages with Node.
- The server's instructions and `parlaibero://methods/networks` describe the three networks apart.
- Results of `comention_network` (old `cooccurrence_network` with actors) and `mention_network` do not change.

## 0.5.0 · 2026-10-14 · publicada en PyPI

Two network tools on a library (plan: `docs/PLAN_redes.md`; method: resource `parlaibero://methods/networks`).

- `cooccurrence_network`: entities mentioned in the same intervention, with co-occurrence, NPMI (thresholds on
  the unrounded value), Jaccard, bias between two groups, Leiden communities, betweenness and strength,
  examples, and ambiguity alerts derived from rules. `min_co` scales with the library (`max(5, N/120)`).
  Without `entities` it proposes candidates and builds nothing.
- `mention_network`: a directed network of who names whom: deputies in office on the day, from the register,
  plus the external actors you declare. It separates `reference` from `address`, counts the record's notes in
  brackets apart, and resolves homonyms by the title's gender, a given name or a party, otherwise listing them
  apart. It reports in/out strength, PageRank, reciprocity, a group → group matrix, E-I, asymmetric pairs and an
  optional validation sample. Precision was measured by independent review in four rounds; it is in the method
  resource.
- Leiden communities ported from the Diarios Explorer (`leiden.py`), with identical results for the same seed.
- Interactive HTML pages: light and dark, keyboard, a table twin for every figure, palettes checked with the
  validator, and a self-check of the embedded data after writing.
- **No earlier result changes.** The 21-call battery gives the same output as 0.4.0.

## 0.4.0 · 2026-10-04

El motor sirve también otras colecciones: perfiles de colección (`profile.py`).

- Un perfil dice qué conjuntos hay, cómo se lee y se mapea cada CSV, qué columnas extra se filtran y
  comparan, dónde vive el almacén y cómo se llaman las bibliotecas en el explorador. ParlaIbero es el
  perfil por defecto; [luz-mcp](https://github.com/rodrodr/luz-tools) es el segundo.
- **Ningún resultado de ParlaIbero cambia**: una batería de 21 llamadas sobre ES y SV da la misma salida
  con 0.3.0 y 0.4.0, salvo el orden de los empates de `term_frequency(by='session')`, que antes era
  arbitrario y ahora sigue el nombre de la sesión.
- `analysis.search_text`, `library.create_from_query` y la clase `Tools(server, before)`, para que otros
  paquetes reutilicen el motor sin copiarlo.

## 0.3.0 · 2026-10-03

Bibliotecas: subconjuntos con nombre, de uno o varios países (plan: `docs/PLAN_bibliotecas.md`).

- `library_create`, `library_describe`, `library_edit` (añadir, quitar, anotar), `library_combine`,
  `library_rebuild`, `library_delete`, `library_export` y `library_import`.
- `library=` en todas las herramientas de análisis; `distinctive_words` compara una biblioteca con el
  resto de sus cámaras (`field='library'`); `term_frequency(by='session')` ayuda a fechar un
  acontecimiento en cada cámara (para `event_dates`).
- Exportación para el Diarios Explorer: un `.2replib` por país y un índice
  (`.parlaibero-biblioteca.json`). Comprobada contra el motor real del explorador con los CSV
  publicados de El Salvador y España: importa todos los items, reconoce la fuente como suya y
  devuelve los mismos `speech_id`, con notas y etiquetas.
- Columna `row_n` (número de registro en el CSV publicado, el `speech_id` del explorador),
  comprobada en cada importación contra una lectura independiente del archivo.
- Las bibliotecas viven en su propio archivo (`bibliotecas.duckdb`), adjunto como `lib`.
  **Las bases hechas con 0.2 deben ejecutar `parlaibero-mcp reindex` una vez**: recarga cada país
  desde los CSV ya descargados (unos minutos, sin descargar nada).

## 0.2.1 · 2026-10-03

- Todas las herramientas de análisis devuelven el DOI y la edición de los conjuntos que usaron
  (antes, solo `ngram_viewer`, `term_counter` y `share_of_voice`).
- Varias variantes con `+` ya no se combinan en una sola alternancia RE2: un `regexp_matches` por
  variante, unidas con OR. «cambio climático» con cuatro formas en los 16 países: de más de 10 min a 16 s.
- `download` en la terminal: una sola línea de progreso por fichero de datos; los de documentación
  se resumen en una línea en vez de imprimirse dos veces con «0 / 0 MB».

## 0.2.0 · 2026-10-03

Analysis tools for the MCP server.

- `ngram_viewer`: Google Books Ngram-style series (several terms, `+` variants, `*` prefixes,
  per million words / counts / % of interventions, smoothing, per country), with the base behind
  every point and low-base years flagged; writes the chart as SVG or interactive HTML.
- `term_counter`: totals, breakdown by sex and party, first and last use per country.
- `share_of_voice`: voice of each sex or party against its weight on the register (by date overlap,
  so it works in all 16 countries whatever their legislature labels).
- `distinctive_words` (weighted log-odds, Monroe et al. 2008), `kwic`, `collocations`, `coverage`,
  `export_result` (CSV/Parquet, sandboxed), `query_log` (with a methods note).
- Filters `exclude_chair` and `max_turn_words`, with automatic warnings when documents read into the
  record or the chair weigh on a result; rows without a date are reported, not silently dropped.
- One definition of a word everywhere (letters, digits and combining marks). `n_words` changes
  accordingly, and a precomputed word table makes single-word series instant.
  **Databases built with 0.1 must run `parlaibero-mcp reindex` once (≈2 min, no re-download).**
- DuckDB's progress bar is off, so nothing but the protocol reaches stdout.

## 0.1.0 · 2026-10-03

First release: MCP server (download, documentation, SQL, search, reading, citation) and the 21
`diaries-*` skills.
