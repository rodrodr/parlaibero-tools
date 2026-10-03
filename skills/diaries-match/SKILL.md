---
name: diaries-match
description: "Vincula nombres de oradores con la base de datos de diputados"
allowed-tools: [Read, Write, Edit, Bash]
---

Eres el skill `diaries-match` del pipeline ParlaIbero. Vinculas cada `speaker_raw` de `interventions_raw.csv` con un registro de `deputies.csv`, produciendo `matching_table.csv`. Usa umbrales altos para garantizar calidad. Este skill opera a nivel PAÍS.


## Paso 0 — La vinculación congelada MANDA (obligatorio antes de nada)

```bash
python3 ~/.claude/skills/diaries-lib/lib/utils/frozen_matching.py --country {iso2} --check
python3 ~/.claude/skills/diaries-lib/lib/utils/frozen_matching.py --country {iso2} --apply
```

⚠⚠ **El `--apply` de este paso solo actúa cuando YA existe `matching_table.csv`** — es decir,
en re-ejecuciones sobre tabla viva. En un arranque desde cero la tabla aún no existe y
`frozen_matching.py` devuelve `None`: el `--apply` es un **no-op silencioso**. El paso que
garantiza lo congelado en ese escenario es el **Paso 6-final**, obligatorio tras reconstruir
la tabla. Este Paso 0 sirve para saber ANTES de empezar cuánto trabajo manual hay en juego
(el `--check` funciona siempre que exista la congelada).

⚠⚠ **La revisión humana NO está marcada en ninguna columna.** Se hizo sin tocar
`match_method`, así que hoy es indistinguible de lo automático: no hay forma de saber qué filas
miró una persona. Por eso se congela **toda** la tabla, no solo lo revisado, y por eso la
congelada gana siempre sobre lo que produzca una re-ejecución.

Congeladas (verificado 2026-08-23): **106.938 decisiones** en 13 países —EC 24.075 ·
PA 15.766 · PT 12.754 · CO 12.486 · MX 10.706 · ES 7.171 · PY 7.142 · UY 5.727 · AR 4.906 ·
DO 2.357 · CR 2.313 · GT 1.190 · SV 345— con manifiesto `sha256`. Solo BR, CL y PE no tienen
tabla: se construyeron fuera del pipeline con otro mecanismo, y **reprocesarlos no arriesga
ninguna decisión de tabla congelada**.

⚠ **`speaker_raw` se casa EXACTAMENTE, sin normalizar tildes ni caja.** Normalizar la clave
parece inofensivo: en `split_embedded_markers` se destildaba el vocabulario y no el texto, y el
resultado no fue fallar sino **acertar a medias**, con oradores mutilados y un recuento
plausible.

⚠ **Una entrada congelada que ya no aparece NO se borra: se informa** en
`docs/{iso2}/vinculacion_huerfana.csv`. Significa que la extracción cambió esa forma y que hay
una decisión humana que rehacer sobre la nueva.

⚠ **La cola es lo frágil.** Entre el 42 % y el 61 % de las formas de `speaker_raw` aparecen una
sola vez (UY 42 %, CO 56 %, PA 61 %), mientras las 500 más frecuentes cubren el 85–91 % de las
intervenciones. El grueso sobrevive a un reproceso; la cola —donde están las decisiones
difíciles— es lo primero que cambia al mejorar la extracción. El recuento de **formas NUEVAS**
que da `--check` es exactamente el trabajo manual que añadiría ese reproceso, y se sabe antes
de empezarlo.


## Principio — Primacía del diario

Una intervención **NUNCA se elimina porque su orador no case con el padrón**. El acta es la
fuente primaria y el padrón el auxiliar: la fila sin `id_dep` es un hueco visible y auditable;
la fila borrada es una pérdida silenciosa que ningún recuento delata. Todo residuo `unmatched`
se queda en el corpus y se declara — [[feedback_primacia_del_diario]].


## Argumentos esperados

`--country {iso2}` (obligatorio)
`--force` (regenerar aunque ya exista matching_table.csv)
`--dry-run` (mostrar plan sin escribir)

## Paso 1 — Leer configuración

Lee `country_config/{iso2}.yaml` con Read. Extrae:
- `match.threshold_auto` (confianza mínima para match automático; default: 0.90)
- `match.threshold_flag` (confianza mínima para considerar match posible; default: 0.70)
- `match.fuzzy_threshold` (umbral para `fuzzy_match.py` con `token_set_ratio`, escala 0-100; default: 85)
- `match.ambiguity_margin` (margen para considerar empate entre candidatos; default: 4)

`fuzzy_match.py` (reescrito 2026-06) ya: limpia títulos/cargos ("DIPUTADO", "SEÑOR DIPUTADO",
"Accidental"…), matchea contra nombre completo Y apellidos con `token_set_ratio`, filtra candidatos
por **vigencia temporal** (mandato del diputado vs fecha de sesión) y **detecta empates** entre
apellidos compartidos (no elige uno arbitrario → `match_method="ambiguous"` para el paso LLM).

## Paso 2 — Verificar prerequisitos

Verifica que existen ambos archivos:
```bash
test -f source/{iso2}/matrix/interventions_raw.csv && echo "OK" || echo "MISSING"
test -f source/{iso2}/deputies/deputies.csv && echo "OK" || echo "MISSING"
```

