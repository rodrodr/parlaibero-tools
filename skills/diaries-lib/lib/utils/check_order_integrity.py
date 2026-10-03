#!/usr/bin/env python3
"""Comprueba que `intervention_order` no ha perdido nada: cada hueco debe estar en un sidecar.

`intervention_order` es la posición de la intervención **en la sesión original**, y se conserva
al apartar filas a un sidecar. Por eso una secuencia con huecos no es un error: es la huella de
lo que se movió. Pero entonces hace falta poder distinguir las dos cosas:

    hueco EXPLICADO    la posición está en un sidecar del país → reversible, por diseño
    hueco HUÉRFANO     la posición no está en ninguna parte    → fila perdida de verdad

⚠ **Sin esta comprobación, «empieza en 2» y «faltan posiciones» son indistinguibles de una
pérdida de datos.** BR, PE y SV arrancan en la posición 2 en TODAS sus sesiones, y la
explicación resultó ser que la fila de apertura —cabecera, no discurso— se apartó al sidecar en
todas ellas: SV 389 filas de orden 1 para 389 sesiones, BR 6.921, PE 3.000. Parecía un
off-by-one sistemático y era una operación deliberada y reversible.

⚠ **La clave de sesión no es siempre `date` + `session_number`.** BR tiene 40.672 filas con
`session_number` vacío, así que dos sesiones del mismo día caen en el mismo grupo y aparecen
como «órdenes duplicados» que no lo son. La utilidad detecta el caso y lo dice en vez de
denunciar un defecto inexistente.

Uso:
    python3 check_order_integrity.py --country br
    python3 check_order_integrity.py --all
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import pandas as pd

PAISES = "ar br cl co cr do ec es gt mx pa pe pt py sv uy".split()


def sidecars(iso2: str) -> dict:
    """→ {(fecha, sesion): {posiciones apartadas}} de todos los sidecars del país."""
    fuera: dict = defaultdict(set)
    for p in Path(f"source/{iso2}/standardize").glob("*sidecar*.csv"):
        if ".pre_" in p.name:
            continue
        d = pd.read_csv(p, dtype=str, keep_default_na=False)
        if not {"date", "intervention_order"} <= set(d.columns):
            continue
        ses = d["session_number"] if "session_number" in d.columns else ""
        o = pd.to_numeric(d.intervention_order, errors="coerce")
        for f, s, k in zip(d.date, ses if len(ses) else [""] * len(d), o):
            if pd.notna(k):
                fuera[(f, s)].add(int(k))
    return fuera


def revisar(iso2: str) -> dict | None:
    p = Path(f"source/{iso2}/standardize/{iso2.upper()}_interventions.csv")
    if not p.exists():
        return None
    d = pd.read_csv(p, dtype=str, keep_default_na=False)
    if "intervention_order" not in d.columns:
        return {"pais": iso2.upper(), "sin_columna": True}
    d["_o"] = pd.to_numeric(d.intervention_order, errors="coerce")
    sin_num = int((d.session_number.str.strip() == "").sum()) if "session_number" in d else 0
    fuera = sidecars(iso2)

    n = huecos = expl = huerf = dup = 0
    ses = d["session_number"] if "session_number" in d.columns else pd.Series("", d.index)
    for (f, s), g in d.groupby([d.date, ses]):
        n += 1
        o = g._o.dropna().astype(int)
        if o.empty:
            continue
        if o.duplicated().any():
            dup += 1
        falta = set(range(1, int(o.max()) + 1)) - set(o)
        if falta:
            huecos += 1
            ap = fuera.get((f, s), set())
            e = len(falta & ap)
            expl += e
            huerf += len(falta) - e
    return {"pais": iso2.upper(), "sesiones": n, "con_huecos": huecos,
            "pos_explicadas": expl, "pos_huerfanas": huerf, "dup": dup,
            "sin_session_number": sin_num}


def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument("--country")
    a.add_argument("--all", action="store_true")
    o = a.parse_args()
    cs = PAISES if o.all else [o.country.lower()]

    print(f"{'':4} {'sesiones':>9} {'c/huecos':>9} {'explicadas':>11} {'HUÉRFANAS':>10} "
          f"{'ord.dup':>8}")
    aviso = []
    for c in cs:
        r = revisar(c)
        if not r:
            continue
        if r.get("sin_columna"):
            print(f"{r['pais']:4} sin columna intervention_order")
            continue
        print(f"{r['pais']:4} {r['sesiones']:>9,} {r['con_huecos']:>9,} "
              f"{r['pos_explicadas']:>11,} {r['pos_huerfanas']:>10,} {r['dup']:>8,}")
        if r["sin_session_number"]:
            aviso.append(f"  ⚠ {r['pais']}: {r['sin_session_number']:,} filas sin "
                         f"`session_number` — la clave (fecha, sesión) agrupa DOS sesiones del "
                         f"mismo día en una, y sus «órdenes duplicados» son artefacto de eso")
    for x in aviso:
        print(x)
    print("\n⚠ Un hueco EXPLICADO está en un sidecar y es reversible; uno HUÉRFANO es una fila "
          "que\n  no está en ninguna parte. Solo la segunda columna es un defecto.")


if __name__ == "__main__":
    main()
