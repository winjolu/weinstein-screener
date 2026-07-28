"""Reading back what the screener already found.

The scan writes far more than it prints. A universe run stores a full
condition breakdown for every name that reached the prefilter, and until
now the only ways to see any of it were a terminal dump of three hundred
names or hand-written SQL. That's the wrong shape for the thing I
actually want to do, which is work through candidates one at a time and
notice what changed since last week.

Everything here reads the database and nothing here calls the API. That's
deliberate: it makes the tool instant and usable offline, and it means I
can interrogate a scan long after the market data behind it has moved on.
A report can therefore never surprise me with a different answer than the
scan gave — if a number looks wrong, the scan is where to look.
"""
import argparse
import datetime
import json
import sys

from screener import conditions, db

# Conditions in checklist order, with the short labels I use when reading
# them down a column rather than the internal keys.
CONDITION_LABELS = (
    ("stage_setup", "1. Stage 2 setup"),
    ("price_above_ma", "2. Price above 30wk MA"),
    ("volume_confirmation", "3. Volume confirms"),
    ("rs_improving", "4. Relative strength rising"),
    ("sector_strength", "5. Sector is strong"),
    ("market_stage", "6. Market not Stage 4"),
    ("resistance_breakout", "7. Resistance broken"),
    ("pullback_quality", "8. Pullback is orderly"),
    ("risk_reward", "9. Risk/reward acceptable"),
)

MARKS = {True: "PASS", False: "FAIL", None: " ?  "}


def _load(row):
    """One stored row, with its JSON blob already parsed."""
    row = dict(row)
    row["detail"] = json.loads(row["conditions_detail"] or "{}")
    return row


def _fmt(value, places=2, dash="-"):
    if value is None:
        return dash
    return f"{value:,.{places}f}"


def _why(name, detail):
    """The number that explains a condition's verdict, where there is one.

    I want enough to know whether to pull up the chart, not the whole
    blob. Anything not summarised here is still in --json.
    """
    d = detail.get(name) or {}
    if name == "volume_confirmation":
        ratio, phase = d.get("volume_ratio"), d.get("phase")
        if ratio is None:
            return ""
        return f"{ratio:.2f}x 4wk avg" + (f", {phase}" if phase else "")
    if name == "sector_strength":
        pct = d.get("sector_strength_percentile")
        return "" if pct is None else f"{pct:.0f}th percentile"
    if name == "resistance_breakout":
        level = d.get("resistance_level")
        return f"level {_fmt(level)}" if level is not None else "no level found"
    if name == "risk_reward":
        parts = []
        if d.get("stop_pct") is not None:
            parts.append(f"stop {d['stop_pct']:.1f}% away")
        if d.get("stop_too_wide"):
            parts.append(f"wider than the {conditions.MAX_SENSIBLE_STOP_PCT:.0f}% ceiling")
        if d.get("target_method"):
            parts.append(f"target via {d['target_method']}")
        return ", ".join(parts)
    if name == "rs_improving" and d.get("rs_ma_rising") is not None:
        return "RS average rising" if d["rs_ma_rising"] else "RS average flat or falling"
    return ""


