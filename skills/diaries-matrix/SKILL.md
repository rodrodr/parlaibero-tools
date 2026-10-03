---
name: diaries-matrix
description: "Convierte texto etiquetado en matriz de intervenciones CSV"
allowed-tools: [Read, Write, Edit, Bash]
---

Eres el skill `diaries-matrix` del pipeline ParlaIbero. Conviertes archivos de texto etiquetado en la matriz de intervenciones `interventions_raw.csv`. El proceso es determinista — no uses juicio LLM para interpretar contenido, solo parsea.

## Argumentos esperados

`--country {iso2}` (obligatorio)
`--all` (procesar todas las sesiones pendientes)
`--session {session_id}` (procesar una sola sesión)
`--force` (reprocesar aunque ya esté completa)
`--dry-run` (mostrar qué se haría sin ejecutar)

## ⛔ GATE DE ENTRADA (OBLIGATORIO) — ABSOLUTE FAIL si diaries-tag tiene falsos negativos

La matriz se construye a partir del tagging. Un falso negativo (marcador de orador sin etiquetar)
atribuye TODA su intervención al speaker anterior → fila(s) corrupta(s) en la matriz. ANTES de
parsear NADA, verifica que ninguna sesión esté en HALT por falsos negativos. Si las hay, ABORTA:

```bash
python3 -c "import json,sys; S=json.load(open('state/{iso2}/pipeline_state.json'))['sessions']; h=[k for k,v in S.items() if v['skills'].get('diaries-tag',{}).get('status')=='halt']; (print(f'\\u26d4 ABSOLUTE FAIL: {len(h)} sesiones diaries-tag en HALT por falsos negativos. NO continuar. Ej: {h[:8]}') or sys.exit(1)) if h else print('Gate OK: 0 falsos negativos en diaries-tag')"
```

Si imprime `ABSOLUTE FAIL` (exit 1): **DETENTE, no construyas la matriz.** Remite a `/diaries-tag`
(Paso 2e-bis y Paso 4). El proceso solo prosigue cuando diaries-tag tiene 0 HALT por falsos negativos.

## Paso 1 — Leer configuración

Lee `country_config/{iso2}.yaml` con Read. Extrae:
- `standardize.csv_separator` (default: ";")
- `processing.min_intervention_chars` (default: 10)
- `intervention_format` (default: "auto") — valores posibles: `"auto"` | `"inline"` | `"standalone"`
  - `"inline"`: formato estándar del pipeline `<int speaker="NAME">texto</int>`
  - `"standalone"`: formato independiente `<int>NAME</int>` + texto a continuación (p.ej. Portugal)
  - `"auto"`: detección automática por archivo (recomendado si el corpus es homogéneo; seguro incluso si no se configuró)

Si el archivo no existe, detente con error: `ERROR: No existe country_config/{iso2}.yaml. Ejecuta primero /diaries-bootstrap --country {iso2}`

## Paso 2 — Determinar sesiones a procesar

Lista los archivos tagged disponibles:
```bash
find source/{iso2}/tagged -name "*.txt" 2>/dev/null | sort
```

Lee el estado actual con Read en `state/{iso2}/pipeline_state.json`. Identifica cuáles sesiones tienen `diaries-matrix` en status `complete` (para excluirlas salvo que se pase `--force`).

Si se pasó `--session {id}`: procesar solo esa sesión.
Si se pasó `--all`: procesar todas las que no estén completas (o todas si `--force`).
Si no se pasó ninguno: procesar todas las pendientes.

Si no hay sesiones que procesar: imprime "No hay sesiones pendientes para diaries-matrix en {iso2}." y termina.

## Paso 3 — Procesar cada sesión

Para cada sesión a procesar:

**3a. Verificar archivos requeridos**

Verifica que existen ambos archivos:
- `source/{iso2}/tagged/{session_id}.txt`
- `source/{iso2}/meta/{session_id}.json`

Si falta alguno, registra error en estado (`--status halt`) y continúa con la siguiente sesión. Informa al usuario qué falta.

**3b. Contar tags de apertura `<int` en el archivo fuente (auditoría previa)**

