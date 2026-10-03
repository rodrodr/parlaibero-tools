#!/usr/bin/env python3
"""DESCUBRE las formas de marcador de orador de un país, sin asumir ningún vocabulario.

**Por qué existe.** El método anterior era adivinar una lista de palabras de rol —DIPUTADO,
SEÑOR, PRESIDENTE…— y contar cuántas veces aparecía cada una. Ese método falló tres veces
seguidas y siempre en la misma dirección:

  · **SV**: se muestrearon 40 archivos, todos del tramo 2018+, y se perdió `REP. NOMBRE:`,
    la forma de 2014. Un año entero sin etiquetar.
  · **GT**: la lista adivinada no incluía `EL R.` —Representante—, que es la forma DOMINANTE:
    204.356 apariciones. El sondeo devolvió 14.255 marcadores para un corpus de 251.777 filas
    y llevó a concluir, en falso, que los PDF no marcaban oradores.
  · **GT otra vez**: encontrado `EL R.`, faltaba `LA R.` (27.354, el 11,8%). Un patrón solo
    masculino **borra a las mujeres que presiden y ejercen la secretaría**.

Aquí no se adivina nada: se buscan **encabezamientos por su FORMA** —línea que empieza en
mayúscula, es corta, termina en `:` o `.` y va seguida de prosa— y se agrupan por su
esqueleto. Lo que domina el ranking ES la convención del país, se llame como se llame.

⚠ **Siempre POR AÑO.** Las cámaras cambian de convención con la época, y una muestra de
conveniencia esconde el cambio.

⚠ **Siempre buscando la PAREJA DE GÉNERO.** Por cada forma masculina hallada se busca su
femenina (EL/LA, DIPUTADO/DIPUTADA, SEÑOR/SEÑORA, PRIMER/PRIMERA…) y se avisa si falta o si
aparece muchísimo menos: es el error que más daño hace y el más fácil de no ver.

Uso:
    python3 discover_speaker_patterns.py --country gt
    python3 discover_speaker_patterns.py --country gt --from extracted --top 25
"""
from __future__ import annotations

import argparse
import glob
import os
import re
from collections import Counter, defaultdict

# Encabezamiento CANDIDATO por su forma: inicio de línea, empieza en mayúscula, corto,
# termina en `:` o `.`, y va seguido de algo. Sin ninguna palabra concreta.
CAND = re.compile(r"(?m)^[ \t]*([A-ZÁÉÍÓÚÑÜ][^\n]{2,88}?)\s*([.:])(?=\s)")

# El esqueleto sustituye los NOMBRES por un hueco y CONSERVA las palabras de rol, para que
# «EL R. SECRETARIO HERRERA QUEZADA:» y «EL R. SECRETARIO GARCIA Y GARCIA:» caigan juntas
# SIN perder la palabra «SECRETARIO», que es lo que define la familia.
#
# ⚠ Rol y nombre se distinguen POR FRECUENCIA, no por vocabulario: una palabra de rol aparece
# en miles de cabeceras distintas y un apellido en unas pocas. Sustituir todas las versales
# —como hacía la primera versión— borraba «SEÑOR MINISTRO DE …» y dejaba «EL «N» «N» DE «N»»,
# con lo que las 24.027 intervenciones de ministros e invitados de GT se dispersaban en tantos
# esqueletos como carteras y no aparecían en el ranking. Fue el segundo fallo de exhaustividad
# de la misma sesión, y del mismo tipo que el primero.
def construir_esqueleto(frecuencias: Counter, umbral: int):
    def esqueleto(s: str) -> str:
        out = []
        for tok in re.split(r"(\s+)", s):
            if not tok.strip():
                out.append(tok); continue
            limpio = re.sub(r"[^A-ZÁÉÍÓÚÑÜa-záéíóúñü]", "", tok)
            if not limpio:
                out.append(re.sub(r"\d+", "#", tok)); continue
            if limpio.isupper() and len(limpio) > 2 and frecuencias[limpio.upper()] < umbral:
                out.append(tok.replace(limpio, "«N»"))
            elif limpio[:1].isupper() and not limpio.isupper() and frecuencias[limpio.upper()] < umbral:
                out.append(tok.replace(limpio, "«n»"))
            else:
                out.append(re.sub(r"\d+", "#", tok))
        return re.sub(r"\s+", " ", "".join(out)).strip()
    return esqueleto


PAREJAS = [("EL ", "LA "), ("DIPUTADO", "DIPUTADA"), ("SEÑOR", "SEÑORA"),
           ("PRESIDENTE", "PRESIDENTA"), ("SECRETARIO", "SECRETARIA"),
           ("PRIMER ", "PRIMERA "), ("DIPUTADOS", "DIPUTADAS"),
           ("VICEPRESIDENTE", "VICEPRESIDENTA"), ("LICENCIADO", "LICENCIADA")]


