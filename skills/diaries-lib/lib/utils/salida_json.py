"""Salida JSON común de los scripts de métricas de diaries-lib: procedencia y escritura atómica.

La usan vinculacion_efectiva.py (tr-0003) y vinculacion_tr0109.py. Contrato:
- salida 0 correcto, 1 hallazgo de calidad, 2 error de uso o de entorno (ErrorEntorno);
- con --json el error sale en stdout como {"error": ...}; sin --json, en stderr;
- --out se escribe en un temporal del mismo directorio y se sustituye con os.replace, y nunca
  sobre una entrada.
"""
import hashlib
import json
import os
import shlex
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


class ErrorEntorno(Exception):
    """La cifra no se puede calcular: falta un fichero, una columna o las filas (salida 2)."""


def sha256(ruta) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as fh:
        for bloque in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def procedencia(script) -> dict:
    """Qué script produjo la cifra, en qué versión, cuándo (UTC), con qué orden y desde dónde."""
    script = Path(script).resolve()
    return {"script": str(script), "script_sha256": sha256(script),
            "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "comando": shlex.join([script.name, *sys.argv[1:]]),
            "directorio": os.getcwd()}


def comprueba_destino(destino, entradas) -> Path:
    """Devuelve la ruta de --out, o lanza ErrorEntorno si es (o apunta a) una de las entradas."""
    d = Path(destino)
    for e in map(Path, entradas):
        mismo = d.absolute() == e.absolute() or d.resolve() == e.resolve()
        if not mismo and d.exists() and e.exists():
            mismo = os.path.samefile(d, e)
        if mismo:
            raise ErrorEntorno(f"--out {destino} es una entrada ({e}): nunca se escribe sobre una entrada")
    return d


def escribe_atomico(destino, datos: dict) -> None:
    """JSON a un temporal del mismo directorio y os.replace: nadie ve nunca un fichero a medias."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=destino.parent, prefix=f".{destino.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(datos, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, destino)
    except BaseException:
        if os.path.exists(tmp):          # solo el temporal propio; el destino queda como estaba
            os.unlink(tmp)
        raise


def sale_con_error(mensaje: str, como_json: bool) -> int:
    if como_json:
        print(json.dumps({"error": mensaje}, ensure_ascii=False))
    else:
        print(f"ERROR: {mensaje}", file=sys.stderr)
    return 2
