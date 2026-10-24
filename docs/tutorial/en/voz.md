# Who speaks, and how much they weigh

<!-- eyebrow: Study 3 · Representation -->

*[Versión en español](../es/voz.md) · [Tutorial index](../TUTORIAL.en.md)*

Does each group speak in proportion to its weight in the chamber? `share_of_voice` answers with a ratio: the share of
the words (or of the turns) a group speaks, divided by its share of the register of deputies for the period. A ratio
of 1 means it speaks as much as it weighs; above 1, more. This study computes it for women deputies in the sixteen
parliaments since 2010 and goes through the four traps that can turn it around: a Mesa Directiva (the chamber's
governing board) that speaks from the floor, the unit of measurement, language, and the labels on the register.

<!-- side -->

**The chain of this study**

1. `share_of_voice`: voice and weight, year by year
2. `share_of_voice`: since 2021, in words and in turns
3. `query_sql`: the shape of each chamber's turns
4. `share_of_voice`: Mexico, by legislature
5. `distinctive_words`: what women and men deputies say
6. `query_sql`: Mexico without those who speak like the Mesa
7. `distinctive_words`: Spain and its languages
8. `share_of_voice`: Spain, by party

## 1. Voice and weight, year by year

> **Ask:** "Since 2010, year by year and in each parliament, what share of the words do women deputies speak and what
> share of the register are they? Without the chair of the sitting and without turns over 10,000 words."
>
> *The agent uses* `share_of_voice` (`by="sex"`, `per="year"`, `date_from="2010-01-01"`, `exclude_chair=true`,
> `max_turn_words=10000`).

<!-- viz:voz_anual -->
<!-- table:voz_anual -->
| Country (voice / register, %) | 2010 | 2013 | 2016 | 2019 | 2022 | 2025 |
|---|---:|---:|---:|---:|---:|---:|
| Argentina | 35 / 38 | 32 / 36 | 33 / 37 | 35 / 39 | 41 / 43 | 36 / 44 |
| Brazil | 8 / 8 | 10 / 9 | 12 / 9 | 16 / 11 | 24 / 12 | 20 / 14 |
| Chile | 12 / 14 | 14 / 14 | 17 / 16 | 20 / 23 | 29 / 29 | 31 / 35 |
| Colombia | 10 / 12 | 16 / 14 | 17 / 19 | 13 / 17 | 26 / 23 | 23 / 29 |
| Costa Rica | 23 / 38 | 28 / 37 | 21 / 35 | 36 / 41 | 43 / 45 | 51 / 48 |
| Dominican Rep. | 11 / 21 | 20 / 22 | 20 / 26 | 22 / 28 | 11 / 25 | 19 / 36 |
| Ecuador | 27 / 40 | 30 / 44 | 35 / 46 | 36 / 43 | 44 / 42 | 40 / 43 |
| Spain | 25 / 37 | 31 / 40 | 24 / 40 | 36 / 45 | 39 / 42 | 40 / 44 |
| Guatemala | 11 / 13 | 4 / 14 | 3 / 17 | 6 / 17 | 18 / 19 | 17 / 20 |
| Mexico | 48 / 33 | 41 / 42 | 57 / 43 | 68 / 48 | 63 / 49 | 46 / 49 |
| Panama | 11 / 16 | 9 / 16 | 29 / 15 | 30 / 23 | 25 / 31 | 21 / 34 |
| Peru | 25 / 28 | 23 / 21 | 25 / 25 | 35 / 28 | 38 / 38 | 36 / 39 |
| Portugal | 28 / 33 | 28 / 34 | 35 / 42 | 39 / 46 | 34 / 47 | 36 / 47 |
| Paraguay | 11 / 11 | 18 / 11 | 22 / 13 | 26 / 14 | 29 / 14 | 26 / 8 |
| El Salvador | — | — | — | 22 / 40 | 39 / 40 | 45 / 41 |
| Uruguay | 10 / 19 | 9 / 17 | 18 / 32 | 17 / 30 | 30 / 35 | 24 / 36 |
<!-- /table -->

In most chambers women deputies' voice runs below their weight and comes closer to it over the years: in Spain it
goes from 25% of the words with 37% of the register in 2010 to 40% with 44% in 2025; in Costa Rica, from 23% with 38%
to 51% with 48%. Brazil has been above its weight since 2013 (in 2022, 24% of the words with 12% of the register).
Mexico has been far above it since 2016, and section 3 explains why.

