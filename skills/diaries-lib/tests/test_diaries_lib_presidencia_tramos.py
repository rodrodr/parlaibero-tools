"""Presidencia por tramos (attribute_presidency): la carátula desplazaba cada relevo un turno.

cambios() sitúa cada nota de relevo contando las marcas <int de tagged/, y atribuir() contaba también la
fila de la carátula (Prolegomena, orden 0, que añade recover_frontmatter y no tiene marca). Cada tramo
empezaba un turno antes y el turno que contiene la nota pasaba a quien asume: en Bolivia (153.ª, orden 77),
el único turno de la presidenta que asume se iba a quien la releva al final de ese turno.

Estas pruebas fijan:
- la posición de la nota en su turno: si ABRE el turno, el tramo empieza en él; si lo cierra o cae en
  medio, en el siguiente; la vuelta al titular sigue la misma regla;
- que la carátula no cambia nada: con ella y sin ella, la misma atribución;
- sobre una COPIA de la corrida de Bolivia, cuya raíz indica DIARIES_BOLIVIA (sin ella, se salta): con
  carátulas, lo mismo que sin ellas, y el orden 77 de la 153.ª con quien asume, como está publicado.
"""
import json
import os
import shutil
from pathlib import Path

import pandas as pd
import pytest

from lib.utils import attribute_presidency as ap

BO = Path(os.environ.get("DIARIES_BOLIVIA", "/nonexistent"))

P = '<int speaker="SEÑOR PRESIDENTE">'
NOTA, VUELVE = "(Ocupa la Presidencia el señor Dos)", "(Reasume la Presidencia el titular)"
SESIONES = {    # turnos de tagged/ → quién preside cada uno
    "abre":   ([f"{P}Se abre la sesión.</int>", f"{P}{NOTA}\nContinúa la sesión.</int>", f"{P}Se levanta.</int>"],
               ["ZZ1", "ZZ2", "ZZ2"]),
    "cierra": ([f"{P}Se abre la sesión.\n\n{NOTA}</int>", f"{P}Continúa la sesión.</int>", f"{P}Se levanta.</int>"],
               ["ZZ1", "ZZ2", "ZZ2"]),
    "medio":  ([f"{P}Se abre la sesión.\n{NOTA}\nY sigue.</int>", f"{P}Continúa la sesión.</int>",
                f"{P}Se levanta.</int>"],
               ["ZZ1", "ZZ2", "ZZ2"]),
    "vuelta": ([f"{P}Se abre la sesión.\n{NOTA}</int>", f"{P}Continúa la sesión.</int>",
                f"{P} {VUELVE} Se levanta.</int>"],
               ["ZZ1", "ZZ2", "ZZ1"]),
}
CONFIG = r"""presidency:
  scope: segments
  target: [PRESIDENT]
  sources: [{from: meta, field: president}]
  segments:
    from: tagged
    intervention_mark: '<int\s+speaker='
    pattern: '\(\s*Ocupa\s+la\s+Presidencia\s+el\s+señor\s+(\w+)\s*\)'
    back_to_base: '\(\s*Reasume\s+la\s+Presidencia\s+el\s+titular\s*\)'
"""


@pytest.fixture
def zz(tmp_path, monkeypatch):
    (tmp_path / "country_config").mkdir()
    (tmp_path / "country_config" / "zz.yaml").write_text(CONFIG, encoding="utf-8")
    for d in ("meta", "tagged"):
        (tmp_path / "source" / "zz" / d).mkdir(parents=True)
    filas = []
    for n, (sid, (turnos, _)) in enumerate(SESIONES.items(), 1):
        fecha = f"2001-01-0{n}"
        (tmp_path / "source" / "zz" / "meta" / f"{sid}.json").write_text(json.dumps({"date": fecha, "president": "Uno"}))
        # el sumario recapitula el relevo ANTES de la primera marca: no es un relevo
        (tmp_path / "source" / "zz" / "tagged" / f"{sid}.txt").write_text(
            f"Sumario: {NOTA}\n" + "\n".join(turnos), encoding="utf-8")
        filas.append({"date": fecha, "id_session": sid, "intervention_order": "0", "speaker_raw": "PROLEGOMENA", "id_dep": ""})
        filas += [{"date": fecha, "id_session": sid, "intervention_order": str(i), "speaker_raw": "PRESIDENTE", "id_dep": ""}
                  for i in range(1, len(turnos) + 1)]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(ap, "indice", lambda iso2: ({}, {}, {}, {}))
    monkeypatch.setattr(ap, "resolver", lambda nombre, *a, **k: {"Uno": "ZZ1", "Dos": "ZZ2"}.get(nombre.strip()))
    return ap.cargar_config("zz"), pd.DataFrame(filas)


@pytest.mark.parametrize("con_caratula", [True, False], ids=["con_caratula", "sin_caratula"])
@pytest.mark.parametrize("sid", list(SESIONES))
def test_el_tramo_empieza_donde_dice_la_posicion_de_la_nota(zz, sid, con_caratula):
    cfg, df = zz
    d = df if con_caratula else df[df.intervention_order != "0"]
    asign, _, _ = ap.atribuir("zz", cfg, d)
    turnos = d.index[(d.id_session == sid) & (d.intervention_order != "0")]
    assert [asign.get(i) for i in turnos] == SESIONES[sid][1]


@pytest.mark.skipif(not (BO / "source" / "bo" / "standardize" / "BO_interventions.csv").exists(),
                    reason="sin la corrida de Bolivia (DIARIES_BOLIVIA)")
def test_bolivia_la_caratula_no_mueve_la_mesa(tmp_path, monkeypatch):
    p = tmp_path / "bo"
    (p / "country_config").mkdir(parents=True)
    shutil.copy2(BO / "country_config" / "bo.yaml", p / "country_config" / "bo.yaml")
    for d in ("meta", "tagged", "deputies"):
        shutil.copytree(BO / "source" / "bo" / d, p / "source" / "bo" / d)
    monkeypatch.chdir(p)
    df = pd.read_csv(BO / "source" / "bo" / "standardize" / "BO_interventions.csv", dtype=str, keep_default_na=False)
    cfg = ap.cargar_config("bo")
    es = ap.objetivo_presidencia(df, cfg)
    d2 = df.copy()
    d2.loc[es, "id_dep"] = ""                       # como --check: la mesa publicada se borra y se rehace
    con, _, _ = ap.atribuir("bo", cfg, d2)
    sin, _, _ = ap.atribuir("bo", cfg, d2[d2.intervention_order != "0"])
    assert {i: con.get(i) for i in sin} == sin
    r77 = df.index[df.id_int == "BO001000300077"][0]
    assert con.get(r77) == df.at[r77, "id_dep"] == "BO0023"
    assert all(con[i] == df.at[i, "id_dep"] for i in con)
