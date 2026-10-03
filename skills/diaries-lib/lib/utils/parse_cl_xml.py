#!/usr/bin/env python3
"""
Parser del track XML de Chile (Cámara de Diputadas y Diputados) -> matriz de intervenciones.

El XML (boletin_ses_*.xml) ya viene TAGGED y MATCHED:
  <INTERVENCION_DIPUTADO DIPUTADO="Apellido, Nombre" DIPUTADOValue="<Id oficial>">...texto...
El DIPUTADOValue = <Id> oficial de la Cámara = id_dep (validado 100% contra deputies.csv).

GRANULARIDAD — una fila por TURNO (no por bloque):
  Cada bloque INTERVENCION_* se atribuye a un orador, pero su texto EMBEBE interjecciones de
  otros (sobre todo el Presidente: "Tiene la palabra"). Esas interjecciones NO están como bloques
  separados. Para fidelidad y consistencia con el track tradicional (que etiqueta cada "El señor
  X.-" como un turno), dividimos el texto del bloque por los marcadores inline y atribuimos cada
  segmento a su orador real, resuelto contra el ROSTER LOCAL de la sesión (apellido->id_dep
  construido desde los atributos de TODOS los bloques de esa sesión).

Salida: filas con el esquema canónico
  legislature, session_number, date, session_type, speaker_raw, id_dep, speaker_name, party, district, text
(district queda vacío: la fuente oficial no lo trae).

CLI:
  python parse_cl_xml.py --file source/cl/raw/xml/boletin_ses_2015-01-06_3169.xml   # 1 archivo -> stdout muestra
  python parse_cl_xml.py --all --workers 8 --out source/cl/matrix/interventions_xml.csv
  python parse_cl_xml.py --sample 3                                                  # 3 sesiones, inspección
"""
import argparse, csv, glob, re, sys, unicodedata
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from rapidfuzz import fuzz, process as rf_process

PROJECT = Path.cwd()
DEPUTIES = PROJECT / "source" / "cl" / "deputies" / "deputies.csv"
PERIODOS = PROJECT / "source" / "cl" / "deputies" / "periodos.xml"

# ── período legislativo por fecha (campo `legislature`) ───────────────────────
# En Chile la "legislatura" del esquema = PERÍODO LEGISLATIVO (mandato de 4 años, p.ej.
# "1990-1994"), NO el número de legislatura (319, 350…). Se deriva de la fecha de sesión
# vía periodos.xml (open-data Cámara). Fuente única y completa: corrige el código erróneo
# y los vacíos del header.
_PERIODS = None
def load_periodos():
    import xml.etree.ElementTree as ET
    out = []
    if not PERIODOS.exists():
        return out
    root = ET.parse(PERIODOS).getroot()
    for p in root:
        if p.tag.split("}")[-1] != "PeriodoLegislativo":
            continue
        nom = fi = ff = ""
        for c in p:
            t = c.tag.split("}")[-1]
            if t == "Nombre": nom = (c.text or "").strip()
            elif t == "FechaInicio": fi = (c.text or "")[:10]
            elif t == "FechaTermino": ff = (c.text or "")[:10]
        if nom and fi and ff:
            out.append((fi, ff, nom))
    return out

def period_for_date(date):
    global _PERIODS
    if _PERIODS is None:
        _PERIODS = load_periodos()
    if not date:
        return ""
    for fi, ff, nom in _PERIODS:
        if fi <= date <= ff:
            return nom
    return ""

CANON_COLS = ["legislature","session_number","date","session_type",
              "speaker_raw","id_dep","speaker_name","party","district","text","tipo"]

# ── normalización de apellidos para el roster ─────────────────────────────────
def norm_sur(s):
    s = unicodedata.normalize("NFD", (s or "").upper().strip())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")  # quita acentos
    s = s.replace(".", "").strip()
    return re.sub(r"\s+", " ", s)

# ── deputies.csv: id_dep -> (nombre_completo, [(ini,fin,partido)]) ────────────
def load_deputies():
    info = {}
    if not DEPUTIES.exists():
        return info
    for r in csv.DictReader(DEPUTIES.open(encoding="utf-8"), delimiter=";"):
        d = info.setdefault(r["id_dep"], {"name": r["nombre_completo"], "mil": []})
        if not d["name"]:
            d["name"] = r["nombre_completo"]
        d["mil"].append((r.get("fecha_inicio",""), r.get("fecha_fin",""), r.get("partido","")))
    return info

