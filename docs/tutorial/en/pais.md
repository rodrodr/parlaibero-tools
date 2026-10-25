# A country from scratch

<!-- eyebrow: Guide · The diaries-* skills, end to end -->

*[Versión en español](../es/pais.md) · [Building a corpus](construir.md) · [Tutorial index](../TUTORIAL.en.md)*

[Building a corpus](construir.md) explains what each skill does. This guide uses them, one after another, on a country
that is not in ParlaIbero: four sessions of the Bolivian Chamber of Deputies, from the PDFs of *El Redactor de Debates*
to the intervention matrix linked to the register of deputies. Each step shows the command, what the skill asked and
what it was told, the figures, an excerpt of the record, what was checked by hand and the decision that was recorded.
It also shows what went wrong, which was quite a lot: errors of the skills, of the library and of Claude Code running
them. The figures and excerpts come from the real run; in the excerpts, every deputy's name is covered with `[N]`. The
excerpts stay in Spanish, as the record is, with a gloss in the text.

<!-- side -->

**The run**

<!-- table:pais_ficha -->
- **Country:** Bolivia, Chamber of Deputies
- **Source:** El Redactor de Debates, digital PDF
- **Sittings:** 67th · 76th · 153rd · 154th
- **Rows:** 905
- **Linked speech:** 97.1%
- **Questions answered:** 25
- **Decisions:** 25, 5 superseded
- **Local scripts:** 14
- **Skills:** parlaibero-tools `3935e4d`
<!-- /table -->

The skills as they stood at that commit. A later version may ask other things or in another order; the method is the
same.

## 1. The question and the source

Before the first command you need to know what the corpus is for, because that decides how many sessions it needs.
Here the question is one of method: to show how a corpus is built. Four sessions from two volumes, March and July 2024,
are enough, and it is said from the start that the sample is not fit for time series: the 2023-2024 volumes hold 27 of
the more than 200 sessions of that legislative year. That is the first decision in the log (bo-0001), and the joint
sessions of the Plurinational Legislative Assembly stay out.

*El Redactor de Debates* publishes one volume a month, as a digital PDF: the text can be copied, so no OCR will be
needed. Each volume has some preliminary pages (authorities, committees, resolutions), the month's sessions and an
index.

The work goes in a separate folder, with copies of the PDFs and their sha256 checked against the originals, so that
nothing tried out touches the source. The folder is set up with the library's installer:

```bash
mkdir bo_desde_cero && cd bo_desde_cero
bash ~/.claude/skills/diaries-lib/install.sh
```

## 2. Preparing the sources

The skills expect one file per session, named by its date, in `source/bo/raw/`. No skill cuts a volume into sessions:
that is prior work, done with a local script. Each session starts on a new page with a fixed heading («Nª SESIÓN … /
LEGISLATURA … / LA PAZ, day …»), so the script cuts there.

Here came the first question. The sitting of 31 July runs past midnight, and the August volume starts another session,
the 154th, in the middle of it. One session or two? The answer was two, cut where the August volume itself cuts it
(bo-0003), and the preliminaries stay out of the sessions (bo-0002).

<!-- table:pais_sesiones -->
| Sitting | Date | Pages | Tagged turns | Rows of the canonical file | Words in the canonical file |
|---|---|---:|---:|---:|---:|
| 67th | 2024-03-13 | 221 | 408 | 409 | 97,873 |
| 76th | 2024-03-26 | 67 | 128 | 129 | 32,277 |
| 153rd | 2024-07-31 | 79 | 185 | 186 | 40,866 |
| 154th | 2024-08-01 | 77 | 181 | 181 | 42,700 |
| **Total** |  | 444 | 902 | 905 | 213,716 |
<!-- /table -->

The hand check: the two March sessions have 134,048 words in the volume's pages and 134,048 in the two cut PDFs, and
on the page split between the 153rd and the 154th none is missing. (The table's words are those of the canonical file
at the end of the run, without running heads or folios.) The canonical file has one row more than there are turns in
three sessions: the cover, added at the end as row 0.

## 3. Setting up the country: bootstrap

```text
/diaries-bootstrap --country bo
```

