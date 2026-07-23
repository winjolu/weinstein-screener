"""Pivot-based support/resistance levels and trend lines.

Verified against a real chart script's calculation methods (not its
drawing/label/alert code): pivot detection — a bar's high/low strictly
exceeding every bar within a fixed window on both sides, only confirmed
once that many bars have passed since — and a violation-count validation
model. A candidate level or line only counts as valid if price hasn't
broken through it, except within a small grace window of the most recent
bars, which are excluded from the violation count so a live test in
progress doesn't instantly disqualify the level. Defaults below (20-bar
pivot window, 3 points considered per candidate, 0 violations allowed, a
3-bar exception window) match that script's own defaults.

What's NOT verified, because the relevant code wasn't available to check
against: the reference script can apparently display several valid
levels/lines at once, built through a point-pair combination step I
didn't have source for. Wherever more than one candidate is valid here,
I pick the most recently anchored one as a single representative value —
that selection rule is my own choice, not a confirmed match.

One more open question worth flagging: the pivot-window default was
written for whatever chart resolution someone runs it on, and I don't
know whether the real usage is on a daily or weekly chart. This project
always passes weekly bars, and a 20-bar pivot window on weekly data is a
very long, strict requirement — about 20 weeks of quiet on each side of
a pivot — so it may surface far fewer pivots here than the same setting
would on a daily chart. Worth checking real output once this runs
against actual data, and adjusting pivot_length if it comes back empty
too often.
"""


