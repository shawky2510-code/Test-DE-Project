"""Reusable cleaning functions. Every step is a function, not a notebook cell.

Order of the pipeline (see clean_bars):
  parse_timestamps -> dedup -> resolve symbol/run -> calendar check -> value checks
  -> adjustment factor -> canonical table + rejects table
"""
import json
import numpy as np
import pandas as pd
from . import config as C

SECTOR_FIX = {"Information Technology": "Technology"}
FAR_FUTURE = pd.Timestamp("2100-01-01")


# ----------------------------------------------------------------------------- reference data
def clean_symbols(symbols):
    """symbols.csv has a repeated SEC009 row (lower-case ticker, upper-case name) and one
    non-standard sector label. Keep the first row per security_id and normalise labels."""
    s = symbols.copy()
    s["ticker"] = s["ticker"].str.strip()
    dup = s.duplicated("security_id", keep="first")
    removed = s[dup]
    s = s[~dup].copy()
    s["sector"] = s["sector"].replace(SECTOR_FIX)
    s["listing_date"] = pd.to_datetime(s["listing_date"])
    s["delisting_date"] = pd.to_datetime(s["delisting_date"])
    return s.reset_index(drop=True), removed


def build_dim_symbol(symbols, history):
    """Type-2 symbol dimension: one row per (security_id, period in which ticker, sector and
    shares_outstanding were constant). valid_to is exclusive. Starting values come from the
    old_value of the first change, later values from new_value. If symbols.csv disagrees with
    the history, the dated history wins (see the findings)."""
    h = history.copy()
    h["effective_date"] = pd.to_datetime(h["effective_date"])
    rows = []
    for _, s in symbols.iterrows():
        sid = s["security_id"]
        hs = h[h.security_id == sid].sort_values("effective_date")
        start = {"ticker": s["ticker"], "sector": s["sector"],
                 "shares_outstanding": str(s["shares_outstanding"])}
        for col in start:
            first = hs[hs.change_type == col].head(1)
            if len(first):
                start[col] = first.iloc[0]["old_value"]
        cuts = sorted(hs["effective_date"].unique())
        edges = [s["listing_date"]] + [pd.Timestamp(c) for c in cuts]
        ends = edges[1:] + [s["delisting_date"] if pd.notna(s["delisting_date"]) else FAR_FUTURE]
        state = dict(start)
        for i, (a, b) in enumerate(zip(edges, ends)):
            if i > 0:
                for _, ch in hs[hs.effective_date == a].iterrows():
                    state[ch["change_type"]] = ch["new_value"]
            rows.append({"security_id": sid, **state, "company_name": s["company_name"],
                         "valid_from": a, "valid_to": b})
    d = pd.DataFrame(rows)
    d["sector"] = d["sector"].replace(SECTOR_FIX)
    d["shares_outstanding"] = d["shares_outstanding"].astype("int64")
    return d


def ticker_validity(dim_symbol):
    """Collapse the dimension to (ticker, security_id, valid_from, valid_to) so a ticker can
    be looked up as of a date. Consecutive periods with the same ticker are merged."""
    t = dim_symbol[["security_id", "ticker", "valid_from", "valid_to"]].sort_values(
        ["security_id", "valid_from"])
    out = []
    for (sid, tk), g in t.groupby(["security_id", "ticker"], sort=False):
        out.append({"security_id": sid, "ticker": tk,
                    "valid_from": g.valid_from.min(), "valid_to": g.valid_to.max()})
    return pd.DataFrame(out)


def clean_runs(runs):
    """sim_runs.json exports RUN-2025B twice. Keep the latest export (largest created_at) per
    run_id and flag a sigma_annual that is not a fraction (RUN-2025C holds 18.0, a percent)."""
    r = runs.copy()
    r["created_at"] = pd.to_datetime(r["created_at"], utc=True)
    r = r.sort_values(["run_id", "created_at"])
    removed = r[r.duplicated("run_id", keep="last")]
    r = r.drop_duplicates("run_id", keep="last").copy()
    r["config_flags"] = np.where(r["parameters.volatility.sigma_annual"] > 1,
                                 "SIGMA_ANNUAL_LOOKS_LIKE_PERCENT", "")
    r["sigma_annual_clean"] = np.where(r["parameters.volatility.sigma_annual"] > 1,
                                       r["parameters.volatility.sigma_annual"] / 100,
                                       r["parameters.volatility.sigma_annual"])
    return r.reset_index(drop=True), removed


