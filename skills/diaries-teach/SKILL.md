---
name: diaries-teach
description: "Explica cómo funcionan los skills diaries-* y guía al usuario por los caminos de uso típicos del pipeline ParlaIbero."
allowed-tools: [Read, Bash]
---

# /diaries-teach — Guía interactiva del pipeline ParlaIbero

Cuando el usuario invoca este skill, preséntate como guía del sistema y ofrece los caminos disponibles. Si el usuario ya indicó un contexto (país, problema, etapa), ve directamente al camino pertinente.

---

## Presentación inicial

Muestra esto si no hay contexto previo:

```
╔══════════════════════════════════════════════════════════════════╗
║         ParlaIbero — Pipeline de Diarios Parlamentarios          ║
║                     /diaries-teach                               ║
╚══════════════════════════════════════════════════════════════════╝

Soy el guía de este sistema. Puedo orientarte en:

  [1] ¿Qué es este sistema y cómo funciona?
  [2] Quiero procesar un país nuevo desde cero
  [3] Quiero retomar un pipeline interrumpido
  [4] Tengo un problema con un skill concreto
  [5] ¿Cómo funciona el sistema de confianza (AUTO/FLAG/HALT)?
  [6] ¿Cómo corrijo errores y propago correcciones?
  [7] Mapa completo de todos los skills
  [8] Quiero dejar constancia de una decisión metodológica

¿Por dónde empezamos?
```

Espera la respuesta del usuario y sigue el camino correspondiente. Si el usuario escribe texto libre en lugar de un número, detecta la intención y entra al camino más apropiado.

---

## CAMINO 1 — ¿Qué es este sistema?

Explica con tus propias palabras:

**El problema que resuelve:** Los diarios de sesiones parlamentarias (PDF o HTML escaneados) son documentos no estructurados con cientos de páginas. El corpus ParlaIbero necesita saber *quién dijo qué* en cada sesión, vinculado con datos biográficos del diputado (partido, distrito, sexo). Hacerlo a mano para decenas de países y miles de sesiones es inviable.

**La solución:** Un pipeline de 13 pasos que transforma cada documento fuente en filas de una matriz estructurada: `legislatura, sesión, fecha, orador, texto, partido, distrito, ...`

**El rol de Claude:** No es un script de Python que se ejecuta solo. Claude *es* el orquestador: lee las instrucciones de cada skill (`~/.claude/skills/diaries-*/SKILL.md`), ejecuta las utilidades deterministas cuando corresponde (`lib/utils/`), razona sobre los casos ambiguos, y decide cómo continuar.

**La arquitectura en una línea:**  
`PDF/HTML fuente` → `OCR (Ollama)` → `texto limpio` → `oradores etiquetados` → `matriz CSV` → `vinculación con diputados` → `standardize/{ISO2}_interventions.csv` canónico

Luego pregunta: *¿Quieres ver el mapa completo del pipeline o prefieres pasar directamente a un camino práctico?*

---

## CAMINO 2 — Nuevo país desde cero

Presenta el flujo completo con explicación de cada etapa. Usa este formato:

