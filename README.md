# ParlaIbero · herramientas

<img src="assets/logo_aei.jpg" alt="Ministerio de Ciencia, Innovación y Universidades · Cofinanciado por la Unión Europea · Agencia Estatal de Investigación" width="560">

Proyecto PID2022-141706NB-C22 financiado por MICIU/AEI/10.13039/501100011033 y por FEDER, UE.

---

**ParlaIbero** reúne las intervenciones en el pleno de las cámaras bajas o únicas de 16 países:
Argentina, Brasil, Chile, Colombia, Costa Rica, Ecuador, El Salvador, España, Guatemala, México,
Panamá, Paraguay, Perú, Portugal, República Dominicana y Uruguay. Son 10.091.060 intervenciones en
52.718 sesiones, cada una vinculada a un padrón de diputados. Hay un conjunto de datos con su DOI
por país en [Harvard Dataverse](https://dataverse.harvard.edu/dataverse/parlaibero), bajo licencia
CC BY 4.0.

Este repositorio ofrece dos cosas:

| | qué es | para quién |
|---|---|---|
| [`mcp/`](mcp/) | **Servidor MCP** que descarga los datos de Dataverse y permite consultarlos desde Claude Code, Claude Desktop, Cursor, Codex, Gemini CLI o cualquier agente compatible con MCP | quien quiere **usar** los datos |
| [`skills/`](skills/) | Los **21 skills `diaries-*`** y su código (`diaries-lib`): la tubería que convirtió los diarios de sesiones (PDF y HTML) en esas matrices | quien quiere **reproducir** el corpus o **construir** uno nuevo |

*[English below](#english).*

## 1 · Servidor MCP: consultar ParlaIbero desde un agente

Requisito: [uv](https://docs.astral.sh/uv/getting-started/installation/) (instala Python si hace falta).

**Claude Code**

```bash
claude mcp add parlaibero -s user -- uvx --from "git+https://github.com/rodrodr/parlaibero-tools#subdirectory=mcp" parlaibero-mcp
```

**Claude Desktop, Cursor, Gemini CLI y otros** (bloque `mcpServers` de su configuración):

```json
{
  "mcpServers": {
    "parlaibero": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/rodrodr/parlaibero-tools#subdirectory=mcp", "parlaibero-mcp"]
    }
  }
}
```

Después basta con pedirlo en lenguaje natural: *«descarga El Salvador y dime qué partidos hablan más
de seguridad desde 2019»*, *«¿cuánto se menciona la corrupción en el Congreso peruano por
década?»*, *«compara el peso de las diputadas en el habla de España y Portugal»*.

| herramienta | qué hace |
|---|---|
| `list_countries` · `download_country` | los 16 conjuntos, qué hay descargado, y la descarga de Dataverse con verificación MD5 |
| `get_documentation` · `describe_data` | README, diccionario, limitaciones conocidas… (`en`, `es`, `pt`) y el esquema de las tablas |
| `coverage` | **la base antes de leer una tendencia**: sesiones, palabras, vinculación, años que faltan y años con base escasa |
| `ngram_viewer` | visor **tipo Google Books Ngram**: varias palabras o frases a la vez, por millón de palabras, con suavizado y una línea por país si se quiere; escribe el gráfico en **SVG** (para artículos y diapositivas) o **HTML** (interactivo) |
| `term_counter` | el contador: apariciones, intervenciones, oradores, desglose por sexo y partido, y la **primera y la última aparición en cada país** |
| `term_frequency` | un término agrupado por año, década, país, legislatura, partido, sexo u orador |
| `share_of_voice` | cuánto habla cada grupo (sexo o partido) frente a su peso en el padrón de ese periodo |
| `distinctive_words` | las palabras que más distinguen a dos grupos: diputadas y diputados, dos partidos, dos periodos (log-odds de Monroe et al. 2008) |
| `kwic` · `collocations` | concordancias en contexto y palabras que acompañan a un término |
| `search_text` · `get_intervention` · `get_session` | buscar pasajes y leerlos con su contexto |
| `query_sql` · `export_result` | SQL de solo lectura (DuckDB) y exportación a CSV o Parquet |
| `query_log` · `how_to_cite` | lo que se ha ejecutado, con las versiones de los datos (y una nota de métodos), y la cita de cada conjunto |

Dos filtros cambian los resultados, y las herramientas avisan cuando conviene usarlos:
`max_turn_words` deja fuera los turnos muy largos. Casi siempre son documentos leídos en el acta,
que el corpus conserva como habla cuando el acta no marca separación: son el 54 % de las palabras
de Argentina, el 26 % de Uruguay y el 25 % de México, frente a menos del 1 % en España. Por su
parte, `exclude_chair` deja fuera a la presidencia de la sesión, cuyo habla procedimental puede
dominar una comparación entre grupos.

Los datos se guardan en `~/.parlaibero` (o en `PARLAIBERO_HOME`). Los 16 países ocupan unos
12 GB de descarga y 15 GB de base de datos; El Salvador, el más pequeño, ocupa 99 MB. Los países
grandes pueden descargarse desde la terminal, para no depender del tiempo de espera del cliente:

```bash
uvx --from "git+https://github.com/rodrodr/parlaibero-tools#subdirectory=mcp" parlaibero-mcp download ES MX
```

Más detalles en [`mcp/README.md`](mcp/README.md).

## 2 · Skills `diaries-*`: la tubería de construcción

Son instrucciones para [Claude Code](https://claude.com/claude-code) (ficheros `SKILL.md`) más el
código Python que invocan. Llevan un diario de sesiones desde el PDF escaneado hasta la matriz
canónica de 16 columnas: OCR, extracción, corrección, metadatos, deduplicación, etiquetado de
oradores, vinculación con el padrón, estandarización y documentación, con un sistema de confianza
(AUTO / FLAG / HALT) y un registro de decisiones metodológicas.

```bash
git clone https://github.com/rodrodr/parlaibero-tools.git
cd parlaibero-tools
bash install_skills.sh          # copia los diaries-* a ~/.claude/skills (no sobrescribe sin --force)
```

Y en la carpeta del proyecto que vaya a contener los datos:

```bash
bash ~/.claude/skills/diaries-lib/install.sh
```

Luego, dentro de Claude Code, `/diaries-teach` explica el recorrido y
`/diaries-bootstrap --country xx` empieza un país nuevo. El OCR de PDF escaneados usa
[Ollama](https://ollama.com) en local.

> Los skills recogen la experiencia de construir los 16 corpus y conservan referencias a ese
> proceso: identificadores de decisiones (`tr-0109`, `br-0011`…), países de ejemplo y scripts
> propios de cada país que no forman parte de este repositorio. Son el método tal como se aplicó,
> no un producto genérico. El código vive en `~/.claude/skills/diaries-lib/` porque los `SKILL.md`
> lo llaman por esa ruta.

## Cómo citar

Cada país se cita por su conjunto de datos, con su DOI y su versión (`how_to_cite` la devuelve
formateada). Los identificadores `id_session` e `id_int` son estables dentro de una versión
publicada, no entre versiones.

## Licencia

El código (servidor MCP y skills) se publica bajo [MIT](LICENSE). Los datos de ParlaIbero no están
en este repositorio: se descargan de Harvard Dataverse, donde cada conjunto lleva su licencia
(CC BY 4.0), su autoría y su DOI. El logotipo de la financiación pertenece a sus titulares y no se
puede reutilizar ni modificar.

---

## English

**ParlaIbero** collects the plenary speeches of the lower or single chambers of 16 countries in
Latin America, Spain and Portugal: 10,091,060 interventions in 52,718 sessions, each linked to a
register of deputies. There is one dataset and one DOI per country in
[Harvard Dataverse](https://dataverse.harvard.edu/dataverse/parlaibero), under CC BY 4.0.

This repository provides:

- **[`mcp/`](mcp/), an MCP server** that downloads the datasets and lets any MCP-capable agent
  (Claude Code, Claude Desktop, Cursor, Codex, Gemini CLI…) search, count and read them. Install it
  in Claude Code with
  `claude mcp add parlaibero -s user -- uvx --from "git+https://github.com/rodrodr/parlaibero-tools#subdirectory=mcp" parlaibero-mcp`.
  See [`mcp/README.md`](mcp/README.md) for other clients.
- **[`skills/`](skills/), the 21 `diaries-*` Claude Code skills** and their Python code: the
  pipeline that turned session diaries (PDF/HTML) into the corpus, from OCR to the canonical
  16-column matrix. Install them with `bash install_skills.sh`. The skills are written in Spanish
  and keep references to the construction of the 16 corpora.

Cite each country's dataset with its DOI and version (the `how_to_cite` tool formats it). Code is
MIT-licensed; data are CC BY 4.0 in Dataverse.

Grant PID2022-141706NB-C22 funded by MICIU/AEI/10.13039/501100011033 and by ERDF/EU.

## Datasets

| ISO | country (years) | version | DOI |
|---|---|---|---|
| AR | Argentina (1983-2025) | v2.0 | [10.7910/DVN/IVNYID](https://doi.org/10.7910/DVN/IVNYID) |
| BR | Brazil (2003-2025) | v2.0 | [10.7910/DVN/VTXNW3](https://doi.org/10.7910/DVN/VTXNW3) |
| CL | Chile (1990-2025) | v2.0 | [10.7910/DVN/IKBNRL](https://doi.org/10.7910/DVN/IKBNRL) |
| CO | Colombia (2000-2025) | v2.0 | [10.7910/DVN/TYYERX](https://doi.org/10.7910/DVN/TYYERX) |
| CR | Costa Rica (1994-2025) | v2.0 | [10.7910/DVN/W6UAHQ](https://doi.org/10.7910/DVN/W6UAHQ) |
| DO | Dominican Republic (2001-2025) | v2.0 | [10.7910/DVN/DZKXUG](https://doi.org/10.7910/DVN/DZKXUG) |
| EC | Ecuador (1979-2025) | v2.0 | [10.7910/DVN/M2QJN6](https://doi.org/10.7910/DVN/M2QJN6) |
| ES | Spain (1977-2025) | v2.0 | [10.7910/DVN/OKHGAB](https://doi.org/10.7910/DVN/OKHGAB) |
| GT | Guatemala (2000-2026) | v2.0 | [10.7910/DVN/NH5TTC](https://doi.org/10.7910/DVN/NH5TTC) |
| MX | Mexico (1988-2025) | v2.0 | [10.7910/DVN/0IS1YE](https://doi.org/10.7910/DVN/0IS1YE) |
| PA | Panama (1996-2025) | v2.0 | [10.7910/DVN/Y8FUSX](https://doi.org/10.7910/DVN/Y8FUSX) |
| PE | Peru (1995-2025) | v1.0 | [10.7910/DVN/7MK94V](https://doi.org/10.7910/DVN/7MK94V) |
| PT | Portugal (1976-2025) | v2.0 | [10.7910/DVN/VRPUFU](https://doi.org/10.7910/DVN/VRPUFU) |
| PY | Paraguay (1988-2025) | v2.0 | [10.7910/DVN/PDX8GA](https://doi.org/10.7910/DVN/PDX8GA) |
| SV | El Salvador (2018-2025) | v2.0 | [10.7910/DVN/MUJU6A](https://doi.org/10.7910/DVN/MUJU6A) |
| UY | Uruguay (1985-2025) | v2.0 | [10.7910/DVN/KI1AOC](https://doi.org/10.7910/DVN/KI1AOC) |

<sub>Versions as published on 2026-10-03; `list_countries` reads the current ones from Dataverse.</sub>

## Para mantenedores · maintainers

`skills/` se **genera**: no se edita a mano. La fuente única es `~/.claude/skills/diaries-*` del
investigador, y `python3 maintainer/sync_skills.py` la exporta excluyendo respaldos y estado de
proyecto, convierte las rutas absolutas en relativas y falla si queda alguna ruta personal o algo
con aspecto de credencial.