Si falta `interventions_raw.csv`: `ERROR: Ejecuta primero /diaries-matrix --country {iso2}`
Si falta `deputies.csv`: `ERROR: Ejecuta primero /diaries-deputies --country {iso2}`

Si `match/matching_table.csv` ya existe y no se pasó `--force`: detente con `ERROR: match/matching_table.csv ya existe. Usa --force para regenerar.`

## Paso 3 — Extraer speakers únicos CON sus fechas de sesión

Cada `speaker_raw` se exporta con el conjunto de fechas en que intervino — el matcher las usa para
filtrar diputados por vigencia temporal (desambigua apellidos compartidos). NO deduplicar a solo el
nombre: hay que conservar las fechas.

```bash
python3 -c "
import pandas as pd, json
df = pd.read_csv('source/{iso2}/matrix/interventions_raw.csv', sep=';', dtype=str)
g = df.dropna(subset=['speaker_raw']).groupby('speaker_raw')['date'].apply(
    lambda s: sorted({d for d in s.dropna() if d})
)
speakers = [{'speaker_raw': k, 'dates': v} for k, v in g.items()]
print(json.dumps(speakers, ensure_ascii=False))
" > source/{iso2}/.tmp_speakers.json
```

Muestra el conteo: "Speakers únicos encontrados: {N}" (si el CSV no tiene columna `date`, el matcher
funciona igual pero sin filtro temporal — la desambiguación recae más en el paso LLM).

## Paso 4 — Ejecutar matching difuso (con desambiguación temporal)

```bash
python ~/.claude/skills/diaries-lib/lib/utils/fuzzy_match.py \
  --names "source/{iso2}/.tmp_speakers.json" \
  --deputies "source/{iso2}/deputies/deputies.csv" \
  --threshold {fuzzy_threshold} \
  --ambiguity-margin {ambiguity_margin} \
  --output "source/{iso2}/.tmp_matches.json"
```

El JSON de salida marca cada speaker con `match_method`: `exact` | `fuzzy` | `ambiguous` | `unmatched`.
Los `ambiguous` traen un campo `candidates` (lista de diputados empatados) que el paso 5 desambigua
por contexto. **Requisito de esquema**: `deputies.csv` debe tener las columnas canónicas
(`id_dep`, `nombre_completo`, `apellidos`, `fecha_inicio`, `fecha_fin`). El matcher es robusto a
mayúsculas/variantes, pero sin `apellidos` el matching de apellido-solo pierde calidad y sin
`fecha_inicio/fin` no hay filtro temporal.

## Paso 4a-bis — Triaje de NO-PERSONAS sobre el residuo `unmatched` (antes de todo lo demás)

Medición sobre la revisión manual del usuario en DO (2026-07), tomada como verdad de terreno —
154 correcciones sobre 2.357 speakers:

| corrección automático → humano | n | % |
|---|---:|---:|
| `unmatched` → **NOT_SPEAKER** | 102 | **66%** |
| `unmatched` → persona real | 41 | 27% |
| **id ASIGNADO que estaba mal** | **0** | **0%** |

El matcher no falla atribuyendo — su precisión es del 100%. **Dos tercios del trabajo humano es
declarar "esto nunca fue una persona"**, y eso es vocabulario cerrado: partidos, órganos,
comisiones, articulado legal, instrucciones de edición filtradas del acta. Automatízalo:

```bash
python3 -c "
import sys; sys.path.insert(0,'$HOME/.claude/skills/diaries-lib/lib/utils')
from classify_notspeaker import clasificar
"   # → clase de no-persona, o None si puede ser alguien
```

⚠ **ÁMBITO — el error de diseño que hay que evitar.** Aplícalo **SOLO** a los `unmatched`. Correrlo
sobre todo el universo de speakers produjo **577 falsos positivos** en DO: nombres reales que el
tagger truncó (`Agustín Burgos Tejada de`, `… y de`) disparan las reglas sintácticas, pero ya tienen
match correcto. **Un match exitoso ES la prueba de que hay persona**; ahí no hay nada que clasificar.

⚠ **Precisión antes que recall.** Descartar a un diputado real pierde sus intervenciones sin dejar
rastro; dejar pasar basura solo cuesta una línea de revisión. Ante la duda, el clasificador calla.

**El criterio que más rinde es el NÚCLEO del sintagma, no contar tokens.** `Corte de Apelación del
Departamento Judicial de Montecristi` es una entidad porque empieza por `Corte`; los nombres propios
posteriores son irrelevantes. Ningún nombre de persona empieza por `Comisión`, `Bloque` o `Corte`.
Ese cambio subió el recall del 46% al 68%; el resto de clases lo llevó al 83%.

Rendimiento validado en DO: **precisión 97,7% · recall 83,3%**, y los 2 únicos "fallos" no eran
diputados (`Y`, y una Secretaría de Estado que el usuario había marcado `role` — mismo resultado).
Reduce la revisión humana de 102 filas a 17.

**Antes de correrlo en un país nuevo**, revisa que el léxico refleje su realidad: siglas de partidos
(están en `country_config`), nombres de comisiones y órganos, y la fórmula del articulado legal.

**Regla de prosa — sin léxico, derivada del propio corpus (pásale `comunes=`).** La parte más
portable del clasificador, porque no depende de ningún vocabulario y funciona en cualquier país e
idioma. Señal: **una palabra común aparece en minúscula en medio de una frase; un apellido nunca.**

