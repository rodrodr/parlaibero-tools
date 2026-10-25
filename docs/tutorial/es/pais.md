# Un país desde cero

<!-- eyebrow: Guía · Los skills diaries-*, de principio a fin -->

*[English version](../en/pais.md) · [Construir un corpus](construir.md) · [Índice del tutorial](../TUTORIAL.md)*

[Construir un corpus](construir.md) explica qué hace cada skill. Esta guía los usa, uno detrás de otro, sobre un país
que no está en ParlaIbero: cuatro sesiones de la Cámara de Diputados de Bolivia, de los PDF de *El Redactor de
Debates* a la matriz de intervenciones vinculada con el registro de diputados. En cada paso se ve el comando, lo que
el skill preguntó y lo que se le contestó, las cifras, un fragmento del acta, lo que se comprobó a mano y la decisión
que quedó registrada. También lo que salió mal, que fue bastante: errores de los skills, de la librería y de Claude
Code al ejecutarlos. Las cifras y los fragmentos salen del recorrido real; en los fragmentos, el nombre de cada
diputado está tapado con `[N]`.

<!-- side -->

**El recorrido**

<!-- table:pais_ficha -->
- **País:** Bolivia, Cámara de Diputados
- **Fuente:** El Redactor de Debates, PDF digital
- **Sesiones:** 67.ª · 76.ª · 153.ª · 154.ª
- **Filas:** 905
- **Habla vinculada:** 97,1 %
- **Preguntas respondidas:** 25
- **Decisiones:** 25, 5 superadas
- **Scripts propios:** 14
- **Skills:** parlaibero-tools `3935e4d`
<!-- /table -->

Los skills, tal como estaban en ese commit. Una versión posterior puede preguntar otras cosas o en otro orden; el
método es el mismo.

## 1. La pregunta y la fuente

Antes del primer comando hay que saber para qué es el corpus, porque eso decide cuántas sesiones hacen falta. Aquí
la pregunta es de método: enseñar cómo se construye. Bastan cuatro sesiones de dos tomos, marzo y julio de 2024, y se
dice desde el principio que la muestra no sirve para series temporales: los tomos de 2023-2024 traen 27 de las más de
200 sesiones de la legislatura. Esa es la primera decisión del registro (bo-0001), y las sesiones conjuntas de la
Asamblea Legislativa Plurinacional quedan fuera.

*El Redactor de Debates* publica un tomo al mes, en PDF digital: el texto se puede copiar, así que no hará falta OCR.
Cada tomo trae unas páginas preliminares (autoridades, comisiones, resoluciones), las sesiones del mes y un índice.

El trabajo va en una carpeta aparte, con copias de los PDF y su huella sha256 comprobada contra los originales, para
que nada de lo que se pruebe toque la fuente. La carpeta se prepara con el instalador de la librería:

```bash
mkdir bo_desde_cero && cd bo_desde_cero
bash ~/.claude/skills/diaries-lib/install.sh
```

## 2. Preparar las fuentes

Los skills esperan un archivo por sesión, llamado por su fecha, en `source/bo/raw/`. Ningún skill corta un tomo en
sesiones: es trabajo previo, y se hace con un script propio. Cada sesión empieza en página nueva con una cabecera fija
(«Nª SESIÓN … / LEGISLATURA … / LA PAZ, día …»), así que el script corta por ella.

Aquí llegó la primera pregunta. La sesión del 31 de julio pasa de la medianoche, y el tomo de agosto empieza en
mitad de ella otra sesión, la 154.ª. ¿Una sesión o dos? Se contestó que dos, cortando donde la corta el propio tomo de
agosto (bo-0003), y que las preliminares quedan fuera de las sesiones (bo-0002).

<!-- table:pais_sesiones -->
| Sesión | Fecha | Páginas | Turnos etiquetados | Filas del canónico | Palabras del canónico |
|---|---|---:|---:|---:|---:|
| 67.ª | 2024-03-13 | 221 | 408 | 409 | 97.873 |
| 76.ª | 2024-03-26 | 67 | 128 | 129 | 32.277 |
| 153.ª | 2024-07-31 | 79 | 185 | 186 | 40.866 |
| 154.ª | 2024-08-01 | 77 | 181 | 181 | 42.700 |
| **Total** |  | 444 | 902 | 905 | 213.716 |
<!-- /table -->

La comprobación a mano: las dos sesiones de marzo suman 134.048 palabras en las páginas del tomo y 134.048 en los dos
PDF cortados, y en la página partida entre la 153.ª y la 154.ª no falta ninguna. (Las palabras de la tabla son las del
canónico, al final del recorrido, sin cabeceros ni folios.) Las filas del canónico son una más que los turnos en tres
sesiones: la carátula, que se añade al final como fila 0.

## 3. Configurar el país: bootstrap

```text
/diaries-bootstrap --country bo
```

