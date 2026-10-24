# One virus, sixteen floors

<!-- eyebrow: Study 2 · The reaction to an event -->

*[Versión en español](../es/pandemia.md) · [Tutorial index](../TUTORIAL.en.md)*

On 11 March 2020 the World Health Organization declared the COVID-19 pandemic. The sixteen parliaments received the
same news with very different calendars, rules of procedure and sizes. This study asks when each floor named the
disease, how much attention it gave it week by week, which chambers stopped meeting and, with a library built around
the date, what each chamber talked about and who did the talking. It is also a study of false positives: three of the
sixteen 'first uses' are not about the virus.

<!-- side -->

**The chain of this study**

1. `term_counter`: the first use on each floor
2. `kwic`: reading the first uses
3. `query_sql`: when each chamber stopped meeting
4. `query_sql`: attention, week by week
5. `library_create`: a library around 11 March
6. `library_describe`: what is in it before comparing
7. `distinctive_words`: what each chamber talked about
8. `share_of_voice`: who spoke, against a baseline

## 1. The first use on each floor

> **Ask:** "When was *coronavirus* or *covid* said for the first time in each parliament? Search from June 2019."
>
> *The agent uses* `term_counter` (`terms="coronavirus+covid*"`, `date_from="2019-06-01"`). The asterisk accepts
> any ending: *covid*, *covid-19*, *covid19*.

The answer contains three impossible dates. Ecuador says June 2019, six months before the virus was known; El Salvador,
December 2019; Guatemala, 21 January 2020, with the word 'COVID-19', which the WHO did not coin until 11 February.
Before believing them, you have to read them.

> **Ask:** "Show me the first uses in Ecuador, El Salvador and Guatemala, in date order."
>
> *The agent uses* `kwic` (`pattern="\b(covid|coronavirus)"`, `regex=true`, `order="oldest"`, `n=3`), one country at
> a time.

The concordances settle it. In Ecuador, 'Covid' is the beginning of the name of an organisation that appears in lists of
official letters read out on the floor, in June and again in October 2019. In El Salvador it is 'Covidien', a brand of
surgical supplies in a purchase list. In Guatemala the word is the real one, but it is spoken of in the past tense
('en el tiempo del COVID'): the sitting is misdated. All three are corrected by the next reading (`kwic` from another
date), which gives the real first use.

> [!WARNING]
> A prefix such as `covid*` catches any word that begins the same way, and a date in the record can be wrong. When the
> result depends on the first or the last use, read those lines with `kwic` and `order="oldest"` before accepting the
> date. When quoting, paraphrase: the lists read out on the floor contain the names of private individuals.

One more fact is needed to read the calendar: whether the chamber was meeting.

> **Ask:** "What was the last sitting of each parliament before 11 March 2020, what was the first one after, and how
> many sittings did it hold in the following 120 days?"
>
> *The agent uses* `query_sql`:

```sql
SELECT country,
       max(date) FILTER (WHERE date < DATE '2020-03-11') AS last_before,
       min(date) FILTER (WHERE date >= DATE '2020-03-11') AS first_after,
       count(DISTINCT id_session) FILTER (WHERE date BETWEEN DATE '2020-03-11' AND DATE '2020-07-09') AS sessions_120_days
FROM interventions
WHERE date BETWEEN DATE '2019-10-01' AND DATE '2020-12-31'
GROUP BY 1 ORDER BY 1
```

With the three corrections and the sitting dates, the calendar looks like this:

<!-- viz:pan_primeros -->
<!-- table:pan_primeros -->
| Country | First genuine use | Party | Last sitting before 11 Mar | First after | Sittings in 120 days | Uses up to 2025 | What was corrected |
|---|---|---|---|---|---:|---:|---|
| Mexico | 2020-01-28 | MORENA | 2020-03-10 | 2020-03-12 | 4 | 5,414 |  |
| Chile | 2020-01-29 | IND | 2020-03-10 | 2020-03-11 | 40 | 3,660 |  |
| Guatemala | 2020-01-30 | (not linked) | 2020-03-10 | 2020-03-11 | 16 | 2,276 | false positive on 2020-01-21: a sitting dated 21 January 2020 that speaks of 'COVID-19' in the past tense: the date is wrong |
| Panama | 2020-01-30 | CD | 2020-03-04 | 2020-03-11 | 30 | 2,215 |  |
| El Salvador | 2020-01-30 | PDC | 2020-03-05 | 2020-03-12 | 32 | 4,508 | false positive on 2019-12-19: a brand of surgical supplies ('Covidien') in a purchase list |
| Brazil | 2020-02-04 | PSL | 2020-03-10 | 2020-03-11 | 74 | 10,337 |  |
| Spain | 2020-02-04 | UP | 2020-02-27 | 2020-03-18 | 19 | 3,751 |  |
| Peru | 2020-02-05 | FUERZA POPULAR | 2020-03-10 | 2020-03-11 | 16 | 5,056 |  |
| Portugal | 2020-03-04 | PS | 2020-03-06 | 2020-03-11 | 36 | 3,460 |  |
| Costa Rica | 2020-03-05 | UNIDAD SOCIAL CRISTIANA | 2020-03-10 | 2020-03-11 | 50 | 1,435 |  |
| Uruguay | 2020-03-17 | Partido Nacional | 2020-03-10 | 2020-03-11 | 25 | 3,948 |  |
| Dominican Rep. | 2020-03-19 | (not linked) | 2020-03-04 | 2020-03-18 | 11 | 506 |  |
| Ecuador | 2020-03-24 | (not linked) | 2020-02-18 | 2020-03-24 | 39 | 2,453 | false positive on 2019-06-20: the name of an organisation that begins with 'Covid', in lists of letters read into the record (again on 2019-10-24) |
| Colombia | 2020-04-21 | Cambio Radical | 2019-12-20 | 2020-04-21 | 23 | 2,289 |  |
| Argentina | 2020-05-13 | FRENTE RENOVADOR, FEDERAL UNIDOS POR UNA NUEVA ARGENTINA, FRENTE DE TODOS | 2020-03-01 | 2020-05-13 | 4 | 964 |  |
| Paraguay | 2020-09-02 | Partido Liberal Radical Auténtico | (corpus empty) | 2020-09-02 | 0 | 1,070 |  |
<!-- /table -->

The real first uses fall into three moments. Mexico, Chile, Guatemala, Panama and El Salvador name the virus between 28
and 30 January 2020 (on the 30th the WHO declared a public health emergency of international concern); Brazil, Spain
and Peru, in early February; Portugal and Costa Rica, in early March. The last to do so are not the slowest, but the
ones that were not meeting: Argentina had no sittings between 1 March and 13 May, Colombia between 20 December and
21 April, Ecuador between 18 February and 24 March, and Paraguay's corpus has no sittings from April 2019 to September
2020. In these four cases the first use coincides with the first sitting: it measures the calendar, not the reaction.

## 2. Attention, week by week

A total count favours the chambers that talk the most. To compare attention, the share of each week's interventions
that name the disease is better.

> **Ask:** "Week by week, from January to September 2020, what share of the interventions on each floor names
> *covid* or *coronavirus*? Count the weeks from the WHO declaration."
>
> *The agent uses* `query_sql`:

```sql
WITH w AS (
  SELECT country, CAST(floor(date_diff('day', DATE '2020-03-11', date) / 7) AS INT) AS week,
         count(*) AS interventions,
         count(*) FILTER (WHERE regexp_matches(lower(text), '\b(covid|coronavirus)')) AS covid
  FROM interventions
  WHERE dm_speech = 1 AND date BETWEEN DATE '2020-01-01' AND DATE '2020-09-30'
  GROUP BY 1, 2)
SELECT country, week, interventions, covid, round(100.0 * covid / interventions, 1) AS pct
FROM w ORDER BY 1, 2
```

