"""Evaluates a ticker against Weinstein's 9-condition buying checklist
(see docs/methodology.md). Each condition resolves to True, False, or
None — I use None whenever the data genuinely doesn't support a confident
call rather than forcing a guess either way.

Conditions 2 and 6 are mechanical thresholds. Condition 3 is phase-aware
rather than a single fixed threshold — see _evaluate_volume_confirmation.
Condition 5 depends on whatever sector match data_fetch.get_sector_data()
could find. Conditions 1 and 7 lean on a stage/breakout read that can
itself come back ambiguous.
Conditions 8 and 9 are the two the book describes qualitatively rather
than with hard numbers — I flag both for manual review in the output,
and for 9 specifically I return None (not a guessed True/False) whenever
the reward-to-risk margin is thin. Condition 7 also gets flagged for
manual review, but for a different reason: it leans on
trend_support_resistance.py, whose level/trend-line selection still
carries an unverified tie-break rule and an unconfirmed pivot-window
default for weekly data — see that module's docstring.

A "not actionable" result from evaluate_conditions() means the long
checklist isn't satisfied — it does NOT mean there's nothing here.
Depending on stage and RS direction, the same ticker may be a short
candidate under a separate set of rules I haven't built yet. Short
selling isn't just these 9 conditions inverted: several of them are
asymmetric between long and short per the book — volume confirmation
is required for a valid long breakout but explicitly not required for
a valid short breakdown, for one. Until that separate checklist exists,
run_screener.py's summary flags a cheap "short?" heuristic pointer
(low long score, Stage 3/4, declining or negative RS) so this
information isn't silently thrown away in the meantime — that flag is
not a real evaluation, just a placeholder worth a manual look.
"""
import math

from . import historical_levels, mansfield_rs, moving_averages, sector_strength, trend_support_resistance

# Scoring model. The old rule — "at least 8 of 9 True" — quietly treated
# None exactly like False, which contradicts the whole reason this file
# returns None in the first place. Measured against real tickers, that
# meant several could never be flagged actionable no matter how good the
# setup was, purely because two conditions came back "unknown": a stock
# with 7 True / 0 False / 2 None was scored the same as one with 7 True
# / 2 False. Those are very different situations.
#
# So unknowns are now excluded from the ratio instead of counted as
# failures, with two guards so that excluding them can't manufacture a
# signal out of thin air:
#
#   1. An evidence floor — enough conditions have to actually resolve
#      before any verdict is meaningful.
#   2. Hard gates — a False on any structurally non-negotiable condition
#      disqualifies outright, regardless of how good the ratio looks.
#      These three are the ones the book treats as prerequisites rather
#      than as weighable evidence: the stage setup itself, price above
#      the 30-week MA, and not buying into a confirmed Stage 4 market.
#
# ACTIONABLE_SCORE is set so the full-information case is unchanged from
# the old rule: with all 9 resolved, ceil(0.8 * 9) = 8, exactly the
# previous threshold. Fewer resolved conditions require proportionally
# fewer passes, but never a smaller share of them.
ACTIONABLE_SCORE = 0.80
# Tolerate at most two unknowns. Three is too thin to act on, and not
# for a generic sample-size reason: the conditions that most often come
# back unknown are resistance_breakout, pullback_quality and
# volume_confirmation — precisely the entry-*trigger* ones. Three
# unknowns therefore tends to mean "I can see this stock is in a good
# stage and trend, but I have no evidence about whether it's actually
# breaking out right now," which is exactly when a screener should not
# be saying "actionable."
MIN_RESOLVED_CONDITIONS = 7
NON_NEGOTIABLE_CONDITIONS = ("stage_setup", "price_above_ma", "market_stage")

# Kept for reference: the legacy absolute threshold this replaced.
ACTIONABLE_THRESHOLD = 8

# How far back (in weeks) I look for the base that preceded a breakout,
# and how many recent weeks count as "still close to the breakout."
BASE_WINDOW = 26
RECENT_WINDOW = 8
PRE_BASE_LOOKBACK = 52

MA_PERIOD = 30
MA_SLOPE_LOOKBACK = 5
MA_SLOPE_THRESHOLD_PCT = 0.5

VOLUME_CONFIRM_RATIO = 2.0
# My own reading of "contraction" for the pullback half of condition 3 —
# the book doesn't give a number, so below-average (< 1.0x the trailing
# 4-week average) is my baseline for "volume is drying up," same spirit
# as the other undefined thresholds in this file.
VOLUME_CONTRACTION_RATIO = 1.0

