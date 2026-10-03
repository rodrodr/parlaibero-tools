#!/usr/bin/env python3
"""Reimporta la revisión MANUAL del matching —`.numbers` o `.csv`— al corpus y a la tabla del país.

Complemento de `export_match_review.py`. Lee la hoja revisada, **comprueba antes de escribir** y
solo entonces aplica.

**Comprobaciones, y por qué cada una:**

  1. **El `id_dep` existe en el padrón.** Un identificador tecleado a mano puede tener una errata,
     y un `id_dep` huérfano rompe la integridad referencial del corpus sin que nada avise.
  2. **No contradice lo automático en silencio.** Si la hoja cambia un `id_dep` que ya estaba, se
     LISTA para que la persona lo confirme: puede ser una corrección deliberada o un descuido al
     arrastrar celdas en la hoja de cálculo.
     ⚠ **Una forma puede tener VARIOS `id_dep` legítimos**: la clave del matching es
     `(speaker_raw, date)`, así que `PRESIDENTE` son 20 personas en ES y un apellido compartido
     son dos diputados de períodos distintos. Comparar contra UN id —el que sobreviva a un
     `dict(zip(...))`, que se queda con el último— inventa contradicciones: en ES dio **53
     falsas, todas con el id del investigador ya presente en el corpus**. La comparación es
     contra el CONJUNTO de ids de esa forma.
  3. **Las celdas VACÍAS se respetan.** Vacío significa «no es diputado» o «no hay información»,
     y es una decisión humana. No se reintenta ni se rellena con una conjetura automática: eso
     sería sustituir un juicio informado por uno peor.

⚠ **No comparar `legislature` del corpus con la del padrón sin mirar su formato.** En SV el corpus
la guarda como RANGO (`XII–XIV`) y el padrón suelta (`XII`, `XIII`): la intersección nunca casa y
produce 34 avisos falsos sobre datos correctos.

Uso:
    python3 import_match_review.py --country sv --file source/sv/match/matching_table_manual.numbers --dry-run
    python3 import_match_review.py --country sv --file … --apply
"""
from __future__ import annotations

import argparse
import csv as _csv
import shutil
from pathlib import Path

import pandas as pd


def leer_hoja(p: str) -> pd.DataFrame:
    if p.endswith(".numbers"):
        from numbers_parser import Document
        filas = Document(p).sheets[0].tables[0].rows(values_only=True)
        return pd.DataFrame(filas[1:], columns=filas[0]).fillna("")
    with open(p, encoding="utf-8") as fh:
        d = _csv.Sniffer().sniff(fh.readline(), ";,\t").delimiter
    return pd.read_csv(p, sep=d, dtype=str, keep_default_na=False)


def leer(p: str):
    with open(p, encoding="utf-8") as fh:
        d = _csv.Sniffer().sniff(fh.readline(), ";,\t").delimiter
    return pd.read_csv(p, sep=d, dtype=str, keep_default_na=False), d


