#!/usr/bin/env python3
"""Amputación de margen izquierdo en un corpus OCR (escaneos recortados en los que falta el
principio de cada línea de cuerpo).

⚠ **MIRA LA IMAGEN ANTES DE DOCUMENTAR NINGUNA CIFRA DE ESTE PROGRAMA.** ⚠
Ningún indicador de texto puede probar por sí solo que un escaneo esté recortado. Este mide bien
—se valida en §CONTROLES— pero su función es decirte DÓNDE mirar, no ahorrarte mirar.

MÉTODO
------
Para cada línea de cuerpo se toma su primera palabra y se clasifica en tres cajas EXCLUYENTES:

    (a) ES PALABRA                                    → benigno, línea normal
    (b) UNIDA AL FINAL DE LA LÍNEA ANTERIOR ES PALABRA → benigno, partición silábica sin guion
                                                         (`Aproba`/`da`, `legislado`/`res`)
    (c) NO es palabra, NO une, pero SÍ lo es al
        ANTEPONERLE 1-3 LETRAS                        → AMPUTACIÓN ← lo único que es daño

Solo (c) se reporta. El léxico de referencia (`lib/resources/lexico_es_ref.json`, 55.667 formas)
procede de corpus DIGITALES del propio proyecto —MX en HTML y CL en XML, exigiendo presencia en
ambos—, nunca de texto pasado por OCR: sin eso la medida sería circular.

HISTORIA — ESTE ARCHIVO MIDIÓ MAL DURANTE UNA SEMANA (corregido 2026-07-31)
--------------------------------------------------------------------------
La versión anterior contaba primeras palabras de **≤3 caracteres** que no estuviesen en una lista
de palabras cortas frecuentes. Falsa por dos motivos independientes:

  1. Confundía (b) con (c). La partición silábica sin guion es la convención habitual de las actas
     mecanografiadas y dispara el contador en TODO el corpus por igual.
  2. **Era ciega al fenómeno que decía medir.** La amputación no produce tokens cortos:
     `nosotros`→`osotros` (7), `juzgue`→`uzgue` (5), `hacerlo`→`acerlo` (6). El filtro `len<=3`
     los descarta a todos. Que devolviera cifras altas fue coincidencia, no señal.

Reportó **15,5% en EC 1979-93** y se documentó como «pérdida irrecuperable en 2.027 sesiones».
La medición correcta da **0,98% global y 60 sesiones**: un error de factor ~150 en el alcance.
Peor: sobre esa cifra falsa se rechazó el re-OCR con modelo de lenguaje, con el argumento de que
«inventaría los caracteres amputados» cuando no faltaba prácticamente ninguno — mientras el
problema real (tesseract ilegible en tipografía mecanografiada, ~24 errores por 62 palabras)
quedaba sin diagnosticar durante días.

Un segundo intento por geometría de píxel («tinta cerca del borde izquierdo») también falló: las
actas con MARCO IMPRESO tienen el filete a ~0,7% del ancho y el detector medía la raya del
formulario. Ambos fallos habrían caído a la primera si alguien hubiera rasterizado una página.

CONTROLES (obligatorios: sin ellos la cifra no significa nada)
-------------------------------------------------------------
Corpus donde el recorte es FÍSICAMENTE IMPOSIBLE porque nunca hubo escaneo (medidos 2026-07-31):

    MX (HTML)  0,06%   ·   CR (.docx)  0,02%      ← suelo verdadero del método
    CO (PDF)   0,75%   ·   AR (PDF)    1,45%      ← más alto: saltos de línea duros → (b) residual

Un corpus escaneado que caiga en ese rango **no tiene recorte apreciable**. EC dio 0,98%: dentro
del rango, pese a estar íntegramente escaneado. El daño real estaba concentrado en 60 sesiones de
6.075, no repartido por época.

Compara siempre contra dos controles digitales antes de afirmar que hay daño, y usa `--sessions`
para localizar las sesiones concretas: este defecto es de SESIÓN (papel mal colocado en el
escáner), no de década.

USO
---
    python measure_edge_loss.py --country ec
    python measure_edge_loss.py --country ec --sessions docs/ec/edge_loss_sessions.csv \\
                                --json docs/ec/edge_loss.json
    python measure_edge_loss.py --country mx --source extracted   # control sobre corpus digital

Se ejecuta desde la RAÍZ DEL PROYECTO (rutas de datos relativas a Path.cwd()).
"""
import os
import re
import csv
import json
import argparse
import unicodedata
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

