"""What I actually hold, what stop each position is on, and what I did
about each suggestion.

The screener answers "what looks good". That is not the question a
person with money already committed is asking. They want to know what to
sell to buy something better, where each stop should sit this week, and
whether the thing they were told last month worked.

Three pieces, and the third matters most:

1. **Positions** — what is held, at what cost, on what stop.
2. **Stops** — recomputed against current bars, ratcheting up only.
3. **The recommendation log** — what was suggested, and what was
   actually done about it.

That last one is the only source of forward evidence this project will
ever have. Every figure in docs/ is a backtest, run over history I have
already read, on an engine whose defects I keep finding. A record of
what was suggested before the outcome was known cannot be quietly tuned
in my favour, and it starts being worth something the day it exists.

Holdings live in config/portfolio.json, which is gitignored. Only the
example file is committed. This is a public repository and a position
list is nobody else's business.
"""
import datetime
import json
import os

from . import db, stop_loss

PORTFOLIO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config", "portfolio.json")


def _today():
    return datetime.date.today().isoformat()


def load(path=None):
    """Current holdings, or an empty portfolio if none has been set up.

    A missing file is a legitimate state — a new user has no positions —
    so it returns empty rather than raising.
    """
    path = path or PORTFOLIO_PATH
    if not os.path.exists(path):
        return {"cash": 0.0, "positions": []}
    with open(path) as handle:
        data = json.load(handle)
    data.setdefault("cash", 0.0)
    data.setdefault("positions", [])
    return data


def save(portfolio, path=None):
    """Write holdings back, atomically.

    Via a temporary file and os.replace so an interrupted write cannot
    leave a half-written portfolio — the same pattern the bar cache uses,
    and rather more important here, since this file is the only record of
    what is actually owned.
    """
    path = path or PORTFOLIO_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".partial"
    with open(tmp, "w") as handle:
        json.dump(portfolio, handle, indent=2, sort_keys=True)
    os.replace(tmp, path)


def position_for(portfolio, ticker):
    for position in portfolio["positions"]:
        if position["ticker"] == ticker.upper():
            return position
    return None


def add_position(portfolio, ticker, shares, entry_price, stop,
                 entry_date=None, note=None):
    """Record a purchase.

    Buying more of something already held averages the cost basis rather
    than creating a second row, because a stop applies to a position
    rather than to a lot, and two rows would mean two stops on one
    holding.
    """
    ticker = ticker.upper()
    existing = position_for(portfolio, ticker)
    if existing:
        total = existing["shares"] + shares
        existing["cost_basis"] = (
            (existing["cost_basis"] * existing["shares"] + entry_price * shares) / total)
        existing["shares"] = total
        # The higher stop wins: adding to a winner should not loosen the
        # protection already earned on the original shares.
        existing["stop"] = max(existing["stop"], stop) if existing.get("stop") else stop
        return existing

    position = {
        "ticker": ticker,
        "shares": shares,
        "cost_basis": entry_price,
        "stop": stop,
        "entry_date": entry_date or _today(),
    }
    if note:
        position["note"] = note
    portfolio["positions"].append(position)
    return position


def close_position(portfolio, ticker):
    """Remove a holding, returning it so a caller can log the exit."""
    ticker = ticker.upper()
    for index, position in enumerate(portfolio["positions"]):
        if position["ticker"] == ticker:
            return portfolio["positions"].pop(index)
    return None


def refresh_stops(portfolio, bars_by_symbol, method="ma"):
    """Recompute each position's trailing stop against current bars.

    Ratchets up only, which is the whole point of a trailing stop and the
    one property worth asserting: a stop that can fall is not protection,
    it is a way of losing more slowly while feeling protected.

    Returns one entry per position describing what changed, so a caller
    can show a list of adjustments rather than silently mutating
    their holdings.
    """
    changes = []
    for position in portfolio["positions"]:
        bars = bars_by_symbol.get(position["ticker"])
        if not bars:
            changes.append({"ticker": position["ticker"], "status": "no data",
                            "stop": position.get("stop")})
            continue

        entry_idx = _index_of_date(bars, position["entry_date"])
        suggestion = stop_loss.trailing_stop(
            bars, position["cost_basis"], entry_idx, method=method)
        proposed = (suggestion or {}).get("recommended")
        current = position.get("stop")

        if proposed is None:
            changes.append({"ticker": position["ticker"], "status": "unchanged",
                            "stop": current})
            continue

        if current is None or proposed > current:
            position["stop"] = proposed
            changes.append({"ticker": position["ticker"], "status": "raised",
                            "from": current, "stop": proposed})
        else:
            changes.append({"ticker": position["ticker"], "status": "held",
                            "stop": current, "would_have_been": proposed})
    return changes


def _index_of_date(bars, date_str):
    """Index of the last bar on or before a date; 0 if none match."""
    found = 0
    for index, bar in enumerate(bars):
        stamp = (bar.get("time") or bar.get("date") or "")[:10]
        if stamp <= date_str:
            found = index
        else:
            break
    return found


def stops_hit(portfolio, bars_by_symbol):
    """Positions whose stop has been touched by the latest bar.

    Checked against the bar's low rather than its close: a stop is an
    order resting in the market, and it fills when price trades through
    it, not when the week happens to finish below it.
    """
    hit = []
    for position in portfolio["positions"]:
        bars = bars_by_symbol.get(position["ticker"])
        stop = position.get("stop")
        if not bars or stop is None:
            continue
        latest = bars[-1]
        if latest.get("low") is not None and latest["low"] <= stop:
            hit.append({"ticker": position["ticker"], "stop": stop,
                        "low": latest["low"],
                        "date": (latest.get("time") or latest.get("date") or "")[:10]})
    return hit


def log_recommendation(ticker, action, suggested_on=None, shares=None,
                       price=None, stop=None, rationale=None):
    """Record what the system suggested, before the outcome is known."""
    db.save_recommendation({
        "ticker": ticker.upper(),
        "action": action,
        "suggested_on": suggested_on or _today(),
        "shares": shares,
        "price": price,
        "stop": stop,
        "rationale": rationale,
        "taken": None,
        "taken_note": None,
    })


def record_outcome(ticker, suggested_on, taken, note=None):
    """Record what was actually done about a suggestion.

    `taken` is True, False, or a string for a partial or modified action.
    Anything other than a plain yes is worth keeping verbatim — "bought
    half" and "waited a week" are the observations that reveal whether
    the suggestions are actually usable.
    """
    db.update_recommendation(ticker.upper(), suggested_on, taken, note)


def scoreboard(bars_by_symbol=None):
    """Suggested versus taken, and how each has done since.

    Deliberately reports the ones NOT taken as well. A record of only the
    trades that were acted on is a record of my judgement as much
    as the system's, and the gap between them is the interesting part.
    """
    rows = db.get_recommendations()
    out = []
    for row in rows:
        entry = dict(row)
        if bars_by_symbol and row.get("price"):
            bars = bars_by_symbol.get(row["ticker"])
            if bars:
                entry["price_now"] = bars[-1].get("close")
                if entry["price_now"]:
                    entry["move_pct"] = (
                        (entry["price_now"] - row["price"]) / row["price"] * 100)
        out.append(entry)
    return out
