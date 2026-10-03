#!/usr/bin/env python3
"""
Une líneas que son partes de un nombre de personaje roto por salto de línea.

Detecta 3 patrones:
  A) A: "DON"  +  B: "SACRAMENTO. ..."
     → une A+B como "DON SACRAMENTO. ..."

  B) A: "DON"  +  B: "(acotación...)"  +  C: "SACRAMENTO. ..."
     → salta B (acotación) y une A+C

  C) A: "DON"  +  B: "(acotación...)"
     → A queda como está (no hay speaker que seguir; caso degenerado)

A: una sola palabra en mayúsculas, 3-15 chars, SIN terminador
B: una sola palabra en mayúsculas, 3-15 chars, CON `.` + espacio (es un speaker)
C: empieza con `(`  (acotación / stage direction)
"""
import re
import sys
from pathlib import Path

src = Path(sys.argv[1])
dst = Path(sys.argv[2])

text = src.read_text()
lines = text.split("\n")

# Patrones
A = re.compile(r"^[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ]{2,14}$")              # palabra sola, sin terminador
B = re.compile(r"^[A-ZÁÉÍÓÚÜÑ][A-ZÁÉÍÓÚÜÑ]{2,14}\.\s")             # speaker: palabra + ". "
C = re.compile(r"^\s*\(.*\)\s*$")                                   # acotación en una sola línea

merged = 0
i = 0
out = []
while i < len(lines):
    line = lines[i]
    if A.match(line):
        # buscar la siguiente línea con contenido
        j = i + 1
        # saltar acotaciones de una línea
        while j < len(lines) and (lines[j].strip() == "" or C.match(lines[j])):
            j += 1
        if j < len(lines) and B.match(lines[j]):
            # une A + línea j (que es el speaker real)
            out.append(f"{line} {lines[j]}")
            i = j + 1
            merged += 1
            continue
    out.append(line)
    i += 1

dst.write_text("\n".join(out))
print(f"líneas unidas: {merged}")
