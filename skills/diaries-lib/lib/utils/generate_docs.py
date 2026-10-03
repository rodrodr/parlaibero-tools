#!/usr/bin/env python3
"""
Generate user-facing corpus documentation (README, data dictionary, JSON-LD).

CLI:
    python generate_docs.py --country <iso2> --config <yaml_path> \
        --corpus-info <json_path> --output-dir <dir> \
        --interventions <csv_path>
"""
import re
import sys
import json
import argparse
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

# ── Canonical data dictionary ─────────────────────────────────────────────────
_DATA_DICT = [
    ("id_session",          "string",  "Stable WITHIN this edition, not across editions: the ordinals are derived from position, so adding or removing sessions in a later edition shifts every identifier after the change. Cite the edition, and do not use these identifiers as a key against another edition. Format: {ISO2}{legislature:03d}{session:04d}. The ordinals are DERIVED (legislature by earliest session date, session by date and number within it), because `legislature` and `session_number` are country-specific text and not always present.", "CR0190010"),
    ("id_int",              "string",  "Stable WITHIN this edition, not across editions, for the same reason as `id_session`. Format: id_session + intervention_order as 5 digits. Unique across the corpus. Prolegomena rows (intervention_order = 0) end in 00000. Duplicate front matter within a session is disambiguated upstream by suffixing session_number (104 -> 104B), which yields a distinct id_session -- never by special id_int ranges.", "CR019001000120"),
    ("legislature",         "string",  "Legislature identifier as printed in the source. Format is country-specific and NOT comparable across countries (roman numerals, year ranges, ordinals).", "XIV"),
    ("legislative_session", "string",  "Legislative session or period within the legislature, where the source records one.", "1"),
    ("session_number",      "string",  "Session number. Usually an integer, but may be alphanumeric where the chamber appends a session-type suffix.", "12A"),
    ("date",                "date",    "Session date in ISO 8601 format.",                                          "2023-03-15"),
    ("session_type",        "string",  "Session type, normalised to five values across the collection: ordinaria, extraordinaria, solemne, instalación, otros (the record's own wording is mapped to these; the values are Spanish literals in every country, Brazil and Portugal included). «otros» covers both a type outside the four named and a sitting whose record states no type at all; the column is never empty.", "ordinaria"),
    ("intervention_order",  "integer", "Position of the intervention within its session (1-based, in order of record). **0 = front matter**: cover page, summary, index or roll call preceding the first intervention. These precede WITHOUT displacing the numbering of the rest.", "7"),
    ("speaker_raw",         "string",  "Speaker designation exactly as it appears in the parliamentary record.",     "Sr. PEDRO NUNO SANTOS"),
    ("id_dep",              "string",  "Deputy identifier in the national roster. Empty where the speaker could not be linked, or where the speaker is not a member (minister, clerk, guest).", "PT0042"),
    ("speaker_name",        "string",  "Normalised full name of the deputy. Empty when id_dep is empty.",            "Pedro Nuno Santos"),
    ("sex",                 "string",  "Sex of the deputy: M / F. Empty when id_dep is empty, or when the roster does not record the member's sex. DERIVED variable — the provenance of every value is recorded in `sex_source` of the companion roster file, so users can restrict to the higher-precision levels.", "F"),
    ("party",               "string",  "Political party of the deputy. Whether this varies with the session date depends on how each national roster is built; see the `notes` field of corpus_info.json.", "PS"),
    ("district",            "string",  "Electoral district of the deputy.",                                         "Porto"),
    ("dm_speech",           "binary",  "1 if the row is parliamentary speech, 0 if it is not (front matter, summary, vote tally, reproduced document). Filters the corpus to speech with a single condition. Populated with evidence: 0 is set only where demonstrated, so 1 means «not shown to be non-speech».", "1"),
    ("text",                "string",  "Full text of the intervention.",                                            "Mr President, I request the floor..."),
]

LICENSE = "CC BY 4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"


# ── Stats helper ──────────────────────────────────────────────────────────────

