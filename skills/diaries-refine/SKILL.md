---
name: diaries-refine
description: "Mejora un SKILL.md a partir de una observación de testing real. Edita directamente el skill en ~/.claude/skills/ y registra el cambio en REFINEMENTS.md."
allowed-tools: [Read, Write, Edit, Bash]
---

Este skill opera sobre los SKILL.md globales en `~/.claude/skills/`, no sobre datos de sesiones. Su propósito es cerrar el loop entre testing real → mejora del comportamiento del skill.

**Dos rutas de entrada:**

1. **Con argumento directo:**
   `/diaries-refine --skill diaries-tag --issue "descripción del problema"`

2. **Sin argumentos (modo interactivo):**
   El skill pregunta qué skill mejorar y cuál es la observación.

---

## Rutas

```
SKILLS_DIR = ~/.claude/skills                       # única fuente de los SKILL.md
BASE_DIR   = .    # solo para REFINEMENTS.md
```

Los SKILL.md viven SOLO en `~/.claude/skills/diaries-*/` (única fuente, versionada con
git ahí). **No hay copia en el repositorio** — se editan directamente en esa ruta.

---

## Paso 0 — Determinar skill y observación

Si se invocó con `--skill {name}` y `--issue "{texto}"`, usar esos valores.

Si no, preguntar:

```
¿Qué skill quieres mejorar?

  Pipeline:  bootstrap · ocr · extract · correct · meta · dedupe · tag · matrix
             deputies · match · merge · standardize · document
  Control:   status · review · feedback · report · decide · validate · teach · refine

→
```

Luego:
```
Describe la observación de testing (qué falló, qué fue confuso,
qué caso no estaba cubierto):

→
```

---

## Paso 1 — Localizar el SKILL.md

Todos los skills `diaries-*` viven en la misma ruta, sin distinción pipeline/control:

```
~/.claude/skills/diaries-{nombre}/SKILL.md
```

Lee el archivo completo.

---

## Paso 2 — Analizar la observación y proponer mejora

Con la observación del usuario y el SKILL.md actual, razona:

1. **¿En qué sección del SKILL.md está el problema?**
   - ¿Falta un caso en un paso de procesamiento?
   - ¿Es un umbral de confianza inadecuado?
   - ¿Hay una instrucción ambigua o incompleta?
   - ¿Falta un ejemplo concreto?
   - ¿Hay un edge case no documentado?

2. **¿Cuál es la mejora mínima que resuelve el problema?**
   Preferir cambios quirúrgicos: añadir un caso, clarificar una instrucción, añadir un ejemplo. No reescribir secciones enteras salvo que sea necesario.

3. **¿Afecta a otros skills?**
   Si la observación revela un problema transversal (p.ej. todos los skills ignoran un tipo de error), señalarlo.

Muestra al usuario:

```
OBSERVACIÓN:
  {issue}

SECCIÓN AFECTADA:
  {sección del SKILL.md}

CAMBIO PROPUESTO:
--- antes
{texto actual}
+++ después
{texto mejorado}

RAZONAMIENTO:
  {por qué este cambio resuelve el problema}
```

Pide confirmación: `[A]plicar / [E]ditar / [C]ancelar`

---

## Paso 3 — Aplicar el cambio

Si el usuario confirma ([A] o edita y confirma):

### 3a. Editar el SKILL.md

Usa la herramienta Edit para aplicar el cambio quirúrgico al archivo
`~/.claude/skills/diaries-{nombre}/SKILL.md`. El cambio queda activo de inmediato:
es la única copia y Claude Code la lee directamente.

### 3b. Registrar en REFINEMENTS.md

Append al archivo `REFINEMENTS.md`:

```markdown
## {YYYY-MM-DD} · diaries-{nombre}

**Observación:** {issue}

**Cambio aplicado:** {descripción concisa del cambio, 1–2 líneas}

**Sección modificada:** {nombre de la sección}

---
```

Si el archivo no existe, créalo con esta cabecera primero:

```markdown
# Refinements — diaries-* skills

Registro cronológico de mejoras a los SKILL.md derivadas de testing real.
Cada entrada incluye la observación que motivó el cambio y la modificación aplicada.

---

```

---

## Paso 4 — Confirmar y orientar al usuario

```
✓ diaries-{nombre} actualizado
  SKILL.md:    ~/.claude/skills/diaries-{nombre}/SKILL.md
  Registrado:  REFINEMENTS.md

El cambio está activo inmediatamente — Claude Code ya usa el skill actualizado.

¿Quieres re-ejecutar el skill sobre las sesiones afectadas?
  → /diaries-{nombre} --country {iso2} --all --force
  → O usa /diaries-status --country {iso2} para ver el estado actual.
```

---

## Comportamiento especial: observaciones sin skill específico

Si el usuario describe un problema pero no sabe qué skill lo causó, ayuda a diagnosticar:

1. Pregunta: ¿en qué etapa del pipeline apareció el problema? (OCR / texto / etiquetado / metadatos / vinculación)
2. Muestra el mapa de skills relevante para esa etapa
3. Lee el output del skill sospechoso (archivo en `source/{iso2}/`) si se especifica un país y sesión
4. Concluye qué skill necesita mejora y continúa con el flujo normal

---

## Notas

- Este skill NO modifica datos de sesiones ni `pipeline_state.json`. Solo modifica SKILL.md.
- Si la mejora requiere re-procesar sesiones, el usuario debe ejecutar el skill afectado con `--force` manualmente.
- Cambios estructurales grandes (rediseño de un skill completo) merecen una discusión antes de aplicarse — en ese caso, muestra el borrador completo antes de editar.