Antes de ejecutar el parser, cuenta los tags de APERTURA en el archivo tagged. ⚠ Debe contar tanto el
formato **inline** `<int speaker="...">` como el **standalone** `<int>`; por eso el patrón es `<int`
seguido de espacio o `>` — NO el literal `<int>`, que NO matchea el inline y daría `n_tags_fuente=0` →
**falso HALT en todo corpus inline** (verificado en UY 2026-06-17, formato inline). El lookahead
`[\s>]` además excluye los cierres `</int>`:

```bash
python3 -c "
import re, sys
text = open(sys.argv[1], encoding='utf-8', errors='replace').read()
n = len(re.findall(r'<int(?=[\s>])', text))
print(n)
" "source/{iso2}/tagged/{session_id}.txt"
```

Guarda este valor como `n_tags_fuente`. Si `n_tags_fuente == 0`, registra HALT: el archivo no contiene etiquetas `<int` válidas.

**3c. Ejecutar el parser**

```bash
mkdir -p source/{iso2}/matrix/
python ~/.claude/skills/diaries-lib/lib/utils/parse_interventions.py \
  --input "source/{iso2}/tagged/{session_id}.txt" \
  --meta "source/{iso2}/meta/{session_id}.json" \
  --output "source/{iso2}/matrix/interventions_raw.csv" \
  --min-chars {min_intervention_chars} \
  --separator "{csv_separator}" \
  --format {intervention_format}
```

**Nota sobre formatos:**
- `--format auto` (default): detecta automáticamente si la sesión usa `<int speaker="NAME">texto</int>` (inline) o `<int>NAME</int>` + texto a continuación (standalone). Seguro para cualquier corpus.
- `--format inline`: fuerza el formato estándar del pipeline.
- `--format standalone`: fuerza el formato de tag independiente (Portugal, archivos pre-etiquetados externos).

**3d. Leer resultado**

El script escribe JSON a stdout. Léelo y extrae:
- `format_used`: formato detectado/aplicado (`"inline"` o `"standalone"`)
- `interventions_added`: número de intervenciones añadidas
- `untagged_blocks`: bloques sin etiquetar (inline) o speakers sin texto (standalone)
- `filtered_short`: intervenciones descartadas por ser menores de `min_chars`

**3e. Verificar cobertura de tags**

Calcula la tasa de cobertura comparando el resultado del parser con el conteo previo:

```
n_procesados = interventions_added + filtered_short  # tags que el parser reconoció como speaker
tasa_cobertura = n_procesados / max(n_tags_fuente, 1)
```

Si `tasa_cobertura < 0.50`: emite advertencia visible:
```
⚠ COBERTURA BAJA: {session_id} — solo {tasa_cobertura:.0%} de los {n_tags_fuente} tags <int> produjeron intervenciones ({interventions_added} aceptadas, {filtered_short} descartadas por longitud). Posible problema en el parser o en el formato del archivo.
```

Si `tasa_cobertura < 0.20`: registra HALT en lugar de continuar — hay un fallo sistemático.

Esta comprobación es la salvaguarda principal contra bugs silenciosos en el parser (como el umbral `len(s) <= 20` en `_clean_speaker()` que rechazaba nombres válidos en corpora todo-mayúsculas).

**3f. Calcular confianza**

```
confianza = 1.0 - (untagged_blocks / max(interventions_added + untagged_blocks, 1))
# Penalizar adicionalmente si la cobertura de tags es baja
if tasa_cobertura < 0.80:
    confianza = min(confianza, tasa_cobertura)
```

**3g. Actualizar estado**

```bash
python ~/.claude/skills/diaries-lib/lib/utils/update_state.py \
  --country {iso2} --skill diaries-matrix --session {session_id} \
  --status complete --confidence {confianza} \
  --output "source/{iso2}/matrix/interventions_raw.csv"
```

Si `confianza < 0.80`: usa `--status flag` en lugar de `complete`.
Si `tasa_cobertura < 0.20`: usa `--status halt`.

## Paso 4 — Resumen final

