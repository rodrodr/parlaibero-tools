# Un virus, dieciséis plenos

<!-- eyebrow: Estudio 2 · La reacción a un acontecimiento -->

*[English version](../en/pandemia.md) · [Índice del tutorial](../TUTORIAL.md)*

El 11 de marzo de 2020 la Organización Mundial de la Salud declaró la pandemia de COVID-19. Los dieciséis parlamentos
vivieron la misma noticia con calendarios, reglamentos y tamaños muy distintos. Este estudio pregunta cuándo nombró
cada pleno la enfermedad, cuánta atención le dedicó semana a semana, quién dejó de reunirse y, con una biblioteca
construida alrededor de la fecha, de qué habló cada cámara y quién lo hizo. Es también un estudio sobre los falsos
positivos: tres de los dieciséis «primeros usos» no hablan del virus.

<!-- side -->

**La cadena de este estudio**

1. `term_counter`: el primer uso en cada pleno
2. `kwic`: leer los primeros usos
3. `query_sql`: cuándo dejó de reunirse cada cámara
4. `query_sql`: la atención, semana a semana
5. `library_create`: una biblioteca alrededor del 11 de marzo
6. `library_describe`: qué hay en ella antes de comparar
7. `distinctive_words`: de qué habló cada cámara
8. `share_of_voice`: quién habló, frente a una línea de base

## 1. El primer uso en cada pleno

> **Pide:** «¿Cuándo se dijo por primera vez *coronavirus* o *covid* en cada parlamento? Busca desde junio de 2019.»
>
> *El agente usa* `term_counter` (`terms="coronavirus+covid*"`, `date_from="2019-06-01"`). El asterisco acepta
> cualquier final: *covid*, *covid-19*, *covid19*.

La respuesta trae tres fechas imposibles. Ecuador dice junio de 2019, seis meses antes de que se conociera el virus;
El Salvador, diciembre de 2019; Guatemala, el 21 de enero de 2020, con la palabra «COVID-19», que la OMS no acuñó hasta
el 11 de febrero. Antes de creerlas, hay que leerlas.

> **Pide:** «Enséñame los primeros usos de Ecuador, El Salvador y Guatemala, por orden de fecha.»
>
> *El agente usa* `kwic` (`pattern="\b(covid|coronavirus)"`, `regex=true`, `order="oldest"`, `n=3`), un país cada
> vez.

Las concordancias lo aclaran. En Ecuador, «Covid» es el comienzo del nombre de una organización que aparece en listas
de oficios leídas en el pleno, en junio y otra vez en octubre de 2019. En El Salvador es «Covidien», una marca de
material quirúrgico en una lista de compras. En Guatemala la palabra es la de verdad, pero se habla de ella en pasado
(«en el tiempo del COVID»): la sesión está mal fechada. Las tres se corrigen con la siguiente lectura (`kwic` desde
otra fecha), que da el primer uso real.

> [!WARNING]
> Un prefijo como `covid*` atrapa cualquier palabra que empiece igual, y una fecha del acta puede estar mal. Cuando el
> resultado depende del primer o del último uso, lee esas líneas con `kwic` y `order="oldest"` antes de dar la fecha
> por buena. Al citar, parafrasea: las listas leídas en el pleno contienen nombres de personas particulares.

Falta un dato para leer el calendario: si la cámara se reunía.

> **Pide:** «¿Cuál fue la última sesión de cada parlamento antes del 11 de marzo de 2020, cuál la primera después, y
> cuántas sesiones celebró en los 120 días siguientes?»
>
> *El agente usa* `query_sql`:

```sql
SELECT country,
       max(date) FILTER (WHERE date < DATE '2020-03-11') AS last_before,
       min(date) FILTER (WHERE date >= DATE '2020-03-11') AS first_after,
       count(DISTINCT id_session) FILTER (WHERE date BETWEEN DATE '2020-03-11' AND DATE '2020-07-09') AS sessions_120_days
FROM interventions
WHERE date BETWEEN DATE '2019-10-01' AND DATE '2020-12-31'
GROUP BY 1 ORDER BY 1
```

