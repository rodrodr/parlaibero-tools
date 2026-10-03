#!/usr/bin/env python3
"""
Rebuild PY matrix from TXT_SPEAKER files (standalone format).

Steps:
  1. Map TXT_SPEAKER filenames → session_ids
  2. For multi-file sessions: concatenate A/B parts; prefer OCR over PDF
  3. Generate meta JSONs (source/py/meta/)
  4. Run parse_interventions for each session (standalone format)
  5. Accumulate into source/py/matrix/interventions_raw.csv
  6. Update pipeline_state.json

Usage:
  python rebuild_matrix_py.py [--dry-run] [--session SESSION_ID]

⚠ POR QUÉ ES ESPECÍFICO DE ESTE PAÍS (revisado 2026-08-02)
Reconstruye la matriz de PY desde ficheros sueltos. Lo específico es el formato; lo reutilizable es el criterio de ENSAMBLADO: una sesión puede venir partida en varios archivos (partes A/B/C) y con varias procedencias del mismo trozo, y hay que unirlas en orden de parte prefiriendo la mejor fuente (OCR sobre PDF). Aparece también en GT (2 fases), CL (doble vía XML+PDF) y CR.
"""

import re
import json
import argparse
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from datetime import date as Date

BASE_DIR = Path.cwd()
TAGGED_DIR = BASE_DIR / "source/py/tagged/TXT_SPEAKER"
META_DIR   = BASE_DIR / "source/py/meta"
MATRIX_CSV = BASE_DIR / "source/py/matrix/interventions_raw.csv"
STATE_PATH = BASE_DIR / "state/py/pipeline_state.json"
PARSE_SCRIPT = BASE_DIR / "lib/utils/parse_interventions.py"
UPDATE_SCRIPT = BASE_DIR / "lib/utils/update_state.py"

SEPARATOR = ";"
MIN_CHARS  = 10

# ── Legislature ranges ────────────────────────────────────────────────────────

LEGISLATURES = [
    ("1989-1993", Date(1989, 4,  1), Date(1993, 6, 30)),
    ("1993-1998", Date(1993, 7,  1), Date(1998, 6, 30)),
    ("1998-2003", Date(1998, 7,  1), Date(2003, 6, 30)),
    ("2003-2008", Date(2003, 7,  1), Date(2008, 6, 30)),
    ("2008-2013", Date(2008, 7,  1), Date(2013, 6, 30)),
    ("2013-2018", Date(2013, 7,  1), Date(2018, 6, 30)),
    ("2018-2023", Date(2018, 7,  1), Date(2023, 6, 30)),
    ("2023-2028", Date(2023, 7,  1), Date(2028, 6, 30)),
]

TYPE_MAP = {"O": "SO", "E": "SE", "P": "SP", "S": "SP", "C": "SP"}

# Hard-coded corrections for filenames with OCR errors in the year field.
# Maps the bogus parsed session_id → (real_session_id, real_date_iso, real_type_code).
_SESSION_ID_CORRECTIONS: dict[str, tuple[str, str, str]] = {
    # DS-HCD-8-10-10098-OCR.txt: year parsed as "10098" (→1009), real year 1998, real day 6 (from content)
    "1009-10-08_SO": ("1998-10-06_SO", "1998-10-06", "SO"),
    # DS-HCD-18-07-1195-OCR.txt: year parsed as "1195" (→1195), real year 1995, real type SE (from content)
    "1195-07-18_SO": ("1995-07-18_SE", "1995-07-18", "SE"),
}

SESSION_TYPE_LABELS = {
    "SO": "ordinaria",
    "SE": "extraordinaria",
    "SP": "especial",
}


def infer_legislature(session_date: Date) -> str:
    for label, start, end in LEGISLATURES:
        if start <= session_date <= end:
            return label
    return ""


