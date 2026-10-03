#!/usr/bin/env python3
"""
Parser del track TRADICIONAL de Chile (PDF/DOC) -> matriz de intervenciones.

Complementa al track XML (parse_cl_xml.py). Mismo esquema de salida (11 cols, con `tipo`) para
integrar ambos en una matriz única. El formato de orador es IDÉNTICO al de los marcadores inline
del XML ("El señor APELLIDO (rol).-"), así que reutiliza toda la maquinaria de parse_cl_xml:
MARKER, resolve, resolve_by_date, turn_tipo, party_at, deputies-index, ROLLCALL_RE.

Sub-eras (source_format en session_manifest.csv):
  pdf_embedded (1990–95, escaneado pero texto embebido OK) · doc_native (1996–2015, .DOC textutil) ·
  pdf_digital (2016–25, nativo). NINGUNO usa OCR.

Diferencias con el XML (no estructurado): no hay roster de bloques -> resolución por deputies.csv
(apellido + fecha de sesión); metadata desde la CABECERA del documento + nombre de archivo; los
pases de lista de voto vienen como texto ("-Votaron por la afirmativa…") y se extraen a filas voto_*.

CLI:
  python parse_cl_traditional.py --file source/cl/raw/pdf/2024/C20240103_124.pdf
  python parse_cl_traditional.py --sample
  python parse_cl_traditional.py --all --workers 8 --out source/cl/matrix/interventions_trad.csv
"""
import argparse, csv, re, subprocess, sys
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

LIB = Path(__file__).resolve().parent
sys.path.insert(0, str(LIB))
import parse_cl_xml as X
from strip_headers import strip_running_furniture, strip_text

MONTHS = {m: i for i, m in enumerate(
    ["enero","febrero","marzo","abril","mayo","junio","julio","agosto",
     "septiembre","octubre","noviembre","diciembre"], 1)}

# ── extracción de texto por formato ───────────────────────────────────────────
DOC_ARTIFACT = re.compile(r"EMBED\s+\w+\s*\\?\*?\s*MERGEFORMAT|EMBED\s+\w+", re.I)

def extract_doc(path):
    out = subprocess.run(["textutil", "-convert", "txt", "-stdout", str(path)],
                         capture_output=True, text=True, timeout=120)
    txt = DOC_ARTIFACT.sub("", out.stdout)
    cleaned, _ = strip_text(txt, recurrence=0.5, similarity=85)   # modo no paginado
    return cleaned

def extract_pdf(path):
    import fitz
    doc = fitz.open(str(path))
    pages = [pg.get_text("text") for pg in doc]
    doc.close()
    if len(pages) >= 4:
        clean_pages, _ = strip_running_furniture(pages, edge=3, recurrence=0.5,
                                                 similarity=85, min_pages=4)
        return "\n".join(clean_pages)
    return "\n".join(pages)

def get_text(path):
    return extract_doc(path) if path.suffix.lower() in (".doc", ".docx") else extract_pdf(path)

def dehyphenate(t):
    t = re.sub(r"(\w)[-­]\s*\n\s*(\w)", r"\1\2", t)                 # corte a fin de línea (newline)
    t = re.sub(r"([a-záéíóúñ])-([a-záéíóúñ]{2,})", r"\1\2", t)      # "Presi-denta" sin espacio
    t = re.sub(r"([a-záéíóúñ])-\s+([a-záéíóúñ]{2,})", r"\1\2", t)   # "Vicepresi- dente" con espacio
    return re.sub(r"\s+", " ", t).strip()

# ── metadata desde cabecera + nombre de archivo ───────────────────────────────
def file_date(name):
    m = re.search(r"C(\d{8})", name)
    if m:
        d = m.group(1); return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    m = re.search(r"(\d{4}-\d{2}-\d{2})", name)
    return m.group(1) if m else ""

