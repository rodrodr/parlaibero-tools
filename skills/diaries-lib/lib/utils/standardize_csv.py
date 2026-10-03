#!/usr/bin/env python3
"""
Enforce the canonical final schema on enriched CSV.

CLI:
    python standardize_csv.py --input <path> --output <path> \
        --config <yaml_path> [--force]

Canonical columns (in order) — **16**:
    id_session, id_int, legislature, legislative_session, session_number, date,
    session_type, intervention_order, speaker_raw, id_dep, speaker_name, sex, party,
    district, dm_speech, text

⚠ `id_session`/`id_int` (esquema del investigador, 2026-08-10) se añaden aquí como columnas VACÍAS
si faltan, y `diaries-standardize` Paso 4-ter las rellena con `asignar_ids.py`. Antes de este arreglo
esta utilidad declaraba 14 y las DROPEABA al reindexar: mismo patrón destructivo que con `sex` y
`dm_speech` (ver abajo). Si se re-estandariza, hay que correr `asignar_ids.py` inmediatamente después.

⚠ `sex` se añadió al esquema el 2026-07-30 y esta utilidad se quedó en 11 columnas sin él.
Como aquí se ENFUERZA el esquema, volver a ejecutar el paso habría borrado en silencio la
columna en cualquier país: 22.026 personas revisadas a mano, 98,98% de exactitud medida.
Un enforcer desactualizado no falla — destruye, y con aire de haber hecho su trabajo.
⚠ `dm_speech` se añadió el 2026-08-09 por la misma razón: la fila que no es intervención —el
sumario del acta, el recuento de una votación, el documento reproducido— no se aparta a un
sidecar ni se borra, se MARCA con 0. Es binaria a propósito: sirve para filtrar el corpus a
intervenciones reales de una sola condición. Las clases finas (mesa · diputado · gobierno ·
otros, y summary · procedural_reading · other) llegarán como variables aparte, de
enriquecimiento; esta solo responde «¿esto es una intervención?». Mantener esta lista al día
es la condición para que la columna se conserve.
⚠ `legislative_session` se añadió el 2026-08-15 (decisión tr-0078). La estructura legislativa
tiene DOS niveles en al menos BR, UY, PA, DO y CO, y estaban aplastados en una sola columna:
`legislature` guarda el nivel MAYOR —el único disjunto en el tiempo— y `legislative_session`
el MENOR (sesión legislativa anual en BR, periodo ordinario en UY, legislatura dentro del
periodo constitucional en PA, legislatura ordinaria/prórroga en DO). Ambos se LEEN DEL ACTA,
que los declara explícitamente; no se derivan de un calendario externo.
"""
import sys
import json
import argparse
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

_CANONICAL_COLUMNS = [
    "id_session",
    "id_int",
    "legislature",
    "legislative_session",
    "session_number",
    "date",
    "session_type",
    "intervention_order",
    "speaker_raw",
    "id_dep",
    "speaker_name",
    "sex",
    "party",
    "district",
    "dm_speech",
    "text",
]

# For each canonical column, the ordered list of possible source column names.
# First match found in the dataframe wins.
_COLUMN_ALIASES: dict[str, list[str]] = {
    "id_session":     ["id_session", "id_sesion"],
    "id_int":         ["id_int", "id_intervencion"],
    "legislature":    ["legislature", "legislatura"],
    "legislative_session": ["legislative_session", "sesion_legislativa", "periodo_ordinario",
                            "sessao_legislativa", "legislatura_ordinaria"],
    "session_number": ["session_number", "numero_publicacion", "numero_sesion"],
    "date":           ["date", "fecha"],
    "session_type":   ["session_type", "tipo_sesion"],
    "speaker_raw":    ["speaker_raw", "interventor_normalizado"],
    "id_dep":         ["id_dep", "diputado_id"],
    "speaker_name":   ["speaker_name", "nombre_completo", "full_name", "nome_completo", "nombre_original",
                       "nome_parlamentar", "alias"],
    "party":          ["party", "partido", "party_raw", "partido_raw", "partij", "formacion_electoral",
                       "sgl_partido", "sigla_partido"],
    "district":       ["district", "circunscripcion", "distrito", "constituency", "circonscription"],
    "dm_speech":      ["dm_speech", "es_discurso", "is_speech"],
    "text":           ["text", "intervencion"],
}

