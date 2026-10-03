#!/usr/bin/env python3
"""Reconcilia el `speaker_raw` de un REPROCESO con la tabla de matching CONGELADA.

**Por qué existe.** Al reprocesar un país desde la fuente, el `speaker_raw` sale en la forma
que trae el acta —`ALEJOS CAMBARA`, apellidos en versales— mientras la tabla congelada está
tecleada sobre la forma normalizada del corpus vigente —`José Roberto Alejos Cámbara`—. Son
la misma persona escritas de dos maneras, y un cruce literal las da por distintas: en GT el
cruce directo perdía el 100% de las decisiones. Esas decisiones son trabajo humano —1.190 en
GT, 99.768 en trece países— y **el reproceso no puede costarlas**.

La reconciliación va en CASCADA, de la evidencia más fuerte a la más débil, y cada fila queda
etiquetada con la regla que la resolvió para que se pueda auditar:

  1. `tabla`      — la forma normalizada está en la tabla congelada CON `id_dep`. Es una
                    decisión tuya, incluidas las de solo apellido resueltas a mano o por LLM.
  2. `padron`     — coincide con los apellidos del padrón y **solo hay una persona** con ellos.
  3. `padron_rol` — igual, tras recortar un prefijo de cargo que el etiquetado dejó pegado
                    (`VOCAL I DE LA COMISION PERMANENTE, MENDEZ HERBRUGER`). 7.400 filas en GT.
  4. `fuzzy`      — variante de OCR de un apellido del padrón por encima del umbral
                    (`MONTENEGRO COTTON` → `Montenegro Cottom`). Sin ambigüedad y con margen
                    sobre el segundo candidato, que es lo que evita el falso positivo.
  5. `no_diputado`— la forma trae un cargo NO parlamentario explícito (MINISTRO, PROCURADOR,
                    MAGISTRADO, EMBAJADOR…). Se descuenta del denominador de la vinculación
                    efectiva; ver `feedback_vinculacion_efectiva` — solo los NOMBRADOS, nunca
                    los cargos anónimos, que son huecos propios.
  6. `ambiguo` / `sin_correspondencia` — NO se inventan. Salen al informe para revisión.

⚠⚠ **Un `unmatched` de la tabla congelada NO significa «no es diputado».** Significa «el
pipeline anterior no supo resolver esta forma», que es cosa muy distinta. En GT la tabla trae
a la vez `Nery Abilio Ramos y Ramos → GT00579 exact` y `Ramos Y Ramos → unmatched`: la misma
persona, presidente del Congreso, sin resolver en su forma de solo apellido. Dar el `unmatched`
por decisión humana apartaba **21.187 filas** de tres presidentes del Congreso y bajaba la
vinculación 8,6 puntos por un artefacto. Por eso el padrón se consulta ANTES, y `no_diputado`
exige evidencia POSITIVA de cargo no parlamentario. Es la [[feedback_primacia_del_diario]]
aplicada al matching: el fallo es de la tabla, no del acta.

⚠ **La columna `apellidos` de los padrones suele venir como «Apellidos, Nombre», no como
apellidos sueltos.** Cruzar contra ella tal cual falla, y cruzar solo contra la parte anterior
a la coma pierde las formas que el acta escribe igual (`RABBÉ TEJADA, LUIS ARMANDO`: 1.404
filas en GT). Se prueban LAS DOS.

⚠ **El apellido compartido no se resuelve por frecuencia.** Dos diputados con los mismos
apellidos son dos personas; elegir al más frecuente inventa atribuciones. Van a `ambiguo`.

Uso:
    python3 reconcile_frozen_match.py --country gt \
        --matrix source/gt/matrix/interventions_raw.csv \
        --out source/gt/match/matching_table_reproceso.csv
"""
from __future__ import annotations

import argparse
import csv
import re
import unicodedata as U
from collections import defaultdict

import pandas as pd

try:
    from rapidfuzz import fuzz, process as rf_process
except ImportError:  # la cascada funciona sin fuzzy, solo pierde el paso 5
    fuzz = rf_process = None

