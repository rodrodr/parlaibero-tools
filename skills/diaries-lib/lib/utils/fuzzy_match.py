#!/usr/bin/env python3
"""
Fuzzy name matching con RapidFuzz para vincular speaker_raw → diputado. Sin LLM.

Mejoras (2026-06, tras evaluación de calidad):
  1. LIMPIEZA DE TÍTULOS/CARGOS antes de matchear ("DIPUTADO", "SEÑOR DIPUTADO", "Accidental"…).
  2. Matching contra NOMBRE COMPLETO y APELLIDOS (el speaker suele ser solo el apellido).
  3. SCORER token_set_ratio (maneja apellido-subconjunto; token_sort_ratio fallaba "PEREYRA"→"Juan Pereyra").
  4. FILTRO TEMPORAL: si el speaker trae fechas de sesión y el diputado tiene mandato
     [fecha_inicio, fecha_fin], solo son candidatos los diputados vigentes en esas fechas.
     Esto desambigua apellidos compartidos (en PY el 81% comparten apellido; "González" ×49).
  5. DETECCIÓN DE EMPATES: si 2+ diputados distintos empatan a score alto, NO se elige uno
     arbitrariamente → match_method="ambiguous" con la lista de candidatos para el paso LLM.
  6. Fix del bug de índice (se itera sobre objetos diputado, sin indexar listas desalineadas).

CLI:
    python fuzzy_match.py --names <json> --deputies <csv> --threshold 85 --output <json>
    # --names: lista de strings  O  lista de {"speaker_raw": str, "dates": ["YYYY-MM-DD", ...]}
"""
import sys
import json
import argparse
import csv
import re
import unicodedata
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from rapidfuzz.fuzz import token_set_ratio
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False


# Títulos/cargos a eliminar antes de matchear (orden no importa; se quitan como palabra completa).
# NO incluir partículas de apellido (de, del, la, los) ni iniciales.
_TITLES = [
    "senor diputado nacional", "senora diputada nacional", "senor diputado", "senora diputada",
    "diputado nacional", "diputada nacional", "el senor", "la senora",
    "diputado", "diputada", "senador", "senadora", "deputado", "deputada",
    "presidente", "presidenta", "vicepresidente", "vicepresidenta",
    "secretario", "secretaria", "prosecretario", "prosecretaria",
    "ministro", "ministra", "accidental", "suplente", "titular",
    "senor", "senora", "sr", "sra", "don", "dona",
    "excelentisimo", "honorable", "doctor", "doctora", "licenciado", "licenciada", "ing",
]
_TITLES_RE = re.compile(r"\b(?:" + "|".join(sorted(_TITLES, key=len, reverse=True)) + r")\b")


def _normalize_name(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _strip_titles(norm_s: str) -> str:
    """Quita títulos/cargos de un nombre YA normalizado. Si queda vacío, devuelve el original."""
    stripped = _TITLES_RE.sub(" ", norm_s)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return stripped if stripped else norm_s


def _parse_date(s: str):
    if not s:
        return None
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s.strip())
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.match(r"(\d{4})", s.strip())
    return date(int(m.group(1)), 1, 1) if m else None


def _load_names(names_arg: str):
    path = Path(names_arg)
    raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else json.loads(names_arg)
    # Normalizar a [{"speaker_raw": str, "dates": [date|None]}]
    out = []
    for item in raw:
        if isinstance(item, str):
            out.append({"speaker_raw": item, "dates": []})
        elif isinstance(item, dict):
            dates = [d for d in (_parse_date(x) for x in item.get("dates", [])) if d]
            out.append({"speaker_raw": item.get("speaker_raw", ""), "dates": dates})
    return out


def _load_deputies(csv_path: Path) -> list[dict]:
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        sample = f.read(2048)
        f.seek(0)
        try:
            sep = csv.Sniffer().sniff(sample, delimiters=";,\t|").delimiter
        except csv.Error:
            sep = ";"
        return list(csv.DictReader(f, delimiter=sep))


