#!/usr/bin/env python3
"""Contrasta la fecha y el número de sesión de la matriz con la CABECERA DEL PROPIO ACTA.

La fecha y el número de una sesión son metadatos que el pipeline **derivó**; el acta los
**declara**. Cuando discrepan, manda el acta: es la fuente primaria y lo demás es
construcción nuestra (`feedback_primacia_del_diario`).

Cuatro veredictos por sesión:

    OK              la cabecera confirma lo registrado
    FECHA_DISTINTA  el acta dice otra fecha Y esa fecha encaja con las sesiones vecinas
                    → el metadato es el sospechoso
    OCR_CABECERA    el acta dice otra fecha pero esa fecha NO encaja en el calendario del
                    corpus → la corrupta es la cabecera, no el metadato
    CONFLADA        varias cabeceras distintas bajo una misma fecha registrada: son DOS
                    sesiones fundidas en una (el caso de las 14 sesiones dobladas de CL)
    SIN_CABECERA    no validable — se informa, no se da por buena

⚠⚠ **Cuando discrepan NO siempre manda el acta, y decidirlo por principio se equivoca.**
Si la cabecera viene de OCR, la discrepancia suele ser suya. Se decide por CRONOLOGÍA:
la fecha declarada se contrasta con las sesiones vecinas del propio corpus. Medido en UY,
de 22 discrepancias **20 eran años enteros de diferencia** —−20, +1, +10, −2, +4, −70 años:
un dígito del año mal leído— y las sesiones vecinas confirmaban la fecha registrada. Solo 2
eran plausibles y por tanto imputables al metadato.

⚠ **La cabecera se busca ANCLADA y CON MAYÚSCULAS, sin `re.I`.** Es lo que la distingue de las
referencias del índice, que van en Title Case: en SV, «Sesión … Número 1, de fecha 24 de mayo»
es una remisión a otra acta, y la cabecera autorizada es «LA SESIÓN PLENARIA ORDINARIA No. 1 DE
FECHA 24 DE MAYO DE 2018». Casar sin distinguir mayúsculas convierte cada índice en una
discrepancia falsa.

⚠ **Solo las primeras intervenciones de la sesión.** El cuerpo del debate cita fechas de otras
sesiones continuamente; la cabecera está al principio. `scan_rows` acota, y la utilidad informa
cuántas coincidencias aparecieron fuera de ese margen para que se vea si el margen se queda corto.

⚠ **No corrige nada.** Escribe el informe y para. Una fecha mal derivada puede estar
propagada a `session_id`, a los intermedios y al padrón: la corrección es un reproceso, no un
`UPDATE` sobre la matriz.

Configuración (opcional; por defecto reutiliza lo que ya declara el país):

    audit:
      session_header:
        pattern: 'SESI[OÓ]N .{0,40}?(?:N[ÚU]MERO|No\\.)\\s*(\\d+).{0,20}?(\\d{1,2}) DE ([A-ZÁÉÍÓÚ]{4,}) DE (\\d{4})'
        number_group: 1
        day_group: 2
        month_group: 3
        year_group: 4
        case_sensitive: true      # por defecto true, y hay que justificar ponerlo en false
        scan_rows: 6

Uso:
    python3 audit_session_dates.py --country sv
    python3 audit_session_dates.py --country sv --report docs/sv/fechas.csv
"""
from __future__ import annotations

import argparse
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import pandas as pd

try:
    import yaml
except ImportError:                                    # pragma: no cover
    yaml = None

