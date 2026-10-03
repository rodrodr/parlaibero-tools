#!/usr/bin/env python3
"""parse_attendance.py — Extrae las listas nominales de asistencia de los diarios.

Los diarios parlamentarios suelen abrir con un pase de lista:

    Asisten los señores Representantes: <nombre>, <nombre>, ... y <nombre>.
    Con licencia: <nombre>, ...
    Faltan con aviso: <nombre>, ...
    Sin aviso: <nombre>.

Este pase de lista es la señal MÁS fuerte para desambiguar oradores: el conjunto
`presentes` es exactamente quién pudo hablar ese día. Las sub-secciones de
ausentes (`con licencia`, `faltan`, `sin aviso`) NO pudieron hablar → se usan
solo como pertenencia a la legislatura, no para constreñir oradores.

Salida (CSV a --output): session_id ; date ; status ; name_raw
  status ∈ {present, absent}

Uso:
  python parse_attendance.py --input source/uy/corrected --output source/uy/match/attendance.csv
  python parse_attendance.py --input source/uy/corrected/1992-10-07.txt --print
"""
import argparse, csv, os, re, sys, unicodedata
from concurrent.futures import ThreadPoolExecutor

# ── Anclas ────────────────────────────────────────────────────────────────────
# "Asisten los señores Representantes:" tolerando ruido OCR en "señores".
RE_START = re.compile(
    r"[Aa]sisten\s+l[oa]s?\s+\S+\s+[Rr]epresent\w*\s*:|"
    r"[Cc]oncurren\s+l[oa]s?\s+[^:\n]{0,40}:",
)
# Encabezados de sub-bloques de AUSENTES (todo lo que sigue a presentes).
RE_ABSENT_HDR = re.compile(
    r"(?:^|\n)\s*("
    r"[Cc]on\s+licencias?|[Ff]altan?\s+con\s+licencia|"
    r"[Ff]altan?\s+con\s+aviso|[Ff]altan?\s+sin\s+aviso|"
    r"[Cc]on\s+aviso|[Ss]in\s+aviso"
    r")\s*:",
)
# Terminador duro del pase de lista completo (empieza el cuerpo de la sesión).
RE_HARD_STOP = re.compile(
    r"(?:^|\n)\s*(?:SE[ÑN]ORA?\b|\(Es\s+la\s+hora|Habiendo\s+n[uú]mero|"
    r"#+\s*\d+\s*\.\-|\d+\s*\.\-\s+[A-ZÁÉÍÓÚ])",
)
# Tokens que NO son nombres (basura que a veces cae dentro del bloque).
RE_NOISE = re.compile(r"^\(|^\d|presidenta?$|secretari", re.I)


def _clean_block(txt: str) -> str:
    # Une hifenaciones de fin de línea y saltos de línea internos del bloque.
    txt = re.sub(r"-\s*\n\s*", "", txt)       # "Ba-\nrreiro" -> "Barreiro"
    txt = re.sub(r"\s*\n\s*", " ", txt)        # wrap dentro del bloque
    return re.sub(r"\s+", " ", txt).strip()


def _split_names(block: str):
    block = _clean_block(block).rstrip(" .")
    # separa por comas y por " y " / " e " final
    parts = re.split(r",|\s+\by\b\s+|\s+\be\b\s+", block)
    out = []
    for p in parts:
        p = p.strip(" .;:")
        if len(p) < 3 or RE_NOISE.search(p):
            continue
        if not re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]", p):
            continue
        # un nombre real tiene al menos una mayúscula inicial de palabra
        if not re.search(r"[A-ZÁÉÍÓÚÑ]", p):
            continue
        out.append(p)
    return out


def parse_text(text: str):
    """Devuelve (present:list[str], absent:list[str])."""
    m = RE_START.search(text)
    if not m:
        return [], []
    rest = text[m.end():]
    # límite del pase de lista entero
    hs = RE_HARD_STOP.search(rest)
    region = rest[: hs.start()] if hs else rest[:6000]
    # primer encabezado de ausentes parte presentes/ausentes
    ah = RE_ABSENT_HDR.search(region)
    if ah:
        present_block = region[: ah.start()]
        absent_region = region[ah.start():]
    else:
        present_block, absent_region = region, ""
    present = _split_names(present_block)
    # ausentes: concatena todos los sub-bloques (quita sus encabezados)
    absent_txt = RE_ABSENT_HDR.sub(" , ", absent_region)
    absent = _split_names(absent_txt) if absent_txt.strip() else []
    return present, absent


def _session_date(session_id: str) -> str:
    m = re.match(r"(\d{4}-\d{2}-\d{2})", session_id)
    return m.group(1) if m else ""


def _process(path: str):
    sid = os.path.splitext(os.path.basename(path))[0]
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return sid, [], []
    present, absent = parse_text(text)
    return sid, present, absent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="dir de corrected/ o un .txt")
    ap.add_argument("--output", help="CSV de salida (session_id;date;status;name_raw)")
    ap.add_argument("--print", action="store_true", dest="do_print")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    if os.path.isdir(args.input):
        files = [os.path.join(args.input, f) for f in os.listdir(args.input)
                 if f.endswith(".txt")]
    else:
        files = [args.input]

    rows = []
    n_present = n_sessions_with = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for sid, present, absent in ex.map(_process, files):
            if present:
                n_sessions_with += 1
                n_present += len(present)
            date = _session_date(sid)
            for nm in present:
                rows.append((sid, date, "present", nm))
            for nm in absent:
                rows.append((sid, date, "absent", nm))

    rows.sort(key=lambda r: (r[0], r[2]))
    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["session_id", "date", "status", "name_raw"])
            w.writerows(rows)

    if args.do_print:
        for r in rows[:80]:
            print(r)

    import json
    print(json.dumps({
        "files": len(files),
        "sessions_with_attendance": n_sessions_with,
        "present_names_total": n_present,
        "rows": len(rows),
        "output": args.output,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
