---
name: diaries-document
description: "Genera la documentación del corpus para un país (entrevista al procesador + README canónico)"
allowed-tools: [Read, Write, Edit, Bash]
---

Eres el skill `diaries-document` del pipeline ParlaIbero. Entrevistas al procesador para recopilar la información necesaria y generas la documentación orientada a usuarios finales del corpus. Este skill opera a nivel PAÍS.

## Argumentos esperados

`--country {iso2}` (obligatorio)
`--force` (regenerar aunque ya exista la documentación)

---

## Paso 1 — Verificar prerequisito

Verifica que existen el archivo canónico final **y el padrón auxiliar** — la documentación
cubre a los dos, y el `data_dictionary.md` generado remite al padrón («the companion roster
file», donde vive `sex_source`): documentar sin que exista publica una referencia rota.

```bash
test -f source/{iso2}/standardize/{ISO2}_interventions.csv && echo "OK" || echo "MISSING"
test -f source/{iso2}/standardize/{ISO2}_deputies.csv && echo "OK" || echo "MISSING roster"
```

Si falta la matriz: `ERROR: Falta source/{iso2}/standardize/{ISO2}_interventions.csv. Ejecuta primero /diaries-standardize --country {iso2}`
Si falta el padrón: `ERROR: Falta source/{iso2}/standardize/{ISO2}_deputies.csv. Genéralo con /diaries-deputies (Paso 6, padrón publicable) antes de documentar.`

Verifica si ya existe `docs/{iso2}/corpus_info.json`:
```bash
test -f docs/{iso2}/corpus_info.json && echo "EXISTS" || echo "NEW"
```

- Si EXISTS y se pasó `--force`: carga el JSON existente como punto de partida y ofrece al usuario modificarlo.
- Si EXISTS y no se pasó `--force`: usa el JSON existente directamente (salta la entrevista) y regenera los documentos.
- Si NEW: conduce la entrevista completa.

---

## Paso 2 — Estadísticas automáticas del corpus

Antes de la entrevista, extrae estadísticas del corpus para tenerlas disponibles:

⚠ **El separador NO se hardcodea:** solo ES y GT usaban `;` (ya no); los otros 14 usan `,`. Un `sep=';'`
fijo colapsa las 16 columnas en una y revienta en 14 de 16 países — detéctalo siempre.
(Alternativa: delega las estadísticas en `generate_docs.py`, Paso 5, que ya resuelve el
separador y computa además la vinculación efectiva.)

```bash
python3 -c "
import pandas as pd, json
p = 'source/{iso2}/standardize/{ISO2}_interventions.csv'
sep = max([',', ';', '\t'], key=open(p, encoding='utf-8').readline().count)
df = pd.read_csv(p, sep=sep, dtype=str, keep_default_na=False)
stats = {
    'total_interventions': len(df),
    'total_sessions': df[['date','session_number']].drop_duplicates().shape[0],
    'date_range': [df['date'].min(), df['date'].max()],
    'legislatures': sorted(df['legislature'].dropna().unique().tolist()),
    'matched_deputies': int((df['id_dep'].notna() & (df['id_dep'] != '')).sum()),
    'unique_deputies': df['id_dep'].replace('', pd.NA).dropna().nunique(),
    'match_rate': round((df['id_dep'].replace('', pd.NA).notna().sum()) / max(len(df),1), 4),
}
print(json.dumps(stats, ensure_ascii=False))
"
```

Guarda estas estadísticas en memoria para usarlas en el README.

---

## Paso 3 — Entrevista al procesador

Presenta cada pregunta de forma clara y espera la respuesta antes de continuar con la siguiente. Si el usuario ya proporcionó algunos valores en corpus_info.json existente, muéstralos como valor por defecto entre corchetes.

### Pregunta 1 — Fuente de los diarios parlamentarios

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
diaries-document — {ISO2} (1/5)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
¿Cuál es la fuente de los diarios parlamentarios?

Incluye: institución, URL o repositorio, período cubierto y
formato original (PDF, HTML, XML…).

Ejemplo: "Diário da Assembleia da República. Assembleia da
República de Portugal. https://debates.parlamento.pt/.
Legislaturas I–XVII (1975–2024). Formato PDF."
```

### Pregunta 2 — Fuente de los metadatos de diputados

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
diaries-document — {ISO2} (2/5)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
¿Cuál es la fuente de los metadatos de los diputados?

Incluye: institución, URL o base de datos de referencia, y
qué información contiene (nombre, partido, distrito, fechas…).

Ejemplo: "Base de datos de deputados. Assembleia da República
de Portugal. https://www.parlamento.pt/DeputadoGP/."
```

### Pregunta 3 — Descripción del proceso de transformación

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
diaries-document — {ISO2} (3/5)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Describe brevemente el proceso de transformación de los
diarios en registros de intervención.

Menciona: si hubo OCR o los textos ya estaban digitalizados,
cómo se identificaron los oradores, si hubo revisión manual,
y cómo se fusionaron con los metadatos de diputados.

(Puedes ser breve — 2–4 frases.)
```

### Pregunta 4 — Autores y afiliaciones

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
diaries-document — {ISO2} (4/5)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
¿Quiénes son los autores o procesadores del corpus?

Formato recomendado: "Apellido, Nombre (Institución)".
Si son varios, escríbelos en líneas separadas o separados
por punto y coma.
```