# ── Familias de resolución del orador (tr-0114, 2026-09-04) ─────────────────────────────────
# Cada país etiqueta sus métodos con su propio vocabulario (`frozen:publicado`, `apellido_unico`,
# `ventana`, `presidencia_nombrada:*`…). Publicar ese vocabulario en bruto no se entiende; publicar
# un glosario fijo de 13 métodos —lo que hacía este generador hasta el 2026-09-04— describía
# procedimientos que ningún corpus usaba. Las familias agrupan lo que significa cada etiqueta y se
# cuentan sobre las filas de HABLA del paquete depositado; el vocabulario crudo va al JSON.
_FAMILIES = [
    ("inherited", "Inherited",
     "Link inherited from the human-reviewed matching of the previous edition (August 2026), kept only where it agrees with the current register"),
    ("source", "From the source",
     "Identifier supplied by the source itself (the chamber's structured feed)"),
    ("register", "Register, by name",
     "Name resolved against the register of that legislature or session date (full name, name in brackets, token coverage, initials; members named as government or guests included)"),
    ("register_fuzzy", "Register, with tolerance",
     "Name resolved against the register with orthographic tolerance, where the OCR or the transcription degraded it"),
    ("surname", "Surname only",
     "Surname-only marker resolved because the surname is unique in the legislature"),
    ("sitting", "By the sitting",
     "Resolved by the sitting itself: the roll call of that day, the members present, the mandate window at the session date, or the sex declared by the form of address"),
    ("chair_named", "Chair, named",
     "Chair or bureau member named in the marker or declared by the record's cover and hand-over lines"),
    ("office", "Office without a name",
     "Chamber office or named non-member (PRESIDENTE with no name, SECRETARIO, ministers, clerks, guests): linked where the cover or the hand-over lines identify a member holding the chair; no id by design otherwise"),
    ("structural", "Structural",
     "Resolved from a structural feature of the marker rather than the name alone (initials, party and state in brackets, apposition)"),
    ("manual", "Manual",
     "Human review by the corpus authors, or assisted resolution of an ambiguous form"),
    ("not_speaker", "Not a speaker",
     "Not a person, or no speaker form in the record: no id by design"),
    ("unresolved", "Unresolved",
     "Named speaker left unlinked: no match, or several candidates the record does not separate"),
    ("other", "Other", "Rows outside the families above"),
]


def _family(m: str, linked: bool, country: str) -> str:
    f = _family_base(m, linked, country)
    # una fila SIN id de una familia que resuelve (por sesión, padrón, apellido…) es un caso no
    # resuelto: se cuenta como tal, no como éxito de la familia (UY: 7.481 «por_sesion» ambiguas)
    if not linked and f not in ("office", "not_speaker", "unresolved", "other"):
        return "unresolved"
    if linked and f == "unresolved":        # etiqueta «unmatched» con id (CL: 2 filas): no es un no resuelto
        return "other"
    return f


def _family_base(m: str, linked: bool, country: str) -> str:
    m = (m or "").strip().lower()
    if m == "":
        if linked:
            return "source" if country == "cl" else "other"
        return "unresolved"
    if m == "congelada_role":
        return "office"
    if m.startswith(("frozen", "congelada")):
        return "inherited"
    if m in ("role", "cargo_anonimo"):
        return "office"
    if m.startswith("presidencia") or m in ("vicepresidencia_nombrada", "secretaria_nombrada"):
        return "chair_named"
    if m in ("manual", "llm"):
        return "manual"
    if m in ("not_speaker", "sin_forma"):
        return "not_speaker"
    if m in ("unmatched", "ambiguous", "ambiguo", "ambiguous_unresolved", "fuera_de_mandato", "sin_nombre"):
        return "unresolved"
    if (m in ("attendance", "por_sesion", "ventana", "ventana_sexo", "nombre_ventana",
              "nombre_pila_ventana", "gender_split")
            or m.startswith(("pase_de_lista", "padron_fecha"))):
        return "sitting"
    if m.startswith("apellido"):
        return "register_fuzzy" if "difuso" in m else "surname"
    if m == "fuzzy" or "difuso" in m or "ocr_il" in m or m == "surname_fix":
        return "register_fuzzy"
    if m == "structural":
        return "structural"
    return "register"


