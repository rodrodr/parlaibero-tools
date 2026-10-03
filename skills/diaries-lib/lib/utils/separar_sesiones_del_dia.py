#!/usr/bin/env python3
"""Devuelve su identidad propia a cada sesión del mismo día: agrupa y renumera por sesión.

Señalado por el investigador (2026-08-10) en CR: *«Lo que haces es intercalar las sesiones en
lugar de asignar un código distinto a cada una. El orden de intervención es una sucesión de
textos alternados de diferentes sesiones.»* Y es exacto — el 2009-05-28 de CR alterna:

    (sesión 7, orden 1) · (sesión 18, orden 2) · (sesión 7, orden 3) · (sesión 18, orden 4) …

**La causa es mía.** Todas las utilidades que renumeran —`fix_prolegomena`, `separar_incrustados`,
`quitar_filas_sin_texto`, `co_prolegomena_en_orden1`…— usaban la clave `(legislature, date)`, que
funde en UNA sola secuencia todas las sesiones celebradas ese día. El 1994-04-30 de CR llegó a
mezclar **once sesiones** con once Prolegomena seguidos en el orden 0.

**La clave de una sesión es `(legislature, date, session_number)`**, no la fecha.

Alcance medido antes de reparar: **4.886 jornadas con más de una sesión · ~1,95 M de filas ·
6.655 sesiones con el orden no contiguo**. BR aporta 1,22 M de filas y CR 79.661.

Qué hace:

1. **Agrupa** las filas de cada sesión en un bloque contiguo, respetando el orden relativo que ya
   tenían dentro de su sesión (ordenación estable) y el orden natural de las sesiones del día.
2. **Renumera** `intervention_order` de 1 a n dentro de cada sesión; los Prolegomena conservan 0.

CLI:
    python separar_sesiones_del_dia.py --country cr [--medir]
"""
import argparse
import csv
import os
import re
import sys
from collections import defaultdict

csv.field_size_limit(sys.maxsize)


def _num(s):
    """El número de sesión ordena por su parte numérica: «12A» va tras «12» y antes de «13»."""
    m = re.match(r"\s*(\d+)", s or "")
    return (int(m.group(1)) if m else 10 ** 9, s or "")


def _lee(p):
    with open(p, encoding="utf-8") as fh:
        d = csv.Sniffer().sniff(fh.readline(), ";,").delimiter
        fh.seek(0)
        r = csv.DictReader(fh, delimiter=d)
        return list(r.fieldnames), list(r), d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", required=True)
    ap.add_argument("--medir", action="store_true")
    a = ap.parse_args()
    iso, I = a.country.lower(), a.country.upper()
    p = f"source/{iso}/standardize/{I}_interventions.csv"
    campos, filas, d = _lee(p)

    jor = defaultdict(set)
    for x in filas:
        jor[(x["legislature"], x["date"])].add(x["session_number"].strip())
    multi = {k for k, v in jor.items() if len(v) > 1}
    afect = sum(1 for x in filas if (x["legislature"], x["date"]) in multi)
    print(f"  {I} · jornadas con más de una sesión: {len(multi):,} de {len(jor):,}"
          f" · filas afectadas {afect:,}")
    if a.medir:
        for k in list(multi)[:3]:
            v = sorted(jor[k], key=_num)
            print(f"     [{k[1]}] sesiones {v[:8]}")
        return

    # ordenación ESTABLE: la posición original se conserva dentro de cada sesión
    orden = sorted(range(len(filas)),
                   key=lambda i: (filas[i]["legislature"], filas[i]["date"],
                                  _num(filas[i]["session_number"])))
    salida = [filas[i] for i in orden]

    cnt = defaultdict(int)
    for y in salida:
        if y["intervention_order"] == "0":
            continue
        k = (y["legislature"], y["date"], y["session_number"].strip())
        cnt[k] += 1
        y["intervention_order"] = str(cnt[k])

    bak = p.replace(".csv", ".pre_sesiones.csv")
    tmp = p + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, delimiter=d)
        w.writeheader()
        w.writerows(salida)
    if not os.path.exists(bak):
        os.rename(p, bak)
    else:
        os.remove(p)
    os.rename(tmp, p)
    print(f"  ✓ {len(cnt):,} sesiones agrupadas y renumeradas")


if __name__ == "__main__":
    main()
