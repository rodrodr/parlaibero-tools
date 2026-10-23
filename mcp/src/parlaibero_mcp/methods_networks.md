# Network tools: method

Three tools build networks on a **library** (`library_create`), for any topic and any of the 16 countries. They
answer different questions and are **never mixed in one network**:

| tool | nodes | an edge means | question |
|---|---|---|---|
| `cooccurrence_network` | **words** and multi-word expressions, found in the library itself | they occur in the same intervention more than chance | what is talked about: themes |
| `comention_network` | **actors** you list: people and institutions | both are mentioned in the same intervention | which actors are discussed together, and by whom |
| `mention_network` | **people**: speakers, deputies, external actors you declare | A names B on the floor (directed) | who talks about whom |

A word or a concept is never an actor: `comention_network` refuses `concepto` and points to
`cooccurrence_network`, and `cooccurrence_network` takes no entities.

All three write their files only to an **absolute** `output_dir`, are deterministic for a given `seed`, are
recorded in `query_log`, and cite each dataset by DOI and version in every output. A library with several
countries gives **one network per country**: a speaker can only name the members of their own chamber, and the
vocabulary of each chamber is its own. `pooled=True` merges the countries in `comention_network` when that is what
you want.

---

## 1. `cooccurrence_network`: words and themes

The method of the Diarios Explorer (`engine/coocurrencia.js`), **ported line by line** (`cooccurrence.py`) and
tested against the explorer's own code, which the test suite runs in Node: tokens, stretches, the segmentation of
speech, expressions, the lexicon and the whole network (nodes, edges, themes, parties and reading lists) are
identical on a test corpus, and the MCP tool gives the explorer's network on a store built from that corpus.

### Vocabulary

- **Lexicon.** Every term of the library is compared with the rest of the country's corpus (corpus − library):
  signed G² of Dunning on the full 2×2 table, |G²| ≥ 10.83 (p < 0.001), frequency ≥ 5, the 2,000 most over-used.
  Tokens: lower case, runs of letters and digits, accents folded (`Previdência` = `previdencia`).
- **Expressions.** The corpus's multi-word expressions (`reforma da previdência`, `teto de gastos`), detected once
  over the whole country by the explorer, are counted and measured like words, and joined into one token in the
  text, so each is one node. Their tables are downloaded once from the explorer's site and used only if they were
  built from the loaded dataset (DOI, version, file size, SHA-256); otherwise the network is built without them
  and the output says why. `expressions=false` leaves them out.
- **Nodes:** the first `vocabulary` (250) terms of the lexicon, without numbers (digits or numerals written out)
  and without the **Snowball** stopwords of the language (Portuguese for Brazil and Portugal, Spanish otherwise;
  `estado`, `estados` are kept), BSD-3-Clause, recorded in every output. `exclude` drops terms after reading the
  themes.

### Text and unit

- **Speech only** (`speech_only`, default): stage directions in brackets and upper-case lines (vote lists,
  headers) are left out, as in the explorer's fast segmentation. Rows marked `dm_speech = 0` are not in the text.
- **Unit:** the intervention (default) or consecutive fragments of `fragment` tokens (20) within it.

### Edges and themes

- **Association:** signed G² on the 2×2 table of units; kept if positive and G² ≥ 10.83 **and** among the
  `neighbours` (10) highest-G² edges of either term.
- **Weight:** association strength, observed / expected (van Eck and Waltman 2009, as VOSviewer). The G² decides
  which edges exist; the strength, how much they weigh.
- **Themes:** Leiden communities (resolution `resolution`, seed `seed`) of three terms or more; smaller ones are
  listed as loose terms. Themes are ordered by the mean G² of their terms in the lexicon: how characteristic of
  the library they are.
- **Per theme:** its terms by internal strength; the interventions that use any of them; the words of the
  interventions it dominates (the theme with the largest share of its own vocabulary present); the theme's words
  said by each party, and that party's words in the library, so a **rate per 1,000 words** compares parties of
  different size; a **reading list**: BM25 (k1 = 1.2, b = 0.75) with ln(1 + G²) as the term weight.

