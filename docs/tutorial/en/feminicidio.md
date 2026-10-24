# How a word enters sixteen parliaments

<!-- eyebrow: Study 1 · The diffusion of a concept -->

*[Versión en español](../es/feminicidio.md) · [Tutorial index](../TUTORIAL.en.md)*

'Feminicidio' [femicide] names the killing of a woman because she is a woman. The word reached the Ibero-American
parliaments in this century, almost always carried in by a law. This study follows its entry into the sixteen chambers:
when it appears, which sittings concentrate it, who says it and with what other words. Seven tools, chained as an agent
would chain them, and at each step a check before believing the result.

<!-- side -->

**The chain in this study**

1. `term_counter`: how many times and since when
2. `ngram_viewer`: the curve of each parliament
3. `term_frequency`: the sittings that concentrate the word
4. `get_session`: what was being debated in them
5. `query_sql`: women and men deputies, with the unigram table
6. `ngram_viewer`: the terms of Spain and Portugal
7. `collocations`: what goes with the word

## 1. How many times and since when

The three forms count as a single term: *feminicidio*, *femicidio* (the form used in the debates of Guatemala,
Argentina, Panama or Uruguay) and *feminicídio* in Portuguese. Turns over 10,000 words, nearly always documents read on
the floor, are left out.

> **Ask:** "How many times has *feminicidio*, *femicidio* or *feminicídio* been said in each parliament, and when was it
> first said? Leave out turns over 10,000 words."
>
> *The agent uses* `term_counter` (`terms="feminicidio+feminicídio+femicidio"`, `max_turn_words=10000`).

<!-- viz:fem_primeros -->
<!-- table:fem_primeros -->
| Country | First use | Party | Corpus from | Uses | Peak year (per million) | Session with most uses (uses) |
|---|---|---|---|---:|---|---|
| Costa Rica | 2001-07-24 | FUERZA DEMOCRÁTICA | 1994 | 502 | 2024 (45.5) | 2021-03-08 (32) |
| Dominican Rep. | 2002-11-21 | PLD | 2001 | 240 | 2021 (83.0) | 2013-06-25 (40) |
| Panama | 2002-12-10 | ARN | 1996 | 435 | 2013 (80.9) | 2013-10-17 (71) |
| Mexico | 2003-09-01 | PRD | 1988 | 5,737 | 2020 (196.6) | 2020-02-18 (144) |
| Guatemala | 2004-07-07 | URNG MAIZ | 2000 | 306 | 2008 (87.6) | 2008-04-09 (46) |
| Chile | 2005-01-06 | PPD | 1990 | 1,189 | 2023 (59.2) | 2023-04-18 (129) |
| Spain | 2005-03-17 | PSOE | 1977 | 23 | 2022 (1.4) | 2021-06-15 (4) |
| Peru | 2007-09-06 | AP | 1995 | 1,499 | 2011 (101.0) | 2011-12-01 (218) |
| Uruguay | 2008-03-05 | Partido Nacional | 1985 | 290 | 2017 (61.2) | 2017-09-12 (78) |
| Portugal | 2008-10-01 | BE | 1976 | 24 | 2024 (3.3) | 2024-12-18 (4) |
| Colombia | 2008-11-25 | MIRA | 2000 | 806 | 2023 (148.6) | 2023-12-13 (172) |
| Argentina | 2010-05-04 | (not linked) | 1983 | 262 | 2018 (50.1) | 2012-04-18 (44) |
| Brazil | 2011-04-28 | PPS | 2003 | 4,056 | 2024 (106.5) | 2021-05-18 (160) |
| Ecuador | 2011-11-16 | MPAIS | 1979 | 999 | 2023 (115.2) | 2017-07-11 (94) |
| Paraguay | 2016-05-25 | Avanza País | 1988 | 164 | 2023 (57.6) | 2023-08-30 (34) |
| El Salvador | 2018-06-21 | (not linked) | 2018 | 264 | 2023 (79.8) | 2023-02-21 (130) |
<!-- /table -->

In all, 16,796 uses in 5,182 interventions from 2,260 sittings, spoken by 2,103 speakers. Mexico accounts for 5,737
and Brazil for 4,056: between the two, more than half. The order of arrival begins in Central America and Mexico
(Costa Rica in 2001, the Dominican Republic and Panama in 2002, Mexico in 2003, Guatemala in 2004) and ends with Brazil
and Ecuador (2011) and Paraguay (2016). In Spain and Portugal the word appears early, in 2005 and 2008, but is hardly
used: 23 and 24 times in twenty years.

