# Cómo entra una palabra en dieciséis parlamentos

<!-- eyebrow: Estudio 1 · La difusión de un concepto -->

*[English version](../en/feminicidio.md) · [Índice del tutorial](../TUTORIAL.md)*

«Feminicidio» nombra el asesinato de una mujer por ser mujer. La palabra llegó a los parlamentos iberoamericanos en
este siglo, casi siempre de la mano de una ley. Este estudio sigue su entrada en las dieciséis cámaras: cuándo aparece,
qué sesiones la concentran, quién la dice y con qué otras palabras. Siete herramientas, encadenadas como lo haría un
agente, y en cada paso una comprobación antes de creer el resultado.

<!-- side -->

**La cadena de este estudio**

1. `term_counter`: cuántas veces y desde cuándo
2. `ngram_viewer`: la curva de cada parlamento
3. `term_frequency`: las sesiones que concentran la palabra
4. `get_session`: qué se debatía en ellas
5. `query_sql`: diputadas y diputados, con la tabla de unigramas
6. `ngram_viewer`: los términos de España y Portugal
7. `collocations`: lo que acompaña a la palabra

## 1. Cuántas veces y desde cuándo

Las tres formas cuentan como un solo término: *feminicidio*, *femicidio* (la forma de los debates de Guatemala, Argentina,
Panamá o Uruguay) y *feminicídio* en portugués. Los turnos de más de 10.000 palabras, casi siempre
documentos leídos en el pleno, quedan fuera.

> **Pide:** «¿Cuántas veces se ha dicho *feminicidio*, *femicidio* o *feminicídio* en cada parlamento, y cuándo se
> dijo por primera vez? Deja fuera los turnos de más de 10.000 palabras.»
>
> *El agente usa* `term_counter` (`terms="feminicidio+feminicídio+femicidio"`, `max_turn_words=10000`).

<!-- viz:fem_primeros -->
<!-- table:fem_primeros -->
| País | Primer uso | Partido | Corpus desde | Usos | Año pico (por millón) | Sesión con más usos (usos) |
|---|---|---|---|---:|---|---|
| Costa Rica | 2001-07-24 | FUERZA DEMOCRÁTICA | 1994 | 502 | 2024 (45,5) | 2021-03-08 (32) |
| Rep. Dominicana | 2002-11-21 | PLD | 2001 | 240 | 2021 (83,0) | 2013-06-25 (40) |
| Panamá | 2002-12-10 | ARN | 1996 | 435 | 2013 (80,9) | 2013-10-17 (71) |
| México | 2003-09-01 | PRD | 1988 | 5.737 | 2020 (196,6) | 2020-02-18 (144) |
| Guatemala | 2004-07-07 | URNG MAIZ | 2000 | 306 | 2008 (87,6) | 2008-04-09 (46) |
| Chile | 2005-01-06 | PPD | 1990 | 1.189 | 2023 (59,2) | 2023-04-18 (129) |
| España | 2005-03-17 | PSOE | 1977 | 23 | 2022 (1,4) | 2021-06-15 (4) |
| Perú | 2007-09-06 | AP | 1995 | 1.499 | 2011 (101,0) | 2011-12-01 (218) |
| Uruguay | 2008-03-05 | Partido Nacional | 1985 | 290 | 2017 (61,2) | 2017-09-12 (78) |
| Portugal | 2008-10-01 | BE | 1976 | 24 | 2024 (3,3) | 2024-12-18 (4) |
| Colombia | 2008-11-25 | MIRA | 2000 | 806 | 2023 (148,6) | 2023-12-13 (172) |
| Argentina | 2010-05-04 | (no vinculado) | 1983 | 262 | 2018 (50,1) | 2012-04-18 (44) |
| Brasil | 2011-04-28 | PPS | 2003 | 4.056 | 2024 (106,5) | 2021-05-18 (160) |
| Ecuador | 2011-11-16 | MPAIS | 1979 | 999 | 2023 (115,2) | 2017-07-11 (94) |
| Paraguay | 2016-05-25 | Avanza País | 1988 | 164 | 2023 (57,6) | 2023-08-30 (34) |
| El Salvador | 2018-06-21 | (no vinculado) | 2018 | 264 | 2023 (79,8) | 2023-02-21 (130) |
<!-- /table -->

En total, 16.796 usos en 5.182 intervenciones de 2.260 sesiones, dichos por 2.103 oradores. México reúne 5.737 y
Brasil 4.056: entre los dos, más de la mitad. El orden de llegada empieza en Centroamérica y México (Costa Rica en
2001, República Dominicana y Panamá en 2002, México en 2003, Guatemala en 2004) y termina en Brasil y Ecuador (2011)
y Paraguay (2016). En España y Portugal la palabra aparece pronto, en 2005 y 2008, pero casi no se usa: 23 y 24 veces
en veinte años.

