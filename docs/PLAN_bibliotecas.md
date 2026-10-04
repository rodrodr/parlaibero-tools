# Plan · Bibliotecas en `parlaibero-mcp` (v0.3.0)

> **Estado: TERMINADO** (2026-10-03): 0.3.0 publicada en PyPI por el investigador. Aprobado con las decisiones del §7.
> Origen: conversación del 3-oct. Idea del investigador: antes del análisis temático, una herramienta de **subconjuntos**
> como las bibliotecas del explorador, que además **cruce países** para el análisis comparado. Decidido: exportar a
> archivos del explorador **por país** (opción 1); el explorador no se toca.

---

## 1. Qué se construye y qué no

**Dentro**
- Bibliotecas con nombre, persistentes, de **uno o varios países**.
- Crearlas, afinarlas (añadir, quitar, anotar), combinarlas y describirlas.
- Un parámetro `library` en todas las herramientas de análisis.
- **Exportar por país** a archivos `.2replib` que el explorador importa tal cual, más un índice que los une.
- **Importar** `.2replib` del explorador (uno o varios) para reunirlos en una biblioteca comparada.

**Fuera** (más adelante, si se decide): análisis temático y anotación de posiciones; bibliotecas autocontenidas con el
texto dentro (opción 3); cambios en el explorador (opciones 2 y 3); búsquedas guardadas.

---

## 2. Lo que hace hoy el explorador (leído en su código el 3-oct)

| hecho | dónde |
|---|---|
| Las bibliotecas viven en una SQLite aparte: `collections`, `items`, `saved_searches`. «Actualizar los datos no borra su trabajo». | `worker/29_engine__library.js` |
| Un item es `(corpus, speech_id, note, tags, char_start, char_end, added_at, position)`. | ídem |
| **`speech_id` es el número de fila del CSV publicado, desde 1**, en el orden en que se carga: `const id = this.insertadas + 1`. La tabla del explorador guarda también `id_int`, pero el `.2replib` solo lleva `speech_id`. | `worker/05_worker__construir.js:362` |
| Archivo de una biblioteca: **`2replib/1`**, JSON con sangría 2, `ensure_ascii=False` y orden de claves fijo: `format`, `exported_at`, `corpus`, `fuente`, [`fuente_importada`], `collection` {`name`, `description`, `color`}, `items` [{`speech_id`, `note`, `tags`, `date`, `rep_name`, `speaker`, `fuente_cita`, `fuente_doi`}]. | `worker/30_engine__paquetes.js` |
| Al importar exige `format`, `collection` e `items[].speech_id`; `note` y `tags` son opcionales; el nombre recibe « (importada)». Valida todo antes de escribir. | ídem |
| `fuente` es la ficha del conjunto: `titulo`, `autores`, `anio`, `editor`, `doi`, `url`, `version_cita`, `cita`, `licencia`… | `datos/fuentes_parlaibero.json`, `worker/18_engine__fuente.js` |
| Una biblioteca es de **un solo corpus** (un país). | — |

**Comprobado en el código (3-oct):**
- **El cargador no se salta ningún registro.** Solo omite las líneas vacías, que no son registros. Un registro con
  un número de campos distinto de 16 aborta la carga entera (`worker/07_worker__ingesta.js:255-260`). Por tanto,
  `speech_id` es el número del registro de datos, sin la cabecera.
- **El `corpus` de una biblioteca es `Diarios_{ISO}`**, por ejemplo `Diarios_SV` (`corpusBibliotecas`,
  `worker/28_engine__info.js:107`). Con ese mismo nombre el explorador recupera la ficha `fuente` del país
  (`paisDeCorpus`).
- ⚠ **El explorador NO comprueba a qué país pertenece un `.2replib`.** Al importar, ignora el campo `corpus` y
  cuelga los `speech_id` del corpus que esté cargado (`worker/31_engine__rutas_biblioteca.js`,
  `P.importarBiblioteca(lib, payload, nombreCorpus(ctx))`). Importar el archivo de Argentina con el CSV de España
  cargado crea, sin aviso, una biblioteca de intervenciones españolas que no tienen nada que ver. Exportar por país
  multiplica los archivos y, con ellos, la ocasión del error. Defensa en el MCP: el país va en el nombre del archivo,
  en el nombre de la biblioteca y en su descripción. La defensa de verdad es que el explorador compare `corpus` con
  el corpus cargado: es un cambio en el explorador, fuera de este plan, y se le propone aparte.