def find_pivot_highs(highs, pivot_length):
    """A pivot high at index i is a bar whose high is strictly greater than
    every bar's high within `pivot_length` bars on both sides. A pivot
    can't be confirmed until `pivot_length` bars after it exist, so the
    most recent `pivot_length` bars never produce a pivot. This part is
    a verified match to the reference calculation.

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


def _line_price_at(line, idx):
    """Linear extrapolation of a two-point line to any bar index."""
    return line["p1"] + line["slope"] * (idx - line["i1"])


def _count_resistance_violations(highs, level, set_idx, except_bars):
    """Bars whose high closed above a fixed resistance price, checked from
    the level's own bar through `except_bars` bars before the latest bar —
    the most recent `except_bars` bars are excluded from the count.
    """
    latest = len(highs) - 1
    history_reference = latest - set_idx
    if except_bars >= history_reference:
        return 0
    count = 0
    for idx in range(set_idx, latest - except_bars + 1):
        if highs[idx] > level:
            count += 1
    return count


def _count_support_violations(lows, level, set_idx, except_bars):
    """Mirror of _count_resistance_violations for a fixed support price."""
    latest = len(lows) - 1
    history_reference = latest - set_idx
    if except_bars >= history_reference:
        return 0
    count = 0
    for idx in range(set_idx, latest - except_bars + 1):
        if lows[idx] < level:
            count += 1
    return count


def _count_highs_above_line(highs, line, except_bars):
    """Same violation model as _count_resistance_violations, but against a
    sloped line's projected price at each bar rather than a fixed level —
    used for a downtrend line drawn through pivot highs.
    """
    latest = len(highs) - 1
    set_idx = line["i1"]
    history_reference = latest - set_idx
    if except_bars >= history_reference:
        return 0
    count = 0
    for idx in range(set_idx, latest - except_bars + 1):
        if highs[idx] > _line_price_at(line, idx):
            count += 1
    return count


def _count_lows_below_line(lows, line, except_bars):
    """Used for an uptrend line drawn through pivot lows."""
    latest = len(lows) - 1
    set_idx = line["i1"]
    history_reference = latest - set_idx
    if except_bars >= history_reference:
        return 0
    count = 0
    for idx in range(set_idx, latest - except_bars + 1):
        if lows[idx] < _line_price_at(line, idx):
            count += 1
    return count


def _select_level(pivots, points_to_check, max_violation, except_bars, prices, direction):
    """Considers only the most recent `points_to_check` pivots as level
    candidates, and returns the most recent one whose violation count is
    within `max_violation` — or None if none qualify.
    """
    candidates = pivots[-points_to_check:]
    for idx, price in reversed(candidates):
        if direction == "resistance":
            violations = _count_resistance_violations(prices, price, idx, except_bars)
        else:
            violations = _count_support_violations(prices, price, idx, except_bars)
        if violations <= max_violation:
            return {"level": price, "set_at_index": idx, "violations": violations}
    return None


def _build_trend_line_candidates(pivots):
    """All pairwise combinations among the given pivots, each kept as a
    two-point line in slope/intercept form.
    """
    candidates = []
    for a in range(len(pivots)):
        for b in range(a + 1, len(pivots)):
            i1, p1 = pivots[a]
            i2, p2 = pivots[b]
            if i2 == i1:
                continue
            slope = (p2 - p1) / (i2 - i1)
            candidates.append({"i1": i1, "p1": p1, "i2": i2, "p2": p2, "slope": slope})
    return candidates


def _select_trend_line(pivots, points_to_check, max_violation, except_bars, prices, direction):
    """
    :param direction: "support" (an uptrend line through pivot lows — the
        second point must be higher than the first, validated against
        lows breaking below it) or "resistance" (a downtrend line through
        pivot highs — the second point must be lower than the first,
        validated against highs breaking above it).
    """
    recent_pivots = pivots[-points_to_check:]
    candidates = _build_trend_line_candidates(recent_pivots)

    valid = []
    for line in candidates:
        if direction == "support":
            if line["p2"] <= line["p1"]:
                continue
            violations = _count_lows_below_line(prices, line, except_bars)
        else:
            if line["p2"] >= line["p1"]:
                continue
            violations = _count_highs_above_line(prices, line, except_bars)
        if violations <= max_violation:
            valid.append({**line, "violations": violations})

    if not valid:
        return None

    # See the module docstring: picking the most recently anchored valid
    # line as the single representative value is my own tie-break.
    valid.sort(key=lambda l: (l["i2"], l["i1"]))
    return valid[-1]


def analyze(bars, pivot_length=20, points_to_check=3, max_violation=0, except_bars=3):
    """Runs the full pivot/level/trend-line read for one series of bars.

    See the module docstring for what's verified here versus what's my
    own reasonable choice pending source I don't have.
    """
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]

    pivot_highs = find_pivot_highs(highs, pivot_length)
    pivot_lows = find_pivot_lows(lows, pivot_length)

    resistance = _select_level(pivot_highs, points_to_check, max_violation, except_bars, highs, "resistance")
    support = _select_level(pivot_lows, points_to_check, max_violation, except_bars, lows, "support")

    uptrend_line = _select_trend_line(pivot_lows, points_to_check, max_violation, except_bars, lows, "support")
    downtrend_line = _select_trend_line(pivot_highs, points_to_check, max_violation, except_bars, highs, "resistance")

    trend_line = None
    latest_idx = len(bars) - 1
    if uptrend_line:
        trend_line = {
            "type": "support",
            **uptrend_line,
            "projected_value": _line_price_at(uptrend_line, latest_idx),
        }
    elif downtrend_line:
        trend_line = {
            "type": "resistance",
            **downtrend_line,
            "projected_value": _line_price_at(downtrend_line, latest_idx),
        }

    return {
        "resistance_level": resistance["level"] if resistance else None,
        "resistance_violations": resistance["violations"] if resistance else None,
        "resistance_set_at_index": resistance["set_at_index"] if resistance else None,
        "support_level": support["level"] if support else None,
        "support_violations": support["violations"] if support else None,
        "support_set_at_index": support["set_at_index"] if support else None,
        "trend_line": trend_line,
        "pivot_highs": pivot_highs,
        "pivot_lows": pivot_lows,
    }
