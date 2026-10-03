---
name: diaries-review
description: "Revisión interactiva de casos FLAG y HALT en el pipeline"
allowed-tools: [Read, Write, Edit, Bash]
---

Eres el skill `diaries-review` del pipeline ParlaIbero. Presentas al usuario los casos FLAG del pipeline para que tome decisiones —aceptar, corregir, escalar o saltar— y LISTAS los HALT con su error para marcarlos resueltos tras la intervención manual. Es un bucle interactivo de revisión.

## Argumentos esperados

`--country {iso2}` (obligatorio)
`--skill {nombre}` (opcional — filtrar a un skill concreto)

## Paso 1 — Leer estado

Lee `state/{iso2}/pipeline_state.json` con Read.

Si no existe: `ERROR: No existe state/{iso2}/pipeline_state.json.`

## Paso 2 — Recopilar casos FLAG

Recorre el JSON de estado. Recopila todos los casos con status `flag` en la estructura:
```
{
  "diaries-tag": ["1931-07-14", "1931-08-03"],
  "diaries-match": ["_country"],
  ...
}
```

Si se pasó `--skill {nombre}`: filtra para incluir solo ese skill.

Si no hay casos FLAG ni HALT: imprime "No hay casos FLAG ni HALT pendientes. Pipeline al día." y termina. Si solo hay HALT, pasa directamente al Paso 2-bis.

Cuenta el total: "Casos FLAG a revisar: {N}"

## Paso 2-bis — Listar y resolver casos HALT

El flujo «Retomar pipeline interrumpido» promete resolver FLAGs **y HALTs**; este skill debe
mostrar ambos. Recopila también los casos con status `halt` y lístalos con su `error_message`:

```
Casos HALT (requieren intervención manual):
  diaries-meta / 1931-06-02 — "3 páginas sin fecha legible"
  diaries-tag  / 1931-08-15 — "0 marcadores detectados"
```

Un HALT no entra al bucle del Paso 3: la intervención la hace el usuario fuera del skill. Tras
listar, pregunta por cada uno si la intervención manual ya se realizó:

- **Sí, resuelto** → registra un CorrectionRecord `punctual` describiendo la intervención (como
  en la opción [C]) y marca el nuevo status:
  ```bash
  python ~/.claude/skills/diaries-lib/lib/utils/update_state.py \
    --country {iso2} --skill {skill_name} --session {session_id} \
    --status complete --confidence {confianza}
  ```
  (o `--status flag` si el usuario prefiere que pase por el bucle de revisión.)
- **No** → se mantiene en `halt`; seguirá apareciendo aquí y en `/diaries-status`.

## Paso 3 — Bucle de revisión

Para cada caso FLAG, en orden del pipeline (bootstrap → ocr → extract → correct → meta → dedupe → tag → matrix → deputies → match → merge → standardize → document):

**3a. Mostrar cabecera del caso**

```
─────────────────────────────────────────────────────────────────────
Caso {i}/{N}
Sesión:  {session_id}
Skill:   {skill_name}
Conf.:   {confidence:.2f}
Archivo: {output_path}
─────────────────────────────────────────────────────────────────────
```

**3b. Mostrar fragmento del archivo**

Si el archivo indicado en `output_path` existe:
- Para skills de texto (tag, correct, extract): lee y muestra las primeras 30 líneas con Read.
- Para skills CSV (matrix, merge, standardize): lee y muestra las primeras 10 filas con Read.
- Para skills de matching (match, deputies): muestra solo los registros con `confidence < 0.90` o `match_method = "unmatched"` (máx. 20 filas).
- Para otros archivos: muestra las primeras 20 líneas.

Si el archivo no existe: "Archivo de salida no encontrado en {output_path}"

**3c. Preguntar al usuario**

Muestra el menú de opciones y espera la respuesta:
```
¿Qué hacer con este caso?
  [A] Aceptar resultado — marcar como COMPLETE
  [C] Corregir — describir la corrección puntual
  [R] Reintentar con MiniMax M3 — re-OCR páginas de baja confianza    ← solo diaries-ocr
  [E] Escalar — marcar como HALT (requiere intervención manual posterior)
  [S] Saltar — revisar más tarde (mantener FLAG)
  [Q] Salir de la revisión

Opción:
```

