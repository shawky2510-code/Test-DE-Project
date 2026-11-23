"""Declared conventions and the closed rejection enum (Dataset Description sections 0 and 4)."""
from pathlib import Path
import os

# Where the pack lives and where outputs go. Both can be changed with environment variables.
RAW_DIR = Path(os.environ.get("MARKETSIM_RAW", "data/raw/marketsim-pack-v1"))
OUT_DIR = Path(os.environ.get("MARKETSIM_OUT", "output"))

# ONE declared time convention: the exchange clock, America/New_York
# (taken from exchange_calendar.csv). UTC is kept next to it.
EXCHANGE_TZ = "America/New_York"

# Closed enum in the order given by the Dataset Description. When two reasons apply
# to the same record, the FIRST one in this list wins (the order is the precedence).
REASONS = [
    "DUPLICATE_BAR", "UNKNOWN_SYMBOL", "UNKNOWN_RUN", "MALFORMED_TIMESTAMP",
    "OUTSIDE_SESSION", "INVALID_OHLC", "INVALID_NUMERIC_RANGE",
    "MISSING_REQUIRED_FIELD", "LATE_BEYOND_WATERMARK", "UNPARSEABLE_RECORD",
    "SCHEMA_VIOLATION",
]

INDEX_TICKER = "INDEX"
INDEX_SECURITY_ID = "INDEX"
LATE_SECONDS = 60          # late = received_at more than 60 s after the end of the bar
PRICE_TOL = 0.005          # reconciliation: prices within half a cent
