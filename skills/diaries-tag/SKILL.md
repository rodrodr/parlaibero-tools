---
name: diaries-tag
description: "Etiqueta oradores en texto corregido: pase regex determinista + resolución LLM de spans sospechosos. Skill crítico con umbrales más bajos."
allowed-tools: [Read, Write, Edit, Bash]
---

Argumentos: `--country {iso2}` + uno de `--session YYYY-MM-DD` | `--batch YYYY-MM` | `--all` + opcionales `--force`, `--dry-run`


## Paso 0 — DESCUBRIR las formas de marcador (OBLIGATORIO, antes de escribir un solo patrón)

```bash
python3 ~/.claude/skills/diaries-lib/lib/utils/discover_speaker_patterns.py --country {iso2}
```

⚠⚠ **No se adivina el vocabulario. Nunca.** El método de proponer una lista de palabras de rol
—DIPUTADO, SEÑOR, PRESIDENTE— y contar cuántas veces sale cada una **ha fallado tres veces
seguidas**, siempre por lo mismo: la forma real del país no estaba en la lista adivinada.

| | qué se perdió |
|---|---|
| **SV** | Se muestrearon 40 archivos, todos de 2018+, y se perdió `REP. NOMBRE:` de 2014 — **un año entero sin etiquetar**. |
| **GT** | La lista no incluía `EL R.` (*Representante*), la forma **dominante**: 212.082 apariciones. El sondeo devolvió 14.255 marcadores para un corpus de 251.777 filas, y llevó a concluir **en falso** que los PDF no marcaban oradores. |
| **GT (otra vez)** | Hallado `EL R.`, faltaba **`LA R.`**: 28.805, el 13,6 % del masculino. Un patrón solo masculino **borra a las mujeres que presiden y ejercen la secretaría**. |

La utilidad busca encabezamientos **por su FORMA** —línea que empieza en mayúscula, corta,
terminada en `:` o `.` y seguida de prosa— y los agrupa por esqueleto, sustituyendo los nombres
por un hueco. **Lo que domina el ranking ES la convención del país**, se llame como se llame.
En GT, `EL R.` y `LA R.` salen 1.º y 6.º sin haber asumido nada.

Trae además dos comprobaciones que son justo donde fallaba el ojo:

- **Pareja de género en cada forma** (EL/LA, DIPUTADO/DIPUTADA, PRESIDENTE/PRESIDENTA,
  SECRETARIO/SECRETARIA, PRIMER/PRIMERA…). Si la femenina no aparece o cae por debajo del 2 %,
  avisa. **Es el error que más daño hace y el más fácil de no ver.**
- **Forma dominante POR AÑO**, porque las cámaras cambian de convención con la época y una
  muestra de conveniencia lo esconde.

**Todo lo hallado se declara en `country_config/{iso2}.yaml`** — `speaker_tag_patterns`,
`speaker_prefix_strip` y, si el marcador se parte en dos líneas, `correct.marker_reassembly`.
Cada país tiene su convención y **tiene que quedar escrita en su config**, no redescubrirse.

⚠ **PUNTO DE PARTIDA del descubrimiento: `docs/_metodologia/FASE_C_MARCADORES_POR_PAIS.md`** (en el
proyecto de datos, carpeta `docs/_metodologia/`), no una cita narrativa. Las formas concretas por país ya están PAGADAS ahí —
terminadores, clases de marcador y variantes OCR de la campaña Fase C—: el descubrimiento las
CONFIRMA sobre el corpus vigente y las amplía, no las reinventa desde cero. ⚠ Con una salvedad:
su **§0.6 (convención `9000N` para el Prolegomena duplicado) está SUPERADO** por
`desdoblar_prolegomena_duplicado.py` (decisión tr-0084) — no copiarlo.

### Semilla de TERMINADORES por país (declarada — ADEMÁS del descubrimiento, no en su lugar)

El terminador es la mitad del marcador y el descubrimiento por forma puede infraponderarlo cuando
el OCR lo degrada. Estos ya están verificados y entran como semilla declarada en
`speaker_tag_patterns`:

| País | Terminador | Nota |
|---|---|---|
| ES · GT · EC | `:` | |
| UY | `.—` | ⚠ ignorarlo enterró **7.851 marcadores** |
| EC | también `.-` | grafía OCR del `.—` |
| PT | `—` standalone | el em-dash solo, sin punto |

Y la tolerancia OCR que a la clase del honorífico casi siempre le falta:

- `se\S{1,2}or` — la ñ rota: `seflor`, `sefior`, `senor`, `sedor`…
- prefijo `EL` → `FL` (EC)
- `H.D.` → `HE.` (PA)

⚠ **Comprobar la cobertura antes de dar el patrón por bueno**: el total de marcadores hallados
debe cubrir una fracción razonable de las filas esperadas. En GT, 231.710 marcadores para
251.777 filas es el **92,0 %**; los 14.255 del sondeo adivinado eran el 5,7 % y eso era la
señal de que el patrón estaba mal, no los datos.

### Paso 0-bis — Los que FALLAN se prueban contra las cadenas REALES, no contra la intuición

Cuando queden marcadores sin etiquetar, **no razones sobre la causa: extrae las cadenas y mide.**

