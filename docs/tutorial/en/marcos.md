# Fighting privileges: pension reform in Brazil

<!-- eyebrow: Study 4 · Interpretive frames -->

*[Versión en español](../es/marcos.md) · [Tutorial index](../TUTORIAL.en.md)*

Between December 2016 and November 2019, Brazil's Chamber of Deputies debated two pension reforms: PEC 287/2016
[a proposed constitutional amendment], which stalled in February 2018, and PEC 6/2019, which became Constitutional
Amendment 103/2019. The 2019 government defended it as a reform to 'fight privileges'; the opposition called it the
destruction of the Previdência [social security]. This study gathers those debates in a library, finds their themes
with a word network, follows a frame, maps the institutions that are named and asks who names whom. In the last step,
a namesake turns the conclusion around.

<!-- side -->

**The chain in this study**

1. `library_create`: the library of the two reforms
2. `query_sql`: the library, month by month
3. `cooccurrence_network`: the themes
4. `distinctive_words`: two reforms, two parties
5. `collocations` and `term_frequency`: 'privilégios' [privileges]
6. `kwic`: read the frame before counting it
7. `comention_network`: the institutions
8. `mention_network`: who names whom

## 1. The library of the two reforms

> **Ask:** "Create a library, *previdencia*, with the interventions in Brazil's Chamber that name *reforma da
> previdência*, *previdência social* or *aposentadoria* at least twice, from December 2016 to November 2019,
> without the chair."
>
> *The agent uses* `library_create` (`countries=["BR"]`,
> `terms="reforma da previdência+previdência social+aposentadoria*"`, `min_occurrences=2`,
> `date_from="2016-12-01"`, `date_to="2019-11-30"`, `exclude_chair=true`).

The library holds 3,126 interventions from 505 sittings, spoken by 466 speakers: 1.7 million words. Of these, 98.6%
are linked to a deputy; women deputies are 15.2% of the speakers whose sex is in the register, and long turns barely
count (0.7% of the words). A library is also a table, and it can be queried with SQL.

> **Ask:** "How is the library spread month by month?"
>
> *The agent uses* `query_sql`, joining the library with the interventions:

```sql
SELECT strftime(i.date, '%Y-%m') AS month, count(*) AS interventions, count(DISTINCT i.id_session) AS sessions
FROM lib.library_items li
JOIN lib.libraries l ON l.id = li.library_id
JOIN interventions i ON i.country = li.country AND i.id_int = li.id_int
WHERE l.name = 'previdencia'
GROUP BY 1 ORDER BY 1
```

<!-- viz:mar_meses -->
<!-- table:mar_meses -->
| Year | Interventions | Busiest month (interventions) |
|---|---:|---|
| 2016 | 127 | 2016-12 (127) |
| 2017 | 1,283 | 2017-03 (283) |
| 2018 | 243 | 2018-02 (87) |
| 2019 | 1,473 | 2019-07 (382) |
<!-- /table -->

The two reforms are visible. The first fills 2017 (283 interventions in March, 216 in December) and fades out in
February 2018, when the federal intervention in Rio de Janeiro prevented votes on constitutional amendments. The second
takes up 2019 and peaks in July, the month of the first vote on the floor, with 382 interventions.

## 2. The themes: a word network

> **Ask:** "What themes were discussed in the library, and which parties use them most? Leave out personal names."
>
> *The agent uses* `cooccurrence_network` (`library="previdencia"`, `layout="clusters"`, `exclude=[…]`,
> `output_dir=…`). It writes an interactive page, tables and a summary.

<!-- embed:redes/palavras.html 760 -->

