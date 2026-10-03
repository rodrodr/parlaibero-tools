#!/usr/bin/env python3
"""Inventario completo de sesiones DOBLADAS (duplicación Clase B) por país.

Distingue una sesión ingerida dos veces de la repetición legítima de fórmulas de
trámite, que es lo que arruina el conteo ingenuo de «texto repetido dentro de la
sesión». El discriminador es la FORMA DE LA MULTIPLICIDAD:

  · sesión doblada      → MUCHOS textos distintos repetidos, casi todos ×2
  · fórmula de trámite  → POCOS textos distintos, repetidos ×muchos

Verificado: MX repite "consulte la secretaría a la asamblea, en votación
económica…" 115 veces en una misma sesión (una por punto del orden del día) y
PY "se gira a las comisiones de…" 157 veces. Ninguna de las dos es duplicación.

Criterio de sesión doblada:
    ≥ 20 textos distintos repetidos  Y  ≥ 70% de ellos con multiplicidad
    exactamente 2  Y  ≥ 25% de las filas de la sesión implicadas.

Salida: <outdir>/{iso2}_dobladas.json
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

MINLEN = 80
KEYLEN = 200
MIN_DISTINTOS = 20
MIN_RATIO_X2 = 0.70
MIN_PCT_SESION = 25.0


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9 ]", " ", re.sub(r"\s+", " ", s)).strip()


def audit(iso2: str, outdir: Path) -> dict:
    p = Path(f"source/{iso2}/standardize/{iso2.upper()}_interventions.csv")
    sep = ";" if p.open(encoding="utf-8", errors="replace").readline().count(";") > 1 else ","
    df = pd.read_csv(p, sep=sep, dtype=str, keep_default_na=False,
                     usecols=lambda c: c in ("date", "session_number", "text"))
    total = len(df)
    df["_k"] = df.date + "|" + (df["session_number"] if "session_number" in df else "")
    tam = df.groupby("_k").size().to_dict()

    largo = df[df.text.str.len() >= MINLEN].copy()
    largo["_t"] = [norm(t)[:KEYLEN] for t in largo.text]
    g = largo.groupby(["_k", "_t"]).size()
    rep = g[g > 1]

    dobladas, formulas = [], 0
    for k in {a for a, _ in rep.index}:
        sub = rep.loc[k]
        n_dist = len(sub)
        n_x2 = int((sub == 2).sum())
        extra = int((sub - 1).sum())
        n_ses = tam.get(k, 1)
        pct = 100 * extra / n_ses
        ratio = n_x2 / n_dist if n_dist else 0
        if n_dist >= MIN_DISTINTOS and ratio >= MIN_RATIO_X2 and pct >= MIN_PCT_SESION:
            dobladas.append({"sesion": k, "filas_sesion": n_ses, "filas_repetidas": extra,
                             "pct_sesion": round(pct, 1), "textos_distintos": n_dist,
                             "ratio_x2": round(ratio, 2), "mult_max": int(sub.max())})
        else:
            formulas += 1

    dobladas.sort(key=lambda d: -d["filas_repetidas"])
    res = {
        "iso2": iso2,
        "total_filas": total,
        "sesiones": len(tam),
        "sesiones_dobladas": len(dobladas),
        "filas_duplicadas": sum(d["filas_repetidas"] for d in dobladas),
        "pct_corpus": round(100 * sum(d["filas_repetidas"] for d in dobladas) / total, 3) if total else 0,
        "sesiones_con_repeticion_legitima": formulas,
        "detalle": dobladas[:60],
    }
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / f"{iso2}_dobladas.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return res


if __name__ == "__main__":
    r = audit(sys.argv[1], Path(sys.argv[2]))
    print(f"{r['iso2'].upper():4} sesiones dobladas: {r['sesiones_dobladas']:4} de {r['sesiones']:6,} · "
          f"filas duplicadas: {r['filas_duplicadas']:7,} ({r['pct_corpus']}%) · "
          f"(sesiones con fórmulas repetidas, ignoradas: {r['sesiones_con_repeticion_legitima']:,})")
