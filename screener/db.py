"""SQLite storage for screener run results and the ticker watchlist.

The database lives in application support, not under the project. It was
at data/screener.db until a 200MB file rewritten thousands of times per
backtest met the sync client watching that folder. SCREENER_DB overrides
the location; merge_backtest_trades brings a side database home.
"""
import datetime
import json
import os
import sqlite3

def _default_db_path():
    """Application support, not the project directory.

    It used to live at data/screener.db, which put a 200MB database that
    is rewritten thousands of times per backtest inside a folder Google
    Drive continuously uploads. That cost a four-hour run to a lock
    timeout and roughly tripled every arm's runtime.

    Falls back to the old location if application support cannot be
    created, because a screener that refuses to start over a directory
    is worse than one writing somewhere imperfect.
    """
    home = os.path.expanduser("~")
    candidate = os.path.join(home, "Library", "Application Support",
                             "weinstein-screener")
    try:
        os.makedirs(candidate, exist_ok=True)
        return os.path.join(candidate, "screener.db")
    except OSError:
        return os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "screener.db")


# SCREENER_DB overrides, which is what a long backtest uses to write to
# its own file and merge afterwards — two arms sharing one database has
# already killed a run.
DB_PATH = os.environ.get("SCREENER_DB") or _default_db_path()

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
    is_fund BOOLEAN NOT NULL DEFAULT 0,
    security_type TEXT,
    fetched_date TEXT NOT NULL
);

-- Who actually owns a ticker, and since when. Tickers get recycled: GM
-- today is the company incorporated in 2009, not the one that went
-- bankrupt, and CC is Chemours rather than Circuit City. Webull resolves
-- a symbol to whoever holds it now, so bars predating the current
-- holder's existence belong to somebody else entirely.
--
-- SEC's CIK is the stable identifier a ticker isn't — it is assigned per
-- filer and never recycled. first_filing_date is the cutoff: cached bars
-- older than it are a different company and have to be trimmed.
--
-- Cached because this needs one request per symbol against EDGAR and
-- almost never changes.
CREATE TABLE IF NOT EXISTS security_identity (
    ticker TEXT PRIMARY KEY,
    cik INTEGER,
    company_name TEXT,
    first_filing_date TEXT,
    former_names TEXT,
    delisted_date TEXT,
    delisting_form TEXT,
    fetched_date TEXT NOT NULL
);

-- Mined features for each signal, one row per (ticker, entry_date, run).
-- Deliberately NOT a rebuildable cache: regenerating these means walking
-- the whole universe again, and the first version of this data lived in
-- a scratch file that would have been deleted with the session. Losing
-- it would have cost hours of compute and, worse, silently removed the
-- only thing capable of ranking signals by anything finer than a count.
--
-- Stored as a JSON blob rather than fixed columns because the feature
-- set grows every time a new idea gets tested, and a schema migration
-- per idea is how measuring things stops happening.
CREATE TABLE IF NOT EXISTS signal_features (
    ticker TEXT NOT NULL,
    entry_date TEXT NOT NULL,
    parameter_set TEXT NOT NULL,
    features TEXT NOT NULL,
    return_pct REAL,
    PRIMARY KEY (ticker, entry_date, parameter_set)
);

-- Exactly which symbols a given backtest window ran over. Without this a
-- result cannot be reproduced, only re-approximated — the universe is an
-- input to every figure recorded and it was living in a temp file.
CREATE TABLE IF NOT EXISTS universe_snapshot (
    name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    created_date TEXT NOT NULL,
    PRIMARY KEY (name, symbol)
);

-- Every delisting notice filed with the SEC, from the quarterly form
-- indexes. Form 25/25-NSE is the removal notice; Form 15 is
-- deregistration and comes later, so the two are kept apart rather than
-- collapsed into "gone".
--
-- This measures the survivorship hole rather than filling it: EDGAR
-- knows which companies left and when, and has none of their prices.
-- Whether the hole is worth paying a vendor to fill is what this
-- answers, before paying.
CREATE TABLE IF NOT EXISTS delisting_events (
    cik INTEGER NOT NULL,
    company_name TEXT,
    form TEXT NOT NULL,
    filed_date TEXT NOT NULL,
    PRIMARY KEY (cik, form, filed_date)
);

