"""I1: do insider open-market purchases predict returns?

Registered in docs/preregistered-tests.md before this ran. Every design
choice below — the filing date as the event date, the three controls,
the |t| >= 3.0 bar, the two-way clustering — was fixed there first and
is reproduced here rather than re-derived, on the same reasoning as
every other registered test in this project: a threshold chosen after
seeing the result is not a threshold.

### Why filing date, not transaction date

The transaction date is unknowable to a trader until the filing exists.
Using it would be the same look-ahead leak found earlier at the 200-day
checkpoint: a return computed from information that had not yet reached
the market.

### Why two-way clustering

Insiders at one company file together, so treating each filing as an
independent draw overstates the sample size along the firm axis.
Everyone also tends to file near the same market-wide moves, which
overstates it along the calendar axis. `market_core.timeseries` had
neither before this — its `ols` only handles Newey-West serial
correlation, which corrects the wrong axis for a filings table. The
two-way cluster machinery (`cluster_two_way`, `cluster_mean`) was built
into that shared module for this test, since a data-layer capability
belongs there rather than copied here.

### Why the point-in-time universe is rebuilt here

The docs describe the "same point-in-time rule as W2" — domestic common
stock, on a real exchange, listed at the event date — but no reusable
function for it survived a scratch-directory clear earlier in the
project. Query, not code, is the primary artifact this file is meant to
stop losing a second time.
"""
import sqlite3
import time

import numpy as np
import pandas as pd

from market_core import costs, sharadar, timeseries as ts

REAL_EXCHANGES = ("NYSE", "NASDAQ", "NYSEARCA", "NYSEMKT", "BATS")

# Warrants and secondary-class shares matching this prefix are excluded
# deliberately: they trade on the underlying's news, not their own.
DOMESTIC_COMMON = ("Domestic Common Stock", "Domestic Common Stock Primary Class",
                   "Domestic Common Stock Secondary Class")

HORIZONS = (5, 21, 63)
STAKE = 1000.0

# "40 draws" per the registration.
RANDOM_DRAWS = 40


def eligible_tickers(conn):
    """The point-in-time universe: domestic common stock on a real
    exchange, with the listing window each ticker actually traded in.

    Returned indexed by ticker so a filing date can be checked against
    `firstpricedate`/`lastpricedate` directly — the current `isdelisted`
    flag alone answers "is this listed today", not "was this listed on
    the date of a ten-year-old filing".
    """
    tickers = pd.read_sql(
        "SELECT ticker, exchange, category, firstpricedate, lastpricedate "
        "FROM tickers WHERE tbl='SEP'", conn)
    return tickers[tickers["exchange"].isin(REAL_EXCHANGES) &
                   tickers["category"].isin(DOMESTIC_COMMON)].set_index("ticker")


def insider_events(conn, eligible):
    """Code P and S filings, restricted to the point-in-time universe.

    Filing date only enters the selection — no price data does — which
    is the whole point of an orthogonal signal.
    """
    events = pd.read_sql(
        "SELECT ticker, filingdate, transactioncode FROM insiders "
        "WHERE transactioncode IN ('P','S') AND filingdate IS NOT NULL", conn)
    events = events[events["ticker"].isin(eligible.index)].copy()
    first_ok = events["ticker"].map(eligible["firstpricedate"]).fillna("0000-00-00")
    last_ok = events["ticker"].map(eligible["lastpricedate"]).fillna("9999-99-99")
    return events[(events["filingdate"] >= first_ok) &
                  (events["filingdate"] <= last_ok)].reset_index(drop=True)


def load_price_panel(conn, tickers):
    """Every close for the given tickers, grouped for fast per-ticker
    lookup. A single indexed join rather than one query per ticker —
    the difference between this loading in three minutes and three
    hours, measured across ~17,000 tickers."""
    conn.execute("CREATE TEMP TABLE wanted (ticker TEXT PRIMARY KEY)")
    conn.executemany("INSERT INTO wanted VALUES (?)", [(t,) for t in sorted(tickers)])
    prices = pd.read_sql(
        "SELECT p.ticker, p.date, p.closeadj FROM prices p JOIN wanted w "
        "ON w.ticker = p.ticker ORDER BY p.ticker, p.date", conn)
    return {ticker: (group["date"].to_numpy(), group["closeadj"].to_numpy(dtype=float))
            for ticker, group in prices.groupby("ticker", sort=False)}


def load_benchmark(conn, ticker="IWM"):
    """IWM's own close series. Lives in `fundprices`, not `prices` — the
    same table split that silently dropped six of seven benchmarks from
    an earlier build script, so this asks for it by name rather than
    assuming the caller already knows which table an index fund is in."""
    bars = pd.read_sql(
        "SELECT date, closeadj FROM fundprices WHERE ticker=? ORDER BY date",
        conn, params=(ticker,))
    return bars["date"].to_numpy(), bars["closeadj"].to_numpy(dtype=float)


