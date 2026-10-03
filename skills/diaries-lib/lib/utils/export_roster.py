#!/usr/bin/env python3
"""Exporta el padrón de cada país como **ancillary data** publicable junto a la matriz.

Los padrones nacionales son **independientes por diseño** (cada cámara se rige por
reglas distintas: mandatos por legislatura o por persona, transfuguismo registrado
o no, distrito uninominal o plurinominal). No se homogeneízan: se emite un
**núcleo común** de columnas —el que permite unir con la matriz y hacer análisis
comparado— y se **conservan al final las columnas propias** de cada país, que se
documentan en su diccionario de datos.

Núcleo común (en el orden de salida):

    id_dep · speaker_name · first_name · last_name · sex · sex_source
    party · parliamentary_group · district · legislature · start_date · end_date · notes

Una columna del núcleo que el país no registre sale **vacía**, nunca inventada.
`sex`/`sex_source` se toman de `{ISO2}_sex.csv` si existe (ver derivar_sexo.py).

⚠ BR no tiene columna de nombre en su padrón: el nombre publicable es `alias`,
que es la forma con la que la Cámara identifica al parlamentario. Se declara.

Uso:  python3 exportar_padron.py [--apply]
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# ⚠ EC faltaba de la lista hasta el 2026-09-02: su padrón publicable era el del 18-ago.
PAISES = ["ar", "br", "cl", "co", "cr", "do", "ec", "es", "gt", "mx", "pa", "pe", "pt", "py", "sv", "uy"]

NUCLEO = ["id_dep", "speaker_name", "first_name", "last_name", "sex", "sex_source",
          "party", "parliamentary_group", "district", "legislature",
          "start_date", "end_date", "notes"]

# nombre del núcleo → nombres posibles en los padrones nacionales, por prioridad
ALIAS = {
    "id_dep":             ["id_dep", "diputado_id"],
    "speaker_name":       ["nombre_completo", "speaker_name", "nombre_original", "alias"],
    "first_name":         ["nombre", "nombre_propio", "first_name"],
    "last_name":          ["apellidos", "last_name"],
    "party":              ["partido", "party", "sgl_partido", "formacion_electoral"],
    "parliamentary_group": ["grupo_parlamentario", "grupos_parlamentarios", "grupo_ultimo"],
    "district":           ["circunscripcion", "distrito", "district", "provincia", "entidad"],
    "legislature":        ["legislatura", "legislature", "legislatura_num", "id_legislatura"],
    "start_date":         ["fecha_inicio", "fecha_alta", "start_date", "dt_inicio_partido"],
    "end_date":           ["fecha_fin", "fecha_baja", "end_date", "dt_fin_partido"],
    "notes":              ["notas", "notes"],
}


def ruta_padron(iso2: str) -> Path | None:
    for nombre in ("deputies.csv", "diputados_bd.csv"):
        p = Path(f"source/{iso2}/deputies/{nombre}")
        if p.exists():
            return p
    return None


def leer(p: Path) -> pd.DataFrame:
    head = p.open(encoding="utf-8", errors="replace").readline()
    sep = ";" if head.count(";") > head.count(",") else ","
    return pd.read_csv(p, sep=sep, dtype=str, keep_default_na=False)


def construir(iso2: str, r: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    usadas, out = set(), {}
    for destino, candidatos in ALIAS.items():
        low = {c.lower(): c for c in r.columns}
        for cand in candidatos:
            if cand in low and low[cand] not in usadas:
                out[destino] = r[low[cand]]
                usadas.add(low[cand])
                break
        else:
            out[destino] = ""
    df = pd.DataFrame(out)
    # `sex`/`sex_source` ya están en el núcleo: si el padrón de trabajo los trae
    # (los escribe sexo_a_padron.py), no deben repetirse como columna propia
    df["sex"] = r["sex"] if "sex" in r.columns else ""
    df["sex_source"] = r["sex_source"] if "sex_source" in r.columns else ""
    # Nombres de persona SIEMPRE en MAYÚSCULAS, en los dieciséis padrones (regla del
    # investigador, 2026-09-01). La caja la fija cada fuente nacional y esa mezcla
    # llegaba tal cual al corpus. `.upper()` respeta los diacríticos.
    for _c in ("speaker_name", "first_name", "last_name"):
        if _c in df.columns:
            _v = df[_c]
            df[_c] = _v.where(_v.isna(), _v.astype(str).str.upper())

    # legislatura guardada en `notas` («legislatura:1984-1986 · fuente:…», EC): si la columna
    # no existe o está vacía, se recupera de ahí. Solo rellena, nunca sobrescribe.
    if "notes" in df.columns:
        _rec = df["notes"].astype(str).str.extract(r"legislatura:([^ ·;]+)")[0]
        _leg = df["legislature"].astype(str)
        df["legislature"] = _leg.where(_leg.str.strip() != "", _rec.fillna(""))

    # vocabulario ÚNICO de `sex_source` en la colección (el que declara corpus_info.sex_variable);
    # EC escribía las etiquetas en español («nombre:morfologia»).
    _SEXSRC = {"nombre:morfologia": "given_name_morph", "nombre": "given_name", "nombre:raro": "given_name_rare",
               "tratamiento": "honorific", "registro_oficial": "official_registry", "padron": "roster"}
    if "sex_source" in df.columns:
        df["sex_source"] = df["sex_source"].astype(str).map(lambda v: _SEXSRC.get(v, v))

    extras = [c for c in r.columns if c not in usadas and c not in ("sex", "sex_source")]
    for c in extras:
        df[c] = r[c].values
    return df[NUCLEO + extras], extras


def main(apply: bool, paises=None) -> None:
    """`paises`: lista de iso2 a exportar; None = los 16. ⚠ Exportar TODOS desde la cadena de UN país pisa los padrones
    publicables que otro país ya post-procesó (ES: legislature = etiqueta + legislature_number), y desfasa su documentación
    en el panel (2026-09-03). Las cadenas pasan --country."""
    print(f"{'':4} {'filas':>7} {'personas':>9} {'sexo':>7}  columnas propias conservadas")
    print("-" * 96)
    for c in (paises or PAISES):
        p = ruta_padron(c)
        if p is None:
            print(f"{c.upper():4} sin padrón")
            continue
        r = leer(p)
        df, extras = construir(c, r)

        sx = Path(f"source/{c}/deputies/{c.upper()}_sex.csv")
        if sx.exists():
            # ⚠ El fichero lateral RELLENA y CORRIGE, pero NO borra. Antes sustituía la columna
            # entera, así que toda persona ausente de él salía SIN SEXO del padrón publicado
            # aunque el padrón de trabajo lo tuviera — en CO, los 3 presidentes añadidos el
            # 2026-09-01. Un `.fillna("")` sobre un `map` es exactamente eso: un borrado.
            s = pd.read_csv(sx, dtype=str, keep_default_na=False).set_index("id_dep")
            for _col in ("sex", "sex_source"):
                _nuevo = df.id_dep.map(s[_col])
                df[_col] = _nuevo.where(_nuevo.notna() & (_nuevo.astype(str).str.strip() != ""),
                                        df[_col] if _col in df.columns else "")

        npers = df.id_dep.nunique()
        psex = 100 * (df.drop_duplicates("id_dep").sex != "").mean()
        print(f"{c.upper():4} {len(df):7,} {npers:9,} {psex:6.1f}%  {', '.join(extras) or '—'}")

        if apply:
            dst = Path(f"source/{c}/standardize/{c.upper()}_deputies.csv")
            # ⚠ Escribir SOLO si el contenido cambia. Reescribir los dieciséis en cada pasada
            # les daba una fecha nueva sin cambiar un byte, y el panel marcaba «document
            # parcial» en países cerrados: la documentación parecía caducada frente a un
            # padrón que era idéntico. Un fichero con la misma fecha que ayer es información.
            nuevo = df.to_csv(index=False)
            if dst.exists() and dst.read_text(encoding="utf-8") == nuevo:
                print(f"     {c.upper()} sin cambios · no se reescribe")
            else:
                dst.write_text(nuevo, encoding="utf-8")

    if not apply:
        print("\n--- SIMULACIÓN --- (usa --apply para escribir "
              "source/{iso2}/standardize/{ISO2}_deputies.csv)")


if __name__ == "__main__":
    import sys
    argv = sys.argv[1:]
    paises = None
    if "--country" in argv:
        i = argv.index("--country"); paises = [x.strip().lower() for x in argv[i + 1].split(",")]; argv = argv[:i] + argv[i + 2:]
    main("--apply" in argv, paises)
