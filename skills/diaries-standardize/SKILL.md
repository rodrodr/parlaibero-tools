---
name: diaries-standardize
description: "Aplica el esquema canónico final a interventions_enriched.csv"
allowed-tools: [Read, Write, Edit, Bash]
---

Eres el skill `diaries-standardize` del pipeline ParlaIbero. Conviertes `interventions_enriched.csv` en `{ISO2}_interventions.csv` con el esquema canónico de ParlaIbero. NUNCA sobreescribas el archivo canónico sin `--force`. Este skill opera a nivel PAÍS.

## Argumentos esperados

`--country {iso2}` (obligatorio)
`--force` (permite sobreescribir el archivo canónico si ya existe)

## Paso 1 — Guardia de sobreescritura

ANTES de hacer cualquier otra cosa, verifica si el archivo final ya existe:
```bash
test -f source/{iso2}/standardize/{ISO2}_interventions.csv && echo "EXISTS" || echo "OK"
```

donde `{ISO2}` es el código del país en MAYÚSCULAS (ej. `PT`, `ES`, `MX`).

Si existe y NO se pasó `--force`: detente inmediatamente con:
```
ERROR: source/{iso2}/standardize/{ISO2}_interventions.csv ya existe.
Usa --force para sobreescribir.
ADVERTENCIA: Sobreescribir eliminará el archivo canónico actual del país.
```

No continúes bajo ninguna circunstancia sin `--force` si el archivo existe.

## Paso 1-bis — Seguridad de reejecución (lo que un `--force` destruye en silencio)

⚠ El guardia de sobreescritura protege el archivo, pero **no avisa de lo que se pierde**. Sobre un
corpus ya cerrado se han aplicado casi siempre operaciones POSTERIORES al pipeline estándar, que
una regeneración limpia borra sin decir nada. Antes de usar `--force`, comprueba las tres:

**1. Filas apartadas a un sidecar (LEGADO de la línea base, no destino).** La doctrina vigente
es que **nada se aparta**: la fila que no es discurso se REINTEGRA en el canónico declarada con
`dm_speech = 0` ([[decision_tipo_de_texto]]). Si existe `standardize/{ISO2}_*_sidecar.csv` es un
resto de la línea base anterior — al regenerar, sus filas vuelven al corpus con `dm_speech = 0`;
**no se re-extraen a un sidecar nuevo**.

```bash
ls source/{iso2}/standardize/*_sidecar.csv 2>/dev/null && echo "⚠ sidecar LEGADO: sus filas se reintegran con dm_speech=0, no se vuelve a apartar"
```

**2. Atribuciones aplicadas después del merge** (roles de mesa resueltos por la cabecera del acta,
`diaries-merge` Paso 3-bis). Viven en el enriched, no en la `matching_table`, así que un merge
rehecho desde cero las pierde. Señal: filas con `match_method == "president_meta"` en el enriched.

**3. Correcciones humanas.** `manual`, `NOT_SPEAKER` y `role` en la `matching_table`
(`diaries-match` Paso 6b las reinyecta), y los valores marcados `manual:` en las notas del roster
(`diaries-deputies` Paso 4e establece la precedencia).

**Compara SIEMPRE antes y después.** Una regeneración no debería cambiar el recuento salvo que lo
esperes:

```bash
python3 -c "
import csv,sys,os; csv.field_size_limit(sys.maxsize)
p='source/{iso2}/standardize/{ISO2}_interventions.csv'
if os.path.exists(p):
    fh=open(p); d=csv.Sniffer().sniff(fh.readline(),';,').delimiter; fh.seek(0)
    n=i=0
    for r in csv.DictReader(fh,delimiter=d):
        n+=1; i+=bool(r['id_dep'].strip())
    print(f'ACTUAL: {n:,} filas · id_dep {i/n:.1%}  ← compáralo con el resultado de la regeneración')"
```

(Sniffer de separador como en el 4-ter c — **ES y GT usaban `;` — YA NO, ver abajo**; leer con el separador
equivocado colapsa las 16 columnas en una y el recuento de `id_dep` sale falso.)

