#!/usr/bin/env python3
"""
Filtra el CSV de intervenciones para mantener solo los speakers en la whitelist
del config. Aplica también a intervenciones en blanco (sin speaker).

Uso: python3 filter_whitelisted_speakers.py <config.yaml> <input.csv> <output.csv>
"""
import csv
import sys
from pathlib import Path
import yaml

config_path = Path(sys.argv[1])
input_path = Path(sys.argv[2])
output_path = Path(sys.argv[3])

config = yaml.safe_load(config_path.read_text())
speakers_cfg = config.get("speakers", {})
whitelist = set(speakers_cfg.get("whitelist", []))
filter_enabled = speakers_cfg.get("filter", False)

if not filter_enabled or not whitelist:
    print("filter: SKIP (whitelist vacía o filter=false)")
    # copia el archivo tal cual
    output_path.write_text(input_path.read_text())
    sys.exit(0)

with input_path.open() as f:
    reader = csv.reader(f, delimiter=";")
    rows = list(reader)
header, data = rows[0], rows[1:]

# Localiza el índice de la columna speaker_raw (6ª columna según esquema canónico)
speaker_idx = header.index("speaker_raw") if "speaker_raw" in header else 5

# Aplica whitelist
filtered = [r for r in data if r[speaker_idx] in whitelist]
removed = len(data) - len(filtered)

with output_path.open("w", newline="") as f:
    writer = csv.writer(f, delimiter=";")
    writer.writerow(header)
    writer.writerows(filtered)

print(f"input:    {len(data)} intervenciones")
print(f"output:   {len(filtered)} intervenciones")
print(f"removed:  {removed} (speakers no whitelisteados)")
