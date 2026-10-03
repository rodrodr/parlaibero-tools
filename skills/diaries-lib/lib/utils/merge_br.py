"""
merge_br.py — Transforma la matriz de Brasil al esquema canónico ParlaIbero

La nueva matriz (generada en R) ya incluye party, district, speaker_name e id_dip.
No se necesita ningún join con deputies.csv — este script solo parsea id_sesion,
mapea session_type y renombra columnas.

Uso:
    python lib/utils/merge_br.py
    python lib/utils/merge_br.py --matrix path/BR_diarios.csv \
        --output path/interventions_enriched.csv

⚠ POR QUÉ ES ESPECÍFICO DE ESTE PAÍS (revisado 2026-08-02)
Adopta al esquema canónico la matriz de BR, construida fuera del pipeline. El renombrado de columnas ya lo hace `standardize_csv.py` con `_COLUMN_ALIASES` del country_config; lo único propio de BR es el parseo de su `id_sesion`.
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_MATRIX = BASE_DIR / "source/br/matrix/BR_diarios.csv"
DEFAULT_OUTPUT = BASE_DIR / "source/br/merge/interventions_enriched.csv"

SESSION_TYPE_MAP = {
    "Ordinária - CD":                    "Ordinaria",
    "Ordinária - CN":                    "Ordinaria",
    "Deliberativa Ordinária - CD":       "Ordinaria",
    "Extraordinária - CD":               "Extraordinaria",
    "Extraordinária - CN":               "Extraordinaria",
    "Deliberativa Extraordinária - CD":  "Extraordinaria",
    "Solene - CD":                       "Solemne",
    "Solene - CN":                       "Solemne",
    "Não Deliberativa Solene - CD":      "Solemne",
    "Não Deliberativa de Debates - CD":  "Otra",
    "Preparatória":                      "Otra",
    "Comissão Geral":                    "Otra",
    "Outro Evento":                      "Otra",
}


def parse_session_id(id_sesion: pd.Series) -> pd.DataFrame:
    """Extrae legislature (4 primeros chars) y session_number (dígitos+letra tras S).

    Ejemplo: BR52P1S001O → legislature=BR52, session_number=001O
    """
    legislature    = id_sesion.str[:4]
    session_number = id_sesion.str.extract(r'S(\d+[A-Z]?)', expand=False)
    return pd.DataFrame({"legislature": legislature, "session_number": session_number})


def transform(matrix_path: Path, output_path: Path) -> dict:
    print("Cargando matriz…")
    mat = pd.read_csv(matrix_path, sep=";", dtype=str,
                      keep_default_na=False, na_values=["NA", ""])
    total_rows = len(mat)

    # Parsear session info
    session = parse_session_id(mat["id_sesion"])
    mat["legislature"]    = session["legislature"]
    mat["session_number"] = session["session_number"]
    mat["session_type"]   = mat["nm_sesion"].map(SESSION_TYPE_MAP)
    mat["date"]           = pd.to_datetime(mat["dt_sesion"], errors="coerce").dt.date

    unmapped = mat["nm_sesion"].notna() & mat["session_type"].isna()
    if unmapped.any():
        print(f"  AVISO: {unmapped.sum()} filas con nm_sesion no mapeado:")
        print("  ", mat.loc[unmapped, "nm_sesion"].value_counts().to_string())

    # Renombrar al esquema canónico (corrigiendo typo sepaker_name → speaker_name)
    mat = mat.rename(columns={
        "id_dip":        "id_dep",
        "sepaker_name":  "speaker_name",
        "order":         "intervention_order",
    })

    out_cols = [
        "legislature", "session_number", "date", "session_type",
        "intervention_order", "speaker_raw", "id_dep", "speaker_name",
        "party", "district", "text",
    ]
    out = mat[out_cols].copy()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_path, sep=";", index=False, encoding="utf-8")

    rows_with_id    = int(out["id_dep"].notna().sum())
    rows_with_party = int(out["party"].notna().sum())
    rows_with_dist  = int(out["district"].notna().sum())

    return {
        "rows_input":            total_rows,
        "rows_output":           len(out),
        "rows_with_id_dep":      rows_with_id,
        "rows_without_id_dep":   total_rows - rows_with_id,
        "rows_with_party":       rows_with_party,
        "rows_with_district":    rows_with_dist,
        "session_type_unmapped": int(unmapped.sum()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Transforma matriz BR al esquema canónico")
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if not args.matrix.exists():
        print(f"Error: --matrix no encontrado: {args.matrix}", file=sys.stderr)
        sys.exit(1)

    stats = transform(args.matrix, args.output)

    print(f"\nEscrito: {args.output} ({stats['rows_output']:,} filas)\n")
    print("diaries-merge — BR")
    print(f"Filas entrada        : {stats['rows_input']:,}")
    print(f"Filas salida         : {stats['rows_output']:,}  {'OK' if stats['rows_input'] == stats['rows_output'] else 'ERROR'}")
    print(f"  Con id_dep         : {stats['rows_with_id_dep']:,}")
    print(f"  Sin id_dep         : {stats['rows_without_id_dep']:,}")
    print(f"Con party            : {stats['rows_with_party']:,}")
    print(f"Con district         : {stats['rows_with_district']:,}")
    print(f"nm_sesion no mapeado : {stats['session_type_unmapped']:,}")
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
