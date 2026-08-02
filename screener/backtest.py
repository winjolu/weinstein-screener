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

3. The cap is 1200 bars on every timespan, measured 2026-07-28, and the
   worry recorded here was justified — it was worse than "None more
   often than it should be". The server refuses an oversized request
   outright rather than truncating it, so a backtest starting more than
   about 3.3 years back failed *every* sector fetch, not just the early
   ones, and a bare except turned that into a full run with condition 5
   unresolved at every checkpoint. data_fetch._capped() now clamps and
   warns, which restores the intended behaviour: sector-dependent
   conditions come back None only for checkpoints older than the ~4.8
   years of daily bars the cap allows. Weekly bars reach ~23 years, so
   condition 6 — the market-stage read, and the one a long backtest is
   really for — is unaffected.

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

# How much of a position comes off at the swing-rule target, with the
# rest left to the trailing stop. Half is the book's own figure — it says
# to take profits on only half the position when the target area is
# reached, and to sell the remainder when the stop is set off. One of the
# few numbers in this project I didn't have to invent.
PARTIAL_EXIT_FRACTION = 0.5


def _bar_index_on_or_before(bars_full, as_of_date):
    """Index of the last bar dated on or before as_of_date, or None."""
    found = None
    for idx, bar_ in enumerate(bars_full):
        if bar_["time"][:10] <= as_of_date:
            found = idx
        else:
            break
    return found


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


def _ma_at(bars, period):
    """The simple moving average on the last bar given, or None."""
    from . import moving_averages
    series = moving_averages.sma([b["close"] for b in bars], period)
    return series[-1] if series else None


