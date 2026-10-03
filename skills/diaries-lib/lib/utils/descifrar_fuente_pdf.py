#!/usr/bin/env python3
"""Descifra el texto que el PDF entregó con una codificación de fuente desplazada.

Señalado por el investigador (2026-08-10) en CO, sesión 228 de 2017-06-20:

    …una pregunta UHVSHFWR DO DUWtFXOR HQ HO TXH HVWDEOHFH XQD OLPLWDFLyQ SDUD ORV…

No es basura aleatoria ni mojibake de codificación: es un **desplazamiento de −3** sobre las
letras ASCII —`UHVSHFWR` → `RESPECTO`, `DO` → `AL`— con el ESPACIO llegando como `\\x03`. Ocurre
cuando el PDF trae una fuente con codificación propia y la extracción toma los índices de glifo
en vez de los caracteres.

Alcance: **CO 35.734 filas / 1.191.256 apariciones**, AR 38 filas (106.030), UY 53 (36.464),
PE 577 (19.852), y unos pocos en BR y PA.

⚠ **La corrupción es POR TRAMOS**: dentro de la misma intervención se alternan trozos cifrados y
trozos correctos —«…VHDQ **herederos, valga la redundancia**, de cuatro XQLGDGHV…»—. Por eso no
se puede descifrar la fila entera: se descifra tramo a tramo y **solo si el resultado se parece
más al español que el original**, medido por proporción de vocales y de palabras plausibles. Sin
esa condición, un tramo sano se destruiría.

CLI:
    python descifrar_fuente_pdf.py --country co [--medir]
"""
import argparse
import csv
import os
import re
import sys

csv.field_size_limit(sys.maxsize)

VOC = set("aeiouáéíóúü")
# ⚠ El tramo cifrado es una tirada de tokens unidos por `\x03`. Mi primera versión cogía
# también el texto SANO que lo precedía —separado por espacios normales— y lo destruía:
# «taría se permite llamar para la votación.» salía como «qxoíx pb mbojfqb...».
# El separador es `\x03` seguido a menudo de un espacio normal; exigir que no lo hubiera
# dejaba sin descifrar justo el ejemplo del investigador.
# El carácter que hace de espacio VARÍA con la fuente: `\x03` en unos documentos, `\x01` en
# otros. Se admite cualquier carácter de control por debajo de 0x20.
CTRL = r"[\x01-\x08\x0b\x0c\x0e-\x1f]"
TRAMO = re.compile(rf"\S+(?:{CTRL}[ \t]*\S+)+")


def _es(s: str) -> float:
    """Cuánto se parece a español: proporción de palabras con vocales en proporción normal."""
    w = re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñü]{3,}", s)
    if not w:
        return 0.0
    ok = sum(1 for x in w if 0.25 <= sum(1 for c in x.lower() if c in VOC) / len(x) <= 0.75)
    return ok / len(w)


# El desplazamiento NO es de letras sino del VALOR DEL BYTE: +29. Así encajan a la vez las
# letras (`U`+29=`r`), el espacio (`\x03`+29=` `) y los dígitos usados como letra (`9`+29=`V`).
# Los acentos van aparte: la fuente los coloca en índices propios, y se derivan de los pares
# observados —«DUWtFXOR»→«artículo», «OLPLWDFLyQ»→«limitación»—.
# Los acentos viven en índices propios de la fuente; se derivan de pares observados:
# «DUWtFXOR»→artículo · «OLPLWDFLyQ»→limitación · «PX\\»→muy · «FODUR»→claro
_ACENTO = {"t": "í", "y": "ó", "v": "ó", "q": "í", "z": "ú", "|": "ü", "x": "ñ",
           "\x96": "ñ", "\\": "y", "~": "a", "\x7f": "e"}