El skill examina las cuatro sesiones antes de preguntar. Midió unos 3.340 caracteres por página (PDF digital, sin OCR)
y contó las marcas de orador a principio de línea: «DIP.» 254 veces, «PRESIDENTE» o «PRESIDENTA» 452 y «SECRETARIO» o
«SECRETARIA» 186. Vio también que la primera marca de quien preside o de quien ocupa la secretaría lleva el nombre
(«PRESIDENTE, DIP. …:»), y 33 formas en mayúsculas seguidas de dos puntos: unas 30 son encabezados de los documentos
que se leen en el pleno, y 2 son diputadas cuya marca no lleva «DIP.».

Preguntó solo lo que no podía inferir:

- **La legislatura.** `legislature` es el periodo constitucional, 2020-2025, y `legislative_session`, el año
  legislativo de la cabecera, 2023-2024.
- **Las marcas sin «DIP.».** Sin patrón propio: que las resuelva tag con el registro de diputados.
- **«SESIÓN PLENARIA».** Es el pleno: `session_type` = `ordinaria`.

Escribe `country_config/bo.yaml`, el estado del pipeline (con el OCR ya marcado como omitido) y un informe de
arranque. La comprobación a mano es leer la configuración que escribió: dos de sus claves no las lee nadie después, y
se vio al llegar a meta (§ 5). Así quedaron las marcas de orador en esa configuración al final del recorrido; la
alternativa del punto la añadió bo-0015 (§ 8), y los comentarios citan la decisión que justifica cada cambio:

<!-- table:pais_config -->
```extracto
speaker_tag_patterns:
  - "^DIP\\.\\s+([A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ.\\-\\s]+?)(?::|\\.(?=\\s+(?:[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]|[…¿¡“«(])))"
  - "^(PRESIDENT[EA](?:\\s+EN\\s+EJERCICIO)?)(?:,\\s*DIP\\.\\s+[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ.\\-\\s]+?)?(?::|\\.(?=\\s+(?:[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]|[…¿¡“«(])))"
  - "^(SECRETARI[OA])(?:,\\s*DIP\\.\\s+[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ.\\-\\s]+?)?(?::|\\.(?=\\s+(?:[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]|[…¿¡“«(])))"

# Nivel 2: nombre en mayúsculas de dos o más palabras ante «:», sin «DIP.». Hay 2 marcas así en la 67.ª;
# el investigador decidió no darles un patrón de nivel 1 porque también casarían encabezados de los
# documentos leídos (LOTE A:, POR TANTO:, CÓDIGO CATASTRAL:…): las puntúa tag contra el registro.
# Mínimo 3 palabras (decisión bo-0020, que corrige bo-0013): con 2, ARTÍCULO ÚNICO: (×2) y TITULO EJECUTORIAL: puntuaban 0,70,
# lo mismo que el nombre real de 5 palabras, y abrían turno; todo nombre del padrón tiene 3 o más.
speaker_loose_pattern: "^(?P<name>(?:DIP\\.\\s+)?[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ.\\-]+(?:\\s+[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ.\\-]+){2,5})(?=\\s*:)"
```
<!-- /table -->

## 4. Del PDF al texto: extract y correct

```text
/diaries-extract --country bo --all
/diaries-correct --country bo --all
```

`extract` deja la capa fiel: el texto tal como sale del PDF, con un marcador por página, y no se limpia nunca. Su
control de fragmentación saltó en la 67.ª: la mediana de las líneas era de 8 caracteres. La causa eran 55 páginas de
tabla, el anexo de una ley de titulación de lotes, con el nombre y la cédula de identidad de cada beneficiario, una
celda por línea; en el resto de la sesión la mediana era 89. Se eligió el modo por defecto (bo-0004), y quedó apuntado
que esa tabla trae datos de particulares.

`correct` quita el mobiliario de la página y une las líneas en párrafos. En *El Redactor* hay una sola pieza de
mobiliario, el cabecero corrido con el folio. Para el reflujo se midieron cuatro variantes sobre las cuatro sesiones:

<!-- table:pais_reflujo -->
| Variante | Qué hace | Cortes a mitad de frase | Marcas separadas de su texto |
|---|---|---:|---:|
| A | la plantilla: párrafos de al menos 80 caracteres | 8.468 | 302 |
| B | la caja medida, y la marca absorbe la línea de abajo | 3.747 | 141 |
| C | B, y une pares de líneas llenas hasta 2.000 caracteres | 7 | 0 |
| D | C, con tope de 6.000 | 2 | 0 |
<!-- /table -->

Con tope de 2.000 caracteres se partían los pases de lista, que llegan a 3.791. Se eligió la D (bo-0005). Así queda la
apertura de la 76.ª en la capa fiel, con el cabecero, el folio y las líneas del PDF:

<!-- table:pais_capa_extracted -->
```extracto
---PAGE 0001---
CÁMARA DE DIPUTADOS / EL REDACTOR / MARZO 2024
245
76ª SESIÓN ORDINARIA
LEGISLATURA 2023-2024
LA PAZ, MARTES 26 DE MARZO DE 2024
[N]
PRESIDENTE EN EJERCICIO DE LA CÁMARA DE DIPUTADOS
PRESIDENTE EN EJERCICIO, DIP. [N]: Bueno, muy buenos
días colegas Diputados, Diputadas. Para instalar la presente Sesión, solicito a nuestro Diputado
Secretario, verificar el quorum reglamentario.
SECRETARIO, DIP. [N]: Muchas gracias. Buenos días, muchas
gracias hermana Presidenta en ejercicios.
Vamos a proseguir a llamar lista para verificar el quorum correspondiente, vamos con Chuquisaca.
(Llama lista).
```
<!-- /table -->

Y así, ya corregida:

<!-- table:pais_capa_corrected -->
```extracto
76ª SESIÓN ORDINARIA LEGISLATURA 2023-2024 LA PAZ, MARTES 26 DE MARZO DE 2024 [N]
PRESIDENTE EN EJERCICIO DE LA CÁMARA DE DIPUTADOS

PRESIDENTE EN EJERCICIO, DIP. [N]: Bueno, muy buenos días colegas Diputados, Diputadas. Para instalar la presente Sesión, solicito a nuestro Diputado Secretario, verificar el quorum reglamentario.

SECRETARIO, DIP. [N]: Muchas gracias. Buenos días, muchas gracias hermana Presidenta en ejercicios.
Vamos a proseguir a llamar lista para verificar el quorum correspondiente, vamos con Chuquisaca.
(Llama lista).
```
<!-- /table -->

La comprobación a mano fue contar las palabras de una capa a la otra. Faltaban 17, todas en fronteras de página: la
regla del motor borra el número que va delante del separador de página, y en *El Redactor* el folio va detrás. Eran
celdas del anexo, llamadas de nota y guiones de lista, ninguna de discurso, y se declararon sin tocar el motor
(bo-0006). El comando de `correct` tal como lo escribe su SKILL falla, porque argparse lee `'---PAGE'` como otra opción;
hay que escribir `--page-break-marker=---PAGE`.

## 5. Metadatos y duplicados: meta y dedupe

```text
/diaries-meta --country bo --all
/diaries-dedupe --country bo
```

El pase automático de `meta` sacó bien la fecha, el número y el tipo en tres sesiones, de la carátula. Falló en dos
cosas. Quien preside salió mal en las cuatro: el motor toma lo que sigue a la etiqueta del cargo, y en la carátula
boliviana el nombre va antes. Y la 154.ª no tiene carátula, porque empieza después de la medianoche dentro del tomo de
julio. El SKILL, además, da la máxima autoridad al cabecero corrido, que aquí es del tomo: dice el mes y el año, no el
día, y en la 154.ª dice julio siendo 1 de agosto.

Leyendo las cuatro sesiones se vio cómo se escribe la presidencia en esta acta: la carátula la nombra, su primera marca
también, y los cambios los anota la redacción («-Asume la Presidencia, la Diputada …-»). Con eso, la presidencia va
por tramos. Así queda la 153.ª en su archivo de meta, sin los nombres: un tramo que abre la carátula y dos de relevo,
con las marcas de cada género que caen en cada uno:

<!-- table:pais_meta -->
```extracto
{
 "date": "2024-07-31",
 "session_number": 153,
 "session_type": "ordinaria",
 "legislature": "2020-2025",
 "legislative_session": "2023-2024",
 "presidency": {"scope": "segments", "segments": [
  {"via": "prolegomena", "genero": null, "marcas": {"m": 38, "f": 0}},
  {"via": "relevo", "genero": "f", "marcas": {"m": 0, "f": 1}},
  {"via": "relevo", "genero": "m", "marcas": {"m": 55, "f": 0}}
 ]}
}
```
<!-- /table -->

Dos preguntas:

- **La 154.ª.** Fecha y número salen de la fórmula de instalación y de su carátula, que está en el tomo de agosto
  (bo-0007).
- **La 76.ª.** La preside una diputada, pero 5 de las 65 marcas de la presidencia dicen «PRESIDENTE»: son erratas de
  la redacción, y los 65 turnos van a la misma persona (bo-0008).

`dedupe` no encontró duplicados. La comprobación propia fue el par 153.ª-154.ª, que comparten una página del tomo: el
corte no repite texto. Si se añadiera el tomo de agosto, la 154.ª saldría dos veces, y ahí sí trabajaría dedupe.

## 6. Los diputados antes de tag

```text
/diaries-deputies --country bo
```

