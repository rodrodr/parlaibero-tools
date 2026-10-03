---
name: diaries-status
description: "Muestra el estado actual del pipeline para un país"
allowed-tools: [Read, Write, Edit, Bash]
---

Eres el skill `diaries-status` del pipeline ParlaIbero. Lees el estado del pipeline y presentas una tabla ASCII clara con el progreso de todos los skills. Comando de control de solo lectura — no modifica ningún archivo.

## Argumentos esperados

`--country {iso2}` (obligatorio)

## Paso 1 — Leer estado

Lee el archivo de estado con Read:
`state/{iso2}/pipeline_state.json`

Si no existe: `ERROR: No existe state/{iso2}/pipeline_state.json. ¿Ejecutaste /diaries-bootstrap --country {iso2}?`

## Paso 2 — Calcular estadísticas por skill

El orden canónico del pipeline es (13 skills — de esta lista deriva el «siguiente skill pendiente» del Paso 5):
1. diaries-bootstrap
2. diaries-ocr
3. diaries-extract
4. diaries-correct
5. diaries-meta
6. diaries-dedupe
7. diaries-tag
8. diaries-matrix
9. diaries-deputies
10. diaries-match
11. diaries-merge
12. diaries-standardize
13. diaries-document

Para cada skill:

**Skills por sesión** (bootstrap, ocr, extract, correct, meta, tag, matrix): cuenta las sesiones en cada status: `complete`, `flag`, `halt`, `pending`, `running`, `skipped`. Una sesión es `pending` si aparece en `sessions` pero no tiene entry para ese skill. Una sesión en `running` es una ejecución colgada (interrumpida sin cerrar): cuéntala en la columna `Pend` y lístala aparte en el Paso 4. Calcula también el total de sesiones y la confianza media (de las sesiones complete).

**Skills a nivel país** (deputies, match, merge, standardize, document): busca la entrada `_country` en sessions. Su estado es único (no por sesiones). Muestra como "1/0" en las columnas respectivas.

⚠ **`diaries-dedupe` se cuenta POR SESIÓN** aunque se ejecute a nivel país: `detect_duplicates.py` marca `complete`/`skipped` en cada sesión afectada (así lo fija su Paso 3), no en `_country`.

## Paso 3 — Imprimir tabla ASCII

```
══════════════════════════════════════════════════════════════════════
ParlaIbero — Estado del pipeline: {ISO2}
Fecha: {fecha_actual}
══════════════════════════════════════════════════════════════════════
Skill                   Total    OK   FLAG  HALT  Pend  Conf.media
──────────────────────────────────────────────────────────────────────
diaries-bootstrap           1     1     0     0     0     1.00
diaries-ocr                45    40     3     2     0     0.92
diaries-extract            45    38     4     3     0     0.88
diaries-correct            45    35     5     5     0     0.91
diaries-meta               45    28     2    15     0     0.95
diaries-dedupe              1     1     0     0     0     0.93
diaries-tag                45    30     8     7     0     0.84
diaries-matrix             45    25     3    17     0     0.89
diaries-deputies            1     1     0     0     0     0.94
diaries-match               1     0     1     0     0     0.82
diaries-merge               1     0     0     0     1      —
diaries-standardize         1     0     0     0     1      —
diaries-document            1     0     0     0     1      —
══════════════════════════════════════════════════════════════════════
```

## Paso 4 — Mostrar sesiones problemáticas

Si hay sesiones con status `flag`, lista:
```
Sesiones con FLAG pendiente:
  diaries-tag:    1931-07-14, 1931-08-03
  diaries-match:  _country
```

Si hay sesiones con status `halt`, lista:
```
Sesiones con HALT (requieren intervención manual):
  diaries-meta:   1931-06-02, 1931-06-14, 1931-07-01
  diaries-tag:    1931-08-15
```

Si hay sesiones con status `running`, lista:
```
Sesiones en RUNNING (ejecución interrumpida — re-ejecutar el skill):
  diaries-ocr:    1931-09-10
```

## Paso 5 — Mensajes de acción

Si hay HALTs:
```
⚠ Hay {N} sesiones HALT. Revisa los errores y ejecuta el skill con --force tras corregir.
```

Si hay FLAGs:
```
Ejecuta /diaries-review --country {iso2} para revisar los {N} casos pendientes.
```

Si todo está complete (todos los skills en verde):
```
Pipeline completo para {iso2}. Corpus listo.
Siguiente paso: /diaries-report --country {iso2}
```

Si hay skills pendientes sin errores (solo pending):
```
Progreso: {n_complete_skills}/{total_skills} skills completados.
Siguiente skill pendiente: /diaries-{siguiente_skill} --country {iso2} --all
```
