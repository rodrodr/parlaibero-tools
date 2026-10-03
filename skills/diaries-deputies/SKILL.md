---
name: diaries-deputies
description: "Construye o actualiza la base de datos de diputados"
allowed-tools: [Read, Write, Edit, Bash]
---

Eres el skill `diaries-deputies` del pipeline ParlaIbero. Construyes o actualizas `deputies.csv`, la base de datos de diputados/oradores del país. Este skill opera a nivel PAÍS (una sola ejecución por país, no por sesión).

## Argumentos esperados

`--country {iso2}` (obligatorio)
`--force` (sobrescribir deputies.csv si ya existe)
`--dry-run` (mostrar plan sin escribir nada)

## Paso 1 — Leer configuración

Lee `country_config/{iso2}.yaml` con Read. Extrae:
- `deputies.external_file` (ruta a archivo externo con lista de diputados; vacío si no aplica)
- `deputies.id_dep_prefix` (prefijo para IDs, ej. "ES", "PT"; default: iso2.upper())
- `deputies.fuzzy_dedup_threshold` (umbral para deduplicación fuzzy; default: 85)

## Paso 2 — Verificar prerequisito

⚠ **El prerequisito depende de la RUTA, y `matrix` NO siempre hace falta** (corregido 2026-07-24).

| Ruta | Insumo | Puede ejecutarse |
|---|---|---|
| A — archivo externo (Paso 3) | el propio archivo | en cualquier momento |
| **Pase de lista (Paso 4a-pre, preferente)** | `corrected/` | **ANTES de `diaries-tag`** |
| B — desde speakers (Paso 4a) | `matrix/interventions_raw.csv` | después de `diaries-matrix` |

```bash
test -f source/{iso2}/matrix/interventions_raw.csv && echo "matrix OK (ruta B disponible)" \
  || echo "sin matrix — usa la ruta del pase de lista o el archivo externo"
ls source/{iso2}/corrected/*.txt >/dev/null 2>&1 && echo "corrected OK (pase de lista disponible)"
```

Detente con error **solo si vas por la ruta B** y falta la matriz:
`ERROR: Falta source/{iso2}/matrix/interventions_raw.csv. Ejecuta primero /diaries-matrix --country {iso2}`

Si las actas traen pase de lista nominal, **construye el padrón antes de tagear**: además de ser
más completo (incluye a quien no habla), el roster resultante se pasa a `diaries-tag --deputies`
para mejorar el scoring de su nivel probabilístico, y el índice fecha→presentes que produce es el
insumo de la desambiguación por asistencia de `diaries-match`. Dos pasos posteriores mejoran.

Si `deputies.csv` ya existe y no se pasó `--force`: detente con error: `ERROR: source/{iso2}/deputies/deputies.csv ya existe. Usa --force para reconstruir.`

## Paso 3-pre — PENDIENTE: la fuente OFICIAL EN LÍNEA como insumo del padrón

⚠ **Directiva del investigador (2026-09-01): en una actualización futura, la bajada de la API pasa
a formar parte de este skill.** Queda aquí descrito para que aterrice sin arqueología; hoy todavía
NO está implementado y BR se resolvió con un paso propio.

**Por qué importa, con el coste ya medido en BR.** Un padrón extraído en una fecha cierra en ella
el último tramo de TODAS las personas. Si el corpus llega más lejos, cada intervención posterior
cae fuera del último tramo conocido: en BR fueron **30.745 filas (3,19%)**, el 86,6% por ser
posteriores a la fecha de extracción (18-12-2024) y el 13,4% por caer antes del alta que el padrón
registraba. Reconstruir desde la API oficial las dejó en **1.442 (−95%)**.

**Cómo se hizo, que es lo reutilizable:**

1. **La API da EVENTOS, no intervalos.** Un tramo va de un evento al siguiente dentro de la misma
   legislatura, y el último queda **ABIERTO** salvo que exista un `FIM_MANDATO`. Un tramo sin fecha
   de fin está VIGENTE, no es inválido — y aguas abajo hay que tratarlo así.
2. **Fundir los tramos consecutivos con el mismo partido.** La API emite un evento por cada cambio
   de SITUACIÓN (licencias, suplencias), no solo de partido: sin fundir, el padrón de BR se
   inflaba de 4.980 a 12.911 filas sin aportar un solo hecho nuevo.
3. **Guardar el JSON CRUDO de cada persona.** La descarga es la única parte NO reproducible del
   proceso —la API puede cambiar—, así que lo que se conserva es su respuesta.
4. **Declarar la FECHA DE DESCARGA en el `country_config`.** Los tramos abiertos son «vigentes a»
   esa fecha; sin ella, una lectura futura tomará por actual algo que dejó de serlo.
5. ⚠⚠ **Comparar ANTES de sustituir, nunca después.** El script exige un `--medir` previo, y fue
   esa comparación la que destapó lo que nadie buscaba: el padrón local escribía `PL` para
   2007-2018, cuando ese partido se llamaba `PR`. **Aplicaba el nombre ACTUAL hacia atrás**, y el
   acta lo dirimió con un corte limpio (PL≤2006 · PR 2007-2018 · PL≥2019, cero solapamiento). En
   un corpus histórico el nombre correcto es el CONTEMPORÁNEO: quien busque «PR» en 2010 debe
   encontrarlo. Una fuente externa que contradiga al padrón es una oportunidad de aprender, y solo
   lo es si se mira antes de escribir.

Implementación de referencia: `scripts/campana_reproceso/br_match/bajar_historico_br.py` y
`tramos_desde_api_br.py`. Decisión `br-0017`.

## Paso 3 — Ruta A: archivo externo

Si `deputies.external_file` no está vacío en la configuración:

**3A-1.** Lee el archivo externo con Read.

**3A-2.** Verifica que tiene las columnas mínimas requeridas: `nombre_completo`, `nombre`, `apellidos`. Si falta alguna, detente con: `ERROR: El archivo externo no tiene las columnas requeridas: {columnas_faltantes}`

**3A-3.** Si falta la columna `id_dep`: genera IDs secuenciales con prefijo:
```python
id_dep = f"{PREFIX}{N:04d}"  # donde N empieza en 1
```

**3A-4.** Asegúrate de que el CSV final tenga estas columnas canónicas en orden:
`id_dep, nombre_completo, nombre, apellidos, partido, grupo_parlamentario, circunscripcion, legislatura, fecha_inicio, fecha_fin, notas`

Las columnas faltantes del externo se rellenan con vacío. Escribe el resultado en `source/{iso2}/deputies/deputies.csv`.

> ⚠ **`legislatura` es columna propia.** Ver el Paso 4-bis: no vale dejarla en `notas`.

## Paso 4 — Ruta B: construir desde cero

Si `deputies.external_file` está vacío:

**4a-pre. Fuente preferente: el PASE DE LISTA, no los speakers.**

Antes de caer en 4a, comprueba si las actas traen pase de lista nominal
(`Asisten los señores diputados:` / `DIPUTADOS PRESENTES` / `INCORPORADOS A LA SESIÓN`). Si existe,
constrúyelo desde ahí — es estrictamente superior:

| | desde speakers (4a) | desde pase de lista |
|---|---|---|
| cobertura | solo quien HABLÓ | membresía completa, también los silenciosos |
| período | hay que inferirlo | explícito por fecha de sesión |
| autoridad | derivado del tagging | dato primario del acta |

El roster construido desde speakers **nunca puede ser más completo que el tagging**, y hereda todos
sus errores. Además, el índice fecha→presentes que produces aquí es el insumo de la desambiguación
por asistencia en `diaries-match` — se paga solo.

⚠ El pase de lista es una **lista separada por comas y en prosa**: parsearlo genera basura que
DEBES limpiar antes de dedup, porque los artefactos ESCONDEN duplicados. Catálogo observado en DO:

| artefacto | ejemplo real | tratamiento |
|---|---|---|
| coma ausente → dos personas pegadas | `Clodomiro de Jesús Chá Dionicio de la Rosa` | partir en dos |
| arrastre del vecino | `Batista Areché` ⇐ *Cedeño Areché* | fantasma, ver 5c-bis |
| ancla de la frase absorbida | `INCORPORADOS A LA SESIÓN: Nelsa Suárez` | recortar el ancla |
| fuga de prosa posterior | `Guadalupe Valdez. Por disposición de la Presidencia…` | cortar en el `.` |
| residuo de token | `Ra Máximo Castro Silverio` | recortar cabeza |
| conector final | `… y` | recortar cola |

**4a. Extraer speakers únicos**

```bash
python3 -c "
import pandas as pd, json, sys
df = pd.read_csv('source/{iso2}/matrix/interventions_raw.csv', sep=';')
names = df['speaker_raw'].dropna().unique().tolist()
print(json.dumps(names))
" > source/{iso2}/.tmp_speakers.json
```

**4b. Matching difuso contra deputies.csv existente**

Si `source/{iso2}/deputies/deputies.csv` ya existe (modo actualización incremental):
```bash
python ~/.claude/skills/diaries-lib/lib/utils/fuzzy_match.py \
  --names "source/{iso2}/.tmp_speakers.json" \
  --deputies "source/{iso2}/deputies/deputies.csv" \
  --threshold {fuzzy_dedup_threshold} \
  --output "source/{iso2}/.tmp_fuzzy.json"
```

Filtra los nombres que ya tienen match para no duplicarlos. Si deputies.csv no existe aún, omite este paso.

**4c. Agrupar por similaridad**

Lee `.tmp_speakers.json` (y `.tmp_fuzzy.json` si existe). Para los nombres sin match previo, agrúpalos por similaridad de cadena:

- **Clúster de 1 nombre**: crea el registro directamente. Heurística de separación nombre/apellidos: las últimas 1-2 palabras son apellidos, el resto es nombre. Ajusta si el patrón del país es diferente (p. ej. países donde el primer apellido va antes).
- **Clúster de 2-3 nombres**: usa el nombre más largo como forma canónica. Aplica la misma heurística nombre/apellidos.
- **Clúster de 4+ nombres**: usa tu juicio como LLM. Analiza las variantes, determina la forma canónica más completa, y separa nombre/apellidos con cuidado.

**4d. Asignar IDs y escribir**

Asigna `id_dep = {PREFIX}{N:04d}` siendo PREFIX el valor de `deputies.id_dep_prefix` y N el número secuencial (continúa desde el último si hay deputies.csv previo).

```bash
mkdir -p source/{iso2}/deputies/
```

Escribe `source/{iso2}/deputies/deputies.csv` con columnas canónicas:
`id_dep, nombre_completo, nombre, apellidos, partido, grupo_parlamentario, circunscripcion, legislatura, fecha_inicio, fecha_fin, notas`

Las columnas sin información van vacías.

## Paso 4-bis — UNA FILA POR (id_dep, legislatura). Nunca colapsar (OBLIGATORIO)

**La unidad de observación del padrón es la persona EN una legislatura, no la persona.** Un
diputado que sirvió tres períodos tiene **tres filas**, con el mismo `id_dep` y distinta
`legislatura`. Por tanto **`id_dep` NO es único en este archivo**, y es correcto que no lo sea:
es lo único que permite que `partido`, `circunscripcion` y `grupo_parlamentario` cambien de un
período a otro, que es justo lo que se quiere medir.

