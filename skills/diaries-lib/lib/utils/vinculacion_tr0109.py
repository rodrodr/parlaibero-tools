#!/usr/bin/env python3
"""Vinculación efectiva con la definición vigente tr-0109, la del bloque `linkage` de
docs/{iso}/corpus_info.json. Es la cifra que publica diaries-report.

    efectiva = vinculadas / (filas de habla − sin escaño − no atribuibles)

- Filas de habla: `dm_speech == "1"` (si el CSV no trae la columna, todas).
- Vinculadas: filas de habla con `id_dep`.
- No atribuibles: filas de habla sin vincular cuyo `speaker_raw` está vacío o es una voz colectiva
  o un anónimo («Varios señores diputados», «Un señor DIPUTADO», «El señor» sin nombre, «N.N.»).
- Sin escaño: NO se reclasifica. Es `linkage.cannot_hold_seat_discounted` del corpus_info.json del
  país, que cada país calcula con la convención de su tabla (tr-0156); tr-0109 lo hereda igual.
- La presidencia sin nombre (`PRESIDENTE` a secas) no se descuenta: quien preside es diputado.

Es la parte de vinculación de linkage_no_atribuibles.py (proyecto ParlaIbero,
scripts/campana_reproceso/_reocr_ec/, tr-0109, 2026-09-03), traída al skill para que diaries-report
no dependa de un script suelto del proyecto. Lee el paquete (dataverse/paquetes/{ISO}/) o, si no
hay paquete, el CSV de standardize, y lo dice. Solo lee: nunca escribe corpus_info.json ni el CSV.
La equivalencia está probada en tests/test_diaries_lib_vinculacion_tr0109.py, contra el script
original sobre datos sintéticos y sobre una copia de PY (93,91 %, la cifra publicada).

Salida: 0 si la cifra coincide con la publicada en corpus_info.json; 1 si no coincide (el JSON se
escribe igual y dice en qué difiere); 2 si no se puede calcular.

Uso, desde la raíz del proyecto:
    python3 vinculacion_tr0109.py --country py [--json] [--out docs/py/vinculacion_efectiva.json]
                                  [--comparar tr-0003]
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from salida_json import (ErrorEntorno, comprueba_destino, escribe_atomico,  # noqa: E402
                         procedencia, sale_con_error, sha256)

csv.field_size_limit(sys.maxsize)

DEFINICION = {
    "id": "tr-0109",
    "formula": "efectiva = vinculadas / (filas de habla − sin escaño − no atribuibles)",
    "descripcion": ("Sobre las filas de habla (dm_speech = 1). Se descuenta a quien no puede tener "
                    "escaño (linkage.cannot_hold_seat_discounted de corpus_info.json, sin "
                    "reclasificar) y lo que el acta no permite atribuir: voces colectivas, anónimos "
                    "y filas sin orador. La presidencia sin nombre no se descuenta."),
    "decision": "tr-0109 (2026-09-03) en state/_transversal/decisions.jsonl; amplía tr-0003",
    "cifra_del_informe": True,
}

# Copia literal de linkage_no_atribuibles.py (tr-0109), rarezas incluidas: «El señor.» con punto no
# casa por el \b final. Cambiarla cambia la cifra publicada; la prueba compara las dos líneas.
RX = re.compile(r"(?i)^(?:-?\s*)?(?:vozes|voces|una voz|uma voz|un señor|una señora|varios|varias|algunos|algumas|muitas|diversos|dos señores|un diputado|otros señores|otro señor|el señor\.?$|la señora\.?$|n\.n\.?|rumores|aplausos|risas|murmullos|gritos|protestas|vários|vezes do|dozes do)\b")

# (clave de corpus_info.json, clave propia, se compara como porcentaje a dos decimales)
_COMPARA = (("total_rows", "filas", False), ("speech_rows", "filas_habla", False),
            ("linked", "vinculadas", False), ("unattributable_rows", "no_atribuibles", False),
            ("rows_without_speaker", "filas_sin_orador", False),
            ("gross", "bruta", True), ("effective", "efectiva", True))
_PUBLICADO = ("total_rows", "speech_rows", "linked", "cannot_hold_seat_discounted",
              "unattributable_rows", "rows_without_speaker", "gross", "effective")


def _es(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _pct(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


def _rutas(iso: str):
    I = iso.upper()
    return (Path(f"dataverse/paquetes/{I}/{I}_interventions.csv"),
            Path(f"source/{iso}/standardize/{I}_interventions.csv"),
            Path(f"docs/{iso}/corpus_info.json"))


def _entrada(iso: str):
    paquete, std, _ = _rutas(iso)
    if paquete.is_symlink() and not paquete.exists():
        raise ErrorEntorno(f"enlace roto en {paquete}: no se calcula sobre un fichero que no se puede abrir")
    if paquete.is_file():
        return paquete, "paquete"
    if std.is_file():
        return std, "standardize (no hay paquete)"
    raise ErrorEntorno(f"no existe {paquete} ni {std}")


def _linkage(iso: str):
    p = _rutas(iso)[2]
    if not p.is_file():
        raise ErrorEntorno(f"no existe {p}: tr-0109 toma de ahí el descuento «sin escaño»")
    try:
        ci = json.loads(p.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ErrorEntorno(f"{p} no es JSON válido: {e}") from None
    L = ci.get("linkage") if isinstance(ci, dict) else None
    if not isinstance(L, dict):
        raise ErrorEntorno(f"{p} no tiene bloque linkage: tr-0109 toma de ahí el descuento «sin escaño»")
    return p, L


def _cuenta(ruta: Path) -> dict:
    """El recuento de linkage_no_atribuibles.py: mismas condiciones y en el mismo orden."""
    with open(ruta, encoding="utf-8-sig") as fh:
        cab = fh.readline()
        try:
            sep = csv.Sniffer().sniff(cab, ";,").delimiter
        except csv.Error:
            raise ErrorEntorno(f"{ruta}: no se reconoce el separador de la cabecera") from None
        fh.seek(0)
        rd = csv.DictReader(fh, delimiter=sep)
        faltan = [c for c in ("speaker_raw", "id_dep") if c not in (rd.fieldnames or ())]
        if faltan:
            raise ErrorEntorno(f"{ruta} no tiene la columna {' ni '.join(faltan)}")
        n = hab = lig = unat = nos = 0
        for r in rd:
            n += 1
            orador = r.get("speaker_raw") or ""
            if not orador:
                nos += 1
            if r.get("dm_speech", "1") != "1":
                continue
            hab += 1
            if r.get("id_dep"):
                lig += 1
                continue
            if not orador.strip() or RX.match(orador.strip()):
                unat += 1
    if not n:
        raise ErrorEntorno(f"{ruta} no tiene filas")
    if not hab:
        raise ErrorEntorno(f"{ruta} no tiene filas de habla (dm_speech = 1)")
    return {"sep": sep, "n": n, "hab": hab, "lig": lig, "unat": unat, "nos": nos}


def _entero_no_negativo(x: Any) -> Optional[int]:
    """`x` como int si es un entero (o un float con valor entero exacto, p. ej. 20.0) y ≥ 0; None
    si no lo es. Un generador de corpus_info.json podría escribir el descuento como float sin que
    deje de ser, semánticamente, el mismo entero."""
    if isinstance(x, bool):
        return None
    if isinstance(x, int):
        return x if x >= 0 else None
    if isinstance(x, float) and x.is_integer():
        return int(x) if x >= 0 else None
    return None


def calcula(iso: str):
    """Cifras tr-0109 de un país, comparadas con su corpus_info.json: (cifras, coincide)."""
    ruta, origen = _entrada(iso)
    p_ci, L = _linkage(iso)
    avisos = []
    if "cannot_hold_seat_discounted" in L:
        ext_crudo = L["cannot_hold_seat_discounted"]
        ext = _entero_no_negativo(ext_crudo)
        if ext is None:
            raise ErrorEntorno(f"{p_ci}: linkage.cannot_hold_seat_discounted no es un entero ≥ 0 ({ext_crudo!r})")
    else:
        ext = 0
        avisos.append(f"{p_ci} no trae linkage.cannot_hold_seat_discounted: se descuentan 0 filas "
                      "sin escaño, como hace tr-0109")
    c = _cuenta(ruta)
    den = c["hab"] - ext - c["unat"]
    if den <= 0:
        raise ErrorEntorno(f"denominador {den}: las filas descontadas ({ext} sin escaño y {c['unat']} "
                           f"no atribuibles) igualan o superan las {c['hab']} de habla")
    efectiva = round(c["lig"] / den, 12)
    res = {"filas": c["n"], "filas_habla": c["hab"], "vinculadas": c["lig"],
           "sin_escano_descontadas": ext, "no_atribuibles": c["unat"], "filas_sin_orador": c["nos"],
           "denominador": den, "bruta": round(c["lig"] / c["hab"], 12),
           "bruta_pct": float(f"{c['lig'] / c['hab'] * 100:.2f}"),
           "efectiva": efectiva, "efectiva_pct": float(f"{efectiva * 100:.2f}")}

    diferencias = []
    for clave, propia, es_pct in _COMPARA:
        if clave not in L:
            continue
        pub, mia = L[clave], res[propia]
        if es_pct:
            igual = isinstance(pub, (int, float)) and f"{pub * 100:.2f}" == f"{mia * 100:.2f}"
        else:
            igual = pub == mia
        if not igual:
            diferencias.append({"campo": clave, "publicado": pub, "recalculado": mia})
    if "effective" not in L:
        diferencias.append({"campo": "effective", "publicado": None, "recalculado": efectiva})
    coincide = not diferencias
    declara = "tr-0109" in str(L.get("definition", ""))
    if not declara:
        avisos.append(f"la definición publicada en {p_ci} no cita tr-0109")

    de_donde = f"del paquete {ruta}" if origen == "paquete" else f"de {ruta}, porque no hay paquete"
    texto = (f"Vinculación, definición tr-0109 (la del bloque linkage de {p_ci}): bruta "
             f"{_pct(res['bruta_pct'])} % y efectiva {_pct(res['efectiva_pct'])} % sobre "
             f"{_es(c['hab'])} filas de habla {de_donde}: {_es(c['lig'])} vinculadas; se descuentan "
             f"{_es(ext)} filas de quien no puede tener escaño (cifra de corpus_info.json, que "
             f"tr-0109 no reclasifica) y {_es(c['unat'])} no atribuibles (voces colectivas y "
             f"anónimos). La presidencia sin nombre no se descuenta.")
    if coincide:
        texto += f" Coincide con la cifra publicada en {p_ci}."
    else:
        texto += (f" No coincide con la cifra publicada en {p_ci} (difieren: "
                  f"{', '.join(d['campo'] for d in diferencias)}): ese corpus_info.json no describe "
                  "estos datos.")
    texto += "".join(f" Aviso: {a}." for a in avisos)

    res.update({
        "entrada": {"ruta": str(ruta), "origen": origen, "ruta_real": str(ruta.resolve()),
                    "sha256": sha256(ruta), "separador": c["sep"]},
        "corpus_info": {"ruta": str(p_ci), "sha256": sha256(p_ci), "declara_tr0109": declara,
                        "publicado": {k: L[k] for k in _PUBLICADO if k in L},
                        "coincide": coincide, "diferencias": diferencias},
        "avisos": avisos, "texto_informe": texto})
    return res, coincide


def _compara_tr0003(iso: str, pais: dict) -> dict:
    import vinculacion_efectiva as tr0003
    try:
        _, c = tr0003.cifras(iso)
    except ErrorEntorno as e:
        return {"definicion": tr0003.DEFINICION, "error": str(e)}
    return {"definicion": tr0003.DEFINICION, "nota": "solo para comparar: no es la cifra del informe",
            "paises": {iso.upper(): c},
            "diferencia_puntos": round(pais["efectiva_pct"] - c["efectiva_pct"], 2)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Vinculación efectiva tr-0109, la de corpus_info.json.")
    ap.add_argument("--country", required=True, help="ISO2 del país (py, br...)")
    ap.add_argument("--json", action="store_true", help="imprime el JSON en vez del resumen")
    ap.add_argument("--out", help="escribe el JSON aquí (atómico, nunca sobre una entrada)")
    ap.add_argument("--comparar", choices=["tr-0003"],
                    help="añade la definición anterior, solo para comparar")
    a = ap.parse_args(argv)
    iso, I = a.country.lower(), a.country.upper()
    try:
        destino = comprueba_destino(a.out, _rutas(iso)) if a.out else None
        pais, coincide = calcula(iso)
        salida = {**procedencia(__file__), "definicion": DEFINICION, "paises": {I: pais}}
        if a.comparar:
            salida["comparacion"] = _compara_tr0003(iso, pais)
        if destino:
            escribe_atomico(destino, salida)
    except ErrorEntorno as e:
        return sale_con_error(str(e), a.json)
    except OSError as e:
        return sale_con_error(f"no se pudo leer o escribir: {e}", a.json)
    if a.json:
        print(json.dumps(salida, ensure_ascii=False, indent=2))
    else:
        print(f"{I} · tr-0109 · efectiva {_pct(pais['efectiva_pct'])} % · bruta {_pct(pais['bruta_pct'])} %")
        print(pais["texto_informe"])
        k = salida.get("comparacion")
        if k:
            print(f"Comparación tr-0003 (no es la cifra del informe): "
                  + (f"efectiva {_pct(k['paises'][I]['efectiva_pct'])} %" if "paises" in k else k["error"]))
    return 0 if coincide else 1


if __name__ == "__main__":
    sys.exit(main())