```python
# 1) saca a un fichero cada marcador que quedó DENTRO del text de la matriz
RX = re.compile(r'(?m)^((?:EL|LA)\s+(?:R\.|SEÑOR[A]?)\s[^\n]{2,80}?:)')   # forma laxa del país
casos = [m.group(1) for t in d.text for m in RX.finditer(t)]
# 2) cuenta cuántas casa cada patrón CANDIDATO — segundos, sin reprocesar nada
ok = sum(1 for c in casos if any(r.match(c) for r in candidatos))
# 3) lista las que siguen fallando, agrupadas por frecuencia
Counter(c for c in casos if not any(r.match(c) for r in candidatos)).most_common(8)
```

En GT esto ahorró dos reprocesos completos: la causa se diagnosticó mal **dos veces** —primero
«sangría al inicio de línea» (**0 casos** al medirlo), después «ruido de OCR en el cargo» (76 %
según un clasificador que solo miraba si aparecía la palabra `PRESIDENTE`)—. La causa real era
**el guion del apellido compuesto**, ausente de la clase `[A-ZÁÉÍÓÚÑÜ\s,.]`: `TARACENA DÍAZ-SOL`,
presidente del pleno, perdía **4.888 marcadores él solo**; con `LINARES-BELTRANENA`,
`RODRÍGUEZ-AZPURU` y `DÍAZ-DURÁN`, 4.979 de 5.307. El paso 3 lo enseña en la primera línea.

Tres cosas que la clase del nombre casi siempre necesita y casi nunca lleva:

| | |
|---|---|
| **guion** `‐-―-` | apellidos compuestos — la causa nº 1 |
| **coma** dentro del cargo | `MINISTRO DE AGRICULTURA, GANADERIA Y ALIMENTACION, LICENCIADO …` (1.257 en GT) |
| **sufijo de cargo tolerante** | `EN\s+FUNCIONES\s+D[^:\n]{0,24}` absorbe `PR3ESIDENTE`, `PRESDIENTE`, `RESIDENTE` |

Y **control obligatorio antes de aplicar**: imprime el nombre capturado para media docena de
casos —uno normal, uno con guion, uno corrompido por OCR y **uno femenino**— y compruébalos a
ojo. Un patrón que sube la cobertura pero captura mal el nombre empeora la vinculación.


## Paso 0-config — Leer configuración del país

Lee `country_config/{iso2}.yaml`.

Extrae:
- `speaker_tag_patterns` (lista de regex ESTRICTAS — nivel 1)
- `speaker_loose_pattern` (regex LAXA con grupo `name` — nivel 2 probabilístico)
- `speaker_score_threshold` (default 0.60) y `speaker_borderline_threshold` (default 0.40)
- `speaker_prefix_strip` (lista de prefijos a eliminar)
- `president_tag` (string o regex que identifica al presidente)
- Umbrales específicos del skill si existen en `thresholds.diaries-tag`:
  - `threshold_auto` (default para este skill: **0.80**)
  - `threshold_flag` (default para este skill: **0.60**)

Usa los umbrales de `thresholds.diaries-tag` si están definidos; si no, usa los valores por defecto del skill (0.80 / 0.60), NO los globales.

### Criterio de detección de oradores — DOS NIVELES (general para TODOS los países)

`tag_text.py` aplica un criterio laxo obligatorio en todos los países (OCR/escaneos producen
terminadores inconsistentes):
- **NIVEL 1 ESTRICTO** (`speaker_tag_patterns`): marcador canónico. La clase de guion DEBE
  aceptar `[-–—]` (hyphen, en-dash, em-dash): el OCR emite EM-DASH "—", el embebido usa "-".
- **NIVEL 2 PROBABILÍSTICO** (`speaker_loose_pattern`): líneas con terminador irregular
  (`.` sin guion, `—` sin punto, `:`, o ninguno). Scorer universal (terminador, texto siguiente,
  paréntesis, plausibilidad del nombre, match con diputados vía `--deputies`); penaliza vocativos.
  score ≥ umbral → etiqueta (recupera ~5% de marcadores irregulares); intermedios → caso límite (FLAG).
El honorífico en MAYÚSCULA a inicio de línea discrimina del "señor" minúscula del texto corrido.
También preserva el texto de intervención en la misma línea que el marcador.

### Las CINCO clases y su tratamiento

Todo lo que PARECE un marcador cae en una de cinco clases, y cada una tiene tratamiento propio.
Confundirlas produce los falsos positivos y negativos más caros del pipeline:

| Clase | Firma | Tratamiento |
|---|---|---|
| **FORMAL** | núcleo VERSAL + terminador del país (`:`, `.—`…) | **abre turno** — la única clase que produce `<int>` |
| **APARTE** | interjección entre paréntesis DENTRO del turno de otro | NO abre turno: permanece en el texto del anfitrión. El criterio para separarlo como turno propio es **si hay TEXTO delante**, no una distancia (BR: 18.718 separados así — [[feedback_apartes]]) |
| **MENCIÓN** | Titlecase + verbo en el discurso («el señor García afirma…») | ignorar. El discriminador frente al turno real es el **núcleo VERSAL** del marcador |
| **VOTO nominal** | «Por el señor Diputado X», listas de votación | NO abre turno. El patrón por país se registra en `tag.vote_patterns` del config y se **EXCLUYE** del tagging; `diaries-matrix` declara esas filas `dm_speech = 0` |
| **NARRATIVA** | el orador va en una CLÁUSULA en prosa, no en un núcleo versal | modo propio (`tagging_style: narrative`) — subsección siguiente |

