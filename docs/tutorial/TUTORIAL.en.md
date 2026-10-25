# Sixteen parliaments, one agent

<!-- eyebrow: parlaibero-tools · tutorial -->

*[Versión en español](TUTORIAL.md)*

The plenary sittings of sixteen Ibero-American parliaments: nearly ten million interventions since 1976, linked to the
register of deputies. parlaibero-tools offers two tools for the same corpus: an MCP server to query it from an AI agent
and 21 Claude Code skills to build it.

<!-- doors -->

### Query the data

`parlaibero-mcp` · an MCP server with 31 tools

Your agent (Claude, the ChatGPT desktop app, Codex, Cursor…) downloads the datasets from Harvard Dataverse and then
searches, counts and reads the sittings on your computer. No programming is needed: you ask in words. You need
[uv](https://docs.astral.sh/uv/getting-started/installation/); in Claude Code:

```bash
claude mcp add parlaibero -s user -- uvx parlaibero-mcp
```

In Claude Desktop, Cursor, Gemini CLI and most clients, this block goes in their configuration (the other variants are
in the [README](../../mcp/README.md)):

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

- [Four studies](#1-four-studies)
- [A library from scratch](en/bibliotecas.md)
- [The 31 tools](en/referencia.md)

### Build a corpus

`diaries-*` · 21 Claude Code skills

The pipeline that turned the session diaries into those datasets: from the scanned PDF or the HTML to the 16-column
matrix, with a confidence system that leaves the doubtful cases to you and a log of every decision. For a chamber, a
country or a period that is not there, or to audit how one was made.

```bash
git clone https://github.com/rodrodr/parlaibero-tools.git
cd parlaibero-tools
bash install_skills.sh
```

And in the project folder that will hold the data:

```bash
bash ~/.claude/skills/diaries-lib/install.sh
```

- [Building a corpus](en/construir.md)
- [A country from scratch](en/pais.md)
- [Technical documentation, in Spanish only](../../skills/diaries-lib/docs/diaries_index.html)

<!-- /doors -->

## 1. Four studies

Each study shows parlaibero-mcp at work: a chain of requests with their real results and the checks that, more than
once, change the conclusion. The agent picks the tool, runs it on your computer and reads the result.

<!-- studies -->

Each study is a page with the same format. A request says what you write to the agent; below it comes the tool the
agent uses, with its main parameters, and then the result: tables, charts or interactive pages. The results are real:
they were obtained with the script [`casos.py`](casos.py), and anyone can reproduce them (the personal names left out
of the word lists are kept separately, outside the repository). The answer your agent writes
will vary; the data will not. At the end of each study there is a request that asks for it all at once.

> **Ask:** what you write to the agent, in your own words.
>
> *The agent uses* `the_tool` (`parameter=value`) and reads the result.

If you have never made a library, start with the guide [A library from scratch](en/bibliotecas.md). It builds one step
by step, from the question to the checklist: when you need one, how to test the words and the threshold, how to read a
sample in each chamber and what to do when the first definition fails.

## 2. What is in the database

> **Ask:** "Which parliaments does ParlaIbero have, and which have I downloaded?"
>
> *The agent uses* `list_countries`.

<!-- table:ini_corpus -->
| Country | Years | Sittings | Speech interventions | Version | DOI |
|---|---|---:|---:|---|---|
| Argentina | 1983–2025 | 1,086 | 256,636 | 2.0 | [10.7910/DVN/IVNYID](https://doi.org/10.7910/DVN/IVNYID) |
| Brazil | 2003–2025 | 7,731 | 1,649,698 | 2.0 | [10.7910/DVN/VTXNW3](https://doi.org/10.7910/DVN/VTXNW3) |
| Chile | 1990–2025 | 4,336 | 556,679 | 2.0 | [10.7910/DVN/IKBNRL](https://doi.org/10.7910/DVN/IKBNRL) |
| Colombia | 2000–2025 | 1,608 | 463,201 | 2.0 | [10.7910/DVN/TYYERX](https://doi.org/10.7910/DVN/TYYERX) |
| Costa Rica | 1994–2025 | 5,343 | 375,730 | 2.0 | [10.7910/DVN/W6UAHQ](https://doi.org/10.7910/DVN/W6UAHQ) |
| Dominican Rep. | 2001–2025 | 2,225 | 101,381 | 2.0 | [10.7910/DVN/DZKXUG](https://doi.org/10.7910/DVN/DZKXUG) |
| Ecuador | 1979–2025 | 6,105 | 1,280,822 | 2.0 | [10.7910/DVN/M2QJN6](https://doi.org/10.7910/DVN/M2QJN6) |
| Spain | 1977–2025 | 3,559 | 558,940 | 2.0 | [10.7910/DVN/OKHGAB](https://doi.org/10.7910/DVN/OKHGAB) |
| Guatemala | 2000–2026 | 2,039 | 251,720 | 2.0 | [10.7910/DVN/NH5TTC](https://doi.org/10.7910/DVN/NH5TTC) |
| Mexico | 1988–2025 | 2,537 | 630,937 | 2.0 | [10.7910/DVN/0IS1YE](https://doi.org/10.7910/DVN/0IS1YE) |
| Panama | 1996–2025 | 3,638 | 508,324 | 2.0 | [10.7910/DVN/Y8FUSX](https://doi.org/10.7910/DVN/Y8FUSX) |
| Peru | 1995–2025 | 3,061 | 849,499 | 1.0 | [10.7910/DVN/7MK94V](https://doi.org/10.7910/DVN/7MK94V) |
| Portugal | 1976–2025 | 4,939 | 1,554,381 | 2.0 | [10.7910/DVN/VRPUFU](https://doi.org/10.7910/DVN/VRPUFU) |
| Paraguay | 1988–2025 | 1,275 | 360,201 | 2.0 | [10.7910/DVN/PDX8GA](https://doi.org/10.7910/DVN/PDX8GA) |
| El Salvador | 2018–2025 | 423 | 48,654 | 2.0 | [10.7910/DVN/MUJU6A](https://doi.org/10.7910/DVN/MUJU6A) |
| Uruguay | 1985–2025 | 2,813 | 421,284 | 2.0 | [10.7910/DVN/KI1AOC](https://doi.org/10.7910/DVN/KI1AOC) |
| **Total** |  | 52,718 | 9,868,087 |  |  |
<!-- /table -->

Each country is a Harvard Dataverse dataset with its own DOI and version, and it is downloaded once (between 0.5 and
1.5 GB, a few minutes) with `download_country`; the largest can be downloaded from the terminal with
`parlaibero-mcp download BR`. The data stay in a local DuckDB database, in `~/.parlaibero`, and everything is computed
on your computer. Each row is an intervention, linked where possible to the register of deputies, which supplies sex,
party and district.

Before interpreting a trend you need to know how much text supports it, and of what kind.

> **Ask:** "What is the base for Argentina, Spain, Mexico and Uruguay in 2022 and 2023?"
>
> *The agent uses* `coverage` (`countries=["AR","ES","MX","UY"]`, `by="year"`, `date_from="2022-01-01"`,
> `date_to="2023-12-31"`).

<!-- table:ini_cobertura -->
| Country | Words a year (median) | Words in turns over 10,000 (%) | Linked speech (%) |
|---|---:|---:|---:|
| Argentina | 1,222,879 | 19.3 | 90.8 |
| Spain | 3,199,097 | 0.8 | 96.9 |
| Mexico | 5,847,478 | 26.4 | 96.2 |
| Uruguay | 3,742,281 | 32.0 | 96.4 |
<!-- /table -->

Some records do not separate the documents read aloud (reports, bills, lists) from speech. In Uruguay, 32.0% of the
words of those years are in turns of more than 10,000 words; in Mexico, 26.4%; in Argentina, 19.3%; in Spain, 0.8%. A
comparison of words between these countries without `max_turn_words=10000` mostly compares documents.

> [!TIP]
> `get_documentation` serves the documents deposited with each dataset (known limitations, corpus information, data
> dictionary), in Spanish, English and Portuguese. Ask the agent to read a country's limitations before comparing it.

## 3. How to ask

The agent translates the request into calls, so the more precise the question, the better the choice. It helps to say
which countries and which period, which unit (words, turns, interventions, sittings) and which groups, and to ask for
the checks: the base before comparing, reading before interpreting, a rate instead of a count. A study usually follows
this path:

1. What is there, and on what base? (`list_countries`, `coverage`, `get_documentation`)
2. How much is said, and since when? (`term_counter`, `ngram_viewer`)
3. Where is it concentrated? (`term_frequency`, `get_session`)
4. What exactly is said? (`kwic`, `collocations`, `search_text`, `get_intervention`)
5. Who speaks, and what sets the groups apart? (`share_of_voice`, `distinctive_words`)
6. A subset to study in depth (`library_create`, `library_describe`), step by step in the [libraries
   guide](en/bibliotecas.md)
7. Themes, actors and mentions (`cooccurrence_network`, `comention_network`, `mention_network`)
8. What no tool does (`query_sql`)
9. Closing the study: export, log and cite (`export_result`, `library_export`, `query_log`, `how_to_cite`)

You can ask for a whole study at once or step by step. Step by step costs more, but it lets you look at each result
before the next, which is where the problems show up. The [tools page](en/referencia.md) describes all 31, with their
parameters and an example request.

## 4. Before believing a result

The four studies and the libraries guide run into fifteen traps. None is an error of the agent: they are properties of the records, of the
registers and of the measures, and each one has its check.

- **The corpus starts late.** The first use is the corpus's, not the country's. [Femicide, § 1](en/feminicidio.md#1-how-many-times-and-since-when)
- **The moving average shifts the peaks.** Read each year's count before dating one. [Femicide, § 2](en/feminicidio.md#2-the-curve-of-each-parliament)
- **A term does not translate.** Spain and Portugal name violence against women in another way. [Femicide, § 5](en/feminicidio.md#5-spain-and-portugal-another-word-for-the-same-thing)
- **Prefixes and misplaced dates.** `covid*` finds *Covidien*; a sitting can be misdated. [Pandemic, § 1](en/pandemia.md#1-the-first-use-on-each-floor)
- **The chamber was not meeting.** A late first use can be a first sitting. [Pandemic, § 1](en/pandemia.md#1-the-first-use-on-each-floor)
- **Counts and proportions.** The chamber that says a word most can be the one that pays it least attention. [Pandemic, § 2](en/pandemia.md#2-attention-week-by-week)
- **Documents read aloud.** In some chambers, a third of the words are documents. [§ 2 of this page](#2-what-is-in-the-database)
- **A baseline.** A change is measured against the same group in the same period, not against 1. [Pandemic, § 5](en/pandemia.md#5-who-spoke-about-the-pandemic)
- **The Mesa Directiva speaks from the floor.** Voting formulas count as voice. [Voice, § 3](en/voz.md#3-mexico-the-mesa-speaks-from-the-floor)
- **Words or turns.** The same voice changes with the unit. [Voice, § 2](en/voz.md#2-since-2021-words-and-turns)
- **Language before topic.** Word lists compare languages and styles. [Voice, § 4](en/voz.md#4-spain-and-its-languages) and [Pandemic, § 4](en/pandemia.md#4-what-each-chamber-talked-about)
- **Labels, boundaries and gaps in the register.** Federations of the same party, the day the legislature changes, incomplete years. [Voice, § 5](en/voz.md#5-spain-by-party-labels-and-boundaries)
- **Counting a frame is not adopting it, and a name is not a person.** [Frames, § 4](en/marcos.md#4-privilégios-one-frame-two-uses) and [§ 6](en/marcos.md#6-who-names-whom-the-namesake)
- **A definition that works in three chambers fails in the fourth.** Read a sample in each chamber on its own. [Libraries, § 5](en/bibliotecas.md#5-describe-and-read-a-sample-in-each-chamber)
- **Precise is not complete.** A definition without noise can leave two thirds of the topic outside: coverage is measured by reading what is left out. [Libraries, § 9](en/bibliotecas.md#9-beyond-the-keywords)

## 5. Closing a study

> **Ask:** "Save the weekly pandemic table as Parquet, so I can carry on in R."
>
> *The agent uses* `export_result` (`sql=…`, `path=…/pandemia_semanal.parquet`, `format="parquet"`). It writes only to
> the destination folder you give it.

> **Ask:** "Export the *pandemia* library to open it in the Diarios Explorer."
>
> *The agent uses* `library_export` (`name="pandemia"`, `folder=…`), which writes one file per country, because the
> explorer opens one country at a time, and an index from which `library_import` rebuilds the comparative library.

> **Ask:** "Write the methods appendix for what we have done."
>
> *The agent uses* `query_log` (`methods_path=…/metodos.md`), which lists each analysis with its parameters and the
> version of each dataset.

> **Ask:** "Give me the citation for the datasets we have used."
>
> *The agent uses* `how_to_cite`, one country at a time. Each dataset is cited with its DOI and its version: row
> identifiers are stable within a version, not across versions.

> [!NOTE]
> The examples in this tutorial do not name people: quotations leave out the speaker, word lists leave out proper names
> and networks describe actors by their office. If you publish results from the agent, do the same, above all when the
> records include the names of private individuals or of victims.
