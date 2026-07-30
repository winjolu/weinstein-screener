"""The short-side checklist.

Deliberately a separate module rather than a flag on the long one,
because the rules are not symmetric and writing them as one function
invites treating them as if they were.

Where they genuinely mirror — stage, the moving average, relative
strength, sector, the market read — this reuses conditions.py's helpers
so the two sides can't drift apart. Where the book is explicit that they
differ, the difference is implemented and commented:

1. **Volume is not a requirement.** An upside breakout needs a
   significant volume increase to be trustworthy; a downside breakdown
   does not need one to be valid. The book is emphatic that a stock can
   move into Stage 4 on light volume and fall a long way afterwards, and
   warns specifically against being lulled by light volume. It does add
   that for short sales heavy volume is *preferable*, since urgent
   selling tends to fall faster — so volume is recorded as a bonus and
   never as a gate. This is the one asymmetry most likely to be got
   wrong by inverting the long checklist mechanically.

2. **The ideal entry is the pullback, not the breakdown.** The book's
   preferred short entry is a rally back to the breakdown level on light
   volume, where the old support has become resistance. The long side
   buys the breakout itself; the short side prefers to sell into the
   bounce.

3. **Never short on valuation.** A high multiple is not a reason. The
   book gives a worked example of a stock at 35 times earnings that
   doubled while the market fell. Only stage justifies a short, which is
   why there is no fundamental input here at all.

Risk is bounded exactly as it is on the long side. A short at 40 with a
buy-stop at 44 risks 10%, the same as a long at 40 with a sell-stop at
36. The "unlimited losses" framing does not survive a protective stop,
and the book says so directly.
"""
from . import conditions, mansfield_rs, moving_averages, trend_support_resistance

# Mirrors of the long-side scoring model. Kept as separate constants
# rather than imported so the two sides can be tuned independently —
# there is no reason to assume the same thresholds suit both.
ACTIONABLE_SCORE = 0.80
MIN_RESOLVED_CONDITIONS = 7
NON_NEGOTIABLE_CONDITIONS = ("stage_setup", "price_below_ma", "market_stage")

CONDITION_NAMES = (
    "stage_setup", "price_below_ma", "rs_deteriorating", "sector_weak",
    "market_stage", "support_breakdown", "rally_quality", "risk_reward",
)

# A rally back toward the broken level is the preferred entry. This is
# how close to that level counts as "back at it".
RALLY_TO_BREAKDOWN_TOLERANCE_PCT = 5.0

# Light volume on that rally is what makes it ideal — it says the bounce
# has no conviction behind it. Below this multiple of the trailing
# average counts as light.
LIGHT_RALLY_VOLUME_RATIO = 1.0

# Heaviness on the breakdown itself is a bonus, never a requirement.
HEAVY_BREAKDOWN_VOLUME_RATIO = 2.0

# Mirror of the long side's stop ceiling: the book's 15% limit applies to
# how far the protective stop sits from entry, whichever way round.
MAX_SENSIBLE_STOP_PCT = 15.0


def _empty_result():
    return {
        "conditions": {name: None for name in CONDITION_NAMES},
        "conditions_met": 0,
        "scoring": {"actionable": False, "reason": "no price history",
                    "met": 0, "failed": 0, "unknown": len(CONDITION_NAMES),
                    "resolved": 0, "required": None, "score": None,
                    "blocking": []},
        "stage": None, "price": None, "ma_30w": None,
        "support_level": None, "breakdown_idx": None,
        "buy_stop": None, "target": None,
        "breakdown_volume_ratio": None, "heavy_breakdown": None,
        "rallied_back": None,
    }


def _find_support_and_breakdown(bars, closes):
    """Mirror of the long side's base/breakout search: the support level
    the pivot read identifies, and the most recent close that crossed
    from above it to below.

    Uses trend_support_resistance.analyze() — the same machinery the long
    side leans on for resistance, so both sides inherit the same
    (documented, unverified) pivot-window behaviour rather than one of
    them quietly using something else.
    """
    read = trend_support_resistance.analyze(bars)
    support = read.get("support_level")
    if support is None:
        return None, None
    breakdown_idx = None
    for idx in range(1, len(closes)):
        if closes[idx - 1] >= support > closes[idx]:
            breakdown_idx = idx
    return support, breakdown_idx


