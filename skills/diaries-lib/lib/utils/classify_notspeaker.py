#!/usr/bin/env python3
"""Triaje de NO-PERSONAS sobre el residuo `unmatched` del match.

⚠ ÁMBITO (error de diseño detectado y corregido, DO 2026-07): se aplica SOLO a los speakers que
quedaron `unmatched`. Aplicarlo a todo el universo produce 577 falsos positivos, porque nombres
reales truncados por el tagger ("Agustín Burgos Tejada de", "... y de") disparan las reglas
sintácticas — pero esos ya tienen match correcto y el roster los confirma. Un match exitoso ES la
prueba de que hay persona; no hay nada que clasificar.

REGLA DE DISEÑO: precisión 100%. Descartar a un diputado real pierde sus intervenciones sin
rastro; dejar pasar basura solo cuesta una línea de revisión.
"""
import re, unicodedata

def _n(s):
    s = unicodedata.normalize("NFD", (s or "").strip())
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()

SIGLAS = r"PLD|PRD|PRSC|PRM|PRI|PQDC|FNP|UDC|PNVC|PDP|PHD|PPC|PRSD|PUN|PAN"
PARTIDO_TOK = {"partido","liberacion","revolucionario","reformista","social","cristiano",
               "dominicano","dominicana","moderno","quisqueyano","democrata","fuerza",
               "progresista","independiente","humanista","bloque","pueblo","penagomista"}
ORG_TOK = {"comision","comisiones","camara","senado","congreso","asamblea","secretaria",
           "bufete","directiva","republica","constitucion","codigo","penal","civil","ley",
           "poder","ejecutivo","judicial","tribunal","corte","apelacion","junta","central",
           "electoral","ministerio","direccion","departamento","instituto","consejo","sala",
           "pleno","legislativa","asociacion","industrias","federacion","colegio","universidad",
           "ayuntamiento","distrito","provincia","municipio","nacional","elaboracion","actas"}
ROL_SOLO = {"diputado","diputada","adjunto","adjunta","titular","suplente","taquigrafa",
            "taquigrafo","relatora","relator","ujier","secretario","secretaria","asesor",
            "presidente","presidenta","vicepresidente","ponente","proponente","orador"}
ORDINAL = (r"primer[oa]?|segund[oa]|tercer[oa]?|cuart[oa]|quint[oa]|sext[oa]|septim[oa]|"
           r"octav[oa]|noven[oa]|decim[oa]|unic[oa]|final|transitori[oa]")

_PART = {"de","del","la","las","los","y","e","san","santa","vda","da","dos","el","al"}
def _nombres_propios(s):
    """tokens Capitalizados que no son partícula ni vocabulario de organización/partido/rol"""
    out = []
    for t in s.split():
        tn = _n(t).strip(".,;:")
        if t[:1].isupper() and tn and tn not in _PART and tn not in PARTIDO_TOK \
           and tn not in ORG_TOK and tn not in ROL_SOLO and not tn.isdigit():
            out.append(tn)
    return out

# NÚCLEO del sintagma: si la 1ª palabra significativa es de organización/partido/rol, es una
# entidad, por muchos nombres propios que vengan detrás ("Corte de Apelación ... de Montecristi").
# Un nombre de persona NUNCA empieza por "Comisión", "Bloque" o "Corte". Excluye los términos que
# también pueden ser apellido o topónimo (nacional, central, distrito, provincia...).
HEAD_AMBIGUO = {"nacional","central","civil","penal","sala"}
HEAD_ORG = (ORG_TOK | PARTIDO_TOK | ROL_SOLO |
            {"frente","movimiento","casa","fundacion","oficina","division","unidad",
             "subcomision","funciones","secretariado","gabinete","despacho",  # "mesa" NO: es apellido
             "nota","proyecto","informe","acta","expediente","iniciativa","mocion",
             "honorables","numerar","personalidad","parlamento","permanente"}) - HEAD_AMBIGUO
# materias/temáticas de comisión: no son nombres, son áreas de política pública
MATERIA_TOK = {"ciencia","tecnologia","educacion","fisica","recreacion","deportes","salud",
               "publica","obras","publicas","hacienda","interior","policia","agricultura",
               "turismo","cultura","medio","ambiente","industria","comercio","trabajo",
               "juventud","mujer","genero","ninez","adolescencia","fideicomiso","disciplina",
               "presupuesto","finanzas","defensa","exteriores","derechos","humanos",
               "planificacion","desarrollo","contabilidad","relaciones","juridica","legislativa",
               "general","permanente","vivienda","transporte","energia","minas","frontera"}

def _head(n):
    for t in n.split():
        if t not in _PART: return t
    return ""

# Marcador explícito de persona: si el sintagma DECLARA que sigue una persona y detrás vienen
# ≥2 nombres propios, no es una entidad por mucho que arranque con palabra de organización
# ("Pleno la Diputada Minerva Josefina Tavárez M" = persona con prefijo espurio del tagger).
MARCA_PERSONA = re.compile(r"\b(diputad[oa]s?|senador[ae]?s?|se[nñ]or[ae]?s?|honorable|hon\.|"
                           r"licenciad[oa]|doctor[a]?|ing\.|lic\.|dr[a]?\.)\b", re.I)

