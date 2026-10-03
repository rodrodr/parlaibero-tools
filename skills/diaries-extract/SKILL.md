---
name: diaries-extract
description: "Consolida el raw (OCR/PDF digital/HTML/XML/DOCX/texto) en un texto de trabajo FIEL con marcadores de página. NO limpia: la limpieza (cabeceros, mobiliario, hifenización, reflujo) es de diaries-correct."
allowed-tools: [Read, Write, Edit, Bash]
---

Argumentos: `--country {iso2}` + uno de `--session YYYY-MM-DD` | `--batch YYYY-MM` | `--all` + opcionales `--force`, `--dry-run`

## Responsabilidad ÚNICA de este skill

`diaries-extract` produce **`extracted/{session_id}.txt` = la capa de texto FIEL**: saca el texto del
formato de origen (OCR, PDF digital, HTML, XML, DOCX, texto plano), lo consolida en un `.txt` y
**conserva la frontera de página** (`---PAGE N---`). **No limpia NADA** — ni cabeceros, ni mobiliario,
ni hifenización, ni reflujo. Toda la limpieza es de `diaries-correct`.

⚠ Este es un cambio de diseño (2026-08): antes `extract` también quitaba cabeceros (`strip_headers`) y
mantenía una capa `text/` aparte. Ahora **`extracted/` ES la capa fiel** (funde el papel del viejo
`text/`) y la limpieza se hace UNA sola vez, aguas abajo, en `correct`. Lo que habilita moverla es que
`extracted/` **conserva los marcadores de página**, así que `correct` sigue teniendo la frontera que
necesita para anclar el mobiliario. Ver `docs/_historico/PLAN_REPROCESO_DESDE_CERO.md §1.1` (proyecto de datos).

Lo único que `extract` juzga es la **CALIDAD de la extracción** (gates que miden, no limpian): si el
texto salió fragmentado o con el prefijo de orador corrompido, baja la confianza / HALT.

---

## Paso 0 — Leer configuración del país

Lee `country_config/{iso2}.yaml`. Extrae:
- `source_format` — el formato DOMINANTE del país.
- `sources` — mapa POR ARCHIVO/ERA para fuentes mixtas (`[{pattern|era, format}]`, lo registra
  `bootstrap`). Si existe, el formato de CADA sesión se resuelve contra este mapa; el global es
  solo el default.
- `extract.emit_page_marker` (default: true) y `extract.page_marker_format` — la frontera de página
  que se CONSERVA en la salida (es estructura de la fuente, no mobiliario).
- `extract.page_break_marker` — marca de salto que la fuente YA trae (p.ej. `--- PAGE BREAK ---`), si aplica.
- `threshold_auto` (default: 0.85) · `threshold_flag` (default: 0.65)

⚠ **`extract` ya NO lee `strip_headers` ni vocabulario de mobiliario** — eso vive en `correct`.

---

## Paso 1 — Determinar lista de sesiones

**`--session YYYY-MM-DD`**: una sola sesión.

**`--batch YYYY-MM`**: `ls source/{iso2}/raw/ | grep "^YYYY-MM"`.

**`--all`**: `ls source/{iso2}/raw/`.

Filtra las ya completadas (salvo `--force`): lee `state/{iso2}/pipeline_state.json` y excluye las que
tengan `skills.diaries-extract.status == "complete"`. Si la lista queda vacía: imprime "No hay sesiones
pendientes para diaries-extract." y termina.

---

## Paso 2 — Verificar prerequisitos por sesión

Para cada `session_id`, según `source_format`:

- **`pdf_image` | `pdf_poor_ocr`**: existe ≥1 `page_*.txt` en `source/{iso2}/ocr/{session_id}/`
  (`ls source/{iso2}/ocr/{session_id}/page_*.txt 2>/dev/null | wc -l`). Si 0 → error "OCR no completado" y salta.
- **`pdf_digital`**: existe `source/{iso2}/raw/{session_id}.pdf`.
- **`html`**: existe `source/{iso2}/raw/{session_id}.html`.
- **`xml`**: existe `source/{iso2}/raw/{session_id}.xml`.
- **`docx`**: existe `source/{iso2}/raw/{session_id}.docx`.
- **`text_flat`** (texto de sesión ya extraído, p.ej. ES): existe `source/{iso2}/raw/{session_id}.txt`.

Si el archivo no existe: registra error y salta.

