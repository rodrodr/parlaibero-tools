---
name: diaries-correct
description: "Corrige párrafos e hifenaciones en texto extraído: pase determinista vía script + resolución LLM de saltos ambiguos."
allowed-tools: [Read, Write, Edit, Bash]
---

Argumentos: `--country {iso2}` + uno de `--session YYYY-MM-DD` | `--batch YYYY-MM` | `--all` + opcionales `--force`, `--dry-run`

---

## ⚠⚠ SECUENCIA CANÓNICA DE LIMPIEZA (orden obligatorio)

`correct_text.py` ejecuta cinco pasos, **en este orden**, leyendo el vocabulario de CADA país de su
`country_config`. El orden no es negociable: cada paso depende del artefacto que deja el anterior.

1. **Identificar el separador de página** — `---PAGE N---` (lo pone la extracción) o el que use el país.
   Es el ANCLA de todo lo demás.
2. **Eliminar el mobiliario** (cabeceros/piés) anclado a ese separador — bloque + folio suelto,
   reconectando la frase que el bloque parte. Vocabulario en `correct.furniture_block`.
3. **Eliminar el separador de página** — solo AHORA, ya vacío de mobiliario. Quitarlo ANTES (paso
   más temprano) deja el mobiliario huérfano: destruye el ancla sin limpiar (error BR 2026-08-22).
4. **Aislar los marcadores de orador** (pre-tag scan) — una línea en blanco delante de cada
   `speaker_tag_patterns`, como frontera dura que el paso 5 no cruza y el tagger ve sin ambigüedad.
   Aislar es más robusto que solo "proteger" el marcador durante el merge.
5. **Restaurar la fluidez** — deshifenizar y unir las líneas de caja que cortan frases/títulos,
   DENTRO de cada turno, sin cruzar los marcadores del paso 4.

Es el **esqueleto común**; el separador, el mobiliario y el marcador **son de cada país** y se
DESCUBREN leyendo su texto (y por década, porque el formato cambia con la época), se GUARDAN en su
`country_config`, y se VERIFICAN sobre ese país antes de promover. Nunca en bloque, nunca adivinando
ni reusando los de otro país. Ver la directiva de procesamiento por país en la memoria del proyecto.

## ⚠ `correct` es el ÚNICO limpiador (rediseño 2026-08)

Desde el rediseño, `diaries-extract` entrega `extracted/` **fiel y SIN limpiar** (con los marcadores
de página `---PAGE N---` conservados). Por tanto **toda** la eliminación de cabeceros, folios,
mobiliario, mastete e hifenización ocurre AQUÍ, una sola vez. Ya no hay `strip_headers` en extract ni
capa `text/`. El límite tiene tres partes, que bracketean el bucle por sesión:

- **Paso 0b — DESCUBRIR el mobiliario** del país → `country_config` (una vez por país, antes del batch).
- **Paso 2 — APLICAR** los 5 pasos por sesión (`correct_text.py`).
- **Paso 2-R — VERIFICAR EL RESIDUO** (bucle supervisado): el config inicial NUNCA basta —OCR y
  cambios de formato por década dejan variantes— así que se mide lo que sobrevivió y se refina hasta ~0.
  Ver [[feedback_residuo_mobiliario_loop]].


## Paso 0 — Leer configuración del país

Lee `country_config/{iso2}.yaml`.

Extrae (todo lo específico del país vive aquí; el código es solo el motor):
- `speaker_tag_patterns` — formas del marcador de orador (pasos 4 y 5: aislar y proteger). DESCUBRIR
  leyendo el texto y por década; incluir la pareja de género (O SR./A SRA., EL/LA…) y las variantes
  de separador (raya que falta, se parte, u OCR la vuelve otro carácter).
