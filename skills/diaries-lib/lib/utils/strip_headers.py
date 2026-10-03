#!/usr/bin/env python3
"""
Detección y eliminación de CABECEROS y PIES de página recurrentes (running
headers/footers) en diarios parlamentarios. Determinista, sin LLM.

Opera SOBRE PÁGINAS (lista de strings) — por eso vive en diaries-extract, que es
el único punto donde la frontera de página está intacta y AGUAS ABAJO del OCR:
  - pdf_digital → páginas de fitz
  - OCR         → cada page_*.txt es una página (el OCR NO se reprocesa)

Algoritmo (validado en UY, ambas épocas, 819k líneas, 0 falsos positivos):
  1. Solo se consideran líneas en la ZONA-BORDE (primeras/últimas `edge` líneas de
     cada página). El cuerpo nunca se toca → la prosa que menciona la institución
     (p.ej. "LA CÁMARA DE REPRESENTANTES se reunirá...") está a salvo.
  2. Una línea es "mobiliario" si su forma RECURRE en >= `recurrence` de las páginas.
     Tres señales, robustas al ruido OCR:
       a) Nº de página: línea de borde compuesta solo de dígitos.
       b) Cluster difuso (RapidFuzz token_sort_ratio, sensible a longitud → no
          confunde una carta larga que contiene los tokens del cabecero). Los
          centroides deben ser CORTOS (<= max_centroid_tokens) — un mueble es breve.
       c) Ancla posicional: token-líder (>=6 letras) que encabeza la ÚLTIMA línea de
          >= `recurrence` de las páginas → pie-sello (el OCR destroza cada palabra
          pero "Biblioteca…" siempre lidera la última línea).
  3. La normalización enmascara dígitos (#) y quita acentos/puntuación, de modo que
     "CÁMARA"≈"CAMARA" y "- 5 -"≈"- 12 -".

Overrides por país (opcionales, desde country_config):
  protect_patterns: regex; una línea de borde que casa NUNCA se elimina (seguridad).
  extra_patterns:   regex; una línea de borde que casa SIEMPRE se elimina.

CLI:
    python strip_headers.py --ocr-dir <dir page_*.txt>   [--report]
    python strip_headers.py --pdf <archivo.pdf>          [--report]
"""
from __future__ import annotations
import re
import sys
import math
import json
import argparse
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False


# ── normalización ──────────────────────────────────────────────────────────────

