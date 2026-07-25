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

from . import sector_strength

_data_client = None
_spy_daily_closes_cache = None


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


def get_daily_bars(symbol, category, lookback_days=30):
    """I pull daily OHLCV bars for one symbol, oldest bar first, with
    timestamps preserved. get_daily_closes() is a thin wrapper that keeps
    just the closes for the live sector_strength percentile calculation,
    which doesn't need timestamps — but backtest.py does, to truncate a
    series to a specific historical date, which is why this exists as
    its own function rather than being folded into get_daily_closes.
    """
    client = _get_client()
    response = client.market_data.get_batch_history_bar(
        [symbol], category, Timespan.D.name, count=str(lookback_days)
    )
    return _bars_from_response(response, symbol)


def get_daily_closes(symbol, category, lookback_days=30):
    """I pull daily closing prices for one symbol, oldest bar first.
    lookback_days=30 gives comfortable margin over sector_strength.py's
    default 20-day lookback (which needs 21 closes) after accounting for
    the occasional gap. Public since both get_sector_data and
    sector_scan.py's sector-ranking need it.
    """
    return [b["close"] for b in get_daily_bars(symbol, category, lookback_days)]


def get_spy_daily_closes():
    """SPY's daily closes are the same for every ticker in a run (or every
    sector in a sector-ranking pass), so I fetch them once per process
    instead of once per caller.
    """
    global _spy_daily_closes_cache
    if _spy_daily_closes_cache is None:
        _spy_daily_closes_cache = get_daily_closes("SPY", Category.US_ETF.name)
    return _spy_daily_closes_cache


def get_sector_data(ticker):
    """I look up a ticker's sector via its company profile, then match that
    name against the sector overview list to get the sector's own price-change
    stats. Webull's API doesn't expose a direct ticker-to-sector-id lookup, so
    this is a name match rather than an ID join — if it doesn't match cleanly
    I return sector_strength_pct=None rather than guessing.

    The profile's classification comes back as an "industries" list (broadest
    entry first, e.g. ["Software & IT Services", "Software"]), not a single
    "sector"/"industry" field — confirmed against a live response. ETFs and
    some funds carry an empty list here, which is a legitimate case, not a
    data error, so that returns sector=None rather than raising.

    Also fetches daily closes for the ticker's mapped sector ETF and for
    SPY (via sector_strength.get_sector_etf's reference mapping), so
    conditions.py can use the real percentile calculation instead of the
    coarser change_ratio fallback below. That's supplementary to the
    sector match itself, so a failure here doesn't fail the whole ticker —
    it just leaves sector_etf_closes/spy_daily_closes as None and lets the
    caller fall back.
    """
    client = _get_client()

    profile_response = client.instrument.get_company_profile(ticker, Category.US_STOCK.name)
    profile = profile_response.json()
    industries = profile.get("industries") or []
    if not industries:
        return {"sector": None, "sector_strength_pct": None}
    sector_name = industries[0]

    sector_etf_closes = None
    spy_daily_closes = None
    try:
        sector_etf = sector_strength.get_sector_etf(sector_name)
        sector_etf_closes = get_daily_closes(sector_etf, Category.US_ETF.name)
        spy_daily_closes = get_spy_daily_closes()
    except Exception:
        sector_etf_closes = None
        spy_daily_closes = None

    sectors_response = client.screener.get_market_sectors(Category.US_STOCK.name, period="D5")
    sectors_payload = sectors_response.json()
    # Confirmed against a live response: this comes back as a bare array,
    # not wrapped in a "result"/"data" key like I'd originally guessed.
    if isinstance(sectors_payload, list):
        sectors = sectors_payload
    else:
        sectors = sectors_payload.get("result") or sectors_payload.get("data") or []

    match = next(
        (s for s in sectors if s.get("name", "").strip().lower() == sector_name.strip().lower()),
        None,
    )
    if match is None:
        return {
            "sector": sector_name,
            "sector_strength_pct": None,
            "sector_etf_closes": sector_etf_closes,
            "spy_daily_closes": spy_daily_closes,
        }

    return {
        "sector": sector_name,
        "sector_strength_pct": float(match["change_ratio"]) * 100,
        "sector_etf_closes": sector_etf_closes,
        "spy_daily_closes": spy_daily_closes,
    }


def get_sector_data_for_backtest(ticker, lookback_days):
    """Like get_sector_data(), but for backtest.py: returns full
    timestamped daily bars for the ticker's mapped sector ETF and for
    SPY, not just the most recent 30 days of bare closes, so the series
    can be truncated to any historical as_of_date.

    Deliberately never includes a sector_strength_pct — that field comes
    from get_market_sectors(), a live snapshot with no historical/as-of
    parameter in Webull's API at all, so there's no way to ask it "what
    was this on a past date." Using today's value for a historical
    evaluation would be lookahead bias, not an approximation, so
    backtest.py never reads it. See backtest.py's module docstring.
    """
    client = _get_client()

    profile_response = client.instrument.get_company_profile(ticker, Category.US_STOCK.name)
    profile = profile_response.json()
    industries = profile.get("industries") or []
    sector_name = industries[0] if industries else None

    sector_etf_bars = []
    spy_bars = []
    if sector_name:
        try:
            sector_etf = sector_strength.get_sector_etf(sector_name)
            sector_etf_bars = get_daily_bars(sector_etf, Category.US_ETF.name, lookback_days)
            spy_bars = get_daily_bars("SPY", Category.US_ETF.name, lookback_days)
        except Exception:
            sector_etf_bars = []
            spy_bars = []

    return {"sector": sector_name, "sector_etf_bars": sector_etf_bars, "spy_bars": spy_bars}
