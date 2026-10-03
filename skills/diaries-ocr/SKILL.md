---
name: diaries-ocr
description: "Aplica OCR con Ollama a sesiones en formato pdf_image o pdf_poor_ocr y actualiza el estado del pipeline."
allowed-tools: [Read, Write, Edit, Bash]
---

Argumentos: `--country {iso2}` + uno de `--session YYYY-MM-DD` | `--batch YYYY-MM` | `--all` + opcionales `--force`, `--dry-run`

## Nota sobre modelos y rendimiento (verificado empíricamente en UY M3 Max, 2026-06)

**Modelo:** `Maternion/LightOnOCR-2:1b` primario (mejor calidad/velocidad), `glm-ocr` fallback
por defecto. **El fallback es configurable por país** (`ocr.fallback_model`; `ec.yaml` usa
`deepseek-ocr`) — glm-ocr es solo el default. No hay modelo local más rápido con calidad
equivalente (deepseek-ocr ~10 s, glm-ocr ~22 s vs LightOnOCR ~8 s/página). Configurado en
`country_config` (`ocr.primary_model` / `ocr.fallback_model`).

**⚠ CAUSA #1 DE LENTITUD — procesos huérfanos.** Batches OCR abortados dejan subprocesos vivos
compitiendo por el GPU (medido: 20 procesos → throughput cae de ~700 a ~160 pág/h). Una latencia
"de 63 s/página" suele ser 100% contaminación; la latencia LIMPIA real es ~8 s. SIEMPRE: matar
huérfanos (`pkill -f ocr_pages`) + lockfile antes de un batch, y MEDIR limpio (sin batch corriendo)
antes de diagnosticar config. Ver memoria `feedback_ocr_throughput.md`.

**El GPU satura con UNA inferencia.** El paralelismo ayuda poco: 1 worker ≈ 496, 6 workers ≈ 756
pág/h (páginas ligeras). Óptimo: `workers = ollama_num_parallel = 6`. 8 PERJUDICA (contención de KV).

**DPI 150 == DPI 300** en calidad Y velocidad (el modelo redimensiona internamente). Usar 150
(menos overhead de PNG). `ocr.dpi: 150` en el config.

**El coste escala con CHARS de salida (densidad), no con páginas.** Trabajar en chars/hora
(invariante a densidad), no pág/hora. Para estimar tiempos: `random.sample()` sobre el rango
COMPLETO de páginas de VARIOS documentos y VARIOS años — NUNCA las primeras páginas (carátula/
índice son ~1.4x más ligeras) ni un solo año. En UY el sesgo combinado infló el estimado 3x.

**Paralelización a nivel de PÁGINA > a nivel de sesión** (un solo proceso, GPU sin huecos entre
sesiones, checkpoint fino, imposible generar zombies). El render (fitz) bajo lock; el OCR concurrente
(libera GIL en la espera HTTP).

**Para corpus urgentes/grandes:** vLLM en GPU NVIDIA cloud = ~90x (LightOnOCR-1B: 5.71 pág/s en
H100 ≈ 20.500 pág/h; ~$12 por 80.000 páginas). Es el despliegue nativo del modelo. Local Ollama
es el techo sin coste.

**Arranque de Ollama antes de un batch largo** (`KEEP_ALIVE=-1` → el modelo nunca se descarga):
```bash
pkill -9 -f ollama; sleep 3
OLLAMA_NUM_PARALLEL=6 OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_KEEP_ALIVE=-1 \
  ollama serve > /tmp/ollama_{iso2}.log 2>&1 &
sleep 5
ollama run {ocr.primary_model} "test" 2>/dev/null  # pre-cargar modelo
```

---

## ⚠ UN SOLO TRABAJO DE OCR A LA VEZ EN LA MÁQUINA

**Antes de lanzar cualquier OCR, comprueba que no hay otro corriendo.** Dos procesos peleándose
por la GPU no se reparten el trabajo: **el segundo falla entero y en silencio**.

```bash
pgrep -fl "ocr_pages|run_ocr_batch|reocr" || echo "libre"
ls logs/ocr_*.lock 2>/dev/null
```