> [!WARNING]
> Two points on the chart come from the register, not from the debate. In Paraguay, the 2025 register gives women
> deputies 8% of the weight (four women deputies) when earlier years gave them between 14% and 19%: voice seems to
> triple weight because that year's register is incomplete. In Guatemala, 2024 gives women deputies 47% of the words
> against 14% and 17% in the neighbouring years, with 49 women deputies on the register instead of 32. Before reading
> a jump, look at `members_on_register` and `speakers` in the result, and read the country's documentation with
> `get_documentation`.

## 2. Since 2021: words and turns

> **Ask:** "Since 2021, all together, compare women deputies' weight with their share of the words and with their
> share of the turns."
>
> *The agent uses* `share_of_voice` twice (`by="sex"`, `per="all"`, `date_from="2021-01-01"`,
> `exclude_chair=true`, `max_turn_words=10000`), the second time with `unit="turns"`.

<!-- viz:voz_reciente -->
<!-- table:voz_reciente -->
| Country | Weight on the register | Share of the words | Ratio | Share of the turns | Women who speak | Linked speech |
|---|---:|---:|---:|---:|---:|---:|
| Paraguay | 15.1% | 27.6% | 1.83 | 25.8% | 27 | 88% |
| Brazil | 14.9% | 21.9% | 1.47 | 23.1% | 153 | 95% |
| Guatemala | 18.6% | 25.0% | 1.35 | 28.9% | 48 | 97% |
| Mexico | 48.1% | 60.0% | 1.25 | 61.4% | 723 | 97% |
| Ecuador | 40.2% | 43.9% | 1.09 | 42.5% | 174 | 60% |
| Peru | 32.6% | 33.9% | 1.04 | 35.2% | 88 | 79% |
| Costa Rica | 44.8% | 45.6% | 1.02 | 44.0% | 52 | 98% |
| Colombia | 23.5% | 23.6% | 1.00 | 20.4% | 77 | 67% |
| Chile | 29.0% | 29.1% | 1.00 | 27.6% | 73 | 88% |
| El Salvador | 41.2% | 38.9% | 0.94 | 22.7% | 82 | 99% |
| Argentina | 41.6% | 37.8% | 0.91 | 38.1% | 198 | 95% |
| Spain | 44.3% | 38.9% | 0.88 | 38.9% | 271 | 96% |
| Portugal | 46.7% | 36.9% | 0.79 | 26.2% | 218 | 88% |
| Uruguay | 36.9% | 27.2% | 0.74 | 25.1% | 161 | 94% |
| Panama | 32.8% | 23.2% | 0.71 | 22.9% | 61 | 60% |
| Dominican Rep. | 32.4% | 12.2% | 0.38 | 11.3% | 94 | 99% |
<!-- /table -->

The ratio ranges from 0.38 in the Dominican Republic, where women deputies are 32.4% of the register and speak 12.2%
of the words, to 1.47 in Brazil (Paraguay, at 1.83, reflects the incomplete 2025 register). Six chambers are close to
1: Ecuador, Peru, Costa Rica, Colombia, Chile and El Salvador.

The unit matters. In El Salvador women deputies speak 38.9% of the words but take only 22.7% of the turns; in
Portugal, 36.9% and 26.2%. They speak less often, and for longer. How much the measure shifts depends on how each
chamber shares out the floor.

> **Ask:** "How many words does a typical intervention by a deputy have in each parliament, since 2021? Give me the
> median and the 90th percentile."
>
> *The agent uses* `query_sql`:

```sql
SELECT country, count(*) AS interventions,
       CAST(median(n_words) AS INT) AS median_words,
       CAST(quantile_cont(n_words, 0.9) AS INT) AS p90_words
FROM interventions
WHERE dm_speech = 1 AND date >= DATE '2021-01-01' AND id_dep IS NOT NULL AND id_dep <> ''
GROUP BY 1 ORDER BY median_words DESC
```

<!-- table:voz_turnos -->
| Country | Deputies' interventions since 2021 | Median words | 90th percentile |
|---|---:|---:|---:|
| El Salvador | 23,494 | 146 | 913 |
| Costa Rica | 47,277 | 84 | 739 |
| Dominican Rep. | 19,059 | 64 | 432 |
| Chile | 92,920 | 41 | 456 |
| Spain | 62,554 | 39 | 922 |
| Brazil | 248,945 | 25 | 366 |
| Mexico | 142,001 | 22 | 454 |
| Guatemala | 31,313 | 21 | 343 |
| Peru | 158,727 | 19 | 257 |
| Paraguay | 36,955 | 19 | 394 |
| Argentina | 36,190 | 18 | 527 |
| Colombia | 99,870 | 18 | 268 |
| Panama | 45,866 | 18 | 309 |
| Portugal | 156,878 | 18 | 222 |
| Uruguay | 40,823 | 18 | 744 |
| Ecuador | 38,626 | 16 | 733 |
<!-- /table -->

