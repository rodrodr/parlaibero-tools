#!/usr/bin/env python3
"""Elimina las filas sin texto y renumera la jornada. Una fila vacía no significa nada.

Decisión del investigador (2026-08-10): «una fila sin texto es un sinsentido en esa base de
datos». Y es exacto — el corpus es una matriz de INTERVENCIONES: una fila sin `text` no
documenta nada, no se puede leer, no se puede contar y no se puede citar. Da igual que tenga
orador y `id_dep`: lo que aporta una intervención es lo que se dijo.

De dónde salieron: al retirar el mobiliario de página, 121 filas de BR se quedaron vacías porque
su texto **era solo cabecera** ([[feedback_mobiliario_br_page]]). No es que se hayan vaciado
ahora: nunca tuvieron discurso, y el mobiliario lo disimulaba. PE aporta otras 46.

Esto NO contradice «nada se borra, se declara»: esa regla protege el CONTENIDO —el documento
leído, el recuento de votación, el sumario—, que se queda en el corpus con `dm_speech = 0`. Aquí
no hay contenido que proteger.

Tras eliminarlas se **renumera `intervention_order`** por jornada, de 1 en adelante y en el orden
de registro, para que no queden huecos. Los Prolegomena conservan su 0.

CLI:
    python quitar_filas_sin_texto.py --country br [--medir]
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
    ap.add_argument("--medir", action="store_true")
    a = ap.parse_args()
    iso, I = a.country.lower(), a.country.upper()
    p = f"source/{iso}/standardize/{I}_interventions.csv"
    campos, filas, d = _lee(p)

    vacias = [x for x in filas if not x["text"].strip()]
    if not vacias:
        print(f"  {I} · ninguna fila sin texto")
        return
    jornadas = {(x.get("legislature", ""), x["date"]) for x in vacias}
    print(f"  {I} · filas sin texto: {len(vacias):,} en {len(jornadas):,} jornadas"
          f" · con id_dep {sum(1 for x in vacias if x['id_dep'].strip()):,}")
    if a.medir:
        for x in vacias[:5]:
            print(f"     [{x['date']}] orden {x['intervention_order']} "
                  f"{x['speaker_raw'][:30]!r} id={x['id_dep'] or '—'}")
        return

    salida = [x for x in filas if x["text"].strip()]
    cnt = defaultdict(int)
    for y in salida:
        if y["intervention_order"] == "0":     # los Prolegomena conservan su 0
            continue
        k = (y.get("legislature", ""), y["date"], y.get("session_number", "").strip())
        cnt[k] += 1
        y["intervention_order"] = str(cnt[k])

    bak = p.replace(".csv", ".pre_vacias.csv")
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
    print(f"  ✓ corpus {len(filas):,} → {len(salida):,} filas · orden renumerado en"
          f" {len(jornadas):,} jornadas")


if __name__ == "__main__":
    main()
