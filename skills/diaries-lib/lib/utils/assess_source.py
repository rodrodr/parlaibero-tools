#!/usr/bin/env python3
"""
Evaluación de fuentes por AÑO: discriminador OCR/embebido + estimación de carga.

LECCIÓN CENTRAL (UY 2026-06) — el discriminador OCR/embebido fiable es la ESTRUCTURA
del PDF (¿capa de imagen escaneada o texto vectorial nativo?), NO las métricas de
carácter del texto. Un escaneo tiene chars válidos (0% "corrupto") aunque el orden de
columnas y la integridad de párrafos sean malos — algo que el char-count NO ve. Construir
la frontera con heurísticas de carácter reproduce el error original (ver memoria
[[feedback-uy-ocr-vs-embed]]).

Señal estructural fiable (pdfimages): páginas de cuerpo con imagen de página completa
⇒ ESCANEADO; sin imágenes ⇒ DIGITAL nativo. "Página completa" se decide de forma
RELATIVA al tamaño físico de la página (imagen que cubre > 80% del área ⇒ escaneo,
sea cual sea su resolución) — el umbral absoluto de ancho (>1000px) queda solo como
respaldo cuando falta el ppi. LECCIÓN (EC 2026-07): escaneos XnView a 72–96 DPI
producen imágenes de ~860px que quedaban bajo el umbral absoluto y el año salía
"DIGITAL" con chars/pág≈0 — contradicción imposible en un PDF digital real. De ahí
también el guard: DIGITAL + densidad ≈ 0 ⇒ reclasificar como ESCANEADO (marcado *).

  - DIGITAL  → usar texto embebido directamente (definitivo, sin OCR).
  - ESCANEADO → el texto embebido es una capa OCR de calidad DESCONOCIDA. Decidir OCR
    fresco vs embebido con un TEST EMPÍRICO de extracción (comparar intervenciones
    extraídas de embebido vs OCR en 2-3 sesiones), NO con métricas de carácter.

ESTIMACIÓN DE CARGA: el coste de OCR escala con CHARS a generar (densidad), no con
páginas. El conteo de chars del embebido es un proxy gratis del volumen por año.
Muestreo: páginas ALEATORIAS del rango COMPLETO de varios docs (las primeras —carátula/
índice— son ~1.4x más ligeras y sesgan al alza).

CLI:
    python assess_source.py --country uy
    python assess_source.py --country uy --samples-per-year 6 --chars-per-hour 1270000
"""
import sys
import re
import random
import argparse
import subprocess
import statistics
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

BASE_DIR = Path.cwd()  # raíz del proyecto (datos); el skill se ejecuta desde la raíz del proyecto

FULLPAGE_IMG_MIN_WIDTH = 1000     # px: respaldo absoluto si no hay ppi (escaneos ≥ ~120 DPI)
FULLPAGE_AREA_FRACTION = 0.8      # imagen que cubre > 80% del área física de la página ⇒ escaneo
SCANNED_DOC_FRACTION = 0.5        # > 50% de docs del año escaneados ⇒ año ESCANEADO
DIGITAL_MIN_CHARS_PER_PAGE = 100  # DIGITAL con densidad bajo esto = contradicción ⇒ ESCANEADO
EMBED_TO_OCR_RATIO = 1.10         # OCR genera ~1.1x los chars del embebido (calibrado UY)
DEFAULT_CHARS_PER_HOUR = 1_270_000  # M3 Max, LightOnOCR-2:1b, 6 workers


def page_dims_pts(pdf: Path) -> tuple[float, float] | None:
    """Tamaño físico de página (pts) según pdfinfo, o None si no se puede leer."""
    try:
        out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, timeout=20).stdout
        m = re.search(r"Page size:\s+([\d.]+)\s*x\s*([\d.]+)\s*pts", out)
        return (float(m.group(1)), float(m.group(2))) if m else None
    except Exception:
        return None