Con las tres correcciones y las fechas de sesión, el calendario queda así:

<!-- viz:pan_primeros -->
<!-- table:pan_primeros -->
| País | Primer uso real | Partido | Última sesión antes del 11-mar | Primera después | Sesiones en 120 días | Usos hasta 2025 | Lo que se corrigió |
|---|---|---|---|---|---:|---:|---|
| México | 2020-01-28 | MORENA | 2020-03-10 | 2020-03-12 | 4 | 5.414 |  |
| Chile | 2020-01-29 | IND | 2020-03-10 | 2020-03-11 | 40 | 3.660 |  |
| Guatemala | 2020-01-30 | (no vinculado) | 2020-03-10 | 2020-03-11 | 16 | 2.276 | falso positivo el 2020-01-21: una sesión fechada el 21 de enero de 2020 que habla de «COVID-19» en pasado: la fecha está mal |
| Panamá | 2020-01-30 | CD | 2020-03-04 | 2020-03-11 | 30 | 2.215 |  |
| El Salvador | 2020-01-30 | PDC | 2020-03-05 | 2020-03-12 | 32 | 4.508 | falso positivo el 2019-12-19: una marca de material quirúrgico («Covidien») en una lista de compras |
| Brasil | 2020-02-04 | PSL | 2020-03-10 | 2020-03-11 | 74 | 10.337 |  |
| España | 2020-02-04 | UP | 2020-02-27 | 2020-03-18 | 19 | 3.751 |  |
| Perú | 2020-02-05 | FUERZA POPULAR | 2020-03-10 | 2020-03-11 | 16 | 5.056 |  |
| Portugal | 2020-03-04 | PS | 2020-03-06 | 2020-03-11 | 36 | 3.460 |  |
| Costa Rica | 2020-03-05 | UNIDAD SOCIAL CRISTIANA | 2020-03-10 | 2020-03-11 | 50 | 1.435 |  |
| Uruguay | 2020-03-17 | Partido Nacional | 2020-03-10 | 2020-03-11 | 25 | 3.948 |  |
| Rep. Dominicana | 2020-03-19 | (no vinculado) | 2020-03-04 | 2020-03-18 | 11 | 506 |  |
| Ecuador | 2020-03-24 | (no vinculado) | 2020-02-18 | 2020-03-24 | 39 | 2.453 | falso positivo el 2019-06-20: el nombre de una organización que empieza por «Covid», en listas de oficios leídas en el pleno (también el 2019-10-24) |
| Colombia | 2020-04-21 | Cambio Radical | 2019-12-20 | 2020-04-21 | 23 | 2.289 |  |
| Argentina | 2020-05-13 | FRENTE RENOVADOR, FEDERAL UNIDOS POR UNA NUEVA ARGENTINA, FRENTE DE TODOS | 2020-03-01 | 2020-05-13 | 4 | 964 |  |
| Paraguay | 2020-09-02 | Partido Liberal Radical Auténtico | (corpus vacío) | 2020-09-02 | 0 | 1.070 |  |
<!-- /table -->

Los primeros usos reales se reparten en tres momentos. México, Chile, Guatemala, Panamá y El Salvador nombran el virus
entre el 28 y el 30 de enero de 2020 (el 30 la OMS declaró la emergencia de salud pública internacional); Brasil,
España y Perú, a primeros de febrero; Portugal y Costa Rica, a primeros de marzo. Los últimos en hacerlo no son los más lentos, sino los que no se reunían:
Argentina no tuvo sesiones entre el 1 de marzo y el 13 de mayo, Colombia entre el 20 de diciembre y el 21 de abril, Ecuador entre el 18 de febrero y el 24 de marzo, y el corpus de
Paraguay no tiene sesiones desde abril de 2019 hasta septiembre de 2020. En estos cuatro casos, el primer uso coincide
con la primera sesión: mide el calendario, no la reacción.

