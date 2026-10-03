#!/usr/bin/env python3
"""BR: parte la fila cuando lleva DENTRO el turno de otro orador, y le da su hablante.

Señalado por el investigador (2026-08-10) con dos filas concretas. En 2003-06-10, orden 165, el
corpus atribuye a JANDIRA FEGHALI un texto que contiene:

    Sr. Presidente, na votação nominal do recurso, votei com o PCdoB.
    O SR. ADELOR VIEIRA (PMDB-SC.  Pela ordem.  Sem revisão do orador.)
    Sr. Presidente, votei com o meu partido, PMDB.

Es un turno entero de otra persona metido en el de la primera. `diaries-tag` no lo cortó.

## Las TRES colas del marcador brasileño

El marcador es `O SR. NOME (…)` y detrás puede venir:

    (Nome) –Tem V.Exa. a palavra.        guion pegado al paréntesis
    (PMDB-SC. Pela ordem.) – Sr. …       guion con espacios
    (PMDB-SC.  Sem revisão do orador.)   NADA: acaba en el paréntesis y salta de línea

La tercera es la que se me escapó al parchear la detección, y son 111 marcadores. El marcador se
reconoce por ir **al principio de línea** con `O SR./A SRA.` y paréntesis; el tratamiento va
DENTRO del propio marcador, así que aquí no se aplica el filtro anti-vocativo
([[feedback_marcador_con_parentesis]]).

## Qué hace

Corta la fila en cada marcador. La cabeza se queda con el orador original; cada trozo posterior
sale como intervención propia, con `speaker_raw` = el nombre del marcador, vinculado contra el
padrón por **nombre parlamentario** ([[feedback_nombre_parlamentario]]). El paréntesis además
declara partido y estado —`(PMDB-SC. …)`—, y eso se aprovecha para `party` y `district`.
Las filas nuevas se insertan detrás de la original y la jornada se renumera.

CLI:
    python separar_incrustados.py [--medir]
"""
import argparse
import csv
import os
import re
import sys
import unicodedata
from collections import defaultdict

csv.field_size_limit(sys.maxsize)
CORPUS = "source/br/standardize/BR_interventions.csv"
PADRON = "source/br/standardize/BR_deputies.csv"
FUENTE = "source/br/deputies/deputados_BR.csv"

# ── APARTE ──────────────────────────────────────────────────────────────────────────
# Señalado por el investigador (2026-08-10): dentro del turno, otro diputado interrumpe.
#     Ouço V.Exa. com prazer.
#     O Sr. Zico Bronzeado – …
# Lo distingue la CAJA: el turno completo va en versales —`O SR. NOME (PMDB-SC. …)`— y el
# aparte en caja de título, sin paréntesis de procedencia. 18.930 apartes en 18.526 filas.
#
# ⚠ Dónde TERMINA era la pregunta difícil, y estuve a punto de concluir lo contrario: en 12.590
# filas hay >500 caracteres tras el último aparte y parecía que el orador principal reanudaba.
# Medido de verdad —¿la cola se dirige al principal, con «V.Exa.» o su apellido en vocativo?—,
# **el 97,9 % de las colas SON el aparte**: corre hasta el siguiente marcador o hasta el final
# de la fila. El 2,1 % restante es el residuo asumido.
APARTE = re.compile(r"(?m)^[ \t]*((?:O|A)\s+Sr[a]?\.\s+[A-ZÁÂÃÉÊÍÓÔÕÚÇ][^\n–—-]{1,60}?)\s*[–—-]\s")

