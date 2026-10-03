#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# ParlaIbero · instala los skills diaries-* en ~/.claude/skills
#
#   bash install_skills.sh            instala (no sobrescribe skills que ya existan)
#   bash install_skills.sh --force    sustituye los diaries-* existentes, guardando
#                                     antes una copia en ~/.claude/skills/.diaries_backup_<fecha>/
#   bash install_skills.sh --deps     además instala las dependencias de Python
#
# Los skills llaman a su código por la ruta ~/.claude/skills/diaries-lib/, así que esa
# es la ubicación obligatoria. Solo se tocan las carpetas diaries-*.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$REPO/skills"
DEST="${PARLAIBERO_SKILLS_DIR:-$HOME/.claude/skills}"   # cambiarlo solo para pruebas: los SKILL.md llaman a ~/.claude/skills/diaries-lib
FORCE=0; DEPS=0
for a in "$@"; do
  case "$a" in
    --force) FORCE=1 ;;
    --deps)  DEPS=1 ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "opción desconocida: $a" >&2; exit 2 ;;
  esac
done

[ -d "$SRC/diaries-lib" ] || { echo "✗ no encuentro $SRC/diaries-lib" >&2; exit 1; }
mkdir -p "$DEST"

existing=()
for d in "$SRC"/diaries-*; do
  [ -e "$DEST/$(basename "$d")" ] && existing+=("$(basename "$d")")
done

if [ ${#existing[@]} -gt 0 ] && [ $FORCE -eq 0 ]; then
  echo "✗ ya existen en $DEST: ${existing[*]}" >&2
  echo "  Vuelve a ejecutar con --force para sustituirlos (se guarda una copia antes)." >&2
  exit 1
fi

if [ ${#existing[@]} -gt 0 ]; then
  BK="$DEST/.diaries_backup_$(date +%Y%m%d_%H%M%S)"
  mkdir -p "$BK"
  for n in "${existing[@]}"; do mv "$DEST/$n" "$BK/"; done
  echo "  copia de los anteriores en $BK"
fi

n=0
for d in "$SRC"/diaries-*; do
  cp -R "$d" "$DEST/"
  n=$((n + 1))
done
echo "✓ $n carpetas instaladas en $DEST ($(ls -d "$DEST"/diaries-*/SKILL.md 2>/dev/null | wc -l | tr -d ' ') skills + diaries-lib)"

if [ $DEPS -eq 1 ]; then
  python3 -m pip install -r "$DEST/diaries-lib/requirements.txt"
fi

cat <<EOF

Siguiente paso, desde la carpeta de tu proyecto (solo datos):
  bash ~/.claude/skills/diaries-lib/install.sh     # dependencias + estructura de carpetas
  claude                                           # y dentro: /diaries-teach  o  /diaries-bootstrap --country xx
EOF
