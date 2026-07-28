"""Entry point: runs the Weinstein stage-analysis screener across the
watchlist and writes results to data/screener.db.

I add the project root to sys.path so this works whether it's invoked as
`python -m screener.run_screener` or run directly as a script.
"""
import argparse
import datetime
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from screener import (
    conditions, data_fetch, db, position_sizing, rate_limit, sector_scan,
    stop_loss, universe,
)

# Cheap heuristic pointer for run_screener's summary only — not a real
# evaluation. See conditions.py's module docstring for why the short
# side isn't just these 9 conditions inverted.
SHORT_CANDIDATE_MAX_CONDITIONS_MET = 3

# Fetch slightly deeper than the evaluation window: the in-progress week
# gets dropped on arrival, so asking for exactly the window would leave
# every evaluation one bar short of it.
FETCH_WEEKS = conditions.EVALUATION_WEEKS + 2

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
TICKERS_PATH = os.path.join(CONFIG_DIR, "tickers.json")
TICKERS_EXAMPLE_PATH = os.path.join(CONFIG_DIR, "tickers.example.json")


def _load_tickers():
    path = TICKERS_PATH
    if not os.path.exists(path):
        print(
            f"config/tickers.json not found — falling back to "
            f"{os.path.basename(TICKERS_EXAMPLE_PATH)}. Copy config/tickers.example.json "
            "to config/tickers.json and add a real watchlist when ready."
        )
        path = TICKERS_EXAMPLE_PATH

    with open(path) as f:
        data = json.load(f)
    return data.get("tickers", [])


def _evaluate_and_store(ticker, run_date, bars, index_bars, sector_data):
    """Scores one ticker against already-fetched bars and persists the row.

    Split out from _process_ticker so the universe scan can reuse exactly
    this logic. That path fetches bars in batches and sector data lazily,
    so it has nothing to gain from per-ticker fetching — but it must not
    diverge on how a result is scored, sized, or stored.
    """
    result = conditions.evaluate_conditions(ticker, bars, index_bars, sector_data)

    # Stop-loss/entry-plan are only meaningful once a ticker actually
    # qualifies, and only if there's a real breakout bar to size them
    # against — a Stage 2 pass without a breakout inside the recent
    # lookback window (see conditions.py's _find_base_and_breakout)
    # leaves breakout_idx as None, and I'm not guessing an entry point.
    stop = None
    entry_plan = None
    if result["actionable"]:
        breakout_idx = result.get("breakout_idx")
        if breakout_idx is not None:
            breakout_price = bars[breakout_idx]["close"]
            stop = stop_loss.trailing_stop(bars, breakout_price, breakout_idx)
            entry_plan = position_sizing.get_entry_plan(
                breakout_price, current_price=result["price"]
            )

    conditions_detail = result["conditions_detail"]
    if stop is not None:
        conditions_detail["stop_loss"] = stop
    if entry_plan is not None:
        conditions_detail["entry_plan"] = entry_plan

    row = {
        "ticker": ticker,
        "run_date": run_date,
        "stage": result["stage"],
        "price": result["price"],
        "ma_30w": result["ma_30w"],
        "price_above_ma": result["price_above_ma"],
        "ma_rising": result["ma_rising"],
        "mansfield_rs": result["mansfield_rs"],
        "rs_improving": result["rs_improving"],
        "volume_ratio": result["volume_ratio"],
        "volume_confirmed": result["volume_confirmed"],
        "sector": sector_data.get("sector") if sector_data else None,
        "sector_strength_pct": sector_data.get("sector_strength_pct") if sector_data else None,
        "market_stage_ok": result["market_stage_ok"],
        "resistance_level": result["resistance_level"],
        "breakout_confirmed": result["breakout_confirmed"],
        "swing_target": result["swing_target"],
        "swing_stop": result["swing_stop"],
        "conditions_met": result["conditions_met"],
        "conditions_detail": conditions_detail,
        "notes": None,
        "stop_loss": stop,
        "entry_plan": entry_plan,
        # In-memory only for the summary table — db.insert_result filters
        # to RESULT_COLUMNS, and these persist inside conditions_detail.
        "scoring": result["scoring"],
        "breakout_age_weeks": result["breakout_age_weeks"],
        "base_is_tight": result["base_is_tight"],
        "base_range_pct": result["base_range_pct"],
    }
    db.insert_result(row)
    return row