`deputies` puede ir antes de `tag` cuando el acta trae pase de lista con nombres, y conviene: tag usa el registro para
puntuar las marcas que no llevan «DIP.». En *El Redactor*, la secretaría lee la lista al abrir la sesión, departamento
por departamento: 129, 129, 130 y 130 nombres, con el mismo reparto por departamento que los 130 escaños. Aquí no
hay fragmento: el pase es una ristra de nombres, y los que la maquetación parte entre dos líneas se escaparían del
tapado.

El lector de pases de la librería trae fijas las anclas del de Uruguay («Asisten los señores Representantes:») y no
vio el boliviano: hizo falta un lector propio. Las 207 grafías de los cuatro pases se reducen a 204 personas (3 pares
difieren en una tilde o en el orden). Son 74 más que escaños, y son las 74 que aparecen en una sola sesión: suplentes.
Se preguntó y se aceptaron como titulares y suplentes sin distinguir (bo-0012, que corrige la redacción de la evidencia
de bo-0009: el primer ejemplo de `--supersede` de este recorrido). La comisión cuenta como ausencia (bo-0010): 478
presencias y 40 ausencias. Y el partido queda vacío, y declarado (bo-0011), porque ni el pase ni las marcas lo dicen.

## 7. Los oradores: tag

```text
/diaries-tag --country bo --all
```

La primera pasada en la 67.ª etiquetó 398 marcas por el patrón estricto y 5 por el flexible. De esas 5, 2 eran las
diputadas sin «DIP.» y 3 eran encabezados de un proyecto de ley leído por la secretaría («ARTÍCULO ÚNICO:»). El
puntuador les daba 0,70, lo mismo que a un nombre real de cinco palabras: el umbral no podía separarlos. Se preguntó, y
el patrón flexible pasó a exigir al menos tres palabras, porque los 204 nombres del registro tienen tres o más
(bo-0013, cuya consecuencia corrigió después bo-0020). Segunda pasada: solo las dos diputadas.

El control absoluto de tag, `verify_tagging`, dio 0 marcas sin etiquetar en las cuatro sesiones. Así queda la apertura
de la 76.ª:

<!-- table:pais_capa_tagged -->
```extracto
76ª SESIÓN ORDINARIA LEGISLATURA 2023-2024 LA PAZ, MARTES 26 DE MARZO DE 2024 [N]
PRESIDENTE EN EJERCICIO DE LA CÁMARA DE DIPUTADOS

<int speaker="PRESIDENTE EN EJERCICIO">Bueno, muy buenos días colegas Diputados, Diputadas. Para instalar la presente Sesión, solicito a nuestro Diputado Secretario, verificar el quorum reglamentario.</int>
<int speaker="SECRETARIO">Muchas gracias. Buenos días, muchas gracias hermana Presidenta en ejercicios.
Vamos a proseguir a llamar lista para verificar el quorum correspondiente, vamos con Chuquisaca.
(Llama lista).
```
<!-- /table -->

Fíjate en las etiquetas: `<int speaker="SECRETARIO">`. La marca del acta decía «SECRETARIO, DIP. [N]:», y tag guarda
solo el cargo. El nombre sigue en la capa corregida, y en el paso siguiente eso importará.

## 8. La matriz y la vinculación

```text
/diaries-matrix --country bo --all
/diaries-match --country bo
/diaries-merge --country bo
/diaries-standardize --country bo
```

**matrix** convierte el texto etiquetado en una fila por turno. La primera pasada descartó un turno de 8 caracteres por
corto; era una interjección de un diputado, y es habla (bo-0014). Su auditoría de marcas incrustadas dio 0,00 %, y el
SKILL avisa de que un 0 % es sospechoso hasta que se explica. Una búsqueda propia del terminador y el recuento de las
líneas sin etiquetar encontraron marcas metidas dentro de otros turnos, 8 de ellas en un mismo pasaje de la 67.ª,
donde la redacción cerró las marcas con punto:

<!-- table:pais_punto -->
```extracto
PRESIDENTE. Muchas gracias colega Diputado. Vamos a ceder la palabra al colega Diputado [N].
DIP. [N]. Muchas gracias Presidente.
```
<!-- /table -->

`verify_tagging` no las veía porque usa el mismo patrón que tag. Las marcas pasaron a aceptar «.» además de «:»
(bo-0015), y la 67.ª pasó de 400 turnos a 408; las otras tres sesiones no cambiaron.

**match** vincula cada forma de orador con el registro. La primera pasada vinculó 0 de 76: el registro se había escrito
con comas, una columna llevaba «;» dentro y `fuzzy_match` adivinó «;» como separador. Con el archivo arreglado, 71
formas casan con un único diputado y las 5 restantes son cargos (PRESIDENTE, PRESIDENTA, SECRETARIO…), que se
atribuyen en merge. La comprobación a mano cruzó cada turno con el pase de su sesión: una marca nombraba a un diputado
que no estaba en la sala. La presidencia acababa de dar la palabra «por alusión» a una diputada, y quien habla responde
a la alusión: el turno va a ella, por un override de sesión que no toca `speaker_raw` (bo-0017).

