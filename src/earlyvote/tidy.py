"""The one long table every source is reshaped into.

Counts are cumulative as of `days_out` days before Election Day.
`county` is "ALL" on statewide rows, which must never be summed with county rows.
`party` is registration, never vote choice: DEM, REP, OTH (unaffiliated and minor
parties), or UNK where the source gives no split. `party_basis` says whether the
split is registration or modeled.
"""

import re
from pathlib import Path

import pandas as pd

from earlyvote import DATA

PROCESSED = DATA / "processed"
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


def load(sources: tuple[str, ...] = ("nc", "uf", "fl")) -> pd.DataFrame:
    frames = [pd.read_parquet(p) for s in sources for p in sorted((PROCESSED / s).glob("*.parquet"))]
    return pd.concat(frames, ignore_index=True).astype({c: "category" for c in LABELS})


def county_key(name: str) -> str:
    """Join key across sources: 'DeSoto County' and 'DESOTO' both become 'desoto'."""
    name = re.sub(r"\s+(county|parish|borough|census area|city and borough)$", "", name.strip().lower())
    return re.sub(r"[^a-z0-9]", "", name)
