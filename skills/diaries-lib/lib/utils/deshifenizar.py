#!/usr/bin/env python3
"""Segunda pasada de deshifenización: une las palabras partidas por el salto de línea.

Lo detectó el investigador con el inspector (2026-08-10), en ES:

    …se ha efec-
    tuado la corrección indicada.
    …y se dará por apro-
    bado

`correct_text.py` SÍ une guiones, pero atado al reflujo de párrafos; en los países cuyo reproceso
**preservó la estructura de línea** —ES conserva 476.196 filas con líneas propias— no hay reflujo
y por tanto no hay unión. De ahí que haga falta una pasada aparte, y **después** de quitar
cabeceras y pies: si el mobiliario se cuela entre las dos mitades, ni se ven juntas
([[feedback_mobiliario_br_page]]).

Alcance medido: **5.606.507 cortes** — ES 2.015.272 · AR 1.641.698 · PE 876.251 · UY 802.160 ·
CL 153.888 · PY 92.776 · PT 13.941 · BR 6.973 · el resto, menos de 2.000.

## La decisión no se adivina: la resuelve el propio corpus

El riesgo de unir a ciegas es el COMPUESTO legítimo partido al final de línea: «político-\\nsocial»
no es «políticosocial». Para decidir se construye un léxico con el propio corpus —las palabras y
los compuestos que aparecen EN MEDIO de la línea, donde nadie los partió— y se compara:

    frecuencia("efectuado") = 3.412   ·  frecuencia("efec-tuado") = 0   → se une
    frecuencia("políticosocial") = 0  ·  frecuencia("político-social") = 87 → se mantiene el guion

Sin evidencia en ninguno de los dos sentidos se une, porque un guion a final de línea es
abrumadoramente un artefacto de composición. El léxico es del país y del idioma que toque, así
que la regla vale igual para español y portugués sin listas escritas a mano.

CLI:
    python deshifenizar.py --country es [--medir]          # CSV canónico (campaña)
    python deshifenizar.py --textdir source/es/corrected [--medir]   # reproceso, sobre corrected/
"""
import argparse
import csv
import os
import re
import sys
import unicodedata
from collections import Counter

csv.field_size_limit(sys.maxsize)

LETRA = "A-Za-zÁÉÍÓÚÑÜáéíóúñüÀÂÃÊÔÕÇàâãêôõç"
# palabra partida: letra + guion + fin de línea + minúscula
# ⚠ Puede haber una línea EN BLANCO entre las dos mitades: al quitar el cabecero que se colaba
# en medio queda el hueco. Por eso se admite un salto extra — pero solo uno, para no coser
# nunca dos párrafos distintos.
# ⚠ La continuación puede ir en VERSALES: los títulos y epígrafes del acta se parten igual
# —«OFICIO DE COMISION DE DERE-\nCHOS HUMANOS», «EL PRESI-\nDENTE DE LA REPUBLICA»— y exigir
# minúscula dejaba 129.024 cortes sin unir (ES 64.408 · UY 33.365 · CL 4.406). Se admite la
# continuación en mayúsculas solo si la primera mitad también lo está, para no coser un final
# de frase con el nombre propio que abre la siguiente.
_MIN = "a-záéíóúñüàâãêôõç"
_MAY = "A-ZÁÉÍÓÚÑÜÀÂÃÊÔÕÇ"
# ⚠ El corte admite hasta TRES saltos entre las dos mitades, no uno. Al retirar el mobiliario de
# página queda un hueco donde estaba la cabecera —«eco-\n\n\nnómica»— y con un solo salto se
# perdían 640 uniones en PY. El guardarraíl no es el número de saltos: es el LÉXICO, que decide si
# `mitad1+mitad2` es una palabra del corpus y `mitad2` suelta no lo es.
CORTE = re.compile(rf"([{LETRA}]{{2,}})-[ \t]*\n[ \t]*\n{{0,2}}[ \t]*([{_MIN}][{LETRA}]*)"
                   rf"|([{_MAY}]{{2,}})-\n[ \t]*\n?[ \t]*([{_MAY}][{_MAY}]*)")
