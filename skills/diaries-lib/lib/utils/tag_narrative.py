#!/usr/bin/env python3
"""Tagger de estilo NARRATIVO (actas donde la relatora introduce cada intervención en
prosa y cita el discurso entre comillas tipográficas).

    En la prosecución del debate, el Diputado X hizo la siguiente exposición: “DISCURSO”.

Invariante: la intervención abre con `: “` y cierra con `”`. El orador se resuelve HACIA
ATRÁS en la cláusula introductoria (no se ancla al verbo introductor, que es lista abierta).
Primer país: DO (República Dominicana). Ver country_config `tagging_style: narrative`.

Salida: formato inline `<int speaker="NOMBRE">texto</int>` (consumido por parse_interventions).

Reglas de resolución del orador (en orden de prioridad):
  1. "…NOMBRE, quien VERBO:" → NOMBRE (con o sin honorífico).
  2. Última mención persona en posición de SUJETO (se excluyen objetos "al Diputado X",
     "dirigiéndose a…"), con honorífico diputado/legislador/senador/ministro/señor/….
  3. Verbos de concesión de palabra ("le fue concedido…a la Diputada X") → el objeto ES el orador.
  4. Rol sin nombre ("el Diputado Presidente", "la Secretaria") → speaker rol (PRESIDENTE…).
  5. Anáfora de continuación ("volvió a hacer uso de la palabra", "continuó diciendo",
     "prosiguió", "nueva vez") sin mención nueva → orador anterior.
  6. Cláusula con sustantivo de DOCUMENTO y sin persona ("la comunicación dice:", "el
     informe se transcribe a continuación:") → cita documental, NO se etiqueta.
  7. Sin referente → sin etiquetar; se reporta en unresolved (candidato a pase LLM).

Cierre de cita con PROFUNDIDAD auto-reparadora:
  - “ a inicio de párrafo con cita abierta = comilla de CONTINUACIÓN (no incrementa).
  - “ interna en medio del texto = cita anidada (incrementa); ” decrementa.
  - Si aparece un nuevo párrafo narrativo con ancla `: “` mientras hay cita abierta
    (cierre perdido), se fuerza el cierre al final del párrafo anterior (auto-reparación).
"""
import argparse, json, re, sys, unicodedata
from pathlib import Path

NAME_TOKEN = r"[A-ZÁÉÍÓÚÜÑ][\wÁÉÍÓÚÜÑáéíóúüñ.'\-]*"
NAME_SEQ = rf"{NAME_TOKEN}(?:\s+(?:del|de(?:\s+l[ao]s?)?|la|los|las|y|van|von|Vda\.?|{NAME_TOKEN}))*"

HONORIFIC = (r"(?:[Dd]iputad[oa]s?|[Ll]egislador(?:a|es)?|[Ss]enador(?:a|es)?|[Mm]inistr[oa]s?|"
             r"[Ss]ecretari[oa]|[Vv]icepresident[ea]|[Pp]residenta?|[Pp]residencia|[Rr]elator[a]?|"
             r"[Ss]eñor(?:a|ita)?|[Dd]octor[a]?|[Ll]icenciad[oa]|[Ii]ngenier[oa]|[Pp]rofesor[a]?)")

# aposición breve permitida entre honorífico y nombre: "Diputado coproponente, Rafael X"
APPOSITION = r"(?:\s+(?:coproponente|proponente|vocer[oa]|vicevocer[oa]|elect[oa]))?(?:\s*,)?"

ROLE_WORDS = (r"(?:[Pp]resident[ea](?:\s+en\s+[Ff]unciones)?|[Vv]icepresident[ea](?:\s+en\s+"
              r"[Ff]unciones(?:\s+de\s+[Pp]resident[ea])?)?|[Ss]ecretari[oa](?:\s+[Aa]d[\s-]?[Hh]oc)?|"
              r"[Rr]elator[a]?(?:[\s-][Tt]aqu[íi]graf[oa](?:\s+[Pp]arlamentari[oa])?)?)")

