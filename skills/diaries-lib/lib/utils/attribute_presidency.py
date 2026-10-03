#!/usr/bin/env python3
"""Atribuye la presidencia de la sesión al `id_dep` de quien preside.

Generaliza las **doce variantes por país** que se escribieron una a una durante la revisión
pre-publicación (BR, PA, PE, PT, PY, UY). El algoritmo es el mismo en todas; lo que cambia
cabe en tres parámetros del `country_config/{iso2}.yaml`:

    presidency:
      scope: session | segments     # ¿un presidente por sesión, o cambia dentro?
      target: [PRESIDENT]           # prefijos de speaker_raw que se atribuyen
      sources:                      # dónde se declara quién preside, por orden
        - from: corrected           # corrected | meta | tagged
          pattern: '...'            # regex con el nombre en un grupo
          name_group: 1
          head: 20000               # solo el principio del documento
      segments:                     # solo si scope: segments
          from: tagged
          pattern: '\\(Ocupa la Presidencia el se[ñn]or ([^)]{2,50})\\)'

**Por qué importa `scope`.** En Uruguay la mesa rota DENTRO de la sesión: atribuir un único
presidente por sesión falla el **35,0%** de los casos, medido. El modo `segments` sigue las
marcas de relevo del propio acta y atribuye por tramos.

**El resolutor es el mismo para todos** y su cascada está calibrada contra revisión humana:
50 discrepancias al azar entre esta utilidad y los scripts originales, juzgadas mirando el acta.
Todas las estrategias acertaban el 100% salvo una —casar por **un único token de apellido**, usada
en 35 de los 50 casos y con **51% de acierto**—. Restringida a exigir unicidad en todo el padrón,
y con las partículas ya fuera del índice (`De Vargas` colisionaba con cualquier apellido en «de»),
la utilidad acierta o se abstiene en **47 de 50**, con una sola regresión.

**Criterio de aceptación: el ACIERTO medido, no la reproducción.** `--check` contrasta contra
lo ya atribuido, y lo ya atribuido también puede estar mal. Quien decide es
`audit_presidency_gender.py`, que juzga con el género del vocativo contiguo —un mecanismo que
no comparte nada con la atribución—. La reproducción **no predice el acierto**: en PT el
genérico reproducía solo el 66,27% siendo cinco puntos MEJOR (93,62 → 98,74), y en BR
reproduce el 27,50% siendo dos puntos y medio PEOR (99,27 → 96,89).

**Dónde sustituye a los scripts originales y dónde no** (auditoría de 2026-08-01):

    PT 93,62 → 98,74 ·  UY 98,21 → 99,65 ·  PY 99,19 → 99,82 ·  PA 90,82 → 91,64   ✓ sustituye
    PE 89,49 → 88,19 ·  BR 99,27 → 96,89                                            ✗ NO sustituye

BR y PE se construyeron fuera del pipeline —sin `corrected/` ni `tagged/`— y su mesa rota
dentro de la sesión sin ningún intermedio donde situar los tramos. Conservan su atribución.

⚠ **Nunca elimina ni aparta filas.** Solo rellena `id_dep`, `speaker_name` y `party` donde
estaban vacíos: si el orador no casa con el padrón, el fallo es del padrón y la intervención
se queda como está (validation_methodology §4.6).

Uso:
    python3 attribute_presidency.py --country pa                 # simulación
    python3 attribute_presidency.py --country pa --apply
    python3 attribute_presidency.py --country pa --check         # contrasta con lo ya atribuido
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

try:
    import yaml
except ImportError:                                    # pragma: no cover
    yaml = None

PART = {"de", "del", "la", "las", "los", "da", "das", "do", "dos", "y", "e",
        "san", "santa", "van", "von", "di", "der"}
TITULOS = re.compile(r"^\s*(?:sr\.?[ªa]?s?\.?|sra\.?|srta\.?|don|do[ñn]a|dr\.?[ªa]?|dra\.?|"
                     r"lic\.?|ing\.?|prof\.?|ex\.?\s*[mn]?[oa]?s?\.?|representante|"
                     r"deputad[oa]|diputad[oa]|se[ñn]or(?:a|ita)?)\s+", re.I)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z\s]", " ", s)).strip()


def limpiar(n: str) -> str:
    """Quita tratamientos y cargos del nombre extraído por el patrón."""
    prev = None
    while prev != n:
        prev = n
        n = TITULOS.sub("", n).strip()
    return re.sub(r"\s+", " ", n).strip(" .,-")


# ── configuración ─────────────────────────────────────────────────────────────
def cargar_config(iso2: str) -> dict:
    p = Path(f"country_config/{iso2}.yaml")
    if not p.exists() or yaml is None:
        return {}
    d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return d.get("presidency") or {}


# ── padrón ────────────────────────────────────────────────────────────────────
def indice(iso2: str):
    """→ (completo, apellido, mandatos, info) para resolver un nombre a id_dep."""
    for n in ("deputies.csv", "diputados_bd.csv"):
        p = Path(f"source/{iso2}/deputies/{n}")
        if p.exists():
            break
    else:
        raise SystemExit(f"sin padrón para {iso2}")
    head = p.open(encoding="utf-8", errors="replace").readline()
    r = pd.read_csv(p, sep=";" if head.count(";") > head.count(",") else ",",
                    dtype=str, keep_default_na=False)
    low = {c.lower(): c for c in r.columns}
    cid = low.get("id_dep") or low.get("diputado_id")
    cnm = next((low[k] for k in ("nombre_completo", "speaker_name", "nombre_original", "alias")
                if k in low), cid)
    cap = next((low[k] for k in ("apellidos", "last_name") if k in low), None)
    cpa = next((low[k] for k in ("partido", "party", "sgl_partido") if k in low), None)
    cin = next((low[k] for k in ("fecha_inicio", "fecha_alta", "start_date") if k in low), None)
    cfi = next((low[k] for k in ("fecha_fin", "fecha_baja", "end_date") if k in low), None)

    completo, apellido, mand, info = defaultdict(set), defaultdict(set), defaultdict(list), {}
    for _, row in r.iterrows():
        i = row[cid]
        nc = str(row[cnm])
        info.setdefault(i, (nc, str(row[cpa]) if cpa else ""))
        k = norm(nc)
        if k:
            completo[k].add(i)
        ap = norm(row[cap]) if cap else " ".join(
            [x for x in norm(nc).split() if x not in PART][-2:])
        if ap:
            apellido[ap].add(i)
            # ⚠ solo el primer token SI NO es partícula: indexar «de» hacía que
            # «De Vargas» colisionara con cualquier apellido que empiece por «de»
            pr = ap.split()[0]
            if pr not in PART and len(pr) > 2:
                apellido[pr].add(i)
        if cin:
            a = pd.to_datetime(row[cin], errors="coerce")
            b = pd.to_datetime(row[cfi], errors="coerce") if cfi else pd.NaT
            if pd.notna(a):
                mand[i].append((a, b if pd.notna(b) else pd.Timestamp("2100-01-01")))
    return completo, apellido, mand, info


def _orto(s: str) -> str:
    """Normaliza las equivalencias ortográficas del español que el OCR y las actas mezclan.

    Medido en EC: `LARRIVA GONZÁLEZ` no casaba con *Larriva **Gonzáles*** por una sola letra,
    y esa diputada tiene 816 intervenciones. s↔z, b↔v, g↔j ante e/i, y h muda.
    """
    s = re.sub(r"h", "", s)
    s = re.sub(r"z", "s", s)
    s = re.sub(r"v", "b", s)
    s = re.sub(r"g([ei])", r"j\1", s)
    s = re.sub(r"ll", "y", s)
    return s


def resolver(nombre: str, completo, apellido, mand, fecha: str = "") -> str | None:
    """Nombre del acta → id_dep.

    Cascada de estrategias, de la más estricta a la más laxa, con desempate por mandato
    vigente en la fecha. Cada paso viene de un fallo real medido en el proyecto:

    1. nombre completo exacto
    2. apellidos exactos, y primer apellido — el acta suele citar solo por apellido
    3. **el marcador es PREFIJO del nombre del padrón** — `Ope Pasquet` → `Ope Pasquet
       Iribarne` (UY)
    4. **subconjunto de tokens** — el marcador nombra parte y el padrón el resto
    5. **equivalencia ortográfica** — s↔z, b↔v, g↔j, h muda (EC, 816 intervenciones)

    Nunca devuelve un candidato ambiguo: si tras desempatar por mandato queda más de uno,
    devuelve None y la fila se queda sin atribuir. Una atribución dudosa es peor que ninguna.
    """
    n = norm(limpiar(nombre))
    if not n:
        return None
    toks = [x for x in n.split() if x not in PART and len(x) > 2]
    if not toks:
        return None

    def desempatar(cand):
        if not cand:
            return None
        if len(cand) == 1:
            return next(iter(cand))
        d = pd.to_datetime(fecha, errors="coerce")
        if pd.isna(d):
            return None
        viv = [i for i in cand if any(a <= d <= b for a, b in mand.get(i, ()))]
        return viv[0] if len(viv) == 1 else None

    # 1-2 · exacto, de más específico a menos
    for cand in (completo.get(n), apellido.get(n), apellido.get(" ".join(toks[-2:]))):
        if (r := desempatar(cand)):
            return r

    # 2-bis · UN SOLO token de apellido: solo si es ÚNICO en todo el padrón.
    # ⚠ Medido sobre 50 discrepancias revisadas a mano: esta estrategia se usaba en 35 de
    # ellas y acertaba el 51% — una moneda al aire. Todas las demás acertaban el 100%.
    # Con un apellido común, «el único vigente en esa fecha» no es la persona correcta:
    # es la única que quedó tras filtrar, que es otra cosa. Si hay más de un candidato,
    # se prefiere NO atribuir.
    uni = apellido.get(toks[-1]) if len(toks) == 1 else None
    if uni and len(uni) == 1:
        return next(iter(uni))

    # 3 · el marcador es prefijo del nombre del padrón
    if (r := desempatar({i for k, v in completo.items() if k.startswith(n + " ") for i in v})):
        return r

    # 4 · subconjunto de tokens
    st = set(toks)
    if (r := desempatar({i for k, v in completo.items()
                         if st and st <= set(k.split()) for i in v})):
        return r

    # 5 · equivalencia ortográfica, sobre nombre completo y apellidos
    o = _orto(n)
    if (r := desempatar({i for k, v in completo.items() if _orto(k) == o for i in v})):
        return r
    if (r := desempatar({i for k, v in apellido.items() if _orto(k) == o for i in v})):
        return r
    so = {_orto(x) for x in toks}
    if (r := desempatar({i for k, v in completo.items()
                         if so and so <= {_orto(x) for x in k.split()} for i in v})):
        return r
    return None


# ── extracción de quién preside ───────────────────────────────────────────────
def _sid_a_fecha(iso2: str) -> dict:
    """session_id → fecha, SIEMPRE desde meta/.

    ⚠ La fecha no se deriva del nombre de fichero: es catalogación, no fuente. En CO la
    cabecera del acta corrigió 11 fechas mal catalogadas en el nombre
    ([[feedback_meta_date_extraction]]). El único país donde se permite es PY, y por un
    defecto real de sus datos —sus session_id no casan entre meta/ y tagged/ (243 de 1.553)—
    que hay que declarar explícitamente con `date_from: filename` en su config.
    """
    m = {}
    for mp in glob.glob(f"source/{iso2}/meta/*.json"):
        try:
            d = json.load(open(mp, encoding="utf-8"))
        except Exception:
            continue
        f = str(d.get("date", "")).strip()
        if f:
            m[Path(mp).stem] = f
    return m


FECHA_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
FECHA_DMY = re.compile(r"(\d{2})-(\d{2})-(\d{4})")


def _fecha_de_nombre(sid: str) -> str | None:
    if (g := FECHA_ISO.search(sid)):
        return g.group(0)
    if (g := FECHA_DMY.search(sid)):
        return f"{g.group(3)}-{g.group(2)}-{g.group(1)}"
    return None


def _leer_texto(fp: str, head: int) -> str:
    """Texto plano. Si es HTML, se le quitan las etiquetas antes de buscar.

    ⚠ Sin esto PT daba 0%: su cabecera declara `Presidente: Ex.mo Sr. …` pero en el HTML
    original hay etiquetas entre medias, así que ningún patrón sobre el nombre casaba.
    """
    t = open(fp, encoding="utf-8", errors="replace").read(head * 4)
    if fp.lower().endswith((".html", ".htm", ".xml")):
        t = re.sub(r"<(?:script|style)[^>]*>.*?</(?:script|style)>", " ", t, flags=re.S | re.I)
        t = re.sub(r"<[^>]+>", " ", t)
        t = (t.replace("&nbsp;", " ").replace("&aacute;", "á").replace("&eacute;", "é")
              .replace("&iacute;", "í").replace("&oacute;", "ó").replace("&uacute;", "ú")
              .replace("&ntilde;", "ñ").replace("&amp;", "&"))
        t = re.sub(r"[ \t]{2,}", " ", t)
    return t[:head]


def _leer_pdf(fp: str, head: int, paginas: int = 1) -> str:
    """Las primeras `paginas` del PDF.

    ⚠ Una sola página no basta cuando la fórmula va DENTRO del debate y no en la cabecera:
    BR marca `O SR. PRESIDENTE (Nome)` en el cuerpo, y con `pdf_pages: 1` reproducía el 1%.
    Los que la llevan en cabecera (PE) van bien con 1 y no conviene subirlo: cada página
    extra multiplica el tiempo sobre miles de PDF.
    """
    try:
        import pdfplumber
        with pdfplumber.open(fp) as d:
            return "\n".join((pg.extract_text() or "")
                              for pg in d.pages[:max(1, paginas)])[:head]
    except Exception:
        return ""


def por_fecha(iso2: str, cfg: dict) -> tuple[dict, Counter]:
    """→ {fecha: nombre} desde las fuentes declaradas, en orden de prioridad."""
    out, gen = {}, Counter()
    sid2f = _sid_a_fecha(iso2)
    for src in cfg.get("sources", []):
        kind = src.get("from", "corrected")
        if kind == "meta":
            campo = src.get("field", "president")
            for mp in glob.glob(f"source/{iso2}/meta/*.json"):
                try:
                    d = json.load(open(mp, encoding="utf-8"))
                except Exception:
                    continue
                f, v = str(d.get("date", "")), str(d.get(campo, "")).strip()
                if f and v:
                    out.setdefault(f, v)
            continue
        pat = re.compile(src["pattern"], re.I | re.M)
        g = int(src.get("name_group", 1))
        head = int(src.get("head", 20000))
        por_nombre = src.get("date_from") == "filename"
        if kind == "external":
            rutas = sorted(glob.glob(os.path.expanduser(src["path"]), recursive=True))
            npag = int(src.get("pdf_pages", 1))
            leer = ((lambda f, h: _leer_pdf(f, h, npag))
                    if rutas and rutas[0].lower().endswith(".pdf") else _leer_texto)
        else:
            rutas = sorted(glob.glob(f"source/{iso2}/{kind}/**/*.txt", recursive=True))
            leer = _leer_texto
        for fp in rutas:
            sid = Path(fp).stem
            f = (_fecha_de_nombre(sid) if por_nombre or kind == "external"
                 else sid2f.get(sid))
            if not f or f in out:
                continue
            cuerpo = leer(fp, head)
            if not cuerpo:
                continue
            m = pat.search(cuerpo)
            if m:
                out[f] = re.sub(r"\s+", " ", m.group(g)).strip()
                if g > 1 and m.lastindex and m.lastindex >= 1:
                    gen[str(m.group(1)).lower()[:2]] += 1
    return out, gen


VUELTA = "\x00base"          # centinela: el relevo devuelve la mesa al titular de la sesión


def cambios(iso2: str, cfg: dict) -> dict:
    """→ {fecha: [(ordinal_de_intervencion, nombre | VUELTA)]} para scope=segments.

    ⚠ **El relevo de vuelta suele no llevar nombre**, y hay que reconocerlo igual. En PT
    hay 511 «assumiu a presidência o Presidente.» a secas frente a los relevos con nombre:
    si solo se capturan los nombrados, el tramo del vicepresidente no se cierra nunca y se
    come el resto de la sesión. Se declara con `segments.back_to_base`.
    """
    seg = cfg.get("segments") or {}
    if not seg:
        return {}
    pat = re.compile(seg["pattern"], re.I)
    vuelta = re.compile(seg["back_to_base"], re.I) if seg.get("back_to_base") else None
    # ⚠ El marcador por defecto NO puede exigir el atributo: PT etiqueta con `<int>` a secas
    # y `<int\s+speaker=` no casaba ni una vez, así que TODOS los relevos caían en la
    # posición 0 y el último se llevaba la sesión entera. Un contador que da cero es
    # indistinguible de «no hubo relevos» y no protesta.
    marca = re.compile(seg.get("intervention_mark", r"<int\b"))
    carpeta = seg.get("from", "tagged")
    sid2f = _sid_a_fecha(iso2)
    out, sin_marca = defaultdict(list), []
    for fp in sorted(glob.glob(f"source/{iso2}/{carpeta}/**/*.txt", recursive=True)):
        f = sid2f.get(Path(fp).stem)
        if not f:
            continue
        t = open(fp, encoding="utf-8", errors="replace").read()
        pos = [m.start() for m in marca.finditer(t)]
        marcas = [(m.start(), m.group(1)) for m in pat.finditer(t)]
        if vuelta:
            nombrados = {m[0] for m in marcas}
            marcas += [(m.start(), VUELTA) for m in vuelta.finditer(t)
                       if m.start() not in nombrados]
        # ⚠ Lo que aparece ANTES de la primera intervención es el sumario, no un relevo.
        # En PT el sumario de cabecera recapitula todos los relevos de la sesión: sin esta
        # guarda caen todos en la posición 0 y el último se come la sesión entera —el
        # presidente titular desaparecía de 116.175 filas—. Se desactiva con `preamble: keep`
        # si alguna cámara anuncia de verdad el relevo antes de la primera intervención.
        if pos and seg.get("preamble", "skip") == "skip":
            marcas = [m for m in marcas if m[0] > pos[0]]
        if marcas and not pos:
            sin_marca.append(Path(fp).stem)
        for ini, nom in marcas:
            out[f].append((sum(1 for p in pos if p < ini), nom))
    if sin_marca:
        print(f"  ⚠ {len(sin_marca):,} documentos con relevo pero SIN marcas de intervención "
              f"({seg.get('intervention_mark', '<int')}): los tramos no se pueden situar "
              f"— p.ej. {sin_marca[0]}", file=sys.stderr)
    return out


def objetivo_presidencia(df: pd.DataFrame, cfg: dict) -> pd.Series:
    """Filas cuya presidencia se atribuye, según `target` menos `target_exclude`.

    ⚠ **El prefijo solo no basta.** «PRESIDENT» captura también al *Presidente da República*
    —jefe de Estado, no diputado— y a los presidentes de cámaras extranjeras invitadas: en PT
    son 80 filas que se habrían atribuido a un parlamentario portugués cualquiera.

    ⚠ **La exclusión es por coincidencia COMPLETA, no por subcadena.** El *Presidente da
    Assembleia da República* SÍ es el objetivo —es quien preside la cámara— y contiene entera
    la cadena del jefe de Estado: excluir «da República» por subcadena se llevaba por delante
    esas 160 filas.
    """
    s = df.speaker_raw.str.strip().str.upper()
    pref = tuple(x.upper() for x in cfg.get("target", ["PRESIDENT"]))
    m = s.str.startswith(pref)
    ex = cfg.get("target_exclude", [])
    if ex:
        m &= ~s.str.fullmatch("|".join(x.upper() for x in ex), na=False)
    return m


# ── atribución ────────────────────────────────────────────────────────────────
def atribuir(iso2: str, cfg: dict, df: pd.DataFrame):
    """→ (asignacion {indice: id_dep}, objetivo, diagnostico)"""
    completo, apellido, mand, info = indice(iso2)
    nombres, gen = por_fecha(iso2, cfg)
    cbs = cambios(iso2, cfg) if cfg.get("scope") == "segments" else {}

    es_pres = objetivo_presidencia(df, cfg)
    objetivo = es_pres & (df.id_dep.str.strip() == "")

    asign, sin = {}, Counter()
    orden = ("intervention_order" if "intervention_order" in df.columns else None)
    for f, grupo in df.groupby("date", sort=False):
        # ⚠ los tramos se asignan por POSICION, así que hay que recorrer las filas en el
        # orden real de la sesión. En UY, 5 de cada 400 fechas venían desordenadas en el
        # CSV y eso desplazaba el corte, cambiando el presidente de un tramo entero.
        idxs = (list(grupo.sort_values(orden, key=lambda s: pd.to_numeric(s, errors="coerce")).index)
                if orden else list(grupo.index))
        base = nombres.get(f)
        id_base = resolver(base, completo, apellido, mand, f) if base else None
        if base and not id_base:
            sin[limpiar(base)] += 1
        tramos = []
        for k, nom in sorted(cbs.get(f, [])):
            if nom == VUELTA:
                tramos.append((k, id_base))
                continue
            i = resolver(nom, completo, apellido, mand, f)
            (tramos.append((k, i)) if i else sin.__setitem__(limpiar(nom), sin[limpiar(nom)] + 1))
        actual = id_base
        for rank, x in enumerate(idxs):
            while tramos and tramos[0][0] <= rank:
                actual = tramos.pop(0)[1]
            if objetivo[x] and actual:
                asign[x] = actual
    return asign, objetivo, {"fechas_con_nombre": len(nombres), "sin_resolver": sin,
                             "genero": dict(gen), "info": info,
                             "fechas_con_cambios": sum(1 for v in cbs.values() if v)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true",
                    help="contrasta contra la atribución ya existente, sin escribir")
    a = ap.parse_args()
    c = a.country.lower()

    cfg = cargar_config(c)
    if not cfg:
        raise SystemExit(f"✗ {c}: falta el bloque `presidency:` en country_config/{c}.yaml")

    csv = Path(f"source/{c}/standardize/{c.upper()}_interventions.csv")
    df = pd.read_csv(csv, dtype=str, keep_default_na=False)

    if a.check:
        # ¿reproduce el genérico lo que ya está atribuido?
        es_pres = objetivo_presidencia(df, cfg)
        ya = df[es_pres & (df.id_dep.str.strip() != "")]
        d2 = df.copy()
        d2.loc[ya.index, "id_dep"] = ""            # se borra para que sean objetivo
        asign, _, diag = atribuir(c, cfg, d2)
        ok = sum(1 for i in ya.index if asign.get(i) == df.at[i, "id_dep"])
        dif = sum(1 for i in ya.index if i in asign and asign[i] != df.at[i, "id_dep"])
        falta = len(ya) - ok - dif
        print(f"{c.upper()} · CHECK contra {len(ya):,} filas ya atribuidas")
        print(f"  reproduce igual : {ok:8,} ({100*ok/max(len(ya),1):6.2f}%)")
        print(f"  atribuye OTRO   : {dif:8,} ({100*dif/max(len(ya),1):6.2f}%)")
        print(f"  no atribuye     : {falta:8,} ({100*falta/max(len(ya),1):6.2f}%)")
        return

    asign, objetivo, diag = atribuir(c, cfg, df)
    n = int(objetivo.sum())
    print(f"{c.upper()} · scope={cfg.get('scope','session')} · "
          f"fechas con presidencia declarada: {diag['fechas_con_nombre']:,}"
          + (f" · con relevos: {diag['fechas_con_cambios']:,}" if diag['fechas_con_cambios'] else ""))
    if diag["genero"]:
        print(f"  reparto por género del artículo: {diag['genero']}  ← control de sesgo")
    print(f"  filas de presidencia sin id : {n:,}")
    print(f"  atribuibles                 : {len(asign):,} "
          f"({100*len(asign)/max(n,1):.1f}% del hueco)")
    s = diag["sin_resolver"]
    if s:
        print(f"  nombres sin resolver        : {len(s):,} — top {[k for k,_ in s.most_common(4)]}")

    if not a.apply:
        print("\n--- SIMULACIÓN --- (usa --apply para escribir)")
        for x in list(asign)[:4]:
            print(f"   {df.at[x,'date']} · {df.at[x,'speaker_raw'][:34]!r} → {asign[x]} "
                  f"{diag['info'].get(asign[x],('?',))[0][:34]!r}")
        return

    bak = csv.with_name(csv.stem + ".pre_presidencia.csv")
    if not bak.exists():
        shutil.copy2(csv, bak)
        print(f"  copia de seguridad → {bak.name}")
    idx = pd.Index(sorted(asign))
    df.loc[idx, "id_dep"] = [asign[i] for i in idx]
    df.loc[idx, "speaker_name"] = [diag["info"].get(asign[i], ("", ""))[0] for i in idx]
    df.loc[idx, "party"] = [diag["info"].get(asign[i], ("", ""))[1] for i in idx]
    df.to_csv(csv, index=False, encoding="utf-8")
    chk = pd.read_csv(csv, dtype=str, keep_default_na=False, usecols=["id_dep"])
    assert len(chk) == len(df), "recuento inconsistente"
    print(f"✓ {len(chk):,} filas · id_dep {100*(chk.id_dep.str.strip()!='').mean():.2f}%")


if __name__ == "__main__":
    main()
