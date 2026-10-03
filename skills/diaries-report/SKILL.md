---
name: diaries-report
description: "Genera el informe completo del proceso de construcción del corpus"
allowed-tools: [Read, Write, Edit, Bash]
---

Eres el skill `diaries-report` del pipeline ParlaIbero. Generas `docs/{iso2}/pipeline_report.md` — un informe completo y detallado del proceso de construcción del corpus, incluyendo estadísticas de automatización, distribuciones de confianza e historial de correcciones.

> ⚠⚠ **Escribe `pipeline_report.md`, NUNCA `process_report.md`.** Son dos documentos distintos que
> durante meses compartieron nombre y se pisaron el uno al otro:
>
> | | quién lo genera | para quién |
> |---|---|---|
> | `process_report.md` | la cadena del depósito (`actualizar_deposito.sh` → `generar_docs_en.py`) | **público**: va al depósito, sellado con DOI y en tres lenguas |
> | `pipeline_report.md` | **este skill** | **interno**: automatización, confianza, correcciones, lo que queda abierto |
>
> La colisión no es hipotética y ocurrió en las dos direcciones: en AR, el informe del skill
> (julio) fue sobrescrito por la cadena del depósito (agosto), y un `--force` de este skill en
> septiembre habría borrado el informe público **con su DOI**. Decisión `ar-0029`.


## Argumentos esperados

`--country {iso2}` (obligatorio)
`--force` (sobreescribir si ya existe)

## Paso 1 — Leer fuentes de datos

Lee ambos archivos con Read:
- `state/{iso2}/pipeline_state.json`
- `country_config/{iso2}.yaml`

Si no existe el estado: `ERROR: No existe state/{iso2}/pipeline_state.json.`

Si `docs/{iso2}/pipeline_report.md` ya existe y no se pasó `--force`:
`ERROR: docs/{iso2}/pipeline_report.md ya existe. Usa --force para regenerar.`

## Paso 2 — Calcular estadísticas generales

Del JSON de estado, calcula:

**Sesiones:**
- `total_sesiones`: total de session_ids en `sessions` (excluyendo `_country`)
- `sesiones_sin_intervencion_humana`: sesiones donde todos los skills están `complete` **o
  `skipped`** y NO tienen ningún `CorrectionRecord` y la decisión no fue tomada por `diaries-review`

⚠⚠ **`skipped` cuenta como resuelto, no como pendiente.** Un paso omitido POR DISEÑO no es una
intervención humana: es el pipeline reconociendo que ese paso no aplica. Exigir `complete` a secas
destroza la métrica en cuanto un país omite algo. Medido en CL (2026-09-01): la definición estricta
daba **0,1 %** de automatización y la correcta **96,2 %**, y la diferencia entera la producían
4.416 sesiones sin OCR —el texto viene embebido— y 3.229 sin `tag` —el track XML llega etiquetado
de origen—. Publicar el 0,1 % habría descrito el corpus más automático del proyecto como el más
manual. Si se publican ambas, la estricta va SIEMPRE con la explicación de qué la produce.
- `tasa_automatizacion`: sesiones_sin_intervencion_humana / total_sesiones

**Por skill (todos los 13 del pipeline, `diaries-dedupe` incluido):**
- Conteo de sesiones en cada status: complete, flag, halt, pending
- `confianza_media`: promedio de los valores de confianza de sesiones `complete`
- `confianza_min` y `confianza_max`

⚠⚠ **La `tasa_automatizacion` NO se publica sola: dila SIEMPRE junto al recuento de decisiones
humanas que viven en los artefactos.** El estado solo recoge lo aplicado vía `/diaries-feedback`.
Medido en AR (2026-09-01): el estado daba **71,6%** de automatización con 295 `CorrectionRecord`,
mientras los artefactos guardaban **4.906 decisiones humanas congeladas** en `matching_table.frozen.csv`,
**473 formas marcadas `role`** (17.965 filas) y **29 decisiones metodológicas** en `decisions.jsonl`.
Publicar el 71,6% como «automatización» sería falso por un orden de magnitud. El informe debe
llevar esa comparación en su PRIMERA sección, no en una nota al pie.