def _process_ticker(ticker, run_date, index_bars):
    bars = data_fetch.get_weekly_bars(ticker, lookback_weeks=FETCH_WEEKS)
    sector_data = data_fetch.get_sector_data(ticker)
    return _evaluate_and_store(ticker, run_date, bars, index_bars, sector_data)


def _could_still_qualify(result):
    """Whether a ticker scored *without* sector data could still become
    actionable once that sector lookup happens.

    This is what makes a full-market scan affordable. The sector lookup
    is the one genuinely per-ticker API call left, so it's worth spending
    only on names that could actually clear the bar. Everything else in
    the checklist is computable from bars alone.

    The test is exact rather than a heuristic, so it can't discard a real
    candidate: assume the pending sector condition resolves in the
    ticker's favour and ask whether that would be enough. Nothing else is
    assumed — the other unknowns stay unknown, because they're unresolved
    for reasons the chart won't change (no breakout to measure, not in a
    pullback), not for want of another API call.
    """
    scoring = result["scoring"]
    if scoring["blocking"]:
        return False

    # Only credit the sector condition if it's actually still pending.
    # Adding it unconditionally would inflate both counts on any result
    # that already has a sector — and push the resolved total past the
    # nine conditions that exist.
    pending = 1 if result["conditions"].get("sector_strength") is None else 0
    best_met = scoring["met"] + pending
    best_resolved = scoring["resolved"] + pending
    if best_resolved < conditions.MIN_RESOLVED_CONDITIONS:
        return False
    return best_met >= math.ceil(conditions.ACTIONABLE_SCORE * best_resolved)


def _looks_like_short_candidate(row):
    """Cheap heuristic pointer only, not a real evaluation — flags
    tickers scoring low on the long checklist while already in Stage 3/4
    with declining or negative RS, so that signal isn't silently thrown
    away before the real short checklist exists. See conditions.py's
    module docstring.
    """
    if row["conditions_met"] > SHORT_CANDIDATE_MAX_CONDITIONS_MET:
        return False
    if row["stage"] not in (3, 4):
        return False
    mrs = row["mansfield_rs"]
    negative_rs = mrs is not None and mrs < 0
    declining_rs = row["rs_improving"] is False
    return negative_rs or declining_rs


def _process_universe(run_date, index_bars, limit=None, min_dollar_volume=None,
                       include_funds=False, include_non_common=False):
    """Screens the whole tradable universe rather than a list I wrote.

    Shaped as a funnel because the costs are wildly uneven. Discovery and
    metadata filtering are nearly free, bars are cheap in batches of
    twenty, and the sector lookup is the only real per-ticker expense —
    so it goes last, applied to the few hundred names that could still
    qualify rather than the few thousand that can't.
    """
    symbols = universe.get_universe(include_funds=include_funds,
                                    include_non_common=include_non_common)
    if limit:
        symbols = symbols[:limit]
        print(f"--limit: screening the first {len(symbols)} symbols only")

    print(f"fetching weekly bars for {len(symbols)} symbols "
          f"({(len(symbols) + data_fetch.MAX_SYMBOLS_PER_BATCH - 1) // data_fetch.MAX_SYMBOLS_PER_BATCH} batched calls)...")
    bars_by_symbol = data_fetch.get_weekly_bars_batch(symbols, lookback_weeks=FETCH_WEEKS)
    print(f"  got bars for {len(bars_by_symbol)} of {len(symbols)}")

    kwargs = {"report": True}
    if min_dollar_volume is not None:
        kwargs["min_dollar_volume"] = min_dollar_volume
    bars_by_symbol = universe.filter_by_liquidity(bars_by_symbol, **kwargs)

    # Score everything on bars alone. No API calls here, so it's cheap to
    # run across the whole survivor set and lets the sector spend be
    # aimed precisely.
    candidates = []
    near_misses = []
    for symbol, bars in bars_by_symbol.items():
        try:
            provisional = conditions.evaluate_conditions(symbol, bars, index_bars, None)
        except Exception as exc:
            print(f"[{symbol}] skipped during prefilter — {exc}")
            continue
        if _could_still_qualify(provisional):
            candidates.append((symbol, bars))
        elif not provisional["scoring"]["blocking"]:
            near_misses.append((symbol, provisional))

    print(f"prefilter: {len(candidates)} could still qualify, "
          f"{len(near_misses)} scored but can't reach the bar")

    rows = []
    for i, (symbol, bars) in enumerate(candidates, 1):
        try:
            sector_data = data_fetch.get_sector_data(symbol)
            rows.append(_evaluate_and_store(symbol, run_date, bars, index_bars, sector_data))
        except Exception as exc:
            print(f"[{symbol}] skipped — {exc}")
        if i % 25 == 0:
            used, cap = rate_limit.snapshot()
            print(f"  evaluated {i}/{len(candidates)} (rate budget {used}/{cap})")

    _print_near_misses(near_misses)
    return rows


