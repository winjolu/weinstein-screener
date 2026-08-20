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
import re

from webull.data.common.category import Category

from market_core import liquidity

from . import data_fetch, db, rate_limit

# `ABR PRD`, `JPM PRC`, `NLY PRF` — the exchange's own preferred-share
# notation, and the one part of this that needs no corroboration.
PREFERRED_SYMBOL_RE = re.compile(r"\s+PR[A-Z]?$")

# Trailing letters that mark a derivative of the common rather than the
# common itself, where the four-letter base exists under the same name.
DERIVATIVE_SUFFIXES = {"U": "unit", "W": "warrant", "R": "right"}

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


# The ETF-family fields. None of them is a security-type label, but the
# API populates them for pooled products and leaves them absent entirely
# for ordinary shares, which makes their mere presence the signal.
ETF_FIELDS = ("etf_leveraged_factor", "single_stock_etf", "crypto_etf")

# Nasdaq's fifth-letter convention distinguishes share classes from
# preferreds and notes, but not cleanly enough to use alone. These are
# the letters that mean "another class of common" — Central Garden's
# CENTA, Liberty Latin America's LILAK, Urban One's UONEK.
COMMON_CLASS_SUFFIXES = frozenset("ABCK")

# Everything a stage analysis can legitimately be run on. The rest are
# instruments whose price series answers a different question.
DEFAULT_SCREENABLE_TYPES = frozenset({"common"})


def is_fund(instrument):
    """True for pooled products — ETFs, ETNs, closed-end funds — as
    opposed to common stock.

    The API doesn't label these directly, but it does carry ETF-specific
    fields, and those are populated for pooled products and absent
    entirely for ordinary shares. I check the field rather than the name
    deliberately: matching words like "Trust" or "Shares" misclassifies
    real companies, since plenty of REITs are trusts and HomeTrust
    Bancshares is a bank.

    This used to test `etf_leveraged_factor` alone, which turned out to
    be ETF-specific rather than fund-generic — closed-end funds leave it
    empty and so came back as ordinary stock. `crypto_etf` is the one
    that separates them: it's present-but-false on a CEF and absent on a
    real company. Widening the test to "any of the three is populated"
    picks up 346 further names, and every one I inspected is a closed-end
    fund. Those are the 343 unflagged fund-like names I'd previously
    assumed were REITs and trusts; the assumption was wrong.
    """
    return any(instrument.get(field) is not None for field in ETF_FIELDS)


def _margin_requirement(instrument):
    try:
        return float(instrument.get("margin_requirement_long") or 0)
    except (TypeError, ValueError):
        return 0.0


def classify_security_types(instruments):
    """Maps each symbol to what kind of instrument it actually is.

    Returns one of: common, fund, preferred, unit, warrant, right.

    Stage analysis assumes a price series driven by a business's
    prospects. A preferred share is driven by interest rates, a SPAC unit
    by a pending deal, a warrant by the leverage in its strike. All three
    still produce a rising line above a rising average, so the checklist
    passes them for entirely the wrong reasons — measured on one scan,
    the three top-scoring names in the entire market were AGNC preferreds
    at 9 of 9.

    Classification can't be done per-instrument, because the signal is
    relational: `AGNCL` is a preferred because `AGNC` exists under the
    same company name. So this takes the whole list at once.

    Two conventions do the work, and they need different treatment:

    - The ` PR<letter>` symbol infix is an unambiguous exchange
      convention for preferred shares, so it stands on its own. I
      initially demanded a tradability confirmation here too and it was
      a mistake: large-cap preferreds like `JPM PRC` are liquid enough
      to be marginable, so requiring a 100% margin rate wrongly rescued
      24 genuine preferreds.
    - The five-letter Nasdaq suffix is genuinely ambiguous — `GOOGL` is
      Alphabet's Class A, not an Alphabet preferred. There I take the
      structural match as a candidate only, and confirm it against how
      the instrument trades, since preferreds and notes carry a 100%
      margin requirement where ordinary shares don't.

    What I deliberately don't use is the margin requirement on its own.
    It tracks illiquidity rather than security type: `GCBC`, `LARK`,
    `SBFG` and `ATLO` are ordinary community banks that also carry 100%
    margin, and they're exactly the small-cap Stage 2 names this screener
    exists to surface. Filtering on it would delete them silently.
    """
    by_symbol = {i.get("symbol"): i for i in instruments if i.get("symbol")}
    by_name = {}
    for instrument in instruments:
        name = (instrument.get("name") or "").strip().upper()
        by_name.setdefault(name, set()).add(instrument.get("symbol"))

    types = {}
    for symbol, instrument in by_symbol.items():
        types[symbol] = _security_type(instrument, symbol, by_symbol, by_name)
    return types


