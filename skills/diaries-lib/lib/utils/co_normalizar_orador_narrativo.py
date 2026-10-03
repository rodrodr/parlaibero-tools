#!/usr/bin/env python3
"""CO: el `speaker_raw` es una FRASE narrativa, no la identificación de quien habla.

Señalado por el investigador (2026-08-10):

    speaker_raw = «El señor Presidente somete a consideración la proposición»
    speaker_raw = «La Secretaría General informa, doctor Jesús Alfonso Rodríguez C.»
    speaker_raw = «Quiero decir algo»

Son **29.608 filas**. El acta narra quién va a hablar y el etiquetado tomó la narración entera
como nombre del orador. En **24.540** de ellas la frase CONTIENE el nombre de la persona.

## Qué se hace y qué NO

Se normaliza a la convención que **el propio corpus ya usa** en otras 25.246 filas —`Secretario
General, Jorge Humberto Mantilla Serrano`—: se extrae el cargo y el nombre y se descarta el verbo.
El texto de la intervención no se toca.

⚠ **No se inventa la vinculación.** Los nombres extraídos —Jesús Alfonso Rodríguez Camargo, Flor
Marina Daza Ramírez, Angelino Lizcano Rivera, Jorge Humberto Mantilla Serrano…— **no están en
ninguno de los dos padrones de CO** (838 y 1.166 filas). El investigador advierte que en Colombia
los secretarios SÍ son representantes electos, a diferencia de otros países, así que el hueco es
del padrón, no del acta ([[feedback_primacia_del_diario]]). Hace falta una fuente externa con los
Secretarios Generales de la Cámara; hasta entonces `id_dep` se queda vacío y el nombre, al menos,
queda legible y agrupable.

Las frases SIN nombre extraíble —«Quiero decir algo», «El señor Presidente somete a
consideración el Orden del Día»— se dejan intactas: ahí no hay a quién identificar, y sustituirlas
por el cargo sería atribuir sin prueba.

CLI:
    python co_normalizar_orador_narrativo.py [--medir]
"""
import argparse
import csv
import os
import re
import sys
from collections import Counter

csv.field_size_limit(sys.maxsize)
CORPUS = "source/co/standardize/CO_interventions.csv"

NARR = re.compile(r"(?i)\b(?:somete|informa|manifiesta|solicita|pregunta|responde|interviene|"
                  r"anuncia|concede|declara|ordena|dispone|da\s+lectura|abre|cierra|llama)\b")
# el nombre va tras un tratamiento; se admiten de dos a cinco palabras capitalizadas
# ⚠ SIN `re.I`: con él, `[A-ZÁÉÍÓÚÑ]` casa también minúsculas y «señor Presidente somete a
# consideración la» pasaba por nombre propio. El tratamiento se enumera en ambas cajas a mano.
NOMBRE = re.compile(r"\b(?:[Dd]octor[a]?|[Dd]r\.?[a]?|[Ss]e(?:ñ|n)or[a]?)\s+"
                    r"([A-ZÁÉÍÓÚÑ][a-záéíóúñ.]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ.]*){1,4})")
CARGO = re.compile(r"(?i)\b(Secretar[íi]a\s+General|Secretario\s+General|Subsecretar[íi]a\s+General|"
                   r"Subsecretario\s+General|Secretari[oa]|Presidenci[ao]|Presidente)\b")


def normaliza(s: str):
    """Devuelve la forma normalizada, o None si no hay nombre que extraer."""
    if not NARR.search(s) or len(s) < 24:
        return None
    g = NOMBRE.search(s)
    if not g:
        return None
    nombre = re.sub(r"\s+", " ", g.group(1)).strip(" .,")
    # ⚠ El verbo de la narración se cuela al final del nombre —«Rodríguez Camargo. Inf»,
    # «Lizcano Rivera Informa»— y al quedarse con «la variante más larga» se amplificaba.
    nombre = re.sub(r"(?i)[\s.,]+(?:inf(?:orma)?|manifiesta|somete|solicita|pregunta|responde|"
                    r"anuncia|concede|declara|ordena|dispone|abre|cierra|llama)\b.*$", "", nombre)
    nombre = nombre.strip(" .,")
    if len(nombre) < 6:
        return None
    c = CARGO.search(s)
    cargo = _CANON.get(re.sub(r"\s+", " ", c.group(1)).strip().lower(), "") if c else ""
    # el corpus escribe «Secretario General, Nombre»; se respeta esa convención
    return f"{cargo}, {nombre}" if cargo else nombre


