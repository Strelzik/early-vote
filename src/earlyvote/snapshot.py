"""Daily copies of sources that overwrite themselves (UF tracker, Florida DOS).

Each file lands at data/raw/snapshots/<source>/<name>/<YYYYmmddTHHMM>_<sha>.<ext>.
A copy is written only when its content differs from every earlier copy.
"""

import csv
import hashlib
import io
import time
from datetime import datetime
from pathlib import Path

from earlyvote import DATA
from earlyvote.fetch import get as _get
from earlyvote.fetch import write_atomic

SNAPSHOTS = DATA / "raw" / "snapshots"

UF_BASE = "https://election.lab.ufl.edu/data-downloads/earlyvote/2026"
FL_BASE = "https://electionfiles.floridados.gov/countyballotreportfiles"
FL_ELECTION_NUMBER = 49894
FL_FILES = ("VbmProvided", "VbmVoted", "EarlyVoted")


def get(url: str) -> bytes | None:
    # Florida's CDN serves stale copies to plain requests about 1 in 6 times; a unique query string bypasses it.
    return _get(f"{url}?t={time.time_ns()}")


def save(source: str, name: str, data: bytes, now: datetime) -> Path | None:
    folder = SNAPSHOTS / source / name
    digest = hashlib.sha256(data).hexdigest()[:12]
    if folder.exists() and any(p.stem.endswith(digest) for p in folder.iterdir()):
        return None
    suffix = Path(name).suffix or ".txt"
    path = folder / f"{now:%Y%m%dT%H%M}_{digest}{suffix}"
    write_atomic(path, data)
    return path


def uf_files() -> dict[str, bytes]:
    national = get(f"{UF_BASE}/US.csv")
    if national is None:
        raise RuntimeError("UF US.csv not found")
    files = {"US.csv": national}
    states = [r["state_abbv"] for r in csv.DictReader(io.StringIO(national.decode("utf-8-sig")))]
    for st in states:
        body = get(f"{UF_BASE}/{st}_county.csv")
        if body is not None:
            files[f"{st}_county.csv"] = body
    return files


def fl_files() -> dict[str, bytes]:
    files = {}
    for kind in FL_FILES:
        name = f"Stats_{FL_ELECTION_NUMBER}_{kind}.txt"
        body = get(f"{FL_BASE}/{name}")
        if body is not None:
            files[name] = body
    return files


def run(now: datetime | None = None) -> list[Path]:
    now = now or datetime.now()
    written = []
    for source, fetch in (("uf", uf_files), ("fl", fl_files)):
        for name, data in fetch().items():
            if path := save(source, name, data, now):
                written.append(path)
    return written
