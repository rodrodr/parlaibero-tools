"""Fallo 1: StateManager perdía escrituras con concurrencia y rompía lecturas.

Reproducción de la auditoría (patrones-1): 40 `update_state.py` en paralelo guardaban 24–30 de 40
sesiones, todos con `"ok": true`, y un lector veía el JSON a medias («Expecting value»).
"""
import json
import multiprocessing
import os
import stat
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from conftest import UPDATE_STATE, escribe_estado, estado_sintetico, lee_estado, update_state
from _diaries_lib_trabajadores import escritor_api, escritor_repetido, lector_crudo

from lib.schemas import CorrectionRecord, CorrectionType, SessionState, SkillState, SkillStatus
from lib.state_manager import StateManager


# ─────────────────────────── concurrencia real entre procesos ───────────────────────────

def test_40_update_state_en_paralelo_no_pierden_sesiones(proyecto):
    """El escenario exacto de la auditoría: 40 procesos CLI, 16 a la vez, sesiones distintas."""
    escribe_estado(proyecto, "zz", estado_sintetico("zz", 2000))

    def uno(i):
        return update_state(proyecto, "--country", "zz", "--skill", "diaries-ocr",
                            "--session", f"s{i:02d}", "--status", "complete", "--confidence", "0.9")

    with ThreadPoolExecutor(max_workers=16) as ex:
        res = list(ex.map(uno, range(40)))

    fallidos = [(r.returncode, r.stdout.strip(), r.stderr[-300:]) for r in res if r.returncode != 0]
    st = lee_estado(proyecto, "zz")
    faltan = [f"s{i:02d}" for i in range(40)
              if st["sessions"].get(f"s{i:02d}", {}).get("skills", {}).get("diaries-ocr", {}).get("status")
              != "complete"]
    ok_true = sum(1 for r in res if r.returncode == 0 and json.loads(r.stdout)["ok"])
    assert not fallidos and not faltan, (
        f"{len(faltan)}/40 escrituras perdidas ({ok_true} procesos dijeron ok:true); "
        f"{len(fallidos)} procesos con error, p. ej. {fallidos[:2]}")
    assert sum(1 for s in st["sessions"] if s.startswith("SO_")) == 2000, "se perdieron sesiones previas"


def test_40_procesos_multiprocessing_api_sin_perdidas(proyecto):
    """40 procesos (multiprocessing, spawn) que usan la API: mark_skill en sesiones distintas,
    add_correction sobre la MISMA entrada y mutación directa de global_rules."""
    escribe_estado(proyecto, "zz", estado_sintetico("zz", 1500))
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(16) as pool:
        hechos = pool.map(escritor_api, [(str(proyecto), i) for i in range(40)])
    assert sorted(hechos) == list(range(40))

    st = lee_estado(proyecto, "zz")
    marcadas = [f"m{i:02d}" for i in range(40)
                if st["sessions"].get(f"m{i:02d}", {}).get("skills", {}).get("diaries-tag", {}).get("status")
                == "complete"]
    assert len(marcadas) == 40, f"mark_skill: {len(marcadas)}/40"

    corr = st["sessions"]["_country"]["skills"]["diaries-review"]["corrections"]
    assert sorted(c["description"] for c in corr) == [f"corr-{i:02d}" for i in range(40)], \
        f"add_correction sobre la misma entrada: {len(corr)}/40"

    reglas = sorted(r["description"] for r in st["global_rules"])
    assert reglas == [f"regla-{i:02d}" for i in range(40)], f"global_rules: {len(reglas)}/40"


