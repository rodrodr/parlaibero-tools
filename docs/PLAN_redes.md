# Plan · Dos herramientas de red: `cooccurrence_network` y `mention_network` (motor 0.5.0)

> **Estado: hecho (14-oct), sin publicar ni confirmar en git.** Fases A–E completas: motor 0.5.0 y luz-mcp 0.2.0
> construidos y probados (57 pruebas del motor con las regresiones; 9 de luz; batería de 21 llamadas idéntica a la
> 0.4.0; prueba de punta a punta por el protocolo MCP). Publicar en PyPI lo hace el investigador.
> Decisiones del investigador: 1) NPMI sin redondear; 2) `min_co` proporcional a N; 3) Leiden (portado del
> explorador, paridad exacta); 4) por defecto solo `reference`; 5) el Anexo se queda en local.
> Origen: especificación del investigador (14-oct) y prototipo construido ese día sobre la biblioteca
> `golpe_8jan` (registro en `~/.parlaibero/query_log.jsonl`, 10:29–10:58 UTC).
> **Requisito transversal del investigador:** son herramientas GENERALES, para cualquier biblioteca sobre cualquier
> tema en cualquiera de los 16 países. Nada del caso brasileño puede quedar escrito en el código.

---

## 1. Lo que se ha comprobado antes de planificar

| comprobación | resultado |
|---|---|
| Biblioteca `golpe_8jan` | 3 073 intervenciones; **2 949 desde el 8-1-2023** (incluye una ventana previa, del 31-10-2022 al 7-1-2023: el test debe pasar `date_from`). |
| El «Anexo» con las 47 entidades | **No venía en el texto pegado.** Recuperado del registro de consultas del prototipo: es la lista de `query_sql` de las 10:58. Guardado en `docs/anexo_golpe_8jan.tsv` (§9, decisión 5). |
| Cifras de regresión de la especificación | **Reproducidas exactamente**: N = 2 949, 190 aristas, Σco = 19 989, Σco_izq = 12 605, Σco_PL = 5 793, ΣNPMI = 35,44. |
| **Por qué salen 190** | El prototipo **redondea el NPMI a dos decimales ANTES de aplicar `min_npmi`**: una arista con NPMI 0,095 pasa como 0,10. Con el umbral sobre el valor sin redondear salen **181 aristas, Σco 18 986, Σizq 12 054, ΣPL 5 453, ΣNPMI 34,54** (decisión 1). |
| Colapso de nombres sin código brasileño | El prototipo reescribía a mano las variantes «nombre + apellido» de una familia de políticos con el mismo apellido. El mecanismo general del §3.2 (exclusión por entidad, y a igual posición gana la coincidencia más larga) **reproduce las cifras exactas**, sin una línea específica de Brasil. |
| Etiquetas de partido | Los datos dicen `PCDOB` y la especificación `PCdoB`: las etiquetas se casan sin distinguir mayúsculas. |
| Padrones de los 16 países | Todos tienen fecha de inicio de mandato. Las fechas de fin están casi completas: falta en Brasil el 23 % y en Guatemala el 14 % (son mandatos abiertos, no huecos). Los nombres llegan en formatos distintos: «NOMBRE APELLIDO» o «APELLIDO, NOMBRE»; Brasil solo trae el nombre parlamentario; Colombia no tiene columna de nombre de pila. El nomenclátor del §4 tiene que admitirlos todos. |

---

## 2. Dónde vive el código

Las dos herramientas van en el **motor** (`parlaibero_mcp/networks.py` y `charts_network.py`), no en el servidor de
ParlaIbero. Así luz-mcp las hereda con su perfil, sin copiar nada. En Luz, los grupos naturales son
`party_family` y `reg_family`, y no hay sexo.

Ambas son de **solo lectura** sobre el corpus. Escriben únicamente en `output_dir`, que debe ser una ruta absoluta;
no sobrescriben nada salvo con `overwrite=true`. Quedan registradas en `query_log`.

Versión: **motor 0.5.0, y luz-mcp 0.2.0**, que hereda las dos herramientas. Puerta: la batería de 21 llamadas tiene
que dar la misma salida que la 0.4.0.

