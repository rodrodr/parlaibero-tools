---
name: diaries-bootstrap
description: "Configura un país nuevo: detecta trabajo ya realizado en carpetas intermedias, infiere la config desde archivos fuente, entrevista al usuario para confirmar lo que falta, e inicializa el estado del pipeline reflejando la situación real."
allowed-tools: [Read, Write, Edit, Bash]
---

Este skill opera a nivel PAÍS. Recibe `--country {iso2}`. No usa --session ni --batch.

Convención de rutas: todas son **relativas a la raíz del proyecto** (el dir con source/, state/, country_config/, docs/ — el proyecto es solo DATOS; el código vive en ~/.claude/skills/). Ejecuta el skill desde esa raíz.

---

## Paso 0 — Verificar que existe material fuente

```bash
find source/{iso2}/raw -type f \( -iname '*.pdf' -o -iname '*.html' -o -iname '*.xml' \
  -o -iname '*.docx' -o -iname '*.doc' -o -iname '*.txt' \) 2>/dev/null | head
```

Si el directorio no existe o está vacío:
```
ERROR: No se encontraron archivos en source/{iso2}/raw/
Crea el directorio y copia los archivos fuente antes de ejecutar este skill.
Estructura esperada: source/{iso2}/raw/**/{session_id}.{pdf|html|xml|docx|doc|txt}
```

⚠ El `raw/` curado viene en SUBDIRECTORIOS — por año (`es/raw/1977/`) o por formato
(`cl/raw/{ocr,pdf,xml}`, `pt/raw/{html,xml_json}`) — y en CUALQUIERA de las seis extensiones.
El inventario es RECURSIVO siempre; un `ls` plano ve cero archivos y aborta en falso.

Obtén la lista completa de session_ids (stem de cada archivo, recursivo):
```bash
find source/{iso2}/raw -type f \( -iname '*.pdf' -o -iname '*.html' -o -iname '*.xml' \
  -o -iname '*.docx' -o -iname '*.doc' -o -iname '*.txt' \) | sed 's|.*/||; s/\.[^.]*$//' | sort -u
```

---

## Paso 0b — Inventario de trabajo ya realizado

Antes de inferir nada, audita qué etapas ya están pobladas para cada sesión.
Esto evita repisar trabajo hecho y permite arrancar desde donde realmente se está.

### Comprobaciones por sesión

Para cada `session_id` en la lista del Paso 0, ejecuta en un solo bloque:

