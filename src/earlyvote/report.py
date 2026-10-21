"""Build reports/earlyvote.html: one self-contained page with the data inlined."""

import json
from datetime import date
from importlib.resources import files
from pathlib import Path

import pandas as pd

from earlyvote import ROOT, eavs, geo, tidy, uf
from earlyvote.elections import GENERALS
from earlyvote.tidy import STATEWIDE

OUT = ROOT / "reports" / "earlyvote.html"
EARLY = ["mail_returned", "in_person_early"]
# County rows: prefer the voter file, then Florida's official feed, then UF.
COUNTY_SOURCES = ["ncsbe_absentee", "fl_dos", "uf_tracker"]


def wide(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Long tidy rows -> one row per key with mode and party columns plus `total` early votes."""
    modes = df.pivot_table(index=keys, columns="mode", values="count", aggfunc="sum", observed=True)
    parties = df[df["mode"].isin(EARLY)].pivot_table(
        index=keys, columns="party", values="count", aggfunc="sum", observed=True)
    out = modes.join(parties, how="left").reindex(
        columns=["mail_requested", *EARLY, "DEM", "REP", "OTH", "UNK"]).fillna(0)
    out["total"] = out[EARLY].sum(axis=1)
    return out.reset_index()


def statewide(df: pd.DataFrame) -> pd.DataFrame:
    """Statewide early vote by state, cycle, days out. NC sums its voter-file counties; others use UF."""
    nc = df[df["source"] == "ncsbe_absentee"]
    others = df[(df["source"] == "uf_tracker") & (df["county"] == STATEWIDE) & (df["state"] != "NC")]
    return wide(pd.concat([nc, others]), ["state", "cycle", "days_out", "as_of"])


def latest_counties(df: pd.DataFrame, cycle: int) -> pd.DataFrame:
    df = df[(df["cycle"] == cycle) & (df["county"] != STATEWIDE)]
    df = df[df["source"].isin(COUNTY_SOURCES)]
    best = df.groupby("state", observed=True)["source"].agg(lambda s: min(s, key=COUNTY_SOURCES.index))
    df = df[df["source"] == df["state"].map(best)]
    df = df[df["days_out"] == df.groupby("state", observed=True)["days_out"].transform("min")]
    return wide(df, ["state", "county", "days_out", "as_of", "source"])


def county_rollup(rows: pd.DataFrame, names: pd.Series) -> pd.DataFrame:
    """Tracker places (towns, cities, counties) summed into counties by their population shares."""
    cols = ["total", "turn2022", "DEM", "REP", "OTH"]
    parts = rows[rows["turn2022"] > 0].explode("parts").dropna(subset=["parts"])
    if parts.empty:
        return pd.DataFrame(columns=["fips5", "name", *cols])
    share = parts["parts"].str[1].astype(float)
    out = parts[cols].mul(share, axis=0).groupby(parts["parts"].str[0].rename("fips5")).sum().reset_index()
    return out.assign(name=out["fips5"].map(names).fillna(out["fips5"]))


def turnout_2022() -> dict[str, dict]:
    fetched, path = uf.snapshots(2026, "US.csv")[-1]
    us = uf.read(path)
    return {r.state_abbv: {"name": r.state, "turn2022": int(r.turn_2022)} for r in us.itertuples()}


def records(df: pd.DataFrame, cols: list[str]) -> list[list]:
    df = df[cols].copy()
    for c in df.select_dtypes("number"):
        df[c] = df[c].round().astype("int64")
    return df.astype(object).to_dict("split")["data"]


def payload() -> dict:
    df = tidy.load()
    finals = eavs.load()
    states = turnout_2022()
    sw = statewide(df)
    counties = latest_counties(df, 2026)

    ev_final = finals.assign(early=finals["early_in_person"].fillna(0) + finals["mail"].fillna(0))
    state_finals = ev_final.groupby(["state", "cycle"])[["total", "early"]].sum()
    places = geo.Geography(finals[finals["cycle"] == 2022])

    nc_counties = df[df["source"] == "ncsbe_absentee"]
    nc_curves = (nc_counties[nc_counties["mode"].isin(EARLY)]
                 .groupby(["county", "cycle", "days_out"], observed=True)["count"].sum().reset_index())

    out = {}
    for st, meta in states.items():
        s = sw[sw["state"] == st]
        cur = s[s["cycle"] == 2026]
        if cur.empty or cur["total"].max() == 0:
            continue
        last = cur.loc[cur["days_out"].idxmin()]
        party_reg = st in tidy.PARTY_REGISTRATION and bool(last[["DEM", "REP"]].sum() > 0)
        cty = counties[counties["state"] == st].reset_index(drop=True)
        cty["county"] = cty["county"].astype(str)
        cty = cty.join(places.place(st, cty["county"]))
        cty["county"] = cty["county"].where(~cty["county"].str.isupper(), cty["county"].str.title())
        out[st] = {
            "name": meta["name"],
            "turn2022": meta["turn2022"],
            "partyReg": party_reg,
            "curveSource": "NC State Board voter file" if st == "NC" else "UF Election Lab snapshots",
            "latest": {k: (str(last[k]) if k == "as_of" else int(last[k]))
                       for k in ["as_of", "days_out", "mail_requested", *EARLY, "DEM", "REP", "OTH", "UNK", "total"]},
            "curves": {int(c): records(g.sort_values("days_out", ascending=False),
                                       ["days_out", "total", "DEM", "REP", "OTH"])
                       for c, g in s.groupby("cycle")},
            "finals": {int(c): {"early": int(r.early), "total": int(r.total)}
                       for (_, c), r in state_finals.loc[[st]].iterrows()} if st in state_finals.index else {},
            "counties": records(cty, ["county", "turn2022", "total", "mail_returned", "in_person_early",
                                      "DEM", "REP", "OTH"]),
            "countyMap": records(county_rollup(cty, places.names), ["fips5", "name", "total", "turn2022",
                                                                    "DEM", "REP", "OTH"]),
            "countySource": cty["source"].iloc[0] if len(cty) else None,
            "countyAsOf": str(cty["as_of"].iloc[0]) if len(cty) else None,
        }
        if st == "NC":
            out[st]["countyCurves"] = {
                county: {int(c): records(gc.sort_values("days_out", ascending=False), ["days_out", "count"])
                         for c, gc in g.groupby("cycle")}
                for county, g in nc_curves.groupby("county", observed=True)
            }
    return {
        "generated": date.today().isoformat(),
        "elections": {c: {"kind": g.kind, "covid": g.covid_outlier, "day": g.election_day.isoformat()}
                      for c, g in GENERALS.items()},
        "states": out,
    }


def build() -> Path:
    template = files("earlyvote").joinpath("report_template.html").read_text(encoding="utf-8")
    html = template.replace("/*__DATA__*/null", json.dumps(payload(), separators=(",", ":")))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    return OUT
