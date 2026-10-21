from datetime import date

import pandas as pd

from earlyvote import nc
from earlyvote.elections import GENERALS

G = GENERALS[2022]  # Election Day 2022-11-08


def ballots(rows):
    cols = ["county_desc", "age", "voter_party_code", "ballot_req_type",
            "ballot_req_dt", "ballot_rtn_dt", "ballot_rtn_status"]
    return pd.DataFrame(rows, columns=cols)


def final_counts(tidy):
    last = tidy[tidy["days_out"] == tidy["days_out"].min()]
    return last.groupby(["mode", "party"])["count"].sum().to_dict()


def test_modes_parties_and_cumulative_grid():
    df = ballots([
        ["WAKE", "30", "DEM", "ONE-STOP", "10/20/2022", "10/20/2022", "ACCEPTED"],
        ["WAKE", "70", "UNA", "EARLY VOTING", "10/21/2022", "10/21/2022", "ACCEPTED"],
        ["WAKE", "50", "REP", "CIVILIAN", "09/01/2022", "10/25/2022", "ACCEPTED - CURED"],
        ["WAKE", "50", "REP", "MAIL", "09/02/2022", "", " "],
        ["WAKE", "50", "LIB", "ONE-STOP", "10/22/2022", "10/22/2022", "CANCELLED"],
        ["WAKE", "50", "REP", "MAIL", "10/01/2022", "12/30/2022", "ACCEPTED"],
    ])
    tidy = nc.cumulate(nc.daily_events(df), G, through=date(2022, 11, 8))

    assert tidy["days_out"].max() == nc.MAX_DAYS_OUT
    assert tidy["days_out"].min() == 0
    assert final_counts(tidy) == {
        ("in_person_early", "DEM"): 1,
        ("in_person_early", "OTH"): 1,
        ("mail_requested", "REP"): 3,
        ("mail_returned", "REP"): 1,
    }
    series = tidy[(tidy["mode"] == "in_person_early") & (tidy["party"] == "DEM")].sort_values("days_out", ascending=False)
    assert series["count"].is_monotonic_increasing
    assert series.loc[series["days_out"] == 20, "count"].item() == 0
    assert series.loc[series["days_out"] == 19, "count"].item() == 1


def test_2008_layout_and_through_cutoff():
    df = ballots([
        ["DURHAM", "40", "DEM", "ONE STOP", "20081020", "20081020", "OK"],
        ["DURHAM", "40", "DEM", "ONE STOP", "20081101", "20081101", "OK"],
    ])
    g = GENERALS[2008]
    tidy = nc.cumulate(nc.daily_events(df), g, through=date(2008, 10, 25))

    assert tidy["days_out"].min() == g.days_out(date(2008, 10, 25))
    assert final_counts(tidy) == {("in_person_early", "DEM"): 1}
    assert set(tidy["age_band"]) == {"26-40"}
