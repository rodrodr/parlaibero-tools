#!/usr/bin/env python3
"""Verifica que el corpus publicado de un país cumple las decisiones metodológicas transversales.

**Por qué existe.** El proyecto acumula 130 decisiones registradas, 89 de ellas transversales, y
los países se procesaron en momentos distintos: los primeros no pudieron cumplir decisiones que
aún no existían. «Reprocesar para que todos entren en las mismas condiciones» solo es verificable
si esas condiciones están escritas como comprobaciones que se ejecutan. Este script las ejecuta.

Comprueba **solo lo observable en la salida publicada** (`{ISO2}_interventions.csv` y
`{ISO2}_deputies.csv`). Lo que depende de la fuente —cobertura de sesiones, fidelidad del OCR—
no se puede verificar aquí y no se finge que sí: sale como `n/d`.

⚠ **Un cero en un detector nuevo es sospechoso hasta explicarlo.** Varias comprobaciones informan
del denominador además del resultado, precisamente para que un 0 se pueda distinguir de un
detector ciego. Ver [[feedback_flattened_text_detectors]].

Uso:
    python3 conformidad.py --country es
    python3 conformidad.py --all            # los 15, en paralelo
"""
from __future__ import annotations

import argparse
import csv as _csv
import glob
import os
import re
import unicodedata as U
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

# `id_session` e `id_int` (2026-08-10, propuesta del investigador): identificadores únicos y
# estables que no dependen de la fecha —{ISO2}{legislatura:03d}{sesión:04d}{orden:05d}—, lo que
# resuelve de raíz la ambigüedad de dos sesiones el mismo día ([[feedback_sesiones_mismo_dia]]).
CANONICAS = ["id_session", "id_int",
             "legislature", "session_number", "date", "session_type", "intervention_order",
             "speaker_raw", "id_dep", "speaker_name", "sex", "party", "district", "dm_speech",
             "text"]
# `dm_speech` es binaria: 1 si la fila es una intervención, 0 si no. La fila que no lo es
# —sumario, recuento de votación, documento reproducido— no se aparta ni se borra: se MARCA.
DM = {"0", "1"}

# ── marcadores incrustados: un turno nuevo dentro del propio text ──────────────
# ⚠ El vocabulario NO se adivina: se DERIVA de las formas `speaker_raw` del propio país. Un
# patrón universal escrito a mano da a la vez falsos negativos y falsos positivos — probado:
# `DIPUTAD[OA]…:` marcaba 9.286 filas de GT, y la mayoría eran `DIPUTADOS PONENTES:`, el pie de
# firma de una iniciativa, no un orador. Ver [[feedback_descubrir_marcadores]].
_TOPE_FORMAS = 300     # las más pesadas; se informa qué cobertura representan


def _detector_del_pais(m: pd.DataFrame) -> tuple[re.Pattern | None, float]:
    """Regex de las formas de orador REALES del país, y qué % de filas cubren esas formas."""
    c = Counter(s.strip() for s in m.speaker_raw if len(s.strip()) >= 8)
    top = [f for f, n in c.most_common(_TOPE_FORMAS) if n >= 3]
    if not top:
        return None, 0.0
    cob = sum(c[f] for f in top) / max(len(m), 1)
    alt = "|".join(re.escape(f) for f in sorted(top, key=len, reverse=True))
    # dentro del texto, precedido de fin de turno anterior: no cuenta el arranque de la fila
    return re.compile(r"(?<=[.;:!?»\"\)])\s+(?:" + alt + r")", re.M), cob


def _cabezas_del_pais(m: pd.DataFrame) -> tuple[re.Pattern | None, int]:
    """Regex de las CABEZAS de marcador del país (los cargos), y cuántas son.

    La cabeza es el primer token de las formas de orador reales —SEÑOR, DIPUTADO, SECRETARIO,
    PRESIDENTE…— y se queda con las que encabezan al menos el 0,5% de las formas: así el
    vocabulario sale del país y no de una lista adivinada. Ver `_detector_del_pais`.
    """
    c = Counter(s.strip() for s in m.speaker_raw if len(s.strip()) >= 8)
    if not c:
        return None, 0
    ini = Counter()
    for f, k in c.items():
        t = re.split(r"[^\wÁÉÍÓÚÑÜ]+", _nrm(f).strip(), maxsplit=1)[0]
        if len(t) >= 4:
            ini[t] += k
    tot = sum(ini.values())
    cab = [t for t, k in ini.most_common(12) if k / max(tot, 1) >= 0.005]
    if not cab:
        return None, 0
    alt = "|".join(re.escape(t) for t in sorted(cab, key=len, reverse=True))
    # ⚠ SIN `re.I`: con mayúsculas y minúsculas indistintas, cualquier línea de prosa que
    # empiece «señor Presidente…» cuenta, y PY —que está corregido— daba 4,24%.
    return re.compile(r"^(?:" + alt + r")\b[^:\n]{0,60}$"), len(cab)


