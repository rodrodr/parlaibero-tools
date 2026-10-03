#!/usr/bin/env python3
"""Une los TÍTULOS en MAYÚSCULAS partidos por el ancho de columna (Fase A.7 del reproceso).

Une `MAYÚSCULAS ⏎ MAYÚSCULAS` SOLO si el fragmento es un título/frase envuelta, y **NUNCA** si el
contexto del corte tiene señal de pase de lista / tabla / roster / índice / mobiliario / basura OCR.
Portado de `~/reocr_ec/faseA_titulo_{dryrun,apply}.py` (aplicado a 15/16 países, 341.310 uniones).

⚠ TIPIFICAR antes de reparar y decidir POR TIPO: se corrige todo lo seguro en vez de renunciar a la
clase por sus casos dudosos. Las guardas hardcodeadas (siglas de partido, nombres de pila) solo hacen
el criterio MÁS conservador —nunca fuerzan una unión—, así que son seguras entre países.

Uso como módulo (en `correct_text.procesa_secuencia`):
    from unir_titulos_partidos import unir_titulos
    text, n = unir_titulos(text)

⚠ Es un `\\n`-join DENTRO de `text`: no cambia el número de filas ni ninguna otra columna. De bajo
riesgo, pero verifícalo por país con `--dry` antes de promover (los guardarraíles se calibran contra
el pase de lista y la basura OCR del propio país).
"""
from __future__ import annotations

import re

SPLIT = re.compile(r'([A-ZÁÉÍÓÚÑ]{4,}[ ,]*)\n([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ .,]{2,})')

# --- guardarraíles: si el CONTEXTO del corte casa alguno, NO unir ---
G_ROLL   = re.compile(r'\b(PRESENTE|AUSENTE|A FAVOR|EN CONTRA|SIN VOTO|AFIRMATIVO|NEGATIVO|ABSTENCI[OÓ]N|SÍ|VOTÓ)\b'
                      r'|\b(Presente|Ausente|Vot[oó]|Declin[oó]|A favor|En contra|Sin voto)\b\.?'
                      r'|\bACA\b|\bAUS\b')
G_PARTY  = re.compile(r'\b(PLD|PRM|PRD|PRSC|FP|UCR|PRO|PJ|INDEPEN|FA|ASD|BIS|PQDC|PRSD|DXC)\b\s*(SI|NO|SÍ|Sí|No|--|SIN|\d)')
G_PARTY2 = re.compile(r'^(PLD|PRM|PRD|PRSC|FP|UCR|PRO|PJ|INDEPEN|FA|ASD|BIS|PQDC|PRSD|DXC)\b')
G_ROSTER = re.compile(r'^(PRIMER|SEGUNDO|TERCER|CUARTO|QUINTO|SEXTO|SÉPTIMO)?\s*(VICE)?(PRESIDENTE|SECRETARIO|SECRETARIA)\b|^VOCAL\b')
G_CARGO  = re.compile(r'\b(PRESIDENTE|VICEPRESIDENTE|SECRETARIO|SECRETARIA|VOCAL)\b')


def _es_roster_back(pre_ctx: str) -> bool:
    # línea de mesa: ≥2 cargos en el texto ANTES del corte (…VICEPRESIDENTE TERCER VICEPRESIDENTE)
    return len(G_CARGO.findall(pre_ctx)) >= 2


G_INDEX  = re.compile(r'[ÍI]NDICE|ASUNTO\s+P[ÁA]GINA|\.{4,}')
G_ASIST  = re.compile(r'HONORABLES?\s+(DIPUTAD|LEGISLADOR|DIPUTAD[AO]S|SUPLENTES|PRINCIPALES)')
G_EPIG   = re.compile(r'^(ART[ÍI]CULO|ARTIGO|CAP[ÍI]TULO|T[ÍI]TULO|SEC[CÇ][ÍIÃ]?[OÓ]?N?|SUBSECCI[ÓO]N|CONSIDERANDO|'
                      r'POR TANTO|DECRETA|ACUERDA|RESUELVE|DICTAMEN|SUMARIO|SUM[ÁA]RIO|HONORABLE PLENO|'
                      r'EXPOSICI[ÓO]N DE MOTIVOS|DISPOSICION|ANEXO|PROYECTO DE (LEY|RESOLUCI)|'
                      r'PROJETO DE LEI|PROPOSTA DE (LEI|RESOLU)|VOTO DE)\b')
G_FURN   = re.compile(r'DEPARTAMENTO DE TAQUIGRAFIA|TAQUIGRAFIA|REVIS[ÃA]O\b|\bSERERP\b|COORDENA[ÇC]'
                      r'|DIVIS[ÃA]O DE REDA|SECRETARIA DE REGISTRO|IMPRENSA NACIONAL|REGISTRO E REDA'
                      r'|PORTE\s+PAGO|APOIO AUDIOVISUAL')