Si tras regenerar bajan las filas vinculadas, **has perdido trabajo posterior**: recupéralo del
backup y vuelve a aplicarlo antes de dar el paso por bueno.

## Paso 2 — Leer configuración

Lee `country_config/{iso2}.yaml` con Read. Extrae:
- `processing.csv_separator` (default: ";")

## Paso 3 — Verificar prerequisito

Verifica que existe `source/{iso2}/merge/interventions_enriched.csv`:
```bash
test -f source/{iso2}/merge/interventions_enriched.csv && echo "OK" || echo "MISSING"
```

Si no existe: `ERROR: Falta source/{iso2}/merge/interventions_enriched.csv. Ejecuta primero /diaries-merge --country {iso2}`

## Paso 4 — Ejecutar estandarización

```bash
mkdir -p source/{iso2}/standardize/
python ~/.claude/skills/diaries-lib/lib/utils/standardize_csv.py \
  --input "source/{iso2}/merge/interventions_enriched.csv" \
  --output "source/{iso2}/standardize/{ISO2}_interventions.csv" \
  --config "country_config/{iso2}.yaml" \
  {--force si se pasó el flag}
```

El script escribe JSON a stdout con:
```json
{
  "total_rows": 5432,
  "validation_errors": 0,
  "output_path": "source/{iso2}/standardize/{ISO2}_interventions.csv",
  "status": "ok"
}
```

## Esquema canónico — 16 columnas (en este orden)

⚠ **El esquema canónico REAL tiene 16 columnas** (verificado uniforme en los 16 países). `id_session`
e `id_int` los pone `asignar_ids.py` (Paso 4-ter); el resto, `standardize_csv.py`.

| # | Columna | Tipo | Restricciones |
|---|---|---|---|
| 1 | `id_session` | string | `{ISO2}{leg:03d}{ses:04d}` (9 car.). Lo asigna `asignar_ids.py`. |
| 2 | `id_int` | string | `id_session`+`{orden:05d}` (14 car.), único y estable. Lo asigna `asignar_ids.py`. |
| 3 | `legislature` | string | Período constitucional (ver Paso 4-bis); se imputa por fecha si falta |
| 4 | `legislative_session` | string | Período de sesiones (ordinario/extraordinario) dentro de la legislatura |
| 5 | `session_number` | string | **Entero puro O alfanumérico** (`12`, `12A`, `001O`). Con o sin ceros a la izquierda. Vacío permitido. |
| 6 | `date` | string | ISO 8601 `YYYY-MM-DD` obligatorio cuando presente |
| 7 | `session_type` | string | `Ordinaria` / `Extraordinaria` / `Solemne` / `Otra` |
| 8 | `intervention_order` | string | Entero secuencial dentro de la sesión; `0` = Prolegomena; se genera si falta |
| 9 | `speaker_raw` | string | Texto original del orador, sin normalizar |
| 10 | `id_dep` | string | ID único del diputado; vacío para no-diputados |
| 11 | `speaker_name` | string | Nombre normalizado; puede coincidir con `speaker_raw` |
| 12 | `sex` | string | `M`/`F`; vacío sin `id_dep`. Derivada — procedencia en `sex_source` del padrón |
| 13 | `party` | string | Sigla o nombre del partido en la fecha de la sesión |
| 14 | `district` | string | Circunscripción o estado electoral |
| 15 | `dm_speech` | string | Binaria `1`/`0`: `1` = intervención; `0` = no-discurso (Prolegomena, sumario, votación) |
| 16 | `text` | string | Texto completo de la intervención |

