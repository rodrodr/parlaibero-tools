---
name: diaries-dedupe
description: "Detecta y pone en cuarentena sesiones DUPLICADAS, en sus dos clases: (A) la misma sesión catalogada bajo >1 session_id, y (B) una sola sesión con las filas dobladas por ingesta multi-track. Se ejecuta DESPUÉS de diaries-meta y ANTES de diaries-tag: evita el doble conteo y que el inventario estructural del tagging se calibre sobre formas contadas dos veces."
---

# diaries-dedupe — Deduplicación de sesiones (nivel país)

Argumentos: `--country {iso2}` + opcionales `--write`, `--yes`.

**Cuándo se ejecuta:** una vez por país, **DESPUÉS de `diaries-meta` y ANTES de `diaries-tag`**.
Es un paso de resolución de entidades a nivel de SESIÓN (análogo a `diaries-match` para oradores).

⚠ **Antes de TAG, no antes de MATRIX** (corregido 2026-07-24). Su único insumo es el campo `date`
de `meta/`, y `diaries-meta` lee `extracted/` (la capa fiel): nada obliga a esperar al etiquetado. Y
hacerlo después tiene dos costes, uno de ellos de CORRECCIÓN:

1. **Sesga el inventario estructural de `diaries-tag` (Paso 0c)**, que rankea las formas de
   marcador por frecuencia sobre TODO el corpus para decidir cuáles importan. Con sesiones
   duplicadas dentro, sus formas se cuentan dos veces y el ranking sale distorsionado — el gate
   que debe detectar clases de marcador ausentes queda calibrado sobre datos inflados.
2. **Desperdicia la fase más cara y delicada** del pipeline etiquetando material que se va a
   descartar.

La secuencia correcta de la cadena de ingesta es:
`ocr → extract → correct → meta → dedupe → [deputies si hay pase de lista] → tag → matrix`.

## Por qué existe

Hay **dos clases** de duplicado, con detectores distintos. La segunda se descubrió tarde (CL,
2026-07-29) precisamente porque el detector de la primera es estructuralmente ciego a ella.

### Clase A — la misma sesión bajo >1 `session_id` (Paso 1)

Las fuentes traen **escaneos duplicados**: la misma sesión catalogada bajo dos o más `session_id`.
Dos patrones típicos (verificados en UY, 2026-06-17):
1. **Familias `_1`/`_2`/`_3` del mismo día** re-escaneadas (idéntico boletín).
2. **Nombre de archivo corrido ±N días** respecto a la fecha real (artefacto de catalogación/bootstrap),
   cuyo gemelo correctamente fechado ya existe.

Si no se eliminan, `diaries-matrix` **duplica las intervenciones** de esas sesiones en el corpus.

### Clase B — una sola sesión con las filas DOBLADAS (Paso 1-bis)

Aparece en países con **más de una vía de ingesta** (dual-track XML+PDF, o formatos que cambian por
época). La misma sesión entra por las dos vías y acaba con sus intervenciones repetidas **dentro de
un único `session_id`**. El Paso 1 no la ve: agrupa por fecha/`session_id` y aquí solo hay UNA
sesión, así que no hay nada que agrupar. Verificado en CL: 14 sesiones, ~1.200 intervenciones
repetidas, invisibles hasta que se midió el canónico.

⚠ **La señal fiable es el BOLETÍN + la FECHA REAL, no el contenido.** El número de boletín
("NÚMERO N" en el masthead) es el id único y monotónico del diario; la fecha real se verifica con el
**día de la semana** del masthead. El solapamiento de texto (Jaccard) da **falsos negativos** porque
dos escaneos de la misma sesión con distinta calidad OCR comparten pocas líneas exactas — por eso se
usa solo como respaldo cuando no hay identificador de sesión comparable.

**Regla:** duplicado = MISMO boletín **Y** MISMA fecha real. Mismo día con **boletines distintos** =
sesiones legítimas (mañana/tarde) → NO se tocan. Si el masthead no trae boletín legible, el
identificador secundario es **`session_number` + `session_type` de meta** (validados por
diaries-meta): identificadores distintos = sesiones legítimas del mismo día, **nunca** se agrupan
por Jaccard (comparten boilerplate: cabeceras, mesa, listas de asistencia → falsos positivos;
verificado en AR, 2026-07-06: 25ª/26ª/27ª REUNIÓN del mismo día, y asamblea vs ordinaria nº 1).

