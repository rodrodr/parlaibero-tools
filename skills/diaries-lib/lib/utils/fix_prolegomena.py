#!/usr/bin/env python3
"""Repara los Prolegomena que traen un turno dentro. Dos males distintos, una sola regla.

Tras recuperar la carátula ([[feedback_prolegomena]]) quedaron 923 Prolegomena con algún
marcador de intervención dentro. Comprobando si ese turno está o no en el corpus de su fecha,
resultaron ser DOS fenómenos opuestos:

    613  el turno FALTA del corpus  → el Prolegomena es la ÚNICA copia de una intervención real
    222  el texto está DUPLICADO   → el corte llegó tarde y repite lo que ya está

Enterrar una intervención real bajo `dm_speech = 0` es peor que no haberla recuperado, y repetir
texto infla el corpus. La regla que resuelve ambos sin decidir a ojo:

    se corta en el PRIMER marcador cuyo texto ya esté en el corpus —de ahí en adelante todo es
    duplicado y sobra— y los marcadores ANTERIORES, cuyo texto no está en ninguna fila, salen
    como intervenciones recuperadas.

Las recuperadas se vinculan con la `matching_table.csv` del propio país y toman sus atributos
del padrón, así que no bajan la tasa de vinculación. Se insertan DELANTE de la primera
intervención existente y la jornada se renumera: son turnos de pleno derecho, no preliminares,
y el 0 se reserva para lo que de verdad no es intervención.

CLI:
    python fix_prolegomena.py --country mx [--medir]
"""
import argparse
import csv
import os
import re
import sys
import unicodedata
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import conformidad as CF
import recover_frontmatter as R

csv.field_size_limit(sys.maxsize)
ANCLA = 150          # cuánto texto tras el marcador se busca en el corpus para decidir

# Rótulos de ROL de la institución (es/pt). La presidencia y la secretaría intervienen aunque
# no tengan `id_dep` —en CR son anónimas— y por eso una forma de rol vale como orador aunque
# no vincule con el padrón.
_ROL = re.compile(r"\b(?:PRESIDEN(?:TE|TA|CIA)|VICEPRESIDEN(?:TE|TA)|SECRETARI[OA]|"
                  r"SECRETARI|MESA\s+DIRECTIVA|MODERADOR[A]?)\b")


def _N(s):
    s = "".join(c for c in unicodedata.normalize("NFD", str(s).upper())
                if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Z0-9]+", "", s)


def marcas(t, det):
    """Posiciones de los marcadores de turno reales, con los mismos filtros que la verificación."""
    out = []
    for g in det.finditer(t):
        i = g.end()
        if not CF._TERMINA.match(t[i:i + 20]):
            continue
        if CF._LISTA.match(t[i:i + 56]):
            continue
        # Mismo criterio que en recover_frontmatter: el terminador «(Nome) –» identifica el
        # marcador por sí solo, y en BR el tratamiento va DENTRO del marcador.
        if not CF._TERMINA_PAREN.match(t[i:i + 100]) \
           and CF._TRATO.search(t[max(0, g.start() - 12):g.start() + 1]):
            continue
        if CF._firma(t[max(0, g.start() - 60):g.start()]):
            continue
        if R._ROTULO.match(t[i:i + 24]):
            continue
        ab, ce = t.rfind("(", 0, i), t.rfind(")", 0, i)
        if ab > ce:
            continue
        out.append((g.start(), i, g.group(0).strip()))
    return out


