# Building a corpus

<!-- eyebrow: The diaries-* skills -->

*[Versión en español](../es/construir.md) · [Tutorial index](../TUTORIAL.en.md)*

The data parlaibero-mcp queries came out of a pipeline: 21 Claude Code skills that take a session diary from the
scanned PDF, the HTML or the XML to the 16-column matrix of interventions, linked to the register of deputies. This
page explains when they are worth using, what each step does, how they warn you when in doubt and where to start.

<!-- side -->

**Install**

You need [Claude Code](https://claude.com/claude-code) and Python `≥ 3.11`. From the repository:

```bash
git clone https://github.com/rodrodr/parlaibero-tools.git
cd parlaibero-tools
bash install_skills.sh
```

It copies the skills to `~/.claude/skills`. If you already have any of them, it stops without touching them; `--force`
replaces them and keeps a copy first. Then, in the project folder that will hold the data:

```bash
bash ~/.claude/skills/diaries-lib/install.sh
```

It installs the Python dependencies, creates `source/`, `state/`, `country_config/` and `docs/`, and checks for
[Ollama](https://ollama.com), which is needed only for the OCR of scanned PDFs.

## 1. When to use them, and when not

To query the sixteen parliaments you do not need them: the MCP server downloads the datasets already built. The skills
are for something else:

- **A corpus that does not exist.** Another chamber (a senate, a regional parliament), another country or another
  period, from its session diaries.
- **Reproducing or auditing a published one.** The skills are the method the sixteen were built with, and every
  decision of the construction was recorded with its evidence.
- **A single piece.** Local OCR of some scanned PDFs, or tagging the speakers of some records, without going as far as
  the matrix.

Before starting, three things. Claude Code is the orchestrator: it reads each `SKILL.md`, runs the code in
`diaries-lib`, reasons about the ambiguous cases and asks you. It is not a program you launch and wait for: every
country in the corpus went through reviews by hand and decisions that had to be taken and recorded. And the skills
carry the experience of building the sixteen corpora and keep references to that process: decision identifiers such
as `tr-0109`, example countries and some countries' own scripts that are not in the repository. They are the method as
it was applied, not a generic product, and they are written in Spanish.

> [!NOTE]
> Apart from Claude Code, no key is needed. OCR runs on your computer with Ollama. There is a retry with MiniMax for the
> worst-read pages, but it is off by default and needs its own key.

## 2. The pipeline

<!-- pipeline -->

Thirteen skills in order, grouped in five stretches. Each one reads a folder of `source/{iso2}/` and writes another,
and none overwrites what came before: if a step fails, it is fixed and re-run from there. `extracted/` is the faithful
layer, the text as it came out of the source, and it is never cleaned; cleaning belongs to `correct` alone.

The order has three nuances worth knowing before you start:

- `ocr` works only if the PDF is an image. With a digital PDF, HTML or XML, it is skipped.
- `meta` and `dedupe` come before `tag`. Tagging ranks the forms of the speaker markers by how often they appear in the
  whole corpus to decide which go into its lexicon; a duplicated sitting counts them twice, and deduplicating later
  no longer corrects that decision.
- `deputies` can come before `tag` if the records carry a roll call: the register then comes from the corrected text
  and helps recognise the speakers.

The delivery is two files: `{ISO2}_interventions.csv`, with the 16 canonical columns, and `{ISO2}_deputies.csv`, the
register of deputies, which joins the first by `id_dep` and the legislature. They are the ones published in Harvard
Dataverse and the ones `download_country` loads on your computer:

```text
id_session · id_int · legislature · legislative_session · session_number · date · session_type · intervention_order
speaker_raw · id_dep · speaker_name · sex · party · district · dm_speech · text
```

The other eight skills have no turn. They are used at any time to see the state, review and correct, validate,
record a decision, write the report, learn the system or improve a skill.

## 3. AUTO, FLAG, HALT: when it asks you

Nearly every step computes a confidence between 0 and 1 and compares it with two thresholds. Above the first, AUTO: it goes on
without asking. Between the two, FLAG: it goes on, but notes the case for you to review. Below the second, HALT: it
stops until you step in. The thresholds live in each country's configuration (`country_config/{iso2}.yaml`) and can be
adjusted; these are the template's:

<!-- table:umbrales -->
| Skill | AUTO | FLAG | HALT |
|---|---:|---:|---:|
| `diaries-tag` | ≥ 0.80 | ≥ 0.60 | < 0.60 |
| `diaries-match` | ≥ 0.90 | ≥ 0.70 | < 0.70 |
| all the others | ≥ 0.85 | ≥ 0.65 | < 0.65 |
<!-- /table -->

Two steps have thresholds of their own. `match` demands more: a wrong link puts one person's words under another's
name, with their party and their sex. `tag` accepts a somewhat lower confidence, but has a rule that does not depend on
it: a single untagged speaker mark stops the sitting, because it would silently give the
whole intervention to the previous speaker. Each card in § 6 says what the confidence of its step measures.

Pending cases are reviewed with `/diaries-review`: for each FLAG it shows the evidence and the confidence, and you
accept, correct, escalate it to HALT or leave it for later. An error that repeats is corrected once with
`/diaries-feedback`: for one sitting, as a rule from a date on, or for the whole skill.

```text
/diaries-status --country {iso2}
/diaries-review --country {iso2}
```

## 4. The decision log

The important decisions of a corpus are taken in the moment and forgotten afterwards: a threshold, a definition, some
rows set aside, one source preferred to another. `/diaries-decide` saves them when they are taken, with four fields: the
decision, the alternatives, the evidence and the consequence. The evidence is compulsory and says what was measured,
on what and with what result; if nothing was measured, it says so, and that is useful too. What is not saved is a
preference presented as a finding:

- ✗ «This threshold was chosen.»
- ✓ «This threshold was chosen because, on a sample read by hand, it separated the rows to set aside from the rows to
  keep; with a lower one, good rows were set aside.»

A superseded decision is not deleted: `--supersede` marks it and links it to the one that corrects it, and that chain
is the history of the corpus's corrections. A country's decisions go to `state/{iso2}/decisions.jsonl`, and those that
hold for all, to `state/_transversal/`. At the end, `/diaries-report` writes the internal report of the process,
`docs/{iso2}/pipeline_report.md`: timeline, confidences, corrections, automation rate and what is still open.

Three skills record different things:

| Skill | What it records |
|---|---|
| `/diaries-decide` | the reasoning: why something was done and with what evidence |
| `/diaries-feedback` | the action: a correction the pipeline applies |
| `/diaries-refine` | the behaviour: a change to a `SKILL.md` |

## 5. Where to start

1. Install the skills and prepare the project folder, with the two commands at the top of the page.
2. Copy a country's diaries into `source/{iso2}/raw/`, one file per sitting. If they are named by their date
   (`YYYY-MM-DD.pdf` or `.html`), you save yourself questions.
3. Open Claude Code in the project folder and ask for the guide with `/diaries-teach`. Its path 2, «Nuevo país desde
   cero» (a new country from scratch), walks through the five stretches and offers to go with you through the first
   step.
4. Set up the country with `/diaries-bootstrap --country {iso2}`, which examines three to five documents and asks you
   only what it could not infer.
5. Follow the chain, and review with `/diaries-review` each time a step leaves cases in FLAG:

```text
/diaries-ocr --country {iso2} --all
/diaries-extract --country {iso2} --all
/diaries-correct --country {iso2} --all
/diaries-meta --country {iso2} --all
/diaries-dedupe --country {iso2}
/diaries-tag --country {iso2} --all
/diaries-matrix --country {iso2} --all
/diaries-deputies --country {iso2}
/diaries-match --country {iso2}
/diaries-merge --country {iso2}
/diaries-standardize --country {iso2}
/diaries-document --country {iso2}
/diaries-report --country {iso2}
```

If the chain stops, `/diaries-status` says where, and which step is pending next; `/diaries-review` resolves the open
cases, and you go on from the skill that stopped.

The guide [A country from scratch](pais.md) runs this whole chain on four sessions from Bolivia, a country that is not
in ParlaIbero: what each skill asked, what was checked by hand and what went wrong.

The skills' full technical documentation, written during the construction and in Spanish only, details every
confidence formula, every check and every stopping rule: the [index of the 21 skills](../../../skills/diaries-lib/docs/diaries_index.html)
and the [procedure tree](../../../skills/diaries-lib/docs/pipeline_procedure_tree.html). They keep references to the
project the corpus was built in, such as scripts that are not in the repository; where something disagrees, the
`SKILL.md` files prevail.

## 6. The 21 cards

Each card says what the skill does, what it reads and writes, what its confidence measures and how it is run, next to
the description Claude Code uses to decide when to use it: that is why a skill can also be asked for in words («review
the pending cases for Chile»). Paths are relative to the project folder; `{iso2}` is the country code in lower case,
`{ISO2}` in upper case, and `{id}` the sitting's.

<!-- skills -->
