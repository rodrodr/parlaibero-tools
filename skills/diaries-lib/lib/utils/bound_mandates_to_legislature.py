#!/usr/bin/env python3
"""Acota los mandatos del padrón al rango real de su legislatura.

Algunos padrones registran **una fila por (persona × legislatura)** pero repiten en todas
las mismas fechas: las de la carrera entera, no las del mandato concreto. En PT,
*Amaro da Costa* figura en las legislaturas `Cons`, `I` y `II` con idénticas fechas de 1975
a 1980, y hay mandatos declarados de hasta **50 años**.

Eso no es cosmético: **inutiliza el desempate por fecha**. Ante un apellido repetido, todos
los candidatos figuran vigentes en cualquier fecha, así que el resolutor no puede elegir y
se abstiene. Es lo que dejaba la atribución de presidencia de PT en el 10,07% pese a que la
extracción funcionaba en 296 de cada 300 documentos.

El rango real de cada legislatura **se deriva del propio corpus** —primera y última fecha de
sesión— y cada fila se acota a la intersección de su carrera con ese rango.

⚠ **Nunca amplía, solo recorta.** Si la intersección es vacía la fila se deja intacta y se
marca: significa que la legislatura declarada no encaja con las fechas, y eso es un dato que
hay que mirar, no corregir en silencio.

⚠ **Es un arreglo del PADRÓN, no del corpus.** Ninguna intervención se toca
(`validation_methodology` §4.6).

Uso:
    python3 bound_mandates_to_legislature.py --country pt
    python3 bound_mandates_to_legislature.py --country pt --apply
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import pandas as pd


def ruta_padron(iso2: str) -> Path:
    for n in ("deputies.csv", "diputados_bd.csv"):
        p = Path(f"source/{iso2}/deputies/{n}")
        if p.exists():
            return p
    raise SystemExit(f"sin padrón para {iso2}")


def rangos_legislatura(iso2: str) -> dict:
    """Primera y última fecha de sesión de cada legislatura, según el propio corpus."""
    d = pd.read_csv(f"source/{iso2}/standardize/{iso2.upper()}_interventions.csv", dtype=str,
                    keep_default_na=False, usecols=["legislature", "date"])
    d = d[(d.legislature.str.strip() != "") & d.date.str.match(r"\d{4}-\d{2}-\d{2}")]
    g = d.assign(_d=pd.to_datetime(d.date, errors="coerce")).dropna(subset=["_d"]) \
         .groupby("legislature")._d.agg(["min", "max"])
    return {i: (r["min"], r["max"]) for i, r in g.iterrows()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    c = a.country.lower()

    p = ruta_padron(c)
    head = p.open(encoding="utf-8", errors="replace").readline()
    sep = ";" if head.count(";") > head.count(",") else ","
    r = pd.read_csv(p, sep=sep, dtype=str, keep_default_na=False)
    low = {x.lower(): x for x in r.columns}
    cle = next((low[k] for k in ("legislature", "legislatura", "legislatura_num") if k in low), None)
    cin = next((low[k] for k in ("start_date", "fecha_inicio", "fecha_alta") if k in low), None)
    cfi = next((low[k] for k in ("end_date", "fecha_fin", "fecha_baja") if k in low), None)
    if not (cle and cin and cfi):
        raise SystemExit(f"✗ {c}: el padrón necesita legislatura y fechas de inicio/fin")

    rng = rangos_legislatura(c)
    ini = pd.to_datetime(r[cin], errors="coerce")
    fin = pd.to_datetime(r[cfi], errors="coerce")
    antes = ((fin - ini).dt.days / 365.25)

    n_ac = n_sin = n_vacio = 0
    ni, nf = ini.copy(), fin.copy()
    for i in r.index:
        L = str(r.at[i, cle]).strip()
        if L not in rng or pd.isna(ini[i]) or pd.isna(fin[i]):
            n_sin += 1
            continue
        a0, b0 = rng[L]
        na, nb = max(ini[i], a0), min(fin[i], b0)
        if na > nb:
            n_vacio += 1          # la legislatura declarada no encaja: se deja intacta
            continue
        if (na, nb) != (ini[i], fin[i]):
            n_ac += 1
        ni[i], nf[i] = na, nb
    despues = ((nf - ni).dt.days / 365.25)

    print(f"{c.upper()} · {len(r):,} filas · {r[low.get('id_dep','id_dep')].nunique():,} personas")
    print(f"  legislaturas con rango derivado del corpus: {len(rng)}")
    print(f"  filas acotadas                : {n_ac:,}")
    print(f"  sin legislatura o sin fechas  : {n_sin:,}")
    print(f"  intersección vacía (se dejan) : {n_vacio:,}  ← revisar, no corregir en silencio")
    print(f"  duración del mandato · mediana {antes.median():.1f} → {despues.median():.1f} años")
    print(f"                        · máximo {antes.max():.1f} → {despues.max():.1f} años")

    if not a.apply:
        print("\n--- SIMULACIÓN --- (usa --apply para escribir)")
        return

    bak = p.with_name(p.stem + ".pre_mandatos.csv")
    if not bak.exists():
        shutil.copy2(p, bak)
        print(f"  copia de seguridad → {bak.name}")
    r[cin] = ni.dt.strftime("%Y-%m-%d").fillna(r[cin])
    r[cfi] = nf.dt.strftime("%Y-%m-%d").fillna(r[cfi])
    r.to_csv(p, sep=sep, index=False, encoding="utf-8")
    print(f"✓ {p.name} actualizado · {n_ac:,} mandatos acotados")


if __name__ == "__main__":
    main()