## 2. La atención, semana a semana

Un recuento total favorece a las cámaras que más hablan. Para comparar la atención, mejor la parte de las
intervenciones de cada semana que nombran la enfermedad.

> **Pide:** «Semana a semana, de enero a septiembre de 2020, ¿qué parte de las intervenciones de cada pleno nombra
> *covid* o *coronavirus*? Cuenta las semanas desde la declaración de la OMS.»
>
> *El agente usa* `query_sql`:

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
| País | Semanas con sesión (0–12) | Media de las semanas 0–12 (%) | Semana más alta (%) |
|---|---:|---:|---:|
| España | 11 / 13 | 19,3 | 29,7 (semana 4) |
| El Salvador | 13 / 13 | 15,5 | 27,3 (semana 15) |
| Argentina | 3 / 13 | 10,5 | 17,7 (semana 9) |
| Portugal | 12 / 13 | 10,0 | 15,4 (semana 5) |
| Perú | 8 / 13 | 9,4 | 22,7 (semana 19) |
| Ecuador | 11 / 13 | 9,3 | 17,3 (semana 1) |
| Chile | 13 / 13 | 8,9 | 13,5 (semana 13) |
| Costa Rica | 13 / 13 | 8,5 | 21,1 (semana 8) |
| Panamá | 8 / 13 | 8,2 | 17,6 (semana 14) |
| Uruguay | 12 / 13 | 6,6 | 19,1 (semana 8) |
| Guatemala | 7 / 13 | 6,5 | 23,8 (semana 18) |
| Rep. Dominicana | 5 / 13 | 4,8 | 12,5 (semana 18) |
| Colombia | 8 / 13 | 3,7 | 10,5 (semana 5) |
| México | 2 / 13 | 3,0 | 12,6 (semana 29) |
| Brasil | 13 / 13 | 2,8 | 4,6 (semana 16) |
| Paraguay | 0 / 13 | — | 4,7 (semana 25) |
<!-- /table -->

España dedica a la enfermedad el 19,3 % de sus intervenciones en las trece semanas que siguen a la declaración, con
un máximo del 29,7 % en la cuarta (del 8 al 14 de abril). El Salvador la sigue con el 15,5 %. Brasil, que es la cámara
que más veces dice la palabra en todo el periodo (10.337), queda casi al final con el 2,8 %: sus plenos se componen de
muchísimas intervenciones breves (la mediana de las de sus diputados desde 2021 es de 25 palabras, como se ve en el
[estudio 3](voz.md)), y la mayoría no tratan del asunto. México y Argentina solo tienen dos y tres semanas con sesión en esos tres meses, y Paraguay ninguna.

> [!NOTE]
> Una proporción de intervenciones depende de cómo trocea cada cámara su debate. Para comparar países es mejor que un
> recuento, pero no es neutral: dos cámaras con la misma atención pueden dar cifras distintas si una interrumpe más que
> otra. La tabla de palabras (`unigrams`) o `ngram_viewer` con `measure="per_million"` dan la otra medida, por palabras.

## 3. Una biblioteca alrededor del 11 de marzo

Para pasar de contar a comparar contenidos conviene aislar los debates del asunto. Una biblioteca guarda, país por país,
las intervenciones que cumplen una definición; todas las herramientas de análisis aceptan después `library=`.

> **Pide:** «Crea una biblioteca, *pandemia*, con las intervenciones que nombren *coronavirus*, *covid* o *pandemia* al
> menos dos veces, desde 30 días antes hasta 120 después del 11 de marzo de 2020, en los dieciséis países y sin la
> presidencia de la sesión.»
>
> *El agente usa* `library_create` (`terms="coronavirus+covid+pandemia"`, `min_occurrences=2`,
> `event_dates={…: "2020-03-11"}`, `days_before=30`, `days_after=120`, `exclude_chair=true`).