RULES = [
 # núcleo de organización → entidad, sin importar los nombres propios posteriores…
 # …salvo que declare explícitamente una persona y la nombre
 ("nucleo_organizacion", lambda s, n, np:
    _head(n) in HEAD_ORG and not (MARCA_PERSONA.search(n) and len(np) >= 2)),
 # sintagma de materia legislativa ("Ciencia y Tecnología", "Educación Física y Recreación")
 ("materia_legislativa", lambda s, n, np:
    sum(1 for t in n.split() if t in MATERIA_TOK) >= 1 and
    all(t in MATERIA_TOK or t in _PART or t in ORG_TOK for t in n.split())),
 # instrucción editorial filtrada del acta al texto
 ("instruccion_editorial", lambda s, n, np: s.isupper() and len(s.split()) >= 3 and
    re.search(r"\b(AGREGAR|MODIFICAR|ELIMINAR|SUSTITUIR|INCLUIR|SUPRIMIR|LEER|DESPU[EÉ]S|ANTES|"
              r"CAMBIAR|CORREGIR|A[NÑ]ADIR|QUITAR|PONER|DICE|DIGA|DONDE|CONSIDERANDO|"
              r"P[AÁ]RRAFO|EXPRESIONES|PALABRA)\b", s)),
 # articulado del documento legal: "CONSIDERANDO CUARTO", "Artículo Único", "Párrafo I"
 ("articulado_legal", lambda s, n, np:
    bool(re.match(rf"^(?:(?:en|al|del?)\s+(?:el|la|los|las)\s+)?"
                  rf"(considerando|visto|resulta|articulo|art\.|parrafo|inciso|literal|"
                  rf"capitulo|titulo|seccion)\b(\s+({ORDINAL}|[ivxlc]+|\d+))?\s*$", n)) or
    bool(re.match(rf"^({ORDINAL})\s+(considerando|parrafo|articulo)\s*$", n))),
 # sigla de partido suelta o con artículo
 ("sigla_partido", lambda s, n, np:
    bool(re.fullmatch(rf"(?:del?\s+|el\s+)?(?:{SIGLAS})", s.strip(), re.I))),
 # nombre de partido o bloque, sin persona
 ("nombre_partido", lambda s, n, np:
    sum(1 for t in n.split() if t in PARTIDO_TOK) >= 2 and not np),
 # órgano, comisión, norma, territorio — sin persona
 ("organizacion", lambda s, n, np:
    sum(1 for t in n.split() if t in ORG_TOK) >= 1 and not np),
 # rol pelado, sin nombre que lo acompañe
 ("rol_sin_nombre", lambda s, n, np:
    not np and bool(n.split()) and all(t in ROL_SOLO or t in _PART for t in n.split())),
 # cadena de alianza electoral: siglas unidas por guiones
 ("alianza_siglas", lambda s, n, np:
    bool(re.fullmatch(r"[A-Z]{2,6}(?:\s*[-/]\s*[A-Z]{2,6}){1,5}", s.strip()))),
 # número de expediente / referencia documental
 ("referencia_documental", lambda s, n, np: bool(re.match(r"^n[oº°]\.?\s*\d", n))),
 # sin ningún token nominal: función gramatical suelta ("Hubiere de", "Y", "que")
 ("fragmento_sin_nombre", lambda s, n, np: not np),
]

def palabras_comunes(textos, min_freq=20, ratio=0.60):
    """Deriva el vocabulario común DEL PROPIO CORPUS — sin léxico ni diccionario, así que
    funciona en cualquier país e idioma. Señal: una palabra común aparece en minúscula en
    medio de una frase; un apellido nunca. Medido en DO: `vía` 1.00, `tras` 0.98 frente a
    `González` 0.00, `Balaguer` 0.00, `Minyet` 0.00 (protege apellidos raros que ningún
    léxico contendría). ⚠ No normalices a minúscula el texto antes: destruye la señal."""
    import collections
    txt = " ".join(textos)
    sa = lambda x: "".join(c for c in unicodedata.normalize("NFD", x)
                          if unicodedata.category(c) != "Mn")
    low = collections.Counter(sa(m).lower() for m in
          re.findall(r"(?<=[a-záéíóúñü,] )([a-záéíóúñü]{3,})", txt))
    up = collections.Counter(sa(m).lower() for m in
         re.findall(r"(?<=[a-záéíóúñü,] )([A-ZÁÉÍÓÚÑ][a-záéíóúñü]{2,})", txt))
    return {w for w in set(low) | set(up)
            if (low[w] + up[w]) >= min_freq and low[w] / (low[w] + up[w]) >= ratio}


def clasificar(speaker_raw, comunes=None):
    """→ nombre de la clase si NO es persona; None si puede serlo.

    `comunes`: conjunto de palabras_comunes() para activar la regla de prosa (recomendado).

    ⚠ Llamar SOLO sobre speakers con match_method == "unmatched" y sin id_dep. Sobre filas ya
    emparejadas produce falsos positivos que descartan diputados reales — medido dos veces en DO:
    577 FP en el universo completo, y con la regla de prosa `Bueno` (=Ramón Antonio Bueno Patiño),
    `Mesa Velásquez`, `Pleno la Diputada Minerva…`. Todos tenían match correcto.
    """
    s = (speaker_raw or "").strip()
    n = _n(s)
    if not n: return "vacio"
    np_ = _nombres_propios(s)
    for name, fn in RULES:
        try:
            if fn(s, n, np_): return name
        except Exception: pass
    if comunes:
        sig = [t for t in n.split() if t.strip(".,;:") and t not in _PART and len(t) > 2]
        if sig and all(t.strip(".,;:") in comunes for t in sig):
            return "prosa"
    return None
