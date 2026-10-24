# Quién habla y cuánto pesa

<!-- eyebrow: Estudio 3 · Representación -->

*[English version](../en/voz.md) · [Índice del tutorial](../TUTORIAL.md)*

¿Habla cada grupo en proporción a su peso en la cámara? `share_of_voice` responde con una razón: la parte de las
palabras (o de los turnos) que dice un grupo, dividida por su parte en el registro de diputados del periodo. Una
razón de 1 quiere decir que habla lo que pesa; por encima, más. Este estudio la calcula para las diputadas de los
dieciséis parlamentos desde 2010 y recorre las cuatro trampas que pueden darle la vuelta: una Mesa que habla desde el
escaño, la unidad de medida, la lengua y las etiquetas del registro.

<!-- side -->

**La cadena de este estudio**

1. `share_of_voice`: voz y peso, año a año
2. `share_of_voice`: desde 2021, en palabras y en turnos
3. `query_sql`: la forma de los turnos de cada cámara
4. `share_of_voice`: México, por legislatura
5. `distinctive_words`: qué dicen diputadas y diputados
6. `query_sql`: México sin quienes hablan como la Mesa
7. `distinctive_words`: España y sus lenguas
8. `share_of_voice`: España, por partido

## 1. Voz y peso, año a año

> **Pide:** «Desde 2010, año a año y en cada parlamento, ¿qué parte de las palabras dicen las diputadas y qué parte
> del registro son? Sin la presidencia de la sesión y sin los turnos de más de 10.000 palabras.»
>
> *El agente usa* `share_of_voice` (`by="sex"`, `per="year"`, `date_from="2010-01-01"`, `exclude_chair=true`,
> `max_turn_words=10000`).

<!-- viz:voz_anual -->
<!-- table:voz_anual -->
| País (voz / registro, %) | 2010 | 2013 | 2016 | 2019 | 2022 | 2025 |
|---|---:|---:|---:|---:|---:|---:|
| Argentina | 35 / 38 | 32 / 36 | 33 / 37 | 35 / 39 | 41 / 43 | 36 / 44 |
| Brasil | 8 / 8 | 10 / 9 | 12 / 9 | 16 / 11 | 24 / 12 | 20 / 14 |
| Chile | 12 / 14 | 14 / 14 | 17 / 16 | 20 / 23 | 29 / 29 | 31 / 35 |
| Colombia | 10 / 12 | 16 / 14 | 17 / 19 | 13 / 17 | 26 / 23 | 23 / 29 |
| Costa Rica | 23 / 38 | 28 / 37 | 21 / 35 | 36 / 41 | 43 / 45 | 51 / 48 |
| Rep. Dominicana | 11 / 21 | 20 / 22 | 20 / 26 | 22 / 28 | 11 / 25 | 19 / 36 |
| Ecuador | 27 / 40 | 30 / 44 | 35 / 46 | 36 / 43 | 44 / 42 | 40 / 43 |
| España | 25 / 37 | 31 / 40 | 24 / 40 | 36 / 45 | 39 / 42 | 40 / 44 |
| Guatemala | 11 / 13 | 4 / 14 | 3 / 17 | 6 / 17 | 18 / 19 | 17 / 20 |
| México | 48 / 33 | 41 / 42 | 57 / 43 | 68 / 48 | 63 / 49 | 46 / 49 |
| Panamá | 11 / 16 | 9 / 16 | 29 / 15 | 30 / 23 | 25 / 31 | 21 / 34 |
| Perú | 25 / 28 | 23 / 21 | 25 / 25 | 35 / 28 | 38 / 38 | 36 / 39 |
| Portugal | 28 / 33 | 28 / 34 | 35 / 42 | 39 / 46 | 34 / 47 | 36 / 47 |
| Paraguay | 11 / 11 | 18 / 11 | 22 / 13 | 26 / 14 | 29 / 14 | 26 / 8 |
| El Salvador | — | — | — | 22 / 40 | 39 / 40 | 45 / 41 |
| Uruguay | 10 / 19 | 9 / 17 | 18 / 32 | 17 / 30 | 30 / 35 | 24 / 36 |
<!-- /table -->

