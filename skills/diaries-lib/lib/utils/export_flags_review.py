#!/usr/bin/env python3
"""Prepara para revisión humana SOLO los FLAG donde el criterio humano aporta algo.

De los 363 FLAG de la validación, **315 no necesitan ojo humano**: son huecos del padrón
—orador nombrado sin `id_dep` (210) y sin mandato en la legislatura (105)—, y la regla del
proyecto ya dice qué hacer con ellos: la intervención se mantiene, el defecto se documenta
(validation_methodology §4.6). Triados automáticamente, el **96%** son personas que no
figuran en el padrón; solo 9 serían recuperables por el matcher.

Quedan **64 filas** en tres clases donde ninguna regla puede decidir:

- **marcador de otro orador en el `text`** (44) — ¿turno de palabra ajeno o cita?
- **cadena de firmas** (15) — ¿discurso o el pie de un proyecto con sus autores?
- **caracteres corrompidos** (5) — ¿cuánto texto se pierde de verdad?

Se recorta el **contexto alrededor del hallazgo** (±220 caracteres) en vez de volcar la
intervención entera: lo que hay que juzgar es el punto concreto, no leerse el discurso.
El texto completo queda en `texto_completo` por si hace falta.

Uso:  python3 scripts/validacion/preparar_revision_flags.py
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).parent))
# ⚠ Importa de `validate_structural`, la utilidad GLOBAL, no de `scripts/validacion/validar.py`,
# que es la copia del proyecto anterior a la promoción del código. Con el import viejo esto
# reventaba con ModuleNotFoundError en cuanto se ejecutaba: mismo defecto que el runner de OCR
# apuntando a un lib/utils/ que ya no existe. Un módulo promovido tiene que arrastrar sus imports.
from validate_structural import (MARCADOR, GUION_DELANTE, FIRMAS, CORRUPTO,  # noqa: E402
                                 norm_acentos)

PAISES = ["ar", "br", "cl", "co", "cr", "do", "es", "gt", "mx", "pa", "pe", "pt", "py", "sv", "uy"]
SALIDA = Path("docs/validacion/revision_flags")
VENTANA = 220

CLASES = {
    "marcador(es) en el text": "marcador_ajeno",
    "cadena de firmas": "cadena_firmas",
    "caracteres corrompidos": "texto_corrompido",
}


def contexto(txt: str, clase: str) -> str:
    """Recorta alrededor del hallazgo, para no obligar a leer la intervención entera."""
    pats = {"marcador_ajeno": [MARCADOR, GUION_DELANTE],
            "cadena_firmas": [FIRMAS], "texto_corrompido": [CORRUPTO]}[clase]
    for pat in pats:
        m = pat.search(txt) or pat.search(norm_acentos(txt))
        if m:
            i, j = m.span()
            ini, fin = max(0, i - VENTANA), min(len(txt), j + VENTANA)
            return (("…" if ini else "") + txt[ini:fin] + ("…" if fin < len(txt) else "")
                    ).replace("\n", " ⏎ ")
    return txt[:2 * VENTANA].replace("\n", " ⏎ ")


def main() -> None:
    filas = []
    for c in PAISES:
        m = pd.read_csv(f"docs/validacion/{c.upper()}_muestra.csv", dtype=str,
                        keep_default_na=False)
        for _, r in m[m.veredicto == "FLAG"].iterrows():
            for etiqueta, clase in CLASES.items():
                if etiqueta in r.motivos:
                    filas.append({
                        "pais": c.upper(), "clase": clase,
                        "date": r.date, "session_number": r.session_number,
                        "intervention_order": r.intervention_order,
                        "speaker_raw": r.speaker_raw, "id_dep": r.id_dep,
                        "speaker_name": r.speaker_name,
                        "que_decidir": {"marcador_ajeno": "¿turno de palabra ajeno, o una cita?",
                                        "cadena_firmas": "¿discurso, o el pie de un proyecto?",
                                        "texto_corrompido": "¿cuánto texto se pierde?"}[clase],
                        "CONTEXTO": contexto(r.text, clase),
                        "ES_DEFECTO": "", "NOTA": "",
                        "n_caracteres": len(r.text), "texto_completo": r.text,
                    })
                    break

    d = pd.DataFrame(filas).sort_values(["clase", "pais"]).reset_index(drop=True)
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    d.to_csv(SALIDA.with_suffix(".csv"), index=False, encoding="utf-8")

    try:
        from numbers_parser import Document
        doc = Document()
        t = doc.sheets[0].tables[0]
        t.name = "revision_flags"
        for j, col in enumerate(d.columns):
            t.write(0, j, str(col))
        for i, fila in enumerate(d.itertuples(index=False), start=1):
            for j, v in enumerate(fila):
                t.write(i, j, "" if v is None else str(v))
        doc.save(SALIDA.with_suffix(".numbers"))
        fmt = "Numbers + CSV"
    except Exception as e:                       # pragma: no cover
        fmt = f"solo CSV ({type(e).__name__})"

    print(f"{len(d)} filas para revisión humana · {fmt}")
    for k, v in d.clase.value_counts().items():
        print(f"  {v:3}  {k}")
    print(f"\n  → {SALIDA.with_suffix('.numbers')}")
    print("\nMarcar ES_DEFECTO = «sí» si la fila está mal; en blanco si está bien.")


if __name__ == "__main__":
    main()
