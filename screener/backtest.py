"""Backtesting engine: reproduces what the screener would have said on
a past date, using only data available as of that date, then simulates
how the resulting trade would have actually played out.

LOOKAHEAD-BIAS NOTES — read before trusting any result from this module:

1. Weekly bars (ticker and index) are truncated to as_of_date by keeping
   only bars dated on or before it, so evaluate_as_of() only ever sees
   what already existed at that point. This part I'm confident is clean.

2. Sector strength is the one place I'm NOT fully certain is clean by
   construction, so I'm flagging it explicitly rather than assuming it
   works: data_fetch.get_sector_data_for_backtest() returns full
   timestamped daily bars for the ticker's sector ETF and for SPY, which
   evaluate_as_of() truncates the same way as the weekly bars before
   computing the percentile. That truncation is sound. What is NOT sound,
   and what I deliberately never use here, is "sector_strength_pct" — the
   live get_market_sectors() snapshot condition 5 falls back to when
   daily closes aren't available. That number has no historical/as-of
   parameter in Webull's API at all; it's always today's value. Using it
   for a past date would be silent lookahead bias, not just imprecision,
   so evaluate_as_of() hard-codes it to None and lets condition 5 resolve
   only through the (properly truncated) percentile path or come back
   None. If sector_etf_bars/spy_bars weren't fetched with enough
   lookback_days to cover a given as_of_date, condition 5 will
   legitimately come back None there rather than silently reaching
   forward for data that didn't exist yet — that's the intended failure
   mode, not a bug.

3. I do NOT know Webull's actual cap (if any) on the `count` parameter
   for daily bars over a long lookback. run_backtest() requests enough
   lookback_days to cover the full test window plus warm-up, but if the
   real API caps that lower than requested, sector-dependent conditions
   could come back None more often than they should for the earliest
   part of a long backtest. I haven't verified this against a real
   multi-year request — worth checking directly before trusting a long
   backtest's early checkpoints.

4. simulate_trade() is the one place that deliberately does NOT truncate
   bars_full — a trade's actual outcome depends on what price really did
   after entry, so using future bars there is correct, not a bias. Only
   the evaluate_as_of() decision step needs truncation; the outcome
   step needs the opposite.
"""
import contextlib
import datetime

from . import conditions, data_fetch, db, stop_loss

# How many weeks of history to fetch before the earliest checkpoint, so
# conditions.py's own longest internal lookback (PRE_BASE_LOOKBACK=52)
# is actually warmed up rather than just technically non-empty.
LOOKBACK_BUFFER_WEEKS = 90

MIN_TRADES_FOR_CONFIDENCE = 30


def _truncate_bars(bars_full, as_of_date):
    """Keeps only bars dated on or before as_of_date (a "YYYY-MM-DD"
    string), comparing the date portion of each bar's ISO timestamp as a
    plain string. Webull's bar timestamps are zero-padded ISO 8601 with a
    fixed time-of-day and offset, so string comparison sorts correctly
    without parsing timezones.
    """
    return [b for b in bars_full if b["time"][:10] <= as_of_date]


@contextlib.contextmanager
def _condition_overrides(overrides):
    """Temporarily monkey-patches conditions.py's module-level constants
    (e.g. TSR_PIVOT_LENGTH, RISK_REWARD_CLEAR_PASS) so run_backtest() can
    test alternate parameter values without editing conditions.py's
    constants directly or restructuring it to accept them as arguments.
    Always restores the originals afterward, even on error — this is a
    deliberately scoped, reverted mutation, not a standing one.
    """
    originals = {}
    try:
        for name, value in overrides.items():
            if not hasattr(conditions, name):
                raise ValueError(f"conditions.py has no constant named {name!r} to override")
            originals[name] = getattr(conditions, name)
            setattr(conditions, name, value)
        yield
    finally:
        for name, value in originals.items():
            setattr(conditions, name, value)