> [!WARNING]
> `term_counter` gives the first use **in the corpus**, not in the country. El Salvador's corpus begins in May 2018,
> so its "first use" of June 2018 only says that the word was already in circulation. Before reading the order of
> arrival as an order of diffusion, compare each date with the start of the corpus (the "Corpus from" column, which
> comes from `list_countries`). In Argentina and El Salvador the first use comes from a speaker the register does not
> identify: it may be a minister, a guest or a collective voice.

## 2. The curve of each parliament

> **Ask:** "Plot the frequency per million words, year by year from 2000, one panel per country, with a three-year
> moving average and without the long turns."
>
> *The agent uses* `ngram_viewer` (`terms="feminicidio+feminicídio+femicidio"`, `split_by_country=true`,
> `smoothing=1`, `date_from="2000"`, `max_turn_words=10000`). With `chart_path` it also draws the chart as an SVG.

!['femicide' in six parliaments: the SVG that ngram_viewer draws](../img/feminicidio_en.svg)

<!-- viz:fem_paneles -->
<!-- table:fem_paneles -->
| Country | 2005 | 2010 | 2015 | 2020 | 2025 |
|---|---:|---:|---:|---:|---:|
| Costa Rica | 2.2 | 1.7 | 4.2 | 18.0 | 32.8 |
| Dominican Rep. | 1.6 | 7.0 | 18.4 | 35.0 | 26.9 |
| Panama | 0.0 | 1.9 | 13.8 | 10.9 | 25.3 |
| Mexico | 8.8 | 10.2 | 35.1 | 119.7 | 70.8 |
| Guatemala | 4.5 | 8.7 | 8.4 | 6.5 | 5.8 |
| Chile | 0.8 | 8.0 | 2.7 | 27.0 | 11.6 |
| Spain | 0.1 | 0.0 | 0.2 | 0.5 | 0.3 |
| Peru | 0.0 | 36.6 | 21.6 | 35.8 | 5.0 |
| Uruguay | 0.0 | 0.6 | 1.4 | 9.1 | 2.7 |
| Portugal | 0.0 | 0.0 | 0.0 | 0.9 | 2.5 |
| Colombia | 0.0 | 0.3 | 19.6 | 6.3 | 31.4 |
| Argentina | 0.0 | 2.5 | 5.4 | 4.8 | 4.1 |
| Brazil | 0.0 | 0.0 | 21.4 | 53.2 | 84.2 |
| Ecuador | 0.0 | 0.2 | 8.0 | 9.6 | 46.1 |
| Paraguay | — | — | 3.1 | 5.5 | 27.1 |
| El Salvador | — | — | — | 7.1 | 5.0 |
<!-- /table -->

There are two shapes of curve. In Guatemala and Peru the word shoots up with a law and then falls: the debate is
concentrated in a few sittings. In Mexico, Brazil, Colombia and Ecuador it grows steadily and stays: the word stops
being the name of a bill and enters everyday vocabulary, in denunciations, condemnations and commemorations. Mexico
reaches 119.7 uses per million words in 2020; Brazil is still rising in 2025 (84.2).

> [!NOTE]
> The moving average shifts the peaks. In Panama the smoothed curve peaks in 2014, but that year there were two uses:
> the 140 are from 2013, the year of the bill seen in the next step. To date a peak, read each year's count (it is in
> the tooltip of each panel) or ask for `smoothing=0`. Years with a thin base (fewer than 250,000 words or ten sittings)
> come out empty: the server flags them and they should not be read as a trend.

## 3. The sittings that concentrate the word

> **Ask:** "In which sittings is the word concentrated in each country? Give me the top five."
>
> *The agent uses* `term_frequency` (`by="session"`, `max_rows=5`), one country at a time.

> **Ask:** "Open the sittings with the most uses in Guatemala, Peru, Argentina, Panama and Uruguay. Which bill was
> being debated?"
>
> *The agent uses* `get_session` (`id_session=…`), which returns the list of turns with the opening of each one. The
> agent looks for the bill in it and, if needed, reads a full intervention with `get_intervention`.

<!-- table:fem_sesiones -->
| Country | Sitting | What was debated | Uses | Interventions using it | Turns in the sitting |
|---|---|---|---:|---:|---:|
| Guatemala | 2008-04-09 | The Law against Femicide and other Forms of Violence against Women, passed in the sitting | 46 | 22 | 141 |
| Peru | 2011-12-01 | An urgent Executive bill amending article 107 of the Penal Code; members' bills on femicide are merged into it | 218 | 60 | 357 |
| Argentina | 2012-04-18 | A Penal Code reform on femicide, at the end of a sitting with other bills | 44 | 16 | 429 |
| Panama | 2013-10-17 | The 'Femicide Bill', 75 articles long, alongside other items on the agenda | 71 | 25 | 263 |
| Uruguay | 2017-09-12 | A bill that makes femicide a very special aggravating circumstance of homicide | 78 | 20 | 150 |
<!-- /table -->