```bash
python3 - << 'EOF'
import os, json
from pathlib import Path

BASE   = Path(".")
iso2   = "{iso2}"
src    = BASE / "source" / iso2

# Leer source_format (y el mapa `sources:` de las fuentes mixtas) desde country_config si ya existe
config_path = BASE / "country_config" / f"{iso2}.yaml"
source_format = None
sources_map = []          # fuentes mixtas: [{pattern|era, format}, ...] — ver Paso 1b
if config_path.exists():
    try:
        import yaml
        cfg = yaml.safe_load(config_path.read_text())
        source_format = cfg.get("source_format")
        sources_map = cfg.get("sources") or []
    except Exception:
        pass

# ocr_required: False = nunca necesario | True = necesario | None = desconocido (sin config)
if source_format in ("pdf_digital", "html", "xml", "docx", "doc", "text_flat"):
    ocr_required = False
elif source_format in ("pdf_image", "pdf_poor_ocr"):
    ocr_required = True
else:
    ocr_required = None

# Inventario RECURSIVO (rglob) y por TODAS las extensiones: el raw/ curado viene en
# subdirectorios por año (es/raw/1977/) o por formato (cl/raw/{ocr,pdf,xml},
# pt/raw/{html,xml_json}). Un iterdir() plano sobre .pdf/.html ve CERO archivos.
EXTS = ('.pdf', '.html', '.xml', '.docx', '.doc', '.txt')
raw_files = {p.stem: p for p in sorted((src / "raw").rglob("*"))
             if p.is_file() and p.suffix.lower() in EXTS}
sessions = sorted(raw_files)

# check_ocr devuelve True (completo) | False (pendiente) | "SKIP" (no aplica)
# El formato se decide POR ARCHIVO: primero el mapa `sources:` (pattern/era — resuelve los
# .pdf mixtos de PA/UY), luego el sufijo, luego el source_format del país.
import fnmatch
def formato_de(s):
    rel = str(raw_files[s].relative_to(src))
    for e in sources_map:                      # gana la entrada más específica: pattern > era
        if e.get("pattern") and fnmatch.fnmatch(rel, e["pattern"]):
            return e["format"]
    anio = next((int(t[:4]) for t in (raw_files[s].stem,) if t[:4].isdigit()), None)
    for e in sources_map:
        if e.get("era") and anio is not None:
            a, b = str(e["era"]).split("-")
            if int(a) <= anio <= int(b):
                return e["format"]
    return None                                # sin entrada: decide el sufijo / source_format
def check_ocr(s):
    fmt = formato_de(s)
    if fmt in ("pdf_digital", "html", "xml", "docx", "doc", "text_flat"):
        return "SKIP"
    if fmt in ("pdf_image", "pdf_poor_ocr"):
        return any((src/"ocr"/s).glob("*.txt")) if (src/"ocr"/s).exists() else False
    if raw_files[s].suffix.lower() in ('.txt', '.html', '.xml', '.docx', '.doc'):
        return "SKIP"
    if ocr_required is False:
        return "SKIP"
    if ocr_required is None:
        # Heurística: extracted/ presente pero ocr/ ausente → probablemente formato digital
        if (src/"extracted"/f"{s}.txt").exists() and not (src/"ocr"/s).exists():
            return "SKIP"
    return any((src/"ocr"/s).glob("*.txt")) if (src/"ocr"/s).exists() else False

# Comprobaciones por sesión
skill_checks = {
    "diaries-ocr":       check_ocr,
    "diaries-extract":   lambda s: (src/"extracted"/f"{s}.txt").exists() and (src/"extracted"/f"{s}.txt").stat().st_size > 100,
    "diaries-correct":   lambda s: (src/"corrected"/f"{s}.txt").exists() and (src/"corrected"/f"{s}.txt").stat().st_size > 100,
    "diaries-tag":       lambda s: (src/"tagged"/f"{s}.txt").exists() and (src/"tagged"/f"{s}.txt").stat().st_size > 100,
    "diaries-meta":      lambda s: (src/"meta"/f"{s}.json").exists(),
}

# Comprobaciones de nivel país
country_checks = {
    "diaries-matrix":      (src/"matrix"/"interventions_raw.csv").exists(),
    "diaries-deputies":    (src/"deputies"/"deputies.csv").exists(),
    "diaries-match":       (src/"match"/"matching_table.csv").exists(),
    "diaries-merge":       (src/"merge"/"interventions_enriched.csv").exists(),
    "diaries-standardize": (src/"standardize"/f"{iso2.upper()}_interventions.csv").exists(),
    "diaries-document":    (BASE/"docs"/iso2/"README.md").exists(),
}

# Verificar si ya existe un pipeline_state.json previo
state_path = BASE / "state" / iso2 / "pipeline_state.json"
has_state = state_path.exists()

inventory = {}
for s in sessions:
    inventory[s] = {skill: check(s) for skill, check in skill_checks.items()}

# Formato de celda: OK | SKIP | .
def fmt(v):
    if v is True:    return "OK"
    if v == "SKIP":  return "SKIP"
    return "."

# Imprimir resumen
SKILLS_ORDER = ["diaries-ocr","diaries-extract","diaries-correct","diaries-tag","diaries-meta"]
col_w = 10

header = f"{'session_id':<22}" + "".join(f"{sk.replace('diaries-',''):<{col_w}}" for sk in SKILLS_ORDER)
print(header)
print("-" * len(header))
for s, checks in inventory.items():
    row = f"{s:<22}" + "".join(f"{fmt(checks[sk]):<{col_w}}" for sk in SKILLS_ORDER)
    print(row)

print()
print("=== Nivel país ===")
for skill, done in country_checks.items():
    print(f"  {skill:<28} {'OK' if done else 'pendiente'}")

# Conteos — SKIP no cuenta como hecho ni como pendiente
def n_done(sk): return sum(1 for s in inventory if inventory[s][sk] is True)
def n_skip(sk): return sum(1 for s in inventory if inventory[s][sk] == "SKIP")

total = len(sessions)
print()
print(f"Total sesiones: {total}")
for sk in SKILLS_ORDER:
    nd = n_done(sk)
    ns = n_skip(sk)
    applicable = total - ns
    pct = nd / applicable * 100 if applicable else 100
    skip_note = f"  (+ {ns} SKIP)" if ns > 0 else ""
    print(f"  {sk:<28} {nd:>4}/{applicable}{skip_note}  ({pct:.0f}%)")

print()
print(f"pipeline_state.json existente: {'SÍ' if has_state else 'NO'}")
if source_format:
    print(f"source_format detectado:       {source_format}")
else:
    print(f"source_format:                 (no hay country_config todavía)")
EOF
```