<!-- table:mar_temas -->
| Theme | Most characteristic terms | Interventions with the theme (%) | Parties that use it most | Those that use it least |
|---:|---|---:|---|---|
| 1 | prestação continuada, regime próprio, previdenciários, déficit, regime geral, gastos, funrural, fiscal | 75.5 | PTB, PSD, NOVO | PP, PSDB, PMDB |
| 2 | nova previdência, previdência vai, aí, vai, mentira, brasil, dinheiro, agora | 97.5 | PSD, NOVO, PT | PMDB, PRB, PSDB |
| 3 | intermitente, tempo mínimo, tempo de contribuição, anos de contribuição, idade, homens, média, tempo mínimo de contribuição | 82.7 | PDT, PSB, PT | PMDB, NOVO, PSL |
| 4 | sobre a reforma, votar a reforma, contra a reforma, favor da reforma, votar a reforma da previdência, votação da reforma da previdência | 8.4 | DEM, PSD, PSOL | PCDOB, PSDB, PSL |
| 5 | destruição da previdência social, trabalhista, destruir a previdência, vivenciando, golpe, golpista, ilegítimo, governo ilegítimo | 84.4 | PT, PCDOB, PSOL | NOVO, PSDB, MDB |
| 6 | prestação, continuada, bpc, benefício, benefício de prestação continuada, aposentadoria rural, financeiro, idosos | 22.4 | PTB, PRB, PSD | PR, PSL, NOVO |
| 7 | combater privilégios, lucros e dividendos, salários mínimos, antirreforma, viúva, ganha, abono salarial, salário mínimo | 62.8 | PDT, PSOL, PSB | PSDB, PR, PODE |
| 8 | sistema de capitalização, chile, capitalização, regime de capitalização, transição, bancos, desta reforma | 16.0 | PDT, PSB, NOVO | PSL, PMDB, PR |
| 9 | fásica, regime geral da previdência, seguridade, comissão especial da reforma da previdência, previdenciário | 6.8 | DEM, PTB, PCDOB | PSD, PT, PODE |
<!-- /table -->

The network has 245 terms and 1,666 links, grouped into nine themes. Each one is a vocabulary: one for the accounts
(*déficit*, *regime próprio*, *gastos*, theme 1), one for the rules (*tempo de contribuição*, *idade*, theme 3), one
for the poorest (*benefício de prestação continuada*, *aposentadoria rural*, theme 6) and one for the Chilean model
(*capitalização*, *Chile*, theme 8). Two are competing frames. Theme 5, *destruição da previdência* [destruction of the
Previdência], *golpe* [coup], *governo ilegítimo* [illegitimate government], is the opposition's theme of 2016 and
2017: the PT, the PCdoB and the PSOL use it most. Theme 7 brings together *combater privilégios* [fight privileges]
with *lucros e dividendos* [profits and dividends], *abono salarial* [wage bonus] and *salário mínimo* [minimum wage]:
the government's frame and the answer of those who ask who pays.

> [!NOTE]
> Personal names are taken out of the network with `exclude`, after a first reading of the themes: that is how the tool
> is meant to be used, proposing first and refining afterwards. The interventions column does not add up to 100: a
> theme is present in an intervention if one of its terms appears, and the themes overlap.

## 3. Two reforms, two parties

> **Ask:** "Which words set the debates of 2016 and 2017 apart from those of 2019?"
>
> *The agent uses* `distinctive_words` (`field="period"`, `a="2016-2017"`, `b="2019-2019"`,
> `library="previdencia"`, `exclude_chair=true`).

<!-- viz:mar_periodo -->
<!-- table:mar_periodo -->
|  | 2016–2017 | z | 2019 | z |
|---:|---|---:|---|---:|
| 1 | trabalhista | 14.2 | reais | 18.6 |
| 2 | golpe | 13.7 | sra | 17.7 |
| 3 | direitos | 13.3 | pobres | 16.2 |
| 4 | mulheres | 12.1 | aqui | 15.4 |
| 5 | de | 11.5 | eu | 15.3 |
| 6 | em | 11.3 | nós | 13.9 |
| 7 | as | 11.3 | oposição | 13.6 |
| 8 | trabalho | 10.8 | educação | 13.5 |
| 9 | terceirização | 10.6 | deputado | 13.4 |
| 10 | trabalhadores | 9.7 | ganha | 12.4 |
| 11 | empresas | 9.6 | economia | 12.3 |
| 12 | ano | 9.1 | mais | 12.3 |
| 13 | contra | 9.0 | capitalização | 12.2 |
| 14 | art | 8.9 | privilégios | 12.1 |
| 15 | golpista | 8.8 | reforma | 11.7 |
<!-- /table -->

