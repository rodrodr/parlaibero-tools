#!/usr/bin/env python3
"""Toma el número de sesión de `meta/`, que es la fuente autorizada, y no del texto.

Idea del investigador (2026-08-10): en vez de leer el número en la carátula —que solo lo declara
en CR y DO— usar `source/{iso}/meta/*.json`, donde cada acta tiene su `session_number` y su
`date` derivados en su momento del propio documento.

El problema es de PROCEDENCIA: las filas del corpus no guardan de qué acta salieron. Se reconstruye
emparejando el Prolegomena con la cabeza del `corrected/` correspondiente.

## Cómo se empareja, y por qué así

⚠ **No sirve el prefijo**: muchas actas comparten cabecera —«DEPARTAMENTO DE ACTAS / ASAMBLEA
LEGISLATIVA…»— y con 120 caracteres emparejé 1994 con 1996. ⚠ **Tampoco sirve la igualdad**: el
texto del Prolegomena ya NO es idéntico al del acta, porque después pasaron la deshifenización,
la limpieza de mobiliario y el descifrado de fuente.

Lo que funciona: una **firma distintiva** —60 caracteres tomados a 300 de profundidad, ya pasada
la cabecera común— exigiendo que identifique a UNA sola acta. En CR da 4.554 firmas unívocas y
empareja 2.534 de los 5.339 Prolegomena.

**Guardarraíl independiente**: solo se acepta el emparejamiento si la FECHA del meta coincide con
la de la fila. La fecha no participa en la firma, así que es una comprobación externa: coincide
en el 98 %, y ese 98 % es la prueba de que el emparejamiento es bueno.

CLI:
    python numero_sesion_desde_meta.py --country cr [--medir]
"""
import argparse
import csv
import glob
import gzip
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict

csv.field_size_limit(sys.maxsize)
INI, LARGO = 300, 60          # dónde empieza la firma y cuánto mide


def _N(s):
    s = "".join(c for c in unicodedata.normalize("NFD", str(s).upper())
                if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Z0-9]+", "", s)


def _abre(p, n=20000):
    o = gzip.open if p.endswith(".gz") else open
    with o(p, "rt", encoding="utf-8", errors="replace") as fh:
        return fh.read(n)


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

    firma = defaultdict(list)
    for m in glob.glob(f"source/{iso}/meta/*.json"):
        try:
            d = json.load(open(m, encoding="utf-8"))
        except Exception:
            continue
        sid = d.get("session_id") or os.path.basename(m)[:-5]
        for ext in (".txt", ".txt.gz"):
            p = f"source/{iso}/corrected/{sid}{ext}"
            if os.path.exists(p):
                firma[_N(_abre(p))[INI:INI + LARGO]].append(
                    (str(d.get("session_number", "") or ""), str(d.get("date", "") or "")))
                break
    uni = {k: v[0] for k, v in firma.items() if len(v) == 1 and len(k) == LARGO}
    if not uni:
        print(f"  {I} · sin `meta/` o sin `corrected/` con los que emparejar")
        return

    p = f"source/{iso}/standardize/{I}_interventions.csv"
    campos, filas, d = _lee(p)
    empar = cambia = fecha_mal = 0
    porjor = defaultdict(list)
    for i, x in enumerate(filas):
        porjor[(x["legislature"], x["date"], x["session_number"].strip())].append(i)

    nuevos = {}
    for i, x in enumerate(filas):
        if x["intervention_order"] != "0":
            continue
        k = _N(x["text"])[INI:INI + LARGO]
        v = uni.get(k)
        if not v:
            continue
        sn, fe = v
        if fe and fe != x["date"]:      # guardarraíl externo: la fecha debe cuadrar
            fecha_mal += 1
            continue
        empar += 1
        if sn and sn != x["session_number"].strip():
            cambia += 1
            nuevos[i] = sn

    print(f"  {I} · firmas unívocas {len(uni):,} · Prolegomena emparejados {empar:,}")
    print(f"     descartados porque la fecha no cuadra: {fecha_mal:,}")
    print(f"     con `session_number` distinto del de meta: {cambia:,}")
    if a.medir:
        for i, sn in list(nuevos.items())[:5]:
            print(f"       [{filas[i]['date']}] {filas[i]['session_number']!r} → {sn!r}")
        return
    for i, sn in nuevos.items():
        filas[i]["session_number"] = sn

    bak = p.replace(".csv", ".pre_meta.csv")
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