# Cargos que NO son de la cámara. Exige evidencia POSITIVA: un `unmatched` en la tabla
# congelada no vale como prueba (ver la advertencia del encabezado).
NO_PARLAMENTARIO = re.compile(
    r"\b(?:MINISTR[OA]|VICEMINISTR[OA]|PROCURADOR[A]?|FISCAL|MAGISTRAD[OA]|EMBAJADOR[A]?"
    r"|PRESIDENTE\s+DE\s+LA\s+REP[UÚ]BLICA|CONTRALOR[A]?|SUPERINTENDENTE"
    r"|DEFENSOR[A]?|ALCALDE|ALCALDESA|GOBERNADOR[A]?|SECRETARI[OA]\s+DE\s+ESTADO)\b",
    re.I,
)

# Prefijos de cargo que el etiquetado puede dejar pegados al nombre.
# ⚠ Se aplica SOBRE EL TEXTO YA NORMALIZADO, nunca sobre el crudo: recortarlo antes de quitar
# los acentos hacía que `VOCAL I DE LA COMISIÓN PERMANENTE, ARÉVALO BARRIOS` no casara —la
# tilde de COMISIÓN— mientras su gemelo sin tilde sí. El acta escribe las dos formas.
ROL_PEGADO = re.compile(
    r"^(?:ACCIDENTAL|VOCAL(?:\s+[IVX]+)?(?:\s+(?:PRIMER[OA]?|SEGUND[OA]|TERCER[OA]?))?"
    r"(?:\s+DE\s+LA\s+COMISION\s+PERMANENTE)?"
    r"|DE\s+LA\s+JUNTA(?:\s+PROVISIONAL)?(?:\s+DE\s+DEBATES)?"
    r"|(?:PRIMER[A]?|SEGUND[OA]|TERCER[A]?|CUART[OA]|QUINT[OA])?\s*(?:VICE)?PRESIDENT[EA]"
    r"|SECRETARI[OA]|DIPUTAD[OA])\s*,?\s+"
)

# «Apellido de casada»: `ACEÑA VILLACORTA DE FUENTES` frente a `Aceña Villacorta` en el padrón.
# Solo afecta a mujeres, así que no cubrirlo borra mujeres y solo mujeres — el patrón que ya
# se documentó en `feedback_gender_bias_extraction`. Se prueba el núcleo sin el ` DE X` final.
NUCLEO_CASADA = re.compile(r"\s+(?:DE|VDA\s+DE|V\s+DE)\s+\S+(?:\s+\S+)?$")


def nrm(s: str) -> str:
    """Versales sin acentos ni puntuación. El guion pasa a espacio: `DÍAZ-SOL` == `DIAZ SOL`."""
    s = U.normalize("NFD", s.upper())
    s = "".join(c for c in s if U.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^A-ZÑ ]", " ", s.replace("-", " "))).strip()


def leer(p: str) -> pd.DataFrame:
    with open(p, encoding="utf-8") as fh:
        d = csv.Sniffer().sniff(fh.readline(), ";,\t").delimiter
    return pd.read_csv(p, sep=d, dtype=str, keep_default_na=False)