def evaluate_as_of(ticker, as_of_date, bars_full, index_bars_full, sector_data_full):
    """Reproduces exactly what conditions.evaluate_conditions() would
    have returned on as_of_date, using only data available up to and
    including that date. See this module's docstring for the
    point-in-time-cleanliness notes this depends on.

    :param bars_full: the ticker's full weekly OHLCV history, oldest
        first, each dict carrying a "time" ISO timestamp.
    :param index_bars_full: same shape, for the comparison index.
    :param sector_data_full: {"sector": ..., "sector_etf_bars": [...],
        "spy_bars": [...]} — from data_fetch.get_sector_data_for_backtest.
        "sector_etf_bars"/"spy_bars" must be full timestamped bar dicts,
        not bare closes, since closes alone can't be truncated to a date.
    :return: same dict shape as evaluate_conditions(), plus "as_of_date"
        and "bars_used" (how many truncated weekly bars fed this
        evaluation, so a caller can sanity-check warm-up).
    """
    bars = _truncate_bars(bars_full, as_of_date)
    index_bars = _truncate_bars(index_bars_full, as_of_date)

    sector_etf_bars = _truncate_bars(sector_data_full.get("sector_etf_bars") or [], as_of_date)
    spy_bars = _truncate_bars(sector_data_full.get("spy_bars") or [], as_of_date)

    sector_data = {
        "sector": sector_data_full.get("sector"),
        # Never point-in-time correct — see this module's docstring.
        "sector_strength_pct": None,
        "sector_etf_closes": [b["close"] for b in sector_etf_bars],
        "spy_daily_closes": [b["close"] for b in spy_bars],
    }

    result = conditions.evaluate_conditions(ticker, bars, index_bars, sector_data)
    result["as_of_date"] = as_of_date
    result["bars_used"] = len(bars)
    return result


def simulate_trade(ticker, entry_date, entry_price, swing_stop, swing_target, bars_full,
                    trailing_method='ma', max_hold_weeks=52):
    """Walks forward week by week from entry_date, recomputing
    stop_loss.trailing_stop() using only bars up to and including each
    simulated week (a real trailing stop can only react to price action
    that's already happened by that week), and checks whether that
    week's low hit the current stop or its high hit swing_target.

    When both could plausibly be hit in the same week, I check the stop
    first — weekly OHLC alone can't tell me the actual intraweek order,
    and assuming the stop hit first is the more conservative read.

    Running out of bars_full or reaching max_hold_weeks without an exit
    both come back as "still_open" — from the backtest's perspective
    those are the same situation: the real outcome isn't known yet.

    :return: {"ticker", "entry_date", "entry_price", "exit_date",
        "exit_price", "exit_reason", "return_pct", "r_multiple",
        "still_open"}, or None if entry_date has no matching bar in
        bars_full.
    """
    dates = [b["time"][:10] for b in bars_full]
    try:
        entry_idx = dates.index(entry_date)
    except ValueError:
        return None

    stop = stop_loss.initial_stop(swing_stop)
    last_idx = min(entry_idx + max_hold_weeks, len(bars_full) - 1)

    exit_idx = None
    exit_reason = None
    exit_price = None

    for idx in range(entry_idx + 1, last_idx + 1):
        bars_so_far = bars_full[:idx + 1]
        trail = stop_loss.trailing_stop(bars_so_far, entry_price, entry_idx, method=trailing_method)
        if trail and trail["recommended"] is not None:
            if stop is None or trail["recommended"] > stop:
                stop = trail["recommended"]

        bar = bars_full[idx]
        if stop is not None and bar["low"] <= stop:
            exit_idx, exit_reason, exit_price = idx, "stop", stop
            break
        if swing_target is not None and bar["high"] >= swing_target:
            exit_idx, exit_reason, exit_price = idx, "target", swing_target
            break

    if exit_idx is None:
        return {
            "ticker": ticker,
            "entry_date": entry_date,
            "entry_price": entry_price,
            "exit_date": None,
            "exit_price": None,
            "exit_reason": "still_open",
            "return_pct": None,
            "r_multiple": None,
            "still_open": True,
        }

    exit_date = bars_full[exit_idx]["time"][:10]
    return_pct = (exit_price - entry_price) / entry_price * 100
    risk = entry_price - swing_stop if swing_stop is not None else None
    r_multiple = (exit_price - entry_price) / risk if risk and risk > 0 else None

    return {
        "ticker": ticker,
        "entry_date": entry_date,
        "entry_price": entry_price,
        "exit_date": exit_date,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "return_pct": return_pct,
        "r_multiple": r_multiple,
        "still_open": False,
    }


