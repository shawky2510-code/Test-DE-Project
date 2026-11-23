-- Milestone 1 warehouse tables. The big tables are created here; the small ones are created by pandas.
CREATE SCHEMA IF NOT EXISTS m1;

DROP TABLE IF EXISTS m1.bars_canonical;
CREATE TABLE m1.bars_canonical (
    bar_id            text PRIMARY KEY,         -- run_id|security_id|bar start (UTC)
    source_file       text NOT NULL,
    source_row        integer NOT NULL,          -- row number in bars_1m.parquet (0-based)
    run_id            text NOT NULL,
    security_id       text NOT NULL,
    ticker_as_traded  text NOT NULL,
    bar_start_local   timestamp NOT NULL,        -- exchange time, America/New_York
    bar_start_utc     timestamptz NOT NULL,
    trading_date      date NOT NULL,
    minute_of_session integer NOT NULL,          -- 0 = first minute of the session
    open              double precision NOT NULL,
    high              double precision NOT NULL,
    low               double precision NOT NULL,
    close             double precision NOT NULL,
    volume            bigint NOT NULL,
    adj_factor        double precision NOT NULL, -- price factor from splits (before split date)
    adj_close         double precision NOT NULL,
    received_at_utc   timestamptz NOT NULL,
    lateness_s        double precision NOT NULL,
    quality_flags     text                       -- pipe separated, NULL when clean
);

DROP TABLE IF EXISTS m1.rejects;
CREATE TABLE m1.rejects (
    run_id        text,
    ticker        text,
    ts            text,
    received_at   timestamptz,
    source_row    integer NOT NULL,
    reject_reason text NOT NULL CHECK (reject_reason IN (
        'DUPLICATE_BAR','UNKNOWN_SYMBOL','UNKNOWN_RUN','MALFORMED_TIMESTAMP','OUTSIDE_SESSION',
        'INVALID_OHLC','INVALID_NUMERIC_RANGE','MISSING_REQUIRED_FIELD','LATE_BEYOND_WATERMARK',
        'UNPARSEABLE_RECORD','SCHEMA_VIOLATION')),
    n_reasons     integer,                       -- how many reasons applied (the first in the enum order is kept)
    raw_payload   text,
    source_file   text NOT NULL
);
