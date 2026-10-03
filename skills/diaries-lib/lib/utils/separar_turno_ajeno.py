#!/usr/bin/env python3
"""Separa el turno de otro orador incrustado en una intervención. Vocabulario POR PAÍS.

El fenómeno es común —dentro de un turno arranca otro y el etiquetado no lo cortó— pero **la
forma del marcador es de cada país**, así que el patrón no se comparte:

    BR   O SR. NOME (PMDB-SC. Pela ordem.)      versales + paréntesis   → `separar_incrustados.py`
    BR   O Sr. Nome –                           caja de título          → ídem, `--apartes`
    AR   Sr.⏎Avila⏎Gallo. —                     PARTIDO por el salto    → aquí

En AR el marcador viene roto por la composición en columnas: `Sr.` en una línea, el apellido
repartido en una o dos más, y el guion al final. Es el mismo fenómeno que
[[feedback_marcador_partido]] documentó en PA·GT·CO·PY, y en AR son **702 marcadores en 490
filas** con nombres de diputados reales (Jaroslavsky, Martínez Márquez, Tello Rosas).

Se cose el nombre, se corta la fila, y cada trozo sale como intervención propia vinculada con la
`matching_table.csv` del país.

⚠ **El corte NO se decide por distancia.** Un umbral «a partir del carácter 30» me ocultó 2.192
apartes en BR ([[feedback_apartes]]). Lo que decide es si hay TEXTO delante del marcador.

CLI:
    python separar_turno_ajeno.py --country ar [--medir]
"""
import argparse
import csv
import os
import re
import sys
import unicodedata
from collections import defaultdict

csv.field_size_limit(sys.maxsize)

