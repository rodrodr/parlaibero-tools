#!/usr/bin/env python3
"""Atribuye la presidencia leyendo a quién NOMBRA el acta, y por TRAMO, no por sesión.

Señalado por el investigador (2026-08-11) en los dos países a la vez:

    PA  «…el H.L Alberto Magno Castilero, Presidente Encargado de la Asamblea Legislativa,
         dio inicio a la sesión ordinaria…»                          (PA002035000000, Prolegomena)
    MX  «PRESIDENCIA DEL C. DIPUTADO SÓCRATES RIZZO GARCÍA»          (MX001000100000, Prolegomena)

El corpus tenía esas filas con `speaker_raw = 'PRESIDENTE ENCARGADO'` y sin `id_dep`, mientras el
acta decía el nombre dos párrafos más arriba.

## Por qué por TRAMO y no por sesión

En MX la declaración **también aparece a mitad de sesión** —«Presidencia del diputado X»— porque la
mesa se releva: el 67 % de las jornadas mexicanas tienen más de una presidencia
([[feedback_juez_genero_vocativo]]). Atribuir la primera declaración a toda la sesión sería
exactamente el error que ese juez destapó. Así que cada declaración abre un TRAMO y solo alcanza
hasta la siguiente. En PA la declaración vive en el Prolegomena y el tramo es la sesión entera.

## Tres guardarraíles, y ninguno es opcional

1. **Solo se tocan filas cuyo `speaker_raw` es un CARGO de presidencia y no tienen `id_dep`.** Una
   fila con nombre propio ya resuelto no se toca nunca.
2. **El nombre declarado tiene que resolver en el padrón.** Si no resuelve, no se inventa nada.
3. ⚠ **Si la forma declara SEXO —`PRESIDENTA`, `La Presidenta`— el sexo de la persona resuelta
   tiene que coincidir.** Es un control independiente y gratuito: la forma viene del texto y el
   sexo del padrón. Sin él se repetiría el fallo de UY, donde 16.812 filas de «A PRESIDENTA»
   acabaron en un hombre ([[feedback_rol_vinculado_en_bloque]]).

CLI:
    python presidencia_declarada.py --country pa [--medir]
"""
import argparse
import csv
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict

from rapidfuzz import fuzz

csv.field_size_limit(sys.maxsize)

# ⚠⚠ NO son la presidencia de la cámara, y hay que excluirlas SIEMPRE: «Presidencia de la
# REPÚBLICA», «de la ASAMBLEA GENERAL», «de la COMISIÓN de Hacienda». Esta exclusión ya estaba
# documentada para el juez del vocativo (`_OTRO_CARGO` en `conformidad.py`) y aun así la he
# omitido TRES veces en una sola jornada —MX, PE y UY—, cada vez atribuyendo el jefe de Estado o
# quien presidía una comisión como si presidiera la sesión. Por eso vive aquí como constante
# compartida y no dentro del patrón de cada país: una exclusión aprendida en un control tiene que
# poder aplicarse a todos los que miran el mismo texto, sin volver a escribirla.
# ⚠ Y hay que consumir el ARTÍCULO ENTERO antes del lookahead: con `DE\s*L?\s*`, la ele de «LA»
# se consumía sola y el negativo veía «A REPÚBLICA» en vez de «REPÚBLICA», así que no disparaba.
# ⚠ El ARTÍCULO va DENTRO del negativo. Dejarlo fuera como opcional permite que el motor
# retroceda, no lo consuma, y el lookahead vea «LA REPÚBLICA» —que no está en la lista— en vez de
# «REPÚBLICA». Con el artículo dentro, no hay forma de esquivarlo.
_NO_CARGO = (r"(?!(?:l[ao]s?\s+|est[ae]\s+)?(?:rep[úu]blica|asamblea|comisi[óo]n|mesa|junta|senado|"
             r"c[áa]mara|tribunal|corte|gobierno|consejo|instituto|partido|congreso|"
             r"naci[óo]n|banco|directiva)\b)")

