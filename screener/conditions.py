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

# How far above the 30-week average price may sit and still be buyable.
# None disables the gate, which is the current behaviour and the default
# until a value is chosen on evidence rather than by me picking one.
#
# This exists because "don't buy too late in an advance, far above the
# ideal entry point" is on the book's never-violate list and had no
# implementation. The only related check was an advisory flag measuring
# distance above the *breakout level*, which is a different quantity: a
# stock can break out of a tight base that is itself 174% above its own
# 30-week average, read as barely extended, and take a stop two thirds of
# the way down the chart. IMCC did exactly that and lost 63%.
#
# Gate rather than condition on purpose. Adding a tenth condition to a
# ratio would let it be outvoted by the other nine, which is the failure
# this is meant to close.
MAX_EXTENSION_ABOVE_MA_PCT = None

# Continuation entries: buying a stock already in Stage 2 that has pulled
# back toward its rising average, rather than requiring a fresh breakout
# through resistance.
#
# The book describes this as the trader's re-entry — after selling well
# above the average, repurchase on dips back close to it. The screener
# only ever recognises breakout entries, which is why a stop-out is
# usually terminal: the stock is mid-trend, resistance was cleared long
# ago, and condition 7 has nothing left to confirm. Measured over the
# 2021-2026 window it took a median of 2 trades per stock across five
# years and captured 2% of the available advance.
#
# A continuation setup requires the trend intact (Stage 2, price above a
# rising average) and price within this distance of the average — close
# enough that the stop sits near, which is the whole point.
#
# None disables it, which is current behaviour.
CONTINUATION_ENTRY_MAX_PCT_ABOVE_MA = None

# Conditions to drop from scoring entirely, by name. A dropped condition
# resolves to None, which the ratio already excludes, so it stops
# influencing the verdict without changing the arithmetic elsewhere.
#
# This exists because measuring each condition separately against outcome
# produced two results the checklist can't survive unexamined:
#
#   volume_confirmation  +1.84% when it passes, +1.84% when it fails.
#                        Not weak — identical to two decimals across 6,151
#                        trades. The condition carries no information.
#
#   risk_reward          +1.50% when it passes, +2.26% when it fails.
#                        Backwards. The 15% stop ceiling is selecting
#                        against winners, which is now the fourth
#                        independent measurement pointing that way.
#
# Only resistance_breakout showed real edge (+1.75% against -0.80%).
# The remaining five never vary within the trade set, because three of
# them are hard gates that must pass for a trade to exist at all — that
# is a selection artifact and says nothing about their worth. Testing
# those needs them removed, not scored.
DISABLED_CONDITIONS = ()

# The mined entry filter: relative strength above MINED_RS_MIN, price at
# least MINED_PCT_BELOW_HIGH below its 52-week high, and a base wider
# than MINED_MIN_BASE_PCT. None disables it.
#
# Found by ranking 13 entry features against realised return over 6,151
# derivation trades, not by reading the book — and two of its three parts
# contradict the book. It buys *below* the 52-week high where the book
# buys breakouts into strength, and it prefers *wide* bases where the
# book and this code both prefer tight ones.
#
# It is the only rule in the project to replicate out of sample, holding
# across 2005-2009 (never queried, includes the crash), 2010-2020 and
# 2021-2026, improving per-trade return roughly fivefold in each.
MINED_ENTRY_FILTER = False
MINED_RS_MIN = 20.0
MINED_PCT_BELOW_HIGH = 7.0
MINED_MIN_BASE_PCT = 35.0

# Which side of MINED_PCT_BELOW_HIGH counts as a pass. I mined the
# threshold's *value* out of the winners and never questioned its
# *sign*. Batch 8 swept it and win rate falls as the required discount
# widens — 42.7 / 41.8 / 40.3 on derive and 39.9 / 38.6 / 37.5 on test
# across 5 / 7 / 10 percent — so demanding a deeper discount is at best
# doing nothing. That also runs against the documented 52-week-high
# effect, and against the book, which buys strength rather than
# discount. True requires price *within* the threshold of the high.
MINED_REQUIRE_NEAR_HIGH = False

