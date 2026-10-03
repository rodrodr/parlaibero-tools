#!/usr/bin/env python3
"""
Join interventions + matching + deputies tables with pandas.

CLI:
    python merge_tables.py --interventions <path> --matching <path> \
        --deputies <path> --output <path> --separator ";"
"""
import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


def _read_csv_auto(path: Path, sep: str = ";") -> "pd.DataFrame":
    """Lee el CSV detectando el separador POR FICHERO.

    ⚠⚠ La versión anterior solo caía al respaldo si la lectura lanzaba EXCEPCIÓN — y leer un
    fichero con `;` usando `,` no falla: devuelve UNA SOLA COLUMNA con la cabecera entera dentro.
    Así que la «detección automática» no se activaba nunca. En BR eso dejó el padrón sin columna
    `id_dep`, el join con el padrón no llegó a ejecutarse, y el enriched salió SIN partido, sin
    distrito y sin sexo — con un `match_rate` de 0,98 que parecía perfecto, porque `id_dep` viene
    de la tabla de match y no del padrón.

    Los tres ficheros del merge pueden tener separadores DISTINTOS (en BR la matriz usa `,` y el
    padrón `;`), así que no vale una sola bandera para los tres: se decide por la cabecera de cada
    uno, y el `sep` recibido solo desempata."""
    cabecera = path.open(encoding="utf-8", errors="replace").readline()
    mejor = max([",", ";", "\t"], key=cabecera.count)
    if cabecera.count(mejor) == 0:
        mejor = sep
    return pd.read_csv(str(path), sep=mejor, dtype=str, keep_default_na=False)


def _leg_key(serie):
    """Clave NORMALIZADA de legislatura para el join — no toca los valores de salida.

    La matriz cruda conserva el ordinal que `meta` lee del acta (`101º`) y el padrón guarda el
    número pelado (`101`). Los dos son correctos en su sitio, pero como clave de join no casan:
    en AR el solapamiento era 0 de 5 valores, y el fallo es SILENCIOSO — al ser un LEFT JOIN el
    recuento de filas no cambia, `len(enriched) == len(interventions)` pasa, la cobertura de
    vinculación tampoco se mueve (id_dep viene del match), y `partido`/`circunscripcion` salen
    vacíos en TODO el corpus sin que nada avise ([[feedback_clave_join_legislatura]]).

    Se quitan marcas ordinales y espacios: `101º` `101°` `101ª` `101.` ` 101 ` → `101`.

    Y un PREFIJO DE PAÍS de dos letras, pero **solo si lo que queda es todo dígitos**: en BR la
    matriz dice `52` y el padrón `BR52`, con solapamiento CERO. La condición no es un capricho —
    quitar dos letras a ciegas destrozaría a los países cuya legislatura es alfabética: `LIV` de
    México quedaría en `V` y `II` de Portugal en la cadena vacía. Con la guarda, esos no se tocan.

    Si ambos lados ya coinciden, es un no-op."""
    s = (serie.astype(str).str.strip()
         .str.replace(r"[º°ª\.]+$", "", regex=True)
         .str.strip())
    sin_pref = s.str.replace(r"^[A-Za-z]{2}(?=\d+$)", "", regex=True)
    return sin_pref