def _checkpoint_dates(start_date, end_date, check_interval_weeks):
    start = datetime.date.fromisoformat(start_date)
    end = datetime.date.fromisoformat(end_date)
    step = datetime.timedelta(weeks=check_interval_weeks)

    dates = []
    current = start
    while current <= end:
        dates.append(current.isoformat())
        current += step
    return dates


def _lookback_weeks_needed(start_date):
    start = datetime.date.fromisoformat(start_date)
    today = datetime.date.today()
    weeks_since_start = max(0, (today - start).days // 7)
    return weeks_since_start + LOOKBACK_BUFFER_WEEKS


def run_backtest(tickers, start_date, end_date, check_interval_weeks=4, parameter_set="baseline",
                  trailing_method='ma', max_hold_weeks=52, **condition_overrides):
    """Steps through start_date to end_date at check_interval_weeks
    intervals. At each checkpoint, evaluates each ticker as of that date
    and, if it comes back actionable with a real breakout bar to size
    against, simulates the resulting trade and persists it to
    backtest_trades.

    Fetches each ticker's full history once (not once per checkpoint) —
    weekly bars naturally come back through today regardless of
    end_date, since Webull's API only ever fetches "as of now," which is
    what lets simulate_trade() see real forward price action for trades
    entered near end_date.

    Once a ticker enters a trade at some checkpoint, later checkpoints
    are skipped until that trade resolves, so one real breakout doesn't
    get re-detected and re-recorded as several overlapping trades.

    :param condition_overrides: passed to conditions.py's module-level
        constants for the duration of this run only — see
        _condition_overrides(). Example: TSR_PIVOT_LENGTH=10.
    :return: list of trade-result dicts, each tagged with
        "parameter_set", "as_of_date", and "conditions_met".
    """
    lookback_weeks = _lookback_weeks_needed(start_date)
    lookback_days = (datetime.date.today() - datetime.date.fromisoformat(start_date)).days + 45

    checkpoints = _checkpoint_dates(start_date, end_date, check_interval_weeks)

    index_bars_full = data_fetch.get_index_bars("SPY", lookback_weeks=lookback_weeks)

    trades = []
    for ticker in tickers:
        try:
            bars_full = data_fetch.get_weekly_bars(ticker, lookback_weeks=lookback_weeks)
            sector_data_full = data_fetch.get_sector_data_for_backtest(ticker, lookback_days)
        except Exception as exc:
            print(f"[{ticker}] backtest skipped — fetch failed: {exc}")
            continue

        in_trade_until = None
        for as_of_date in checkpoints:
            if in_trade_until is not None and as_of_date <= in_trade_until:
                continue

            try:
                if condition_overrides:
                    with _condition_overrides(condition_overrides):
                        result = evaluate_as_of(ticker, as_of_date, bars_full, index_bars_full, sector_data_full)
                else:
                    result = evaluate_as_of(ticker, as_of_date, bars_full, index_bars_full, sector_data_full)
            except Exception as exc:
                print(f"[{ticker}] {as_of_date} evaluate_as_of failed — {exc}")
                continue

            if not conditions.is_actionable(result["conditions_met"]):
                continue

            breakout_idx = result.get("breakout_idx")
            if breakout_idx is None:
                continue

            entry_price = bars_full[breakout_idx]["close"]
            entry_date = bars_full[breakout_idx]["time"][:10]

            trade = simulate_trade(
                ticker, entry_date, entry_price, result["swing_stop"], result["swing_target"],
                bars_full, trailing_method=trailing_method, max_hold_weeks=max_hold_weeks,
            )
            if trade is None:
                continue

            trade["as_of_date"] = as_of_date
            trade["conditions_met"] = result["conditions_met"]
            trade["parameter_set"] = parameter_set
            trades.append(trade)
            db.insert_backtest_trade(trade)

            in_trade_until = trade["exit_date"] or end_date

    return trades
