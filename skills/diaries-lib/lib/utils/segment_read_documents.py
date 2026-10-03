#!/usr/bin/env python3
"""Separa a un sidecar los documentos LEÍDOS EN SALA que están dentro del `text`.

Las actas incorporan al cuerpo de la intervención el texto íntegro de lo que se lee: leyes,
dictámenes, decretos, exposiciones de motivos, anexos. No es discurso, y deja el corpus
inservible para estilometría o análisis de discurso: en MX eran **583,6 M de caracteres**,
en UY **149,5 M** —con una sola fila de 7,4 M atribuida a `PRESIDENTE`— y en GT bajó el texto
de 233,9 M a 185,4 M.

Tres modos de reconocer el documento, porque cada cámara lo marca distinto:

    read_documents:
      mode: delimiters | block | headings
      # delimiters — la fuente los marca explícitamente (MX: «…»)
      delimiters: ['«', '»']
      # block — fórmula de apertura … fórmula de cierre (GT: decretos)
      opening: 'EL CONGRESO DE LA REPÚBLICA .{0,80} CONSIDERANDO'
      closing:  'PASE AL ORGANISMO EJECUTIVO'
      # headings — encabezados de línea, con rachas (UY, GT upstream)
      headings: ['PROYECTO DE LEY', 'EXPOSICIÓN DE MOTIVOS', 'CONSIDERANDO']
      min_block: 3000            # rachas más cortas se dejan en su sitio
      row_min_chars: 10000       # opcional: solo filas por encima de este tamaño
      orality_signals: [...]     # OBLIGATORIO — ver abajo
      orality_per_1k: 0.35       # DENSIDAD máxima de señales por cada 1.000 caracteres

⚠ **El umbral de densidad NO tiene un valor universal, y hay que fijarlo por país con
`--sample`.** Medido en MX sobre su estado previo a la segmentación, barriendo el umbral:
0,10 extrae el 83% de lo que extrajo la pasada original · 0,20 el 104% · 0,35 el 122% ·
1,00 el 140%. No se elige ajustando a la cifra del original —esa pasada dejó 13.382 filas
con documento sin extraer—, sino mirando qué entra y qué sale en cada tramo. El 0.35 por
defecto es un punto de partida, no una recomendación.

⚠ **El contrapeso se mide por DENSIDAD, no por ocurrencias absolutas.** Un texto legal de
30.000 caracteres dice «nuestro» inevitablemente; una intervención de 800 que lo diga tres
veces es habla. Con umbral absoluto de 0, en MX quedaban vetados documentos inequívocos
—«Iniciativa que reforma los artículos 1, 103 y 107 de la Constitución…»— por una sola
aparición en 33.000 caracteres, y solo se extraía el 40% de lo que debía.

⚠⚠ **El contrapeso no es opcional, y es lo único que impide un destrozo.** La
primera versión del segmentador de UY iba a extraer el **45,91% del corpus** con un control
que marcaba «0,00%» de riesgo, porque el control compartía léxico con el detector. Lo
desmintió mirar una muestra ALEATORIA de lo que se iba a descartar. Un bloque que contiene
interrogaciones, segunda persona, muletillas o fórmulas de sala **es discurso**, por mucho
que empiece con un encabezado de documento.

⚠ **Nada se borra: se mueve.** Las filas o bloques van a `{ISO2}_sidecar_documentos.csv`,
reasociables por `date` + `session_number` + `intervention_order`. Cuando el documento ocupa
la fila entera, la fila se aparta completa; cuando está dentro, se recorta del `text` y el
resto de la intervención se queda.

Uso:
    python3 segment_read_documents.py --country mx --sample 20    # OBLIGATORIO primero
    python3 segment_read_documents.py --country mx                # simulación con recuento
    python3 segment_read_documents.py --country mx --apply
"""
from __future__ import annotations

import argparse
import random
import re
import shutil
from pathlib import Path

import pandas as pd

try:
    import yaml
except ImportError:                                    # pragma: no cover
    yaml = None

# Señales de que un bloque es HABLA, no documento. Se usan como contrapeso: si aparecen
# dentro del bloque candidato, no se extrae. Deben ser INDEPENDIENTES del léxico que
# detecta el documento (validation_methodology §4.4).
ORALIDAD_POR_DEFECTO = [
    r"[¿?]",                                             # interrogación
    r"\b(?:usted(?:es)?|su\s+se[ñn]or[íi]a)\b",          # segunda persona
    r"\b(?:o sea|es decir|por ejemplo|fíjese|mire)\b",   # muletillas
    r"\b(?:muchas gracias|tiene la palabra|se va a votar)\b",   # fórmulas de sala
    r"\b(?:creo|pienso|quiero|quisiera|nuestro|nuestra|me parece)\b",  # subjetividad
]


def cargar_config(iso2: str) -> dict:
    p = Path(f"country_config/{iso2}.yaml")
    if not p.exists() or yaml is None:
        return {}
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("read_documents") or {}


def compilar(cfg: dict):
    """→ (buscador_de_bloques, patrón_de_oralidad)"""
    modo = cfg.get("mode", "headings")
    if modo == "delimiters":
        a, b = cfg.get("delimiters", ["«", "»"])
        pat = re.compile(re.escape(a) + r"(.*?)" + re.escape(b), re.S)
    elif modo == "block":
        pat = re.compile(rf"(?:{cfg['opening']}).{{{int(cfg.get('min_block', 500))},}}?"
                         rf"(?:{cfg['closing']})", re.I | re.S)
    else:
        enc = "|".join(cfg.get("headings", []))
        # el encabezado debe SER la línea, no aparecer dentro de ella
        pat = re.compile(rf"(?m)^\s*(?:{enc})\s*:?\s*$")
    señales = cfg.get("orality_signals") or ORALIDAD_POR_DEFECTO
    return modo, pat, re.compile("|".join(señales), re.I)


