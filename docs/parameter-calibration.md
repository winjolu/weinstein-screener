# Parameter Calibration Status

The 9-condition checklist comes from the book, but several of the
numbers the code tests against do not — the book states those rules
qualitatively. This file records which thresholds are my own
operational choices, how much evidence each one actually rests on, and
what would justify revisiting it.

The distinction I care about here is between a parameter being
*calibrated* (it behaves sensibly on the data I've looked at) and
*validated* (it demonstrably predicts better outcomes). Everything
below is at best the former.

## Decision: MAX_SENSIBLE_STOP_PCT stays in conditions.py (2026-07-25)

A stop further than 15% below entry fails condition 9 outright, in
`conditions.py`, as a screening decision.

I considered moving this to `position_sizing.py` on the argument that a
wide stop is a position-sizing problem rather than a screening one —
risk less capital on the setup instead of rejecting it.

**That argument is wrong, and not merely under-evidenced.** R-multiple
is defined as (exit − entry) / (entry − stop). Position size does not
appear in it. So shrinking a position cannot change that trade's
R-expectancy at all; it changes only the dollar variance. A setup with
no edge per unit of risk still has no edge per unit of risk when you
take less of it. The justification fails by construction, independent of
any sample size.

A diagnostic backtest run with the ceiling disabled pointed the same
way, though it is weak evidence and I am not leaning on it: 65 trades
versus 53, win rate 46.2% versus 49.1%, expectancy +2.31% versus
+3.02%. Isolating just the newly admitted wide-stop trades gave 16
trades at a 31% win rate and +0.023R — indistinguishable from zero
edge, but equally indistinguishable from a modest positive one at that
sample size. The two runs are also not a clean superset of one another,
since admitting a trade earlier suppresses later ones through the
in-trade window.

**What this decision does not do is validate 15% as the right number.**
~~It remains arbitrary — I picked it as a midpoint between the roughly
5-6% risk in the book's worked examples and the roughly 20% my own stop
placement produces on real tickers, two figures I never reconciled.~~

**Correction, 2026-07-28: that was wrong, and it inverted the confidence
I should have had in this number.** Reading the source directly, the
book states the limit outright — restrict purchases to cases where the
initial stop sits no more than 15% below the purchase price, allowing
occasional exceptions for an outstanding pattern. I had not read that
passage when I wrote the note above; I reconstructed the figure by
splitting the difference between two other numbers and then recorded my
own reconstruction as arbitrary.

So 15.0 is the best-sourced threshold in this project rather than the
worst, and it has been treated as the least trustworthy one on the
strength of a note I made up. See [methodology.md](methodology.md).

The more important half of the correction is what kind of rule it is.
The book frames it as a constraint on **which stocks may be bought** —
calculate the stop before placing the buy order, and let the resulting
risk filter the candidate list. It is implemented here as one condition
of nine, so a setup whose stop sits 60% below entry fails condition 9,
scores 7 of the remaining 8, and is bought anyway. That is not a
calibration problem and no value of this constant fixes it.

**Re-open when:** the full-universe scan is verified and has produced a
dataset in the hundreds of trades rather than tens, which is the point
at which wide-stop-setup edge can actually be estimated. The trigger is
sample size, not a tidier architecture — this round rejected an
architectural argument that the data did not support.

## Why I didn't retune the stop ceiling when the data arrived (2026-07-27)

The decision above anticipated re-opening this once a real dataset
existed. One does now — 6,782 stocks — and it says the ceiling rejects
84% of setups among names trading over $25M a week, i.e. it is the
binding constraint on almost everything liquid enough to actually trade.

That looks like a clear case for raising it. It isn't, and the reason is
worth recording so I don't talk myself into it later.

I tested the two mechanical explanations for why my stops sit around 22%
when the book's worked examples risk 5-6%, and both came back negative:

- **The lookback window isn't it.** Shrinking the pre-breakout window
  from 8 weeks to 2 only moves the median from 24.5% to 15.0%, still
  triple the book, and at that length the stop hugs price closely enough
  to be triggered by noise.
- **The entry basis isn't it.** I enter at the breakout week's close
  rather than at the breakout level a resting buy-stop would fill at,
  but breakout weeks close a median of only 2.5% above their own level.
  Worth 2.6 points of the gap, not 17. (The level is touched during the
  breakout week 98% of the time, so buy-stop entry is at least a
  realistic model.)

What's left is that my placement rule and the book's are different rules.
Mine puts the stop at the low of the recent consolidation. Re-reading the
worked examples — buy at 20 3/8 with the stop at 19 1/8, or bought above
resistance at 38 with the stop under the round number of 36 — those are
the nearest meaningful chart level *below entry*, not the bottom of the
range. I confirmed both ends of the spectrum on real data: the range low
gives roughly 22%, tucking under the breakout level itself gives 1-2%.
The book's practice sits between them and I implement neither.

So the ceiling isn't the broken part. Retuning it would fit a number to a
distribution produced by a rule I've just established doesn't match the
method, and there's no natural breakpoint to fit to in any case — 17.5%
at the first quartile, 24.5% at the median, smooth throughout.

### Then I tried the rework, and it was worse

I rebuilt stop placement to pick the *nearest* meaningful level below
entry — minor swing lows, the cleared resistance, the nearest round
number — rather than the lowest low of a window. It produced a median
stop of 5.5%, almost exactly the book's figure. I nearly committed it.

It was wrong, and the giveaway was the spread rather than the middle. The
old rule ran 17.5% to 35.8% across the quartiles; the rework ran 4.6% to
6.6%. A stop derived from real support should vary a great deal between
stocks, and one that barely varies is being set by a constant. It was:
the nearest round number below the minimum-distance ceiling is always
within one step of that ceiling, so it won 84% of the time and the
minimum distance was setting every stop. Chart structure won 1% of the
time. Condition 9 flipped from failing 84% to passing 90%, which is
equally uninformative in the opposite direction.

The lesson, which I have now learned twice on this same function: when a
calibration change makes a distribution collapse rather than shift, the
parameter is talking, not the market.

### Why the book's percentages don't transfer

The thing that actually settles it is weekly noise. Across 320,771
stock-weeks on liquid names, the median weekly dip below the prior close
is 3.1% and the 75th percentile is 6.3%. A 5% stop therefore sits between
the median and p75 of a *single week's ordinary movement* — it gets
tagged in 33% of weeks, against 2% for a 22% stop. Nothing about position
sizing rescues that: a tight stop buys a 4.4x larger position for the
same dollar risk, but it's being hit by Tuesday rather than by the thesis
failing, and this system's whole premise is holding through a multi-month
advance.

So Weinstein's stop *placement principle* — nearest meaningful support —
is what transfers, and on modern charts that principle yields roughly
22%, not roughly 5%. His percentages are 1980s stocks at 1980s
volatility, managed on daily charts between weekly reviews. Treating his
numbers as portable to a weekly-bar screener is a category error.

**Both numbers stay as they are, and are now justified rather than merely
unretuned.** The 84% "too wide" rate is the tool correctly reporting that
most breakouts near highs carry real risk, and it costs one condition of
nine rather than rejecting the setup outright, which is proportionate.

## Trailing stop: the book's own method measured worse (2026-07-27)

Partial profit-taking failing pointed at the trailing stop, on the
theory that the 30-week average sits too far below price after a sharp
advance and hands back the gain. Reading the book properly showed my
trailing stop wasn't its method at all. The book waits for a correction
of at least 8-10%, holds off raising anything until the stock rallies
back near its prior high, then places the stop under the correction low
or under the average depending on which is lower — and, once the average
flattens and a Stage 3 top becomes likely, moves under the correction
low even when that sits above the average. Mine just followed the
average, with no notion of corrections and no tightening near a top.

Implemented as a third method and measured across 200 tickers over
nearly three years, roughly 220 resolved trades per arm rather than the
29 I'd been deciding on:

| trailing stop | resolved | win% | payoff | per trade | total R |
|---|---|---|---|---|---|
| 30-week average (mine) | 220 | 39.5% | 2.24 | +2.86% | +22.8 |
| swing lows (mine) | 133 | 39.8% | 1.40 | −0.58% | +3.8 |
| corrections, per the book | 140 | 36.4% | 1.15 | −2.99% | −10.2 |

The average wins clearly, and the book's method is worst. Its stop moves
so rarely that positions don't resolve — 58 of 198 still open against 14
of 234 — so it isn't holding winners longer so much as failing to close
anything.

Two honest qualifications. The confirmation threshold, "rallies back
close to its prior peak", is a number I invented to operationalise a
phrase; too strict a value would produce exactly this symptom, so I
can't fully separate "the book's method is worse here" from "my reading
of it is wrong". And the 107 trades common to all three arms show every
method negative, because a trade only appears in that subset if it
resolved under the loosest stop too, which selects for losers.

**The default stays on the 30-week average.** The book's method stays in
the code as a named option, since the finding is about my implementation
of it rather than about the idea.

### The samples I'd been deciding on were too small

Worth recording separately. The same window on 20 tickers gave a 51.7%
win rate and a 1.61 payoff; 200 tickers gave 39.5% and 2.24. Those
aren't refinements of each other, and the earlier figure flattered the
win rate while hiding a genuinely better payoff profile. Anything
concluded from a 29-trade sample in this project should be treated as a
hint, and the 200-ticker harness takes about three minutes an arm.

## PARTIAL_EXIT_FRACTION = 0.5 — measured properly, and it's a wash (2026-07-28)

The book sells half the position at the swing-rule target. I'd measured
this once on ten target-reaching trades, found selling everything looked
better, and kept the book's half anyway on sample-size grounds.

Re-measured on 254 trades across 198 tickers, of which 83 reach the
target. Two things made this version worth trusting where the last
wasn't. First, the sample: 83 against 10. Second, the comparison is
paired — 151 of the 254 trades never reach the target and are identical
in every arm, so comparing arm-level averages dilutes the real effect by
roughly two-thirds. Comparing only the trades where the policy applies:

| at the target | mean | median |
|---|---|---|
| sell everything | +19.83% | +17.92% |
| sell half (the book) | +19.18% | +15.49% |
| sell nothing, trail it all | +18.53% | +10.08% |

Selling everything wins on 66% of individual trades. That looks decisive
and isn't: the mean advantage over selling half is 0.65 points against a
16.57-point spread, which is 0.4 standard errors from zero. The medians
show why. Selling everything wins more often; selling half wins bigger
when it wins, because the retained half occasionally runs a long way.
Those are the two halves of the same trade-off and they cancel.

**Unchanged, but for a better reason.** It was kept because ten
observations shouldn't overrule the source. It's now kept because 83
can't find a difference either — and where there's no measurable
difference, the book's version is the one with reasoning behind it.

Note the ordering is stable across all three arms and both statistics,
which is worth something even without significance: nothing here suggests
letting the whole position run is better, and that was the live
hypothesis when the trailing stop was under suspicion.

## CORRECTION_RECOVERY_PCT = 3.0 is wrong, and the rule around it may be too (2026-07-28)

This is the number I invented to operationalise the book's "rallies back
close to its prior peak" — how near the old high a stock must get before
the correction-based trailing stop is allowed to move up. I flagged it
in known-gaps as the likely reason the book's trailing method measured
worse than simply following the 30-week average. Swept it across 198
tickers, same window, ~250 trades an arm:

| threshold | n | win | mean/trade | total R | never resolved |
|---|---|---|---|---|---|
| 1% | 102 | 27.5% | −6.28% | −30.1 | 44.6% |
| **3% (default)** | 147 | 39.5% | **−2.06%** | −10.0 | 27.2% |
| 6% | 187 | 41.7% | +0.11% | −3.1 | 16.9% |
| 12% | 227 | 42.3% | +1.07% | +9.0 | 8.8% |
| 20% | 236 | 41.5% | +1.26% | +9.2 | 7.5% |
| *30-week average* | *238* | *44.5%* | *+2.85%* | *+24.0* | — |

**The guess was right: 3.0 is far too strict**, and costs about 3.3
points a trade against a loose setting. The last column is the
mechanism and it's unambiguous — at 1% nearly half the positions never
resolve at all, because a stock has to climb back to within 1% of its
old high before the stop may move, and mostly it doesn't. The stop sits
still and the trade never closes. That is precisely the symptom I
recorded without being able to explain it.

**But the more useful finding is the shape of the curve.** Performance
improves monotonically as the threshold loosens, all the way to a value
so permissive the rule barely constrains anything. A gate that works
better the less it gates is evidence against the gate, not evidence for
a particular setting. Retuning to 20% would be fitting the number to
this window; the honest options are to set it at ~10%, which is at
least coherent with the rule's own scale given it requires an 8-10%
correction first, or to drop the confirmation requirement and re-measure
the method without it.

**Left at 3.0 pending that decision**, since `trailing_method='book'` is
not the default and nothing is exposed while it waits. Recording the
number as known-bad rather than silently retuning it to the value this
particular sweep preferred.

**What doesn't change:** the 30-week average still wins clearly, at
+2.85% against +1.26% for the best book setting. The earlier conclusion
stands; only its explanation has improved. The gap was partly my
threshold, and correcting that closes about two-thirds of it.

## Other thresholds, ranked by how much I trust them

**ACTIONABLE_SCORE = 0.80** — ~~most trustworthy of the set, because it
is anchored rather than invented: ceil(0.8 × 9) = 8 reproduces the
previous "8 of 9" rule exactly when every condition resolves.~~

**Struck 2026-07-28.** This was anchored to the "8 of 9" rule, and that
rule is not in the book — I had it from my own summary, which invented
it. So the reasoning was that 0.80 faithfully reproduces a threshold
that never existed. Faithfully reproducing something made up is not
anchoring.

Worse, the book addresses this exact construction and rejects it. It
asks whether poor volume on a breakout can be overlooked when every
other factor is positive, and answers that it cannot — the missing
confirmation is itself the danger signal. A score that admits a setup at
8 of 9 is that reasoning in code, and which condition failed is the part
it discards. The right shape is gates, not a ratio. Recorded in
[known-gaps.md](known-gaps.md); not changed yet, because switching the
whole checklist to hard gates is a methodology decision rather than a
retune, and it would reject most of what currently qualifies.

**MIN_RESOLVED_CONDITIONS = 7 and NON_NEGOTIABLE_CONDITIONS** — both are
patches over the same missing structure. The non-negotiable list exists
because scoring alone let obviously-wrong setups through, which is the
scoring model failing and being propped up rather than replaced. If the
checklist becomes gates, both constants disappear.

**MIN_IMPORTANT_DECLINE_PCT = 10.0** — 10% is the conventional
correction threshold, so not arbitrary, and its blast radius is small:
it only routes between target methods. Effectively untested, though,
since the swing rule fired on none of the last 15 tickers.

**MIN_RESOLVED_CONDITIONS = 7** — has some empirical basis, in that I
raised it from 6 after watching 6 admit a stock carrying three
unknowns. That is a single observation, and it is a hard gate on
whether anything gets a verdict at all.

**MAX_SENSIBLE_STOP_PCT = 15.0** — least trustworthy, per the decision
above.

## The thing all of this was calibrating doesn't beat the index (2026-07-28)

Worth stating at the top level rather than leaving implicit in the
per-parameter entries below. Measured over 100 mid-cap-or-larger names,
taking every signal, the method returns +0.9% to +2.4% a year over
2015-2026 and +1.2% to +3.3% over 2005-2026. Buying SPY and doing
nothing returned +12.4% and +10.4% respectively.

That reframes every threshold on this page. Tuning a parameter that
moves per-trade return by a fraction of a point is rearranging
something that is currently 8-10 points a year behind doing nothing at
all. It doesn't make the calibration work wrong — a correctly measured
parameter is still worth having — but it does mean no amount of it is
the missing piece.

The one component that clearly works is condition 6. See
[known-gaps.md](known-gaps.md): one trade entered in the entire 2008
decline, and a −9.7% worst drawdown against the index's −54.6%. The
method does what it says on crash avoidance. The open question is no
longer "does stage analysis work" but "is a mostly-cash portfolio with
occasional equity exposure worth running", and that is a question about
whether the low drawdown justifies a cash-like return.

## Standing caveats on any backtest number from this project

- Trades are concentrated: five tickers accounted for roughly half of
  both samples above.
- Every window tested so far sits inside a bull market. Nothing here
  has been exercised against a Stage 4 market, which is precisely when
  condition 6 is supposed to matter most.
- Median R is negative in both samples. The typical trade is a small
  loss and the edge lives in the tail, which is normal for this style
  but means headline averages are less stable than the trade count
  suggests.
- `simulate_trade` exits fully at the target, while the book uses that
  level for partial selling. Winners are therefore capped relative to
  the method being modelled.
