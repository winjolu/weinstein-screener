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
