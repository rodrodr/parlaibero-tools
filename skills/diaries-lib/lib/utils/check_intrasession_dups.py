#!/usr/bin/env python3
"""Busca duplicación DENTRO de una sesión en cualquier corpus (Clase B).

Replanteamiento respecto al caso de CL: allí se detectó comparando los dos tracks
de ingesta vía la columna `source`, pero **la procedencia no hace falta**. Si una
sesión entró dos veces, sus intervenciones aparecen dos veces con el mismo texto
dentro del mismo `(date, session_number)`. Buscar texto idéntico repetido en la
misma sesión detecta la clase en los 15 corpus, registren o no el track.

Falsos positivos esperables y cómo se acotan:
  · asentimientos ("Gracias.", "Sí.") → se ignoran los textos < 80 caracteres
  · fórmulas de votación repetidas    → se reporta aparte el reparto por longitud

Salida: <outdir>/{iso2}_intradup.json
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

MINLEN = 80          # por debajo, la repetición es legítima (asentimientos, fórmulas)
KEYLEN = 200


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9 ]", " ", re.sub(r"\s+", " ", s)).strip()


def audit(iso2: str, outdir: Path) -> dict:
    csv = Path(f"source/{iso2}/standardize/{iso2.upper()}_interventions.csv")
    head = csv.open(encoding="utf-8", errors="replace").readline()
    sep = ";" if head.count(";") > head.count(",") else ","

    df = pd.read_csv(csv, sep=sep, dtype=str, keep_default_na=False,
                     usecols=lambda c: c in ("date", "session_number", "speaker_raw", "text"))
    total = len(df)
    df = df[df.text.str.len() >= MINLEN].copy()
    df["_k"] = df.date + "|" + df.get("session_number", "")
    df["_t"] = [norm(t)[:KEYLEN] for t in df.text]

    g = df.groupby(["_k", "_t"]).size()
    rep = g[g > 1]
    filas_extra = int((rep - 1).sum())
    sesiones = {k for k, _ in rep.index}

    # peso por sesión: una sesión doblada entera pesa mucho; una fórmula repetida, poco
    por_sesion = Counter()
    for (k, _), n in rep.items():
        por_sesion[k] += n - 1
    top = por_sesion.most_common(15)

    # ¿cuántas de las filas de esas sesiones están repetidas? (sesión doblada vs ruido)
    tam = df.groupby("_k").size().to_dict()
    sospechosas = [{"sesion": k, "filas_repetidas": n, "filas_sesion": tam.get(k, 0),
                    "pct": round(100 * n / tam.get(k, 1), 1)} for k, n in top]

    ejemplos = []
    for (k, t), n in rep.sort_values(ascending=False).head(5).items():
        ejemplos.append({"sesion": k, "veces": int(n), "texto": t[:140]})

    res = {
        "iso2": iso2,
        "total_filas": total,
        "filas_evaluadas": len(df),
        "umbral_longitud": MINLEN,
        "filas_duplicadas_intrasesion": filas_extra,
        "pct": round(100 * filas_extra / total, 3) if total else 0,
        "sesiones_afectadas": len(sesiones),
        "top_sesiones": sospechosas,
        "ejemplos": ejemplos,
    }
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / f"{iso2}_intradup.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    return res


if __name__ == "__main__":
    r = audit(sys.argv[1], Path(sys.argv[2]))
    peor = r["top_sesiones"][0]["pct"] if r["top_sesiones"] else 0
    print(f"[{r['iso2']}] {r['filas_duplicadas_intrasesion']:,} filas repetidas intra-sesión "
          f"({r['pct']}%) en {r['sesiones_afectadas']:,} sesiones · peor sesión {peor}% doblada")
