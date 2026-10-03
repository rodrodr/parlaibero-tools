#!/usr/bin/env python3
"""Deriva `sex` (M/F) para los diputados con `id_dep`, con procedencia declarada.

Tres fuentes, en orden de autoridad decreciente. Cada valor guarda en `sex_source`
de cuál procede, porque es una variable **derivada** y quien la use debe poder
descartar el nivel que no le sirva:

  0. `official_registry` — un **registro oficial** publicado por la propia cámara o su
                    base relacional, que ya trae el sexo declarado: `deputados_BR.csv`
                    (datos abiertos de la Câmara, cubre el 100% de BR), `pe_diputado.csv`
                    (100% de PE), `diputados_v2.xml` (datos abiertos de la Cámara chilena),
                    `BASE_2018_2021.xlsx` de PoderES (SV, casado por nombre),
                    `diputados_arg.csv` y `diputados_pa_final.csv` (parciales). Viven en
                    `source/{iso2}/deputies/` **junto** al padrón de trabajo, sin ser el
                    padrón: hay que ir a buscarlos, y en cuatro formatos distintos.
                    Los ocho países restantes (CO CR DO ES GT MX PT UY) no tienen ninguno
                    y dependen enteramente de los niveles derivados.
  1. `roster`     — el padrón nacional ya lo registra en `notas` (CL completo).
  2. `honorific`  — género gramatical del tratamiento en `speaker_raw` del propio corpus
                    (`La señora DIPUTADA…`, `A Sr.ª…`), por mayoría ≥90% de las filas
                    de esa persona.
  3. `given_name` — diccionario de nombres de pila **aprendido del propio corpus** a
                    partir de 1 y 2 (≥2 apariciones concordantes). No se importa
                    ninguna lista externa.
  4. `given_name_rare` — el mismo diccionario con una sola aparición.
  5. `given_name_morph` — morfología del español y el portugués: nombre de pila en
                    *-a* → F, en *-o* → M, con una lista corta de excepciones.

⚠ **El honorífico solo cuenta si va junto a un nombre propio.** Sobre un cargo pelado
no dice nada de la persona: en ES, `VICEPRESIDENTA` estaba asignado a *Gómez Llorente,
Luis*, y `SECRETARIA` (por *Secretaría*, la oficina) a una docena de hombres. Sin esta
guarda la exactitud sobre ES caía al 35%. El error tiene la forma habitual del sesgo
de género del proyecto ([[feedback_gender_bias_extraction]]): inventa mujeres donde el
cargo es femenino y, en sentido inverso, **borra a las diputadas que presiden bajo un
`PRESIDENTE` masculino genérico**.

⚠ **El nivel 5 existe para no borrar mujeres.** Con solo el diccionario, la cobertura
era del **50,0% en mujeres frente al 82,3% en hombres**: los nombres masculinos alcanzan
el mínimo de apariciones y los femeninos no, porque los casos conocidos son 80% hombres.
Una columna así infra-identificaría a las diputadas de forma sistemática, y cualquiera
que calculase con ella el porcentaje de discurso femenino obtendría una cifra sesgada a
la baja. Con la morfología, la cobertura pasa a **94,2% en mujeres y 91,5% en hombres**.

**Exactitud medida contra revisión humana exhaustiva** de once países (2026-07-30). El
usuario revisó el padrón completo de CO CR DO ES GT MX PA PT PY SV UY y marcó
`sex_source = manual` en lo que cambió, dejando verificado lo demás — así que hay
denominador real, no una estimación:

    nivel                    n     errores    exactitud
    given_name          31.544        163       99,48%
    official_registry      326          1       99,69%
    given_name_morph     1.832         29       98,42%
    honorific            2.999        103       96,57%
    given_name_rare      1.671         95       94,31%
    ──────────────────────────────────────────────────
    conjunto            38.372        391       98,98%

    por sexo real:   M  28.192   129 err   99,54%
                     F  10.180   262 err   97,43%

**Una mujer tiene 5,5 veces más probabilidad de quedar mal clasificada.** Se declara:
quien mida participación femenina con esta variable debe saber que es menos precisa
para ellas. La revisión humana corrigió además 1.380 huecos que la derivación no cubría.

⚠ **`honorific` es el segundo nivel PEOR, por debajo del diccionario de nombres.** El
tratamiento explícito del acta parecía la señal más segura y no lo es: sus 103 errores son
casi todos mujeres presidiendo bajo el masculino genérico —`PRESIDENTE`, `PRESIDENTE EN
FUNCIONES`— y marcadores donde el nombre de una persona queda pegado al cargo de otra
(`Víctor Osvaldo Gómez Casanova la Diputada Vicepresidenta`). Exigir que el marcador
contenga un nombre **no basta**: haría falta que el tratamiento sea el que acompaña al
NOMBRE, no un cargo que aparezca en la misma línea. Afectó a Adriana Magali Matiz, Alba
Luz Pinilla, Ángela María Robledo, Rosmery Martínez y Lucía Medina, entre otras.

⚠ **La fiabilidad de `given_name_morph` depende del país.** Contrastado contra el registro
oficial de BR —1.492 casos que no habían entrado al entrenamiento—, `given_name` dio 98,6%
y `given_name_rare` 96,9%, confirmando la estimación; pero `given_name_morph` cayó al
**87,8%**, con el error sesgado en una dirección: **63 M→F frente a 14 F→M**. El padrón
brasileño identifica por apodo parlamentario, donde la terminación dice poco, y el efecto
era **inflar** el recuento de mujeres (245 detectadas frente a 196 reales). Donde exista
registro oficial, usarlo; donde no, tratar ese nivel como el más frágil.

`roster`, `honorific` y `manual` no son predicciones y no entran en esa medida. Quien
necesite precisión por encima de cobertura puede descartar `given_name_morph` y
`given_name_rare` filtrando por `sex_source`; por eso se publica el nivel y no solo el
valor.

Escribe `source/{iso2}/deputies/{ISO2}_sex.csv` (id_dep, sex, sex_source), que luego
consumen exportar_padron.py y aplicar_sexo_matriz.py.

Uso:  python3 derivar_sexo.py [--apply]
"""
from __future__ import annotations