En la mayoría de las cámaras la voz de las diputadas va por debajo de su peso y se le acerca con los años: en España
pasa del 25 % de las palabras con el 37 % del registro en 2010 al 40 % con el 44 % en 2025; en Costa Rica, del 23 % con
el 38 % al 51 % con el 48 %. Brasil va por encima desde 2013 (en 2022, el 24 % de las palabras con el 12 % del
registro). México está muy por encima desde 2016, y la sección 3 explica por qué.

> [!WARNING]
> Dos puntos del gráfico son del registro, no del debate. En Paraguay, el registro de 2025 da a las diputadas el 8 %
> del peso (cuatro diputadas) cuando los años anteriores daba entre el 14 y el 19 %: la voz parece triplicar el peso
> porque el registro de ese año está incompleto. En Guatemala, 2024 da a las diputadas el 47 % de las palabras frente
> al 14 % y el 17 % de los años vecinos, con 49 diputadas en el registro en lugar de 32. Antes de leer un salto,
> mira `members_on_register` y `speakers` en el resultado, y lee la documentación del país con `get_documentation`.

## 2. Desde 2021: palabras y turnos

> **Pide:** «Desde 2021, todo junto, compara el peso de las diputadas con su parte de las palabras y con su parte de
> los turnos.»
>
> *El agente usa* `share_of_voice` dos veces (`by="sex"`, `per="all"`, `date_from="2021-01-01"`,
> `exclude_chair=true`, `max_turn_words=10000`), la segunda con `unit="turns"`.

<!-- viz:voz_reciente -->
<!-- table:voz_reciente -->
| País | Peso en el registro | Parte de las palabras | Razón | Parte de los turnos | Diputadas que hablan | Discurso vinculado |
|---|---:|---:|---:|---:|---:|---:|
| Paraguay | 15,1 % | 27,6 % | 1,83 | 25,8 % | 27 | 88 % |
| Brasil | 14,9 % | 21,9 % | 1,47 | 23,1 % | 153 | 95 % |
| Guatemala | 18,6 % | 25,0 % | 1,35 | 28,9 % | 48 | 97 % |
| México | 48,1 % | 60,0 % | 1,25 | 61,4 % | 723 | 97 % |
| Ecuador | 40,2 % | 43,9 % | 1,09 | 42,5 % | 174 | 60 % |
| Perú | 32,6 % | 33,9 % | 1,04 | 35,2 % | 88 | 79 % |
| Costa Rica | 44,8 % | 45,6 % | 1,02 | 44,0 % | 52 | 98 % |
| Colombia | 23,5 % | 23,6 % | 1,00 | 20,4 % | 77 | 67 % |
| Chile | 29,0 % | 29,1 % | 1,00 | 27,6 % | 73 | 88 % |
| El Salvador | 41,2 % | 38,9 % | 0,94 | 22,7 % | 82 | 99 % |
| Argentina | 41,6 % | 37,8 % | 0,91 | 38,1 % | 198 | 95 % |
| España | 44,3 % | 38,9 % | 0,88 | 38,9 % | 271 | 96 % |
| Portugal | 46,7 % | 36,9 % | 0,79 | 26,2 % | 218 | 88 % |
| Uruguay | 36,9 % | 27,2 % | 0,74 | 25,1 % | 161 | 94 % |
| Panamá | 32,8 % | 23,2 % | 0,71 | 22,9 % | 61 | 60 % |
| Rep. Dominicana | 32,4 % | 12,2 % | 0,38 | 11,3 % | 94 | 99 % |
<!-- /table -->

