# Combatir privilegios: la reforma de las pensiones en Brasil

<!-- eyebrow: Estudio 4 · Marcos interpretativos -->

*[English version](../en/marcos.md) · [Índice del tutorial](../TUTORIAL.md)*

Entre diciembre de 2016 y noviembre de 2019, la Cámara de Diputados de Brasil debatió dos reformas de las pensiones:
la PEC 287/2016, que se paró en febrero de 2018, y la PEC 6/2019, que se convirtió en la Enmienda Constitucional
103/2019. El Gobierno de 2019 la defendió como una reforma para «combatir privilegios»; la oposición la llamó
destrucción de la previdencia. Este estudio reúne esos debates en una biblioteca, busca sus temas con una red de
palabras, sigue un marco, mapea las instituciones que se nombran y pregunta quién nombra a quién. En el último paso,
un homónimo da la vuelta a la conclusión.

<!-- side -->

**La cadena de este estudio**

1. `library_create`: la biblioteca de las dos reformas
2. `query_sql`: la biblioteca, mes a mes
3. `cooccurrence_network`: los temas
4. `distinctive_words`: dos reformas, dos partidos
5. `collocations` y `term_frequency`: «privilégios»
6. `kwic`: leer el marco antes de contarlo
7. `comention_network`: las instituciones
8. `mention_network`: quién nombra a quién

## 1. La biblioteca de las dos reformas

> **Pide:** «Crea una biblioteca, *previdencia*, con las intervenciones de la Cámara de Brasil que nombren al menos dos
> veces *reforma da previdência*, *previdência social* o *aposentadoria*, de diciembre de 2016 a noviembre de 2019,
> sin la presidencia.»
>
> *El agente usa* `library_create` (`countries=["BR"]`,
> `terms="reforma da previdência+previdência social+aposentadoria*"`, `min_occurrences=2`,
> `date_from="2016-12-01"`, `date_to="2019-11-30"`, `exclude_chair=true`).

La biblioteca reúne 3.126 intervenciones de 505 sesiones, dichas por 466 oradores: 1,7 millones de palabras. El 98,6 %
está vinculado a un diputado; las diputadas son el 15,2 % de quienes tienen sexo en el registro, y los turnos largos
apenas pesan (0,7 % de las palabras). Una biblioteca es también una tabla, y se puede consultar con SQL.

> **Pide:** «¿Cómo se reparte la biblioteca mes a mes?»
>
> *El agente usa* `query_sql`, uniendo la biblioteca con las intervenciones:

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
| Año | Intervenciones | Mes con más (intervenciones) |
|---|---:|---|
| 2016 | 127 | 2016-12 (127) |
| 2017 | 1.283 | 2017-03 (283) |
| 2018 | 243 | 2018-02 (87) |
| 2019 | 1.473 | 2019-07 (382) |
<!-- /table -->

Se ven las dos reformas. La primera llena 2017 (283 intervenciones en marzo, 216 en diciembre) y se apaga en febrero de
2018, cuando la intervención federal en Río de Janeiro impidió votar enmiendas constitucionales. La segunda ocupa
2019 y culmina en julio, el mes de la primera votación en el pleno, con 382 intervenciones.

## 2. Los temas: una red de palabras

> **Pide:** «¿De qué temas se habló en la biblioteca y qué partidos los usan más? Deja fuera los nombres de persona.»
>
> *El agente usa* `cooccurrence_network` (`library="previdencia"`, `layout="clusters"`, `exclude=[…]`,
> `output_dir=…`). Escribe una página interactiva, tablas y un resumen.

<!-- embed:redes/palavras.html 760 -->

