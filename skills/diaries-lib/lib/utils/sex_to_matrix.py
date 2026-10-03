#!/usr/bin/env python3
"""Añade la columna `sex` a la matriz canónica de intervenciones de los 15 países.

El dato ya vive en el padrón, así que en la matriz es **redundante a propósito**: evita
tener que hacer un *merge* con el padrón solo para filtrar por sexo, que es de las
operaciones más frecuentes en el uso de este corpus.

Posición: **detrás de `speaker_name`**, junto al resto de atributos de la persona
(`id_dep`, `speaker_name`, `sex`, `party`, `district`). El esquema canónico pasa de
once a doce columnas y hay que actualizar el diccionario de datos de los quince países.

`sex` sale de `{ISO2}_sex.csv` (ver derivar_sexo.py) por `id_dep`. Las filas sin
`id_dep` —cargos de mesa sin nombrar, oradores no vinculados— quedan **vacías**, nunca
imputadas: no hay persona identificada a la que atribuir el dato.

La procedencia (`sex_source`) **no se replica** en la matriz: son 8,2 GB y el dato es
constante por `id_dep`; quien lo necesite lo tiene en el padrón, que se publica al lado.

Trabaja por trozos para no cargar 1,4 M de filas en memoria, y escribe a un temporal
que solo sustituye al original si el recuento de filas cuadra.

Uso:  python3 aplicar_sexo_matriz.py [--apply] [--country XX]
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pandas as pd

PAISES = ["ar", "br", "cl", "co", "cr", "do", "es", "gt", "mx", "pa", "pe", "pt", "py", "sv", "uy"]
TROZO = 200_000
ORDEN = ["legislature", "session_number", "date", "session_type", "intervention_order",
         "speaker_raw", "id_dep", "speaker_name", "sex", "party", "district", "text"]


def procesar(iso2: str, apply: bool) -> None:
    csv = Path(f"source/{iso2}/standardize/{iso2.upper()}_interventions.csv")
    sx = Path(f"source/{iso2}/deputies/{iso2.upper()}_sex.csv")
    if not sx.exists():
        print(f"{iso2.upper():4} sin {sx.name} — ejecuta antes derivar_sexo.py")
        return

    mapa = pd.read_csv(sx, dtype=str, keep_default_na=False).set_index("id_dep")["sex"].to_dict()
    cab = pd.read_csv(csv, dtype=str, keep_default_na=False, nrows=0)
    if "sex" in cab.columns:
        print(f"{iso2.upper():4} ya tiene `sex` — nada que hacer")
        return

    tmp = csv.with_suffix(".tmp")
    n = con = 0
    primero = True
    for tr in pd.read_csv(csv, dtype=str, keep_default_na=False, chunksize=TROZO):
        tr["sex"] = tr.id_dep.map(mapa).fillna("")
        n += len(tr)
        con += int((tr.sex != "").sum())
        if apply:
            cols = [c for c in ORDEN if c in tr.columns] + \
                   [c for c in tr.columns if c not in ORDEN]
            tr[cols].to_csv(tmp, mode="w" if primero else "a", header=primero,
                            index=False, encoding="utf-8")
        primero = False

    print(f"{iso2.upper():4} {n:10,} filas · con sexo {con:10,} ({100*con/max(n,1):5.1f}%)")

    if not apply:
        return
    chk = pd.read_csv(tmp, dtype=str, keep_default_na=False, usecols=["sex"])
    if len(chk) != n:
        tmp.unlink()
        raise SystemExit(f"{iso2.upper()}: recuento inconsistente {len(chk):,} != {n:,}")
    bak = csv.with_name(csv.stem + ".pre_sex.csv")
    if not bak.exists():
        shutil.copy2(csv, bak)
    tmp.replace(csv)


def main() -> None:
    apply = "--apply" in sys.argv
    paises = PAISES
    if "--country" in sys.argv:
        paises = [sys.argv[sys.argv.index("--country") + 1].lower()]
    for c in paises:
        procesar(c, apply)
    if not apply:
        print("\n--- SIMULACIÓN --- (usa --apply para reescribir los canónicos)")


if __name__ == "__main__":
    main()
