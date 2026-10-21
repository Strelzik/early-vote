"""Place-name matching and county roll-up for EAVS jurisdictions and tracker rows.

EAVS reports counties in most states but towns in New England, municipalities in
Wisconsin, and a few cities on their own (Chicago). Each EAVS jurisdiction is allocated
to counties: by its FIPS code when that names a county, otherwise by the Census
population split of the place or town across counties. Tracker rows are matched to
EAVS jurisdictions by name in increasingly loose steps, then to county names.
"""

import re

import pandas as pd

from earlyvote import DATA
from earlyvote.fetch import download_if_changed
from earlyvote.tidy import county_key

CENSUS = "https://www2.census.gov/programs-surveys/popest/datasets/2020-2024/cities/totals/sub-est2024.csv"
RAW = DATA / "raw" / "geo" / "sub-est2024.csv"

STATE_FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08", "CT": "09", "DE": "10",
    "DC": "11", "FL": "12", "GA": "13", "HI": "15", "ID": "16", "IL": "17", "IN": "18", "IA": "19",
    "KS": "20", "KY": "21", "LA": "22", "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27",
    "MS": "28", "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33", "NJ": "34", "NM": "35",
    "NY": "36", "NC": "37", "ND": "38", "OH": "39", "OK": "40", "OR": "41", "PA": "42", "RI": "44",
    "SC": "45", "SD": "46", "TN": "47", "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53",
    "WV": "54", "WI": "55", "WY": "56",
}
SPELLINGS = [(r"&", " and "), (r"\bsaint\b", "st"), (r"\bsainte\b", "ste"), (r"\bmount\b", "mt"), (r"\bfort\b", "ft"), (r"burgh\b", "burg")]
AFFIXES = r"^(city|town|village|township) of |\s+(town|city|village|township|twp|plt|plantation|\(pt\.?\))$"
# Connecticut's eight pre-2022 counties: Census files now use planning regions, but EAVS 2022
# and the county shapes still use these.
CT_COUNTIES = {
    "09001": "Fairfield County", "09003": "Hartford County", "09005": "Litchfield County",
    "09007": "Middlesex County", "09009": "New Haven County", "09011": "New London County",
    "09013": "Tolland County", "09015": "Windham County",
}


def variants(name: str) -> list[str]:
    """Join keys from strict to loose; a match is accepted only at the first level it is unique."""
    plain = re.sub(r"\s+-\s+.*$", "", str(name).strip().lower())  # WI: "TOWN OF X - Y COUNTY"
    spelled = plain.replace(".", "")
    for pattern, repl in SPELLINGS:
        spelled = re.sub(pattern, repl, spelled)
    bare = spelled
    for _ in range(2):
        bare = re.sub(AFFIXES, "", bare).strip()
    return [county_key(name), county_key(spelled), county_key(bare)]


def census() -> pd.DataFrame:
    download_if_changed(CENSUS, RAW)
    df = pd.read_csv(RAW, dtype=str, encoding="latin-1",
                     usecols=["SUMLEV", "STATE", "COUNTY", "PLACE", "COUSUB", "NAME", "POPESTIMATE2022"])
    return df.assign(pop=pd.to_numeric(df["POPESTIMATE2022"]), fips5=df["STATE"] + df["COUNTY"])


def counties(c: pd.DataFrame) -> pd.DataFrame:
    """fips5, state fips, and county name."""
    ct = pd.DataFrame({"fips5": list(CT_COUNTIES), "STATE": "09", "name": list(CT_COUNTIES.values())})
    current = c.loc[c["SUMLEV"] == "050", ["fips5", "STATE", "NAME"]].rename(columns={"NAME": "name"})
    return pd.concat([current, ct], ignore_index=True)


def splits(c: pd.DataFrame, sumlev: str, code: str) -> pd.DataFrame:
    """Share of each place (157) or county subdivision (061) living in each county."""
    parts = c[c["SUMLEV"] == sumlev].rename(columns={code: "code"})
    parts = parts.assign(share=parts["pop"] / parts.groupby(["STATE", "code"])["pop"].transform("sum"))
    return parts[parts["share"] > 0][["STATE", "code", "fips5", "share", "NAME"]]