- **Mobiliario (paso 2), CINCO clases según cómo aparezca — descubrir por país y por década:**
  - `correct.furniture_block` — bloque anclado al separador de página, o 2+ líneas consecutivas del
    vocabulario. Para formas AMBIGUAS que solas podrían ser texto (BR `^Data:` / `^Montagem:`): se
    retiran en bloque, con el folio suelto, y se detienen en un marcador.
  - `correct.furniture_line` — línea ENTERA inequívoca (remove-if-alone). Se retira aunque vaya
    sola porque no puede ser discurso; si partía una frase, el merge la reconecta. Anclar a línea
    entera (`(?i)^\s*Página\s+\d+\s*$`, `^\s*Gaceta del Congreso \d+$`). CO.
  - `correct.furniture_masthead` — MASTETE/CARÁTULA con **keep-first**: se CONSERVA la primera
    aparición (prolegomena de la página 1) y se retiran solo las repeticiones en páginas 2+. Para
    el encabezado del editor (`IMPRENTA NACIONAL`, `DIRECTORES:`, `Gaceta del Congreso N`,
    `Página N`) que es prolegomena una vez y mobiliario cuando se repite. Regla del investigador:
    «dejarlo en la primera página, retirarlo solo si se repite». Nunca borra prolegomena.
  - `correct.furniture_prefix` — DECAPITACIÓN: cabecero corrido pegado como PREFIJO de una línea de
    contenido (`GACETA DEL CONGRESO 593 tivamente, quiero…`). Recorta solo el prefijo y conserva el
    resto. ⚠ El patrón DEBE ser específico (con su número) y anclar a `^`: un prefijo laxo decapita
    prosa (`C O R T E S` se comía «Cortes»). CO.
  - `correct.furniture_inline` — mobiliario EMBEBIDO a MITAD de línea (existe en
    `correct_text.py::quita_mobiliario_inline`): re.sub por BÚSQUEDA dentro de la línea — se
    reemplaza por un espacio y se reúne la frase, a diferencia de las clases por línea entera.
    Para el cabecero corrido que la página incrusta DENTRO de una oración — ES: `<día> DE <MES> DE
    <año>.-NÚM. n` interleado a mitad de frase (18.113 fuera). Guardarraíl
    `correct.furniture_inline_maxlen` (default 80): un match más largo probablemente tragó texto
    real y se DESCARTA intacto. El patrón debe ser ESPECÍFICO y anclado a una forma de mobiliario;
    uno laxo mid-text se come prosa. El guion pegado a letra (`res-`) NO se toca aquí: lo une la
    deshifenización.
    ⚠⚠ **DEFECTO DE ORDEN CONOCIDO, NO REPARADO (`tr-0094`).** `quita_mobiliario` —que aplica
    `furniture_line`— corre ANTES que `quita_mobiliario_inline`, así que **la línea que solo SE
    CONVIERTE en mobiliario puro después del recorte inline queda huérfana y nadie la vuelve a
    mirar**. Medido en EC: `CONGRESO NACIONAL ACTA No. 001` pierde su `ACTA No. 001` por
    `furniture_inline` y deja `CONGRESO NACIONAL` suelto — 1.959 líneas que en `extracted/` no
    existen, las CREA el motor. Afecta a todo país que combine ambas clases. Al medir residuo de
    membrete, descuenta esta causa antes de escribir un patrón nuevo: el patrón no falta, el orden
    falla. La reparación natural —volver a pasar solo `furniture_line` tras el recorte inline— debe
    ser opt-in y medirse aparte.
  - ⚠⚠ **NUNCA borrar PROLEGOMENA.** El índice/CONTENIDO, la carátula, el sumario y el pase de
    lista (una sola vez, al arranque, antes de la primera intervención) son Prolegomena
    (`intervention_order = 0`) y **jamás se excluyen** — es el principio «nada se borra». Solo se
    retira el mobiliario de página REPETIDO (número de página, cabecero corrido, `Página N`/`Gaceta
    N` en cada folio). Las entradas del índice tienen forma de marcador (`Intervención del
    Representante X …….. 15`) pero NO son turnos: se conservan como texto de prolegomena y no se
    parten en marcadores (partirlas crea filas espurias en matrix). Los patrones de mobiliario
    anclan formas de MOBILIARIO, nunca `^Intervención…`/`^Palabras…`.
  - NUNCA por palabra suelta que también sea discurso (`Obrigado.`, `País.`) ni por subcadena; el
    número puede llevar separador de miles (`\d[\d.]*`); las formas cambian de década (el masthead
    de CO son líneas sueltas hasta 2019 y UNA línea fundida desde 2020).
- `correct.marker_reassembly` / `marker_join_next` + `marker_join_terminator` — reensamblar el
  marcador cuando el PDF lo parte en varias líneas (terminador `:` por defecto; ` - ` en BR, `.—` en PE).
- `correct.paragraph_accumulate` (default: false) — unir por PÁRRAFO, no por pares. Actívalo donde la
  fuente emita una línea de columna por bloque.
- `correct.split_at_sentence_end` (default: false) — cerrar párrafo donde la frase acaba sin llenar
  la caja. Actívalo si el país TIENE estructura de párrafo; déjalo en false donde no la haya (BR).
- `correct.marker_absorbs_below` (default: false) — el marcador absorbe su propio discurso hacia
  abajo. `true` donde el marcador comparte línea con el inicio del discurso (BR, PT); `false` donde
  ocupa la línea entera (PA, CR: patrón anclado a `$`), porque unirlo lo destruiría.
- `correct.join_split_titles` (default: false) — une el título en MAYÚSCULAS partido por la caja
  (existe en `correct_text.py`, gated → `unir_titulos_partidos.py`; Fase A.7: 341.310 uniones en
  15/16 países). Opt-in por país y SIEMPRE con TODAS las guardas de `clasifica()`: roster/mesa,
  epígrafe (`ARTÍCULO/CAPÍTULO/SUMARIO…`), party, asistencia, roll-call, índice, basura OCR
  (stutter), namelist (pase de lista SIN palabra de estado — EC 89 %→20 %), tabla y mobiliario de
  taquigrafía (BR/PT). **Unir en bloque fusiona el pase de lista**: el «título partido» son OCHO
  fenómenos y solo tres se unen. Verificar por país ejecutando la CLI del módulo (que ES dry-run por diseño: imprime la clasificación sin escribir) antes de promover. Ver
  [[feedback_titulo_mayusculas_partido]].
