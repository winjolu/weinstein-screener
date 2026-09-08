"""I2: are insider sales a short signal, and does size or clustering help?

Registered in docs/preregistered-tests.md before this ran. The
unconditional answer was already in hand from I1, which used code-S as
one of its three controls and measured a mean abnormal return after a
sale of roughly zero. So this does not re-ask that question. It asks
whether *conditioning* on how big the sale was, or on how many insiders
sold at once, isolates a subset that does predict a decline — which is
what a mixture of thousands of scheduled, uninformative sales and a
handful of informed ones would look like.

### Why the size metrics are ratios rather than dollars alone

A $5M sale means something different at a $200M company than at a $200B
one, and something different again in 2009 than in 2026. Three measures
are computed for that reason: the raw dollar value, the value as a
fraction of market capitalisation, and the value divided by the
company's ordinary daily turnover — how many days of normal volume the
insider dumped, which is the one that says whether the sale was large
enough to be noticed by the market at all.

### Why deciles are cut inside each calendar month

Ranking pooled across eighteen years would sort by inflation and by the
growth of the market as much as by the size of the sale, putting recent
sales in the top decile because they are recent. Cutting within the
month asks "large compared to what else insiders were selling that
month", which is the comparison the hypothesis is actually about.

### On the borrow cost

Shorting is not buying with the sign flipped. `short_borrow_apr` existed
on the broker profile from the beginning and nothing read it, so any
short costed through the shared module was being charged nothing to
borrow — the largest cost on that side, missing. It is charged here at
two rates, and both are optimistic: no borrow-availability data exists
in this archive, and the thin names that attract heavy insider selling
are exactly the ones that are dear or impossible to borrow.
"""
import sqlite3

import numpy as np
import pandas as pd

from market_core import costs, liquidity, sharadar

from . import insider_study as study

# Trading days over which "how many days of volume was this" is measured,
# ending the day before the filing so the sale itself never enters its
# own denominator.
VOLUME_WINDOW = 63

# A cluster is three or more distinct people selling the same company
# inside a month. Declared before running, not tuned afterwards.
CLUSTER_WINDOW_DAYS = 30
CLUSTER_MIN_SELLERS = 3

# The shipwreck outcome: stopped trading within a year, having already
# lost half its value. The decline qualifier is what separates a
# collapse from an acquisition, which usually leaves at a premium.
SHIPWRECK_HORIZON = 252
SHIPWRECK_DECLINE_PCT = -50.0

TAIL_THRESHOLD_PCT = -20.0

# Calendar days per trading day, for converting a holding period into a
# borrow charge. 252 trading days to the year.
CALENDAR_PER_TRADING_DAY = 365.0 / 252.0


def load_sales(conn, eligible, start=None, end=None, code="S"):
    """Code-S filings with the columns the size and cluster tests need.

    `insider_study.insider_events` deliberately reads only the three
    columns its own test uses; this needs the owner and the transaction
    value as well, so it queries separately rather than widening a
    function whose narrowness is part of its argument.
    """
    events = pd.read_sql(
        "SELECT ticker, filingdate, transactioncode, ownername, "
        "transactionvalue, transactionshares, transactionpricepershare, "
        "isofficer, isdirector, istenpercentowner "
        "FROM insiders WHERE transactioncode=? AND filingdate IS NOT NULL",
        conn, params=(code,))
    if start:
        events = events[events["filingdate"] >= start]
    if end:
        events = events[events["filingdate"] <= end]
    events = events[events["ticker"].isin(eligible.index)].copy()
    first_ok = events["ticker"].map(eligible["firstpricedate"]).fillna("0000-00-00")
    last_ok = events["ticker"].map(eligible["lastpricedate"]).fillna("9999-99-99")
    events = events[(events["filingdate"] >= first_ok) &
                    (events["filingdate"] <= last_ok)]
    events["value"] = pd.to_numeric(events["transactionvalue"], errors="coerce").abs()
    return events.reset_index(drop=True)