In all five countries, the sitting with the most uses is the one where the law was debated. This is the proof that the
curve measures something real: the peaks are not transcription errors or documents read out, but the moment the
chamber legislates. In Mexico, by contrast, the sitting with the most uses (144, in February 2020) does not reach 3% of
the total: there the word is spread over hundreds of sittings.

> [!TIP]
> `get_session` without `include_text` returns only the opening of each turn, which is enough to find your way without
> loading a whole sitting. The openings sometimes include the names of the chair or of third parties: if you are going
> to publish, paraphrase, as in the table.

## 4. Who says the word

`term_counter` already splits by sex: over the whole period, women deputies say *feminicidio* 42.52 times per million
words and men deputies 4.41.

<!-- table:fem_sexo_total -->
|  | Uses | Per million words |
|---|---:|---:|
| Women deputies | 11,090 | 42.52 |
| Men deputies | 4,569 | 4.41 |
| Speakers not linked | 1,137 | 7.37 |
<!-- /table -->

Does this happen in every parliament, or do the big ones drive it? The database's unigram table (words by country,
year and sex) answers that in one query.

> **Ask:** "Compare the frequency of the word between women and men deputies since 2012, country by country. Use the
> unigram table."
>
> *The agent uses* `query_sql`:

```sql
SELECT country, sex,
       sum(n) FILTER (WHERE fold IN ('feminicidio', 'femicidio')) AS uses,
       sum(n) AS words,
       round(1e6 * coalesce(sum(n) FILTER (WHERE fold IN ('feminicidio', 'femicidio')), 0) / sum(n), 2) AS per_million
FROM unigrams
WHERE year >= 2012 AND sex IN ('F', 'M')
GROUP BY 1, 2 ORDER BY 1, 2
```

<!-- viz:fem_sexo -->
<!-- table:fem_sexo -->
| Country | Uses (women) | Per million | Uses (men) | Per million | Ratio |
|---|---:|---:|---:|---:|---:|
| Brazil | 1,232 | 83.43 | 710 | 7.73 | 10.8 |
| El Salvador | 110 | 24.01 | 21 | 2.28 | 10.5 |
| Colombia | 204 | 45.92 | 115 | 5.52 | 8.3 |
| Paraguay | 49 | 31.23 | 26 | 4.29 | 7.3 |
| Chile | 555 | 65.53 | 301 | 9.10 | 7.2 |
| Costa Rica | 286 | 21.44 | 106 | 3.57 | 6.0 |
| Peru | 393 | 36.43 | 180 | 6.57 | 5.5 |
| Ecuador | 517 | 62.81 | 161 | 12.08 | 5.2 |
| Mexico | 2,478 | 45.72 | 408 | 9.58 | 4.8 |
| Spain | 9 | 0.59 | 4 | 0.15 | 3.9 |
| Portugal | 9 | 0.77 | 5 | 0.22 | 3.5 |
| Uruguay | 129 | 14.98 | 156 | 4.33 | 3.5 |
| Dominican Rep. | 46 | 37.36 | 65 | 10.95 | 3.4 |
| Guatemala | 40 | 17.72 | 82 | 6.92 | 2.6 |
| Argentina | 148 | 18.79 | 214 | 10.11 | 1.9 |
| Panama | 76 | 19.79 | 192 | 15.19 | 1.3 |
<!-- /table -->

In all sixteen, women use it more. The gap ranges from 1.3 times in Panama to 10.8 in Brazil, where a woman deputy
says the word 83 times per million words and a man deputy fewer than 8. That in Uruguay, the Dominican Republic,
Guatemala, Argentina or Panama men deputies add up to more uses than women deputies contradicts nothing: they speak
many more words.

> [!NOTE]
> The `unigrams` table stores words in lower case and without accents (`fold`), so `feminicidio` includes
> *feminicídio*. It is fast because it is already aggregated, but it cannot filter by turn length: it also counts the
> documents read out. `describe_data` describes all the tables in the database.

## 5. Spain and Portugal: another word for the same thing

A word that does not appear does not mean the issue does not exist. In the two Iberian parliaments the debate on
violence against women was held in other terms.

> **Ask:** "In Spain and Portugal it hardly appears. What terms do they use? Compare *violencia de género* and
> *violencia doméstica*, in both languages, since 1996."
>
> *The agent uses* `ngram_viewer` (`terms="violencia de género+violência de género, violência doméstica+violencia
> doméstica, feminicidio+feminicídio"`, `countries=["ES","PT"]`, `split_by_country=true`). The comma separates terms;
> the `+` sign adds up the variants of a single term.

