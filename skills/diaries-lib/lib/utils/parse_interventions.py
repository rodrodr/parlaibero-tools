#!/usr/bin/env python3
"""
Extract <int> blocks from tagged text and generate CSV rows.

Supports two tagging conventions:

  inline (standard pipeline):
      <int speaker="NAME">intervention text</int>

  standalone (Portugal-style):
      <int>NAME</int>
      intervention text on following lines until next <int>

      Also handles embedded variant found in old OCR files:
      <int>NAME (PARTY):-  full text here...</int>

Format is auto-detected by default; override with --format.

CLI:
    python parse_interventions.py \\
        --input  <tagged_path> \\
        --meta   <meta_json_path> \\
        --output <csv_path> \\
        [--min-chars 10] [--separator ";"] [--format auto|inline|standalone]
"""
import sys
import json
import argparse
import csv
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# ── Regexes ───────────────────────────────────────────────────────────────────

# Inline format:  <int speaker="NAME">text</int>
# ⚠ Tolera atributos ADICIONALES (`<int speaker="X" kind="documento">`). Exigir que `speaker`
# fuera el único atributo descartaba en silencio 13.111 intervenciones de DO —las citas
# documentales que el tagger narrativo ya etiqueta— sin dar ningún error: el marcador estaba
# en el texto y la fila no aparecía en la matriz.
_INLINE_RE = re.compile(r'<int\s+speaker="([^"]*)"[^>]*>(.*?)</int>', re.DOTALL)

# Standalone format:  <int>CONTENT</int>
_STANDALONE_RE = re.compile(r'<int>(.*?)</int>', re.DOTALL)

# Embedded-text separator inside a standalone tag.
# Handles both colon ("NAME (PARTY): text") and em-dash ("NAME (PARTY) — text").
_EMBEDDED_SPLIT_RE = re.compile(
    r'^([^:–—]{2,80}?)(?::\s*|(?:\s*[–—]\s*))[.·\-–—]*\s*(.+)$',
    re.DOTALL,
)

# Trailing party-code suffix: (PS), {UEDS), [PSD]-, (CI)S-PP), (BE)), etc.
# The `[\)\]\}»]*` (zero-or-more) handles doubled closing brackets like "))"
_PARTY_SUFFIX_RE = re.compile(
    r'\s*[\(\[\{«]([\w\.\-/ ]{0,20}?)[\)\]\}»]*[\.\-!\']*\s*$'
)

# Captures the inner party code from a suffix match (group 1 of _PARTY_SUFFIX_RE)
_PARTY_INNER_RE = re.compile(
    r'[\(\[\{«]([\w\.\-/ ]{1,20}?)[\)\]\}»]'
)

# Reject tag content that is only a party/group code (no real name).
# Uses case-insensitive flag so "Indep./UEDS" is caught too.
_PARTY_ONLY_RE = re.compile(
    r'^[\(\[\{«]?[A-Za-z0-9À-ÿ\.\-/\$\s]{1,25}[\)\]\}»]*[\.\-!\']*$'
)

# Reject content that looks like a party-only label even with mixed case.
# Catches "Indep.", "Indep-", "Indep./UEDS", "P$D", "PC.F", etc.
_LABEL_ONLY_RE = re.compile(
    r'^(?:Indep\.?|P[\$\.][\w\.]*|PC\.?[A-Z]?|CDS\.?|UEDS\.?|PPM\.?|UDP\.?|PRD\.?)[\-/\.\s]*(?:[A-Z]{2,6})?$',
    re.IGNORECASE,
)

# Transition phrases that signal the tag contains a floor-change, not a speaker label
_TRANSITION_RE = re.compile(r'O (?:Sr\.|Sjr\.|Snr\.|Skjr\.)| A (?:Sr\.ª|Sra\.)')

# Fields written to CSV
_FIELDNAMES = [
    # ⚠ `session_id` es la CLAVE que une la matriz con todo lo derivado de la sesión —meta,
    # presidencia por tramo, dedupe, renumeración—. Sin ella hay que reconstruirla por
    # (fecha + nº de acta), que no es única: las sesiones sin fecha legible quedan fuera y las
    # matutina/vespertina del mismo día colisionan. Añadida 2026-08-15 al atribuir la presidencia
    # de EC, donde 492.691 filas (40,9%) no se podían asignar a nadie por falta de esta columna.
    #
    # ⚠⚠ Añadir una columna CAMBIA LA CABECERA: este parser ESCRIBE EN APPEND, así que añadir
    # filas nuevas a un `interventions_raw.csv` creado con el esquema anterior las desalinea en
    # silencio. Al reprocesar un país hay que RECONSTRUIR la matriz entera, no ampliarla.
    # `standardize_csv.py` no la propaga: la salida canónica conserva sus columnas.
    "session_id",
    "legislature",
    "session_number",
    "session_type",
    "date",
    "president",
    "speaker_raw",
    "party_raw",
    "text",
]