Aquí *covid* va sin asterisco: la búsqueda por palabra entera encuentra *covid-19* (el guion separa palabras), pero no
*Covidien*. La biblioteca guarda la definición de cada país y la versión de los datos con que se creó.

> **Pide:** «Antes de comparar, dime qué hay en la biblioteca.»
>
> *El agente usa* `library_describe` (`name="pandemia"`).

<!-- table:pan_biblioteca -->
| País | Intervenciones | Sesiones | Fechas | Oradores | Palabras | Vinculadas (%) | Mujeres (% de las que tienen sexo) | Palabras en turnos largos (%) |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| Argentina | 117 | 4 | 2020-05-13 – 2020-06-25 | 71 | 82.863 | 94,9 | 45,5 | 0,0 |
| Brasil | 1.481 | 76 | 2020-02-17 – 2020-07-09 | 294 | 798.021 | 97,7 | 25,4 | 0,0 |
| Chile | 488 | 39 | 2020-03-03 – 2020-07-09 | 142 | 337.630 | 91,2 | 24,0 | 0,0 |
| Colombia | 428 | 22 | 2020-04-21 – 2020-06-20 | 140 | 362.411 | 83,2 | 20,8 | 6,1 |
| Costa Rica | 183 | 39 | 2020-02-17 – 2020-07-02 | 55 | 194.374 | 99,5 | 44,0 | 0,0 |
| Rep. Dominicana | 15 | 7 | 2020-03-19 – 2020-06-18 | 9 | 9.266 | 100,0 | 6,7 | 0,0 |
| Ecuador | 324 | 34 | 2020-03-24 – 2020-07-07 | 132 | 591.827 | 82,1 | 32,0 | 25,9 |
| España | 374 | 19 | 2020-03-18 – 2020-06-25 | 127 | 545.459 | 94,7 | 39,3 | 3,8 |
| Guatemala | 206 | 17 | 2020-02-11 – 2020-06-27 | 61 | 145.637 | 99,5 | 15,1 | 0,0 |
| México | 48 | 10 | 2020-02-11 – 2020-06-30 | 36 | 163.081 | 100,0 | 72,9 | 58,1 |
| Panamá | 273 | 30 | 2020-02-10 – 2020-07-09 | 65 | 195.329 | 79,9 | 30,7 | 0,0 |
| Perú | 323 | 13 | 2020-02-26 – 2020-07-06 | 125 | 194.889 | 93,5 | 28,1 | 6,7 |
| Portugal | 426 | 37 | 2020-03-04 – 2020-07-09 | 147 | 218.700 | 91,3 | 46,3 | 0,0 |
| Paraguay | 0 | — | — | — | — | — | — | — |
| El Salvador | 618 | 32 | 2020-02-15 – 2020-07-09 | 71 | 467.835 | 99,5 | 26,0 | 0,0 |
| Uruguay | 93 | 19 | 2020-03-25 – 2020-07-08 | 57 | 126.195 | 96,8 | 15,6 | 8,1 |
<!-- /table -->

Son 5.397 intervenciones de quince países: Paraguay no tiene ninguna, porque su corpus no tiene sesiones en esas
fechas. La herramienta avisa de tres cosas que cambian el análisis. Las partes difieren en tamaño más de diez veces
(15 intervenciones de la República Dominicana, 1.481 de Brasil), así que hay que comparar tasas dentro de cada cámara,
no recuentos juntos. En México, el 58,1 % de las palabras está en turnos de más de 10.000 palabras, casi siempre
documentos leídos en el pleno, y en Ecuador el 25,9 %: las comparaciones por palabras deben repetirse con
`max_turn_words=10000`. Y las cámaras de lengua portuguesa y española necesitan los términos en las dos lenguas, y sus
listas de palabras comparan lenguas tanto como debates.

## 4. De qué habló cada cámara