import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

PAISES = ["ar", "br", "cl", "co", "cr", "do", "ec", "es", "gt", "mx", "pa", "pe", "pt", "py", "sv", "uy"]

FEM = re.compile(r"\b(?:la\s+se[ñn]ora|la\s+se[ñn]orita|se[ñn]ora|se[ñn]orita|deputada|diputada|"
                 r"presidenta|vicepresidenta|secretaria|sra|doctora|dra)\b", re.I)
MASC = re.compile(r"\b(?:el\s+se[ñn]or|se[ñn]or|deputado|diputado|presidente|vicepresidente|"
                  r"secretario|sr|doctor|dr)\b", re.I)

# vocabulario de cargo y cortesía: si al quitarlo no queda nada, el marcador no nombra a nadie
ROL = set("""senor senora senorita sr sra srta dr dra doctor doctora don dona el la los las de del
y e presidente presidenta vicepresidente vicepresidenta secretario secretaria prosecretario
prosecretaria diputado diputada deputado deputada ministro ministra primero primera segundo segunda
tercero tercera cuarto cuarta quinto quinta interino interina provisional accidental suplente
gobierno cortes camara camaras congreso republica asamblea estado nacion mesa presidencia
excelentisimo excelentisima ilustrisimo sus senorias senoria orden dia""".split())

# partículas que no son nombre de pila
PART = {"de", "del", "la", "las", "los", "da", "das", "do", "dos", "y", "e",
        "san", "santa", "van", "von", "di", "der", "el"}

MIN_CASOS = 2        # apariciones mínimas de un nombre de pila para entrar al diccionario
MIN_ACUERDO = 0.90   # concordancia mínima entre esas apariciones

# Registros oficiales con el sexo ya declarado, que viven en `source/{iso2}/deputies/`
# junto al padrón de trabajo pero NO son el padrón. Son dato, no predicción, y mandan
# sobre cualquier derivación.
#   iso2 → (archivo, columna clave, columna de sexo, transformación de la clave)
FUENTES_OFICIALES = {
    # datos abiertos de la Câmara dos Deputados; la clave va dentro de la URI del API
    "br": ("deputados_BR.csv", "uri", "siglaSexo", lambda s: "BR" + s.rsplit("/", 1)[-1]),
    "pe": ("pe_diputado.csv", "id_diputado", "sexo", None),
    "ar": ("diputados_arg.csv", "id_dep", "genero", None),
    "pa": ("diputados_pa_final.csv", "id_dep", "sexo", None),
    # datos abiertos de la Cámara de Diputados de Chile: <Id> + <Sexo>Masculino|Femenino
    "cl": ("diputados_v2.xml", "Id", "Sexo", lambda s: "CL" + s.zfill(5)),
}
NS_CL = "{http://opendata.camara.cl/camaradiputados/v1}"