```python
from classify_notspeaker import palabras_comunes, clasificar
COMUNES = palabras_comunes(df["text"].dropna())     # ~10.000 palabras en DO
clasificar(sr, COMUNES)
```

Medido en DO: `vía` 1.00 · `tras` 0.98 · `excepciones` 1.00 (comunes) frente a `González` 0.00 ·
`Balaguer` 0.00 · **`Minyet` 0.00** — protege apellidos raros que ningún léxico contendría, y por
eso es más segura que una lista negra. Subió el recall de 83,3% a **89,5%** sin coste de precisión.

⚠ **No normalices el texto a minúscula antes de medir**: destruye la señal por completo (con el
texto ya en minúsculas, `González` da 1527 "minúsculas" y parece palabra común).

**Rendimiento final validado en DO contra dos rondas de revisión humana: precisión 97,9% · recall
89,5% · 0 diputados reales descartados.**

## Paso 4a-ter — Intervenciones conjuntas (`A y B`)

Clase estructural que el tagger produce y ningún matcher resuelve: **dos oradores en un solo
marcador** (`Eulalio Ramírez Ramírez y Luis Simón Terrero Carvajal`). Detección barata y segura:
parte por ` y `, y si **ambas** mitades casan con el roster a ≥88, es conjunta.

No la resuelvas en automático — la decisión (atribuir al 1º / partir la intervención / marcar como
conjunta) es del usuario. Sácala al archivo de revisión con las dos personas ya identificadas. En DO
fueron 10 casos.

## Paso 4a-quater — El apellido partido por el guion de fin de línea

Antes de dar por no-coincidente ninguna forma, **deshaz la hifenación tipográfica**: si el
marcador cruzó un salto de línea de columna estrecha, el apellido llega roto y no casa con nada.

```python
s = re.sub(r"([A-ZÁÉÍÓÚÑ])-\s+([A-ZÁÉÍÓÚÑ])", r"\1\2", s)   # «FRU- TOS» → «FRUTOS»
```

Casos reales de PY, todos irrecuperables sin esto y todos correctos con ello: `DIPUTADO JULIO
CESAR FRU- TOS` → `Frutos, Julio Cesar`; `DIPUTADO MIGUEL ANGEL RA- MIREZ` → `Ramírez García,
Miguel Ángel`; `DIPUTADO JUAN MANUEL BENI- TEZ FLORENTIN` → `Benitez Florentín, Juan Manuel`.

⚠ **Únelo sin espacio, y solo entre mayúsculas.** Un guion entre minúsculas puede ser un apellido
compuesto real, y unir por ahí inventa personas. La de-hifenación de verdad se hace aguas arriba,
en `diaries-correct` (paso «restaurar la fluidez» de su secuencia de limpieza — `extract` ya no
limpia) y antes de cualquier reensamblado; esto es la
red de seguridad de este skill, no el arreglo. Ver [[feedback_marcador_partido]].

## Paso 4b — Heurísticas estructurales para no-coincidencias (antes del LLM)

Aplica sobre cada `speaker_raw` con `match_method == "unmatched"` tras el paso 4 (NO sobre los
`ambiguous`, que ya tienen candidatos). El matcher reescrito ya resuelve el caso de apellido-solo
(heurística 1) vía `token_set_ratio`, así que en la práctica solo quedará trabajo para la
**heurística 2 (expansión de iniciales)** —que el fuzzy no cubre— y casos residuales. Mantén las tres
por robustez.

```python
import unicodedata, re
from rapidfuzz import fuzz

def norm(s):
    s = unicodedata.normalize('NFD', s.lower().strip())
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', s)

def has_initial(token):
    return bool(re.match(r'^[a-z]\.$', token))
```

**Heurística 1 — Apellido como prefijo del `speaker_raw`**

Si `norm(speaker_raw)` es un prefijo del `norm(apellidos)` de algún diputado (o viceversa), y el speaker_raw tiene al menos 4 caracteres:

```python
for dep in deputies:
    ape_norm = norm(dep['apellidos'])
    raw_norm = norm(speaker_raw)
    if (ape_norm.startswith(raw_norm) or raw_norm.startswith(ape_norm)) and len(raw_norm) >= 4:
        # Candidato encontrado — guardar con confidence = 0.80
```

Esto captura casos como `speaker_raw = "Alegre"` → `apellidos = "Alegre Sasiain"`.

**Heurística 2 — Expansión de iniciales**

Si el `speaker_raw` contiene tokens que son iniciales (`X.`), compara expandiéndolas contra cada token del `apellidos` del diputado que empiece con esa letra:

```python
raw_tokens = norm(speaker_raw).split()
for dep in deputies:
    ape_tokens = norm(dep['apellidos']).split()
    if len(raw_tokens) != len(ape_tokens):
        continue
    all_match = all(
        rt == at or (has_initial(rt) and at.startswith(rt[0]))
        for rt, at in zip(raw_tokens, ape_tokens)
    )
    if all_match:
        # Candidato — confidence = 0.75
```

Esto captura `speaker_raw = "Alfonso G."` → `apellidos = "Alfonso González"`.

**Heurística 3 — Apellido + nombre parcial (primer token)**

Si el `speaker_raw` contiene apellido y parte del nombre, prueba a comparar solo el primer apellido y el primer nombre:

```python
raw_parts = norm(speaker_raw).split(',', 1)  # ["apellido", "nombre"]
if len(raw_parts) == 2:
    raw_ape = raw_parts[0].strip()
    raw_nom_first = raw_parts[1].strip().split()[0] if raw_parts[1].strip() else ''
    for dep in deputies:
        dep_ape_first = norm(dep['apellidos']).split()[0]
        dep_nom_first = norm(dep['nombre']).split()[0] if dep['nombre'] else ''
        if dep_ape_first == raw_ape and dep_nom_first == raw_nom_first:
            # Candidato — confidence = 0.85
```

**Criterio de desambiguación cuando hay múltiples candidatos**

Si más de un diputado pasa alguna de las tres heurísticas:
- Prioridad: heurística 3 > heurística 1 > heurística 2
- Si siguen empatados, escala al LLM con los candidatos pre-filtrados

Registra `match_method: "structural"` para los casos resueltos por estas heurísticas.

## Paso 4c — Restricción por lista de asistencia (señal MÁS fuerte de desambiguación)

Los diarios suelen abrir con un **pase de lista nominal** (`Asisten los señores
Representantes: …` / `Con licencia: …` / `Faltan con aviso: …`). El conjunto de
**presentes** es exactamente quién pudo hablar ese día → desambigua apellidos
compartidos mejor que la ventana de mandato (que es de ~5 años), y como es
**por-sesión**, resuelve el caso que el modelo global no puede: el mismo apellido
(`DÍAZ`, `MUJICA`, `ABDALA`) es **personas distintas según la fecha**.

Ejecuta SOLO si el corpus trae pase de lista (compruébalo con un `grep -lc` de
`[Aa]sisten los señores` sobre `corrected/`; si la cobertura es baja, omite este paso):

```bash
# 1. Extraer las listas de asistencia (present/absent por sesión)
python ~/.claude/skills/diaries-lib/lib/utils/parse_attendance.py \
  --input source/{iso2}/corrected \
  --output source/{iso2}/match/attendance.csv

# 2. Mapear presentes→id_dep por fecha y RE-RESOLVER el matching con esa restricción
python ~/.claude/skills/diaries-lib/lib/utils/attendance_resolve.py \
  --country {iso2} \
  --attendance     source/{iso2}/match/attendance.csv \
  --deputies       source/{iso2}/deputies/deputies.csv \
  --interventions  source/{iso2}/matrix/interventions_raw.csv \
  --matching       source/{iso2}/match/matching_table.csv \
  --index-out      source/{iso2}/match/attendance_index.csv \
  --overrides-out  source/{iso2}/match/matching_overrides.csv \
  --map-threshold 88 --constrain-threshold 82
```

Qué hace `attendance_resolve.py` (precisión > recall, por diseño):
- **Mapea** cada presente al roster por **cobertura fuzzy de tokens** (cada token
  fuerte del nombre debe estar cubierto; NO usa `token_set_ratio` puro, que da 100
  a cualquier apellido-subconjunto y produce falsos positivos) + vigencia temporal.
- **Re-resuelve cada `speaker_raw` no-rol POR SESIÓN**: para cada sesión en que el
  speaker interviene, el universo de candidatos es el **conjunto de presentes de ESA
  sesión** (no el roster completo, ni la unión de sesiones). Comparar contra ~97
  presentes en vez de 2.371 del roster es la mayor palanca de precisión: el candidato
  tiene que ser alguien que realmente pudo hablar ese día. La unicidad se evalúa dentro
  de la sesión; el `matching_table` global lleva el id modal y los overrides corrigen
  sesión a sesión (mismo apellido → persona distinta según la fecha).
  - **Corrige** asignaciones erróneas por segundo apellido (`DÍAZ`→`Cabrera Diaz`
    ❌ → `Díaz Maynard` ✅) y **rescata** variantes OCR reales (`PASOUET IRIBARNE`
    → `Pasquet Iribarne`). Solo si cobertura de asistencia ≥ 0.5 (evita forzar).
  - **NO fuerza** speakers con pista de nombre que ningún presente satisface
    (`PÉREZ (Carlos Hugo)` sin un Carlos Hugo Pérez presente → queda `unmatched`).
  - Marca estos casos `match_method: "attendance"`.
- **Rescate de variantes OCR contra la lista de presentes — filtro progresivo por
  evidencia combinada** (clave): el índice de candidatos del roster se siembra por
  **token exacto**, así que un apellido OCR-deformado (`ABADALA`, `ABDLA`, `ABDOLA`,
  `ATCHGARRY`, `MONTANEA`) no comparte token con ningún nombre y **nunca llega a ser
  candidato** → queda `unmatched`. El fallback compara el apellido del speaker, por
  **similitud de carácter** (fuzz), contra los **nombres de los presentes** de esa
  sesión (pool pequeño, ya resuelto a id_dep). Compara solo contra tokens de
  **apellido** (no nombre de pila → evita `TOMA`→`Tomás`); `ss` = peor cobertura de
  los apellidos del speaker (todos deben cubrirse → `RODRIGUEZ CAMUSO`→`Rodríguez
  Camusso` ✅, no `Andrade Rodríguez` ❌). Dos regímenes:
  - **Sin pista de nombre**: solo evidencia de apellido → umbral estricto `ss ≥ 0.86`.
  - **Con pista** (paréntesis, `(don Washington)`): se ABRE la ventana del apellido a
    `0.78` y se combina con la similitud del nombre de pila `hs` (verificada contra el
    nombre **completo**, porque la separación nombre/apellidos del roster es ruidosa —
    `Washington` puede estar en apellidos): `combined = 0.45·ss + 0.55·hs`. Un apellido
    flojo (0.78) se vuelve confiable (≥0.80) si el nombre encaja, y uno fuerte NO basta
    si el nombre no encaja (`PÉREZ (Carlos Hugo)` vs `Darío Perez` → reject). Se acepta
    solo si el mejor `combined ≥ 0.80` **y es único** (supera al 2º por ≥0.08) → si dos
    presentes encajan apellido+nombre, es ambiguo y no se fuerza.
  - **Calibración del umbral ancho (0.78):** el suelo de ruido empírico de apellidos
    casuales es ~67 (`bergara`/`garcia`=61, `caranella`/`caraballo`=67); las variantes
    OCR reales puntúan ≥83 (`abdola`/`abdala`=83, `atchgarry`/`atchugarry`=95). 0.78 cae
    en el hueco → separa limpio. Tunable: `--hint-wide`, `--hint-accept`, `--attendance-sim`.