MARCADOR = {
    # CL · «El señor NAVARRETE.-». Cuatro cosas que la primera versión NO veía, y por las que
    # medí 1.278 donde hay 4.433:
    #   · el apellido lleva GUION —VIERA-GALLO— y el OCR lo degrada a «~» o «_»;
    #   · el OCR PARTE las letras: «NA V ARRETE», «SOT A», «V ALDES», «ELGUET A»;
    #   · detrás va un paréntesis de tratamiento: «(Presidente)», «(don Jorge)», «(Secretario)»;
    #   · el terminador es un GUION, con «.» o «,» delante o sin nada: «.-», «,-», «.~», «-».
    # ⚠ El punto y la coma SUELTOS no valen: «El señor Ministro, que se encuentra presente…» es
    # prosa, y admitirlos metía 1.251 falsos. Y el guion debe ir seguido de espacio, porque si no
    # el cuantificador perezoso corta «VIERA-GALLO» en «VIERA» y toma su propio guion por final.
    # Un solo grupo, que es el marcador entero tal como lo escribe el acta.
    # ⚠ El marcador no siempre abre línea: el OCR lo pega al renglón anterior —«…OFICIO. . El
    # señor ALAMOS (Presidente).-»—. Son 87 más, así que vale también tras signo de cierre.
    # SV · el marcador viene PARTIDO PALABRA A PALABRA, una por línea:
    #     REP.⏎MANUEL⏎VICENTE⏎MENJÍVAR⏎ESQUIVEL:⏎Con mucho gusto Presidente.
    # De los 5.900 incrustados, **3.924 llevan cuatro saltos dentro del propio marcador** y solo
    # 1.027 van en una sola línea. Por eso el etiquetador no vio ninguno: ningún patrón anclado en
    # «inicio de línea + nombre + terminador» puede casar con esto ([[feedback_marcador_partido]]).
    # El grupo captura SOLO EL NOMBRE —sin `REP.` ni `DIPUTADO`— porque el `speaker_raw` de SV es
    # el nombre completo en versales («ERNESTO ALFREDO CASTRO ALDANA»), y así vincula directo.
    # ⚠ El apellido puede llevar PARTÍCULA en minúscula: «REP. ROBERTO JOSÉ d’AUBUISSON MUNGUÍA:».
    # Solo se admiten las partículas conocidas —d’ · de · del · da · dos · van · von · y—: abrir
    # el patrón a cualquier token en minúscula metía «presidente», «diputada» y «siguientes».
    # ⚠ Y la comilla de la partícula NO es la recta: el acta usa la curva «d’AUBUISSON» y la tilde
    # aguda «d´AUBUISSON». Con `'` sola no casaba ninguna de las cuatro.
    # ⚠ El cuerpo puede arrancar PEGADO al terminador con puntos suspensivos —«REP. CARLOS
    # ARMANDO REYES:…inmediatamente, para que realmente podamos ver…»—: son 85 turnos que se
    # perdían por exigir un espacio detrás. La elipsis marca que el orador RETOMA lo que venía
    # diciendo, cortado por el mobiliario de la transcripción.
    # ⚠ Solo valen `REP.` y `DIPUTAD[OA]`, que son inequívocos. Admitir `SR`/`PRESIDENTE` metería
    # los vocativos, que en SV son constantes.
    "sv": re.compile(r"(?m)^[ \t]*(?:REP|DIPUTAD[OA])\.?[ \t]*\n?"
                     r"((?:[ \t]*(?:(?:de|del|da|dos|van|von|y)[ \t]+)?"
                     r"(?:[a-zñ]{1,2}[’'´`])?"
                     r"[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ'’´]{1,20}[ \t]*\n?){2,6}?)"
                     r"[ \t]*[:.](?=\s|…|\.\.\.)"),
    # PE · «El señor CÁCERES VELÁSQUEZ, Róger (FNTC).— La palabra, señor Presidente.»
    # El `speaker_raw` del corpus son SOLO LOS APELLIDOS en versales —«LESCANO ANCIETA»,
    # «VELÁSQUEZ QUESQUÉN»—, así que para vincular hay que quitar el nombre de pila y la sigla del
    # grupo, que van detrás de la coma y entre paréntesis. El terminador es la raya, pegada o no.
    "pe": re.compile(r"(?m)(?:^[ \t]*|(?<=[.!?»])[ \t]*)((?:El|La)\s+se(?:ñ|n)or(?:a|ita)?\s+"
                     r"[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ' ]{2,40}?"
                     r"(?:,\s*[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){0,2})?"
                     r"(?:\s*\([^)\n]{0,40}\))?)\s*\.?\s*[—–-]\s*"),
    # PA · el marcador va en VERSALES y termina en DOS PUNTOS, y tiene CUATRO formas, las cuatro
    # tomadas de los `speaker_raw` que el propio corpus ya usa (81.445 «PRESIDENTE», 52.553
    # «PRESIDENTE ENCARGADO», 37.686 «SUBSECRETARIO GENERAL», y los nominales «NOMBRE, PRESIDENTE»):
    #   · el cargo pelado                    «PRESIDENTE ENCARGADO:»
    #   · el tratamiento parlamentario       «H. L . REYMO HURTADO LAY:» · «H.D.» · «R.L.»
    #   · el título profesional              «LIC. JULIO LEDEZMA, ASESOR DEL MINISTERIO…:»
    #   · nombre seguido de cargo            «H.L. LAURENTINO CORTIZO COHEN, PRESIDENTE:»
    # ⚠ NO vale el patrón genérico «línea en versales terminada en dos puntos»: da 28.910 y casi
    # todo son rótulos —«HONORABLES LEGISLADORES EN LICENCIA:», «RESUELVE:», «CONSIDERANDO:»,
    # «AUSENTES:»—. Hay que anclarlo en las formas del país ([[feedback_descubrir_marcadores]]).
    # ⚠ El OCR destroza el terminador: los dos puntos salen como «i», «1» o «I» —«H.L. CARLOS
    # SANTANA i»— y el propio tratamiento se separa: «H . L.», «H. L .».
    # ⚠⚠ Pero esas tres letras SOLO valen a final de línea. Admitiéndolas en cualquier posición,
    # el corte caía DENTRO de una palabra —«SECRETA|RIO GENERAL», «LIC. JORGE R|ICARDO»— y salían
    # 6.534 cortes con el 7 % de vinculación. Y el tratamiento tiene que ser una sigla REAL
    # (H.L. · H.D. · R.L. · S.E.), no dos letras cualesquiera: con `[HRSC].[LDE]` entraban
    # «RESUELVE», «SECRETA» y «C. LUNES».
    "pa": re.compile(r"(?m)^[ \t]*((?:"
                     r"(?:(?:VICE)?PRESIDENT[EA]|(?:SUB|PRO)?SECRETARI[OA])"
                     r"(?:[ \t]+(?:ENCARGAD[OA]|GENERAL|ADJUNT[OA]))?"
                     r"|(?:H\s*\.\s*[LD]|R\s*\.\s*L|S\s*\.\s*E)\s*\.\s*"
                     r"[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ0-9 .,'’\-]{3,60}?"
                     r"|(?:LIC|DR|ING|ARQ|MGTR|PROF)\s*\.\s*[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ0-9 .,'’\-]{3,80}?"
                     r"|[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ0-9 .'’\-]{3,50}?,[ \t]*"
                     r"(?:(?:VICE)?PRESIDENT[EA]|(?:SUB|PRO)?SECRETARI[OA])[A-ZÁÉÍÓÚÑ ]{0,20}"
                     r"))[ \t]*(?::|;|(?<=[A-Z])[ \t]*[i1I](?=[ \t]*\n))[ \t]*(?:\n|(?=\S))"),
    # MX · dos familias, las dos de las legislaturas viejas y las dos con DOS PUNTOS:
    #   «El C. Carlos Víctor Manuel Carreto y Fernández de Lara: - Señor presidente…»
    #   «Pablo Gómez Alvarez: - …», sin tratamiento ninguno
    # ⚠ El marcador va a MEDIA LÍNEA, detrás de un punto —el investigador lo vio en
    # `MX001000300287`— así que el ancla de inicio de línea sola no basta.
    # ⚠ Los dos puntos SOLOS no valen, hace falta el GUION detrás: «Presidente: Herbert Taylor
    # Arthur; vicepresidente: Eduardo R…» es la lista de la mesa directiva, y «González:
    # Proposición con punto de acuerdo…» es una entrada de índice. Admitiendo los dos puntos a
    # secas salían 6.493 cortes con más ruido que señal; con el guion, 308 y limpios.
    # ⚠ El guion va PEGADO al texto la quinta parte de las veces —«EL C. Presidente: -Para recibir
    # el cuerpo del diputado…»— así que no puede exigirse espacio detrás: eran 70 más. Y el
    # paréntesis del marcador no siempre es «(desde su curul)»: también «(a las 10.15 horas)».
    # ⚠ Entre token y token va `[ \t]+`, NUNCA `\s+`: con `\s+` el nombre cruzaba el salto de
    # línea y se comía el rótulo anterior —«INSCRIPCIÓN PARA INTERVENCIONES\n\nEL C. Presidente:»
    # entraba como un solo nombre— y el marcador real quedaba dentro, sin cortar. El paréntesis
    # opcional tenía el mismo agujero: empezaba en `\s*`, así que cruzaba el salto igual y
    # «DEL ESTADO DE SONORA\n\nEL C. PRESIDENTE:» volvía a entrar como un nombre solo. Cualquier
    # `\s` dentro de un patrón de NOMBRE es un agujero: los nombres no cruzan párrafos.
    # ⚠⚠ Y el nombre tiene que ser un NOMBRE: cada token en mayúscula salvo los enlaces
    # (de·del·la·y). Sin esa regla, «El C. Presidente de la Mesa Directiva acordó dar entrada…»
    # entraba como orador —143 veces— porque el cuantificador perezoso alcanzaba unos dos puntos
    # setenta caracteres más allá.
    "mx": re.compile(r"(?m)(?:^[ \t]*|(?<=[.!?»])[ \t]*)("
                     r"(?:(?:El|La|EL|LA)\s+(?:mism[oa]\s+)?C+\.?\s*)?"
                     r"[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ'’.-]{1,22}"
                     r"(?:[ \t]+(?:de|del|la|las|los|y|e)[ \t]+[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ'’.-]{1,22}"
                     r"|[ \t]+[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ'’.-]{1,22}){0,8}"
                     r"(?:[ \t]*\([^)\n]{0,34}\)?)?"
                     r")\s*:\s*[-–—]\s*"),
    "cl": re.compile(r"(?m)(?:^[ \t]*|(?<=[.!?»\"’_])[ \t]*)((?:El|La)\s+se(?:ñ|n)or[a]?\s+"
                     r"[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑa-záéíóúñ'’\-~_ ]{2,40}?"
                     r"(?:\s*\([^)\n]{0,44}\))?)\s*[.,]?\s*[-–—~_](?=\s|$)"),
    # AR tiene DOS formas del mismo marcador y hacen falta las dos:
    #  (a) partido por la composición en columnas: `Sr.`⏎`Avila`⏎`Gallo. —`
    #  (b) en una línea y con el CARGO en minúscula entre el tratamiento y el apellido:
    #      `Sr. diputado Raimundi. -_Ya termino…`  ← señalado por el investigador (AR013003800032)
    # ⚠ Dos detalles que me costaron 546 marcadores: «diputado» va en MINÚSCULA —y mi patrón
    # exigía mayúscula tras `Sr.`— y el terminador puede ser `-_`, no solo guion y espacio.
    # El CARGO puede ir en su propia línea (`Sra.`⏎`diputada`⏎`Guzmán`) y el apellido llevar
    # PARTÍCULAS en minúscula (`Falcioni de Bravo`), así que ambos se admiten explícitamente.
    "ar": re.compile(r"(?m)^[ \t]*(Sra?\.)[ \t]*\n?"
                     r"(?:[ \t]*(?:diputad[oa]|se(?:ñ|n)or[a]?)[ \t]*\n?)?"
                     r"((?:[ \t]*(?:de|del|la|las|los|y)?[ \t]*"
                     # el apellido puede venir con las LETRAS ESPACIADAS por la composición:
                     # «L e n c i n a», «M a n z a n o». Se admite como variante del token.
                     r"(?:[A-ZÁÉÍÓÚÑ](?:[ \t][A-Za-zÁÉÍÓÚÑáéíóúñ]){2,20}"
                     r"|[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ'’]{1,24})[ \t]*\n?){1,4})"
                     # el guion puede caer en su PROPIA línea: «Sr.»⏎«Guelar.»⏎«—»
                     r"[ \t]*[.,]?[ \t\n]*[—–_-]"),
}


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
    a = ap.parse_args()
    iso, I = a.country.lower(), a.country.upper()
    rx = MARCADOR.get(iso)
    if not rx:
        print(f"  {I} · sin vocabulario de marcador medido para este país")
        return
    p = f"source/{iso}/standardize/{I}_interventions.csv"
    campos, filas, d = _lee(p)
    _, dep, _ = _lee(f"source/{iso}/standardize/{I}_deputies.csv")

    tab = {}
    mp = f"source/{iso}/match/matching_table.csv"
    if os.path.exists(mp):
        _, mt, _ = _lee(mp)
        for x in mt:
            if x.get("id_dep", "").strip():
                tab.setdefault(_N(x["speaker_raw"]), x["id_dep"])
    # ⚠ La mejor tabla es EL PROPIO CORPUS: ya tiene resuelto «El señor LEAY» → CL00175, y con
    # la forma tal como la escribe el acta. Solo se toman las formas UNÍVOCAS —si una cadena
    # apunta a dos personas, no sirve para vincular—. Sin esto, CL vinculaba el 0 %: su
    # `matching_table.csv` no existe y el padrón guarda «Leay Morán», no «LEAY».
    cuenta = defaultdict(set)
    for x in filas:
        if x["id_dep"].strip() and x["speaker_raw"].strip():
            cuenta[_N(x["speaker_raw"])].add(x["id_dep"])
    for k, v in cuenta.items():
        if len(v) == 1:
            tab.setdefault(k, next(iter(v)))
    atr, pornombre = {}, {}
    for x in dep:
        atr.setdefault(x["id_dep"], {}).setdefault(
            x.get("legislature", ""),
            (x.get("speaker_name", ""), x.get("sex", ""), x.get("party", ""), x.get("district", "")))
        for c in ("speaker_name", "last_name"):
            if x.get(c, "").strip():
                pornombre.setdefault(_N(x[c]), x["id_dep"])

    # ⚠ Asimetría deliberada. En MX el marcador puede ser un nombre PELADO seguido de dos
    # puntos, y esa forma la comparten los rótulos del acta: «Revolucionario Institucional:»
    # (84), «Revolución Democrática:» (51), «Cambio Climático y Recursos Naturales:». Ninguna
    # regla de forma los separa de un orador, porque tienen la MISMA forma. Así que donde el
    # marcador es débil se exige EVIDENCIA: el corte solo se hace si el nombre resuelve a una
    # persona del padrón o a una forma ya vinculada en el corpus. Un cargo (Presidente,
    # Secretario) se acepta igualmente: no vincula por diseño, como en el resto del corpus.
    EXIGE_VINCULO = {"mx"}
    _CARGO = re.compile(r"(?i)^(?:el\s+|la\s+)?(?:mism[oa]\s+)?c*\.?\s*"
                        r"(presidente|presidenta|presidencia|secretari|prosecretari|vicepresident)")

    def _resuelve(m, tab, pornombre):
        """¿El nombre del marcador es una persona conocida? Guardarraíl de `EXIGE_VINCULO`."""
        n = re.sub(r"\s+", " ", m.group(1)).strip(" .,:")
        so = re.sub(r"(?i)^(?:el|la)\s+(?:mism[oa]\s+)?c+\.?\s*", "", n)
        so = re.sub(r"\s*\([^)]*\)?\s*$", "", so)
        so = re.sub(r"\s*\(?\s*desde\s+(?:su|la)\s+curul\)?\s*$", "", so, flags=re.I).strip()
        # ⚠ Sin el núcleo onomástico, el guardarraíl RECHAZABA a las mujeres por su apellido de
        # casada: «La C. Rosalía Ramírez de Ortega» no está así en el padrón, y su turno se quedaba
        # sin separar. Es el sesgo de [[memoria_genero]] reproducido por mi propio guardarraíl —
        # una regla de evidencia hereda el sesgo de la fuente de evidencia. Se prueba también el
        # nombre sin la cola «de X».
        nuc = re.sub(r"\s+(?:de|del)\s+(?:la\s+|los\s+|las\s+)?\S+$", "", so)
        return bool(tab.get(_N(n)) or tab.get(_N(so)) or tab.get(_N(nuc))
                    or pornombre.get(_N(so)) or pornombre.get(_N(nuc)) or pornombre.get(_N(n)))

    salida, nuevas, vinc = [], 0, 0
    for x in filas:
        t = x["text"]
        cortes = [m for m in rx.finditer(t) if t[:m.start()].strip()]
        if iso in EXIGE_VINCULO:
            cortes = [m for m in cortes if _resuelve(m, tab, pornombre) or _CARGO.match(m.group(1).strip())]
        if not cortes:
            salida.append(x)
            continue
        x["text"] = t[:cortes[0].start()].strip()
        salida.append(x)
        for k, m in enumerate(cortes):
            fin = cortes[k + 1].start() if k + 1 < len(cortes) else len(t)
            cuerpo = t[m.end():fin].strip(" \n:.—–-")
            if len(cuerpo) < 20:
                continue
            g2 = m.group(2) if (m.lastindex or 0) >= 2 else m.group(1)
            nombre = re.sub(r"\s+", " ", g2).strip(" .,")   # el apellido, ya cosido
            # ⚠ El CARGO viaja dentro del nombre —«diputado Raimundi»— y así no casa con ningún
            # padrón: la vinculación caía al 26 %. Se retira antes de emparejar, pero se
            # CONSERVA en `speaker_raw`, que debe reflejar lo que dice el acta.
            # PA: fuera el tratamiento parlamentario o profesional, que no es parte del nombre
            solo = re.sub(r"^[HRSC]\s*\.?\s*[LDE]\s*\.?\s*", "", nombre)
            solo = re.sub(r"(?i)^(?:lic|dr|ing|arq|mgtr|prof)\s*\.\s*", "", solo)
            solo = re.sub(r"(?i)^(?:el|la)\s+(?:mism[oa]\s+)?c+\.?\s*", "", solo)
            # PE: el padrón y el corpus solo guardan los APELLIDOS; fuera el nombre de pila
            # tras la coma y la sigla del grupo entre paréntesis.
            solo = re.sub(r"(?i)^(?:el|la)\s+se(?:ñ|n)or(?:a|ita)?\s+", "", solo)
            solo = re.sub(r"\s*\([^)]*\)\s*$", "", solo)
            solo = re.sub(r",\s*[A-ZÁÉÍÓÚÑ][a-záéíóúñ].*$", "", solo).strip()

            solo = re.sub(r"(?i)^(?:el|la)\s+se(?:ñ|n)or[a]?\s+", "", solo)
            solo = re.sub(r"(?i)^(?:diputad[oa]|se(?:ñ|n)or[a]?)\s+", "", solo).strip()
            # ⚠ El OCR parte las letras del apellido: «NA V ARRETE» es NAVARRETE. Para
            # vincular se quitan los espacios internos de los tramos en VERSALES; el
            # `speaker_raw` conserva la forma del acta.
            # ⚠ Fuera la coletilla entre paréntesis: el tratamiento chileno «(Presidente)» y la
            # acotación mexicana «(desde su curul)», que el OCR además deja SIN CERRAR la mitad de
            # las veces. Sin quitarla, MX vinculaba el 27 % de los nombres de persona en vez del
            # 76 %. El `speaker_raw` la conserva: es información del acta, no ruido.
            solo = re.sub(r"\s*\(?\s*desde\s+(?:su|la)\s+curul\)?\s*$", "", solo, flags=re.I)
            solo = re.sub(r"\s*\([^)]*\)?\s*$", "", solo).strip()
            if solo.isupper():
                solo = solo.replace(" ", "")
            y = {c: "" for c in campos}
            for c in ("legislature", "session_number", "date", "session_type"):
                y[c] = x.get(c, "")
            y["speaker_raw"] = (f"{m.group(1)} {nombre}" if (m.lastindex or 0) >= 2 else nombre)
            y["dm_speech"] = "1"
            y["text"] = cuerpo
            # se prueba la forma tal cual, la cosida, y la del apellido sin espacios internos
            idp = (tab.get(_N(y["speaker_raw"])) or tab.get(_N(nombre)) or tab.get(_N(solo))
                   or tab.get(_N(re.sub(r"\s+", "", y["speaker_raw"])))
                   or pornombre.get(_N(solo)) or pornombre.get(_N(nombre), ""))
            if idp:
                vinc += 1
                v = atr.get(idp, {})
                t4 = v.get(y["legislature"]) or (next(iter(v.values())) if v else ("",) * 4)
                y["id_dep"] = idp
                y["speaker_name"], y["sex"], y["party"], y["district"] = t4
            salida.append(y)
            nuevas += 1

    print(f"  {I} · turnos separados: {nuevas:,} (vinculados {vinc:,},"
          f" {vinc/max(nuevas,1)*100:.0f}%) · corpus {len(filas):,} → {len(salida):,}")
    if a.medir:
        return
    cnt = defaultdict(int)
    for y in salida:
        if y["intervention_order"] == "0":
            continue
        k = (y.get("legislature", ""), y["date"], y.get("session_number", "").strip())
        cnt[k] += 1
        y["intervention_order"] = str(cnt[k])
    salida = [y for y in salida if y["text"].strip()]

    bak = p.replace(".csv", ".pre_ajeno.csv")
    tmp = p + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, delimiter=d)
        w.writeheader()
        w.writerows(salida)
    if not os.path.exists(bak):
        os.rename(p, bak)
    else:
        os.remove(p)
    os.rename(tmp, p)
    print(f"  ✓ corpus reescrito: {len(salida):,} filas")


if __name__ == "__main__":
    main()
