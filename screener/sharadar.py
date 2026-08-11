"""Sharadar client, for the one thing Webull cannot provide.

Webull returns INVALID_SYMBOL for any company that no longer exists, so
every result in this project has been measured on a universe of
survivors. The census in docs/preregistered-tests.md found 2,805
companies delisted and absent from a 1,257-name holdout universe, and D3
found that 2% of trades going to zero erases the edge in two windows of
three. This module exists to replace that guess with a measurement.

Sharadar's Prices tier carries roughly 15,000 delisted securities back to
January 1998, which spans every window tested here.

API contract, confirmed against the live service on 2026-08-03 rather
than assumed — guessing at API details has cost this project real time
twice, and both times it was written down afterwards:

- Base is https://api.sharadar.com/v1.0/data/{table}
- The key is a query parameter, `api_key`, not a header
- Responses are **CSV**, not JSON. My first client assumed JSON and
  every call failed with a decode error against a perfectly good 200.
- Pagination is offset-based: `limit` defaults to 1000 and caps at
  10000, with `skip` for the offset. A bare tickers query returning
  exactly 10000 rows is the cap, not the total.
- Dates filter with `date.gte` / `date.lte` and the strict variants.
- Rate limits are undocumented, so requests are spaced conservatively.
"""
import csv
import io
import os
import time
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://api.sharadar.com/v1.0/data/"
MAX_LIMIT = 10000
_MIN_INTERVAL = 0.2   # undocumented limits; 5/sec is well inside anything sane
_last_request = [0.0]


class MissingApiKey(RuntimeError):
    """Raised instead of sending an unauthenticated request.

    A missing key produces a plausible-looking empty result rather than
    an error, which would read as "this company has no data" — exactly
    the wrong conclusion in a module built to distinguish absence from
    non-existence.
    """


def _api_key():
    key = os.environ.get("SHARADAR_API_KEY", "").strip()
    if not key:
        raise MissingApiKey(
            "SHARADAR_API_KEY is not set. It belongs in .env, which is "
            "gitignored; see .env.example.")
    return key


def _throttle():
    wait = _MIN_INTERVAL - (time.time() - _last_request[0])
    if wait > 0:
        time.sleep(wait)
    _last_request[0] = time.time()


def _get(table, **params):
    """One request. Returns parsed CSV rows as dicts."""
    params["api_key"] = _api_key()
    url = API_BASE + table + "?" + urllib.parse.urlencode(params)
    _throttle()
    with urllib.request.urlopen(url, timeout=120) as response:
        body = response.read().decode("utf-8", errors="replace")
    return list(csv.DictReader(io.StringIO(body)))


def fetch(_table, page_size=MAX_LIMIT, max_rows=None, **params):
    # The positional name is underscored because `table` is also a real
    # column in the tickers response, so callers legitimately want to
    # filter on it. Without this, fetch("tickers", table="stocks") raises
    # "got multiple values for argument 'table'" — which is a confusing
    # error for a correct-looking call.
    """All rows for a query, following offset pagination to the end.

    Stops when a page comes back shorter than requested, which is the
    only end-of-data signal the API gives — there is no cursor and no
    total count.
    """
    rows, skip = [], 0
    while True:
        page = _get(_table, limit=page_size, skip=skip, **params)
        rows.extend(page)
        if len(page) < page_size:
            return rows
        skip += page_size
        if max_rows is not None and len(rows) >= max_rows:
            return rows[:max_rows]


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def daily_bars(ticker, start=None, end=None):
    """Daily bars shaped like the rest of this project's bar caches.

    **On which close to use.** Sharadar gives `close` (split-adjusted)
    and `closeadj` (split *and* dividend adjusted). Webull's bars are
    dividend-adjusted, confirmed earlier by scaling factors matching each
    stock's own yield, so `closeadj` is the one that makes the two
    sources comparable.

    Open, high and low are split-adjusted only. Taking `closeadj` while
    leaving those raw would produce bars whose close sits outside their
    own high-low range on any dividend-paying stock — a silent
    corruption that stop and target logic would act on without
    complaint. Each bar is therefore scaled by its own
    closeadj/close ratio, which keeps it internally consistent.
    """
    params = {"ticker": ticker}
    if start:
        params["date.gte"] = start
    if end:
        params["date.lte"] = end

    bars = []
    for row in fetch("stocks", **params):
        close = _number(row.get("close"))
        adjusted = _number(row.get("closeadj"))
        if close is None or adjusted is None or not row.get("date"):
            continue
        factor = (adjusted / close) if close else 1.0
        bars.append({
            "time": row["date"] + "T00:00:00.000+0000",
            "open": (_number(row.get("open")) or close) * factor,
            "high": (_number(row.get("high")) or close) * factor,
            "low": (_number(row.get("low")) or close) * factor,
            "close": adjusted,
            "volume": _number(row.get("volume")) or 0.0,
        })
    bars.sort(key=lambda b: b["time"])
    return bars


