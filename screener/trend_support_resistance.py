"""Pivot-based support/resistance levels and trend lines.

IMPORTANT: this is my approximation of a third-party charting concept,
built from a feature description rather than verified source. The pivot
logic itself (a bar whose high/low is the local extreme within a fixed
window on each side) is a standard, well-known technique, but the exact
level-selection, tolerance, and trend-line rules below are my own
reasonable first pass — not a known-identical port. Treat every number
this module produces as directional, and expect this file to get
corrected once I have the real source to check it against.
"""


def find_pivot_highs(highs, pivot_length):
    """A pivot high at index i is a bar whose high is strictly greater than
    every bar's high within `pivot_length` bars on both sides. A pivot
    can't be confirmed until `pivot_length` bars after it exist, so the
    most recent `pivot_length` bars never produce a pivot.

    Returns a list of (index, price) tuples, oldest first.
    """
    pivots = []
    n = len(highs)
    for i in range(pivot_length, n - pivot_length):
        surrounding = highs[i - pivot_length:i] + highs[i + 1:i + pivot_length + 1]
        if surrounding and highs[i] > max(surrounding):
            pivots.append((i, highs[i]))
    return pivots


def find_pivot_lows(lows, pivot_length):
    """Mirror of find_pivot_highs for local minima."""
    pivots = []
    n = len(lows)
    for i in range(pivot_length, n - pivot_length):
        surrounding = lows[i - pivot_length:i] + lows[i + 1:i + pivot_length + 1]
        if surrounding and lows[i] < min(surrounding):
            pivots.append((i, lows[i]))
    return pivots


def get_resistance_level(highs, pivot_length, lookback_pivots=3):
    """Resistance = average of the most recent `lookback_pivots` pivot highs."""
    pivots = find_pivot_highs(highs, pivot_length)
    if not pivots:
        return None
    recent = pivots[-lookback_pivots:]
    return sum(price for _, price in recent) / len(recent)


def get_support_level(lows, pivot_length, lookback_pivots=3):
    """Support = average of the most recent `lookback_pivots` pivot lows."""
    pivots = find_pivot_lows(lows, pivot_length)
    if not pivots:
        return None
    recent = pivots[-lookback_pivots:]
    return sum(price for _, price in recent) / len(recent)


def get_trend_line(pivots, current_index):
    """Fits a line through the two most recent pivots and projects its
    value at current_index. Pass pivot lows for an uptrend line, pivot
    highs for a downtrend line.

    :return: {"slope": ..., "projected_value": ...} or None if there
        aren't at least 2 pivots to fit a line through.
    """
    if len(pivots) < 2:
        return None
    (i1, p1), (i2, p2) = pivots[-2], pivots[-1]
    if i2 == i1:
        return None
    slope = (p2 - p1) / (i2 - i1)
    projected_value = p2 + slope * (current_index - i2)
    return {"slope": slope, "projected_value": projected_value}


def count_level_tests(closes, level, set_at_index, direction, tolerance_pct=2.0):
    """Counts how many bars after `set_at_index` closed within
    `tolerance_pct` of `level` without it breaking, plus bars elapsed
    since the level was set.

    :param direction: "support" or "resistance" — determines which side
        of the level counts as a break.
    """
    if level is None or set_at_index is None:
        return {"tests": 0, "bars_since_set": 0, "broken": False}

    tests = 0
    broken = False
    for i in range(set_at_index + 1, len(closes)):
        price = closes[i]
        distance_pct = abs(price - level) / level * 100
        if distance_pct <= tolerance_pct:
            tests += 1
        if direction == "resistance" and price > level:
            broken = True
        elif direction == "support" and price < level:
            broken = True

    bars_since_set = max(0, len(closes) - 1 - set_at_index)
    return {"tests": tests, "bars_since_set": bars_since_set, "broken": broken}


def analyze(bars, pivot_length=5, lookback_pivots=3, tolerance_pct=2.0):
    """Runs the full pivot/level/trend-line read for one series of bars.

    See the module docstring — every value here is an approximation
    pending verified source, not a known-correct port.
    """
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    closes = [b["close"] for b in bars]

    pivot_highs = find_pivot_highs(highs, pivot_length)
    pivot_lows = find_pivot_lows(lows, pivot_length)

    resistance_level = get_resistance_level(highs, pivot_length, lookback_pivots)
    support_level = get_support_level(lows, pivot_length, lookback_pivots)

    resistance_set_at = pivot_highs[-1][0] if pivot_highs else None
    support_set_at = pivot_lows[-1][0] if pivot_lows else None

    resistance_tests = count_level_tests(
        closes, resistance_level, resistance_set_at, "resistance", tolerance_pct
    )
    support_tests = count_level_tests(
        closes, support_level, support_set_at, "support", tolerance_pct
    )

    # Picking whether we're currently reading an uptrend line (off pivot
    # lows) or a downtrend line (off pivot highs): whichever pair of
    # recent pivots is actually sloping the expected direction. If
    # neither is, I don't have a confident trend line to report.
    uptrend_line = get_trend_line(pivot_lows, len(closes) - 1)
    downtrend_line = get_trend_line(pivot_highs, len(closes) - 1)

    trend_line = None
    if uptrend_line and uptrend_line["slope"] > 0:
        trend_line = {"type": "support", **uptrend_line}
    elif downtrend_line and downtrend_line["slope"] < 0:
        trend_line = {"type": "resistance", **downtrend_line}

    return {
        "resistance_level": resistance_level,
        "support_level": support_level,
        "resistance_tests": resistance_tests,
        "support_tests": support_tests,
        "trend_line": trend_line,
        "pivot_highs": pivot_highs,
        "pivot_lows": pivot_lows,
    }
