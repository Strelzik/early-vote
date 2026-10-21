"""North Carolina voter-level absentee files -> tidy cumulative counts by days out.

One row per ballot in the source, with request and return dates, so the curve for any
past cycle can be rebuilt exactly. Names and addresses are never read.
"""

import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd

from earlyvote import DATA
from earlyvote.elections import GENERALS, General
from earlyvote.fetch import download_if_changed
from earlyvote.tidy import MAX_DAYS_OUT, PROCESSED, cumulate, through, write

RAW = DATA / "raw" / "nc"
BUCKET = "https://s3.amazonaws.com/dl.ncsbe.gov/ENRS"
SOURCE = "ncsbe_absentee"

# 2008 uses older column names for the same fields.
RENAMES = {"ballot_request_type": "ballot_req_type", "request_recvd_dt": "ballot_req_dt"}
FIELDS = ["county_desc", "age", "voter_party_code", "ballot_req_type",
          "ballot_req_dt", "ballot_rtn_dt", "ballot_rtn_status"]
IN_PERSON_TYPES = {"ONE STOP", "ONE-STOP", "EARLY VOTING"}
AGE_BINS = [17, 25, 40, 65, 200]
AGE_LABELS = ["18-25", "26-40", "41-65", "65+"]


def zip_path(g: General) -> Path:
    return RAW / f"absentee_{g.election_day:%Y%m%d}.zip"


def download(g: General) -> bool:
    url = f"{BUCKET}/{g.election_day:%Y_%m_%d}/{zip_path(g).name}"
    return download_if_changed(url, zip_path(g))


def read_ballots(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as z, z.open(z.namelist()[0]) as f:
        df = pd.read_csv(f, dtype=str, encoding="latin-1", keep_default_na=False,
                         usecols=lambda c: c in FIELDS or c in RENAMES)
    return df.rename(columns=RENAMES)[FIELDS]


def parse_dates(s: pd.Series) -> pd.Series:
    s = s.str.strip()
    fmt = "%m/%d/%Y" if s.str.contains("/").any() else "%Y%m%d"
    return pd.to_datetime(s, format=fmt, errors="coerce")


def daily_events(ballots: pd.DataFrame) -> pd.DataFrame:
    """New ballots per (county, party, age_band, mode, date)."""
    in_person = ballots["ballot_req_type"].str.strip().isin(IN_PERSON_TYPES)
    status = ballots["ballot_rtn_status"].str.strip()
    accepted = status.str.startswith("ACCEPTED") | (status == "OK")
    req_dt = parse_dates(ballots["ballot_req_dt"])
    rtn_dt = parse_dates(ballots["ballot_rtn_dt"])
    party = ballots["voter_party_code"].str.strip()

    base = pd.DataFrame({
        "county": ballots["county_desc"].str.strip().str.title(),
        "party": party.where(party.isin(["DEM", "REP"]), "OTH"),
        "age_band": pd.cut(pd.to_numeric(ballots["age"], errors="coerce"), AGE_BINS,
                           labels=AGE_LABELS).astype(str).replace("nan", "unknown"),
    })
    events = {
        "mail_requested": (~in_person, req_dt),
        "mail_returned": (~in_person & accepted, rtn_dt),
        "in_person_early": (in_person & accepted, rtn_dt.fillna(req_dt)),
    }
    parts = [base[mask].assign(mode=mode, date=when[mask]) for mode, (mask, when) in events.items()]
    keys = ["county", "party", "age_band", "mode", "date"]
    return pd.concat(parts).dropna(subset=["date"]).groupby(keys).size().rename("new").reset_index()


def processed_path(g: General) -> Path:
    return PROCESSED / "nc" / f"{g.cycle}.parquet"


def build(g: General) -> Path:
    """Download if changed, then rebuild the cycle's parquet when the zip is newer."""
    download(g)
    src, out = zip_path(g), processed_path(g)
    if out.exists() and out.stat().st_mtime >= src.stat().st_mtime:
        return out
    exported = datetime.fromtimestamp(src.stat().st_mtime).date()
    daily = daily_events(read_ballots(src))
    if exported <= g.election_day:
        # Live files list only mail ballots already returned, so requests would be undercounted.
        daily = daily[daily["mode"] != "mail_requested"]
    return write(cumulate(daily, g, through(g, exported), "NC", SOURCE), out)


def run(cycles: list[int] | None = None) -> list[Path]:
    return [build(GENERALS[c]) for c in cycles or sorted(GENERALS)]


# (earlier general, later general): who among the earlier early voters has voted early in the later one.
REPEAT_PAIRS = [(2024, 2026), (2020, 2022), (2022, 2024), (2018, 2020)]
REPEAT_PATH = PROCESSED / "nc_repeat.parquet"


def early_voters(g: General) -> pd.DataFrame:
    """One row per voter with an accepted early ballot: ncid, party, and the date it was returned."""
    with zipfile.ZipFile(zip_path(g)) as z, z.open(z.namelist()[0]) as f:
        df = pd.read_csv(f, dtype=str, encoding="latin-1", keep_default_na=False,
                         usecols=["ncid", "voter_party_code", "ballot_rtn_status", "ballot_rtn_dt"])
    df = df[df["ballot_rtn_status"].str.strip().str.startswith("ACCEPTED")]
    party = df["voter_party_code"].str.strip()
    df = pd.DataFrame({"ncid": df["ncid"], "party": party.where(party.isin(["DEM", "REP"]), "OTH"),
                       "date": parse_dates(df["ballot_rtn_dt"])})
    return df.sort_values("date").drop_duplicates("ncid")


def repeat_voters() -> Path:
    """Share of each party's early voters in one general who have voted early in the next, by days out.

    Rebuilt only when a source zip is newer than the table.
    """
    cycles = sorted({c for pair in REPEAT_PAIRS for c in pair})
    newest = max(zip_path(GENERALS[c]).stat().st_mtime for c in cycles)
    if REPEAT_PATH.exists() and REPEAT_PATH.stat().st_mtime >= newest:
        return REPEAT_PATH
    voters = {c: early_voters(GENERALS[c]) for c in cycles}
    rows = []
    for before, after in REPEAT_PAIRS:
        g = GENERALS[after]
        prior = voters[before][["ncid", "party"]]
        later = voters[after].set_index("ncid")["date"]
        last = g.days_out(through(g, datetime.fromtimestamp(zip_path(g).stat().st_mtime).date()))
        returned = prior.assign(days_out=(pd.Timestamp(g.election_day) - prior["ncid"].map(later)).dt.days)
        base = prior.groupby("party").size()
        for d in range(MAX_DAYS_OUT, last - 1, -1):
            done = returned[returned["days_out"] >= d].groupby("party").size().reindex(base.index, fill_value=0)
            rows += [(before, after, p, d, done[p] / base[p], int(base[p])) for p in base.index]
    out = pd.DataFrame(rows, columns=["before", "after", "party", "days_out", "rate", "base"])
    return write(out, REPEAT_PATH)