# El mismo cargo aparece en femenino, masculino y con/sin «General». Se unifica, porque si no la
# misma persona sale bajo tres cadenas distintas y no se puede agrupar.
_CANON = {
    "secretaría general": "Secretaría General", "secretaria general": "Secretaría General",
    "secretario general": "Secretaría General", "secretario": "Secretaría General",
    "secretaria": "Secretaría General",
    "subsecretaría general": "Subsecretaría General", "subsecretaria general": "Subsecretaría General",
    "subsecretario general": "Subsecretaría General",
    "presidencia": "Presidencia", "presidencio": "Presidencia", "presidente": "Presidencia",
}


def _lee(p):
    with open(p, encoding="utf-8") as fh:
        d = csv.Sniffer().sniff(fh.readline(), ";,").delimiter
        fh.seek(0)
        r = csv.DictReader(fh, delimiter=d)
        return list(r.fieldnames), list(r), d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--medir", action="store_true")
    a = ap.parse_args()
    campos, filas, d = _lee(CORPUS)

    # PRIMERA pasada: para cada persona, quedarse con la variante MÁS COMPLETA de su nombre
    # (clave = primer token + último token con más de dos letras). Sin esto, «Jesús Alfonso
    # Rodríguez», «…Rodríguez C» y «…Rodríguez Camargo» son tres oradores distintos.
    largo = {}
    for x in filas:
        nv = normaliza(x["speaker_raw"].strip())
        if not nv or "," not in nv:
            continue
        cargo, nom = nv.split(",", 1)
        t = [w for w in nom.split() if len(w) > 2]
        if not t:
            continue
        # la clave son los DOS PRIMEROS nombres, que son estables; el último apellido aparece
        # abreviado la mitad de las veces («Rodríguez C» vs «Rodríguez Camargo») y como clave
        # partía a la misma persona en dos.
        clave = (cargo, t[0].lower(), t[1].lower() if len(t) > 1 else "")
        if len(nom) > len(largo.get(clave, "")):
            largo[clave] = nom.strip()

    n = 0
    sin = Counter()
    ejem = []
    personas = Counter()
    for x in filas:
        s = x["speaker_raw"].strip()
        nv = normaliza(s)
        if nv is None:
            if NARR.search(s) and len(s) >= 24:
                sin[s[:52]] += 1
            continue
        if "," in nv:
            cargo, nom = nv.split(",", 1)
            t = [w for w in nom.split() if len(w) > 2]
            if t:
                nv = f"{cargo}, {largo.get((cargo, t[0].lower(), t[1].lower() if len(t) > 1 else ''), nom.strip())}"
        n += 1
        personas[nv] += 1
        if len(ejem) < 5:
            ejem.append((s[:56], nv))
        if not a.medir:
            x["speaker_raw"] = nv
    print(f"  CO · formas narrativas normalizadas: {n:,}")
    print(f"     sin nombre extraíble (se dejan intactas): {sum(sin.values()):,}")
    for s, k in ejem:
        print(f"       {s!r}\n         → {k!r}")
    print("     personas resultantes más frecuentes:")
    for s, k in personas.most_common(6):
        print(f"       {k:>6,}  {s[:56]!r}")
    if a.medir:
        return
    bak = CORPUS.replace(".csv", ".pre_orador.csv")
    tmp = CORPUS + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, delimiter=d)
        w.writeheader()
        w.writerows(filas)
    if not os.path.exists(bak):
        os.rename(CORPUS, bak)
    else:
        os.remove(CORPUS)
    os.rename(tmp, CORPUS)
    print("  ✓ corpus reescrito")


if __name__ == "__main__":
    main()