# Kept for reference: the legacy absolute threshold this replaced.
ACTIONABLE_THRESHOLD = 8

# How many weeks of consolidation a breakout has to clear to count as
# one, and how far back before that base I look for the prior peak the
# swing rule measures from.
BASE_WINDOW = 26
PRE_BASE_LOOKBACK = 52

# How much history an evaluation is allowed to see, enforced inside
# evaluate_conditions rather than left to whatever each caller happened
# to fetch.
#
# This exists because it was silently broken. Pivot detection scans the
# entire series it's handed, so the live screener (fetching 104 weeks)
# and the backtest (fetching weeks-since-start plus a 90-week buffer,
# nearer 170) could look at the same stock on the same date and find
# different pivots, hence different resistance, different stops, and a
# different verdict. Nothing surfaced that — the results just disagreed
# depending on which entry point you came through.
#
# Where the number comes from: the swing rule needs a full pre-base
# window behind a full base, so PRE_BASE_LOOKBACK + BASE_WINDOW = 78 is
# the floor for complete geometry. 104 leaves 26 further weeks for price
# to have moved since the breakout, and comfortably clears the other
# internal lookbacks (MA_PERIOD + MA_SLOPE_LOOKBACK = 35, and Mansfield
# RS's 52-period SMA needing 53).
#
# Callers may fetch more than this — the backtest has to, since it walks
# forward through later bars — and the surplus is ignored here. Fetching
# *less* still degrades the evaluation, so this is a ceiling on what gets
# looked at, not a guarantee of what's available.
EVALUATION_WEEKS = 104

# A base wider than this (high-to-low, as a percentage of its high) isn't
# really a consolidation — it's a wide swing that happens to have a
# highest point. My own cutoff, not the book's; it's reported rather than
# used to reject, so a loose base shows up for review instead of being
# silently treated the same as a tight one.
BASE_MAX_RANGE_PCT = 40.0

MA_PERIOD = 30
MA_SLOPE_LOOKBACK = 5
MA_SLOPE_THRESHOLD_PCT = 0.5

# Require the average's slope to be *improving* before calling a Stage 1
# to Stage 2 transition, not merely positive. None disables it, which is
# the current behaviour.
#
# The book describes the transition as a shape: the average falls, flattens,
# then curves up. A single slope reading can't see that — it answers "is it
# rising", which is the first derivative, where the shape is the second. A
# flat average reached by decelerating from a steep decline is the setup;
# a flat average rolling over from an advance is the opposite, and they
# read identically to one slope measurement.
#
# Circumstantial support, not a result: on a recent live scan 323 of 330
# names classified Stage 2 and only 2 as Stage 1, so the transition the
# method exists to catch is essentially never observed.
MA_CURVATURE_LOOKBACK = None

VOLUME_CONFIRM_RATIO = 2.0

# The book gives TWO acceptable volume patterns and this code only ever
# tested the first:
#
#   A. a one-week spike of at least twice the past month's average, or
#   B. a build-up over the past three to four weeks running at twice the
#      prior average, coupled with *some* increase on the breakout week.
#
# So a stock quietly accumulating volume for a month and then breaking
# out on a modest bump satisfies the book and fails this implementation.
# Set BUILDUP_WEEKS to enable pattern B as an alternative route to
# passing; None keeps the current single-pattern behaviour.
#
# Worth noting the book prefaces both with an explicit rejection of any
# "magic level" of volume, then immediately uses twice-the-average as its
# working figure — so 2.0 is sourced rather than invented, and it is the
# *pattern* that was missing, not the number.
VOLUME_BUILDUP_WEEKS = None
VOLUME_BUILDUP_RATIO = 2.0
# "at least some increase on the breakout week" — deliberately mild,
# since under pattern B the confirmation has already happened during the
# build-up rather than on the breakout bar itself.
VOLUME_BUILDUP_BREAKOUT_MIN = 1.0
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

