#!/usr/bin/env python3
"""Registra una decisión metodológica del pipeline, con su evidencia.

Las decisiones importantes de un corpus se toman en el momento y se olvidan después.
Este módulo las persiste en un formato estructurado para que `diaries-report` genere el
informe metodológico sin reconstruir nada, y para que dentro de un año se pueda saber
**por qué** se hizo algo y **con qué evidencia**.

    state/{iso2}/decisions.jsonl     decisiones de un país
    state/_transversal/decisions.jsonl   decisiones que afectan a todos

**`evidencia` es obligatoria y se valida.** «Se usó el umbral 0,5» no sirve dentro de un
año; «se usó 0,5 porque con controles independientes daba ratios de 400× a 4.500×» sí. Sin
evidencia la decisión no se guarda: el campo existe justamente para impedir que se registre
una preferencia como si fuera un hallazgo.

**Una decisión superada NO se borra.** Se marca `estado="superada"` y la nueva la enlaza con
`supersede`. Esa cadena es el historial de correcciones del proyecto — la sección más útil
del informe metodológico y, en un Data Descriptor, la que da credibilidad en vez de quitarla.

Uso desde el skill `diaries-decide`:

    python3 ~/.claude/skills/diaries-lib/lib/utils/record_decision.py \\
        --pais cr --fase diaries-validate \\
        --decision "El índice del acta se traslada al sidecar de no-discurso" \\
        --alternativas "Dividir las filas en una intervención por orador" \\
        --evidencia "Firma: ≥50% de líneas acaban en «: nº». Cuatro señales de oralidad
                     independientes dan ratios de 400× a 4.500× entre lo que se mueve y lo
                     que se queda (n=40.000)" \\
        --consecuencia "20.350 filas (5,47%) al sidecar; 372.045 → 351.695" \\
        [--supersede cr-0003] [--estado vigente]

    --pais transversal   para las decisiones que afectan a todos los corpus
    --listar             muestra las decisiones registradas
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

MIN_EVIDENCIA = 40          # por debajo no es evidencia, es una afirmación
ESTADOS = ("vigente", "superada", "revertida")
MARCAS = {"vigente": " ", "superada": "×", "revertida": "↩"}


def ruta(pais: str) -> Path:
    sub = "_transversal" if pais.lower() in ("transversal", "global", "all") else pais.lower()
    return Path.cwd() / "state" / sub / "decisions.jsonl"


def leer(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def siguiente_id(pais: str, previas: list[dict]) -> str:
    pre = "tr" if pais.lower() in ("transversal", "global", "all") else pais.lower()
    n = max((int(m.group(1)) for d in previas
             if (m := re.match(rf"{pre}-(\d+)$", d.get("id", "")))), default=0)
    return f"{pre}-{n + 1:04d}"


def estado_de(d: dict) -> tuple[str, str]:
    """Devuelve (marca, superada_por) de un registro, tolerando las formas antiguas.

    Tres casos que el acceso por índice no aguantaba:

    - **`estado` ausente.** Los 57 registros del esquema viejo no lo llevan. Se leen como
      vigentes: son decisiones que nadie anuló, solo se escribieron antes del campo.
    - **`estado="superada-por-co-0005"`.** Cuatro registros llevan el puntero DENTRO del
      estado en vez de `estado="superada"` + `superada_por`. Es el MISMO estado con el id
      incrustado, no un estado nuevo, así que se reconoce por prefijo y se recupera el
      puntero. No se admite como clave del diccionario de marcas: el valor lleva dentro el
      id de la decisión que anula, es distinto en cada registro y no hay diccionario que lo
      cubra. Los .jsonl no se tocan.
    - **`superada_por` ausente.** Es el caso normal: solo lo llevan las 3 anuladas.

    Un `?` sigue señalando un valor que de verdad no sabemos leer, que es para lo que sirve.
    """
    e = (d.get("estado") or "vigente").strip()
    por = d.get("superada_por") or ""
    if m := re.match(r"(superada|revertida)[-_]por[-_](.+)$", e):
        e, por = m.group(1), por or m.group(2)
    return MARCAS.get(e, "?"), por


def vista(d: dict) -> tuple[str, str, str, str]:
    """(id, fecha, fase, texto) de un registro, sea del esquema actual o del viejo.

    El fichero es acumulativo de solo-añadir y mezcla DOS esquemas (ver la nota de `main`):
    los registros anteriores al 2026-08-09 llevan `timestamp/country/skill/title` y no
    tienen `id`, `fecha` ni `fase`. No se migran — se leen con `.get` y se muestran con lo
    que sí traen: el país entre paréntesis donde iría el id, la fecha del `timestamp` y el
    `title`, que es su etiqueta corta (su `decision` es el cuerpo largo).
    """
    ident = d.get("id") or f"({d.get('country', '??').lower()})"
    fecha = d.get("fecha") or d.get("timestamp", "")[:10]
    fase = d.get("fase") or d.get("skill", "")
    texto = d.get("title") or d.get("decision", "")
    return ident, fecha, fase, texto


def validar(a) -> None:
    ev = " ".join(a.evidencia.split())
    if len(ev) < MIN_EVIDENCIA:
        raise SystemExit(
            f"✗ `evidencia` demasiado corta ({len(ev)} car., mínimo {MIN_EVIDENCIA}).\n"
            "  Una decisión sin evidencia medida no se registra. Di QUÉ se midió, SOBRE QUÉ\n"
            "  y QUÉ SALIÓ — no basta con justificar la preferencia.")
    if a.estado not in ESTADOS:
        raise SystemExit(f"✗ estado debe ser uno de {ESTADOS}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pais", required=True, help="iso2, o «transversal»")
    ap.add_argument("--fase", default="", help="skill o etapa del pipeline")
    ap.add_argument("--decision")
    ap.add_argument("--alternativas", default="")
    ap.add_argument("--evidencia", default="")
    ap.add_argument("--consecuencia", default="")
    ap.add_argument("--supersede", default="", help="id de la decisión que esta anula")
    ap.add_argument("--estado", default="vigente")
    ap.add_argument("--fecha", default=str(date.today()))
    ap.add_argument("--listar", action="store_true")
    a = ap.parse_args()

    p = ruta(a.pais)
    previas = leer(p)

    if a.listar:
        if not previas:
            print(f"(sin decisiones registradas en {p})")
            return
        for d in previas:
            marca, superada_por = estado_de(d)
            ident, fecha, fase, texto = vista(d)
            print(f"{marca} {ident:<9} {fecha:<10} [{fase}] {texto[:78]}")
            if d.get("supersede"):
                print(f"     anula → {d['supersede']}")
            if superada_por:
                print(f"     anulada por → {superada_por}")
        return

    if not a.decision:
        raise SystemExit("✗ falta --decision")
    validar(a)

    d = {"id": siguiente_id(a.pais, previas), "fecha": a.fecha,
         "ambito": "transversal" if a.pais.lower() in ("transversal", "global", "all")
                   else a.pais.lower(),
         "fase": a.fase, "decision": " ".join(a.decision.split()),
         "alternativas": " ".join(a.alternativas.split()),
         "evidencia": " ".join(a.evidencia.split()),
         "consecuencia": " ".join(a.consecuencia.split()),
         "supersede": a.supersede, "estado": a.estado}

    # ⚠ El fichero mezcla DOS esquemas: los registros anteriores al 2026-08-08 llevan
    # `timestamp/country/skill/title` y NO tienen `id`. Recorrerlos con `x["id"]` reventaba
    # `--supersede` con un KeyError. Se leen con `.get`, que es lo que corresponde a un registro
    # acumulativo de solo-añadir: los formatos viejos conviven, no se migran ni se borran.
    if a.supersede:
        if not any(x.get("id") == a.supersede for x in previas):
            raise SystemExit(f"✗ no existe la decisión {a.supersede} en {p.name}")
        # la anulada se marca, NUNCA se borra
        for x in previas:
            if x.get("id") == a.supersede:
                x["estado"] = "superada"
                x["superada_por"] = d["id"]
        p.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in previas),
                     encoding="utf-8")
        print(f"  {a.supersede} marcada como superada")

    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"✓ {d['id']} registrada en {p}")


if __name__ == "__main__":
    main()
