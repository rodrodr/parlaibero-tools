#!/usr/bin/env python3
"""Audita la atribución de la presidencia con un juez INDEPENDIENTE: el género del vocativo.

Cuando un orador abre su turno dirigiéndose a la mesa —«Sr.ª Presidente», «Señora Presidenta»,
«Sr. Presidente»— el acta está declarando el **sexo de quien preside en ese momento**, y lo
hace con un mecanismo que no comparte nada con la atribución: ni el extractor, ni el padrón,
ni el resolutor de nombres. Contrastarlo con el `sex` de la persona atribuida da una tasa de
acierto medida, no una tasa de reproducción.

**Por qué hace falta.** `--check` de `attribute_presidency.py` compara contra lo que ya había,
y lo que ya había también puede estar mal. En PT el corpus vigente acertaba el **94,09%** y el
genérico por tramos el **99,00%**: sin este juez, la versión mejor parecía la peor, porque
reproducía menos.

⚠ **No ve confusiones entre personas del mismo sexo**, que en cámaras muy masculinizadas son
la mayoría de los casos posibles. Es un límite inferior del error, nunca un certificado. Y
por eso mismo un resultado alto NO autoriza a saltarse el muestreo del acta.

⚠ **El vocativo pertenece a la intervención CONTIGUA, no a la que se juzga**: quien saluda a
la mesa es el orador siguiente, no quien preside. Se busca en ±2 turnos y se descarta si no
aparece ninguno.

⚠ **Un `sex` que falte no cuenta como fallo.** Solo se juzgan las filas donde tanto el
vocativo como el padrón se pronuncian; lo demás queda fuera del denominador y se informa.

Uso:
    python3 audit_presidency_gender.py --country pt                 # audita el corpus actual
    python3 audit_presidency_gender.py --country pt --compare       # actual vs genérico
"""
from __future__ import annotations

import argparse
import glob
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import attribute_presidency as ap          # noqa: E402

# El grupo 1 decide el sexo: si trae marca de femenino, preside una mujer.
VOCATIVO = re.compile(
    r"^\s*(?:Ex\.?[ma]{0,3}\.?\s*)?"
    r"(Sr\.ª|Sr\.as|Sra\.|Sras\.|Senhora|Se[ñn]ora|Sr\.|Sr\.s|Srs\.|Senhor|Se[ñn]or)"
    r"\s*[.,]?\s*President[ae]\b", re.I)
FEMENINO = re.compile(r"ª|sra|sras|senhora|se[ñn]ora", re.I)


def vocativos(df: pd.DataFrame) -> dict:
    """→ {(fecha, sesion): {orden: 'M'|'F'}} leído de la PROPIA MATRIZ.

    ⚠ **No se lee de `tagged/`.** BR y PE se construyeron fuera del pipeline y no tienen esa
    carpeta, y UY etiqueta con otra marca: un juez que dependa de los intermedios solo sirve
    para los países que los conservan —falló en 4 de 6—. El `text` de la matriz es lo único
    que existe en los 16 por definición.
    """
    orden = "intervention_order"
    r = pd.to_numeric(df[orden], errors="coerce")
    ses = df["session_number"] if "session_number" in df.columns else ""
    out = {}
    for (f, s, k), txt in zip(zip(df.date, ses, r), df.text):
        if pd.isna(k):
            continue
        m = VOCATIVO.match(str(txt).lstrip())
        if m:
            out.setdefault((f, s), {})[int(k)] = "F" if FEMENINO.search(m.group(1)) else "M"
    return out


def sexo_por_id(iso2: str, df: pd.DataFrame) -> dict:
    s = dict(zip(df.id_dep, df.sex)) if "sex" in df.columns else {}
    p = Path(f"source/{iso2}/standardize/{iso2.upper()}_deputies.csv")
    if p.exists():
        r = pd.read_csv(p, dtype=str, keep_default_na=False)
        if "sex" in r.columns:
            s.update(dict(zip(r.id_dep, r.sex)))
    return s


def juzgar(df, es_pres, voc, sexo, getid, ventana=2):
    """Contrasta el sexo de quien se atribuye con el género del vocativo contiguo."""
    ok = mal = sin_voc = sin_sexo = 0
    r = pd.to_numeric(df["intervention_order"], errors="coerce")
    ses = df["session_number"] if "session_number" in df.columns else pd.Series("", df.index)
    for i in df.index[es_pres]:
        k = r[i]
        if pd.isna(k):
            continue
        vv = voc.get((df.at[i, "date"], ses[i]))
        rk = int(k)
        gen = next((vv[rk + d] for j in range(1, ventana + 1) for d in (j, -j)
                    if vv and rk + d in vv), None) if vv else None
        if not gen:
            sin_voc += 1
            continue
        sx = sexo.get(getid(i), "")
        if sx not in ("M", "F"):
            sin_sexo += 1
            continue
        ok += sx == gen
        mal += sx != gen
    return ok, mal, sin_voc, sin_sexo


def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument("--country", required=True)
    a.add_argument("--compare", action="store_true", help="contrasta el corpus con el genérico")
    a.add_argument("--window", type=int, default=2)
    o = a.parse_args()
    c = o.country.lower()

    cfg = ap.cargar_config(c)
    if not cfg:
        raise SystemExit(f"✗ {c}: sin bloque `presidency:` en country_config/{c}.yaml")
    df = pd.read_csv(f"source/{c}/standardize/{c.upper()}_interventions.csv",
                     dtype=str, keep_default_na=False)
    if "sex" not in df.columns:
        raise SystemExit(f"✗ {c}: la matriz no tiene columna `sex`")

    voc = vocativos(df)
    n = sum(len(v) for v in voc.values())
    if not n:
        raise SystemExit(f"✗ {c}: ningún vocativo localizado en el `text` de la matriz")
    es = ap.objetivo_presidencia(df, cfg)
    sexo = sexo_por_id(c, df)

    print(f"{c.upper()} · {n:,} vocativos con género en {len(voc):,} sesiones · "
          f"{int(es.sum()):,} filas de presidencia")
    filas = [("corpus actual", lambda i: df.at[i, "id_dep"])]
    if o.compare:
        asign, _, _ = ap.atribuir(c, cfg, df.assign(id_dep=""))
        filas.append(("genérico", lambda i: asign.get(i, "")))
    for etiq, get in filas:
        ok, mal, sv, ss = juzgar(df, es, voc, sexo, get, o.window)
        t = ok + mal
        print(f"  {etiq:16} acierta {ok:8,} de {t:8,} = "
              f"{(100*ok/t if t else 0):6.2f}%   (sin vocativo {sv:,} · sin sexo {ss:,})")
    print("\n⚠ no ve confusiones entre personas del MISMO sexo: es un límite inferior del error")


if __name__ == "__main__":
    main()