def test_lector_nunca_ve_un_json_a_medias(proyecto):
    """Mientras 6 procesos reescriben un estado de varios MB, un lector en bruto (como los
    `python3 -c json.load(...)` de los SKILL.md) no debe ver nunca un fichero incompleto."""
    p = escribe_estado(proyecto, "zz", estado_sintetico("zz", 6000))
    assert p.stat().st_size > 2_000_000

    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(6) as pool:
        asyncres = pool.map_async(escritor_repetido, [(str(proyecto), i, 4) for i in range(6)])
        resultado = {}
        parar = threading.Event()               # el lector corre hasta que terminan los escritores

        def lector():
            leidas = rotas = 0
            ejemplo = ""
            while not parar.is_set():
                r = lector_crudo(str(p), time.time() + 0.2)
                leidas += r["leidas"]; rotas += r["rotas"]; ejemplo = ejemplo or r["ejemplo"]
            resultado.update(leidas=leidas, rotas=rotas, ejemplo=ejemplo)

        hilo = threading.Thread(target=lector, daemon=True)
        hilo.start()
        try:
            asyncres.get(timeout=600)
        finally:
            parar.set()
            hilo.join(timeout=30)

    assert resultado["leidas"] > 20
    assert resultado["rotas"] == 0, (f"{resultado['rotas']} de {resultado['leidas']} lecturas vieron "
                                     f"un JSON incompleto; p. ej. {resultado['ejemplo']}")
    st = lee_estado(proyecto, "zz")
    esperadas = {f"w{i:02d}_{j:02d}" for i in range(6) for j in range(4)}
    assert esperadas <= set(st["sessions"]), f"faltan {sorted(esperadas - set(st['sessions']))[:5]}"


# ─────────────────────────── fusión determinista (dos gestores) ───────────────────────────

def _dos(proyecto, n=50):
    escribe_estado(proyecto, "zz", estado_sintetico("zz", n))
    a, b = StateManager(proyecto, "zz"), StateManager(proyecto, "zz")
    a.load(); b.load()
    return a, b


def test_dos_gestores_sesiones_distintas(proyecto):
    a, b = _dos(proyecto)
    a.mark_skill(session_id="nueva_a", skill="diaries-meta", status="complete", confidence=0.9)
    b.mark_skill(session_id="nueva_b", skill="diaries-meta", status="flag", confidence=0.7)
    st = lee_estado(proyecto, "zz")
    assert st["sessions"]["nueva_a"]["skills"]["diaries-meta"]["status"] == "complete"
    assert st["sessions"]["nueva_b"]["skills"]["diaries-meta"]["status"] == "flag"


def test_mutacion_directa_no_pisa_lo_ajeno(proyecto):
    """Patrón de los scripts del proyecto: `st = sm.load()`, mutar el objeto y `sm.save()`."""
    a, b = _dos(proyecto)
    b.mark_skill(session_id="de_b", skill="diaries-tag", status="complete", confidence=0.95)
    a.state.current_skill = "diaries-meta"
    a.state.get_session("de_a").get_skill("diaries-meta").status = "complete"
    a.save()
    st = lee_estado(proyecto, "zz")
    assert st["current_skill"] == "diaries-meta"
    assert st["sessions"]["de_a"]["skills"]["diaries-meta"]["status"] == "complete"
    assert st["sessions"]["de_b"]["skills"]["diaries-tag"]["status"] == "complete"


def test_misma_entrada_campos_distintos_se_conservan(proyecto):
    a, b = _dos(proyecto)
    sid = "SO_00003_2001-01-01"
    a.add_correction(sid, "diaries-correct", CorrectionRecord(type=CorrectionType.RULE, description="de A"))
    b.add_correction(sid, "diaries-correct", CorrectionRecord(type=CorrectionType.PUNCTUAL, description="de B"))
    b.state.get_session(sid).get_skill("diaries-correct").note = "nota de B"
    b.save()
    sk = lee_estado(proyecto, "zz")["sessions"][sid]["skills"]["diaries-correct"]
    assert sorted(c["description"] for c in sk["corrections"]) == ["de A", "de B"]
    assert sk["note"] == "nota de B"
    assert sk["status"] == "complete" and sk["confidence"] == 0.93