La razón va de 0,38 en la República Dominicana, donde las diputadas son el 32,4 % del registro y dicen el 12,2 % de las
palabras, a 1,47 en Brasil (Paraguay, con 1,83, arrastra el registro incompleto de 2025). Seis cámaras están cerca de 1:
Ecuador, Perú, Costa Rica, Colombia, Chile y El Salvador.

La unidad importa. En El Salvador las diputadas dicen el 38,9 % de las palabras, pero toman solo el 22,7 % de los
turnos; en Portugal, el 36,9 % y el 26,2 %. Hablan menos veces y más rato. Que la medida cambie tanto depende de cómo
se reparte la palabra en cada cámara.

> **Pide:** «¿Cuántas palabras tiene una intervención típica de un diputado en cada parlamento, desde 2021? Dame la
> mediana y el percentil 90.»
>
> *El agente usa* `query_sql`:

```sql
SELECT country, count(*) AS interventions,
       CAST(median(n_words) AS INT) AS median_words,
       CAST(quantile_cont(n_words, 0.9) AS INT) AS p90_words
FROM interventions
WHERE dm_speech = 1 AND date >= DATE '2021-01-01' AND id_dep IS NOT NULL AND id_dep <> ''
GROUP BY 1 ORDER BY median_words DESC
```

<!-- table:voz_turnos -->
| País | Intervenciones de diputados desde 2021 | Mediana de palabras | Percentil 90 |
|---|---:|---:|---:|
| El Salvador | 23.494 | 146 | 913 |
| Costa Rica | 47.277 | 84 | 739 |
| Rep. Dominicana | 19.059 | 64 | 432 |
| Chile | 92.920 | 41 | 456 |
| España | 62.554 | 39 | 922 |
| Brasil | 248.945 | 25 | 366 |
| México | 142.001 | 22 | 454 |
| Guatemala | 31.313 | 21 | 343 |
| Perú | 158.727 | 19 | 257 |
| Paraguay | 36.955 | 19 | 394 |
| Argentina | 36.190 | 18 | 527 |
| Colombia | 99.870 | 18 | 268 |
| Panamá | 45.866 | 18 | 309 |
| Portugal | 156.878 | 18 | 222 |
| Uruguay | 40.823 | 18 | 744 |
| Ecuador | 38.626 | 16 | 733 |
<!-- /table -->

Las cámaras se parecen poco. En El Salvador, la intervención mediana tiene 146 palabras; en Costa Rica, 84. En
Portugal, Colombia, Panamá, Argentina o Uruguay, 18, y en Ecuador 16: allí abundan los turnos breves, como preguntas,
réplicas o peticiones de palabra. Contar turnos mide cuántas veces se toma la palabra; contar palabras, cuánto
se dice. Elige la unidad según la pregunta y dila al presentar el resultado.

## 3. México: la Mesa habla desde el escaño

> **Pide:** «En México, por legislatura desde 2012, ¿qué parte de las palabras dicen las diputadas?»
>
> *El agente usa* `share_of_voice` (`countries=["MX"]`, `by="sex"`, `per="legislature"`, `date_from="2012-09-01"`,
> `exclude_chair=true`, `max_turn_words=10000`).

En la LXIV legislatura (2018–2021), las diputadas dicen el 66,7 % de las palabras con el 45,2 % del registro, una razón
de 1,47. ¿Qué dicen?

> **Pide:** «En esa legislatura, ¿qué palabras distinguen a las diputadas de los diputados?»
>
> *El agente usa* `distinctive_words` (`field="sex"`, `a="F"`, `b="M"`, `countries=["MX"]`,
> `date_from="2018-09-01"`, `date_to="2021-08-31"`, `exclude_chair=true`, `max_turn_words=10000`).