```
PASO 1 — Preparar las fuentes
─────────────────────────────
Coloca los archivos de sesiones en:
  source/{iso2}/raw/

Convención de nombres: YYYY-MM-DD.pdf  (o .html)
Si los archivos tienen otro formato de nombre, diaries-bootstrap
los detectará y te pedirá confirmación.

PASO 2 — Configurar el país
────────────────────────────
/diaries-bootstrap --country {iso2}

  Fase 1: examina 3-5 documentos automáticamente
    • detecta el formato (pdf_image / pdf_digital / html)
    • infiere patrones de oradores, fechas, numeración
    • asigna confianza a cada inferencia

  Fase 2: te pregunta solo lo que no pudo inferir
    • muestra evidencia antes de preguntar
    • cada respuesta elimina preguntas innecesarias

  Produce: country_config/{iso2}.yaml
           state/{iso2}/pipeline_state.json
           docs/{iso2}/onboarding_report.md

PASO 3 — Cadena de ingesta (por sesión)
─────────────────────────────────────────
/diaries-ocr       → OCR con Ollama si formato es pdf_image
/diaries-extract   → texto limpio + normalización Unicode
/diaries-correct   → párrafos e hifenaciones (determinista + tú)
/diaries-meta      → fecha, nº sesión, tipo, presidencia por tramos  (lee extracted/, la capa fiel)
/diaries-dedupe    → quita escaneos duplicados  ⚠ ANTES de tag, no después
/diaries-deputies  → opcional aquí: si hay pase de lista nominal, el padrón sale
                     de corrected/ y mejora el scoring de tag (--deputies)
/diaries-tag       → etiqueta oradores ⚠ skill más crítico
/diaries-matrix    → convierte texto etiquetado en filas CSV

  ⚠ Por qué meta y dedupe van ANTES de tag: el Paso 0c de /diaries-tag rankea las
  formas de marcador por frecuencia sobre todo el corpus para decidir cuáles entran
  al léxico. Si quedan sesiones duplicadas, sus formas se cuentan dos veces y esa
  calibración sale sesgada — y deduplicar después ya no lo arregla.

  Después de cada skill con FLAGs:
  /diaries-review --country {iso2}

PASO 4 — Resolución de entidades (a nivel país)
─────────────────────────────────────────────────
/diaries-deputies  → construye BD de diputados únicos
/diaries-match     → vincula cada speaker_raw con un id_dep
/diaries-review    → revisar los casos de baja confianza

PASO 5 — Finalización
───────────────────────
/diaries-merge        → enriquece la matriz con datos del diputado
/diaries-standardize  → esquema canónico (16 columnas)
/diaries-document     → genera metodología, diccionario, JSON-LD
/diaries-report       → informe final del proceso
```

Luego pregunta: *¿Quieres que te acompañe en el primer paso ahora mismo?*  
Si dice sí, invita directamente: `Dime el código ISO2 del país y confirma que tienes los archivos en source/{iso2}/raw/.`

---

## CAMINO 3 — Retomar pipeline interrumpido

```
Diagnóstico en tres pasos:

1. Ver el estado actual:
   /diaries-status --country {iso2}

   Interpreta la tabla:
   • Columna OK    → sesiones completadas con AUTO
   • Columna FLAG  → requieren tu revisión (/diaries-review)
   • Columna HALT  → error o confianza muy baja, intervención manual
   • Columna Pend  → aún no procesadas

2. Resolver los casos pendientes:
   /diaries-review --country {iso2}
   
   Para cada FLAG eliges:
   [A] Aceptar   → marcar como completo
   [C] Corregir  → anotar una corrección puntual
   [R] Reintentar→ re-OCR con MiniMax M3 (solo diaries-ocr)
   [E] Escalar   → convertir en HALT para revisión manual
   [S] Saltar    → revisar más tarde
   [Q] Salir     → interrumpir la revisión

3. Continuar desde donde se detuvo:
   /{skill_detenido} --country {iso2} --all
```

Pregunta qué país tiene interrumpido. Si lo dice, ofrece ejecutar `/diaries-status --country {iso2}` ahora mismo para leer el estado juntos.

---

## CAMINO 4 — Problema con un skill concreto

Pregunta: *¿Qué skill está dando problemas?* y *¿cuál es el síntoma?*

Según la respuesta, orienta así:

**diaries-bootstrap** — Si no infiere bien los patrones:  
→ Edita `country_config/{iso2}.yaml` directamente después del bootstrap.  
→ Los campos más importantes: `speaker_tag_patterns`, `session_date_regex`, `session_number_regex`.

**diaries-ocr** — Si la confianza es baja:  
→ Verifica que Ollama está corriendo: `ollama list` y comprueba que `Maternion/LightOnOCR-2:1b` aparece.  
→ Aumenta DPI en config: `ocr.dpi: 400` para documentos muy comprimidos.  
→ Si el modelo falla: el fallback `glm-ocr` se activa automáticamente.