def evaluate_short_conditions(ticker, bars, index_bars, sector_data=None):
    """The short checklist, same shape as the long one so callers and
    reports can treat them alike."""
    if not bars or not index_bars:
        return _empty_result()

    bars = bars[-conditions.EVALUATION_WEEKS:]
    index_bars = index_bars[-conditions.EVALUATION_WEEKS:]
    if len(bars) < conditions.MA_PERIOD + conditions.MA_SLOPE_LOOKBACK:
        return _empty_result()

    closes = [b["close"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    volumes = [b["volume"] for b in bars]
    latest = len(closes) - 1
    price = closes[latest]

    ma_series = moving_averages.sma(closes, conditions.MA_PERIOD)
    ma_now = ma_series[latest]
    stage = conditions._classify_stage(closes, ma_series)

    # 1. Stage 4, or Stage 3 already breaking down. Never short Stage 2 —
    #    the book's worked example of shorting on valuation into a Stage 2
    #    advance is the mistake it warns hardest against.
    if stage == 4:
        stage_setup = True
    elif stage == 2:
        stage_setup = False
    elif stage == 3:
        stage_setup = None
    else:
        stage_setup = None

    # 2. Price below the 30-week average. Mirror of the long condition.
    price_below_ma = None if ma_now is None else price < ma_now

    # 3. Relative strength deteriorating. A stock falling faster than the
    #    market is the short-side equivalent of leadership.
    #
    #    Paired by date, exactly as the long side does. Pairing these two
    #    series positionally is a bug this project has already had: it
    #    misaligns whenever a week is missing from either side, and it
    #    silently discarded 463 tickers before it was found.
    index_by_date = {b["time"][:10]: b["close"] for b in index_bars}
    paired = [
        (b["close"], index_by_date[b["time"][:10]])
        for b in bars
        if b["time"][:10] in index_by_date
    ]
    rs_deteriorating = None
    if paired:
        mrs_series, _ = mansfield_rs.compute_mansfield_rs(
            [c for c, _ in paired], [i for _, i in paired]
        )
        mrs_now = mrs_series[-1] if mrs_series else None
        mrs_prior = (
            mrs_series[-1 - conditions.MA_SLOPE_LOOKBACK]
            if len(mrs_series) > conditions.MA_SLOPE_LOOKBACK else None
        )
        if mrs_now is not None and mrs_prior is not None:
            # Negative and getting worse — the mirror of the long side's
            # "improving and positive".
            rs_deteriorating = mrs_now < 0 and mrs_now < mrs_prior

    # 4. Sector weak — mirror of sector strength, using the same
    #    percentile with the comparison reversed.
    sector_weak = None
    if sector_data:
        pct = None
        etf, spy = sector_data.get("sector_etf_closes"), sector_data.get("spy_daily_closes")
        if etf and spy:
            from . import sector_strength
            pct = sector_strength.get_sector_strength_percentile(etf, spy)
        if pct is not None:
            if pct <= conditions.SECTOR_STRENGTH_PERCENTILE_FAIL:
                sector_weak = True
            elif pct >= conditions.SECTOR_STRENGTH_PERCENTILE_PASS:
                sector_weak = False

    # 5. The market itself not in a confirmed advance. Mirror of "don't
    #    buy into a Stage 4 market" — don't short into a Stage 2 one.
    idx_closes = [b["close"] for b in index_bars]
    idx_ma = moving_averages.sma(idx_closes, conditions.MA_PERIOD)
    market_stage_raw = conditions._classify_stage(idx_closes, idx_ma)
    market_stage = None if market_stage_raw is None else market_stage_raw != 2

    # 6. Support broken.
    support_level, breakdown_idx = _find_support_and_breakdown(bars, closes)
    support_breakdown = None if support_level is None else breakdown_idx is not None

    # Volume on the breakdown: a bonus, never a gate. See the module
    # docstring — a breakdown on light volume is still valid, and the
    # book explicitly warns against reading light volume as safety.
    breakdown_volume_ratio = None
    heavy_breakdown = None
    if breakdown_idx is not None and breakdown_idx >= 4:
        prior = volumes[breakdown_idx - 4:breakdown_idx]
        if prior and sum(prior):
            breakdown_volume_ratio = volumes[breakdown_idx] / (sum(prior) / len(prior))
            heavy_breakdown = breakdown_volume_ratio >= HEAVY_BREAKDOWN_VOLUME_RATIO

    # 7. Rally quality — the preferred entry is a bounce back to the
    #    broken level on light volume, where old support is now the
    #    ceiling.
    rally_quality = None
    rallied_back = None
    if support_level and breakdown_idx is not None and latest > breakdown_idx:
        near = abs(price - support_level) / support_level * 100
        rallied_back = near <= RALLY_TO_BREAKDOWN_TOLERANCE_PCT and price < support_level
        if rallied_back:
            recent = volumes[max(0, latest - 4):latest]
            if recent and sum(recent):
                ratio = volumes[latest] / (sum(recent) / len(recent))
                rally_quality = ratio <= LIGHT_RALLY_VOLUME_RATIO
        else:
            # Already well below the level: not the ideal entry, but not
            # a disqualification either.
            rally_quality = None

    # 8. Risk/reward, with the protective stop *above* the entry.
    buy_stop = None
    target = None
    risk_reward = None
    if support_level and breakdown_idx is not None:
        recent_high = max(highs[breakdown_idx:latest + 1]) if latest >= breakdown_idx else None
        buy_stop = max(support_level, recent_high) if recent_high else support_level
        prior_low = min(lows[:breakdown_idx]) if breakdown_idx else None
        if prior_low and price:
            target = prior_low
            risk = buy_stop - price
            reward = price - target
            if risk > 0:
                stop_pct = risk / price * 100
                if stop_pct > MAX_SENSIBLE_STOP_PCT:
                    risk_reward = False
                elif reward / risk >= conditions.RISK_REWARD_CLEAR_PASS:
                    risk_reward = True
                elif reward / risk <= conditions.RISK_REWARD_CLEAR_FAIL:
                    risk_reward = False

    checks = {
        "stage_setup": stage_setup,
        "price_below_ma": price_below_ma,
        "rs_deteriorating": rs_deteriorating,
        "sector_weak": sector_weak,
        "market_stage": market_stage,
        "support_breakdown": support_breakdown,
        "rally_quality": rally_quality,
        "risk_reward": risk_reward,
    }

    return {
        "conditions": checks,
        "conditions_met": sum(1 for v in checks.values() if v is True),
        "scoring": score_short_conditions(checks),
        "stage": stage,
        "price": price,
        "ma_30w": ma_now,
        "support_level": support_level,
        "breakdown_idx": breakdown_idx,
        "buy_stop": buy_stop,
        "target": target,
        "breakdown_volume_ratio": breakdown_volume_ratio,
        "heavy_breakdown": heavy_breakdown,
        "rallied_back": rallied_back,
    }


def score_short_conditions(checks):
    """Same shape as the long side's scorer, and carrying the same known
    flaw: the ratio lets any single condition fail. Recorded rather than
    fixed, because testing that correction on the long side made results
    worse and there's no reason to assume differently here without
    measuring it."""
    import math

    met = sum(1 for v in checks.values() if v is True)
    failed = sum(1 for v in checks.values() if v is False)
    unknown = sum(1 for v in checks.values() if v is None)
    resolved = met + failed
    blocking = [n for n in NON_NEGOTIABLE_CONDITIONS if checks.get(n) is False]
    required = math.ceil(ACTIONABLE_SCORE * resolved) if resolved else None

    if blocking:
        actionable, reason = False, "blocked by: " + ", ".join(blocking)
    elif resolved < MIN_RESOLVED_CONDITIONS:
        actionable = False
        reason = f"only {resolved} of {len(checks)} conditions resolved"
    elif met >= required:
        actionable, reason = True, f"{met} of {resolved} resolved conditions met"
    else:
        actionable = False
        reason = f"{met} of {resolved} resolved conditions met, need {required}"

    return {"actionable": actionable, "reason": reason, "met": met,
            "failed": failed, "unknown": unknown, "resolved": resolved,
            "required": required,
            "score": (met / resolved) if resolved else None,
            "blocking": blocking}
