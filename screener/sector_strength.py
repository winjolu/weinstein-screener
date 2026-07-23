"""Sector strength expressed as a percentile of daily outperformance
against SPY, rather than a single relative-return number.
"""


def get_sector_strength_percentile(sector_etf_closes, spy_closes, lookback=20):
    """I compute daily returns for the sector ETF and SPY over the last
    `lookback` trading days, then return the percentage of those days the
    sector ETF's return beat SPY's (0-100).

    Both inputs must be same-length daily close sequences, oldest first,
    with at least `lookback + 1` closes so day-over-day returns can be
    computed. Returns None if there isn't enough history.
    """
    if len(sector_etf_closes) != len(spy_closes):
        raise ValueError("sector_etf_closes and spy_closes must be the same length")
    if len(sector_etf_closes) < lookback + 1:
        return None

    sector_window = sector_etf_closes[-(lookback + 1):]
    spy_window = spy_closes[-(lookback + 1):]

    outperform_days = 0
    for i in range(1, len(sector_window)):
        sector_return = (sector_window[i] - sector_window[i - 1]) / sector_window[i - 1]
        spy_return = (spy_window[i] - spy_window[i - 1]) / spy_window[i - 1]
        if sector_return > spy_return:
            outperform_days += 1

    return 100 * outperform_days / lookback