- **El orden de las filas, medido el 3-oct.** DuckDB conserva el orden del archivo al importar: `row_number()`
  coincide fila a fila con una lectura independiente en Python en El Salvador (49 077 filas) y en Brasil
  (1 657 113, lectura en paralelo), con cero discrepancias. La lectura en Python de Brasil tarda 9 s, así que la
  comprobación se hace en cada importación.

---

## 3. Modelo de datos

**Un archivo aparte, `~/.parlaibero/bibliotecas.duckdb`**, como hace el explorador: volver a descargar o reindexar la
base de datos no toca el trabajo del usuario. Las consultas lo adjuntan en solo lectura.

```
libraries      id · name · description · color · created_at · updated_at · design (JSON: calendario | evento)
library_parts  library_id · country · edition · doi · label · definition (JSON: términos, filtros, ventana)
library_items  library_id · country · id_int · row_n · note · tags (JSON) · char_start · char_end ·
               added_at · position · origin ('definicion' | 'manual' | 'importada')
library_excl   library_id · country · id_int        ← lo que el usuario quitó a mano
```

**`row_n`, el número de registro del CSV publicado.** Se añade a `interventions` al importar, con la misma regla que
el explorador: se lee el CSV en orden y sin paralelismo, se numera con `row_number()` y se descartan solo las líneas
vacías. Sirve para traducir `speech_id ⇄ id_int` en las dos direcciones. Es la versión 4 del
esquema. Para las bases existentes, `parlaibero-mcp reindex` lo calcula releyendo los CSV descargados; si no están,
pide volver a descargar ese país.

**La edición, por parte.** `id_int` y `speech_id` solo son estables dentro de una edición. Cada parte guarda la edición
de su país, y el MCP se niega a mezclar ediciones sin decirlo.

---

## 4. Herramientas

| herramienta | qué hace |
|---|---|
| `library_create` | Crea una biblioteca de uno o varios países. Cada parte tiene su definición: términos (con `+` y `*`, como el resto), filtros (fechas, partido, sexo, diputado, `exclude_chair`, `max_turn_words`) y una etiqueta común («corrupción»). Ventanas de tiempo por **calendario** (las mismas fechas en todos) o **alineadas a un evento** (fecha cero propia de cada país, con ventana ±N días). Devuelve la descripción. |
| `library_add` · `library_remove` | Añade o quita intervenciones por `id_int`, por búsqueda o por consulta. Lo quitado a mano se recuerda. |
| `library_note` | Nota y etiquetas de una intervención. |
| `library_combine` | Unión, intersección o diferencia de dos bibliotecas, en una nueva. |
| `library_describe` | Por país: intervenciones, sesiones, años, oradores, palabras, vinculación, peso de la presidencia y de los turnos largos, años de base escasa y edición. Avisos de comparación cuando hay varios países. |
| `library_list` · `library_delete` | Listar; borrar exige `confirm=true`. |
| `library_rebuild` | Rehace las partes desde su definición tras una edición nueva, dice qué entra y qué sale, y conserva las notas y exclusiones de las intervenciones que se pueden reencontrar. |
| `library_export` | **Opción 1:** un `.2replib` por país, más el índice. Además, si se pide, CSV o Parquet de las intervenciones con sus metadatos. |
| `library_import` | Uno o varios `.2replib` (cada uno pasa a ser la parte de su país) o un índice (la biblioteca comparada entera). |

**`library` en las herramientas existentes:** `search_text`, `kwic`, `collocations`, `term_counter`,
`term_frequency`, `ngram_viewer`, `share_of_voice`, `coverage` y `distinctive_words` (la biblioteca frente al resto
de su cámara, o frente a otra biblioteca). `query_sql` ve la tabla `library_items` para unirla con `interventions`.

**Por defecto, comparar es por país:** con varios países, los resultados salen separados y normalizados dentro de cada
cámara; agregar exige pedirlo y lleva el aviso de composición. `distinctive_words` avisa si mezcla español y portugués.

---

## 5. Exportar por país (opción 1)

