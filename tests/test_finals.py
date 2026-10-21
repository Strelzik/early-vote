import pandas as pd

from earlyvote import finals


def rows(data):
    return pd.DataFrame(data, columns=["county_name", "precinct", "candidate", "party_simplified", "mode", "votes"])


def test_duplicate_total_rows_are_dropped_where_a_split_exists():
    df = rows([
        ("FULTON", "P1", "A", "DEMOCRAT", "ADVANCED", 60), ("FULTON", "P1", "A", "DEMOCRAT", "ELECTION DAY", 40),
        ("FULTON", "P1", "A", "DEMOCRAT", "TOTAL", 100),
        ("FULTON", "P1", "B", "REPUBLICAN", "ABSENTEE", 20), ("FULTON", "P1", "B", "REPUBLICAN", "ELECTION DAY", 80),
        ("FULTON", "P1", "B", "REPUBLICAN", "TOTAL", 100),
    ])
    assert finals.early_votes(df) == (60, 20, 80)


def test_unsplit_precincts_over_two_percent_reject_the_state():
    df = rows([
        ("A", "P1", "X", "DEMOCRAT", "EARLY VOTING", 90), ("A", "P1", "X", "DEMOCRAT", "ELECTION DAY", 5),
        ("B", "P2", "X", "DEMOCRAT", "TOTAL", 5),
    ])
    assert finals.early_votes(df) is None


def test_mode_labels():
    expected = {
        "ABSENTEE": "early", "ABSENTEE 2": "early", "ADVANCE IN PERSON 3": "early", "EARLY VOTE NORTH": "early",
        "MAIL-IN CANVASS 2": "early", "IN-PERSON": "election_day", "MACHINE": "election_day",
        "ELECTION DAY - OSS": "election_day", "PROVISIONAL": "other", "TOTAL": "unsplit",
        "ELECTION DAY/EARLY VOTING": "unknown", "NON-FEDERAL": "unknown",
    }
    assert {label: finals.mode_kind(label) for label in expected} == expected


NC_2020_LIKE = """
<h2>Outstanding Mail Ballots</h2><h3>Total Voted by Party Registration</h3>
<table><tr><th>Party</th><th>Outstanding Ballots</th></tr><tr><td>Democrats</td><td>9</td></tr></table>
<h2>In-Person Votes</h2><h3>In-Person Votes by Party Registration</h3>
<table><tr><th>Party</th><th>Count</th></tr><tr><td>Democrats</td><td>50</td></tr>
<tr><td>Republicans</td><td>40</td></tr><tr><td>Unaffiliated</td><td>10</td></tr><tr><td>TOTAL</td><td>100</td></tr></table>
<h2>Returned and Accepted Mail Ballots</h2><h3>Mail Ballots Returned and Accepted by Party Registration</h3>
<table><tr><th>Party</th><th>Returned Ballots</th></tr><tr><td>Democrats</td><td>7</td></tr>
<tr><td>Republicans</td><td>2</td></tr><tr><td>Unaffiliated</td><td>1</td></tr></table>
"""


def test_page_totals_skip_mislabeled_outstanding_table_and_add_in_person_and_mail():
    assert finals.page_totals(NC_2020_LIKE) == (57, 42, 11, 110)