# My own operational cutoffs for reading the swing-rule reward/risk ratio —
# the book gives the swing rule itself but not a numeric pass/fail line, so
# I use these only to decide when a margin is thin enough to flag rather
# than as an official rule.
RISK_REWARD_CLEAR_PASS = 1.5
RISK_REWARD_CLEAR_FAIL = 1.0

# Fallback threshold for condition 5 when I only have the sector-overview
# change_ratio (data_fetch.get_sector_data) rather than the daily
# sector-ETF-vs-SPY closes sector_strength.py actually wants.
SECTOR_STRENGTH_THRESHOLD_PCT = 1.0
# Percentile thresholds once daily closes are available.
SECTOR_STRENGTH_PERCENTILE_PASS = 60
SECTOR_STRENGTH_PERCENTILE_FAIL = 40

# Pivot/trend-line read for condition 7 — these match the verified
# reference defaults exactly. See trend_support_resistance.py's module
# docstring for what's verified versus still approximate, including the
# weekly-vs-daily pivot-window concern for TSR_PIVOT_LENGTH. The reference
# calculation declares separate "points to check"/"max violation"/"except
# bars" inputs for trend lines vs. support/resistance levels, but they
# default to the same values and I don't have evidence they're ever set
# differently, so I share one set of constants across both here.
TSR_PIVOT_LENGTH = 20
TSR_POINTS_TO_CHECK = 3
# Relaxed from the verified default of 0: on real weekly data, a strict
# zero-violation requirement left almost every level unresolved even
# with plenty of pivot candidates. Checked live — 2 was where genuinely
# useful levels started resolving for real tickers without just letting
# anything through. This is my own tuning, not part of the verified
# reference default.
TSR_MAX_VIOLATION = 2
TSR_EXCEPT_BARS = 3


def _volume_ratio_at(volumes, idx):
    """Ratio of the volume at idx to the average of the 4 weeks before it."""
    if idx < 4:
        return None
    window = volumes[idx - 4:idx]
    avg = sum(window) / len(window)
    if avg == 0:
        return None
    return volumes[idx] / avg


def _classify_stage(closes, ma_series):
    """A heuristic read of Weinstein's 4 stages from price vs. its 30-week MA.

    The book's stage calls are ultimately a visual judgment, so I only
    resolve a stage when the MA slope and price position agree clearly;
    otherwise this returns None rather than forcing one of the 4 labels.

    ma_series (the SMA, matching the book's own 30-week-MA definition)
    stays the actual line price gets compared against for every branch
    below — that doesn't change. What changed is how I read trend
    *direction*: a plain 30-week SMA is slow enough that its slope keeps
    pointing the old direction for a while after price has already
    crossed it, which meant an early top or bottom (price just broke the
    "wrong" way, MA hasn't caught up yet) was falling through every
    branch as an unresolved None. I use a WMA's slope instead, which
    reacts faster, and explicitly handle the two lopsided cases (MA
    still trending one way, price already the other) as early Stage 3 or
    Stage 1 rather than requiring the MA to go fully flat first.
    """
    latest = len(closes) - 1
    if latest < MA_SLOPE_LOOKBACK or ma_series[latest] is None or ma_series[latest - MA_SLOPE_LOOKBACK] is None:
        return None

    wma_series = moving_averages.wma(closes, MA_PERIOD)
    if wma_series[latest] is None or wma_series[latest - MA_SLOPE_LOOKBACK] is None:
        return None

    ma_now = ma_series[latest]
    price = closes[latest]
    wma_now = wma_series[latest]
    wma_prior = wma_series[latest - MA_SLOPE_LOOKBACK]
    slope_pct = (wma_now - wma_prior) / wma_prior * 100 if wma_prior else 0.0

    rising = slope_pct > MA_SLOPE_THRESHOLD_PCT
    falling = slope_pct < -MA_SLOPE_THRESHOLD_PCT

    if rising and price > ma_now:
        return 2
    if falling and price < ma_now:
        return 4
    if rising and price < ma_now:
        return 3  # MA still trending up, price already broke below it — early top
    if falling and price > ma_now:
        return 1  # MA still trending down, price already broke above it — early base breakout

    # Only genuinely flat-MA cases reach here — same stricter check as
    # before, since a flat MA alone isn't enough to call a stage without
    # a real prior move behind it.
    reference_idx = max(0, latest - 26)
    reference = closes[reference_idx]
    change_pct = (price - reference) / reference * 100 if reference else 0.0
    if change_pct <= -10:
        return 1
    if change_pct >= 10:
        return 3
    return None