def _security_type(instrument, symbol, by_symbol, by_name):
    if PREFERRED_SYMBOL_RE.search(symbol):
        return "preferred"

    if len(symbol) == 5 and symbol.isalpha():
        base, suffix = symbol[:-1], symbol[-1]
        name = (instrument.get("name") or "").strip().upper()
        # The sibling has to share a company name, not merely a prefix,
        # or any four-letter ticker would capture unrelated five-letter
        # ones that happen to start the same way.
        if base in by_symbol and base in by_name.get(name, ()):
            if suffix in DERIVATIVE_SUFFIXES:
                return DERIVATIVE_SUFFIXES[suffix]
            if suffix not in COMMON_CLASS_SUFFIXES and _margin_requirement(instrument) >= 1.0:
                return "preferred"

    if is_fund(instrument):
        return "fund"
    return "common"


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


def wanted_types(include_funds=False, include_non_common=False):
    """Which security types a scan should admit."""
    types = set(DEFAULT_SCREENABLE_TYPES)
    if include_funds:
        types.add("fund")
    if include_non_common:
        types.update({"preferred", "unit", "warrant", "right"})
    return types


def get_universe(refresh=False, include_funds=False, include_non_common=False):
    """The screenable universe as a list of symbols, cached for a week.

    Listings change slowly, so re-paginating the whole instrument list on
    every run buys nothing.

    Only common stock is screened by default.

    Funds are the softer exclusion of the two. They aren't invalid
    subjects for stage analysis — the book applies it to sector funds
    explicitly — but they swamp a stock screen in practice. A first
    limited run came back almost entirely ETFs, several of them slices of
    the same sector firing together as if they were independent signals,
    and none carry an industry classification, so condition 5 can never
    resolve. `include_funds=True` screens them anyway.

    Preferreds, units, warrants and rights are excluded on a stronger
    argument: the checklist doesn't merely struggle with them, it passes
    them for the wrong reasons. `include_non_common=True` exists so the
    exclusion can be measured rather than trusted, not because screening
    them is a sensible default.
    """
    types = wanted_types(include_funds, include_non_common)

    if not refresh:
        cached = db.get_cached_universe()
        if cached:
            # A cache written before security types existed has the column
            # empty; treating that as "unknown, so keep it" would silently
            # restore the old behaviour, so an untyped cache is refetched.
            if any(row.get("security_type") for row in cached):
                return [r["symbol"] for r in cached if r.get("security_type") in types]

    instruments = fetch_all_instruments()
    screenable = [i for i in instruments if is_screenable(i)]
    security_types = classify_security_types(screenable)
    db.cache_universe(screenable, security_types=security_types)

    counts = {}
    for value in security_types.values():
        counts[value] = counts.get(value, 0) + 1
    breakdown = ", ".join(f"{n} {t}" for t, n in sorted(counts.items(), key=lambda kv: -kv[1]))
    print(
        f"universe: {len(instruments)} instruments -> {len(screenable)} screenable "
        f"({breakdown})"
    )
    return [s for s, t in sorted(security_types.items()) if t in types]


def filter_by_liquidity(bars_by_symbol, min_dollar_volume=MIN_AVG_WEEKLY_DOLLAR_VOLUME, report=True):
    """Drops names too thin for the volume and pivot logic to mean much.

    Dollar volume rather than share volume, since a $3 stock trading a
    million shares is not the same market as a $300 one. Measured over
    the last 12 complete weeks and reported as a distribution, because I'd
    rather set this threshold from what the data actually looks like than
    from a number I made up.

    The measurement itself lives in `market_core.liquidity`, because
    close-times-volume stops being meaningful once a reverse split has
    driven adjusted volume below one share and it rounds up to the
    storage floor. That defect is a property of the vendor's data rather
    than of this screen, and it is large: 6% of the archive's price bars
    sit on that floor. Names it makes unmeasurable are dropped and
    counted separately, so a data fault never gets reported as a
    judgement about tradability.
    """
    keep, rejected = liquidity.filter_by_dollar_volume(
        bars_by_symbol, min_dollar_volume, window=12)

    if report:
        scored = {}
        for symbol, bars in bars_by_symbol.items():
            measured = liquidity.dollar_volume(bars[-12:])
            if measured is not None:
                scored[symbol] = measured
        if scored:
            ordered = sorted(scored.values())
            def pct(p):
                return ordered[min(int(len(ordered) * p), len(ordered) - 1)]
            print(
                f"liquidity: median ${pct(0.5)/1e6:.1f}M/wk  "
                f"p25 ${pct(0.25)/1e6:.1f}M  p75 ${pct(0.75)/1e6:.1f}M  "
                f"-> {len(keep)}/{len(scored)} above ${min_dollar_volume/1e6:.0f}M"
            )
        if rejected["unmeasurable"]:
            print(f"liquidity: {len(rejected['unmeasurable'])} names dropped as "
                  f"unmeasurable — adjusted volume on the storage floor")
    return keep