def party_at(dep, date):
    """Partido vigente en la fecha de sesión (YYYY-MM-DD)."""
    if not dep or not date:
        return ""
    cand = ""
    for ini, fin, part in dep["mil"]:
        if ini and fin and ini <= date <= fin:
            return part
        if part and not cand:
            cand = part   # fallback: primer partido conocido
    return cand

def load_dep_index():
    """Índice apellido(primer token) -> [(id_dep, nombre_norm, apellidos_norm, [(ini,fin),...])].
    Para resolver marcadores de diputados por apellido + fecha + nombre de pila. La clave es el
    PRIMER token del apellido; el apellido completo se guarda para desambiguar compuestos, y la
    búsqueda por token único permite resolver formato 'Nombre Apellido' y apellidos OCR-partidos."""
    idx = {}
    if not DEPUTIES.exists():
        return idx
    per_id = {}
    for r in csv.DictReader(DEPUTIES.open(encoding="utf-8"), delimiter=";"):
        ape = norm_sur(r.get("apellidos",""))
        if not ape:
            continue
        tok = ape.split(" ")[0]
        k = (tok, r["id_dep"])
        per_id.setdefault(k, [norm_sur(r.get("nombre","")), ape, []])
        per_id[k][2].append((r.get("fecha_inicio",""), r.get("fecha_fin","")))
    for (tok, idd), (nom, ape, spans) in per_id.items():
        idx.setdefault(tok, []).append((idd, nom, ape, spans))
    return idx

def _firstname_hint(role):
    """Extrae nombre de pila de un rol tipo 'don Sergio' / 'doña Natalia'."""
    m = re.search(r"do[ñn]a?\s+([A-Za-zÁÉÍÓÚÜÑáéíóúñ]+)", role or "")
    return norm_sur(m.group(1)) if m else ""

def resolve_by_date(idx, sur, date, role="", name_hint=""):
    """Resuelve apellido contra deputies.csv en 4 estrategias (única/fecha/nombre de pila):
      1) apellido completo/compuesto ("MUÑOZ BARRA")
      2) primer token como apellido ("LATORRE", "MUÑOZ" ambiguo -> desempata por nombre)
      3) formato 'Nombre Apellido(s)' era reciente ("GONZALO WINTER" -> apellido=último token, nombre=primero)
      4) apellido partido por OCR ("HORV ATH" -> juntar tokens = "HORVATH")"""
    S = norm_sur(sur)
    if not S:
        return ""
    toks = S.split()
    hint = norm_sur(name_hint) if name_hint else _firstname_hint(role)

    def pick(cands, fname=""):
        if not cands:
            return ""
        if len(cands) == 1:
            return cands[0][0]
        active = [c for c in cands if any(i and f and i <= date <= f for i, f in c[3])]
        pool = active if active else cands
        if len(pool) == 1:
            return pool[0][0]
        h = fname or hint
        if h:
            byn = [c[0] for c in pool if c[1] and (c[1].split(" ")[0] == h or c[1].startswith(h))]
            if len(byn) == 1:
                return byn[0]
        return ""

    first = idx.get(toks[0], [])
    # 1) apellido completo / compuesto
    if len(toks) > 1:
        comp = [c for c in first if c[2] == S or c[2].startswith(S + " ") or S.startswith(c[2] + " ")]
        r = pick(comp)
        if r:
            return r
    # 2) primer token como apellido
    r = pick(first, hint)
    if r:
        return r
    # 3) 'Nombre Apellido(s)': primer token = nombre de pila; probar el resto como apellido
    if len(toks) >= 2:
        for st in range(len(toks) - 1, 0, -1):
            cands = [c for c in idx.get(toks[st], []) if c[1] and c[1].split(" ")[0] == toks[0]]
            r = pick(cands, fname=toks[0])
            if r:
                return r
    # 4) apellido partido por OCR: juntar tokens
    if len(toks) > 1:
        r = pick(idx.get("".join(toks), []), hint)
        if r:
            return r
    return ""   # irresoluble -> sin id

# ── fecha FECHA_INICIO -> YYYY-MM-DD ──────────────────────────────────────────
# Discrepancias fecha-del-contenido vs fecha-del-nombre. NO se resuelven en el parser.
# ⚠ Con --workers>1 esta lista vive en CADA PROCESO HIJO y no llega al padre: sirve para
# inspección en modo --file/--sample, no como informe. El listado completo se genera
# aparte y vive en docs/cl/discrepancias_fecha_xml_vs_nombre.csv, y lo decide
# `audit_session_dates.py` por cronología contra las sesiones vecinas.
_DISCREPANCIAS = []

