"""Proyecto sintético para la vinculación efectiva tr-0109 (y su comparación con tr-0003).

Lo usan las pruebas de diaries-lib y las de diaries-report. ZZ tiene 119 filas; el paquete
(dataverse/paquetes/ZZ/ZZ_interventions.csv) es un enlace a source/zz/standardize, como en el proyecto:

    habla (dm_speech = 1)    112, de las que 60 vinculadas
    sin escaño               20: NO se reclasifica, lo publica corpus_info.json (aquí, 10 RELATOR
                             + 10 SECRETARIO (Administrativo))
    no atribuibles           12: 4 «Varios señores diputados», 3 «Un señor DIPUTADO», 2 «El señor»,
                             1 «N.N.» y 2 filas de habla sin orador
    no se descuentan         10 PRESIDENTE a secas, 5 «EL SEÑOR MARIO ROSSI, PRESIDENTE DE LA
                             COMISIÓN» y 5 «Juan Pérez»
    fuera del habla          5 filas sin orador y 2 vinculadas con dm_speech = 0

    tr-0109                  60 / (112 − 20 − 12) = 75,00 %; bruta 60 / 112 = 53,57 %
    tr-0003                  62 / (119 − 20) = 62,63 % (vinculacion_efectiva.py: todas las filas)
    fragmento antiguo        81,5 % (el python3 -c del Paso 3-bis de diaries-report)
"""
import csv
import json
import os
from pathlib import Path

ESPERADO = dict(filas=119, filas_habla=112, vinculadas=60, sin_escano=20, no_atribuibles=12,
                filas_sin_orador=7, denominador=80, efectiva_pct=75.0, bruta_pct=53.57,
                tr0003_efectiva_pct=62.63)

FILAS = ([(f"El señor Diputado Número{i}", f"ZZ{i:03d}", "1") for i in range(60)]
         + [("RELATOR", "", "1")] * 10
         + [("SECRETARIO (Administrativo)", "", "1")] * 10
         + [("PRESIDENTE", "", "1")] * 10
         + [("Varios señores diputados", "", "1")] * 4
         + [("Un señor DIPUTADO", "", "1")] * 3
         + [("El señor", "", "1")] * 2
         + [("N.N.", "", "1")]
         + [("", "", "1")] * 2
         + [("Juan Pérez", "", "1")] * 5
         + [("EL SEÑOR MARIO ROSSI, PRESIDENTE DE LA COMISIÓN", "", "1")] * 5
         + [("", "", "0")] * 5
         + [("El señor Diputado Número1", "ZZ001", "0")] * 2)


def linkage_publicado(**cambios) -> dict:
    """El bloque `linkage` tal como lo deja tr-0109 (linkage_no_atribuibles.py) para estos datos."""
    bloque = {
        "definition": ("effective = linked / (total speech rows − rows spoken by someone who CANNOT "
                       "hold a seat − rows the record itself makes UNATTRIBUTABLE). Same definition "
                       "across all sixteen corpora (tr-0109: unattributable rows discounted; the "
                       "previous figure is kept as effective_previous_definition)."),
        "total_rows": 119, "speech_rows": 112, "linked": 60, "gross": round(60 / 112, 12),
        "cannot_hold_seat_discounted": 20, "unattributable_rows": 12,
        "effective": round(60 / 80, 12), "effective_previous_definition": 0.7,
        "rows_without_speaker": 7,
    }
    bloque.update(cambios)
    return bloque


def crea_proyecto(raiz: Path, sep: str = ",", linkage=None, paquete: bool = True, extra=()) -> Path:
    """Escribe el proyecto sintético en `raiz` y lo devuelve. `linkage=False` omite el bloque;
    `extra` añade filas (speaker_raw, id_dep, dm_speech) que no entran en ESPERADO."""
    std = raiz / "source" / "zz" / "standardize"
    std.mkdir(parents=True)
    with open(std / "ZZ_interventions.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=sep)
        w.writerow(["date", "speaker_raw", "id_dep", "dm_speech", "text"])
        w.writerows([("2001-01-01", s, i, dm, "x") for s, i, dm in FILAS + list(extra)])
    if paquete:
        pk = raiz / "dataverse" / "paquetes" / "ZZ"
        pk.mkdir(parents=True)
        os.symlink("../../../source/zz/standardize/ZZ_interventions.csv", pk / "ZZ_interventions.csv")
    docs = raiz / "docs" / "zz"
    docs.mkdir(parents=True)
    ci = {"country": "ZZ"}
    if linkage is not False:
        ci["linkage"] = linkage_publicado() if linkage is None else linkage
    (docs / "corpus_info.json").write_text(json.dumps(ci, ensure_ascii=False, indent=2), encoding="utf-8")
    return raiz