The skill examines the four sessions before asking. It measured about 3,340 characters a page (digital PDF, no OCR)
and counted the speaker marks at the start of a line: «DIP.» 254 times, «PRESIDENTE» or «PRESIDENTA» 452 and
«SECRETARIO» or «SECRETARIA» 186. It also saw that the first mark of whoever chairs or holds the secretariat carries the
name («PRESIDENTE, DIP. …:»), and 33 upper-case forms followed by a colon: about 30 are headings of documents read out
in the plenary, and 2 are deputies whose mark has no «DIP.».

It asked only what it could not infer:

- **The legislature.** `legislature` is the constitutional term, 2020-2025, and `legislative_session` the legislative
  year in the heading, 2023-2024.
- **Marks without «DIP.».** No pattern of their own: tag resolves them with the register of deputies.
- **«SESIÓN PLENARIA».** It is the plenary: `session_type` = `ordinaria`.

It writes `country_config/bo.yaml`, the pipeline state (with OCR already marked as skipped) and a start-up report. The
hand check is to read the configuration it wrote: two of its keys are never read afterwards, which showed on reaching
meta (§ 5). This is how the speaker marks stood in that configuration at the end of the run; the full-stop alternative
was added by bo-0015 (§ 8), and the comments cite the decision behind each change:

<!-- table:pais_config -->
```extracto
speaker_tag_patterns:
  - "^DIP\\.\\s+([A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ.\\-\\s]+?)(?::|\\.(?=\\s+(?:[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]|[…¿¡“«(])))"
  - "^(PRESIDENT[EA](?:\\s+EN\\s+EJERCICIO)?)(?:,\\s*DIP\\.\\s+[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ.\\-\\s]+?)?(?::|\\.(?=\\s+(?:[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]|[…¿¡“«(])))"
  - "^(SECRETARI[OA])(?:,\\s*DIP\\.\\s+[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ.\\-\\s]+?)?(?::|\\.(?=\\s+(?:[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]|[…¿¡“«(])))"

# Nivel 2: nombre en mayúsculas de dos o más palabras ante «:», sin «DIP.». Hay 2 marcas así en la 67.ª;
# el investigador decidió no darles un patrón de nivel 1 porque también casarían encabezados de los
# documentos leídos (LOTE A:, POR TANTO:, CÓDIGO CATASTRAL:…): las puntúa tag contra el registro.
# Mínimo 3 palabras (decisión bo-0020, que corrige bo-0013): con 2, ARTÍCULO ÚNICO: (×2) y TITULO EJECUTORIAL: puntuaban 0,70,
# lo mismo que el nombre real de 5 palabras, y abrían turno; todo nombre del padrón tiene 3 o más.
speaker_loose_pattern: "^(?P<name>(?:DIP\\.\\s+)?[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ.\\-]+(?:\\s+[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ.\\-]+){2,5})(?=\\s*:)"
```
<!-- /table -->

## 4. From PDF to text: extract and correct

```text
/diaries-extract --country bo --all
/diaries-correct --country bo --all
```

`extract` leaves the faithful layer: the text as it comes out of the PDF, with a marker for each page, never cleaned.
Its fragmentation gate fired in the 67th: the median line was 8 characters long. The cause was 55 pages of table, the
annex of a land-titling law with the name and identity-card number of each beneficiary, one cell per line; in the rest
of the session the median was 89. The default mode was chosen (bo-0004), and it was noted that the table holds private
persons' data.

`correct` removes the page furniture and joins the lines into paragraphs. *El Redactor* has a single piece of furniture,
the running head with the folio. For the reflow, four variants were measured on the four sessions:

<!-- table:pais_reflujo -->
| Variant | What it does | Breaks mid-sentence | Marks cut off from their text |
|---|---|---:|---:|
| A | the template: paragraphs of at least 80 characters | 8,468 | 302 |
| B | the measured box, and the mark absorbs the line below | 3,747 | 141 |
| C | B, and joins pairs of full lines up to 2,000 characters | 7 | 0 |
| D | C, capped at 6,000 | 2 | 0 |
<!-- /table -->

With a 2,000-character cap the roll calls, which run to 3,791, were split. D was chosen (bo-0005). This is the opening of
the 76th in the faithful layer, with the running head, the folio and the PDF's lines. The acting chair (*PRESIDENTE EN
EJERCICIO*) opens the sitting and asks the secretary to check the quorum; the secretary thanks her and starts the roll
call (*Llama lista*):