# Threshold: tag content longer than this is treated as embedded text
_EMBEDDED_CHAR_THRESHOLD = 80


MARCA_PAGINA = re.compile(r"^[ \t]*-{3}\s*PAGE\s+(\d+)\s*-{3}[ \t]*$", re.M | re.I)


def quitar_marca_pagina(texto: str) -> tuple[str, list[int]]:
    """Retira las marcas de página del `text` y devuelve las páginas que abarcaba.

    ⚠ **La página NO se añade a la fila.** El esquema canónico es fijo y el escritor CSV lleva
    la lista de columnas cerrada: meter una clave extra hace fallar TODAS las escrituras
    (`dict contains fields not in fieldnames`). Si algún día la página pasa a ser columna
    publicable, hay que añadirla al esquema primero, no colarla por aquí.

    ⚠ **El marcador jamás llega al corpus.** Es una frontera técnica que sirve para limpiar
    mobiliario y para saber en qué página está cada intervención; dejarlo dentro del `text`
    sería fabricar la misma basura que el pipeline retira.
    """
    paginas = [int(m.group(1)) for m in MARCA_PAGINA.finditer(texto)]
    return MARCA_PAGINA.sub("", texto).strip(), paginas


def _clean_speaker(raw: str) -> tuple[str | None, str | None]:
    """Normalise and validate speaker_raw extracted from a standalone <int> tag.

    Returns (cleaned_name, party_raw), where either can be None.
    cleaned_name is None if the content is not a valid speaker.
    """
    s = raw.strip()

    # Strip feminine-ordinal prefix "ª " (OCR for "Sr.ª ") before any other check
    s = re.sub(r'^ª\s+', '', s).strip()
    # Strip single lowercase article prefix "a " (OCR for "A Sr.ª ") before name
    s = re.sub(r'^[ao]\s+(?=[A-ZÁÀÃÂÉÊÍÓÔÕÚÇ])', '', s).strip()

    # Reject empty or very short
    if len(s) < 3:
        return None, None

    # Reject content that starts with a lowercase letter (phrase, not a name)
    if s[0].islower():
        return None, None

    # Reject if the tag contains a floor-change transition phrase
    # e.g. "Pedro Pinto (CH) — Está a fugir!  O Sr. Rui Tavares"
    if _TRANSITION_RE.search(s):
        return None, None

    # Reject all-uppercase short strings that look like party/group codes.
    # Threshold is intentionally low (≤6) so that corpora where names are entirely
    # uppercase (e.g. Paraguay OCR) are not incorrectly filtered.
    # Portuguese party codes (PS, PSD, BE, CDS …) are all ≤6 chars and still rejected.
    alpha_words = re.findall(r'[A-Za-záàãâéêíóôõúçÀ-ÿ]+', s)
    if alpha_words and all(w == w.upper() for w in alpha_words) and len(s) <= 6:
        return None, None

    # Reject known mixed-case party/group label patterns: "Indep.", "P$D", etc.
    if _LABEL_ONLY_RE.match(s):
        return None, None

    # Extract party code before stripping it: "(PS)", "(PSD)", "(BE))", etc.
    party_raw = None
    party_m = _PARTY_SUFFIX_RE.search(s)
    if party_m:
        inner_m = _PARTY_INNER_RE.search(party_m.group(0))
        if inner_m:
            party_raw = inner_m.group(1).strip() or None

    # Strip trailing party-code suffixes
    s = _PARTY_SUFFIX_RE.sub('', s).strip()

    # After stripping party, reject if nothing recognisable remains
    if len(s) < 3:
        return None, None

    # Insert space between fused camelCase (OCR missing spaces): LuísMarquesGuedes
    s = re.sub(r'(?<=[a-záàãâéêíóôõúç])(?=[A-ZÁÀÃÂÉÊÍÓÔÕÚÇ])', ' ', s)

    # Strip residual trailing punctuation
    s = re.sub(r'[\-!;:\.,\'"]+$', '', s).strip()

    return (s if len(s) >= 3 else None), party_raw