def show_ticker(ticker, as_json=False, history_limit=12):
    """Everything stored about one name, plus how it has scored over time."""
    ticker = ticker.upper()
    rows = [_load(r) for r in db.get_ticker_history(ticker, history_limit)]
    if not rows:
        print(f"No stored results for {ticker}.")
        print("It either hasn't been scanned, or it never cleared the universe")
        print("prefilter — a scan only stores names that could still qualify.")
        return 1

    rows.sort(key=lambda r: r["run_date"])
    latest = rows[-1]
    detail = latest["detail"]
    scoring = detail.get("scoring", {})

    if as_json:
        print(json.dumps(latest["detail"], indent=2, sort_keys=True))
        return 0

    print(f"\n{ticker} — as of {latest['run_date']}")
    print("=" * 62)
    print(f"  Stage {latest['stage'] or '?'}    "
          f"price {_fmt(latest['price'])}    "
          f"30wk MA {_fmt(latest['ma_30w'])}    "
          f"sector: {latest['sector'] or 'unknown'}")

    verdict = "ACTIONABLE" if scoring.get("actionable") else "not actionable"
    print(f"\n  {verdict} — {scoring.get('reason', 'no verdict recorded')}")
    if scoring.get("blocking"):
        print(f"  Blocked by: {', '.join(scoring['blocking'])}")

    print("\n  Checklist")
    print("  " + "-" * 60)
    for key, label in CONDITION_LABELS:
        result = (detail.get(key) or {}).get("result")
        note = _why(key, detail)
        flag = "  (eyeball this one)" if (detail.get(key) or {}).get("low_confidence") else ""
        print(f"  [{MARKS[result]}] {label:<28} {note}{flag}")

    stop = detail.get("stop_loss") or {}
    if stop.get("recommended") is not None:
        price = latest["price"]
        away = f" ({(price - stop['recommended']) / price * 100:.1f}% below)" if price else ""
        print(f"\n  Stop: {_fmt(stop['recommended'])}{away} via {stop.get('method', '?')}")

    plan = detail.get("entry_plan") or {}
    if plan.get("entries"):
        state = "EXTENDED — past the entry zone" if plan.get("extended") else "in the entry zone"
        print(f"  Entry: {state}", end="")
        if plan.get("extended_pct") is not None:
            print(f" ({plan['extended_pct']:+.1f}% vs breakout)")
        else:
            print()
        for e in plan["entries"]:
            print(f"    {e.get('size_pct', '?')}% at {_fmt(e.get('price'))} — {e.get('note', '')}")

    base = detail.get("base") or {}
    if base.get("breakout_age_weeks") is not None:
        # base_is_tight only means "under the 40% cutoff", which is a junk
        # filter rather than a quality mark. Calling a 27% base "tight" in
        # the output reads as an endorsement the flag doesn't carry, so I
        # print the number and only annotate the failing case.
        note = "" if base.get("base_is_tight") else "  (wider than the 40% cutoff)"
        print(f"  Base: {_fmt(base.get('base_range_pct'), 1)}% range, "
              f"broke out {base['breakout_age_weeks']} weeks ago{note}")

    if len(rows) > 1:
        print(f"\n  History ({len(rows)} scans)")
        print("  " + "-" * 60)
        print(f"  {'date':<12}{'stage':>6}{'met':>6}{'price':>10}  verdict")
        for r in rows:
            s = r["detail"].get("scoring", {})
            mark = "actionable" if s.get("actionable") else ""
            print(f"  {r['run_date']:<12}{str(r['stage'] or '?'):>6}"
                  f"{str(r['conditions_met']):>6}{_fmt(r['price']):>10}  {mark}")
    print()
    return 0


