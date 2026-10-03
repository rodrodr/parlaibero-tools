---
name: diaries-meta
description: "Extrae metadatos de sesión (fecha, número, tipo, legislatura y la PRESIDENCIA — uno o varios presidentes por TRAMO) y escribe el JSON por sesión. NO asume formato: usa la heurística registrada del país o la DESCUBRE y la registra."
allowed-tools: [Read, Write, Edit, Bash]
---

Argumentos: `--country {iso2}` + uno de `--session YYYY-MM-DD` | `--batch YYYY-MM` | `--all` + opcionales `--force`, `--dry-run`

**Posición en la cadena: justo DESPUÉS de `diaries-correct`, ANTES de `diaries-tag`.**
Su insumo es **`extracted/{session_id}.txt` — la capa FIEL** (rediseño 2026-08): los metadatos de
sesión (Acta N.º, fecha, tipo) viven a menudo en el **cabecero/mastete de cada página**, que
`diaries-correct` elimina (en SV la limpieza retira 8.531 car. y 100 folios de una sola sesión). Por
eso meta lee la capa fiel, no la corregida. `corrected/` sirve de respaldo manual si una sesión
concreta se parsea mejor limpia. No necesita el texto etiquetado. Ejecutarlo antes de tag permite que
`diaries-dedupe` (que solo consume el campo `date` de `meta/`) elimine los escaneos duplicados ANTES
de la fase de etiquetado, la más cara y cuyo inventario estructural se sesga con duplicados.

⚠ Como `extracted/` conserva los marcadores de página (`---PAGE N---`) y repite el cabecero por
página, la auditoría de fechas de meta (contar la fecha del cabecero) se beneficia; ignora los
`---PAGE N---` al parsear.


## ⛔ GATE DE ENTRADA (OBLIGATORIO) — `extracted/` presente

En el orden canónico `meta` corre ANTES de `diaries-tag` (… correct → **meta** → dedupe → tag …),
así que NO depende del etiquetado ni de ninguna fase posterior. Su prerequisito real es que
`diaries-extract` haya completado — la capa fiel es su insumo:

```bash
ls source/{iso2}/extracted/*.txt >/dev/null 2>&1 \
  && echo "Gate OK: extracted/ presente" \
  || echo "⛔ Sin extracted/ para {iso2}. Ejecuta /diaries-extract primero."
```

Si falta `extracted/`: **DETENTE, no extraigas metadatos** y remite a `/diaries-extract`. El
respaldo `corrected/` del Paso 2a es por sesión concreta, no exime del gate: sin capa fiel no
hay cabecero corrido que votar.

---

## ⛔⛔ ANTES DE RE-EJECUTAR sobre un país que YA tiene `meta/` — dos comprobaciones

Re-ejecutar `meta` **reescribe el JSON entero**. Dos cosas se pierden sin aviso, y las dos costaron
un susto real el 2026-08-29.

**1 · ¿Lo generó este skill, o una tubería propia del país?** Mira `date_source` en tres o cuatro
JSON. Si trae valores que `extract_meta.py` NO emite —solo emite `text`, `filename_fallback` y
`missing`— entonces el dato lo produjo otro código y re-ejecutar lo DEGRADA. Etiquetas vistas:
`acta_header`, `acta`, `body`, `neighbour_arbitration` (CO) · `contenido+filename`,
`date_cabecero_votos`, `date_multiday_line` (PA). Medido al rehacer CO con el extractor genérico:

| campo | tubería propia | extractor genérico |
|---|---|---|
| `date` | 1.608 | 1.087 |
| `session_number` | 1.608 | 1.339 |
| **presidencia** | **1.600** | **0** |

Las tuberías por país están en `scripts/campana_reproceso/{iso}_meta/` (`tr-0097`). **Copia
`meta/` antes de tocarlo** y compara campo a campo antes de dar la re-ejecución por buena.

**2 · ¿Hay dictamen de fechas para ese país?** `state/_fechas_dictamen.json` guarda el arbitraje
humano de `tr-0090` (178 casos en 10 países). Re-ejecutar lo borra. Comprueba antes y re-aplica
después:

```bash
python3 tools/reaplicar_dictamen_fechas.py --country {iso2} --check   # antes
python3 tools/reaplicar_dictamen_fechas.py --country {iso2}           # después
```

⚠ Un `meta` cuyo `extracted/` se rehizo después **no está necesariamente caducado**. Mídelo antes
de rehacerlo: en PA las 119 sesiones afectadas reproducían la fecha IDÉNTICA 119/119, y en CO
re-ejecutar habría perdido 698 fechas de 1.608 porque el parser estaba afinado contra el
renderizado anterior. La decisión correcta puede ser **cerrar sin re-ejecutar**, con la medición
como evidencia (`co-0016`, `pa-0004`, `uy-0007`).

---

## Paso 0 — Heurística del país: usar la registrada, o DESCUBRIRLA

