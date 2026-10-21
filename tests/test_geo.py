import pandas as pd

from earlyvote import geo


def geography(units, county_names, county_turnout, parts):
    g = object.__new__(geo.Geography)
    g.units = units
    g.names = pd.Series(county_names)
    g.county_turnout = pd.Series(county_turnout, dtype=float)
    g.parts = pd.Series(parts, dtype="object")
    return g


def test_towns_match_towns_never_counties():
    units = pd.DataFrame({
        "state": "CT", "jurisdiction": ["HARTFORD TOWN", "ST. ALBANS CITY", "ST. ALBANS TOWN", "SOUTH BURLINGTO"],
        "total": [40, 10, 20, 30],
    }, index=[11, 12, 13, 14])
    g = geography(units, {"09003": "Hartford County"}, {"09003": 999},
                  {11: [("09003", 1.0)], 12: [("09001", 1.0)], 13: [("09001", 1.0)], 14: [("09001", 1.0)]})
    names = pd.Series(["Hartford", "SAINT ALBANS CITY", "SAINT ALBANS TOWN", "South Burlington", "Nowhere"])

    out = g.place("CT", names)

    assert out["turn2022"].tolist() == [40, 10, 20, 30, 0]
    assert out["parts"].iloc[0] == [("09003", 1.0)]


def test_county_lists_prefer_strict_units_then_counties_then_loose_units():
    units = pd.DataFrame({
        "state": "IL", "jurisdiction": ["COOK COUNTY", "CHICAGO CITY", "CITY OF ADAMS - ADAMS COUNTY"],
        "total": [700, 1000, 5],
    }, index=[1, 2, 3])
    g = geography(units, {"17031": "Cook County", "17001": "Adams County"}, {"17031": 1700, "17001": 50},
                  {1: [("17031", 1.0)], 2: [("17031", 1.0)], 3: [("17001", 1.0)]})
    names = pd.Series(["Cook County", "City of Chicago", "ADAMS COUNTY"])

    out = g.place("IL", names)

    assert out["turn2022"].tolist() == [700, 1000, 50]
    assert out["parts"].iloc[2] == [("17001", 1.0)]
