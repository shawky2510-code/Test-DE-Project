"""The four Milestone 1 metrics (Dataset Description, Appendix A), in pandas."""
import numpy as np
import pandas as pd
from . import config as C


def expected_bars(runs, symbols, calendar, events, dim_symbol):
    """expected = session minutes on the calendar for every symbol listed that day, plus the
    index, minus announced halt minutes. One row per (run, security_id, trading_date)."""
    days = calendar[calendar.is_trading_day]
    out = []
    for _, r in runs.iterrows():
        start, end = pd.Timestamp(r["window.start"]), pd.Timestamp(r["window.end"])
        dd = days[(days.date >= start) & (days.date <= end)][["date", "session_len"]]
        for _, s in symbols.iterrows():
            last = s.delisting_date - pd.Timedelta(days=1) if pd.notna(s.delisting_date) else end
            x = dd[(dd.date >= s.listing_date) & (dd.date <= last)]
            out.append(pd.DataFrame({"run_id": r.run_id, "security_id": s.security_id,
                                     "trading_date": x.date.to_numpy(),
                                     "expected": x.session_len.to_numpy()}))
        out.append(pd.DataFrame({"run_id": r.run_id, "security_id": C.INDEX_SECURITY_ID,
                                 "trading_date": dd.date.to_numpy(), "expected": dd.session_len.to_numpy()}))
    exp = pd.concat(out, ignore_index=True)
    h = events[events["type"] == "halt"]
    for _, e in h.iterrows():                     # halts apply to every run
        m = (exp.security_id == e.security_id) & (exp.trading_date == e.event_date)
        exp.loc[m, "expected"] -= int(e.duration_minutes)
    return exp


def completeness(canonical, expected):
    acc = canonical.groupby(["run_id", "security_id", "trading_date"]).size().rename("accepted").reset_index()
    t = expected.merge(acc, on=["run_id", "security_id", "trading_date"], how="outer")
    t["accepted"] = t["accepted"].fillna(0).astype(int)
    t["expected"] = t["expected"].fillna(0).astype(int)
    t["completeness"] = np.where(t.expected > 0, t.accepted / t.expected, np.nan)
    by_run = t.groupby("run_id").agg(accepted=("accepted", "sum"), expected=("expected", "sum"))
    by_run["completeness"] = by_run.accepted / by_run.expected
    return t, by_run


def ohlc_validity(raw_deduped_bars):
    """Population: bars with all four prices present (a null price is a MISSING_REQUIRED_FIELD,
    not an OHLC failure). valid = low <= open,close <= high and all prices > 0."""
    b = raw_deduped_bars
    chk = b.dropna(subset=["open", "high", "low", "close"])
    valid = ((chk.low <= chk.open) & (chk.low <= chk.close) & (chk.open <= chk.high) &
             (chk.close <= chk.high) & (chk[["open", "high", "low", "close"]] > 0).all(axis=1))
    out = pd.DataFrame({"run_id": chk.run_id, "valid": valid}).groupby("run_id")["valid"].agg(
        checked="size", valid="sum")
    out["rate"] = out["valid"] / out["checked"]
    return out


def reconciliation_summary(rec):
    s = rec.groupby(["run_id", "status"]).size().unstack(fill_value=0)
    for c in ["matched", "mismatched", "missing_in_vendor", "missing_in_derived"]:
        if c not in s:
            s[c] = 0
    s["compared"] = s.matched + s.mismatched
    s["match_rate"] = s.matched / s.compared
    return s[["compared", "matched", "mismatched", "missing_in_vendor", "missing_in_derived", "match_rate"]]


def reject_and_late(n_received, canonical, rejects):
    r = rejects.groupby("run_id").size().rename("rejected")
    rec = pd.Series(n_received).rename("received")
    a = canonical.groupby("run_id").size().rename("accepted")
    late = canonical[canonical.lateness_s > C.LATE_SECONDS].groupby("run_id").size().rename("late_accepted")
    t = pd.concat([rec, r, a, late], axis=1).fillna(0).astype(int)
    t["reject_rate"] = t.rejected / t.received
    t["late_rate"] = t.late_accepted / t.accepted
    return t