def parse_session_id(session_id: str) -> tuple[Date | None, str, str]:
    """Return (date, session_type_code, sub_suffix) from session_id like 1993-06-30_SO or 2018-08-01_SE_01."""
    m = re.match(r'^(\d{4}-\d{2}-\d{2})_([A-Z]+)(?:_(\w+))?$', session_id)
    if not m:
        return None, "SO", ""
    try:
        d = Date.fromisoformat(m.group(1))
    except ValueError:
        return None, "SO", ""
    return d, m.group(2), m.group(3) or ""


def parse_old_filename(name: str) -> tuple[str | None, str, str | None, str]:
    """Parse DS-*-HCD-DD-MM-YYYY-OCR/PDF.txt → (date_str, session_type, part_suffix, variant)."""
    stem = re.sub(r'-(OCR|PDF)$', '', name)
    variant = "OCR" if "OCR" in name else ("PDF" if "PDF" in name else "UNK")

    type_match = re.search(r'DS\s*-?\s*([OEPSC])\s*-?\s*HCD', stem, re.IGNORECASE)
    stype = TYPE_MAP.get(type_match.group(1).upper(), "SO") if type_match else "SO"

    year_match = re.search(r'(\d{4})', stem)
    if not year_match:
        return None, stype, None, variant
    year = year_match.group(1)

    before_year = stem[: year_match.start()]
    # Part suffix: letter (A, B, C) or digit (2, 3) between separators before the date
    part_match = re.search(r'-([A-Ca-c2-9])-', before_year)
    part_suffix = part_match.group(1).upper() if part_match else None

    nums = re.findall(r'\d{1,2}', before_year)
    valid_pairs = [
        (nums[i], nums[i + 1])
        for i in range(len(nums) - 1)
        if 1 <= int(nums[i]) <= 31 and 1 <= int(nums[i + 1]) <= 12
    ]
    if not valid_pairs:
        return None, stype, part_suffix, variant

    day, month = valid_pairs[-1]
    try:
        date_str = f"{year}-{int(month):02d}-{int(day):02d}"
    except Exception:
        return None, stype, part_suffix, variant

    return date_str, stype, part_suffix, variant


def build_file_map() -> dict[str, list[tuple[Path, str, str | None]]]:
    """Returns {session_id: [(path, variant, part_suffix), ...]}"""
    session_to_files: dict[str, list] = defaultdict(list)

    for f in sorted(TAGGED_DIR.rglob("*.txt")):
        name = f.name
        new_match = re.match(r'^(\d{4}-\d{2}-\d{2}_\w+)\.txt$', name)
        if new_match:
            session_to_files[new_match.group(1)].append((f, "NEW", None))
            continue
        if "HCD" in name or "HCR" in name:
            date_str, stype, part, variant = parse_old_filename(name)
            if date_str:
                session_id = f"{date_str}_{stype}"
                session_to_files[session_id].append((f, variant, part))
    return session_to_files


def best_file(candidates: list[tuple[Path, str, str | None]]) -> list[Path]:
    """
    Return ordered list of paths to read (and concatenate).
    - OCR preferred over PDF
    - A/B/C parts concatenated in order
    - Plain + A/B: return plain first, then B (B = second part of session)
    """
    if len(candidates) == 1:
        return [candidates[0][0]]

    # Separate by part suffix
    parts: dict[str | None, list[tuple[Path, str]]] = defaultdict(list)
    for path, variant, part in candidates:
        parts[part].append((path, variant))

    # Build ordered part list: None (plain) first, then A, B, C, 2, 3 …
    def part_sort(p):
        if p is None: return 0
        if p.isdigit(): return int(p)
        return ord(p) - ord('A') + 1

    ordered_parts = sorted(parts.keys(), key=part_sort)
    result = []
    for part_key in ordered_parts:
        # Within each part, prefer OCR over PDF
        candidates_for_part = parts[part_key]
        ocr = [p for p, v in candidates_for_part if v == "OCR"]
        if ocr:
            result.append(ocr[0])
        else:
            result.append(candidates_for_part[0][0])

    return result


