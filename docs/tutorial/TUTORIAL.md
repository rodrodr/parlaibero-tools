# Dieciséis parlamentos, un agente

<!-- eyebrow: parlaibero-tools · tutorial -->

*[English version](TUTORIAL.en.md)*

Los plenos de dieciséis parlamentos iberoamericanos: casi diez millones de intervenciones desde 1976, vinculadas con el
registro de diputados. parlaibero-tools ofrece dos herramientas para el mismo corpus: un servidor MCP para consultarlo
desde un agente de IA y 21 skills de Claude Code para construirlo.

<!-- doors -->

### Consultar los datos

`parlaibero-mcp` · un servidor MCP con 31 herramientas

Tu agente (Claude, ChatGPT de escritorio, Codex, Cursor…) descarga los conjuntos de Harvard Dataverse y después busca,
cuenta y lee los plenos en tu ordenador. No hace falta programar: se pide con palabras. Hace falta
[uv](https://docs.astral.sh/uv/getting-started/installation/); en Claude Code:

```bash
claude mcp add parlaibero -s user -- uvx parlaibero-mcp
```

En Claude Desktop, Cursor, Gemini CLI y la mayoría de clientes, este bloque en su configuración (las demás variantes
están en el [README](../../mcp/README.md)):

```json
{
  "mcpServers": {
    "parlaibero": {
      "command": "uvx",
      "args": ["parlaibero-mcp"]
    }
  }
}
```

- [Cuatro estudios](#1-cuatro-estudios)
- [Una biblioteca desde cero](es/bibliotecas.md)
- [Las 31 herramientas](es/referencia.md)

### Construir un corpus

`diaries-*` · 21 skills de Claude Code

La tubería que convirtió los diarios de sesiones en esos conjuntos: del PDF escaneado o el HTML a la matriz de 16
columnas, con un sistema de confianza que te deja los casos dudosos y un registro de cada decisión. Para una cámara, un
país o un periodo que no están, o para auditar cómo se hizo uno.

```bash
git clone https://github.com/rodrodr/parlaibero-tools.git
cd parlaibero-tools
bash install_skills.sh
```

Y en la carpeta del proyecto que tendrá los datos:

```bash
bash ~/.claude/skills/diaries-lib/install.sh
```

- [Construir un corpus](es/construir.md)
- [Un país desde cero](es/pais.md)
- [Documentación técnica, solo en español](../../skills/diaries-lib/docs/diaries_index.html)

<!-- /doors -->

## 1. Cuatro estudios

Cada estudio muestra parlaibero-mcp en uso: una cadena de peticiones con sus resultados reales y las comprobaciones
que, más de una vez, cambian la conclusión. El agente elige la herramienta, la ejecuta en tu ordenador y lee el
resultado.

<!-- studies -->

Cada estudio es una página con el mismo formato. Una petición dice lo que se escribe al agente; debajo, la
herramienta que usa con sus parámetros principales, y después el resultado: tablas, gráficos o páginas interactivas.
Los resultados son reales, se obtuvieron con el script [`casos.py`](casos.py) y cualquiera puede reproducirlos (los
nombres de persona que se excluyen de las listas de palabras se guardan aparte, fuera del repositorio). La
respuesta que redacte tu agente cambiará; los datos, no. Al final de cada estudio hay una petición que lo pide todo de
una vez.

> **Pide:** lo que se escribe al agente, con tus palabras.
>
> *El agente usa* `la_herramienta` (`parámetro=valor`) y lee el resultado.

Si nunca has hecho una biblioteca, empieza por la guía [Una biblioteca desde cero](es/bibliotecas.md). Construye una
paso a paso, de la pregunta a la lista de comprobación: cuándo hace falta, cómo se prueban las palabras y el umbral,
cómo se lee una muestra en cada cámara y qué se hace cuando la primera definición falla.

## 2. Qué hay en la base

> **Pide:** «¿Qué parlamentos tiene ParlaIbero y cuáles tengo descargados?»
>
> *El agente usa* `list_countries`.

<!-- table:ini_corpus -->
| País | Años | Sesiones | Intervenciones de discurso | Versión | DOI |
|---|---|---:|---:|---|---|
| Argentina | 1983–2025 | 1.086 | 256.636 | 2.0 | [10.7910/DVN/IVNYID](https://doi.org/10.7910/DVN/IVNYID) |
| Brasil | 2003–2025 | 7.731 | 1.649.698 | 2.0 | [10.7910/DVN/VTXNW3](https://doi.org/10.7910/DVN/VTXNW3) |
| Chile | 1990–2025 | 4.336 | 556.679 | 2.0 | [10.7910/DVN/IKBNRL](https://doi.org/10.7910/DVN/IKBNRL) |
| Colombia | 2000–2025 | 1.608 | 463.201 | 2.0 | [10.7910/DVN/TYYERX](https://doi.org/10.7910/DVN/TYYERX) |
| Costa Rica | 1994–2025 | 5.343 | 375.730 | 2.0 | [10.7910/DVN/W6UAHQ](https://doi.org/10.7910/DVN/W6UAHQ) |
| Rep. Dominicana | 2001–2025 | 2.225 | 101.381 | 2.0 | [10.7910/DVN/DZKXUG](https://doi.org/10.7910/DVN/DZKXUG) |
| Ecuador | 1979–2025 | 6.105 | 1.280.822 | 2.0 | [10.7910/DVN/M2QJN6](https://doi.org/10.7910/DVN/M2QJN6) |
| España | 1977–2025 | 3.559 | 558.940 | 2.0 | [10.7910/DVN/OKHGAB](https://doi.org/10.7910/DVN/OKHGAB) |
| Guatemala | 2000–2026 | 2.039 | 251.720 | 2.0 | [10.7910/DVN/NH5TTC](https://doi.org/10.7910/DVN/NH5TTC) |
| México | 1988–2025 | 2.537 | 630.937 | 2.0 | [10.7910/DVN/0IS1YE](https://doi.org/10.7910/DVN/0IS1YE) |
| Panamá | 1996–2025 | 3.638 | 508.324 | 2.0 | [10.7910/DVN/Y8FUSX](https://doi.org/10.7910/DVN/Y8FUSX) |
| Perú | 1995–2025 | 3.061 | 849.499 | 1.0 | [10.7910/DVN/7MK94V](https://doi.org/10.7910/DVN/7MK94V) |
| Portugal | 1976–2025 | 4.939 | 1.554.381 | 2.0 | [10.7910/DVN/VRPUFU](https://doi.org/10.7910/DVN/VRPUFU) |
| Paraguay | 1988–2025 | 1.275 | 360.201 | 2.0 | [10.7910/DVN/PDX8GA](https://doi.org/10.7910/DVN/PDX8GA) |
| El Salvador | 2018–2025 | 423 | 48.654 | 2.0 | [10.7910/DVN/MUJU6A](https://doi.org/10.7910/DVN/MUJU6A) |
| Uruguay | 1985–2025 | 2.813 | 421.284 | 2.0 | [10.7910/DVN/KI1AOC](https://doi.org/10.7910/DVN/KI1AOC) |
| **Total** |  | 52.718 | 9.868.087 |  |  |
<!-- /table -->

Cada país es un conjunto de datos de Harvard Dataverse con su DOI y su versión, y se descarga una vez (entre 0,5 y
1,5 GB, unos minutos) con `download_country`; los más grandes pueden descargarse desde la terminal con
`parlaibero-mcp download BR`. Los datos quedan en una base DuckDB local, en `~/.parlaibero`, y todo se calcula en tu
ordenador. Cada fila es una intervención, enlazada cuando se puede con el registro de diputados, que aporta el sexo,
el partido y la circunscripción.

Antes de interpretar una tendencia hay que saber cuánto texto la sostiene, y de qué tipo.

> **Pide:** «¿Qué base tienen Argentina, España, México y Uruguay en 2022 y 2023?»
>
> *El agente usa* `coverage` (`countries=["AR","ES","MX","UY"]`, `by="year"`, `date_from="2022-01-01"`,
> `date_to="2023-12-31"`).

<!-- table:ini_cobertura -->
| País | Palabras al año (mediana) | Palabras en turnos de más de 10.000 (%) | Discurso vinculado (%) |
|---|---:|---:|---:|
| Argentina | 1.222.879 | 19,3 | 90,8 |
| España | 3.199.097 | 0,8 | 96,9 |
| México | 5.847.478 | 26,4 | 96,2 |
| Uruguay | 3.742.281 | 32,0 | 96,4 |
<!-- /table -->

Algunas actas no separan los documentos leídos en voz alta (informes, proyectos, listas) del discurso. En Uruguay, el
32,0 % de las palabras de esos años está en turnos de más de 10.000 palabras; en México, el 26,4 %; en Argentina, el
19,3 %; en España, el 0,8 %. Una comparación de palabras entre estos países, sin `max_turn_words=10000`, compara sobre
todo documentos.

> [!TIP]
> `get_documentation` sirve los documentos depositados con cada conjunto (limitaciones conocidas, información del
> corpus, diccionario de datos), en español, inglés y portugués. Pídele al agente que lea las limitaciones de un país
> antes de compararlo.

## 3. Cómo pedir

El agente traduce la petición en llamadas, así que cuanto más precisa la pregunta, mejor la elección. Conviene decir
qué países y qué periodo, qué unidad (palabras, turnos, intervenciones, sesiones) y qué grupos, y pedir las
comprobaciones: la base antes de comparar, la lectura antes de interpretar, una tasa en lugar de un recuento. Un
estudio suele seguir este camino:

1. ¿Qué hay y con qué base? (`list_countries`, `coverage`, `get_documentation`)
2. ¿Cuánto se dice y desde cuándo? (`term_counter`, `ngram_viewer`)
3. ¿Dónde se concentra? (`term_frequency`, `get_session`)
4. ¿Qué se dice exactamente? (`kwic`, `collocations`, `search_text`, `get_intervention`)
5. ¿Quién habla, y qué distingue a los grupos? (`share_of_voice`, `distinctive_words`)
6. Un subconjunto para estudiarlo a fondo (`library_create`, `library_describe`), paso a paso en la [guía de
   bibliotecas](es/bibliotecas.md)
7. Temas, actores y menciones (`cooccurrence_network`, `comention_network`, `mention_network`)
8. Lo que ninguna herramienta hace (`query_sql`)
9. Cerrar el estudio: exportar, registrar y citar (`export_result`, `library_export`, `query_log`, `how_to_cite`)

Puedes pedir un estudio entero de una vez o paso a paso. Paso a paso cuesta más, pero permite mirar cada resultado
antes del siguiente, que es donde aparecen los problemas. La [página de herramientas](es/referencia.md) describe las
31, con sus parámetros y un ejemplo de petición.

## 4. Antes de creer un resultado

Los cuatro estudios y la guía de bibliotecas encuentran quince trampas. Ninguna es un error del agente: son propiedades de las actas, de los
registros y de las medidas, y cada una tiene su comprobación.

- **El corpus empieza tarde.** El primer uso es el del corpus, no el del país. [Feminicidio, § 1](es/feminicidio.md#1-cuántas-veces-y-desde-cuándo)
- **La media móvil desplaza los picos.** Lee el recuento de cada año antes de fechar uno. [Feminicidio, § 2](es/feminicidio.md#2-la-curva-de-cada-parlamento)
- **Un término no se traduce.** España y Portugal nombran la violencia contra las mujeres de otra forma. [Feminicidio, § 5](es/feminicidio.md#5-españa-y-portugal-otra-palabra-para-lo-mismo)
- **Prefijos y fechas mal puestas.** `covid*` encuentra *Covidien*; una sesión puede estar mal fechada. [Pandemia, § 1](es/pandemia.md#1-el-primer-uso-en-cada-pleno)
- **La cámara no se reunía.** Un primer uso tardío puede ser una primera sesión. [Pandemia, § 1](es/pandemia.md#1-el-primer-uso-en-cada-pleno)
- **Recuentos y proporciones.** La cámara que más dice una palabra puede ser la que menos atención le presta. [Pandemia, § 2](es/pandemia.md#2-la-atención-semana-a-semana)
- **Documentos leídos.** En algunas cámaras, un tercio de las palabras son documentos. [§ 2 de esta página](#2-qué-hay-en-la-base)
- **Una línea de base.** Un cambio se mide contra el mismo grupo en el mismo periodo, no contra 1. [Pandemia, § 5](es/pandemia.md#5-quién-habló-de-la-pandemia)
- **La Mesa habla desde el escaño.** Las fórmulas de votación cuentan como voz. [Voz, § 3](es/voz.md#3-méxico-la-mesa-habla-desde-el-escaño)
- **Palabras o turnos.** La misma voz cambia según la unidad. [Voz, § 2](es/voz.md#2-desde-2021-palabras-y-turnos)
- **La lengua antes que el tema.** Las listas de palabras comparan lenguas y estilos. [Voz, § 4](es/voz.md#4-españa-y-sus-lenguas) y [pandemia, § 4](es/pandemia.md#4-de-qué-habló-cada-cámara)
- **Etiquetas, fronteras y huecos del registro.** Federaciones de un mismo partido, el día en que cambia la legislatura, años incompletos. [Voz, § 5](es/voz.md#5-españa-por-partido-etiquetas-y-fronteras)
- **Contar un marco no es adoptarlo, y un nombre no es una persona.** [Marcos, § 4](es/marcos.md#4-privilégios-un-marco-dos-usos) y [§ 6](es/marcos.md#6-quién-nombra-a-quién-el-homónimo)
- **Una definición que vale en tres cámaras falla en la cuarta.** Lee una muestra en cada cámara por separado. [Bibliotecas, § 5](es/bibliotecas.md#5-describir-y-leer-una-muestra-en-cada-cámara)
- **Precisa no es completa.** Una definición sin ruido puede dejar fuera dos tercios del tema: la cobertura se mide leyendo lo que queda fuera. [Bibliotecas, § 9](es/bibliotecas.md#9-más-allá-de-las-palabras-clave)

## 5. Cerrar un estudio

> **Pide:** «Guarda la tabla semanal de la pandemia en Parquet, para seguir en R.»
>
> *El agente usa* `export_result` (`sql=…`, `path=…/pandemia_semanal.parquet`, `format="parquet"`). Escribe solo en la
> carpeta de destino que le indiques.

> **Pide:** «Exporta la biblioteca *pandemia* para abrirla en el Diarios Explorer.»
>
> *El agente usa* `library_export` (`name="pandemia"`, `folder=…`), que escribe un archivo por país, porque el
> explorador abre un país cada vez, y un índice con el que `library_import` reconstruye la biblioteca comparada.

> **Pide:** «Escribe el apéndice de métodos de lo que hemos hecho.»
>
> *El agente usa* `query_log` (`methods_path=…/metodos.md`), que lista cada análisis con sus parámetros y la versión
> de cada conjunto de datos.

> **Pide:** «Dame la cita de los conjuntos que hemos usado.»
>
> *El agente usa* `how_to_cite`, un país cada vez. Cada conjunto se cita con su DOI y su versión: los identificadores
> de las filas son estables dentro de una versión, no entre versiones.

> [!NOTE]
> Los ejemplos de este tutorial no nombran a personas: las citas omiten a quien habla, las listas de palabras dejan
> fuera los nombres propios y las redes describen a los actores por su cargo. Si publicas resultados del agente, haz
> lo mismo, sobre todo cuando las actas recogen nombres de particulares o de víctimas.