def allocate(units: pd.DataFrame) -> pd.DataFrame:
    """EAVS jurisdictions (state, jurisdiction, fips) -> rows of (unit index, fips5, share)."""
    c = census()
    valid = set(counties(c)["fips5"])
    places, cousubs = splits(c, "157", "PLACE"), splits(c, "061", "COUSUB")
    place_names = {(r.STATE, r.code): variants(r.NAME)[2] for r in places.itertuples()}
    place_parts = {k: list(zip(g["fips5"], g["share"])) for k, g in places.groupby(["STATE", "code"])}
    cousub_parts = {k: list(zip(g["fips5"], g["share"])) for k, g in cousubs.groupby(["STATE", "code"])}
    rows = []
    for i, state, jurisdiction, fips in units[["state", "jurisdiction", "fips"]].itertuples():
        st, fips = STATE_FIPS.get(state), str(fips)
        if st is None:
            continue
        if len(fips) == 10 and place_names.get((st, fips[2:7])) == variants(jurisdiction)[2]:
            parts = place_parts[(st, fips[2:7])]
        elif len(fips) == 10 and fips[:5] in valid:
            parts = [(fips[:5], 1.0)]
        elif len(fips) == 5:
            parts = cousub_parts.get((st, fips), [])
        else:
            parts = []
        rows += [(i, f, s) for f, s in parts]
    return pd.DataFrame(rows, columns=["unit", "fips5", "share"])


class Geography:
    """Baseline turnout and county allocation for tracker place names, from one EAVS cycle."""

    def __init__(self, units: pd.DataFrame):
        self.units = units
        self.alloc = allocate(units)
        self.names = counties(census()).set_index("fips5")["name"]
        weighted = self.alloc.join(units["total"], on="unit")
        self.county_turnout = (weighted["total"] * weighted["share"]).groupby(weighted["fips5"]).sum()
        self.parts = self.alloc.groupby("unit")[["fips5", "share"]].apply(lambda g: list(zip(g["fips5"], g["share"])))

    def place(self, state: str, names: pd.Series) -> pd.DataFrame:
        """Per name: 2022 turnout and its (fips5, share) county parts. Unmatched names get turnout 0.

        A list of towns matches only EAVS towns, so the town of Hartford never becomes Hartford
        County. A list of counties tries strict EAVS names first (Illinois reports suburban Cook
        apart from Chicago), then county names, then loose EAVS names ("City of Chicago").
        """
        units = self.units[self.units["state"] == state]
        in_state = self.names[self.names.index.str[:2] == STATE_FIPS.get(state, "")]
        towns = len(names) > 1.5 * len(in_state)
        stages = [("unit", (0, 1, 2, 3))] if towns else [("unit", (0, 1)), ("county", (0, 1, 2)), ("unit", (2, 3))]

        turn = pd.Series(0.0, index=names.index)
        parts: dict = {}
        for kind, levels in stages:
            todo = names[turn == 0]
            hits = match(todo, units["jurisdiction"] if kind == "unit" else in_state, levels).dropna()
            for j, hit in hits.items():
                if kind == "unit":
                    total = units.at[hit, "total"]
                    turn[j], parts[j] = (0 if pd.isna(total) else total), self.parts.get(hit, [])
                else:
                    turn[j], parts[j] = self.county_turnout.get(hit, 0), [(hit, 1.0)]
        return pd.DataFrame({"turn2022": turn, "parts": [parts.get(j, []) for j in names.index]}, index=names.index)


def match(names: pd.Series, candidates: pd.Series, levels: tuple[int, ...] = (0, 1, 2)) -> pd.Series:
    """Index label in `candidates` for each name, or NA. Loose levels skip keys shared by several candidates.

    Level 3 accepts a unique prefix of at least 10 letters, for names EAVS truncated ("SOUTH BURLINGTO").
    """
    out = pd.Series(pd.NA, index=names.index, dtype="object")
    cand = {i: variants(n) for i, n in candidates.items()}
    for level in levels:
        if level == 3:
            for j, name in names[out.isna()].items():
                key = variants(name)[2]
                hits = [i for i, v in cand.items() if min(len(key), len(v[2])) >= 10
                        and (key.startswith(v[2]) or v[2].startswith(key))]
                if len(hits) == 1:
                    out[j] = hits[0]
            continue
        index: dict[str, object] = {}
        for i, v in cand.items():
            index[v[level]] = None if v[level] in index else i
        for j, name in names[out.isna()].items():
            hit = index.get(variants(name)[level])
            if hit is not None:
                out[j] = hit
    return out
