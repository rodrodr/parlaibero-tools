"""Fallo 4 (lado de la lib): vinculacion_efectiva.py solo imprimía una tabla.

El script gana --json y --out (salida JSON con procedencia). La tabla por defecto no cambia.

ADAPTACIÓN (23-09-2026, DECISIÓN de las 17:40): este script es la definición tr-0003 y NO da la
cifra del informe. La de diaries-report es tr-0109 (vinculacion_tr0109.py, pruebas en
test_diaries_lib_vinculacion_tr0109.py); tr-0003 queda para comparar. Por eso la prueba que se
llamaba «cifras canónicas» pasa a llamarse test_json_con_las_cifras_tr0003 y exige, además, que el
JSON declare su definición. Las cifras esperadas no cambian: son las de tr-0003.

Fixture (tests/fixtures/vinculacion): ZZ con 105 filas —60 vinculadas, 10 RELATOR, 10 SECRETARIO
(Administrativo), 10 PRESIDENTE, 5 «EL SEÑOR MARIO ROSSI, PRESIDENTE DE LA COMISIÓN», 5 sin padrón,
2 SECRETARIO ambiguo y 3 «Primer Secretario»— e YY con 20 filas separadas por «;».
"""
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import FIXTURES, VINCULACION

FIX = FIXTURES / "vinculacion"


def _corre(cwd, *args):
    return subprocess.run([sys.executable, str(VINCULACION), *args], cwd=cwd,
                          capture_output=True, text=True, timeout=120)


@pytest.fixture
def proyecto_vinc(tmp_path):
    shutil.copytree(FIX / "source", tmp_path / "source")
    return tmp_path


def test_tabla_por_defecto_identica_a_la_original(proyecto_vinc):
    r = _corre(proyecto_vinc)
    assert r.returncode == 0
    assert r.stdout == (FIXTURES / "vinculacion_tabla_esperada.txt").read_text(encoding="utf-8")
    r = _corre(proyecto_vinc, "--country", "zz")
    assert r.stdout == (FIXTURES / "vinculacion_tabla_esperada_zz.txt").read_text(encoding="utf-8")


def test_json_con_las_cifras_tr0003(proyecto_vinc):
    r = _corre(proyecto_vinc, "--country", "zz", "--json")
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert d["definicion"]["id"] == "tr-0003"
    zz = d["paises"]["ZZ"]
    assert (zz["filas"], zz["vinculadas"]) == (105, 60)
    assert zz["no_diputado_descontado"] == 20           # 10 RELATOR + 10 SECRETARIO (Administrativo)
    assert zz["presidencia_sin_identificar"] == 10      # PRESIDENTE a secas: NO se descuenta
    assert zz["ambiguo"] == 2
    assert zz["resto_sin_vincular"] == 13               # 5 Rossi + 5 sin padrón + 3 Mesa
    assert zz["bruta_pct"] == 57.14
    assert zz["efectiva_pct"] == 70.59                  # 60 / (105 − 20)
    assert zz["efectiva_si_ambiguos_funcionarios_pct"] == 72.29
    assert zz["efectiva"] == pytest.approx(60 / 85)
    assert zz["separador"] == ","
    csv_zz = proyecto_vinc / "source/zz/standardize/ZZ_interventions.csv"
    assert zz["sha256"] == hashlib.sha256(csv_zz.read_bytes()).hexdigest()
    assert d["total"]["efectiva_pct"] == 70.59
    for clave in ("script", "script_sha256", "generado", "comando", "definicion"):
        assert d[clave], clave


def test_json_todos_los_paises_y_separador_punto_y_coma(proyecto_vinc):
    r = _corre(proyecto_vinc, "--json")
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert sorted(d["paises"]) == ["YY", "ZZ"]
    yy = d["paises"]["YY"]
    assert yy["separador"] == ";" and yy["efectiva_pct"] == 88.24 and yy["no_diputado_descontado"] == 3
    t = d["total"]
    assert (t["filas"], t["vinculadas"], t["no_diputado_descontado"]) == (125, 75, 23)
    assert t["efectiva_pct"] == 73.53 and t["efectiva_si_ambiguos_funcionarios_pct"] == 75.0
    assert t["horquilla_puntos"] == 1.47


def test_out_escribe_atomico_y_sigue_imprimiendo_la_tabla(proyecto_vinc):
    out = proyecto_vinc / "docs" / "zz" / "vinculacion_efectiva.json"
    r = _corre(proyecto_vinc, "--country", "zz", "--out", str(out))
    assert r.returncode == 0, r.stderr
    assert r.stdout == (FIXTURES / "vinculacion_tabla_esperada_zz.txt").read_text(encoding="utf-8")
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["paises"]["ZZ"]["efectiva_pct"] == 70.59
    assert not [x for x in out.parent.iterdir() if x.name.endswith(".tmp")]


def test_json_error_de_entorno_sale_con_2(proyecto_vinc, tmp_path):
    r = _corre(proyecto_vinc, "--country", "qq", "--json")
    assert r.returncode == 2
    assert "error" in json.loads(r.stdout)
    vacio = tmp_path / "vacio"; vacio.mkdir()
    r = _corre(vacio, "--json")
    assert r.returncode == 2


def test_json_sin_columna_id_dep_no_da_cero_silencioso(proyecto_vinc):
    p = proyecto_vinc / "source/zz/standardize/ZZ_interventions.csv"
    p.write_text("speaker_raw,texto\nPRESIDENTE,hola\n", encoding="utf-8")
    r = _corre(proyecto_vinc, "--country", "zz", "--json")
    assert r.returncode == 2
    assert "id_dep" in json.loads(r.stdout)["error"]


def test_out_nunca_sobrescribe_una_entrada(proyecto_vinc):
    p = proyecto_vinc / "source/zz/standardize/ZZ_interventions.csv"
    antes = p.read_bytes()
    r = _corre(proyecto_vinc, "--country", "zz", "--out", str(p))
    assert r.returncode == 2
    assert "entrada" in r.stderr          # rechazo explícito, no el de argparse por opción desconocida
    assert p.read_bytes() == antes