> **Pide:** «En la biblioteca, ¿qué palabras distinguen al Congreso español de las otras cámaras de habla hispana? Deja
> fuera los turnos de más de 10.000 palabras.»
>
> *El agente usa* `distinctive_words` (`field="country"`, `a="ES"`, `library="pandemia"`,
> `countries=[los catorce de habla hispana]`, `max_turn_words=10000`).

<!-- viz:pan_es -->
<!-- table:pan_es -->
|  | España | z | las otras 12 cámaras de habla hispana | z |
|---:|---|---:|---|---:|
| 1 | usted | 46,6 | presidente | 30,6 |
| 2 | españa | 36,2 | salud | 25,2 |
| 3 | ustedes | 35,4 | proyecto | 23,9 |
| 4 | gobierno | 33,3 | ley | 23,8 |
| 5 | señora | 30,7 | nacional | 23,2 |
| 6 | real | 29,2 | artículo | 22,3 |
| 7 | comunidades | 27,1 | mil | 18,2 |
| 8 | aplausos | 26,8 | del | 16,8 |
| 9 | autónomos | 26,0 | diputados | 16,8 |
| 10 | autónomas | 24,5 | emergencia | 15,7 |
| 11 | ha | 23,8 | comisión | 15,7 |
| 12 | medidas | 23,6 | covid | 15,5 |
| 13 | presidenta | 23,5 | tema | 15,4 |
| 14 | sanidad | 23,3 | república | 15,2 |
<!-- /table -->

La lista dice más de cómo se debate que de lo que se debate. Del lado español están las formas de dirigirse al
Gobierno (*usted*, *ustedes*, *señora*, *gobierno*), el Estado autonómico (*comunidades*, *autónomas*), el decreto ley
con que se gobernó la emergencia (*real*, de *real decreto*) y una convención del acta, que anota los *aplausos*. Del
otro lado, el procedimiento legislativo (*proyecto*, *ley*, *artículo*, *comisión*) y el trato a quien preside
(*presidente*). Los dos debates son sobre la pandemia; lo que los separa es el tipo de parlamento.

> **Pide:** «Haz lo mismo entre Portugal y Brasil.»
>
> *El agente usa* `distinctive_words` (`field="country"`, `a="PT"`, `b="BR"`, `library="pandemia"`,
> `max_turn_words=10000`).

<!-- viz:pan_ptbr -->
<!-- table:pan_ptbr -->
|  | Portugal | z | Brasil | z |
|---:|---|---:|---|---:|
| 1 | as | 26,4 | presidente | 27,0 |
| 2 | srs | 24,7 | nós | 21,8 |
| 3 | resposta | 24,4 | eu | 20,3 |
| 4 | de | 23,1 | ele | 16,7 |
| 5 | medidas | 22,3 | esse | 16,1 |
| 6 | das | 20,2 | essa | 15,9 |
| 7 | psd | 19,4 | projeto | 15,6 |
| 8 | portugal | 18,5 | quero | 15,4 |
| 9 | emergência | 17,4 | coronavírus | 14,1 |
| 10 | baixa | 17,2 | muito | 13,9 |
| 11 | covid | 16,7 | isso | 13,7 |
| 12 | estas | 16,6 | brasil | 13,6 |
| 13 | apoio | 16,3 | momento | 13,4 |
| 14 | serviço | 16,1 | deputado | 13,1 |
| 15 | sr | 15,9 | estados | 12,8 |
<!-- /table -->

Aquí la lengua pesa todavía más. Portugal tiene *as*, *das*, *de*, *srs.* y *sr.*, las formas del portugués europeo y
del tratamiento del acta; Brasil, *nós*, *eu*, *ele*, *esse*, *essa*, *quero*, la oralidad del portugués brasileño.
Entre ellas asoma el contenido: en Portugal, *resposta*, *medidas*, *apoio*, *serviço* y *emergência* (el estado de
emergencia); en Brasil, *coronavírus*, que en Portugal se decía *covid*, y *estados*, la federación. Y una palabra que
parece de contenido y no lo es: *baixa* viene casi siempre de la fórmula con que el acta portuguesa anuncia que un
proyecto «baixa à 6.ª Comissão». Leer cinco líneas con `kwic` basta para saberlo.

