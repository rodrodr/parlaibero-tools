# A library from scratch

<!-- eyebrow: Guide · Step by step -->

*[Versión en español](../es/bibliotecas.md) · [Tutorial index](../TUTORIAL.en.md)*

The studies in this tutorial show what can be done with a library. This guide teaches how to make one: how to go from
a question to a definition, how to test it, what to do when it fails, and how to use and maintain it afterwards. A
library is a named set of interventions, saved on your computer, that marks out a study: a topic, a period, a group of
speakers, or all three, in one country or in several. Every analysis tool then works inside it with `library=`. The
example question is a real one: how the floors of Colombia, Peru, Ecuador and Chile debated the arrival of Venezuelan
migrants since 2015. Answering it takes two definitions, because the first one fails in one of the four chambers.

<!-- side -->

**The chain of this guide**

1. `term_counter`: test the words
2. `kwic`: read what is surprising
3. `library_create`: a first definition and its threshold
4. `library_combine`: cross two libraries
5. `library_describe`: what is in it before comparing
6. `kwic`: read a sample in each chamber
7. `library_create`: a second, narrower definition
8. `library_edit`: remove what is not debate, and annotate
9. `query_sql` and `distinctive_words`: use the library
10. `library_combine`, `query_sql` and `kwic`: read what is left outside
11. `library_rebuild`, `library_export` and `library_delete`: maintain it

## 1. Library or filters?

Every analysis tool takes filters: countries, dates, party, sex, without the chair, without the long turns. Counting
a word or drawing its curve does not need a library. You need one when the object of the study is not a word but a
set that has to be defined, and that you come back to many times.

| If you want to… | Filters are enough | A library is better |
|---|:---:|:---:|
| count a word or see its curve | ✓ |  |
| compare groups across all the speech of a few years | ✓ |  |
| study a topic that is said with several words, and that naming once is not enough for |  | ✓ |
| read, count, compare and draw networks on the same set |  | ✓ |
| remove by hand what does not belong, or annotate interventions |  | ✓ |
| give each country its own definition or its own date |  | ✓ |
| open the set in the Diarios Explorer or pass it to someone else |  | ✓ |

A library is focused in three ways, which combine:

- **A topic**: `terms`, with `min_occurrences` to keep the interventions that discuss it and not those that mention it,
  or `regex=true` for a regular expression.