### Criterio de detección — QUINTA CLASE: estilo NARRATIVO ⚠

Algunas actas **no usan marcador directo**: la relatora introduce cada intervención en PROSA y el
orador se declara en una frase, no en un `NOMBRE:`. Son turnos reales, pero de otra clase. **Frecuente
en DO y CO.** Dos variantes:

- **DO — narración con cita**: «En la prosecución del debate, el Diputado X hizo la siguiente
  exposición: "DISCURSO".» La intervención abre con `: "` y cierra con `"`; el orador se resuelve HACIA
  ATRÁS en la cláusula introductoria. Motor ya existente: **`tag_narrative.py`**, activado con
  `tagging_style: narrative` en el `country_config`.
- **CO — `speaker_raw` que es una FRASE**: «El señor Presidente somete a consideración…», «La
  Secretaría General informa, doctor Jesús Alfonso Rodríguez C.» (29.608 filas). El etiquetado tomó la
  narración entera por orador. Se **NORMALIZA a la persona** con **`co_normalizar_orador_narrativo.py`**;
  el `speaker_raw` final es el nombre, no la frase.

⚠ **Descubre el estilo por país** (Paso 0b): si el acta narra en vez de marcar, el modo es narrativo y
`speaker_tag_patterns` NO basta. La quinta clase se distingue de las otras cuatro (formal · aparte ·
mención · voto) en que el orador está en una CLÁUSULA, no en un núcleo versal. Ver
[[feedback_co_orador_narrativo]] y `docs/_metodologia/FASE_C_MARCADORES_POR_PAIS.md`.

### Paso 0b — ANÁLISIS PROFUNDO de variantes de marcador (OBLIGATORIO la primera vez por país)

El honorífico y el terminador son ESPECÍFICOS de cada país y cambian por OCR, era y taquígrafo.
NO se asumen: se descubren empíricamente ANTES de tagear:

```bash
python ~/.claude/skills/diaries-lib/lib/utils/analyze_speaker_markers.py --country {iso2} --source both
```

Reporta con frecuencias y ejemplos reales: honoríficos presentes; variantes de género
(SEÑOR/SEÑORA, DIPUTADO/DIPUTADA, avisa si falta un género); distribución real de terminadores;
y ERRORES de OCR/taquígrafo (honoríficos degradados a distancia ≤2 de uno común — ej. UY:
`SEROR`≈SEÑOR, `SEÑORE`≈SEÑORA, `SERÓN`), que se pierden si no se normalizan.

Usa la salida para (1) calibrar `speaker_tag_patterns` y `speaker_loose_pattern`, y (2) añadir
normalización de las variantes de error a `diaries-correct` (`/diaries-feedback --type rule`)
ANTES de tagear. Repetir si el país tiene varias eras/fuentes con marcadores distintos.

⚠ **Si el marcador lleva ARTÍCULO CON GÉNERO, conservalo en `speaker_raw`.** Cuando las actas
escriben `EL H. APELLIDO` / `LA H. APELLIDO` (o `EL SEÑOR` / `LA SEÑORA`), el artículo es un
**discriminador de identidad**, no decoración: distingue a dos personas que comparten apellido y
que ninguna otra señal separa. Captúralo dentro del grupo de `speaker_tag_patterns` en vez de
consumirlo en el prefijo. Es gratis en el momento del tagging e **irrecuperable después**.

Caso real EC (2026-07): `EL H. MEJÍA VILLA` y `LA H. MEJÍA VILLA` son **María Floripe** y
**Francisco Antonio Mejía Villa**, hermanos, ambos por Esmeraldas y en el **mismo período**
1984-1986 — ni la ventana de mandato ni la circunscripción los separan. El patrón capturaba solo
el apellido, así que **465 intervenciones quedaron fusionadas bajo una sola grafía**. El artículo
estaba en `corrected/` (286 `EL` vs 215 `LA` en 146 sesiones): la señal existía y el tagging la
destruyó. En `diaries-match` solo se recuperó el 60% a posteriori, atribuyendo por fecha las
sesiones donde el acta usa un único artículo (101 overrides); las sesiones que usan **ambos**
artículos son irrecuperables sin realinear intervención a intervención.

Prueba de si te afecta, sobre `corrected/` y ANTES de tagear:

```bash
python3 -c "
import glob,re,collections
ROL=re.compile(r'(?i)presid|secretar|prosecret|relator|vicepres')   # los roles NO son personas
pat=re.compile(r'(?im)^\s*(EL|LA)\s+(?:H\.?|SE[NÑ]OR[A]?|DIPUTAD[OA])\s+([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ ]{3,30}?)\s*[:.\-]')
g=collections.defaultdict(collections.Counter)
for f in glob.glob('source/{iso2}/corrected/*.txt'):
    for art,ape in pat.findall(open(f,encoding='utf-8',errors='replace').read()):
        k=' '.join(ape.split())
        if not ROL.search(k): g[k][art.upper()]+=1
amb=[]
for k,c in g.items():
    if len(c)<2: continue
    n=sum(c.values()); mn=min(c.values())
    if mn>=5 and mn/n>=0.05: amb.append((n,k,dict(c),mn/n))   # minoría sustancial, no ruido OCR
amb.sort(reverse=True)
print(f'apellidos con AMBOS artículos de forma sustancial: {len(amb)}')
for n,k,c,r in amb: print(f'  {n:>6}  {k:<26} {str(c):<26} minoría {r:.0%}')"
```

⚠ **Los dos filtros del guion son imprescindibles, no cosmética.** Sin ellos la sonda es inútil:
en EC devolvía **192 apellidos** dominados por `PRESIDENTE` (383.177 `EL` / 134 `LA`), donde esos
134 son erratas de OCR y no una segunda persona. Excluyendo el vocabulario de rol y exigiendo que
la minoría llegue a ≥5 apariciones y ≥5% del total, la lista baja a **13 casos** y los de minoría
alta son los reales: `MEJÍA VILLA` 42%, `SAQUICELA TOLEDO` 47%, `CHAUVÍN HIDALGO` 45%,
`GUTIÉRREZ BORBÚA` 26%, `BUCARAM ORTIZ` 14%.

Cuanto más equilibrado el reparto, más seguro es que son **dos personas fusionadas**; una minoría
del 5-9% suele ser ruido de OCR. Si la lista no está vacía, ajusta `speaker_tag_patterns` para
incluir el artículo antes de seguir. Precedente relacionado: en CR ignorar el género del rol
produjo el bug de `PRESIDENTA` (22.979 filas atribuidas mal).

---

### Paso 0b-bis — PREREQUISITO: el corpus tiene que estar YA deduplicado

```bash
ls source/{iso2}/meta/*.json >/dev/null 2>&1 && echo 'meta OK' || echo '⚠ ejecuta /diaries-meta primero'
test -d source/{iso2}/_quarantine_duplicates && echo 'dedupe ejecutado' || echo '⚠ ejecuta /diaries-dedupe primero'
```

El inventario del Paso 0c rankea las formas de marcador por frecuencia sobre TODO el corpus. Si
hay sesiones duplicadas, sus formas se cuentan dos veces y el ranking —que es el que decide qué
clases de marcador merecen entrar al léxico— sale sesgado. Deduplicar después no lo arregla:
para entonces la calibración ya se hizo sobre datos inflados. Ver `diaries-dedupe`.

Si el país trae **pase de lista nominal** en las actas, construye además el padrón antes de
tagear (`diaries-deputies` Paso 4a-pre, que solo necesita `corrected/`) y pásalo con
`--deputies`: mejora el scoring del nivel 2 probabilístico.

### Paso 0c — INVENTARIO ESTRUCTURAL EXHAUSTIVO de marcadores (OBLIGATORIO — el gate real)

⚠ **Lección PA 2026-07 (y patrón repetido en todos los países): el tagging y verify_tagging
comparten el mismo LÉXICO de honoríficos → una CLASE de marcador ausente del config es
INVISIBLE para ambos.** En PA, verify reportaba 0 residuales mientras **92.757 marcadores**
quedaban sin etiquetar (su texto contaminando la intervención anterior): SUBSECRETARIO/RELATOR
nunca estuvieron en el léxico (~47K), la mesa cambió de convención en 2016 a "—NOMBRE, ROL" sin
honorífico (~121K), B.L.←H.L., -HO./-He.←H.D., L1CDO←LIC., "PRES IDENTE" partido, nombre+rol
>70 chars (tope de longitud), S.E. ministros, LICENCIADO deletreado…

El anti-doto es el **inventario por FORMA estructural** (independiente del léxico), ANTES de
tagear el corpus completo y DESPUÉS como gate. Detector: línea corta (≤90) no etiquetada que
(a) empieza con guion [-–—] y tiene ratio de mayúsculas ≥0.5 entre letras, o (b) termina en ':'
con ratio ≥0.6. Clusteriza por firma (roles/honoríficos literales, nombres→N) y ranquea:

```python
import re, unicodedata
from pathlib import Path
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
def scan(p):
    out=[]
    for line in p.read_text(errors="replace").splitlines():
        ls=line.strip()
        if not ls or ls.startswith("<int") or len(ls)>90: continue
        L=[c for c in ls if c.isalpha()]
        if len(L)<4: continue
        u=sum(1 for c in L if c.isupper())/len(L)
        if not ((re.match(r"^[-–—]\s*\S",ls) and u>=0.5) or (ls.endswith(":") and u>=0.6)): continue
        out.append(ls[:75])
    return out
files=sorted(Path(f"source/{iso2}/tagged").glob("*.txt"))   # o corrected/ antes del 1er tag
with ThreadPoolExecutor(max_workers=12) as ex:
    allc=[x for lst in ex.map(scan,files) for x in lst]
for s,c in Counter(allc).most_common(50): print(f"{c:>6}  {s}")
```

