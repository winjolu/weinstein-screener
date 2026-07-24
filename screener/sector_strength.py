"""Sector strength as a momentum-of-relative-strength rank: how often the
sector-ETF/SPY ratio is higher today than it was on each of the last N
days, rather than a simple day-by-day outperformance count.
"""

# Sector name -> representative ETF. Two different naming sources live
# here, since two different things consult this map:
#
# - The reference chart indicator's own sector taxonomy (Technology
#   Services, Energy Minerals, etc.) — kept so this project's
#   classification can still be cross-checked against that chart.
# - Webull's own get_company_profile() industry strings (Oil & Gas,
#   Banking Services, etc.) — confirmed live against a real
#   get_market_sectors() response on 2026-07-24. This is the set
#   get_sector_data() actually needs, since its sector names come from
#   Webull's own data, not the chart indicator. Missing this the first
#   time around meant every real ticker's sector lookup silently fell
#   through to the SPY default, which made the resulting percentile
#   meaningless (SPY compared against itself).
#
# This is reference data (a lookup table), not calculation logic.
SECTOR_ETF_MAP = {
    # --- reference chart indicator's taxonomy ---
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
    # --- Webull's own industry taxonomy (confirmed live, 2026-07-24) ---
    "Software & IT Services": "XLK",
    "Semiconductors & Semiconductor Equipment": "XLK",
    "Banking Services": "XLF",
    "Computers, Phones & Household Electronics": "XLK",
    "Pharmaceuticals": "XLV",
    "Machinery, Tools, Heavy Vehicles, Trains & Ships": "XLI",
    "Oil & Gas": "XLE",
    "Diversified Retail": "XLY",
    "Telecommunications Services": "XLC",
    "Investment Banking & Investment Services": "XLF",
    "Insurance": "XLF",
    "Aerospace & Defense": "XLI",
    "Consumer Goods Conglomerates": "XLP",
    "Professional & Commercial Services": "XLI",
    "Automobiles & Auto Parts": "XLY",
    "Electric Utilities & IPPs": "XLU",
    "Healthcare Equipment & Supplies": "XLV",
    "Metals & Mining": "XLB",
    "Residential & Commercial REITs": "XLRE",
    "Food & Tobacco": "XLP",
}
DEFAULT_SECTOR_ETF = "SPY"

# Keyword fallback for industry names not in the exact-match table above —
# the confirmed list came from one live API call and almost certainly
# isn't exhaustive, so an unrecognized name falls through to a substring
# match on these hints before hitting the SPY default. Order matters:
# first match wins.
_KEYWORD_ETF_HINTS = [
    (("software", "semiconductor", "computer", "electronics", "technology"), "XLK"),
    (("bank", "invest", "insurance", "financial", "capital markets"), "XLF"),
    (("pharma", "health", "biotech", "medical"), "XLV"),
    (("food", "beverage", "tobacco", "household", "personal products", "staples"), "XLP"),
    (("oil", "gas", "energy", "coal"), "XLE"),
    (
        ("machinery", "aerospace", "defense", "industrial", "commercial services",
         "transportation", "airlines", "shipping"),
        "XLI",
    ),
    (("retail", "auto", "leisure", "hotel", "restaurant", "apparel", "media & entertainment"), "XLY"),
    (("utilit",), "XLU"),
    (("metal", "mining", "chemical", "material", "construction material"), "XLB"),
    (("telecom", "communication", "entertainment", "internet"), "XLC"),
    (("reit", "real estate"), "XLRE"),
]


def get_sector_etf(sector_name):
    """Maps a sector name to its representative ETF: exact match against
    SECTOR_ETF_MAP first, then a keyword fallback for names not seen yet,
    then SPY as the last resort.
    """
    if sector_name in SECTOR_ETF_MAP:
        return SECTOR_ETF_MAP[sector_name]

    lowered = sector_name.lower()
    for keywords, etf in _KEYWORD_ETF_HINTS:
        if any(keyword in lowered for keyword in keywords):
            return etf

    return DEFAULT_SECTOR_ETF


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