def test_mismo_campo_gana_la_ultima_escritura(proyecto):
    """Semántica documentada: en el MISMO campo de la MISMA entrada gana quien guarda después."""
    a, b = _dos(proyecto)
    sid = "SO_00001_2001-01-01"
    a.mark_skill(session_id=sid, skill="diaries-correct", status="flag", confidence=0.7)
    b.mark_skill(session_id=sid, skill="diaries-correct", status="halt", confidence=0.2)
    sk = lee_estado(proyecto, "zz")["sessions"][sid]["skills"]["diaries-correct"]
    assert (sk["status"], sk["confidence"]) == ("halt", 0.2)


def test_el_gestor_queda_al_dia_tras_fusionar(proyecto):
    a, b = _dos(proyecto)
    b.mark_skill(session_id="de_b", skill="diaries-tag", status="complete")
    a.mark_skill(session_id="de_a", skill="diaries-tag", status="complete")
    assert "de_b" in a.state.sessions, "tras fusionar, el estado en memoria incluye lo ajeno"
    # y un segundo guardado de A no deshace nada
    a.save()
    st = lee_estado(proyecto, "zz")
    assert {"de_a", "de_b"} <= set(st["sessions"])


# ─────────────── referencias antiguas tras una fusión (patrón uy_correct/estado.py) ───────────────
# Los scripts del proyecto hacen `st = sm.load()`, un bucle de mark_skill y después
# `st.current_skill = …` y `sm.save()`. Si un mark_skill del bucle fusiona con lo que guardó otro
# proceso, el estado en memoria tiene que actualizarse EN SITIO: lo que el script mute luego por
# sus referencias antiguas (st, una sesión, una skill, una lista) tiene que llegar al disco.

def _guarda_otro(proyecto, sid="de_b"):
    """Otro proceso guarda entretanto una sesión nueva."""
    b = StateManager(proyecto, "zz"); b.load()
    b.mark_skill(session_id=sid, skill="diaries-tag", status="complete", confidence=0.95)


def test_referencias_antiguas_siguen_vivas_tras_fusionar(proyecto):
    escribe_estado(proyecto, "zz", estado_sintetico("zz", 50))
    sm = StateManager(proyecto, "zz")
    st = sm.load()
    sid = "SO_00002_2001-01-01"
    ses = st.sessions[sid]
    sk = ses.get_skill("diaries-correct")
    _guarda_otro(proyecto)
    sm.mark_skill(session_id="de_a", skill="diaries-correct", status="complete", confidence=0.9)  # fusiona
    st.current_skill = "diaries-tag"
    sk.note = "nota tras fusionar"
    sm.save()
    disco = lee_estado(proyecto, "zz")
    assert disco["current_skill"] == "diaries-tag", "se perdió st.current_skill mutado tras la fusión"
    assert disco["sessions"][sid]["skills"]["diaries-correct"]["note"] == "nota tras fusionar"
    assert {"de_a", "de_b"} <= set(disco["sessions"])
    assert sm.state is st, "la fusión sustituyó el objeto de estado"
    assert sm.state.sessions[sid] is ses and ses.skills["diaries-correct"] is sk
    assert "de_b" in st.sessions, "lo ajeno llega también a la referencia antigua"


def test_patron_uy_correct_bucle_de_mark_skill_y_current_skill(proyecto):
    """scripts/campana_reproceso/uy_correct/estado.py, con otro proceso guardando a mitad del bucle."""
    escribe_estado(proyecto, "zz", estado_sintetico("zz", 30))
    sm = StateManager(proyecto, "zz")
    st = sm.load()
    sids = sorted(st.sessions)
    for i, sid in enumerate(sids):
        if i == 10:
            _guarda_otro(proyecto)
        sm.mark_skill(sid, skill="diaries-correct", status=SkillStatus.FLAG, confidence=0.72,
                      output_path=f"source/zz/corrected/{sid}.txt", error_message="delta")
    st.current_skill = "diaries-tag"
    sm.save()
    disco = lee_estado(proyecto, "zz")
    assert disco["current_skill"] == "diaries-tag", "se perdió st.current_skill tras el bucle"
    assert all(disco["sessions"][s]["skills"]["diaries-correct"]["status"] == "flag" for s in sids)
    assert disco["sessions"]["de_b"]["skills"]["diaries-tag"]["status"] == "complete"


