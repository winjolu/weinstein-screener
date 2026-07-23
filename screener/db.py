"""SQLite storage for screener run results and the ticker watchlist.

I keep the database at data/screener.db, which is already gitignored via
data/* — nothing here ever needs to touch git.
"""
import json
import os
import sqlite3

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "screener.db"
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS screener_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    run_date TEXT NOT NULL,
    stage INTEGER,
    price REAL,
    ma_30w REAL,
    price_above_ma BOOLEAN,
    ma_rising BOOLEAN,
    mansfield_rs REAL,
    rs_improving BOOLEAN,
    volume_ratio REAL,
    volume_confirmed BOOLEAN,
    sector TEXT,
    sector_strength_pct REAL,
    market_stage_ok BOOLEAN,
    resistance_level REAL,
    breakout_confirmed BOOLEAN,
    swing_target REAL,
    swing_stop REAL,
    conditions_met INTEGER,
    conditions_detail TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS tickers_watchlist (
    ticker TEXT PRIMARY KEY,
    added_date TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT 1
);
"""

RESULT_COLUMNS = [
    "ticker", "run_date", "stage", "price", "ma_30w", "price_above_ma",
    "ma_rising", "mansfield_rs", "rs_improving", "volume_ratio",
    "volume_confirmed", "sector", "sector_strength_pct", "market_stage_ok",
    "resistance_level", "breakout_confirmed", "swing_target", "swing_stop",
    "conditions_met", "conditions_detail", "notes",
]


def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db():
    """I create the database file and both tables if they don't exist yet."""
    conn = _connect()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def seed_watchlist_from_config(tickers, run_date):
    """I load tickers into tickers_watchlist on first run.

    Existing rows are left alone — this only inserts tickers that aren't
    already tracked, so it's safe to call on every run.
    """
    conn = _connect()
    try:
        for ticker in tickers:
            conn.execute(
                "INSERT OR IGNORE INTO tickers_watchlist (ticker, added_date, active) "
                "VALUES (?, ?, 1)",
                (ticker, run_date),
            )
        conn.commit()
    finally:
        conn.close()


def insert_result(result):
    """I insert one ticker's screener result.

    `conditions_detail` gets JSON-encoded automatically if it's passed in
    as a dict rather than an already-serialized string.
    """
    row = dict(result)
    if isinstance(row.get("conditions_detail"), (dict, list)):
        row["conditions_detail"] = json.dumps(row["conditions_detail"])

    conn = _connect()
    try:
        columns = [c for c in RESULT_COLUMNS if c in row]
        placeholders = ", ".join("?" for _ in columns)
        conn.execute(
            f"INSERT INTO screener_results ({', '.join(columns)}) VALUES ({placeholders})",
            [row[c] for c in columns],
        )
        conn.commit()
    finally:
        conn.close()


def get_latest_results():
    """I return every screener_results row from the most recent run_date."""
    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        latest = conn.execute("SELECT MAX(run_date) FROM screener_results").fetchone()[0]
        if latest is None:
            return []
        rows = conn.execute(
            "SELECT * FROM screener_results WHERE run_date = ? ORDER BY ticker",
            (latest,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_ticker_history(ticker, weeks_back):
    """I return a ticker's most recent `weeks_back` screener_results rows, oldest first."""
    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM screener_results WHERE ticker = ? ORDER BY run_date DESC LIMIT ?",
            (ticker, weeks_back),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]
    finally:
        conn.close()
