"""Initial and trailing stop-loss logic.

The short-side functions here are stop-ORDER logic only (where does a
buy-stop sit, and how does it trail as a short position works) — not the
short-selling checklist itself. That's a separate, not-yet-built set of
conditions (see conditions.py's module docstring): several of the long
checklist's rules don't just invert for shorts, so the short side isn't
built by negating these 9 conditions. This module only covers where to
place and move the stop once a position already exists, long or short.
"""
from . import moving_averages, trend_support_resistance

# My own reading of "comfortably above/below" the MA before a stop starts
# actively trailing it — the book describes the idea qualitatively, not a
# number. Below this buffer, the MA is too close to price to trail
# without getting stopped out on ordinary noise.
MA_TRAIL_BUFFER_PCT = 5.0

# How far BELOW the 30-week average the trailing stop actually sits.
#
# The book says to place the stop below the average, not on it. This code
# placed it exactly at the average, which is a materially tighter stop:
# any ordinary pullback that touches the line closes the position. That
# is the mechanism behind the worst measured behaviour in the project —
# across 1,168 stocks that rose more than 20% over the 2021-2026 window,
# averaging +270%, the system captured 5.0%. A capture rate of 2%.
# GOOGL in miniature: bought 280.64, stopped at 286.01 for +1.9%, then
# ran to 400 without us.
#
# The book is also explicit that while price is above a rising average in
# Stage 2 fashion, the position should be given plenty of room to gyrate.
# Zero preserves the old behaviour; this ships at zero until measured.
MA_STOP_BUFFER_PCT = 0.0

# Pivot length used to find swing lows/highs to trail. Deliberately
# shorter than trend_support_resistance's TSR_PIVOT_LENGTH (20, tuned for
# resistance/support levels that need to be "major") — a trailing stop
# should pick up nearer-term swing points so it actually ratchets as a
# position develops, not just wait for a rare 20-week pivot.
SWING_TRAIL_PIVOT_LENGTH = 5

# The book's own trailing rule, which is considerably more specific than
# "follow the moving average" and is the only one of the three methods
# here actually drawn from it.
#
# It waits for a substantial correction — it says at least 8 to 10
# percent — and then does *not* move the stop until the stock has ended
# that correction and rallied back close to its prior high. The level
# depends on where the correction low sits relative to the average: if
# breaking the low would also violate the 30-week MA, the stop goes under
# the low; if the low is above a rising MA, the stop goes under the MA
# instead, which gives the position room to gyrate.
#
# Then a deliberate change of tactics that the other methods have no
# equivalent for: once the MA stops rising and flattens, a Stage 3 top is
# probably forming, and the stop moves under the correction low even
# though that sits above the MA. That is the part that stops a winner
# handing back its gains, and its absence is my leading explanation for
# why letting a runner continue measured worse than taking the target.
MIN_CORRECTION_PCT = 8.0

# "Rallies back close to its prior peak" — the confirmation the book
# requires before the stop is actually moved. The threshold is mine; it
# describes the idea in words rather than numbers.
CORRECTION_RECOVERY_PCT = 3.0

# How flat the MA has to go before the aggressive Stage 3 tactic kicks
# in, measured over the same lookback conditions.py uses for its own
# slope reads so the two agree about what "rising" means.
MA_FLAT_LOOKBACK = 5
MA_FLAT_SLOPE_PCT = 0.5


def initial_stop(swing_stop):
    """The starting stop for a long position is just conditions.py's own
    swing_stop from the risk/reward read — this function exists so
    callers have one consistent entry point rather than reaching into
    conditions.py's internals directly. Not new logic.
    """
    return swing_stop


def short_initial_stop(swing_high):
    """Mirror of initial_stop for the short side: the starting buy-stop is
    the swing high from the short setup's own risk read.
    """
    return swing_high


def _trailing_ma_stop(bars, entry_idx, ma_period):
    """Trails the rising 30-week MA once price closes comfortably above
    it. The stop only ratchets up — it never steps down even if the MA
    dips for a bar or two.
    """
    closes = [b["close"] for b in bars]
    ma_series = moving_averages.sma(closes, ma_period)
    latest_idx = len(bars) - 1

    stop = None
    for idx in range(entry_idx, latest_idx + 1):
        ma_val = ma_series[idx]
        if ma_val is None:
            continue
        comfortably_above = closes[idx] > ma_val * (1 + MA_TRAIL_BUFFER_PCT / 100)
        level = ma_val * (1 - MA_STOP_BUFFER_PCT / 100)
        if comfortably_above and (stop is None or level > stop):
            stop = level
    return stop


def _trailing_swing_low_stop(bars, entry_idx):
    """Trails each new confirmed pivot low since entry. Ratchets up only —
    a later, lower pivot low never pulls the stop back down.
    """
    lows = [b["low"] for b in bars]
    latest_idx = len(bars) - 1
    pivots = trend_support_resistance.find_pivot_lows(lows, SWING_TRAIL_PIVOT_LENGTH)

    stop = None
    for idx, price in pivots:
        if idx < entry_idx or idx > latest_idx:
            continue
        if stop is None or price > stop:
            stop = price
    return stop


def _ma_is_rising(ma_series, idx):
    """Whether the average is still advancing, or has flattened into the
    higher-risk zone where the book tightens the stop.
    """
    prior = idx - MA_FLAT_LOOKBACK
    if prior < 0 or ma_series[idx] is None or ma_series[prior] is None or not ma_series[prior]:
        return None
    return (ma_series[idx] - ma_series[prior]) / ma_series[prior] * 100 > MA_FLAT_SLOPE_PCT


