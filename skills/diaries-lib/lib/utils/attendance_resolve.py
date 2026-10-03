#!/usr/bin/env python3
"""attendance_resolve.py — Mapea las listas de asistencia a id_dep por fecha y
constriñe el matching de oradores al conjunto de PRESENTES de cada sesión.

Pipeline:
  1. Lee `attendance.csv` (de parse_attendance.py) + `deputies.csv`.
  2. Mapea cada nombre PRESENTE → id_dep del roster (fuzzy token_set_ratio sobre
     nombre_completo + filtro/bonus de vigencia temporal por año de la sesión).
     Escribe `attendance_index.csv` (date;id_dep;name_raw;nombre_completo;score).
     → índice por fecha: date → {id_dep presentes}.
  3. Re-resuelve `matching_table.csv` usando ese índice:
       Para cada speaker_raw, candidatos = diputados cuyo nombre/apellido casa
       (índice invertido de tokens). Se prefiere el candidato PRESENTE en las
       sesiones donde el speaker interviene. Como la asistencia es por-sesión,
       el MISMO apellido puede resolver a personas distintas según la fecha →
       se emiten overrides por (date, speaker_raw) cuando la resolución varía.
  4. Escribe matching_table.csv mejorado (global, retrocompatible) +
     matching_overrides.csv (date;speaker_raw;id_dep;nombre_completo;method).

Solo el conjunto `present` constriñe oradores (los ausentes —licencia/faltan—
no pudieron hablar). Diseñado país-agnóstico: cualquier corpus con pase de lista.

Uso:
  python attendance_resolve.py --country uy \
      --attendance source/uy/match/attendance.csv \
      --deputies   source/uy/deputies/deputies.csv \
      --interventions source/uy/matrix/interventions_raw.csv \
      --matching   source/uy/match/matching_table.csv \
      --index-out  source/uy/match/attendance_index.csv \
      --overrides-out source/uy/match/matching_overrides.csv \
      --map-threshold 88 --constrain-threshold 82
"""
import argparse, csv, json, re, sys, unicodedata, collections
from rapidfuzz import fuzz

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def norm(s):
    s = unicodedata.normalize('NFD', (s or '').lower().strip())
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', s)).strip()


def load_deputies(path):
    dep = []
    with open(path, encoding='utf-8') as f:
        for r in csv.DictReader(f, delimiter=';'):
            dep.append({
                'id': r['id_dep'],
                'full': r['nombre_completo'],
                'nfull': norm(r['nombre_completo']),
                'nape': norm(r.get('apellidos', '')),
                'fi': (r.get('fecha_inicio') or '')[:4],
                'ff': (r.get('fecha_fin') or '')[:4],
            })
    return dep


def build_index(dep):
    """token normalizado -> [índices de dep]."""
    idx = collections.defaultdict(list)
    for i, d in enumerate(dep):
        for t in set(d['nfull'].split()):
            if len(t) >= 3:
                idx[t].append(i)
    return idx


def vig(d, year):
    return bool(d['fi'] and d['ff'] and year and d['fi'] <= year <= d['ff'])


PARTICLES = {'de', 'del', 'la', 'las', 'los', 'y', 'e', 'da', 'do', 'dos',
             'das', 'von', 'van', 'di', 'le', 'don', 'dona'}


def strong_tokens(nq):
    """Tokens informativos de una cadena normalizada (sin partículas/iniciales)."""
    return [t for t in nq.split()
            if len(t) >= 4 and t not in PARTICLES and not re.match(r'^[a-z]$', t)]


def _tok_match(q, dep_tokens):
    """¿algún token del diputado casa (exacto/fuzzy/prefijo) con el token q?"""
    for dt in dep_tokens:
        if q == dt:
            return True
        if len(q) >= 4 and len(dt) >= 4 and (q in dt or dt in q):
            return True
        if fuzz.ratio(q, dt) >= 82:           # tolera ruido OCR (Supparo/Suppano)
            return True
    return False