- `correct.hyphen_join` (default: true) · `threshold_auto` (0.85) · `threshold_flag` (0.65)
- `correct.min_paragraph_chars` — umbral de "línea corta". **Déjalo sin fijar (o 0): se mide la caja
  del propio documento** (p90×1,15). Un fijo de 80 perdía las líneas que llegan justo al borde.
- ⚠⚠ `correct.pairs_merge_full_lines` (default: false) — **quita la puerta de LONGITUD del modo
  pares, que es el mayor defecto de reflujo del motor.** El modo pares REINYECTA la línea fusionada,
  así que une hasta que la línea alcanza la caja y ahí PARA, a mitad de frase. Atribución con la
  caja medida en `extracted/`: bloquea el **95,5 %** de los cortes intra-frase de DO y el **99,9 %**
  de los de PE (caja media 85 car.). Efecto al activarla: DO 594.092 → 34.378 cortes, PE 3.062.595 →
  4.282, con Δ = 0 en marcadores, alfanuméricos y celdas de votación.
  **No es el acumulador**: mantiene la reinyección, que es lo que conserva la deshifenización
  (`pe-0004` descartó `paragraph_accumulate` porque la rompía: residuo «X- y» de 0 a 12.007; con la
  bandera se queda en 1.045 → 1.045). Va acotada por `max_paragraph_chars` — **sin tope encadena el
  documento entero**, medido en DO: una línea de 21.413 caracteres. Y respeta
  `min_paragraph_chars: 0`, el interruptor que apaga el merge: saltárselo aplanó las 7 sesiones de
  OCR-HTML de DO (79.544 líneas → 5.230, fundiendo las `<td>`). Opt-in por país; medir marcadores
  antes y después. `tr-0092`.
- `correct.merge_over_protected_after_comma` (default: false) — ignora la protección de la línea de
  ABAJO cuando la de arriba deja la frase abierta en **coma**. La protección automática por palabra
  de rol (`_MARKER_PROTECT_DEFAULT`: `PRESIDENT[AE]|SECRETARI[OA]|…`) toma por marcador nuevo la
  continuación de un cargo que envuelve, y PARTE el marcador real:
  `INTERVENCIÓN DE LA SEÑORITA X,` ⏎ `PRESIDENTA DEL CONSEJO…`. Un marcador nunca empieza justo
  después de una coma. EC: 1.379 casos → 0, sin perder ninguno de los 1.253.728 que casan
  `speaker_tag_patterns`. Repara además los bloques de firma. `tr-0093`.
- `correct.ocr_leader_tail` (default: false) — recorta la GUÍA DE PUNTOS que el OCR deja al final de
  línea (`Muchísimas gracias. =————“=““=“=iiiiiiimiiiiion`). **NUNCA borra la línea**: el residuo va
  siempre pegado a contenido real —en EC, 0 líneas enteras de basura frente a 6.273 colas sobre
  contenido, y la línea que la lleva puede ser un cambio de presidencia o un voto nominal—.
  ⚠ Tres vías se probaron y DESTRUYEN, no las repitas: una **regex** casa por la izquierda y se
  llevaba «secretario general de la Asamblea Nacional» (2.971 de 7.130 recortes); **trocear por
  espacios** perdía el nombre cuando la basura va pegada sin espacio (`Espín Sofía.------===nmmmm`
  → se perdía «Sofía», y son VOTOS NOMINALES); y juzgar la degeneración sobre el token CON su
  puntuación daba positivo en `Presidente...` por el triple punto (166 casos). El criterio válido:
  el corte solo cae **después de un carácter que no sea letra**, y la cola prueba degeneración por
  tres letras idénticas seguidas, guía de símbolos o diversidad ≤ 0,45. EC: colas 19.493 → 8.330 y
  los nombres de votación nominal SUBEN de 9.316 a 10.815, porque al recortar la cola el nombre
  vuelve a ser reconocible. `ec-0008`.

---

## Paso 0b — Descubrir el mobiliario del país → `country_config` (una vez por país)

Antes de corregir el batch, hay que DESCUBRIR qué cabeceros/folios/mastete recurren en `extracted/`
(ahora fiel, con marcadores de página) y registrarlos en `correct.furniture_*`. **No lo adivines: se
descubre por FRECUENCIA sobre el corpus del país, por década.** Reutiliza el motor que ya existe (no
reimplementar — lección de la auditoría):