### Pregunta 5 — Notas adicionales (opcional)

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
diaries-document — {ISO2} (5/5)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
¿Hay limitaciones conocidas, advertencias o notas adicionales
que deban aparecer en la documentación? (opcional)

Pulsa Enter para omitir.
```

---

## Paso 4 — Guardar corpus_info.json

Crea o actualiza `docs/{iso2}/corpus_info.json` con las respuestas:

```json
{
  "diary_source": "{respuesta 1}",
  "deputy_source": "{respuesta 2}",
  "transformation": "{respuesta 3}",
  "authors": ["{autor1}", "{autor2}", ...],
  "notes": "{respuesta 5 o null}",
  "license": "CC BY 4.0",
  "license_url": "https://creativecommons.org/licenses/by/4.0/"
}
```

Los `authors` se parsean de la respuesta 4: si contiene `;` o saltos de línea, divide en lista; si no, es un único elemento.

```bash
mkdir -p docs/{iso2}/
```

Escribe el JSON con Write.

---

## Paso 5 — Generar documentación

```bash
python ~/.claude/skills/diaries-lib/lib/utils/generate_docs.py \
  --country {iso2} \
  --config "country_config/{iso2}.yaml" \
  --corpus-info "docs/{iso2}/corpus_info.json" \
  --output-dir "docs/{iso2}/" \
  --interventions "source/{iso2}/standardize/{ISO2}_interventions.csv" \
  --matching-table "source/{iso2}/match/matching_table.csv"
```

El script genera:
- `README.md` — documentación principal orientada a usuarios finales
- `data_dictionary.md` — diccionario de variables
- `dataset.jsonld` — metadatos estructurados Schema.org

**El padrón auxiliar es parte de la entrega documentada.** La distribución del corpus son DOS
archivos: `{ISO2}_interventions.csv` + `{ISO2}_deputies.csv` (unible por `id_dep` +
`legislature`). El `data_dictionary.md` ya remite a él («the companion roster file»); comprueba
que `dataset.jsonld` declara AMBOS archivos de la distribución — si el padrón no figura, la
vía es arreglar `generate_docs.py` y REGENERAR (una sola puerta), nunca parchear el archivo
generado a mano.

**Vinculación: se publican AMBAS tasas, bruta Y efectiva.** La **bruta** (filas con `id_dep` /
filas totales) infravalora el trabajo: su denominador incluye intervenciones institucionales que
no son vinculables a un diputado (mesa sin persona, `NOT_SPEAKER`, no-discurso). La **efectiva**
las descuenta del denominador. `generate_docs.py` ya computa las dos (`match_rate` y
`deputy_match_rate`, este último depurando el denominador vía la `matching_table.csv`): pásale
siempre `--matching-table` y verifica que el README enuncia las dos cifras, no solo la bruta —
[[feedback_vinculacion_efectiva]].

**Puerta hermana y principio de sincronía.** `docs/{iso2}/process_report.md` lo genera
`/diaries-report`: este skill documenta el CORPUS para el usuario final; aquel documenta el
PROCESO — un corpus no está documentado hasta que existen ambos. Y la documentación **se
regenera SIEMPRE entera y por una sola puerta** (este skill para README / data_dictionary /
dataset.jsonld; `/diaries-report` para process_report.md): nunca se parchea a mano un archivo
generado. El inglés y las traducciones son **renders paralelos** de la misma fuente
(`corpus_info.json` + estadísticas), no padre e hijo: un cambio se aplica en la fuente y se
re-renderizan todos — [[feedback_sincronia_documentacion]].

---

## Paso 6 — Verificar archivos de salida

```bash
test -f docs/{iso2}/README.md && echo "OK" || echo "MISSING"
test -f docs/{iso2}/data_dictionary.md && echo "OK" || echo "MISSING"
test -f docs/{iso2}/dataset.jsonld && echo "OK" || echo "MISSING"
```

Si falta alguno: registra `--status halt` y reporta qué falta.

---

## Paso 7 — Actualizar estado

```bash
python ~/.claude/skills/diaries-lib/lib/utils/update_state.py \
  --country {iso2} --skill diaries-document --session "_country" \
  --status complete --confidence 1.0 \
  --output "docs/{iso2}/"
```

---

## Paso 8 — Confirmación final

```
diaries-document — {ISO2}
Documentación generada en docs/{iso2}/:

  README.md          — descripción del corpus, fuentes, metodología, autores
  data_dictionary.md — diccionario de variables
  dataset.jsonld     — metadatos Schema.org (CC BY 4.0)
  corpus_info.json   — respuestas del procesador (reutilizable con --force)

Status: complete
```

Si todos los skills del pipeline están en complete:
"El corpus {iso2} está listo para distribución."

> ⚠⚠ **Separador: SIEMPRE la coma, en los dieciséis** (directiva del investigador, 2026-09-01, `br-0019`). Antes se decía que ES y GT usaban `;`; se unificó por compatibilidad. ⚠ ES y GT tienen aún su canónico en `;` y pasarán a `,` al regenerarse en su reproceso, así que **al LEER conviene seguir detectando el separador**, aunque al ESCRIBIR sea siempre coma.
