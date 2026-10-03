#!/usr/bin/env python3
"""Recupera el nombre de quien preside desde el TEXTO EXTRAÍDO, no desde la matriz.

Idea del investigador (2026-08-11): *«mira en el texto extraído y no en la matriz»*. Y estaba ahí:
en BR el marcador de la fuente es `O SR. PRESIDENTE (Ramez Tebet) –` —con el nombre DENTRO— y la
matriz guardó solo `PRESIDENTE`. En 60 de 60 sesiones muestreadas el nombre seguía en
`corrected/`. **La información no se perdió en la extracción: se perdió al construir la matriz.**

## Por qué no basta con «un presidente por sesión»

La presidencia ROTA dentro de la sesión: en `d_2003-02-02` alternan «Henrique Eduardo Alves» (129
marcadores) y «João Paulo» (88). Asignar el más frecuente a toda la sesión metería 88 filas en la
persona equivocada — el error que ya cometimos en PT con Eurico de Melo.

## El ancla es el TEXTO de cada fila

Para cada fila sin `id`, se toman sus primeros caracteres normalizados, se buscan en el texto
fuente y se lee **hacia atrás** hasta el marcador más cercano. Así cada fila recibe el nombre de
quien la dijo, no el de quien más presidió ese día.

⚠ Guardarraíles: la firma del texto debe ser **unívoca** dentro del archivo (si aparece dos veces
no se sabe cuál es) y el marcador debe quedar **a menos de 400 caracteres** por delante — si está
más lejos, entre medias hay otra cosa y no es su marcador.

CLI:
    python presidencia_desde_fuente.py --country br [--medir] [--limite N]
"""
import argparse
import csv
import glob
import gzip
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict

csv.field_size_limit(sys.maxsize)

MARCADOR = {
    "br": re.compile(r"(?m)^[ \t]*(?:O|A)\s+SRA?[ªº.]{0,2}\s+PRESIDENT[EA]\s*\(([^)\n]{3,70})\)"),
}
# ⚠ La firma NO puede ser larga: el texto de la matriz ya NO es el de `corrected/` —después pasó
# limpieza de mobiliario, deshifenización y separación de turnos— así que cuanto más larga, más
# probable que algo haya cambiado dentro. Con 70 caracteres se localizaba el 22 %; con 34, el 78 %.
# El precio es más ambigüedad, y por eso la unicidad se sigue exigiendo.
FIRMA, VENTANA = 34, 400


def _N(s):
    s = "".join(c for c in unicodedata.normalize("NFD", str(s).upper())
                if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Z0-9]+", "", s)


