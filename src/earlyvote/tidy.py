"""The one long table every source is reshaped into.

Counts are cumulative as of `days_out` days before Election Day.
`party` is registration, never vote choice: DEM, REP, OTH (unaffiliated and minor
parties), or UNK where the source gives no split. `party_basis` says whether the
split is registration or modeled.
"""

import pandas as pd

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
