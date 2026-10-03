#!/usr/bin/env python3
"""Capa de verificación ANTI-FALSOS-NEGATIVOS para diaries-tag (CRÍTICA).

El tagging es la fase más delicada del pipeline: un marcador de orador NO detectado
(falso negativo) hace que TODA su intervención se atribuya al orador ANTERIOR, corrompiendo
silenciosamente la matriz de datos — y NINGUNA métrica de confianza por conteo lo detecta.

Esta capa compara el TAGGED contra el patrón de marcador y reporta MARCADORES RESIDUALES:
líneas con forma de marcador de orador (honorífico + nombre en MAYÚSCULAS a inicio de línea)
que quedaron como texto plano, sin convertirse en <int>. Excluye listas de asistencia
("APELLIDO, Nombre"). También detecta intervenciones gigantes (texto >> mediana → englobó
marcadores perdidos).

CLI: python verify_tagging.py --tagged <f> --config <yaml>
Imprime JSON con n_residual_markers (falsos negativos), ejemplos y veredicto.
Exit code 2 si el veredicto es 'falsos_negativos' (para gating en el skill).
"""
import sys, json, re, argparse, statistics
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
try:
    import yaml; HAS_YAML = True
except ImportError:
    HAS_YAML = False


def honorifics_from_config(config_path):
    """Deriva los honoríficos (prefijos de orador en MAYÚSCULAS) del country_config."""
    hon = set()
    if config_path and HAS_YAML and Path(config_path).exists():
        cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
        for h in (cfg.get("speaker_prefix_strip") or []):
            tok = str(h).upper().strip()
            # solo palabras-honorífico reales (letras), no clases de caracteres de regex
            if tok and re.fullmatch(r"[A-ZÑÁÉÍÓÚÜ]+", tok):
                hon.add(tok)
    # SEÑOR/SEÑORA solo como FALLBACK genérico: si el país deriva sus propios honoríficos
    # (CR usa DIPUTADO/PRESIDENTE/SECRETARIO, NO SEÑOR), añadirlos produciría falsos
    # positivos sobre vocativos de discurso ("Señor:", "Señor Presidente:").
    if not hon:
        hon = {"SEÑOR", "SEÑORA", "SENOR", "SENORA"}
    return sorted(hon)


