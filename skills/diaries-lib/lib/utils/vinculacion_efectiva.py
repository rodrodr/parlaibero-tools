#!/usr/bin/env python3
"""Recalcula la vinculación EFECTIVA sobre el corpus actual, con la definición tr-0003.

⚠ (2026-09-23) La cifra de diaries-report y de corpus_info.json es la de la definición vigente
tr-0109 (vinculacion_tr0109.py): descuenta además lo que el acta no permite atribuir y cuenta solo
las filas de habla. Este script queda para comparar (vinculacion_tr0109.py --comparar tr-0003).

    efectiva = vinculadas / (total − filas de NO-DIPUTADO NOMBRADO)

Se descuenta solo a quien **no puede tener escaño** y va NOMBRADO en el acta: ministros, secretaría
general, relatores, contralores, magistrados, jefe del Estado, invitados. ⚠ **No se descuentan los
cargos anónimos** (`PRESIDENTE` a secas): quien preside ES un diputado, así que no recuperar su
identidad es un hueco propio, no una exclusión estructural ([[feedback_vinculacion_efectiva]]).

**Por qué hace falta rehacerlo (2026-08-11).** Las cifras de `docs/{iso}/corpus_info.json` se
calcularon antes del reproceso y ya no describen estos corpus: BR figura con 1.627.304 filas y
tiene 1.666.126; PY con 334.045 y tiene 374.629. Publicar una efectiva de otro corpus es peor que
no publicarla. El script original leía su clasificación de un fichero temporal que ya no existe,
así que la regla se reconstruye aquí y queda en el código, no en un scratch.

⚠ Esta es MI reconstrucción de la regla, no la clasificación original. Difiere de la publicada en
la medida en que difieran los patrones; se informa el desglose entero para que sea auditable.

CLI:
    python vinculacion_efectiva.py [--country pe] [--json] [--out FICHERO.json]

La tabla por defecto no cambia. --json imprime las mismas cifras en JSON con procedencia (script,
sha256, hora UTC, orden y sha256 de cada CSV); --out las escribe de forma atómica, nunca sobre una
entrada, y sigue imprimiendo la tabla. En esos dos modos, un CSV ausente, sin filas o sin
id_dep/speaker_raw sale con 2 y {"error": ...}; el modo tabla se comporta como siempre.
"""
import argparse
import csv
import glob
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from salida_json import (ErrorEntorno, comprueba_destino, escribe_atomico,  # noqa: E402
                         procedencia, sale_con_error, sha256)

csv.field_size_limit(sys.maxsize)

DEFINICION = {
    "id": "tr-0003",
    "formula": "efectiva = vinculadas / (filas − filas de no-diputado)",
    "descripcion": ("Se descuenta a quien no puede tener escaño, lleve nombre o no (relatores, "
                    "secretaría administrativa, ministros...), con la clasificación reconstruida en "
                    "vinculacion_efectiva.py (2026-08-11) sobre todas las filas del CSV de "
                    "standardize. La presidencia sin nombre no se descuenta."),
    "decision": "tr-0003 (2026-07-30) en state/_transversal/decisions.jsonl",
    "cifra_del_informe": False,
    "nota": "Solo para comparar: la cifra de diaries-report es tr-0109 (vinculacion_tr0109.py).",
}

# Cargos que NO pueden tener escaño en la cámara
_NO_DIP = (r"ministr[oa]|secretari[oa]|subsecretari[oa]|prosecretari[oa]|relator[a]?|"
           r"contralor[a]?|magistrad[oa]|fiscal|procurador[a]?|defensor[a]?|"
           r"presidente\s+de\s+la\s+rep[úu]blica|jefe\s+de\s+(?:estado|gabinete)|"
           r"primeir[oa]-?ministr[oa]|embajador[a]?|viceministr[oa]|asesor[a]?|"
           r"director[a]?|gerente|maestr[oa]\s+de\s+ceremonias|invitad[oa]|"
           r"presidente\s+de\s+la\s+corte|canciller|intendente")
ROL = re.compile(rf"(?i)\b(?:{_NO_DIP})\b")
# Un NOMBRE propio: al menos dos tokens con mayúscula inicial y minúsculas detrás, o versales
NOMBRE = re.compile(r"[A-ZÁÉÍÓÚÑÂÊÔÃÕÇ][a-záéíóúñâêôãõç]{2,}"
                    r"(?:\s+(?:d[eao]l?|d[aeo]s?|y|e)?\s*[A-ZÁÉÍÓÚÑÂÊÔÃÕÇ][a-záéíóúñâêôãõç]{2,}){1,}"
                    r"|[A-ZÁÉÍÓÚÑ]{3,}(?:\s+[A-ZÁÉÍÓÚÑ]{3,}){1,}")