def test_la_fusion_actualiza_en_sitio_la_entrada_que_cambio_el_otro(proyecto):
    escribe_estado(proyecto, "zz", estado_sintetico("zz", 20))
    sid = "SO_00004_2001-01-01"
    sm = StateManager(proyecto, "zz"); st = sm.load()
    sk = st.sessions[sid].skills["diaries-correct"]
    b = StateManager(proyecto, "zz"); b.load()
    b.state.sessions[sid].skills["diaries-correct"].note = "nota de B"
    b.add_correction(sid, "diaries-correct", CorrectionRecord(type=CorrectionType.RULE, description="de B"))
    sm.mark_skill(session_id="otra", skill="diaries-meta", status="complete")        # fusiona
    assert sk.note == "nota de B" and [c.description for c in sk.corrections] == ["de B"], \
        "la skill que el script conserva no refleja lo que guardó el otro proceso"
    sk.output_path = "source/zz/corrected/nuevo.txt"
    sm.save()
    d = lee_estado(proyecto, "zz")["sessions"][sid]["skills"]["diaries-correct"]
    assert d["output_path"] == "source/zz/corrected/nuevo.txt"
    assert d["note"] == "nota de B" and [c["description"] for c in d["corrections"]] == ["de B"]
    assert d["status"] == "complete" and d["confidence"] == 0.93


def test_listas_y_dicts_del_estado_conservan_su_identidad(proyecto):
    escribe_estado(proyecto, "zz", estado_sintetico("zz", 20))
    sm = StateManager(proyecto, "zz"); st = sm.load()
    reglas, sesiones = st.global_rules, st.sessions
    b = StateManager(proyecto, "zz"); b.load()
    b.state.global_rules.append(CorrectionRecord(type=CorrectionType.RULE, description="regla de B"))
    b.save()
    sm.mark_skill(session_id="de_a", skill="diaries-meta", status="complete")       # fusiona
    reglas.append(CorrectionRecord(type=CorrectionType.STRATEGY, description="regla de A"))
    sesiones["alias_a"] = SessionState()
    sesiones["alias_a"].get_skill("diaries-meta").status = "flag"
    sm.save()
    disco = lee_estado(proyecto, "zz")
    assert sorted(r["description"] for r in disco["global_rules"]) == ["regla de A", "regla de B"]
    assert disco["sessions"]["alias_a"]["skills"]["diaries-meta"]["status"] == "flag"
    assert sm.state.global_rules is reglas and sm.state.sessions is sesiones


