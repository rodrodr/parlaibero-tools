"""
build_deputies_br.py — Construye deputies.csv para Brasil

Une 7 tablas relacionales en una tabla plana con una fila por
(diputado × legislatura × período de partido), con fechas efectivas
recortadas al período de la legislatura. Permite merge posterior
con la matriz de intervenciones usando la fecha de sesión.

Uso:
    python lib/utils/build_deputies_br.py
    python lib/utils/build_deputies_br.py --source source/br/deputies/ --output source/br/deputies/deputies.csv

⚠ POR QUÉ ES ESPECÍFICO DE ESTE PAÍS (revisado 2026-08-02)
Aplana las 7 tablas relacionales del portal de datos abiertos de la Câmara en un padrón. El esquema de origen es de BR y no se generaliza; el recorte de fechas al período de la legislatura sí, y vive en `bound_mandates_to_legislature.py`.
"""

import argparse
import sys
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = BASE_DIR / "source/br/deputies"
DEFAULT_OUTPUT = BASE_DIR / "source/br/deputies/deputies.csv"


def load_table(path: Path, date_cols: list[str] = None, utc: bool = False) -> pd.DataFrame:
    df = pd.read_csv(path, sep=";", dtype=str, na_values=["NA", ""])
    if date_cols:
        for col in date_cols:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], utc=utc, errors="coerce")
                if utc:
                    df[col] = df[col].dt.tz_localize(None)
    return df


def build(source_dir: Path, output_path: Path) -> pd.DataFrame:
    src = source_dir

    # --- Cargar tablas ---
    dep = load_table(src / "br_diputado.csv")
    dep_leg = load_table(src / "br_diputado_legislatura.csv", ["dt_alta", "dt_baja"], utc=True)
    dep_dist = load_table(src / "br_diputado_distrito.csv")
    dep_part = load_table(src / "br_diputado_partido.csv", ["dt_alta", "dt_baja"], utc=True)
    leg = load_table(src / "br_legislatura.csv", ["dt_inicio", "dt_fin"])
    distrito = load_table(src / "br_distrito.csv")

    # --- Paso 1: (diputado × legislatura) con fechas de legislatura ---
    base = dep_leg[["id_diputado", "id_legislatura"]].merge(
        leg[["id_legislatura", "dt_inicio", "dt_fin"]],
        on="id_legislatura",
        how="left",
    )

    # --- Paso 2: Añadir distrito ---
    base = base.merge(
        dep_dist[["id_diputado", "id_legislatura", "id_distrito"]],
        on=["id_diputado", "id_legislatura"],
        how="left",
    ).merge(
        distrito[["id_distrito", "nm_distrito", "cd_adm_iso"]],
        on="id_distrito",
        how="left",
    )

    # --- Paso 3: Cruce con partidos (cartesiano por diputado, luego filtro solapamiento) ---
    crossed = base.merge(
        dep_part[["id_diputado", "sgl_partido", "dt_alta", "dt_baja"]].rename(
            columns={"dt_alta": "dt_alta_part", "dt_baja": "dt_baja_part"}
        ),
        on="id_diputado",
        how="left",
    )

    # Solapa: el período del partido intersecta con el período de la legislatura
    mask = (crossed["dt_alta_part"] < crossed["dt_fin"]) & (
        crossed["dt_baja_part"] > crossed["dt_inicio"]
    )
    crossed = crossed[mask].copy()

    # --- Paso 4: Fechas efectivas (recortadas al período de la legislatura) ---
    crossed["dt_inicio_partido"] = crossed[["dt_alta_part", "dt_inicio"]].max(axis=1).dt.date
    crossed["dt_fin_partido"] = crossed[["dt_baja_part", "dt_fin"]].min(axis=1).dt.date

    # --- Paso 5: Añadir nombre y alias del diputado ---
    crossed = crossed.merge(
        dep[["id_diputado", "nombre_completo", "alias"]],
        on="id_diputado",
        how="left",
    )

    # --- Paso 6: Seleccionar y renombrar columnas de salida ---
    result = crossed[
        [
            "id_diputado",
            "alias",
            "id_legislatura",
            "nm_distrito",
            "sgl_partido",
            "dt_inicio_partido",
            "dt_fin_partido",
        ]
    ].rename(columns={"id_diputado": "id_dep", "nm_distrito": "distrito"})

    result = result.sort_values(["id_dep", "id_legislatura", "dt_inicio_partido"]).reset_index(drop=True)

    return result


def print_stats(df: pd.DataFrame) -> None:
    print(f"Total filas          : {len(df):,}")
    print(f"Diputados únicos     : {df['id_dep'].nunique():,}")
    print(f"Legislaturas         : {sorted(df['id_legislatura'].unique())}")
    print(f"Partidos únicos      : {df['sgl_partido'].nunique():,}")
    print(f"Nulos sgl_partido    : {df['sgl_partido'].isna().sum():,}")
    print(f"Nulos distrito       : {df['distrito'].isna().sum():,}")
    print()
    print("Filas por legislatura:")
    print(df.groupby("id_legislatura").size().to_string())
    print()
    multi = (
        df.groupby(["id_dep", "id_legislatura"])["sgl_partido"]
        .nunique()
        .pipe(lambda s: (s > 1).sum())
    )
    print(f"Diputados con >1 partido en misma legislatura: {multi:,}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Construye deputies.csv para Brasil")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if not args.source.exists():
        print(f"Error: directorio fuente no encontrado: {args.source}", file=sys.stderr)
        sys.exit(1)

    print(f"Fuente : {args.source}")
    print(f"Salida : {args.output}")
    print()

    df = build(args.source, args.output)
    df.to_csv(args.output, sep=";", index=False)

    print(f"Escrito: {args.output} ({len(df):,} filas)\n")
    print_stats(df)


if __name__ == "__main__":
    main()
