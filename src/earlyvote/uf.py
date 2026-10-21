"""UF Election Lab snapshots -> tidy rows.

US.csv gives one statewide row per state, dated by its `last_update`. County files carry
no date, so each takes its state's `last_update` from the US.csv snapshot nearest in time.
"""

from bisect import bisect_left
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from earlyvote.elections import GENERALS
from earlyvote.snapshot import SNAPSHOTS
from earlyvote.tidy import PARTY_REGISTRATION, PROCESSED, STATEWIDE, finish, write

MODES = {"request": "mail_requested", "accept": "mail_returned", "inperson": "in_person_early"}
SOURCE = "uf_tracker"
KEYS = ["state", "county", "as_of", "mode", "party"]


def snapshots(cycle: int, name: str) -> list[tuple[datetime, Path]]:
    folder = SNAPSHOTS / f"uf-{cycle}" / name
    if not folder.exists():
        return []
    return sorted((datetime.strptime(p.name[:13], "%Y%m%dT%H%M"), p) for p in folder.iterdir())


def read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")


def by_party(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Wide UF columns -> one row per mode and party. Party split only where the state reports one."""
    parts = []
    for prefix, mode in MODES.items():
        if f"{prefix}_all" not in df:
            continue
        num = {p: pd.to_numeric(df.get(f"{prefix}_{p}", pd.Series(0, index=df.index)), errors="coerce").fillna(0)
               for p in ("all", "dem", "rep")}
        reported = num["all"].gt(0)
        split = reported & (num["dem"] + num["rep"]).gt(0)
        unsplit = reported & ~split
        oth = (num["all"] - num["dem"] - num["rep"]).clip(lower=0)
        for party, counts, mask, basis in (
            ("DEM", num["dem"], split, "registration"),
            ("REP", num["rep"], split, "registration"),
            ("OTH", oth, split, "registration"),
            ("UNK", num["all"], unsplit, "none"),
        ):
            parts.append(df.loc[mask, keys].assign(mode=mode, party=party, party_basis=basis, count=counts[mask]))
    return pd.concat(parts, ignore_index=True)


def statewide(cycle: int) -> tuple[pd.DataFrame, dict[datetime, dict[str, str]]]:
    """Statewide rows, plus each snapshot's last_update per state for dating county files."""
    rows, dates = [], {}
    for fetched, path in snapshots(cycle, "US.csv"):
        df = read(path).drop(columns="state").rename(columns={"state_abbv": "state"})
        dates[fetched] = dict(zip(df["state"], df["last_update"]))
        df = df.assign(county=STATEWIDE, as_of=df["last_update"], fetched=fetched)
        rows.append(by_party(df, ["state", "county", "as_of", "fetched"]))
    return pd.concat(rows, ignore_index=True), dates


def counties(cycle: int, dates: dict[datetime, dict[str, str]]) -> pd.DataFrame:
    stamps = sorted(dates)
    rows = []
    for folder in sorted((SNAPSHOTS / f"uf-{cycle}").glob("*_county.csv")):
        state = folder.name[:2]
        for fetched, path in snapshots(cycle, folder.name):
            i = bisect_left(stamps, fetched)
            nearest = min(stamps[max(i - 1, 0):i + 1], key=lambda s: abs(s - fetched))
            if abs(nearest - fetched).days >= 1 or state not in dates[nearest]:
                continue
            df = read(path)
            numeric = [c for c in df.columns if c.split("_")[0] in MODES]
            # Some states (e.g. TN) list one row per county per day; the counts are daily increments.
            df[numeric] = df[numeric].apply(pd.to_numeric, errors="coerce")
            df = df.groupby("county", as_index=False)[numeric].sum()
            df = df.assign(state=state, as_of=dates[nearest][state], fetched=fetched)
            rows.append(by_party(df, ["state", "county", "as_of", "fetched"]))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def parse_update(s: pd.Series, cycle: int) -> pd.Series:
    """'10/19/2026' or '9-7-2024'. The year is forced to the cycle's, since UF files carry typos like 11/1/2023 in 2024."""
    d = pd.to_datetime(s.str.strip().str.replace("-", "/"), format="%m/%d/%Y", errors="coerce")
    ok = d.notna()
    out = pd.Series(pd.NaT, index=s.index, dtype="object")
    out[ok] = [date(cycle, m, dd) for m, dd in zip(d[ok].dt.month, d[ok].dt.day)]
    return out


def build(cycle: int) -> Path:
    g = GENERALS[cycle]
    states, dates = statewide(cycle)
    df = pd.concat([states, counties(cycle, dates)], ignore_index=True)
    df["as_of"] = parse_update(df["as_of"], cycle)
    df = df.dropna(subset=["as_of"]).sort_values("fetched").drop_duplicates(KEYS, keep="last")
    df = df[df["as_of"] <= g.election_day]
    modeled = (df["party_basis"] == "registration") & ~df["state"].isin(PARTY_REGISTRATION)
    df.loc[modeled, "party_basis"] = "modeled"
    df = df.assign(
        cycle=cycle, election_type=g.kind, covid_outlier=g.covid_outlier,
        days_out=[g.days_out(d) for d in df["as_of"]], age_band="all", source=SOURCE,
    )
    return write(finish(df), PROCESSED / "uf" / f"{cycle}.parquet")


def run(cycles: tuple[int, ...] = (2024, 2026)) -> list[Path]:
    return [build(c) for c in cycles if snapshots(c, "US.csv")]
