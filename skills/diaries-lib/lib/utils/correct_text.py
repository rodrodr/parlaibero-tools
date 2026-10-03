#!/usr/bin/env python3
"""
Deterministic typographic correction pass (paragraphs & hyphenation). No LLM.

Aplica además NORMALIZACIONES deterministas por país (regex) desde el config:
`correct.normalize_replacements` — lista de [pattern, replacement] aplicadas en modo MULTILINE
ANTES del procesado de párrafos. Uso típico: corregir variantes de honorífico degradadas por OCR
detectadas con analyze_speaker_markers.py (ej. UY: "^SEROR " → "SEÑOR ") para que el tagging las
detecte. Anclar siempre (^, \\b) y ser específico para no sobre-corregir.

CLI:
    python correct_text.py --input <path> --output <path> \
        [--config <yaml>] --min-paragraph-chars 80 [--no-hyphen-join]
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


def apply_normalizations(text: str, replacements: list) -> tuple[str, int]:
    """Aplica [pattern, replacement] regex (MULTILINE). Devuelve (texto, nº de sustituciones)."""
    total = 0
    for entry in replacements or []:
        if isinstance(entry, (list, tuple)) and len(entry) == 2:
            pattern, repl = entry
        elif isinstance(entry, dict):
            pattern, repl = entry.get("pattern", ""), entry.get("replacement", "")
        else:
            continue
        if not pattern:
            continue
        try:
            text, n = re.subn(pattern, repl, text, flags=re.MULTILINE)
            total += n
        except re.error as exc:
            sys.stderr.write(f"[correct_text] normalización inválida '{pattern}': {exc}\n")
    return text, total

def reassemble_markers(text: str, prefix_patterns: list,
                       max_frag_len: int = 45, max_frags: int = 6) -> tuple[str, int]:
    """Une MARCADORES DE ORADOR fragmentados en varias líneas (PDF de columna estrecha / OCR):

        -H.D.            →  -H.D. NORMAN SCOTT
        NORMAN               (una sola línea, tageable)
        SCOTT

    Una línea que ARRANCA como marcador (prefijo honorífico/rol del config, regex de
    `correct.marker_reassembly`) pero SIN ':' final absorbe las líneas siguientes que son
    fragmentos TODO-MAYÚSCULAS cortos, hasta incluir la línea que termina en ':' (colon-style)
    o hasta el último fragmento uppercase (hyphen-style). El discurso (Title-case/minúsculas)
    corta la absorción, así que las listas de asistencia y la prosa no se tocan.
    Sin esto, el tagging (anclado a línea) NO VE estos marcadores y la intervención entera se
    atribuye al orador ANTERIOR (falso negativo silencioso; verificado en PA 2026-07)."""
    prefix_res = []
    for p in prefix_patterns or []:
        try:
            prefix_res.append(re.compile(p))
        except re.error as exc:
            sys.stderr.write(f"[correct_text] marker_reassembly inválido '{p}': {exc}\n")
    if not prefix_res:
        return text, 0
    # Un fragmento de marcador es corto y DOMINANTEMENTE mayúsculas. No exigir mayúsculas
    # estrictas: el OCR mete minúsculas sueltas en nombres ("RODRíGUEZ", "LdPEZ", "ENCAKGADO").
    # El discurso (Title-case: "Señor", "Gracias", "Continuando") queda fuera por el ratio.
    def _is_frag(s: str) -> bool:
        if not s or len(s) > max_frag_len:
            return False
        if not re.match(r"^[A-ZÁÉÍÓÚÜÑ0-9(]", s):
            return False
        letters = [c for c in s if c.isalpha()]
        if not letters:
            return False
        return sum(1 for c in letters if c.isupper()) / len(letters) >= 0.60
    frag_re = type("F", (), {"match": staticmethod(lambda s: _is_frag(s))})()
    lines = text.split("\n")
    out: list[str] = []
    joins = 0
    i, n = 0, len(lines)
    while i < n:
        ls = lines[i].rstrip()
        if ls and not ls.endswith(":") and any(rx.match(ls) for rx in prefix_res):
            acc = [ls]
            j, took = i + 1, 0
            while j < n and took < max_frags:
                nxt = lines[j].strip()
                if not nxt or not frag_re.match(nxt):
                    break
                acc.append(nxt)
                took += 1
                j += 1
                if nxt.endswith(":"):
                    break
            if took > 0:
                out.append(" ".join(acc))
                joins += took
                i = j
                continue
        out.append(lines[i])
        i += 1
    return "\n".join(out), joins


# ── El guion de fin de línea no siempre es el guion ASCII ─────────────────────
# U+00AD es el guion BLANDO: existe únicamente para marcar dónde puede partirse una palabra, así
# que unir por él es correcto siempre. U+2010 y U+2011 son el guion tipográfico. Sin ellos, en
# PE 2023 el marcador llegaba partido —`El señor ECHEVERRÍA RODRÍ­⏎GUEZ (CD-JPP).—`— y el
# turno entero se perdía. Ver [[feedback_marcador_partido]].
_GUIONES = r"\-­‐‑"
_GUION_FIN = rf"[A-Za-záéíóúüñÁÉÍÓÚÜÑ][{_GUIONES}]$"
_GUION_FIN_VERSAL = rf"[A-ZÁÉÍÓÚÜÑ][{_GUIONES}]$"

# Characters that signal a sentence/paragraph end — we do NOT merge after these
# ⚠ `…` CIERRA FRASE. Marca la interrupción del orador y en PT es constantísima («Vozes do PSD:
# — Ah!…», «A Sr.ª Presidente: — …»). Sin él, el merge daba la línea por inacabada y se tragaba
# el marcador de la intervención siguiente: 85 turnos incrustados que quedaban atribuidos al
# orador ANTERIOR. Ver [[feedback_embedded_markers]] y [[feedback_apartes]].
_SENTENCE_END = set(".?!:»\"…")

# set de texto normal para la densidad de BASURA BINARIA (field-codes de conversiones
# .doc→.docx antiguas). Incluye la tipografía legítima; la sopa de bytes queda fuera.
_TEXTO_NORMAL = set(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    "ÁÉÍÓÚÜÑáéíóúüñÀÃÂÊÔÕÇàãâêôõçºª"
    "0123456789 \t.,;:()[]¿?¡!«»\"'’‘“”`-–—…/%°$€&#@*+=§"
)


def quita_lineas_basura(text: str, ratio: float, min_len: int = 8) -> tuple[str, int]:
    """Retira LÍNEAS de basura binaria («7GkŽ¹Úü!Fo–¸Û», «Š"üýŒ$» — field-codes que la
    conversión .doc→.docx dejó incrustados) por DENSIDAD de caracteres fuera del set de
    texto normal. Opt-in por país (`correct.junk_line_ratio`); el umbral se calibra con
    sonda — CR: 0.30 separa la sopa de bytes de cualquier prosa real (el español acentuado
    con tipografía queda por debajo de 0.10). La línea corta (< min_len) nunca se toca."""
    out, n = [], 0
    run4 = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{4,}")
    for ln in text.split("\n"):
        s = ln.strip()
        if len(s) >= min_len:
            weird = sum(1 for c in s if c not in _TEXTO_NORMAL)
            if weird / len(s) >= ratio:
                n += 1
                continue
            # 2º criterio (CR ronda 2): la sopa de bytes con letras ASCII intercaladas
            # («èB¢E¤ECFEFdFfF…») queda BAJO el umbral de densidad — su firma real es no
            # contener NINGUNA palabra: sin un solo run de ≥4 letras y con glifos raros.
            # Ninguna línea de prosa real de ≥20 car carece de una palabra de 4 letras.
            if len(s) >= 20 and weird >= 3 and not run4.search(s):
                n += 1
                continue
        out.append(ln)
    return "\n".join(out), n

# ── COLA DE GUÍA DE PUNTOS DEL OCR (opt-in: correct.ocr_leader_tail) ─────────────────
# El OCR renderiza la guía de puntos del acta como una tira degenerada al FINAL de la
# línea: «Muchísimas gracias. =————“=““=“=iiiiiiimiiiiion». Señalado por el investigador
# en EC el 2026-08-29. Ver el docstring de recorta_cola_ocr para las tres versiones que
# fallaron antes y por qué: no es un problema que una regex pueda resolver.
# alfabeto con el que el OCR renderiza la guía de puntos. SIN vocales abiertas (a, e, u):
# su presencia es la señal más barata de que hay una palabra de verdad.
_LEADER = set("ionctmlrsIT")
_SIMBOLOS = set("=—–-.+*\"“”'|><~_,:;· •°º\t")
_TRIPLE = re.compile(r"(.)\1\1")
_TOKEN = re.compile(r"[^\s]+")
_LETRA = re.compile(r"[^\W\d_]", re.UNICODE)


def _es_letra(c: str) -> bool:
    return bool(_LETRA.match(c))


def _cola_degenerada(cola: str) -> bool:
    """¿Es esto guía de puntos y no texto?"""
    nucleo = "".join(c for c in cola if _es_letra(c))
    simbolos = sum(1 for c in cola if c in _SIMBOLOS)
    if not nucleo:
        return simbolos >= 4                      # tira de puros símbolos
    if any(not _es_letra(c) and c not in _SIMBOLOS and not c.isspace() for c in cola):
        return False                              # cifras u otra cosa: no se toca
    if not all(c in _LEADER for c in nucleo):
        return False                              # una letra fuera del alfabeto guía → texto
    # con letras del alfabeto guía, aún hay que PROBAR la degeneración, por una de tres vías
    if _TRIPLE.search(nucleo):          # (a) tres letras idénticas: el español no las tiene
        return True
    if len(nucleo) <= 4 or simbolos >= 4:   # (b) resto muy corto, o guía de símbolos clara
        return True
    # (c) DIVERSIDAD BAJA: «oroomocctiocicticciir» son 21 letras y solo 6 distintas (0,29).
    #     Sin esta vía se escapaba el propio ejemplo del investigador, que no tiene ninguna
    #     letra triplicada y solo llega a 3 símbolos.
    return len(nucleo) >= 8 and len(set(nucleo)) / len(nucleo) <= 0.45


def recorta_cola_ocr(text: str, min_cola: int = 6, min_cabeza_tokens: int = 2):
    """Devuelve (texto, nº de líneas recortadas, nº de caracteres retirados)."""
    out, n_lineas, n_car = [], 0, 0
    for ln in text.split("\n"):
        if not ln.strip():
            out.append(ln)
            continue
        mejor = None
        # los cortes CANDIDATOS son las posiciones que siguen a un carácter no-letra
        for i in range(len(ln) - min_cola, 0, -1):
            if _es_letra(ln[i - 1]):
                continue                          # cortaría media palabra
            cola = ln[i:]
            if len(cola.strip()) < min_cola:
                continue
            if _cola_degenerada(cola):
                mejor = i                         # se sigue buscando más a la izquierda
            else:
                break                             # ya no es cola: se para
        if mejor is None:
            out.append(ln)
            continue
        cabeza = ln[:mejor].rstrip()
        if len(_TOKEN.findall(cabeza)) < min_cabeza_tokens:
            out.append(ln)
            continue
        out.append(cabeza)
        n_lineas += 1
        n_car += len(ln) - len(cabeza)
    return "\n".join(out), n_lineas, n_car


# ⚠ ABREVIATURAS QUE NO CIERRAN FRASE. El punto de `Sr.`, `Dr.` o `Exmo.` es de abreviatura, no
# de fin de oración, y sin esta excepción `Sr.`⏎`Presidente` nunca se une: la regla veía el punto
# y daba la frase por terminada. Es uno de los casos que el investigador reportó en BR.
# Se comprueba sobre la ÚLTIMA palabra de la línea, no sobre el texto entero.
_ABREV_NO_FIN = {
    "sr", "sra", "srs", "sras", "srta", "sr.a", "dr", "dra", "drs", "dras",
    "exmo", "exma", "exmos", "exmas", "ilmo", "ilma", "lic", "ing", "prof", "profa",
    "d", "dn", "dna", "da", "hon", "mons", "gral", "cnel", "cap", "tte", "adm",
    "núm", "num", "n", "art", "arts", "pág", "pag", "págs", "cf", "vid", "etc",
    "ex", "av", "avda", "apdo", "s.a", "s.l", "v.exa", "s.exa", "vv.exas",
}


def ancho_de_caja(text: str, defecto: int = 80) -> int:
    """Estima el ancho de columna del documento: p90 de las líneas seguidas de otra no vacía.

    ⚠ El umbral de fusión NO puede ser un número fijo. `min_paragraph_chars = 80` dejaba fuera
    justo las líneas que llegan al borde de la caja, que son las que hay que unir. Medido sobre
    `extracted/`, el p90 de las líneas que no cierran frase coincide con la caja de cada país:
    EC 72 (caja 71) · DO 102 (101) · CL 43 (42) · PA 50 (56) · UY 97. Con 80 se cubrían EC, PA y
    CL, y se perdían DO y UY enteros.

    Se calcula por DOCUMENTO porque la caja es propiedad del PDF, no del corpus: medirla sobre el
    conjunto daba modas de 1-3 caracteres, sin sentido."""
    ls = [l.rstrip() for l in text.split("\n")]
    L = [len(ls[i]) for i in range(len(ls) - 1)
         if ls[i].strip() and ls[i + 1].strip() and len(ls[i]) >= 20]
    if len(L) < 30:
        return defecto
    L.sort()
    return max(defecto, int(L[int(len(L) * 0.90)] * 1.15))


def _cierra_frase(linea: str) -> bool:
    """True si la línea termina de verdad una oración (y no en una abreviatura)."""
    s = linea.rstrip()
    if not s or s[-1] not in _SENTENCE_END:
        return False
    # Una COMILLA solo cierra frase si va precedida de puntuación: «…Mesamávida"» a fin de
    # línea es una frase que CONTINÚA (el blanco que se insertaba ahí partía la oración en
    # dos párrafos — lector adversarial CL iter-3, clase blanco-MID-frase).
    if s[-1] in "\"»”'" and (len(s) < 2 or s[-2] not in ".!?…"):
        return False
    if s[-1] == ".":
        ult = re.split(r"[\s(\[«\"]", s[:-1])[-1].lower().strip("¡¿-–—")
        if ult in _ABREV_NO_FIN or (len(ult) <= 2 and ult.isalpha()):
            return False
    return True

# PROTECCIÓN DE MARCADORES en el merge de párrafos (general, siempre activa): una línea que
# PARECE marcador de orador nunca se absorbe hacia el párrafo anterior.
# ⚠ LA PROTECCIÓN ES EN UN SOLO SENTIDO. Se comprueba sobre la línea SIGUIENTE (no se absorbe un
# marcador), nunca sobre la línea en curso: impedir que un marcador absorba hacia abajo lo separa
# de su propio texto. En PT era el 29,4 % de los saltos que quedaban dentro de los párrafos —
# «A Sr.ª Presidente: — Sr.as» ⏎ «e Srs. Deputados, o primeiro ponto da ordem do dia…»—. Un
# marcador seguido de otro marcador sigue a salvo, porque esa comprobación es la que se conserva. Sin esto, cuando la
# línea previa termina sin puntuación (OCR: "Peraltao" por "Peralta."), el merge pega el
# marcador a mitad de línea y el tagging ya no lo ve → intervención atribuida al orador
# ANTERIOR (falso negativo silencioso; verificado en PA 2026-07: ~3.000 casos). Dejar el
# salto de línea de más es inocuo; absorber un marcador es destructivo.
# ⚠ El marcador de página que emite `extract_text` es una FRONTERA, no texto: si el merge de
# párrafos lo absorbe, queda «…importante ---PAGE 0002--- y la frase continúa», que es
# exactamente el mobiliario incrustado que el pipeline existe para evitar. Protegido siempre.
_PAGINA_RX = __import__("re").compile(r"^\s*-{3}\s*PAGE\s+\d+\s*-{3}\s*$", __import__("re").I)

_MARKER_PROTECT_DEFAULT = [
    _PAGINA_RX,
    re.compile(r"^\s*[-–—]\s*[A-ZÁÉÍÓÚÜÑ]"),                      # dash + MAYÚSCULA
    re.compile(r"^\s*(?:H\.?\s?[DL]\.?|LIC\.?)\s+[A-ZÁÉÍÓÚÜÑ]"),   # honorífico + nombre
    re.compile(r"^\s*(?:PRESIDENT[AE]|SECRETARI[OA]|VICEPRESIDENT[AE]|SUBSECRETARI[OA])\b"),
    re.compile(r"^\s*SE[ÑN]ORA?\s+[A-ZÁÉÍÓÚÜÑ]{2}"),               # SEÑOR + NOMBRE caps
]


_COMA_FIN = re.compile(r',\s*$')


def _corta_marcador_falso(actual: str, activo: bool) -> bool:
    """¿Hay que IGNORAR la protección de la línea de abajo?

    Un marcador de orador NUNCA empieza justo después de una línea que deja la frase
    abierta en coma. Cuando el cargo del orador ENVUELVE a la segunda línea —«INTERVENCIÓN
    DE LA SEÑORITA X,» ⏎ «PRESIDENTA DEL CONSEJO…»— la protección por palabra de rol
    (_MARKER_PROTECT_DEFAULT[3]) toma la continuación por un marcador nuevo y PARTE el
    marcador real. Medido en EC: 1.379 casos. Opt-in por país.
    """
    return activo and bool(_COMA_FIN.search(actual))


def _is_protected(line: str, extra_res: list) -> bool:
    ls = line.lstrip()
    return any(rx.match(ls) for rx in _MARKER_PROTECT_DEFAULT) or \
           any(rx.match(ls) for rx in (extra_res or []))

# Patterns that suggest a new paragraph is starting (don't merge into them)
# ⚠⚠ CORREGIDO 2026-08-19. Antes era `r"^[A-ZÁÉÍÓÚÜÑ]|^El |^La |..."`, es decir: CUALQUIER línea
# que empiece por mayúscula se trataba como párrafo nuevo y no se unía a la anterior. Esa regla
# existía para suplir una señal que faltaba —la LÍNEA EN BLANCO, que `strip_headers` destruía al
# filtrar `if ln.strip()`— y su efecto era dejar sin unir todo corte de columna que continuara con
# nombre propio: `Espírito`⏎`Santo`, `Mesa`⏎`Diretora`, `no acordo de`⏎`Lideranças`. De ahí venía
# la mayor parte de los títulos partidos y de las uniones fallidas del corpus.
#
# Reparada la causa en `strip_headers`, la separación de párrafo vuelve a estar disponible (medida:
# 49,2 % de líneas en blanco en PT, 43,6 % en EC), y es ELLA la que marca el inicio de párrafo. Aquí
# solo quedan los arranques que una línea en blanco no señala: viñetas, numerales y estructura
# legal. Una mayúscula suelta ya NO es señal de párrafo nuevo.
_PARAGRAPH_START_RE = re.compile(
    # guarda: guion PEGADO a minúscula es un INCISO del orador («-podríamos decir-»), nunca
    # arranque de párrafo — rompía la frase por una vía no identificada del alternador
    # (anomalía registrada; la guarda la anula sea cual sea). CL iter-2 del lector.
    r"^\s*(?!(?-i:[-–—][a-záéíóúüñ]))(?:"   # ⚠ este RE compila con re.I: toda discriminación de caja exige (?-i:…)
    r"[-–—•*]\s|"                                     # viñeta
    r"(?-i:[-–—](?=[A-ZÁÉÍÓÚÜÑ][a-záéíóúüñ]))|"             # narrativa taquigráfica pegada («-Aplausos…», «-Habla…») — CL 2026-08-23
    r"\d{1,3}[.)º°ª]\s|"                              # numeral (≤3 dígitos: «2023. » es un AÑO que continúa la frase, no un ítem — CL ronda 14)
    r"\d{1,3}\.(?=(?-i:[A-ZÁÉÍÓÚÜÑ]{2}))|"                  # epígrafe numerado PEGADO a VERSALES («23.AUTORIZACION…») — CL 2026-08-23
    r"[a-z][.)]\s|"                                   # inciso a) b)
    # romano con CAJA DISCRIMINADA: con re.I, «civil. » casaba [IVXLC]+ entero (c-i-v-i-l son
    # todas letras romanas) y la línea que arrancaba así se trataba como párrafo nuevo — el
    # acumulador partía «…da sociedade ⏎ civil. Ela solicita…» (BR pasada 3, clase residual).
    # El enumerador romano en minúscula existe pero corto y con paréntesis: «iv) », no «civil. »
    r"(?-i:[IVXLC]+)[.)]\s|(?-i:[ivxlc]{1,4})\)\s|"   # romano
    # ⚠ La estructura legal DISCRIMINA POR CAJA: el «Artículo 21.-» que abre disposición va con
    # inicial MAYÚSCULA; el «artículo 21» minúsculo a inicio de línea es una CONTINUACIÓN de
    # frase envuelta («…las multas de que trata el ⏎artículo 7…») que este patrón, compilado con
    # re.I, partía en falso — 2.125 cortes en CL (pre-chequeo iter-6). Mismo caso para
    # título/capítulo/sección minúsculos («a cualquier ⏎título»).
    r"(?-i:A)rt(?:[íi]culo|igo)?\.?\s*\d|(?-i:ARTÍCULO)\s*\d|"    # artículo de ley
    r"(?-i:C)AP[ÍI]TULO\b|(?-i:T)[ÍI]TULO\s|(?-i:S)ECC[ÍI]ÓN\b|(?-i:S)ECÇÃO\b|"
    r"(?-i:L)IVRO\b|(?-i:L)IBRO\b|(?-i:A)NEXO\b"
    r")", re.I)



def unir_marcador_partido(text: str, patrones: list, max_cierre: int = 40,
                          cierre: str = ":") -> tuple[str, int]:
    """Une un marcador que empieza en una línea y CIERRA con el terminador en la siguiente.

    ⚠ **Distinto de `reassemble_markers`, y por un motivo medido.** Aquel absorbe las líneas
    siguientes de un marcador sin ':' final, y en GT eso hundió el etiquetado de 224.934 a
    199.863 (−25.071): absorbía prosa. Este solo une cuando la unión **queda cerrada**, es
    decir cuando la 2ª línea contiene ':' dentro de sus primeros `max_cierre` caracteres.
    Con esa condición la unión no puede tragarse un discurso entero.

    En GT son 11.427 casos, todos del mismo corte: «…, EN FUNCIONES DE⏎PRESIDENTE: …».

    ⚠ **El terminador NO es universal.** GT y la mayoría cierran el marcador con ':', pero PE lo
    cierra con '.—' («El señor DE BELAUNDE DE⏎CÁRDENAS.— Gracias, Presidente.»). Con ':' fijo,
    en PE no se unía ninguno y el turno se perdía entero, igual que en PY. De ahí `cierre`.

        correct:
          marker_join_next: ['^(?:EL|LA)\\s+R\\.\\s', '^(?:EL|LA)\\s+SEÑOR[A]?\\s']
          marker_join_terminator: '.—'      # por defecto ':'
    """
    if not patrones:
        return text, 0
    rx = [re.compile(p) for p in patrones]
    # «Ya cerrado» tolera las variantes que el contain literal no ve: el guion EN/EM del acta
    # («O SR. X (Fora do microfone.) – Inflamados.») y el terminador en FIN de línea sin espacio
    # de cola («A SRA. PARK CANNON (Manifestação em língua estrangeira.) -»). Con el contain
    # literal ambos pasaban por marcador partido y la unión se tragaba el marcador siguiente.
    cierre_rx = re.compile(re.escape(cierre).replace("\\-", "[-–—]"))
    lineas = text.split("\n")
    out: list = []
    n = 0
    i = 0
    while i < len(lineas):
        ln = lineas[i]
        if (i + 1 < len(lineas) and not cierre_rx.search(ln.rstrip() + " ")
                and any(r.match(ln.strip()) for r in rx)
                and cierre in lineas[i + 1][:max_cierre]
                # la continuación de un marcador partido nunca arranca OTRO marcador: si la 2ª
                # línea casa un patrón, unir es enterrarla (BR: −13 marcadores en una sesión)
                and not any(r.match(lineas[i + 1].strip()) for r in rx)):
            # Si la 1ª línea acaba en guion, el corte está DENTRO de una palabra: se une sin
            # espacio y sin el guion. Con un espacio quedaba «VELÁSQUEZ QUES­ QUÉN» y el nombre
            # dejaba de casar con el padrón — el arreglo destruía lo que venía a arreglar.
            izq = ln.rstrip()
            if re.search(_GUION_FIN, izq) or re.search(_GUION_FIN_VERSAL, izq):
                out.append(izq[:-1] + lineas[i + 1].lstrip())
            else:
                out.append(izq + " " + lineas[i + 1].lstrip())
            n += 1
            i += 2
            continue
        out.append(ln)
        i += 1
    return "\n".join(out), n


def unir_marcador_vertical(text: str, cfg: dict, cierre_def: str = ":",
                           marker_res: list = None) -> tuple[str, int]:
    """Reensambla el marcador EXPLOTADO EN VERTICAL: una palabra por línea.

    Distinto de `unir_marcador_partido`, que une DOS líneas y exige el terminador en la segunda.
    Aquí el marcador viene hecho trizas porque el PDF emite cada tramo con estilo propio:

        EL ⏎ R. ⏎ PRIMER ⏎ VICEPRESIDENTE ⏎ ROSALES ⏎ MARROQUIN, ⏎ EN ⏎ FUNCIONES ⏎ DE ⏎
        PRESIDENTE:  Habiendo el representante Flores Ortiz apelado al pleno…

    Medido en GT (2026-08-25): **1.940 marcadores en 69 sesiones de la era 2001, y NINGUNO casa
    ningún `speaker_tag_pattern`** — `diaries-tag` los perdería enteros.

    ⚠ **Opt-in y con los PATRONES EN EL CONFIG DEL PAÍS** (indicación del investigador: «lo ideal
    sería generar reglas específicas en el config de cada país para lidiar con esos casos
    particulares»). Sin `correct.marker_join_vertical` el mecanismo es INERTE — los otros 15
    países no se enteran:

        correct:
          marker_join_vertical:
            prefixes: ['^(?:EL|LA)$']   # la línea que ARRANCA el marcador troceado
            terminator: ':'             # por defecto, marker_join_terminator
            max_lines: 12

    ⚠ La cautela viene de un desastre medido: en GT un `marker_reassembly` mal acotado hundió el
    etiquetado 25.071 marcadores (`gt-0004`) porque absorbía prosa. Aquí los guardarraíles son
    tres: (1) el arranque lo declara el país y debe ser EXACTO (`^(?:EL|LA)$` no casa ninguna
    línea de discurso: la prosa no deja un artículo solo en su renglón); (2) solo se une si el
    bloque CIERRA con el terminador dentro de `max_lines`, así que nunca se traga un discurso;
    (3) no se cruza una línea que ya sea un marcador por sí misma.
    La prueba de que no absorbe prosa es la proporción: 1.940 uniones → +1.939 taggables (1:1).
    Si absorbiera, las uniones superarían a los marcadores ganados.
    """
    if not cfg:
        return text, 0
    arranques = _compila(cfg.get("prefixes"))
    if not arranques:
        return text, 0
    maxl = int(cfg.get("max_lines", 12))
    cierre = cfg.get("terminator") or cierre_def
    lineas = text.split("\n")
    out: list = []
    i = n = 0
    while i < len(lineas):
        s = lineas[i].strip()
        if s and any(r.match(s) for r in arranques):
            acc, j, cerrado = [], i, False
            while j < min(i + maxl, len(lineas)):
                x = lineas[j].strip()
                if x:
                    # ⚠ GUARDA 3, y la aprendí por las malas: si la ventana alcanza una línea que
                    # YA ES un marcador entero, unir es ENTERRARLO. Sin esta comprobación la
                    # regla ganaba 13.308 taggables pero se comía marcadores completos en 13
                    # sesiones («EL R. PRESIDENTE ARZÚ ESCOBAR:  Señores representantes…»).
                    # Mismo criterio que `unir_marcador_partido`: la continuación de un marcador
                    # troceado nunca arranca OTRO marcador.
                    if len(acc) and marker_res and any(r.match(x) for r in marker_res):
                        break
                    acc.append(x)
                    if cierre in x and len(acc) > 1:
                        cerrado = True
                        break
                j += 1
            if cerrado:
                out.append(" ".join(acc))
                n += 1
                i = j + 1
                continue
        out.append(lineas[i])
        i += 1
    return "\n".join(out), n


def _compila(patrones):
    out = []
    for p in patrones or []:
        try:
            out.append(re.compile(p))
        except re.error:
            pass
    return out


# ── PASOS 2-3-4 de la secuencia canónica de limpieza (ver diaries-correct/SKILL.md) ───────────
# La SECUENCIA es: 1) identificar separador de página → 2) eliminar mobiliario anclado a él →
# 3) eliminar el separador → 4) aislar los marcadores (pre-tag scan) → 5) restaurar fluidez (merge).
# El ORDEN es obligatorio: quitar el separador antes que el mobiliario deja el mobiliario huérfano
# (destruye el ancla sin limpiar). Cada paso lee el vocabulario del país de su country_config.

_PAGE_RX = re.compile(r"^\s*-{2,}\s*PAGE\s*(?:\d+|BREAK)\s*-{2,}\s*$", re.I)


def quita_mobiliario(text: str, furniture_res: list, marker_res: list,
                     line_res: list = None, prefix_res: list = None,
                     masthead_res: list = None, max_block: int = 6) -> tuple[str, int]:
    """PASOS 1-2-3: retira el bloque de cabecera/pie ANCLADO al separador de página (bloque +
    folio suelto + basura corta), y elimina el propio separador. Al quitar el bloque, las dos
    mitades de la frase que partía quedan contiguas y el merge (paso 5) las reconecta.

    ⚠ Se detiene SIEMPRE en un marcador de orador, para no tragárselo. El folio (nº ≤4 dígitos)
    y las líneas ≤3 caracteres se consumen dentro del bloque porque `limpiar_mobiliario` los
    saltaba sin quitarlos y acababan incrustados en la frase. Sin separador delante, el bloque
    se retira solo si hay 2+ líneas de vocabulario consecutivas (una sola podría ser texto)."""
    # ⚠ El mobiliario casa sobre la línea SIN SANGRÍA (lstrip), como _is_protected: la era
    # moderna de CL indenta el cabecero con 5-15 espacios y los patrones anclados a ^ quedaban
    # ciegos — el bloque no consumía y el merge fusionaba el cabecero dentro del párrafo
    # («…princi- 72 CÁMARA DE DIPUTADOS», lector adversarial iter-1). La indentación es layout.
    # es_furn reconoce TAMBIÉN furniture_line: el país que define su cabecero por líneas (BR)
    # y no por bloque dejaba el consumo post-página ciego — rompía en la 1ª línea del cabecero,
    # la maquinaria de líneas lo retiraba después, y las BLANCAS del bloque quedaban huérfanas
    # en medio de la frase cortada por la página.
    def es_furn(x): return any(r.match(x.lstrip()) for r in furniture_res) or \
                           any(r.match(x.lstrip()) for r in (line_res or []))
    def es_marc(x): return any(r.match(x.lstrip()) for r in marker_res)
    L = text.split("\n"); out: list = []; i = 0; n = 0
    _seen_masthead: set = set()
    while i < len(L):
        if _PAGE_RX.match(L[i]):
            # ⚠ Las BLANCAS que preceden al marcador se van con él (CL 2026-08-23): si quedan,
            # cortan el párrafo en cada frontera de página («…in-» ⏎ ⏎ «ciso…») y ni el merge ni
            # la deshifenización pueden cruzar la blanca. Se conserva UNA blanca solo si la línea
            # anterior CIERRA frase (frontera legítima de párrafo) — mismo criterio que
            # drop_page_marker, que ya no ve marcadores porque aquí se retiran antes.
            while out and (not out[-1].strip() or re.match(r"^\.{2,4}$", out[-1].strip())):
                out.pop()      # blancas y «...» de continuación se van con el corte
            # el FOLIO del pie va DELANTE del separador en la mayoría de composiciones (BR:
            # 98.710 delante vs 209 detrás en muestra de 800 archivos) — se consume aquí,
            # ANCLADO a la marca, con el mismo criterio que el de detrás; un número suelto sin
            # marca al lado no se toca nunca. Las reglas `(?=---PAGE )` de normalize eran
            # código muerto: cuando corren (paso 3) la marca ya no existe.
            if out and re.match(r"^\d{1,4}(?:\s*/\s*\d{1,4})?$", out[-1].strip()):
                out.pop(); n += 1
                while out and not out[-1].strip():
                    out.pop()
            if out and _cierra_frase(out[-1].rstrip()):
                out.append("")
            n += 1; i += 1
            k = 0
            while i < len(L) and k < max_block:
                s = L[i].strip()
                if es_marc(L[i]):
                    break
                if not s:
                    # las BLANCAS del bloque no cuentan contra el tope: no pueden ser texto, y
                    # contarlas lo agotaba (BR: 3 líneas de cabecera + 3 blancas = 6) dejando
                    # la última blanca viva EN MEDIO de la frase cortada por la página
                    i += 1; n += 1
                # ⚠ La basura corta (≤3 car.) NO puede ser una PALABRA (GT 2026-08-25): en la era
                # 2001 el marcador viene partido con el artículo solo en su línea —«EL» ⏎ «R.
                # PRIMER VICEPRESIDENTE ROSALES MARROQUIN, EN FUNCIONES DE» ⏎ «PRESIDENTE:…»— y
                # esta rama se comía el «EL», destruyendo el marcador entero: −32 en una sola
                # sesión, −177 en el corpus, con el delta NEGATIVO de marcadores como firma
                # ([[feedback_correct_furniture_burial]]). Restringirlo a lo no alfabético deja
                # fuera fragmentos de OCR («·», «12», «..») y conserva toda palabra.
                # ⚠⚠ 2ª vuelta (GT 2026-08-25, lo cazó el refutador del workflow): `not s.isalpha()`
                # se quedaba CORTO. El ítem de enumeración «a)» mide 2 caracteres y NO es
                # alfabético (lleva el paréntesis), así que seguía cayendo cuando el bloque de
                # página lo alcanzaba: medido, 685 ítems BORRADOS en 300 sesiones (los otros
                # 13.850 no se pierden, se unen a su texto, que es lo correcto).
                # Criterio definitivo: la basura corta no puede llevar NINGÚN alfanumérico. Los
                # fragmentos reales del OCR («·», «..», «--», «*») siguen cayendo; el número
                # suelto ya lo cubre su propia rama, justo encima.
                elif es_furn(L[i]) or re.match(r"^\d{1,4}(?:\s*/\s*\d{1,4})?$", s) \
                        or (len(s) <= 3 and not any(c.isalnum() for c in s)) \
                        or re.match(r"^\.{2,4}$", s):
                    i += 1; n += 1; k += 1
                else:
                    break
            continue
        if furniture_res and es_furn(L[i]) and not es_marc(L[i]):
            j = i
            while j < len(L) and es_furn(L[j]):
                j += 1
            if j - i >= 2:
                n += j - i; i = j; continue
        # MASTETE/CARÁTULA (keep-first): la primera aparición es prolegomena de la página 1 y se
        # CONSERVA; solo se retiran las repeticiones en páginas 2+. El investigador: «dejarlo en
        # la primera página, retirarlo solo si se repite». Es el principio «nada se borra»
        # ([[feedback_prolegomena]]).
        if masthead_res and not es_marc(L[i]):
            hit = next((idx for idx, r in enumerate(masthead_res) if r.match(L[i].lstrip())), None)
            if hit is not None:
                if hit in _seen_masthead:
                    n += 1; i += 1; continue          # repetición → se retira
                _seen_masthead.add(hit)               # 1ª vez → se conserva
                out.append(L[i]); i += 1; continue
        # mobiliario de LÍNEA SUELTA inequívoca (remove-if-alone): p. ej. «Página 3»,
        # «Gaceta del Congreso 67». Se retira aunque vaya sola —no puede ser discurso— y, si
        # partía una frase, el merge (paso 5) reconecta las mitades. Los patrones DEBEN anclar la
        # línea entera (`...$`) para no decapitar una línea de contenido que empiece igual.
        if line_res and any(r.match(L[i].lstrip()) for r in line_res) and not es_marc(L[i]):
            n += 1; i += 1; continue
        # DECAPITACIÓN: cabecero corrido pegado como PREFIJO de una línea de contenido
        # («GACETA DEL CONGRESO 593 tivamente, quiero…»). Se recorta SOLO el prefijo y se conserva
        # el resto; si la línea era solo el cabecero, se elimina. Nunca por subcadena: el patrón
        # ancla a `^` y debe ser específico (con su número), para no decapitar prosa
        # ([[feedback_mobiliario_pagina]]: `C O R T E S` se comía la palabra «Cortes»).
        if prefix_res and not es_marc(L[i]):
            ln = L[i].lstrip() if any(r.match(L[i].lstrip()) for r in prefix_res) else L[i]
            tocado = False
            m = next((mm for r in prefix_res if (mm := r.match(ln))), None)
            while m and m.end() > 0:
                ln = ln[m.end():].lstrip(); n += 1; tocado = True
                m = next((mm for r in prefix_res if (mm := r.match(ln))), None)
            if tocado:
                if ln.strip():
                    out.append(ln)
                i += 1; continue
        out.append(L[i]); i += 1
    return "\n".join(out), n


def separa_marcadores(text: str, marker_res: list) -> str:
    """PASO 4 (pre-tag scan): aísla cada marcador de orador con UNA línea en blanco delante, para
    que sea una frontera dura que el merge no cruce y el tagger vea sin ambigüedad. Aislar es más
    robusto que solo 'proteger' el marcador durante el merge: uno que empieza su propia línea en
    blanco no lo entierra ningún join."""
    if not marker_res:
        return text
    L = text.split("\n"); out: list = []
    for ln in L:
        if any(r.match(ln.lstrip()) for r in marker_res):
            while out and not out[-1].strip():
                out.pop()
            if out:
                out.append("")
        out.append(ln)
    return "\n".join(out)


def separa_marcadores_inline(text: str, inline_res: list) -> tuple[str, int]:
    """Marcador INCRUSTADO a mitad de línea — viene así del propio OCR (EC LLM: «…el texto
    del Artículo uno. EL SEÑOR PRESIDENTE: Está en consideración…» llega como UN párrafo con
    el cambio de turno dentro; hallado por el investigador en la muestra, 2026-08-24).
    Se parte la línea ANTES del marcador cuando lo precede un CIERRE de frase. El patrón es
    POR PAÍS (correct.isolate_markers_inline) y debe capturar (1)=cierre precedente,
    (2)=marcador; la COMA no es cierre a propósito: «ASUME LA DIRECCIÓN…, EL SEÑOR DIPUTADO
    VITERI» es narración que MENCIONA a la persona, no un turno."""
    n = 0
    def corta(m):
        nonlocal n
        n += 1
        g1 = m.group(1)
        # la ristra de guiones separadora entre turnos se DESCARTA al partir; la puntuación
        # real de la frase («.», «?», «.-») se conserva sin su cola de guiones
        g1 = re.sub(r"[-–—]{2,}\s*$", "", g1)
        return g1 + "\n\n" + m.group(2)
    for rx in inline_res:
        text = rx.sub(corta, text)
    return text, n


def correct_text(
    text: str,
    min_paragraph_chars: int | None = None,   # None → se mide la caja del propio documento
    min_paragraph_chars_max: int | None = None,   # TOPE de la caja medida (opt-in por país)
    join_hyphens: bool = True,
    marker_hyphen_prefixes: list | None = None,
    protect_res: list = None,
    paragraph_accumulate: bool = False,
    pairs_merge_full_lines: bool = False,   # opt-in por país: ver el bloque de abajo
    merge_over_protected_after_comma: bool = False,
    max_paragraph_chars: int = 2000,
    drop_page_marker: bool = True,
    split_at_sentence_end: bool = False,
    marker_absorbs_below: bool = False,
    merge_indent_aware: bool = False,
    heading_own_paragraph: str | None = None,
    collapse_layout_blanks: bool = False,
    collapse_layout_blanks_ratio: float = 0.30,
    flow_output: bool = False,
) -> tuple[str, dict]:
    # ⚠⚠ EL MARCADOR DE PÁGINA NO PUEDE SOBREVIVIR A `correct`. Lo escribe la extracción para
    # anclar la limpieza de mobiliario; una vez hecha, es ruido. En BR llegó hasta el CSV final y
    # contaminó 566.218 filas (−66,9 M car. al limpiarlo después, a mano). Se retira AQUÍ, al
    # entrar, y no al salir, porque así hace un segundo trabajo: el salto de página parte la
    # frase en el 38,8 % de los casos («…mereceriam, se não por» ⏎ «si pelo menos por aqueles…»,
    # a veces partiendo la palabra: «social-» ⏎ «democracia»). Reduciendo la frontera a UN salto
    # de línea, el merge de abajo la recompone con su propio criterio —ancho de caja y
    # puntuación—, que es quien debe decidirlo; en el 61,2 % restante la línea cierra frase y el
    # merge la deja en paz. En PT son 239.611 marcadores y ~92.000 frases recompuestas.
    # `drop_page_marker=False` para el país que necesite conservarlo como ancla aguas abajo.
    if drop_page_marker:
        _L, _out = text.split("\n"), []
        _skip_blanks = False
        for _ln in _L:
            if not _PAGINA_RX.match(_ln):
                # las blancas que SIGUEN al marcador de una frase cortada también son del corte
                # de página, no de párrafo: dejarlas partía la frase igual que el marcador
                # («…ocupada pelo Sr. João ⏎⏎ Caldas, 4º Suplente…» — BR piloto del colapso)
                if _skip_blanks and not _ln.strip():
                    continue
                _skip_blanks = False
                _out.append(_ln)
                continue
            while _out and not _out[-1].strip():      # las blancas que lo rodean se van con él
                _out.pop()
            # el corte de página NO es una frontera de párrafo: si la línea anterior quedó
            # cortada, se dejan contiguas y decide el merge; si cierra frase, se conserva.
            if _out and _cierra_frase(_out[-1].rstrip()):
                _out.append("")
            else:
                _skip_blanks = True
        text = "\n".join(_out)

    # ── BLANCA DE LAYOUT (opt-in: correct.collapse_layout_blanks) ─────────────────────────────
    # En el PDF a DOBLE ESPACIO (BR 2003-2018: una blanca entre CADA línea envuelta, ratio
    # blancas/texto ≈ 1,0 medido por censo) la línea en blanco NO señala párrafo: es interlínea
    # de composición, y como el acumulador rompe en toda blanca, el reflujo quedaba a cero —
    # 8,5 M de cortes intra-frase con salto de PÁRRAFO en el corrected (704.882 solo en 2003;
    # en la era a espacio simple 2019-2025 el mismo motor deja 20-100/año). Se DETECTA por
    # archivo (ratio ≥ 0.30 cubre los años mixtos 2013-2018) y solo se retira la blanca ÚNICA
    # entre dos líneas de texto cuando el par es una continuación de columna inequívoca:
    #   · A no cierra frase, y
    #   · B arranca en col 0 (la convención sangra el párrafo nuevo) en minúscula, o A llena
    #     la caja (≥70 % del ancho medido, sin contar la sangría) — así el PASE DE LISTA
    #     (líneas cortas capitalizadas) y el epígrafe centrado quedan intactos, y
    #   · B no es marcador protegido, ni viñeta/numeral/estructura legal, ni epígrafe.
    # La blanca doble (sección) se conserva siempre. Igual que con el marcador de página: aquí
    # solo se retira la señal falsa; la unión la decide el merge de abajo con su criterio.
    layout_blank_joins = 0
    if collapse_layout_blanks:
        _ls = text.split("\n")
        _ntxt = sum(1 for _l in _ls if _l.strip())
        _nbl = len(_ls) - _ntxt
        if _ntxt and _nbl / _ntxt >= collapse_layout_blanks_ratio:
            _ancho = ancho_de_caja(text)
            _hrx = re.compile(heading_own_paragraph) if heading_own_paragraph else None
            _o2: list = []
            _k = 0
            while _k < len(_ls):
                _o2.append(_ls[_k])
                if (_ls[_k].strip() and _k + 2 < len(_ls)
                        and not _ls[_k + 1].strip() and _ls[_k + 2].strip()):
                    _a = _ls[_k].rstrip()
                    _b = _ls[_k + 2]
                    # continuación de columna en col 0 (convención general), o continuación
                    # DENTRO de un bloque sangrado (narración de la mesa, documento citado:
                    # ahí la sangría marca pertenencia al bloque, no párrafo nuevo — solo se
                    # une con B en minúscula, que nunca es ítem de lista ni pase de asistencia)
                    _cont = (_b[:1] not in " \t"
                             and (_b[:1].islower() or len(_a.strip()) >= 0.7 * _ancho)) \
                        or (_a[:1] in " \t" and _b[:1] in " \t"
                            and _b.lstrip()[:1].islower())
                    if (_cont
                            and not _cierra_frase(_a)
                            and not _PARAGRAPH_START_RE.match(_b)
                            and not _is_protected(_b, protect_res)
                            and not (_hrx and _hrx.match(_b.strip()))):
                        _k += 2
                        layout_blank_joins += 1
                        continue
                _k += 1
            text = "\n".join(_o2)

    if min_paragraph_chars is None:
        min_paragraph_chars = ancho_de_caja(text)
        # ── TOPE de la caja medida (opt-in: correct.min_paragraph_chars_max) ──────────────
        # `ancho_de_caja` es un p90×1,15 y por tanto SE DISPARA en el fichero cuyo cuerpo no
        # es prosa: en MX subía a 699 en 210 ficheros y el merge fundía tablas enteras. El
        # tope acota esa cola sin renunciar a medir (las épocas difieren de verdad: en DO el
        # p90 de la prosa va de 133 en 2001-2008 a 104 en 2017-2025).
        # Se elige POR PAÍS y por encima de la caja legítima más ancha MEDIDA, no a ojo:
        # en DO, sobre las 2.225 sesiones, p99 = 181 y el máximo legítimo 196; el único valor
        # por encima es 301, y es una de las 7 sesiones cuyo OCR emitió tablas en HTML.
        # Ausente (None) → comportamiento idéntico al anterior: los otros países no se enteran.
        if min_paragraph_chars_max:
            min_paragraph_chars = min(min_paragraph_chars, int(min_paragraph_chars_max))
    lines = text.split("\n")
    n = len(lines)

    # ── MODO SANGRÍA (opt-in: correct.merge_indent_aware) ────────────────────────────────
    # En los PDF con composición moderna la apertura de párrafo lleva SANGRÍA (CL: el 96-97 %
    # de las líneas que siguen a un cierre de frase y arrancan en mayúscula van sangradas) y
    # la continuación de columna NO la lleva: ese 3-4 % sin sangrar es exactamente la frase
    # partida que el acumulador cerraba en falso («…por la sequía.» ⏎ «La mayor parte del
    # agua…» — lector adversarial CL iter-5). La convención se DETECTA por archivo: donde no
    # existe (OCR de los 90: 0 % sangrado), el modo queda inerte y nada cambia.
    indent_mode = False
    indent_joins = 0
    if merge_indent_aware:
        _cand = _ind = 0
        for _a, _b in zip(lines, lines[1:]):
            _sa = _a.rstrip()
            if _sa and _cierra_frase(_sa) and _b.strip() and _b.lstrip()[:1].isupper():
                _cand += 1
                if _b[:1] in " \t":
                    _ind += 1
        indent_mode = _cand >= 30 and _ind / _cand >= 0.7

    def _continuacion_sin_sangria(nl: str) -> bool:
        """Continuación de columna disfrazada de párrafo: mayúscula inicial SIN la sangría
        que la convención del archivo exige a los párrafos nuevos (y sin ser viñeta,
        numeral ni marcador protegido)."""
        return (indent_mode and nl and nl[:1] not in " \t" and bool(nl.strip())
                and nl.lstrip()[:1].isupper()
                and not _PARAGRAPH_START_RE.match(nl)
                and not _is_protected(nl, protect_res)
                and not (heading_rx and heading_rx.match(nl.strip())))

    # ── EPÍGRAFE EN PÁRRAFO PROPIO (opt-in: correct.heading_own_paragraph) ───────────────
    # El epígrafe numerado Title-case («1.→Fundamentos de Derecho», «a.2.- Reforma Curricular»)
    # no cierra frase, así que el acumulador lo pegaba a su párrafo (iter-5 R5, 9/9 fusionados).
    # Apagar el merge entero lo evitaba pero dejaba sin unir los tramos ENVUELTOS de los mismos
    # archivos (iter-6: 13×R1 «la Ley Orgánica⏎Constitucional»). Con esta regla el epígrafe
    # cierra su propio párrafo (blanco antes y después) y el resto del archivo SÍ refluye.
    # ⚠ Ámbito por país/era vía config: en OCR envuelto una línea «12. El proyecto que…» partida
    # a media frase sería falsamente cerrada — actívalo solo donde las líneas son párrafos.
    heading_rx = re.compile(heading_own_paragraph) if heading_own_paragraph else None
    heading_isolated = 0

    hyphen_joins = 0
    marker_hyphen_rx = [re.compile(x) for x in (marker_hyphen_prefixes or [])]
    short_merges = 0
    ambiguous_breaks: list[dict] = []
    total_paragraphs = 0

    result: list[str] = []
    i = 0

    while i < n:
        line = lines[i]

        # --- Hyphenation join ---
        if join_hyphens and i + 1 < n:
            next_line = lines[i + 1]
            # Line ends with letter + hyphen, next starts with lowercase
            if re.search(_GUION_FIN, line) and next_line and next_line[0].islower():
                # Remove the hyphen and join without space
                joined = line[:-1] + next_line
                hyphen_joins += 1
                # Mismo motivo que en el merge de línea corta: el resultado puede volver a
                # terminar en guion (dos cortes seguidos). Se reinyecta en vez de apilarse.
                lines[i + 1] = joined
                i += 1
                continue

            # ── El mismo corte, pero en VERSALES y DENTRO de un marcador de orador ──
            # La regla de arriba exige que la continuación empiece en minúscula, y por eso no ve
            # `El señor MINISTRO PARA LAS ADMINISTRACIO-⏎NES PUBLICAS:`. En ES son unos 5.300
            # marcadores: el corte cae dentro del propio marcador, antes de que el etiquetador
            # llegue a verlo, así que la intervención entera se pierde.
            #
            # ⚠ Se limita a las líneas que EMPIEZAN un marcador (`marker_hyphen_prefixes`) y NO
            # se aplica al cuerpo del texto: ahí un `PALABRA-⏎OTRA` en versales puede ser un
            # compuesto real y unirlo destruiría el guion. Comprobado en ES sobre 96 pares
            # distintos: los 96 son cortes silábicos (CONSU-⏎MO, BERMU-⏎DEZ, JOVELLA-⏎NOS),
            # ninguno es apellido compuesto — el tipógrafo corta por sílabas, no por el guion duro.
            if marker_hyphen_rx and re.search(_GUION_FIN_VERSAL, line) and next_line \
                    and next_line[:1].isupper() \
                    and any(r.match(line) for r in marker_hyphen_rx):
                result.append(line[:-1] + next_line)
                hyphen_joins += 1
                i += 2
                continue

        # --- Epígrafe en párrafo propio (ver heading_own_paragraph arriba) ---
        if heading_rx and heading_rx.match(line.strip()):
            if result and result[-1].strip():
                result.append("")
            result.append(line.strip())
            result.append("")
            heading_isolated += 1
            i += 1
            continue

        # --- Short line merge ---
        stripped = line.rstrip()
        if (
            stripped
            # ⚠ En modo ACUMULADOR la entrada no puede exigir línea corta: la unión de guiones
            # REINYECTA la línea fusionada (p.ej. 3 líneas de columna → 117 car.) y con el tope
            # de caja esa línea ya no entraba al acumulador — el salto sobrevivía exactamente
            # después de cada cadena de guiones (CL 2026-08-23, 554 saltos intra-frase). Una
            # línea LLENA que no cierra frase es precisamente la que continúa. Las salvaguardas
            # reales son las de PARADA (cierra_frase · paragraph_start · protegida), no la longitud.
            # ⚠⚠ LA PUERTA DE LONGITUD ES EL DEFECTO DE REFLUJO DEL MODO PARES (DO, 2026-08-29).
            # El modo pares REINYECTA la línea fusionada, así que va uniendo hasta que la línea
            # alcanza la caja — y ahí se detiene, A MITAD DE FRASE. En DO eso deja el 40,20 % de
            # los saltos de prosa cortando frases (los países sanos van al 4-9 %), y el 95,5 %
            # de ellos los bloquea ESTA condición y ninguna otra. Es la misma razón por la que
            # PE «paga 3,1 M de saltos intra-frase» (nota de pe-0004).
            # `pairs_merge_full_lines` aplica en modo pares el razonamiento que el acumulador ya
            # hace suyo doce líneas más arriba —una línea LLENA que no cierra frase es la que
            # continúa— SIN renunciar a la reinyección, que es lo que conserva la
            # deshifenización (por eso PE se quedó en pares: decisión pe-0004).
            # ⚠ El tope NO es opcional: la puerta de longitud era también el único límite del
            #   modo pares. Sin `max_paragraph_chars` una sesión sin puntuación de cierre
            #   encadena el documento entero — medido en DO: una línea de 21.413 caracteres.
            # Es OPT-IN POR PAÍS (default False): activarlo donde el marcador ocupa la línea
            # entera puede fundirlo con su texto. Medir marcadores antes y después, siempre.
            and (len(stripped) < min_paragraph_chars or paragraph_accumulate
            # ⚠⚠ `min_paragraph_chars = 0` ES EL INTERRUPTOR EXPLÍCITO que apaga el merge de
            #   pares (era doc de CL; lote de OCR-HTML de DO). La bandera NO puede saltárselo:
            #   al hacerlo aplanó las 7 sesiones de OCR-HTML de DO —2013-03-19_005 pasó de
            #   79.544 líneas a 5.230, fundiendo las etiquetas <td> entre sí— que es justo lo
            #   que el override existía para impedir. Por eso exige min_paragraph_chars veraz.
                 or (pairs_merge_full_lines and min_paragraph_chars
                     and len(stripped) < max_paragraph_chars))
            # en modo sangría, un cierre de frase seguido de continuación SIN sangrar no
            # cierra el párrafo: la frase siguiente es de la misma columna (iter-5)
            and (not _cierra_frase(stripped)
                 or (paragraph_accumulate and i + 1 < n
                     and _continuacion_sin_sangria(lines[i + 1])))
            and i + 1 < n
            # ⚠⚠ ¿PUEDE UN MARCADOR ABSORBER SU PROPIO TEXTO? Depende del país, y equivocarse
            # destruye marcadores en silencio. Donde el marcador OCUPA LA LÍNEA ENTERA —patrón
            # anclado a `$`: PA 83 % de sus patrones, CR 100 %, EC 56 %— unirlo con la línea de
            # abajo hace que su propio patrón deje de casar: en PA desaparecían 1.336 de 2.147
            # marcadores (−62 %) sin quedar siquiera incrustados, porque ya no eran esa forma.
            # Donde el marcador comparte línea con el texto (PT: «A Sr.ª Presidente: — Sr.as»
            # ⏎ «e Srs. Deputados,…») ocurre lo contrario: NO unirlo lo separa de su discurso,
            # el 29,4 % de los cortes. Por eso es una decisión POR PAÍS y el default es el
            # conservador. Regla: actívalo solo si los patrones del país NO llevan `$`.
            and (marker_absorbs_below or not _is_protected(line, protect_res))
        ):
            next_line = lines[i + 1]
            if next_line and not _PARAGRAPH_START_RE.match(next_line) \
                    and (not _is_protected(next_line, protect_res)
                         or _corta_marcador_falso(stripped, merge_over_protected_after_comma)):
                if not paragraph_accumulate:
                    joined = stripped + " " + next_line.lstrip()
                    short_merges += 1
                    # ⚠ NO se apila el resultado directamente. La línea recién fusionada puede
                    # terminar ella misma en guion de corte, y apilarla con `i += 2` la sacaba
                    # del bucle para siempre: la deshifenización no volvía a mirarla nunca.
                    # Medido en EC (2026-08-15): 48.515 de 112.118 cortes (el 43%) se quedaban
                    # SIN UNIR por esto —«…termina en Es-⏎meraldas»— y el patrón afecta a los
                    # 16 países, no solo a este. Se reinyecta para reexaminarla.
                    lines[i + 1] = joined
                    i += 1
                    continue
                # ── modo ACUMULADOR ────────────────────────────────────────────────
                # Une por PÁRRAFO, no por pares: sigue absorbiendo mientras la línea no
                # cierre frase y la siguiente no arranque párrafo ni sea un marcador.
                #
                # Por qué existe: el modo por pares deja el texto de CO en líneas de 61
                # caracteres de media, y sus 10 patrones de orador están anclados a inicio
                # de línea — casaban 32 líneas donde el corpus publicado tenía 9.029.
                # Iterar la pasada por pares NO lo resuelve: converge en 45.096 líneas.
                acc = [stripped]
                acc_consumed = 0          # líneas ABSORBIDAS (no `len(acc)`: la deshifenación fusiona)
                if _cierra_frase(stripped):
                    indent_joins += 1          # entró por la vía de sangría (cierre + continuación)
                j = i + 1
                while j < n:
                    nxt = lines[j]
                    if not nxt.strip() or _PARAGRAPH_START_RE.match(nxt) \
                            or (_is_protected(nxt, protect_res)
                                and not _corta_marcador_falso(acc[-1].rstrip(),
                                                              merge_over_protected_after_comma)) \
                            or (heading_rx and heading_rx.match(nxt.strip())):
                        break
                    # ⚠⚠ DESHIFENACIÓN DENTRO DEL ACUMULADOR. La unión de guiones de arriba solo
                    # mira `lines[i]` y reinyecta; las líneas que ESTE bucle absorbe no vuelven a
                    # pasar por ella, y `" ".join(acc)` las pegaba con un ESPACIO: toda palabra
                    # partida dentro del párrafo quedaba fosilizada como «obser- vaciones», a
                    # mitad de línea, donde ya ninguna pasada la ve. Medido en PE sobre 12
                    # sesiones al comparar los dos modos: hyphen_joins 16.212 → 4.205 y residuo
                    # «X- y» 0 → 12.007 (decisión pe-0004). Por eso PE se quedó en modo pares y
                    # paga 3,1 M de saltos intra-frase, y por eso PY tuvo que parchearlo en su
                    # config —`normalize_replacements` (e), pre-merge— país por país.
                    #
                    # El criterio es EXACTAMENTE el del motor (`_GUION_FIN` + continuación en
                    # minúscula), así que no introduce ninguna clase de riesgo nueva: aplica
                    # aquí la misma decisión que ya se toma una línea más arriba. Va bajo
                    # `join_hyphens`: donde el país delega la unión en la 2ª pasada con léxico
                    # (`hyphen_join: false` — BR·CL·ES·EC·GT) esto queda INERTE, como debe.
                    # El resultado puede volver a terminar en guion (dos cortes seguidos) y se
                    # reexamina solo, porque se reescribe `acc[-1]` en vez de apilar.
                    nxt_s = nxt.strip()
                    if (join_hyphens and re.search(_GUION_FIN, acc[-1])
                            and nxt_s[:1].islower()):
                        acc[-1] = acc[-1][:-1] + nxt_s
                        hyphen_joins += 1
                    else:
                        acc.append(nxt_s)
                    acc_consumed += 1
                    if _cierra_frase(nxt):
                        # modo sangría: el cierre de frase no cierra el párrafo si lo que
                        # sigue es continuación sin sangrar (frase nueva de la misma columna)
                        # — salvo que el párrafo ya exceda el tope (ahí SÍ cierra: es frontera
                        # de frase legítima).
                        if (j + 1 < n and _continuacion_sin_sangria(lines[j + 1])
                                and sum(len(x) for x in acc) < max_paragraph_chars):
                            indent_joins += 1
                            j += 1
                            continue
                        j += 1
                        break
                    # ⚠ Tope SUAVE: cortar por longitud partía la frase en un punto arbitrario
                    # («…quedó de manifiesto: 58 ⏎⏎ delincuentes fueron premiados…» — lector
                    # adversarial CL iter-8, 98 casos). Superado el tope se sigue absorbiendo
                    # HASTA el próximo cierre de frase; el freno duro (4×) solo para texto
                    # patológico sin puntuación (tablas aplanadas).
                    if sum(len(x) for x in acc) >= 4 * max_paragraph_chars:
                        j += 1
                        break
                    j += 1
                result.append(" ".join(acc))
                # ⚠ El párrafo acumulado se cierra con línea EN BLANCO: sin ella, la mitad de los
                # párrafos quedaban pegados al siguiente (convención inconsistente — lector
                # adversarial CL iter-1, 15 casos).
                result.append("")
                short_merges += acc_consumed
                i = j
                continue

        # --- Ambiguous break detection ---
        if stripped and stripped[-1] in ".?!:" and len(stripped) < min_paragraph_chars:
            ambiguous_breaks.append({
                "line": i + 1,
                "text": stripped[:80],
            })

        result.append(line)

        # Count paragraph boundaries (blank lines or sentence-ending lines)
        if not stripped or _cierra_frase(stripped):
            total_paragraphs += 1

        i += 1

    # ── LA FRASE QUE ACABA SIN LLENAR LA LÍNEA CIERRA PÁRRAFO ────────────────────────────────
    # Solo para fuentes que emiten UNA LÍNEA DE COLUMNA por bloque (el HTML de PT desde 2010, el
    # de MX): ahí las líneas de un mismo párrafo van con salto simple y el merge las une, pero
    # cuando el párrafo termina no queda ninguna señal de que ha terminado — el salto sobrevive
    # como un corte dentro del párrafo. Era el 67,6 % de los que quedaban en PT.
    # El criterio es el clásico de composición: si la línea cierra frase Y NO llega al ancho de
    # la caja, sobra sitio y por tanto el párrafo acabó ahí; si lo llena, es coincidencia y el
    # texto sigue. Va al final, después del merge, para no interferir con él.
    if split_at_sentence_end:
        _L, _o = "\n".join(result).split("\n"), []
        for _i, _ln in enumerate(_L):
            _o.append(_ln)
            _s = _ln.rstrip()
            if not _s or _i + 1 >= len(_L):
                continue
            _nx = _L[_i + 1].lstrip()
            if (_nx and _cierra_frase(_s) and len(_s) < min_paragraph_chars
                    and (_nx[:1].isupper() or _nx[:1] in "—–«¿¡")):
                _o.append("")
        result = _o

    final_text = "\n".join(result)
    # ── SALIDA FLUIDA (opt-in: correct.flow_output) ───────────────────────────────────────────
    # La capa corrected de referencia (CL, GATE A) sale a COLUMNA 0 con blanca única entre
    # párrafos (0,0 % de líneas sangradas). La sangría es señal de párrafo DURANTE el merge
    # (indent_aware, collapse_layout_blanks) — por eso esto va al FINAL, cuando ya no informa:
    # dejarla rompía además los patrones de tag anclados a `^O SR` (BR).
    if flow_output:
        final_text = re.sub(r"(?m)^[ \t]+", "", final_text)
        final_text = re.sub(r"\n{3,}", "\n\n", final_text)
    return final_text, {
        "hyphen_joins": hyphen_joins,
        "short_merges": short_merges,
        "indent_mode": indent_mode,
        "indent_joins": indent_joins,
        "headings_isolated": heading_isolated,
        "layout_blank_joins": layout_blank_joins,
        "ambiguous_breaks": ambiguous_breaks,
        "total_paragraphs": total_paragraphs,
    }


# Frontera REAL de turno en marcadores narrativa+cita (DO): un cierre de comilla `”`/`"` O unos
# puntos suspensivos `...`/`…` (interrupción, la cita quedó abierta), SEGUIDOS de una narrativa
# nueva en mayúscula que lleva a `: “` (un marcador). El lookahead exige el `: “` para no partir
# unos puntos suspensivos a media frase del mismo orador. `[^“”\n]` impide cruzar una cita.
_TURN_BOUND = __import__("re").compile(
    r'([”"]|\.\.\.|…)([\s.,;]*)(?=[A-ZÁÉÍÓÚÑ¿¡][^“”\n]{4,230}?:\s*[“"])')


def separa_turnos_por_cita(text: str, blancos: int = 2) -> str:
    """Separa turnos en su frontera real (cierre de cita o interrupción por `...`), manteniendo
    «nombre … manifestó: "cita"» junto. Aislar por el ':' partía el nombre del marcador (DO).
    `blancos` líneas en blanco (2-3 saltos) para que ninguna etapa posterior las borre."""
    sep = "\n" * (blancos + 1)
    return _TURN_BOUND.sub(lambda m: m.group(1) + sep, text)


def quita_mobiliario_periodico(text: str, protect_res: list, min_rep: int = 8,
                               max_len: int = 70, min_gap: int = 12, max_gap: int = 600,
                               dispersion: float = 0.30) -> tuple[str, int, list]:
    """Detector POSICIONAL de mobiliario de página (enfoque exigido por el investigador,
    ES 2026-08-24: «con solo contar las líneas de cada página ante regularidades de cada
    archivo ya se puede ver dónde están y qué son»).

    Una FORMA de línea (dígitos→#, espacios plegados) que se repite ≥min_rep veces con
    espaciado CASI CONSTANTE (≈ la página; mediana de gaps en [min_gap, max_gap] y
    MAD ≤ dispersion·mediana) es mobiliario corrido — se haya comido el OCR lo que sea:
    el discriminador es la POSICIÓN, no el contenido (la lección de la CAJA de PY). El
    habla repetida («Muchas gracias.») no es periódica: llega en rachas y su MAD explota.
    Se mide POR ARCHIVO (cada archivo su regularidad). Los marcadores protegidos nunca
    se tocan. Corre ANTES del merge y de la deshifenización: así la frase cortada por la
    página se reúne limpia. Devuelve (texto, líneas retiradas, formas [(shape, n)])."""
    from collections import defaultdict as _dd
    lineas = text.split("\n")
    pos = _dd(list)
    for i, l in enumerate(lineas):
        s = l.strip()
        if 3 <= len(s) <= max_len:
            pos[re.sub(r"\d+", "#", re.sub(r"\s+", " ", s))].append(i)
    fuera: set = set()
    formas = []
    for shape, ps in pos.items():
        if len(ps) < min_rep:
            continue
        # ⚠ guardia de CONTENIDO además de la posicional: el mobiliario lleva DÍGITOS
        # (fecha, folio, NÚM) o va todo en VERSALES (CONGRESO); el habla procedimental
        # repetida no («Comienza la votación. (Pausa.)» — 6 votaciones casualmente
        # equiespaciadas pasaban el test posicional con pocas repeticiones)
        if "#" not in shape and not shape.isupper():
            continue
        # el mobiliario jamás EMPIEZA en minúscula: «emitidos, #; a favor, #; abstenciones,
        # una.» son RECUENTOS DE VOTACIÓN (llevan dígitos y 8 votaciones cayeron
        # equiespaciadas — muestra ES 1990-05-31); la continuación envuelta en minúscula
        # nunca es cabecero
        if shape[:1].islower():
            continue
        gaps = sorted(b - a for a, b in zip(ps, ps[1:]))
        med = gaps[len(gaps) // 2]
        if not (min_gap <= med <= max_gap):
            continue
        mad = sorted(abs(g - med) for g in gaps)[len(gaps) // 2]
        if mad > dispersion * med:
            continue
        if _is_protected(lineas[ps[0]].strip(), protect_res):
            continue
        fuera.update(ps)
        formas.append((shape[:60], len(ps)))
    if not fuera:
        return text, 0, []
    return ("\n".join(l for i, l in enumerate(lineas) if i not in fuera),
            len(fuera), sorted(formas, key=lambda x: -x[1]))


def quita_mobiliario_inline(text: str, inline_res: list, maxlen: int = 80) -> tuple[str, int]:
    """Quita mobiliario/cabecero EMBEBIDO a mitad de línea (re.sub por BÚSQUEDA, no por línea entera).

    Para el cabecero corrido que la página incrusta DENTRO de una frase —ES: «<día> DE <MES> DE <año>
    .-NÚM. <n>» interleado a mitad de oración—. Distinto de `quita_mobiliario` (que borra LÍNEAS
    enteras ancladas a `^`): aquí el patrón va dentro de la línea, se reemplaza por un espacio y se
    reúne la frase. Portado de `~/reocr_ec/faseA_es_numheader.py`.

    ⚠ Guardarraíl `maxlen`: un match más largo que `maxlen` probablemente tragó texto real → se
    DESCARTA (queda intacto). El patrón debe ser ESPECÍFICO y anclado a una forma de mobiliario
    (`DE <año> .- NÚM <n>`); un patrón laxo mid-text se come prosa. El guion pegado a letra (`res-`)
    NO se toca aquí: lo une la deshifenización posterior. Verificar por país con muestra.
    """
    if not inline_res:
        return text, 0
    total = 0
    for rx in inline_res:
        def _sub(m, _rx=rx):
            nonlocal total
            if len(m.group(0)) > maxlen:
                return m.group(0)               # anti-sobrecaptura: intacto
            total += 1
            return " "
        text = rx.sub(_sub, text)
    text = re.sub(r'[ \t]{2,}', ' ', text)      # colapsa espacios dobles del reemplazo (respeta \n)
    return text, total


def procesa_secuencia(text: str, cfg: dict) -> tuple[str, dict]:
    """SECUENCIA CANÓNICA de limpieza (5 pasos) sobre un texto, con la config de un país.
    Única fuente de verdad: la usan tanto la CLI (`main`) como el reproceso por lotes."""
    cfg = cfg or {}
    ccfg = cfg.get("correct", {}) or {}

    def _c(patrones):
        out = []
        for p in patrones or []:
            try:
                out.append(re.compile(p))
            except re.error:
                pass
        return out

    marker_res = _c(cfg.get("speaker_tag_patterns"))
    furniture_res = _c(ccfg.get("furniture_block"))
    furniture_line_res = _c(ccfg.get("furniture_line"))
    furniture_prefix_res = _c(ccfg.get("furniture_prefix"))
    furniture_masthead_res = _c(ccfg.get("furniture_masthead"))

    # PASOS 1-3 (mobiliario + separador) van sobre el texto SIN APLANAR: si un país aplana en sus
    # normalize_replacements (CO), hacerlo antes destruiría las líneas de mobiliario.
    # ⚠ ANTES del mobiliario: el tab inicial es LAYOUT (textutil lo emite en masa — CL era doc:
    # 411.216 líneas, 50.146 delante de un marcador) y rompe todo patrón anclado a `^`.
    # Opt-in por país (correct.strip_leading_tabs). Solo tabs INICIALES: los internos son
    # separadores de tabla (asistencia) y no se tocan.
    if ccfg.get("strip_leading_tabs", False):
        text = re.sub(r"(?m)^\t+", "", text)
    text, n_furn = quita_mobiliario(text, furniture_res, marker_res, furniture_line_res,
                                    furniture_prefix_res, furniture_masthead_res)
    # mobiliario EMBEBIDO a mitad de línea (ES: cabecero «… DE <año>.-NÚM. n» dentro de la frase)
    text, n_inline = quita_mobiliario_inline(text, _c(ccfg.get("furniture_inline")),
                                             maxlen=int(ccfg.get("furniture_inline_maxlen", 80)))
    n_furn += n_inline
    # COLA de guía de puntos del OCR (opt-in: correct.ocr_leader_tail). Va AQUÍ, con el resto
    # de la retirada de residuo y ANTES del merge: si se dejara para después, el merge une la
    # línea siguiente sobre la basura (la línea no cierra frase mientras la cola está puesta)
    # y la entierra a mitad de línea, donde ya ninguna pasada la ve.
    n_cola = car_cola = 0
    if ccfg.get("ocr_leader_tail"):
        text, n_cola, car_cola = recorta_cola_ocr(text)
        n_furn += n_cola
    # líneas de BASURA BINARIA (opt-in: correct.junk_line_ratio — ver quita_lineas_basura)
    if ccfg.get("junk_line_ratio"):
        text, n_junk = quita_lineas_basura(text, float(ccfg["junk_line_ratio"]),
                                           int(ccfg.get("junk_line_min_len", 8)))
        n_furn += n_junk
    # ── mobiliario POSICIONAL (opt-in: correct.furniture_periodic) — TODO el mobiliario se
    # retira ANTES de normalizar/unir/refluir (secuencia canónica, orden del investigador)
    n_periodic = 0
    formas_periodicas: list = []
    if ccfg.get("furniture_periodic"):
        # ⚠ `marker_join_next` va TAMBIÉN en la protección temprana (GT 2026-08-25). Ahí declara
        # cada país el PREFIJO de la cabeza de un marcador PARTIDO —«EL R. PRIMER VICEPRESIDENTE,
        # MALDONADO AGUIRRE, EN FUNCIONES DE» ⏎ «PRESIDENTE: Señores diputados…»—, y esa primera
        # línea no casa NINGÚN `speaker_tag_pattern` porque todos exigen el `:` final. Sin esto
        # queda desprotegida: es versal (pasa la guarda de contenido) y el presidente habla con
        # regularidad (pasa la de dispersión), así que el posicional la borra como si fuera
        # cabecero — y encima corre ANTES de `unir_marcador_partido`, que es quien la habría
        # rearmado. Añadir protección nunca puede retirar de más: solo impide borrados.
        _prot_early = _c(list(ccfg.get("marker_reassembly") or [])
                         + list(ccfg.get("protect_extra") or [])
                         + (list(ccfg.get("marker_join_next") or [])
                            + list(cfg.get("speaker_tag_patterns") or [])
                            if ccfg.get("protect_markers", True) else []))
        text, n_periodic, formas_periodicas = quita_mobiliario_periodico(text, _prot_early)
        n_furn += n_periodic
    text, n_norm = apply_normalizations(text, ccfg.get("normalize_replacements", []))
    text, n_join = reassemble_markers(text, ccfg.get("marker_reassembly", []))
    text, n_jn = unir_marcador_partido(text, ccfg.get("marker_join_next", []),
                                       cierre=ccfg.get("marker_join_terminator", ":"))
    n_join += n_jn
    # marcador EXPLOTADO en vertical (opt-in por país: correct.marker_join_vertical)
    text, n_jv = unir_marcador_vertical(text, ccfg.get("marker_join_vertical"),
                                        cierre_def=ccfg.get("marker_join_terminator", ":"),
                                        marker_res=marker_res)
    n_join += n_jv
    if ccfg.get("isolate_markers", True):
        text = separa_marcadores(text, marker_res)                                         # paso 4
    n_inline_marc = 0
    if ccfg.get("isolate_markers_inline"):
        text, n_inline_marc = separa_marcadores_inline(text, _c(ccfg["isolate_markers_inline"]))

    # protect_markers=False para países cuyo "marcador" es narrativa embebida que se ENVUELVE
    # (DO: «…Ana Isabel Bonilla Hernández, quien se» ⏎ «expresó: "…"»): protegerlo impide unir el
    # nombre con su ': "' y el tag pierde el orador. Ahí el matrix segmenta por ': "' de todos
    # modos, así que no hace falta proteger el marcador; sí el mobiliario/pase de lista.
    _prot = list(ccfg.get("marker_reassembly", []) or []) + list(ccfg.get("protect_extra", []) or [])
    if ccfg.get("protect_markers", True):
        _prot += list(cfg.get("speaker_tag_patterns", []) or [])
    protect_res = _c(_prot)
    corrected, stats = correct_text(                                                       # paso 5
        text,
        # null/ausente → se mide la caja; 0 (overlay era doc de CL) → merge de pares APAGADO:
        # en la era doc cada línea ES un párrafo completo y todo merge es una fusión
        min_paragraph_chars=ccfg.get("min_paragraph_chars"),
        min_paragraph_chars_max=ccfg.get("min_paragraph_chars_max"),
        join_hyphens=bool(ccfg.get("hyphen_join", True)),
        protect_res=protect_res,
        marker_hyphen_prefixes=ccfg.get("marker_hyphen_prefixes", []) or [],
        paragraph_accumulate=bool(ccfg.get("paragraph_accumulate", False)),
        pairs_merge_full_lines=bool(ccfg.get("pairs_merge_full_lines", False)),
        merge_over_protected_after_comma=bool(
            ccfg.get("merge_over_protected_after_comma", False)),
        max_paragraph_chars=int(ccfg.get("max_paragraph_chars", 2000) or 2000),
        split_at_sentence_end=bool(ccfg.get("split_at_sentence_end", False)),
        marker_absorbs_below=bool(ccfg.get("marker_absorbs_below", False)),
        merge_indent_aware=bool(ccfg.get("merge_indent_aware", False)),
        heading_own_paragraph=ccfg.get("heading_own_paragraph"),
        collapse_layout_blanks=bool(ccfg.get("collapse_layout_blanks", False)),
        collapse_layout_blanks_ratio=float(ccfg.get("collapse_layout_blanks_ratio", 0.30)),
        flow_output=bool(ccfg.get("flow_output", False)),
    )
    # ── SEGUNDO pase de mobiliario EMBEBIDO, ya POST-merge ────────────────────────────────
    # El primero corre antes del merge y su patrón no cruza saltos ([^\n]): el cabecero que el
    # extracted trae PARTIDO en dos líneas («SESION loa, EN MARTES 6 DE ⏎ NOVIEMBRE DE 1990 947»)
    # solo existe entero DESPUÉS de que el merge lo funda dentro de la frase — 4 supervivientes
    # con match comprobado en C19901106_10 (lector adversarial CL iter-6). Idempotente.
    corrected, n_inline2 = quita_mobiliario_inline(
        corrected, _c(ccfg.get("furniture_inline")),
        maxlen=int(ccfg.get("furniture_inline_maxlen", 80)))
    n_furn += n_inline2
    stats["normalizations_applied"] = n_norm
    stats["periodic_furniture_removed"] = n_periodic
    stats["periodic_shapes"] = formas_periodicas[:12]
    stats["marker_joins"] = n_join
    stats["inline_markers_isolated"] = n_inline_marc
    stats["furniture_removed"] = n_furn
    stats["ocr_leader_tail_lines"] = n_cola
    stats["ocr_leader_tail_chars"] = car_cola
    # unir los TÍTULOS en versales partidos por el ancho de columna (Fase A.7); opt-in por país,
    # con guardarraíles conservadores (nunca une pase de lista / tabla / roster / índice / OCR).
    if ccfg.get("join_split_titles", False):
        try:
            from unir_titulos_partidos import unir_titulos
        except ImportError:
            import os as _os, sys as _sys
            _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
            from unir_titulos_partidos import unir_titulos
        corrected, n_titulo = unir_titulos(corrected)
    # ── UNIR BLOQUES DE TÍTULO (opt-in: correct.join_title_blocks — petición del investigador,
    # ES 2026-08-24): el ítem del orden del día debe quedar en UNA línea HASTA el «(Número de
    # expediente …)» inclusive. El bloque son párrafos consecutivos en VERSALES-dominantes que
    # arrancan en «— » (el ítem), siguen con la pregunta «¿…?» en versales y cierran con el
    # paréntesis de expediente. Un nuevo «— » corta el bloque (ítems en secuencia del sumario);
    # los marcadores protegidos jamás se absorben.
    if ccfg.get("join_title_blocks", False):
        _RX_EXP = re.compile(r"^\(N[úu]mero de expediente[^)\n]{1,50}\)\s*\.?\s*$", re.I)
        def _caps_dom(s):
            lets = [c for c in s if c.isalpha()]
            return len(s) >= 6 and lets and sum(1 for c in lets if c.isupper()) / len(lets) >= 0.8
        _L3 = corrected.split("\n")
        _O3: list = []
        _n_blq = 0
        _i3 = 0
        while _i3 < len(_L3):
            _s = _L3[_i3].strip()
            # ⚠ sin _is_protected en el ARRANQUE: la protección por defecto trata «guion +
            # MAYÚSCULA» como marcador, y el ítem del orden del día ES esa forma
            if re.match(r"^[—–-]\s+", _s) and _caps_dom(_s):
                _blq = [_s]
                _j3, _usa = _i3 + 1, 0
                while _j3 < len(_L3) and _usa < 6:
                    _nx = _L3[_j3].strip()
                    if not _nx:
                        _j3 += 1
                        continue
                    if _RX_EXP.match(_nx):
                        _blq.append(_nx)
                        _j3 += 1
                        break
                    if _caps_dom(_nx) and not re.match(r"^[—–-]\s+", _nx) \
                            and not _is_protected(_nx, protect_res):
                        _blq.append(_nx)
                        _usa += 1
                        _j3 += 1
                        continue
                    break
                if len(_blq) > 1:
                    if _O3 and _O3[-1].strip():
                        _O3.append("")
                    _O3.append(" ".join(_blq))
                    _O3.append("")
                    _n_blq += 1
                    _i3 = _j3
                    continue
            _O3.append(_L3[_i3])
            _i3 += 1
        corrected = "\n".join(_O3)
        stats["title_blocks_joined"] = _n_blq
    # ── AISLAR TÍTULOS (opt-in por país: correct.isolate_titles = regex) ─────────────────
    # Los epígrafes numerados en VERSALES («23.AUTORIZACION PARA QUE…») van con línea en
    # blanco ANTES y DESPUÉS (petición del investigador, CL 2026-08-23, ronda 11). Corre al
    # FINAL (post-merge y post-unir_titulos) para ver el título ya reensamblado en una línea.
    _iso_tit = ccfg.get("isolate_titles")
    if _iso_tit:
        _rx_tit = re.compile(_iso_tit)
        _L2, _O2 = corrected.split("\n"), []
        _i2 = 0
        while _i2 < len(_L2):
            _ln = _L2[_i2]
            if _rx_tit.match(_ln.strip()):
                if _O2 and _O2[-1].strip():
                    _O2.append("")
                # El título puede continuar en líneas VERSALES (incluso tras punto:
                # «…ESE PAIS.» ⏎ «PROYECTO DE ACUERDO SOBRE LA MATERIA») — se absorben
                # hasta 3 líneas caps-dominantes que no sean marcador (CL ronda 13).
                _tit = _ln.rstrip()
                _k2 = 0
                while _i2 + 1 < len(_L2) and _k2 < 3:
                    _nx = _L2[_i2 + 1].strip()
                    _lets = [c for c in _nx if c.isalpha()]
                    if (len(_nx) >= 6 and _lets
                            and sum(1 for c in _lets if c.isupper()) / len(_lets) >= 0.8
                            and not _is_protected(_nx, protect_res)):
                        _tit += " " + _nx
                        _i2 += 1; _k2 += 1
                    else:
                        break
                _O2.append(_tit)
                _O2.append("")
                _i2 += 1
                continue
            if _ln.strip() or not (_O2 and not _O2[-1].strip()):
                _O2.append(_ln)
            _i2 += 1
        corrected = "\n".join(_O2)
    # ── NORMALIZACIONES POST-merge (opt-in: correct.normalize_post) ──────────────────────
    # Para artefactos que solo EXISTEN tras el merge — p.ej. la referencia duplicada en
    # costura de página cuya primera copia venía partida en dos líneas del extracted y solo
    # es adyacente a su gemela después de unir (CL, lector adversarial iter-1).
    # ── BLANCO ENTRE PÁRRAFOS (opt-in: correct.paragraph_blank_min = longitud mínima) ────
    # Convención única: línea que CIERRA frase y mide ≥N va seguida de línea en blanco si lo
    # siguiente arranca párrafo (mayúscula/¿¡«). Por LÍNEAS y con guarda de longitud para no
    # partir abreviaturas ni listas cortas (iter-2 del lector: 38 junturas mixtas).
    _pbm = ccfg.get("paragraph_blank_min")
    if _pbm:
        _L3, _O3 = corrected.split("\n"), []
        for _k3, _ln in enumerate(_L3):
            _O3.append(_ln)
            _s3 = _ln.rstrip()
            if (len(_s3) >= int(_pbm) and _s3.endswith((".", "!", "?", "…", "»", "”"))
                    and _k3 + 1 < len(_L3) and _L3[_k3 + 1].strip()
                    and _L3[_k3 + 1].lstrip()[:1] in "ABCDEFGHIJKLMNOPQRSTUVWXYZÁÉÍÓÚÜÑ¿¡«\"“0123456789"):
                _O3.append("")
        corrected = "\n".join(_O3)
    _np = ccfg.get("normalize_post")
    if _np:
        corrected, _n_np = apply_normalizations(corrected, _np)
        stats["normalizations_applied"] = stats.get("normalizations_applied", 0) + _n_np
    if ccfg.get("turn_split_after_quote"):
        corrected = separa_turnos_por_cita(corrected, int(ccfg.get("turn_split_blanks", 2)))
    return corrected, stats


def main():
    parser = argparse.ArgumentParser(description="Deterministic typographic correction")
    parser.add_argument("--input", required=True, help="Input text file")
    parser.add_argument("--output", required=True, help="Output text file")
    parser.add_argument("--config", default=None,
                        help="YAML del país (opcional): aplica correct.normalize_replacements")
    parser.add_argument("--min-paragraph-chars", type=int, default=0,
                        dest="min_paragraph_chars",
                        help="Threshold for 'short line' detection (default: 80)")
    parser.add_argument("--no-hyphen-join", action="store_true", dest="no_hyphen_join",
                        help="Disable hyphenation joining")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(json.dumps({"status": "error", "error": f"Not found: {input_path}"}))
        sys.exit(1)

    text = input_path.read_text(encoding="utf-8")
    cfg = {}
    if args.config and HAS_YAML and Path(args.config).exists():
        cfg = yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}
    corrected, stats = procesa_secuencia(text, cfg)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(corrected, encoding="utf-8")

    stats["status"] = "ok"
    stats["output"] = str(output_path)
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