def parse_meta(text, name):
    head = text[:2500]
    date = file_date(name)
    if not date:
        m = re.search(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", head)
        if m and m.group(2).lower() in MONTHS:
            date = f"{m.group(3)}-{MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    snum = re.search(r"Sesi[oó]n\s+(\d+)[ªa]", head)
    if not snum:
        snum = re.search(r"Ses(\d+)", name)
    leg = (re.search(r"LEGISLATURA\s+(\d+)", head) or
           re.search(r"(\d+)[ªa]?\.?\s+LEGISLATURA", head) or   # "323a. LEGISLATURA"
           re.search(r"Leg(\d+)", name))
    # tipo: parentético tras la línea de sesión, "(Ordinaria, de…", o palabra suelta
    mtype = re.search(r"\((Ordinaria|Especial|Extraordinaria|Solemne|Pública)\b", head, re.I)
    stype = X.norm_type(mtype.group(1)) if mtype else ""
    if not stype:  # era temprana: "LEGISLATURA EXTRAORDINARIA", "Sesión de instalación"
        if re.search(r"instalaci[oó]n", head, re.I):      stype = "instalación"
        elif re.search(r"\bEXTRAORDINARIA\b", head):       stype = "extraordinaria"
        elif re.search(r"\bESPECIAL\b", head, re.I):       stype = "especial"
        elif re.search(r"\bORDINARIA\b", head):            stype = "ordinaria"
    return (leg.group(1) if leg else "",
            snum.group(1) if snum else "",
            date,
            stype)

# ── pases de lista de voto en texto plano -> filas voto_* ─────────────────────
VOTE_START = re.compile(
    r"-?\s*(?P<k>Votaron\s+por\s+la\s+afirmativa|Votaron\s+por\s+la\s+negativa|"
    r"Se\s+abstuvieron|Se\s+abstuvo|Vot[oó]\s+por\s+la\s+afirmativa|Vot[oó]\s+por\s+la\s+negativa)"
    r"[^:]*:?", re.I)
VOTE_KIND = {"afirmativa": ("voto_afavor", "VOTACIÓN AFIRMATIVA"),
             "negativa":   ("voto_encontra", "VOTACIÓN NEGATIVA"),
             "abst":       ("voto_abstencion", "ABSTENCIONES")}
def vote_kind(k):
    k = k.lower()
    if "afirmativa" in k: return VOTE_KIND["afirmativa"]
    if "negativa" in k:   return VOTE_KIND["negativa"]
    return VOTE_KIND["abst"]

def extract_votes(text):
    """Saca los pases de lista de voto del texto; devuelve (texto_sin_votos, [filas_voto])."""
    votes = []
    spans = []
    starts = list(VOTE_START.finditer(text))
    for i, m in enumerate(starts):
        # fin del bloque de voto: siguiente voto, o un marcador de orador, o +1200 chars
        nxt = starts[i+1].start() if i+1 < len(starts) else len(text)
        mk = X.MARKER.search(text, m.end(), min(nxt, m.end()+2000))
        end = min(nxt, mk.start() if mk else nxt)
        body = text[m.end():end].strip(" ;.-")
        if 3 < len(body) < 4000:
            tipo, label = vote_kind(m.group("k"))
            votes.append((tipo, label, text[m.start():end]))
            spans.append((m.start(), end))
    # eliminar spans del texto (de atrás hacia delante)
    for s, e in reversed(spans):
        text = text[:s] + " " + text[e:]
    return text, votes

# ── parseo principal de una sesión ────────────────────────────────────────────
def parse_session(path, dep_idx):
    name = Path(path).name
    raw = get_text(Path(path))
    legislature, session_number, date, session_type = parse_meta(raw, name)
    text = dehyphenate(raw)
    text, votes = extract_votes(text)

    rows = []
    def emit(sraw, sid, tipo, seg):
        rows.append((legislature, session_number, date, session_type, sraw, sid, tipo, seg))

    marks = list(X.MARKER.finditer(text))
    for i, mk in enumerate(marks):
        end = marks[i+1].start() if i+1 < len(marks) else len(text)
        seg = text[mk.end():end].strip()
        sur = mk.group("sur"); role = X.marker_role(mk)
        sid = X.resolve(sur, role, {}, {}, dep_idx, date, mk.group("dname") or "")
        sraw = re.sub(r"\s+", " ", mk.group(0)).strip().rstrip(".-").strip()
        if seg and len(seg) > 1:
            emit(sraw, sid, X.turn_tipo("INTERVENCION_DIPUTADO", role, bool(sid)), seg)
    for tipo, label, body in votes:
        emit(label, "", tipo, body.strip())
    return rows

def process_one(path):
    return X.enrich(parse_session(path, _W["idx"]), _W["info"])

_W = {}
def _init():
    _W["info"] = X.load_deputies(); _W["idx"] = X.load_dep_index()

def iter_sources():
    rootp = Path("source/cl/raw/pdf")
    for y in sorted(rootp.iterdir()):
        if not y.is_dir(): continue
        for f in sorted(y.iterdir()):
            if f.suffix.lower() in (".pdf", ".doc", ".docx"):
                yield f

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file"); ap.add_argument("--all", action="store_true")
    ap.add_argument("--sample", action="store_true"); ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default="source/cl/matrix/interventions_trad.csv")
    args = ap.parse_args()

    if args.file or args.sample:
        idx = X.load_dep_index(); dep = X.load_deputies()
        if args.file:
            files = [Path(args.file)]
        else:
            allf = list(iter_sources())
            pe = next(f for f in allf if "199" in str(f) and f.suffix.lower()==".pdf")
            dn = next(f for f in allf if f.suffix.lower()==".doc")
            pd = next(f for f in allf if "202" in str(f) and f.suffix.lower()==".pdf")
            files = [pe, dn, pd]
        for f in files:
            rows = X.enrich(parse_session(f, idx), dep)
            from collections import Counter
            tipos = Counter(r[10] for r in rows)
            wid = sum(1 for r in rows if r[5])
            print(f"\n=== {f.name}: {len(rows)} filas, {wid} con id ({wid/max(len(rows),1)*100:.0f}%) ===")
            print(f"  meta: leg={rows[0][0]!r} s{rows[0][1]} {rows[0][2]} {rows[0][3]!r}" if rows else "  (0)")
            print(f"  tipos: {dict(tipos)}")
            for r in rows[:5]:
                print(f"    [{r[10]}] raw={r[4][:30]!r} id={r[5]} text={r[9][:55]!r}")
        return

    files = list(iter_sources())
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    nf = nr = 0
    with open(args.out, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter=";"); w.writerow(X.CANON_COLS)
        with ProcessPoolExecutor(max_workers=args.workers, initializer=_init) as ex:
            futs = {ex.submit(process_one, f): f for f in files}
            for fut in as_completed(futs):
                try:
                    rs = fut.result()
                except Exception as e:
                    print(f"  ERROR {futs[fut].name}: {e}", flush=True); continue
                w.writerows(rs); nf += 1; nr += len(rs)
                if nf % 100 == 0:
                    print(f"  {nf}/{len(files)} archivos, {nr} filas", flush=True)
    print(f"OK: {nf} archivos -> {nr} filas -> {args.out}")

if __name__ == "__main__":
    main()