**Procedimiento:** (1) corre el inventario sobre `corrected/` ANTES del primer tagging masivo;
(2) cubre TODAS las clases del top con patrones/normalizaciones (ver taxonomía abajo);
(3) re-corre tras tagear sobre `tagged/`: el residuo aceptable es SOLO estructura documental
(RESUELVE:, CONSIDERANDO:, HORA DE INICIO:, cabeceras de asistencia PRESENTES:/AUSENTES:) —
cualquier clase con honorífico/rol/nombre+cargo en el top ES un fallo a cubrir. Itera hasta ahí.

**Taxonomía de clases (verificadas en PA/UY/CR — búscalas TODAS):**
- Roles de mesa/staff COMPLETOS: PRESIDENTE/A, VICEPRESIDENTE/A, SECRETARIO/A, **SUBSECRETARIO/A,
  PROSECRETARIO/A, RELATOR/A, ASISTENTE DEL SECRETARIO** (+ENCARGADO/GENERAL/ALTERNO/"A. I.").
- Honoríficos deletreados y abreviados: LICENCIADO/A, LICDO/L1CDO/LCDO, DIPUTADO/A, DOCTOR/A,
  DRA., SR./SRA., PROF., ING., MAGISTER, HONORABLE SEÑOR, **S.E.** (ministros).
- Variantes OCR del honorífico: B.L.←H.L., -HO./-He./-Ho.←H.D., SEROR←SEÑOR, y letras
  minúsculas dentro de nombres CAPS (ROGELlO, DíDIMO) → canonicalizar en
  `correct.normalize_replacements` ((?<=[A-Z])l(?=[A-Z])→I, í→Í, PRES\s?IDENTE→PRESIDENTE,
  SUBSECRETAaIO→SUBSECRETARIO, GENERA(fin de línea)→GENERAL, ENCl~GADO→ENCARGADO…).
- **Cambios de CONVENCIÓN por era** (el más peligroso): p.ej. PA 2016+ la mesa firma
  "—NOMBRE, ROL" SIN honorífico. Detección: Paso 2e-ter (panel por año).
- Formas compuestas: rol-primero ("PRESIDENTE ENCARGADO, H.L. X:"), marcador+discurso en la
  misma línea, ':' en la línea siguiente, marcador fragmentado multi-línea (columna estrecha)
  → `correct.marker_reassembly` + protección del merge (ya generales en correct_text.py).
- Topes de longitud: nombre+cargo real llega a 90 chars — no capar a 55-70.

### Paso 0c-bis — MARCADOR PARTIDO por el salto de línea (OBLIGATORIO — gate propio de tag)

⚠ **Lección PY 2026-08: ~100.000 turnos perdidos, el 25% del corpus, sin que ningún recuento lo
delatara.** El OCR corta el marcador por el ancho de columna:

```
SEÑOR DIPUTADO RICARDO GONZALEZ
ESCOBAR: Gracias, señor Presidente.
```

Un patrón que exige el marcador entero en una línea no ve ninguno de esos turnos: su texto se
queda dentro de la intervención anterior. El total salía en 285.912 marcas —una cifra creíble—
frente a 386.133 reales. **Se descubrió comparando forma a forma con el etiquetado anterior:
faltaban TODAS las formas largas (`SEÑOR DIPUTADO <NOMBRE>:`) y ninguna corta (`SEÑOR
PRESIDENTE:`, que cabe en una línea).** Un total plausible no prueba nada; el inventario por
forma sí.

Este gate es **propio de tag** y no depende de que `correct` lo haya reensamblado bien: mide el
resultado, no la intención.

```python
# ¿cuántas parejas de líneas forman un marcador que quedó SIN envolver?
import re
from pathlib import Path
from collections import Counter
CAB = r"(?:SE(?:Ñ|N)OR[A]?|DIPUTAD[OA]|PRESIDENT[EA]|SECRETARI[OA]|RELATOR[A]?)"   # ← del Paso 0c
COLA = re.compile(r"^[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ .'\-]{1,40}:(\s|$)")
def versal(s):
    L=[c for c in s if c.isalpha()]
    return len(L)>=4 and sum(1 for c in L if c.isupper())/len(L)>=0.8
part=Counter()
for p in Path(f"source/{iso2}/tagged").glob("*.txt"):
    ls=[l.strip() for l in p.read_text(errors="replace").split("\n")]
    for a,b in zip(ls,ls[1:]):
        if versal(a) and re.match(rf"^{CAB}\b[^:\n]{{0,60}}$",a) and COLA.match(b) and versal(b.split(":")[0]):
            part[f"{a[:40]} ⏎ {b[:30]}"]+=1
print(sum(part.values()), "marcadores partidos sin envolver")
for s,c in part.most_common(15): print(f"{c:>5}  {s}")
```

**Criterio: HALT si supera el 0,2% de las intervenciones.** Medido: 1,486% en el estado roto de
PY frente a 0,003% una vez cosido, y ninguno de los 16 corpus publicados pasa de 0,072%. Si
enciende:

1. **Coser, NO aplanar.** Une solo las líneas que juntas forman un marcador (hasta dos
   continuaciones, sin cruzar línea en blanco). Aplanar el texto también lo arregla, pero
   destruye la estructura de línea —una de las 14 comprobaciones de `conformidad.py`— y en CO
   dejó capturas de `speaker_raw` de 6.310 caracteres.