### Interpretar el inventario

Con los resultados, determina:

**A. Sesiones completamente vírgenes** — ninguna etapa procesada → `status: pending`

**B. Sesiones parcialmente procesadas** — algunas etapas tienen output → marca las etapas completas como `complete (detectado)` y las restantes como `pending`

**C. Sesiones completamente procesadas hasta alguna etapa** — p.ej. todas tienen `corrected/` pero ninguna tiene `tagged/` → el pipeline puede arrancar desde `diaries-tag`

**D. Estado del nivel país** — si `interventions_raw.csv` existe, `diaries-matrix` puede estar parcialmente completo; si `deputies.csv` existe, `diaries-deputies` está hecho; etc.

**E. OCR vacío con fuente sin OCR** — `ocr/` no existe o está vacío pero `extracted/` tiene contenido, o el formato (del país o del ARCHIVO según `sources:`) es `pdf_digital`/`html`/`xml`/`docx`/`doc`/`text_flat` → el inventario muestra `SKIP` para `diaries-ocr`. Es estado **normal y correcto**: solo `pdf_image`/`pdf_poor_ocr` necesitan OCR. No se trata como pendiente. El pipeline arranca directamente desde `diaries-correct` (o la primera etapa sin output).

### Si existe pipeline_state.json previo

Si `state/{iso2}/pipeline_state.json` ya existe:
- Léelo: `cat state/{iso2}/pipeline_state.json`
- **No lo sobreescribas** — en su lugar, fusiona: añade sesiones nuevas que aparezcan en `raw/` pero no en el estado, y actualiza sesiones marcadas como `pending` si el inventario detecta que ya tienen output.
- Informa al usuario: "Encontré un estado previo con {N} sesiones. He fusionado {M} sesiones nuevas y actualizado {K} estados según los archivos encontrados."
- Si hay inconsistencias graves (p.ej. sesión marcada `complete` en el estado pero sin archivo de output), señálalo como advertencia sin modificar ese registro.

---

## Paso 1 — Fase 1: Inferencia automática

### 1a. Elegir los archivos fuente para análisis de patrones

Prioridad de fuentes para extraer patrones:
1. Si hay archivos en `corrected/` → usar esos (texto ya limpio, mejor calidad)
2. Si hay archivos en `extracted/` → usar esos
3. Si no hay ninguno → usar los archivos `raw/` directamente

```bash
# Verificar qué está disponible
ls source/{iso2}/corrected/ 2>/dev/null | head -5 || echo "(vacío)"
ls source/{iso2}/extracted/ 2>/dev/null | head -5 || echo "(vacío)"
```

Selecciona hasta 5 archivos de la fuente de mejor calidad disponible (primero, último y 3 intermedios).

### 1b. Determinar el formato de fuente

Si los archivos a analizar son de `corrected/` o `extracted/`, el formato ya fue procesado previamente. En ese caso:
- Intenta inferirlo desde el contenido del texto (¿hay marcas de OCR? ¿es HTML convertido?)
- O pregunta directamente al usuario: "¿Sabes cuál es el formato original? (pdf_image / pdf_digital / pdf_poor_ocr / html / xml / docx / doc / text_flat)"
- Marca `source_format` con confianza 0.70 si se infirió del texto, o 1.0 si el usuario lo confirmó.

