# Cambios de diaries-lib

## 25-10-2026 · attribute_presidency: la carátula desplazaba cada relevo un turno

- **La carátula contaba como turno.** `cambios()` sitúa cada nota de relevo contando las marcas `<int`
  de `tagged/`. `atribuir()` contaba además la fila de la carátula (Prolegomena, orden 0, que añade
  `recover_frontmatter`), que no tiene marca. Así, cada tramo empezaba un turno antes y el turno que
  contiene la nota pasaba a quien asume.
  - Caso medido: en la corrida de Bolivia, el único turno de la presidenta que asume
    en la 153.ª se iba a quien la releva al final de ese turno.
  - Arreglo: `atribuir()` ya no cuenta las filas de orden 0.
  - Comprobado que es seguro: en CL, CO, PE, PT y UY el orden 0 es siempre la carátula (una fila por
    sesión como mucho, sin orador, `dm_speech` 0), y los turnos empiezan en 1.
- **La nota que abre su turno.** Si entre la marca del turno y la nota no se dijo nada, el tramo nuevo
  empieza en ese turno. Si la nota cierra el turno o cae en medio, el tramo empieza en el siguiente.
  - Antes valía siempre «el siguiente»; solo con carátula salía bien, por accidente.
  - Medido el 25-10-2026: en BO, UY y PT ninguna nota abre su turno, así que esta regla no cambia sus
    atribuciones.
- **UY y PT publicados: sin cambios.** Su mesa no sale de este script, sino de los `match_*.py` del
  reproceso. Esos scripts leen la nota en el texto de cada fila, y el canónico coincide con `merge`
  fila a fila.
- **Prueba nueva:** `tests/test_diaries_lib_presidencia_tramos.py` (9 casos). Cubre cada posición de
  la nota, con y sin carátula, y una copia de la corrida de Bolivia (`DIARIES_BOLIVIA`; sin ella, se salta). Con el
  módulo anterior fallan 6 de los 9.

Batería: `cd ~/.claude/skills && PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider -q
diaries-lib/tests` con `DIARIES_BOLIVIA` → 94 passed (85 + 9); sin ella, 93 passed y 1 skipped.

## 24-09-2026 · parche A1, ronda 2 (arreglo tras el ataque 1)

Corrige lo que confirmó el probador adversarial de la ronda 1 (`attack-diaries-lib-fix-1.json`): 1 hallazgo alto y 3 bajos. La API pública de `StateManager`, el formato de `pipeline_state.json` y de `confidence_anomalies.jsonl`, y la salida de `vinculacion_tr0109.py`/`vinculacion_efectiva.py` no cambian salvo lo descrito aquí. Pruebas nuevas en `tests/`: cada repro del ataque tiene ahora una prueba que fallaba antes de este arreglo y pasa después.

- **`confidence-texto-por-asignacion-directa` (alto).** Una asignación directa de un valor NO numérico a `.confidence` (p. ej. `sk.confidence = "muy alta"`, el patrón que el propio parche A1 documenta y ejercita como soportado) no pasaba por ningún validador —no hay `validate_assignment=True`—, así que `acotar_confianza()` la dejaba pasar intacta («lo no numérico lo decide Pydantic, como antes») y llegaba a disco sin acotar ni registrar; la SIGUIENTE carga lanzaba la traza cruda de `pydantic.ValidationError` y dejaba el `pipeline_state.json` de todo un país ilegible para el pipeline entero.
  - `acotar_confianza()` (`lib/schemas.py`) trata ahora lo no convertible a float como anómalo: se acota a `None`, igual que un valor no finito.
  - Se registra en `confidence_anomalies.jsonl` con `source="no_numerico"` (nuevo valor posible, junto a `carga`/`asignacion`/`mark_skill`), para distinguirlo de un número simplemente fuera de rango. Helper nuevo y aditivo: `confianza_no_numerica()`.
  - Decisión sobre qué hace `load()` si el JSON en disco YA trae un valor así: tratarlo con la MISMA regla (se acota a `None` y se registra) en vez de lanzar una excepción propia, por ser la opción que menos toca la API pública (cero excepciones nuevas, ninguna firma cambiada) — y sale gratis, porque `load()` y `save()` ya pre-escaneaban el dict con `_escanear_anomalias()` **antes** de llamar a `model_validate()` (para los valores fuera de rango); ese mismo pre-escaneo limpia ahora también lo no numérico antes de que Pydantic lo vea. El `field_validator` de `SkillState.confidence` queda igual de tolerante como defensa en profundidad, por si algo construye el modelo directamente sin pasar por `StateManager`.
  - `mark_skill()` cubre el mismo caso si alguien le pasa una `confidence` no numérica directamente (no alcanzable por la CLI, que ya filtra con `argparse type=float`).