> **Pide:** «¿Y Perú frente al resto de cámaras de habla hispana?»
>
> *El agente usa* `distinctive_words` (`field="country"`, `a="PE"`, `library="pandemia"`, `max_turn_words=10000`).

<!-- table:pan_pe -->
|  | Perú | z | las demás | z |
|---:|---|---:|---|---:|
| 1 | perú | 34,9 | yo | 10,6 |
| 2 | congresistas | 27,5 | lo | 9,9 |
| 3 | salud | 26,7 | aquí | 9,6 |
| 4 | personal | 22,8 | ciento | 9,0 |
| 5 | corrupción | 22,4 | número | 8,5 |
| 6 | congreso | 21,9 | que | 8,1 |
| 7 | ministros | 20,9 | social | 7,9 |
| 8 | presidente | 20,6 | asamblea | 7,8 |
| 9 | oxígeno | 19,8 | le | 7,5 |
| 10 | región | 18,2 | mil | 7,2 |
| 11 | regionales | 17,6 | dólares | 6,9 |
| 12 | ejecutivo | 17,4 | medidas | 6,8 |
| 13 | intermedio | 16,5 | dos | 6,6 |
| 14 | congresista | 15,5 | compañeros | 6,5 |
| 15 | contraloría | 15,5 | españa | 6,4 |
<!-- /table -->

Perú tiene un debate propio: *oxígeno* (las muertes por falta de oxígeno medicinal), *corrupción* y *contraloría*,
*ministros* y *ejecutivo*, las *regiones*. *Intermedio* es otra cosa: la cortesía con que los congresistas se dirigen a
otros «por intermedio» de la Presidencia.

> [!TIP]
> Para comparar contenidos sin que pese la forma de cada cámara, compara dentro de una misma cámara: la biblioteca
> frente al resto de sus debates de esos meses, o un periodo frente a otro. `distinctive_words` acepta los dos
> contrastes: `field="period"`, o `field="library"`, que compara la biblioteca con el resto del discurso de sus mismas
> cámaras.

## 5. Quién habló de la pandemia

> **Pide:** «En la biblioteca, ¿hablaron las diputadas en proporción a su peso en cada cámara? Compáralo con todo lo
> que se dijo en el pleno en esos mismos meses, sin la presidencia.»
>
> *El agente usa* `share_of_voice` dos veces: con `library="pandemia"` y con `date_from="2020-02-10"`,
> `date_to="2020-07-09"`, `exclude_chair=true`; en las dos, `by="sex"`, `per="all"`, `max_turn_words=10000`.

<!-- viz:pan_voz -->
<!-- table:pan_voz -->
| País | Intervenciones | Diputadas que hablan | Peso en el registro | Voz en la pandemia | Razón (pandemia) | Razón (todo) |  |
|---|---:|---:|---:|---:|---:|---:|---|
| Brasil | 1.481 | 49 | 11,9 % | 23,6 % | 1,99 | 1,90 |  |
| México | 48 | 25 | 47,9 % | 87,6 % | 1,83 | 1,50 | fuera del gráfico |
| Colombia | 428 | 20 | 16,9 % | 21,2 % | 1,25 | 0,91 |  |
| Panamá | 273 | 16 | 30,9 % | 34,7 % | 1,12 | 0,99 |  |
| Argentina | 117 | 33 | 39,6 % | 42,7 % | 1,08 | 1,05 |  |
| Costa Rica | 183 | 24 | 41,4 % | 42,2 % | 1,02 | 0,79 |  |
| Chile | 488 | 30 | 22,6 % | 22,5 % | 1,00 | 1,00 |  |
| Portugal | 426 | 55 | 47,5 % | 44,7 % | 0,94 | 0,87 |  |
| Perú | 323 | 29 | 27,2 % | 25,3 % | 0,93 | 0,95 |  |
| España | 374 | 52 | 43,6 % | 34,0 % | 0,78 | 0,79 |  |
| Ecuador | 324 | 40 | 42,4 % | 32,2 % | 0,76 | 0,72 |  |
| El Salvador | 618 | 21 | 40,4 % | 26,7 % | 0,66 | 0,58 |  |
| Guatemala | 206 | 17 | 19,3 % | 10,6 % | 0,55 | 0,70 |  |
| Uruguay | 93 | 7 | 34,0 % | 14,8 % | 0,44 | 0,63 | fuera del gráfico |
| Rep. Dominicana | 15 | 1 | 28,3 % | 6,6 % | 0,23 | 0,30 | fuera del gráfico |
<!-- /table -->