def _is_true(value):
    return str(value).strip().upper() in ("Y", "YES", "TRUE", "1", "T")


def ticker_metadata(ticker=None, **params):
    """Rows from the tickers table, with the two fields that matter typed.

    `permaticker` is the permanent company identifier — it survives
    ticker changes, which is what a ticker itself does not. This project
    found GM, WM and CC all resolving to companies that did not hold
    those symbols during the periods being tested; permaticker is the
    field that makes that detectable rather than invisible.
    """
    if ticker:
        params["ticker"] = ticker
    out = []
    for row in fetch("tickers", **params):
        record = dict(row)
        record["isdelisted"] = _is_true(row.get("isdelisted"))
        record["permaticker"] = row.get("permaticker") or None
        out.append(record)
    return out


def delisted_tickers(**params):
    """Every company Sharadar carries that no longer trades.

    The population this project has never been able to see. Its size is
    the survivorship hole; its returns are the correction.
    """
    return [r for r in ticker_metadata(**params) if r["isdelisted"]]


# ---------------------------------------------------------------------
# Keeping the local database current.
#
# The bulk export is a snapshot: 46M price rows and 14M daily
# fundamentals, downloaded once and already stale by the next close. Any
# operation that needs *today* has to top up from the API.
#
# Incremental rather than wholesale, because re-downloading 6GB to add
# one day's bars is how a daily refresh becomes something nobody runs.

DB_PATH = os.path.expanduser("~/market-data/sharadar.db")

# Which column carries the as-of date, per table. Sharadar is not
# consistent about this and guessing produces an empty refresh that
# looks like "no new data" rather than an error.
DATE_COLUMN = {
    "prices": "date",
    "fundprices": "date",
    "dailyfundamentals": "date",
    # datekey, not calendardate. A company filing its Q1 six months late
    # carries an old calendardate and a new datekey, so asking for
    # calendardate greater than the newest stored skips that filing
    # permanently — and slow filers are 2.28% of rows, which is not a
    # random 2.28%. datekey is also the column every point-in-time read
    # has to use anyway.
    "fundamentals": "datekey",
    "actions": "date",
    "events": "date",
    "insiders": "filingdate",
    "sp500": "date",
}

# Local table name -> the API table it comes from, where they differ.
API_TABLE = {"prices": "stocks", "fundprices": "funds",
             "dailyfundamentals": "daily"}


# History held from a full-depth bulk load is archival. A shorter
# entitlement changes what can be downloaded; it does not change what is
# already held, and nothing should treat those as the same thing.
COVERAGE_TABLE = "data_coverage"

# How far the local data may fall behind before an append becomes a lie.
# refresh() asks for rows after the newest stored. Once the local data is
# further behind than the entitlement reaches, the earliest row the API
# will return sits past the gap, and appending it writes an unfillable
# hole while reporting success.
MAX_REFRESH_GAP_DAYS = 30


class ArchivalWrite(RuntimeError):
    """An operation would destroy history that cannot be re-downloaded."""


class RefreshGap(RuntimeError):
    """An append would leave an unfillable hole in the series."""


def _ensure_coverage(conn):
    conn.execute(
        f"""CREATE TABLE IF NOT EXISTS {COVERAGE_TABLE} (
                table_name TEXT PRIMARY KEY,
                frozen_before TEXT NOT NULL,
                rows_at_freeze INTEGER,
                note TEXT)""")


def freeze_history(table, before, note=None, db_path=None):
    """Mark everything in `table` dated before `before` as archival.

    Run once while the full-depth entitlement is still active. After
    that, assert_writable refuses any operation reaching below the
    watermark, whichever project attempts it.
    """
    import sqlite3
    column = DATE_COLUMN.get(table)
    if not column:
        raise ValueError(f"no date column known for {table!r}")
    conn = sqlite3.connect(db_path or DB_PATH)
    try:
        _ensure_coverage(conn)
        held = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {column} < ?", (before,)).fetchone()[0]
        conn.execute(
            f"INSERT OR REPLACE INTO {COVERAGE_TABLE} VALUES (?,?,?,?)",
            (table, before, held, note))
        conn.commit()
    finally:
        conn.close()
    return held