Con mapa `sources` (fuentes mixtas), el prerequisito se evalúa con el formato de ESA sesión, no
con el `source_format` global.

---

## Paso 3 — Extraer el texto FIEL de cada sesión

### 3a. Directorio de salida
```bash
mkdir -p source/{iso2}/extracted/
```

### 3b. Extensión del archivo fuente
- `pdf_*` → `.pdf` · `html` → `.html` · `xml` → `.xml` · `docx` → `.docx` · `text_flat` → `.txt`

### 3c. Mapear `source_format` → `--source-format` del script
- `pdf_digital` → `pdf_digital`
- `pdf_image` | `pdf_poor_ocr` | `pdf_good_ocr` → `ocr_pages` (lee los `page_*.txt` ya producidos; **NO reprocesa OCR**)
- `html` → `html` · `docx` → `docx`
- `xml` → **NO pasa por `extract_text.py`** (el script no acepta `xml`): parser estructurado DE
  PAÍS, ver 3c-bis.
- `doc` (CL) → convertir con `textutil -convert txt` (macOS) y tratar como `text_flat` (3c-bis).
- `text_flat` → `text_flat` (sin `--ocr-dir`). Con `extract.page_break_marker` presente segmenta por esa
  marca; sin ella, el texto entra tal cual.

⚠ **Ingesta híbrida POR ARCHIVO (PA/UY):** `extract` enruta CADA sesión según el formato que
`bootstrap` registró para ese archivo en el mapa `sources` — `pdf_digital` para los PDF buenos,
`ocr_pages` para los reprocesados — y `pdf_digital`/`ocr_pages` ya no son excluyentes a nivel
país. Si la sesión casa una entrada de `sources`, gana esa entrada sobre el `source_format` global.

### 3c-bis. XML y DOC — rutas de país, fuera de `extract_text.py`

⚠ Este skill mandaba invocar `extract_text.py --source-format xml`. **Esa opción no existe**
(`choices=["pdf_digital", "ocr_pages", "html", "text_flat", "docx"]`): la invocación fallaba en el
primer archivo. La ruta REAL del XML es un **parser estructurado de cada país** — el esquema no es
transferible:

- **CL — `parse_cl_xml.py`** (`~/.claude/skills/diaries-lib/lib/utils/parse_cl_xml.py`): el XML de
  la Cámara ya viene **TAGGED y MATCHED** — cada turno trae su orador con el id oficial de la
  Cámara, que se usa como `id_dep`. Produce la **matriz por TURNO directamente**, así que esas
  sesiones entran al pipeline en el nivel de `matrix` (se saltan extract/correct/tag); los gates
  B/C se aplican igual sobre su salida.
- **PT** — XML comprimido con esquema DISTINTO al de CL: parser propio a construir/descubrir en su
  arranque. No reutilizar el de CL (directiva de procesamiento por país).
- **`doc` (CL)** — convertir primero (`textutil -convert txt archivo.doc`, macOS) y tratar el
  resultado como `text_flat` (pass-through fiel por `extract_text.py`).

### 3d. Ejecutar la extracción FIEL

Si `--dry-run`: imprime el comando y salta.

⚠ `extract_text.py` es **FIEL POR DEFECTO** (arreglado 2026-08-23): sin banderas, `--output`
recibe el texto fiel (consolidado + marcadores de página, sin quitar cabeceros). `--strip-headers`
existe solo como legado opt-in y **NO debe usarse en el flujo canónico**; `--no-strip-headers` se
acepta como no-op. Se sigue pasando `--config` porque de él salen el formato del marcador de página
y el modo de `text_flat` — no la limpieza.

```bash
python ~/.claude/skills/diaries-lib/lib/utils/extract_text.py \
  --input "source/{iso2}/raw/{session_id}.{ext}" \
  --source-format {extract_format} \
  --ocr-dir "source/{iso2}/ocr/{session_id}/" \
  --config "country_config/{iso2}.yaml" \
  --output "source/{iso2}/extracted/{session_id}.txt"
```

Lee el JSON de stdout (`status`, `chars`, `valid_ratio`, `page_markers`). Ya **no** hay campos
`header_*`: no se elimina mobiliario en esta etapa.

### 3e. Verificar tamaño de salida
```bash
wc -c "source/{iso2}/extracted/{session_id}.txt"
```
Si < 500 caracteres: advertencia "Archivo de salida muy pequeño ({N} chars) — posible fallo de extracción."