_ISO8601_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


_VACIOS = ("", "nan", "None", "NaN", "<NA>", "null", "NULL")


def _n_con_datos(serie) -> int:
    s = serie.astype(object).where(serie.notna(), "").astype(str).str.strip()
    return int((~s.isin(_VACIOS)).sum())


def _tiene_datos(serie) -> bool:
    """¿La columna aporta ALGÚN valor real? `NaN`, `""`, `"nan"` y `"None"` no cuentan."""
    # ⚠ `.fillna("")` ANTES de comparar: con dtype Arrow, `astype(str)` deja el NA como NA
    # y toda comparación con él da False, así que el vacío se contaba como dato.
    s = serie.astype(object).where(serie.notna(), "").astype(str).str.strip()
    return bool((~s.isin(_VACIOS)).any())


def _extract_year(date_val: str) -> str | None:
    if not date_val or not isinstance(date_val, str):
        return None
    m = re.match(r"(\d{4})", date_val.strip())
    return m.group(1) if m else None


# ⚠ EC (2026-09-02): el acta numera «Acta No. 23-232» / «24-022» (período-secuencia). Es la
#   convención de la fuente, no ruido: se admite UN guion interno entre grupos alfanuméricos.
_ALPHANUMERIC_RE = re.compile(r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)?$")


def _validate_session_number(val: str) -> tuple[int | str | None, bool]:
    """Returns (coerced_value_or_None, is_valid).

    Acepta:
    - Vacío / None → None (válido)
    - Entero puro: "12" → 12
    - Float serializado: "12.0" → 12
    - Alfanumérico: "12A", "12B" → "12A" (válido, se preserva como string)
    """
    if not val or val.strip() == "" or val.strip().lower() in ("none", "null", "nan"):
        return None, True
    val = val.strip()
    try:
        return int(val), True
    except (ValueError, TypeError):
        pass
    # Float-serialised integers ("9.0" → 9)
    try:
        f = float(val)
        if f == int(f):
            return int(f), True
    except (ValueError, TypeError):
        pass
    # Alphanumeric (e.g. "12A", "12B") — preserve as string
    if _ALPHANUMERIC_RE.match(val):
        return val, True
    return None, False


def _validate_date(val: str) -> bool:
    if not val or val.strip() == "" or val.strip().lower() in ("none", "null", "nan"):
        return True  # None is allowed
    return bool(_ISO8601_RE.match(val.strip()))


def _add_intervention_order(df: "pd.DataFrame") -> "pd.DataFrame":
    """Add intervention_order: sequential rank within each (date, session_number) group.

    sort=False preserves the original row order — critical for debate reconstruction.
    If the column already exists in the input (provided by source), it is kept as-is.
    """
    if "intervention_order" in df.columns:
        return df
    df = df.copy()
    df["intervention_order"] = (
        df.groupby(["date", "session_number"], sort=False).cumcount() + 1
    ).astype(str)

    # ⚠⚠ Los PROLEGOMENA van en `0`, no en `1`. El esquema canónico lo dice —«0 = carátula,
    #   sumario, índice o pase de lista que preceden a la primera intervención; preceden SIN
    #   desplazar la numeración del resto»— pero esta función no lo aplicaba, así que en todo
    #   país cuya matriz NO trae la columna la carátula quedaba numerada como intervención 1.
    #   Detectado en AR y confirmado en BR (2026-09-01); antes se arreglaba con un script por país.
    #
    #   La firma es inequívoca y se ha verificado en los dos: la PRIMERA fila de la sesión con
    #   `dm_speech = 0` y sin orador. En AR se cumple en las 1.086 sesiones; en BR en 7.473 de
    #   7.801 — las 328 restantes simplemente no tienen carátula, que es un hecho, no un fallo.
    if {"dm_speech", "speaker_raw"} <= set(df.columns):
        prim = df.groupby(["date", "session_number"], sort=False).head(1).index
        es_prol = (df.index.isin(prim)
                   & (df["dm_speech"].astype(str).str.strip() == "0")
                   & (df["speaker_raw"].fillna("").astype(str).str.strip() == ""))
        if es_prol.any():
            # El resto de la sesión se numera 1..N: el Prolegomena no desplaza a nadie.
            # ⚠ El desplazamiento depende de si ESA sesión tiene carátula o no. `cumcount()`
            #   empieza en 0, así que en una sesión SIN carátula hay que sumar 1, y en una CON
            #   carátula no: sumarlo siempre habría hecho empezar en 0 a las sesiones sin ella
            #   (328 de las 7.801 en BR).
            g = df.groupby(["date", "session_number"], sort=False)
            orden = g.cumcount()
            tiene = es_prol.groupby([df["date"], df["session_number"]], sort=False).transform("any")
            df["intervention_order"] = (orden + (~tiene).astype(int)).astype(str)
            df.loc[es_prol, "intervention_order"] = "0"
            n = int(es_prol.sum())
            print(f"  Prolegomena marcados con intervention_order = 0: {n:,}")
    return df