Prohibido, las dos formas de romperlo:

| ✗ mal | ✓ bien |
|---|---|
| `GT00017 · … · notas="VI,VII,VIII"` | tres filas, `legislatura` = `VI`, `VII`, `VIII` |
| `GT00017 · legislatura="VI,VII,VIII"` | tres filas, una por legislatura |

**Por qué está escrito aquí.** El esquema de este skill **no incluía `legislatura`**, así que
cada país la metió donde pudo: en `notas`. Resultado medido el 2026-08-03 sobre los quince
padrones publicados —**`legislature` vacía en TODAS las filas en 9 de 15**: AR, CL, CO, DO, GT,
PA, PE, PY, UY. En GT eran romanos sueltos (`IX,X`) con 264 filas colapsadas; en PY y UY iba
como `legislature:1998-2003` dentro del texto libre; en AR como `periodos:2003 - 2005, 2003 -
2007`. Ninguna comprobación del pipeline lo veía, porque los totales cuadran.

Son dos defectos encadenados, y conviene nombrarlos por separado:

1. **Variable de análisis en el cajón de sastre.** `notas` es texto libre: no se puede unir,
   filtrar ni agrupar por él. Si un dato sirve para analizar, va en su columna.
2. **Varias observaciones en una celda.** `IX,X` mete dos hechos en una fila y obliga a cada
   usuario a partir la cadena por su cuenta — y, peor, hace imposible que el partido difiera
   entre esas dos legislaturas.

**Comprobación obligatoria antes de cerrar el padrón:**

```python
assert (d.legislatura == "").sum() == 0,            "legislatura vacía: sácala de la fuente, no la inventes"
assert not d.legislatura.str.contains(",").any(),   "legislaturas colapsadas en una celda"
assert not d.duplicated(["id_dep", "legislatura"]).any(), "par (id_dep, legislatura) repetido"
```

Si la fuente no da la legislatura, la fila se queda con el campo **vacío y contada aparte**:
nunca se rellena a ojo ni se propaga desde una fila vecina. En CL, CO y PA el dato no está en
ninguna columna y hay que recuperarlo de la fuente en su reproceso.

⚠ **Aguas abajo:** con el padrón en formato largo, las uniones matriz ↔ padrón van por
**`id_dep` + `legislatura`**, no por `id_dep` solo — unir por `id_dep` multiplica filas. El
`data_dictionary.md` del país debe decirlo: la frase «joinable on `id_dep`» pasa a ser falsa.
Para arreglar un padrón ya escrito:
`python3 ~/.claude/skills/diaries-lib/lib/utils/normalize_roster_legislature.py --csv <padrón> --dry-run`

**4e. Peso de evidencia y procedencia en `notas` (AMBOS obligatorios)**

Estas dos anotaciones no son documentación: son **infraestructura** de la que dependen 5c-bis, 5e y
5i. Sin ellas el roster no es auditable y la dedup elige a ciegas.

- **Peso** — `visto_en:{N} sesiones` en cada fila (nº de sesiones donde aparece esa grafía). Es lo
  que distingue una persona de un misparse, y la grafía real de la contaminada.
- **Procedencia** — etiqueta la FUENTE de cada valor, no solo el hecho:
  `camara:oficial(1998-2002)` · `cedula:001-0123456-7` · `jce:` · `acta:bloque` ·
  `web:busqueda-verificada` · `partido:inferido-otro-periodo` · `manual`

**Precedencia al rellenar o corregir un campo** (un enriquecimiento posterior NUNCA pisa una fuente
más fuerte):

```
manual  >  camara:oficial  >  acta:bloque  >  jce:  >  web:  >  *:inferido  >  (vacío)
```

Esto es lo que permite reprocesar el roster N veces sin destruir trabajo previo: al integrar los
listados oficiales de DO, la regla `if not partido or 'inferido' in notas` corrigió 137 partidos sin
tocar una sola corrección humana.

## Paso 5 — Deduplicación (SIEMPRE obligatorio)

Este paso debe ejecutarse **siempre**, tanto en Ruta A como en Ruta B, y antes de calcular confianza. Los sistemas parlamentarios frecuentemente asignan códigos distintos al mismo diputado en diferentes legislaturas. Ignorar esto produce inconsistencias graves en diaries-match.

**Importante:** múltiples filas con el **mismo** `id_dep` en distintas legislaturas son **correctas** — un diputado puede aparecer N veces si sirvió N períodos. El problema son distintos `id_dep` para la misma persona.

### 5a. Normalización robusta

Usa `unicodedata` en lugar de sustituciones manuales; es más completo:

```python
import unicodedata, re

def norm(s):
    s = unicodedata.normalize('NFD', s.lower().strip())
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')  # strip diacritics
    return re.sub(r'\s+', ' ', s)
```

### 5b. Tres pasadas de detección complementarias

La deduplicación requiere tres pasadas porque cada una captura un tipo distinto de variante. Construye primero el diccionario de IDs únicos:

```python
from rapidfuzz import fuzz

# Una fila representante por id_dep (primera aparición)
seen = {}   # id_dep → {'nombre_completo', 'nombre', 'apellidos', ...}
for row in rows:
    if row['id_dep'] not in seen:
        seen[row['id_dep']] = row

ids = list(seen.keys())
```

#### Pasada 1 — Fuzzy sobre nombre_completo completo

Detecta: typos de 1-2 caracteres, acentos faltantes, variantes OCR (J/G, rn/m…), apellidos con tokens en orden invertido.