def _match_families(enriched_path, country: str, date_max: str = None) -> dict:
    """Cuenta las filas de HABLA del enriched por método crudo y por familia, acotadas a la
    fecha máxima del paquete (EC y SV llevan corte temporal). Devuelve {} si no hay enriched."""
    if not HAS_PANDAS or not enriched_path or not Path(enriched_path).exists():
        return {}
    try:
        with Path(enriched_path).open("r", encoding="utf-8") as _f:
            head = _f.readline()
        sep = max([",", ";", "\t"], key=head.count)
        cols = [c.strip() for c in head.strip().split(sep)]
        mcol = "match_method" if "match_method" in cols else ("metodo" if "metodo" in cols else None)
        if not mcol:
            return {}
        use = [c for c in (mcol, "id_dep", "dm_speech", "date") if c in cols]
        raw, linked = {}, {}
        for df in pd.read_csv(str(enriched_path), sep=sep, dtype=str, keep_default_na=False,
                              usecols=use, chunksize=200000):
            if "dm_speech" in df.columns:
                df = df[df["dm_speech"].astype(str).str.strip() != "0"]
            if date_max and "date" in df.columns:
                d = df["date"].astype(str).str.strip()
                df = df[(d == "") | (d <= date_max)]
            has_id = df["id_dep"].astype(str).str.strip() != ""
            for m, n in df[mcol].value_counts().items():
                raw[m] = raw.get(m, 0) + int(n)
            for m, n in df[mcol][has_id].value_counts().items():
                linked[m] = linked.get(m, 0) + int(n)
        fam = {}
        for m, n in raw.items():
            k_lnk = linked.get(m, 0)
            # una etiqueta puede tener filas con y sin id (role, por_sesion): se reparten
            for f, cnt, lk in ((_family(m, True, country), k_lnk, k_lnk),
                               (_family(m, False, country), n - k_lnk, 0)):
                if cnt <= 0:
                    continue
                e = fam.setdefault(f, {"rows": 0, "linked": 0, "methods": {}})
                e["rows"] += cnt; e["linked"] += lk
                e["methods"][m] = e["methods"].get(m, 0) + cnt
        total = sum(v["rows"] for v in fam.values())
        order = {k: i for i, (k, _, _) in enumerate(_FAMILIES)}
        out = [{"key": k, "label": dict((a, b) for a, b, _ in _FAMILIES)[k],
                "rows": v["rows"], "linked": v["linked"],
                "share": round(v["rows"] / total, 4) if total else 0.0,
                "methods": dict(sorted(v["methods"].items(), key=lambda x: -x[1]))}
               for k, v in sorted(fam.items(), key=lambda x: (-x[1]["rows"], order.get(x[0], 99)))]
        return {"speech_rows": total, "date_max": date_max, "method_column": mcol,
                "families": out}
    except Exception:
        return {}


