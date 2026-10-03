#!/usr/bin/env python3
"""Quita el mobiliario de página (folios, cabeceros, pies) que quedó DENTRO de la matriz.

`strip_headers.py` resuelve esto hacia adelante, en `diaries-extract`, donde la frontera de
página está intacta. Pero los corpus cerrados antes de aquel arreglo la perdieron: el folio y
el cabecero quedaron incrustados a mitad de intervención, donde la página cortó el discurso.
Esta utilidad actúa sobre la matriz ya estandarizada.

    page_furniture:
      line_patterns:                   # LÍNEA ENTERA, ya normalizada (mayúsculas, sin tildes,
        - '[IVX]+ SERIE\\s*[-—]?\\s*NUMERO \\d+'   #  dígitos literales). Nunca subcadena.
        - 'CAMARA DE REPRESENTANTES'
      folio: true                      # línea de solo dígitos (por defecto true)
      protect:                         # una línea que case NUNCA se quita
        - '.*,$'

⚠⚠ **La eliminación es por LÍNEA ENTERA ANCLADA, jamás por subcadena.** Es el defecto que este
diseño existe para evitar, y está medido: un detector por tokens institucionales marca
`LA CAMARA DE REPRESENTANTES,` (13.813 líneas de UY, que es prosa: «la Cámara de
Representantes, reunida en sesión…»), `EL SENADO Y CAMARA DE DIPUTADOS, ETC.` (fórmula de
promulgación de AR), `SECRETARIOS DE LA CAMARA DE DIPUTADOS.— PRESENTES.` (encabezamiento de
una carta, MX) y `LA ASAMBLEA LEGISLATIVA DE LA REPUBLICA DE EL SALVADOR, CONSIDERANDO:`
(cuerpo de un decreto). Todas son texto legítimo y todas contienen el nombre de la cámara.

⚠ **Un folio no es «una línea de dígitos»: es una línea de dígitos RODEADA DE PROSA.** Las
tablas de votación son columnas de números y una a una parecen folios. Si la línea anterior o
la siguiente también es solo dígitos, no se toca.

⚠ **Los corpus aplanados no se pueden limpiar así y hay que decirlo, no devolver cero.** CL,
ES y GT no tienen ni un salto de línea en el `text`: sin línea no hay anclaje, y quitar el
mobiliario ahí exigiría casar por subcadena, que es justo lo prohibido. La utilidad se detiene
y lo informa en vez de dar un 0,00% tranquilizador.

⚠ **Nada se borra: se mueve.** Las líneas retiradas van a `{ISO2}_sidecar_mobiliario.csv` con
su fila de origen, reasociables por `date` + `session_number` + `intervention_order`.

Uso:
    python3 strip_matrix_furniture.py --country uy --discover   # propone candidatos
    python3 strip_matrix_furniture.py --country uy --sample 25  # OBLIGATORIO antes de aplicar
    python3 strip_matrix_furniture.py --country uy              # simulación con recuento
    python3 strip_matrix_furniture.py --country uy --apply
"""
from __future__ import annotations

import argparse
import random
import re
import shutil
import unicodedata
from collections import Counter
from pathlib import Path

import pandas as pd

try:
    import yaml
except ImportError:                                    # pragma: no cover
    yaml = None

SOLO_DIGITOS = re.compile(r"^[\s\-–—.\[\(]*(\d{1,4})[\s\-–—.\]\)]*$")
# Un número que CIERRA con punto es el final de una frase, no un folio. Medido en UY sobre
# las 74.854 líneas de solo dígitos: «…de 14 de enero de / 1994.», «…en el año / 1952.»,
# «…después del artículo / 432.». El folio nunca lleva punto final.
CIERRA_FRASE = re.compile(r"\d\s*\.\s*$")
# ⚠ Explícito a propósito. La primera versión derivaba el número del mes de la posición en
# una lista con los doce nombres en español seguidos de los doce en portugués, y la fórmula
# de plegado devolvía agosto para JULHO y enero para SETIEMBRE. No dio error: dio fechas
# plausibles y lejanas, la guarda de proximidad las rechazó, y el resultado fue extraer 35
# líneas en vez de 41.255. Un mapa de doce entradas no necesita aritmética.
MESES = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6, "JULIO": 7,
    "AGOSTO": 8, "SEPTIEMBRE": 9, "SETIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
    "JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "MAIO": 5, "JUNHO": 6, "JULHO": 7,
    "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12,
}
SOLO_FECHA = re.compile(r"^(\d{1,2})\s+DE\s+([A-Z]{3,10})\s+DE\s+(\d{4})$")


