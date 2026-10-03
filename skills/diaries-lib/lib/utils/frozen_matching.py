#!/usr/bin/env python3
"""Congela la vinculación revisada a mano y la impone sobre cualquier re-ejecución de match.

**El problema que resuelve.** Las `matching_table.csv` acumulan **106.938 decisiones** de
`speaker_raw → id_dep` en 13 países (EC 24.075 · PA 15.766 · PT 12.754 · CO 12.486 · MX 10.706 ·
PY 7.142 · ES 7.171 · UY 5.727 · AR 4.906 · DO 2.357 · CR 2.313 · GT 1.190 · SV 345; verificado
2026-08-23; br/cl/pe sin tabla), muchas revisadas por el investigador. Y
**ninguna columna indica cuáles**: la revisión se hizo sin tocar `match_method`, así que hoy es
indistinguible de lo automático. Si un reproceso regenera la tabla, el trabajo desaparece sin
dejar rastro y sin que nada lo delate.

**Por eso se congela TODA la tabla, no solo lo revisado.** No se puede separar lo uno de lo
otro, y ante esa duda la única opción segura es tratar cada fila existente como decisión humana.

    --freeze   copia la tabla actual a `matching_table.frozen.csv` + manifiesto sha256.
               NUNCA sobrescribe: si ya existe, se niega.
    --check    contrasta la tabla actual contra la congelada, sin escribir nada.
    --apply    impone las decisiones congeladas sobre la tabla actual.

⚠ **`speaker_raw` se casa EXACTAMENTE como está**, con sus tildes y su caja. Normalizar la
clave parece inofensivo y no lo es: en `split_embedded_markers` se destildaba el vocabulario
pero no el texto, y el resultado no fue fallar sino **acertar a medias**, produciendo oradores
mutilados con un recuento que parecía razonable.

⚠ **Una entrada congelada que ya no aparece en el corpus nuevo NO se borra: se informa.**
Significa que la extracción cambió esa forma, y por tanto que hay una decisión humana que
habrá que rehacer sobre la forma nueva. Borrarla en silencio es perder justo lo que se quería
proteger.

⚠ **La cola es lo frágil.** Entre el 42% y el 61% de las formas de `speaker_raw` aparecen una
sola vez (UY 42%, CO 56%, PA 61%), mientras las 500 más frecuentes cubren el 85-91% de las
intervenciones. El grueso del corpus sobrevive a un reproceso casi con seguridad; la cola —que
es donde están las decisiones difíciles— es lo primero que cambia al mejorar la extracción.

Uso:
    python3 frozen_matching.py --country pa --freeze
    python3 frozen_matching.py --country pa --check
    python3 frozen_matching.py --country pa --apply
    python3 frozen_matching.py --all --freeze
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import date
from pathlib import Path

import pandas as pd

PAISES = "ar br cl co cr do ec es gt mx pa pe pt py sv uy".split()


def ruta(iso2: str) -> Path:
    return Path(f"source/{iso2}/match/matching_table.csv")


def congelada(iso2: str) -> Path:
    return Path(f"source/{iso2}/match/matching_table.frozen.csv")


def sep_de(p: Path) -> str:
    h = p.open(encoding="utf-8", errors="replace").readline()
    return ";" if h.count(";") > h.count(",") else ","


def leer(p: Path) -> tuple[pd.DataFrame, str]:
    s = sep_de(p)
    return pd.read_csv(p, sep=s, dtype=str, keep_default_na=False), s


def sha256(p: Path) -> str:
    x = hashlib.sha256()
    with p.open("rb") as f:
        while (b := f.read(1 << 20)):
            x.update(b)
    return x.hexdigest()


def freeze(c: str) -> None:
    p, q = ruta(c), congelada(c)
    if not p.exists():
        print(f"  {c.upper()}: sin matching_table — nada que congelar")
        return
    if q.exists():
        print(f"  {c.upper()}: ✗ ya congelada ({q.name}) — NUNCA se sobrescribe")
        return
    shutil.copy2(p, q)
    d, _ = leer(q)
    man = q.with_suffix(".sha256.json")
    man.write_text(json.dumps({
        "archivo": q.name, "sha256": sha256(q), "filas": len(d),
        "congelado": str(date.today()),
        "motivo": ("La revisión humana no está marcada en ninguna columna, así que TODA la "
                   "tabla se trata como decisión del investigador."),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  {c.upper()}: ✓ {len(d):,} decisiones congeladas → {q.name}")


def _clave(d: pd.DataFrame) -> pd.Series:
    """La clave es `speaker_raw` TAL CUAL, sin normalizar (ver aviso de la cabecera)."""
    return d["speaker_raw"].astype(str)


def _ambiguas(fro: pd.DataFrame) -> dict:
    """⚠⚠ Formas cuya clave apunta a MAS DE UN `id_dep` en la tabla congelada.

    `dict(zip(clave, id_dep))` y `{k: i for i, k in enumerate(clave)}` COLAPSAN la clave
    repetida quedandose con la ULTIMA. Sin esta guarda, `--apply` mandaba todas las filas de
    una forma ambigua a un solo diputado, y `--check` era CIEGO al estrago porque construia
    el mismo diccionario aplastado y comparaba el valor colapsado consigo mismo: informaba
    CERO discrepancias.

    Medido el 2026-08-26 sobre los 13 paises congelados: 11 no tienen ninguna forma ambigua.
    Muerden dos, y por causas distintas:
      ES  95 formas → 228.458 filas (42,37% del corpus). Son CARGOS PELADOS que solo la
          fecha desambigua: `PRESIDENTE` apunta a 21 `id_dep` distintos en 147.217 filas y
          `PRESIDENTA` a 11 en 69.491.
      PT 230 formas → 71.612 filas (6,37%). Son HOMONIMOS reales: dos diputados distintos con
          el mismo nombre parlamentario en legislaturas distintas — `Jose Magalhaes` 2,
          `Antonio Costa` 3, `Joao Pinho de Almeida` 4.
    Ninguna de las dos clases se resuelve por `speaker_raw`: hace falta la FECHA o la
    legislatura. Hasta que la clave las incorpore, estas formas NO se imponen: se INFORMAN.
    """
    g = fro.groupby(_clave(fro))["id_dep"].nunique()
    return {k: int(v) for k, v in g[g > 1].items()}


def check(c: str, aplicar: bool = False) -> dict | None:
    p, q = ruta(c), congelada(c)
    if not q.exists():
        print(f"  {c.upper()}: sin congelar — ejecuta --freeze primero")
        return None
    if not p.exists():
        print(f"  {c.upper()}: ✗ la matching_table ACTUAL no existe, pero sí la congelada")
        return None
    act, s = leer(p)
    fro, _ = leer(q)
    ka, kf = set(_clave(act)), set(_clave(fro))
    nuevas = ka - kf
    huerfanas = kf - ka
    comunes = ka & kf

    amb = _ambiguas(fro)
    fid = dict(zip(_clave(fro), fro["id_dep"]))
    aid = dict(zip(_clave(act), act["id_dep"]))
    # las ambiguas se sacan de `discrepan`: comparar contra un valor colapsado no dice nada
    discrepan = [k for k in comunes
                 if k not in amb and (fid.get(k) or "") != (aid.get(k) or "")]

    print(f"  {c.upper()}: congeladas {len(fro):,} · actuales {len(act):,}")
    print(f"      coinciden y no cambian : {len(comunes)-len(discrepan):,}")
    print(f"      la actual CONTRADICE la congelada: {len(discrepan):,}"
          + ("   ← la congelada manda" if discrepan else ""))
    print(f"      formas NUEVAS (trabajo manual nuevo): {len(nuevas):,}")
    print(f"      congeladas que YA NO aparecen: {len(huerfanas):,}"
          + ("   ← revisar: la extracción cambió esa forma" if huerfanas else ""))
    if amb:
        cae = sum(1 for k in comunes if k in amb)
        print(f"      ⚠⚠ formas AMBIGUAS (apuntan a >1 id_dep): {len(amb):,}"
              f" · presentes en la actual: {cae:,}")
        for k, n_ in sorted(amb.items(), key=lambda x: -x[1])[:6]:
            print(f"           {k[:34]!r:<38} → {n_} id_dep distintos")
        print("           NO se imponen: `speaker_raw` no las desambigua, hace falta la FECHA.")

    if not aplicar:
        return {"nuevas": len(nuevas), "huerfanas": len(huerfanas),
                "discrepan": len(discrepan), "ambiguas": len(amb)}

    bak = p.with_name(p.stem + ".pre_frozen.csv")
    if not bak.exists():
        shutil.copy2(p, bak)
        print(f"      copia previa → {bak.name}")
    # ⚠ el dict se construye SOLO con las formas no ambiguas: una clave repetida se
    #   quedaria con la ultima y mandaria todas sus filas a un unico diputado.
    idx = {}
    for i_, k_ in enumerate(_clave(fro)):
        if k_ not in amb:
            idx[k_] = i_
    act = act.copy()
    col_k = _clave(act)
    n = n_saltadas = 0
    for i, k in zip(act.index, col_k):
        if k in amb:
            n_saltadas += 1
            continue
        j = idx.get(k)
        if j is None:
            continue
        for col in fro.columns:
            if col in act.columns and col != "speaker_raw":
                v = fro.iat[j, fro.columns.get_loc(col)]
                if act.at[i, col] != v:
                    act.at[i, col] = v
                    n += 1
    act.to_csv(p, sep=s, index=False, encoding="utf-8")
    impuestas = len([k for k in comunes if k not in amb])
    print(f"      ✓ impuestas {impuestas:,} decisiones congeladas ({n:,} celdas corregidas)")
    if amb:
        ap = Path(f"docs/{c}/vinculacion_ambigua.csv")
        ap.parent.mkdir(parents=True, exist_ok=True)
        fro[_clave(fro).isin(amb)].to_csv(ap, index=False, encoding="utf-8")
        print(f"      ⚠⚠ NO impuestas {n_saltadas:,} filas de {len(amb):,} formas ambiguas → {ap}")
        print(f"         Resolver por FECHA antes de imponerlas. Ver `_ambiguas()`.")
    if huerfanas:
        hp = Path(f"docs/{c}/vinculacion_huerfana.csv")
        hp.parent.mkdir(parents=True, exist_ok=True)
        fro[_clave(fro).isin(huerfanas)].to_csv(hp, index=False, encoding="utf-8")
        print(f"      → {len(huerfanas):,} congeladas sin equivalente: {hp}")
    return {"nuevas": len(nuevas), "huerfanas": len(huerfanas), "discrepan": len(discrepan)}


def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument("--country")
    a.add_argument("--all", action="store_true")
    a.add_argument("--freeze", action="store_true")
    a.add_argument("--check", action="store_true")
    a.add_argument("--apply", action="store_true")
    o = a.parse_args()
    cs = PAISES if o.all else [o.country.lower()]
    if o.freeze:
        print("CONGELAR la vinculación revisada a mano")
        for c in cs:
            freeze(c)
    elif o.check or o.apply:
        print("IMPONER la vinculación congelada" if o.apply else "CONTRASTAR contra la congelada")
        for c in cs:
            check(c, aplicar=o.apply)
    else:
        a.error("elige --freeze, --check o --apply")


if __name__ == "__main__":
    main()
