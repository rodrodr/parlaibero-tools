#!/usr/bin/env python3
"""
Análisis PROFUNDO de marcadores de orador por país (paso previo al tagging).

El honorífico ("SEÑOR", "Sr.", "O SR.", "Diputado"...) y el terminador (".-", ".—", ".", ":")
son ESPECÍFICOS de cada país y CAMBIAN por OCR, era y taquígrafo. No se pueden asumir: hay que
descubrirlos empíricamente sobre el corpus real. Esta herramienta escanea el texto (OCR y/o
embebido) y reporta, con frecuencias y ejemplos:

  1. HONORÍFICOS: tokens iniciales que preceden a un nombre en mayúsculas (SEÑOR, SEÑORA, SR.,
     SRA., DIPUTADO, DIPUTADA, PRESIDENTE, MINISTRO, O SR., A SRA., EL SEÑOR...).
  2. VARIANTES DE GÉNERO: pares masculino/femenino (SEÑOR/SEÑORA, DIPUTADO/DIPUTADA).
  3. TERMINADORES: distribución de la puntuación que separa el marcador de la intervención.
  4. ERRORES Y VARIACIONES (OCR / taquígrafo): honoríficos raros a distancia de edición ≤2 de
     uno común (SENOR, SEÑOA, SE&OR, SERÑOR...) → candidatos a normalización/corrección.

Salida: reporte legible + sugerencia de `speaker_tag_patterns` (estricto) y `speaker_loose_pattern`
(probabilístico) para el country_config.

CLI:
    python analyze_speaker_markers.py --country uy
    python analyze_speaker_markers.py --country uy --source ocr|extracted|both --max-files 400
"""
import re
import sys
import argparse
import unicodedata
from pathlib import Path
from collections import Counter

BASE_DIR = Path.cwd()  # raíz del proyecto (datos); el skill se ejecuta desde la raíz del proyecto

# Honoríficos canónicos conocidos (para detectar variantes/errores por proximidad)
KNOWN_HONORIFICS = [
    "SEÑOR", "SEÑORA", "SR", "SRA", "DIPUTADO", "DIPUTADA",
    "PRESIDENTE", "PRESIDENTA", "MINISTRO", "MINISTRA", "SECRETARIO", "SECRETARIA",
    "SENHOR", "SENHORA", "DEPUTADO", "DEPUTADA", "DOUTOR", "DOCTORA", "DOCTOR",
]
GENDER_PAIRS = [("SEÑOR", "SEÑORA"), ("SR", "SRA"), ("DIPUTADO", "DIPUTADA"),
                ("PRESIDENTE", "PRESIDENTA"), ("MINISTRO", "MINISTRA"),
                ("SECRETARIO", "SECRETARIA"), ("SENHOR", "SENHORA"), ("DEPUTADO", "DEPUTADA")]

# Línea candidata: honorífico+nombre en MAYÚSCULAS (solo letras — el terminador NO se absorbe),
# paréntesis opcional, terminador (punto/raya/dos puntos opcional), e intervención en PROSA.
# Requerir prosa (minúsculas en 'rest') excluye cabeceras en mayúsculas (CÁMARA, PROYECTO...).
CANDIDATE = re.compile(
    r"^(?P<head>[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ'’]*(?:\s+[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ'’]*){0,5})"
    r"(?P<paren>\s*\([^)]*\))?"
    r"(?P<term>\s*\.?\s*[-–—:]?\s*)"
    r"(?P<rest>[¿¡A-Za-záéíóúüñ].*)$"
)
_HAS_LOWER = re.compile(r"[a-záéíóúüñ]")


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.upper())
                   if unicodedata.category(c) != "Mn")