# Where the initial stop belongs. The book's worked examples tuck it just
# under a nearby support level — buy at 20 3/8 with the stop at 19 1/8,
# buy at 38 with the stop under 36 — which risks roughly 5-6%. Using the
# base's absolute low instead put stops 28-40% below entry on real
# tickers, which made every risk/reward reading meaningless and is
# exactly what the book warns against when it talks about buying stocks
# too far above their stop-loss points.
# How many weeks back from the breakout to look for the support the stop
# sits under. This is the immediate consolidation price thrust out of —
# searching the whole base instead put the stop under a low from up to
# half a year earlier, which on a trending stock is 20-40% away and not
# a stop anyone would actually place. The exact window is my own
# operational choice; the book picks the level visually off the chart.
STOP_SUPPORT_WINDOW = 8
STOP_BUFFER_PCT = 1.0
MAX_SENSIBLE_STOP_PCT = 15.0

# The swing rule measures from "the peak price before an important
# decline". A shallow dip isn't one, and without a real decline there's
# nothing for the rule to measure. This cutoff for "important" is mine,
# not the book's.
MIN_IMPORTANT_DECLINE_PCT = 10.0

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

    if MA_CURVATURE_LOOKBACK:
        # Compare this slope against the slope one window earlier. A
        # decline that is easing counts as curving up even while still
        # negative — that is precisely the flattening phase.
        back = MA_CURVATURE_LOOKBACK
        prior_idx = latest - back
        if prior_idx - MA_SLOPE_LOOKBACK >= 0:
            prior_now = wma_series[prior_idx]
            prior_then = wma_series[prior_idx - MA_SLOPE_LOOKBACK]
            if prior_now is not None and prior_then and prior_then != 0:
                prior_slope = (prior_now - prior_then) / prior_then * 100
                curving_up = slope_pct > prior_slope
                if falling and price > ma_now and not curving_up:
                    # Price above a falling average that is still
                    # steepening is a bounce, not a base.
                    return None
                if rising and price > ma_now and not curving_up:
                    # An advance already decelerating is late-stage.
                    return 3

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


def _find_base_and_breakout(closes, highs, lows):
    """Locates the most recent breakout event and the consolidation it
    emerged from.

    The previous version didn't detect anything. It assumed the base was
    always exactly the fixed slice bars[-34:-8] and only looked for a
    breakout in the final 8 weeks, so anything that broke out earlier
    simply vanished. Measured across a real 15-ticker scan, 7 had no
    detectable breakout at all, which cascaded into three conditions
    (volume, pullback, risk/reward) all returning None and left most of
    the universe unable to reach a verdict.

    A breakout bar closes above every high in the preceding BASE_WINDOW
    weeks. In a sustained advance that stays true for many consecutive
    bars, so the meaningful one is the *first* of such a run — the
    transition out of the base — not the latest. I scan backward for the
    most recent False->True transition to find it.

    This feeds conditions 1, 8, and 9, which all need a specific breakout
    bar to reason about. Condition 7 uses a separate pivot-based read
    from trend_support_resistance.py — see _evaluate_resistance_breakout.
    """
    n = len(closes)
    empty = {
        "resistance_level": None, "breakout_idx": None, "base_start": None,
        "base_end": None, "breakout_age_weeks": None, "base_range_pct": None,
        "base_is_tight": None,
    }
    if n < BASE_WINDOW + 4:
        return empty

    def is_breakout(i):
        return closes[i] > max(highs[i - BASE_WINDOW:i])

    breakout_idx = None
    for i in range(n - 1, BASE_WINDOW, -1):
        if is_breakout(i) and not is_breakout(i - 1):
            breakout_idx = i
            break

    # A run that was already underway at the earliest bar I can test:
    # there's no False->True transition inside the data, but the breakout
    # is real, it just happened before this history starts.
    if breakout_idx is None and is_breakout(BASE_WINDOW):
        breakout_idx = BASE_WINDOW

    if breakout_idx is None:
        return empty

    base_end = breakout_idx
    base_start = max(0, breakout_idx - BASE_WINDOW)
    resistance_level = max(highs[base_start:base_end])
    base_low = min(lows[base_start:base_end])
    base_range_pct = (
        (resistance_level - base_low) / resistance_level * 100 if resistance_level else None
    )

    return {
        "resistance_level": resistance_level,
        "breakout_idx": breakout_idx,
        "base_start": base_start,
        "base_end": base_end,
        "breakout_age_weeks": (n - 1) - breakout_idx,
        "base_range_pct": base_range_pct,
        "base_is_tight": (
            base_range_pct is not None and base_range_pct <= BASE_MAX_RANGE_PCT
        ),
    }


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


