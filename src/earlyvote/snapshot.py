"""Daily copies of sources that overwrite themselves (UF tracker, Florida DOS).

Each file lands at data/raw/snapshots/<source>-<cycle>/<name>/<YYYYmmddTHHMM>_<sha>.<ext>.
A copy is written only when its content differs from every earlier copy.
"""

import csv
import hashlib
import io
import time
from datetime import datetime
from pathlib import Path

import requests

from earlyvote import DATA
from earlyvote.fetch import get as _get
from earlyvote.fetch import write_atomic

SNAPSHOTS = DATA / "raw" / "snapshots"

UF_BASE = "https://election.lab.ufl.edu/data-downloads/earlyvote/2026"
FL_BASE = "https://electionfiles.floridados.gov/countyballotreportfiles"
FL_ELECTION_NUMBER = 49894
FL_FILES = ("VbmProvided", "VbmVoted", "EarlyVoted")
WAYBACK = "https://web.archive.org"


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


def uf_states(national: bytes) -> list[str]:
    return [r["state_abbv"] for r in csv.DictReader(io.StringIO(national.decode("utf-8-sig")))]


def uf_files() -> dict[str, bytes]:
    national = get(f"{UF_BASE}/US.csv")
    if national is None:
        raise RuntimeError("UF US.csv not found")
    files = {"US.csv": national}
    for st in uf_states(national):
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
    for source, fetch in (("uf-2026", uf_files), ("fl-2026", fl_files)):
        for name, data in fetch().items():
            if path := save(source, name, data, now):
                written.append(path)
    return written


def wayback_get(url: str) -> bytes | None:
    """The Archive rate-limits bursts, so pace requests and wait out 429s."""
    for wait in (2, 30, 90, None):
        try:
            time.sleep(2)
            return _get(url)
        except requests.HTTPError as e:
            if e.response.status_code != 429 or wait is None:
                raise
            time.sleep(wait)


def wayback_captures(url: str) -> list[str]:
    cdx = wayback_get(f"{WAYBACK}/cdx/search/cdx?url={url}&fl=timestamp&filter=statuscode:200&collapse=digest")
    return cdx.decode().split() if cdx else []


def backfill(cycles: tuple[int, ...] = (2024, 2026)) -> list[Path]:
    """Add Internet Archive copies of the UF files as snapshots dated by capture time."""
    written = []
    for cycle in cycles:
        base = f"election.lab.ufl.edu/data-downloads/earlyvote/{cycle}"
        names = ["US.csv"] + [f"{st}_county.csv" for st in uf_states(_get(f"https://{base}/US.csv"))]
        for name in names:
            try:
                captures = wayback_captures(f"{base}/{name}")
            except requests.RequestException as e:
                print(f"skip {cycle} {name}: {e}")
                continue
            for ts in captures:
                try:
                    data = wayback_get(f"{WAYBACK}/web/{ts}id_/https://{base}/{name}")
                except requests.RequestException as e:
                    print(f"skip {cycle} {name} {ts}: {e}")
                    continue
                if data and (path := save(f"uf-{cycle}", name, data, datetime.strptime(ts, "%Y%m%d%H%M%S"))):
                    written.append(path)
    return written