- **Overrides por-fecha** (`matching_overrides.csv`, `date;speaker_raw;id_dep;…`):
  cuando un mismo `speaker_raw` resuelve a personas distintas según la fecha. El
  `matching_table.csv` global lleva el id **modal**; el override corrige sesión a
  sesión. `diaries-merge` aplica el override ANTES del join con deputies.

Lee el JSON de salida (`speakers_rescued`, `speakers_corrected`,
`speakers_split_by_date`, `overrides`) y repórtalo. El paso es **idempotente** y
seguro de re-ejecutar (parte siempre del `matching_table` actual).

## Paso 4c-bis — Vinculación por VENTANA de sesión (`match_ventana.py`)

Método del matching difuso que ningún match directo cubre: **la sesión acota el universo de
personas**. Quien habla en un acta está en esa acta, y casi siempre varias veces; si una forma
sin vincular se parece mucho a otra que SÍ está resuelta **en la misma sesión**, y el candidato
es ÚNICO, se adopta su `id_dep`. Caso origen (CL, 2026-08-10): `La señora MALVENDA (Presidente
pro visional)` sin vincular a un turno de `La señora MALUENDA (Presidenta provisional)` →
CL00656.

**Dos medidas de parecido, porque los fallos son de dos clases** — se toma el MÁXIMO de ambas:

| medida | caso que cubre | ejemplo |
|---|---|---|
| `ratio` | una letra mal leída (OCR) | `MALVENDA` ↔ `MALUENDA` = 87,5 |
| `token_set_ratio` | la misma persona con más nombre | `FLORES` ↔ `FLORES DON IVAN` = 100 |

Solo `ratio` dejaba fuera el caso FLORES (55); solo tokens ataría cualquier apellido suelto.

**Guardarraíles** (los tres, ver el docstring del script): **unicidad** — si en la sesión hay
dos personas distintas por encima del umbral, se descarta (en CL, 110 casos donde vincular sería
una moneda al aire); **los ROLES no juegan** — `PRESIDENTE`, `SECRETARIO`, `MINISTRO`… ni como
origen ni como candidato (su parecido es con el cargo, no con la persona), y los cargos de
GOBIERNO se excluyen también dentro del paréntesis; **normalización previa** — tratamiento, rol
entre paréntesis y `don`/`doña` se retiran antes de comparar.

⚠ **El UMBRAL NO ES TRANSFERIBLE entre países.** El 85 se calibró sobre CL; en cada país nuevo
se calibra con muestra: corre `--medir`, revisa a mano una muestra de las adopciones propuestas
y ajusta `--umbral` antes de aplicar — [[feedback_match_ventana]].

```bash
python3 ~/.claude/skills/diaries-lib/lib/utils/match_ventana.py --country {iso2} --medir
python3 ~/.claude/skills/diaries-lib/lib/utils/match_ventana.py --country {iso2} --umbral {calibrado}
```

## Paso 4c-ter — Nombre PARLAMENTARIO vs civil

**Se casa contra la forma con que EL ACTA nombra al diputado, no contra el nombre civil del
padrón.** Si la fuente del padrón trae ambas formas, el índice de match se construye sobre la
parlamentaria. En BR el padrón fuente trae `nome` (*Vicentinho* — el que usa el Diário) y
`nomeCivil` (*VICENTE PAULO DA SILVA* — el que se usó para casar): matchear contra el civil dejó
fuera **1.121 formas y 41.545 filas** de diputados que SÍ estaban en el padrón. Lo repara
`br_match_nome_parlamentar.py` (desambigua los 320 nombres parlamentarios repetidos por
legislatura; lo que no desambigua **se deja sin vincular** — 798 filas: un hueco declarado vale
más que una atribución inventada). En un país nuevo, comprueba PRIMERO qué forma usa el acta
antes de elegir la columna del padrón contra la que casar — [[feedback_nombre_parlamentario]].

```bash
python3 ~/.claude/skills/diaries-lib/lib/utils/br_match_nome_parlamentar.py --medir   # solo BR
```

## Paso 4c-quater — Género del CARGO: solo la forma FEMENINA vincula por sexo

Solo la forma **femenina** del cargo (`LA PRESIDENTA`, `LA SECRETARIA`) autoriza a vincular a
una mujer; la forma masculina es **genérica** —cubre a cualquiera que ocupe el cargo— y **NO se
vincula en bloque por sexo**. Y una forma de cargo NUNCA se vincula en bloque a una persona: el
cargo lo ocupan personas distintas según el tramo, y la atribución va por tramo
(`diaries-merge`, Paso 3-bis), no por forma global.