```python
names_norm = {i: norm(seen[i]['nombre_completo']) for i in ids}

candidates = []
for i in range(len(ids)):
    for j in range(i+1, len(ids)):
        a, b = ids[i], ids[j]
        score = fuzz.token_sort_ratio(names_norm[a], names_norm[b])
        if score >= 85 and _typo_guard(names_norm[a], names_norm[b]):
            candidates.append(('fuzzy', score, a, b))
```

⚠ **Guarda por token diferente (OBLIGATORIA).** Un score alto sobre el nombre completo NO implica
typo: con 3 de 4 tokens idénticos, dos personas distintas superan 85. Caso real DO:
`Ramón Antonio Báez Leonardo` vs `Ramón Antonio Báez Mejía` → 87, y son **padre e hijo**. La
pregunta correcta no es "¿se parecen los nombres?" sino "**¿los tokens que DIFIEREN son el mismo
token mal escrito?**" — `Féliz`/`Félix` sí (93); `Leonardo`/`Mejía` no (22).

```python
def _typo_guard(a, b, min_tok=72):
    """True solo si los tokens no compartidos son variantes ortográficas entre sí."""
    ta, tb = a.split(), b.split()
    da, db = [t for t in ta if t not in tb], [t for t in tb if t not in ta]
    if not da and not db:
        return True                      # idénticos salvo orden
    if len(da) != len(db):
        return False                     # uno tiene tokens de más → es subset, no typo (Pasada 2/4)
    return all(max(fuzz.ratio(x, y) for y in db) >= min_tok for x in da)
```

#### Pasada 2 — Subconjunto de apellido con mismo nombre

Detecta el patrón más frecuente de variación inter-legislatura: un registro tiene los apellidos completos y otro solo el primero (o viceversa), con el mismo nombre de pila. El `token_sort_ratio` penaliza los tokens extra y puede caer bajo 85 en este caso.

```python
for i in range(len(ids)):
    for j in range(i+1, len(ids)):
        a, b = ids[i], ids[j]
        ape_a = norm(seen[a]['apellidos'])
        ape_b = norm(seen[b]['apellidos'])
        nom_a = norm(seen[a]['nombre'])
        nom_b = norm(seen[b]['nombre'])

        # Un apellido es prefijo del otro (e.g. "alegre" ⊂ "alegre sasiain")
        apellido_subset = (ape_a.startswith(ape_b + ' ') or
                           ape_b.startswith(ape_a + ' '))
        # Nombres iguales o uno es prefijo del otro ("mirian" ⊂ "mirian graciela")
        nombre_match = (nom_a == nom_b or
                        nom_a.startswith(nom_b + ' ') or
                        nom_b.startswith(nom_a + ' '))

        if apellido_subset and nombre_match:
            score = fuzz.token_sort_ratio(names_norm[a], names_norm[b])
            candidates.append(('subset_apellido', score, a, b))
```

#### Pasada 3 — Scan de vecinos tras ordenar por apellidos

Ordenar el catálogo por `norm(apellidos)` y comparar cada entrada con sus ±5 vecinas. Esto agrupa en contigüidad las variantes del mismo apellido, haciendo visibles pares que el fuzzy global no alcanza (e.g., iniciales: `Alfonso G.` / `Alfonso Gonzalez`).

```python
import re

def has_initial(token):
    return bool(re.match(r'^[a-z]\.$', token))

def initial_matches(tok_initial, tok_full):
    """'g.' matches 'gonzalez' → True"""
    return tok_full.startswith(tok_initial[0])

sorted_ids = sorted(ids, key=lambda i: norm(seen[i]['apellidos']))

WINDOW = 5
for idx, a in enumerate(sorted_ids):
    for b in sorted_ids[max(0, idx-WINDOW):idx]:
        ape_a_tokens = norm(seen[a]['apellidos']).split()
        ape_b_tokens = norm(seen[b]['apellidos']).split()
        # Si tienen igual número de tokens en apellidos y mismo primer apellido
        if not ape_a_tokens or not ape_b_tokens:
            continue
        if ape_a_tokens[0] != ape_b_tokens[0]:
            continue  # primer apellido distinto → saltar

        # Buscar iniciales expandidas en los tokens restantes
        # e.g. ape_a = ["alfonso", "g."], ape_b = ["alfonso", "gonzalez"]
        all_match = True
        for ta, tb in zip(ape_a_tokens[1:], ape_b_tokens[1:]):
            if ta == tb:
                continue
            if has_initial(ta) and initial_matches(ta, tb):
                continue
            if has_initial(tb) and initial_matches(tb, ta):
                continue
            all_match = False
            break

        nom_a = norm(seen[a]['nombre'])
        nom_b = norm(seen[b]['nombre'])
        nombre_match = (nom_a == nom_b or
                        nom_a.startswith(nom_b + ' ') or
                        nom_b.startswith(nom_a + ' '))

        if all_match and nombre_match:
            score = fuzz.token_sort_ratio(names_norm[a], names_norm[b])
            candidates.append(('initial_expand', score, a, b))

# Deduplicar pares (a,b) y (b,a)
seen_pairs = set()
final = []
for kind, score, a, b in candidates:
    key = tuple(sorted([a, b]))
    if key not in seen_pairs:
        seen_pairs.add(key)
        final.append((kind, score, a, b))
final.sort(key=lambda x: -x[1])
```

#### Pasada 3-bis — Abreviaturas y apellido de casada

Dos clases que las pasadas fuzzy/subconjunto **no pueden** ver, porque el token que difiere no es
ni un typo ni un subconjunto. Ambas detectadas en DO (2026-07) sobre un roster ya "dedupeado".

**(a) Abreviaturas.** `Betzaida Ma. Manuela Santana Sierra` = `Betzaida María Manuela Santana
Sierra` (53 intervenciones partidas en dos ids). Expande antes de comparar:

```python
ABBR = {"ma":"maria","mª":"maria","jo":"jose","fco":"francisco","fca":"francisca",
        "ant":"antonio","ml":"manuel","mnl":"manuel","gmo":"guillermo","fdo":"fernando",
        "dgo":"domingo","mgl":"miguel","rfl":"rafael","edo":"eduardo","alb":"alberto"}
```

**(b) Apellido de casada — sesga por género, así que ignorarlo daña el corpus de forma asimétrica.**
En la convención hispana una mujer aparece con sus dos apellidos de soltera en unas fuentes
(`Betzaida María Santana **Sierra**`, la del acta) y con `de {apellido del marido}` en otras
(`Betzaida María Santana **de Báez**`, la del listado oficial). **Ningún fuzzy las une**: cambia el
apellido final entero. Como las listas oficiales suelen usar la forma de casada y las actas la de
soltera, el efecto es que **las diputadas se quedan sin partido ni distrito mientras los diputados
sí los reciben**.

Firma: mismos nombres de pila + **mismo primer apellido** + mismo período + una de las dos formas
contiene ` de ` o `Vda.`. Compara por el núcleo (pila + 1er apellido), no por el nombre completo:

```python
PART = {"de","del","la","las","los","y","vda","viuda"}
nucleo = lambda s: [t for t in norm(s).split() if t not in PART]   # pila + apellidos, sin partículas
# ≥3 tokens iniciales iguales + colas distintas + marca " de "/Vda. → candidato fuerte
```

⚠ **La cédula (o DNI/identificador nacional) es el árbitro.** Si ambas entradas la traen y difieren,
**son personas distintas, sin discusión** — en DO `Rafael Antonio Mena Castro` (037-0022155-3) y
`Rafael Antonio **Reynoso** Castro` (057-0003717-8) comparten pila y último apellido y no son la
misma persona. Por eso conviene guardar la cédula en `notas` siempre que la fuente la dé (4e).

#### Pasada 4 — Subconjunto de `nombre_completo` (robusta a split malo)

⚠ Las Pasadas 2 y 3 dependen de que `nombre`/`apellidos` estén bien SEPARADOS. Cuando el roster
viene de fuentes mezcladas o se AUMENTÓ después (nuevos miembros, suplentes, scraping), esos campos
suelen estar mal divididos o vacíos y las pasadas anteriores no detectan la variante. Esta pasada
trabaja sobre el token-set del `nombre_completo` COMPLETO, sin depender del split. Caso real CO
(2026-06): "Berner León Zambrano Erazo" (CO00089) y "Berner Zambrano" (CO00090) = misma persona, no
detectada hasta esta pasada; en total 29 personas duplicadas en un roster ya "dedupeado".

```python
# token-set del nombre completo por id
tok = {i: set(norm(seen[i]['nombre_completo']).split()) for i in ids}
multi = [i for i in ids if len(tok[i]) >= 2]
for x in range(len(multi)):
    for y in range(x + 1, len(multi)):
        a, b = multi[x], multi[y]
        ta, tb = tok[a], tok[b]
        # forma corta ⊂ forma larga (subconjunto estricto) Y ≥2 tokens compartidos
        # (el ≥2 evita falsos: "Juan García" vs "Juan García López" sí; "Juan" vs "Juan Pérez" no)
        if ta != tb and (ta <= tb or tb <= ta) and len(ta & tb) >= 2:
            score = fuzz.token_set_ratio(names_norm[a], names_norm[b])
            candidates.append(('subset_nombre_completo', score, a, b))
```

**Union-find para cadenas transitivas (OBLIGATORIO).** Si A⊂B y B⊂C (p. ej. "Jorge García-Herreros"
⊂ "Jorge Alberto García-Herreros C." ⊂ ...), los tres son la MISMA persona. Agrupa los pares con
union-find antes de elegir el canónico, para no dejar fusiones a medias:

```python
parent = {i: i for i in ids}
def find(z):
    while parent[z] != z: parent[z] = parent[parent[z]]; z = parent[z]
    return z
def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb: parent[max(ra, rb, key=lambda i: int(re.sub(r'\D','',i)))] = min(ra, rb, key=lambda i: int(re.sub(r'\D','',i)))
for kind, score, a, b in final:   # solo pares confirmados "misma persona"
    union(a, b)
# grupos = componentes conexas; canónico por grupo según 5d
```

#### Nota — re-ejecutar la dedup tras AUMENTAR el roster

La deduplicación NO es solo del build inicial: cada vez que se añaden miembros (suplentes, entrantes
a media legislatura, scraping de una fuente nueva), hay que **re-correr el Paso 5 completo** sobre el
roster resultante y **re-aplicar el id canónico a `matching_table.csv`** (5f). Saltarse esto es la
causa #1 de duplicados de persona que fragmentan el match (1 persona → varios id_dep → intervenciones
repartidas). Verifica al final: 0 nombres `nombre_completo` normalizados con >1 id_dep.

### 5c. Clasificar cada par encontrado

Para cada par con score >= 85, determina si es la misma persona o no:

**Indicadores de MISMA persona** (merge):
- Misma inicial o mismo nombre de pila
- Apellido principal idéntico o con variante ortográfica de 1-2 caracteres
- El segundo apellido de una entrada es subconjunto del apellido de la otra (`Masi` / `Masi Jara`)
- Los dos apellidos aparecen en ambas entradas pero en orden distinto
- Uno tiene inicial intermedia espuria (p. ej. `Sanabria P., Eugenio` / `Sanabria, Eugenio`)

