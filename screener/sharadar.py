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


def fetch(table, page_size=MAX_LIMIT, max_rows=None, **params):
    """All rows for a query, following offset pagination to the end.

    Stops when a page comes back shorter than requested, which is the
    only end-of-data signal the API gives — there is no cursor and no
    total count.
    """
    rows, skip = [], 0
    while True:
        page = _get(table, limit=page_size, skip=skip, **params)
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
