"""Turns a list of simulated trades into what an account would have done.

The backtester answers "was each signal any good". That's the wrong unit
for deciding whether to run this with real money, for three reasons the
per-trade numbers actively hide:

1. **Time.** A +10% trade held three weeks and a +10% trade held two
   years are the same number and completely different investments. Any
   honest return figure has to be per year, not per trade.
2. **Idle money.** Signals don't arrive evenly. Capital sits doing
   nothing between them, and that dead time is part of the return whether
   or not the trade statistics mention it.
3. **The benchmark.** A strategy returning 8% a year is bad if simply
   buying the index returned 14% over the same stretch. Nothing in a
   win rate shows this, and it is the only comparison that decides
   whether the work is worth doing at all.

So this module reports two different things and keeps them apart.
"Return per trade" is what the average signal was worth. "Return on the
account" is what someone actually running it would have earned, which
needs a peak-capital figure and a calendar.
"""
import datetime
import statistics


def _date(value):
    return datetime.date.fromisoformat(value[:10])


def _safe_cagr(ending, starting, years):
    """Compound annual rate, returning -1.0 when the account is wiped out.

    Python's ** on a negative base with a fractional exponent returns a
    complex number rather than raising, so a strategy that lost more than
    its capital produced a CAGR that printed as "-1.89+26.38j%" and
    passed through every downstream format string unnoticed.
    """
    if starting <= 0:
        return float("nan")
    if ending <= 0:
        return -1.0
    return (ending / starting) ** (1 / years) - 1