def _compute_stats(interventions_path: Path, sep: str = ";",
                   matching_path: Path = None) -> dict:
    if not HAS_PANDAS or not interventions_path or not interventions_path.exists():
        return {}
    try:
        df = pd.read_csv(str(interventions_path), sep=sep, dtype=str, keep_default_na=False)
        matched = int((df["id_dep"].notna() & (df["id_dep"] != "")).sum()) if "id_dep" in df.columns else 0
        total = len(df)

        stats = {
            "total_interventions": total,
            # ⚠ (tr-0118) Las sesiones se cuentan por `id_session`, que es el identificador
            # publicado. Contar pares (fecha, número) daba una cifra distinta en el README que en
            # el resto de documentos allí donde una fecha lleva dos sesiones o el número está vacío
            # (EC 6.104 frente a 6.105; UY 2.812 frente a 2.813).
            "total_sessions": (int(df["id_session"].replace("", pd.NA).dropna().nunique())
                               if "id_session" in df.columns else
                               (df[["date", "session_number"]].drop_duplicates().shape[0]
                                if "date" in df.columns else None)),
            # ⚠ Excluir las fechas VACÍAS antes del min/max. EC tiene 4.162 filas cuyo meta de
            # sesión nunca se extrajo y llevan `date` vacío; la cadena vacía ganaba el mínimo y el
            # README publicaba «spanning  to 2026-01-22», sin fecha de inicio.
            "date_min": (df.loc[df["date"].astype(str).str.strip() != "", "date"].min()
                         if "date" in df.columns else None),
            "date_max": (df.loc[df["date"].astype(str).str.strip() != "", "date"].max()
                         if "date" in df.columns else None),
            "legislatures": sorted(df["legislature"].dropna().unique().tolist()) if "legislature" in df.columns else [],
            "matched_deputies": matched,
            "unique_deputies": int(df["id_dep"].replace("", pd.NA).dropna().nunique()) if "id_dep" in df.columns else None,
            "match_rate": round(matched / max(total, 1), 4),
        }

        # Fuente PREFERENTE para el desglose por método: el enriched, que lleva `match_method`
        # por FILA y refleja la atribución DEFINITIVA. La matching_table describe solo la fase
        # de match y se queda obsoleta si el merge reatribuye después (en DO, 32.337 filas
        # `role` pasaron a `president_meta`: documentarlas como `role` daba a entender que
        # estaban sin vincular). (DO, 2026-07-24.)
        _enr = Path(str(interventions_path).replace(
            f"/standardize/{Path(interventions_path).name}", "/merge/interventions_enriched.csv"))
        if _enr.exists():
            with _enr.open("r", encoding="utf-8") as _ef:
                _eh = _ef.readline()
            if "match_method" in _eh:
                edf = pd.read_csv(str(_enr), sep=max([",", ";", "\t"], key=_eh.count),
                                  dtype=str, keep_default_na=False, usecols=["match_method"])
                mc = edf["match_method"].replace("", "unmatched").value_counts().to_dict()
                inst = int(mc.get("institutional", 0))
                stats["institutional_interventions"] = inst
                stats["deputy_interventions"] = total - inst
                stats["deputy_match_rate"] = round(matched / max(total - inst, 1), 4)
                stats["match_method_counts"] = {k: int(v) for k, v in mc.items()
                                                if k != "institutional"}
                return stats

        # Fallback: matching_table (corpus sin enriched a mano)
        if matching_path and Path(matching_path).exists():
            with Path(matching_path).open("r", encoding="utf-8") as _mf:
                _mh = _mf.readline()
            mt = pd.read_csv(str(matching_path), sep=max([",", ";", "\t"], key=_mh.count),
                             dtype=str, keep_default_na=False)
            # `legislature` NO está en la matching_table de todos los países (DO no la tiene):
            # exigirla dejaba `match_method_counts` vacío y la documentación acababa listando
            # métodos que el corpus no usa. `speaker_raw` es la clave natural. (DO, 2026-07-24.)
            if "match_method" in mt.columns and "speaker_raw" in mt.columns:
                join_cols = ["speaker_raw", "legislature"] if "legislature" in mt.columns else ["speaker_raw"]
                merged = df.merge(mt[join_cols + ["match_method"]].drop_duplicates(join_cols),
                                  on=join_cols, how="left")
                method_counts = merged["match_method"].value_counts().to_dict()
                institutional = int(method_counts.get("institutional", 0))
                deputy_total = total - institutional
                stats["institutional_interventions"] = institutional
                stats["deputy_interventions"] = deputy_total
                stats["deputy_match_rate"] = round(matched / max(deputy_total, 1), 4)
                # Per-method intervention counts (excluding institutional)
                stats["match_method_counts"] = {
                    k: int(v) for k, v in method_counts.items() if k != "institutional"
                }

        return stats
    except Exception:
        return {}


# ── README generator ──────────────────────────────────────────────────────────