MESES = {"ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
         "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "SETIEMBRE": 9, "OCTUBRE": 10,
         "NOVIEMBRE": 11, "DICIEMBRE": 12,
         # portugués
         "JANEIRO": 1, "FEVEREIRO": 2, "MARCO": 3, "MAIO": 5, "JUNHO": 6, "JULHO": 7,
         "AGOSTO": 8, "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12}
FECHA_SUELTA = re.compile(r"(\d{1,2})\s*[º°ªo.]*\s+DE\s+([A-ZÁÉÍÓÚÇ]{4,})\s+DE\s+(\d{4})")


def sin_tildes(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def a_iso(dia, mes, anio) -> str | None:
    m = MESES.get(sin_tildes(str(mes)).upper())
    if not m:
        return None
    try:
        return f"{int(anio):04d}-{m:02d}-{int(dia):02d}"
    except (TypeError, ValueError):
        return None


def cargar(iso2: str) -> dict:
    p = Path(f"country_config/{iso2}.yaml")
    d = (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.exists() and yaml else {}
    cfg = ((d.get("audit") or {}).get("session_header")) or {}
    if not cfg.get("pattern"):
        # se reutiliza lo que el país ya declara para diaries-meta
        cfg = dict(cfg)
        cfg["pattern"] = d.get("session_date_regex")
        cfg["_heredado"] = True
    return cfg


def buscar(texto: str, pat: re.Pattern, cfg: dict):
    """→ (fecha_iso, numero) declarados por la cabecera, o (None, None)."""
    m = pat.search(texto)
    if not m:
        return None, None
    g = m.groups()
    num = None
    if cfg.get("number_group"):
        num = m.group(int(cfg["number_group"]))
    if cfg.get("day_group"):
        f = a_iso(m.group(int(cfg["day_group"])), m.group(int(cfg["month_group"])),
                  m.group(int(cfg["year_group"])))
        return f, num
    # patrón heredado: un solo grupo con la fecha en prosa
    bruto = next((x for x in g if x), "")
    mm = FECHA_SUELTA.search(sin_tildes(bruto).upper())
    return (a_iso(*mm.groups()) if mm else None), num


def por_documento(iso2: str, carpeta: str, pat, cfg, head: int = 20000) -> dict:
    """Busca la cabecera en los INTERMEDIOS. → {session_id: (fecha, numero)}"""
    import glob
    out = {}
    for fp in sorted(glob.glob(f"source/{iso2}/{carpeta}/**/*.txt", recursive=True)):
        t = open(fp, encoding="utf-8", errors="replace").read(head)
        t = re.sub(r"<[^>]+>", " ", t)
        fe, nu = buscar(t, pat, cfg)
        if fe:
            out[Path(fp).stem] = (fe, nu)
    return out


def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument("--country", required=True)
    a.add_argument("--report", default="")
    a.add_argument("--scan-rows", type=int, default=0)
    o = a.parse_args()
    c = o.country.lower()

    cfg = cargar(c)
    if not cfg.get("pattern"):
        raise SystemExit(
            f"✗ {c}: ni `audit.session_header.pattern` ni `session_date_regex` en el config.\n"
            f"  Sin fórmula de cabecera no hay nada contra lo que contrastar — declararla es\n"
            f"  el trabajo, y no se puede suplir con una heurística.")
    banderas = 0 if cfg.get("case_sensitive", True) else re.I
    pat = re.compile(cfg["pattern"], banderas)
    nfilas = o.scan_rows or int(cfg.get("scan_rows", 6))

    d = pd.read_csv(f"source/{c}/standardize/{c.upper()}_interventions.csv",
                    dtype=str, keep_default_na=False)

    # ⚠ La cabecera puede NO haber sobrevivido a la construcción de la matriz: en SV solo
    # 342 de 43.599 filas conservan «DE FECHA», porque la fórmula de apertura no era una
    # intervención y se quedó fuera. Se busca primero en los intermedios, donde sí está.
    fuente = "matriz"
    for carpeta in (cfg.get("from") or "corrected tagged").split():
        if list(Path(f"source/{c}/{carpeta}").glob("**/*.txt"))[:1]:
            doc = por_documento(c, carpeta, pat, cfg)
            if doc:
                fuente = carpeta
                break
    else:
        doc = {}
    orden = pd.to_numeric(d.get("intervention_order"), errors="coerce")
    tiene_num = "session_number" in d.columns

    cab: dict = defaultdict(set)
    nums: dict = defaultdict(set)
    tardias = 0
    if doc:
        # los intermedios llevan la cabecera intacta: la fecha registrada de cada documento
        # sale de meta/, que es de donde la tomó la matriz
        import sys as _s
        _s.path.insert(0, str(Path(__file__).resolve().parent))
        from attribute_presidency import _sid_a_fecha
        sid2f = _sid_a_fecha(c)
        for sid, (fe, nu) in doc.items():
            f = sid2f.get(sid)
            if not f:
                continue
            cab[f].add(fe)
            if nu:
                nums[f].add(str(nu))
    else:
        for f, g in d.groupby("date", sort=False):
            g = g.assign(_o=orden[g.index]).sort_values("_o")
            for k, (i, r) in enumerate(g.iterrows()):
                fe, nu = buscar(str(r.text), pat, cfg)
                if not fe:
                    continue
                if k < nfilas:
                    cab[f].add(fe)
                    if nu:
                        nums[f].add(str(nu))
                else:
                    tardias += 1

    # ⚠ Cuando discrepan, NO siempre manda el acta: si la cabecera viene de OCR, la
    # discrepancia suele ser suya. Se decide por CRONOLOGÍA, no por principio — la fecha de
    # la cabecera se contrasta con las sesiones vecinas del propio corpus. Medido en UY: de
    # 22 discrepancias, 20 eran años enteros de diferencia (−20, +1, +10, −2, +4, −70 años,
    # un dígito del año mal leído) y las vecinas confirmaban la fecha registrada.
    reg = sorted(pd.to_datetime(pd.Series(sorted(d.date.unique())), errors="coerce").dropna())
    import bisect

    def cabecera_implausible(f: str, h: str) -> bool:
        try:
            tf, th = pd.Timestamp(f), pd.Timestamp(h)
        except ValueError:
            return False
        i = bisect.bisect_left(reg, tf)
        ant = reg[i - 1] if i else tf - pd.Timedelta(days=30)
        sig = reg[i + 1] if i + 1 < len(reg) else tf + pd.Timedelta(days=30)
        return not (ant <= th <= sig)

    filas, cnt = [], defaultdict(int)
    for f in sorted(d.date.unique()):
        h = cab.get(f, set())
        reg_num = ""
        if tiene_num:
            v = d.loc[d.date == f, "session_number"].unique()
            reg_num = "|".join(sorted(x for x in v if x))
        if not h:
            v = "SIN_CABECERA"
        elif len(h) > 1:
            v = "CONFLADA"
        elif next(iter(h)) == f:
            v = "OK"
        else:
            h1 = next(iter(h))
            v = "OCR_CABECERA" if cabecera_implausible(f, h1) else "FECHA_DISTINTA"
        cnt[v] += 1
        if v != "OK":
            filas.append({"fecha_registrada": f, "cabecera": "|".join(sorted(h)),
                          "num_registrado": reg_num,
                          "num_cabecera": "|".join(sorted(nums.get(f, set()))),
                          "veredicto": v})

    tot = len(d.date.unique())
    print(f"  fuente de la cabecera: {fuente}"
          f"{f' ({len(doc):,} documentos)' if fuente != 'matriz' else ''}")
    print(f"{c.upper()} · {tot:,} sesiones · cabecera buscada en las primeras {nfilas} "
          f"intervenciones{' (patrón heredado de session_date_regex)' if cfg.get('_heredado') else ''}")
    for v in ("OK", "FECHA_DISTINTA", "OCR_CABECERA", "CONFLADA", "SIN_CABECERA"):
        n = cnt[v]
        print(f"  {v:15} {n:>7,} ({100*n/tot:5.1f}%)")
    if tardias:
        print(f"  ⚠ {tardias:,} coincidencias FUERA de las primeras {nfilas} filas — si son "
              f"muchas,\n    o la cabecera va más abajo o el patrón está cazando citas del cuerpo")
    if cnt["SIN_CABECERA"] > 0.5 * tot:
        print("  ⚠⚠ MÁS DE LA MITAD SIN CABECERA: el resultado NO es una cifra de calidad del\n"
              "     corpus, es que el patrón no encuentra la cabecera. Declara\n"
              "     `audit.session_header.pattern` antes de leer nada de lo de arriba.")

    # ⚠ Un DESFASE CONSTANTE es defecto del patrón, no de los datos. En PT, 1.321 de las
    # 1.368 discrepancias eran exactamente +1 día: el patrón cogía la fecha de PUBLICACIÓN
    # («Sexta-feira, 12 de outubro de 2012») en vez de la de la sesión («REUNIÃO PLENÁRIA DE
    # 11 DE OUTUBRO»). Sin esta comprobación, un fallo del patrón se lee como 28% de fechas
    # mal derivadas.
    dis = [x for x in filas if x["veredicto"] == "FECHA_DISTINTA" and "|" not in x["cabecera"]]
    if len(dis) >= 20:
        off = pd.Series([(pd.Timestamp(x["cabecera"]) - pd.Timestamp(x["fecha_registrada"])).days
                         for x in dis])
        moda, veces = off.mode().iat[0], int((off == off.mode().iat[0]).sum())
        if veces > 0.6 * len(dis) and abs(moda) <= 7:
            print(f"  ⚠⚠ DESFASE CONSTANTE de {moda:+d} días en {veces:,} de {len(dis):,} "
                  f"discrepancias:\n     el patrón está cogiendo OTRA fecha (típicamente la de "
                  f"publicación, no la de\n     la sesión). Es defecto del patrón, no del corpus.")

    ej = [x for x in filas if x["veredicto"] == "FECHA_DISTINTA"][:8]
    if ej:
        print("\n  muestra · fecha registrada → la que declara el acta")
        for x in ej:
            print(f"    {x['fecha_registrada']}  →  {x['cabecera']}   (nº {x['num_cabecera'] or '—'})")

    if o.report and filas:
        p = Path(o.report)
        p.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(filas).to_csv(p, index=False, encoding="utf-8")
        print(f"\n  informe → {p}  ({len(filas):,} sesiones que no son OK)")
    print("\n⚠ No se corrige nada: una fecha mal derivada está propagada al session_id y a los "
          "intermedios,\n  así que la corrección es un reproceso, no un UPDATE sobre la matriz.")


if __name__ == "__main__":
    main()