**diaries-tag** — Si detecta pocos oradores (es el skill más crítico):  
→ Revisa `speaker_tag_patterns` en el YAML: ¿el patrón cubre las variantes reales del documento?  
→ Ejecuta sobre una sesión de prueba: `/diaries-tag --country {iso2} --session YYYY-MM-DD`  
→ Baja los umbrales si el corpus es irregular: en el YAML, `thresholds.diaries-tag.threshold_auto: 0.70`

**diaries-match** — Si muchos oradores quedan sin vincular:  
→ Revisa `deputies.csv`: ¿los nombres canónicos son los que aparecen en las sesiones?  
→ Inyecta una corrección de tipo `rule`:  
   `/diaries-feedback --country {iso2} --skill diaries-match --type rule --description "..."`  
→ Baja el umbral difuso: en config, `match.fuzzy_threshold: 70`

**diaries-standardize** — Error "archivo ya existe":  
→ Es la guardia del archivo canónico. Usa `--force` solo si estás seguro:  
   `/diaries-standardize --country {iso2} --force`

Para cualquier HALT: leer el `error_message` en `state/{iso2}/pipeline_state.json`:
```bash
python -c "
import json
state = json.load(open('state/{iso2}/pipeline_state.json'))
for sid, sess in state['sessions'].items():
    for skill, s in sess['skills'].items():
        if s['status'] == 'halt':
            print(sid, skill, s.get('error_message',''))
"
```

---

## CAMINO 5 — Sistema de confianza AUTO/FLAG/HALT

Explica con ejemplos concretos:

```
Cada skill devuelve una puntuación de confianza (0.0 – 1.0).

  ≥ 0.85  →  AUTO    Pipeline continúa sin interrumpir
  ≥ 0.65  →  FLAG    Caso registrado, tú revisas al final del bloque
  < 0.65  →  HALT    Pipeline se detiene, necesitas intervenir ahora

Ejemplos de cálculo:

  diaries-ocr:  confianza = 0.7 × media_páginas + 0.3 × página_más_baja
                (penaliza documentos con una página muy mala)

  diaries-tag:  confianza = n_auto / (n_auto + n_sin_tag + n_llm × (1 - conf_llm))
                (penaliza los oradores que Claude tuvo que inferir)

  diaries-match: confianza = n_matched_auto / n_speakers_únicos
                (porcentaje de oradores vinculados con alta certeza)

Umbrales por skill en country_config/{iso2}.yaml:

  thresholds:
    diaries-tag:
      threshold_auto: 0.80   ← más permisivo (corpus más difícil)
      threshold_flag: 0.60
    diaries-match:
      threshold_auto: 0.90   ← más estricto (vinculación es crítica)
      threshold_flag: 0.70
```

---

## CAMINO 6 — Correcciones y propagación

Explica los tres tipos con un ejemplo de cada uno:

```
TIPO 1 — punctual  (una sola sesión, no se propaga)
───────────────────────────────────────────────────
Cuándo: encontraste un error concreto en una sesión específica.

/diaries-feedback --country es --skill diaries-tag \
  --type punctual \
  --description "Sesión 1932-03-14: el bloque de pág. 7 es mesa directiva, no orador" \
  --from 1932-03-14


TIPO 2 — rule  (desde una sesión en adelante, re-procesa)
───────────────────────────────────────────────────────────
Cuándo: identificaste un patrón sistemático que afecta muchas sesiones.

/diaries-feedback --country es --skill diaries-tag \
  --type rule \
  --description "El patrón 'EL SR. MINISTRO' no estaba en speaker_tag_patterns" \
  --pattern "^EL SR\. MINISTRO" \
  --action "tag_as_speaker" \
  --from 1931-09-01

→ Automáticamente marca como PENDING todas las sesiones desde 1931-09-01.
→ Luego re-ejecuta: /diaries-tag --country es --all


TIPO 3 — strategy  (todo el skill, requiere --force)
─────────────────────────────────────────────────────
Cuándo: necesitas cambiar el enfoque completo (nuevo umbral, nueva lógica).

/diaries-feedback --country es --skill diaries-match \
  --type strategy \
  --description "Bajar umbral difuso a 70 para nombres compuestos gallegos"

→ Registrado en global_rules del estado.
→ Luego re-ejecuta: /diaries-match --country es --all --force
```