### Differences from the explorer

- Reference counts come from every row of the country in the MCP's database (the explorer reads its FTS5 index
  of the same rows; the two tokenizers differ by about one token in a million).
- Speech only uses the fast segmentation for any library; the explorer applies its full parser of the record
  below 25 million characters.
- Displayed forms are the country's most frequent written form of each word.

---

## 2. `comention_network`: actors mentioned together

### Unit and counts

- **Unit:** the intervention. **N** = interventions of the library after the filters (`date_from`,
  `date_to`, `exclude_chair`, `max_turn_words`).
- **Actors:** `[{name, type, pattern, exclude}]`. `type` is `persona` or `institucion`; anything else is
  refused (words and concepts are the nodes of `cooccurrence_network`).
  `pattern` is a regular expression matched on the text in lower case without accents, so `nacion`
  matches «Nación». It must also be valid in RE2, the engine that pre-filters the rows: no look-behind,
  no back-references. `exclude` removes the matches that also match it.
- **The longest match wins.** If two entities match overlapping spans, only the longer one counts:
  «maria pereira» belongs to the entity *Maria Pereira* and does not also count for *Pereira*. Use this,
  and `exclude`, to separate people who share a surname.
- **n(a)** = interventions where entity *a* appears. **co(a, b)** = interventions where both appear.

### Measures

| measure | definition | reads as |
|---|---|---|
| `co` | interventions with both | **volume**: how often they are discussed together |
| NPMI | ln(p(ab) / (p(a) p(b))) / (−ln p(ab)); 1 if co = N | **affinity** beyond chance, from −1 to 1; 0 = independent |
| Jaccard | co / (n(a) + n(b) − co) | overlap |
| bias | (n₁/N₁ − n₂/N₂) / (n₁/N₁ + n₂/N₂) | which of two groups talks about the entity more, from −1 to 1, per intervention of each group |

Read `co` and NPMI together. Two very frequent entities have a high `co` and an NPMI close to 0: they are
mentioned together because both are everywhere. Two rare ones can have a high NPMI and a `co` of 3.
Thresholds are applied to the **unrounded** NPMI.

- **Edges kept:** `co ≥ min_co` and NPMI ≥ `min_npmi` (0.10 by default). `min_co` defaults to
  `max(5, round(N / 120))`, so it scales with the library, and is reported.
- **Groups** (optional): `groups={"g1": [...labels], "g2": [...labels]}` on `group_by` (party by default).
  Labels are matched case-insensitively. Rows whose label is in neither group count as `rest`, and the
  unmatched labels are listed, never guessed. No political classification is built in.
- **Communities:** Leiden (Traag et al. 2019) on `co`. It is a port of the Diarios Explorer's
  implementation: same random generator, same result for the same seed.
- **Centrality:** betweenness (Brandes; distance = 1/co) and strength.

### Without `entities`

The tool proposes candidates and builds nothing: proper names and acronyms of a sample. Confirm or edit them
and call it again.

### Ambiguity alerts

The tool warns, by rule rather than by list, about:
- **short patterns** (under 5 characters), unless at least 80 % of their matches are in capitals (acronyms);
- **people or institutions** written mostly in lower case (a common word);
- **surnames** shared by two or more deputies in office;
- **entities in more than 80 % of the library**: they are its subject, not a node.

---

## 3. `mention_network`: who names whom

### What counts as a mention

An arrow **A → B** counts the interventions of speaker A that name B.
- **B is a deputy** of the chamber who was **in office that day**, according to the published register.
  A term with no end date closes the day before the next legislature in the register begins.
- **B can also be an external actor** you declare: `external_actors=[{name, aliases, role}]`, such as a
  head of government, a judge or a body. Nothing is built in.

Names come from the register:
- **The full name** counts anywhere.
- **A surname alone** counts only right after a title:
  - **a legislative title:** deputy, member, congressman, *diputado/a*, *deputado/a*, *parlamentar*…;
  - **an honorific:** *señor/a*, *sr./sra.*, *don/doña*…, **by default only in Spanish**. In Spain
    «señor X» named a member 95 times out of 96 across three samples. In the Brazilian chamber «sr./senhor X»
    names ministers, judges or a former president as often as members (see the validation below). Portugal
    was not measured and inherits the Portuguese default. `honorifics=True` or `False` overrides the default.
