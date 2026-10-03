#!/usr/bin/env python3
"""Vincula por VENTANA: si un nombre casi idéntico ya está resuelto en la misma sesión, se adopta.

Propuesto por el investigador (2026-08-10) sobre CL, con tres casos que ningún match directo
resuelve y que la vecindad sí:

    La señora MALUENDA (Presidenta provisional)   → CL00656
    La señora MALVENDA (Presidente pro visional)  → vacío     ← un carácter de diferencia
    El señor FLORES (Presidente accidental)       → vacío
    El señor FLORES, don Iván (Presidente accid.) → CL00982   ← dos turnos más adelante

La idea es que **la sesión acota el universo de personas**: quien habla en un acta está en esa
acta, y casi siempre varias veces. Si una forma sin vincular se parece mucho a otra que SÍ está
resuelta en la misma sesión, y el candidato es ÚNICO, la duda desaparece.

## Dos medidas de parecido, porque los fallos son de dos clases

    ratio            MALVENDA ↔ MALUENDA        87,5   una letra mal leída
    token_set_ratio  FLORES   ↔ FLORES DON IVAN  100    la misma persona con más nombre

Se toma el máximo de ambas con umbral 85. Comparar solo con `ratio` dejaba fuera el caso de
FLORES (55) y solo con tokens habría atado cualquier apellido suelto.

## Salvaguardas

- **Unicidad**: si en la sesión hay dos personas distintas por encima del umbral, se descarta.
  En CL son 110 casos, y ahí un match sería una moneda al aire.
- **Los ROLES no juegan**: `PRESIDENTE`, `SECRETARIO`, `MINISTRO`… ni como origen ni como
  candidato. Su parecido es con el cargo, no con la persona.
- El tratamiento y el rol entre paréntesis se retiran antes de comparar, y también el `don`/`doña`.

CLI:
    python match_ventana.py --country cl [--medir] [--umbral 85]
"""
import argparse
import csv
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict

from rapidfuzz import fuzz

csv.field_size_limit(sys.maxsize)

TRATO = re.compile(r"^(?:EL|LA|LOS|LAS)\s+SE[ÑN]OR[AES]*\s+", re.I)
# Cargos de CÁMARA: quien los ocupa ES diputado, así que la forma anónima («PRESIDENTE») no
# sirve como origen ni como candidato, pero «El señor MALUENDA (Presidenta provisional)» SÍ.
# Por eso este patrón se busca en el NÚCLEO, que ya viene sin el paréntesis.
ROL = re.compile(r"\b(PRESIDENT|SECRETARI|VICEPRESIDENT|PROSECRETARI|DIPUTAD|RELATOR)")
# Cargos de GOBIERNO: quien los ocupa NO es diputado. Esto sí se busca en la forma completa,
# porque vive dentro del paréntesis: «El señor LARRAÍN (ministro de Hacienda)» se emparejaba
# con una diputada. Distinguirlo del anterior es lo que evita romper el método.
GOBIERNO = re.compile(r"\b(MINISTR|SUBSECRETARI|VICEMINISTR|CANCILLER|JEFE DE GABINETE|"
                      r"PRIMEIRO MINISTR|ASESOR)")


def _N(s):
    s = "".join(c for c in unicodedata.normalize("NFD", str(s).upper())
                if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Z ]+", " ", s).strip()


def nucleo(s: str) -> str:
    """El nombre desnudo: sin tratamiento, sin el rol entre paréntesis y sin «don»."""
    s = re.sub(r"\(.*?\)", "", s)
    s = TRATO.sub("", _N(s))
    s = re.sub(r"^(?:SRA?|SENOR[A]?|DON|DONA)\b\.?\s*", "", s)
    s = re.sub(r"\bDO[NÑ]A?\b", "", s)
    return re.sub(r"\s+", " ", s).strip()


def parecido(a: str, b: str) -> float:
    """Parecido entre dos nombres del CORPUS, con el crédito por tokens acotado.

    ⚠ `token_set_ratio` premia el subconjunto y con un apellido compartido dispara: emparejó
    «FLORES FLORES» con «ZUMAETA FLORES» y con «FLORES NANO» —tres personas distintas de PE—.
    Y acotarlo exigiendo «dos tokens en común» tampoco basta: `{FLORES, FLORES}` es UN token
    distinto, así que caía en la rama que yo creía segura.

    El discriminante que sí funciona: en estas formas el corpus escribe **el apellido primero**,
    de modo que el crédito por tokens solo se da si **coincide el primer token** o si comparten
    dos o más tokens largos. «FLORES» ↔ «FLORES IVAN» pasa; «FLORES FLORES» ↔ «ZUMAETA FLORES»
    no, y cae a la comparación literal, que la descarta.
    """
    lit = fuzz.ratio(a, b)
    pa, pb = a.split(), b.split()
    if not pa or not pb:
        return lit
    comunes = len({t for t in pa if len(t) > 3} & {t for t in pb if len(t) > 3})
    # El ancla del primer apellido solo se exige cuando AMBOS nombres tienen dos o más tokens:
    # ahí es donde `token_set_ratio` regala el parecido por un apellido común. Con una forma de
    # un solo token —«CAVAJLARO», «ROJO»— exigirla retiraba 697 aciertos entre AR, PA y CL.
    if len(pa) < 2 or len(pb) < 2 or pa[0] == pb[0] or comunes >= 2:
        return max(lit, fuzz.token_set_ratio(a, b))
    return lit