⚠ **Reformulado 2026-07-30 tras encontrar que este skill fallaba en 7 de 15 países.** La versión
anterior **asumía** que alguien había escrito los regex correctos en el config y solo los
*verificaba*. Si `president_tag` faltaba o era incorrecto, el campo quedaba vacío en silencio.
Consecuencias medidas: PY tenía la clave `president` **creada y vacía en el 100% de sus sesiones**;
PA solo la rellenaba en el 22%; BR, PT y PE ni siquiera llegaron a tener `meta/`. En total,
**1.253.000 intervenciones sin atribuir cuyo dato estaba en la primera página del acta.**

El skill **no debe asumir ningún formato**. Debe usar la heurística ya registrada para el país y,
si no la hay o no valida, **descubrir la estructura** y registrarla.

⚠⚠ **Y hay un motivo de MOTOR por el que `president_tag` puede no disparar NUNCA** (medido
2026-08-25, DO). `extract_meta.py` mete el valor en `re.escape()` y además lo compara con
`stripped.lower().startswith(president_tag.lower())`: **lo trata como LITERAL**. Un `president_tag`
escrito como expresión regular —con grupos, alternativas o `\s+`— es inerte por construcción.
Lo declaran así **diez de los dieciséis países**. Hoy no hay daño porque las pasadas del reproceso
construyeron su propia extracción, pero **es una trampa esperando a quien confíe en esa vía**:
si tu `president_tag` lleva `( ) [ ] | + * ? { } ^ $ \`, NO lo uses — extrae la presidencia con
tu propio patrón y **declara la cobertura medida**, no supongas que el motor la ha poblado.

⚠⚠⚠ **LA TRAMPA DE GÉNERO DEL `president_tag`** (PE, 2026-08-29). Como el motor lo trata como
literal y le recorta el prefijo, la tentación es declarar la forma que da un nombre limpio —
`PRESIDENCIA DEL SEÑOR` — y esa forma **borra a todas las presidentas**, porque la femenina es
`PRESIDENCIA DE LA SEÑORA`. En PE habría costado **659 presidencias femeninas, el 21,6 %**. Es el
sesgo documentado en `[[feedback_gender_bias_extraction]]`: *cuando el patrón falla, la que
desaparece es una mujer*, y aquí se paga en cinco segundos de comodidad y en silencio absoluto.

**Regla: el tag DEBE cubrir las tres formas** (`DEL SEÑOR`, `DE LA SEÑORA`, `DE LOS SEÑORES`),
aunque deje el artículo pegado al nombre — eso se limpia después sin perder a nadie. Y el control
de aceptación **no es la cobertura global, es la cobertura POR SEXO**: si el reparto femenino cae
muy por debajo de lo que declara el padrón del país, el patrón está sesgado, no el parlamento.
⚠ Lo mismo al partir un bloque con varios nombres: el tratamiento PLURAL (`SEÑORES`, `SEÑORAS`) no
declara el sexo de cada persona — se deja VACÍO. Atribuir el género del bloque a todos sus nombres
es el error de `[[feedback_rol_vinculado_en_bloque]]`, que costó 16.812 filas en UY.

### Paso 0a — ¿Hay heurística registrada?

Lee `country_config/{iso2}.yaml`, sección `meta_patterns:`. Si existe y trae
`validado_en` con sus estadísticas, **úsala y salta al Paso 1**. Ese es el camino normal tras la
primera ejecución: el descubrimiento se hace **una vez por país**, no por sesión.

```yaml
meta_patterns:
  president:
    regex: "PRESIDENCIA\\s+DEL?\\s+(?:SE[ÑNÒ]OR(?:A)?)?\\s*([A-ZÁÉÍÓÚÑ][^\\n,]{4,55})"
    ambito: primeras_3_paginas       # primeras_N_lineas | primeras_N_paginas | documento
    validado_en: 2026-07-30
    cobertura: 1.00                  # fracción de la muestra donde dispara
    resuelve_padron: 0.94            # fracción cuyo nombre casa con deputies.csv
    contiguidad_temporal: 0.97       # ver 0c — la señal que más pesa
    genero: {masc: 97, fem: 23}      # control de sesgo, ver 0d
