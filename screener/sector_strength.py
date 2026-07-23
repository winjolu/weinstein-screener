"""Sector strength as a momentum-of-relative-strength rank: how often the
sector-ETF/SPY ratio is higher today than it was on each of the last N
days, rather than a simple day-by-day outperformance count.
"""

# Sector name -> representative ETF, used so this project's sector
# classification lines up with what a real chart would show. This is
# reference data (a lookup table), not calculation logic.
SECTOR_ETF_MAP = {
    "Technology Services": "XLK",
    "Electronic Technology": "XLK",
    "Finance": "XLF",
    "Health Technology": "XLV",
    "Health Services": "XLV",
    "Retail Trade": "XLP",
    "Consumer Non-Durables": "XLP",
    "Energy Minerals": "XLE",
    "Producer Manufacturing": "XLI",
    "Consumer Services": "XLY",
    "Consumer Durables": "XLY",
    "Commercial Services": "XLI",
    "Industrial Services": "XLI",
    "Utilities": "XLU",
    "Transportation": "XLI",
    "Non-Energy Minerals": "XLB",
    "Process Industries": "XLB",
    "Communications": "XLC",
    "Distribution Services": "XLI",
    "Miscellaneous": "SPY",
}
DEFAULT_SECTOR_ETF = "SPY"


def get_sector_etf(sector_name):
    """Maps a sector name to its representative ETF, defaulting to SPY for
    anything not in the table (matching the reference lookup's fallback).
    """
    return SECTOR_ETF_MAP.get(sector_name, DEFAULT_SECTOR_ETF)


def get_sector_strength_percentile(sector_etf_closes, spy_closes, lookback=20):
    """I compute the sector-ETF/SPY ratio for each bar, then compare
    today's ratio against each of the last `lookback` bars' ratios and
    return what percentage of those comparisons came out higher (0-100).

    This is a momentum read on the ratio itself — "is today's relative
    strength elevated versus recent history" — not a count of how many
    individual days the sector ETF simply outperformed SPY day-over-day.
    Those are genuinely different numbers.

    Both inputs must be same-length close sequences, oldest first, with
    at least `lookback + 1` closes so the ratio has `lookback` prior
    values to compare against. Returns None if there isn't enough history.
    """
    if len(sector_etf_closes) != len(spy_closes):
        raise ValueError("sector_etf_closes and spy_closes must be the same length")
    if len(sector_etf_closes) < lookback + 1:
        return None

    rs_ratio = [s / i for s, i in zip(sector_etf_closes, spy_closes)]
    latest_ratio = rs_ratio[-1]

    higher_count = sum(1 for k in range(1, lookback + 1) if latest_ratio > rs_ratio[-1 - k])

    return 100 * higher_count / lookback
