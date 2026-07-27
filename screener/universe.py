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

# The listed universe measured 64,358 instruments — 65 pages. My first
# guess at this cap was 40, which truncated silently and made me think
# the universe was 40,000 and the screenable set a third of its real
# size. Headroom plus a warning now, since quietly screening a fraction
# of the market is exactly the kind of wrong that looks fine.
MAX_PAGES = 120

# Exchange codes worth screening. The rest of the listed universe is
# OTC/pink-sheet (PINL, PK, OTCID, OTCB) where the volume and pivot logic
# behaves badly on thin, gappy data.
MAJOR_EXCHANGES = {"NYSE", "NAS", "NSQ", "NMS", "PSE", "ASE", "BATS", "ARCA", "AMEX"}

# "OC" is the tradable status; the bulk of the universe sits in "NT",
# which isn't screenable.
TRADABLE_STATUS = "OC"

# Minimum average weekly dollar volume, set at the point where the data
# itself degrades rather than at a guess about tradability.
#
# I originally invented $5M. Measured across the universe, that was
# excluding 2,286 names, 163 of which would otherwise have reached the
# prefilter — and it wasn't buying signal quality, because the rate at
# which names reach the prefilter is essentially flat across every
# liquidity band: 7.3% under $1M, 7.0% at $1-5M, 6.0% at $5-15M, 8.7%
# above $200M. A filter that removes a uniform slice of candidates isn't
# filtering, it's just shrinking the search.
#
# What does change with liquidity is data integrity, and it breaks
# sharply below $1M: 8.9% of those names carry a zero-volume week
# against 2.8% just above, 34.6% have truncated history against 21.5%,
# and 30% can't be assigned a stage at all. Above $1M the degradation is
# smooth with no natural cutoff, so anything higher would be preference
# dressed as a threshold.
#
# Note this is a data-quality floor, not a capacity one. $1M a week is
# roughly $200k a day, which is thin for a position of any size — raise
# it with --min-dollar-volume if the trade size warrants, since that's a
# judgement about the account rather than about the data.
MIN_AVG_WEEKLY_DOLLAR_VOLUME = 1_000_000


def fetch_all_instruments():
    """Paginates the full US_STOCK instrument list. ~20 calls."""
    client = data_fetch._get_client()
    out = []
    last_id = None
    exhausted = False
    for _ in range(MAX_PAGES):
        rate_limit.acquire()
        page = client.instrument.get_instrument(
            symbols=None,
            category=Category.US_STOCK.name,
            last_instrument_id=last_id,
            page_size=INSTRUMENTS_PER_PAGE,
        ).json()
        if not isinstance(page, list) or not page:
            exhausted = True
            break
        out.extend(page)
        last_id = page[-1].get("instrument_id")
        if len(page) < INSTRUMENTS_PER_PAGE:
            exhausted = True
            break

    if not exhausted:
        print(
            f"WARNING: stopped paginating at MAX_PAGES ({MAX_PAGES}) with more "
            f"instruments still available. The scan is seeing only part of the "
            f"market — raise MAX_PAGES."
        )
    return out


def is_fund(instrument):
    """True for ETFs, ETNs and similar pooled products, as opposed to
    common stock.

    The API doesn't label these directly, but it does carry ETF-specific
    fields — leverage factor, single-stock flag, crypto flag — and those
    are populated for pooled products and absent entirely for ordinary
    shares. Checked across the whole screenable set: 3,338 instruments
    flagged this way have fund-like names against 16 that don't, so the
    signal is sound.

    I check the field rather than the name deliberately. Matching on
    words like "Trust" or "Shares" misclassifies real companies — plenty
    of REITs are trusts — and that showed up as 343 disagreements where
    the field is the one telling the truth.
    """
    return instrument.get("etf_leveraged_factor") is not None


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


def get_universe(refresh=False, include_funds=False):
    """The screenable universe as a list of symbols, cached for a week.

    Listings change slowly, so re-paginating the whole instrument list on
    every run buys nothing.

    Funds are excluded by default. They aren't invalid subjects for stage
    analysis — the book applies it to sector funds explicitly — but they
    swamp a stock screen in practice. A first limited run came back
    almost entirely ETFs, several of them slices of the same sector
    firing together as if they were independent signals, and none of them
    carry an industry classification, so condition 5 can never resolve
    and they're capped below a full verdict. Pass include_funds=True to
    screen them anyway.
    """
    if not refresh:
        cached = db.get_cached_universe()
        if cached:
            rows = cached if include_funds else [r for r in cached if not r["is_fund"]]
            return [row["symbol"] for row in rows]

    instruments = fetch_all_instruments()
    screenable = [i for i in instruments if is_screenable(i)]
    db.cache_universe(screenable, is_fund=is_fund)

    funds = sum(1 for i in screenable if is_fund(i))
    print(
        f"universe: {len(instruments)} instruments -> {len(screenable)} screenable "
        f"({len(screenable) - funds} stocks, {funds} funds)"
    )
    selected = screenable if include_funds else [i for i in screenable if not is_fund(i)]
    return [i["symbol"] for i in selected if i.get("symbol")]


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
