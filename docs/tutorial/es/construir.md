# Construir un corpus

<!-- eyebrow: Los skills diaries-* -->

*[English version](../en/construir.md) · [Índice del tutorial](../TUTORIAL.md)*

Los datos que consulta parlaibero-mcp salieron de una tubería: 21 skills de Claude Code que llevan un diario de
sesiones desde el PDF escaneado, el HTML o el XML hasta la matriz de intervenciones de 16 columnas, vinculada con el
registro de diputados. Esta página explica cuándo conviene usarlos, qué hace cada paso, cómo avisan cuando dudan y por
dónde se empieza.

<!-- side -->

**Instalar**

Hacen falta [Claude Code](https://claude.com/claude-code) y Python `≥ 3.11`. Desde el repositorio:

```bash
git clone https://github.com/rodrodr/parlaibero-tools.git
cd parlaibero-tools
bash install_skills.sh
```

Copia los skills a `~/.claude/skills`. Si ya tienes alguno, se detiene sin tocarlo; `--force` los sustituye y guarda
antes una copia. Después, en la carpeta del proyecto que vaya a contener los datos:

```bash
bash ~/.claude/skills/diaries-lib/install.sh
```

Instala las dependencias de Python, crea `source/`, `state/`, `country_config/` y `docs/`, y comprueba
[Ollama](https://ollama.com), que solo hace falta para el OCR de los PDF escaneados.

## 1. Cuándo usarlos, y cuándo no

Para consultar los dieciséis parlamentos no hacen falta: el servidor MCP descarga los conjuntos ya construidos. Los
skills sirven para otra cosa:

- **Un corpus que no existe.** Otra cámara (un senado, un parlamento regional), otro país u otro periodo, a partir de
  sus diarios de sesiones.
- **Reproducir o auditar uno publicado.** Los skills son el método con el que se construyeron los dieciséis, y cada
  decisión de la construcción quedó registrada con su evidencia.
- **Una pieza suelta.** El OCR local de unos PDF escaneados, o el etiquetado de oradores de unas actas, sin llegar a la
  matriz.

Antes de empezar, tres cosas. Claude Code es quien orquesta: lee cada `SKILL.md`, ejecuta el código de `diaries-lib`,
razona sobre los casos ambiguos y te pregunta. No es un programa que se lanza y termina: cada país del corpus pasó por
revisiones a mano y por decisiones que hubo que tomar y registrar. Y los skills recogen la experiencia de construir los
dieciséis corpus y conservan referencias a ese proceso: identificadores de decisiones como `tr-0109`, países de
ejemplo y scripts propios de algunos países que no están en el repositorio. Son el método tal como se aplicó, no un
producto genérico, y están escritos en español.

> [!NOTE]
> Aparte de Claude Code no hace falta ninguna clave. El OCR corre en tu ordenador con Ollama. Existe un reintento con
> MiniMax para las páginas peor leídas, pero está apagado por defecto y pide su propia clave.

## 2. El recorrido

<!-- pipeline -->

Trece skills en orden, agrupados en cinco tramos. Cada uno lee una carpeta de `source/{iso2}/` y escribe otra, y
ninguno sobrescribe lo anterior: si un paso falla, se corrige y se repite desde ahí. `extracted/` es la capa fiel, el
texto tal como salió de la fuente, y no se limpia nunca; la limpieza es solo cosa de `correct`.

El orden tiene tres matices que conviene saber antes de empezar:

- `ocr` solo trabaja si el PDF es una imagen. Con un PDF digital, HTML o XML, se salta.
- `meta` y `dedupe` van antes de `tag`. El etiquetado ordena las formas de los marcadores de orador por su frecuencia
  en todo el corpus para decidir cuáles entran en su léxico; una sesión duplicada las cuenta dos veces, y deduplicar
  después ya no corrige esa decisión.
- `deputies` puede ir antes de `tag` si las actas traen pase de lista nominal: el registro sale entonces del texto
  corregido y ayuda a reconocer a los oradores.

La entrega son dos archivos: `{ISO2}_interventions.csv`, con las 16 columnas canónicas, y `{ISO2}_deputies.csv`, el
registro de diputados, que se une al primero por `id_dep` y la legislatura. Son los que se publican en Harvard
Dataverse y los que `download_country` carga en tu ordenador:

```text
id_session · id_int · legislature · legislative_session · session_number · date · session_type · intervention_order
speaker_raw · id_dep · speaker_name · sex · party · district · dm_speech · text
```

Los otros ocho skills no tienen turno. Se usan en cualquier momento para ver el estado, revisar y corregir, validar,
registrar una decisión, escribir el informe, aprender el sistema o mejorar un skill.

## 3. AUTO, FLAG, HALT: cuándo te pregunta

Casi todos los pasos calculan una confianza entre 0 y 1 y la comparan con dos umbrales. Por encima del primero, AUTO: sigue sin
preguntar. Entre los dos, FLAG: sigue, pero apunta el caso para que lo revises. Por debajo del segundo, HALT: se
detiene hasta que intervengas. Los umbrales están en la configuración de cada país (`country_config/{iso2}.yaml`) y
pueden ajustarse; estos son los de la plantilla:

<!-- table:umbrales -->
| Skill | AUTO | FLAG | HALT |
|---|---:|---:|---:|
| `diaries-tag` | ≥ 0,80 | ≥ 0,60 | < 0,60 |
| `diaries-match` | ≥ 0,90 | ≥ 0,70 | < 0,70 |
| los demás | ≥ 0,85 | ≥ 0,65 | < 0,65 |
<!-- /table -->

Dos pasos tienen umbrales propios. `match` exige más: una vinculación equivocada pone las palabras de una persona a
nombre de otra, con su partido y su sexo. `tag` admite una confianza algo menor, pero tiene una regla que no depende de
ella: una sola marca de orador sin etiquetar detiene la sesión, porque atribuiría en silencio
la intervención entera al orador anterior. Cada ficha del § 6 dice qué mide la confianza de su paso.

Los casos pendientes se revisan con `/diaries-review`: para cada FLAG muestra la evidencia y la confianza, y tú
aceptas, corriges, lo escalas a HALT o lo dejas para más tarde. Un error que se repite se corrige una sola vez con
`/diaries-feedback`: para una sesión, como regla desde una fecha o para todo el skill.

```text
/diaries-status --country {iso2}
/diaries-review --country {iso2}
```

## 4. El registro de decisiones

Las decisiones importantes de un corpus se toman en el momento y se olvidan después: un umbral, una definición, unas
filas que se apartan, una fuente que se prefiere a otra. `/diaries-decide` las guarda cuando se toman, con cuatro
campos: la decisión, las alternativas, la evidencia y la consecuencia. La evidencia es obligatoria y dice qué se midió,
sobre qué y qué salió; si no se midió nada, se dice así, y eso también sirve. Lo que no se guarda es una preferencia
presentada como hallazgo:

- ✗ «Se eligió este umbral.»
- ✓ «Se eligió este umbral porque, en una muestra leída a mano, separaba las filas que había que apartar de las que
  había que dejar; con uno más bajo se apartaban filas buenas.»

Una decisión superada no se borra: `--supersede` la marca y la enlaza con la que la corrige, y esa cadena es la
historia de las correcciones del corpus. Las decisiones de un país van a `state/{iso2}/decisions.jsonl`, y las que
valen para todos, a `state/_transversal/`. Al final, `/diaries-report` escribe el informe interno del proceso,
`docs/{iso2}/pipeline_report.md`: cronología, confianzas, correcciones, tasa de automatización y lo que queda abierto.

Tres skills registran cosas distintas:

| Skill | Qué registra |
|---|---|
| `/diaries-decide` | el razonamiento: por qué se hizo algo y con qué evidencia |
| `/diaries-feedback` | la acción: una corrección que el pipeline aplica |
| `/diaries-refine` | el comportamiento: un cambio en un `SKILL.md` |

## 5. Por dónde empezar

1. Instala los skills y prepara la carpeta del proyecto, con los dos comandos del principio de la página.
2. Copia los diarios de un país en `source/{iso2}/raw/`, un archivo por sesión. Si se llaman por su fecha
   (`AAAA-MM-DD.pdf` o `.html`), te ahorras preguntas.
3. Abre Claude Code en la carpeta del proyecto y pide la guía con `/diaries-teach`. Su camino 2, «Nuevo país desde
   cero», recorre los cinco tramos y se ofrece a acompañarte en el primer paso.
4. Configura el país con `/diaries-bootstrap --country {iso2}`, que examina de tres a cinco documentos y te pregunta
   solo lo que no pudo inferir.
5. Sigue la cadena, y revisa con `/diaries-review` cada vez que un paso deje casos en FLAG:

```text
/diaries-ocr --country {iso2} --all
/diaries-extract --country {iso2} --all
/diaries-correct --country {iso2} --all
/diaries-meta --country {iso2} --all
/diaries-dedupe --country {iso2}
/diaries-tag --country {iso2} --all
/diaries-matrix --country {iso2} --all
/diaries-deputies --country {iso2}
/diaries-match --country {iso2}
/diaries-merge --country {iso2}
/diaries-standardize --country {iso2}
/diaries-document --country {iso2}
/diaries-report --country {iso2}
```

Si la cadena se detiene, `/diaries-status` dice dónde y cuál es el siguiente paso pendiente; `/diaries-review` resuelve
los casos abiertos, y se sigue desde el skill que se detuvo.

La guía [Un país desde cero](pais.md) recorre esta cadena entera sobre cuatro sesiones de Bolivia, un país que no está
en ParlaIbero: lo que preguntó cada skill, lo que se comprobó a mano y lo que salió mal.

La documentación técnica completa de los skills, escrita durante la construcción y solo en español, detalla cada
fórmula de confianza, cada control y cada regla de parada: el [índice de los 21 skills](../../../skills/diaries-lib/docs/diaries_index.html)
y el [árbol de procedimiento](../../../skills/diaries-lib/docs/pipeline_procedure_tree.html). Conservan referencias al
proyecto en que se construyó el corpus, como scripts que no están en el repositorio; donde algo no coincida, mandan los
`SKILL.md`.

## 6. Las 21 fichas

Cada ficha dice qué hace el skill, qué lee y qué escribe, qué mide su confianza y cómo se invoca, junto a la
descripción con la que Claude Code decide cuándo usarlo: por eso un skill también se puede pedir con palabras
(«revisa los casos pendientes de Chile»). Las rutas son relativas a la carpeta del proyecto; `{iso2}` es el código del
país en minúsculas, `{ISO2}` en mayúsculas, e `{id}`, el de la sesión.

<!-- skills -->
