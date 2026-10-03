#!/usr/bin/env python3
"""Exporta los skills diaries-* desde su fuente única (~/.claude/skills) a skills/ de este repo.

La carpeta skills/ de este repositorio es GENERADA: no se edita a mano. La fuente única de los
skills sigue siendo ~/.claude/skills/diaries-*; este script la proyecta para su distribución.

Qué hace:
  1. Borra skills/ y la vuelve a crear desde la fuente.
  2. Excluye lo que no debe distribuirse: respaldos (*.bak*, *.pre_*), cachés de Python, estado
     de proyecto (state/), .env y scripts de un solo uso que leen ficheros temporales.
  3. Sustituye las rutas absolutas del proyecto del investigador por rutas relativas al
     directorio de trabajo (los skills se ejecutan desde la raíz del proyecto).
  4. FALLA si, tras la limpieza, queda alguna ruta personal o algo con aspecto de credencial.

Uso:
  python3 maintainer/sync_skills.py            # exporta
  python3 maintainer/sync_skills.py --check    # solo comprueba la fuente, no escribe
"""
from __future__ import annotations

import argparse
import fnmatch
import re
import shutil
import sys
from pathlib import Path

FUENTE = Path.home() / ".claude" / "skills"
REPO = Path(__file__).resolve().parents[1]
DESTINO = REPO / "skills"

# Patrones (sobre la ruta relativa a la carpeta del skill) que NO se distribuyen.
EXCLUIR = [
    "*.bak", "*.bak_*", "*.pre_*", "*.pyc", "*/__pycache__/*", "__pycache__/*",
    ".DS_Store", "*/.DS_Store", ".env", "*/.env", ".pytest_cache/*", "*/.pytest_cache/*",
    "state/*",                              # estado de proyecto suelto (diaries-deputies/state/do)
    "lib/utils/compute_linkage.py",         # un solo uso: lee un JSON de un directorio temporal
]

# Sustituciones de rutas personales → rutas relativas al proyecto (cwd).
SUSTITUCIONES = [
    (re.compile(r'Path\(["\']/Users/rodrodr/Dropbox/Apps/diaries["\']\)'), "Path.cwd()"),
    (re.compile(r'str\(Path\.home\(\) / "Dropbox/Apps/diaries"\)'), 'str(Path.cwd())'),
    (re.compile(r"/Users/rodrodr/Dropbox/Apps/diaries/"), ""),
]

# Lo que NO puede quedar en lo exportado.
PROHIBIDO = [
    re.compile(r"/Users/rodrodr"),
    re.compile(r"/private/tmp/claude-"),
    re.compile(r"Dropbox/Apps/diaries"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"gh[opsu]_[A-Za-z0-9]{20,}"),
    re.compile(r"X-Dataverse-key\s*[:=]\s*['\"]?[0-9a-f]{8}-"),
]

TEXTO = {".py", ".md", ".sh", ".yaml", ".yml", ".txt", ".json", ".html", ".toml", ".cfg"}


def excluido(rel: str) -> bool:
    return any(fnmatch.fnmatch(rel, p) for p in EXCLUIR)


def skills_fuente() -> list[Path]:
    return sorted(p for p in FUENTE.glob("diaries-*") if p.is_dir())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="no escribe; informa de lo que exportaría")
    args = ap.parse_args()

    carpetas = skills_fuente()
    if len([c for c in carpetas if (c / "SKILL.md").exists()]) != 21 or not (FUENTE / "diaries-lib").is_dir():
        print(f"✗ se esperaban 21 skills con SKILL.md y diaries-lib en {FUENTE}", file=sys.stderr)
        return 1

    if not args.check:
        if DESTINO.exists():
            shutil.rmtree(DESTINO)
        DESTINO.mkdir(parents=True)

    copiados = omitidos = reescritos = 0
    problemas: list[str] = []
    for carpeta in carpetas:
        for f in sorted(carpeta.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(carpeta).as_posix()
            if excluido(rel):
                omitidos += 1
                continue
            destino = DESTINO / carpeta.name / rel
            if f.suffix in TEXTO:
                texto = f.read_text(encoding="utf-8")
                nuevo = texto
                for patron, reemplazo in SUSTITUCIONES:
                    nuevo = patron.sub(reemplazo, nuevo)
                if nuevo != texto:
                    reescritos += 1
                for patron in PROHIBIDO:
                    for m in patron.finditer(nuevo):
                        linea = nuevo.count("\n", 0, m.start()) + 1
                        problemas.append(f"{carpeta.name}/{rel}:{linea}: {patron.pattern}")
                if not args.check:
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    destino.write_text(nuevo, encoding="utf-8")
                    shutil.copystat(f, destino)
            elif not args.check:
                destino.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, destino)
            copiados += 1

    print(f"skills: {len(carpetas)} carpetas · {copiados} ficheros exportados · "
          f"{omitidos} excluidos · {reescritos} con rutas reescritas")
    if problemas:
        print("✗ quedan rutas personales o credenciales:", file=sys.stderr)
        for p in problemas:
            print("   " + p, file=sys.stderr)
        if not args.check:
            shutil.rmtree(DESTINO)
            print("  (skills/ borrado: no se deja una exportación sucia)", file=sys.stderr)
        return 1
    print("✓ ninguna ruta personal ni credencial en lo exportado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
