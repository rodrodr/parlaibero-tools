"""Fallo 2: la confianza no tenía límites (patrones-13).

`--confidence 7.5`, `-3` y `nan` se guardaban con ok:true y Pydantic los recargaba sin error; en
state/co hay tres negativas reales en diaries-correct (−0,15; −0,011; −0,567). Se acota a [0, 1]
y cada valor anómalo queda REGISTRADO (state/{iso2}/confidence_anomalies.jsonl + aviso en stderr),
no escondido.
"""
import json
import math
import warnings
from concurrent.futures import ThreadPoolExecutor

import pytest

from conftest import escribe_estado, estado_sintetico, lee_estado, update_state

from lib.schemas import PipelineState, SkillState
from lib.state_manager import StateManager

try:                                   # antes del arreglo no existen: las pruebas fallan una a una
    from lib.schemas import ConfianzaFueraDeRango, acotar_confianza, confianza_no_numerica
except ImportError:                    # pragma: no cover
    ConfianzaFueraDeRango = type("NoExiste", (Warning,), {})
    acotar_confianza = None
    confianza_no_numerica = None

ANOM = "confidence_anomalies.jsonl"


def _anomalias(proyecto, pais="zz"):
    p = proyecto / "state" / pais / ANOM
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _conf(proyecto, sid, skill, pais="zz"):
    return lee_estado(proyecto, pais)["sessions"][sid]["skills"][skill]["confidence"]


@pytest.mark.parametrize("valor,esperado", [("7.5", 1.0), ("-0.15", 0.0), ("-3", 0.0), ("1.0000001", 1.0)])
def test_update_state_acota_y_registra(proyecto, valor, esperado):
    r = update_state(proyecto, "--country", "zz", "--skill", "diaries-tag", "--session", "s0",
                     "--status", "complete", "--confidence", valor)
    assert r.returncode == 0 and json.loads(r.stdout)["ok"] is True
    assert _conf(proyecto, "s0", "diaries-tag") == esperado
    an = _anomalias(proyecto)
    assert len(an) == 1
    assert an[0]["session"] == "s0" and an[0]["skill"] == "diaries-tag"
    assert an[0]["raw_confidence"] == float(valor) and an[0]["stored_confidence"] == esperado
    assert an[0]["source"] == "mark_skill"
    assert "fuera de [0, 1]" in r.stderr


def test_update_state_nan_no_se_guarda_como_numero(proyecto):
    r = update_state(proyecto, "--country", "zz", "--skill", "diaries-tag", "--session", "s0",
                     "--status", "complete", "--confidence", "nan")
    assert r.returncode == 0
    texto = (proyecto / "state" / "zz" / "pipeline_state.json").read_text(encoding="utf-8")
    assert "NaN" not in texto, "NaN no es JSON válido"
    assert _conf(proyecto, "s0", "diaries-tag") is None
    an = _anomalias(proyecto)
    assert an and an[0]["raw_confidence"] == "nan" and an[0]["stored_confidence"] is None


@pytest.mark.parametrize("valor", ["0", "1", "0.0", "1.0", "0.5"])
def test_valores_validos_intactos_y_sin_registro(proyecto, valor):
    r = update_state(proyecto, "--country", "zz", "--skill", "diaries-tag", "--session", "s0",
                     "--status", "complete", "--confidence", valor)
    assert r.returncode == 0
    assert _conf(proyecto, "s0", "diaries-tag") == float(valor)
    assert _anomalias(proyecto) == []
    assert "fuera de [0, 1]" not in r.stderr


def test_esquema_acota_al_validar_y_avisa():
    datos = {"country": "zz", "sessions": {"a": {"skills": {
        "diaries-correct": {"status": "complete", "confidence": -0.567},
        "diaries-tag": {"status": "complete", "confidence": 7.5},
        "diaries-meta": {"status": "complete", "confidence": 0.9}}}}}
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        st = PipelineState.model_validate(datos)
    sk = st.sessions["a"].skills
    assert sk["diaries-correct"].confidence == 0.0
    assert sk["diaries-tag"].confidence == 1.0
    assert sk["diaries-meta"].confidence == 0.9
    avisos = [x for x in w if issubclass(x.category, ConfianzaFueraDeRango)]
    assert len(avisos) == 2 and "-0.567" in str(avisos[0].message)


