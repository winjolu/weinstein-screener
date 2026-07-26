"""Discovers the tradable universe so the screener can look at stocks I
don't already have opinions about.

The curated config/sector_universe/*.json lists were always a stopgap —
they can only surface names I'd already thought of, which defeats the
point of screening. This walks the actual listed universe instead.

The economics turned out far better than expected. The instrument
endpoint returns 1,000 records per call, so the whole ~20,000-instrument
universe costs 20 calls, and the metadata that comes back filters most of
it out for free: roughly 8,600 of those are OTC/pink-sheet listings and
13,700 aren't in a tradable status at all. What survives is around 3,200
real candidates, whose weekly bars cost ~160 batched calls. A full-market
sweep therefore fits comfortably inside a 300-per-minute budget — the
constraint was never the quota, it was fetching one symbol at a time.
"""
from webull.data.common.category import Category

from . import data_fetch, db, rate_limit

INSTRUMENTS_PER_PAGE = 1000
MAX_PAGES = 40

# Exchange codes worth screening. The rest of the listed universe is
# OTC/pink-sheet (PINL, PK, OTCID, OTCB) where the volume and pivot logic
# behaves badly on thin, gappy data.
MAJOR_EXCHANGES = {"NYSE", "NAS", "NSQ", "NMS", "PSE", "ASE", "BATS", "ARCA", "AMEX"}

# "OC" is the tradable status; the bulk of the universe sits in "NT",
# which isn't screenable.
TRADABLE_STATUS = "OC"

# Minimum average weekly dollar volume. Weinstein's volume rules assume a
# liquid, institutionally-traded stock, and thin names also break the
# pivot logic. I'm deliberately leaving this at a permissive default
# rather than guessing a "right" number — see filter_by_liquidity, which
# reports the distribution so it can be set from real data.
MIN_AVG_WEEKLY_DOLLAR_VOLUME = 5_000_000


def fetch_all_instruments():
    """Paginates the full US_STOCK instrument list. ~20 calls."""
    client = data_fetch._get_client()
    out = []
    last_id = None
    for _ in range(MAX_PAGES):
        rate_limit.acquire()
        page = client.instrument.get_instrument(
            symbols=None,
            category=Category.US_STOCK.name,
            last_instrument_id=last_id,
            page_size=INSTRUMENTS_PER_PAGE,
        ).json()
        if not isinstance(page, list) or not page:
            break
        out.extend(page)
        last_id = page[-1].get("instrument_id")
        if len(page) < INSTRUMENTS_PER_PAGE:
            break
    return out


def is_screenable(instrument):
    """Metadata-only filter — costs nothing beyond the instrument list.

    Leveraged, single-stock and crypto ETFs are excluded because stage
    analysis of a leveraged derivative reads the derivative's decay, not
    the underlying's trend.
    """
    if instrument.get("status") != TRADABLE_STATUS:
        return False
    if instrument.get("exchange_code") not in MAJOR_EXCHANGES:
        return False
    if instrument.get("etf_leveraged_flag") == "YES":
        return False
    if instrument.get("single_stock_etf") or instrument.get("crypto_etf"):
        return False
    return True


def get_universe(refresh=False):
    """The screenable universe as a list of symbols, cached for a week.

    Listings change slowly, so re-paginating the whole instrument list on
    every run buys nothing.
    """
    if not refresh:
        cached = db.get_cached_universe()
        if cached:
            return [row["symbol"] for row in cached]

    instruments = fetch_all_instruments()
    screenable = [i for i in instruments if is_screenable(i)]
    db.cache_universe(screenable)
    print(
        f"universe: {len(instruments)} instruments -> {len(screenable)} screenable "
        f"after metadata filter"
    )
    return [i["symbol"] for i in screenable if i.get("symbol")]


def filter_by_liquidity(bars_by_symbol, min_dollar_volume=MIN_AVG_WEEKLY_DOLLAR_VOLUME, report=True):
    """Drops names too thin for the volume and pivot logic to mean much.

    Dollar volume rather than share volume, since a $3 stock trading a
    million shares is not the same market as a $300 one. Measured over
    the last 12 complete weeks and reported as a distribution, because I'd
    rather set this threshold from what the data actually looks like than
    from a number I made up.
    """
    scored = {}
    for symbol, bars in bars_by_symbol.items():
        recent = bars[-12:]
        if not recent:
            continue
        scored[symbol] = sum(b["close"] * b["volume"] for b in recent) / len(recent)

    keep = {s: bars_by_symbol[s] for s, dv in scored.items() if dv >= min_dollar_volume}

    if report and scored:
        ordered = sorted(scored.values())
        def pct(p):
            return ordered[min(int(len(ordered) * p), len(ordered) - 1)]
        print(
            f"liquidity: median ${pct(0.5)/1e6:.1f}M/wk  "
            f"p25 ${pct(0.25)/1e6:.1f}M  p75 ${pct(0.75)/1e6:.1f}M  "
            f"-> {len(keep)}/{len(scored)} above ${min_dollar_volume/1e6:.0f}M"
        )
    return keep