<!-- viz:voz_mx_palabras -->
<!-- table:voz_mx_palabras -->
|  | Diputadas | z | Diputados | z |
|---:|---|---:|---|---:|
| 1 | diputada | 77,4 | que | 73,6 |
| 2 | del | 75,6 | no | 72,5 |
| 3 | votación | 66,1 | es | 70,4 |
| 4 | grupo | 62,9 | un | 49,2 |
| 5 | parlamentario | 62,1 | pero | 46,7 |
| 6 | diputado | 60,0 | una | 46,0 |
| 7 | de | 56,2 | porque | 44,1 |
| 8 | partido | 53,9 | esta | 43,7 |
| 9 | diputados | 53,9 | yo | 43,2 |
| 10 | mujeres | 52,1 | más | 41,3 |
| 11 | general | 48,9 | eso | 41,2 |
| 12 | manifestarlo | 44,9 | país | 40,8 |
| 13 | sírvanse | 44,4 | hay | 40,1 |
| 14 | estén | 43,0 | pueblo | 39,6 |
| 15 | cargo | 42,8 | aquí | 37,3 |
<!-- /table -->

La lista de las diputadas no es un debate: *votación*, *sírvanse*, *manifestarlo*, *estén*, *diputada*, *diputado*,
*grupo parlamentario*. Es la fórmula «las diputadas y los diputados que estén por la afirmativa, sírvanse
manifestarlo», y el anuncio de quién tiene la palabra. La leen las secretarias de la Mesa Directiva, que son diputadas
y hablan desde su escaño. `exclude_chair` quita los turnos de quien preside, pero no los de la Mesa. La de los diputados
sí es un debate: *que*, *no*, *pero*, *porque*, *país*, *pueblo*.

> **Pide:** «Repite la comparación por legislatura sin los diputados y diputadas que hablan como la Mesa: los que
> tienen más de mil turnos en la legislatura.»
>
> *El agente usa* `query_sql`:

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
| Legislatura | Peso de las diputadas | Sus palabras | Razón | Diputadas / diputados con más de 1.000 turnos | Sus palabras sin ellos | Razón sin ellos |
|---|---:|---:|---:|---|---:|---:|
| LXII | 42,2 % | 41,5 % | 0,98 | 3 / 10 | 54,5 % | 1,29 |
| LXIII | 42,5 % | 57,7 % | 1,36 | 8 / 4 | 48,2 % | 1,14 |
| LXIV | 45,2 % | 66,7 % | 1,47 | 8 / 3 | 57,6 % | 1,27 |
| LXV | 48,2 % | 63,9 % | 1,33 | 7 / 3 | 62,2 % | 1,29 |
| LXVI | 48,6 % | 46,7 % | 0,96 | 2 / 2 | 50,8 % | 1,05 |
<!-- /table -->

Sin los once oradores con más de mil turnos (ocho diputadas y tres diputados), las diputadas de la LXIV dicen el
57,6 % de las palabras: siguen por encima de su peso (1,27), pero lejos del 66,7 %. La corrección no siempre va en la
misma dirección: en la LXII los oradores de la Mesa eran sobre todo diputados (diez frente a tres), y al quitarlos la
parte de las diputadas sube del 41,5 % al 54,5 %.

> [!IMPORTANT]
> El corte de mil turnos es una regla ad hoc para mostrar el efecto, no una definición de la Mesa. Para un trabajo
> publicado, identifica a sus integrantes por legislatura (en la documentación del país o leyendo las sesiones con
> `get_session`) y quítalos por su `id_dep`. Y recuerda que la consulta SQL no aplica `exclude_chair`: sus cifras se
> comparan entre sí, no con las de `share_of_voice`.

## 4. España y sus lenguas

> **Pide:** «En el Congreso español, desde diciembre de 2019, ¿qué palabras distinguen a diputadas y diputados?»
>
> *El agente usa* `distinctive_words` (`field="sex"`, `a="F"`, `b="M"`, `countries=["ES"]`,
> `date_from="2019-12-03"`, `exclude_chair=true`).

