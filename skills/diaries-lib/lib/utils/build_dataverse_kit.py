#!/usr/bin/env python3
"""Construye el kit de publicación de ParlaIbero para Harvard Dataverse.

Genera, por país, la carpeta que se deposita como *dataset* dentro de la colección
ParlaIbero, con los metadatos en el formato que exige la **Native API** de Dataverse
(bloques `citation` y `socialscience`), el manifiesto de archivos con sus sumas de
verificación y la documentación ya existente en `docs/{iso2}/`.

    dataverse_kit/
    ├── README.md                     ← procedimiento de depósito
    ├── collection.json               ← descripción de la colección ParlaIbero
    └── {iso2}/
        ├── dataset.json              ← payload de la Native API (citation + socialscience)
        ├── MANIFEST.csv              ← archivo · rol · bytes · sha256 · descripción
        ├── README.md · data_dictionary.md · process_report.md · dataset.jsonld
        └── data/                     ← ENLACES SIMBÓLICOS a los datos, no copias

Los datos **no se copian**: 8,2 GB duplicados no caben, y el depósito se hace desde el
enlace. Los `.pre_*` son copias de trabajo del pipeline y **no se publican**; las de
cuarentena sí, porque documentan qué se retiró y permiten rehacerlo.

Uso:  python3 construir_kit_dataverse.py [--apply]
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

PAISES = ["ar", "br", "cl", "co", "cr", "do", "es", "gt", "mx", "pa", "pe", "pt", "py", "sv", "uy"]
KIT = Path("dataverse_kit")

NOMBRE = {"ar": "Argentina", "br": "Brazil", "cl": "Chile", "co": "Colombia", "cr": "Costa Rica",
          "do": "Dominican Republic", "es": "Spain", "gt": "Guatemala", "mx": "Mexico",
          "pa": "Panama", "pe": "Peru", "pt": "Portugal", "py": "Paraguay",
          "sv": "El Salvador", "uy": "Uruguay"}
CAMARA = {"ar": "Cámara de Diputados de la Nación", "br": "Câmara dos Deputados",
          "cl": "Cámara de Diputados", "co": "Cámara de Representantes",
          "cr": "Asamblea Legislativa", "do": "Cámara de Diputados",
          "es": "Congreso de los Diputados", "gt": "Congreso de la República",
          "mx": "Cámara de Diputados", "pa": "Asamblea Nacional",
          "pe": "Congreso de la República", "pt": "Assembleia da República",
          "py": "Cámara de Diputados", "sv": "Asamblea Legislativa",
          "uy": "Cámara de Representantes"}
IDIOMA = {"br": "Portuguese", "pt": "Portuguese"}

AUTORES = [
    ("Rodrigues-Silveira, Rodrigo", "Universidad de Salamanca", "ORCID", ""),
    ("Martínez Osorio, Guillermo", "Universidad de Salamanca", "ORCID", ""),
]
CONTACTO = [("Rodrigues-Silveira, Rodrigo", "Universidad de Salamanca", "rodrodr@usal.es")]

ROL = {  # sufijo de archivo → (rol, descripción para el manifiesto)
    "_interventions.csv": ("primary",
        "Matriz principal de intervenciones parlamentarias en el esquema canónico de ParlaIbero."),
    "_deputies.csv": ("ancillary",
        "Padrón de diputados: identificador, nombre, sexo, partido, distrito y mandato. "
        "Se une a la matriz principal por `id_dep`."),
    "_sidecar_no_discurso.csv": ("ancillary",
        "Filas retiradas de la matriz por no ser discurso (sumarios, listas de votación). "
        "Reasociables por date + session_number + intervention_order."),
    "_sidecar_documentos.csv": ("ancillary",
        "Documentos leídos en sala segmentados fuera del texto de las intervenciones."),
    "_sidecar_decretos.csv": ("ancillary",
        "Textos de decretos y dictámenes leídos en sala, separados del discurso."),
    "_tipo_source_sidecar.csv": ("ancillary",
        "Procedencia y tipo de cada fila de la matriz principal, alineado fila a fila."),
    "_quarantine_intrasesion_dups.csv": ("ancillary",
        "Filas duplicadas dentro de una misma sesión retiradas en la deduplicación."),
    "_quarantine_filas_solo_folio.csv": ("ancillary",
        "Filas cuyo texto era solo un folio o cabecera de página."),
    "_folios_eliminados.csv": ("ancillary",
        "Registro de los folios y cabeceras retirados del texto."),
}

DESCRIPCION = """<p><b>ParlaIbero</b> es un corpus armonizado de intervenciones parlamentarias
de {pais} ({camara}), construido a partir de los diarios de sesiones oficiales.
Cubre <b>{periodo}</b> e incluye <b>{n_int:,} intervenciones</b> en <b>{n_ses:,} sesiones</b>,
atribuidas a <b>{n_dip:,} parlamentarios</b> identificados.</p>

