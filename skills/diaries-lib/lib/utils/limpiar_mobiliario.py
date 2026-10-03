#!/usr/bin/env python3
"""Quita el mobiliario de página que sobrevivió a `correct`: el marcador y su bloque.

Detectado el 2026-08-10 con el inspector HTML, mirando registros de BR uno a uno:

    ---PAGE 0005---
    Tipo: Sessão Solene - CN
    Data: 01/01/03
    Montagem: Lívia 104

Alcance real medido en los 15 corpus: **BR 566.218 filas (34,66 %)**, PE 175.247 (20,89 %),
ES 22.756 (4,26 %), PT 4.882, CR 381, UY 51, y menos de 40 en el resto.

## Dos ámbitos distintos, y no hay que confundirlos

**El marcador `---PAGE N---` lo pone la EXTRACCIÓN y es común a todos los países**: una línea
entera que solo es eso nunca es contenido, así que se quita en todos.

**El bloque que lo rodea es de cada país** y hay que descubrirlo por separado. Solo el de BR es
regular —`Tipo:` 98,8 %, `Data:` 99,8 %, `Montagem:` 94 % en las líneas +1, +2 y +3—, así que es
el único que se retira aquí. Los de PE (`Diario de los Debates -`, `ESIÓN`), ES (`Página`,
`Sesión plenaria núm. N`), CR (`Asamblea Legislativa - Departamento de Actas`) y UY (`Biblioteca
del Poder Legislativo…`) aparecen en posiciones variables y **quedan pendientes de su propia
medición**: meterlos con el patrón de BR sería adivinar.

## Cómo se quita

Línea ENTERA y EN BLOQUE, nunca por subcadena ni por recurrencia ([[feedback_mobiliario_pagina]]).
Tras el marcador se retiran las líneas CONSECUTIVAS que casen con el vocabulario del país, y se
para en la primera que no case — que es texto real. Importa porque el bloque **parte frases**:

    …foram solenemente empossados nos cargos,          ← antes
    ---PAGE 0005--- · Tipo: · Data: · Montagem:        ← se va
    respectivamente, de Presidente e Vice-Presidente…  ← después

Al retirarlo la frase se recompone sola.

CLI:
    python limpiar_mobiliario.py --country br [--medir]
"""
import argparse
import csv
import os
import re
import sys

csv.field_size_limit(sys.maxsize)

# Común a todos: lo escribe la extracción, no la fuente.
# ⚠ El marcador de página tiene DOS formas según cómo se extrajo el país: «---PAGE 12---» lleva
# número y «--- PAGE BREAK ---» no. Exigir `\d+` dejaba fuera los 49.860 de PY —el 12 % de sus
# filas— y el limpiador informaba «45 filas con mobiliario» sobre 44.943 que lo tenían.
MARCADOR = re.compile(r"^\s*-{2,}\s*PAGE\s*(?:\d+|BREAK)\s*-{2,}\s*$", re.I)

# Bloque que SIGUE al marcador, por país. Solo se rellena lo que se ha medido.
BLOQUE = {
    # ⚠ re.M es imprescindible: sin él, `rx.search(texto)` solo mira la PRIMERA línea y la
    # salida temprana de `limpia` descartaba la fila entera. Costó 10.956 líneas sin quitar.
    "br": re.compile(r"^\s*(?:Tipo|Data|Montagem|N[úu]mero\s+Sess[ãa]o)\s*:|"
                     r"^\s*COORDENA[ÇC][ÃA]O\s+DE\s+REDA[ÇC][ÃA]O", re.I | re.M),
    # PY · tras «--- PAGE BREAK ---» viene la cabecera, con el folio DELANTE o DETRÁS y a veces
    # un punto pegado: «8 CAMARA DE DIPUTADOS», «CAMARA DE DIPUTADOS 11», «.HONORABLE CAMARA DE
    # DIPUTADOS». En medio el OCR deja basura suelta —«o a», «—»—, que el bloque se lleva por
    # delante. 49.860 saltos en 44.943 filas, el 12 % del corpus.
    # ⚠ NO se toca «PLANTEL DE FUNCIONARIOS» (colofón con los nombres de la redacción) ni, sobre
    # todo, «Tiene la palabra el Diputado Nacional», que también sigue al salto 211 veces y es
    # CONTENIDO. El ancla es CAMARA DE DIPUTADOS o DIARIO DE SESIONES, no «lo que va detrás del
    # salto» ([[feedback_mobiliario_pagina]]).
    "py": re.compile(r"^\s*[.\-—\s]*\d{0,4}\s*(?:HONORABLE\s+)?C[ÁA]MARA\s+DE\s+DIPUTADOS"
                     r"\s*\d{0,4}\s*[.\-—]?\s*$|^\s*DIARIO\s+DE\s+SESIONES\s*$", re.I | re.M),
}
MAX_BLOQUE = 4          # el bloque de BR mide 3 líneas; 4 deja margen sin invadir texto