# ── ARBITRAJE DE FECHA · precomputado, global, no por archivo ────────────────
# La fecha correcta NO se puede decidir mirando un archivo aislado: hace falta ver a sus
# VECINAS. El XML trae `NUMERO` de sesión, que es secuencial en el tiempo dentro de cada
# legislatura, y eso da un árbitro independiente de las dos fechas en disputa.
#
# Medido sobre 3.183 sesiones con número: ordenando por número de sesión, la fecha del NOMBRE
# produce 78 inversiones cronológicas y la del CONTENIDO 125. De las 149 discrepancias, 54
# encajan solo con el nombre y 9 solo con el contenido. Es decir: **en este track el campo
# corrupto es `FECHA_INICIO`**, y el nombre de archivo es el más fiable de los dos — al revés
# de lo que dice la regla general del proyecto, que por eso se aplica MIDIENDO y no por norma.
#
# El mapa lo genera un paso aparte y vive en `source/cl/meta_xml/fechas_arbitradas.json`,
# con el motivo de cada decisión escrito para poder auditarla. Si no existe, el parser cae a
# la heurística simple.
_ARB = None
def _arbitradas():
    global _ARB
    if _ARB is None:
        p = PROJECT / "source" / "cl" / "meta_xml" / "fechas_arbitradas.json"
        try:
            import json as _j
            _ARB = _j.load(open(p, encoding="utf-8"))
        except Exception:
            _ARB = {}
    return _ARB


