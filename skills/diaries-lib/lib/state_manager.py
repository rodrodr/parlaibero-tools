"""Estado del pipeline por país: state/{iso2}/pipeline_state.json.

Garantías (parche A1, 2026-09-23):

- **Sin escrituras perdidas con concurrencia.** `save()` toma un bloqueo exclusivo
  (`fcntl.flock` sobre `pipeline_state.json.lock`) y, si otro proceso guardó desde que este
  cargó, FUSIONA: parte de lo que hay en disco y aplica solo lo que este proceso cambió
  (por sesión, skill y campo; las listas de correcciones y `global_rules` se unen). Así funcionan
  tanto `mark_skill`/`add_correction` como la mutación directa del objeto que devuelve `load()`.
  Si dos procesos cambian el MISMO campo de la MISMA entrada, gana el último que guarda.
- **La fusión actualiza la memoria en sitio.** Tras fusionar, el objeto que devolvió `load()`
  sigue siendo `sm.state`, y las sesiones, skills, dicts y listas que ya existían siguen siendo los
  mismos objetos, con lo ajeno incorporado. Lo que un script mute después por una referencia
  antigua (`st = sm.load()`, un bucle de `mark_skill` y luego `st.current_skill = …`) llega al
  disco. El dict de sesiones (y el de skills de cada sesión) puede ganar o perder claves en un
  guardado que fusiona: quien itere sobre él mientras guarda debe iterar sobre una copia
  (`list(st.sessions)`), como ya hacen los scripts del proyecto.
- **Escritura atómica.** Se escribe en un temporal del mismo directorio, se hace fsync y se
  sustituye con `os.replace`: un lector ve el fichero anterior o el nuevo, nunca uno a medias.
  Un `.tmp` huérfano de un proceso muerto antes del `os.replace` (SIGKILL) no se acumula: se
  limpia, si es más viejo que `DIARIES_STATE_LOCK_TIMEOUT`, al entrar en `_bloqueo()`.
- **Lectura tolerante.** Si el JSON está a medias (un escritor ajeno sin bloqueo), `load()`
  reintenta unos segundos. Un fichero ilegible de forma persistente da error y NUNCA se
  sustituye a ciegas por el estado en memoria.
- **Confianza en [0, 1].** Los valores anómalos —fuera de rango o no numéricos (asignación directa
  de un texto u otro tipo, que no pasa por Pydantic)— se acotan a `None` y se registran con su
  sesión, skill y valor original en `state/{iso2}/confidence_anomalies.jsonl` (y se avisa por
  stderr), tanto si se detectan al cargar un estado ya así en disco como al guardar una asignación
  directa: nunca se lanza la traza cruda de `pydantic.ValidationError`.
- **Marcas de tiempo en UTC con zona** (`datetime.now(timezone.utc)`).

El formato de pipeline_state.json no cambia (json.dumps(model_dump(), indent=2,
ensure_ascii=False)) y la API pública es la misma.
"""
import contextlib
import json
import math
import os
import stat
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl
except ImportError:                                    # pragma: no cover  (Windows)
    fcntl = None

from pydantic import BaseModel

from lib.schemas import (
    PipelineState,
    SessionState,
    SkillStatus,
    CorrectionRecord,
    SkillState,
    acotar_confianza,
    ahora_utc,
    confianza_no_numerica,
)

ANOMALIAS = "confidence_anomalies.jsonl"
_LOCK_TIMEOUT_DEFECTO = 600.0                                               # segundos
_ESPERAS_LECTURA = (0.05, 0.1, 0.2, 0.4, 0.8, 1.0)                          # ≈2,5 s en total


def _aviso(msg: str) -> None:
    print(f"⚠ diaries-lib: {msg}", file=sys.stderr)


def _leer_lock_timeout() -> float:
    """DIARIES_STATE_LOCK_TIMEOUT en segundos (≥ 0; «inf» espera sin límite). Un valor ilegible
    no rompe la importación de todos los scripts: se avisa y se usa el valor por defecto."""
    crudo = os.environ.get("DIARIES_STATE_LOCK_TIMEOUT", "").strip()
    if not crudo:
        return _LOCK_TIMEOUT_DEFECTO
    try:
        valor = float(crudo)
    except ValueError:
        valor = float("nan")
    if valor != valor or valor < 0:
        _aviso(f"DIARIES_STATE_LOCK_TIMEOUT={crudo!r} no es un número de segundos válido; "
               f"uso {_LOCK_TIMEOUT_DEFECTO:.0f} s")
        return _LOCK_TIMEOUT_DEFECTO
    return valor