# ⚠⚠ La palabra «nombrado» de la definición NO es la condición: es una descripción. Leyéndola como
# condición —descontar solo si el rol va acompañado de un nombre propio— mi primer recálculo dio
# **PE 88,59 % donde la cifra publicada es 96,70 %**, porque `RELATOR` ×69.923 va SIN nombre y aun
# así un relator no puede ser diputado nunca. El contraste que la definición dibuja es otro:
#
#     descuenta   → el cargo NO PUEDE tener escaño (relator, secretaría general, ministro), lo
#                   lleve nombre o no. Es una exclusión estructural.
#     no descuenta → `PRESIDENTE` a secas, porque **quien preside SÍ es diputado** y no haber
#                   recuperado su identidad es un hueco NUESTRO.
#
# Es la distinción entera de [[feedback_vinculacion_efectiva]]: no llamar exclusión estructural a
# un fallo de atribución propio. La presencia de un nombre no cambia de qué lado cae la fila.
PRESIDE = re.compile(r"(?i)^\W*(?:el|la|a|o)?\s*(?:c\.?\s*)?(?:vice)?president")

# ⚠ «Secretario» significa cosas DISTINTAS en cada cámara y de eso dependían 3,7 puntos de la
# cifra final. La regla la fijó el investigador (2026-08-11): **«secretario administrativo
# siempre es funcionario»**. Extendida al vocabulario que el corpus usa de verdad:
#   FUNCIONARIO → administrativo · general · redactor · de actas · de un MINISTERIO
#   DIPUTADO    → el ordinal de la Mesa (primer/segundo secretario, secretaria primera) y el
#                 explícito «Secretario diputado» de MX
# En MX el 96 % de los «secretarios» YA está identificado como diputado (68.392 de 71.336): allí
# es un cargo de la Mesa. En CO y PA son la Secretaría General de la cámara, funcionarios. En PY
# son 69.977 «SECRETARIO (Administrativo)» y ninguno vinculado.
# ⚠ El OCR escribe «(Acministrativo)» y «(A dministrativo)»: hay que admitirlos o se quedan 450
# filas del lado equivocado por una letra.
_ADMIN = r"a[cd]?\s?ministrativ[oa]"
FUNCIONARIO = re.compile(rf"(?i)\b(?:sub|pro)?secretari[oa]\b[^\n]{{0,30}}?"
                         rf"\b(?:{_ADMIN}|general|redactor[a]?|de\s+actas|"
                         rf"de\s+(?:econom[íi]a|educaci[óo]n|estado|hacienda|gobierno|trabajo|"
                         rf"salud|defensa|emergencia))\b"
                         rf"|\b(?:sub|pro)?secretari[oa]\s*\(\s*{_ADMIN}")
MESA = re.compile(r"(?i)\b(?:primer|segund[oa]|tercer|cuart[oa]|primera|1ra?\.?|2da?\.?)\s+"
                  r"(?:sub|pro)?secretari[oa]\b|\bsecretari[oa]\s+(?:diputad[oa]|primera|segunda)\b"
                  r"|\bsecretari[oa]\s+de\s+la\s+mesa\b")


def clasifica(sr: str) -> str:
    """`estructural` (se descuenta) · `presidencia` · `otro` (no se descuentan)."""
    s = (sr or "").strip()
    if not s:
        return "otro"
    if PRESIDE.match(s) and not re.search(r"(?i)rep[úu]blica|corte|tribunal", s):
        return "presidencia"
    if MESA.search(s):
        return "otro"                       # cargo de la Mesa: ES diputado, cuenta en contra
    if FUNCIONARIO.search(s):
        return "estructural"
    if re.search(r"(?i)\b(?:sub|pro)?secretari[oa]\b", s):
        return "ambiguo"                    # ni ordinal de Mesa ni administrativo: sin decidir
    return "estructural" if ROL.search(s) else "otro"


def uno(iso):
    I = iso.upper()
    p = f"source/{iso}/standardize/{I}_interventions.csv"
    with open(p, encoding="utf-8-sig") as fh:
        d = csv.Sniffer().sniff(fh.readline(), ";,").delimiter
        fh.seek(0)
        n = v = nom = ano = otr = amb = 0
        for x in csv.DictReader(fh, delimiter=d):
            n += 1
            if x.get("id_dep", "").strip():
                v += 1
                continue
            k = clasifica(x.get("speaker_raw", ""))
            nom += k == "estructural"
            ano += k == "presidencia"
            amb += k == "ambiguo"
            otr += k == "otro"
    return I, n, v, nom, ano, otr, amb


def _csv(iso):
    return f"source/{iso}/standardize/{iso.upper()}_interventions.csv"


def _valida(iso):
    """Lo que el modo tabla no comprueba: que el CSV exista y traiga id_dep y speaker_raw."""
    p = _csv(iso)
    if not os.path.isfile(p):
        raise ErrorEntorno(f"no existe {p}")
    with open(p, encoding="utf-8-sig") as fh:
        cab = fh.readline()
    try:
        d = csv.Sniffer().sniff(cab, ";,").delimiter
    except csv.Error:
        raise ErrorEntorno(f"{p}: no se reconoce el separador de la cabecera") from None
    campos = next(csv.reader([cab], delimiter=d), [])
    faltan = [c for c in ("id_dep", "speaker_raw") if c not in campos]
    if faltan:
        raise ErrorEntorno(f"{p} no tiene la columna {' ni '.join(faltan)}")
    return p, d