def parse_date(s):
    m = re.match(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", s or "")
    if not m:
        return ""
    d, mo, y = m.groups()
    return f"{y}-{int(mo):02d}-{int(d):02d}"

TYPE_MAP = {"ordinaria":"ordinaria","especial":"especial","extraordinaria":"extraordinaria",
            "solemne":"solemne","especial legislativa":"especial"}
def norm_type(s):
    s = (s or "").strip().lower()
    for k, v in TYPE_MAP.items():
        if s.startswith(k):
            return v
    return s or ""

# ── marcador inline de orador ─────────────────────────────────────────────────
# "El señor LORENZINI.-" / "El señor CORNEJO (Presidente).-" / "La señora GUZMÁN.-" / "El señor LORENZINI-"
# Apellido: tokens TODO-MAYÚSCULA (>=2 letras), con guion interno (VIERA-GALLO), hasta 3 tokens
# (MUÑOZ BARRA). Terminador OBLIGATORIO [.\-] tras el rol opcional → excluye frases como
# "El señor Secretario dará..." (Titlecase, sin terminador) y evita absorber el terminador.
_SUR = r"[A-ZÁÉÍÓÚÜÑÇÀ]{2,}(?:-[A-ZÁÉÍÓÚÜÑÇÀ]+)*"   # Ç: «PROKURIÇA» OCR (iter incrustados 2026-08-24)
# palabras-rol conocidas (para anclar el rol cuando el cierre ')' se corrompe)
_RKW  = (r"Presidenta|Presidente|Vicepresidenta|Vicepresidente|Prosecretari[oa]|"
         r"Secretari[oa]|[Mm]inistr[oa]|Subsecretari[oa]|Intendent[ae]")
_RKWB = _RKW + r"|don|do[ñn]a"
# El ROL entre paréntesis:
#  A) cierre ')' LIMPIO -> admite roles largos (hasta 70c: "Ministro de Transportes y Telecomunicaciones").
#  B) cierre OCR corrupto/perdido, anclado en palabra-rol: "(Vicepresidentes Tiene" (')'→'s') o
#     "(Presidente.- En" (')' perdido). Acotado a 40c -> nunca traga el discurso.
#  El tope de 70c en A acota cualquier swallow (un párrafo son cientos/miles de chars).
# Sin rol -> terminador [.\-] OBLIGATORIO (evita falsos positivos en prosa).
MARKER = re.compile(
    r"(?:El|La)\s+[Ss]e[ñn]or(?:a|ita)?\s+"   # señor | señora | señorita (perspectiva de género)
    r"(?P<sur>(?>" + _SUR + r"(?:\s+" + _SUR + r"){0,2}))"   # ATÓMICO: no parte "VIERA-GALLO" por su guion
    # ⚠ dname admite ABREVIATURA con punto («doña M.a Loreto» / «M.ª» — la grafía real de las
    # VICEPRESIDENTAS Carvajal y compañía) y una COMA de cierre antes del paréntesis del rol
    # («doña Isabel, (Presidenta)»). Sin esto, 2.738 marcadores incrustados —casi todos de
    # PRESIDENTAS— quedaban sin partir dentro del bloque de otro orador (medido 2026-08-24,
    # detector independiente sobre los 3.295 XML; la clase de [[feedback_gender_bias_extraction]]).
    r"(?:,?\s*do[ñn]a?s?\s+(?P<dname>[A-ZÁÉÍÓÚÜÑ](?:[a-záéíóúñ]+|\.[aªo°]?)(?:\s+[A-ZÁÉÍÓÚÜÑ](?:[a-záéíóúñ]+|\.[aªo°]?)){0,2}),?)?"
    r"(?:"
       r"(?:"
          r",?\s*\((?P<role>[^)\n]{1,90})\)"                                          # A: cierre ')' limpio (roles largos OK)
          r"|"
          r",?\s*\(\s*(?P<roleb>(?:" + _RKWB + r")[^)\n]{0,40}?)"
          r"\s*(?:[)sDJlI](?=\s+[A-ZÁÉÍÓÚ¿¡])|(?=\s*[.\-]))"                        # B: cierre OCR corrupto/perdido
          r"|"
          r",?\s*(?P<rolec>(?:[Mm]inistr[oa]|[Ss]ubsecretari[oa]|[Ii]ntendent[ae]|[Ss]ecretari[oa])(?:\s[^()\n.]{0,60}?)?)"
          r"(?=\s*[.\-(])"                       # C: rol de GOBIERNO en APOSICIÓN, sin paréntesis
                                                 #    («doña Magdalena, ministra de Vivienda y
                                                 #    Urbanismo (…).-» — 28 incrustados, 2026-08-24)
       r")"
       r"(?:\s*[\(\[][^)\]\n]{0,20}[\)\]])*"
       r"\s*[.\-]*"                                                                # con rol -> terminador opcional
    r"|"
       r"(?:\s*[\(\[][^)\]\n]{0,20}[\)\]])*"
       r"\s*(?:[.\-]+|(?=\s+Se[ñn]ora?\s+[Pp]resident[ea]\b))"                    # sin rol -> terminador obligatorio,
                                                 # O el VOCATIVO de apertura como firma («El señor
                                                 # OJEDA Señor Presidente, …» — la fuente omite el
                                                 # «.-»; iter incrustados 2026-08-24)
    r")"
)
def marker_role(mk):
    return mk.group("role") or mk.group("roleb") or mk.group("rolec") or ""

def owner_label(tag, owner_dip):
    """speaker_raw del propietario de un bloque sin marcador inline. Los bloques de argumentación
    AFAVOR/ENCONTRA/OTRO sin DIPUTADO NO tienen orador identificable -> speaker_raw vacío (no 'Afavor')."""
    if owner_dip:
        return owner_dip.group(1)
    base = tag.replace("INTERVENCION_", "")
    return "" if base in ("AFAVOR", "ENCONTRA", "OTRO") else base.title()
ROLE_NO_ID  = re.compile(r"secretari|prosecretari", re.I)            # roles de cámara (no diputados)
ROLE_GOV    = re.compile(r"ministr|subsecretari|autoridad|intendent", re.I)  # gobierno (sin id por diseño)

# El texto de intervención debe TERMINAR donde empieza la sección de documentos/anexos (sin oradores):
# "DOCUMENTOS DE LA CUENTA", "ANEXO DE LA SESIÓN"… (encabezado en MAYÚSCULAS → no es mención en prosa).
# Si no, fallback al cierre formal "Se levantó la sesión …". Evita que el último orador absorba el anexo.
_DOCS_BOUNDARY = re.compile(r"\b(?:DOCUMENTOS\s+DE\s+LA\s+CUENTA|ANEXOS?\s+DE\s+(?:LA\s+)?SESI[OÓ]N)\b")
# Nota del redactor de cierre: "Se levantó la sesión a las 19.16 horas" o "Se levantó a las 14.53
# horas" ("la sesión" opcional). Anclado en "a las … horas" (no aparece en mitad del discurso).
_END_BOUNDARY  = re.compile(r"(?:-\s*)?Se\s+levant[oó]\s+(?:la\s+sesi[oó]n\s+)?a\s+las?\s+[\d.:,]+\s*horas?\.?")
def clean_text(t):
    # cierre formal de sesión seguido de MUCHO contenido = anexo colgado -> cortar tras el cierre
    m = _END_BOUNDARY.search(t)
    if m and len(t) - m.end() > 200:
        return t[:m.end()].rstrip()
    # encabezado de sección de documentos/anexos (MAYÚSCULAS) -> cortar antes
    m = _DOCS_BOUNDARY.search(t)
    if m and m.start() > 40:
        return t[:m.start()].rstrip(" -;.\n")
    return t

def strip_tags(s):
    s = re.sub(r"<br\s*/?>", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = (s.replace("&aacute;","á").replace("&eacute;","é").replace("&iacute;","í")
           .replace("&oacute;","ó").replace("&uacute;","ú").replace("&ntilde;","ñ")
           .replace("&Aacute;","Á").replace("&Eacute;","É").replace("&Iacute;","Í")
           .replace("&Oacute;","Ó").replace("&Uacute;","Ú").replace("&Ntilde;","Ñ")
           .replace("&amp;","&").replace("&quot;",'"').replace("&nbsp;"," "))
    return re.sub(r"\s+", " ", s).strip()

# Elementos a capturar: TODAS las intervenciones (incl. AFAVOR/ENCONTRA/OTRO, que SON discursos
# de argumentación de proyectos de acuerdo) + los pases de lista de voto (A_FAVOR/EN_CONTRA/ABSTENCION).
ELEM = re.compile(r"<(INTERVENCION_[A-Z]+|A_FAVOR|EN_CONTRA|ABSTENCION)\b([^>]*)>(.*?)</\1>", re.S)
VOTE_TIPO  = {"A_FAVOR": "voto_afavor", "EN_CONTRA": "voto_encontra", "ABSTENCION": "voto_abstencion"}
VOTE_LABEL = {"A_FAVOR": "VOTACIÓN AFIRMATIVA", "EN_CONTRA": "VOTACIÓN NEGATIVA", "ABSTENCION": "ABSTENCIONES"}
BLOCK = re.compile(r"<(INTERVENCION_[A-Z]+)([^>]*)>(.*?)</\1>", re.S)  # roster (incl. anidadas)
# firma del pase de lista nominal de votación (era moderna). Si NO casa -> argumentación (era temprana).
ROLLCALL_RE = re.compile(r"Votaron\s+por\s+la|Vot[oó]\s+por\s+la|Se\s+abstuv", re.I)
# Fórmula con la que la mesa cede la palabra. Marca el fragmento que NO es del diputado
# al que apunta el atributo del elemento, sino de quien preside.
CEDE_PALABRA = re.compile(
    r"(?:tiene|tendr[áa]|puede hacer uso de)\s+la\s+palabra|ofrezco\s+la\s+palabra"
    r"|en\s+el\s+turno\s+de|por\s+la\s+v[íi]a\s+de\s+la\s+interrupci[óo]n", re.I)
# Roles de mesa: quien los lleva pasa a ser «quien preside» para los fragmentos siguientes.
ROL_MESA = re.compile(r"presiden|vicepresiden", re.I)

ATTR_DIP = re.compile(r'DIPUTADO="([^"]*)"')
ATTR_VAL = re.compile(r'DIPUTADOValue="([^"]*)"')

def turn_tipo(block_tag, role, has_id):
    """Tipo de intervención por turno: prioriza el rol inline; si no, el tag del bloque.
    Valores: presidente | secretario | prosecretario | autoridad (gobierno) |
             discurso_afavor | discurso_encontra | discurso_otro | diputado."""
    r = (role or "").lower()
    if "presiden" in r:        return "presidente"
    if "prosecretari" in r:    return "prosecretario"
    if "secretari" in r:       return "secretario"
    if re.search(r"ministr|subsecretari|autoridad|intendent", r): return "autoridad"
    base = block_tag.replace("INTERVENCION_", "").lower()
    return {"presidente":"presidente", "secretario":"secretario", "prosecretario":"prosecretario",
            "autoridad":"autoridad", "afavor":"discurso_afavor", "encontra":"discurso_encontra",
            "otro":"discurso_otro"}.get(base, "diputado")

def build_roster(blocks):
    """apellido_norm -> id_dep ; y primer-token -> id_dep si es único en la sesión."""
    full, first = {}, {}
    first_conflict = set()
    for tag, attrs, body in blocks:
        dip = ATTR_DIP.search(attrs); val = ATTR_VAL.search(attrs)
        if not (dip and val):
            continue
        apellido = dip.group(1).split(",")[0]   # "Lorenzini, Pablo" -> "Lorenzini"
        key = norm_sur(apellido)
        if key:
            full[key] = val.group(1)
            tok = key.split(" ")[0]
            if tok in first and first[tok] != val.group(1):
                first_conflict.add(tok)
            first.setdefault(tok, val.group(1))
    for tok in first_conflict:
        first.pop(tok, None)
    return full, first

def resolve(sur, role, full, first, dep_idx=None, date="", name_hint=""):
    """Devuelve id_dep | '' resolviendo el apellido del marcador.
    Orden: roster de sesión (exacto) -> fuzzy roster (typos OCR) -> deputies.csv por fecha.
    Roles de cámara (Secretario/Prosecretario) y gobierno (Ministro…) -> sin id por diseño.
    name_hint = nombre de pila ('don Nombre') para desambiguar apellidos compartidos."""
    role = role or ""
    if ROLE_NO_ID.search(role) or ROLE_GOV.search(role):
        return ""
    key = norm_sur(sur)
    # apellido que ES un rol de cámara/gobierno ("El señor SECRETARIO.-")
    if ROLE_NO_ID.search(key) or ROLE_GOV.search(key):
        return ""
    if key in full:
        return full[key]
    tok = key.split(" ")[0]
    if tok in first:
        return first[tok]
    # fuzzy contra el roster de la sesión (typos OCR: ANDRADRE->ANDRADE)
    if full:
        m = rf_process.extractOne(key, list(full.keys()), scorer=fuzz.ratio)
        if m and m[1] >= 88:
            return full[m[0]]
        if first:
            m2 = rf_process.extractOne(tok, list(first.keys()), scorer=fuzz.ratio)
            if m2 and m2[1] >= 90:
                return first[m2[0]]
    # fallback global: diputado ausente del roster (Vicepresidente / Presidente accidental)
    if dep_idx is not None:
        idd = resolve_by_date(dep_idx, sur, date, role, name_hint)
        if idd:
            return idd
    return ""   # no resuelto

def parse_plain(text, leg, snum, date, stype, dep_idx):
    """Boletín NO estructurado (sin INTERVENCION_*): parsear el texto plano de la SESION
    por marcadores inline. Sin roster de sesión -> resolver vía deputies.csv por fecha.
    El encabezado/índice (antes del primer marcador) se descarta."""
    rows = []
    marks = list(MARKER.finditer(text))
    for i, mk in enumerate(marks):
        end = marks[i+1].start() if i+1 < len(marks) else len(text)
        seg = text[mk.end():end].strip()
        sur = mk.group("sur"); role = marker_role(mk)
        sid = resolve(sur, role, {}, {}, dep_idx, date, mk.group("dname") or "")
        sraw = re.sub(r"\s+", " ", mk.group(0)).strip().rstrip(".-").strip()
        tipo = turn_tipo("INTERVENCION_DIPUTADO", role, bool(sid))
        if seg and len(seg) > 1:
            rows.append((leg, snum, date, stype, sraw, sid, tipo, seg))
    return rows

def parse_file(path, dep_idx=None):
    t = Path(path).read_text(encoding="utf-8", errors="ignore")
    sesion = re.search(r"<SESION ([^>]*)>", t)
    sesion_inner = re.search(r"<SESION\b[^>]*>(.*?)</SESION>", t, re.S)
    sesion_text  = strip_tags(sesion_inner.group(1)) if sesion_inner else ""
    portada = re.search(r"<PORTADA>(.*?)</PORTADA>", t, re.S)
    ptxt = re.sub(r"<br\s*/?>", "\n", portada.group(1)) if portada else ""

    numero = re.search(r'NUMERO="([^"]*)"', sesion.group(1)) if sesion else None
    fecha  = re.search(r'FECHA_INICIO="([^"]*)"', sesion.group(1)) if sesion else None
    tipo   = re.search(r'TIPO="([^"]*)"', sesion.group(1)) if sesion else None

    # meta desde PORTADA o, si falta, desde la cabecera del texto de SESION (boletines sin PORTADA)
    meta_text = ptxt + "\n" + sesion_text[:3000]
    sesnum = re.search(r"Sesi[oó]n\s+(\d+)[ªa]", meta_text)
    leg    = re.search(r"LEGISLATURA\s+(\d+)", meta_text)

    session_number = (sesnum.group(1) if sesnum else (numero.group(1) if numero else ""))
    legislature    = leg.group(1) if leg else ""
    # FECHA — el CONTENIDO manda; el nombre de archivo solo si del contenido no sale nada.
    #
    # Antes era al revés («el nombre es la fuente autoritativa»), justificado por typos de año en
    # FECHA_INICIO. Medido sobre los 3.295 XML: el atributo está en 3.239 y coincide con el nombre
    # en 3.090 (95,40%); discrepan 149 y **solo 2** tienen año imposible (2077, 2099) — que son
    # exactamente los que citaba la justificación. Es decir, la regla generalizaba de 2 casos a
    # 3.295. El guardarraíl se queda, pero acotado a lo que la evidencia sostiene: año fuera de
    # rango. Las 149 discrepancias NO se resuelven aquí a ojo: se emiten al informe y las decide
    # `audit_session_dates.py` por CRONOLOGÍA, contra las sesiones vecinas del propio corpus.
    fn = re.search(r"_(\d{4}-\d{2}-\d{2})_", Path(path).name)
    fecha_nombre = fn.group(1) if fn else ""
    fecha_xml = parse_date(fecha.group(1) if fecha else "")
    arb = _arbitradas().get(Path(path).name)
    if arb:
        date, date_source = arb["date"], arb["date_source"]
    else:
        plausible = bool(fecha_xml) and 1985 <= int(fecha_xml[:4]) <= 2026
        date = fecha_xml if plausible else (fecha_nombre or fecha_xml)
        date_source = "xml" if plausible else "filename"
    session_type   = norm_type(tipo.group(1) if tipo else "")

    elems = list(ELEM.finditer(t))
    # roster: TODAS las intervenciones con DIPUTADO (incl. anidadas en A_FAVOR de la era temprana)
    full, first = build_roster(BLOCK.findall(t))

    rows = []

    def emit(sraw, sid, tipo, seg):
        rows.append((legislature, session_number, date, session_type, sraw, sid, tipo, seg))

    # Quién preside en cada momento de la sesión. Se actualiza con cada marcador inline cuyo rol
    # es de mesa, y sirve para el fragmento PREVIO al primer marcador de un bloque (ver abajo).
    mesa = {"sraw": "", "id": ""}

    def handle_speech(tag, attrs, body):
        """Parsea un bloque de discurso por marcadores inline (una fila por turno)."""
        owner_dip = ATTR_DIP.search(attrs); owner_val = ATTR_VAL.search(attrs)
        owner_id = owner_val.group(1) if owner_val else ""
        text = strip_tags(body)
        if not text:
            return
        marks = list(MARKER.finditer(text))
        if not marks:
            sraw = owner_label(tag, owner_dip)
            emit(sraw, owner_id, turn_tipo(tag, "", bool(owner_id)), text.strip())
            return
        if marks[0].start() > 0:
            pre = text[:marks[0].start()].strip()
            if len(pre) > 1:
                # ⚠ El fragmento ANTERIOR al primer marcador NO es del diputado del atributo.
                # El XML mete dos oradores en un mismo elemento: la presidencia cede la palabra y
                # a continuación habla el diputado, y el elemento lleva el nombre del SEGUNDO:
                #   <INTERVENCION_DIPUTADO DIPUTADO="Chadwick, Andrés">
                #     El señor VICEPRESIDENTE.- Tiene la palabra el Diputado señor Chadwick.
                #     El señor CHADWICK.- Señor Presidente, …
                # Atribuir ese `pre` al propietario ponía en boca del diputado la frase con la que
                # le dan la palabra: 5.053 turnos (1,19% del track XML), siempre del mismo tipo.
                # Si el fragmento CEDE la palabra, es de la mesa; se le asigna quien presidía en
                # ese punto de la sesión, y si aún no consta, se deja el orador VACÍO —nunca se
                # atribuye a quien la recibe—.
                if CEDE_PALABRA.search(pre):
                    emit(mesa["sraw"], mesa["id"],
                         turn_tipo(tag, "presidente", bool(mesa["id"])), pre)
                else:
                    sraw = owner_label(tag, owner_dip)
                    emit(sraw, owner_id, turn_tipo(tag, "", bool(owner_id)), pre)
        for i, mk in enumerate(marks):
            end = marks[i+1].start() if i+1 < len(marks) else len(text)
            seg = text[mk.end():end].strip()
            sur = mk.group("sur"); role = marker_role(mk)
            sid_dep = resolve(sur, role, full, first, dep_idx, date, mk.group("dname") or "")
            sraw = re.sub(r"\s+", " ", mk.group(0)).strip().rstrip(".-").strip()
            if role and ROL_MESA.search(role):
                mesa["sraw"], mesa["id"] = sraw, sid_dep
            if seg:
                emit(sraw, sid_dep, turn_tipo(tag, role, bool(sid_dep)), seg)

    # mapa A_FAVOR/EN_CONTRA/ABSTENCION -> tag sintético de discurso (era temprana = argumentación)
    DEBATE_TAG = {"A_FAVOR": "INTERVENCION_AFAVOR", "EN_CONTRA": "INTERVENCION_ENCONTRA",
                  "ABSTENCION": "INTERVENCION_OTRO"}
    has_speech_block = False
    for m in elems:
        tag, attrs, body = m.group(1), m.group(2), m.group(3)
        if tag in VOTE_TIPO:
            text = strip_tags(body)
            if not text:
                continue
            # ¿pase de lista nominal (era moderna) o sección de argumentación (era temprana)?
            is_rollcall = ROLLCALL_RE.search(text[:160]) and "INTERVENCION_" not in body
            if is_rollcall:
                emit(VOTE_LABEL[tag], "", VOTE_TIPO[tag], text)
            else:
                has_speech_block = True
                handle_speech(DEBATE_TAG[tag], "", body)
            continue
        has_speech_block = True
        handle_speech(tag, attrs, body)

    # boletín NO estructurado (VALID=False, sin INTERVENCION_*): recuperar del texto plano
    if not has_speech_block:
        rows += parse_plain(sesion_text, legislature, session_number, date, session_type, dep_idx)
    return rows

def enrich(rows, dep_info):
    """Añade speaker_name (deputies), party (por fecha) y legislature = período legislativo
    (por fecha, vía periodos.xml — anula el código que traía el parser). district vacío."""
    out = []
    for (leg, snum, date, stype, sraw, id_dep, tipo, text) in rows:
        name = dep_info.get(id_dep, {}).get("name", "") if id_dep else ""
        party = party_at(dep_info.get(id_dep), date) if id_dep else ""
        legislature = period_for_date(date) or leg
        if not tipo.startswith("voto_"):       # los pases de lista de voto no se truncan
            text = clean_text(text)
        out.append([legislature, snum, date, stype, sraw, id_dep, name, party, "", text, tipo])
    return out

_WORKER = {}
def _init_worker():
    _WORKER["info"] = load_deputies()
    _WORKER["idx"]  = load_dep_index()

def process_one(path):
    return enrich(parse_file(path, _WORKER["idx"]), _WORKER["info"])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file"); ap.add_argument("--all", action="store_true")
    ap.add_argument("--sample", type=int); ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default="source/cl/matrix/interventions_xml.csv")
    args = ap.parse_args()

    files = sorted(glob.glob("source/cl/raw/xml/*.xml"))
    if args.file:
        files = [args.file]
    elif args.sample:
        n = len(files); idx = [0, n//4, n//2, 3*n//4, n-1][:args.sample]
        files = [files[i] for i in idx]

    if args.file or args.sample:
        dep = load_deputies(); idx = load_dep_index()
        total = 0
        for f in files:
            rows = enrich(parse_file(f, idx), dep)
            total += len(rows)
            print(f"\n=== {Path(f).name}: {len(rows)} turnos ===")
            for r in rows[:6]:
                print(f"  [{r[0]}|s{r[1]}|{r[2]}|{r[3]}] raw={r[4]!r} id={r[5]} name={r[6]!r} party={r[7]} text={r[9][:70]!r}")
        print(f"\nTOTAL turnos en muestra: {total}")
        return

    # batch completo en paralelo
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    n_files = 0; n_rows = 0
    with open(args.out, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(CANON_COLS)
        with ProcessPoolExecutor(max_workers=args.workers, initializer=_init_worker) as ex:
            futs = {ex.submit(process_one, f): f for f in files}
            for fut in as_completed(futs):
                rows = fut.result()
                w.writerows(rows)
                n_files += 1; n_rows += len(rows)
                if n_files % 250 == 0:
                    print(f"  {n_files}/{len(files)} archivos, {n_rows} turnos", flush=True)
    print(f"OK: {n_files} archivos -> {n_rows} turnos -> {args.out}")

if __name__ == "__main__":
    main()