<!-- viz:pan_semanas -->
<!-- table:pan_semanas -->
| Country | Weeks with sittings (0–12) | Mean of weeks 0–12 (%) | Highest week (%) |
|---|---:|---:|---:|
| Spain | 11 / 13 | 19.3 | 29.7 (week 4) |
| El Salvador | 13 / 13 | 15.5 | 27.3 (week 15) |
| Argentina | 3 / 13 | 10.5 | 17.7 (week 9) |
| Portugal | 12 / 13 | 10.0 | 15.4 (week 5) |
| Peru | 8 / 13 | 9.4 | 22.7 (week 19) |
| Ecuador | 11 / 13 | 9.3 | 17.3 (week 1) |
| Chile | 13 / 13 | 8.9 | 13.5 (week 13) |
| Costa Rica | 13 / 13 | 8.5 | 21.1 (week 8) |
| Panama | 8 / 13 | 8.2 | 17.6 (week 14) |
| Uruguay | 12 / 13 | 6.6 | 19.1 (week 8) |
| Guatemala | 7 / 13 | 6.5 | 23.8 (week 18) |
| Dominican Rep. | 5 / 13 | 4.8 | 12.5 (week 18) |
| Colombia | 8 / 13 | 3.7 | 10.5 (week 5) |
| Mexico | 2 / 13 | 3.0 | 12.6 (week 29) |
| Brazil | 13 / 13 | 2.8 | 4.6 (week 16) |
| Paraguay | 0 / 13 | — | 4.7 (week 25) |
<!-- /table -->

Spain devotes 19.3% of its interventions to the disease in the thirteen weeks that follow the declaration, with a peak
of 29.7% in week 4 (8 to 14 April). El Salvador follows with 15.5%. Brazil, the chamber that says the word most often
over the whole period (10,337), comes almost last with 2.8%: its sittings are made up of a great many brief
interventions (the median for its deputies since 2021 is 25 words, as [study 3](voz.md) shows), and most of them are
not about the matter. Mexico and Argentina have only two and three weeks with sittings in those three months, and
Paraguay none.

> [!NOTE]
> A share of interventions depends on how each chamber cuts up its debate. For comparing countries it is better than a
> count, but it is not neutral: two chambers with the same attention can give different figures if one interrupts more
> than the other. The word table (`unigrams`) or `ngram_viewer` with `measure="per_million"` gives the other measure,
> by words.

## 3. A library around 11 March

To move from counting to comparing content, it helps to isolate the debates on the subject. A library stores, country by
country, the interventions that meet a definition; every analysis tool then accepts `library=`.

> **Ask:** "Create a library, *pandemia*, with the interventions that name *coronavirus*, *covid* or *pandemia* at
> least twice, from 30 days before to 120 days after 11 March 2020, in the sixteen countries and without the chair of
> the sitting."
>
> *The agent uses* `library_create` (`terms="coronavirus+covid+pandemia"`, `min_occurrences=2`,
> `event_dates={…: "2020-03-11"}`, `days_before=30`, `days_after=120`, `exclude_chair=true`).

Here *covid* has no asterisk: the whole-word search finds *covid-19* (the hyphen separates words), but not *Covidien*.
The library stores each country's definition and the version of the data it was created with.

> **Ask:** "Before comparing, tell me what is in the library."
>
> *The agent uses* `library_describe` (`name="pandemia"`).

<!-- table:pan_biblioteca -->
| Country | Interventions | Sittings | Dates | Speakers | Words | Linked (%) | Women (% of those with sex) | Words in long turns (%) |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| Argentina | 117 | 4 | 2020-05-13 – 2020-06-25 | 71 | 82,863 | 94.9 | 45.5 | 0.0 |
| Brazil | 1,481 | 76 | 2020-02-17 – 2020-07-09 | 294 | 798,021 | 97.7 | 25.4 | 0.0 |
| Chile | 488 | 39 | 2020-03-03 – 2020-07-09 | 142 | 337,630 | 91.2 | 24.0 | 0.0 |
| Colombia | 428 | 22 | 2020-04-21 – 2020-06-20 | 140 | 362,411 | 83.2 | 20.8 | 6.1 |
| Costa Rica | 183 | 39 | 2020-02-17 – 2020-07-02 | 55 | 194,374 | 99.5 | 44.0 | 0.0 |
| Dominican Rep. | 15 | 7 | 2020-03-19 – 2020-06-18 | 9 | 9,266 | 100.0 | 6.7 | 0.0 |
| Ecuador | 324 | 34 | 2020-03-24 – 2020-07-07 | 132 | 591,827 | 82.1 | 32.0 | 25.9 |
| Spain | 374 | 19 | 2020-03-18 – 2020-06-25 | 127 | 545,459 | 94.7 | 39.3 | 3.8 |
| Guatemala | 206 | 17 | 2020-02-11 – 2020-06-27 | 61 | 145,637 | 99.5 | 15.1 | 0.0 |
| Mexico | 48 | 10 | 2020-02-11 – 2020-06-30 | 36 | 163,081 | 100.0 | 72.9 | 58.1 |
| Panama | 273 | 30 | 2020-02-10 – 2020-07-09 | 65 | 195,329 | 79.9 | 30.7 | 0.0 |
| Peru | 323 | 13 | 2020-02-26 – 2020-07-06 | 125 | 194,889 | 93.5 | 28.1 | 6.7 |
| Portugal | 426 | 37 | 2020-03-04 – 2020-07-09 | 147 | 218,700 | 91.3 | 46.3 | 0.0 |
| Paraguay | 0 | — | — | — | — | — | — | — |
| El Salvador | 618 | 32 | 2020-02-15 – 2020-07-09 | 71 | 467,835 | 99.5 | 26.0 | 0.0 |
| Uruguay | 93 | 19 | 2020-03-25 – 2020-07-08 | 57 | 126,195 | 96.8 | 15.6 | 8.1 |
<!-- /table -->