_COLA = re.compile(r"^[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ .'\-]{1,40}:(\s|$)")


def _versal(s: str) -> bool:
    L = [c for c in s if c.isalpha()]
    return len(L) >= 4 and sum(1 for c in L if c.isupper()) / len(L) >= 0.8


def _partido(t: str, cab: re.Pattern) -> bool:
    """¿Hay dentro del turno un marcador partido en dos líneas y por eso sin envolver?

    La firma es la PAREJA: una línea versal que abre con un cargo del país y NO cierra en ':',
    seguida inmediatamente de otra versal que sí lo hace —«SEÑOR DIPUTADO RICARDO GONZALEZ» /
    «ESCOBAR: Gracias…». Cada mitad por separado es inútil: la cabeza sola no queda al final
    del turno (queda en medio) y la cola sola marca la estructura documental del acta
    (`PUNTO CUARTO:` en GT, `CONSIDERANDO:` en DO: 2.634 y 232 falsos positivos).
    """
    ls = t.split("\n")
    for i in range(len(ls) - 1):
        a = ls[i].strip()
        if not a or not _versal(a) or not cab.match(a):
            continue
        b = ls[i + 1].strip()
        if b and _COLA.match(b) and _versal(b.split(":")[0]):
            return True
    return False


# Dos contextos donde una forma de orador aparece SIN abrir turno. Ambos son fenómenos
# documentados del acta, y sin excluirlos el detector es casi todo falso positivo:
#   · acotación entre paréntesis — GT: «(EL R. CAMEY CURUP HACE USO DE LA PALABRA)»
#   · pase de lista o votación nominal — SV: «CASTRO ALDANA PRESENTE SUECY CALLEJAS …»
# El voto puede ir alineado en columna, a decenas de espacios del nombre: la ventana es amplia
# a propósito. Con 14 caracteres SV daba 48 filas y casi todas seguían siendo pase de lista.
_LISTA = re.compile(r"^[\s.·-]{0,40}(?:PRESENTE|AUSENTE|A\s+FAVOR|EN\s+CONTRA|ABSTEN|"
                    r"S(?:Í|I)\b|NO\b|\(Ausente\))", re.I)


# Una forma solo abre turno si la sigue un terminador de marcador. Sin exigirlo, en países cuyo
# `speaker_raw` es un nombre pelado —PT: «Presidente», «Bernardino Soares»— cualquier VOCATIVO
# dentro del discurso («Sr. Presidente, …») cuenta como marcador: daba 350.603 filas, el 31%.
# ⚠ El marcador puede llevar un PARÉNTESIS entre la forma y el terminador, y entonces el guion
# va sin espacios: BR escribe «O SR. PRESIDENTE (Henrique Eduardo Alves) –Tem V.Exa. a palavra.»
# Sin contemplarlo, el detector daba **0,00 % de marcadores incrustados en BR** cuando el 100 %
# de sus Prolegomena traía un turno dentro. El guion pegado solo se acepta DETRÁS del paréntesis,
# que es lo que lo hace inequívoco; suelto seguiría siendo ambiguo.
# El terminador CON PARÉNTESIS se aísla aparte porque además decide sobre el tratamiento:
# en BR el marcador ES «O SR. PRESIDENTE (Nome) –», con el tratamiento DENTRO del propio
# marcador, así que la regla anti-vocativo lo descartaba y daba 0,00 % de incrustados.
_TERMINA_PAREN = re.compile(r"^\s*\([^)\n]{0,90}\)\s*[:—–-]")
# ⚠ El guion PEGADO al punto —«El señor NAVARRETE.- Señor Presidente…»— no pasaba: la rama del
# guion exigía espacio a los dos lados (`\s+[—–]\s`) y el guion-menos ni siquiera estaba en la
# clase. Por eso CL daba «marcadores incrustados ✓» con 4.433 dentro. Se exige espacio DETRÁS,
# que es lo que impide que «VIERA-GALLO» se lea como marcador terminado en su propio guion.
_TERMINA = re.compile(r"^(?:\s*\([^)\n]{0,90}\)\s*[:—–-]"
                      r"|\s*[.,]?\s*[-–—~_](?=\s)"
                      r"|\s*(?:[:.]\s+[A-ZÁÉÍÓÚÑÀÂÃÊÔÕÇ«¿¡]|[:]\s|\s+[—–]\s))")
