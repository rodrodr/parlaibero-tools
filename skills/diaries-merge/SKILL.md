---
name: diaries-merge
description: "Join de intervenciones con matching y diputados para producir CSV enriquecido"
allowed-tools: [Read, Write, Edit, Bash]
---

Eres el skill `diaries-merge` del pipeline ParlaIbero. Ejecutas el join entre `interventions_raw.csv`, `matching_table.csv` y `deputies.csv` para producir `interventions_enriched.csv`. Proceso puro pandas, sin juicio LLM. Este skill opera a nivel PAÍS.

## Argumentos esperados

`--country {iso2}` (obligatorio)
`--force` (sobrescribir interventions_enriched.csv si ya existe)

## Paso 1 — Verificar prerequisitos

Verifica que existen los tres archivos requeridos:
```bash
test -f source/{iso2}/matrix/interventions_raw.csv && echo "OK" || echo "MISSING"
test -f source/{iso2}/match/matching_table.csv && echo "OK" || echo "MISSING"
test -f source/{iso2}/deputies/deputies.csv && echo "OK" || echo "MISSING"
```

Si falta `interventions_raw.csv`: `ERROR: Ejecuta primero /diaries-matrix --country {iso2}`
Si falta `matching_table.csv`: `ERROR: Ejecuta primero /diaries-match --country {iso2}`
Si falta `deputies.csv`: `ERROR: Ejecuta primero /diaries-deputies --country {iso2}`

Si `merge/interventions_enriched.csv` ya existe y no se pasó `--force`:
`ERROR: source/{iso2}/merge/interventions_enriched.csv ya existe. Usa --force para regenerar.`

**1b. El padrón tiene que ser DEL PAÍS (comprobación de un segundo, error real).**
`source/pe/deputies/deputies.csv` resultó ser el padrón de **PARAGUAY** (ids `PY…`, partidos
paraguayos) traspapelado en la carpeta de Perú. Un join contra el archivo equivocado no falla:
produce cero coincidencias y parece un problema de emparejamiento.

```bash
python3 -c "
import csv
p='source/{iso2}/deputies/deputies.csv'
ids=[r['id_dep'] for r in csv.DictReader(open(p)) if r.get('id_dep')][:200]
pre={i[:2] for i in ids}
print('prefijos:',pre,'| esperado: {ISO2}','→','OK' if pre=={'{ISO2}'} else '⚠ REVISAR')"
```

Comprueba además que el padrón que usa el merge es el que alimentó al match: si el país llegó
pre-estructurado puede haber varios (en PE el bueno es `pe_diputado.csv`, no `deputies.csv`).

## Paso 1-ter — Al REEJECUTAR sobre un corpus ya cerrado

Un merge rehecho parte de `matching_table` + `deputies` y **pierde todo lo que se aplicó después**:
sobre todo las atribuciones de roles de mesa del Paso 3-bis, que viven solo en el enriched. Antes de
regenerar, mide el punto de partida para poder comparar:

```bash
python3 -c "
import csv,sys,os; csv.field_size_limit(sys.maxsize)
from collections import Counter
p='source/{iso2}/merge/interventions_enriched.csv'
if os.path.exists(p):
    c=Counter(); n=0
    for r in csv.DictReader(open(p)):
        n+=1; c[r.get('match_method','')]+=1
    print(f'{n:,} filas · métodos: {dict(c.most_common(8))}')
    if c.get('president_meta'): print(f\"⚠ {c['president_meta']:,} filas atribuidas POST-MERGE: reaplica el Paso 3-bis tras regenerar\")"
```

**Regla:** si el recuento de filas con `id_dep` baja respecto al enriched anterior, la regeneración
ha perdido trabajo. No sigas al standardize hasta recuperarlo.

## Paso 2 — Ejecutar merge