# Registros oficiales SIN identificador común: hay que casarlos por nombre contra el
# padrón. Se casa por CONJUNTO de tokens (el orden nombre/apellido varía entre fuentes)
# y se acepta también la inclusión de un conjunto en el otro, que cubre los nombres
# abreviados. Siguen siendo dato declarado, no predicción.
#   iso2 → (archivo, hoja, fila de cabecera, columnas de nombre, columna de sexo)
FUENTES_POR_NOMBRE = {
    # base de PoderES sobre la legislatura 2018-2021, con `GÉNERO` declarado
    "sv": ("BASE_2018_2021.xlsx", "BD_PoderES", 2, ("NOMBRES", "APELLIDOS"), "GÉNERO"),
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z\s]", " ", s)).strip()


def nombra_persona(speaker_raw: str) -> bool:
    """True si el marcador contiene algo más que cargo y cortesía."""
    return any(t not in ROL and len(t) > 2 for t in norm(speaker_raw).split())


def tokens_pila(nombre: str) -> list[str]:
    """Nombre de pila: los dos primeros tokens útiles.

    ⚠ **ES y PY escriben «Apellidos, Nombre»** (`Pau i Pernau, Josep`). Ahí los dos
    primeros tokens son APELLIDOS, no el nombre de pila: sin esta guarda la cobertura
    de ES caía al 28% y su exactitud al 65%, porque el diccionario estaba leyendo
    apellidos. Cuando hay coma, el nombre de pila va detrás.
    """
    s = str(nombre)
    if "," in s:
        s = s.split(",", 1)[1]
    t = [x for x in norm(s).split() if x not in PART and len(x) > 2]
    return t[:2]


def ruta_padron(iso2: str) -> Path | None:
    for n in ("deputies.csv", "diputados_bd.csv"):
        p = Path(f"source/{iso2}/deputies/{n}")
        if p.exists():
            return p
    return None


def leer(p: Path) -> pd.DataFrame:
    head = p.open(encoding="utf-8", errors="replace").readline()
    return pd.read_csv(p, sep=";" if head.count(";") > head.count(",") else ",",
                       dtype=str, keep_default_na=False)