<!-- viz:fem_iberia -->
<!-- table:fem_iberia -->
| Series | 1998 | 2002 | 2006 | 2010 | 2014 | 2018 | 2022 | 2025 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ES · gender | 2.6 | 44.8 | 175.5 | 138.1 | 204.1 | 261.3 | 140.4 | 118.6 |
| PT · gender | 0.0 | 0.0 | 6.7 | 3.0 | 8.8 | 11.5 | 9.2 | 17.3 |
| ES · domestic | 24.2 | 57.5 | 17.7 | 8.5 | 8.0 | 4.7 | 2.3 | 2.3 |
| PT · domestic | 6.9 | 20.0 | 62.0 | 72.5 | 88.8 | 216.8 | 195.6 | 248.9 |
<!-- /table -->

The two parliaments chose different words. In the Spanish Congress, *violencia de género* [gender violence] goes from
2.6 uses per million in 1998 to 175.5 in 2006 and displaces *violencia doméstica* [domestic violence], which falls from
57.5 to under 3. In the Assembleia da República the term is *violência doméstica*, which reaches 248.9 in 2025, while
*violência de género* never goes above 20. An international comparison with a single term measures each country's
vocabulary, not its attention to the problem.

## 6. What goes with the word

Frequency says how much; collocations say in what sense. The words that appear near *feminicidio* more often than
chance would lead us to expect change over the years.

> **Ask:** "In Mexico, which words does *feminicidio* appear with up to 2011, and which ones from 2016 on?"
>
> *The agent uses* `collocations` twice (`pattern="feminicidio*"`, `countries=["MX"]`, `date_to="2011"` and
> `date_from="2016"`, `max_turn_words=10000`).

<!-- viz:fem_colocaciones -->
<!-- table:fem_colocaciones -->
|  | To 2011 | G² | From 2016 | G² |
|---:|---|---:|---|---:|
| 1 | relacionadas | 596 | delito | 2,190 |
| 2 | mexicana | 501 | tentativa | 839 |
| 3 | investigaciones | 480 | homicidio | 781 |
| 4 | delito | 356 | víctimas | 506 |
| 5 | república | 344 | país | 413 |
| 6 | vinculada | 299 | doloso | 386 |
| 7 | juárez | 278 | casos | 351 |
| 8 | registrados | 252 | aumento | 348 |
| 9 | tipificar | 247 | grado | 321 |
| 10 | ciudad | 232 | homicidios | 289 |
| 11 | país | 222 | enérgicamente | 277 |
| 12 | competentes | 158 | violación | 246 |
| 13 | justicia | 152 | tipificación | 231 |
| 14 | relación | 145 | condena | 222 |
| 15 | ocurridos | 143 | trata | 203 |
<!-- /table -->

Up to 2011, the word's companions are those of an investigation: *investigaciones* [investigations], *relacionadas*
[related], *registrados* [recorded], *ocurridos* [that occurred], *competentes* [competent, as in the competent
authorities], and a place, Ciudad Juárez. From 2016 on they are those of criminal law and condemnation: *delito*
[offence], *tentativa* [attempt], *homicidio*, *doloso* [intentional], *tipificación* [definition as a crime],
*víctimas*, *aumento* [increase], and *condena* [condemnation] next to *enérgicamente* [strongly], the language of the
statements that condemn a crime. This is a hypothesis to check by reading, not a conclusion: the next step is `kwic`
with each collocation, to see the sentences.

## 7. What the study allows us to say

**What the data say.** The word enters all sixteen chambers within two decades; in five of them, the sitting with the
most uses is the debate on its law; in all of them women deputies use it more; in Mexico its vocabulary shifts, from
investigation to crime; and Spain and Portugal deal with the issue in other words.

**What they do not say.** The order of arrival does not prove contagion from one country to another: that would take
the dates of the bills, networks of those who promoted them or explicit citations of other laws, and the first use
depends on when each corpus begins. The ratio between women and men deputies does not say why women speak more about
the issue (committees, agenda, specialisation?); `distinctive_words` with `field="sex"` and `share_of_voice` help to
take it further.

**The checks in this study.** The start of each corpus before reading a first use; the unsmoothed count before dating
a peak; reading the peak sittings before interpreting them; a rate per million words, never a count, to compare groups
that speak different amounts; and each country's terms before comparing countries.

> **Ask for it all at once:** "Study how the word *feminicidio* (with *femicidio* and *feminicídio*) entered the 16
> parliaments: first use and total by country, the yearly curve per million words without turns over 10,000 words,
> the sittings that concentrate it and what was being debated in them, the difference between women and men deputies
> since 2012, which terms Spain and Portugal use instead, and how the words that go with it change in Mexico. Point out
> where the corpus starts late and do not name any victim."