def _print_near_misses(near_misses, top=10):
    """Names that scored cleanly but can't reach actionable — the
    monitoring list. Reported from the sector-less pass, so it costs
    nothing beyond bars already fetched.
    """
    if not near_misses:
        return
    ranked = sorted(
        near_misses,
        key=lambda pair: (pair[1]["scoring"]["met"], -pair[1]["scoring"]["failed"]),
        reverse=True,
    )[:top]
    print()
    print(f"closest non-qualifying ({len(near_misses)} total, showing {len(ranked)}) — "
          "scored without sector data, so not directly comparable to the table above:")
    for symbol, result in ranked:
        s = result["scoring"]
        stage = result["stage"] if result["stage"] is not None else "?"
        print(f"  {symbol:<8} stage {stage}  {s['met']} met / {s['failed']} failed / {s['unknown']} unknown")


def _needs_manual_review(conditions_detail):
    # pullback_quality/risk_reward only need a human look when they came
    # back genuinely ambiguous (None). resistance_breakout always does,
    # regardless of its result, since the pivot/trend-line read behind it
    # is an approximation — see trend_support_resistance.py.
    ambiguous_review = any(
        conditions_detail[name]["result"] is None and conditions_detail[name].get("manual_review")
        for name in ("pullback_quality", "risk_reward")
        if name in conditions_detail
    )
    always_review = conditions_detail.get("resistance_breakout", {}).get("manual_review", False)
    return ambiguous_review or always_review


def _rank_key(row):
    """Ordering for the summary, most worth looking at first.

    A watchlist of twenty came out in whatever order it was written and
    that was fine. A full-market scan surfaced 225 actionable names,
    which is a list nobody works through — so the ordering has to carry
    real information.

    Priorities, in order: setups that qualify; then ones still entryable
    rather than already extended past the breakout, since the book is
    explicit about not chasing; then a strong sector, which is Weinstein's
    own top-down sequence and the reason sector rank is worth keeping
    even once the universe is screened directly; then the proportion of
    resolved conditions met; then the freshest breakout.
    """
    scoring = row["scoring"]
    plan = row.get("entry_plan") or {}
    detail = row["conditions_detail"].get("sector_strength", {})
    percentile = detail.get("sector_strength_percentile")
    age = row.get("breakout_age_weeks")
    return (
        0 if scoring["actionable"] else 1,
        1 if plan.get("extended") else 0,
        -(percentile if percentile is not None else -1),
        -(scoring["score"] or 0),
        age if age is not None else 10_000,
    )