<!-- table:mar_temas -->
| Tema | Términos más característicos | Intervenciones con el tema (%) | Partidos que más lo usan | Los que menos |
|---:|---|---:|---|---|
| 1 | prestação continuada, regime próprio, previdenciários, déficit, regime geral, gastos, funrural, fiscal | 75,5 | PTB, PSD, NOVO | PP, PSDB, PMDB |
| 2 | nova previdência, previdência vai, aí, vai, mentira, brasil, dinheiro, agora | 97,5 | PSD, NOVO, PT | PMDB, PRB, PSDB |
| 3 | intermitente, tempo mínimo, tempo de contribuição, anos de contribuição, idade, homens, média, tempo mínimo de contribuição | 82,7 | PDT, PSB, PT | PMDB, NOVO, PSL |
| 4 | sobre a reforma, votar a reforma, contra a reforma, favor da reforma, votar a reforma da previdência, votação da reforma da previdência | 8,4 | DEM, PSD, PSOL | PCDOB, PSDB, PSL |
| 5 | destruição da previdência social, trabalhista, destruir a previdência, vivenciando, golpe, golpista, ilegítimo, governo ilegítimo | 84,4 | PT, PCDOB, PSOL | NOVO, PSDB, MDB |
| 6 | prestação, continuada, bpc, benefício, benefício de prestação continuada, aposentadoria rural, financeiro, idosos | 22,4 | PTB, PRB, PSD | PR, PSL, NOVO |
| 7 | combater privilégios, lucros e dividendos, salários mínimos, antirreforma, viúva, ganha, abono salarial, salário mínimo | 62,8 | PDT, PSOL, PSB | PSDB, PR, PODE |
| 8 | sistema de capitalização, chile, capitalização, regime de capitalização, transição, bancos, desta reforma | 16,0 | PDT, PSB, NOVO | PSL, PMDB, PR |
| 9 | fásica, regime geral da previdência, seguridade, comissão especial da reforma da previdência, previdenciário | 6,8 | DEM, PTB, PCDOB | PSD, PT, PODE |
<!-- /table -->

La red tiene 245 términos y 1.666 enlaces, agrupados en nueve temas. Cada uno es un vocabulario: el de las cuentas
(*déficit*, *regime próprio*, *gastos*, tema 1), el de las reglas (*tempo de contribuição*, *idade*, tema 3), el de los
más pobres (*benefício de prestação continuada*, *aposentadoria rural*, tema 6) y el del modelo chileno
(*capitalização*, *Chile*, tema 8). Dos son marcos en disputa. El tema 5, *destruição da previdência*, *golpe*,
*governo ilegítimo*, es el de la oposición de 2016 y 2017: lo usan más el PT, el PCdoB y el PSOL. El tema 7 reúne
*combater privilégios* con *lucros e dividendos*, *abono salarial* y *salário mínimo*: el marco del Gobierno y la
respuesta de quien pregunta quién paga.

> [!NOTE]
> Los nombres de persona salen de la red con `exclude`, después de leer los temas una primera vez: es la forma de
> trabajar con la herramienta, que primero propone y después se afina. La columna de intervenciones no suma 100: un
> tema está presente en una intervención si aparece uno de sus términos, y los temas se solapan.

## 3. Dos reformas, dos partidos

> **Pide:** «¿Qué palabras distinguen los debates de 2016 y 2017 de los de 2019?»
>
> *El agente usa* `distinctive_words` (`field="period"`, `a="2016-2017"`, `b="2019-2019"`,
> `library="previdencia"`, `exclude_chair=true`).

<!-- viz:mar_periodo -->
<!-- table:mar_periodo -->
|  | 2016–2017 | z | 2019 | z |
|---:|---|---:|---|---:|
| 1 | trabalhista | 14,2 | reais | 18,6 |
| 2 | golpe | 13,7 | sra | 17,7 |
| 3 | direitos | 13,3 | pobres | 16,2 |
| 4 | mulheres | 12,1 | aqui | 15,4 |
| 5 | de | 11,5 | eu | 15,3 |
| 6 | em | 11,3 | nós | 13,9 |
| 7 | as | 11,3 | oposição | 13,6 |
| 8 | trabalho | 10,8 | educação | 13,5 |
| 9 | terceirização | 10,6 | deputado | 13,4 |
| 10 | trabalhadores | 9,7 | ganha | 12,4 |
| 11 | empresas | 9,6 | economia | 12,3 |
| 12 | ano | 9,1 | mais | 12,3 |
| 13 | contra | 9,0 | capitalização | 12,2 |
| 14 | art | 8,9 | privilégios | 12,1 |
| 15 | golpista | 8,8 | reforma | 11,7 |
<!-- /table -->

La primera reforma se debatió junto con otras: *trabalhista* y *terceirização* son la reforma laboral y la ley de
subcontratación de 2017, y *golpe* y *golpista*, el marco con que la oposición leyó el cambio de gobierno de 2016. La
de 2019 habla de dinero (*reais*, *economia*, *ganha*), de *pobres*, de *capitalização* y de *privilégios*.

> **Pide:** «En 2019, ¿qué palabras distinguen al PT del PSL?»
>
> *El agente usa* `distinctive_words` (`field="party"`, `a="PT"`, `b="PSL"`, `library="previdencia"`,
> `date_from="2019-01-01"`, `exclude_chair=true`).