def generate_meta(session_id: str, session_date: Date, session_type_code: str) -> dict:
    legislature = infer_legislature(session_date)
    session_type_label = SESSION_TYPE_LABELS.get(session_type_code, "ordinaria")
    return {
        "session_id": session_id,
        "date": session_date.isoformat(),
        "session_number": "",
        "session_type": session_type_label,
        "legislature": legislature,
        "president": "",
    }


def load_state() -> dict:
    with open(STATE_PATH) as f:
        return json.load(f)


def update_state_entry(session_id: str, status: str, confidence: float, error: str = "") -> None:
    cmd = [
        sys.executable, str(UPDATE_SCRIPT),
        "--country", "py",
        "--skill", "diaries-matrix",
        "--session", session_id,
        "--status", status,
        "--confidence", str(confidence),
        "--output", str(MATRIX_CSV),
    ]
    if error:
        cmd += ["--error", error]
    subprocess.run(cmd, check=True, capture_output=True)


def process_session(session_id: str, files: list[Path], dry_run: bool) -> dict:
    """
    Returns {"status": "complete"|"flag"|"halt", "confidence": float, "error": str,
             "effective_session_id": str}
    """
    # Apply hard-coded corrections for sessions with OCR errors in the year
    correction = _SESSION_ID_CORRECTIONS.get(session_id)
    if correction:
        effective_id, date_iso, stype_code = correction
        try:
            session_date = Date.fromisoformat(date_iso)
        except ValueError:
            return {"status": "halt", "confidence": 0.0, "error": f"Bad correction date for {session_id}"}
    else:
        effective_id = session_id
        session_date, stype_code, _ = parse_session_id(session_id)
        if session_date is None:
            return {"status": "halt", "confidence": 0.0, "error": f"Cannot parse date from {session_id}"}

    # Write meta JSON using the corrected session identity
    meta = generate_meta(effective_id, session_date, stype_code)
    meta_path = META_DIR / f"{effective_id}.json"
    if not dry_run:
        META_DIR.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # Concatenate file contents
    texts = []
    for fp in files:
        try:
            texts.append(fp.read_text(encoding="utf-8", errors="replace"))
        except Exception as e:
            return {"status": "halt", "confidence": 0.0, "error": f"Read error {fp.name}: {e}"}

    combined_text = "\n\n".join(texts)

    # Pre-processing: repair tags where </int> was placed before the full speaker label.
    # In standalone format, labels always end with ':'.  When OCR breaks a name across lines
    # the tagger may close the tag mid-name, leaving "REST_OF_NAME:" on the next line.
    # We detect this and extend the tag to include the continuation.
    def _repair_broken_tags(text: str) -> str:
        def _do_repair(rm: re.Match) -> str:
            tag_body   = rm.group(1)
            blank_line = rm.group(2)   # non-empty if a blank line separated tag from continuation
            noise_sep  = rm.group(3)   # leading noise chars (, ' " – etc.)
            cont       = rm.group(4)   # continuation ending with ':'
            cont_clean = re.sub(r"^[\s,\"'\-–—_|`~¿!'']+", '', cont).rstrip(':').rstrip()
            if not cont_clean:
                return rm.group(0)
            # Extra guard: blank line present → only accept when explicit noise introduces
            # the continuation (prevents joining unrelated uppercase speakers across blank lines)
            if blank_line and not noise_sep.strip() and not re.match(r"^[,\"'\-–—_|`~¿!''¡]", cont):
                return rm.group(0)
            # Guard: uppercase-starting continuation must look like a name (≥60% uppercase)
            if cont_clean[0].isupper():
                alpha = [c for c in cont_clean if c.isalpha()]
                if alpha and sum(1 for c in alpha if c.isupper()) / len(alpha) < 0.60:
                    return rm.group(0)
            tag_clean = tag_body.strip()
            # Mid-word split (lowercase/digit start) → concat without space
            if cont_clean[0].islower() or cont_clean[0].isdigit():
                joined = tag_clean + cont_clean
            else:
                joined = (tag_clean + ' ' + cont_clean).strip()
            return f'<int>{joined}:</int>'

        return re.sub(
            r'<int>'
            r'((?:SEÑOR[A]?\s+)?DIPUTAD[OA]\s+[^<:\n]{3,50}?)'
            r'</int>'
            r'[ \t]*\n([ \t]*\n)?[ \t]*'   # 1–2 newlines; group 2 = blank-line flag
            r"([,\"'\-–—_|`~¿!'']*)"       # optional noise prefix (group 3)
            r'([^<\n:]{1,35}:)',            # continuation ≤35 chars + ':' (group 4)
            _do_repair,
            text,
            flags=re.IGNORECASE,
        )

    combined_text = _repair_broken_tags(combined_text)

    # Normalize <int> tag content to reduce spurious speaker_raw variants:
    # 1. Collapse OCR line-breaks:    "NOMBRE\nAPELLIDO"       → "NOMBRE APELLIDO"
    # 2. Strip leading dashes/spaces: "- SEÑOR DIPUTADO NAME"  → "SEÑOR DIPUTADO NAME"
    # 3. Uppercase mixed-case señor:  "Señor DIPUTADO NAME"    → "SEÑOR DIPUTADO NAME"
    # 4. Discard tag fusions: if a second speaker label appears after a name, truncate there.
    #    e.g. "DIPUTADO SILVIO GUSTAVO SEÑOR PRESIDENTE" → keep up to the second label
    _SECOND_SPEAKER_RE = re.compile(
        r'\s+(?:SEÑOR\s+PRESIDENTE|SEÑORA\s+PRESIDENTA|SECRETARIO|'
        r'(?:SEÑOR\s+)?DIPUTAD[OA]\s+[-\w])',
        re.IGNORECASE,
    )

    def _normalize_tag(m: re.Match) -> str:
        content = m.group(1).strip()
        # Strip trailing single-letter lines (roll-call / attendance codes like P, A, V, E, S, N)
        # that appear as their own line in the original OCR.  Must run BEFORE newline collapse.
        content = re.sub(r'(?:\n\s*[A-Z]\s*)+$', '', content).strip()
        # Collapse OCR line-breaks within the name
        content = re.sub(r'\s*\n\s*', ' ', content).strip()
        # Strip leading dashes/spaces
        content = re.sub(r'^[-–—\s]+', '', content).strip()
        # Uppercase first char if lowercase
        if content and content[0].islower():
            content = content[0].upper() + content[1:]
        # Normalize mixed-case "Señor/Señora" prefix
        content = re.sub(r'\b[Ss]eñor([ao]?)\b', lambda x: 'SEÑOR' + x.group(1).upper(), content)
        # Collapse multiple consecutive spaces into one
        content = re.sub(r'  +', ' ', content).strip()
        # Truncate at second speaker label (tag fusion artifact).
        # Minimum start position 20 to ensure a full prefix + name precede it,
        # avoiding false positives like "SEÑORA DIPUTADA NAME" where DIPUTADA is at pos 7.
        fusion = _SECOND_SPEAKER_RE.search(content)
        if fusion and fusion.start() >= 20:
            content = content[:fusion.start()].strip()
        return f"<int>{content}</int>"

    combined_text = re.sub(r'<int>(.*?)</int>', _normalize_tag, combined_text, flags=re.DOTALL)

    if dry_run:
        int_count = len(re.findall(r'<int>', combined_text))
        return {"status": "dry-run", "confidence": 1.0, "error": "", "ints": int_count,
                "effective_session_id": effective_id}

    # Write combined text to temp file
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', encoding='utf-8',
                                     delete=False) as tmp:
        tmp.write(combined_text)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [
                sys.executable, str(PARSE_SCRIPT),
                "--input", tmp_path,
                "--meta", str(meta_path),
                "--output", str(MATRIX_CSV),
                "--min-chars", str(MIN_CHARS),
                "--separator", SEPARATOR,
                "--format", "standalone",
            ],
            capture_output=True, text=True, timeout=60,
        )
    finally:
        os.unlink(tmp_path)

    if result.returncode != 0:
        err = result.stderr.strip() or result.stdout.strip()
        return {"status": "halt", "confidence": 0.0, "error": err[:200]}

    try:
        stats = json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        return {"status": "halt", "confidence": 0.0, "error": f"Bad JSON: {result.stdout[:100]}"}

    added  = stats.get("interventions_added", 0)
    untag  = stats.get("untagged_blocks", 0)
    confidence = 1.0 - (untag / max(added + untag, 1))

    if confidence >= 0.80:
        status = "complete"
    elif confidence >= 0.65:
        status = "flag"
    else:
        status = "flag"  # still flag, not halt — data is probably there

    return {
        "status": status,
        "confidence": round(confidence, 4),
        "error": "",
        "stats": stats,
        "effective_session_id": effective_id,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--session", default=None, help="Process only this session_id")
    args = parser.parse_args()

    file_map = build_file_map()
    state    = load_state()
    state_sessions = [s for s in state["sessions"] if s != "_country"]

    if args.session:
        sessions_to_process = [args.session] if args.session in state["sessions"] else []
        if not sessions_to_process:
            print(f"Session {args.session} not in state.", file=sys.stderr)
            sys.exit(1)
    else:
        sessions_to_process = sorted(state_sessions)

    # Reset output CSV if not dry-run and not single-session
    if not args.dry_run and not args.session:
        MATRIX_CSV.parent.mkdir(parents=True, exist_ok=True)
        if MATRIX_CSV.exists():
            MATRIX_CSV.unlink()
        print(f"Cleared {MATRIX_CSV}")

    n_total = len(sessions_to_process)
    n_complete = n_flag = n_halt = n_no_file = 0
    results = []

    for i, session_id in enumerate(sessions_to_process, 1):
        if session_id not in file_map:
            print(f"[{i}/{n_total}] {session_id}: NO FILE — skipping")
            n_no_file += 1
            if not args.dry_run:
                update_state_entry(session_id, "halt", 0.0, "No TXT_SPEAKER file found")
            continue

        files = best_file(file_map[session_id])
        r = process_session(session_id, files, args.dry_run)

        status       = r["status"]
        conf         = r.get("confidence", 0.0)
        ints         = r.get("stats", {}).get("interventions_added", r.get("ints", "?"))
        err          = r.get("error", "")
        effective_id = r.get("effective_session_id", session_id)

        correction_note = f" → {effective_id}" if effective_id != session_id else ""
        icon = "✓" if status == "complete" else ("⚑" if status == "flag" else "✗")
        print(f"[{i}/{n_total}] {session_id}{correction_note}: {icon} {status} conf={conf:.2f} ints={ints} {err[:60] if err else ''}")

        if status == "complete":
            n_complete += 1
        elif status == "flag":
            n_flag += 1
        elif status == "halt":
            n_halt += 1

        if not args.dry_run and status != "dry-run":
            # Update state under the effective (corrected) session_id
            update_state_entry(effective_id, status, conf, err)

        results.append((session_id, status, conf))

    print()
    print("═" * 60)
    print(f"diaries-matrix — PY rebuild")
    print(f"  Procesadas:  {n_total}")
    print(f"  Completas:   {n_complete}")
    print(f"  FLAG:        {n_flag}")
    print(f"  HALT:        {n_halt}")
    print(f"  Sin archivo: {n_no_file}")
    if not args.dry_run and MATRIX_CSV.exists():
        rows = sum(1 for _ in MATRIX_CSV.open(encoding="utf-8")) - 1
        print(f"  Total filas: {rows:,}")
        print(f"  Salida:      {MATRIX_CSV}")
    print("═" * 60)


if __name__ == "__main__":
    main()