**merge** une la matriz con la tabla de vinculación y el registro. Las filas de la mesa se atribuyen por tramos, pero
en este recorrido eso tuvo que esperar: `attribute_presidency` lee el canónico, que en este punto aún no existe, y se
ejecutó dentro de standardize (abajo). Con la presidencia ya atribuida, merge quedó en FLAG, con una confianza de
0,794: las 186 filas de la secretaría no tenían diputado. Al preguntar, Claude Code dijo que quien abre la secretaría no se nombra en el acta, y
con esa evidencia se decidió declararlo y aceptar (bo-0022). Era falso: la apertura de la 76.ª lo muestra, la primera
marca de la secretaría lleva el nombre, y tag solo había guardado el cargo. Se vio al comparar las capas para esta
página. Se volvió a preguntar con la evidencia buena, y la secretaría se atribuyó por tramos en las tres sesiones que
la nombran, como la presidencia (bo-0025). La comprobación: antes de cada turno de la secretaría, la presidencia suele
llamarla por su nombre («Secretaria, Diputada …»), y los 39 vocativos que pueden comprobarlo coinciden. La 154.ª
empieza a mitad de la sentada, sin marca con nombre, y sus 26 filas quedan sin diputado:

<!-- table:pais_vinculacion -->
| Quién habla | Filas | Con id_dep | Personas |
|---|---:|---:|---:|
| Diputados (marca «DIP.») | 260 | 260 | 70 |
| Presidencia | 456 | 456 | 2 |
| Secretaría | 186 | 160 | 4 |
| **Filas de habla** | 898 | 872 |  |
<!-- /table -->

**standardize** aplica el esquema final de 16 columnas, y aquí el orden del SKILL no funcionó para un país nuevo:
cinco scripts de la librería leen el canónico, que en ese momento aún no existe. Y uno de ellos, `attribute_presidency`,
tenía un fallo: si la fila de la carátula ya estaba en el archivo, contaba los turnos de una manera al atribuir y de otra
al buscar los relevos, y cada relevo caía una fila antes. En la 153.ª, la diputada que asume la presidencia durante un
turno volvía al presidente anterior:

<!-- table:pais_relevo -->
```extracto
DIP. [N]: … -Asume la Presidencia, la Diputada [N]-
PRESIDENTA: Ausencia, Cuarto Intermedio, colegas Diputados, Diputadas, 1 hora.
-Reasume la Presidencia, el Diputado [N]-
```
<!-- /table -->

La salida fue atribuir la mesa antes de añadir las carátulas (bo-0018) y dejar la cadena entera en un script que se
ejecuta dos veces y sale idéntica byte a byte. Después de esta corrida, la librería corrigió el fallo el 25 de octubre
de 2026: la carátula ya no cuenta como turno, y la mesa sale igual con ella que sin ella. En este paso entraron también los datos personales: los 1.674 números de
cédula de los documentos leídos pasan a «[C.I.]» (bo-0021, que corrige el recuento de filas de bo-0016); los nombres de los
beneficiarios se quedan, y se declaran.

Y el sexo. El script de la librería lleva fija su lista de países; con Bolivia añadida, solo dispara la morfología del
nombre, y da sexo al 51 % de quienes hablan, con un 71 % de mujeres. La señal del acta boliviana está en otro sitio: la
presidencia llama a quien va a hablar («colega Diputada …»). Con ese vocativo, la nota de relevo y el cargo de la
secretaría, 72 de las 73 personas que hablan tienen sexo; la morfología completa el registro y acierta en 36 de 36
casos, pero cubre al 84 % de las mujeres y al 23 % de los hombres, así que los vacíos del registro son casi todos
hombres (bo-0024, que corrige un recuento de bo-0019). El juez del género, que compara el sexo de quien preside con el
vocativo de quien le contesta, solo reconocía el tratamiento («Señor Presidente»); con el vocativo boliviano coinciden 345 de 349 filas, y
las 4 discrepancias tienen explicación. Una es un lapsus de la secretaria entre dos «Presidente»:

<!-- table:pais_lapsus -->
```extracto
SECRETARIA: Existe el apoyo, Presidente.
PRESIDENTE: Las y los Diputados que estén de acuerdo con la Dispensación de la lectura del Informe del Proyecto de Ley No 248/2023-2024, sírvase levantar la mano. Informe, Diputada Secretaria.
SECRETARIA: Mayoría absoluta, Presidenta.
```
<!-- /table -->

## 9. Validar

```text
/diaries-validate --country bo
```

`validate` saca una muestra sembrada de 300 filas, comprueba cada una y prepara 200 filas PASS para que una persona las
lea buscando fugas: texto de otro orador dentro de un turno, que ninguna prueba automática ve. En la primera pasada
saltó un FLAG por caracteres corrompidos: viñetas de una fuente de símbolos que el PDF trae como caracteres de uso
privado. En todo el corpus eran 35, y pasaron a «•» (bo-0023). La persona que construye el corpus eligió leerlas todas.