def recoger() -> tuple[dict, dict, dict]:
    """→ sexo[(pais,id)], fuente[(pais,id)], nombre[(pais,id)]"""
    sexo, fuente, nombre = {}, {}, {}

    for c, (arch, ck, cs, tk) in FUENTES_OFICIALES.items():   # nivel 0: registro oficial
        p = Path(f"source/{c}/deputies/{arch}")
        if not p.exists():
            continue
        if p.suffix.lower() == ".xml":
            pares = []
            for nodo in ET.parse(p).getroot().findall(f"{NS_CL}Diputado"):
                i = nodo.findtext(f"{NS_CL}Id")
                s = nodo.find(f"{NS_CL}{cs}")
                if i and s is not None:
                    pares.append((i, (s.text or "").strip()))
        else:
            head = p.open(encoding="utf-8-sig", errors="replace").readline()
            r = pd.read_csv(p, sep=";" if head.count(";") > head.count(",") else ",",
                            dtype=str, keep_default_na=False, encoding="utf-8-sig")
            if ck not in r.columns or cs not in r.columns:
                continue
            pares = list(zip(r[ck], r[cs]))

        for k, v in pares:
            v = str(v).strip().upper()
            v = "M" if v.startswith("MASC") else "F" if v.startswith("FEM") else v
            if v in ("M", "F"):
                sexo[(c, tk(k) if tk else k)] = v
                fuente[(c, tk(k) if tk else k)] = "official_registry"

    for c, (arch, hoja, cab, cn_, cs) in FUENTES_POR_NOMBRE.items():   # nivel 0-bis
        p = Path(f"source/{c}/deputies/{arch}")
        pad = ruta_padron(c)
        if not p.exists() or pad is None:
            continue
        x = pd.read_excel(p, sheet_name=hoja, header=cab, dtype=str)
        x = x[x[cs].isin(["M", "F"])]
        idx = {frozenset(norm(" ".join(str(v.get(k, "")) for k in cn_)).split()): v[cs]
               for _, v in x.iterrows()}
        idx.pop(frozenset(), None)
        r = leer(pad)
        low = {y.lower(): y for y in r.columns}
        cid = low.get("id_dep") or low.get("diputado_id")
        cnm = next((low[k] for k in ("nombre_completo", "speaker_name", "nombre_original")
                    if k in low), None)
        if not (cid and cnm):
            continue
        for i, nm in zip(r[cid], r[cnm]):
            k = (c, i)
            if k in sexo:
                continue
            t = frozenset(norm(nm).split())
            v = idx.get(t) or next((g for kk, g in idx.items() if t and (t <= kk or kk <= t)), None)
            if v:
                sexo[k], fuente[k] = v, "official_registry"

    for c in PAISES:                                   # nivel 1: padrón
        p = ruta_padron(c)
        if p is None:
            continue
        r = leer(p)
        low = {x.lower(): x for x in r.columns}
        cid = low.get("id_dep") or low.get("diputado_id")
        cn = next((low[k] for k in ("nombre_completo", "speaker_name", "nombre_original", "alias")
                   if k in low), None)
        cnt = next((low[k] for k in ("notas", "notes") if k in low), None)
        if not cid:
            continue
        for _, row in r.iterrows():
            k = (c, row[cid])
            if cn:
                nombre.setdefault(k, row[cn])
            # corrección humana: máxima autoridad, nunca se recalcula
            if "sex" in low and "sex_source" in low and str(row[low["sex_source"]]) == "manual":
                v = str(row[low["sex"]]).strip().upper()
                if v in ("M", "F"):
                    sexo[k], fuente[k] = v, "manual"
                    continue
            if cnt and k not in sexo:          # el registro oficial ya resuelto manda
                m = re.search(r"sexo\s*:\s*([MFmf])", str(row[cnt]))
                if m:
                    sexo[k], fuente[k] = m.group(1).upper(), "roster"

    for c in PAISES:                                   # nivel 2: honorífico junto a nombre
        d = pd.read_csv(f"source/{c}/standardize/{c.upper()}_interventions.csv", dtype=str,
                        keep_default_na=False, usecols=["id_dep", "speaker_raw", "speaker_name"])
        d = d[d.id_dep.str.strip() != ""]
        for i, g in d.groupby("id_dep"):
            k = (c, i)
            nombre.setdefault(k, g.speaker_name.iloc[0])
        d = d[d.speaker_raw.map(nombra_persona)]
        for i, g in d.groupby("id_dep"):
            k = (c, i)
            if k in sexo:
                continue
            f = int(g.speaker_raw.str.contains(FEM).sum())
            m = int(g.speaker_raw.str.contains(MASC).sum())
            if f + m == 0 or max(f, m) / (f + m) < MIN_ACUERDO:
                continue
            sexo[k], fuente[k] = ("F" if f > m else "M"), "honorific"

    return sexo, fuente, nombre


def aprender(sexo: dict, nombre: dict, minimo: int = MIN_CASOS) -> dict:
    c = defaultdict(Counter)
    for k, s in sexo.items():
        t = tokens_pila(nombre.get(k, ""))
        if t:
            c[t[0]][s] += 1
    return {k: v.most_common(1)[0][0] for k, v in c.items()
            if sum(v.values()) >= minimo
            and v.most_common(1)[0][1] / sum(v.values()) >= MIN_ACUERDO}


# nombres de pila cuya terminación contradice su género: la morfología no decide sobre ellos
EXCEPCIONES = {"jose", "juan", "luca", "elias", "matias", "tobias", "zacarias", "nicolas",
               "andrea", "jeremias", "isaias", "ezequias", "josue", "noe", "aquiles",
               "sacramento", "amparo", "rosario", "guadalupe", "trinidad", "consuelo"}


def morfologia(nombre: str) -> str | None:
    """Género por terminación del **primer** nombre de pila (español y portugués).

    ⚠ Mira solo el primer token y, si no concluye, **no decide**. Recorrer los tokens
    siguientes hace que en los nombres de un solo nombre de pila la regla caiga sobre
    el APELLIDO, y los apellidos ibéricos en *-a* son abundantísimos: así salían
    `Arthur Lira`, `Glauber Braga` y `Lincoln Portela` clasificados como mujeres —y
    Arthur Lira, que presidió la cámara, arrastra 24.490 intervenciones.
    """
    t = tokens_pila(nombre)
    if not t or t[0] in EXCEPCIONES:
        return None
    if t[0].endswith("a"):
        return "F"
    if t[0].endswith(("o", "os")):
        return "M"
    return None


