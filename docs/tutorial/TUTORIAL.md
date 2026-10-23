# Tutorial: ParlaIbero desde un agente

*[English version](TUTORIAL.en.md)*

El servidor MCP de ParlaIbero permite que un agente (Claude, ChatGPT de escritorio, Codex, Cursor…) busque, cuente,
compare y lea los 10 millones de intervenciones de los plenos de 16 parlamentos iberoamericanos. No hace falta
programar: se le pide en lenguaje natural y el agente elige la herramienta. Este tutorial recorre las funciones con
preguntas reales y lo que el servidor devuelve.

**Cómo leer los ejemplos.** Cada uno tiene cuatro partes:

> **Pide:** lo que se escribe al agente.
>
> *El agente usa* la herramienta y sus parámetros principales.

Después viene un extracto del resultado y una nota sobre cómo leerlo. Los resultados son reales: se obtuvieron con
parlaibero-mcp 0.6.0 sobre las versiones 2.0 de los conjuntos de Dataverse, y el script
[`ejemplos.py`](ejemplos.py) los reproduce. Están recortados, y las citas de discursos omiten el nombre de quien
habla. La respuesta que redacte el agente variará; los datos, no.

**Contenido**

0. [Empezar](#0-empezar)
1. [Mirar la base antes de interpretar](#1-mirar-la-base-antes-de-interpretar)
2. [Palabras a lo largo del tiempo](#2-palabras-a-lo-largo-del-tiempo)
3. [Quién habla](#3-quién-habla)
4. [Qué distingue a dos grupos](#4-qué-distingue-a-dos-grupos)
5. [Una biblioteca para un asunto](#5-una-biblioteca-para-un-asunto)
6. [Leer en contexto](#6-leer-en-contexto)
7. [Tres redes, tres preguntas](#7-tres-redes-tres-preguntas)
8. [Reproducir, exportar y citar](#8-reproducir-exportar-y-citar)
9. [El caso completo, en ocho peticiones](#9-el-caso-completo-en-ocho-peticiones)
10. [Resumen de herramientas](#10-resumen-de-herramientas)

---

## 0. Empezar

**Instalar.** Hace falta [uv](https://docs.astral.sh/uv/getting-started/installation/). En Claude Code:

```bash
claude mcp add parlaibero -s user -- uvx parlaibero-mcp
```

En Claude Desktop, Cursor, Gemini CLI y la mayoría de clientes se añade este bloque a su configuración (las demás
variantes están en el [README](../../mcp/README.md)):

```json
{ "mcpServers": { "parlaibero": { "command": "uvx", "args": ["parlaibero-mcp"] } } }
```

**Qué hay y qué tengo.**

> **Pide:** «¿Qué parlamentos tiene ParlaIbero y cuáles tengo ya descargados?»
>
> *El agente usa* `list_countries`.

```text
AR  Argentina  ParlaIbero-AR (1983-2025)  v2.0  844 MB  descargado: 258.808 filas, 1.086 sesiones
BR  Brasil     ParlaIbero-BR (2003-2025)  v2.0  1.457 MB  descargado: 1.657.113 filas, 7.731 sesiones
…   (16 países, cada uno con su DOI en Harvard Dataverse)
```

> **Pide:** «Descarga el de Brasil.»
>
> *El agente usa* `download_country` (`country="BR"`).

Cada país se descarga una sola vez (entre 0,5 y 1,5 GB, unos minutos), con verificación MD5, y se carga en una base
DuckDB local en `~/.parlaibero`. Después, todo se calcula en tu ordenador. El servidor no envía nada: solo descarga
los datos de Dataverse y, para la red de palabras, las tablas de expresiones del Diarios Explorer.

---

## 1. Mirar la base antes de interpretar

Antes de leer una tendencia hay que saber cuánto texto hay detrás de cada año.

> **Pide:** «¿Cómo de completa es la base de Brasil desde 2015?»
>
> *El agente usa* `coverage` (`countries=["BR"], by="year", date_from="2015-01-01"`).

| año | sesiones | palabras de habla | vinculadas a un diputado |
|---|---:|---:|---:|
| 2015 | 485 | 11.755.593 | 96,0 % |
| 2016 | 407 | 9.774.223 | 96,9 % |
| 2017 | 512 | 10.381.908 | 98,9 % |
| 2018 | 338 | 5.861.262 | 98,8 % |
| 2019 | 486 | 6.602.044 | 98,8 % |
| 2020 | 206 | 5.178.959 | 98,6 % |

Resumen: ningún año falta y ninguno tiene una base escasa; el 99 % del habla está vinculada a un diputado.

**Cómo leerlo.** El número de palabras cambia mucho de un año a otro (2018 y 2020 tienen la mitad que 2015). Por eso
las tendencias se miden por millón de palabras, no en recuentos brutos. `coverage` marca los años con poca base
(`low_base`) y los que faltan.

> **Pide:** «Compara Argentina y España en 2022 y 2023.»
>
> *El agente usa* `coverage` (`countries=["AR","ES"], date_from="2022-01-01", date_to="2023-12-31"`).

```text
AR  long_turn_words_pct 19,3 %   (2022: 20,4 %; 2023: 17,6 %)
ES  long_turn_words_pct  0,8 %
```

> [!WARNING]
> **Documentos leídos en el acta.** En algunos diarios, los informes, proyectos y listas leídos en voz alta quedan
> como habla porque el acta no los separa. En Argentina, el 19 % de las palabras de esos años está en turnos de más
> de 10.000 palabras; en España, menos del 1 %. Para comparar palabras entre países, repite el análisis con
> `max_turn_words=10000`.

> **Pide:** «¿Qué limitaciones conocidas tiene el corpus de Brasil? En español.»
>
> *El agente usa* `get_documentation` (`country="BR", document="known_limitations", language="es"`).

Devuelve el documento depositado con los datos, con cada limitación y su cifra medida. `get_documentation` sirve
también el README, el diccionario de datos, el informe de construcción y los datos de vinculación, en inglés,
español y portugués.

---

## 2. Palabras a lo largo del tiempo

> **Pide:** «Dibuja cuándo se empezó a hablar de "fake news" en Brasil, España, Argentina y México desde 2010, una
> línea por país, y guárdalo en SVG.»
>
> *El agente usa* `ngram_viewer` (`terms="fake news", countries=["BR","ES","AR","MX"], split_by_country=true,
> smoothing=1, chart_path=".../fake_news.svg"`).

![«fake news» por millón de palabras en cuatro parlamentos](img/ngram_fake_news_es.svg)

| país | primer año | máximo | apariciones |
|---|---:|---:|---:|
| Brasil | 2017 | 143,5 por millón (2023) | 4.692 |
| España | 2017 | 13,5 por millón (2019) | 214 |
| Argentina | 2017 | 7,0 por millón (2024) | 48 |
| México | 2019 | 0,4 por millón (2021) | 11 |

**Cómo leerlo.**

- **Es una tasa, no un recuento:** apariciones por millón de palabras de cada año, comparables entre años y países.
- **El suavizado** (`smoothing=1`) promedia cada año con el anterior y el siguiente, como Google Ngram.
- **Cada punto lleva su base:** palabras, sesiones y si la base es escasa. Una tasa alta sobre pocas palabras pesa
  poco.
- `chart_path` acaba en `.svg` (figura para un artículo) o `.html` (página con datos al pasar el ratón, modo oscuro y
  tabla).

> [!NOTE]
> **Portugués y español.** Brasil y Portugal hablan portugués: un término en español no coincide allí. Para comparar
> se escriben las dos formas unidas con `+`: `"corrupción+corrupção"`. Las búsquedas no distinguen mayúsculas ni
> tildes, y `*` al final busca un prefijo (`democrati*`).

> **Pide:** «¿Cuántas veces se ha dicho "reforma da previdência" en la Câmara, quién lo dice más y cuándo apareció
> por primera vez?»
>
> *El agente usa* `term_counter` (`terms="reforma da previdência", countries=["BR"]`).

```text
13.386 apariciones · 8.118 intervenciones · 1.862 sesiones · 920 oradores
por sexo, por millón de palabras:  diputadas 78,5 · diputados 64,1
partidos con más apariciones:       PT 4.448 (94,8 por millón) · PSOL 1.156 (170,6) · PCdoB 839 (112,6)
primera aparición: 2003-01-01 · última: 2025-12-16
```

**Cómo leerlo.** El PT es el partido que más veces lo dice, pero el PSOL, más pequeño, lo dice casi el doble por cada
millón de sus palabras. Las tasas por millón corrigen el tamaño de cada grupo. Para ver la serie año a año, por
legislatura o por partido, está `term_frequency` (`by="year"`, `"party"`, `"legislature"`…).

---

## 3. Quién habla

> **Pide:** «¿Las diputadas españolas hablan en proporción a sus escaños? Por legislatura desde 2004, sin contar
> la presidencia.»
>
> *El agente usa* `share_of_voice` (`countries=["ES"], by="sex", per="legislature", exclude_chair=true`).

| legislatura | años | voz de las diputadas | peso en el padrón | voz / peso |
|---|---|---:|---:|---:|
| VIII | 2004–2008 | 25,7 % | 35,8 % | 0,72 |
| X | 2011–2015 | 29,5 % | 39,3 % | 0,75 |
| XII | 2016–2019 | 32,5 % | 41,3 % | 0,79 |
| XIV | 2020–2023 | 38,4 % | 42,5 % | 0,90 |
| XV | 2023–2025 | 37,9 % | 44,4 % | 0,85 |

**Cómo leerlo.** «Voz» es la parte de las palabras pronunciadas por diputadas; «peso», su parte en el padrón de la
legislatura. Un cociente de 1 sería hablar en proporción a los escaños. La brecha se ha reducido, pero no ha
desaparecido. La voz se mide sobre los diputados vinculados: ministros y otras voces sin escaño quedan fuera del
denominador, y el resultado indica cuánto habla deja dentro.

> [!WARNING]
> **La presidencia.** Quien preside la sesión pronuncia muchos turnos de trámite («tiene la palabra…»). En las
> comparaciones entre grupos puede dominar el resultado: usa `exclude_chair=true` en `share_of_voice` y
> `distinctive_words`.

> [!NOTE]
> **Sexo, partido y distrito** vienen del padrón de diputados y están vacíos cuando el orador no se pudo vincular
> (ministros, secretarios, voces colectivas). La vinculación y sus límites cambian entre países: consúltalos con
> `coverage` y `get_documentation(..., "known_limitations")` antes de comparar.

---

## 4. Qué distingue a dos grupos

> **Pide:** «¿Qué palabras distinguen al PT del PL en la legislatura actual (2023–2025), sin la presidencia?»
>
> *El agente usa* `distinctive_words` (`field="party", a="PT", b="PL", countries=["BR"], date_from="2023-01-01",
> date_to="2025-12-31", exclude_chair=true, top=15`).

| más propias del PT | z | más propias del PL | z |
|---|---:|---|---:|
| renda | 33,5 | não | −44,4 |
| trabalhadores | 33,3 | eu | −41,9 |
| educação | 32,3 | esquerda | −40,3 |
| políticas | 32,2 | deus | −33,6 |
| programa | 32,1 | stf | −29,1 |
| deputadas | 30,2 | oposição | −27,4 |
| fome | 26,3 | desgoverno | −26,5 |
| desenvolvimento | 26,2 | minoria | −25,5 |

**Cómo leerlo.** El método es el *log-odds* ponderado con un prior de Dirichlet (Monroe, Colaresi y Quinn 2008): da
peso a las diferencias que no se deben al azar y no premia las palabras raras. Un |z| mayor que 1,96 es significativo;
con corpus de este tamaño casi todas lo superan con creces, así que lo que importa es el orden. Aquí, el partido del
gobierno habla de políticas (renta, educación, hambre). La oposición habla en primera persona, con negaciones, de sus
adversarios (la izquierda, el STF) y del «desgoverno». Las palabras funcionales no se quitan: también son estilo.

Los grupos pueden ser partidos, sexo (`"F"`/`"M"`), periodos (`"2003-2010"` frente a `"2019-2022"`), países, un
diputado (`id_dep`) o una biblioteca frente al resto (sección 5).

---

## 5. Una biblioteca para un asunto

Una **biblioteca** es un subconjunto de intervenciones con nombre: un asunto, un periodo, un grupo, de uno o varios
países. Se guarda, y todas las herramientas de análisis aceptan `library=` para trabajar dentro de ella. El resto
del tutorial sigue un caso: la reforma de la Previdência en Brasil.

> **Pide:** «Crea una biblioteca "tutorial_previdencia" con las intervenciones de la Câmara que discuten la reforma
> de la Previdência entre la PEC 287 (diciembre de 2016) y su promulgación (noviembre de 2019): las que usen al menos
> dos veces "reforma da previdência", "previdência social" o "aposentadoria*". Sin la presidencia.»
>
> *El agente usa* `library_create` (`name="tutorial_previdencia", countries=["BR"],
> terms="reforma da previdência+previdência social+aposentadoria*", min_occurrences=2, date_from="2016-12-01",
> date_to="2019-11-30", exclude_chair=true`).

```text
tutorial_previdencia · BR
3.126 intervenciones · 505 sesiones · 466 oradores · 1.716.163 palabras
2016: 127 · 2017: 1.283 · 2018: 243 · 2019: 1.473
vinculadas: 98,6 % · diputadas: 15,2 % de los oradores con sexo conocido · turnos largos: 0,7 %
```

**Cómo leerlo.** `min_occurrences=2` deja las intervenciones que **discuten** el asunto y no las que lo mencionan de
pasada. Los años reflejan las dos tramitaciones (2017 y 2019). `library_describe` vuelve a dar este retrato cuando se
necesite.

Las bibliotecas también se pueden hacer con varios países a la vez (con las formas de cada idioma), alinear en torno a
un acontecimiento (`event_dates` y `days_before`/`days_after`), retocar a mano (`library_edit`, con notas y
etiquetas) y combinar (`library_combine`: unión, intersección, diferencia).

> **Pide:** «¿Qué vocabulario distingue a esa biblioteca del resto de la Câmara en el mismo periodo?»
>
> *El agente usa* `distinctive_words` (`field="library", a="tutorial_previdencia", countries=["BR"],
> date_from="2016-12-01", date_to="2019-11-30", exclude_chair=true`).

```text
previdência (z 185,5) · reforma (174,7) · aposentadoria (87,4) · social (60,4) · idade (58,8)
trabalhadores (58,6) · contribuição (58,0) · anos (57,5) · aposentar …
```

Sirve para comprobar que la biblioteca recoge el asunto que se buscaba.

---

## 6. Leer en contexto

Contar no basta: hay que leer.

> **Pide:** «Muéstrame seis ejemplos de "regra de transição" en la biblioteca.»
>
> *El agente usa* `kwic` (`pattern="regra de transição", library="tutorial_previdencia", n=6, width=80`).

```text
68 intervenciones contienen la frase; muestra aleatoria de 6 (reproducible: seed=1)
2017-05-10 PTB   … a proposta do Governo previa [regra de transição]. O Relator retirou essa …
2019-04-15 PT    … porque quer estabelecer outra [regra de transição] para quem já está numa …
2017-10-19 PT    … idade mínima, tempo de contribuição mínima e [regra de transição] — esse é o cerne …
2019-04-17 PDT   … que não há [regra de transição] colocada na PEC 06/19. Sai da regra antiga …
2019-03-12 PODE  … vamos garantir uma [regra de transição] justa, que trate iguais como iguais …
```

**Cómo leerlo.** Cada línea lleva la fecha, el partido y el identificador de la intervención (`id_int`). Con él,
`get_intervention` devuelve el texto completo (y, si se pide, los turnos de alrededor), y `get_session` el orden
de la sesión entera. `search_text` busca de lo más reciente a lo más antiguo, con filtros de partido, sexo o
diputado.

> **Pide:** «¿Con qué palabras aparece "privilégio" (y sus formas) en la biblioteca?»
>
> *El agente usa* `collocations` (`pattern="privilégio*", library="tutorial_previdencia", top=15`).

```text
421 intervenciones · 776 apariciones
combater (G² 876,8) · combate (378,5) · acabar (240,9) · combatendo (82,9) · cortar (81,6)
atacar (78,1) · nenhum (71,7) · ataca (63,9) · tira (48,9) · mexe (48,0)
```

**Cómo leerlo.** Son las palabras que aparecen a ±5 palabras del término más de lo que aparecen en el resto de esas
mismas intervenciones (G² de Dunning; por encima de 10,8, p < 0,001). Los privilegios son algo que se «combate», se
«corta» o se «ataca». Pero las colocaciones no dicen quién habla ni con qué intención. «Combater privilégios» era el
lema del gobierno, y en esta biblioteca lo pronuncia sobre todo la izquierda: 114 de las 140 intervenciones con esa
construcción. Para saber si lo asume o lo discute hay que leer los ejemplos con `kwic` y repetir el análisis con
`party=`.

---

## 7. Tres redes, tres preguntas

El servidor construye tres redes distintas que **nunca se mezclan**, porque responden a preguntas distintas:

| herramienta | nodos | un vínculo significa | pregunta |
|---|---|---|---|
| `cooccurrence_network` | palabras y expresiones de la biblioteca | aparecen juntas más de lo esperable | de qué se habla: temas |
| `comention_network` | actores que tú defines: personas e instituciones | se mencionan en la misma intervención | qué actores se discuten juntos, y quién |
| `mention_network` | personas: oradores, diputados, actores externos | A nombra a B en el pleno | quién habla de quién |

Las tres escriben en una carpeta (ruta absoluta) una página interactiva, con tablas, CSV, JSON y un resumen. Las
páginas tienen tres disposiciones (fuerzas, grupos separados y anillos), hasta 30 colores, nodos de tamaño regulable
y un panel lateral que se puede ocultar.

### 7.1 Palabras y temas

> **Pide:** «Haz la red de palabras de la biblioteca y agrúpala en temas. Quita los nombres de personas. Guarda las
> páginas en ~/previdencia/redes.»
>
> *El agente usa* `cooccurrence_network` (`library="tutorial_previdencia", exclude=[...nombres...],
> layout="clusters", output_dir="..."`).

![Red de palabras de la biblioteca, en grupos separados](img/red_palabras.png)

| tema | términos centrales | intervenciones | partidos que más lo usan (por 1.000 palabras) |
|---|---|---:|---|
| Reglas de acceso | tempo de contribuição, idade mínima, anos de contribuição, homens, mulheres | 83 % | PDT 16,2 · PSB 15,9 · PT 14,8 |
| Lectura de la oposición | destruição da previdência social, golpe, governo ilegítimo, reforma trabalhista, direitos | 84 % | PT 15,5 · PCdoB 13,4 · PSOL 12,1 |
| Cuentas y regímenes | déficit, regime próprio, regime geral, fiscal, gastos, benefícios | 76 % | PTB 11,5 · PSD 9,5 · NOVO 9,2 |
| Privilegios y desigualdad | combater privilégios, lucros e dividendos, grandes fortunas, salário mínimo, abono salarial | 63 % | PDT 9,0 · PSOL 8,7 · PSB 8,1 |
| BPC y aposentadoria rural | benefício de prestação continuada, BPC, aposentadoria rural, idosos | 22 % | PTB 2,5 · PRB 1,6 · PSD 1,5 |
| Capitalización | sistema de capitalização, Chile, regime de capitalização, bancos | 16 % | PDT 1,3 · PSB 1,1 · NOVO 1,1 |

Además salen el registro común del pleno («vai», «governo», «agora»: el 98 % de las intervenciones, que no es un tema)
y dos temas de trámite (la votación y la comisión especial).

**Cómo se hace.** Es el método del Diarios Explorer, portado y comprobado contra su código:

- **Vocabulario:** las 250 palabras y expresiones más características de la biblioteca frente al resto del corpus del
  país (G² con signo), sin cifras ni palabras vacías. Las expresiones del corpus («regra de transição»,
  «lucros e dividendos») son un solo nodo.
- **Vínculos:** dos términos se unen si aparecen en la misma intervención más de lo esperable (G² ≥ 10,83) y el vínculo
  está entre los 10 más fuertes de alguno de los dos.
- **Temas:** comunidades de Leiden con tres términos o más, ordenadas por lo característicos que son de la biblioteca.

**Cómo leerlo.** La tasa por 1.000 palabras compara partidos de tamaño distinto: el PT usa el vocabulario de «la
destrucción de la Previdência» 15,5 veces por cada 1.000 de sus palabras; el NOVO, 3,7. Cada tema propone las
intervenciones que conviene leer primero (`read_first`). Para temas más finos, sube la resolución (`resolution=1.6`);
para centrarte en otra cosa, excluye términos (`exclude`). La unidad puede ser la intervención o fragmentos de 20
palabras (`unit="fragment"`).

### 7.2 Actores mencionados juntos

> **Pide:** «¿Qué instituciones se mencionan juntas en esos debates, y cuáles nombran más la izquierda o la derecha?
> Usa INSS, Congresso Nacional, STF, TCU, Ministério da Fazenda o da Economia, Banco Central, centrais sindicais,
> bancos, Forças Armadas y el Judiciário. Izquierda: PT, PSOL, PCdoB, PDT, PSB, REDE; derecha: PSL, PL, PR, PP, DEM,
> PSC, PRB, Republicanos, NOVO, PTB, Patriota.»
>
> *El agente usa* `comention_network` (`library="tutorial_previdencia", entities=[{name, type: "institucion",
> pattern}...], groups={"esquerda": [...], "direita": [...]}, min_co=8, layout="clusters"`).

![Instituciones mencionadas juntas, en tres comunidades](img/red_actores.png)

```text
10 actores · 10 vínculos · 3 comunidades
  C1: Bancos · Centrais sindicais · Banco Central
  C2: Congresso Nacional · STF · Tribunais e Judiciário · Forças Armadas
  C3: INSS · TCU · Ministério da Fazenda / Economia
sesgo (+ izquierda, − derecha): Centrais sindicais +1,00 · Bancos +0,56 · Tribunais e Judiciário −0,29
avisos: «bancos», «militares», «tribunais» y «economia» se escriben casi siempre en minúscula: también son palabras comunes
```

**Cómo leerlo.**

- **co** cuenta las intervenciones que nombran a los dos actores (volumen); **NPMI** mide cuánto más de lo esperable
  aparecen juntos (afinidad, de −1 a 1). Hay que leerlos por separado: dos actores muy frecuentes tienen un co alto y
  un NPMI cercano a 0.
- **El sesgo** compara la proporción de intervenciones de cada grupo que nombra al actor. Entre izquierda y derecha,
  a las centrales sindicales solo las nombra la izquierda, y a los bancos, sobre todo ella.
- **Los avisos** señalan patrones ambiguos: conviene leer los ejemplos de cada actor (clic en el nodo) antes de
  interpretar.

> [!IMPORTANT]
> **Solo actores.** `comention_network` acepta personas e instituciones (`type: "persona"` o `"institucion"`). Las
> palabras, ideas y conceptos van en `cooccurrence_network`: si se le pasa un `concepto`, lo rechaza. Sin `entities`,
> propone candidatos (nombres propios y siglas de una muestra) y no construye nada hasta que los confirmes. Los
> patrones son expresiones regulares RE2 sobre texto en minúsculas y sin tildes (sin *look-arounds*).

> [!NOTE]
> **El umbral automático** de co es `max(5, N/120)`: 26 en una biblioteca de 3.126 intervenciones. En bibliotecas
> pequeñas deja fuera a los actores menos nombrados; aquí se bajó a 8.

### 7.3 Quién nombra a quién

> **Pide:** «En esos debates, ¿quién nombra a quién? Agrupa por izquierda y derecha.»
>
> *El agente usa* `mention_network` (`library="tutorial_previdencia", target_scope="speakers", groups={...},
> min_mentions=3, layout="rings"`).

![Menciones entre grupos por cada 100 intervenciones](img/menciones_grupos.png)

**Cómo leerlo.** La izquierda nombra sobre todo a la propia izquierda (4,6 menciones por cada 100 de sus
intervenciones, 96 en total) y bastante menos a la derecha (1,8). La derecha reparte sus menciones (1,5 a cada lado).
El índice E-I lo resume: −0,27 en la izquierda (habla de los suyos), +0,27 en la derecha (habla de los otros).

La página dibuja también la red de personas, con flechas de quien nombra a quien es nombrado, en anillos (los más
conectados en el centro) o en grupos. Los nombres salen del padrón de diputados en ejercicio ese día: por el nombre
completo, o por el apellido tras un título parlamentario. Los homónimos se resuelven por el género del título o el
partido escrito junto al nombre; si no, se listan aparte y nunca se adivinan. `validation_sample` escribe una muestra
para revisar a mano, y `external_actors` añade personas de fuera del pleno (ministros, jueces) por su cargo o sus
alias.

---

## 8. Reproducir, exportar y citar

> **Pide:** «¿Cuántas intervenciones de la biblioteca hay por año? Hazlo con SQL.»
>
> *El agente usa* `query_sql` (una consulta de solo lectura en DuckDB; `describe_data` da el esquema).

```sql
SELECT year(i.date) AS ano, count(*) AS intervencoes
FROM interventions i
WHERE i.id_int IN (SELECT it.id_int FROM lib.library_items it
                   JOIN lib.libraries l ON l.id = it.library_id
                   WHERE l.name = 'tutorial_previdencia')
GROUP BY 1 ORDER BY 1
```

```text
2016: 127 · 2017: 1.283 · 2018: 243 · 2019: 1.473
```

> **Pide:** «Guarda esa tabla en CSV para seguir en R.»
>
> *El agente usa* `export_result` (`sql=..., path="~/previdencia/por_ano.csv"`). También admite Parquet.

> **Pide:** «Exporta la biblioteca para abrirla en el Diarios Explorer.»
>
> *El agente usa* `library_export` (`name="tutorial_previdencia", folder="..."`): un archivo `.2replib` por país y un
> índice. Cada `.2replib` se importa en el explorador con el CSV de su propio país cargado.

> **Pide:** «Escribe una nota de métodos con todo lo que hemos hecho.»
>
> *El agente usa* `query_log` (`methods_path="~/previdencia/metodos.md"`).

```markdown
# Data and queries
Data: ParlaIbero (Harvard Dataverse, CC BY 4.0), one dataset per country:
- Brazil: https://doi.org/10.7910/DVN/VTXNW3, version 2.0
…
Analyses run with parlaibero-mcp:
- 2026-10-23T14:56:02 · `term_counter` · {"terms": "reforma da previdência", "countries": ["BR"], …}
…
```

> **Pide:** «¿Cómo cito los datos de Brasil?»
>
> *El agente usa* `how_to_cite` (`country="BR"`).

```text
Rodrigues-Silveira, Rodrigo, 2026, "ParlaIbero-BR: Parliamentary Speeches from Brazil (2003-2025)",
https://doi.org/10.7910/DVN/VTXNW3, Harvard Dataverse, V2
```

> [!NOTE]
> **Versiones.** Los identificadores (`id_int`, `id_session`) son estables dentro de una versión publicada, no entre
> versiones. Cita cada conjunto con su versión. Si se descarga una edición nueva, `library_rebuild` reconstruye las
> bibliotecas sobre ella.

---

## 9. El caso completo, en ocho peticiones

1. «¿Cómo de completa es la base de Brasil entre 2016 y 2019?» (`coverage`)
2. «¿Cuándo y cuánto se habló de "reforma da previdência"?» (`ngram_viewer`, `term_counter`)
3. «Crea una biblioteca con las intervenciones que discuten la reforma…» (`library_create`)
4. «¿Qué vocabulario la distingue del resto del pleno?» (`distinctive_words`, `field="library"`)
5. «Muéstrame ejemplos de "regra de transição" y con qué palabras aparece "privilégio".» (`kwic`, `collocations`)
6. «Haz la red de palabras y sus temas.» (`cooccurrence_network`)
7. «¿Qué instituciones se mencionan juntas y quién nombra a quién?» (`comention_network`, `mention_network`)
8. «Escribe la nota de métodos y dime cómo citar los datos.» (`query_log`, `how_to_cite`)

---

## 10. Resumen de herramientas

| para… | herramientas |
|---|---|
| ver qué hay y descargarlo | `list_countries`, `download_country`, `import_from_folder` |
| conocer los datos | `get_documentation`, `describe_data`, `coverage` |
| contar palabras | `ngram_viewer`, `term_counter`, `term_frequency` |
| comparar grupos | `share_of_voice`, `distinctive_words` |
| leer | `kwic`, `collocations`, `search_text`, `get_intervention`, `get_session` |
| trabajar sobre un asunto | `library_create`, `library_describe`, `library_edit`, `library_combine`, `library_rebuild`, `library_delete`, `library_export`, `library_import` |
| redes | `cooccurrence_network` (palabras y temas), `comention_network` (actores), `mention_network` (quién nombra a quién) |
| reproducir y citar | `query_sql`, `export_result`, `query_log`, `how_to_cite` |

El detalle técnico de cada herramienta está en el [README del servidor](../../mcp/README.md), y el método de las
redes, en el recurso `parlaibero://methods/networks` (también en
[`methods_networks.md`](../../mcp/src/parlaibero_mcp/methods_networks.md)).