def _gen_readme(country: str, config: dict, info: dict, stats: dict) -> str:
    name = config.get("name", country.upper())
    today = date.today().isoformat()
    authors = info.get("authors", [])
    authors_str = "; ".join(authors) if authors else "—"
    diary_source = info.get("diary_source", "—")
    deputy_source = info.get("deputy_source", "—")
    transformation = info.get("transformation", "—")
    notes = info.get("notes") or ""
    license_val = info.get("license", LICENSE)
    license_url = info.get("license_url", LICENSE_URL)

    lines = [
        f"# {name} — Parliamentary Interventions Corpus",
        "",
        f"> **License:** [{license_val}]({license_url})  ",
        f"> **Generated:** {today}  ",
        f"> **Authors:** {authors_str}",
        "",
    ]

    # ── Overview ──
    lines += ["## Overview", ""]
    if stats:
        n = stats.get("total_interventions", "—")
        s = stats.get("total_sessions", "—")
        d_min = stats.get("date_min", "—")
        d_max = stats.get("date_max", "—")
        legs = stats.get("legislatures", [])
        mr = stats.get("match_rate", 0)
        nd = stats.get("unique_deputies", "—")
        lines += [
            f"This corpus contains **{n:,} parliamentary interventions** from **{s:,} sessions**",
            f"spanning **{d_min} to {d_max}**.",
            "",
        ]
        if legs:
            lines += [f"**Legislatures covered:** {', '.join(legs)}", ""]

        # ⚠ La vinculación se publica con la MISMA definición en las tres lenguas.
        # El inglés la calculaba sobre TODAS las filas y el español/portugués sobre las de
        # HABLA, así que el mismo corpus daba dos cifras distintas según el idioma y ninguna
        # decía sobre qué. En CL la brecha era de 6,4 puntos (88,7% frente a 95,1%). Manda el
        # bloque `linkage` de corpus_info.json, que es donde vive la definición homogénea.
        _lk = info.get("linkage") or {}
        if _lk.get("speech_rows") and _lk.get("linked") is not None:
            _desc = _lk.get("cannot_hold_seat_discounted", 0)
            # ⚠ Definición tr-0109 (2026-09-03): se descuentan también las filas que el acta hace
            #   INATRIBUIBLES (voces colectivas, anónimos). Hasta el 2026-09-04 esta frase solo
            #   nombraba el primer descuento y la cifra publicada no se reproducía con ella (PT).
            _unat = _lk.get("unattributable_rows") or 0
            _unat_txt = (f"and the {_unat:,} rows the record itself makes **unattributable** "
                         "(collective voices of a bench, anonymous speakers)" if _unat else
                         "and the rows the record itself makes **unattributable** (collective "
                         "voices of a bench, anonymous speakers), of which this corpus has none")
            lines += [
                f"**Deputy linkage:** **{_lk['gross']:.1%} gross** and **{_lk['effective']:.1%} "
                f"effective** — {_lk['linked']:,} of {_lk['speech_rows']:,} speech rows carry a "
                f"member id ({nd:,} unique deputies).  ",
                f"Effective linkage discounts the {_desc:,} rows spoken by a **named non-member** "
                "(ministers without seat, clerks, prosecutors, ambassadors, guests), who cannot "
                f"hold a seat and are absent from the register by definition, {_unat_txt}. Rows "
                "attributed to an **unnamed** chamber office are not discounted: whoever chairs is "
                "a member, so an unrecovered identity is a gap in this corpus, not a structural "
                "exclusion. The same definition is applied to all sixteen ParlaIbero corpora, "
                "which is what makes the effective figure comparable between them — the gross one "
                "is not.",
                "",
            ]
        elif "deputy_match_rate" in stats:
            inst = stats.get("institutional_interventions", 0)
            dep_total = stats.get("deputy_interventions", 0)
            dep_rate = stats["deputy_match_rate"]
            lines += [
                f"**Deputy linkage:** {dep_rate:.1%} of deputy interventions linked to a deputy record "
                f"({nd:,} unique deputies, out of {dep_total:,} deputy interventions).  ",
                f"The remaining {inst:,} interventions correspond to institutional speakers "
                f"(government members, ministers, etc.) and are correctly excluded from linkage.",
                "",
            ]
        else:
            lines += [
                f"**Deputy linkage:** {mr:.1%} of interventions linked to a deputy record ({nd} unique deputies).",
                "",
            ]

    # ── Data sources ──
    lines += [
        "## Data Sources",
        "",
        "### Parliamentary Records",
        "",
        diary_source,
        "",
        "### Deputy Metadata",
        "",
        deputy_source,
        "",
    ]

    # ── Methodology ──
    lines += [
        "## Methodology",
        "",
        transformation,
        "",
        "The corpus was produced using the **ParlaIbero pipeline**, which covers:",
        "",
        "1. Text extraction from source documents (OCR or direct digitisation)",
        "2. Speaker identification and tagging",
        "3. Session metadata extraction (date, legislature, session type)",
        "4. Fuzzy matching of speaker names against the deputy reference database",
        "5. Standardisation to the canonical schema",
        "",
    ]

    # ── Speaker matching ──
    # ⚠ Desde el 2026-09-04 (tr-0114) la tabla sale de las FAMILIAS de resolución medidas en el
    #   enriched del país (stats["match_families"]), no de un glosario fijo: hasta entonces el
    #   README listaba 13 métodos que ningún corpus del reproceso usaba y omitía los reales.
    lines += [
        "## Speaker Matching",
        "",
        "Each intervention is attributed to a member by resolving the speaker as printed "
        "(`speaker_raw`) against the national register. The unit of resolution — the legislature, "
        "the sitting, or the mandate window at the session date — is the one described in the "
        "Methodology section. The table counts the deposited speech rows (`dm_speech = 1`) by the "
        "way their speaker was resolved; the raw per-row labels are kept in `match_methods.json`.",
        "",
    ]
    _mf = stats.get("match_families") or {}
    if _mf.get("families"):
        _desc = {k: d for k, _, d in _FAMILIES}
        lines += [
            "| How the speaker was resolved | Speech rows | % | With member id |",
            "|---|---:|---:|---:|",
        ]
        for f in _mf["families"]:
            lines.append(f"| **{f['label']}** — {_desc.get(f['key'], '')} | {f['rows']:,} | "
                         f"{f['share']:.1%} | {f['linked']:,} |")
        lines += [""]
    else:
        lines += ["Per-row resolution counts are not available for this corpus.", ""]

    # ── Schema ──
    lines += [
        "## Data Schema",
        "",
        f"The dataset contains {len(_DATA_DICT)} columns. See [`data_dictionary.md`](data_dictionary.md) for full descriptions.",
        "",
        "| Column | Type | Description |",
        "|--------|------|-------------|",
    ]
    for col, dtype, desc, _ in _DATA_DICT:
        lines.append(f"| `{col}` | {dtype} | {desc} |")

    # ── Citation ──
    lines += [
        "",
        "## Citation",
        "",
        "If you use this corpus in your research, please cite it as:",
        "",
        "```",
    ]
    if authors:
        citation_authors = "; ".join(authors)
        lines.append(f"{citation_authors} ({today[:4]}). {name} — Parliamentary Interventions Corpus.")
    else:
        lines.append(f"ParlaIbero Project ({today[:4]}). {name} — Parliamentary Interventions Corpus.")
    lines += [
        f"ParlaIbero. Licensed under {license_val}. {license_url}",
        "```",
        "",
    ]

    # ── License ──
    lines += [
        "## License",
        "",
        f"This dataset is released under the [{license_val}]({license_url}) licence.",
        "You are free to share and adapt the material for any purpose, provided you give",
        "appropriate credit, provide a link to the licence, and indicate if changes were made.",
        "",
    ]

    # ── Notes ──
    if notes:
        lines += ["## Notes", "", notes, ""]

    return "\n".join(lines)