def _find_base_and_breakout(closes, highs):
    """Finds the resistance level of the most recent base and, if price has
    broken above it within the recent window, the index of that breakout bar.

    This feeds conditions 1, 8, and 9, which all need a specific breakout
    bar to reason about (was there one, how long ago, what was the base's
    low). Condition 7 uses a separate pivot-based read from
    trend_support_resistance.py instead — see _evaluate_resistance_breakout.
    """
    n = len(closes)
    if n < BASE_WINDOW + RECENT_WINDOW + 4:
        return None, None, None

    base_start = n - BASE_WINDOW - RECENT_WINDOW
    base_end = n - RECENT_WINDOW
    resistance_level = max(highs[base_start:base_end])

    breakout_idx = None
    for i in range(base_end, n):
        if closes[i] > resistance_level:
            breakout_idx = i
            break

    return resistance_level, breakout_idx, base_start


def _evaluate_pullback(closes, volumes, resistance_level, breakout_idx, latest_idx):
    """Condition 8. Returns None whenever a pullback read doesn't apply —
    either there's no breakout yet, or the breakout happened this same week,
    or price is still sitting at its post-breakout high with nothing to
    pull back from.
    """
    if resistance_level is None or breakout_idx is None:
        return None
    if breakout_idx == latest_idx:
        return None

    post_breakout_closes = closes[breakout_idx:latest_idx]
    if not post_breakout_closes:
        return None
    post_breakout_high = max(post_breakout_closes)
    if closes[latest_idx] >= post_breakout_high:
        return None

    pullback_closes = closes[breakout_idx + 1:latest_idx + 1]
    pullback_volumes = volumes[breakout_idx + 1:latest_idx + 1]
    if not pullback_closes:
        return None

    breakout_week_volume = volumes[breakout_idx]
    pullback_volume_avg = sum(pullback_volumes) / len(pullback_volumes)
    holding_above_breakout = min(pullback_closes) > resistance_level
    volume_contracting = pullback_volume_avg < breakout_week_volume

    return bool(holding_above_breakout and volume_contracting)


def _evaluate_volume_confirmation(volumes, breakout_idx, latest_idx, pullback_quality):
    """Condition 3: "Volume confirmation on breakout; contraction on
    pullbacks" (docs/methodology.md) — two different, opposite-direction
    reads depending on which moment price is in, not one fixed threshold.

    A flat "always need >= 2x volume" check contradicts condition 8's own
    logic, which correctly treats lower volume during a pullback as a
    good sign — so this needs to know the phase pullback_quality already
    determined (None means "not currently in a pullback," per
    _evaluate_pullback's own contract) rather than reading volume in
    isolation.

    Returns (result, volume_ratio, phase) where phase is one of
    "breakout", "pullback", or "not_applicable" — stored for transparency
    even though it isn't itself pass/fail.
    """
    volume_ratio = _volume_ratio_at(volumes, latest_idx)
    if volume_ratio is None:
        return None, None, "not_applicable"

    at_fresh_breakout = breakout_idx is not None and breakout_idx == latest_idx
    in_pullback = pullback_quality is not None

    if at_fresh_breakout:
        return volume_ratio >= VOLUME_CONFIRM_RATIO, volume_ratio, "breakout"
    if in_pullback:
        return volume_ratio < VOLUME_CONTRACTION_RATIO, volume_ratio, "pullback"

    # Neither a fresh breakout nor an identified pullback — the book's
    # volume rule is specifically about those two moments, so there's
    # nothing meaningful to say about a week that's neither.
    return None, volume_ratio, "not_applicable"