# ⚠ Dos cosas dejaban fuera 9.770 marcadores, y una de ellas por SEXO:
#   · el tratamiento FEMENINO se escribe con ordinal, no con punto —«A SRª JANDIRA FEGHALI»—, y
#     exigir `SRA?\.` lo borraba entero: **4.116 de los 9.770, el 42 %, todas mujeres**. Es el
#     mismo patrón de [[feedback_gender_bias_extraction]]: cuando el detector falla, quien
#     desaparece es una diputada. Se admiten SR. · SR · SRA. · SRA · SRª · SRª. · SRa.
#   · el PARÉNTESIS de procedencia no siempre está: «A SRA. KÁTIA ABREU -» son 1.032 más. Se
#     vuelve opcional, pero entonces el GUION pasa a ser obligatorio, que es lo que impide que
#     un vocativo suelto cuente como marcador.
_TRAT = r"SR(?:A|ª|º|a|ᵃ){0,2}\.{0,2}"          # SR. · SRA. · SRª · SRª. · SRAª · SRa
_ABRE = r"(?:O|A)\s+" + _TRAT + r"\s+"
_MAY = "A-ZÁÂÃÉÊÍÓÔÕÚÇ"
_MIN = "a-záéíóúâêôãõç"
# ⚠⚠ El paréntesis puede llevar un SALTO DE LÍNEA dentro —«(Vanessa Grazziotin. Bloco Socialismo
# e\nDemocracia/PCdoB - AM)»— y prohibirlo con `[^)\n]` dejaba fuera 141 marcadores. **103 de
# ellos femeninos, el 73 %**, y el mecanismo es de libro: la forma femenina es más larga —«Sem
# revisão da ORADORA» frente a «do ORADOR», y los bloques de las diputadas del PCdoB tienen
# nombres largos— así que la línea se parte DENTRO del paréntesis con más frecuencia en ellas.
# Tres caracteres de más en un patrón producen un sesgo de sexo del 73 %.
_PAR = r"\([^)]{0,220}\)"
# Cuatro maneras de cerrar el marcador, cada una con su nombre para saber cuál disparó:
#   `par`     paréntesis de procedencia, con guion detrás o sin él
#   `guion`   guion o raya, con espacio o pegado
#   `versal`  ni guion ni paréntesis: SOLO un espacio. ⚠ Es la arriesgada, y su guardarraíl es la
#             CAJA — el nombre va en VERSALES y el cuerpo trae minúsculas. Sin exigirlo, el
#             cuantificador perezoso cortaba a mitad de nombre («A SRª MARIA ») y la vinculación
#             se hundía del 93 % al 27 %; y se tragaba los títulos en versales, que no son turnos.
#   `lectura` la fórmula fija «…, servindo como 2º Secretário, procede à leitura da ata…», que no
#             es un guion: son lecturas de acta atribuidas a quien PRESIDÍA, no a la Secretaría.
# ⚠ La rama `lectura` termina EXACTAMENTE en «leitura», no unos caracteres más allá. Mi primera
# versión seguía con `[^\n:]{0,60}[:.]?` y ese cuantificador goloso **partió 990 palabras por la
# mitad** —«…que é ap» | «rovada.»—, un daño que ningún recuento delataba porque las filas
# seguían ahí y la vinculación subía. Un terminador se ancla en una frontera de palabra o no se
# ancla en nada.
# ⚠ El NOMBRE de cada rama necesita su propia acotación, y equivocarla no se ve en ningún recuento:
#   · en `lectura` puse un relleno `[^\n,]{0,40}?` para admitir «1º Suplente de Secretário», y ese
#     relleno se comió el nombre: el marcador quedaba en **«O SR. L»**, una letra, y la vinculación
#     se hundió al 48 %. Se arregla prohibiendo la coma DENTRO del nombre y exigiéndola detrás.
#   · en `guion` el nombre admitía cualquier carácter y se tragaba la prosa hasta la siguiente raya:
#     «O SR. MIRO TEIXEIRA - Veja só, Sr. Presi». Se arregla exigiendo VERSALES, que es como el
#     acta escribe el nombre del orador (la caja de título es el APARTE, otra cosa).
_NOM_VER = "[" + _MAY + r"][" + _MAY + r"0-9'’.\- ]{2,60}?[" + _MAY + r"]{2}"
MARCA = re.compile(
    r"(?m)^[ \t]*(?:"
    r"(?P<f_par>" + _ABRE + r"[" + _MAY + r"][^\n(]{0,70}?)\s*(?P<par>" + _PAR + r")\s*[–—:-]?\s*"
    r"|(?P<f_gui>" + _ABRE + _NOM_VER + r")\s*[–—-]\s*"
    r"|(?P<f_ver>" + _ABRE + _NOM_VER + r")[ \t:](?=[" + _MAY + r"][" + _MIN + r"])"
    r"|(?P<f_lec>" + _ABRE + r"[" + _MAY + r"][^\n(,]{0,70}?)\s*,\s*(?:[^\n,]{0,40},\s*)?"
    r"(?:servindo\s+como|para\s+proceder)[\s\S]{0,60}?procede?\s+à\s+leitura\s*"
    r")")


def _forma(m):
    """El marcador tal como lo escribe el acta, venga de la rama que venga."""
    for k in ("f_par", "f_gui", "f_ver", "f_lec"):
        if m.group(k):
            return re.sub(r"\s+", " ", m.group(k))   # el marcador puede venir partido en 3 líneas
    return ""