# ── Data dictionary generator ─────────────────────────────────────────────────

def _real_examples(interventions_path, sep) -> dict:
    """Ejemplos tomados del CSV del propio país. La plantilla traía valores de PT
    (`PT0042`, `Pedro Nuno Santos`, `Porto`, `XIV`), que en la documentación de
    cualquier otro país son sencillamente falsos. (DO, 2026-07-24.)"""
    if not HAS_PANDAS or not interventions_path or not Path(interventions_path).exists():
        return {}
    try:
        # ⚠ Se lee por TROZOS hasta que todas las columnas tengan un valor real. Con las
        #   20.000 primeras filas, CL (sin `district` en 1990-1991) publicaba «Porto», el valor
        #   de la plantilla, como ejemplo de distrito chileno (revisión del 2026-09-03). Una
        #   columna vacía en todo el fichero devuelve «» y el diccionario imprime «—»: nunca
        #   un valor inventado.
        from collections import Counter
        ex = {}
        cols = None
        pendientes = None
        for i, df in enumerate(pd.read_csv(str(interventions_path), sep=sep, dtype=str,
                                           keep_default_na=False, chunksize=50000)):
            if cols is None:
                cols = list(df.columns)
                pendientes = set(cols)
            for col in list(pendientes):
                vals = [v for v in df[col].tolist() if v and v.strip()]
                if not vals:
                    continue
                if col == "text":
                    v = max(vals[:200], key=len)[:60].replace("\n", " ").strip()
                    ex[col] = v + "…"
                else:
                    # el valor no vacío más frecuente del trozo, que es el más representativo
                    ex[col] = Counter(vals).most_common(1)[0][0][:48]
                pendientes.discard(col)
            if not pendientes or i >= 60:
                break
        for col in (cols or []):
            ex.setdefault(col, "")
        return ex
    except Exception:
        return {}