def load_price_panel_with_volume(conn, tickers):
    """Closes and volumes per ticker. The volume is what separates this
    from the panel `insider_study` builds, and it is needed for the
    turnover denominator rather than for the returns."""
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS wanted (ticker TEXT PRIMARY KEY)")
    conn.execute("DELETE FROM wanted")
    conn.executemany("INSERT INTO wanted VALUES (?)", [(t,) for t in sorted(tickers)])
    prices = pd.read_sql(
        "SELECT p.ticker, p.date, p.closeadj, p.close, p.volume FROM prices p "
        "JOIN wanted w ON w.ticker = p.ticker ORDER BY p.ticker, p.date", conn)
    out = {}
    for ticker, group in prices.groupby("ticker", sort=False):
        out[ticker] = {
            "date": group["date"].to_numpy(),
            "closeadj": group["closeadj"].to_numpy(dtype=float),
            "close": group["close"].to_numpy(dtype=float),
            "volume": group["volume"].to_numpy(dtype=float),
        }
    return out


def load_marketcap_panel(conn):
    """Market cap per ticker per day, from `dailyfundamentals`.

    Stored by the vendor in millions; converted to dollars here so it can
    be divided into a transaction value without a units mistake that
    would silently move every ratio by six orders of magnitude.

    This table begins 2016-01-04, which is what bounds the
    cap-relative hypothesis to 2016 onward rather than any choice made
    here.
    """
    frame = pd.read_sql(
        "SELECT ticker, date, marketcap FROM dailyfundamentals "
        "WHERE marketcap IS NOT NULL AND marketcap != '' "
        "ORDER BY ticker, date", conn)
    frame["marketcap"] = pd.to_numeric(frame["marketcap"], errors="coerce") * 1e6
    frame = frame[frame["marketcap"] > 0]
    return {ticker: (group["date"].to_numpy(),
                     group["marketcap"].to_numpy(dtype=float))
            for ticker, group in frame.groupby("ticker", sort=False)}


def _trailing_dollar_volume(dates, close, volume, entry_idx,
                            window=VOLUME_WINDOW):
    """Median daily dollar volume over the `window` bars before each
    entry, or NaN where rounding has destroyed the volume.

    The refusal is the point and it is not a detail: adjusted volume is
    stored as a whole number, so a name that has been through reverse
    splits carries volumes rounded up to a floor of one share against a
    price inflated by the same factor. `market_core.liquidity` documents
    the case and holds the two thresholds; they are imported rather than
    restated so the two cannot drift apart, while the array arithmetic
    lives here because that module works on bar dicts and this needs to
    run over a million events.
    """
    out = np.full(len(entry_idx), np.nan)
    for i, idx in enumerate(entry_idx):
        lo = max(0, idx - window)
        if idx - lo < 10:
            continue
        vol = volume[lo:idx]
        px = close[lo:idx]
        quantised = vol <= liquidity.VOLUME_FLOOR
        if quantised.mean() > liquidity.MAX_QUANTISED:
            continue
        usable = ~quantised
        if usable.sum() < 10:
            continue
        out[i] = float(np.median(px[usable] * vol[usable]))
    return out


def add_size_metrics(events, panel, marketcap_panel):
    """Attach the three declared size measures to each filing.

    :return: the frame with `value`, `value_to_cap`, `days_of_volume`
        and the entry price, one row per input filing. Rows whose
        measure could not be computed carry NaN there and are dropped
        per-hypothesis rather than globally, so a name missing market
        cap still contributes to the dollar-size and turnover tests.
    """
    pieces = []
    for ticker, group in events.groupby("ticker", sort=False):
        bars = panel.get(ticker)
        if bars is None or len(bars["date"]) == 0:
            continue
        dates = bars["date"]
        filing = group["filingdate"].to_numpy()
        entry_idx = np.searchsorted(dates, filing, side="left")
        keep = entry_idx < len(dates)
        if not keep.any():
            continue
        sub = group[keep].copy()
        entry_idx = entry_idx[keep]

        sub["entry_price"] = bars["closeadj"][entry_idx]
        sub["days_of_volume"] = sub["value"].to_numpy() / _trailing_dollar_volume(
            dates, bars["close"], bars["volume"], entry_idx)

        cap_dates, cap_values = marketcap_panel.get(ticker, (None, None))
        if cap_dates is None:
            sub["value_to_cap"] = np.nan
        else:
            ci = np.searchsorted(cap_dates, sub["filingdate"].to_numpy(),
                                 side="right") - 1
            caps = np.where(ci >= 0, cap_values[np.clip(ci, 0, None)], np.nan)
            sub["value_to_cap"] = sub["value"].to_numpy() / caps
        pieces.append(sub)
    return pd.concat(pieces, ignore_index=True) if pieces else events.iloc[:0].copy()