<!-- viz:mar_pt_psl -->
<!-- table:mar_pt_psl -->
|  | PT | z | PSL | z |
|---:|---|---:|---|---:|
| 1 | trabalhadores | 9,2 | eu | 13,0 |
| 2 | proposta | 8,2 | todos | 10,1 |
| 3 | se | 7,0 | nova | 9,3 |
| 4 | trabalhador | 7,0 | esquerda | 9,1 |
| 5 | salário | 6,8 | muito | 8,8 |
| 6 | dos | 6,5 | tenho | 8,3 |
| 7 | povo | 6,2 | psl | 8,3 |
| 8 | direitos | 6,1 | nosso | 7,8 |
| 9 | mínimo | 6,0 | meu | 7,6 |
| 10 | mulheres | 6,0 | segurança | 7,4 |
| 11 | aposentar | 5,9 | me | 7,2 |
| 12 | direito | 5,8 | bem | 7,2 |
| 13 | pobres | 5,6 | meus | 7,2 |
| 14 | portanto | 5,5 | corrupção | 6,5 |
| 15 | social | 5,2 | sou | 6,4 |
<!-- /table -->

El PT habla de *trabalhadores*, *salário mínimo*, *povo*, *direitos*, *mulheres* y *pobres*. El PSL, el partido del
Gobierno de 2019, habla en primera persona (*eu*, *meu*, *tenho*, *sou*), nombra al adversario (*esquerda*) y usa la
etiqueta oficial, *nova* previdência, junto a *segurança* y *corrupção*.

## 4. «Privilégios»: un marco, dos usos

> **Pide:** «¿Qué palabras acompañan a *privilégio* en los discursos del PT, el PSOL, el PSL y el Novo?»
>
> *El agente usa* `collocations` (`pattern="privilégio*"`, `library="previdencia"`, `party=…`), un partido cada vez.

> **Pide:** «¿Cuántas veces dice cada partido *combater privilégios* (o *combater os privilégios*), por millón de
> palabras?»
>
> *El agente usa* `term_frequency` (`pattern="combater privilégios+combater os privilégios"`, `by="party"`,
> `library="previdencia"`).

<!-- table:mar_privilegios -->
| Partido | Intervenciones con «privilégio*» | Palabras que lo acompañan | «Combater (os) privilégios» | Por millón |
|---|---:|---|---:|---:|
| PT | 162 | combater, combate, não, acabar, ataca, combatendo | 61 | 94,4 |
| PSOL | 33 | combater, combate, acabar, diz, dizem, atacar | 12 | 87,5 |
| PSL | 17 | quer, precisa, aposentadoria, quem, previdência, não | 0 | 0,0 |
| NOVO | 11 | verdade, combater, hoje, não | 3 | 100,0 |
<!-- /table -->

<!-- table:mar_frase -->
| Partido | Usos | Intervenciones | Palabras del partido en la biblioteca | Por millón |
|---|---:|---:|---:|---:|
| PT | 61 | 36 | 646.423 | 94,4 |
| PSB | 15 | 13 | 109.771 | 136,7 |
| PSOL | 12 | 9 | 137.091 | 87,5 |
| PL | 6 | 2 | 14.794 | 405,6 |
| PCDOB | 5 | 2 | 115.881 | 43,1 |
| NOVO | 3 | 3 | 29.993 | 100,0 |
<!-- /table -->

*Combater* es la primera compañera de *privilégio* en el PT y el PSOL, y la segunda en el Novo. El PT dice *combater
privilégios* 61 veces, más que ningún otro partido, y el PSL, ninguna. Por millón de palabras el PT (94,4) queda por
debajo del PSB, el Novo y el PL, que la dicen muchas menos veces en mucho menos discurso: con recuentos tan pequeños,
la tasa de un partido pequeño salta con cada uso. Con los números solos, parecería que el PT
adoptó el marco del Gobierno. Hay que leerlo.

> **Pide:** «Enséñame frases del PT con *combater privilégios*, al azar.»
>
> *El agente usa* `kwic` (`pattern="combater privilégios"`, `library="previdencia"`, `party="PT"`, `n=6`,
> `width=90`).

