"""Summarizes backtest_trades: win rate, average return, average
R-multiple, and trade count, grouped by parameter_set so different
condition_overrides combinations can be compared on the same metrics.
"""
from . import db

# Below this many resolved trades for a parameter_set, the comparison
# table flags it rather than implying a conclusion the sample can't
# support.
MIN_TRADES_FOR_CONFIDENCE = 30


def _compute(parameter_set=None):
    trades = db.get_backtest_trades(parameter_set=parameter_set)

    grouped = {}
    for t in trades:
        grouped.setdefault(t["parameter_set"], []).append(t)

    results = []
    for ps, group in grouped.items():
        resolved = [t for t in group if not t["still_open"]]
        n = len(resolved)
        still_open_count = len(group) - n

        wins = sum(1 for t in resolved if t["return_pct"] is not None and t["return_pct"] > 0)
        returns = [t["return_pct"] for t in resolved if t["return_pct"] is not None]
        r_multiples = [t["r_multiple"] for t in resolved if t["r_multiple"] is not None]

        results.append({
            "parameter_set": ps,
            "trade_count": n,
            "still_open_count": still_open_count,
            "win_rate": (wins / n * 100) if n else None,
            "avg_return_pct": (sum(returns) / len(returns)) if returns else None,
            "avg_r_multiple": (sum(r_multiples) / len(r_multiples)) if r_multiples else None,
            "low_confidence": n < MIN_TRADES_FOR_CONFIDENCE,
        })

    return results


def _print_table(results):
    if not results:
        print("No backtest trades recorded yet.")
        return

    header = f"{'PARAM SET':<24}{'TRADES':<8}{'OPEN':<6}{'WIN%':<8}{'AVG RET%':<10}{'AVG R':<8}{'NOTE'}"
    print(header)
    print("-" * len(header))
    for r in sorted(results, key=lambda x: x["parameter_set"]):
        win_rate = f"{r['win_rate']:.1f}" if r["win_rate"] is not None else "n/a"
        avg_ret = f"{r['avg_return_pct']:.2f}" if r["avg_return_pct"] is not None else "n/a"
        avg_r = f"{r['avg_r_multiple']:.2f}" if r["avg_r_multiple"] is not None else "n/a"
        note = (
            f"only {r['trade_count']} trades — too few to draw a real conclusion "
            f"(want {MIN_TRADES_FOR_CONFIDENCE}+)"
            if r["low_confidence"] else ""
        )
        print(
            f"{r['parameter_set']:<24}{r['trade_count']:<8}{r['still_open_count']:<6}"
            f"{win_rate:<8}{avg_ret:<10}{avg_r:<8}{note}"
        )


def summarize(parameter_set=None):
    """Computes and prints the comparison table, and returns the
    underlying data (each entry flagged "low_confidence" when its
    resolved-trade count is under MIN_TRADES_FOR_CONFIDENCE) for
    programmatic use.
    """
    results = _compute(parameter_set=parameter_set)
    _print_table(results)
    return results