2. Admite ruido de OCR delante del marcador: `^[\s.,:;'"\-—·|]{0,4}`. En PY eso solo valía
   2.175 turnos más, pero bajaba los marcadores incrustados de 0,112% a 0.
3. Arregla el reensamblado en `correct.marker_reassembly`, no a mano en una sesión: el fallo es
   de la fuente entera, no de un acta.

La comprobación equivalente sobre el corpus ya publicado es `marcador partido` en
`conformidad.py`, y se ejecuta también al reprocesar un país ya cerrado.

### Paso 2e-ter — PANEL POR AÑO (detector de cambios de convención) — antes de dar por bueno

Tras el tagging masivo, calcula por AÑO: nº de intervenciones, % de turnos rol-only y
turnos/sesión. **Una caída brusca de %rol o del volumen anual en una era = cambió la convención
de marcador y esa era está sin etiquetar** (PA: 2016-2025 con %rol=0 y volumen a un tercio →
121.634 turnos de mesa recuperados). No declares diaries-tag completado si el perfil anual
tiene discontinuidades sin explicación documental.

## Paso 1 — Determinar lista de sesiones

**`--session YYYY-MM-DD`**: una sola sesión.

**`--batch YYYY-MM`**: todas las sesiones cuyo session_id empieza por `YYYY-MM`:
```bash
ls source/{iso2}/corrected/ | grep "^YYYY-MM"
```

**`--all`**: todas:
```bash
ls source/{iso2}/corrected/
```

Filtra sesiones con `skills.diaries-tag.status == "complete"` en el estado, salvo `--force`.

---

## Paso 2 — Procesar cada sesión

### 2a. Verificar prerequisito

```bash
ls "source/{iso2}/corrected/{session_id}.txt" 2>/dev/null
```

Si no existe: registra error "Texto corregido no encontrado. Ejecuta diaries-correct primero." y salta.

⚠ **`tag` NUNCA se ejecuta sobre otra cosa que `corrected/`.** No sobre `extracted/`, no sobre
`ocr/`, no sobre un `.txt` de `raw/`, ni «solo para probar». `corrected/` es donde se reensambla
el marcador que la fuente parte por el salto de línea, y ese reensamblado es la única razón por
la que el etiquetado ve marcadores completos. Saltárselo no degrada un poco el resultado: hace
**desaparecer turnos enteros** sin que ningún recuento lo delate — en PY costó ~100.000 turnos,
una cuarta parte del corpus, con un total perfectamente creíble. Ver
[[feedback_marcador_partido]] y el gate del Paso 0c-bis.

### 2b. Crear directorio de salida

```bash
mkdir -p source/{iso2}/tagged/
```

### 2c. Pase determinista (regex)

Si `--dry-run`: imprime el comando que se ejecutaría y salta.

Si no es dry-run (pasa `--deputies` si existe la base, para mejorar el scoring del nivel 2):
```bash
python ~/.claude/skills/diaries-lib/lib/utils/tag_text.py \
  --input "source/{iso2}/corrected/{session_id}.txt" \
  --config "country_config/{iso2}.yaml" \
  --output "source/{iso2}/tagged/{session_id}.txt" \
  --deputies "source/{iso2}/deputies/deputies.csv"
```

El JSON incluye `strict_matches`, `probabilistic_matches`, `n_borderline` y `borderline_cases`
(nivel 2 bajo umbral → pasan a resolución LLM / FLAG, junto con `untagged_spans` sospechosos).

Lee el JSON de stdout. Estructura esperada:
```json
{
  "tagged_speakers": 187,
  "untagged_spans": [
    {
      "line_number": 43,
      "text": "EL SR. ALCALÁ DE ZAMORA:",
      "suspicious": true,
      "reason": "no_match_regex"
    }
  ]
}
```

### 2d. Pase LLM para spans sospechosos

Si no hay `untagged_spans` con `"suspicious": true`: salta este paso.

Para cada span sospechoso, procésalos en batches de 30. Para cada uno:

1. Lee el contexto: usa Read para leer el archivo `source/{iso2}/tagged/{session_id}.txt` y extrae las 3 líneas anteriores y 3 posteriores a `line_number`.

2. Determina si el span es un orador:
   - **Es orador si**: el texto tiene forma de "NOMBRE:" o variante, y la línea siguiente es un discurso o declaración, y el contexto corresponde a un turno de palabra.
   - **No es orador si**: es un título de sección, una cita dentro de un discurso, un encabezado de columna, o un elemento de lista.

3. Si **es orador**: determina su nombre normalizado (sin prefijos de `speaker_prefix_strip`, en formato "Apellido, Nombre" si es posible). Edita el archivo con Edit para insertar la etiqueta antes de la línea:
   ```
   <int speaker="{NOMBRE_NORMALIZADO}">
   ```
   La etiqueta va en la línea inmediatamente anterior al texto del span.

4. Guarda un registro interno: para cada span resuelto, anota si era orador (True/False) y tu nivel de certeza (0.0–1.0).

### 2e. Calcular confianza y verificar integridad estructural