- Each mention records which of the three licensed it (`licensed_by`), so precision can be measured by class.

Surname aliases:
- **Spanish:** the first surname, or both surnames.
- **Portuguese:** the first or the last surname.
- **Comma-less parliamentary names** («DR. JOÃO TAVARES»): only the last word is surely a surname.
- **Never an alias:**
  - a word the register uses mostly as a given name;
  - a title complement («deputado **federal**»);
  - a party acronym;
  - a phrase that starts with a particle («da …»);
  - one of the chamber's commonest words, unless it is the deputy's own surname.

### What does not count

- **The record's own notes in brackets.** «(The Speaker leaves the chair.)» and «(Mr X: Hear, hear!)»
  are counted apart as `editorial`.
- **Self-mentions.**
- **Plural titles** («Srs. Deputados, Brasil…»), **religious formulas** («nosso Senhor Jesus»), and a title
  whose **gender** contradicts the deputy's sex in the register.
- **A name that goes on.** If a surname is followed straight away by another register surname or by an
  uncommon word, it is someone else who shares a name with the deputy. This favours precision over recall:
  a rare word right after a surname also drops a true mention.
- **A surname shared with a declared external actor.** It needs the deputy's full name.
- **Forms with no name** («V. Exa.», «Su Señoría», «the honourable member») cannot be resolved. They are
  only counted.

### Two kinds of mention

- **`reference`:** talking **about** someone. This is the default (`mention_kinds=["reference"]`).
- **`address`:** speaking **to** someone. These are vocatives («Thank you, Deputy X.», «Sr. Presidente,
  Deputado X, …», «Señora X y señor Y, …») and a second person right after the name.

`mention_kinds=["reference", "address"]` counts both.

### Homonyms

When an alias fits several deputies in office, the tool tries, in this order:
1. the gender of the title;
2. a given name written right after the surname («Durán, don Eduardo»);
3. a party acronym written next to the name.

Whatever is still ambiguous goes to `ambiguas.csv`. It is **never assigned at random**.

### Measures

- **Strength:**
  - in-strength: interventions that mention the person;
  - out-strength: interventions in which the person mentions others.
- **PageRank** and **Leiden communities**, on the symmetrised weights.
- **Reciprocity:** the share of arrows returned. It is computed only between people who speak in the
  library, because an external actor or a silent deputy cannot answer.
- **Group → group matrix:** mentions per 100 interventions of the sending group.
- **E-I index** per group: (out-group − in-group) / total. It counts mentions between deputies only.
- **Strongly asymmetric pairs:** A names B at least 5 times and B names A at most a fifth as often.
  Only between speakers.

### Known limit

A person outside the chamber with **exactly the same full name** as a deputy is taken for the deputy: a
minister and a deputy with the same name, for instance. Declare that person as an **external actor**.
External actors are matched first, so this keeps them from being taken for the deputy.

### Validation

Measured on 14 October 2026. Independent reviewers labelled random samples of resolved mentions by reading
each one in context, and the full speech when needed. The rules were corrected between rounds, and each
round used a **new** sample.

| round | Brazil: right person | Brazil: right kind | Spain: right person | Spain: right kind |
|---|---:|---:|---:|---:|
| 1 (first rules) | 86 / 100 | 67 / 100 | 48 / 50 | 38 / 50 |
| 2 | 96 / 100 | 87 / 96 | 49 / 50 | 48 / 50 |
| 3 | 100 / 100 | 100 / 100 | 50 / 50 | 48 / 50 |

- **Brazil, round 3:** 75 of the 100 mentions were of the three declared external actors, and none was
  licensed by an honorific.
- **Spain, round 3:** the two errors were coordinated vocatives. A rule added afterwards handles them.

**Round 4**