_LOCK_TIMEOUT = _leer_lock_timeout()


def _num_json(v):
    """Un valor apto para JSON estricto: NaN e infinitos van como texto."""
    if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
        return repr(v)
    return v


def _escanear_anomalias(datos: dict, origen: str) -> list[dict]:
    """Acota EN SITIO las confianzas fuera de [0, 1] (o no numéricas) de un estado en forma de
    dict y devuelve un registro por cada una (sesión, skill, valor original y guardado). El
    `source` del registro es "no_numerico" para lo no convertible a float (independientemente de
    dónde se detecte); para un número fuera de rango, sigue siendo `origen` ("carga"/"asignacion")."""
    out = []
    sesiones = datos.get("sessions") if isinstance(datos, dict) else None
    if not isinstance(sesiones, dict):
        return out
    for sid, ses in sesiones.items():
        skills = ses.get("skills") if isinstance(ses, dict) else None
        if not isinstance(skills, dict):
            continue
        for nombre, sk in skills.items():
            if not isinstance(sk, dict):
                continue
            c = sk.get("confidence")
            if c is None or (type(c) is float and 0.0 <= c <= 1.0):
                continue
            acotado, anomala = acotar_confianza(c)
            if anomala:
                sk["confidence"] = acotado
                fuente = "no_numerico" if confianza_no_numerica(c) else origen
                out.append({"session": sid, "skill": nombre, "raw_confidence": c,
                            "stored_confidence": acotado, "source": fuente})
    return out


# ───────────────────────────── fusión a tres bandas ─────────────────────────────
# base  = el estado tal como ESTE proceso lo cargó (o lo escribió por última vez), normalizado
# mio   = el estado en memoria ahora
# disco = lo que hay en disco ahora (otro proceso guardó entretanto)
# Resultado: disco + los cambios de este proceso respecto a base.

def _fusionar_lista(base: list, mio: list, disco: list) -> list:
    if mio == base:                    # este proceso no la tocó: queda la del disco
        return list(disco)
    if disco == base:                  # solo la cambió este proceso: queda la suya, orden incluido
        return list(mio)
    quitados = [x for x in base if x not in mio]
    anadidos = [x for x in mio if x not in base]
    res = [x for x in disco if x not in quitados]
    res += [x for x in anadidos if x not in res]
    return res


def _fusionar_campos(base: dict, mio: dict, disco: dict) -> dict:
    res = dict(disco)
    for k, v in mio.items():
        if k == "corrections":
            res[k] = _fusionar_lista(base.get(k) or [], v or [], disco.get(k) or [])
        elif v != base.get(k):
            res[k] = v
    return res


def _fusionar_sesion(base: dict, mio: dict, disco: dict) -> dict:
    res = dict(disco)
    for k, v in mio.items():
        if k != "skills" and v != base.get(k):
            res[k] = v
    sk_base, sk_mio = base.get("skills") or {}, mio.get("skills") or {}
    sk_res = dict(disco.get("skills") or {})
    defecto = None
    for nombre, m in sk_mio.items():
        b = sk_base.get(nombre)
        if m == b:
            continue                                   # este proceso no la tocó
        d = sk_res.get(nombre)
        if d is None:
            sk_res[nombre] = m
            continue
        if b is None:                                  # creada aquí (get_skill) y también en disco
            defecto = defecto or SkillState().model_dump()
            b = defecto
        sk_res[nombre] = _fusionar_campos(b, m, d)
    for nombre in sk_base:
        if nombre not in sk_mio:
            sk_res.pop(nombre, None)
    res["skills"] = sk_res
    return res


def _fusionar(base: dict, mio: dict, disco: dict) -> dict:
    res = dict(disco)
    for k, v in mio.items():
        if k not in ("sessions", "global_rules") and v != base.get(k):
            res[k] = v
    res["global_rules"] = _fusionar_lista(base.get("global_rules") or [], mio.get("global_rules") or [],
                                          disco.get("global_rules") or [])
    ses_base, ses_mio = base.get("sessions") or {}, mio.get("sessions") or {}
    ses_res = dict(disco.get("sessions") or {})
    for sid, m in ses_mio.items():
        b = ses_base.get(sid)
        if m == b:
            continue
        d = ses_res.get(sid)
        ses_res[sid] = m if d is None else _fusionar_sesion(b or {}, m, d)
    for sid in ses_base:
        if sid not in ses_mio:
            ses_res.pop(sid, None)
    res["sessions"] = ses_res
    return res


