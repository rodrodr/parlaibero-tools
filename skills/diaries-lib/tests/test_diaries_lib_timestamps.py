"""Fallo 3: marcas de tiempo con datetime.utcnow() (obsoleto en 3.12, y sin zona).

`python3 -W error::DeprecationWarning update_state.py ... --status running` terminaba con ok:false.
Ahora las marcas se generan con datetime.now(timezone.utc) y llevan la zona (+00:00).
"""
import json
from datetime import datetime, timedelta, timezone

from conftest import lee_estado, update_state

from lib.schemas import CorrectionRecord, CorrectionType
from lib.state_manager import StateManager


def _utc(s: str) -> datetime:
    d = datetime.fromisoformat(s)
    assert d.tzinfo is not None, f"marca sin zona: {s}"
    assert d.utcoffset() == timedelta(0), f"marca no UTC: {s}"
    return d


def test_update_state_sin_deprecation_warning(proyecto):
    for status in ("running", "complete"):
        r = update_state(proyecto, "--country", "zz", "--skill", "diaries-ocr", "--session", "s1",
                         "--status", status, "--confidence", "0.9", warn_error=True)
        assert r.returncode == 0, r.stdout + r.stderr
        assert json.loads(r.stdout)["ok"] is True


def test_mark_skill_marca_en_utc_con_zona(proyecto):
    sm = StateManager(proyecto, "zz"); sm.load()
    antes = datetime.now(timezone.utc)
    sm.mark_skill(session_id="a", skill="diaries-ocr", status="running")
    sm.mark_skill(session_id="a", skill="diaries-ocr", status="complete", confidence=0.9)
    despues = datetime.now(timezone.utc)
    sk = lee_estado(proyecto, "zz")["sessions"]["a"]["skills"]["diaries-ocr"]
    assert antes <= _utc(sk["started_at"]) <= _utc(sk["completed_at"]) <= despues


def test_correction_record_timestamp_utc():
    antes = datetime.now(timezone.utc)
    c = CorrectionRecord(type=CorrectionType.RULE, description="x")
    assert antes <= _utc(c.timestamp) <= datetime.now(timezone.utc)


def test_marcas_antiguas_sin_zona_se_conservan(proyecto):
    """Las marcas ya escritas (naive, en UTC) no se reescriben: solo cambian las nuevas."""
    from conftest import escribe_estado, estado_sintetico
    p = escribe_estado(proyecto, "zz", estado_sintetico("zz", 3))
    sm = StateManager(proyecto, "zz"); sm.load()
    sm.mark_skill(session_id="nueva", skill="diaries-meta", status="complete")
    st = lee_estado(proyecto, "zz")
    assert st["sessions"]["SO_00000_2001-01-01"]["skills"]["diaries-correct"]["completed_at"] == \
        "2026-08-01T10:00:00.000000"
    _utc(st["sessions"]["nueva"]["skills"]["diaries-meta"]["completed_at"])
