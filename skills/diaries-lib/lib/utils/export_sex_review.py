#!/usr/bin/env python3
"""Exporta `deputies_{ISO2}_review_sex.numbers` para la revisión humana del sexo.

Lleva el `deputies.csv` **entero** —no solo las filas de riesgo— a formato Numbers, con
`sex` y `sex_source` al final. La revisión sobre el padrón completo es lo que pidió el
usuario tras encontrar en AR atribuciones equivocadas: los niveles derivados aciertan
alrededor del 97%, y ese 3% no está confinado a los niveles frágiles.

Se añade `n_interventions` (intervenciones de esa persona en el corpus) para poder
ordenar en Numbers y empezar por lo que más texto afecta.

**Para corregir:** cambiar `sex` a `M` o `F` y poner `sex_source` en `manual`. Solo esas
filas se reimportan, con `importar_revision_sexo.py`; el resto de la hoja se ignora a
propósito, porque una pasada posterior del derivador puede haber mejorado esos valores.

No se exportan los países cuyo sexo procede **enteramente de un registro oficial** (BR,
CL, PE): ahí no hay nada que revisar. Sí los parcialmente cubiertos.

Uso:  python3 exportar_revision_sexo.py [--apply] [--country XX]
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

PAISES = ["ar", "br", "cl", "co", "cr", "do", "es", "gt", "mx", "pa", "pe", "pt", "py", "sv", "uy"]
DERIVADO = {"given_name", "given_name_rare", "given_name_morph", "honorific"}


def ruta_padron(iso2: str) -> Path | None:
    for n in ("deputies.csv", "diputados_bd.csv"):
        p = Path(f"source/{iso2}/deputies/{n}")
        if p.exists():
            return p
    return None


def leer(p: Path) -> pd.DataFrame:
    head = p.open(encoding="utf-8", errors="replace").readline()
    return pd.read_csv(p, sep=";" if head.count(";") > head.count(",") else ",",
                       dtype=str, keep_default_na=False)


def preparar(iso2: str) -> tuple[pd.DataFrame, int] | None:
    p = ruta_padron(iso2)
    if p is None or "sex" not in leer(p).columns:
        return None
    r = leer(p)
    n_der = int(r.sex_source.isin(DERIVADO).sum())
    if n_der == 0:
        return None                       # todo de registro oficial: nada que revisar

    low = {c.lower(): c for c in r.columns}
    cid = low.get("id_dep") or low.get("diputado_id")
    d = pd.read_csv(f"source/{iso2}/standardize/{iso2.upper()}_interventions.csv", dtype=str,
                    keep_default_na=False, usecols=["id_dep"])
    peso = d[d.id_dep.str.strip() != ""].id_dep.value_counts()
    r["n_interventions"] = r[cid].map(peso).fillna(0).astype(int).astype(str)

    # sex/sex_source al final, que es donde se escribe
    cols = [c for c in r.columns if c not in ("sex", "sex_source")] + ["sex", "sex_source"]
    return r[cols], n_der


def escribir(iso2: str) -> str:
    from numbers_parser import Document
    pre = preparar(iso2)
    if pre is None:
        return f"{iso2.upper():4} —"
    r, n_der = pre
    dst = Path(f"source/{iso2}/deputies/deputies_{iso2.upper()}_review_sex.numbers")
    if dst.exists():                      # nunca pisar una revisión en curso sin copia
        import shutil
        bak = dst.with_suffix(".prev.numbers")
        if not bak.exists():
            shutil.move(dst, bak)
        else:
            dst.unlink()

    doc = Document()
    t = doc.sheets[0].tables[0]
    t.name = "deputies"
    for j, c in enumerate(r.columns):
        t.write(0, j, str(c))
    for i, fila in enumerate(r.itertuples(index=False), start=1):
        for j, v in enumerate(fila):
            t.write(i, j, "" if v is None else str(v))
    doc.save(dst)
    return f"{iso2.upper():4} {len(r):7,} filas · {n_der:6,} derivadas → {dst.name}"


def main() -> None:
    apply = "--apply" in sys.argv
    paises = PAISES
    if "--country" in sys.argv:
        paises = [sys.argv[sys.argv.index("--country") + 1].lower()]

    if not apply:
        print(f"{'':4} {'filas':>7} {'derivadas':>10}  se exportaría")
        print("-" * 56)
        for c in paises:
            pre = preparar(c)
            if pre is None:
                print(f"{c.upper():4} {'—':>7} {'—':>10}  no (todo de registro oficial)")
                continue
            r, n = pre
            print(f"{c.upper():4} {len(r):7,} {n:10,}  deputies_{c.upper()}_review_sex.numbers")
        print("\n--- SIMULACIÓN --- (usa --apply para escribir)")
        return

    with ProcessPoolExecutor(max_workers=6) as ex:
        for f in as_completed([ex.submit(escribir, c) for c in paises]):
            print(f.result())


if __name__ == "__main__":
    main()
