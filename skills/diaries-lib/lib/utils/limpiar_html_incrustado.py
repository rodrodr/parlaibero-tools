#!/usr/bin/env python3
"""Quita el marcado HTML que se coló en el texto, conservando el contenido de las celdas.

Hallado el 2026-08-10 al descubrir el vocabulario de mobiliario de UY: entre las líneas más
repetidas del corpus estaban `</tr> <tr>`, `<td></td> <td></td>` y `<td>N</td> <td>N</td>`.

Alcance: **UY 392.782 etiquetas en 974 filas** y **PA 15.484 en 381**; el resto, testimonial.
Están concentradas en los Prolegomena, donde el SUMARIO y el ÍNDICE del acta venían como tabla
HTML dentro de un texto por lo demás en markdown.

**No se borra la fila: el contenido de las celdas ES dato** —«1) ASISTENCIAS Y AUSENCIAS….. 309»
son las entradas del índice con su página—. Se retira solo el marcado, y se conserva la
estructura para que la tabla siga leyéndose:

    </tr>  →  salto de línea      (fin de fila)
    </td>  →  separador « · »     (fin de celda)
    resto  →  se elimina

CLI:
    python limpiar_html_incrustado.py --country uy [--medir]
"""
import argparse
import csv
import html
import os
import re
import sys

csv.field_size_limit(sys.maxsize)

FIN_FILA = re.compile(r"</\s*tr\s*>", re.I)
FIN_CELDA = re.compile(r"</\s*t[dh]\s*>", re.I)
ETIQUETA = re.compile(r"</?\s*(?:table|thead|tbody|tfoot|tr|td|th|p|br|div|span|b|i|u|em|"
                      r"strong|font|col|colgroup|caption)\b[^>]*>", re.I)


def limpia(t: str):
    if "<" not in t:
        return t, 0
    n = len(ETIQUETA.findall(t))
    if not n:
        return t, 0
    t = FIN_FILA.sub("\n", t)
    t = FIN_CELDA.sub(" · ", t)
    t = ETIQUETA.sub("", t)
    t = html.unescape(t)
    t = re.sub(r"[ \t]*·[ \t]*(?=\n|$)", "", t)      # separador huérfano al final de fila
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip(), n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", required=True)
    ap.add_argument("--medir", action="store_true")
    a = ap.parse_args()
    iso, I = a.country.lower(), a.country.upper()
    p = f"source/{iso}/standardize/{I}_interventions.csv"
    with open(p, encoding="utf-8") as fh:
        d = csv.Sniffer().sniff(fh.readline(), ";,").delimiter
        fh.seek(0)
        r = csv.DictReader(fh, delimiter=d)
        campos, filas = list(r.fieldnames), list(r)

    fil = tot = 0
    antes = despues = 0
    muestra = None
    for x in filas:
        t = x["text"]
        antes += len(t)
        nt, n = limpia(t)
        despues += len(nt)
        if n:
            fil += 1
            tot += n
            if muestra is None:
                i = t.find("<t")
                muestra = (t[max(0, i - 40):i + 150], nt[max(0, i - 40):i + 150])
            if not a.medir:
                x["text"] = nt
    print(f"  {I} · filas con marcado {fil:,} · etiquetas retiradas {tot:,}")
    print(f"     texto {antes:,} → {despues:,} caracteres ({(despues-antes)/max(antes,1)*100:+.2f}%)")
    if muestra:
        print(f"     antes:  {muestra[0][:110]!r}")
        print(f"     después:{muestra[1][:110]!r}")
    if a.medir:
        return
    bak = p.replace(".csv", ".pre_html.csv")
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