# …y no lo abre si viene detrás de un tratamiento: es el vocativo, no el orador.
# ⚠ El título académico cuenta como tratamiento. En PT, «Sr. Dr. José Luís Nunes» y «Prof. Vital
# Moreira» se contaban como marcador incrustado porque solo se miraba `Sr.`: el nombre iba
# precedido de `Dr.`, que no estaba en la lista.
_TRATO = re.compile(r"(?:sr|sra|sr\.ª|ex|ex\.ª|se(?:ñ|n)or|senhor|dr|dra|dr\.ª|doutor[a]?|"
                    r"prof|prof\.ª|professor[a]?|eng|eng\.ª|lic|licenciad[oa]|"
                    r"ao|à|do|da|de|o|a)\W{0,3}$", re.I)


# Tercer contexto: la FIRMA al pie de un documento leído. Donde el `speaker_raw` del país es un
# apellido pelado —AR: «Lamberto», «Tello Rosas»— cualquier firmante de un proyecto lo dispara:
# «Alberto I. González. FUNDAMENTOS», «Adriana V. Puiggrós. ANTECEDENTE». Eran 2.461 de las 2.730
# filas de AR y 407 de PT (listas de firmantes con nombre completo), todas falsos positivos.
#
# ⚠ El discriminador NO es «va precedido de una inicial»: esa primera versión, medida en los 16,
# silenciaba 213 marcadores VERDADEROS de MX («El C. Presidente:») y 96 de GT («EL R. MALDONADO
# GUEVARA:»), donde la inicial es el tratamiento abreviado —Ciudadano, Representante—. Lo que
# distingue es qué PRECEDE a la inicial: un nombre de pila es firma; un artículo es tratamiento.
# Un nombre de pila lleva al menos tres minúsculas tras la mayúscula, y así «El»/«EL»/«La»
# quedan fuera por construcción. Medido en los 16: MX, GT y los demás quedan intactos.
# ⚠ La inicial la DESTROZA el OCR: «Jesús ). González», «Raúl 11. González», «Juan F, C. Elizalde».
# Exigir una letra dejaba pasar 1.079 listas de firmas de AR como si fueran turnos incrustados,
# justo al admitir el guion pegado. Se acepta cualquier glifo suelto seguido de punto, porque lo
# que identifica la firma no es la inicial sino el NOMBRE DE PILA que la precede (`_PILA`).
# ⚠ Ni `\b` sirve: entre el espacio y el «)» de «Jesús ).» NO hay frontera de palabra, y el
# guardarraíl no llegaba a dispararse. El ancla es el espacio anterior, no la frontera.
_INICIALES = re.compile(r"(?:(?<=[\s(])|^)"
                        r"(?:[A-ZÁÉÍÓÚÑ0-9()\[\]|!/\\]{1,2}[.,][\s\-–—]*)+$")
_PILA = re.compile(r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñü]{2,}[\s\-–—]*$")


def _firma(prev: str) -> bool:
    """¿Lo que precede a la forma es un NOMBRE DE PILA? Entonces es una firma, no un orador.

    ⚠ La inicial es OPCIONAL. Exigirla dejaba pasar 927 listas de firmas de AR, porque el OCR la
    destroza de mil maneras —«Alberto i.», «Gracia Af.», «Miguel .4.», «Osear ''F.»— y a veces
    sencillamente no la hay: «Silvia Martinez. - Heriberto Agüero». Lo que separa la firma del
    marcador es que el nombre de pila va PEGADO al apellido, sin puntuación en medio: `_PILA`
    solo admite espacios o guiones detrás, así que «…Presidente. El señor X.-» no lo dispara.
    """
    m = _INICIALES.search(prev)
    return bool(_PILA.search(prev[:m.start()] if m else prev))