def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument("--country", required=True)
    a.add_argument("--from", dest="carpeta", default="extracted")
    a.add_argument("--top", type=int, default=20)
    o = a.parse_args()
    c = o.country.lower()

    fs = sorted(glob.glob(f"source/{c}/{o.carpeta}/**/*.txt", recursive=True))
    if not fs:
        raise SystemExit(f"✗ sin textos en source/{c}/{o.carpeta}/")

    # 1ª pasada · frecuencia de cada palabra entre cabeceras DISTINTAS, para separar rol de nombre
    frec: Counter = Counter()
    for f in fs:
        t_ = open(f, encoding="utf-8", errors="replace").read()
        for m in CAND.finditer(t_):
            for w in set(re.findall(r"[A-ZÁÉÍÓÚÑÜa-záéíóúñü]{3,}", m.group(1))):
                frec[w.upper()] += 1
    umbral = max(50, int(0.002 * sum(frec.values()) / max(len(frec), 1) * 100))
    esqueleto = construir_esqueleto(frec, umbral)
    print(f"  (rol vs nombre: palabra en ≥{umbral:,} cabeceras = ROL; menos = nombre)")

    total = Counter()
    por_anio: dict = defaultdict(Counter)
    ejemplo: dict = {}
    for f in fs:
        anio = next((x for x in re.findall(r"(?<!\d)(\d{4})(?!\d)", os.path.basename(f))
                     if 1800 <= int(x) <= 2100), "s/año")
        t = open(f, encoding="utf-8", errors="replace").read()
        for m in CAND.finditer(t):
            cuerpo = m.group(1).strip()
            if len(cuerpo.split()) > 12:
                continue
            k = esqueleto(cuerpo) + m.group(2)
            total[k] += 1
            por_anio[anio][k] += 1
            ejemplo.setdefault(k, cuerpo[:64])

    n = sum(total.values())
    print(f"{c.upper()} · {len(fs):,} documentos · {n:,} encabezamientos candidatos\n")
    print(f"{'veces':>9}  {'%':>5}  esqueleto")
    top = total.most_common(o.top)
    for k, v in top:
        print(f"{v:>9,}  {100*v/n:>4.1f}%  {k[:62]:64} ej: {ejemplo[k][:40]!r}")

    # ⚠ Agrupar SOLO por esqueleto completo dispersa las familias: en GT, «EL SEÑOR MINISTRO
    # DE SALUD PUBLICA Y ASISTENCIA SOCIAL, INGENIERO SOSA RAMIREZ:» y «EL SEÑOR MINISTRO DE
    # GOBERNACION, DOCTOR JIMENEZ IRUNGARAY:» son la MISMA convención y caen en esqueletos
    # distintos porque cada cartera es distinta. Sumadas por prefijo pesan 24.027 filas; por
    # separado no entran en el top-20 y se dan por inexistentes. Fue el segundo fallo de
    # exhaustividad de la misma sesión.
    print("\n⚠ POR PREFIJO — las variantes de una misma familia SUMADAS:")
    pref: Counter = Counter()
    for k, v in total.items():
        pal = k.split()
        for n_ in (4, 3, 2):
            if len(pal) >= n_:
                pref[" ".join(pal[:n_])] += v
                break
    for k, v in pref.most_common(12):
        print(f"   {v:>9,}  {100*v/n:>4.1f}%  {k[:64]}")

    print("\n⚠ COMPROBACIÓN DE GÉNERO — por cada forma, su pareja femenina:")
    avisos = 0
    for k, v in top:
        for m_, f_ in PAREJAS:
            if m_ in k:
                par = k.replace(m_, f_)
                w = total.get(par, 0)
                if w == 0:
                    print(f"   ✗ {k[:46]:48} {v:>8,}  →  «{f_.strip()}» NO APARECE")
                    avisos += 1
                elif w < 0.02 * v:
                    print(f"   ⚠ {k[:46]:48} {v:>8,}  →  femenina {w:,} ({100*w/v:.1f}%)")
                    avisos += 1
                else:
                    print(f"   ✓ {k[:46]:48} {v:>8,}  →  femenina {w:,} ({100*w/v:.1f}%)")
                break
    if not avisos:
        print("   (sin avisos)")

    print("\n⚠ POR AÑO — la forma dominante de cada periodo (el cambio de convención se ve aquí):")
    for anio in sorted(por_anio):
        cc = por_anio[anio]
        if not cc:
            continue
        k, v = cc.most_common(1)[0]
        print(f"   {anio}  {sum(cc.values()):>8,}  dominante: {k[:56]}")

    print("\n→ Copia al `country_config` las formas que sean marcador de turno, con su pareja "
          "femenina,\n  y comprueba que el total cubre una fracción razonable del corpus. "
          "Lo que domina ESTE\n  ranking es la convención del país: no hay que adivinarla.")


if __name__ == "__main__":
    main()
