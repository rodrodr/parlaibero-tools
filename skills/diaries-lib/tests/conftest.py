"""Utilidades comunes de las pruebas de diaries-lib.

Las pruebas nunca tocan datos reales: cada una trabaja en un proyecto temporal (tmp_path) con
la misma estructura que un proyecto ParlaIbero (state/{iso2}/pipeline_state.json).
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

LIB_ROOT = Path(__file__).resolve().parents[1]          # .../diaries-lib (contiene lib/)
TESTS_DIR = Path(__file__).resolve().parent
UPDATE_STATE = LIB_ROOT / "lib" / "utils" / "update_state.py"
VINCULACION = LIB_ROOT / "lib" / "utils" / "vinculacion_efectiva.py"
FIXTURES = TESTS_DIR / "fixtures"

for _p in (str(LIB_ROOT), str(TESTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def estado_sintetico(pais: str, n_sesiones: int, skills=("diaries-extract", "diaries-correct")) -> dict:
    """Estado con n sesiones ya completas, serializado igual que StateManager (model_dump)."""
    from lib.schemas import PipelineState, SkillStatus

    st = PipelineState(country=pais, current_skill="diaries-correct")
    for i in range(n_sesiones):
        ses = st.get_session(f"SO_{i:05d}_2001-01-01")
        for k in skills:
            sk = ses.get_skill(k)
            sk.status = SkillStatus.COMPLETE.value
            sk.confidence = 0.93
            sk.output_path = f"source/{pais}/corrected/SO_{i:05d}.txt"
            sk.completed_at = "2026-08-01T10:00:00.000000"
    return st.model_dump()


def escribe_estado(proyecto: Path, pais: str, datos: dict) -> Path:
    p = proyecto / "state" / pais / "pipeline_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def lee_estado(proyecto: Path, pais: str) -> dict:
    return json.loads((proyecto / "state" / pais / "pipeline_state.json").read_text(encoding="utf-8"))


def update_state(proyecto: Path, *args: str, warn_error: bool = False) -> subprocess.CompletedProcess:
    cmd = [sys.executable]
    if warn_error:
        cmd += ["-W", "error::DeprecationWarning"]
    cmd += [str(UPDATE_STATE), *args]
    return subprocess.run(cmd, cwd=proyecto, capture_output=True, text=True, timeout=300)


@pytest.fixture
def proyecto(tmp_path: Path) -> Path:
    (tmp_path / "state").mkdir()
    return tmp_path