```bash
mkdir -p source/{iso2}/merge/
python ~/.claude/skills/diaries-lib/lib/utils/merge_tables.py \
  --interventions "source/{iso2}/matrix/interventions_raw.csv" \
  --matching "source/{iso2}/match/matching_table.csv" \
  --deputies "source/{iso2}/deputies/deputies.csv" \
  --output "source/{iso2}/merge/interventions_enriched.csv" \
  --separator ";" \
  $([ -f "source/{iso2}/match/matching_overrides.csv" ] && echo "--overrides source/{iso2}/match/matching_overrides.csv")
```

⚠⚠ **El padrón está en formato LARGO: `id_dep` NO es único.** Hay una fila por
`(id_dep, legislatura)` — ver `diaries-deputies`, Paso 4-bis. Un join por `id_dep` **solo**
multiplica las filas de la matriz por el número de legislaturas que sirvió cada diputado, y no
falla: devuelve un enriched más grande que la matriz, con las intervenciones duplicadas tantas
veces como períodos. **Une por `id_dep` + `legislatura`.**

Comprobación obligatoria justo después del merge — es de una línea y ahorra un corpus inflado:

```python
assert len(enriched) == len(interventions), \
    f"el merge cambió el nº de filas: {len(interventions):,} → {len(enriched):,}"
```

Si la matriz no trae `legislatura` fiable, une por `id_dep` **contra el padrón deduplicado por
persona** (una fila por `id_dep`, quedándose con el período que cubra la fecha de la sesión) —
nunca contra el padrón largo entero.

Si existe `match/matching_overrides.csv` (lo genera el Paso 4c de `diaries-match`
con la restricción por lista de asistencia), pásalo con `--overrides`: aplica la
resolución **por-sesión** (mismo apellido → persona distinta según la fecha)
sustituyendo `id_dep` ANTES del join con deputies, de modo que `nombre_completo`,
`partido` y `district` salgan del diputado correcto. El JSON de salida añade
`overrides_applied` (nº de intervenciones reasignadas) — repórtalo.

El script escribe JSON a stdout con la estructura:
```json
{
  "rows_input": 1234,
  "rows_output": 1234,
  "match_rate": 0.95,
  "unmatched_rows": 62,
  "columns_added": ["id_dep", "nombre_completo", "nombre", "apellidos", ...]
}
```

Lee ese JSON y extrae los valores.

**Nota — `sex` viaja, no se calcula.** El enriched ARRASTRA `sex` del padrón vía join, como una
columna más; `merge` no lo deriva ni lo recalcula. (La lección del enforcer de esquema que
borraba la columna vive en `diaries-standardize`.)

## Paso 3 — Verificar integridad de salida

**3a.** Verifica que el archivo de salida existe:
```bash
test -f source/{iso2}/merge/interventions_enriched.csv && echo "OK" || echo "MISSING"
```

**3b.** Verifica que el número de filas de salida coincide con el de entrada:
```bash
python3 -c "
import pandas as pd
df_raw = pd.read_csv('source/{iso2}/matrix/interventions_raw.csv', sep=';')
df_enr = pd.read_csv('source/{iso2}/merge/interventions_enriched.csv', sep=';')
print(f'raw={len(df_raw)} enriched={len(df_enr)} match={len(df_raw)==len(df_enr)}')
"
```

Si `match=False`: registra `--status halt` y reporta el error al usuario con el conteo exacto de filas de entrada vs. salida.

**3c. Verificación de atribución temporal en rosters multi-período (OBLIGATORIA si el
roster tiene fecha_inicio/fecha_fin y diputados con >1 período)**

`merge_tables.py` hace el join PERIOD-AWARE: para diputados multi-período elige la fila del
roster cuyo período CUBRE la fecha de sesión (o el más cercano). Verifícalo con un diputado
multi-período que cambió de partido: sus intervenciones antiguas deben llevar el partido de
la ÉPOCA, no el del último período. (Bug real PA 2026-07: "primera fila por id" asignaba a
sesiones de 2009 el partido de 2024 — 34.787 filas mal atribuidas.)