def _gen_data_dictionary(examples: dict = None) -> str:
    lines = [
        "# Data Dictionary — Canonical Schema",
        "",
        f"The corpus exports {len(_DATA_DICT)} columns in the following order:",
        "",
        "| # | Column | Type | Description | Example |",
        "|---|--------|------|-------------|---------|",
    ]
    examples = examples or {}
    for i, (col, dtype, desc, example) in enumerate(_DATA_DICT, 1):
        # la plantilla solo suple cuando el CSV no se leyó; una columna leída y vacía va como «—»
        example = examples[col] if col in examples else example
        lines.append(f"| {i} | `{col}` | {dtype} | {desc} | {('`' + example + '`') if example else '—'} |")
    lines += [""]
    return "\n".join(lines)


# ── JSON-LD generator ─────────────────────────────────────────────────────────

def _gen_jsonld(country: str, config: dict, info: dict, stats: dict,
                interventions_path: Path) -> str:
    name = config.get("name", country.upper())
    today = date.today().isoformat()
    authors = info.get("authors", [])
    license_url = info.get("license_url", LICENSE_URL)

    # ⚠ (tr-0118) La descripción se COMPONE con los hechos del corpus. Antes salía del config, que
    # no la trae, y los dieciséis publicaban «Parliamentary speeches corpus — XX», que no dice nada.
    _inst = config.get("institution") or config.get("chamber") or ""
    _pais = config.get("country_name_en") or name
    _n = stats.get("total_interventions"); _s = stats.get("total_sessions")
    _d0, _d1 = stats.get("date_min"), stats.get("date_max")
    description = config.get("description") or (
        (f"Parliamentary interventions of the {_inst} of {_pais}" if _inst else
         f"Parliamentary interventions from {_pais}")
        + (f": {_n:,} rows across {_s:,} sessions" if _n and _s else "")
        + (f", {_d0} to {_d1}" if _d0 and _d1 else "")
        + ", each attributed to the speaker as printed and, where resolved, to a member of the "
          "companion register, which carries party, district and a derived sex variable.")
    # el enlace del conjunto es su página de depósito, que `incrustar_doi.py` deja en corpus_info
    url = config.get("url") or info.get("dataverse_url", "")

    def _creador(a):
        m = re.match(r"^(.*?)\s*\((.*?)\)\s*$", a.strip())
        nombre, resto = (m.group(1), m.group(2)) if m else (a.strip(), "")
        c = {"@type": "Person", "name": nombre}
        mo = re.search(r"ORCID:\s*(\d{4}-\d{4}-\d{4}-[\dX]{4})", resto)
        if mo:
            c["identifier"] = f"https://orcid.org/{mo.group(1)}"
            resto = resto[:mo.start()].rstrip(" ;")
        if resto:
            c["affiliation"] = {"@type": "Organization", "name": resto}
        return c

    creators = [_creador(a) for a in authors] if authors else [
        {"@type": "Organization", "name": "ParlaIbero Project"}]

    variable_measured = [
        {"@type": "PropertyValue", "name": col, "description": desc}
        for col, _, desc, _ in _DATA_DICT
    ]

    distribution = []
    if interventions_path and interventions_path.exists():
        distribution.append({
            "@type": "DataDownload",
            "name": interventions_path.name,
            "encodingFormat": "text/csv",
            # ⚠ (tr-0118) El NOMBRE del fichero, no la ruta local: `dataverse/paquetes/UY/...` no
            # existe para quien lee el metadato desde fuera.
            "contentUrl": interventions_path.name,
        })
        # ⚠ La distribución son DOS ficheros (diaries-document, Paso 5): la matriz y el padrón
        #   auxiliar `{ISO2}_deputies.csv`, unible por (id_dep, legislature). Hasta el 2026-09-02
        #   el jsonld solo declaraba la matriz, en los 16 países (tr-0106).
        roster_path = interventions_path.with_name(interventions_path.name.replace("_interventions", "_deputies"))
        if roster_path != interventions_path and roster_path.exists():
            distribution.append({
                "@type": "DataDownload",
                "name": roster_path.name,
                "description": "Companion roster of members, joinable to the interventions file on id_dep and, where the roster is in long format, on the legislature or the mandate window as well.",
                "encodingFormat": "text/csv",
                "contentUrl": roster_path.name,
            })

    dataset = {
        "@context": "https://schema.org/",
        "@type": "Dataset",
        "name": f"ParlaIbero — {name}",
        "description": description,
        "url": url,
        "license": license_url,
        "creator": creators,
        "datePublished": today,
        "dateModified": today,
        # el idioma real lo fija el paso propio de la colección (incrustar_doi.py): aquí un valor por defecto
        "inLanguage": config.get("language", "es"),
        "variableMeasured": variable_measured,
        "distribution": distribution,
    }

    if stats.get("total_interventions"):
        dataset["size"] = f"{stats['total_interventions']:,} interventions"
    if stats.get("date_min") and stats.get("date_max"):
        dataset["temporalCoverage"] = f"{stats['date_min']}/{stats['date_max']}"

    return json.dumps(dataset, ensure_ascii=False, indent=2)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate user-facing corpus documentation")
    parser.add_argument("--country", required=True, help="ISO 2-letter country code")
    parser.add_argument("--config", required=True, help="YAML config file")
    parser.add_argument("--corpus-info", required=True, dest="corpus_info",
                        help="corpus_info.json with interview answers")
    parser.add_argument("--output-dir", required=True, dest="output_dir")
    parser.add_argument("--interventions", default=None,
                        help="Standardised interventions CSV")
    parser.add_argument("--matching-table", default=None, dest="matching_table",
                        help="Matching table CSV (for deputy-only match rate)")
    parser.add_argument("--enriched", default=None,
                        help="Enriched matrix with per-row match_method (source/{iso}/merge/interventions_enriched.csv)")
    args = parser.parse_args()

    if not HAS_YAML:
        print(json.dumps({"status": "error", "error": "PyYAML not installed"}))
        sys.exit(1)

    config_path = Path(args.config)
    info_path = Path(args.corpus_info)
    output_dir = Path(args.output_dir)

    for p, label in [(config_path, "config"), (info_path, "corpus-info")]:
        if not p.exists():
            print(json.dumps({"status": "error", "error": f"{label} not found: {p}"}))
            sys.exit(1)

    with config_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    with info_path.open("r", encoding="utf-8") as f:
        info = json.load(f)

    interventions_path = Path(args.interventions) if args.interventions else None
    matching_path = Path(args.matching_table) if args.matching_table else None
    # Clave canónica `csv_separator`, con `separator` como alias histórico. Detectar mal el
    # separador aquí NO lanza error: _compute_stats lo captura y devuelve {}, generando la
    # documentación SIN estadísticas y en silencio. Por eso se decide por sniffing de la
    # cabecera, que no depende del config y es infalible. (DO, 2026-07-24.)
    _std = config.get("standardize", {}) or {}
    sep = _std.get("csv_separator") or _std.get("separator") or ";"
    if interventions_path and interventions_path.exists():
        with interventions_path.open("r", encoding="utf-8") as _f:
            _head = _f.readline()
        sep = max([",", ";", "\t"], key=_head.count)
    stats = _compute_stats(interventions_path, sep, matching_path)
    _enr = Path(args.enriched) if args.enriched else None
    _mf = _match_families(_enr, args.country.lower(), (stats or {}).get("date_max"))
    if _mf:
        stats = stats or {}
        stats["match_families"] = _mf
    if not stats:
        print(json.dumps({"status": "warning",
                          "msg": "ESTADÍSTICAS VACÍAS — la documentación saldrá sin cifras"}),
              file=sys.stderr)

    output_dir.mkdir(parents=True, exist_ok=True)
    files_generated = []

    readme_path = output_dir / "README.md"
    readme_path.write_text(_gen_readme(args.country, config, info, stats), encoding="utf-8")
    files_generated.append(str(readme_path))

    dict_path = output_dir / "data_dictionary.md"
    dict_path.write_text(_gen_data_dictionary(_real_examples(interventions_path, sep)),
                         encoding="utf-8")
    files_generated.append(str(dict_path))

    if stats.get("match_families"):
        _mp = output_dir / "match_methods.json"
        _mp.write_text(json.dumps({"country": args.country.lower(), "computed": date.today().isoformat(),
                                   **stats["match_families"]}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        files_generated.append(str(_mp))

    jsonld_path = output_dir / "dataset.jsonld"
    jsonld_path.write_text(
        _gen_jsonld(args.country, config, info, stats, interventions_path),
        encoding="utf-8"
    )
    files_generated.append(str(jsonld_path))

    print(json.dumps({
        "status": "ok",
        "files_generated": files_generated,
        "output_dir": str(output_dir),
        "stats": stats,
    }, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