def verify(tagged_text, honorifics):
    hon_re = "|".join(re.escape(h) for h in honorifics)
    # Candidato a marcador: [artículo EL/LA] [ordinal PRIMER/SEGUNDO/...] HONORÍFICO ...
    # CASE-INSENSITIVE y tolerante a prefijo de artículo/ordinal: en muchos países el
    # marcador es "EL PRESIDENTE X:", "LA PRIMERA SECRETARIA, Y:" o, en eras recientes,
    # Title-Case ("Presidente Rafael Ortiz:"). El cand original (honorífico al inicio y solo
    # MAYÚSCULAS) era CIEGO a todo eso → falsos negativos sin detectar. La precisión la dan
    # los filtros posteriores (marker_shape + _next_is_speech + listentry).
    _PRE = r"(?:(?:el|la|los|las)\s+)?(?:(?:primer[ao]?|primera|segund[oa]|tercer[ao])\s+)?"
    cand = re.compile(rf"^\s*{_PRE}({hon_re})\b", re.IGNORECASE)
    # Lista de asistencia: HONORÍFICO + APELLIDO, Nombre  (coma seguida de nombre) → NO es marcador.
    # NOTA: solo excluye entradas SIN terminador de turno; un marcador con coma ("PRIMER
    # SECRETARIO, X:") termina en ':' y lo decide marker_shape + _next_is_speech, no esta regla.
    listentry = re.compile(rf"^\s*({hon_re})\s+[A-ZÑÁÉÍÓÚÜ][A-ZÑÁÉÍÓÚÜ\s.]+,\s*[A-ZÑ]")

    # Un residual REAL parece un marcador de turno: termina en terminador de orador
    # (.-/.—/.·/:/-/—) o va seguido de discurso. Excluye firmas/listas de varios nombres
    # ("X Y DOCTOR Z") para no producir falsos positivos que bloqueen el pipeline en vano.
    # Un marcador de turno SIN etiquetar es una línea corta "rol [nombre]" que TERMINA en el
    # terminador de turno (':' en CR; '.-'/'—' en otros). Exigir el terminador-FINAL (no en
    # cualquier posición) descarta los falsos positivos del cand amplio: vocativos de discurso
    # ("Señor Presidente, ..."), narración ("El diputado X viene y...") y pase de lista
    # ("Diputado X. Ausente."), que NO terminan en ':' ni en raya.
    ends_marker = re.compile(r"(?::|[.·]?\s*[-–—])\s*:?\s*$")
    lines = tagged_text.split("\n")

    def _next_is_speech(idx):
        """El siguiente texto no vacío parece DISCURSO (no una lista/firma/caption).
        Un marcador de turno REAL va seguido de prosa; un ítem de lista de firmantes, un
        encabezado de decreto ('PRESIDENTE DE LA REPÚBLICA / Y EL MINISTRO...') o un pie
        de caption legal va seguido de otra línea en MAYÚSCULAS o de otro candidato."""
        for k in range(idx + 1, len(lines)):
            nxt = lines[k].strip()
            if not nxt:
                continue
            nxt = re.sub(r"</?int[^>]*>", "", nxt).strip()
            if not nxt:
                continue
            # discurso = contiene minúsculas y NO es a su vez un candidato a marcador
            return bool(re.search(r"[a-záéíóúñü]", nxt)) and not cand.match(nxt)
        return False  # nada después → firma/cierre, no es turno

    residuals = []
    for idx, line in enumerate(lines):
        ls = line.lstrip()
        if ls.startswith("<int"):
            continue  # ya etiquetada
        m_cand = cand.match(ls)
        if not m_cand or listentry.match(ls):
            continue
        # Honorífico "señor/señora" en minúscula o Title-Case (NO todo-mayúsculas) = VOCATIVO
        # ("Señor Presidente:", "Señora Alcaldesa:") o NARRATIVA ("El señor X respondió:"), nunca
        # un turno: en español el marcador de orador capitaliza el honorífico (SEÑOR ...). Solo
        # aplica a la familia señor/señora (otros honoríficos Title-Case sí pueden ser marcador).
        _hon = m_cand.group(1)
        if _hon.lower() in ("señor", "señora", "senor", "senora") and not _hon.isupper():
            continue
        if "\t" in ls:
            continue  # entrada de ÍNDICE/TOC (líder de tabulación + nº de página), no un turno
        head = ls[:70]
        if re.search(r"\sy\s", head, re.IGNORECASE) or "DOCTOR" in head.upper():
            continue  # firma/vocativo de varios roles/oradores unidos por 'y', no un marcador
        if re.match(r"^\s*SE[ÑN]ORA?\s+EDIL", ls):
            continue  # "señor(a) edil(a)" = asunto/expediente de junta departamental, no orador
        if "PRESIDENTE DE LA REP" in head:
            continue  # encabezado/pie de decreto ('El Presidente de la República y el Ministro')
        if re.search(r",\s+[a-záéíóúñ]", ls) or "MOCIÓN" in ls.upper():
            continue  # narración ("X, en el uso de la palabra:") / encabezado de moción → no es
                      # un marcador: en un marcador real la coma va seguida del NOMBRE (mayúscula)
        if re.match(r"^\s*(?:primer[ao]?\s+|segund[oa]\s+)?(?:pro)?(?:president|vicepresident|secretari)[aeo]s?\s*[.:\-–—\s]*$", ls, re.IGNORECASE):
            continue  # etiqueta de DIRECTORIO ('Presidente.-' bajo el nombre): rol solo SIN
                      # artículo ni nombre; un turno de rol real es 'EL PRESIDENTE:' (con artículo)
        if not ends_marker.search(ls.rstrip()):
            continue  # no termina en terminador de turno → vocativo/narración/pase de lista
        if len(ls.rstrip()) > 70:
            continue  # un marcador es CORTO (rol+nombre); una frase de prosa que acaba en ':'
                      # (p.ej. "El Diputado X, con base en el art. 138, reitera la moción:") no lo es
        if not _next_is_speech(idx):
            continue  # lista de firmantes / caption / firma de decreto → no es un turno real
        residuals.append(ls.strip()[:90])

    # Intervenciones (texto tras cada <int ...>)
    blocks = re.split(r"<int[^>]*>", tagged_text)[1:]
    lens = [len(b) for b in blocks]
    n_int = len(blocks)
    med = statistics.median(lens) if lens else 0
    giants = [l for l in lens if med > 0 and l > 20 * med and l > 4000]

    n_resid = len(residuals)
    capture = n_int / (n_int + n_resid) if (n_int + n_resid) > 0 else 1.0

    # El veredicto se basa en los RESIDUALES (señal directa de falso negativo).
    # Las intervenciones gigantes son señal SECUNDARIA (informativa): muchas sesiones tienen
    # una lectura/discurso largo legítimo, así que no disparan el veredicto por sí solas.
    if n_resid == 0:
        verdict = "ok"
    elif n_resid <= 2:
        verdict = "revisar"          # pocos residuales: inspección puntual
    else:
        verdict = "falsos_negativos"  # señal clara de marcadores perdidos

    return {
        "n_tagged": n_int,
        "n_residual_markers": n_resid,
        "capture_rate": round(capture, 4),
        "giant_interventions": len(giants),
        "median_intervention_len": int(med),
        "verdict": verdict,
        "residual_examples": residuals[:10],
    }


def main():
    ap = argparse.ArgumentParser(description="Verificación anti-falsos-negativos de tagging")
    ap.add_argument("--tagged", required=True)
    ap.add_argument("--config", default=None)
    args = ap.parse_args()
    hon = honorifics_from_config(args.config)
    rep = verify(Path(args.tagged).read_text(encoding="utf-8", errors="replace"), hon)
    rep["status"] = "ok"
    print(json.dumps(rep, ensure_ascii=False))
    sys.exit(2 if rep["verdict"] == "falsos_negativos" else 0)


if __name__ == "__main__":
    main()
