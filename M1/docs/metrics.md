# The four Milestone 1 metrics (pandas)

Student: Ahmed Shawky Moubarak (70-40377). Values are in `output/metrics/*.csv` and shown in `notebooks/02_curated_output_and_metrics.ipynb`. Window: 2025-01-02 to 2025-06-30 (123 trading days), known runs RUN-2025A/B/C. All rates are computed with the policies of `data_dictionary.md`.

## 1. Bar completeness (accepted / expected)
Expected = session minutes (390, 210 on 2025-04-17) for every symbol listed that day plus the index, minus the announced halt (GALR 45 min on 2025-02-12). Also per run / symbol / day in `completeness_by_run_symbol_day.csv`.

| Run | Accepted | Expected | Completeness |
|---|---|---|---|
| RUN-2025A | 1,413,522 | 1,414,935 | 99.900% |
| RUN-2025B | 1,413,467 | 1,414,935 | 99.896% |
| RUN-2025C | 1,413,466 | 1,414,935 | 99.896% |

11 of 10,926 symbol-days are below 99% (lowest 93.3%). A missing bar counts as not accepted; a symbol-day with no bars would stay at 0.

## 2. OHLC validity rate
Population: de-duplicated bars of known runs that have all four prices. Valid = low <= open, close <= high and prices > 0.

| Run | Checked | Valid | Rate |
|---|---|---|---|
| RUN-2025A | 1,426,081 | 1,425,654 | 99.970% |
| RUN-2025B | 1,419,737 | 1,419,311 | 99.970% |
| RUN-2025C | 1,414,333 | 1,413,909 | 99.970% |

## 3. Minute-to-daily reconciliation against the vendor
Prices within half a cent, volume exact, on the same basis (split-adjusted JORV, FENM volume in lots).

| Run | Compared | Matched | Mismatched | Missing in vendor | Missing in derived | Match rate |
|---|---|---|---|---|---|---|
| RUN-2025A | 3,612 | 2,448 | 1,164 | 30 | 0 | 67.8% |
| RUN-2025B | 3,605 | 2,415 | 1,190 | 37 | 0 | 67.0% |
| RUN-2025C | 3,614 | 2,413 | 1,201 | 28 | 0 | 66.8% |

98.6% of the mismatches are days with missing minutes (rejected or never delivered); with `--repair` the match rate is 82.4% / 80.6% / 81.4%. The 95 days "missing in vendor" are derived days the vendor file has no row for.

## 4. Rejected-record and late-record rate
Late = more than 60 s after the end of the bar; late bars are accepted and flagged.

| Run | Received | Rejected | Reject rate | Accepted | Late accepted | Late rate |
|---|---|---|---|---|---|---|
| RUN-2025A | 1,431,358 | 17,836 | 1.246% | 1,413,522 | 7,076 | 0.501% |
| RUN-2025B | 1,424,991 | 11,524 | 0.809% | 1,413,467 | 7,059 | 0.499% |
| RUN-2025C | 1,419,566 | 6,100 | 0.430% | 1,413,466 | 7,064 | 0.500% |
| RUN-TEST | 260 | 260 | 100% | 0 | 0 | undefined |
| Known runs | 4,275,915 | 35,460 | 0.829% | 4,240,455 | 21,199 | 0.500% |

Rejects by reason (all runs): OUTSIDE_SESSION 16,764; DUPLICATE_BAR 14,913; INVALID_OHLC 1,272; MISSING_REQUIRED_FIELD 850; INVALID_NUMERIC_RANGE 846; MALFORMED_TIMESTAMP 425; UNKNOWN_SYMBOL 390; UNKNOWN_RUN 260. Total 35,720; canonical 4,240,455; input 4,276,175.
