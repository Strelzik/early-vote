import pandas as pd

from earlyvote import pa


def test_daily_maps_party_codes_modes_and_dates(monkeypatch):
    calls = []

    def fake_counts(dataset, column, has_disposition):
        calls.append((dataset, column, has_disposition))
        return pd.DataFrame({
            "countyname": ["ALLEGHENY", "ALLEGHENY", "ALLEGHENY", "ERIE"],
            "party": ["D", "DEM", "R", "NF"],
            "d": ["2022-10-01T00:00:00.000", "2022-10-01", "2022-10-02", "not a date"],
            "n": ["5", "2", "3", "9"],
        })

    monkeypatch.setattr(pa, "counts", fake_counts)
    out = pa.daily(2022)

    assert calls == [("uhfm-zhus", "appreturndate", False), ("uhfm-zhus", "ballotreturneddate", False)]
    got = {(r.county, r.party, r.mode, str(r.date.date())): r.new for r in out.itertuples()}
    assert got == {
        ("Allegheny", "DEM", "mail_requested", "2022-10-01"): 7,
        ("Allegheny", "REP", "mail_requested", "2022-10-02"): 3,
        ("Allegheny", "DEM", "mail_returned", "2022-10-01"): 7,
        ("Allegheny", "REP", "mail_returned", "2022-10-02"): 3,
    }


def test_declined_applications_filtered_from_2024_and_empty_results_are_fine(monkeypatch):
    seen = {}

    def capture(dataset, column, has_disposition):
        seen[dataset] = has_disposition
        return pd.DataFrame([], columns=["countyname", "party", "d", "n"], dtype=str)

    monkeypatch.setattr(pa, "counts", capture)
    for cycle in (2020, 2024, 2026):
        assert pa.daily(cycle).empty
    assert seen == {"mcba-yywm": False, "3q5t-ddp8": True, "nbwd-pfn4": True}