<p>El corpus forma parte de ParlaIbero, que aplica el mismo esquema canónico de once
columnas a quince países iberoamericanos, de modo que los datos de {pais} son directamente
comparables con los del resto de la colección.</p>

<p><b>Vinculación de oradores.</b> El {bruto:.1f}% de las intervenciones lleva identificador
de parlamentario. La cifra bruta no es comparable entre países, porque depende de cuánto
discurso atribuye cada cámara a cargos de mesa sin nombrarlos; descontados esos cargos, la
vinculación <i>efectiva</i> es del <b>{efectivo:.1f}%</b>. Ambas se documentan en el
informe de proceso.</p>

<p><b>Datos auxiliares.</b> Se publica junto a la matriz el padrón de parlamentarios,
unible por <code>id_dep</code>, con la variable derivada <code>sex</code> y su procedencia
declarada en <code>sex_source</code>.</p>"""


def sha256(p: Path, tope: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(tope), b""):
            h.update(b)
    return h.hexdigest()


def campo(nombre, valor, tipo="primitive", multiple=False):
    return {"typeName": nombre, "multiple": multiple, "typeClass": tipo, "value": valor}


def compuesto(nombre, filas):
    return {"typeName": nombre, "multiple": True, "typeClass": "compound", "value": filas}


def info(iso2: str) -> dict:
    p = Path(f"docs/{iso2}/corpus_info.json")
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def dataset_json(iso2: str, ci: dict) -> dict:
    pais = NOMBRE[iso2]
    est = ci.get("estadisticas", ci.get("statistics", {}))
    n_int = int(est.get("intervenciones", est.get("interventions", 0)) or 0)
    n_ses = int(est.get("sesiones", est.get("sessions", 0)) or 0)
    n_dip = int(est.get("diputados", est.get("deputies", 0)) or 0)
    periodo = str(est.get("periodo", est.get("period", "")) or "")
    bruto = float(est.get("vinculacion_bruta", est.get("linkage_gross", 0)) or 0)
    efect = float(est.get("vinculacion_efectiva", est.get("linkage_effective", bruto)) or bruto)
    ini, fin = (periodo.split("–") + [""])[:2] if "–" in periodo else (periodo, periodo)

    desc = DESCRIPCION.format(pais=pais, camara=CAMARA[iso2], periodo=periodo or "s. d.",
                              n_int=n_int, n_ses=n_ses, n_dip=n_dip,
                              bruto=bruto, efectivo=efect)
    idioma = IDIOMA.get(iso2, "Spanish")

    citation = [
        campo("title", f"ParlaIbero — Parliamentary Interventions of {pais}, {periodo}"),
        compuesto("author", [{
            "authorName": campo("authorName", a),
            "authorAffiliation": campo("authorAffiliation", af),
        } for a, af, _, _ in AUTORES]),
        compuesto("datasetContact", [{
            "datasetContactName": campo("datasetContactName", n),
            "datasetContactAffiliation": campo("datasetContactAffiliation", af),
            "datasetContactEmail": campo("datasetContactEmail", e),
        } for n, af, e in CONTACTO]),
        compuesto("dsDescription", [{"dsDescriptionValue": campo("dsDescriptionValue", desc)}]),
        campo("subject", ["Social Sciences"], "controlledVocabulary", True),
        compuesto("keyword", [{"keywordValue": campo("keywordValue", k)} for k in (
            "parliamentary debates", "legislative speech", "text corpus", pais,
            "Ibero-America", "political representation", "ParlaIbero")]),
        campo("language", [idioma], "controlledVocabulary", True),
        campo("kindOfData", ["Text", "Event/Transaction Data"], "primitive", True),
        compuesto("software", [{"softwareName": campo("softwareName", "ParlaIbero pipeline")}]),
        compuesto("timePeriodCovered", [{
            "timePeriodCoveredStart": campo("timePeriodCoveredStart", ini),
            "timePeriodCoveredEnd": campo("timePeriodCoveredEnd", fin),
        }]),
        compuesto("dateOfCollection", [{
            "dateOfCollectionStart": campo("dateOfCollectionStart", "2026-01-01"),
            "dateOfCollectionEnd": campo("dateOfCollectionEnd", "2026-07-30"),
        }]),
    ]
    social = [
        campo("unitOfAnalysis", ["Parliamentary intervention (a continuous turn of speech "
                                 "attributed to a single speaker in the official record)"],
              "primitive", True),
        campo("universe", [f"All interventions recorded in the official session diaries of the "
                           f"{CAMARA[iso2]} of {pais} for the period {periodo}."],
              "primitive", True),
        campo("timeMethod", "Longitudinal: Trend/Repeated cross-section"),
        campo("collectionMode", ["Content coding of official published records"], "primitive", True),
        campo("dataSources", [f"Diario de Sesiones / Diário da Assembleia — {CAMARA[iso2]}, {pais}"],
              "primitive", True),
        campo("cleaningOperations",
              "OCR where the source was a scanned image; header and folio removal; speaker "
              "marker detection and attribution; deduplication at session and row level; "
              "linkage of speakers to a deputy roster by fuzzy name matching with mandate-date "
              "disambiguation; separation of non-speech material to reversible sidecar files."),
    ]
    return {"datasetVersion": {
        "license": {"name": "CC BY 4.0", "uri": "http://creativecommons.org/licenses/by/4.0/"},
        "metadataBlocks": {
            "citation": {"displayName": "Citation Metadata", "name": "citation", "fields": citation},
            "socialscience": {"displayName": "Social Science and Humanities Metadata",
                              "name": "socialscience", "fields": social},
        }}}


def archivos(iso2: str) -> list[tuple[Path, str, str]]:
    """→ [(ruta, rol, descripción)] de lo que se publica."""
    out = []
    for p in sorted(Path(f"source/{iso2}/standardize").glob("*.csv")):
        if ".pre_" in p.name:
            continue                       # copia de trabajo del pipeline
        for suf, (rol, des) in ROL.items():
            if p.name.endswith(suf):
                out.append((p, rol, des))
                break
    return out


def main(apply: bool) -> None:
    print(f"{'':4} {'archivos':>8} {'GB':>7}  documentación")
    print("-" * 72)
    total = 0
    for c in PAISES:
        ci = info(c)
        ds = dataset_json(c, ci)
        fs = archivos(c)
        gb = sum(p.stat().st_size for p, _, _ in fs) / 1073741824
        total += gb
        docs = [d for d in ("README.md", "data_dictionary.md", "process_report.md",
                            "dataset.jsonld") if Path(f"docs/{c}/{d}").exists()]
        print(f"{c.upper():4} {len(fs):8} {gb:7.2f}  {', '.join(docs)}")

        if not apply:
            continue
        d = KIT / c
        (d / "data").mkdir(parents=True, exist_ok=True)
        (d / "dataset.json").write_text(json.dumps(ds, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
        for doc in docs:
            (d / doc).write_bytes(Path(f"docs/{c}/{doc}").read_bytes())
        man = []
        for p, rol, des in fs:
            enl = d / "data" / p.name
            if enl.is_symlink() or enl.exists():
                enl.unlink()
            enl.symlink_to(p.resolve())
            man.append({"file": p.name, "role": rol, "bytes": p.stat().st_size,
                        "sha256": sha256(p), "description": des})
        pd.DataFrame(man).to_csv(d / "MANIFEST.csv", index=False, encoding="utf-8")

    print("-" * 72)
    print(f"{'TOT':4} {'':8} {total:7.2f} GB")
    if not apply:
        print(f"\n--- SIMULACIÓN --- (usa --apply para escribir {KIT}/)")


if __name__ == "__main__":
    main("--apply" in sys.argv)