def fecha_de_linea(canonica: str):
    """→ (día, mes, año) si la línea es SOLO una fecha; None en otro caso."""
    m = SOLO_FECHA.match(canonica)
    if not m:
        return None
    mes = MESES.get(m.group(2))
    return (int(m.group(1)), mes, int(m.group(3))) if mes else None
# Señales de que una línea es PROSA aunque case un patrón de mobiliario: un mueble no lleva
# verbo conjugado ni termina en coma, y no continúa la frase anterior.
PROSA = re.compile(r",\s*$|\b(?:se|que|de la que|reunid[ao]|considerando|resuelve|"
                   r"acuerda|declara|manifiesta)\b", re.I)


def canon(s: str) -> str:
    """Mayúsculas sin tildes y con espacios normalizados. Los dígitos se conservan."""
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").upper()
    return re.sub(r"\s+", " ", s).strip()


def cargar_config(iso2: str) -> dict:
    p = Path(f"country_config/{iso2}.yaml")
    if not p.exists() or yaml is None:
        return {}
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("page_furniture") or {}


def compilar(cfg: dict):
    pats = cfg.get("line_patterns") or []
    quita = re.compile("|".join(f"(?:{p})" for p in pats)) if pats else None
    prot = re.compile("|".join(f"(?:{p})" for p in cfg["protect"])) if cfg.get("protect") else None
    pre = cfg.get("line_prefixes") or []
    prefijo = re.compile("^(?:" + "|".join(f"(?:{p})" for p in pre) + ")") if pre else None
    return quita, prot, bool(cfg.get("folio", True)), prefijo


def quitar_prefijo(linea: str, prefijo) -> tuple[str, str]:
    """→ (mobiliario, resto). El cabecero puede llevar PEGADA la palabra que la página cortó.

    ⚠ En UY la línea de fecha del cabecero arrastra la cola de la palabra partida:
    «Miércoles 7 de noviembre de 2007 **clusive**, con sus propios…» —de «in-clusive»—.
    Borrar la línea entera se lleva por delante texto real, así que aquí se recorta solo el
    prefijo y el resto se queda unido a lo que sigue.
    """
    if not prefijo:
        return "", linea
    m = prefijo.match(linea.strip())
    if not m:
        return "", linea
    return m.group(0), linea.strip()[m.end():].lstrip()


def es_folio(lns: list[str], es_num: list[bool], i: int) -> bool:
    """¿La línea `i`, que es solo dígitos, es un folio y no texto?

    Tres guardas, cada una de un falso positivo medido en UY sobre 74.854 líneas de dígitos:

    · **cierra frase** — «…de 14 de enero de / 1994.» es un año partido por el salto, no un
      folio. 8,9% de las líneas de dígitos van tras prosa que continúa.
    · **año** — cuatro cifras entre 1800 y 2100. Se pierde algún folio real de ese rango, y
      es el error que hay que preferir: dejar mobiliario es ruido, borrar texto es pérdida.
    · **tabla o lista** — una columna de votación y una lista numerada son sucesiones de
      números, y cada uno por separado parece un folio. ⚠ Los vecinos se buscan **saltando
      las líneas en blanco**: mirar solo la línea pegada dejaba pasar «702 ⏎⏎ 703 ⏎⏎ 704»,
      que es una secuencia, no tres folios. Medido: 5.761 casos en UY (7,7% de sus líneas de
      dígitos) y 929 en PT, de los que la versión anterior solo veía los contiguos.
    """
    s = lns[i].strip()
    if CIERRA_FRASE.search(s):
        return False
    m = SOLO_DIGITOS.match(s)
    if m and 1800 <= int(m.group(1)) <= 2100 and len(m.group(1)) == 4:
        return False
    for paso in (-1, 1):                      # vecino no vacío más cercano en cada sentido
        j = i + paso
        while 0 <= j < len(lns) and not lns[j].strip():
            j += paso
        if 0 <= j < len(lns) and es_num[j]:
            return False
    return True


