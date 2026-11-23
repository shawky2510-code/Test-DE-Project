# Data-quality findings (Milestone 1)

Student: Ahmed Shawky Moubarak (70-40377). Every number below comes from `notebooks/01_reading_and_profiling.ipynb` and the pipeline output. "Detected" says how it was found.

| # | File | Problem | Detected by | Decision |
|---|---|---|---|---|
| P01 | symbols.csv | `SEC009` appears twice (`istk`, `ISTON THERAPEUTICS`) | `security_id` is not unique (31 rows, 30 ids) | keep the first row, drop the repeat |
| P02 | symbols.csv | Sector `Information Technology` (MARB) next to `Technology` | `value_counts` of sector | map to `Technology` |
| P03 | symbols / history | symbols.csv says VALX is `Energy` but history says it became `Technology` on 2025-05-01 | compared the end-state file with the dated history | dated history wins; two dimension rows for SEC022 |
| P04 | sim_runs.json | `RUN-2025B` exported twice (created 07-02 and 07-03) | `run_id` not unique after flattening | keep the latest `created_at` |
| P05 | sim_runs.json | `RUN-2025C` has `sigma_annual = 18.0` (others 0.18) | compared parameters per run | flag `SIGMA_ANNUAL_LOOKS_LIKE_PERCENT`, store 0.18 as `sigma_annual_clean` |
| P06 | events.json | Events use `ORBT` (old ticker); times carry -05:00 / -04:00 | ticker not in symbols.csv; offsets | resolve ticker as of the event date; convert times to exchange time |
| P07 | bars | `RUN-TEST` (260 rows) is not in sim_runs.json | run ids vs sim_runs | `UNKNOWN_RUN` (260) |
| P08 | bars | `ZZZT` (392 rows, RUN-2025A, one day) is not a company | tickers vs symbols | `UNKNOWN_SYMBOL` (390; 2 rows had an earlier reason) |
| P09 | bars | **Three clocks:** RUN-2025B `ts` is UTC with `Z` (13:25-20:59), the others exchange time | pattern of each `ts` format and the hour range | normalise with real tz rules (DST on 9 March handled); keep both local and UTC |
| P10 | bars | 159 rows `DD/MM/YYYY` all equal to `31/03/2025 10:15`; ARVT close 134 / 107 / 112 | one repeated string with prices from different months | `MALFORMED_TIMESTAMP` (not guessed) |
| P11 | bars | 266 other invalid timestamps: `not-a-time` (115) and the impossible `2025-02-30 10:00:00` (151) | regex and parse failure | `MALFORMED_TIMESTAMP` |
| P12 | bars | RUN-2025A has 11,346 bars on the holiday 2025-01-20 | bar date vs calendar | `OUTSIDE_SESSION` |
| P13 | bars | RUN-2025B keeps trading after the 13:00 early close on 2025-04-17 (5,415 bars) | minute vs session_close | `OUTSIDE_SESSION` |
| P14 | bars | 60 bars (20 per run) at 09:25-09:29, before the open | minute vs session_open | `OUTSIDE_SESSION` |
| P15 | bars | 14,913 extra copies of a (run, ticker, minute); the second copy arrives 5-600 s later; in 2,130 keys the close differs | duplicated natural key | keep earliest `received_at`; others `DUPLICATE_BAR` |
| P16 | bars | 854 null `close` | null rates | `MISSING_REQUIRED_FIELD` (850 after precedence) |
| P17 | bars | 1,282 bars with `high < low` | OHLC rule | `INVALID_OHLC` (1,272 after precedence). All could be repaired by swapping high/low, kept as a `--repair` sensitivity run |
| P18 | bars | 853 negative volumes (min -47,568) | range check | `INVALID_NUMERIC_RANGE` (846 after precedence). Sign flip is plausible; see sensitivity |
| P19 | bars | 21,199 accepted bars arrive more than 60 s late (0.5% of accepted) | `received_at` minus end of bar; 99.5% of accepted bars arrive within 2 s; every late bar is at least 120 s late (max 1,802 s) | accepted, flag `LATE` |
| P20 | bars | JORV close falls from ~387 to ~192 on 2025-04-01 (2:1 split in events.json) | event + price series | `adj_factor` 0.5 before the split, `adj_close` |
| P21 | bars | Bars per symbol-day wander (gaps and repeats): ARVT in RUN-2025A has 214 to 398 bars a day, and over all symbol-days the minimum is 209 (an early-close day) | counts per day | expected bars from the calendar; completeness metric |
| P22 | symbols | CELK and DOVV list in 2025; YARL delisted 2025-04-30; ORBT/ORBX rename | listing/delisting columns, history | expected bars follow the listing window; symbol as of date |
| P23 | vendor | Vendor JORV prices before the split are already split-adjusted (x0.5, volume x2) | ratio vendor / derived = 0.5 | compare on the same basis |
| P24 | vendor | Vendor `FENM` volume is 1/100 of the minute volume (round lots) | ratio = 0.010 | compare `round(volume/100)` for securities detected this way |
| P25 | vendor | 49 days still differ with all minutes present: 24 on 2025-04-17 in RUN-2025B (vendor includes bars after the early close) and 25 vendor closes 1-5 cents from the last minute's close | residual after P23/P24 | derived daily bar is trusted; reported as `VALUE_DIFF` |
| P26 | vendor | Vendor rows for `INDEX` and the old ticker `ORBT` | tickers not in symbols.csv | resolve with the same as-of dimension |

## What the mismatches in the reconciliation really are
Of 3,555 mismatched days, 3,506 (98.6%) are `MISSING_MINUTES`: our derived day has fewer than the expected bars because bars were rejected or never arrived, so the volume cannot be equal to the vendor's full-day volume. If swapped high/low and negative volumes are repaired instead of rejected (`--repair`), the match rate rises from 66.8-67.8% to 80.6-82.4% per run, which supports the repairs as correct and shows how much the policy matters.

## Things I did not do on purpose
* No price or volume was imputed.
* The held-out files `stream_bars.json` and `regime_labels.csv` are not read by the pipeline.
* The 31/03 placeholder rows were not "recovered" from `received_at`.
