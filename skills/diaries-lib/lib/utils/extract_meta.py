#!/usr/bin/env python3
"""
Extract session metadata from corrected text using config regex patterns.

CLI:
    python extract_meta.py --input <path> --config <yaml_path> \
        --session-id <id> --country <iso2>

Output: JSON to stdout (no file written; caller handles persistence).
"""
import sys
import json
import argparse
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

# ── Month tables (Spanish + Portuguese) ──────────────────────────────────────
_MONTHS_ES = {
    # Spanish full
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9,  # "setiembre": grafía rioplatense (UY/AR) sin 'p'
    "octubre": 10, "noviembre": 11, "diciembre": 12,
    # Spanish abbreviated
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
    # Portuguese full
    "janeiro": 1, "fevereiro": 2, "março": 3,
    "abril": 4, "maio": 5, "junho": 6, "julho": 7,
    "agosto": 8, "setembro": 9, "outubro": 10,
    "novembro": 11, "dezembro": 12,
    # Portuguese abbreviated
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}

_SESSION_TYPES = {
    "ordinaria": "ordinaria",
    "extraordinaria": "extraordinaria",
    "solemne": "solemne",
    "especial": "especial",
    "plenaria": "plenaria",
    # Portuguese variants
    "ordinária": "ordinaria",
    "extraordinária": "extraordinaria",
    "solene": "solemne",
    "plenária": "plenaria",
    "reunião plenária": "plenaria",
}


# ── date parsing ─────────────────────────────────────────────────────────────

def _try_dateparser(date_str: str) -> str | None:
    """Try using the dateparser library (optional dependency)."""
    try:
        import dateparser
        parsed = dateparser.parse(date_str, languages=["es"])
        if parsed:
            return parsed.strftime("%Y-%m-%d")
    except ImportError:
        pass
    return None


# ── día en PALABRAS (actas mecanografiadas antiguas: "FEBRERO OCHO DE 1985") ──
_ES_DAY_WORDS = {
    "primero": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
    "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13,
    "catorce": 14, "quince": 15, "dieciseis": 16, "dieciséis": 16, "diecisiete": 17,
    "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veintiuno": 21, "veintiun": 21,
    "veintidos": 22, "veintidós": 22, "veintitres": 23, "veintitrés": 23,
    "veinticuatro": 24, "veinticinco": 25, "veintiseis": 26, "veintiséis": 26,
    "veintisiete": 27, "veintiocho": 28, "veintinueve": 29, "treinta": 30,
}


_ES_CARDINAL = {
    "cero": 0, "un": 1, "uno": 1, "primero": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12,
    "trece": 13, "catorce": 14, "quince": 15, "dieciseis": 16, "dieciséis": 16,
    "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veintiuno": 21,
    "veintiun": 21, "veintidos": 22, "veintidós": 22, "veintitres": 23, "veintitrés": 23,
    "veinticuatro": 24, "veinticinco": 25, "veintiseis": 26, "veintiséis": 26,
    "veintisiete": 27, "veintiocho": 28, "veintinueve": 29, "treinta": 30, "cuarenta": 40,
    "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90,
    "cien": 100, "ciento": 100, "doscientos": 200, "trescientos": 300, "cuatrocientos": 400,
    "quinientos": 500, "seiscientos": 600, "setecientos": 700, "ochocientos": 800,
    "novecientos": 900, "mil": 1000,
}


def _parse_es_cardinal(phrase: str) -> int | None:
    """'CUARENTA Y NUEVE'→49, 'VEINTE Y SEIS'→26 (variante EC), 'CIENTO CUARENTA'→140.
    Devuelve None si algún token NO es un numeral: así se rechaza el ruido del cabecero
    ('CONGRESO NACIONAL DEL ECUADOR') sin necesidad de listas negras."""
    if not phrase:
        return None
    toks = [t for t in re.split(r"[\s\-]+", phrase.lower().strip(" .,:;")) if t and t != "y"]
    if not toks or len(toks) > 5:
        return None
    total = 0
    for t in toks:
        v = _ES_CARDINAL.get(t)
        if v is None:
            return None                      # un token no-numeral invalida la frase entera
        total += v
    return total if 0 < total < 2000 else None


