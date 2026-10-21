# Data source survey (checked 2026-10-20)

What each source offers today, probed directly. Nothing has been built yet.

## Summary

| Source | 2026 now | Past cycles | County | Party | History by days out |
|---|---|---|---|---|---|
| UF Election Lab tracker | 49 states+DC, CSV, updated daily | 2024 final CSV only; 2020/2022 pages have no data files | 40 states | ~25 states (registration) | No. Latest snapshot only |
| NC State Board (voter-level) | Daily zip, 735k rows | Every election 1990s–2024 | Yes (+precinct, CD, leg.) | Yes | **Yes, exact** (request/send/return dates per ballot) |
| PA data.pa.gov (voter-level) | Daily, 1.27M rows | 2020, 2022, 2024 generals | Yes | Yes | **Yes, exact** (mail only; PA has no in-person early vote) |
| FL Division of Elections | Daily county × party text files | Final PDFs only | Yes | Yes | No. Latest only, must snapshot ourselves |
| NV Secretary of State | Daily county × party | 2024 reports exist | Yes | Yes | Partial; site is behind bot protection |
| AZ | No official public feed (UF uses stealth-analytics.com) | — | Some | Yes | No |
| GA SoS absentee files (bonus) | Voter-level with dates | Yes | Yes | No registration party | Yes, but portal blocks scripts (403) |
| EAVS (EAC) | — | 2004–2024, every even year | Yes (6,461 jurisdictions in 2024) | No | No. Final totals only |
| Census CPS supplement | — | Every even year, Census API 2010–2024 | No | No | No. Survey of method (mail / early / Election Day) by state |

## UF Election Lab

- National: `https://election.lab.ufl.edu/data-downloads/earlyvote/2026/US.csv`
  - Columns: `request_*`, `accept_*` (mail returned), `inperson_*`, `voted_*`, each split by dem/rep/none, 4 age bands, race, gender; plus `turn_2022`, `last_update`, `data_source`, `notes`.
  - 49 rows (no AL, NH). AK, LA, MO, NY, SC, WV, WA show zeros so far.
- County: `.../2026/{ST}_county.csv` exists for 40 states (AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY ME MD MA MI MN MS MT NE NV NJ NM NC ND OH OK OR PA RI SD TN UT VT VA WI WY). New England files are towns.
- Congressional district: `.../2026/{ST}_cd.csv` for some states.
- **No history.** Each file is overwritten. Wayback has ~10 captures of the 2026 file (Sep 18 – Oct 19) and 13 of the 2024 file, mostly outside the final weeks.
- Past cycles: 2024 has a final `2024/US.csv`. 2022 is an RPubs page, 2020 a GitHub Pages site (R Markdown, numbers in HTML, no CSVs). 2008–2018 lived on electproject.org; Wayback coverage is near daily for 2014, patchy for 2016 and 2018.
- `last_update` varies by state (some lag days), so "days out" must use each row's date, not the download date.
- **License: CC BY-NC-ND 4.0.** Attribution required, no commercial use, no redistribution of modified versions. Fine for private analysis; ask before publishing derived maps.

## North Carolina (best source)

- Bucket listing: `https://s3.amazonaws.com/dl.ncsbe.gov?list-type=2&prefix=ENRS/2026_11_03/`
- `absentee_20261103.zip` (32 MB, refreshed ~5am ET daily): one row per ballot. Fields include `county_desc`, `age`, `race`, `gender`, `voter_party_code`, `precinct_desc`, `cong_dist_desc`, `ballot_req_type` (MAIL / EARLY VOTING), `ballot_req_dt`, `ballot_send_dt`, `ballot_rtn_dt`, `ballot_rtn_status`, `site_name`.
- Also small aggregates: `absentee_counts_county_*.csv`, `absentee_counts_state_*.csv`, `absentee_demo_stats_*.csv`.
- Same files exist for every general: 2008 (112 MB), 2010, 2012, 2014, 2016, 2018, 2020, 2022 (100 MB), 2024 (207 MB). Because every ballot has dates, cumulative curves by days out can be rebuilt exactly for any cycle.
- Contains names and addresses; drop those columns on read and never commit raw files.
- 2026 row counts match UF (735,552 rows vs UF 733,095 accepted).

## Pennsylvania

- Socrata datasets on data.pa.gov, one per election: 2026 `nbwd-pfn4` (live), 2024 `3q5t-ddp8`, 2022 `uhfm-zhus`, 2020 `mcba-yywm`.
- Fields: `countyname`, `party`, `dateofbirth` (year-month), `appissuedate`, `appreturndate`, `ballotsentdate`, `ballotreturneddate`, CD / state house / senate, lat/lon, status.
- Mail only. No-excuse mail began in 2020, so no comparable 2018 or earlier.
- Queryable with SoQL, so county × party × day can be aggregated server-side.

## Florida

- Daily county × party text files (tab-separated, latest only):
  `https://electionfiles.floridados.gov/countyballotreportfiles/Stats_49894_{VbmVoted,VbmProvided,EarlyVoted}.txt`
- Archive page holds final PDFs per election, not daily series. Voter-level files come from county supervisors on request, not public download.
- In-person early voting statewide is Oct 24 – Oct 31 (some counties start sooner).
- To get a 2026 time series we must start saving these files daily now. Past days-out curves would come only from Wayback, if captured.

## Nevada, Arizona, Georgia

- NV: SoS daily early voting turnout by county and party (and the "Vivid" dashboard). `nvsos.gov` returns an Incapsula bot challenge to scripts; would need a headless browser or manual download.
- AZ: no official daily public file. UF cites stealth-analytics.com. Maricopa and other counties do not publish a statewide-style feed.
- GA: no party registration, but the SoS publishes voter-level absentee files with dates at `mvp.sos.ga.gov/s/voter-absentee-files`. Returns 403 to scripts.

## EAVS

- Index: `https://www.eac.gov/research-and-data/datasets-codebooks-and-surveys`
- CSV/XLSX for 2004–2024 (format varies a lot before 2016). 2024 V2 CSV: 6,461 jurisdictions, `FIPSCode`, `State_Abbr`, section F1 participation by mode (F1a total, F1b Election Day in person, F1d mail, F1f early in person, per the EAVS instrument).
- Final totals only, no party, no dates. Use it as the denominator and the "how big did early vote end up" baseline per county.

## Census CPS Voting and Registration Supplement

- Census API `https://api.census.gov/data/{year}/cps/voting/nov` works for 2010–2024.
- `PES5` (in person vs mail), `PES6` (on or before Election Day), by state. Sample survey: state-level only, no party, no dates. Low priority.

## Implications for the build

1. Start a daily snapshot job right away for UF (national + county) and FL. Every day we wait is lost history for 2026.
2. True days-out comparisons across cycles are only available from NC (2008–2026) and PA (2020–2026). Lead with NC.
3. Other states: compare 2026 to the past cycle's **final** early vote (EAVS or UF 2024/2022 final) and to 2022 total turnout, not day-by-day.
4. Wayback scraping for UF/electproject past cycles is possible but patchy; treat as a stretch goal.
5. Party split: use registration from UF/state files only for party-registration states; anything else is modeled and must be labeled as such.