def monthly_decile(events, column, deciles=10):
    """Decile rank of `column` within each calendar month.

    Ranking pooled across the whole history would sort by era as much as
    by size. NaNs stay NaN rather than being ranked as small, so a
    missing measure never quietly becomes a bottom-decile observation.
    """
    month = events["filingdate"].str[:7]
    values = events[column]
    return values.groupby(month).transform(
        lambda s: pd.qcut(s, deciles, labels=False, duplicates="drop")
        if s.notna().sum() >= deciles else pd.Series(np.nan, index=s.index))


def cluster_sizes(events, window_days=CLUSTER_WINDOW_DAYS):
    """How many distinct insiders sold the same company in the trailing
    window ending at each filing.

    Counted on a *trailing* window rather than a centred one: a trader
    acting on a filing can only see sales already filed, and a centred
    window would count sellers who had not appeared yet — the same
    look-ahead that inflated an earlier result in this project by 200
    days.

    Two pointers over each ticker's filings with a running tally of
    owners, rather than a window comparison per row, because this runs
    over about two million filings.
    """
    out = np.ones(len(events), dtype=float)
    day = pd.to_datetime(events["filingdate"].str[:10],
                         errors="coerce").to_numpy()
    tickers = events["ticker"].to_numpy()
    owners = events["ownername"].fillna("").to_numpy()
    span = np.timedelta64(int(window_days), "D")

    order = np.lexsort((day, tickers))
    start = 0
    for end in range(1, len(order) + 1):
        if end < len(order) and tickers[order[end]] == tickers[order[start]]:
            continue
        block = order[start:end]
        counts = {}
        left = 0
        for right in range(len(block)):
            here = block[right]
            counts[owners[here]] = counts.get(owners[here], 0) + 1
            while day[block[left]] < day[here] - span:
                gone = owners[block[left]]
                counts[gone] -= 1
                if counts[gone] == 0:
                    del counts[gone]
                left += 1
            out[here] = len(counts)
        start = end
    return out


def shipwreck_outcomes(events, panel, horizon=SHIPWRECK_HORIZON,
                       decline_pct=SHIPWRECK_DECLINE_PCT):
    """Did the ticker stop trading within `horizon` trading days, and had
    it already collapsed when it did?

    Two flags, because they measure different things. `stopped_trading`
    counts every exit including takeovers, which usually leave at a
    premium and are the opposite of a shipwreck — roughly 60% of the
    companies that have left this archive were acquired. `sank`
    additionally requires the last available close to be at least
    `decline_pct` below the price on the filing date, which is what
    separates a collapse from a buyout.

    A name whose series simply ends because the archive ends is not a
    delisting. Anything filed within `horizon` trading days of the end
    of that ticker's data is excluded from both outcomes rather than
    counted as a survivor, since it has not had time to fail.
    """
    stopped = np.zeros(len(events), dtype=bool)
    sank = np.zeros(len(events), dtype=bool)
    resolved = np.zeros(len(events), dtype=bool)
    positions = np.arange(len(events))
    archive_end = max((bars["date"][-1] for bars in panel.values()
                       if len(bars["date"])), default="")

    for ticker, group in events.groupby("ticker", sort=False):
        bars = panel.get(ticker)
        if bars is None or len(bars["date"]) == 0:
            continue
        dates, closes = bars["date"], bars["closeadj"]
        rows = positions[group.index]
        entry_idx = np.searchsorted(dates, group["filingdate"].to_numpy(),
                                    side="left")
        ticker_ends_early = dates[-1] < archive_end
        for row, idx in zip(rows, entry_idx):
            if idx >= len(dates):
                continue
            has_full_horizon = idx + horizon < len(dates)
            if has_full_horizon:
                resolved[row] = True
                continue
            # Not enough bars left. That is a delisting only if this
            # ticker's series ends before the archive does; otherwise
            # the data simply has not caught up yet.
            if not ticker_ends_early:
                continue
            resolved[row] = True
            stopped[row] = True
            entry = closes[idx]
            if entry > 0 and (closes[-1] / entry - 1.0) * 100 <= decline_pct:
                sank[row] = True
    return {"stopped_trading": stopped, "sank": sank, "resolved": resolved}