La línea de base cambia la lectura. Las diputadas brasileñas dicen en los debates de la pandemia el 23,6 % de las
palabras con un peso del 11,9 % en el registro, una razón de 1,99; pero en todo el discurso de esos meses ya estaban en 1,90: no
es un efecto de la pandemia. Donde sí cambia es en Colombia (1,25 frente a 0,91) y Costa Rica (1,02 frente a 0,79),
donde ellas hablaron del virus más de lo que hablaban en general, y en Guatemala, donde lo hicieron menos (0,55 frente
a 0,70). En España (0,78 y 0,79) y Chile (1,00 y 1,00) no hay diferencia.

> [!WARNING]
> Tres cámaras quedan fuera del gráfico. En la República Dominicana habla una sola diputada; en Uruguay, siete; México
> tiene 48 intervenciones en la biblioteca. Una razón calculada sobre tan pocas personas cambia con una intervención
> más: está en la tabla, con su número, y no debe compararse con las demás.

## 6. Lo que el estudio permite decir

**Lo que dicen los datos.** Diez parlamentos nombran el virus antes de la declaración; los que lo hacen tarde son los
que no se reunían. La atención semanal va del 19,3 % de las intervenciones en España al 2,8 % en Brasil. Lo que separa
los debates de cada cámara es sobre todo su forma de hablar y su lengua; el contenido propio aparece cuando se
compara con cuidado, como el oxígeno en Perú. La voz de las diputadas en la pandemia sube en Colombia y Costa Rica y
baja en Guatemala respecto de su propia línea de base.

**Lo que no dicen.** El primer uso no mide la preocupación de nadie: depende del calendario de sesiones y de lo que se
transcribe. La biblioteca recoge intervenciones que nombran la enfermedad al menos dos veces, no todos los debates
sobre sus consecuencias (la economía, la educación, las elecciones aplazadas).

**Las comprobaciones de este estudio.** Leer los primeros usos antes de fecharlos; mirar si la cámara se reunía;
proporciones, no recuentos, para comparar cámaras de tamaños distintos; describir la biblioteca antes de compararla;
dejar fuera los turnos largos donde pesan; y una línea de base del mismo periodo antes de decir que algo cambió.

> **Pídelo de una vez:** «Estudia cómo reaccionaron los 16 parlamentos a la pandemia de COVID-19: el primer uso de
> *coronavirus* o *covid* en cada uno, leído para descartar falsos positivos; cuándo dejó de reunirse cada pleno; la
> parte de las intervenciones que nombra la enfermedad, semana a semana, de enero a septiembre de 2020; una biblioteca
> con las intervenciones que la nombran al menos dos veces entre 30 días antes y 120 después del 11 de marzo, descrita
> antes de compararla; las palabras que distinguen a España, a Perú y a Portugal frente a Brasil; y la voz de las
> diputadas en esos debates frente a todo el discurso de los mismos meses. Deja fuera los turnos de más de 10.000
> palabras y no cites nombres de personas.»