Si los archivos son de `raw/`, ejecuta la detección **estructural por año** (discriminador FIABLE):

```bash
python3 ~/.claude/skills/diaries-lib/lib/utils/assess_source.py --country {iso2}
```

Clasifica cada año como DIGITAL / ESCANEADO / MIXTO según la ESTRUCTURA del PDF (capa de
imagen vía `pdfimages`), NO según métricas de carácter. Mapeo a `source_format`:
- Año **DIGITAL** (sin capa de imagen) → `pdf_digital` → texto embebido, OMITIR OCR.
- Año **ESCANEADO/MIXTO** (capa de imagen) → `pdf_image` → capa OCR de calidad desconocida.

⚠ CRÍTICO — NO decidir OCR/embebido por `chars_per_page`: un escaneo tiene chars 100%
válidos aunque columnas y párrafos estén rotos (destruye intervenciones sin que el char-count
lo vea). Para años ESCANEADOS confirmar OCR-fresco vs embebido con TEST EMPÍRICO de extracción
en 2-3 sesiones; ante la duda, OCR. Registrar la frontera por año (eras mixtas como UY:
escaneado 1985–2000, digital 2002+ → años digitales se marcan `diaries-ocr: skipped`).

**El formato se detecta y registra POR ARCHIVO, no como un único `source_format` de país.** El
`source_format` global queda como formato DOMINANTE (compatibilidad); para las fuentes mixtas el
config lleva además un mapa de fuentes:

```yaml
source_format: pdf_image          # dominante (compatibilidad)
sources:                          # mapa POR ARCHIVO/ERA — gana la entrada más específica
  - {pattern: "raw/xml/*",  format: xml}         # PT: xml + html · CL: xml + doc + pdf
  - {pattern: "raw/pdf/*",  format: pdf_digital} #   (CL: mejor fuente POR SESIÓN)
  - {era: "1985-2000",      format: pdf_image}   # PA/UY: pdf_digital + ocr_pages según era
  - {pattern: "raw/**/*.txt", format: text_flat}
```

`extract` y `ocr` enrutan CADA sesión por este mapa; `pdf_digital` y `ocr_pages` ya no son
excluyentes a nivel país.

⚠ **Un `.txt` en `raw/` significa «ya extraído hasta aquí»**: se registra `text_flat` y **NO se
re-OCR-ea** aunque el país sea escaneado. Su ruta es `diaries-extract` en modo `text_flat`
(pass-through fiel).

### 1c. Extraer texto para análisis de patrones

Toma los archivos seleccionados en 1a. Extrae las primeras 100 líneas de cada uno:

**Si son .txt (extracted/ o corrected/):**
```bash
head -100 {ruta_archivo}
```

**Si son .pdf (raw/):**
```bash
python3 -c "
import fitz
doc = fitz.open('{ruta_completa}')
lines = []
for page in doc[:5]:
    lines.extend(page.get_text().splitlines())
    if len(lines) >= 100: break
print('\n'.join(lines[:100]))
"
```

**Si son .html:**
```bash
python3 -c "
from bs4 import BeautifulSoup
soup = BeautifulSoup(open('{ruta_completa}').read(), 'html.parser')
print('\n'.join(soup.get_text().splitlines()[:100]))
"
```

### 1d. Verificar integridad del prefijo de orador en fuentes escaneadas

**Antes de inferir patrones**, si los archivos a analizar son de fuentes escaneadas
(`pdf_poor_ocr` o `pdf_image`), ejecuta este chequeo crítico en la muestra de texto.

El chequeo es **genérico** — no asume ningún prefijo concreto. Funciona en cualquier idioma:

```python
import re

# 1. Identificar líneas candidatas a turno de orador por estructura posicional:
#    - Línea corta (< 60 chars)
#    - Empieza con mayúscula
#    - Termina en ".-"  o  ":"  (marcadores universales de turno de palabra)
candidate_lines = [
    l.strip() for l in text.splitlines()
    if re.match(r'^[A-ZÁÉÍÓÚÜÑÀÃÂÊÍÔÕÇ][^\n]{3,55}(\.-|:)\s*$', l.strip())
]

# 2. Detectar síntomas de corrupción OCR en esas líneas:
#    Caracteres que no deben aparecer dentro de un nombre propio en mayúsculas:
#    ~  '  ^  _  {  }  |  \  y letras minúsculas intercaladas en palabra mayúscula
CORRUPTION_RE = re.compile(r"[~'`^_|\\{}]|[A-Z][a-z]{1,2}[A-Z]")

