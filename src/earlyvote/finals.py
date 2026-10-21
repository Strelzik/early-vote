"""Final early vote by party for past generals, from three kinds of sources.

- registration: McDonald's 2014-2018 Google Sheets and the UF 2020/2022 state pages give
  early voters by party registration as of the last days before the election.
- vote_choice: MEDSL precinct returns give votes for each party's candidates split by
  vote mode, in states that report the split. Top of ticket: President, else US House.

One row per state, cycle, and source: DEM, REP, OTH, total.
"""

import csv
import html
import io
import re
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd

from earlyvote import DATA, eavs
from earlyvote.elections import GENERALS
from earlyvote.fetch import download_if_changed, get, write_atomic
from earlyvote.tidy import PARTY_REGISTRATION, PROCESSED, write

RAW = DATA / "raw" / "medsl"
CACHE = DATA / "raw" / "finals"
OUT = PROCESSED / "finals_party.parquet"
COLUMNS = ["state", "cycle", "source", "basis", "as_of", "DEM", "REP", "OTH", "total"]

MCDONALD_SHEETS = {
    2014: "1oCBdr7Mu_PzF454sbZDmIpYMlehTzISDLNxeJKOTGtA",
    2016: "1fz_V3oAUL8XJMEudq5wm5hDT_f554uagt6sIm_sJDro",
    2018: "1OgRzmhXLW6YEHQdhQkpSES3lbsVbRLkz2ZCv2Jh5tf0",
}
UF_2022_INDEX = "https://rpubs.com/ElectProject/early_vote_2022"
UF_2020_PAGE = "https://electproject.github.io/Early-Vote-2020G/{st}.html"
STATE_NAMES = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA", "Colorado": "CO",
    "Connecticut": "CT", "Delaware": "DE", "District of Columbia": "DC", "Florida": "FL", "Georgia": "GA",
    "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA",
    "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS", "Missouri": "MO", "Montana": "MT",
    "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM",
    "New York": "NY", "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD",
    "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}


def cached(name: str, url: str) -> str | None:
    """These sources are frozen, so each is fetched once."""
    path = CACHE / name
    if not path.exists():
        body = get(url)
        if body is None:
            return None
        write_atomic(path, body)
    return path.read_bytes().decode("utf-8", errors="ignore")


def number(s) -> float:
    s = str(s).replace(",", "").replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return float("nan")


def month_day(cycle: int, s: str) -> str | None:
    m = re.match(r"(\d{1,2})/(\d{1,2})", str(s).strip())
    return date(cycle, int(m[1]), int(m[2])).isoformat() if m else None


def mcdonald(cycle: int) -> pd.DataFrame:
    text = cached(f"mcdonald_{cycle}.csv",
                  f"https://docs.google.com/spreadsheets/d/{MCDONALD_SHEETS[cycle]}/export?format=csv")
    rows = list(csv.reader(io.StringIO(text)))
    out = []
    if cycle == 2014:
        # Each state row holds the total; the rows beneath carry party percentages of returned ballots.
        for i, row in enumerate(rows):
            st = STATE_NAMES.get(row[0].strip())
            if not st or row[3].strip() != "Party":
                continue
            total = number(row[2])
            pcts = {}
            for below in rows[i + 1:i + 5]:
                label = below[3].strip().lower()
                if label in ("dem", "rep", "none/other", "other", "ind"):
                    pcts[label] = number(below[4]) / 100
            dem, rep = pcts.get("dem", 0) * total, pcts.get("rep", 0) * total
            out.append((st, cycle, "mcdonald_sheet", "registration", month_day(cycle, row[15]),
                        dem, rep, total - dem - rep, total))
    else:
        header = next(i for i, r in enumerate(rows) if r and r[0] == "State")
        cols = rows[header]
        at = {name: cols.index(name) for name in ("Dem", "Rep", "Other", "Ind", "Party total", "As of")}
        for r in rows[header + 1:]:
            if not re.fullmatch(r"[A-Z]{2}", r[0].strip()) or not r[at["Dem"]].strip():
                continue
            dem, rep = number(r[at["Dem"]]), number(r[at["Rep"]])
            other = sum(v for v in (number(r[at["Other"]]), number(r[at["Ind"]])) if v == v)
            total = number(r[at["Party total"]])
            total = total if total == total else dem + rep + other
            out.append((r[0].strip(), cycle, "mcdonald_sheet", "registration", month_day(cycle, r[at["As of"]]),
                        dem, rep, total - dem - rep, total))
    return pd.DataFrame(out, columns=COLUMNS)


SECTIONS = {  # which party table a heading introduces, judged by heading text and count column
    "total": lambda h, col: h.startswith("Total Voted") and col == "Count",
    "in_person": lambda h, col: h.startswith(("In-Person", "Total In-Person")),
    "mail": lambda h, col: h.startswith(("Mail Ballots Returned", "Mail Ballots", "Total Mail"))
                           and col.startswith(("Returned", "Count")),
}


