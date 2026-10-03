# Changelog

## 0.2.1 · sin publicar

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