def _trailing_book_stop(bars, entry_idx, ma_period):
    """Trails the way the book describes: under corrections, confirmed by
    a recovery, and tightened once the average flattens.

    Only bars up to each point are used, and the level only ever moves
    up, so this is a stop that could actually have been resting in the
    market rather than one fitted after the fact.
    """
    closes = [b["close"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    ma_series = moving_averages.sma(closes, ma_period)
    latest_idx = len(bars) - 1

    stop = None
    peak = highs[entry_idx]
    correction_low = lows[entry_idx]

    for idx in range(entry_idx + 1, latest_idx + 1):
        peak = max(peak, highs[idx])
        correction_low = min(correction_low, lows[idx])

        if not peak:
            continue
        depth_pct = (peak - correction_low) / peak * 100
        recovered = closes[idx] >= peak * (1 - CORRECTION_RECOVERY_PCT / 100)

        # A correction only counts once it's deep enough *and* the stock
        # has climbed back toward its high. Raising on the way down would
        # be setting the stop into a decline still in progress.
        if depth_pct < MIN_CORRECTION_PCT or not recovered:
            continue

        ma_now = ma_series[idx]
        rising = _ma_is_rising(ma_series, idx)
        if ma_now is None or rising is None:
            level = correction_low
        elif rising and ma_now < correction_low:
            # The low sits above a rising average, so the average is the
            # more generous level and the position keeps its room.
            level = ma_now
        else:
            # Either breaking the low would breach the average anyway, or
            # the average has flattened and it's time to be aggressive.
            level = correction_low

        if stop is None or level > stop:
            stop = level
        # Start watching for the next correction from here.
        correction_low = lows[idx]

    return stop


def trailing_stop(bars, entry_price, entry_idx, method='ma', ma_period=30):
    """I compute every trailing-stop method and return them together —
    `method` marks which one is treated as the recommended value for this
    call, but all are included so they can be compared against real
    output rather than argued about.

    'book' is the only one drawn from the source: corrections, confirmed
    by a recovery, tightened once the average flattens. 'ma' simply
    follows the 30-week average and 'swing' follows confirmed pivot lows;
    both are mine, and both lack any notion of a top forming.

    entry_price is accepted for interface symmetry with the short-side
    function and possible future use, but none of the methods need it —
    they're pure price-action reads, not distance-from-entry
    calculations.

    Returns None rather than a guessed value when entry_idx doesn't fall
    within the bars given, matching the rest of this project's standard
    for insufficient data.
    """
    if entry_idx is None or entry_idx < 0 or entry_idx >= len(bars):
        return None

    ma_stop = _trailing_ma_stop(bars, entry_idx, ma_period)
    swing_low_stop = _trailing_swing_low_stop(bars, entry_idx)
    book_stop = _trailing_book_stop(bars, entry_idx, ma_period)

    recommended = {
        "ma": ma_stop,
        "swing": swing_low_stop,
        "book": book_stop,
    }.get(method, ma_stop)

    return {
        "ma_stop": ma_stop,
        "swing_low_stop": swing_low_stop,
        "book_stop": book_stop,
        "recommended": recommended,
        "method": method,
    }


def _trailing_ma_short_stop(bars, entry_idx, ma_period):
    """Mirror of _trailing_ma_stop for a short: trails the declining MA
    once price closes comfortably below it, ratcheting the buy-stop down
    only — it never steps back up.
    """
    closes = [b["close"] for b in bars]
    ma_series = moving_averages.sma(closes, ma_period)
    latest_idx = len(bars) - 1

    stop = None
    for idx in range(entry_idx, latest_idx + 1):
        ma_val = ma_series[idx]
        if ma_val is None:
            continue
        comfortably_below = closes[idx] < ma_val * (1 - MA_TRAIL_BUFFER_PCT / 100)
        if comfortably_below and (stop is None or ma_val < stop):
            stop = ma_val
    return stop


def _trailing_swing_high_stop(bars, entry_idx):
    """Mirror of _trailing_swing_low_stop for a short: trails each new
    confirmed pivot high since entry, ratcheting down only.
    """
    highs = [b["high"] for b in bars]
    latest_idx = len(bars) - 1
    pivots = trend_support_resistance.find_pivot_highs(highs, SWING_TRAIL_PIVOT_LENGTH)

    stop = None
    for idx, price in pivots:
        if idx < entry_idx or idx > latest_idx:
            continue
        if stop is None or price < stop:
            stop = price
    return stop


def short_trailing_stop(bars, entry_price, entry_idx, method='ma', ma_period=30):
    """Buy-stop for a short position: ratchets DOWN as price falls,
    trailing the declining MA or each new swing high instead of the rising
    MA/swing low a long position trails.

    This is its own function rather than the long-side trailing_stop()
    called with negated inputs — a buy-stop closing a short is a distinct
    order type from a sell-stop closing a long, per the book's own
    short-selling rules, not just a sign-flipped version of the same
    mechanism.
    """
    if entry_idx is None or entry_idx < 0 or entry_idx >= len(bars):
        return None

    ma_stop = _trailing_ma_short_stop(bars, entry_idx, ma_period)
    swing_high_stop = _trailing_swing_high_stop(bars, entry_idx)
    recommended = ma_stop if method == 'ma' else swing_high_stop

    return {
        "ma_stop": ma_stop,
        "swing_high_stop": swing_high_stop,
        "recommended": recommended,
        "method": method,
    }