<!-- table:pais_capa_extracted -->
```extracto
---PAGE 0001---
CÁMARA DE DIPUTADOS / EL REDACTOR / MARZO 2024
245
76ª SESIÓN ORDINARIA
LEGISLATURA 2023-2024
LA PAZ, MARTES 26 DE MARZO DE 2024
[N]
PRESIDENTE EN EJERCICIO DE LA CÁMARA DE DIPUTADOS
PRESIDENTE EN EJERCICIO, DIP. [N]: Bueno, muy buenos
días colegas Diputados, Diputadas. Para instalar la presente Sesión, solicito a nuestro Diputado
Secretario, verificar el quorum reglamentario.
SECRETARIO, DIP. [N]: Muchas gracias. Buenos días, muchas
gracias hermana Presidenta en ejercicios.
Vamos a proseguir a llamar lista para verificar el quorum correspondiente, vamos con Chuquisaca.
(Llama lista).
```
<!-- /table -->

And corrected:

<!-- table:pais_capa_corrected -->
```extracto
76ª SESIÓN ORDINARIA LEGISLATURA 2023-2024 LA PAZ, MARTES 26 DE MARZO DE 2024 [N]
PRESIDENTE EN EJERCICIO DE LA CÁMARA DE DIPUTADOS

PRESIDENTE EN EJERCICIO, DIP. [N]: Bueno, muy buenos días colegas Diputados, Diputadas. Para instalar la presente Sesión, solicito a nuestro Diputado Secretario, verificar el quorum reglamentario.

SECRETARIO, DIP. [N]: Muchas gracias. Buenos días, muchas gracias hermana Presidenta en ejercicios.
Vamos a proseguir a llamar lista para verificar el quorum correspondiente, vamos con Chuquisaca.
(Llama lista).
```
<!-- /table -->

The hand check was to count the words from one layer to the other. 17 were missing, all at page boundaries: the
engine's rule deletes the number in front of the page separator, and in *El Redactor* the folio comes after it. They
were annex cells, footnote calls and list dashes, none of them speech, and they were declared without changing the
engine (bo-0006). The `correct` command as its SKILL writes it fails, because argparse reads `'---PAGE'` as another
option; it has to be written `--page-break-marker=---PAGE`.

## 5. Metadata and duplicates: meta and dedupe

```text
/diaries-meta --country bo --all
/diaries-dedupe --country bo
```

`meta`'s automatic pass got the date, number and type right in three sessions, from the cover. It failed in two things.
The chair came out wrong in all four: the engine takes what follows the label of the office, and on the Bolivian cover
the name comes before it. And the 154th has no cover, because it starts after midnight inside the July volume. The
SKILL, besides, gives the most authority to the running head, which here belongs to the volume: it says the month and
the year, not the day, and for the 154th it says July although it is 1 August.

Reading the four sessions showed how this record writes the chair: the cover names the chair, so does its first mark,
and the changes are noted by the editors («-Asume la Presidencia, la Diputada …-», *the deputy takes the chair*). So the
chair goes by segment. This is the 153rd in its meta file, without the names: one segment opened by the cover and two by
hand-overs, with the marks of each gender that fall in each:

<!-- table:pais_meta -->
```extracto
{
 "date": "2024-07-31",
 "session_number": 153,
 "session_type": "ordinaria",
 "legislature": "2020-2025",
 "legislative_session": "2023-2024",
 "presidency": {"scope": "segments", "segments": [
  {"via": "prolegomena", "genero": null, "marcas": {"m": 38, "f": 0}},
  {"via": "relevo", "genero": "f", "marcas": {"m": 0, "f": 1}},
  {"via": "relevo", "genero": "m", "marcas": {"m": 55, "f": 0}}
 ]}
}
```
<!-- /table -->

Two questions:

- **The 154th.** Date and number come from the opening formula and from its cover, which is in the August volume
  (bo-0007).
- **The 76th.** A woman chairs it, but 5 of the chair's 65 marks say «PRESIDENTE»: they are the editors' errata, and the
  65 turns go to the same person (bo-0008).

`dedupe` found no duplicates. The check of our own was the 153rd-154th pair, which share a page of the volume: the cut
repeats no text. If the August volume were added, the 154th would appear twice, and then dedupe would have work to do.

