#!/usr/bin/env python3
"""Repara una forma de CARGO que quedó vinculada en bloque a una persona equivocada.

Caso que lo motiva (UY, 2026-08-10): la forma `A PRESIDENTA` —«LA PRESIDENTA» con la ele comida
por el OCR— quedó fuera de la propagación de presidencia y sus **16.812 filas de 1991 a 2025**
acabaron atribuidas a `UY00310 Carlos A. Lopez`, un HOMBRE cuyo mandato en el padrón es solo
2001. Un rol femenino, una sola persona, 34 años, y **ningún recuento lo delataba**: la vio el
juez de género del vocativo, que es un control independiente. Ver [[feedback_match_punto_critico]].

Cómo se distingue de lo normal: las formas de cargo bien propagadas llevan MUCHOS `id_dep`
—`PRESIDENTE` tiene 148 en UY, 167 en MX, 64 en PA—. La firma del fallo es **una forma de cargo
con un solo `id_dep` al 100 %**.

Regla de reparación, en cascada y solo con evidencia del propio corpus:

  1. presidencia del MISMO sexo que el cargo resuelta en esa jornada, si hay una sola  → se adopta
  2. lo mismo dentro de la legislatura, si hay una sola                                 → se adopta
  3. en otro caso → se VACÍA el id_dep y sus derivados

El paso 3 baja la vinculación, y debe hacerlo: eran vínculos falsos que además corrompían `sex`.
Vale más un hueco declarado que una atribución inventada.

CLI:
    python fix_rol_mal_vinculado.py --country uy --forma "A PRESIDENTA" --sexo F [--medir]
"""
import argparse
import csv
import os
import re
import sys
from collections import Counter, defaultdict

csv.field_size_limit(sys.maxsize)
DERIVADAS = ("speaker_name", "sex", "party", "district")


def _lee(p):
    with open(p, encoding="utf-8") as fh:
        d = csv.Sniffer().sniff(fh.readline(), ";,").delimiter
        fh.seek(0)
        r = csv.DictReader(fh, delimiter=d)
        return list(r.fieldnames), list(r), d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", required=True)
    ap.add_argument("--forma", help="speaker_raw exacto de la forma de cargo")
    ap.add_argument("--patron", help="regex de formas de cargo (alternativa a --forma)")
    ap.add_argument("--no-vaciar", action="store_true",
                    help="no borrar el id_dep indeterminable; solo listarlo para revisión")
    ap.add_argument("--sexo", required=True, choices=["F", "M"], help="sexo que impone el cargo")
    ap.add_argument("--medir", action="store_true")
    a = ap.parse_args()
    iso, I = a.country.lower(), a.country.upper()
    csvp = f"source/{iso}/standardize/{I}_interventions.csv"
    campos, filas, d = _lee(csvp)
    _, dep, _ = _lee(f"source/{iso}/standardize/{I}_deputies.csv")
    sx = {x["id_dep"]: x.get("sex", "") for x in dep}
    atr = {}
    for x in dep:
        atr.setdefault(x["id_dep"], {}).setdefault(
            x.get("legislature", ""),
            tuple(x.get(c, "") for c in ("speaker_name", "sex", "party", "district")))

    if a.patron:
        rx = re.compile(a.patron, re.I)
        obj = a.patron
        # solo las que CONTRADICEN el sexo del cargo: el resto ya está bien
        esta = [x for x in filas if x["id_dep"] and rx.fullmatch(x["speaker_raw"].strip())
                and sx.get(x["id_dep"], "") and sx[x["id_dep"]] != a.sexo]
    else:
        obj = a.forma.strip()
        esta = [x for x in filas if x["speaker_raw"].strip() == obj]
    if not esta:
        print(f"  {I} · la forma {obj!r} no aparece")
        return
    # presidencias del sexo del cargo resueltas en otras filas, por jornada y por legislatura
    ses, leg = defaultdict(Counter), defaultdict(Counter)
    for x in filas:
        if x["speaker_raw"].strip() == obj or not x["id_dep"]:
            continue
        if "RESIDENT" not in x["speaker_raw"].upper():
            continue
        if sx.get(x["id_dep"], "") != a.sexo:
            continue
        ses[x["date"]][x["id_dep"]] += 1
        leg[x.get("legislature", "")][x["id_dep"]] += 1

    v1 = v2 = vac = 0
    for x in esta:
        c = ses.get(x["date"])
        i = None
        if c and len(c) == 1:
            i, v1 = next(iter(c)), v1 + 1
        else:
            c2 = leg.get(x.get("legislature", ""))
            if c2 and len(c2) == 1:
                i, v2 = next(iter(c2)), v2 + 1
        if i:
            val = atr.get(i, {})
            t = val.get(x.get("legislature", "")) or (next(iter(val.values())) if val else ("",) * 4)
            x["id_dep"] = i
            for c3, y in zip(DERIVADAS, t):
                if c3 in x:
                    x[c3] = y
        elif a.no_vaciar:
            vac += 1                      # se deja como está, solo se cuenta para revisión
        else:
            vac += 1
            x["id_dep"] = ""
            for c3 in DERIVADAS:
                if c3 in x:
                    x[c3] = ""
    print(f"  {I} · {obj!r}: {len(esta):,} filas")
    print(f"   resueltas por la jornada: {v1:,} · por la legislatura: {v2:,}"
          f" · {'sin resolver (intactas)' if a.no_vaciar else 'VACIADAS'}: {vac:,}")
    if a.medir:
        return
    bak = csvp.replace(".csv", ".pre_rol.csv")
    tmp = csvp + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, delimiter=d)
        w.writeheader()
        w.writerows(filas)
    if not os.path.exists(bak):
        os.rename(csvp, bak)
    else:
        os.remove(csvp)
    os.rename(tmp, csvp)
    print("  ✓ corpus reescrito")


if __name__ == "__main__":
    main()