def main(apply: bool) -> None:
    sexo, fuente, nombre = recoger()
    print(f"conocido por fuente directa: {len(sexo):,} "
          f"(roster {sum(v == 'roster' for v in fuente.values()):,} · "
          f"honorific {sum(v == 'honorific' for v in fuente.values()):,})")

    dicc = aprender(sexo, nombre)                      # ≥2 apariciones concordantes
    raro = aprender(sexo, nombre, minimo=1)            # una sola aparición
    print(f"diccionario aprendido del corpus: {len(dicc):,} nombres frecuentes, "
          f"{len(raro) - len(dicc):,} raros")

    pendientes = [k for k in nombre if k not in sexo]
    for nivel, resolver in (("given_name", lambda n: next((dicc[t] for t in tokens_pila(n)
                                                           if t in dicc), None)),
                            ("given_name_rare", lambda n: next((raro[t] for t in tokens_pila(n)
                                                                if t in raro), None)),
                            ("given_name_morph", morfologia)):
        for k in pendientes:
            if k in sexo:
                continue
            v = resolver(nombre.get(k, ""))
            if v:
                sexo[k], fuente[k] = v, nivel

    print(f"\n{'':4} {'con id_dep':>11} {'con sexo':>9} {'cob%':>6} "
          f"{"ofic":>7} {"roster":>6} {"honor":>6} {'nombre':>7} {'raro':>6} {'morf':>6} {'%F':>6}")
    print("-" * 92)
    tot_i = tot_s = 0
    for c in PAISES:
        d = pd.read_csv(f"source/{c}/standardize/{c.upper()}_interventions.csv", dtype=str,
                        keep_default_na=False, usecols=["id_dep"])
        ids = sorted({x for x in d.id_dep if x.strip()})
        # se emite para TODO el padrón, no solo para quien habla: el padrón se publica
        # entero como dato auxiliar y dejar en blanco a quien nunca intervino sería
        # un hueco artificial (en PT eran dos tercios de las filas)
        todos = sorted({i for p, i in sexo if p == c} | set(ids))
        fil = [(i, sexo[(c, i)], fuente[(c, i)]) for i in todos if (c, i) in sexo]
        cnt = Counter(f for _, _, f in fil)
        pf = 100 * sum(s == "F" for _, s, _ in fil) / max(len(fil), 1)
        # la cobertura se mide sobre quien interviene, que es lo que afecta a la matriz
        conhab = sum(1 for i in ids if (c, i) in sexo)
        tot_i += len(ids)
        tot_s += conhab
        print(f"{c.upper():4} {len(ids):11,} {conhab:9,} {100*conhab/max(len(ids),1):5.1f}% "
              f"{cnt["official_registry"]:7,} {cnt["roster"]:6,} {cnt["honorific"]:6,} {cnt['given_name']:7,} "
              f"{cnt['given_name_rare']:6,} {cnt['given_name_morph']:6,} {pf:5.1f}%")
        if apply:
            dst = Path(f"source/{c}/deputies/{c.upper()}_sex.csv")
            pd.DataFrame(fil, columns=["id_dep", "sex", "sex_source"]).to_csv(
                dst, index=False, encoding="utf-8")
    print("-" * 92)
    print(f"{'TOT':4} {tot_i:11,} {tot_s:9,} {100*tot_s/max(tot_i,1):5.1f}%")
    if not apply:
        print("\n--- SIMULACIÓN --- (usa --apply para escribir {ISO2}_sex.csv)")


if __name__ == "__main__":
    import argparse
    _ap = argparse.ArgumentParser()
    _ap.add_argument("--apply", action="store_true")
    _ap.add_argument("--country", help="ISO2: limita la cascada a UN país; sin él, todos")
    _a = _ap.parse_args()
    if _a.country:
        _c = _a.country.lower()
        if _c not in PAISES:
            sys.exit(f"país desconocido: {_c!r} (válidos: {', '.join(PAISES)})")
        PAISES[:] = [_c]
    main(_a.apply)