def doc_is_scanned(pdf: Path) -> bool | None:
    """True si las páginas de cuerpo tienen imagen de página completa (escaneo).

    Criterio primario RELATIVO: área física de la imagen (px/ppi) > FULLPAGE_AREA_FRACTION
    del área de la página — independiente de la resolución del escaneo (EC: 72–96 DPI
    ⇒ ~860px, invisible para el umbral absoluto). El ancho absoluto se mantiene como
    respaldo cuando el ppi o el tamaño de página no están disponibles.
    """
    try:
        out = subprocess.run(["pdfimages", "-list", "-f", "4", "-l", "8", str(pdf)],
                             capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return None
    dims = page_dims_pts(pdf)
    page_area = dims[0] * dims[1] if dims else 0.0
    big = 0
    for line in out.splitlines()[2:]:
        parts = line.split()
        if len(parts) <= 4 or not parts[3].isdigit():
            continue
        if int(parts[3]) > FULLPAGE_IMG_MIN_WIDTH:
            big += 1
            continue
        if page_area and len(parts) > 13:
            try:
                w_pts = int(parts[3]) / float(parts[12]) * 72
                h_pts = int(parts[4]) / float(parts[13]) * 72
            except (ValueError, ZeroDivisionError):
                continue
            if (w_pts * h_pts) / page_area > FULLPAGE_AREA_FRACTION:
                big += 1
    return big > 0


def doc_density(pdf: Path, pages_per_doc: int) -> list[int]:
    """Chars por página de una muestra ALEATORIA del rango completo (proxy de volumen)."""
    try:
        out = subprocess.run(["pdftotext", str(pdf), "-"],
                             capture_output=True, text=True, timeout=90).stdout
    except Exception:
        return []
    body = [p for p in out.split("\f") if len(p) > 200]
    if not body:
        return []
    return [len(p) for p in random.sample(body, min(pages_per_doc, len(body)))]


def page_count(pdf: Path) -> int:
    try:
        out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, timeout=20).stdout
        m = re.search(r"Pages:\s+(\d+)", out)
        return int(m.group(1)) if m else 0
    except Exception:
        return 0


def assess_one(args) -> dict:
    pdf, pages_per_doc = args
    return {"scanned": doc_is_scanned(pdf),
            "chars": doc_density(pdf, pages_per_doc),
            "pages": page_count(pdf)}


YEAR_MIN, YEAR_MAX = 1800, 2099


def infer_year(pdf: Path, raw: Path) -> int | None:
    """Año de un PDF: cualquier componente del path bajo raw/, o el nombre del archivo.

    Cascada: (1) directorio de 4 dígitos en el path (raw/pdf/1990/… o raw/1990/…);
    (2) fecha compacta YYYYMMDD en el nombre (C19900311_0.pdf → 1990);
    (3) fecha con separadores YYYY-MM-DD (d_2002-10-16_*.pdf → 2002);
    (4) año aislado de 4 dígitos en el nombre.
    """
    for part in pdf.relative_to(raw).parts[:-1]:
        if part.isdigit() and len(part) == 4 and YEAR_MIN <= int(part) <= YEAR_MAX:
            return int(part)
    name = pdf.name
    m = re.search(r"(?<!\d)((?:18|19|20)\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)", name)
    if m:
        return int(m.group(1))
    m = re.search(r"(?<!\d)((?:18|19|20)\d{2})[-_./](0[1-9]|1[0-2])[-_./](0[1-9]|[12]\d|3[01])", name)
    if m:
        return int(m.group(1))
    m = re.search(r"(?<!\d)((?:18|19|20)\d{2})(?!\d)", name)
    return int(m.group(1)) if m else None


def discover_year_pdfs(raw: Path) -> tuple[dict[int, list[Path]], list[Path]]:
    """PDFs a cualquier profundidad bajo raw/, agrupados por año inferido.

    Los layouts plano (raw/*.pdf), por año (raw/{año}/) y con nivel intermedio
    (raw/pdf/{año}/) son casos particulares del mismo barrido recursivo. Extensión
    case-insensitive (.pdf/.PDF); se ignoran componentes ocultos (.DS_Store etc.).
    Devuelve (year_pdfs, sin_año).
    """
    year_pdfs: dict[int, list[Path]] = {}
    no_year: list[Path] = []
    for pdf in sorted(raw.rglob("*")):
        if not pdf.is_file() or pdf.suffix.lower() != ".pdf":
            continue
        if any(part.startswith(".") for part in pdf.relative_to(raw).parts):
            continue
        yr = infer_year(pdf, raw)
        if yr is None:
            no_year.append(pdf)
        else:
            year_pdfs.setdefault(yr, []).append(pdf)
    return year_pdfs, no_year


