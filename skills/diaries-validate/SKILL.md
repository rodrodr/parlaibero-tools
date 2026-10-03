---
name: diaries-validate
description: Valida la integridad estructural del corpus por muestreo, con auto-filtro PASS/FLAG y calibración empírica de la tasa de fuga. Produce la cifra de calidad que el corpus puede afirmar, no la que se supone.
---

# /diaries-validate — Validación de integridad estructural

Mide **qué fracción del corpus está bien estructurada y bien atribuida**, por muestreo y con
la tasa de error acotada empíricamente. No es una comprobación de que el pipeline terminó:
eso lo dice `/diaries-status`. Esto dice si lo que produjo es correcto.

Método completo en `docs/_metodologia/validation_methodology.md`.

---

## Por qué existe

Sin esto, la calidad del corpus es una suposición. Y el proyecto ya tiene el caso de lo que
pasa al suponerla: en AR se declaró un **0,016%** de marcadores incrustados cuando el real era
**0,47%** —treinta veces más— por dar el filtro por infalible en vez de medirlo.

La primera ejecución (2026-07-31) destapó **cuatro clases de defecto que ningún control veía**,
una de ellas aprobando sin mirar el 46,8% del corpus paraguayo.

---

## Principio de independencia

El verificador **no comparte código ni léxico con lo que vigila**: los detectores de este
skill se escriben aparte de los del pipeline, con patrones propios, y no reutilizan las
listas ni las regex de `correct`/`tag`. Un control que comparte léxico con su productor
hereda sus puntos ciegos y da 0 residuales justo donde falla (CR: 22.979 marcadores omitidos
con el verificador dando 0). Ya se practica; queda declarado como requisito de diseño
(plan de validación §5).

---

## Paso 1 — Muestreo y auto-filtro

```bash
python3 ~/.claude/skills/diaries-lib/lib/utils/validate_structural.py --country {iso2} --n 300
```

Muestra aleatoria simple **ponderada por intervención** —la pregunta es «de lo que alguien va
a leer, ¿qué fracción está bien?», no «qué fracción de los oradores únicos»—. Cada fila se
separa en:

- **PASS** — trivialmente correcta según reglas deterministas
- **FLAG** — todo lo demás, a revisión humana

⚠ **El filtro es un separador de OBVIEDAD, no un juez de calidad.** Solo marca PASS lo que no
admite duda; ante cualquier sombra, FLAG. Eso desactiva la circularidad productor-validador,
porque el error del pipeline vive en los casos difíciles y esos van todos a FLAG por
construcción.

**Dimensiones:**

| | qué comprueba |
|---|---|
| **D1** pureza | ningún marcador de otro orador dentro del `text` |
| **D2** atribución | mandato vigente · homonimia · orador nombrado sin `id_dep` |
| **D3** carácter | sin glifos corrompidos (área de uso privado, carácter de reemplazo) |

⚠ **D1 se busca INLINE, nunca anclado a línea.** GT, ES y CL tienen 0% de saltos de línea; un
detector anclado a línea da cero falso ahí, y GT parecía limpio siendo el peor corpus en
folios. Y con dos detectores: **vocabulario** —los nombres de orador que el corpus ya conoce,
independiente de la tipografía— y **léxico** —cortesía + nombre en mayúsculas—, porque el
segundo caza a quien nunca se etiquetó y el primero no.

⚠ **La vigencia se juzga por MANDATO EN LA LEGISLATURA, no por fecha exacta.** Exigir que la
fecha caiga dentro del intervalo convierte la precisión con que cada padrón anotó las fechas
en una medida de calidad, que no lo es. Corregirlo bajó los FLAG de 7,6% a 5,8%: de 180
«fuera de mandato», **75 eran artefacto de la anotación**.

⚠ **Descubrir dónde está la legislatura, no asumir el nombre de la columna.** GT la registra
en `notas`, el campo genérico de la plantilla, y figuró como «no comprobable» en dos pasadas
teniendo el dato delante.

⚠ **La homonimia NO se marca**: se adjudicó en `/diaries-match`, con revisión humana caso por
caso, antes del merge. Volver a marcarla es rehacer trabajo hecho por una persona.

---

## Paso 2 — Calibración de la tasa de fuga

**Obligatorio. Sin esto no hay cifra de calidad, solo rendimiento del filtro.**

```bash
python3 ~/.claude/skills/diaries-lib/lib/utils/prepare_leak_calibration.py --n 200
```

Una **fuga** es una fila marcada PASS que en realidad tenía un problema: se escapó y nadie la
va a mirar. La asimetría es la razón de todo el diseño — un FLAG de más cuesta una revisión
inútil; un PASS de más es un error silencioso.

200 filas PASS al azar, **repartidas por igual entre países** para que todas las convenciones
queden ejercitadas. Las revisa una persona.

**Cuándo parar.** Cada corrección invalida formalmente la ronda que la destapó, así que
perseguir el «0 en 200» es una regresión infinita. Se declara la tasa medida con su intervalo
y la corrección posterior, que solo puede bajarla. Dos rondas bastaron: **2,0% → 0,5%**, y de
cuatro clases de defecto a una, cada vez más local.

---

## Paso 3 — Triaje de los FLAG

```bash
python3 ~/.claude/skills/diaries-lib/lib/utils/export_flags_review.py
```

**No todos los FLAG necesitan ojo humano.** Los de hueco de padrón —orador nombrado sin
`id_dep`, sin mandato en la legislatura— se resuelven solos: el triaje automático mostró que
el **96%** son personas que no figuran en el padrón, no fallos del matcher.