def test_acotar_confianza_casos_limite():
    assert acotar_confianza(None) == (None, False)
    assert acotar_confianza(0.0) == (0.0, False)
    assert acotar_confianza(1) == (1, False)
    assert acotar_confianza(-1e-9) == (0.0, True)
    assert acotar_confianza(float("inf")) == (None, True)
    v, a = acotar_confianza(float("nan"))
    assert v is None and a
    # Ronda 2 (ataque 1, hallazgo alto confidence-texto-por-asignacion-directa): lo no numérico
    # AHORA también es anómalo (antes se devolvía intacto confiando en que Pydantic lo rechazara,
    # pero una asignación directa a `.confidence` no pasa por Pydantic: ver test_diaries_lib_*
    # más abajo). Se acota a None, igual que un valor no finito.
    assert acotar_confianza("abc") == (None, True)
    assert acotar_confianza([1, 2]) == (None, True)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        sk = SkillState(confidence="abc")          # YA NO lanza: se acota y se avisa
    assert sk.confidence is None
    assert any(issubclass(x.category, ConfianzaFueraDeRango) for x in w)


def test_confianza_no_numerica_distingue_de_fuera_de_rango():
    """`confianza_no_numerica` distingue la causa «no es un número» (para el source
    "no_numerico" del registro) de un número simplemente fuera de [0, 1] o no finito."""
    assert confianza_no_numerica("abc") is True
    assert confianza_no_numerica("muy alta") is True
    assert confianza_no_numerica([1, 2]) is True
    assert confianza_no_numerica(None) is False
    assert confianza_no_numerica(True) is False
    assert confianza_no_numerica(7.5) is False            # fuera de rango, pero SÍ es un número
    assert confianza_no_numerica(-3) is False
    assert confianza_no_numerica(float("nan")) is False   # no finito, pero es un float
    assert confianza_no_numerica(float("inf")) is False
    assert confianza_no_numerica("0.8") is False           # texto que SÍ convierte a float


def test_estado_real_con_negativas_como_co(proyecto):
    """Réplica del caso CO: tres negativas en diaries-correct con status complete."""
    datos = estado_sintetico("zz", 10)
    malas = {"SO_00001_2001-01-01": -0.15, "SO_00002_2001-01-01": -0.011, "SO_00003_2001-01-01": -0.567}
    for sid, v in malas.items():
        datos["sessions"][sid]["skills"]["diaries-correct"]["confidence"] = v
    p = escribe_estado(proyecto, "zz", datos)
    antes = p.read_bytes()

    # 1) solo leer: en memoria acotado; en disco nada cambia ni se registra (no se esconde nada)
    sm = StateManager(proyecto, "zz")
    st = sm.load()
    assert all(st.sessions[s].skills["diaries-correct"].confidence == 0.0 for s in malas)
    assert p.read_bytes() == antes and _anomalias(proyecto) == []

    # 2) al guardar: el valor persistido queda en [0,1] y cada original queda en el registro
    sm.mark_skill(session_id="otra", skill="diaries-meta", status="complete", confidence=0.9)
    st2 = lee_estado(proyecto, "zz")
    for sid in malas:
        assert st2["sessions"][sid]["skills"]["diaries-correct"]["confidence"] == 0.0
    an = _anomalias(proyecto)
    assert sorted((a["session"], a["raw_confidence"], a["source"]) for a in an) == \
        sorted((s, v, "carga") for s, v in malas.items())

    # 3) guardar otra vez no duplica el registro
    sm2 = StateManager(proyecto, "zz"); sm2.load(); sm2.save()
    assert len(_anomalias(proyecto)) == 3


def test_asignacion_directa_se_acota_y_registra(proyecto):
    escribe_estado(proyecto, "zz", estado_sintetico("zz", 3))
    sm = StateManager(proyecto, "zz"); sm.load()
    sm.state.get_session("SO_00000_2001-01-01").get_skill("diaries-correct").confidence = 3.0
    sm.save()
    assert _conf(proyecto, "SO_00000_2001-01-01", "diaries-correct") == 1.0
    an = _anomalias(proyecto)
    assert len(an) == 1 and an[0]["raw_confidence"] == 3.0 and an[0]["source"] == "asignacion"
    assert sm.state.sessions["SO_00000_2001-01-01"].skills["diaries-correct"].confidence == 1.0


# ─────────────── ronda 2 (ataque 1): confidence-texto-por-asignacion-directa (alto) ───────────────
# `sk.confidence = "muy alta"` (mutación directa, el patrón que el propio docstring de
# state_manager.py documenta como soportado) no pasa por Pydantic (no hay validate_assignment): el
# texto llegaba a disco intacto, sin acotar ni registrar, y la SIGUIENTE carga lanzaba la traza
# cruda de pydantic.ValidationError, dejando el pipeline_state.json de todo un país ilegible.

