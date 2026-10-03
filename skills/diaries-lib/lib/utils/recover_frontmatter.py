#!/usr/bin/env python3
"""Recupera la CARÁTULA y el SUMARIO del acta, que el pipeline descartaba en silencio.

La directiva del proyecto es enriquecer, no desechar. Medido el 2026-08-09 comparando
`corrected/` con el corpus publicado, la cabecera del acta llegaba al corpus en el 0% de las
actas de AR, 1% de UY, 3% de PA, 6% de CL y MX, 10% de CO, 15% de GT y 20% de CR — con cuerpos
que llegaban al 62-92%. Se perdía material que nadie puede reconstruir después:

    AR  presidencia, secretarios, prosecretarios y la LISTA DE DIPUTADOS PRESENTES
    PA  legislatura, hora del primer llamado y el pase de lista completo
    CL  número y tipo de sesión, horas, presidencia ACCIDENTAL, secretario, e ÍNDICE
    GT  período legislativo, tomo, tipo y número de sesión, y el SUMARIO con sus páginas
    ES  legislatura, número, presidencia y el ORDEN DEL DÍA
    UY  número y tomo, legislatura, período, y quiénes presiden y actúan en secretaría
    MX  legislatura, año, período, número de diario, presidencia y recinto

El límite NO se adivina: es **todo lo que precede en `corrected/` al primer texto que sí llegó
al corpus**. Así el criterio es el mismo en los 16 países y se puede comprobar.

La cabecera entra como una FILA MÁS de la sesión —los **Prolegomena**— con `dm_speech = 0`,
sin orador (no lo tiene) y con **`intervention_order = 0`**: precede a la primera intervención
válida sin desplazar la numeración de ninguna. Así el corpus se enriquece sin romper ninguna
referencia ya publicada, y `intervention_order == 0` identifica el elemento por sí solo.

CLI:
    python recover_frontmatter.py --country ar [--etapa corrected] [--medir] [--min 200]
"""
import argparse
import csv
import glob
import gzip
import os
import re
import sys
import unicodedata
from collections import defaultdict

csv.field_size_limit(sys.maxsize)

FECHA = re.compile(r"(\d{4})[-_]?(\d{2})[-_]?(\d{2})")
_PAG = re.compile(r"^-{2,}\s*PAGE\s+\d+\s*-{2,}\s*$", re.M | re.I)
ANCLA = 220        # cuántos caracteres normalizados del primer turno se usan para anclar


def _norm_map(s: str):
    """Normaliza y devuelve (normalizado, índice_normalizado → índice_original)."""
    out, idx = [], []
    for i, c in enumerate(s):
        d = unicodedata.normalize("NFD", c.upper())
        for ch in d:
            if unicodedata.category(ch) == "Mn":
                continue
            if ch.isalnum():
                out.append(ch)
                idx.append(i)
    return "".join(out), idx


def _norm(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFD", s.upper())
                if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Z0-9]+", "", s)