---

## 3. `cooccurrence_network`

### 3.1 Parámetros

| parámetro | tipo | por defecto | nota |
|---|---|---|---|
| `library` | str | obligatorio | |
| `date_from`, `date_to`, `exclude_chair`, `max_turn_words` | | los del motor | Se aplican sobre la biblioteca, igual que en las demás herramientas. |
| `entities` | lista `{name, type, pattern, exclude?}` | omitido → modo `auto` | `type` es `persona`, `institucion` o `concepto`. `pattern` y `exclude` son regex RE2 sobre el texto normalizado (§3.2). |
| `groups` | `{grupo: [etiquetas]}` o el nombre de una columna | sin grupos | Ver §3.3. Se admiten hasta 2 grupos de contraste y un tercero, «resto». |
| `min_co` | int | **automático**: `max(5, round(N/120))`, que da 25 para N = 2 949 | Siempre se informa del valor usado (decisión 2). |
| `min_npmi` | float | 0,10 | Se compara con el valor sin redondear (decisión 1). |
| `max_nodes` | int | 60 | Nodos de mayor `n`, después de los filtros. |
| `max_entities` | int | 150 (tope duro: 400) | Para que el coste sea predecible. |
| `kwic_per_entity` | int | 5 | Muestra con semilla fija. |
| `seed` | int | 1 | Fija las muestras, las comunidades y la posición inicial del grafo. |
| `output_dir`, `formats` (`html`, `csv`, `json`, `md`), `overwrite` | | | |

### 3.2 Cálculo

- **La unidad es la intervención**, y N es el número de intervenciones de la biblioteca después de los filtros.
- **Texto normalizado:** `strip_accents(lower(text))`. Los patrones se escriben sobre ese texto.
- **Colapso de variantes, en general y sin listas de un país:**
  1. Cada entidad puede llevar un `exclude`: lo que coincide con su patrón dentro de un tramo de `exclude` no cuenta.
  2. Si dos entidades coinciden en tramos solapados, **gana la coincidencia más larga**. «maria pereira» es
     de la entidad «Maria Pereira» y no suma a «Pereira».

  Con estas dos reglas se reproduce el prototipo, como recoge el §1.
- **Métricas por arista:**
  - `co` y `co` por grupo, según el grupo del orador de la intervención;
  - Jaccard: co / (nₐ + n_b − co);
  - NPMI: ln(p(ab) / (p(a)·p(b))) / (−ln p(ab)), con **NPMI = 1 si co = N**.
- **Métricas por nodo:**
  - `n` y `n` por grupo;
  - el sesgo, (n₁/N₁ − n₂/N₂) / (n₁/N₁ + n₂/N₂) ∈ [−1, 1], solo si hay dos grupos de contraste;
  - el grado ponderado y la intermediación;
  - la comunidad (decisión 3).
- **Bibliotecas con varios países:** una red **por país** por defecto, con su N, sus grupos y su sesgo; se puede
  pedir una red conjunta. La herramienta avisa si en una biblioteca con BR o PT hay patrones que solo tienen forma
  en español, o al revés.

### 3.3 Grupos, sin clasificación política incorporada

**El MCP no trae ningún mapa por defecto de partido a bloque.** Sería una clasificación política discutible metida
dentro de la herramienta, y además distinta en cada país.

- **Sin `groups`:** los nodos se colorean por la comunidad, y la tabla da `n` por partido (los 8 primeros más «Otros»).
  No hay sesgo.
- **Con `groups` como mapa:** hasta dos bloques de contraste más «resto». El resultado lista las etiquetas de
  partido que no quedaron asignadas, con cuántas intervenciones tiene cada una.
- **Con `groups` como nombre de columna:** se usan las columnas de grupo del perfil (`sex`, `party`, o
  `party_family`/`reg_family` en Luz).
- **Nombres de columna genéricos:** `co_g1`, `co_g2`, `co_resto`, con las etiquetas de los grupos en los metadatos.
  `co_izq` y `co_pl` eran del caso brasileño.

### 3.4 Modo `auto`

Sin `entities`, la herramienta **no construye la red**: devuelve candidatos para que el usuario los valide. Son
candidatos generales, para cualquier lengua y tema:

- secuencias en mayúscula frecuentes en el texto original (nombres propios), cotejadas con el padrón del país;
- siglas;
- las palabras distintivas de la biblioteca frente al resto de su cámara (`distinctive_words`).

Cada candidato viene con su `n`, un patrón propuesto y 3 líneas KWIC. La red se construye en una segunda llamada,
con la lista ya confirmada.

### 3.5 Calidad de los datos

- **Informe de ambigüedad:** para cada entidad, 5 líneas KWIC aleatorias (con semilla) y alertas automáticas:
  - el patrón es corto (menos de 5 caracteres o una sigla);
  - el patrón es una palabra común en la lengua del país;
  - el patrón coincide con un apellido de varios diputados del padrón en el periodo.

  La lista de la especificación (`dino`, `lira`, `supremo`, `imagens`, `pf`) sale de estas reglas y no hay que
  escribirla a mano.
- **Aviso de azar:** aristas con NPMI alto y `co` cerca del umbral.
- **Aviso de turnos largos:** el de siempre, si `max_turn_words` no está fijado.
- **Autocomprobación en código:** se vuelve a leer el JSON que quedó dentro del HTML escrito, y Σco, Σco por grupo
  y ΣNPMI tienen que coincidir con el resultado del cálculo. Si no coinciden, la herramienta falla; no escribe un
  HTML incorrecto.

### 3.6 Salidas

- **La respuesta** lleva el resumen exploratorio:
  - N, nodos, aristas y densidad;
  - las 15 primeras aristas por `co` y por NPMI;
  - los nodos y las aristas con más sesgo hacia cada grupo;
  - centralidades y comunidades;
  - los avisos;
  - las rutas de los archivos.
- **`summary.md`:** lo mismo, más la cita de cada conjunto (DOI y versión) y los parámetros.
- **CSV y JSON:** nodos y aristas.
- **HTML autocontenido:**
  - d3 v7.8.5 desde cdnjs; tema claro y oscuro con tokens CSS (`prefers-color-scheme` y `data-theme`);
  - **forma** según el tipo, **tamaño** √n, **grosor** según `co`, **opacidad** según NPMI;
  - **color** según el sesgo, en una escala divergente de 7 pasos validada con el script de `dataviz`, o según la
    comunidad si no hay grupos;
  - controles: los deslizadores de umbral, «separar por grupo», etiquetas, restablecer vista y la métrica de tamaño;
  - foco de teclado y vecinos resaltados; tooltip con `textContent`; un clic muestra las KWIC;
  - tabla gemela en `<details>`; funciona en móvil, sin desplazamiento horizontal.
- **Los datos van dentro del HTML con `json.dumps`, escapando `</`:** el texto de un discurso puede contener
  `</script>`. Nunca se transcribe nada a mano.

---

## 4. `mention_network`

### 4.1 Parámetros

| parámetro | tipo | por defecto |
|---|---|---|
| `library`, `date_from`, `date_to`, `exclude_chair`, `max_turn_words` | | |
| `target_scope` | `speakers`, `external` o `both` | `both` |
| `external_actors` | `[{name, aliases, role}]` | ninguno; no se incorpora ninguna lista |
| `mention_kinds` | `reference`, `address` o ambos | `reference` (decisión 4) |
| `min_mentions`, `min_speakers`, `top_n`, `groups`, `seed` | | |
| `output_dir`, `formats`, `overwrite` | | |

### 4.2 Construcción

1. **Nomenclátor**, construido desde el padrón (`deputies`) y `speaker_name`, **restringido a los diputados con
   mandato en la fecha de cada intervención**. Eso elimina la mayoría de los homónimos en cualquier país.
   - **Alias que se generan:**
     - el nombre completo, en los dos órdenes;
     - el primer apellido y los dos apellidos;
     - el nombre parlamentario, que en Brasil y Portugal es el que se usa en el pleno.
   - **Los tratamientos** se tratan como configuración por lengua, no como código:
     - `es`: diputado/a, señor/a, señoría, honorable, ministro/a, presidente/a, senador/a;
     - `pt`: deputado/a, senhor/a, nobre deputado, V. Exa./Vossa Excelência, ministro/a, presidente/a.