def _lee(p):
    with open(p, encoding="utf-8") as fh:
        d = csv.Sniffer().sniff(fh.readline(), ";,").delimiter
        fh.seek(0)
        r = csv.DictReader(fh, delimiter=d)
        return list(r.fieldnames), list(r), d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", required=True)
    ap.add_argument("--medir", action="store_true")
    ap.add_argument("--limite", type=int, default=0, help="solo N sesiones, para sondear")
    a = ap.parse_args()
    iso, I = a.country.lower(), a.country.upper()
    rx = MARCADOR[iso]
    p = f"source/{iso}/standardize/{I}_interventions.csv"
    campos, filas, d = _lee(p)
    _, dep, _ = _lee(f"source/{iso}/standardize/{I}_deputies.csv")

    # ⚠ El acta nombra en CORTO —«João Paulo»— y el padrón guarda «João Paulo Cunha». Se indexa
    # también por subconjunto de tokens, exigiendo unicidad: si dos personas encajan, ninguna.
    porn = {}
    subs = defaultdict(set)
    for x in dep:
        for c in ("speaker_name", "last_name"):
            v = x.get(c, "").strip()
            if v:
                porn.setdefault(_N(v), x["id_dep"])
                subs[frozenset(t for t in re.sub(r"[^A-Za-zÀ-ÿ ]", " ", v).upper().split()
                               if len(t) > 2)].add(x["id_dep"])
    for x in filas:                                   # el corpus también sabe nombres
        if x["id_dep"].strip() and x["speaker_raw"].strip():
            porn.setdefault(_N(x["speaker_raw"]), x["id_dep"])
    atr = {}
    for x in dep:
        atr.setdefault(x["id_dep"], (x.get("speaker_name", ""), x.get("sex", ""),
                                     x.get("party", ""), x.get("district", "")))

    porfecha = defaultdict(list)
    for q in glob.glob(f"source/{iso}/corrected/*.txt.gz") + glob.glob(f"source/{iso}/corrected/*.txt"):
        m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(q))
        if m:
            porfecha[m.group(1)].append(q)

    pend = defaultdict(list)
    for i, x in enumerate(filas):
        if not x["id_dep"].strip() and re.fullmatch(r"(?i)\W*PRESIDENT[EA]\W*", x["speaker_raw"] or ""):
            pend[x["date"]].append(i)

    puesto, corta, sinfirma, ambigua, lejos, sinres = 0, 0, 0, 0, 0, Counter()
    resuelto = {}          # índice de fila → id, para poder interpolar después
    for k, (fe, idxs) in enumerate(sorted(pend.items())):
        if a.limite and k >= a.limite:
            break
        for q in porfecha.get(fe, []):
            o = gzip.open if q.endswith(".gz") else open
            with o(q, "rt", encoding="utf-8", errors="replace") as fh:
                t = fh.read()
            tn = _N(t)
            # posición normalizada → posición cruda, para poder mirar hacia atrás
            marc = [(len(_N(t[:m.start()])), m.group(1).strip()) for m in rx.finditer(t)]
            if not marc:
                continue
            # ⚠ El acta alterna la forma CORTA y la LARGA del mismo nombre dentro del mismo
            # archivo: «João Paulo» y «João Paulo Cunha». La corta encaja con CINCO diputados del
            # padrón y el guardarraíl de unicidad la rechaza —bien rechazada—, pero la larga está
            # ahí mismo. Se desambigua con el CONTEXTO LOCAL: una forma corta que sea prefijo de
            # una sola forma larga del propio archivo hereda su identidad. Fuera del archivo esa
            # inferencia no valdría; dentro, el acta ya ha dicho de quién habla.
            largos = {n for _, n in marc}
            local = {}
            for corto in largos:
                cand = {n for n in largos if n != corto and _N(n).startswith(_N(corto))}
                if len(cand) == 1:
                    local[corto] = next(iter(cand))
            for i in idxs:
                if filas[i]["id_dep"].strip():
                    continue
                f0 = _N(filas[i]["text"])[:FIRMA]
                if len(f0) < 30:
                    corta += 1          # «Muito obrigado.» no tiene firma: se interpola luego
                    continue
                a1 = tn.find(f0)
                if a1 < 0:
                    sinfirma += 1
                    continue
                if tn.find(f0, a1 + 1) >= 0:
                    ambigua += 1
                    continue
                prev = [(pos, n) for pos, n in marc if pos <= a1]
                if not prev or a1 - prev[-1][0] > VENTANA:
                    lejos += 1
                    continue
                nom = prev[-1][1]
                nom = local.get(nom, nom)
                # ⚠ El paréntesis del marcador trae el nombre Y su procedencia: «Renan Calheiros.
                # PMDB - AL», «Arthur Lira. Bloco/PP - AL». Sin quitar esa cola, el 67 % de los
                # nombres «no estaba en el padrón» — y sí estaba. Me llegué a convencer de que
                # eran senadores del Congresso Nacional presidiendo sesiones conjuntas: era un
                # sufijo sin recortar. La cola se reconoce por su FORMA —sigla y UF de dos
                # letras—, no por cortar en el primer punto, que se llevaría «Dr. Ubiali».
                nom = re.sub(r"\.\s*(?:Bloco[^.]{0,40}?|[A-ZÁÉÍÓÚ][\w/º.-]{1,24})\s*[-–]\s*"
                             r"[A-Z]{2}\s*$", "", nom).strip(" .,")
                base = re.sub(r"\s*\(.*$", "", nom).strip()
                idp = porn.get(_N(nom)) or porn.get(_N(base))
                if not idp:
                    ts = frozenset(t for t in re.sub(r"[^A-Za-zÀ-ÿ ]", " ", base).upper().split()
                                   if len(t) > 2)
                    if len(ts) >= 2:
                        h = {j for kk, vv in subs.items() if ts <= kk for j in vv}
                        if len(h) == 1:
                            idp = next(iter(h))
                if not idp:
                    sinres[nom[:34]] += 1
                    continue
                puesto += 1
                resuelto[i] = idp
                if not a.medir:
                    filas[i]["id_dep"] = idp
                    filas[i]["speaker_name"], filas[i]["sex"], pa, di = atr.get(idp, ("",) * 4)
                    filas[i]["party"] = filas[i]["party"] or pa
                    filas[i]["district"] = filas[i]["district"] or di

    # ⚠ Las filas CORTAS —«Muito obrigado.», «Tem V.Exa. a palavra.»— son el 42 % y no tienen
    # firma localizable: no hay texto suficiente para anclarlas. Se resuelven por INTERPOLACIÓN:
    # si la fila anterior y la siguiente de la misma sesión están ancladas **y coinciden**, la de
    # en medio es de la misma persona. Si discrepan, se deja en blanco: entre dos presidencias
    # distintas no se puede saber de qué lado cae.
    inter = 0
    for fe, idxs in pend.items():
        orden = sorted(idxs)
        for k, i in enumerate(orden):
            if i in resuelto or filas[i]["id_dep"].strip():
                continue
            ant = next((resuelto[j] for j in reversed(orden[:k]) if j in resuelto), None)
            sig = next((resuelto[j] for j in orden[k + 1:] if j in resuelto), None)
            if ant and ant == sig:
                inter += 1
                resuelto[i] = ant
                if not a.medir:
                    filas[i]["id_dep"] = ant
                    filas[i]["speaker_name"], filas[i]["sex"], pa, di = atr.get(ant, ("",) * 4)
                    filas[i]["party"] = filas[i]["party"] or pa
                    filas[i]["district"] = filas[i]["district"] or di

    print(f"  {I} · filas de presidencia sin id: {sum(len(v) for v in pend.values()):,}")
    print(f"     por INTERPOLACIÓN entre anclas coincidentes: {inter:,}")
    print(f"     ATRIBUIDAS desde la fuente: {puesto:,}")
    print(f"     texto demasiado corto {corta:,} · sin firma localizable {sinfirma:,} · firma ambigua {ambigua:,} · "
          f"marcador demasiado lejos {lejos:,} · nombre sin resolver {sum(sinres.values()):,}")
    if a.medir:
        for k, v in sinres.most_common(4):
            print(f"       no resuelve: {k!r} ×{v}")
        return
    bak = p.replace(".csv", ".pre_fuente.csv")
    tmp = p + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, delimiter=d)
        w.writeheader()
        w.writerows(filas)
    if not os.path.exists(bak):
        os.rename(p, bak)
    else:
        os.remove(p)
    os.rename(tmp, p)
    print("  ✓ corpus reescrito")


if __name__ == "__main__":
    main()