# mención persona: honorífico (+rol opcional) (+aposición) + nombre opcional
MENTION = re.compile(
    rf"(?P<full>(?P<hon>{HONORIFIC})(?:\s+(?P<role>{ROLE_WORDS}))?{APPOSITION}(?:\s+(?P<name>{NAME_SEQ}))?)")

# la APOSICIÓN descriptiva («, vocero del bloque de Diputados del PLD») arranca en
# minúscula y puede contener siglas versales: se admite entre el nombre y «quien» para
# que no se trague el nombre real (producía speaker «del PLD», 2026-08-30)
QUIEN = re.compile(
    rf"(?P<name>{NAME_SEQ})(?:\s*,\s*(?![^,:\n]{{0,90}}\b(?:agot[óo]|hizo|fue(?:ron)?|us[óo]|"
    rf"expres[óo]|manifest[óo]|pronunci[óo]|declar[óo]|dio|dijo|solicit[óo]|ley[óo])\b)"
    rf"[a-záéíóúüñ][^,:\n]{{0,90}})?\s*,?\s+(?:quien(?:es)?|(?<!en )(?<!de )(?<!con )(?<!por )(?:la|el)\s+cual)\s+"
    rf"[\wáéíóúüñ]+[^:]{{0,120}}$")

# verbos de habla que, como cláusula sola sin mención, señalan anáfora del orador anterior
SPEECH_VERB = re.compile(
    r"\b(?:dij(?:o|eron)|señal[óo]|manifest[óo]|expres[óo]|agreg[óo]|añadi[óo]|indic[óo]|"
    r"apunt[óo]|precis[óo]|afirm[óo]|pregunt[óo]|respondi[óo]|declar[óo]|concluy[óo]|"
    r"puntualiz[óo]|acot[óo]|explic[óo]|inform[óo]|advirti[óo]|enfatiz[óo]|reiter[óo]|"
    r"coment[óo]|sostuvo|adujo|arguy[óo]|expuso|ley[óo]|prosigui[óo]|continu[óo]|"
    r"argument[óo]|record[óo]|destac[óo]|subray[óo]|asever[óo]|resalt[óo]|contest[óo]|"
    r"replic[óo]|insisti[óo]|exhort[óo]|salud[óo]|pronunci[óo]|anunci[óo]|inquiri[óo]|exclam[óo]|"
    r"se\s+(?:manifest[óo]|expres[óo]|pronunci[óo]|refiri[óo]))\b[^:]{0,60}$", re.I)

VOTE_CONTEXT = re.compile(r"votaci[óo]n|escrutinio|qu[óo]rum|comprobaci[óo]n", re.I)

# participio + "por": el texto citado es un DOCUMENTO aunque mencione diputados autores
DOC_PARTICIPLE = re.compile(
    r"(?:presentad|suscrit|firmad|sometid|depositad|remitid|enviad|dirigid|le[íi]d|"
    r"propuest)[ao]s?\s+por\b", re.I)

# cláusula que es SOLO un nombre propio (≥2 tokens): "Santana Suriel:"
BARE_NAME = re.compile(rf"^(?:[Ee]l\s+|[Ll]a\s+)?(?P<name>{NAME_SEQ})$")

# NOMBRE sin honorífico seguido de verbo de habla: "Fernández Saviñón, se dirigió…"
NAME_VERB = re.compile(
    rf"(?P<name>{NAME_SEQ})\s*,?\s+(?:se\s+)?"
    r"(?:dirigi[óo]|pronunci[óo]|manifest[óo]|expres[óo]|comunic[óo]|inform[óo]|anunci[óo]|"
    r"apuntal[óo]|explic[óo]|dijo|señal[óo]|indic[óo]|coment[óo]|agreg[óo]|precis[óo]|"
    r"apunt[óo]|respondi[óo]|contest[óo]|pregunt[óo]|ley[óo]|expuso|declar[óo]|ofreci[óo])\b")

# NOMBRE + cargo de personal técnico: "Lelis Santana de Faxas, Encargada del Departamento…"
NAME_TITLE = re.compile(
    rf"(?P<name>{NAME_SEQ})\s*,\s*(?:Encargad[oa]|Directora?|Jefa?|Coordinador[a]?|Asistente)\b")

