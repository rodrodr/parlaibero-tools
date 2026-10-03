#!/usr/bin/env python3
"""`dm_speech`: ¿esta fila es una intervención? 1 sí, 0 no.

La 13ª columna canónica (2026-08-09). Nace de una regla del proyecto: **la fila que no es
intervención no se aparta a un sidecar ni se borra, se MARCA**. El sumario del acta, el
recuento de una votación y el documento reproducido son parte del diario y se publican; lo que
faltaba era poder filtrarlos con una sola condición: `dm_speech == 1`.

Es BINARIA a propósito. Las clases finas —mesa · diputado · gobierno · otros por un lado, y
summary · procedural_reading · other por otro— llegarán como variables aparte, de
enriquecimiento. Esta solo responde a la pregunta que hace falta para trabajar con el corpus.

El **motivo** por el que una fila vale 0 se conserva internamente y se informa en `--medir`,
porque es el material del que saldrán esas variables:

    sumario   índice de la sesión: «Lamberto: eleva su renuncia (5.296-D.-06)»
    votacion  recuento o pase de lista nominal: nombre + sí/no/abstención/presente/ausente
    lectura   documento reproducido: articulado, fórmula de promulgación, firma, dateline
    sin_orador  no hay a quién atribuirla

`mesa` NO es motivo de 0: la presidencia interviene, y separar sus turnos es cosa de la
variable fina de rol, no de este filtro.

Qué NO hace: no inventa vocabulario de orador. Ver [[feedback_descubrir_marcadores]].

⚠ Este marcador es de ALTA PRECISIÓN y BAJA COBERTURA: un 0 es fiable, pero hay filas que no
son intervención y siguen en 1 porque el detector no las ve. `--medir` saca muestra de los 0
para comprobar la precisión, y el informe de cada país declara la cobertura conocida. No se
publica una cobertura sin medirla — ver [[feedback_verificar_la_metrica]].
"""
import argparse
import csv
import os
import random
import re
import sys
import unicodedata
from collections import Counter

csv.field_size_limit(sys.maxsize)

MOTIVOS = ["sumario", "votacion", "lectura", "sin_orador"]

# ── sumario ───────────────────────────────────────────────────────────────────
# La entrada del índice es «Forma: verbo en minúscula» y el bloque trae referencias de
# expediente. Una línea suelta no basta: se exige un BLOQUE de líneas SEGUIDAS, porque
# contándolas dispersas cualquier fila larga de AR calificaba —salían discursos de la
# presidencia sobre el artículo 157 del reglamento.
_SUM_LIN = re.compile(r"^\s*[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ .()'’\-]{2,44}:\s+[a-záéíóúñ]")
_SUM_EXP = re.compile(r"\(\d[\d.]*[-/][A-ZÁÉÍÓÚÑ]\.?[-/]\d{2,4}\)")
_SUM_CAB = re.compile(r"^\s*(?:SUMARIO|ASUNTOS\s+ENTRADOS|CONTESTACIONES\s+A\s+PEDIDOS|"
                      r"COMUNICACIONES\s+(?:OFICIALES|DE)|DICT[ÁA]MENES\s+(?:DE|OBSERVADOS)|"
                      r"[ÍI]NDICE|ORDEM\s+DO\s+DIA|SUM[ÁA]RIO)", re.M)

# ── votación ──────────────────────────────────────────────────────────────────
# ⚠ SIN `re.I`, y con el voto EN VERSAL. Con mayúsculas y minúsculas indistintas, `NO` casaba
# con cualquier línea de prosa terminada en «no» y los «recuentos» resultaban ser cierres de
# sesión: 181 filas de AR, todas falsas. Es el mismo error que ya costó dos barridos en MX.
# La línea de un recuento además es CORTA: el nombre y su voto, nada más.
_VOT_LIN = re.compile(r"^[^\n:]{3,44}[:\s.·-]{1,40}(?:S[ÍI]|NO|ABSTENCI[ÓO]N|ABSTEN[ÇC][ÃA]O|"
                      r"PRESENTE|AUSENTE|A\s+FAVOR|EN\s+CONTRA|SIM|N[ÃA]O)\s*$", re.M)
_VOT_TOT = re.compile(r"(?:votos?\s+(?:afirmativos|negativos|a\s+favor|en\s+contra)|"
                      r"resultado\s+d[ea]\s+(?:la\s+)?vota[cç][ãi]|"
                      r"aprobad[oa]\s+por\s+\d+\s+votos|vota(?:ram|ções)\s+a\s+favor)", re.I)

