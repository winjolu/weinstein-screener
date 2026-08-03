"""Who owns a ticker, and since when, from SEC EDGAR.

Tickers get recycled and Webull resolves a symbol to whoever holds it
now. Asking for GM with an end date in 2008 returns bars; General Motors
Co was incorporated in 2009, so those bars are somebody else's. CC is
Chemours today and was Circuit City then. The series that comes back is
well-formed and spliced together from two unrelated companies, which is
the worst shape an error can take here.

EDGAR's CIK is the identifier a ticker isn't: assigned per filer, never
recycled. A company's first filing date is therefore a hard floor on how
far back its bars can legitimately go.

What this can and cannot do. It detects contamination and dates
delistings, both free. It cannot produce prices for companies that no
longer trade — EDGAR holds filings, not market data — so it measures the
survivorship hole without filling it.
"""
import datetime
import json
import os
import threading
import time
import urllib.request

from . import db

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"

# SEC's published fair-access ceiling is 10 requests a second. I sit
# under it rather than on it — being throttled costs far more than the
# handful of seconds this gives up over a full universe resolve.
MAX_REQUESTS_PER_SECOND = 8.0

# Forms that mark a security leaving an exchange. Form 25 (and 25-NSE,
# filed by the exchange rather than the issuer) is the delisting notice;
# Form 15 is deregistration, which usually follows.
DELISTING_FORMS = ("25", "25-NSE")
DEREGISTRATION_FORMS = ("15-12B", "15-12G", "15F-12B", "15F-12G")

_lock = threading.Lock()
_last_request = [0.0]
_ticker_map = None


class MissingUserAgent(RuntimeError):
    """SEC rejects requests without a contact address, and rightly."""


def _user_agent():
    """SEC requires a descriptive User-Agent naming a contact address.
    Read from the environment rather than committed, since it is an email
    address and this repository is public.
    """
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if not ua:
        raise MissingUserAgent(
            "SEC requires a User-Agent with a contact address. Set "
            "SEC_USER_AGENT in .env, e.g. 'weinstein-screener name@example.com'. "
            "Requests without one are refused."
        )
    return ua


def _throttle():
    with _lock:
        gap = 1.0 / MAX_REQUESTS_PER_SECOND
        wait = _last_request[0] + gap - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_request[0] = time.monotonic()