def _volume_buildup_ratio(volumes, breakout_idx, weeks):
    """Average volume over the `weeks` before the breakout, against the
    average of the equivalent stretch before that.

    This is the book's second acceptable pattern — sustained heavy
    trading during the base rather than a single spike on the breakout.
    """
    if breakout_idx is None or weeks is None:
        return None
    start = breakout_idx - weeks
    prior_start = start - weeks
    if prior_start < 0:
        return None
    recent = volumes[start:breakout_idx]
    prior = volumes[prior_start:start]
    if not recent or not prior:
        return None
    prior_avg = sum(prior) / len(prior)
    if not prior_avg:
        return None
    return (sum(recent) / len(recent)) / prior_avg


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
        if volume_ratio >= VOLUME_CONFIRM_RATIO:
            return True, volume_ratio, "breakout"
        # Pattern B: the build-up route. Volume ran heavy for the weeks
        # *before* the breakout, and the breakout week itself only needs
        # some increase rather than a spike.
        if VOLUME_BUILDUP_WEEKS:
            built = _volume_buildup_ratio(volumes, breakout_idx, VOLUME_BUILDUP_WEEKS)
            if (built is not None and built >= VOLUME_BUILDUP_RATIO
                    and volume_ratio >= VOLUME_BUILDUP_BREAKOUT_MIN):
                return True, volume_ratio, "breakout_buildup"
        return False, volume_ratio, "breakout"
    if in_pullback:
        return volume_ratio < VOLUME_CONTRACTION_RATIO, volume_ratio, "pullback"

    # Neither a fresh breakout nor an identified pullback — the book's
    # volume rule is specifically about those two moments, so there's
    # nothing meaningful to say about a week that's neither.
    return None, volume_ratio, "not_applicable"


def _find_initial_stop(lows, base_start, base_end, resistance_level, entry):
    """The initial stop belongs just beneath the support price thrust out
    of, which is what the book's examples do — not at the bottom of the
    entire base.

    Two wrong turns worth recording, since both produced plausible-looking
    numbers that were badly wrong. Searching the whole base for a swing
    low put the stop under a low from up to half a year earlier: 20-40%
    away on a trending stock, which is what the original base-low version
    already did and is not a stop anyone would place. Using the cleared
    resistance instead went the other way — resistance is the base's high,
    so it outranks every low inside that base by construction, collapsing
    the stop to 1-2% and passing all fifteen tickers on ratios up to 30:1.
    A condition that passes everything is as uninformative as one that
    fails everything.

    So: the low of the immediate pre-breakout consolidation, tucked under
    by a small buffer. Only bars up to the breakout are considered, so
    this is a level that could genuinely have been set at entry rather
    than one confirmed in hindsight.
    """
    window_start = max(base_start, base_end - STOP_SUPPORT_WINDOW)
    window = [low for low in lows[window_start:base_end] if low < entry]
    if window:
        return min(window) * (1 - STOP_BUFFER_PCT / 100), "pre_breakout_low"

    if resistance_level is not None and resistance_level < entry:
        return resistance_level * (1 - STOP_BUFFER_PCT / 100), "breakout_level"

    return None, "unavailable"


