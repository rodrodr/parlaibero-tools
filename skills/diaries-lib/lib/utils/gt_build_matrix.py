#!/usr/bin/env python3
"""
gt_build_matrix.py — Build interventions_raw.csv for Guatemala from PDF diaries.

Python rewrite of GTM_Rodrigo.R with 4 bug fixes:
  1. "SO" session prefix → "ordinaria" (R had "Extraordinaria")
  2. speech_order is cumulative per session, not reset per PDF file
  3. session_number preserved as string (R's as.numeric() silently destroyed strings)
  4. 2020-02-25 session assigned to legislature "IX" via date-range logic (R had "VIII")

Invoked by Claude during the GT pipeline as:
    python lib/utils/gt_build_matrix.py \\
        --pdf_dir  source/gt/raw \\
        --deputies source/gt/deputies/Diputados_GUATEMALA.xlsx \\
        --output   source/gt/matrix/interventions_raw.csv

Output columns (match GTM_diarios.csv schema):
    legislature, date, time_beg, number, speech_order,
    session_type, nm_speaker, party, district, role, text, nwords

⚠ POR QUÉ ES ESPECÍFICO DE ESTE PAÍS (revisado 2026-08-02)
GT se ingirió fuera del pipeline: este script construye la matriz directamente desde los PDF, con el layout de esa cámara. NO es generalizable —el pipeline normal es ocr→extract→correct→tag→matrix— pero sus cuatro correcciones SÍ dejaron reglas generales: el tipo de sesión sale del prefijo (`session_type_by_prefix`), `session_number` se conserva como CADENA (hay números alfanuméricos: 12A, 001O), la legislatura se decide por rango de fechas, y sobre todo: **`intervention_order` es acumulativo por SESIÓN, no por archivo** —una sesión repartida en varios PDF no reinicia el contador—.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

import pandas as pd

# Ensure sibling utils are importable regardless of working directory
sys.path.insert(0, str(Path(__file__).parent))
from gt_name_corrections import correct_nm_fuse, normalize_speaker, to_ascii_upper


# ── Legislature date ranges ───────────────────────────────────────────────────

_LEGISLATURES = [
    ("X",    date(2024, 1, 14), date(2028, 1, 14)),
    ("IX",   date(2020, 1, 14), date(2024, 1, 14)),
    ("VIII", date(2016, 1, 14), date(2020, 1, 14)),
    ("VII",  date(2012, 1, 14), date(2016, 1, 14)),
    ("VI",   date(2008, 1, 14), date(2012, 1, 14)),
    ("V",    date(2004, 1, 14), date(2008, 1, 14)),
    ("IV",   date(2000, 1, 14), date(2004, 1, 14)),
]


def _assign_legislature(d: date) -> str:
    for leg, start, end in _LEGISLATURES:
        if start <= d < end:
            return leg
    return ""


# ── Session type from filename prefix ────────────────────────────────────────
# BUG FIX #1: R script mapped "SO" → "Extraordinaria"; correct is "ordinaria".

def _session_type_from_prefix(prefix: str) -> str | None:
    p = prefix.upper()
    if p == "SE":
        return "extraordinaria"
    if p == "SO":
        return "ordinaria"   # was "Extraordinaria" in R script
    if p == "SS":
        return "solemne"
    return None


# ── Filename parsing ───────────────────────────────────────────────────────────

_DATE_PATTERNS = [
    (re.compile(r'\b(\d{4})-(\d{2})-(\d{2})\b'), 'ymd'),   # YYYY-MM-DD
    (re.compile(r'\b(\d{2})-(\d{2})-(\d{4})\b'), 'dmy'),   # DD-MM-YYYY
    (re.compile(r'\b(\d{2})-(\d{2})-(\d{2})\b'), 'dmy2'),  # DD-MM-YY
]


def _parse_date_from_string(s: str) -> date | None:
    for pat, fmt in _DATE_PATTERNS:
        m = pat.search(s)
        if m:
            try:
                if fmt == 'ymd':
                    return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                elif fmt in ('dmy', 'dmy2'):
                    day, month = int(m.group(1)), int(m.group(2))
                    year = int(m.group(3))
                    if fmt == 'dmy2':
                        year += 2000 if year < 50 else 1900
                    return date(year, month, day)
            except ValueError:
                continue
    return None


def _parse_filename(filename: str) -> tuple[str | None, str | None, date | None]:
    """
    Parse GT diary filename → (session_type, session_number, session_date).

    Expected format: {TYPE}_{NUMBER}_{DATE}[_extra...].pdf
    Falls back to searching the whole stem for a recognizable date.
    """
    stem = Path(filename).stem
    parts = stem.split('_')

    session_type = None
    number = None
    session_date = None

    if len(parts) >= 3:
        session_type = _session_type_from_prefix(parts[0])
        number = parts[1]
        session_date = _parse_date_from_string(parts[2])

    # Fallback: search entire stem for date
    if session_date is None:
        session_date = _parse_date_from_string(stem)

    return session_type, number, session_date


# ── Text pre-processing ───────────────────────────────────────────────────────
# Equivalent to R lines 137–169 (fixed-string and regex replacements before
# speaker detection).

_FIXED_REPLACEMENTS: list[tuple[str, str]] = [
    (
        "EL R. ÁLVAREZ MORALES Y LA R. MONTENEGRO COTTOM",
        "EL R. ÁLVAREZ MORALES y la R. MONTENEGRO COTTOM",
    ),
    ("BERGANZA BOJORQUEZ, FERDY LEONEL...", "BERGANZA BOJORQUEZ, FERDY LEONEL: ..."),
    (" CONSIDERANDO:", " considerando:"),
    ("BALDIZON MENDEZ, MANUEL...", "BALDIZON MENDEZ, MANUEL: ..."),
    ("MENDEZ...", "MENDEZ: ..."),
    ("SANDOVAL...", "SANDOVAL: ..."),
    ("SALAZAR...", "SALAZAR: ..."),
    ("TORREBIARTE...", "TORREBIARTE: ..."),
    ("SINIBALDI APARICIO...", "SINIBALDI APARICIO: ..."),
]

_REGEX_REPLACEMENTS: list[tuple[str, str]] = [
    (
        r"EL R\. GARCÍA RODAS INDICA QUE TERMINÓ LAS PREGUNTAS ADICIONALES, DICIENDO",
        "EL R. GARCÍA RODAS indica que terminó las preguntas adicionales, DICIENDO",
    ),
    (
        r"EL DIPUTADO JULIO CÉSAR IXCAMEY VELÁSQUEZ, INTEGRANTE DE LA",
        "EL DIPUTADO Julio César Ixcamey Velásquez, INTEGRANTE DE LA",
    ),
    (
        r"EL R\. MANUEL ANTONIO BALDIZON MENDEZ SOLICITA LA PALABRA",
        "EL R. Manuel Antonio Baldizon Mendez SOLICITA LA PALABRA",
    ),
    (r" VOTÓ A FAVOR\.", " Votó a favor."),
    (r", SE ESPERA EL VOTO\.", ", Se espera el voto."),
]


def _preprocess_text(tx: str) -> str:
    # Collapse runs of non-newline whitespace
    tx = re.sub(r'[^\S\n]+', ' ', tx)

    for old, new in _FIXED_REPLACEMENTS:
        tx = tx.replace(old, new)

    tx = tx.replace(
        "LA DIPUTADA EN LA RELACION COMERCIAL:\n",
        "  LA DIPUTADA EN LA relación comercial:",
    )

    for pattern, repl in _REGEX_REPLACEMENTS:
        tx = re.sub(pattern, repl, tx)

    return tx


# ── Speaker extraction ────────────────────────────────────────────────────────
# Equivalent to R patron_interviniente (line 233).

_SPEAKER_RE = re.compile(
    r'(?:(?:EL|LA)\s+(?:(?:VICE)?PRESIDENT[AE]|MINISTR[AO]|SECRETARI[AO]'
    r'|DIPUTAD[AO]|SE[ÑN]OR[A]?|R\.))\s+'
    r'[A-ZÁÉÍÓÚÜÑ.,\-][A-ZÁÉÍÓÚÜÑ.,\-\s]*:',
    re.UNICODE,
)

_BUREAU_RE = re.compile(r'PRESIDENT[EA]|SECRETARI[OA]', re.IGNORECASE)


# ── PDF text extraction ───────────────────────────────────────────────────────

def _extract_pdf_text(pdf_path: Path) -> str:
    """
    Extract text from all pages, concatenated with double newlines.
    Equivalent to R: pdf_text(lf[i]) |> paste(collapse="\n\n")
    """
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            pages = [p.extract_text() or '' for p in pdf.pages]
        return '\n\n'.join(pages)
    except ImportError:
        pass

    try:
        import pypdf
        reader = pypdf.PdfReader(str(pdf_path))
        pages = [p.extract_text() or '' for p in reader.pages]
        return '\n\n'.join(pages)
    except ImportError:
        pass

    raise RuntimeError(
        "No PDF library found. Install pdfplumber: pip install pdfplumber"
    )


# ── Single-PDF processor ──────────────────────────────────────────────────────

def _process_pdf(pdf_path: Path) -> list[dict]:
    """Extract intervention rows from a single PDF."""
    filename = pdf_path.name
    session_type, number, session_date = _parse_filename(filename)

    if session_date is None:
        print(f"WARN: cannot parse date from {filename} — skipping", file=sys.stderr)
        return []

    tx = _extract_pdf_text(pdf_path)
    if not tx.strip():
        return []

    tx = _preprocess_text(tx)

    # Start time
    m = re.search(r'\(Las (\d{1,2}:\d{2}) horas\)', tx)
    time_beg = m.group(1) if m else None

    # Speaker positions
    speaker_matches = list(_SPEAKER_RE.finditer(tx))
    if not speaker_matches:
        return []

    rows: list[dict] = []
    for i, sm in enumerate(speaker_matches):
        speaker_raw = tx[sm.start():sm.end()].strip()
        text_start = sm.end()
        text_end = speaker_matches[i + 1].start() if i + 1 < len(speaker_matches) else len(tx)
        text = re.sub(r'\s+', ' ', tx[text_start:text_end].strip())

        if not text:
            continue

        rows.append({
            'filename': filename,
            'date': session_date,
            'number': number,               # string — BUG FIX #3
            'session_type': session_type,
            'time_beg': time_beg,
            'speaker_raw': speaker_raw,
            'nwords': len(text.split()),
            'text': text,
            'is_bureau': bool(_BUREAU_RE.search(speaker_raw)),
            '_file_order': i,               # position within file
        })

    return rows


# ── Role classification ───────────────────────────────────────────────────────

_GOV_RE = re.compile(
    r'MINISTR[OA]|PRESIDENT[EA]\s+CONSTITUCIONAL|SECRETARIO\s+GENERAL'
    r'|SECRETARIO\s+DE\s|VICEPRESIDENTE\s+DE\s+LA\s+REPUBLICA',
    re.IGNORECASE,
)
_JUD_RE = re.compile(
    r'CORTE|PROCURADOR|MAGISTRAD[OA]|JUDICIAL|FISCAL\s+GENERAL',
    re.IGNORECASE,
)


def _classify_role(speaker_raw: str, has_party: bool, is_bureau: bool) -> str:
    if has_party:
        return "Bureau" if is_bureau else "Representative"
    if _GOV_RE.search(speaker_raw):
        return "Government"
    if _JUD_RE.search(speaker_raw):
        return "Judiciary"
    return "Other"


# ── Main pipeline ─────────────────────────────────────────────────────────────

def build_matrix(
    pdf_dir: Path,
    deputies_file: Path,
    output_file: Path,
) -> None:
    # 1. Collect PDFs
    pdfs = sorted(pdf_dir.rglob('*.pdf')) + sorted(pdf_dir.rglob('*.PDF'))
    print(f"PDFs found: {len(pdfs)}", file=sys.stderr)
    if not pdfs:
        print("ERROR: no PDF files found in", pdf_dir, file=sys.stderr)
        sys.exit(1)

    # 2. Extract all interventions
    all_rows: list[dict] = []
    for idx, pdf_path in enumerate(pdfs, 1):
        if idx % 100 == 0:
            print(f"  {idx}/{len(pdfs)}: {pdf_path.name}", file=sys.stderr)
        all_rows.extend(_process_pdf(pdf_path))

    print(f"Raw interventions extracted: {len(all_rows)}", file=sys.stderr)

    # 3. Build DataFrame and sort deterministically before numbering
    df = pd.DataFrame(all_rows)
    df['_date_str'] = df['date'].astype(str)
    df = df.sort_values(['_date_str', 'number', 'filename', '_file_order']).reset_index(drop=True)

    # 4. Assign cumulative speech_order per session — BUG FIX #2
    # R script did 1:nrow(dt) per PDF; we number globally within each (date, number) group.
    df['speech_order'] = (
        df.groupby(['_date_str', 'number']).cumcount() + 1
    )

    # 5. Assign legislature from date — BUG FIX #4 (date-range handles 2020-02-25 → IX)
    df['legislature'] = df['date'].apply(_assign_legislature)

    # 6. Normalize speaker → nm_fuse
    print("Normalizing speaker names...", file=sys.stderr)
    df['nm_fuse'] = df['speaker_raw'].apply(normalize_speaker)

    # 7. Apply corrections (simple + conditional)
    df['nm_fuse'] = df.apply(
        lambda r: correct_nm_fuse(
            r['nm_fuse'],
            speaker_raw=r['speaker_raw'],
            legislature=r['legislature'],
            d=r['date'],
            filename=r['filename'],
        ),
        axis=1,
    )

    # 8. Load deputies (supports both .xlsx and .csv)
    print("Loading deputies...", file=sys.stderr)
    if deputies_file.suffix.lower() == '.csv':
        di = pd.read_csv(deputies_file, usecols=[
            'apellidos', 'nombre_completo', 'partido', 'circunscripcion', 'notas'
        ])
        # notas holds comma-separated legislatures (e.g. "V" or "VII,VIII,IX")
        di = di.assign(legislature=di['notas'].str.split(',')).explode('legislature')
        di['legislature'] = di['legislature'].str.strip()
        di = di.rename(columns={
            'nombre_completo': 'nm_speaker',
            'apellidos':       'nm_fuse',
            'partido':         'party',
            'circunscripcion': 'district_dep',
        })[['legislature', 'nm_speaker', 'nm_fuse', 'party', 'district_dep']]
    else:
        di = pd.read_excel(deputies_file, usecols=[
            'legislatura', 'diputado', 'apellidos', 'partido_postulante', 'distrito'
        ])
        di.columns = ['legislature', 'nm_speaker', 'nm_fuse', 'party', 'district_dep']
    di['nm_fuse'] = di['nm_fuse'].apply(
        lambda s: to_ascii_upper(str(s)).strip() if pd.notna(s) else ''
    )

    # 9. Merge on (legislature, nm_fuse)
    print("Merging with deputies...", file=sys.stderr)
    merged = df.merge(di, on=['legislature', 'nm_fuse'], how='left')

    # Filter pre-corpus rows (R line 713: rea <- rea[rea$date>"2000-05-01",])
    merged = merged[merged['date'] > date(2000, 5, 1)].copy()

    # 10. Resolve nm_speaker fallback
    merged['nm_speaker_final'] = merged['nm_speaker'].where(
        merged['nm_speaker'].notna(),
        merged['nm_fuse'].str.title(),
    )

    # Drop rows where nm_speaker is still NA (R line 760: dgt <- dgt[!is.na(dgt$nm_speaker),])
    merged = merged[merged['nm_speaker_final'].notna()].copy()

    # 11. Resolve district: prefer deputy file district, fall back to PDF district
    merged['district_final'] = merged['district_dep'].where(
        merged['district_dep'].notna(),
        merged.get('district'),
    )

    # 12. Classify roles
    merged['has_party'] = merged['party'].notna()
    merged['role'] = merged.apply(
        lambda r: _classify_role(r['speaker_raw'], r['has_party'], r['is_bureau']),
        axis=1,
    )

    # 13. Final sort and column selection
    merged = merged.sort_values(['_date_str', 'time_beg', 'number', 'speech_order'])

    out = merged[[
        'legislature', '_date_str', 'time_beg', 'number', 'speech_order',
        'session_type', 'nm_speaker_final', 'party', 'district_final',
        'role', 'text', 'nwords',
    ]].copy()
    out.columns = [
        'legislature', 'date', 'time_beg', 'number', 'speech_order',
        'session_type', 'nm_speaker', 'party', 'district',
        'role', 'text', 'nwords',
    ]

    # 14. Write
    output_file.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output_file, index=False, encoding='utf-8')
    print(f"\nWritten {len(out)} rows → {output_file}", file=sys.stderr)

    # Summary
    matched = out['party'].notna().sum()
    print(f"Matched to deputies: {matched} ({matched / len(out):.1%})", file=sys.stderr)
    for leg in ['IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X']:
        n = (out['legislature'] == leg).sum()
        if n:
            print(f"  Legislature {leg}: {n:,}", file=sys.stderr)


# ── CLI ───────────────────────────────────────────────────────────────────────

_BASE = Path.cwd()


def _main() -> None:
    p = argparse.ArgumentParser(description="Build GT interventions_raw.csv from PDFs")
    p.add_argument(
        '--pdf_dir', type=Path,
        default=_BASE / 'source/gt/raw',
        help='Directory containing PDF diary files (searched recursively)',
    )
    p.add_argument(
        '--deputies', type=Path,
        default=_BASE / 'source/gt/deputies/Diputados_GUATEMALA.xlsx',
        help='Deputies Excel file',
    )
    p.add_argument(
        '--output', type=Path,
        default=_BASE / 'source/gt/matrix/interventions_raw.csv',
        help='Output CSV path',
    )
    args = p.parse_args()

    if not args.pdf_dir.exists():
        print(f"ERROR: pdf_dir not found: {args.pdf_dir}", file=sys.stderr)
        sys.exit(1)
    if not args.deputies.exists():
        print(f"ERROR: deputies file not found: {args.deputies}", file=sys.stderr)
        sys.exit(1)

    build_matrix(args.pdf_dir, args.deputies, args.output)


if __name__ == '__main__':
    _main()