```bash
# Descubre cabeceros/pies recurrentes en la zona-borde de cada página (frontera = ---PAGE N---):
python3 ~/.claude/skills/diaries-lib/lib/utils/strip_headers.py \
  --text-file source/{iso2}/extracted/{una_sesion}.txt \
  --page-break-marker '---PAGE' --report        # imprime candidatos + ejemplos, NO escribe
# Alternativa por vecinos del folio (ancla dura), útil cuando el cabecero es variable:
python3 ~/.claude/skills/diaries-lib/lib/utils/strip_matrix_furniture.py --country {iso2} --discover
```

Con los candidatos, redacta `correct.furniture_*` (las 5 clases del Paso 0) y **VERIFÍCALOS sobre una
muestra ALEATORIA antes de promover** (`--sample`). Caveats **inviolables** (portados de
`strip_matrix_furniture`, cada uno pagó un corpus):

- ⚠⚠ **Por LÍNEA ENTERA ANCLADA (`^…$`), JAMÁS por subcadena.** Un detector por tokens institucionales
  marca `LA CÁMARA DE REPRESENTANTES,` (13.813 líneas de prosa en UY), la fórmula de promulgación de AR
  y el encabezamiento de las cartas de MX. Todas llevan el nombre de la cámara y todas son texto legítimo.
- ⚠ **El mobiliario viene en BLOQUE, y exigirlo separa el mueble de la prosa.** La cabecera de UY son
  tres líneas —folio · `CÁMARA DE REPRESENTANTES` · fecha—. Aislada, esa línea es el encabezamiento de
  una carta. Exigir el bloque descartó 22.610 apariciones sueltas de 38.696.
- ⚠ **Un folio NO es «una línea de dígitos»**: es una línea de dígitos que no cierra frase
  («…de 14 de enero de / **1994.**» es un año partido), que no está entre 1800-2100, y que no tiene otro
  número al lado (una tabla de votación es una columna de números). Sin cabecera que lo ancle, un número
  suelto NO es folio: AR tiene 18.677 líneas de solo dígitos y PA 22.871, y NINGUNA es folio (son puntos
  del orden del día). El descubrimiento se ancla al marcador de página o al bloque, nunca al número solo.
- ⚠ **El cabecero puede llevar PEGADA la palabra que la página cortó** —«Miércoles 7 de noviembre de
  2007 **clusive**…», de «in-clusive»—. Por eso `correct.furniture_prefix` DECAPITA solo el prefijo y
  conserva el resto (borrar la línea entera se llevó 17.182 casos de texto real en UY).
- ⚠ **Masthead con keep-first**: la carátula/mastete es Prolegomena la PRIMERA vez (pág. 1) y mobiliario
  cuando se repite (`correct.furniture_masthead`). Nunca borra la primera aparición.
- ⚠⚠ **NUNCA borrar Prolegomena** (índice, carátula, sumario, pase de lista de arranque): son
  `intervention_order = 0`. Las entradas de índice tienen forma de marcador (`Intervención del
  Representante X …….. 15`) pero NO son turnos — se conservan, no se parten (partirlas crea filas
  espurias en matrix). Los patrones de mobiliario anclan formas de MOBILIARIO, jamás `^Intervención…`.
- **Por DÉCADA**: las formas cambian con la época (el masthead de CO son líneas sueltas hasta 2019 y UNA
  línea fundida desde 2020). Descubre y verifica en cada tramo temporal.

Guarda lo verificado en `country_config/{iso2}.yaml` (`correct.furniture_block/line/masthead/prefix/inline`).
Este paso se hace una vez por país (y se re-abre cuando el bucle de residuo, Paso 2-R, encuentra variantes).

---

## ⚠ Deuda declarada: los overrides por ÉPOCA no los lee el motor

Cuando un país necesita una regla **solo para un tramo de años** —MX aplicó una Fase B de reflujo
acotada a 1988-1990, precedente CL— la sede natural es una clave tipo `correct_era_overrides` en el
`country_config`. **Pero `correct_text.py` no la lee**: la aplica un driver externo. Consecuencia
medida (MX, 2026-08-25): `/diaries-correct --country mx --all` **sin ese driver NO reproduce** el
tramo, aunque el config lo declare.

Mientras esto siga así: (1) **declara el override en el config igualmente**, para que conste qué se
hizo y con qué cifras; (2) **deja el driver junto al informe**, no en un scratchpad efímero; y
(3) **dilo en el informe de cierre como deuda de infraestructura**, no como detalle. Un corpus que
no se reproduce con el comando documentado tiene un problema aunque el dato esté bien.

## Paso 1 — Determinar lista de sesiones

**`--session YYYY-MM-DD`**: una sola sesión.

**`--batch YYYY-MM`**: todas las sesiones cuyo session_id empieza por `YYYY-MM`:
```bash
ls source/{iso2}/extracted/ | grep "^YYYY-MM"
```

**`--all`**: todas las sesiones con texto extraído:
```bash
ls source/{iso2}/extracted/
```

Filtra sesiones ya completadas en diaries-correct (salvo `--force`): lee `state/{iso2}/pipeline_state.json` y excluye las que tengan `skills.diaries-correct.status == "complete"`.

