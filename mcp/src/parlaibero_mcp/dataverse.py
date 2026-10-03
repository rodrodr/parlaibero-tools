"""Read-only client for the Harvard Dataverse API (metadata, citation and file downloads).

Nothing here writes to Dataverse: every call is a GET.
"""
from __future__ import annotations

import hashlib
import html
import os
import re
import time
from pathlib import Path
from typing import Callable

import httpx

from . import __version__

BASE_URL = os.environ.get("PARLAIBERO_DATAVERSE_URL", "https://dataverse.harvard.edu").rstrip("/")
_HEADERS = {"User-Agent": f"parlaibero-mcp/{__version__}"}
_CACHE: dict[str, tuple[float, dict]] = {}
_TTL = 3600.0


def _client(timeout: float = 60.0) -> httpx.Client:
    return httpx.Client(headers=_HEADERS, follow_redirects=True, timeout=timeout)


def dataset(doi: str) -> dict:
    """JSON of the latest published version of a dataset (cached for an hour)."""
    hit = _CACHE.get(doi)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    with _client() as c:
        r = c.get(f"{BASE_URL}/api/datasets/:persistentId/", params={"persistentId": f"doi:{doi}"})
        r.raise_for_status()
        data = r.json()["data"]
    _CACHE[doi] = (time.time(), data)
    return data


def summary(doi: str) -> dict:
    """Title, version, release date, license and file list of a dataset."""
    d = dataset(doi)
    v = d["latestVersion"]
    title = next((f["value"] for f in v["metadataBlocks"]["citation"]["fields"]
                  if f["typeName"] == "title"), "")
    files = []
    for f in v.get("files", []):
        df = f["dataFile"]
        files.append({
            "id": df["id"],
            "filename": df["filename"],
            "size": df.get("filesize"),
            "md5": (df.get("checksum") or {}).get("value") or df.get("md5"),
        })
    return {
        "doi": doi,
        "url": f"https://doi.org/{doi}",
        "title": title,
        "version": f"{v.get('versionNumber')}.{v.get('versionMinorNumber')}",
        "release_time": v.get("releaseTime"),
        "license": (v.get("license") or {}).get("name"),
        "files": files,
    }


def citation(doi: str) -> str:
    with _client() as c:
        r = c.get(f"{BASE_URL}/api/datasets/:persistentId/versions/:latest-published/citation",
                  params={"persistentId": f"doi:{doi}"})
        r.raise_for_status()
        msg = r.json()["data"]["message"]
    return html.unescape(re.sub(r"<[^>]+>", "", msg))


def fetch_text(file_id: int) -> str:
    with _client() as c:
        r = c.get(f"{BASE_URL}/api/access/datafile/{file_id}")
        r.raise_for_status()
        return r.content.decode("utf-8")


def download(file_id: int, dest: Path, md5: str | None = None,
             progress: Callable[[int, int | None], None] | None = None) -> Path:
    """Stream a data file to `dest`, verifying its MD5 against Dataverse before keeping it."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    h = hashlib.md5()
    done = 0
    with _client(timeout=600.0) as c, c.stream("GET", f"{BASE_URL}/api/access/datafile/{file_id}") as r:
        r.raise_for_status()
        total = int(r.headers["Content-Length"]) if "Content-Length" in r.headers else None
        last = 0.0
        with part.open("wb") as out:
            for chunk in r.iter_bytes(chunk_size=1 << 20):
                out.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if progress and time.time() - last > 1.0:
                    progress(done, total)
                    last = time.time()
    if progress:
        progress(done, done)
    if md5 and h.hexdigest() != md5:
        part.unlink(missing_ok=True)
        raise IOError(f"MD5 mismatch downloading file {file_id}: got {h.hexdigest()}, expected {md5}")
    part.replace(dest)
    return dest