def show_diff(from_date=None, to_date=None):
    """What changed between two scans, stage transitions first.

    This is the report I actually wanted. Weinstein's whole method is
    about catching a stock as it crosses from Stage 1 into Stage 2, and a
    single scan can't show a crossing — only two can. Note the asymmetry
    in what a disappearance means: a name absent from the later scan
    might have deteriorated, or might simply have dropped below the
    liquidity floor or failed the prefilter, so I report those separately
    from real stage changes rather than implying they're signals.
    """
    dates = db.get_run_dates()
    if len(dates) < 2:
        print(f"Need two scans to diff; found {len(dates)}.")
        return 1

    to_date = to_date or dates[0]
    from_date = from_date or next((d for d in dates if d < to_date), None)
    if from_date is None:
        print(f"No scan earlier than {to_date}. Have: {', '.join(dates)}")
        return 1

    before = {r["ticker"]: _load(r) for r in db.get_results_for_run(from_date)}
    after = {r["ticker"]: _load(r) for r in db.get_results_for_run(to_date)}
    if not before or not after:
        print(f"One of those dates has no rows ({from_date}: {len(before)}, "
              f"{to_date}: {len(after)}).")
        return 1

    print(f"\n{from_date}  ->  {to_date}")
    print("=" * 62)
    print(f"  {len(before)} names then, {len(after)} now")

    common = sorted(set(before) & set(after))
    stage_moves, newly_actionable, lost_actionable = [], [], []
    for t in common:
        b, a = before[t], after[t]
        if b["stage"] != a["stage"] and b["stage"] and a["stage"]:
            stage_moves.append((t, b["stage"], a["stage"], a))
        was = (b["detail"].get("scoring") or {}).get("actionable")
        now = (a["detail"].get("scoring") or {}).get("actionable")
        if now and not was:
            newly_actionable.append((t, a))
        elif was and not now:
            lost_actionable.append((t, a, (a["detail"].get("scoring") or {}).get("reason", "")))

    # Stage 1 -> 2 is the crossing the method exists to catch, so it leads
    # regardless of how the rest of the checklist scored.
    def _rank(item):
        _, old, new, _ = item
        return (0 if (old, new) == (1, 2) else 1, -new)

    print(f"\n  Stage changes ({len(stage_moves)})")
    print("  " + "-" * 60)
    if not stage_moves:
        print("  none")
    for t, old, new, row in sorted(stage_moves, key=_rank):
        headline = "  <-- the crossing" if (old, new) == (1, 2) else ""
        print(f"  {t:<8} Stage {old} -> {new}   {_fmt(row['price']):>9}  "
              f"{row['conditions_met']}/9{headline}")

    print(f"\n  Newly actionable ({len(newly_actionable)})")
    print("  " + "-" * 60)
    if not newly_actionable:
        print("  none")
    for t, row in newly_actionable:
        print(f"  {t:<8} Stage {row['stage'] or '?'}  {_fmt(row['price']):>9}  "
              f"{row['sector'] or 'unknown'}")

    print(f"\n  No longer actionable ({len(lost_actionable)})")
    print("  " + "-" * 60)
    if not lost_actionable:
        print("  none")
    for t, row, reason in lost_actionable:
        print(f"  {t:<8} {reason}")

    gone, arrived = sorted(set(before) - set(after)), sorted(set(after) - set(before))
    print(f"\n  Entered the scan: {len(arrived)}   Dropped out: {len(gone)}")
    if arrived:
        print(f"    in:  {', '.join(arrived[:15])}{' ...' if len(arrived) > 15 else ''}")
    if gone:
        print(f"    out: {', '.join(gone[:15])}{' ...' if len(gone) > 15 else ''}")
    print("\n  A name dropping out may have deteriorated, or may just have")
    print("  failed the prefilter or the liquidity floor. Not a sell signal.")
    print()
    return 0