Coste medido de ignorarlo: **6.514 filas reatribuidas** por confundir género del cargo con sexo
de la persona, y en UY **16.812 filas de «A PRESIDENTA» atribuidas a un hombre** por vincular la
forma de cargo en bloque — [[feedback_genero_del_cargo]], [[feedback_rol_vinculado_en_bloque]].

## Paso 5 — Resolución LLM (ambiguos + no-coincidencias)

Lee `.tmp_matches.json`. Procesa los entries con `match_method` en `{"ambiguous", "unmatched"}`:

### 5·0 — TRIAJE del residual por PESO (antes de invertir esfuerzo)

⚠ La cobertura se mide POR INTERVENCIÓN, **no por cabezas**. NO persigas la completitud del
roster por sí misma. Antes de resolver los `unmatched` uno a uno o de buscar fuentes externas
de diputados, **ordena los `unmatched` por número de intervenciones** (cuéntalas en
`interventions_raw.csv`) y decide:

- **Top del unmatched con 1–5 intervenciones c/u** → marginales (suplentes/entrantes
  ocasionales, invitados, OCR irrecuperable). Hablan poco; su pérdida de cobertura es mínima.
  **Déjalos en `unmatched`/`role` y documenta el residual — NO raspes fuentes externas.**
- **Top del unmatched con decenas/cientos de intervenciones** → agujero REAL del roster
  (miembros plenos ACTIVOS que la fuente omitió). Ahí SÍ vale rellenar el roster (volver a
  `diaries-deputies` o raspar la fuente oficial) y re-matchear.

El discriminador es el PESO en intervenciones del top del unmatched, no el conteo de personas
faltantes. Un roster "incompleto" en cabezas puede tener cobertura por intervención excelente.

> **Caso real — MX (2026-06):** rellenar el roster desde SIL movió el unmatched de 4%→0.7%, pero
> el mérito NO fueron los suplentes (829 de 1.813 filas añadidas) sino ~984 **propietarios
> activos** que el padrón de origen omitía: Silvano Aureoles (2.300 interv., presidente), Murguía
> (~1.400, presidió), Mario Delgado. Mirar el top del unmatched por peso reveló que no era ruido
> sino presidentes faltantes. Si el top hubieran sido suplentes de 3 frases, la respuesta correcta
> habría sido no hacer nada.

**5a.** Busca contexto en `interventions_raw.csv`: localiza hasta 3 intervenciones antes y 3 después
del primer bloque donde aparece ese `speaker_raw` (quién habló alrededor, partido, tema).

**5b — caso `ambiguous`** (apellido compartido, ya hay `candidates`): elige ENTRE los candidatos del
campo `candidates` usando el contexto:
- El diputado vigente en la fecha de la sesión (ya pre-filtrado, pero confirma con partido/distrito).
- Quién intervino antes/después (turnos por bloque/partido).
- Si el contexto no permite decidir, elige el de mayor `score` y baja la confianza (≤ 0.70 → FLAG).
- Registra `match_method: "llm"`, `id_dep: {elegido}`, `confidence: {tu_estimación}`.

**5c — caso `unmatched`** (identificar desde cero consultando `deputies/deputies.csv`):
- Variantes ortográficas, abreviaciones, errores OCR (rn→m, li→h, ñ→n), títulos/cargos en el crudo.
- Heurística 2 (expansión de iniciales) como punto de partida si arrojó candidatos.
- Filtra mentalmente por la fecha de sesión (mandato del diputado).

**5d.** Si lo identificas con confianza razonable: `match_method: "llm"`, `id_dep`, `confidence`.
**5e.** Si no: `match_method: "unmatched"`, `id_dep: null`, `confidence: 0.0`.

## Paso 6 — Construir matching_table.csv

```bash
mkdir -p source/{iso2}/match/
```

Consolida todos los resultados en `source/{iso2}/match/matching_table.csv` con columnas:
`speaker_raw, n_interv, id_dep, nombre_completo, match_method, confidence, notas`

⚠ **`n_interv` es OBLIGATORIA: el nº de intervenciones de ese `speaker_raw` en la matriz.** Sin ella
la tabla no dice **dónde importa cada decisión**, y el revisor humano trata igual una grafía de
2.239 intervenciones y una de 3. Es el dato que permite priorizar el esfuerzo: en EC el 26% del
residuo estaba en 30 grafías y el resto repartido en 8.565 — información que no se puede deducir
de la tabla sin este campo. Cuéntala desde `interventions_raw.csv`, nunca la estimes:

```python
from collections import Counter
w = Counter()
for r in csv.DictReader(open(f"source/{iso2}/matrix/interventions_raw.csv"), delimiter=SEP):
    w[(r.get("speaker_raw") or "").strip()] += 1
# ...luego, por fila: "n_interv": w.get(sr, 0)
```

La revisión humana se hace **sobre esta tabla completa**, nunca sobre un extracto: ver 6c, que
explica por qué recortarla a «solo lo dudoso» destruye el contexto necesario para resolverla.
`diaries-merge` **ignora** la columna —selecciona las suyas por lista blanca en `merge_tables.py`—
así que añadirla no rompe el join.