```

Si la heurística existe pero su cobertura cae por debajo de lo registrado (fuente ampliada, nueva
época), **vuelve a descubrir** y actualiza el registro conservando el histórico.

### Paso 0b — DESCUBRIMIENTO (cuando no hay heurística o no valida)

**No inventes el patrón: encuéntralo.** El acta declara su propia identidad en la apertura —
presidencia, fecha, tipo, número, legislatura — pero cada cámara lo redacta a su manera. Formas
reales encontradas en los 7 países corregidos, para que se vea el rango que hay que cubrir:

| País | Forma | Tipo estructural |
|---|---|---|
| PE | `PRESIDENCIA DEL SEÑOR CARLOS FERRERO COSTA` | encabezado, valor tras la etiqueta |
| PT | `Presidente: Ex.mo Sr. Vasco da Gama Fernandes` | etiqueta`:`valor |
| BR | `TIPO DA SESSÃO: Ordinária - CD` · `O SR. PRESIDENTE (Nome)` | etiqueta`:`valor + paréntesis inline |
| PA | `el H.D. Sergio Gálvez Evers, Presidente de la Asamblea Nacional` | **prosa**: valor ANTES de la etiqueta |
| PY | bloque de etiquetas … lista de asistencia … `: Diputado Juan B. Ramírez` | **tabla de 2 columnas linealizada**: valores muy lejos de sus etiquetas |
| UY | `meta.president` ya poblado | — |
| GT | cabecera de página, no de sesión | — |

**Algoritmo:**

1. **Muestrea 40 documentos repartidos por TODO el período**, no solo los recientes. La convención
   cambia con los años: en PT la mención inline da 0% antes de 1990 y 21–39% después; en PA el
   tratamiento pasa de `H.L.` a `H.D.` en 2004.
2. **Ancla:** localiza las apariciones de la raíz del rol (`PRESIDEN`, y su equivalente en el idioma)
   en el **primer 15%** del documento.
3. **Candidatos:** extrae las secuencias de tokens capitalizados en ±250 caracteres de cada ancla,
   en ambas direcciones (en PA el nombre va ANTES de la etiqueta; en PY, a más de 900 caracteres).
4. **Puntúa cada plantilla** (forma del ancla · dirección · distancia) por las cuatro señales de 0c.
5. **Gana** la de mayor `resuelve_padron × contiguidad_temporal`. Si ninguna supera los umbrales,
   **HALT con la evidencia**: es preferible un campo vacío declarado a uno mal poblado.
6. **Registra la ganadora** en `meta_patterns:` con sus estadísticas medidas.

### Paso 0c — Validación del patrón descubierto (las cuatro señales)

Ninguna se apoya en el propio patrón, que es lo que las hace válidas:

1. **Resuelve contra el padrón.** El nombre extraído debe casar con `deputies.csv`. Suelo: 0,70.
2. **Contigüidad temporal — la señal más fuerte.** Un presidente de cámara ejerce un MANDATO: los
   nombres extraídos deben formar **bloques contiguos en el tiempo**, no alternarse sesión a sesión.
   Mídelo como la fracción de sesiones consecutivas con el mismo nombre. Suelo: 0,80. Esta señal
   detecta desalineaciones que ningún recuento revela.
3. **Cardinalidad.** Una cámara tiene pocos presidentes por década. Si el patrón extrae cientos de
   nombres distintos, está capturando oradores, no la presidencia. En PY dieron 111 nombres para
   1.553 diarios; en PE, 54 para 120.
4. **Reparto por género.** ⚠ **Obligatorio, y no es una comprobación cosmética.** Un patrón mal
   construido puede capturar casi solo un género: en PA, una primera versión anclada con
   `[^.]{0,300}` (que cualquier punto intermedio rompía) daba 13% de cobertura y **52 de 53
   coincidencias eran mujeres**. Sin anclar subía al 77% con reparto normal (250/59). Como las
   formas femeninas son más largas (`Presidenta`, `la H.D.`, `SEÑORA`), los patrones frágiles
   tienden a sesgar en una dirección u otra. Si el reparto se desvía mucho del histórico conocido de
   la cámara, **el patrón está mal**, no la cámara. Ver [[feedback_gender_bias_extraction]].

### Paso 0c-ter — La FECHA EN LETRAS, y por qué hay que ANCLARLA a la fórmula ⚠

Para arbitrar una fecha dudosa, el instrumento más fuerte y automatizable es la **fecha escrita en
letras** dentro del acta —niveles 1-2 de la jerarquía de `tr-0090`— porque es independiente del
cabecero, que es nivel 6 y no gana por sí solo. Sirve además donde el `session_id` no lleva fecha:
en EC, 1.092 de 1.233 sesiones marcadas no la llevaban y ninguna otra vía las alcanzaba.

⚠⚠ **Pero hay que anclarla a la FÓRMULA del acta, no tomar la primera fecha del documento.** La
versión sin anclar aplicada a EC marcó 217 sesiones como sospechosas y **el investigador revisó
tres y las tres eran falsas alarmas**: una efeméride institucional partida por el salto de línea
(«hace ya ciento ocho años, el veintiséis ⏎ de abril de mil novecientos» → el parser devolvía
**1900**), una fecha citada dentro de un discurso («tuvimos el honor de asistir el veintidós de
mayo del dos mil doce»), y una errata del propio acta que el meta ya había resuelto bien.

**Ánclala** a `se instala la sesión`, `siendo las N horas`, `a los N días del mes de`, o al
**Orden del Día** que lee el Secretario. Y encadena filtros baratos, que es lo que de verdad
decide:

- **coherencia con la banda de legislatura** — descarta el candidato fuera de rango;
- **posición en el documento** — una cita en prosa no vive en el primer 15 % del acta;
- **LEER la cita** — en el rescate de fechas de EC, un candidato que pasaba todos los filtros
  resultó ser la sesión de una COMISIÓN referida dentro del acta del pleno;
- **el día de la semana declarado** — control gratuito e independiente: en EC descartó
  `CE-22-258`, que dice «miércoles 3 de junio del 2004» siendo jueves.

De 33 sesiones sin fecha en EC, esa cadena rescató 11 con doble corroboración; sin los dos últimos
filtros habrían entrado 2 malas. Sobre las 1.233 marcadas: 819 corroboradas, 96 rellenadas, 11
corregidas (`ec-0009`, `ec-0010`).

### Paso 0c-bis — Presidencia por TRAMOS: descubrir los relevos dentro de la sesión ⚠

⚠ **«Un presidente por sesión» falla el 35,0% de los casos (medido).** La presidencia cambia de manos
dentro de una misma sesión: el titular se ausenta y entra un vicepresidente, luego reasume. Meta no debe
capturar UN nombre, sino **la SECUENCIA de quién preside y en qué tramo** — es lo que permite a
`diaries-match` atribuir los turnos de «EL PRESIDENTE» a la persona real por tramo y **evitar filas sin
`id_dep`**.

Dos fuentes, y hay que mirar ambas:
1. **La mesa de la carátula/Prolegomena** — el presidente de apertura (lo da el Paso 0a-0c) y el resto
   de la mesa (vicepresidentes, secretarios), que son los candidatos a relevo.
2. **Los relevos anunciados en el CUERPO** — descúbrelos como un patrón más del país (no los adivines):
   formas reales — `(Ocupa la Presidencia el señor X)`, `Pasa a presidir el señor X`, `Reasume la
   Presidencia el señor X`, `Preside la señora X`. Cambian por década y por país.

**Determina el `scope` del país y regístralo** en `country_config/{iso2}.yaml` (lo consume
`attribute_presidency.py`, que ya generaliza 12 variantes):

```yaml
presidency:
  scope: session | segments          # session = un presidente; segments = cambia dentro
                                     # (el presidente de APERTURA sale siempre de la carátula/Prolegomena)
  segments:                          # solo si scope: segments
    pattern: '\(Ocupa la Presidencia el se[ñn]or ([^)]{2,50})\)'   # DESCUBIERTO, no adivinado