<!-- viz:voz_es_palabras -->
<!-- table:voz_es_palabras -->
|  | Diputadas | z | Diputados | z |
|---:|---|---:|---|---:|
| 1 | mujeres | 63,1 | españa | 29,4 |
| 2 | violencia | 36,5 | do | 28,2 |
| 3 | las | 35,9 | señor | 28,1 |
| 4 | per | 35,3 | non | 24,7 |
| 5 | els | 34,5 | caso | 24,7 |
| 6 | personas | 32,1 | bng | 24,2 |
| 7 | sexual | 30,4 | del | 22,8 |
| 8 | nosotras | 29,6 | creo | 22,7 |
| 9 | igualdad | 29,2 | muchas | 21,2 |
| 10 | les | 28,4 | as | 21,1 |
| 11 | mujer | 26,1 | unión | 20,9 |
| 12 | perquè | 26,1 | señora | 20,6 |
| 13 | derechos | 25,4 | máis | 20,4 |
| 14 | amb | 25,3 | en | 20,3 |
| 15 | ciudadanía | 24,9 | evidentemente | 20,3 |
<!-- /table -->

Del lado de las diputadas hay un tema (*mujeres*, *violencia*, *sexual*, *igualdad*, *nosotras*, *derechos*) y una
lengua: *per*, *els*, *les*, *perquè*, *amb* son catalán. Del lado de los diputados, *España* y *señor*, y otra lengua:
*do*, *non*, *as*, *máis* son gallego, junto a *BNG*, el partido de su único diputado. Desde la reforma del Reglamento
de septiembre de 2023 se puede hablar en el pleno en catalán, gallego y euskera.

> **Pide:** «¿Cuántas intervenciones del Congreso tienen *perquè* (catalán) o *máis* (gallego), año a año desde 2019?»
>
> *El agente usa* `query_sql`:

```sql
SELECT year(date) AS year, count(*) AS interventions
FROM interventions
WHERE country = 'ES' AND dm_speech = 1 AND date >= DATE '2019-01-01'
  AND regexp_matches(lower(text), '\b(perquè|máis)\b')
GROUP BY 1 ORDER BY 1
```

<!-- table:voz_es_lenguas -->
| Año | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Intervenciones con «perquè» o «máis» | 1 | 6 | 8 | 7 | 32 | 140 | 106 |
<!-- /table -->

Hasta 2022 no pasan de ocho al año; en 2024 son 140. Una lista de palabras por sexo mide aquí, en parte, quién habla
en qué lengua.

> [!TIP]
> Para separar el tema de la lengua, repite la comparación hasta agosto de 2023 (`date_to="2023-08-31"`), o compara
> dentro de cada lengua. Las listas de `distinctive_words` comparan lenguas tanto como contenidos cada vez que los
> dos grupos no hablan la misma.

## 5. España, por partido: etiquetas y fronteras

> **Pide:** «En la legislatura que empezó en agosto de 2023, ¿cuánto habla cada partido frente a su peso?»
>
> *El agente usa* `share_of_voice` (`countries=["ES"]`, `by="party"`, `per="all"`, `date_from="2023-08-18"`,
> `exclude_chair=true`).

<!-- table:voz_es_partidos -->
| Etiqueta en el registro | Diputados que hablan | En el registro | Peso en el registro | Parte de las palabras | Razón |
|---|---:|---:|---:|---:|---:|
| PSOE | 100 | 108 | 26,8 % | 17,0 % | 0,63 |
| PP | 139 | 148 | 36,7 % | 15,6 % | 0,42 |
| SUMAR | 35 | 35 | 8,7 % | 14,4 % | 1,66 |
| VOX | 33 | 34 | 8,4 % | 11,7 % | 1,38 |
| ERC | 8 | 8 | 2,0 % | 11,6 % | 5,82 |
| JxCAT-JUNTS | 8 | 8 | 2,0 % | 9,8 % | 4,96 |
| EAJ-PNV | 6 | 6 | 1,5 % | 5,7 % | 3,82 |
| EH Bildu | 7 | 7 | 1,7 % | 4,9 % | 2,83 |
| BNG | 1 | 1 | 0,2 % | 4,3 % | 17,32 |
| UPN | 1 | 1 | 0,2 % | 1,1 % | 4,55 |
| PSC-PSOE | 20 | 23 | 5,7 % | 1,1 % | 0,19 |
| PSE-EE (PSOE) | 6 | 6 | 1,5 % | 1,1 % | 0,72 |
| CCa | 1 | 1 | 0,2 % | 1,0 % | 4,11 |
| PsdeG-PSOE | 10 | 11 | 2,7 % | 0,4 % | 0,17 |
| PSIB-PSOE | 2 | 3 | 0,7 % | 0,2 % | 0,29 |
| PSN-PSOE | 3 | 3 | 0,7 % | 0,1 % | 0,15 |
| **PSOE con sus federaciones** | 141 | 154 | 38,2 % | 19,9 % | 0,52 |
<!-- /table -->