**Indicadores de PERSONAS DISTINTAS** (no merge):
- Nombres de pila distintos (e.g., `Silvio` vs `Luis`)
- Segundo apellido completamente distinto con caracteres diferentes (e.g., `Samaniego Alemán` vs `Samaniego Álvarez`): puede ser padre/hijo o personas sin relación
- Score exactamente en el umbral (85-87) con sospecha de coincidencia casual: revisar el contexto (legislaturas, partidos, circunscripciones)

Cuando un par es ambiguo, presenta ambas entradas al usuario con sus campos completos (partido, circunscripción, fechas) y pide confirmación antes de fusionar.

**Asimetría del error (regla de decisión ante la duda).** Los dos errores NO cuestan lo mismo:
fusionar mal dos personas **corrompe la atribución de cientos de intervenciones** y es invisible
aguas abajo; dejar sin fusionar un fantasma de `v=1` cuesta **una** intervención y queda visible
como `unmatched`. Ante duda genuina: **no fusionar**, y registrar el par en el informe.

### 5c-bis. Fantasmas de parseo y entidades contaminadas

El encuadre "misma persona con dos id" no cubre dos clases que el skill trataba como personas. En
DO eran **el 46% del período 1998-2002**: no sobraban diputados, sobraba basura.

**(a) Fantasmas — entradas que no son una persona.** Firma: `v≤2` + comparte nombre de pila *y*
primer apellido con una entrada de peso alto, pero el apellido final es el del **vecino en el pase
de lista** (`Bidó M Arnaud` ⇐ *Bisonó Vda. Arnaud*; `Castillo Semán` ⇐ *Pelegrín Castillo Semán*).
Las 4 pasadas no los ven porque el token que difiere no es un typo ni un subconjunto.

```python
# candidato a fantasma: peso ínfimo + núcleo compartido con un pesado + cola divergente
if w[a] <= 2 and w[b] >= 10 and nom_a == nom_b and ape_a.split()[0] == ape_b.split()[0]:
    absorber_en_b(a)      # NO es un merge entre iguales: 'a' desaparece, 'b' manda
```

El trato es **absorción**, no fusión: la grafía, el partido y el distrito salen siempre de la
entrada pesada (5e). Si el fantasma tiene `v=0` y ninguna fuente oficial lo respalda, se elimina.

**(b) Entidades contaminadas — un id que son DOS personas.** La operación inversa, que el skill no
contemplaba en absoluto. Firma: un `id_dep` cuyo `nombre_completo` contiene **dos núcleos
onomásticos plausibles** *y* cuyos períodos son **discontinuos**. Caso real DO0133
`Clodomiro de Jesús Chá Dionicio de la Rosa` = *Chávez Tineo* (1998) + *Dionisio de la Rosa*
(2016, 2020). Un merge nunca lo arregla: hay que **partir** el id y reasignar las filas por fecha.

Detección barata sobre todo el roster:
```python
# >5 tokens Y un hueco de período ≥ 2 legislaturas bajo el mismo id → inspeccionar
if len(nombre.split()) > 5 and hay_hueco_de_periodos(id_dep):
    flag_para_split(id_dep)
```

### 5d. Elegir id_dep canónico por grupo

Criterios de prioridad (en orden):
1. Tiene URL en campo `notas` (indica registro en sistema oficial)
2. Tiene partido conocido (no vacío, no "NO ESPECIFICADO")
3. Menor valor **numérico** del sufijo del id (registro más antiguo del sistema fuente)
   - Extraer número: `int(re.sub(r'\D', '', id_dep))` para comparar
   - Ej.: PY14 < PY84 < PY100045 < PY101372

### 5e. Elegir nombre_completo / nombre / apellidos canónicos

⚠ **La grafía canónica es la de la variante con MÁS EVIDENCIA, no la más larga.** Regla anterior
("más completo / más largo") — era incorrecta y producía el peor resultado posible: elegía
sistemáticamente el fantasma de parseo, porque los nombres contaminados son SIEMPRE más largos que
el real (arrastran el apellido del vecino). Caso real DO (2026-07): el grupo
{`de León de León` (v=41), `Pedro Antonio de León de Le Santana` (v=1)} → la regla vieja canonizaba
la basura y corrompía las 41 filas buenas.

Preferencia en orden:
1. **Mayor peso de evidencia** (`visto_en:N`, 4e): la grafía que aparece en más sesiones es la
   real; las de `v≤2` son casi siempre misparses. Es el criterio DOMINANTE.
2. **Mejor tipografía**: mixed-case con acentos > mixed-case sin acentos > ALL_CAPS
3. **Más completo** solo para desempatar entre variantes de peso comparable (`Castiglioni Soria`
   > `Castiglioni` si ambas tienen v similar)

Si un campo `nombre` o `apellidos` parece contener tokens que pertenecen al otro campo (p. ej. un apellido dentro de `nombre`), reconstruir correctamente antes de asignar.

### 5f. Aplicar y registrar

- Reasignar `id_dep` canónico en **todas** las filas del grupo (incluidas las de otras legislaturas)
- En las filas que eran aliases: añadir `alias_de:{old_id}` a `notas`
- En la fila/s con el id canónico: añadir `aliases:{id1},{id2}` a `notas`
- Actualizar `nombre_completo`, `nombre`, `apellidos` a la versión canónica en todo el grupo
- Actualizar `matching_table.csv` si existe: redirigir todos los `id_dep` alias al canónico

### 5g. Re-escanear tras cada pasada

Después de aplicar cada ronda de fusiones, vuelve a ejecutar el escaneo fuzzy. Las fusiones pueden revelar nuevas coincidencias que antes estaban enmascaradas por variantes intermedias. Repite hasta que no queden pares con score >= 85 (excepto los explícitamente excluidos como personas distintas).

### 5h. Reportar duplicados