Al terminar todas las sesiones, imprime:

```
diaries-matrix — {iso2}
Sesiones procesadas: {N}
  Completas:  {n_complete}
  Con FLAG:   {n_flag}
  Con HALT:   {n_halt}
Archivo de salida: source/{iso2}/matrix/interventions_raw.csv
Total intervenciones acumuladas: {total_rows}

Auditoría de cobertura de tags:
  Tags <int> en fuentes:   {total_tags_fuente}
  Intervenciones + filtradas: {total_procesados}
  Cobertura global:        {cobertura_global:.1%}
  Sesiones con cobertura < 50%: {n_cobertura_baja}
```

Si `cobertura_global < 0.80`: emite advertencia adicional:
```
⚠ La cobertura global de tags es {cobertura_global:.0%}. Revisa parse_interventions.py — posible problema sistemático en el parser (umbrales de filtrado, formato no detectado, o normalización de texto).
```

Si hay sesiones con FLAG: "Ejecuta /diaries-review --country {iso2} --skill diaries-matrix para revisar los casos."

## Paso 5 — Auditoría de MARCADORES INCRUSTADOS (OBLIGATORIA — gate de salida)

⚠ **Este es el falso negativo más insidioso del pipeline y ha aparecido en casi todos los
países**: un marcador de orador ABSORBIDO dentro del campo `text` de otra intervención.
`verify_tagging` NO lo ve (ancla a inicio de línea); la intervención entera queda atribuida
al orador ANTERIOR, silenciosamente. Causas típicas (verificadas en PA 2026-07, 10.499 casos):
1. El **merge de párrafos de diaries-correct** absorbía el marcador cuando la línea previa
   terminaba sin puntuación (OCR: "Peraltao" por "Peralta."). Fix general ya en
   `~/.claude/skills/diaries-lib/lib/utils/correct_text.py` (`_MARKER_PROTECT_DEFAULT` +
   guardas en el merge).
2. **Marcadores fragmentados** en varias líneas por PDF de columna estrecha
   ("-H.D.\nNORMAN\nSCOTT"). Fix general: `reassemble_markers()` en `correct_text.py`,
   activado con `correct.marker_reassembly` (lista de prefijos regex) en el country_config.
3. **Ruido OCR pegado antes del marcador** ("~ -HD."). Fix: `correct.normalize_replacements`.

Tras construir la matriz, ejecuta SIEMPRE este escaneo sobre el campo `text` (adapta los
regex a los `speaker_tag_patterns` del país; los de abajo son la familia PA/genérica):

```python
import csv, sys, re
csv.field_size_limit(sys.maxsize)
# (a) marcador en línea INTERNA del text (re.M) — deriva de speaker_tag_patterns del config
RE_LINE = re.compile(r'{patrones del país anclados ^...$ con re.M}', re.M)
# (b) marcador a MITAD de línea tras fin de oración (absorbido por un join)
RE_MID  = re.compile(r'[.!?»"\)]\s+({prefijo honorífico}\s+[A-ZÁÉÍÓÚÜÑ][^\n]{2,50}:)\s')
# (c) hyphen-style incrustado (si el país lo usa)
RE_HYP  = re.compile(r'[^\n]\s[-–—]\s?{prefijo}\s+[A-ZÁÉÍÓÚÜÑ]{2}')
n = hits = 0
for r in csv.DictReader(open("source/{iso2}/matrix/interventions_raw.csv")):
    n += 1; t = r['text']
    hits += len(RE_LINE.findall(t)) + len(RE_MID.findall(t)) + len(RE_HYP.findall(t))
print(f"filas={n}  incrustados={hits}  ratio={hits/max(n,1):.2%}")
```

**Criterio:**
- `ratio <= 0.1%` → aceptable (residuo de OCR revuelto irreducible). Documentar el número.
- `ratio > 0.1%` → **NO avanzar a deputies/match/merge.** Diagnosticar la CAPA de origen
  mirando 5-10 ejemplos en contexto: ¿el marcador está fragmentado en `extracted/`? →
  `correct.marker_reassembly`. ¿Está entero en `corrected/` pero absorbido a mitad de línea?
  → protección del merge / `normalize_replacements` de split. ¿Ruido antes del dash? → strip.
  Corregir en la capa correcta y RE-EJECUTAR la cadena correct → tag → matrix (es barata,
  minutos). Repetir la auditoría hasta bajar del umbral.