El registro etiqueta por partido, no por grupo parlamentario: el grupo socialista aparece partido en el PSOE y cinco
federaciones (PSC, PSdeG, PSE-EE, PSIB y PSN). Sumadas, son el 38,2 % del registro y dicen el 19,9 % de las palabras,
una razón de 0,52; el PP, 0,42. Los grupos pequeños hablan mucho más que su peso, porque en muchos debates el tiempo se
reparte por grupo y no por escaño: Sumar 1,66, Vox 1,38, ERC 5,82. Las razones de un solo diputado (BNG, UPN, CCa)
pueden pasar de 4 o de 17 y no dicen nada sobre un grupo: son una persona.

> [!WARNING]
> El periodo empieza el 18 de agosto, el día después de la sesión constitutiva. El 17 el registro tiene a la vez a los
> 350 diputados nuevos y a 135 de la legislatura anterior, cuyo mandato termina ese día; si el periodo incluye ese
> día, los que repiten se cuentan con la etiqueta de su fila antigua, y Vox pasa de 34 miembros a 20. Cuando un periodo
> cruza un cambio de legislatura, empieza al día siguiente o mira `members_on_register` antes de leer la razón.

## 6. Lo que el estudio permite decir

**Lo que dicen los datos.** Desde 2021, las diputadas hablan en proporción a su peso en seis parlamentos, por debajo
en la República Dominicana, Panamá, Uruguay y Portugal, y por encima en Brasil y, con las cautelas del registro, en
Guatemala y Paraguay. Las cifras de
México, España y Paraguay cambian cuando se mira cómo se producen: una Mesa que lee votaciones, dos lenguas nuevas en
el pleno y un registro incompleto.

**Lo que no dicen.** La razón no mide influencia ni calidad: una diputada que lee el resultado de una votación suma
palabras. Tampoco explica por qué un grupo habla menos (el reparto del tiempo, las comisiones, los cargos). Y pesa a
los grupos con el registro, que cuenta a todos los que pasan por el escaño en el periodo, incluidas las sustituciones.

**Las comprobaciones de este estudio.** Sin presidencia y sin turnos largos; palabras y turnos, por separado;
leer las palabras de un grupo antes de interpretar su voz; mirar quién concentra los turnos; separar lengua y tema;
juntar las etiquetas que son un mismo grupo; no leer razones de grupos de una persona; y comprobar el registro en los
saltos y en las fronteras de legislatura.

> **Pídelo de una vez:** «Estudia si las diputadas hablan en proporción a su peso en los 16 parlamentos: año a año
> desde 2010 y, desde 2021, en palabras y en turnos, sin la presidencia y sin los turnos de más de 10.000 palabras.
> Compara la longitud de los turnos de cada cámara. En México, por legislatura, mira qué palabras distinguen a
> diputadas y diputados y repite la cuenta sin quienes hablan como la Mesa. En España, mira si la lengua pesa en las
> palabras de cada sexo y calcula la voz por partido desde el 18 de agosto de 2023, juntando las federaciones del PSOE.
> Señala los años en que el registro parece incompleto.»
