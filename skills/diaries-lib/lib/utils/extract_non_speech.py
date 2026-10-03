#!/usr/bin/env python3
"""Separa a un sidecar reversible las filas que NO son intervenciones.

Punto 2 del protocolo de revisión. Primer caso tratado: `Sumario` como falso
orador, defecto transversal presente en tres corpus. No es una persona: es la
sección de sumario/índice del diario promovida a orador por el segmentador.

Comprobado antes de mover (ninguna de las tres lleva `id_dep`):
  · SV — 390 filas: «ÍNDICE / Pág. / - Ingreso de la Honorable Asamblea…»
  · ES — 3.433 filas: «SUMARIO Se abre la sesión…», sinopsis redactada por la
         edición del diario, no dicha en sala (mediana 11.352 caracteres)
  · BR — 6.921 filas: «DEPARTAMENTO DE TAQUIGRAFIA REVISÃO E REDAÇÃO SESSÃO:…»

Las filas se conservan íntegras en `{ISO2}_sidecar_no_discurso.csv`, de modo que
la operación es reversible y el material sigue disponible para quien lo quiera.

Uso:  python3 extraer_no_discurso.py {iso2} [--apply]
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

import pandas as pd

# speaker_raw que no son personas, por país (comparación normalizada)
NO_DISCURSO = {
    "sv": ["sumario"],
    "es": ["sumario"],
    "br": ["sumario"],
}

# Chile trae la clasificación hecha en la columna `tipo` del sidecar: las filas
# `voto_*` son pases de lista de votación nominal, no intervenciones (0% llevan
# id_dep). Se extraen por esa vía, no por `speaker_raw`.
POR_TIPO = {"cl": ("CL_tipo_source_sidecar.csv", ("voto_afavor", "voto_encontra", "voto_abstencion"))}

# Guarda: una fila de voto puede llevar DENTRO una intervención real
# ("…se abstuvieron. El señor COLOMA (Vicepresidente).- Si el resultado es el
# indicado, no habría quórum…"). Medido en CL: 777 de 54.792 filas (1,4%) con
# 1.608 marcadores. Esas NO se mueven: necesitan la recuperación de marcadores
# incrustados, que es otra operación.
MARCADOR_CL = re.compile(
    r"(?:El|La)\s+(?:señor|señora|señorita)\s+[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s]{2,}\s*\([^)]{0,40}\)\s*\.?-")


def main(iso2: str, apply: bool) -> None:
    csv = Path(f"source/{iso2}/standardize/{iso2.upper()}_interventions.csv")
    bak = csv.with_name(f"{iso2.upper()}_interventions.pre_nodiscurso.csv")
    side = csv.with_name(f"{iso2.upper()}_sidecar_no_discurso.csv")

    sep = ";" if csv.open(encoding="utf-8", errors="replace").readline().count(";") > 1 else ","
    df = pd.read_csv(csv, sep=sep, dtype=str, keep_default_na=False)
    n0 = len(df)

    objetivo = NO_DISCURSO.get(iso2, [])
    extra_side = None

    if iso2 in POR_TIPO:
        fichero, tipos = POR_TIPO[iso2]
        extra_side = csv.with_name(fichero)
        tp = pd.read_csv(extra_side, dtype=str, keep_default_na=False)
        assert len(tp) == len(df), "canónico y sidecar de tipo desalineados"
        m = tp["tipo"].isin(tipos).values
        con_marcador = df.text.map(lambda t: bool(MARCADOR_CL.search(t))).values
        n_prot = int((m & con_marcador).sum())
        print(f"[{iso2}] filas de tipo {tipos}: {int(m.sum()):,} · "
              f"protegidas por llevar intervención incrustada: {n_prot:,}")
        m = pd.Series(m & ~con_marcador, index=df.index)
    elif objetivo:
        m = df.speaker_raw.str.strip().str.lower().isin(objetivo)
    else:
        print(f"[{iso2}] sin clases declaradas — nada que hacer")
        return

    sel = df[m]
    print(f"[{iso2}] {n0:,} filas · a sidecar: {len(sel):,} ({100*len(sel)/n0:.2f}%)")

    # Idempotencia: si no hay nada que mover pero ya existe un sidecar con
    # contenido, el trabajo está hecho — salir sin escribir. Sin esta guarda una
    # segunda ejecución sobrescribía el sidecar con un archivo vacío y se perdía
    # el registro de lo extraído (ocurrió en BR: 6.921 filas, recuperadas del
    # respaldo).
    side_existente = side.exists() and side.stat().st_size > 200
    if len(sel) == 0:
        print("   ya aplicado" if side_existente else "   nada que mover")
        return
    if len(sel):
        con_id = int((sel.id_dep.str.strip() != "").sum())
        print(f"   con id_dep: {con_id}  {'⚠ REVISAR' if con_id else '(ninguna, como se esperaba)'}")
        print(f"   caracteres retirados: {int(sel.text.str.len().sum()):,} "
              f"({100*sel.text.str.len().sum()/df.text.str.len().sum():.2f}% del texto)")
        print(f"   valores de speaker_raw: {sel.speaker_raw.value_counts().to_dict()}")
        if con_id:
            sys.exit("ABORTA: hay filas con id_dep; no son ruido de segmentación")

    if not apply:
        print("   --- SIMULACIÓN (sin --apply no se escribe nada) ---")
        return

    if not bak.exists():
        shutil.copy2(csv, bak)
        print(f"   copia de seguridad → {bak.name}")
    sel.to_csv(side, index=False, encoding="utf-8")
    out = df[~m]
    out.to_csv(csv, index=False, encoding="utf-8", sep=sep)
    if extra_side is not None:   # el sidecar de `tipo` va fila a fila: recortarlo igual
        tp = pd.read_csv(extra_side, dtype=str, keep_default_na=False)
        tp[~m.values].to_csv(extra_side, index=False, encoding="utf-8")

    chk = pd.read_csv(csv, sep=sep, dtype=str, keep_default_na=False)
    assert len(chk) == n0 - len(sel), "recuento inconsistente"
    if objetivo and iso2 not in POR_TIPO:
        assert not chk.speaker_raw.str.strip().str.lower().isin(objetivo).any(), "quedan residuos"
    print(f"   ✓ {len(chk):,} filas ({n0:,} − {len(sel):,}) · sidecar {side.name}")


if __name__ == "__main__":
    main(sys.argv[1], "--apply" in sys.argv)
