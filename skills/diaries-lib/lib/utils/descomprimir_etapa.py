#!/usr/bin/env python3
"""Descomprime una etapa de texto que se archivó en `.txt.gz` para liberar disco.

**Por qué existe.** El 2026-08-03 el disco bajó a 2,5 GB libres y se comprimieron las etapas
intermedias (`extracted/`, `corrected/`, `tagged/`) de los 12 países cerrados: 74.642 archivos,
de 18 GB a 3,6 GB. Las utilidades del pipeline hacen `glob("*.txt")`, así que sobre una etapa
comprimida **devuelven cero archivos y parece que no hay datos** — un falso «no hay nada que
procesar» que es exactamente el tipo de error que este proyecto ya ha pagado caro.

Antes de re-ejecutar cualquier etapa sobre un país archivado, descomprímela:

    python3 descomprimir_etapa.py --country uy --etapa corrected
    python3 descomprimir_etapa.py --country uy --todas          # extracted+corrected+tagged

Y al terminar, si hace falta espacio, se vuelve a comprimir:

    python3 descomprimir_etapa.py --country uy --todas --comprimir

⚠ **NO están comprimidos**: `raw/` y `ocr/` (fuentes, no se tocan nunca), ni EC ni ES, que
estaban en curso. Comprobar siempre con `ls` antes de suponer el estado de una etapa.
"""
from __future__ import annotations

import argparse
import glob
import gzip
import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed

ETAPAS = ("extracted", "corrected", "tagged")


def _descomprimir(f: str) -> int:
    dst = f[:-3]
    with gzip.open(f, "rb") as a, open(dst, "wb") as b:
        shutil.copyfileobj(a, b, 1024 * 1024)
    n = os.path.getsize(dst)
    os.remove(f)
    return n


def _comprimir(f: str) -> int:
    with open(f, "rb") as a, gzip.open(f + ".gz", "wb", compresslevel=6) as b:
        shutil.copyfileobj(a, b, 1024 * 1024)
    n0, n1 = os.path.getsize(f), os.path.getsize(f + ".gz")
    if n1 < n0:
        os.remove(f)
        return n0 - n1
    os.remove(f + ".gz")
    return 0


def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument("--country", required=True)
    a.add_argument("--etapa", action="append", default=[])
    a.add_argument("--todas", action="store_true")
    a.add_argument("--comprimir", action="store_true", help="la operación inversa")
    o = a.parse_args()
    c = o.country.lower()
    etapas = ETAPAS if (o.todas or not o.etapa) else o.etapa

    for e in etapas:
        pat = f"source/{c}/{e}/**/*.txt" + ("" if o.comprimir else ".gz")
        fs = [f for f in glob.glob(pat, recursive=True) if os.path.isfile(f)]
        if not fs:
            print(f"  {c}/{e}: nada que hacer ({'sin .txt' if o.comprimir else 'sin .txt.gz'})")
            continue
        fn = _comprimir if o.comprimir else _descomprimir
        tot = 0
        with ThreadPoolExecutor(max_workers=8) as ex:
            for fut in as_completed([ex.submit(fn, f) for f in fs]):
                tot += fut.result()
        verbo = "comprimidos" if o.comprimir else "descomprimidos"
        print(f"  {c}/{e}: {len(fs):,} {verbo} · {tot/2**30:.2f} GB")


if __name__ == "__main__":
    main()