The first reform was debated alongside others: *trabalhista* and *terceirização* are the 2017 labour reform and
outsourcing law, and *golpe* and *golpista* the frame through which the opposition read the change of government of
2016. The 2019 reform talks about money (*reais*, *economia*, *ganha*), about *pobres* [the poor], *capitalização* and
*privilégios*.

> **Ask:** "In 2019, which words set the PT apart from the PSL?"
>
> *The agent uses* `distinctive_words` (`field="party"`, `a="PT"`, `b="PSL"`, `library="previdencia"`,
> `date_from="2019-01-01"`, `exclude_chair=true`).

<!-- viz:mar_pt_psl -->
<!-- table:mar_pt_psl -->
|  | PT | z | PSL | z |
|---:|---|---:|---|---:|
| 1 | trabalhadores | 9.2 | eu | 13.0 |
| 2 | proposta | 8.2 | todos | 10.1 |
| 3 | se | 7.0 | nova | 9.3 |
| 4 | trabalhador | 7.0 | esquerda | 9.1 |
| 5 | salário | 6.8 | muito | 8.8 |
| 6 | dos | 6.5 | tenho | 8.3 |
| 7 | povo | 6.2 | psl | 8.3 |
| 8 | direitos | 6.1 | nosso | 7.8 |
| 9 | mínimo | 6.0 | meu | 7.6 |
| 10 | mulheres | 6.0 | segurança | 7.4 |
| 11 | aposentar | 5.9 | me | 7.2 |
| 12 | direito | 5.8 | bem | 7.2 |
| 13 | pobres | 5.6 | meus | 7.2 |
| 14 | portanto | 5.5 | corrupção | 6.5 |
| 15 | social | 5.2 | sou | 6.4 |
<!-- /table -->

The PT talks about *trabalhadores* [workers], *salário mínimo*, *povo* [people], *direitos* [rights], *mulheres*
[women] and *pobres*. The PSL, the governing party in 2019, speaks in the first person (*eu*, *meu*, *tenho*, *sou*),
names its opponent (*esquerda* [the left]) and uses the official label, *nova* previdência [new Previdência], along
with *segurança* [security] and *corrupção*.

## 4. 'Privilégios': one frame, two uses

> **Ask:** "Which words go with *privilégio* in the speeches of the PT, the PSOL, the PSL and Novo?"
>
> *The agent uses* `collocations` (`pattern="privilégio*"`, `library="previdencia"`, `party=…`), one party at a time.

> **Ask:** "How many times does each party say *combater privilégios* (or *combater os privilégios*), per million
> words?"
>
> *The agent uses* `term_frequency` (`pattern="combater privilégios+combater os privilégios"`, `by="party"`,
> `library="previdencia"`).

<!-- table:mar_privilegios -->
| Party | Interventions with 'privilégio*' | Words around it | 'Combater (os) privilégios' | Per million |
|---|---:|---|---:|---:|
| PT | 162 | combater, combate, não, acabar, ataca, combatendo | 61 | 94.4 |
| PSOL | 33 | combater, combate, acabar, diz, dizem, atacar | 12 | 87.5 |
| PSL | 17 | quer, precisa, aposentadoria, quem, previdência, não | 0 | 0.0 |
| NOVO | 11 | verdade, combater, hoje, não | 3 | 100.0 |
<!-- /table -->

<!-- table:mar_frase -->
| Party | Uses | Interventions | The party's words in the library | Per million |
|---|---:|---:|---:|---:|
| PT | 61 | 36 | 646,423 | 94.4 |
| PSB | 15 | 13 | 109,771 | 136.7 |
| PSOL | 12 | 9 | 137,091 | 87.5 |
| PL | 6 | 2 | 14,794 | 405.6 |
| PCDOB | 5 | 2 | 115,881 | 43.1 |
| NOVO | 3 | 3 | 29,993 | 100.0 |
<!-- /table -->

*Combater* heads the words that accompany *privilégio* in the PT and the PSOL, and comes second in Novo. The PT says
*combater privilégios* 61 times, more than any other party, and the PSL not once. Per million words the PT (94.4) comes
below the PSB, Novo and the PL, which say it far fewer times in far less speech: with counts this small, a small
party's rate jumps with every use. From the numbers alone, it
would seem that the PT had adopted the government's frame. You have to read it.