def _percentile(values, fraction):
    """Simple order-statistic percentile. Sorts a copy, so callers keep
    whatever ordering they had."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(int(len(ordered) * fraction), len(ordered) - 1)]


def _payoff(wins, losses):
    """Average win over average loss, or NaN when undefined."""
    if not wins or not losses:
        return float("nan")
    mean_loss = abs(statistics.mean(losses))
    if mean_loss == 0:
        return float("nan")
    return statistics.mean(wins) / mean_loss


def _resolved(trades):
    """Trades that actually finished. An open trade has no return yet,
    and counting it as zero would quietly dilute everything."""
    return [t for t in trades
            if not t.get("still_open")
            and t.get("exit_date")
            and t.get("return_pct") is not None]


def summarise_trades(trades, stake=1000.0):
    """Per-trade view: what one signal was worth on average."""
    done = _resolved(trades)
    if not done:
        return None

    returns = [t["return_pct"] for t in done]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]
    profits = sorted((stake * r / 100.0 for r in returns), reverse=True)
    holds = [(_date(t["exit_date"]) - _date(t["entry_date"])).days / 7.0 for t in done]

    total_profit = sum(profits)
    top5 = sum(profits[:5])

    return {
        "n": len(done),
        "still_open": len(trades) - len(done),
        "win_rate": len(wins) / len(done) * 100,
        # "Payoff" = average win divided by average loss. Above 1 means
        # winners are bigger than losers, which is how a strategy can be
        # profitable while being wrong most of the time.
        # Guarded against a zero denominator. A trade returning exactly
        # 0% is counted as a loss, so a sample whose only non-winners are
        # flat gives mean(losses) == 0 and divides by zero. Rare in real
        # data and trivial to hit in a test.
        "payoff": _payoff(wins, losses),
        "mean_pct": statistics.mean(returns),
        "median_pct": statistics.median(returns),
        "best_pct": max(returns),
        "worst_pct": min(returns),
        "stake": stake,
        "capital_deployed": stake * len(done),
        "total_profit": total_profit,
        "roi_on_deployed": total_profit / (stake * len(done)) * 100,
        "top5_share": (top5 / total_profit * 100) if total_profit > 0 else float("nan"),
        "median_hold_weeks": statistics.median(holds),
        "mean_hold_weeks": statistics.mean(holds),
        # The spread, not just the middle. Reporting means alone hid the
        # most important property of the best-performing rule found here:
        # it doesn't avoid losses, it takes bigger swings both ways. Its
        # median trade is worse than the baseline's while its mean is four
        # times better, because the entire edge sits in the right tail.
        # A reader given only the mean would picture the wrong strategy.
        "p5_pct": _percentile(returns, 0.05),
        "p25_pct": _percentile(returns, 0.25),
        "p75_pct": _percentile(returns, 0.75),
        "p95_pct": _percentile(returns, 0.95),
        "share_losing_20pct": sum(1 for r in returns if r < -20) / len(returns) * 100,
        "share_gaining_50pct": sum(1 for r in returns if r > 50) / len(returns) * 100,
    }


def simulate_account(trades, stake=1000.0):
    """Account view: put `stake` into every signal as it arrives, hold to
    the simulated exit, and track what the whole book is doing.

    Every signal is taken. That's deliberate — capping positions would
    mean choosing which to skip, and any rule for choosing is another
    untested parameter. It does mean the capital requirement is whatever
    the worst week demanded rather than something decided in advance.
    """
    done = _resolved(trades)
    if not done:
        return None

    events = []
    for t in done:
        profit = stake * t["return_pct"] / 100.0
        events.append((_date(t["entry_date"]), "open", stake, t))
        events.append((_date(t["exit_date"]), "close", stake + profit, t))
    events.sort(key=lambda e: e[0])

    open_positions = 0
    peak_positions = 0
    realised = 0.0
    curve = []  # (date, cumulative realised profit)
    # Capital tied up, integrated over calendar time. Peak capital alone
    # is an unfairly harsh denominator: it's the single worst week, and
    # the book is far smaller than that most of the time. Averaging over
    # the window says how hard the money actually worked.
    position_days = 0.0
    previous = events[0][0]
    for when, kind, _amount, trade in events:
        position_days += open_positions * (when - previous).days
        previous = when
        if kind == "open":
            open_positions += 1
            peak_positions = max(peak_positions, open_positions)
        else:
            open_positions -= 1
            realised += stake * trade["return_pct"] / 100.0
            curve.append((when, realised))

    start = min(_date(t["entry_date"]) for t in done)
    end = max(_date(t["exit_date"]) for t in done)
    years = max((end - start).days / 365.25, 1e-9)

    # Capital that would have had to be on hand: the most the book ever held
    # at once. Fewer dollars than this and some signals go untaken, which
    # is a different strategy from the one being measured.
    capital_required = peak_positions * stake
    total_return_pct = realised / capital_required * 100

    # Compound annual growth rate — the yearly rate that turns the
    # starting capital into the ending capital over this many years.
    # Reported because a raw total over 11 years flatters itself.
    #
    # Guarded because losses can exceed the capital base. A fractional
    # power of a negative number is complex in Python rather than an
    # error, so an arm that lost more than it started with silently
    # reported a CAGR like "-1.89+26.38j%" — which formats without
    # complaint and is meaningless. An account wiped out past zero is
    # -100% a year and there is nothing further to compound.
    cagr = _safe_cagr(capital_required + realised, capital_required, years)

    # The same figure against average rather than peak capital. This is
    # the strategy's return per dollar-year of exposure, and it's the
    # fairer comparison against an index that stays fully invested —
    # though it's also the optimistic end, since nobody can size an
    # account to the average and still take every signal at the peak.
    avg_capital = (position_days / max((end - start).days, 1)) * stake
    if avg_capital > 0:
        cagr_on_average = _safe_cagr(avg_capital + realised, avg_capital, years)
    else:
        cagr_on_average = float("nan")

    # Largest peak-to-trough fall in cumulative profit. This is the
    # losing streak that would have had to be sat through without quitting.
    worst_drawdown = 0.0
    running_peak = 0.0
    for _, value in curve:
        running_peak = max(running_peak, value)
        worst_drawdown = min(worst_drawdown, value - running_peak)

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "years": years,
        "n": len(done),
        "trades_per_year": len(done) / years,
        "peak_positions": peak_positions,
        "capital_required": capital_required,
        "avg_capital": avg_capital,
        "realised_profit": realised,
        "total_return_pct": total_return_pct,
        "cagr_pct": cagr * 100,
        "cagr_on_average_pct": cagr_on_average * 100,
        "worst_drawdown": worst_drawdown,
        "curve": curve,
    }


def simulate_fixed_capital(trades, capital=25000.0, stake=1000.0, seed=None,
                            cash_yield_pct=0.0, priority=None):
    """What a real account with a fixed amount of money would have done.

    simulate_account() takes every signal and reports the answer against
    two denominators, peak capital and average capital. Peak is harsh —
    it sizes the account for the single busiest week of a decade — and
    average is unachievable, since nobody can hold the average and still
    fund the peak. The true answer sits between them and neither figure
    can reach it.

    This closes that gap the way reality does: start with `capital`, put
    `stake` into each signal as it arrives, and when the cash is gone,
    miss the rest. Missing signals is not a modelling choice here, it is
    what having finite money means.

    The one judgement call is which signals get skipped when several
    arrive the same week and only some can be funded. There is no
    principled ordering, so `seed` shuffles the tie and callers should
    run several — if the answer moves much between seeds, the result
    depends on an arbitrary choice and should not be trusted. With
    seed=None the order is alphabetical by ticker, which is stable and
    equally arbitrary.

    `cash_yield_pct` is the annual rate earned on money not currently in
    a position. It defaults to zero, which is the conservative reading
    and also the wrong one: this strategy holds a great deal of cash, and
    comparing idle cash against a fully-invested index while paying it
    nothing charges the strategy for a cost it would not really bear.
    Over 2021-2026 short-term cash paid roughly 4%, which on a book that
    is two-thirds in cash is worth well over two points a year — enough
    to change a conclusion. Left off by default so it is always an
    explicit choice rather than a quiet assist.

    :return: dict including `skipped`, which is the figure to watch. A
        high skip rate means the reported return belongs to a different
        and much more selective strategy than the one that was tested.
        `deployed_vs_start_pct` says how much of the money was at work.
    """
    done = _resolved(trades)
    if not done:
        return None

    by_entry = sorted(done, key=lambda t: (_date(t["entry_date"]), t["ticker"]))
    if priority is not None:
        # Rank competing signals instead of taking them arbitrarily. This
        # only bites when the account cannot fund everything, which is
        # the normal case: at $25,000 an account funds about one signal
        # in seven, so the ordering decides most of the return.
        #
        # Applied before the seed shuffle deliberately — the shuffle then
        # only breaks ties *within* a priority level, so a seed sweep
        # still measures the noise left after ranking rather than
        # undoing the ranking.
        by_entry.sort(key=lambda t: (_date(t["entry_date"]), -priority(t)))
    if seed is not None:
        import random
        rng = random.Random(seed)

        # The shuffle runs inside each group of signals that are
        # genuinely interchangeable. Without a priority that means
        # "same day"; with one it means "same day and same rank", so the
        # shuffle randomises what the ranking left undecided instead of
        # discarding the ranking outright.
        def group_key(trade):
            if priority is None:
                return (_date(trade["entry_date"]),)
            return (_date(trade["entry_date"]), priority(trade))

        grouped, i = [], 0
        while i < len(by_entry):
            j = i
            while j < len(by_entry) and group_key(by_entry[j]) == group_key(by_entry[i]):
                j += 1
            tied = by_entry[i:j]
            rng.shuffle(tied)
            grouped.extend(tied)
            i = j
        by_entry = grouped

    # Exits sort ahead of entries on the same date: money freed by a sale
    # is available to the next buy. Doing it the other way round
    # understates capacity for no reason. The sort is stable, so the
    # entry order established above (seeded or alphabetical) survives it.
    events = ([(_date(t["exit_date"]), 0, "exit", t) for t in done]
              + [(_date(t["entry_date"]), 1, "entry", t) for t in by_entry])
    events.sort(key=lambda e: (e[0], e[1]))

    cash = float(capital)
    open_count = 0
    peak_open = 0
    taken, skipped = 0, 0
    realised = 0.0
    interest = 0.0
    curve = []
    deployed_day_dollars = 0.0
    elapsed_days = 0
    last_when = events[0][0]
    rate = cash_yield_pct / 100.0

    for when, _order, kind, trade in events:
        days = (when - last_when).days
        if days:
            deployed_day_dollars += open_count * stake * days
            elapsed_days += days
            if rate:
                earned = cash * rate * days / 365.25
                cash += earned
                interest += earned
            last_when = when

        if kind == "exit":
            if trade.get("_funded"):
                proceeds = stake * (1 + trade["return_pct"] / 100.0)
                cash += proceeds
                realised += proceeds - stake
                open_count -= 1
                curve.append((when, cash + open_count * stake))
        elif cash >= stake:
            cash -= stake
            open_count += 1
            peak_open = max(peak_open, open_count)
            trade["_funded"] = True
            taken += 1
        else:
            trade["_funded"] = False
            skipped += 1

    for trade in done:
        trade.pop("_funded", None)

    start = min(_date(t["entry_date"]) for t in done)
    end = max(_date(t["exit_date"]) for t in done)
    years = max((end - start).days / 365.25, 1e-9)
    # _resolved() has already dropped anything still open, so every
    # funded position has been drained by now and the cash is the whole
    # account. Asserted rather than written as `cash + open_count *
    # stake`, which reads as if it handles a case that cannot occur —
    # and which no test could ever exercise.
    assert open_count == 0, "a funded position was never closed out"
    ending = cash

    worst_drawdown = 0.0
    running_peak = float(capital)
    for _, value in curve:
        running_peak = max(running_peak, value)
        worst_drawdown = min(worst_drawdown, value - running_peak)

    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "years": years,
        "capital": float(capital),
        "ending_equity": ending,
        "realised_profit": realised,
        "interest_earned": interest,
        # Money at work, measured against the *starting* balance. It
        # can exceed 100%: a winning account compounds, and thirty
        # $1,000 positions on an account that began with $25,000 is a
        # real state of affairs rather than an accounting error.
        "deployed_vs_start_pct": (deployed_day_dollars / (elapsed_days * capital) * 100
                                  if elapsed_days and capital else 0.0),
        "taken": taken,
        "skipped": skipped,
        "skip_rate_pct": skipped / (taken + skipped) * 100 if (taken + skipped) else 0.0,
        "peak_positions": peak_open,
        "total_return_pct": (ending - capital) / capital * 100,
        "cagr_pct": _safe_cagr(ending, capital, years) * 100,
        "worst_drawdown": worst_drawdown,
    }


def simulate_compounded(trades, stake=1000.0):
    """The same trades, but with profits put back to work.

    The fixed-stake view answers "what is one signal worth" and is the
    right shape for that question. It is the wrong shape for comparing
    against buying the index, because the index compounds and a fixed
    stake does not: every winner's gains sit in cash instead of
    increasing the next position. Over four years that barely matters;
    over twenty it is most of the difference, and the comparison would
    be rigged against the strategy without it.

    So: start with the capital the fixed-stake run needed, size every
    position at an equal fraction of current equity, and let it ride.
    Equal fractions rather than a fixed count because that's what makes
    every signal takeable no matter how the account has grown.
    """
    done = _resolved(trades)
    if not done:
        return None

    slots = simulate_account(done, stake)["peak_positions"]
    equity = starting = slots * stake

    # Sizing is decided at entry, but equity only changes at exit, so the
    # book has to be walked in event order rather than trade order.
    events = []
    for t in done:
        events.append((_date(t["entry_date"]), 0, t))
        events.append((_date(t["exit_date"]), 1, t))
    events.sort(key=lambda e: (e[0], e[1]))

    sizes = {}
    peak_equity = starting
    worst_drawdown_pct = 0.0
    for when, kind, trade in events:
        key = id(trade)
        if kind == 0:
            sizes[key] = equity / slots
        else:
            equity += sizes.pop(key, equity / slots) * trade["return_pct"] / 100.0
            peak_equity = max(peak_equity, equity)
            worst_drawdown_pct = min(worst_drawdown_pct,
                                     (equity - peak_equity) / peak_equity * 100)

    start = min(_date(t["entry_date"]) for t in done)
    end = max(_date(t["exit_date"]) for t in done)
    years = max((end - start).days / 365.25, 1e-9)

    return {
        "starting_capital": starting,
        "ending_equity": equity,
        "total_return_pct": (equity / starting - 1) * 100,
        "cagr_pct": _safe_cagr(equity, starting, years) * 100,
        "worst_drawdown_pct": worst_drawdown_pct,
        "years": years,
    }


def roi_uncertainty(trades, sample_size=100, draws=2000, stake=1000.0, seed=20260728):
    """"What would my return be over 100 trades?" is a distribution.

    Asked once, the honest answer isn't a number — it's a range, and the
    range is usually much wider than the headline average suggests. This
    draws `sample_size` trades at random from the ones that actually
    happened, many times over, and reports where those outcomes land.

    That makes the sample-size problem concrete rather than a warning. A
    strategy whose middle 90% of hundred-trade outcomes runs from -8% to
    +19% has not demonstrated an edge, however good its average looks;
    it has demonstrated that a hundred trades can't tell the difference.

    Sampling with replacement, which is the standard bootstrap. It
    assumes trades are independent and they aren't — they cluster in
    time and in a handful of names — so the real spread is wider still.
    """
    import random

    done = _resolved(trades)
    if len(done) < 2:
        return None

    returns = [t["return_pct"] for t in done]
    rng = random.Random(seed)
    outcomes = []
    for _ in range(draws):
        picked = [returns[rng.randrange(len(returns))] for _ in range(sample_size)]
        outcomes.append(sum(picked) / sample_size)
    outcomes.sort()

    def at(p):
        return outcomes[min(int(len(outcomes) * p), len(outcomes) - 1)]

    return {
        "sample_size": sample_size,
        "draws": draws,
        "p5": at(0.05),
        "p25": at(0.25),
        "median": at(0.50),
        "p75": at(0.75),
        "p95": at(0.95),
        "share_losing": sum(1 for o in outcomes if o <= 0) / len(outcomes) * 100,
        "dollars_p5": stake * sample_size * at(0.05) / 100,
        "dollars_median": stake * sample_size * at(0.50) / 100,
        "dollars_p95": stake * sample_size * at(0.95) / 100,
    }


def benchmark_buy_and_hold(index_bars, start, end):
    """What simply buying the index and doing nothing would have returned
    over the same window — the number the strategy has to beat to justify
    existing."""
    inside = [b for b in index_bars if start <= b["date"][:10] <= end]
    if len(inside) < 2:
        return None
    first, last = inside[0]["close"], inside[-1]["close"]
    years = max((_date(inside[-1]["date"]) - _date(inside[0]["date"])).days / 365.25, 1e-9)
    total = (last / first - 1) * 100
    return {
        "start": inside[0]["date"][:10],
        "end": inside[-1]["date"][:10],
        "total_return_pct": total,
        "cagr_pct": ((last / first) ** (1 / years) - 1) * 100,
        "years": years,
    }


def format_report(trades, benchmark=None, stake=1000.0, label=""):
    """A report meant to be read by someone who doesn't already know the
    vocabulary, so each figure says what it means."""
    per_trade = summarise_trades(trades, stake)
    account = simulate_account(trades, stake)
    compounded = simulate_compounded(trades, stake)
    if not per_trade or not account:
        return f"{label}: no resolved trades to report."

    money = lambda v: f"${v:,.0f}"
    out = []
    add = out.append

    add(f"\n{'=' * 68}")
    add(f"{label or 'Simulation'}")
    add(f"{'=' * 68}")
    add(f"Window {account['start']} to {account['end']}  "
        f"({account['years']:.1f} years)")
    add(f"{account['n']} completed trades"
        + (f", {per_trade['still_open']} still open and excluded"
           if per_trade["still_open"] else ""))
    add(f"about {account['trades_per_year']:.0f} signals a year")

    add(f"\n-- What one signal was worth ------------------------------------")
    add(f"  Right {per_trade['win_rate']:.1f}% of the time. Most trades lose;")
    add(f"  the median trade returned {per_trade['median_pct']:+.2f}%, while the")
    add(f"  average returned {per_trade['mean_pct']:+.2f}% because the winners are bigger.")
    add(f"  Average winner is {per_trade['payoff']:.2f}x the average loser.")
    add(f"  Best {per_trade['best_pct']:+.1f}%, worst {per_trade['worst_pct']:+.1f}%.")
    add(f"  Typical holding period {per_trade['median_hold_weeks']:.0f} weeks.")
    add(f"\n  The spread, which the average hides:")
    add(f"    worst 5%    {per_trade['p5_pct']:>+7.1f}%")
    add(f"    lower qtr   {per_trade['p25_pct']:>+7.1f}%")
    add(f"    median      {per_trade['median_pct']:>+7.1f}%")
    add(f"    upper qtr   {per_trade['p75_pct']:>+7.1f}%")
    add(f"    best 5%     {per_trade['p95_pct']:>+7.1f}%")
    add(f"  {per_trade['share_losing_20pct']:.1f}% of trades lost more than 20%; "
        f"{per_trade['share_gaining_50pct']:.1f}% gained more than 50%.")

    add(f"\n-- Putting {money(stake)} into every signal -----------------------------")
    add(f"  {money(per_trade['capital_deployed'])} deployed across {per_trade['n']} trades")
    add(f"  Net profit {money(per_trade['total_profit'])}")
    add(f"  = {per_trade['roi_on_deployed']:+.1f}% on money actually put to work")
    if per_trade["top5_share"] == per_trade["top5_share"]:  # not NaN
        add(f"  The 5 best trades produced {per_trade['top5_share']:.0f}% of all profit.")
        add(f"  (If that is most of it, the result rests on a handful of names.)")

    add(f"\n-- What the account would have done ------------------------------")
    add(f"  Most positions open at once: {account['peak_positions']}")
    add(f"  So you'd have needed {money(account['capital_required'])} on hand to take every signal.")
    add(f"  Profit {money(account['realised_profit'])} on that capital "
        f"= {account['total_return_pct']:+.1f}% total")
    add(f"  which is {account['cagr_pct']:+.1f}% a year compounded.")
    add(f"  Worst run of losses along the way: {money(account['worst_drawdown'])}")
    add(f"\n  Money is not all working all the time. On average only "
        f"{money(account['avg_capital'])} was")
    add(f"  actually in the market, so per dollar-year of exposure the rate is")
    add(f"  {account['cagr_on_average_pct']:+.1f}% a year. The truth is between these two: you")
    add(f"  cannot size an account to the average and still take every signal.")

    add(f"\n-- With profits reinvested ---------------------------------------")
    add(f"  The figures above never compound: every trade gets the same")
    add(f"  {money(stake)} however well the account has done. Putting the gains back")
    add(f"  to work, at an equal fraction of equity per position:")
    add(f"  {money(compounded['starting_capital'])} becomes {money(compounded['ending_equity'])} "
        f"= {compounded['total_return_pct']:+.1f}% total,")
    add(f"  or {compounded['cagr_pct']:+.1f}% a year. Deepest fall from a high along the")
    add(f"  way: {compounded['worst_drawdown_pct']:.1f}%.")

    spread = roi_uncertainty(trades, sample_size=100, stake=stake)
    if spread:
        add(f"\n-- If you only got 100 signals -----------------------------------")
        add(f"  Drawing 100 trades at random from these, {spread['draws']:,} times over,")
        add(f"  to show how much a 100-trade run is down to luck:")
        add(f"    worst 5% of runs:  {spread['p5']:+.2f}% a trade  "
            f"({money(spread['dollars_p5'])} on {money(stake * 100)})")
        add(f"    typical run:       {spread['median']:+.2f}% a trade  "
            f"({money(spread['dollars_median'])})")
        add(f"    best 5% of runs:   {spread['p95']:+.2f}% a trade  "
            f"({money(spread['dollars_p95'])})")
        add(f"  {spread['share_losing']:.0f}% of 100-trade runs lost money outright.")
        if spread["p5"] < 0 < spread["p95"]:
            add(f"  The range crosses zero, so 100 trades cannot tell a real edge")
            add(f"  here from luck — regardless of what the average says.")

    if benchmark:
        add(f"\n-- Against simply buying the index -------------------------------")
        add(f"  SPY over the same window: {benchmark['total_return_pct']:+.1f}% total, "
            f"{benchmark['cagr_pct']:+.1f}% a year.")
        lo, hi = account["cagr_pct"], max(account["cagr_on_average_pct"],
                                          compounded["cagr_pct"])
        verdict = "BEATS" if lo > benchmark["cagr_pct"] else (
            "STRADDLES" if hi > benchmark["cagr_pct"] else "LOSES TO")
        add(f"  The strategy earned between {lo:+.1f}% and {hi:+.1f}% a year "
            f"depending on")
        add(f"  how the capital is counted, so it {verdict} buy-and-hold.")
        if hi <= benchmark["cagr_pct"]:
            add(f"  A positive return is not the same as a good one. Doing nothing")
            add(f"  would have earned more with no work and no risk of being wrong.")

    return "\n".join(out)