---

## Paso 2 — Procesar cada sesión

### 2a. Verificar prerequisito

```bash
ls "source/{iso2}/extracted/{session_id}.txt" 2>/dev/null
```

Si no existe: registra error "Texto extraído no encontrado para {session_id}. Ejecuta diaries-extract primero." y salta.

### 2b. Crear directorio de salida

```bash
mkdir -p source/{iso2}/corrected/
```

### 2b-bis. Protección de marcadores en el merge (automática) + reensamblado (config)

⚠ **El merge de párrafos puede DESTRUIR marcadores de orador** (verificado PA 2026-07):
si la línea previa termina sin puntuación (OCR "Peraltao" por "Peralta."), el join absorbe
el marcador a mitad de línea y diaries-tag ya no lo ve → la intervención entera se atribuye
al orador ANTERIOR (falso negativo silencioso, invisible para verify_tagging).
`correct_text.py` incluye protección AUTOMÁTICA (`_MARKER_PROTECT_DEFAULT`: dash+MAYÚSCULA,
honoríficos H.D./H.L./LIC., roles, SEÑOR+CAPS) — nunca fusiona una línea con forma de marcador.

Para PDFs de columna estrecha que FRAGMENTAN el marcador en varias líneas
("-H.D.\nNORMAN\nSCOTT"), activa el reensamblado en el country_config:
```yaml
correct:
  marker_reassembly:      # prefijos regex de marcador (ver pa.yaml como referencia)
    - "^[-–—]\\s*(?:H\\.?\\s?[DL]\\.?|LIC\\.?)..."
```
La auditoría que detecta este problema aguas abajo está en diaries-matrix (Paso 5).

⚠⚠ **El reensamblado también puede DESTRUIR el marcador que pretende reparar** (medido PA
2026-08-25, reproducción en `pa_correct/defectos_motor.py`). `reassemble_markers()` decide con
`_is_frag()`, que **no exige que el fragmento parezca parte de un nombre propio**: acepta basura de
OCR de 1-3 caracteres, epígrafes en versales y acotaciones entre paréntesis.

| unión que hace el motor | efecto |
|---|---|
| `-PRESIDENTE` ⏎ `F-` → `-PRESIDENTE F-` | **deja de ser etiquetable** |
| `-PRESIDENTE` ⏎ `(RECESO)` | **deja de ser etiquetable** |
| `-RELATOR` ⏎ `ORDEN DEL DIA` | sigue casando pero **contamina el `speaker_raw`** → daña el `match` **sin mover ningún recuento** |

Coste medido: 3 sesiones de 3.654 en PA. **Antes de activar `marker_reassembly`, prueba unión a
unión** clasificando si el resultado **sigue casando algún `speaker_tag_pattern`**: en PA ese ensayo
reveló que un patrón heredado creaba 0 marcadores y destruía 4, y era el mecanismo del −62 %
en miniatura. Si el marcador del país **ya viene completo en su línea**, el reensamblado solo puede
dañarlo: muévelo a `protect_extra`, que conserva la protección y pierde la absorción.

**Marcador partido en DOS líneas → `marker_join_next` (con condición de cierre).**
Distinto del caso anterior: aquí el marcador no está fragmentado en muchos trozos, sino cortado
justo por la mitad, y la línea de arriba **no llega a los dos puntos**:

```
EL R. SEGUNDO VICEPRESIDENTE, MENDEZ HERBRUGER, EN FUNCIONES DE
PRESIDENTE:  Compañeros diputados…
```

`marker_reassembly` **no sirve aquí y empeora el resultado**: unir por prefijo bajó el etiquetado
de GT de 224.934 a 199.863 (−25.071), porque arrastraba líneas que empiezan igual sin ser marcador.
Lo que lo hace seguro es exigir que la continuación **cierre** el marcador:

```yaml
correct:
  marker_join_next:                 # une línea+siguiente SOLO si:
    - '^(?:EL|LA)\s+R\.\s'          #   1) la 1ª casa el patrón y NO tiene ':'
    - '^(?:EL|LA)\s+SEÑOR[A]?\s'    #   2) la 2ª SÍ tiene ':' en sus primeros 40 caracteres
```

Sin la condición (2) la regla es una fusión ciega; con ella solo actúa donde hay un marcador
partido de verdad. GT: 230.123 → 240.462 etiquetadas (+10.339), **ninguna caída**.

⚠ **Escribe los patrones simétricos en género** (`(?:EL|LA)`, `PRESIDENT[EA]`, `SEÑOR[A]?`). Una
regla solo masculina aquí no borra intervenciones —eso se vería—: parte a la **misma diputada** en
dos `speaker_raw` distintos y le vincula peor la mitad de sus turnos, sin que ningún total falle.
Ver `feedback_gender_bias_extraction` y la decisión `gt-0005`.

### 2c. Pase determinista