# ⚠ TODOS estos patrones llevan re.M: sin él, el `search()` de la salida temprana solo mira la
# PRIMERA línea de la fila y descarta el resto. Es el mismo fallo que costó 10.956 líneas en BR;
# cayó dos veces en el mismo día.
# ── mobiliario que se cuela como PREFIJO de una línea con texto detrás ────────────────
# AR parte la palabra y mete el cabecero en medio, en la MISMA línea que la continuación:
#     …del cambio de domi-
#     Abril 6 de 2005 cilio
# Por eso no basta con borrar líneas enteras: hay que decapitar el prefijo y dejar el resto.
# El OCR corta el nombre del mes —«Abri 18 de 2001» por «Abril 18 de 2001»—, así que se casa
# por RAÍZ de al menos cuatro letras y se deja libre la terminación.
_MES = (r"(?:ener|febr|marz|abri|mayo|juni|juli|agos|septi|setie|octu|novi|dici)\w{0,6}")
_DIA = (r"(?:LUNES|MARTES|MI[EÉ]RCOLES|MIERCOLES|JUEVES|VIERNES|S[AÁ]BADO|SABADO|DOMINGO)")
_MESU = (r"(?:ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|SEPTIEMBRE|SETIEMBRE|"
         r"OCTUBRE|NOVIEMBRE|DICIEMBRE)")
PREFIJO = {
    # CL no trae `---PAGE N---` —viene de XML y HTML—, así que el ancla es la FORMA del propio
    # cabecero: el nombre de la cámara en versales, o la línea de identidad de la sesión
    # «SESION 3ª, EN MIERCOLES 21 DE MARZO DE 1990». El OCR la degrada mucho («SESION la»,
    # «SESION 1 1»), de ahí los sosias del dígito. 10.510 líneas en 5.390 filas.
    # ⚠ Ir variante a variante NO escala: el OCR degrada el ordinal de infinitas maneras
    # («SESION 20-», «19i!», «12'», «21&», «lB», «l i», «lOa») y la fecha admite dos jornadas
    # («DE MIERCOLES 18 A JUEVES 19 DE NOVIEMBRE»). Lo estable son los DOS EXTREMOS: la línea
    # empieza por SESION y contiene «DE {mes} DE {año}» a menos de 70 caracteres. Todo lo de en
    # medio se deja libre. Así el residuo pasó de 3.290 líneas a lo que quede sin fecha.
    "cl": re.compile(rf"^\s*(?:C[AÁ]MARA\s+DE\s+DIPUTADOS"
                     rf"|SESI[OÓ]N[^\n]{{0,70}}?[\s<>|]DE[\s<>|]+{_MESU}(?:[\s<>|]+DE[\s<>|]+[\dlOISB]{{4}})?)"
                     rf"\s*[.,:<]?\s*", re.I | re.M),
    # ES · el mastete de portada, repetido a la cabeza de muchas filas:
    #     Año 1977 · C O R T E S · Núm. 3 · DIARIO DE SESIONES · {fecha}
    # ⚠ Aquí SOLO van los inequívocos. «Cortes» y «Núm.» sueltos son PROSA —«las Cortes de la
    # Monarquía Española se reunirán»— y con `re.I` mi primera versión los decapitaba. Por eso
    # `C O R T E S` se exige con las letras SEPARADAS (así es el mastete) y sin `re.I`, y los
    # ambiguos se tratan aparte, solo cuando son la línea entera. Ver [[feedback_mobiliario_pagina]].
    "es": re.compile(r"^\s*(?:A[ñn]o\s+\d{4}"
                     r"|C\s+O\s+R\s+T\s+E\s+S(?:\s+G\s*E\s*N\s*E\s*R\s*A\s*L\s*E\s*S)?"
                     r"|DIARIO\s+DE\s+SESIONES(?:\s+DEL?)?"
                     r"|CONGRESO\s+DE\s+LOS\s+DIPUTADOS)\s*[.,:]?\s*", re.M),
    # PT · folio y mastete del Diário; el «texto detrás» suele ser el propio cabecero («N.º 10»).
    "pt": re.compile(r"^\s*(?:P[áa]gina\s*\d*"
                     r"|[IVX]+\s*S[ée]rie\s*[-–—]?\s*N[úu]mero\s*[\d.]*"
                     r"|DI[ÁA]RIO\s+DA\s+ASSEMBLEIA\s+DA\s+REP[ÚU]BLICA(?:\s*N\.?[ºo°]?\s*[\d.]*)?)"
                     r"\s*[.,:]?\s*", re.M),
    # CR · aquí el cabecero ocupa la línea ENTERA: lo que sigue al número es su propia fecha
    # («Acta de la Sesión Plenaria Nº 107 del 23 de febrero de 1996»), no discurso. Por eso el
    # patrón se come también la cola de fecha en vez de dejarla suelta.
    "cr": re.compile(r"^\s*(?:Asamblea\s+Legislativa\s*[-–—]\s*Departamento\s+de\s+\w+"
                     r"|Acta\s+(?:de\s+la\s+)?[Ss]esi[óo]n\s+Plenaria\s+N[°ºo.]*\s*[\d.]*"
                     r"|P[ÁA]GINA\s+\d+)"
                     r"(?:\s*[-–—]?\s*(?:del?|celebrada)\s+[^\n]{0,60})?\s*[.,:]?\s*", re.I | re.M),
    "ar": re.compile(rf"^\s*(?:{_MES}\s+\d{{1,2}}\s+de\s+\d{{4}}"
                     rf"|Reuni[óo]n\s+\d+\s*[ªº°\"»'’]?"
                     rf"|DSDN[-\w.]*\.indd\s*[\d\s:]*"
                     rf"|C[ÁA]MARA\s+DE\s+DIPUTADOS\s+DE\s+LA\s+NACI[ÓO]N)\s*", re.I | re.M),
}
# ⚠ Solo en VERSALES es cabecero: «La Cámara de Diputados de la Nación» en minúsculas es la
# fórmula de sanción y aparece 3.742 veces como texto legítimo. Por eso el patrón de la Cámara
# se exige en mayúsculas (el resto del prefijo lleva re.I porque el mes y «Reunión» no ambiguan).
# Mobiliario SIN marcador de página delante. La extracción no siempre emitió el `--- PAGE BREAK ---`
# —en PY falta en las legislaturas 7 a 9, que son 16.690 de los 19.145 casos— así que la cabecera
# queda suelta en medio del texto. Se retira por sustitución sobre el texto entero, no línea a
# línea, porque el folio va SEPARADO por varias líneas en blanco:
#     «HONORABLE CAMARA DE DIPUTADOS \n \n \n \n \n 115»
# ⚠⚠ El discriminador es la CAJA. «…como se había sancionado acá en la Cámara de Diputados.» es
# TEXTO y aparece 1.192 veces; el mobiliario va siempre en VERSALES. Por eso este patrón NO lleva
# `re.I`, y es lo único que lo separa del contenido ([[feedback_mobiliario_pagina]]).
LIBRE = {
    "py": re.compile(r"(?m)^[ \t.\-—]*\d{0,4}[ \t.\-—]*(?:HONORABLE[ \t]+)?"
                     r"C[ÁA]MARA[ \t]+DE[ \t]+DIPUTADOS[ \t.\-—]*"
                     r"(?:[ \t]*\n)*[ \t]*\d{0,4}[ \t.\-—]*$"),
}