def _lee(p):
    with open(p, encoding="utf-8") as fh:
        d = csv.Sniffer().sniff(fh.readline(), ";,").delimiter
        fh.seek(0)
        r = csv.DictReader(fh, delimiter=d)
        return list(r.fieldnames), list(r), d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", required=True)
    ap.add_argument("--umbral", type=float, default=85)
    ap.add_argument("--ventana", type=int, default=0,
                    help="nº de intervenciones a cada lado; 0 = la sesión entera")
    ap.add_argument("--medir", action="store_true")
    a = ap.parse_args()
    iso, I = a.country.lower(), a.country.upper()
    p = f"source/{iso}/standardize/{I}_interventions.csv"
    campos, filas, d = _lee(p)
    _, dep, _ = _lee(f"source/{iso}/standardize/{I}_deputies.csv")
    atr = {}
    for x in dep:
        atr.setdefault(x["id_dep"], {}).setdefault(
            x.get("legislature", ""),
            tuple(x.get(c, "") for c in ("speaker_name", "sex", "party", "district")))

    por = defaultdict(list)
    for i, x in enumerate(filas):
        por[(x["legislature"], x["date"])].append(i)

    res = Counter()
    muestras = []
    for k, idx in por.items():
        # (posición en la sesión, núcleo, id) de cada fila YA vinculada
        vinc = []
        for pos, j in enumerate(idx):
            if not filas[j]["id_dep"].strip():
                continue
            n = nucleo(filas[j]["speaker_raw"])
            if n and not ROL.search(n) and not GOBIERNO.search(_N(filas[j]["speaker_raw"])):
                vinc.append((pos, n, filas[j]["id_dep"]))
        if not vinc:
            continue
        donde = {j: pos for pos, j in enumerate(idx)}
        for i in idx:
            x = filas[i]
            if x["id_dep"].strip():
                continue
            # ⚠ Una fila declarada NO-DISCURSO no tiene orador que vincular. Sin este guardarraíl
            # CL emparejaba `ABSTENCIONES` —una etiqueta de recuento de votos— con un diputado
            # real, 546 veces. Lo que no es habla no se vincula. [[decision_tipo_de_texto]]
            if x.get("dm_speech", "1").strip() == "0":
                res["no es discurso"] += 1
                continue
            # ⚠ El ROL se busca en la forma COMPLETA, no en el núcleo. `nucleo()` quita el
            # paréntesis, y en CL el cargo vive justo ahí: «El señor LARRAÍN (ministro de
            # Hacienda)» quedaba como «LARRAIN» y se emparejaba con una diputada.
            n = nucleo(x["speaker_raw"])
            if len(n) < 4 or ROL.search(n) or GOBIERNO.search(_N(x["speaker_raw"])):
                res["rol o vacío"] += 1
                continue
            cand = {}
            # ⚠ La ventana ESTRECHA no añade candidatos: los quita. Y eso es lo que deja bajar
            # el umbral sin perder precisión — en el debate, quien interrumpe vuelve a hablar
            # cerca, así que el vecino inmediato acota quién puede ser. Idea del investigador.
            for pos, nj, idj in vinc:
                if a.ventana and abs(pos - donde[i]) > a.ventana:
                    continue
                r = parecido(n, nj)
                if r >= a.umbral:
                    cand[idj] = max(cand.get(idj, 0), r)
            if len(cand) == 1:
                res["resuelto"] += 1
                idp = next(iter(cand))
                if len(muestras) < 8:
                    muestras.append((x["date"], x["speaker_raw"][:42], idp))
                if not a.medir:
                    v = atr.get(idp, {})
                    t = v.get(x.get("legislature", "")) or (next(iter(v.values())) if v else ("",) * 4)
                    x["id_dep"] = idp
                    for c, y in zip(("speaker_name", "sex", "party", "district"), t):
                        if c in x:
                            x[c] = y
            elif len(cand) > 1:
                res["ambiguo (se descarta)"] += 1
            else:
                res["sin candidato"] += 1

    print(f"  {I} · sin vincular examinadas: {sum(res.values()):,}")
    for k2, v in res.most_common():
        print(f"     {k2:24} {v:>8,}")
    if muestras:
        print("     muestras:")
        for f, s, i in muestras:
            print(f"       [{f}] {s!r} → {i}")
    if a.medir:
        return
    bak = p.replace(".csv", ".pre_ventana.csv")
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