Si `--dry-run`: imprime el comando que se ejecutaría y salta.

Si no es dry-run:
```bash
python ~/.claude/skills/diaries-lib/lib/utils/correct_text.py \
  --input "source/{iso2}/extracted/{session_id}.txt" \
  --output "source/{iso2}/corrected/{session_id}.txt" \
  --config "country_config/{iso2}.yaml"
```
`--config` es lo que hace que corran los 5 pasos con el vocabulario del país (normalizaciones,
reensamblado, mobiliario, aislamiento de marcadores y merge con sus flags). Sin `--config` solo
corre el merge con defaults conservadores. El ancho de caja se mide por documento; no fijes
`--min-paragraph-chars` salvo para forzar un umbral concreto.

El JSON de salida incluye `furniture_removed` (líneas de mobiliario retiradas) y `marker_joins`
(marcadores reensamblados), además de `ambiguous_breaks`.

Lee el JSON de stdout. Estructura esperada:
```json
{
  "total_paragraphs": 312,
  "hyphens_joined": 47,
  "ambiguous_breaks": [
    {
      "line_number": 84,
      "context_before": "...",
      "context_after": "...",
      "candidate_text": "texto del salto en cuestión"
    }
  ]
}
```

### 2d. Resolver saltos ambiguos con tu juicio LLM

Si `ambiguous_breaks` está vacío: salta este paso.

Si hay saltos ambiguos: procésalos en batches de máximo 20.

Para cada salto ambiguo, lee el contexto dado (3 líneas antes y después) y determina:

**Es salto de párrafo real si:**
- El texto antes termina con punto, cierre de comillas, o una oración completa.
- El texto después empieza con mayúscula y es una idea nueva.
- El contexto sugiere cambio temático o cambio de orador.

**Es artefacto (no es salto real) si:**
- La línea anterior termina en medio de una palabra o con coma.
- El texto después es continuación gramatical del anterior.
- Parece un salto de línea de columna de periódico o justificación de imprenta.

Si determinas que un salto es un artefacto (las dos partes deben unirse): edita el archivo de salida directamente con Edit para unir las dos partes con un espacio, eliminando el salto de línea.

Si determinas que el salto es correcto: no hagas nada.

### 2d-bis. GATE DE SALIDA — no puede quedar ningún marcador partido

⚠ **Este es el gate que justifica que `correct` exista.** `diaries-tag` NO puede ejecutarse sobre
`extracted/`: `corrected/` es donde el marcador partido por el ancho de columna se reensambla, y
si aquí queda partido, tag pierde el turno ENTERO sin que ningún recuento lo delate. En PY,
etiquetar saltándose este paso costó ~100.000 turnos —el 25% del corpus— con un total
perfectamente creíble. Ver [[feedback_marcador_partido]].

No basta con haber configurado `marker_reassembly` o `marker_join_next`: hay que **medir el
residuo** sobre `corrected/`, con el vocabulario de cargo del propio país (Paso 0c de
`diaries-tag`), no con una lista adivinada:

```python
import re
from pathlib import Path
from collections import Counter
CAB = r"(?:SE(?:Ñ|N)OR[A]?|DIPUTAD[OA]|PRESIDENT[EA]|SECRETARI[OA]|RELATOR[A]?)"   # ← el del país
COLA = re.compile(r"^[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ .'\-]{1,40}:(\s|$)")
def versal(s):
    L=[c for c in s if c.isalpha()]
    return len(L)>=4 and sum(1 for c in L if c.isupper())/len(L)>=0.8
part=Counter()
for p in Path(f"source/{iso2}/corrected").glob("*.txt"):
    ls=[l.strip() for l in p.read_text(errors="replace").split("\n")]
    for a,b in zip(ls,ls[1:]):
        if versal(a) and re.match(rf"^{CAB}\b[^:\n]{{0,60}}$",a) and COLA.match(b) and versal(b.split(":")[0]):
            part[f"{a[:40]} ⏎ {b[:30]}"]+=1
print(sum(part.values()),"marcadores aún partidos")
for s,c in part.most_common(15): print(f"{c:>5}  {s}")
```

Si sale distinto de ~0, **no avances a tag**: añade el patrón a `marker_join_next` (con la
condición de cierre del Paso 2b-bis) y vuelve a correr. Cose, no aplanes: aplanar el texto
también une el marcador, pero borra la estructura de línea que `conformidad.py` comprueba, y en
CO dejó `speaker_raw` de 6.310 caracteres.

### 2d-ter. GATE del −N de marcadores — el acumulador que los ENTIERRA

⚠⚠ El fenómeno del **−28 % de BR**: el acumulador de párrafos absorbe el marcador de orador dentro
de la línea anterior y lo entierra — el texto no pierde un carácter, pero `tag` ya no ve el turno.
**El −N ES la señal**; verificar con patrones VACÍOS es ciego (un control «0 marcadores rotos» sin
`speaker_tag_patterns` da 0 siempre). Ver [[feedback_correct_furniture_burial]].