_LEX_PATH = Path(__file__).resolve().parent.parent / "resources" / "lexico_es_ref.json"
_AB = "abcdefghijklmnopqrstuvwxyz"
_W = re.compile(r"[a-záéíóúüñ]+")
_YEAR_RE = re.compile(r"(1[89]\d{2}|20\d{2})")
LEX = None                     # se carga perezosamente y se hereda por fork en los workers


def _lex():
    global LEX
    if LEX is None:
        if not _LEX_PATH.exists():
            raise SystemExit(
                f"Falta el léxico de referencia en {_LEX_PATH}.\n"
                "Debe construirse desde corpus DIGITALES del proyecto (HTML/XML/docx), nunca desde\n"
                "texto OCR, exigiendo que cada forma aparezca en al menos dos países."
            )
        LEX = set(json.load(open(_LEX_PATH, encoding="utf-8")))
    return LEX


def norm(s):
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def clasifica(tok, prev_tail):
    """(a) palabra · (b) sílaba partida · (c) amputada · None = no evaluable."""
    lex = _lex()
    if len(tok) < 2 or len(tok) > 14:
        return None
    if tok in lex:
        return "a"
    if prev_tail and (prev_tail + tok) in lex:
        return "b"
    for c1 in _AB:                                   # ¿palabra si le devuelvo 1 letra?
        if c1 + tok in lex:
            return "c"
    for c1 in _AB:                                   # ¿y si le devuelvo 2?
        for c2 in _AB:
            if c1 + c2 + tok in lex:
                return "c"
    return None                                      # otro error de OCR: ni a favor ni en contra


def _scan_text(txt, tot, min_chars):
    prev = ""
    for ln in txt.splitlines():
        s = ln.strip()
        if len(s) < min_chars or not s[0].isalpha():
            prev = ""
            continue
        toks = _W.findall(norm(s))
        if not toks:
            prev = ""
            continue
        k = clasifica(toks[0], prev)
        if k:
            tot[k] += 1
        prev = toks[-1]


def _measure_one(args):
    """Una sesión: directorio de páginas OCR, o un único .txt extraído/corregido."""
    path, min_chars = args
    tot = defaultdict(int)
    p = Path(path)
    files = sorted(p.glob("page_*.txt")) if p.is_dir() else [p]
    for f in files:
        try:
            _scan_text(f.read_text(encoding="utf-8", errors="ignore"), tot, min_chars)
        except Exception:
            continue
    ev = tot["a"] + tot["b"] + tot["c"]
    return (p.name if p.is_dir() else p.stem), dict(tot), (tot["c"] / ev if ev else None)


def resolve_year(project: Path, iso: str, session_id: str):
    """Año de la sesión, por orden de fiabilidad: meta > destino del symlink > session_id."""
    meta = project / f"source/{iso}/meta/{session_id}.json"
    if meta.exists():
        try:
            date = str(json.loads(meta.read_text(encoding="utf-8")).get("date", ""))
            if len(date) >= 4 and date[:4].isdigit():
                return int(date[:4])
        except Exception:
            pass
    src = project / f"source/{iso}/raw/{session_id}.pdf"
    if src.is_symlink():
        head = os.readlink(src).split("/")[0]
        if head.isdigit() and len(head) == 4:
            return int(head)
    m = _YEAR_RE.search(session_id)
    return int(m.group(1)) if m else None