⚠ **Un total de 0 `CorrectionRecord` NO significa que no hubiera intervención humana.** Si la
revisión se aplicó editando los artefactos (tabla de vinculación, roster) en vez de vía
`/diaries-feedback`, el estado no la recoge. Antes de escribir «automatización 100 %», compara la
`matching_table.csv` con su copia previa a la revisión y cuenta las filas `manual` / `NOT_SPEAKER` /
`role`: eso SÍ es intervención humana y debe figurar en el informe. En DO el estado decía 0
correcciones y en realidad hubo 160 decisiones humanas sobre oradores.

**Correcciones (de todos los CorrectionRecords del estado):**
- Total por tipo: punctual, rule, strategy
- Lista completa ordenada por timestamp

**Intervenciones humanas:**
- Decisiones tomadas desde `diaries-review` (busca `applied_by: "diaries-review"` en corrections)
- Agrupa por tipo: A (aceptado), C (corregido), E (escalado)

⚠ `applied_by` solo persiste desde el **2026-08-23** (`CorrectionRecord` en `schemas.py` lo
declara desde esa fecha; antes Pydantic lo destruía al reserializar). Para estados escritos
ANTES, el campo no existe: **un 0 histórico no significa cero intervención humana** — sigue
vigente la advertencia de arriba de contrastar con los artefactos (tabla de vinculación, roster).

## Paso 3 — Construir histogramas ASCII

Para cada skill que tenga sesiones con valores de confianza registrados, construye un histograma ASCII de 10 barras (rango 0.0 a 1.0):

```
diaries-tag — Distribución de confianza (45 sesiones)
[0.0-0.1] ░░░░░░░░░░░░░░░░░░░░ 0
[0.1-0.2] ░░░░░░░░░░░░░░░░░░░░ 0
...
[0.7-0.8] ██████░░░░░░░░░░░░░░ 8
[0.8-0.9] ████████████░░░░░░░░ 22
[0.9-1.0] ████████████████████ 15
```

Cada barra usa `█` para las unidades llenas, escala al máximo de la distribución. Usa 20 caracteres de ancho de barra.

## Paso 3-bis — Métrica de vinculación: SIEMPRE bruta y efectiva

La vinculación bruta (filas de habla con `id_dep`) NO es comparable entre países: su denominador
incluye a quien no puede tener escaño y lo que el acta no atribuye a nadie, y esa proporción depende
de cómo redacta cada cámara, no de la calidad del corpus. Publícalas siempre juntas.

La cifra del informe es la de la definición vigente **tr-0109**, la misma del bloque `linkage` de
`docs/{iso2}/corpus_info.json`. La calcula un script, nunca el modelo:

```bash
python3 ~/.claude/skills/diaries-lib/lib/utils/vinculacion_tr0109.py --country {iso2} --out docs/{iso2}/vinculacion_efectiva.json
```

`efectiva = vinculadas / (filas de habla − sin escaño − no atribuibles)`. «Sin escaño» no se
reclasifica: es `linkage.cannot_hold_seat_discounted` del corpus_info.json, que cada país calcula
con la convención de su tabla. «No atribuibles» son las voces colectivas y los anónimos. La
presidencia sin nombre (`PRESIDENTE` a secas) no se descuenta: quien preside es diputado, y no haber
recuperado su identidad es un hueco nuestro, no una exclusión estructural.

- Copia **literalmente** `paises.{ISO2}.texto_informe` del JSON en el Resumen ejecutivo. Ese texto
  ya dice la definición, las cifras y de dónde sale cada una: no redondees ni recalcules nada.
- Salida 1: la cifra recalculada no coincide con la publicada en corpus_info.json. El texto ya lo
  dice; llévalo también al diagnóstico de salud. Este skill no corrige corpus_info.json.
- Salida 2: no se pudo calcular (falta el CSV, una columna o el bloque `linkage`). Escribe
  «Vinculación efectiva: no disponible» con el mensaje de error y no uses un JSON anterior.
- Para comparar con la definición anterior, tr-0003 (`vinculacion_efectiva.py`), añade
  `--comparar tr-0003`. El bloque `comparacion` no es la cifra del informe: si lo citas, va aparte
  y con su identificador.

## Paso 4 — Evaluar salud del pipeline

Calcula la "salud" global:
- **Verde**: tasa_automatizacion >= 0.80 y no hay HALTs y confianza_media global >= 0.85
- **Amarillo**: tasa_automatizacion >= 0.60 y HALTs <= 5% de sesiones y confianza_media global >= 0.75
- **Rojo**: cualquier otra combinación