Verificado el 2026-08-03: con el re-OCR de EC en marcha se lanzó el OCR de **un solo** PDF de CL
(196 páginas). Falló en las 196, todas con el mismo error de Metal —
`Unable to reach MTLCompilerService … Reentrancy avoided` → `failed to initialize the Metal
library`. Ninguna página escrita. El error **no dice «GPU ocupada»**: dice que no puede compilar
el kernel, que parece un problema de instalación y lleva a diagnosticar la máquina en vez de la
concurrencia.

Dos consecuencias prácticas:

- **Lo que se pierde no es solo el trabajo nuevo**: el riesgo real es tumbar el trabajo LARGO que
  ya llevaba días. Tras el fallo hay que **verificar el proceso largo** —que sigue vivo y que
  sigue ESCRIBIENDO— y no darlo por bueno solo porque el PID exista:
  `find <dir> -name 'page_*.txt' -mmin -10 | wc -l` debe ser > 0.
- **Un OCR pequeño no es una excepción**: 196 páginas bastaron. No hay tamaño seguro; lo que
  colisiona es la inicialización del backend, no el volumen.

Si hay un OCR largo en curso, **el trabajo pequeño espera**. No es un cuello de botella real:
el corpus grande termina antes si nadie lo interrumpe.

## Procesos OCR de larga duración (corpus grandes, días/semanas): control AUTO-CURATIVO obligatorio

Un OCR de decenas de miles de páginas corre **días o semanas**. En ese horizonte nada frágil
sobrevive, y la regla es: **el proceso debe seguir solo, detectar su propia degradación y
corregirla sin que nadie vuelva a mirarlo.** No basta con que "persista": tiene que
AUTO-CORREGIRSE en runtime y MEDIR su desempeño continuamente. Lecciones verificadas (UY, 2026-06):

**Lo que NO sobrevive — no usar para batches largos:**
- **Background del harness / `nohup` / `&`**: el harness barre el árbol de procesos en los gaps
  de sesión. Mueren por la noche.
- **Cron de sesión (`CronCreate` session-only)**: NO dispara en idle prolongado — el tick se
  pierde si nadie interactúa. Inservible como red de seguridad nocturna.
- **Daemon local con doble-fork (`PPID=1`)**: también lo barre la limpieza del harness.

**Único mecanismo robusto: servicio del sistema (macOS `launchd` LaunchAgent; en Linux
`systemd --user` con `Restart=always`) AUTO-CURATIVO de 3 capas que se vigilan entre sí:**

1. **LaunchAgent con `KeepAlive=true` INCONDICIONAL** → launchd reinicia el runner SIEMPRE que
   muera. ⚠ NO usar `KeepAlive={SuccessfulExit:false}`: si el runner sale con código 0 sin haber
   completado, queda muerto y nadie lo revive (bug real cometido). `RunAtLoad=true` para revivir
   tras reinicio de máquina. El wrapper se **auto-desinstala** (`launchctl unload` + borrar el
   plist) al detectar la salida completa, para romper el bucle de reinicios.

2. **Wrapper auto-saneante** (lo que ejecuta launchd): en CADA arranque, ANTES de lanzar el runner,
   garantiza el entorno óptimo — **exactamente 1 `ollama serve`** (mata duplicados) y **0 runners
   huérfanos**. Los Ollama duplicados son la CAUSA #1 de lentitud (contención de GPU: ~140 pág/h
   con 2 vs ~300 limpio) y reaparecen solos tras cada relanzamiento.

3. **Guardian interno en el runner** (hilo `daemon`, cada ~90 s): fuerza `os._exit(1)` —y deja que
   launchd reinicie limpio— cuando detecta:
   - **estancamiento**: sin avance de páginas en > N s (p.ej. 420; resetear el contador antes del
     paso de extract/finalize para no falsear un estancamiento).
   - **contención**: `pgrep -f 'ollama serve'` devuelve > 1.
   Además, **timeout HTTP por página**: usar `ollama.Client(timeout=120)`, NO `ollama.chat()` sin
   timeout (una request colgada bloquea para siempre). En timeout/error → escribir un fallback y
   seguir, nunca bloquear.

**Checkpoint por página OBLIGATORIO** (saltar `page_*.txt` ya escritas con tamaño > 0): cada
reinicio continúa sin repetir trabajo. Sin esto, el ciclo reiniciar→reanudar no converge.

