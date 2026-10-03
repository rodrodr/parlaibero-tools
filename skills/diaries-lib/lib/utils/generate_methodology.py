#!/usr/bin/env python3
"""Genera `docs/_metodologia/generados/METODOLOGIA.md` a partir de las decisiones registradas.

⚠ Variante antigua sin llamadores: el generador canónico es `scripts/generar_metodologia.py` del
proyecto (normaliza los 57 registros de agosto sin `id`). Se mantiene la ruta de escritura
sincronizada para que nunca vuelva a escribir en la raíz de docs/ (reorganización 2026-09-06).

El documento metodológico **no se escribe a mano**: se compone de los `decisions.jsonl` que
`/diaries-decide` va acumulando. Así no hay dos versiones de la verdad, y volver a generarlo
tras una decisión nueva es gratis.

Incluye a propósito una sección de **decisiones superadas**, con el enlace a la que las
anuló. En un *Data Descriptor* esa sección **da credibilidad en vez de quitarla**: demuestra
que las conclusiones se contrastaron, no que se acertó a la primera.

Uso:  python3 scripts/generar_metodologia.py
"""
from __future__ import annotations

import json
from pathlib import Path

NOM = {"ar": "Argentina", "br": "Brasil", "cl": "Chile", "co": "Colombia", "cr": "Costa Rica",
       "do": "Rep. Dominicana", "es": "España", "gt": "Guatemala", "mx": "México",
       "pa": "Panamá", "pe": "Perú", "pt": "Portugal", "py": "Paraguay",
       "sv": "El Salvador", "uy": "Uruguay"}