That makes 5,397 interventions from fifteen countries: Paraguay has none, because its corpus has no sittings on those
dates. The tool warns of three things that change the analysis. The parts differ in size by a factor of more than ten
(15 interventions from the Dominican Republic, 1,481 from Brazil), so rates must be compared within each chamber, not
counts pooled together. In Mexico, 58.1% of the words are in turns of more than 10,000 words, nearly always documents
read out on the floor, and in Ecuador 25.9%: comparisons by words must be repeated with `max_turn_words=10000`. And the
Portuguese-speaking and Spanish-speaking chambers need the terms in both languages, and their word lists compare
languages as much as debates.

## 4. What each chamber talked about

> **Ask:** "In the library, which words distinguish the Spanish Congress from the other Spanish-speaking chambers?
> Leave out turns of more than 10,000 words."
>
> *The agent uses* `distinctive_words` (`field="country"`, `a="ES"`, `library="pandemia"`,
> `countries=[the fourteen Spanish-speaking ones]`, `max_turn_words=10000`).

<!-- viz:pan_es -->
<!-- table:pan_es -->
|  | Spain | z | the other 12 Spanish-speaking chambers | z |
|---:|---|---:|---|---:|
| 1 | usted | 46.6 | presidente | 30.6 |
| 2 | españa | 36.2 | salud | 25.2 |
| 3 | ustedes | 35.4 | proyecto | 23.9 |
| 4 | gobierno | 33.3 | ley | 23.8 |
| 5 | señora | 30.7 | nacional | 23.2 |
| 6 | real | 29.2 | artículo | 22.3 |
| 7 | comunidades | 27.1 | mil | 18.2 |
| 8 | aplausos | 26.8 | del | 16.8 |
| 9 | autónomos | 26.0 | diputados | 16.8 |
| 10 | autónomas | 24.5 | emergencia | 15.7 |
| 11 | ha | 23.8 | comisión | 15.7 |
| 12 | medidas | 23.6 | covid | 15.5 |
| 13 | presidenta | 23.5 | tema | 15.4 |
| 14 | sanidad | 23.3 | república | 15.2 |
<!-- /table -->

The list says more about how the debate is held than about what is debated. On the Spanish side are the forms of
address to the Government (*usted*, *ustedes*, *señora*, *gobierno*), the State of the Autonomies (*comunidades*,
*autónomas*), the decree-law by which the emergency was governed (*real*, from *real decreto* [royal decree]) and a
convention of the record, which notes the *aplausos* [applause]. On the other side, the legislative procedure
(*proyecto*, *ley*, *artículo*, *comisión*) and the form of address for the chair (*presidente*). Both debates are about
the pandemic; what separates them is the type of parliament.

> **Ask:** "Do the same for Portugal and Brazil."
>
> *The agent uses* `distinctive_words` (`field="country"`, `a="PT"`, `b="BR"`, `library="pandemia"`,
> `max_turn_words=10000`).

