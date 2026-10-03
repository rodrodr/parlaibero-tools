#!/usr/bin/env python3
"""
Speaker tagging con criterio de DOS NIVELES (general para todos los países):

  NIVEL 1 — ESTRICTO: patrones canónicos de `speaker_tag_patterns` (regex del config).
            Coinciden con el marcador inequívoco (ej. "SEÑOR APELLIDO.-"). Tag directo.

  NIVEL 2 — PROBABILÍSTICO: para líneas que NO matchean el estricto pero parecen orador.
            Un detector LAXO (`speaker_loose_pattern`) captura honorífico + nombre SIN exigir
            terminador, y un scorer UNIVERSAL puntúa el caso límite por sus rasgos:
              - terminador: ".-/.—" (fuerte) | "." o "-" o ":" (medio) | nada (débil)
              - va seguido de texto de intervención (mayúscula/¿/¡)  → sube
              - paréntesis con nombre de pila                         → sube
              - nombre plausible (1-4 tokens en mayúsculas)           → sube
              - coincide con la base de diputados (si se pasa)        → sube fuerte
              - seguido de coma/minúscula (vocativo en texto corrido) → baja
            score >= speaker_score_threshold (def. 0.60) → se etiqueta.
            borderline [speaker_borderline_threshold, threshold) → NO se etiqueta, se
              registra como caso límite (señal para FLAG/revisión).

Por qué general: el OCR y los escaneos producen terminadores inconsistentes (.-, .—, ., :,
o ninguno) en TODOS los países. Un matcher estricto pierde ~5% de oradores en silencio.
El nivel 2 los recupera sin disparar falsos positivos (el honorífico en MAYÚSCULA a inicio
de línea ya discrimina del "señor" minúscula del texto corrido).

CLI:
    python tag_text.py --input <path> --config <yaml> --output <path> [--deputies <csv>]
"""
import sys
import csv
import json
import argparse
import re
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


# ── parámetros universales del scorer (sobreescribibles por config) ───────────

DEFAULT_SCORE_THRESHOLD = 0.60       # >= → etiquetar como orador
DEFAULT_BORDERLINE_THRESHOLD = 0.40  # [borderline, threshold) → caso límite (FLAG)

# Terminadores y su peso base (universal). Period+dash es el canónico; el resto, más débil.
_TERM_PERIOD_DASH = re.compile(r"^\s*\.\s*[-–—]")      # ".-"  ".—"  ".–"
_TERM_DASH_ONLY   = re.compile(r"^\s*[-–—]")           # "-" "—" "–"
_TERM_PERIOD_ONLY = re.compile(r"^\s*\.")                        # "."
_TERM_COLON       = re.compile(r"^\s*:")                         # ":"
_VOCATIVE_AFTER   = re.compile(r"^\s*[,;]|^\s+[a-záéíóúüñ]")     # ", le pido" / " continúa" → vocativo
_INTERVENTION_START = re.compile(r"^\s*[\.\:\-–—]*\s*[¿¡A-ZÁÉÍÓÚÜÑ]")  # texto de intervención


# ── helpers ──────────────────────────────────────────────────────────────────

_SUSPICIOUS_RE = re.compile(
    r"^[A-ZÁÉÍÓÚÜÑÀÃÂÊÍÔÕÇ\s]{4,}$|:$|"
    r"\bSr\.\b|\bSra\.\b|\bSEÑOR\b|\bSEÑORA\b|"
    r"\bSenhor\b|\bSenhora\b|\bDeputado\b|\bDeputada\b|\bPresidente\b",
    re.UNICODE | re.IGNORECASE,
)


def _is_suspicious(line: str) -> bool:
    return bool(_SUSPICIOUS_RE.search(line.strip()))


def _strip_prefixes(name: str, prefixes: list[str]) -> str:
    if name is None:
        return ""
    name = name.strip()
    if name.endswith(":"):
        name = name[:-1].strip()
    for prefix in prefixes:
        # case-insensitive: el honorífico varía de caja por era/OCR (CR: 'EL PRESIDENTE'
        # en mayúsculas ≤2012 vs 'Presidente' Title-Case ≥2013).
        if name.lower().startswith(prefix.lower()) and (
                len(name) == len(prefix)
                or not prefix[-1].isalpha()          # el prefijo cierra en ',' '.' etc.
                or not name[len(prefix)].isalpha()):  # frontera de palabra: 'doctor' no muerde 'doctora'
            stripped = name[len(prefix):].strip()
            if stripped:  # no vaciar marcadores de SOLO-rol ('EL PRESIDENTE:' → 'PRESIDENTE')
                name = stripped
    return name.strip()


