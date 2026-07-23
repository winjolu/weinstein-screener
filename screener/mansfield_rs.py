"""Mansfield Relative Strength.

This mirrors the exact formula in pinescript/mansfield_rs.pine so the two
stay in sync: RS ratio is a security's close divided by an index's close on
the same bar, and MRS expresses today's ratio as a percentage gap from its
own SMA, so it oscillates around zero instead of drifting with price.
"""


def compute_mansfield_rs(security_closes, index_closes, period=52, rs_ma_trend_lookback=5):
    """I return (mrs, rs_ma_rising) for security_closes/index_closes.

    Both inputs must be same-length sequences, oldest bar first.

    mrs is a list aligned to the inputs; the first `period - 1` entries
    come back as None since there isn't a full SMA window yet, matching
    the Pine Script's `na` warm-up behavior. This part of the math is
    unchanged from the verified version.

    rs_ma_rising is a single boolean (or None if there isn't enough
    warmed-up history to compare): whether the RS ratio's own SMA — the
    denominator in the MRS formula — is trending upward over the last
    `rs_ma_trend_lookback` bars. This is a distinct signal from mrs
    itself: a stock can show a positive MRS breakout while the RS-MA
    underneath it is still declining, which reads very differently on
    the chart than a breakout under a rising RS-MA.
    """
    if len(security_closes) != len(index_closes):
        raise ValueError("security_closes and index_closes must be the same length")

    rs_ratio = [s / i for s, i in zip(security_closes, index_closes)]

    mrs = [None] * len(rs_ratio)
    sma_rs_series = [None] * len(rs_ratio)
    window_sum = 0.0
    for idx, ratio in enumerate(rs_ratio):
        window_sum += ratio
        if idx >= period:
            window_sum -= rs_ratio[idx - period]
        if idx >= period - 1:
            sma_rs = window_sum / period
            sma_rs_series[idx] = sma_rs
            mrs[idx] = 100 * ((ratio / sma_rs) - 1)

    latest = len(sma_rs_series) - 1
    compare_idx = latest - rs_ma_trend_lookback
    if (
        compare_idx >= 0
        and sma_rs_series[latest] is not None
        and sma_rs_series[compare_idx] is not None
    ):
        rs_ma_rising = sma_rs_series[latest] > sma_rs_series[compare_idx]
    else:
        rs_ma_rising = None

    return mrs, rs_ma_rising