---

## CAMINO 7 — Mapa completo de todos los skills

Muestra este diagrama y explica brevemente cada nodo:

```
source/{iso2}/raw/  (PDF / HTML fuente)
         │
         ▼
  /diaries-bootstrap ──► country_config/{iso2}.yaml
         │                state/{iso2}/pipeline_state.json
         │
         ▼
  /diaries-ocr ──────────► source/{iso2}/ocr/{id}/page_NNNN.txt
  (solo si pdf_image)       [Ollama: LightOnOCR-2:1b → glm-ocr]
         │
         ▼
  /diaries-extract ──────► source/{iso2}/extracted/{id}.txt
  (texto limpio, NFC)
         │
         ▼
  /diaries-correct ──────► source/{iso2}/corrected/{id}.txt
  (párrafos + hifenación)   [determinista + Claude para ambiguos]
         │
         ▼
  /diaries-meta ─────────► source/{iso2}/meta/{id}.json
  (fecha, nº, tipo,          [regex + Claude para faltantes]
   legislatura, pdte)
         │
         ▼
  /diaries-dedupe ───────► cuarentena de sesiones duplicadas
  (a nivel país, sobre       [⚠ ANTES de tag: evita calibrar
   meta/ y corrected/)        el léxico sobre formas dobladas]
         │
         ▼
  /diaries-tag ──────────► source/{iso2}/tagged/{id}.txt
  (⚠ crítico, 0.80/0.60)   [regex pase 1 → Claude para sospechosos]
         │
         ▼
  /diaries-matrix ────────► source/{iso2}/matrix/interventions_raw.csv
  (parse <int> → CSV)        [acumulativo por sesión]
         │
         ├──────────────► /diaries-deputies ──► source/{iso2}/deputies/deputies.csv
         │                (BD de diputados)      [externo o construido con RapidFuzz+Claude]
         ▼
  /diaries-match ─────────► source/{iso2}/match/matching_table.csv
  (speaker_raw → id_dep)     [exact → fuzzy → Claude → unmatched]
         │
         ▼
  /diaries-merge ─────────► source/{iso2}/merge/interventions_enriched.csv
  (join pandas)
         │
         ▼
  /diaries-standardize ───► source/{iso2}/standardize/{ISO2}_interventions.csv  ⚠ canónico
  (16 columnas canónicas)
         │
         ▼
  /diaries-document ──────► docs/{iso2}/README.md
                                        data_dictionary.md
                                        dataset.jsonld
                                        corpus_info.json

──────────────────────────────────────────────────────────────────
  CONTROL (disponibles en cualquier momento)

  /diaries-status    → tabla de estado del pipeline
  /diaries-review    → revisar FLAGs interactivamente [A/C/R/E/S/Q]
  /diaries-feedback  → inyectar corrección (punctual/rule/strategy)
  /diaries-decide    → registrar una decisión metodológica CON SU EVIDENCIA
                       → state/{iso2}/decisions.jsonl · state/_transversal/
                       → docs/_metodologia/generados/METODOLOGIA.md (generado, no se edita a mano)
  /diaries-validate  → validación estructural por muestreo + calibración de fuga
  /diaries-report    → informe completo del proceso (lee lo que registró decide)
  /diaries-teach     → esta guía (estás aquí)
  /diaries-refine    → mejorar un SKILL.md desde una observación de testing
──────────────────────────────────────────────────────────────────
```

Tras mostrar el mapa, pregunta: *¿Hay algún nodo o conexión que quieras entender mejor?*

---