_IMPUTE_MAX_GAP_DAYS = 120


def _vacias(col: "pd.Series") -> "pd.Series":
    """Máscara de celdas vacías, INDEPENDIENTE DEL DTYPE.

    ⚠ Esto era un no-op silencioso (detectado 2026-08-15). El código anterior decidía la rama
    según `col.dtype == object`:

        col.str.strip().isin(["", "None", "nan"]) if col.dtype == object else col.isna()

    En pandas < 3 una columna de texto tenía dtype `object` y funcionaba. **En pandas 3.0 el
    dtype por defecto pasó a ser `str`**, la condición se volvió falsa y la rama activa pasó a
    ser `.isna()`, que NO considera vacía una cadena vacía. Resultado: la imputación de
    `legislature` y `session_number` dejó de hacer nada, sin error y sin traza. Los 60.804 huecos
    de `legislature` en BR son consecuencia de esto, no de las fuentes.

    Un no-op silencioso es peor que una excepción: no deja rastro y el resultado parece correcto.
    Por eso aquí no se ramifica por dtype — se normaliza a texto y se compara.
    """
    return col.astype("string").fillna("").str.strip().isin(["", "None", "nan", "<NA>"])


def _impute_legislature(df: "pd.DataFrame", max_gap_days: int = _IMPUTE_MAX_GAP_DAYS) -> "pd.DataFrame":
    """Impute missing legislature values using nearest-date context.

    For a date with empty legislature, find the closest preceding and following
    dates (globally, not per-legislature) that have a known value:
    - Same prev and next  → use that value
    - Different prev/next → use prev (session belongs to the outgoing legislature)
    - Only prev           → use prev
    - Only next           → use next
    - Neither             → leave empty

    ⚠ LA IMPUTACIÓN ES EL ÚLTIMO RECURSO, NO EL PRIMERO (2026-08-15, decisión tr-0078).
    Las actas DECLARAN su legislatura de forma explícita —«da 54ª Legislatura» en BR, «XLII
    LEGISLATURA» en UY, «PERIODO CONSTITUCIONAL 2009-2014» en PA—, así que lo correcto es leerla.
    Esta función solo cubre lo que la lectura no alcanzó.

    ⚠ COTA DE DISTANCIA OBLIGATORIA. La versión anterior copiaba del vecino conocido más próximo
    SIN LÍMITE: en PA dejó 49 filas fechadas en 2021 con la etiqueta `2009-2014`, un salto de
    siete años. Que fueran pocas fue suerte —depende de dónde caigan los huecos—, y la función
    corre en los 16 países. Ahora se rechaza cualquier vecino a más de `max_gap_days`.

    ⚠ Y DEJA CONSTANCIA. Antes imputaba en silencio: ninguna traza distinguía un valor leído del
    acta de uno copiado del vecino, y por eso el defecto sobrevivió a todas las revisiones. El
    recuento se devuelve en `df.attrs["legislature_imputed"]`.
    """
    if "legislature" not in df.columns or "date" not in df.columns:
        return df

    # Build date → legislature map for known rows (first non-empty value per date)
    known: dict[str, str] = {}
    for date, grp in df.groupby("date"):
        for v in grp["legislature"]:
            if isinstance(v, str) and v.strip() not in ("", "None", "nan"):
                known[date] = v.strip()
                break

    missing_dates = set()
    for date, grp in df.groupby("date"):
        if date not in known:
            missing_dates.add(date)

    if not missing_dates:
        return df

    sorted_known_dates = sorted(known.keys())

    from datetime import date as _date

    def _dias(a: str, b: str) -> int | None:
        """Distancia en días entre dos fechas ISO; None si alguna no lo es."""
        try:
            ya, ma, da = (int(x) for x in a[:10].split("-"))
            yb, mb, db = (int(x) for x in b[:10].split("-"))
            return abs((_date(ya, ma, da) - _date(yb, mb, db)).days)
        except Exception:
            return None

    imputed: dict[str, str] = {}
    descartados = 0
    for date in missing_dates:
        before = [d for d in sorted_known_dates if d < date]
        after  = [d for d in sorted_known_dates if d > date]

        prev_d = before[-1] if before else None
        next_d = after[0]   if after  else None

        # Solo se acepta un vecino DENTRO de la cota. Sin fecha comparable, no se imputa:
        # un valor copiado de siete años atrás es peor que un hueco declarado.
        def _valido(d):
            if d is None:
                return False
            g = _dias(date, d)
            return g is not None and g <= max_gap_days

        if _valido(prev_d):
            imputed[date] = known[prev_d]      # prev gana (legislatura saliente)
        elif _valido(next_d):
            imputed[date] = known[next_d]
        else:
            descartados += 1

    df.attrs["legislature_impute_rejected_dates"] = descartados
    if not imputed:
        df.attrs["legislature_imputed"] = 0
        return df

    # Merge known + imputed so empty rows on ANY date can be filled
    fill_map = {**imputed, **known}

    df = df.copy()
    empty_mask = _vacias(df["legislature"])
    n_imp = 0
    for idx in df[empty_mask].index:
        date = df.at[idx, "date"]
        if date in imputed:                    # solo cuenta lo REALMENTE imputado, no lo conocido
            df.at[idx, "legislature"] = imputed[date]
            n_imp += 1
        elif date in known:
            df.at[idx, "legislature"] = known[date]

    df.attrs["legislature_imputed"] = n_imp
    return df