```
n_auto      = tagged_speakers del JSON (identificados por regex)
n_llm       = número de spans sospechosos que resultaron ser oradores (paso 2d)
n_untagged  = número de spans sospechosos que NO eran oradores
avg_llm_conf = promedio de las certezas individuales del paso 2d (0.0 si no hubo spans)

confidence = n_auto / (n_auto + n_untagged + n_llm * (1 - avg_llm_conf))
```

Si `n_auto + n_untagged + n_llm == 0`: confidence = 0.50 (sesión sin oradores detectados — sospechosa).

**⚠ Verificación de integridad estructural (aprendido en UY, 2026-06; refinado 2026-06-16):**

Una sesión con `n_auto` muy bajo en texto sustancial tiene TRES causas distintas que hay que
DISTINGUIR — no todas son fallo. El conteo de oradores SOLO no basta (marcaría falsos positivos):

1. **Trámite genuino (NO es fallo → complete):** sesiones de asuntos entrados, exposiciones
   escritas, pedidos de informes o textos de proyectos de ley (articulado), SIN debate oral.
   Tienen pocos o ningún marcador de orador real, y eso es CORRECTO. El texto está LIMPIO.
2. **OCR de prefijo corrupto:** el OCR degradó el honorífico (`SEÑOR→SEROR`) y el regex no lo
   reconoció → debate perdido. Señal: muchas variantes degradadas del honorífico pero pocas
   detectadas. → re-normalizar (diaries-correct) y re-taggear.
3. **Encoding roto (PUA / control chars):** PDF digital con fuente sin `ToUnicode` → el texto
   embebido es basura parcial y el prefijo es ilegible → debate perdido. Señal: ratio alto de
   chars PUA (0xE000–0xF8FF) o de control, o ratio alfabético bajo. → recuperación híbrida
   (decode +0xF000 / OCR del render), luego re-extract → re-correct → re-tag.

Guardia (el discriminador es la INTEGRIDAD del texto, NO solo `n_auto`):

```python
chars = len(corrected_text)
pua   = sum(1 for c in corrected_text if 0xE000 <= ord(c) <= 0xF8FF) / max(chars, 1)
ctrl  = sum(1 for c in corrected_text if ord(c) < 32 and c not in '\n\t') / max(chars, 1)
alpha = sum(1 for c in corrected_text if c.isalpha()) / max(chars, 1)
corrupto = pua > 0.05 or ctrl > 0.10 or alpha < 0.55

if chars > 5000 and n_auto < 3:
    if corrupto:
        # causa 2/3: debate perdido por encoding/OCR roto → recuperar (HALT)
        confidence = min(confidence, 0.45)
        advertencia = (f"TEXTO CORRUPTO: {n_auto} oradores, pua={pua:.0%} ctrl={ctrl:.0%} "
                       f"alpha={alpha:.0%}. Recuperar con OCR híbrido (decode+OCR) y re-taggear.")
    # else (texto limpio) → causa 1: TRÁMITE GENUINO, NO penalizar (pocos oradores es correcto)
```

⚠ **NO penalices por `n_auto < 3` si el texto está LIMPIO.** En UY, 91 de 93 sesiones que la
guardia vieja marcó eran trámite genuino (falsos positivos); solo 2 tenían texto corrupto y
necesitaban recuperación. La integridad del texto es el discriminador, no el conteo de oradores.

### 2e-bis. CAPA DE VERIFICACIÓN anti-falsos-negativos (OBLIGATORIA — gate antes de avanzar)

El tagging es la fase MÁS DELICADA del pipeline. Un marcador NO detectado (falso negativo)
atribuye TODA su intervención al orador anterior y corrompe la matriz SILENCIOSAMENTE — ninguna
métrica de conteo lo nota. Por eso, tras taggear CADA sesión, ejecuta SIEMPRE esta verificación
ANTES de fijar el estado:

```bash
python ~/.claude/skills/diaries-lib/lib/utils/verify_tagging.py \
  --tagged "source/{iso2}/tagged/{session_id}.txt" \
  --config "country_config/{iso2}.yaml"
```

Reporta `n_residual_markers` (líneas con FORMA de marcador de orador que quedaron SIN etiquetar
= falsos negativos REALES; ya excluye firmas, listas de asistencia "APELLIDO, Nombre" y menciones),
`verdict`, `capture_rate` y ejemplos.

**REGLA DURA — ABSOLUTE FAIL.** Si `n_residual_markers >= 1` → la sesión va a **HALT**, NUNCA a
`complete` ni a `flag`. Un falso negativo confirmado es un fallo ABSOLUTO del proceso: el pipeline
no puede avanzar con esa sesión hasta que el marcador se IDENTIFIQUE y se CORRIJA. `confidence =
min(confidence, 0.50)`. Solo `n_residual_markers == 0` permite `complete`.

**Causa #1 de falsos negativos — paréntesis del OCR.** El OCR confunde `(` `)` con `{` `}` `[` `]`
y a veces pierde el `(` de apertura: `(Abdala}`, `{Abdala)`, `PRESIDENTE Marchesano)`. Un solo
presidente así pierde TODAS sus intervenciones. El grupo de paréntesis de `speaker_tag_patterns`
y `speaker_loose_pattern` DEBE aceptar apertura opcional `[({]?` y cierre flexible `[)}]`, no solo
`\(...\)`. (Verificado en UY: recuperó >2400 intervenciones en una sola sesión de 1,75 MB.)