def _norm(s: str) -> str:
    """Mayúsculas sin acentos para comparación de apellidos."""
    return "".join(c for c in unicodedata.normalize("NFD", s.upper())
                   if unicodedata.category(c) != "Mn")


def _load_deputy_surnames(deputies_csv: "Path | None") -> set[str]:
    """Conjunto de apellidos normalizados de la base de diputados (rasgo opcional del scorer)."""
    if not deputies_csv or not Path(deputies_csv).exists():
        return set()
    surnames: set[str] = set()
    try:
        with open(deputies_csv, encoding="utf-8") as f:
            reader = csv.reader(f, delimiter=";")
            for row in reader:
                for cell in row:
                    for tok in _norm(cell).split():
                        if len(tok) >= 3:
                            surnames.add(tok)
    except Exception:
        pass
    return surnames


_SIN_PAREN = re.compile(r"\([^)]*\)")


def _versal_dominante(nombre: str, ratio: float) -> bool:
    """¿El nombre es DOMINANTEMENTE versal, ignorando el paréntesis del cargo?

    El paréntesis va en minúsculas por convención tipográfica —«(de la Ponencia)»— y contarlo
    invierte la decisión: en ES declaraba prosa 408 marcadores reales. Se quita antes de medir.
    """
    letras = [c for c in _SIN_PAREN.sub("", nombre) if c.isalpha()]
    if not letras:
        return False
    return sum(1 for c in letras if c.isupper()) / len(letras) >= ratio


def score_candidate(name: str, rest: str, has_paren: bool, deputy_surnames: set[str]) -> float:
    """
    Puntúa un candidato a orador (nivel 2). `rest` = texto de la línea tras el nombre
    (incluye terminador + intervención). Devuelve score en [0, 1].
    """
    score = 0.0

    # 1) Fuerza del terminador
    if _TERM_PERIOD_DASH.match(rest):
        score += 0.55
    elif _TERM_DASH_ONLY.match(rest) or _TERM_PERIOD_ONLY.match(rest) or _TERM_COLON.match(rest):
        score += 0.40
    else:
        score += 0.15  # sin terminador claro

    # 2) Va seguido de texto de intervención (no vacío, empieza por mayúscula/¿/¡)
    if _VOCATIVE_AFTER.match(rest):
        score -= 0.30                       # ", le pido" / " continúa" → vocativo en texto corrido
    elif _INTERVENTION_START.match(rest) and len(rest.strip(" .:-–—")) > 0:
        score += 0.20

    # 3) Paréntesis con nombre de pila (rasgo típico del marcador)
    if has_paren:
        score += 0.10

    # 4) Plausibilidad del nombre: 1-4 tokens en mayúsculas, longitud razonable
    tokens = name.split()
    if 1 <= len(tokens) <= 4 and all(2 <= len(t) <= 20 for t in tokens):
        score += 0.10
    else:
        score -= 0.20

    # 5) Coincidencia con la base de diputados (señal fuerte, opcional)
    if deputy_surnames:
        name_toks = set(_norm(name).split())
        if name_toks & deputy_surnames:
            score += 0.30

    return max(0.0, min(1.0, score))


# ── tagging principal ─────────────────────────────────────────────────────────

