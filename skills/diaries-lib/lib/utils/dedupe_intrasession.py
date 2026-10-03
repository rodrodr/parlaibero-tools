#!/usr/bin/env python3
"""Deduplica la Clase B residual: filas repetidas dentro de una misma sesión.

Generalización del caso de CL a los países donde el barrido detectó sesiones
dobladas. A diferencia de CL, estos corpus **no registran la procedencia** de
cada fila (allí existía la columna `source` con el track de ingesta), así que la
elección de qué copia conservar se hace por la calidad de la propia fila.

Criterio de sesión doblada (el mismo del barrido, ya validado): ≥20 textos
distintos repetidos, ≥70% de ellos con multiplicidad exactamente 2, y ≥25% de las
filas de la sesión implicadas. Eso separa la sesión ingerida dos veces de la
repetición legítima de fórmulas de trámite — que es lo que arruina el conteo
ingenuo: MX repite «consulte la secretaría a la asamblea, en votación
económica…» 115 veces en una sola sesión, una por punto del orden del día.

Dentro de esas sesiones se deduplica **fila a fila**, nunca por bloques: se
conserva una sola fila por texto normalizado repetido, prefiriendo (1) la que
tiene `id_dep`, (2) la de texto más largo, (3) la primera. Las descartadas van a
cuarentena reversible.

Uso:  python3 dedupe_intrasesion.py {iso2} [--apply]
"""
from __future__ import annotations

import re
import shutil
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
    return re.sub(r"[^a-z0-9]", "", s)


def main(iso2: str, apply: bool) -> None:
    p = Path(f"source/{iso2}/standardize/{iso2.upper()}_interventions.csv")
    bak = p.with_name(f"{iso2.upper()}_interventions.pre_dedupeB.csv")
    quar = p.with_name(f"{iso2.upper()}_quarantine_intrasesion_dups.csv")

    # el separador varía por país (CL usa «;»): detectarlo, no asumir coma
    with open(p, encoding="utf-8") as _fh:
        _head = _fh.readline()
    _sep = ";" if _head.count(";") > _head.count(",") else ","
    df = pd.read_csv(p, dtype=str, keep_default_na=False, sep=_sep)
    n0 = len(df)
    df["_k"] = df.date + "|" + df.session_number
    tam = df.groupby("_k").size().to_dict()

    largo = df[df.text.str.len() >= MINLEN].copy()
    largo["_t"] = [norm(t)[:KEYLEN] for t in largo.text]
    g = largo.groupby(["_k", "_t"]).size()
    rep = g[g > 1]

    dobladas = []
    for k in {a for a, _ in rep.index}:
        sub = rep.loc[k]
        nd, n2 = len(sub), int((sub == 2).sum())
        extra = int((sub - 1).sum())
        pct = 100 * extra / tam.get(k, 1)
        if nd >= MIN_DISTINTOS and n2 / nd >= MIN_RATIO_X2 and pct >= MIN_PCT_SESION:
            dobladas.append(k)

    print(f"[{iso2}] {n0:,} filas · sesiones dobladas: {len(dobladas)}")
    if not dobladas:
        print("   nada que hacer")
        return

    cand = largo[largo._k.isin(dobladas)].copy()
    cand["_len"] = cand.text.str.len()
    cand["_hasid"] = (cand.id_dep.str.strip() != "").astype(int)
    drop = []
    for (k, t), n in cand.groupby(["_k", "_t"]).size().items():
        if n < 2:
            continue
        gg = cand[(cand._k == k) & (cand._t == t)].sort_values(
            ["_hasid", "_len"], ascending=[False, False], kind="stable")
        drop.extend(gg.index[1:].tolist())

    print(f"   filas a retirar: {len(drop):,} ({100*len(drop)/n0:.3f}% del corpus)")
    if not apply:
        print("   --- SIMULACIÓN ---")
        for k in dobladas[:5]:
            print(f"      {k}: {tam.get(k,0)} filas en la sesión")
        return

    if not bak.exists():
        shutil.copy2(p, bak)
        print(f"   copia de seguridad → {bak.name}")
    df.loc[drop].drop(columns=["_k"]).to_csv(quar, index=False, encoding="utf-8")
    out = df.drop(index=drop).drop(columns=["_k"])
    out.to_csv(p, index=False, encoding="utf-8")
    chk = pd.read_csv(p, dtype=str, keep_default_na=False)
    assert len(chk) == n0 - len(drop), "recuento inconsistente"
    print(f"   ✓ {len(chk):,} filas ({n0:,} − {len(drop):,}) · cuarentena {quar.name}")


if __name__ == "__main__":
    main(sys.argv[1], "--apply" in sys.argv)