<!-- table:mar_kwic -->
| Fecha | Partido | Contexto |
|---|---|---|
| 2017-11-28 | PT | …. Então, vão diminuir o valor da aposentadoria do trabalhador mais pobre. Isso é **combater privilégios** ? Chega a ser um acinte dizer que isso é combater privilégios. Quem trabalha no … |
| 2017-11-28 | PT | … mais pobre. Isso é combater privilégios? Chega a ser um acinte dizer que isso é **combater privilégios** . Quem trabalha no fundo de uma mina de carvão, por exemplo, terá que trabalhar … |
| 2019-04-03 | PT | … contra a reforma da Previdência. Argumentam que esta reforma da Previdência vai **combater privilégios** , mas isso é mentira. Nós desafiamos quem diz isso a mostrar qual é o privilégio… |
| 2019-07-09 | PT | …eforma perversa. E eles se escondem na cortina de fumaça de que a reforma é para **combater privilégios** . Essa reforma não combate privilégios. Ela atinge a maioria do povo brasileiro,… |
| 2019-04-03 | PT | …m um País continental como o Brasil. É bom lembrar, inclusive, que o discurso de **combater privilégios** não tem a menor sustentação, porque, na verdade, eles estão destruindo o direito… |
| 2019-02-20 | PT | …io de uma das questões da antirreforma da Previdência, que eles dizem que é para **combater privilégios** . Eu quero aqui falar com os trabalhadores da construção civil, com os metalúrgi… |
| 2019-04-16 | PT | …xto. Quero dizer que, ao contrário do que o Governo diz, essa reforma não é para **combater privilégios** , porque de 1 trilhão de economia que está previsto, 85% serão pagos pelos traba… |
<!-- /table -->

Son seis intervenciones al azar, y una dice la frase dos veces. En las siete líneas, el PT cita el marco para
negarlo: «¿Isso é combater privilégios?», «isso é mentira», «cortina de
fumaça», «essa reforma não é para combater privilégios». El marco es del Gobierno; los usos son la impugnación de la
oposición.

> [!IMPORTANT]
> Un recuento no distingue entre adoptar un marco y discutirlo. Antes de decir que un grupo «usa» un marco, lee una
> muestra al azar con `kwic` (`order="random"`), y si vas a contarlo, cuenta por separado las frases que lo afirman y
> las que lo niegan.

## 5. Las instituciones que se nombran juntas

> **Pide:** «¿Qué instituciones se nombran juntas en la biblioteca, y cuáles nombra más la izquierda o la derecha?
> Considera el INSS, el Congreso, el STF, el TCU, el Banco Central, el Ministerio de Hacienda o de Economía, las
> centrales sindicales, los bancos, las Fuerzas Armadas y los tribunales.»
>
> *El agente usa* `comention_network` (`library="previdencia"`, `entities=[…]` con un patrón por institución,
> `groups={"esquerda": [PT, PSOL, PCdoB, PDT, PSB, REDE], "direita": [PSL, PL, PR, PP, DEM, …]}`, `min_co=8`).

<!-- embed:redes/atores.html 720 -->

<!-- table:mar_actores -->
| Institución | Intervenciones | Izquierda | Derecha | Resto | Sesgo |
|---|---:|---:|---:|---:|---:|
| Bancos | 403 | 333 | 24 | 46 | 0,56 |
| Congresso Nacional | 344 | 223 | 57 | 64 | -0,00 |
| INSS | 248 | 147 | 53 | 48 | -0,17 |
| Forças Armadas | 220 | 146 | 39 | 35 | -0,02 |
| Tribunais e Judiciário | 177 | 89 | 41 | 47 | -0,29 |
| STF | 165 | 110 | 35 | 20 | -0,11 |
| Centrais sindicais | 77 | 72 | 0 | 5 | 1,00 |
| Ministério da Fazenda / Economia | 62 | 35 | 16 | 11 | -0,28 |
| TCU | 33 | 18 | 7 | 8 | -0,21 |
| Banco Central | 32 | 18 | 6 | 8 | -0,13 |
<!-- /table -->

La izquierda habla mucho más de la reforma (2.090 intervenciones, frente a 532 de la derecha y 504 del resto), así que
el sesgo no compara recuentos: compara la parte de las intervenciones de cada grupo que nombra a la institución, y va
de −1 (solo la derecha) a +1 (solo la izquierda). Los *bancos* son la institución más nombrada (403 intervenciones) y,
de las muy nombradas, la que más se inclina a la izquierda (0,56): son los que ganarían con la capitalización. Las centrales sindicales solo las nombra la
izquierda (72 de 77, sesgo 1,00). El Congreso y las Fuerzas Armadas, cuyo régimen propio se discutió aparte, salen
equilibrados; los tribunales y el ministerio, algo más de derecha.