Two samples:
- **Brazil, deputies only,** with no external actors declared, stratified by licence:
  - after a legislative title: right person 35 / 35;
  - by full name: 21 / 25, all four errors homonyms outside the chamber (see the known limit);
  - after an honorific: 18 / 40, mostly «sr. X» meaning the former president who shares the surname of a
    deputy.

  This round is why honorifics license a surname **only in Spanish by default**. In Spain the honorific
  path was right 31/31, 29/30 and 35/35 in rounds 1–3. Of the 74 mentions with the
  right person, 70 had the right kind; rules added afterwards handle two of the four misses.
- **Chile,** a chamber the rules were never adjusted on, 60 mentions: right person 60 / 60, right kind
  60 / 60.

  24 of the 60 were in text read into the record: lists of a bill's authors, committee replacements and
  vote tallies. They are correct mentions, but they are not debate.

Check a sample of your own: `validation_sample=100` writes a CSV with the context of each mention and
two empty columns to label.

---

## 4. Drawing

The pages draw every network the same way, so that the ink says what the data say:

- **Zoom moves the points, not the marks.** Nodes, lines, labels and arrowheads keep their size on screen at any
  zoom; zooming in separates the nodes instead of inflating them.
- **Node size:** √ of the size measure, between 2.5 px and the **«node size»** control (12 px of radius by default;
  `max_node_size` sets it, 4–40).
- **Lines are thin.** Width: √ of the weight between 0.4 px and the **«edge width»** control (1.5 px by default;
  `max_edge_width`, 0.5–6); the weight is read in the tooltip and the tables, and opacity carries a second measure
  (NPMI or G²). A wide invisible band keeps thin lines easy to point at.
- **Arrowheads have a fixed size** (6 px), whatever the width of their line, and their tip touches the edge of the
  target node.
- **Three layouts**, chosen with `layout` and switchable in the page:
  - `force` (default): force-directed, computed before drawing with a fixed seed.
  - `clusters`: each group (theme, community or party) is laid out on its own with its internal edges, then the
    groups are placed as named discs kept apart by a fixed gap, those with more edges between them a little closer;
    the edges between groups recede. Themes read as separate islands.
  - `rings`: the Diarios Explorer's centrifugal layout. Rings by the number of distinct connections among the edges
    shown (the 3 % most connected in the core, then the next 7 %, 15 %, 30 % and the rest; ties are never split),
    sectors by group, clockwise from 12 by weight, each ordered from the most to the least connected; edges curve
    towards the centre. Rings and sectors are recomputed when the thresholds change. The rings grow with √ of the
    nodes beyond 60, so a large network keeps its spacing.
- **Up to 30 colours.** Each theme, community or party has its own colour up to 30 (a 31st and beyond are gray). The
  first 8 are the reference palette; the other 22 were chosen to be as far apart as possible within the lightness
  band and the chroma floor, each with its dark-theme step, and ordered so that neighbours in the order are told
  apart in both themes, also under colour-blindness (`validate_palette.js`: adjacent CVD ΔE ≥ 8.4, normal vision
  ≥ 18.7). Thirty hues cannot all be told apart pairwise, so names on the discs, sectors and legend, the theme
  selector and the tables carry identity too.

## 5. Outputs

| file | content |
|---|---|
| `*.html` | Interactive page: the network, controls and examples on click, light and dark themes, and keyboard use. Every figure is also in a table. The data are embedded, and the page is checked against them after it is written; a mismatch deletes the file and raises an error. |
| `*_nodes.csv`, `*_edges.csv` | the network, with every measure |
| `*_themes.csv` | `cooccurrence_network` only: each theme with its terms |
| `*_block_matrix.csv`, `*_ambiguas.csv`, `*_validation_sample.csv` | `mention_network` only |
| `*.json` | everything above, with the parameters and checksums |
| `*_summary.md` | a short summary with the citation |

The pages load d3 7.8.5 from cdnjs. Nothing else leaves your machine.

## 6. Cite

Each output lists the dataset of every country used, with its DOI and version (see `how_to_cite`).
Name the tool and the engine version, which is printed in every output.