-- What the system suggested, and what was actually done about it.
--
-- The only forward evidence this project will ever produce. Everything
-- in docs/ is a backtest over history I have already read, on an engine
-- whose defects keep surfacing. A row written before the outcome is
-- known cannot be tuned after the fact.
--
-- Suggestions NOT acted on are kept deliberately: a log of only the
-- trades taken measures my judgement as much as the system's,
-- and the gap between them is the interesting part.
CREATE TABLE IF NOT EXISTS recommendations (
    ticker TEXT NOT NULL,
    suggested_on TEXT NOT NULL,
    action TEXT NOT NULL,
    shares REAL,
    price REAL,
    stop REAL,
    rationale TEXT,
    taken TEXT,
    taken_note TEXT,
    PRIMARY KEY (ticker, suggested_on, action)
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

# Cache tables get rebuilt rather than migrated when their shape changes.
# They hold nothing that can't be re-fetched, so dropping is cheaper and
# far less error-prone than an ALTER path that has to know every previous
# version of the table. Anything holding real history — screener_results,
# backtest_trades — is deliberately absent from this list and would need
# a proper migration.
_REBUILDABLE_CACHE_COLUMNS = {
    "universe_cache": {"symbol", "name", "exchange_code", "status", "is_fund",
                       "security_type", "fetched_date"},
    "sector_cache": {"ticker", "sector", "fetched_date"},
    "security_identity": {"ticker", "cik", "company_name", "first_filing_date",
                          "former_names", "delisted_date", "delisting_form",
                          "fetched_date"},
}


def _rebuild_stale_cache_tables(conn):
    for table, expected in _REBUILDABLE_CACHE_COLUMNS.items():
        existing = conn.execute(f"PRAGMA table_info({table})").fetchall()
        if not existing:
            continue  # first run; CREATE TABLE will handle it
        if {row[1] for row in existing} != expected:
            conn.execute(f"DROP TABLE {table}")


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
    # Sixty seconds rather than the five Python defaults to. Two backtest
    # arms running at once lost one of them outright: a six-band sweep
    # died on "database is locked" in its final band, after four hours,
    # having written five bands I could still use and a sixth I had to
    # throw away. This database also lives inside a synced folder, so a
    # write can block on the sync client rather than on the other writer,
    # and five seconds is well inside what that costs. Waiting a minute
    # is always cheaper than losing the run.
    conn = sqlite3.connect(DB_PATH, timeout=60.0)
    if _schema_ready_for != DB_PATH:
        _rebuild_stale_cache_tables(conn)
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
        # One row per ticker per run date. Re-running a scan the same day
        # used to append rather than replace, so a second pass left two
        # rows for every ticker and get_latest_results returned both —
        # measured at 651 rows across 334 tickers, which would silently
        # double-count in anything reading the history back.
        conn.execute(
            "DELETE FROM screener_results WHERE ticker = ? AND run_date = ?",
            (row.get("ticker"), row.get("run_date")),
        )
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


def get_run_dates(limit=None):
    """Scan dates, newest first."""
    conn = _connect()
    try:
        sql = "SELECT DISTINCT run_date FROM screener_results ORDER BY run_date DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [row[0] for row in conn.execute(sql).fetchall()]
    finally:
        conn.close()


def get_results_for_run(run_date):
    """Every row from one scan."""
    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM screener_results WHERE run_date = ? ORDER BY ticker", (run_date,)
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
# A company's first filing date never changes and its CIK never changes.
# Only the delisting fields can move, and a security that delists stays
# delisted, so this is refreshed on a long cycle rather than a short one.
IDENTITY_CACHE_TTL_DAYS = 180


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


def save_recommendation(row):
    """Record a suggestion. Replaces on the same ticker/date/action so a
    re-run of the same day corrects rather than duplicates."""
    conn=_connect()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO recommendations
               (ticker, suggested_on, action, shares, price, stop, rationale,
                taken, taken_note)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (row["ticker"], row["suggested_on"], row["action"], row.get("shares"),
             row.get("price"), row.get("stop"), row.get("rationale"),
             row.get("taken"), row.get("taken_note")))
        conn.commit()
    finally:
        conn.close()


def update_recommendation(ticker, suggested_on, taken, note=None):
    """Record what was done about a suggestion. `taken` is stored as text
    so "bought half" and "waited a week" survive as themselves rather
    than being flattened into yes or no."""
    conn=_connect()
    try:
        conn.execute(
            """UPDATE recommendations SET taken = ?, taken_note = ?
               WHERE ticker = ? AND suggested_on = ?""",
            (str(taken), note, ticker, suggested_on))
        conn.commit()
    finally:
        conn.close()


def get_recommendations(ticker=None):
    conn=_connect(); conn.row_factory=sqlite3.Row
    try:
        if ticker:
            rows=conn.execute(
                "SELECT * FROM recommendations WHERE ticker = ? ORDER BY suggested_on",
                (ticker,)).fetchall()
        else:
            rows=conn.execute(
                "SELECT * FROM recommendations ORDER BY suggested_on").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def save_delisting_events(rows):
    """Bulk-write delisting notices. Idempotent on (cik, form, date), so
    re-running a quarter corrects rather than duplicates."""
    conn=_connect()
    try:
        conn.executemany(
            """INSERT OR REPLACE INTO delisting_events
               (cik, company_name, form, filed_date) VALUES (?, ?, ?, ?)""",
            [(r["cik"], r.get("company_name"), r["form"], r["filed_date"])
             for r in rows])
        conn.commit()
    finally:
        conn.close()
    return len(rows)


