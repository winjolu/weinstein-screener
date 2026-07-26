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
