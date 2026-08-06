"""Standard moving averages — nothing proprietary, just the textbook math."""


def sma(values, period):
    """Simple moving average. Same-length output list, None during warm-up."""
    result = [None] * len(values)
    window_sum = 0.0
    for i, v in enumerate(values):
        window_sum += v
        if i >= period:
            window_sum -= values[i - period]
        if i >= period - 1:
            result[i] = window_sum / period
    return result


def wma(values, period):
    """Linearly weighted moving average: the most recent bar in the window
    gets weight `period`, the oldest bar in the window gets weight 1.
    Same-length output list, None during warm-up.
    """
    result = [None] * len(values)
    weight_sum = period * (period + 1) / 2
    for i in range(len(values)):
        if i < period - 1:
            continue
        window = values[i - period + 1:i + 1]
        weighted = sum(v * (position + 1) for position, v in enumerate(window))
        result[i] = weighted / weight_sum
    return result

def ema(values, period):
    """Exponentially weighted moving average, smoothing 2/(period+1).

    Seeded with the simple average of the first `period` values rather
    than with the first value alone. Both are in common use and they
    disagree for a surprisingly long time — seeding from a single bar
    leaves a visible error hundreds of bars later on a long series, which
    on a 200-day average is most of a backtest window. The SMA seed is
    what charting packages use, and matching them is the point: a
    threshold calibrated here has to mean the same thing on a screen.

    Same-length output list, None during warm-up, so it lines up with
    sma() and wma() and can be swapped for either without the caller
    knowing which it asked for.
    """
    if period <= 0:
        raise ValueError("period must be positive")
    result = [None] * len(values)
    if len(values) < period:
        return result
    seed = sum(values[:period]) / period
    result[period - 1] = seed
    k = 2.0 / (period + 1)
    previous = seed
    for i in range(period, len(values)):
        previous = values[i] * k + previous * (1 - k)
        result[i] = previous
    return result