def _evaluate_risk_reward(highs, lows, closes, resistance_level, breakout_idx, base_start, base_end):
    """Condition 9. Three corrections from what this used to compute, each
    checked against the book's own worked examples:

    1. The swing rule projects from the peak that preceded the decline,
       not from the entry price. Take that peak, subtract the low that
       followed it, and add the difference back onto the peak.
    2. It only comes into force once price has bettered that old peak.
       Before then the nearest real objective is the peak itself, so
       that's what I measure against, labelled as such.
    3. The stop goes just under the nearest support below entry — see
       _find_initial_stop.

    The book also notes the swing rule "doesn't appear often" and uses it
    for partial profit-taking rather than as an entry gate. When there was
    no important decline to measure I fall back to projecting the base's
    own height, labelled distinctly since that's a standard measured-move
    idea rather than anything the book prescribes.

    The base bounds are passed in now that they're detected rather than
    assumed, since base_start + BASE_WINDOW is no longer guaranteed to
    equal base_end (an early breakout clamps base_start at zero).
    """
    if resistance_level is None or breakout_idx is None or base_start is None:
        return None, None, None, {}

    entry = closes[breakout_idx]
    base_low = min(lows[base_start:base_end])

    stop, stop_method = _find_initial_stop(lows, base_start, base_end, resistance_level, entry)
    if stop is None:
        return None, None, None, {"stop_method": stop_method}

    pre_base_end = base_start
    pre_base_start = max(0, pre_base_end - PRE_BASE_LOOKBACK)
    peak_price = None
    decline_low = None
    if pre_base_start < pre_base_end:
        pre_base = highs[pre_base_start:pre_base_end]
        peak_price = max(pre_base)
        peak_idx = pre_base_start + pre_base.index(peak_price)
        # The rule's low is the bottom of the decline that followed the
        # peak, which generally forms *before* the base proper and so
        # falls outside the base window. Measuring from the base's own low
        # instead understates the decline — checked against the book's
        # worked example, where it produced 36.25 against a stated 37.75.
        decline_low = min(lows[peak_idx:base_end])

    decline_pct = (
        ((peak_price - decline_low) / peak_price * 100)
        if peak_price and decline_low is not None and peak_price > decline_low else None
    )
    important_decline = decline_pct is not None and decline_pct >= MIN_IMPORTANT_DECLINE_PCT

    # The rule's geometry is peak -> decline -> base -> breakout back
    # above that peak. That only holds if the base actually formed below
    # the old peak. When the base's own high already sits above it, price
    # never "betters an old peak" in the sense the rule means, and
    # projecting from a peak the stock left behind long ago produces
    # targets underneath the current price — which is what was making six
    # of fifteen tickers report negative reward.
    swing_rule_applies = important_decline and peak_price > resistance_level

    if swing_rule_applies and entry > peak_price:
        target = peak_price + (peak_price - decline_low)
        target_method = "swing_rule"
    elif swing_rule_applies:
        target = peak_price
        target_method = "prior_peak"
    else:
        target = resistance_level + (resistance_level - base_low)
        target_method = "base_height_fallback"

    reward = target - entry
    risk = entry - stop
    stop_pct = (risk / entry * 100) if entry else None

    detail = {
        "target_method": target_method,
        "stop_method": stop_method,
        "prior_peak": peak_price,
        "base_low": base_low,
        "decline_low": decline_low,
        "decline_pct": decline_pct,
        "reward": reward,
        "risk": risk,
        "stop_pct": stop_pct,
        "stop_too_wide": stop_pct is not None and stop_pct > MAX_SENSIBLE_STOP_PCT,
    }

    if risk <= 0:
        return target, stop, None, detail

    if detail["stop_too_wide"]:
        # The nearest genuine support is so far below entry that the
        # position would risk more than the book ever countenances — it
        # warns specifically about buying stocks too far above their
        # stop-loss points. A favourable ratio doesn't rescue that: the
        # ratio is about proportion, this is about absolute exposure on a
        # single position. Reported rather than silently tightened,
        # because a stop placed closer than real support is fiction.
        detail["ratio"] = reward / risk
        return target, stop, False, detail

    if reward <= 0:
        # The measured objective already sits at or below the entry, so
        # there's no favourable reward left to weigh. That's a definite
        # answer, not an unknown one.
        detail["ratio"] = reward / risk
        return target, stop, False, detail

    ratio = reward / risk
    detail["ratio"] = ratio
    if ratio >= RISK_REWARD_CLEAR_PASS:
        result = True
    elif ratio <= RISK_REWARD_CLEAR_FAIL:
        result = False
    else:
        result = None  # thin margin — flagged for manual review below

    return target, stop, result, detail


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