# palabras y compuestos tal como aparecen SIN partir, para construir el léxico
# ⚠ {1,}, no {3,}: el listón proporcional necesita la frecuencia de las palabras-función CORTAS
# («ley- de»: con f(«de»)=0 por el {3,}, min(f(a),f(b)) colapsaba a 0 y el listón a 1 — «leyde»
# se unía igual con 9 apariciones basura frente a f(«ley»)=152.906; pasada 24 CL). Las entradas
# de 1-2 letras solo alimentan el listón: un `junto` mide siempre formas de ≥3 caracteres.
PALABRA = re.compile(rf"[{LETRA}]+")
COMPUESTO = re.compile(rf"([{LETRA}]{{2,}})-([{LETRA}]{{2,}})")
# ⚠ Corte con guion+ESPACIO en la MISMA línea: cuando el reflujo ya unió las líneas, el
# «efec-\ntuado» quedó como «efec- tuado» (~209k solo en ES; la campaña del 10-ago no los veía
# porque su patrón exigía el SALTO). A mitad de línea el guion+espacio NO es abrumadoramente un
# artefacto —rangos «Madrid- Barcelona», incisos—, así que esta variante EXIGE evidencia
# positiva del léxico para unir; sin evidencia se CONSERVA tal cual (política más estricta que
# la del salto de línea).
# ⚠ El «guion» puede llegar OCR-eado a interpunct —«refe·· rirse» (CL iter-5)— o con APÓSTROFO
# espurio pegado —«con-' cedida», «Repú- ' blica» (iter-6)—: se admiten ·/·· y el apóstrofo a
# cada lado del espacio; la evidencia del léxico sigue mandando, así que no añaden riesgo.
# ⚠ iter-7: el apóstrofo también aparece ANTES del guion («tra'- mitación») y tras el guion
# puede venir coma o dos puntos OCR-eados («noso-, tros», «destina-: dos»).
CORTE_ESPACIO = re.compile(rf"([{LETRA}]{{2,}})'?(?:-|·{{1,2}})[',:\"]?[ \t]+(?:['\"][ \t]*)?([{_MIN}][{LETRA}]*)")
# Guion de fin de línea degradado por el OCR a PUNTUACIÓN («inter.:.⏎⏎namente» — iter-6): SOLO
# minúsculas, SOLO con evidencia positiva; al unir, el separador basura desaparece con el corte.
# Variante INLINE del separador basura, ya con las líneas unidas («empeña.., dos»,
# «beneficia:' dos» — iter-8): el guion del corte salió OCR-eado como puntuación y el
# reflujo dejó la palabra partida a mitad de línea. SOLO con evidencia; el par de una
# elipsis legítima («espera... nada») no tiene forma unida en el léxico y se conserva.
CORTE_JUNK_ESP = re.compile(rf"([{_MIN}]{{3,}})[.:·,']{{2,3}}[ \t]+([{_MIN}][{LETRA}]*)")
CORTE_JUNK = re.compile(rf"([{_MIN}]{{3,}})[.:·]{{2,3}}[ \t]*\n[ \t]*\n{{0,2}}[ \t]*([{_MIN}][{LETRA}]*)")
# Rama VERSAL del corte con espacio: «MARIO PA- LESTRO ROJAS» (títulos y sumarios en mayúsculas
# tras el reflujo). Igual que la rama minúscula: SOLO une con evidencia positiva del léxico;
# sin ella conserva — el apellido compuesto («PEREZ- GARCIA») nunca se une sin prueba.
CORTE_ESPACIO_VERSAL = re.compile(rf"([{_MAY}]{{2,}})-[ \t]+([{_MAY}][{_MAY}]*)")
# Corte PEGADO sin espacio dentro de la línea («Vicepresi-dente» tras un join que conservó el
# guion): SOLO minúscula-minúscula y SOLO con evidencia del léxico — «político-social» tiene
# evidencia de compuesto y se conserva; los apellidos VERSALES jamás entran (CL iter-4).
CORTE_PEGADO = re.compile(rf"((?:[{_MAY}])?[{_MIN}]{{3,}})-([{_MIN}]{{2,}})")

