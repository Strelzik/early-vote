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

Saves new copies of the UF Election Lab national and county CSVs and the Florida DOS county files to `data/raw/snapshots/`. These sources overwrite themselves daily, so history exists only if this runs. A copy is kept only when its content changed. The Windows scheduled task `earlyvote-snapshot` runs it at 9:00 and 19:30 and logs to `data/logs/snapshot.log`.

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

Party is registration, not vote choice.

## NC notes

- In person early means ONE STOP / EARLY VOTING ballots with an accepted status. Mail returned means other ballot types with an accepted status (`ACCEPTED*`, or `OK` in 2008). Mail requested counts every mail request by request date.
- Each file is cut off the day before NC exported it, which drops a handful of ballots dated in the future.
- While a cycle is live, NC's file lists only mail ballots already returned, so `mail_requested` is omitted for 2026 until the post-election file.
- 2020 is a COVID outlier for mail voting.

## Data license

UF Election Lab statistics are CC BY-NC-ND 4.0. Attribute them, do not use them commercially, and ask before publishing derived works.
