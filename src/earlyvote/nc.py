"""North Carolina voter-level absentee files -> tidy cumulative counts by days out.

One row per ballot in the source, with request and return dates, so the curve for any
past cycle can be rebuilt exactly. Names and addresses are never read.
"""

import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from earlyvote import DATA
from earlyvote.elections import GENERALS, General
from earlyvote.fetch import download_if_changed
from earlyvote.tidy import COLUMNS, validate

RAW = DATA / "raw" / "nc"
PROCESSED = DATA / "processed" / "nc"
BUCKET = "https://s3.amazonaws.com/dl.ncsbe.gov/ENRS"

MAX_DAYS_OUT = 120
MIN_DAYS_OUT = -14

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


def cumulate(daily: pd.DataFrame, g: General, through: date) -> pd.DataFrame:
    """Daily new counts -> cumulative count at every days-out from MAX_DAYS_OUT down to `through`."""
    last = g.days_out(through)
    days_out = (pd.Timestamp(g.election_day) - daily["date"]).dt.days
    daily = daily.assign(days_out=days_out.clip(upper=MAX_DAYS_OUT))

    keys = ["county", "party", "age_band", "mode"]
    wide = daily.pivot_table(index=keys, columns="days_out", values="new", aggfunc="sum", fill_value=0)
    wide = wide.reindex(columns=range(MAX_DAYS_OUT, last - 1, -1), fill_value=0).cumsum(axis=1)
    out = wide.stack().rename("count").reset_index()
    out = out.assign(
        state="NC", cycle=g.cycle, election_type=g.kind, covid_outlier=g.covid_outlier,
        as_of=(pd.Timestamp(g.election_day) - pd.to_timedelta(out["days_out"], unit="D")).dt.date,
        party_basis="registration", source="ncsbe_absentee",
    )
    out["count"] = out["count"].astype("int64")
    labels = ["state", "county", "election_type", "mode", "party", "party_basis", "age_band", "source"]
    return validate(out[COLUMNS].astype({c: "category" for c in labels}))


def processed_path(g: General) -> Path:
    return PROCESSED / f"{g.cycle}.parquet"


def build(g: General) -> Path:
    """Download if changed, then rebuild the cycle's parquet when the zip is newer."""
    download(g)
    src, out = zip_path(g), processed_path(g)
    if out.exists() and out.stat().st_mtime >= src.stat().st_mtime:
        return out
    exported = datetime.fromtimestamp(src.stat().st_mtime).date()
    through = min(g.election_day + timedelta(days=-MIN_DAYS_OUT), exported - timedelta(days=1))
    daily = daily_events(read_ballots(src))
    if exported <= g.election_day:
        # Live files list only mail ballots already returned, so requests would be undercounted.
        daily = daily[daily["mode"] != "mail_requested"]
    tidy = cumulate(daily, g, through)
    out.parent.mkdir(parents=True, exist_ok=True)
    part = out.with_name(out.name + ".part")
    tidy.to_parquet(part, index=False)
    part.replace(out)
    return out


def load() -> pd.DataFrame:
    return pd.read_parquet(PROCESSED)


def run(cycles: list[int] | None = None) -> list[Path]:
    return [build(GENERALS[c]) for c in cycles or sorted(GENERALS)]