### 3f. GATE de fragmentación (ancho de columna) — mide, NO limpia

⚠ **El fallo que más veces se ha repetido** (PA, GT, CO, PY): la caja es estrecha (dos columnas, o un
PDF cuyo `get_text()` devuelve un fragmento por línea) y la fuente **corta el marcador y el nombre**:

```
SEÑOR DIPUTADO RICARDO GONZALEZ          DIPUTADO JULIO CESAR FRU-
ESCOBAR: Gracias, señor Presidente.      TOS: Muchas gracias.
```

Aguas abajo **desaparecen turnos enteros** (PY: ~100.000, el 25% del corpus) o el apellido no casa con
el padrón (`FRU- TOS` nunca será `Frutos`), y nada lo delata. **Mídelo aquí, que es donde nace:**

```python
import statistics, re
from pathlib import Path
for p in sorted(Path(f"source/{iso2}/extracted").glob("*.txt")):
    ls=[l.strip() for l in p.read_text(errors="replace").split("\n") if l.strip()]
    if not ls: continue
    med=statistics.median(len(l) for l in ls)
    gui=sum(1 for l in ls if re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]-$", l))    # corte con guion
    if med < 25 or gui/len(ls) > 0.02:
        print(f"{p.name}: línea mediana {med:.0f} car · {gui} cortes con guion de {len(ls)} líneas")
```

- **Línea mediana < 25 car** → la extracción devuelve fragmentos, no líneas. Prueba otro modo
  (`get_text("blocks")`, `sort=True`) ANTES de dar el texto por bueno; en PY solo 17 de 243 PDF estaban
  así, pero bastaba para sesgar el diagnóstico. Si persiste, baja la confianza (es fallo de extracción).
- **Cortes con guion > 2%** → anótalo: la de-hifenación es obligatoria en `correct` y debe hacerse ANTES
  de cualquier reensamblado.

⚠ **Aquí NO se aplana ni se reúne el marcador**: el reflujo y la reunión son de `correct`
(`marker_reassembly` / reflujo por columna). Aplanar borra la estructura de línea que `conformidad.py`
comprueba. Ver [[feedback_marcador_partido]].

### 3g. GATE de integridad del prefijo de orador (solo escaneadas: `pdf_poor_ocr`/`pdf_image`)

El `valid_ratio` puede ser 0.98 y el texto ser inútil para el tagging si el OCR embebido corrompe los
caracteres del prefijo de orador (caso documentado: UY 1987, 14 vs 164 intervenciones). Chequeo
**genérico**, derivado del country_config (no asume idioma):

```python
import re, yaml
config  = yaml.safe_load(open(f'country_config/{iso2}.yaml'))
patterns = config.get('speaker_tag_patterns', [])
text    = open(f'source/{iso2}/extracted/{session_id}.txt').read()
candidate_lines = [l.strip() for l in text.splitlines()
    if re.match(r'^[A-ZÁÉÍÓÚÜÑÀÃÂÊÍÔÕÇ][^\n]{3,55}(\.-|:)\s*$', l.strip())]
matched = [l for l in candidate_lines if any(re.search(p, l) for p in patterns)]
CORRUPTION_RE = re.compile(r"[~'`^_|\\{}]|[A-Z][a-z]{1,2}[A-Z]")
corrupted = [l for l in candidate_lines if l not in matched and CORRUPTION_RE.search(l)]
total = len(candidate_lines); garble_ratio = len(corrupted)/total if total else 0
```

Si `garble_ratio > 0.50` Y `source_format in ("pdf_poor_ocr","pdf_image")`:
- Advertencia con 3 ejemplos de líneas corrompidas.
- `confidence = min(confidence, 0.55)` → HALT.
- `error_message`: `"Texto embebido no apto para tagging: prefijo de orador corrompido ({garble_ratio:.0%}). Ejecutar diaries-ocr primero."`

**Nota:** si `candidate_lines` está vacío (sesión corta o solo trámite), omite el chequeo — no es
corrupción, es ausencia de debate.

### 3h. Calcular confianza y status

`confidence = valid_ratio`. Si la salida < 500 chars: `confidence = min(confidence, 0.60)`. Aplica el
GATE de garble (3g) y, si la fragmentación (3f) persiste tras probar otro modo, bájala también. **No hay
lógica de cabeceros** (no se limpia aquí).

- `confidence >= threshold_auto` → `complete`
- `confidence >= threshold_flag` → `flag`
- `confidence < threshold_flag` → `halt`

### 3i. Actualizar estado
```bash
python ~/.claude/skills/diaries-lib/lib/utils/update_state.py \
  --country {iso2} --skill diaries-extract --session {session_id} \
  --status {complete|flag|halt} --confidence {valor} \
  --output "source/{iso2}/extracted/{session_id}.txt"