def party_tables(page: str) -> dict[str, pd.DataFrame]:
    """The first Party table in each section. NC's 2020 page labels its outstanding-ballot table
    'Total Voted', so the count column decides as well as the heading."""
    heading, found = "", {}
    for m in re.finditer(r"<h[1-5][^>]*>(.*?)</h[1-5]>|<table.*?</table>", page, re.S):
        if m.group(1) is not None:
            heading = html.unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
            continue
        if "Party" not in m.group(0)[:600]:
            continue
        df = pd.read_html(io.StringIO(m.group(0)))[0]
        if "Party" not in df.columns:
            continue
        for kind, fits in SECTIONS.items():
            if kind not in found and fits(heading, str(df.columns[1])):
                found[kind] = df
                break
    return found


def by_party(df: pd.DataFrame) -> tuple[float, float, float, float]:
    labels = df["Party"].astype(str).str.lower()
    values = df[df.columns[1]].map(number)
    dem = values[labels.str.contains("democrat")].sum()
    rep = values[labels.str.contains("republican")].sum()
    total = values[~labels.str.contains("total")].sum()
    return dem, rep, total - dem - rep, total


def page_totals(page: str) -> tuple[float, float, float, float] | None:
    """Total early vote by party: the page's total if it has one, else in-person plus mail."""
    tables = party_tables(page)
    if "total" in tables:
        return by_party(tables["total"])
    parts = [by_party(tables[k]) for k in ("in_person", "mail") if k in tables]
    return tuple(map(sum, zip(*parts))) if parts else None


def uf_pages(cycle: int) -> pd.DataFrame:
    if cycle == 2022:
        index = cached("uf_2022_index.html", UF_2022_INDEX)
        frame = re.search(r'rstudio-pubs-static\.s3\.amazonaws\.com/[^"]+\.html', index)
        index = cached("uf_2022_main.html", "https://" + frame[0])
        pages = {m[1].upper(): m[0] for m in re.finditer(
            r"https://rpubs\.com/ElectProject/([A-Za-z]{2})_early_vo[dt]e_2022", index)}
    else:
        pages = {st: UF_2020_PAGE.format(st=st) for st in STATES}
    out = []
    for st, url in sorted(pages.items()):
        page = cached(f"uf_{cycle}_{st}.html", url)
        if page and cycle == 2022:
            frame = re.search(r'rstudio-pubs-static\.s3\.amazonaws\.com/[^"]+\.html', page)
            page = cached(f"uf_{cycle}_{st}_inner.html", "https://" + frame[0]) if frame else None
        totals = page_totals(page) if page else None
        if totals:
            out.append((st, cycle, "uf_tracker", "registration", None, *totals))
    return pd.DataFrame(out, columns=COLUMNS)
STATES = [
    "AK", "AL", "AR", "AZ", "CA", "CO", "CT", "DC", "DE", "FL", "GA", "HI", "IA", "ID", "IL", "IN", "KS",
    "KY", "LA", "MA", "MD", "ME", "MI", "MN", "MO", "MS", "MT", "NC", "ND", "NE", "NH", "NJ", "NM", "NV",
    "NY", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VA", "VT", "WA", "WI", "WV", "WY",
]
MEDSL_FILES = {  # cycle: (branch, file name)
    2018: ("master", "2018-{st}-precinct-general.zip"),
    2022: ("main", "2022-{st}-local-precinct-general.zip"),
    2024: ("main", "{st}24.zip"),
}
# MEDSL mode labels by what they mean for early voting, first match wins. VA's "ABSENTEE" covers all
# early votes and its "IN-PERSON" is Election Day. "MACHINE" and "ELECTION" appear in CT, DE, and HI
# 2018, which had no in-person early voting. Labels that match nothing count against the state.
MODE_RULES = [
    ("unsplit", r"TOTAL|UNSPECIFIED"),
    ("early", r"EARLY( VOT\w*.*| VOTES?)?|LATE EARLY|LATE VOTES|ADVANCED?( IN PERSON( \d)?)?|ONE[ -]STOP"
              r"|ABSENTEE( \d| BY MAIL| / MILITARY|/EARLY.*)?|2ND ABSENTEE|MAIL( BALLOTS|-IN|-IN CANVASS \d| IN)?"
              r"|PROVISIONAL EARLY"),
    ("election_day", r"(PROVISIONAL )?ELECTION( DAY( - \w+| PAPER)?|_DAY)?|IN-PERSON|MACHINE( COUNT)?|NOT ABSENTEE"),
    ("other", r"PROVISIONAL|FAILSAFE( PROVISIONAL)?|QUESTION|FEDERAL( OVERSEAS)?|WRITE-IN|POST|EMERGENCY"
              r"|SAME DAY REGISTRATION \(SDR\)|AFFIDAVIT|MILITARY|UNKNOWN|HAND COUNT"),
]
MAX_UNSPLIT = 0.02


