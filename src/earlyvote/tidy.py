"""The one long table every source is reshaped into.

Counts are cumulative as of `days_out` days before Election Day.
`county` is "ALL" on statewide rows, which must never be summed with county rows.
`party` is registration, never vote choice: DEM, REP, OTH (unaffiliated and minor
parties), or UNK where the source gives no split. `party_basis` says whether the
split is registration or modeled.
"""

import re
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from earlyvote import DATA
from earlyvote.elections import General

PROCESSED = DATA / "processed"
MAX_DAYS_OUT = 120
MIN_DAYS_OUT = -14
STATEWIDE = "ALL"
# States (and DC) where voters register by party. A party split anywhere else is modeled.
PARTY_REGISTRATION = {
    "AK", "AZ", "CA", "CO", "CT", "DC", "DE", "FL", "IA", "ID", "KS", "KY", "LA", "MA", "MD", "ME",
    "NC", "NE", "NH", "NJ", "NM", "NV", "NY", "OK", "OR", "PA", "RI", "SD", "UT", "WV", "WY",
}
LABELS = ["state", "county", "election_type", "mode", "party", "party_basis", "age_band", "source"]
COLUMNS = [
    "state", "county", "cycle", "election_type", "covid_outlier", "days_out",
    "as_of", "mode", "party", "party_basis", "age_band", "count", "source",
]
MODES = {"mail_requested", "mail_returned", "in_person_early"}
PARTIES = {"DEM", "REP", "OTH", "UNK"}
PARTY_BASES = {"registration", "modeled", "none"}
AGE_BANDS = {"18-25", "26-40", "41-65", "65+", "unknown", "all"}


def validate(df: pd.DataFrame) -> pd.DataFrame:
    if list(df.columns) != COLUMNS:
        raise ValueError(f"columns {list(df.columns)} != {COLUMNS}")
    for col, allowed in (("mode", MODES), ("party", PARTIES),
                         ("party_basis", PARTY_BASES), ("age_band", AGE_BANDS)):
        bad = set(df[col].unique()) - allowed
        if bad:
            raise ValueError(f"{col} has unexpected values {bad}")
    if (df["count"] < 0).any():
        raise ValueError("negative counts")
    return df


def through(g: General, exported: date) -> date:
    """Last complete day in a source exported on `exported`: the day before, at most two weeks past Election Day."""
    return min(g.election_day + timedelta(days=-MIN_DAYS_OUT), exported - timedelta(days=1))


def cumulate(daily: pd.DataFrame, g: General, last_day: date, state: str, source: str) -> pd.DataFrame:
    """Daily new counts (county, party, age_band, mode, date, new) -> tidy cumulative counts
    at every days-out from MAX_DAYS_OUT down to `last_day`. Earlier dates count at MAX_DAYS_OUT."""
    last = g.days_out(last_day)
    days_out = (pd.Timestamp(g.election_day) - daily["date"]).dt.days
    daily = daily.assign(days_out=days_out.clip(upper=MAX_DAYS_OUT))

    keys = ["county", "party", "age_band", "mode"]
    wide = daily.pivot_table(index=keys, columns="days_out", values="new", aggfunc="sum", fill_value=0)
    wide = wide.reindex(columns=range(MAX_DAYS_OUT, last - 1, -1), fill_value=0).cumsum(axis=1)
    out = wide.stack().rename("count").reset_index()
    out = out.assign(
        state=state, cycle=g.cycle, election_type=g.kind, covid_outlier=g.covid_outlier,
        as_of=(pd.Timestamp(g.election_day) - pd.to_timedelta(out["days_out"], unit="D")).dt.date,
        party_basis="registration", source=source,
    )
    return finish(out)


def finish(df: pd.DataFrame) -> pd.DataFrame:
    """Order columns, set dtypes, and validate a source's rows."""
    df = df[COLUMNS].astype({c: "category" for c in LABELS} | {"count": "int64", "cycle": "int64", "days_out": "int64"})
    return validate(df)


def write(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    df.to_parquet(part, index=False)
    part.replace(path)
    return path


def load(sources: tuple[str, ...] = ("nc", "pa", "uf", "fl")) -> pd.DataFrame:
    frames = [pd.read_parquet(p) for s in sources for p in sorted((PROCESSED / s).glob("*.parquet"))]
    return pd.concat(frames, ignore_index=True).astype({c: "category" for c in LABELS})


def county_key(name: str) -> str:
    """Join key across sources: 'DeSoto County' and 'DESOTO' both become 'desoto'."""
    name = re.sub(r"\s+(county|parish|borough|census area|city and borough)$", "", name.strip().lower())
    return re.sub(r"[^a-z0-9]", "", name)
