# earlyvote

Early vote numbers by state, county, and party registration for the 2026 midterm, compared with past generals at the same number of days before Election Day.

See [docs/data-sources.md](docs/data-sources.md) for what each source offers.

## Setup

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
```

## Commands

```bash
.venv/Scripts/python -m earlyvote.cli snapshot
```

Saves new copies of the UF Election Lab national and county CSVs and the Florida DOS county files to `data/raw/snapshots/<source>-<cycle>/`. These sources overwrite themselves daily, so history exists only if this runs. A copy is kept only when its content changed. The Windows scheduled task `earlyvote-snapshot` runs `snapshot` then `build` at 9:00 and 19:30 and logs to `data/logs/snapshot.log`.

```bash
.venv/Scripts/python -m earlyvote.cli backfill
```

Adds Internet Archive copies of the UF files for 2024 and 2026 as dated snapshots. Safe to rerun; it is paced because the Archive rate-limits.

```bash
.venv/Scripts/python -m earlyvote.cli build
```

Runs `nc`, `uf`, `fl`, `eavs`, and `report` (each also runs alone). Writes `data/processed/{nc,uf,fl}/<cycle>.parquet`, `data/processed/eavs.parquet`, and `reports/earlyvote.html`.

```bash
.venv/Scripts/python -m earlyvote.cli nc
```

Downloads the NC State Board voter-level absentee file for each general (2008 to 2026) and writes `data/processed/nc/<cycle>.parquet`. Pass years to limit it, for example `nc 2026`. Files are redownloaded only when NC publishes a new version.

## Tidy table

Every source is reshaped to one long table (`src/earlyvote/tidy.py`). Counts are cumulative as of `days_out` days before Election Day.

| column | values |
|---|---|
| state, county | two-letter state, county name in title case |
| cycle, election_type, covid_outlier | year, `midterm` or `presidential`, true for 2020 |
| days_out, as_of | days before Election Day (120 means 120 or more) and the matching date |
| mode | `mail_requested`, `mail_returned`, `in_person_early` |
| party, party_basis | `DEM`, `REP`, `OTH` (unaffiliated and minor), `UNK`; `registration` or `modeled` |
| age_band | `18-25`, `26-40`, `41-65`, `65+`, `unknown` (UF's bands) |
| count, source | cumulative ballots, source id |

Party is registration, not vote choice. `county` is `ALL` on statewide rows (UF); never sum those with county rows. A split in a state without party registration (`tidy.PARTY_REGISTRATION`) is marked `modeled`. Load everything with `earlyvote.tidy.load()`.

## Final totals (EAVS)

`earlyvote.eavs.load()` returns one row per jurisdiction and cycle (2014 to 2024): total turnout, Election Day, early in person, mail (domestic plus all-mail jurisdictions), UOCAVA, provisional. It is the denominator for "share of 2022 turnout" and the final early vote for cycles with no daily history. NC's voter file counts about 4% more in-person early votes than EAVS for 2022.

`earlyvote.geo` joins tracker places to EAVS. EAVS jurisdictions are towns in New England, municipalities in Wisconsin, and a few separate cities (Chicago); each is allocated to counties by its FIPS code or, when it spans counties, by the Census 2022 population split (`sub-est2024.csv`, no key needed). Names match strictly first, then with spelling fixes (Saint/St, burgh/burg, &/and), then without TOWN/CITY, then by a unique 10-letter prefix (EAVS truncates some names). Town lists match only towns; county lists try county names before loose town names. Matched 2022 turnout covers at least 97% of every state with county data except where EAVS left a county blank (AR, KS, UT). Connecticut uses its eight pre-2022 counties to match EAVS and the map shapes.

## Report

`reports/earlyvote.html` is one self-contained page: a state map (share of 2022 turnout, or party split), a state picker with cumulative early vote by days out (midterms or presidential years, ballots or share of turnout), party mix by cycle, and a county map and table. NC counties also have their own days-out trends. To view it in a browser served locally:

```bash
.venv/Scripts/python -m http.server 8765 --directory reports
```

## UF notes

- Statewide history for 2026 and 2024 comes only from saved snapshots and Internet Archive copies, so curves have gaps between saved days.
- County files have no date; each takes its state's `last_update` from the nearest national snapshot.
- Tennessee county rows are daily increments and are summed. Dates with the wrong year (for example 11/1/2023 in the 2024 file) are read in the cycle's year.

## Florida notes

- Counts run through the day before each county's compile date. Mail requested is "provided, not yet returned" plus returned.
- Florida's CDN serves stale copies to plain requests, so snapshot requests carry a unique query string.

## NC notes

- In person early means ONE STOP / EARLY VOTING ballots with an accepted status. Mail returned means other ballot types with an accepted status (`ACCEPTED*`, or `OK` in 2008). Mail requested counts every mail request by request date.
- Each file is cut off the day before NC exported it, which drops a handful of ballots dated in the future.
- While a cycle is live, NC's file lists only mail ballots already returned, so `mail_requested` is omitted for 2026 until the post-election file.
- 2020 is a COVID outlier for mail voting.

## Data license

UF Election Lab statistics are CC BY-NC-ND 4.0. Attribute them, do not use them commercially, and ask before publishing derived works.