def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument("--country", required=True)
    a.add_argument("--file", required=True)
    a.add_argument("--apply", action="store_true")
    a.add_argument("--dry-run", action="store_true")
    o = a.parse_args()
    if not (o.apply or o.dry_run):
        raise SystemExit("✗ elige --dry-run o --apply")
    c, C = o.country.lower(), o.country.upper()

    hoja = leer_hoja(o.file).astype(str)
    hoja = hoja[hoja.speaker_raw.str.strip() != ""]
    mp = {r.speaker_raw: str(r.id_dep).strip() for _, r in hoja.iterrows()
          if str(r.id_dep).strip() not in ("", "nan", "None")}

    dep_p = (f"source/{c}/deputies/deputies.csv" if Path(f"source/{c}/deputies/deputies.csv").exists()
             else f"source/{c}/standardize/{C}_deputies.csv")
    dep, _ = leer(dep_p)
    col_nom = "speaker_name" if "speaker_name" in dep.columns else "nombre_completo"
    ids = set(dep.id_dep)
    info = {}
    for _, r in dep.iterrows():
        info.setdefault(r.id_dep, (r[col_nom], r.get("sex", ""), r.get("party", ""), r.get("district", "")))

    m, sep = leer(f"source/{c}/standardize/{C}_interventions.csv")
    # ⚠ CONJUNTO de ids por forma, no uno: la clave real es (speaker_raw, date) y una misma
    # forma la usan varias personas en períodos distintos. Ver la nota del encabezado.
    ya: dict[str, set] = {}
    for s, i in zip(m.speaker_raw, m.id_dep):
        if i:
            ya.setdefault(s, set()).add(i)

    inexistentes = sorted({i for i in mp.values() if i not in ids})
    contradicen = [(s, "/".join(sorted(ya[s])[:3]), j) for s, j in mp.items()
                   if s in ya and j not in ya[s]]
    nuevos = {s: j for s, j in mp.items() if s not in ya and j in ids}
    n_filas = int(m.speaker_raw.isin(nuevos).sum())
    vacias = len(hoja) - len(mp)
    # formas que la hoja resuelve pero que YA tienen id en parte de sus filas: el import no las
    # toca —rellenarlas con un solo id sería falso cuando la forma la usan varias personas—.
    huecos = m[(m.id_dep == "") & (m.speaker_raw.isin(ya))].speaker_raw
    parciales = huecos[huecos.isin(mp)].value_counts()

    print(f"── {C} · revisión manual: {len(hoja):,} formas ──")
    print(f"  con id_dep         : {len(mp):,}")
    print(f"  dejadas EN BLANCO  : {vacias:,}   (se respetan: no se reintentan)")
    print(f"  formas NUEVAS      : {len(nuevos):,}  → {n_filas:,} filas del corpus")
    print(f"  id_dep INEXISTENTES: {len(inexistentes)}" + (f"  {inexistentes[:6]}" if inexistentes else ""))
    print(f"  CONTRADICEN lo automático: {len(contradicen)}")
    for s, x, y in contradicen[:8]:
        print(f"     {s[:34]!r:38} {x} → {y}")
    if contradicen:
        print("     ⚠ revísalas: puede ser corrección deliberada o un arrastre de celdas")
    if len(parciales):
        print(f"  formas PARCIALMENTE vinculadas que la hoja resuelve: {len(parciales):,}"
              f"  → {int(parciales.sum()):,} filas vacías que este import NO rellena")
        for s, n in parciales.head(4).items():
            print(f"     {s[:34]!r:38} {n:,} vacías · {len(ya[s])} id automáticos")
        print("     (rellenarlas pide el árbitro de mandato, no un id único: ver README)")
    if inexistentes:
        print("\n  ✗ hay id_dep que no existen en el padrón — corrígelos antes de aplicar")
        return
    if o.dry_run:
        print("\n  [dry-run] no se ha escrito nada.")
        return

    bak = f"source/{c}/standardize/{C}_interventions.pre_manual.csv"
    if not Path(bak).exists():
        shutil.copy2(f"source/{c}/standardize/{C}_interventions.csv", bak)
        print(f"  copia de seguridad → {Path(bak).name}")
    antes = int((m.id_dep != "").sum())
    for k, (s, i) in enumerate(zip(m.speaker_raw, m.id_dep)):
        if i or s not in nuevos:
            continue
        j = nuevos[s]
        m.at[k, "id_dep"] = j
        nom, sx, pa, di = info.get(j, ("", "", "", ""))
        m.at[k, "speaker_name"] = nom
        if sx:
            m.at[k, "sex"] = sx
        if not m.at[k, "party"]:
            m.at[k, "party"] = pa
        if not m.at[k, "district"]:
            m.at[k, "district"] = di
    m.to_csv(f"source/{c}/standardize/{C}_interventions.csv", sep=sep, index=False, encoding="utf-8")
    print(f"\n  ✓ vinculación {100*antes/len(m):.2f}% → {100*(m.id_dep!='').mean():.2f}%")
    print(f"    huérfanos {len(set(m[m.id_dep!=''].id_dep) - ids)} · "
          f"personas {m[m.id_dep!=''].id_dep.nunique():,}")


if __name__ == "__main__":
    main()