**SIEMPRE medir y registrar el desempeño** — no asumir que va bien: el runner escribe un
`health.log` con marca de tiempo (ritmo en pág/h cada N páginas, saneos del guardian, reinicios).
Permite AVERIGUAR el desempeño días después sin estar presente. Un ritmo bajo casi siempre es
contención (huérfanos), no el modelo: medir el ritmo LIMPIO (1 solo Ollama) antes de tocar la config.

> Plantilla de referencia de las 3 capas (UY): `~/.parlaibero/run_hybrid_uy.py` (runner + guardian),
> `~/.parlaibero/ocr_uy_service.sh` (wrapper saneante), `~/Library/LaunchAgents/com.parlaibero.ocr-uy.plist`.
> Adaptarla cambiando rutas, sesiones y objetivo. Ver memoria `country_uy.md` (lección de control automático).

---

## Paso 0 — Leer configuración del país

Lee `country_config/{iso2}.yaml`.

Extrae:
- `source_format`
- `ocr.dpi` (default: 150 — 150 == 300 en calidad/velocidad)
- `ocr.primary_model` (default: `null` → usa el PRIMARY_MODEL del cliente)
- `ocr.fallback_model` (default: `glm-ocr` — configurable por país; `ec.yaml` usa `deepseek-ocr`)
- `ocr.workers` (default: 6 — óptimo en Apple Silicon; el GPU satura con 1 inferencia)
- `ocr.ollama_num_parallel` (default: 6 — debe igualar a `ocr.workers`)
- `threshold_auto` (default: 0.85)
- `threshold_flag` (default: 0.65)

Antes de un batch largo: matar huérfanos y arrancar Ollama (`KEEP_ALIVE=-1` → modelo siempre cargado):
```bash
pkill -9 -f "ocr_pages"; pkill -9 -f ollama; sleep 3
OLLAMA_NUM_PARALLEL={ocr.ollama_num_parallel} OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_KEEP_ALIVE=-1 \
  ollama serve > /tmp/ollama_{iso2}.log 2>&1 &
sleep 5
ollama run {ocr.primary_model} "test" 2>/dev/null  # pre-cargar modelo
```

### Si source_format es `pdf_digital` o `html`:

Imprime:
```
Formato {source_format} no requiere OCR. Skill omitido.
Las sesiones permanecen en estado pending para diaries-extract.
Ejecuta: /diaries-extract --country {iso2} --all
```
Termina sin modificar el estado.

---

## Paso 1 — Determinar lista de sesiones

### Según el modo de invocación:

**`--session YYYY-MM-DD`**: un solo archivo `source/{iso2}/raw/YYYY-MM-DD.*`

**`--batch YYYY-MM`**: todos los archivos en `source/{iso2}/raw/` cuyo nombre empieza por `YYYY-MM`
```bash
ls source/{iso2}/raw/ | grep "^YYYY-MM"
```

**`--all`**: todos los archivos en `source/{iso2}/raw/`
```bash
ls source/{iso2}/raw/
```

### Filtrar sesiones ya completadas (salvo `--force`):

Lee `state/{iso2}/pipeline_state.json`.

Excluye sesiones donde `sessions.{session_id}.skills.diaries-ocr.status` sea `"complete"` o `"skipped"` (las `skipped` son sesiones de formato digital que no requieren OCR).

Con `--force`: procesa todas las sesiones del rango sin excluir.

Si tras filtrar la lista queda vacía: imprime "No hay sesiones pendientes para diaries-ocr." y termina.

---

## Paso 2 — Procesar cada sesión

Para cada `session_id` en la lista:

### 2a. Localizar el archivo fuente

```bash
ls source/{iso2}/raw/{session_id}.*
```

Si no existe: registra error para esa sesión y continúa con la siguiente.

### 2b. Crear directorio de salida

```bash
mkdir -p source/{iso2}/ocr/{session_id}/
```

### 2c. Ejecutar OCR

Si `--dry-run`: imprime el comando que se ejecutaría y salta al siguiente. No ejecutes ni actualices estado.

