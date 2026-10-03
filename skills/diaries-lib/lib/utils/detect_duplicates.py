#!/usr/bin/env python3
"""
Detecta y (opcionalmente) pone en cuarentena ESCANEOS DUPLICADOS de un corpus de diarios:
la misma sesión catalogada bajo >1 session_id (familias _N del mismo día re-escaneadas, o
nombres de archivo corridos ±N días respecto a la fecha real).

SEÑAL FIABLE (no usar solo el contenido): número de BOLETÍN (id único y monotónico del diario,
en el masthead "NÚMERO N") + FECHA REAL del masthead verificada por el DÍA DE LA SEMANA.
Regla: duplicado = MISMO boletín Y MISMA fecha real. Mismo día con boletines distintos =
sesiones legítimas (mañana/tarde) → NO se tocan. El solapamiento de texto (Jaccard) da falsos
negativos (escaneos dup con distinta calidad OCR puntúan bajo); se usa solo como respaldo cuando
no hay boletín legible.

CLI:
    python detect_duplicates.py --country uy [--write] [--threshold 0.35]
    (dry-run por defecto; imprime el plan. --write mueve a cuarentena y actualiza estado.)

FECHA DE AGRUPACIÓN: se deriva de meta/{sid}.json (campo date, ya validado por diaries-meta) y,
en su defecto, de una fecha ISO o compacta YYYYMMDD dentro del session_id (con validación real de
mes/día). Sesiones sin fecha derivable se EXCLUYEN de la clusterización (nunca agrupar por prefijo
arbitrario del nombre: con ids tipo diario_YYYYMMDDn el prefijo trunca a "diario_YYY" y produce
clusters falsos masivos). Guard adicional: clusters con >max_redundant_per_cluster redundantes o
que mezclan fechas de meta distintas se degradan a revisión, no al plan de cuarentena.

Rutas relativas al proyecto (cwd). Reversible: mueve a source/{iso}/_quarantine_duplicates/
con manifest.json (redundant→keeper); restaurar = mover de vuelta.
"""
import sys, re, json, argparse, shutil, subprocess
from pathlib import Path
from datetime import date
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