Tras el batch, cuenta los marcadores de orador (patrón del país) en `extracted/` vs `corrected/`,
POR SESIÓN:

```python
import re, yaml
from pathlib import Path
cfg = yaml.safe_load(open(f"country_config/{iso2}.yaml"))
pats = [re.compile(x) for x in cfg.get("speaker_tag_patterns", [])]
assert pats, "sin speaker_tag_patterns el control es CIEGO — descúbrelos antes (Paso 0)"
def n_marc(path):
    return sum(1 for l in path.read_text(errors="replace").split("\n")
               if any(rx.search(l.strip()) for rx in pats))
caidas = []
for pe in sorted(Path(f"source/{iso2}/extracted").glob("*.txt")):
    pc = Path(f"source/{iso2}/corrected") / pe.name
    if not pc.exists(): continue
    a, b = n_marc(pe), n_marc(pc)
    if a and (a - b) / a > 0.02:
        caidas.append((pe.stem, a, b, (a - b) / a))
for s, a, b, r in sorted(caidas, key=lambda x: -x[3])[:20]:
    print(f"{s}: {a} → {b}  (−{r:.1%})")
print(f"{len(caidas)} sesiones con caída de marcadores > 2%")
```

Una caída relativa **> 2 %** en una sesión = el acumulador ENTERRÓ marcadores → **HALT esa sesión
y revisar el merge** (`_MARKER_PROTECT_DEFAULT`, `protect_markers`, `paragraph_accumulate`) antes
de avanzar. Un +N es normal (el reensamblado CREA marcadores completos); lo que no puede pasar es
que `correct` destruya los que `extract` entregó.

### 2e. Calcular confianza

⚠ **NO uses el ratio de saltos ambiguos como proxy de confianza.** En diarios de debate
parlamentario, las líneas cortas terminadas en `.?!:` (orden del día, listas de asistencia,
destinos de trámite, marcadores de orador, artículos de ley) son fines de párrafo LEGÍTIMOS,
no artefactos. El ratio es alto POR GÉNERO (medido en UY: 0.31–0.84 en todas las épocas) y la
fórmula por ratio marcaría casi todas las sesiones en FLAG — falso negativo masivo. Los
`ambiguous_breaks` son candidatos a INSPECCIÓN selectiva (Paso 2d), no una métrica de calidad.

El pase determinista es CONSERVADOR (solo une hifenaciones y líneas cortas que NO terminan en
puntuación de cierre) y NUNCA borra contenido. Por eso la confianza se basa en la INTEGRIDAD del
texto de salida:

```
in_chars  = len(texto tras normalizaciones)
out_chars = len(texto corregido)

si out_chars >= 0.80 * in_chars  Y  total_paragraphs > 0  Y  out_chars > 300:
    confidence = 0.95   → complete
si no (pérdida de contenido / salida vacía o minúscula):
    confidence = 0.60   → flag (el corrector pudo fallar; revisar)
```

Esto da `complete` a las sesiones bien corregidas (la inmensa mayoría) y solo eleva a revisión las
que perdieron texto — la señal de fallo REAL.

**En batches `--all` masivos, NO resuelvas los ambiguos uno a uno** (inviable y son mayormente
legítimos): aplica el pase determinista + esta confianza por integridad. La resolución LLM del
Paso 2d queda para sesiones individuales o revisión puntual de un caso concreto.

### 2f. Actualizar estado

```bash
python ~/.claude/skills/diaries-lib/lib/utils/update_state.py \
  --country {iso2} \
  --skill diaries-correct \
  --session {session_id} \
  --status {complete|flag|halt} \
  --confidence {valor} \
  --output "source/{iso2}/corrected/{session_id}.txt"
```

---

## Paso 2-R — Bucle de residuo de mobiliario (supervisado) ⚠⚠

**El config del Paso 0b NUNCA basta a la primera.** Aunque creas haber identificado todas las variantes,
el OCR y los cambios de formato por década dejan cabeceros, folios y mastete que se cuelan al corpus y
hay que remover después. Es un error recurrente (BR `---PAGE N---` 66,9 M car.; `limpiar_mobiliario`
midió residuo en BR 34,66 %, PE 20,89 %, ES 4,26 %). Por eso, tras aplicar el batch, se **mide el
residuo y se refina**, en bucle, hasta ~0. Ver [[feedback_residuo_mobiliario_loop]].

### 2-R.a — Medir el residuo (DOS detectores, uno independiente del config)

⚠ El verificador **no puede compartir léxico con lo que vigila** ([[feedback_control_independiente]]):
no basta con re-correr los patrones del config. Se usan dos medidas:

```bash
# (1) Detector conocido: cuenta el mobiliario tipo-bloque que sobrevivió (patrones ya validados)
python3 ~/.claude/skills/diaries-lib/lib/utils/limpiar_mobiliario.py --country {iso2} --medir
```