# ───────────────────────────── reconciliación en sitio ─────────────────────────────
# Tras fusionar, la memoria se pone al día SIN sustituir objetos: los scripts guardan referencias
# (`st = sm.load()`, una sesión, una skill, una lista) y siguen mutándolas después de un
# mark_skill. Si save() cambiara self._state por un objeto nuevo, esas mutaciones se perderían.

def _huella(x) -> str:
    """Clave estable de un elemento de lista (un modelo o un valor JSON)."""
    if isinstance(x, BaseModel):
        x = x.model_dump()
    return json.dumps(x, sort_keys=True, ensure_ascii=False, default=str)


def _reconciliar_lista(viejo: list, nuevo: list) -> None:
    """Deja en `viejo` el contenido de `nuevo` sin cambiar de lista y reutilizando los elementos
    de `viejo` que siguen, para que una referencia a uno de ellos siga viva."""
    huellas = [_huella(v) for v in viejo]
    huellas_nuevo = [_huella(n) for n in nuevo]
    if huellas == huellas_nuevo:
        return
    libres: dict[str, list] = {}
    for h, v in zip(huellas, viejo):
        libres.setdefault(h, []).append(v)
    res = []
    for h, n in zip(huellas_nuevo, nuevo):
        pila = libres.get(h)
        res.append(pila.pop(0) if pila else n)
    viejo[:] = res


def _reconciliar_dict(viejo: dict, nuevo: dict) -> None:
    """Deja el dict `viejo` igual que `nuevo`, en sitio: quita las claves que ya no están,
    actualiza en sitio los modelos de las que siguen y añade al final las nuevas."""
    for k in [k for k in viejo if k not in nuevo]:
        del viejo[k]
    for k, n in nuevo.items():
        if k not in viejo:
            viejo[k] = n
            continue
        v = viejo[k]
        if isinstance(v, BaseModel) and type(v) is type(n):
            _reconciliar_modelo(v, n)
        elif v != n:
            viejo[k] = n


def _reconciliar_modelo(viejo: BaseModel, nuevo: BaseModel, saltar: tuple = ()) -> None:
    """Deja `viejo` igual que `nuevo` (del mismo tipo), campo a campo y en sitio. Un valor igual
    no se reasigna, así que se conserva tal como lo dejó el script (p. ej. un enum)."""
    for campo in type(viejo).model_fields:
        if campo in saltar:
            continue
        v, n = getattr(viejo, campo), getattr(nuevo, campo)
        if isinstance(v, BaseModel) and type(v) is type(n):
            _reconciliar_modelo(v, n)
        elif isinstance(v, dict) and isinstance(n, dict):
            _reconciliar_dict(v, n)
        elif isinstance(v, list) and isinstance(n, list):
            _reconciliar_lista(v, n)
        elif v != n:
            setattr(viejo, campo, n)


def _reconciliar_estado(st: PipelineState, mio: dict, fusion: dict) -> None:
    """Pone `st` igual que `fusion` en sitio. `mio` es el volcado de `st` antes de fusionar: solo
    se validan y se tocan las sesiones que difieren de él (el estado de BR tiene ~100k skills)."""
    _reconciliar_modelo(st, PipelineState.model_validate({**fusion, "sessions": {}}), saltar=("sessions",))
    ses_fus, ses_mio, sesiones = fusion.get("sessions") or {}, mio.get("sessions") or {}, st.sessions
    for sid in [s for s in sesiones if s not in ses_fus]:
        del sesiones[sid]
    for sid, d in ses_fus.items():
        actual = sesiones.get(sid)
        if isinstance(actual, SessionState):
            if ses_mio.get(sid) != d:
                _reconciliar_modelo(actual, SessionState.model_validate(d))
        else:
            sesiones[sid] = SessionState.model_validate(d)


