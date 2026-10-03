---
name: diaries-decide
description: Registra una decisión metodológica del pipeline con su evidencia, para que el informe del corpus pueda explicar QUÉ se hizo, POR QUÉ y CON QUÉ PRUEBA. Captura en el momento; sin evidencia medida no se guarda.
---

# diaries-decide — registrar una decisión metodológica

Las decisiones importantes de un corpus se toman en el momento y se pierden después. Este
skill las persiste, para el informe metodológico y para poder retomar el trabajo dentro de un
año sabiendo **por qué** se hizo algo.

**Capturar e informar son cosas distintas.** Capturar hay que hacerlo **en el momento** o se
pierde; informar se genera después de lo capturado. `/diaries-report` es lo segundo; esto es
lo primero.

> **El caso que motivó este skill.** La tabla de vinculación de los quince corpus fue revisada
> a mano por el investigador antes del merge, y esa revisión **no dejó rastro en ningún
> fichero**. Consecuencia medida: la validación volvió a marcar **128 casos ya resueltos**, y
> solo se corrigió porque el investigador lo recordaba. Con una sesión de por medio, esa
> información se habría perdido para siempre.

---

## Cuándo invocarlo

Siempre que se tome una decisión que **alguien podría cuestionar después**, o que un
investigador externo necesitaría conocer para interpretar el dato:

- se fija un umbral, un criterio o una definición (¿por qué 0,5 y no 0,7?)
- se aparta, divide o transforma un conjunto de filas
- se elige entre fuentes que discrepan
- se descarta una vía por haberla medido y no funcionar
- **se corrige una decisión anterior** — este es el caso más valioso

No para el trabajo rutinario: procesar una sesión, corregir una errata, ejecutar un skill.

---

## Paso 1 — Reunir los cuatro campos

Se pregunta al usuario lo que falte. **Ninguno se rellena por cuenta propia**: si el
razonamiento no está claro, el registro no vale nada.

| campo | qué es | ejemplo |
|---|---|---|
| `decision` | qué se hizo | «El índice del acta se traslada al sidecar de no-discurso» *(histórico — ver nota)* |
| `alternativas` | qué más se consideró y por qué no | «Dividir las filas en una intervención por orador — lo desmintió la muestra» |
| **`evidencia`** | **qué se midió, sobre qué, y qué salió** | «Cuatro señales de oralidad independientes dan ratios de 400× a 4.500× (n=40.000)» |
| `consecuencia` | qué cambió, con cifras | «20.350 filas (5,47%) al sidecar; 372.045 → 351.695» *(histórico — ver nota)* |

> ⚠ Los ejemplos de `decision` y `consecuencia` son HISTÓRICOS (CR, época del sidecar) y su
> política está **superada**: hoy nada se aparta a un sidecar — la fila que no es discurso se
> DECLARA con `dm_speech = 0` y se queda en el corpus (la carátula y el sumario son los
> Prolegomena, con `intervention_order = 0`). Se conservan porque ilustran el formato del
> registro, no para copiar el patrón. La forma vigente sería: «El índice del acta se declara
> `dm_speech = 0`» / «20.350 filas (5,47%) declaradas `dm_speech = 0`; el total no cambia».

### La evidencia es obligatoria y se valida

`record_decision.py` **rechaza** una evidencia por debajo de 40 caracteres. Es deliberado:
el campo existe para impedir que se registre una preferencia como si fuera un hallazgo.

- ✗ «Se usó el umbral 0,5» — dentro de un año no dice nada.
- ✓ «Se usó 0,5 porque con controles independientes daba ratios de 400× a 4.500× entre lo
  que se mueve y lo que se queda, medido sobre 40.000 filas.»

Si la decisión se tomó **sin** medir nada, hay que decirlo así: «no medido; se eligió por
analogía con PA, pendiente de comprobar». Eso también es información útil, y honesta.

---

## Paso 2 — Ámbito

```
--pais {iso2}        → state/{iso2}/decisions.jsonl
--pais transversal   → state/_transversal/decisions.jsonl
```

Ante la duda, **transversal**: una decisión que hoy parece de un país suele acabar aplicándose
a los demás. La definición de vinculación efectiva empezó siendo «lo de Colombia».

---

## Paso 3 — ¿Anula una decisión anterior?

Si la decisión **corrige** otra, pasar `--supersede {id}`. La anterior se marca
`estado="superada"` y guarda `superada_por`; **nunca se borra**.

Esa cadena es lo más valioso del registro. En una sola sesión se superaron tres decisiones:

- la definición de vinculación efectiva cambió dos veces —la primera propuesta como
  «conservadora» era la contraria—;
- el criterio de vigencia pasó de fecha exacta a mandato en la legislatura;
- el diagnóstico del índice de Costa Rica se invirtió por completo (de «dividir» a «apartar»).

En un *Data Descriptor*, la sección de errores corregidos **da credibilidad en vez de
quitarla**, y se genera sola desde estos enlaces.

---

## Paso 4 — Registrar

```bash
python3 ~/.claude/skills/diaries-lib/lib/utils/record_decision.py \
    --pais cr --fase diaries-validate \
    --decision "..." --alternativas "..." --evidencia "..." --consecuencia "..." \
    [--supersede cr-0003]
```

Consultar lo ya registrado:

```bash
python3 ~/.claude/skills/diaries-lib/lib/utils/record_decision.py --pais cr --listar
```

---

## Paso 5 — Confirmar

Mostrar el id asignado y, si anuló otra, decir cuál. Recordar que el registro alimenta
`/diaries-report`.

---

## Principios transversales ya registrados

Antes de registrar una decisión nueva, comprobar si es un caso de alguno de estos — si lo es,
enlazarla en vez de repetir el razonamiento:

| principio | de dónde salió |
|---|---|
| **Descubrir, no asumir** | `diaries-meta` asumía el regex del config y falló en 7 de 15 países. GT registraba la legislatura en `notas` y se dio por «no comprobable» |
| **Un control no puede compartir el léxico de lo que valida** | CR: 22.979 marcadores omitidos con el verificador dando 0 residuales |
| **El diario es la fuente primaria; el padrón, una construcción nuestra** | Una intervención NUNCA se elimina porque su orador no case con el padrón |
| **Los padrones nacionales son independientes por diseño** | No hay un formato «correcto» al que homogeneizarlos |
| **No confundir «el dato no puede expresar esto» con «esto está mal»** | Exigir fechas de mandato mandaba a FLAG el 100% de GT |
| **No llamar exclusión estructural a un fallo de atribución propio** | Descontar los `PRESIDENTE` anónimos inflaba BR de 86% a 99% |
| **Medir por subgrupo, no en agregado** | La cobertura del 75,9% escondía un 50,0% en mujeres frente a 82,3% en hombres |
| **La muestra no repara: señala dónde reparar** | El 4,15% de CR llevó a mover 20.350 filas; corregir la muestra habría cambiado el 0,005% |
| **Mirar una muestra ALEATORIA de lo que se va a tocar** | Evitó dividir el índice de CR en miles de intervenciones basura |

---

## Notas

- Este skill **no modifica datos**. Solo escribe el registro de decisiones.
- El registro es acumulativo y de solo-añadir: las decisiones superadas se marcan, no se borran.
- Para cambiar el comportamiento de un skill a partir de una observación de testing, usar
  `/diaries-refine`; para inyectar una corrección en el pipeline, `/diaries-feedback`. Este
  skill documenta el **razonamiento**, no la acción.
