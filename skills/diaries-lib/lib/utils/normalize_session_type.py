#!/usr/bin/env python3
"""Normaliza `session_type` a minúsculas en los 15 corpus.

El valor no tenía capitalización consistente entre países: AR, BR, CO, ES, MX,
PE y PT usaban mayúscula inicial (`Ordinaria`) y CL, CR, DO, GT, PA, PY, SV y UY
minúscula (`ordinaria`). Para el uso previsto del corpus —concatenar los 16 CSV—
eso rompe cualquier agrupación por tipo de sesión: `Ordinaria` y `ordinaria`
cuentan como categorías distintas.

Se elige **minúsculas** porque es la convención documentada en `CLAUDE.md`
(`ordinaria / extraordinaria / solemne / especial`) y la que ya usaban 8 de los 15.

⚠ No se unifica el CONJUNTO de valores, solo su grafía. Cada cámara tiene las
categorías que tiene, y eso es información, no ruido: AR distingue `asamblea` y
`preparatoria`, CL `congreso pleno` e `instalación`, MX `comisión permanente`,
PA `judicial`. Forzar un vocabulario común destruiría esa distinción.

Verificado antes de aplicar: ningún par de valores colisiona al bajar a
minúsculas — los 15 corpus conservan el mismo número de valores distintos.

Uso:  python3 normalizar_session_type.py [--apply]
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pandas as pd

PAISES = ["ar", "br", "cl", "co", "cr", "do", "es", "gt", "mx", "pa", "pe", "pt", "py", "sv", "uy"]


def main(apply: bool) -> None:
    total = 0
    for c in PAISES:
        p = Path(f"source/{c}/standardize/{c.upper()}_interventions.csv")
        bak = p.with_name(f"{c.upper()}_interventions.pre_sessiontype.csv")
        d = pd.read_csv(p, dtype=str, keep_default_na=False)
        antes = d.session_type.copy()
        nuevo = antes.str.strip().str.lower()
        n = int((nuevo != antes).sum())
        # guarda: la grafía no debe fusionar categorías
        assert antes.str.strip().str.lower().nunique() == antes.nunique(), f"{c}: colisión de valores"
        total += n
        print(f"  {c.upper()}  {len(d):>9,} filas · cambian {n:>9,} · valores {sorted(set(nuevo))[:6]}")
        if apply and n:
            if not bak.exists():
                shutil.copy2(p, bak)
            d["session_type"] = nuevo
            d.to_csv(p, index=False, encoding="utf-8")

    print(f"\ntotal de filas modificadas: {total:,}")
    if not apply:
        print("--- SIMULACIÓN (sin --apply no se escribe nada) ---")
        return

    print("\nverificación final:")
    vals = {}
    for c in PAISES:
        p = Path(f"source/{c}/standardize/{c.upper()}_interventions.csv")
        d = pd.read_csv(p, dtype=str, keep_default_na=False, usecols=["session_type"])
        v = sorted({x for x in d.session_type if x.strip()})
        assert all(x == x.lower() for x in v), f"{c}: quedan mayúsculas"
        vals[c.upper()] = v
    comunes = set.intersection(*(set(v) for v in vals.values()))
    print(f"  ✓ los 15 en minúsculas · categorías comunes a todos: {sorted(comunes)}")
    todas = sorted(set().union(*(set(v) for v in vals.values())))
    print(f"  vocabulario completo del corpus ({len(todas)}): {todas}")


if __name__ == "__main__":
    main("--apply" in sys.argv)