```

Por cada sesión, meta registra en su JSON la **presidencia como lista de tramos** (apertura + relevos),
no un único `president`. Reutiliza la maquinaria existente (no reimplementar):
`presidencia_desde_fuente.py` (saca el NOMBRE desde `extracted/`, p.ej. BR `O SR. PRESIDENTE (Ramez
Tebet)`), `presidencia_declarada.py` (atribuye por tramo leyendo a quién nombra el acta),
`attribute_presidency.py` (lo aplica aguas abajo en match) y `audit_presidency_gender.py` (el
JUEZ por tramo: contrasta el sexo de la persona atribuida con el género del vocativo contiguo —
un control que no comparte nada con la atribución). Ver [[auditoria_presidencias_padron]].

⚠ Descubre el patrón de relevo sobre una muestra repartida por TODO el período y verifícalo (misma
disciplina que 0b): la mención de relevo aparece a partir de cierta época y con formas distintas.

### Paso 0d — Qué más trae la cabecera

La misma fórmula suele declarar **fecha, tipo de sesión, número y legislatura**. Descúbrelos en la
misma pasada: en BR `TIPO DA SESSÃO` resolvió 93.122 filas de `session_type` (aflorando la categoría
`no deliberativa`, 47.239 filas, que estaba escondida bajo el cajón `otra`); en PE la cabecera trae
período legislativo, número de sesión y turno.

⚠ **La fecha y el número deben salir de la fórmula de cabecera, nunca del nombre de archivo en
silencio** (regla previa, mantenida): un regex no anclado captura la PRIMERA fecha del texto, que
suele ser una referencia a un acta anterior. Inspecciona 3-5 textos y confirma que el patrón casa
con la fórmula, no con las referencias. El número del nombre de archivo puede ser el del boletín,
distinto del de sesión (verificado en ES).

### Paso 0e — Resto de la configuración

Lee también: `session_type_keywords`, `meta.date_locale`, `country`, `threshold_auto` (0.85),
`threshold_flag` (0.65).

⚠⚠ **`meta.head_lines` / `meta.tail_lines` — LA VENTANA DE CABECERA ES POR PAÍS** (`tr-0095`).
`extract_meta.py` busca los campos en `lines[:head_lines] + lines[-tail_lines:]`, con default
**30/10**. En un acta cuya página 1 empieza por el folio y el pase de lista, la FECHA cae fuera de
las 30 primeras líneas — y entonces **gana la de la COLA, que en muchos diarios anuncia la sesión
SIGUIENTE**. Medido en PE: `1996-10-17_PLO-1996-13` salía fechado el 18 porque el acta termina con
«viernes 18 de octubre de 1996»; 109 sesiones con la fecha adelantada un día.

**Mide la distribución antes de fijarla**: en PE la fecha aparece en la línea 12 de mediana, 34 en
el p90, 62 en el p99 y 67 como máximo, así que se puso `head_lines: 80`. Subir el valor «por si
acaso» tampoco es gratis — una ventana ancha admite ruido: en PE aparecieron 3 divergencias de −1
día que la ventana de 30 no producía. Efecto de fijarla bien: `date_source=text` 2.726 → 3.040,
presidencia 88,5 % → 99,5 %, halts 309 → 10.

⚠ `meta.date_year_range: [min, max]` — descarta años imposibles del OCR y las fechas de leyes
CITADAS de otra época. Decláralo siempre; es barato y evita que una cita gane la fecha.

---

## Paso 1 — Determinar lista de sesiones

**`--session YYYY-MM-DD`**: una sola sesión.

**`--batch YYYY-MM`**: todas las sesiones cuyo session_id empieza por `YYYY-MM`:
```bash
ls source/{iso2}/extracted/ | grep "^YYYY-MM"
```

**`--all`**: todas:
```bash
ls source/{iso2}/extracted/
```

Filtra sesiones con `skills.diaries-meta.status == "complete"` en el estado, salvo `--force`.

---

## Paso 2 — Procesar cada sesión

### 2a. Verificar prerequisito

```bash
ls "source/{iso2}/extracted/{session_id}.txt" 2>/dev/null
```

Si no existe: registra error "Texto extraído no encontrado. Ejecuta diaries-extract primero." y salta.
(Si por algún motivo faltara `extracted/` pero existe `corrected/`, úsalo como respaldo.)

### 2b. Crear directorio de salida

```bash
mkdir -p source/{iso2}/meta/
```

### 2c. Extracción determinista

Si `--dry-run`: imprime el comando que se ejecutaría y salta.

Si no es dry-run:
```bash
python ~/.claude/skills/diaries-lib/lib/utils/extract_meta.py \
  --input "source/{iso2}/extracted/{session_id}.txt" \
  --config "country_config/{iso2}.yaml" \
  --session-id {session_id} \
  --country {iso2}