def linea_de_fecha_de_cabecera(canonica: str, fecha_sesion: str, dias: int) -> bool:
    """¿Es la línea de fecha del cabecero corrido, y no una fecha citada en el discurso?

    ⚠ **La cabecera lleva la fecha de PUBLICACIÓN, a un día de la sesión.** En PT hay 41.255
    líneas que son solo una fecha, y el contexto las delata: «…con ingenuidad o ci-⏎28 DE
    JULHO DE 1976⏎nismo, se asseverou». Pero el discurso cita fechas continuamente —una ley
    de 1998 mencionada en 2010—, así que la forma sola no basta: se exige que la fecha caiga
    **a pocos días de la sesión**. Una fecha lejana es una cita y se queda.
    """
    f = fecha_de_linea(canonica)
    if not f or not fecha_sesion:
        return False
    try:
        from datetime import date
        d1 = date(f[2], f[1], f[0])
        y, m, dd = (int(x) for x in fecha_sesion.split("-"))
        return abs((d1 - date(y, m, dd)).days) <= dias
    except (ValueError, TypeError):
        return False


def marcar(texto: str, quita, prot, folio: bool, prefijo=None,
           bloque: bool = True, fecha_sesion: str = "", dias_fecha: int = 0) -> tuple[list[int], dict]:
    """→ (líneas que son mobiliario entero, {línea: (prefijo_quitado, resto)}).

    ⚠ **El mobiliario viene en BLOQUE, y exigirlo es lo que separa el mueble de la prosa.**
    En UY la cabecera son tres líneas seguidas —folio, «CÁMARA DE REPRESENTANTES», fecha—.
    Aislada, esa misma línea es el encabezamiento de una carta reproducida en el acta:
    «Señor Presidente de la / Cámara de Representantes / Dr. Jorge Orrico». La forma es
    idéntica; lo único que las distingue es la compañía. Con `require_block: false` se acepta
    la línea suelta, y hay que justificar por qué.
    """
    lns = texto.split("\n")
    cn = [canon(x) for x in lns]
    es_num = [bool(x.strip()) and bool(SOLO_DIGITOS.match(x.strip())) for x in lns]
    fuera, recortes = [], {}

    # 1ª pasada · lo inequívoco por su forma: folios y cabeceros con texto pegado
    ancla = set()
    for i, bruto in enumerate(lns):
        if not cn[i]:
            continue
        if prot and prot.fullmatch(cn[i]):
            continue
        if es_num[i]:
            if folio and es_folio(lns, es_num, i):
                fuera.append(i)
                ancla.add(i)
            continue
        if dias_fecha and linea_de_fecha_de_cabecera(cn[i], fecha_sesion, dias_fecha):
            fuera.append(i)
            ancla.add(i)
            continue
        if prefijo:
            mob, resto = quitar_prefijo(bruto, prefijo)
            if mob:
                ancla.add(i)
                (fuera.append(i) if not resto else recortes.__setitem__(i, (mob, resto)))

    # 2ª pasada · los patrones de línea, que solo valen acompañados
    for i, bruto in enumerate(lns):
        if not cn[i] or i in ancla or (prot and prot.fullmatch(cn[i])):
            continue
        if not (quita and quita.fullmatch(cn[i])) or PROSA.search(bruto):
            continue
        if bloque:
            vecino = any(j in ancla for j in (i - 1, i + 1))
            # el bloque puede venir partido por una línea vacía
            if not vecino and i > 1 and not cn[i - 1]:
                vecino = (i - 2) in ancla
            if not vecino and i + 2 < len(lns) and not cn[i + 1]:
                vecino = (i + 2) in ancla
            if not vecino:
                continue
        fuera.append(i)
    return sorted(fuera), recortes