Si no es dry-run y el batch es grande (cientos/miles de sesiones), NO lances el OCR a mano ni
escribas un runner por país — usa el genérico, que se parametriza desde `ocr:` del
`country_config`:

```bash
python3 ~/.claude/skills/diaries-lib/lib/utils/run_ocr_batch.py --country {iso2} --dry-run
nohup python3 ~/.claude/skills/diaries-lib/lib/utils/run_ocr_batch.py --country {iso2} > /dev/null 2>&1 &
python3 ~/.claude/skills/diaries-lib/lib/utils/run_ocr_batch.py --country {iso2} --progress
```

Cola global de páginas de todas las sesiones con `ThreadPoolExecutor(ocr.workers)`, checkpoint
por página, limpieza de huérfanos al arrancar y lockfile contra batches simultáneos.

⚠ Evita la paralelización a nivel de SESIÓN con subprocesos: deja el GPU ocioso entre páginas de
una misma sesión (~345 vs ~700 pág/h) y los subprocesos huérfanos degradan el throughput.

⚠ **Hasta 2026-08-02 este skill mandaba copiar `run_ocr_uy.py` como «patrón de referencia».**
Tenía el país, las rutas, el modelo y los umbrales a fuego, y desde que el código pasó a
`~/.claude/skills/` apuntaba a un `lib/utils/update_state.py` inexistente: **estaba roto y solo
se habría descubierto al usarlo en Ecuador**. Un patrón que se copia no se mantiene.

⚠⚠ **`--dry-run` no debe escribir NADA, y el original sí lo hacía.** Su auditoría de pre-vuelo
borraba las páginas vacías o truncadas *antes* de comprobar si era simulación: una invocación
anunciada como «sin ejecutar» se llevó 984 páginas de UY (16 sesiones). Ya está corregido —en
simulación las cuenta y las deja—, pero la lección va más allá de este script: **una bandera de
simulación que modifica datos es peor que no tenerla**, porque invita a ejecutarla sin pensar.

Para sesiones individuales o batches pequeños (≤10):
```bash
python ~/.claude/skills/diaries-lib/lib/utils/ocr_pages.py \
  --input "source/{iso2}/raw/{session_id}.pdf" \
  --output-dir "source/{iso2}/ocr/{session_id}/" \
  --dpi {ocr.dpi} \
  --model {ocr.primary_model}   # omitir si primary_model no está en el config
```

Lee el JSON de stdout. Estructura esperada (los campos REALES de `ocr_pages.py`):
```json
{
  "status": "ok",
  "pages": [
    {"page": 1, "chars": 2841, "confidence": 0.91, "model": "...", "suspicious": false, "error": null}
  ],
  "mean_confidence": 0.87,
  "min_confidence": 0.42,
  "output_dir": "source/{iso2}/ocr/{session_id}/"
}
```
No existe ningún campo `low_confidence_pages`: las páginas dudosas son las que llevan
`pages[].suspicious: true` (confidence < 0.50).

### 2d. Evaluar confianza y determinar status

`confidence = mean_confidence` del JSON.

Si alguna página lleva `pages[].suspicious: true` (confidence < 0.50): añade advertencia en el
resumen final; usa `min_confidence` para dimensionar el peor caso.

Determina status:
- `confidence >= threshold_auto` → `complete`
- `confidence >= threshold_flag` → `flag`
- `confidence < threshold_flag` → `halt`

### 2e. Actualizar estado

```bash
python ~/.claude/skills/diaries-lib/lib/utils/update_state.py \
  --country {iso2} \
  --skill diaries-ocr \
  --session {session_id} \
  --status {complete|flag|halt} \
  --confidence {valor} \
  --output "source/{iso2}/ocr/{session_id}/"
```

---

## Paso 2-bis — Cuatro fallos del OCR que NO lanzan error y hay que buscar activamente

### (a) Página ROTADA — comprobar la ORIENTACIÓN antes de gastar el OCR

Un escaneo cabeza abajo (180°) o de canto (90/270°) produce OCR **sin error y con métricas
normales**, pero texto ILEGIBLE: los glifos rotados se leen como otras letras (T→L, U→N, A→V,
C→O), de modo que `CONSTITUCIONALES` sale como `SATVNOIONLILENOO`.