def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument("--country", required=True)
    a.add_argument("--matrix", required=True)
    a.add_argument("--out", required=True)
    a.add_argument("--fuzzy-min", type=float, default=92.0,
                   help="similitud mínima (0-100) para aceptar una variante de OCR")
    a.add_argument("--fuzzy-margen", type=float, default=6.0,
                   help="ventaja mínima sobre el 2º candidato; sin margen no se acepta")
    o = a.parse_args()
    c = o.country.lower()

    dep = leer(f"source/{c}/deputies/deputies.csv")
    tab = leer(f"source/{c}/match/matching_table.csv")
    mat = leer(o.matrix)

    # ── índices ────────────────────────────────────────────────────────────────────────
    # Solo las entradas CON id_dep. Las `unmatched` se ignoran a propósito: no son
    # decisiones de «no es diputado», sino fallos del pipeline anterior (ver encabezado).
    TAB = {nrm(r.speaker_raw): r.id_dep for _, r in tab.iterrows() if r.id_dep}

    # Los `unmatched` de la tabla NO prueban «no es diputado», pero los que traen un cargo
    # ajeno a la cámara SÍ identifican a la persona: de `El Senor Ministro De Salud Publica,
    # Ingeniero Sosa Ramirez` se extrae que SOSA RAMIREZ es ministro. El etiquetado captura
    # solo el apellido y pierde el cargo, así que sin este índice esos oradores caen en
    # `sin_correspondencia` y contaminan el denominador de la vinculación efectiva.
    NO_DIP: set[str] = set()
    for _, r in tab.iterrows():
        if r.id_dep or not NO_PARLAMENTARIO.search(r.speaker_raw):
            continue
        k = nrm(r.speaker_raw)
        pal = k.split()
        for n_ in (3, 2):                    # los últimos 2-3 tokens son el apellido
            if len(pal) > n_:
                NO_DIP.add(" ".join(pal[-n_:]))

    AP: dict[str, set] = defaultdict(set)
    for _, r in dep.iterrows():
        ap = r.get("apellidos", "") or ""
        AP[nrm(ap)].add(r.id_dep)                 # forma completa «Apellidos, Nombre»
        AP[nrm(ap.split(",")[0])].add(r.id_dep)   # solo apellidos
    unicos = {k: next(iter(v)) for k, v in AP.items() if len(v) == 1}

    nombre = dict(zip(dep.id_dep, dep.nombre_completo))
    claves = list(unicos)

    # Mandato de cada diputado, para desambiguar el apellido compartido POR FECHA de sesión:
    # dos personas con los mismos apellidos casi nunca coinciden en el tiempo.
    mandato = {r.id_dep: (r.get("fecha_inicio", ""), r.get("fecha_fin", ""))
               for _, r in dep.iterrows()}
    # fechas en que aparece cada forma, tomadas de la propia matriz
    fechas: dict[str, set] = defaultdict(set)
    if "date" in mat.columns:
        for s_, d_ in zip(mat.speaker_raw, mat.date):
            fechas[s_].add(d_)

    # ── PASE DE LISTA · el desambiguador fuerte ────────────────────────────────────────
    # Las actas nombran a los diputados COMPLETOS en los pases de lista y en los recuentos
    # nominales de votación (`Nájera Flores, Dora Lizett 123`). Si en la sesión donde aparece
    # `BALDIZON MENDEZ` la lista nombra a Manuel Antonio y no a Salvador Francisco, el apellido
    # compartido deja de ser ambiguo. Es mucho más fino que el rango de mandato, que solo
    # separa a quienes no coincidieron en el tiempo. Ver `feedback_attendance_disambiguation`.
    PLENO = {}                                  # nombre completo normalizado → id_dep
    for _, r in dep.iterrows():
        PLENO[nrm(r.nombre_completo)] = r.id_dep
        ap = r.get("apellidos", "") or ""
        if "," in ap:
            PLENO[nrm(ap)] = r.id_dep           # forma «Apellidos, Nombre» del pase de lista
    NUM_FINAL = re.compile(r"\s*\d{1,4}\s*$")   # el ordinal que cierra la línea de la lista
    presentes: dict[str, set] = defaultdict(set)
    if "date" in mat.columns:
        for t, d_ in zip(mat.text, mat.date):
            if "\n" not in t:
                continue
            for ln in t.split("\n"):
                ln = ln.strip()
                if not (8 < len(ln) < 70):
                    continue
                i = PLENO.get(nrm(NUM_FINAL.sub("", ln)))
                if i:
                    presentes[d_].add(i)

    def por_lista(s: str, cands: set) -> str:
        """Único candidato NOMBRADO en los pases de lista de las sesiones donde habla."""
        vistos = set()
        for f in fechas.get(s, ()):
            vistos |= cands & presentes.get(f, set())
        return next(iter(vistos)) if len(vistos) == 1 else ""

    def por_mandato(s: str, cands: set) -> str:
        """Devuelve el único candidato cuyo mandato cubre TODAS las fechas de la forma."""
        fs = {f for f in fechas.get(s, ()) if re.match(r"^\d{4}-\d{2}-\d{2}$", f)}
        if not fs:
            return ""
        viables = []
        for i in cands:
            ini, fin = mandato.get(i, ("", ""))
            if not ini and not fin:
                continue
            if all((not ini or f >= ini) and (not fin or f <= fin) for f in fs):
                viables.append(i)
        return viables[0] if len(viables) == 1 else ""

    # ── cascada ────────────────────────────────────────────────────────────────────────
    filas, res = [], defaultdict(lambda: [0, 0])
    for s, n in mat.speaker_raw.value_counts().items():
        k = nrm(s)
        k_rol = ROL_PEGADO.sub("", k)          # ⚠ sobre lo YA normalizado, por las tildes
        k_sol = NUCLEO_CASADA.sub("", k_rol)   # núcleo sin el « DE X» de casada
        idd, regla, conf = "", "", 0.0
        if k in TAB:
            idd, regla, conf = TAB[k], "tabla", 1.0
        elif k in unicos:
            idd, regla, conf = unicos[k], "padron", 1.0
        elif k_rol != k and k_rol in unicos:
            idd, regla, conf = unicos[k_rol], "padron_rol", 0.95
        elif k in AP or (k_rol != k and k_rol in AP):
            cands = AP.get(k) or AP[k_rol]
            # el pase de lista primero: nombra a la persona, no solo acota su época
            if (e := por_lista(s, cands)):
                idd, regla, conf = e, "pase_de_lista", 0.93
            elif (e := por_mandato(s, cands)):
                idd, regla, conf = e, "mandato", 0.90
            else:
                regla = "ambiguo"
        elif k_sol != k_rol and k_sol in unicos:
            idd, regla, conf = unicos[k_sol], "casada", 0.88
        elif k_rol in NO_DIP or k_sol in NO_DIP or NO_PARLAMENTARIO.search(s):
            # evidencia POSITIVA de cargo ajeno a la cámara — no basta con estar `unmatched`
            regla, conf = "no_diputado", 1.0
        elif rf_process is not None and claves:
            top = rf_process.extract(k, claves, scorer=fuzz.ratio, limit=2)
            if top and top[0][1] >= o.fuzzy_min and (
                    len(top) < 2 or top[0][1] - top[1][1] >= o.fuzzy_margen):
                idd, regla, conf = unicos[top[0][0]], "fuzzy", top[0][1] / 100
            else:
                regla = "sin_correspondencia"
        else:
            regla = "sin_correspondencia"
        filas.append({"speaker_raw": s, "id_dep": idd,
                      "nombre_completo": nombre.get(idd, ""), "match_method": regla,
                      "confidence": f"{conf:.2f}", "n_filas": n, "notas": ""})
        res[regla][0] += 1
        res[regla][1] += n

    pd.DataFrame(filas).to_csv(o.out, sep=";", index=False, encoding="utf-8")

    tot = len(mat)
    print(f"── {c.upper()} · reconciliación con la tabla congelada ──")
    for k in sorted(res):
        f, r = res[k]
        print(f"  {k:22} {f:>5} formas  {r:>9,} filas  {100*r/tot:>5.1f}%")
    vinc = sum(r for k, (_, r) in res.items()
               if k in ("tabla", "padron", "padron_rol", "pase_de_lista",
                        "mandato", "casada", "fuzzy"))
    nodip = res["no_diputado"][1]
    print(f"\n  vinculada BRUTA    {vinc:>9,}  {100*vinc/tot:.1f}%")
    print(f"  no-diputado        {nodip:>9,}")
    print(f"  vinculada EFECTIVA {vinc:>9,}  {100*vinc/max(tot-nodip,1):.1f}%  "
          f"(descontando solo los no-diputados NOMBRADOS)")
    print(f"\n  → {o.out}")
    print("  ⚠ revisa a mano las filas «ambiguo» y «sin_correspondencia»: no se han inventado.")


if __name__ == "__main__":
    main()