```bash
python3 -c "
import csv,sys; csv.field_size_limit(sys.maxsize)
# elige un id multi-período con partidos distintos en deputies.csv y comprueba 2 eras
for r in csv.DictReader(open('source/{iso2}/merge/interventions_enriched.csv')):
    if r['id_dep']=='{ID_MULTI}': print(r['date'], r['partido'], r['fecha_inicio']); break
"
```

**3d. Medición de la consistencia temporal (OBLIGATORIA, no basta con el sondeo de 3c)**

3c comprueba UN caso; esto mide TODOS. La fecha de cada intervención debe caer dentro del mandato
del diputado al que se le atribuye:

```bash
python3 -c "
import csv,sys; csv.field_size_limit(sys.maxsize)
ok=bad=0
for r in csv.DictReader(open('source/{iso2}/merge/interventions_enriched.csv')):
    if not r['id_dep'].strip() or not r.get('fecha_inicio'): continue
    if r['fecha_inicio'] <= r['date'] <= r['fecha_fin']: ok+=1
    else: bad+=1
print(f'consistencia temporal: {ok/(ok+bad):.2%}  desalineadas={bad}')"
```

Referencias medidas: DO 99,96% · PE 97,40% (preexistente, sin investigar). **< 99% → FLAG.**
Las desalineadas se reparten en dos clases con tratamiento distinto:

- **Hueco intermedio del roster** (el diputado tiene filas ANTES y DESPUÉS del período en que
  habla) → sirvió de forma continua y falta la fila del período central. Añádela heredando
  partido y distrito, con `periodo:inferido-servicio-continuo` en `notas`. En DO eran 4 casos y
  98 filas; arreglarlos bajó las desalineadas de 148 a 34.
- **Extremo** (habla fuera de todo mandato conocido) → posible error de emparejamiento. No lo
  arregles en automático: sácalo al informe.

## Paso 3-bis — Atribución de roles de mesa por la cabecera del acta

⚠ **El paso de mayor impacto de todo el pipeline, y el más fácil de olvidar.** Muchas cámaras
etiquetan las intervenciones de quien preside solo con el cargo (`PRESIDENTE`, `O SR. PRESIDENTE`,
`PRESIDENTA`), sin nombre. Sin este paso, esas filas se quedan sin `id_dep` para siempre:

| país | intervenciones afectadas | % del corpus |
|---|---:|---:|
| PE | 396.756 | **42,1 %** |
| DO | 36.033 | **36,5 %** |
| PA, CR | (resuelto en su momento) | ~20–30 % |

⚠ **«Resuelto en su momento» describe la línea base, no exime del paso.** En un reproceso,
3-bis se RE-EJECUTA desde cero en TODOS los países: el enriched regenerado pierde esas
atribuciones (Paso 1-ter) y la cifra histórica no las devuelve.

### Se ejecuta con la utilidad genérica, no a mano

```bash
python3 ~/.claude/skills/diaries-lib/lib/utils/attribute_presidency.py --country {iso2}
python3 ~/.claude/skills/diaries-lib/lib/utils/attribute_presidency.py --country {iso2} --apply
python3 ~/.claude/skills/diaries-lib/lib/utils/attribute_presidency.py --country {iso2} --check
```

Se parametriza en `country_config/{iso2}.yaml`; **no se escribe un script por país**. Durante la
revisión pre-publicación se escribieron **doce variantes** —BR, PA, PE, PT, PY, UY— que hacían lo
mismo con el patrón metido a fuego, y Ecuador habría necesitado la decimotercera:

```yaml
presidency:
  scope: session | segments        # ¿un presidente por sesión, o cambia dentro?
  target: [PRESIDENT]              # prefijos de speaker_raw que se atribuyen
  sources:                         # dónde se declara, por orden de prioridad
    - from: corrected              # corrected | tagged | meta | external
      pattern: 'PRESIDENCIA DEL SEÑOR ([^\n,]{4,55})'
      name_group: 1
      head: 20000                  # solo la cabecera del documento
    - from: meta
      field: president
  target_exclude:                  # coincidencia COMPLETA, no subcadena
    - 'PRESIDENTE D[AE] REP[ÚU]BLICA(?: .*)?'
  segments:                        # solo si scope: segments
      from: tagged
      pattern: '\(Ocupa la Presidencia el se[ñn]or ([^)]{2,50})\)'
      back_to_base: 'assumiu a presidência (?:o|a) Presidente\s*[.<\n]'
      intervention_mark: '<int\b'  # por defecto; solo si la marca es otra
```

