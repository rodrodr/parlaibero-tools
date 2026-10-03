#!/usr/bin/env python3
"""BR: vincula por NOMBRE PARLAMENTARIO, que es como el acta nombra a los diputados.

Lo señaló el investigador (2026-08-10): «VICENTINHO, ERIKA KOKAY, LUIZ LIMA, HILDO ROCHA, JOSÉ
MEDEIROS… están en el padrón y no vinculan». Y es exacto — el padrón fuente
`source/br/deputies/deputados_BR.csv` trae DOS nombres por persona:

    nome       Vicentinho                       ← el que usa el Diário
    nomeCivil  VICENTE PAULO DA SILVA           ← el que se usó para casar

El match se hizo contra el civil, así que **todo el que firma con nombre parlamentario quedó
fuera**: 1.121 formas distintas y **41.545 filas**. Además el padrón publicado se construyó solo
con los que vincularon —3.682 personas de las 7.858 de la fuente—, de modo que los no vinculados
ni siquiera aparecían en él.

`id_dep` = `BR` + el número final de la `uri` de dadosabertos
(`…/api/v2/deputados/220593` → `BR220593`), que es la convención ya usada en el corpus.

**Desambiguación:** 320 nombres parlamentarios están repetidos en la fuente. Se resuelve con la
legislatura de la fila —el corpus usa `BR54` y la fuente `idLegislaturaInicial/Final`—, y lo que
siga sin resolverse **se deja sin vincular**: 798 filas de 41.545, y un hueco declarado vale más
que una atribución inventada ([[feedback_primacia_del_diario]]).

CLI:
    python br_match_nome_parlamentar.py [--medir]
"""
import argparse
import csv
import os
import re
import sys
import unicodedata
from collections import defaultdict

csv.field_size_limit(sys.maxsize)
CORPUS = "source/br/standardize/BR_interventions.csv"
PADRON = "source/br/standardize/BR_deputies.csv"
FUENTE = "source/br/deputies/deputados_BR.csv"


def _N(s):
    s = "".join(c for c in unicodedata.normalize("NFD", str(s).upper())
                if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Z0-9]+", "", s)


def _lee(p):
    with open(p, encoding="utf-8") as fh:
        d = csv.Sniffer().sniff(fh.readline(), ";,").delimiter
        fh.seek(0)
        r = csv.DictReader(fh, delimiter=d)
        return list(r.fieldnames), list(r), d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--medir", action="store_true")
    a = ap.parse_args()

    _, src, _ = _lee(FUENTE)
    uri = next(k for k in src[0] if "uri" in k.lower())
    por = defaultdict(list)
    for x in src:
        n = re.search(r"(\d+)\s*$", (x[uri] or "").rstrip("/"))
        if not n or not x.get("nome"):
            continue
        try:
            li, lf = int(x["idLegislaturaInicial"]), int(x["idLegislaturaFinal"])
        except (ValueError, TypeError):
            li, lf = 0, 99
        por[_N(x["nome"])].append(
            {"id": "BR" + n.group(1), "nome": x["nome"], "sexo": (x.get("siglaSexo") or "").strip(),
             "li": li, "lf": lf})

    campos, filas, d = _lee(CORPUS)
    pcampos, padron, pd_ = _lee(PADRON)
    ya = {x["id_dep"] for x in padron}

    vinc = ambig = 0
    nuevos = {}
    for x in filas:
        if x["id_dep"].strip():
            continue
        cand = por.get(_N(x["speaker_raw"]))
        if not cand:
            continue
        if len(cand) > 1:                      # desempata la legislatura de la propia fila
            g = re.search(r"(\d+)", x.get("legislature", "") or "")
            if g:
                k = int(g.group(1))
                cand = [c for c in cand if c["li"] <= k <= c["lf"]] or cand
        if len(cand) != 1:
            ambig += 1
            continue
        c = cand[0]
        vinc += 1
        if not a.medir:
            x["id_dep"], x["speaker_name"] = c["id"], c["nome"]
            if c["sexo"] in ("M", "F"):
                x["sex"] = c["sexo"]
        if c["id"] not in ya:
            nuevos.setdefault((c["id"], x.get("legislature", "")), c)

    print(f"  BR · filas vinculadas por nombre parlamentario: {vinc:,}")
    print(f"     sin resolver por nombre repetido (se dejan vacías): {ambig:,}")
    print(f"     personas nuevas para el padrón: {len({k[0] for k in nuevos}):,}"
          f" ({len(nuevos):,} filas persona×legislatura)")
    if a.medir:
        return

    for (idp, leg), c in nuevos.items():
        f = {k: "" for k in pcampos}
        f["id_dep"], f["speaker_name"], f["legislature"] = idp, c["nome"], leg
        if c["sexo"] in ("M", "F"):
            f["sex"], f["sex_source"] = c["sexo"], "official_registry"
        f["notes"] = "alta 2026-08-10: vinculado por nome parlamentar"
        padron.append(f)

    for p, cs, rs, sep in ((CORPUS, campos, filas, d), (PADRON, pcampos, padron, pd_)):
        bak = p.replace(".csv", ".pre_nomeparl.csv")
        tmp = p + ".tmp"
        with open(tmp, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=cs, delimiter=sep)
            w.writeheader()
            w.writerows(rs)
        if not os.path.exists(bak):
            os.rename(p, bak)
        else:
            os.remove(p)
        os.rename(tmp, p)
    print(f"  ✓ corpus y padrón reescritos · padrón {len(padron):,} filas")


if __name__ == "__main__":
    main()
