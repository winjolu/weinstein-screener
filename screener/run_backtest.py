"""Entry point: runs one or more named parameter sets over a ticker
universe and date range, then prints the comparison table.

I add the project root to sys.path so this works whether it's invoked
as `python -m screener.run_backtest` or run directly as a script.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from screener import backtest, backtest_report, bar_cache, db, sector_scan

# Named parameter sets worth comparing against baseline — see
# backtest.py's _condition_overrides for how these get applied.
# conditions.py's own constant names, e.g. TSR_PIVOT_LENGTH, are the keys.
DEFAULT_PARAMETER_SETS = {
    "baseline": {},
    "pivot_length=10": {"TSR_PIVOT_LENGTH": 10},
    "risk_reward_pass=2.0": {"RISK_REWARD_CLEAR_PASS": 2.0},
    "sector_strength_pass=70": {"SECTOR_STRENGTH_PERCENTILE_PASS": 70},
}


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Backtest the screener's checklist over a historical date range."
    )
    parser.add_argument(
        "--tickers", nargs="*",
        help="Explicit ticker list. Defaults to the sector_scan broad universe.",
    )
    parser.add_argument(
        "--top-n", type=int, default=3,
        help="Sectors to pull tickers from if --tickers isn't given (default 3).",
    )
    parser.add_argument("--start", required=True, help="Backtest start date, YYYY-MM-DD.")
    parser.add_argument("--end", required=True, help="Backtest end date, YYYY-MM-DD.")
    parser.add_argument("--interval-weeks", type=int, default=4)
    parser.add_argument("--max-hold-weeks", type=int, default=52)
    parser.add_argument(
        "--parameter-sets", nargs="*",
        help="Named parameter sets to run, from DEFAULT_PARAMETER_SETS "
             "(default: all of them). Example: baseline pivot_length=10",
    )
    return parser.parse_args()


def main():
    args = _parse_args()

    tickers = args.tickers if args.tickers else sector_scan.build_watchlist_from_top_sectors(n=args.top_n)
    print(f"Backtesting {len(tickers)} tickers from {args.start} to {args.end}: {tickers}")

    parameter_sets = DEFAULT_PARAMETER_SETS
    if args.parameter_sets:
        unknown = [name for name in args.parameter_sets if name not in DEFAULT_PARAMETER_SETS]
        if unknown:
            raise SystemExit(
                f"Unknown parameter set(s): {unknown}. "
                f"Known sets: {list(DEFAULT_PARAMETER_SETS)}"
            )
        parameter_sets = {name: DEFAULT_PARAMETER_SETS[name] for name in args.parameter_sets}

    db.init_db()

    for name, overrides in parameter_sets.items():
        print(f"--- running parameter set: {name} ---")
        trades = backtest.run_backtest(
            tickers, args.start, args.end,
            check_interval_weeks=args.interval_weeks,
            parameter_set=name,
            max_hold_weeks=args.max_hold_weeks,
            **overrides,
        )
        print(f"{name}: {len(trades)} trades recorded.")

        # What the arm consumed, not just what it was told to do. The W2
        # and W3 figures stopped reproducing because their bar cache was
        # a symlink into a scratch directory that got cleaned, and
        # nothing anywhere recorded which file an arm had run against.
        db.record_provenance(name, bar_cache_path=bar_cache.CACHE_PATH)

    print()
    backtest_report.summarize()


if __name__ == "__main__":
    main()