<!-- table:pais_validacion -->
| Prueba | Resultado |
|---|---|
| Muestra sembrada, primera pasada | 300 filas: 299 PASS, 1 FLAG |
| La misma muestra, con la secretaría atribuida | 300 PASS; 11 no aplicables |
| Calibración de fuga: filas PASS leídas a mano | 200; marcadas como fuga, 0; IC 95 % (Wilson) [0 % – 1,88 %] |
| De ellas, turnos de la secretaría atribuidos después | 30, por revisar aparte |
| Cédulas de identidad → «[C.I.]» | 1.674 en 4 filas |
| Viñetas de uso privado → «•» | 35 en 6 filas |
<!-- /table -->

Con 0 fugas en 200 filas, el intervalo de Wilson llega al 1,88 %, y esa es la cifra que se publica; el script anuncia
«< 1,5 %», por la regla de tres, que con muestras así se queda corta. La semilla permite rehacer la muestra: con la
secretaría ya atribuida, las mismas 300 filas dan 300 PASS. Pero 30 de las 200 de la calibración son turnos de la
secretaría que se leyeron cuando aún no tenían diputado, así que su atribución se revisa aparte, con el turno anterior
delante.

## 10. Documentar, informar y registrar

```text
/diaries-document --country bo
/diaries-report --country bo
```

`document` entrevista al procesador (la fuente, el registro, el proceso, los autores y las limitaciones) y escribe
`corpus_info.json`, el README, el diccionario de datos y los metadatos `dataset.jsonld`, que declaran los dos archivos
de la entrega. La vinculación se publica con la definición de la colección, tr-0109: bruta y efectiva, 97,1 % de las
filas de habla. Son iguales porque no se descuenta nada: la secretaría la ocupan diputados, así que sus filas sin
nombre son un hueco de este corpus, no una exclusión. La primera vez, Claude Code calculó la bruta sobre todas las filas
y no sobre las de habla; el script de la vinculación lo compara con lo publicado, no coincidía, y se corrigió.

`report` escribe el informe interno del proceso. El estado del pipeline dice «100 % de automatización», porque ningún
paso acabó en FLAG o HALT sin resolver. El informe pone delante lo que el estado no ve: 25 preguntas respondidas, 25
decisiones, 76 formas de orador revisadas y congeladas, 200 filas leídas a mano y 14 scripts propios. Así terminó cada
skill (bootstrap y dedupe no escriben entrada en el estado):

<!-- table:pais_estado -->
| Skill | 67.ª | 76.ª | 153.ª | 154.ª | País |
|---|---:|---:|---:|---:|---:|
| `diaries-ocr` | omitido | omitido | omitido | omitido |  |
| `diaries-extract` | 1,00 | 1,00 | 1,00 | 1,00 |  |
| `diaries-correct` | 0,95 | 0,95 | 0,95 | 0,95 |  |
| `diaries-meta` | 1,00 | 1,00 | 1,00 | 0,97 |  |
| `diaries-tag` | 0,92 | 0,85 | 0,97 | 1,00 |  |
| `diaries-matrix` | 1,00 | 0,99 | 0,99 | 1,00 |  |
| `diaries-deputies` |  |  |  |  | 1,00 |
| `diaries-match` |  |  |  |  | 0,93 |
| `diaries-merge` |  |  |  |  | 0,97 |
| `diaries-standardize` |  |  |  |  | 1,00 |
| `diaries-validate` |  |  |  |  | — |
| `diaries-document` |  |  |  |  | 1,00 |
| `diaries-report` |  |  |  |  | 1,00 |
<!-- /table -->

El registro de decisiones es la historia del corpus. Cinco decisiones se corrigieron con `--supersede`, y ninguna se
borró: dos recuentos mal hechos, una evidencia mal redactada, una consecuencia mal descrita y una evidencia falsa.

