#!/usr/bin/env python3
"""
Extract clean text from digital PDFs, OCR page dirs, or HTML files.

La extracción es PAGE-AWARE: arma una lista de páginas y, antes de unirlas, aplica
eliminación de CABECEROS y PIES recurrentes (strip_headers.py) — el único punto del
pipeline donde la frontera de página está intacta y AGUAS ABAJO del OCR (los page_*.txt
ya producidos se reutilizan; el OCR no se reprocesa).

CLI:
    python extract_text.py --input <path> \
        --source-format <pdf_digital|ocr_pages|html> \
        [--ocr-dir <dir>] [--config <yaml>] [--strip-headers (legado)] \
        --output <path>
"""
import sys
import json
import argparse
import re
import html as _html_lib
import unicodedata
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent))  # para importar strip_headers (mismo dir)

try:
    import fitz  # PyMuPDF
    HAS_FITZ = True
except ImportError:
    HAS_FITZ = False

try:
    from docx import Document as _DocxDocument  # python-docx
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

from strip_headers import strip_running_furniture, strip_text


# ── helpers ──────────────────────────────────────────────────────────────────

class _HTMLTextExtractor(HTMLParser):
    """Minimal HTML → plaintext stripper."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        # Solo contenedores con texto a descartar. NO incluir elementos void
        # (meta, link, br): no se cierran, así que en HTML no-XHTML (sin "/>")
        # solo disparan starttag y dejarían el contador de skip atascado en >0,
        # descartando todo el body. Los void no emiten handle_data de todas formas.
        self._skip_tags = {"script", "style", "head"}
        self._current_skip = 0
        self._in_pre = 0

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t == "body":
            self._current_skip = 0  # robustez: head/meta sin cerrar no deben tapar el body
        if t in self._skip_tags:
            self._current_skip += 1
        if t == "pre":
            self._in_pre += 1
        # ⚠ EL BLOQUE ABRE PÁRRAFO, EL <br> SOLO SALTA DE LÍNEA. Antes ambos emitían un `\n`
        # y la frontera de párrafo dependía de que el fichero trajera un salto entre `</p>` y
        # `<p>` — es decir, de cómo estuviera FORMATEADO el HTML, no de su estructura.
        if t in {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"}:
            self._parts.append("\n\n")
        elif t == "br":
            self._parts.append("\n")

    def handle_endtag(self, tag):
        t = tag.lower()
        if t in self._skip_tags:
            self._current_skip = max(0, self._current_skip - 1)
        if t == "pre":
            self._in_pre = max(0, self._in_pre - 1)
        if t in {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"}:
            self._parts.append("\n\n")

    def handle_data(self, data):
        if self._current_skip == 0:
            # ⚠⚠ EN HTML EL WHITESPACE DEL CONTENIDO SE COLAPSA. Un salto de línea dentro de un
            # `<p>` es formateo del fichero, no del documento: el navegador lo renderiza como un
            # espacio. Conservarlo parte el párrafo por donde está cortada la línea del fuente.
            # En MX el 85 % de los `<p>` traen saltos literales y solo el 1 % un `<br>` de verdad
            # — eran 181.670 saltos intra-párrafo en 30 sesiones de 2010 contra 0 en las de 1980.
            # Dentro de `<pre>` sí es significativo y se respeta.
            self._parts.append(data if self._in_pre else re.sub(r"\s+", " ", data))

    def get_text(self) -> str:
        return "".join(self._parts)


def _strip_html(html_content: str) -> str:
    extractor = _HTMLTextExtractor()
    extractor.feed(html_content)
    text = extractor.get_text()
    # ⚠⚠ VACIAR LAS LÍNEAS DE SOLO-ESPACIO ANTES DE COLAPSAR. El colapso de whitespace deja un
    # espacio suelto donde el fichero tenía el salto entre `</p>` y `<p>`, y ese espacio queda
    # DELANTE del marcador de orador. Los `speaker_tag_patterns` anclan a `^`, así que con un
    # espacio por delante no casan y el turno entero se pierde: en MX bajaba de 15.257
    # marcadores a 3.749 sin que faltara un solo carácter de texto. Además `\n \n` no casa con
    # `\n{3,}`, así que sin el strip las líneas «vacías» conservan su espacio. La rama con
    # `container` de extract_html ya hacía esto; esta no.
    text = "\n".join(l.strip() for l in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _valid_ratio(text: str) -> float:
    """Proportion of chars that are NOT control chars (ord<32 except \\n\\t) nor PUA (0xE000–0xF8FF)."""
    if not text:
        return 1.0
    valid = 0
    for c in text:
        o = ord(c)
        if o < 32 and c not in ("\n", "\t"):
            continue  # control char — not valid
        if 0xE000 <= o <= 0xF8FF:
            continue  # PUA — not valid
        valid += 1
    return valid / len(text)


def extract_pdf_digital(pdf_path: Path, sort: bool = False) -> list[str]:
    """Devuelve la lista de páginas (texto) de un PDF con texto embebido.

    `sort=True` → `get_text(sort=True)`: reordena los spans por posición. Necesario en PDFs
    modernos cuyo orden interno de spans fragmenta las líneas (CL 2020-2025: mediana de línea
    26 → 79 car). NO usarlo por defecto: en PDFs sanos puede reordenar columnas legítimas.
    Se activa con --pdf-sort (el SKILL decide por era, registrada en el config del país)."""
    if not HAS_FITZ:
        raise ImportError("PyMuPDF (fitz) is required for pdf_digital extraction")
    doc = fitz.open(str(pdf_path))
    pages = [page.get_text("text", sort=True) if sort else page.get_text("text") for page in doc]
    doc.close()
    return pages


def extract_ocr_pages(ocr_dir: Path) -> list[str]:
    """Devuelve la lista de páginas: cada page_*.txt ya producido por el OCR es una página.

    Limpia el énfasis MARKDOWN que LightOnOCR-2 emite de forma sistemática (envuelve los
    turnos de orador y encabezados en negrita: "**H.L. NOMBRE:**"). Sin este strip, los
    marcadores `**` rompen el regex de tagging (el prefijo deja de anclar al inicio de línea).
    Es un artefacto del modelo, no del contenido → se elimina siempre en la capa OCR."""
    txt_files = sorted(ocr_dir.glob("page_*.txt"))
    if not txt_files:
        raise FileNotFoundError(f"No page_*.txt files found in {ocr_dir}")
    return [f.read_text(encoding="utf-8").replace("**", "").replace("__", "")
            for f in txt_files]


# Caracteres de texto español "normal" (letras con/sin acento, dígitos, puntuación común).
# La fracción de caracteres dentro de este set es una medida ESTABLE de "español limpio":
# el mojibake reemplaza letras acentuadas por símbolos fuera del set, bajando la fracción.
_NORMAL_ES = set(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    "ÁÉÍÓÚÜÑáéíóúüñ"
    "0123456789"
    " \t\n.,;:()[]¿?¡!«»\"'`-–—/%ºª°&#@"
)
# Pares (origen, destino) para revertir el mojibake. Cada flavor es la inversa de un
# mis-decode (p.ej. bytes Latin-1 leídos como Mac-Roman → revertir con mac_roman→latin-1).
_ENC_CANDIDATES = [("mac_roman", "latin-1"), ("mac_roman", "cp1252"),
                   ("cp1252", "mac_roman"), ("latin-1", "mac_roman")]
_CLEAN_RATIO = 0.97  # ratio de texto-normal por encima del cual se asume limpio (fast path)
# firma de mojibake Mac-Roman DENTRO de palabra («Gonz·lez», «JimÈnez», «LÛpez», «CaÒas»,
# «Nœmero»): inexistente en español/portugués limpios; ≥5 apariciones anulan el fast path
_MOJI_SIG = re.compile(r"[A-Za-zÁÉÍÓÚÑáéíóúñ][·ÈÌÛÒœ‡ÊŸ˙˚¸∑€Δ][A-Za-zÁÉÍÓÚÑáéíóúñ]")
# el MISMO flavor en VERSALES cae en glifos de tipografía normal y era INVISIBLE al ratio:
# Á→¡ («W¡LTER») É→… Í→Õ («MARÕA», «VÕCTOR») Ó→” Ú→⁄ Ü→‹ Ñ→— («A—A»=AÑA, «SE—OR»).
# ⚠ El contexto es VERSAL a ambos lados a propósito: «pero…y» entre minúsculas es puntos
# suspensivos TEXTUALES legítimos, no mojibake (medido: a…p/s…a/o…y en CR).
# ⚠ La RAYA solo es firma entre VOCALES («MU—OZ», «A—A», «SE—OR»): la Ñ española vive entre
# vocales, y así «LEY—QUE» (raya legítima sin espacios) jamás se convierte en «LEYÑQUE».
_MOJI_SIG_VERSAL = re.compile(r"[A-ZÁÉÍÓÚÑ][¡…Õ”“⁄‹][A-ZÁÉÍÓÚÑ]|[AEIOUÁÉÍÓÚ]—[AEIOU]")

# ANOMALÍA general para PUNTUAR candidatos: cualquier no-letra (salvo . ' ’ - – — y dígitos,
# por «S.A.», «O'CONNOR», «McGREGOR» vía la rama de minúscula que puntúa igual en identity y
# candidato) o una MINÚSCULA entre dos versales. Existe porque la firma sola se puede LAVAR:
# el candidato inverso (cp1252→mac_roman) convertía ¡→° y —→ó — no repara, pero reducía las
# firmas con el ratio empatado y GANABA («W¡LTER»→«W°LTER», «MU—OZ»→«MUóOZ»). Con la
# anomalía, el lavado empata (°/ó siguen siendo anómalos entre versales) y no puede ganar;
# solo la reparación real (Á/Ñ) baja a cero. La raya queda FUERA de la anomalía: solo cuenta
# como firma en contexto vocal—vocal, para que «LA LEY—QUE» jamás se convierta en «LEYÑQUE».
_ANOM_VERSAL = re.compile(r"[A-ZÁÉÍÓÚÜÑ](?:[a-záéíóúüñ]|[^\w .'’\-–—])[A-ZÁÉÍÓÚÜÑ]")


def _sig_count(s: str) -> int:
    """Firmas PRECISAS de mojibake (gatillo de reparación)."""
    return len(_MOJI_SIG.findall(s)) + len(_MOJI_SIG_VERSAL.findall(s))


def _anom_count(s: str) -> int:
    """Anomalías para PUNTUAR candidatos (incluye el lavado que la firma no ve)."""
    return len(_MOJI_SIG.findall(s)) + len(_ANOM_VERSAL.findall(s)) + \
        len(re.findall(r"[AEIOUÁÉÍÓÚ]—[AEIOU]", s))


# Set para PUNTUAR candidatos por línea: incluye además la tipografía legítima que el flavor
# versal usa como destino (… “ ” ¡ — ya está —/–/¡ en _NORMAL_ES). Así convertir un «…»
# textual en «É» NO gana ratio (corrompería «pero… y» → «peroÉ y»): la reparación versal
# solo puede ganar por REDUCCIÓN DE FIRMA, que exige el contexto versal inequívoco.
_SCORE_EXTRA = set("…“”¡")


def _score_ratio(text: str) -> float:
    return (sum(c in _NORMAL_ES or c in _SCORE_EXTRA for c in text) / len(text)
            if text else 0.0)


def _normal_ratio(text: str) -> float:
    """Fracción de caracteres que son texto español normal. Métrica estable de limpieza:
    alta en texto correcto, baja en mojibake (que mete símbolos fuera del set)."""
    return sum(c in _NORMAL_ES for c in text) / len(text) if text else 0.0


def _transcode(text: str, src: str, dst: str) -> str:
    """Aplica la reversa de un mis-decode, carácter a carácter (sin pérdida: los
    caracteres no codificables en `src` se dejan intactos)."""
    out = []
    for ch in text:
        if ch in ("\n", "\t"):
            out.append(ch); continue
        try:
            out.append(ch.encode(src).decode(dst))
        except (UnicodeEncodeError, UnicodeDecodeError):
            out.append(ch)
    return "".join(out)


def repair_legacy_encoding(text: str) -> str:
    """Repara mojibake de codificación heredada AUTO-DETECTANDO el flavor por documento.

    Las conversiones .doc→.docx antiguas producen mojibake HETEROGÉNEO incluso dentro de
    un mismo año (visto en actas CR 1994-1996: unos archivos limpios y otros con bytes
    Latin-1 leídos como Mac-Roman → 'á'→'·','ó'→'Û', o variantes 'á'→'∑','ó'→'€'). Un
    único sentido de reparación corrompe los que no lo necesitan, así que NO se aplica
    a ciegas por año.

    Estrategia idempotente y segura, guiada por `_normal_ratio` (fracción de texto español
    normal): si el texto ya luce limpio (ratio >= 0.97) se devuelve intacto (fast path →
    los archivos correctos NUNCA se tocan). Si no, se prueban los candidatos de
    transcodificación y se elige el de mayor ratio; identity gana los empates, así que solo
    se transforma cuando una candidata supera ESTRICTAMENTE a no-tocar."""
    base = _normal_ratio(text)
    # ⚠ El fast path por ratio GLOBAL deja pasar el mojibake DILUIDO: un acta grande con
    # miles de glifos rotos sigue midiendo >= 0.97 (CR 1994-06-08: 3.265 glifos en 291 k car
    # = 1,1% → «limpio»). Segundo gatillo por FIRMA: glifo Mac-Roman ENTRE letras
    # («Gonz·lez», «CaÒas», «LÛpez») — esa forma no existe en español limpio. Con firma
    # presente se salta el fast path y deciden los candidatos (que solo ganan si el ratio
    # mejora ESTRICTAMENTE, así que un falso positivo de firma no corrompe nada).
    if base >= _CLEAN_RATIO and _sig_count(text) == 0:
        return text  # ya limpio → idempotente, sin riesgo de re-corromper
    # ⚠ Reparación POR PÁRRAFO, no global: las conversiones antiguas MEZCLAN tramos limpios
    # y rotos en el MISMO archivo (CR 1994-04-30_122: 804 firmas repartidas del 0% al 100%
    # de la posición). El candidato global perdía ahí: transcodificar corrompe los tramos
    # limpios (á→‡) y esa pérdida compensa la ganancia de los rotos → identity ganaba y el
    # archivo quedaba entero sin reparar. Por párrafo, cada tramo decide solo; el limpio
    # (ratio alto y sin firma) ni se toca.
    # ⚠ Puntuación LEXICOGRÁFICA (ratio, −firmas): el flavor VERSAL mapea a tipografía
    # normal (MU—OZ, MARÕA) y el ratio EMPATA — el desempate es la reducción de firma.
    # El ratio va primero: si el candidato corrompe acentos legítimos (Ú→ò), pierde
    # aunque quite firmas.
    def _mejor(s: str) -> str:
        best, best_key = s, (_score_ratio(s), -_anom_count(s))
        for src, dst in _ENC_CANDIDATES:
            cand = _transcode(s, src, dst)
            key = (_score_ratio(cand), -_anom_count(cand))
            if key > best_key:
                best, best_key = cand, key
        return best

    out = []
    for ln in text.split("\n"):
        if not ln.strip() or (_score_ratio(ln) >= _CLEAN_RATIO and _sig_count(ln) == 0):
            out.append(ln)
            continue
        ln = _mejor(ln)
        # ⚠ Pase por PALABRA para la línea MIXTA: «EL DIPUTADO W¡LTER MU—OZ CÉSPEDES:» tiene
        # rotos Y acentos legítimos — la transcodificación de la línea ENTERA corrompe el É
        # legítimo (É→ƒ) y ningún candidato gana; por token, solo los que llevan firma se
        # reparan («W¡LTER»→«WÁLTER») y «CÉSPEDES» ni se toca.
        if _sig_count(ln):
            ln = " ".join(_mejor(tok) if _sig_count(tok) else tok
                          for tok in ln.split(" "))
        out.append(ln)
    return "\n".join(out)


_NORMAL_TEXT = set(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    "ÁÉÍÓÚÜÑáéíóúüñÀÃÂÊÍÔÕÇàãâêíôõç"
    "0123456789"
    " \t.,;:()[]¿?¡!«»\"'`-–—/%°ºª$€&#@*+="
)


_RUN4 = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{4,}")


def _looks_like_text(line: str) -> bool:
    """True si el párrafo parece prosa/cabecera real (no basura binaria/field-code).
    Test POSITIVO: contiene un run de >=4 letras latinas seguidas Y la fracción de
    caracteres fuera del set de texto normal es baja (<25%). Robusto frente a glifos
    de basura (±∞®¢) que Python clasifica como alfabéticos. Usado SOLO para localizar
    el primer párrafo legible y descartar el run inicial de basura previo."""
    s = line.strip()
    if len(s) < 4 or not _RUN4.search(s):
        return False
    weird = sum(1 for c in s if c not in _NORMAL_TEXT)
    return weird / len(s) < 0.25


def extract_docx(docx_path: Path, legacy_fix: bool = True) -> str:
    """Lee un .docx digital (párrafos vía python-docx) → texto plano (no paginado).

    - Une los párrafos con '\\n' (cada párrafo es una línea lógica del acta).
    - Descarta el run INICIAL de párrafos de basura binaria (field-codes de la
      conversión .doc→.docx antigua) hasta el primer párrafo legible.
    - Si legacy_fix=True (default) aplica repair_legacy_encoding(), que AUTO-DETECTA el
      flavor de mojibake por documento y NO toca los archivos ya limpios (idempotente).
      Por eso es seguro dejarlo activo en todos los años: no depende de una lista de años
      ni puede re-corromper texto correcto."""
    if not HAS_DOCX:
        raise ImportError("python-docx es necesario para source_format=docx (pip install python-docx)")
    doc = _DocxDocument(str(docx_path))
    paras = [p.text for p in doc.paragraphs]
    # descartar el run INICIAL de basura binaria hasta el primer párrafo legible
    # (preserva todo el cuerpo: solo busca el primer texto real desde el inicio)
    start = next((i for i, p in enumerate(paras) if _looks_like_text(p)), 0)
    text = "\n".join(paras[start:])
    if legacy_fix:
        text = repair_legacy_encoding(text)
    text = _drop_binary_blobs(text)
    return text


def _drop_binary_blobs(text: str) -> str:
    """Elimina líneas de basura binaria embebida (objetos OLE / bitmaps 'INCRUSTAR PBrush'
    volcados como texto: runs largos de 'ÿÿÿ…', '€€€…', control chars). En actas CR 1996
    estos blobs llegaban a superar en bytes a la prosa real. Señal inequívoca: línea larga
    con fracción de texto-normal muy baja. La prosa y los turnos de orador siempre superan
    0.8, así que el umbral 0.5 (con guarda de longitud) no toca contenido legítimo."""
    keep = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            keep.append(line); continue
        r = _normal_ratio(s)
        # blob largo (objeto OLE) o fragmento de basura pura (control chars / símbolos
        # sueltos). La puntuación y palabras cortas legítimas ("Sí.", "1)", "—") son
        # ratio≈1.0, así que el umbral 0.35 no las toca.
        if (len(s) >= 15 and r < 0.65) or r < 0.35:
            continue
        keep.append(line)
    return "\n".join(keep)


def _decode_html_bytes(raw: bytes) -> str:
    """Decodifica HTML respetando su charset declarado. Muchos diarios (p.ej. MX) son
    ISO-8859-1; leerlos como UTF-8 corrompe acentos/ñ y rompe nombres aguas abajo.
    Estrategia: 1) charset del <meta>; 2) UTF-8 estricto; 3) fallback cp1252/latin-1."""
    head = raw[:4096].decode("ascii", errors="ignore").lower()
    m = re.search(r'charset=["\']?\s*([a-z0-9_\-]+)', head)
    if m:
        enc = m.group(1).strip()
        try:
            return raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            pass
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def extract_html(html_path: Path, container: str | None = None,
                 stop_at: str | None = None, page_marker_class: str | None = None) -> str:
    """Extrae el texto de un HTML, opcionalmente ACOTADO a un contenedor.

    ⚠ Sin `container`, convierte la página ENTERA y arrastra la navegación del sitio web: en el
    diario portugués salían «Debates Parlamentares», «Menu» y cientos de líneas de solo espacios
    mezclados con el acta. El contenido real vive en un contenedor concreto —en PT
    `<div id="pageTextRaw">`, presente en el 100 % de los ficheros— y fuera de él no hay acta.

    · `container`         selector simple `id="x"` o `class="x"` donde empieza el contenido
    · `stop_at`           fragmento de atributo donde TERMINA (la columna lateral de la página)
    · `page_marker_class` class de los divs que marcan frontera de página; se convierten en el
                          marcador `---PAGE---`, que aguas abajo permite limpiar mobiliario.

    La separación de párrafo se preserva convirtiendo `</p>` y `<br>` en línea en blanco: es la
    señal que distingue un fin de párrafo de un corte por el ancho de columna, y sin ella la etapa
    `correct` no puede decidir. En PT sale al 51 %."""
    if container:
        raw = _decode_html_bytes(html_path.read_bytes())
        m = re.search(rf'<div[^>]*{container}[^>]*>(.*)', raw, re.S | re.I)
        if m:
            h = m.group(1)
            if stop_at:
                c = re.search(rf'<div[^>]*{stop_at}', h, re.I)
                if c:
                    h = h[:c.start()]
            h = re.sub(r"(?is)<(script|style).*?</\1>", " ", h)
            # centinelas: las fronteras REALES se marcan antes de colapsar el whitespace,
            # para que el colapso no pueda borrarlas.
            if page_marker_class:
                h = re.sub(rf'(?i)<div[^>]*class="[^"]*{page_marker_class}[^"]*"[^>]*>',
                           "\x01", h)
            h = re.sub(r"(?i)</p\s*>|<br\s*/?>", "\x00", h)
            h = re.sub(r"<[^>]+>", "", h)
            h = _html_lib.unescape(h)
            # ⚠⚠ EL SALTO DE LÍNEA LITERAL DENTRO DE UN <p> NO ES UN SALTO DEL DOCUMENTO. HTML
            # colapsa el whitespace: el navegador lo renderiza como un espacio, y solo `<br>` y
            # `</p>` producen salto visible. Conservarlo PARTE el párrafo por donde el fichero
            # está formateado, no por donde el acta lo separa. En MX el 85 % de los `<p>` traen
            # saltos literales frente a un 1 % con `<br>` de verdad: eran 181.670 saltos
            # intra-párrafo en 30 sesiones de 2010, contra 0 en las de 1980 (que vienen en una
            # sola línea). `[ \t]+` no los tocaba porque `\n` no es ni espacio ni tabulador.
            h = re.sub(r"\s+", " ", h)
            h = h.replace("\x01", "\n---PAGE---\n").replace("\x00", "\n\n")
            # ⚠ ORDEN: hay que vaciar las líneas de solo-espacio ANTES de colapsar los saltos.
            # Al revés, `\n \n \n` no casa con `\n{3,}` y el resultado sale con series de
            # líneas «vacías» que en realidad contienen un espacio: en PT daba 79,7 % de vacías
            # y `strip_headers` abortaba por su guarda del 35 %, sin quitar un solo cabecero.
            h = "\n".join(l.strip() for l in h.split("\n"))
            h = re.sub(r"\n{3,}", "\n\n", h)
            return h.strip()
    return _extract_html_plano(html_path)


def _extract_html_plano(html_path: Path) -> str:
    content = _decode_html_bytes(html_path.read_bytes())
    return _strip_html(content)


def _load_strip_config(config_path: str | None) -> dict:
    """Lee la sección `extract:` del country_config + los speaker_patterns (top-level).
    Defaults si no hay config."""
    cfg = {
        "strip_headers": True,
        "edge": 3,
        "recurrence": 0.5,
        "similarity": 85,
        "min_pages": 4,
        "page_break_marker": "",
        "emit_page_marker": True,
        "page_marker_format": "---PAGE {n:04d}---",
        "protect_patterns": [],
        "extra_patterns": [],
        "speaker_patterns": [],   # derivado de speaker_tag_patterns + speaker_loose_pattern (modo frecuencia)
    }
    if config_path and HAS_YAML and Path(config_path).exists():
        data = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
        ex = (data.get("extract", {}) or {})
        for k in cfg:
            if k != "speaker_patterns" and k in ex and ex[k] is not None:
                cfg[k] = ex[k]
        # patrones de orador para excluir turnos en el modo frecuencia (no paginado sin marca)
        sp = list(data.get("speaker_tag_patterns", []) or [])
        loose = data.get("speaker_loose_pattern")
        if loose:
            sp.append(loose)
        cfg["speaker_patterns"] = sp
    return cfg


def main():
    parser = argparse.ArgumentParser(description="Extract clean text from PDF/OCR/HTML/flat-text")
    parser.add_argument("--input", required=True, help="Input file path")
    parser.add_argument(
        "--source-format",
        required=True,
        choices=["pdf_digital", "ocr_pages", "html", "text_flat", "docx"],
        dest="source_format",
        help="text_flat = texto de sesión ya extraído, sin paginar (modo marcador o frecuencia); "
             "docx = acta .docx digital (párrafos vía python-docx, no paginada)",
    )
    parser.add_argument("--ocr-dir", default=None, dest="ocr_dir",
                        help="Directory with page_*.txt (required for ocr_pages)")
    parser.add_argument("--pdf-sort", action="store_true", dest="pdf_sort",
                        help="pdf_digital: get_text(sort=True) — para PDFs cuyo orden de spans "
                             "fragmenta las líneas (p.ej. CL 2020-2025). Decidir por ERA en el SKILL.")
    parser.add_argument("--legacy-encoding-fix", action="store_true", dest="legacy_encoding_fix",
                        help="Repara mojibake Mac-Roman→CP1252 (solo docx de años con codificación corrupta)")
    parser.add_argument("--config", default=None,
                        help="YAML del país (opcional): aplica la sección extract.* (cabeceros/pies)")
    parser.add_argument("--no-strip-headers", action="store_true", dest="no_strip_headers",
                        help="Sin efecto (es ya el comportamiento por defecto); se acepta por compatibilidad")
    parser.add_argument("--strip-headers", action="store_true", dest="strip_headers",
                        help="LEGADO: reactiva la limpieza de cabeceros EN extract. El flujo "
                             "canónico (rediseño 2026-08) no limpia aquí: la limpieza es de "
                             "diaries-correct y extracted/ es la capa FIEL.")
    parser.add_argument("--output", required=True, help="Output text file path")
    parser.add_argument("--text-output", default=None, dest="text_output",
                        help=("TEXTO DE ORIGEN consolidado: el texto tal como sale de la fuente "
                              "—OCR, PDF digital, DOCX, HTML o .txt— con la frontera de página "
                              "marcada y NADA MÁS. Sin quitar cabeceros ni corregir. Es la base "
                              "reproducible de la que derivan extract y meta."))
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    scfg = _load_strip_config(args.config)
    # Rediseño 2026-08 (§1.1 del plan de reproceso): extract NO limpia por defecto.
    # Solo limpia si se pide EXPLÍCITAMENTE con --strip-headers (y el config no lo veta).
    do_strip = args.strip_headers and scfg["strip_headers"] and not args.no_strip_headers
    header_report = {"enabled": False}

    # ── text_flat / docx: texto de sesión SIN paginar (modo marcador o frecuencia) ──
    if args.source_format in ("text_flat", "docx"):
        if not input_path.exists():
            print(json.dumps({"status": "error", "error": f"Not found: {input_path}"}))
            sys.exit(1)
        if args.source_format == "docx":
            # auto-repair de codificación SIEMPRE: detecta el flavor por documento y
            # es idempotente (no toca los archivos limpios). El flag --legacy-encoding-fix
            # se mantiene por compatibilidad pero ya no es necesario.
            raw = extract_docx(input_path)
        else:
            raw = input_path.read_text(encoding="utf-8", errors="replace")
        if do_strip:
            raw, header_report = strip_text(
                raw,
                page_break_marker=(scfg["page_break_marker"] or None),
                speaker_patterns=scfg["speaker_patterns"],
                edge=int(scfg["edge"]),
                min_pages=int(scfg["min_pages"]),
                recurrence=float(scfg["recurrence"]),
                similarity=int(scfg["similarity"]),
                protect_patterns=scfg["protect_patterns"],
                extra_patterns=scfg["extra_patterns"],
            )

    # ── formatos PAGINADOS: arma páginas y aplica el detector page-aware antes de unir ──
    else:
        if args.source_format == "pdf_digital":
            if not input_path.exists():
                print(json.dumps({"status": "error", "error": f"Not found: {input_path}"}))
                sys.exit(1)
            pages = extract_pdf_digital(input_path, sort=args.pdf_sort)
        elif args.source_format == "ocr_pages":
            ocr_dir = Path(args.ocr_dir) if args.ocr_dir else input_path
            if not ocr_dir.is_dir():
                print(json.dumps({"status": "error", "error": f"Not a directory: {ocr_dir}"}))
                sys.exit(1)
            pages = extract_ocr_pages(ocr_dir)
        elif args.source_format == "html":
            if not input_path.exists():
                print(json.dumps({"status": "error", "error": f"Not found: {input_path}"}))
                sys.exit(1)
            pages = [extract_html(input_path)]  # no paginado → strip se auto-omite (min_pages)
        else:
            print(json.dumps({"status": "error", "error": "Unknown source_format"}))
            sys.exit(1)

        _paginas_origen = list(pages)      # ⚠ copia ANTES de limpiar: es el texto de origen
        if do_strip and args.source_format != "html":
            pages, header_report = strip_running_furniture(
                pages,
                edge=int(scfg["edge"]),
                min_pages=int(scfg["min_pages"]),
                recurrence=float(scfg["recurrence"]),
                similarity=int(scfg["similarity"]),
                protect_patterns=scfg["protect_patterns"],
                extra_patterns=scfg["extra_patterns"],
                # ⚠ Los patrones de orador NO se pasaban aquí: se recogían del config y solo se
                # usaban en la ruta de frecuencia. En la ruta paginada el detector de mobiliario
                # borraba marcadores. Ver la nota en strip_running_furniture.
                speaker_patterns=scfg["speaker_patterns"],
            )
            header_report["mode"] = "paginated"
        # ⚠ La frontera de página es la MEJOR señal para limpiar mobiliario, y hasta ahora
        # se usaba una vez (aquí, para quitar cabeceros) y se tiraba al unir con "\n\n".
        # Aguas abajo no había forma de recuperarla: un "\n\n" no distingue un salto de
        # página de uno de párrafo. Sin ella, en AR y PA un número suelto es indistinguible
        # del número de un punto del orden del día (medido: 18.677 y 22.871 líneas), y en PT
        # quedan 940 filas con la cabecera absorbida a mitad de línea que ya no se pueden
        # tocar. Emitir el marcador cuesta nada y deja la puerta abierta para siempre.
        marca = scfg.get("emit_page_marker", True)
        if marca and len(pages) > 1:
            plantilla = scfg.get("page_marker_format") or "---PAGE {n:04d}---"
            raw = ""
            for i, pg in enumerate(pages, 1):
                raw += ("" if i == 1 else "\n") + plantilla.format(n=i) + "\n" + pg
            header_report["page_markers"] = len(pages)
        else:
            raw = "\n\n".join(pages)

    text = unicodedata.normalize("NFC", raw)
    vr = _valid_ratio(text)

    # ── TEXTO DE ORIGEN ────────────────────────────────────────────────────────────────
    # ⚠ Se escribe ANTES de cualquier limpieza y homogeneiza los cinco formatos de entrada
    # en un único .txt. Sin esta capa, cambiar una regla de limpieza obliga a volver a los
    # binarios originales —PDF, DOCX, HTML— y a reprocesar desde cero; con ella se re-deriva
    # en segundos. Y resuelve un problema real: `meta` puede consultar el texto ÍNTEGRO, con
    # sus cabeceros, porque ahí viven metadatos que la limpieza retira («Acta Número 35 de la
    # Sesión Plenaria Ordinaria de fecha 14 de febrero de 2019» va en el cabecero de cada
    # página en SV).
    # Lo único que se añade es la marca de página: es estructura de la fuente que el texto
    # plano no sabe expresar de otro modo, no una modificación del contenido.
    if getattr(args, "text_output", None):
        origen = locals().get("_paginas_origen")
        if origen is not None:
            plantilla = scfg.get("page_marker_format") or "---PAGE {n:04d}---"
            crudo = "".join(("" if i == 1 else "\n") + plantilla.format(n=i) + "\n" + pg
                            for i, pg in enumerate(origen, 1))
        else:
            crudo = raw          # formatos no paginados: el texto ya es el de origen
        tp = Path(args.text_output)
        tp.parent.mkdir(parents=True, exist_ok=True)
        tp.write_text(unicodedata.normalize("NFC", crudo), encoding="utf-8")
        header_report["text_source"] = str(tp)
        header_report["text_source_chars"] = len(crudo)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")

    print(json.dumps({
        "status": "ok",
        "chars": len(text),
        "valid_ratio": round(vr, 4),
        "source_format": args.source_format,
        "output": str(output_path),
        # ── informe de cabeceros/pies (alimenta confianza/FLAG en el skill) ──
        "header_strip_enabled": header_report.get("enabled", False),
        "header_mode": header_report.get("mode"),
        "header_pages": header_report.get("n_pages", 0),
        "header_skipped": header_report.get("skipped", False),
        "header_lines_removed": header_report.get("lines_removed", 0),
        "header_removal_ratio": header_report.get("removal_ratio", 0.0),
        "header_suspect_count": len(header_report.get("suspect_removals", [])),
        "header_suspect_samples": header_report.get("suspect_removals", [])[:5],
        "header_furniture": header_report.get("furniture_forms", [])[:6],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