def cifras(iso):
    """uno() validado y con procedencia, para --json y --out: (tupla de uno(), cifras)."""
    p, d = _valida(iso)
    t = uno(iso)
    I, n, v, nom, ano, otr, amb = t
    if not n:
        raise ErrorEntorno(f"{p} no tiene filas")
    if n <= nom + amb:
        raise ErrorEntorno(f"{p}: se descuentan todas las filas y la efectiva no está definida")
    ef, efa = v / (n - nom), v / (n - nom - amb)
    return t, {"filas": n, "vinculadas": v, "no_diputado_descontado": nom,
               "presidencia_sin_identificar": ano, "ambiguo": amb, "resto_sin_vincular": otr,
               "bruta_pct": float(f"{100*v/n:.2f}"), "efectiva": ef,
               "efectiva_pct": float(f"{100*ef:.2f}"),
               "efectiva_si_ambiguos_funcionarios_pct": float(f"{100*efa:.2f}"),
               "separador": d, "ruta": p, "sha256": sha256(p)}


def _total(tuplas):
    n, v, nom, ano, otr, amb = (sum(t[k] for t in tuplas) for k in range(1, 7))
    ef, efa = v / (n - nom), v / (n - nom - amb)
    return {"filas": n, "vinculadas": v, "no_diputado_descontado": nom,
            "presidencia_sin_identificar": ano, "resto_sin_vincular": otr, "ambiguo": amb,
            "bruta_pct": float(f"{100*v/n:.2f}"), "efectiva": ef,
            "efectiva_pct": float(f"{100*ef:.2f}"),
            "efectiva_si_ambiguos_funcionarios_pct": float(f"{100*efa:.2f}"),
            "horquilla_puntos": float(f"{100*(efa-ef):.2f}")}


def _imprime_tabla(resultados):
    """La tabla de siempre (la fijan tests/fixtures/vinculacion_tabla_esperada*.txt).
    `resultados` devuelve las tuplas de uno() y se llama después de la cabecera, como antes."""
    print(f"  {'':4} {'filas':>11} {'bruta':>8} {'EFECTIVA':>9}   "
          f"{'·':>8}  {'NO-DIP':>13} {'presidencia':>12} {'ambiguo':>9}")
    T = [0, 0, 0, 0, 0, 0]
    for I, n, v, nom, ano, otr, amb in resultados():
        T[0] += n; T[1] += v; T[2] += nom; T[3] += ano; T[4] += otr; T[5] += amb
        ef = v / (n - nom) if n > nom else 0
        efa = v / (n - nom - amb) if n > nom + amb else 0
        print(f"  {I}  {n:>11,} {100*v/n:>7.2f}% {100*ef:>8.2f}% {100*efa:>8.2f}%  "
              f"{nom:>13,} {ano:>12,} {amb:>9,}")
    ef = T[1] / (T[0] - T[2])
    efa = T[1] / (T[0] - T[2] - T[5])
    print(f"\n  TOTAL {T[0]:,} filas · bruta {100*T[1]/T[0]:.2f}%")
    print(f"     EFECTIVA {100*ef:.2f}%  (si los {T[5]:,} ambiguos son diputados)")
    print(f"     EFECTIVA {100*efa:.2f}%  (si son funcionarios)  ← horquilla {100*(efa-ef):.2f} puntos")
    print(f"     descontado {T[2]:,} · presidencia sin identificar {T[3]:,} (NO se descuenta) · "
          f"resto {T[4]:,}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--country")
    ap.add_argument("--json", action="store_true", help="imprime las cifras en JSON en vez de la tabla")
    ap.add_argument("--out", help="escribe el JSON aquí (atómico, nunca sobre una entrada) y "
                                  "sigue imprimiendo la tabla")
    a = ap.parse_args()
    P = [a.country.lower()] if a.country else sorted(
        os.path.basename(os.path.dirname(os.path.dirname(x)))
        for x in glob.glob("source/*/standardize/*_interventions.csv"))
    if not (a.json or a.out):
        with ThreadPoolExecutor(max_workers=8) as ex:     # modo tabla: el de siempre, errores incluidos
            _imprime_tabla(lambda: sorted(ex.map(uno, P)))
        return 0
    try:
        if not P:
            raise ErrorEntorno("no hay ningún source/*/standardize/*_interventions.csv en este directorio")
        destino = comprueba_destino(a.out, [_csv(iso) for iso in P]) if a.out else None
        with ThreadPoolExecutor(max_workers=8) as ex:
            C = sorted(ex.map(cifras, P), key=lambda x: x[0])
        salida = {**procedencia(__file__), "definicion": DEFINICION,
                  "paises": {t[0]: d for t, d in C}, "total": _total([t for t, _ in C])}
        if destino:
            escribe_atomico(destino, salida)
    except ErrorEntorno as e:
        return sale_con_error(str(e), a.json)
    except OSError as e:
        return sale_con_error(f"no se pudo leer o escribir: {e}", a.json)
    if a.json:
        print(json.dumps(salida, ensure_ascii=False, indent=2))
    else:
        _imprime_tabla(lambda: [t for t, _ in C])
    return 0


if __name__ == "__main__":
    sys.exit(main())