<!-- viz:pan_ptbr -->
<!-- table:pan_ptbr -->
|  | Portugal | z | Brazil | z |
|---:|---|---:|---|---:|
| 1 | as | 26.4 | presidente | 27.0 |
| 2 | srs | 24.7 | nós | 21.8 |
| 3 | resposta | 24.4 | eu | 20.3 |
| 4 | de | 23.1 | ele | 16.7 |
| 5 | medidas | 22.3 | esse | 16.1 |
| 6 | das | 20.2 | essa | 15.9 |
| 7 | psd | 19.4 | projeto | 15.6 |
| 8 | portugal | 18.5 | quero | 15.4 |
| 9 | emergência | 17.4 | coronavírus | 14.1 |
| 10 | baixa | 17.2 | muito | 13.9 |
| 11 | covid | 16.7 | isso | 13.7 |
| 12 | estas | 16.6 | brasil | 13.6 |
| 13 | apoio | 16.3 | momento | 13.4 |
| 14 | serviço | 16.1 | deputado | 13.1 |
| 15 | sr | 15.9 | estados | 12.8 |
<!-- /table -->

Here language weighs even more. Portugal has *as*, *das*, *de*, *srs.* and *sr.*, the forms of European Portuguese and
of the record's style of address; Brazil, *nós*, *eu*, *ele*, *esse*, *essa*, *quero*, the orality of Brazilian
Portuguese. Among them, content shows through: in Portugal, *resposta*, *medidas*, *apoio*, *serviço* and *emergência*
(the state of emergency); in Brazil, *coronavírus*, which in Portugal was *covid*, and *estados*, the federation. And
one word that looks like content and is not: *baixa* almost always comes from the formula with which the Portuguese
record announces that a bill 'baixa à 6.ª Comissão' [is referred to the 6th Committee]. Reading five lines with `kwic`
is enough to find out.

> **Ask:** "And Peru against the other Spanish-speaking chambers?"
>
> *The agent uses* `distinctive_words` (`field="country"`, `a="PE"`, `library="pandemia"`, `max_turn_words=10000`).

<!-- table:pan_pe -->
|  | Peru | z | the others | z |
|---:|---|---:|---|---:|
| 1 | perú | 34.9 | yo | 10.6 |
| 2 | congresistas | 27.5 | lo | 9.9 |
| 3 | salud | 26.7 | aquí | 9.6 |
| 4 | personal | 22.8 | ciento | 9.0 |
| 5 | corrupción | 22.4 | número | 8.5 |
| 6 | congreso | 21.9 | que | 8.1 |
| 7 | ministros | 20.9 | social | 7.9 |
| 8 | presidente | 20.6 | asamblea | 7.8 |
| 9 | oxígeno | 19.8 | le | 7.5 |
| 10 | región | 18.2 | mil | 7.2 |
| 11 | regionales | 17.6 | dólares | 6.9 |
| 12 | ejecutivo | 17.4 | medidas | 6.8 |
| 13 | intermedio | 16.5 | dos | 6.6 |
| 14 | congresista | 15.5 | compañeros | 6.5 |
| 15 | contraloría | 15.5 | españa | 6.4 |
<!-- /table -->

