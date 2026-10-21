"""Pennsylvania voter-level mail ballot files (data.pa.gov) -> tidy cumulative counts by days out.

Pennsylvania has no in-person early voting, and no-excuse mail began in 2020, so the
series covers mail requested and returned for 2020-2026. The server counts by county,
party, and date, so no voter-level rows are downloaded. These files carry no voter ID,
so repeat voters cannot be tracked across cycles.
"""

from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

from earlyvote.elections import GENERALS, General
from earlyvote.tidy import PROCESSED, cumulate, through, write

SOCRATA = "https://data.pa.gov"
DATASETS = {2020: "mcba-yywm", 2022: "uhfm-zhus", 2024: "3q5t-ddp8", 2026: "nbwd-pfn4"}
DATE_COLUMNS = {"mail_requested": "appreturndate", "mail_returned": "ballotreturneddate"}
# 2020 and 2022 code parties D/R; later files use DEM/REP.
PARTIES = {"D": "DEM", "DEM": "DEM", "R": "REP", "REP": "REP"}
SOURCE = "pa_dos_mail"


def exported(dataset: str) -> datetime:
    meta = requests.get(f"{SOCRATA}/api/views/{dataset}.json", timeout=60).json()
    return datetime.fromtimestamp(meta["rowsUpdatedAt"])


def counts(dataset: str, column: str, has_disposition: bool) -> pd.DataFrame:
    where = f"{column} IS NOT NULL"
    if has_disposition:
        where += " AND (ballot_application_disposition IS NULL OR ballot_application_disposition != 'Declined')"
    r = requests.get(f"{SOCRATA}/resource/{dataset}.json", timeout=600, params={
        "$select": f"countyname, party, {column} AS d, count(*) AS n",
        "$group": "countyname, party, d", "$where": where, "$limit": 2_000_000})
    r.raise_for_status()
    return pd.DataFrame(r.json(), columns=["countyname", "party", "d", "n"], dtype=str)


def daily(cycle: int) -> pd.DataFrame:
    dataset = DATASETS[cycle]
    has_disposition = cycle >= 2024
    parts = []
    for mode, column in DATE_COLUMNS.items():
        df = counts(dataset, column, has_disposition)
        parts.append(pd.DataFrame({
            "county": df["countyname"].str.strip().str.title(),
            "party": df["party"].map(PARTIES).fillna("OTH"),
            "age_band": "all",
            "mode": mode,
            "date": pd.to_datetime(df["d"].str[:10], format="%Y-%m-%d", errors="coerce"),
            "new": df["n"].astype(int),
        }))
    keys = ["county", "party", "age_band", "mode", "date"]
    return pd.concat(parts).dropna(subset=["date"]).groupby(keys, as_index=False)["new"].sum()


def processed_path(g: General) -> Path:
    return PROCESSED / "pa" / f"{g.cycle}.parquet"


def build(g: General) -> Path:
    """Past cycles are frozen ('NO FURTHER UPDATES'), so only rebuild them when missing."""
    out = processed_path(g)
    updated = exported(DATASETS[g.cycle])
    if out.exists() and datetime.fromtimestamp(out.stat().st_mtime) >= updated:
        return out
    return write(cumulate(daily(g.cycle), g, through(g, updated.date()), "PA", SOURCE), out)


def run(cycles: list[int] | None = None) -> list[Path]:
    return [build(GENERALS[c]) for c in cycles or sorted(DATASETS)]
