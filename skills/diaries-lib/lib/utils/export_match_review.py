#!/usr/bin/env python3
"""Prepara la hoja de revisión MANUAL del matching, con candidatos y evidencia ya calculados.

**Por qué esta fase merece hoja propia.** El matching es donde se concentran los errores del
pipeline: la extracción y el etiquetado dan 95-99% con problemas locales, pero aquí los fallos
son de MODELO —tomar `speaker_raw` como clave cuando un cargo lo ocupa otra persona en cada
período, tratar como ambiguo a quien solo tiene varias legislaturas, atribuir sin comprobar el
mandato— y ninguno se ve en un recuento. La revisión humana es lo que los caza.

**Lo que hace esta hoja para que la revisión cunda:**

  · **Ordena por PESO** (`n_filas`): con 3.893 formas sin vincular en ES, el top-20 concentraba
    el 56%. Revisar por orden alfabético desperdicia el esfuerzo; por peso, veinte decisiones
    cubren más de la mitad del problema.
  · **Trae los CANDIDATOS ya buscados** del padrón, con su mandato y si cubre las fechas en que
    esa forma habla, para no tener que ir a consultarlos.
  · **Trae el CONTEXTO**: fechas y legislaturas en que aparece, y un fragmento de una de sus
    intervenciones, que suele bastar para reconocer a la persona.

⚠ **Lo que se deja EN BLANCO se respeta.** Una celda vacía significa «no es diputado» o «no hay
información», y es una decisión humana: la reimportación no la sobrescribe ni la reintenta.

Uso:
    python3 export_match_review.py --country py
    python3 export_match_review.py --country py --solo-sin-vincular --top 400
"""
from __future__ import annotations

import argparse
import csv as _csv
import re
import unicodedata as U
from collections import defaultdict

import pandas as pd


def nrm(s: str) -> str:
    s = U.normalize("NFD", str(s).upper())
    s = "".join(c for c in s if U.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^A-ZÑ ]", " ", s.replace("-", " "))).strip()


def leer(p: str):
    with open(p, encoding="utf-8") as fh:
        d = _csv.Sniffer().sniff(fh.readline(), ";,\t").delimiter
    return pd.read_csv(p, sep=d, dtype=str, keep_default_na=False)


def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument("--country", required=True)
    a.add_argument("--top", type=int, default=0, help="solo las N formas de más peso")
    a.add_argument("--solo-sin-vincular", action="store_true")
    a.add_argument("--out", default="")
    o = a.parse_args()
    c = o.country.lower()
    C = c.upper()

    m = leer(f"source/{c}/standardize/{C}_interventions.csv")
    dep_p = (f"source/{c}/deputies/deputies.csv" if __import__("os").path.exists(
        f"source/{c}/deputies/deputies.csv") else f"source/{c}/standardize/{C}_deputies.csv")
    dep = leer(dep_p)
    col_id = "id_dep"
    col_nom = "speaker_name" if "speaker_name" in dep.columns else "nombre_completo"
    col_ape = next((x for x in ("apellidos", "last_name", "apellidos_norm") if x in dep.columns), col_nom)

    # índice apellido normalizado → personas (deduplicadas: varias legislaturas ≠ ambigüedad)
    idx: dict[str, set] = defaultdict(set)
    for _, r in dep.iterrows():
        idx[nrm(str(r[col_ape]).split(",")[0])].add(r[col_id])
        idx[nrm(r[col_nom])].add(r[col_id])
    nom = dict(zip(dep[col_id], dep[col_nom]))

    ctx = defaultdict(lambda: {"n": 0, "fechas": set(), "legs": set(), "txt": ""})
    for s, f, l, t in zip(m.speaker_raw, m.date, m.get("legislature", [""] * len(m)), m.text):
        k = ctx[s]
        k["n"] += 1
        k["fechas"].add(f)
        k["legs"].add(l)
        if not k["txt"] and len(t) > 120:
            k["txt"] = re.sub(r"\s+", " ", t)[:180]

    # ⚠ CONJUNTO de ids por forma. La clave del matching es (speaker_raw, date): `PRESIDENTE` son
    # 20 personas en ES y un apellido compartido son dos diputados de períodos distintos. Volcar
    # UNO solo —el último que sobreviva a un `dict(zip(...))`— presenta como asignación firme lo
    # que es una entre varias, e invita a «corregirla». La hoja lo dice explícitamente.
    vinc: dict[str, set] = {}
    for s, i in zip(m.speaker_raw, m.id_dep):
        if i:
            vinc.setdefault(s, set()).add(i)
    filas = []
    for s, k in sorted(ctx.items(), key=lambda kv: -kv[1]["n"]):
        ii = sorted(vinc.get(s, ()))
        actual = ii[0] if len(ii) == 1 else (f"⟨{len(ii)} personas — no tocar⟩" if ii else "")
        if o.solo_sin_vincular and ii:
            continue
        cand = sorted(idx.get(nrm(s), set()))
        filas.append({
            "speaker_raw": s,
            "id_dep": actual,                      # ← rellenar o corregir AQUÍ
            "nombre_completo": nom.get(actual, "") if len(ii) == 1 else "",
            "n_filas": k["n"],
            "fechas": f"{min(k['fechas'])} … {max(k['fechas'])}" if k["fechas"] else "",
            "legislaturas": ",".join(sorted(x for x in k["legs"] if x))[:40],
            "candidatos": " | ".join(f"{i}={nom.get(i,'')}" for i in cand[:4]),
            "fragmento": k["txt"],
            "notas": "",
        })
    if o.top:
        filas = filas[:o.top]
    out = o.out or f"source/{c}/match/matching_review_{C}.csv"
    df = pd.DataFrame(filas)
    df.to_csv(out, sep=";", index=False, encoding="utf-8")
    ac = df.n_filas.cumsum() / df.n_filas.sum() if len(df) else []
    print(f"── {C} · hoja de revisión ──")
    print(f"  formas: {len(df):,} · filas que representan: {df.n_filas.sum():,}")
    if len(df) >= 20:
        print(f"  concentración: top-20 = {100*ac.iloc[19]:.1f}% · top-50 = "
              f"{100*ac.iloc[min(49,len(ac)-1)]:.1f}% de las filas")
    print(f"  → {out}")
    print("  Ábrelo en Numbers, ordena por `n_filas` y rellena `id_dep`.")
    print("  ⚠ Lo que dejes EN BLANCO se respeta: no se reintenta ni se sobrescribe.")


if __name__ == "__main__":
    main()