⚠ **Es invisible para TODAS las métricas del skill**: `alpha_ratio` normal, 0 páginas vacías, sin
degeneración de tablas, confianza de sesión alta. Hallazgo EC (2026-07): 2 sesiones así
sobrevivieron a `extract`, `correct`, `meta` (fecha ilegible → contaban como "sesión sin fecha") y
`tag` (0 marcadores detectados), y solo se descubrieron 4 fases después, al bloquear el gate de
`diaries-matrix`. ⚠ **NO lo confundas con recorte de margen (caso b)**: el síntoma se parece —el
primer token de cada línea es basura— pero la causa y el arreglo son opuestos (el recorte es
irrecuperable; la rotación se arregla por completo).

**PRE-OCR — detección con el OSD de tesseract, por VOTO entre páginas:**

```bash
# por página: devuelve 'Orientation in degrees' y 'Rotate'
tesseract stdin stdout --psm 0 < pagina.png
```

La confianza del OSD es BAJA (7–31 medida en EC, tanto en aciertos como en normales), así que una
sola página NO decide: **muestrea 5–8 páginas de la sesión y vota**. Si gana un ángulo ≠ 0, aplica
la rotación al render antes de OCR-ear la sesión completa
(`fitz.Matrix(dpi/72, dpi/72) * fitz.Matrix(-1,0,0,-1,0,0)` para 180°).

**POST-OCR — validación por densidad de PALABRAS FUNCIÓN del idioma** (`de la que el en y a los
se del las por un con no una su para es al`), como red de seguridad si el OSD falla:

| | densidad |
|---|---|
| sesiones invertidas (EC) | **5,0 %** |
| mediana del corpus | 38,4 % |
| siguiente peor (OCR malo, no invertida) | 17,3 % |

El salto es limpio; el umbral **< 35 % de la mediana** no dio falsos positivos en 6.146 sesiones.

Re-OCR con la rotación correcta recupera la sesión POR COMPLETO (EC: 0 → 274 intervenciones,
fecha y nº de acta legibles, 0 residuales de tagging).

### (b) Escaneos recortados al margen — medir, documentar, NUNCA reconstruir

Hallazgo EC (2026-07): los escaneos de 1979–1994 están **cortados por el margen izquierdo** y
pierden la primera palabra de muchas líneas (en 1979, el 24 % de ellas). Verificado a nivel de
píxel: `CropBox == MediaBox`, es decir, **la pérdida es de la digitalización original y es
irrecuperable**.

⚠ **Es invisible para las métricas de confianza.** El `alpha_ratio` da 0,95 en una línea a la que
le falta la primera palabra: el texto que queda está perfectamente escrito. Detéctalo por
**LÉXICO**, no por métricas de carácter — `~/.claude/skills/diaries-lib/lib/utils/measure_edge_loss.py` mide la fracción de
líneas que empiezan por un token que no existe en el diccionario. Suelo normal 1–3 %; **> 10 %
indica recorte**.

⚠⚠ **NUNCA reconstruyas con un LLM lo que falta.** Medido en EC: **0 % de acierto** con dos
caracteres amputados, además de pérdida de alineación de líneas y sustituciones semánticamente
plausibles pero falsas — el peor tipo de error, porque es indetectable aguas abajo. El fallback con
LLM llegó a **fabricar un 7 % de caracteres inventados** en las páginas de sombra, y el control de
calidad del híbrido nunca se disparó porque era ciego al daño de borde. **Tesseract puro es más
defendible**: pierde texto, pero no lo inventa.

Sí es legítimo normalizar por reglas lo que sea **vocabulario cerrado** (marcadores de orador,
fórmulas de cabecera), donde el conjunto de valores posibles es conocido y finito.

### (c) Degeneración en tablas numéricas densas

Los modelos OCR-LLM entran en **bucle de repetición** ante tablas densas (presupuestos, anexos
numéricos) y generan páginas gigantes de texto repetido. Señal barata: **tamaño de página > 20 KB**.

```bash
find source/{iso2}/ocr -name 'page_*.txt' -size +20k | head -20
find source/{iso2}/ocr -name 'page_*.txt' -size +20k | wc -l
```