def load_panel(db_path=None):
    """Everything `event_returns` and the controls need, in one dict."""
    conn = sqlite3.connect(f"file:{db_path or sharadar.DB_PATH}?mode=ro", uri=True)
    try:
        eligible = eligible_tickers(conn)
        events = insider_events(conn, eligible)
        by_ticker = load_price_panel(conn, eligible.index)
        iwm_dates, iwm_close = load_benchmark(conn)
    finally:
        conn.close()
    return {"eligible": eligible, "events": events, "by_ticker": by_ticker,
            "iwm_dates": iwm_dates, "iwm_close": iwm_close}


def _benchmark_return(entry_date, exit_date, bench_dates, bench_close):
    """IWM's return over the same calendar window an event's own return
    used — B2's size-matching, computed pointwise rather than for a
    single fixed window. Looks up the last available close on or before
    each date, so a benchmark holiday that skips a trading day the
    stock itself has bars for does not throw the lookup off by one."""
    ei = np.searchsorted(bench_dates, entry_date, side="right") - 1
    xi = np.searchsorted(bench_dates, exit_date, side="right") - 1
    valid = (ei >= 0) & (xi >= 0)
    out = np.full(len(entry_date), np.nan)
    out[valid] = bench_close[xi[valid]] / bench_close[ei[valid]] - 1.0
    return out


def event_returns(events_df, by_ticker, bench_dates, bench_close, horizons=HORIZONS):
    """Long-format frame, one row per (event, horizon): raw return,
    abnormal return against IWM, and the costed version of both.

    Grouped by ticker before the per-horizon arithmetic — with 2.4
    million eligible filings, a python loop over individual events was
    measured taking minutes; grouping to ~9-17k tickers and using
    `searchsorted` within each group is the difference between that and
    single-digit seconds per horizon.
    """
    rows = []
    for ticker, group in events_df.groupby("ticker", sort=False):
        dates, closes = by_ticker.get(ticker, (None, None))
        if dates is None or len(dates) == 0:
            continue
        filing = group["filingdate"].to_numpy()
        codes = group["transactioncode"].to_numpy()
        entry_idx = np.searchsorted(dates, filing, side="left")
        in_range = entry_idx < len(dates)
        if not in_range.any():
            continue
        entry_idx = entry_idx[in_range]
        codes = codes[in_range]
        entry_close = closes[entry_idx]
        entry_date = dates[entry_idx]

        for h in horizons:
            exit_idx = entry_idx + h
            ok = exit_idx < len(dates)
            if not ok.any():
                continue
            exit_close = closes[exit_idx[ok]]
            exit_date = dates[exit_idx[ok]]
            raw_pct = (exit_close / entry_close[ok] - 1.0) * 100
            bench_pct = _benchmark_return(entry_date[ok], exit_date,
                                          bench_dates, bench_close) * 100
            cost_pct = np.array([
                costs.cost_pct({"entry_price": e, "exit_price": x},
                                profile=costs.WEBULL, stake=STAKE)
                for e, x in zip(entry_close[ok], exit_close)])
            rows.append(pd.DataFrame({
                "ticker": ticker,
                "filingdate": entry_date[ok],
                "transactioncode": codes[ok],
                "horizon": h,
                "raw_pct": raw_pct,
                "abnormal_pct": raw_pct - bench_pct,
                "abnormal_costed_pct": (raw_pct - cost_pct) - bench_pct,
            }))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["ticker", "filingdate", "transactioncode", "horizon",
                 "raw_pct", "abnormal_pct", "abnormal_costed_pct"])


def random_control(events, eligible, by_ticker, bench_dates, bench_close,
                    horizons=HORIZONS, draws=RANDOM_DRAWS, seed=0):
    """Control 1: the same number of (ticker, date) pairs as the code-P
    group, tickers redrawn uniformly from the point-in-time universe on
    the same calendar dates, `draws` independent times.

    A uniformly drawn ticker can land on a date outside its own listing
    window; those draws are resampled for a fixed number of rounds and
    whatever is still unresolved after that is dropped. The code-P group
    loses events to the same edge — no bars far enough forward near the
    end of the archive — so this is not a new source of bias, just the
    same one applied to the control.
    """
    rng = np.random.default_rng(seed)
    real = events[events["transactioncode"] == "P"]
    dates = real["filingdate"].to_numpy()
    n = len(dates)
    universe = eligible.index.to_numpy()
    first = eligible["firstpricedate"].fillna("0000-00-00").to_numpy()
    last = eligible["lastpricedate"].fillna("9999-99-99").to_numpy()

    all_draws = []
    for draw in range(draws):
        pick = rng.integers(0, len(universe), size=n)
        for _round in range(6):
            ok = (first[pick] <= dates) & (dates <= last[pick])
            if ok.all():
                break
            pick[~ok] = rng.integers(0, len(universe), size=(~ok).sum())
        ok = (first[pick] <= dates) & (dates <= last[pick])
        frame = pd.DataFrame({"ticker": universe[pick][ok],
                              "filingdate": dates[ok],
                              "transactioncode": "R"})
        result = event_returns(frame, by_ticker, bench_dates, bench_close, horizons)
        if len(result):
            result["draw"] = draw
            all_draws.append(result)
    return pd.concat(all_draws, ignore_index=True) if all_draws else pd.DataFrame()