def merge_tables(
    interventions_path: Path,
    matching_path: Path,
    deputies_path: Path,
    output_path: Path,
    separator: str = ";",
    overrides_path: Path = None,
) -> dict:
    df_int = _read_csv_auto(interventions_path, sep=separator)
    df_match = _read_csv_auto(matching_path, sep=separator)
    df_dep = _read_csv_auto(deputies_path, sep=separator)

    # ── Step 1: interventions LEFT JOIN matching ──
    # Auto-detect join key, de la MÁS precisa a la menos:
    #   (speaker_raw, date)        — la tabla resuelve por SESIÓN (CL): el mismo apellido es
    #                                personas distintas según la fecha, y la legislatura no
    #                                basta para separarlas cuando conviven en la misma.
    #   (speaker_raw, legislature) — la tabla resuelve por legislatura.
    #   speaker_raw                — una decisión por forma, para todo el corpus.
    if "date" in df_match.columns and "date" in df_int.columns:
        join_keys = ["speaker_raw", "date"]
    elif "legislature" in df_match.columns and "legislature" in df_int.columns:
        join_keys = ["speaker_raw", "legislature"]
    else:
        join_keys = ["speaker_raw"]

    match_cols_add = [c for c in ["id_dep", "speaker_name", "match_method", "metodo",
                                   "party", "confidence", "similarity_score"]
                      if c in df_match.columns and c not in join_keys]

    match_subset = df_match[join_keys + match_cols_add].drop_duplicates(subset=join_keys)

    # Rename similarity_score → match_confidence if present
    if "similarity_score" in match_subset.columns:
        match_subset = match_subset.rename(columns={"similarity_score": "match_confidence"})

    merged = df_int.merge(match_subset, on=join_keys, how="left", suffixes=("", "_match"))

    # ⚠ Si la MATRIZ ya trae `id_dep` (CL: el track XML lo da de origen), el merge deja el suyo y
    # manda el de la tabla a `id_dep_match` — la vinculación se perdía entera y en silencio. Se
    # COALESCEN: manda el de la matriz, que viene de la fuente, y la tabla rellena los huecos.
    for _c in ("id_dep", "match_method", "metodo", "speaker_name"):
        _m = f"{_c}_match"
        if _c in merged.columns and _m in merged.columns:
            _vacio = merged[_c].isna() | (merged[_c].astype(str).str.strip()
                                          .isin(("", "nan", "None", "NaN")))
            merged.loc[_vacio, _c] = merged.loc[_vacio, _m]
            merged = merged.drop(columns=[_m])
        elif _m in merged.columns and _c not in merged.columns:
            merged = merged.rename(columns={_m: _c})

    # ── Step 1b: aplicar overrides de asistencia por (date, speaker_raw) ──
    # La asistencia resuelve por-sesión: el mismo apellido puede ser personas
    # distintas según la fecha. El override sustituye id_dep ANTES del join con
    # deputies, para que nombre/partido/distrito salgan del diputado correcto.
    overrides_applied = 0
    if overrides_path is not None and Path(overrides_path).exists() \
            and "date" in merged.columns and "speaker_raw" in merged.columns:
        df_ov = _read_csv_auto(Path(overrides_path), sep=separator)
        # ⚠ DO (2026-09-02): 33 fechas tienen VARIAS sesiones con presidentes distintos, así que
        # la clave por fecha es ambigua para los cargos de mesa. Si el fichero de overrides trae
        # `session_id` y la matriz también, la clave es (session_id, speaker_raw); si no, la de
        # siempre, (date, speaker_raw). Retrocompatible con los overrides de UY/AR.
        _por_sesion = ("session_id" in df_ov.columns and "session_id" in merged.columns
                       and (df_ov["session_id"].astype(str).str.strip() != "").any())
        _kcol = "session_id" if _por_sesion else "date"
        if {_kcol, "speaker_raw", "id_dep"}.issubset(df_ov.columns) and len(df_ov):
            ov_map = {(r[_kcol], r["speaker_raw"]): r["id_dep"]
                      for _, r in df_ov.iterrows() if r["id_dep"]}
            if "id_dep" not in merged.columns:
                merged["id_dep"] = ""
            if "match_method" not in merged.columns:
                merged["match_method"] = ""
            new_ids = merged["id_dep"].copy()
            mm = merged["match_method"].copy()
            for i, (d, sp) in enumerate(zip(merged[_kcol], merged["speaker_raw"])):
                # Las correcciones manuales son autoridad máxima: el override de
                # asistencia (por-sesión) NUNCA las pisa.
                if mm.iat[i] == "manual":
                    continue
                nid = ov_map.get((d, sp))
                if nid and nid != new_ids.iat[i]:
                    new_ids.iat[i] = nid
                    mm.iat[i] = "attendance"
                    overrides_applied += 1
            merged["id_dep"] = new_ids
            merged["match_method"] = mm

    # ── Step 2: result LEFT JOIN deputies ON id_dep ──
    # If deputies has a legislature column, join on (id_dep, legislature) to get
    # the legislature-specific partido/circunscripcion; otherwise join on id_dep only.
    dep_id_col = next((c for c in ("id_dep", "id", "ID") if c in df_dep.columns), None)
    if dep_id_col is None:
        raise SystemExit(
            f"✗ el padrón no tiene columna de identificador ({list(df_dep.columns)[:4]}…). "
            "Suele ser el separador mal detectado: un fichero con `;` leído con `,` da UNA sola "
            "columna y el join con el padrón no llega a ejecutarse, dejando el corpus sin "
            "partido, sin distrito y sin sexo, con un match_rate que parece correcto.")
    _cols_antes = set(merged.columns)

    if dep_id_col and "id_dep" in merged.columns:
        if dep_id_col != "id_dep":
            df_dep = df_dep.rename(columns={dep_id_col: "id_dep"})

        dep_leg_col = next((c for c in ("legislature", "legislatura", "id_legislatura",
                                "legislatura_id", "id_legislature")
                            if c in df_dep.columns), None)
        int_leg_col = "legislature" if "legislature" in merged.columns else None

        # ⚠⚠ MISMO NOMBRE, CONCEPTO DISTINTO. En CR la matriz llama `legislature` al AÑO
        # legislativo dentro del período («PRIMERA», «SEGUNDA») y el padrón al CUATRIENIO
        # («1994-1998»): el solapamiento de claves es CERO y el join no casaría NADA, vaciando
        # partido y provincia con un `match_rate` que parece correcto. Se mide el solapamiento
        # ANTES de elegir la rama; sin él, se cae a la rama por FECHAS, que es la correcta
        # cuando el padrón tiene `fecha_inicio`/`fecha_fin` (cr-0039).
        if dep_leg_col and int_leg_col:
            _a = set(_leg_key(df_dep[dep_leg_col].astype(str)).unique())
            _b = set(_leg_key(merged[int_leg_col].astype(str)).unique())
            if not (_a & _b):
                print(f"  ⚠ la clave de legislatura NO SOLAPA ({len(_a)} × {len(_b)} valores, "
                      f"0 en común): se ignora y se une por FECHA DE SESIÓN")
                dep_leg_col = None

        if dep_leg_col and int_leg_col:
            # Join on (id_dep, legislature) — most precise.
            # ⚠ La clave se NORMALIZA (`101º` ↔ `101`); los valores de salida no se tocan.
            df_dep_j = df_dep.rename(columns={dep_leg_col: "legislature"})
            dep_extra = [c for c in df_dep_j.columns
                         if c not in ("id_dep", "legislature") and c not in merged.columns]
            dep_subset = df_dep_j[["id_dep", "legislature"] + dep_extra].copy()
            dep_subset["_lk"] = _leg_key(dep_subset["legislature"])
            dep_subset = dep_subset.drop(columns=["legislature"])

            # ⚠⚠ TRAMOS dentro de una misma legislatura. En BR el padrón tiene una fila por
            #   (persona, legislatura, TRAMO DE PARTIDO): BR178938 en la legislatura 55 pasó por
            #   PSOL → S.PART. → PTdoB → AVANTE, con sus fechas. Son 987 pares repetidos.
            #   `drop_duplicates` se quedaría con el PRIMERO y le pondría PSOL a sesiones que
            #   fueron de AVANTE — la misma clase que en PA dejó 34.787 filas con el partido del
            #   período equivocado. Cuando hay tramos Y hay fechas, se elige por FECHA DE SESIÓN.
            _ini = next((c for c in ("fecha_inicio", "dt_inicio_partido", "dt_alta", "start_date")
                         if c in dep_subset.columns), None)
            _fin = next((c for c in ("fecha_fin", "dt_fin_partido", "dt_baja", "end_date")
                         if c in dep_subset.columns), None)
            _dups = dep_subset.duplicated(subset=["id_dep", "_lk"]).sum()
            _por_tramo = {}
            if _dups and _ini and _fin and "date" in merged.columns:
                for _, _rp in dep_subset.iterrows():
                    _por_tramo.setdefault((_rp["id_dep"], _rp["_lk"]), []).append(_rp)
                _por_tramo = {k: v for k, v in _por_tramo.items() if len(v) > 1}
                print(f"  tramos dentro de una legislatura: {len(_por_tramo):,} pares "
                      f"(id_dep, legislatura) con más de una fila → se elige por fecha de sesión")
            elif _dups:
                print(f"  ⚠ {_dups:,} pares (id_dep, legislatura) repetidos y NO hay fechas para "
                      f"desempatar: se conserva el primero (revisar)")
            dep_subset = dep_subset.drop_duplicates(subset=["id_dep", "_lk"])
            merged["_lk"] = _leg_key(merged["legislature"])
            solape = len(set(merged["_lk"]) & set(dep_subset["_lk"]))
            if solape == 0:
                raise SystemExit(
                    "✗ la clave de legislatura NO solapa entre matriz y padrón tras normalizar "
                    f"({sorted(set(merged['_lk']))[:4]} vs {sorted(set(dep_subset['_lk']))[:4]}). "
                    "Un LEFT JOIN aquí vaciaría partido/distrito en TODO el corpus sin avisar.")
            merged = merged.merge(dep_subset, on=["id_dep", "_lk"],
                                  how="left", suffixes=("", "_dep"))
            # …y se corrigen las filas cuyo tramo no es el que cubre la fecha de la sesión
            if _por_tramo:
                _cols = [c for c in dep_subset.columns if c not in ("id_dep", "_lk")]
                _cambiadas = 0
                _vals = {c: merged[c].copy() for c in _cols if c in merged.columns}
                for _i, (_id, _lk, _d) in enumerate(zip(merged["id_dep"], merged["_lk"],
                                                        merged["date"])):
                    _rows = _por_tramo.get((_id, _lk))
                    if not _rows:
                        continue
                    _ds = str(_d)[:10]
                    _elegida = None
                    for _rp in _rows:
                        _a, _b = str(_rp[_ini])[:10], str(_rp[_fin])[:10]
                        # ⚠ un tramo SIN fecha de fin está VIGENTE, no es inválido: cubre desde su
                        #   inicio en adelante. Exigir fin descartaba los 1.246 tramos abiertos de
                        #   BR y los mandaba al respaldo «primer tramo».
                        if len(_a) == 10 and len(_b) < 10 and _a <= _ds:
                            _elegida = _rp
                            break
                        if len(_a) == 10 and len(_b) == 10 and _a <= _ds <= _b:
                            _elegida = _rp
                            break
                    if _elegida is None:
                        continue                      # ninguno cubre: se deja el primero
                    for _c in _vals:
                        if _vals[_c].iat[_i] != _elegida[_c]:
                            _vals[_c].iat[_i] = _elegida[_c]
                            _cambiadas += 1
                for _c, _s in _vals.items():
                    merged[_c] = _s
                print(f"  celdas corregidas al tramo que cubre la fecha: {_cambiadas:,}")
            merged = merged.drop(columns=["_lk"])
        elif {"fecha_inicio", "fecha_fin"} <= set(df_dep.columns) and "date" in merged.columns:
            # PERIOD-AWARE JOIN (roster multi-período SIN columna legislature, p.ej. PA):
            # un diputado con N períodos tiene N filas con partido/circunscripción distintos.
            # Tomar "la primera fila por id" asigna atributos del período EQUIVOCADO (sesión
            # de 2009 con el partido de 2024 — detectado en PA 2026-07: 34.787 filas mal).
            # Se elige la fila cuyo período CUBRE la fecha de sesión; si ninguno la cubre,
            # la de período más CERCANO.
            dep_extra = [c for c in df_dep.columns
                         if c != "id_dep" and c not in merged.columns]
            dep_subset = df_dep[["id_dep"] + dep_extra]
            base = dep_subset.drop_duplicates(subset="id_dep")
            merged = merged.merge(base, on="id_dep", how="left", suffixes=("", "_dep"))
            counts = dep_subset.groupby("id_dep").size()
            multi_ids = set(counts[counts > 1].index)
            if multi_ids:
                periods: dict = {}
                for _, rp in dep_subset[dep_subset["id_dep"].isin(multi_ids)].iterrows():
                    periods.setdefault(rp["id_dep"], []).append(rp)

                def _days(d1, d2):
                    try:
                        from datetime import date as _d
                        a = _d(*map(int, str(d1)[:10].split("-")))
                        b = _d(*map(int, str(d2)[:10].split("-")))
                        return abs((a - b).days)
                    except (ValueError, TypeError):
                        return 10 ** 9

                def _pick(dep_id, date):
                    # Comparación de FECHA COMPLETA ISO (no solo año): en el año de transición
                    # (los períodos cambian el 1-jul) una sesión de julio pertenece ya al
                    # período NUEVO; la granularidad de año la asignaría al viejo.
                    rowsp = periods[dep_id]
                    ds = str(date)[:10]
                    best, bestd = rowsp[0], 10 ** 9
                    for rp in rowsp:
                        a = str(rp["fecha_inicio"])[:10]
                        b = str(rp["fecha_fin"])[:10]
                        if len(a) == 10 and len(b) == 10 and a <= ds <= b:
                            return rp
                        d = min(_days(ds, a), _days(ds, b))
                        if d < bestd:
                            bestd, best = d, rp
                    return best

                # ⚠ Asignar celda a celda con `.at` son (filas × columnas) escrituras: en CL,
                # 4,5 millones, y el merge no terminaba. Se resuelve UNA VEZ por par
                # (id_dep, fecha) —que son órdenes de magnitud menos— y se vuelca por COLUMNA.
                mask = (merged["id_dep"].isin(multi_ids)).to_numpy()
                if mask.any():
                    _idx = merged.index[mask]
                    _claves = list(zip(merged.loc[_idx, "id_dep"],
                                       merged.loc[_idx, "date"].astype(str).str[:10]))
                    _elec = {k: _pick(k[0], k[1]) for k in set(_claves)}
                    for c in dep_extra:
                        _col = merged[c].to_numpy(dtype=object, copy=True)
                        _pos = merged.index.get_indexer(_idx)
                        for _p, _k in zip(_pos, _claves):
                            _col[_p] = _elec[_k][c]
                        merged[c] = _col
        else:
            # Fallback: join on id_dep only (take first row per deputy)
            dep_extra = [c for c in df_dep.columns
                         if c != "id_dep" and c not in merged.columns]
            dep_subset = df_dep[["id_dep"] + dep_extra].drop_duplicates(subset="id_dep")
            merged = merged.merge(dep_subset, on="id_dep", how="left", suffixes=("", "_dep"))

    # ── Stats ──
    total_rows = len(merged)
    # ⚠ `notna()` cuenta la CADENA VACÍA como presente, y las filas sin vincular llevan ""
    # (no NaN): en AR daba «match_rate 0.9934» sobre una vinculación real del 90,79%
    # ([[feedback_verificar_la_metrica]]). Se mide lo NO VACÍO, y la tasa se calcula sobre las
    # filas CON ORADOR, no sobre el total — los Prolegomena no tienen a quién vincular.
    if "id_dep" in merged.columns:
        _id = merged["id_dep"].fillna("").astype(str).str.strip()
        rows_with_id = int((_id != "").sum())
    else:
        rows_with_id = 0
    if "speaker_raw" in merged.columns:
        _sp = merged["speaker_raw"].fillna("").astype(str).str.strip()
        denom = int((_sp != "").sum())
    else:
        denom = total_rows
    match_rate = rows_with_id / denom if denom > 0 else 0.0

    # ── Write output ──
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # ── Propagación de los atributos DE LA PERSONA ───────────────────────────────
    # El sexo es un atributo de la PERSONA, no del par (persona, legislatura). Cuando el join no
    # encuentra fila para esa legislatura —porque el acta registra a alguien hablando en una que
    # el padrón no le asigna— la columna sale vacía, pero el dato existe en las demás filas de esa
    # misma persona. Rellenarlo NO es derivar ni inferir: es leer el mismo hecho en otra fila.
    #
    # ⚠⚠ Solo se propagan los atributos que son de la persona. `party` y `district` NO: cambian
    #   legítimamente entre legislaturas y propagarlos inventaría historia política (regla 5k de
    #   `diaries-deputies`). Y solo si la persona tiene UN ÚNICO valor: con dos, no se elige.
    _PERSONALES = ("sex", "sex_source", "speaker_name", "nombre_completo", "alias")
    _prop = {}
    for _c in _PERSONALES:
        if _c not in merged.columns or _c not in df_dep.columns:
            continue
        _u = (df_dep[df_dep[_c].astype(str).str.strip() != ""]
              .groupby("id_dep")[_c].agg(lambda s: set(s)))
        _prop[_c] = {i: next(iter(v)) for i, v in _u.items() if len(v) == 1}
    if _prop:
        _tot = 0
        for _c, _mapa in _prop.items():
            # ⚠ tras un LEFT JOIN sin coincidencia pandas pone NaN, NO cadena vacía; y
            #   `str(NaN)` es «nan», así que comparar con "" da siempre falso y la propagación
            #   no se activaba nunca. Hay que contar como vacío el NaN y el literal «nan».
            _s = merged[_c]
            _vacias = _s.isna() | (_s.astype(str).str.strip().isin(["", "nan", "None"]))
            _rell = merged.loc[_vacias, "id_dep"].map(_mapa)
            _n = int(_rell.notna().sum())
            if _n:
                merged.loc[_vacias, _c] = _rell.fillna(merged.loc[_vacias, _c])
                _tot += _n
                print(f"  `{_c}` propagado desde la propia persona: {_n:,} filas")
        if not _tot:
            print("  atributos de persona: nada que propagar")

    # ⚠ un merge que no aporta NI UNA columna del padrón es siempre un fallo, y silencioso:
    #   el recuento de filas no cambia y `match_rate` sigue bien porque `id_dep` viene del match.
    _aportadas = set(merged.columns) - _cols_antes
    if not _aportadas:
        raise SystemExit(
            "✗ el join con el padrón no aportó NINGUNA columna. El enriched saldría sin partido, "
            "sin distrito y sin sexo. Revisa el separador del padrón y el nombre de sus columnas.")
    print(f"  columnas aportadas por el padrón: {len(_aportadas)} · {sorted(_aportadas)[:6]}")

    merged.to_csv(str(output_path), sep=separator, index=False, encoding="utf-8")

    return {
        "total_rows": total_rows,
        "rows_with_id_dep": rows_with_id,
        "rows_with_speaker": denom,
        "match_rate": round(match_rate, 4),
        "overrides_applied": overrides_applied,
        "output_path": str(output_path),
    }