The chambers are not much alike. In El Salvador, the median intervention has 146 words; in Costa Rica, 84. In
Portugal, Colombia, Panama, Argentina or Uruguay, 18, and in Ecuador 16: there, short turns abound, such as
questions, replies or requests for the floor. Counting turns measures how many times the floor is taken; counting
words, how much is said. Choose the unit according to the question, and state it when you present the result.

## 3. Mexico: the Mesa speaks from the floor

> **Ask:** "In Mexico, by legislature since 2012, what share of the words do women deputies speak?"
>
> *The agent uses* `share_of_voice` (`countries=["MX"]`, `by="sex"`, `per="legislature"`, `date_from="2012-09-01"`,
> `exclude_chair=true`, `max_turn_words=10000`).

In the LXIV legislature (2018–2021), women deputies speak 66.7% of the words with 45.2% of the register, a ratio of
1.47. What do they say?

> **Ask:** "In that legislature, which words set women deputies apart from men deputies?"
>
> *The agent uses* `distinctive_words` (`field="sex"`, `a="F"`, `b="M"`, `countries=["MX"]`,
> `date_from="2018-09-01"`, `date_to="2021-08-31"`, `exclude_chair=true`, `max_turn_words=10000`).

<!-- viz:voz_mx_palabras -->
<!-- table:voz_mx_palabras -->
|  | Women | z | Men | z |
|---:|---|---:|---|---:|
| 1 | diputada | 77.4 | que | 73.6 |
| 2 | del | 75.6 | no | 72.5 |
| 3 | votación | 66.1 | es | 70.4 |
| 4 | grupo | 62.9 | un | 49.2 |
| 5 | parlamentario | 62.1 | pero | 46.7 |
| 6 | diputado | 60.0 | una | 46.0 |
| 7 | de | 56.2 | porque | 44.1 |
| 8 | partido | 53.9 | esta | 43.7 |
| 9 | diputados | 53.9 | yo | 43.2 |
| 10 | mujeres | 52.1 | más | 41.3 |
| 11 | general | 48.9 | eso | 41.2 |
| 12 | manifestarlo | 44.9 | país | 40.8 |
| 13 | sírvanse | 44.4 | hay | 40.1 |
| 14 | estén | 43.0 | pueblo | 39.6 |
| 15 | cargo | 42.8 | aquí | 37.3 |
<!-- /table -->

The women deputies' list is not a debate: 'votación', 'sírvanse', 'manifestarlo', 'estén', 'diputada', 'diputado',
'grupo parlamentario'. It is the formula 'las diputadas y los diputados que estén por la afirmativa, sírvanse
manifestarlo' [women and men deputies in favour, please signify it], and the announcement of who has the floor. It is
read out by the secretaries of the Mesa Directiva, who are women deputies and speak from their seats. `exclude_chair`
removes the turns of whoever is in the chair, but not those of the Mesa. The men deputies' list, by contrast, is a
debate: 'que', 'no', 'pero', 'porque', 'país', 'pueblo' [that, no, but, because, country, people].

> **Ask:** "Repeat the comparison by legislature without the women and men deputies who speak like the Mesa: those
> with more than a thousand turns in the legislature."
>
> *The agent uses* `query_sql`:

```sql
WITH d AS (
  SELECT legislature, sex, id_dep, count(*) AS turns, sum(n_words) AS words
  FROM interventions
  WHERE country = 'MX' AND legislature IN ('LXII', 'LXIII', 'LXIV', 'LXV', 'LXVI') AND dm_speech = 1
    AND sex IN ('F', 'M') AND n_words <= 10000
  GROUP BY 1, 2, 3)
SELECT legislature, sex, count(*) AS deputies,
       count(*) FILTER (WHERE turns > 1000) AS mesa_like,
       sum(words) AS words,
       sum(words) FILTER (WHERE turns <= 1000) AS words_rest
FROM d GROUP BY 1, 2 ORDER BY 1, 2
```

