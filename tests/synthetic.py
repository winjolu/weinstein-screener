"""Shared synthetic bar builders.

Every test in this suite runs offline against constructed data. That's
deliberate: a test that needs the market open, or that asserts against
whatever a real ticker happens to be doing today, isn't a regression
test — it's a coin flip that occasionally fails for reasons unrelated
to the code.
"""
import datetime


def bar(date, high, low, close, volume=1_000_000.0, open_=None):
    return {
        "time": f"{date}T04:00:00.000+0000",
        "open": open_ if open_ is not None else close,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def weekly_dates(n, start="2023-01-06"):
    d = datetime.date.fromisoformat(start)
    out = []
    for _ in range(n):
        out.append(d.isoformat())
        d += datetime.timedelta(weeks=1)
    return out


def daily_dates(n, start="2023-01-03"):
    d = datetime.date.fromisoformat(start)
    out = []
    for _ in range(n):
        out.append(d.isoformat())
        d += datetime.timedelta(days=1)
    return out


def trending_bars(n, start_price=100.0, weekly_step=1.0, start="2023-01-06", daily=False):
    """A clean monotonic trend — useful when a test needs "some plausible
    series" rather than a specific chart shape.
    """
    dates = daily_dates(n, start) if daily else weekly_dates(n, start)
    price = start_price
    bars = []
    for d in dates:
        price += weekly_step
        bars.append(bar(d, price * 1.01, price * 0.98, price))
    return bars
