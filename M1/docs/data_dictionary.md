# Data dictionary and policies (Milestone 1)

Student: Ahmed Shawky Moubarak (70-40377). Team: _fill in_.

## 1. Policies

| Policy | Decision | Why |
|---|---|---|
| **Time convention** | The exchange clock, `America/New_York` (from `exchange_calendar.csv`). Every bar has `bar_start_local` (exchange time) **and** `bar_start_utc`. A bar is labelled with the **start** of its minute and ends one minute later. | The Dataset Description declares the exchange clock as canonical. |
| **Source clocks** | `YYYY-MM-DD HH:MM:SS` = exchange time (RUN-2025A, RUN-2025C). `YYYY-MM-DDTHH:MM:SSZ` = **UTC** (RUN-2025B), converted with the real time-zone rules, so the 9 March daylight-saving change is handled. `received_at` is UTC. `events.json` times carry an explicit offset and are converted. | Found by looking at the clock range of each format (UTC 13:30-20:59 against 09:30-15:59). |
| **Placeholder timestamps** | 159 rows written `DD/MM/YYYY HH:MM` all hold the text `31/03/2025 10:15`. They are rejected as `MALFORMED_TIMESTAMP` (not guessed). | Same text for different dates and prices; the minute cannot be trusted. `received_at` could estimate it, but 21% of those estimated minutes already exist, so it is not safe. |
| **Session** | A bar is inside the session when the calendar day is a trading day and `open <= minute < close` (09:30 inclusive, 16:00 exclusive; 13:00 on the early close 2025-04-17). `minute_of_session` = minutes since the open (0 to 389). | Calendar is the authority; whatever the source says. |
| **Dedup** | Natural key `(run_id, ticker, minute)`; minute is the normalised UTC instant. Keep the copy with the **earliest `received_at`** (ties: lowest source row); the others are `DUPLICATE_BAR`. Dedup is done before the other checks. | Dataset Description, Appendix A. |
| **Symbol resolution** | `ticker` is matched to `security_id` **as of the bar's trading date** with a Type-2 dimension `dim_symbol` built from `symbols.csv` + `symbol_history.csv` (valid_from inclusive, valid_to exclusive). Listing date starts the validity, delisting date (first day no longer listed) ends it. `INDEX` is a special security `INDEX`. A ticker valid on no company that day is `UNKNOWN_SYMBOL`. | The stable key is `security_id`, tickers change (ORBT to ORBX on 2025-03-17). |
| **Reference conflicts** | If `symbols.csv` and the dated history disagree (VALX sector) the **dated history wins**. The repeated SEC009 row is dropped, `Information Technology` is mapped to `Technology`. Of two exports of the same run, the **latest `created_at`** wins. | The history has an effective date; the symbol file only has the end state. |
| **Null policy** | A bar with any null OHLC price, or null run/ticker/ts, is rejected as `MISSING_REQUIRED_FIELD`. Nothing is imputed. Nullable fields in the output: `quality_flags` (empty = no issue). Late-arrival lateness is never null for accepted bars. | A made-up price would corrupt returns and volatility. |
| **Reject reason precedence** | If two reasons apply, the **first in this order** is used: DUPLICATE_BAR, UNKNOWN_SYMBOL, UNKNOWN_RUN, MALFORMED_TIMESTAMP, OUTSIDE_SESSION, INVALID_OHLC, INVALID_NUMERIC_RANGE, MISSING_REQUIRED_FIELD, LATE_BEYOND_WATERMARK, UNPARSEABLE_RECORD, SCHEMA_VIOLATION. `rejects.n_reasons` records how many applied (80 rows had two). | Dataset Description, section 4. |
| **Invalid values** | Strict default = reject. `INVALID_OHLC`: any price <= 0, or not `low <= open,close <= high` (all 1,272 are `high < low`). `INVALID_NUMERIC_RANGE`: volume < 0. A sensitivity run with `--repair` swaps a consistent high/low and flips a negative volume instead; the effect is reported in `output/sensitivity_repair/`. | Strict keeps the OHLC validity metric meaningful. |
| **Late records** | late = `received_at` more than 60 s after the end of the bar. Late bars are **accepted and flagged `LATE`**. `LATE_BEYOND_WATERMARK` is a stream (Milestone 2) reason and is not used. | Appendix A defines late-accepted. |
| **Price comparability** | `adj_factor` = product of split factors for splits **after** the bar's trading date (JORV 2:1 on 2025-04-01 gives 0.5 before that day, 1.0 from that day). `adj_close = close x adj_factor`. Volume is left as delivered. Returns in Milestone 2 use `adj_close`. | Without it the split looks like a -50% return. |
| **Daily bars** | From accepted minute bars of the same run, security and trading day: open = first minute, high = max, low = min, close = last minute, volume = sum. | Source of truth; the vendor file is a second opinion. |
| **Reconciliation** | Match = four prices within half a cent and volume exact, **after** (a) putting derived prices/volume on the vendor's split-adjusted basis for JORV before the split, and (b) comparing `round(volume/100)` for securities whose vendor volume is in lots of 100 (detected by the median ratio, found for FENM). Statuses: `matched`, `mismatched`, `missing_in_vendor`, `missing_in_derived`. A mismatch is `MISSING_MINUTES` if the derived day has fewer bars than expected, else `VALUE_DIFF`. | Found in profiling (P23, P24). |
| **Index** | Kept as a bar series with `security_id = INDEX`; counts in completeness (one extra symbol) and must be excluded by the Milestone 2 cross-sectional averages. | Overview semantics. |