- **Un archivo por país**, `{nombre}_{ISO}.2replib`, en el formato `2replib/1` **byte a byte** como lo escribe el
  explorador: mismo orden de claves, sangría y escape.
  - `corpus`: `Diarios_{ISO}`, el nombre que el explorador espera para ese país.
  - `fuente`: la ficha del conjunto con la forma de `fuentes_parlaibero.json`, rellena desde Dataverse (título,
    autores, año, editor, DOI, URL, versión, cita, licencia).
  - Cada item: `speech_id` = `row_n`; `note`, `tags`; `date`; `rep_name` (= `speaker_name`); `speaker`
    (= `speaker_raw`); `fuente_cita` y `fuente_doi`.
- **El índice**, `{nombre}.parlaibero-biblioteca.json` (formato propio, `parlaibero-biblioteca/1`): nombre,
  descripción, diseño (calendario o evento), y por parte el país, el archivo, la edición, el DOI, el número de
  intervenciones, la definición y el sha256 del archivo. Con él, `library_import` reconstruye la biblioteca comparada;
  sin él, cada archivo sigue siendo una biblioteca de su país.
- **Ida y vuelta:** MCP → explorador → MCP devuelve las mismas intervenciones, notas y etiquetas.

---

## 6. Puertas antes de publicar 0.3.0

1. **`row_n` ≡ `speech_id`:** cargar El Salvador y España en el explorador, exportar una biblioteca de cada uno y
   comprobar que cada `speech_id` señala en el MCP la intervención de la misma fecha y orador.
2. **Bytes idénticos:** un `.2replib` escrito por el MCP es igual al que escribe el explorador para las mismas
   intervenciones (un archivo real del explorador sirve de muestra en las pruebas).
3. **Importar con comprobación:** cada `speech_id` se traduce a `id_int` y se coteja `date` y `speaker`; lo que no
   cuadra se informa, no se traduce en silencio.
4. **Edición:** si la versión de la `fuente` de un archivo no es la descargada, se avisa y no se importa sin
   `force=true`.
5. Las puertas habituales del repositorio: las pruebas sin red (más las nuevas de bibliotecas) y la prueba de punta
   a punta por el protocolo MCP.

---

## 7. Decisiones (del investigador, 3-oct)

1. **Archivo aparte**, `bibliotecas.duckdb`.
2. **Calendario**, con **ayuda para alinear a un evento**. Las ventanas se guardan siempre como fechas. Para alinear,
   `library_create` acepta una fecha de evento por país y un margen (`event_dates`, `days_before`, `days_after`) y
   la convierte en la ventana de cada país, dejando escrito en la definición que viene de un evento. Para encontrar
   esas fechas, `term_counter` da el primer uso de un término en cada cámara y `term_frequency` agrupa por sesión
   (`by='session'`) para ver dónde se concentra.
3. **Sí**: CSV o Parquet de la biblioteca, con sus metadatos, como opción de `library_export`.
4. **Sí, prueba automática en el explorador.** Se añade al repositorio del explorador **solo** la prueba: un arnés
   de Node que carga su propio motor, construye la base con un CSV publicado, importa el `.2replib` escrito por el
   MCP y lo vuelve a exportar. Así es el código del explorador, no una copia, el que juzga la compatibilidad.

**Ajuste a la puerta 2 del §6.** Pedir bytes idénticos obligaría a reescribir en Python el formateador de citas del
explorador (BibTeX, RIS, CSL-JSON): una copia que habría que mantener sincronizada, justo lo que la norma «una cosa,
un archivo» desaconseja. La puerta pasa a ser la ida y vuelta por el motor real: el explorador importa el archivo
sin error, conserva notas y etiquetas, reconoce la fuente (la misma `cita` que su ficha del país, para que no la
marque como «importada») y, al volver a exportar, devuelve los mismos `speech_id`.

## 8. Entregas

| fase | contenido |
|---|---|
| A | `row_n`, esquema 4, `reindex`, `bibliotecas.duckdb` |
| B | crear, añadir, quitar, anotar, combinar, describir, listar, borrar, rehacer |
| C | parámetro `library` en las herramientas existentes |
| D | exportar e importar `.2replib` y el índice; ida y vuelta |
| E | README, instrucciones del servidor, CHANGELOG; publicar 0.3.0 (lo publica usted) |
