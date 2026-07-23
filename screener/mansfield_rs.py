"""Mansfield Relative Strength.

This mirrors the exact formula in pinescript/mansfield_rs.pine so the two
stay in sync: RS ratio is a security's close divided by an index's close on
the same bar, and MRS expresses today's ratio as a percentage gap from its
own SMA, so it oscillates around zero instead of drifting with price.
"""


def compute_mansfield_rs(security_closes, index_closes, period=52, rs_ma_trend_lookback=1):
    """I return (mrs, rs_ma_rising) for security_closes/index_closes.

    Both inputs must be same-length sequences, oldest bar first.

    mrs is a list aligned to the inputs; the first `period - 1` entries
    come back as None since there isn't a full SMA window yet. This part
    of the math is verified correct: the reference calculation scales the
    raw ratio by a constant (multiplies it by 100 before taking its own
    SMA) purely for display purposes, but that constant cancels out
    identically in the final ((ratio / SMA) - 1) * 100 expression — it has
    zero effect on mrs, so I don't apply it here.

    rs_ma_rising is a single boolean (or None if there isn't enough
    warmed-up history to compare): whether the RS ratio's own SMA — the
    denominator in the MRS formula — is higher than it was
    `rs_ma_trend_lookback` bars ago. The reference calculation for this
    flag is a strict single-bar-over-bar comparison (this bar's SMA vs.
    the immediately preceding bar's SMA), which is exactly what the
    default of 1 reproduces. Raising this above 1 is a deliberate
    departure from that verified behavior, not an equivalent multi-bar
    smoothing of it — a "rising for N bars" check and a plain
    N-bars-back comparison only happen to be the same thing when N=1.
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