# Quién declara la presidencia, en las palabras de cada país
DECLARA = {
    # «el H.L Alberto Magno Castilero, Presidente Encargado de la Asamblea Legislativa»
    # ⚠ Sin atar la fórmula a «dio inicio a la sesión», el patrón también casaba con MENCIONES
    # dentro de un discurso —«de 1994, cuando era Presidente de la Asamblea»— y esas abrían un
    # tramo con un presidente PASADO. La declaración válida es la del acta al abrir la sesión.
    "pa": re.compile(r"(?:H\s*\.?\s*[LD]\s*\.?\s*|licenciad[oa]\s+|[Hh]onorable\s+)?"
                     r"([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+(?:de|del|la|los)?\s*"
                     r"[A-ZÁÉÍÓÚÑ][a-záéíóúñ.]+){1,4}),?\s*"
                     r"(President[ae](?:\s+Encargad[oa])?)\s+de\s+la\s+Asamblea[^,\n]{0,30},?\s*"
                     r"(?=dio\s+inicio|declar[óo]\s+abierta|abri[óo]\s+la\s+sesi[óo]n)"),
    # UY · dos formas, y entre las dos cubren el 77 % de las sesiones:
    #   A «PRESIDENCIA PROVISORIA DEL SEÑOR REPRESENTANTE DON JULIO E. DAVEREDE»          (36 %)
    #   B la LISTA de la mesa, con el cargo entre paréntesis                              (69 %)
    #       PRESIDEN LOS SEÑORES REPRESENTANTES
    #       MAESTRA NORA CASTRO (Presidenta)
    #       ESCRIBANA BEATRIZ ARGIMÓN (1ra. Vicepresidenta)
    #       Y CARLOS VARELA NESTIER (4to. Vicepresidente)
    # ⚠⚠ La forma B es la mejor evidencia de todo el corpus para esto, porque **el acta misma
    # distingue** quién preside de quién es vicepresidente. El paréntesis tiene que ser
    # EXACTAMENTE «Presidente/a»: con «1ra. Vicepresidenta» dentro, se atribuiría la sesión a
    # quien no la presidía. Es justo el fallo que dejó 16.812 filas de «A PRESIDENTA» en un
    # hombre ([[feedback_rol_vinculado_en_bloque]]).
    # El tratamiento profesional —MAESTRA, ESCRIBANA, DOCTORA, CONTADOR— va delante del nombre y
    # se retira; el «PRESIDE EL SEÑOR REPRESENTANTE DON» de la forma A también.
    "uy": re.compile(r"(?im)^[ \t]*(?:(?:MAESTR|ESCRIBAN|DOCTOR|CONTADOR|PROFESOR|ARQUITECT|"
                     r"INGENIER)[AO]?\.?[ \t]+|Y[ \t]+)*"
                     r"([A-ZÁÉÍÓÚÑa-z][A-ZÁÉÍÓÚÑ'. a-z]{4,72}?)[ \t]*\(President[ae]\)"
                     r"|PRESIDENCIA\s+(?:PROVISORIA\s+)?DE(?:L|\s+LA|\s+EL)?\s+" + _NO_CARGO +
                     r"(?:SE(?:Ñ|N)OR[A]?\s+)?"
                     r"(?:REPRESENTANTE\s+)?(?:DON\s+|DO(?:Ñ|N)A\s+|SR[A]?\.?\s+)?"
                     r"([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ. ]{5,50}?)(?=\s*\n|\s{2,}|$)"),
    # PT · el Prolegomena trae un RÓTULO de carátula: «Presidente: Ex.mo Sr. Vasco da Gama
    # Fernandes». Lo declara el 98 % de las sesiones (4.836 de 4.932) y SIEMPRE en el Prolegomena,
    # nunca en el cuerpo: aquí no hay relevo que seguir, la sesión entera es un tramo.
    "pt": re.compile(r"(?im)^[ \t]*Presidente\s*:\s*"
                     r"(?:Ex\.?\s*m[oa]\.?\s*|Exmo\.?\s*|Ex\.?\s*ma\.?\s*)?"
                     r"(?:Sr\.?[ª]?\s*|Senhor[a]?\s*|Dr\.?[ª]?\s*)*"
                     r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][^\n]{4,60}?)\s*$"),
    # PE · «PRESIDENCIA DEL SEÑOR JAIME YOSHIYAMA». El `speaker_raw` del corpus es «PRESIDENTE»
    # (302.069 filas) y «PRESIDENTA» (99.577), sin nombre: el nombre está aquí.
    # ⚠ La forma PLURAL —«PRESIDENCIA DE LOS SEÑORES X, Y y Z»— nombra a TODOS los que presidieron
    # la jornada y no permite elegir uno; se excluye con el negativo `(?!LOS|LAS)`. Atribuir el
    # primero de la lista a toda la sesión sería el error del relevo otra vez.
    "pe": re.compile(r"(?i)presidencia\s+de\s*l\s*(?!os\b|as\b)"
                     r"(?!(?:rep[úu]blica|comisi[óo]n|mesa|junta|senado|c[áa]mara|tribunal|corte|"
                     r"gobierno|consejo|instituto|partido|congreso|naci[óo]n)\b)"
                     r"(?:se(?:ñ|n)or(?:a|ita)?\s+|sr[a]?\.?\s+|doctor[a]?\s+|congresista\s+)?"
                     r"([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ']+(?:\s+(?:de|del|la|los|y)?\s*"
                     r"[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ']+){1,4})"),
    # «PRESIDENCIA DEL C. DIPUTADO SÓCRATES RIZZO GARCÍA» · «Presidencia del diputado X»
    # ⚠⚠ «Presidencia de la REPÚBLICA» y «presidencia de la COMISIÓN de Información» NO son la
    # presidencia de la cámara. Sin excluirlas, la atribución tomaba el jefe de Estado o quien
    # presidiera una comisión como si presidiera la sesión. Es el mismo error que ya estaba
    # documentado en el juez de género ([[feedback_juez_genero_vocativo]], `_OTRO_CARGO`) y lo
    # repetí aquí: una exclusión aprendida en un control hay que llevarla a TODOS los que miran
    # el mismo texto. Por eso se exige además que detrás venga «diputado» o «C.»: el nombre
    # pelado tras «presidencia de la» es casi siempre una institución, no una persona.
    "mx": re.compile(r"(?i)presidencia\s+de\s*l\s*(?:la\s+)?"
                     r"(?!(?:rep[úu]blica|comisi[óo]n|mesa|junta|senado|c[áa]mara|tribunal|corte|"
                     r"gobierno|consejo|instituto|partido|congreso|asamblea|naci[óo]n)\b)"
                     r"(?:c\.?\s*)?(?:diputad[oa]\s+|dip\.?\s+)"
                     r"([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ']+(?:\s+(?:de|del|la|los|y)?\s*"
                     r"[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ']+){1,4})"),
}
# Qué `speaker_raw` es un cargo de presidencia, y qué sexo declara la forma (o ninguno)
CARGO = re.compile(r"(?i)^\W*(?:el|la|a)?\s*(?:c\.?\s*)?"
                   r"(vice)?president(?:e|a|ª)(?:\s+(?:encargad[oa]|en\s+funciones|"
                   r"provisional|accidental|adjunt[oa]))?\W*$")