⚠ **`target_exclude` porque el prefijo solo no basta.** «PRESIDENT» captura también al *Presidente
de la República* —jefe de Estado, no diputado— y a presidentes de cámaras extranjeras invitadas: en
PT son 81 filas que se habrían atribuido a un parlamentario portugués cualquiera. La exclusión es
por **coincidencia completa**: el *Presidente da Assembleia da República* SÍ es el objetivo y
contiene entera la cadena del jefe de Estado.

⚠ **`back_to_base`: el relevo de vuelta no lleva nombre.** En PT hay 511 «assumiu a presidência o
Presidente.» a secas. Sin reconocerlos, el tramo del vicepresidente **no se cierra nunca** y se come
el resto de la sesión.

⚠ **Lo que aparece antes de la primera intervención es el sumario, no un relevo.** La cabecera de PT
recapitula todos los relevos de la sesión: sin la guarda caen todos en la posición 0 y el último se
lleva la sesión entera —el presidente titular desaparecía de 116.175 filas—. Se desactiva con
`preamble: keep` si alguna cámara los anuncia de verdad antes de empezar.

⚠ **Un contador de intervenciones que da cero es indistinguible de «no hubo relevos».** PT etiqueta
con `<int>` a secas; la marca por defecto exigía `<int speaker=` y no casaba **ni una vez** en 5.017
documentos. No dio error: dio un resultado plausible. La marca por defecto ya es tolerante y la
utilidad avisa cuando encuentra relevos en un documento sin ninguna marca.

**`scope: segments` cuando la mesa rota dentro de la sesión.** En UY, atribuir un único presidente
por sesión falla el **35,0 %** de los casos, medido; el modo por tramos sigue las marcas de relevo
del propio acta. Si el acta no declara los relevos, deja `scope: session` y **no inventes** (ver la
regla de parada más abajo).

**`from: external`** para los corpus construidos fuera del pipeline, que no tienen `corrected/` ni
`tagged/`: BR y PE sacan la presidencia de los PDF originales, con `path:` apuntando fuera del
proyecto.

⚠ **La fecha sale SIEMPRE de `meta/`, nunca del nombre de fichero.** Solo se permite
`date_from: filename` declarando el motivo, y hoy únicamente en PY, cuyos `session_id` no casan
entre `meta/` y `tagged/` (243 de 1.553) — un defecto de sus datos, no una preferencia.

### Cómo se acepta: por el ACIERTO medido, nunca por la reproducción

```bash
python3 ~/.claude/skills/diaries-lib/lib/utils/audit_presidency_gender.py --country {iso2} --compare
```

Cuando un orador abre su turno con «Sr.ª Presidente» / «Sr. Presidente», el acta está declarando
el **sexo de quien preside en ese momento**, con un mecanismo que no comparte nada con la
atribución: ni el extractor, ni el padrón, ni el resolutor. Contrastarlo con el `sex` de la persona
atribuida da una tasa de acierto, no de parecido.

⚠ **La reproducción NO predice el acierto, y creerlo invierte la decisión.** En PT el genérico
reproducía solo el 66,27 % siendo **cinco puntos mejor**; en BR reproduce el 27,50 % siendo dos
puntos y medio **peor**. Auditoría de 2026-08-01, corpus actual → genérico:

| ✓ el genérico sustituye | | ✗ el genérico NO sustituye | |
|---|---:|---|---:|
| PT | 93,62 → **98,74** | PE | 89,49 → 88,19 |
| UY | 98,21 → **99,65** | BR | 99,27 → 96,89 |
| PY | 99,19 → **99,82** | | |
| PA | 90,82 → **91,64** | | |