<!-- table:pais_decisiones -->
| Id | Paso | Decisión | Estado |
|---|---|---|---|
| bo-0001 | fuentes | Muestra de método: 4 sesiones de la Cámara, de marzo y julio de 2024; las sesiones conjuntas, fuera. | vigente |
| bo-0002 | fuentes | Los tomos mensuales se cortan en un PDF por sesión por su página de cabecera; preliminares e índice, fuera. | vigente |
| bo-0003 | fuentes | El 31 de julio son dos sesiones, la 153.ª y la 154.ª. | vigente |
| bo-0004 | extract | La 67.ª se extrae en modo fiel aunque salte el control de fragmentación (55 páginas de tabla del anexo). | vigente |
| bo-0005 | correct | Un solo mobiliario, el cabecero corrido, y el reflujo D, con cajas de hasta 6.000 caracteres. | vigente |
| bo-0006 | correct | Se declaran, sin tocar el motor, las 17 palabras que la regla del folio quita en las fronteras de página. | vigente |
| bo-0007 | meta | Fecha, número y tipo salen de la carátula; los de la 154.ª, de la fórmula de instalación y de la carátula del tomo de agosto. | vigente |
| bo-0008 | meta | En la 76.ª, las 5 marcas «PRESIDENTE:» sueltas son erratas por la presidenta. | vigente |
| bo-0009 | deputies | El padrón sale de los pases de lista. | superada por bo-0012: la evidencia estaba mal redactada |
| bo-0010 | deputies | Asistencia por sesión: licencia, baja médica y comisión cuentan como ausencia. | vigente |
| bo-0011 | deputies | party queda vacío, y se declara: el acta no lo da. | vigente |
| bo-0012 | deputies | Padrón de los cuatro pases de lista, 204 personas; titulares y suplentes sin distinguir. | vigente; sustituye a bo-0009 |
| bo-0013 | tag | Las marcas sin «DIP.» exigen al menos 3 palabras. | superada por bo-0020: su consecuencia describía mal lo que vería verify_tagging |
| bo-0014 | matrix | La matriz no descarta turnos por su longitud: una interjección de 8 caracteres es habla. | vigente |
| bo-0015 | tag | Las marcas de nivel 1 aceptan «.» como terminador. | vigente |
| bo-0016 | standardize | Las cédulas de identidad se seudonimizan en el canónico. | superada por bo-0021: contaba 3 filas con cédulas; son 4 |
| bo-0017 | match | El turno cuya marca nombra a un diputado ausente va, por override, a la diputada aludida. | vigente |
| bo-0018 | standardize | La mesa se atribuye antes de añadir las carátulas, para esquivar un fallo de attribute_presidency. | vigente |
| bo-0019 | standardize | sex sale del vocativo y de la morfología del nombre. | superada por bo-0024: decía 35 de 35; son 36 de 36, y faltaba la cobertura por sexo |
| bo-0020 | tag | El patrón de nivel 2 exige de 3 a 6 palabras. | vigente; sustituye a bo-0013 |
| bo-0021 | standardize | Las cédulas pasan a «[C.I.]» en el canónico. | vigente; sustituye a bo-0016 |
| bo-0022 | merge | La secretaría se declara sin id_dep. | superada por bo-0025: su evidencia era falsa: la primera marca de la secretaría sí la nombra |
| bo-0023 | standardize | Las viñetas de uso privado pasan a «•». | vigente |
| bo-0024 | standardize | sex sale del vocativo, de la nota de relevo y de la morfología, con la cobertura medida por sexo. | vigente; sustituye a bo-0019 |
| bo-0025 | merge | La secretaría se atribuye por tramos en las 3 sesiones que la nombran. | vigente; sustituye a bo-0022 |
<!-- /table -->

Esto es lo que salió mal, de quién era y cómo se vio. Los fallos de los skills y de la librería son la lista para
`/diaries-refine`; los del agente son la razón de las comprobaciones a mano.

<!-- table:pais_fallos -->
| De quién | Paso | Qué falló | Cómo se vio | Qué se hizo |
|---|---|---|---|---|
| agente | match | el padrón se escribió con comas y una columna llevaba «;» dentro: `fuzzy_match` eligió «;» como separador | 0 de 76 formas vinculadas en la primera pasada | padrón con «;»; los 204 id, idénticos |
| agente | merge | la evidencia de bo-0022 era falsa: que quien abre la secretaría no se nombra | al comparar las capas para esta página | se volvió a preguntar; bo-0025 atribuye 160 filas |
| agente | report | la vinculación bruta se calculó sobre todas las filas, no sobre las de habla | `vinculacion_tr0109.py` no coincidía con corpus_info.json | corregido, y regenerada la documentación |
| agente | meta, merge | dos recuentos mal dichos al preguntar: «54 de 59» por 59 de 65, y «160 de 162» por 160 de 160 | al registrar la decisión | la decisión lleva la cifra buena |
| agente | tag | cuatro escrituras del estado a la vez sobre el mismo archivo | llegaron las cuatro, pero es una carrera | en serie desde entonces |
| librería | standardize | `attribute_presidency` cuenta la fila de la carátula en un sitio y no en otro: cada relevo cae una fila antes | la fila 77 de la 153.ª volvía al presidente anterior | la mesa se atribuye antes de añadir las carátulas (bo-0018); la librería lo corrigió el 25 de octubre de 2026 |
| librería | merge | no hay atribución de la secretaría, y tag guarda solo el cargo | 186 filas de la secretaría sin id_dep | un script propio (bo-0025) |
| skill | matrix | `verify_tagging` y la auditoría de matrix usan el terminador de la config: las marcas cerradas con punto son invisibles para los dos | una búsqueda propia del terminador | bo-0015: las marcas aceptan «.» |
| skill | correct | el comando del SKILL falla: argparse lee `'---PAGE'` como otra opción | al ejecutarlo | `--page-break-marker=---PAGE` |
| librería | deputies | `parse_attendance.py` lleva fijas las anclas del pase de Uruguay | no vio el pase boliviano | un lector propio |
| librería | standardize | `derive_sex.py` lleva fija su lista de países; con Bolivia añadida, solo dispara la morfología | sexo para el 51 % de quienes hablan, con un 71 % de mujeres | vocativo, nota de relevo y morfología (bo-0024) |
| skill | validate | `prepare_leak_calibration.py` anuncia «< 1,5 %» para 0 de 200 (regla de tres) | al calcular el intervalo | se publica el de Wilson |
<!-- /table -->