def main():
    parser = argparse.ArgumentParser(description="Join interventions + matching + deputies")
    parser.add_argument("--interventions", required=True, help="Interventions CSV")
    parser.add_argument("--matching", required=True, help="Fuzzy matching results JSON or CSV")
    parser.add_argument("--deputies", required=True, help="Deputies reference CSV")
    parser.add_argument("--output", required=True, help="Output merged CSV")
    parser.add_argument("--separator", default=";", help="CSV separator (default: ;)")
    parser.add_argument("--overrides", default=None,
                        help="CSV de overrides por (date;speaker_raw;id_dep) de la asistencia")
    args = parser.parse_args()

    if not HAS_PANDAS:
        print(json.dumps({"status": "error", "error": "pandas package not installed"}))
        sys.exit(1)

    interventions_path = Path(args.interventions)
    matching_path = Path(args.matching)
    deputies_path = Path(args.deputies)
    output_path = Path(args.output)

    for p in [interventions_path, matching_path, deputies_path]:
        if not p.exists():
            print(json.dumps({"status": "error", "error": f"Not found: {p}"}))
            sys.exit(1)

    # If matching is a JSON file (from fuzzy_match.py), convert to DataFrame-compatible format
    matching_path_use = matching_path
    if matching_path.suffix.lower() == ".json":
        import json as _json
        import tempfile
        import csv as _csv

        records = _json.loads(matching_path.read_text(encoding="utf-8"))
        # records is a list of dicts
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8", newline=""
        )
        if records:
            fieldnames = list(records[0].keys())
            writer = _csv.DictWriter(tmp, fieldnames=fieldnames, delimiter=args.separator)
            writer.writeheader()
            writer.writerows(records)
        tmp.close()
        matching_path_use = Path(tmp.name)

    try:
        stats = merge_tables(
            interventions_path,
            matching_path_use,
            deputies_path,
            output_path,
            separator=args.separator,
            overrides_path=Path(args.overrides) if args.overrides else None,
        )
    finally:
        # Clean up temp file if we created one
        if matching_path.suffix.lower() == ".json" and matching_path_use != matching_path:
            matching_path_use.unlink(missing_ok=True)

    stats["status"] = "ok"
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
