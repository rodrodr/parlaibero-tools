"""
Separación de nombre y apellidos con reglas específicas por idioma.

Idiomas soportados:
  'pt'  — Portugués (Portugal y Brasil)
  'es'  — Español

Uso:
    from lib.utils.split_name import split_name
    nombre, apellidos = split_name("Abel Augusto de Almeida Carneiro", lang='pt',
                                   parl_name="Abel Carneiro")
    # Con diccionario de prenomes (claves sin acentos) para mayor precisión:
    nombre, apellidos = split_name("Diogo Pinto de Freitas do Amaral", lang='pt',
                                   parl_name="Freitas do Amaral",
                                   prenomes_dict={'diogo', 'abel', 'antonio', ...})
"""

import unicodedata
from typing import Optional

PT_PARTICLES = {'de', 'do', 'da', 'dos', 'das', 'e'}
ES_PARTICLES = {'de', 'del', 'la', 'los', 'las', 'y'}


def split_name(full_name: str, lang: str = 'pt', parl_name: str = '',
               prenomes_dict: Optional[set] = None) -> tuple[str, str]:
    """
    Separa nombre y apellidos según las convenciones del idioma.

    Portugués ('pt') — lógica en cuatro pasos:
      1. Si la primera palabra del parlamentario NO está en posición 0 del nombre
         completo Y no es un prenome conocido → todo lo anterior son prenomes.
         Si es un prenome conocido en pos > 0, cae al PASO 2/3.
      2. Con partícula: si el parlamentario confirma >1 prenome inicial consecutivo
         → split en esa frontera (ej. "António Júlio …").
      3. Con partícula: la palabra inmediatamente antes de la primera partícula es
         apellido compuesto SALVO que sea un prenome conocido (en cuyo caso la
         partícula inicia los apellidos). Si no es prenome, retroceder hasta
         encontrar la frontera real.
      4. Sin partícula: regla conservadora — surname_start = n.º de prenomes iniciales
         confirmados por el parlamentario (mínimo 1), extendido con prenomes_dict.

    El prenomes_dict debe usar claves sin acentos (norm_ascii) para comparación robusta.

    Español ('es'):
        Apellidos = últimas 2 palabras + partícula prepositiva precedente si la hay.

    Retorna (nombre, apellidos).
    """
    if lang == 'pt':
        return _split_portuguese(full_name, parl_name, prenomes_dict)
    elif lang == 'es':
        return _split_spanish(full_name, parl_name)
    return _split_portuguese(full_name, parl_name, prenomes_dict)


def _norm(w: str) -> str:
    return unicodedata.normalize('NFC', w.strip().lower())


def _norm_ascii(w: str) -> str:
    """Normaliza sin acentos — para lookup en prenomes_dict."""
    s = unicodedata.normalize('NFD', w.strip().lower())
    return ''.join(c for c in s if unicodedata.category(c) != 'Mn')


def _in_prenomes(w: str, prenomes_dict: set) -> bool:
    return _norm_ascii(w) in prenomes_dict


def _prefix_match_count(parl_words: list[str], full_words: list[str]) -> int:
    """Número de palabras iniciales consecutivas de parl que coinciden con full."""
    count = 0
    for pi, pw in enumerate(parl_words):
        if pi < len(full_words) and _norm(full_words[pi]) == _norm(pw):
            count += 1
        else:
            break
    return count


