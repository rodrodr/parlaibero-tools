---
name: diaries-feedback
description: "Inyecta correcciones y reglas en el estado del pipeline"
allowed-tools: [Read, Write, Edit, Bash]
---

Eres el skill `diaries-feedback` del pipeline ParlaIbero. Registras correcciones en el estado del pipeline para que queden trazadas y puedan propagarse a sesiones futuras. Hay tres tipos: puntuales, de regla y de estrategia.

## Argumentos esperados

`--country {iso2}` (obligatorio)
`--skill {nombre}` (obligatorio — skill afectado)
`--type {punctual|rule|strategy}` (obligatorio)
`--description {texto}` (obligatorio — descripción legible de la corrección)
`--pattern {regex}` (opcional — patrón que dispara la corrección)
`--action {texto}` (opcional — acción correctiva a tomar)
`--from {session_id|global}` (opcional — a partir de qué sesión aplica; default: global)

## Paso 1 — Leer estado

Lee `state/{iso2}/pipeline_state.json` con Read.

Si no existe: `ERROR: No existe state/{iso2}/pipeline_state.json.`

## Paso 2 — Validar argumentos

Verifica que `--type` es uno de: `punctual`, `rule`, `strategy`.
Verifica que `--skill` es un skill válido del pipeline.
Verifica que `--description` no está vacío.

Si `--type` es `punctual` o `rule` y no se pasó `--from`: solicita al usuario que especifique la sesión con `--from {session_id}`.

## Paso 3 — Construir CorrectionRecord

Construye el objeto de corrección:
```json
{
  "type": "{type}",
  "description": "{description}",
  "pattern": "{pattern_o_null}",
  "action": "{action_o_null}",
  "applied_from": "{from_o_global}",
  "skill": "{skill_name}",
  "timestamp": "{ISO_8601_actual}"
}
```

> Nota (2026-08-23): los campos `skill` y `applied_by` ya persisten en el estado —
> `CorrectionRecord` en `schemas.py` los declara desde esa fecha. En estados escritos antes,
> Pydantic los descartaba al reserializar: el campo puede faltar en registros antiguos.

La fecha ISO 8601 es la del sistema en el momento del registro: `{fecha ISO 8601 del sistema}` (p. ej. `date -u +%Y-%m-%dT%H:%M:%SZ`).

## Paso 4 — Aplicar según tipo

### Tipo `punctual`

Inserta el CorrectionRecord en el array `sessions.{session_id}.skills.{skill_name}.corrections[]` del JSON de estado.

Si la ruta `sessions.{session_id}.skills.{skill_name}.corrections` no existe, créala como array vacío y añade el registro.

Usa Edit para modificar `state/{iso2}/pipeline_state.json` directamente.

Sesiones afectadas: 1 (solo la sesión indicada en `--from`).

### Tipo `rule`

**4a.** Inserta el CorrectionRecord en `sessions.{session_id}.skills.{skill_name}.corrections[]` (sesión origen indicada en `--from`).

**4b.** Identifica todas las sesiones que fueron procesadas por ese skill DESPUÉS de la sesión indicada en `--from`. ⚠ Los `session_id` NO son fechas ni ordenan cronológicamente (`diario_198311291`, `boletin_ses_1991-05-21_72`): ordena por el campo `date` de `source/{iso2}/meta/{session_id}.json` y filtra los que están después. Fallback si una sesión no tiene meta todavía: deriva la fecha de un `YYYY-MM-DD` reconocible dentro del propio `session_id`; si tampoco lo hay, INCLÚYELA en el rango afectado y díselo al usuario — re-marcar de más cuesta una re-ejecución, dejar fuera una sesión afectada deja el error dentro.

**4c.** Para cada sesión posterior que tenga status `complete` para ese skill: cámbiala a status `pending` — esto fuerza re-ejecución.

**4d.** Usa Edit para aplicar todos los cambios al JSON de estado en una sola operación si es posible, o en operaciones sucesivas.

Sesiones afectadas: 1 + N posteriores re-marcadas como pending.

### Tipo `strategy`

**4a.** Inserta el CorrectionRecord en el array `global_rules[]` del JSON de estado (a nivel raíz del objeto). Si no existe, créalo.

**4b.** NO modifica el status de sesiones individuales.

Sesiones afectadas: todas las futuras (la regla se aplica en próximas ejecuciones).

Imprime instrucción al usuario:
```
Corrección de estrategia registrada.
Para aplicarla a todo el corpus, ejecuta:
  /diaries-{skill} --country {iso2} --all --force
```

## Paso 5 — Guardar y confirmar

Verifica que el JSON de estado es válido después de la edición:
```bash
python3 -c "import json; json.load(open('state/{iso2}/pipeline_state.json'))" && echo "JSON OK" || echo "JSON ERROR"
```

Si hay error de JSON: reporta el error y no confirmes el guardado. El usuario deberá editar manualmente.

Imprime confirmación:
```
Corrección registrada.
──────────────────────────────
Tipo:              {type}
Skill:             {skill_name}
Descripción:       {description}
Sesión origen:     {from}
Sesiones afectadas: {N}
Timestamp:         {timestamp}
──────────────────────────────
```

Si tipo es `rule` y hay sesiones re-marcadas como pending:
```
Sesiones re-marcadas como PENDING para re-ejecución:
  {session_1}, {session_2}, ...
Ejecuta /diaries-{skill} --country {iso2} --all para reprocesarlas.
```