BR y PE se construyeron fuera del pipeline —sin `corrected/` ni `tagged/`— y su mesa rota dentro de
la sesión sin ningún intermedio donde situar los tramos. **Conservan su atribución original.**

⚠ **El juez no ve confusiones entre personas del mismo sexo**, que en cámaras masculinizadas son
la mayoría de los casos posibles: es un **límite inferior del error**. Un 99 % no autoriza a
saltarse el muestreo del acta ante una discrepancia concreta.

Antes de existir el juez, la utilidad se validó revisando a mano 50 discrepancias al azar: el
genérico acertaba en 32, el original en 16 y ninguno en 2. Correlacionando el veredicto con la
estrategia del resolutor apareció que **una sola fallaba** —casar por un único token de apellido,
usada en 35 de los 50 casos y con 51 % de acierto, mientras las otras cinco acertaban el 100 %—.

**Ante la duda, no atribuir.** Una atribución dudosa es peor que ninguna: la fila sin `id_dep` es
un hueco visible y auditable; la mal atribuida es un error silencioso.

**Antes de todo lo anterior**, el acta casi siempre dice quién presidió en una fórmula de encabezado
que `diaries-meta` ya extrae al campo `president` (`president_tag` del `country_config`):

- DO — `PRESIDENCIA DE LA DIPUTADA: {NOMBRE}`
- PE — `PRESIDENCIA DEL SEÑOR {NOMBRE}` / `DE LOS SEÑORES {N1}, {N2} Y {N3}`

Marca `match_method = "president_meta"` para que el origen quede auditable.

⚠ **Regla de parada — no inventes cuando la sesión tiene varias presidencias.** Es el error que
hay que evitar, y aparece en los dos países medidos:

- Si la sesión declara **una sola** presidencia → atribuye.
- Si declara **varias** y el corpus distingue el género del marcador (`PRESIDENTE` /
  `PRESIDENTA`), atribuye solo cuando el **sexo registrado en el padrón** desempata sin
  ambigüedad. En PE esto recuperó 14.720 intervenciones extra.
- Si conviven `PRESIDENTE` y `PRESIDENTE EN FUNCIONES` en la misma sesión, o hay dos o más
  presidencias del mismo sexo → **no atribuyas**. El acta nombra a quienes presidieron pero no
  dice cuándo se produjo el relevo. En PE eso deja fuera el 55,4 % de la presidencia; es un
  límite de la fuente, no del procesamiento, y documentarlo es preferible a inventar.

**Antes de darlo por imposible, mira la forma de la fórmula.** En PE existe en singular
(`DEL SEÑOR X`) y en **plural** (`DE LOS SEÑORES X, Y Y Z`), con el nombre continuando en la línea
siguiente: un regex anclado a `\n` perdía el 32 % de las cabeceras y habría hecho concluir que la
cobertura era mucho peor de la real.

## Paso 3-ter — Integridad referencial matriz ↔ padrón (Gate E, OBLIGATORIO)

Todo `id_dep` del enriched debe existir en `deputies.csv`, y todo par `(id_dep, legislatura)`
usado debe existir en el padrón. Se comprueba AQUÍ, antes de `standardize`: un id huérfano en el
canónico rompe el join con el padrón publicable sin que nada avise —
[[feedback_integridad_referencial]].

