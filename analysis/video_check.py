"""Check early-vote claims from the Oct 2026 Cohen/Morris video against official data.

Run: .venv/Scripts/python analysis/video_check.py
"""

import io
import zipfile
from datetime import timedelta

import pandas as pd
import requests

from earlyvote import eavs, geo, nc, tidy
from earlyvote.elections import GENERALS

PRES_2024 = ("https://raw.githubusercontent.com/tonmcg/US_County_Level_Election_Results_08-24/"
             "master/2024_US_County_Level_Presidential_Results.csv")
PA_DATASETS = {2022: "uhfm-zhus", 2024: "3q5t-ddp8", 2026: "nbwd-pfn4"}
EARLY = ["mail_returned", "in_person_early"]


def margin(dem: float, rep: float, total: float) -> str:
    return f"D {100 * dem / total:4.1f}%  R {100 * rep / total:4.1f}%  D-R {100 * (dem - rep) / total:+5.1f}"


def virginia_geography() -> None:
    """Virginia has no party registration, so weight each locality's early vote by its 2024 Harris share."""
    pres = pd.read_csv(io.StringIO(requests.get(PRES_2024, timeout=60).text), dtype={"county_fips": str})
    pres = pres[pres["state_name"] == "Virginia"]
    harris = (pres.set_index(pres["county_fips"].str.zfill(5))
              .eval("votes_dem / (votes_dem + votes_gop)").rename("harris"))

    finals = eavs.load()
    places = geo.Geography(finals[finals["cycle"] == 2022])
    uf = tidy.load(("uf",))
    va = uf[(uf["state"] == "VA") & (uf["cycle"] == 2026) & (uf["county"] != tidy.STATEWIDE) & uf["mode"].isin(EARLY)]
    va = va[va["as_of"] == va["as_of"].max()]
    cur = va.groupby("county", observed=True)["count"].sum()
    cur = cur.to_frame("early").join(places.place("VA", cur.index.to_series()))
    cur = cur.explode("parts").dropna(subset=["parts"])
    cur = (cur["early"] * cur["parts"].str[1]).groupby(cur["parts"].str[0]).sum()

    rows = {f"2026 early, through {va['as_of'].max()}": cur}
    for cycle in (2022, 2024):
        f = finals[(finals["state"] == "VA") & (finals["cycle"] == cycle)]
        fips5 = f["fips"].str[:5]
        rows[f"{cycle} final early"] = (f["early_in_person"].fillna(0) + f["mail"].fillna(0)).groupby(fips5).sum()
        rows[f"{cycle} all voters"] = f["total"].groupby(fips5).sum()

    print("\nVirginia: early electorate weighted by each locality's 2024 Harris two-party share")
    for label, votes in rows.items():
        j = votes.to_frame("v").join(harris, how="inner")
        print(f"  {label:32} {100 * (j.v * j.harris).sum() / j.v.sum():5.1f}% Harris-weighted"
              f"  ({100 * j.v.sum() / votes.sum():.0f}% of votes matched)")


def nc_margins() -> None:
    d = pd.concat([pd.read_parquet(nc.processed_path(GENERALS[c])) for c in (2018, 2022, 2024, 2026)])
    d = d[d["mode"].isin(EARLY)]
    days = int(d.loc[d["cycle"] == 2026, "days_out"].min())
    print(f"\nNorth Carolina: early voters by party registration at {days} days out (voter file)")
    for c, g in d[d["days_out"] == days].groupby("cycle"):
        p = g.groupby("party", observed=True)["count"].sum()
        print(f"  {c}  {int(p.sum()):>9,}  {margin(p['DEM'], p['REP'], p.sum())}")


def nc_repeat_voters(days: int) -> None:
    """Of each party's early voters in an earlier general, the share who voted early in the later one by `days` out."""
    def voters(cycle: int, through_days: int | None = None) -> pd.DataFrame:
        with zipfile.ZipFile(nc.zip_path(GENERALS[cycle])) as z, z.open(z.namelist()[0]) as f:
            df = pd.read_csv(f, dtype=str, encoding="latin-1", keep_default_na=False,
                             usecols=["ncid", "voter_party_code", "ballot_rtn_status", "ballot_rtn_dt"])
        df = df[df["ballot_rtn_status"].str.strip().str.startswith("ACCEPTED")]
        if through_days is not None:
            cutoff = GENERALS[cycle].election_day - timedelta(days=through_days)
            df = df[nc.parse_dates(df["ballot_rtn_dt"]).dt.date <= cutoff]
        return df.drop_duplicates("ncid")

    print(f"\nNorth Carolina: share of an earlier cycle's early voters who already voted early, at {days} days out")
    for before, after in ((2024, 2026), (2022, 2026), (2020, 2022), (2018, 2022)):
        prior, later = voters(before), voters(after, days)
        prior = prior.assign(again=prior["ncid"].isin(later["ncid"]))
        party = prior["voter_party_code"].where(prior["voter_party_code"].isin(["DEM", "REP"]), "OTH")
        rates = prior.groupby(party)["again"].mean()
        print(f"  {before} early voters -> {after}:  D {100 * rates['DEM']:4.1f}%  R {100 * rates['REP']:4.1f}%"
              f"  Other {100 * rates['OTH']:4.1f}%")


def pa_margins(days: int) -> None:
    """Pennsylvania mail ballots returned by party, same days out (PA has no in-person early voting)."""
    print(f"\nPennsylvania: mail ballots returned by party at {days} days out (data.pa.gov voter-level files)")
    for cycle, dataset in PA_DATASETS.items():
        cutoff = GENERALS[cycle].election_day - timedelta(days=days)
        r = requests.get(f"https://data.pa.gov/resource/{dataset}.json", timeout=120, params={
            "$select": "party, count(*) AS n", "$group": "party",
            "$where": f"ballotreturneddate <= '{cutoff}T23:59:59'"})
        p = pd.DataFrame(r.json()).astype({"n": int})
        # 2022 codes parties D/R; later files use DEM/REP.
        p = p.groupby(p["party"].replace({"D": "DEM", "R": "REP"}))["n"].sum()
        print(f"  {cycle}  {int(p.sum()):>9,}  {margin(p.get('DEM', 0), p.get('REP', 0), p.sum())}")


if __name__ == "__main__":
    virginia_geography()
    nc_margins()
    pa_margins(days=15)
    nc_repeat_voters(days=15)