def test_fusion_aleatoria_memoria_igual_a_disco_y_nada_se_pierde(proyecto):
    """Adversarial, con semilla fija: A y B cambian sesiones disjuntas (estado, nota, correcciones,
    borrados, sesiones nuevas) y ambos añaden a una entrada compartida y a global_rules. B guarda y
    luego A (fusiona). El disco es la suma de los dos, la memoria de A es igual al disco y las
    referencias que A conservaba siguen vivas."""
    import random

    rnd = random.Random(20260923)
    escribe_estado(proyecto, "zz", estado_sintetico("zz", 60))
    esperado = lee_estado(proyecto, "zz")
    a, b = StateManager(proyecto, "zz"), StateManager(proyecto, "zz")
    sta = a.load(); b.load()
    sids = sorted(sta.sessions)
    rnd.shuffle(sids)
    refs = {sid: (sta.sessions[sid], sta.sessions[sid].skills["diaries-correct"]) for sid in sids}

    def corr(desc):
        return CorrectionRecord(type=CorrectionType.PUNCTUAL, description=desc, timestamp="t")

    def aplica(gestor, sid, op, quien):
        ses_e = esperado["sessions"]
        if op == 3:
            del gestor.state.sessions[sid]; del ses_e[sid]
            return
        sk, sk_e = gestor.state.sessions[sid].skills["diaries-correct"], ses_e[sid]["skills"]["diaries-correct"]
        if op == 0:
            sk.status, sk.confidence = "flag", round(rnd.random(), 3)
            sk_e["status"], sk_e["confidence"] = sk.status, sk.confidence
        elif op == 1:
            sk.note = sk_e["note"] = f"nota {quien} {sid}"
        else:
            sk.corrections.append(corr(f"{quien}-{sid}"))
            sk_e["corrections"].append(corr(f"{quien}-{sid}").model_dump(mode="json"))

    for quien, gestor, lote in (("B", b, sids[:20]), ("A", a, sids[20:40])):
        for sid in lote:
            aplica(gestor, sid, rnd.randrange(4), quien)
        for k in range(3):
            nueva = f"nueva_{quien}_{k}"
            gestor.state.get_session(nueva).get_skill("diaries-meta").status = "complete"
            esperado["sessions"][nueva] = {"skills": {"diaries-meta": SkillState(status="complete").model_dump(mode="json")}}
        gestor.state.get_session("_country").get_skill("diaries-review").corrections.append(corr(f"comp-{quien}"))
        gestor.state.global_rules.append(corr(f"regla-{quien}"))
    esperado["sessions"]["_country"] = {"skills": {"diaries-review": SkillState(
        corrections=[corr("comp-B"), corr("comp-A")]).model_dump(mode="json")}}
    esperado["global_rules"] = [corr("regla-B").model_dump(mode="json"), corr("regla-A").model_dump(mode="json")]

    b.save()
    a.save()                                                   # fusiona sobre lo de B
    disco = lee_estado(proyecto, "zz")
    assert disco == esperado
    assert a.state.model_dump() == disco, "la memoria de A no coincide con lo que escribió"
    assert a.state is sta
    vivas = [sid for sid in sids if sid in disco["sessions"]]
    assert all(sta.sessions[sid] is refs[sid][0] and sta.sessions[sid].skills["diaries-correct"] is refs[sid][1]
               for sid in vivas)
    # y lo que A mute después por una referencia antigua (a una sesión que cambió B) llega al disco
    sid_b = next(s for s in sids[:20] if s in disco["sessions"])
    refs[sid_b][1].error_message = "tras la fusión"
    a.save()
    assert lee_estado(proyecto, "zz")["sessions"][sid_b]["skills"]["diaries-correct"]["error_message"] == "tras la fusión"


def test_la_lista_que_solo_cambio_este_proceso_se_guarda_tal_cual(proyecto):
    """Si el otro proceso no tocó una lista, gana entera la versión de este, orden incluido."""
    datos = estado_sintetico("zz", 5)
    datos["global_rules"] = [CorrectionRecord(type=CorrectionType.RULE, description=f"r{i}").model_dump()
                             for i in range(3)]
    escribe_estado(proyecto, "zz", datos)
    sm = StateManager(proyecto, "zz"); st = sm.load()
    _guarda_otro(proyecto)
    st.global_rules.reverse()
    sm.save()
    assert [r["description"] for r in lee_estado(proyecto, "zz")["global_rules"]] == ["r2", "r1", "r0"]


def test_guardar_sin_cambios_ajenos_no_vuelve_a_parsear(proyecto, monkeypatch):
    """Vía rápida: si el fichero es el que este gestor cargó o escribió, save() compara bytes y no
    lo parsea (el estado de BR ocupa decenas de MB y mark_skill guarda en cada llamada)."""
    import lib.state_manager as modulo

    escribe_estado(proyecto, "zz", estado_sintetico("zz", 20))
    sm = StateManager(proyecto, "zz"); sm.load()

    class SinLoads:
        dumps = staticmethod(json.dumps)

        @staticmethod
        def loads(*a, **k):
            raise AssertionError("save() volvió a parsear un fichero que no había cambiado")

    monkeypatch.setattr(modulo, "json", SinLoads)
    for i in range(3):
        sm.mark_skill(session_id=f"r{i}", skill="diaries-meta", status="complete")
    monkeypatch.undo()
    assert {"r0", "r1", "r2"} <= set(lee_estado(proyecto, "zz")["sessions"])