corrupted = [l for l in candidate_lines if CORRUPTION_RE.search(l)]
clean     = [l for l in candidate_lines if not CORRUPTION_RE.search(l)]

total = len(candidate_lines)
garble_ratio = len(corrupted) / total if total > 0 else 0
```

Muestra al usuario los primeros 5 ejemplos de líneas corrompidas para que pueda juzgar:
```
Líneas candidatas a orador con corrupción detectada:
  'SEROR BOUZA.-'          ← 'Ñ' → 'R'  (español)
  'SEfloR GARCIA.-'        ← 'Ñ' → 'fl' (ligadura)
  "SENHOR SILVA.-"         ← OK en portugués (no es corrupción)
  'DEPUTADO FARIA.-'       ← OK en portugués
```

**Importante:** algunas variantes son correctas en ciertos idiomas (ej: `SENHOR` en
portugués, `SR.` en castellano antiguo, `DIPUTADO` sin prefijo). Claude debe razonar sobre
si las "anomalías" son corrupción real o simplemente el estilo del país/época.

Si `garble_ratio > 0.40` Y los ejemplos muestran corrupción real (no estilo legítimo):
- Informa: `"Texto embebido posiblemente corrupto para tagging ({garble_ratio:.0%} de
  candidatos afectados). Ejemplos: {corrupted[:3]}"`
- Registra `source_format: pdf_poor_ocr` y marca OCR como obligatorio.
- En `pipeline_state.json`, esas sesiones deben tener `diaries-ocr.status: pending`.

**Por qué esto importa:** `valid_ratio=0.98` puede convivir con caracteres específicos
corrompidos que rompen el regex de tagging. En un test con diarios de Uruguay 1987, el
texto embebido detectó 14 intervenciones; el OCR detectó 164. La diferencia fue un único
carácter mal codificado en el prefijo de orador. Este error no es recuperable aguas abajo.

### 1e. Inferir patrones desde el texto

Analiza el texto con tu propio juicio como LLM. Para cada campo, busca evidencia concreta:

| Campo | Qué buscar | Confianza alta si... |
|-------|-----------|----------------------|
| `speaker_tag_patterns` | Líneas que empiezan con nombre de orador seguido de `:` | ≥ 5 coincidencias del mismo patrón |
| `speaker_prefix_strip` | Prefijos como "El Sr.", "La Sra.", "SEÑOR" antes del nombre | ≥ 3 variantes consistentes |
| `president_tag` | Línea que identifica al presidente de la cámara | ≥ 2 ocurrencias |
| `session_number_regex` | Patrón de número de sesión ("Núm. 12", "Sesión 5ª") | En ≥ 2 documentos distintos |
| `session_date_regex` | Patrón de fecha ("12 de febrero de 1932") | ≥ 3 ejemplos con mismo formato |
| `session_type_keywords` | "ordinaria", "extraordinaria", etc. | ≥ 2 tipos distintos |

Si los archivos son de `tagged/`, extrae también los patrones de etiquetado `<int speaker="...">` ya presentes — eso revela los patrones confirmados en sesiones anteriores.

---

## Paso 2 — Fase 2: Entrevista dirigida

Para cada campo con confianza < 0.80, muestra la evidencia y pregunta al usuario.

**Si el inventario muestra que ya hay sesiones procesadas con éxito**, reduce la entrevista: los patrones que funcionaron antes son evidencia de alta confianza. Menciona: "Detecté {N} sesiones ya etiquetadas — he tomado sus patrones como referencia."

Formato de pregunta:
```
Campo: speaker_tag_patterns
Encontré este patrón en {N} casos:
  "{ejemplo_1}"
  "{ejemplo_2}"
Regex inferido: `^(?:El\s+)?Sr\.\s+([A-ZÁÉÍÓÚÜÑ][A-Z\s]+):`
¿Es correcto? ¿Hay otros formatos de orador que no aparecen aquí?
[Confirmar / Corregir: ...]
```