2. **Homónimos:** un alias que corresponde a varios diputados en la misma fecha se resuelve con el tratamiento
   más el nombre, el partido citado junto al nombre o la sigla regional. Lo que no se resuelve va a
   `ambiguas.csv` y nunca se asigna al azar.
3. **Dos clases de mención** (decisión 4):
   - `address`: el orador se dirige a alguien, en segunda persona o con un vocativo («Deputado Fulano, V. Exa. sabe…»);
   - `reference`: habla de alguien en tercera persona («o nobre Deputado Fulano disse…»).

   **Las fórmulas genéricas sin nombre** («V. Exa.», «nobre colega», «Su Señoría») no se pueden resolver: se
   cuentan y se informa de ellas, pero no crean aristas.
4. **Exclusiones:** las automenciones, y la presidencia si `exclude_chair`.
5. **Arista A → B:** su peso es el número de intervenciones de A que mencionan a B. Se guardan también el total de
   menciones y el número de sesiones.
6. **Bibliotecas con varios países:** una red por país, porque un orador no puede mencionar a otro de otra cámara
   en el pleno. Los actores externos sí pueden ser comunes a varios países.

### 4.3 Análisis y salidas

- **Medidas:**
  - fuerza de entrada y de salida, reciprocidad, PageRank y comunidades;
  - la matriz grupo → grupo, normalizada por las intervenciones del grupo emisor;
  - el índice E-I;
  - los principales emisores y receptores;
  - los pares muy asimétricos;
  - una serie temporal opcional de las menciones recibidas por cada actor.
- **Visualización:**
  - grafo dirigido con flechas finas; tamaño según la fuerza de entrada;
  - color según el partido o el grupo, con 8 categorías como máximo más «Otros», paleta validada;
  - los actores externos con otra forma;
  - el mapa de calor grupo → grupo como vista alternativa, con su tabla gemela;
  - los mismos requisitos de accesibilidad, temas y móvil que la herramienta 1.
- **Cobertura del nomenclátor por país:** se informa de qué parte de los oradores de la biblioteca tiene alias
  utilizables. Los padrones son distintos en cada país, y eso condiciona lo que la red puede ver.

### 4.4 Validación (hecha el 14-oct, tres rondas)

Cada muestra la etiquetó a mano un revisor independiente que leía el contexto (y, si hacía falta, la intervención
entera y el padrón). Muestras: `golpe_8jan` (BR, 100 menciones) y `amnistia_ES` (ES, 50), sorteadas con semilla
entre las menciones resueltas. **Las reglas se corrigieron entre rondas, y cada ronda usa una muestra NUEVA.**

| ronda | BR: objetivo correcto | BR: clase correcta | ES: objetivo correcto | ES: clase correcta |
|---|---:|---:|---:|---:|
| 1 (reglas iniciales) | 86 / 100 | 67 / 100 | 48 / 50 | 38 / 50 (11 «?») |
| 2 | 96 / 100 | 87 / 96 | 49 / 50 | 48 / 50 |
| 3 | 100 / 100 | 100 / 100 | 50 / 50 | 48 / 50 |

⚠ La ronda 3 de BR es la primera con actores externos (antes un fallo los dejaba fuera): 75 de las 100 menciones
son de los tres actores externos declarados (el presidente, el expresidente y un juez del Supremo), solo 25 de diputados y ninguna por tratamiento. Para los diputados por
tratamiento la mejor cifra es la de la ronda 2 (66/67 por título legislativo).

**Ronda 4** (reglas casi finales, muestras nuevas):

- **Brasil solo diputados**, sin externos declarados y estratificada por licencia:
  - título legislativo: 35/35;
  - nombre completo: 21/25, con cuatro homónimos de fuera de la cámara;
  - tratamiento: **18/40**, casi todo «sr. X» por el expresidente cuyo apellido comparte un diputado.

  De ahí la decisión de que el tratamiento solo licencia un apellido, por defecto, **en español**: en España
  acertó 95 de 96 en tres rondas (31/31, 29/30 y 35/35; el único error, un presidente autonómico, lo caza ya
  la regla del nombre que continúa). Portugal no se ha medido: hereda el valor del portugués. `honorifics=` lo
  cambia.