## 6. The deputies before tag

```text
/diaries-deputies --country bo
```

`deputies` can run before `tag` when the record has a roll call with names, and it should: tag uses the register to
score the marks that carry no «DIP.». In *El Redactor* the secretariat reads the list at the opening, department by
department: 129, 129, 130 and 130 names, with the same split by department as the 130 seats. There is no excerpt
here: the roll call is a string of names, and those the layout splits across two lines would escape the masking.

The library's roll-call reader has Uruguay's anchors hard-coded («Asisten los señores Representantes:») and did not see
the Bolivian one: a reader of our own was needed. The 207 spellings of the four roll calls come down to 204 people (3
pairs differ by an accent or the word order). That is 74 more than seats, and they are the 74 who appear in a single
session: substitutes. The question was asked, and they were accepted as titular and substitute members, not told apart
(bo-0012, which corrects the wording of bo-0009's evidence: the first `--supersede` of this run). Committee duty counts
as absence (bo-0010): 478 presences and 40 absences. And party stays empty, and declared (bo-0011), because neither the
roll call nor the marks give it.

## 7. The speakers: tag

```text
/diaries-tag --country bo --all
```

The first pass on the 67th tagged 398 marks with the strict pattern and 5 with the loose one. Of those 5, 2 were the
deputies without «DIP.» and 3 were headings of a bill read out by the secretariat («ARTÍCULO ÚNICO:», *sole article*).
The scorer gave them 0.70, the same as a real five-word name: the threshold could not tell them apart. The question was
asked, and the loose pattern was made to need at least three words, since all 204 names in the register have three or
more (bo-0013, whose consequence bo-0020 later corrected). Second pass: only the two deputies.

tag's absolute gate, `verify_tagging`, found 0 untagged marks in the four sessions. This is the opening of the 76th now:

<!-- table:pais_capa_tagged -->
```extracto
76ª SESIÓN ORDINARIA LEGISLATURA 2023-2024 LA PAZ, MARTES 26 DE MARZO DE 2024 [N]
PRESIDENTE EN EJERCICIO DE LA CÁMARA DE DIPUTADOS

<int speaker="PRESIDENTE EN EJERCICIO">Bueno, muy buenos días colegas Diputados, Diputadas. Para instalar la presente Sesión, solicito a nuestro Diputado Secretario, verificar el quorum reglamentario.</int>
<int speaker="SECRETARIO">Muchas gracias. Buenos días, muchas gracias hermana Presidenta en ejercicios.
Vamos a proseguir a llamar lista para verificar el quorum correspondiente, vamos con Chuquisaca.
(Llama lista).
```
<!-- /table -->

Look at the tags: `<int speaker="SECRETARIO">`. The record's mark said «SECRETARIO, DIP. [N]:», and tag keeps only the
office. The name is still in the corrected layer, and that will matter in the next step.

## 8. The matrix and the linkage

```text
/diaries-matrix --country bo --all
/diaries-match --country bo
/diaries-merge --country bo
/diaries-standardize --country bo
```

**matrix** turns the tagged text into one row per turn. The first pass dropped an 8-character turn as too short; it was
a deputy's interjection, and it is speech (bo-0014). Its audit of embedded marks gave 0.00%, and the SKILL warns that a
0% is suspicious until explained. A search of our own for the terminator and the count of untagged lines found marks
buried inside other turns, 8 of them in one passage of the 67th, where the editors closed the marks with a full stop
(*the chair: «Thank you, colleague. We give the floor to colleague Deputy [N].»; the deputy: «Thank you very much,
President.»*):

<!-- table:pais_punto -->
```extracto
PRESIDENTE. Muchas gracias colega Diputado. Vamos a ceder la palabra al colega Diputado [N].
DIP. [N]. Muchas gracias Presidente.
```
<!-- /table -->

`verify_tagging` did not see them because it uses the same pattern as tag. The marks were made to accept «.» as well as
«:» (bo-0015), and the 67th went from 400 turns to 408; the other three sessions did not change.

**match** links each speaker form to the register. The first pass linked 0 of 76: the register had been written with
commas, one column held «;» and `fuzzy_match` guessed «;» as the separator. With the file fixed, 71 forms match a single
deputy and the other 5 are offices (PRESIDENTE, PRESIDENTA, SECRETARIO…), attributed in merge. The hand check crossed
each turn with its session's roll call: one mark named a deputy who was not in the chamber. The chair had just given the
floor «by allusion» to a woman deputy, and the speaker answers the allusion: the turn goes to her, by a session override
that leaves `speaker_raw` untouched (bo-0017).

**merge** joins the matrix with the linkage table and the register. The chair's rows are attributed by segment, but in
this run that had to wait: `attribute_presidency` reads the canonical file, which does not exist yet at this point, and
it ran inside standardize (below). With the chair already attributed, merge ended in FLAG, with a confidence of 0.794:
the 186 rows of the secretariat had no deputy. When asking, Claude Code said that whoever opens the secretariat is not named in
the record, and on that evidence it was decided to declare it and accept (bo-0022). It was false: the opening of the
76th shows it, the secretariat's first mark carries the name, and tag had kept only the office. It came to light when
comparing the layers for this page. The question was asked again with the right evidence, and the secretariat was
attributed by segment in the three sessions that name it, like the chair (bo-0025). The check: before a secretariat
turn the chair often calls the secretary by name («Secretaria, Diputada …»), and the 39 vocatives that can check it all
agree. The 154th starts mid-sitting, with no named mark, and its 26 rows stay without a deputy:

<!-- table:pais_vinculacion -->
| Who speaks | Rows | With id_dep | People |
|---|---:|---:|---:|
| Deputies («DIP.» mark) | 260 | 260 | 70 |
| Chair | 456 | 456 | 2 |
| Secretariat | 186 | 160 | 4 |
| **Speech rows** | 898 | 872 |  |
<!-- /table -->

**standardize** applies the final 16-column schema, and here the SKILL's order did not work for a new country: five
library scripts read the canonical file, which does not exist yet at that point. And one of them,
`attribute_presidency`, had a defect: if the cover row was already in the file, it counted the turns one way when
attributing and another when looking for the hand-overs, and each hand-over landed one row early. In the 153rd, the woman
deputy who takes the chair for one turn went back to the previous chair (*a deputy's turn ends with the note that she
takes the chair; she calls a one-hour recess; the note that he takes it back*):

<!-- table:pais_relevo -->
```extracto
DIP. [N]: … -Asume la Presidencia, la Diputada [N]-
PRESIDENTA: Ausencia, Cuarto Intermedio, colegas Diputados, Diputadas, 1 hora.
-Reasume la Presidencia, el Diputado [N]-
```
<!-- /table -->

The way out was to attribute the chair before adding the covers (bo-0018) and to put the whole chain in a script that
runs twice and comes out identical byte for byte. After this run, the library fixed the defect on 25 October 2026: the
cover no longer counts as a turn, and the chair comes out the same with it or without it. Personal data came in at this step too: the 1,674 identity-card
numbers of the documents read out become «[C.I.]» (bo-0021, which corrects bo-0016's row count); the beneficiaries'
names stay, and are declared.

And sex. The library's script has its country list hard-coded; with Bolivia added, only the given-name morphology
fires, and it gives sex to 51% of speakers, 71% of them women. The signal of the Bolivian record is elsewhere: the chair
calls whoever will speak next («colega Diputada …», *colleague Deputy*). With that vocative, the hand-over note and the
secretariat's office, 72 of the 73 people who speak have sex; morphology completes the register and is right in 36 of
36 cases, but it covers 84% of women and 23% of men, so the register's blanks are almost all men (bo-0024, which
corrects a count of bo-0019). The gender judge, which compares the sex of whoever chairs with the vocative of whoever
answers, only recognised the formal title («Señor Presidente»); with the Bolivian vocative 345 of 349 rows agree, and
the 4 discrepancies are explained. One is the secretary's slip between two «Presidente» (*the support is there,
President; the vote; absolute majority, Madam President*):

