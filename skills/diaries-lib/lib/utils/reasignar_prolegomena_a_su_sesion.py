#!/usr/bin/env python3
"""Devuelve cada Prolegomena a la sesión que él mismo declara ser.

Señalado por el investigador (2026-08-10): *«Se repite varias veces el Prolegomena de la sesión
104 de 1994-04-30»*. No son copias — son las carátulas de **sesiones distintas** metidas bajo la
misma fecha y el mismo número:

    registrado 1994-04-30 nº 104  →  «ACTA DE LA SESION Nº 108 … DEL 24 DE FEBRERO»
                                  →  «Nº 110» · «Nº 116» · «Nº 120» · «Nº 122» · «Nº 124» …

**El origen es cómo se insertaron.** `recover_frontmatter` colocaba cada carátula delante de la
PRIMERA intervención de la fecha, así que todas las de un día caían juntas y heredaban el número
de la primera. Las intervenciones, en cambio, sí conservan su `session_number` correcto.

La reparación no necesita heurística: **la cabecera del acta declara su propio número**, y basta
leerlo. Lo que no se toca es la FECHA: en CR, 4.983 Prolegomena la declaran y solo 123 discrepan,
así que el problema está en el número, no en el día.

CLI:
    python reasignar_prolegomena_a_su_sesion.py --country cr [--medir]
"""
import argparse
import csv
import os
import re
import sys
from collections import Counter, defaultdict

csv.field_size_limit(sys.maxsize)

# El símbolo de ordinal lo degrada el OCR: «Nº», «N.º», «No.», «N∫». Se admite cualquiera.
NUM = re.compile(r"(?i)ACTA\s+DE\s+LA\s+SESI[OÓ]N\s*(?:PLENARIA\s*)?(?:ORDINARIA\s*|"
                 r"EXTRAORDINARIA\s*)?N?[ºo°∫.\s]{0,4}(\d{1,4})")
# DO escribe el número EN LETRA y luego en cifra: «ACTA NÚMERO DOS (02) DE LA PRIMERA
# LEGISLATURA…». Vale cualquiera de las dos, y la cifra entre paréntesis es la más fiable.
NUM_DO = re.compile(r"(?i)ACTA\s+N[ÚU]MERO\s+[A-ZÁÉÍÓÚ\s]{3,30}?\((\d{1,4})\)")
_ORD = {"UNO":1,"DOS":2,"TRES":3,"CUATRO":4,"CINCO":5,"SEIS":6,"SIETE":7,"OCHO":8,"NUEVE":9,
        "DIEZ":10,"ONCE":11,"DOCE":12,"TRECE":13,"CATORCE":14,"QUINCE":15}
NUM_LETRA = re.compile(r"(?i)ACTA\s+N[ÚU]MERO\s+([A-ZÁÉÍÓÚ]+)")


def _declarado(t: str):
    """El número de sesión que la carátula declara, en cifra o en letra."""
    for rx in (NUM, NUM_DO):
        m = rx.search(t)
        if m:
            return str(int(m.group(1)))
    m = NUM_LETRA.search(t)
    if m and m.group(1).upper() in _ORD:
        return str(_ORD[m.group(1).upper()])
    return None


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

    # números de sesión que EXISTEN en esa fecha según las intervenciones
    reales = defaultdict(set)
    for x in filas:
        if x["intervention_order"] != "0":
            reales[(x["legislature"], x["date"])].add(x["session_number"].strip())

    antes = Counter()
    for x in filas:
        if x["intervention_order"] == "0":
            antes[(x["legislature"], x["date"], x["session_number"].strip())] += 1
    dup_antes = sum(1 for v in antes.values() if v > 1)

    cambia = huerfano = 0
    for x in filas:
        if x["intervention_order"] != "0":
            continue
        dec = _declarado(x["text"][:700])
        if not dec:
            continue
        if dec == x["session_number"].strip():
            continue
        # ⚠ Solo se reasigna si ese número EXISTE ese día entre las intervenciones. Si no, el
        # Prolegomena quedaría suelto en una sesión sin turnos, que es peor que dejarlo donde está.
        if dec not in reales.get((x["legislature"], x["date"]), set()):
            huerfano += 1
            continue
        cambia += 1
        if not a.medir:
            x["session_number"] = dec

    despues = Counter()
    for x in filas:
        if x["intervention_order"] == "0":
            despues[(x["legislature"], x["date"], x["session_number"].strip())] += 1
    dup_despues = sum(1 for v in despues.values() if v > 1)

    print(f"  {I} · Prolegomena reasignados a su sesión declarada: {cambia:,}")
    print(f"     descartados por no existir esa sesión ese día: {huerfano:,}")
    print(f"     sesiones con más de un Prolegomena: {dup_antes:,} → {dup_despues:,}")
    if a.medir:
        return
    bak = p.replace(".csv", ".pre_reasig.csv")
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