# ── Format detection ──────────────────────────────────────────────────────────

def detect_format(tagged_text: str) -> str:
    """Return 'inline' or 'standalone' based on first <int> tag found."""
    first_inline = tagged_text.find('<int speaker="')
    first_standalone = re.search(r'<int>[^/]', tagged_text)  # <int>X not </int>

    if first_inline == -1 and first_standalone:
        return "standalone"
    if first_standalone is None and first_inline >= 0:
        return "inline"
    if first_inline >= 0 and first_standalone:
        # Both present — whichever comes first wins
        return "inline" if first_inline < first_standalone.start() else "standalone"
    return "inline"  # fallback


# ── Inline parser (original) ──────────────────────────────────────────────────

def _parse_inline(tagged_text: str, min_chars: int,
                  keep_untagged: bool = False) -> tuple[list[dict], int, int]:
    """Parse <int speaker="NAME">text</int> format.

    Returns (rows_without_session_fields, filtered_short, untagged_blocks).

    ⚠ `keep_untagged` (opt-in): SIN él, el texto FUERA de los <int> se CUENTA pero se DESCARTA —
    y en actas con estructura documental eso es una pérdida silenciosa mayúscula: en CL moderno
    los DOCUMENTOS DE LA CUENTA/anexos entre y tras los turnos son hasta el 77 % del acta
    (d_2024-12-02: la matriz retenía el 22,6 % de los caracteres — medido 2026-08-24). Con él,
    cada HUECO contiguo entra como fila SIN orador en su posición de documento (una fila por
    hueco, no por párrafo): nada se borra, se DECLARA — aguas abajo recibe `dm_speech = 0` y el
    hueco de cabecera es el Prolegomena ([[feedback_prolegomena]], [[anexos_del_diario]]).
    """
    rows = []
    filtered_short = 0
    untagged_blocks = 0
    pos = 0

    def _emite_hueco(gap: str):
        nonlocal untagged_blocks
        gs = gap.strip()
        if len(gs) <= 20:
            return
        untagged_blocks += 1
        if keep_untagged:
            gs, _p = quitar_marca_pagina(gs)
            if gs.strip():
                rows.append({"speaker_raw": "", "party_raw": "", "text": gs.strip()})

    for m in _INLINE_RE.finditer(tagged_text):
        _emite_hueco(tagged_text[pos:m.start()])
        speaker_raw, content = m.group(1), m.group(2)
        text_clean = content.strip()
        pos = m.end()
        if len(text_clean) < min_chars:
            filtered_short += 1
            continue
        text_clean, _pags = quitar_marca_pagina(text_clean)
        rows.append({"speaker_raw": speaker_raw, "party_raw": "", "text": text_clean})
    _emite_hueco(tagged_text[pos:])

    return rows, filtered_short, untagged_blocks


# ── Standalone parser ─────────────────────────────────────────────────────────

def _split_embedded(tag_content: str) -> tuple[str, str]:
    """Split 'SPEAKER (PARTY): text' or 'SPEAKER (PARTY) — text' into (speaker, text).

    Always tries the colon/em-dash split first, regardless of length.
    For long content without a recognisable separator, treats it as a (possibly
    garbled) speaker name and lets _clean_speaker decide whether to keep it.
    """
    m = _EMBEDDED_SPLIT_RE.match(tag_content)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    return tag_content, ""


