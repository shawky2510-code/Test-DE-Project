"""End-to-end Milestone 1 pipeline.  python run_pipeline.py [--raw DIR] [--out DIR] [--load-db]"""
import argparse, json, time
from pathlib import Path
import pandas as pd
from marketsim import config as C, readers as R, cleaning as K, metrics as M


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(C.RAW_DIR)); ap.add_argument("--out", default=str(C.OUT_DIR))
    ap.add_argument("--load-db", action="store_true")
    ap.add_argument("--repair", action="store_true", help="sensitivity run: repair swapped high/low and negative volume instead of rejecting")
    a = ap.parse_args()
    raw, out = Path(a.raw), Path(a.out)
    (out / "canonical_bars").mkdir(parents=True, exist_ok=True)
    (out / "metrics").mkdir(exist_ok=True)
    t0 = time.time()
    log = lambda m: print(f"[{time.time()-t0:6.1f}s] {m}", flush=True)

    # 1. read every file in its own format
    bars = R.read_bars(raw); log(f"bars_1m.parquet: {len(bars):,} rows")
    symbols_raw = R.read_symbols(raw); history = R.read_symbol_history(raw)
    calendar = K.clean_calendar(R.read_calendar(raw))
    runs_raw = R.read_runs(raw); vendor = R.read_vendor(raw); events_raw = R.read_events(raw)

    # 2. reference data
    symbols, sym_removed = K.clean_symbols(symbols_raw)
    dim_symbol = K.build_dim_symbol(symbols, history)
    vtick = K.ticker_validity(dim_symbol)
    runs, runs_removed = K.clean_runs(runs_raw)
    events = K.clean_events(events_raw, vtick)
    refs = dict(calendar=calendar, runs=runs, vtick=vtick, events=events)

    # 3. clean bars
    canonical, rejects = K.clean_bars(bars, refs, repair=a.repair)
    assert len(canonical) + len(rejects) == len(bars), "a record was silently dropped"
    assert rejects.reject_reason.isin(C.REASONS).all()
    log(f"canonical {len(canonical):,}  rejects {len(rejects):,}")

    # 4. daily bars + reconciliation
    daily = K.derive_daily(canonical)
    # 5. metrics
    expected = M.expected_bars(runs, symbols, calendar, events, dim_symbol)
    rec = K.reconcile_daily(daily, vendor, vtick, expected)
    comp, comp_run = M.completeness(canonical, expected)
    dedup_bars = bars.loc[~bars.index.isin(rejects[rejects.reject_reason == "DUPLICATE_BAR"].source_row)]
    known = dedup_bars[dedup_bars.run_id.isin(runs.run_id)]
    ohlc = M.ohlc_validity(known)
    recs = M.reconciliation_summary(rec)
    rl = M.reject_and_late(bars.groupby("run_id").size(), canonical, rejects)

    # 6. write outputs
    for rid, g in canonical.groupby("run_id"):
        g.to_parquet(out / "canonical_bars" / f"run_id={rid}.parquet", compression="zstd", index=False)
    rejects.to_parquet(out / "rejects.parquet", compression="zstd", index=False)
    rejects.drop(columns=["n_reasons"]).to_csv(out / "rejects.csv", index=False)
    dim_symbol.to_csv(out / "dim_symbol.csv", index=False)
    runs.drop(columns=["source_row"]).to_csv(out / "dim_sim_run.csv", index=False)
    calendar.to_csv(out / "dim_calendar.csv", index=False)
    events.drop(columns=["source_row"]).to_csv(out / "events_flat.csv", index=False)
    daily.to_parquet(out / "daily_bars.parquet", compression="zstd", index=False)
    rec.to_parquet(out / "reconciliation.parquet", compression="zstd", index=False)
    rec[rec.status != "matched"].to_csv(out / "reconciliation_exceptions.csv", index=False)
    comp.to_csv(out / "metrics" / "completeness_by_run_symbol_day.csv", index=False)
    comp_run.to_csv(out / "metrics" / "m1_completeness_by_run.csv")
    ohlc.to_csv(out / "metrics" / "m2_ohlc_validity_by_run.csv")
    recs.to_csv(out / "metrics" / "m3_reconciliation_by_run.csv")
    rl.to_csv(out / "metrics" / "m4_reject_late_by_run.csv")
    pd.crosstab(rejects.run_id, rejects.reject_reason).to_csv(out / "metrics" / "rejects_by_run_reason.csv")
    log("outputs written")

    if a.load_db:
        from marketsim import load_db
        load_db.load_all(out, canonical_dir=out / "canonical_bars")
        log("loaded into PostgreSQL")


if __name__ == "__main__":
    main()