def _get_json(url):
    _throttle()
    request = urllib.request.Request(url, headers={
        "User-Agent": _user_agent(),
        "Accept-Encoding": "gzip, deflate",
        "Host": url.split("/")[2],
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            import gzip
            raw = gzip.decompress(raw)
        return json.loads(raw)


def ticker_cik_map(refresh=False):
    """Current ticker -> CIK for every SEC filer, about 10,000 of them.

    One request for the whole map, so this is memoised per process rather
    than stored: it is a single small file and re-fetching it once a run
    is not the cost worth optimising.

    Only *current* tickers appear. A symbol absent here has no SEC filer
    behind it today — ETFs organised as trusts, foreign issues, and
    anything already delisted all land in that bucket, and they are not
    the same case as each other.
    """
    global _ticker_map
    if _ticker_map is None or refresh:
        payload = _get_json(TICKER_MAP_URL)
        _ticker_map = {
            entry["ticker"].upper(): {"cik": entry["cik_str"], "name": entry["title"]}
            for entry in payload.values()
        }
    return _ticker_map


def _oldest_filing_date(filings):
    """Earliest filing across both the recent block and the archived
    index files. `recent` holds only the last thousand or so filings, so
    a long-lived company's true first filing lives in `files`, and
    reading `recent` alone would date it far too late — which for this
    purpose means failing to flag contamination that is really there.
    """
    dates = [d for d in filings.get("recent", {}).get("filingDate", []) if d]
    for archived in filings.get("files", []):
        if archived.get("filingFrom"):
            dates.append(archived["filingFrom"])
    return min(dates) if dates else None


def _delisting(filings):
    """The most recent delisting notice, if any, as (date, form).

    Presence does *not* mean the company is gone. Form 25 is filed for a
    single class of security and for voluntary moves between exchanges as
    readily as for failures, and a company can outlive it. Treating this
    as "died" would overcount badly, which is why the form is stored
    alongside the date rather than collapsed into a boolean.
    """
    recent = filings.get("recent", {})
    hits = [(date, form)
            for form, date in zip(recent.get("form", []), recent.get("filingDate", []))
            if form in DELISTING_FORMS]
    return max(hits) if hits else (None, None)


def company_identity(ticker):
    """Resolve one ticker. Never raises for an unknown symbol — a ticker
    with no filer behind it is a real and common answer, and is recorded
    as such so it isn't looked up again on the next run.
    """
    symbol = ticker.upper()
    entry = ticker_cik_map().get(symbol)
    if entry is None:
        return {"ticker": symbol, "cik": None, "company_name": None,
                "first_filing_date": None, "former_names": [],
                "delisted_date": None, "delisting_form": None}

    payload = _get_json(SUBMISSIONS_URL.format(cik=entry["cik"]))
    filings = payload.get("filings", {})
    delisted_date, delisting_form = _delisting(filings)
    return {
        "ticker": symbol,
        "cik": entry["cik"],
        "company_name": payload.get("name") or entry["name"],
        "first_filing_date": _oldest_filing_date(filings),
        "former_names": [n.get("name") for n in payload.get("formerNames", [])
                         if n.get("name")],
        "delisted_date": delisted_date,
        "delisting_form": delisting_form,
    }


def resolve_identities(tickers, progress=None, batch_size=200):
    """Fill the cache for whichever of these still need it.

    Writes in batches rather than at the end, so an interrupted run keeps
    everything it already paid for. Resolving the full universe is one
    request per symbol and the whole reason the table exists is to never
    do it twice.

    :return: how many were fetched. Zero means everything was cached,
        which is the normal steady state rather than a failure.
    """
    pending = db.tickers_needing_identity(sorted({t.upper() for t in tickers}))
    fetched, batch = 0, []
    for symbol in pending:
        try:
            batch.append(company_identity(symbol))
        except MissingUserAgent:
            raise
        except Exception as exc:  # noqa: BLE001 - one bad symbol shouldn't end the run
            if progress:
                progress(f"{symbol}: {type(exc).__name__} {exc}")
            continue
        fetched += 1
        if len(batch) >= batch_size:
            db.cache_identities(batch)
            batch = []
            if progress:
                progress(f"{fetched}/{len(pending)} resolved")
    if batch:
        db.cache_identities(batch)
    return fetched


# A ticker that genuinely changed hands stops trading in between: the
# old company is delisted and the new one lists later, usually months or
# years apart. A corporate reorganisation has no such gap — the business
# and its price series continue uninterrupted while only the legal
# filer changes. 120 days is comfortably longer than any holiday or
# suspension and far shorter than a real relisting interval.
MIN_RECYCLING_GAP_DAYS = 120


def _bar_date(bar):
    return (bar.get("time") or bar.get("date", ""))[:10]


def contaminated_symbols(bars_by_symbol, min_gap_days=MIN_RECYCLING_GAP_DAYS):
    """Symbols whose cached history looks like two different companies
    spliced together.

    Two tests, and the second matters more than I first assumed. The CIK
    test alone — does history predate the current filer's first filing —
    flags 605 of 5,803 symbols, and **91% of those are false positives**:
    XOM, BlackRock, Bunge and hundreds of others re-registered as new
    legal entities while the same business kept trading under the same
    ticker without a break. A new CIK is not a new company.

    So a real trading gap is required as well. Set min_gap_days to 0 to
    see the raw CIK finding, which is worth doing once to understand how
    much noise the second test is removing.

    Reports rather than deletes. Whether to trim a series or drop the
    symbol depends on how much survives, and that belongs to the caller.
    """
    findings = []
    for symbol, bars in bars_by_symbol.items():
        if not bars:
            continue
        bad = db.bars_predating_owner(symbol, bars)
        if not bad:
            continue
        identity = db.get_cached_identity(symbol)
        cutoff = identity["first_filing_date"]
        dates = sorted(_bar_date(b) for b in bars)
        before = [d for d in dates if d < cutoff]
        after = [d for d in dates if d >= cutoff]

        gap = None
        if before and after:
            gap = (datetime.date.fromisoformat(after[0])
                   - datetime.date.fromisoformat(before[-1])).days
        if min_gap_days and (gap is None or gap < min_gap_days):
            continue

        findings.append({
            "symbol": symbol,
            "company_name": identity["company_name"],
            "first_filing_date": cutoff,
            "bars_before": len(bad),
            "bars_total": len(bars),
            "earliest_bar": min(_bar_date(b) for b in bad),
            "gap_days": gap,
        })
    return sorted(findings, key=lambda f: -(f["gap_days"] or 0))
