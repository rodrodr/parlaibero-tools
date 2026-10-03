#!/usr/bin/env python3
"""Escribe `sex` y `sex_source` en el `deputies.csv` de cada país, para revisión humana.

El dato derivado se lleva al padrón de trabajo —no solo al fichero auxiliar— para que
se pueda **corregir a mano**. Una fila corregida debe marcarse así:

    sex = M|F        sex_source = manual

`derivar_sexo.py` trata `manual` como el nivel de máxima autoridad y **no lo recalcula**
en sucesivas ejecuciones, de modo que la revisión no se pierde.

Genera además `{ISO2}_sex_revision.csv`, la lista ordenada por **riesgo × peso**: primero
los niveles menos fiables (`given_name_morph`, luego `given_name_rare`), y dentro de cada
uno los parlamentarios con más intervenciones. Revisar por ese orden concentra el esfuerzo
donde un error afecta a más texto; el nivel `morph` es además donde se acumulan las
mujeres (ver la nota de sesgo en derivar_sexo.py), así que es el que más importa mirar.

Uso:  python3 sexo_a_padron.py [--apply]
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pandas as pd

PAISES = ["ar", "br", "cl", "co", "cr", "do", "ec", "es", "gt", "mx", "pa", "pe", "pt", "py", "sv", "uy"]
RIESGO = {"given_name_morph": 0, "given_name_rare": 1, "given_name": 2,
          "honorific": 3, "roster": 4, "manual": 5}


def ruta_padron(iso2: str) -> Path | None:
    for n in ("deputies.csv", "diputados_bd.csv"):
        p = Path(f"source/{iso2}/deputies/{n}")
        if p.exists():
            return p
    return None


def main(apply: bool) -> None:
    print(f"{'':4} {'filas':>7} {'con sexo':>9} {'cob%':>6} {'a revisar':>10}  padrón")
    print("-" * 70)
    for c in PAISES:
        p = ruta_padron(c)
        sx = Path(f"source/{c}/deputies/{c.upper()}_sex.csv")
        if p is None or not sx.exists():
            print(f"{c.upper():4} falta padrón o {c.upper()}_sex.csv")
            continue

        head = p.open(encoding="utf-8", errors="replace").readline()
        sep = ";" if head.count(";") > head.count(",") else ","
        r = pd.read_csv(p, sep=sep, dtype=str, keep_default_na=False)
        low = {x.lower(): x for x in r.columns}
        cid = low.get("id_dep") or low.get("diputado_id")

        s = pd.read_csv(sx, dtype=str, keep_default_na=False).drop_duplicates("id_dep") \
              .set_index("id_dep")
        manual = r[low["sex_source"]].eq("manual") if "sex_source" in low else \
            pd.Series(False, index=r.index)
        nuevo_s = r[cid].map(s["sex"]).fillna("")
        nuevo_f = r[cid].map(s["sex_source"]).fillna("")
        if manual.any():                     # la corrección humana manda
            nuevo_s = nuevo_s.mask(manual, r[low["sex"]])
            nuevo_f = nuevo_f.mask(manual, "manual")
        r["sex"], r["sex_source"] = nuevo_s, nuevo_f

        # peso: intervenciones por parlamentario, para priorizar la revisión
        d = pd.read_csv(f"source/{c}/standardize/{c.upper()}_interventions.csv", dtype=str,
                        keep_default_na=False, usecols=["id_dep"])
        peso = d[d.id_dep.str.strip() != ""].id_dep.value_counts()

        cn = next((low[k] for k in ("nombre_completo", "speaker_name", "nombre_original", "alias")
                   if k in low), cid)
        rev = r.drop_duplicates(cid)[[cid, cn, "sex", "sex_source"]].copy()
        rev.columns = ["id_dep", "name", "sex", "sex_source"]
        rev["n_interventions"] = rev.id_dep.map(peso).fillna(0).astype(int)
        rev["_r"] = rev.sex_source.map(RIESGO).fillna(-1)
        rev = rev[rev.sex_source.isin(("given_name_morph", "given_name_rare"))] \
                 .sort_values(["_r", "n_interventions"], ascending=[True, False]) \
                 .drop(columns="_r")

        cob = 100 * (r.drop_duplicates(cid).sex != "").mean()
        print(f"{c.upper():4} {len(r):7,} {int((r.sex != '').sum()):9,} {cob:5.1f}% "
              f"{len(rev):10,}  {p.name}")

        if apply:
            bak = p.with_name(p.stem + ".pre_sex.csv")
            if not bak.exists():
                shutil.copy2(p, bak)
            r.to_csv(p, sep=sep, index=False, encoding="utf-8")
            rev.to_csv(p.with_name(f"{c.upper()}_sex_revision.csv"), index=False,
                       encoding="utf-8")

    if not apply:
        print("\n--- SIMULACIÓN --- (usa --apply para escribir en los deputies.csv)")


if __name__ == "__main__":
    import argparse
    _ap = argparse.ArgumentParser()
    _ap.add_argument("--apply", action="store_true")
    _ap.add_argument("--country", help="ISO2: limita la cascada a UN país; sin él, todos")
    _a = _ap.parse_args()
    if _a.country:
        _c = _a.country.lower()
        if _c not in PAISES:
            sys.exit(f"país desconocido: {_c!r} (válidos: {', '.join(PAISES)})")
        PAISES[:] = [_c]
    main(_a.apply)
