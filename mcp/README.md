# parlaibero-mcp

An [MCP](https://modelcontextprotocol.io) server that gives AI agents access to **ParlaIbero**:
10 million plenary interventions from the lower or single chambers of 16 Ibero-American countries,
linked to their deputies, deposited in [Harvard Dataverse](https://dataverse.harvard.edu/dataverse/parlaibero)
(CC BY 4.0, one DOI per country).

The server downloads each country's dataset once (MD5-verified, straight from Dataverse), loads it
into a local [DuckDB](https://duckdb.org) database and exposes tools to search, count and read it.
Nothing is sent anywhere except plain GET requests to Dataverse.

## Install

You need [uv](https://docs.astral.sh/uv/getting-started/installation/). The package is on
[PyPI](https://pypi.org/project/parlaibero-mcp/); no clone is required. For the development version,
replace `parlaibero-mcp` with `--from "git+https://github.com/rodrodr/parlaibero-tools#subdirectory=mcp" parlaibero-mcp`.

**Claude Code**

```bash
claude mcp add parlaibero -s user -- uvx parlaibero-mcp
```

**Codex CLI**

```bash
codex mcp add parlaibero -- uvx parlaibero-mcp
```

**ChatGPT desktop app** and **Codex** share one configuration (`~/.codex/config.toml`). The command above
writes it; or add by hand:

```toml
[mcp_servers.parlaibero]
command = "uvx"
args = ["parlaibero-mcp"]
```

ChatGPT on the web only accepts remote servers, so it cannot use this one.

**OpenCode** (`~/.config/opencode/opencode.json`):

```json
{
  "mcp": {
    "parlaibero": { "type": "local", "command": ["uvx", "parlaibero-mcp"], "enabled": true }
  }
}
```

**Antigravity** (`~/.gemini/config/mcp_config.json`, or *MCP Servers → Manage → View raw config*),
**Claude Desktop** (`claude_desktop_config.json`), **Cursor** (`~/.cursor/mcp.json`), **Gemini CLI**
(`~/.gemini/settings.json`), **Windsurf** and most other clients use the same block:

```json
{
  "mcpServers": {
    "parlaibero": {
      "command": "uvx",
      "args": ["parlaibero-mcp"]
    }
  }
}
```

Desktop apps do not always see your shell's `PATH`: if the server fails to start, replace `"uvx"` with
the full path printed by `which uvx` (e.g. `/Users/you/.local/bin/uvx`).

To install it as a regular command instead: `uv tool install parlaibero-mcp`,
then use `parlaibero-mcp` as the command.

## Tools

**Getting and understanding the data**

| tool | what it does |
|---|---|
| `list_countries` | the 16 datasets: DOI, published version, download size, what is already local |
| `download_country` | download a country from Dataverse and load it (skips files already current) |
| `import_from_folder` | load CSV files you downloaded by hand from Dataverse |
| `get_documentation` | README, data dictionary, known limitations, process report, corpus facts (`en`/`es`/`pt`) — no download needed |
| `describe_data` | schema of the local tables, loaded countries, example queries |
| `coverage` | **check the base before reading a trend**: sessions, speech words, linked and sex-known shares per year or legislature, missing years, low-base periods, each corpus's linkage figures |
| `how_to_cite` | formatted citation of a country's dataset with DOI and version |

**Counting words over time**

| tool | what it does |
|---|---|
| `ngram_viewer` | Google Books Ngram-style series: several words or phrases at once (`,` separates series, `+` sums variants, `*` ends a prefix), per million words, raw counts or % of interventions, optional smoothing, one line per country if wanted. Every point carries its base (words, sessions) and low-base years are flagged. Can write the chart as **`.svg`** (figure for a paper or slide) or **`.html`** (hover read-out, dark mode, data table) |
| `term_counter` | totals for one or more terms: occurrences, interventions, sessions, speakers, by sex and party with per-million rates, and the **first and last use in each country** |
| `term_frequency` | one term grouped by year, decade, country, legislature, party, sex, speaker or session type |

**Who speaks and how**

| tool | what it does |
|---|---|
| `share_of_voice` | share of words (or turns) and of speakers by sex or party, against the group's share of members on the register in that period, and their ratio (> 1 = speaks more than its weight) |
| `distinctive_words` | the words that most distinguish two groups — women vs men, party vs party, period vs period — by weighted log-odds with an informative Dirichlet prior (Monroe, Colaresi & Quinn 2008) |
| `kwic` | keyword-in-context concordance lines from a reproducible random sample |
| `collocations` | words over-represented around a term (Dunning log-likelihood) |
| `search_text` | find interventions by word, phrase or regex, with filters, newest first |
| `get_intervention` · `get_session` | read one turn with its context, or a whole session |

**Anything else, and reproducibility**

| tool | what it does |
|---|---|
| `query_sql` | read-only DuckDB SQL; the connection cannot write, read other files or reach the network |
| `export_result` | save a query's full result as CSV or Parquet for R, Python or Stata |
| `query_log` | every analysis run (tool, parameters, dataset versions); can write a Markdown methods note |

The resource `parlaibero://about` summarises the collection.

### Two filters that change results

Most analysis tools take `exclude_chair` and `max_turn_words`, and warn when you should use them:

- **`max_turn_words`** — the published corpora keep documents read into the record (committee
  reports, bills, lists) as speech when the record marks no separator. They sit in very long turns
  and, measured on 3 October 2026, hold **54 % of the speech words in Argentina, 26 % in Uruguay and
  25 % in Mexico**, against under 1 % in Spain or Brazil. Any rate per million words or share of
  words is affected; `max_turn_words=10000` leaves those turns out, and `coverage` reports the share
  per country (`long_turn_words_pct`).
- **`exclude_chair`** — the presiding officer's procedural turns (giving the floor, calling votes)
  can dominate a group. Comparing women and men deputies in Spain 2016-2023, the most distinctive
  "women's words" are *votación, votos, pausa* with the chair in, and *mujeres, violencia,
  igualdad, género* without it.

Rows without a date (6,187 in Ecuador, 44 in Costa Rica) are left out of anything by year or
period, and the tools say so.

### How words are counted

A word is a run of letters, digits or combining marks. Counts are whole-word, case- and
accent-insensitive (`nacion` = `Nación`), so `corrupción` does not count `anticorrupción` — add
it as a variant (`corrupción+anticorrupción`) if you want both. `n_words`, the precomputed word
table and every tool use this same definition, so their figures add up. Single words are served
from a precomputed table (instant); phrases and filters by party or deputy scan the text (seconds).

## Data model

```
interventions   country · id_session · id_int · legislature · legislative_session · session_number ·
                date · session_type · intervention_order · speaker_raw · id_dep · speaker_name ·
                sex · party · district · dm_speech · text · n_words
unigrams        word counts of speech rows by country, year and sex (accent-folded)
vocab           display form of each folded word
deputies        country + the core columns of every deputy register
deputies_{iso}  the full register of one country, with its own extra columns
datasets        what is loaded: DOI, version, source, rows, sessions, date range
```

Things worth knowing before drawing conclusions (the server also tells the agent):

- `dm_speech = 1` marks speech. Rows with `0` are cover pages, summaries, vote tallies and
  reproduced documents; `intervention_order = 0` is the session's Prolegomena.
- `sex`, `party` and `district` come from the deputy register and are empty when the speaker is
  not a linked deputy (ministers, clerks, collective or anonymous voices).
- Coverage, linkage and caveats differ by country: read `known_limitations` and `corpus_info`.
- `id_session` / `id_int` are stable within a published version, not across versions. Cite the
  dataset with its version.

## Command line

```bash
parlaibero-mcp                    # serve MCP over stdio (what clients run)
parlaibero-mcp download SV ES     # download and load countries ('all' for the 16)
parlaibero-mcp import ~/Downloads/parlaibero
parlaibero-mcp status
parlaibero-mcp reindex             # after upgrading from an older version (no re-download)
parlaibero-mcp remove SV
```

Large countries (Brazil, Mexico, Portugal, Ecuador, Spain: 1-1.5 GB each) are best downloaded from
the terminal so a client time-out does not interrupt them. All 16 take about 12 GB of downloads
plus 15 GB of database; the downloaded CSVs can be deleted afterwards to save space
(`~/.parlaibero/data/{ISO}/*.csv`), but they are needed to re-import.

## Configuration

| variable | default | |
|---|---|---|
| `PARLAIBERO_HOME` | `~/.parlaibero` | where downloads and the database live |
| `PARLAIBERO_DATAVERSE_URL` | `https://dataverse.harvard.edu` | Dataverse installation |
| `PARLAIBERO_LOG` | `1` | `0` turns off the query log (`~/.parlaibero/query_log.jsonl`) |

## License

MIT for the code. The data are CC BY 4.0 and are cited per country with their DOI.

Grant PID2022-141706NB-C22 funded by MICIU/AEI/10.13039/501100011033 and by ERDF/EU.