def _edit_distance(a: str, b: str) -> int:
    if abs(len(a) - len(b)) > 2:
        return 3
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[-1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def classify_terminator(term: str) -> str:
    t = term.strip()
    has_dot = "." in t
    has_dash = bool(re.search(r"[-–—]", t))
    has_colon = ":" in t
    if has_dot and has_dash:
        return "punto+raya  (.-/.—)"
    if has_dash:
        return "raya sola   (— sin punto)"
    if has_dot:
        return "punto solo  (.)"
    if has_colon:
        return "dos puntos  (:)"
    return "ninguno     (espacio)"


def main():
    ap = argparse.ArgumentParser(description="Análisis profundo de marcadores de orador por país")
    ap.add_argument("--country", required=True)
    ap.add_argument("--source", choices=["ocr", "extracted", "both"], default="both")
    ap.add_argument("--max-files", type=int, default=400)
    ap.add_argument("--min-honorific-freq", type=int, default=5)
    args = ap.parse_args()

    src = BASE_DIR / "source" / args.country
    files: list[Path] = []
    if args.source in ("ocr", "both"):
        files += list((src / "ocr").rglob("page_*.txt"))
    if args.source in ("extracted", "both"):
        files += list((src / "extracted").glob("*.txt"))
    if not files:
        print(f"ERROR: sin archivos en source/{args.country}/(ocr|extracted)")
        sys.exit(1)
    # Muestreo uniforme a lo largo del corpus (cubre todas las eras)
    files.sort()
    if len(files) > args.max_files:
        step = len(files) / args.max_files
        files = [files[int(i * step)] for i in range(args.max_files)]

    first_token = Counter()       # honorífico candidato (1er token)
    two_token = Counter()         # honorífico de 2 tokens (EL SEÑOR, O SR.)
    terminators = Counter()
    examples_term = {}
    candidates = 0

    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for line in text.split("\n"):
            s = line.strip()
            if len(s) < 8 or len(s) > 200:
                continue
            m = CANDIDATE.match(s)
            if not m:
                continue
            # Exigir PROSA en la intervención (minúsculas) → excluye cabeceras en mayúsculas
            if not _HAS_LOWER.search(m.group("rest")):
                continue
            head = m.group("head")
            toks = head.split()
            # Un marcador real tiene honorífico + nombre = ≥2 tokens en mayúscula, primer
            # token ≥2 letras. Excluye frases que empiezan con una sola mayúscula
            # ("A las 15 horas…", "Biblioteca…" → head de 1 letra).
            if len(toks) < 2 or len(toks[0].rstrip(".")) < 2:
                continue
            # Conservar la ñ y la grafía original (en mayúsculas) para VER variantes OCR distintas
            # (SEÑOR vs SEROR vs SERÑOR no deben colapsarse).
            t0 = toks[0].upper().rstrip(".")
            candidates += 1
            first_token[t0] += 1
            if len(toks) >= 2:
                two_token[f"{t0} {toks[1].upper().rstrip('.')}"] += 1
            term_class = classify_terminator(m.group("term"))
            terminators[term_class] += 1
            if term_class not in examples_term:
                examples_term[term_class] = s[:75]

    print(f"Análisis de marcadores — {args.country.upper()}  "
          f"({len(files)} archivos, {candidates:,} líneas candidatas)\n")

    known_norm = {_norm(h) for h in KNOWN_HONORIFICS}

    # 1. Honoríficos (tokens iniciales frecuentes, grafía original → variantes OCR visibles)
    print("── HONORÍFICOS detectados (1er token, freq ≥ {}) ──".format(args.min_honorific_freq))
    honorifics = [(t, c) for t, c in first_token.most_common(40) if c >= args.min_honorific_freq]
    for t, c in honorifics[:20]:
        tag = "conocido" if _norm(t) in known_norm else "?"
        print(f"  {c:>6}  {t:<14} [{tag}]")

    # 2. Variantes de género presentes (suma todas las grafías que normalizan al mismo honorífico)
    print("\n── VARIANTES DE GÉNERO presentes ──")
    def freq_norm(target_norm):
        return sum(c for t, c in first_token.items() if _norm(t) == target_norm)
    for masc, fem in GENDER_PAIRS:
        cm, cf = freq_norm(_norm(masc)), freq_norm(_norm(fem))
        if cm or cf:
            warn = ("  ⚠ sin femenino (¿faltan diputadas o se omite el género?)" if cf == 0 and cm else
                    "  ⚠ sin masculino" if cm == 0 and cf else "")
            print(f"  {masc}({cm}) / {fem}({cf}){warn}")

    # 3. Terminadores
    print("\n── TERMINADORES (separador marcador→intervención) ──")
    for t, c in terminators.most_common():
        pct = c / candidates * 100 if candidates else 0
        print(f"  {c:>6} ({pct:>4.1f}%)  {t:<22} ej: {examples_term[t]!r}")

    # 4. Errores / variaciones de OCR o taquígrafo (variante rara ≈ honorífico común, dist edición)
    print("\n── ERRORES / VARIACIONES probables (honorífico raro ≈ uno común) ──")
    flagged = 0
    for t, c in sorted(first_token.items(), key=lambda x: -x[1]):
        tn = _norm(t)
        if c < 2 or tn in known_norm or len(tn) < 4:
            continue
        # Honorífico común MÁS CERCANO (distancia mínima), no el primero que cumpla el umbral
        best_h, best_d = None, 99
        for h in known_norm:
            if abs(len(tn) - len(h)) > 2:
                continue
            d = _edit_distance(tn, h)
            if d < best_d:
                best_h, best_d = h, d
        if best_h and 1 <= best_d <= 2:
            print(f"  {c:>4}  {t:<14} ≈ {best_h}  (dist {best_d}) → normalizar antes del tagging")
            flagged += 1
    if not flagged:
        print("  (ninguna variante sospechosa frecuente)")

    # 5. Sugerencia de patrones para el config (honoríficos canónicos cuya forma normalizada
    #    aparece entre los detectados — preserva la grafía correcta SEÑOR/SEÑORA, no la del OCR)
    detected_norm = {_norm(t) for t, _ in honorifics}
    canon = [h for h in KNOWN_HONORIFICS if _norm(h) in detected_norm]
    hon_alt = "|".join(canon) if canon else "SEÑOR|SEÑORA"
    print("\n── SUGERENCIA para country_config ──")
    print("  # Verificar/ajustar manualmente. Guion [-–—] + espacio opcional; el OCR varía.")
    print(f'  speaker_tag_patterns:')
    print(f'    - "^(?:{hon_alt})\\\\s+([A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ\\\\s]+?)(?:\\\\s*\\\\([^)]+\\\\))?\\\\.\\\\s*[-–—]"')
    print(f'  speaker_loose_pattern:')
    print(f'    "^(?P<name>(?:{hon_alt})\\\\s+[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ.\\\\s]+?)'
          f'(?:\\\\s*\\\\([^)]*\\\\))?(?=\\\\s*[.:\\\\-–—]|\\\\s+[¿¡A-ZÁÉÍÓÚÜÑ])"')


if __name__ == "__main__":
    main()