Peru has a debate of its own: *oxígeno* (the deaths from lack of medical oxygen), *corrupción* and *contraloría* [the
comptroller's office], *ministros* and *ejecutivo*, the *regiones*. *Intermedio* is something else: the courtesy with
which congress members address others 'por intermedio' [through] the chair.

> [!TIP]
> To compare content without the form of each chamber weighing in, compare within one chamber: the library against
> the rest of its debates in those months, or one period against another. `distinctive_words` accepts both contrasts:
> `field="period"`, or `field="library"`, which compares the library with the rest of the speech of its own chambers.

## 5. Who spoke about the pandemic

> **Ask:** "In the library, did women deputies speak in proportion to their weight in each chamber? Compare it with
> everything said on the floor in those same months, without the chair."
>
> *The agent uses* `share_of_voice` twice: with `library="pandemia"` and with `date_from="2020-02-10"`,
> `date_to="2020-07-09"`, `exclude_chair=true`; in both, `by="sex"`, `per="all"`, `max_turn_words=10000`.

<!-- viz:pan_voz -->
<!-- table:pan_voz -->
| Country | Interventions | Women who speak | Weight on the register | Voice in the pandemic | Ratio (pandemic) | Ratio (all) |  |
|---|---:|---:|---:|---:|---:|---:|---|
| Brazil | 1,481 | 49 | 11.9% | 23.6% | 1.99 | 1.90 |  |
| Mexico | 48 | 25 | 47.9% | 87.6% | 1.83 | 1.50 | left out of the chart |
| Colombia | 428 | 20 | 16.9% | 21.2% | 1.25 | 0.91 |  |
| Panama | 273 | 16 | 30.9% | 34.7% | 1.12 | 0.99 |  |
| Argentina | 117 | 33 | 39.6% | 42.7% | 1.08 | 1.05 |  |
| Costa Rica | 183 | 24 | 41.4% | 42.2% | 1.02 | 0.79 |  |
| Chile | 488 | 30 | 22.6% | 22.5% | 1.00 | 1.00 |  |
| Portugal | 426 | 55 | 47.5% | 44.7% | 0.94 | 0.87 |  |
| Peru | 323 | 29 | 27.2% | 25.3% | 0.93 | 0.95 |  |
| Spain | 374 | 52 | 43.6% | 34.0% | 0.78 | 0.79 |  |
| Ecuador | 324 | 40 | 42.4% | 32.2% | 0.76 | 0.72 |  |
| El Salvador | 618 | 21 | 40.4% | 26.7% | 0.66 | 0.58 |  |
| Guatemala | 206 | 17 | 19.3% | 10.6% | 0.55 | 0.70 |  |
| Uruguay | 93 | 7 | 34.0% | 14.8% | 0.44 | 0.63 | left out of the chart |
| Dominican Rep. | 15 | 1 | 28.3% | 6.6% | 0.23 | 0.30 | left out of the chart |
<!-- /table -->

The baseline changes the reading. In the pandemic debates, Brazilian women deputies speak 23.6% of the words with a
weight of 11.9% on the register, a ratio of 1.99; but in all speech in those months they were already at 1.90: it is
not an effect of the pandemic. Where it does change is in Colombia (1.25 against 0.91) and Costa Rica (1.02 against
0.79), where women spoke about the virus more than they spoke in general, and in Guatemala, where they did so less
(0.55 against 0.70). In Spain (0.78 and 0.79) and Chile (1.00 and 1.00) there is no difference.

> [!WARNING]
> Three chambers are left out of the chart. In the Dominican Republic a single woman deputy speaks; in Uruguay, seven;
> Mexico has 48 interventions in the library. A ratio computed on so few people changes with one more intervention: it
> is in the table, with its number, and should not be compared with the others.

## 6. What the study allows us to say

**What the data say.** Ten parliaments name the virus before the declaration; those that do so late are those that were
not meeting. Weekly attention ranges from 19.3% of interventions in Spain to 2.8% in Brazil. What separates the debates
of each chamber is above all its way of speaking and its language; its own content appears when the comparison is made
with care, such as oxygen in Peru. Women deputies' voice in the pandemic rises in Colombia and Costa Rica and falls in
Guatemala relative to their own baseline.

**What they do not say.** The first use does not measure anyone's concern: it depends on the calendar of sittings and on
what is transcribed. The library gathers interventions that name the disease at least twice, not all the debates on its
consequences (the economy, education, postponed elections).

**The checks in this study.** Read the first uses before dating them; see whether the chamber was meeting; shares, not
counts, to compare chambers of different sizes; describe the library before comparing it; leave out long turns where
they weigh; and a baseline from the same period before saying that something changed.

> **Ask for it all at once:** "Study how the 16 parliaments reacted to the COVID-19 pandemic: the first use of
> *coronavirus* or *covid* in each one, read to rule out false positives; when each floor stopped meeting; the share of
> interventions that name the disease, week by week, from January to September 2020; a library with the interventions
> that name it at least twice between 30 days before and 120 days after 11 March, described before comparing it; the
> words that distinguish Spain, Peru and Portugal against Brazil; and the voice of women deputies in those debates
> against all speech in the same months. Leave out turns of more than 10,000 words and do not cite anyone by name."
