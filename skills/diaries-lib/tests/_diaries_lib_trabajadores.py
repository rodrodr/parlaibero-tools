"""Funciones de nivel de módulo para multiprocessing (spawn necesita poder importarlas)."""
import json
import sys
import time
from pathlib import Path

LIB_ROOT = Path(__file__).resolve().parents[1]
if str(LIB_ROOT) not in sys.path:
    sys.path.insert(0, str(LIB_ROOT))


def escritor_api(args):
    """Un proceso: carga, marca su sesión, añade una corrección a una entrada COMPARTIDA y una
    regla global por mutación directa, y guarda. Devuelve el índice."""
    proyecto, i = args
    from lib.schemas import CorrectionRecord, CorrectionType
    from lib.state_manager import StateManager

    sm = StateManager(Path(proyecto), "zz")
    sm.load()
    sm.mark_skill(session_id=f"m{i:02d}", skill="diaries-tag", status="complete", confidence=0.8)
    sm.add_correction("_country", "diaries-review",
                      CorrectionRecord(type=CorrectionType.PUNCTUAL, description=f"corr-{i:02d}",
                                       applied_by="diaries-review"))
    sm.state.global_rules.append(CorrectionRecord(type=CorrectionType.RULE, description=f"regla-{i:02d}"))
    sm.save()
    return i


def escritor_repetido(args):
    """Un proceso que guarda varias veces seguidas (para la prueba de lecturas concurrentes)."""
    proyecto, i, veces = args
    from lib.state_manager import StateManager

    for j in range(veces):
        sm = StateManager(Path(proyecto), "zz")
        sm.load()
        sm.mark_skill(session_id=f"w{i:02d}_{j:02d}", skill="diaries-meta", status="complete",
                      confidence=0.9)
    return i


def lector_crudo(ruta: str, hasta: float) -> dict:
    """Lee el fichero en bruto (como los `python3 -c json.load(...)` de los SKILL.md) hasta `hasta`
    (time.time()). Cuenta las lecturas que no son un JSON completo."""
    p = Path(ruta)
    leidas = rotas = 0
    ejemplo = ""
    while time.time() < hasta:
        try:
            b = p.read_bytes()
        except FileNotFoundError:
            continue
        leidas += 1
        if not b.rstrip().endswith(b"}"):
            rotas += 1
            ejemplo = ejemplo or f"{len(b)} bytes, termina en {b[-20:]!r}"
            continue
        if leidas % 7 == 0:                      # parseo completo de vez en cuando
            try:
                json.loads(b)
            except ValueError as exc:
                rotas += 1
                ejemplo = ejemplo or str(exc)
    return {"leidas": leidas, "rotas": rotas, "ejemplo": ejemplo}