def medsl_zip(cycle: int, st: str) -> Path:
    branch, pattern = MEDSL_FILES[cycle]
    name = pattern.format(st=st.lower())
    url = f"https://raw.githubusercontent.com/MEDSL/{cycle}-elections-official/{branch}/individual_states/{name}"
    path = RAW / str(cycle) / name
    try:
        download_if_changed(url, path)
    except Exception as e:  # a missing state file is normal (e.g. DC in some years)
        print(f"skip MEDSL {cycle} {st}: {e}")
    return path


def medsl_read(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as z:
        name = next(n for n in z.namelist() if n.endswith((".csv", ".tab")) and not n.startswith("__MACOSX"))
        raw = z.read(name)
    sep = "\t" if name.endswith(".tab") else ","
    cols = ["office", "party_simplified", "mode", "votes", "stage", "special", "county_name", "precinct", "candidate"]
    df = pd.read_csv(io.BytesIO(raw), sep=sep, dtype=str, low_memory=False, usecols=lambda c: c in cols)
    return df.assign(votes=pd.to_numeric(df["votes"], errors="coerce").fillna(0))


def mode_kind(mode: str) -> str:
    mode = str(mode).strip().upper()
    return next((kind for kind, pattern in MODE_RULES if re.fullmatch(pattern, mode)), "unknown")


def early_votes(df: pd.DataFrame, label: str = "") -> tuple[float, float, float] | None:
    """Early (DEM, REP, total) votes from one office's MEDSL rows, or None when the split is incomplete."""
    kind = df["mode"].map(mode_kind)
    # Some states (GA) repeat each precinct's split rows as a TOTAL row; drop TOTAL wherever a split exists.
    keys = [df[c] for c in ("county_name", "precinct", "candidate") if c in df]
    has_split = (kind != "unsplit").groupby(keys).transform("any") if keys else kind != "unsplit"
    keep = ~((kind == "unsplit") & has_split)
    df, kind = df[keep], kind[keep]
    share = df.groupby(kind)["votes"].sum() / df["votes"].sum()
    unknown = df.loc[kind == "unknown", "mode"].unique()
    if len(unknown):
        print(f"MEDSL {label}: unclassified modes {list(unknown)} ({share.get('unknown', 0):.1%} of votes)")
    if share.get("unsplit", 0) + share.get("unknown", 0) > MAX_UNSPLIT or not share.get("early", 0):
        return None
    early = df[kind == "early"]
    party = early["party_simplified"].str.upper()
    return early.loc[party == "DEMOCRAT", "votes"].sum(), early.loc[party == "REPUBLICAN", "votes"].sum(), early["votes"].sum()


def medsl_state(cycle: int, st: str) -> tuple | None:
    """Early votes for each party's top-of-ticket candidates, or None when the state does not split by mode."""
    path = medsl_zip(cycle, st)
    if not path.exists():
        return None
    df = medsl_read(path)
    office = df["office"].str.upper().str.strip()
    df = df[office.isin({"US PRESIDENT", "PRESIDENT"})] if GENERALS[cycle].kind == "presidential" else df[office == "US HOUSE"]
    if "stage" in df:
        df = df[df["stage"].fillna("GEN").str.upper().isin(["GEN", "GENERAL"])]
    votes = early_votes(df, f"{cycle} {st}")
    if votes is None:
        return None
    dem, rep, total = votes
    return (st, cycle, "medsl", "vote_choice", None, dem, rep, total - dem - rep, total)


def medsl(cycle: int) -> pd.DataFrame:
    rows = [r for st in STATES if (r := medsl_state(cycle, st))]
    return pd.DataFrame(rows, columns=COLUMNS)


def consistent_with_eavs(df: pd.DataFrame) -> pd.Series:
    """MEDSL rows whose early total is within 0.8-1.25x of EAVS early ballots (or EAVS has none).
    Outside that, some counties fold early ballots into other labels (ID, NE, MO 2018)."""
    finals = eavs.load()
    early = (finals["early_in_person"].fillna(0) + finals["mail"].fillna(0)).groupby([finals["state"], finals["cycle"]]).sum()
    baseline = pd.Series([early.get((s, c), 0) for s, c in zip(df["state"], df["cycle"])], index=df.index)
    ratio = df["total"] / baseline
    return (df["source"] != "medsl") | (baseline == 0) | ratio.between(0.8, 1.25)


def build() -> Path:
    df = pd.concat([*(mcdonald(c) for c in MCDONALD_SHEETS), *(uf_pages(c) for c in (2020, 2022)),
                    *(medsl(c) for c in MEDSL_FILES)], ignore_index=True)
    modeled = (df["basis"] == "registration") & ~df["state"].isin(PARTY_REGISTRATION)
    df.loc[modeled, "basis"] = "modeled"
    return write(df[(df["total"] > 0) & consistent_with_eavs(df)], OUT)