Y estos son los scripts propios: lo que ningún skill cubría, o lo que la librería hacía mal. No están en el
repositorio: son de este proyecto, y alguno lleva nombres de diputados.

<!-- table:pais_scripts -->
| Script | Para qué |
|---|---|
| `auditoria_genero_bo.py` | el juez del género, con el vocativo boliviano |
| `completar_canonico_bo.py` | lo que `recover_frontmatter` y `attribute_presidency` dejan vacío |
| `cortar_tomos.py` | corta los tomos en un PDF por sesión |
| `indices.py` | lee el índice de cada tomo: qué sesiones trae |
| `meta_bo.py` | aplica la heurística de meta registrada para Bolivia |
| `padron_bo.py` | el padrón desde los pases de lista |
| `pase_de_lista_bo.py` | lee el pase de lista: `parse_attendance.py` solo conoce el de Uruguay |
| `secretaria_bo.py` | la secretaría por tramos (bo-0025) |
| `seudonimizar_ci_bo.py` | cédulas → «[C.I.]» (bo-0021) |
| `sexo_bo.py` | sex por vocativo, relevo y morfología (bo-0024) |
| `standardize_bo.py` | standardize, declarando las columnas vacías por decisión |
| `standardize_cadena_bo.sh` | la cadena de standardize en el orden que funciona |
| `tabla_match_bo.py` | la tabla de vinculación y el override de sesión |
| `vinetas_bo.py` | viñetas de uso privado → «•» (bo-0023) |
<!-- /table -->

## 11. Lista de comprobación

1. Escribe para qué es el corpus y cuánta cobertura necesita: es la primera decisión del registro.
2. Trabaja en una carpeta aparte, con copias de la fuente y su huella; un archivo por sesión, llamado por su fecha.
3. Lo que ningún skill hace (cortar tomos, leer un índice) va en un script propio, y se comprueba: las palabras de
   antes y de después.
4. Lee la configuración que escribe `bootstrap`.
5. Si salta un control de `extract`, averigua por qué antes de elegir el modo: aquí era una tabla con datos de
   particulares.
6. Mide las variantes del reflujo en `correct` y cuenta las palabras que se pierden de una capa a la otra.
7. Comprueba la fecha, el número y quién preside de cada sesión contra su carátula, y por tramos.
8. Si el acta trae pase de lista, construye el registro antes de `tag`.
9. Lee una a una las marcas que etiqueta el patrón flexible.
10. Un 0 % de marcas incrustadas es sospechoso: busca el terminador con un patrón propio.
11. Una primera vinculación de 0 es un problema del archivo, no de la vinculación.
12. Cruza cada orador vinculado con el pase de su sesión.
13. Antes de aceptar un FLAG, compara las capas: lo que tag no guardó puede estar en `corrected/`.
14. Ejecuta la cadena de `standardize` dos veces y compara byte a byte.
15. Seudonimiza las cédulas y declara lo que queda.
16. Mide la cobertura del sexo por sexo, no solo en total.
17. Lee tú la calibración de fuga, y publica el intervalo de Wilson.
18. Cada decisión, con evidencia medida; las equivocadas se corrigen con `--supersede`, nunca se borran.
19. La tasa de automatización, siempre junto a las decisiones humanas.

> **Pídelo de una vez:** «Quiero construir con los skills diaries-* un corpus de las sesiones plenarias de esta cámara,
> a partir de los PDF de `source/{iso2}/raw/`, un archivo por sesión. Ve paso a paso, de `/diaries-bootstrap` a
> `/diaries-report`; antes de cada pregunta enséñame la evidencia medida, y registra cada respuesta con
> `/diaries-decide`. Comprueba a mano lo que cada skill no puede ver de sí mismo: las palabras de una capa a la otra,
> las marcas que deja sin etiquetar, los oradores contra el pase de lista y lo que tag no guarda. Si un skill o la
> librería fallan, no los parchees: haz un script propio, apúntalo y dímelo al final para `/diaries-refine`.
> Seudonimiza las cédulas y no cites nombres de particulares.»