⚠ **`nombre_completo` SIEMPRE del roster, uno por `id_dep`** (no del string del candidato fuzzy/LLM).
Tras asignar `id_dep`, rellena `nombre_completo` con el nombre canónico del roster para ese id. Si no,
el mismo id_dep aparece con nombres distintos según el método ("Fabio Amín" vs "Fabio Raúl Amín Saleme"
para CO00235) → inconsistencia que dispara revisión manual innecesaria. Verifica al final: 0 id_dep con
>1 `nombre_completo` distinto. (Lo mismo si fusionas ids duplicados: re-aplica el nombre canónico a TODAS
las filas de ese id, no solo a las que cambiaron de id.)

donde `match_method` es uno de: `exact`, `fuzzy`, `structural`, `attendance`, `llm`, `manual`, `unmatched`.
(`manual` = corrección humana → **autoridad máxima**: el Paso 4c y `diaries-merge`
NUNCA la sobrescriben, igual que `role`. Si editas `matching_table.csv` a mano, marca
las filas corregidas como `manual` para protegerlas de cualquier re-ejecución.)
(`attendance` = resuelto/corregido por el pase de lista del Paso 4c; si se generó
`matching_overrides.csv`, déjalo en `match/` — lo consume `diaries-merge`.)
(`ambiguous` es un estado intermedio del paso 4; tras el paso 5 todos quedan resueltos como
`llm` o `unmatched`. Si por alguna razón quedara algún `ambiguous` sin resolver, trátalo como
`unmatched` a efectos de cobertura.)

### 6a — `unmatched` está SOBRECARGADO: sepáralo en dos

Un solo estado esconde dos problemas con dueños distintos, y mezclarlos es lo que hace la revisión
manual tan pesada:

| estado | significado | dueño del arreglo |
|---|---|---|
| `NOT_SPEAKER` | no es una persona (partido, órgano, articulado…) | `diaries-tag` — es un artefacto del tagger |
| `unmatched` | **es** una persona, pero no está en el roster | `diaries-deputies` — es un hueco del padrón |

Distinguirlos no es cosmética: cada uno se arregla en un skill distinto, y la métrica de cobertura
solo debe descontar `NOT_SPEAKER` (con `role`), nunca `unmatched` — que es deuda real.

### 6b — Re-ejecutar el match sobre una tabla ya revisada

⚠ Si `matching_table.csv` ya existe y contiene revisión humana, **reinyecta** las filas con
`match_method` ∈ {`manual`, `NOT_SPEAKER`, `role`} ANTES de recalcular, y sáltate esos
`speaker_raw` en el bucle. Sin esto, cada mejora del matcher destruye horas de trabajo del usuario.

```python
HUMAN = {r["speaker_raw"]: r for r in csv.DictReader(open(prev))
         if r["match_method"] in ("manual", "NOT_SPEAKER", "role")}
...
if sr in HUMAN:                      # decisión humana: intacta
    table.append(HUMAN[sr]); continue
```

Normaliza a minúscula al leer: los editores de hoja de cálculo devuelven `MANUAL`, y
`merge_tables.py` solo protege `manual`.

### 6c — La revisión se hace sobre la tabla COMPLETA. NO generes un archivo de extracto

⛔ **NUNCA generes `revision_pendiente.csv` ni ningún otro extracto de «solo lo dudoso».** Es un
error de diseño, no una preferencia de estilo: **el extracto elimina justamente el contexto que hace
falta para resolver los vacíos.**

Los casos que quedan sin vincular son los que el regex y el matching difuso no supieron resolver.
Resolverlos a mano es un trabajo de **reconocimiento de patrones**: se identifica una grafía dudosa
comparándola con las que sí se resolvieron —variantes del mismo apellido, el mismo orador escrito de
otro modo dos filas más abajo, la forma que el OCR degradó— y todo eso desaparece al recortar la
tabla a las filas problemáticas. El revisor se queda mirando `ARREAGA PAZMIÑO` en el vacío, cuando
la respuesta estaba en la fila `ARRIAGA PAZMIÑO` que el extracto no incluye porque ya tenía match.

En su lugar, **enriquece `matching_table.csv`** con las columnas que hacen la revisión eficiente sin
perder contexto, y entrégala completa (o cópiala a `matching_table_manual.csv` para que el usuario
edite sin miedo a que una re-ejecución la sobrescriba):

| columna | para qué |
|---|---|
| `n_interv` | **peso** — dónde importa cada decisión (Paso 6, obligatoria) |
| `prioridad` | naturaleza del caso, vacía si el match es firme (ver tabla abajo) |
| `primera_fecha` / `ultima_fecha` | ventana temporal del orador, para cotejar con el mandato |
| `candidatos` | los 3 mejores del roster con su score, en los casos dudosos |

| prioridad | qué es |
|---|---|
| `0-CONJUNTA` | dos oradores en un marcador (4a-ter) |
| `1-AMBIGUO` | empate entre candidatos sin resolver |
| `2-SIN_MATCH` | persona probable ausente del roster |
| `3-FUZZY_BAJO` | match con confianza < 0.93 |
| `4-ASISTENCIA_DEBIL` | resuelto por pase de lista con soporte < 0.80 |

Ordena por `speaker_raw` **alfabéticamente**, no por prioridad: las variantes de un mismo apellido
quedan contiguas, que es precisamente la adyacencia que el revisor necesita. La priorización por
impacto se obtiene ordenando por `n_interv` en la hoja de cálculo cuando haga falta — y sin perder
las filas resueltas al hacerlo.

