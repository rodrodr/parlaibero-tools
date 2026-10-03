"""Arreglo 4 según la DECISIÓN del 23-09-2026 (17:40): la vinculación efectiva del informe es tr-0109.

tr-0109 es la definición vigente y la publicada en docs/{iso}/corpus_info.json:

    efectiva = vinculadas / (filas de habla − sin escaño − no atribuibles)

Hasta ahora solo la calculaba linkage_no_atribuibles.py, un script suelto del proyecto ParlaIbero.
Su parte de vinculación pasa a diaries-lib/lib/utils/vinculacion_tr0109.py, que solo lee. Estas
pruebas fijan:
- las cifras sobre el proyecto sintético (tests/_diaries_lib_vinculacion_sintetica.py);
- la EQUIVALENCIA con el script original, ejecutado sobre una copia del proyecto sintético;
- la equivalencia sobre una COPIA de PY: 93,91 %, la cifra publicada (se salta si no hay datos);
- la discrepancia con corpus_info.json (salida 1), los errores de entorno (salida 2), --out atómico
  que nunca pisa una entrada, y tr-0003 disponible solo para comparar.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import LIB_ROOT
from _diaries_lib_vinculacion_sintetica import ESPERADO, crea_proyecto, linkage_publicado

TR0109 = LIB_ROOT / "lib" / "utils" / "vinculacion_tr0109.py"
PROYECTO_REAL = Path(os.environ.get("DIARIES_PROYECTO", str(Path.cwd())))
ORIGINAL = PROYECTO_REAL / "scripts/campana_reproceso/_reocr_ec/linkage_no_atribuibles.py"
# sha256 de PY_interventions.csv el día de la medición (24-09-2026): 275.887 / (360.201 − 66.431 − 0)
PY_SHA256_MEDIDO = "76a37ed2856d8ae19552c7ae58dd392c9ef3f30f3a6e0d2c0e5b25dd834ad194"

# Formas límite para la equivalencia: la herramienta tiene que reproducir el script original
# también en sus rarezas («El señor.» con punto NO casa por el \b final; id_dep " " cuenta como
# vinculada; dm_speech vacío no es habla).
EXTRA_EQUIVALENCIA = [
    ("Vozes do PSD", "", "1"), ("Uma voz do PS", "", "1"), ("- Varios señores Diputados", "", "1"),
    ("El señor.", "", "1"), ("N.N", "", "1"), ("Aplausos", "", "1"), ("  varios  ", "", "1"),
    ("La señora", "", "1"), ("Un diputado", "", "1"), ("El señor Presidente", "", "1"),
    ("Otro señor", "", "1"), ("X", " ", "1"), ("Rumores", "", "0"), ("", "ZZ099", ""),
]


def _corre(cwd, *args):
    return subprocess.run([sys.executable, str(TR0109), *args], cwd=cwd,
                          capture_output=True, text=True, timeout=600)


def _json(cwd, *args):
    r = _corre(cwd, "--json", *args)
    return r, json.loads(r.stdout)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.fixture
def zz(tmp_path):
    return crea_proyecto(tmp_path / "p")


def test_cifras_tr0109_del_proyecto_sintetico(zz):
    r, d = _json(zz, "--country", "zz")
    assert r.returncode == 0, r.stdout + r.stderr
    assert d["definicion"]["id"] == "tr-0109"
    c = d["paises"]["ZZ"]
    assert (c["filas"], c["filas_habla"], c["vinculadas"]) == (119, 112, 60)
    assert (c["sin_escano_descontadas"], c["no_atribuibles"], c["denominador"]) == (20, 12, 80)
    assert c["filas_sin_orador"] == ESPERADO["filas_sin_orador"]
    assert (c["efectiva_pct"], c["bruta_pct"]) == (75.0, 53.57)
    assert c["efectiva"] == round(60 / 80, 12) and c["bruta"] == round(60 / 112, 12)
    assert c["corpus_info"]["coincide"] is True and c["corpus_info"]["diferencias"] == []
    assert c["entrada"]["origen"] == "paquete"
    assert c["entrada"]["sha256"] == _sha(zz / "source/zz/standardize/ZZ_interventions.csv")
    assert c["corpus_info"]["sha256"] == _sha(zz / "docs/zz/corpus_info.json")
    for clave in ("script", "script_sha256", "generado", "comando"):
        assert d[clave], clave
    assert d["generado"].endswith("+00:00")
    assert "comparacion" not in d


def test_el_texto_del_informe_dice_la_definicion_y_de_donde_sale_cada_cifra(zz):
    _, d = _json(zz, "--country", "zz")
    t = d["paises"]["ZZ"]["texto_informe"]
    for trozo in ("tr-0109", "53,57 %", "75,00 %", "112 filas de habla", "60 vinculadas",
                  "20 filas", "12 no atribuibles", "docs/zz/corpus_info.json", "Coincide"):
        assert trozo in t, trozo


def test_equivalencia_con_el_script_original_del_proyecto(tmp_path):
    """El script del proyecto, sobre una COPIA de un proyecto sintético, reescribe su bloque linkage
    (se parte de cifras falsas); la herramienta tiene que dar exactamente esas mismas cifras."""
    if not ORIGINAL.exists():
        pytest.skip(f"no está el script original: {ORIGINAL}")
    falso = linkage_publicado(total_rows=1, speech_rows=1, linked=1, gross=0.1,
                              unattributable_rows=0, effective=0.1, rows_without_speaker=0)
    p = crea_proyecto(tmp_path / "p", linkage=falso, extra=EXTRA_EQUIVALENCIA)
    r = subprocess.run([sys.executable, str(ORIGINAL), "zz"], cwd=p, capture_output=True,
                       text=True, timeout=600)
    assert r.returncode == 0, r.stderr
    L = json.loads((p / "docs/zz/corpus_info.json").read_text(encoding="utf-8"))["linkage"]
    assert L["speech_rows"] != 1, "el script original no recalculó el bloque"
    r, d = _json(p, "--country", "zz")
    assert r.returncode == 0, r.stdout + r.stderr
    c = d["paises"]["ZZ"]
    assert (c["filas"], c["filas_habla"], c["vinculadas"], c["no_atribuibles"],
            c["filas_sin_orador"], c["sin_escano_descontadas"]) == (
        L["total_rows"], L["speech_rows"], L["linked"], L["unattributable_rows"],
        L["rows_without_speaker"], L["cannot_hold_seat_discounted"])
    assert (c["efectiva"], c["bruta"]) == (L["effective"], L["gross"])
    assert c["corpus_info"]["coincide"] is True


def test_la_regex_de_no_atribuibles_es_la_del_original():
    if not ORIGINAL.exists():
        pytest.skip(f"no está el script original: {ORIGINAL}")
    patron = re.compile(r'^RX = re\.compile\(r"(.*)"\)\s*$', re.M)
    original = patron.findall(ORIGINAL.read_text(encoding="utf-8"))
    nuestra = patron.findall(TR0109.read_text(encoding="utf-8"))
    assert len(original) == 1 and nuestra == original


@pytest.fixture(scope="module")
def py_copia(tmp_path_factory):
    """COPIA de PY (paquete + corpus_info.json). Se ejecuta la herramienta sobre la copia intacta;
    después, si está, el script original sobre la misma copia, y otra vez la herramienta."""
    ci = PROYECTO_REAL / "docs/py/corpus_info.json"
    pk = PROYECTO_REAL / "dataverse/paquetes/PY/PY_interventions.csv"
    if not (ci.is_file() and pk.is_file()):
        pytest.skip("no hay datos de PY para la prueba de equivalencia")
    raiz = tmp_path_factory.mktemp("copia_py")
    (raiz / "docs/py").mkdir(parents=True)
    (raiz / "dataverse/paquetes/PY").mkdir(parents=True)
    shutil.copyfile(ci, raiz / "docs/py/corpus_info.json")
    shutil.copyfile(pk, raiz / "dataverse/paquetes/PY/PY_interventions.csv")
    entradas = [raiz / "docs/py/corpus_info.json", raiz / "dataverse/paquetes/PY/PY_interventions.csv"]
    antes = [_sha(x) for x in entradas]
    r1, d1 = _json(raiz, "--country", "py")
    intactas = [_sha(x) for x in entradas] == antes
    publicado = json.loads(entradas[0].read_text(encoding="utf-8"))["linkage"]
    res = dict(r1=r1, d1=d1, publicado=publicado, intactas=intactas)
    if ORIGINAL.exists():
        ro = subprocess.run([sys.executable, str(ORIGINAL), "py"], cwd=raiz, capture_output=True,
                            text=True, timeout=600)
        assert ro.returncode == 0, ro.stderr
        res["original"] = json.loads(entradas[0].read_text(encoding="utf-8"))["linkage"]
        res["r2"], res["d2"] = _json(raiz, "--country", "py")
    return res


def test_copia_de_py_da_93_91(py_copia):
    r, c = py_copia["r1"], py_copia["d1"]["paises"]["PY"]
    if c["entrada"]["sha256"] != PY_SHA256_MEDIDO:
        pytest.skip("PY ha cambiado desde la medición del 24-09-2026: la cifra fija no aplica")
    assert r.returncode == 0, r.stdout
    assert c["efectiva_pct"] == 93.91
    assert (c["vinculadas"], c["filas_habla"], c["sin_escano_descontadas"], c["no_atribuibles"]) == (
        275887, 360201, 66431, 0)
    assert c["efectiva"] == py_copia["publicado"]["effective"] == 0.939125846751
    assert c["corpus_info"]["coincide"] is True
    assert py_copia["intactas"], "la herramienta modificó la copia"


def test_copia_de_py_equivale_al_script_original(py_copia):
    if "original" not in py_copia:
        pytest.skip(f"no está el script original: {ORIGINAL}")
    L, r, c = py_copia["original"], py_copia["r2"], py_copia["d2"]["paises"]["PY"]
    assert r.returncode == 0, r.stdout
    assert (c["filas"], c["filas_habla"], c["vinculadas"], c["no_atribuibles"], c["filas_sin_orador"]) == (
        L["total_rows"], L["speech_rows"], L["linked"], L["unattributable_rows"], L["rows_without_speaker"])
    assert (c["efectiva"], c["bruta"]) == (L["effective"], L["gross"])


def test_discrepancia_con_corpus_info_sale_con_1_y_lo_dice(tmp_path):
    p = crea_proyecto(tmp_path / "p", linkage=linkage_publicado(linked=59, effective=round(59 / 80, 12)))
    r, d = _json(p, "--country", "zz")
    assert r.returncode == 1
    c = d["paises"]["ZZ"]
    assert c["efectiva_pct"] == 75.0                     # la cifra es la recalculada, no la publicada
    assert c["corpus_info"]["coincide"] is False
    assert {x["campo"] for x in c["corpus_info"]["diferencias"]} == {"linked", "effective"}
    assert "No coincide" in c["texto_informe"]


def test_sin_escano_ausente_cuenta_cero_como_tr0109_y_avisa(tmp_path):
    L = linkage_publicado(effective=round(60 / 100, 12))
    del L["cannot_hold_seat_discounted"]
    p = crea_proyecto(tmp_path / "p", linkage=L)
    r, d = _json(p, "--country", "zz")
    assert r.returncode == 0, r.stdout
    c = d["paises"]["ZZ"]
    assert (c["sin_escano_descontadas"], c["efectiva_pct"]) == (0, 60.0)
    assert any("cannot_hold_seat_discounted" in a for a in c["avisos"])
    assert "cannot_hold_seat_discounted" in c["texto_informe"]


def test_cannot_hold_seat_discounted_float_entero_se_acepta(tmp_path):
    """Repro de g_a/ataque_vinculacion.py (T3): 20.0 (float con valor entero exacto) representa el
    mismo descuento que 20 (int); un generador futuro de corpus_info.json podría escribirlo así."""
    p = crea_proyecto(tmp_path / "p", linkage=linkage_publicado(cannot_hold_seat_discounted=20.0))
    r, d = _json(p, "--country", "zz")
    assert r.returncode == 0, d.get("error") or (r.stdout + r.stderr)
    c = d["paises"]["ZZ"]
    assert c["sin_escano_descontadas"] == 20
    assert c["efectiva_pct"] == 75.0
    assert c["corpus_info"]["coincide"] is True


@pytest.mark.parametrize("valor", [20.5, -1.0], ids=["no_entero", "negativo"])
def test_cannot_hold_seat_discounted_float_no_entero_o_negativo_se_rechaza(tmp_path, valor):
    """20.5 no es un entero exacto y -1.0 es negativo: ninguno de los dos se acepta (a diferencia
    de 20.0, que sí); se sigue rechazando con salida 2, como antes de este arreglo."""
    p = crea_proyecto(tmp_path / "p", linkage=linkage_publicado(cannot_hold_seat_discounted=valor))
    r, d = _json(p, "--country", "zz")
    assert r.returncode == 2
    assert "cannot_hold_seat_discounted" in d["error"]


def test_definicion_publicada_que_no_cita_tr0109_avisa(tmp_path):
    p = crea_proyecto(tmp_path / "p", linkage=linkage_publicado(definition="linked / (total - named)"))
    _, d = _json(p, "--country", "zz")
    c = d["paises"]["ZZ"]
    assert c["corpus_info"]["declara_tr0109"] is False
    assert any("tr-0109" in a for a in c["avisos"])


def test_sin_paquete_usa_standardize_y_lo_dice(tmp_path):
    p = crea_proyecto(tmp_path / "p", paquete=False)
    r, d = _json(p, "--country", "zz")
    assert r.returncode == 0, r.stdout
    c = d["paises"]["ZZ"]
    assert c["entrada"]["origen"].startswith("standardize") and c["efectiva_pct"] == 75.0
    assert "source/zz/standardize/ZZ_interventions.csv" in c["texto_informe"]


def test_separador_punto_y_coma(tmp_path):
    p = crea_proyecto(tmp_path / "p", sep=";")
    r, d = _json(p, "--country", "zz")
    assert r.returncode == 0, r.stdout
    c = d["paises"]["ZZ"]
    assert (c["entrada"]["separador"], c["efectiva_pct"]) == (";", 75.0)


def test_bom_utf8_antes_de_id_dep_no_rompe_la_columna(tmp_path):
    """Repro de g_a/ataque_vinculacion.py (T1): un CSV con BOM UTF-8 y 'id_dep' como primera
    columna no debe dar un falso 'no tiene la columna id_dep' (el BOM se pegaba al nombre de la
    cabecera: '\\ufeffid_dep'). Bajo, barato: leer con encoding='utf-8-sig'."""
    raiz = tmp_path / "p"
    std = raiz / "source" / "zz" / "standardize"
    std.mkdir(parents=True)
    docs = raiz / "docs" / "zz"
    docs.mkdir(parents=True)
    contenido = "id_dep,speaker_raw,dm_speech\nZZ001,Juan Pérez,1\n,PRESIDENTE,1\n,RELATOR,1\n"
    (std / "ZZ_interventions.csv").write_bytes(b"\xef\xbb\xbf" + contenido.encode("utf-8"))
    (docs / "corpus_info.json").write_text(json.dumps(
        {"linkage": linkage_publicado(cannot_hold_seat_discounted=1, total_rows=3, speech_rows=3,
                                      linked=1, unattributable_rows=0, rows_without_speaker=0,
                                      gross=round(1 / 3, 12), effective=round(1 / 2, 12))}),
        encoding="utf-8")
    r, d = _json(raiz, "--country", "zz")
    assert r.returncode == 0, d.get("error") or (r.stdout + r.stderr)
    c = d["paises"]["ZZ"]
    assert (c["filas"], c["filas_habla"], c["vinculadas"]) == (3, 3, 1)
    assert c["corpus_info"]["coincide"] is True


def _sin_corpus_info(p):
    (p / "docs/zz/corpus_info.json").unlink()


def _sin_linkage(p):
    (p / "docs/zz/corpus_info.json").write_text('{"country": "ZZ"}', encoding="utf-8")


def _corpus_info_roto(p):
    (p / "docs/zz/corpus_info.json").write_text("{no es json", encoding="utf-8")


def _sin_datos(p):
    (p / "dataverse/paquetes/ZZ/ZZ_interventions.csv").unlink()
    (p / "source/zz/standardize/ZZ_interventions.csv").unlink()


def _enlace_roto(p):
    (p / "source/zz/standardize/ZZ_interventions.csv").unlink()


def _csv(texto):
    def f(p):
        (p / "source/zz/standardize/ZZ_interventions.csv").write_text(texto, encoding="utf-8")
    return f


def _sin_escano_texto(p):
    ci = p / "docs/zz/corpus_info.json"
    ci.write_text(json.dumps({"linkage": linkage_publicado(cannot_hold_seat_discounted="20")}),
                  encoding="utf-8")


@pytest.mark.parametrize("rompe, fragmento, pais", [
    (_sin_corpus_info, "corpus_info.json", "zz"),
    (_sin_linkage, "linkage", "zz"),
    (_corpus_info_roto, "JSON", "zz"),
    (_sin_datos, "no existe", "zz"),
    (_enlace_roto, "enlace roto", "zz"),
    (_csv("date,speaker_raw,dm_speech\n2001-01-01,PRESIDENTE,1\n"), "id_dep", "zz"),
    (_csv("date,id_dep,dm_speech\n2001-01-01,ZZ001,1\n"), "speaker_raw", "zz"),
    (_csv("date,speaker_raw,id_dep,dm_speech\n"), "filas", "zz"),
    (_csv("date,speaker_raw,id_dep,dm_speech\n2001-01-01,PRESIDENTE,,0\n"), "habla", "zz"),
    (_sin_escano_texto, "cannot_hold_seat_discounted", "zz"),
    (lambda p: None, "no existe", "qq"),
], ids=["sin_corpus_info", "sin_linkage", "corpus_info_roto", "sin_csv", "enlace_roto",
        "sin_id_dep", "sin_speaker_raw", "sin_filas", "sin_habla", "sin_escano_texto", "pais_ausente"])
def test_errores_de_entorno_salen_con_2_y_no_escriben(zz, rompe, fragmento, pais):
    rompe(zz)
    out = zz / "docs" / pais / "vinculacion_efectiva.json"
    r = _corre(zz, "--country", pais, "--json", "--out", str(out))
    assert r.returncode == 2, r.stdout + r.stderr
    assert fragmento in json.loads(r.stdout)["error"]
    assert not out.exists()
    r = _corre(zz, "--country", pais)                     # sin --json: el error va a stderr
    assert r.returncode == 2 and fragmento in r.stderr and not r.stdout


def test_out_atomico_no_toca_las_entradas_y_resume_en_pantalla(zz):
    entradas = [zz / "source/zz/standardize/ZZ_interventions.csv", zz / "docs/zz/corpus_info.json"]
    antes = [x.read_bytes() for x in entradas]
    out = zz / "docs/zz/nuevo/vinculacion_efectiva.json"
    r = _corre(zz, "--country", "zz", "--out", str(out))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "tr-0109" in r.stdout and "75,00 %" in r.stdout
    assert json.loads(out.read_text(encoding="utf-8"))["paises"]["ZZ"]["efectiva_pct"] == 75.0
    assert not [x for x in out.parent.iterdir() if x.name.endswith(".tmp")]
    assert [x.read_bytes() for x in entradas] == antes


@pytest.mark.parametrize("destino", ["source/zz/standardize/ZZ_interventions.csv",
                                     "dataverse/paquetes/ZZ/ZZ_interventions.csv",
                                     "docs/zz/corpus_info.json"])
def test_out_nunca_sobrescribe_una_entrada(zz, destino):
    p = zz / destino
    antes = p.read_bytes()
    r = _corre(zz, "--country", "zz", "--out", str(p))
    assert r.returncode == 2
    assert "entrada" in r.stderr          # rechazo explícito, no un fallo cualquiera
    assert p.read_bytes() == antes
    assert (zz / "dataverse/paquetes/ZZ/ZZ_interventions.csv").is_symlink()


def test_tr0003_queda_solo_para_comparar(zz):
    r, d = _json(zz, "--country", "zz", "--comparar", "tr-0003")
    assert r.returncode == 0, r.stdout
    c = d["paises"]["ZZ"]
    assert c["efectiva_pct"] == 75.0                      # la cifra del informe no cambia
    k = d["comparacion"]
    assert k["definicion"]["id"] == "tr-0003"
    assert k["paises"]["ZZ"]["efectiva_pct"] == ESPERADO["tr0003_efectiva_pct"]
    assert k["diferencia_puntos"] == round(75.0 - ESPERADO["tr0003_efectiva_pct"], 2)
    assert "62,63" not in c["texto_informe"]
