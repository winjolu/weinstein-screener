"""Mansfield Relative Strength.

This mirrors the exact formula in pinescript/mansfield_rs.pine so the two
stay in sync: RS ratio is a security's close divided by an index's close on
the same bar, and MRS expresses today's ratio as a percentage gap from its
own SMA, so it oscillates around zero instead of drifting with price.
"""


def compute_mansfield_rs(security_closes, index_closes, period=52):
    """I return a list of MRS values aligned to security_closes/index_closes.

    Both inputs must be same-length sequences, oldest bar first. The first
    `period - 1` entries come back as None since there isn't a full SMA
    window yet, matching the Pine Script's `na` warm-up behavior.
    """
    if len(security_closes) != len(index_closes):
        raise ValueError("security_closes and index_closes must be the same length")

    rs_ratio = [s / i for s, i in zip(security_closes, index_closes)]

    mrs = [None] * len(rs_ratio)
    window_sum = 0.0
    for idx, ratio in enumerate(rs_ratio):
        window_sum += ratio
        if idx >= period:
            window_sum -= rs_ratio[idx - period]
        if idx >= period - 1:
            sma_rs = window_sum / period
            mrs[idx] = 100 * ((ratio / sma_rs) - 1)

    return mrs