def tag_text(text: str, config: dict, deputy_surnames: set[str] | None = None) -> tuple[str, dict]:
    deputy_surnames = deputy_surnames or set()
    patterns_cfg = config.get("speaker_tag_patterns", [])
    prefix_strip = config.get("speaker_prefix_strip", [])
    loose_pat_str = config.get("speaker_loose_pattern", "")
    score_threshold = float(config.get("speaker_score_threshold", DEFAULT_SCORE_THRESHOLD))
    borderline_threshold = float(config.get("speaker_borderline_threshold", DEFAULT_BORDERLINE_THRESHOLD))
    # 0 = desactivado (comportamiento previo). ES usa 0.60, calibrado sobre 14.280 cadenas reales.
    uppercase_min_ratio = float(config.get("speaker_uppercase_min_ratio", 0) or 0)

    # Compilar patrones estrictos (nivel 1), ordenados por prioridad
    compiled = []
    for i, entry in enumerate(patterns_cfg):
        if isinstance(entry, str):
            pattern, priority = entry, i
        elif isinstance(entry, dict):
            pattern, priority = entry.get("pattern", ""), entry.get("priority", 99)
        else:
            continue
        if pattern:
            try:
                compiled.append((re.compile(pattern), priority))
            except re.error as exc:
                sys.stderr.write(f"[tag_text] patrón inválido '{pattern}': {exc}\n")
    compiled.sort(key=lambda x: x[1])

    # Detector laxo (nivel 2). Debe capturar el nombre en grupo 'name'.
    loose_re = None
    if loose_pat_str:
        try:
            loose_re = re.compile(loose_pat_str)
        except re.error as exc:
            sys.stderr.write(f"[tag_text] speaker_loose_pattern inválido: {exc}\n")

    # ⚠ TOPE DE LONGITUD DEL ORADOR. Un marcador es un nombre o un cargo: no pasa de ~80
    # caracteres. Sin tope, un patrón con captura sin límite —`(.+?):`— o sin grupo —donde el
    # orador es la coincidencia entera— se traga todo hasta el siguiente ':' del documento.
    # En CO, con el texto aplanado, eso producía `speaker_raw` de hasta 6.310 caracteres: el
    # ÍNDICE completo de la Gaceta, con decenas de nombres dentro, cerrado por los dos puntos
    # de una hora («abriendo el registro a las 3:15»). Es un falso positivo que además
    # contamina la hoja de revisión del match, que es donde el investigador lo detectó.
    speaker_max = int(config.get("speaker_max_chars", 0) or 0)

    def _extract(m, group_name: str) -> str:
        if group_name in m.groupdict() and m.group(group_name) is not None:
            return m.group(group_name)
        # primer grupo capturado no-None (el nombre puede ser opcional en marcadores de rol)
        for g in (m.groups() or ()):
            if g is not None:
                return g
        return m.group(0)  # marcador de solo-rol sin nombre ('EL PRESIDENTE:')

    # El texto de intervención suele ir en la MISMA línea que el marcador
    # ("SEÑOR X.— Pido la palabra."). Hay que preservarlo: es el inicio de la intervención.
    _LEAD_TERM = re.compile(r"^\s*[.:\-–—]+\s*")

    def match_speaker(line: str) -> tuple[str | None, str, float, str]:
        """Devuelve (nombre|None, tipo, score, texto_inline_tras_el_marcador)."""
        s = line.strip()
        # Nivel 1 — estricto
        for (pat, _) in compiled:
            m = pat.match(s)
            if m:
                nombre = _extract(m, "speaker")
                # ⚠ GUARDARRAÍL DE VERSALES. Un patrón tolerante a la corrupción del OCR
                # —dígitos, comas, apóstrofos, minúsculas intrusas dentro de la palabra— es
                # imprescindible en corpus mal escaneados (ES 1977-1979: 13.485 marcadores
                # que el patrón limpio no veía), pero por sí solo captura PROSA:
                # «El señor Riestra dice que hay una laguna:» son 343 casos en ES.
                # El discriminador que sí funciona es la PROPORCIÓN de versales.
                #
                # ⚠⚠ El paréntesis del cargo va en minúsculas POR DISEÑO —«(de la Ponencia)»,
                # «(Fernández Ordóñez)»— así que se EXCLUYE del cálculo. Incluirlo declaraba
                # prosa 408 marcadores reales, y me llevó a creer que el patrón tenía falsos
                # positivos cuando tenía cero.
                if uppercase_min_ratio and not _versal_dominante(nombre, uppercase_min_ratio):
                    continue
                if speaker_max and len(nombre.strip()) > speaker_max:
                    continue          # no es un orador: ver el tope arriba
                inline = _LEAD_TERM.sub("", s[m.end():])
                return _strip_prefixes(nombre, prefix_strip), "strict", 1.0, inline
        # Nivel 2 — probabilístico
        if loose_re:
            m = loose_re.match(s)
            if m:
                name = _extract(m, "name").strip()
                has_paren = bool(re.search(r"\([^)]*\)", s[:m.end() + 25]))
                rest = s[m.end():]
                sc = score_candidate(name, rest, has_paren, deputy_surnames)
                clean = _strip_prefixes(name, prefix_strip)
                inline = _LEAD_TERM.sub("", rest)
                if sc >= score_threshold:
                    return clean, "prob", sc, inline
                if sc >= borderline_threshold:
                    return clean, "borderline", sc, inline
        return None, "", 0.0, ""

    lines = text.split("\n")
    output_parts: list[str] = []
    tagged_speakers: set[str] = set()
    total_interventions = 0
    n_strict = n_prob = 0
    borderline_cases: list[dict] = []
    untagged_spans: list[dict] = []

    current_speaker: str | None = None
    current_block: list[str] = []
    pre_speaker_lines: list[str] = []
    first_speaker_found = False

    def _flush_block():
        nonlocal current_speaker, current_block, total_interventions
        if current_speaker is not None and current_block:
            content = "\n".join(current_block).strip()
            output_parts.append(f'<int speaker="{current_speaker}">{content}</int>')
            total_interventions += 1
        current_block = []

    for line_idx, line in enumerate(lines):
        name, kind, score, inline = match_speaker(line)

        if kind == "borderline":
            # No se etiqueta: se registra como caso límite para revisión (FLAG).
            borderline_cases.append({"line": line_idx + 1, "score": round(score, 2),
                                     "candidate": name, "text": line.strip()[:90]})
            name = None  # tratar como texto normal

        if name is not None:
            if not first_speaker_found:
                output_parts.extend(pre_speaker_lines)
                first_speaker_found = True
            else:
                _flush_block()
            current_speaker = name
            tagged_speakers.add(name)
            # Preservar el texto de intervención que va en la misma línea que el marcador
            current_block = [inline] if inline.strip() else []
            if kind == "strict":
                n_strict += 1
            elif kind == "prob":
                n_prob += 1
        else:
            if not first_speaker_found:
                pre_speaker_lines.append(line)
            elif current_speaker is None:
                stripped = line.strip()
                if len(stripped) > 20:
                    untagged_spans.append({"line": line_idx + 1, "text": stripped[:100],
                                           "suspicious": _is_suspicious(stripped)})
                output_parts.append(line)
            else:
                current_block.append(line)

    _flush_block()
    if not first_speaker_found:
        output_parts.extend(pre_speaker_lines)

    output_text = "\n".join(output_parts)
    stats = {
        "tagged_speakers": len(tagged_speakers),
        "total_interventions": total_interventions,
        "strict_matches": n_strict,
        "probabilistic_matches": n_prob,
        "borderline_cases": borderline_cases,
        "n_borderline": len(borderline_cases),
        "untagged_spans": untagged_spans,
        "total_lines": len(lines),
    }
    return output_text, stats


def main():
    parser = argparse.ArgumentParser(description="Speaker tagging de dos niveles (estricto + probabilístico)")
    parser.add_argument("--input", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--deputies", default=None,
                        help="CSV de diputados (opcional): mejora el scoring de casos límite")
    args = parser.parse_args()

    if not HAS_YAML:
        print(json.dumps({"status": "error", "error": "PyYAML not installed"})); sys.exit(1)

    input_path, config_path, output_path = Path(args.input), Path(args.config), Path(args.output)
    if not input_path.exists():
        print(json.dumps({"status": "error", "error": f"Not found: {input_path}"})); sys.exit(1)
    if not config_path.exists():
        print(json.dumps({"status": "error", "error": f"Config not found: {config_path}"})); sys.exit(1)

    with config_path.open(encoding="utf-8") as f:
        config = yaml.safe_load(f)

    deputy_surnames = _load_deputy_surnames(Path(args.deputies)) if args.deputies else set()

    text = input_path.read_text(encoding="utf-8")
    tagged_text, stats = tag_text(text, config, deputy_surnames)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(tagged_text, encoding="utf-8")

    stats["status"] = "ok"
    stats["output"] = str(output_path)
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