⚠ **Fecha de agrupación — NUNCA por prefijo del session_id.** La fecha se deriva en este orden:
1. `source/{iso2}/meta/{session_id}.json` campo `date` (ya validado por diaries-meta);
2. regex flexible sobre el session_id: ISO `YYYY-MM-DD` o compacta `YYYYMMDD` con validación real
   de mes/día (tolera sufijos pegados tipo `diario_YYYYMMDDn`);
3. si no hay fecha derivable → la sesión se **EXCLUYE** de la clusterización (sale en
   `excluded_no_date` + aviso por stderr).

Motivo: con ids no-ISO (AR: `diario_YYYYMMDD{n}`) el antiguo corte `sid[:10]` truncaba a
`diario_200` y produjo 23 clusters falsos con 87 sesiones legítimas como redundantes — habría
destruido el corpus con `--write`.

---

## Paso 0 — Configuración (opcional)

Lee `country_config/{iso2}.yaml`. Sección opcional `dedupe:` (si falta, se usan defaults razonables):

```yaml
dedupe:
  bulletin_regex: "\\bN[ÚU]MERO?\\s*0*(\\d{2,5})\\b"   # id del diario en el masthead
  masthead_weekday_regex: "..."                          # captura (díaSemana, día, mes, año)
  content_sim_threshold: 0.35                            # respaldo cuando no hay boletín
  max_redundant_per_cluster: 5                           # guard: cluster mayor → review, no plan
```

Los defaults del script sirven para diarios tipo "CIUDAD, <día> <dd> DE <mes> DE <yyyy>" + "NÚMERO N".
Ajusta los regex si la cabecera del país difiere (revisa 2-3 mastheads reales antes).

---

## Paso 1 — Detección (dry-run)

```bash
python ~/.claude/skills/diaries-lib/lib/utils/detect_duplicates.py --country {iso2}
```

Devuelve JSON por stdout:
- `duplicate_clusters`, `redundant_sessions`
- `plan`: lista de `{date, keeper, bulletin, redundant:[...]}` — el **keeper** es la sesión
  correctamente fechada y más completa; las `redundant` se eliminarían.
- `review_shared_bulletin_distinct`: pares que comparten boletín pero cuya fecha real DIFIERE y el
  contenido NO es similar → casi siempre **boletín mal leído por OCR** = sesiones DISTINTAS. **NO se
  cuarentenan**; se listan para revisión manual.
- `review_guard_clusters`: clusters degradados por el guard de seguridad (más de
  `max_redundant_per_cluster` redundantes, o miembros con fechas de meta DISTINTAS). **NO se
  cuarentenan** aunque se pase `--write`; revísalos manualmente — un cluster grande o con fechas
  mezcladas casi siempre delata un fallo de derivación de fecha, no duplicados reales.
- `excluded_no_date`: sesiones sin fecha derivable (ni meta ni session_id), excluidas de la
  clusterización. Si hay muchas, ejecuta antes `/diaries-meta` para ese país.

Si `duplicate_clusters == 0`: informa "corpus sin duplicados" y termina (revisa igualmente los
`review_*` si los hay).

---

## Paso 1-bis — Duplicación DENTRO de una sesión (ingesta multi-track)

**Cuándo aplicar:** solo si el país tiene **más de una vía de ingesta** (dual-track, o formatos que
cambian por época). Lo dice `country_config/{iso2}.yaml` / el `onboarding_report`. Si la ingesta es
de una sola vía, salta este paso.

**Detección, según el momento:**

- *Antes de tag* (lo normal): comprueba si dos archivos fuente de **tracks distintos** resuelven al
  mismo `(date, session_number)` de `meta/`. Esos son los candidatos.
- *Con el corpus ya construido*: agrupa el canónico por `(date, session_number)` y mira si las filas
  de una misma sesión provienen de más de un track. Requiere que la procedencia esté registrada
  (en CL, la columna `source`). **Si el corpus no guarda la procedencia, esta clase es indetectable
  a posteriori** — razón de más para comprobarlo antes de tag.

**Detector preferente — DESPLAZAMIENTO CONSTANTE (añadido 2026-07-30).** Antes de nada, comprueba si
los pares de filas con el mismo texto dentro de una sesión están separados por un **desplazamiento
constante** de `intervention_order`. Es la firma inequívoca de una ingesta doble: la sesión se copió
como bloque contiguo, así que la fila 14 se repite en la 540, la 370 en la 896 y la 448 en la 974 —
**todas a 526 de distancia** (caso real, CO `2007-05-02|37`). Ventajas sobre el criterio de
multiplicidad: no necesita umbrales, y **distingue por construcción** el duplicado de la fórmula de
trámite, porque una fórmula repetida a lo largo del debate NO produce un desplazamiento regular.