- **Chile**, país en el que nunca se ajustaron las reglas: 60/60 en persona y 60/60 en clase. 24 de las 60
  menciones están en texto leído al acta (autores de un proyecto, reemplazos, votaciones).

**Lo que corrigió cada error, siempre con una regla general:**

- **Notas del Diario entre paréntesis** («(O Sr. X deixa a cadeira…)», «(El señor X: ¡Bravo!)»): pasan a la clase
  `editorial` y no cuentan. Eran el 11 de 50 en ES.
- **Complementos del título** («deputado FEDERAL Fulano»): se saltan; «federal» ya no es el diputado cuyo nombre
  parlamentario termina en «… da Federal».
- **Nombres de pila tomados por apellidos** («Dr. LUIZ Fulano»): sin coma, solo la última palabra del
  nombre es apellido seguro, y una palabra que el padrón usa más como nombre de pila no es alias por sí sola.
- **El nombre que continúa** (un militar y un presidente autonómico que comparten nombre o apellido con un
  diputado): si tras el apellido viene otro apellido
  del padrón o una palabra rara, es otra persona.
- **Género del título contra el sexo del padrón** («señor X» no es una diputada apellidada X).
- **Títulos en plural** («Srs. Deputados, Brasil…») no licencian un apellido.
- **El apellido de un actor externo declarado** («o sr. X» cuando el expresidente X está declarado y un diputado
  comparte su apellido) exige nombre completo.
- **«Nosso Senhor Jesus»** no es un tratamiento.
- **Vocativos:** se salta hacia atrás sobre las fórmulas de trato («grato, digníssimo presidente X», «caro colega
  deputado X», «o senhor, presidente X,»), y se reconoce el segundo de dos vocativos coordinados («Señora X y
  señor Y, …»).
- **Pares asimétricos y reciprocidad** solo entre quienes hablan en la biblioteca: un actor externo no puede
  responder.
- **Fallo:** los alias de los actores externos se comparaban como lista contra tupla y nunca casaban.

**Límite que queda, y su remedio:** un homónimo de fuera de la cámara con nombre completo (un exasesor
presidencial y un exministro que se llaman exactamente como dos diputados) se toma por el diputado. Declararlo como actor externo lo evita,
porque los externos se buscan primero.

**Cifras de regresión** (`tests/test_mentions.py`, opcional): `golpe_8jan` desde 2023-01-08, sin presidencia, con
los tres externos (lista local, fuera del repositorio) y los grupos izq/pl: N 2 949, 60 nodos, 312 aristas,
reciprocidad 0,0993, Σ intervenciones 2 408, Σ menciones 5 112, E-I entre diputados pl −0,327 · izq 0,582 ·
resto −0,071; resueltas 7 549, ambiguas 10, editoriales 370, automenciones 39.

**No hecho:** la serie temporal opcional de menciones recibidas (§4.3) queda para otra versión.

**Cambios del alcance durante la ejecución:** `honorifics=` (el tratamiento licencia un apellido por defecto solo
en español, medido); desempate de homónimos por el nombre de pila escrito tras el apellido; el modo `auto` ya no
propone tratamientos, meses ni acotaciones; la matriz grupo → grupo deja a los actores externos en su propia
columna, fuera de la escala de color, que se validó en claro y oscuro (texto de las celdas ≥ 5,39:1).

---

## 5. Pruebas

- **Sin red y sintéticas:**
  - el colapso de variantes, `exclude` y «gana la más larga»;
  - NPMI en sus extremos (co = N, co = 1);
  - el sesgo con un grupo vacío;
  - el escape de `</script>` y la autocomprobación del HTML;
  - las bibliotecas con varios países;
  - el nomenclátor con los dos formatos de nombre y con homónimos por fecha.
- **Regresión sobre `golpe_8jan`:** opcional (se activa con una variable de entorno) y se salta si la biblioteca
  no existe, porque depende de su base local. Con las 47 entidades, `date_from` 2023-01-08, `exclude_chair` y los
  grupos de la especificación, da 181 aristas, Σco 18 986, Σizq 12 054, ΣPL 5 453 y ΣNPMI 34,517 (sin redondear).
