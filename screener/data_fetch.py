"""Wraps the official Webull OpenAPI Python SDK for the bars, index, and
sector data this screener needs. See docs/webull-api-reference.md for the
endpoints in use, and the SDK's own source (webull-inc/webull-openapi-python-sdk
on GitHub) for the client classes referenced below — the hosted docs don't
show Market Data client code directly, so I confirmed these against the SDK
source itself.
"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from webull.core.client import ApiClient
from webull.data.data_client import DataClient
from webull.data.common.category import Category
from webull.data.common.timespan import Timespan

_data_client = None


def _get_client():
    """I lazily build one DataClient per process from the .env credentials."""
    global _data_client
    if _data_client is None:
        app_key = os.environ.get("WEBULL_APP_KEY")
        app_secret = os.environ.get("WEBULL_APP_SECRET")
        if not app_key or not app_secret:
            raise RuntimeError(
                "WEBULL_APP_KEY/WEBULL_APP_SECRET are not set. Copy .env.example to "
                ".env and fill in real credentials before running the screener."
            )
        api_client = ApiClient(app_key, app_secret, "us")
        _data_client = DataClient(api_client)
    return _data_client


def _bars_from_response(response, symbol):
    """I unpack a batch-bars response into OHLCV dicts, oldest bar first.

    I'm assuming Webull returns bars newest-first, matching how most vendors'
    "last N bars" endpoints behave, and reverse here so index -1 is always
    the latest bar. I haven't confirmed this against a live response yet —
    worth double-checking the first time this runs for real.
    """
    payload = response.json()
    bars = []
    for entry in payload.get("result", []):
        if entry.get("symbol") == symbol:
            bars = entry.get("result", [])
            break

    if not bars:
        raise RuntimeError(f"Webull returned no bars for {symbol}: {payload}")

    return [
        {
            "time": bar["time"],
            "open": float(bar["open"]),
            "high": float(bar["high"]),
            "low": float(bar["low"]),
            "close": float(bar["close"]),
            "volume": float(bar["volume"]),
        }
        for bar in reversed(bars)
    ]


def get_weekly_bars(ticker, lookback_weeks=104):
    """I pull weekly OHLCV bars for one ticker, oldest bar first."""
    client = _get_client()
    response = client.market_data.get_batch_history_bar(
        [ticker], Category.US_STOCK.name, Timespan.W.name, count=str(lookback_weeks)
    )
    return _bars_from_response(response, ticker)


def get_index_bars(index_symbol="SPX", lookback_weeks=104):
    """I pull weekly OHLCV bars for the index used in the Mansfield RS comparison.

    Webull's OpenAPI Category enum only covers US_STOCK/US_ETF/US_OPTION/etc —
    there's no INDEX category, so a raw index ticker like SPX isn't fetchable
    through batch-bars at all (confirmed against the SDK's category.py). Until
    Webull exposes one, this needs an ETF proxy — pass 'SPY' instead of the
    literal index symbol.
    """
    if index_symbol.upper() == "SPX":
        raise ValueError(
            "SPX is a raw index — Webull's OpenAPI has no INDEX category, so it "
            "can't be pulled via batch-bars. Pass an ETF proxy instead, e.g. "
            "get_index_bars('SPY')."
        )

    # Using SPY instead of SPX is mathematically equivalent for this formula —
    # MRS is a ratio-of-a-ratio, so the constant SPY/SPX price-scaling factor
    # cancels out. Only residual drift is SPY's ~0.09%/year expense ratio,
    # negligible over a 52-week window. Worth knowing: the reference
    # calculation this project's Mansfield RS is checked against actually
    # compares against a direct SPX-tracking feed by default, not SPY, so
    # exact numeric parity with a chart running that default isn't expected
    # regardless of the math above — the reasoning here is about why SPY is
    # an acceptable proxy, not a claim that it reproduces that chart bar-for-bar.
    client = _get_client()
    response = client.market_data.get_batch_history_bar(
        [index_symbol], Category.US_ETF.name, Timespan.W.name, count=str(lookback_weeks)
    )
    return _bars_from_response(response, index_symbol)


def get_sector_data(ticker):
    """I look up a ticker's sector via its company profile, then match that
    name against the sector overview list to get the sector's own price-change
    stats. Webull's API doesn't expose a direct ticker-to-sector-id lookup, so
    this is a name match rather than an ID join — if it doesn't match cleanly
    I return sector_strength_pct=None rather than guessing.
    """
    client = _get_client()

    profile_response = client.instrument.get_company_profile(ticker, Category.US_STOCK.name)
    profile = profile_response.json()
    sector_name = profile.get("sector") or profile.get("industry")
    if not sector_name:
        raise RuntimeError(
            f"Webull company profile for {ticker} has no sector/industry field: {profile}"
        )

    sectors_response = client.screener.get_market_sectors(Category.US_STOCK.name, period="D5")
    sectors_payload = sectors_response.json()
    sectors = sectors_payload.get("result") or sectors_payload.get("data") or []

    match = next(
        (s for s in sectors if s.get("name", "").strip().lower() == sector_name.strip().lower()),
        None,
    )
    if match is None:
        return {"sector": sector_name, "sector_strength_pct": None}

    return {
        "sector": sector_name,
        "sector_strength_pct": float(match["change_ratio"]) * 100,
    }
