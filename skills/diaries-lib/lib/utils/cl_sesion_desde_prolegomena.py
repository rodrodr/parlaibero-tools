#!/usr/bin/env python3
"""CL: número y tipo de sesión leídos del Prolegomena, con tolerancia al OCR.

Señalado por el investigador (2026-08-10). La cabecera del acta lo trae todo en una línea:

    Sesión 2a., en martes 20 de marzo de 1990. (Ordinaria, de 16 a 18.12 horas)
    Sesión de instalación, en 11 de marzo de 1990.

El OCR degrada esa línea de formas muy concretas, y son las que hay que tolerar —el investigador
las enumeró—: «sesion», «sesi6n», «Sesión la.» por «Sesión 1ª» (la ele por el uno), «Ordlnaria»
por «Ordinaria», y el tipo entre paréntesis con coma, con punto o con espacio de más:
`(Ordinaria, de …)` · `(Ordinaria. de …)` · `( Ordinaria)` · `(Ordinaria)`.

**No sobreescribe a ciegas**: solo rellena lo que está vacío y REPORTA las discrepancias con lo
ya registrado, que es donde hay que mirar antes de decidir.

CLI:
    python cl_sesion_desde_prolegomena.py [--medir] [--rellenar] [--forzar]
"""
import argparse
import csv
import os
import re
import sys
import unicodedata
from collections import Counter

csv.field_size_limit(sys.maxsize)
CORPUS = "source/cl/standardize/CL_interventions.csv"

# «sesión» con sus degradaciones: la ó puede salir como 0/6/o, y la i como 1/l
_SESION = r"[Ss]es[il1][o0óôö6][n]"
# El ordinal puede venir en cifras («2a.», «31ª») o con la ele que el OCR pone por el uno («la.»)
# El ordinal puede no tener NI UN dígito: el OCR escribe «Sesión lOa.» por «Sesión 10a.» —ele
# por uno y O mayúscula por cero—. Por eso se aceptan los sosias tipográficos y se traducen.
_SOSIA = str.maketrans({"l": "1", "I": "1", "|": "1", "O": "0", "o": "0", "S": "5", "B": "8"})
NUM = re.compile(rf"{_SESION}\s*[Nn]?[°º]?\.?\s*([0-9lIO|SB]{{1,3}})\s*[ªaº°]\.?", re.I)
INSTAL = re.compile(rf"{_SESION}\s+de\s+[il1]nstalac[il1][o0óô]n", re.I)

# El tipo va entre paréntesis; se tolera espacio inicial, y coma o punto antes de la hora.
# «Ordlnaria» y «Extraordlnaria» son la i leída como ele.
_TIPOS = [
    ("ordinaria",     r"ord[il1]nar[il1]a"),
    ("extraordinaria", r"extraord[il1]nar[il1]a"),
    ("especial",      r"espec[il1]al"),
    ("solemne",       r"solemne"),
    ("congreso pleno", r"congreso\s+pleno"),
]
TIPO = [(n, re.compile(rf"\(\s*{p}\s*[.,)]", re.I)) for n, p in _TIPOS]


def lee_cabecera(t: str):
    """Devuelve (numero, tipo) leídos de la cabecera del Prolegomena.

    ⚠ La ventana es CORTA a propósito. Buscando en 1.200 caracteres se enganchaba una mención
    posterior —«el acta de la sesión 1ª»— y el número salía mal: 1990-04-18 daba 1 en vez de 10.
    La cabecera termina donde empieza «Presidencia de…», así que ahí se corta.
    """
    cab = t[:1200]
    corte = re.search(r"Presidenc[il1]a\s+de", cab, re.I)
    cab = cab[:corte.start()] if corte else cab[:400]
    num = tipo = ""
    if INSTAL.search(cab):
        tipo = "instalación"
        num = "1"
    m = NUM.search(cab)
    if m:
        crudo = m.group(1).translate(_SOSIA)
        if crudo.isdigit():
            num = str(int(crudo))
    for n, rx in TIPO:
        if rx.search(cab):
            tipo = n
            break
    return num, tipo


def _lee(p):
    with open(p, encoding="utf-8") as fh:
        d = csv.Sniffer().sniff(fh.readline(), ";,").delimiter
        fh.seek(0)
        r = csv.DictReader(fh, delimiter=d)
        return list(r.fieldnames), list(r), d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--medir", action="store_true")
    ap.add_argument("--rellenar", action="store_true", help="escribe solo donde está vacío")
    ap.add_argument("--forzar", action="store_true", help="además, corrige las discrepancias")
    a = ap.parse_args()
    campos, filas, d = _lee(CORPUS)

    pro = {}
    for x in filas:
        if x["intervention_order"] == "0":
            pro[(x["legislature"], x["date"])] = x["text"]

    leido, coincide, difiere, vacio = {}, Counter(), [], Counter()
    for k, t in pro.items():
        n, ti = lee_cabecera(t)
        if n or ti:
            leido[k] = (n, ti)
    act = {}
    for x in filas:
        act.setdefault((x["legislature"], x["date"]), x)
    for k, (n, ti) in leido.items():
        x = act.get(k)
        if not x:
            continue
        for campo, val in (("session_number", n), ("session_type", ti)):
            if not val:
                continue
            cur = x[campo].strip()
            # ⚠ «3a» y «3» NO son una discrepancia: el acta imprime el ordinal y el esquema
            # admite alfanumérico, así que el corpus está bien y quien normaliza de más es la
            # lectura. Comparar en crudo daba 910 falsas diferencias.
            if campo == "session_number" and cur and re.fullmatch(r"\d{1,3}\s*[ªaAº°]?\.?", cur) \
               and re.sub(r"\D", "", cur) == val:
                coincide[campo] += 1
                continue
            if not cur:
                vacio[campo] += 1
            elif cur == val:
                coincide[campo] += 1
            else:
                difiere.append((k[1], campo, cur, val))

    print(f"  CL · Prolegomena con cabecera legible: {len(leido):,} de {len(pro):,}")
    for campo in ("session_number", "session_type"):
        dif = sum(1 for x in difiere if x[1] == campo)
        print(f"     {campo:15} coincide {coincide[campo]:>5,} · rellena hueco {vacio[campo]:>4,}"
              f" · DIFIERE {dif:>5,}")
    if difiere:
        print("\n     discrepancias (registrado → leído del acta):")
        for f, c, cur, val in difiere[:10]:
            print(f"       [{f}] {c}: {cur!r} → {val!r}")
    if a.medir or not (a.rellenar or a.forzar):
        return

    esc = 0
    for x in filas:
        k = (x["legislature"], x["date"])
        if k not in leido:
            continue
        n, ti = leido[k]
        for campo, val in (("session_number", n), ("session_type", ti)):
            if not val:
                continue
            if not x[campo].strip() or (a.forzar and x[campo].strip() != val):
                x[campo] = val
                esc += 1
    bak = CORPUS.replace(".csv", ".pre_sesion.csv")
    tmp = CORPUS + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, delimiter=d)
        w.writeheader()
        w.writerows(filas)
    if not os.path.exists(bak):
        os.rename(CORPUS, bak)
    else:
        os.remove(CORPUS)
    os.rename(tmp, CORPUS)
    print(f"  ✓ {esc:,} celdas escritas")


if __name__ == "__main__":
    main()
