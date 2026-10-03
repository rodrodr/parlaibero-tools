#!/usr/bin/env python3
"""Runner de OCR por lotes con paralelización A NIVEL DE PÁGINA. Interrumpible y reanudable.

Generaliza `run_ocr_uy.py`, que el skill de OCR mandaba **copiar y editar** por país: tenía el
país, las rutas, el modelo y los umbrales metidos a fuego, y desde la migración del código a
`~/.claude/skills/` apuntaba a un `lib/utils/update_state.py` que ya no existe — el patrón de
referencia estaba roto y solo se habría descubierto al usarlo en el país siguiente.

**Por qué a nivel de PÁGINA y no de sesión.** Una cola global con todas las páginas de todas
las sesiones pendientes mantiene el GPU sin huecos: ~750 pág/h frente a ~345 con un subproceso
por sesión, medido. Con paralelismo por sesión el slot queda ocioso entre páginas de un mismo
documento, y los subprocesos huérfanos son la causa #1 de lentitud (20 procesos compitiendo:
el rendimiento cae de ~700 a ~160 pág/h).

⚠ **El GPU satura con UNA inferencia; más workers no es mejor.** 1 worker ≈ 496 pág/h,
6 ≈ 756, **8 PERJUDICA** por contención de KV. `ocr.workers` debe igualar a
`ocr.ollama_num_parallel`.

⚠ **Reanudación fina, por página.** Las páginas ya escritas con al menos `min_valid_chars` se
saltan; las vacías o truncadas se borran en el arranque para que se reintenten. Una respuesta
vacía NO se escribe: escribirla convertiría un fallo transitorio en una página perdida para
siempre (ver `feedback_empty_page_silent_loss`).

⚠ **Lockfile y limpieza de huérfanos antes de empezar.** Dos batches simultáneos no se
detectan por el resultado —salen páginas, más despacio—, así que hay que impedirlos.

Uso:
    python3 run_ocr_batch.py --country uy --dry-run
    nohup python3 run_ocr_batch.py --country uy > /dev/null 2>&1 &
    python3 run_ocr_batch.py --country uy --progress      # avance por año, sin procesar
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import statistics
import subprocess
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

_LIB = Path.home() / ".claude/skills/diaries-lib"
sys.path.insert(0, str(_LIB))

try:
    import yaml
except ImportError:                                    # pragma: no cover
    yaml = None

UPDATE = _LIB / "lib/utils/update_state.py"

_state_lock = threading.Lock()
_render_lock = threading.Lock()      # PyMuPDF no es thread-safe; el render es barato (~0,3 s)
_sessions_lock = threading.Lock()
_shutdown = threading.Event()


class Cfg:
    """Todo lo que antes estaba a fuego, leído del country_config."""

    def __init__(self, iso2: str):
        self.iso2 = iso2
        p = Path(f"country_config/{iso2}.yaml")
        d = (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.exists() and yaml else {}
        o = d.get("ocr") or {}
        th = (d.get("thresholds") or {}).get("diaries-ocr") or {}
        self.model = o.get("primary_model") or o.get("model") or "Maternion/LightOnOCR-2:1b"
        self.dpi = int(o.get("dpi", 150))
        self.workers = int(o.get("workers", 6))
        self.min_chars = int(o.get("min_valid_chars", 80))
        self.auto = float(th.get("threshold_auto", d.get("threshold_auto", 0.85)))
        self.flag = float(th.get("threshold_flag", d.get("threshold_flag", 0.65)))
        self.raw = Path(f"source/{iso2}/raw")
        self.ocr = Path(f"source/{iso2}/ocr")
        self.state = Path(f"state/{iso2}/pipeline_state.json")
        self.log = Path(f"logs/ocr_{iso2}.log")
        self.lock = Path(f"logs/ocr_{iso2}.lock")


def _signal(cfg):
    def h(signum, frame):
        logging.getLogger(__name__).warning(
            "Señal recibida — no se envían páginas nuevas; las en vuelo terminan. "
            f"Reanudar: nohup python3 run_ocr_batch.py --country {cfg.iso2} > /dev/null 2>&1 &")
        _shutdown.set()
        cfg.lock.unlink(missing_ok=True)
    return h


def _pids_con_lock() -> set:
    """PIDs vivos que sostienen el lock de ALGÚN país."""
    vivos = set()
    for f in Path("logs").glob("ocr_*.lock"):
        try:
            pid = int(f.read_text().strip())
            os.kill(pid, 0)
            vivos.add(pid)
        except (ProcessLookupError, ValueError, OSError):
            pass
    return vivos


def kill_orphans(aplicar: bool = True) -> tuple[int, int]:
    """Mata los procesos OCR HUÉRFANOS. → (muertos, respetados)

    ⚠⚠ **Nunca mata a quien sostiene un lock vivo, ni siquiera el de otro país.** La versión
    heredada mataba por patrón de línea de órdenes, sin distinguir: un batch de un país
    habría matado de un SIGKILL el de otro que llevara días corriendo. Con los 10 días de
    OCR de Ecuador en marcha, eso no es una hipótesis.

    ⚠ **En `--dry-run` no mata nada**, solo cuenta. Es la segunda vez que aparece aquí el
    mismo fallo —una bandera de simulación con efectos— y por eso está escrito dos veces.
    """
    me, n, resp = os.getpid(), 0, 0
    protegidos = _pids_con_lock() | {me}
    out = subprocess.run(["pgrep", "-f", "ocr_pages.py|run_ocr_batch.py"],
                         capture_output=True, text=True).stdout
    for s in out.split():
        pid = int(s)
        if pid in protegidos:
            resp += 1
            continue
        if not aplicar:
            n += 1
            continue
        try:
            os.kill(pid, signal.SIGKILL)
            n += 1
        except ProcessLookupError:
            pass
    return n, resp


def acquire_lock(cfg, log) -> bool:
    if cfg.lock.exists():
        try:
            old = int(cfg.lock.read_text().strip())
            os.kill(old, 0)
            log.error(f"Ya hay un batch corriendo (PID {old}). Aborto. "
                      f"Si el lock es huérfano, borra {cfg.lock}")
            return False
        except (ProcessLookupError, ValueError):
            log.warning(f"Lock huérfano — reclamando {cfg.lock}")
    cfg.lock.parent.mkdir(parents=True, exist_ok=True)
    cfg.lock.write_text(str(os.getpid()))
    return True


def auditar(cfg, aplicar: bool = True) -> dict:
    """Marca (y opcionalmente borra) las páginas vacías o truncadas, para que se reintenten.

    ⚠ **En `--dry-run` NO borra nada.** El original sí lo hacía: la auditoría de pre-vuelo
    escribía en disco antes de comprobar si era una simulación, y una llamada que se anuncia
    como «sin ejecutar» se llevó por delante 984 páginas de UY. Un `--dry-run` que modifica
    datos es peor que no tenerlo, porque invita a ejecutarlo sin pensar.
    """
    vac = cor = ok = 0
    for f in cfg.ocr.rglob("page_*.txt"):
        n = f.stat().st_size
        if n == 0:
            if aplicar:
                f.unlink()
            vac += 1
        elif n < cfg.min_chars and len(f.read_text(errors="ignore")) < cfg.min_chars:
            if aplicar:
                f.unlink()
            cor += 1
        else:
            ok += 1
    return {"ok": ok, "vacias": vac, "cortas": cor}


def pendientes(cfg) -> list[str]:
    st = json.loads(cfg.state.read_text(encoding="utf-8"))
    return sorted(sid for sid, s in st["sessions"].items()
                  if s.get("skills", {}).get("diaries-ocr", {}).get("status", "pending")
                  not in ("complete", "skipped", "flag"))


def marcar(cfg, sid, status, conf, salida):
    with _state_lock:
        subprocess.run([sys.executable, str(UPDATE), "--country", cfg.iso2,
                        "--skill", "diaries-ocr", "--session", sid, "--status", status,
                        "--confidence", str(conf), "--output", salida],
                       check=True, capture_output=True)


def confianza(t: str) -> float:
    return (sum(1 for c in t if c.isalnum() or c == " ") / len(t)) if t else 0.0


def fuente(cfg, sid: str) -> Path | None:
    """El original exigía `.pdf`; no todos los países lo son."""
    for ext in (".pdf", ".PDF"):
        p = cfg.raw / f"{sid}{ext}"
        if p.exists():
            return p
    c = sorted(cfg.raw.glob(f"{sid}.*"))
    return c[0] if c else None


def construir(cfg, pend, log):
    """→ (tareas, sesiones). Solo las páginas que faltan generan tarea."""
    import fitz
    tareas, ses, sin_pdf = [], {}, 0
    for sid in pend:
        pdf = fuente(cfg, sid)
        if not pdf:
            sin_pdf += 1
            continue
        try:
            with _render_lock:
                doc = fitz.open(str(pdf)); n = len(doc); doc.close()
        except Exception as e:
            log.warning(f"  no se pudo abrir {pdf.name}: {e}")
            sin_pdf += 1
            continue
        out = cfg.ocr / sid
        out.mkdir(parents=True, exist_ok=True)
        confs, faltan = [], 0
        for i in range(n):
            f = out / f"page_{i+1:04d}.txt"
            if f.exists():
                t = f.read_text(encoding="utf-8", errors="ignore")
                if len(t) >= cfg.min_chars:
                    confs.append(confianza(t))
                    continue
                f.unlink()
            tareas.append((sid, pdf, i, f))
            faltan += 1
        ses[sid] = {"total": n, "faltan": faltan, "confs": confs, "err": 0, "dir": out}
    if sin_pdf:
        log.warning(f"  {sin_pdf} sesiones sin fuente legible — omitidas")
    return tareas, ses


def cerrar(cfg, sid, ses, cont):
    s = ses[sid]
    m = statistics.fmean(s["confs"]) if s["confs"] else 0.0
    st = ("halt" if (s["err"] and not s["confs"]) else
          "complete" if m >= cfg.auto else "flag" if m >= cfg.flag else "halt")
    marcar(cfg, sid, st, m, str(s["dir"]))
    cont[st] = cont.get(st, 0) + 1
    return st, m


def pagina(cfg, tarea) -> dict:
    import fitz
    from lib.ollama_client import ocr_image_bytes
    sid, pdf, i, out = tarea
    try:
        with _render_lock:
            doc = fitz.open(str(pdf))
            img = doc[i].get_pixmap(matrix=fitz.Matrix(cfg.dpi / 72, cfg.dpi / 72)).tobytes("png")
            doc.close()
    except Exception as e:
        return {"sid": sid, "conf": 0.0, "error": f"render: {e}"}
    r = ocr_image_bytes(img, primary_model=cfg.model)
    t, err = r["text"], r["error"]
    # ⚠ una respuesta vacía NO se escribe: escribirla convierte un fallo transitorio en una
    # página perdida para siempre, y el recuento de archivos no lo delata
    if err or len(t) < 10:
        return {"sid": sid, "conf": 0.0, "error": err or "respuesta_vacia"}
    out.write_text(t, encoding="utf-8")
    return {"sid": sid, "conf": confianza(t), "error": None}


def progreso(cfg) -> None:
    """Avance por año, leyendo el estado. Sustituye al watcher que corría en paralelo.

    ⚠ **El año se toma solo si el token es un AÑO PLAUSIBLE.** Los `session_id` de EC llevan
    el número de acta, y coger «el primer grupo de 4 dígitos» agrupaba por 1000, 1001, 1002…
    como si fueran años. Si no hay año reconocible se agrupa aparte y se avisa, en vez de
    devolver una tabla con aspecto correcto y contenido falso.
    """
    import re
    st = json.loads(cfg.state.read_text(encoding="utf-8"))
    por = defaultdict(lambda: defaultdict(int))
    for sid, s in st["sessions"].items():
        anios = [int(x) for x in re.findall(r"(?<!\d)(\d{4})(?!\d)", sid)]
        anio = next((str(x) for x in anios if 1800 <= x <= 2100), "s/año")
        por[anio][s.get("skills", {}).get("diaries-ocr", {}).get("status", "pending")] += 1
    tot_g = sum(sum(c.values()) for c in por.values())
    print(f"{cfg.iso2.upper()} · avance de diaries-ocr por año")
    print(f"  {'año':>6} {'total':>7} {'complete':>9} {'flag':>6} {'halt':>6} {'pend':>6}")
    for a in sorted(por):
        c = por[a]
        n = sum(c.values())
        print(f"  {a:>6} {n:>7,} {c.get('complete',0):>9,} {c.get('flag',0):>6,} "
              f"{c.get('halt',0):>6,} {c.get('pending',0):>6,}")
    sin = sum(por.get("s/año", {}).values())
    if sin > 0.5 * tot_g:
        print(f"  ⚠ {sin:,} de {tot_g:,} sesiones sin año en el `session_id`: el desglose por "
              f"año no\n    dice nada de este país, solo el total.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--progress", action="store_true")
    a = ap.parse_args()
    cfg = Cfg(a.country.lower())

    if not cfg.state.exists():
        raise SystemExit(f"✗ {cfg.iso2}: sin {cfg.state} — ejecuta /diaries-bootstrap antes")
    if a.progress:
        return progreso(cfg)

    cfg.log.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(cfg.log, encoding="utf-8"),
                                  logging.StreamHandler(sys.stdout)])
    for ruidoso in ("httpx", "httpcore", "ollama"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)
    log = logging.getLogger(__name__)

    h = _signal(cfg)
    signal.signal(signal.SIGTERM, h)
    signal.signal(signal.SIGINT, h)

    n, resp = kill_orphans(aplicar=not a.dry_run)
    if n:
        log.warning(f"pre-vuelo: {n} procesos OCR huérfanos "
                    f"{'eliminados' if not a.dry_run else 'SE ELIMINARÍAN (dry-run: intactos)'}")
    if resp:
        log.info(f"pre-vuelo: {resp} proceso(s) OCR con lock vivo — RESPETADOS "
                 f"(batch de otro país en marcha)")
    if not a.dry_run and not acquire_lock(cfg, log):
        sys.exit(1)
    if cfg.ocr.exists():
        au = auditar(cfg, aplicar=not a.dry_run)
        verbo = "borradas para reintento" if not a.dry_run else "SE BORRARÍAN (dry-run: intactas)"
        log.info(f"pre-vuelo: {au['ok']:,} páginas OK"
                 + (f", {au['vacias']} vacías y {au['cortas']} truncadas {verbo}"
                    if au["vacias"] + au["cortas"] else ", sin corruptas"))

    pend = pendientes(cfg)
    log.info(f"{len(pend)} sesiones pendientes · construyendo la cola de páginas…")
    tareas, ses = construir(cfg, pend, log)
    total = len(tareas)
    log.info(f"{total:,} páginas en {len(ses)} sesiones · {cfg.workers} workers (nivel PÁGINA) "
             f"· modelo {cfg.model} · {cfg.dpi} dpi")

    if a.dry_run:
        log.info(f"[dry-run] se procesarían {total:,} páginas. Sin ejecutar.")
        return

    cont = {"complete": 0, "flag": 0, "halt": 0}
    t0 = datetime.now()
    for sid, s in ses.items():
        if s["faltan"] == 0:
            st, c = cerrar(cfg, sid, ses, cont)
            log.info(f"  {sid} (ya en caché) → {st} conf={c:.2f}")

    hechas = 0
    with ThreadPoolExecutor(max_workers=cfg.workers) as ex:
        futs = {}
        for t in tareas:
            if _shutdown.is_set():
                break
            futs[ex.submit(pagina, cfg, t)] = t
        for f in as_completed(futs):
            r = f.result()
            sid = r["sid"]
            hechas += 1
            with _sessions_lock:
                s = ses[sid]
                (s["confs"].append(r["conf"]) if not r["error"]
                 else s.__setitem__("err", s["err"] + 1))
                s["faltan"] -= 1
                fin = s["faltan"] == 0
            if fin:
                st, c = cerrar(cfg, sid, ses, cont)
                seg = (datetime.now() - t0).total_seconds()
                pph = hechas / seg * 3600 if seg else 0
                log.info(f"[{hechas:,}/{total:,}] {sid} → {st} conf={c:.2f} | {pph:.0f} pág/h "
                         f"| ~{((total-hechas)/pph if pph else 0):.1f} h restantes")

    horas = (datetime.now() - t0).total_seconds() / 3600
    log.info(f"\n=== diaries-ocr {cfg.iso2.upper()} (paralelo por página) ===\n"
             f"  complete {cont['complete']} · flag {cont['flag']} · halt {cont['halt']}\n"
             f"  {hechas:,} páginas en {horas:.2f} h "
             f"({hechas/horas if horas else 0:.0f} pág/h)")
    cfg.lock.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
