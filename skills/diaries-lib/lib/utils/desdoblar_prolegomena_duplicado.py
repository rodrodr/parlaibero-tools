#!/usr/bin/env python3
"""Una sesión, un Prolegomena: desdobla los duplicados con sufijo y elimina las copias exactas.

Instrucción del investigador (2026-08-10): *«Si el Prolegomena está duplicado (con contenidos
distintos) hay que asignar un número o letra a la misma para evitar dicha duplicidad.»*

Tras reasignar los que declaran su número —CR 506→310, DO 140→1
([[feedback_sesiones_mismo_dia]])— quedaban **1.457 sesiones con más de una carátula** cuyo texto
NO declara a qué sesión pertenece. Sin evidencia interna no se puede adivinar, pero sí se puede
dejar de fingir que son la misma sesión.

Dos casos y dos tratamientos:

- **Texto IDÉNTICO** → es una copia y sobra. Se elimina; no se pierde nada.
- **Texto DISTINTO** → son actas distintas. La primera conserva el número y las demás reciben
  **sufijo alfabético** —`104`, `104B`, `104C`…—, que el esquema canónico ya admite:
  `session_number` es «entero puro o alfanumérico (12, 12A, 001O)».

⚠ **Lo que esto NO hace**: repartir las intervenciones entre las sesiones desdobladas. No hay de
dónde deducir a cuál pertenece cada turno, así que **todas se quedan con el número base**. La
sesión con sufijo queda con su carátula y sin turnos, y eso es información honesta: dice «de esta
acta tenemos la portada, y sus intervenciones están mezcladas con las de la sesión base».

CLI:
    python desdoblar_prolegomena_duplicado.py --country br [--medir]
"""
import argparse
import csv
import os
import sys
from collections import defaultdict

csv.field_size_limit(sys.maxsize)
SUF = "BCDEFGHIJKLMNOPQRSTUVWXYZ"


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

    por = defaultdict(list)
    for i, x in enumerate(filas):
        if x["intervention_order"] == "0":
            por[(x["legislature"], x["date"], x["session_number"].strip())].append(i)

    quitar, renombra = set(), {}
    dup = ident = desdobla = 0
    for k, idx in por.items():
        if len(idx) < 2:
            continue
        dup += 1
        vistos = {}
        letra = 0
        for j, i in enumerate(idx):
            t = filas[i]["text"].strip()
            if t in vistos:                      # copia exacta: sobra
                quitar.add(i)
                ident += 1
                continue
            vistos[t] = i
            if len(vistos) == 1:                 # la primera conserva el número
                continue
            if letra >= len(SUF):
                continue
            renombra[i] = k[2] + SUF[letra]
            letra += 1
            desdobla += 1

    print(f"  {I} · sesiones con más de una carátula: {dup:,}")
    print(f"     copias EXACTAS eliminadas: {ident:,}")
    print(f"     carátulas desdobladas con sufijo: {desdobla:,}")
    if a.medir:
        for i, s in list(renombra.items())[:4]:
            print(f"       [{filas[i]['date']}] {filas[i]['session_number']!r} → {s!r}")
        return

    for i, s in renombra.items():
        filas[i]["session_number"] = s
    salida = [x for i, x in enumerate(filas) if i not in quitar]

    bak = p.replace(".csv", ".pre_desdoble.csv")
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
    print(f"  ✓ corpus {len(filas):,} → {len(salida):,} filas")


if __name__ == "__main__":
    main()