def clean_calendar(cal):
    c = cal.copy()
    c["date"] = pd.to_datetime(c["date"])
    c["is_trading_day"] = c["is_trading_day"].str.lower().eq("true")
    def minutes(t):
        return t.str.slice(0, 2).astype("Int64") * 60 + t.str.slice(3, 5).astype("Int64")
    c["open_min"] = minutes(c["session_open"])
    c["close_min"] = minutes(c["session_close"])
    c["session_len"] = (c["close_min"] - c["open_min"]).fillna(0).astype(int)
    return c


def clean_events(events, vtick):
    """Events carry an explicit UTC offset. Convert to exchange time, resolve the ticker as
    of the event date, and derive the split factor and the halt window."""
    e = events.copy()
    ts = pd.to_datetime(e["time"], utc=True).dt.tz_convert(C.EXCHANGE_TZ)
    e["event_local"] = ts.dt.tz_localize(None)
    e["event_date"] = e["event_local"].dt.normalize()
    e = e.merge(vtick, on="ticker", how="left")
    e = e[(e.valid_from.isna()) | ((e.event_date >= e.valid_from) & (e.event_date < e.valid_to))]
    e = e.drop(columns=["valid_from", "valid_to"])
    def factor(r):
        if r["type"] != "split":
            return np.nan
        new, old = [float(x) for x in str(r["ratio"]).split(":")]
        return old / new                      # 2:1 -> prices before the split x 0.5
    e["price_factor"] = e.apply(factor, axis=1)
    e["halt_start_local"] = np.where(e["type"] == "halt", e["event_local"], pd.NaT)
    e["halt_start_local"] = pd.to_datetime(e["halt_start_local"])
    e["halt_end_local"] = e["halt_start_local"] + pd.to_timedelta(e["duration_minutes"], unit="m")
    return e.reset_index(drop=True)


