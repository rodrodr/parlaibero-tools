#!/usr/bin/env python3
"""Punto 7 del protocolo — contraste del padrón contra los escaños de la cámara.

Detecta **basura de parseo del pase de lista**: si un período registra muchas más
personas que escaños tiene la cámara, el padrón está absorbiendo entradas que no
son diputados (líneas mal cortadas, cargos, erratas de OCR convertidas en personas).

⚠ Este punto quedó mal medido en la primera pasada. Se usó «mandatos activos por
año», que produce **picos falsos en los años de elección**: en un año de relevo
conviven el mandato saliente y el entrante, así que el recuento se dispara sin que
haya nada anómalo. Además, derivar el mandato como `min(inicio)`–`max(fin)` por
persona **puentea los huecos** de quien tuvo mandatos discontinuos.

Aquí se cuenta por **PERÍODO declarado** (una fila de padrón = un mandato), que es
la unidad correcta: por definición, en un período no puede haber más titulares que
escaños, salvo por sustituciones — que existen y hay que tolerar.

Umbral: se marca el período cuyo censo supere en más del **40%** la mediana de los
demás períodos del mismo país. Ese margen absorbe suplencias y renuncias; por
encima, es basura de parseo.

Uso:  python3 punto7_roster_vs_escanos.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

PAISES = ["ar", "br", "cl", "co", "cr", "do", "es", "gt", "mx", "pa", "pe", "pt", "py", "sv", "uy"]

ALIAS_ID = ["id_dep", "diputado_id"]
ALIAS_PER = ["legislature", "legislatura", "id_legislatura", "legislatura_num"]
ALIAS_INI = ["fecha_inicio", "fecha_alta", "start_date", "dt_inicio_partido"]


def pick(cols, keys):
    low = {c.lower(): c for c in cols}
    for k in keys:
        if k.lower() in low:
            return low[k.lower()]
    return None


def cargar(iso2: str):
    for nombre in ("deputies.csv", "diputados_bd.csv"):
        p = Path(f"source/{iso2}/deputies/{nombre}")
        if p.exists():
            break
    else:
        return None
    head = p.open(encoding="utf-8", errors="replace").readline()
    sep = ";" if head.count(";") > head.count(",") else ","
    return pd.read_csv(p, sep=sep, dtype=str, keep_default_na=False)


def main() -> None:
    print(f"{'':4} {'personas':>9} {'períodos':>9} {'mediana':>8} {'máximo':>8}  períodos anómalos")
    print("-" * 84)
    for c in PAISES:
        r = cargar(c)
        if r is None:
            print(f"{c.upper():4} sin padrón legible")
            continue
        cid = pick(r.columns, ALIAS_ID)
        per = pick(r.columns, ALIAS_PER)
        ini = pick(r.columns, ALIAS_INI)
        if not cid:
            print(f"{c.upper():4} sin columna de id")
            continue
        if per:
            g = r.groupby(r[per].astype(str))[cid].nunique()
        elif ini:
            # sin columna de período: agrupar por año de inicio de mandato
            g = r.assign(_a=pd.to_datetime(r[ini], errors="coerce").dt.year).dropna(subset=["_a"]) \
                 .groupby("_a")[cid].nunique()
        else:
            print(f"{c.upper():4} sin período ni fecha")
            continue
        g = g[g > 0]
        if len(g) < 2:
            print(f"{c.upper():4} {r[cid].nunique():9,} {len(g):9}  (un solo período: no comparable)")
            continue
        med = g.median()
        anom = [(k, int(v), round(v / med, 2)) for k, v in g.items() if v > med * 1.4]
        anom.sort(key=lambda x: -x[2])
        et = ", ".join(f"{k}={v} ({r_}×)" for k, v, r_ in anom[:3]) or "—"
        print(f"{c.upper():4} {r[cid].nunique():9,} {len(g):9} {med:8.0f} {int(g.max()):8,}  {et}")


if __name__ == "__main__":
    main()