def _impute_session_numbers(df: "pd.DataFrame") -> "pd.DataFrame":
    """Impute missing session_number by sequential pattern within legislature.

    Regla A: if gap between prev_sn and next_sn (same legislature, ordered by date) == 2,
             impute prev_sn + 1.
    Regla B: if no next session exists in the legislature, impute prev_sn + 1.
    All other cases (gap == 1, gap > 2, no prev) are left empty.
    """
    if "session_number" not in df.columns or "date" not in df.columns:
        return df

    # Build per-date session_number map (one value per date+legislature)
    def first_int(series):
        for v in series:
            try:
                i = int(v)
                return i
            except (ValueError, TypeError):
                pass
        return None

    leg_col = "legislature" if "legislature" in df.columns else None

    # Collect known (date, legislature) → int session_number
    known: dict[tuple, int] = {}
    for (date, leg), grp in df.groupby(["date", leg_col] if leg_col else ["date"]):
        val = first_int(grp["session_number"])
        if val is not None:
            known[(date, leg if leg_col else "")] = val

    # For each missing date, look up prev/next within same legislature
    imputed: dict[tuple, int] = {}
    missing_keys = set()
    for (date, leg), grp in df.groupby(["date", leg_col] if leg_col else ["date"]):
        key = (date, leg if leg_col else "")
        if key not in known:
            missing_keys.add(key)

    for (date, leg) in missing_keys:
        same_leg = {k: v for k, v in known.items() if k[1] == leg}
        before = {k: v for k, v in same_leg.items() if k[0] < date}
        after  = {k: v for k, v in same_leg.items() if k[0] > date}

        prev_sn = known[max(before, key=lambda k: k[0])] if before else None
        next_sn = known[min(after,  key=lambda k: k[0])] if after  else None

        if prev_sn is None:
            continue  # no context, leave empty

        if next_sn is None:
            # Regla B: end of legislature
            imputed[(date, leg)] = prev_sn + 1
        elif (next_sn - prev_sn) == 2:
            # Regla A: exact sequential gap
            imputed[(date, leg)] = prev_sn + 1
        # else: gap == 1 or gap > 2 — leave empty

    if not imputed:
        return df

    # Apply imputed values back to rows
    df = df.copy()
    leg_series = df[leg_col] if leg_col else ""
    mask = _vacias(df["session_number"])
    for idx in df[mask].index:
        key = (df.at[idx, "date"], df.at[idx, leg_col] if leg_col else "")
        if key in imputed:
            df.at[idx, "session_number"] = str(imputed[key])

    return df