Va a revisión humana **solo** lo que ninguna regla puede decidir: marcador de otro orador
(¿turno ajeno o cita?), cadena de firmas (¿discurso o pie de un proyecto?), caracteres
corrompidos (¿cuánto texto se pierde?). En la primera ejecución fueron **58 filas de 363**.

Con el **contexto recortado** alrededor del hallazgo, no la intervención entera.

---

## Paso 4 — Auditoría de fechas contra la cabecera del acta

```bash
python3 ~/.claude/skills/diaries-lib/lib/utils/audit_session_dates.py --country {iso2} \
        --report docs/{iso2}/auditoria_fechas.csv
```

La fecha y el número de sesión son metadatos que el pipeline **derivó**; el acta los
**declara**. Cuatro veredictos: `OK` · `FECHA_DISTINTA` · `OCR_CABECERA` · `CONFLADA`
(dos sesiones fundidas en una) · `SIN_CABECERA`.

⚠⚠ **Ante una discrepancia NO manda automáticamente el acta.** La primacía del diario vale
cuando el diario es legible; si la cabecera viene de OCR, la corrupta suele ser ella. Se decide
por **cronología** contra las sesiones vecinas del propio corpus. Medido en UY: de 22
discrepancias, **20 eran diferencias de años enteros** (−20, +1, +10, −2, +4, −70 — un dígito
del año mal leído) y las vecinas confirmaban la fecha registrada. Corregir por principio habría
falsificado 20 fechas correctas.

⚠⚠ **Un desfase CONSTANTE es defecto del patrón, nunca de los datos.** En PT la auditoría daba
28,0 % de fechas distintas; **1.321 de las 1.368 eran exactamente +1 día**, porque el patrón
cogía la fecha de *publicación* del diario en vez de la de la sesión. La utilidad lo detecta y
lo dice.

⚠ **Más de la mitad sin cabecera ⇒ el resultado no es una cifra de calidad**, es que el patrón
no la encuentra. Hoy solo cuatro países tienen cobertura suficiente para leer el resultado —
UY 96,2 % · MX 92,1 % · PA 83,3 % · CR 82,0 %—; el resto necesita declarar
`audit.session_header.pattern`, porque el `session_date_regex` heredado se escribió para
extraer una fecha de una posición conocida, no para localizar la cabecera autorizada.

⚠ **No corrige nada.** Una fecha mal derivada está propagada al `session_id` y a los
intermedios: la corrección es un reproceso, no un `UPDATE` sobre la matriz.

## Paso 5 — Integridad de `intervention_order`

```bash
python3 ~/.claude/skills/diaries-lib/lib/utils/check_order_integrity.py --all
```

`intervention_order` es la posición en la **sesión original**. Doctrina vigente: **nada se
aparta a un sidecar** — la fila que no es discurso se DECLARA con `dm_speech = 0` y se queda
en el corpus; la carátula y el sumario son los Prolegomena, con `intervention_order = 0`.
Un hueco, por tanto, hay que poder explicarlo:

| | |
|---|---|
| hueco **EXPLICADO** | Prolegomena en orden 0 · filas declaradas `dm_speech = 0` presentes en la matriz |
| hueco **HUÉRFANO** | la posición no está en ninguna parte → fila perdida de verdad |

⚠ **Los sidecars de agosto son artefactos de la LÍNEA BASE (legado).** BR, PE y SV arrancan en
la posición 2 en **todas** sus sesiones porque la campaña previa apartó la fila de apertura a
un sidecar (SV 389 posiciones 1 para 389 sesiones · BR 6.921 · PE 3.000): al auditar ESA línea
base hay que cruzar con los sidecars o es indistinguible de una pérdida. Tras el reproceso
desde cero **«empieza en 2» vuelve a ser señal de PÉRDIDA**: la apertura debe estar en la
matriz como orden 0 o como fila `dm_speech = 0`, nunca fuera.

⚠ **`date` + `session_number` NO identifica la sesión en todos los países.** PA y PY no tienen
`session_number` en ninguna fila, y BR en 40.672: dos sesiones del mismo día caen en el mismo
grupo y aparecen «órdenes duplicados» que no lo son. La utilidad lo avisa.

Resultado (2026-08-02): **~2.378 posiciones huérfanas** en 8 países —CO 1.026 · BR 420 · PY 351
· PT 142 · MX 134 · PE 108 · UY 102 · GT 95—, sobre ~8,1 M de intervenciones. Pendiente de
diagnosticar país por país: pueden ser filas perdidas o huecos de numeración al construir.

## Cómo se lee el resultado

⚠ **«Sin mandato» y «sin id_dep» NO son instrucciones de borrado.** El diario es la fuente
primaria y el padrón una construcción nuestra: el desajuste es defecto del padrón. La
intervención **se mantiene siempre** (`validation_methodology` §4.6).

⚠ **PASS no es «correcto», es «no verificable en contra».** El filtro no comprueba si una
atribución es *correcta*, solo si es *plausible*: una fila con `id_dep` puesto y mandato
vigente pasa aunque el id sea de otra persona. Esa dimensión solo se ve muestreando y mirando
el acta.

**Primera ejecución, 15 países, n=300 cada uno:**

| | |
|---|---|
| FLAG | 363 de 4.500 = **8,1%** |
| tasa de fuga | **0,5%** IC 95% [0,09 – 2,78] |
| D1 (pureza) | 1,0% de la muestra |

---

## Umbrales

No usa AUTO/FLAG/HALT por confianza: el veredicto es determinista. Un país con **0% de FLAG**
no es necesariamente el mejor — hay que mirar cuántas dimensiones quedaron **no aplicables**,
porque su padrón no podía expresarlas.
