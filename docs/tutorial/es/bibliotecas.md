# Una biblioteca desde cero

<!-- eyebrow: Guía · Paso a paso -->

*[English version](../en/bibliotecas.md) · [Índice del tutorial](../TUTORIAL.md)*

Los estudios del tutorial muestran lo que se puede hacer con una biblioteca. Esta guía enseña a hacerla: cómo se pasa
de una pregunta a una definición, cómo se prueba, qué se hace cuando falla y cómo se usa y se mantiene después. Una
biblioteca es un conjunto de intervenciones con nombre, guardado en tu ordenador, que delimita un estudio: un tema, un
periodo, un grupo de oradores, o las tres cosas, en uno o en varios países. Después, cada herramienta de análisis
trabaja dentro de ella con `library=`. La pregunta de ejemplo es real: cómo debatieron los plenos de Colombia, Perú,
Ecuador y Chile la llegada de migrantes venezolanos desde 2015. Para responderla hacen falta dos definiciones, porque
la primera falla en una de las cuatro cámaras.

<!-- side -->

**La cadena de esta guía**

1. `term_counter`: probar las palabras
2. `kwic`: leer lo que sorprende
3. `library_create`: una primera definición y su umbral
4. `library_combine`: cruzar dos bibliotecas
5. `library_describe`: qué hay antes de comparar
6. `kwic`: leer una muestra en cada cámara
7. `library_create`: una segunda definición, más estrecha
8. `library_edit`: quitar lo que no es debate y anotar
9. `query_sql` y `distinctive_words`: usar la biblioteca
10. `library_combine`, `query_sql` y `kwic`: leer lo que queda fuera
11. `library_rebuild`, `library_export` y `library_delete`: mantenerla

## 1. ¿Biblioteca o filtros?

Todas las herramientas de análisis aceptan filtros: países, fechas, partido, sexo, sin la presidencia, sin los turnos
largos. Para contar una palabra o dibujar su curva no hace falta una biblioteca. Hace falta cuando el objeto del
estudio no es una palabra, sino un conjunto que hay que definir y al que se vuelve muchas veces.

| Si quieres… | Basta con los filtros | Mejor una biblioteca |
|---|:---:|:---:|
| contar una palabra o ver su curva | ✓ |  |
| comparar grupos en todo el discurso de unos años | ✓ |  |
| estudiar un tema que se dice con varias palabras, y que no basta con nombrar una vez |  | ✓ |
| leer, contar, comparar y dibujar redes sobre el mismo conjunto |  | ✓ |
| quitar a mano lo que no sirve, o anotar intervenciones |  | ✓ |
| dar a cada país su propia definición o su propia fecha |  | ✓ |
| abrir el conjunto en el Diarios Explorer o pasárselo a otra persona |  | ✓ |

Una biblioteca se enfoca de tres maneras, que se combinan:

- **Un tema**: `terms`, con `min_occurrences` para quedarse con las intervenciones que lo tratan y no con las que lo
  nombran, o `regex=true` para una expresión regular.
