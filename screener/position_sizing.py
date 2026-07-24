"""Entry-plan sizing for tickers that already qualify as actionable on
the long checklist. Not a 10th checklist condition — it doesn't feed
conditions.py's conditions_met count, it's a separate output layered on
top of a result that's already actionable.
"""

VALID_STYLES = ("investor", "trader")


def get_entry_plan(breakout_price, style='investor'):
    """I return the entry level(s) and position size(s) for a qualifying
    ticker, given its breakout price.

    Note on the signature: I added breakout_price as a required first
    argument rather than the style-only get_entry_plan(style='investor')
    originally described — returning real price levels needs the
    breakout price, so a price-less signature couldn't actually produce
    them. style keeps the same default.

    :param style: 'trader' takes a full position at the breakout price.
        'investor' takes half at the breakout, with the second half
        meant to trigger on a pullback toward the breakout level — I
        don't try to auto-detect that fill here, just return the two
        levels/sizes so it can be acted on manually.
    """
    if style not in VALID_STYLES:
        raise ValueError(f"Unknown style: {style!r}. Expected one of {VALID_STYLES}.")

    if style == 'trader':
        return {
            "style": "trader",
            "entries": [
                {"price": breakout_price, "size_pct": 100, "note": "full position at breakout"},
            ],
        }

    return {
        "style": "investor",
        "entries": [
            {"price": breakout_price, "size_pct": 50, "note": "first half at breakout"},
            {
                "price": breakout_price,
                "size_pct": 50,
                "note": "second half on a pullback toward the breakout level — fill manually, not auto-detected",
            },
        ],
    }
