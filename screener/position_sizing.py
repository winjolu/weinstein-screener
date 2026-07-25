"""Entry-plan sizing for tickers that already qualify as actionable on
the long checklist. Not a 10th checklist condition — it doesn't feed
conditions.py's conditions_met count, it's a separate output layered on
top of a result that's already actionable.
"""

VALID_STYLES = ("investor", "trader")

# How far above the breakout level price can be before buying it is
# chasing rather than entering. My own operational cutoff: the book's
# worked examples put the initial stop roughly 5-6% under the entry, so
# once price is more than that above the breakout, a stop at the
# breakout level already risks more than those examples ever did.
EXTENDED_THRESHOLD_PCT = 5.0


def get_entry_plan(breakout_price, current_price=None, style='investor'):
    """I return the entry level(s) and position size(s) for a qualifying
    ticker, given its breakout price.

    Note on the signature: I added breakout_price as a required first
    argument rather than the style-only get_entry_plan(style='investor')
    originally described — returning real price levels needs the
    breakout price, so a price-less signature couldn't actually produce
    them. style keeps the same default.

    current_price is optional but worth passing: the breakout it's
    measured against may be many weeks old, and quoting that stale level
    as a live buy price is how one ends up chasing something that already
    ran. When it's supplied I report how far price has extended past the
    breakout and flag when that's too far to enter here.

    :param style: 'trader' takes a full position at the breakout price.
        'investor' takes half at the breakout, with the second half
        meant to trigger on a pullback toward the breakout level — I
        don't try to auto-detect that fill here, just return the two
        levels/sizes so it can be acted on manually.
    """
    if style not in VALID_STYLES:
        raise ValueError(f"Unknown style: {style!r}. Expected one of {VALID_STYLES}.")

    extended_pct = None
    extended = None
    if current_price is not None and breakout_price:
        extended_pct = (current_price - breakout_price) / breakout_price * 100
        extended = extended_pct > EXTENDED_THRESHOLD_PCT

    if style == 'trader':
        entries = [
            {"price": breakout_price, "size_pct": 100, "note": "full position at breakout"},
        ]
    else:
        entries = [
            {"price": breakout_price, "size_pct": 50, "note": "first half at breakout"},
            {
                "price": breakout_price,
                "size_pct": 50,
                "note": "second half on a pullback toward the breakout level — fill manually, not auto-detected",
            },
        ]

    return {
        "style": style,
        "entries": entries,
        "current_price": current_price,
        "extended_pct": extended_pct,
        "extended": extended,
        "note": (
            f"price is {extended_pct:.1f}% above the breakout — too extended to enter here, "
            "wait for a pullback toward that level"
            if extended else None
        ),
    }