# ⚠ Perseguir la inicial destrozada por el OCR no converge: «Alberto i.», «Gracia fvf.»,
# «Joseﬁ na V.», «Oscat -8.», «M ...». Lo que SÍ distingue a la firma es que viene en CADENA —la
# lista de firmantes de un proyecto encadena «Nombre Apellido. – Nombre Apellido. – …»— mientras
# que un turno de palabra no se encadena. Con tres eslabones en 260 caracteres, AR baja de 927 a
# 402 y CL solo pierde 9. Es un criterio de CONTEXTO, no de forma, y por eso resiste al OCR.
_CADENA = re.compile(r"[.,]\s*[-–—~]\s*[A-ZÁÉÍÓÚÑ]")


def _incrustados(t: str, det: re.Pattern) -> bool:
    for g in det.finditer(t):
        i = g.end()
        if not _TERMINA.match(t[i:i + 20]):
            continue
        if _LISTA.match(t[i:i + 56]):
            continue
        if _TRATO.search(t[max(0, g.start() - 12):g.start() + 1]):
            continue
        if _firma(t[max(0, g.start() - 60):g.start()]):
            continue
        ab, ce = t.rfind("(", 0, i), t.rfind(")", 0, i)
        if ab > ce:                      # dentro de un paréntesis todavía abierto
            continue
        if len(_CADENA.findall(t[max(0, g.start() - 130):i + 130])) >= 3:
            continue                     # cadena de firmas, no turnos
        return True
    return False

# ⚠ El vocativo se dirige a quien PRESIDE LA CÁMARA. «Señor Presidente de la República» es otro
# cargo y no dice nada del sexo de la presidencia: en DO era el 34,3 % de los vocativos contados,
# y el juez comparaba menciones al jefe de Estado con el sexo de quien presidía la sesión.
_OTRO_CARGO = (r"(?!\s+(?:de|del)\s+l?[ao]?\s*(?:rep[úu]blica|gobierno|congreso|senado|"
               r"c[áa]mara|comisi[óo]n|tribunal|corte|banco|junta|instituto|consejo|partido|"
               r"mesa\s+directiva))")
VF = re.compile(r"\bse(?:ñ|n)ora\s+presidenta\b" + _OTRO_CARGO, re.I)
VM = re.compile(r"\bse(?:ñ|n)or\s+presidente\b" + _OTRO_CARGO, re.I)


def _leer(p: str) -> pd.DataFrame:
    with open(p, encoding="utf-8") as fh:
        d = _csv.Sniffer().sniff(fh.readline(), ";,\t").delimiter
    return pd.read_csv(p, sep=d, dtype=str, keep_default_na=False)


def _nrm(s: str) -> str:
    s = U.normalize("NFD", str(s).upper())
    return "".join(c for c in s if U.category(c) != "Mn")


