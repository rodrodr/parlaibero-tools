#!/usr/bin/env python3
"""Huella de calidad de un corpus, para comparar ANTES y DESPUÉS de un reproceso.

Sin una medición tomada **antes**, «el reproceso mejoró el corpus» es una afirmación que nadie
puede comprobar —ni un revisor, ni nosotros dentro de seis meses—. Esta utilidad congela en un
JSON las magnitudes que definen la calidad estructural, para que el después se pueda restar del
antes y publicar la diferencia.

No juzga: mide. Cada campo es una cifra reproducible con el mismo código sobre las dos
versiones.

⚠ **Se toma ANTES de la primera modificación.** Una huella tomada a medias no sirve de
referencia, y no hay forma de reconstruirla luego salvo restaurando copias.

⚠ **Los cero se declaran, no se omiten.** Un país con 0 saltos de línea (CL, ES, GT) tiene ese
0 escrito en su huella: es el dato más importante de los tres, porque significa que varios
controles no pueden ni ejecutarse ahí.

Uso:
    python3 corpus_fingerprint.py --all --out docs/_historico/linea_base_2026-08-02.json
    python3 corpus_fingerprint.py --compare docs/_historico/linea_base_2026-08-02.json
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd

PAISES = "ar br cl co cr do ec es gt mx pa pe pt py sv uy".split()
SOLO_DIGITOS = re.compile(r"^[\s\-–—.\[\(]*\d{1,4}[\s\-–—.\]\)]*$")
NO_DIPUTADO = re.compile(r"ministr|secretari|president[ae] de la rep|invitad|embajador|"
                         r"defensor|contralor|fiscal|magistrad", re.I)


def huella(iso2: str) -> dict | None:
    p = Path(f"source/{iso2}/standardize/{iso2.upper()}_interventions.csv")
    if not p.exists():
        return None
    d = pd.read_csv(p, dtype=str, keep_default_na=False)
    n = len(d)
    txt = d["text"].astype(str)
    fechas = d["date"][d["date"].str.match(r"\d{4}-\d{2}-\d{2}", na=False)]
    ses = d["session_number"] if "session_number" in d.columns else pd.Series("", d.index)

    con_id = int((d["id_dep"].str.strip() != "").sum()) if "id_dep" in d.columns else 0
    nombrado_sin_id = int(((d["id_dep"].str.strip() == "") &
                           d["speaker_raw"].str.contains(NO_DIPUTADO, na=False)).sum()) \
        if "id_dep" in d.columns else 0

    # integridad del orden, por sesión
    orden = pd.to_numeric(d.get("intervention_order"), errors="coerce")
    huecos = arranca_en_1 = 0
    for _, g in d.assign(_o=orden).groupby([d["date"], ses]):
        o = g["_o"].dropna().astype(int)
        if o.empty:
            continue
        if o.min() == 1:
            arranca_en_1 += 1
        if len(o) != int(o.max() - o.min() + 1):
            huecos += 1

    lineas = folios = 0
    for t in txt:
        if "\n" not in t:
            continue
        for ln in t.split("\n"):
            s = ln.strip()
            if s:
                lineas += 1
                if SOLO_DIGITOS.match(s):
                    folios += 1

    sx = Counter(d["sex"]) if "sex" in d.columns else Counter()
    return {
        "filas": n,
        "columnas": list(d.columns),
        "caracteres": int(txt.str.len().sum()),
        "fechas_unicas": int(fechas.nunique()),
        "rango": [fechas.min(), fechas.max()] if len(fechas) else None,
        "formas_speaker_raw": int(d["speaker_raw"].nunique()),
        "formas_que_aparecen_una_vez": int((d["speaker_raw"].value_counts() == 1).sum()),
        "filas_con_saltos_de_linea": int(txt.str.contains("\n").sum()),
        "lineas_no_vacias": lineas,
        "lineas_de_solo_digitos": folios,
        "vinculacion_bruta": round(100 * con_id / n, 2) if n else 0,
        "no_diputados_nombrados_sin_id": nombrado_sin_id,
        "sesiones_con_huecos_de_orden": huecos,
        "sesiones_que_arrancan_en_1": arranca_en_1,
        "sex_M": sx.get("M", 0), "sex_F": sx.get("F", 0),
        "sex_vacio": sx.get("", 0),
    }


def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument("--country")
    a.add_argument("--all", action="store_true")
    a.add_argument("--out", default="")
    a.add_argument("--compare", default="")
    o = a.parse_args()

    if o.compare:
        prev = json.loads(Path(o.compare).read_text(encoding="utf-8"))
        print(f"comparando contra {o.compare} ({prev.get('_fecha')})\n")
        for c in sorted(k for k in prev if not k.startswith("_")):
            act = huella(c)
            if not act:
                print(f"{c.upper()}: no existe ahora"); continue
            ant = prev[c]
            print(f"── {c.upper()}")
            for k in ("filas", "caracteres", "fechas_unicas", "vinculacion_bruta",
                      "filas_con_saltos_de_linea", "lineas_de_solo_digitos",
                      "sesiones_con_huecos_de_orden", "formas_speaker_raw"):
                x, y = ant.get(k), act.get(k)
                if x != y:
                    d = (y - x) if isinstance(x, (int, float)) else None
                    print(f"   {k:34} {x:>12,} → {y:>12,}"
                          + (f"  ({d:+,})" if d is not None else ""))
            if ant.get("columnas") != act.get("columnas"):
                print(f"   ⚠ ESQUEMA cambiado: {len(ant['columnas'])} → {len(act['columnas'])} col.")
        return

    cs = PAISES if o.all else [o.country.lower()]
    out = {"_fecha": str(date.today()),
           "_nota": "Línea base tomada ANTES del reproceso. No juzga: mide."}
    for c in cs:
        h = huella(c)
        if h:
            out[c] = h
            print(f"  {c.upper():3} {h['filas']:>10,} filas · {h['fechas_unicas']:>5,} fechas · "
                  f"vinc. {h['vinculacion_bruta']:>5.1f}% · saltos {h['filas_con_saltos_de_linea']:>9,}")
    if o.out:
        Path(o.out).parent.mkdir(parents=True, exist_ok=True)
        Path(o.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n✓ huella de {len(out)-2} países → {o.out}")


if __name__ == "__main__":
    main()
