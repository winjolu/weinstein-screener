"""The once-a-day check: what to do about what I already hold.

Built to the shape I actually work in — stops adjusted on weekdays,
purchases considered at the weekend once the weekly bar has closed.
That split is not a compromise, it follows from what the two decisions
depend on. A stop is a price event and can trigger any day. An entry is
a signal event, and the signal is not real until the bar it is measured
on has finished forming.

So a weekday run has a genuine job (stops, exits) and deliberately does
not suggest purchases. A weekend run does both.

Everything here states a number. "Consider evaluating AAPL" is not
usable output: it cannot be checked against a chart, argued with, or
scored later against what actually happened. If this thing cannot commit
to a share count and a stop, it has not finished thinking.

**It suggests. It does not decide, and it does not trade.** I check
each line against my own charts and record what I did.
"""
import datetime

from . import conditions, portfolio


def _weekly_bar_is_closed(today=None):
    """True at the weekend, when the week's bar has finished forming.

    Entries wait for this. A breakout measured on a Wednesday is measured
    on a bar that still has two days left to change its mind, and acting
    on it is reading a number that does not exist yet.
    """
    today = today or datetime.date.today()
    return today.weekday() >= 5


def review(portfolio_book, bars_by_symbol, candidates=None, today=None,
           risk_pct=1.0, account_value=None):
    """What to do today, as data. `format_review` renders it.

    Returns a dict with three sections, in the order they matter:
    `urgent` (stops touched), `stops` (adjustments), and `buys` (only
    when the weekly bar has closed).
    """
    today = today or datetime.date.today()
    account_value = account_value or _account_value(portfolio_book, bars_by_symbol)

    urgent = portfolio.stops_hit(portfolio_book, bars_by_symbol)
    stop_changes = portfolio.refresh_stops(portfolio_book, bars_by_symbol)

    buys = []
    if _weekly_bar_is_closed(today) and candidates:
        for candidate in candidates:
            sized = _size(candidate, account_value, risk_pct)
            if sized:
                buys.append(sized)

    return {
        "date": today.isoformat(),
        "weekly_bar_closed": _weekly_bar_is_closed(today),
        "account_value": account_value,
        "urgent": urgent,
        "stops": [c for c in stop_changes if c["status"] == "raised"],
        "unchanged": [c for c in stop_changes if c["status"] != "raised"],
        "buys": buys,
    }


def _account_value(book, bars_by_symbol):
    """Cash plus positions at their latest close."""
    total = book.get("cash", 0.0)
    for position in book["positions"]:
        bars = bars_by_symbol.get(position["ticker"])
        price = bars[-1]["close"] if bars else position["cost_basis"]
        total += position["shares"] * price
    return total


# No single position may exceed this share of the account, however
# tight its stop. Risk sizing alone would put a quarter of the book into
# one name if the stop were close enough, and a gap through the stop
# does not care how carefully the position was sized. Matches the cap
# used in portfolio_sim so the backtest and the live path agree.
MAX_POSITION_PCT = 10.0


def _size(candidate, account_value, risk_pct):
    """Shares to buy, from the distance to the stop.

    Risking a fixed slice of the account per position is the only sizing
    rule here that reflects what is actually at stake. A flat dollar
    amount bets three times as much on a wide-stop idea as a tight-stop
    one without anyone choosing that.

    Returns None when the stop is missing or sits above entry — a setup
    whose risk cannot be measured does not get sized by guesswork.
    """
    price = candidate.get("price")
    stop = candidate.get("stop")
    if not price or not stop or stop >= price:
        return None

    stop_pct = (price - stop) / price * 100
    if stop_pct > conditions.MAX_SENSIBLE_STOP_PCT:
        return None

    dollars_at_risk = account_value * risk_pct / 100.0
    shares = int(dollars_at_risk / (price - stop))

    ceiling = int(account_value * MAX_POSITION_PCT / 100.0 / price)
    capped = shares > ceiling
    shares = min(shares, ceiling)
    if shares <= 0:
        return None

    return {
        "ticker": candidate["ticker"],
        "shares": shares,
        "price": price,
        "stop": stop,
        "cost": shares * price,
        "risk": shares * (price - stop),
        "stop_pct": stop_pct,
        "share_of_account": shares * price / account_value * 100,
        "capped": capped,
        "rationale": candidate.get("rationale", ""),
    }


def format_review(result):
    """The review as plain text, for someone who did not write it."""
    lines = [f"Daily review — {result['date']}", ""]

    if result["urgent"]:
        lines.append("STOPS TRIGGERED — these need attention first:")
        for hit in result["urgent"]:
            lines.append(f"  {hit['ticker']}: traded down to {hit['low']:.2f}, "
                         f"through your stop at {hit['stop']:.2f} "
                         f"(week of {hit['date']})")
        lines.append("")

    if result["stops"]:
        lines.append("Stops to raise:")
        for change in result["stops"]:
            was = change.get("from")
            was_text = f"{was:.2f}" if was is not None else "none set"
            lines.append(f"  {change['ticker']}: {was_text} -> {change['stop']:.2f}")
        lines.append("")

    if not result["weekly_bar_closed"]:
        lines.append("No purchases suggested midweek: the weekly bar is still")
        lines.append("forming, so any breakout it shows can still un-happen.")
        lines.append("Run again at the weekend for entries.")
    elif result["buys"]:
        lines.append("Candidates, sized against your account:")
        for buy in result["buys"]:
            lines.append(
                f"  {buy['ticker']}: buy {buy['shares']} shares at {buy['price']:.2f} "
                f"= ${buy['cost']:,.0f} ({buy['share_of_account']:.1f}% of the account)")
            lines.append(
                f"      stop {buy['stop']:.2f} ({buy['stop_pct']:.1f}% below entry), "
                f"risking ${buy['risk']:,.0f} if it fails")
            if buy["rationale"]:
                lines.append(f"      {buy['rationale']}")
    else:
        lines.append("No candidates passed today.")

    lines.append("")
    lines.append("Check each of these against your own charts before acting on")
    lines.append("any of it, then record what you actually did. What you decline")
    lines.append("is as useful to the record as what you take.")
    return "\n".join(lines)
