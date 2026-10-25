"""The figures and excerpts of «Un país desde cero» (es/pais.md, en/pais.md), from a real run of the diaries-* skills on
four sessions of the Bolivian Chamber of Deputies. The run lives outside the repository; this script reads it and
writes web/data/recorrido.json, which datos.py turns into the page's tables.

    python3 docs/tutorial/web/recorrido.py RUN_FOLDER
    python3 docs/tutorial/web/recorrido.py RUN_FOLDER --check FILE…   (the page's name guard, on the built files)

What goes into the JSON: counts recomputed from the run's files; the decision log without its text (ids, phases,
supersede links, and a one-line summary written here); the few figures measured during the run that left no file
(MEDIDO, with the section of the run's log); and short excerpts of the record. Every deputy's name is masked against
the run's roster, and the script refuses to write if a capitalised word outside the excerpts' vocabulary, a long
number or a line-end hyphen survives. Needs only the standard library.
"""
import csv
import json
import math
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

RUN = Path(sys.argv[1]).expanduser().resolve()
OUT = Path(__file__).resolve().parent / "data" / "recorrido.json"
SKILLS_COMMIT = "3935e4d"
SESSIONS = ["2024-03-13", "2024-03-26", "2024-07-31", "2024-08-01"]
csv.field_size_limit(sys.maxsize)


def rows(path, sep=None):
    with open(RUN / path, encoding="utf-8", newline="") as f:
        head = f.readline()
        f.seek(0)
        return list(csv.DictReader(f, delimiter=sep or max([",", ";"], key=head.count)))


def norm(s):
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


# ---------------------------------------------------------------- masking
ROSTER = rows("source/bo/deputies/deputies.csv")
TOKENS = {norm(t) for r in ROSTER for t in re.findall(r"[^\W\d_]+", r["nombre_completo"]) if len(t) >= 3}
TOKENS -= {"del", "las", "los", "san"}
W = r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+"
KEEP = [r"\bLA PAZ(?=, (?:LUNES|MARTES|MIÉRCOLES|JUEVES|VIERNES))"]      # the city in the session heading


def mask(text):
    kept = []

    def hold(m):
        kept.append(m[0])
        return f"\x01{len(kept) - 1}\x01"
    for k in KEEP:
        text = re.sub(k, hold, text)
    out = re.sub(rf"{W}(?:[ \-]+{W})*", lambda m: re.sub(W, lambda w: "\x00" if norm(w[0]) in TOKENS else w[0], m[0]), text)
    out = re.sub(r"\x00(?:[ \-]+(?:\x00|de|del|la|las|los|y|DE|DEL|LA))*[ \-]*\x00|\x00", "[N]", out)
    return re.sub(r"\x01(\d+)\x01", lambda m: kept[int(m[1])], out)


# The capitalised words the excerpts may keep. Anything else capitalised (a name missing from the roster, a minister,
# a private person) stops the script.
VOCAB = set("""
CÁMARA DE DIPUTADOS EL REDACTOR MARZO SESIÓN ORDINARIA LEGISLATURA LA PAZ MARTES PRESIDENTE EN EJERCICIO DIP
SECRETARIO SECRETARIA PRESIDENTA PAGE Bueno Diputados Diputadas Para Sesión Diputado Diputada Secretario Secretaria
Muchas Buenos Presidenta Presidente Vamos Chuquisaca Llama Gracias Ausencia Cuarto Intermedio Reasume Asume
Presidencia Existe Las Informe Proyecto Ley No Dispensación Mayoría Queda APROBADA Conclusiones Secretaría
""".split())


def guard(text, where):
    """Refuse a string that could carry a name or a personal number."""
    bare = text
    for k in KEEP:
        bare = re.sub(k, "", bare)
    assert not any(norm(w) in TOKENS for w in re.findall(W, bare)), f"{where}: a roster word survived the mask"
    assert not re.search(r"\d{6,}", text), f"{where}: a long number"
    assert not re.search(r"\w-\n", text), f"{where}: a line-end hyphen (a split name escapes the mask)"


def guard_excerpt(text, where):
    guard(text, where)
    odd = sorted({w for w in re.findall(W, text.replace("[N]", "")) if w[0].isupper() and w not in VOCAB})
    assert not odd, f"{where}: capitalised words outside the vocabulary: {len(odd)}"


# ---------------------------------------------------------------- the run's files
def read(stage, date):
    return (RUN / f"source/bo/{stage}/{date}.txt").read_text(encoding="utf-8")