def candidates_for(query, dep, idx, min_cov=0.7):
    """Candidatos cuyo nombre cubre los tokens fuertes del speaker_raw.

    Devuelve [(idx, coverage, name_score)] con coverage = fracción de tokens
    fuertes del query hallados (fuzzy) en el diputado. Gate por cobertura de
    tokens (no por token_set_ratio, que da 100 a cualquier apellido-subconjunto).
    """
    nq = norm(query)
    strong = strong_tokens(nq)
    toks = [t for t in nq.split() if len(t) >= 3]
    pool = set()
    for t in toks:
        pool.update(idx.get(t, []))
    if not pool and len(nq) >= 4:
        for i, d in enumerate(dep):
            if d['nape'].startswith(nq) or nq in d['nape'].split():
                pool.add(i)
    out = []
    for ci in pool:
        d = dep[ci]
        dep_tokens = d['nfull'].split()
        if strong:
            matched = sum(1 for q in strong if _tok_match(q, dep_tokens))
            cov = matched / len(strong)
        else:
            # query sin tokens fuertes (apellido muy corto): exige aparición exacta
            cov = 1.0 if any(_tok_match(t, dep_tokens) for t in toks) else 0.0
        if cov >= min_cov:
            sc = fuzz.token_set_ratio(nq, d['nfull'])
            out.append((ci, round(cov, 3), sc))
    # mejor cobertura primero, luego score de nombre
    out.sort(key=lambda x: (-x[1], -x[2]))
    return out


def parse_speaker(sp):
    """speaker_raw → (surname_tokens, hint_tokens).

    Formato típico: "APELLIDO(S) (Nombre)" o "APELLIDO, Nombre". Lo que va dentro
    del paréntesis (o tras la coma) es pista de NOMBRE de pila; lo previo, apellidos.
    """
    hint = []
    m = re.search(r'\(([^)]*)\)', sp)
    if m:
        hint = [t for t in norm(m.group(1)).split()
                if t not in PARTICLES and len(t) >= 3]
        sp = sp[:m.start()] + ' ' + sp[m.end():]
    head = sp.split(',', 1)[0]            # quita ", Nombre" si lo hay
    sur = [t for t in norm(head).split()
           if len(t) >= 4 and t not in PARTICLES]
    return sur, hint