> **Ask:** "Show me some PT sentences with *combater privilégios*, at random."
>
> *The agent uses* `kwic` (`pattern="combater privilégios"`, `library="previdencia"`, `party="PT"`, `n=6`,
> `width=90`).

<!-- table:mar_kwic -->
| Date | Party | Context |
|---|---|---|
| 2017-11-28 | PT | …. Então, vão diminuir o valor da aposentadoria do trabalhador mais pobre. Isso é **combater privilégios** ? Chega a ser um acinte dizer que isso é combater privilégios. Quem trabalha no … |
| 2017-11-28 | PT | … mais pobre. Isso é combater privilégios? Chega a ser um acinte dizer que isso é **combater privilégios** . Quem trabalha no fundo de uma mina de carvão, por exemplo, terá que trabalhar … |
| 2019-04-03 | PT | … contra a reforma da Previdência. Argumentam que esta reforma da Previdência vai **combater privilégios** , mas isso é mentira. Nós desafiamos quem diz isso a mostrar qual é o privilégio… |
| 2019-07-09 | PT | …eforma perversa. E eles se escondem na cortina de fumaça de que a reforma é para **combater privilégios** . Essa reforma não combate privilégios. Ela atinge a maioria do povo brasileiro,… |
| 2019-04-03 | PT | …m um País continental como o Brasil. É bom lembrar, inclusive, que o discurso de **combater privilégios** não tem a menor sustentação, porque, na verdade, eles estão destruindo o direito… |
| 2019-02-20 | PT | …io de uma das questões da antirreforma da Previdência, que eles dizem que é para **combater privilégios** . Eu quero aqui falar com os trabalhadores da construção civil, com os metalúrgi… |
| 2019-04-16 | PT | …xto. Quero dizer que, ao contrário do que o Governo diz, essa reforma não é para **combater privilégios** , porque de 1 trilhão de economia que está previsto, 85% serão pagos pelos traba… |
<!-- /table -->

These are six interventions drawn at random, and one says the phrase twice. In all seven lines, the PT quotes the
frame in order to deny it: 'Isso é combater privilégios?' [Is this fighting
privileges?], 'isso é mentira' [that is a lie], 'cortina de fumaça' [smokescreen], 'essa reforma não é para combater
privilégios' [this reform is not for fighting privileges]. The frame is the government's; the uses are the
opposition's challenge to it.

> [!IMPORTANT]
> A count does not tell adopting a frame from disputing it. Before saying that a group "uses" a frame, read a random
> sample with `kwic` (`order="random"`), and if you are going to count it, count the sentences that assert it and
> those that deny it separately.

## 5. The institutions named together

> **Ask:** "Which institutions are named together in the library, and which ones do the left or the right name most?
> Consider the INSS, Congress, the STF, the TCU, the Central Bank, the Finance or Economy Ministry, the trade union
> confederations, the banks, the Armed Forces and the courts."
>
> *The agent uses* `comention_network` (`library="previdencia"`, `entities=[…]` with one pattern per institution,
> `groups={"esquerda": [PT, PSOL, PCdoB, PDT, PSB, REDE], "direita": [PSL, PL, PR, PP, DEM, …]}`, `min_co=8`).

<!-- embed:redes/atores.html 720 -->

<!-- table:mar_actores -->
| Institution | Interventions | Left | Right | Rest | Bias |
|---|---:|---:|---:|---:|---:|
| Bancos | 403 | 333 | 24 | 46 | 0.56 |
| Congresso Nacional | 344 | 223 | 57 | 64 | -0.00 |
| INSS | 248 | 147 | 53 | 48 | -0.17 |
| Forças Armadas | 220 | 146 | 39 | 35 | -0.02 |
| Tribunais e Judiciário | 177 | 89 | 41 | 47 | -0.29 |
| STF | 165 | 110 | 35 | 20 | -0.11 |
| Centrais sindicais | 77 | 72 | 0 | 5 | 1.00 |
| Ministério da Fazenda / Economia | 62 | 35 | 16 | 11 | -0.28 |
| TCU | 33 | 18 | 7 | 8 | -0.21 |
| Banco Central | 32 | 18 | 6 | 8 | -0.13 |
<!-- /table -->