## Paso 4-bis — Decisiones metodológicas registradas

Antes de redactar nada, leer lo que `/diaries-decide` haya acumulado:

```bash
python3 ~/.claude/skills/diaries-lib/lib/utils/record_decision.py --pais {iso2} --listar
python3 ~/.claude/skills/diaries-lib/lib/utils/record_decision.py --pais transversal --listar
```

**No reconstruir el razonamiento de memoria ni inferirlo del código:** cada entrada ya trae
qué se decidió, qué alternativa se descartó, **con qué evidencia medida** y qué consecuencia
tuvo. El informe cita esas entradas por su `id`.

Las decisiones marcadas `superada` **se incluyen igualmente**, con el enlace a la que las
anuló. El historial de correcciones da credibilidad al corpus en vez de quitarla: demuestra
que las conclusiones se contrastaron.

El documento metodológico completo se regenera con
`python3 scripts/generar_metodologia.py` → `docs/_metodologia/generados/METODOLOGIA.md`.

## Paso 5 — Crear directorio y escribir informe

```bash
mkdir -p docs/{iso2}/
```

Escribe `docs/{iso2}/pipeline_report.md` con Write. El informe debe contener estas secciones en español:

---

```markdown
# Informe de proceso — {NOMBRE_PAIS} ({ISO2})

Generado: {fecha_actual}

## Resumen ejecutivo

| Campo | Valor |
|-------|-------|
| País | {nombre_pais} |
| Institución | {institucion} |
| Período | {fecha_inicio} — {fecha_fin} |
| Total sesiones | {total_sesiones} |
| Total intervenciones | {total_intervenciones} |
| Tasa de automatización | {tasa_automatizacion:.1%} |
| Salud del pipeline | {VERDE/AMARILLO/ROJO} |

{texto_informe de docs/{iso2}/vinculacion_efectiva.json, literal (Paso 3-bis)}

## Estado por skill

| Skill | Total | OK | FLAG | HALT | Pend | Conf.media |
|-------|-------|-----|------|------|------|-----------|
| diaries-bootstrap | ... | ... | ... | ... | ... | ... |
...

(una fila por skill: los 13 en orden canónico — bootstrap · ocr · extract · correct · meta ·
dedupe · tag · matrix · deputies · match · merge · standardize · document)

## Distribución de confianza

{histogramas ASCII por skill}

## Historial de correcciones

| Timestamp | Tipo | Skill | Sesión | Descripción |
|-----------|------|-------|--------|-------------|
| ... | ... | ... | ... | ... |

Total correcciones: {N_total}
  Puntuales:   {N_punctual}
  De regla:    {N_rule}
  De estrategia: {N_strategy}

## Intervenciones humanas

{tabla de decisiones tomadas desde diaries-review}

Sesiones con intervención humana: {N} ({porcentaje:.1%} del total)

## Decisiones metodológicas

{una línea por decisión registrada con /diaries-decide, citada por su `id` — qué se decidió
y su consecuencia; las marcadas `superada` se incluyen con el enlace a la que las anuló}

## Diagnóstico de salud del pipeline

**Estado global: {VERDE/AMARILLO/ROJO}**

{párrafo de evaluación breve: qué skills tienen mayor tasa de FLAG/HALT,
qué tipos de correcciones predominan, recomendaciones para mejorar
la automatización en el siguiente corpus}
```

---

## Paso 6 — Actualizar estado y confirmar

```bash
python ~/.claude/skills/diaries-lib/lib/utils/update_state.py \
  --country {iso2} --skill diaries-report --session "_country" \
  --status complete --confidence 1.0 \
  --output "docs/{iso2}/pipeline_report.md"
```

Imprime:
```
diaries-report — {iso2}
Informe generado en docs/{iso2}/pipeline_report.md
Salud del pipeline: {VERDE/AMARILLO/ROJO}
Tasa de automatización: {tasa:.1%}
Total correcciones registradas: {N}
```

> ⚠⚠ **Separador: SIEMPRE la coma, en los dieciséis** (directiva del investigador, 2026-09-01, `br-0019`). Antes se decía que ES y GT usaban `;`; se unificó por compatibilidad. ⚠ ES y GT tienen aún su canónico en `;` y pasarán a `,` al regenerarse en su reproceso, así que **al LEER conviene seguir detectando el separador**, aunque al ESCRIBIR sea siempre coma.
