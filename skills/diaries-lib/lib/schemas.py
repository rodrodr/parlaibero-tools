from __future__ import annotations
import math
import warnings
from enum import Enum
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import datetime, timezone


def ahora_utc() -> str:
    """Marca de tiempo ISO 8601 en UTC con zona explícita (…+00:00).

    Sustituye a `datetime.utcnow().isoformat()` (obsoleto en Python 3.12 y sin zona). Las marcas
    antiguas del estado, sin zona, también están en UTC y se conservan tal cual.
    """
    return datetime.now(timezone.utc).isoformat()


class ConfianzaFueraDeRango(UserWarning):
    """Una confianza fuera de [0, 1] (o no finita) se acotó al validar el estado."""


def acotar_confianza(valor: Any) -> tuple[Any, bool]:
    """Acota una confianza a [0, 1]. Devuelve (valor_a_guardar, es_anomala).

    - None pasa tal cual (no hay confianza).
    - Menor que 0 → 0.0; mayor que 1 → 1.0.
    - No finita (NaN, ±inf) → None: no es un número utilizable y NaN ni siquiera es JSON válido.
    - Lo no numérico (no se puede convertir a float) → None: TAMBIÉN es anómalo (ronda 2, hallazgo
      «confidence-texto-por-asignacion-directa»). Antes se devolvía intacto confiando en que
      Pydantic lo rechazara al validar, pero una asignación directa (`sk.confidence = "texto"`, sin
      pasar por `model_validate`) no pasa por Pydantic y el valor llegaba a disco sin acotar ni
      registrar; además, si el JSON en disco ya traía un valor así, la siguiente carga lanzaba la
      traza cruda de `pydantic.ValidationError`. Ver `confianza_no_numerica` para distinguir este
      caso (de tipo) de uno simplemente fuera de rango (de valor) al registrar la anomalía.
    Quien llama decide cómo registrar la anomalía; esta función nunca la esconde (la señala).
    """
    if valor is None or isinstance(valor, bool):
        return valor, False
    try:
        x = float(valor)
    except (TypeError, ValueError):
        return None, True
    if not math.isfinite(x):
        return None, True
    if x < 0.0:
        return 0.0, True
    if x > 1.0:
        return 1.0, True
    return valor, False


def confianza_no_numerica(valor: Any) -> bool:
    """True si `valor` es la anomalía «no_numerico»: no None/bool y no convertible a float (texto
    u otro tipo asignado directamente a `confidence`). Distingue esa causa de un número fuera de
    [0, 1] o no finito (NaN/inf), que también es anómalo pero sí es un número."""
    if valor is None or isinstance(valor, bool):
        return False
    try:
        float(valor)
    except (TypeError, ValueError):
        return True
    return False


class ConfidenceLevel(str, Enum):
    AUTO = "auto"
    FLAG = "flag"
    HALT = "halt"


class ConfidenceScore(BaseModel):
    value: float = Field(ge=0.0, le=1.0)
    level: ConfidenceLevel
    explanation: str
    details: dict[str, Any] = Field(default_factory=dict)


class CorrectionType(str, Enum):
    PUNCTUAL = "punctual"
    RULE = "rule"
    STRATEGY = "strategy"


class CorrectionRecord(BaseModel):
    type: CorrectionType
    description: str
    pattern: str = ""
    action: str = ""
    applied_from: str = ""
    # Quién aplicó la corrección ("diaries-review") y a qué skill iba dirigida.
    # Sin estos campos Pydantic los DESTRUYE en cada round-trip de StateManager
    # y el conteo de intervención humana de diaries-report da siempre 0.
    applied_by: str = ""
    skill: str = ""
    timestamp: str = Field(default_factory=ahora_utc)


class SkillStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FLAG = "flag"
    HALT = "halt"
    SKIPPED = "skipped"