```bash
python3 -c "
import csv,sys; csv.field_size_limit(sys.maxsize)
def rd(p):
    fh=open(p,encoding='utf-8'); d=csv.Sniffer().sniff(fh.readline(),';,').delimiter; fh.seek(0)
    return csv.DictReader(fh,delimiter=d)
def leg(r): return (r.get('legislatura') or r.get('legislature') or '').strip()
dep,pares=set(),set()
# ⚠ si el enriched NO trae columna de legislatura, el chequeo de pares degenera (clave vacía):
#   en ese caso solo vale el chequeo de id_dep
hay_leg=None
for r in rd('source/{iso2}/deputies/deputies.csv'):
    i=(r.get('id_dep') or '').strip()
    if i: dep.add(i); pares.add((i,leg(r)))
ids_h,pares_h=set(),set()
for r in rd('source/{iso2}/merge/interventions_enriched.csv'):
    if hay_leg is None: hay_leg=('legislatura' in r or 'legislature' in r)
    i=(r.get('id_dep') or '').strip()
    if not i: continue
    if i not in dep: ids_h.add(i)
    elif hay_leg and (i,leg(r)) not in pares: pares_h.add((i,leg(r)))
print(f'id_dep huérfanos (no existen en el padrón): {len(ids_h)}')
print(f'pares (id_dep, legislatura) huérfanos:      {len(pares_h)}' if hay_leg
      else 'SIN columna de legislatura en el enriched: chequeo de pares NO aplicable')
for x in sorted(ids_h)[:20]:   print('  ID? ', x)
for x in sorted(pares_h)[:20]: print('  PAR?', x)"
```

Los huérfanos **se listan y se resuelven ANTES de `diaries-standardize`**, cada clase con su
tratamiento:

- **`id_dep` inexistente en el padrón** → error duro: errata de id (en la `matching_table` o en
  una edición manual) o fila que falta en `deputies.csv`. Se corrige el id o se completa el
  padrón — no pasa al canónico.
- **Par `(id_dep, legislatura)` huérfano** → el acta registra al diputado hablando en una
  legislatura que el padrón no le asigna, y el acta manda: la fila **NUNCA se elimina**
  ([[feedback_primacia_del_diario]]). Se resuelve completando el padrón (suplencias, tomas de
  posesión a media legislatura, típicamente en legislatura contigua) o, si la fuente no lo
  respalda, declarándolo en `process_report.md` como medida de completitud del padrón.

## Paso 4 — Calcular confianza

⚠ **Orden obligatorio: el Paso 3-bis corre ANTES de este cálculo, y la confianza INCORPORA lo
atribuido allí.** El `match_rate` del JSON de `merge_tables.py` se computa en el join, ANTES de
3-bis: usarlo tal cual puede dejar el skill en `flag` por filas que 3-bis ya resolvió
(`president_meta`). Recalcula sobre el enriched FINAL:

```bash
python3 -c "
import csv,sys; csv.field_size_limit(sys.maxsize)
fh=open('source/{iso2}/merge/interventions_enriched.csv'); d=csv.Sniffer().sniff(fh.readline(),';,').delimiter; fh.seek(0)
n=m=0
for r in csv.DictReader(fh,delimiter=d):
    n+=1; m+=bool((r.get('id_dep') or '').strip())
print(f'match_rate post-3bis: {m/max(n,1):.4f}')"
```

```
confianza = match_rate  (recalculado sobre el enriched tras 3-bis)
```

Determina status:
- Si `match_rate >= 0.90` y filas coinciden: status = `complete`
- Si `match_rate >= 0.70` y filas coinciden: status = `flag`
- Si `match_rate < 0.70` o filas no coinciden: status = `halt`

## Paso 5 — Actualizar estado

```bash
python ~/.claude/skills/diaries-lib/lib/utils/update_state.py \
  --country {iso2} --skill diaries-merge --session "_country" \
  --status {status} --confidence {confianza} \
  --output "source/{iso2}/merge/interventions_enriched.csv"
```

## Paso 6 — Resumen

Imprime:
```
diaries-merge — {iso2}
Filas entrada:       {rows_input}
Filas salida:        {rows_output}  [OK / ERROR: no coinciden]
Tasa de match:       {match_rate:.1%}
Filas sin match:     {unmatched_rows}
Columnas añadidas:   {columns_added}
Status:              {status}
```

Si status es `flag` o `halt`: "Revisa los speakers sin resolver en match/matching_table.csv y ejecuta /diaries-match --country {iso2} --force."