# ⚠⚠ NUNCA FUSIONAR CONTRA UN IDENTIFICADOR DE ORADOR (investigador, EC 2026-08-25).
# El fallo: el numeral romano de sección acaba en guion —«-II-»— y la rama VERSAL de CORTE lo
# leía como primera mitad de palabra partida («II» + «EL»). Sin evidencia léxica decidía
# CONSERVAR, y la vía de conservación de `une()` emitía «a-» reanudando en la segunda mitad:
# el salto de línea (y la BLANCA) desaparecían y el marcador quedaba pegado al numeral —
# «-II-EL SEÑOR SECRETARIO: Sí, señor Presidente». 889 casos en 359 archivos de EC, todos
# introducidos por esta etapa (en `extracted/` había 0).
# Para el resto de cortes el colapso ES correcto y se mantiene: lo único que se separa es el
# marcador. Un identificador de orador SIEMPRE abre párrafo propio —invariante que impone
# `separa_marcadores` en correct—, así que aquí se restituye el blanco tal como venía y, si
# solo quedaba un salto, se promueve a línea en blanco.
MARCADOR_RES: list = []


def carga_marcadores(config_path):
    """Compila los `speaker_tag_patterns` del país. Sin config, el guardarraíl queda inerte."""
    global MARCADOR_RES
    try:
        import yaml
        cfg = yaml.safe_load(open(config_path, encoding="utf-8")) or {}
    except Exception:
        return 0
    MARCADOR_RES = []
    for p in cfg.get("speaker_tag_patterns") or []:
        try:
            MARCADOR_RES.append(re.compile(p))
        except re.error:
            pass
    return len(MARCADOR_RES)


def _abre_marcador(s, i):
    """¿El texto que empieza en `i` es un identificador de orador? Los patrones del país están
    anclados a inicio de línea, así que se prueban sobre la ventana que arranca en la 2ª mitad."""
    if not MARCADOR_RES:
        return False
    ventana = s[i:i + 300]
    return any(r.match(ventana) for r in MARCADOR_RES)


def _conserva_separado(m, i_b):
    """Conserva el par SIN colapsar: devuelve el texto original hasta la 2ª mitad (con sus
    saltos intactos) y reanuda ahí. Si solo había un salto, se promueve a línea en blanco para
    que el marcador abra párrafo."""
    seg = m.string[m.start():i_b]
    if "\n" in seg and "\n\n" not in seg:
        seg = re.sub(r"[ \t]*\n[ \t]*\Z", "\n\n", seg)
    return seg, i_b


def lexico(textos):
    """Frecuencias de palabra suelta y de compuesto con guion, tomadas de líneas sin partir."""
    pal, comp = Counter(), Counter()
    for t in textos:
        # se quitan los cortes de línea para no contar como palabra las mitades
        limpio = CORTE.sub(lambda m: "-".join(_partes(m)), t)
        for w in PALABRA.findall(limpio):
            pal[w.lower()] += 1
        for a, b in COMPUESTO.findall(limpio):
            comp[(a.lower(), b.lower())] += 1
    return pal, comp


def _partes(m):
    """Las dos mitades, venga por la rama en minúsculas o por la de versales."""
    return (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))


def _fold(w):
    """Pliega los acentos: el OCR de VERSALES los pierde y el lookup exacto no ve la evidencia
    («FOR- TIN» tenía 24 «Fortín» en el corpus y se conservaba — lector adversarial CL iter-5)."""
    return "".join(c for c in unicodedata.normalize("NFD", w) if not unicodedata.combining(c))


def plegado(pal):
    """Léxico plegado por acentos, para el lookup de rescate."""
    f = Counter()
    for w, c in pal.items():
        f[_fold(w)] += c
    return f


def _scan_sub(rx, decide, t):
    """`re.sub` con REANUDACIÓN controlada: al CONSERVAR un par, el escaneo se reanuda en la
    segunda mitad, no después de ella. El sub clásico consumía «alguno- tendría», decidía
    conservar, y saltaba por encima de «tendría- mos» — que sí tenía evidencia (320 archivos):
    todo corte precedido de un inciso quedaba a la SOMBRA (lector adversarial CL iter-5).

    `decide(m)` devuelve `(texto_emitido, posición_de_reanudación_en_el_original)`."""
    out, pos = [], 0
    while True:
        m = rx.search(t, pos)
        if not m:
            break
        rep, resume = decide(m)
        out.append(t[pos:m.start()])
        out.append(rep)
        pos = resume
    out.append(t[pos:])
    return "".join(out)