DOC_NOUN = re.compile(
    r"(?:comunicaci[óo]n|carta|correspondencia|excusa|informe|nota|oficio|resoluci[óo]n|"
    r"art[íi]culo|texto|acta|actas|certificaci[óo]n|decreto|ley|leyes|proyecto|iniciativa|"
    r"documento|p[áa]rrafo|considerando|reglamento|constituci[óo]n|dispositivo|misiva|"
    r"instancia|enmienda|convenio|contrato|informe|licencia|orden\s+del\s+d[íi]a|"
    r"a\s+saber|el\s+mismo|la\s+misma|se\s+transcribe|se\s+copia|se\s+lee\s+as[íi]|"
    r"reza|dice\s+textualmente|cuyo\s+texto|del\s+tenor|"
    r"palabras?\b|se\s+lea|sustituy|agregar|eliminar|t[íi]tulo|ep[íi]grafe|frase|"
    r"propuesta|moci[óo]n|pedimento|modificaci[óo]n|aviso|listado|"
    r"\bdiga\b|debe\s+decir|que\s+dice|dice(?:\s+textualmente)?\s*$|como\s+sigue|"
    r"redacci[óo]n|se[ñn]ala\s+textualmente|establece|\(dice|"
    r"dir[áa]\b|intercalar|se\s+cita|contempla|pr[ée]stamo|circular)", re.I)

ANAPHORA = re.compile(
    r"(?:volvi[óo]\s+a|continu[óo]|prosigui[óo]|nueva\s+vez|de\s+nuevo|"
    r"retom[óo]\s+(?:el\s+uso\s+de\s+)?la\s+palabra|concluy[óo]\s+(?:diciendo|as[íi]|expresando)|"
    r"sigui[óo]\s+(?:diciendo|expresando)|agreg[óo]\s+(?:adem[áa]s|luego|entonces)?|prosecuci[óo]n\s+de\s+su)", re.I)

CONCESSION = re.compile(r"(?:concedi[dó]|otorga[dr]|cedi[dó]|conced[eé])", re.I)

OBJECT_PREP = re.compile(r"(?:\ba\s+l?[oa]?s?\s*$|\bal\s*$|dirigi[ée]ndose\s+a(?:\s+l[oa]s?)?\s*$|"
                         r"\bal\s+$)", re.I)

ROLE_CANON = [
    (re.compile(r"vicepresiden", re.I), "VICEPRESIDENTE"),
    (re.compile(r"presiden", re.I), "PRESIDENTE"),
    (re.compile(r"secretari", re.I), "SECRETARIO"),
    (re.compile(r"relator", re.I), "RELATORA"),
]

ABBREV = re.compile(r"(?:Sr|Sra|Dr|Dra|No|N[úu]m|[Aa]rt|p[áa]g|Lic|Ing|Prof|St[oa]|Ud|Uds|etc)\.$")


def _clause_before(text: str, pos: int, window: int = 600, segments: int = 1) -> str:
    """Cláusula introductoria: los últimos `segments` tramos delimitados por
    terminadores fuertes (”, . o salto doble)."""
    start = max(0, pos - window)
    seg = text[start:pos]
    cuts = [0]
    for m in re.finditer(r"[”“]|\.\s|\n\n|;\s", seg):
        tail = seg[:m.start()].rstrip()
        if m.group(0).startswith(".") and ABBREV.search(tail[-6:] + "."):
            continue
        cuts.append(m.end())
    cut = cuts[-segments] if len(cuts) >= segments else 0
    return re.sub(r"\s+", " ", seg[cut:]).strip()


def _clause_start(text: str, pos: int, window: int = 600) -> int:
    """Índice absoluto donde empieza la cláusula introductoria que precede a pos."""
    start = max(0, pos - window)
    seg = text[start:pos]
    cut = 0
    for m in re.finditer(r"[”“]|\.\s|\n\n|;\s|\.{3}", seg):
        tail = seg[:m.start()].rstrip()
        if m.group(0).startswith(".") and not m.group(0).startswith("...") \
                and ABBREV.search(tail[-6:] + "."):
            continue
        cut = m.end()
    return start + cut