- **A period**: `date_from` and `date_to`, or a different date in each country with `event_dates`, `days_before` and
  `days_after`, as in the [pandemic library](pandemia.md#3-a-library-around-11-march).
- **A group**: `party`, `sex` or `id_dep`, for the speeches of a party, of the women deputies or of one person.

A topic within a period, in a single country, is the [library of Brazil's two pension
reforms](marcos.md#1-the-library-of-the-two-reforms). This guide makes one in four countries and dwells on the
definition, because the topic is said with ordinary words that mean different things in each chamber.

## 2. From the question to the definition

Before opening a tool, write the question down and take it apart. Each part becomes a parameter, and whatever you do
not decide here the agent decides for you.

| Question | In this guide | Parameter |
|---|---|---|
| About what? | the arrival of Venezuelan migrants: not migration in general, nor Venezuela's politics | `terms`, `regex`, `min_occurrences` |
| Where? | Colombia, Peru, Ecuador and Chile, four destination countries of Venezuelan emigration | `countries` |
| When? | since 2015, so that the series starts before the large arrivals | `date_from` |
| Who? | the whole floor, except whoever chairs the sitting | `exclude_chair` |
| What for? | count year by year in each chamber and compare what each one talks about | how much precision is needed |

The last row matters more than it seems. For a trend, the definition has to measure the same thing in the four
chambers and in every year. To compare vocabularies, the set has to be clean: a few interventions about something else
are enough to push their words up the list. That is why a definition is judged not by how many interventions it
brings, but by how many of those it brings answer the question.

## 3. Test the words

> **Ask:** "How many times are *migrante*, *migración*, *migratorio*, *inmigrante*, *refugiado*, *desplazado* and
> *venezolano* or *Venezuela* said on the floors of Colombia, Peru, Ecuador and Chile since 2015?"
>
> *The agent uses* `term_counter` (`terms="migrante*, migraci*, migratori*, inmigra*, refugiad*, desplazad*, venezolan*+venezuela"`,
> `countries=["CO", "PE", "EC", "CL"]`, `date_from="2015-01-01"`). Commas separate terms that are counted apart; the
> `+` sign adds variants into a single term.

<!-- table:bib_terminos -->
| Term | Chile | Colombia | Ecuador | Peru | Interventions (all four) |
|---|---:|---:|---:|---:|---:|
| `migrante*` | 1,500 | 415 | 5,269 | 450 | 2,434 |
| `migraci*` | 1,850 | 455 | 1,399 | 1,129 | 2,490 |
| `migratori*` | 1,379 | 293 | 2,341 | 601 | 1,769 |
| `inmigra*` | 1,149 | 36 | 288 | 72 | 841 |
| `refugiad*` | 187 | 103 | 685 | 103 | 416 |
| `desplazad*` | 114 | 617 | 202 | 122 | 842 |
| `venezolan* + venezuela` | 1,495 | 3,108 | 2,226 | 1,737 | 3,418 |
<!-- /table -->

Three figures call for a reading before anything is defined.

> **Ask:** "Show me twelve random uses of *desplazado* in Colombia, sixteen of *venezolano* in the four countries and
> twelve of *migrante* in Ecuador."
>
> *The agent uses* `kwic` (`pattern="desplazad*"`, `countries=["CO"]`, `n=12`), and the same with the other two.

- **Desplazado** (displaced) is said more in Colombia than in the other three countries together. The twelve
  interventions read (out of 488) talk about internal displacement by the armed conflict. It is another topic: it
  stays out.
- **Venezolano** on its own is not enough. Of the sixteen interventions read (out of 1,434), six talk about migrants;
  the rest, about Venezuelan politics, military incursions at the border, the economy or a criminal gang. A migration
  word is needed next to it.
- **Migrante** is said 5,269 times in Ecuador, three and a half times more than in Chile. The twelve interventions read
  (out of 1,241) talk about Ecuadorians abroad (remittances, consulates, returnees, the assembly members elected by the
  emigrants) or about human trafficking. In Ecuador, a *migrante* is first of all the Ecuadorian who left.

> [!TIP]
> A term does not count the same thing in each chamber. Before putting it into a definition, read a random sample in
> each country where its figure is surprising: twelve or twenty lines are enough to see whether it is about what you
> are looking for.

## 4. First definition: a threshold and a cross

The first library gathers the migration topic. The `min_occurrences` parameter says how many times the terms must
appear in an intervention: with 1, any intervention that names them comes in; with 2 or 3, those that discuss it. The
threshold is not guessed: it is tested.

> **Ask:** "Create three migration libraries in the four countries since 2015, without the chair: with at least one,
> two and three mentions of *migrante*, *migración*, *migratorio*, *inmigrante* or *refugiado*."
>
> *The agent uses* `library_create` three times (`terms="migrante*, migraci*, migratori*, inmigra*, refugiad*"`,
> `min_occurrences` 1, 2 and 3, `date_from="2015-01-01"`, `exclude_chair=true`, `label="migración"`).

<!-- table:bib_umbral -->
| Mentions per intervention | Chile | Colombia | Ecuador | Peru | Total |
|---|---:|---:|---:|---:|---:|
| 1 or more | 1,841 | 595 | 1,918 | 895 | 5,249 |
| 2 or more | 943 | 224 | 984 | 352 | 2,503 |
| 3 or more | 655 | 117 | 680 | 203 | 1,655 |
<!-- /table -->

Going from one mention to two leaves the library at less than half. To know what is lost, read what lies between the
two thresholds: a library made from the difference of the other two.

> **Ask:** "Make a library with the interventions that name migration only once (those in the first that are not in
> the second) and show me twenty at random."
>
> *The agent uses* `library_combine` (`name="una_mencion"`, `a="migracion_1"`, `b="migracion"`, `op="difference"`) and
> then `kwic` with `library="una_mencion"`.

There are 2,746 interventions. Of the twenty read, about four deal with migration; the rest name it in passing: a
non-discrimination clause that lists "migratory status", a treaty, an organisation in a list, the title of a law read
out on the floor, the name of an institution, migration from the countryside to the city, displaced people called
refugees, the speaker's own biography. The two-mention threshold stays: the library *migracion*.

Venezuela is missing. An intervention enters the library if it uses any of the terms (it is an "or"), and
`min_occurrences` counts the occurrences of all of them together. That is why "migration and Venezuela" is not asked
for in a single library: you make two and cross them.

> **Ask:** "Make another library, *venezuela*, with the interventions that name *venezolano* or *Venezuela* in the
> same countries and years, and cross it with the migration one."
>
> *The agent uses* `library_create` (`terms="venezolan*+venezuela"`, `exclude_chair=true`) and `library_combine`
> (`a="migracion"`, `b="venezuela"`, `op="intersection"`).

The *venezuela* library has 3,289 interventions; the cross, *migracion_y_venezuela*, 468: 165 from Chile, 86 from
Colombia, 145 from Ecuador and 72 from Peru. This is the first definition: two or more mentions of migration, and
Venezuela, in the same intervention.

> [!NOTE]
> Working libraries cost nothing: they are made to test, compared and deleted (§ 10). Give them names that say what they
> are (*migracion_1*, *una_mencion*) and a description; `library_describe` without a name lists them all.

## 5. Describe, and read a sample in each chamber

> **Ask:** "Describe *migracion_y_venezuela* before using it."
>
> *The agent uses* `library_describe` (`name="migracion_y_venezuela"`).

The description warns of two things. In Ecuador, 84.4% of the library's words are in turns of more than 10,000 words,
and in Peru 30.9%: documents read into the record, which § 7 looks at. And there are years with fewer than five
interventions (2015 to 2018 in Chile, four years in Colombia and five in Peru) that cannot be read as a trend. What the description does
not say is whether the interventions are about what you are looking for. Only reading tells.

> **Ask:** "Show me twenty random interventions from the library in each country, with the sentence where Venezuela
> is named, and count how many talk about Venezuelan migrants."
>
> *The agent uses* `kwic` (`pattern="\b(venezolan|venezuela)"`, `regex=true`, `library="migracion_y_venezuela"`,
> `n=20`), one country at a time. The sample is random with a fixed seed: the same request, on the same data, gives
> the same twenty.

In Chile, 16 of the 20 talk about Venezuelan migrants; in Colombia, 17; in Peru, 18. In Ecuador, 6. Ecuador's other
fourteen talk about Ecuadorians living in Venezuela, about Ecuadorian emigrants with Venezuela named somewhere else in
the intervention, about lists of countries and treaties, about Venezuelan politics, about a diplomatic asylum (another
sense of *refugiado*) or about security. The definition works in three chambers and fails in the fourth, for the
reason § 3 hinted at: in Ecuador the migration debate is about Ecuadorians, and in a long intervention Venezuela comes
up for other reasons.

> [!IMPORTANT]
> Read each chamber's sample on its own and write the count down: "16 of 20" is a methods figure, and it goes in the
> paper. A sample of the four countries together would have hidden Ecuador's failure among the other three's hits.

## 6. Second definition: in the same sentence

Ecuador's failure has a shape: the migration word and Venezuela are in the same intervention, but not in the same
sentence. The second definition asks for that with a regular expression.

> **Ask:** "Create *migracion_venezolana* with the interventions where a migration word and *venezolano* appear in the
> same sentence, in the four countries since 2015 and without the chair."
>
> *The agent uses* `library_create` (`regex=true`, `date_from="2015-01-01"`, `exclude_chair=true`,
> `label="migración venezolana"`), with this expression as its term:

```text
(?i)\b(migrante|migraci|migratori|inmigra|refugiad)[^.;:?!]{0,200}\bvenezolan|\bvenezolan[^.;:?!]{0,200}\b(migrante|migraci|migratori|inmigra|refugiad)
```

It reads like this. `(?i)` makes it ignore case: a regular expression is applied to the text as it is, with its
capitals and its accents, which is why the prefixes are cut before the accent (*migraci* finds *migración* and
*migraciones*). `\b` marks the start of a word. `[^.;:?!]{0,200}` allows up to 200 characters with no full stop, colon,
semicolon, or closing question or exclamation mark: roughly, the same sentence. The bar `|` repeats the search in the
other order. The definition changes two things at once: it asks for the same sentence, and only for the demonym,
*venezolano*, not for the country's name, which is the one that turns up in lists and in foreign policy.

The test is the same: twenty random interventions in each chamber, with `kwic` and the same expression.

<!-- table:bib_definiciones -->
| Country | First: interventions | First: of 20 read, about Venezuelan migrants | Second: interventions | Second: of 20 read, about Venezuelan migrants |
|---|---:|---:|---:|---:|
| Chile | 165 | 16 / 20 | 49 | 20 / 20 |
| Colombia | 86 | 17 / 20 | 106 | 20 / 20 |
| Ecuador | 145 | 6 / 20 | 53 | 19 / 20 |
| Peru | 72 | 18 / 20 | 59 | 20 / 20 |
| **Total** | 468 |  | 267 |  |
<!-- /table -->

The second definition is precise in the four chambers, but it is not better at everything. In Ecuador it goes from 145
to 53 interventions and takes almost all the noise with it. In Chile it goes from 165 to 49, and what it loses was
mostly on topic: if the sample holds for the rest, the first gathers more than a hundred interventions about Venezuelan
migrants in Chile, and the second keeps less than half of them (§ 9 measures it), because there migrants and Venezuela
are named in different sentences. In Colombia it grows from 86 to 106, because the second accepts a single mention of
migration if it sits next to *venezolano*.

Neither is the right one. The first covers more where it works; the second can be read without noise in the four
chambers. The guide goes on with the second and looks at both together in § 8: what both say can be stated; what
depends on the definition cannot.

> [!TIP]
> What you learn from reading a sample is the next definition. Write down each version, its sample and its count: the
> sequence of definitions is the justification of the method.

## 7. Correct by hand and annotate

> **Ask:** "Describe *migracion_venezolana*. If there are turns of more than 10,000 words, tell me who says them, when,
> and how many words they have."
>
> *The agent uses* `library_describe` and then `query_sql`:

```sql
SELECT i.country, i.date, i.n_words, i.speaker_raw
FROM lib.library_items li
JOIN lib.libraries l ON l.id = li.library_id
JOIN interventions i ON i.country = li.country AND i.id_int = li.id_int
WHERE l.name = 'migracion_venezolana' AND i.n_words > 10000
ORDER BY 1, 2
```

In Ecuador, 87.6% of the new library's words are in long turns, and in Peru 39.4%. They are ten interventions.
Ecuador's eight are reports read out by the secretariat or the deputy secretariat, of between 17,895 and 224,643
words: documents, not debate. Peru's two are speeches of the executive, the President of the Council of Ministers'
presentation to the floor in May 2020 (13,133 words) and the presidential message of July 2023 (10,090): they are
speech, and they stay.

> **Ask:** "Remove from the library the secretariat's readings of more than 10,000 words, with a query I can repeat,
> and annotate the Colombian motion that creates the ad hoc committee to follow the migration crisis."
>
> *The agent uses* `library_edit` (`action="remove"`, `sql=…`) with this query, and `library_edit` again
> (`action="note"`, `id_ints=[…]`, `note=…`, `tags=["hito", "comisión accidental"]`) for the note:

```sql
SELECT id_int FROM interventions
WHERE country IN ('CO', 'PE', 'EC', 'CL') AND n_words > 10000 AND regexp_matches(speaker_raw, '(?i)secretari')
```

The query searches the whole corpus; `library_edit` removes only those in the library, eight, and leaves 259. The
exclusion is saved: if the library is rebuilt (§ 10), those eight do not come back. The identifier of the intervention
you annotate (`id_int`) comes from any reading with `kwic`, and the note and the tags travel with it to the libraries
it is combined into, to the export and to the table of interventions.

<!-- table:bib_describe -->
| Country | Interventions | Sittings | Dates | Speakers | Words | Linked (%) | Women (% of those with sex) | Words in long turns (%) |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| Chile | 49 | 29 | 2018-05-03 – 2025-11-26 | 38 | 30,949 | 85.7 | 16.7 | 0.0 |
| Colombia | 106 | 63 | 2015-09-16 – 2024-07-31 | 63 | 103,602 | 69.8 | 24.3 | 0.0 |
| Ecuador | 45 | 30 | 2015-09-10 – 2025-12-17 | 33 | 69,963 | 68.9 | 32.3 | 0.0 |
| Peru | 59 | 33 | 2016-06-16 – 2025-09-11 | 45 | 58,941 | 83.1 | 28.6 | 39.4 |
<!-- /table -->

After the cleaning, long turns weigh 0% in Ecuador and stay at 39.4% in Peru, because they were kept on purpose: in
word comparisons they are left out with `max_turn_words=10000`, which does not delete them from the library. The parts
are small: 49 interventions by 38 speakers in Chile will not bear a cut by party or by sex.

> [!WARNING]
> Remove by query, not by eye: a query can be reread, repeated on another edition of the data and cited in the methods
> appendix. And do not remove what gets in the way of the hypothesis, but what is not the unit of the study: here,
> documents read out that are not debate.

## 8. Use the library

**Year by year.** The study's first question is when the topic was debated in each chamber.

> **Ask:** "Year by year, how many interventions of each library are there per thousand interventions of the floor, in
> each country? Show both definitions."
>
> *The agent uses* `query_sql`, which joins the libraries with the interventions and divides by the floor's total for
> each year:

```sql
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
ORDER BY 1, 2, 3
```

Per thousand, and not in raw numbers, because the chambers change size: Colombia's floor had 16,198 interventions in
2017 and 58,757 in 2020; Peru's, 19,962 in 2019 and 87,932 in 2020. In raw numbers, the year with most interventions on
the topic in Colombia is 2020 (24); per thousand, 2018 (1.01).

<!-- viz:bib_anual -->
<!-- table:bib_anual -->
| Country (definition) | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Chile (second) | 0.00 | 0.00 | 0.00 | 0.45 | 0.07 | 0.21 | 0.58 | 0.36 | 0.56 | 0.29 | 0.20 |
| Chile (first) | 0.06 | 0.06 | 0.19 | 0.27 | 0.61 | 0.37 | 1.42 | 1.02 | 2.49 | 1.21 | 0.86 |
| Colombia (second) | 0.15 | 0.00 | 0.86 | 1.01 | 0.72 | 0.41 | 0.47 | 0.00 | 0.09 | 0.08 | 0.00 |
| Colombia (first) | 0.51 | 0.13 | 0.49 | 0.63 | 0.45 | 0.29 | 0.47 | 0.00 | 0.14 | 0.08 | 0.03 |
| Ecuador (second) | 0.17 | 0.00 | 0.00 | 0.23 | 1.40 | 1.06 | 0.33 | 0.18 | 0.12 | 0.20 | 0.72 |
| Ecuador (first) | 1.92 | 1.09 | 1.07 | 0.91 | 1.67 | 2.11 | 0.98 | 1.40 | 0.59 | 0.47 | 3.30 |
| Peru (second) | 0.00 | 0.06 | 0.14 | 0.27 | 0.15 | 0.11 | 0.06 | 0.16 | 0.57 | 0.05 | 0.14 |
| Peru (first) | 0.00 | 0.00 | 0.19 | 0.18 | 0.05 | 0.14 | 0.04 | 0.22 | 0.85 | 0.08 | 0.21 |
<!-- /table -->

The two definitions agree on what can be stated. Colombia rises before anyone else, in 2017 and 2018, and almost
disappears from 2022. Peru has a single peak, in 2023. Ecuador rises in 2019 and 2020, and again in 2025. They differ on
what cannot be stated as it stands: the first gives Ecuador a high line every year (between 0.47 and 3.30 per
thousand), much of which is Ecuadorian emigration; and in Chile both rise in 2021 and in 2023, but in 2023 the first
reaches 2.49 per thousand and the second 0.56. How much more Chile debates the topic depends on the definition.

**The sittings behind each peak.** A year with twenty interventions can be a single debate.

> **Ask:** "Which sittings hold the most interventions of *migracion_venezolana* in each country?"
>
> *The agent uses* `query_sql` (the three sittings with the most interventions of the library in each country).

Ten of Peru's 22 interventions in 2023 come from the sitting of 3 May, on the migrants gathering in Tacna, at the
border with Chile. Six of Ecuador's seven in 2025 come from 27 August, when the Assembly debates the denunciation of the
migration statute with Venezuela. Seven of Colombia's 21 in 2019 come from 20 August, with the bill that grants
nationality to the children of Venezuelans born in Colombia. Seven of Chile's nine in 2021, from an October sitting on
clandestine entries through the north. Before reading a peak as a trend, read the sitting.

**What disappears.** Colombia's part almost empties from 2022.

> **Ask:** "Since the Colombian Congress was installed in July 2022, what is being talked about when *venezolano* is
> said?"
>
> *The agent uses* `kwic` (`pattern="venezolan*"`, `countries=["CO"]`, `date_from="2022-07-20"`, `n=15`).

There are 111 interventions. Most of those read talk about Venezuela as foreign policy: the 2024 elections, the
restoration of relations, gas, trade. The migrants are still there (one intervention recalls that at least two million
Venezuelans live in Colombia), but the floor no longer debates their arrival.

**What each chamber talks about.** The library also serves to compare vocabularies, each chamber with itself.

> **Ask:** "In each country, which words set the interventions of *migracion_venezolana* apart from the rest of the
> floor in the same years? Leave out turns of more than 10,000 words."
>
> *The agent uses* `distinctive_words` (`field="library"`, `a="migracion_venezolana"`, `countries=[…]`,
> `date_from="2015-01-01"`, `exclude_chair=true`, `max_turn_words=10000`), one country at a time.

With `field="library"` and a single country, the comparison is the library against the rest of its own chamber: it
does not compare the languages or the styles of four parliaments, but what each one talks about when it talks about the
topic.

<!-- table:bib_palabras -->
| Country | Words that set the debate apart from the rest of its chamber, most first |
|---|---|
| Chile | norte, cúcuta, visa, irregular, colchane, bolivia, embajador, expulsiones, país, fronteras, extranjeros, caracas, haitianos, países, visas |
| Colombia | bogotá, emergencia, gc898, cancillería, frontera, corrigió, discrimine, millones, salud, cuba, relaciones, exterior, humanitaria, diplomacia, upc |
| Ecuador | estatuto, movilidad, denuncia, excanciller, bolivariana, humana, frontera, exterior, internacional, carácter, relaciones, ginebra, internacionales, homicidios, exteriores |
| Peru | extranjeros, cancillería, frontera, fronteras, acnur, chile, relaciones, exteriores, irregular, países, cooperación, vigilancia, humanitario, tacna, consulares |
<!-- /table -->

Each chamber debates a different problem. Chile, entry through the north: *Colchane*, *Bolivia*, *visa*, *irregular*,
*expulsiones* (expulsions). Colombia, the emergency and diplomacy: *emergencia*, *salud* (health), *humanitaria*,
*cancillería* (foreign ministry), *relaciones*, *exterior*. Ecuador, the legal framework (*estatuto*, *denuncia*,
*movilidad humana*, the name of its migration law) and security (*homicidios*). Peru, foreigners and the control of its
southern border: *extranjeros*, *frontera*, *vigilancia*, *Tacna*, *Chile*, *ACNUR* (UNHCR).

> [!WARNING]
> A library's list of distinctive words starts with the ones that define it: here *venezolanos*, *Venezuela*,
> *migrantes*, *migratoria*… They say nothing new, and the table removes them, together with *Migraciones*, the name
> of a Peruvian institution, and personal names. Look at the odd ones too: *gc898* and *corrigió*, in Colombia, are
> transcription correction stamps in a single 2019 intervention, which `kwic` finds (`pattern="gc898"`). One long
> intervention is enough to push a word up the list.

## 9. Beyond the keywords

A library made of words gathers the interventions that say them. A debate on a topic also has the ones that do not:
the question that follows, the ministry's answer, whoever talks about "the migrants" without saying where they come
from, whoever calls the topic by another name. The readings of §§ 5 and 6 measure precision: of what goes in, how much
answers the question. Coverage is still missing: of what answers the question, how much goes in. Precision is read
inside the library; coverage, outside it.

The MCP does not search by meaning: libraries are defined with words, regular expressions and filters. What a
definition leaves out is looked for where it should be, and read. This section looks in three places: other words of
the debate, the rest of each debate, and what one definition loses against another. Each reading counts three classes:
the interventions that talk about Venezuelan migrants and name them somewhere; those that talk about migration without
saying where from; and the rest (another topic, Venezuela's politics or procedure).

**Expand the vocabulary.** The table in § 8 gives words of each debate that the definition does not search for:
*Colchane* in Chile, *movilidad humana* (human mobility) in Ecuador, *extranjeros* (foreigners) in Peru. Are they other
ways of saying the topic?

> **Ask:** "For each of those three words, make a library in its country since 2015, without the chair; remove what is
> already in *migracion_venezolana* and show me twenty random interventions of what is left."
>
> *The agent uses* `library_create` (`terms="colchane"`, `countries=["CL"]`, `date_from="2015-01-01"`,
> `exclude_chair=true`), `library_combine` (`a="colchane"`, `b="migracion_venezolana"`, `op="difference"`) and `kwic`
> with `library="colchane_fuera"`; and the same with `movilidad humana` in Ecuador and `extranjero*` in Peru.

*Colchane*, the border crossing with Bolivia, appears in 125 interventions, and 117 are outside. The lines read talk
about the northern border (the migration coming in through it, the military, visits by members of parliament), and
none says where the migrants come from: the word names a route, not a nationality. *Movilidad humana* appears in 1,113, and 1,097 are outside: almost all name the Ministry of Foreign
Affairs and Human Mobility, the Assembly's committee or the law that protects Ecuadorians abroad. *Extranjero* appears
in 1,507, and 1,489 are outside: mostly *en el extranjero*, abroad (Peruvians living elsewhere, elections outside the
country, the President of the Republic's trips), and foreign capital, companies or troops. A word that sets a debate
apart does not define it: it sets the debate apart because the debate uses it more than the rest of the chamber, and
the rest uses it for other things.

But a `kwic` line shows some 240 characters, and an intervention can name the Venezuelans somewhere else. Since
talking about Venezuelan migrants takes naming them, there is a ceiling that needs no reading, and a reading that is
needed: the sample's interventions that name Venezuela, whole.

> **Ask:** "How many of those left outside name *venezolano* or *Venezuela*? Of the twenty in each sample, show me
> whole the ones that do."
>
> *The agent uses* `library_combine` (`a="colchane_fuera"`, `b="venezuela"`, `op="intersection"`), with the
> *venezuela* library from § 4, and the same with the other two; then `get_intervention` with the `id_int` of each
> intervention in the sample that names Venezuela.

Venezuela is named in 21 of *Colchane*'s 117, 118 of *movilidad humana*'s 1,097 and 67 of *extranjero*'s 1,489. In the
samples, three of *Colchane*'s do, three of *movilidad humana*'s and none of *extranjero*'s. Read whole, *Colchane*'s
three talk about Venezuelan migrants: they put the crisis or the regime in Venezuela as the cause of what happens at
the border, far from the line read. The three for *movilidad humana* talk about Ecuadorians living in Venezuela, its
politics or organised crime. Of *Colchane*'s twenty, then, three belong to the first class, twelve to the second and
five to other things at the border.

When the class depends on something said elsewhere, the line is not enough: read the whole intervention. *Colchane*
brings mostly the second class, and adding it to the definition means deciding that the question includes the
migration coming in through the north, whether or not it says where from. *Movilidad humana* and *extranjero* would
bring in hundreds of interventions on another topic for a few dozen, at most, of the first class.

**The context of the debate.** A debate is a sequence: who asks, who answers, who replies. The library gathers the
interventions that say the words, and the rest of the same debate stays outside. To see it, look for the sittings where
the library has three interventions or more and, in each one, those between the library's first and last that are not
in it.

> **Ask:** "In the sittings where *migracion_venezolana* has three interventions or more, how many interventions are
> there between the library's first and last that are not in it, without the chair? Then show me twenty random ones in
> each country."
>
> *The agent uses* `query_sql`:

```sql
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
SELECT o.country, count(DISTINCT o.id_session) AS sessions,
       (SELECT count(*) FROM items i JOIN debates d ON i.country = d.country AND i.id_session = d.id_session
        WHERE i.country = o.country) AS in_library,
       count(*) AS outside, count(*) FILTER (WHERE o.n_words >= 50) AS outside_50_words_or_more,
       count(*) FILTER (WHERE regexp_matches(o.text, '(?i)venezolan|venezuela')) AS outside_naming_venezuela
FROM outside o GROUP BY 1 ORDER BY 1
```

For the sample, the same query ends in `SELECT country, date, id_int, n_words, text FROM outside`, with twenty rows per
country chosen at random and always the same ones (`QUALIFY row_number() OVER (PARTITION BY country ORDER BY
md5(id_int)) <= 20`). The chair filter is a simple version of the one the tools use: it also removes, for instance,
whoever presides over Peru's Council of Ministers, who stayed in § 7. The identifier `id_int` starts with the country
code, so it is enough to know whether an intervention is in the library. The query cuts each text at 900 characters
(`max_cell_chars`): as with the words, those that name Venezuela are read whole.

<!-- table:bib_contexto -->
| Country | Sittings | In the library | Outside | Outside, 50 words or more |
|---|---:|---:|---:|---:|
| Chile | 4 | 18 | 193 | 170 |
| Colombia | 11 | 46 | 903 | 352 |
| Ecuador | 4 | 15 | 84 | 73 |
| Peru | 4 | 25 | 82 | 68 |
<!-- /table -->

There are many more interventions outside than inside, but they are not more debate on the topic. In Colombia, of the
903 left outside only 352 have 50 words or more: the rest are votes, readings of articles and procedural notices. Of
the twenty read in each chamber, those that talk about Venezuelan migrants and name them are seven in Peru, three in
Colombia, three in Chile and two in Ecuador. Naming Venezuela is not enough: in Chile, four of the seven that name it
come from a 2018 special sitting on its political situation, and in Ecuador two of four talk about the Ecuadorians who
live there.

The second class weighs as much as the first: seven of twenty in Peru, four in Chile, four in Colombia. They are "the migrants", "the
people who come from outside", "the migration crisis", the expulsions, the refugee law. In a debate on Venezuelan
migration, many talk about Venezuelans without naming them, but not all: in Chile, *haitianos* (Haitians) is among the
debate's words (§ 8). Whether they go in is a decision about the question, not about the words: the arrival of
Venezuelan migrants, or the migration that comes through those borders? Decide it before adding anything, write it
down and apply it the same way in the four chambers.

**Measure coverage: read what is left outside.** The third place is what one definition loses against another. § 6
reckoned that in Chile the second definition keeps less than half of what the first gathers. It can be measured.

> **Ask:** "Make a library with what is in *migracion_y_venezuela* and not in *migracion_venezolana*, and show me
> twenty random interventions from Chile, with the sentence where Venezuela is named."
>
> *The agent uses* `library_combine` (`name="perdidas"`, `a="migracion_y_venezuela"`, `b="migracion_venezolana"`,
> `op="difference"`) and `kwic` (`pattern="\b(venezolan|venezuela)"`, `regex=true`, `library="perdidas"`,
> `countries=["CL"]`, `n=20`).

There are 304 interventions: 128 from Chile, 115 from Ecuador, 33 from Peru and 28 from Colombia. Going by § 5 (6 of 20),
Ecuador's should be mostly the noise the first definition had there; they are not read here. Of Chile's twenty, sixteen talk
about Venezuelan migrants. The second definition loses them for three reasons: the migrants and Venezuela are in
different sentences; the sentence says *Venezuela* and not *venezolano*; or the migration word is none of those it
searches for: *migrando* (migrating), *migrar* (to migrate), *llegada* (arrival), *expulsión* (expulsion).

All the readings together:

<!-- table:bib_fuera -->
| Where | Outside | Name Venezuela | Of 20 read: name Venezuela | Venezuelan migrants | migration without saying where from | another topic | Venezuelan migrants outside (95% interval) |
|---|---:|---:|---:|---:|---:|---:|---:|
| What the second definition leaves out of the first, Chile | 128 | 128 | 20 | 16 | 3 | 1 | 75–118 |
| The rest of the debates, Chile | 193 | 41 | 7 | 3 | 4 | 13 | 6–31 |
| The rest of the debates, Colombia | 903 | 36 | 3 | 3 | 4 | 13 | 16–36 |
| The rest of the debates, Ecuador | 84 | 16 | 4 | 2 | 0 | 18 | 2–14 |
| The rest of the debates, Peru | 82 | 29 | 7 | 7 | 7 | 6 | 19–29 |
| *Colchane*, Chile | 117 | 21 | 3 | 3 | 12 | 5 | 9–21 |
| *movilidad humana*, Ecuador | 1,097 | 118 | 3 | 0 | 2 | 18 | 0–66 |
| `extranjero*`, Peru | 1,489 | 67 | 0 | 0 | 4 | 16 | 0–67 |
<!-- /table -->

The last column turns each reading into an interval. Since the first class has to name Venezuela, it is estimated
among those that do: the share of the first class among the sampled ones that name Venezuela, with its 95% interval
(Wilson's), times the number outside that name Venezuela. If the sample has none, the interval runs from zero to the
ceiling. With samples this small, it gives an order of magnitude, not a measurement.

What is most missing, in Chile, is what the second definition loses from the first: between 75 and 118 interventions
on Venezuelan migrants. With the 49 it has, the second covers between 29% and 40% of what the two find together, and
that at most, because some interventions are found by neither. It is precise in the four chambers (§ 6) and covers a
third in one: precision and coverage are measured apart. The rest of the debates adds a few dozen in each chamber, and
*Colchane* between 9 and 21; the three places partly overlap, so they do not add up. *Movilidad humana* and
*extranjero* bring mostly other topics.

There are two ways to add what is missing. One more definition: `library_create` with `extend=true` adds another
definition to the library (here, for Chile, an expression that accepts *llegada*, *expulsión* or the verb *migrar*
next to *venezolano*), and the rebuild replays it. Or what was read: `library_edit` (`action="add"`, `id_ints=[…]`)
adds the interventions that were read and accepted, and the rebuild finds them by their text. Both are tested like the
first definition: a sample inside, a reading outside and the count written down. This guide adds nothing: it shows
where to look and how much is missing. This section's working libraries are deleted like those in § 10.

> [!NOTE]
> The MCP has no semantic search: no embeddings and no search by meaning. There are two ways to go beyond the words,
> and both end in identifiers. One is for the agent to read: with `kwic`, `get_intervention` or `get_session` it decides
> what answers the question, and adds or removes it by its `id_int`. The other is to compute similarity outside the MCP
> with an embedding model, on the interventions that `export_result` writes, and bring the identifiers back with
> `library_edit` and `id_ints`. Either way the result is tested like a definition: read a sample inside and what is
> left outside, and write it down.

## 10. Maintain it

**Rebuild it.** Each country publishes new editions of its data, and intervention identifiers change from one edition
to the next.

> **Ask:** "Rebuild *migracion_venezolana* on the downloaded data."
>
> *The agent uses* `library_rebuild` (`name="migracion_venezolana"`).

The rebuild applies the definitions again, keeps the exclusions and finds by their text the interventions added by
hand and their notes. On the same edition, the report says that the 49, 106, 45 and 59 interventions stay, that none
comes in, none is lost and no note is lost: Ecuador stays at 45, not 53, because the eight readings remain out. With a
new edition, the report says what comes in and what is lost in each country; an intervention whose text was corrected
counts as lost, and its definition may bring it back. The reading of the sample belongs to an edition: with another
one, read again.

A combined library, such as *migracion_y_venezuela*, has no definition of its own. The rebuild finds its interventions
by their text, but it replays no definition, so it does not pick up what a new edition adds. To bring it up to date,
rebuild *migracion* and *venezuela* and cross them again, and whatever was corrected by hand in the combined one is
lost. Corrections by hand belong in libraries with a definition of their own, like the second one.

**Extend it.** `extend=true` adds another country or another period, with its own definition, to a library that
already exists, and `per_country` gives a country its own terms: to add Brazil, the same expression in Portuguese.

**Export it.**

> **Ask:** "Export *migracion_venezolana* for the Diarios Explorer, with a CSV table of its interventions."
>
> *The agent uses* `library_export` (`name="migracion_venezolana"`, `folder=…`, `table_format="csv"`).

It writes one `.2replib` file per country, because the explorer opens one country at a time; an index with which
`library_import` rebuilds the comparative library; and the table, with each intervention, its data, its note and its
tags. Each `.2replib` is imported in the explorer with its own country's CSV loaded: the explorer does not check.

**Delete what is no longer needed.**

> **Ask:** "Delete the working libraries: *migracion_1*, *migracion_3* and *una_mencion*."
>
> *The agent uses* `library_delete`, first without `confirm` and then with `confirm=true`.

Without `confirm`, it says what it would delete (the 5,249 interventions of *migracion_1*) and deletes nothing. With
`confirm=true` it deletes the library, never the data. *migracion* and *venezuela* stay, since they are needed to bring
the cross up to date, and so do the two definitions. For the methods appendix, `query_log` lists every step with its
parameters and the version of the data ([Home, § 5](../TUTORIAL.en.md#5-closing-a-study)).

## 11. Checklist

1. Write the question down: about what, where, when, who and what for.
2. Test the words with `term_counter`, country by country, and read with `kwic` every figure that surprises you.
3. Test the threshold: compare one, two and three mentions, and read what lies between two thresholds.
4. "A and B" is two libraries and a cross (`library_combine`), or a regular expression.
5. Describe the library before comparing it: the size of each part, the long turns, the thin years.
6. Read a random sample in each chamber, count how many answer the question and write it down.
7. If a chamber fails, narrow the definition, read again and write down what you lose in the others.
8. Measure coverage too: read what is left outside (what each definition loses, the rest of the debates, the words of
   the debate), set a ceiling with what names the topic and decide what to do with what treats it without naming it.
9. Remove by query what is not the unit of the study, and annotate the milestones.
10. Rates, not counts, and the sitting behind each peak.
11. Leave out the words that define the library before reading a vocabulary.
12. Keep the definitions, the readings and the data edition; rebuild, export and delete what is no longer of use.

> **Ask for it all at once:** "I want to study how the floors of Colombia, Peru, Ecuador and Chile debated the arrival
> of Venezuelan migrants since 2015. First test the words (*migrante*, *migración*, *migratorio*, *inmigrante*,
> *refugiado*, *venezolano*) and read the figures that are surprising. Make a library without the chair, test its
> threshold by reading what lies between one and two mentions, describe it and read twenty random interventions in each
> country, counting how many talk about Venezuelan migrants. If a chamber fails, narrow the definition to the same
> sentence and read again. Read what is left outside as well (what the second definition loses from the first, the rest
> of the debates and the words that set each debate apart) and tell me how many interventions on Venezuelan migrants
> are missing. Remove by query the documents read out by the secretariat, compare year by year per
> thousand interventions with both definitions, look at which sittings make the peaks and which words set the debate
> apart in each chamber, without the ones that define the library and without turns of more than 10,000 words. Do not
> quote personal names."
