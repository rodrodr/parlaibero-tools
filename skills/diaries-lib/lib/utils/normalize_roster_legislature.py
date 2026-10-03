#!/usr/bin/env python3
"""Saca la legislatura de `notes`, la pone en su columna y pasa el padrón a formato LARGO.

**Qué estaba mal.** En 9 de los 15 padrones publicados la columna `legislature` estaba **vacía
en todas las filas** mientras el dato vivía dentro de `notes`: como romanos sueltos (`IX,X` en
GT), o bajo una clave (`legislature:1998-2003` en PY y UY, `periodos:2003 - 2005, 2003 - 2007`
en AR). Dos defectos encadenados:

  1. **Columna equivocada.** `notes` es texto libre; nadie puede unir, filtrar ni agrupar por
     ella. Una variable de análisis no se guarda en el cajón de sastre.
  2. **Varias observaciones en una celda.** `IX,X` en una sola fila dice que esa persona estuvo
     en dos legislaturas, pero obliga a cada usuario a partir la cadena por su cuenta. La unidad
     de observación del padrón es **la persona EN una legislatura**, no la persona: es lo que
     permite que el partido, el distrito y el grupo cambien de una a otra.

Tras pasar por aquí, `id_dep` **deja de ser único** —hay una fila por `(id_dep, legislature)`—
y las uniones con la matriz deben hacerse por **`id_dep` + `legislature`**, no solo por `id_dep`.
Seis de los quince padrones (BR, CL, CO, ES, MX, PT…) ya estaban en formato largo, así que esto
los alinea a todos.

⚠ **Lo que NO hace: inventar.** Si de `notes` no sale ninguna legislatura, la fila se queda como
está y se cuenta aparte. En CL, CO y PA la columna está vacía y `notes` tampoco la trae: ahí el
dato hay que recuperarlo de la fuente, en el reproceso del país.

⚠ **El resto de `notes` se conserva.** Solo se borra el fragmento que era la legislatura; si la
celda contenía además `tipo:TITULAR | url:…`, eso sigue ahí.

Uso:
    python3 normalize_roster_legislature.py --csv source/gt/standardize/GT_deputies.csv --dry-run
    python3 normalize_roster_legislature.py --csv source/gt/standardize/GT_deputies.csv --apply
"""
from __future__ import annotations

import argparse
import csv as _csv
import re
import shutil
from pathlib import Path

import pandas as pd

# Romanos sueltos, la forma de GT: `IX`, `IX,X`, `VI, VII, VIII`
SOLO_ROMANOS = re.compile(r"^\s*[IVXLC]+(?:\s*,\s*[IVXLC]+)*\s*$")
# Bajo clave, la forma de AR/PY/UY/DO/PE: `legislature:1998-2003`, `periodos:1983 - 1985, …`
BAJO_CLAVE = re.compile(
    r"(?:^|\|\s*|;\s*)(?:legislature|legislatura|periodos?|per[ií]odos?)s?\s*[:=]\s*([^|;]+)",
    re.I,
)


def separar(notes: str) -> tuple[list[str], str]:
    """Devuelve (legislaturas, notes sin ellas). Lista vacía si no hay nada que sacar."""
    n = (notes or "").strip()
    if not n:
        return [], ""
    if SOLO_ROMANOS.match(n):                       # la celda ENTERA era la legislatura
        return [x.strip() for x in n.split(",") if x.strip()], ""
    m = BAJO_CLAVE.search(n)
    if m:
        legs = [x.strip() for x in m.group(1).split(",") if x.strip()]
        resto = (n[:m.start()] + n[m.end():]).strip(" |;\t")
        resto = re.sub(r"\s*[|;]\s*[|;]\s*", " | ", resto).strip(" |;")
        return legs, resto
    return [], n


def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument("--csv", required=True)
    a.add_argument("--apply", action="store_true")
    a.add_argument("--dry-run", action="store_true")
    o = a.parse_args()
    if not (o.apply or o.dry_run):
        raise SystemExit("✗ elige --dry-run o --apply")

    p = Path(o.csv)
    with p.open(encoding="utf-8") as fh:
        sep = _csv.Sniffer().sniff(fh.readline(), ";,\t").delimiter
    d = pd.read_csv(p, sep=sep, dtype=str, keep_default_na=False)

    # Los padrones internos van en español (`notas`, `legislatura`) y los publicados en inglés.
    # Sin esto la utilidad creaba columnas vacías y daba «0 recuperadas» sobre un fichero que
    # sí tenía el dato: un falso negativo silencioso, del tipo que este proyecto ya ha pagado.
    ALIAS = {"notas": "notes", "legislatura": "legislature", "legislaturas": "legislature"}
    col_leg, col_not = "legislature", "notes"
    for es, en in ALIAS.items():
        if es in d.columns and en not in d.columns:
            (col_leg, col_not) = (es, col_not) if en == "legislature" else (col_leg, es)
    d = d.rename(columns={col_leg: "legislature", col_not: "notes"})
    devolver = {"legislature": col_leg, "notes": col_not}   # para escribir con su nombre original
    for c in ("legislature", "notes"):
        if c not in d.columns:
            d[c] = ""

    filas, sin, con = [], 0, 0
    for _, r in d.iterrows():
        legs, resto = separar(r.notes)
        if not legs:
            # ya tenía legislatura propia, o no hay de dónde sacarla
            sin += 0 if r.legislature else 1
            filas.append(dict(r))
            continue
        con += 1
        for lg in legs:
            x = dict(r)
            x["legislature"] = lg
            x["notes"] = resto
            filas.append(x)

    out = pd.DataFrame(filas)[list(d.columns)].rename(
        columns={k: v for k, v in devolver.items() if k != v})
    print(f"── {p.name} ──")
    print(f"  antes  : {len(d):>7,} filas · {d.id_dep.nunique():,} personas · "
          f"legislature vacía {int((d.legislature=='').sum()):,}")
    print(f"  después: {len(out):>7,} filas · {out.id_dep.nunique():,} personas · "
          f"legislature vacía {int((out[devolver['legislature']]=='').sum()):,}")
    print(f"  filas con legislatura recuperada de `notes`: {con:,}")
    if sin:
        print(f"  ⚠ {sin:,} filas se quedan SIN legislatura: no está en `notes`. "
              f"Hay que recuperarla de la fuente, no inventarla.")
    print(f"  legislaturas: {sorted(x for x in out[devolver['legislature']].unique() if x)[:12]}")

    if o.dry_run:
        print("\n  [dry-run] no se ha escrito nada.")
        return
    bak = p.with_name(p.stem + ".pre_legislature.csv")
    if not bak.exists():
        shutil.copy2(p, bak)
        print(f"  copia de seguridad → {bak.name}")
    out.to_csv(p, sep=sep, index=False, encoding="utf-8")
    print(f"  ✓ escrito {p.name}")
    print("  ⚠ `id_dep` ya NO es único: une por `id_dep` + `legislature`.")


if __name__ == "__main__":
    main()