LINEA_SOLA = {
    # ⚠ NADA de «línea de solo dígitos» en AR. Lo puse y borré **66.687 líneas** que eran los
    # números de los puntos del orden del día, con el título en la línea siguiente («2» →
    # «REPUDIO A DECISIONES DEL GOBIERNO»). [[feedback_mobiliario_pagina]] ya lo decía: AR tiene
    # 18.677 líneas de solo dígitos y NINGUNA es un folio. Sin ancla no hay folio.
    "ar": re.compile(r"^\s*(?:•\s*•|[-–—]{2,})\s*$", re.M),
    # SV · la transcripción intercala su propio mobiliario EN MEDIO del discurso: «SQ.» (sigue) y
    # la marca de reloj «HORA: 8:40 PM». Corta el turno en dos y deja el marcador del siguiente
    # orador incrustado detrás. 205 y 243 respectivamente. Solo si ocupan la línea entera.
    # ⚠ El «SQ.» va precedido de las INICIALES del transcriptor —«MMC/SQ.», «RdeC/SQ.», «IdeI/SQ.»—
    # y la marca de reloj termina en punto y en minúscula: «HORA: 8:40 am.». Sin contemplarlo
    # quedaban 169 de 448.
    "sv": re.compile(r"^\s*(?:[A-Za-z]{1,6}/)?SQ\.?\s*$"
                     r"|^\s*HORA\s*:\s*\d{1,2}:\d{2}\s*(?:AM|PM|[ap]\.?\s*m\.?)?\.?\s*$",
                     re.I | re.M),
    # ES · los ambiguos: valen SOLO si ocupan la línea entera, nunca como prefijo
    "es": re.compile(r"^\s*(?:N[úu]m\.?\s*[\d.]+|CORTES\s+GENERALES"
                     r"|Sesi[óo]n\s+Plenaria\s+n[úu]m\.?\s*[\d.]*)\s*[.,:]?\s*$", re.M),
}