<!-- table:pais_lapsus -->
```extracto
SECRETARIA: Existe el apoyo, Presidente.
PRESIDENTE: Las y los Diputados que estén de acuerdo con la Dispensación de la lectura del Informe del Proyecto de Ley No 248/2023-2024, sírvase levantar la mano. Informe, Diputada Secretaria.
SECRETARIA: Mayoría absoluta, Presidenta.
```
<!-- /table -->

## 9. Validating

```text
/diaries-validate --country bo
```

`validate` draws a seeded sample of 300 rows, checks each one and sets aside 200 PASS rows for a person to read looking
for leaks: another speaker's text inside a turn, which no automatic test sees. The first pass raised one FLAG for
corrupted characters: bullets from a symbol font that the PDF gives as private-use characters. There were 35 in the
whole corpus, and they became «•» (bo-0023). The person building the corpus chose to read all of them.

<!-- table:pais_validacion -->
| Check | Result |
|---|---|
| Seeded sample, first pass | 300 rows: 299 PASS, 1 FLAG |
| The same sample, with the secretariat attributed | 300 PASS; 11 not applicable |
| Leak calibration: PASS rows read by hand | 200; marked as leaks, 0; 95% CI (Wilson) [0% – 1.88%] |
| Of them, secretariat turns attributed afterwards | 30, to be checked apart |
| Identity-card numbers → «[C.I.]» | 1,674 in 4 rows |
| Private-use bullets → «•» | 35 in 6 rows |
<!-- /table -->