def _evaluate_risk_reward(highs, lows, closes, resistance_level, breakout_idx, base_start):
    """Condition 9, Weinstein's swing rule: project the point-distance of the
    decline into the base up from the breakout price, and compare that
    reward against the risk back down to the base's low.
    """
    if resistance_level is None or breakout_idx is None or base_start is None:
        return None, None, None

    pre_base_end = base_start
    pre_base_start = max(0, pre_base_end - PRE_BASE_LOOKBACK)
    if pre_base_start >= pre_base_end:
        return None, None, None

    peak_price = max(highs[pre_base_start:pre_base_end])
    base_end = base_start + BASE_WINDOW
    swing_low = min(lows[base_start:base_end])
    decline_distance = peak_price - swing_low

    entry = closes[breakout_idx]
    swing_target = entry + decline_distance
    swing_stop = swing_low

    reward = swing_target - entry
    risk = entry - swing_stop
    if risk <= 0:
        return swing_target, swing_stop, None

    ratio = reward / risk
    if ratio >= RISK_REWARD_CLEAR_PASS:
        result = True
    elif ratio <= RISK_REWARD_CLEAR_FAIL:
        result = False
    else:
        result = None  # thin margin — flagged for manual review below

    return swing_target, swing_stop, result


def _evaluate_resistance_breakout(bars, volumes, latest_idx):
    """Condition 7, using the pivot-based resistance level from
    trend_support_resistance.py instead of the base-window read the other
    conditions share. Returns (result, detail) where detail carries the
    pivot/level context worth checking against the real chart.
    """
    tsr_result = trend_support_resistance.analyze(
        bars, pivot_length=TSR_PIVOT_LENGTH, points_to_check=TSR_POINTS_TO_CHECK,
        max_violation=TSR_MAX_VIOLATION, except_bars=TSR_EXCEPT_BARS,
    )
    tsr_resistance = tsr_result["resistance_level"]
    resistance_status = tsr_result["resistance_status"]

    if resistance_status == "already_cleared":
        # Every candidate pivot was violated, but price broke through on
        # a close and has stayed above it ever since — there's no
        # overhead resistance left to test against a specific week's
        # volume, so checking this week's volume_ratio doesn't answer a
        # meaningful question here. Already cleared and held is itself
        # the pass.
        result = True
    elif tsr_resistance is None:
        result = None
    else:
        volume_ratio_latest = _volume_ratio_at(volumes, latest_idx)
        price_broke_out = bars[latest_idx]["close"] > tsr_resistance
        if not price_broke_out:
            result = False
        elif volume_ratio_latest is None:
            result = None
        else:
            result = volume_ratio_latest >= VOLUME_CONFIRM_RATIO

    detail = {
        "resistance_level": tsr_resistance,
        "resistance_status": resistance_status,
        "resistance_violations": tsr_result["resistance_violations"],
        "support_level": tsr_result["support_level"],
        "support_violations": tsr_result["support_violations"],
        "trend_line": tsr_result["trend_line"],
    }
    return result, detail