Si hay desplazamiento constante en la mayoría de los pares, la sesión está doblada y el propio
desplazamiento indica dónde empieza la copia. Si no lo hay, cae al criterio de multiplicidad de
abajo, que es más laxo y necesita los umbrales.

**Verificación por sesión:** normaliza el texto (sin tildes, minúsculas, sin puntuación, prefijo de
150 caracteres), ignora los textos de menos de 25 caracteres (asentimientos: "Gracias.", "Sí.", que
se repiten de forma legítima) y mide el solapamiento sobre el **lado menor**:

| Solapamiento | Veredicto | Acción |
|---|---|---|
| ≥ 70% | duplicada | deduplicar fila a fila |
| 25–70% | parcial | deduplicar fila a fila (solo desaparece lo repetido) |
| < 25% | **complementaria, NO es duplicado** | no tocar |

⚠ **NUNCA descartes una de las dos copias entera.** Es la trampa de este caso, y las tres razones
están medidas en CL (2026-07-29), no supuestas:

1. **Ninguna copia contiene a la otra.** En `1994-04-12|11` había 55 textos solo en el track xml y
   51 solo en el tradicional: descartar cualquiera de las dos pierde contenido real.
2. **La copia "peor" era la mejor.** La documentación daba el track tradicional (PDF/OCR) por
   inferior al XML estructurado. Medido sobre las 12 sesiones duplicadas: tradicional tenía **85,3%
   de `id_dep` frente a 83,8%**, texto mediano de 225 caracteres frente a 195, y **0 `speaker_raw`
   vacíos frente a 20**. Elegir la copia por reputación del track habría degradado el corpus.
3. **Una de las 14 no era un duplicado.** `1999-05-12|63` compartía **1 texto de 57**: eran tramos
   complementarios de la misma sesión, cada track con una parte. Un veredicto por sesión la habría
   mutilado; la deduplicación fila a fila le quitó exactamente 1 fila.

**Deduplicación fila a fila.** Dentro de cada sesión, cuando un mismo texto normalizado aparece en
**ambos** tracks se conserva una sola fila. Criterio de cuál, en orden: (1) la que tiene `id_dep`,
(2) la de texto más largo, (3) la del track con mejor calidad **medida en ese país** (no la
reputada). Así solo desaparece lo que está repetido y el remanente complementario se conserva.

**Después de deduplicar:** si el corpus ya tenía `intervention_order`, **renumerarlo** en las
sesiones tocadas — al quitar filas queda con huecos. Verifica que vuelve a ser 1-based y continuo.

⚠ **Este paso SIEMPRE informa y pide confirmación explícita, incluso con `--write` o `--yes`.**
A diferencia de la Clase A, aquí no hay un identificador duro que respalde la decisión: el boletín
es el mismo porque la sesión es la misma. Todo el peso recae en la similitud de texto, que es un
juicio. Muestra al usuario la tabla por sesión (filas de cada track, solapamiento, veredicto) y el
recuento de filas a retirar antes de tocar nada, y **señala expresamente las sesiones por debajo
del 25%** como "no son duplicados, se conservan".

Cuarentena reversible: las filas retiradas van a un CSV aparte con su procedencia —
`source/{iso2}/standardize/{ISO2}_quarantine_intrasesion_dups.csv`, junto al canónico (después se
comprime a `.csv.gz`; así vive en SV) —, más copia del canónico previo
(`{ISO2}_interventions.pre_dedupeB.csv`). Nunca se borran.

Implementación de referencia (lib — generaliza el one-off de CL):
`~/.claude/skills/diaries-lib/lib/utils/check_intrasession_dups.py` (detector: texto ≥80 car.
repetido dentro del mismo `(date, session_number)`, sin necesitar columna de procedencia) y
`~/.claude/skills/diaries-lib/lib/utils/dedupe_intrasession.py` (deduplicación fila a fila;
simula por defecto, escribe con `--apply`).

---

## Paso 2 — Revisar el plan

Muestra al usuario un resumen: nº de clusters, total a cuarentena, y la tabla `keeper ← [redundant]`.
Señala los `review_shared_bulletin_distinct` como "posibles boletines mal leídos (revisar)", los
`review_guard_clusters` como "clusters sospechosos degradados por el guard (revisar antes de tocar)"
y los `excluded_no_date` como "sin fecha derivable (corregir meta primero)".

### ⚠⚠ El plan del detector NO se aplica tal cual. Dos defectos medidos (2026-08-29)