def _canon_role(role_text: str, hon: str) -> str:
    probe = f"{hon} {role_text or ''}"
    for rx, canon in ROLE_CANON:
        if rx.search(role_text or "") or rx.search(hon or ""):
            if canon == "VICEPRESIDENTE" and re.search(r"funciones\s+de\s+president", probe, re.I):
                return "PRESIDENTE EN FUNCIONES"
            return canon
    return ""


_LEAD_VERB = re.compile(
    r"^(?:Expres[óo]|Señal[óo]|Manifest[óo]|Indic[óo]|Precis[óo]|Aclar[óo]|Agreg[óo]|"
    r"Dijo|Continu[óo]|Concluy[óo]|Pregunt[óo]|Respondi[óo]|Explic[óo]|Inform[óo]|"
    r"Apunt[óo]|Afirm[óo]|Destac[óo]|Subray[óo]|Intervino|Prosigui[óo]|Anunci[óo]|"
    r"Puntualiz[óo]|Acot[óo]|Enfatiz[óo]|Reiter[óo]|Asever[óo]|Argument[óo]|"
    r"Consider[óo]|Contest[óo]|Ratific[óo]|Coincidi[óo]|Sugiri[óo]|Insisti[óo]|"
    r"Advirti[óo]|Sostuvo|Record[óo])\s+", re.I)

_TRAIL_VERB = re.compile(
    r"\s+(?:Manifest[óo]|Dijo|Señal[óo]|Continu[óo]|Agreg[óo]|Expres[óo]|Indic[óo]|"
    r"Precis[óo]|Explic[óo]|Inform[óo]|Concluy[óo]|Anunci[óo]|Pregunt[óo]|Respondi[óo])$")

_LEAD_JUNK = re.compile(r"^(?:CD|C[ÁA]MARA(?:\s+DE\s+DIPUTADOS)?)\s+")


def _clean_name(name: str) -> str | None:
    """Normaliza el nombre capturado: quita artículos, residuos de cabecera, verbos
    capitalizados iniciales y honoríficos; canoniza los que son solo rol."""
    n = re.sub(r"\s+", " ", name).strip(" ,y")
    changed = True
    while changed:
        changed = False
        for rx in (_LEAD_JUNK, _LEAD_VERB,
                   re.compile(r"^(?:[Ee]l|[Ll]a|[Ll]os|[Ll]as)\s+"),
                   re.compile(rf"^{HONORIFIC}\s+")):
            n2 = rx.sub("", n)
            if n2 != n:
                n, changed = n2, True
    n = _TRAIL_VERB.sub("", n).strip(" ,y")
    if not n:
        return None
    # entes colectivos e instituciones no son oradores
    if re.match(r"(?:de\s+la\s+)?(?:Comisi[óo]n|Bufete|C[áa]mara)\b", n, re.I):
        return None
    if re.fullmatch(r"General(?:\s+de\s+la\s+C[áa]mara)?", n):
        return "SECRETARIO"   # "Secretaria General de la Cámara" con honorífico recortado
    # nombre kilométrico = lista absorbida (designaciones de comisión): rol si lo hay, si no descartar
    if len(n.split()) > 8:
        for rx, canon in ROLE_CANON:
            if rx.search(n.split()[-1]) or rx.search(" ".join(n.split()[-3:])):
                return canon
        return None
    # ¿es solo un rol?
    if re.fullmatch(r"(?:[Pp]residenta?e?|[Pp]residencia)(?:\s+en\s+[Ff]unciones)?", n):
        return "PRESIDENTE" if "uncion" not in n else "PRESIDENTE EN FUNCIONES"
    if re.fullmatch(r"(?:en\s+)?[Ff]unciones\s+de\s+[Pp]residenta?e?", n):
        return "PRESIDENTE EN FUNCIONES"
    if re.fullmatch(r"(?:[Pp]or\s+)?[Ss]ecretar[íi]a|[Ss]ecretari[oa]", n):
        return "SECRETARIO"
    if re.fullmatch(r"[Rr]elatora?(?:[\s-][Tt]aqu[íi]grafa?(?:[\s-]?[Pp]arlamentaria)?)?", n):
        return "RELATORA"
    return n


