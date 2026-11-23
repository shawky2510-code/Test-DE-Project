"""Small tests of the cleaning functions (python -m pytest tests)."""
import sys
sys.path.insert(0, ".")
import pandas as pd
from marketsim import cleaning as K


def test_timestamp_conventions():
    p = K.parse_timestamps(pd.Series(["2025-01-02 09:30:00", "2025-01-02T14:30:00Z",
                                      "2025-07-01T13:30:00Z", "not-a-time", "2025-02-30 10:00:00",
                                      "31/03/2025 10:15"]))
    assert p.bar_start_local.iloc[0] == p.bar_start_local.iloc[1]            # 14:30Z = 09:30 NY (winter)
    assert p.bar_start_local.iloc[2] == pd.Timestamp("2025-07-01 09:30")     # 13:30Z = 09:30 NY (summer)
    assert p.bar_start_utc.iloc[3:].isna().all()                             # malformed / placeholder


def test_symbol_as_of_date():
    sym = pd.DataFrame({"security_id": ["S1"], "ticker": ["NEW"], "company_name": ["x"], "sector": ["Energy"],
                        "listing_date": pd.to_datetime(["2020-01-01"]), "delisting_date": pd.to_datetime([None]),
                        "shares_outstanding": [10]})
    hist = pd.DataFrame({"security_id": ["S1"], "change_type": ["ticker"], "old_value": ["OLD"],
                         "new_value": ["NEW"], "effective_date": ["2025-03-17"]})
    vt = K.ticker_validity(K.build_dim_symbol(sym, hist))
    df = pd.DataFrame({"ticker": ["OLD", "OLD", "NEW", "NEW"],
                       "trading_date": pd.to_datetime(["2025-03-14", "2025-03-17", "2025-03-14", "2025-03-17"])})
    out = K.attach_security(df, vt).tolist()
    assert out[0] == "S1" and pd.isna(out[1]) and pd.isna(out[2]) and out[3] == "S1"


def test_clean_symbols_removes_repeated_row():
    s = pd.DataFrame({"security_id": ["A", "A"], "ticker": ["AAA", "aaa"], "company_name": ["a", "A"],
                      "sector": ["Information Technology", "Information Technology"],
                      "listing_date": ["2020-01-01"] * 2, "delisting_date": [None] * 2, "shares_outstanding": [1, 1]})
    c, removed = K.clean_symbols(s)
    assert len(c) == 1 and c.sector.iloc[0] == "Technology" and len(removed) == 1
