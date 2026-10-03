#!/usr/bin/env python3
"""CO: la apertura del acta se etiquetó como la intervención de orden 1. No es habla.

Señalado por el investigador (2026-08-10) como el fallo más grave que había encontrado:

    orden 1 · speaker_raw = «Presidencia de los honorables Representantes»
    texto    = «Armando Pomárico Ramos, Luis Norberto Guerra Vélez… En Santa Fe de Bogotá,
                D. C., Sede Constitucional del Congreso de la República a los 21 días del mes
                de marzo de 2000, siendo las 4:10 p.m., se reunieron en el Salón Elíptico…»

El `speaker_raw` es una **línea de cabecera** —la que nombra a quien preside—, no un orador, y el
texto es la apertura formal más el pase de lista. Son **127 filas**, y en 105 la cabecera es
literalmente «Presidencia de los honorables Representantes».

## Por qué se mueve entero al Prolegomena

Busqué la transición narración → habla («abre su discusión:», «tiene la palabra…:») para partir
la fila y salvar el habla del final. **Solo 1 de las 127 la tiene.** Sin marca fiable, partir por
heurística sería inventar. Así que el texto **se traslada al Prolegomena de su jornada** —con
`intervention_order = 0` y `dm_speech = 0`— y la fila desaparece como intervención.

Nada se pierde: el texto sigue en el corpus, incluidos los nombres de quienes presiden, que van
en la propia cabecera y son de los pocos sitios donde constan ([[feedback_prolegomena]]). Lo que
se corrige es la ATRIBUCIÓN: 127 intervenciones que nadie pronunció.

En la única fila con transición explícita sí se parte: la narración va al Prolegomena y el habla
se queda como intervención.

CLI:
    python co_prolegomena_en_orden1.py [--medir]
"""
import argparse
import csv
import os
import re
import sys
from collections import defaultdict

csv.field_size_limit(sys.maxsize)
CORPUS = "source/co/standardize/CO_interventions.csv"

# firma de la apertura formal del acta, no del habla
APERTURA = re.compile(r"(?i)se reunieron en el Sal[óo]n|siendo las .{0,12}(?:a\.?m|p\.?m)|"
                      r"Sede Constitucional del Congreso")
# transición explícita narración → habla; solo aparece en 1 de las 127
TRANSICION = re.compile(r"(?i)(?:abre su discusi[óo]n|tiene la palabra(?: el| la)?[^:\n]{0,40}|"
                        r"se le concede el uso de la palabra[^:\n]{0,30})\s*:")


def _lee(p):
    with open(p, encoding="utf-8") as fh:
        d = csv.Sniffer().sniff(fh.readline(), ";,").delimiter
        fh.seek(0)
        r = csv.DictReader(fh, delimiter=d)
        return list(r.fieldnames), list(r), d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--medir", action="store_true")
    a = ap.parse_args()
    campos, filas, d = _lee(CORPUS)

    porjor = defaultdict(list)
    for i, x in enumerate(filas):
        porjor[(x["legislature"], x["date"])].append(i)
    prole = {}
    for k, idx in porjor.items():
        for i in idx:
            if filas[i]["intervention_order"] == "0":
                prole[k] = i
                break

    mover, partir = [], []
    for k, idx in porjor.items():
        for i in idx:
            x = filas[i]
            if x["intervention_order"] != "1":
                continue
            if not APERTURA.search(x["text"][:1200]):
                continue
            m = list(TRANSICION.finditer(x["text"]))
            (partir if m else mover).append((k, i, m[-1].end() if m else 0))

    print(f"  CO · apertura del acta etiquetada como intervención: {len(mover) + len(partir)} filas")
    print(f"     se trasladan enteras al Prolegomena: {len(mover)}")
    print(f"     se parten (narración → Prolegomena, habla → intervención): {len(partir)}")
    if a.medir:
        for k, i, _ in mover[:3]:
            print(f"       [{k[1]}] {filas[i]['speaker_raw'][:44]!r} · {len(filas[i]['text']):,} car.")
        return

    quitar = set()
    nuevos = {}
    for k, i, corte in mover + partir:
        x = filas[i]
        cab = x["speaker_raw"].strip()
        trozo = (cab + ". " if cab else "") + (x["text"][:corte] if corte else x["text"])
        j = prole.get(k)
        if j is not None:
            filas[j]["text"] = (filas[j]["text"].rstrip() + "\n" + trozo).strip()
        else:
            y = {c: "" for c in campos}
            for c in ("legislature", "session_number", "date", "session_type"):
                y[c] = x.get(c, "")
            y["intervention_order"], y["dm_speech"], y["text"] = "0", "0", trozo
            nuevos[i] = y
        if corte:
            x["text"] = x["text"][corte:].strip()
            x["speaker_raw"] = ""      # el orador real no consta; queda por resolver
        else:
            quitar.add(i)

    salida = []
    for i, x in enumerate(filas):
        if i in nuevos:
            salida.append(nuevos[i])
        if i not in quitar:
            salida.append(x)
    cnt = defaultdict(int)
    for y in salida:
        if y["intervention_order"] == "0":
            continue
        kk = (y.get("legislature", ""), y["date"], y.get("session_number", "").strip())
        cnt[kk] += 1
        y["intervention_order"] = str(cnt[kk])

    bak = CORPUS.replace(".csv", ".pre_prolorden1.csv")
    tmp = CORPUS + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, delimiter=d)
        w.writeheader()
        w.writerows(salida)
    if not os.path.exists(bak):
        os.rename(CORPUS, bak)
    else:
        os.remove(CORPUS)
    os.rename(tmp, CORPUS)
    print(f"  ✓ corpus {len(filas):,} → {len(salida):,} filas · Prolegomena nuevos {len(nuevos)}")


if __name__ == "__main__":
    main()