def get_delisting_events(start=None, end=None):
    """Delisting notices, optionally bounded by filing date."""
    conn=_connect(); conn.row_factory=sqlite3.Row
    try:
        q="SELECT * FROM delisting_events WHERE 1=1"; args=[]
        if start: q+=" AND filed_date >= ?"; args.append(start)
        if end:   q+=" AND filed_date <= ?"; args.append(end)
        return [dict(r) for r in conn.execute(q, args)]
    finally:
        conn.close()


def save_signal_features(rows, parameter_set):
    """Persist mined per-signal features.

    `rows` are dicts holding at least ticker and entry_date; everything
    else is kept as the feature blob. Anything already stored for the
    same key is replaced, so a re-mine corrects rather than duplicates.
    """
    payload = []
    for row in rows:
        features = {k: v for k, v in row.items()
                    if k not in ("ticker", "entry_date", "return_pct")}
        payload.append((row["ticker"], row["entry_date"], parameter_set,
                        json.dumps(features), row.get("return_pct")))
    conn = _connect()
    try:
        conn.executemany(
            """INSERT OR REPLACE INTO signal_features
               (ticker, entry_date, parameter_set, features, return_pct)
               VALUES (?, ?, ?, ?, ?)""", payload)
        conn.commit()
    finally:
        conn.close()
    return len(payload)