The left talks about the reform far more (2,090 interventions, against 532 from the right and 504 from the rest), so
the bias does not compare counts: it compares the share of each group's interventions that name the institution, and
it runs from −1 (only the right) to +1 (only the left). The banks are the most named institution (403 interventions)
and, among the much-named ones, the most left-leaning (0.56): they are the ones who would gain from capitalisation. The trade union
confederations are named only by the left (72 of 77, bias 1.00). Congress and the Armed Forces, whose own pension
scheme was discussed separately, come out balanced; the courts and the ministry lean slightly to the right.

## 6. Who names whom: the namesake

> **Ask:** "Which deputies do the left, the right and the rest name? Give me the matrix between groups and each
> group's E-I index."
>
> *The agent uses* `mention_network` (`library="previdencia"`, `groups=…`, `target_scope="speakers"`,
> `min_mentions=3`).

The result says that the left mostly names itself: 96 mentions from left deputies to left deputies, and an E-I index
of −0.27 (from −1, only their own, to +1, only the others). The most named deputy receives 103 mentions. But that
deputy's name matches the Economy Minister's, and the minister was not a deputy: the tool looks names up in the
register of deputies sitting on that day, and it credited the deputy with the minister's mentions.

> **Ask:** "Declare the Economy Minister as an external actor, with the ways they are named, and run the network again."
>
> *The agent uses* `mention_network` with `external_actors=[{"name": "Ministro da Economia", "role": "ministro",
> "aliases": […]}]` and `target_scope="both"`. External actors are looked up before deputies.

<!-- viz:mar_mencoes -->
<!-- table:mar_mencoes -->
| Names | Named | Minister not declared | Minister declared |
|---|---|---:|---:|
| right | right | 8 | 8 |
| right | left | 8 | 3 |
| right | minister | — | 8 |
| right | rest | 6 | 6 |
| left | right | 38 | 32 |
| left | left | 96 | 10 |
| left | minister | — | 131 |
| left | rest | 17 | 11 |
| rest | right | 12 | 12 |
| rest | minister | — | 8 |
| rest | rest | 22 | 16 |
| E-I | left | −0.27 | +0.62 |
| E-I | right | +0.27 | +0.06 |
| E-I | rest | −0.29 | −0.14 |
<!-- /table -->

The conclusion is reversed. Mentions from the left to the left fall from 96 to 10; those from the left to the minister
number 131, 6.3 per hundred interventions of the group. The left's E-I index goes from −0.27 to +0.62: it does not
talk about its own, it talks about the government.

> [!WARNING]
> `mention_network` finds deputies by their name in the register. A minister, a governor or a judge who shares a
> deputy's name is mistaken for that deputy. Before reading the network, look at the most named, read a few lines on
> each with `kwic` and declare those who are not deputies as `external_actors`. For publication, describe the actors
> by their office, as here.

## 7. What the study allows us to say

**What the data say.** The two reforms have different vocabularies: the one of 2016 and 2017 is debated alongside the
labour reform and the change of government; the one of 2019, with money, capitalisation and privileges. The frame of
'fighting privileges' appears mostly in the mouths of the opposition, which quotes it to deny it. The left names
mostly the banks and the trade union confederations, and on the floor it addresses the minister, not its own.

**What they do not say.** A word network proposes themes; it does not prove them: each theme has to be read in its
interventions (the interactive page links the first ones to read). An institution's bias says who names it, not in
what sense.

**The checks in this study.** Describe the library and its calendar before analysing it; remove personal names from
the themes; read a frame before counting it; compare each group's proportions, not counts; and review the most named
in a mention network before interpreting it.

> **Ask for it all at once:** "Study the frames of the pension reform debate in Brazil's Chamber, from December 2016 to
> November 2019: create a library, describe it and show how it is spread month by month; find its themes with a word
> network without personal names; compare 2016–2017 with 2019 and the PT with the PSL; follow the frame of *combater
> privilégios* by party and read a sample before counting it; look at which institutions the left and the right name,
> and who names whom. Review the most named in the mention network and declare those who are not deputies as external
> actors. Describe people by their office."