With 0 leaks in 200 rows, Wilson's interval reaches 1.88%, and that is the figure published; the script announces
«< 1.5%», from the rule of three, which falls short with samples like this. The seed makes the sample repeatable: with
the secretariat attributed, the same 300 rows give 300 PASS. But 30 of the 200 calibration rows are secretariat turns
read before they had a deputy, so their attribution is checked apart, with the previous turn alongside.

## 10. Documenting, reporting and recording

```text
/diaries-document --country bo
/diaries-report --country bo
```

`document` interviews the processor (the source, the register, the process, the authors and the limitations) and
writes `corpus_info.json`, the README, the data dictionary and the `dataset.jsonld` metadata, which declare the two
files of the delivery. Linkage is published with the collection's definition, tr-0109: gross and effective, 97.1% of
speech rows. They are equal because nothing is discounted: deputies hold the secretariat, so its unnamed rows are a gap
of this corpus, not an exclusion. The first time, Claude Code computed the gross rate over all rows rather than over
speech rows; the linkage script compares it with what is published, it did not match, and it was corrected.

`report` writes the internal report of the process. The pipeline state says «100% automation», because no step ended
in an unresolved FLAG or HALT. The report puts first what the state does not see: 25 questions answered, 25 decisions,
76 speaker forms reviewed and frozen, 200 rows read by hand and 14 local scripts. This is how each skill ended
(bootstrap and dedupe write no state entry):

<!-- table:pais_estado -->
| Skill | 67th | 76th | 153rd | 154th | Country |
|---|---:|---:|---:|---:|---:|
| `diaries-ocr` | skipped | skipped | skipped | skipped |  |
| `diaries-extract` | 1.00 | 1.00 | 1.00 | 1.00 |  |
| `diaries-correct` | 0.95 | 0.95 | 0.95 | 0.95 |  |
| `diaries-meta` | 1.00 | 1.00 | 1.00 | 0.97 |  |
| `diaries-tag` | 0.92 | 0.85 | 0.97 | 1.00 |  |
| `diaries-matrix` | 1.00 | 0.99 | 0.99 | 1.00 |  |
| `diaries-deputies` |  |  |  |  | 1.00 |
| `diaries-match` |  |  |  |  | 0.93 |
| `diaries-merge` |  |  |  |  | 0.97 |
| `diaries-standardize` |  |  |  |  | 1.00 |
| `diaries-validate` |  |  |  |  | — |
| `diaries-document` |  |  |  |  | 1.00 |
| `diaries-report` |  |  |  |  | 1.00 |
<!-- /table -->

The decision log is the history of the corpus. Five decisions were corrected with `--supersede`, and none was deleted:
two wrong counts, a badly worded piece of evidence, a misdescribed consequence and a false piece of evidence.