```

---

## Paso 3-bis — Trampas por formato de origen (verificar SIEMPRE, también al reprocesar)

Estas han vaciado o corrompido corpus enteros sin lanzar error. El síntoma común es **sesiones con 0
caracteres o texto ilegible**, no una excepción: hay que buscarlas activamente.

### HTML — leer por el charset DECLARADO, no por UTF-8 fijo
Bug real MX (2026-06): **680 de 2.539 sesiones a 0 caracteres** porque la fuente declara `ISO-8859-1` y
se leía como UTF-8. Detecta la codificación del documento:
```python
import re
raw = path.read_bytes()
m = re.search(rb'charset=["\']?([\w-]+)', raw[:2048], re.I)
enc = m.group(1).decode() if m else "utf-8"
html = raw.decode(enc, errors="replace")
```

### HTML — NO metas elementos void en la lista de etiquetas a saltar
`meta`, `link`, `br`, `img`, `hr` **no tienen cierre** en HTML no-XHTML. Si entran en `_skip_tags`, el
contador de profundidad nunca baja, se atasca y **vacía el cuerpo entero**. Segunda causa de las 680 de MX.

### HTML — el `<p>` VACÍO es la frontera de párrafo, y el whitespace se colapsa CON strip
Los otros dos fenómenos de los cuatro conocidos ([[feedback_html_extract_encoding_void]]):
- **El `<p>` vacío NO se descarta.** Donde `<p>` = línea impresa (PT: 92 % de 2010, 68 % de 2020),
  el `<p>` sin texto es la ÚNICA señal de fin de párrafo — el 19-21 % vienen así. El filtro
  idiomático `if x` los tiraba y dejaba un párrafo por PÁGINA (1.830 car/párrafo vs 176-232 sanos).
  Qué representa `<p>` (¿párrafo o línea?) cambia DENTRO del país: se decide POR DOCUMENTO
  (cuántos `<p>` cierran frase + distribución de longitudes). Lo vacío no es ausencia de
  información: ES la información.
- **El whitespace del CONTENIDO se colapsa, y las líneas se vacían con `strip()` DESPUÉS.** Un
  salto dentro de un `<p>` es formateo del fichero, no del documento. Y las líneas HTML conservan
  la indentación inicial: cualquier verificación tipo `^(El|La)` sin `line.strip()` da falsos 0.

### HTML — PT: doble codificación 2×, deshacerla ANTES de extraer
⚠ (Plan de reproceso §2.) El HTML de PT trae mojibake de SEGUNDO nivel — UTF-8 codificado dos
veces (`Ã£` donde va `ã`). Antes de extraer, detecta y DESHAZ la doble codificación por documento
(revierte una capa mientras la métrica de «texto normal» mejore; idempotente en los sanos). Es
**decodificación FIEL, no limpieza** — pertenece a `extract`, no a `correct`: sin ella cada acento
y cada nombre salen corruptos y `valid_ratio` no lo ve.

### DOCX — mojibake HETEROGÉNEO, detectado por archivo
En CR el mojibake variaba **de archivo a archivo**. **Auto-detecta el flavor por documento** maximizando
una métrica de «texto normal» (fracción de caracteres en rangos esperados), idempotente y con identidad
en empate. En CR el ratio mínimo pasó de 0,027 a 0,960. ⚠ No uses lista negra de glifos (inestable) ni
flag por año (corrompe los limpios). Filtra los blobs binarios embebidos (OLE/PBrush, `ÿÿÿ€€€`).

### Gate de salida (obligatorio)
```bash
python3 -c "
import glob,os
f=sorted(glob.glob('source/{iso2}/extracted/*.txt'))
z=[x for x in f if os.path.getsize(x)<200]
print(f'{len(f)} archivos · {len(z)} con <200 bytes ({len(z)/max(len(f),1):.1%})')
print('  ejemplos:',[os.path.basename(x) for x in z[:5]])"
```
**> 2 % de archivos casi vacíos → PARA e investiga el formato antes de seguir.** Es barato aquí y
carísimo tres pasos más abajo.

---

## Paso 3-ter — La frontera de página se CONSERVA (habilita la limpieza en `correct`)

`extract_text.py` emite un marcador entre páginas —`---PAGE 0001---` en su propia línea— y lo declara en
el JSON (`page_markers`). Se controla con `extract.emit_page_marker` (default **true**) y
`extract.page_marker_format`. **Conservarlo es lo que permite mover la limpieza a `correct`**: sin la
frontera, un número suelto es indistinguible del número de un punto del orden del día (AR 18.677 líneas,
PA 22.871 — y **ninguna** resultó ser folio); con el marcador, un número pegado a la frontera **es** un folio.

⚠⚠ **El marcador NUNCA debe fundirse dentro de una frase** —«…algo importante ---PAGE 0002--- y la frase
continúa»—: por eso va en su propia línea. Aguas abajo:
- **`correct_text`** lo trata como frontera dura: ancla el mobiliario, y el merge de párrafos no lo
  absorbe (`_PAGINA_RX` en `_MARKER_PROTECT_DEFAULT`). Lo elimina en el paso 3 de su secuencia, ya vacío.
- **`parse_interventions`** lo retira del `text` con `quitar_marca_pagina()` y devuelve las páginas que
  abarcaba cada intervención (procedencia).

### Buscar el marcador que la fuente YA trae, antes de darla por perdida
Muchos OCR escriben la frontera. Medido 2026-08-02: **PY** `--- PAGE BREAK ---` en 60/60 archivos;
**EC, UY** la frontera ES el archivo `page_*.txt` (la conserva `extract_ocr_pages`). ⚠⚠ El de PY estaba
ahí desde el principio y no se usaba (PY entraba como `tagged_text`, que se salta la extracción). Al
preparar cualquier re-ingesta, comprobar primero: `--- PAGE BREAK ---`, `--- PÁGINA`, form feed (`\f`),
`[Pág. N]`. Encontrarlo es más fiable que inferirlo.

---

## Paso 3-quater — Por qué `extracted/` es la capa FIEL (y no se limpia NUNCA)

`extracted/` consolida en un único `.txt` lo que venga de OCR, PDF digital, DOCX, HTML, XML o texto plano,
**tal cual**, añadiendo solo la marca de página. Es:

1. **El punto de retorno reproducible.** Cambiar una regla de limpieza NO obliga a volver a los binarios:
   se re-corre `correct` sobre `extracted/` en segundos. Es lo que se archiva para que un tercero rehaga
   el corpus sin las fuentes originales.
2. **La fuente que `meta` consulta ÍNTEGRA.** La limpieza retira metadatos legítimos: en SV «Acta Número
   35 … 14 de febrero de 2019» va en el cabecero de cada página (la limpieza retira 8.531 car y 100
   folios en una sola sesión). `meta` lee `extracted/` primero (la más rica) y `corrected/` como respaldo.
3. **Homogeneiza los formatos**: todo lo que va después deja de depender del formato de origen.

⚠ **`extracted/` no se limpia NUNCA.** Si algo hay que quitar, se quita en `correct`. Un punto de retorno
que se edita no sirve de nada.

> Nota de reproceso: los corpus cerrados con mobiliario incrustado en el `text` ya NO se reparan desde
> `extract` (`strip_matrix_furniture` sale del flujo canónico). Se reprocesan desde `extracted/` con el
> bucle de residuo de `correct` (descubrir→aplicar→verificar residuo→refinar). Ver
> [[feedback_residuo_mobiliario_loop]].

---

## Paso 4 — Resumen final

```
Resumen diaries-extract — {iso2}
─────────────────────────────────────────────
  AUTO  (complete): {N}
  FLAG  (revisar):  {N}
  HALT  (detenido): {N}
  SKIP  (ya hecho): {N}
  ERROR:            {N}
─────────────────────────────────────────────
  Total procesadas: {N}
```

Si hay advertencias de archivos pequeños o de fragmentación, listarlas.

Si hay FLAG/HALT:
```
Hay {N} sesiones que requieren revisión.
Ejecuta: /diaries-review --country {iso2}
```

Si todo es AUTO:
```
Siguiente paso: /diaries-correct --country {iso2} --all
```