# dentro del paréntesis, la sigla del partido y el estado: «PMDB-SC. Pela ordem.»
SIGLA = re.compile(r"^\(\s*([A-ZÁÉÍÓÚ]{2,12}(?:/[A-Z]{2,12})?)\s*[-–]\s*([A-Z]{2})\b")


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
    ap.add_argument("--apartes", action="store_true",
                    help="separa los APARTES (caja de título) en vez de los turnos en versales")
    ap.add_argument("--medir", action="store_true")
    a = ap.parse_args()
    campos, filas, d = _lee(CORPUS)
    RX = APARTE if a.apartes else MARCA
    _, dep, _ = _lee(PADRON)
    _, src, _ = _lee(FUENTE)

    # nombre (parlamentario y civil) → id_dep, para vincular al orador del marcador
    uri = next(k for k in src[0] if "uri" in k.lower())
    pornombre = {}
    for x in src:
        n = re.search(r"(\d+)\s*$", (x[uri] or "").rstrip("/"))
        if not n:
            continue
        idp = "BR" + n.group(1)
        for c in ("nome", "nomeCivil"):
            if x.get(c):
                pornombre.setdefault(_N(x[c]), idp)
    atr = {}
    for x in dep:
        atr.setdefault(x["id_dep"], {}).setdefault(
            x.get("legislature", ""),
            (x.get("speaker_name", ""), x.get("sex", ""), x.get("party", ""), x.get("district", "")))
    sexo = {x["id_dep"]: x.get("sex", "") for x in dep}
    nombre = {x["id_dep"]: x.get("speaker_name", "") for x in dep}

    salida, nuevas, vinc = [], 0, 0
    for x in filas:
        t = x["text"]
        # ⚠ El criterio NO es una distancia. Puse «más de 30 caracteres» para no partir por el
        # marcador que abre la propia fila, y con eso **bloqueé 2.192 apartes**: en «Não,
        # absolutamente.\nO Sr. Murilo Zauith - …» el aparte arranca en el carácter 20. Lo que
        # decide es si hay TEXTO delante: si lo hay, el marcador está incrustado.
        cortes = [m for m in RX.finditer(t) if t[:m.start()].strip()]
        if not cortes:
            salida.append(x)
            continue
        # la cabeza se queda con el orador original
        x["text"] = t[:cortes[0].start()].strip()
        salida.append(x)
        for k, m in enumerate(cortes):
            fin = cortes[k + 1].start() if k + 1 < len(cortes) else len(t)
            cuerpo = t[m.end():fin].strip(" \n:.—–-")
            if len(cuerpo) < 20:
                continue
            forma = _forma(m).strip()
            crudo = re.sub(r"^(?:O|A)\s+" + _TRAT + r"\s*", "", forma, flags=re.I).strip()
            y = {c: "" for c in campos}
            for c in ("legislature", "session_number", "date", "session_type"):
                y[c] = x.get(c, "")
            y["speaker_raw"] = crudo
            y["dm_speech"] = "1"
            y["text"] = cuerpo
            idp = pornombre.get(_N(crudo), "")
            if not idp:
                # `O SR. PRESIDENTE (Ramez Tebet)` — el cargo no vincula, pero el paréntesis
                # NOMBRA a quien lo ocupa. Solo se acepta si dentro no hay sigla de partido:
                # `(PMDB-SC. Pela ordem.)` es procedencia, no un nombre.
                par = m.group("par") or ""
                dentro = par[1:-1].strip() if len(par) >= 2 else ""
                if dentro and not SIGLA.match(par):
                    cand = re.split(r"[.,;]", dentro)[0].strip()
                    if 4 <= len(cand) <= 60:
                        idp = pornombre.get(_N(cand), "")
                        if idp:
                            y["speaker_raw"] = f"{crudo} ({cand})"
            if idp:
                vinc += 1
                y["id_dep"] = idp
                y["speaker_name"] = nombre.get(idp, "") or crudo.title()
                y["sex"] = sexo.get(idp, "")
                v = atr.get(idp, {})
                t4 = v.get(y["legislature"]) or (next(iter(v.values())) if v else ("",) * 4)
                y["party"], y["district"] = t4[2], t4[3]
            g = SIGLA.match(m.group("par") or "")
            if g:
                y["party"] = y["party"] or g.group(1)
                y["district"] = y["district"] or g.group(2)
            salida.append(y)
            nuevas += 1

    print(f"  BR · {'apartes' if a.apartes else 'turnos'} separados: {nuevas:,} (vinculados {vinc:,},"
          f" {vinc/max(nuevas,1)*100:.0f}%) · corpus {len(filas):,} → {len(salida):,}")
    if a.medir:
        for y in [z for z in salida if z.get("speaker_raw") and z["text"] and
                  z is not filas[0]][:0]:
            pass
        return

    cnt = defaultdict(int)
    for y in salida:
        if y["intervention_order"] == "0":
            continue
        k = (y.get("legislature", ""), y["date"], y.get("session_number", "").strip())
        cnt[k] += 1
        y["intervention_order"] = str(cnt[k])
    salida = [y for y in salida if y["intervention_order"] != "0" or len(y["text"].strip()) >= 120]

    bak = CORPUS.replace(".csv", ".pre_separar.csv")
    tmp = CORPUS + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, delimiter=d)
        w.writeheader()
        w.writerows(salida)
    if not os.path.exists(bak):
        os.rename(CORPUS, bak)
    else:
        os.remove(CORPUS)
    os.rename(tmp, CORPUS)
    print(f"  ✓ corpus reescrito: {len(salida):,} filas")


if __name__ == "__main__":
    main()
