"""SQLite storage for screener run results and the ticker watchlist.

I keep the database at data/screener.db, which is already gitignored via
data/* — nothing here ever needs to touch git.
"""
import datetime
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

-- A company's sector classification effectively never changes, so this
-- is cached across runs rather than re-fetched per ticker per scan. That
-- one call per ticker dominates the API budget once the universe is wide.
CREATE TABLE IF NOT EXISTS sector_cache (
    ticker TEXT PRIMARY KEY,
    sector TEXT,
    fetched_date TEXT NOT NULL
);

-- The tradable-instrument universe, refreshed on a TTL. Listings change
-- slowly, so re-paginating 20k instruments on every run is wasteful.
CREATE TABLE IF NOT EXISTS universe_cache (
    symbol TEXT PRIMARY KEY,
    name TEXT,
    exchange_code TEXT,
    status TEXT,
    fetched_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backtest_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    as_of_date TEXT NOT NULL,
    entry_date TEXT NOT NULL,
    entry_price REAL,
    exit_date TEXT,
    exit_price REAL,
    exit_reason TEXT,
    return_pct REAL,
    r_multiple REAL,
    conditions_met INTEGER,
    parameter_set TEXT,
    still_open BOOLEAN
);
"""

RESULT_COLUMNS = [
    "ticker", "run_date", "stage", "price", "ma_30w", "price_above_ma",
    "ma_rising", "mansfield_rs", "rs_improving", "volume_ratio",
    "volume_confirmed", "sector", "sector_strength_pct", "market_stage_ok",
    "resistance_level", "breakout_confirmed", "swing_target", "swing_stop",
    "conditions_met", "conditions_detail", "notes",
]

BACKTEST_TRADE_COLUMNS = [
    "ticker", "as_of_date", "entry_date", "entry_price", "exit_date",
    "exit_price", "exit_reason", "return_pct", "r_multiple",
    "conditions_met", "parameter_set", "still_open",
]


# Which DB path the schema has already been applied to in this process.
# Keyed on the path rather than a plain boolean so that pointing DB_PATH
# at a different file — which the tests do — still gets its schema.
_schema_ready_for = None


def _connect():
    """Opens a connection, ensuring the schema exists first.

    Callers used to have to remember init_db() before touching anything,
    which was fine while the only readers were the screener's own entry
    points and became a trap as soon as data_fetch started consulting the
    sector cache: a missing table surfaces as an opaque OperationalError
    from somewhere unrelated. CREATE TABLE IF NOT EXISTS is cheap and
    idempotent, so there's no reason to make correctness depend on call
    ordering.
    """
    global _schema_ready_for
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    if _schema_ready_for != DB_PATH:
        conn.executescript(SCHEMA)
        conn.commit()
        _schema_ready_for = DB_PATH
    return conn


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


SECTOR_CACHE_TTL_DAYS = 90
UNIVERSE_CACHE_TTL_DAYS = 7


def _is_fresh(fetched_date, ttl_days):
    try:
        age = (datetime.date.today() - datetime.date.fromisoformat(fetched_date)).days
    except (TypeError, ValueError):
        return False
    return age < ttl_days


def get_cached_sector(ticker):
    """Returns {"sector": ...} if a fresh cached classification exists,
    else None. A None sector is itself a valid cached answer — ETFs
    genuinely have no industry — so absence has to be distinguished from
    a cached null, which is why this returns a dict rather than the bare
    value.
    """
    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT sector, fetched_date FROM sector_cache WHERE ticker = ?", (ticker,)
        ).fetchone()
    finally:
        conn.close()

    if row is None or not _is_fresh(row["fetched_date"], SECTOR_CACHE_TTL_DAYS):
        return None
    return {"sector": row["sector"]}


def cache_sector(ticker, sector):
    conn = _connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO sector_cache (ticker, sector, fetched_date) VALUES (?, ?, ?)",
            (ticker, sector, datetime.date.today().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def get_cached_universe():
    """The cached tradable universe, or None when absent or stale."""
    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM universe_cache ORDER BY symbol").fetchall()
    finally:
        conn.close()

    if not rows or not _is_fresh(rows[0]["fetched_date"], UNIVERSE_CACHE_TTL_DAYS):
        return None
    return [dict(r) for r in rows]


def cache_universe(instruments):
    """Replaces the cached universe wholesale — a partial refresh would
    leave delisted names behind.
    """
    today = datetime.date.today().isoformat()
    conn = _connect()
    try:
        conn.execute("DELETE FROM universe_cache")
        conn.executemany(
            "INSERT OR REPLACE INTO universe_cache (symbol, name, exchange_code, status, fetched_date) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (i.get("symbol"), i.get("name"), i.get("exchange_code"), i.get("status"), today)
                for i in instruments
                if i.get("symbol")
            ],
        )
        conn.commit()
    finally:
        conn.close()


def insert_backtest_trade(trade):
    """I insert one simulated trade from backtest.py. Unknown keys in
    `trade` beyond BACKTEST_TRADE_COLUMNS are ignored, same filtering
    approach as insert_result.
    """
    conn = _connect()
    try:
        columns = [c for c in BACKTEST_TRADE_COLUMNS if c in trade]
        placeholders = ", ".join("?" for _ in columns)
        conn.execute(
            f"INSERT INTO backtest_trades ({', '.join(columns)}) VALUES ({placeholders})",
            [trade[c] for c in columns],
        )
        conn.commit()
    finally:
        conn.close()


def get_backtest_trades(parameter_set=None):
    """I return backtest_trades rows, optionally filtered to one
    parameter_set, oldest as_of_date first.
    """
    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        if parameter_set is None:
            rows = conn.execute(
                "SELECT * FROM backtest_trades ORDER BY parameter_set, as_of_date"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM backtest_trades WHERE parameter_set = ? ORDER BY as_of_date",
                (parameter_set,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