## 2. Canonical bar table `bars_canonical` (output/canonical_bars/run_id=*.parquet, schema `m1`)

| Column | Type | Meaning |
|---|---|---|
| `bar_id` | text, unique | `run_id|security_id|YYYYMMDDTHHMM` (UTC start of the bar) |
| `source_file`, `source_row` | text, int | provenance: file and 0-based row in `bars_1m.parquet` |
| `run_id` | text | simulation run (known runs only) |
| `security_id` | text | resolved with the record valid at the bar's date (`INDEX` for the index) |
| `ticker_as_traded` | text | ticker in the source row |
| `bar_start_local` | timestamp | start of the minute, exchange time |
| `bar_start_utc` | timestamptz | same instant in UTC |
| `trading_date` | date | exchange date |
| `minute_of_session` | int | 0 = 09:30 |
| `open, high, low, close` | double | USD as delivered, after validation |
| `volume` | bigint | shares in the minute (index: total of constituents) |
| `adj_factor`, `adj_close` | double | split factor and adjusted close (rule above) |
| `received_at_utc` | timestamptz | when the export system got the bar |
| `lateness_s` | double | `received_at` minus end of bar, seconds |
| `quality_flags` | text | `LATE`, `TS_CONVERTED_FROM_UTC`, `SPLIT_ADJUSTED`, `INSIDE_HALT_WINDOW` (and `REPAIRED_*` in the repair run), joined with `|` |

## 3. Rejects table `rejects` (output/rejects.parquet, rejects.csv)

| Column | Meaning |
|---|---|
| `run_id, ticker, ts, received_at` | raw values (ts is the raw string) |
| `raw_payload` | JSON of the whole raw record |
| `source_file`, `source_row` | pointer back to the row in `bars_1m.parquet` |
| `reject_reason` | exactly one value of the closed enum |
| `n_reasons` | how many reasons applied |

## 4. Other output tables
`dim_symbol` (Type-2 symbol dimension), `dim_sim_run` (flattened runs, one row per run, `config_flags`), `dim_calendar`, `events_flat`, `daily_bars` (derived), `reconciliation` (one row per run/security/day with status and cause), and the metric tables `metric_m1..m4`.