En PA este loop (4 iteraciones) recuperó **+42.132 intervenciones** que estaban atribuidas
al orador equivocado (10.499 → 258 incrustados, 0,08%).

### Split de los incrustados residuales — `split_embedded_markers.py` ES parte del flujo

**Decidido (2026-08-23):** el split no es solo un rescate para corpus ya cerrados. Cuando la
auditoría de arriba deja los incrustados **dentro del umbral** (≤0,1 %, o el residuo que el loop
sobre la capa de origen ya no reduce), `split_embedded_markers.py` forma parte del flujo de este
paso: divide las filas afectadas y recupera el turno sin reprocesar la cadena. **Por encima del
umbral NO se parchea el CSV: se vuelve a tag** — corregir la capa de origen y re-ejecutar
correct → tag → matrix, como manda el criterio de arriba. Sobre un corpus ya cerrado se aplica
igual, con `--sample` para revisar antes de `--apply`:

```bash
python3 ~/.claude/skills/diaries-lib/lib/utils/split_embedded_markers.py --country {iso2}
python3 ~/.claude/skills/diaries-lib/lib/utils/split_embedded_markers.py --country {iso2} --sample 15
python3 ~/.claude/skills/diaries-lib/lib/utils/split_embedded_markers.py --country {iso2} --apply
```

```yaml
embedded_markers:
  terminators: [dash | dash_ocr | colon | dash_before]
  name_titlecase: true      # el nombre va en Title Case, no en versales
  role_lowercase: true      # «El Presidente diputado Alfredo Villegas Arreola:» (MX)
  guards: [rollcall, quote, index, signatures]
```

⚠⚠ **Un 0,00% aquí es sospechoso hasta explicarlo, no una buena noticia.** AR daba **7 filas
de 260.455** con la configuración por defecto —versales y guion limpio— cuando la validación por
muestreo con revisión humana medía **1,00%**. Escribe el marcador en Title Case (`Sr. García
Vázquez. —`) y el guion se le corrompe: sobre 242 marcadores localizados a mano, `—` 182 · `_` 27
· `~` 17 · `·` 14. Con `name_titlecase` + `dash_ocr` pasa a 1.763 filas (0,68 %).

⚠ **El detector por VOCABULARIO no sirve cuando el OCR corrompe el nombre.** En AR el marcador
es `Sr. Alvarcz Ecbagüe` por *Álvarez Echagüe*: de 519 coincidencias del vocabulario del propio
corpus dentro del `text`, **ninguna** era un turno —todas cadenas de firmas o menciones en
prosa—. Ahí solo funciona la forma.

⚠⚠ **Dos guardas que no son opcionales, y las dos vinieron de romper cosas al ampliar el
detector:**

- **Un turno siempre empieza en mayúscula o signo de apertura.** Sin eso, el guion de la
  **hifenación** a final de línea se toma por terminador: «el señor Angelelli no estuvo aje-⏎no
  a la diatriba» producía un orador llamado *señor Angelelli no estuvo aje*. Es el falso positivo
  más traicionero, porque el resultado **parece un nombre**.
- **El glifo corrompido solo cuenta aislado, entre espacios.** Al admitir `~` como guion,
  «Sr. Pre~idente (Pugliese)» —donde la virgulilla es una `s` mal leída— se partía por dentro de
  la palabra.

## Paso 5-bis — PROLEGOMENA: la carátula y el sumario del acta (OBLIGATORIO)

⚠ **Todo lo que hay en `corrected/` ANTES del primer marcador se pierde si no lo recoges aquí.**
La matriz arranca en el primer `<int>`, y lo que precede —que no tiene orador— se cae sin que
ningún recuento lo delate. Medido el 2026-08-09 sobre los corpus ya publicados, la cabecera del
acta llegaba al **0 % en AR, 1 % en UY, 3 % en PA, 6 % en CL y MX, 10 % en CO, 15 % en GT y
20 % en CR**, con cuerpos que llegaban al 62-92 %. Solo PE la conservaba.