def limpia(t: str, rx, pre=None, sola=None, libre=None):
    """Devuelve (texto_limpio, marcadores_quitados, lineas_de_bloque_quitadas)."""
    # Ojo: no basta con buscar «PAGE» para salir pronto — el bloque de cabecera aparece
    # también en filas SIN marcador, y esa salida temprana lo dejaba intacto.
    nl = 0
    if libre:
        t, nl = libre.subn("", t)
    if ("PAGE" not in t.upper() and not (rx and rx.search(t))
            and not (pre and pre.search(t)) and not (sola and sola.search(t))):
        return t, 0, nl
    L = t.split("\n")
    out, i, nm, nb = [], 0, 0, 0
    while i < len(L):
        if MARCADOR.match(L[i]):
            nm += 1
            i += 1
            # ⚠ Entre el marcador y la cabecera suele haber LÍNEAS EN BLANCO —y en PY, además,
            # basura de OCR suelta: «o a», «—»—. Parándose en la primera línea que no case, el
            # limpiador quitaba los 49.860 marcadores de PY y solo 104 cabeceras: la cabecera
            # nunca era la línea inmediatamente siguiente. Se saltan los blancos y la basura
            # corta (hasta 5 líneas: «\n o a \n — \n» son cinco), y se sigue consumiendo el
            # bloque. Saltar tantas es seguro porque el salto SOLO se consume si detrás aparece
            # la cabecera: si no aparece, no se toca nada.
            k = 0
            while rx and i < len(L) and k < MAX_BLOQUE:
                j, saltos = i, 0
                while (j < len(L) and saltos < 5
                       and (not L[j].strip() or len(L[j].strip()) <= 3)):
                    j += 1
                    saltos += 1
                if j < len(L) and rx.match(L[j]):
                    i = j + 1
                    k += 1
                    nb += 1 + saltos
                else:
                    break
            continue
        # El bloque también aparece SIN marcador delante —la extracción no siempre lo puso—:
        # 10.956 líneas `Montagem:` sueltas en BR. Se retira igual, pero exigiendo DOS o más
        # líneas consecutivas del vocabulario: una sola línea que empiece por `Data:` podría
        # ser texto real, un bloque de tres no lo es nunca.
        if rx and rx.match(L[i]):
            j = i
            while j < len(L) and j - i < MAX_BLOQUE and rx.match(L[j]):
                j += 1
            if j - i >= 2:
                nb += j - i
                i = j
                continue
        linea = L[i]
        if sola and sola.match(linea):          # línea que SOLO es mobiliario
            nb += 1
            i += 1
            continue
        if pre:
            m = pre.match(linea)
            # se decapita solo si el prefijo NO se come la línea entera de texto útil
            while m and m.end() < len(linea):
                linea = linea[m.end():]
                nb += 1
                m = pre.match(linea)
            if m and m.end() >= len(linea.rstrip()):   # la línea era solo el cabecero
                nb += 1
                i += 1
                continue
        out.append(linea)
        i += 1
    return "\n".join(out), nm, nb + nl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", required=True)
    ap.add_argument("--medir", action="store_true")
    a = ap.parse_args()
    iso, I = a.country.lower(), a.country.upper()
    p = f"source/{iso}/standardize/{I}_interventions.csv"
    rx = BLOQUE.get(iso)
    pre, sola = PREFIJO.get(iso), LINEA_SOLA.get(iso)
    with open(p, encoding="utf-8") as fh:
        d = csv.Sniffer().sniff(fh.readline(), ";,").delimiter
        fh.seek(0)
        r = csv.DictReader(fh, delimiter=d)
        campos, filas = list(r.fieldnames), list(r)

    tot = nm = nb = quita = 0
    antes = despues = 0
    for x in filas:
        t = x["text"]
        antes += len(t)
        nt, m, b = limpia(t, rx, pre, sola, LIBRE.get(iso))
        despues += len(nt)
        if m or b:
            tot += 1
            nm += m
            nb += b
            if not a.medir:
                x["text"] = nt
    print(f"  {I} · {len(filas):,} filas · con mobiliario {tot:,} ({tot/len(filas)*100:.2f}%)")
    print(f"     marcadores quitados {nm:,} · líneas de bloque {nb:,}"
          + ("" if rx else "  (sin vocabulario de bloque medido para este país)"))
    print(f"     texto {antes:,} → {despues:,} caracteres ({(despues-antes)/max(antes,1)*100:+.2f}%)")
    if a.medir:
        return
    bak = p.replace(".csv", ".pre_mobiliario.csv")
    tmp = p + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, delimiter=d)
        w.writeheader()
        w.writerows(filas)
    if not os.path.exists(bak):
        os.rename(p, bak)
    else:
        os.remove(p)
    os.rename(tmp, p)
    print("  ✓ corpus reescrito")


if __name__ == "__main__":
    main()