def revisar(c: str, fichero: str = "") -> dict:
    C = c.upper()
    r: dict[str, tuple[bool | None, str]] = {}
    pm = fichero or f"source/{c}/standardize/{C}_interventions.csv"
    pd_ = f"source/{c}/standardize/{C}_deputies.csv"
    if not os.path.exists(pm):
        return {"_pais": C, "_error": "sin corpus publicado"}
    m = _leer(pm)
    dep = _leer(pd_) if os.path.exists(pd_) else None

    # 1 · esquema canónico de 13 columnas, en orden (tr-0001, tr-0049)
    r["esquema 15 col"] = (list(m.columns) == CANONICAS,
                           f"{len(m.columns)} col" + ("" if list(m.columns) == CANONICAS else
                                                      f" · faltan {set(CANONICAS)-set(m.columns)}"))
    v = m[m.id_dep != ""] if "id_dep" in m.columns else m.iloc[:0]

    # 2 · sex completo y solo M/F en las filas vinculadas (tr-0001)
    if "sex" in m.columns:
        mal = int((~v.sex.isin(["M", "F"])).sum())
        r["sex en vinculadas"] = (mal == 0, f"{mal:,} sin M/F de {len(v):,}")
    else:
        r["sex en vinculadas"] = (False, "no existe la columna")

    # 3 · el padrón declara sex_source (tr-0002)
    r["padrón con sex_source"] = ((dep is not None and "sex_source" in dep.columns),
                                  "sí" if dep is not None and "sex_source" in dep.columns else "no")

    # 4 · legislatura como COLUMNA del padrón, sin colapsar (gt-0012, gt-0014)
    if dep is None:
        r["padrón legislatura larga"] = (None, "sin padrón")
    elif "legislature" not in dep.columns:
        r["padrón legislatura larga"] = (False, "no es columna")
    else:
        col = int(dep.legislature.str.contains(",").sum())
        dup = int(dep.duplicated(["id_dep", "legislature"]).sum())
        # ⚠ La unidad de observación puede ser la LEGISLATURA o el RANGO DE MANDATO. DO tiene
        # 1.400 filas para 796 personas con `legislature` vacía y `start_date`/`end_date`
        # llenos: es formato largo igual, con otra clave, y 0 repetidas por (id_dep, rango).
        # Exigir solo la etiqueta lo daba por incumplido y llevaba a reescribir un padrón
        # que ya estaba bien.
        clave_fecha = ""
        if dup and {"start_date", "end_date"} <= set(dep.columns):
            d2 = int(dep.duplicated(["id_dep", "start_date", "end_date"]).sum())
            rango = int(((dep.start_date.str.strip() != "") & (dep.end_date.str.strip() != "")).sum())
            if d2 == 0 and rango == len(dep):
                dup = 0
                clave_fecha = " · unidad = rango de mandato, no etiqueta de legislatura"
        r["padrón legislatura larga"] = (col == 0 and dup == 0,
                                         f"{col:,} colapsadas · {dup:,} filas repetidas{clave_fecha}")

    # 5 · integridad referencial matriz → padrón
    if dep is None:
        r["integridad referencial"] = (None, "sin padrón")
    else:
        h = set(v.id_dep) - set(dep.id_dep)
        r["integridad referencial"] = (not h, f"{len(h)} id huérfanos · {int(m.id_dep.isin(h).sum()):,} filas")

    # 6 · intervention_order 1..N, sin huecos ni repeticiones
    # El 0 es legítimo y opcional: son los **Prolegomena** —carátula, sumario, índice, pase de
    # lista— que preceden a la primera intervención sin desplazar su numeración. Puede haber
    # varios en una jornada con más de un acta, así que solo se exige que el tramo ≥1 sea 1..n.
    if "intervention_order" in m.columns:
        o = pd.to_numeric(m.intervention_order, errors="coerce")
        if o.isna().any():
            r["intervention_order"] = (False, f"{int(o.isna().sum()):,} no numéricos")
        else:
            m2 = m.assign(_o=o.astype(int))
            # ⚠ el nombre importa: `v` son las filas vinculadas y vive hasta la comprobación 15.
            # Reutilizarlo aquí con el operador morsa lo pisaba, y la vinculación bruta salía
            # 0,03% en vez de 89,56% — un corpus intacto pareciendo destruido.
            rot = sum(1 for _, g in m2.groupby(["legislature", "date", "session_number"])
                      if sorted(o1 := [x for x in g._o if x >= 1]) != list(range(1, len(o1) + 1)))
            r["intervention_order"] = (rot == 0, f"{rot:,} sesiones rotas de {m2.groupby(['legislature','date']).ngroups:,}")
    else:
        r["intervention_order"] = (False, "no existe")

    # 7 · marcadores incrustados en el text, umbral 0,1% (tr-0013)
    n = len(m)
    det, cob = _detector_del_pais(m)
    if det is None:
        r["marcadores incrustados"] = (None, "sin formas suficientes")
    else:
        inc = int(sum(_incrustados(t, det) for t in m.text))
        r["marcadores incrustados"] = (inc / n < 0.001 if n else None,
                                       f"{inc:,} filas = {100*inc/n:.3f}% (umbral 0,100%) · "
                                       f"detector = {_TOPE_FORMAS} formas propias que cubren "
                                       f"{100*cob:.0f}% del corpus")

    # 8 · texto vacío
    vac = int((m.text.str.strip() == "").sum())
    r["sin texto vacío"] = (vac == 0, f"{vac:,} filas")

    # 9 · el turno empieza en mayúscula o signo de apertura (tr-0048)
    ini = m.text.str.strip().str[:1]
    malini = int((~(ini.map(lambda x: bool(x) and (_nrm(x).isupper() or x in "«\"'(¿¡—-…0123456789")))).sum())
    r["inicio de turno"] = (malini / n < 0.02 if n else None, f"{malini:,} = {100*malini/n:.2f}% (umbral 2%)")

    # 9-bis · marcador PARTIDO por el salto de línea (PY 2026-08: ~100.000 turnos perdidos)
    # El OCR corta el marcador por el ancho de columna —«SEÑOR DIPUTADO RICARDO GONZALEZ /
    # ESCOBAR: Gracias…»— y un etiquetado que lo exige entero en una línea pierde el turno
    # ENTERO, sin que ningún recuento lo delate. Ver [[feedback_marcador_partido]].
    #
    # Firma en la matriz: dentro del turno anterior quedan las DOS mitades seguidas, una
    # línea de cargo sin ':' y otra que lo cierra. Ver `_partido`.
    cab, cobc = _cabezas_del_pais(m)
    if cab is None:
        r["marcador partido"] = (None, "sin formas suficientes")
    else:
        col = int(sum(_partido(t, cab) for t in m.text))
        r["marcador partido"] = (col / n < 0.002 if n else None,
                                 f"{col:,} turnos llevan dentro un marcador partido en dos líneas = "
                                 f"{100*col/n:.3f}% (umbral 0,200%) · vocabulario = "
                                 f"{cobc} cargos del propio país")

    # 10 · fechas ISO válidas
    f = pd.to_datetime(m.date, format="%Y-%m-%d", errors="coerce")
    r["fechas ISO"] = (not f.isna().any(), f"{int(f.isna().sum()):,} inválidas · {m.date.min()} → {m.date.max()}")

    # 11 · duplicación intra-sesión de texto largo
    lar = m[m.text.str.len() > 400]
    d2 = int(lar.duplicated(["legislature", "date", "speaker_raw", "text"]).sum())
    r["sin duplicados largos"] = (d2 / max(len(lar), 1) < 0.005,
                                  f"{d2:,} de {len(lar):,} textos >400 car.")

    # 12 · presidencia: filas de cargo sin vincular (tr-0035, tr-0041)
    esp = m.speaker_raw.str.contains(r"RESIDENT", case=False, regex=True)
    sinp = int((esp & (m.id_dep == "")).sum())
    r["presidencia atribuida"] = (sinp / max(int(esp.sum()), 1) < 0.05,
                                  f"{sinp:,} sin id de {int(esp.sum()):,} filas de presidencia")

    # 13 · juez de género del vocativo, control INDEPENDIENTE (tr-0041)
    #
    # Se juzga POR TRAMO de presidencia, no por jornada. Colapsar el día a una sola presidencia
    # con `most_common(1)` era insostenible: el 67 % de las jornadas de MX y el 54 % de las de UY
    # tienen relevo, así que los vocativos de dos personas distintas se contaban contra el sexo
    # de una sola. Un tramo = filas consecutivas de una misma jornada bajo la misma presidencia
    # identificada, y cada vocativo cuenta para el tramo en que aparece.
    #
    # Medido al adoptarlo: CL 95,8 → 99,1 % · MX 93,7 → 97,0 % · DO 90,2 → 94,9 %, y sobre MUCHOS
    # más casos (CL cuadruplica la muestra). **UY baja a 85,5 %** y no lo rescata subir el mínimo
    # de vocativos (3 → 50 solo llega a 89,2 % descartando el 75 % de los casos): ahí el juez deja
    # de fallar y empieza a acertar — lo que destapa es que la atribución de presidencia DENTRO
    # de la jornada en UY no es fiable. Ver [[feedback_juez_genero_vocativo]].
    sx = dict(zip(dep.id_dep, dep.sex)) if dep is not None and "sex" in dep.columns else {}
    voc = defaultdict(lambda: [0, 0])
    cur = clave = jor = None
    k = 0
    for l, d, idp, es, t in zip(m.legislature, m.date, m.id_dep, esp, m.text):
        if (l, d) != jor:                       # jornada nueva → se reinicia el tramo
            jor, cur, k = (l, d), None, 0
        if es and idp and idp != cur:           # cambia quien preside → tramo nuevo
            cur, k = idp, k + 1
            clave = (l, d, k, idp)
        if cur and "resident" in t:
            x = voc[clave]
            x[0] += len(VF.findall(t))
            x[1] += len(VM.findall(t))
    ac = ct = 0
    for (_l, _d, _k, i), (ff, mm) in voc.items():
        if ff + mm < 3:
            continue
        j = "F" if ff > mm * 2 else ("M" if mm > ff * 2 else "")
        if not j:
            continue
        ct += 1
        ac += int(j == sx.get(i, ""))
    r["juez de género"] = (ac / ct >= 0.95 if ct else None,
                           f"{ac:,}/{ct:,} = {100*ac/ct:.2f}%" if ct else "sin sesiones medibles")

    # 13b · el GÉNERO GRAMATICAL de la forma de cargo contra el sexo de quien se le atribuye
    #
    # Control interno, sin texto: «PRESIDENTA ENCARGADA» no puede ser un hombre. Basta la forma
    # y el padrón, así que no comparte nada con el juez del vocativo y los dos se vigilan solos.
    # Al estrenarlo (2026-08-10) descubrió ~83.000 filas mal atribuidas en 11 países: DO 20,4 % ·
    # MX 8,0 % · PT 7,8 % · PA 7,4 % · BR 3,2 % · PE 2,8 %. Ninguna otra comprobación las veía.
    #
    # Un fallo aquí puede ser de la atribución o del `sex` del padrón; como `sex` está medido al
    # 98,98 % ([[feedback_derivacion_sexo]]), la sospecha razonable recae en la atribución.
    # ⚠ SOLO la forma FEMENINA declara sexo. «Presidente» no dice nada:
    #   · en portugués es EPICENO — PT lo usa 302.767 veces y BR 735.834 para ambos sexos, así
    #     que una mujer llamada «Presidente» es portugués correcto;
    #   · en español muchos diarios lo usan como masculino genérico institucional (DO).
    # Aplicar la regla masculina daba 23.549 falsos positivos en PT y 23.928 en BR — más de la
    # mitad de los «83.000» del primer recuento. Ver [[feedback_genero_del_cargo]].
    gf = m.speaker_raw.str.strip().str.fullmatch(
        r"(?:LA\s+)?(?:VICE)?PRESIDENTA(?:\s+ENCARGADA|\s+A\.?I\.?)?", case=False, na=False)
    sexo_fila = m.id_dep.map(sx).fillna("")
    decl = gf & (m.id_dep != "") & (sexo_fila != "")
    choca = int((gf & (sexo_fila == "M")).sum())
    nd = int(decl.sum())
    r["género del cargo"] = (choca / nd < 0.01 if nd else None,
                             f"{choca:,} de {nd:,} filas cuya forma declara sexo lo contradicen"
                             f" = {100*choca/nd:.1f}% (umbral 1,0%)" if nd
                             else "sin formas que declaren sexo")

    # 14 · NADA apartado a sidecar (decisión del investigador, 2026-08-03)
    # El material leído en acta se queda en `text`; una variable de TIPO dirá si es discurso,
    # votación, mesa o lectura de documento. Un sidecar de contenido es hoy una no conformidad,
    # y además deja huecos en `intervention_order`: las posiciones apartadas no se renumeran.
    # ⚠ El MOBILIARIO DE PÁGINA (cabeceras, pies, folios) NO entra en «reintegrar todo»: no es
    # contenido del acta sino artefacto de la página impresa. Se informa aparte, no se suspende.
    # ⚠ El contenido apartado NO vive solo en `standardize/*sidecar*.csv`. AR salía LIMPIO aquí
    # y tenía 537,7 M de caracteres —el DOBLE de su corpus— en `merge/insertions/insertions.jsonl`.
    # Se busca por toda la carpeta del país y en cualquier formato.
    def _tiene_text(p):
        """Un sidecar de CONTENIDO lleva columna text; los de metadatos (via_tipo,
        tipo_source, procedencia) no. Y las copias .pre_* son backups, no material apartado:
        contarlas dio 319.860 filas fantasma en SV."""
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                head = fh.readline().lower()
            return '"text"' in head or ";text" in head or ",text" in head \
                   or head.rstrip().endswith("text") or '"insertion"' in head \
                   or head.startswith("{")
        except OSError:
            return False
    lados = [p for p in glob.glob(f"source/{c}/**/*", recursive=True)
             if os.path.isfile(p) and "procedencia" not in p.lower()
             and ".pre_" not in os.path.basename(p).lower()
             and "residuo" not in p.lower()
             and any(k in os.path.basename(p).lower() for k in
                     ("sidecar", "insertion", "insercion", "no_discurso", "nodiscurso",
                      "apartado", "excluido", "documentos", "decretos"))
             and p.rsplit(".", 1)[-1].lower() in ("csv", "jsonl", "json", "tsv")
             and _tiene_text(p)]
    mob = [p for p in lados if "mobiliario" in p.lower()]
    cont = [p for p in lados if p not in mob]
    nf = 0
    for p in cont:
        try:
            with open(p, encoding="utf-8") as fh:
                nl = sum(1 for _ in fh)      # ⚠ no reutilizar `n`: es el total de filas del corpus
            nf += nl if p.endswith(".jsonl") else max(nl - 1, 0)
        except OSError:
            pass
    r["nada apartado a sidecar"] = (not cont,
                                    (f"{nf:,} filas en {len(cont)} sidecar de contenido"
                                     if cont else "nada apartado")
                                    + (f" · además {len(mob)} de mobiliario (fuera de la regla)" if mob else ""))

    # 15 · vinculación bruta y efectiva (tr-0003)
    anon = m.speaker_raw.str.contains(
        r"^\s*(?:EL\s+|LA\s+)?(?:SE(?:Ñ|N)OR[AE]?\s+)?"
        r"(?:PRESIDENT|SECRETARI|VICEPRESIDENT|MODERADOR|RELATOR)", case=False, regex=True)
    nom_nodip = (m.id_dep == "") & (~anon)
    r["_vinc"] = (None, f"bruta {100*len(v)/n:.2f}% · sin vincular con nombre {int(nom_nodip.sum()):,}")
    r["_pais"] = C
    r["_filas"] = f"{n:,}"
    return r