# ── lectura ───────────────────────────────────────────────────────────────────
# Cada entrada es una señal ESTRUCTURAL de documento, no una palabra suelta del discurso.
_LEC = {
    "articulado": re.compile(r"^\s*(?:Art(?:[íi]culo)?\.?\s*\d|ARTÍCULO\s+\d|Artigo\s+\d)", re.M),
    "promulga":   re.compile(r"(?:Comun[íi]quese\s+al\s+Poder\s+Ejecutivo|"
                             r"El\s+Senado\s+y\s+(?:la\s+)?C[áa]mara\s+de\s+Diputados|"
                             r"DECRETA|RESUELVE|SANCIONA\s+CON\s+FUERZA|"
                             r"A\s+Assembleia\s+da\s+Rep[úu]blica\s+decreta)", re.M),
    "aparato":    re.compile(r"^\s*(?:FUNDAMENTOS|ANTECEDENTE|EXPOSICI[ÓO]N\s+DE\s+MOTIVOS|"
                             r"INFORME|DICTAMEN|JUSTIFICATIVA|JUSTIFICA[ÇC][ÃA]O|"
                             r"PROJETO\s+DE\s+(?:LEI|RESOLU[ÇC][ÃA]O|DECRETO)|"
                             r"PROJECTO\s+DE\s+(?:LEI|RESOLU[ÇC][ÃA]O)|PROPOSTA\s+DE\s+LEI|"
                             r"REQUERIMENTO|PARECER)\s*$", re.M),
    "dateline":   re.compile(r"^\s*[A-ZÁÉÍÓÚ][\w áéíóúñ]{3,24},\s+\d{1,2}\s+de\s+\w+\s+de\s+\d{4}\.?\s*$", re.M),
    # ⚠ la fórmula de sala es la que delataba a los dos corpus en portugués: con solo la
    # castellana («Sala de la comisión»), BR daba 64 filas de 1,6 M y PT 9 de 1,1 M.
    "sala":       re.compile(r"Sala\s+d[eao]s?\s+(?:la\s+)?(?:comisi[óo]n|sesiones|"
                             r"Sess[õo]es|Comiss[ãa]o|Reuni[õo]es)", re.I),
}
_LEC_MIN = 900          # un documento reproducido es largo; una cita de un artículo, no


def _N(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(s).upper())
                   if unicodedata.category(c) != "Mn")


def _bloque(lineas, rx, minimo: int) -> bool:
    """¿Hay `minimo` líneas SEGUIDAS que casan? Las líneas en blanco no cortan el bloque."""
    n = 0
    for l in lineas:
        if rx.match(l):
            n += 1
            if n >= minimo:
                return True
        elif l.strip():
            n = 0
    return False


def motivo(texto: str, speaker: str) -> str | None:
    """Devuelve por qué la fila NO es una intervención, o None si lo es."""
    t = texto or ""
    lineas = t.split("\n")
    if _bloque(lineas, _SUM_LIN, 4) and (len(_SUM_EXP.findall(t)) >= 2 or _SUM_CAB.search(t)):
        return "sumario"
    if _bloque(lineas, _VOT_LIN, 5) or (_bloque(lineas, _VOT_LIN, 2) and _VOT_TOT.search(t)):
        return "votacion"
    if len(t) >= _LEC_MIN and sum(1 for rx in _LEC.values() if rx.search(t)) >= 2:
        return "lectura"
    if not (speaker or "").strip():
        return "sin_orador"
    return None


def dm_speech(texto: str, speaker: str) -> str:
    return "0" if motivo(texto, speaker) else "1"


def _leer(p):
    with open(p, encoding="utf-8") as fh:
        d = csv.Sniffer().sniff(fh.readline(), ";,").delimiter
        fh.seek(0)
        r = csv.DictReader(fh, delimiter=d)
        return list(r.fieldnames), list(r), d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--medir", action="store_true", help="cuenta y muestrea los 0, no escribe")
    ap.add_argument("--muestra", type=int, default=3)
    a = ap.parse_args()

    campos, filas, d = _leer(a.input)
    c = Counter()
    ejem = {k: [] for k in MOTIVOS}
    for x in filas:
        mo = motivo(x.get("text", ""), x.get("speaker_raw", ""))
        x["dm_speech"] = "0" if mo else "1"
        c[mo or "_intervencion"] += 1
        if mo and len(ejem[mo]) < 400:
            ejem[mo].append((x.get("speaker_raw", ""), (x.get("text", "") or "")[:170]))
    n = max(len(filas), 1)
    cero = n - c["_intervencion"]
    print(f"  {os.path.basename(a.input)} · {len(filas):,} filas · "
          f"dm_speech=1 {c['_intervencion']:,} ({c['_intervencion']/n*100:.2f}%) · "
          f"dm_speech=0 {cero:,} ({cero/n*100:.2f}%)")
    for k in MOTIVOS:
        if c[k]:
            print(f"     motivo {k:11} {c[k]:>9,}  {c[k]/n*100:6.2f}%")

    if a.medir:
        random.seed(13)
        for k in MOTIVOS:
            if not ejem[k]:
                continue
            print(f"\n  ── 0 por {k} ──")
            for sp, tx in random.sample(ejem[k], min(a.muestra, len(ejem[k]))):
                print(f"   [{sp[:28]}] {tx.replace(chr(10), ' ⏎ ')}…")
        return

    if "dm_speech" not in campos:
        i = campos.index("text")
        campos = campos[:i] + ["dm_speech"] + campos[i:]
    tmp = a.input + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as out:
        w = csv.DictWriter(out, fieldnames=campos, delimiter=d)
        w.writeheader()
        w.writerows(filas)
    os.replace(tmp, a.input)
    print("  ✓ escrito con dm_speech")


if __name__ == "__main__":
    main()