(La opción [R] solo se muestra cuando el skill del caso es `diaries-ocr`.)

**3d. Procesar respuesta**

**[A] Aceptar:**
```bash
python ~/.claude/skills/diaries-lib/lib/utils/update_state.py \
  --country {iso2} --skill {skill_name} --session {session_id} \
  --status complete --confidence {confidence_actual}
```
Confirma: "Marcado como COMPLETE."

**[C] Corregir:**
Pide al usuario: "Describe la corrección (qué cambiar y por qué):"
Espera su descripción. Luego:
- Construye un `CorrectionRecord`:
  ```json
  {
    "type": "punctual",
    "description": "{descripción del usuario}",
    "timestamp": "{ISO 8601 actual}",
    "applied_by": "diaries-review"
  }
  ```
  (Desde el **2026-08-23** `applied_by` persiste: `CorrectionRecord` en `schemas.py` lo declara
  y sobrevive el round-trip. Antes de esa fecha Pydantic lo destruía al reserializar — en
  estados antiguos el campo puede faltar.)
- Edita `state/{iso2}/pipeline_state.json` directamente con Edit: añade el registro al array `sessions.{session_id}.skills.{skill_name}.corrections` (créalo si no existe).
- Ejecuta update_state.py con `--status complete`.
- Confirma: "Corrección registrada y marcado como COMPLETE."

**[R] Reintentar con MiniMax M3** *(solo disponible para `diaries-ocr`)*:

Re-procesa las páginas de baja confianza de la sesión usando MiniMax M3 como fallback. Las
páginas ya escritas con confianza ≥ 0.70 se saltean (checkpointing); solo se re-OCR-ean las
de baja confianza, consumiendo el mínimo de llamadas del plan MiniMax.

```bash
python ~/.claude/skills/diaries-lib/lib/utils/ocr_pages.py \
  --input "source/{iso2}/raw/{session_id}.pdf" \
  --output-dir "source/{iso2}/ocr/{session_id}/" \
  --dpi {ocr.dpi} --model "{ocr.primary_model}" --minimax-threshold 0.70
```

Lee el JSON, recalcula `mean_confidence`, determina el nuevo status (complete/flag/halt) con los
umbrales del país, registra una corrección puntual ("Re-OCR con MiniMax M3: conf {antes}→{nueva}")
y actualiza el estado. Confirma: "Re-OCR completado. Confianza: {antes}→{nueva}. Status: {status}."

**[E] Escalar:**
```bash
python ~/.claude/skills/diaries-lib/lib/utils/update_state.py \
  --country {iso2} --skill {skill_name} --session {session_id} \
  --status halt
```
Confirma: "Escalado a HALT. Requiere revisión manual."

**[S] Saltar:**
No modifica nada. Confirma: "Saltado — se mantiene como FLAG."

**[Q] Salir:**
Rompe el bucle inmediatamente.

## Paso 4 — Resumen final

Al terminar el bucle, imprime:
```
─────────────────────────────────────────────────────────────────────
Revisión completada
  Aceptados:   {n_aceptados}
  Corregidos:  {n_corregidos}
  Escalados:   {n_escalados}
  Saltados:    {n_saltados}
  Pendientes:  {n_flag_restantes}
─────────────────────────────────────────────────────────────────────
```

Si aún quedan FLAGS: "Quedan {n} casos FLAG. Ejecuta /diaries-review --country {iso2} cuando quieras continuar."
Si no quedan FLAGS: "Todos los casos FLAG resueltos. Ejecuta /diaries-status --country {iso2} para ver el estado."


---

## Registrar también lo verificado-y-correcto ⚠

No basta con anotar las correcciones: **un caso revisado y confirmado es tan informativo como
uno corregido**, y si no se registra, la siguiente pasada lo vuelve a marcar. Ocurrió: la
validación técnica re-marcó 128 atribuciones que el investigador ya había resuelto en la fase
de match, porque aquella revisión no dejó rastro.

Si de la revisión sale un **criterio** —no una corrección puntual, sino una regla sobre cómo
decidir— registrarlo con `/diaries-decide`, que exige declarar la evidencia.
