import pandas as pd

from earlyvote import uf


def test_party_split_only_where_reported():
    df = pd.DataFrame({
        "state": ["NC", "GA", "AK"],
        "accept_all": ["100", "50", "0"],
        "accept_dem": ["40", "0", "0"],
        "accept_rep": ["35", "0", "0"],
        "inperson_all": ["10", "", "0"],
    })
    out = uf.by_party(df, ["state"])
    got = {(r.state, r.mode, r.party): (r.count, r.party_basis) for r in out.itertuples()}

    assert got == {
        ("NC", "mail_returned", "DEM"): (40, "registration"),
        ("NC", "mail_returned", "REP"): (35, "registration"),
        ("NC", "mail_returned", "OTH"): (25, "registration"),
        ("GA", "mail_returned", "UNK"): (50, "none"),
        ("NC", "in_person_early", "UNK"): (10, "none"),
    }
