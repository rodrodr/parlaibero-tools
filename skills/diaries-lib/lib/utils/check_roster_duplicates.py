#!/usr/bin/env python3
"""Punto 4 del protocolo — duplicados de padrón invisibles al fuzzy.

Dos clases que ni el fuzzy ni el subconjunto pueden ver, porque el token que
difiere no es un typo ni un subconjunto:

  (a) **abreviaturas** — `Betzaida Ma. Manuela Santana Sierra` =
      `Betzaida María Manuela Santana Sierra`;
  (b) **apellido de casada** — `Betzaida María Santana Sierra` (la del acta) =
      `Betzaida María Santana de Báez` (la del listado oficial).

La (b) **sesga por género**: las listas oficiales suelen usar la forma de casada y
las actas la de soltera, así que **las diputadas se quedan sin partido ni
distrito mientras los diputados sí los reciben**.

⚠ Este script REEMPLAZA un detector anterior que era inservible: pedía solo dos
tokens compartidos en cualquier posición y no comprobaba el período, y daba 489
falsos positivos en PT, donde la partícula «de» es corriente en la onomástica
(`Alfredo António de Sousa` emparejado con `Alfredo António Rodrigues Soeiro de
Barros`, que son personas distintas). Aquí se aplica la regla de
`diaries-deputies` Pasada 3-bis, que es bastante más estricta:

  · ≥3 tokens iniciales IDÉNTICOS del núcleo (pila + apellidos sin partículas)
  · colas distintas
  · una de las dos formas contiene ` de ` o `Vda.`
  · **mandatos solapados o contiguos** (una persona no ocupa dos escaños a la vez)
  · **la cédula es el árbitro**: si ambas la traen y difieren, son personas
    distintas, sin discusión

Uso:  python3 punto4_duplicados_padron.py
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

import pandas as pd

PAISES = ["ar", "br", "cl", "co", "cr", "do", "es", "gt", "mx", "pa", "pe", "pt", "py", "sv", "uy"]

ABBR = {"ma": "maria", "mª": "maria", "jo": "jose", "fco": "francisco", "fca": "francisca",
        "ant": "antonio", "ml": "manuel", "mnl": "manuel", "gmo": "guillermo", "fdo": "fernando",
        "dgo": "domingo", "mgl": "miguel", "rfl": "rafael", "edo": "eduardo", "alb": "alberto",
        "jn": "juan", "jose ma": "jose maria"}
PART = {"de", "del", "la", "las", "los", "y", "vda", "viuda", "da", "do", "dos", "das", "e"}
MARCA_CASADA = re.compile(r"\b(?:de|del|vda\.?|viuda)\s+[A-ZÁÉÍÓÚÑ]", re.I)
CEDULA = re.compile(r"\b(\d{3}-\d{7}-\d|\d{7,11})\b")

ALIAS = {"id": ["id_dep", "diputado_id"],
         "name": ["nombre_completo", "speaker_name", "nombre_original", "alias"],
         "start": ["fecha_inicio", "fecha_alta", "start_date", "dt_inicio_partido"],
         "end": ["fecha_fin", "fecha_baja", "end_date", "dt_fin_partido"],
         "notas": ["notas", "notes"]}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z\s]", " ", s)).strip()


def nucleo(s: str) -> list[str]:
    ts = [ABBR.get(t, t) for t in norm(s).split()]
    return [t for t in ts if t not in PART]


def pick(cols, keys):
    low = {c.lower(): c for c in cols}
    for k in keys:
        if k.lower() in low:
            return low[k.lower()]
    return None


def cargar(iso2: str):
    p = Path(f"source/{iso2}/deputies/deputies.csv")
    if not p.exists():
        p = Path(f"source/{iso2}/deputies/diputados_bd.csv")
    if not p.exists():
        return None
    head = p.open(encoding="utf-8", errors="replace").readline()
    sep = ";" if head.count(";") > head.count(",") else ","
    df = pd.read_csv(p, sep=sep, dtype=str, keep_default_na=False)
    m = {k: pick(df.columns, v) for k, v in ALIAS.items()}
    if not m["id"] or not m["name"]:
        return None
    out = pd.DataFrame({"id": df[m["id"]], "name": df[m["name"]]})
    for k in ("start", "end"):
        out[k] = pd.to_datetime(df[m[k]], errors="coerce", dayfirst=True, format="mixed") \
            if m[k] else pd.NaT
    out["notas"] = df[m["notas"]] if m["notas"] else ""
    return out


def solapan(a, b) -> bool:
    """Mandatos solapados o contiguos (±2 años)."""
    a0, a1, b0, b1 = a
    if pd.isna(a0) or pd.isna(b0):
        return True                        # sin fechas: no se puede descartar
    a1 = a1 if pd.notna(a1) else a0
    b1 = b1 if pd.notna(b1) else b0
    hueco = min(abs((b0 - a1).days), abs((a0 - b1).days))
    return not (a1 < b0 or b1 < a0) or hueco <= 730


def analizar(iso2: str) -> dict:
    r = cargar(iso2)
    if r is None:
        return {"iso2": iso2, "error": "padrón no legible"}
    # una entrada por id (mandato mínimo/máximo, notas concatenadas)
    g = r.groupby("id", dropna=True)
    pers = pd.DataFrame({
        "name": g["name"].first(),
        "start": g["start"].min(),
        "end": g["end"].max(),
        "notas": g["notas"].apply(lambda s: " ".join(map(str, s))),
    }).reset_index()

    ced = {}
    for i, n in zip(pers["id"], pers.notas):
        m = CEDULA.search(str(n))
        if m:
            ced[i] = m.group(1)

    # índice por los 3 primeros tokens del núcleo: la firma exigida por el skill
    idx = defaultdict(list)
    for i, n in zip(pers["id"], pers.name):
        nu = nucleo(n)
        if len(nu) >= 3:
            idx[tuple(nu[:3])].append((i, n, nu))

    abrev, casada, descart_ced, descart_fecha = [], [], 0, 0
    mand = {i: (a, b) for i, a, b in zip(pers["id"], pers.start, pers.end)}

    for clave, grupo in idx.items():
        if len(grupo) < 2:
            continue
        for x in range(len(grupo)):
            for y in range(x + 1, len(grupo)):
                (ia, na, nua), (ib, nb, nub) = grupo[x], grupo[y]
                if nua == nub:                      # misma grafía exacta: otra clase
                    continue
                # árbitro: cédulas distintas ⇒ personas distintas
                if ia in ced and ib in ced and ced[ia] != ced[ib]:
                    descart_ced += 1
                    continue
                a, b = mand[ia], mand[ib]
                if not solapan((a[0], a[1], b[0], b[1]), None):
                    descart_fecha += 1
                    continue
                marca = bool(MARCA_CASADA.search(na)) ^ bool(MARCA_CASADA.search(nb))
                par = {"id_a": ia, "name_a": na, "id_b": ib, "name_b": nb,
                       "nucleo_comun": list(clave)}
                if marca and nua[:3] == nub[:3] and nua[3:] != nub[3:]:
                    casada.append(par)
                elif set(norm(na).split()) != set(norm(nb).split()) and nua[:3] == nub[:3]:
                    abrev.append(par)

    return {"iso2": iso2, "personas": len(pers),
            "apellido_casada": len(casada), "abreviatura": len(abrev),
            "descartados_por_cedula": descart_ced, "descartados_por_fecha": descart_fecha,
            "ejemplos_casada": casada[:6], "ejemplos_abrev": abrev[:6]}


if __name__ == "__main__":
    outdir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    tot = {"casada": 0, "abrev": 0}
    print(f"{'':4} {'personas':>9} {'casada':>7} {'abrev':>6} {'desc.céd':>9} {'desc.fecha':>11}")
    print("-" * 52)
    res = {}
    for c in PAISES:
        r = analizar(c)
        res[c] = r
        if "error" in r:
            print(f"{c.upper():4} {r['error']}")
            continue
        tot["casada"] += r["apellido_casada"]
        tot["abrev"] += r["abreviatura"]
        print(f"{c.upper():4} {r['personas']:9,} {r['apellido_casada']:7} {r['abreviatura']:6} "
              f"{r['descartados_por_cedula']:9} {r['descartados_por_fecha']:11}")
    print("-" * 52)
    print(f"TOTAL — apellido de casada: {tot['casada']} · abreviaturas: {tot['abrev']}")
    (outdir / "punto4_resultado.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\ndetalle en {outdir/'punto4_resultado.json'}")