Y no es material prescindible. Es lo único que trae:

| país | qué se perdía |
|---|---|
| AR | presidencia, secretarios, prosecretarios y la **lista de diputados presentes** |
| PA | legislatura, hora del primer llamado y el **pase de lista completo** |
| CL | número y tipo de sesión, horas, presidencia **accidental**, secretario, e ÍNDICE |
| GT | período legislativo, tomo, tipo y número de sesión, y el **SUMARIO con sus páginas** |
| ES | legislatura, número, presidencia y el **ORDEN DEL DÍA** |
| UY | número y tomo, legislatura, período, quiénes presiden y actúan en secretaría |
| MX | legislatura, año, período, número de diario, presidencia y recinto |
| BR | `SESSÃO`, `DATA`, `TURNO`, `TIPO DA SESSÃO`, `LOCAL`, `INÍCIO`/`TÉRMINO` |

**El criterio es uno solo, explícito y verificable: dónde empieza la primera intervención. Todo
lo que venga antes es Prolegomena.** No se adivina el límite — se ancla en el primer texto que
sí llegó al corpus, que es idéntico en los 16 países.

```bash
python3 ~/.claude/skills/diaries-lib/lib/utils/recover_frontmatter.py --country {iso2} --medir
python3 ~/.claude/skills/diaries-lib/lib/utils/recover_frontmatter.py --country {iso2}
```

Entran como **Prolegomena**: una fila por acta, con `intervention_order = 0`, `dm_speech = 0` y
sin orador (no lo tienen). El 0 los pone delante de la primera intervención **sin desplazar la
numeración de ninguna**, así que ninguna referencia previa se rompe y `intervention_order == 0`
los identifica por sí solo. `conformidad.py` acepta el 0 y sigue exigiendo 1..n en el resto.

⚠ **NO pongas tope de longitud.** Un Prolegomena larguísimo no es un error: en CL uno de
1.312.864 caracteres —el 91 % del acta— son `VI.- DOCUMENTOS DE LA CUENTA` y `VII.- OTROS
DOCUMENTOS`, los anexos íntegros, y son perfectamente legítimos. Llegué a filtrarlos por
superar el 25 % del acta y habría vuelto a tirar justo lo que había que rescatar.

**Verificación del corte** (la hace el propio script, y es la prueba de aceptación): se corta en
la primera intervención y se comprueba que **no haya quedado ningún marcador de intervención
dentro** del Prolegomena, con el detector derivado del `speaker_raw` del propio país. Ese es el
control, no el tamaño: el Prolegomena de 1,3 M de CL tiene **1 marcador frente a 96 en el resto
del acta**. Si un Prolegomena trae marcadores, el corte llegó tarde y hay que revisarlo.

Verifica además: `filas(nuevo) − filas(previo) == actas con Prolegomena`.

## Paso 5-ter — ANEXOS DEL DIARIO (declarar, no borrar — OBLIGATORIO)

⚠⚠ **El hallazgo más caro de la revisión final: los ANEXOS eran el 51 % del texto de AR**, y en
total **488,5 M de caracteres declarados en 5 países** — documentos reproducidos, versiones
taquigráficas insertadas, apéndices del acta. No son discurso, pero son parte del acta: **ni se
borran ni se mueven, se DECLARAN**. Ver [[anexos_del_diario]] (decisión `tr-0082`). Los anexos
ya NO son competencia de `diaries-extract` (que es fiel y no recorta): se declaran aquí, sobre
la matriz (plan de reproceso §1.1).

1. **Descubre el separador EXPLÍCITO de anexos del acta** — cada país tiene (o no tiene) el
   suyo; se descubre sobre el texto, no se adivina — y **regístralo en
   `country_config/{iso2}.yaml` → `matrix.annex_separator`**.