Reglas:
- Si el usuario confirma un patrón de orador, deduce los prefijos y omite esa pregunta.
- Si el usuario proporciona el regex correcto, úsalo directamente (confianza = 1.0).
- Si el usuario dice "no sé", deja la inferencia con `needs_review: true`.
- Máximo 8 preguntas. Agrupa las relacionadas.

---

## Paso 3 — Escribir `country_config/{iso2}.yaml`

Lee el template:
```
~/.claude/skills/diaries-lib/templates/_template.yaml
```

Si ya existe `country_config/{iso2}.yaml`, léelo primero y actualiza solo los campos que han mejorado (confianza más alta o confirmados por el usuario). No sobreescribas campos que ya tienen `needs_review: false`.

Escribe (o actualiza) `country_config/{iso2}.yaml` con todos los campos inferidos/confirmados. Para campos no confirmados, añade `# inferido, confianza={X}`.

---

## Paso 4 — Inicializar (o actualizar) `state/{iso2}/pipeline_state.json`

### Si NO existe el estado previo

Crea el directorio:
```bash
mkdir -p state/{iso2}/
```

Construye el JSON usando el inventario del Paso 0b. Para cada sesión:
- Por cada skill de sesión:
  - Si el inventario devolvió `True` → `status: "complete"`, `confidence: null`, `note: "detectado en bootstrap"`
  - Si el inventario devolvió `"SKIP"` → `status: "skipped"`, `note: "no requerido para formato {source_format}"`
  - Si el inventario devolvió `False` → `status: "pending"`
- **Para `diaries-ocr` sin `country_config` todavía**: omitir la entrada (se establecerá cuando se ejecute el skill y conozca el formato)
- Para skills de nivel país: si el Paso 0b detectó el archivo → `status: "complete"`, `note: "detectado en bootstrap"`; si no → omitir (se crearán cuando se ejecuten)

```json
{
  "country": "{iso2}",
  "current_skill": "",
  "global_rules": [],
  "onboarding_report": "docs/{iso2}/onboarding_report.md",
  "sessions": {
    "{session_id}": {
      "skills": {
        "diaries-ocr": {
          "status": "skipped",
          "confidence": null,
          "output_path": null,
          "corrections": [],
          "note": "no requerido para formato pdf_digital",
          "started_at": null,
          "completed_at": null,
          "error_message": null
        },
        "diaries-extract": {
          "status": "complete",
          "confidence": null,
          "output_path": "source/{iso2}/extracted/{session_id}.txt",
          "corrections": [],
          "note": "detectado en bootstrap",
          "started_at": null,
          "completed_at": null,
          "error_message": null
        },
        "diaries-tag": {
          "status": "pending",
          "confidence": null,
          "output_path": null,
          "corrections": [],
          "started_at": null,
          "completed_at": null,
          "error_message": null
        }
      }
    }
  }
}
```

### Si YA existe el estado previo

Fusiona: añade sesiones nuevas con su estado detectado. Para sesiones existentes marcadas como `pending`, actualiza a `complete` si el inventario encontró output. No modifica sesiones con status `complete`, `flag` o `halt` ya establecidos.

---

## Paso 5 — Generar informe de configuración

```bash
mkdir -p docs/{iso2}/
```

Escribe `docs/{iso2}/onboarding_report.md`:

```markdown
# Informe de configuración — {iso2}

Generado: {fecha_actual}

## Estado detectado al iniciar bootstrap

| Etapa | Sesiones completas | Sesiones pendientes | % hecho |
|-------|--------------------|---------------------|---------|
| diaries-ocr | {N} | {M} | {%} |
| diaries-extract | {N} | {M} | {%} |
| diaries-correct | {N} | {M} | {%} |
| diaries-tag | {N} | {M} | {%} |
| diaries-meta | {N} | {M} | {%} |
| diaries-matrix (país) | {OK/pendiente} | — | — |
| diaries-deputies (país) | {OK/pendiente} | — | — |
| diaries-match (país) | {OK/pendiente} | — | — |
| diaries-merge (país) | {OK/pendiente} | — | — |
| diaries-standardize (país) | {OK/pendiente} | — | — |

## Formato de fuente
- **source_format**: {valor} (confianza: {X})

## Patrones inferidos

| Campo | Valor | Confianza | Fuente |
|-------|-------|-----------|--------|
| speaker_tag_patterns | ... | 0.XX | inferido/confirmado/detectado_de_tagged |
| president_tag | ... | 0.XX | ... |
| session_number_regex | ... | 0.XX | ... |
| session_date_regex | ... | 0.XX | ... |
| session_type_keywords | ... | 0.XX | ... |

## Sesiones descubiertas
- **Total**: {N} archivos en source/{iso2}/raw/
- **Con trabajo previo**: {K}
- **Vírgenes**: {N-K}

## Campos que requieren revisión posterior
{lista de campos con needs_review: true, o "Ninguno"}
```

---

## Paso 6 — Resumen final

Imprime un resumen orientado a la acción:

```
Bootstrap completado para: {iso2}
  source_format:    {valor}
  Sesiones totales: {N}

Estado detectado:
  ✓ diaries-extract   {N_ext}/{N} sesiones ya procesadas
  ✓ diaries-correct   {N_cor}/{N} sesiones ya procesadas
  ✗ diaries-tag       0/{N} — pendiente
  ✗ diaries-meta      0/{N} — pendiente
  ...

Archivos generados:
  country_config/{iso2}.yaml
  state/{iso2}/pipeline_state.json
  docs/{iso2}/onboarding_report.md

Próximos pasos recomendados:
  {lista de skills pendientes, en orden, con el comando exacto a ejecutar}
```

Si todo el pipeline de sesiones está completo pero falta algún skill de nivel país:
```
  Las sesiones ya están procesadas. Continúa con:
  /diaries-deputies --country {iso2}
```

Si hay sesiones parcialmente procesadas:
```
  Las sesiones están en distintos estados. Revisa el estado completo con:
  /diaries-status --country {iso2}
  Luego ejecuta el skill correspondiente a la etapa pendiente más temprana.
```

---

## ⚠⚠ REPRODUCIBILIDAD — el código del país vive en el REPOSITORIO, nunca en el scratchpad

Cuando un país necesita una tubería propia —y varios la necesitan: el pipeline genérico de
`lib/utils/` no basta para su `meta`, su `correct` o su `extract`— **ese código es parte del
corpus, no material de trabajo**. Escríbelo o muévelo a `scripts/campana_reproceso/{iso}_{etapa}/`
y no lo dejes en el directorio temporal de la sesión.

El motivo, medido el 2026-08-29 (`tr-0097`, `tr-0098`): la campaña entera del reproceso —**2.417
scripts y 65 informes**, con `extract`, `correct`, `meta` y `dedupe` de prácticamente los dieciséis
países— vivía únicamente en `/private/tmp/…/scratchpad/` y en dos directorios del home, con las
rutas codificadas dentro de los scripts. `/tmp` se limpia solo. Sin ese código, CO y EC habrían
quedado con un `meta` de 0,99 de confianza **que nadie sabría reproducir**, y rehacerlo con el
extractor genérico les quitaba 1.600 presidencias.

Reglas prácticas:
- El **código y los informes** van sin comprimir: hay que poder leerlos, compararlos y ejecutarlos.
- Los **datos de trabajo** que los scripts leen como entrada (`inventory.csv`, `names.json`,
  `audit_config.json`…) **van con el código, comprimidos junto a él**: sin `names.json` la tubería
  de PA no arranca. ⚠ No los dejes en una carpeta aparte: los de la campaña de 2026 vivían en
  `backup/campana_reproceso/` y desaparecieron con ella el 2026-09-06, dejando diez scripts del
  archivo sin sus entradas.
- **Nada de rutas al scratchpad** dentro de los scripts.
- El informe importa tanto como el código: `co_meta/INFORME.md` documenta el *estancio* de la
  Gaceta del Congreso y la medida que lo valida. Sin él queda el cómo y se pierde el porqué.
