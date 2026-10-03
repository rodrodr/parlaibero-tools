#!/usr/bin/env python3
"""Presidentes AUSENTES del padrón, buscados por su firma interna. Sin fuente externa.

⚠ La primera versión usaba un cotejo de nombres MÁS DÉBIL que el de `presidencia_declarada.py`, y
por eso `António de Almeida Santos` salía a la vez como «declarado que no resuelve» y como «nunca
declarado»: era la misma persona contada dos veces, y B daba 79.534 filas donde no había caso.
**Una auditoría tiene que usar el mismo resolutor que aquello que audita, o fabrica alarmas.**

La firma real, la de PT: un nombre que la carátula declara **repetidamente**, que NO resuelve ni
con la cascada completa —exacta · núcleo sin la cola «de X» · subconjunto de tokens con unicidad ·
parecido anclado en primer nombre y último apellido— y cuyas sesiones tienen la presidencia
atribuida a OTRO. Ahí el emparejador no pudo encontrarlo porque no existe en el padrón.
"""
import csv, importlib.util, os, re, sys, unicodedata
from collections import Counter, defaultdict
from rapidfuzz import fuzz

csv.field_size_limit(sys.maxsize)
sp = importlib.util.spec_from_file_location(
    "pd", os.path.expanduser("~/.claude/skills/diaries-lib/lib/utils/presidencia_declarada.py"))
pd = importlib.util.module_from_spec(sp)
sp.loader.exec_module(pd)
_N, _N2 = pd._N, pd._N2


def lee(p):
    with open(p, encoding="utf-8") as fh:
        d = csv.Sniffer().sniff(fh.readline(), ";,").delimiter
        fh.seek(0)
        return list(csv.DictReader(fh, delimiter=d))


for iso in sorted(pd.DECLARA):
    I = iso.upper()
    f = lee(f"source/{iso}/standardize/{I}_interventions.csv")
    dep = lee(f"source/{iso}/standardize/{I}_deputies.csv")

    # ── la MISMA cascada de resolución que usa la herramienta ──────────────────────
    porn, subs, nombres = {}, defaultdict(set), []
    for x in dep:
        for c in ("speaker_name", "last_name"):
            v = x.get(c, "").strip()
            if v:
                porn.setdefault(_N(v), x["id_dep"])
                nuc = re.sub(r"\s+(?:de|del)\s+(?:la\s+|los\s+)?\S+$", "", v)
                if nuc != v:
                    porn.setdefault(_N(nuc), x["id_dep"])
        v = x.get("speaker_name", "").strip()
        if v:
            subs[frozenset(t for t in _N2(v).split() if len(t) > 2)].add(x["id_dep"])
            nombres.append((x["id_dep"], _N2(v)))
    corp = defaultdict(set)
    for x in f:
        if x["id_dep"].strip() and x["speaker_raw"].strip():
            corp[_N(re.sub(r",.*$", "", x["speaker_raw"]))].add(x["id_dep"])
    for k, v in corp.items():
        if len(v) == 1:
            porn.setdefault(k, next(iter(v)))

    def resuelve(nom):
        n = porn.get(_N(nom)) or porn.get(_N(re.sub(r"\s+(?:de|del)\s+(?:la\s+)?\S+$", "", nom)))
        if n:
            return n
        ts = frozenset(t for t in _N2(nom).split() if len(t) > 2)
        if len(ts) >= 2:
            h = {i for k, v in subs.items() if ts <= k for i in v}
            if len(h) == 1:
                return next(iter(h))
        q = _N2(nom)
        qt = q.split()
        if len(q) >= 12:
            h = {i for i, v in nombres if fuzz.ratio(q, v) >= 90}
            if not h and len(qt) >= 3:
                h = {i for i, v in nombres if (vt := v.split()) and len(vt) >= 3
                     and vt[0] == qt[0] and vt[-1] == qt[-1] and fuzz.ratio(q, v) >= 80}
            if len(h) == 1:
                return next(iter(h))
        return ""

    rx = pd.DECLARA[iso]
    sinres, ses_sin = Counter(), defaultdict(set)
    for x in f:
        for m in rx.finditer(x["text"]):
            nom = re.sub(r"\s+", " ", next((g for g in m.groups() if g), "")).strip(" .,")
            nom = re.sub(r"(?i)^(?:presiden?[ne]?\s+)?(?:el|la|los)?\s*"
                         r"(?:se(?:ñ|n)or(?:es|a)?\s+)?(?:representantes?\s+)?"
                         r"(?:don|do(?:ñ|n)a)?\s*", "", nom).strip()
            nom = re.sub(r"(?i)^(?:c\.\s*|c\s+|diputad[oa]\s+|dip\.\s*|lic\.\s*|prof\.?\s+|"
                         r"dr\.?\s+|sr\.?\s+|sra\.?\s+)", "", nom).strip()
            if len(nom) > 8 and not resuelve(nom):
                sinres[nom[:40]] += 1
                ses_sin[nom[:40]].add(x["id_session"])
            break

    print(f"\n  ══ {I} · declaraciones sin resolver: {sum(sinres.values()):,} "
          f"en {len(sinres):,} nombres")
    for k, v in sinres.most_common(4):
        # ¿a quién se atribuye la presidencia en SUS sesiones?
        otro = Counter(x["speaker_name"][:30] for x in f
                       if x["id_session"] in ses_sin[k] and x["id_dep"]
                       and pd.CARGO.match(x["speaker_raw"] or ""))
        top = otro.most_common(1)
        print(f"      {k!r:42} ×{v:<4} sesiones {len(ses_sin[k]):>4} → "
              f"presidencia hoy en {top[0][0]!r} ×{top[0][1]:,}" if top else
              f"      {k!r:42} ×{v:<4} (sin presidencia atribuida)")