def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument("--country", action="append", default=[])
    a.add_argument("--all", action="store_true")
    a.add_argument("--file", default="", help="corpus alternativo (p. ej. el de un reproceso)")
    o = a.parse_args()
    cs = o.country or ([os.path.basename(os.path.dirname(os.path.dirname(p)))
                        for p in sorted(glob.glob("source/*/standardize/??_interventions.csv"))]
                       if o.all else [])
    if not cs:
        raise SystemExit("✗ usa --country XX o --all")
    with ProcessPoolExecutor(max_workers=min(8, len(cs))) as ex:
        res = list(ex.map(revisar, cs, [o.file] * len(cs)))
    res = [x for x in res if "_error" not in x]
    checks = [k for k in res[0] if not k.startswith("_")]
    anchos = max(len(k) for k in checks)
    print("⚠ Un ✓ significa «este control no detecta nada», no «está bien». Lo que ningún\n"
          "  control mira sigue sin mirarse: apartes, turnos ajenos y cabeceros pasaron años\n"
          "  en verde. La revisión registro a registro no es opcional.\n")
    print(f"{'comprobación':{anchos}} " + " ".join(f"{x['_pais']:>3}" for x in res))
    for k in checks:
        fila = " ".join(("  ·" if x[k][0] is None else ("  ✓" if x[k][0] else "  ✗")) for x in res)
        print(f"{k:{anchos}} {fila}")
    print()
    for x in res:
        fallos = [f"{k}: {x[k][1]}" for k in checks if x[k][0] is False]
        print(f"── {x['_pais']} · {x['_filas']} filas · {x['_vinc'][1]}")
        for f in fallos:
            print(f"     ✗ {f}")
        if not fallos:
            # ⚠ NUNCA «cumple»: esto solo dice que estos 16 controles no ven nada, y un control
            # ciego informa cero. BR salía «cumple todas» mientras escondía 18.930 apartes, y CL
            # mientras arrastraba los cabeceros dentro del texto. La fricción va aquí, en la
            # herramienta, no en cómo lo cuente quien la ejecute.
            print("     · sin fallos DETECTABLES por estos 16 controles"
                  " — no es una verificación del corpus")


if __name__ == "__main__":
    main()
