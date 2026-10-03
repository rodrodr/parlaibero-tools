"""Fallo 4: diaries-report inflaba la vinculación efectiva (≈6 puntos en PY: 98,39 % frente a 92,33 %).

El Paso 3-bis del SKILL.md traía un `python3 -c` propio que descontaba como «rol» cualquier orador
con PRESIDENT/SECRETARI/MESA —incluidas personas nombradas y el PRESIDENTE anónimo, que es
diputado— y contaba esas filas como vinculadas. Estas pruebas ejecutan LITERALMENTE los bloques
bash del Paso 3-bis sobre un proyecto sintético y comprueban qué cifra tomaría el informe.

ADAPTACIÓN (23-09-2026). La DECISIÓN de las 17:40, que el usuario delegó en el orquestador, fija
como cifra canónica del informe la definición vigente tr-0109: la del bloque `linkage` de
docs/{iso}/corpus_info.json. La versión anterior de estas pruebas daba por hecha la definición
tr-0003 de vinculacion_efectiva.py: esperaba 70,59 % en un ZZ sin paquete ni corpus_info.json y
comparaba con la tabla de ese script. Ahora el proyecto sintético trae paquete y corpus_info.json
(diaries-lib/tests/_diaries_lib_vinculacion_sintetica.py) y las pruebas exigen:
- que la cifra del informe sea la de tr-0109 (75,00 %) y coincida con la publicada;
- que el informe diga qué definición usa;
- que el skill no dependa de un script suelto del proyecto;
- y que tr-0003 (62,63 %) quede solo como comparación.
El fragmento antiguo da 81,5 %.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

SKILLS = Path(__file__).resolve().parents[2]
SKILL_MD = SKILLS / "diaries-report" / "SKILL.md"
LIB = SKILLS / "diaries-lib"
TR0109 = LIB / "lib" / "utils" / "vinculacion_tr0109.py"

if str(LIB / "tests") not in sys.path:
    sys.path.insert(0, str(LIB / "tests"))
from _diaries_lib_vinculacion_sintetica import ESPERADO, crea_proyecto  # noqa: E402


def _paso_3bis() -> str:
    texto = SKILL_MD.read_text(encoding="utf-8")
    m = re.search(r"^## Paso 3-bis.*?(?=^## )", texto, flags=re.S | re.M)
    assert m, "no se encuentra el Paso 3-bis en diaries-report/SKILL.md"
    return m.group(0)


def _bloques_bash(seccion: str) -> list[str]:
    return re.findall(r"```bash\n(.*?)```", seccion, flags=re.S)


@pytest.fixture
def proyecto(tmp_path: Path) -> Path:
    """ZZ: tr-0109 = 60 / (112 − 20 − 12) = 75,00 %, lo mismo que publica su corpus_info.json."""
    return crea_proyecto(tmp_path)


def _efectiva_que_tomaria_el_informe(proyecto: Path) -> float:
    """Ejecuta los bloques bash del Paso 3-bis tal como los ejecutaría el modelo y devuelve la
    vinculación efectiva (en %) que el informe copiaría."""
    salida = ""
    for bloque in _bloques_bash(_paso_3bis()):
        cmd = (bloque.replace("{iso2}", "zz").replace("{ISO2}", "ZZ")
               .replace("~/.claude/skills", str(SKILLS)))
        r = subprocess.run(["bash", "-c", cmd], cwd=proyecto, capture_output=True, text=True, timeout=120,
                           env={"PATH": f"{Path(sys.executable).parent}:/usr/bin:/bin", "HOME": str(Path.home()),
                                **({"PYTHONDONTWRITEBYTECODE": "1"} if sys.dont_write_bytecode else {})})
        assert r.returncode == 0, f"el bloque del SKILL falla:\n{cmd}\n{r.stdout}\n{r.stderr}"
        salida += r.stdout
    js = proyecto / "docs" / "zz" / "vinculacion_efectiva.json"
    if js.exists():
        return json.loads(js.read_text(encoding="utf-8"))["paises"]["ZZ"]["efectiva_pct"]
    m = re.search(r"efectiva\s+([\d.,]+)\s*%", salida, flags=re.I)
    assert m, f"no se encuentra la efectiva en la salida:\n{salida}"
    return float(m.group(1).replace(",", "."))


def _tr0109(proyecto: Path, *args: str) -> dict:
    r = subprocess.run([sys.executable, str(TR0109), "--country", "zz", "--json", *args], cwd=proyecto,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    return json.loads(r.stdout)


def test_el_informe_toma_la_efectiva_tr0109(proyecto):
    assert _efectiva_que_tomaria_el_informe(proyecto) == ESPERADO["efectiva_pct"]


def test_la_cifra_del_informe_es_la_de_corpus_info_y_la_del_script(proyecto):
    """Sea cual sea el comando del SKILL, su cifra debe coincidir con la publicada en
    corpus_info.json y con la de vinculacion_tr0109.py."""
    efectiva = _efectiva_que_tomaria_el_informe(proyecto)
    L = json.loads((proyecto / "docs/zz/corpus_info.json").read_text(encoding="utf-8"))["linkage"]
    assert efectiva == float(f"{L['effective'] * 100:.2f}")
    d = _tr0109(proyecto)
    assert d["definicion"]["id"] == "tr-0109"
    assert efectiva == d["paises"]["ZZ"]["efectiva_pct"]


def test_el_informe_dice_que_definicion_usa(proyecto):
    _efectiva_que_tomaria_el_informe(proyecto)
    js = proyecto / "docs" / "zz" / "vinculacion_efectiva.json"
    assert js.exists(), "el Paso 3-bis no deja el JSON del que copia el informe"
    d = json.loads(js.read_text(encoding="utf-8"))
    assert d["definicion"]["id"] == "tr-0109"
    assert "tr-0109" in d["paises"]["ZZ"]["texto_informe"]
    assert "texto_informe" in _paso_3bis()
    plantilla = SKILL_MD.read_text(encoding="utf-8").split("## Paso 5", 1)[1]
    assert "texto_informe" in plantilla, "la plantilla del informe no reserva sitio a la vinculación"


def test_el_skill_no_trae_heuristica_propia_ni_depende_del_proyecto(proyecto):
    seccion = _paso_3bis()
    assert "vinculacion_tr0109.py" in seccion and "tr-0109" in seccion
    for patron in ("any(k in", "ROL=(", "(n-otro)/n", "python3 -c"):
        assert patron not in seccion, f"el Paso 3-bis conserva la heurística por subcadena: {patron!r}"
    assert "roles sin nombre propio" not in seccion, "regla contraria a la canónica (SKILL.md:139)"
    assert "99,4 %" not in seccion, "tabla histórica que ningún script reproduce"
    for bloque in _bloques_bash(seccion):
        assert "linkage_no_atribuibles" not in bloque and "scripts/" not in bloque, bloque


def test_tr0003_disponible_solo_para_comparar(proyecto):
    assert "--comparar tr-0003" in _paso_3bis()
    d = _tr0109(proyecto, "--comparar", "tr-0003")
    assert d["paises"]["ZZ"]["efectiva_pct"] == ESPERADO["efectiva_pct"]
    assert d["comparacion"]["definicion"]["id"] == "tr-0003"
    assert d["comparacion"]["paises"]["ZZ"]["efectiva_pct"] == ESPERADO["tr0003_efectiva_pct"]
