# parlaibero-mcp

An [MCP](https://modelcontextprotocol.io) server that gives AI agents access to **ParlaIbero**:
10 million plenary interventions from the lower or single chambers of 16 Ibero-American countries,
linked to their deputies, deposited in [Harvard Dataverse](https://dataverse.harvard.edu/dataverse/parlaibero)
(CC BY 4.0, one DOI per country).

The server downloads each country's dataset once (MD5-verified, straight from Dataverse), loads it
into a local [DuckDB](https://duckdb.org) database and exposes tools to search, count and read it.
Nothing is sent anywhere except plain GET requests to Dataverse.

## Install

You need [uv](https://docs.astral.sh/uv/getting-started/installation/). No clone is required.

**Claude Code**

```bash
claude mcp add parlaibero -s user -- uvx --from "git+https://github.com/rodrodr/parlaibero-tools#subdirectory=mcp" parlaibero-mcp
```

**Codex CLI**

```bash
codex mcp add parlaibero -- uvx --from "git+https://github.com/rodrodr/parlaibero-tools#subdirectory=mcp" parlaibero-mcp
```

**Claude Desktop** (`claude_desktop_config.json`), **Cursor** (`~/.cursor/mcp.json`), **Gemini CLI**
(`~/.gemini/settings.json`), **Windsurf** and most other clients use the same block:

```json
{
  "mcpServers": {
    "parlaibero": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/rodrodr/parlaibero-tools#subdirectory=mcp", "parlaibero-mcp"]
    }
  }
}
```

Desktop apps do not always see your shell's `PATH`: if the server fails to start, replace `"uvx"` with
the full path printed by `which uvx` (e.g. `/Users/you/.local/bin/uvx`).

To install it as a regular command instead: `uv tool install "git+https://github.com/rodrodr/parlaibero-tools#subdirectory=mcp"`,
then use `parlaibero-mcp` as the command.

## Tools

| tool | what it does |
|---|---|
| `list_countries` | the 16 datasets: DOI, published version, download size, what is already local |
| `download_country` | download a country from Dataverse and load it (skips files already current) |
| `import_from_folder` | load CSV files you downloaded by hand from Dataverse |
| `get_documentation` | README, data dictionary, known limitations, process report, corpus facts (`en`/`es`/`pt`) — no download needed |
| `describe_data` | schema of the local tables, loaded countries, example queries |
| `query_sql` | read-only DuckDB SQL; the connection cannot write, read other files or reach the network |
| `search_text` | word, phrase or regex search, case- and accent-insensitive, with filters (countries, dates, party, sex, deputy) |
| `term_frequency` | occurrences of a term by year, decade, country, legislature, party, sex, speaker or session type, per million words |
| `get_intervention` | full text and metadata of one turn, with N turns of context |
| `get_session` | ordered list of turns of a session |
| `how_to_cite` | formatted citation of a country's dataset with DOI and version |

The resource `parlaibero://about` summarises the collection.

## Data model

```
interventions   country · id_session · id_int · legislature · legislative_session · session_number ·
                date · session_type · intervention_order · speaker_raw · id_dep · speaker_name ·
                sex · party · district · dm_speech · text · n_words
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

## License

MIT for the code. The data are CC BY 4.0 and are cited per country with their DOI.

Grant PID2022-141706NB-C22 funded by MICIU/AEI/10.13039/501100011033 and by ERDF/EU.