def main():
    ap = argparse.ArgumentParser(description="Frontera OCR/embebido (estructural) + carga por densidad")
    ap.add_argument("--country", required=True)
    ap.add_argument("--samples-per-year", type=int, default=6)
    ap.add_argument("--pages-per-doc", type=int, default=5)
    ap.add_argument("--chars-per-hour", type=float, default=DEFAULT_CHARS_PER_HOUR)
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()

    raw = BASE_DIR / "source" / args.country / "raw"
    if not raw.exists():
        print(f"ERROR: no existe {raw}"); sys.exit(1)

    year_pdfs, no_year = discover_year_pdfs(raw)
    if no_year:
        print(f"AVISO: {len(no_year)} PDFs sin año inferible (ignorados), "
              f"p.ej. {no_year[0].relative_to(raw)}")
    if not year_pdfs:
        print("ERROR: no se detectaron PDFs por año"); sys.exit(1)

    print(f"Evaluación de fuentes — {args.country.upper()}  "
          f"(discriminador: estructura PDF; {args.samples_per_year} docs/año)\n")
    hdr = f"{'Año':>5} {'docs':>5} {'escaneados':>11} {'chars/pág':>10} {'firma':>11}"
    print(hdr); print("-" * len(hdr))

    year_info = {}
    for yr in sorted(year_pdfs):
        pdfs = year_pdfs[yr]
        sample = random.sample(pdfs, min(args.samples_per_year, len(pdfs)))
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            res = list(ex.map(assess_one, [(p, args.pages_per_doc) for p in sample]))
        scanned_flags = [r["scanned"] for r in res if r["scanned"] is not None]
        if not scanned_flags:
            continue
        frac_scanned = sum(scanned_flags) / len(scanned_flags)
        all_chars = [c for r in res for c in r["chars"]]
        density = statistics.median(all_chars) if all_chars else 0
        avg_pages = statistics.mean([r["pages"] for r in res if r["pages"]]) if any(r["pages"] for r in res) else 0

        signature = "ESCANEADO" if frac_scanned > SCANNED_DOC_FRACTION else \
                    ("MIXTO" if frac_scanned > 0 else "DIGITAL")
        # Guard de contradicción: DIGITAL con chars/pág ≈ 0 es imposible en un PDF
        # digital real (el texto vectorial SIEMPRE tiene densidad). Señal estructural
        # engañada (p.ej. escaneo de baja resolución atípico) ⇒ tratar como escaneo.
        contradiction = signature == "DIGITAL" and density < DIGITAL_MIN_CHARS_PER_PAGE
        if contradiction:
            signature = "ESCANEADO"
        year_info[yr] = {"sig": signature, "density": density, "n_docs": len(pdfs),
                         "avg_pages": avg_pages, "frac": frac_scanned,
                         "contradiction": contradiction}
        print(f"{yr:>5} {len(pdfs):>5} {f'{sum(scanned_flags)}/{len(scanned_flags)}':>11} "
              f"{density:>10.0f} {signature + ('*' if contradiction else ''):>12}")

    if any(v["contradiction"] for v in year_info.values()):
        print("\n  * CONTRADICCIÓN: firma estructural DIGITAL pero chars/pág≈0 → reclasificado ESCANEADO.")
        print("    Revisar manualmente 1-2 PDFs del año (posible escaneo atípico no detectado por pdfimages).")

    # Frontera
    scanned_years = sorted(y for y, v in year_info.items() if v["sig"] in ("ESCANEADO", "MIXTO"))
    digital_years = sorted(y for y, v in year_info.items() if v["sig"] == "DIGITAL")
    print("\n── Recomendación ──")
    if scanned_years:
        print(f"  ESCANEADO (capa OCR de calidad desconocida): {scanned_years[0]}–{scanned_years[-1]} "
              f"({len(scanned_years)} años)")
        print(f"    → Confirmar OCR-fresco vs embebido con TEST EMPÍRICO de extracción en 2-3 sesiones.")
        print(f"      NO decidir por métricas de carácter (chars válidos ≠ extracción correcta).")
    if digital_years:
        print(f"  DIGITAL nativo (usar embebido directo): {digital_years[0]}–{digital_years[-1]} "
              f"({len(digital_years)} años)")

    # Carga OCR estimada para los años escaneados
    if scanned_years:
        # Años sin capa de texto embebida (densidad≈0, p.ej. contradicciones) no aportan
        # proxy de volumen: usar la mediana de los años con densidad real como sustituto.
        real_densities = [v["density"] for v in year_info.values()
                          if v["density"] >= DIGITAL_MIN_CHARS_PER_PAGE]
        fallback_density = statistics.median(real_densities) if real_densities else 1800
        total_chars = 0.0
        total_pages = 0.0
        for yr in scanned_years:
            v = year_info[yr]
            yr_pages = v["avg_pages"] * v["n_docs"]
            total_pages += yr_pages
            dens = v["density"] if v["density"] >= DIGITAL_MIN_CHARS_PER_PAGE else fallback_density
            total_chars += yr_pages * dens * EMBED_TO_OCR_RATIO
        eta_h = total_chars / args.chars_per_hour
        print(f"\n── Carga OCR estimada (si se OCR-ean los años escaneados) ──")
        print(f"  Páginas (aprox): {total_pages:,.0f}  |  Carga: {total_chars/1e6:,.0f} Mchars")
        print(f"  ETA @ {args.chars_per_hour/1e6:.2f} Mchars/h: {eta_h:.0f}h = {eta_h/24:.1f} días")
        print(f"  (densidad-aware: cada año pondera por sus chars/pág reales)")


if __name__ == "__main__":
    main()