def show_actionable(limit=None, min_met=None, include_extended=True):
    """The current shortlist, grouped by sector.

    Grouped rather than ranked flat because the book's sequence is
    top-down: the sector call comes before the stock call. Seeing six
    names from one sector together is information — it says the sector is
    moving — whereas the same six spread down a ranked list read as six
    unrelated ideas.
    """
    rows = [_load(r) for r in db.get_latest_results()]
    if not rows:
        print("No scan results stored yet. Run the screener first.")
        return 1

    run_date = rows[0]["run_date"]
    if min_met is None:
        keep = [r for r in rows if (r["detail"].get("scoring") or {}).get("actionable")]
        label = "actionable"
    else:
        keep = [r for r in rows if (r["conditions_met"] or 0) >= min_met]
        label = f"scoring {min_met}+ of 9"

    if not include_extended:
        keep = [r for r in keep if not (r["detail"].get("entry_plan") or {}).get("extended")]

    print(f"\nShortlist — {run_date}")
    print("=" * 72)
    print(f"  {len(keep)} of {len(rows)} scanned names {label}"
          f"{'' if include_extended else ', excluding extended'}")

    if not keep:
        print("\n  Nothing qualifies. That is a real answer, not a failure —")
        print("  the checklist is meant to be restrictive.\n")
        return 0

    by_sector = {}
    for r in keep:
        by_sector.setdefault(r["sector"] or "unknown", []).append(r)

    def _sector_rank(item):
        _, members = item
        pcts = [(m["detail"].get("sector_strength") or {}).get("sector_strength_percentile")
                for m in members]
        pcts = [p for p in pcts if p is not None]
        return (-(max(pcts) if pcts else -1), -len(members))

    shown = 0
    for sector, members in sorted(by_sector.items(), key=_sector_rank):
        pcts = [(m["detail"].get("sector_strength") or {}).get("sector_strength_percentile")
                for m in members]
        pcts = [p for p in pcts if p is not None]
        strength = f"  [{max(pcts):.0f}th pct]" if pcts else ""
        print(f"\n  {sector}{strength}  — {len(members)} name(s)")
        print("  " + "-" * 70)
        print(f"  {'':2}{'ticker':<8}{'stage':>6}{'met':>5}{'price':>10}{'stop':>10}"
              f"{'age':>6}  entry")
        members.sort(key=lambda r: -(r["conditions_met"] or 0))
        for r in members:
            if limit is not None and shown >= limit:
                print(f"\n  ... stopping at {limit}. Raise or drop --limit for the rest.\n")
                return 0
            stop = (r["detail"].get("stop_loss") or {}).get("recommended")
            age = (r["detail"].get("base") or {}).get("breakout_age_weeks")
            plan = r["detail"].get("entry_plan") or {}
            entry = "extended" if plan.get("extended") else "in zone"
            print(f"  {'':2}{r['ticker']:<8}{str(r['stage'] or '?'):>6}"
                  f"{str(r['conditions_met']):>5}{_fmt(r['price']):>10}"
                  f"{_fmt(stop):>10}{(str(age) + 'w') if age is not None else '-':>6}  {entry}")
            shown += 1

    print("\n  Every name here still needs a chart. The checklist finds")
    print("  candidates; it does not confirm them.\n")
    return 0


def _parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="report",
        description="Read back stored screener results. Database only — no API calls.",
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--ticker", metavar="SYM", help="full breakdown and history for one name")
    g.add_argument("--diff", action="store_true", help="what changed between two scans")
    g.add_argument("--actionable", action="store_true", help="the current shortlist by sector")
    g.add_argument("--runs", action="store_true", help="list stored scan dates")

    p.add_argument("--json", action="store_true", help="with --ticker, dump the raw detail")
    p.add_argument("--from", dest="from_date", metavar="DATE", help="with --diff, earlier scan")
    p.add_argument("--to", dest="to_date", metavar="DATE", help="with --diff, later scan")
    p.add_argument("--limit", type=int, help="with --actionable, cap the names shown")
    p.add_argument("--min-met", type=int, metavar="N",
                   help="with --actionable, show names meeting N+ conditions "
                        "rather than only those passing the full bar")
    p.add_argument("--exclude-extended", action="store_true",
                   help="with --actionable, drop names already past the entry zone")
    return p.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    if args.runs:
        dates = db.get_run_dates()
        if not dates:
            print("No scans stored yet.")
            return 1
        print(f"\n{len(dates)} scan(s), newest first")
        for d in dates:
            n = len(db.get_results_for_run(d))
            print(f"  {d}   {n:>5} names")
        print()
        return 0
    if args.ticker:
        return show_ticker(args.ticker, as_json=args.json)
    if args.diff:
        return show_diff(args.from_date, args.to_date)
    return show_actionable(limit=args.limit, min_met=args.min_met,
                           include_extended=not args.exclude_extended)


if __name__ == "__main__":
    sys.exit(main())