## 6. Quién nombra a quién: el homónimo

> **Pide:** «¿A qué diputados nombran la izquierda, la derecha y el resto? Dame la matriz entre grupos y el índice
> E-I de cada uno.»
>
> *El agente usa* `mention_network` (`library="previdencia"`, `groups=…`, `target_scope="speakers"`,
> `min_mentions=3`).

El resultado dice que la izquierda se nombra sobre todo a sí misma: 96 menciones de diputados de izquierda a diputados
de izquierda, y un índice E-I de −0,27 (de −1, solo a los suyos, a +1, solo a los demás). El diputado más nombrado
recibe 103 menciones. Pero su nombre coincide con el del ministro de Economía, que no era diputado: la herramienta
busca los nombres en el registro de diputados en ejercicio ese día y le atribuyó las menciones del ministro.

> **Pide:** «Declara al ministro de Economía como actor externo, con las formas en que se le nombra, y repite la red.»
>
> *El agente usa* `mention_network` con `external_actors=[{"name": "Ministro da Economia", "role": "ministro",
> "aliases": […]}]` y `target_scope="both"`. Los actores externos se buscan antes que los diputados.

<!-- viz:mar_mencoes -->
<!-- table:mar_mencoes -->
| Nombra | Nombrado | Sin declarar al ministro | Con el ministro declarado |
|---|---|---:|---:|
| derecha | derecha | 8 | 8 |
| derecha | izquierda | 8 | 3 |
| derecha | ministro | — | 8 |
| derecha | resto | 6 | 6 |
| izquierda | derecha | 38 | 32 |
| izquierda | izquierda | 96 | 10 |
| izquierda | ministro | — | 131 |
| izquierda | resto | 17 | 11 |
| resto | derecha | 12 | 12 |
| resto | ministro | — | 8 |
| resto | resto | 22 | 16 |
| E-I | izquierda | −0,27 | +0,62 |
| E-I | derecha | +0,27 | +0,06 |
| E-I | resto | −0,29 | −0,14 |
<!-- /table -->

La conclusión se invierte. Las menciones de la izquierda a la izquierda bajan de 96 a 10; las de la izquierda al
ministro son 131, 6,3 por cada cien intervenciones del grupo. El índice E-I de la izquierda pasa de −0,27 a +0,62: no
habla de los suyos, habla del Gobierno.

> [!WARNING]
> `mention_network` encuentra a los diputados por su nombre en el registro. Un ministro, un gobernador o un juez que
> se llame como un diputado se confunde con él. Antes de leer la red, mira los más nombrados, lee unas líneas de cada
> uno con `kwic` y declara como `external_actors` a quienes no son diputados. Para publicar, describe a los actores
> por su cargo, como aquí.

## 7. Lo que el estudio permite decir

**Lo que dicen los datos.** Las dos reformas tienen vocabularios distintos: la de 2016 y 2017 se discute con la
reforma laboral y el cambio de gobierno; la de 2019, con el dinero, la capitalización y los privilegios. El marco de
«combatir privilegios» aparece sobre todo en boca de la oposición, que lo cita para negarlo. La izquierda nombra
sobre todo a los bancos y a las centrales sindicales, y en el pleno se dirige al ministro, no a los suyos.

**Lo que no dicen.** Una red de palabras propone temas, no los demuestra: cada tema hay que leerlo en sus
intervenciones (la página interactiva enlaza las primeras que leer). El sesgo de una institución dice quién la
nombra, no en qué sentido.

**Las comprobaciones de este estudio.** Describir la biblioteca y su calendario antes de analizarla; quitar los
nombres de persona de los temas; leer un marco antes de contarlo; comparar proporciones de cada grupo y no recuentos;
y revisar los más nombrados de una red de menciones antes de interpretarla.

> **Pídelo de una vez:** «Estudia los marcos del debate de la reforma de las pensiones en la Cámara de Brasil, de
> diciembre de 2016 a noviembre de 2019: crea una biblioteca, descríbela y muestra cómo se reparte mes a mes; busca sus
> temas con una red de palabras sin nombres de persona; compara 2016–2017 con 2019 y el PT con el PSL; sigue el marco
> de *combater privilégios* por partido y lee una muestra antes de contarlo; mira qué instituciones nombran la izquierda
> y la derecha, y quién nombra a quién. Revisa los más nombrados de la red de menciones y declara como actores
> externos a los que no sean diputados. Describe a las personas por su cargo.»
