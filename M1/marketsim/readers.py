"""Read every file in its own format, with explicit types."""
import json
import pandas as pd
import pyarrow.parquet as pq
from . import config as C

BAR_SCHEMA = {"run_id": "string", "ticker": "string", "ts": "string", "open": "double",
              "high": "double", "low": "double", "close": "double", "volume": "int64",
              "received_at": "timestamp[ms, tz=UTC]"}


def read_bars(raw=None):
    """bars_1m.parquet. The schema is checked against the contract before anything else."""
    raw = raw or C.RAW_DIR
    f = pq.ParquetFile(raw / "bars_1m.parquet")
    got = {fld.name: str(fld.type) for fld in f.schema_arrow}
    if got != BAR_SCHEMA:
        raise ValueError(f"bars_1m.parquet schema differs from the contract: {got}")
    df = f.read().to_pandas()
    df["source_row"] = range(len(df))          # provenance: row number inside the file
    return df


def read_symbols(raw=None):
    raw = raw or C.RAW_DIR
    return pd.read_csv(raw / "symbols.csv", dtype={"shares_outstanding": "Int64"},
                       keep_default_na=False, na_values=[""])


def read_symbol_history(raw=None):
    raw = raw or C.RAW_DIR
    return pd.read_csv(raw / "symbol_history.csv", dtype=str)


def read_calendar(raw=None):
    raw = raw or C.RAW_DIR
    return pd.read_csv(raw / "exchange_calendar.csv", dtype=str)


def read_vendor(raw=None):
    raw = raw or C.RAW_DIR
    v = pd.read_csv(raw / "vendor_daily.csv",
                    dtype={"run_id": str, "date": str, "ticker": str, "volume": "int64"})
    v["source_row"] = range(len(v))
    return v


def read_runs(raw=None):
    """sim_runs.json: nested JSON flattened to one row per exported run."""
    raw = raw or C.RAW_DIR
    with open(raw / "sim_runs.json", encoding="utf-8") as f:
        runs = json.load(f)
    df = pd.json_normalize(runs, sep=".")
    for col in ("parameters.climate.states", "parameters.climate.variance_multiplier",
                "parameters.climate.transition_matrix", "parameters.factors.market_weight"):
        df[col] = df[col].apply(json.dumps)       # keep the lists as JSON text
    df["source_row"] = range(len(df))
    return df


def read_events(raw=None):
    """events.json: flattened. details depends on the type (ratio for split, minutes for halt)."""
    raw = raw or C.RAW_DIR
    with open(raw / "events.json", encoding="utf-8") as f:
        ev = json.load(f)["events"]
    df = pd.json_normalize(ev, sep=".")
    df = df.rename(columns={"security.ticker": "ticker", "details.session": "session",
                            "details.duration_minutes": "duration_minutes",
                            "details.ratio": "ratio"})
    df["source_row"] = range(len(df))
    return df
