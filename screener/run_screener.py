"""Entry point: runs the Weinstein stage-analysis screener across the
watchlist and writes results to data/screener.db.

I add the project root to sys.path so this works whether it's invoked as
`python -m screener.run_screener` or run directly as a script.
"""
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from screener import conditions, data_fetch, db

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
        "conditions_detail": result["conditions_detail"],
        "notes": None,
    }
    db.insert_result(row)
    return row


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

    header = f"{'TICKER':<8}{'STAGE':<7}{'MET':<5}{'ACTIONABLE':<12}{'REVIEW':<8}"
    print(header)
    print("-" * len(header))
    for row in rows:
        actionable = "yes" if conditions.is_actionable(row["conditions_met"]) else "no"
        review = "review" if _needs_manual_review(row["conditions_detail"]) else ""
        stage = row["stage"] if row["stage"] is not None else "?"
        print(f"{row['ticker']:<8}{str(stage):<7}{row['conditions_met']:<5}{actionable:<12}{review:<8}")


def main():
    run_date = datetime.date.today().isoformat()
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