def _lee(p, sep=None):
    with open(p, encoding="utf-8") as fh:
        d = sep or csv.Sniffer().sniff(fh.readline(), ";,").delimiter
        fh.seek(0)
        r = csv.DictReader(fh, delimiter=d)
        return list(r.fieldnames), list(r), d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", required=True)
    ap.add_argument("--medir", action="store_true")
    a = ap.parse_args()
    iso = a.country.lower()
    I = iso.upper()
    csvp = f"source/{iso}/standardize/{I}_interventions.csv"
    campos, filas, d = _lee(csvp)

    # tabla de match del país: speaker_raw → id_dep, y atributos del padrón
    tab = {}
    mp = f"source/{iso}/match/matching_table.csv"
    if os.path.exists(mp):
        _, mt, _ = _lee(mp)
        tab = {_N(x["speaker_raw"]): x["id_dep"] for x in mt if x.get("id_dep", "").strip()}
    # nombre del padrón → id_dep: BR escribe QUIÉN preside dentro del paréntesis del marcador
    # («O SR. PRESIDENTE (José Sarney) –»), así que ese nombre vincula el turno recuperado.
    pornombre = {}
    atr = {}
    dp = f"source/{iso}/standardize/{I}_deputies.csv"
    if os.path.exists(dp):
        _, dep, _ = _lee(dp)
        for x in dep:
            atr.setdefault(x["id_dep"], {}).setdefault(
                x.get("legislature", ""),
                (x.get("speaker_name", ""), x.get("sex", ""), x.get("party", ""), x.get("district", "")))
            if x.get("speaker_name", "").strip():
                pornombre.setdefault(_N(x["speaker_name"]), x["id_dep"])

    det = R.detector(filas)
    porf = defaultdict(list)
    for i, x in enumerate(filas):
        porf[x["date"]].append(i)
    corp = {f: _N("\n".join(filas[i]["text"] for i in ix if filas[i]["intervention_order"] != "0"))
            for f, ix in porf.items()}

    nuevas = defaultdict(list)      # fecha → [filas recuperadas]
    recort = trozos = 0
    for x in filas:
        if x["intervention_order"] != "0":
            continue
        t = x["text"]
        ms = marcas(t, det)
        if not ms:
            continue
        cn = corp.get(x["date"], "")
        # primer marcador cuyo texto YA está en el corpus: de ahí en adelante, duplicado
        corte = len(t)
        for s, i, _f in ms:
            if _N(t[i:i + ANCLA * 2])[:ANCLA] in cn:
                corte = s
                break
        if corte < len(t):
            recort += 1
        # los marcadores anteriores al corte son turnos perdidos
        prev = [m for m in ms if m[0] < corte]
        if prev:
            cab = t[:prev[0][0]].strip()
            for k, (s, i, forma) in enumerate(prev):
                fin = prev[k + 1][0] if k + 1 < len(prev) else corte
                cuerpo = t[i:fin]
                # El paréntesis que sigue al cargo NOMBRA a quien lo ocupa: no es cuerpo del
                # turno, es parte del marcador. Se separa y sirve para vincular.
                nombrado = ""
                mp2 = re.match(r"\s*\(([^)\n]{0,90})\)\s*[:—–-]\s*", cuerpo)
                if mp2:
                    nombrado = re.split(r"[.,;]", mp2.group(1))[0].strip()
                    cuerpo = cuerpo[mp2.end():]
                cuerpo = cuerpo.strip(" \n:.—–-")
                if len(cuerpo) < 20:
                    continue
                # ⚠ No todo lo que parece marcador abre un turno. En ES los «turnos» eran
                # entradas del ORDEN DEL DÍA —«MINISTRO DE TRABAJO…: ¿…? (Número de expediente
                # 1801001933)»— y convertirlas en intervenciones habría sido inventar habla.
                # Se convierte solo si la forma VINCULA con el padrón o es un rol de mesa del
                # país (la presidencia es anónima en CR y aun así interviene). Lo demás se
                # queda dentro del Prolegomena, que es donde no hace daño.
                idp = tab.get(_N(forma), "") or (pornombre.get(_N(nombrado), "") if nombrado else "")
                if nombrado:
                    forma = f"{forma} ({nombrado})"
                if not idp and not _ROL.search(_N(forma)):
                    continue
                y = {c: "" for c in campos}
                for c in ("legislature", "session_number", "date", "session_type"):
                    y[c] = x.get(c, "")
                y["speaker_raw"] = forma
                y["dm_speech"] = "1"
                y["text"] = cuerpo
                if idp:
                    v = atr.get(idp, {})
                    nm, sx, pa, di = v.get(y["legislature"]) or (next(iter(v.values())) if v else ("", "", "", ""))
                    y["id_dep"], y["speaker_name"], y["sex"], y["party"], y["district"] = idp, nm, sx, pa, di
                nuevas[x["date"]].append(y)
                trozos += 1
            x["text"] = cab
        else:
            x["text"] = t[:corte].strip()

    vinc = sum(1 for v in nuevas.values() for y in v if y["id_dep"])
    print(f"  {I} · Prolegomena recortados por duplicado: {recort:,}"
          f" · turnos recuperados: {trozos:,} (vinculados {vinc:,}, {vinc/max(trozos,1)*100:.0f}%)")
    if a.medir:
        for f, v in list(nuevas.items())[:2]:
            for y in v[:2]:
                print(f"   [{f}] [{y['speaker_raw'][:26]}] id={y['id_dep'] or '—'} "
                      f"{y['text'][:110]!r}".replace("\\n", " ⏎ "))
        return

    # las recuperadas van DELANTE de la primera intervención de su jornada y se renumera
    out = []
    puesto = set()
    for i, x in enumerate(filas):
        f = x["date"]
        if x["intervention_order"] != "0" and f not in puesto and f in nuevas:
            out.extend(nuevas[f])
            puesto.add(f)
        out.append(x)
    cnt = defaultdict(int)
    for y in out:
        if y["intervention_order"] == "0":
            continue
        k = (y.get("legislature", ""), y["date"], y.get("session_number", "").strip())
        cnt[k] += 1
        y["intervention_order"] = str(cnt[k])
    # los Prolegomena que se quedaron vacíos tras el recorte no se publican
    out = [y for y in out if y["intervention_order"] != "0" or len(y["text"].strip()) >= 200]

    bak = csvp.replace(".csv", ".pre_fixprol.csv")
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
    print(f"  ✓ corpus {len(filas):,} → {len(out):,} filas")


if __name__ == "__main__":
    main()