```python
# (2) Detector INDEPENDIENTE por frecuencia: líneas que RECURREN idénticas en muchas sesiones y NO
#     cierran frase = casi seguro mobiliario que ninguna regla vio. No usa los patrones del config.
import re, collections
from pathlib import Path
base=Path(f"source/{iso2}/corrected"); files=sorted(base.glob("*.txt")); N=len(files) or 1
norm=lambda s: re.sub(r"\d+","#", re.sub(r"\s+"," ", s.strip().upper()))
freq=collections.Counter(); ej={}
for p in files:
    seen=set()
    for l in p.read_text(errors="replace").split("\n"):
        t=l.strip()
        if 4<=len(t)<=70 and not t.endswith((".","?","!",":")):     # no cierra frase
            k=norm(t)
            if k not in seen: seen.add(k); freq[k]+=1; ej.setdefault(k,t)
resid=[(ej[k],c) for k,c in freq.most_common(60) if c>0.20*N]       # recurre en >20% de sesiones
for s,c in resid: print(f"{c:>6} ({c/N:.0%})  {s[:64]}")
print(f"\n{len(resid)} formas recurrentes candidatas a RESIDUO de mobiliario")
```

⚠ Un `0` limpio es SOSPECHOSO hasta explicarlo ([[feedback_flattened_text_detectors]]): si el corpus
está aplanado (CL/ES/GT sin saltos de línea), este detector no ve nada aunque haya mobiliario dentro.

### 2-R.b — Juzgar (supervisado) y refinar

El detector (2) PROPONE; **tú juzgas**. No todo lo recurrente es mobiliario: `Aplausos.`, `Muito bem!`,
las fórmulas de votación y los vocativos recurren y son legítimos. De la lista, separa lo que SÍ es
cabecero/folio/mastete/ID de página:

- Si hay residuo real → **re-DESCUBRE la variante que se escapó** (por década, por variante OCR:
  `GACETA`/`GACFTA`/`GAC ETA`…), añádela a `correct.furniture_*` del `country_config`, y **re-ejecuta el
  Paso 2** sobre las sesiones afectadas (`--force`). Vuelve a 2-R.a.
- Repite **descubrir → aplicar → verificar residuo → refinar** hasta que ambos detectores queden en ~0
  y una muestra aleatoria confirme que no queda mobiliario ni se ha tocado prosa/Prolegomena.

Registra cada variante nueva con `/diaries-decide` (evidencia: el conteo del residuo antes/después).
**No avances a `tag`/`meta` mientras el residuo no esté explicado.**

---

## Paso 2-quater — Deshifenización de SEGUNDA PASADA sobre `corrected/` completo

El paso 5 de la secuencia une el guion atado al reflujo, pero deja dos residuos: el **guion+salto**
en los países sin reflujo, y el **guion+ESPACIO** en la misma línea (~209 k solo en ES), que la
campaña del 10-ago no veía porque su patrón exigía el SALTO. Tras cerrar el bucle 2-R, pasa la
segunda pasada sobre el directorio entero:

```bash
# 1) medir, sin escribir:
python3 ~/.claude/skills/diaries-lib/lib/utils/deshifenizar.py --textdir source/{iso2}/corrected --medir
# 2) revisar las cifras (unidos vs compuesto conservado) y, si cuadran, aplicar:
python3 ~/.claude/skills/diaries-lib/lib/utils/deshifenizar.py --textdir source/{iso2}/corrected
```

`--textdir` construye el LÉXICO sobre todo el directorio — **del corpus del propio país**, no un
diccionario externo — y une las dos variantes. La variante espacio **exige evidencia positiva del
léxico** (la palabra unida debe existir y superar al compuesto con guion) y **conserva lo
ambiguo**: a mitad de línea un guion+espacio no es abrumadoramente un corte. Ver
[[pendiente_deshifenizacion_espacio]].

---

## Paso 3 — Resumen final

```
Resumen diaries-correct — {iso2}
─────────────────────────────────────────────
  AUTO  (complete): {N}
  FLAG  (revisar):  {N}
  HALT  (detenido): {N}
  SKIP  (ya hecho): {N}
  ERROR:            {N}
─────────────────────────────────────────────
  Total procesadas: {N}
  Hifenaciones corregidas (total): {N_total}
  Saltos ambiguos resueltos: {N_total}
```

Si hay casos FLAG o HALT:
```
Hay {N} sesiones que requieren revisión.
Ejecuta: /diaries-review --country {iso2}
```

Si todo es AUTO:
```
Siguientes pasos — SECUENCIA obligatoria, no en paralelo:
  /diaries-meta   --country {iso2} --all
  /diaries-dedupe --country {iso2}
  /diaries-tag    --country {iso2} --all
```
(`dedupe` va ANTES de `tag`: etiquetar sesiones duplicadas sesga el inventario estructural de
`diaries-tag` — cuenta dos veces las formas de marcador — y desperdicia la fase más cara.)