def leer(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def bloque(d: dict) -> str:
    t = [f"#### {d['id']} — {d['decision']}\n",
         f"*{d['fecha']}*" + (f" · fase `{d['fase']}`" if d.get("fase") else "") + "\n"]
    if d.get("alternativas"):
        t.append(f"**Alternativa considerada.** {d['alternativas']}\n")
    t.append(f"**Evidencia.** {d['evidencia']}\n")
    if d.get("consecuencia"):
        t.append(f"**Consecuencia.** {d['consecuencia']}\n")
    if d.get("supersede"):
        t.append(f"> Anula la decisión `{d['supersede']}`.\n")
    if d.get("superada_por"):
        t.append(f"> ⚠ **Superada** por `{d['superada_por']}`.\n")
    return "\n".join(t)


def main() -> None:
    base = Path("state")
    tr = leer(base / "_transversal" / "decisions.jsonl")
    paises = {c: leer(base / c / "decisions.jsonl") for c in NOM}
    paises = {c: v for c, v in paises.items() if v}
    todas = tr + [d for v in paises.values() for d in v]
    sup = [d for d in todas if d.get("estado") == "superada"]

    p = ["# ParlaIbero — Documentación metodológica",
         "",
         "> Generado desde los registros de `/diaries-decide` "
         "(`state/_transversal/decisions.jsonl` y `state/{iso2}/decisions.jsonl`). "
         "**No editar a mano**: regenerar con `python3 scripts/generar_metodologia.py`.",
         "",
         f"**{len(todas)} decisiones registradas** · {len(tr)} transversales · "
         f"{len(todas)-len(tr)} de país · {len(sup)} superadas y conservadas.",
         "",
         "Cada decisión declara **qué se hizo**, **qué alternativa se descartó**, "
         "**con qué evidencia medida** y **qué consecuencia tuvo**. La evidencia es un campo "
         "obligatorio y validado: una decisión sin medición detrás no se registra.",
         "",
         "---",
         "",
         "## Principios transversales",
         "",
         "Los criterios que emergieron del trabajo y que gobiernan las decisiones concretas. "
         "No son específicos de este corpus: son transferibles a cualquier proyecto que "
         "construya datos a partir de fuentes documentales heterogéneas.",
         "",
         "| principio | de dónde salió |",
         "|---|---|",
         "| **Descubrir, no asumir** | `diaries-meta` asumía el regex del config y falló en "
         "**7 de 15 países**. Guatemala registraba la legislatura en `notas` y se dio por "
         "«no comprobable» teniendo el dato delante |",
         "| **Un control no puede compartir el léxico de lo que valida** | Costa Rica: 22.979 "
         "marcadores `PRESIDENTA` omitidos **con el verificador dando 0 residuales**, porque "
         "compartía el patrón del extractor |",
         "| **El diario es la fuente primaria; el padrón, una construcción nuestra** | Una "
         "intervención nunca se elimina porque su orador no case. Brasil no incluía a Marina "
         "Silva ni a Sônia Guajajara; Uruguay, a dos presidentes de la Cámara |",
         "| **Los padrones nacionales son independientes por diseño** | No hay un formato "
         "«correcto» al que homogeneizarlos: cada cámara se rige por leyes distintas |",
         "| **No confundir «el dato no puede expresar esto» con «esto está mal»** | Exigir "
         "fechas de mandato mandaba a FLAG el **100%** de Guatemala sin que hubiera nada mal |",
         "| **No llamar exclusión estructural a un fallo de atribución propio** | Descontar "
         "los `PRESIDENTE` anónimos inflaba Brasil de 86,42% a **99,32%** |",
         "| **Medir por subgrupo, no en agregado** | Una cobertura del 75,9% escondía **50,0% "
         "en mujeres frente a 82,3% en hombres** |",
         "| **La muestra no repara: señala dónde reparar** | El 4,15% de Costa Rica llevó a "
         "mover 20.350 filas reales; corregir la muestra habría cambiado el 0,005% |",
         "| **Mirar una muestra ALEATORIA de lo que se va a tocar** | Evitó dividir el índice "
         "de Costa Rica en miles de intervenciones basura, y en Uruguay evitó extraer el "
         "45,91% del corpus |",
         "",
         "---",
         "",
         "## Decisiones transversales",
         ""]
    for d in tr:
        p.append(bloque(d))

    p += ["---", "", "## Decisiones por país", ""]
    for c, v in sorted(paises.items()):
        p += [f"### {NOM[c]} ({c.upper()})", ""]
        for d in v:
            p.append(bloque(d))

    if sup:
        p += ["---", "", "## Decisiones superadas — el historial de correcciones", "",
              "Se conservan a propósito. Una decisión que se corrigió documenta que la "
              "conclusión se contrastó, y **el motivo por el que la primera versión era "
              "errónea suele ser más instructivo que la versión final**.", ""]
        for d in sup:
            p.append(f"- **`{d['id']}`** ({d['fecha']}) — {d['decision']}  \n"
                     f"  Superada por `{d.get('superada_por','?')}`.")
        p.append("")

    p += ["---", "", "## Documentos relacionados", "",
          "| documento | contenido |",
          "|---|---|",
          "| `docs/_metodologia/validation_methodology.md` | Método de validación: muestreo, auto-filtro "
          "PASS/FLAG, reglas de independencia (§4.4), de alcance (§4.5), de primacía del "
          "diario (§4.6) y de revisión humana del match (§4.7) |",
          "| `docs/validacion/RESULTADOS.md` | Resultados de la validación y las dos rondas de "
          "calibración de fuga |",
          "| `docs/_historico/revision_prepublicacion_hallazgos.md` | Revisión pre-publicación: hallazgos, "
          "correcciones y mediciones |",
          "| `docs/_metodologia/gender_perspective.md` | Defectos con efecto asimétrico por género y la "
          "derivación de `sex` |",
          "| `docs/_metodologia/generados/cobertura_temporal.md` | Cobertura por país, años ausentes y por qué "
          "`legislature` no es comparable |",
          "| `docs/{iso2}/process_report.md` | Historia de procesamiento de cada corpus |",
          ""]

    out = Path("docs/_metodologia/generados/METODOLOGIA.md")   # reorganización de docs/ (2026-09-06)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(p), encoding="utf-8")
    print(f"docs/_metodologia/generados/METODOLOGIA.md · {len(todas)} decisiones "
          f"({len(tr)} transversales, {len(todas)-len(tr)} de país, {len(sup)} superadas)")


if __name__ == "__main__":
    main()