def get_signal_features(parameter_set=None):
    """Mined features, flattened back into one dict per signal."""
    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        if parameter_set:
            rows = conn.execute(
                "SELECT * FROM signal_features WHERE parameter_set = ?",
                (parameter_set,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM signal_features").fetchall()
    finally:
        conn.close()
    out = []
    for row in rows:
        record = json.loads(row["features"])
        record.update(ticker=row["ticker"], entry_date=row["entry_date"],
                      return_pct=row["return_pct"],
                      parameter_set=row["parameter_set"])
        out.append(record)
    return out


def save_universe_snapshot(name, symbols):
    """Record exactly which symbols a named universe contained."""
    today = datetime.date.today().isoformat()
    conn = _connect()
    try:
        conn.execute("DELETE FROM universe_snapshot WHERE name = ?", (name,))
        conn.executemany(
            "INSERT INTO universe_snapshot (name, symbol, created_date) VALUES (?, ?, ?)",
            [(name, s, today) for s in sorted(set(symbols))])
        conn.commit()
    finally:
        conn.close()


def get_universe_snapshot(name):
    """The symbols of a named universe, or [] if never recorded."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT symbol FROM universe_snapshot WHERE name = ? ORDER BY symbol",
            (name,)).fetchall()
    finally:
        conn.close()
    return [r[0] for r in rows]


def get_cached_identity(ticker):
    """Who owns this ticker, from cache, or None when absent or stale.

    Returns a dict rather than the bare CIK because a null CIK is a valid
    cached answer — plenty of tradable symbols have no SEC filer behind
    them at all, ETFs and foreign issues among them — and "we looked and
    there is nobody" has to be distinguishable from "we never looked".
    """
    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM security_identity WHERE ticker = ?", (ticker,)
        ).fetchone()
    finally:
        conn.close()

    if row is None or not _is_fresh(row["fetched_date"], IDENTITY_CACHE_TTL_DAYS):
        return None
    return _identity_row_to_dict(row)


def _identity_row_to_dict(row):
    return {
        "ticker": row["ticker"],
        "cik": row["cik"],
        "company_name": row["company_name"],
        "first_filing_date": row["first_filing_date"],
        "former_names": json.loads(row["former_names"]) if row["former_names"] else [],
        "delisted_date": row["delisted_date"],
        "delisting_form": row["delisting_form"],
    }


def cache_identities(identities):
    """Writes many identities in one transaction.

    Bulk because resolving the universe is thousands of symbols, and a
    commit per row turned the equivalent universe write into the slowest
    part of a run.
    """
    today = datetime.date.today().isoformat()
    conn = _connect()
    try:
        conn.executemany(
            """INSERT OR REPLACE INTO security_identity
               (ticker, cik, company_name, first_filing_date, former_names,
                delisted_date, delisting_form, fetched_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [(i["ticker"], i.get("cik"), i.get("company_name"),
              i.get("first_filing_date"),
              json.dumps(i["former_names"]) if i.get("former_names") else None,
              i.get("delisted_date"), i.get("delisting_form"), today)
             for i in identities],
        )
        conn.commit()
    finally:
        conn.close()


def tickers_needing_identity(tickers):
    """Which of these still need fetching — absent or gone stale.

    The point of the whole table: resolving 5,809 symbols is 5,809
    requests against EDGAR, and doing that again on the next run because
    nobody asked what was already known would be the actual expense.
    """
    conn = _connect()
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT ticker, fetched_date FROM security_identity"
        ).fetchall()
    finally:
        conn.close()
    fresh = {r["ticker"] for r in rows
             if _is_fresh(r["fetched_date"], IDENTITY_CACHE_TTL_DAYS)}
    return [t for t in tickers if t not in fresh]


def bars_predating_owner(ticker, bars):
    """The bars in this series that belong to a previous holder of the
    ticker, judged against when the current owner first filed.

    This is the whole reason the table exists. Requesting GM with an end
    date in 2008 returns bars, and they are not General Motors Co, which
    did not exist until 2009. Splicing those into one series produces
    something well-formed and wrong.

    Returns [] when identity is unknown rather than guessing — an unknown
    owner is not evidence of contamination, and dropping real history on
    a missing lookup would be the worse error.
    """
    identity = get_cached_identity(ticker)
    if not identity or not identity["first_filing_date"]:
        return []
    cutoff = identity["first_filing_date"]
    return [b for b in bars if (b.get("time") or b.get("date", ""))[:10] < cutoff]


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


def cache_universe(instruments, security_types=None):
    """Replaces the cached universe wholesale — a partial refresh would
    leave delisted names behind.

    :param security_types: optional {symbol: type} map, so a scan can
        exclude preferreds, units and funds without re-deriving the
        classification from raw instrument records it no longer has.
        Classification is relational — a symbol is a preferred because a
        sibling exists — so it can't be recomputed one row at a time.
    """
    today = datetime.date.today().isoformat()
    security_types = security_types or {}
    conn = _connect()
    try:
        conn.execute("DELETE FROM universe_cache")
        conn.executemany(
            "INSERT OR REPLACE INTO universe_cache "
            "(symbol, name, exchange_code, status, is_fund, security_type, fetched_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (i.get("symbol"), i.get("name"), i.get("exchange_code"), i.get("status"),
                 security_types.get(i.get("symbol")) == "fund",
                 security_types.get(i.get("symbol")), today)
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

    One row per ticker per entry date per parameter set. Without that,
    re-running a parameter set over the same window appended a second
    copy of every trade, and since the report just aggregates whatever
    rows exist, the sample silently doubled — win rate, expectancy and
    trade count all computed off duplicates that look like independent
    observations. That matters more here than almost anywhere else in
    the project, because these are the numbers I use to decide whether a
    parameter is worth keeping.
    """
    conn = _connect()
    try:
        conn.execute(
            "DELETE FROM backtest_trades WHERE ticker = ? AND entry_date = ? "
            "AND parameter_set IS ?",
            (trade.get("ticker"), trade.get("entry_date"), trade.get("parameter_set")),
        )
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


def merge_backtest_trades(source_path, db_path=None):
    """Copy backtest_trades out of a side database into the main one.

    The companion to SCREENER_DB: a long arm writes to local disk, and
    its results are folded back here when it finishes. Only
    backtest_trades moves — a side database has no screener history worth
    keeping, and copying tables wholesale would overwrite real runs with
    a scratch file's empty ones.

    Returns the number of rows added. Existing rows for a parameter_set
    are cleared first, so re-merging a re-run arm replaces it rather than
    doubling it — silently doubling an arm is exactly the kind of fault
    that reads as a real change in the numbers.
    """
    conn = sqlite3.connect(db_path or DB_PATH, timeout=60.0)
    try:
        conn.executescript(SCHEMA)
        conn.execute("ATTACH DATABASE ? AS src", (source_path,))
        sets = [r[0] for r in conn.execute(
            "SELECT DISTINCT parameter_set FROM src.backtest_trades")]
        for name in sets:
            conn.execute("DELETE FROM backtest_trades WHERE parameter_set IS ?", (name,))
        cols = [r[1] for r in conn.execute("PRAGMA table_info(backtest_trades)")
                if r[1] != "id"]
        collist = ", ".join(cols)
        before = conn.execute("SELECT COUNT(*) FROM backtest_trades").fetchone()[0]
        conn.execute(f"INSERT INTO backtest_trades ({collist}) "
                     f"SELECT {collist} FROM src.backtest_trades")
        after = conn.execute("SELECT COUNT(*) FROM backtest_trades").fetchone()[0]
        conn.commit()
        conn.execute("DETACH DATABASE src")
        return after - before
    finally:
        conn.close()
