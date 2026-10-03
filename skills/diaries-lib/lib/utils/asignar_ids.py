#!/usr/bin/env python3
"""Asigna `id_session` e `id_int`: identificadores únicos y estables de sesión e intervención.

Propuesta del investigador (2026-08-10), que resuelve de raíz la ambigüedad por fecha:

    CR · legislatura 19 · sesión 10 · intervención 120  →  CR019001000120

**Formato**, verificado contra los rangos reales de los 15 corpus:

    {ISO2}{legislatura:03d}{sesión:04d}{orden:05d}     14 caracteres
      2         3               4          5

    legislaturas por país   máx 132 (DO)      → 3 dígitos
    sesiones por legislatura máx 1.512 (BR)   → 4 dígitos
    orden de intervención    máx 16.459 (PA)  → 5 dígitos

`id_session` son los 9 primeros caracteres; `id_int` los 14. Un Prolegomena, con
`intervention_order = 0`, termina en `00000`.

## Por qué los ordinales se DERIVAN y no se copian

`legislature` es un texto distinto en cada país —`'1990-1994'`, `'LIV'`, `'XLII'`, `'PE35'`,
`'Constituyente'`, y vacío en BR y PY— y `session_number` puede ser alfanumérico (`104B`),
repetirse o faltar. Así que:

- la **legislatura** se ordena por la fecha más temprana de sus sesiones y recibe 1..N;
- la **sesión**, dentro de su legislatura, se ordena por fecha y número y recibe 1..M.

Los valores originales no se tocan: `legislature` y `session_number` siguen ahí. Lo que se añade
es una clave **estable, única y ordenable** que no depende de la fecha, que era justo el problema
([[feedback_sesiones_mismo_dia]]).

CLI:
    python asignar_ids.py --country cr [--medir]
"""
import argparse
import csv
import os
import re
import sys
from collections import defaultdict

csv.field_size_limit(sys.maxsize)


def _nat(s):
    """Orden natural del número de sesión: 12 < 12B < 13, y lo vacío al final."""
    m = re.match(r"\s*(\d+)", s or "")
    return (int(m.group(1)) if m else 10 ** 9, s or "")


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

    # 1 · legislaturas ordenadas por su fecha más temprana
    primera = {}
    for x in filas:
        L = x.get("legislature", "")
        f = x.get("date", "")
        if L not in primera or (f and f < primera[L]):
            primera[L] = f
    orden_leg = {L: i + 1 for i, L in enumerate(sorted(primera, key=lambda L: (primera[L], L)))}

    # 2 · sesiones ordenadas dentro de su legislatura
    ses = defaultdict(set)
    for x in filas:
        ses[x.get("legislature", "")].add((x.get("date", ""), x.get("session_number", "").strip()))
    orden_ses = {}
    for L, v in ses.items():
        for i, k in enumerate(sorted(v, key=lambda t: (t[0], _nat(t[1])))):
            orden_ses[(L, k[0], k[1])] = i + 1

    maxleg, maxses, maxord = len(orden_leg), max(len(v) for v in ses.values()), 0
    for x in filas:
        try:
            maxord = max(maxord, int(x["intervention_order"]))
        except ValueError:
            pass
    print(f"  {I} · legislaturas {maxleg} · máx sesiones/legislatura {maxses:,} · máx orden {maxord:,}")
    if maxleg > 999 or maxses > 9999 or maxord > 99999:
        print("  ✗ algún rango no cabe en el formato; abortado")
        return

    if "id_session" not in campos:
        campos = ["id_session", "id_int"] + campos
    hechos = set()
    for x in filas:
        L = x.get("legislature", "")
        nl = orden_leg[L]
        nsn = orden_ses[(L, x.get("date", ""), x.get("session_number", "").strip())]
        try:
            o = int(x["intervention_order"])
        except ValueError:
            o = 0
        x["id_session"] = f"{I}{nl:03d}{nsn:04d}"
        x["id_int"] = f"{x['id_session']}{o:05d}"
        hechos.add(x["id_session"])
    dupint = len(filas) - len({x["id_int"] for x in filas})
    print(f"     sesiones con id: {len(hechos):,} · id_int repetidos: {dupint:,}")
    if a.medir:
        for x in filas[:3]:
            print(f"       {x['id_int']}  ← leg {x.get('legislature','')!r} · ses "
                  f"{x.get('session_number','')!r} · orden {x['intervention_order']}")
        return
    if dupint:
        print("  ✗ hay id_int repetidos: no se escribe")
        return

    bak = p.replace(".csv", ".pre_ids.csv")
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
    print("  ✓ corpus reescrito con id_session e id_int")


if __name__ == "__main__":
    main()