```
Deduplicación:
  IDs únicos antes:        {N_antes}
  IDs únicos después:      {N_despues}
  Filas remapeadas:        {N_remapeadas}
  Grupos deduplicados:     {N_grupos}
    - Mismo partido/distrito: {N1}
    - Mismo partido, dist. distinto: {N2}
    - Partido distinto (cambio de partido): {N3}
  Pares excluidos (distintas personas): {N_excluidos}
```

Si `N_grupos / N_antes > 0.10` (más del 10% del catálogo son duplicados): emite advertencia visible — puede indicar datos fuente de baja calidad o múltiples fuentes sin reconciliar.

### 5i. Validación contra la plantilla de escaños (OBLIGATORIA)

El control de calidad más barato y más potente del skill: **una cámara tiene un número conocido de
escaños**. Contrasta personas-por-período contra ese número. Un exceso moderado es normal
(suplentes, sustituciones a media legislatura); un exceso grande es **basura de parseo**, y el peso
de evidencia lo confirma en la misma tabla.

Salida real de DO (2026-07), tras dedup y tras integrar los listados oficiales:

```
período  roster  escaños  exceso   de ellos v<=2
1998        276      149    +127             130   ← ¡el exceso ES la clase fantasma!
2002        155      150      +5               6
2006        183      178      +5               6
2010        196      183     +13               4
2016        199      190      +9               2
2020        198      190      +8               0
2024        190      190      +0               1
```

La correspondencia +127 exceso / 130 entradas con `v≤2` no es casual: **el exceso y los fantasmas
son el mismo conjunto**. Un período así no necesita más dedup fuzzy — necesita arreglar el parser
de su pase de lista (en DO, 1998 venía de un OCR peor).

Criterio: `exceso > 0.15 × escaños` → **FLAG**, con la columna `v≤2` como diagnóstico. Guarda los
escaños por período en `country_config/{iso2}.yaml` (`deputies.seats_by_period`); son dato público
y estable.

### 5j. El match es un DETECTOR de duplicados — iterar

`diaries-deputies` y `diaries-match` no son secuenciales, son un **bucle**. Los casos `ambiguous`
del match (un `speaker_raw` que empata con 2+ id) son en su mayoría duplicados que la dedup no vio,
porque el match compara contra evidencia que la dedup no tiene: la grafía real usada en las actas.
En DO destapó la escisión `Yuderka de la Rosa` / `Yuderka Ivelisse de la Rosa` y la contaminación
`Alfredo Pache Cristian Paredes Aponte`.

Tras el primer `diaries-match`: revisa sus `ambiguous`, aplica lo que corresponda al roster, y
**vuelve a correr Paso 5 + match**. Converge en 2 iteraciones.

⚠ Al re-correr el match, **la revisión humana previa es la autoridad máxima**: reinyecta las filas
con `match_method` ∈ {`manual`, `NOT_SPEAKER`, `role`} de la `matching_table.csv` anterior ANTES de
recalcular, o el reprocesado destruye horas de trabajo del usuario.

### 5k. Propagación entre períodos (rellenar huecos de partido/distrito)

Una vez deduplicado, un mismo `id_dep` con N filas permite completar los huecos de unas filas con
los datos de otras. Es gratis y rinde mucho, pero tiene dos trampas:

**Partido — propaga SOLO si es unánime.** Los cambios de partido son frecuentes y reales. Propagar
"el más común" inventa historia política. Regla: si las filas conocidas de ese `id_dep` tienen
**un único** valor, propágalo marcando `partido:inferido-otro-periodo`; si hay dos o más, deja
vacío. Un dato duro posterior (`camara:oficial`, `acta:bloque`) siempre lo pisa (precedencia, 4e).

**Distrito — propaga a nivel de PROVINCIA, no de cadena literal.** La circunscripción se renumera
entre períodos y el mismo distrito aparece como `Santiago C2` y `Santiago`, lo que bloquea la
comparación exacta. Normaliza quitando el sufijo antes de comparar — en DO liberó 37 filas que la
comparación literal daba por incompatibles:

```python
prov = re.sub(r'\s+C\d+$', '', circunscripcion).strip()   # "Santiago C2" → "Santiago"
```

### 5l. `partido` es el BLOQUE, no la alianza electoral

Trampa de semántica, no de código, y afecta a la validez del corpus. Los registros electorales
(JCE en DO, equivalentes en otros países) consignan el partido **que encabezaba la alianza por la
que se ganó el escaño**; las actas consignan el **bloque partidario** al que el diputado pertenece
y con el que vota. No coinciden. Máximo Castro figura como PLD/PRM/PRD según el año en el registro
electoral, y es **PRSC durante 38 años** en las actas.

Para un corpus de comportamiento parlamentario el dato correcto es el **bloque**: es el que explica
el voto y la intervención. Si ambas fuentes están disponibles, `acta:bloque` gana al registro
electoral (precedencia, 4e), y se anota `acta:bloque-vs-alianza` para dejar rastro de la
discrepancia.

### Nota sobre conversión ALL_CAPS

Si el archivo externo tiene nombres en ALL_CAPS, conviértelos a mixed-case antes de la deduplicación. Las partículas (`de`, `del`, `de la`, `de los`, `de las`, `y`, `e`) deben quedar en minúscula **excepto** si son la primera palabra del campo. Las iniciales abreviadas (`A.`, `J.`) se capitalizan normalmente.

## Paso 6 — Derivar `sex` y exportar el padrón publicable

`sex` es una variable **derivada**, y su procedencia se declara en `sex_source` para que quien
use el corpus pueda descartar los niveles menos precisos. **No se importa ninguna lista externa
de nombres**: el diccionario se aprende del propio corpus.