```

Lee el JSON de stdout. Estructura esperada:
```json
{
  "session_id": "1932-02-12",
  "date": "1932-02-12",
  "session_number": "45",
  "session_type": "ordinaria",
  "legislature": "II República",
  "president": "El Presidente",
  "fields_missing": ["session_number", "president"],
  "confidence_by_field": {
    "date": 0.95,
    "session_type": 0.88,
    "legislature": 0.72
  }
}
```

Guarda el resultado parcial. Los campos en `fields_missing` necesitan resolución LLM.

### 2d. Resolución LLM para campos faltantes

Si `fields_missing` está vacío: salta este paso.

Lee las primeras 30 líneas del archivo de texto:
```
Read → source/{iso2}/extracted/{session_id}.txt
(offset: 0, limit: 30)
```

Para cada campo faltante, analiza el texto con tu propio juicio:

> ## ⚠ REGLA GENERAL — el CONTENIDO manda; el nombre de archivo solo si es IMPOSIBLE sacarlo del texto
>
> Vale para **todos** los metadatos de sesión —`date`, `session_number`, `session_type`,
> `legislature`, `president`—, no solo para la fecha. El orden es siempre el mismo:
>
> 1. **Contenido del documento.** Se intenta SIEMPRE, y se intenta de verdad: sondear 40
>    documentos repartidos por todo el período antes de concluir que un campo no está.
> 2. **Nombre de archivo.** Solo ante la **imposibilidad** de extraerlo del contenido. Se marca
>    la procedencia (`*_source = filename`) para que se pueda auditar y revisar después.
>
> **«No lo encontré a la primera» no es imposibilidad.** El nombre parece autoritativo porque
> es limpio y regular, y por eso ha engañado cuatro veces en este proyecto: año de 3 dígitos en
> PY, fecha imposible `1009-10-08`, número de acta tomado por año en EC, y **429 sesiones de CL
> declaradas sin fuente** cuando estaban todas —el nombre usaba `AAAAMMDD` sin guiones y el
> patrón solo casaba con guiones—.
>
> **Cómo se comprueba que la imposibilidad es real** (GT, 2026-08-03, sonda de 60 documentos):
>
> | campo | en el contenido | veredicto |
> |---|---|---|
> | `session_type` | **60/60** (`SESIÓN ORDINARIA`) | del CONTENIDO — el nombre era prescindible |
> | `session_number` | **0/60** | imposible → nombre como último recurso, legítimo |
>
> Y cuando las dos vías existen, **se contrastan**: en GT el contenido confirmó el tipo derivado
> del nombre en 1.863 de 1.863 casos, 0 discrepancias. Ese contraste es lo que convierte un
> valor plausible en un valor verificado; sin él no se sabe si el nombre acierta o miente.

**`date`** ⚠ CAMPO CRÍTICO. **JERARQUÍA DE PRIORIDAD DE FUENTES** (de mayor a menor autoridad — el
nombre de archivo es lo ÚLTIMO, nunca lo primero):
1. **Cabecero corrido** (el encabezado institucional repetido en CADA página, votado por mayoría) →
   **MÁXIMA autoridad**: es redundante y robusto. Ver el bloque de RESOLUCIÓN más abajo.
2. **Masthead / fórmula de cabecera de portada** ("MONTEVIDEO, …" / "SESIÓN … DE FECHA …") →
   autoritativo SOLO si el cabecero corrido lo corrobora; por sí solo es un ÚNICO punto de fallo
   (un OCR/typo lo arruina). NO tomes la primera fecha del texto (un diario cita actas/decretos): ánclala.
3. **Nombre de archivo (`session_id`)** → **SOLO ÚLTIMO RECURSO**. **Puede contener errores**
   (catalogación corrida ±1 día, typos). Se usa únicamente cuando NI el cabecero corrido NI el masthead
   dan una fecha fiable. **Nunca prevalece sobre el cabecero: si discrepan, gana SIEMPRE el cabecero.**

Reglas de `date_source` que aplica la PRIMERA PASADA determinista (`extract_meta.py`, que solo ve el
masthead y el nombre); el cabecero corrido las CORRIGE en el paso de RESOLUCIÓN:
- `text` → fecha del masthead; **verifícala contra el cabecero corrido antes de aceptarla**.
- `date_mismatch: true` (masthead ≠ nombre archivo) → **NO marques FLAG por la sola discrepancia con el
  nombre** (el nombre es solo un cotejo débil y puede ser el erróneo): resuélvelo con el VOTO DEL
  CABECERO CORRIDO, que es autoritativo sobre el nombre.
- `filename_fallback` (el masthead no dio fecha) → intenta PRIMERO el VOTO DEL CABECERO CORRIDO; el
  nombre de archivo solo queda como valor de último recurso (FLAG) si el cabecero tampoco resuelve.
- sin fecha en el cabecero, el masthead NI el nombre → **HALT**.
Si `session_date_regex` no captura la cabecera, corrígelo (ánclalo).

> ### ⚠ `date: null` NO es un campo vacío: es una sesión que DESAPARECE de todo filtro por año
>
> **Caso real (EC, 2026-08-15).** 38 sesiones acabaron con `date: null` porque ni el cabecero ni el
> masthead dieron fecha y el identificador no contenía ninguna. Nadie lo notó: `meta` no marcó HALT
> y el pipeline siguió. Meses después, el re-OCR con LLM acotó su alcance con
> `int(meta["date"][:4]) < 2000` — y esas 38 sesiones, **todas anteriores a 2000**, quedaron fuera
> del reproceso **en silencio**. Se descubrieron por casualidad, al montar el árbol híbrido de OCR.
>
> La lección no es «rellenar el hueco»: es que **un nulo se propaga como un filtro**. Cualquier
> etapa posterior que seleccione por año excluye la sesión sin decirlo, porque `None < 2000` no
> es verdadero y tampoco es un error. El daño es proporcional a lo caro que sea lo que se saltó:
> aquí, quince días de GPU.
>
> **Obligatorio, en este orden:**
>
> 1. **Antes de aceptar `date: null`, intenta derivar al menos el AÑO del `session_id`.** Los
>    identificadores parlamentarios casi siempre lo llevan, aunque no en forma de fecha:
>
>    | forma en el `session_id` | ejemplo | año |
>    |---|---|---|
>    | año de 4 cifras | `ANC-1998-007` | 1998 |
>    | **bienio legislativo** (dos pares consecutivos) | `CE-79-80-012`, `PCL-83-84-012` | 1979, 1983 |
>    | bienio al final | `CE-031-97-98` | 1997 |
>    | numeración de legislatura (NO datable) | `CE-22-076`, `CO-26-100` | — |
>
>    El bienio es el patrón que se escapa: `79-80` no es un año de cuatro cifras y ningún regex de
>    fecha lo captura. En EC recuperó **26 de las 38**.
>
> 2. **Escribe `date_year_only: {año}` y `date_source: "session_id_year"`** cuando solo se pueda
>    derivar el año. Es información incompleta pero USABLE: sirve para acotar alcances, ordenar por
>    época y decidir qué motor de OCR corresponde. Deja `date` en `null` — no inventes día y mes.
>
> 3. **HALT si no hay ni año.** Sin año la sesión no es ubicable en el tiempo y cualquier etapa
>    posterior la tratará mal. Que aparezca en la lista de HALT es exactamente lo que se quiere:
>    obliga a mirarla.
>
> 4. **Al cerrar el skill, informa del recuento**, aunque sea cero:
>    `date resuelta: N · solo año (session_id): N · sin fecha (HALT): N`. Un cero explícito es
>    información; la ausencia de la línea no lo es.
>
> **Y para quien consume `meta` aguas abajo:** filtrar por año exige decidir qué se hace con los
> nulos **de forma explícita**. `[s for s in ses if año(s) < 2000]` los descarta callando.
> Escribe la rama del nulo o cuenta cuántos quedaron fuera; si no, el filtro miente.
⚠ El parser de meses debe cubrir las VARIANTES LOCALES (p.ej. rioplatense "setiembre" sin 'p') y el
ordinal de día ("1º"/"1º."); si faltan, la fecha del texto se pierde y cae a `filename_fallback` en masa.

> **RESOLUCIÓN de la fecha por VOTO DEL CABECERO CORRIDO** (autoritativo sobre el masthead Y sobre el
> nombre de archivo) — ejecútalo SIEMPRE que `date_source` sea `filename_fallback` o `date_mismatch`,
> y úsalo también como verificación cuando dudes del masthead. El masthead de portada
> ("MONTEVIDEO, …") es UN único punto de fallo (un OCR/typo y la fecha sale mal). Pero el **cabecero
> corrido** que el diario imprime en CADA página ("… CÁMARA DE REPRESENTANTES &lt;día&gt; &lt;fecha&gt;")
> se repite decenas-cientos de veces y, votado por mayoría, es robusto. En el rediseño 2026-08
> `diaries-extract` es FIEL por defecto y `extracted/` CONSERVA el cabecero de cada página: el
> voto se hace sobre `extracted/{session_id}.txt` DIRECTAMENTE. Solo si una fuente legada se
> extrajo con el `--strip-headers` de compatibilidad (y no se ha re-extraído), recurre a las
> páginas OCR `source/{iso2}/ocr/{session_id}/page_*.txt` o a
> `pdftotext -layout source/{iso2}/raw/{session_id}.pdf`.
>
> Procedimiento (validado en UY 2026-06-17: resolvió **140 de 160** FLAG de fecha):
> 1. Toma `extracted/{session_id}.txt` — la capa fiel, con el cabecero repetido por página —
>    ignorando los `---PAGE N---` (solo si esa capa viene de un `--strip-headers` legado: páginas
>    OCR o `pdftotext -layout` del PDF).
> 2. De las líneas ancladas al **nombre institucional de la cámara** (regex OCR-tolerante, p.ej.
>    `C[ÁA][MNH]ARA\s+DE\s+REPRESENTANTES` en UY; ajústalo al país), extrae la fecha que aparece EN LA
>    MISMA LÍNEA. Así descartas las fechas de antecedentes/decretos del cuerpo. Suma el masthead con peso 1.
> 3. **Voto mayoritario** de esas fechas (parsea con la tabla de meses; tolera grafías locales y ordinales).
> 4. Decide según la mayoría del cabecero (≥2 votos) frente al nombre de archivo:
>    - **== nombre de archivo** → el masthead era el error → `date` = esa fecha → **complete**.
>    - **= nombre − 1 día** → el NOMBRE está corrido +1 (artefacto de catalogación: masthead + cabecero +
>      hora de apertura coinciden en el día real) → adopta la fecha del cabecero como autoritativa,
>      **aunque `date` difiera de `session_id`** (el `session_id` es solo la clave interna del pipeline;
>      la columna `date` del corpus debe llevar la fecha REAL) → **complete**.
>    - domina a **&gt;1 día** y el nombre es del tipo `YYYY-MM-01` → es un **COMPILATORIO multi-sesión**
>      (el PDF abarca varias sesiones del mes) → mantén **FLAG** con la evidencia de votos (división manual).
>    - sin mayoría fiable → mantén **FLAG**.

**`session_number`**: del TEXTO anclado a la cabecera. Validar contra el nombre de archivo; discrepancia
→ FLAG. Si no hay en el texto: vacío (no inventar).

**`session_type`**: clasifica según las palabras clave de `session_type_keywords` en el config. Si no hay coincidencias explícitas pero el texto es una sesión normal del parlamento → `ordinaria` con confianza 0.65.

> ⚠⚠ **El motor compone `\b{re.escape(kw)}\b`, con el ESPACIO LITERAL** (medido 2026-08-25).
> Una palabra clave de varias palabras —`SESIÓN ORDINARIA`— **no casa** cuando el acta compone
> `SESIÓN␣␣␣␣␣ORDINARIA`, que es lo normal en una carátula justificada. Daño medido en el corpus
> **publicado** de DO: `session_type` = `desconocida` en **1.613 de 2.126 filas (75,9 %)**; con
> `\s+` se puebla al 100 %. También pierden AR (+11), BR (+4) y MX (+1) sobre unos cientos.
> **Comprueba SIEMPRE tus keywords de varias palabras contra el texto con espacios múltiples**, y
> si el motor no lo tolera, clasifica con tu propio patrón y dilo.

**`legislature`**: busca el nombre de la legislatura en el encabezado del documento. Compara con el valor `legislature` en country_config.

**`president`**: aplica el patrón de `meta_patterns.president` descubierto y validado en el Paso 0, con su `ambito` registrado — **no** un número fijo de líneas: en PY el nombre está a más de 900 caracteres de su etiqueta, y en PE en la 2ª–3ª página. Si el patrón no dispara en una sesión concreta, deja el campo vacío y añádelo a `fields_missing`; **no** rellenes con un canónico por defecto, que enmascara la ausencia y fue lo que dejó a PY con la clave creada y vacía sin que nadie lo notara.

Para cada campo resuelto por LLM, registra internamente la confianza de tu extracción (0.0–1.0).

### 2e. Construir el JSON de metadatos completo

Combina los resultados del script y la resolución LLM. Calcula la confianza final:

**Peso por campo**: cada campo vale 0.20 (5 campos × 0.20 = 1.0)

**Contribución de cada campo**:
- Encontrado por regex → peso completo (0.20)
- Encontrado por LLM → peso × 0.85 (0.17)
- No encontrado → 0.0

**Override CRÍTICO de `date` (independiente del peso):**
- Fecha **RESUELTA por el VOTO DEL CABECERO CORRIDO** (mayoría clara que confirma el nombre, o que lo
  corrige por estar corrido) → la fecha es autoritativa: **puede ser AUTO/complete** (el cabecero ya es
  la fuente más fiable; no requiere revisión humana adicional).
- `date_source == "filename_fallback"` o `date_mismatch == true` **y el cabecero NO resolvió** (sin
  mayoría fiable, o compilatorio multi-sesión) → la sesión NO puede ser AUTO: forzar **FLAG** como
  mínimo. **La fecha del nombre de archivo nunca se acepta sin revisión humana** — es el último recurso
  y puede contener errores.
- `date_source == "missing"` y el cabecero tampoco da fecha → **HALT**.

```
confidence = suma de contribuciones de los 5 campos
```

Los 5 campos ponderados son: `date`, `session_number`, `session_type`, `legislature`, `president`.

### 2f. Escribir el JSON de metadatos

Escribe con Write:
```
source/{iso2}/meta/{session_id}.json
```

Estructura exacta:
```json
{
  "session_id": "{session_id}",
  "date": "{YYYY-MM-DD o cadena de fecha}",
  "session_number": "{número o null}",
  "session_type": "{ordinaria|extraordinaria|solemne|especial|null}",
  "legislature": "{nombre de legislatura o null}",
  "president": "{nombre normalizado o null}",
  "presidency": {
    "scope": "session|segments",
    "segments": [
      {"name": "{presidente de apertura}", "via": "prolegomena"},
      {"name": "{nombre del relevo}", "via": "relevo"},
      {"name": null, "via": "back_to_base"}
    ]
  },
  "country": "{iso2}",
  "source_file": "source/{iso2}/extracted/{session_id}.txt",
  "confidence": {valor_float}
}
```

**`presidency` — el campo por TRAMOS que promete el Paso 0c-bis**, alineado con la maquinaria
existente, no una forma nueva:

- `segments` es la SECUENCIA de declaraciones en orden de documento: la apertura de la
  carátula/Prolegomena (`via: prolegomena`) más los relevos anunciados en el cuerpo (`via:
  relevo`). `via: back_to_base` con `name: null` es el relevo SIN nombre («reasume la
  Presidencia» a secas) — el centinela que `attribute_presidency.py` llama `VUELTA` y que
  devuelve la mesa al titular; sin registrarlo, el tramo del vicepresidente no se cierra nunca.
  Si el país es `scope: session`, la lista tiene un solo elemento.
- **Qué consume cada pieza:** `attribute_presidency.py` con `sources: - from: meta` lee un campo
  ESCALAR por sesión (su `field`, default `president`) clavado por `date`; el ordinal de
  intervención de cada tramo lo sitúa él mismo sobre `tagged/` con `segments.pattern` — meta
  corre ANTES de tag y no puede dar ordinales. `presidency.segments` es el registro verificable
  de la secuencia (cuántos relevos, qué nombres, si resuelven contra el padrón) sobre el que
  `presidencia_declarada.py` atribuye por tramo y `audit_presidency_gender.py` juzga.
- **`president` (singular) SE MANTIENE por compatibilidad y se DERIVA**: es
  `presidency.segments[0].name` (la apertura). Es el valor que consume la fuente `from: meta`
  de `attribute_presidency.py`. No se rellena con ningún canónico por defecto (regla del 2d).

### 2g. Actualizar estado

```bash
python ~/.claude/skills/diaries-lib/lib/utils/update_state.py \
  --country {iso2} \
  --skill diaries-meta \
  --session {session_id} \
  --status {complete|flag|halt} \
  --confidence {valor} \
  --output "source/{iso2}/meta/{session_id}.json"
```

---

## Paso 3 — Resumen final

```
Resumen diaries-meta — {iso2}
─────────────────────────────────────────────
  AUTO  (complete): {N}
  FLAG  (revisar):  {N}
  HALT  (detenido): {N}
  SKIP  (ya hecho): {N}
  ERROR:            {N}
─────────────────────────────────────────────
  Total procesadas: {N}

Cobertura de campos (sobre total de sesiones procesadas):
  date:            {N} / {total}
  session_number:  {N} / {total}
  session_type:    {N} / {total}
  legislature:     {N} / {total}
  president:       {N} / {total}
```

Si hay casos FLAG o HALT:
```
Hay {N} sesiones que requieren revisión.
Ejecuta: /diaries-review --country {iso2}
```