def evaluate_conditions(ticker, bars, index_bars, sector_data):
    """Evaluates all 9 checklist conditions for one ticker.

    :param bars: weekly OHLCV dicts for the ticker, oldest first.
    :param index_bars: weekly OHLCV dicts for the comparison index, oldest first.
    :param sector_data: dict from data_fetch.get_sector_data(ticker), or None.
        If it also carries "sector_etf_closes" and "spy_daily_closes" (daily
        closes, oldest first), condition 5 uses the percentile read from
        sector_strength.py; otherwise it falls back to the sector-overview
        change_ratio the way it always has, since data_fetch.py doesn't
        fetch daily sector-ETF/SPY closes yet.
    :return: dict with per-condition results, a conditions_met count, and
        the derived fields (stage, price, MA, RS, swing levels, etc.) that
        run_screener.py writes into screener_results.
    """
    closes = [b["close"] for b in bars]
    highs = [b["high"] for b in bars]
    lows = [b["low"] for b in bars]
    volumes = [b["volume"] for b in bars]
    idx_closes = [b["close"] for b in index_bars]

    latest_idx = len(closes) - 1
    ma_series = moving_averages.sma(closes, MA_PERIOD)
    ma_now = ma_series[latest_idx]
    ma_prior = ma_series[latest_idx - MA_SLOPE_LOOKBACK] if latest_idx >= MA_SLOPE_LOOKBACK else None

    stage = _classify_stage(closes, ma_series)
    resistance_level, breakout_idx, base_start = _find_base_and_breakout(closes, highs)

    # Rolling high/low context (5D/2W/52W/all-time) — not one of the 9
    # conditions itself, just supporting context. new_52w_high is the one
    # derived signal worth calling out directly: clearing the 52-week high
    # is a classic strength tell on top of whatever the base-window
    # resistance level above says.
    price_levels = historical_levels.get_historical_high_low(bars)
    week_52_high = price_levels["52W"]["high"]
    new_52w_high = None if week_52_high is None else closes[latest_idx] >= week_52_high

    # Condition 1: proper stage setup.
    if stage is None:
        stage_setup = None
    elif stage == 2:
        stage_setup = True
    elif stage == 1 and breakout_idx is not None:
        stage_setup = True
    elif stage in (3, 4):
        stage_setup = False
    else:
        stage_setup = None

    # Condition 2: price above its 30-week MA.
    price_above_ma = None if ma_now is None else closes[latest_idx] > ma_now

    # MA trend, stored alongside condition 2 but not itself one of the 9.
    ma_rising = None if ma_now is None or ma_prior is None else ma_now > ma_prior

    # Condition 8 gets computed here rather than further down, since
    # condition 3 needs its pullback read to know which of the book's two
    # volume rules applies to this week.
    pullback_quality = _evaluate_pullback(closes, volumes, resistance_level, breakout_idx, latest_idx)

    # Condition 3: volume confirmation on breakout, contraction on pullbacks.
    volume_confirmed, volume_ratio, volume_phase = _evaluate_volume_confirmation(
        volumes, breakout_idx, latest_idx, pullback_quality
    )

    # Condition 4: Mansfield RS improving or positive.
    mrs_series, rs_ma_rising = mansfield_rs.compute_mansfield_rs(closes, idx_closes)
    mrs_now = mrs_series[latest_idx]
    mrs_prior = mrs_series[latest_idx - MA_SLOPE_LOOKBACK] if latest_idx >= MA_SLOPE_LOOKBACK else None
    rs_improving = None if mrs_now is None or mrs_prior is None else mrs_now > mrs_prior
    if mrs_now is None:
        rs_condition = None
    elif mrs_now > 0:
        rs_condition = True
    elif rs_improving is None:
        rs_condition = None
    else:
        rs_condition = rs_improving

    # Condition 5: sector in a strong phase.
    sector_etf_closes = sector_data.get("sector_etf_closes") if sector_data else None
    spy_daily_closes = sector_data.get("spy_daily_closes") if sector_data else None
    sector_strength_percentile = None
    if sector_etf_closes and spy_daily_closes:
        sector_strength_percentile = sector_strength.get_sector_strength_percentile(
            sector_etf_closes, spy_daily_closes
        )

    if sector_strength_percentile is not None:
        if sector_strength_percentile >= SECTOR_STRENGTH_PERCENTILE_PASS:
            sector_strength_result = True
        elif sector_strength_percentile <= SECTOR_STRENGTH_PERCENTILE_FAIL:
            sector_strength_result = False
        else:
            sector_strength_result = None
    else:
        sector_strength_pct = sector_data.get("sector_strength_pct") if sector_data else None
        if sector_strength_pct is None:
            sector_strength_result = None
        elif sector_strength_pct > SECTOR_STRENGTH_THRESHOLD_PCT:
            sector_strength_result = True
        elif sector_strength_pct < -SECTOR_STRENGTH_THRESHOLD_PCT:
            sector_strength_result = False
        else:
            sector_strength_result = None

    # Condition 6: broader market not in a confirmed Stage 4.
    idx_ma_series = moving_averages.sma(idx_closes, MA_PERIOD)
    market_stage = _classify_stage(idx_closes, idx_ma_series)
    market_stage_ok = None if market_stage is None else market_stage != 4

    # Condition 7: resistance breakout, pivot-based read (see caveat on
    # trend_support_resistance.py — this is the lowest-confidence condition).
    resistance_breakout, tsr_detail = _evaluate_resistance_breakout(bars, volumes, latest_idx)

    # Condition 9: risk/reward via the swing rule.
    swing_target, swing_stop, risk_reward = _evaluate_risk_reward(
        highs, lows, closes, resistance_level, breakout_idx, base_start
    )

    conditions = {
        "stage_setup": stage_setup,
        "price_above_ma": price_above_ma,
        "volume_confirmation": volume_confirmed,
        "rs_improving": rs_condition,
        "sector_strength": sector_strength_result,
        "market_stage": market_stage_ok,
        "resistance_breakout": resistance_breakout,
        "pullback_quality": pullback_quality,
        "risk_reward": risk_reward,
    }
    conditions_met = sum(1 for v in conditions.values() if v is True)
    scoring = score_conditions(conditions)

    conditions_detail = {}
    for name, value in conditions.items():
        entry = {"result": value}
        if name in ("pullback_quality", "risk_reward"):
            entry["manual_review"] = True
        if name == "volume_confirmation":
            entry["volume_ratio"] = volume_ratio
            entry["phase"] = volume_phase
        if name == "rs_improving":
            entry["rs_ma_rising"] = rs_ma_rising
        if name == "sector_strength":
            entry["sector_strength_percentile"] = sector_strength_percentile
        if name == "resistance_breakout":
            entry["manual_review"] = True
            entry["low_confidence"] = True
            entry["low_confidence_reason"] = (
                "pivot/trend-line level selection uses an unverified tie-break when "
                "multiple candidates are valid, and the pivot window hasn't been "
                "checked against weekly-bar behavior"
            )
            entry.update(tsr_detail)
        conditions_detail[name] = entry

    # Not one of the 9 conditions, so it isn't in `conditions` above — just
    # supporting context, stored the same way the per-condition detail is.
    conditions_detail["historical_levels"] = {
        "levels": price_levels,
        "new_52w_high": new_52w_high,
    }
    # Persisted alongside the per-condition detail rather than as its own
    # DB column, same pattern as historical_levels — no schema change.
    conditions_detail["scoring"] = scoring

    return {
        "conditions": conditions,
        "conditions_met": conditions_met,
        "scoring": scoring,
        "actionable": scoring["actionable"],
        "conditions_detail": conditions_detail,
        "stage": stage,
        "price": closes[latest_idx],
        "ma_30w": ma_now,
        "price_above_ma": price_above_ma,
        "ma_rising": ma_rising,
        "mansfield_rs": mrs_now,
        "rs_improving": rs_improving,
        "rs_ma_rising": rs_ma_rising,
        "volume_ratio": volume_ratio,
        "volume_confirmed": volume_confirmed,
        "market_stage_ok": market_stage_ok,
        "resistance_level": resistance_level,
        "breakout_confirmed": resistance_breakout,
        "swing_target": swing_target,
        "swing_stop": swing_stop,
        "historical_levels": price_levels,
        "new_52w_high": new_52w_high,
        "breakout_idx": breakout_idx,
    }