La confianza proxy cae por sí sola y marca la sesión como FLAG, así que el pipeline no lo traga en
silencio. Tratamiento: **cuarentena reversible** de esas páginas, nunca borrado — la tabla existe
en el acta y puede recuperarse con otro método.

### (d) Pérdida de la ñ — medir las variantes rotas de «señor» tras el lote

El OCR degrada la `ñ` a secuencias estables (`seflor`, `sefior`, `senor`, `seiior`, `sefíor`…) y el
daño cae justo donde más duele: el MARCADOR de orador. Es el caso EC del plan de reproceso
(«Preservar la ñ (evitar seflor)»). Como el stutter de (c), se busca tras el lote, no página a página:

```bash
grep -rhoiE 'se[fñnil][flíoir]{0,3}or(a|es)?' source/{iso2}/ocr --include='page_*.txt' \
  | tr '[:upper:]' '[:lower:]' | sort | uniq -c | sort -rn | head -15
```

- **Ratio alto de variantes rotas sobre el total de «señor»** (>1-2%) → el modelo primario no
  preserva la ñ en esa fuente: considera el modelo fallback (`ocr.fallback_model`) para las
  sesiones afectadas antes de dar el lote por bueno.
- **Registra las variantes VISTAS** — las reales del corpus, no una lista adivinada — en
  `country_config` → `ocr.enye_variants`, para que `correct` (normalizaciones) y `tag` (patrones de
  marcador) las TOLEREN aguas abajo. En ES la ñ OCR-eada de «señor» sumó +2.892 marcadores
  recuperados; la lista es de cada país, no transferible.

## Paso 2-ter — GATE DE VERDAD DE TERRENO (OBLIGATORIO antes de dar la fase por buena)

⛔ **NINGUNA métrica automática responde a «¿el texto dice lo que dice el papel?».** Todas las que
usa este skill —garble, `alpha_ratio`, densidad de palabras función, tasa de diccionario— miden si
el resultado **se parece** a lenguaje natural, no si **coincide con la fuente**. Un OCR puede
puntuar 94% de palabras válidas y estar destrozando el texto, porque los errores que producen otra
palabra real (`horas`→`honras`, `esta`→`cota`) cuentan como acierto, y los nombres propios no están
en ningún diccionario.

**Coste real de saltarse esto (EC, 2026-07):** se certificó el corpus como «de calidad» con esas
métricas. El procesador preguntó explícitamente si la calidad era buena y se le dijo que sí.
**Dos días de revisión manual después**, la verdad de terreno mostró **~24 errores por cada 62
palabras** en la era mecanografiada — `Quito`→`0uéto`, `Sala de Sesiones`→`Sata de Besionets`,
`VEGA ILAQUICHE`→`VECA JILAQUICAE` — y 24.075 grafías de orador para ~1.900 personas. El trabajo
manual hubo que descartarlo en un 78%.

### Procedimiento — 30 minutos, no negociable

1. **Elige las 3 peores sesiones** por tasa de reconocimiento léxico (no al azar: el gate debe
   atacar el peor caso, que es donde se decide si la fase pasa).
2. **Rasteriza 5-10 páginas** a 300 DPI y **MÍRALAS** con la herramienta de lectura de imágenes.
3. **Transcribe mentalmente un párrafo de cada una** y cuenta errores reales contra la salida OCR,
   distinguiendo dos clases porque tienen consecuencias distintas:
   - **errores en prosa** → degradan el texto de las intervenciones
   - **errores en marcadores de orador** → degradan la ATRIBUCIÓN, que es mucho peor y es lo que
     explota el número de grafías únicas en `diaries-match`
4. **Criterio de rechazo:** >5 errores por cada 100 palabras de prosa, **o** cualquier error
   sistemático en los marcadores de orador → la fase **NO PASA**. Prueba otro motor antes de
   seguir; arrastrar esto contamina todas las fases posteriores y el coste de descubrirlo tarde lo
   paga el revisor humano.

### Señal de alarma retroactiva — barata, pero HAY QUE CRUZARLA CON EL ORIGEN

Si tras `diaries-match` hay **más de 3-4 grafías únicas de orador por persona del padrón**, algo
está fragmentando los nombres. Cuéntalo solo sobre las grafías **vinculadas** (las no vinculadas
mezclan roles, cargos y basura, que no son fragmentación).