**Resolver residuales:** mira el patrón común en `residual_examples`, amplía
`speaker_tag_patterns`/`speaker_loose_pattern` (o añade una normalización a diaries-correct) y
re-taggea con `--force`. Repite hasta 0 residuales reales.

⚠ **El SUELO del detector se fija sobre un país de CONTROL, no se asume.** Un patrón de
residuales escrito contra el texto etiquetado de un país NO se transfiere en crudo: reutilizado
sin recalibrar midió **11,99 %** en PY cuando la tasa real era **0,09 %**. Antes de creer la
cifra, corre el mismo detector sobre un país LIMPIO conocido: esa lectura fija el suelo (medido:
0,008 %) y todo residuo de ese orden es ruido del detector, no falsos negativos. Ver
[[feedback_patrones_contra_texto_etiquetado]].

⚠ **GATE ABSOLUTO — EL PROCESO NO PUEDE PROSEGUIR.** Ninguna sesión con `n_residual_markers >= 1`
puede quedar fuera de HALT. `diaries-matrix` y toda fase posterior a `diaries-tag` DEBEN ABORTAR
si existe cualquier sesión con `diaries-tag` en HALT por falsos negativos (`diaries-matrix` lleva
este gate en su entrada; `diaries-meta` NO aplica — corre ANTES de tag en el orden canónico).
El pipeline solo avanza cuando los falsos negativos están **IDENTIFICADOS y CORREGIDOS** (0
residuales reales en todas las sesiones). Es el peor error
del pipeline: atribuye intervenciones a speakers equivocados y destruye la confianza en los datos.
En batches `--all`, integra la verificación en el runner (como en UY) para que el estado de cada
sesión refleje sus residuales y el gate se aplique automáticamente.

**Cómo desbloquear:** ejecuta `verify_tagging.py` sobre las sesiones en HALT, agrupa los
`residual_examples` por patrón común, amplía `speaker_tag_patterns`/`speaker_loose_pattern` (o
normaliza en diaries-correct), re-taggea con `--force` y re-verifica. Para los residuales que el
regex no pueda capturar (casos únicos), etiquétalos con el pase LLM del Paso 2d. Repite hasta que
TODAS las sesiones tengan 0 residuales reales.

### 2f. Actualizar estado

Usa los umbrales específicos del skill (threshold_auto=0.80, threshold_flag=0.60):
- `confidence >= threshold_auto` → `complete`
- `confidence >= threshold_flag` → `flag`
- `confidence < threshold_flag` → `halt`

```bash
python ~/.claude/skills/diaries-lib/lib/utils/update_state.py \
  --country {iso2} \
  --skill diaries-tag \
  --session {session_id} \
  --status {complete|flag|halt} \
  --confidence {valor} \
  --output "source/{iso2}/tagged/{session_id}.txt"
```

---

## Paso 3 — Resumen final

```
Resumen diaries-tag — {iso2}
─────────────────────────────────────────────
  AUTO  (complete): {N}
  FLAG  (revisar):  {N}
  HALT  (detenido): {N}
  SKIP  (ya hecho): {N}
  ERROR:            {N}
─────────────────────────────────────────────
  Total procesadas: {N}
  Oradores por regex: {total}
  Oradores por LLM:   {total}
  Spans descartados:  {total}
```

Si hay sesiones con confidence 0.50 exacto (sin oradores):
```
Advertencia — sesiones sin ningún orador detectado:
  {session_id_1}, {session_id_2}
Verifica que speaker_tag_patterns en country_config/{iso2}.yaml sea correcto.
```

Si hay casos FLAG o HALT:
```
Hay {N} sesiones que requieren revisión.
Ejecuta: /diaries-review --country {iso2}
```

---

## Paso 4 — GATE DE SALIDA (ABSOLUTE FAIL por falsos negativos)

Cuenta las sesiones en HALT por falsos negativos (verificación del Paso 2e-bis:
`n_residual_markers >= 1`). Si hay AL MENOS UNA, imprime y DETENTE:

```
╔════════════════════════════════════════════════════════════════╗
║  ⛔ ABSOLUTE FAIL — diaries-tag NO superado                     ║
║  {N} sesiones con FALSOS NEGATIVOS (marcadores sin etiquetar).  ║
║  El pipeline NO puede avanzar a diaries-matrix ni más allá.     ║
╚════════════════════════════════════════════════════════════════╝
Falsos negativos = intervenciones atribuidas al orador equivocado. Hay que resolver TODOS
antes de continuar (ver "Cómo desbloquear" en el Paso 2e-bis): verify_tagging.py sobre las
sesiones en HALT → agrupar residuales por patrón → ampliar regex/normalizar → re-tag --force
→ los irreductibles, etiquetar con el pase LLM (Paso 2d). Repetir hasta 0 residuales reales
en TODAS las sesiones.
```

⚠ NO declares diaries-tag completado ni sugieras avanzar de fase mientras exista UNA SOLA sesión
en HALT por falsos negativos. Es un fallo absoluto del proceso, no una advertencia revisable.