def resolve_speaker(clause: str, prev_speaker: str | None) -> tuple[str | None, str]:
    """Devuelve (speaker | None, categoría)."""
    if not clause:
        return None, "sin_clausula"

    # 1. "…NOMBre, quien/la cual VERBO:" — el orador es el nombre MÁS CERCANO a «quien»
    # (último match), y un resultado que arranca en partícula o es solo-cargo se DESCARTA
    # para que resuelvan las menciones/concesión (clase «del PLD», 2026-08-30)
    mqs = list(QUIEN.finditer(clause))
    if mqs:
        name = mqs[-1].group("name").strip()
        name = re.sub(rf"^(?:{ROLE_WORDS})\s+", "", name)
        if re.match(r"(?:Diputad|Vocer|President|Secretari|Legislador|Senador)", name):
            name = None
        else:
            name = _clean_name(name)
        if name and not re.match(r"(?i)^(?:del?|de\s+l[ao]s?|la|los)\b", name) \
                and (len(name.split()) >= 2 or prev_speaker is None):
            return name, "quien"

    # 1b. participio + por = texto de DOCUMENTO aunque cite a los autores
    #     ("modificación presentada por los diputados X y Y, que dice:")
    if DOC_PARTICIPLE.search(clause) and DOC_NOUN.search(clause):
        return None, "documento"

    # 1c. cláusula que es SOLO un nombre propio: "Santana Suriel:"
    mb = BARE_NAME.match(clause)
    if mb and len(mb.group("name").split()) >= 2:
        name = _clean_name(mb.group("name"))
        if name:
            return name, "nombre_desnudo"

    # recolectar menciones con contexto de sujeto/objeto
    subjects, objects, roles = [], [], []
    for m in MENTION.finditer(clause):
        pre = clause[max(0, m.start() - 18):m.start()]
        is_object = bool(OBJECT_PREP.search(pre))
        name = (m.group("name") or "").strip()
        # el honorífico puede SER el rol ("la Presidencia", "el Presidente")
        role = _canon_role(m.group("role") or "", m.group("hon") or "")
        # honorífico genérico (señor/doctor/diputado) sin nombre ni rol → no es mención útil
        if not name and not role:
            continue
        entry = (name, role, m.start())
        (objects if is_object else subjects).append(entry)
        if role and not name:
            roles.append(role)

    # 2. último sujeto con nombre — salvo que un sujeto-ROL aparezca DESPUÉS: el sujeto
    # del verbo de habla es el más CERCANO al ancla («…Hubiere solicitaba la palabra,
    # el Diputado Presidente le señaló:» → PRESIDENTE). Decide la POSICIÓN, no la categoría.
    named_subjects = [e for e in subjects if e[0]]
    role_only_subjects = [e for e in subjects if e[1] and not e[0]]
    if named_subjects:
        if role_only_subjects and role_only_subjects[-1][2] > named_subjects[-1][2]:
            # guarda: «en su condición/calidad/funciones de Presidente» es APOSICIÓN del
            # mismo sujeto, no una mención independiente
            pre_rol = clause[max(0, role_only_subjects[-1][2] - 30):role_only_subjects[-1][2]]
            if not re.search(r"(?:condici[óo]n|calidad|car[áa]cter|funciones?)\s+de\s*(?:el\s+|la\s+)?$", pre_rol, re.I):
                return role_only_subjects[-1][1], "rol_posterior"
        name = _clean_name(named_subjects[-1][0])
        if name:
            return name, "sujeto"

    # 3. concesión de palabra → objeto es orador
    named_objects = [e for e in objects if e[0]]
    if named_objects and CONCESSION.search(clause):
        name = _clean_name(named_objects[-1][0])
        if name:
            return name, "concesion"

    # 4. rol sin nombre (sujeto)
    role_subjects = [e[1] for e in subjects if e[1] and not e[0]]
    if role_subjects:
        return role_subjects[-1], "rol"

    # 4b. nombre sin honorífico + verbo de habla / cargo técnico
    for rx, rule in ((NAME_VERB, "nombre_verbo"), (NAME_TITLE, "nombre_cargo")):
        mn = rx.search(clause)
        if mn:
            name = _clean_name(mn.group("name"))
            if name and (len(name.split()) >= 2 or name.isupper()):
                return name, rule

    # 5. anáfora de continuación (explícita, o verbo de habla desnudo sin mención)
    if ANAPHORA.search(clause) and prev_speaker:
        return prev_speaker, "anafora"
    if SPEECH_VERB.search(clause):
        if VOTE_CONTEXT.search(clause):
            return "PRESIDENTE", "anafora_votacion"
        if prev_speaker:
            return prev_speaker, "anafora_verbo"

    # 6. documento
    if DOC_NOUN.search(clause):
        return None, "documento"

    # objeto con nombre sin verbo de concesión: mejor eso que nada si no hay más
    if named_objects:
        name = _clean_name(named_objects[-1][0])
        if name:
            return name, "objeto_fallback"

    if ANAPHORA.search(clause) is None and roles:
        return roles[-1], "rol"

    return None, "sin_referente"


