#!/usr/bin/env python3
"""Vía PDF/DOC de Chile: texto corregido -> matriz de intervenciones, una fila por TURNO.

**Por qué no se usa `tag_text.py`.** Ese etiquetador recorre el texto LÍNEA A LÍNEA y ancla los
patrones al inicio de línea. En Chile eso no vale, y se puede medir: de los 168.070 marcadores
reales de las vías PDF/DOC, **49.773 (29,6%) están a mitad de línea** —típicamente detrás de la
frase con la que la mesa cede la palabra— y un etiquetador por líneas no los ve. Además el
patrón que había en `cl.yaml` cubría `señor|señora` pero **no `señorita`**, que son otros 11.835
(7,0%) y se lleva por delante justo a quien preside en 2024. Entre las dos cosas, el patrón de
la config habría capturado el **60,8%** de los turnos reales.

Aquí se aplica la MISMA lógica que en el track XML: partir por marcadores inline y atribuir cada
segmento a su orador. Se importa `MARKER` y las funciones de resolución de `parse_cl_xml` en vez
de reescribirlas, porque ese regex ya está probado contra 424.382 turnos y cubre las formas
difíciles: apellidos con guion (VIERA-GALLO), compuestos de hasta tres tokens (MUÑOZ BARRA),
`(Presidente)` intercalado y el terminador `.-` con sus variantes.

Uso:
    python3 parse_cl_text.py --all --workers 8 --out source/cl/matrix/interventions_text.csv
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_cl_xml import (  # noqa: E402  — maquinaria ya probada, no se duplica
    MARKER, CANON_COLS, load_dep_index, load_deputies, marker_role,
    party_at, period_for_date, resolve_by_date,
)

MARCA_PAGINA = re.compile(r"^---PAGE \d+---$", re.M)
ROL_MESA = re.compile(r"presiden|vicepresiden", re.I)


def limpia(t: str) -> str:
    t = MARCA_PAGINA.sub("", t)
    return re.sub(r"[ \t]+", " ", t)


def una_sesion(path: str) -> list:
    sid = os.path.basename(path)[:-4]
    mp = f"source/cl/meta/{sid}.json"
    meta = json.load(open(mp, encoding="utf-8")) if os.path.exists(mp) else {}
    date = meta.get("date", "")
    fila_base = [period_for_date(date) or meta.get("legislature", ""),
                 meta.get("session_number", ""), date, meta.get("session_type", "")]

    t = limpia(open(path, encoding="utf-8", errors="replace").read())
    marcas = list(MARKER.finditer(t))
    if not marcas:
        return []

    idx = load_dep_index()
    deps = load_deputies()
    filas = []
    # El encabezado y el índice —todo lo anterior al primer marcador— se descartan: son la
    # portada, el sumario y la lista de asistencia, no discurso de nadie.
    for i, mk in enumerate(marcas):
        fin = marcas[i + 1].start() if i + 1 < len(marcas) else len(t)
        seg = t[mk.end():fin].strip()
        if not seg:
            continue
        rol = marker_role(mk)
        idd = resolve_by_date(idx, mk.group("sur"), date, rol, mk.group("dname") or "")
        sraw = re.sub(r"\s+", " ", mk.group(0)).strip().rstrip(".-").strip()
        dep = deps.get(idd)
        filas.append(fila_base + [sraw, idd, dep["name"] if dep else "",
                                  party_at(dep, date) if dep else "", "",
                                  seg, "mesa" if rol and ROL_MESA.search(rol) else "discurso"])
    return filas


def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument("--all", action="store_true")
    a.add_argument("--sample", type=int, default=0)
    a.add_argument("--workers", type=int, default=8)
    a.add_argument("--out", required=True)
    o = a.parse_args()

    fs = sorted(glob.glob("source/cl/corrected/*.txt"))
    if o.sample:
        fs = fs[:o.sample]
    n = 0
    with open(o.out, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(CANON_COLS)
        with ProcessPoolExecutor(max_workers=o.workers) as ex:
            for k, fut in enumerate(as_completed([ex.submit(una_sesion, f) for f in fs]), 1):
                filas = fut.result()
                w.writerows(filas)
                n += len(filas)
                if k % 200 == 0:
                    print(f"  {k}/{len(fs)} archivos, {n:,} turnos", flush=True)
    print(f"OK: {len(fs)} archivos -> {n:,} turnos -> {o.out}")


if __name__ == "__main__":
    main()