<!-- table:voz_mx -->
| Legislature | Women's weight | Their words | Ratio | Women / men with over 1,000 turns | Their words without them | Ratio without them |
|---|---:|---:|---:|---|---:|---:|
| LXII | 42.2% | 41.5% | 0.98 | 3 / 10 | 54.5% | 1.29 |
| LXIII | 42.5% | 57.7% | 1.36 | 8 / 4 | 48.2% | 1.14 |
| LXIV | 45.2% | 66.7% | 1.47 | 8 / 3 | 57.6% | 1.27 |
| LXV | 48.2% | 63.9% | 1.33 | 7 / 3 | 62.2% | 1.29 |
| LXVI | 48.6% | 46.7% | 0.96 | 2 / 2 | 50.8% | 1.05 |
<!-- /table -->

Without the eleven speakers with more than a thousand turns (eight women deputies and three men deputies), the women
deputies of the LXIV speak 57.6% of the words: still above their weight (1.27), but far from 66.7%. The correction
does not always go in the same direction: in the LXII the Mesa's speakers were mostly men deputies (ten against
three), and removing them raises the women deputies' share from 41.5% to 54.5%.

> [!IMPORTANT]
> The thousand-turn cut-off is an ad hoc rule to show the effect, not a definition of the Mesa. For published work,
> identify its members by legislature (in the country's documentation or by reading the sittings with `get_session`)
> and remove them by their `id_dep`. And remember that the SQL query does not apply `exclude_chair`: its figures are
> compared with each other, not with those of `share_of_voice`.

## 4. Spain and its languages

> **Ask:** "In the Spanish Congress, since December 2019, which words set women deputies and men deputies apart?"
>
> *The agent uses* `distinctive_words` (`field="sex"`, `a="F"`, `b="M"`, `countries=["ES"]`,
> `date_from="2019-12-03"`, `exclude_chair=true`).

<!-- viz:voz_es_palabras -->
<!-- table:voz_es_palabras -->
|  | Women | z | Men | z |
|---:|---|---:|---|---:|
| 1 | mujeres | 63.1 | españa | 29.4 |
| 2 | violencia | 36.5 | do | 28.2 |
| 3 | las | 35.9 | señor | 28.1 |
| 4 | per | 35.3 | non | 24.7 |
| 5 | els | 34.5 | caso | 24.7 |
| 6 | personas | 32.1 | bng | 24.2 |
| 7 | sexual | 30.4 | del | 22.8 |
| 8 | nosotras | 29.6 | creo | 22.7 |
| 9 | igualdad | 29.2 | muchas | 21.2 |
| 10 | les | 28.4 | as | 21.1 |
| 11 | mujer | 26.1 | unión | 20.9 |
| 12 | perquè | 26.1 | señora | 20.6 |
| 13 | derechos | 25.4 | máis | 20.4 |
| 14 | amb | 25.3 | en | 20.3 |
| 15 | ciudadanía | 24.9 | evidentemente | 20.3 |
<!-- /table -->

On the women deputies' side there is a theme ('mujeres', 'violencia', 'sexual', 'igualdad', 'nosotras', 'derechos'
[women, violence, sexual, equality, we (fem.), rights]) and a language: 'per', 'els', 'les', 'perquè', 'amb' are Catalan.
On the men deputies' side, 'España' and 'señor' [sir], and another language: 'do', 'non', 'as', 'máis' are Galician,
along with 'BNG', the party of a single deputy. Since the reform of the Standing Orders in September 2023, Catalan,
Galician and Basque may be spoken on the floor.

> **Ask:** "How many interventions in the Congress contain 'perquè' (Catalan) or 'máis' (Galician), year by year since
> 2019?"
>
> *The agent uses* `query_sql`:

```sql
SELECT year(date) AS year, count(*) AS interventions
FROM interventions
WHERE country = 'ES' AND dm_speech = 1 AND date >= DATE '2019-01-01'
  AND regexp_matches(lower(text), '\b(perquè|máis)\b')
GROUP BY 1 ORDER BY 1
```

<!-- table:voz_es_lenguas -->
| Year | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Interventions with 'perquè' or 'máis' | 1 | 6 | 8 | 7 | 32 | 140 | 106 |
<!-- /table -->

Up to 2022 there are no more than eight a year; in 2024 there are 140. Here a word list by sex measures, in part, who
speaks in which language.

> [!TIP]
> To separate theme from language, repeat the comparison up to August 2023 (`date_to="2023-08-31"`), or compare
> within each language. The lists from `distinctive_words` compare languages as much as content whenever the two
> groups do not speak the same one.