LIB_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(LIB_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import yaml
from extract_meta import _MONTHS_ES
from lib.state_manager import StateManager

PROJECT_ROOT = Path.cwd()
SUBDIRS = ["corrected", "tagged", "extracted", "meta"]

# Stems de día de la semana (ES + PT) → índice (lunes=0)
_WD_STEMS = [("lun",0),("seg",0),("mar",1),("ter",2),("mié",2),("mi",2),("mil",2),
             ("qua",3),("jue",3),("qui",4),("vie",4),("sex",4),("sáb",5),("sab",5),("dom",6)]
def _wd_index(tok):
    t = tok.lower()
    for pre, i in _WD_STEMS:
        if t.startswith(pre):
            return i
    return None

# Defaults razonables (sobreescribibles por country_config bajo `dedupe:`)
_DEF_BULLETIN = r"\bN[ÚU]MERO?\s*0*(\d{2,5})\b"
# masthead con día de la semana: "<CIUDAD>, <weekday> <dd> DE <mes> DE <yyyy>"
_DEF_MASTHEAD = (r"[A-ZÁÉÍÓÚ]{4,},?\s+([A-Za-zÁÉÍÓÚáéíóú]+)\.?\s+"
                 r"(\d{1,2}|1[gº°o])\s*[º°ªgo.]*\s+DE\s+([A-Za-zÁÉÍÓÚáéíóú]+)\s+DE\s+(\d{4})")


def _weekday(y, m, d):
    try: return date(y, m, d).weekday()
    except Exception: return None


_ISO_DATE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")

def _valid_iso(y, m, d):
    """'YYYY-MM-DD' si (y,m,d) es una fecha real y plausible (1800–2100); None si no."""
    try:
        y, m, d = int(y), int(m), int(d)
        if not 1800 <= y <= 2100: return None
        return date(y, m, d).isoformat()
    except (ValueError, TypeError):
        return None

def _date_from_sid(sid):
    """Extrae la fecha del session_id: ISO (YYYY-MM-DD) o compacta (YYYYMMDD), con validación
    real de mes/día. Tolera sufijos numéricos pegados (diario_YYYYMMDDn). None si no hay fecha."""
    m = _ISO_DATE.search(sid)
    if m:
        v = _valid_iso(*m.groups())
        if v: return v
    for run in re.findall(r"\d{8,}", sid):
        v = _valid_iso(run[:4], run[4:6], run[6:8])
        if v: return v
    return None


class Detector:
    def __init__(self, iso, cfg):
        self.iso = iso
        self.src = PROJECT_ROOT / f"source/{iso}"
        self.corr = self.src / "corrected"
        self.ocr = self.src / "ocr"
        self.raw = self.src / "raw"
        self.meta = self.src / "meta"
        self.quar = self.src / "_quarantine_duplicates"
        dd = (cfg.get("dedupe") or {})
        self.re_bull = re.compile(dd.get("bulletin_regex", _DEF_BULLETIN), re.I)
        self.re_mast = re.compile(dd.get("masthead_weekday_regex", _DEF_MASTHEAD), re.I)
        self.sim_thr = float(dd.get("content_sim_threshold", 0.35))
        self.near_days = int(dd.get("near_days", 10))
        self.max_reds = int(dd.get("max_redundant_per_cluster", 5))
        # `dedupe.exclude_sessions`: sesiones que la revisión humana decidió NO cuarentenar.
        # Caso de uso real (EC 2026-07-25): dos actas declaran el MISMO número pero difieren 10x
        # en tamaño → la grande puede ser un COMPILATORIO multi-sesión, y cuarentenar la pequeña
        # taparía ese problema de fondo. Se apartan ANTES de clusterizar, así no arrastran a su
        # keeper ni aparecen en el plan.
        self.exclude = set(dd.get("exclude_sessions") or [])
        self._meta_dates, self._dates, self._meta_snums = {}, {}, {}

    # ── fecha de agrupación: meta (validada por diaries-meta) > session_id > None ──
    def meta_date(self, sid):
        if sid not in self._meta_dates:
            v = None
            mf = self.meta / f"{sid}.json"
            if mf.exists():
                try:
                    raw = str((json.load(open(mf)) or {}).get("date") or "")
                    m = _ISO_DATE.search(raw)
                    if m: v = _valid_iso(*m.groups())
                except Exception:
                    pass
            self._meta_dates[sid] = v
        return self._meta_dates[sid]

    def session_date(self, sid):
        if sid not in self._dates:
            self._dates[sid] = self.meta_date(sid) or _date_from_sid(sid)
        return self._dates[sid]

    def meta_snum(self, sid):
        """Identificador de sesión desde meta (validado por diaries-meta): session_number
        cualificado por session_type (la numeración es por tipo: ordinaria/asamblea/...).
        None si meta no trae session_number."""
        if sid not in self._meta_snums:
            v = None
            mf = self.meta / f"{sid}.json"
            if mf.exists():
                try:
                    m = json.load(open(mf)) or {}
                    raw = m.get("session_number")
                    if raw not in (None, ""):
                        v = f"{raw}|{str(m.get('session_type') or '').strip().lower()}"
                except Exception:
                    pass
            self._meta_snums[sid] = v
        return self._meta_snums[sid]

    # ── lectura de cabecera (corrected head + página 0 si existe) ──
    def _head(self, sid):
        parts = []
        cf = self.corr / f"{sid}.txt"
        if cf.exists():
            parts.append("\n".join(cf.read_text(encoding="utf-8", errors="replace").split("\n")[:10]))
        od = self.ocr / sid
        if od.is_dir():
            p = od / "page_0001.txt"
            if p.exists():
                parts.append("\n".join(p.read_text(encoding="utf-8", errors="replace").split("\n")[:10]))
        else:
            pdf = self.raw / f"{sid}.pdf"
            if pdf.exists():
                try:
                    parts.append(subprocess.run(["pdftotext", "-layout", "-f", "1", "-l", "1", str(pdf), "-"],
                                                 capture_output=True, timeout=60).stdout.decode("utf-8", "replace"))
                except Exception:
                    pass
        return "\n".join(parts)

    def _lines(self, sid):
        cf = self.corr / f"{sid}.txt"
        if not cf.exists(): return set()
        return set(l.strip() for l in cf.read_text(encoding="utf-8", errors="replace").split("\n") if len(l.strip()) > 15)

    def info(self, sid):
        head = self._head(sid)
        bull = self.re_bull.search(head)
        bull = bull.group(1) if bull else None
        real = self.session_date(sid)
        line = next((l for l in head.split("\n") if self.re_mast.search(l)), "")
        m = self.re_mast.search(line)
        if m:
            w = _wd_index(m.group(1)); day = int(re.sub(r"\D", "", m.group(2)) or 0)
            mon = _MONTHS_ES.get(m.group(3).lower()); year = int(m.group(4))
            if mon and w is not None:
                fd = int(real[8:10]) if real else None
                for cand in [day] + ([fd] if fd else []) + [1]:   # día masthead, día derivado, 1º
                    if 1 <= cand <= 31 and _weekday(year, mon, cand) == w:
                        real = f"{year:04d}-{mon:02d}-{cand:02d}"; break
        return sid, dict(real=real, bull=bull, n=len(self._lines(sid)))

    # ── construir plan ──
    def plan(self):
        allids = sorted(p.stem for p in self.corr.glob("*.txt"))
        if self.exclude:
            n0 = len(allids)
            allids = [s for s in allids if s not in self.exclude]
            print(f"AVISO: {n0-len(allids)} sesión(es) apartadas por dedupe.exclude_sessions: "
                  f"{', '.join(sorted(self.exclude))}", file=sys.stderr)
        # fecha de agrupación por sesión; sin fecha derivable → EXCLUIDA de la clusterización
        excluded = [s for s in allids if not self.session_date(s)]
        if excluded:
            print(f"AVISO: {len(excluded)} sesiones sin fecha derivable (ni meta ni session_id), "
                  f"excluidas de la clusterización: {', '.join(excluded[:10])}"
                  + (" …" if len(excluded) > 10 else ""), file=sys.stderr)
        dated = [s for s in allids if self.session_date(s)]
        pref = defaultdict(list)
        for s in dated: pref[self.session_date(s)].append(s)
        # candidatos: familias del mismo día (>1) ∪ sesiones que comparten boletín
        cand = set(s for v in pref.values() if len(v) > 1 for s in v)
        with ThreadPoolExecutor(max_workers=12) as ex:
            base = dict(ex.map(self.info, dated))           # info de todas (para agrupar por boletín)
        bull_groups = defaultdict(list)
        for s, d in base.items():
            if d["bull"]: bull_groups[d["bull"]].append(s)
        for v in bull_groups.values():
            if len(v) > 1: cand.update(v)
        D = base
        lines_cache = {}
        def lines(s):
            if s not in lines_cache: lines_cache[s] = self._lines(s)
            return lines_cache[s]
        def jac(a, b):
            A, B = lines(a), lines(b)
            return len(A & B) / len(A | B) if A and B else 0.0

        bydate = defaultdict(list)
        for s in cand: bydate[D[s]["real"]].append(s)

        plan, review, guard = [], [], []
        clustered_all = set()
        for d, sids in bydate.items():
            if len(sids) < 2: continue
            used = set()
            for i, s in enumerate(sids):
                if s in used: continue
                cluster = [s]
                for t in sids[i+1:]:
                    if t in used: continue
                    # identificador de sesión: boletín masthead > session_number de meta.
                    # Identificadores DISTINTOS = sesiones legítimas del mismo día → nunca
                    # agrupar por Jaccard (comparten boilerplate: cabeceras, mesa, asistencia).
                    same_id = diff_id = False
                    if D[s]["bull"] and D[t]["bull"]:
                        same_id = D[s]["bull"] == D[t]["bull"]; diff_id = not same_id
                    else:
                        ss, ts = self.meta_snum(s), self.meta_snum(t)
                        if ss and ts:
                            same_id = ss == ts; diff_id = not same_id
                    if same_id or (not diff_id and jac(s, t) >= self.sim_thr):
                        cluster.append(t); used.add(t)
                used.add(s)
                if len(cluster) > 1:
                    keeper = max([c for c in cluster if self.session_date(c) == d] or cluster,
                                 key=lambda x: D[x]["n"])
                    reds = [c for c in cluster if c != keeper]
                    entry = dict(date=d, keeper=keeper, bull=D[keeper]["bull"], reds=reds,
                                 lens={c: D[c]["n"] for c in cluster})
                    # guard: cluster sospechoso → revisión manual, nunca al plan de cuarentena
                    metas = {self.meta_date(c) for c in cluster} - {None}
                    reasons = []
                    if len(reds) > self.max_reds:
                        reasons.append(f"{len(reds)} redundantes > máx {self.max_reds}")
                    if len(metas) > 1:
                        reasons.append(f"mezcla fechas de meta distintas: {sorted(metas)}")
                    if reasons:
                        entry["reason"] = "; ".join(reasons)
                        guard.append(entry)
                    else:
                        plan.append(entry)
                    clustered_all.update(cluster)
        # boletín compartido pero fecha real DISTINTA y contenido NO similar → posible OCR mal leído
        for b, sids in bull_groups.items():
            if len(sids) < 2: continue
            rest = [s for s in sids if s not in clustered_all]
            if len(rest) >= 2:
                review.append(dict(bull=b, sids=sorted(rest),
                                   reals={s: D[s]["real"] for s in rest}))
        return plan, review, guard, excluded, D

    # ── ejecutar cuarentena ──
    def quarantine(self, plan):
        for sub in SUBDIRS + ["ocr", "raw"]:
            (self.quar / sub).mkdir(parents=True, exist_ok=True)
        sm = StateManager(PROJECT_ROOT, self.iso); sm.load()
        # fusiona con un manifiesto previo (no perder registros de ejecuciones anteriores)
        mpath = self.quar / "manifest.json"
        manifest = json.load(open(mpath)) if mpath.exists() else []
        seen = {e["redundant"] for e in manifest}
        moved = 0
        for p in plan:
            for sid in p["reds"]:
                for sub in SUBDIRS:
                    ext = ".json" if sub == "meta" else ".txt"
                    f = self.src / sub / f"{sid}{ext}"
                    if f.exists(): shutil.move(str(f), str(self.quar / sub / f"{sid}{ext}"))
                od = self.ocr / sid
                if od.is_dir(): shutil.move(str(od), str(self.quar / "ocr" / sid))
                rp = self.raw / f"{sid}.pdf"
                if rp.exists() or rp.is_symlink(): shutil.move(str(rp), str(self.quar / "raw" / f"{sid}.pdf"))
                sm.mark_skill(session_id=sid, skill="diaries-dedupe", status="skipped",
                              confidence=0.0, error=f"Duplicado de {p['keeper']} (boletín {p['bull']}); en cuarentena")
                if sid not in seen:
                    manifest.append({"redundant": sid, "keeper": p["keeper"], "bulletin": p["bull"], "date": p["date"]})
                    seen.add(sid)
                moved += 1
            # keeper: fijar fecha real + marcar dedupe complete
            kf = self.meta / f"{p['keeper']}.json"
            if kf.exists():
                m = json.load(open(kf)); m["date"] = p["date"]
                kf.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
            sm.mark_skill(session_id=p["keeper"], skill="diaries-dedupe", status="complete",
                          confidence=1.0, output=str(kf) if kf.exists() else None)
        sm.save()
        (self.quar).mkdir(parents=True, exist_ok=True)
        json.dump(manifest, open(self.quar / "manifest.json", "w"), ensure_ascii=False, indent=2)
        return moved


def main():
    ap = argparse.ArgumentParser(description="Detecta/cuarentena duplicados de sesiones")
    ap.add_argument("--country", required=True)
    ap.add_argument("--write", action="store_true", help="ejecuta la cuarentena (si no, dry-run)")
    args = ap.parse_args()
    iso = args.country.lower()
    cfg_path = PROJECT_ROOT / f"country_config/{iso}.yaml"
    cfg = yaml.safe_load(cfg_path.read_text()) if cfg_path.exists() else {}
    det = Detector(iso, cfg)
    plan, review, guard, excluded, D = det.plan()
    n_red = sum(len(p["reds"]) for p in plan)
    out = {
        "country": iso,
        "duplicate_clusters": len(plan),
        "redundant_sessions": n_red,
        "plan": [{"date": p["date"], "keeper": p["keeper"], "bulletin": p["bull"], "redundant": p["reds"]} for p in plan],
        "review_guard_clusters": [{"date": p["date"], "keeper": p["keeper"], "bulletin": p["bull"],
                                   "redundant": p["reds"], "reason": p["reason"]} for p in guard],
        "review_shared_bulletin_distinct": review,   # boletín compartido pero parecen distintas → revisar
        "excluded_no_date": excluded,                # sin fecha derivable (meta ni session_id) → fuera de clusterización
        "written": False,
    }
    if args.write:
        out["written"] = True
        out["moved"] = det.quarantine(plan)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
