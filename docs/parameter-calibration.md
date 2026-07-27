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
no edge per unit of risk still has no edge per unit of risk when less
of it is taken. The justification fails by construction, independent of
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
It remains arbitrary — I picked it as a midpoint between the roughly
5-6% risk in the book's worked examples and the roughly 20% my own stop
placement produces on real tickers, two figures I never reconciled. It
is currently the binding constraint on condition 9, rejecting 13 of 15
tickers on a recent scan, so it is doing a great deal of work for a
number chosen that way.

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

## Other thresholds, ranked by how much I trust them

**ACTIONABLE_SCORE = 0.80** — most trustworthy of the set, because it
is anchored rather than invented: ceil(0.8 × 9) = 8 reproduces the
previous "8 of 9" rule exactly when every condition resolves, and it
degrades sensibly as conditions come back unknown. Scale-free.

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