def descubrir(d: pd.DataFrame, n: int = 30) -> None:
    """Propone candidatos a mobiliario, ordenados por recurrencia ENTRE SESIONES."""
    por_forma: dict[str, set] = {}
    cuenta: Counter = Counter()
    ses = d["session_number"] if "session_number" in d.columns else d["date"]
    for s, x in zip(zip(d.date, ses), d.text):
        for ln in str(x).split("\n"):
            t = ln.strip()
            if not t or len(t) > 80 or SOLO_DIGITOS.match(t):
                continue
            k = re.sub(r"\d+", r"\\d+", canon(t))
            if len(k.split()) > 10:
                continue
            cuenta[k] += 1
            por_forma.setdefault(k, set()).add(s)
    print(f"  candidatos: forma · sesiones en que aparece · veces\n")
    filas = sorted(por_forma.items(), key=lambda kv: -len(kv[1]))[:n]
    for k, ss in filas:
        print(f"  {len(ss):>6,} ses · {cuenta[k]:>8,} × │ {k[:88]}")
    # ⚠ El ranking por recurrencia NO encuentra la cabecera cuando el país solo tiene folio
    # y una institución partida en varias líneas: en PA y AR sus 22.871 y 18.677 folios no
    # salen (se excluyen por ser dígitos) y lo que asoma arriba son fórmulas de sala. El
    # folio es el ANCLA: lo que se repite a su lado es el resto del cabecero.
    vec: Counter = Counter()
    for x in d.text:
        x = str(x)
        if "\n" not in x:
            continue
        ln = x.split("\n")
        for i, y in enumerate(ln):
            if not y.strip() or not SOLO_DIGITOS.match(y.strip()):
                continue
            for j in (i - 1, i + 1):
                if 0 <= j < len(ln) and ln[j].strip() and not SOLO_DIGITOS.match(ln[j].strip()):
                    k = re.sub(r"\d+", r"\\d+", canon(ln[j])[:70])
                    if len(k.split()) <= 12:
                        vec[k] += 1
    if vec:
        print("\n  VECINOS DEL FOLIO · lo que acompaña a una línea de solo dígitos:\n")
        for k, n in vec.most_common(14):
            print(f"  {n:>8,} × │ {k[:88]}")

    print("\n⚠ La recurrencia NO basta: «MUCHAS GRACIAS» aparece en casi todas las sesiones y es"
          "\n  habla. Copia al config solo las formas que sean mobiliario POR SU FORMA, y como"
          "\n  patrón de LÍNEA ENTERA.")


