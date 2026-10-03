#!/usr/bin/env python3
"""Prepara la muestra de calibración de la tasa de fuga (validation_methodology §5).

Una **fuga** es una fila que el auto-filtro marcó **PASS** y que en realidad tenía un
problema: se escapó y nadie la va a mirar nunca. Esa es la asimetría que hace necesaria esta
comprobación — un FLAG de más cuesta una revisión inútil; un PASS de más es un error
silencioso.

Se toman **200 filas al azar entre las marcadas PASS**, repartidas por igual entre los quince
países para que **todas las convenciones de marcado queden ejercitadas** (el reparto
proporcional al tamaño del corpus habría dejado a los países pequeños sin apenas comprobar,
y son los que tienen las convenciones más raras).

Se incluye el **texto completo**, no truncado: un marcador ajeno puede estar en cualquier
punto, y recortar escondería justo lo que hay que buscar.

**Criterio:** 0 fugas en 200 → tasa de fuga < 1,5% (IC 95% Wilson). Es de **una sola vez**:
valida el mecanismo, no el corpus. Una vez comprobado, se confía en él para el resto,
Ecuador incluido.

⚠ No hacerla es el error que ya se pagó en AR: se declaró un 0,016% de marcadores incrustados
cuando el real era **0,47%** —treinta veces más— por dar el filtro por infalible en vez de
medirlo.

Uso:  python3 scripts/validacion/preparar_calibracion.py [--n 200]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

PAISES = ["ar", "br", "cl", "co", "cr", "do", "es", "gt", "mx", "pa", "pe", "pt", "py", "sv", "uy"]
SALIDA_BASE = "docs/validacion/calibracion_fuga"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=20260731)
    ap.add_argument("--ronda", type=int, default=1)
    a = ap.parse_args()

    por_pais = a.n // len(PAISES)
    resto = a.n - por_pais * len(PAISES)

    partes = []
    for i, c in enumerate(PAISES):
        m = pd.read_csv(f"docs/validacion/{c.upper()}_muestra.csv", dtype=str,
                        keep_default_na=False)
        p = m[m.veredicto == "PASS"]
        k = por_pais + (1 if i < resto else 0)
        s = p.sample(n=min(k, len(p)), random_state=a.seed).copy()
        s.insert(0, "pais", c.upper())
        partes.append(s)

    d = pd.concat(partes, ignore_index=True)
    d["n_caracteres"] = d.text.str.len()
    cols = ["pais", "date", "legislature", "session_number", "intervention_order",
            "speaker_raw", "id_dep", "speaker_name", "n_caracteres", "text"]
    d = d[[c for c in cols if c in d.columns]]
    # columnas que rellena el humano
    d["FUGA"] = ""          # «sí» si la fila tenía un problema que el filtro no vio
    d["MOTIVO"] = ""        # qué problema

    SALIDA = Path(SALIDA_BASE if a.ronda == 1 else f"{SALIDA_BASE}_ronda{a.ronda}")
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    d.to_csv(SALIDA.with_suffix(".csv"), index=False, encoding="utf-8")

    try:
        from numbers_parser import Document
        doc = Document()
        t = doc.sheets[0].tables[0]
        t.name = "calibracion"
        for j, c in enumerate(d.columns):
            t.write(0, j, str(c))
        for i, fila in enumerate(d.itertuples(index=False), start=1):
            for j, v in enumerate(fila):
                t.write(i, j, "" if v is None else str(v))
        doc.save(SALIDA.with_suffix(".numbers"))
        fmt = "Numbers + CSV"
    except Exception as e:                       # pragma: no cover
        fmt = f"solo CSV ({type(e).__name__})"

    print(f"{len(d)} filas PASS al azar · {por_pais}–{por_pais+1} por país · {fmt}")
    print(f"  → {SALIDA.with_suffix('.numbers')}")
    print(f"  → {SALIDA.with_suffix('.csv')}")
    print(f"\n  mediana {int(d.n_caracteres.median()):,} car. · "
          f"máximo {int(d.n_caracteres.max()):,} car.")
    print("\nQué mirar en cada fila:")
    print("  1. ¿hay dentro de `text` el marcador de OTRO orador? (un turno de palabra ajeno)")
    print("  2. ¿la atribución de `speaker_raw` → `speaker_name` es la correcta?")
    print("  3. ¿es realmente discurso, y no un sumario, índice o lista de votación?")
    print("Marcar FUGA = «sí» solo si algo de eso falla. Lo demás se deja en blanco.")


if __name__ == "__main__":
    main()