def simulate_trade(ticker, entry_date, entry_price, swing_stop, swing_target, bars_full,
                    trailing_method='ma', max_hold_weeks=52,
                    partial_exit_fraction=None, take_profit_above_ma_pct=None,
                    stall_exit_weeks=None, stall_exit_min_gain_pct=0.0):
    """Walks forward week by week from entry_date, recomputing
    stop_loss.trailing_stop() using only bars up to and including each
    simulated week (a real trailing stop can only react to price action
    that's already happened by that week), and checks whether that
    week's low hit the current stop or its high hit swing_target.

    Reaching the target sells *part* of the position and lets the rest
    ride the trailing stop, which is what the book actually prescribes —
    it uses the swing-rule level for partial selling and takes the
    remainder off when the stop is hit. Exiting fully at the target, as
    this did before, truncated every winner at its measured objective
    and made the whole method look like a fixed-target system. It was
    the single largest distortion left in the backtest.

    When both could plausibly be hit in the same week, I check the stop
    first — weekly OHLC alone can't tell me the actual intraweek order,
    and assuming the stop hit first is the more conservative read.

    Running out of bars_full or reaching max_hold_weeks without the
    remainder closing both come back as "still_open", even when a
    partial profit was already banked: the trade's final number isn't
    known yet, and counting an unrealised remainder would flatter it.

    `stall_exit_weeks` is the one exit here that sells on *time* rather
    than on price. If the position is still open that many weeks in and
    hasn't cleared `stall_exit_min_gain_pct`, it closes at that week's
    close. Every other exit in this function waits for price to come to
    it, so a trade that simply goes sideways ties up capital forever —
    and with the hold cap removed, "forever" is literal. This is the
    registered R6 arm, unbuilt until now.

    It deliberately does not fire once a partial has been banked: at
    that point the position has already proved itself and the remainder
    is the trailing stop's business.

    :return: trade dict, or None if entry_date has no matching bar.
        return_pct and r_multiple are position-weighted across both legs.
    """
    # Resolved here rather than as a default argument. A default binds
    # once at definition time, so patching the module constant to A/B the
    # exit policy silently did nothing and both arms of the comparison
    # ran identically — which reads as "this change makes no difference"
    # rather than as a broken experiment.
    if partial_exit_fraction is None:
        partial_exit_fraction = PARTIAL_EXIT_FRACTION

    dates = [b["time"][:10] for b in bars_full]
    try:
        entry_idx = dates.index(entry_date)
    except ValueError:
        return None

    stop = stop_loss.initial_stop(swing_stop)
    last_idx = min(entry_idx + max_hold_weeks, len(bars_full) - 1)
    risk = entry_price - swing_stop if swing_stop is not None else None

    partial_idx = None
    partial_price = None
    exit_idx = None
    exit_price = None
    stalled = False

    for idx in range(entry_idx + 1, last_idx + 1):
        bars_so_far = bars_full[:idx + 1]
        trail = stop_loss.trailing_stop(bars_so_far, entry_price, entry_idx, method=trailing_method)
        if trail and trail["recommended"] is not None:
            if stop is None or trail["recommended"] > stop:
                stop = trail["recommended"]

        bar = bars_full[idx]
        if stop is not None and bar["low"] <= stop:
            exit_idx, exit_price = idx, stop
            break
        if (
            swing_target is not None
            and partial_idx is None
            and bar["high"] >= swing_target
        ):
            # Bank part of it and keep going; the rest belongs to the
            # trailing stop now.
            partial_idx, partial_price = idx, swing_target
        elif (
            take_profit_above_ma_pct is not None
            and partial_idx is None
        ):
            # The book's second rule about stocks far above their average,
            # and the one I'd missed. Its answer to a position that has
            # skyrocketed is not "don't buy" — that's the entry rule — but
            # "lock in the gain on part of it and ride the rest with a
            # trailing stop". This is the only intervention tested here
            # that removes no trades, so unlike every filter tried so far
            # it cannot destroy the winners by excluding them.
            ma_now = _ma_at(bars_so_far, conditions.MA_PERIOD)
            if ma_now and (bar["high"] / ma_now - 1) * 100 >= take_profit_above_ma_pct:
                partial_idx = idx
                partial_price = ma_now * (1 + take_profit_above_ma_pct / 100)

        # Checked last, so the stop and the target both get the week
        # first. A stall exit is the weakest claim on the position of
        # the three — it isn't reacting to anything price did, only to
        # how long price has done nothing.
        if (
            stall_exit_weeks is not None
            and partial_idx is None
            and idx - entry_idx >= stall_exit_weeks
            and (bar["close"] - entry_price) / entry_price * 100 < stall_exit_min_gain_pct
        ):
            exit_idx, exit_price = idx, bar["close"]
            stalled = True
            break

    took_partial = partial_idx is not None
    remainder_closed = exit_idx is not None

    if not remainder_closed:
        return {
            "ticker": ticker,
            "entry_date": entry_date,
            "entry_price": entry_price,
            "exit_date": None,
            "exit_price": None,
            "exit_reason": "target_then_open" if took_partial else "still_open",
            "return_pct": None,
            "r_multiple": None,
            "still_open": True,
        }

    if took_partial:
        held = 1.0 - partial_exit_fraction
        blended_exit = partial_exit_fraction * partial_price + held * exit_price
        exit_reason = "target_then_stop"
    else:
        blended_exit = exit_price
        exit_reason = "stall" if stalled else "stop"

    return {
        "ticker": ticker,
        "entry_date": entry_date,
        "entry_price": entry_price,
        "exit_date": bars_full[exit_idx]["time"][:10],
        "exit_price": blended_exit,
        "exit_reason": exit_reason,
        "return_pct": (blended_exit - entry_price) / entry_price * 100,
        "r_multiple": (blended_exit - entry_price) / risk if risk and risk > 0 else None,
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
                  trailing_method='ma', max_hold_weeks=52, bars_by_symbol=None,
                  fetch_sector=True, entry_at="signal",
                  take_profit_above_ma_pct=None,
                  stall_exit_weeks=None, stall_exit_min_gain_pct=0.0,
                  **condition_overrides):
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

    :param bars_by_symbol: optional {symbol: bars} read instead of the
        API — normally bar_cache.load(). Network was the dominant cost of
        a wide run, and it was spent re-fetching history already on disk;
        a few thousand names is hours of transfer for nothing. Symbols
        absent from the mapping are skipped rather than fetched, so a
        partial cache silently shrinks the universe instead of quietly
        going back to the network.
    :param entry_at: "signal" (default) fills at the checkpoint the signal
        fired on — the price actually available when the screener said
        buy. "breakout" fills at the breakout bar instead, which models
        the book's workflow of leaving resting buy-stop orders on a
        pre-identified watchlist. The latter is only honest if such a
        watchlist exists, and this screener doesn't maintain one: it
        scans for breakouts that have already happened. Kept so earlier
        results can be reproduced, not because both are equally valid
        here.
    :param fetch_sector: set False to skip the per-ticker sector lookup
        and run an eight-condition checklist. Sector strength needs daily
        bars, which the server caps at ~4.8 years, so for any window
        starting before roughly 2021 condition 5 cannot resolve anyway —
        fetching it spends one call per ticker to learn nothing. Turning
        it off is honest about that rather than paying for it.
    :param stall_exit_weeks: sell a position that is still open this many
        weeks in and hasn't cleared stall_exit_min_gain_pct. Off by
        default. This is the only exit that frees capital on its own
        schedule rather than waiting for price, which matters once
        max_hold_weeks is loosened — see simulate_trade().
    :param condition_overrides: passed to conditions.py's module-level
        constants for the duration of this run only — see
        _condition_overrides(). Example: TSR_PIVOT_LENGTH=10.
    :return: list of trade-result dicts, each tagged with
        "parameter_set", "as_of_date", and "conditions_met".
    """
    lookback_weeks = _lookback_weeks_needed(start_date)
    lookback_days = (datetime.date.today() - datetime.date.fromisoformat(start_date)).days + 45

    checkpoints = _checkpoint_dates(start_date, end_date, check_interval_weeks)

    if bars_by_symbol is not None and "SPY" in bars_by_symbol:
        index_bars_full = bars_by_symbol["SPY"]
    else:
        index_bars_full = data_fetch.get_index_bars("SPY", lookback_weeks=lookback_weeks)

    empty_sector = {"sector": None, "sector_etf_bars": [], "spy_bars": []}
    skipped = 0

    trades = []
    for ticker in tickers:
        if bars_by_symbol is not None:
            bars_full = bars_by_symbol.get(ticker)
            if not bars_full:
                skipped += 1
                continue
            sector_data_full = (
                data_fetch.get_sector_data_for_backtest(ticker, lookback_days)
                if fetch_sector else empty_sector
            )
        else:
            try:
                bars_full = data_fetch.get_weekly_bars(ticker, lookback_weeks=lookback_weeks)
                sector_data_full = (
                    data_fetch.get_sector_data_for_backtest(ticker, lookback_days)
                    if fetch_sector else empty_sector
                )
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

            if not result["actionable"]:
                continue

            breakout_idx = result.get("breakout_idx")
            if breakout_idx is None:
                continue

            if entry_at == "breakout":
                entry_idx = breakout_idx
            else:
                # The bar the signal actually fired on. Anything else is a
                # price you could no longer get: a scan finds a breakout a
                # median of four weeks after it happened, and filling at
                # the old level books a rise that had already occurred.
                # Measured across the 273-trade study, that phantom gain
                # was worth +1.11 points a trade — which was the whole of
                # the measured edge, turning +$2,729 into -$296.
                entry_idx = _bar_index_on_or_before(bars_full, as_of_date)
                if entry_idx is None or entry_idx < breakout_idx:
                    continue

            entry_price = bars_full[entry_idx]["close"]
            entry_date = bars_full[entry_idx]["time"][:10]

            trade = simulate_trade(
                ticker, entry_date, entry_price, result["swing_stop"], result["swing_target"],
                bars_full, trailing_method=trailing_method, max_hold_weeks=max_hold_weeks,
                take_profit_above_ma_pct=take_profit_above_ma_pct,
                stall_exit_weeks=stall_exit_weeks,
                stall_exit_min_gain_pct=stall_exit_min_gain_pct,
            )
            if trade is None:
                continue

            trade["as_of_date"] = as_of_date
            trade["conditions_met"] = result["conditions_met"]
            trade["parameter_set"] = parameter_set
            trades.append(trade)
            db.insert_backtest_trade(trade)

            in_trade_until = trade["exit_date"] or end_date

    if skipped:
        # Said out loud on purpose. A name missing from the cache
        # contributes no trades and looks identical to one that simply
        # never qualified, which is the silent-exclusion failure this
        # project has now hit in the universe pagination, the batch
        # fetcher and the sector lookup.
        print(f"{skipped} of {len(tickers)} tickers had no cached bars and were skipped")

    return trades


def simulate_short_trade(ticker, entry_date, entry_price, buy_stop, target, bars_full,
                          trailing_method='ma', max_hold_weeks=52,
                          partial_exit_fraction=None):
    """Mirror of simulate_trade for a short position.

    Its own function rather than simulate_trade with negated inputs. A
    buy-stop closing a short is a different order from a sell-stop
    closing a long, and the geometry inverts in ways sign-flipping gets
    subtly wrong: the stop sits *above* entry and ratchets *down*, the
    target sits *below*, and profit is (entry - exit) rather than
    (exit - entry).

    Losses are bounded here exactly as they are on the long side. A short
    at 40 with a buy-stop at 44 risks 10%, the same as a long at 40 with
    a sell-stop at 36 — the book says so directly, and the "unlimited
    risk" framing simply doesn't survive a protective stop being present.
    """
    if partial_exit_fraction is None:
        partial_exit_fraction = PARTIAL_EXIT_FRACTION

    dates = [b["time"][:10] for b in bars_full]
    try:
        entry_idx = dates.index(entry_date)
    except ValueError:
        return None

    stop = buy_stop
    last_idx = min(entry_idx + max_hold_weeks, len(bars_full) - 1)

    partial_idx = partial_price = exit_idx = exit_price = None

    for idx in range(entry_idx + 1, last_idx + 1):
        bars_so_far = bars_full[:idx + 1]
        trail = stop_loss.short_trailing_stop(
            bars_so_far, entry_price, entry_idx, method=trailing_method)
        if trail and trail.get("recommended") is not None:
            # Ratchets DOWN only — the mirror of the long side's
            # up-only rule, and the reason this can't be sign-flipped.
            if stop is None or trail["recommended"] < stop:
                stop = trail["recommended"]

        bar = bars_full[idx]
        if stop is not None and bar["high"] >= stop:
            exit_idx, exit_price = idx, stop
            break
        if target is not None and partial_idx is None and bar["low"] <= target:
            partial_idx, partial_price = idx, target

    if exit_idx is None:
        exit_idx = last_idx
        exit_price = bars_full[last_idx]["close"]
        still_open = True
        exit_reason = "still_open"
    else:
        still_open = False
        exit_reason = "target_then_stop" if partial_idx is not None else "stop"

    if partial_idx is not None and not still_open:
        blended = (partial_price * partial_exit_fraction
                   + exit_price * (1 - partial_exit_fraction))
    else:
        blended = exit_price

    # Profit on a short is entry minus exit.
    return_pct = (entry_price - blended) / entry_price * 100 if entry_price else None
    risk = buy_stop - entry_price if buy_stop is not None else None
    r_multiple = ((entry_price - blended) / risk) if risk else None

    return {
        "ticker": ticker,
        "entry_date": entry_date,
        "entry_price": entry_price,
        "exit_date": bars_full[exit_idx]["time"][:10],
        "exit_price": blended,
        "exit_reason": exit_reason,
        "return_pct": return_pct,
        "r_multiple": r_multiple,
        "still_open": still_open,
        "direction": "short",
    }


def run_short_backtest(tickers, start_date, end_date, check_interval_weeks=4,
                        parameter_set="short_baseline", max_hold_weeks=52,
                        bars_by_symbol=None, fetch_sector=True):
    """The short-side mirror of run_backtest.

    Structurally the same walk — checkpoints, one position at a time per
    ticker, entry at the bar the signal fired on — but evaluating the
    short checklist and simulating a short position.

    `direction` isn't a column on backtest_trades, which holds real
    history and isn't in the rebuildable set, so a schema change would
    need a migration. Short runs are distinguished by their
    parameter_set name instead, which is enough for every reader that
    exists.
    """
    from . import short_conditions

    lookback_weeks = _lookback_weeks_needed(start_date)
    lookback_days = (datetime.date.today() - datetime.date.fromisoformat(start_date)).days + 45
    checkpoints = _checkpoint_dates(start_date, end_date, check_interval_weeks)

    if bars_by_symbol is not None and "SPY" in bars_by_symbol:
        index_bars_full = bars_by_symbol["SPY"]
    else:
        index_bars_full = data_fetch.get_index_bars("SPY", lookback_weeks=lookback_weeks)

    empty_sector = {"sector": None, "sector_etf_bars": [], "spy_bars": []}
    trades = []
    skipped = 0

    for ticker in tickers:
        if bars_by_symbol is not None:
            bars_full = bars_by_symbol.get(ticker)
            if not bars_full:
                skipped += 1
                continue
            sector_data_full = (
                data_fetch.get_sector_data_for_backtest(ticker, lookback_days)
                if fetch_sector else empty_sector
            )
        else:
            try:
                bars_full = data_fetch.get_weekly_bars(ticker, lookback_weeks=lookback_weeks)
                sector_data_full = (
                    data_fetch.get_sector_data_for_backtest(ticker, lookback_days)
                    if fetch_sector else empty_sector
                )
            except Exception as exc:
                print(f"[{ticker}] short backtest skipped — fetch failed: {exc}")
                continue

        in_trade_until = None
        for as_of_date in checkpoints:
            if in_trade_until is not None and as_of_date <= in_trade_until:
                continue

            bars = _truncate_bars(bars_full, as_of_date)
            index_bars = _truncate_bars(index_bars_full, as_of_date)
            sector_data = {
                "sector": sector_data_full.get("sector"),
                "sector_strength_pct": None,
                "sector_etf_closes": [b["close"] for b in
                                      _truncate_bars(sector_data_full.get("sector_etf_bars") or [],
                                                     as_of_date)],
                "spy_daily_closes": [b["close"] for b in
                                     _truncate_bars(sector_data_full.get("spy_bars") or [],
                                                    as_of_date)],
            }
            try:
                result = short_conditions.evaluate_short_conditions(
                    ticker, bars, index_bars, sector_data)
            except Exception as exc:
                print(f"[{ticker}] {as_of_date} short evaluation failed — {exc}")
                continue

            if not result["scoring"]["actionable"]:
                continue
            if result["buy_stop"] is None:
                continue

            entry_idx = _bar_index_on_or_before(bars_full, as_of_date)
            if entry_idx is None:
                continue
            entry_price = bars_full[entry_idx]["close"]
            if result["buy_stop"] <= entry_price:
                # A protective stop has to sit above a short's entry. If
                # the level read puts it below, the setup is malformed
                # rather than merely unattractive — skip rather than
                # inventing a stop.
                continue

            trade = simulate_short_trade(
                ticker, bars_full[entry_idx]["time"][:10], entry_price,
                result["buy_stop"], result["target"], bars_full,
                max_hold_weeks=max_hold_weeks)
            if trade is None:
                continue

            trade["as_of_date"] = as_of_date
            trade["conditions_met"] = result["conditions_met"]
            trade["parameter_set"] = parameter_set
            trades.append(trade)
            db.insert_backtest_trade(trade)
            in_trade_until = trade["exit_date"] or end_date

    if skipped:
        print(f"{skipped} of {len(tickers)} tickers had no cached bars and were skipped")
    return trades