def short_return_pct(abnormal_pct, horizon, profile):
    """What the short actually returned: the negation of the long
    abnormal return, less the borrow charged over the holding period.

    Written as its own function because the sign flip is the step most
    likely to be done in the head and got wrong, and because the borrow
    is a cost on the short whether the short won or lost.
    """
    days = horizon * CALENDAR_PER_TRADING_DAY
    borrow = (profile.short_borrow_apr / 100.0
              * days / costs.DAY_COUNT_BASIS * 100.0)
    return -abnormal_pct - borrow


def aggregate_to_company_day(events):
    """One row per company per filing date.

    Several insiders routinely file the same day, and one insider often
    files several times in a week. Left as separate rows, a single day's
    return would enter the sample once per piece of paperwork, and a
    company with a talkative compliance department would look like a
    stampede. Value is summed; sellers are counted distinctly.
    """
    events = events.copy()
    events["sellers_today"] = 1
    grouped = events.groupby(["ticker", "filingdate"], as_index=False).agg(
        value=("value", "sum"),
        sellers_today=("ownername", "nunique"),
        cluster_sellers=("cluster_sellers", "max"),
        any_officer=("isofficer", lambda s: (s == "Y").any()),
        any_tenpct=("istenpercentowner", lambda s: (s == "Y").any()),
    )
    return grouped


def build_events(db_path=None, start=None, end=None):
    """Company-day sale events with every declared conditioning measure."""
    conn = sqlite3.connect(f"file:{db_path or sharadar.DB_PATH}?mode=ro", uri=True)
    try:
        eligible = study.eligible_tickers(conn)
        raw = load_sales(conn, eligible, start, end, code="S")
        raw["cluster_sellers"] = cluster_sizes(raw)
        events = aggregate_to_company_day(raw)
        wanted = set(events["ticker"])
        panel = load_price_panel_with_volume(conn, wanted)
        marketcap = load_marketcap_panel(conn)
        bench_dates, bench_close = study.load_benchmark(conn)
    finally:
        conn.close()

    events = add_size_metrics(events, panel, marketcap)
    outcomes = shipwreck_outcomes(events, panel)
    for name, flag in outcomes.items():
        events[name] = flag
    for column in ("value", "value_to_cap", "days_of_volume"):
        events[f"{column}_decile"] = monthly_decile(events, column)

    returns_panel = {t: (b["date"], b["closeadj"]) for t, b in panel.items()}
    returns = study.event_returns(events[["ticker", "filingdate"]].assign(
        transactioncode="S"), returns_panel, bench_dates, bench_close)
    return {"events": events, "returns": returns, "panel": panel}


def merge_returns(events, returns, horizon):
    """Company-day events joined to their return at one horizon."""
    at_h = returns[returns["horizon"] == horizon]
    merged = events.merge(at_h[["ticker", "filingdate", "raw_pct", "abnormal_pct",
                                "abnormal_costed_pct"]],
                          on=["ticker", "filingdate"], how="inner")
    for profile, label in ((costs.WEBULL_SHORT_GC, "short_gc_pct"),
                           (costs.WEBULL_SHORT_HTB, "short_htb_pct")):
        merged[label] = short_return_pct(merged["abnormal_pct"], horizon, profile)
    merged["tail"] = (merged["raw_pct"] <= TAIL_THRESHOLD_PCT).astype(float)
    return merged
