import os
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

_session = requests.Session()
_session.headers["User-Agent"] = "Mozilla/5.0 (earlyvote research script)"


def get(url: str) -> bytes | None:
    """Body of url, or None when the server says it does not exist."""
    r = _session.get(url, timeout=120)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.content


def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    part.write_bytes(data)
    part.replace(path)


def download_if_changed(url: str, dest: Path) -> bool:
    """Stream url to dest unless dest already has the remote's size.

    When the server sends Last-Modified, dest's mtime is set to it, so it records when the source
    exported the file. Returns True if downloaded.
    """
    headers = _session.head(url, timeout=60).headers
    remote_size = int(headers.get("Content-Length", -1))
    modified = headers.get("Last-Modified")
    remote_mtime = parsedate_to_datetime(modified).timestamp() if modified else None
    if dest.exists() and dest.stat().st_size == remote_size:
        if remote_mtime:
            os.utime(dest, (remote_mtime, remote_mtime))
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    with _session.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        with part.open("wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    if remote_mtime:
        os.utime(part, (remote_mtime, remote_mtime))
    part.replace(dest)
    return True
