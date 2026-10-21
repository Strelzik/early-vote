"""EAC Election Administration and Voting Survey -> final turnout by mode per jurisdiction.

Kept apart from the tidy table: these are end-of-election totals with no dates, used as
baselines and denominators. Jurisdictions are counties in most states and towns in
New England, Michigan, and Wisconsin.
"""

import zipfile
from pathlib import Path

import pandas as pd

from earlyvote import DATA
from earlyvote.elections import GENERALS
from earlyvote.fetch import download_if_changed
from earlyvote.tidy import PROCESSED, write

RAW = DATA / "raw" / "eavs"
EAC = "https://www.eac.gov/sites/default/files"
FILES = {
    2014: "eac_assets/1/1/2014_EAVS_Excel_Files1.zip",
    2016: "2023-12/EAVS_2016_for_Public_Release_nolabel_V1.1_CSV.zip",
    2018: "2019-10/EAVS_2018_for_Public_Release_nolabel%20v1.1.csv",
    2020: "2023-12/2020_EAVS_for_Public_Release_nolabel_V1.2_CSV.zip",
    2022: "2023-06/2022_EAVS_for_Public_Release_nolabel_V1_CSV.zip",
    2024: "2026-02/2024_EAVS_for_Public_Release_nolabel_V2_csv.zip",
}
# Section F1 items, stable from 2014 (with a Q prefix that year) through 2024.
ITEMS = {"F1a": "total", "F1b": "election_day", "F1c": "uocava", "F1d": "mail",
         "F1e": "provisional", "F1f": "early_in_person", "F1g": "mail_all_mail_jurisdiction"}
IDS = {"FIPSCode": "fips", "State_Abbr": "state", "State": "state",
       "Jurisdiction_Name": "jurisdiction", "JurisdictionName": "jurisdiction", "Jurisdiction": "jurisdiction"}
COLUMNS = ["state", "fips", "jurisdiction", "county", "cycle", "election_type", "covid_outlier",
           "total", "election_day", "early_in_person", "mail", "uocava", "provisional"]


def raw_path(cycle: int) -> Path:
    return RAW / f"eavs_{cycle}{Path(FILES[cycle]).suffix}"


def read(cycle: int) -> pd.DataFrame:
    path = raw_path(cycle)
    if cycle == 2014:
        with zipfile.ZipFile(path) as z, z.open("EAVS_Section_F.xlsx") as f:
            df = pd.read_excel(f, dtype=str)
        df.columns = [c[1:] if c.startswith("QF1") else c for c in df.columns]
    else:
        df = pd.read_csv(path, dtype=str, encoding="latin-1")
    if "State_Abbr" in df:
        df = df.drop(columns="State", errors="ignore")
    return df.rename(columns=IDS | ITEMS)[list(dict.fromkeys(IDS.values())) + list(ITEMS.values())]


def finals(cycle: int) -> pd.DataFrame:
    g = GENERALS[cycle]
    df = read(cycle)
    counts = list(ITEMS.values())
    # Negative values are EAVS missing-data codes (-999999 not provided, -888888 not applicable).
    df[counts] = df[counts].apply(pd.to_numeric, errors="coerce").where(lambda x: x >= 0).astype("Int64")
    df["mail"] = df["mail"].add(df.pop("mail_all_mail_jurisdiction"), fill_value=0)
    return df.assign(
        county=df["jurisdiction"].str.strip().str.title(),
        cycle=cycle, election_type=g.kind, covid_outlier=g.covid_outlier,
    )[COLUMNS]


def run(cycles: list[int] | None = None) -> Path:
    cycles = cycles or sorted(FILES)
    for c in cycles:
        download_if_changed(f"{EAC}/{FILES[c]}", raw_path(c))
    return write(pd.concat([finals(c) for c in cycles], ignore_index=True), PROCESSED / "eavs.parquet")


def load() -> pd.DataFrame:
    return pd.read_parquet(PROCESSED / "eavs.parquet")