# ----------------------------------------------------------------------------- timestamps
def parse_timestamps(ts, dmy_policy="reject"):
    """Declared convention: exchange time (America/New_York); UTC is kept beside it.
    Three formats exist, each with its own clock:
      'YYYY-MM-DD HH:MM:SS'   exchange local time
      'YYYY-MM-DDTHH:MM:SSZ'  UTC (a trailing Z) -> converted to exchange time
      'DD/MM/YYYY HH:MM'      day-first. 159 rows, ALL carrying the same value '31/03/2025 10:15'
                              although their prices and received_at span the whole window, so the
                              value is a placeholder and not the bar's minute. dmy_policy="reject"
                              (default) treats them as malformed; "parse" reads them as exchange time.
    Anything else is malformed (NaT)."""
    ts = ts.astype("string")
    plain = ts.str.match(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$").fillna(False)
    zulu = ts.str.match(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$").fillna(False)
    slash = ts.str.match(r"^\d\d/\d\d/\d{4} \d\d:\d\d$").fillna(False)
    local = pd.Series(pd.NaT, index=ts.index, dtype="datetime64[ns]")
    local[plain] = pd.to_datetime(ts[plain], format="%Y-%m-%d %H:%M:%S", errors="coerce")
    if dmy_policy == "parse":
        local[slash] = pd.to_datetime(ts[slash], format="%d/%m/%Y %H:%M", errors="coerce")
    utc = pd.Series(pd.NaT, index=ts.index, dtype="datetime64[ns, UTC]")
    utc[zulu] = pd.to_datetime(ts[zulu], format="%Y-%m-%dT%H:%M:%SZ", errors="coerce", utc=True)
    # local -> utc and utc -> local
    from_local = local.dt.tz_localize(C.EXCHANGE_TZ, ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
    utc = utc.fillna(from_local)
    local_from_utc = utc.dt.tz_convert(C.EXCHANGE_TZ).dt.tz_localize(None)
    local = local.fillna(local_from_utc)
    fmt = np.select([plain, zulu, slash], ["local_iso", "utc_z", "local_dmy"], "malformed")
    return pd.DataFrame({"bar_start_local": local, "bar_start_utc": utc, "ts_format": fmt},
                        index=ts.index)


# ----------------------------------------------------------------------------- main cleaning
def attach_security(df, vtick, ticker_col="ticker", date_col="trading_date"):
    """Attach security_id by ticker AS OF the bar's date (merge on ticker, keep the record
    whose [valid_from, valid_to) contains the date). INDEX is not a company."""
    x = df[[ticker_col, date_col]].copy()
    x["_i"] = np.arange(len(x))
    m = x.merge(vtick, left_on=ticker_col, right_on="ticker", how="left", suffixes=("", "_v"))
    ok = (m[date_col] >= m["valid_from"]) & (m[date_col] < m["valid_to"])
    m = m[ok].drop_duplicates("_i").set_index("_i")["security_id"]
    sid = pd.Series(m.reindex(np.arange(len(x))).to_numpy(), index=df.index, dtype="object")
    sid[df[ticker_col] == C.INDEX_TICKER] = C.INDEX_SECURITY_ID
    return sid


def clean_bars(bars, refs, source_file="bars_1m.parquet", repair=False):
    """Returns (canonical, rejects). Every input row goes to exactly one of them.
    repair=False (default, strict): invalid values are rejected.
    repair=True  (sensitivity run): a bar whose high < low but is fully consistent once the two are
    swapped gets them swapped, and a negative volume gets its sign flipped; both are flagged."""
    df = bars.copy()
    cal, runs, vtick, events = refs["calendar"], refs["runs"], refs["vtick"], refs["events"]

    p = parse_timestamps(df["ts"])
    df = pd.concat([df, p], axis=1)
    df["trading_date"] = df["bar_start_local"].dt.normalize()

    # 1. duplicates on (run_id, ticker, minute); keep the earliest received_at
    key_ok = df["bar_start_utc"].notna()
    order = df.sort_values(["received_at", "source_row"]).index
    dup = pd.Series(False, index=df.index)
    d = df.loc[order][key_ok.loc[order]]
    dup.loc[d.index[d.duplicated(["run_id", "ticker", "bar_start_utc"], keep="first")]] = True

    # 2. the other checks, one boolean per enum reason
    df["security_id"] = attach_security(df, vtick)
    known_any = set(vtick.ticker) | {C.INDEX_TICKER}
    unk_sym = df["security_id"].isna() & (df["bar_start_utc"].notna() | ~df["ticker"].isin(known_any))
    unk_run = ~df["run_id"].isin(runs["run_id"])
    malformed = df["bar_start_utc"].isna()

    c = cal.set_index("date")
    df["_open"] = df["trading_date"].map(c["open_min"])
    df["_close"] = df["trading_date"].map(c["close_min"])
    df["_trading"] = df["trading_date"].map(c["is_trading_day"]).fillna(False).astype(bool)
    mins = df["bar_start_local"].dt.hour * 60 + df["bar_start_local"].dt.minute
    df["minute_of_session"] = (mins - df["_open"]).astype("Int64")
    outside = ~malformed & (~df["_trading"] | (mins < df["_open"]) | (mins >= df["_close"]))

    df["_rep_hl"] = False
    df["_rep_vol"] = False
    if repair:
        lo, hi = np.minimum(df["low"], df["high"]), np.maximum(df["low"], df["high"])
        sw = (df["high"] < df["low"]) & (lo <= df[["open", "close"]].min(axis=1)) & \
             (hi >= df[["open", "close"]].max(axis=1))
        df.loc[sw, ["high", "low"]] = df.loc[sw, ["low", "high"]].to_numpy()
        df["_rep_hl"] = sw
        neg = df["volume"] < 0
        df.loc[neg, "volume"] = -df.loc[neg, "volume"]
        df["_rep_vol"] = neg
    px = df[["open", "high", "low", "close"]]
    all_px = px.notna().all(axis=1)
    bad_ohlc = all_px & ((px <= 0).any(axis=1) | (df["high"] < df["low"]) |
                         (df["high"] < df[["open", "close"]].max(axis=1)) |
                         (df["low"] > df[["open", "close"]].min(axis=1)))
    bad_num = (df["volume"] < 0)
    missing = px.isna().any(axis=1) | df["run_id"].isna() | df["ticker"].isna() | df["ts"].isna()

    tests = [("DUPLICATE_BAR", dup), ("UNKNOWN_SYMBOL", unk_sym), ("UNKNOWN_RUN", unk_run),
             ("MALFORMED_TIMESTAMP", malformed), ("OUTSIDE_SESSION", outside),
             ("INVALID_OHLC", bad_ohlc), ("INVALID_NUMERIC_RANGE", bad_num),
             ("MISSING_REQUIRED_FIELD", missing)]
    reason = pd.Series(pd.NA, index=df.index, dtype="object")
    for name, mask in tests[::-1]:               # reversed so the first enum value wins
        reason[mask] = name
    df["reject_reason"] = reason
    # how many reasons applied (used by the findings to show the precedence at work)
    df["n_reasons"] = sum(m.astype(int) for _, m in tests)

    rej = df[df["reject_reason"].notna()]
    acc = df[df["reject_reason"].isna()].copy()

    # 3. adjustment factor from splits (prices before the split date x factor)
    acc["adj_factor"] = 1.0
    for _, s in events[events["type"] == "split"].iterrows():
        m = (acc["security_id"] == s["security_id"]) & (acc["trading_date"] < s["event_date"])
        acc.loc[m, "adj_factor"] *= s["price_factor"]
    acc["adj_close"] = (acc["close"] * acc["adj_factor"]).round(4)

    # 4. lateness and non-fatal quality flags
    end_utc = acc["bar_start_utc"] + pd.Timedelta(minutes=1)
    acc["received_at_utc"] = acc["received_at"]
    acc["lateness_s"] = (acc["received_at"] - end_utc).dt.total_seconds()
    flags = pd.DataFrame({
        "LATE": acc["lateness_s"] > C.LATE_SECONDS,
        "TS_CONVERTED_FROM_UTC": acc["ts_format"] == "utc_z",
        "TS_DAY_FIRST_FORMAT": acc["ts_format"] == "local_dmy",
        "SPLIT_ADJUSTED": acc["adj_factor"] != 1.0,
        "REPAIRED_HIGH_LOW_SWAPPED": acc["_rep_hl"],
        "REPAIRED_VOLUME_SIGN": acc["_rep_vol"],
    })
    h = events[events["type"] == "halt"]
    halt = pd.Series(False, index=acc.index)
    for _, e in h.iterrows():
        halt |= ((acc["security_id"] == e["security_id"]) &
                 (acc["bar_start_local"] >= e["halt_start_local"]) &
                 (acc["bar_start_local"] < e["halt_end_local"]))
    flags["INSIDE_HALT_WINDOW"] = halt
    qf = pd.Series("", index=acc.index)
    for name in flags.columns:                      # vectorised: no row-wise apply on 4M rows
        qf = qf + np.where(flags[name] & (qf != ""), "|", "") + np.where(flags[name], name, "")
    acc["quality_flags"] = qf

    acc["bar_id"] = (acc["run_id"] + "|" + acc["security_id"] + "|" +
                     acc["bar_start_utc"].dt.strftime("%Y%m%dT%H%M"))
    acc["source_file"] = source_file
    acc["ticker_as_traded"] = acc["ticker"]
    acc["bar_start_local"] = acc["bar_start_local"]
    acc["received_at_utc"] = acc["received_at_utc"]
    cols = ["bar_id", "source_file", "source_row", "run_id", "security_id", "ticker_as_traded",
            "bar_start_local", "bar_start_utc", "trading_date", "minute_of_session",
            "open", "high", "low", "close", "volume", "adj_factor", "adj_close",
            "received_at_utc", "lateness_s", "quality_flags"]
    canonical = acc[cols].sort_values(["run_id", "security_id", "bar_start_utc"]).reset_index(drop=True)

    rj = rej[["run_id", "ticker", "ts", "open", "high", "low", "close", "volume",
              "received_at", "source_row", "reject_reason", "n_reasons"]].copy()
    rj["raw_payload"] = rej[["run_id", "ticker", "ts", "open", "high", "low", "close", "volume",
                             "received_at"]].astype(object).where(rej[["run_id", "ticker", "ts", "open",
                             "high", "low", "close", "volume", "received_at"]].notna(), None
                             ).apply(lambda r: json.dumps({k: (None if v is None else str(v)) for k, v in r.items()}), axis=1)
    rj["source_file"] = source_file
    rj = rj.drop(columns=["open", "high", "low", "close", "volume"]).reset_index(drop=True)
    return canonical, rj


# ----------------------------------------------------------------------------- daily + reconcile
def derive_daily(canonical):
    """Daily bars from the accepted minute bars (the source of truth)."""
    c = canonical.sort_values("bar_start_utc")
    g = c.groupby(["run_id", "security_id", "trading_date"], sort=True)
    d = g.agg(ticker_as_traded=("ticker_as_traded", "last"), open=("open", "first"),
              high=("high", "max"), low=("low", "min"), close=("close", "last"),
              volume=("volume", "sum"), n_bars=("open", "size"),
              adj_factor=("adj_factor", "first")).reset_index()
    return d


def detect_vendor_volume_scale(daily, v):
    """The vendor may quote volume in another unit for some securities. For each security the
    median of vendor_volume / derived_volume is computed; a median close to 0.01 means the vendor
    reports round lots of 100 shares. Returns {security_id: 100} for those securities."""
    m = daily.merge(v[["run_id", "security_id", "trading_date", "volume_v"]],
                    on=["run_id", "security_id", "trading_date"])
    ratio = (m["volume_v"] / (m["volume"] / m["adj_factor"])).groupby(m["security_id"]).median()
    return {sid: 100 for sid, r in ratio.items() if 0.0095 <= r <= 0.0105}


def reconcile_daily(daily, vendor, vtick, expected=None, tol=C.PRICE_TOL):
    """Compare derived daily bars with vendor_daily.csv. Vendor tickers are resolved as of the
    vendor's date with the same dimension. Two vendor conventions are handled and documented:
      * the vendor's prices before a split are already split-adjusted (and volume scaled), so
        the derived bars are put on the same basis with adj_factor before comparing;
      * for some securities the vendor volume is in lots of 100 (detected from the data).
    Status per (run, security, day): matched | mismatched | missing_in_vendor | missing_in_derived.
    A mismatch is labelled MISSING_MINUTES when the derived day has fewer bars than expected
    (bars were rejected or never arrived), otherwise VALUE_DIFF."""
    v = vendor.copy()
    v["trading_date"] = pd.to_datetime(v["date"])
    v["security_id"] = attach_security(v, vtick, "ticker", "trading_date")
    v = v.rename(columns={c: c + "_v" for c in ["open", "high", "low", "close", "volume"]})
    d = daily.copy()
    scale = detect_vendor_volume_scale(d, v)
    for c in ["open", "high", "low", "close"]:
        d[c + "_cmp"] = d[c] * d["adj_factor"]
    d["volume_cmp"] = d["volume"] / d["adj_factor"]
    lots = d["security_id"].map(scale).fillna(1)
    d["volume_cmp"] = np.where(lots > 1, (d["volume_cmp"] / lots).round(), d["volume_cmp"].round())
    m = d.merge(v[["run_id", "security_id", "trading_date", "open_v", "high_v", "low_v",
                   "close_v", "volume_v", "source_row"]],
                on=["run_id", "security_id", "trading_date"], how="outer", indicator=True)
    both = m["_merge"] == "both"
    diffs = {f: (m[f + "_cmp"] - m[f + "_v"]).abs() > tol + 1e-9 for f in ["open", "high", "low", "close"]}
    diffs["volume"] = (m["volume_cmp"] - m["volume_v"]).abs() > 0
    dd = pd.DataFrame(diffs)
    bad = dd.any(axis=1)
    m["status"] = np.select([m["_merge"] == "left_only", m["_merge"] == "right_only", both & bad],
                            ["missing_in_vendor", "missing_in_derived", "mismatched"], "matched")
    m["mismatch_fields"] = dd.apply(lambda r: "|".join(k for k, x in r.items() if x), axis=1).where(both & bad, "")
    m["vendor_volume_unit"] = np.where(m["security_id"].map(scale).notna(), "lots_of_100", "shares")
    if expected is not None:
        m = m.merge(expected[["run_id", "security_id", "trading_date", "expected"]],
                    on=["run_id", "security_id", "trading_date"], how="left")
        short = m["n_bars"] < m["expected"]
        m["mismatch_cause"] = np.where(m["status"] != "mismatched", "",
                                       np.where(short, "MISSING_MINUTES", "VALUE_DIFF"))
    return m.drop(columns="_merge")
