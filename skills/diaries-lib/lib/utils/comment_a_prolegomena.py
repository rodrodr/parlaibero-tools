#!/usr/bin/env python3
"""Las filas `COMMENT` de PE son la carátula: pasan a Prolegomena (`intervention_order = 0`).

Instrucción del investigador (2026-08-11): *«Lo que es COMMENT debería tener order 0 y ser
Prolegomena.»* Y tiene razón por el contenido: las 3.113 filas traen `DIARIO DE LOS DEBATES`, el
número y tipo de sesión, `PRESIDENCIA DE LOS SEÑORES…`, la fórmula de apertura «—A las 18:00
horas, bajo la Presidencia de…» y hasta el pie con la URL del Congreso. Ya llevan `dm_speech = 0`;
lo que les falta es el `intervention_order = 0` que las declara carátula.

## Tres casos, y solo dos se tocan

| caso | n | qué se hace |
|---|---|---|
| **es la primera fila y la sesión NO tiene Prolegomena** | — | pasa a orden 0 |
| **es la primera fila y la sesión YA tiene Prolegomena** | — | se FUNDE en él y la fila se elimina |
| **va a mitad de sesión** | — | ⚠ **no se toca** |

⚠ El tercer caso no es un COMMENT descolocado: es **la carátula de la SESIÓN SIGUIENTE** metida
dentro de la anterior —«1ª B SESIÓN COMPLEMENTARIA (Vespertina), MARTES 13 DE JUNIO DE 1995»— en
un corpus que tiene varias sesiones el mismo día. Moverlo al orden 0 de la sesión en la que está
lo pondría en la sesión EQUIVOCADA. Es un problema de identidad de sesión, no de carátula, y se
deja señalado en vez de resuelto a medias ([[feedback_sesiones_mismo_dia]]).

Tras mover, el resto de la sesión se renumera 1..N: el orden 0 no desplaza al resto, así que la
fila que era 1 y pasa a 0 deja un hueco que hay que cerrar.

CLI:
    python comment_a_prolegomena.py --country pe [--medir]
"""
import argparse
import csv
import os
import sys
from collections import defaultdict

csv.field_size_limit(sys.maxsize)


def _lee(p):
    with open(p, encoding="utf-8") as fh:
        d = csv.Sniffer().sniff(fh.readline(), ";,").delimiter
        fh.seek(0)
        r = csv.DictReader(fh, delimiter=d)
        return list(r.fieldnames), list(r), d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", required=True)
    ap.add_argument("--marca", default="COMMENT")
    ap.add_argument("--medir", action="store_true")
    a = ap.parse_args()
    iso, I = a.country.lower(), a.country.upper()
    p = f"source/{iso}/standardize/{I}_interventions.csv"
    campos, filas, d = _lee(p)

    # ⚠ La sesión se agrupa por (legislature, date, session_number), NO por `id_session`. En PE
    # ese trío NO es único —varias sesiones el mismo día comparten número— y `asignar_ids` y
    # `conformidad` usan el trío. Renumerando por `id_session` salían 237 `id_int` repetidos y
    # 911 sesiones rotas: la numeración tiene que hacerse con la MISMA clave con la que se
    # verifica, o el arreglo y su comprobación hablan de cosas distintas.
    def _clave(x):
        return (x.get("legislature", ""), x.get("date", ""), x.get("session_number", "").strip())

    ses = defaultdict(list)
    for i, x in enumerate(filas):
        ses[_clave(x)].append(i)

    a_cero, fundidas, intactas, quitar = 0, 0, 0, set()
    for k, idx in ses.items():
        com = [i for i in idx if filas[i]["speaker_raw"].strip().upper() == a.marca]
        if not com:
            continue
        prol = [i for i in idx if filas[i]["intervention_order"] == "0"]
        for j, i in enumerate(com):
            if i != idx[0] and not (j == 0 and i in idx[:2]):
                intactas += 1            # a mitad de sesión: es de OTRA sesión
                continue
            if prol:
                filas[prol[0]]["text"] = (filas[i]["text"].rstrip() + "\n\n"
                                          + filas[prol[0]]["text"].lstrip())
                quitar.add(i)
                fundidas += 1
            else:
                filas[i]["intervention_order"] = "0"
                filas[i]["dm_speech"] = "0"
                prol = [i]
                a_cero += 1

    print(f"  {I} · «{a.marca}» → Prolegomena: {a_cero:,} pasan a orden 0 · "
          f"{fundidas:,} fundidas en el Prolegomena existente")
    print(f"     a mitad de sesión, SIN tocar (carátula de la sesión siguiente): {intactas:,}")
    if a.medir:
        return

    salida = [x for i, x in enumerate(filas) if i not in quitar]
    # renumerar 1..N dentro de cada sesión; el orden 0 no cuenta
    porses = defaultdict(list)
    for i, x in enumerate(salida):
        porses[_clave(x)].append(i)
    rehechas = 0
    for k, idx in porses.items():
        n = 0
        for i in idx:
            if salida[i]["intervention_order"] == "0":
                continue
            n += 1
            if salida[i]["intervention_order"] != str(n):
                salida[i]["intervention_order"] = str(n)
                rehechas += 1
    print(f"     filas renumeradas: {rehechas:,} · corpus {len(filas):,} → {len(salida):,}")

    bak = p.replace(".csv", ".pre_comment.csv")
    tmp = p + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, delimiter=d)
        w.writeheader()
        w.writerows(salida)
    if not os.path.exists(bak):
        os.rename(p, bak)
    else:
        os.remove(p)
    os.rename(tmp, p)
    print("  ✓ corpus reescrito")


if __name__ == "__main__":
    main()