def present_fuzzy_one_session(sur, hint, present, id_ape_list, id_tokens,
                              sur_strict=0.86, sur_wide=0.78, hint_min=0.85,
                              w_sur=0.45, w_hint=0.55, accept=0.80, margin=0.08):
    """Mejor candidato dentro de los diputados PRESENTES de UNA sesión (no del roster
    completo, ni de la unión de sesiones). Comparar contra el conjunto reducido de
    presentes de la sesión es la clave de precisión: el universo de candidatos es
    quién realmente pudo hablar ese día, lo que baja drásticamente la probabilidad de
    falso positivo. La unicidad se evalúa DENTRO de la sesión.

    Rescata variantes OCR del apellido que no comparten token exacto con el roster
    (`ABADALA`/`ABDLA`/`ABDOLA`→`Abdala`). **Filtro progresivo por evidencia combinada**:
    el apellido se compara solo contra tokens de APELLIDO (no nombre de pila → evita
    `TOMA`→`Tomás`); `ss` = peor cobertura de los apellidos del speaker (todos deben
    cubrirse → `RODRIGUEZ CAMUSO`=`Rodríguez Camusso`, no `Andrade Rodríguez`).
    - **Sin pista de nombre**: solo apellido → umbral estricto `ss ≥ sur_strict`.
    - **Con pista** (paréntesis): ventana ancha `sur_wide` + `combined = w_sur·ss +
      w_hint·hs` (hs = nombre de pila vs nombre COMPLETO del presente, porque la
      separación nombre/apellidos del roster es ruidosa). Un apellido flojo se vuelve
      confiable si el nombre encaja; uno fuerte no basta si el nombre no encaja.
    Se exige que el mejor candidato **de la sesión** sea único (supere al 2º por
    `margin`); si no, ambiguo → None.

    Devuelve (id_dep, score 0-100) o None.
    """
    if not sur or not present:
        return None

    def surname_cov(cid):
        ape = id_ape_list.get(cid)
        if not ape:
            return 0.0
        return min(max((fuzz.ratio(s, t) for t in ape), default=0) for s in sur) / 100.0

    scored = []
    for cid in present:
        ss = surname_cov(cid)
        if hint:
            if ss < sur_wide:
                continue
            toks = id_tokens.get(cid, ())
            hs = max((fuzz.ratio(h, t) for h in hint for t in toks), default=0) / 100.0
            if hs < hint_min:
                continue
            scored.append((w_sur * ss + w_hint * hs, cid))
        else:
            if ss >= sur_strict:
                scored.append((ss, cid))
    if not scored:
        return None
    scored.sort(reverse=True)
    top_s, top_id = scored[0]
    if hint and top_s < accept:
        return None
    # unicidad DENTRO de la sesión: si dos presentes encajan casi igual, es ambiguo
    if len(scored) > 1 and (top_s - scored[1][0]) < margin:
        return None
    return (top_id, top_s * 100)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--country', required=True)
    ap.add_argument('--attendance', required=True)
    ap.add_argument('--deputies', required=True)
    ap.add_argument('--interventions', required=True)
    ap.add_argument('--matching', required=True)
    ap.add_argument('--index-out', required=True)
    ap.add_argument('--overrides-out', required=True)
    ap.add_argument('--matching-out', default=None,
                    help='si se da, reescribe matching_table mejorado (default: in place)')
    ap.add_argument('--map-threshold', type=float, default=88.0,
                    help='umbral para mapear nombre de asistencia → id_dep')
    ap.add_argument('--constrain-threshold', type=float, default=82.0,
                    help='umbral para candidatos de speaker_raw a constreñir')
    ap.add_argument('--attendance-sim', type=float, default=86.0,
                    help='umbral ESTRICTO de apellido (sin pista de nombre) vs la '
                         'lista de presentes (rescate de variantes OCR sin token exacto)')
    ap.add_argument('--hint-wide', type=float, default=78.0,
                    help='umbral ANCHO de apellido cuando hay pista de nombre de pila '
                         '(filtro progresivo: apellido flojo + nombre fuerte → match). '
                         'Suelo de ruido empírico ~67 (apellidos casuales tipo '
                         'bergara/garcia); variantes OCR reales ≥83 → 78 separa limpio.')
    ap.add_argument('--hint-accept', type=float, default=80.0,
                    help='umbral del score combinado (apellido+nombre) para aceptar '
                         'un rescate con pista de nombre')
    args = ap.parse_args()

    dep = load_deputies(args.deputies)
    idx = build_index(dep)

    # ── 1. Mapear PRESENTES → id_dep por fecha (con caché) ────────────────────
    present_rows = []
    with open(args.attendance, encoding='utf-8') as f:
        for r in csv.DictReader(f, delimiter=';'):
            if r['status'] == 'present':
                present_rows.append(r)

    cache = {}
    date_present = collections.defaultdict(set)   # date -> {id_dep}
    index_out = []
    mapped = unmapped = 0
    for r in present_rows:
        name, date = r['name_raw'], r['date']
        year = date[:4]
        key = (norm(name), year)
        if key not in cache:
            cands = candidates_for(name, dep, idx, min_cov=0.7)
            # ranking: score de nombre + bonus vigencia; desempate por vigencia
            best = None; bscore = -1; bvig = False; tie = False
            for ci, cov, sc in cands:
                if sc < args.map_threshold:
                    continue
                v = vig(dep[ci], year)
                eff = sc + (8 if v else 0)
                if eff > bscore + 1e-9:
                    bscore, best, bvig, tie = eff, ci, v, False
                elif abs(eff - bscore) <= 1e-9:
                    tie = True
            # acepta solo si hay ganador claro y vigente (alta precisión)
            if best is not None and not (tie and not bvig):
                cache[key] = (dep[best]['id'], dep[best]['full'], round(bscore, 1))
            else:
                cache[key] = None
        res = cache[key]
        if res:
            date_present[date].add(res[0])
            index_out.append((date, res[0], name, res[1], res[2]))
            mapped += 1
        else:
            unmapped += 1

    with open(args.index_out, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['date', 'id_dep', 'name_raw', 'nombre_completo', 'score'])
        w.writerows(sorted(set(index_out)))

    # ── 2. Fechas de cada speaker_raw ─────────────────────────────────────────
    sp_dates = collections.defaultdict(set)
    with open(args.interventions, encoding='utf-8') as f:
        for r in csv.DictReader(f, delimiter=';'):
            sp = (r.get('speaker_raw') or '').strip()
            d = (r.get('date') or '').strip()
            if sp and d:
                sp_dates[sp].add(d)

    # ── 3. Cargar matching_table actual ───────────────────────────────────────
    mt = {}
    header = ['speaker_raw', 'id_dep', 'nombre_completo', 'match_method', 'confidence', 'notas']
    with open(args.matching, encoding='utf-8') as f:
        rd = csv.DictReader(f, delimiter=';')
        for r in rd:
            mt[r['speaker_raw']] = r

    overrides = []          # (date, speaker_raw, id_dep, nombre_completo, method)
    stats = collections.Counter()
    id2full = {d['id']: d['full'] for d in dep}
    # apellidos (tokens, para cobertura del apellido) y nombre completo (tokens,
    # para verificar la pista de nombre de pila) por id, para el rescate por
    # similitud contra la lista de presentes
    id_ape_list = {}
    id_tokens = collections.defaultdict(set)
    for d in dep:
        ape = d['nape'].split()
        if d['id'] not in id_ape_list and ape:
            id_ape_list[d['id']] = ape
        id_tokens[d['id']].update(d['nfull'].split())

    def is_protected(sp):
        # role: cargo rotativo sin id_dep por diseño.
        # manual: corrección humana → máxima autoridad, NUNCA se sobrescribe.
        return mt.get(sp, {}).get('match_method') in ('role', 'manual')

    for sp, dates in sp_dates.items():
        if is_protected(sp):
            continue
        cur = mt.get(sp, {})
        cur_id = (cur.get('id_dep') or '').strip()
        cur_method = cur.get('match_method', '')
        # Candidatos por NOMBRE del roster (índice de tokens exactos): se usan solo
        # como conjunto, intersectado con los PRESENTES de cada sesión más abajo.
        cands = candidates_for(sp, dep, idx, min_cov=0.7)
        cands = [(ci, cov, sc) for ci, cov, sc in cands if sc >= args.constrain_threshold]
        roster_score = {}
        for ci, cov, sc in cands:
            rid = dep[ci]['id']
            roster_score[rid] = max(roster_score.get(rid, 0), sc)

        sur, hint = parse_speaker(sp)

        # ── Resolución POR SESIÓN — el universo de candidatos es siempre el conjunto
        #    de diputados PRESENTES de esa sesión (no el roster, ni la unión de
        #    sesiones); esto es lo que minimiza los falsos positivos.
        per_date = {}
        for d in dates:
            present = date_present.get(d, set())
            if not present:
                continue                 # sin lista de presentes esa fecha → no toca
            pool = {}
            # (a) candidatos por nombre del roster que ESTÁN presentes esa sesión
            for cid in roster_score:
                if cid in present:
                    pool[cid] = roster_score[cid]
            # (b) rescate fuzzy del apellido DENTRO de los presentes de la sesión
            one = present_fuzzy_one_session(
                sur, hint, present, id_ape_list, id_tokens,
                sur_strict=args.attendance_sim / 100.0,
                sur_wide=args.hint_wide / 100.0,
                accept=args.hint_accept / 100.0)
            if one:
                pool[one[0]] = max(pool.get(one[0], 0), one[1])
            if pool:
                per_date[d] = max(pool, key=pool.get)

        if not per_date:
            continue
        resolved_ids = set(per_date.values())
        # global: id presente en más fechas
        cov = collections.Counter(per_date.values())
        global_id, global_n = cov.most_common(1)[0]
        global_full = id2full.get(global_id, '')
        coverage = global_n / len(dates)

        # ¿la asistencia cambia la asignación global?
        # Exige soporte de asistencia suficiente (evita falsos positivos por
        # apellido compartido con bajísima cobertura).
        improved = False
        if coverage >= 0.5:
            if cur_method in ('', 'unmatched') or not cur_id:
                improved = True       # rescata un no-vinculado
                stats['rescued'] += 1
            elif cur_id != global_id:
                improved = True       # corrige una asignación distinta
                stats['corrected'] += 1

        if improved:
            mt.setdefault(sp, {'speaker_raw': sp})
            mt[sp]['id_dep'] = global_id
            mt[sp]['nombre_completo'] = global_full
            mt[sp]['match_method'] = 'attendance'
            mt[sp]['confidence'] = f"{min(0.99, 0.70 + 0.29*coverage):.2f}"
            mt[sp]['notas'] = f"asistencia cov={coverage:.2f} ({global_n}/{len(dates)} sesiones)"

        # overrides por-fecha: cuando una fecha resuelve a un id distinto del global
        if len(resolved_ids) > 1:
            for d, cid in per_date.items():
                if cid != global_id:
                    overrides.append((d, sp, cid, id2full.get(cid, ''), 'attendance'))
            stats['split_speakers'] += 1

    # ── 4. Escribir salidas ───────────────────────────────────────────────────
    overrides = sorted(set(overrides))
    with open(args.overrides_out, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['date', 'speaker_raw', 'id_dep', 'nombre_completo', 'match_method'])
        w.writerows(overrides)

    out_path = args.matching_out or args.matching
    rows = sorted(mt.values(), key=lambda r: r['speaker_raw'].lower())
    with open(out_path, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=header, delimiter=';', extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in header})

    print(json.dumps({
        'present_rows': len(present_rows),
        'present_mapped': mapped,
        'present_unmapped': unmapped,
        'map_rate': round(mapped / max(len(present_rows), 1), 4),
        'dates_with_present': len(date_present),
        'attendance_index_rows': len(set(index_out)),
        'speakers_rescued': stats['rescued'],
        'speakers_corrected': stats['corrected'],
        'speakers_split_by_date': stats['split_speakers'],
        'overrides': len(overrides),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
