#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# ParlaIbero · diaries-* — Instalador de proyecto
#
# Prepara un proyecto: dependencias Python + estructura de directorios, y verifica
# que los 18 skills diaries-* estén disponibles.
#
# ⚠ Los SKILL.md NO viven en este repositorio. Son la ÚNICA FUENTE en
#   ~/.claude/skills/diaries-*/ (versionados con git ahí, disponibles a cualquier
#   harness). Se editan directamente allí (p.ej. vía /diaries-refine). Por eso este
#   instalador NO copia ni sincroniza skills — solo verifica que estén presentes.
#
# Uso:
#   bash install.sh        prepara el proyecto y verifica los skills
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Colores ───────────────────────────────────────────────────────────────────
G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; B='\033[0;34m'; D='\033[2m'; NC='\033[0m'
ok()   { echo -e "  ${G}✓${NC}  $*"; }
warn() { echo -e "  ${Y}!${NC}  $*"; }
fail() { echo -e "  ${R}✗${NC}  $*"; }
step() { echo -e "\n${B}▸${NC} $*"; }

# ── Configuración ─────────────────────────────────────────────────────────────
LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # ~/.claude/skills/diaries-lib (código + requirements)
PROJECT_DIR="$PWD"                                         # proyecto = directorio actual (solo datos)
SKILLS_DIR="$HOME/.claude/skills"

# ── Listas de skills (fuente única en ~/.claude/skills/) ────────────────────────
# En ORDEN DE EJECUCION. ⚠ meta y dedupe van ANTES de tag: el Paso 0c de tag calibra su
# inventario estructural sobre todo el corpus, y las sesiones duplicadas cuentan sus formas
# de marcador DOS VECES. deputies es opcional aquí (solo si el acta trae pase de lista).
PIPELINE_SKILLS=(
  "bootstrap" "ocr" "extract" "correct"
  "meta" "dedupe" "tag" "matrix"
  "deputies" "match" "merge" "standardize" "document"
)
CONTROL_SKILLS=(
  "status" "review" "feedback" "report" "decide" "validate" "teach" "refine"
)

# ── Cabecera ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${B}ParlaIbero · diaries-*${NC}  Pipeline de Diarios Parlamentarios"
echo -e "${D}────────────────────────────────────────────────────────────────${NC}"
echo -e "  Modo: preparación de proyecto (directorio actual)"
echo -e "  Proyecto: ${D}${PROJECT_DIR}${NC}  (datos)"
echo -e "  Código:   ${D}${LIB_DIR}${NC}"
echo -e "  Skills:   ${D}${SKILLS_DIR}${NC}  (fuente única)"
echo ""

# ── 1. Python ─────────────────────────────────────────────────────────────────
step "Verificando Python"
if ! command -v python3 &>/dev/null; then
  fail "Python 3 no encontrado. Instala Python 3.11 o superior."
  exit 1
fi
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
if [[ "$PY_MAJOR" -lt 3 ]] || [[ "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 11 ]]; then
  fail "Se requiere Python 3.11+. Versión encontrada: $PY_VER"
  exit 1
fi
ok "Python $PY_VER"

# ── 2. Dependencias Python ────────────────────────────────────────────────────
step "Instalando dependencias Python"
if [ ! -f "$LIB_DIR/requirements.txt" ]; then
  fail "requirements.txt no encontrado en $LIB_DIR"
  exit 1
fi
if python3 -m pip install -q -r "$LIB_DIR/requirements.txt"; then
  ok "anthropic · pydantic · pyyaml · pymupdf · rapidfuzz · pandas · pillow · ollama"
else
  fail "Error al instalar dependencias. Revisa la salida de pip."
  exit 1
fi

# ── 3. Verificar skills en ~/.claude/skills/ (NO se copian: fuente única) ───────
step "Verificando skills diaries-* en ~/.claude/skills/ (fuente única)"
PRESENT=0; MISSING=0; MISSING_NAMES=()

check_skill() {
  local name="$1"
  if [ -f "$SKILLS_DIR/diaries-${name}/SKILL.md" ]; then
    (( PRESENT++ )) || true
  else
    (( MISSING++ )) || true
    MISSING_NAMES+=("diaries-${name}")
  fi
}
for skill in "${PIPELINE_SKILLS[@]}" "${CONTROL_SKILLS[@]}"; do
  check_skill "$skill"
done

if [[ $MISSING -eq 0 ]]; then
  ok "$PRESENT/18 skills presentes en $SKILLS_DIR"
else
  warn "$PRESENT/18 presentes — faltan: ${MISSING_NAMES[*]}"
  warn "Los skills son la fuente única en ~/.claude/skills/ (versionada con git ahí)."
  warn "Restaúralos desde ese repositorio global; este proyecto NO los contiene."
fi

# ── 4. Estructura de directorios del proyecto (en el directorio actual) ────────
step "Creando estructura de directorios del proyecto"
for d in state source country_config docs; do
  mkdir -p "$PROJECT_DIR/$d"
done
ok "state/  source/  country_config/  docs/"

# ── 5. Ollama (solo para OCR de PDFs escaneados) ───────────────────────────────
step "Verificando Ollama"
if ! command -v ollama &>/dev/null; then
  warn "Ollama no encontrado. Necesario para diaries-ocr con PDFs escaneados."
  warn "Instala desde https://ollama.com y luego ejecuta:"
  echo -e "       ${D}ollama pull Maternion/LightOnOCR-2:1b${NC}  (modelo primario)"
  echo -e "       ${D}ollama pull glm-ocr${NC}                    (fallback)"
else
  if ollama list 2>/dev/null | grep -q "LightOnOCR"; then
    ok "LightOnOCR-2:1b disponible (modelo primario)"
  else
    warn "Modelo primario no instalado. Para OCR de PDFs escaneados:"
    echo -e "       ${D}ollama pull Maternion/LightOnOCR-2:1b${NC}"
  fi
  if ollama list 2>/dev/null | grep -q "glm-ocr"; then
    ok "glm-ocr disponible (fallback)"
  else
    warn "Modelo de fallback no instalado (opcional):"
    echo -e "       ${D}ollama pull glm-ocr${NC}"
  fi
fi

# ── Resumen ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${D}────────────────────────────────────────────────────────────────${NC}"
echo -e "${G}Proyecto preparado${NC}"
echo ""
echo -e "  Skills diaries-* presentes: ${G}${PRESENT}${NC}/18"
[[ $MISSING -gt 0 ]] && echo -e "  Faltan en ~/.claude/skills/: ${Y}${MISSING}${NC}"
echo ""
echo -e "  Próximo paso:"
echo -e "  ${D}1.${NC} Copia tus fuentes en  ${D}source/{iso2}/raw/${NC}"
echo -e "  ${D}2.${NC} Abre Claude Code desde la raíz del proyecto y ejecuta  ${B}/diaries-bootstrap --country {iso2}${NC}"
echo -e "  ${D}3.${NC} O empieza con  ${B}/diaries-teach${NC}  para la guía interactiva"
echo ""