def standardize(
    df: "pd.DataFrame",
    config: dict,
    separator: str = ";",
) -> tuple["pd.DataFrame", dict]:
    validation_errors = 0

    # Apply country-specific column aliases from YAML config first
    yaml_aliases = config.get("_COLUMN_ALIASES", {})
    if yaml_aliases:
        # YAML format: canonical_name → source_col_name
        yaml_rename = {
            src: canonical
            for canonical, src in yaml_aliases.items()
            if isinstance(src, str) and src in df.columns and src != canonical
        }
        if yaml_rename:
            df = df.rename(columns=yaml_rename)

    # Rename enriched columns to canonical names.
    # ⚠ Gana el primer alias PRESENTE **Y CON DATOS**: un alias presente pero enteramente
    # vacío (p. ej. `party_raw` en BR, columna residual de la matriz) ganaba la carrera y
    # dejaba la columna canónica al 0% mientras el valor real esperaba en otro alias
    # (`sgl_partido`). El resultado pasaba todas las validaciones porque la columna EXISTÍA.
    # Gana el alias que MÁS datos trae, no el primero presente ni el primero con algún dato.
    #
    # Dos defectos sucesivos llevaron aquí, ambos silenciosos porque la columna EXISTÍA:
    #   · br-0024 · ganaba el primer alias PRESENTE — `party_raw`, vacía, dejaba fuera a
    #     `sgl_partido` (97,29%) y `party` salía al 0%.
    #   · cl-0049 · con «el primero CON DATOS» seguía fallando por dos vías: la canónica
    #     `district` existía vacía y nadie miraba a `circunscripcion`; y `speaker_name` traía
    #     2.604 nombres de la matriz, suficientes para «tener datos», y así el
    #     `nombre_completo` del padrón —al 100%— nunca competía.
    # El recuento decide y no hay atajos. No se COALESCEN: mezclar dos procedencias en una
    # columna rompe invariantes que sí se comprueban (p. ej. «nombre sin id_dep = 0»).
    for canonical, aliases in _COLUMN_ALIASES.items():
        presentes = [a for a in aliases if a in df.columns]
        if not presentes:
            continue
        conteo = {a: _n_con_datos(df[a]) for a in presentes}
        mejor = max(presentes, key=lambda a: (conteo[a], -presentes.index(a)))
        if mejor == canonical:
            continue
        if canonical in df.columns:
            df = df.drop(columns=[canonical])
        df = df.rename(columns={mejor: canonical})

    rename_map = {}
    if rename_map:
        df = df.rename(columns=rename_map)

    # Generate intervention_order before adding missing columns as None
    # (must run first so the "add missing columns" loop doesn't pre-fill it with None)
    df = _add_intervention_order(df)

    # Add missing canonical columns as None/empty
    for col in _CANONICAL_COLUMNS:
        if col not in df.columns:
            df[col] = None

    # Impute missing legislature by nearest-date context
    df = _impute_legislature(df)

    # Validate and coerce session_number
    coerced_nums = []
    for val in df["session_number"]:
        coerced, valid = _validate_session_number(str(val) if val is not None else "")
        if not valid:
            validation_errors += 1
        coerced_nums.append(coerced)
    df["session_number"] = [str(v) if v is not None else "" for v in coerced_nums]

    # Impute missing session_number by sequential pattern within legislature
    df = _impute_session_numbers(df)

    # Validate date format
    for val in df["date"]:
        v = str(val) if val is not None else ""
        if not _validate_date(v):
            validation_errors += 1

    # Reorder to canonical columns (only keep canonical + drop extra)
    df = df.reindex(columns=_CANONICAL_COLUMNS)

    # ── Nombres de persona SIEMPRE en MAYÚSCULAS ────────────────────────────────
    # Regla del investigador (2026-09-01), para los dieciséis: el padrón de cada país
    # escribe el nombre en la caja que le da la gana —AR entero en caja de título, BR
    # mitad y mitad— y esa mezcla llega al corpus. `speaker_raw` NO se toca: es el
    # literal del acta. `.upper()` respeta los diacríticos (`Eunício` → `EUNÍCIO`).
    if "speaker_name" in df.columns:
        _n = df["speaker_name"]
        df["speaker_name"] = _n.where(_n.isna(), _n.astype(str).str.upper())

    # ── Guardarraíl de RESULTADO ────────────────────────────────────────────────
    # No basta con que la columna exista: si `id_dep` está poblado, los atributos que
    # vienen del padrón por ese join TIENEN que llegar. Una columna canónica al 0%
    # junto a un `id_dep` poblado es un alias mal resuelto, no un hecho de la fuente.
    llenado = {col: _n_con_datos(df[col]) for col in _CANONICAL_COLUMNS}
    vacias_sospechosas = [
        c for c in ("speaker_name", "party", "district", "sex")
        if llenado[c] == 0 and llenado["id_dep"] > 0
    ]
    if vacias_sospechosas:
        raise SystemExit(
            "ABORTA: " + ", ".join(vacias_sospechosas) + " al 0% con "
            f"{llenado['id_dep']:,} filas con id_dep. El enriquecido no trae esas columnas "
            "bajo ningún alias conocido, o el alias elegido estaba vacío. Revisa las "
            "columnas del enriquecido y _COLUMN_ALIASES antes de publicar."
        )

    return df, {
        "total_rows": len(df),
        "validation_errors": validation_errors,
        "fill": llenado,
    }