def score_conditions(conditions):
    """Turns the 9 raw True/False/None results into a verdict that keeps
    "failed" and "unknown" distinct. See the scoring constants above for
    why. Returns the full picture rather than one number, so output can
    show *why* something did or didn't qualify.
    """
    met = sum(1 for v in conditions.values() if v is True)
    failed = sum(1 for v in conditions.values() if v is False)
    unknown = sum(1 for v in conditions.values() if v is None)
    resolved = met + failed

    blocking = [name for name in NON_NEGOTIABLE_CONDITIONS if conditions.get(name) is False]
    required = math.ceil(ACTIONABLE_SCORE * resolved) if resolved else None

    if blocking:
        actionable = False
        reason = "blocked by non-negotiable condition(s): " + ", ".join(blocking)
    elif resolved < MIN_RESOLVED_CONDITIONS:
        actionable = False
        reason = (
            f"only {resolved} of {len(conditions)} conditions resolved — "
            f"need {MIN_RESOLVED_CONDITIONS} before a verdict means anything"
        )
    elif met >= required:
        actionable = True
        reason = f"{met} of {resolved} resolved conditions met"
    else:
        actionable = False
        reason = f"{met} of {resolved} resolved conditions met, need {required}"

    return {
        "actionable": actionable,
        "reason": reason,
        "met": met,
        "failed": failed,
        "unknown": unknown,
        "resolved": resolved,
        "required": required,
        "score": (met / resolved) if resolved else None,
        "blocking": blocking,
    }


def is_actionable(value):
    """Accepts either the dict returned by evaluate_conditions() or a
    bare conditions dict, and reports whether it qualifies.

    This deliberately no longer accepts a bare conditions_met integer —
    that count alone can't distinguish a failed condition from an
    unresolved one, which is exactly the ambiguity this scoring model
    exists to remove.
    """
    if "scoring" in value:
        return value["scoring"]["actionable"]
    if "conditions" in value:
        return score_conditions(value["conditions"])["actionable"]
    return score_conditions(value)["actionable"]