_FUNC = set("DE LA EL LOS LAS Y PARA DEL EN A CON POR QUE SOBRE AL O U E DA DO DOS DAS NO NA À".split())
_PILA = set(("JOSE JOSÉ JUAN LUIS CARLOS JORGE JAIME PEDRO MARIO RAFAEL MIGUEL VICTOR VÍCTOR MANUEL "
    "FERNANDO FRANCISCO ANTONIO ENRIQUE ROBERTO PATRICIO GUILLERMO EDUARDO RICARDO ALBERTO OSCAR ÓSCAR "
    "RAUL RAÚL SERGIO HUGO CESAR CÉSAR MARCELO GUSTAVO ERNESTO ANDRES ANDRÉS RAMIRO RODRIGO GABRIEL "
    "MARIA MARÍA ANA ROSA CARMEN SANDRA GLADYS SILVANA MIRYAM MYRIAN ELENA MARTHA MERCEDES LUCIA LUCÍA "
    "ALFONSO AUGUSTO VINICIO WALTER WASHINGTON HOMERO NELSON EDGAR EDISON DIEGO XAVIER FIDEL BOLIVAR "
    "HECTOR HÉCTOR ANIBAL ANÍBAL JULIO SIXTO ALEXANDRA CLAUDIA CYNTHIA IVAN IVÁN "
    "VICENTE ABELARDO BENICIO YAMILETH HERMES ARTURO ELPIDIO OSMAR EZEQUIEL CALIXTO LEONIDAS "
    "VIRGILIO ELOY ALCIBIADES ADRIAN ADRIÁN MOISES MOISÉS AURA SUSANA JERRY WILSON").split())


def _es_name_list(ctx: str) -> bool:
    toks = re.findall(r'[A-ZÁÉÍÓÚÑ]{2,}', ctx)
    if len(toks) < 5:
        return False
    func = sum(1 for t in toks if t in _FUNC)
    pila = sum(1 for t in toks if t in _PILA)
    if pila >= 2:                       # ≥2 nombres de pila reconocidos ⇒ pase de lista
        return True
    return func == 0                    # o cero palabra función ⇒ nombres, no título


G_TABLE  = re.compile(r'\b(INCISO|SECTOR|PLANILLA|REPARTIDO|CARPETA\s+N|EJECUTORA|CREDITO EJECUTADO|TRANSFERENCIAS|EROGACIONES)\b'
                      r'|\d\s*:\s*\d{2}\s*HORAS|\d{4,}|\d[.,]\d{3}|%\s')
G_STUT   = re.compile(r'(\b[A-ZÁÉÍÓÚÑa-z]{3,}\b)(\s+\1\b){2,}|ESIÓN ESIÓN|VESPER VESPER|MATINAL|\bTINA TINA\b'
                      r'|([A-ZÁÉÍÓÚÑ]\s){4,}')  # letras sueltas espaciadas = OCR degradado (AR/UY)


def clasifica(t: str, m: re.Match) -> str:
    """Devuelve 'JOIN' o el nombre del guardarraíl que la excluye."""
    ctx = t[max(0, m.start() - 70):min(len(t), m.end() + 70)]
    pre_ctx = t[max(0, m.start() - 70):m.start(2)]   # texto ANTES del corte (línea 1)
    seg2 = m.group(2)  # inicio de la 2ª línea
    if G_ROSTER.match(seg2) or _es_roster_back(pre_ctx): return "roster"
    if G_EPIG.match(seg2):          return "epig"
    if G_PARTY2.match(seg2):        return "party"
    if G_FURN.search(ctx):          return "furn"
    if G_ASIST.search(ctx):         return "asist"
    if G_ROLL.search(ctx):          return "roll"
    if G_PARTY.search(ctx):         return "party"
    if G_INDEX.search(ctx):         return "index"
    if G_STUT.search(ctx):          return "ocr"
    if _es_name_list(ctx):          return "namelist"
    if G_TABLE.search(ctx):         return "table"
    return "JOIN"


def _une(m: re.Match) -> str:
    if clasifica(m.string, m) != "JOIN":
        return m.group(0)                       # intacto
    g1, g2 = m.group(1), m.group(2)
    if g1.rstrip().endswith(","):
        return g1.rstrip().rstrip(",") + ", " + g2
    return g1.rstrip() + " " + g2


def unir_titulos(text: str, max_passes: int = 4) -> tuple[str, int]:
    """Une los títulos en versales partidos por el corte de columna. Devuelve (texto, nº uniones).

    Varias pasadas: un título puede venir envuelto en 3+ líneas. El nº de uniones = nº de `\\n`
    eliminados por el patrón (con su clasificador)."""
    if "\n" not in text:
        return text, 0
    new = text
    for _ in range(max_passes):
        nxt = SPLIT.sub(_une, new)
        if nxt == new:
            break
        new = nxt
    return new, text.count("\n") - new.count("\n")


def _run_cli(iso: str, show: int = 10, seed: int = 3) -> None:
    """Dry-run/diagnóstico sobre el CSV canónico de un país (verificación por muestreo)."""
    import csv, random, sys
    csv.field_size_limit(sys.maxsize)
    f = f"source/{iso}/standardize/{iso.upper()}_interventions.csv"
    join = skip = 0
    by: dict[str, int] = {}
    joins: list[str] = []
    with open(f, encoding="utf-8") as fh:
        sep = ";" if fh.readline().count(";") > 0 else ","
        fh.seek(0)
        for r in csv.DictReader(fh, delimiter=sep):
            t = r.get("text") or ""
            for m in SPLIT.finditer(t):
                c = clasifica(t, m)
                if c == "JOIN":
                    join += 1
                    frag = t[max(0, m.start() - 40):m.start(1)] + m.group(1).rstrip() + " ⟶ " + m.group(2)[:40]
                    joins.append(re.sub(r'\s+', ' ', frag).strip())
                else:
                    skip += 1
                    by[c] = by.get(c, 0) + 1
    tot = join + skip
    print(f"\n{iso.upper()}: candidatos={tot:,}  UNIR={join:,} ({join / max(tot, 1):.0%})  saltar={skip:,}  → {by}")
    random.seed(seed)
    for s in random.sample(joins, min(show, len(joins))):
        print(f"    ✓ {s[:150]}")


if __name__ == "__main__":
    import sys
    for _iso in sys.argv[1:]:
        _run_cli(_iso)
