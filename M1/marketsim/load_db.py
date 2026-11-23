"""Load the curated outputs into PostgreSQL (schema m1). Connection from PG* environment variables."""
import io, os
from pathlib import Path
import pandas as pd
import psycopg2
from sqlalchemy import create_engine

BARS_COLS = ["bar_id", "source_file", "source_row", "run_id", "security_id", "ticker_as_traded",
             "bar_start_local", "bar_start_utc", "trading_date", "minute_of_session", "open", "high",
             "low", "close", "volume", "adj_factor", "adj_close", "received_at_utc", "lateness_s",
             "quality_flags"]
REJ_COLS = ["run_id", "ticker", "ts", "received_at", "source_row", "reject_reason", "n_reasons",
            "raw_payload", "source_file"]


def dsn():
    e = os.environ.get
    return dict(host=e("PGHOST", "localhost"), port=e("PGPORT", "5432"), user=e("PGUSER", "marketsim"),
                password=e("PGPASSWORD", "marketsim"), dbname=e("PGDATABASE", "marketsim"))


def _copy(cur, table, df, cols, chunk=250_000):
    for i in range(0, len(df), chunk):
        buf = io.StringIO()
        df.iloc[i:i + chunk][cols].to_csv(buf, index=False, header=False, na_rep="")
        buf.seek(0)
        cur.copy_expert(f"COPY {table} ({','.join(cols)}) FROM STDIN WITH (FORMAT csv, NULL '')", buf)


def load_all(out: Path, canonical_dir: Path):
    d = dsn()
    con = psycopg2.connect(**d)
    con.autocommit = True
    cur = con.cursor()
    cur.execute(Path(__file__).resolve().parent.parent.joinpath("sql", "schema.sql").read_text())
    for f in sorted(canonical_dir.glob("*.parquet")):        # one run at a time keeps memory low
        df = pd.read_parquet(f)
        df["bar_start_utc"] = df["bar_start_utc"].dt.strftime("%Y-%m-%d %H:%M:%S+00")
        df["received_at_utc"] = df["received_at_utc"].dt.strftime("%Y-%m-%d %H:%M:%S+00")
        _copy(cur, "m1.bars_canonical", df, BARS_COLS)
    rj = pd.read_parquet(out / "rejects.parquet")
    rj["received_at"] = rj["received_at"].dt.strftime("%Y-%m-%d %H:%M:%S.%f+00")
    _copy(cur, "m1.rejects", rj, REJ_COLS)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_bars_run_sec_date ON m1.bars_canonical (run_id, security_id, trading_date)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_rej_reason ON m1.rejects (run_id, reject_reason)")
    con.close()

    eng = create_engine("postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}".format(**d))
    small = {"dim_symbol": pd.read_csv(out / "dim_symbol.csv"), "dim_sim_run": pd.read_csv(out / "dim_sim_run.csv"),
             "dim_calendar": pd.read_csv(out / "dim_calendar.csv"), "events": pd.read_csv(out / "events_flat.csv"),
             "daily_bars": pd.read_parquet(out / "daily_bars.parquet"),
             "reconciliation": pd.read_parquet(out / "reconciliation.parquet")}
    for f in (out / "metrics").glob("m*.csv"):
        small["metric_" + f.stem] = pd.read_csv(f)
    for name, df in small.items():
        df.to_sql(name, eng, schema="m1", if_exists="replace", index=False)
