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

# Pivot length used to find swing lows/highs to trail. Deliberately
# shorter than trend_support_resistance's TSR_PIVOT_LENGTH (20, tuned for
# resistance/support levels that need to be "major") — a trailing stop
# should pick up nearer-term swing points so it actually ratchets as a
# position develops, not just wait for a rare 20-week pivot.
SWING_TRAIL_PIVOT_LENGTH = 5


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
        if comfortably_above and (stop is None or ma_val > stop):
            stop = ma_val
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


def trailing_stop(bars, entry_price, entry_idx, method='ma', ma_period=30):
    """I compute both trailing-stop methods and return them together —
    `method` marks which one is treated as the recommended value for this
    call, but both are included so they can be compared against real
    output to see which behaves more sensibly.

    entry_price is accepted for interface symmetry with the short-side
    function and possible future use, but neither current method needs
    it — both are pure price-action reads (the MA level, or the most
    recent swing low), not distance-from-entry calculations.

    Returns None rather than a guessed value when entry_idx doesn't fall
    within the bars given, matching the rest of this project's standard
    for insufficient data.
    """
    if entry_idx is None or entry_idx < 0 or entry_idx >= len(bars):
        return None

    ma_stop = _trailing_ma_stop(bars, entry_idx, ma_period)
    swing_low_stop = _trailing_swing_low_stop(bars, entry_idx)
    recommended = ma_stop if method == 'ma' else swing_low_stop

    return {
        "ma_stop": ma_stop,
        "swing_low_stop": swing_low_stop,
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