def shuffled_control(events, by_ticker, bench_dates, bench_close,
                      horizons=HORIZONS, seed=1):
    """Control 2: real code-P filing dates reassigned at random among the
    same set of tickers. Preserves the marginal distribution of both
    tickers and dates and destroys only which company filed on which
    date — isolating timing from "this kind of company tends to do
    well" as a static trait."""
    rng = np.random.default_rng(seed)
    real = events[events["transactioncode"] == "P"].copy()
    shuffled_dates = rng.permutation(real["filingdate"].to_numpy())
    frame = pd.DataFrame({"ticker": real["ticker"].to_numpy(),
                          "filingdate": shuffled_dates,
                          "transactioncode": "H"})
    return event_returns(frame, by_ticker, bench_dates, bench_close, horizons)


def two_way_test(a, b, cluster_col="ticker", date_col="filingdate"):
    """Cluster-robust test that group `a`'s mean costed abnormal return
    exceeds group `b`'s — a regression of the return on a 1/0 group
    dummy, clustered by firm and by filing date at once."""
    combined = pd.concat([a.assign(_group=1.0), b.assign(_group=0.0)],
                         ignore_index=True)
    out = ts.cluster_two_way(
        combined["abnormal_costed_pct"].to_numpy(),
        combined["_group"].to_numpy(),
        combined[cluster_col].to_numpy(),
        combined[date_col].to_numpy())
    return {"n_a": len(a), "n_b": len(b),
            "mean_a": float(a["abnormal_costed_pct"].mean()),
            "mean_b": float(b["abnormal_costed_pct"].mean()),
            "diff": out["params"][1], "tvalue": out["tvalues"][1],
            "pvalue": out["pvalues"][1], "clipped": out["clipped"]}


def mean_vs_zero(frame, cluster_col="ticker", date_col="filingdate"):
    """Cluster-robust test that a group's mean costed abnormal return is
    different from zero on its own, without reference to a control."""
    out = ts.cluster_mean(frame["abnormal_costed_pct"].to_numpy(),
                          frame[cluster_col].to_numpy(),
                          frame[date_col].to_numpy())
    return {"n": out["nobs"], "mean": out["mean"],
            "tvalue": out["tvalue"], "pvalue": out["pvalue"]}


def run(db_path=None, draws=RANDOM_DRAWS, verbose=True):
    """The full registered comparison: code P against all three controls
    at all three horizons, using costed abnormal returns throughout.

    :return: dict keyed by horizon, each holding the P-vs-zero result
        and a P-vs-control result for each of the three controls.
    """
    t0 = time.time()
    panel = load_panel(db_path)
    events, by_ticker = panel["events"], panel["by_ticker"]
    eligible = panel["eligible"]
    bench_dates, bench_close = panel["iwm_dates"], panel["iwm_close"]

    p_events = events[events["transactioncode"] == "P"]
    s_events = events[events["transactioncode"] == "S"]

    p_ret = event_returns(p_events, by_ticker, bench_dates, bench_close)
    s_ret = event_returns(s_events, by_ticker, bench_dates, bench_close)
    h_ret = shuffled_control(events, by_ticker, bench_dates, bench_close)
    r_ret = random_control(events, eligible, by_ticker, bench_dates, bench_close,
                            draws=draws)

    results = {}
    for h in HORIZONS:
        p_h = p_ret[p_ret["horizon"] == h]
        controls = {"random": r_ret[r_ret["horizon"] == h],
                    "shuffled": h_ret[h_ret["horizon"] == h],
                    "code_s": s_ret[s_ret["horizon"] == h]}
        results[h] = {
            "vs_zero": mean_vs_zero(p_h),
            "vs_control": {name: two_way_test(p_h, ctrl)
                          for name, ctrl in controls.items()},
        }
        if verbose:
            vz = results[h]["vs_zero"]
            print(f"\n--- horizon = {h} trading days ---")
            print(f"P vs zero:     n={vz['n']:>7,}  mean={vz['mean']:+.3f}%  "
                  f"t={vz['tvalue']:+.2f}")
            for name, cmp in results[h]["vs_control"].items():
                print(f"P vs {name:<8}: n_ctrl={cmp['n_b']:>9,}  "
                      f"mean_P={cmp['mean_a']:+.3f}%  mean_ctrl={cmp['mean_b']:+.3f}%  "
                      f"diff={cmp['diff']:+.3f}%  t={cmp['tvalue']:+.2f}")
    if verbose:
        print(f"\ntotal wall time: {time.time()-t0:.0f}s")
    return results


if __name__ == "__main__":
    run()