def _print_summary(rows, detail_limit=25):
    if not rows:
        print("No results.")
        return

    rows = sorted(rows, key=_rank_key)
    actionable_total = sum(1 for r in rows if r["scoring"]["actionable"])
    if actionable_total > detail_limit:
        print(f"{actionable_total} names qualify — showing full detail for the top "
              f"{detail_limit} by sector strength and entry quality.\n")

    header = (
        f"{'TICKER':<8}{'STAGE':<7}{'MET':<5}{'FAIL':<6}{'UNK':<5}"
        f"{'ACTIONABLE':<12}{'REVIEW':<8}{'SHORT?':<8}"
    )
    print(header)
    print("-" * len(header))
    shown = 0
    for row in rows:
        scoring = row["scoring"]
        is_actionable = scoring["actionable"]
        # Every row still gets a line; only the supporting detail is
        # capped, so nothing disappears silently from the scan.
        verbose = is_actionable and shown < detail_limit
        if verbose:
            shown += 1
        actionable = "yes" if is_actionable else "no"
        review = "review" if _needs_manual_review(row["conditions_detail"]) else ""
        stage = row["stage"] if row["stage"] is not None else "?"
        short_flag = "short?" if _looks_like_short_candidate(row) else ""
        print(
            f"{row['ticker']:<8}{str(stage):<7}{scoring['met']:<5}{scoring['failed']:<6}"
            f"{scoring['unknown']:<5}{actionable:<12}{review:<8}{short_flag:<8}"
        )
        # Blocked-by-hard-gate and not-enough-evidence are very different
        # from "narrowly missed", so say which one it was.
        if not is_actionable and (scoring["blocking"] or scoring["resolved"] < conditions.MIN_RESOLVED_CONDITIONS):
            print(f"    {scoring['reason']}")

        if verbose:
            stop = row.get("stop_loss")
            if stop and stop.get("recommended") is not None:
                print(
                    f"    trailing stop ({stop['method']}): {stop['recommended']:.2f}"
                )
            elif stop:
                # Both methods can legitimately come back empty on a fresh
                # breakout: the MA stop waits for price to clear the average
                # by a margin, and a swing-low stop needs a confirmed pivot
                # since entry. Say so rather than printing "None", and fall
                # back to the initial stop, which is what's actually in force.
                initial = row.get("swing_stop")
                fallback = f", use the initial stop at {initial:.2f}" if initial else ""
                print(f"    trailing stop: not established yet{fallback}")
            age = row.get("breakout_age_weeks")
            if age is not None:
                tight = row.get("base_is_tight")
                rng = row.get("base_range_pct")
                tightness = "" if tight is None else (
                    f", base {'tight' if tight else 'LOOSE'} ({rng:.0f}% wide)"
                )
                print(f"    breakout was {age} week(s) ago{tightness}")

            entry_plan = row.get("entry_plan")
            if entry_plan:
                entries = ", ".join(
                    f"{e['size_pct']}% @ {e['price']:.2f} ({e['note']})"
                    for e in entry_plan["entries"]
                )
                print(f"    entry plan ({entry_plan['style']}): {entries}")
                if entry_plan.get("note"):
                    print(f"    {entry_plan['note']}")


def _parse_args():
    parser = argparse.ArgumentParser(description="Run the Weinstein stage-analysis screener.")
    parser.add_argument(
        "--broad", action="store_true",
        help="Build the ticker list from the top-ranked sectors' curated universes "
             "(screener/sector_scan.py) instead of reading config/tickers.json.",
    )
    parser.add_argument(
        "--top-n", type=int, default=3,
        help="Number of top-ranked sectors to pull into a --broad scan (default 3).",
    )
    parser.add_argument(
        "--universe", action="store_true",
        help="Screen every tradable listing rather than a curated list. This is "
             "the only mode that can surface a stock I didn't already know to look at.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Cap how many symbols a --universe scan looks at. For trying things "
             "out without spending a full pass.",
    )
    parser.add_argument(
        "--min-dollar-volume", type=float, default=None,
        help="Override the liquidity floor for a --universe scan, in dollars of "
             "average weekly turnover.",
    )
    parser.add_argument(
        "--include-funds", action="store_true",
        help="Also screen ETFs, closed-end funds and similar pooled products, "
             "which a --universe scan skips by default because they crowd out "
             "individual stocks and carry no sector classification.",
    )
    parser.add_argument(
        "--include-non-common", action="store_true",
        help="Also screen preferred shares, SPAC units, warrants and rights. "
             "Off by default: these pass the checklist for the wrong reasons, "
             "since their price is driven by rates or a pending deal rather "
             "than by a business. Provided so the exclusion can be measured.",
    )
    return parser.parse_args()


def main():
    args = _parse_args()
    run_date = datetime.date.today().isoformat()

    db.init_db()

    # One index fetch for the whole run. This used to happen once per
    # ticker, which was invisible on a 20-name watchlist and would have
    # been thousands of redundant calls across a universe scan.
    index_bars = data_fetch.get_index_bars("SPY", lookback_weeks=FETCH_WEEKS)

    if args.universe:
        summary_rows = _process_universe(
            run_date, index_bars, limit=args.limit,
            min_dollar_volume=args.min_dollar_volume,
            include_funds=args.include_funds,
            include_non_common=args.include_non_common,
        )
    else:
        if args.broad:
            tickers = sector_scan.build_watchlist_from_top_sectors(n=args.top_n)
            print(f"--broad: built a {len(tickers)}-ticker watchlist from the top {args.top_n} sectors.")
        else:
            tickers = _load_tickers()

        db.seed_watchlist_from_config(tickers, run_date)

        summary_rows = []
        for ticker in tickers:
            try:
                summary_rows.append(_process_ticker(ticker, run_date, index_bars))
            except Exception as exc:
                print(f"[{ticker}] skipped — {exc}")

    print()
    _print_summary(summary_rows)


if __name__ == "__main__":
    main()