class StateManager:
    def __init__(self, base_dir: Path, country: str):
        self.path = base_dir / "state" / country / "pipeline_state.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.country = country
        self._state: PipelineState | None = None
        self._base: dict | None = None             # estado normalizado de la última carga/escritura
        self._base_bytes: bytes | None = None      # bytes del fichero en ese momento (None: no existía)
        self._anomalias: list[dict] = []           # pendientes de registrar en el próximo save()

    # ── E/S de bajo nivel ──

    def _leer_disco(self, conocido: bytes | None = None) -> tuple[dict | None, bytes | None]:
        """(datos, bytes) del fichero, o (None, None) si no existe. Si los bytes son `conocido`
        (lo último que este gestor cargó o escribió), no se parsean y datos es None. Si el JSON
        está a medias (escritor ajeno sin bloqueo), reintenta; si sigue ilegible, lanza el error."""
        ultimo: Exception | None = None
        for espera in (*_ESPERAS_LECTURA, None):
            try:
                crudo = self.path.read_bytes()
            except FileNotFoundError:
                return None, None
            if conocido is not None and crudo == conocido:
                return None, crudo
            try:
                return json.loads(crudo.decode("utf-8")), crudo
            except ValueError as exc:                  # JSONDecodeError, UnicodeDecodeError
                ultimo = exc
                if espera is not None:
                    time.sleep(espera)
        raise ultimo

    def _limpiar_tmp_huerfanos(self) -> None:
        """Borra temporales de escritura ('.{nombre}.*.tmp') más viejos que `_LOCK_TIMEOUT`: solo
        pueden ser restos de un proceso que murió (SIGKILL) entre `tempfile.mkstemp` y el
        `os.replace` de `_escribir_atomico`, porque cualquier escritura legítima para este mismo
        país ocurre con este mismo bloqueo ya tomado (se llama tras adquirirlo). Es basura de
        disco que de otro modo se acumula con cada caída; nunca toca `pipeline_state.json` ni un
        temporal reciente (podría ser, en teoría, de otro escritor)."""
        if not math.isfinite(_LOCK_TIMEOUT):        # «inf»: sin margen con el que decidir «viejo»
            return
        limite = time.time() - _LOCK_TIMEOUT
        try:
            candidatos = list(self.path.parent.glob(f".{self.path.name}.*.tmp"))
        except OSError:
            return
        for tmp in candidatos:
            try:
                if tmp.stat().st_mtime < limite:
                    tmp.unlink()
            except FileNotFoundError:
                pass
            except OSError as e:
                _aviso(f"no se pudo borrar el temporal huérfano {tmp}: {e}")

    @contextmanager
    def _bloqueo(self):
        """Bloqueo exclusivo entre procesos (flock). Se libera al cerrar el descriptor, también
        si el proceso muere."""
        if fcntl is None:                              # pragma: no cover
            _aviso("sin fcntl: el estado se guarda sin bloqueo entre procesos")
            yield
            return
        ruta = self.path.with_name(self.path.name + ".lock")
        fd = os.open(ruta, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            limite = time.monotonic() + _LOCK_TIMEOUT
            espera = 0.005
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() > limite:
                        raise TimeoutError(
                            f"no se obtuvo el bloqueo de {ruta} en {_LOCK_TIMEOUT:.0f} s; ¿hay un "
                            f"proceso colgado escribiendo el estado? (DIARIES_STATE_LOCK_TIMEOUT)")
                    time.sleep(espera)
                    espera = min(espera * 2, 0.05)
            self._limpiar_tmp_huerfanos()
            yield
        finally:
            os.close(fd)

    def _escribir_atomico(self, datos: bytes) -> None:
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(datos)
                fh.flush()
                os.fsync(fh.fileno())
            try:
                modo = stat.S_IMODE(os.stat(self.path).st_mode)
            except FileNotFoundError:
                modo = 0o644
            os.chmod(tmp, modo)
            os.replace(tmp, self.path)
        except BaseException:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp)
            raise

    def _registrar_anomalias(self) -> None:
        if not self._anomalias:
            return
        ts, pid = ahora_utc(), os.getpid()
        lineas = "".join(
            json.dumps({"timestamp": ts, **{k: _num_json(v) for k, v in a.items()}, "pid": pid},
                       ensure_ascii=False) + "\n"
            for a in self._anomalias)
        with open(self.path.with_name(ANOMALIAS), "a", encoding="utf-8") as fh:
            fh.write(lineas)
            fh.flush()
            os.fsync(fh.fileno())
        self._anomalias = []

    def _anotar_anomalias(self, nuevas: list[dict], contexto: str) -> None:
        if not nuevas:
            return
        self._anomalias.extend(nuevas)
        muestra = "; ".join(f"{a['session']}/{a['skill']}: {a['raw_confidence']!r} → {a['stored_confidence']!r}"
                            for a in nuevas[:5])
        mas = f" (y {len(nuevas) - 5} más)" if len(nuevas) > 5 else ""
        _aviso(f"{len(nuevas)} confianza(s) fuera de [0, 1] {contexto}: {muestra}{mas}. Se acotan y se "
               f"registran en {self.path.with_name(ANOMALIAS)} al guardar.")

    # ── API pública ──

    def load(self) -> PipelineState:
        datos, crudo = self._leer_disco()
        self._anomalias = []
        if datos is None:
            self._state = PipelineState(country=self.country)
        else:
            self._anotar_anomalias(_escanear_anomalias(datos, "carga"), f"en {self.path}")
            self._state = PipelineState.model_validate(datos)
        self._base = self._state.model_dump()
        self._base_bytes = crudo
        return self._state

    def save(self) -> None:
        if self._state is None:
            raise RuntimeError("No state loaded. Call load() first.")
        mio = self._state.model_dump()
        asignadas = _escanear_anomalias(mio, "asignacion")     # asignaciones directas tras load()
        for a in asignadas:
            self._state.sessions[a["session"]].skills[a["skill"]].confidence = a["stored_confidence"]
        self._anotar_anomalias(asignadas, "asignadas directamente")

        with self._bloqueo():
            disco, crudo = self._leer_disco(conocido=self._base_bytes)
            if crudo == self._base_bytes:
                final = mio                                   # nadie escribió desde nuestra carga
            else:
                # Otro proceso guardó entretanto: fusionar sobre lo que hay en disco. Las anomalías
                # «de carga» que cuentan son las del fichero que ahora se sustituye.
                self._anomalias = [a for a in self._anomalias if a["source"] != "carga"]
                if disco is None:
                    disco = PipelineState(country=self.country).model_dump()
                else:
                    self._anotar_anomalias(_escanear_anomalias(disco, "carga"), f"en {self.path}")
                base = self._base if self._base is not None else PipelineState(country=self.country).model_dump()
                # En sitio: self._state sigue siendo el objeto que tienen los scripts.
                _reconciliar_estado(self._state, mio, _fusionar(base, mio, disco))
                final = self._state.model_dump()
            datos = json.dumps(final, indent=2, ensure_ascii=False).encode("utf-8")
            if datos != crudo:
                self._escribir_atomico(datos)
            self._registrar_anomalias()
        self._base = final
        self._base_bytes = datos

    @property
    def state(self) -> PipelineState:
        if self._state is None:
            self.load()
        return self._state

    def mark_skill(
        self,
        session_id: str,
        skill: str = "",
        skill_name: str = "",
        status: SkillStatus = SkillStatus.PENDING,
        confidence: float | None = None,
        output: str | None = None,
        output_path: str | None = None,
        error_message: str | None = None,
        error: str | None = None,
    ) -> None:
        # Accept either 'skill' or 'skill_name'
        _skill = skill or skill_name
        # Accept either 'output' or 'output_path'
        _output = output or output_path
        skill_state = self.state.get_session(session_id).get_skill(_skill)
        skill_state.status = status
        if confidence is not None:
            valor, anomala = acotar_confianza(confidence)
            if anomala:
                fuente = "no_numerico" if confianza_no_numerica(confidence) else "mark_skill"
                self._anotar_anomalias([{"session": session_id, "skill": _skill, "raw_confidence": confidence,
                                         "stored_confidence": valor, "source": fuente}],
                                       "recibida en mark_skill")
            skill_state.confidence = valor
        if _output is not None:
            skill_state.output_path = _output
        _err = error or error_message
        if _err:
            skill_state.error_message = _err
        if status == SkillStatus.RUNNING:
            skill_state.started_at = ahora_utc()
        elif status in (SkillStatus.COMPLETE, SkillStatus.FLAG, SkillStatus.HALT):
            skill_state.completed_at = ahora_utc()
        self.save()

    def add_correction(
        self,
        session_id: str,
        skill_name: str,
        correction: CorrectionRecord,
    ) -> None:
        skill_state = self.state.get_session(session_id).get_skill(skill_name)
        skill_state.corrections.append(correction)
        self.save()

    def get_sessions_by_status(
        self, skill_name: str, status: SkillStatus
    ) -> list[str]:
        return [
            sid
            for sid, sess in self.state.sessions.items()
            if sess.get_skill(skill_name).status == status
        ]

    def get_all_flag_sessions(self) -> dict[str, list[str]]:
        """Returns {skill_name: [session_ids]} for all FLAG sessions."""
        result: dict[str, list[str]] = {}
        for sid, sess in self.state.sessions.items():
            for skill_name, skill_state in sess.skills.items():
                if skill_state.status == SkillStatus.FLAG:
                    result.setdefault(skill_name, []).append(sid)
        return result
