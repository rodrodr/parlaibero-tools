#!/usr/bin/env python3
"""Recorta la carátula de CL donde empieza a repetir la primera intervención de la sesión.

`fix_prolegomena` compara el turno ENTERO y por eso solo veía 26 casos: aquí la carátula arrastra
el turno de apertura ya partido en dos filas —orden 1 «se abre la sesión» y orden 2 «el acta…»—
así que ningún turno coincide del todo. El ancla que sí funciona es el ARRANQUE: se busca dentro
de la carátula el marcador seguido de los primeros caracteres de la orden 1, y se corta ahí.

⚠ No se recupera nada: lo que se recorta YA está en el corpus como orden 1. Si no lo estuviera,
cortar perdería texto, así que el corte exige la coincidencia.
"""
import csv, os, re, sys, unicodedata
csv.field_size_limit(sys.maxsize)
MARC = re.compile(r"(?m)(?:^[ \t]*|(?<=[.!?»\"’_])[ \t]*)(?:El|La)\s+se(?:ñ|n)or(?:a|ita)?\s+"
                  r"[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑa-záéíóúñ'’\-~_ ]{2,40}?"
                  r"(?:,\s*do(?:n|ña)\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?"
                  r"(?:\s*\([^)\n]{0,44}\))?\s*[.,]?\s*[-–—~_](?=\s)")

def N(s):
    s = "".join(c for c in unicodedata.normalize("NFD", s.upper()) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Z0-9]+", "", s)

p = "source/cl/standardize/CL_interventions.csv"
with open(p, encoding="utf-8") as fh:
    d = csv.Sniffer().sniff(fh.readline(), ";,").delimiter; fh.seek(0)
    r = csv.DictReader(fh, delimiter=d); campos = r.fieldnames; filas = list(r)
prim = {}
for x in filas:
    if x["intervention_order"] == "1":
        prim[x["id_session"]] = x["text"]
corta = 0; quitado = 0
for x in filas:
    if x["intervention_order"] != "0":
        continue
    t = x["text"]; ini = prim.get(x["id_session"])
    if not ini:
        continue
    firma = N(ini)[:40]
    if len(firma) < 20:
        continue
    for m in MARC.finditer(t):
        if N(t[m.end():m.end() + 260])[:40] == firma:
            quitado += len(t) - m.start(); x["text"] = t[:m.start()].rstrip(); corta += 1
            break
print(f"  CL · carátulas recortadas: {corta:,} · caracteres retirados: {quitado:,}")
if "--medir" in sys.argv:
    sys.exit()
bak = p.replace(".csv", ".pre_recorte.csv"); tmp = p + ".tmp"
with open(tmp, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=campos, delimiter=d); w.writeheader(); w.writerows(filas)
if not os.path.exists(bak):
    os.rename(p, bak)
else:
    os.remove(p)
os.rename(tmp, p)
print("  ✓ corpus reescrito")