def _split_portuguese(full_name: str, parl_name: str = '',
                      prenomes_dict: Optional[set] = None) -> tuple[str, str]:
    words = full_name.strip().split()
    if len(words) <= 1:
        return full_name, ''
    if len(words) == 2:
        return words[0], words[1]

    parl_words = parl_name.strip().split() if parl_name else []

    # ── PASO 1: parl empieza después de la posición 0 ────────────────────────────
    # Solo aplica si parl_first NO es un prenome conocido (si lo es, puede ser
    # un prenome abreviado → caer al PASO 2/3 para ubicar correctamente la frontera)
    if parl_words:
        parl_first = _norm(parl_words[0])
        for i, w in enumerate(words):
            if _norm(w) == parl_first:
                if i > 0:
                    parl_first_is_prenome = (prenomes_dict and _in_prenomes(parl_words[0], prenomes_dict))
                    if not parl_first_is_prenome:
                        # parl_first es un apellido → split aquí con walkback
                        split_pt = i
                        while split_pt > 0 and words[split_pt - 1].lower() in PT_PARTICLES:
                            split_pt -= 1
                        if prenomes_dict:
                            while split_pt > 1 and not _in_prenomes(words[split_pt - 1], prenomes_dict):
                                split_pt -= 1
                        split_pt = max(split_pt, 1)
                        return ' '.join(words[:split_pt]), ' '.join(words[split_pt:])
                    # parl_first es prenome → caer al PASO 2/3
                break  # empieza en posición 0 → continuar

    # ── Detectar primera partícula ───────────────────────────────────────────────
    first_particle_idx = None
    for i in range(1, len(words)):
        if words[i].lower() in PT_PARTICLES:
            first_particle_idx = i
            break

    # ── CASO SIN PARTÍCULA ───────────────────────────────────────────────────────
    if first_particle_idx is None:
        if not parl_words or len(parl_words) < 2:
            return ' '.join(words[:-1]), words[-1]

        # Si parl == full no aporta información de acortamiento → 1 prenome
        if _norm(' '.join(parl_words)) == _norm(full_name):
            return words[0], ' '.join(words[1:])

        # Prenomes confirmados = coincidencias iniciales consecutivas con parl[:-1]
        pm = _prefix_match_count(parl_words[:-1], words)
        surname_start = max(pm, 1)
        # Avanzar mientras la siguiente palabra sea un prenome confirmado
        if prenomes_dict:
            while surname_start < len(words) - 1 and _in_prenomes(words[surname_start], prenomes_dict):
                surname_start += 1
        return ' '.join(words[:surname_start]), ' '.join(words[surname_start:])

    # ── CASO CON PARTÍCULA ───────────────────────────────────────────────────────

    # Si parl == full no aporta información de acortamiento → 1 prenome
    if parl_words and _norm(' '.join(parl_words)) == _norm(full_name):
        surname_start = max(first_particle_idx - 1, 1)
        return ' '.join(words[:surname_start]), ' '.join(words[surname_start:])

    # PASO 2: si parl confirma >1 prenome inicial → frontera clara
    # Solo aplicar si la última palabra confirmada NO es una partícula
    if parl_words and len(parl_words) >= 2:
        pm = _prefix_match_count(parl_words[:-1], words)
        if pm > 1 and words[pm - 1].lower() not in PT_PARTICLES:
            return ' '.join(words[:pm]), ' '.join(words[pm:])

    # PASO 3: analizar la palabra antes de la primera partícula
    word_before = words[first_particle_idx - 1]
    parl_first_word = parl_words[0] if parl_words else ''

    if _norm(word_before) == _norm(parl_first_word):
        # Es el prenome principal → partícula inicia apellidos
        surname_start = first_particle_idx
    elif prenomes_dict and _in_prenomes(word_before, prenomes_dict):
        # Es otro prenome → partícula también inicia apellidos
        surname_start = first_particle_idx
    else:
        # Es inicio de apellido compuesto; retroceder mientras previas tampoco sean prenomes
        surname_start = first_particle_idx - 1
        if prenomes_dict:
            while surname_start > 1 and not _in_prenomes(words[surname_start - 1], prenomes_dict):
                surname_start -= 1

    surname_start = max(surname_start, 1)
    return ' '.join(words[:surname_start]), ' '.join(words[surname_start:])


def _split_spanish(full_name: str, parl_name: str = '') -> tuple[str, str]:
    words = full_name.strip().split()
    if len(words) <= 1:
        return full_name, ''
    if len(words) == 2:
        return words[0], words[1]
    # Apellidos = últimas 2 palabras; si van precedidas de partícula, incluirla
    for i in range(len(words) - 2, 0, -1):
        if words[i].lower() in ES_PARTICLES:
            return ' '.join(words[:i]), ' '.join(words[i:])
    return ' '.join(words[:-2]), ' '.join(words[-2:])
