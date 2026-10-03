#!/usr/bin/env python3
"""Agrupa las variantes de OCR de un mismo `speaker_raw` y las lleva a una forma canónica.

**Por qué existe.** Un patrón de orador tolerante a la corrupción del OCR —imprescindible en
corpus mal escaneados— tiene un coste inmediato: cada errata se convierte en un orador nuevo.
En ES, tolerar la basura del OCR de 1977-1979 recuperó 13.485 marcadores que se perdían, pero
los `speaker_raw` distintos pasaron de 4.690 a 9.984, porque `PRESIjDENTE`, `PREiSDENTE`,
`PRESIIDENTE` y `PRB91DENTmE` son cuatro cadenas para el mismo cargo. No es un error del dato
—el acta dice eso— pero si llega así al matching, la vinculación sale artificialmente baja y
lleva a diagnosticar un problema de padrón que no existe.

**Cómo agrupa, de lo seguro a lo arriesgado:**

  1. **Esqueleto**: versales sin acentos, sin dígitos ni signos, espacios colapsados. Junta
     `PRES1,DENTE` con `PRESIDENTE` sin ninguna decisión difusa. Es la mayoría de los casos.
  2. **Difuso contra las formas FRECUENTES**: una forma rara se asimila a una frecuente solo si
     la similitud supera `--min-sim` **y** le saca `--margen` puntos a la segunda candidata. Sin
     el margen, dos apellidos parecidos y ambos reales se funden — que es el error que hay que
     evitar por encima de recuperar una variante.

⚠ **La forma canónica es la MÁS FRECUENTE del grupo, no la primera ni la más corta.** Con OCR, la
lectura correcta es casi siempre la que más se repite; la corrupta aparece pocas veces.

⚠ **Nunca se funden dos formas ambas FRECUENTES.** Si las dos superan `--min-freq` se consideran
personas distintas aunque se parezcan: `MARTINEZ GARCIA` y `MARTINEZ GRACIA` pueden ser dos
diputados. La duda se resuelve NO agrupando, y el par queda en el informe.

Uso:
    python3 normalize_ocr_speakers.py --matrix source/es/matrix/interventions_raw.csv --dry-run
    python3 normalize_ocr_speakers.py --matrix … --apply --out-map docs/es/variantes_ocr.csv
"""
from __future__ import annotations

import argparse
import csv as _csv
import re
import unicodedata as U
from collections import Counter, defaultdict

import pandas as pd

try:
    from rapidfuzz import fuzz, process as rf
except ImportError:
    fuzz = rf = None


def esqueleto(s: str) -> str:
    """Versales sin acentos, sin dígitos ni signos. `PRES1,DENTE` → `PRESIDENTE`."""
    s = U.normalize("NFD", s.upper())
    s = "".join(c for c in s if U.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^A-ZÑ ]", "", s)).strip()


def leer(p: str) -> pd.DataFrame:
    with open(p, encoding="utf-8") as fh:
        d = _csv.Sniffer().sniff(fh.readline(), ";,\t").delimiter
    return pd.read_csv(p, sep=d, dtype=str, keep_default_na=False), d


