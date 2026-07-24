"""Ranks sectors by relative strength and builds a broader watchlist from
the top-ranked sectors' curated ticker universes, as an alternative to
running the screener against a fixed personal watchlist.
"""
import json
import os

from webull.data.common.category import Category

from . import data_fetch, sector_strength

SECTOR_UNIVERSE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "sector_universe"
)


def rank_sectors():
    """I run sector_strength.get_sector_strength_percentile() for every
    sector ETF in SECTOR_ETF_MAP (deduplicated, excluding the SPY
    fallback — ranking SPY against itself is meaningless), and return
    them sorted strongest to weakest.

    :return: list of {"sector_etf": ..., "percentile": ...} dicts, sorted
        descending by percentile. A sector is left out entirely if its
        percentile couldn't be computed (fetch failure, insufficient
        history) rather than sorted in with a guessed value.
    """
    spy_closes = data_fetch.get_spy_daily_closes()
    sector_etfs = sorted(
        set(sector_strength.SECTOR_ETF_MAP.values()) - {sector_strength.DEFAULT_SECTOR_ETF}
    )

    ranked = []
    for etf in sector_etfs:
        try:
            etf_closes = data_fetch.get_daily_closes(etf, Category.US_ETF.name)
            percentile = sector_strength.get_sector_strength_percentile(etf_closes, spy_closes)
        except Exception:
            percentile = None
        if percentile is not None:
            ranked.append({"sector_etf": etf, "percentile": percentile})

    ranked.sort(key=lambda r: r["percentile"], reverse=True)
    return ranked


def get_sector_universe(sector_etf, source="config"):
    """I return the curated ticker list for one sector ETF.

    :param source: only "config" is implemented right now — reads
        config/sector_universe/<sector_etf>.json, a static, manually
        curated list. Webull doesn't expose sector membership directly,
        so this isn't pulled live. Left as a parameter so a future
        live-lookup source can slot in later without changing callers.
    :return: list of ticker strings, or [] if no universe file exists
        for this sector yet.
    """
    if source != "config":
        raise ValueError(f"Unsupported source: {source!r}. Only 'config' is implemented.")

    path = os.path.join(SECTOR_UNIVERSE_DIR, f"{sector_etf}.json")
    if not os.path.exists(path):
        return []

    with open(path) as f:
        data = json.load(f)
    return data.get("tickers", [])


def build_watchlist_from_top_sectors(n=3):
    """I take the top `n` sectors from rank_sectors() and merge their
    curated universes into one deduplicated ticker list, strongest
    sector's tickers first.
    """
    top_sectors = rank_sectors()[:n]

    combined = []
    seen = set()
    for entry in top_sectors:
        for ticker in get_sector_universe(entry["sector_etf"]):
            if ticker not in seen:
                seen.add(ticker)
                combined.append(ticker)

    return combined