## 5. Spain, by party: labels and boundaries

> **Ask:** "In the legislature that began in August 2023, how much does each party speak against its weight?"
>
> *The agent uses* `share_of_voice` (`countries=["ES"]`, `by="party"`, `per="all"`, `date_from="2023-08-18"`,
> `exclude_chair=true`).

<!-- table:voz_es_partidos -->
| Label on the register | Deputies who speak | On the register | Weight on the register | Share of the words | Ratio |
|---|---:|---:|---:|---:|---:|
| PSOE | 100 | 108 | 26.8% | 17.0% | 0.63 |
| PP | 139 | 148 | 36.7% | 15.6% | 0.42 |
| SUMAR | 35 | 35 | 8.7% | 14.4% | 1.66 |
| VOX | 33 | 34 | 8.4% | 11.7% | 1.38 |
| ERC | 8 | 8 | 2.0% | 11.6% | 5.82 |
| JxCAT-JUNTS | 8 | 8 | 2.0% | 9.8% | 4.96 |
| EAJ-PNV | 6 | 6 | 1.5% | 5.7% | 3.82 |
| EH Bildu | 7 | 7 | 1.7% | 4.9% | 2.83 |
| BNG | 1 | 1 | 0.2% | 4.3% | 17.32 |
| UPN | 1 | 1 | 0.2% | 1.1% | 4.55 |
| PSC-PSOE | 20 | 23 | 5.7% | 1.1% | 0.19 |
| PSE-EE (PSOE) | 6 | 6 | 1.5% | 1.1% | 0.72 |
| CCa | 1 | 1 | 0.2% | 1.0% | 4.11 |
| PsdeG-PSOE | 10 | 11 | 2.7% | 0.4% | 0.17 |
| PSIB-PSOE | 2 | 3 | 0.7% | 0.2% | 0.29 |
| PSN-PSOE | 3 | 3 | 0.7% | 0.1% | 0.15 |
| **PSOE with its federations** | 141 | 154 | 38.2% | 19.9% | 0.52 |
<!-- /table -->

The register labels by party, not by parliamentary group: the socialist group appears split between the PSOE and five
federations (PSC, PSdeG, PSE-EE, PSIB and PSN). Added together, they are 38.2% of the register and speak 19.9% of the
words, a ratio of 0.52; the PP, 0.42. The small groups speak far more than their weight, because in many debates time
is shared out by group and not by seat: Sumar 1.66, Vox 1.38, ERC 5.82. The ratios of a single deputy (BNG, UPN, CCa)
can go above 4 or 17 and say nothing about a group: they are one person.

> [!WARNING]
> The period starts on 18 August, the day after the constituent sitting. On the 17th the register holds both the 350
> new deputies and 135 from the previous legislature, whose term ends that day; if the period includes that day, the
> re-elected deputies are counted with the label of their old row, and Vox drops from 34 members to 20. When a period
> crosses a change of legislature, start it on the following day or look at `members_on_register` before reading the
> ratio.

## 6. What the study allows us to say

**What the data say.** Since 2021, women deputies speak in proportion to their weight in six parliaments, below it in
the Dominican Republic, Panama, Uruguay and Portugal, and above it in Brazil and, with the caveats about the register,
in Guatemala and Paraguay. The figures for Mexico, Spain and Paraguay change when you look at how they are produced:
a Mesa that reads out votes, two new languages on the floor and an incomplete register.

**What they do not say.** The ratio measures neither influence nor quality: a woman deputy who reads out the result of
a vote adds words. Nor does it explain why a group speaks less (how time is allocated, committees, posts held). And it
weighs the groups with the register, which counts everyone who passes through a seat in the period, substitutes
included.

**The checks in this study.** Without the chair and without long turns; words and turns, separately; read a group's
words before interpreting its voice; look at who concentrates the turns; separate language from theme; merge the
labels that are one and the same group; do not read ratios for one-person groups; and check the register at jumps
and at legislature boundaries.

> **Ask for it all at once:** "Study whether women deputies speak in proportion to their weight in the 16
> parliaments: year by year since 2010 and, since 2021, in words and in turns, without the chair and without turns
> over 10,000 words. Compare the length of the turns in each chamber. In Mexico, by legislature, look at which words
> set women and men deputies apart and repeat the count without those who speak like the Mesa. In Spain, check
> whether language weighs on each sex's words and compute voice by party from 18 August 2023, merging the PSOE's
> federations. Flag the years in which the register looks incomplete."
