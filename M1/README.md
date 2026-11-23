# MarketSim M1: Sources, Containers, Cleaning

Data Engineering (DTSC 103), Winter 2026. Team: _fill in_. Student: Ahmed Shawky Moubarak (70-40377).
This folder is the `M1/` folder of the team repository `<teamname>_fintech`.

## What is here
| Path | What |
|---|---|
| `notebooks/01_reading_and_profiling.ipynb` | reads every file in its own format and profiles it; says what is wrong **before** fixing (problems P01-P26) |
| `notebooks/02_curated_output_and_metrics.ipynb` | reads the curated output and shows the four metrics |
| `marketsim/` | the reusable cleaning module: `readers.py`, `cleaning.py`, `metrics.py`, `load_db.py`, `config.py` |
| `run_pipeline.py` | runs everything: read, clean, canonical + rejects, daily bars, reconciliation, metrics, PostgreSQL load |
| `tests/` | small tests of the cleaning functions |
| `docker-compose.yml`, `Dockerfile`, `sql/schema.sql` | PostgreSQL 16 + Adminer + the pipeline |
| `data/raw/marketsim-pack-v1/` | the pack as delivered (input) |
| `output/` | curated output: `canonical_bars/`, `rejects.parquet/.csv`, dimensions, `daily_bars`, `reconciliation`, `metrics/` |
| `docs/` | `data_dictionary.md` (policies and columns), `data_quality_findings.md`, `metrics.md` |

## Run it from a clean clone
Needs Docker Desktop (Compose v2).
```bash
git clone https://github.com/<owner>/<teamname>_fintech.git
cd <teamname>_fintech/M1
docker compose up --build
```
What happens: PostgreSQL starts, then the `pipeline` container reads `data/raw/marketsim-pack-v1`, writes `output/`, and loads schema `m1` (about 2 to 3 minutes; the container ends with "loaded into PostgreSQL" and exit code 0). Adminer is at http://localhost:8080 (System PostgreSQL, server `postgres`, user `marketsim`, password `marketsim`, database `marketsim`).

Check the load:
```bash
docker compose exec postgres psql -U marketsim -c "select count(*) from m1.bars_canonical"   # 4240455
docker compose exec postgres psql -U marketsim -c "select reject_reason, count(*) from m1.rejects group by 1 order by 2 desc"
```
Stop and remove: `docker compose down -v`.

Without Docker (Python 3.11+):
```bash
pip install -r requirements.txt
python run_pipeline.py --raw data/raw/marketsim-pack-v1 --out output          # files only
python -m pytest tests -q
```
Sensitivity run (repair swapped high/low and negative volume instead of rejecting): add `--repair` and a different `--out`.

## Results in one table (known runs, details in `docs/metrics.md`)
| Metric | RUN-2025A | RUN-2025B | RUN-2025C |
|---|---|---|---|
| Bar completeness | 99.900% | 99.896% | 99.896% |
| OHLC validity rate | 99.970% | 99.970% | 99.970% |
| Minute-to-daily match rate (matched / compared) | 67.8% | 67.0% | 66.8% |
| Rejected rate / late rate | 1.246% / 0.501% | 0.809% / 0.499% | 0.430% / 0.500% |

4,276,175 input rows = 4,240,455 canonical + 35,720 rejects. Nothing is dropped silently (asserted in the pipeline).

## Git rules we follow (Introduction to Git)
Each member commits their own work from their own account. Notebooks have one owner each; shared code lives in `.py` files. No passwords or `.env` are committed. Dataset files are below GitHub's 100 MB limit (the largest is 56 MB).