> [!WARNING]
> `term_counter` da el primer uso **en el corpus**, no en el país. El de El Salvador empieza en mayo de 2018, así que
> su «primer uso» de junio de 2018 solo dice que la palabra ya circulaba. Antes de leer el orden de llegada como un
> orden de difusión, compara cada fecha con el inicio del corpus (columna «Corpus desde», que da `list_countries`).
> En Argentina y El Salvador el primer uso es de un orador que el registro no identifica: puede ser un ministro, una
> invitada o una voz colectiva.

## 2. La curva de cada parlamento

> **Pide:** «Dibuja la frecuencia por millón de palabras, año a año desde 2000, un panel por país, con media móvil
> de tres años y sin los turnos largos.»
>
> *El agente usa* `ngram_viewer` (`terms="feminicidio+feminicídio+femicidio"`, `split_by_country=true`,
> `smoothing=1`, `date_from="2000"`, `max_turn_words=10000`). Con `chart_path` dibuja además el gráfico en un SVG.

![«feminicidio» en seis parlamentos: el SVG que dibuja ngram_viewer](../img/feminicidio_es.svg)

<!-- viz:fem_paneles -->
<!-- table:fem_paneles -->
| País | 2005 | 2010 | 2015 | 2020 | 2025 |
|---|---:|---:|---:|---:|---:|
| Costa Rica | 2,2 | 1,7 | 4,2 | 18,0 | 32,8 |
| Rep. Dominicana | 1,6 | 7,0 | 18,4 | 35,0 | 26,9 |
| Panamá | 0,0 | 1,9 | 13,8 | 10,9 | 25,3 |
| México | 8,8 | 10,2 | 35,1 | 119,7 | 70,8 |
| Guatemala | 4,5 | 8,7 | 8,4 | 6,5 | 5,8 |
| Chile | 0,8 | 8,0 | 2,7 | 27,0 | 11,6 |
| España | 0,1 | 0,0 | 0,2 | 0,5 | 0,3 |
| Perú | 0,0 | 36,6 | 21,6 | 35,8 | 5,0 |
| Uruguay | 0,0 | 0,6 | 1,4 | 9,1 | 2,7 |
| Portugal | 0,0 | 0,0 | 0,0 | 0,9 | 2,5 |
| Colombia | 0,0 | 0,3 | 19,6 | 6,3 | 31,4 |
| Argentina | 0,0 | 2,5 | 5,4 | 4,8 | 4,1 |
| Brasil | 0,0 | 0,0 | 21,4 | 53,2 | 84,2 |
| Ecuador | 0,0 | 0,2 | 8,0 | 9,6 | 46,1 |
| Paraguay | — | — | 3,1 | 5,5 | 27,1 |
| El Salvador | — | — | — | 7,1 | 5,0 |
<!-- /table -->

Hay dos formas de curva. En Guatemala y Perú la palabra sube de golpe con una ley y después baja: el debate se
concentra en unas pocas sesiones. En México, Brasil, Colombia y Ecuador crece de forma sostenida y se queda: la palabra
deja de ser el nombre de un proyecto y pasa al vocabulario de todos los días, en denuncias, condenas y efemérides.
México llega a 119,7 usos por millón de palabras en 2020; Brasil sigue subiendo en 2025 (84,2).

> [!NOTE]
> La media móvil desplaza los picos. En Panamá la curva suavizada culmina en 2014, pero ese año hubo dos usos: los 140
> son de 2013, el año del proyecto de ley que se ve en el paso siguiente. Para fechar un pico, lee el recuento de cada
> año (está en la información emergente de cada panel) o pide `smoothing=0`. Los años con poca base (menos de 250.000
> palabras o de diez sesiones) salen vacíos: el servidor los marca y no deben leerse como tendencia.

## 3. Las sesiones que concentran la palabra

> **Pide:** «¿En qué sesiones se concentra la palabra en cada país? Dame las cinco primeras.»
>
> *El agente usa* `term_frequency` (`by="session"`, `max_rows=5`), un país cada vez.

> **Pide:** «Abre las sesiones con más usos de Guatemala, Perú, Argentina, Panamá y Uruguay. ¿Qué proyecto se
> debatía?»
>
> *El agente usa* `get_session` (`id_session=…`), que devuelve la lista de turnos con el comienzo de cada uno. El
> agente busca en ella el proyecto y, si hace falta, lee una intervención completa con `get_intervention`.