2. Todo lo posterior al separador → **`dm_speech = 0`**, DECLARADO: la fila se queda en su
   sitio, con su orden y su texto íntegro.
3. **Sin separador marcado en el acta NO se especula.** Discriminancia ≠ frontera: que un
   clasificador distinga «esto parece anexo» no autoriza a trazar el corte donde el acta no lo
   marca. Sin marca explícita, las filas quedan como están.

## Paso 6 — Inventario de filas que NO son discurso (OBLIGATORIO antes de cerrar)

Una matriz puede estar perfectamente etiquetada y aun así contener filas que no son habla
parlamentaria: acotaciones de la redacción, resultados de votación, cabeceras de acta, textos
documentales insertados. Cuentan como intervenciones, inflan el corpus y contaminan cualquier
análisis de texto. En PE eran **104.974 filas, el 11 % del corpus**.

**Detección.** Agrupa por `speaker_raw` los oradores sin nombre de persona y mira su peso:

```bash
python3 -c "
import csv,sys; csv.field_size_limit(sys.maxsize)
from collections import Counter
c=Counter(); n=0
for r in csv.DictReader(open('source/{iso2}/matrix/interventions_raw.csv')):
    n+=1; c[r['speaker_raw']]+=1
for k,v in c.most_common(25): print(f'{v:>8} {v/n:>6.1%}  {k[:60]}')"
```

Señales de clase no-discurso: etiquetas genéricas (`COMMENT`, `ID SESION`, `NOTA`), texto que
empieza por guión de acotación (`—A las 10 horas…`, `—Al voto, se aprueba…`), cabeceras de acta,
y la **votación NOMINAL**: las listas de voto y el «Por el señor Diputado X» repetido. Sus
patrones por país vienen de `tag.vote_patterns` del config — `diaries-tag` los EXCLUYE del
tagging (no abren turno) y aquí se declaran `dm_speech = 0`. El clasificador
`~/.claude/skills/diaries-lib/lib/utils/classify_notspeaker.py` cubre buena parte del vocabulario.

**Default explícito: `dm_speech = 1` salvo prueba de lo contrario.** El `0` solo se pone donde
está DEMOSTRADO que la fila no es discurso; «no clasificado» no es evidencia. El `1` significa
«no demostrado que no sea discurso», no «certificado como discurso».

⚠ **MIRA LA COLA LARGA POR LONGITUD ANTES DE DECIDIR NADA.** Es el error que estuvo a punto de
costar 66 M de caracteres en PE: la **mediana** de las filas `COMMENT` era de 107 caracteres y
describía acotaciones inocuas, pero el **p99 escondía los textos íntegros de las leyes aprobadas**
insertados en el acta — la mayor, de 511.320 caracteres, era una ley completa. También apareció
algún fragmento de discurso real mal clasificado.

```bash
python3 -c "
import csv,sys; csv.field_size_limit(sys.maxsize)
L=sorted(len(r['text']) for r in csv.DictReader(open('source/{iso2}/matrix/interventions_raw.csv'))
         if r['speaker_raw']=='{CLASE}')
print('n',len(L),'mediana',L[len(L)//2],'p99',L[int(len(L)*.99)],'máx',L[-1])"
```

**Tratamiento: SE DECLARAN, no se apartan.** ⚠ Esto ANULA la instrucción anterior de sacarlas a
un sidecar. La directiva del proyecto es enriquecer la base, no desecharla: la fila se queda
donde está y se marca con **`dm_speech = 0`** (13ª columna canónica, binaria: 1 = intervención,
0 = no). Quien quiera solo habla parlamentaria filtra por `dm_speech == 1`; quien quiera las
leyes íntegras, los recuentos o las acotaciones las tiene ahí. Un sidecar es un archivo que
nadie vuelve a abrir, y ya obligó a reintegrar material en MX, CR, ES, UY, SV y AR.

Documenta en el informe **qué** contiene la clase declarada `dm_speech = 0` (nada se
retira): en PE eran tres cosas distintas
(acotaciones ~37 K, resultados de votación ~44 K, leyes íntegras ~10 K), y decir solo «anotaciones
de la redacción» habría sido falso.