class SkillState(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    status: SkillStatus = SkillStatus.PENDING
    # Siempre en [0, 1]. Un valor fuera de rango (en CO había tres negativas en diaries-correct) o
    # no numérico (p. ej. una asignación directa `sk.confidence = "texto"`, que no pasa por
    # Pydantic) se ACOTA a None y se avisa con ConfianzaFueraDeRango; StateManager además lo
    # registra con su sesión y skill en state/{iso2}/confidence_anomalies.jsonl (source
    # "no_numerico" para lo no convertible a float). No se rechaza al cargar ni al guardar para
    # que el estado siga siendo legible.
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    output_path: Optional[str] = None
    corrections: list[CorrectionRecord] = Field(default_factory=list)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    note: Optional[str] = None

    @field_validator("confidence", mode="before")
    @classmethod
    def _acotar_confianza(cls, v: Any) -> Any:
        if v is None or (type(v) is float and 0.0 <= v <= 1.0):     # camino rápido: 100k entradas en BR
            return v
        acotado, anomala = acotar_confianza(v)
        if anomala:
            motivo = "no numérica" if confianza_no_numerica(v) else "fuera de [0, 1]"
            warnings.warn(f"confianza {motivo}: {v!r} → {acotado!r}", ConfianzaFueraDeRango,
                          stacklevel=2)
        return acotado


class SessionState(BaseModel):
    skills: dict[str, SkillState] = Field(default_factory=dict)

    def get_skill(self, skill_name: str) -> SkillState:
        if skill_name not in self.skills:
            self.skills[skill_name] = SkillState()
        return self.skills[skill_name]


class PipelineState(BaseModel):
    country: str
    current_skill: str = ""
    sessions: dict[str, SessionState] = Field(default_factory=dict)
    global_rules: list[CorrectionRecord] = Field(default_factory=list)
    onboarding_report: str = ""

    def get_session(self, session_id: str) -> SessionState:
        if session_id not in self.sessions:
            self.sessions[session_id] = SessionState()
        return self.sessions[session_id]


class InvocationMode(str, Enum):
    SESSION = "session"
    BATCH = "batch"
    ALL = "all"


class SkillInput(BaseModel):
    country: str
    mode: InvocationMode
    session_id: Optional[str] = None
    batch_prefix: Optional[str] = None
    dry_run: bool = False
    force: bool = False


class SkillOutput(BaseModel):
    skill_name: str
    session_id: str
    status: SkillStatus
    confidence: ConfidenceScore
    output_path: str
    summary: str
    warnings: list[str] = Field(default_factory=list)


class SessionType(str, Enum):
    ORDINARIA = "ordinaria"
    EXTRAORDINARIA = "extraordinaria"
    SOLEMNE = "solemne"
    ESPECIAL = "especial"
    DESCONOCIDA = "desconocida"


class SessionMetadata(BaseModel):
    session_id: str
    date: str
    session_number: Optional[int] = None
    session_type: SessionType = SessionType.DESCONOCIDA
    legislature: str = ""
    president: str = ""
    country: str
    source_file: str
    confidence: float = 0.0


class InterventionRow(BaseModel):
    """Canonical output schema for standardize/{ISO2}_interventions.csv."""
    legislature: str = ""
    session_number: Optional[int] = None
    date: str = ""
    session_type: str = ""
    speaker_raw: str = ""
    id_dep: Optional[str] = None
    speaker_name: Optional[str] = None
    party: Optional[str] = None
    district: Optional[str] = None
    text: str = ""


class DeputyRecord(BaseModel):
    id_dep: str
    speaker_name: str
    first_name: str = ""
    last_name: str = ""
    legislature: str = ""
    party: Optional[str] = None
    district: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    notes: Optional[str] = None


class MatchRecord(BaseModel):
    speaker_raw: str
    id_dep: Optional[str] = None
    nombre_completo: Optional[str] = None
    similarity_score: float = 0.0
    match_method: Literal["exact", "fuzzy", "llm", "manual", "unmatched"] = "unmatched"
    confidence: float = 0.0
    reviewed: bool = False