<!-- table:fem_sesiones -->
| País | Sesión | Qué se debatía | Usos | Intervenciones que la usan | Turnos de la sesión |
|---|---|---|---:|---:|---:|
| Guatemala | 2008-04-09 | Ley contra el Femicidio y otras Formas de Violencia contra la Mujer, aprobada en la sesión | 46 | 22 | 141 |
| Perú | 2011-12-01 | Proyecto del Ejecutivo, con urgencia, que modifica el artículo 107 del Código Penal; se le acumulan otros proyectos de congresistas sobre feminicidio | 218 | 60 | 357 |
| Argentina | 2012-04-18 | Reforma del Código Penal sobre el femicidio, al final de una sesión con otros proyectos | 44 | 16 | 429 |
| Panamá | 2013-10-17 | «Proyecto de Femicidio», de 75 artículos, junto a otros puntos del orden del día | 71 | 25 | 263 |
| Uruguay | 2017-09-12 | Proyecto que hace del femicidio un agravante muy especial del homicidio | 78 | 20 | 150 |
<!-- /table -->

En los cinco países, la sesión con más usos es la del debate de la ley. Es la prueba de que la curva mide algo real:
los picos no son errores de transcripción ni documentos leídos, sino el momento en que la cámara legisla. En México,
en cambio, la sesión con más usos (144, en febrero de 2020) no llega al 3 % del total: allí la palabra está repartida
en cientos de sesiones.

> [!TIP]
> `get_session` sin `include_text` devuelve solo el comienzo de cada turno, que basta para orientarse sin cargar
> una sesión entera. Las aperturas incluyen a veces nombres de quien preside o de terceros: si vas a publicar,
> parafrasea, como en la tabla.

## 4. Quién dice la palabra

`term_counter` ya separa por sexo: en todo el periodo, las diputadas dicen *feminicidio* 42,52 veces por millón de
palabras y los diputados 4,41.

<!-- table:fem_sexo_total -->
|  | Usos | Por millón de palabras |
|---|---:|---:|
| Diputadas | 11.090 | 42,52 |
| Diputados | 4.569 | 4,41 |
| Oradores no vinculados | 1.137 | 7,37 |
<!-- /table -->

¿Pasa en todos los parlamentos o lo arrastran los grandes? La tabla de unigramas de la base (palabras por país, año y
sexo) lo responde en una consulta.

> **Pide:** «Compara la frecuencia de la palabra entre diputadas y diputados desde 2012, país por país. Usa la tabla
> de unigramas.»
>
> *El agente usa* `query_sql`:

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
| País | Usos (diputadas) | Por millón | Usos (diputados) | Por millón | Razón |
|---|---:|---:|---:|---:|---:|
| Brasil | 1.232 | 83,43 | 710 | 7,73 | 10,8 |
| El Salvador | 110 | 24,01 | 21 | 2,28 | 10,5 |
| Colombia | 204 | 45,92 | 115 | 5,52 | 8,3 |
| Paraguay | 49 | 31,23 | 26 | 4,29 | 7,3 |
| Chile | 555 | 65,53 | 301 | 9,10 | 7,2 |
| Costa Rica | 286 | 21,44 | 106 | 3,57 | 6,0 |
| Perú | 393 | 36,43 | 180 | 6,57 | 5,5 |
| Ecuador | 517 | 62,81 | 161 | 12,08 | 5,2 |
| México | 2.478 | 45,72 | 408 | 9,58 | 4,8 |
| España | 9 | 0,59 | 4 | 0,15 | 3,9 |
| Portugal | 9 | 0,77 | 5 | 0,22 | 3,5 |
| Uruguay | 129 | 14,98 | 156 | 4,33 | 3,5 |
| Rep. Dominicana | 46 | 37,36 | 65 | 10,95 | 3,4 |
| Guatemala | 40 | 17,72 | 82 | 6,92 | 2,6 |
| Argentina | 148 | 18,79 | 214 | 10,11 | 1,9 |
| Panamá | 76 | 19,79 | 192 | 15,19 | 1,3 |
<!-- /table -->

En los dieciséis la usan más ellas. La distancia va de 1,3 veces en Panamá a 10,8 en Brasil, donde una diputada
dice la palabra 83 veces por millón de palabras y un diputado menos de 8. Que en Uruguay, República Dominicana,
Guatemala, Argentina o Panamá los diputados sumen más usos que las diputadas no contradice nada: hablan muchas
más palabras.

> [!NOTE]
> La tabla `unigrams` guarda las palabras en minúsculas y sin tildes (`fold`), así que `feminicidio` incluye
> *feminicídio*. Es rápida porque ya está agregada, pero no permite filtrar por longitud de turno: cuenta también los
> documentos leídos. `describe_data` describe todas las tablas de la base.

## 5. España y Portugal: otra palabra para lo mismo

Que una palabra no aparezca no quiere decir que el asunto no exista. En los dos parlamentos ibéricos el debate sobre
la violencia contra las mujeres se hizo con otros términos.