## CAMINO 8 — Dejar constancia de una decisión metodológica

Explica **por qué existe** antes de cómo se usa:

```
Las decisiones importantes de un corpus se toman en el momento y se olvidan después.
/diaries-decide las persiste, para el informe metodológico y para poder retomar el
trabajo dentro de un año sabiendo POR QUÉ se hizo algo.

  CAPTURAR ≠ INFORMAR
  · capturar hay que hacerlo EN EL MOMENTO, o se pierde   → /diaries-decide
  · informar se genera después de lo capturado            → /diaries-report

El caso que lo motivó: la revisión manual del match de los 15 corpus no dejó rastro
en ningún fichero. La validación técnica volvió a marcar 128 casos ya resueltos, y
solo se corrigió porque el investigador lo recordaba.
```

**Cuándo invocarlo.** Siempre que se tome una decisión que alguien podría cuestionar
después, o que un investigador externo necesitaría conocer para interpretar el dato:

- se fija un umbral, un criterio o una definición
- se aparta, divide o transforma un conjunto de filas
- se elige entre fuentes que discrepan
- se descarta una vía por haberla medido y no funcionar
- **se corrige una decisión anterior** — el caso más valioso

No para el trabajo rutinario: procesar una sesión, corregir una errata, ejecutar un skill.

**Los cuatro campos**, y por qué la evidencia se valida:

```
decision      qué se hizo
alternativas  qué más se consideró y por qué no
evidencia     QUÉ se midió, SOBRE QUÉ y QUÉ SALIÓ   ← obligatorio, mínimo 40 caracteres
consecuencia  qué cambió, con cifras

  ✗ «Se usó el umbral 0,5»
  ✓ «Se usó 0,5 porque con controles independientes daba ratios de 400× a 4.500×
     entre lo que se mueve y lo que se queda, medido sobre 40.000 filas»
```

El campo existe para impedir que se registre una preferencia como si fuera un hallazgo.
Si no se midió nada, hay que decirlo así: «no medido; se eligió por analogía con PA,
pendiente de comprobar». Eso también es información útil.

**Las decisiones superadas no se borran.** `--supersede {id}` marca la anterior y la
enlaza. Ejemplo real: `cr-0001` (dividir las filas con marcador incrustado) →
`cr-0002` (era el índice del acta; apartarlo al sidecar — política HISTÓRICA, hoy superada:
se declara `dm_speech=0` sin apartar nada). En un *Data Descriptor* esa
cadena **da credibilidad en vez de quitarla**.

**Ante la duda, transversal**: lo que hoy parece de un país suele acabar aplicándose a
todos. La definición de vinculación efectiva empezó siendo «lo de Colombia».

```
/diaries-decide                       → modo interactivo, pregunta los cuatro campos
python3 ~/.claude/skills/diaries-lib/lib/utils/record_decision.py --pais cr --listar
python3 scripts/generar_metodologia.py    → regenera docs/_metodologia/generados/METODOLOGIA.md
```

**No confundir con sus vecinos:**

| skill | qué registra |
|---|---|
| `/diaries-decide` | el **razonamiento**: por qué se hizo, con qué evidencia |
| `/diaries-feedback` | la **acción**: una corrección a aplicar al pipeline |
| `/diaries-refine` | el **comportamiento**: un cambio en un SKILL.md |

---

## Cierre de cualquier camino

Al terminar de explicar un camino, ofrece siempre:

1. **Acción inmediata**: sugiere el comando concreto que el usuario debería ejecutar ahora.
2. **Siguiente paso**: cuál es el skill siguiente en la secuencia.
3. **Si algo sale mal**: qué comando usar para diagnosticar (`/diaries-status`, `/diaries-review`).

Ejemplo de cierre:

```
✓ Con esto ya puedes empezar.

Próximo paso:    /diaries-bootstrap --country {iso2}
Si algo sale mal: /diaries-status --country {iso2}
¿Dudas?          /diaries-teach (vuelves aquí cuando quieras)
```