def _field(dep: dict, *names, default=""):
    """Búsqueda de campo robusta a mayúsculas/variantes."""
    lower = {k.lower().strip(): v for k, v in dep.items() if k}
    for n in names:
        if n.lower() in lower and lower[n.lower()]:
            return lower[n.lower()].strip()
    return default


def _build_index(deputies: list[dict]) -> list[dict]:
    """Índice de diputados con nombre completo, apellidos, id y mandato."""
    idx = []
    for dep in deputies:
        # ⚠ `speaker_name` va PRIMERO entre los alias: es la columna canónica de los padrones
        # publicados ({ISO2}_deputies.csv) y no estaba en la lista, así que en SV el matcher no
        # encontraba el nombre en ninguna fila y devolvía 993 sin vincular de 993 — un cero
        # limpio, sin error. `speaker_raw` cierra la cascada para los padrones que solo traen
        # la forma tal como aparece en el acta.
        full = _field(dep, "nombre_completo", "nombre completo", "full_name", "name", "nombre",
                      "speaker_name", "speaker_raw")
        apes = _field(dep, "apellidos", "apellido", "surname", "surnames")
        if not full and not apes:
            continue
        idx.append({
            "id_dep": _field(dep, "id_dep", "id", default=None) or None,
            "nombre_completo": full or apes,
            "full_norm": _normalize_name(full) if full else "",
            "ape_norm": _normalize_name(apes) if apes else "",
            "ini": _parse_date(_field(dep, "fecha_inicio", "fecha inicio", "start_date")),
            "fin": _parse_date(_field(dep, "fecha_fin", "fecha fin", "end_date")),
        })
    return idx


def _temporally_matches(dep: dict, dates: list) -> bool:
    """
    True SOLO si hay evidencia positiva de vigencia: hay fechas de sesión, el diputado tiene
    mandato registrado, y alguna fecha cae dentro. Se usa para DESEMPATAR, no para excluir
    (un dato de mandato imperfecto no debe perder un match único).
    """
    if not dates or dep["ini"] is None:
        return False
    fin = dep["fin"] or date(2100, 1, 1)
    return any(dep["ini"] <= d <= fin for d in dates)