<!-- table:pais_decisiones -->
| Id | Step | Decision | Status |
|---|---|---|---|
| bo-0001 | sources | Method sample: 4 Chamber sessions, from March and July 2024; joint sessions left out. | in force |
| bo-0002 | sources | The monthly volumes are cut into one PDF per session at its title page; preliminaries and index left out. | in force |
| bo-0003 | sources | 31 July holds two sessions, the 153rd and the 154th. | in force |
| bo-0004 | extract | The 67th is extracted in faithful mode although the fragmentation gate fires (55 pages of annex table). | in force |
| bo-0005 | correct | One piece of page furniture, the running head, and reflow D, with boxes of up to 6,000 characters. | in force |
| bo-0006 | correct | The 17 words that the folio rule drops at page boundaries are declared, without changing the engine. | in force |
| bo-0007 | meta | Date, number and type come from the cover; for the 154th, from the opening formula and the August volume's cover. | in force |
| bo-0008 | meta | In the 76th, the 5 stray «PRESIDENTE:» marks are errata for the presiding woman. | in force |
| bo-0009 | deputies | The roster comes from the roll calls. | superseded by bo-0012: its evidence was badly worded |
| bo-0010 | deputies | Attendance per session: leave, sick leave and committee duty count as absence. | in force |
| bo-0011 | deputies | party stays empty, and is declared: the record does not give it. | in force |
| bo-0012 | deputies | Roster from the four roll calls, 204 people; titular and substitute members not told apart. | in force; replaces bo-0009 |
| bo-0013 | tag | Marks without «DIP.» need at least 3 words. | superseded by bo-0020: its consequence misdescribed what verify_tagging would see |
| bo-0014 | matrix | The matrix drops no turn for its length: an 8-character interjection is speech. | in force |
| bo-0015 | tag | Level-1 marks accept «.» as a terminator. | in force |
| bo-0016 | standardize | Identity-card numbers are pseudonymised in the canonical file. | superseded by bo-0021: it counted 3 rows with identity numbers; there are 4 |
| bo-0017 | match | The turn whose mark names an absent deputy goes, by override, to the deputy alluded to. | in force |
| bo-0018 | standardize | The chair is attributed before the covers are added, to sidestep a defect of attribute_presidency. | in force |
| bo-0019 | standardize | sex comes from the vocative and the given name's morphology. | superseded by bo-0024: it said 35 of 35; it is 36 of 36, and coverage by sex was missing |
| bo-0020 | tag | The level-2 pattern needs 3 to 6 words. | in force; replaces bo-0013 |
| bo-0021 | standardize | Identity-card numbers become «[C.I.]» in the canonical file. | in force; replaces bo-0016 |
| bo-0022 | merge | The secretariat is declared without id_dep. | superseded by bo-0025: its evidence was false: the secretariat's first mark does name the holder |
| bo-0023 | standardize | The private-use bullets become «•». | in force |
| bo-0024 | standardize | sex comes from the vocative, the hand-over note and the morphology, with coverage measured by sex. | in force; replaces bo-0019 |
| bo-0025 | merge | The secretariat is attributed by segment in the 3 sessions that name it. | in force; replaces bo-0022 |
<!-- /table -->

This is what went wrong, whose it was and how it showed. The failures of the skills and of the library are the list for
`/diaries-refine`; the agent's are the reason for the hand checks.

<!-- table:pais_fallos -->
| Whose | Step | What went wrong | How it showed | What was done |
|---|---|---|---|---|
| agent | match | the roster was written with commas and one column held «;»: `fuzzy_match` took «;» as the separator | 0 of 76 forms linked on the first pass | roster with «;»; the 204 ids unchanged |
| agent | merge | bo-0022's evidence was false: that whoever opens the secretariat is not named | comparing the layers for this page | asked again; bo-0025 attributes 160 rows |
| agent | report | gross linkage was computed over all rows, not over speech rows | `vinculacion_tr0109.py` did not match corpus_info.json | corrected, and the documentation regenerated |
| agent | meta, merge | two counts misstated in a question: «54 of 59» for 59 of 65, and «160 of 162» for 160 of 160 | when recording the decision | the decision carries the right figure |
| agent | tag | four writes to the state file at once | all four landed, but it is a race | in series from then on |
| library | standardize | `attribute_presidency` counts the cover row in one place and not in another: each hand-over lands one row early | row 77 of the 153rd went back to the previous chair | the chair is attributed before the covers are added (bo-0018); the library fixed it on 25 October 2026 |
| library | merge | there is no attribution for the secretariat, and tag keeps only the office | 186 secretariat rows without id_dep | a local script (bo-0025) |
| skill | matrix | `verify_tagging` and matrix's audit use the config's terminator: marks closed with a full stop are invisible to both | a search of our own for the terminator | bo-0015: marks accept «.» |
| skill | correct | the SKILL's command fails: argparse reads `'---PAGE'` as another option | on running it | `--page-break-marker=---PAGE` |
| library | deputies | `parse_attendance.py` has Uruguay's roll-call anchors hard-coded | it did not see the Bolivian roll call | a reader of our own |
| library | standardize | `derive_sex.py` has its country list hard-coded; with Bolivia added, only morphology fires | sex for 51% of speakers, 71% of them women | vocative, hand-over note and morphology (bo-0024) |
| skill | validate | `prepare_leak_calibration.py` announces «< 1.5%» for 0 of 200 (rule of three) | computing the interval | Wilson's is published |
<!-- /table -->