- **`bom-utf8-antes-de-id_dep` (bajo).** Un CSV con BOM UTF-8 y `id_dep` como primera columna daba un falso «no tiene la columna id_dep» (el BOM quedaba pegado al nombre de la cabecera: `﻿id_dep`). `vinculacion_tr0109.py` y `vinculacion_efectiva.py` leen ahora los CSV con `encoding="utf-8-sig"` (antes, `"utf-8"`); sin BOM la salida no cambia.
- **`tmp-huerfano-tras-proceso-muerto` (bajo).** Un `.pipeline_state.json.*.tmp` que quedaba huérfano si el proceso moría (`SIGKILL`) entre `tempfile.mkstemp` y el `os.replace` de `_escribir_atomico` se acumulaba para siempre en `state/{iso2}/`. `StateManager._bloqueo()` limpia ahora, justo tras tomar el `flock`, los `.tmp` de ese mismo país más viejos que `DIARIES_STATE_LOCK_TIMEOUT` (con `DIARIES_STATE_LOCK_TIMEOUT=inf` no se borra nada, por no haber margen con el que decidir «viejo»).
- **`cannot_hold_seat_discounted-float-entero-rechazado` (bajo).** `vinculacion_tr0109.py` rechazaba (salida 2) un `linkage.cannot_hold_seat_discounted` que fuera float aunque representara un entero exacto (`20.0`), por exigir `isinstance(ext, int)` estricto. Helper nuevo `_entero_no_negativo()`: acepta también un float con `.is_integer()` y lo convierte a `int`; sigue rechazando lo negativo, lo no entero (`20.5`) y lo que no sea número (p. ej. un texto).

Batería: `cd ~/.claude/skills && PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider -q diaries-lib/tests diaries-report/tests` → 90 passed, 0 failed (81 de la ronda 1 + 9 pruebas nuevas de esta ronda).

## 23-09-2026 · parche A1 de la fase A

Arreglos de la auditoría de patrones (`auditoria-skills-academicos/audits/patrones.md`). El formato de `pipeline_state.json`, la API pública de `StateManager` y la tabla por defecto de `vinculacion_efectiva.py` no cambian. Pruebas en `tests/`, ejecutables con `python3 -m pytest`: cada fallo tiene una prueba que lo reproducía antes del arreglo.

Estado del pipeline (`lib/state_manager.py`, `lib/schemas.py`):

- **Escrituras concurrentes.** La auditoría midió que, de 40 escrituras concurrentes, solo llegaban al disco entre 24 y 30. Ahora `save()` toma `fcntl.flock` sobre `pipeline_state.json.lock` (espera como máximo `DIARIES_STATE_LOCK_TIMEOUT` segundos, 600 por defecto). Si otro proceso guardó entretanto, hace una fusión a tres bandas por sesión, skill y campo, con unión de correcciones y `global_rules`. Las pruebas lanzan 40 procesos con `multiprocessing` y no pierden ninguna escritura.
- **La fusión actualiza la memoria en sitio.** Así, lo que un script mute después por una referencia antigua (`st = sm.load()`, el patrón de varios scripts del proyecto) sigue llegando al disco. Un valor ilegible de `DIARIES_STATE_LOCK_TIMEOUT` ya no rompe con `ValueError`: avisa y usa el valor por defecto.
- **Escritura atómica** (temporal, fsync y `os.replace`) y **lectura tolerante**: `load()` reintenta si encuentra el JSON a medias y nunca sustituye a ciegas un fichero ilegible.
- **Confianza acotada a [0, 1]** (`acotar_confianza`). En CO había valores negativos. Ahora los anómalos se acotan y se registran con su sesión, skill y valor original en `state/{iso2}/confidence_anomalies.jsonl`, en vez de ocultarse.
- **Marcas de tiempo en UTC con zona** (`datetime.now(timezone.utc)`), en lugar del `utcnow()` obsoleto.
- Comprobado sobre copias de los 16 estados reales. La ida y vuelta es byte a byte igual que antes en 15; en CO solo cambian las 3 confianzas negativas, que pasan a 0.0. La fusión es correcta en los 16.

Vinculación efectiva (`lib/utils/`):

- **`vinculacion_tr0109.py` (nuevo).** Calcula la vinculación efectiva con la definición vigente tr-0109, la del bloque `linkage` de `docs/{iso}/corpus_info.json`: `vinculadas / (filas de habla − sin escaño − no atribuibles)`.
  - Por qué: diaries-report calculaba la cifra con el modelo e inflaba la efectiva unos 6 puntos en PY. La única implementación de tr-0109 era `linkage_no_atribuibles.py`, un script suelto del proyecto ParlaIbero; esta herramienta trae su parte de vinculación al skill.
  - Hereda `cannot_hold_seat_discounted` de corpus_info.json sin reclasificarlo, como hace tr-0109.
  - Solo lee. Compara lo recalculado con lo publicado: sale con 0 si coincide, con 1 si no coincide y con 2 si no se puede calcular.
  - Opciones: `--json`, `--out` atómico que nunca pisa una entrada, y `--comparar tr-0003`.
  - Da un `texto_informe` con la definición y la procedencia de cada cifra.
  - Equivalencia probada contra el script original, sobre formas límite sintéticas y sobre una copia de PY: 93,91 %, igual que corpus_info.json.
- **`vinculacion_efectiva.py`** (definición tr-0003, que queda para comparar) gana `--json` y `--out`, con procedencia (sha256 del script y de cada CSV, hora UTC y orden), y errores de entorno con salida 2. El modo tabla se comporta como siempre.
- **`salida_json.py` (nuevo).** Procedencia, escritura atómica y rechazo de un `--out` que sea una entrada; lo comparten los dos scripts.