⚠ **Un ratio alto NO implica OCR malo por sí solo.** Medido en los 16 corpus (2026-07-28), la misma
señal tiene tres causas y se distinguen por el ORIGEN de la fuente y por los ejemplos:

| ratio alto en… | causa | ejemplo real |
|---|---|---|
| fuente **escaneada** | OCR degradado | PA `AICIBÍADES/AICIBiADES/ALCBÍADES · VELÁSQUEZ/VEIÁSQUEZ/VELÃSQUEZ` (218 grafías) |
| fuente **digital** | tagger: el marcador absorbe texto ajeno | CO `Carlos AL Roldán Avendaño John Jairo PLC Sí berto Zuluaga Díaz` (lista de votación mal segmentada) |
| cualquiera, ratio moderado | variación legítima | CR tildes, guiones y formas abreviadas del mismo nombre |

**Protocolo:** calcula el ratio → mira 10 grafías del id con más variantes → si son deformaciones
de caracteres, es OCR (aplica el gate de verdad de terreno); si son marcadores con texto de otros
oradores dentro, es `diaries-tag`; si son tildes y abreviaturas, es ruido tolerable.

⚠ **Y ojo con DÓNDE buscas la página para verificar.** Las «peores sesiones por reconocimiento
léxico» y las «sesiones donde vive el nombre fragmentado» **no son el mismo conjunto**. En PA el
ratio es 7,8 con un caso de 218 grafías, pero la peor sesión por léxico resultó tener texto
tipográfico limpio con **1 error en 300 palabras**: el problema está en páginas concretas, no en
las sesiones que el léxico señala. Si vas a verificar un ratio alto, **rasteriza las páginas donde
aparecen las variantes**, no las que puntúan bajo.

Resultados del barrido (2026-07-28) — el ratio es una ALARMA, no un diagnóstico:

```
ratio    país   verificado con verdad de terreno
11,3     PY     ✗ NO VERIFICABLE — sin raw/ ni ocr/ en el proyecto (solo corrected/ en adelante).
                  El peor ratio del corpus y no se puede diagnosticar ni corregir sin recuperar
                  las fuentes. Es el caso más preocupante precisamente por eso.
 7,8     PA     ~ una página de la peor sesión: LIMPIA (1 error/300 palabras, texto tipografiado,
                  OCR hecho con LLM). Descarta problema sistémico tipo EC; NO descarta páginas
                  concretas malas. Pendiente mirar donde viven las 218 variantes.
 7,5     CO     ✓ NO es OCR (fuente digital): el tagger absorbe listas de votación en el marcador.
 7,4     EC     ✓ OCR MALO CONFIRMADO — 24 errores/62 palabras en la era mecanografiada.
 4,1     CR     ✓ variación legítima (.docx): tildes, guiones, formas abreviadas.
 3,8     PT     — sin verificar
 3,2     UY     — sin verificar (escaneado 1985-2000)
 ≤2,9    DO MX AR GT SV   limpios
```

### Si el gate falla

`tesseract` no es el único motor. Medido en EC sobre las peores páginas: LightOnOCR-2:1b comete
**1 error por cada 62 palabras** donde tesseract comete 24, y acierta 12 de 19 nombres del pase de
lista frente a casi ninguno. Ver `Paso 2-bis` para cuándo el OCR-LLM es seguro y cuándo fabrica.

## Paso 3 — Resumen final

Imprime una tabla:

```
Resumen diaries-ocr — {iso2}
─────────────────────────────────────────────
  AUTO  (complete): {N}
  FLAG  (revisar):  {N}
  HALT  (detenido): {N}
  SKIP  (ya hecho): {N}
  ERROR:            {N}
─────────────────────────────────────────────
  Total procesadas: {N}
```

Si hay páginas con confidence < 0.50, lista los casos:
```
Advertencia — páginas con confianza muy baja (< 0.50):
  {session_id}: páginas {lista}
```

Si hay casos FLAG o HALT:
```
Hay {N} sesiones que requieren revisión.
Ejecuta: /diaries-review --country {iso2}
```

Si todo es AUTO:
```
Siguiente paso: /diaries-extract --country {iso2} --all
```