def match_names(speakers: list[dict], deputies: list[dict],
                threshold: float = 85.0, ambiguity_margin: float = 4.0) -> tuple[list[dict], dict]:
    if not HAS_RAPIDFUZZ:
        raise ImportError("rapidfuzz package is required")

    index = _build_index(deputies)
    exact_by_full = {d["full_norm"]: d for d in index if d["full_norm"]}

    results = []
    stats = {"total": len(speakers), "exact": 0, "fuzzy": 0, "ambiguous": 0, "unmatched": 0}

    for sp in speakers:
        raw = sp["speaker_raw"]
        dates = sp.get("dates", [])
        clean = _strip_titles(_normalize_name(raw))

        # 1. Exact contra nombre completo
        if clean in exact_by_full:
            d = exact_by_full[clean]
            results.append(_row(raw, d, 100.0, "exact", 1.0))
            stats["exact"] += 1
            continue

        # 2. Puntuar TODOS los candidatos (sin excluir por tiempo) con token_set_ratio contra el
        #    NOMBRE COMPLETO. Esto maneja el apellido-solo (subconjunto → 100) Y penaliza el nombre
        #    de pila erróneo ("persio da silva" vs "lorenzo silva" = 57). NO se matchea contra el
        #    campo apellidos por separado: daba 100 a cualquier speaker que contuviera ese apellido
        #    (falso positivo "Persio Da Silva" → "Lorenzo Silva"). Fallback a apellidos solo si no
        #    hay nombre completo.
        scored = []
        for d in index:
            target = d["full_norm"] or d["ape_norm"]
            if not target:
                continue
            score = token_set_ratio(clean, target)
            if score >= threshold:
                scored.append((score, d))

        if not scored:
            results.append(_row(raw, None, 0.0, "unmatched", 0.0))
            stats["unmatched"] += 1
            continue

        scored.sort(key=lambda x: x[0], reverse=True)
        best_score = scored[0][0]
        # Candidatos empatados (dentro del margen del mejor), agrupados por id_dep distinto
        tied = [(sc, d) for sc, d in scored if sc >= best_score - ambiguity_margin]
        tied_ids = {d["id_dep"] for sc, d in tied}

        if len(tied_ids) <= 1:
            # Ganador claro (o un único diputado) → NUNCA se pierde por datos de mandato
            best = scored[0][1]
            results.append(_row(raw, best, best_score, "fuzzy", round(best_score / 100.0, 4)))
            stats["fuzzy"] += 1
            continue

        # Empate real → DESEMPATAR por vigencia temporal (no excluir, solo elegir)
        temporally = [(sc, d) for sc, d in tied if _temporally_matches(d, dates)]
        temporally_ids = {d["id_dep"] for sc, d in temporally}
        if len(temporally_ids) == 1:
            sc, d = max(temporally, key=lambda x: x[0])
            row = _row(raw, d, sc, "fuzzy", round(min(sc, 95) / 100.0, 4))
            row["notas"] = "desambiguado por fecha de sesión (mandato)"
            results.append(row)
            stats["fuzzy"] += 1
            continue

        # Sigue ambiguo (varios vigentes o sin datos temporales) → candidatos para el LLM
        seen, cands = set(), []
        for sc, d in tied:
            if d["id_dep"] in seen:
                continue
            seen.add(d["id_dep"])
            cands.append({"id_dep": d["id_dep"], "nombre_completo": d["nombre_completo"],
                          "score": round(sc, 1), "vigente": _temporally_matches(d, dates)})
        row = _row(raw, None, best_score, "ambiguous", round(best_score / 100.0, 4))
        row["candidates"] = cands[:6]
        row["notas"] = f"{len(tied_ids)} candidatos empatados (desambiguar por contexto)"
        results.append(row)
        stats["ambiguous"] += 1

    return results, stats


def _row(raw, dep, score, method, conf):
    return {
        "speaker_raw": raw,
        "id_dep": dep["id_dep"] if dep else None,
        "nombre_completo": dep["nombre_completo"] if dep else None,
        "similarity_score": round(score, 2),
        "match_method": method,
        "confidence": conf,
    }


def main():
    parser = argparse.ArgumentParser(description="Fuzzy name matching con desambiguación temporal")
    parser.add_argument("--names", required=True, help="JSON: lista de strings o de {speaker_raw, dates}")
    parser.add_argument("--deputies", required=True, help="CSV de diputados")
    parser.add_argument("--threshold", type=float, default=85.0, help="Umbral token_set_ratio (default 85)")
    parser.add_argument("--ambiguity-margin", type=float, default=4.0,
                        help="Margen para considerar empate entre candidatos (default 4)")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if not HAS_RAPIDFUZZ:
        print(json.dumps({"status": "error", "error": "rapidfuzz not installed"})); sys.exit(1)

    deputies_path = Path(args.deputies)
    if not deputies_path.exists():
        print(json.dumps({"status": "error", "error": f"Not found: {deputies_path}"})); sys.exit(1)

    try:
        speakers = _load_names(args.names)
    except (json.JSONDecodeError, FileNotFoundError) as exc:
        print(json.dumps({"status": "error", "error": f"load names: {exc}"})); sys.exit(1)

    deputies = _load_deputies(deputies_path)
    results, stats = match_names(speakers, deputies,
                                 threshold=args.threshold, ambiguity_margin=args.ambiguity_margin)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    stats["output_path"] = str(out)
    stats["status"] = "ok"
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