def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument("--country", required=True)
    a.add_argument("--apply", action="store_true")
    a.add_argument("--discover", action="store_true")
    a.add_argument("--sample", type=int, default=0)
    a.add_argument("--append", action="store_true",
                   help="segunda pasada: AÑADE al sidecar existente en vez de rechazarlo")
    a.add_argument("--seed", type=int, default=20260802)
    # Un REPROCESO trabaja sobre `matrix/interventions_raw.csv`, no sobre la salida canónica:
    # esa aún no existe, y sobreescribirla antes de validar sería irreversible. Sin el flag
    # se mantiene el comportamiento de siempre (el corpus publicado).
    a.add_argument("--matrix", default=None,
                   help="matriz de entrada; por defecto standardize/{ISO2}_interventions.csv")
    a.add_argument("--sidecar", default=None,
                   help="destino del sidecar; por defecto junto a la matriz de entrada")
    o = a.parse_args()
    c = o.country.lower()

    csv = Path(o.matrix) if o.matrix else Path(
        f"source/{c}/standardize/{c.upper()}_interventions.csv")
    sep = ";" if csv.read_text(encoding="utf-8", errors="replace")[:2000].count(";") > \
        csv.read_text(encoding="utf-8", errors="replace")[:2000].count(",") else ","
    d = pd.read_csv(csv, sep=sep, dtype=str, keep_default_na=False)
    con_salto = int(d.text.str.contains("\n").sum())
    if not con_salto:
        raise SystemExit(
            f"✗ {c.upper()}: el `text` no tiene ni un salto de línea — corpus aplanado.\n"
            f"  Sin línea no hay anclaje, y quitar el mobiliario aquí exigiría casar por\n"
            f"  subcadena, que es justo lo que este diseño prohíbe. Hay que reprocesar desde\n"
            f"  `corrected/` con strip_headers.py, no parchear la matriz.")

    if o.discover:
        print(f"{c.upper()} · {len(d):,} filas · {con_salto:,} con saltos de línea")
        return descubrir(d)

    cfg = cargar_config(c)
    if not cfg:
        raise SystemExit(f"✗ {c}: falta el bloque `page_furniture:` en country_config/{c}.yaml\n"
                         f"  Empieza por: strip_matrix_furniture.py --country {c} --discover")
    quita, prot, folio, prefijo = compilar(cfg)
    # ⚠⚠ Sin cabecera que lo ancle, un número suelto NO es identificable como folio. Medido
    # en AR y PA: sin `line_patterns`, lo que se retiraba eran los NÚMEROS DE LOS PUNTOS DEL
    # ORDEN DEL DÍA, con el título en la línea siguiente —«14» + «CÓDIGO PENAL — MODIFICACIÓN
    # (Orden del Día N.º 1126)», «7» + «PEDIDOS DE INFORMES»—, y en PA referencias partidas
    # («231-» + «A, 231-B, 231-C»). En UY y PT los folios sí son folios porque van pegados a
    # «CÁMARA DE REPRESENTANTES» y a «I SÉRIE — NÚMERO 72», que los identifican.
    if folio and not cfg.get("line_patterns") and not cfg.get("require_block", True):
        raise SystemExit(
            f"✗ {c.upper()}: `folio: true` sin `line_patterns` y con `require_block: false`.\n"
            f"  Un número suelto, sin una cabecera al lado que lo identifique, no se puede\n"
            f"  distinguir del número de un punto del orden del día. Declara la cabecera de\n"
            f"  este país, o deja `require_block: true`, o no quites folios aquí.")
    bloque = bool(cfg.get('require_block', True))
    dias_fecha = int(cfg.get("date_line_near_session", 0))

    marcas, cortes, n_fol, n_pat = {}, {}, 0, 0
    for i, t in zip(d.index, d.text):
        t = str(t)
        if "\n" not in t:
            continue
        ix, rec = marcar(t, quita, prot, folio, prefijo, bloque,
                         str(d.at[i, "date"]), dias_fecha)
        if rec:
            cortes[i] = rec
        if ix:
            marcas[i] = ix
            lns = t.split("\n")
            for j in ix:
                if SOLO_DIGITOS.match(lns[j].strip()):
                    n_fol += 1
                else:
                    n_pat += 1

    tot_lin = sum(1 for t in d.text for ln in str(t).split("\n") if ln.strip())
    n = n_fol + n_pat
    print(f"{c.upper()} · {len(d):,} filas · {tot_lin:,} líneas no vacías")
    print(f"  líneas de mobiliario   : {n:,} ({100*n/tot_lin:.2f}%)  "
          f"folios {n_fol:,} · cabeceros {n_pat:,}")
    n_rec = sum(len(v) for v in cortes.values())
    print(f"  cabeceros RECORTADOS   : {n_rec:,}  (llevaban texto pegado detrás)")
    print(f"  filas afectadas        : {len(set(marcas) | set(cortes)):,}")
    vacias = sum(1 for i, ix in marcas.items()
                 if len([x for x in str(d.at[i, 'text']).split('\n') if x.strip()]) == len(ix))
    print(f"  filas que quedarían VACÍAS: {vacias:,}  ← si no es ~0, el patrón caza prosa")

    if o.sample:
        random.seed(o.seed)
        ks = random.sample(sorted(set(marcas) | set(cortes)),
                           min(o.sample, len(set(marcas) | set(cortes))))
        print(f"\n─── MUESTRA ALEATORIA de {len(ks)} · confírmala ANTES de --apply ───")
        for k in ks:
            lns = str(d.at[k, "text"]).split("\n")
            for j, (mob, resto) in list(cortes.get(k, {}).items())[:2]:
                print(f"\n  [{d.at[k,'date']} · {str(d.at[k,'speaker_raw'])[:26]}] RECORTE")
                print(f"  ✂  {mob[:70]!r}")
                print(f"  ✓  se queda: {resto[:70]!r}")
            for j in marcas.get(k, [])[:2]:
                ant = lns[j - 1].strip()[-58:] if j else "(inicio)"
                sig = lns[j + 1].strip()[:58] if j + 1 < len(lns) else "(fin)"
                print(f"\n  [{d.at[k,'date']} · {str(d.at[k,'speaker_raw'])[:26]}]")
                print(f"     …{ant}")
                print(f"  ✂  {lns[j].strip()[:76]!r}")
                print(f"      {sig}…")
        return

    if not o.apply:
        print("\n--- SIMULACIÓN --- (ejecuta antes --sample y confírmalo)")
        return

    side, nuevo = [], []
    for i, r in d.iterrows():
        t = str(r.text)
        if i not in marcas and i not in cortes:
            nuevo.append(t)
            continue
        lns = t.split("\n")
        for j, (mob, resto) in cortes.get(i, {}).items():
            s = dict(r); s["text"] = mob; s["linea"] = j; s["tipo"] = "recorte"
            side.append(s)
            lns[j] = resto                     # el texto pegado detrás SE CONSERVA
        for j in marcas.get(i, []):
            s = dict(r); s["text"] = lns[j].strip(); s["linea"] = j; s["tipo"] = "linea"
            side.append(s)
        quitar = set(marcas.get(i, []))
        nuevo.append("\n".join(x for j, x in enumerate(lns) if j not in quitar).strip())

    # ⚠ La calibración es iterativa: la primera pasada deja siempre variantes que solo se ven
    # mirando el residuo (en PT, 1.977 filas con el número en romanos, con el folio pegado
    # detrás o con «40n» pegado delante por el OCR). El sidecar NUNCA se sobrescribe: o no
    # existe, o se añade a él con --append, de modo que la reversibilidad se conserva entera.
    sp = Path(o.sidecar) if o.sidecar else (
        csv.with_name(csv.stem + "_sidecar_mobiliario.csv") if o.matrix else
        Path(f"source/{c}/standardize/{c.upper()}_sidecar_mobiliario.csv"))
    if sp.exists() and not o.append:
        raise SystemExit(f"✗ {sp.name} ya existe. Si es una segunda pasada de calibración, "
                         f"usa --append; nunca se sobrescribe.")
    bak = csv.with_name(csv.stem + ".pre_mobiliario.csv")
    if not bak.exists():   # la copia es la del estado ORIGINAL, no la de cada pasada
        shutil.copy2(csv, bak)
        print(f"  copia de seguridad → {bak.name}")
    nuevo_side = pd.DataFrame(side)
    if sp.exists():
        previo = pd.read_csv(sp, dtype=str, keep_default_na=False)
        nuevo_side = pd.concat([previo, nuevo_side], ignore_index=True)
        print(f"  sidecar ampliado: {len(previo):,} + {len(side):,} = {len(nuevo_side):,}")
    nuevo_side.to_csv(sp, index=False, encoding="utf-8")
    d["text"] = nuevo
    d.to_csv(csv, index=False, encoding="utf-8")
    print(f"✓ {n:,} líneas + {n_rec:,} recortes retirados · sidecar {sp.name} · "
          f"texto {d.text.str.len().sum()/1e6:.1f} M car.")


if __name__ == "__main__":
    main()
