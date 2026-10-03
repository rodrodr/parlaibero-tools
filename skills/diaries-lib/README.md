# diaries-lib — código y recursos compartidos de los skills `diaries-*`

Esta carpeta **no es un skill** (no tiene `SKILL.md`, no se invoca con `/`). Es el
**código compartido** que usan los 21 skills `diaries-*` del pipeline ParlaIbero, alojado
junto a ellos en `~/.claude/skills/` para que **todo el sistema esté autocontenido en el
área global de skills** y sea portable a cualquier proyecto sin copiar código.

## Contenido

```
diaries-lib/
├── lib/                       código del pipeline (fuente única)
│   ├── *.py                   schemas · confidence · state_manager · config_loader
│   │                          llm_client · minimax_client · ollama_client
│   ├── utils/*.py             utilidades invocadas por los skills (extract_text,
│   │                          tag_text, strip_headers, update_state, …)
│   └── utils_local/*.py       helpers puntuales
├── templates/_template.yaml   plantilla de country_config (la usa diaries-bootstrap)
│   utils/record_decision.py    registro de decisiones metodológicas (la usa diaries-decide)
├── requirements.txt           dependencias Python
├── install.sh                 prepara un proyecto (deps + dirs) y verifica los skills
└── README.md                  este archivo
```

## Cómo lo usan los skills

Cada `SKILL.md` invoca el código por su ruta global y opera sobre los **datos del proyecto**
(rutas relativas al directorio actual, que debe ser la raíz del proyecto):

```bash
python ~/.claude/skills/diaries-lib/lib/utils/extract_text.py \
  --input  source/{iso2}/raw/{id}.pdf \
  --config country_config/{iso2}.yaml \
  --output source/{iso2}/extracted/{id}.txt
```

- **Código** → siempre en `~/.claude/skills/diaries-lib/` (global, una sola copia).
- **Datos** → en el proyecto (`source/`, `state/`, `country_config/{iso2}.yaml`, `docs/`),
  referidos con rutas **relativas** al cwd.
- Las utilidades resuelven `import lib.*` porque su raíz (`parents[2] = diaries-lib`) contiene
  `lib/`; las que tocan datos del proyecto (`update_state`, `assess_source`,
  `analyze_speaker_markers`) usan `Path.cwd()` como raíz del proyecto.

## Modelo de fuente única

Los `SKILL.md` viven SOLO en `~/.claude/skills/diaries-*/` (versionados con git ahí). **No hay
copia en los repos de proyecto.** Se editan directamente (p.ej. con `/diaries-refine`). Este
`diaries-lib/` es el complemento de código de ese mismo modelo: única fuente, global.

## Nuevo proyecto

```bash
cd /ruta/al/nuevo/proyecto      # solo datos
bash ~/.claude/skills/diaries-lib/install.sh
# crea source/ state/ country_config/ docs/, instala deps, verifica los 21 skills
```


## Registro de decisiones metodológicas

`lib/utils/record_decision.py` persiste las decisiones del pipeline con su evidencia, para
que `/diaries-report` no tenga que reconstruir el razonamiento y para poder retomar el trabajo
sabiendo **por qué** se hizo algo.

```
state/{iso2}/decisions.jsonl        decisiones de un país
state/_transversal/decisions.jsonl  las que afectan a todos
```

**La evidencia es un campo obligatorio y validado** (mínimo 40 caracteres): existe para
impedir que se registre una preferencia como si fuera un hallazgo. Las decisiones **superadas
no se borran**: `--supersede` marca la anterior y la enlaza, y esa cadena es el historial de
correcciones del proyecto.

Lo consume el skill `/diaries-decide`; el documento se genera con
`python3 scripts/generar_metodologia.py` → `docs/_metodologia/generados/METODOLOGIA.md`.
