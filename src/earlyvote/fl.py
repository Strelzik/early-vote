"""Florida Division of Elections daily county files -> tidy rows.

Each county row carries the time it was compiled; the counts run through the prior day.
"Provided (not yet returned)" plus returned gives mail ballots requested.
"""

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from earlyvote.elections import GENERALS
from earlyvote.snapshot import FL_ELECTION_NUMBER, FL_FILES, SNAPSHOTS
from earlyvote.tidy import PROCESSED, finish, write

CYCLE = 2026
KINDS = dict(zip(FL_FILES, ("outstanding", "mail_returned", "in_person_early")))
SOURCE = "fl_dos"


def read(kind: str) -> pd.DataFrame:
    rows = []
    folder = SNAPSHOTS / f"fl-{CYCLE}" / f"Stats_{FL_ELECTION_NUMBER}_{kind}.txt"
    for path in sorted(folder.iterdir()):
        df = pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False)
        compiled = pd.to_datetime(df["CompileDate"].str.split().str[0], format="%m/%d/%Y", errors="coerce")
        keep = compiled.notna() & (df["CountyName"] != "State Totals")
        df, compiled = df[keep], compiled[keep]
        n = {c: pd.to_numeric(df[c].str.replace(",", ""), errors="coerce").fillna(0)
             for c in ("TotalDem", "TotalRep", "TotalOth", "TotalNpa")}
        base = pd.DataFrame({
            "county": df["CountyName"], "mode": KINDS[kind],
            "as_of": (compiled - timedelta(days=1)).dt.date,
            "fetched": datetime.strptime(path.name[:13], "%Y%m%dT%H%M"),
        })
        for party, counts in (("DEM", n["TotalDem"]), ("REP", n["TotalRep"]), ("OTH", n["TotalOth"] + n["TotalNpa"])):
            rows.append(base.assign(party=party, count=counts))
    return pd.concat(rows, ignore_index=True)


def build() -> Path:
    g = GENERALS[CYCLE]
    keys = ["county", "as_of", "party"]
    df = pd.concat([read(k) for k in FL_FILES], ignore_index=True)
    df = df.sort_values("fetched").drop_duplicates(keys + ["mode"], keep="last")

    returned = df[df["mode"] == "mail_returned"]
    outstanding = df[df["mode"] == "outstanding"]
    requested = outstanding.merge(returned[keys + ["count"]], on=keys, suffixes=("", "_ret"))
    requested = requested.assign(mode="mail_requested", count=requested["count"] + requested["count_ret"])
    df = pd.concat([df[df["mode"] != "outstanding"], requested[df.columns]], ignore_index=True)

    df = df.assign(
        state="FL", cycle=CYCLE, election_type=g.kind, covid_outlier=g.covid_outlier,
        days_out=[g.days_out(d) for d in df["as_of"]], party_basis="registration",
        age_band="all", source=SOURCE,
    )
    return write(finish(df), PROCESSED / "fl" / f"{CYCLE}.parquet")
