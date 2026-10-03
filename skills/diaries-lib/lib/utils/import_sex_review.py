#!/usr/bin/env python3
"""Importa al padrón las correcciones humanas de `sex` hechas fuera del proyecto.

La revisión se hace cómodamente en una hoja de cálculo —Numbers o CSV— sobre una copia
del padrón. Este script devuelve al `deputies.csv` **solo las filas marcadas
`sex_source = manual`**, que es la marca que `derivar_sexo.py` respeta y no recalcula.

Lo demás de la hoja se ignora a propósito: el resto de sus valores son de la ejecución
del derivador en el momento en que se exportó, y una pasada posterior puede haberlos
mejorado. Reimportarlos en bloque **haría retroceder** el padrón. Se comprueba y se avisa.

Lee `.numbers` (vía numbers-parser) y `.csv`. Necesita las columnas `id_dep`, `sex` y
`sex_source`.

Uso:  python3 importar_revision_sexo.py --country ar --file ruta/a/revision.numbers [--apply]
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pandas as pd


def leer(p: Path) -> pd.DataFrame:
    if p.suffix.lower() == ".numbers":
        from numbers_parser import Document
        filas = Document(p).sheets[0].tables[0].rows(values_only=True)
        return pd.DataFrame(filas[1:], columns=[str(c) for c in filas[0]]).astype(str)
    head = p.open(encoding="utf-8", errors="replace").readline()
    return pd.read_csv(p, sep=";" if head.count(";") > head.count(",") else ",",
                       dtype=str, keep_default_na=False)


def ruta_padron(iso2: str) -> Path:
    for n in ("deputies.csv", "diputados_bd.csv"):
        p = Path(f"source/{iso2}/deputies/{n}")
        if p.exists():
            return p
    raise SystemExit(f"sin padrón para {iso2}")


def main() -> None:
    args = sys.argv
    apply = "--apply" in args
    iso2 = args[args.index("--country") + 1].lower()
    origen = Path(args[args.index("--file") + 1])

    rev = leer(origen)
    # ES nombra su clave `diputado_id`; los padrones son independientes por diseño
    if "id_dep" not in rev.columns and "diputado_id" in rev.columns:
        rev = rev.rename(columns={"diputado_id": "id_dep"})
    falta = {"id_dep", "sex", "sex_source"} - set(rev.columns)
    if falta:
        raise SystemExit(f"a la hoja le faltan columnas: {sorted(falta)}")

    man = rev[rev.sex_source.str.strip().str.lower() == "manual"]
    man = man[man.sex.str.strip().str.upper().isin(["M", "F"])].drop_duplicates("id_dep")
    print(f"{origen.name}: {len(rev):,} filas · {len(man):,} marcadas `manual`")

    p = ruta_padron(iso2)
    head = p.open(encoding="utf-8", errors="replace").readline()
    sep = ";" if head.count(";") > head.count(",") else ","
    r = pd.read_csv(p, sep=sep, dtype=str, keep_default_na=False)
    low = {c.lower(): c for c in r.columns}
    cid = low.get("id_dep") or low.get("diputado_id")

    mapa = dict(zip(man.id_dep.str.strip(), man.sex.str.strip().str.upper()))
    obj = r[cid].isin(mapa)
    cambia = obj & (r[cid].map(mapa) != r["sex"])
    print(f"  encontradas en el padrón: {int(obj.sum()):,} filas "
          f"· cambian el valor actual: {int(cambia.sum()):,}")

    # aviso: el resto de la hoja puede estar desfasado respecto al padrón actual
    otras = rev[rev.sex_source.str.strip().str.lower() != "manual"]
    if len(otras):
        o = otras[otras.sex.isin(["M", "F"])].drop_duplicates("id_dep")
        act = r.drop_duplicates(cid).set_index(cid)["sex"]
        dif = sum(1 for i, s in zip(o.id_dep, o.sex)
                  if i in act.index and act[i] in ("M", "F") and act[i] != s)
        print(f"  (las {len(o):,} filas NO manuales de la hoja difieren en {dif:,} del padrón "
              f"actual; se ignoran a propósito)")

    if not apply:
        if int(cambia.sum()):
            ver = r[cambia].drop_duplicates(cid)
            cn = next((low[k] for k in ("nombre_completo", "speaker_name", "alias") if k in low), cid)
            ver = ver.assign(nuevo=ver[cid].map(mapa))[[cid, cn, "sex", "sex_source", "nuevo"]]
            print("\n" + ver.head(20).to_string(index=False))
        print("\n--- SIMULACIÓN --- (usa --apply para escribir)")
        return

    bak = p.with_name(p.stem + ".pre_manual.csv")
    if not bak.exists():
        shutil.copy2(p, bak)
    r.loc[obj, "sex"] = r.loc[obj, cid].map(mapa)
    r.loc[obj, "sex_source"] = "manual"
    r.to_csv(p, sep=sep, index=False, encoding="utf-8")
    print(f"✓ {p.name}: {int(obj.sum()):,} filas marcadas `manual` (copia en {bak.name})")


if __name__ == "__main__":
    main()