> **Separador**: la mayoría usa `,`; **ES y GT usaban `;` — YA NO, ver abajo** (su `text` trae muchas comas). Es una
> elección por país, no un error — respétala al leer/escribir.
> **Nota sobre `session_number`**: BR usa sufijos de tipo (`001O`, `001E`, `012A`). El validador acepta
> cualquier alfanumérico — no fuerces entero si contiene letras.
> ✅ **`standardize_csv.py` ya declara las 16 columnas** (`id_session`/`id_int` incluidos): las crea
> vacías si faltan y las PRESERVA en re-ejecución. El Paso 4-ter (`asignar_ids.py`) las RELLENA. Antes
> declaraba 14 y las dropeaba (mismo patrón que borró `sex`/`dm_speech` en su día).

## Paso 4-bis — Normalizar `legislature` (convención ParlaIbero)

⚠ `standardize_csv.py` copia `legislature` tal cual viene de la fuente. Si la fuente nombra cada
período de sesiones en texto libre, el resultado es **inservible como variable**: en DO salieron
**145 valores distintos** para 7 legislaturas reales — `DE` vs `DEL` (54.653 vs 44.028 filas),
erratas de la propia acta (`EXTRARDINARIA`, `ORDINARI`, `PRÓRRGA`), espacios perdidos
(`LEGISLATURAORDINARIA`) y variantes de caja.

**La convención del proyecto es el PERÍODO CONSTITUCIONAL** — CL (período legislativo), CR
(período de 4 años), AR (34 períodos), MX (LIV–LXVI), PA (7 períodos). Es lo que hace la columna
comparable entre países y lo que alinea `legislature` con `id_dep`, `party` y `district`, que ya
son period-aware.

Comprueba siempre la cardinalidad antes de cerrar:

```bash
python3 -c "
import csv,sys; csv.field_size_limit(sys.maxsize)
from collections import Counter
fh=open('source/{iso2}/standardize/{ISO2}_interventions.csv'); d=csv.Sniffer().sniff(fh.readline(),';,').delimiter; fh.seek(0)
c=Counter(r['legislature'] for r in csv.DictReader(fh,delimiter=d))
print(len(c),'valores distintos'); print(dict(c.most_common(10)))"
```

(Sniffer como en el 4-ter c — ES/GT usan `;`.)

Si el número de valores distintos **excede el número real de legislaturas del país**, reasigna por
fecha con las fronteras del período y documenta el esquema en `country_config/{iso2}.yaml`
(`standardize.legislature_scheme`). El detalle fino de la fuente (ordinaria/extraordinaria,
prórroga) ya viaja en `session_type` + `date`, y la cadena original se conserva intacta en
`merge/interventions_enriched.csv` — no se pierde nada.

## Paso 4-ter — Desdoblar Prolegomena duplicados + asignar `id_session`/`id_int`

⚠ `standardize_csv.py` NO genera `id_session`/`id_int` (las dos primeras columnas canónicas). Se
asignan aquí, DESPUÉS de que `intervention_order` y `legislature` (Paso 4-bis) estén fijados.
Son TRES sub-pasos en orden fijo: **a) desdoblar → b) asignar → c) verificar valores**.

**a) Desdoblar los Prolegomena duplicados** (obligatorio ANTES de asignar). Dos carátulas con
`orden = 0` en la misma `(legislature, date, session_number)` colisionan en `id_int = …00000` y el
sub-paso b se negará a escribir. Medido en los 16 corpus (2026-08-23): 7 países las tienen — CR
7.678 · ES 1.650 · AR 377 · CL 260 · MX 201 · UY 110 · EC 199. El desdoble elimina las copias
EXACTAS y sufija las distintas (`104` → `104B`), que quedan como sesión propia con carátula y sin
turnos (información honesta — ver el docstring del script).

```bash
# medir primero (read-only):
python ~/.claude/skills/diaries-lib/lib/utils/desdoblar_prolegomena_duplicado.py --country {iso2} --medir
# aplicar (backup {ISO2}_interventions.pre_desdoble.csv la primera vez):
python ~/.claude/skills/diaries-lib/lib/utils/desdoblar_prolegomena_duplicado.py --country {iso2}
```

**b) Asignar los ids:**

```bash
python ~/.claude/skills/diaries-lib/lib/utils/asignar_ids.py --country {iso2}
```