def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument("--matrix", required=True)
    a.add_argument("--apply", action="store_true")
    a.add_argument("--dry-run", action="store_true")
    a.add_argument("--out-map", default="")
    a.add_argument("--min-freq", type=int, default=20,
                   help="a partir de aquí una forma se considera FRECUENTE y no se asimila")
    a.add_argument("--min-sim", type=float, default=92.0)
    a.add_argument("--margen", type=float, default=6.0,
                   help="ventaja mínima sobre la 2ª candidata; sin margen no se agrupa")
    o = a.parse_args()
    if not (o.apply or o.dry_run):
        raise SystemExit("✗ elige --dry-run o --apply")

    d, sep = leer(o.matrix)
    cuenta = Counter(d.speaker_raw)
    formas = [f for f in cuenta if f.strip()]

    # ── paso 1 · esqueleto ────────────────────────────────────────────────────────
    por_esq: dict[str, list] = defaultdict(list)
    for f in formas:
        por_esq[esqueleto(f)].append(f)
    mapa: dict[str, str] = {}
    n1 = 0
    for esq, grupo in por_esq.items():
        if len(grupo) < 2 or not esq:
            continue
        canon = max(grupo, key=lambda x: cuenta[x])   # la MÁS FRECUENTE, no la primera
        for f in grupo:
            if f != canon:
                mapa[f] = canon
                n1 += 1

    # ── paso 2 · difuso, solo raras contra frecuentes ─────────────────────────────
    n2 = 0
    dudosos = []
    if rf is not None:
        frecuentes = sorted({mapa.get(f, f) for f in formas if cuenta[f] >= o.min_freq})
        raras = [f for f in formas if f not in mapa and cuenta[f] < o.min_freq]
        for f in raras:
            top = rf.extract(esqueleto(f), [esqueleto(x) for x in frecuentes],
                             scorer=fuzz.ratio, limit=4)
            if not top or top[0][1] < o.min_sim:
                continue
            # ⚠ El margen existe para no confundir PERSONAS distintas, no para dudar entre dos
            # grafías de la misma. Si las candidatas empatadas apuntan al MISMO destino, no hay
            # ambigüedad que resolver: `MINISTRO DE HACIElNDA` competía consigo mismo escrito de
            # otra forma y el margen lo bloqueaba (98 vs 93). Se comparan los DESTINOS, no los
            # parecidos.
            cerca = [frecuentes[t[2]] for t in top if top[0][1] - t[1] < o.margen]
            destinos = {mapa.get(x, x) for x in cerca}
            if len(destinos) > 1:
                dudosos.append((f, cerca[0], top[0][1], top[1][1] if len(top) > 1 else 0))
                continue
            mapa[f] = mapa.get(frecuentes[top[0][2]], frecuentes[top[0][2]])
            n2 += 1

    filas_af = int(d.speaker_raw.isin(mapa).sum())
    print(f"── {o.matrix} ──")
    print(f"  formas distintas          : {len(formas):,}")
    print(f"  agrupadas por ESQUELETO   : {n1:,}")
    print(f"  agrupadas por DIFUSO      : {n2:,}")
    print(f"  sin agrupar por poco margen (a revisión): {len(dudosos):,}")
    print(f"  formas tras normalizar    : {len({mapa.get(f, f) for f in formas}):,}")
    print(f"  filas afectadas           : {filas_af:,}  ({100*filas_af/len(d):.2f}%)")
    if dudosos:
        print("\n  ejemplos NO agrupados por falta de margen (se prefiere no fundir):")
        for f, c, s1, s2 in dudosos[:6]:
            print(f"    {f[:34]!r:38} ~ {c[:30]!r:34} {s1:.0f} vs {s2:.0f}")
    ej = sorted(mapa.items(), key=lambda kv: -cuenta[kv[0]])[:8]
    print("\n  agrupaciones de más peso:")
    for f, c in ej:
        print(f"    {cuenta[f]:>5}× {f[:36]!r:40} → {c[:36]!r}")

    if o.out_map:
        pd.DataFrame([{"variante": k, "canonica": v, "n_filas": cuenta[k]}
                      for k, v in sorted(mapa.items())]).to_csv(
            o.out_map, sep=";", index=False, encoding="utf-8")
        print(f"\n  → mapa en {o.out_map}")

    if o.dry_run:
        print("\n  [dry-run] no se ha escrito la matriz.")
        return
    d["speaker_raw_ocr"] = d.speaker_raw            # la forma literal del acta NO se pierde
    d["speaker_raw"] = d.speaker_raw.map(lambda x: mapa.get(x, x))
    d.to_csv(o.matrix, sep=sep, index=False, encoding="utf-8")
    print(f"\n  ✓ escrito {o.matrix} · la forma literal se conserva en `speaker_raw_ocr`")


if __name__ == "__main__":
    main()