def test_timeout_de_bloqueo_mal_escrito_no_rompe_la_importacion(proyecto):
    """DIARIES_STATE_LOCK_TIMEOUT con un valor no numérico: aviso y valor por defecto, no un
    ValueError al importar state_manager (rompería todos los scripts del pipeline)."""
    escribe_estado(proyecto, "zz", estado_sintetico("zz", 3))
    env = {**os.environ, "DIARIES_STATE_LOCK_TIMEOUT": "10 min"}
    r = subprocess.run([sys.executable, str(UPDATE_STATE), "--country", "zz", "--skill", "diaries-meta",
                        "--session", "t", "--status", "complete"],
                       cwd=proyecto, env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr[-400:]
    assert "DIARIES_STATE_LOCK_TIMEOUT" in r.stderr
    assert lee_estado(proyecto, "zz")["sessions"]["t"]["skills"]["diaries-meta"]["status"] == "complete"


# ─────────────────────────── compatibilidad con los usos existentes ───────────────────────────

def test_ida_y_vuelta_byte_a_byte(proyecto):
    """Formato intacto: cargar y guardar sin cambios deja el fichero idéntico."""
    datos = estado_sintetico("zz", 30)
    datos["sessions"]["SO_00000_2001-01-01"]["skills"]["diaries-correct"]["corrections"] = [
        {"type": "rule", "description": "Añadir «señor» — ñ y acentos", "pattern": "x", "action": "y",
         "applied_from": "", "applied_by": "diaries-review", "skill": "diaries-correct",
         "timestamp": "2026-08-01T10:00:00.000000"}]
    datos["global_rules"] = [{"type": "strategy", "description": "Regla global", "pattern": "", "action": "",
                              "applied_from": "", "applied_by": "", "skill": "",
                              "timestamp": "2026-08-01T10:00:00.000000"}]
    p = escribe_estado(proyecto, "zz", datos)
    antes = p.read_bytes()
    sm = StateManager(proyecto, "zz"); sm.load(); sm.save()
    assert p.read_bytes() == antes


def test_patron_save_anulado_en_la_instancia(proyecto):
    """do_extract/actualiza_estado.py: `sm.save = lambda: None` y una sola escritura al final."""
    p = escribe_estado(proyecto, "zz", estado_sintetico("zz", 10))
    antes = p.read_bytes()
    sm = StateManager(proyecto, "zz"); sm.load()
    _save = sm.save
    sm.save = lambda: None
    for i in range(5):
        sm.mark_skill(session_id=f"x{i}", skill="diaries-extract", status="complete", confidence=0.99)
    assert p.read_bytes() == antes, "con save anulado no debe escribirse nada"
    sm.state.current_skill = "diaries-extract"
    sm.save = _save
    sm.save()
    st = lee_estado(proyecto, "zz")
    assert all(f"x{i}" in st["sessions"] for i in range(5)) and st["current_skill"] == "diaries-extract"


def test_patron_save_anulado_en_la_clase(proyecto):
    """pe_cierre/estado.py: `StateManager.save = lambda self: None`."""
    escribe_estado(proyecto, "zz", estado_sintetico("zz", 10))
    sm = StateManager(proyecto, "zz"); sm.load()
    _save = StateManager.save
    try:
        StateManager.save = lambda self: None
        sm.mark_skill(session_id="y", skill="diaries-correct", status="halt", confidence=0.1)
    finally:
        StateManager.save = _save
    sm.save()
    assert lee_estado(proyecto, "zz")["sessions"]["y"]["skills"]["diaries-correct"]["status"] == "halt"


def test_estado_nuevo_sin_fichero(proyecto):
    sm = StateManager(proyecto, "nn")
    st = sm.load()
    assert st.country == "nn" and not st.sessions
    sm.mark_skill(session_id="a", skill="diaries-bootstrap", status="complete", confidence=1.0)
    assert lee_estado(proyecto, "nn")["sessions"]["a"]["skills"]["diaries-bootstrap"]["status"] == "complete"


def test_escritura_atomica_sin_restos_y_con_permisos(proyecto):
    p = escribe_estado(proyecto, "zz", estado_sintetico("zz", 10))
    os.chmod(p, 0o640)
    sm = StateManager(proyecto, "zz"); sm.load()
    for i in range(3):
        sm.mark_skill(session_id=f"t{i}", skill="diaries-meta", status="complete")
    restos = [x.name for x in p.parent.iterdir() if x.name.endswith(".tmp")]
    assert not restos, f"quedaron temporales: {restos}"
    assert stat.S_IMODE(p.stat().st_mode) == 0o640


def test_tmp_huerfano_de_proceso_muerto_se_limpia_al_guardar(proyecto):
    """Repro de g_a/ataque_lock_muerto.py (escenario lock_muerto_con_tmp_a_medias): un '.tmp' que
    quedó huérfano porque su proceso murió (SIGKILL) antes del os.replace no debe acumularse para
    siempre; uno recién creado (en teoría, de otro escritor en curso) no debe tocarse."""
    import lib.state_manager as modulo

    p = escribe_estado(proyecto, "zz", estado_sintetico("zz", 2))
    estado_dir = p.parent

    viejo = estado_dir / f".{p.name}.viejo0000.tmp"
    viejo.write_bytes(b"a medio escribir")
    hace = time.time() - modulo._LOCK_TIMEOUT - 30
    os.utime(viejo, (hace, hace))

    reciente = estado_dir / f".{p.name}.reciente0000.tmp"
    reciente.write_bytes(b"otro escritor, recien creado")

    sm = StateManager(proyecto, "zz")
    sm.mark_skill(session_id="s0", skill="diaries-meta", status="complete", confidence=0.5)

    quedan = {x.name for x in estado_dir.iterdir() if x.name.endswith(".tmp")}
    assert viejo.name not in quedan, "el .tmp huérfano y viejo debía limpiarse al guardar"
    assert reciente.name in quedan, "un .tmp reciente no debe borrarse (podría ser de otro proceso)"
    assert lee_estado(proyecto, "zz")["sessions"]["s0"]["skills"]["diaries-meta"]["status"] == "complete"


# ─────────────────────────── lectura tolerante ───────────────────────────

def test_lectura_tolerante_espera_a_que_termine_la_escritura(proyecto):
    """Un escritor ajeno (sin bloqueo) deja el JSON a medias; load() reintenta en vez de fallar."""
    completo = json.dumps(estado_sintetico("zz", 20), indent=2, ensure_ascii=False)
    p = proyecto / "state" / "zz" / "pipeline_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(completo[: len(completo) // 2], encoding="utf-8")

    def termina():
        time.sleep(0.3)
        p.write_text(completo, encoding="utf-8")

    t = threading.Thread(target=termina); t.start()
    try:
        st = StateManager(proyecto, "zz").load()
    finally:
        t.join()
    assert len(st.sessions) == 20


def test_json_corrupto_persistente_no_se_oculta_ni_se_sobrescribe(proyecto):
    p = escribe_estado(proyecto, "zz", estado_sintetico("zz", 5))
    sm = StateManager(proyecto, "zz"); sm.load()
    roto = b'{"country": "zz", "sessions": {"a'
    p.write_bytes(roto)
    with pytest.raises(ValueError):
        StateManager(proyecto, "zz").load()
    with pytest.raises(Exception):
        sm.mark_skill(session_id="z", skill="diaries-meta", status="complete")
    assert p.read_bytes() == roto, "un estado ilegible nunca se sustituye por otro a ciegas"