CONDITION_NAMES = (
    "stage_setup", "price_above_ma", "volume_confirmation", "rs_improving",
    "sector_strength", "market_stage", "resistance_breakout", "pullback_quality",
    "risk_reward",
)


def _empty_result():
    """The shape evaluate_conditions returns when there's nothing to read,
    with every condition unknown. Same keys as a real result so callers
    don't need to special-case it — the evidence floor in the scoring
    model already refuses to call anything actionable on no evidence.
    """
    conditions = {name: None for name in CONDITION_NAMES}
    return {
        "conditions": conditions,
        "conditions_met": 0,
        "conditions_detail": {name: {"result": None} for name in CONDITION_NAMES},
        "scoring": score_conditions(conditions),
        "actionable": False,
        "stage": None, "price": None, "ma_30w": None, "price_above_ma": None,
        "ma_rising": None, "mansfield_rs": None, "rs_improving": None,
        "rs_ma_rising": None, "volume_ratio": None, "volume_confirmed": None,
        "market_stage_ok": None, "resistance_level": None,
        "breakout_confirmed": None, "swing_target": None, "swing_stop": None,
        "historical_levels": None, "new_52w_high": None, "breakout_idx": None,
        "breakout_age_weeks": None, "base_is_tight": None, "base_range_pct": None,
        "extension_above_ma_pct": None,
        "continuation_entry": False,
        "pct_below_52w_high": None,
    }


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

    Only the most recent EVALUATION_WEEKS bars are considered, however
    many are passed in, so that two callers fetching different depths
    reach the same verdict on the same date. Any index this returns is
    translated back to the caller's own numbering, so `breakout_idx`
    still indexes the `bars` list that was handed in.
    """
    # Trim to the evaluation window before anything reads these. Each
    # series is trimmed independently: a recently listed ticker may have
    # fewer bars than the index, and forcing them to a common length here
    # would quietly shorten the stock's own moving average.
    if not bars or not index_bars:
        # Nothing to read. This happens for real in a backtest whenever a
        # checkpoint predates a ticker's first bar — truncating to that
        # date leaves an empty series, and every later step here indexes
        # off the end of it. It surfaced as 318 "list index out of range"
        # failures across one run, each one a checkpoint silently thrown
        # away behind an error that named the symptom rather than the
        # cause. A stock that didn't exist yet isn't an error, it's an
        # unknown.
        return _empty_result()

    bars_offset = max(0, len(bars) - EVALUATION_WEEKS)
    index_offset = max(0, len(index_bars) - EVALUATION_WEEKS)
    bars = bars[bars_offset:]
    index_bars = index_bars[index_offset:]

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
    base = _find_base_and_breakout(closes, highs, lows)
    resistance_level = base["resistance_level"]
    breakout_idx = base["breakout_idx"]
    base_start = base["base_start"]

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
    # How far above the average the stock sat *at the bar a purchase would
    # actually fill on*, which is what decides how far below the entry the
    # stop can possibly sit.
    #
    # Measured at the breakout bar, not at today's bar, and the difference
    # is not cosmetic. A scan sees a breakout a median of four weeks after
    # it happened, and both the entry plan and the backtest fill at the
    # breakout level rather than at today's price. Measuring here would
    # reject a trade on a run-up that occurred *after* the price paid — and
    # worse, it would block re-entry after a stop-out, since a stock that
    # has recovered is extended when next scanned. The first version did
    # exactly that: armed at 40% it removed 226 of 273 trades and enabled
    # no replacements at all.
    #
    # Falls back to the latest bar only when no breakout was detected,
    # where there is no fill bar to speak of.
    _entry_idx = breakout_idx if breakout_idx is not None else latest_idx
    _ma_at_entry = ma_series[_entry_idx] if _entry_idx < len(ma_series) else None
    if not _ma_at_entry:
        # The breakout can predate the average's warm-up, in which case
        # there is no reading at that bar. Falling back to the latest bar
        # is right in substance — the question is how extended the
        # position is — and it also closes a silent hole: returning None
        # here made the extension gate un-fireable on exactly those
        # setups, so R4 was inactive for an unknown share of trades
        # without anything in the output saying so.
        _entry_idx = latest_idx
        _ma_at_entry = ma_now
    extension_above_ma_pct = (
        None if not _ma_at_entry else (closes[_entry_idx] / _ma_at_entry - 1) * 100
    )

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
    # Pair the two series by date rather than by position. Zipping by
    # position quietly compares mismatched weeks whenever the series
    # differ in length, and raises outright when the stock is younger
    # than the index — which across a full-market scan discarded 463
    # recently listed names behind an error message that said nothing
    # about the actual cause. A young stock should come back as "not
    # enough history to judge", not as a crash.
    index_by_date = {b["time"][:10]: b["close"] for b in index_bars}
    paired = [
        (b["close"], index_by_date[b["time"][:10]])
        for b in bars
        if b["time"][:10] in index_by_date
    ]
    mrs_series, rs_ma_rising = mansfield_rs.compute_mansfield_rs(
        [c for c, _ in paired], [i for _, i in paired]
    )
    # Indexed from the end, since the paired series is shorter than the
    # ticker's own bars whenever some weeks had no matching index bar.
    mrs_now = mrs_series[-1] if mrs_series else None
    mrs_prior = (
        mrs_series[-1 - MA_SLOPE_LOOKBACK] if len(mrs_series) > MA_SLOPE_LOOKBACK else None
    )
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
    swing_target, swing_stop, risk_reward, risk_reward_detail = _evaluate_risk_reward(
        highs, lows, closes, resistance_level, breakout_idx, base_start, base["base_end"]
    )

    # A continuation setup stands in for the breakout trigger when the
    # trend is already established. It never relaxes the trend conditions
    # themselves — stage, the average, relative strength and the market
    # read all still have to pass on their own terms.
    continuation_entry = False
    if (
        CONTINUATION_ENTRY_MAX_PCT_ABOVE_MA is not None
        and stage == 2
        and price_above_ma is True
        and ma_rising is True
        and extension_above_ma_pct is not None
        and 0 <= extension_above_ma_pct <= CONTINUATION_ENTRY_MAX_PCT_ABOVE_MA
    ):
        continuation_entry = True
        if resistance_breakout is None:
            resistance_breakout = True
        if pullback_quality is None:
            pullback_quality = True

    conditions = _apply_disabled({
        "stage_setup": stage_setup,
        "price_above_ma": price_above_ma,
        "volume_confirmation": volume_confirmed,
        "rs_improving": rs_condition,
        "sector_strength": sector_strength_result,
        "market_stage": market_stage_ok,
        "resistance_breakout": resistance_breakout,
        "pullback_quality": pullback_quality,
        "risk_reward": risk_reward,
    })
    conditions_met = sum(1 for v in conditions.values() if v is True)
    # The mined filter's three inputs, all measurable at the entry bar.
    pct_below_52w_high = (
        (week_52_high - closes[latest_idx]) / week_52_high * 100
        if week_52_high else None
    )
    mined_ok = (
        _mined_filter_passes(mrs_now, pct_below_52w_high, base["base_range_pct"])
        if MINED_ENTRY_FILTER else None
    )

    scoring = score_conditions(conditions, extension_above_ma_pct, mined_ok)

    conditions_detail = {}
    for name, value in conditions.items():
        entry = {"result": value}
        if name in ("pullback_quality", "risk_reward"):
            entry["manual_review"] = True
        if name == "risk_reward":
            entry.update(risk_reward_detail)
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

    # Also context rather than a condition: which consolidation the
    # breakout came out of, how long ago, and whether that base was
    # actually tight enough to call it one.
    #
    # Bar positions are shifted back into the caller's numbering, since
    # everything above ran against the trimmed window. Without this,
    # anything indexing the original list with these would silently read
    # the wrong bar — the offset is exactly the number of bars dropped.
    conditions_detail["base"] = dict(base)
    for key in ("breakout_idx", "base_start", "base_end"):
        if conditions_detail["base"].get(key) is not None:
            conditions_detail["base"][key] += bars_offset
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
        # Shifted back into the caller's numbering — see above.
        "breakout_idx": (breakout_idx + bars_offset) if breakout_idx is not None else None,
        "breakout_age_weeks": base["breakout_age_weeks"],
        "base_is_tight": base["base_is_tight"],
        "base_range_pct": base["base_range_pct"],
        "extension_above_ma_pct": extension_above_ma_pct,
        "continuation_entry": continuation_entry,
        "pct_below_52w_high": pct_below_52w_high,
    }


def _mined_filter_passes(rs, pct_below_52w_high, base_range_pct):
    """The mined entry filter's three tests, all measurable at entry.

    Extracted so it can be tested with explicit inputs. Exercising it
    through evaluate_conditions needs a synthetic series that happens to
    resolve all three, and building one to order is fixture-fighting —
    mutations of the individual comparisons survived that way.

    Returns False when any input is missing: an unmeasurable filter is
    not a passed one.
    """
    if rs is None or pct_below_52w_high is None or base_range_pct is None:
        return False
    near_high = (pct_below_52w_high < MINED_PCT_BELOW_HIGH
                 if MINED_REQUIRE_NEAR_HIGH
                 else pct_below_52w_high > MINED_PCT_BELOW_HIGH)
    return (rs > MINED_RS_MIN
            and near_high
            and base_range_pct > MINED_MIN_BASE_PCT)


def _effective_resolved_floor():
    """The evidence floor, adjusted for deliberately dropped conditions.

    The floor exists to stop a verdict resting on too little evidence,
    and it was counted against all nine conditions. But dropping a
    condition shrinks the pool it is measured against, so the two
    interact badly: with sector strength unavailable (as it is for any
    window before ~2021) at most eight can resolve, and dropping two
    more leaves six against a floor of seven. Qualification becomes
    arithmetically impossible.

    That is exactly what happened — the arms dropping both volume
    confirmation and risk/reward returned zero trades across all three
    windows, which reads like "the rule rejects everything" and is
    actually "the rule cannot be satisfied". Deliberately removing a
    condition must not make the checklist unreachable.

    Never falls below 4, so dropping conditions can't erode the floor
    to nothing.
    """
    return max(4, MIN_RESOLVED_CONDITIONS - len(DISABLED_CONDITIONS))


def _apply_disabled(values):
    """Forces every name in DISABLED_CONDITIONS to None.

    None is already excluded from the scoring ratio, so a dropped
    condition stops influencing the verdict without altering the
    arithmetic around it.
    """
    return {name: (None if name in DISABLED_CONDITIONS else value)
            for name, value in values.items()}


def score_conditions(conditions, extension_above_ma_pct=None, mined_ok=None):
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

    too_extended = (
        MAX_EXTENSION_ABOVE_MA_PCT is not None
        and extension_above_ma_pct is not None
        and extension_above_ma_pct > MAX_EXTENSION_ABOVE_MA_PCT
    )

    if mined_ok is False:
        actionable = False
        reason = ("fails the mined entry filter (relative strength, distance "
                  "below the 52-week high, base width)")
    elif too_extended:
        actionable = False
        reason = (
            f"price is {extension_above_ma_pct:.0f}% above its 30-week average, "
            f"past the {MAX_EXTENSION_ABOVE_MA_PCT:.0f}% limit — buying here is "
            f"chasing, and puts the stop far below the entry"
        )
    elif blocking:
        actionable = False
        reason = "blocked by non-negotiable condition(s): " + ", ".join(blocking)
    elif resolved < _effective_resolved_floor():
        actionable = False
        reason = (
            f"only {resolved} of {len(conditions)} conditions resolved — "
            f"need {_effective_resolved_floor()} before a verdict means anything"
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
        "extension_above_ma_pct": extension_above_ma_pct,
        "too_extended": too_extended,
        "mined_ok": mined_ok,
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