def _fuzzy_month(token: str) -> int | None:
    """Mes degradado por OCR ('SEPTIMERE', 'AmrxL') → número de mes, o None si es AMBIGUO.

    El vocabulario es cerrado (12 meses), pero eso NO basta: varios nombres están a distancia
    de edición mínima entre sí ('junio'/'julio' = 1, 'mayo'/'marzo' = 2). Adivinar mal el mes
    corrompe la fecha EN SILENCIO, mientras que no adivinarla la manda a FLAG y la revisa una
    persona. Por eso se exige un GANADOR CLARO: el mejor número de mes debe superar al segundo
    por un margen >= 2 (mismo criterio que match.ambiguity_margin del pipeline). Los alias del
    mismo mes ('septiembre'/'setiembre' → 9) no compiten entre sí porque se agrupa por NÚMERO.
    """
    t = (token or "").lower().strip(".,;:()")
    if len(t) < 3:
        return None
    if t in _MONTHS_ES:
        return _MONTHS_ES[t]
    best_by_num: dict[int, int] = {}
    for name, num in _MONTHS_ES.items():
        if len(name) < 4 or abs(len(name) - len(t)) > 3:
            continue
        prev = list(range(len(name) + 1))          # Levenshtein compacto
        for i, ca in enumerate(t, 1):
            cur = [i]
            for j, cb in enumerate(name, 1):
                cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
            prev = cur
        d = prev[-1]
        if d < best_by_num.get(num, 99):
            best_by_num[num] = d
    if not best_by_num:
        return None
    ranked = sorted(best_by_num.items(), key=lambda kv: kv[1])
    (num, d) = ranked[0]
    if d > max(2, len(t) // 2):                    # demasiado lejos de cualquier mes
        return None
    if len(ranked) > 1 and ranked[1][1] - d < 2:   # sin ganador claro → no adivinar
        return None
    return num


def _parse_date_es(date_str: str, fuzzy_month: bool = False) -> str | None:
    """
    Manual Spanish date parsing.
    Handles: '15 de enero de 2023', 'enero 15, 2023', '15/01/2023', '2023-01-15',
    'NOVIEMBRE 12 DEL 2007' (mes-primero + 'del'), '2 de Octubre de 1.979' (año con punto
    de millar) y 'FEBRERO OCHO DE 1985' / 'VEINTIUNO DE FEBRERO DE 1989' (día en palabras).
    `fuzzy_month=True` acepta el mes degradado por OCR (vocabulario cerrado; ver _fuzzy_month).
    """
    if not date_str:
        return None

    date_str = date_str.strip()
    # Año con punto de millar ('1.979' → '1979'): habitual en actas mecanografiadas antiguas.
    date_str = re.sub(r"\b([12])\.(\d{3})\b", r"\1\2", date_str)

    def _month(tok):
        return _MONTHS_ES.get(tok) or (_fuzzy_month(tok) if fuzzy_month else None)

    # Try dateparser first (richer support)
    result = _try_dateparser(date_str)
    if result:
        return result

    # ISO format
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", date_str)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # DD/MM/YYYY or DD-MM-YYYY
    m = re.match(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", date_str)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"

    # '15 de enero de 2023' / '15 enero 2023' / '1º de abril de 1986' (ordinal del día)
    # / 'TRECE (13) DE JUNIO DEL 2001' (día en palabras + dígitos entre paréntesis, estilo DO)
    # tolera ordinal '(1ro.)', espacio '(8 )' y doble paréntesis '(14) )'
    m = re.match(
        # el ordinal del día '1º' llega del OCR como '1?', '1*', '1°', '1o' → clase tolerante
        r"(?:[a-záéíóúü]+[\s,]+)*\(?\s*(\d{1,2})[a-zº°ª?*.,)]*[\s,)]*(?:de\s+)?([a-záéíóú]+)(?:\s+del?)?\s+(\d{4})",
        date_str.lower(),
    )
    if m:
        day, month_str, year = m.group(1), m.group(2), m.group(3)
        month = _month(month_str)
        if month:
            return f"{year}-{month:02d}-{int(day):02d}"

    # 'enero 15, 2023' / 'ENERO 15 DE 2023' (cabecera AR/MX mes-primero) / 'NOVIEMBRE 12 DEL 2007'
    # (EC: el conector puede ser 'de' O 'del' — sin 'l' opcional la fecha se perdía entera)
    m = re.match(r"([a-záéíóú]+)\s+(\d{1,2})[º°ªo.,]*\s*(?:de[l]?\s+)?[,\s]*(\d{4})",
                 date_str.lower())
    if m:
        month = _month(m.group(1))
        if month:
            return f"{m.group(3)}-{month:02d}-{int(m.group(2)):02d}"

    # 'septiembre 19/85' / 'noviembre 10/83' — mes + día/AÑO-DE-2-DÍGITOS (actas EC 1980s).
    # Ventana de siglo: >=79 → 19xx, si no 20xx (el corpus va de 1979 a 2026).
    m = re.match(r"([a-záéíóú]+)\s+(\d{1,2})\s*/\s*(\d{2})\b", date_str.lower())
    if m:
        month = _month(m.group(1))
        if month:
            yy = int(m.group(3))
            year = 1900 + yy if yy >= 79 else 2000 + yy
            return f"{year}-{month:02d}-{int(m.group(2)):02d}"

    # '4 DE SEPTIEMBRE DE (VESPERTINA) 1.980' — texto interpolado (tipo de sesión) entre el
    # conector y el año. Se permite un tramo SIN dígitos para no capturar un año ajeno.
    m = re.match(
        r"(?:[a-záéíóúü]+[\s,]+)*(\d{1,2})[a-zº°ª?*.,)]*\s*(?:de\s+)?([a-záéíóú]+)\s+de\s+"
        r"[^\d\n]{1,20}([12]\d{3})",
        date_str.lower(),
    )
    if m:
        month = _month(m.group(2))
        if month:
            return f"{m.group(3)}-{month:02d}-{int(m.group(1)):02d}"

    # ── día en PALABRAS ──
    low = date_str.lower()
    dw = "|".join(sorted(_ES_DAY_WORDS, key=len, reverse=True))
    # mes-primero: 'FEBRERO OCHO DE 1985'
    m = re.match(rf"([a-záéíóú]+)\s+({dw})\b(?:\s+de[l]?)?\s+(\d{{4}})", low)
    if m:
        month = _month(m.group(1))
        if month:
            return f"{m.group(3)}-{month:02d}-{_ES_DAY_WORDS[m.group(2)]:02d}"
    # día-primero: 'VEINTIUNO DE FEBRERO DE 1989'
    m = re.match(rf"(?:[a-záéíóú]+\s+)*?({dw})\s+de\s+([a-záéíóú]+)(?:\s+de[l]?)?\s+(\d{{4}})", low)
    if m:
        month = _month(m.group(2))
        if month:
            return f"{m.group(3)}-{month:02d}-{_ES_DAY_WORDS[m.group(1)]:02d}"

    return None


# ── extraction logic ──────────────────────────────────────────────────────────

def extract_meta(text: str, config: dict, session_id: str, country: str, source_file: str) -> dict:
    lines = text.split("\n")
    # ⚠⚠ LA VENTANA DE CABECERA ES POR PAÍS (meta.head_lines · meta.tail_lines).
    #   Estaba fija en 30 líneas, y eso hace que en un acta cuya página 1 empieza por el folio
    #   y el pase de lista —líneas cortas— la FECHA caiga fuera de la ventana. Entonces gana la
    #   de la COLA, que en PE anuncia la sesión SIGUIENTE: «viernes 18 de octubre de 1996» en
    #   un acta del 17. Medido en PE: 109 sesiones con la fecha adelantada un día, todas con
    #   date_source=text, y la fecha correcta presente en la posición ~1.233 del documento.
    #   El default (30/10) se conserva, así que ningún país cambia si no lo declara.
    _mcfg = (config.get("meta") or {})
    head_lines = lines[:int(_mcfg.get("head_lines", 30))]
    tail_lines = lines[-int(_mcfg.get("tail_lines", 10)):]
    search_lines = head_lines + tail_lines
    search_text = "\n".join(search_lines)

    fields_found: list[str] = []
    fields_missing: list[str] = []

    # ── date ──
    # GARANTÍA: la fecha del TEXTO (fórmula de cabecera de la sesión) es autoritativa.
    # NUNCA se usa silenciosamente la fecha del nombre de archivo. La fecha del session_id
    # solo se usa como último recurso EXPLÍCITO (date_source="filename_fallback") o para
    # validación cruzada; cualquier discrepancia o fallback baja la confianza → FLAG.
    date_val = None
    date_source = "missing"
    date_mismatch = False

    # Fecha implícita en el session_id (YYYY-MM-DD), si la hay — solo para validar/fallback
    m_sid = re.match(r"(\d{4})-(\d{2})-(\d{2})", session_id)
    filename_date = f"{m_sid.group(1)}-{m_sid.group(2)}-{m_sid.group(3)}" if m_sid else None
    if not filename_date:
        # session_id con fecha compacta (ej. AR: diario_YYYYMMDD{n}) — validar mes/día
        m8 = re.search(r"(\d{4})(\d{2})(\d{2})", session_id)
        if m8 and 1 <= int(m8.group(2)) <= 12 and 1 <= int(m8.group(3)) <= 31:
            filename_date = f"{m8.group(1)}-{m8.group(2)}-{m8.group(3)}"

    date_regex = config.get("session_date_regex")
    # meta.fuzzy_month: acepta el nombre de mes degradado por OCR ('SEPTIMERE'→septiembre)
    # SOLO si hay un ganador claro (ver _fuzzy_month). Activar en corpus escaneados antiguos.
    fuzzy_m = bool((config.get("meta", {}) or {}).get("fuzzy_month", False))
    # meta.date_year_range: [min, max] plausible del corpus. Descarta años imposibles del OCR
    # ('2600' por 2000, '2082' por 2002) y las fechas de actas/leyes CITADAS de otra época,
    # y sigue buscando en las coincidencias siguientes en vez de rendirse con la primera.
    yr_range = (config.get("meta", {}) or {}).get("date_year_range") or None
    text_date = None
    if date_regex:
        for m in re.finditer(date_regex, search_text, re.IGNORECASE | re.MULTILINE):
            raw_date = m.group(1) if m.lastindex else m.group(0)
            cand = _parse_date_es(raw_date, fuzzy_month=fuzzy_m)
            if not cand:
                continue
            if yr_range:
                yy = int(cand[:4])
                if not (int(yr_range[0]) <= yy <= int(yr_range[1])):
                    continue
            text_date = cand
            break

    if text_date:
        date_val = text_date
        date_source = "text"
        fields_found.append("date")
        # Validación cruzada con el nombre de archivo
        if filename_date and filename_date != text_date:
            date_mismatch = True
            fields_missing.append("date_mismatch")  # baja confianza → revisión
    elif filename_date:
        # Último recurso EXPLÍCITO: el texto no dio fecha. NO es silencioso: se marca.
        date_val = filename_date
        date_source = "filename_fallback"
        fields_missing.append("date")  # cuenta como faltante → confianza baja → FLAG
    else:
        fields_missing.append("date")

    # ── session_number ──
    # Try regex against text first; if the regex looks like a filename pattern
    # (contains "POR_Diario" or similar), apply it against session_id instead.
    session_number = None
    session_num_regex = config.get("session_number_regex")
    if session_num_regex:
        # Detect filename-style regex (contains literal word chars common in IDs)
        _is_filename_re = bool(re.search(r'[A-Z]{2,}_[A-Z]', session_num_regex))
        search_target = session_id if _is_filename_re else search_text
        m = re.search(session_num_regex, search_target, re.IGNORECASE)
        if m:
            raw = (m.group(1) if m.lastindex else m.group(0)).strip(" .,-")
            # El esquema canónico admite número ENTERO **o ALFANUMÉRICO** ('12', '12A', '001O',
            # EC '146-C' / '005-AN-2025-2029'). Antes se forzaba int() y todo lo alfanumérico
            # caía a None: en EC eso perdía el nº de acta de casi toda la era moderna.
            if re.fullmatch(r"\d+", raw):
                session_number = int(raw)
                fields_found.append("session_number")
            elif re.match(r"\d", raw) and len(raw) <= 24:
                session_number = raw            # alfanumérico: se conserva tal cual
                fields_found.append("session_number")
            else:
                # Número EN PALABRAS ('ACTA No. CUARENTA Y NUEVE' → 49): habitual en actas
                # mecanografiadas antiguas. El parser devuelve None si algún token no es
                # numeral, así que el ruido del cabecero no cuela.
                session_number = _parse_es_cardinal(raw)
                if session_number is not None:
                    fields_found.append("session_number")
                else:
                    fields_missing.append("session_number")
        else:
            fields_missing.append("session_number")
    else:
        fields_missing.append("session_number")

    # ── session_type ──
    # keywords may be a flat list or a dict {canonical: [synonyms, ...]}
    session_type = None
    raw_keywords = config.get("session_type_keywords", {})
    if isinstance(raw_keywords, dict):
        kw_pairs = [(canonical, kw)
                    for canonical, synonyms in raw_keywords.items()
                    for kw in (synonyms if isinstance(synonyms, list) else [synonyms])]
    else:
        kw_pairs = [(kw, kw) for kw in raw_keywords]

    for canonical, kw in kw_pairs:
        if re.search(rf"\b{re.escape(kw.lower())}\b", search_text.lower()):
            session_type = _SESSION_TYPES.get(canonical.lower(),
                           _SESSION_TYPES.get(kw.lower(), canonical))
            fields_found.append("session_type")
            break
    else:
        session_type = "desconocida"
        fields_missing.append("session_type")

    # ── president ──
    # Searches for "Presidente: [honorifics] NAME" anywhere in the header lines —
    # handles cases where the tag is embedded mid-line (common in PT pre-tagged files).
    president = ""
    president_tag = config.get("president_tag", "")
    canonical = (config.get("meta") or {}).get("president_name_canonical", "")

    # Build an inline regex: "Presidente:" anywhere in a line, then optional honorifics, then name.
    # Captures everything up to a known terminator (Secretário, Vogai, pipe, comma, line-end).
    _PRES_INLINE_RE = re.compile(
        r'\b' + re.escape(president_tag) + r'\s*:\s*'
        r'(?:Ex\.?m[ao]s?\.?\s+)?(?:Sr\.?\s*[aª]?\s+)?'
        r'([A-ZÁÀÃÂÉÊÍÓÔÕÚÇ].+?)(?=\s+(?:Secret[aá]ri|Vogai|Deput)|[\|,;\n\r]|$)',
        re.IGNORECASE,
    ) if president_tag else None

    if president_tag:
        for line in search_lines:
            stripped = line.strip()
            # Try inline pattern first (handles "… Presidente: Ex.mo Sr. NAME …")
            if _PRES_INLINE_RE:
                m = _PRES_INLINE_RE.search(stripped)
                if m:
                    name = m.group(1).strip()
                    # Strip residual honorifics that slipped through
                    name = re.sub(r'^(?:Ex\.?m[ao]s?\.?\s+)?(?:Sr\.?\s*[aª]?\s+)?', '', name, flags=re.IGNORECASE).strip()
                    if len(name) > 3:
                        president = name
                        fields_found.append("president")
                        break
            # Fallback: line starts exactly with the president tag
            if stripped.lower().startswith(president_tag.lower()):
                after = stripped[len(president_tag):].strip().lstrip(":").strip()
                after = re.sub(r'^(?:Ex\.?m[ao]s?\.?\s+)?(?:Sr\.?[aª]?\s+)?', '', after, flags=re.IGNORECASE).strip()
                if len(after) > 3:
                    president = after
                    fields_found.append("president")
                    break
        if not president and canonical:
            president = canonical
            fields_found.append("president")
        elif not president:
            fields_missing.append("president")
    else:
        if canonical:
            president = canonical
            fields_found.append("president")
        else:
            fields_missing.append("president")

    # ── legislature ──
    # `legislature_periods`: lista de {from, to, name} — deriva el período legislativo de la
    # FECHA cuando el texto no lo nombra (caso habitual: la cabecera del acta no dice la
    # legislatura, pero el período constitucional es una función determinista de la fecha).
    # Tiene prioridad sobre el regex de texto porque es exacto y no depende del OCR.
    legislature = ""
    periods = config.get("legislature_periods") or []
    if periods and date_val and re.match(r"\d{4}-\d{2}-\d{2}", str(date_val)):
        for p in periods:
            if str(p.get("from", "")) <= date_val <= str(p.get("to", "9999-12-31")):
                legislature = str(p.get("name", ""))
                break
        if legislature:
            fields_found.append("legislature")
            return {
                "session_id": session_id, "date": date_val, "date_source": date_source,
                "date_mismatch": date_mismatch, "filename_date": filename_date,
                "session_number": session_number, "session_type": session_type,
                "president": president, "legislature": legislature,
                "country": country.upper(), "source_file": source_file,
                "fields_found": fields_found, "fields_missing": fields_missing,
            }

    legislature_regex = config.get("legislature_regex")
    if legislature_regex:
        m = re.search(legislature_regex, search_text, re.IGNORECASE | re.MULTILINE)
        if m:
            # primer grupo NO vacío: un regex con ALTERNATIVAS («LEGISLATURA 328a» |
            # «320a LEGISLATURA» | «LEGISLATURA EXTRAORDINARIA») captura en grupos distintos;
            # m.group(1) fijo devolvía None cuando ganaba la 2ª o 3ª (CL 2026-08-24)
            legislature = (next((g for g in m.groups() if g), m.group(0))
                           if m.lastindex else m.group(0))
            fields_found.append("legislature")
        else:
            # Fallback to literal value in config
            legislature = str(config.get("legislature", ""))
            if legislature:
                fields_found.append("legislature")
            else:
                fields_missing.append("legislature")
    else:
        legislature = str(config.get("legislature", ""))
        if legislature:
            fields_found.append("legislature")
        else:
            fields_missing.append("legislature")

    return {
        "session_id": session_id,
        "date": date_val,
        "date_source": date_source,          # "text" | "filename_fallback" | "missing"
        "date_mismatch": date_mismatch,      # True si texto ≠ nombre de archivo → revisar
        "filename_date": filename_date,      # para auditoría/revisión
        "session_number": session_number,
        "session_type": session_type,
        "president": president,
        "legislature": legislature,
        "country": country.upper(),
        "source_file": source_file,
        "fields_found": fields_found,
        "fields_missing": fields_missing,
    }


SIN_DATO = ("", None, "unknown")


def completar_desde_session_id(meta: dict, session_id: str, cfg: dict) -> list:
    """Rellena metadatos que el TEXTO no dio, leyéndolos del `session_id`.

    Muchas fuentes codifican en el nombre lo que el acta no repite: número de sesión, tipo y
    legislatura. En SV el nombre es `2014-01-16_2018-2021-Ordinaria-83` y el corpus actual
    tiene `session_number` al 100%, pero el texto no lo declara: sin esto, un reproceso lo
    perdería entero.

        session_id_fields:
          pattern: '(?P<legislature>\\d{4}-\\d{4})-(?P<session_type>[A-Za-z]+)-(?P<session_number>\\d+)$'

    ⚠ **Nunca sobrescribe lo que el texto SÍ declaró**, y **nunca aporta la fecha**: la fecha
    sale de la cabecera del acta, jamás del nombre de archivo, y esa regla no se relaja aquí
    (`feedback_meta_date_extraction`). Si se quisiera, tendría que declararse aparte y con
    motivo, como se hizo en PY.
    """
    cfgp = (cfg.get("session_id_fields") or {}).get("pattern")
    if not cfgp:
        return []
    import re as _re
    m = _re.search(cfgp, session_id)
    if not m:
        return []
    puestos = []
    for k, v in (m.groupdict() or {}).items():
        if k == "date" or not v:
            continue
        if meta.get(k) in SIN_DATO:
            meta[k] = v
            puestos.append(k)
    return puestos


def main():
    parser = argparse.ArgumentParser(description="Extract session metadata from text")
    parser.add_argument("--input", required=True, help="Corrected text file path")
    parser.add_argument("--config", required=True, help="YAML config file path")
    parser.add_argument("--session-id", required=True, dest="session_id")
    parser.add_argument("--country", required=True, help="ISO 2-letter country code")
    args = parser.parse_args()

    if not HAS_YAML:
        print(json.dumps({"status": "error", "error": "PyYAML not installed"}))
        sys.exit(1)

    input_path = Path(args.input)
    config_path = Path(args.config)

    if not input_path.exists():
        print(json.dumps({"status": "error", "error": f"Not found: {input_path}"}))
        sys.exit(1)
    if not config_path.exists():
        print(json.dumps({"status": "error", "error": f"Config not found: {config_path}"}))
        sys.exit(1)

    with config_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    text = input_path.read_text(encoding="utf-8")
    result = extract_meta(text, config, args.session_id, args.country, str(input_path))
    puestos = completar_desde_session_id(result, args.session_id, config)
    if puestos:
        result["desde_session_id"] = puestos     # queda auditable de dónde salió cada dato
    result["status"] = "ok"
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