And these are the local scripts: what no skill covered, or what the library did wrong. They are not in the repository:
they belong to this project, and one of them holds deputies' names.

<!-- table:pais_scripts -->
| Script | What for |
|---|---|
| `auditoria_genero_bo.py` | the gender judge, with the Bolivian vocative |
| `completar_canonico_bo.py` | what `recover_frontmatter` and `attribute_presidency` leave empty |
| `cortar_tomos.py` | cuts the volumes into one PDF per session |
| `indices.py` | reads each volume's index: which sessions it holds |
| `meta_bo.py` | applies meta's heuristic as registered for Bolivia |
| `padron_bo.py` | the roster from the roll calls |
| `pase_de_lista_bo.py` | reads the roll call: `parse_attendance.py` only knows Uruguay's |
| `secretaria_bo.py` | the secretariat by segment (bo-0025) |
| `seudonimizar_ci_bo.py` | identity-card numbers → «[C.I.]» (bo-0021) |
| `sexo_bo.py` | sex from vocative, hand-over and morphology (bo-0024) |
| `standardize_bo.py` | standardize, declaring the columns left empty by decision |
| `standardize_cadena_bo.sh` | the standardize chain in the order that works |
| `tabla_match_bo.py` | the linkage table and the session override |
| `vinetas_bo.py` | private-use bullets → «•» (bo-0023) |
<!-- /table -->

## 11. Checklist

1. Write down what the corpus is for and how much coverage it needs: it is the first decision in the log.
2. Work in a separate folder, with copies of the source and their hash; one file per session, named by its date.
3. What no skill does (cutting volumes, reading an index) goes into a local script, and is checked: the words before
   and after.
4. Read the configuration `bootstrap` writes.
5. If an `extract` gate fires, find out why before choosing the mode: here it was a table with private persons' data.
6. Measure the reflow variants in `correct` and count the words lost from one layer to the other.
7. Check each session's date, number and chair against its cover, and by segment.
8. If the record has a roll call, build the register before `tag`.
9. Read one by one the marks the loose pattern tags.
10. A 0% of embedded marks is suspicious: search for the terminator with a pattern of your own.
11. A first linkage of 0 is a problem with the file, not with the linking.
12. Cross each linked speaker with their session's roll call.
13. Before accepting a FLAG, compare the layers: what tag did not keep may be in `corrected/`.
14. Run the `standardize` chain twice and compare byte for byte.
15. Pseudonymise identity-card numbers and declare what remains.
16. Measure sex coverage by sex, not only overall.
17. Read the leak calibration yourself, and publish Wilson's interval.
18. Every decision with measured evidence; wrong ones are corrected with `--supersede`, never deleted.
19. The automation rate, always next to the human decisions.

> **Ask for it all at once:** «I want to build, with the diaries-* skills, a corpus of this chamber's plenary sessions
> from the PDFs in `source/{iso2}/raw/`, one file per session. Go step by step, from `/diaries-bootstrap` to
> `/diaries-report`; before each question show me the measured evidence, and record each answer with
> `/diaries-decide`. Check by hand what each skill cannot see of itself: the words from one layer to the next, the marks
> it leaves untagged, the speakers against the roll call and what tag does not keep. If a skill or the library fails,
> don't patch them: write a local script, note it and tell me at the end for `/diaries-refine`. Pseudonymise
> identity-card numbers and quote no private person's name.»
