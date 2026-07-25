"""Entry point: runs the Weinstein stage-analysis screener across the
watchlist and writes results to data/screener.db.

I add the project root to sys.path so this works whether it's invoked as
`python -m screener.run_screener` or run directly as a script.
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from screener import conditions, data_fetch, db, position_sizing, sector_scan, stop_loss

# Cheap heuristic pointer for run_screener's summary only — not a real
# evaluation. See conditions.py's module docstring for why the short
# side isn't just these 9 conditions inverted.
SHORT_CANDIDATE_MAX_CONDITIONS_MET = 3

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


def _process_ticker(ticker, run_date):
    bars = data_fetch.get_weekly_bars(ticker)
    index_bars = data_fetch.get_index_bars("SPY")
    sector_data = data_fetch.get_sector_data(ticker)

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
            entry_plan = position_sizing.get_entry_plan(breakout_price)

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
        # to RESULT_COLUMNS, and scoring persists inside conditions_detail.
        "scoring": result["scoring"],
    }
    db.insert_result(row)
    return row


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


def _print_summary(rows):
    if not rows:
        print("No results.")
        return

    header = (
        f"{'TICKER':<8}{'STAGE':<7}{'MET':<5}{'FAIL':<6}{'UNK':<5}"
        f"{'ACTIONABLE':<12}{'REVIEW':<8}{'SHORT?':<8}"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        scoring = row["scoring"]
        is_actionable = scoring["actionable"]
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

        if is_actionable:
            stop = row.get("stop_loss")
            if stop:
                print(
                    f"    stop-loss ({stop['method']} recommended): "
                    f"ma={stop['ma_stop']} swing_low={stop['swing_low_stop']} "
                    f"-> {stop['recommended']}"
                )
            entry_plan = row.get("entry_plan")
            if entry_plan:
                entries = ", ".join(
                    f"{e['size_pct']}% @ {e['price']:.2f} ({e['note']})"
                    for e in entry_plan["entries"]
                )
                print(f"    entry plan ({entry_plan['style']}): {entries}")


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
    return parser.parse_args()


def main():
    args = _parse_args()
    run_date = datetime.date.today().isoformat()

    if args.broad:
        tickers = sector_scan.build_watchlist_from_top_sectors(n=args.top_n)
        print(f"--broad: built a {len(tickers)}-ticker watchlist from the top {args.top_n} sectors.")
    else:
        tickers = _load_tickers()

    db.init_db()
    db.seed_watchlist_from_config(tickers, run_date)

    summary_rows = []
    for ticker in tickers:
        try:
            row = _process_ticker(ticker, run_date)
            summary_rows.append(row)
        except Exception as exc:
            print(f"[{ticker}] skipped — {exc}")

    _print_summary(summary_rows)


if __name__ == "__main__":
    main()