Formato `{ISO2}{legislatura:03d}{sesión:04d}{orden:05d}` (14 car.); `id_session` = primeros 9,
`id_int` = 14. La utilidad **no escribe si detecta `id_int` repetidos** (señal de colisión de
legislatura/sesión/orden a resolver antes). Prolegomena (`orden = 0`) → `id_int` termina en `00000`.

**c) Verificación obligatoria de VALORES** ⚠ — la cabecera no basta: `asignar_ids.py` termina con
**rc=0 incluso cuando se niega a escribir** (busca `✗` en su salida) y en ese caso los ids quedan
VACÍOS. Y el desdoble solo cubre las carátulas: una colisión de `orden ≥ 1` (dos sesiones reales
fundidas bajo la misma clave) también lo hace abortar.

```bash
head -1 source/{iso2}/standardize/{ISO2}_interventions.csv | tr ',;' '\n' | head -2
# debe imprimir:  id_session  /  id_int
python3 -c "
import csv,sys; csv.field_size_limit(sys.maxsize)
vistos,dup,vac,n=set(),0,0,0
fh=open('source/{iso2}/standardize/{ISO2}_interventions.csv'); d=csv.Sniffer().sniff(fh.readline(),';,').delimiter; fh.seek(0)
for r in csv.DictReader(fh,delimiter=d):
    n+=1; v=(r.get('id_int') or '').strip()
    if not v: vac+=1
    elif v in vistos: dup+=1
    else: vistos.add(v)
print(f'filas {n:,} · id_int vacíos {vac:,} · duplicados {dup:,}')"
# ambos deben ser 0
```

Si hay VACÍOS: `asignar_ids` se negó — el desdoble no bastó; identifica las claves
`(legislature, date, session_number, intervention_order)` repetidas y resuélvelas antes de
reintentar. Si hay DUPLICADOS: PARA — el corpus quedó con ids corruptos; restaura el backup.

> `standardize_csv.py` ya preserva `id_session`/`id_int` (las crea vacías si faltan), pero **no las
> COMPUTA** — este paso es OBLIGATORIO tras cada `standardize_csv.py`.

## Paso 5 — Reportar errores de validación

Lee el JSON de stdout. Si `validation_errors > 0`:

Imprime cada error con contexto:
```
ERRORES DE VALIDACIÓN ({validation_errors} total):
  Fila {row}: columna '{column}' — valor '{value}' — {error}
  ...
```

Si `validation_errors > total_rows * 0.05` (más del 5% de filas con error): usa status `flag`.
Si `validation_errors > total_rows * 0.20` (más del 20%): usa status `halt`.

## Paso 6 — Calcular confianza

```
confianza = 1.0 - (validation_errors / max(total_rows, 1))
```

## Paso 7 — Actualizar estado

```bash
python ~/.claude/skills/diaries-lib/lib/utils/update_state.py \
  --country {iso2} --skill diaries-standardize --session "_country" \
  --status {status} --confidence {confianza} \
  --output "source/{iso2}/standardize/{ISO2}_interventions.csv"
```

donde `{status}` es `complete`, `flag` o `halt` según el paso 5.

## Paso 8 — Confirmación final

Imprime:
```
diaries-standardize — {iso2}
standardize/{ISO2}_interventions.csv generado: {total_rows} filas
Errores de validación: {validation_errors}
Status: {status}
Confianza: {confianza:.3f}
```

Si hay errores: "Revisa los errores de validación arriba. Ejecuta /diaries-review --country {iso2} --skill diaries-standardize para gestionarlos."

> ⚠⚠ **Separador: SIEMPRE la coma, en los dieciséis** (directiva del investigador, 2026-09-01, `br-0019`). Antes se decía que ES y GT usaban `;`; se unificó por compatibilidad. ⚠ ES y GT tienen aún su canónico en `;` y pasarán a `,` al regenerarse en su reproceso, así que **al LEER conviene seguir detectando el separador**, aunque al ESCRIBIR sea siempre coma.