def main():
    parser = argparse.ArgumentParser(description="Standardize CSV to canonical schema")
    parser.add_argument("--input", required=True, help="Enriched CSV input")
    parser.add_argument("--output", required=True, help="Standardized CSV output")
    parser.add_argument("--config", required=True, help="YAML config file")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite output if it already exists")
    args = parser.parse_args()

    if not HAS_PANDAS:
        print(json.dumps({"status": "error", "error": "pandas package not installed"}))
        sys.exit(1)
    if not HAS_YAML:
        print(json.dumps({"status": "error", "error": "PyYAML package not installed"}))
        sys.exit(1)

    input_path = Path(args.input)
    output_path = Path(args.output)
    config_path = Path(args.config)

    if not input_path.exists():
        print(json.dumps({"status": "error", "error": f"Not found: {input_path}"}))
        sys.exit(1)
    if not config_path.exists():
        print(json.dumps({"status": "error", "error": f"Config not found: {config_path}"}))
        sys.exit(1)
    if output_path.exists() and not args.force:
        print(json.dumps({"status": "error", "error": f"Output already exists: {output_path}. Use --force to overwrite."}))
        sys.exit(1)

    with config_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Separador de LECTURA del enriched. La clave canónica en los country_config es
    # `csv_separator`; `separator` se acepta como alias histórico. Antes solo se leía
    # `separator`, así que los configs que solo declaraban `csv_separator` caían al ";"
    # por defecto y reventaban con "Expected 1 fields" — de ahí la clave duplicada que
    # arrastran ar/cr/ec/mx/pa.yaml. (Detectado en DO, 2026-07-24.)
    _std = config.get("standardize", {}) or {}
    sep = _std.get("csv_separator") or _std.get("separator") or ";"

    # Verificación dura: el separador debe producir >1 columna en la cabecera.
    with input_path.open("r", encoding="utf-8") as _f:
        _head = _f.readline()
    if _head.count(sep) == 0:
        _alt = "," if sep == ";" else ";"
        if _head.count(_alt) > 0:
            print(json.dumps({"status": "warning",
                              "msg": f"separador '{sep}' no aparece en la cabecera; usando '{_alt}'"}),
                  file=sys.stderr)
            sep = _alt

    df = pd.read_csv(str(input_path), sep=sep, dtype=str, keep_default_na=False)

    df_out, stats = standardize(df, config, separator=sep)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Harvard Dataverse requires comma-separated output — always ","
    df_out.to_csv(str(output_path), sep=",", index=False, encoding="utf-8")

    stats["output_path"] = str(output_path)
    stats["status"] = "ok"
    print(json.dumps(stats, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