def frozen_before(table, db_path=None):
    """The archival watermark for `table`, or None if never frozen."""
    import sqlite3
    conn = sqlite3.connect(db_path or DB_PATH)
    try:
        _ensure_coverage(conn)
        row = conn.execute(
            f"SELECT frozen_before FROM {COVERAGE_TABLE} WHERE table_name = ?",
            (table,)).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def assert_writable(table, earliest_affected, db_path=None):
    """Raise unless an operation confined to `earliest_affected` onwards is safe.

    Every destructive path — a bulk rebuild, a DROP, a reload — calls
    this first. Appending later rows is always allowed; reaching below
    the watermark is not.
    """
    mark = frozen_before(table, db_path=db_path)
    if mark and str(earliest_affected) < mark:
        raise ArchivalWrite(
            f"{table}: rows before {mark} came from a full-depth load and "
            f"cannot be re-downloaded, but this would touch {earliest_affected}. "
            f"Append instead, or clear the watermark deliberately.")


def _days_between(earlier, later):
    """Calendar days from `earlier` to `later`, 0 if the order is reversed."""
    import datetime
    a = datetime.date.fromisoformat(str(earlier)[:10])
    b = datetime.date.fromisoformat(str(later)[:10])
    return max((b - a).days, 0)


def latest_local_date(table, db_path=None):
    """Newest date already stored, or None if the table is empty."""
    import sqlite3
    column = DATE_COLUMN.get(table)
    if not column:
        raise ValueError(f"no date column known for {table!r}; add it to DATE_COLUMN")
    conn = sqlite3.connect(db_path or DB_PATH)
    try:
        row = conn.execute(f"SELECT MAX({column}) FROM {table}").fetchone()
    finally:
        conn.close()
    return row[0] if row and row[0] else None


def refresh(table, db_path=None, since=None, dry_run=False,
            allow_gap=False, max_gap_days=MAX_REFRESH_GAP_DAYS):
    """Append rows dated after what we already hold.

    Returns the number of rows inserted. Safe to run repeatedly: it asks
    only for dates strictly after the newest stored, so a second run in
    the same day adds nothing rather than duplicating.

    Deliberately does not deduplicate. If a vendor restates a row we
    would end up with both versions, which is visible and fixable —
    whereas silently overwriting history is the restatement problem this
    project spent a day learning to avoid.
    """
    import sqlite3
    column = DATE_COLUMN.get(table)
    if not column:
        raise ValueError(f"no date column known for {table!r}")
    start = since or latest_local_date(table, db_path)
    if not start:
        raise ValueError(f"{table} is empty; load the bulk export first, "
                         "do not build it one day at a time")

    rows = fetch(API_TABLE.get(table, table), **{f"{column}.gt": start})
    if rows and not allow_gap:
        earliest = min(str(r.get(column, "")) for r in rows if r.get(column))
        gap = _days_between(start, earliest)
        if gap > max_gap_days:
            raise RefreshGap(
                f"{table}: newest stored row is {start}, but the earliest the "
                f"API returns is {earliest} — a {gap}-day hole the entitlement "
                f"can no longer fill. Appending would report success and leave "
                f"the series broken. Pass allow_gap=True only if the hole is "
                f"genuinely acceptable.")
    if dry_run or not rows:
        return len(rows)

    conn = sqlite3.connect(db_path or DB_PATH)
    try:
        cols = [c[1] for c in conn.execute(f"PRAGMA table_info({table})")]
        payload = [tuple(r.get(c) for c in cols) for r in rows]
        conn.executemany(
            f"INSERT INTO {table} VALUES ({','.join('?' * len(cols))})", payload)
        conn.commit()
    finally:
        conn.close()
    return len(payload)


def refresh_all(tables=("prices", "fundprices", "dailyfundamentals"), db_path=None):
    """Top up the tables a live screener actually reads. Returns
    {table: rows_added}, and lets a failure on one table surface rather
    than silently leaving the rest stale."""
    return {t: refresh(t, db_path=db_path) for t in tables}
