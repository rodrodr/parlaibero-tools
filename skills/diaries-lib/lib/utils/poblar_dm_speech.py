#!/usr/bin/env python3
"""Puebla `dm_speech` con los 0 que están DEMOSTRADOS, y solo con ésos.

`dm_speech` es binaria: 1 = la fila es una intervención, 0 = no lo es. Sirve para FILTRAR el
corpus a habla parlamentaria con una sola condición. El principio es que **el 0 se pone donde
está probado**; el 1 es el resto, y significa exactamente «no se ha demostrado que no sea
discurso» — no «verificado como discurso». Esa asimetría hay que documentarla en el diccionario
de datos, porque es lo que el usuario del corpus necesita saber.

## Las cuatro fuentes de 0, todas verificadas mirando el contenido (2026-08-10)

1. **Prolegomena** — `intervention_order = 0`: carátula, sumario, índice y pase de lista que
   preceden a la primera intervención. Ya poblados: 35.235 filas ([[feedback_prolegomena]]).
2. **Sin orador** — ni `speaker_raw` ni `id_dep`. Sin orador no hay intervención atribuida, y eso
   no admite discusión. 9.570 filas (CL 5.988, ES 3.553, MX 26, UY 3).
3. **Recuentos de votación** — solo CL los tiene como forma propia: `VOTACIÓN AFIRMATIVA`,
   `VOTACIÓN NEGATIVA`, `ABSTENCIONES` (35.545 filas). El contenido es una lista de nombres
   —«Votaron por la afirmativa los siguientes señores diputados: …»—, no habla.
4. **Sumario e índice como fila propia** y **mobiliario de página**: ES `Sumario` (1.904),
   SV `Sumario` (389), PE `COMMENT` (3.113 · cabeceras `---PAGE 0001---`, URLs, «Es transcripción
   de la versión magnetofónica»).

## Lo que NO es motivo de 0, y por qué importa

**Secretarios, relatores, ministros y presidencia SON discurso** aunque no vinculen con el padrón:
PE `RELATOR` (69.968), PY `SECRETARIO (Administrativo)` (66.203), PA `SUBSECRETARIO GENERAL`
(37.686), CO `Secretario General, …` (25.246), PT `Primeiro-Ministro` (17.114), ES `MINISTRO DEL
INTERIOR` (2.481). Son personas hablando que no son diputados — un hueco de vinculación, no de
habla. Marcarlas 0 habría borrado del corpus toda la voz del Gobierno y de la Mesa.

El vocabulario de arriba está **descubierto midiendo** las formas frecuentes que nunca vinculan,
no adivinado ([[feedback_descubrir_marcadores]]).

CLI:
    python poblar_dm_speech.py --country cl [--medir]
"""
import argparse
import csv
import os
import sys
from collections import Counter

csv.field_size_limit(sys.maxsize)

# Formas de `speaker_raw` que NO son habla, descubiertas por país. Comparación exacta tras
# normalizar espacios: son etiquetas del propio diario, no nombres, así que no hay fuzzy.
NO_HABLA = {
    "cl": {"VOTACIÓN AFIRMATIVA", "VOTACIÓN NEGATIVA", "ABSTENCIONES"},
    "es": {"Sumario"},
    "sv": {"Sumario"},
    "pe": {"COMMENT"},
}


def _lee(p):
    with open(p, encoding="utf-8") as fh:
        d = csv.Sniffer().sniff(fh.readline(), ";,").delimiter
        fh.seek(0)
        r = csv.DictReader(fh, delimiter=d)
        return list(r.fieldnames), list(r), d


def motivo(x, formas):
    """Devuelve el motivo del 0, o None si la fila se queda en 1."""
    if x.get("intervention_order", "").strip() == "0":
        return "prolegomena"
    s = " ".join(x.get("speaker_raw", "").split())
    if s in formas:
        return "etiqueta_no_habla"
    if not s and not x.get("id_dep", "").strip():
        return "sin_orador"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", required=True)
    ap.add_argument("--medir", action="store_true")
    a = ap.parse_args()
    iso, I = a.country.lower(), a.country.upper()
    csvp = f"source/{iso}/standardize/{I}_interventions.csv"
    campos, filas, d = _lee(csvp)
    if "dm_speech" not in campos:
        print(f"  {I} · sin columna dm_speech")
        return
    formas = NO_HABLA.get(iso, set())

    c = Counter()
    for x in filas:
        mo = motivo(x, formas)
        c[mo or "_habla"] += 1
        if not a.medir:
            x["dm_speech"] = "0" if mo else "1"
    n = len(filas)
    cero = n - c["_habla"]
    print(f"  {I} · {n:,} filas · dm_speech=0 {cero:,} ({cero/n*100:.2f}%)")
    for k in ("prolegomena", "etiqueta_no_habla", "sin_orador"):
        if c[k]:
            print(f"     {k:18} {c[k]:>9,}")
    if a.medir:
        return
    bak = csvp.replace(".csv", ".pre_dmspeech.csv")
    tmp = csvp + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, delimiter=d)
        w.writeheader()
        w.writerows(filas)
    if not os.path.exists(bak):
        os.rename(csvp, bak)
    else:
        os.remove(csvp)
    os.rename(tmp, csvp)
    print("  ✓ corpus reescrito")


if __name__ == "__main__":
    main()