def _abre(p: str) -> str:
    o = gzip.open if p.endswith(".gz") else open
    with o(p, "rt", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def cabecera(texto: str, primeros: list[str]) -> str:
    """Lo que precede al primer turno del acta que sí llegó al corpus.

    `primeros` son los textos candidatos a primer turno (las filas del corpus de esa fecha).
    Se ancla el que aparezca ANTES en el acta: con varias sesiones el mismo día, cada archivo
    engancha con el turno que de verdad lo abre.
    """
    tn, idx = _norm_map(texto)
    if not tn:
        return ""
    mejor = None
    for t in primeros:
        a = _norm(t)[:ANCLA]
        if len(a) < 60:
            continue
        j = tn.find(a)
        if j >= 0 and (mejor is None or j < mejor):
            mejor = j
    if mejor is None or mejor == 0:
        return ""
    return texto[:idx[mejor]]


def limpia(s: str) -> str:
    return _PAG.sub("", s).strip()


def detector(filas):
    """Regex de las formas de orador REALES del país. El vocabulario no se adivina: se deriva
    del propio `speaker_raw`, igual que en `conformidad._detector_del_pais`."""
    from collections import Counter
    c = Counter(x["speaker_raw"].strip() for x in filas if len(x["speaker_raw"].strip()) >= 8)
    top = [f for f, n in c.most_common(300) if n >= 3]
    if not top:
        return None
    alt = "|".join(re.escape(f) for f in sorted(top, key=len, reverse=True))
    return re.compile(r"(?:^|(?<=[.;:!?»\"\)])\s+)(?:" + alt + r")", re.M)


# La carátula NOMBRA a quien ocupa el cargo, y esa línea es idéntica a un marcador de turno:
# PT escribe «Presidente: Ex.mo Sr. Vasco da Gama Fernandes» y «Secretários: Ex.mas Sr.as …».
# Lo que sigue a los dos puntos no es habla, es un tratamiento y un nombre propio. Sin esto, la
# verificación daba 98,10 % de Prolegomena «sucios» en PT, y los 859 avisos de la muestra eran
# TODOS esa misma línea. Medir qué dispara una métrica antes de creérsela.
_ROTULO = re.compile(r"^\s*[:.]?\s*(?:Ex\.?\s*[ma]?[oa]?\.?|Exm[oa]s?\.?|S\.?\s*Ex\.?[ª\.]?|"
                     r"Sr\.?[ª\.]?a?s?|Senhor(?:a|es|as)?|Se(?:ñ|n)or(?:a|es|as)?|"
                     r"Dr\.?[ª\.]?a?|Doutor[a]?|Excelent[íi]ssim[oa])\b")


def marcadores_dentro(c: str, det) -> int:
    """Cuántos marcadores de intervención quedaron DENTRO del Prolegomena.

    Es el control del corte: se corta en la primera intervención y se comprueba que no haya
    ninguna dentro. Reutiliza los mismos filtros que `conformidad._incrustados` —terminador de
    marcador, pase de lista, tratamiento, paréntesis abierto y firma al pie— para no contar
    como orador lo que solo es un nombre citado.
    """
    if det is None:
        return 0
    import conformidad as CF
    n = 0
    for g in det.finditer(c):
        i = g.end()
        if not CF._TERMINA.match(c[i:i + 20]):
            continue
        if CF._LISTA.match(c[i:i + 56]):
            continue
        # El terminador «(Nome) –» identifica el marcador por sí solo: en BR el tratamiento
        # va DENTRO del marcador («O SR. PRESIDENTE (…) –»), así que exigir que no haya
        # tratamiento delante lo hacía invisible. Con paréntesis, no se aplica ese filtro.
        paren = CF._TERMINA_PAREN.match(c[i:i + 100])
        if not paren and CF._TRATO.search(c[max(0, g.start() - 12):g.start() + 1]):
            continue
        if CF._firma(c[max(0, g.start() - 60):g.start()]):
            continue
        if _ROTULO.match(c[i:i + 24]):        # rótulo de la carátula, no turno
            continue
        ab, ce = c.rfind("(", 0, i), c.rfind(")", 0, i)
        if ab > ce:
            continue
        n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", required=True)
    ap.add_argument("--etapa", default="corrected")
    ap.add_argument("--min", type=int, default=200, help="caracteres mínimos para publicarla")
    # ⚠ NO hay tope de longitud, y ponerlo fue un error. Llegué a filtrar por encima del 25 %
    # del acta temiendo que un prolegomena largo arrastrara discurso real. Es falso, y se mide:
    # el prolegomena de 1.312.864 caracteres de CL (91 % del acta) tiene **1 marcador de orador
    # frente a 96 en el resto**. Son `VI.- DOCUMENTOS DE LA CUENTA` y `VII.- OTROS DOCUMENTOS`,
    # los anexos íntegros, que en CL son enormes y perfectamente legítimos.
    # El criterio es uno solo: dónde empieza la primera intervención. Todo lo anterior es
    # Prolegomena, mida lo que mida.
    ap.add_argument("--medir", action="store_true", help="no escribe; informa qué recuperaría")
    a = ap.parse_args()
    iso = a.country.lower()
    csvp = f"source/{iso}/standardize/{iso.upper()}_interventions.csv"

    with open(csvp, encoding="utf-8") as fh:
        d = csv.Sniffer().sniff(fh.readline(), ";,").delimiter
        fh.seek(0)
        r = csv.DictReader(fh, delimiter=d)
        campos = list(r.fieldnames)
        filas = list(r)
    por = defaultdict(list)
    for i, x in enumerate(filas):
        por[x["date"]].append(i)

    fs = sorted(glob.glob(f"source/{iso}/{a.etapa}/*.txt") +
                glob.glob(f"source/{iso}/{a.etapa}/*.txt.gz"))
    nuevas, sin_ancla, cortas, ncar, grandes = defaultdict(list), 0, 0, 0, []
    for p in fs:
        m = FECHA.search(os.path.basename(p))
        if not m or (f := f"{m.group(1)}-{m.group(2)}-{m.group(3)}") not in por:
            continue
        # solo las primeras filas de la fecha pueden abrir el acta
        cands = [filas[i]["text"] for i in por[f][:40]]
        t = _abre(p)
        c = limpia(cabecera(t, cands))
        if not c:
            sin_ancla += 1
            continue
        if len(c) < a.min:
            cortas += 1
            continue
        nuevas[f].append((os.path.basename(p), c))
        ncar += len(c)
        grandes.append((os.path.basename(p), len(c), len(t)))

    n_act = sum(len(v) for v in nuevas.values())
    print(f"  {iso.upper()} · actas con Prolegomena: {n_act:,} de {len(fs):,}"
          f" · {ncar:,} caracteres")
    print(f"   sin ancla en el corpus: {sin_ancla:,} · más cortos que {a.min}: {cortas:,}")
    # Los más largos se informan, no se filtran: en CL son los anexos íntegros de la Cuenta.
    for nm, lc, lt in sorted(grandes, key=lambda z: -z[1])[:3]:
        print(f"      el más largo · {nm[:34]:35} {lc:>9,} de {lt:>9,}  ({lc/lt:.0%})")

    # ── VERIFICACIÓN DEL CORTE ────────────────────────────────────────────────
    # Se corta en la primera intervención; el control es que no haya quedado NINGÚN marcador
    # de intervención dentro. La longitud no dice nada: el Prolegomena de 1.312.864 caracteres
    # de CL es legítimo —son los DOCUMENTOS DE LA CUENTA— y tiene 1 marcador frente a 96 en el
    # resto del acta. Lo que delata un corte tardío es el marcador, no el tamaño.
    det = detector(filas)
    sucios = []
    for f, v in nuevas.items():
        for nm, c in v:
            k = marcadores_dentro(c, det)
            if k:
                sucios.append((nm, k, len(c)))
    lim = sum(k for _, k, _ in sucios)
    print(f"   ✔ verificación del corte: {len(sucios):,} de {n_act:,} Prolegomena con algún"
          f" marcador dentro ({len(sucios)/max(n_act,1)*100:.2f}%) · {lim:,} marcadores en total")
    for nm, k, lc in sorted(sucios, key=lambda z: -z[1])[:5]:
        print(f"      ⚠ {nm[:38]:39} {k:>4} marcadores en {lc:,} car.")
    if a.medir:
        for f in list(nuevas)[:2]:
            nm, c = nuevas[f][0]
            print(f"\n  ── {nm} ──\n   " + c[:400].replace("\n", "\n   ") + " …")
        return

    # `dm_speech` se estrena aquí, y se puebla con la única evidencia que tenemos: 0 en los
    # Prolegomena —que sabemos que no son intervención— y 1 en todo lo demás. No afirma que el
    # resto sea discurso; afirma que no está detectado como no-discurso. Los detectores de
    # sumario, votación y documento reproducido irán bajando ese 1 a medida que se midan.
    if "dm_speech" not in campos:
        campos = campos[:campos.index("text")] + ["dm_speech"] + campos[campos.index("text"):]
        for x in filas:
            x["dm_speech"] = "1"
    plantilla = {k: "" for k in campos}
    out, ins = [], 0
    hechas = defaultdict(int)
    for i, x in enumerate(filas):
        f = x["date"]
        if i == por[f][0] and nuevas.get(f):
            for nm, c in nuevas[f]:
                y = dict(plantilla)
                for k in ("legislature", "session_number", "date", "session_type"):
                    y[k] = x.get(k, "")
                y["dm_speech"] = "0"
                y["intervention_order"] = "0"     # Prolegomena: preceden sin desplazar nada
                y["text"] = c
                out.append(y)
                ins += 1
            hechas[f] += 1
        out.append(x)
    bak = csvp.replace(".csv", ".pre_caratula.csv")
    tmp = csvp + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos, delimiter=d)
        w.writeheader()
        w.writerows(out)
    if not os.path.exists(bak):
        os.rename(csvp, bak)
    else:
        os.remove(csvp)
    os.rename(tmp, csvp)
    print(f"  ✓ {ins:,} carátulas incorporadas · corpus {len(filas):,} → {len(out):,} filas"
          f" · copia previa {os.path.basename(bak)}")


if __name__ == "__main__":
    main()