def densidad_oral(bloque: str, oral: re.Pattern) -> float:
    """Señales de habla por cada 1.000 caracteres del bloque."""
    n = len(bloque)
    return 1e9 if n == 0 else 1000 * len(oral.findall(bloque)) / n


def bloques(texto: str, modo: str, pat: re.Pattern, cfg: dict):
    """→ [(inicio, fin)] de los tramos candidatos a documento."""
    mn = int(cfg.get("min_block", 200))
    if modo in ("delimiters", "block"):
        return [(m.start(), m.end()) for m in pat.finditer(texto)
                if m.end() - m.start() >= mn]
    # headings: desde cada encabezado hasta el siguiente, si la racha es larga
    ms = list(pat.finditer(texto))
    out = []
    for i, m in enumerate(ms):
        fin = ms[i + 1].start() if i + 1 < len(ms) else len(texto)
        if fin - m.start() >= mn:
            out.append((m.start(), fin))
    # fusiona tramos contiguos
    fus = []
    for a, b in out:
        if fus and a - fus[-1][1] < 200:
            fus[-1] = (fus[-1][0], b)
        else:
            fus.append((a, b))
    return fus


def analizar(d: pd.DataFrame, cfg: dict):
    """→ {indice: [(ini, fin)]} de lo que se extraería, tras el contrapeso."""
    modo, pat, oral = compilar(cfg)
    rmin = int(cfg.get("row_min_chars", 0))
    dmax = float(cfg.get("orality_per_1k", 0.35))
    out, descartados = {}, 0
    for i, t in zip(d.index, d.text):
        t = str(t)
        if len(t) < rmin:
            continue
        bs = bloques(t, modo, pat, cfg)
        buenos = []
        for a, b in bs:
            if densidad_oral(t[a:b], oral) > dmax:
                descartados += 1        # densidad de habla: NO es documento
                continue
            buenos.append((a, b))
        if buenos:
            out[i] = buenos
    return out, descartados


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--seed", type=int, default=20260801)
    a = ap.parse_args()
    c = a.country.lower()

    cfg = cargar_config(c)
    if not cfg:
        raise SystemExit(f"✗ {c}: falta el bloque `read_documents:` en country_config/{c}.yaml")

    csv = Path(f"source/{c}/standardize/{c.upper()}_interventions.csv")
    d = pd.read_csv(csv, dtype=str, keep_default_na=False)
    tot = d.text.str.len().sum()
    marcas, desc = analizar(d, cfg)
    car = sum(b - a_ for v in marcas.values() for a_, b in v)
    enteras = sum(1 for i, v in marcas.items()
                  if sum(b - a_ for a_, b in v) > 0.9 * len(str(d.at[i, "text"])))

    print(f"{c.upper()} · {len(d):,} filas · modo {cfg.get('mode')}")
    print(f"  filas con documento    : {len(marcas):,} ({100*len(marcas)/len(d):.2f}%)")
    print(f"  de ellas, fila ENTERA  : {enteras:,}")
    print(f"  caracteres a apartar   : {car/1e6:.1f} M de {tot/1e6:.1f} M ({100*car/tot:.1f}%)")
    print(f"  bloques descartados por contener habla: {desc:,}  ← contrapeso")

    if a.sample:
        random.seed(a.seed)
        ks = random.sample(sorted(marcas), min(a.sample, len(marcas)))
        print(f"\n─── MUESTRA ALEATORIA de {len(ks)} · confírmala ANTES de --apply ───")
        for k in ks:
            t = str(d.at[k, "text"])
            a_, b = marcas[k][0]
            print(f"\n[{d.at[k,'date']} · {d.at[k,'speaker_raw'][:30]!r} · fila {len(t):,} car.]")
            print(f"   se aparta: {t[a_:a_+190].replace(chr(10),' ')}…")
            resto = (t[:a_] + t[b:]).strip()
            print(f"   se queda : {(resto[:150] or '(nada — la fila entera es documento)')}")
        return

    if not a.apply:
        print("\n--- SIMULACIÓN --- (ejecuta antes --sample y confirma)")
        return

    side, filas = [], []
    for i, r in d.iterrows():
        if i not in marcas:
            filas.append(r.to_dict())
            continue
        t = str(r.text)
        trozos = "".join(t[a_:b] for a_, b in marcas[i])
        resto = t
        for a_, b in sorted(marcas[i], reverse=True):
            resto = resto[:a_] + resto[b:]
        resto = re.sub(r"\s{2,}", " ", resto).strip()
        s = r.to_dict()
        s["text"] = trozos
        side.append(s)
        if resto:
            x = r.to_dict()
            x["text"] = resto
            filas.append(x)

    out = pd.DataFrame(filas)
    sd = pd.DataFrame(side)
    sp = Path(f"source/{c}/standardize/{c.upper()}_sidecar_documentos.csv")
    if sp.exists():
        raise SystemExit(f"✗ {sp.name} ya existe — revisar antes de sobrescribir")
    bak = csv.with_name(csv.stem + ".pre_documentos.csv")
    if not bak.exists():
        shutil.copy2(csv, bak)
        print(f"  copia de seguridad → {bak.name}")
    sd.to_csv(sp, index=False, encoding="utf-8")
    out.to_csv(csv, index=False, encoding="utf-8")
    chk = pd.read_csv(csv, dtype=str, keep_default_na=False, usecols=["text"])
    print(f"✓ matriz {len(chk):,} filas ({len(d)-len(chk):,} apartadas enteras) · "
          f"sidecar {len(sd):,} bloques · texto {chk.text.str.len().sum()/1e6:.1f} M car.")


if __name__ == "__main__":
    main()
