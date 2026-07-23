"""Rolling historical high/low levels over configurable lookback windows."""

DEFAULT_WINDOWS = {
    # Expressed in bar counts, not calendar time. These assume weekly
    # bars, so "5D" is approximated as the single most recent weekly bar —
    # weekly OHLCV can't give a true 5-trading-day high/low, only daily
    # bars would have that precision.
    "5D": 1,
    "2W": 2,
    "52W": 52,
    "all_time": None,  # None means "every bar passed in"
}


def get_historical_high_low(bars, windows=None):
    """I return the highest high and lowest low over each rolling window.

    :param bars: OHLCV dicts, oldest first.
    :param windows: {label: bar_count}, where bar_count=None means "all
        bars". Defaults to DEFAULT_WINDOWS.
    :return: {label: {"high": ..., "low": ...}}
    """
    if windows is None:
        windows = DEFAULT_WINDOWS

    result = {}
    for label, window in windows.items():
        subset = bars if window is None else bars[-window:]
        if not subset:
            result[label] = {"high": None, "low": None}
            continue
        result[label] = {
            "high": max(b["high"] for b in subset),
            "low": min(b["low"] for b in subset),
        }
    return result
