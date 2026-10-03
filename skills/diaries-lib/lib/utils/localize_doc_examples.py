#!/usr/bin/env python3
"""Sustituye los ejemplos de la plantilla por datos reales de cada país.

Once de los quince `docs/{iso2}/data_dictionary.md` llevan verbatim los ejemplos de
Portugal —`PT0042`, `Pedro Nuno Santos`, `Porto`, `PS`—, porque la plantilla nunca se
particularizó. Un corpus español que documenta un identificador portugués es un defecto
de publicación, no cosmético: quien lea el diccionario para saber qué forma tiene
`id_dep` en ese país obtiene la respuesta equivocada.

Se toma una fila REAL del canónico de cada país —la primera con `id_dep`, `party` y
`district` no vacíos— y se sustituye **solo la columna «Example»** de la tabla, sin
tocar las descripciones.

Uso:  python3 particularizar_ejemplos_docs.py [--apply]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

PAISES = ["ar", "br", "cl", "co", "cr", "do", "es", "gt", "mx", "pa", "pe", "pt", "py", "sv", "uy"]
COLS = ["legislature", "session_number", "date", "session_type", "intervention_order",
        "speaker_raw", "id_dep", "speaker_name", "sex", "party", "district", "text"]


def muestra(iso2: str) -> dict[str, str]:
    """Una fila REAL y representativa del canónico.

    No se exige `district`: CL no lo registra —no consta en la fuente— y exigirlo dejaba
    a Chile sin ejemplos. Y se prefiere una fila cuyo `speaker_raw` contenga de verdad
    el nombre de la persona: en varios corpus hay marcadores que son solo el cargo
    (`SECRETARIA`), y como ejemplo de documentación despistan más que ilustran.
    """
    reserva = {}
    for tr in pd.read_csv(f"source/{iso2}/standardize/{iso2.upper()}_interventions.csv",
                          dtype=str, keep_default_na=False, chunksize=20000):
        ok = tr[(tr.id_dep.str.strip() != "") & (tr.party.str.strip() != "")
                & (tr.legislature.str.strip() != "")]
        if not len(ok):
            continue
        if not reserva:
            reserva = ok.iloc[0].to_dict()
        # ¿el marcador comparte alguna palabra larga con el nombre normalizado?
        for _, r in ok.iterrows():
            pal = {w.lower() for w in re.findall(r"\w{4,}", r.speaker_name)}
            if pal & {w.lower() for w in re.findall(r"\w{4,}", r.speaker_raw)}:
                reserva = r.to_dict()
                break
        else:
            continue
        break
    if reserva:
        reserva["text"] = (reserva.get("text", "")[:60].strip() + "…") if reserva.get("text") else ""
    return reserva


def main(apply: bool) -> None:
    for c in PAISES:
        p = Path(f"docs/{c}/data_dictionary.md")
        if not p.exists():
            continue
        m = muestra(c)
        if not m:
            print(f"{c.upper():4} sin fila completa en el canónico — se deja como está")
            continue

        lineas, cambios = p.read_text(encoding="utf-8").split("\n"), 0
        for i, ln in enumerate(lineas):
            g = re.match(r"^(\|\s*\d+\s*\|\s*`(\w+)`\s*\|.*\|)([^|]*)\|\s*$", ln)
            if not g or g.group(2) not in COLS:
                continue
            v = str(m.get(g.group(2), "")).replace("|", "/").replace("\n", " ").strip()
            nuevo = f"{g.group(1)} `{v}` |" if v else f"{g.group(1)} |"
            if nuevo != ln:
                lineas[i] = nuevo
                cambios += 1
        print(f"{c.upper():4} {cambios:2} ejemplos particularizados "
              f"· id_dep={m.get('id_dep')!r} district={m.get('district')!r}")
        if apply:
            p.write_text("\n".join(lineas), encoding="utf-8")

    if not apply:
        print("\n--- SIMULACIÓN --- (usa --apply para escribir)")


if __name__ == "__main__":
    main("--apply" in sys.argv)
