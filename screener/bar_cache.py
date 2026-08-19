"""A local copy of the whole market's weekly history.

Every conclusion this project has reached has been limited by sample
size rather than by method. The eleven-year study ran 100 names and
produced 273 trades of which three carried the entire profit, and at
that size a filter that removes one winner destroys the result — which
is exactly what happened to every risk filter I tested. Bootstrapping
said as much directly: the 5th-to-95th range of hundred-trade outcomes
straddles zero, so a hundred trades cannot separate edge from luck.

The fix is more names, not more years, and it turns out to be cheap. The
batch endpoint takes 20 symbols at 1200 bars, so the entire common-stock
universe — 5,816 names, back to 2003 — is about 291 calls and a quarter
of an hour. That was never the bottleneck; I'd assumed it was.

Stored as a single pickle under data/, which is already gitignored. Not
in SQLite: this is a bulk numeric cache read whole and rebuilt whole,
which is the shape pickle is good at and rows are not. Nothing here is
authoritative — delete it and it rebuilds.
"""
import datetime
import os
import pickle
import time

from . import data_fetch, paths, universe

# Not inside the checkout. This file reached 334MB here and 1.7GB on the
# sibling project, and the checkout sits in a synced folder — a sync
# client rewriting a cache mid-run is the same collision that cost a
# four-hour sweep and left two arms silently short of rows.
CACHE_PATH = paths.data_file("weekly_bars.pkl", env="SCREENER_BAR_CACHE")

# The server's ceiling, and about 23 years of weekly bars — as far back
# as any backtest here can reach. See docs/webull-api-reference.md.
MAX_LOOKBACK_WEEKS = 1200

_loaded = None
_loaded_path = None


def build(symbols=None, lookback_weeks=MAX_LOOKBACK_WEEKS, path=None, progress=True):
    """Fetches full weekly history for `symbols` and writes the cache.

    Defaults to every common stock in the universe. Symbols the API has
    nothing for are simply absent from the result — the batch fetcher
    bisects around failures, so one dead ticker doesn't cost the other
    nineteen.
    """
    path = path or CACHE_PATH
    symbols = list(symbols) if symbols is not None else universe.get_universe()

    started = time.time()
    bars = {}
    batch = data_fetch.MAX_SYMBOLS_PER_BATCH
    total_batches = (len(symbols) + batch - 1) // batch

    for i in range(0, len(symbols), batch):
        chunk = symbols[i:i + batch]
        bars.update(data_fetch.get_weekly_bars_batch(chunk, lookback_weeks=lookback_weeks))
        if progress and (i // batch) % 25 == 0:
            done = i // batch + 1
            elapsed = time.time() - started
            rate = done / elapsed if elapsed else 0
            remaining = (total_batches - done) / rate / 60 if rate else 0
            print(f"  batch {done}/{total_batches}  {len(bars)} symbols  "
                  f"~{remaining:.0f} min left", flush=True)

    payload = {
        "bars": bars,
        "built": datetime.datetime.now().isoformat(timespec="seconds"),
        "lookback_weeks": lookback_weeks,
        "requested": len(symbols),
        "returned": len(bars),
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Written to a temporary name first: a crash partway through a 300MB
    # dump would otherwise leave a truncated file that loads as garbage.
    tmp = path + ".partial"
    with open(tmp, "wb") as fh:
        pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, path)

    if progress:
        missing = len(symbols) - len(bars)
        print(f"cached {len(bars)} symbols "
              f"({missing} had no data) in {(time.time() - started) / 60:.1f} min "
              f"-> {os.path.getsize(path) / 1e6:.0f} MB", flush=True)
    return bars


def load(path=None):
    """The cached bars as {symbol: bars}, memoised per process.

    Raises if the cache doesn't exist rather than silently rebuilding —
    a quarter-hour of API calls shouldn't happen as a side effect of a
    read.
    """
    global _loaded, _loaded_path
    path = path or CACHE_PATH
    if _loaded is not None and _loaded_path == path:
        return _loaded
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No bar cache at {path}. Build it with bar_cache.build() — "
            f"about 15 minutes for the full universe."
        )
    with open(path, "rb") as fh:
        payload = pickle.load(fh)
    _loaded, _loaded_path = payload["bars"], path
    return _loaded


def info(path=None):
    """When the cache was built and what's in it, without loading bars."""
    path = path or CACHE_PATH
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        payload = pickle.load(fh)
    bars = payload["bars"]
    depths = sorted(len(v) for v in bars.values())
    return {
        "built": payload["built"],
        "lookback_weeks": payload["lookback_weeks"],
        "symbols": len(bars),
        "requested": payload.get("requested"),
        "total_bars": sum(depths),
        "median_depth": depths[len(depths) // 2] if depths else 0,
        "size_mb": os.path.getsize(path) / 1e6,
    }


def with_history(minimum_weeks, path=None):
    """Symbols with at least `minimum_weeks` of bars.

    A backtest checkpoint needs EVALUATION_WEEKS of history behind it
    before it can resolve anything, so names shorter than that contribute
    nothing but runtime.
    """
    return sorted(s for s, b in load(path).items() if len(b) >= minimum_weeks)