# Puntuación y acentos que el cifrado representa con caracteres de control (la coma es `\x0f`).
# Si aparecen TAL CUAL dentro de un tramo, son texto sano que sobrevivió y NO deben desplazarse:
# sin esto, «herederos,» salía «herederosI» y «claro» salía «cl~ro».
_SANOS = set(",.;:()¿?¡!«»\"'áéíóúñüÁÉÍÓÚÑÜ–—")


def _shift(s: str, k: int = 29) -> str:
    o = []
    for c in s:
        if c in _SANOS:
            o.append(c)
            continue
        n = ord(c) + k
        if 32 <= n <= 126:
            o.append(chr(n))
        elif c in _ACENTO:
            o.append(_ACENTO[c])
        else:
            o.append(c)
    return "".join(o)


def _sano(tok: str) -> bool:
    """¿Este token ya es texto bueno? Entonces no se toca.

    ⚠ Dentro de un tramo cifrado la señal NO es la proporción de vocales —«HI» y «PE», que son
    «de» y «la», tienen dos letras y se daban por sanos—, sino la presencia de MINÚSCULAS: el
    cifrado convierte las minúsculas del original en mayúsculas, así que un token sin ninguna
    minúscula dentro del tramo está cifrado. «Señor» y «doctor» se salvan; «VIWMHIRGME» no.
    """
    L = [c for c in tok if c.isalpha()]
    if len(L) < 3:
        return True
    return 0.25 <= sum(1 for c in L if c.lower() in VOC) / len(L) <= 0.7


def descifra(t: str):
    """Devuelve (texto, tokens_descifrados, tokens_intactos).

    ⚠ Se trabaja TOKEN a token, no por tramo. Por tramo, la tirada se comía el texto sano
    contiguo y lo destruía: «Señor Secretario» salía «k}ñor Secretario». Cada token se descifra
    solo si (a) no es ya español legible y (b) el desplazamiento lo convierte en algo que sí lo
    parece. El desplazamiento se BUSCA por token, porque varía con la fuente.
    """
    if not re.search(CTRL, t):
        return t, 0, 0
    hechos = intactos = 0
    out = []
    pos = 0
    for m in TRAMO.finditer(t):
        out.append(t[pos:m.start()])
        toks = re.split(rf"{CTRL}[ \t]*", m.group(0))
        # El desplazamiento se decide con el TRAMO entero —un token suelto da muy poca señal y
        # elegía offsets absurdos— y luego se aplica solo a los tokens que no son ya españoles.
        sucios = " ".join(x for x in toks if not _sano(x))
        k_mejor, val = 0, _es(sucios)
        for k in range(20, 35):
            v = _es(_shift(sucios, k))
            if v > val:
                k_mejor, val = k, v
        for j, tok in enumerate(toks):
            if j:
                out.append(" ")
            if _sano(tok) or not k_mejor:
                out.append(tok)
                intactos += 1
            else:
                out.append(_shift(tok, k_mejor))
                hechos += 1
        pos = m.end()
    out.append(t[pos:])
    return "".join(out), hechos, intactos


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
    a = ap.parse_args()
    iso, I = a.country.lower(), a.country.upper()
    p = f"source/{iso}/standardize/{I}_interventions.csv"
    campos, filas, d = _lee(p)

    fil = h = i2 = 0
    muestra = None
    for x in filas:
        if not re.search(CTRL, x["text"]):
            continue
        nt, hh, ii = descifra(x["text"])
        fil += 1
        h += hh
        i2 += ii
        if muestra is None and hh:
            j = re.search(CTRL, x["text"]).start()
            muestra = (x["text"][max(0, j - 50):j + 70], nt[max(0, j - 50):j + 70])
        if not a.medir:
            x["text"] = nt
    print(f"  {I} · filas afectadas {fil:,} · tramos DESCIFRADOS {h:,} · dejados intactos {i2:,}")
    if muestra:
        print(f"     antes:   {muestra[0]!r}")
        print(f"     después: {muestra[1]!r}")
    if a.medir:
        return
    bak = p.replace(".csv", ".pre_cifra.csv")
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