> **Pide:** «En España y Portugal casi no aparece. ¿Qué términos usan? Compara *violencia de género* y *violencia
> doméstica*, en las dos lenguas, desde 1996.»
>
> *El agente usa* `ngram_viewer` (`terms="violencia de género+violência de género, violência doméstica+violencia
> doméstica, feminicidio+feminicídio"`, `countries=["ES","PT"]`, `split_by_country=true`). La coma separa términos;
> el signo `+` suma variantes de un mismo término.

<!-- viz:fem_iberia -->
<!-- table:fem_iberia -->
| Serie | 1998 | 2002 | 2006 | 2010 | 2014 | 2018 | 2022 | 2025 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ES · género | 2,6 | 44,8 | 175,5 | 138,1 | 204,1 | 261,3 | 140,4 | 118,6 |
| PT · género | 0,0 | 0,0 | 6,7 | 3,0 | 8,8 | 11,5 | 9,2 | 17,3 |
| ES · doméstica | 24,2 | 57,5 | 17,7 | 8,5 | 8,0 | 4,7 | 2,3 | 2,3 |
| PT · doméstica | 6,9 | 20,0 | 62,0 | 72,5 | 88,8 | 216,8 | 195,6 | 248,9 |
<!-- /table -->

Los dos parlamentos eligieron palabras distintas. En el Congreso español, *violencia de género* pasa de 2,6 usos por
millón en 1998 a 175,5 en 2006 y desplaza a *violencia doméstica*, que cae de 57,5 a menos de 3. En la Assembleia da
República el término es *violência doméstica*, que llega a 248,9 en 2025, mientras *violência de género* no pasa
de 20. Una comparación internacional con un solo término mide el vocabulario de cada país, no su atención al problema.

## 6. Lo que acompaña a la palabra

La frecuencia dice cuánto; las colocaciones, en qué sentido. Las palabras que aparecen cerca de *feminicidio* más de
lo que el azar haría esperar cambian con los años.

> **Pide:** «En México, ¿con qué palabras aparece *feminicidio* hasta 2011, y con cuáles desde 2016?»
>
> *El agente usa* `collocations` dos veces (`pattern="feminicidio*"`, `countries=["MX"]`, `date_to="2011"` y
> `date_from="2016"`, `max_turn_words=10000`).

<!-- viz:fem_colocaciones -->
<!-- table:fem_colocaciones -->
|  | Hasta 2011 | G² | Desde 2016 | G² |
|---:|---|---:|---|---:|
| 1 | relacionadas | 596 | delito | 2.190 |
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

Hasta 2011, las compañeras de la palabra son las de una investigación: *investigaciones*, *relacionadas*,
*registrados*, *ocurridos*, *competentes*, y un lugar, Ciudad Juárez. Desde 2016 son las del derecho penal y la
condena: *delito*, *tentativa*, *homicidio*, *doloso*, *tipificación*, *víctimas*, *aumento*, y *condena* junto a
*enérgicamente*, el lenguaje de los pronunciamientos que condenan un crimen. Es una hipótesis para leer, no una conclusión: el paso
siguiente es `kwic` con cada colocación, para ver las frases.

## 7. Lo que el estudio permite decir

**Lo que dicen los datos.** La palabra entra en las dieciséis cámaras en dos décadas; en cinco de ellas, la sesión con
más usos es la del debate de su ley; en todas la usan más las diputadas; en México cambia de vocabulario, de la
investigación al delito; y España y Portugal tratan el asunto con otras palabras.

**Lo que no dicen.** El orden de llegada no prueba contagio de un país a otro: para eso harían falta fechas de los
proyectos, redes de quienes los impulsaron o citas explícitas a otras leyes, y el primer uso depende de cuándo empieza
cada corpus. La razón entre diputadas y diputados no dice por qué hablan más del asunto ellas (¿comisiones, agenda,
especialización?); `distinctive_words` con `field="sex"` y `share_of_voice` ayudan a seguir.

**Las comprobaciones de este estudio.** Inicio de cada corpus antes de leer un primer uso; recuento sin suavizar antes
de fechar un pico; lectura de las sesiones pico antes de interpretarlas; una tasa por millón de palabras, nunca un
recuento, para comparar grupos que hablan cantidades distintas; y los términos de cada país antes de comparar países.

> **Pídelo de una vez:** «Estudia cómo entró la palabra *feminicidio* (con *femicidio* y *feminicídio*) en los 16
> parlamentos: primer uso y total por país, la curva anual por millón de palabras sin los turnos de más de 10.000
> palabras, las sesiones que la concentran y qué se debatía en ellas, la diferencia entre diputadas y diputados desde
> 2012, qué términos usan España y Portugal en su lugar y cómo cambian en México las palabras que la acompañan.
> Señala dónde el corpus empieza tarde y no nombres a ninguna víctima.»
