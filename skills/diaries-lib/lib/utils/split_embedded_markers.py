#!/usr/bin/env python3
"""Divide las filas que contienen dentro el turno de palabra de OTRO orador.

Es el falso negativo más insidioso del pipeline: el marcador **sí se etiquetó**, pero quedó
absorbido dentro del `text` de la intervención anterior, así que `verify_tagging` no lo ve —
para él no hay marcadores sin etiquetar— y los recuentos cuadran. El discurso queda atribuido
a quien no lo dijo.

Magnitud medida (validación 2026-07-31, muestra de 300 por país con revisión humana de los
casos marcados): **~43.500 filas, el 0,54% del corpus**. Por país: UY 2,67% · PA y CR y PY y
AR ~1% · BR y MX 0,67% · PT 0,75% · ES y CO ~0,33% · CL, DO, GT, PE y SV en cero.
Precedente: en PA la auditoría recuperó **42.132 intervenciones**.

⚠ **La forma del marcador NO es común entre cámaras**, y por eso esto se parametriza:

    embedded_markers:
      terminators: [dash, colon, dash_before]   # cuáles admite esta cámara
      role_lowercase: false                     # MX escribe «El Presidente diputado X:»
      min_chunk: 60                             # trozo mínimo para ser intervención propia
      guards: [rollcall, quote, index]          # qué NO es un marcador incrustado

- **dash** — `SEÑOR MELO.-` (UY, AR, CL) · en AR el OCR corrompe el guion a `~`
- **colon** — `EL PRESIDENTE X:` (CR, PY) · `La señora SAINZ GARCIA:` (ES)
- **dash_before** — `—JULIO ESCOBAR, ASOCIACIÓN DE INTERÉS PÚBLICO` (PA, para no-diputados)

⚠⚠ **NUNCA aplicar sin mirar antes una muestra ALEATORIA de lo que se dividiría.** En CR el
detector marcó un 4,15% que parecía esta misma clase y resultó ser **el índice del acta**;
dividirlo habría fabricado miles de intervenciones basura. Lo desmintió la muestra, no el
porcentaje. Por eso `--sample` es un paso obligatorio del procedimiento, no una opción.

Las filas nuevas heredan `date`, `session_number`, `legislature` y `session_type` de la madre,
se quedan **sin `id_dep`** —lo resuelve `diaries-match` después— y se renumera
`intervention_order` de las sesiones afectadas. El sidecar de tipo/procedencia, si existe, se
reconstruye para seguir alineado fila a fila.

Uso:
    python3 split_embedded_markers.py --country uy --sample 25    # OBLIGATORIO primero
    python3 split_embedded_markers.py --country uy                # simulación con recuento
    python3 split_embedded_markers.py --country uy --apply
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

# ── piezas del marcador ───────────────────────────────────────────────────────
# ⚠ SENSIBLE A MAYÚSCULAS a propósito: `Señor Presidente:` en minúsculas es el VOCATIVO con
# que empieza casi toda intervención (20,4% de las filas de UY), no un marcador. Ignorar la
# distinción marcaba el 30% de UY sin un solo verdadero positivo.
# el artículo forma parte del marcador tal como lo escribe el acta —CL usa
# «El señor COLOMA (Vicepresidente).-»— y hay que capturarlo para que el `speaker_raw`
# resultante sea el mismo que el de las filas no divididas del corpus
ARTICULO = r"(?:[Ee]l|[Ll]a)\s+"
# ⚠ La ñ de «señor» la CORROMPE el OCR y ahí se pierden marcadores: en ES la campaña midió +2.892
# formas (seflor·sefior·setior·seíior·serior·sedor·seAor·sehor·sellor·seílor·selior…), donde la ñ sale
# como 1-2 caracteres cualesquiera. Por eso el hueco central admite `[A-Za-zÑñ]{1,2}` en vez de solo
# `[ÑNñn]`. El riesgo (p.ej. «sector») lo contiene la GUARDA dura que sigue: hace falta un NOMBRE en
# VERSALES y el terminador después, y el paso `--sample` es obligatorio. Ver feedback_faseC_es_marcadores.
CORTESIA = (r"(?:" + ARTICULO + r")?"
            r"(?:[Ss][Ee][A-Za-zÑñ]{1,2}[Oo][Rr](?:[Ii][Tt])?[AaOo]?|[Ss][Rr][Aa]?|[Ss][Rr][Tt][Aa])\s*[.,·]?")
# REPRESENTANTE: EC («EL H. REPRESENTANTE APELLIDO,NOMBRE:») y CO usan este rol; sin él, sus marcadores
# de diputado no se detectan. DEPUTAD[OA] cubre BR/PT.
ROL_CAPS = (r"(?:PRESIDENT[EA]|VICEPRESIDENT[EA]|SECRETARI[OA]|PROSECRETARI[OA]|"
            r"DIPUTAD[OA]|DEPUTAD[OA]|REPRESENTANTE|MINISTR[OA]|RELATOR[A]?|OFICIAL\s+MAYOR)")
ROL_MIXTO = (r"(?:[Ee]l|[Ll]a)\s+(?:[Pp]residente|[Vv]icepresidente|[Ss]ecretari[oa])"
             r"(?:\s+diputad[oa])?")
NOMBRE_CAPS = r"[A-ZÁÉÍÓÚÑÜ][A-ZÁÉÍÓÚÑÜ'\s]{2,44}?"
NOMBRE_MIXTO = r"[A-ZÁÉÍÓÚÑÜ][A-Za-zÁÉÍÓÚÑÜáéíóúñü'\s]{2,44}?"
PAREN = r"(?:[\(\{][^)\}]{0,40}[\)\}])?"

# ⚠ Un turno SIEMPRE empieza en mayúscula, comilla o signo de apertura. Sin esta guarda, el
# guion de la HIFENACIÓN a final de línea se toma por terminador y parte la prosa por dentro
# de una palabra: «el señor Angelelli no estuvo aje-\nno a la diatriba» daba un orador
# llamado *señor Angelelli no estuvo aje*, y «el señor Mar-\ntínez de Hoz» uno llamado
# *el señor Mar*. Es el falso positivo más traicionero porque el resultado parece un nombre.
INICIO_TURNO = r"(?=\s*[«»\"'¿¡\-]?\s*[A-ZÁÉÍÓÚÑÜ0-9])"

FIN = {
    # el guion, con el punto corrompido por OCR a coma o virgulilla
    "dash":       r"\s*" + PAREN + r"\s*[.,~]?\s*[-–—]" + INICIO_TURNO,
    "colon":      r"\s*" + PAREN + r"\s*[.,]?\s*:" + INICIO_TURNO,
    # ⚠ el GUION MISMO corrompido por el OCR. Medido en AR sobre 242 marcadores reales:
    # «—» 182 · «_» 27 · «~» 17 · «·» 14 · «-» 1 · «–» 1. Con la clase de guion limpia se
    # pierde uno de cada cuatro, y en los escaneos peores bastante más.
    # ⚠ El glifo corrompido solo cuenta AISLADO, entre espacios. Sin esa guarda, «Sr.
    # Pre~idente (Pugliese)» —donde la «~» es una «s» mal leída— se parte por dentro de la
    # palabra y produce un orador «Sr. Pre~» con el resto del nombre dentro del texto. El
    # guion limpio no necesita la guarda; el corrompido sí, y es la diferencia entre
    # recuperar turnos y fabricar basura.
    "dash_ocr":   (r"\s*" + PAREN + r"\s*[.,]?\s*"
                   r"(?:[-–—]|(?<=[\s.])[_~·=*](?=\s))") + INICIO_TURNO,
}
CITA = re.compile(r"(?:dijo|dice|le[íi]|leo|cito|citando|manifest[óo]|expres[óo]|"
                  r"se[ñn]al[óo]|afirm[óo])\b", re.I)
FIN_PAGINA = re.compile(r"[:\.]\s*\t?\s*\d{1,3}\s*$")
FIRMAS = re.compile(r"[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+\s*[.,]?\s*[–—]\s*[A-ZÁÉÍÓÚÑ]")


def construir_patron(cfg: dict) -> re.Pattern:
    """Ensambla el patrón de marcador según los terminadores que use esta cámara."""
    terms = cfg.get("terminators", ["dash"])
    alts = []
    for t in terms:
        if t == "dash_before":
            # PA: el guion va DELANTE del nombre y el CARGO tras una coma.
            # ⚠ El cargo hay que CONSUMIRLO entero, no solo comprobar que empieza. La versión
            # anterior terminaba en «coma + UNA mayúscula» y ese punto se usaba como corte:
            # partía el cargo por la mitad y dejaba el resto dentro del discurso —«MINISTRA DE
            # EDUCACIÓN, L» + «UCY MOLINAR…», «SECRETARIA GENERAL, E» + «NCARGADA»,
            # «JUAN DIEGO VÁSQUEZ GUTIÉRREZ, D» + «IPUTADO»—. El orador salía mutilado y el
            # texto empezaba a media palabra.
            # El cargo se consume por PALABRAS en versales, y la racha no puede terminar
            # justo antes de una minúscula: si no, se traga la inicial de la frase siguiente
            # —«…LUCY MOLINAR T» + «odas las que se puedan», «…ENCARGADA R» + «esumen»—.
            alts.append(r"(?:^|\n)\s*[—–-]\s*[A-ZÁÉÍÓÚÑÜ][A-ZÁÉÍÓÚÑÜ'\.\s]{4,44},"
                        r"\s*(?:[A-ZÁÉÍÓÚÑÜ'\.]+\s*)+(?![a-záéíóúñü])")
            continue
        f = FIN.get(t)
        if not f:
            continue
        alts.append(rf"(?:{CORTESIA}\s+{NOMBRE_CAPS}{f})")
        alts.append(rf"(?:\b{ROL_CAPS}\b(?:\s+{NOMBRE_CAPS})?{f})")
        if cfg.get("role_lowercase"):
            # MX: «El Presidente diputado Alfredo Villegas Arreola:»
            alts.append(rf"(?:{ROL_MIXTO}\s+{NOMBRE_MIXTO}{f})")
        if cfg.get("name_titlecase"):
            # ⚠ AR escribe el nombre en Title Case, no en versales: «Sr. García Vázquez. —».
            # Exigir mayúsculas dejaba el detector en 7 filas de 260.455 —un 0,00% que
            # parecía un corpus limpio— cuando la validación por muestreo medía un 1,00%.
            # Y el nombre viene corrompido por el OCR («Sr. Alvarcz Ecbagüe» por *Álvarez
            # Echagüe*), así que el detector por VOCABULARIO tampoco lo ve: aquí solo
            # sirve la forma.
            alts.append(rf"(?:{CORTESIA}\s*{NOMBRE_MIXTO}{f})")
    return re.compile("|".join(alts))


def norm_ac(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip()


def vocabulario(d: pd.DataFrame):
    """Los nombres de orador que el corpus ya conoce, para detectar sin asumir tipografía.

    ⚠ **El nombre se busca TAL COMO ESTÁ EN EL CORPUS, con sus tildes.** La versión anterior
    quitaba los acentos del vocabulario pero no del texto contra el que casaba: «Jattín»
    nunca coincidía entera y solo enganchaban fragmentos, produciendo oradores mutilados
    como *a Zulema Jattin C* en vez de *Presidenta Zulema Jattín Corrales* —5 de 10 filas de
    la muestra de CO—. Normalizar la aguja y no el pajar no falla: acierta a medias, que es
    peor, porque el recuento parece razonable.

    ⚠ **De más larga a más corta**: en una alternancia, `re` devuelve la PRIMERA que casa,
    no la más larga. Sin ordenar, «Zulema Jattín» ganaba a «Presidenta Zulema Jattín
    Corrales» y el marcador salía recortado.
    """
    voc = [s for s, _ in Counter(d.speaker_raw[d.speaker_raw.str.split().str.len() >= 2])
           .most_common(600)]
    voc = sorted({v.strip().rstrip(":").strip() for v in voc if len(v) > 10},
                 key=len, reverse=True)[:400]
    if not voc:
        return None, None
    alt = "|".join(map(re.escape, voc))
    ROL_PREV = r"(?:EL |LA )?(?:PRESIDENT[EA]|VICEPRESIDENT[EA]|DIPUTAD[OA]|SECRETARI[OA])\s+"
    return (re.compile(rf"(?:{ROL_PREV})?(?:{alt})\s*[.,]?\s*[:\-–—]"),
            re.compile(rf"(?:{alt})"))


def es_indice(t: str) -> bool:
    lin = [x for x in str(t).split("\n") if x.strip()]
    return bool(lin) and sum(bool(FIN_PAGINA.search(x)) for x in lin) / len(lin) >= 0.5


CONTEXTO_EXCLUIR_DEF = [
    # cabecera que enumera quién presidió, no un turno
    r"Presidencia\s+de\s+l[oa]s?\b",
    # enumeración de intervinientes unidos por «y»
    r"\bintervenci[óo]n(?:es)?\s+de\b",
]


def cargar_config(iso2: str) -> dict:
    p = Path(f"country_config/{iso2}.yaml")
    if not p.exists() or yaml is None:
        return {}
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("embedded_markers") or {}


def dividir(texto: str, speaker0: str, pat: re.Pattern, cfg: dict):
    """→ [(speaker, texto)]; el primer trozo conserva el orador original."""
    mn = int(cfg.get("min_chunk", 60))
    ms = [m for m in pat.finditer(texto)
          if not CITA.search(texto[max(0, m.start() - 90):m.start()])]
    if not ms:
        return [(speaker0, texto)]
    out = []
    cab = texto[:ms[0].start()].strip()
    if len(cab) >= mn:
        out.append((speaker0, cab))
    for i, m in enumerate(ms):
        fin = ms[i + 1].start() if i + 1 < len(ms) else len(texto)
        cuerpo = texto[m.end():fin].strip()
        if len(cuerpo) < mn:
            continue
        out.append((re.sub(r"\s+", " ", m.group(0)).strip(" .,:-–—"), cuerpo))
    return out or [(speaker0, texto)]


def objetivo(d: pd.DataFrame, pat: re.Pattern, cfg: dict, voc_nom=None):
    """Filas divisibles, con las guardas aplicadas."""
    guards = set(cfg.get("guards", ["rollcall", "quote", "index"]))
    maxn = int(cfg.get("max_names", 6))
    m = d.text.map(lambda t: bool(pat.search(str(t))))
    if "index" in guards:
        m &= ~d.text.map(es_indice)
    if "rollcall" in guards and voc_nom is not None:
        m &= ~d.text.map(lambda t: len(voc_nom.findall(norm_ac(t))) > maxn)
    if "signatures" in guards:
        m &= d.text.map(lambda t: len(FIRMAS.findall(str(t))) < 3)
    return m


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--sample", type=int, default=0,
                    help="muestra ALEATORIA de lo que se dividiría — hazlo SIEMPRE primero")
    ap.add_argument("--seed", type=int, default=20260801)
    a = ap.parse_args()
    c = a.country.lower()

    cfg = cargar_config(c)
    if not cfg:
        raise SystemExit(f"✗ {c}: falta el bloque `embedded_markers:` en country_config/{c}.yaml")

    csv = Path(f"source/{c}/standardize/{c.upper()}_interventions.csv")
    d = pd.read_csv(csv, dtype=str, keep_default_na=False)
    n0 = len(d)
    pat = construir_patron(cfg)
    voc_pat, voc_nom = vocabulario(d)
    # ⚠ El vocabulario servía SOLO para elegir filas candidatas; el corte lo hacía siempre el
    # patrón de FORMA. En CO eso daba 2 filas de 450.741 (0,00%) frente al 0,33% medido a
    # mano, porque su marcador —«Nombre Completo:» en Title Case— no tiene forma que lo
    # distinga de un vocativo («Honorables Representantes:», «Señor Presidente:»). Es la
    # imagen simétrica de AR, donde el OCR corrompe el nombre y solo sirve la forma:
    # ningún detector solo cubre los dos casos.
    if cfg.get("use_vocabulary"):
        pat = re.compile(f"(?:{pat.pattern})|(?:{voc_pat.pattern})")
    obj = objetivo(d, pat, cfg, voc_nom)

    trozos = {i: dividir(d.at[i, "text"], d.at[i, "speaker_raw"], pat, cfg)
              for i in d.index[obj]}
    nuevas = sum(len(v) - 1 for v in trozos.values())
    print(f"{c.upper()} · {n0:,} filas · terminadores {cfg.get('terminators')}")
    print(f"  filas divisibles       : {int(obj.sum()):,} ({100*obj.sum()/n0:.2f}%)")
    print(f"  intervenciones a recuperar: {nuevas:,}")

    if a.sample:
        random.seed(a.seed)
        ks = random.sample(sorted(trozos), min(a.sample, len(trozos)))
        print(f"\n─── MUESTRA ALEATORIA de {len(ks)} · confírmala ANTES de --apply ───")
        for k in ks:
            r = d.loc[k]
            print(f"\n[{r.date} ses {r.session_number} · orador actual {r.speaker_raw[:34]!r}]")
            for sp, tx in trozos[k][:3]:
                print(f"   → {sp[:44]!r}: {tx[:110]}…")
        return

    if not a.apply:
        print("\n--- SIMULACIÓN --- (ejecuta antes --sample y confirma)")
        return

    filas = []
    for i, r in d.iterrows():
        if i not in trozos:
            filas.append(r.to_dict())
            continue
        for k, (sp, tx) in enumerate(trozos[i]):
            x = r.to_dict()
            x["text"] = tx
            if k > 0:
                x.update(speaker_raw=sp, id_dep="", speaker_name="", party="",
                         district="", sex="")
            filas.append(x)
    out = pd.DataFrame(filas)

    ses = set(d.loc[obj, "date"] + "|" + d.loc[obj, "session_number"])
    key = out.date + "|" + out.session_number
    m = key.isin(ses)
    out.loc[m, "intervention_order"] = (out[m].groupby(key[m], sort=False).cumcount() + 1).astype(str)

    bak = csv.with_name(csv.stem + ".pre_incrustados.csv")
    if not bak.exists():
        shutil.copy2(csv, bak)
        print(f"  copia de seguridad → {bak.name}")
    out.to_csv(csv, index=False, encoding="utf-8")
    chk = pd.read_csv(csv, dtype=str, keep_default_na=False, usecols=["text"])
    assert len(chk) == n0 + nuevas, f"recuento inconsistente {len(chk)} != {n0 + nuevas}"
    assert not (chk.text.str.strip() == "").any(), "han quedado filas vacías"
    print(f"✓ {len(chk):,} filas ({n0:,} + {nuevas:,}) · {len(ses)} sesiones renumeradas")


if __name__ == "__main__":
    main()