def _canon(line: str) -> str:
    """Acentos fuera, minúsculas, dígitos→#, solo [a-z # espacio]."""
    s = unicodedata.normalize("NFKD", line)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.casefold()
    s = re.sub(r"\d+", "#", s)
    s = re.sub(r"[^a-z#\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _lead_token(line: str, min_len: int = 6) -> str | None:
    for t in _canon(line).split():
        if len(t) >= min_len:
            return t
    return None


def _is_bare_pagenum(line: str) -> bool:
    c = _canon(line)
    return bool(line.strip()) and c.replace("#", "").strip() == "" and "#" in c


def _ratio(a: str, b: str) -> float:
    if HAS_RAPIDFUZZ:
        return fuzz.token_sort_ratio(a, b)
    # Fallback sin rapidfuzz: similitud por tokens (Jaccard*100, sensible a longitud)
    sa, sb = set(a.split()), set(b.split())
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    return 100.0 * inter / max(len(sa), len(sb))


# ── detección ────────────────────────────────────────────────────────────────

def strip_running_furniture(
    pages: list[str],
    *,
    edge: int = 3,
    min_pages: int = 4,
    recurrence: float = 0.5,
    similarity: int = 85,
    max_centroid_tokens: int = 10,
    protect_patterns: list[str] | None = None,
    extra_patterns: list[str] | None = None,
    speaker_patterns: list[str] | None = None,
    max_removal_ratio: float = 0.35,
) -> tuple[list[str], dict]:
    """Devuelve (paginas_limpias, report). No muta `pages`.

    `max_removal_ratio` es un tope de seguridad: por encima de él no se elimina NADA y el
    report lo dice. Ver la nota al final de la función.

    ⚠ `speaker_patterns`: UN MARCADOR DE ORADOR NUNCA ES MOBILIARIO. La ruta no paginada
    (`strip_text`) ya lo respetaba con `is_speaker()`; esta no, y era un descuido, no un diseño.
    El detector borra líneas que se REPITEN en el borde de la página, y «EL SEÑOR PRESIDENTE.-»
    se repite cientos de veces: cuando cae en el borde, lo elimina.

    Medido en EC (2026-08-15): se comía el **7,89% de los marcadores** del OCR-LLM (~44.200
    extrapolados) frente al 0,62% del de tesseract. La diferencia de 12× tiene una causa
    incómoda: el OCR limpio produce el marcador IDÉNTICO cada vez, así que el agrupador difuso
    lo reconoce como forma recurrente; el ruido de tesseract protegía sus marcadores por
    accidente. **Cuanto mejor es el OCR, más lo castigaba este filtro.**
    """
    protect = [re.compile(p) for p in (protect_patterns or [])] + \
              [re.compile(p) for p in (speaker_patterns or [])]
    extra = [re.compile(p) for p in (extra_patterns or [])]

    # ⚠⚠ LA LÍNEA EN BLANCO ES LA SEPARACIÓN DE PÁRRAFO Y NO SE PUEDE DESCARTAR.
    # Hasta 2026-08-19 esta línea llevaba `if ln.strip()`, que las eliminaba todas para poder
    # indexar la zona-borde con índices consecutivos. El efecto colateral era destructivo: el
    # OCR entrega entre un 20 % y un 50 % de líneas vacías (medido en EC: 39 de 110) y `extracted`
    # salía con CERO. Sin esa señal, la etapa `correct` no puede distinguir un fin de párrafo de
    # un corte por el ancho de columna, y tuvo que recurrir a heurísticas —«empieza por
    # mayúscula» = párrafo nuevo— que dejan sin unir `Espírito`⏎`Santo` o `Mesa`⏎`Diretora`.
    # De ahí vienen la mayoría de los problemas de unión de líneas y de títulos partidos.
    # Ahora se CONSERVAN, y la zona-borde se indexa con un contador que solo cuenta las no vacías.
    pl = [[ln.rstrip() for ln in p.splitlines()] for p in pages]
    n_nonempty = sum(1 for p in pl if any(ln.strip() for ln in p))
    total_lines = sum(sum(1 for ln in p if ln.strip()) for p in pl)

    report: dict = {
        "enabled": True,
        "n_pages": n_nonempty,
        "skipped": False,
        "furniture_forms": [],
        "lines_removed": 0,
        "removal_ratio": 0.0,
        "removed_samples": [],
        "suspect_removals": [],
    }

    if n_nonempty < min_pages or total_lines == 0:
        report["skipped"] = f"solo {n_nonempty} páginas (< min_pages={min_pages})"
        return ["\n".join(p) for p in pl], report

    thr = max(2, math.ceil(recurrence * n_nonempty))

    # (b) clusters difusos sobre FORMAS ÚNICAS de la zona-borde (centroides cortos).
    # Dedup primero: el coste es O(formas_únicas × centroides), no O(ocurrencias²).
    form_pages: dict[str, set] = defaultdict(set)
    for i, p in enumerate(pl):
        if not p:
            continue
        for raw in p[:edge] + p[-edge:]:
            c = _canon(raw)
            nt = len(c.split())
            if nt < 2 or nt > max_centroid_tokens or not any(ch.isalpha() for ch in c):
                continue
            form_pages[c].add(i)
    # las formas más frecuentes siembran centroides; las variantes OCR se enganchan.
    centroids: list[list] = []  # [canon, set_pages]
    for c in sorted(form_pages, key=lambda x: -len(form_pages[x])):
        placed = False
        for cl in centroids:
            if abs(len(cl[0]) - len(c)) <= 14 and _ratio(c, cl[0]) >= similarity:
                cl[1] |= form_pages[c]
                placed = True
                break
        if not placed:
            centroids.append([c, set(form_pages[c])])
    furniture = [cl[0] for cl in centroids if len(cl[1]) >= thr]

    # (c) anclas posicionales: token-líder (>=6 letras) recurrente en la PRIMERA línea
    # (cabecera) y en la ÚLTIMA línea (pie). Robusto al ruido OCR palabra-a-palabra.
    first_lead, last_lead = Counter(), Counter()
    for p in pl:
        if not p:
            continue
        nL = len(p)
        top_tok = {_lead_token(p[j]) for j in range(min(edge, nL))}
        bot_tok = {_lead_token(p[j]) for j in range(max(0, nL - edge), nL)}
        for t in top_tok:
            if t:
                first_lead[t] += 1
        for t in bot_tok:
            if t:
                last_lead[t] += 1
    anchor_first = {t for t, ct in first_lead.items() if ct >= thr}
    anchor_last = {t for t, ct in last_lead.items() if ct >= thr}

    # ── eliminación (solo zona-borde) ──
    removed: list[str] = []
    clean_pages: list[str] = []
    for p in pl:
        # nL y j cuentan SOLO líneas con contenido: una vacía no ocupa posición de borde, o
        # bastarían dos vacías al principio para sacar la cabecera de la zona vigilada.
        nL = sum(1 for ln in p if ln.strip())
        keep = []
        j = -1
        for raw in p:
            if not raw.strip():          # línea en blanco: se conserva y no consume posición
                keep.append(raw)
                continue
            j += 1
            in_edge = j < edge or j >= nL - edge
            if not in_edge:
                keep.append(raw)
                continue
            if any(rx.search(raw) for rx in protect):       # nunca eliminar
                keep.append(raw)
                continue
            drop = False
            if any(rx.search(raw) for rx in extra):          # siempre eliminar
                drop = True
            elif _is_bare_pagenum(raw):                       # (a)
                drop = True
            else:
                c = _canon(raw)
                ntok = len(c.split())
                if ntok >= 2 and any(_ratio(c, f) >= similarity for f in furniture):
                    drop = True                               # (b) cluster difuso
                elif 1 <= ntok <= max_centroid_tokens:
                    # (c) ancla posicional — solo líneas CORTAS (un mueble es breve);
                    # una frase de prosa larga en el borde nunca se elimina por ancla.
                    ld = _lead_token(raw)
                    if j < edge and ld in anchor_first:
                        drop = True                           # cabecera
                    elif j >= nL - edge and ld in anchor_last:
                        drop = True                           # pie
            if drop:
                removed.append(raw)
            else:
                keep.append(raw)
        clean_pages.append("\n".join(keep))

    # ── informe / auditoría ──
    uniq_removed = list(dict.fromkeys(removed))
    # sospechosos de FP: línea larga tipo prosa que NO contiene ningún token-mueble
    furn_tokens = set()
    for f in furniture:
        furn_tokens.update(t for t in f.split() if len(t) >= 5)
    furn_tokens.update(anchor_first)
    furn_tokens.update(anchor_last)
    suspects = [
        x for x in uniq_removed
        if len(x.split()) > 9 and x.rstrip()[-1:] in ".!?"
        and not any(t in _canon(x) for t in furn_tokens)
    ]

    report["furniture_forms"] = furniture[:15]
    report["lines_removed"] = len(removed)
    ratio = len(removed) / total_lines if total_lines else 0.0
    report["removal_ratio"] = round(ratio, 4)
    report["removed_samples"] = uniq_removed[:15]
    report["suspect_removals"] = suspects[:15]

    # ⚠ TOPE DE SEGURIDAD. El mobiliario de página es una fracción pequeña del acta; si la
    # detección se lleva más de `max_removal_ratio`, no ha encontrado cabeceras: ha encontrado
    # el cuerpo. En DO arrasó 7 documentos —uno de 1.680.671 caracteres quedó en 614, un -100%—
    # y el total global no lo delataba, porque 3,7 M de pérdida se diluían en 471 M. Sin este
    # tope el fallo es SILENCIOSO: devuelve un texto plausible y vacío.
    if ratio > max_removal_ratio:
        report["skipped"] = (f"quitaba el {100*ratio:.0f}% de las líneas "
                             f"(> {100*max_removal_ratio:.0f}%): no se elimina nada")
        report["lines_removed"] = 0
        return pages, report
    return clean_pages, report


# ── modo NO PAGINADO (texto de sesión completo) ────────────────────────────────

def _greedy_clusters(form_to_set: dict, similarity: int, max_len_diff: int = 14) -> list:
    """Agrupa formas canónicas por similitud difusa. `form_to_set`: canon -> set(idx).
    Devuelve [[centroide, set_unión], ...]; las formas más frecuentes siembran centroides."""
    centroids: list = []
    for c in sorted(form_to_set, key=lambda x: -len(form_to_set[x])):
        placed = False
        for cl in centroids:
            if abs(len(cl[0]) - len(c)) <= max_len_diff and _ratio(c, cl[0]) >= similarity:
                cl[1] |= form_to_set[c]
                placed = True
                break
        if not placed:
            centroids.append([c, set(form_to_set[c])])
    return centroids


def strip_unpaginated(
    text: str,
    *,
    speaker_patterns: list | None = None,
    recurrence: float = 0.5,
    similarity: int = 85,
    max_centroid_tokens: int = 10,
    min_count: int = 4,
    protect_patterns: list | None = None,
    extra_patterns: list | None = None,
) -> tuple:
    """Texto SIN marcador de página: detecta cabeceros/pies por FRECUENCIA.

    Las líneas que recurren ~1 vez por página son el mobiliario (su recuento estima el nº de
    páginas). Los turnos de orador (`speaker_patterns`) y los paréntesis de acotación
    ("(Aplausos.)") se EXCLUYEN para no borrar contenido. Más conservador que el modo paginado
    (no hay restricción posicional): solo elimina lo que recurre >= recurrence × (pico de recurrencia)."""
    spk = [re.compile(p) for p in (speaker_patterns or [])]
    protect = [re.compile(p) for p in (protect_patterns or [])]
    extra = [re.compile(p) for p in (extra_patterns or [])]

    report = {"enabled": True, "mode": "frequency", "skipped": False, "furniture_forms": [],
              "lines_removed": 0, "removal_ratio": 0.0, "removed_samples": [], "suspect_removals": []}

    def is_speaker(s):
        return any(rx.search(s) for rx in spk)

    def is_protected_content(s):
        # Contenido legítimo que NO es mobiliario. Dos señales (modo frecuencia, sin posición):
        #  1. Acotación escénica ("(Pausa.)") o final de oración/cláusula (. ! ? ) ; :) →
        #     el contenido procedimental recurrente ("Comienza la votación. (Pausa.)") termina así;
        #     un mueble (fecha+número, nº de página, institución) no.
        #  2. Prosa en CAJA DE ORACIÓN: un cabecero tipográfico va en MAYÚSCULAS (o es puro
        #     número); si <50% de las letras son mayúsculas es prosa ("Efectuada la votación…").
        if re.match(r"^[(\[¡¿]", s) or s[-1:] in ".!?);:":
            return True
        alpha = [c for c in s if c.isalpha()]
        if alpha and sum(c.isupper() for c in alpha) / len(alpha) < 0.5:
            return True
        return False

    lines = text.split("\n")
    total_ne = sum(1 for l in lines if l.strip())
    if total_ne == 0:
        report["skipped"] = "texto vacío"
        return text, report

    # candidatos a mobiliario: líneas cortas, no-orador, no-acotación → set de índices
    form_idx: dict = defaultdict(set)
    for i, l in enumerate(lines):
        s = l.strip()
        if not s or is_speaker(s) or is_protected_content(s):
            continue
        c = _canon(s)
        if not c or len(c.split()) > max_centroid_tokens:
            continue
        form_idx[c].add(i)

    if not form_idx:
        report["skipped"] = "sin candidatos"
        return text, report

    # Solo se agrupan las formas RECURRENTES (count>=2): una forma única no puede ser
    # mobiliario, y restringir a las recurrentes acota el coste a unas pocas decenas de
    # formas (no a todo el texto) — clave para textos largos sin paginar.
    recurring = {c: idx for c, idx in form_idx.items() if len(idx) >= 2}
    clusters = _greedy_clusters(recurring, similarity) if recurring else []
    p_est = max((len(idx) for _, idx in clusters), default=0)
    thr = max(min_count, math.ceil(recurrence * p_est))
    furn_forms = [cen for cen, idx in clusters if len(idx) >= thr]

    # Eliminación: match difuso de cada línea candidata contra los pocos centroides-mueble
    # (barato, y recupera variantes OCR que aparecían una sola vez).
    removed, out = [], []
    for i, l in enumerate(lines):
        s = l.strip()
        if not s or is_speaker(s) or is_protected_content(s) or any(rx.search(l) for rx in protect):
            out.append(l)
            continue
        c = _canon(s)
        drop = bool(furn_forms) and len(c.split()) <= max_centroid_tokens \
            and any(_ratio(c, f) >= similarity for f in furn_forms)
        if not drop and any(rx.search(l) for rx in extra):
            drop = True
        if drop:
            removed.append(s)
        else:
            out.append(l)

    furn_tokens = set()
    for f in furn_forms:
        furn_tokens.update(t for t in f.split() if len(t) >= 5)
    suspects = [x for x in dict.fromkeys(removed)
                if len(x.split()) > 9 and x.rstrip()[-1:] in ".!?"
                and not any(t in _canon(x) for t in furn_tokens)]

    report["furniture_forms"] = furn_forms[:15]
    report["lines_removed"] = len(removed)
    report["removal_ratio"] = round(len(removed) / total_ne, 4)
    report["removed_samples"] = list(dict.fromkeys(removed))[:15]
    report["suspect_removals"] = suspects[:15]
    return "\n".join(out), report


def strip_text(text: str, *, page_break_marker: str | None = None, **kwargs) -> tuple:
    """Entrada para TEXTO (no lista de páginas). Dos posibilidades del modo no paginado:
      - CON marcador (`page_break_marker` presente): segmenta por el marcador y aplica el
        detector PAGINADO validado (segmentación perfecta).
      - SIN marcador: aplica el detector por FRECUENCIA (`strip_unpaginated`).
    """
    if page_break_marker and page_break_marker in text:
        pa = {k: v for k, v in kwargs.items()
              if k in ("edge", "min_pages", "recurrence", "similarity", "max_removal_ratio",
                       "max_centroid_tokens", "protect_patterns", "extra_patterns")}
        pages = text.split(page_break_marker)
        clean_pages, report = strip_running_furniture(pages, **pa)
        report["mode"] = "paginated_marker"
        return "\n\n".join(clean_pages), report
    fr = {k: v for k, v in kwargs.items()
          if k in ("speaker_patterns", "recurrence", "similarity",
                   "max_centroid_tokens", "min_count", "protect_patterns", "extra_patterns")}
    return strip_unpaginated(text, **fr)


# ── carga (para CLI / test) ────────────────────────────────────────────────────

def _load_ocr_dir(d: Path) -> list[str]:
    files = sorted(d.glob("page_*.txt"))
    return [f.read_text(encoding="utf-8", errors="replace") for f in files]


def _load_pdf(path: Path) -> list[str]:
    import fitz  # PyMuPDF
    doc = fitz.open(str(path))
    pages = [pg.get_text("text") for pg in doc]
    doc.close()
    return pages


def main():
    ap = argparse.ArgumentParser(description="Detecta/elimina cabeceros y pies recurrentes")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--ocr-dir", help="Directorio con page_*.txt (modo paginado)")
    src.add_argument("--pdf", help="Archivo PDF, texto embebido vía fitz (modo paginado)")
    src.add_argument("--text-file", dest="text_file",
                     help="Texto de sesión completo (modo NO paginado: marcador o frecuencia)")
    ap.add_argument("--page-break-marker", dest="page_break_marker", default=None,
                    help="Marca de salto de página en el texto (ej. '---PAGE BREAK---')")
    ap.add_argument("--speaker-pattern", dest="speaker_pattern", action="append", default=[],
                    help="Regex de turno de orador a excluir (repetible; modo frecuencia)")
    ap.add_argument("--edge", type=int, default=3)
    ap.add_argument("--recurrence", type=float, default=0.5)
    ap.add_argument("--similarity", type=int, default=85)
    ap.add_argument("--report", action="store_true", help="Imprime el report y ejemplos")
    args = ap.parse_args()

    if args.text_file:
        text = Path(args.text_file).read_text(encoding="utf-8", errors="replace")
        _, rep = strip_text(text, page_break_marker=args.page_break_marker,
                            speaker_patterns=args.speaker_pattern,
                            edge=args.edge, recurrence=args.recurrence, similarity=args.similarity)
    else:
        pages = _load_ocr_dir(Path(args.ocr_dir)) if args.ocr_dir else _load_pdf(Path(args.pdf))
        _, rep = strip_running_furniture(
            pages, edge=args.edge, recurrence=args.recurrence, similarity=args.similarity
        )

    if args.report:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        keys = [k for k in ("mode", "n_pages", "lines_removed", "removal_ratio",
                            "skipped", "suspect_removals") if k in rep]
        print(json.dumps({k: rep[k] for k in keys}, ensure_ascii=False))


if __name__ == "__main__":
    main()