def _parse_standalone(tagged_text: str, min_chars: int) -> tuple[list[dict], int, int]:
    """Parse <int>NAME</int> standalone-tag format.

    The intervention text is the content between this tag's closing </int>
    and the opening <int> of the next tag.

    Also handles embedded variant: <int>NAME (PARTY):.- long text here...</int>
    where both speaker and text are inside the tag.

    Returns (rows_without_session_fields, filtered_short, untagged_blocks).
    """
    tag_matches = list(_STANDALONE_RE.finditer(tagged_text))

    rows = []
    filtered_short = 0
    empty_speakers = 0  # speakers with no text (proxy for "untagged" quality signal)

    for i, m in enumerate(tag_matches):
        tag_content = m.group(1).strip()

        # Text between this tag's end and the start of the next tag
        next_start = tag_matches[i + 1].start() if i + 1 < len(tag_matches) else len(tagged_text)
        following_text = tagged_text[m.end():next_start].strip()

        # Resolve speaker and text
        speaker_raw, embedded_text = _split_embedded(tag_content)

        # Validate and clean the speaker name; also extract party code
        speaker_clean, party_raw = _clean_speaker(speaker_raw)
        if speaker_clean is None:
            filtered_short += 1
            continue

        if embedded_text:
            # Text was embedded inside the tag; append any following text too
            full_text = (embedded_text + " " + following_text).strip() if following_text else embedded_text
        else:
            full_text = following_text

        if len(full_text) < min_chars:
            filtered_short += 1
            if not full_text:
                empty_speakers += 1
            continue

        full_text, _pags = quitar_marca_pagina(full_text)
        rows.append({"speaker_raw": speaker_clean, "party_raw": party_raw or "",
                     "text": full_text})

    # "Untagged" for standalone = speakers with zero following text
    # (preamble before first tag is intentionally ignored — it's session header)
    untagged_blocks = empty_speakers

    return rows, filtered_short, untagged_blocks


# ── Main parse function ───────────────────────────────────────────────────────

def parse_interventions(
    tagged_text: str,
    meta: dict,
    output_path: Path,
    min_chars: int = 10,
    separator: str = ";",
    fmt: str = "auto",
    keep_untagged: bool = False,
) -> dict:
    """Parse tagged text and append rows to CSV.

    Parameters
    ----------
    fmt : "auto" | "inline" | "standalone"
    """
    resolved_fmt = detect_format(tagged_text) if fmt == "auto" else fmt

    if resolved_fmt == "standalone":
        rows_partial, filtered_short, untagged_blocks = _parse_standalone(tagged_text, min_chars)
    else:
        rows_partial, filtered_short, untagged_blocks = _parse_inline(tagged_text, min_chars, keep_untagged)

    # Session-level fields from meta
    session_fields = {
        # `session_id` sale del meta, que es quien conoce la identidad de la sesión.
        "session_id":     meta.get("session_id", ""),
        "legislature":    meta.get("legislature", ""),
        "session_number": meta.get("session_number", ""),
        "session_type":   meta.get("session_type", ""),
        "date":           meta.get("date", ""),
        "president":      meta.get("president", ""),
    }

    rows = [{**session_fields, **r} for r in rows_partial]

    # Append to CSV (write header only on first write)
    file_exists = output_path.exists() and output_path.stat().st_size > 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if file_exists else "w"

    with output_path.open(mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=_FIELDNAMES,
            delimiter=separator,
            quoting=csv.QUOTE_MINIMAL,
        )
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)

    return {
        "format_used":        resolved_fmt,
        "interventions_added": len(rows),
        "filtered_short":     filtered_short,
        "untagged_blocks":    untagged_blocks,
        "output_path":        str(output_path),
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Parse <int> blocks to CSV")
    parser.add_argument("--input",     required=True, help="Tagged text file")
    parser.add_argument("--meta",      required=True, help="Session metadata JSON file")
    parser.add_argument("--output",    required=True, help="Output CSV path")
    parser.add_argument("--min-chars", type=int, default=10, dest="min_chars",
                        help="Minimum chars for an intervention (default: 10)")
    parser.add_argument("--separator", default=";", help="CSV separator (default: ;)")
    parser.add_argument("--keep-untagged", action="store_true", dest="keep_untagged",
                        help="los huecos fuera de <int> entran como filas SIN orador (nada se borra)")
    parser.add_argument("--format",    default="auto", dest="fmt",
                        choices=["auto", "inline", "standalone"],
                        help="Tag format: auto (default), inline, or standalone")
    args = parser.parse_args()

    input_path  = Path(args.input)
    meta_path   = Path(args.meta)
    output_path = Path(args.output)

    if not input_path.exists():
        print(json.dumps({"status": "error", "error": f"Not found: {input_path}"}))
        sys.exit(1)
    if not meta_path.exists():
        print(json.dumps({"status": "error", "error": f"Meta not found: {meta_path}"}))
        sys.exit(1)

    with meta_path.open("r", encoding="utf-8") as f:
        meta = json.load(f)

    tagged_text = input_path.read_text(encoding="utf-8")
    stats = parse_interventions(tagged_text, meta, output_path, args.min_chars, args.separator, args.fmt,
                                keep_untagged=args.keep_untagged)
    stats["status"] = "ok"
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
