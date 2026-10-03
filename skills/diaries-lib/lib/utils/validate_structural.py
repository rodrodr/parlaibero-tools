#!/usr/bin/env python3
"""Validación de integridad estructural — auto-filtro PASS/FLAG (docs/_metodologia/validation_methodology.md).

Muestrea intervenciones al azar y las separa en **PASS** (trivialmente correctas, decididas
por reglas deterministas) y **FLAG** (todo lo demás). El humano revisa solo los FLAG.

El filtro es un **separador de obviedad, no un juez de calidad**: ante cualquier sombra de
duda marca FLAG. La asimetría es deliberada — un FLAG de más cuesta una revisión; un PASS de
más es un error que se cuela y nunca se ve.

**D1 — pureza del `text`.** Cero marcadores de un segundo interlocutor dentro del texto.
Se busca **inline**, sin anclar a principio de línea, porque GT, ES y CL tienen 0% de saltos
de línea y cualquier detector anclado a línea daría cero falso ahí
([[feedback_flattened_text_detectors]]).

Dos detectores complementarios, porque ninguno basta solo:

- **`vocabulario`** — busca en el `text` los nombres de orador **que el propio corpus
  conoce** (los `speaker_raw` más frecuentes con dos o más palabras) seguidos de un
  terminador. Es **independiente de la convención tipográfica**, que es lo que hacía fallar
  a la versión anterior: GT nombra a sus oradores en versalitas y daba 0%, y CR marca con
  **dos puntos** en vez de guion y daba 1,3% cuando el fenómeno real era del 4,15%.
- **`lexico`** — cortesía + nombre EN MAYÚSCULAS + guion. Cubre a los oradores que **no**
  están en el vocabulario porque nunca se les etiquetó en ninguna fila, que es justamente la
  clase que interesa encontrar.

**Tres guardas, porque el detector señala bien dónde pero no qué** (lección de CR, donde el
4,15% resultó ser el índice del acta y no discurso incrustado):

- **pase de lista** — con seis o más nombres del vocabulario, la fila es una votación nominal.
- **cita** — un verbo de cita o unas comillas justo antes: alguien leyendo lo que dijo otro.
- **índice del acta** — la mitad o más de sus líneas acaban en `: <número de página>`.

Cada guarda se reporta por separado, para que se vea qué se descartó y por qué.

⚠ **FLAG NO ES UNA INSTRUCCIÓN DE BORRADO.** Nunca se elimina ni se aparta una intervención
porque su orador no case con el padrón —sin mandato en esa legislatura, o ausente del padrón—.
El diario es la fuente primaria y el padrón una construcción nuestra: ese desajuste es un
defecto del padrón, no del acta. La intervención **se mantiene siempre**; lo que procede es
corregir el padrón o documentar la limitación (ver validation_methodology §4.6). «Fuera de
mandato» fue el motivo de FLAG más frecuente de la primera ejecución (180 de 343) y ninguna
de esas filas se tocó.

**D2 — atribución.** Con `id_dep`: el diputado debe estar **vigente** en la fecha de sesión y
su apellido **no puede estar compartido** por otra persona vigente en ese momento. Sin
`id_dep`: no se juzga la atribución (no hay ninguna), pero se marca aparte para el recall.

⚠ **La vigencia se comprueba con lo que el padrón de cada país puede expresar, y si no puede
expresarla NO se marca FLAG.** Los padrones nacionales son independientes por diseño: GT no
registra fechas de mandato (0% legibles) y SV ni siquiera tiene esas columnas — ambos
registran la pertenencia **por legislatura**, que es otra convención, no un defecto. La
primera versión de este filtro exigía fechas y mandaba a FLAG el **100%** de la muestra de GT
sin que hubiera nada mal. Es el mismo error que se corrigió en la vinculación efectiva: no
confundir «el dato no puede expresar esto» con «esto está mal». Orden: fechas de mandato →
legislatura → **no aplicable**, y lo no aplicable se reporta aparte, para que se sepa qué
dimensiones quedaron verificadas en cada país.

Uso:  python3 scripts/validacion/validar.py --country gt [--n 300] [--seed 20260731]
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

import pandas as pd

# ── D1: léxico de marcadores de orador, con variantes de OCR ───────────────────
# cortesía: Sr / Sra / Srta / Señor(a) / Senor(a) / Sr.ª, con el punto corrompido a , - ·
# o ausente, y la confusión frecuente Sr↔S↔St↔Sí↔Si
# ⚠ SENSIBLE A MAYÚSCULAS, y a propósito. Un marcador de orador es
#      cortesía + NOMBRE EN MAYÚSCULAS + terminador de guion:   SEÑOR MELO SANTA MARINA.-
# mientras que la misma cortesía en minúsculas y con dos puntos es el VOCATIVO con que
# empieza casi toda intervención:                               Señor Presidente: quiero…
# La primera versión usaba IGNORECASE y borraba esa distinción: en UY marcó el 30% de la
# muestra, y al mirarla eran vocativos («Señor Presidente:» está en el 20,4% de las filas)
# y «sí»/«si» corrientes capturados por la variante de OCR S[íi]. Cero verdaderos positivos.
CORTESIA = r"(?:[Ss][Ee][ÑNñn][Oo][Rr](?:[Ii][Tt])?[AaOo]?|[Ss][Rr][Aa]?|[Ss][Rr][Tt][Aa])\s*[.,·]?"
ROL = (r"(?:PRESIDENT[EA]|VICEPRESIDENT[EA]|SECRETARI[OA]|PROSECRETARI[OA]|"
       r"DIPUTAD[OA]|DEPUTAD[OA]|MINISTR[OA]|RELATOR[A]?|OFICIAL\s+MAYOR)")
NOMBRE_CAPS = r"[A-ZÁÉÍÓÚÑÜ][A-ZÁÉÍÓÚÑÜ'\s]{2,44}?"
# terminador: guion (en cualquiera de sus formas), opcionalmente precedido de punto o coma.
# Los dos puntos NO valen por sí solos: son la marca del vocativo, no la del marcador.
FIN = r"\s*(?:[\(\{][^)\}]{0,40}[\)\}])?\s*[.,]?\s*[-–—]"
# PY y CR marcan con DOS PUNTOS, no con guion, y por eso se escapó una fuga de la
# calibración (`SEÑOR VICENTE FERNANDEZ: 26 guardias…`). Se admiten los dos puntos solo
# cuando el nombre va EN MAYÚSCULAS: el vocativo `Señor Presidente:` va en minúsculas,
# así que la distinción que salvó a UY del 30% de falsos positivos se mantiene intacta.
FIN_DP = r"\s*(?:[\(\{][^)\}]{0,40}[\)\}])?\s*[.,]?\s*:"
# Forma panameña para los comparecientes que NO son diputados: el guion va DELANTE del
# nombre y la organización detrás de una coma. La destapó la 2ª ronda de calibración
#     —JULIO ESCOBAR, ASOCIACIÓN DE INTERÉS PÚBLICO
# Prevalencia: PA 0,68% · PY 0,05% · resto ≈0. Es una convención de una sola cámara, y por
# eso ningún detector escrito sobre las otras catorce la habría previsto.
GUION_DELANTE = re.compile(
    r"(?:^|\n)\s*[—–-]\s*[A-ZÁÉÍÓÚÑÜ][A-ZÁÉÍÓÚÑÜ'\.\s]{4,44},\s*[A-ZÁÉÍÓÚÑÜ]")

MARCADOR = re.compile(
    rf"(?:{CORTESIA}\s+{NOMBRE_CAPS}(?:{FIN}|{FIN_DP}))"
    # el rol puede llevar el nombre detrás y cerrar con dos puntos: `EL PRESIDENTE X:` (CR).
    # ROL va en mayúsculas literales y el patrón es sensible a ellas, así que `Presidente:`
    # —el vocativo— no entra.
    rf"|(?:\b{ROL}\b(?:\s+{NOMBRE_CAPS})?(?:{FIN}|{FIN_DP}))")

PART = {"de", "del", "la", "las", "los", "da", "das", "do", "dos", "y", "e", "san", "santa"}

# ── guardas de D1 ─────────────────────────────────────────────────────────────
MIN_TROZO = 60          # por debajo del umbral no es una intervención propia
MAX_NOMBRES = 6         # con más nombres del vocabulario, la fila es un pase de lista
CITA = re.compile(r"(?:dijo|dice|le[íi]|leo|cito|citando|manifest[óo]|expres[óo]|"
                  r"se[ñn]al[óo]|afirm[óo])\b", re.I)
FIN_PAGINA = re.compile(r"[:\.]\s*\t?\s*\d{1,3}\s*$")

# D3 — texto corrompido. Caracteres del área de uso privado (una fuente rota los deja
# como glifos sin significado) y el carácter de reemplazo de Unicode. Dimensión que el
# filtro NO comprobaba: la destapó la calibración de fuga con una fila de ES.
CORRUPTO = re.compile(r"[\ue000-\uf8ff\ufffd]")

# Cadena de firmas: «X. Apellido. – Y. Apellido. – Z. Apellido», el pie de un proyecto
# con sus autores. No es discurso, y la guarda de pase de lista no lo veía porque exige
# nombres del vocabulario y estos van abreviados. AR 2,73% · MX 1,07%.
FIRMAS = re.compile(r"[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+\s*[.,]?\s*[–—]\s*[A-ZÁÉÍÓÚÑ]")


def es_indice(t: str) -> bool:
    """El sumario del acta: la mitad o más de las líneas acaban en «: nº de página»."""
    lin = [x for x in str(t).split("\n") if x.strip()]
    return bool(lin) and sum(bool(FIN_PAGINA.search(x)) for x in lin) / len(lin) >= 0.5


def vocabulario(d: pd.DataFrame):
    """Nombres de orador que el corpus conoce → (patrón con terminador, patrón desnudo)."""
    from collections import Counter
    voc = [s for s, _ in Counter(d.speaker_raw[d.speaker_raw.str.split().str.len() >= 2])
           .most_common(600)]
    voc = [norm_acentos(v) for v in voc if len(v) > 10][:400]
    if not voc:
        return None, None
    ROL_PREV = r"(?:EL |LA )?(?:PRESIDENT[EA]|VICEPRESIDENT[EA]|DIPUTAD[OA]|SECRETARI[OA])\s+"
    alt = "|".join(map(re.escape, voc))
    return (re.compile(rf"(?:{ROL_PREV})?(?:{alt})\s*[.,]?\s*[:\-–—]"),
            re.compile(rf"(?:{alt})"))


def norm_acentos(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip()


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z\s]", " ", s)).strip()


# vocabulario de cargo y cortesía: si al quitarlo no queda nada, el marcador no nombra a nadie
VOC_ROL = set("""senor senora senorita sr sra srta dr dra doctor doctora don dona el la los las
de del y e presidente presidenta vicepresidente vicepresidenta secretario secretaria
prosecretario prosecretaria diputado diputada deputado deputada ministro ministra primero
primera segundo segunda tercero tercera cuarto cuarta quinto quinta interino interina
provisional accidental suplente gobierno cortes camara camaras congreso republica asamblea
estado nacion mesa presidencia encargado relator relatora funciones""".split())


def nombra_persona(speaker_raw: str) -> bool:
    """True si el marcador contiene algo más que cargo y cortesía."""
    return any(t not in VOC_ROL and len(t) > 2 for t in norm(speaker_raw).split())


# Oficios que NO son escaño: quien los ejerce va nombrado en el acta y **no puede** tener
# id_dep. Es la misma distinción que define la vinculación efectiva. Sin ella, marcar
# «nombrado sin id_dep» convertía en FLAG a los 148.000 secretarios generales de CO y
# disparaba su tasa al 35,3% sin que hubiera nada mal.
NO_DIPUTADO = re.compile(
    r"\b(ministr[oa]s?|vice\s?ministr|secretari[oa]\s+general|subsecretari|prosecretari|"
    r"secretari[oa]\s+de\s+la\s+c[aá]mara|maestr[oa]\s+de\s+ceremoni|relator|edec[aá]n|"
    r"oficial\s+mayor|contralor|fiscal\s+general|procurador|defensor\s+del\s+pueblo|"
    r"magistrad|presidente\s+de\s+la\s+rep[uú]blica|jefe\s+de\s+estado|embajador|"
    r"general\s+de\s+divisi|contralmirante)\b", re.I)


# Métodos de `matching_table` que constituyen ADJUDICACIÓN de la atribución: o los decidió
# una persona, o los resolvió una señal INDEPENDIENTE del parecido del nombre. La homonimia
# no se vuelve a marcar sobre ellos — sería rehacer una revisión ya hecha.
#   manual     · decisión humana en la fase de match
#   attendance · pase de lista nominal de esa sesión (la señal más fuerte del proyecto)
#   exact      · el nombre completo casó exactamente: no había ambigüedad que resolver
# `fuzzy`, `word_subset` y similares NO adjudican: son parecido de cadena, que es justo
# donde la homonimia muerde.
ADJUDICADO = {"manual", "attendance", "exact"}


def cargar_adjudicados(iso2: str) -> dict:
    """(speaker_raw → id_dep) ya adjudicados en la fase de match."""
    p = Path(f"source/{iso2}/match/matching_table.csv")
    if not p.exists():
        return {}
    h = p.open(encoding="utf-8", errors="replace").readline()
    d = pd.read_csv(p, sep=";" if h.count(";") > h.count(",") else ",",
                    dtype=str, keep_default_na=False)
    if not {"speaker_raw", "id_dep", "match_method"} <= set(d.columns):
        return {}
    # La revisión humana no siempre queda en `match_method`: CO, DO y MX la anotan en
    # `notas` («revisión manual», «revisión manual del usuario»). Cuenta igual.
    rev = d.notas.str.contains(r"revisi[óo]n\s+manual", case=False, regex=True) \
        if "notas" in d.columns else pd.Series(False, index=d.index)
    d = d[(d.match_method.isin(ADJUDICADO) | rev) & (d.id_dep.str.strip() != "")]
    return dict(zip(d.speaker_raw.str.strip(), d.id_dep.str.strip()))


def ruta_padron(iso2: str) -> Path | None:
    for n in ("deputies.csv", "diputados_bd.csv"):
        p = Path(f"source/{iso2}/deputies/{n}")
        if p.exists():
            return p
    return None


def cargar_padron(iso2: str, vocab_leg: set | None = None):
    """→ (mandatos[id] = [(ini,fin)], apellidos[apellido] = {id}, nombre[id])"""
    p = ruta_padron(iso2)
    r = pd.read_csv(p, sep=";" if p.open(encoding="utf-8", errors="replace").readline().count(";")
                    > p.open(encoding="utf-8", errors="replace").readline().count(",") else ",",
                    dtype=str, keep_default_na=False)
    low = {c.lower(): c for c in r.columns}
    cid = low.get("id_dep") or low.get("diputado_id")
    cnm = next((low[k] for k in ("nombre_completo", "speaker_name", "nombre_original", "alias")
                if k in low), cid)
    cap = next((low[k] for k in ("apellidos", "last_name") if k in low), None)
    cin = next((low[k] for k in ("fecha_inicio", "fecha_alta", "start_date") if k in low), None)
    cfi = next((low[k] for k in ("fecha_fin", "fecha_baja", "end_date") if k in low), None)

    cle = next((low[k] for k in ("legislatura", "legislature", "legislatura_num", "id_legislatura")
                if k in low), None)

    # ⚠ DESCUBRIR, no asumir el nombre de la columna. GT registra las legislaturas de cada
    # diputado —`X`, `IV`, `IX,X`, `VI,VII,VIII`— dentro de `notas`, el campo genérico de la
    # plantilla. Asumir que la legislatura solo puede llamarse `legislatura`/`legislature`
    # dejaba a Guatemala como «no comprobable» teniendo el dato delante. Se detecta
    # contrastando cada columna de texto con el vocabulario de legislaturas DEL CORPUS.
    if cle is None and vocab_leg:
        for cand in r.columns:
            vals = {x.strip() for v in r[cand] for x in str(v).split(",") if x.strip()}
            if vals and len(vals & vocab_leg) / len(vals) >= 0.9:
                cle = cand
                break

    mand, ape, nom, leg = defaultdict(list), defaultdict(set), {}, defaultdict(set)
    tok = defaultdict(set)          # TODOS los tokens del nombre → ids (para estrechar)
    for _, row in r.iterrows():
        i = row[cid]
        nom.setdefault(i, row[cnm])
        a = norm(row[cap]) if cap else ""
        if not a:
            t = [x for x in norm(row[cnm]).split() if x not in PART]
            a = " ".join(t[-2:]) if len(t) > 1 else (t[0] if t else "")
        if a:
            ape[a].add(i)
            ape[a.split()[0]].add(i)
        for x in norm(row[cnm]).split():
            if x not in PART and len(x) > 2:
                tok[x].add(i)
        if cin:
            ini = pd.to_datetime(row[cin], errors="coerce")
            fin = pd.to_datetime(row[cfi], errors="coerce") if cfi else pd.NaT
            if pd.notna(ini):
                mand[i].append((ini, fin if pd.notna(fin) else pd.Timestamp("2100-01-01")))
        if cle and str(row[cle]).strip():
            for x in str(row[cle]).split(","):      # un diputado puede tener varias
                if x.strip():
                    leg[i].add(x.strip())

    # qué puede expresar este padrón: decide qué comprobación de vigencia se aplica
    modo = "fecha" if mand else ("legislatura" if leg else "n/a")
    return mand, ape, nom, leg, modo, tok


def evaluar(fila, mand, ape, nom, leg, modo, tok, voc_pat=None, voc_nom=None,
            rango_leg=None, adjud=None):
    """→ (veredicto, motivos, no_aplicables)

    PASS solo si ninguna comprobación APLICABLE falla. Lo no aplicable no es un fallo:
    se cuenta aparte para declarar qué quedó verificado en cada país.
    """
    motivos, na = [], []

    # ── D1: pureza del text ────────────────────────────────────────────────
    txt = str(fila.text)
    if es_indice(txt):
        na.append("D1: fila de índice del acta (no es discurso; no se juzga la pureza)")
    else:
        na_txt = norm_acentos(txt)
        hits = []
        if voc_pat is not None:
            if len(voc_nom.findall(na_txt)) > MAX_NOMBRES:
                na.append("D1: pase de lista (no es discurso ajeno incrustado)")
            else:
                for m in voc_pat.finditer(na_txt):
                    ctx = na_txt[max(0, m.start() - 90):m.start()]
                    if CITA.search(ctx) or ctx.rstrip().endswith(("«", '"', "\u201c")):
                        continue                    # cita, no turno de palabra
                    if len(na_txt[m.end():m.end() + MIN_TROZO].strip()) >= MIN_TROZO // 2:
                        hits.append(("vocabulario", m.group(0).strip()))
        for m in MARCADOR.finditer(txt):
            ctx = txt[max(0, m.start() - 90):m.start()]
            if not CITA.search(ctx):
                hits.append(("lexico", m.group(0).strip()))
        for m in GUION_DELANTE.finditer(txt):
            hits.append(("guion_delante", m.group(0).strip()))
        if hits:
            que = "+".join(sorted({k for k, _ in hits}))
            motivos.append(f"D1: {len(hits)} marcador(es) en el text [{que}]")

    # ── D3: integridad del carácter ────────────────────────────────────────
    if CORRUPTO.search(txt):
        motivos.append("D3: caracteres corrompidos en el text")

    # ── D1-bis: la fila no parece discurso ─────────────────────────────────
    if len(FIRMAS.findall(txt)) >= 3:
        motivos.append("D1: cadena de firmas (no parece discurso)")

    # ── D2: atribución ─────────────────────────────────────────────────────
    idd = str(fila.id_dep).strip()
    if not idd:
        # ⚠ Sin id_dep NO es siempre «nada que juzgar». Si el marcador NOMBRA a una
        # persona, es un orador identificable que quedó sin vincular — un fallo de recall,
        # no una exclusión estructural. Tratarlo como no aplicable hacía que el filtro
        # aprobara sin mirar casi la mitad del corpus de PY (46,8% de filas sin id_dep),
        # y así se escapó `Presidente (Pilgüese)` = Juan Carlos Pugliese con el OCR roto.
        sr = str(fila.speaker_raw)
        if NO_DIPUTADO.search(sr):
            na.append("D2: no-diputado nombrado (no puede tener id_dep)")
        elif nombra_persona(sr):
            motivos.append("D2: orador NOMBRADO sin id_dep (identificable y sin vincular)")
        else:
            na.append("D2: cargo sin nombre y sin id_dep (nada que vincular)")
        return ("PASS" if not motivos else "FLAG"), motivos, na

    if idd not in nom:
        motivos.append("D2: id_dep no existe en el padrón")
        return "FLAG", motivos, na

    d = pd.to_datetime(str(fila.date), errors="coerce")
    cohorte = None                      # conjunto de ids vigentes en ese momento

    # ⚠ La unidad de vigencia es el MANDATO EN UNA LEGISLATURA, no la fecha exacta.
    # Se comprueba que el mandato del diputado SOLAPE la legislatura de la sesión; exigir
    # que la fecha de sesión caiga dentro del intervalo convierte la precisión con que cada
    # padrón anotó las fechas en un criterio de calidad, que es lo que NO es: PT registra
    # mandatos que abarcan la carrera, UY los tiene truncados y ES solo tiene fecha legible
    # en el 36,6% de sus filas, y en los tres casos la persona SÍ era diputada.
    L = str(getattr(fila, "legislature", "")).strip()
    rl = (rango_leg or {}).get(L)

    def solapa(i):
        if L and L in leg.get(i, set()):          # el padrón lo sitúa en esa legislatura
            return True
        if rl and mand.get(i):                    # su mandato solapa el rango de la legislatura
            return any(a <= rl[1] and b >= rl[0] for a, b in mand[i])
        if mand.get(i) and pd.notna(d):           # sin legislatura: se cae a la fecha
            return any(a <= d <= b for a, b in mand[i])
        return None                               # no comprobable

    v = solapa(idd)
    if v is None:
        na.append("D2: vigencia no comprobable (el padrón no expresa mandato ni legislatura)")
    elif not v:
        motivos.append(f"D2: sin mandato en la legislatura {L!r}" if L
                       else "D2: sin mandato que cubra la fecha de sesión")
    else:
        # ⚠ La cohorte para juzgar HOMONIMIA se mantiene lo más ajustada que permita el dato.
        # La vigencia se juzga por legislatura (regla del mandato), pero para saber si un
        # apellido era ambiguo importa quién estaba en el escaño EN ESE MOMENTO: dos personas
        # que nunca coincidieron no crean ambigüedad. Usar la legislatura entera para esto
        # inflaba los FLAG de AR y UY.
        if pd.notna(d):
            cohorte = lambda i: (any(a <= d <= b for a, b in mand[i]) if mand.get(i)
                                 else solapa(i) is True)
        else:
            cohorte = lambda i: solapa(i) is True

    # ── homonimia: ¿el marcador basta para elegir a una sola persona? ──────
    # Se toman los candidatos COMPATIBLES CON TODOS los tokens del marcador, no la
    # unión de quienes comparten alguno: si `speaker_raw` es un nombre completo, no hay
    # ambigüedad aunque el apellido lo lleven diez personas. Con la unión, SV —cuyos
    # marcadores son nombres completos— daba 72,7% de FLAG sin ambigüedad real.
    if (adjud or {}).get(str(fila.speaker_raw).strip()) == idd:
        na.append("D2: homonimia ya adjudicada en la fase de match")
        return ("PASS" if not motivos else "FLAG"), motivos, na

    t = [x for x in norm(fila.speaker_raw).split() if x not in PART and len(x) > 2]
    cand = None
    for k in t:
        c_k = tok.get(k) or ape.get(k, set())
        if not c_k:
            continue
        cand = c_k if cand is None else (cand & c_k)
    cand = cand or set()
    if len(cand) > 1:
        if cohorte is None:
            na.append("D2: homonimia no comprobable (sin cohorte vigente)")
        else:
            viv = {i for i in cand if cohorte(i)}
            if len(viv) > 1:
                # NO es FLAG, y no por concesión: **el match pasó por la revisión manual
                # del investigador antes de la fase de merge**. La desambiguación de
                # apellidos compartidos es precisamente lo que esa revisión resolvió, caso
                # por caso. Volver a marcarla aquí sería rehacer un trabajo ya hecho por una
                # persona, no por una regla — y la persona es la referencia, no el filtro.
                #
                # ⚠ Esa revisión **no queda registrada en los datos**: en la mayoría de los
                # casos se confirmó la atribución sin cambiar `match_method` ni anotar nada,
                # así que `matching_table` no distingue «revisado y confirmado» de «nunca
                # mirado». La propiedad es real y hay que declararla en la documentación del
                # corpus; el fichero, por sí solo, no la acredita.
                na.append(f"D2: apellido compartido por {len(viv)} vigentes "
                          "(resuelto en la revisión manual del match)")

    return ("PASS" if not motivos else "FLAG"), motivos, na


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", required=True)
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=20260731)
    a = ap.parse_args()
    c = a.country.lower()

    csv = Path(f"source/{c}/standardize/{c.upper()}_interventions.csv")
    cols = ["legislature", "date", "session_number", "intervention_order", "speaker_raw",
            "id_dep", "speaker_name", "text"]
    d = pd.read_csv(csv, dtype=str, keep_default_na=False, usecols=cols)
    m = d.sample(n=min(a.n, len(d)), random_state=a.seed)
    vocab_leg = {x.strip() for x in d.legislature if x.strip()} \
        if 'legislature' in d.columns else set()
    mand, ape, nom, leg, modo, tok = cargar_padron(c, vocab_leg)

    vp, vn = vocabulario(d)
    # rango de fechas de cada legislatura, derivado del propio corpus
    rl = {}
    if "legislature" in d.columns:
        q = d[(d.legislature.str.strip() != "") & (d.date.str.strip() != "")]
        g = q.assign(_d=pd.to_datetime(q.date, errors="coerce")).dropna(subset=["_d"]) \
             .groupby("legislature")._d.agg(["min", "max"])
        rl = {i: (r["min"], r["max"]) for i, r in g.iterrows()}
    adj = cargar_adjudicados(c)
    res = [evaluar(f, mand, ape, nom, leg, modo, tok, vp, vn, rl, adj)
           for f in m.itertuples(index=False)]
    m = m.assign(veredicto=[v for v, _, _ in res],
                 motivos=[" | ".join(x) for _, x, _ in res],
                 no_aplicable=[" | ".join(x) for _, _, x in res])

    nf = int((m.veredicto == "FLAG").sum())
    print(f"{c.upper()} · muestra {len(m):,} de {len(d):,} · vigencia por {modo.upper()}")
    print(f"  PASS {len(m)-nf:4,} ({100*(len(m)-nf)/len(m):5.1f}%)   "
          f"FLAG {nf:4,} ({100*nf/len(m):5.1f}%)\n")
    for etq, idx in (("motivos de FLAG", 1), ("no aplicable (no es fallo)", 2)):
        cnt = defaultdict(int)
        for r in res:
            for x in r[idx]:
                cnt[x.split("(")[0].strip()] += 1
        if cnt:
            print(f"  {etq}:")
            for k, v in sorted(cnt.items(), key=lambda x: -x[1]):
                print(f"    {v:4,}  {k}")

    out = Path(f"docs/validacion/{c.upper()}_muestra.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    m.to_csv(out, index=False, encoding="utf-8")
    print(f"\n→ {out}")


if __name__ == "__main__":
    main()