**1 · El «boletín» por defecto NO es un identificador único.** Donde el país no tiene un número de
diario propio, el regex acaba capturando el **número de acta, que se repite cada legislatura**, y
la agrupación cae a similitud de contenido. En PE eso propuso **borrar el 17 % del corpus**: 525
clusters y 526 «redundantes», de los que **506 se diferenciaban de su keeper solo en la letra de
TOMO**. Comprobado que no eran duplicados sino TURNOS: `PLO-1997-10A` abre «a las 09 horas y 22
minutos» y `10B` «a las 17 horas y 29 minutos»; `36.ª E SESIÓN (Matinal)` frente a
`36.ª F SESIÓN (Vespertina)`; Jaccard de vocabulario 0,21-0,25 y tamaños que difieren 4×.

**Antes de mirar el plan, mira los grupos de `review_shared_bulletin_distinct`.** Si mezclan años
distintos, el boletín no es único y el país necesita su propio `dedupe.bulletin_regex` — en PE, el
número de sesión CON su letra de tomo. En CO los 300 grupos separaban una mediana de **19 años**.
Y comprueba siempre lo que de verdad define un duplicado: que dos sesiones compartan boletín **Y
fecha**. Si ninguna lo hace, no hay duplicados por mucho cluster que salga.

**2 · El keeper que propone puede ser el equivocado.** En PA acertaba en 7 de 16: proponía
conservar `d_1999-06-18_A_PLENO` cuando el dictamen de fechas establece que esa acta es del
**1998**-06-18 y ya existe `d_1998-06-18_A_PLENO` — conservar el mal nombrado deja un id de
catálogo falso. **Manda el criterio de `co-0010`: gana el `session_id` que casa la fecha y el
número que declara el ACTA, no el que el detector ponga primero.**

⚠ Y un hallazgo que conviene esperar: **el arbitraje de fechas destapa duplicados**. En PA, 5 de
los 15 pares reales aparecieron solo al re-fechar el acta — hasta entonces las dos copias parecían
sesiones de días distintos. Si el país tiene dictamen (`tr-0090`), corre `dedupe` DESPUÉS de
aplicarlo.

Si NO se pasó `--write` ni `--yes`: **detente aquí** y pide confirmación
(`[A]plicar cuarentena / [C]ancelar`). El paso es destructivo (aunque reversible).

---

## Paso 3 — Cuarentena (reversible)

Con confirmación (o `--write`):

```bash
python ~/.claude/skills/diaries-lib/lib/utils/detect_duplicates.py --country {iso2} --write
```

Esto, por cada `redundant`:
- Mueve sus archivos (`corrected/ tagged/ extracted/ meta/ ocr/ raw/`) a
  `source/{iso2}/_quarantine_duplicates/` (mismo árbol) → **reversible** (mover de vuelta restaura).
- Marca `diaries-dedupe = skipped` en el estado, con `error` = "Duplicado de {keeper} (boletín N)".
- Escribe/fusiona `source/{iso2}/_quarantine_duplicates/manifest.json` (`redundant → keeper`).
- Marca cada `keeper` como `diaries-dedupe = complete` y fija su `date` a la fecha real.

El script es **idempotente**: re-ejecutarlo no duplica entradas del manifiesto ni vuelve a mover nada.

---

## Paso 4 — Resumen

```
Resumen diaries-dedupe — {iso2}
─────────────────────────────────────────────
  Clase A · misma sesión bajo >1 session_id
  Clusters de duplicados:      {N}
  Sesiones a cuarentena:       {N}   → source/{iso2}/_quarantine_duplicates/
  Pares a revisar (boletín ?): {N}   (posibles OCR mal leídos = sesiones distintas)

  Clase B · filas dobladas dentro de una sesión (solo ingesta multi-track)
  Sesiones con doble track:    {N}
  De ellas, duplicadas:        {N}   ({N} complementarias, NO se tocan)
  Filas retiradas:             {N}   → standardize/{ISO2}_quarantine_intrasesion_dups.csv

  Corpus activo: {antes} → {después} sesiones
─────────────────────────────────────────────
Reversible: mover de vuelta desde _quarantine_duplicates/ restaura cualquier caso.
Manifiesto: source/{iso2}/_quarantine_duplicates/manifest.json
```

Si hay `review_shared_bulletin_distinct`, recuérdalo: requieren una mirada manual (normalmente son
sesiones distintas con el boletín OCR-mal-leído; confírmalo comparando sus mastheads).

**Siguiente:** `/diaries-tag --country {iso2} --all` (ya sobre el corpus sin duplicados, de modo
que el inventario estructural del Paso 0c se calibre sin formas contadas dos veces).