**La maquinaria de esta hoja YA existe — úsala, no la reconstruyas** (§0.1 del plan de
reproceso: grep `lib/` antes de construir):

```bash
# exporta la hoja de revisión con candidatos, mandatos, contexto y peso ya calculados
python3 ~/.claude/skills/diaries-lib/lib/utils/export_match_review.py --country {iso2}
# reimporta la hoja revisada (.numbers o .csv), comprobando ANTES de escribir
python3 ~/.claude/skills/diaries-lib/lib/utils/import_match_review.py --country {iso2} --file … --dry-run
python3 ~/.claude/skills/diaries-lib/lib/utils/import_match_review.py --country {iso2} --file … --apply
```

`export_match_review.py` ordena por peso (`n_filas`) y trae candidatos del padrón con su
mandato más un fragmento de intervención; `import_match_review.py` verifica que cada `id_dep`
existe en el padrón, lista las contradicciones contra el **CONJUNTO** de ids de cada forma (no
contra uno solo) y **respeta las celdas vacías** como decisión humana. Ver sus docstrings.

## Paso 6-final — RE-IMPONER la vinculación congelada (OBLIGATORIO)

Tras reconstruir y enriquecer la tabla (Pasos 4–6c), vuelve a imponer las decisiones congeladas:

```bash
python3 ~/.claude/skills/diaries-lib/lib/utils/frozen_matching.py --country {iso2} --check
python3 ~/.claude/skills/diaries-lib/lib/utils/frozen_matching.py --country {iso2} --apply
```

⚠⚠ **Este paso es el que protege de verdad, no el Paso 0.** En un arranque desde cero la tabla
no existe cuando corre el Paso 0, así que su `--apply` es un no-op (`frozen_matching.py`
devuelve `None` sin tabla actual): sin este paso final, las decisiones congeladas se pierden
**justo en el escenario para el que se congelaron** — el reproceso completo (§6.1 del plan).

Lo que ya no casa —formas congeladas que la nueva extracción cambió— **se INFORMA en
`docs/{iso2}/vinculacion_huerfana.csv`, nunca se borra**: cada huérfana es una decisión humana
que hay que rehacer sobre la forma nueva. Reporta los recuentos del `--check` (coinciden ·
contradicen · nuevas · huérfanas) en el resumen del Paso 10.

## Paso 7 — Calcular confianza global y determinar status

```
n_unique_speakers = total de speakers únicos
n_matched_auto = count de filas donde match_method in (exact, fuzzy) AND confidence >= threshold_auto
confianza_global = n_matched_auto / n_unique_speakers
```

Determina status:
- Si `(n_unique_speakers - n_matched_auto) / n_unique_speakers > 0.10`: status = `flag`
- Si `(n_unique_speakers - n_matched_auto) / n_unique_speakers > 0.30`: status = `halt` (demasiados sin resolver)
- En caso contrario: status = `complete`

## Paso 8 — Actualizar estado

```bash
python ~/.claude/skills/diaries-lib/lib/utils/update_state.py \
  --country {iso2} --skill diaries-match --session "_country" \
  --status {status} --confidence {confianza_global} \
  --output "source/{iso2}/match/matching_table.csv"
```

## Paso 9 — Limpiar temporales

```bash
rm -f source/{iso2}/.tmp_speakers.json source/{iso2}/.tmp_matches.json
```

## Paso 10 — Resumen

Imprime:
```
diaries-match — {iso2}
Speakers únicos:     {N_total}
  Exact match:       {N_exact}
  Fuzzy match:       {N_fuzzy}
  Ambiguos→LLM:      {N_ambiguous_resueltos}  (apellido compartido, desambiguados por contexto)
  Structural match:  {N_structural}
  LLM match:         {N_llm}
  Sin resolver:      {N_unmatched}
Tasa de cobertura:   {confianza_global:.1%}
Congelado (--check): {N_frozen_aplicadas} aplicadas · {N_frozen_contradicen} contradicen · {N_frozen_huerfanas} huérfanas → docs/{iso2}/vinculacion_huerfana.csv
Status:              {status}
```

Si hay speakers sin resolver, muestra tabla:
```
Speakers no vinculados:
  {speaker_raw_1}
  {speaker_raw_2}
  ...
```

Si status es `flag` o `halt`: "Ejecuta /diaries-review --country {iso2} --skill diaries-match para resolver los casos pendientes."


---

## Dejar rastro de la revisión humana ⚠

Cuando el usuario revise la vinculación, **marcar en `matching_table.csv` cada fila que pase
por sus ojos, aunque la decisión sea confirmar lo propuesto**:

| columna | valor |
|---|---|
| `revisado_por` | `usuario` |
| `revisado_en` | fecha ISO |

**Por qué importa, con el coste ya medido.** La revisión manual de los quince corpus se hizo
sin tocar `match_method` ni `notas`, así que la tabla **no distingue «revisado y confirmado»
de «nunca mirado»**. Consecuencia: la validación técnica volvió a marcar **128 casos ya
resueltos**, y solo se corrigió porque el investigador lo recordaba. Con una sesión de por
medio, esa información se habría perdido.

Es trivial en el momento e irrecuperable después. Aplica igual a `/diaries-review`: registrar
también **lo verificado-y-correcto**, no solo las correcciones — un caso confirmado es tan
informativo como uno corregido.

Si la revisión revela un criterio nuevo, registrarlo con `/diaries-decide`.