# verbo de habla para variantes de ancla degradadas (sin ':' o sin comilla)
_VERB_NEAR = (r"(?:dij(?:o|eron)|manifest[óo]|expres[óo]|señal[óo]|indic[óo]|declar[óo]|"
              r"explic[óo]|pregunt[óo]|respondi[óo]|contest[óo]|agreg[óo]|añadi[óo]|"
              r"precis[óo]|apunt[óo]|afirm[óo]|coment[óo]|anunci[óo]|inform[óo]|expuso|"
              r"puntualiz[óo]|concluy[óo]|pronunci[óo]|exterioriz[óo]|leyó)")


def tag_narrative(text: str, incluir_documentos: bool = False) -> tuple[str, dict]:
    # anclas TIPADAS: (open_pos, colon_pos, kind)
    #   curly    → ': “'  (invariante principal; profundidad auto-reparadora)
    #   straight → ': "'  (comillas rectas; cierre en la siguiente ")
    #   curly sin colon → VERBO + '“' ("quien señaló “Realmente…")
    #   noquote  → VERBO + ':' + texto directo; solo se etiqueta si aparece la ” de
    #              CIERRE antes de la barrera (subcaso "apertura perdida")
    anchors = []
    seen = set()
    for m in re.finditer(r":\s*[“\"]", text):
        q = m.end() - 1
        anchors.append((q, m.start(), "curly" if text[q] == "“" else "straight"))
        seen.add(q)
    for m in re.finditer(rf"{_VERB_NEAR}[,;]?\s+(“)", text):
        q = m.end() - 1
        if q not in seen:
            anchors.append((q, q, "curly"))
            seen.add(q)
    for m in re.finditer(rf"{_VERB_NEAR}\s*(:)\s*(?![“\"<\n])(?=[A-ZÁÉÍÓÚÜÑ¿¡])", text):
        colon = m.start() + m.group(0).rindex(":")
        content = colon + 1
        while content < len(text) and text[content] in " \t":
            content += 1
        if (content - 1) not in seen:
            anchors.append((content - 1, colon, "noquote"))
            seen.add(content - 1)
    anchors.sort(key=lambda a: a[0])

    out = []
    stats = {"anchored_quotes": len(anchors), "tagged": 0, "document_skips": 0,
             "anaphora": 0, "unresolved": [], "healed_closures": 0,
             "forced_closures": 0, "quoteless_skipped": 0,
             "by_kind": {}, "by_rule": {}}
    prev_speaker = None
    cursor = 0

    for idx, (open_pos, colon_pos, kind) in enumerate(anchors):
        if open_pos < cursor:      # ancla dentro de una cita ya consumida
            continue
        # residuo de cabecera de página pegado al ancla ("dijo: ACTA NO. 55 DEL…")
        if kind == "noquote" and re.match(r"\s*ACTA\s+NO", text[open_pos + 1:open_pos + 12], re.I):
            stats["quoteless_skipped"] += 1
            continue
        # barrera anti-engullimiento: al CRUZAR cada ancla posterior se decide si
        # el span sigue abierto legítimamente (cita interna, sin ” previa) o si una
        # “ sin pareja atascó el contador (hay ” previa → cerrar ahí)
        barrier_idx = idx + 1
        clause = _clause_before(text, colon_pos)
        if (re.match(r"^(?:quien(?:es)?|la\s+cual|el\s+cual|de\s+[A-ZÁÉÍÓÚÜÑ])", clause)
                or len(clause) < 25):
            wider = _clause_before(text, colon_pos, segments=2)
            if len(wider) > len(clause):
                clause = wider
        speaker, rule = resolve_speaker(clause, prev_speaker)
        # sin referente → ensanchado progresivo de la cláusula (2 y 3 segmentos)
        if speaker is None and rule == "sin_referente":
            for seg in (2, 3):
                wider = _clause_before(text, colon_pos, window=900, segments=seg)
                if len(wider) <= len(clause):
                    continue
                speaker, rule = resolve_speaker(wider, prev_speaker)
                if speaker is not None or rule == "documento":
                    clause = wider
                    break
        stats["by_rule"][rule] = stats["by_rule"].get(rule, 0) + 1

        # localizar el cierre según el tipo de ancla
        depth, i, n = 1, open_pos + 1, len(text)
        end = None
        last_close = None   # última ” vista (candidata a cierre real si el conteo se atasca)

        if kind == "straight":
            # comillas rectas: sin anidamiento fiable → cerrar en la siguiente "
            j = open_pos + 1
            while j < n:
                if barrier_idx < len(anchors) and j >= anchors[barrier_idx][0]:
                    b_clause = _clause_before(text, anchors[barrier_idx][1])
                    b_sp, b_rule = resolve_speaker(b_clause, None)
                    if b_sp is not None or b_rule == "documento":
                        end = max(open_pos + 1, _clause_start(text, anchors[barrier_idx][1]) - 1)
                        stats["forced_closures"] += 1
                        break
                    barrier_idx += 1
                if text[j] == '"':
                    end = j
                    break
                j += 1
            if end is None:
                end = min(open_pos + 30000, n - 1)
                stats["healed_closures"] += 1
        elif kind == "noquote":
            # sin comilla de apertura: SOLO etiquetar si la ” de cierre aparece
            # antes de la barrera y a distancia razonable (apertura perdida)
            j, limit = open_pos + 1, min(open_pos + 3000, n)
            while j < limit:
                if barrier_idx < len(anchors) and j >= anchors[barrier_idx][0]:
                    end = None
                    break
                if text[j] == "”":
                    end = j
                    break
                if text[j] == "“":   # se abre otra cita: esto no era discurso directo
                    end = None
                    break
                j += 1
            if end is None:
                stats["quoteless_skipped"] += 1
                out.append(text[cursor:open_pos + 1])
                cursor = open_pos + 1
                continue

        while end is None and i < n:
            ch = text[i]
            # LÍMITE DURO al cruzar un ancla posterior con la cita aún "abierta":
            # si ya hubo ” (cierre real candidato), una “ sin pareja atascó el
            # contador → cerrar en esa última ”. Si NO hubo ”, es una cita interna
            # legítima ("me dijo: “ven”") → avanzar la barrera y seguir contando.
            if barrier_idx < len(anchors) and i >= anchors[barrier_idx][0]:
                if last_close is not None:
                    end = last_close
                    stats["forced_closures"] += 1
                    break
                # sin ” previa: ¿cita interna legítima o discurso interrumpido sin
                # cierre ("...") con narración de la relatora? Discriminar resolviendo
                # la cláusula del ancla-barrera: persona/rol/documento → es la relatora
                # → cerrar el span al inicio de esa cláusula.
                b_colon = anchors[barrier_idx][1]
                b_clause = _clause_before(text, b_colon)
                b_sp, b_rule = resolve_speaker(b_clause, None)
                if b_sp is not None or b_rule == "documento":
                    end = max(open_pos + 1, _clause_start(text, b_colon) - 1)
                    stats["forced_closures"] += 1
                    break
                barrier_idx += 1
            if ch == "“":
                at_para_start = bool(re.match(r"\n\s*$", text[max(0, i - 40):i])) or \
                                text[i - 1] == "\n"
                if not at_para_start:
                    depth += 1
                # continuación a inicio de párrafo: no incrementa
            elif ch == "”":
                depth -= 1
                last_close = i
                if depth == 0:
                    end = i
                    break
            elif ch == ":" and depth >= 1:
                # posible nueva ancla narrativa con cierre perdido: párrafo nuevo
                nxt = re.match(r":\s*“", text[i:i + 4])
                if nxt:
                    seg_start = text.rfind("\n\n", open_pos, i)
                    if seg_start > open_pos:
                        para = text[seg_start:i]
                        # el párrafo debe ser narrativo (no empezar con “)
                        if not para.strip().startswith("“") and MENTION.search(para):
                            end = seg_start
                            stats["healed_closures"] += 1
                            break
            i += 1
        if end is None:
            if last_close is not None:
                end = last_close
            elif barrier_idx < len(anchors):
                end = min(anchors[barrier_idx][0] - 1, open_pos + 30000)
            else:
                end = min(open_pos + 30000, n - 1)
            stats["healed_closures"] += 1

        speech = text[open_pos + 1:end].strip()
        # limpiar comillas de continuación a inicio de párrafo dentro del discurso
        speech = re.sub(r"(\n\s*)“", r"\1", speech)

        if speaker and len(speech) >= 3:
            out.append(text[cursor:colon_pos + 1])
            out.append(f'\n<int speaker="{speaker}">{speech}</int>\n')
            close_extra = 1 if end < n and text[end] in "”\"" else 0
            cursor = end + close_extra
            stats["tagged"] += 1
            stats["by_kind"][kind] = stats["by_kind"].get(kind, 0) + 1
            prev_speaker = speaker
        elif rule == "documento":
            # Cita documental. Se consume el span completo en cualquier caso, para que sus
            # anclas internas (enmiendas, artículos citados) no generen falsos
            # "sin_referente" en cascada.
            #
            # ⚠ Con `incluir_documentos` el documento SÍ se etiqueta, atribuido a quien lo
            # está leyendo (el orador anterior). Decisión del investigador (2026-08-03): el
            # material leído en acta se queda en `text` y será una variable de TIPO la que
            # diga si es discurso, votación, mesa o lectura de documento — apartarlo pierde
            # información que puede interesar a otros estudios. En DO son 13.644 documentos
            # y el corpus publicado retenía por eso solo el 17% del texto del acta.
            stats["document_skips"] += 1
            close_extra = 1 if end < n and text[end] in "”\"" else 0
            if incluir_documentos and prev_speaker and len(speech) >= 3:
                out.append(text[cursor:colon_pos + 1])
                out.append(f'\n<int speaker="{prev_speaker}" kind="documento">{speech}</int>\n')
                stats["documentos_incluidos"] = stats.get("documentos_incluidos", 0) + 1
            else:
                out.append(text[cursor:end + close_extra])
            cursor = end + close_extra
        elif len(speech) < 60:
            # cita corta sin referente = palabra/frase entrecomillada inline (benigna)
            stats["inline_word_quotes"] = stats.get("inline_word_quotes", 0) + 1
            out.append(text[cursor:open_pos + 1])
            cursor = open_pos + 1
        else:
            line_no = text.count("\n", 0, colon_pos) + 1
            stats["unresolved"].append({"line_number": line_no,
                                        "clause": clause[-120:],
                                        "rule": rule,
                                        "speech_head": speech[:80]})
            # sin referente sustantivo: no etiquetar y no consumir (candidato a pase LLM)
            out.append(text[cursor:open_pos + 1])
            cursor = open_pos + 1

    out.append(text[cursor:])
    return "".join(out), stats


def main():
    ap = argparse.ArgumentParser(description="Tagger narrativo (estilo DO)")
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--incluir-documentos", action="store_true",
                    dest="incluir_documentos",
                    help="etiqueta las citas documentales, atribuidas a quien las lee")
    ap.add_argument("--config", required=False, help="country_config (reservado)")
    args = ap.parse_args()

    text = Path(args.input).read_text(errors="replace")
    tagged, stats = tag_narrative(text, incluir_documentos=args.incluir_documentos)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(tagged)

    stats["unresolved_count"] = len(stats["unresolved"])
    stats["unresolved"] = stats["unresolved"][:20]
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