- **La batería de 21 llamadas,** idéntica a la 0.4.0.

---

## 6. Documentación y cita

- **Documentación del método:** en el README y en un recurso MCP `parlaibero://methods/networks`, con las
  definiciones, los límites y la lectura de `co` frente a NPMI (volumen frente a afinidad). `get_documentation`
  sirve los documentos depositados en Dataverse; el método no va ahí.
- **Cita:** el DOI y la versión de cada conjunto, en el pie del HTML y en `summary.md` (lo que la especificación
  llama `how_to_cite`).
- **⚠ Ejemplos públicos:** las 47 entidades de la regresión son casi todas políticos con nombre. Por la directiva de
  divulgación, **no pueden ser el ejemplo del README ni del sitio**. El ejemplo público usará conceptos e
  instituciones, o actores por su cargo.

---

## 7. Fases

| fase | contenido | puerta |
|---|---|---|
| A | `cooccurrence_network`, cálculo y resumen (sin HTML) | regresión de `golpe_8jan` y pruebas sintéticas |
| B | HTML de la herramienta 1 | validación de la paleta, autocomprobación, revisión visual en claro, oscuro y móvil |
| C | `mention_network`, cálculo | precisión medida sobre la muestra del §4.4 |
| D | HTML de la herramienta 2 | como en B |
| E | Documentación, CHANGELOG, motor 0.5.0 y luz-mcp 0.2.0 (los publica usted) | batería de 21 llamadas y prueba de punta a punta por el protocolo MCP |

---

## 8. Mejoras sobre la especificación

1. **Umbral sobre el NPMI sin redondear** (decisión 1).
2. **Colapso de variantes general** (`exclude` y «gana la más larga») en vez de la reescritura con nombres brasileños.
3. **Sin mapa de bloques incorporado:** grupos opcionales, etiquetas sin distinguir mayúsculas y un informe de lo
   que no se asignó.
4. **`min_co` proporcional a N,** porque 25 vacía una biblioteca de 300 intervenciones.
5. **Redes por país** en las bibliotecas con varios países.
6. **«Cortesía» separada en dos cosas:** dirigirse a alguien y referirse a él. Las fórmulas sin nombre no se pueden
   resolver.
7. **Nomenclátor restringido a los mandatos vigentes** en la fecha de cada intervención.
8. **Validación medida de `mention_network`** antes de fijar sus cifras de regresión.
9. **NPMI definido cuando co = N; datos escapados en el HTML; autocomprobación leyendo el archivo escrito.**
10. **Las alertas de ambigüedad salen de reglas,** no de una lista escrita a mano para un caso.

---

## 9. Decisiones que se le piden

1. **Umbral de NPMI.** ¿Sobre el valor sin redondear (recomendado), y con él cifras de regresión de **181 aristas,
   Σco 18 986, Σizq 12 054, ΣPL 5 453, ΣNPMI 34,54**? ¿O conservar el redondeo del prototipo, con 190 / 19 989 /
   12 605 / 5 793 / 35,44?
2. **`min_co` por defecto:** ¿proporcional a N (`max(5, N/120)`, recomendado) o fijo en 25?
3. **Comunidades: Louvain o Leiden.** Louvain (networkx, con semilla, Python puro) es lo que pide la especificación
   y apenas añade peso a la instalación. Leiden es el algoritmo que usted prefirió antes y el que ya usa el
   explorador (`35a_engine__leiden.js`); en Python necesita `igraph` y `leidenalg`, que hacen más pesada la
   instalación con `uvx`. Alternativa: portar a Python el Leiden del explorador, para que las dos herramientas den
   las mismas comunidades.
4. **Menciones:** ¿por defecto solo `reference` (hablar de alguien), o también `address` (dirigirse a él), con pesos
   separados?
5. **El Anexo de 47 entidades.** Lleva nombres de políticos. ¿Va al repositorio público como dato de la prueba, o se
   queda solo en local y la prueba de regresión se salta cuando no está?