def test_asignacion_directa_de_texto_se_acota_a_none_y_se_registra(proyecto, capsys):
    """Repro de g_a/ataque_confianza_texto.py: la asignación directa de un valor NO numérico debe
    acotarse a None y registrarse en confidence_anomalies.jsonl, igual que un fuera de rango.
    (`sm.save()` avisa por stderr con `_aviso`, no con `warnings.warn`: eso solo ocurre al VALIDAR
    con Pydantic, ver test_acotar_confianza_casos_limite más abajo para ese otro camino.)"""
    escribe_estado(proyecto, "zz", estado_sintetico("zz", 1))
    sm = StateManager(proyecto, "zz"); sm.load()
    sk = sm.state.get_session("SO_00000_2001-01-01").get_skill("diaries-correct")
    sk.confidence = "muy alta"

    sm.save()
    aviso = capsys.readouterr().err
    assert "fuera de [0, 1]" in aviso and "muy alta" in aviso, "no se avisó por stderr, se escondió"

    conf_en_disco = _conf(proyecto, "SO_00000_2001-01-01", "diaries-correct")
    assert conf_en_disco is None, f"debía quedar en None, no {conf_en_disco!r}"
    an = _anomalias(proyecto)
    assert len(an) == 1
    assert an[0]["raw_confidence"] == "muy alta"
    assert an[0]["stored_confidence"] is None
    assert an[0]["source"] == "no_numerico"
    assert sk.confidence is None, "en memoria también debe quedar acotada, no solo en disco"

    # Round-trip: una recarga posterior no debe fallar (el valor ya quedó limpio en disco).
    st2 = StateManager(proyecto, "zz").load()
    assert st2.sessions["SO_00000_2001-01-01"].skills["diaries-correct"].confidence is None


def test_load_no_lanza_traza_cruda_de_pydantic_con_confidence_no_numerica_en_disco(proyecto):
    """Si pipeline_state.json YA trae un valor no numérico (heredado, o escrito a mano), load() no
    debe lanzar pydantic.ValidationError: se acota a None, se registra al siguiente save() y el
    estado sigue siendo legible para todo el pipeline."""
    datos = estado_sintetico("zz", 1)
    datos["sessions"]["SO_00000_2001-01-01"]["skills"]["diaries-correct"]["confidence"] = "muy alta"
    escribe_estado(proyecto, "zz", datos)

    sm = StateManager(proyecto, "zz")
    st = sm.load()                                      # no debe lanzar
    assert st.sessions["SO_00000_2001-01-01"].skills["diaries-correct"].confidence is None

    sm.mark_skill(session_id="otra", skill="diaries-meta", status="complete", confidence=0.9)
    an = _anomalias(proyecto)
    assert any(a["raw_confidence"] == "muy alta" and a["stored_confidence"] is None
               and a["source"] == "no_numerico" for a in an)


def test_mark_skill_con_confianza_no_numerica_no_rompe(proyecto):
    """mark_skill(confidence=<texto>), llamado directamente por un script (no por la CLI, que
    filtra con argparse type=float), tampoco debe colar el texto sin acotar ni registrar."""
    sm = StateManager(proyecto, "zz")
    sm.mark_skill(session_id="s0", skill="diaries-tag", status="complete", confidence="alta")
    assert _conf(proyecto, "s0", "diaries-tag") is None
    an = _anomalias(proyecto)
    assert len(an) == 1
    assert an[0]["raw_confidence"] == "alta" and an[0]["source"] == "no_numerico"


def test_anomalias_de_carga_no_se_multiplican_con_concurrencia(proyecto):
    """8 procesos cargan a la vez un estado con 3 negativas: el registro debe tener 3, no 24."""
    datos = estado_sintetico("zz", 500)
    for i in (1, 2, 3):
        datos["sessions"][f"SO_0000{i}_2001-01-01"]["skills"]["diaries-correct"]["confidence"] = -0.1 * i
    escribe_estado(proyecto, "zz", datos)

    def uno(i):
        return update_state(proyecto, "--country", "zz", "--skill", "diaries-meta", "--session",
                            f"c{i}", "--status", "complete", "--confidence", "0.8")

    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(uno, range(8)))
    assert all(r.returncode == 0 for r in res)
    an = _anomalias(proyecto)
    assert len(an) == 3, f"{len(an)} registros de carga para 3 anomalías"
    st = lee_estado(proyecto, "zz")
    assert all(f"c{i}" in st["sessions"] for i in range(8))
    assert all(not (isinstance(sk.get("confidence"), float) and (sk["confidence"] < 0 or sk["confidence"] > 1))
               for s in st["sessions"].values() for sk in s["skills"].values())
