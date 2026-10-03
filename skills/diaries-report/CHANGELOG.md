# Cambios de diaries-report

## 23-09-2026 · parche A1 de la fase A: la vinculación efectiva la calcula un script

Qué fallaba: el Paso 3-bis traía su propio `python3 -c`, que descontaba como «rol» a todo orador con PRESIDENT, SECRETARI o MESA en el nombre. Eso incluía a personas nombradas y al `PRESIDENTE` anónimo, que es diputado. Con él, el informe inflaba la efectiva unos 6 puntos en PY (98,4 %). Además, la tabla histórica del paso (PY 99,4 %…) no la reproducía ningún script, y la regla «la efectiva descuenta solo los roles sin nombre propio» contradecía la definición del proyecto.

Qué cambia, según la decisión del 23-09 (delegada por el usuario en el orquestador): la cifra del informe es la de la definición vigente tr-0109, la misma del bloque `linkage` de `docs/{iso2}/corpus_info.json`, para que informe y metadatos coincidan.

- El Paso 3-bis ejecuta `diaries-lib/lib/utils/vinculacion_tr0109.py --country {iso2} --out docs/{iso2}/vinculacion_efectiva.json`. Sobre una copia de PY da 93,91 %, la cifra publicada.
- El informe copia literalmente el `texto_informe` del JSON en el Resumen ejecutivo. Ese texto dice qué definición usa (tr-0109), de dónde sale cada cifra y si coincide con corpus_info.json. La plantilla le reserva sitio.
- Salida 1 (no coincide con lo publicado): se dice en el informe y en el diagnóstico de salud. Salida 2 (no se puede calcular): «no disponible», sin reutilizar un JSON anterior.
- tr-0003 (`vinculacion_efectiva.py`) solo está disponible para comparar, con `--comparar tr-0003`: no es la cifra del informe.
- El skill ya no depende de `linkage_no_atribuibles.py`, un script suelto del proyecto: su lógica de vinculación vive en diaries-lib, con prueba de equivalencia.
- Se retiran del paso la tabla histórica y el aviso sobre el separador, porque el script lo detecta.
- Pruebas en `tests/test_diaries_report_vinculacion.py`: ejecutan literalmente los bloques bash del Paso 3-bis sobre un proyecto sintético. Antes del arreglo fallaban las 5; ahora pasan.