CANON = rows("source/bo/standardize/BO_interventions.csv")
META = {d: json.loads((RUN / f"source/bo/meta/{d}.json").read_text(encoding="utf-8")) for d in SESSIONS}
STATE = json.loads((RUN / "state/bo/pipeline_state.json").read_text(encoding="utf-8"))
LOG = [json.loads(x) for x in (RUN / "state/bo/decisions.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
INFO = json.loads((RUN / "docs/bo/corpus_info.json").read_text(encoding="utf-8"))
SCRIPTS = sorted(p.name for p in (RUN / "_herramientas").iterdir() if p.suffix in (".py", ".sh"))


def wilson(k, n, z=1.96):
    p = k / n
    c = (p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n)
    return max(0.0, c), (p + z * z / (2 * n) + z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n)


def sessions():
    out = []
    for d in SESSIONS:
        c = [r for r in CANON if r["date"] == d]
        out.append({"date": d, "number": META[d]["session_number"],
                    "pages": read("extracted", d).count("---PAGE"),
                    "tagged": read("tagged", d).count("<int "),
                    "rows": len(c), "words": sum(len(r["text"].split()) for r in c)})
    return out


def who(r):
    s = r["speaker_raw"]
    return "chair" if s.startswith("PRESIDENT") else "secretariat" if s.startswith("SECRETARI") else \
        "none" if not s or r["intervention_order"] == "0" else "deputy"


def linkage():
    speech = [r for r in CANON if r["dm_speech"] == "1"]
    by = {}
    for k in ("deputy", "chair", "secretariat"):
        g = [r for r in CANON if who(r) == k]
        by[k] = {"rows": len(g), "linked": sum(1 for r in g if r["id_dep"]),
                 "people": len({r["id_dep"] for r in g if r["id_dep"]})}
    sec_none = Counter(r["date"] for r in CANON if who(r) == "secretariat" and not r["id_dep"])
    return {"rows": len(CANON), "speech": len(speech), "linked": sum(1 for r in speech if r["id_dep"]),
            "gross": round(sum(1 for r in speech if r["id_dep"]) / len(speech), 4), "by_speaker": by,
            "secretariat_without_id": dict(sec_none), "published": INFO["linkage"]["gross"]}


def match():
    table = rows("source/bo/match/matching_table.csv")
    frozen = rows("source/bo/match/matching_table.frozen.csv")
    over = rows("source/bo/match/matching_overrides.csv")
    return {"forms": len(table), "methods": dict(Counter(r["match_method"] for r in table)),
            "frozen": len(frozen), "overrides": len(over)}


def deputies():
    att = rows("source/bo/match/attendance.csv")
    seen = Counter(re.search(r"visto_en:(\d+)", r["notas"])[1] for r in ROSTER)
    speakers = {r["id_dep"] for r in CANON if r["id_dep"]}
    sex = {r["id_dep"]: r["sex"] for r in ROSTER}
    return {"people": len(ROSTER), "seats": 130, "attendance": dict(Counter(r["status"] for r in att)),
            "seen_in_sessions": dict(sorted(seen.items())),
            "speakers": len(speakers), "speakers_with_sex": sum(1 for i in speakers if sex.get(i)),
            "speakers_f": sum(1 for i in speakers if sex.get(i) == "F"),
            "roster_with_sex": sum(1 for r in ROSTER if r["sex"]),
            "sex_source": dict(Counter(r["sex_source"] for r in ROSTER if r["sex_source"]))}


def validation():
    sample = rows("docs/validacion/BO_muestra.csv")
    leak = rows("docs/validacion/calibracion_fuga.csv")
    sec = rows("docs/validacion/calibracion_fuga_secretaria.csv")
    marked = sum(1 for r in leak if r["FUGA"].strip())
    lo, hi = wilson(marked, len(leak))
    return {"sample": len(sample), "verdicts": dict(Counter(r["veredicto"] for r in sample)),
            "not_applicable": sum(1 for r in sample if r["no_aplicable"].strip()),
            "leak_rows": len(leak), "leak_marked": marked, "wilson": [round(lo, 4), round(hi, 4)],
            "leak_by_speaker": dict(Counter("chair" if r["speaker_raw"].startswith("PRESIDENT") else "secretariat"
                                            if r["speaker_raw"].startswith("SECRETARI") else "deputy" for r in leak)),
            "secretariat_recheck": len(sec), "secretariat_marked": sum(1 for r in sec if r["FUGA"].strip()),
            "ci_masked": sum(r["text"].count("[C.I.]") for r in CANON),
            "ci_rows": sum(1 for r in CANON if "[C.I.]" in r["text"]),
            "bullets": INFO["undecodable_text"]["pua"], "bullet_rows": INFO["undecodable_text"]["filas"]}


def state():
    s = {k: v["skills"] for k, v in STATE["sessions"].items()}
    per = {k: {d: [s[d][k]["status"], s[d][k]["confidence"]] for d in SESSIONS} for k in s[SESSIONS[0]]}
    country = {k: [v["status"], v["confidence"]] for k, v in s["_country"].items()}
    return {"sessions": per, "country": country}


# ---------------------------------------------------------------- decisions: ids and links from the log, the summary here
RESUMEN = {
    "bo-0001": ("Muestra de método: 4 sesiones de la Cámara, de marzo y julio de 2024; las sesiones conjuntas, fuera.",
                "Method sample: 4 Chamber sessions, from March and July 2024; joint sessions left out."),
    "bo-0002": ("Los tomos mensuales se cortan en un PDF por sesión por su página de cabecera; preliminares e índice, fuera.",
                "The monthly volumes are cut into one PDF per session at its title page; preliminaries and index left out."),
    "bo-0003": ("El 31 de julio son dos sesiones, la 153.ª y la 154.ª.",
                "31 July holds two sessions, the 153rd and the 154th."),
    "bo-0004": ("La 67.ª se extrae en modo fiel aunque salte el control de fragmentación (55 páginas de tabla del anexo).",
                "The 67th is extracted in faithful mode although the fragmentation gate fires (55 pages of annex table)."),
    "bo-0005": ("Un solo mobiliario, el cabecero corrido, y el reflujo D, con cajas de hasta 6.000 caracteres.",
                "One piece of page furniture, the running head, and reflow D, with boxes of up to 6,000 characters."),
    "bo-0006": ("Se declaran, sin tocar el motor, las 17 palabras que la regla del folio quita en las fronteras de página.",
                "The 17 words that the folio rule drops at page boundaries are declared, without changing the engine."),
    "bo-0007": ("Fecha, número y tipo salen de la carátula; los de la 154.ª, de la fórmula de instalación y de la carátula del tomo de agosto.",
                "Date, number and type come from the cover; for the 154th, from the opening formula and the August volume's cover."),
    "bo-0008": ("En la 76.ª, las 5 marcas «PRESIDENTE:» sueltas son erratas por la presidenta.",
                "In the 76th, the 5 stray «PRESIDENTE:» marks are errata for the presiding woman."),
    "bo-0009": ("El padrón sale de los pases de lista.",
                "The roster comes from the roll calls."),
    "bo-0010": ("Asistencia por sesión: licencia, baja médica y comisión cuentan como ausencia.",
                "Attendance per session: leave, sick leave and committee duty count as absence."),
    "bo-0011": ("party queda vacío, y se declara: el acta no lo da.",
                "party stays empty, and is declared: the record does not give it."),
    "bo-0012": ("Padrón de los cuatro pases de lista, 204 personas; titulares y suplentes sin distinguir.",
                "Roster from the four roll calls, 204 people; titular and substitute members not told apart."),
    "bo-0013": ("Las marcas sin «DIP.» exigen al menos 3 palabras.",
                "Marks without «DIP.» need at least 3 words."),
    "bo-0014": ("La matriz no descarta turnos por su longitud: una interjección de 8 caracteres es habla.",
                "The matrix drops no turn for its length: an 8-character interjection is speech."),
    "bo-0015": ("Las marcas de nivel 1 aceptan «.» como terminador.",
                "Level-1 marks accept «.» as a terminator."),
    "bo-0016": ("Las cédulas de identidad se seudonimizan en el canónico.",
                "Identity-card numbers are pseudonymised in the canonical file."),
    "bo-0017": ("El turno cuya marca nombra a un diputado ausente va, por override, a la diputada aludida.",
                "The turn whose mark names an absent deputy goes, by override, to the deputy alluded to."),
    "bo-0018": ("La mesa se atribuye antes de añadir las carátulas, para esquivar un fallo de attribute_presidency.",
                "The chair is attributed before the covers are added, to sidestep a defect of attribute_presidency."),
    "bo-0019": ("sex sale del vocativo y de la morfología del nombre.",
                "sex comes from the vocative and the given name's morphology."),
    "bo-0020": ("El patrón de nivel 2 exige de 3 a 6 palabras.",
                "The level-2 pattern needs 3 to 6 words."),
    "bo-0021": ("Las cédulas pasan a «[C.I.]» en el canónico.",
                "Identity-card numbers become «[C.I.]» in the canonical file."),
    "bo-0022": ("La secretaría se declara sin id_dep.",
                "The secretariat is declared without id_dep."),
    "bo-0023": ("Las viñetas de uso privado pasan a «•».",
                "The private-use bullets become «•»."),
    "bo-0024": ("sex sale del vocativo, de la nota de relevo y de la morfología, con la cobertura medida por sexo.",
                "sex comes from the vocative, the hand-over note and the morphology, with coverage measured by sex."),
    "bo-0025": ("La secretaría se atribuye por tramos en las 3 sesiones que la nombran.",
                "The secretariat is attributed by segment in the 3 sessions that name it."),
}
# Why each superseded entry was replaced: what was wrong in it (the log's own words are not copied: one quotes a name).
POR_QUE = {
    "bo-0009": ("la evidencia estaba mal redactada", "its evidence was badly worded"),
    "bo-0013": ("su consecuencia describía mal lo que vería verify_tagging", "its consequence misdescribed what verify_tagging would see"),
    "bo-0016": ("contaba 3 filas con cédulas; son 4", "it counted 3 rows with identity numbers; there are 4"),
    "bo-0019": ("decía 35 de 35; son 36 de 36, y faltaba la cobertura por sexo", "it said 35 of 35; it is 36 of 36, and coverage by sex was missing"),
    "bo-0022": ("su evidencia era falsa: la primera marca de la secretaría sí la nombra", "its evidence was false: the secretariat's first mark does name the holder"),
}


def decisions():
    by = {d["id"]: d for d in LOG}
    assert set(by) == set(RESUMEN), "the summaries do not match the decision log"
    later = {d["supersede"]: d["id"] for d in LOG if d.get("supersede")}
    assert set(later) == set(POR_QUE), "the superseded entries do not match POR_QUE"
    assert all(by[k]["estado"] == "superada" for k in later)
    return [{"id": d["id"], "phase": d["fase"], "status": d["estado"], "supersedes": d.get("supersede"),
             "superseded_by": later.get(d["id"]), "es": RESUMEN[d["id"]][0], "en": RESUMEN[d["id"]][1],
             **({"why_es": POR_QUE[d["id"]][0], "why_en": POR_QUE[d["id"]][1]} if d["id"] in later else {})}
            for d in LOG]


# ---------------------------------------------------------------- figures measured during the run that left no file
MEDIDO = {
    "questions": {"log": "§ 2-17", "n": 25},
    "bootstrap": {"log": "§ 3", "chars_per_page": 3340, "marks": {"DIP.": 254, "PRESIDENTE/A": 452, "SECRETARIO/A": 186},
                  "caps_forms": 33, "headings": 30, "bare_names": 2},
    "cut_check": {"log": "§ 2", "march_words": 134048},
    "spellings": {"log": "§ 8", "n": 207, "pairs": 3},
    "validate_first": {"log": "§ 14", "pass": 299, "flag": 1},
    "reflow": {"log": "§ 5", "variants": [["A", 8468, 302], ["B", 3747, 141], ["C", 7, 0], ["D", 2, 0]]},
    "words_lost_at_page_boundaries": {"log": "§ 5", "n": 17},
    "tag_first_pass_67": {"log": "§ 9", "strict": 398, "level2": 5, "headings": 3},
    "embedded_marks_found_by_hand": {"log": "§ 10", "anywhere": 4, "one_passage": 8, "tagged_67_before": 400},
    "match_first_pass": {"log": "§ 11", "linked": 0, "forms": 76},
    "merge_before_secretariat": {"log": "§ 12", "linked": 716, "rows": 902, "confidence": 0.794},
    "gross_over_all_rows": {"log": "§ 16", "pct": 79.1, "right_pct": 79.73},
    "derive_sex_as_shipped": {"log": "§ 13", "speakers_pct": 51, "women_pct": 71},
    "gender_audit": {"log": "§ 13", "agree": 345, "of": 349, "explained": 4},
    "secretariat_vocatives": {"log": "§ 17", "agree": 39, "of": 39, "notes_resolved": 31, "notes_without_id": 8},
    "morph_against_vocative": {"log": "§ 15, § 17", "right": 36, "of": 36, "women": [27, 32], "men": [9, 39]},
}


# ---------------------------------------------------------------- excerpts
def upto(text, end):
    i = text.index(end) + len(end)
    return "\n".join(x.rstrip() for x in text[:i].split("\n"))


def canon(date, order):
    r = next(r for r in CANON if r["date"] == date and r["intervention_order"] == str(order))
    return r


def line(r, text=None):
    return f"{r['speaker_raw']}: {text if text is not None else r['text']}"


def excerpts():
    out = {}
    for stage in ("extracted", "corrected", "tagged"):        # the 76th opens: the same lines in three layers
        out[f"capa_{stage}"] = upto(read(stage, "2024-03-26"), "(Llama lista).")
    m = re.search(r"^PRESIDENTE\. Muchas gracias colega Diputado\. Vamos a ceder la palabra[^\n]*\nDIP\.[^\n]*?\. "
                  r"Muchas gracias Presidente\.", read("corrected", "2024-03-13"), re.M)
    out["punto"] = m[0]                                      # marks closed with a full stop (bo-0015)
    r76, r77 = canon("2024-07-31", 76), canon("2024-07-31", 77)
    note = re.findall(r"-\s*Asume la Presidencia[^-\n]*-", r76["text"])
    assert len(note) == 1
    out["relevo"] = "\n".join([f"DIP. [N]: … {note[0]}", line(r77)])  # the hand-over the defect moved one row
    out["lapsus"] = "\n".join(line(canon("2024-03-13", o)) for o in (222, 223, 224))  # the audit's «slip»
    cfg = (RUN / "country_config/bo.yaml").read_text(encoding="utf-8")   # the speaker marks, as the run left them
    out["config"] = re.search(r"^speaker_tag_patterns:.*?^speaker_loose_pattern:[^\n]*", cfg, re.S | re.M)[0]
    m = META["2024-07-31"]                                    # the chair by segment, without the names
    seg = [{k: s[k] for k in ("via", "genero", "marcas")} for s in m["presidency"]["segments"]]
    head = json.dumps({k: m[k] for k in ("date", "session_number", "session_type", "legislature", "legislative_session")},
                      ensure_ascii=False, indent=1)[:-2]
    out["meta"] = head + f',\n "presidency": {{"scope": "{m["presidency"]["scope"]}", "segments": [\n' + \
        ",\n".join("  " + json.dumps(s, ensure_ascii=False) for s in seg) + "\n ]}\n}"
    return {k: mask(v) for k, v in out.items()}


CONFIG = {"config", "meta"}        # the run's own files, not the record: no vocabulary to check


def walk(x, path="json"):
    if isinstance(x, dict):
        for k, v in x.items():
            walk(v, f"{path}.{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            walk(v, f"{path}[{i}]")
    elif isinstance(x, str):
        guard(x, path)


def check(files):
    """The name guard on built files: roster words with their context, long numbers. Reports; a person decides."""
    hits = 0
    for f in files:
        text = Path(f).read_text(encoding="utf-8")
        for m in re.finditer(W, text):
            if norm(m[0]) in TOKENS and not any(re.search(k, text[max(0, m.start() - 3):m.end() + 12]) for k in KEEP):
                ctx = text[max(0, m.start() - 30):m.end() + 30].replace("\n", " ")
                print(f"{Path(f).name}: roster word «{m[0]}» … {ctx}")
                hits += 1
        for m in re.finditer(r"(?<![\d.,])\d{6,10}(?![\d,])", text):
            print(f"{Path(f).name}: long number {m[0]}")
            hits += 1
    print(f"{hits} to look at in {len(files)} files")


def main():
    if "--check" in sys.argv:
        check(sys.argv[sys.argv.index("--check") + 1:])
        return
    ex = excerpts()
    for k, v in ex.items():
        (guard if k in CONFIG else guard_excerpt)(v, k)
    out = {"run": {"country": "bo", "skills_commit": SKILLS_COMMIT, "scripts": SCRIPTS},
           "sessions": sessions(), "deputies": deputies(), "match": match(), "linkage": linkage(),
           "validation": validation(), "state": state(), "decisions": decisions(), "measured": MEDIDO,
           "excerpts": ex}
    walk({k: v for k, v in out.items() if k != "excerpts"})
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{OUT.name}: {len(out['decisions'])} decisions, {len(ex)} excerpts, {out['linkage']['linked']} of "
          f"{out['linkage']['speech']} speech rows linked")


if __name__ == "__main__":
    main()