```bash
python3 ~/.claude/skills/diaries-lib/lib/utils/derive_sex.py --country {iso2} --apply       # cascada de 6 niveles
python3 ~/.claude/skills/diaries-lib/lib/utils/sex_to_roster.py --country {iso2} --apply    # escribe sex + sex_source en deputies.csv
python3 ~/.claude/skills/diaries-lib/lib/utils/export_sex_review.py --country {iso2} --apply  # Numbers para revisión humana
python3 ~/.claude/skills/diaries-lib/lib/utils/import_sex_review.py --country {iso2} --file … --apply
python3 ~/.claude/skills/diaries-lib/lib/utils/sex_to_matrix.py --country {iso2} --apply    # añade la columna a la matriz
```

`derive_sex.py` y `sex_to_roster.py` aceptan `--country` de verdad y conocen EC (arreglado
2026-08-23). ⚠ **Pero ambos leen `source/{c}/standardize/{C}_interventions.csv`**: en un
reproceso, en esta etapa ese CSV es todavía el del corpus VIEJO. La cascada se corre **en su
momento — tras `diaries-standardize`** — o, si se corre aquí, aceptando explícitamente esa
fuente como aproximación y dejándolo anotado.

**Orden de autoridad de las fuentes**, de mayor a menor:

| `sex_source` | qué es | exactitud medida |
|---|---|---|
| `manual` | corrección humana — **nunca se recalcula** | — |
| `official_registry` | registro oficial de la cámara | 99,69% |
| `roster` | el padrón lo trae en `notas` | — |
| `given_name` | diccionario de nombres de pila aprendido del corpus | 99,48% |
| `given_name_morph` | terminación del primer nombre (-a → F, -o → M) | 98,42% |
| `honorific` | tratamiento junto al nombre en el acta | 96,57% |
| `given_name_rare` | el diccionario, nombre visto una sola vez | 94,31% |

⚠ **Buscar el registro oficial ANTES de derivar.** Siete países lo tenían ya declarado en
`source/{iso2}/deputies/`, junto al padrón pero sin ser el padrón, y en cuatro formatos
distintos: CSV, XML, XLSX y `.numbers`. Derivar sin mirar fue el error más caro de esta fase.

⚠ **Medir la cobertura POR SEXO, no en agregado.** La primera versión tenía **50,0% en mujeres
frente a 82,3% en hombres** y en el agregado (75,9%) no se veía: los casos de partida son 80%
hombres, así que los nombres masculinos alcanzan el mínimo de apariciones y los femeninos no.

⚠ **El honorífico solo cuenta junto a un nombre propio.** Sobre un cargo pelado no dice nada de
la persona: en ES, `VICEPRESIDENTA` estaba asignado a *Gómez Llorente, Luis*.

**Exactitud del conjunto, medida contra revisión humana exhaustiva de once padrones (38.372
filas): 98,98%.** Por sexo real: M 99,54%, F 97,43% — una mujer tiene 5,5 veces más
probabilidad de quedar mal clasificada, y **eso se declara** en la documentación del corpus.

### El padrón publicable `{ISO2}_deputies.csv`

**Ruta canónica: `source/{iso2}/standardize/{ISO2}_deputies.csv`** — se publica junto a la
matriz, unible por `id_dep` (+ `legislature`), y es el archivo al que remite el
`data_dictionary` del corpus («the companion roster file»).

Columnas núcleo: `id_dep, speaker_name, first_name, last_name, sex, sex_source, party,
parliamentary_group, district, legislature, start_date, end_date, notes`.

Hereda del interno la forma larga del Paso 4-bis: **una fila por `(id_dep, legislature)` y
`id_dep` NO único**. Antes de publicar, las tres aserciones del Paso 4-bis otra vez, ahora sobre
los nombres en inglés, y una más de integridad contra la matriz:

```python
pares_matriz = set(zip(m.loc[m.id_dep != "", "id_dep"], m.loc[m.id_dep != "", "legislature"]))
huerfanos    = pares_matriz - set(zip(d.id_dep, d.legislature))
```

Los huérfanos **no se corrigen ni se apartan**: son diputados a los que el acta registra
hablando en una legislatura que el padrón no les asigna, y el acta manda —
[[feedback_primacia_del_diario]]. Se declaran en `process_report.md` como medida de
completitud del padrón. En GT son 57 pares y 1.286 filas (0,55% de las vinculadas), siempre en
una legislatura **contigua** a la que el padrón asigna, lo que apunta a suplencias y tomas de
posesión a media legislatura.

## Paso 7 — Calcular confianza

```
confianza = 1.0 - (clustered_ambiguous / max(total_unique, 1))
```

donde `clustered_ambiguous` = número de clústeres con 4+ nombres que requirieron juicio LLM (Ruta B), o número de grupos con partido distinto en la deduplicación (Ruta A).

## Paso 8 — Actualizar estado

```bash
python ~/.claude/skills/diaries-lib/lib/utils/update_state.py \
  --country {iso2} --skill diaries-deputies --session "_country" \
  --status complete --confidence {confianza} \
  --output "source/{iso2}/deputies/deputies.csv"
```

Si `confianza < 0.85`: usa `--status flag`.

## Paso 9 — Limpiar y resumir

Elimina archivos temporales:
```bash
rm -f source/{iso2}/.tmp_speakers.json source/{iso2}/.tmp_fuzzy.json
```

Imprime resumen:
```
diaries-deputies — {iso2}
Diputados en deputies/deputies.csv: {N_total}
  Nuevos registros:    {N_nuevos}
  De archivo externo:  {N_externos}  (o "Construido desde speakers")
  Clústeres resueltos: {N_clusters}
  Ambiguos (FLAG):     {N_ambiguos}
Confianza: {confianza:.2f}
```