FEM = re.compile(r"(?i)presidenta|presidentª")


def _N2(s):
    """Normaliza conservando los espacios, para poder trabajar por tokens."""
    s = "".join(c for c in unicodedata.normalize("NFD", str(s).upper())
                if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Z ]+", " ", s).strip()


def _N(s):
    s = "".join(c for c in unicodedata.normalize("NFD", str(s).upper())
                if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Z0-9]+", "", s)


def _lee(p):
    with open(p, encoding="utf-8") as fh:
        d = csv.Sniffer().sniff(fh.readline(), ";,").delimiter
        fh.seek(0)
        r = csv.DictReader(fh, delimiter=d)
        return list(r.fieldnames), list(r), d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", required=True)
    ap.add_argument("--medir", action="store_true")
    ap.add_argument("--corregir", action="store_true",
                    help="además de rellenar huecos, CORRIGE la atribución cuando contradice "
                         "lo que declara el acta")
    a = ap.parse_args()
    iso, I = a.country.lower(), a.country.upper()
    rx = DECLARA.get(iso)
    if rx is None:
        print(f"  {I} · sin patrón de declaración registrado")
        return
    p = f"source/{iso}/standardize/{I}_interventions.csv"
    campos, filas, d = _lee(p)
    _, dep, _ = _lee(f"source/{iso}/standardize/{I}_deputies.csv")

    # ⚠ El padrón no basta como fuente de nombres: «Yanibel Ábrego Smith» preside 9.465 filas del
    # corpus y aun así no resolvía. El corpus YA sabe quién es cada nombre —lo tiene resuelto en
    # sus propias filas vinculadas— y esa es la mejor tabla. Solo se toman las formas UNÍVOCAS.
    # padrón: nombre → (id, sexo). Se prueba también el núcleo sin la cola «de X»,
    # porque si no el guardarraíl rechaza a las mujeres por su apellido de casada.
    porn, sexo = {}, {}
    for x in dep:
        sexo[x["id_dep"]] = x.get("sex", "")
        for c in ("speaker_name", "last_name"):
            v = x.get(c, "").strip()
            if v:
                porn.setdefault(_N(v), x["id_dep"])
                nuc = re.sub(r"\s+(?:de|del)\s+(?:la\s+|los\s+|las\s+)?\S+$", "", v)
                if nuc != v:
                    porn.setdefault(_N(nuc), x["id_dep"])

    dos = defaultdict(set)
    for x in filas:
        if x["id_dep"].strip() and x["speaker_raw"].strip():
            v = re.sub(r",.*$", "", x["speaker_raw"]).strip()   # «NOMBRE, PRESIDENTE» → «NOMBRE»
            dos[_N(v)].add(x["id_dep"])
            sexo.setdefault(x["id_dep"], x.get("sex", ""))
    for k, v in dos.items():
        if len(v) == 1:
            porn.setdefault(k, next(iter(v)))

    # ⚠ El acta nombra en corto —«Carlos Ferrero»— y el padrón guarda el nombre civil entero
    # —«Carlos E. Ferrero Costa»—, así que la igualdad exacta falla en el 86 % de PE. Se añade un
    # cotejo por SUBCONJUNTO de tokens: la forma corta resuelve si TODOS sus tokens están en un
    # nombre del padrón y **solo en uno**. La unicidad es el guardarraíl: si dos personas encajan,
    # no se elige ninguna. Mínimo dos tokens, para que un apellido suelto no arrastre.
    subs = defaultdict(set)
    for x in dep:
        v = x.get("speaker_name", "").strip()
        if v:
            subs[frozenset(t for t in _N2(v).split() if len(t) > 2)].add(x["id_dep"])

    # ⚠ El OCR corrompe LETRAS DENTRO del nombre —«Vasco da Cama Fernandes» por «da Gama»— y
    # entonces ni la igualdad ni el subconjunto de tokens sirven, porque el token está mal escrito.
    # Último recurso: parecido literal con umbral ALTO y **unicidad**. Si dos personas del padrón
    # pasan del umbral, no se elige ninguna: un nombre corrupto no autoriza a adivinar.
    nombres = [(x["id_dep"], _N2(x.get("speaker_name", ""))) for x in dep
               if x.get("speaker_name", "").strip()]

    def _por_parecido(nom, umbral=90):
        """Parecido literal alto, o ANCLADO en el primer nombre y el último apellido.

        ⚠ Bajar el umbral a secas es lo que en PE emparejó a tres personas distintas llamadas
        FLORES ([[feedback_match_ventana]]). El ancla es más estrecha y más segura: «VASCO DA CAMA
        FERNANDES» y «VASCO DA GAMA LOPES FERNANDES» dan 84,6 —por debajo de 90— pero comparten el
        PRIMER nombre y el ÚLTIMO apellido, y la corrupción está en medio. Con las dos puntas
        fijas, 80 basta. Y en los dos casos se exige unicidad.
        """
        q = _N2(nom)
        if len(q) < 12:
            return ""
        qt = q.split()
        hit = {i for i, v in nombres if fuzz.ratio(q, v) >= umbral}
        if not hit and len(qt) >= 3:
            hit = {i for i, v in nombres
                   if (vt := v.split()) and len(vt) >= 3
                   and vt[0] == qt[0] and vt[-1] == qt[-1] and fuzz.ratio(q, v) >= 80}
        return next(iter(hit)) if len(hit) == 1 else ""

    def _por_tokens(nom):
        ts = frozenset(t for t in _N2(nom).split() if len(t) > 2)
        if len(ts) < 2:
            return ""
        hit = {i for k, v in subs.items() if ts <= k for i in v}
        return next(iter(hit)) if len(hit) == 1 else ""

    # tramos: cada declaración abre uno y alcanza hasta la siguiente de su sesión
    exactos = set()          # resueltos por IGUALDAD, no por parecido: los únicos que corrigen
    tramo = {}
    sinres = Counter()
    # ⚠ En PA, PT y UY la declaración vive SOLO en la carátula; buscarla en el cuerpo del debate
    # recoge MENCIONES —«bajo la presidencia del señor Diputado Alonso»— que abren un tramo con
    # alguien que no presidía: una sola de esas se llevó 83 filas por delante en UY. En MX y PE,
    # en cambio, la declaración reaparece a mitad de sesión porque la mesa se releva, y limitarla
    # al Prolegomena perdería los relevos. Es una propiedad del PAÍS, no del patrón.
    SOLO_CARATULA = {"pa", "pt", "uy"}

    for i, x in enumerate(filas):
        if iso in SOLO_CARATULA and x["intervention_order"] != "0":
            continue
        for m in rx.finditer(x["text"]):
            nom = re.sub(r"\s+", " ", next((g for g in m.groups() if g), "")).strip(" .,")
            # la forma A de UY arrastra el encabezamiento: «PRESIDE EL SEÑOR REPRESENTANTE DON X»
            nom = re.sub(r"(?i)^(?:PRESIDE[N]?\s+)?(?:EL|LA|LOS|LAS)?\s*"
                         r"(?:SE(?:Ñ|N)OR(?:ES|A|AS)?\s+)?(?:REPRESENTANTES?\s+)?"
                         r"(?:DON|DO(?:Ñ|N)A)?\s*", "", nom).strip()
            # el tratamiento profesional va delante también en la forma A: «Prof. JOSÉ C. MAHÍA»
            nom = re.sub(r"(?i)^(?:prof|dr|dra|esc|cr|cra|arq|ing|mtro|mtra|maestr[ao]|"
                         r"escriban[ao]|doctor[a]?|contador[a]?)\.?\s+", "", nom).strip()
            # el OCR pega el rol al nombre y la frase sigue: «diputadoJorge Carlos Ramírez Marín En»
            # ⚠ `c\.?` con `\s*` detrás se comía la C INICIAL DEL NOMBRE: «Carlos»→«arlos»,
            # «César»→«ésar», «Crispiano»→«rispiano». Una abreviatura solo lo es si la sigue un
            # punto o un espacio; sin exigirlo, el patrón muerde la primera letra del nombre y
            # ninguna de esas personas resuelve. Costaba 2.561 declaraciones solo en PE.
            nom = re.sub(r"(?i)^(?:c\.\s*|c\s+|diputad[oa]\s+|dip\.\s*|lic\.\s*)", "", nom)
            nom = re.sub(r"\s+(?:En|A|De|Y|El|La|Se|Que|Con|Por|Para)$", "", nom).strip()
            # ⚠ Se distingue la resolución ESTRICTA (igualdad exacta o núcleo sin la cola «de X»)
            # de la aproximada (subconjunto de tokens · parecido anclado). Rellenar un hueco puede
            # apoyarse en la aproximada; **CORREGIR una atribución existente, no**: es destructivo.
            # Sin esa distinción, una declaración se resolvió por parecido a `Jorge Alonso`
            # —0 filas en el corpus y 0 carátulas que lo nombren— y se llevaba 83 filas por delante.
            estricta = (porn.get(_N(nom))
                        or porn.get(_N(re.sub(r"\s+(?:de|del)\s+(?:la\s+)?\S+$", "", nom))))
            idp = estricta or _por_tokens(nom) or _por_parecido(nom)
            if idp and estricta:
                exactos.add(idp)
            # ⚠⚠ Si la declaración NO resuelve, el tramo se CIERRA. Dejarlo abierto con el
            # presidente anterior es peor que no atribuir: el acta está diciendo «cambió la
            # presidencia» y nosotros seguiríamos poniendo al de antes. Encontrado en muestra:
            # `MX001015000010` quedó atribuido a Ricardo Monreal cuando el acta declara a Gonzalo
            # Martínez Corbalá, que no resolvía. 2 de 6 filas de la muestra estaban mal por eso.
            tramo[i] = idp if idp else None
            if not idp:
                sinres[nom[:40]] += 1
            break

    usados = {x["id_dep"].strip() for x in filas if x["id_dep"].strip()}
    puestos = Counter()
    corregidas = Counter()
    choque = 0
    cur, cur_ses = None, None
    for i, x in enumerate(filas):
        if x["id_session"] != cur_ses:
            cur, cur_ses = None, x["id_session"]
        if i in tramo:
            cur = tramo[i]          # None = declaración ilegible: deja de atribuirse
        if cur is None or not CARGO.match(x["speaker_raw"] or ""):
            continue
        ya = x["id_dep"].strip()
        # ⚠ Corregir NO es rellenar. Solo se hace con `--corregir`, solo cuando el `speaker_raw`
        # es el CARGO PELADO (una fila con nombre propio no se toca nunca) y solo cuando el acta
        # declara a OTRA persona para esa misma sesión. El caso que lo motivó: PT atribuía 12.006
        # filas de la VI Legislatura a Eurico Silva Teixeira de Melo, que **no aparece declarado
        # como presidente en ninguna carátula**, mientras el acta nombraba a António Moreira
        # Barbosa de Melo —ausente del padrón— en 278 sesiones. La vinculación era del 100 % y
        # ningún control lo veía: es un fallo de MODELO ([[feedback_match_punto_critico]]).
        if ya:
            # ⚠⚠ Corregir en bloque APLASTA EL RELEVO. En PT no existe la forma «Vice-Presidente»:
            # quien ocupa la silla figura siempre como «Presidente» (302.767 filas), y 841 sesiones
            # ya reparten esa presidencia entre varias personas. Reatribuir todas al titular de la
            # carátula borraría a los vicepresidentes que presidieron de verdad — 50.227 filas.
            # Así que solo se corrige contra quien **NUNCA aparece declarado presidente en NINGUNA
            # carátula del corpus**: ese no presidió nunca, y su atribución es un artefacto del
            # emparejador. Eurico Silva Teixeira de Melo: 0 declaraciones en 4.847 carátulas, y
            # 12.006 filas. Barbosa de Melo, el que sí presidía, faltaba del padrón.
            # ⚠⚠ Y «nunca declarado» TAMPOCO basta: la carátula nombra SOLO al Presidente, así que
            # un vicepresidente que presidió no aparece nunca en ella —Júlio Miranda Calha lo fue—
            # y el guardarraíl lo habría borrado. La firma del defecto real es otra y es
            # inequívoca: **el presidente declarado no tiene NI UNA fila en su propia sesión**.
            # Eso solo pasa si el emparejador nunca lo encontró. Si ya tiene filas, lo demás son
            # vicepresidentes relevándolo y no se toca nada.
            # ⚠⚠⚠ Tres guardarraíles distintos me dieron 50.227, 14.936 y 29.704 correcciones. Que
            # la cifra dependa tanto del criterio ES la prueba de que el caso general NO es
            # determinable con estos datos: no se puede distinguir «mal atribuido» de «un
            # vicepresidente presidió de verdad», porque PT no escribe «Vice-Presidente» nunca y la
            # carátula solo nombra al titular. Matos Correia, Jorge Lacão y Teresa Vasconcelos
            # fueron vicepresidentes: corregirlos sería inventar.
            #
            # Solo se corrige donde la CADENA CAUSAL está completa: el presidente declarado no
            # tiene NI UNA fila en TODO el corpus, es decir el emparejador no pudo asignarle nada
            # porque **no estaba en el padrón**, y cada uno de sus turnos fue a parar al apellido
            # más parecido. Es el caso de António Moreira Barbosa de Melo —ausente del padrón,
            # 278 carátulas suyas, 11.898 filas en Eurico Silva Teixeira de Melo—. Ahí no hay
            # ambigüedad posible: nadie puede haber presidido «en su lugar» si él no existía.
            if not a.corregir or ya == cur or cur in usados or cur not in exactos:
                continue
            corregidas[(ya, cur)] += 1
        # ⚠ guardarraíl de sexo: si la FORMA es femenina, la persona tiene que serlo
        if FEM.search(x["speaker_raw"]) and sexo.get(cur, "") != "F":
            choque += 1
            continue
        puestos[cur] += 1
        if not a.medir:
            x["id_dep"] = cur
            x["sex"] = sexo.get(cur, "")
            for y in dep:
                if y["id_dep"] == cur:
                    x["speaker_name"] = y.get("speaker_name", "")
                    x["party"] = x["party"] or y.get("party", "")
                    break

    print(f"  {I} · declaraciones que resuelven en el padrón: "
          f"{sum(1 for v in tramo.values() if v):,} · "
          f"nombres que no resuelven: {sum(sinres.values()):,}")
    print(f"     filas de presidencia atribuidas: {sum(puestos.values()):,} "
          f"({len(puestos):,} personas distintas)")
    print(f"     descartadas porque la FORMA es femenina y la persona no: {choque:,}")
    if corregidas:
        print(f"     CORREGIDAS (el acta declara a otra persona): {sum(corregidas.values()):,}")
        nom = {x["id_dep"]: x.get("speaker_name", "") for x in dep}
        for (v, n), q in corregidas.most_common(5):
            print(f"       {nom.get(v, v)[:32]!r} → {nom.get(n, n)[:32]!r}  {q:,}")
    if a.medir:
        for k, v in sinres.most_common(4):
            print(f"       no resuelve: {k!r} ×{v}")
        return
    bak = p.replace(".csv", ".pre_presidencia.csv")
    tmp = p + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, delimiter=d)
        w.writeheader()
        w.writerows(filas)
    if not os.path.exists(bak):
        os.rename(p, bak)
    else:
        os.remove(p)
    os.rename(tmp, p)
    print("  ✓ corpus reescrito")


if __name__ == "__main__":
    main()