def main():
    ap = argparse.ArgumentParser(
        description="Amputación de margen izquierdo por descomposición léxica "
                    "(NO concluye recorte por sí solo: rasteriza y mira)")
    ap.add_argument("--country", required=True)
    ap.add_argument("--source", default="ocr", choices=["ocr", "extracted", "corrected"],
                    help="ocr = un directorio por sesión; extracted/corrected = un .txt por sesión")
    ap.add_argument("--min-line-chars", type=int, default=30)
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--flag-threshold", type=float, default=0.06,
                    help="tasa por sesión a partir de la cual se marca como afectada")
    ap.add_argument("--json", default=None)
    ap.add_argument("--sessions", default=None, help="CSV con las sesiones que superan el umbral")
    args = ap.parse_args()

    project, iso = Path.cwd(), args.country.lower()
    root = project / f"source/{iso}/{args.source}"
    if not root.is_dir():
        raise SystemExit(f"No existe {root}")
    targets = sorted(p for p in root.iterdir()
                     if (p.is_dir() if args.source == "ocr" else p.suffix == ".txt"))
    if not targets:
        raise SystemExit(f"Sin sesiones en {root}")
    _lex()

    res = {}
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for sid, tot, rate in ex.map(_measure_one,
                                     [(str(t), args.min_line_chars) for t in targets],
                                     chunksize=8):
            if rate is not None:
                res[sid] = {"year": resolve_year(project, iso, sid), "rate": rate, **tot}

    per = defaultdict(lambda: [0, 0, 0, 0])
    tot_c = tot_ev = 0
    for sid, r in res.items():
        ev = r["a"] + r["b"] + r["c"]
        tot_c += r["c"]
        tot_ev += ev
        p = per[r["year"]]
        p[0] += r["c"]; p[1] += ev; p[2] += 1
        if r["rate"] > args.flag_threshold:
            p[3] += 1

    print(f"AMPUTACIÓN DE MARGEN IZQUIERDO — {iso.upper()}  (fuente: {args.source})")
    print("⛔ Cifra orientativa: RASTERIZA UNA PÁGINA DE LAS SESIONES MARCADAS Y MÍRALA.")
    print("   Controles digitales (sin escaneo posible): MX 0,06% · CR 0,02% · CO 0,75% · AR 1,45%.")
    print("   Un corpus escaneado dentro de ese rango NO tiene recorte apreciable.\n")
    print(f"{'año':<7}{'sesiones':>9}{'amputación':>12}{'ses>umbral':>12}")
    for y in sorted(per, key=lambda v: (v is None, v)):
        c, ev, n, alt = per[y]
        bar = "█" * int((c / max(ev, 1)) * 300)
        print(f"{str(y):<7}{n:>9}{c/max(ev,1):>11.1%}{alt:>12}  {bar}")

    flagged = sorted(((r["rate"], s) for s, r in res.items() if r["rate"] > args.flag_threshold),
                     reverse=True)
    print(f"\nTOTAL: {tot_c:,}/{tot_ev:,} líneas = {tot_c/max(tot_ev,1):.2%}")
    print(f"Sesiones por encima del {args.flag_threshold:.0%}: {len(flagged)} de {len(res)} "
          f"({len(flagged)/max(len(res),1):.1%})")
    if flagged:
        print("Peores:", ", ".join(f"{s} ({r:.0%})" for r, s in flagged[:8]))
        print("→ Rasteriza una página de la primera y confirma el recorte antes de documentar.")

    if args.sessions:
        out = Path(args.sessions)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["session_id", "year", "amputation_rate", "lines_amputated",
                        "lines_evaluated", "severity"])
            for rate, sid in flagged:
                r = res[sid]
                w.writerow([sid, r["year"], f"{rate:.4f}", r["c"], r["a"] + r["b"] + r["c"],
                            "severa" if rate > 0.15 else ("alta" if rate > 0.10 else "moderada")])
        print(f"\nSesiones afectadas → {out}")

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "country": iso, "source": args.source,
            "metric": "left_edge_amputation_lexical_decomposition",
            "method": "primera palabra: (a) es palabra · (b) une con la linea anterior = particion "
                      "silabica · (c) solo lo es al anteponerle 1-3 letras = AMPUTACION",
            "controls_digital_corpora": {"mx_html": 0.0006, "cr_docx": 0.0002,
                                         "co_pdf": 0.0075, "ar_pdf": 0.0145},
            "total": {"sessions": len(res), "lines_evaluated": tot_ev, "amputated": tot_c,
                      "rate": round(tot_c / max(tot_ev, 1), 4)},
            "sessions_above_threshold": len(flagged),
            "by_year": {str(y): {"sessions": p[2], "lines": p[1], "amputated": p[0],
                                 "rate": round(p[0] / max(p[1], 1), 4),
                                 "sessions_above_threshold": p[3]}
                        for y, p in sorted(per.items(), key=lambda kv: (kv[0] is None, kv[0]))},
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON → {out}")


if __name__ == "__main__":
    main()