def _mk_freq(pal, pal_f):
    # ⚠ `plegar` SOLO en contextos VERSALES: el plegado rescata la evidencia que el OCR de
    # mayúsculas pierde («FOR- TIN» ↔ «Fortín»), pero en minúsculas la TILDE distingue palabras
    # y plegarla fabrica evidencia falsa — «acompañé-\nse» se unió como «acompañése» con la
    # evidencia plegada de «Acompáñese» (lector adversarial CL iter-7). Para el LISTÓN sí se
    # pliega siempre: inflar la frecuencia de las mitades solo SUBE el listón (conservador).
    def _freq(w, plegar=True):
        w = w.lower()
        n = pal.get(w, 0)
        if not n and plegar and pal_f:
            n = pal_f.get(_fold(w), 0)
        return n
    return _freq


def _mk_barra(_freq):
    def _barra(a, b, guion):
        # Evidencia PROPORCIONAL: si las dos mitades son a la vez palabras frecuentes del corpus
        # («ley» + «de»), la lectura separada es plausible —guion de INCISO, no de corte— y unas
        # pocas apariciones basura no bastan: 9 tokens OCR «leyde» dieron auto-evidencia y
        # fabricaron «la historia fidedigna de la leyde que» (lector adversarial CL iter-5).
        # El listón sube con la frecuencia de la mitad MENOS frecuente; en el corte genuino
        # («efec-» + «tuado») esa mitad ronda 0 y el listón se queda en 1.
        # ⚠ Con TOPE en 30: sin él, el corte de CLÍTICO quedaba fuera («modificar- se»:
        # f(modificar)≈4.000 → listón 200 > f(modificarse)≈75, y se conservaba partido —
        # lector iter-6). 30 sigue muy por encima de la basura («leyde»: 9).
        return max(1, guion, min(min(_freq(a), _freq(b)) // 20, 30))
    return _barra


def une(t, pal, comp, stats, pal_f=None):
    _freq = _mk_freq(pal, pal_f)
    _barra = _mk_barra(_freq)

    def decide(m):
        a, b = _partes(m)
        g2 = 2 if m.group(1) else 4
        # el marcador de orador nunca se cose a la línea de arriba (ver MARCADOR_RES)
        if _abre_marcador(m.string, m.start(g2)):
            stats["marcador_separado"] += 1
            return _conserva_separado(m, m.start(g2))
        junto = _freq(a + b, plegar=bool(m.group(3)))
        guion = comp.get((a.lower(), b.lower()), 0)
        if junto >= _barra(a, b, guion):
            stats["une"] += 1
            return a + b, m.end()
        if guion:
            stats["compuesto"] += 1
        # Sin evidencia en ninguno de los dos sentidos, el valor por defecto NO es el mismo:
        # en minúsculas un guion a final de línea es casi siempre corte de composición, pero en
        # VERSALES el apellido compuesto es frecuente —«PEREZ-GARCIA»— y unir destruiría el
        # nombre. Ahí se exige evidencia positiva; sin ella se conserva el guion.
        elif m.group(3):
            stats["versal_sin_evidencia"] += 1
        else:
            # Sin evidencia ya NO se une (flip 2026-08-23, lector adversarial CL: «de la
            # ley-\nuna situación» → «leyuna»; el guion a fin de línea también puede ser un
            # INCISO). Se conserva el corte unido con guion — legible y honesto.
            stats["une_sin_evidencia"] += 1
        # conserva «a-b» dejando la 2ª mitad RE-ESCANEABLE (reanuda en su inicio)
        return a + "-", m.start(g2)
    return _scan_sub(CORTE, decide, t)


def une_espacio(t, pal, comp, stats, pal_f=None):
    """Variante guion+espacio: solo une con evidencia positiva (y proporcional) del léxico."""
    _freq = _mk_freq(pal, pal_f)
    _barra = _mk_barra(_freq)

    def d_esp(m):
        a, b = m.group(1), m.group(2)
        junto = _freq(a + b, plegar=False)
        guion = comp.get((a.lower(), b.lower()), 0)
        if junto >= _barra(a, b, guion):
            stats["esp_une"] += 1
            return a + b, m.end()
        if guion:
            # compuesto DECIDIDO por evidencia: se NORMALIZA a «A-B» (cerrar el espacio,
            # conservar el guion) — «MARTÍNEZ- PUJALTE»→«MARTÍNEZ-PUJALTE», «DECRETO- LEY»→
            # «DECRETO-LEY» (petición del investigador, títulos ES 2026-08-24). Sin evidencia
            # se conserva TAL CUAL (doctrina probatoria).
            stats["esp_compuesto"] += 1
            return a + "-" + b, m.end()
        stats["esp_sin_evidencia"] += 1
        return m.string[m.start():m.start(2)], m.start(2)   # conserva TAL CUAL, sin sombra
    t = _scan_sub(CORTE_ESPACIO, d_esp, t)

    def d_v(m):
        a, b = m.group(1), m.group(2)
        # misma doctrina que en `une()`: contra un marcador no se une ni se normaliza el guion
        if _abre_marcador(m.string, m.start(2)):
            stats["marcador_separado"] += 1
            return m.string[m.start():m.start(2)], m.start(2)
        junto = _freq(a + b)
        guion = comp.get((a.lower(), b.lower()), 0)
        if junto >= _barra(a, b, guion):
            stats["esp_une_versal"] += 1
            return a + b, m.end()
        if guion:
            stats["esp_versal_compuesto_norm"] += 1
            return a + "-" + b, m.end()
        stats["esp_versal_conservado"] += 1
        return m.string[m.start():m.start(2)], m.start(2)
    t = _scan_sub(CORTE_ESPACIO_VERSAL, d_v, t)

    def d_p(m):
        a, b = m.group(1), m.group(2)
        junto = _freq(a + b, plegar=False)
        guion = comp.get((a.lower(), b.lower()), 0)
        if junto >= max(_barra(a, b, guion), guion * 3, 1):
            stats["pegado_une"] += 1
            return a + b, m.end()
        stats["pegado_conservado"] += 1
        return m.string[m.start():m.start(2)], m.start(2)
    t = _scan_sub(CORTE_PEGADO, d_p, t)

    def d_j(m):
        a, b = m.group(1), m.group(2)
        junto = _freq(a + b, plegar=False)
        guion = comp.get((a.lower(), b.lower()), 0)
        if junto >= _barra(a, b, guion):
            stats["junk_une"] += 1
            return a + b, m.end()      # el separador basura se va CON el corte
        stats["junk_conservado"] += 1
        return m.string[m.start():m.start(2)], m.start(2)
    t = _scan_sub(CORTE_JUNK, d_j, t)
    return _scan_sub(CORTE_JUNK_ESP, d_j, t)


def _main_textdir(a):
    """Modo reproceso: opera sobre un directorio de .txt (p.ej. source/{iso}/corrected/).
    Léxico sobre TODOS los archivos del directorio; unión in-place hasta PUNTO FIJO.

    ⚠ El léxico se ARRANCA a sí mismo: la evidencia pre-unión de una forma puede quedar justo
    bajo el listón («intentaban»: 7 pre-unión < listón 8) y las uniones de la propia pasada la
    suben por encima — una sola pasada no alcanza el punto fijo (lector adversarial CL iter-7).
    Se itera (máx 4 rondas) reconstruyendo el léxico hasta que una ronda no toque nada."""
    from pathlib import Path
    d = Path(a.textdir)
    files = sorted(d.glob("*.txt"))
    if not files:
        sys.exit(f"sin .txt en {d}")
    # el guardarraíl del marcador necesita los patrones del país: se toma `--config` o, si no se
    # da, se DERIVA de la ruta (source/{iso}/corrected → country_config/{iso}.yaml) para que no
    # dependa de acordarse del flag
    cfg_path = a.config
    if not cfg_path:
        partes = [x for x in d.resolve().parts]
        if "source" in partes:
            iso = partes[partes.index("source") + 1]
            cand = Path.cwd() / "country_config" / f"{iso}.yaml"
            cfg_path = str(cand) if cand.exists() else None
    n_marc = carga_marcadores(cfg_path) if cfg_path else 0
    print(f"  guardarraíl de marcador: {n_marc} patrones"
          f"{' — ' + str(cfg_path) if n_marc else ' (INERTE: sin config)'}")
    for ronda in range(1, 5):
        pal, comp = lexico(f.read_text(encoding="utf-8") for f in files)
        pal_f = plegado(pal)
        stats, tocados = Counter(), 0
        for f in files:
            t = f.read_text(encoding="utf-8")
            nt = une(t, pal, comp, stats, pal_f)
            nt = une_espacio(nt, pal, comp, stats, pal_f)
            if nt != t:
                tocados += 1
                if not a.medir:
                    f.write_text(nt, encoding="utf-8")
        print(f"  {d} · ronda {ronda} · {len(files):,} archivos · {tocados:,} con uniones"
              f"{' (SIMULACIÓN, nada escrito)' if a.medir else ''}")
        print(f"     salto: unidos {stats['une']:,} · sin evidencia {stats['une_sin_evidencia']:,}"
              f" · compuesto conservado {stats['compuesto']:,} · versal conservado {stats['versal_sin_evidencia']:,}")
        print(f"     espacio: unidos {stats['esp_une']:,} (+{stats['esp_une_versal']:,} versal) · compuesto conservado {stats['esp_compuesto']:,}"
              f" · sin evidencia CONSERVADO {stats['esp_sin_evidencia'] + stats['esp_versal_conservado']:,}")
        print(f"     junk-separador: unidos {stats['junk_une']:,} · conservados {stats['junk_conservado']:,}"
              f" · pegado: unidos {stats['pegado_une']:,}")
        print(f"     MARCADOR separado (no se cose a la línea de arriba): {stats['marcador_separado']:,}")
        if a.medir or tocados == 0:
            break


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--country")
    ap.add_argument("--textdir", help="directorio de .txt (p.ej. source/{iso}/corrected): "
                                      "léxico sobre todos, unión in-place. Modo del reproceso.")
    ap.add_argument("--medir", action="store_true")
    ap.add_argument("--config", help="country_config/{iso}.yaml — de ahí salen los "
                                     "speaker_tag_patterns del guardarraíl de marcador. "
                                     "Si no se da, se deriva de --textdir.")
    a = ap.parse_args()
    if bool(a.country) == bool(a.textdir):
        ap.error("exactamente uno de --country (CSV canónico) o --textdir (reproceso)")
    if a.textdir:
        _main_textdir(a)
        return
    iso, I = a.country.lower(), a.country.upper()
    carga_marcadores(a.config or f"country_config/{iso}.yaml")
    p = f"source/{iso}/standardize/{I}_interventions.csv"
    with open(p, encoding="utf-8") as fh:
        d = csv.Sniffer().sniff(fh.readline(), ";,").delimiter
        fh.seek(0)
        r = csv.DictReader(fh, delimiter=d)
        campos, filas = list(r.fieldnames), list(r)

    pal, comp = lexico(x["text"] for x in filas)
    pal_f = plegado(pal)
    stats = Counter()
    antes = sum(len(x["text"]) for x in filas)
    muestras = []
    for x in filas:
        t = x["text"]
        if "-\n" not in t and not CORTE_ESPACIO.search(t):
            continue
        nt = une_espacio(une(t, pal, comp, stats, pal_f), pal, comp, stats, pal_f)
        if len(muestras) < 6 and nt != t:
            m = CORTE.search(t)
            if m:
                muestras.append(("-".join(_partes(m)),
                                 une(m.group(0), pal, comp, Counter())))
        if not a.medir:
            x["text"] = nt
    _c = Counter()
    despues = sum(len(une_espacio(une(x["text"], pal, comp, _c, pal_f), pal, comp, _c, pal_f)
                      if a.medir else x["text"]) for x in filas)
    tot = sum(stats.values())
    print(f"  {I} · léxico: {len(pal):,} palabras · {len(comp):,} compuestos con guion")
    print(f"     cortes tratados {tot:,} → unidos {stats['une']:,}"
          f" · unidos sin evidencia {stats['une_sin_evidencia']:,}"
          f" · guion CONSERVADO por ser compuesto {stats['compuesto']:,}"
          f" · versal sin evidencia (guion conservado) {stats['versal_sin_evidencia']:,}")
    print(f"     espacio: unidos {stats['esp_une']:,} (+{stats['esp_une_versal']:,} versal) · compuesto conservado {stats['esp_compuesto']:,}"
          f" · sin evidencia CONSERVADO {stats['esp_sin_evidencia'] + stats['esp_versal_conservado']:,}")
    print(f"     texto {antes:,} → {despues:,} caracteres")
    if muestras:
        print("     muestras:")
        for a1, b1 in muestras:
            print(f"       {a1!r} → {b1!r}")
    if a.medir:
        return
    bak = p.replace(".csv", ".pre_guion.csv")
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
