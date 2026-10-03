#!/usr/bin/env python3
"""
Post-procesa interventions.csv:
  1. Une los saltos de línea del campo `text` (los reemplaza por espacio).
  2. Extrae todos los textos entre paréntesis (...) y los mueve a una nueva
     columna `comentario` (concatenados con espacio).
  3. Limpia espacios redundantes en `text`.

Uso: python3 split_commentary.py <input.csv> <output.csv>
"""
import csv
import re
import sys
from pathlib import Path

input_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])

PARENS_RE = re.compile(r"\([^)]*\)")
SPACES_RE = re.compile(r"\s+")


def clean_text_and_extract(text: str) -> tuple[str, str]:
    # 1. elimina saltos de línea (también \r)
    flat = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")

    # 2. extrae todos los (...) en orden de aparición
    parens = PARENS_RE.findall(flat)
    comentario = " ".join(p.strip() for p in parens if p.strip())

    # 3. elimina los (...) del text
    cleaned = PARENS_RE.sub(" ", flat)

    # 4. colapsa espacios múltiples y recorta
    cleaned = SPACES_RE.sub(" ", cleaned).strip()

    return cleaned, comentario


with input_path.open() as f:
    reader = csv.reader(f)
    rows = list(reader)

header, data = rows[0], rows[1:]
ti = header.index("text")

n_with_newlines = 0
n_with_parens = 0
n_with_comentario = 0

out_rows = []
for r in data:
    while len(r) < len(header):
        r.append("")
    text = r[ti]
    if "\n" in text:
        n_with_newlines += 1
    if "(" in text:
        n_with_parens += 1
    new_text, comentario = clean_text_and_extract(text)
    if comentario:
        n_with_comentario += 1
    r[ti] = new_text
    r.append(comentario)
    out_rows.append(r)

# añade la columna comentario al header
new_header = header + ["comentario"]

output_path.parent.mkdir(parents=True, exist_ok=True)
with output_path.open("w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(new_header)
    writer.writerows(out_rows)

print(f"input:                {len(data)} filas")
print(f"  con saltos de línea:  {n_with_newlines}")
print(f"  con paréntesis:        {n_with_parens}")
print(f"output:               {len(out_rows)} filas")
print(f"  con comentario no vacío: {n_with_comentario}")
print(f"  columnas:               {len(new_header)} (era {len(header)})")
print(f"output_path:          {output_path}")