- **Un periodo**: `date_from` y `date_to`, o una fecha distinta en cada país con `event_dates`, `days_before` y
  `days_after`, como en la [biblioteca de la pandemia](pandemia.md#3-una-biblioteca-alrededor-del-11-de-marzo).
- **Un grupo**: `party`, `sex` o `id_dep`, para los discursos de un partido, de las diputadas o de una persona.

Un tema dentro de un periodo, en un solo país, es la [biblioteca de las dos reformas de las pensiones en
Brasil](marcos.md#1-la-biblioteca-de-las-dos-reformas). Esta guía hace una en cuatro países y se detiene en la
definición, porque el tema se dice con palabras corrientes que significan cosas distintas en cada cámara.

## 2. De la pregunta a la definición

Antes de abrir una herramienta conviene escribir la pregunta y desmontarla. Cada parte se convierte en un parámetro, y
lo que no se decide aquí lo decide el agente por ti.

| Pregunta | En esta guía | Parámetro |
|---|---|---|
| ¿De qué? | la llegada de migrantes venezolanos: no la migración en general, ni la política de Venezuela | `terms`, `regex`, `min_occurrences` |
| ¿Dónde? | Colombia, Perú, Ecuador y Chile, cuatro países de destino de la emigración venezolana | `countries` |
| ¿Cuándo? | desde 2015, para que la serie empiece antes de las grandes llegadas | `date_from` |
| ¿Quién? | todo el pleno, salvo quien preside la sesión | `exclude_chair` |
| ¿Para qué? | contar año a año en cada cámara y comparar de qué habla cada una | cuánta precisión hace falta |

La última fila importa más de lo que parece. Para una tendencia, la definición tiene que medir lo mismo en las cuatro
cámaras y en todos los años. Para comparar vocabularios, el conjunto tiene que estar limpio: unas pocas
intervenciones sobre otra cosa bastan para que sus palabras suban a la lista. Por eso una definición no se juzga por
cuántas intervenciones trae, sino por cuántas de las que trae responden a la pregunta.

## 3. Probar las palabras

> **Pide:** «¿Cuántas veces se dicen *migrante*, *migración*, *migratorio*, *inmigrante*, *refugiado*, *desplazado*
> y *venezolano* o *Venezuela* en los plenos de Colombia, Perú, Ecuador y Chile desde 2015?»
>
> *El agente usa* `term_counter` (`terms="migrante*, migraci*, migratori*, inmigra*, refugiad*, desplazad*, venezolan*+venezuela"`,
> `countries=["CO", "PE", "EC", "CL"]`, `date_from="2015-01-01"`). Las comas separan términos que se cuentan aparte;
> el signo `+` suma variantes en un solo término.

<!-- table:bib_terminos -->
| Término | Chile | Colombia | Ecuador | Perú | Intervenciones (las cuatro) |
|---|---:|---:|---:|---:|---:|
| `migrante*` | 1.500 | 415 | 5.269 | 450 | 2.434 |
| `migraci*` | 1.850 | 455 | 1.399 | 1.129 | 2.490 |
| `migratori*` | 1.379 | 293 | 2.341 | 601 | 1.769 |
| `inmigra*` | 1.149 | 36 | 288 | 72 | 841 |
| `refugiad*` | 187 | 103 | 685 | 103 | 416 |
| `desplazad*` | 114 | 617 | 202 | 122 | 842 |
| `venezolan* + venezuela` | 1.495 | 3.108 | 2.226 | 1.737 | 3.418 |
<!-- /table -->

Tres cifras piden una lectura antes de definir nada.

> **Pide:** «Enséñame doce usos al azar de *desplazado* en Colombia, dieciséis de *venezolano* en los cuatro países y
> doce de *migrante* en Ecuador.»
>
> *El agente usa* `kwic` (`pattern="desplazad*"`, `countries=["CO"]`, `n=12`), y lo mismo con los otros dos.

- **Desplazado** se dice más en Colombia que en los otros tres países juntos. Las doce intervenciones leídas (de 488)
  hablan del desplazamiento interno por el conflicto armado. Es otro tema: queda fuera.
- **Venezolano**, solo, no basta. De las dieciséis intervenciones leídas (de 1.434), seis hablan de migrantes; las
  demás, de la política venezolana, de incursiones militares en la frontera, de la economía o de una banda criminal.
  Hace falta una palabra de migración al lado.
- **Migrante** se dice en Ecuador 5.269 veces, tres veces y media más que en Chile. Las doce intervenciones leídas (de
  1.241) hablan de ecuatorianos en el extranjero (remesas, consulados, retornados, los asambleístas elegidos por los
  emigrantes) o de la trata de personas. En Ecuador, *migrante* es ante todo el ecuatoriano que se fue.

> [!TIP]
> Un término no cuenta lo mismo en cada cámara. Antes de meterlo en una definición, lee una muestra al azar en cada
> país donde su cifra sorprenda: doce o veinte líneas bastan para ver si habla de lo que buscas.

## 4. Primera definición: un umbral y un cruce

La primera biblioteca recoge el tema migratorio. El parámetro `min_occurrences` dice cuántas veces tienen que aparecer
los términos en una intervención: con 1 entra cualquiera que los nombre; con 2 o 3, las que hablan de ello. El umbral
no se adivina: se prueba.

> **Pide:** «Crea tres bibliotecas de migración en los cuatro países desde 2015, sin la presidencia: con al menos una,
> dos y tres menciones de *migrante*, *migración*, *migratorio*, *inmigrante* o *refugiado*.»
>
> *El agente usa* `library_create` tres veces (`terms="migrante*, migraci*, migratori*, inmigra*, refugiad*"`,
> `min_occurrences` 1, 2 y 3, `date_from="2015-01-01"`, `exclude_chair=true`, `label="migración"`).

<!-- table:bib_umbral -->
| Menciones por intervención | Chile | Colombia | Ecuador | Perú | Total |
|---|---:|---:|---:|---:|---:|
| 1 o más | 1.841 | 595 | 1.918 | 895 | 5.249 |
| 2 o más | 943 | 224 | 984 | 352 | 2.503 |
| 3 o más | 655 | 117 | 680 | 203 | 1.655 |
<!-- /table -->

Pasar de una mención a dos deja la biblioteca en menos de la mitad. Para saber qué se pierde, se lee lo que queda entre
los dos umbrales: una biblioteca hecha con la diferencia de las otras dos.

> **Pide:** «Haz una biblioteca con las intervenciones que nombran la migración una sola vez (las de la primera que no
> están en la segunda) y enséñame veinte al azar.»
>
> *El agente usa* `library_combine` (`name="una_mencion"`, `a="migracion_1"`, `b="migracion"`, `op="difference"`) y
> después `kwic` con `library="una_mencion"`.

Son 2.746 intervenciones. De las veinte leídas, unas cuatro tratan la migración; las demás la nombran de paso: una
cláusula contra la discriminación que enumera la «condición migratoria», un tratado, una organización en una lista,
el título de una ley leído en el pleno, el nombre de una institución, la migración del campo a la ciudad, desplazados
llamados refugiados, la biografía de quien habla. Se queda el umbral de dos menciones: la biblioteca *migracion*.

Falta Venezuela. Una intervención entra en la biblioteca si usa cualquiera de los términos (es un «o»), y
`min_occurrences` cuenta las apariciones de todos juntos. Por eso «migración y Venezuela» no se pide en una sola
biblioteca: se hacen dos y se cruzan.

> **Pide:** «Haz otra biblioteca, *venezuela*, con las intervenciones que nombran *venezolano* o *Venezuela* en los
> mismos países y años, y crúzala con la de migración.»
>
> *El agente usa* `library_create` (`terms="venezolan*+venezuela"`, `exclude_chair=true`) y `library_combine`
> (`a="migracion"`, `b="venezuela"`, `op="intersection"`).

La biblioteca *venezuela* tiene 3.289 intervenciones; el cruce, *migracion_y_venezuela*, 468: 165 de Chile, 86 de
Colombia, 145 de Ecuador y 72 de Perú. Es la primera definición: dos menciones de migración o más, y Venezuela, en la
misma intervención.

> [!NOTE]
> Las bibliotecas de trabajo no cuestan nada: se crean para probar, se comparan y se borran (§ 10). Ponles nombres que
> digan lo que son (*migracion_1*, *una_mencion*) y una descripción; `library_describe` sin nombre las lista todas.

## 5. Describir y leer una muestra en cada cámara

> **Pide:** «Describe *migracion_y_venezuela* antes de usarla.»
>
> *El agente usa* `library_describe` (`name="migracion_y_venezuela"`).

La descripción avisa de dos cosas. En Ecuador, el 84,4 % de las palabras de la biblioteca está en turnos de más de
10.000 palabras, y en Perú el 30,9 %: documentos leídos en el pleno, que se miran en el § 7. Y hay años con menos de
cinco intervenciones (de 2015 a 2018 en Chile, cuatro años en Colombia y cinco en Perú) que no se pueden leer como tendencia. Lo que la
descripción no dice es si las intervenciones hablan de lo que buscas. Eso solo se sabe leyendo.

> **Pide:** «Enséñame veinte intervenciones al azar de la biblioteca en cada país, con la frase donde se nombra
> Venezuela, y cuenta cuántas hablan de migrantes venezolanos.»
>
> *El agente usa* `kwic` (`pattern="\b(venezolan|venezuela)"`, `regex=true`, `library="migracion_y_venezuela"`,
> `n=20`), un país cada vez. La muestra sale al azar con una semilla fija: la misma petición, sobre los mismos datos, da
> las mismas veinte.

En Chile, 16 de las 20 hablan de migrantes venezolanos; en Colombia, 17; en Perú, 18. En Ecuador, 6. Las otras catorce
de Ecuador hablan de ecuatorianos que viven en Venezuela, de emigrantes ecuatorianos con Venezuela nombrada en otro
punto de la intervención, de listas de países y de tratados, de la política venezolana, de un asilo diplomático (otro
sentido de *refugiado*) o de seguridad. La definición funciona en tres cámaras y falla en la cuarta, por la razón que
el § 3 dejaba ver: en Ecuador, el debate migratorio trata de los ecuatorianos, y en una intervención larga Venezuela
aparece por otros motivos.

> [!IMPORTANT]
> Lee la muestra de cada cámara por separado y apunta el recuento: «16 de 20» es un dato de método, que va en el
> artículo. Una muestra de los cuatro países juntos habría escondido el fallo de Ecuador entre los aciertos de los otros
> tres.

## 6. Segunda definición: en la misma frase

El fallo de Ecuador tiene una forma: la palabra de migración y Venezuela están en la misma intervención, pero no en la
misma frase. La segunda definición lo pide con una expresión regular.

> **Pide:** «Crea *migracion_venezolana* con las intervenciones donde una palabra de migración y *venezolano* aparecen
> en la misma frase, en los cuatro países desde 2015 y sin la presidencia.»
>
> *El agente usa* `library_create` (`regex=true`, `date_from="2015-01-01"`, `exclude_chair=true`,
> `label="migración venezolana"`), con esta expresión como término:

```text
(?i)\b(migrante|migraci|migratori|inmigra|refugiad)[^.;:?!]{0,200}\bvenezolan|\bvenezolan[^.;:?!]{0,200}\b(migrante|migraci|migratori|inmigra|refugiad)
```

Se lee así. `(?i)` hace que no distinga mayúsculas: una expresión regular se aplica al texto tal como está, con sus
mayúsculas y sus tildes, y por eso los prefijos se cortan antes de la tilde (*migraci* encuentra *migración* y
*migraciones*). `\b` marca el comienzo de una palabra. `[^.;:?!]{0,200}` admite hasta 200 caracteres sin punto, dos
puntos, punto y coma ni cierre de interrogación o de exclamación: más o menos, la misma frase. La barra `|` repite la
búsqueda en el otro orden. La definición cambia dos cosas a la vez: pide la misma frase, y solo el gentilicio,
*venezolano*, no el nombre del país, que es el que aparece en las listas y en la política exterior.

La prueba es la misma: veinte intervenciones al azar en cada cámara, con `kwic` y la misma expresión.

<!-- table:bib_definiciones -->
| País | Primera: intervenciones | Primera: de 20 leídas, sobre migrantes venezolanos | Segunda: intervenciones | Segunda: de 20 leídas, sobre migrantes venezolanos |
|---|---:|---:|---:|---:|
| Chile | 165 | 16 / 20 | 49 | 20 / 20 |
| Colombia | 86 | 17 / 20 | 106 | 20 / 20 |
| Ecuador | 145 | 6 / 20 | 53 | 19 / 20 |
| Perú | 72 | 18 / 20 | 59 | 20 / 20 |
| **Total** | 468 |  | 267 |  |
<!-- /table -->

La segunda definición es precisa en las cuatro cámaras, pero no es mejor en todo. En Ecuador pasa de 145 a 53
intervenciones y se lleva casi todo el ruido. En Chile pasa de 165 a 49, y lo que pierde era sobre todo del tema: si la
muestra vale para el resto, la primera reúne en Chile más de cien intervenciones sobre migrantes venezolanos, y la
segunda se queda con menos de la mitad (el § 9 lo mide), porque allí se nombra a los migrantes y a Venezuela en frases
distintas. En Colombia crece de 86 a 106, porque la segunda acepta una sola mención de migración si está junto a
*venezolano*.

Ninguna de las dos es la buena. La primera cubre más donde funciona; la segunda se puede leer sin ruido en las cuatro
cámaras. La guía sigue con la segunda y mira las dos juntas en el § 8: lo que digan las dos se puede afirmar; lo que
dependa de la definición, no.

> [!TIP]
> Lo que se aprende al leer una muestra es la definición siguiente. Apunta cada versión, su muestra y su recuento: la
> secuencia de definiciones es la justificación del método.

## 7. Corregir a mano y anotar

> **Pide:** «Describe *migracion_venezolana*. Si hay turnos de más de 10.000 palabras, dime quién los dice, cuándo y
> cuántas palabras tienen.»
>
> *El agente usa* `library_describe` y después `query_sql`:

```sql
SELECT i.country, i.date, i.n_words, i.speaker_raw
FROM lib.library_items li
JOIN lib.libraries l ON l.id = li.library_id
JOIN interventions i ON i.country = li.country AND i.id_int = li.id_int
WHERE l.name = 'migracion_venezolana' AND i.n_words > 10000
ORDER BY 1, 2
```

En Ecuador, el 87,6 % de las palabras de la nueva biblioteca está en turnos largos, y en Perú el 39,4 %. Son diez
intervenciones. Las ocho de Ecuador son informes leídos por la secretaría o la prosecretaría, de entre 17.895 y 224.643
palabras: documentos, no debate. Las dos de Perú son discursos del poder ejecutivo, la presentación del presidente del
Consejo de Ministros ante el pleno en mayo de 2020 (13.133 palabras) y el mensaje presidencial de julio de 2023
(10.090): son discurso, y se quedan.

> **Pide:** «Quita de la biblioteca las lecturas de la secretaría de más de 10.000 palabras, con una consulta que
> pueda repetir, y anota la proposición colombiana que crea la comisión accidental de seguimiento a la crisis
> migratoria.»
>
> *El agente usa* `library_edit` (`action="remove"`, `sql=…`) con esta consulta, y otra vez `library_edit`
> (`action="note"`, `id_ints=[…]`, `note=…`, `tags=["hito", "comisión accidental"]`) para la nota:

```sql
SELECT id_int FROM interventions
WHERE country IN ('CO', 'PE', 'EC', 'CL') AND n_words > 10000 AND regexp_matches(speaker_raw, '(?i)secretari')
```

La consulta busca en todo el corpus; `library_edit` solo quita las que están en la biblioteca, ocho, y deja 259. La
exclusión queda guardada: si la biblioteca se reconstruye (§ 10), esas ocho no vuelven. El identificador de la
intervención que se anota (`id_int`) sale de cualquier lectura con `kwic`, y la nota y las etiquetas viajan con ella a
las bibliotecas que se combinen, a la exportación y a la tabla de intervenciones.

<!-- table:bib_describe -->
| País | Intervenciones | Sesiones | Fechas | Oradores | Palabras | Vinculadas (%) | Mujeres (% de las que tienen sexo) | Palabras en turnos largos (%) |
|---|---:|---:|---|---:|---:|---:|---:|---:|
| Chile | 49 | 29 | 2018-05-03 – 2025-11-26 | 38 | 30.949 | 85,7 | 16,7 | 0,0 |
| Colombia | 106 | 63 | 2015-09-16 – 2024-07-31 | 63 | 103.602 | 69,8 | 24,3 | 0,0 |
| Ecuador | 45 | 30 | 2015-09-10 – 2025-12-17 | 33 | 69.963 | 68,9 | 32,3 | 0,0 |
| Perú | 59 | 33 | 2016-06-16 – 2025-09-11 | 45 | 58.941 | 83,1 | 28,6 | 39,4 |
<!-- /table -->

Tras la limpieza, los turnos largos pesan 0 % en Ecuador y siguen en el 39,4 % en Perú, porque se han quedado a
propósito: en las comparaciones por palabras se dejan fuera con `max_turn_words=10000`, que no los borra de la
biblioteca. Las partes son pequeñas: 49 intervenciones de 38 oradores en Chile no aguantan un corte por partido o por
sexo.

> [!WARNING]
> Quita por consulta, no a ojo: una consulta se puede releer, repetir sobre otra edición de los datos y citar en el
> apéndice de métodos. Y no quites lo que estorba a la hipótesis, sino lo que no es la unidad del estudio: aquí,
> documentos leídos que no son debate.

## 8. Usar la biblioteca

**Año a año.** La primera pregunta del estudio es cuándo se debatió el tema en cada cámara.

> **Pide:** «Año a año, ¿cuántas intervenciones de cada biblioteca hay por cada mil intervenciones del pleno, en cada
> país? Pon las dos definiciones.»
>
> *El agente usa* `query_sql`, que une las bibliotecas con las intervenciones y divide por el total del pleno de cada
> año:

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

Por cada mil, y no en bruto, porque las cámaras cambian de tamaño: el pleno de Colombia tuvo 16.198 intervenciones en
2017 y 58.757 en 2020; el de Perú, 19.962 en 2019 y 87.932 en 2020. En bruto, el año con más intervenciones sobre el
tema en Colombia es 2020 (24); por cada mil, 2018 (1,01).

<!-- viz:bib_anual -->
<!-- table:bib_anual -->
| País (definición) | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Chile (segunda) | 0,00 | 0,00 | 0,00 | 0,45 | 0,07 | 0,21 | 0,58 | 0,36 | 0,56 | 0,29 | 0,20 |
| Chile (primera) | 0,06 | 0,06 | 0,19 | 0,27 | 0,61 | 0,37 | 1,42 | 1,02 | 2,49 | 1,21 | 0,86 |
| Colombia (segunda) | 0,15 | 0,00 | 0,86 | 1,01 | 0,72 | 0,41 | 0,47 | 0,00 | 0,09 | 0,08 | 0,00 |
| Colombia (primera) | 0,51 | 0,13 | 0,49 | 0,63 | 0,45 | 0,29 | 0,47 | 0,00 | 0,14 | 0,08 | 0,03 |
| Ecuador (segunda) | 0,17 | 0,00 | 0,00 | 0,23 | 1,40 | 1,06 | 0,33 | 0,18 | 0,12 | 0,20 | 0,72 |
| Ecuador (primera) | 1,92 | 1,09 | 1,07 | 0,91 | 1,67 | 2,11 | 0,98 | 1,40 | 0,59 | 0,47 | 3,30 |
| Perú (segunda) | 0,00 | 0,06 | 0,14 | 0,27 | 0,15 | 0,11 | 0,06 | 0,16 | 0,57 | 0,05 | 0,14 |
| Perú (primera) | 0,00 | 0,00 | 0,19 | 0,18 | 0,05 | 0,14 | 0,04 | 0,22 | 0,85 | 0,08 | 0,21 |
<!-- /table -->

Las dos definiciones coinciden en lo que se puede afirmar. Colombia sube antes que nadie, en 2017 y 2018, y casi
desaparece desde 2022. Perú tiene un solo pico, en 2023. Ecuador sube en 2019 y 2020, y otra vez en 2025. Difieren en
lo que no se puede afirmar sin más: la primera da a Ecuador una línea alta todos los años (entre 0,47 y 3,30 por mil),
que en buena parte es la emigración ecuatoriana; y en Chile las dos suben en 2021 y en 2023, pero en 2023 la primera
llega a 2,49 por mil y la segunda a 0,56. Cuánto más debate Chile el tema depende de la definición.

**Las sesiones de cada pico.** Un año con veinte intervenciones puede ser un solo debate.

> **Pide:** «¿Qué sesiones reúnen más intervenciones de *migracion_venezolana* en cada país?»
>
> *El agente usa* `query_sql` (las tres sesiones con más intervenciones de la biblioteca en cada país).

Diez de las 22 intervenciones de Perú en 2023 son de la sesión del 3 de mayo, sobre los migrantes que se acumulan en
Tacna, en la frontera con Chile. Seis de las siete de Ecuador en 2025 son del 27 de agosto, cuando la Asamblea debate
la denuncia del estatuto migratorio con Venezuela. Siete de las 21 de Colombia en 2019 son del 20 de agosto, con el
proyecto que da la nacionalidad a los hijos de venezolanos nacidos en Colombia. Siete de las nueve de Chile en 2021, de
una sesión de octubre sobre los ingresos clandestinos por el norte. Antes de leer un pico como una tendencia, lee la
sesión.

**Lo que desaparece.** La parte colombiana casi se vacía desde 2022.

> **Pide:** «Desde la instalación del Congreso colombiano en julio de 2022, ¿de qué se habla cuando se dice
> *venezolano*?»
>
> *El agente usa* `kwic` (`pattern="venezolan*"`, `countries=["CO"]`, `date_from="2022-07-20"`, `n=15`).

Son 111 intervenciones. La mayoría de las leídas hablan de Venezuela como política exterior: las elecciones de 2024, el
restablecimiento de las relaciones, el gas, el comercio. Los migrantes siguen ahí (una intervención recuerda que en
Colombia viven al menos dos millones de venezolanos), pero el pleno ya no debate su llegada.

**De qué habla cada cámara.** La biblioteca también sirve para comparar vocabularios, cada cámara consigo misma.

> **Pide:** «En cada país, ¿qué palabras distinguen las intervenciones de *migracion_venezolana* del resto del pleno en
> los mismos años? Deja fuera los turnos de más de 10.000 palabras.»
>
> *El agente usa* `distinctive_words` (`field="library"`, `a="migracion_venezolana"`, `countries=[…]`,
> `date_from="2015-01-01"`, `exclude_chair=true`, `max_turn_words=10000`), un país cada vez.

Con `field="library"` y un solo país, la comparación es la biblioteca frente al resto de su propia cámara: no compara
las lenguas ni los estilos de cuatro parlamentos, sino de qué habla cada uno cuando habla del tema.

<!-- table:bib_palabras -->
| País | Palabras que distinguen el debate del resto de su cámara, de más a menos |
|---|---|
| Chile | norte, cúcuta, visa, irregular, colchane, bolivia, embajador, expulsiones, país, fronteras, extranjeros, caracas, haitianos, países, visas |
| Colombia | bogotá, emergencia, gc898, cancillería, frontera, corrigió, discrimine, millones, salud, cuba, relaciones, exterior, humanitaria, diplomacia, upc |
| Ecuador | estatuto, movilidad, denuncia, excanciller, bolivariana, humana, frontera, exterior, internacional, carácter, relaciones, ginebra, internacionales, homicidios, exteriores |
| Perú | extranjeros, cancillería, frontera, fronteras, acnur, chile, relaciones, exteriores, irregular, países, cooperación, vigilancia, humanitario, tacna, consulares |
<!-- /table -->

Cada cámara debate un problema distinto. Chile, la entrada por el norte: *Colchane*, *Bolivia*, *visa*, *irregular*,
*expulsiones*. Colombia, la emergencia y la diplomacia: *emergencia*, *salud*, *humanitaria*, *cancillería*,
*relaciones*, *exterior*. Ecuador, el marco legal (*estatuto*, *denuncia*, *movilidad humana*, el nombre de su ley de
migración) y la seguridad (*homicidios*). Perú, los extranjeros y el control de su frontera sur: *extranjeros*,
*frontera*, *vigilancia*, *Tacna*, *Chile*, *ACNUR*.

> [!WARNING]
> La lista de palabras distintivas de una biblioteca empieza por las que la definen: aquí *venezolanos*, *Venezuela*,
> *migrantes*, *migratoria*… No dicen nada nuevo, y la tabla las quita, junto con *Migraciones*, el nombre de una
> institución peruana, y los nombres de persona. Mira también lo raro: *gc898* y *corrigió*, en Colombia, son sellos
> de corrección de la transcripción en una sola intervención de 2019, que `kwic` encuentra (`pattern="gc898"`). Una
> intervención larga basta para subir una palabra a la lista.

## 9. Más allá de las palabras clave

Una biblioteca hecha con palabras recoge las intervenciones que las dicen. Un debate sobre un tema tiene también las
que no las dicen: la pregunta que sigue, la respuesta del ministerio, quien habla de «los migrantes» sin decir de dónde
vienen, quien llama al tema por otro nombre. Las lecturas de los §§ 5 y 6 miden la precisión: de lo que entra, cuánto
responde a la pregunta. Falta la cobertura: de lo que responde a la pregunta, cuánto entra. La precisión se lee dentro
de la biblioteca; la cobertura, fuera.

El MCP no busca por significado: las bibliotecas se definen con palabras, expresiones regulares y filtros. Lo que una
definición deja fuera se busca donde debería estar, y se lee. Esta sección mira en tres sitios: otras palabras del
debate, el resto de cada debate y lo que una definición pierde frente a otra. Cada lectura cuenta tres clases: las
intervenciones que hablan de migrantes venezolanos y los nombran en algún punto; las que hablan de migración sin decir
de dónde; y las demás (otro tema, la política de Venezuela o el procedimiento).

**Ampliar el vocabulario.** La tabla del § 8 da palabras de cada debate que la definición no busca: *Colchane* en
Chile, *movilidad humana* en Ecuador, *extranjeros* en Perú. ¿Son otras maneras de decir el tema?

> **Pide:** «Para cada una de esas tres palabras, haz una biblioteca en su país desde 2015, sin la presidencia; quítale
> lo que ya está en *migracion_venezolana* y enséñame veinte intervenciones al azar de lo que queda.»
>
> *El agente usa* `library_create` (`terms="colchane"`, `countries=["CL"]`, `date_from="2015-01-01"`,
> `exclude_chair=true`), `library_combine` (`a="colchane"`, `b="migracion_venezolana"`, `op="difference"`) y `kwic`
> con `library="colchane_fuera"`; y lo mismo con `movilidad humana` en Ecuador y `extranjero*` en Perú.

*Colchane*, el paso fronterizo con Bolivia, sale en 125 intervenciones, y 117 están fuera. Las líneas leídas hablan
de la frontera norte (la migración que entra por ella, los militares, las visitas de parlamentarios), y ninguna dice
de dónde vienen los migrantes: la palabra nombra una ruta, no una nacionalidad. *Movilidad humana* sale en 1.113, y 1.097 están fuera: casi todas nombran el Ministerio de Relaciones Exteriores y
Movilidad Humana, la comisión de la Asamblea o la ley que protege a los ecuatorianos en el exterior. *Extranjero* sale
en 1.507, y 1.489 están fuera: sobre todo *en el extranjero* (los peruanos que viven fuera, las elecciones fuera del
país, los viajes del presidente de la República), y capitales, empresas o tropas extranjeras. Una palabra que distingue
un debate no lo define: lo distingue porque el debate la usa más que el resto de la cámara, y el resto la usa para
otras cosas.

Pero una línea de `kwic` enseña unos 240 caracteres, y una intervención puede nombrar a los venezolanos en otro punto.
Como para hablar de migrantes venezolanos hay que nombrarlos, hay un techo que no hace falta leer, y una lectura que
sí: las intervenciones de la muestra que nombran Venezuela, enteras.

> **Pide:** «¿Cuántas de las que quedan fuera nombran *venezolano* o *Venezuela*? De las veinte de cada muestra,
> enséñame enteras las que lo hacen.»
>
> *El agente usa* `library_combine` (`a="colchane_fuera"`, `b="venezuela"`, `op="intersection"`), con la biblioteca
> *venezuela* del § 4, y lo mismo con las otras dos; después, `get_intervention` con el `id_int` de cada intervención
> de la muestra que nombra Venezuela.

Nombran Venezuela 21 de las 117 de *Colchane*, 118 de las 1.097 de *movilidad humana* y 67 de las 1.489 de
*extranjero*. En las muestras, tres de *Colchane*, tres de *movilidad humana* y ninguna de *extranjero*. Leídas
enteras, las tres de *Colchane* hablan de migrantes venezolanos: ponen la crisis o el régimen de Venezuela como causa
de lo que pasa en la frontera, lejos de la línea leída. Las tres de *movilidad humana* hablan de los ecuatorianos que
viven en Venezuela, de su política o de delincuencia organizada. De las veinte de *Colchane*, por tanto, tres son de la primera clase, doce de la
segunda y cinco de otras cosas de la frontera.

Cuando la clase depende de algo que se dice en otro punto, la línea no basta: se lee la intervención entera.
*Colchane* trae sobre todo la segunda clase, y añadirla a la definición es decidir que la pregunta incluye la migración
que entra por el norte, se diga o no de dónde viene. *Movilidad humana* y *extranjero* traerían cientos de
intervenciones de otro tema por unas decenas, como mucho, de la primera clase.

**El contexto del debate.** Un debate es una secuencia: quien pregunta, quien responde, quien replica. La biblioteca
recoge las intervenciones que dicen las palabras, y el resto del mismo debate queda fuera. Para verlo se buscan las
sesiones donde la biblioteca tiene tres intervenciones o más y, en cada una, las que hay entre la primera y la última
de la biblioteca sin estar en ella.

> **Pide:** «En las sesiones donde *migracion_venezolana* tiene tres intervenciones o más, ¿cuántas intervenciones hay
> entre la primera y la última de la biblioteca que no están en ella, sin la presidencia? Enséñame después veinte al
> azar en cada país.»
>
> *El agente usa* `query_sql`:

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

Para la muestra, la misma consulta termina en `SELECT country, date, id_int, n_words, text FROM outside`, con veinte
filas por país elegidas al azar y siempre las mismas (`QUALIFY row_number() OVER (PARTITION BY country ORDER BY
md5(id_int)) <= 20`). El filtro de la presidencia es una versión simple del que usan las herramientas: quita también,
por ejemplo, a quien preside el Consejo de Ministros en Perú, que en el § 7 se quedaba. El identificador `id_int` lleva
delante el código del país, así que basta para saber si una intervención está en la biblioteca. La consulta corta cada
texto en 900 caracteres (`max_cell_chars`): como con las palabras, las que nombran Venezuela se leen enteras.

<!-- table:bib_contexto -->
| País | Sesiones | En la biblioteca | Fuera | Fuera, de 50 palabras o más |
|---|---:|---:|---:|---:|
| Chile | 4 | 18 | 193 | 170 |
| Colombia | 11 | 46 | 903 | 352 |
| Ecuador | 4 | 15 | 84 | 73 |
| Perú | 4 | 25 | 82 | 68 |
<!-- /table -->

Fuera hay muchas más intervenciones que dentro, pero no son más debate sobre el tema. En Colombia, de las 903 que
quedan fuera solo 352 tienen 50 palabras o más: el resto son votaciones, lecturas de artículos y avisos de
procedimiento. De las veinte leídas en cada cámara, hablan de migrantes venezolanos y los nombran siete en Perú, tres
en Colombia, tres en Chile y dos en Ecuador. Nombrar Venezuela no basta: en Chile, cuatro de las siete que la nombran
son de una sesión especial de 2018 sobre su situación política, y en Ecuador dos de cuatro hablan de los ecuatorianos
que viven allí.

La segunda clase pesa tanto como la primera: siete de veinte en Perú, cuatro en Chile, cuatro en Colombia. Son «los migrantes», «las
personas que vienen de afuera», «la crisis migratoria», las expulsiones, la ley de refugio. En un debate sobre la
migración venezolana, muchas hablan de los venezolanos sin nombrarlos, pero no todas: en Chile, *haitianos* está entre
las palabras del debate (§ 8). Si entran o no es una decisión sobre la pregunta, no sobre las palabras: ¿la llegada de
migrantes venezolanos, o la migración que llega por esas fronteras? Se decide antes de añadir nada, se escribe y se
aplica igual en las cuatro cámaras.

**Medir la cobertura: leer lo que queda fuera.** El tercer sitio es lo que una definición pierde frente a otra. El § 6
calculaba que en Chile la segunda definición se queda con menos de la mitad de lo que reúne la primera. Se puede medir.

> **Pide:** «Haz una biblioteca con lo que está en *migracion_y_venezuela* y no en *migracion_venezolana*, y enséñame
> veinte intervenciones al azar de Chile, con la frase donde se nombra Venezuela.»
>
> *El agente usa* `library_combine` (`name="perdidas"`, `a="migracion_y_venezuela"`, `b="migracion_venezolana"`,
> `op="difference"`) y `kwic` (`pattern="\b(venezolan|venezuela)"`, `regex=true`, `library="perdidas"`,
> `countries=["CL"]`, `n=20`).

Son 304 intervenciones: 128 de Chile, 115 de Ecuador, 33 de Perú y 28 de Colombia. Por el § 5 (6 de 20), las de Ecuador
deben de ser sobre todo el ruido que la primera definición tenía allí; no se leen aquí. De las veinte de Chile, dieciséis
hablan de migrantes venezolanos. La segunda definición las pierde por tres razones: los migrantes y Venezuela están en
frases distintas; la frase dice *Venezuela* y no *venezolano*; o la palabra de migración no es ninguna de las que
busca: *migrando*, *migrar*, *llegada*, *expulsión*.

Todas las lecturas, juntas:

<!-- table:bib_fuera -->
| Dónde | Fuera | Nombran Venezuela | De 20 leídas: nombran Venezuela | migrantes venezolanos | migración sin decir de dónde | otro tema | Migrantes venezolanos fuera (intervalo del 95 %) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Lo que la segunda definición deja fuera de la primera, Chile | 128 | 128 | 20 | 16 | 3 | 1 | 75–118 |
| El resto de los debates, Chile | 193 | 41 | 7 | 3 | 4 | 13 | 6–31 |
| El resto de los debates, Colombia | 903 | 36 | 3 | 3 | 4 | 13 | 16–36 |
| El resto de los debates, Ecuador | 84 | 16 | 4 | 2 | 0 | 18 | 2–14 |
| El resto de los debates, Perú | 82 | 29 | 7 | 7 | 7 | 6 | 19–29 |
| *Colchane*, Chile | 117 | 21 | 3 | 3 | 12 | 5 | 9–21 |
| *movilidad humana*, Ecuador | 1.097 | 118 | 3 | 0 | 2 | 18 | 0–66 |
| `extranjero*`, Perú | 1.489 | 67 | 0 | 0 | 4 | 16 | 0–67 |
<!-- /table -->

La última columna convierte cada lectura en un intervalo. Como la primera clase tiene que nombrar Venezuela, se
estima entre las que la nombran: la proporción de la primera clase entre las leídas que nombran Venezuela, con su
intervalo del 95 % (el de Wilson), por las que nombran Venezuela fuera. Si la muestra no tiene ninguna, el intervalo va
de cero al techo. Con muestras tan pequeñas, da un orden de magnitud, no una medida.

Lo que más falta, en Chile, es lo que la segunda definición pierde de la primera: entre 75 y 118 intervenciones sobre
migrantes venezolanos. Con las 49 que tiene, la segunda cubre entre el 29 % y el 40 % de lo que encuentran las dos
juntas, y eso como mucho, porque hay intervenciones que no encuentra ninguna. Es precisa en las cuatro cámaras (§ 6) y
en una cubre un tercio: precisión y cobertura se miden por separado. El resto de los debates añade unas decenas en cada
cámara, y *Colchane* entre 9 y 21; los tres sitios se solapan en parte, así que no se suman. *Movilidad humana* y
*extranjero* traen sobre todo otros temas.

Para añadir lo que falta hay dos caminos. Una definición más: `library_create` con `extend=true` suma a la biblioteca
otra definición (aquí, para Chile, una expresión que acepte *llegada*, *expulsión* o el verbo *migrar* junto a
*venezolano*), y la reconstrucción la repite. O lo leído: `library_edit` (`action="add"`, `id_ints=[…]`) añade las
intervenciones que se han leído y aceptado, y la reconstrucción las encuentra por su texto. Las dos se prueban como la
primera definición: una muestra dentro, una lectura fuera y el recuento apuntado. Esta guía no añade nada: enseña
dónde mirar y cuánto falta. Las bibliotecas de trabajo de esta sección se borran como las del § 10.

> [!NOTE]
> El MCP no tiene búsqueda semántica: ni embeddings ni un buscador por significado. Hay dos maneras de ir más allá de
> las palabras, y las dos acaban en identificadores. Una es que el agente lea: con `kwic`, `get_intervention` o
> `get_session` decide qué responde a la pregunta, y lo añade o lo quita por su `id_int`. La otra es calcular fuera
> del MCP la similitud con un modelo de embeddings, sobre las intervenciones que escribe `export_result`, y traer los
> identificadores con `library_edit` e `id_ints`. En los dos casos el resultado se prueba como una definición: se lee
> una muestra dentro y lo que queda fuera, y se apunta.

## 10. Mantenerla

**Reconstruirla.** Cada país publica ediciones nuevas de sus datos, y los identificadores de las intervenciones cambian
de una edición a otra.

> **Pide:** «Reconstruye *migracion_venezolana* sobre los datos descargados.»
>
> *El agente usa* `library_rebuild` (`name="migracion_venezolana"`).

La reconstrucción vuelve a aplicar las definiciones, mantiene las exclusiones y encuentra por su texto las
intervenciones añadidas a mano y sus notas. Sobre la misma edición, el informe dice que se quedan las 49, 106, 45 y 59
intervenciones, que no entra ninguna, que no se pierde ninguna y que no se pierde ninguna nota: Ecuador sigue en 45, y
no en 53, porque las ocho lecturas siguen fuera. Con una edición nueva, el informe dice qué entra y qué se pierde en
cada país; una intervención cuyo texto se corrigió cuenta como perdida, y su definición puede volver a traerla. La
lectura de la muestra es de una edición: con otra, se vuelve a leer.

Una biblioteca combinada, como *migracion_y_venezuela*, no tiene definición propia. La reconstrucción encuentra sus
intervenciones por su texto, pero no repite ninguna definición, así que no recoge lo que una edición nueva añada. Para
ponerla al día se reconstruyen *migracion* y *venezuela* y se cruzan otra vez, y lo que se hubiera corregido a mano
en la combinada se pierde. Las correcciones a mano se hacen en bibliotecas con definición propia, como la segunda.

**Ampliarla.** `extend=true` añade a una biblioteca que ya existe otro país u otro periodo, con su propia definición, y
`per_country` da a un país sus propios términos: para sumar Brasil, la misma expresión en portugués.

**Exportarla.**

> **Pide:** «Exporta *migracion_venezolana* para el Diarios Explorer, con una tabla CSV de sus intervenciones.»
>
> *El agente usa* `library_export` (`name="migracion_venezolana"`, `folder=…`, `table_format="csv"`).

Escribe un archivo `.2replib` por país, porque el explorador abre un país cada vez; un índice con el que
`library_import` reconstruye la biblioteca comparada; y la tabla, con cada intervención, sus datos, su nota y sus
etiquetas. Cada `.2replib` se importa en el explorador con el CSV de su propio país cargado: el explorador no lo
comprueba.

**Borrar lo que ya no hace falta.**

> **Pide:** «Borra las bibliotecas de trabajo: *migracion_1*, *migracion_3* y *una_mencion*.»
>
> *El agente usa* `library_delete`, primero sin `confirm` y después con `confirm=true`.

Sin `confirm`, dice lo que borraría (las 5.249 intervenciones de *migracion_1*) y no borra nada. Con `confirm=true`
borra la biblioteca, nunca los datos. Se quedan *migracion* y *venezuela*, que hacen falta para poner al día el cruce,
y las dos definiciones. Para el apéndice de métodos, `query_log` lista cada paso con sus parámetros y la versión de
los datos ([Inicio, § 5](../TUTORIAL.md#5-cerrar-un-estudio)).

## 11. Lista de comprobación

1. Escribe la pregunta: de qué, dónde, cuándo, quién y para qué.
2. Prueba las palabras con `term_counter`, país por país, y lee con `kwic` cada cifra que sorprenda.
3. Prueba el umbral: compara una, dos y tres menciones, y lee lo que queda entre dos umbrales.
4. «A y B» son dos bibliotecas y un cruce (`library_combine`), o una expresión regular.
5. Describe la biblioteca antes de compararla: el tamaño de cada parte, los turnos largos, los años con poco.
6. Lee una muestra al azar en cada cámara, cuenta cuántas responden a la pregunta y apúntalo.
7. Si una cámara falla, estrecha la definición, vuelve a leer y apunta lo que pierdes en las otras.
8. Mide también la cobertura: lee lo que queda fuera (lo que pierde cada definición, el resto de los debates, las
   palabras del debate), pon un techo con lo que nombra el tema y decide qué hacer con lo que lo trata sin nombrarlo.
9. Quita por consulta lo que no es la unidad del estudio, y anota los hitos.
10. Tasas, no recuentos, y la sesión detrás de cada pico.
11. Deja fuera las palabras que definen la biblioteca antes de leer un vocabulario.
12. Guarda las definiciones, las lecturas y la edición de los datos; reconstruye, exporta y borra lo que ya no sirve.

> **Pídelo de una vez:** «Quiero estudiar cómo debatieron los plenos de Colombia, Perú, Ecuador y Chile la llegada de
> migrantes venezolanos desde 2015. Prueba primero las palabras (*migrante*, *migración*, *migratorio*, *inmigrante*,
> *refugiado*, *venezolano*) y lee las cifras que sorprendan. Haz una biblioteca sin la presidencia, pruébale el umbral
> leyendo lo que queda entre una y dos menciones, descríbela y lee veinte intervenciones al azar en cada país, contando
> cuántas hablan de migrantes venezolanos. Si una cámara falla, estrecha la definición a la misma frase y vuelve a
> leer. Lee también lo que queda fuera (lo que la segunda definición pierde de la primera, el resto de los debates y las
> palabras que distinguen cada debate) y dime cuántas intervenciones sobre migrantes venezolanos faltan. Quita por consulta los documentos leídos por la secretaría, compara año a año por cada mil intervenciones con
> las dos definiciones, mira qué sesiones hacen los picos y qué palabras distinguen el debate en cada cámara, sin las
> que definen la biblioteca y sin los turnos de más de 10.000 palabras. No cites nombres de personas.»
