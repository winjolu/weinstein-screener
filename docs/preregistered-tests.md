# Pre-registered tests

Written **before** running anything, and committed so the timestamp
proves it. Results get appended below each entry; the specification
above the line is never edited afterwards.

## Why this file exists

By the time this was written I had already looked at every result in the
dataset — both study windows, the three parameter experiments, the
liquidity segmentation, the gate arms. That makes me an unreliable
source for "let's test whether X works", because I can no longer tell
whether X is a principled hypothesis or something I noticed in the
results and am about to confirm using the same data.

Pre-registration doesn't fix that. What it does is make it **bounded and
visible**: every rule to be tested is written down first, including the
ones expected to fail, so a success can be read as one-in-N rather than
arriving alone and looking decisive.

What it specifically prevents:

- **Moving the goalposts.** "+2%/yr doesn't beat the index but it's
  positive, so call it a partial win."
- **Metric shopping.** Computing six statistics and leading with the
  flattering one.
- **Silent tweaking.** 40% didn't work, try 37%, try 43%, until it does.
- **Hidden multiplicity.** Test twenty rules, report the one that
  passed. Roughly one in twenty passes by chance alone.

## Provenance matters more than the count

Each rule below is marked with where it came from, because that decides
how much my contamination matters:

- **`[book]`** — taken from the source text, which I read after the
  measurements were already done. These cannot have been fitted to the
  results, and are the strongest tests here.
- **`[structural]`** — a mechanical alternative (a different moving
  average, a curvature term) with no outcome data behind the choice.
- **`[data]`** — noticed in results I had already seen. Weakest, and
  flagged as such. Treat a pass here as a hypothesis for a future test,
  not as a finding.

---

## Design

**Universe.** Cached common stock (`bar_cache`, built 2026-07-28,
5,808 symbols), restricted to average weekly dollar volume ≥ $50M over
the trailing 12 weeks — the mid-cap-or-larger proxy used throughout, and
named as a proxy since there is no market-cap field. Names with
insufficient history contribute no trades until they list, which is
correct rather than something to filter.

**Split.** Derive on **2010-01-01 → 2020-12-31**, test on
**2021-01-01 → 2026-03-31**. Chosen because the test window is *harder*
than the derivation window (20.0% of weeks below the 30-week average
against 16.2%), which is the right direction — the reverse flatters an
out-of-sample result.

**Mechanics.** 4-week checkpoints, $1,000 per signal, every signal
taken, `trailing_method='ma'`, `fetch_sector=False` throughout. Sector
strength cannot resolve before ~2021 because daily bars cap at ~4.8
years, so **every arm runs an eight-condition checklist, in both
windows, for comparability.** This is a real departure from the live
tool and limits what these results say about the nine-condition version.

**Procedure.** All rules run on the derivation window. Rules are then
carried to the test window **once**, and the test window is not re-run
per variant. Any threshold a rule needs is fixed on derivation data
before the test run.

## Metrics, fixed in advance

Primary and secondary are both reported for every arm; neither is
selected after the fact.

1. **Primary — does it beat doing nothing.** Compound annual return on
   the test window, computed by `portfolio_sim.simulate_account`, against
   SPY buy-and-hold over the identical window. Reported on both peak and
   average capital, since peak alone is unfairly harsh and average alone
   is unachievable.
2. **Secondary — does it beat the current system.** Same figure against
   the unmodified baseline arm.

**Success is declared only if:**

- **(a)** the arm's CAGR on *average* capital exceeds SPY's over the test
  window — the generous end of the capital range, chosen deliberately so
  a failure here cannot be blamed on harsh accounting; **and**
- **(b)** the improvement over baseline survives resampling: bootstrap
  2,000 draws of the arm's test-window trades, and require the 5th
  percentile of the per-trade mean to exceed the baseline's median. A
  point estimate alone does not count.

**Failure** is anything else, including "improved but inside the
resampling noise". That case is explicitly a failure, not a partial win.

**Abandonment.** If no arm satisfies (a), the conclusion recorded is that
this method did not beat the index on this data, and the next step is a
different question, not another parameter.

---

## The rules

Every candidate is listed. None are added after results are seen.

### R1 — Baseline `[control]`
Unmodified current logic: nine conditions scored as a ratio,
`ACTIONABLE_SCORE = 0.80`, `MIN_RESOLVED_CONDITIONS = 7`, the three
existing non-negotiables. Not expected to beat SPY — it returned
+0.9% to +3.3%/yr in earlier runs against SPY's +10-14%. Present as the
comparison, not as a candidate.

### R2 — Hard gates instead of scoring `[book]`
Every resolved condition must pass; no ratio, no shortfall tolerated.
Unknowns do not block. Implemented as `ACTIONABLE_SCORE = 1.0`.

The book's buying process is a sequence whose steps discard candidates,
its don't-buy list is introduced as rules never to violate, and it poses
the 8-of-9 construction as a quiz question whose answer is no. **This is
the single most important test here** — the scoring model is the largest
departure from the source, and it was invented upstream of me.

Expectation: far fewer trades, higher win rate, uncertain total return.

### R3 — 15% stop-distance limit as a purchase gate `[book]`
Reject any setup whose initial stop sits more than
`MAX_SENSIBLE_STOP_PCT = 15` below entry, as a gate rather than as
condition 9. The book states this limit outright and frames it as a
constraint on which stocks may be bought.

Expectation: **fails.** Post-hoc filtering at 100 names cut profit from
+$2,729 to −$1,913 by removing 15 of the 18 best trades. Included
anyway, because it is the book's own rule and it deserves a fair test at
26× the sample — and because declaring an expected failure in advance is
what makes the successes here mean anything.

### R4 — Extension gate at entry `[data]`
`MAX_EXTENSION_ABOVE_MA_PCT = 40`, measured at the fill bar.

Expectation: **fails.** Already run at 100 names across both windows and
both thresholds; monotonically reduced returns every time. Listed to
keep the denominator honest.

### R5 — Extension-triggered partial profit-taking `[book]`
When a *held* position rises more than 40% above its 30-week average,
sell half and trail the remainder. The book gives this as the response to
a position that has run far above the average — take some off, ride the
rest. It is a different rule from R4 and applies to exits, not entries.

**The most promising untested idea in this batch**, because unlike every
filter tried so far it removes no trades, so it cannot destroy the
winners by excluding them.

### R6 — Trader's-way exits `[book]`
Tighter initial stop, do not wait for the 30-week average to be violated
before selling, exit on extended sideways action. The book describes
this as a distinct discipline from the investor's way, which is the only
one currently built.

Threshold for "sideways" fixed on derivation data before the test run,
and recorded here when set.

### R7 — Moving-average variant `[structural]`
Replace the SMA with a WMA, then an EMA, for the trailing stop and stage
classification. The book is inconsistent about which it means, and the
code already uses a WMA for slope direction while comparing price to an
SMA. Two arms.

### R8 — Curvature in stage detection `[structural]`
Add a second-derivative term: require the 30-week average's slope to be
*improving* over the prior 10 weeks for a Stage 1→2 transition, rather
than reading a single slope. This is the flattening-then-turning-up shape
the book describes, which the current single-slope read does not capture.

Supporting observation, not a result: on the last live scan 323 of 330
names classified as Stage 2 and only 2 as Stage 1, so the transition the
method exists to catch is essentially never observed.

---

## Standing caveats that no result here escapes

- **Survivorship.** Delisted names are unavailable — confirmed by
  testing, not assumed: their instrument records exist but every bar
  request returns `INVALID_SYMBOL`. All results are therefore biased in
  the strategy's favour, so a failure to beat the index is if anything
  understated.
- **Eight conditions, not nine**, for the reason given under Design.
- **No costs.** No commission, no slippage, no borrow. Rules with higher
  turnover — R6 especially — are flattered most by this.
- **One dataset.** Every arm shares a universe and a split, so the arms
  are correlated and a common-mode error would move all of them
  together.

---

## Results

*Nothing below this line until the runs are done. Appended, not edited.*

### Run 2026-07-29

**Universe** 2,627 mid-cap-or-larger names from the cache built
2026-07-28. **Derivation** 2010-01-01 to 2020-12-31, **test**
2021-01-01 to 2026-03-31, 4-week checkpoints, $1,000 a signal,
`fetch_sector=False`, eight conditions in both windows as specified.

**One correction to the instrument, made before the run and after the
spec was committed.** Fills now happen at the bar the signal fired on
rather than at the breakout bar. Scans find a breakout a median of four
weeks after it happens, so filling at the old level books a rise that had
already occurred — worth +1.11 points a trade on the earlier 273-trade
study, which was the whole of its measured edge. That is a bug in the
measuring instrument, not a change to any rule, and every arm below runs
with it fixed.

**Not run:** R6 (trader's-way exits) and R7 (moving-average variants)
need code that still doesn't exist. Recorded as not-yet-run rather than
dropped, so the denominator stays honest: six of eight arms were tested.

#### Derivation — SPY buy-and-hold +13.61%/yr

| arm | n | win | mean | peak/yr | avg/yr | short of index |
|---|---|---|---|---|---|---|
| R1 baseline | 6,151 | 40.1% | +1.84% | +1.95% | +4.57% | 9.0 pts |
| R2 hard gates | 915 | 39.5% | +1.75% | +1.15% | +4.07% | 9.5 pts |
| R3 stop-15% gate | 3,882 | 39.1% | +1.42% | +1.57% | +3.93% | 9.7 pts |
| R4 extension gate | 5,598 | 39.8% | +1.50% | +1.59% | +3.89% | 9.7 pts |
| R5 take-profit | 6,151 | 39.9% | +1.33% | +1.44% | +3.50% | 10.1 pts |
| **R8 curvature** | 4,559 | **41.7%** | **+2.23%** | +2.10% | **+4.94%** | 8.7 pts |

#### Test, out of sample — SPY buy-and-hold +11.78%/yr

| arm | n | win | mean | peak/yr | avg/yr | short of index |
|---|---|---|---|---|---|---|
| R1 baseline | 3,804 | 37.7% | +1.10% | +1.24% | +3.47% | 8.3 pts |
| R2 hard gates | 325 | 37.8% | +0.14% | +0.12% | +0.44% | 11.3 pts |
| R3 stop-15% gate | 1,521 | 33.9% | +0.19% | +0.24% | +0.72% | 11.1 pts |
| R4 extension gate | 3,052 | 36.1% | +0.10% | +0.13% | +0.36% | 11.4 pts |
| R5 take-profit | 3,804 | 36.4% | **−0.12%** | −0.14% | −0.41% | 12.2 pts |
| **R8 curvature** | 2,798 | 39.1% | **+1.29%** | +1.42% | **+3.86%** | 7.9 pts |

### Verdict: every arm FAILS criterion (a)

Not narrowly. The best arm is short of simply buying the index by 7.9
points a year, out of sample, on 2,798 trades. Criterion (a) is decisive
and no arm comes close.

**The abandonment condition is met.** As written above: the conclusion
recorded is that this method did not beat the index on this data, and the
next step is a different question rather than another parameter.

### What the arms actually showed

**The baseline beat four of the five modifications.** Including both
rules taken directly from the book. R2 — hard gates, the structure the
source actually describes and the change I argued was most important —
cut trades by 91% and returned +0.44% a year against the baseline's
+3.47%. Restoring the book's own structure made it worse.

**R5 was the one I expected to work and it was the worst arm.** The
reasoning was that it changes exits rather than removing trades, so
unlike every filter it couldn't destroy the winners by excluding them.
It destroyed them anyway, by capping them: banking half a position at 40%
above the average takes the runners off precisely when they are running.
Out of sample it turned a +1.10% average trade into −0.12%.

**R8 was the only arm to improve on the baseline, and it did so in both
windows** — +0.37 points a year in derivation, +0.39 out of sample, with
a higher win rate in both. Consistent direction across an out-of-sample
split is worth more than a larger one-off gain. But it is not
significant: R8's bootstrap 5th percentile (+0.45%) sits below the
baseline's mean (+1.10%), so the improvement cannot be distinguished from
noise even at this sample size. And 0.4 points does not touch a 7.9-point
deficit.

### Correction to criterion (b)

As registered it compares a resampled *mean* against the baseline's
*median*. These returns are heavily skewed — test-window median −3.84%
against a mean of +1.10% — so that bar is cleared by almost anything.
Every arm passed (b) as written, including arms returning near zero. The
criterion was close to vacuous.

It changes no verdict, because (a) fails for every arm. But it was
specified in advance, it was wrong, and it is recorded rather than
quietly restated. A correct version compares mean to mean, under which
no arm passes either.

### What this does and does not establish

It does **not** show stage analysis doesn't work. It shows *this
implementation*, on this universe, over these windows, with eight
conditions and no transaction costs, returned 3-4% a year where the index
returned 11-14%.

The standing caveats all point the same way: survivorship bias favours
the strategy, no costs are modelled, and condition 5 was unavailable
throughout. Removing those would widen the gap.

The one thing measured here that clearly works is unchanged: condition 6
kept the method out of the 2008 decline almost entirely, with a −9.7%
worst drawdown against the index's −54.6%. The method is defensive and
the defence is real. On this evidence it is not a way to make money
relative to owning the index, and the low drawdown is what it buys in
exchange for roughly a third of the return.

---

## Batch 2 — registered 2026-07-29, after the first batch failed

The first batch established that no variation of the *existing* logic
beats the index. What it also showed, and what this batch responds to,
is where the failure actually sits. Across the 2021-2026 window the
system traded 1,168 stocks that rose more than 20% — averaging +270% —
and captured 5.0% of that. A 2% capture rate. On the 455 that fell more
than 20%, averaging -58%, it lost 2.4%.

That is not a system picking the wrong stocks. It is a system that is
very good at not losing money and nearly incapable of making any. The
first batch varied entry filters, which is the half that was already
working.

`[defect]` marks a rule addressing a measured failure of the
implementation rather than a reading of the book. Weaker provenance than
`[book]` but stronger than `[data]`: the defect was measured, the fix is
a hypothesis about it.

### R9 — Loosen the trailing stop `[book]` `[defect]`
`MA_STOP_BUFFER_PCT`, placing the trailing stop a set distance *below*
the 30-week average rather than exactly on it.

The book says to place the stop below the average, and separately that
while price is above a rising average in Stage 2 the position should be
given plenty of room to gyrate. This code put the stop on the line, so
any pullback that touches it closes the position. GOOGL is the case in
miniature: bought 280.64, stopped at 286.01 for +1.9%, then ran to 400.

Sweep 0 (current), 5, 10, 15%.

### R10 — Weekly checkpoints `[defect]`
`check_interval_weeks=1` instead of 4. The screener found GOOGL's
breakout four weeks late and refused SNDX through a 55% advance while
reporting conditions unresolved. Cheapest possible test of entry lag.

### R11 — Continuation entries `[book]` `[defect]`
`CONTINUATION_ENTRY_MAX_PCT_ABOVE_MA`, admitting a stock already in
Stage 2 that has pulled back near its rising average, without requiring
a fresh breakout.

The book describes this as the trader's re-entry — sell well above the
average, repurchase on dips back toward it. Only breakout entries exist
today, which is why a stop-out is usually terminal: mid-trend there is
no resistance left for condition 7 to confirm. Median 2 trades per stock
across five years.

Sweep 10, 20, 30%.

### R12 — The short side `[book]`
`short_conditions.py`. Not the long checklist inverted — the book's
asymmetries are implemented explicitly: volume is never a gate on a
breakdown (only a bonus), the preferred entry is the rally back to the
broken level on light volume, and stage alone justifies a short with no
fundamental input existing at all.

Measured on its own and combined with the long side, since the case for
it is that capital sits idle through declines.

### Success criteria — unchanged, with (b) corrected

Criterion (a) stands exactly as before: CAGR on average capital must
exceed SPY's over the test window.

Criterion (b) is corrected to compare the arm's bootstrap 5th percentile
against the baseline's **mean**, not its median. As originally written it
compared a resampled mean to a median and was cleared by almost anything;
that error is recorded above rather than hidden, and this is the fix.

**Same abandonment condition.** If no arm satisfies (a), the answer is
that this doesn't beat the index and the next question is a different one.

### Results

*Nothing below this line until the runs are done.*

---

## Batch 3 — registered 2026-07-29, after R9 failed

R9 loosened the trailing stop and made things monotonically worse:
+1.84% a trade on the line, −0.11% at 5% below, −3.26% at 10%, −7.74% at
15%, with the win rate collapsing from 40% to 20%. The prediction was
that a looser stop would let winners run. It didn't.

The trade counts explain why, and they point somewhere else. Loosening
took the count from 6,151 to 692, because a position that stays open
blocks later checkpoints on the same ticker. The stop wasn't holding
winners longer — it was holding *losers* longer and losing more on each.

### R13 — Maximum holding period `[defect]`
`max_hold_weeks`, currently 52. Every trade is force-closed after a
year no matter what price is doing. A stock trending for three years is
cut at one, and no stop setting can reach that — which makes it a better
candidate than R9 was for the 2% capture rate, and a different mechanism
entirely.

Sweep 52 (current), 104, 156, and effectively unlimited (520).

**Expectation, recorded before running:** genuinely uncertain, and I want
that on the record given the run of wrong calls. The argument for is that
a year is arbitrary and the method is explicitly about multi-year
advances. The argument against is that R9 also looked obviously right and
wasn't — and longer holds have the same checkpoint-blocking side effect
that made R9 worse, so this could fail the same way for the same reason.

If it fails, the shared mechanism becomes the finding: any change that
keeps positions open longer reduces trade count faster than it improves
per-trade return, and that is a property of the harness rather than of
the market.

### Criteria
Unchanged from batch 2, including the corrected (b).

### R14 — Weekly checkpoints with a long maximum hold `[defect]`
`check_interval_weeks=1` and `max_hold_weeks=520` together.

Registered **before** R13 reports, and specified as a fixed pair rather
than "weekly plus whatever hold turns out best" — the latter would be
choosing the combination after seeing which half worked, which is the
thing this file exists to prevent.

The two address opposite ends of the same diagnosis. Weekly checkpoints
attack entry lag, which is the half already confirmed: R10 improved on
the baseline in derivation on every measure (+2.46% a trade against
+1.84%, 41.5% win against 40.1%, nearly double the total). A long hold
attacks the forced exit, which is the remaining untested candidate for
the 2% capture rate.

If R13 fails on its own, this arm still runs as registered. A
combination can behave differently from either part, and dropping it
after seeing a disappointing single would be the same selective
reporting in reverse.

### Derivation results so far, recorded before the test window returns

| arm | n | win | mean | avg/yr |
|---|---|---|---|---|
| R10 weekly checkpoints | 8,940 | 41.5% | **+2.46%** | **+5.55%** |
| R1 baseline | 6,151 | 40.1% | +1.84% | +4.57% |
| R11 continuation entries | 8,134 | 39.6% | +1.45% | +3.67% |
| R9 stop 5% below | 3,469 | 35.6% | −0.11% | −0.28% |
| R9 stop 10% below | 2,310 | 28.9% | −3.26% | −18.99% |
| R9 stop 15% below | 1,771 | 23.3% | −6.25% | −100.00% |

R10 is the only arm across both batches to improve the baseline by a
margin worth the name, and it is the cheapest change of any tested —
look weekly instead of monthly.

R11 fires rather than sitting inert (4,220 trades unique to it, 2,107
displaced) and still underperforms, which answers the re-entry question
directly: re-entry is available, it just isn't profitable. Worth noting
the book pairs that re-entry with the trader's tighter stops and faster
exits, and it has been implemented here inside the investor's framework.
That is a caveat on the finding, not a rescue of it.

### Batch 2 results — test window, 2021-2026 (SPY +11.78%/yr)

| arm | n | win | mean | avg/yr | vs index |
|---|---|---|---|---|---|
| R1 baseline | 3,804 | 37.7% | +1.10% | +3.47% | −8.3 |
| R9 stop 5% below | 2,906 | 37.1% | −0.21% | −0.53% | −12.3 |
| R9 stop 10% below | 2,242 | 32.0% | −3.09% | −8.59% | −20.4 |
| R9 stop 15% below | 1,778 | 28.0% | −5.94% | −20.02% | −31.8 |
| R11 continuation | 4,993 | 37.5% | +0.73% | +2.35% | −9.4 |
| R10 weekly | *invalidated — see below* | | | | |

**All arms fail criterion (a).** R9 fails monotonically in both windows,
so its failure is real rather than a fluke of one period. R11 fails in
both windows while demonstrably firing (2,067 trades unique to it out of
sample, 4,220 in derivation), so re-entry on a pullback without a fresh
breakout is genuinely a weaker setup rather than an unimplemented one.

**R10's test arm was invalid and is being re-run.** The harness used
`kwargs.pop()` against a module-level arm list; the derivation phase
consumed `check_interval_weeks=1`, so the test phase fell back to 4 and
the arm ran as the baseline, reporting byte-identical figures. Recorded
here rather than silently re-run, because the alternative was reporting
that the one promising change failed out of sample — a plausible,
clean, entirely false finding.

---

## Batch 4 — volume, registered 2026-07-29

All four run on top of R14's configuration (weekly checkpoints, no
maximum hold), because R14 is the current best out-of-sample arm at
+7.07%/yr and the useful question is whether volume improves *that*, not
whether it improves a configuration already superseded.

**What the book actually says.** It opens by rejecting any "magic level"
of volume — no randomly picked multiple — and then gives twice the
average as its working figure. So the current `VOLUME_CONFIRM_RATIO =
2.0` is sourced rather than invented, like the 15% stop limit was.

What it also gives, and what was never implemented, is a **second
acceptable pattern**. Either:

  A. a one-week spike of at least twice the past month's average, **or**
  B. a build-up over three to four weeks at twice the prior average,
     coupled with at least *some* increase on the breakout week.

Only A existed. A stock accumulating volume through its base and then
breaking out on a modest bump satisfied the book and failed this code.

### V1 — Lower threshold, 1.5x `[data]`
`VOLUME_CONFIRM_RATIO = 1.5`. Departs from the book's stated figure.

### V2 — At or above average, 1.0x `[data]`
`VOLUME_CONFIRM_RATIO = 1.0`. Volume merely not falling.

### V3 — No volume requirement `[data]`
`VOLUME_CONFIRM_RATIO = 0.0`, so condition 3 never fails at a breakout.
The book is explicit that a breakout without a significant volume
increase should be avoided, so this is registered as a control on how
much work the condition does, not as a candidate.

### V4 — The book's build-up pattern `[book]`
`VOLUME_BUILDUP_WEEKS = 4`, admitting pattern B alongside pattern A.
Stronger provenance than V1-V3: it implements something the source
states and this code omitted, rather than moving a number the source
supplies.

**Expectation, recorded first:** V4 should admit more trades without
loosening the standard, since it adds a route the book endorses rather
than lowering the bar. V1-V3 should degrade progressively if the volume
condition is carrying real information, and do nothing if it isn't —
either outcome is informative. Given six wrong predictions tonight I
hold all of this loosely.

### Criteria
Unchanged, and compared against R14 rather than R1 since that is the
base these are built on.

---

## Batch 4 — pattern-mined rule, registered 2026-07-29 before any holdout run

This batch is different in kind from the others and is labelled
accordingly. Everything above was a hypothesis from the book or from a
measured defect. This is **mined from the data**, deliberately,
after I concluded that my original objection —
an n of 3 winners — no longer applies at 415 winners above +25%.

**What I did.** Extracted 13 features for all 6,151 derivation trades,
computed only from bars up to the entry date so a rule built on them is
one the screener could actually have applied. Ranked each feature by
quintile against realised return, then tested combinations.

**How many things I tried, stated up front:** 13 single features by
quintile, 8 single-threshold filters, 4 combinations. **25 looks.** At
that count roughly one in twenty passes at 5% by chance, so an
unreplicated result here means very little on its own.

### What the mining found

Only two features are monotonic across quintiles, which is the shape a
real relationship takes rather than a lumpy one:

| feature | Q1 → Q5 mean return | monotonic |
|---|---|---|
| Mansfield relative strength | +0.61% → +3.62% | yes |
| % below the 52-week high | +1.09% → +3.66% | yes |
| base width | +0.85% → +3.86% | nearly |
| **volume ratio at entry** | +2.21% → +2.00% | **no, and flat** |
| **conditions met (the checklist itself)** | +1.33% → +1.18% | **no, and flat** |

Two of those deserve saying plainly. **The checklist score does not
predict outcome** — trades scoring 7 did no better than trades scoring
6. And **being further below the 52-week high predicts better returns**,
which is the opposite of buying strength at new highs.

### R15 — the mined rule `[data]`

Enter only when all three hold at the signal bar:

- Mansfield relative strength **> 20**
- price **> 7% below** its 52-week high
- base range **> 35%** wide

Thresholds rounded outward from the fitted quintile edges (20.8, 7.9,
36.1) deliberately, since exact edges are the most overfitted point
available.

**Derivation performance:** 319 trades, 46.7% win, **+9.17% a trade**
against the baseline's +1.84%. A five-fold improvement, which is
precisely the magnitude that should trigger suspicion rather than
excitement.

### The holdout

**2005-01-01 to 2009-12-31**, 1,257 mid-cap names with history reaching
that far. I have never run a query against this period, never read a
result from it, and it is the only genuinely uncontaminated data in the
project. It also contains the 2008 crash, so it is a hard test rather
than a friendly one.

**Success:** the rule's mean return on the holdout exceeds the
unfiltered baseline's on the same holdout, by a margin surviving a
bootstrap at the 5th percentile.

**Expectation, recorded now:** I expect this to shrink substantially.
A five-fold improvement found across 25 looks on one decade is far more
likely to be a description of 2010-2020 than a property of markets. If
it holds even at half strength on 2005-2009 including a crash, that is
a real finding.

---

## Batch 5 — registered 2026-07-29, built from what measures rather than what's written

My framing changed here and the batch reflects it: I am not
committed to the book, so deviations that survive the data are to be
followed and flagged rather than argued down.

Two measurements drive this batch, both from testing each condition
separately against realised return over 6,151 derivation trades:

| condition | passes | fails | edge |
|---|---|---|---|
| resistance_breakout | +1.75% | −0.80% | **+2.56** |
| pullback_quality | +1.85% | +1.55% | +0.30 |
| **volume_confirmation** | +1.84% | +1.84% | **+0.01** |
| **risk_reward** | +1.50% | +2.26% | **−0.76** |

**Volume confirmation carries no information** — identical to two
decimals whether it passes or fails. Not a threshold that needs
adjusting; a condition that measures nothing. That is a flat
contradiction of the book, which calls the volume signal vital.

**Risk/reward is inverted.** Trades that fail it return more. The 15%
stop ceiling — the book's own explicit purchase rule — selects against
winners, now on a fourth independent measurement.

The other five never vary inside the trade set, three because they are
hard gates a trade cannot exist without. That is a selection artifact,
not evidence they work, and testing them needs removal rather than
scoring. **Recorded as a real gap: we have never tested whether
requiring price above the 30-week average helps.**

### R16 — drop volume confirmation `[data]`
`DISABLED_CONDITIONS = ("volume_confirmation",)`

### R17 — drop the risk/reward ceiling `[data]`
`DISABLED_CONDITIONS = ("risk_reward",)`

### R18 — drop both `[data]`

### R19 — the mined filter alone `[data]`
`MINED_ENTRY_FILTER = True`. Relative strength > 20, price > 7% below
its 52-week high, base > 35% wide. Already replicated across three
windows; run here as a gate inside the live engine rather than as
post-hoc filtering, which is a different and stricter test — the filter
now changes which trades are *taken*, so it also changes what later
checkpoints are free to enter.

### R20 — everything that has measured positive `[data]` `[defect]`
Mined filter, both dead conditions dropped, weekly checkpoints, and no
one-year hold cap. Every component independently improved results;
this asks whether they compound or interfere.

Registered as a fixed combination before any of it runs, not assembled
afterwards from whichever parts looked best.

### Criteria
Unchanged. Criterion (a) — beat the index on average capital — plus the
corrected (b) against the baseline's mean. Reported on **all three
windows**, with 2005-2009 carrying the most weight since it is the only
period never used to derive anything.

**Expectation:** R19 and R20 improve per-trade return substantially, on
the strength of the replication already seen. Whether they beat the
index on *peak* capital is the open question — the mined filter is
highly selective, and selectivity leaves capital idle.

---

## Batch 7 — do the hard gates earn their place? Registered 2026-07-29

Three conditions never vary inside the trade set — `stage_setup`,
`price_above_ma`, `market_stage` — because a trade cannot exist unless
they pass. Their constancy has been recorded throughout as a selection
artifact rather than evidence they work, and testing them needs them
*removed*, not scored.

**We have never checked whether requiring price above the 30-week
average helps.** It is the most load-bearing assumption in the project
and it is entirely untested. Same for the market-stage read, which is
the one component with a demonstrated benefit (it kept the method out of
2008) but has never been measured against the cost of the trades it
refuses.

Each arm removes one condition from `NON_NEGOTIABLE_CONDITIONS`, leaving
it in the ratio. So the question is precisely "does this need to be a
veto, or is being one voice among several enough?"

Base configuration is weekly checkpoints with no hold cap — the
best-measured setup so far, so these test the gates on the system we
would actually run rather than on the original baseline.

### G1 — price_above_ma not a veto `[structural]`
### G2 — market_stage not a veto `[structural]`
### G3 — stage_setup not a veto `[structural]`
### G4 — none of the three a veto `[structural]`

Run on all three windows.

**Expectation:** G2 loosens the crash protection, so I expect it to look
fine in the two bull windows and worse in 2005-2009 — which would be the
first result where a component's value shows up only in the period that
contains a crash. If that pattern appears it is worth more than the
arithmetic, because it is the shape the whole method claims to have.

G1 I genuinely don't know. Every other "obvious" gate tested tonight has
either done nothing or hurt.

### Batch 5 results — two windows in, one still running

**Holdout 2005-2009 (SPY +0.80%/yr, never used to derive anything)**

| arm | n | win | mean | peak/yr | avg/yr |
|---|---|---|---|---|---|
| baseline | 1,753 | 38.8% | +1.59% | +1.53% | +4.70% |
| R16 drop volume | 598 | 38.5% | +1.23% | +1.02% | +3.66% |
| R17 drop risk/reward | 1,483 | 43.8% | +3.56% | +3.65% | +8.76% |
| R18 drop both | 5,711 | 39.7% | +2.01% | +2.75% | +5.88% |
| R19 mined filter | 151 | 45.7% | +6.42% | +3.68% | +14.48% |
| **R20 all combined** | 1,530 | 42.0% | **+7.87%** | **+4.57%** | **+15.69%** |

**Derivation 2010-2020 (SPY +13.61%/yr)**

| arm | n | win | mean | peak/yr | avg/yr | vs index |
|---|---|---|---|---|---|---|
| baseline | 6,151 | 40.1% | +1.84% | +1.95% | +4.57% | −9.0 |
| weekly + no cap | 10,898 | 44.2% | +4.55% | +4.15% | +7.72% | −5.9 |
| R17 drop risk/reward | 4,902 | 42.1% | +1.85% | +1.75% | +4.41% | −9.2 |
| R19 mined filter | 542 | 44.3% | +6.18% | +3.15% | +10.73% | −2.9 |
| **R20 all combined** | 3,578 | 41.8% | **+9.07%** | **+4.99%** | **+12.95%** | **−0.7** |

### What these show

**The components compound rather than interfere.** R20 beats R19 on
per-trade return in both windows while taking six to ten times as many
trades. Selectivity was the mined filter's weakness — 151 trades over
five years leaves capital idle — and pairing it with weekly checkpoints
fixes that without diluting the edge.

**The risk/reward ceiling is harmful specifically in falling markets.**
Dropping it improves 2005-2009 from +1.59% to +3.56% a trade and does
nothing at all in 2010-2020 (+1.84% to +1.85%). That is the shape a
component's value is supposed to have — visible only in the window that
contains a crash — appearing for a rule the book states as protective.
It is not neutral; it hurts precisely when it is meant to help.

**Volume removal alone is worse than baseline** (+1.23% against +1.59%)
while removing both is better (+2.01%). So the gain comes from the
risk/reward ceiling, not from volume — consistent with volume measuring
no edge in either direction.

**Still short of the index in a bull window.** R20 closes the gap from
−9.0 to −0.7 points in 2010-2020, which is near parity rather than a
pass. Criterion (a) has not been met in any window where the index
compounded normally. The 2005-2009 result flatters every arm because
the index returned +0.80% there.

---

## Batch 8 — is the mined rule a plateau or a knife edge? Registered 2026-07-29

R20 passed both criteria out of sample (+11.99%/yr against SPY's
+11.78%, bootstrap p5 +3.38% against the baseline's +1.10% mean). The
mined filter carries most of that.

The filter's thresholds — relative strength > 20, price > 7% below the
52-week high, base > 35% wide — were rounded outward from fitted
quintile edges (20.8, 7.9, 36.1). **Rounding outward is not the same as
being insensitive to the values.** If the rule only works at those exact
settings it is a fitted curve wearing a rule's clothing; if it works
across a broad range it is describing something real about markets.

**This is the test I would weight most heavily before treating any of
this as tradeable**, more than another window would add.

### Design
One threshold varied at a time from the centre (20 / 7 / 35), holding
the other two fixed. Full R20 configuration otherwise — dropped
conditions, weekly checkpoints, no hold cap — so this measures
sensitivity of the system as it would actually run.

| arm | RS | below high | base |
|---|---|---|---|
| S0 centre | 20 | 7 | 35 |
| S1 | **15** | 7 | 35 |
| S2 | **25** | 7 | 35 |
| S3 | 20 | **5** | 35 |
| S4 | 20 | **10** | 35 |
| S5 | 20 | 7 | **30** |
| S6 | 20 | 7 | **40** |

All three windows.

### How to read it
**Plateau** — returns stay materially above baseline across every
variant. The rule survives; the exact numbers don't matter much.

**Knife edge** — the centre wins and neighbours collapse toward
baseline. Then it is fitted, the out-of-sample passes were luck of the
threshold, and it should not be traded.

**Monotonic drift** — performance climbs steadily with one threshold,
meaning the true optimum lies outside the range tested and the rounding
was in the wrong direction. Would need a wider sweep, registered
separately, before believing any single setting.

**Expectation:** genuinely uncertain, which is why it is worth running.
The rule replicated across three windows, which argues real. It was also
selected from 25 looks, which argues fitted. Sensitivity is what
separates those two stories.

### Robustness checks on R20 — not registered in advance, and labelled as such

Two diagnostics run after the fact. They test the *result* rather than
propose a rule, so they can't be p-hacked in the usual way, but they
were not pre-specified and are recorded here as post-hoc.

**Concentration.** The baseline's entire profit came from 25 trades out
of 3,804 — the top 25 account for 102% of it, so removing them turns it
negative. That is why every filter tested earlier destroyed returns:
each was removing one of a handful of trades carrying everything.

| share of total profit | baseline | R20 |
|---|---|---|
| top 3 trades | 36% | 13% |
| top 10 | 63% | 29% |
| top 25 | 102% | 51% |

R20 is materially less concentrated. It keeps a fat right tail without
depending on a few lottery tickets.

**Split-half by name.** Tickers split randomly into two disjoint sets,
each arm scored separately:

| | half A | half B |
|---|---|---|
| baseline | +1.30% | +0.90% |
| R20 | +4.63% | +4.32% |

Both R20 halves land within 0.3 points on roughly 1,900 trades each. The
effect reproduces on two independent groups of stocks, which is a fourth
replication alongside the three time windows.

**What this does not address.** Split-half stability says nothing about
threshold overfitting — a threshold fitted to a period reproduces across
both halves of that same period perfectly well. Batch 8 remains the test
that decides whether the mined filter is real or fitted.

---

## Batch 10 — R21, the two strongest parts without the rest. Registered 2026-08-02

R20 changes four things at once and passed. That leaves it unclear how
much of the pass came from the two components that measured best on
their own — the mined entry filter (R19) and dropping the risk/reward
ceiling (R17) — versus the two scheduling changes bundled with them
(weekly checkpoints, no hold cap).

### R21 — mined filter + drop risk/reward `[data]`
`MINED_ENTRY_FILTER = True`, `DISABLED_CONDITIONS = ("risk_reward",)`,
weekly checkpoints and no hold cap held at the R20 setting so the only
difference from R20 is that volume confirmation stays *in*.

Registered as a decomposition, not a search. If R21 matches R20, then
volume confirmation is confirmed inert for a third time and the simpler
rule should be preferred. If R21 is clearly worse, dropping volume was
carrying more than the per-condition analysis suggested, and that
analysis needs revisiting.

**Expectation:** R21 lands within noise of R20. Volume measured +1.84%
either way at the condition level and has never moved a result since.

### Criteria
Unchanged: average-capital return against buy-and-hold, plus the
bootstrap p5 against the baseline mean, reported on all three windows.

---

## Batch 11 — the short side, re-run against the corrected floor. Registered 2026-08-02

The original short backtest produced 123 trades. At the time I read
that as the short setup simply being rare. It is now more likely an
artifact: the same evidence-floor arithmetic that silently made R18 and
R20 un-qualifiable was in force, and the short module has *fewer*
resolvable conditions than the long side to begin with — no fundamental
input exists for it at all, so it starts closer to the floor.

### S7 — short side with the adaptive floor `[defect]`
Re-run the short backtest unchanged except that
`_effective_resolved_floor()` governs qualification. No threshold is
being tuned; this asks whether the original 123 trades were a real
scarcity or a starved sample.

**Expectation:** trade count rises substantially. Per-trade return is
genuinely unknown — a starved sample is not biased in a predictable
direction, so this could go either way, and a larger sample that
performs *worse* is a perfectly plausible outcome worth reporting as
loudly as a good one.

**Standing caveat, unchanged.** Short results carry an execution cost
this engine does not model: borrow fees, hard-to-borrow names, and the
possibility of a forced buy-in. Any positive short result should be
discounted for that before it means anything, and I should not treat a
marginal short edge as tradeable.

---

## Batch 7 results — the vetoes are redundant, not wrong

Complete on both windows that have a matched reference arm. The
2005-2009 reference is what batch 9 exists to supply, so the holdout is
not scored here.

A note on how nearly this went wrong: I read G4 mid-run at 1,764 trades
and it looked like a serious bug, because removing every veto is a
strict relaxation and cannot *lose* 9,138 trades. It was an unfinished
arm. Polling the count twice caught it.

2010-2020, weekly checkpoints, no hold cap. SPY returned +13.61%/yr.

| arm | trades | added | removed | win | mean | avg capital |
|---|---|---|---|---|---|---|
| all three vetoes (reference) | 10,898 | — | — | 44.2% | +4.55% | +7.72% |
| no price-above-MA veto | 10,898 | 0 | 0 | 44.2% | +4.55% | +7.72% |
| no market-stage veto | 10,904 | 16 | 10 | 44.3% | +4.56% | +7.72% |
| no stage-setup veto | 10,898 | 0 | 0 | 44.2% | +4.55% | +7.72% |

And on the test window, 2021-2026, SPY +11.78%/yr:

| arm | trades | added | removed | win | mean | $100k account |
|---|---|---|---|---|---|---|
| all three vetoes (reference) | 5,923 | — | — | 39.2% | +2.70% | +7.26%/yr |
| no price-above-MA veto | 5,923 | 0 | 0 | 39.2% | +2.70% | +7.26%/yr |
| no market-stage veto | 5,929 | 11 | 5 | 39.2% | +2.70% | +7.39%/yr |
| no stage-setup veto | 5,923 | 0 | 0 | 39.2% | +2.70% | +7.26%/yr |
| **no vetoes at all** | 5,929 | 11 | 5 | 39.2% | +2.70% | +7.39%/yr |

Removing the price-above-MA veto changes the trade set by **zero
trades**, in both windows. Same for stage-setup. Removing the
market-stage veto changes 16 entries out of 10,898 on derive and 11 of
5,923 on test.

The G4 arm settles the mechanism: removing **all three** vetoes gives
exactly the same trade set as removing the market-stage veto alone — 16
added and 10 removed on derive, 11 and 5 on test, identical to the
last decimal on every statistic. The other two vetoes are not merely
weak, they never bind at all. Only market-stage ever rejects anything
the scoring ratio would have accepted, and it does so about one time in
seven hundred.

Two identical arms would normally mean a broken experiment under the
standing rule, and that was checked first: the patch asserts, and the
scorer reads the veto list at call time rather than binding it as a
default. The result is real, and there is a mechanism for it. A stock
that fails one of these gates almost always fails others — a stock below
its 30-week average is rarely in a Stage 2 setup — so the 80% scoring
ratio already rejects it on count. The veto is a second lock on a door
the first lock had shut.

**What this does and does not say.** It does not say the conditions are
worthless; they may be doing their work through the ratio. It says their
*special status* is unearned. Three conditions have been described
throughout this project as non-negotiable, and on the evidence they
could be demoted to ordinary voters without changing what the system
buys. That is one fewer piece of structure to justify, and it removes a
place where I had assumed rather than measured.

It also explains a nagging observation. These three conditions never
vary inside the trade set — always True, every trade. I had recorded
that as a selection artifact of the veto. It is now clear the ratio
would have produced the same constancy on its own.

---

## Batch 12 — R6 at last, the exit that sells on time. Registered 2026-08-02

R6 was registered in the first batch and never ran, because the code to
sell on elapsed time did not exist. It does now
(`simulate_trade(stall_exit_weeks=...)`), and the case for it has grown
rather than shrunk: every other exit in the engine waits for price to
reach a level, so a position that simply goes sideways holds capital
indefinitely — and R20, the best rule measured so far, removes the
one-year hold cap entirely. R20's own weakness is that it leaves capital
committed; this is the mechanism that would free it.

### R6a / R6b — stall exit at 13 and 26 weeks `[book]` `[structural]`
On top of the full R20 configuration. A position still open after 13
(respectively 26) weeks that has not cleared 0% is sold at that week's
close. R20 itself runs alongside as a matched control.

Two settings, not a sweep, and declared as two: one quarter and one half
year, chosen because they are the obvious round intervals and not
because anything was measured at either. If both fail, R6 fails. If one
works and the other does not, that asks for a registered sweep rather
than adopting the winner.

**Expectation:** higher return on *average capital* — the metric that
penalises idle money — and a *lower* mean per trade, because the
positions being cut are ones that might have recovered. Those two moving
in opposite directions is the expected signature, and if mean per trade
also rises I should be suspicious rather than pleased.

**The trap this could fall into.** Cutting flat positions raises win
rate arithmetically by removing trades that were going to lose slowly.
Win rate is therefore not evidence here, and the criteria stay what they
have been: average-capital return against buy-and-hold, and the
bootstrap p5 against the baseline mean.

---

## The fixed-capital result, and what it does to R20's pass

Not a registered test. It is a correction to how every result in this
file has been measured, found by building the account simulation that
should have existed before any of the criteria were written.

### The problem with both existing denominators

`simulate_account()` takes every signal and reports the answer twice.
**Peak capital** sizes the account for the single busiest week in a
decade — R20 needed $589,000 on hand in the test window. **Average
capital** divides by the money actually working over calendar time,
which is the optimistic end, because nobody can hold the average and
still fund the peak.

Criterion (a) throughout this file — beat the index — has been scored on
average capital. R20 passed it out of sample at +11.99%/yr against SPY's
+11.78%. That pass is now in question, because neither denominator is
what happens to a real account.

### What a real account does

`simulate_fixed_capital()` starts with a fixed sum, stakes $1,000 per
signal as signals arrive, and misses the rest when the cash runs out.
Missing signals is not a modelling choice; it is what finite money
means. Idle cash earns a yield — 0.5% through the 2010s, 4% since 2022 —
because charging the strategy nothing on a book that is often half in
cash, while comparing it to a fully-invested index, is a real cost it
would not actually bear.

| account | R20 2010-2020 | R20 2021-2026 |
|---|---|---|
| $25,000 | +11.27% | +11.46% |
| $50,000 | +12.62% | +8.53% |
| $100,000 | +10.35% | +10.17% |
| $250,000 | +6.92% | +8.72% |
| **buy and hold SPY** | **+13.61%** | **+11.78%** |

**R20 does not beat buying the index at any account size, in either
window.** The closest it comes is $50,000 over 2010-2020, a point short,
and $25,000 over 2021-2026, a third of a point short. It still beats the
baseline everywhere, so the *relative* findings in this file stand. The
absolute one does not.

### Why the small accounts look better, and why that is not encouraging

A $25,000 account misses 86% of signals in the test window. Its return
is therefore decided by which handful of trades it happened to fund, and
that shows up directly in the seed spread: 8.47 points between the best
and worst arbitrary tie-break, against 0.26 points at $250,000. The
small-account figures are not a finding about the strategy. They are
noise with a plausible mean.

The larger the account, the more of the strategy actually gets run — and
the more of it gets run, the worse it does. That is the shape of a rule
whose good trades are scarce relative to how many signals it emits.

### What I got wrong

The criterion was chosen before the tool existed to measure the thing it
was standing in for, and it flattered the result. R20's out-of-sample
pass was real against the criterion as written, and the criterion was
not good enough. I am recording this rather than restating the pass,
because the pass is what I reported.

Future results should lead with the fixed-capital figure at a stated
account size, with the seed spread beside it. Average capital stays as a
secondary number for comparing arms against each other, which is the
one thing it is genuinely good for.

---

## Batch 13 — which signals get funded? Registered 2026-08-02

The fixed-capital result changes the question. R20 emits about 3,900
signals in the test window and a $25,000 account can fund 14% of them,
so the account's return is decided mostly by *which* ones it funds — the
seed spread is 8.47 points between arbitrary tie-breaks at that size.
Nothing in this project has ever ranked signals; the engine treats every
qualifying setup as interchangeable.

If a ranking exists that beats an arbitrary tie-break, it is worth more
to a real account than any rule change tested so far, because it costs
nothing to apply and applies to whatever rule is running underneath.

### The one feature available without recomputation
`conditions_met` is stored per trade. On the derivation window under
R20 it is monotone across all three of its buckets:

| conditions met | trades | win rate | mean | median |
|---|---|---|---|---|
| 4 | 2,165 | 39.9% | +8.96% | -4.51% |
| 5 | 1,292 | 44.4% | +9.17% | -3.58% |
| 6 | 121 | 48.8% | +10.01% | -0.48% |

**This is weak evidence and is registered as such.** Three buckets means
a random ordering comes out monotone about one time in six, the top
bucket holds 121 trades, and the mean spread is one point. Win rate and
median separate more convincingly than mean does, which is the pattern
of a feature that avoids bad trades rather than finds good ones.

### R22 — fund the highest-scoring signals first `[data]`
When several signals compete for the same money, fund them in
descending `conditions_met` order instead of arbitrarily. Scored against
the arbitrary tie-break across the same set of seeds, at $25,000,
$50,000 and $100,000, on the test and holdout windows.

**Criterion:** the ranked account must beat the *mean* of the arbitrary
tie-breaks by more than the seed spread of those tie-breaks. Beating the
average while sitting inside the noise band is not a result.

**Expectation:** a small improvement at small account sizes and
essentially none at large ones, since a large account funds nearly
everything and has little left to rank. If the improvement is instead
largest at the large accounts, something is wrong with the test rather
than surprising about the market.

**The failure mode I am watching for.** Ranking cannot be tested on the
window it was derived from, and the table above is derived. The derive
window is therefore excluded from scoring — it appears here only to
record why the rule was proposed.

### R22 result — the ranking does not work

Scored on the two windows it was not derived from. Ranked funding
against the mean of eight arbitrary tie-breaks, with the spread of those
tie-breaks as the noise band the improvement had to clear.

| account | test 2021-2026 | holdout 2005-2009 |
|---|---|---|
| $25,000 | **-1.72 pts** (noise band 14.85) | +0.11 pts (band 7.03) |
| $50,000 | **-0.96 pts** (band 6.12) | +0.89 pts (band 3.19) |
| $100,000 | +0.20 pts (band 2.92) | +0.91 pts (band 1.47) |

**R22 fails.** It is negative where it was predicted to help most, and
every positive figure sits well inside the noise. The derivation-window
monotonicity across three buckets did not survive, which is roughly what
a one-in-six chance of spurious monotonicity should be expected to do.

Registering the weakness in advance is what makes this cheap to
discard. Without the pre-registered noise band, "+0.91 points at
$100,000, replicated in the holdout" is a perfectly presentable finding
and it is nothing at all.

**The wider signal-selection problem stands unsolved.** A $25,000
account still funds one signal in seven, and which seven still swings
the answer by 14.85 points in the test window. `conditions_met` is
simply the wrong feature — it is coarse, and it measures agreement among
conditions that per-condition analysis already showed to be mostly
inert. A ranking built on features with actual resolution is still worth
trying, and is not attempted here because those features are not stored
per trade and would need a re-run to produce.

---

## An observation from the holdout that is not a registered test

R20 over 2005-2009, the window containing the crash, on a $100,000
account: **+9.64%/yr against SPY's +0.80%/yr.** With idle cash paid
nothing at all it is +7.99%/yr, so this is not an artifact of interest.

The mechanism is visible in the entry dates:

| year | entries |
|---|---|
| 2005 | 338 |
| 2006 | 304 |
| 2007 | 229 |
| 2008 | **63** |
| 2009 | **570** |

It mostly sat out 2008 and bought the 2009 recovery heavily. That is
precisely what stage analysis claims to do, and it is the first result
in this project where the method beats buying the index by a wide
margin rather than trailing it.

**Why I am not treating this as a finding.** Survivorship bias is
unfixable in this data — delisted names have instrument records but
their bars come back INVALID_SYMBOL — and it bites hardest in exactly
this window. The 2005-2009 universe is the set of companies that still
existed in 2026, so every firm that went bankrupt in the crash is
missing. A strategy that buys the 2009 recovery is being scored on a
universe pre-filtered to companies that recovered. The true figure is
lower than +9.64% and I have no way to say by how much.

What survives the caveat is the *shape*: entries collapse in the bear
market and surge in the recovery, without anything in the rule looking
at a calendar. Survivorship inflates the returns of the trades that were
taken; it does not explain the timing of when the system chose to trade
at all.

**One thing this changes.** Every headline in this file compares against
SPY over windows that were mostly bull markets, and the method has
consistently trailed. If its advantage is concentrated in falling
markets, then judging it on 2010-2020 — an almost uninterrupted advance
— asks it to win where it does not claim to. That is worth testing
directly rather than inferring, and needs the batch 9 reference arm
before anything can be concluded.

---

## Batch 14 — does the mined filter select, or does it just thin? Registered 2026-08-02

Batch 8 showed the mined filter's thresholds are on a plateau: moving
any of the three across a range that changes trade count by 56% moves
win rate by 0.8 points and leaves the bootstrap ranges almost entirely
overlapping. That rules out a knife-edge fit, which is the good news.

It also raises a question the whole project has skipped. Every
comparison of the filter against the baseline has confounded two
different things:

1. the filter picks *better* setups (selection), and
2. the filter emits *fewer* signals, so a fixed-capital account is less
   crowded and funds a larger share of what it sees (thinning).

Thinning improves a capital-constrained account mechanically, with no
skill involved at all. R19 and R20 both beat the baseline, and neither
test could tell which effect produced the win.

### R23 — the random-filter control `[structural]`
Take the baseline arm and discard trades **at random** until its count
matches the filtered arm's. Score it identically. Repeat over many
random draws and report the distribution, not one draw.

**Criterion:** the mined filter must beat the random thinning
distribution's 95th percentile. Beating its median means the filter is
worth exactly as much as deleting signals with a coin.

**Expectation:** genuinely uncertain, and the flatness in batch 8 is a
bad sign for the filter. A rule that selects well should get *better*
per trade as it tightens, and mean per trade did rise slightly with
tightening (+7.22% → +8.05%) while win rate did not move (41.6% →
42.1%). Rising mean with a flat win rate and a falling trade count is
what thinning a fat-tailed distribution looks like, not what selection
looks like.

**Why this is a fair test and not a rigged one.** Random thinning keeps
the same entry dates and the same underlying trade population, so the
crowding relief is identical. The only thing it lacks is the filter's
claim to know which setups are better. That is precisely the quantity
in dispute.

### Batch 8 result — a plateau, not a knife edge

Holdout 2005-2009, the window never used to derive anything. Each
threshold moved one at a time from the centre, everything else held at
the R20 configuration.

| setting | trades | win | mean | median | $100k account |
|---|---|---|---|---|---|
| RS > 15 | 1,898 | 41.6% | +7.22% | -3.52% | +10.20% ± 1.41 |
| **RS > 20 (centre)** | 1,530 | 42.0% | +7.87% | -3.55% | +9.64% ± 1.47 |
| RS > 25 | 1,215 | 42.1% | +8.05% | -3.63% | +8.92% ± 1.48 |
| >5% below high | 1,647 | 41.9% | +7.19% | -3.72% | +9.34% |
| **>7% (centre)** | 1,530 | 42.0% | +7.87% | -3.55% | +9.63% |
| >10% below high | 1,369 | 41.4% | +7.71% | -3.92% | +8.03% |
| base > 30% | 1,694 | 42.1% | +7.52% | -3.77% | +9.61% ± 1.14 |
| **base > 35% (centre)** | 1,530 | 42.0% | +7.87% | -3.55% | +9.63% |
| base > 40% | 1,309 | 41.3% | +8.02% | -3.81% | +8.54% ± 1.25 |

**The decisive test passes.** Nothing collapses toward baseline at any
neighbouring setting, so the rule is not a curve fitted to one lucky
threshold, and the out-of-sample passes recorded earlier in this file
were not luck of where the cutoff sat.

**It passes by being insensitive.** Trade count varies by 56% across
these settings and win rate spans 0.8 points. The bootstrap intervals on
mean per trade overlap almost entirely: RS>15 gives +1.91% to +13.70%,
RS>25 gives +2.09% to +15.46%. The numbers I mined — 20, 7%, 35% — were
neither a lucky pick nor a good one. They are arbitrary points on a flat
surface, and should be documented as such in
parameter-calibration.md rather than defended.

Looser settings return more on a real account in both parameters that
were swept in both directions, which is a consistent sign. It is also
about 1.2 points against seed spreads of 1.4, so it is recorded as a
direction worth a registered test and not as a finding.

### Batch 14 result — R23 passes: the filter selects

Forty random draws per window, discarding baseline trades at random down
to the filtered arm's count, scored identically on a $100,000 account.

| | filtered | random thinning (median / 95th / best of 40) | unfiltered |
|---|---|---|---|
| test 2021-2026 | **+10.17%** | +6.96% / +8.04% / +8.25% | +7.26% |
| derive 2010-2020 | **+10.35%** | +7.32% / +8.20% / +8.85% | +8.95% |

The filtered arm beats **every one of the forty draws** in both windows,
not merely the registered 95th-percentile bar. The gain is selection,
not crowding relief.

**What it does and does not attribute.** R20 differs from the baseline
in three ways at once — the mined filter plus two dropped conditions —
so this establishes that *R20's selection* carries information, not that
the mined filter does so on its own. R21 in batch 10 is the arm that
separates them, and until it lands the credit is unassigned.

**Why this pairs with batch 8 rather than contradicting it.** What the
filter looks at carries real information; where each cutoff sits does
not, across the range tested. A genuine effect on a broad plateau is the
most trustworthy shape available, and the exact opposite of the
knife-edge fit that batch 8 was built to detect.

---

## Batch 15 — the refinement queue. Registered 2026-08-02

Six changes agreed after the drawdown comparison reframed what this
strategy appears to be: not an index-beater, but something returning
about the index with roughly half the fall. Ordered so that each one is
measurable before the next depends on it.

### M1 — mark-to-market equity `[defect]`
The account curve values open positions at purchase price, so an open
loser shows no drawdown until it closes. Every drawdown figure recorded
in this file is therefore optimistic by an unmeasured amount. This is a
correction, not an experiment, and it must land first because it is the
measurement everything defensive is judged on.

### M2 — position sizing by risk `[book]` `[structural]`
Every trade currently gets the same $1,000 whether the stop sits 4% or
14% away, so the real bet varies by more than 3x without anyone choosing
it. Size instead so each trade risks the same fraction of the account:
shares = (risk budget) / (entry - stop). Stop distance is already
computed for every trade, so the input exists.

**Expectation:** lower variance, and per-trade mean roughly unchanged.
If mean per trade moves a lot, sizing is smuggling in a selection effect
and needs investigating rather than adopting.

### M3 — exposure scaled by volatility and market regime `[data]`
Hold less when markets are turbulent. Not a signal, a sizing overlay,
and it stacks on whatever rule is underneath.

### M4 — add to winners `[book]`
The top 25 trades produce 51% of all profit. With a payoff that
concentrated, how much is held in the few that work matters more than
which ones get picked, and a position is currently never increased.

### M5 — exit on relative strength deterioration `[book]`
Median trade -3.55%, mean +7.87%: most positions bleed slowly and a few
pay for everything. Every exit today is a price stop. Leaving when a
stock starts lagging the market targets the bleed directly. The stall
exit built for R6 is the crude version of this; this is the informed
one.

### M6 — transaction costs, and the honest version of them `[structural]`
Webull's published schedule, confirmed 2026-08-02: $0 commission; FINRA
TAF $0.000195/share on sales capped at $9.79; SEC fee $0.0000206 x
proceeds on sales; CAT fee $0.000003 x volume on both sides.

On a $1,000 position that is **$0.03 round trip, about 0.003%**. Against
a mean trade of +7.87% it is not a rounding error, it *is* the rounding.

Modelling it exactly is therefore close to pointless on its own, and it
will be modelled exactly anyway because it costs nothing to be right.
The cost that matters is the one Webull does not charge: the bid-ask
spread and slippage, paid to the market. This universe includes small
community banks whose spreads are wide.

**So the registered test is a breakeven sweep, not a point estimate.**
Re-run the best rule charging 0.1%, 0.25%, 0.5%, 1.0% and 2.0% round
trip and report the cost at which the edge disappears. "How much friction
can this survive" is answerable; "what exactly is the spread on 1,168
names over 20 years" is not.

### M7 — a mechanical trend rule against the stage classifier `[data]`
Time-series momentum is the documented, mechanical form of what stage
analysis does by eye: hold an asset while its own trend is up. Replace
the stage classifier with a plain rule — price above its 30-week average
and 12-month return positive — and run it head to head.

**Expectation:** genuinely uncertain, and that is the point. If a
two-line rule matches nine hand-tuned conditions, most of this project's
machinery is decoration. That is worth knowing and would not be a bad
outcome.

### M8 — momentum as a ranking, not a gate `[data]`
R22 failed because it ranked on `conditions_met` — three coarse values
built from conditions already shown to be mostly inert. Mansfield
relative strength is a momentum measure and the project computes it
already, then throws away its resolution by using it as pass/fail.
Cross-sectional momentum is the best-evidenced effect in equities, and
ranking by it is the version with literature behind it.

Scored against the R22 criterion, unchanged: it must beat the arbitrary
tie-break by more than the seed spread of those tie-breaks.

---

## Batch 16 — what a month of Sharadar is for. Registered 2026-08-02

Agreed to trial a survivorship-free data vendor. Registering the
evaluation *before* the data arrives, so the verdict is decided by a
test rather than by having paid for it.

### The reason, and the reason it is not fundamentals
The system uses no fundamental inputs at all — the short module has none
by design and every long condition is price or volume. Point-in-time
fundamentals matter only for a machine-learning direction not committed
to. What the vendor fixes *today* is survivorship: it carries delisted
companies, which Webull cannot serve at all.

### S1 — how much has survivorship been inflating everything `[defect]`
Re-run R20 over 2005-2009 on a universe including companies that were
delisted or went bankrupt, against the same run on the survivors-only
universe already recorded.

That window currently shows +9.63%/yr against SPY's +0.80%, with a
-10.3% drawdown against SPY's -54.6%, and has been explicitly refused as
a finding because the universe is the set of companies still listed in
2026 — a strategy that buys the 2009 recovery being scored on a
population pre-filtered to things that recovered.

**Expectation:** the gap narrows substantially. If it does not, that is
the more surprising result and deserves more scrutiny than a
confirmation would.

**Criterion for the vendor, not the strategy:** this test is worth the
subscription whichever way it comes out. A large gap tells us every
figure in this file is inflated and by roughly how much; a small gap
removes the caveat currently attached to all of them. There is no
outcome here that leaves us where we started.

### S2 — daily bars beyond the 1200-bar wall `[structural]`
Webull caps 1200 bars on every timespan, which is 4.75 years of daily
data and the reason no daily-bar rule has ever been tested over a
meaningful window. Long daily history removes that block.

Secondary to S1 and explicitly so: it enables new work, whereas S1
corrects existing work.

### On point-in-time data generally
Recorded because it was worked out from first principles and is worth
keeping. Testing on restated fundamentals produces a backtest that
cannot be reproduced live, since live only ever offers what was known
then. Two leaks matter and the second is usually larger:

1. **Restatement** — today's database overwrites what was originally
   filed.
2. **Reporting lag** — a quarter ending 31 December is not filed until
   late February. Stamping those figures on 31 December trades on
   information six weeks before it existed. The numbers are correct;
   they were simply not available. Point-in-time data carries the filing
   date, which is what allows the delay to be enforced.

Index membership has the same property: "the S&P 500 in 2008" means its
constituents then, not now. That is the survivorship problem again in
another form.

The price side of this project already honours the equivalent
discipline — the backtest walks forward and reads only bars up to each
checkpoint. Fundamentals are the same rule applied to a source where the
discipline has to be bought rather than coded.

---

## Batch 17 — what public data can and cannot repair. Registered 2026-08-02

Two discoveries change the data picture, one of them a correction to
this project's own reference notes.

### Webull serves the full daily history after all
`docs/webull-api-reference.md` records 1200 bars as "the practical limit
on how far any backtest can go". That is wrong. The 1200 cap is
per-request, and the SDK exposes `start_time`/`end_time` parameters the
code has never used. They fail on the batch endpoint and fail as date
strings, but on the single-symbol endpoint with **epoch milliseconds**
they page backwards correctly. SPY returns 486 bars on the page ending
1995-01-03, reaching 1993-01-29 — the fund's own inception, not a wall.

Full daily history is therefore free, at roughly five calls per symbol
to cover 2005-now, about ninety minutes unattended for the whole
universe. No purchase needed for depth.

### But tickers are recycled, and that is a live contamination risk
Webull maps a symbol to whoever holds it *now*:

| ticker | Webull resolves to | who held it in 2007 |
|---|---|---|
| GM | General Motors Co (CIK 1467858, first filed 2009-07-16) | the old GM, later Motors Liquidation |
| WM | Waste Management | Washington Mutual also traded as WM |
| CC | Chemours (incorporated 2014) | Circuit City |

Requesting GM with an end date in 2008 returned 304 bars. Whatever those
are, they are not the company that ticker resolves to today. A naive
backfill would splice unrelated companies into one series and return
something that looks perfectly well-formed.

### D1 — the contamination detector `[defect]`
SEC EDGAR assigns every filer a permanent **CIK**, which is precisely
the stable identifier a ticker is not. `company_tickers.json` maps
current tickers to CIKs, and `data.sec.gov/submissions/CIK##########.json`
gives each company's first filing date and former names.

For every symbol in the cache, compare the earliest cached bar against
the CIK's first filing. Bars predating the company's existence are a
different company and must be trimmed, not kept.

**This must run before any daily backfill**, or the cache is poisoned in
a way that reads as clean data. Free, and within SEC's stated fair-access
rate.

### D2 — the delisting census `[defect]`
Delisting is a matter of public record: **Form 25 / 25-NSE** is the
notification filed when a security is removed, and **Form 15** is
deregistration. Lehman's CIK 806085 carries 25-NSE filings dated
2008-10-15 and 2008-10-21.

So the companies that left the market, and when, are knowable for free.
Counting them against our universe converts "survivorship bias, extent
unknown" into a measured hole.

**The classification problem, flagged rather than waved through.** Form
25 is filed for *every* removal — acquisitions and voluntary exchange
transfers as well as failures. That matters more than it first appears:
an acquired company usually left at a premium, so its absence makes our
results look *worse*, while a bankruptcy's absence makes them look
better. Survivorship bias is normally assumed to inflate, and it is not
obvious a priori which way the net runs here. A census that does not
separate the two answers nothing.

### D3 — bounding the damage `[structural]`
With D2's count, bound the impact rather than pretend to fix it: what
happens to every headline figure if the missing names are assumed to
have performed at market, and separately if the failures are assumed
total losses.

Worth noting that the stop logic caps single-name damage — except in
precisely the case that matters, since bankruptcies gap overnight
through any stop.

### What none of this fixes
EDGAR holds filings, not prices. Knowing Lehman delisted on 2008-10-15
does not produce Lehman's daily bars, and Webull returns INVALID_SYMBOL
for the ticker. Public data lets us **detect** contamination and
**measure** the hole. Filling it still needs a vendor with permanent
security identifiers and dead-company price history.

The Sharadar case therefore narrows to exactly one thing — prices for
companies that no longer exist — and D2 is what tells us whether that
one thing is worth paying for, before paying for it.

### Batch 8 complete — two findings the holdout alone could not show

The full sweep across all three windows. Account figures are a $100,000
account with idle cash paid the rate of the period.

**1. Relative strength is monotone in every window, on both measures.**

| window | RS>15 | RS>20 | RS>25 | monotone |
|---|---|---|---|---|
| derive | 41.2% / +8.15% | 41.8% / +9.07% | 42.9% / +10.05% | yes |
| test | 38.3% / +4.46% | 38.6% / +4.48% | 39.1% / +5.05% | yes |
| holdout | 41.6% / +7.22% | 42.0% / +7.87% | 42.1% / +8.05% | yes |

Win rate *and* mean per trade both rise with relative strength, in three
independent windows, without exception. Nothing else measured in this
project has replicated that cleanly. The monotonicity screen was adopted
because a random ordering comes out monotone about one time in six; three
windows agreeing on two measures is a different order of evidence.

**But tightening the gate does not improve the account.** Account return
across those same arms is 10.47 / 10.35 / 10.32 on derive and 9.99 /
10.17 / 9.85 on test — flat, because every trade removed is capital left
idle. The quality gained and the participation lost cancel.

That is the argument for **M8**, and it is now an evidenced one rather
than an analogy to the literature: relative strength carries a real
gradient, and a threshold is the one way of using a gradient that throws
it away. Ranking keeps the ordering without cutting participation.

**2. The 52-week-high condition points the wrong way.**

| window | below>5% | below>7% | below>10% |
|---|---|---|---|
| derive | **42.7%** / +9.01% | 41.8% / +9.07% | 40.3% / +9.49% |
| test | **39.9%** / +4.65% | 38.6% / +4.48% | 37.5% / +4.24% |
| holdout | 41.9% / +7.19% | **42.0%** / +7.87% | 41.4% / +7.71% |

The mined rule demands a stock sit at least 7% below its 52-week high.
Win rate falls as that discount is widened, clearly in two windows and
flat in the third — the requirement is at best doing nothing and at
worst costing us. Mean per trade disagrees on derive and agrees on test,
so the case rests on win rate.

It also runs against the documented 52-week-high effect, where proximity
to the high predicts outperformance rather than the reverse. I mined
this threshold out of the winners and never asked whether its *sign* was
right.

### R24 — drop or invert the 52-week-high requirement `[data]` `[defect]`
Three arms on the full R20 configuration: the condition removed
entirely; the condition inverted to require price *within* 7% of the
high; and R20 unchanged as the matched control, run last.

**Expectation:** removal is neutral-to-positive and inversion is
positive. If inversion wins clearly, the mined filter was carrying a
sign error through every result in this file, and R19/R20's measured
edge came from its other two components in spite of this one.

---

## Batch 9 result — the bear-market edge is the method's, not R20's

The 2005-2009 reference arm finally exists, and it settles the question
raised when that window first showed an unexpectedly large margin.

$100,000 account, idle cash paid the rate of the period.

| window | SPY | baseline (9 conditions) | R20 |
|---|---|---|---|
| 2005-2009 | +0.80% | **+8.06%** | **+9.69%** |
| 2010-2020 | +13.61% | +8.96% | +10.34% |
| 2021-2026 | +11.78% | +7.39% | +10.21% |

**The plain nine-condition checklist already captures nearly all of it.**
R20 adds about 1.6 points in that window; it does not create the effect.
Stage analysis as written is what sits out a bear market — and it does so
without anything in the rule consulting a calendar or an index level
beyond the market-stage condition, which batch 7 showed barely binds.

### Chained across the whole period

Indicative rather than exact — the holdout runs a 1,257-name universe
against the other windows' 2,627, so this compounds three results that
are not on identical footing.

| | growth of $100,000 | CAGR | worst drawdown |
|---|---|---|---|
| SPY buy and hold | $759,970 | 10.01% | -54.6% |
| baseline | $550,583 | 8.36% | -15.4% |
| **R20** | **$780,833** | **10.15%** | **-20.3%** |

Return per unit of worst drawdown: SPY 0.18, R20 0.50, baseline 0.54.

**Every headline in this file up to now said the strategy loses to the
index.** Across a full cycle containing a crash, R20 matches it — 10.15%
against 10.01% — while falling less than half as far at the worst point.
That is not a better index tracker. It is a different risk profile, and
it is the profile trend-following is documented to have: lagging through
sustained advances, protecting through drawdowns.

The windows I had been scoring on were two bull markets and one crash,
and I was averaging over them as though the strategy claimed to win in
all three.

### Four reasons this is softer than it looks, three of them downward

1. **Survivorship**, unquantified, and heaviest in 2005-2009 — the
   window carrying most of the result. Batch 16 exists to measure this.
2. **Drawdown is understated.** Open positions are valued at cost, so an
   unrealised loss shows nothing until it closes. M1 fixes it and will
   make these numbers worse.
3. **No transaction costs** anywhere. M6.
4. **Chaining across universes**, as noted above.

The one thing pointing the other way is that the effect appears in the
baseline as well as in R20, so it does not depend on any of the tuning
done in this file — which is the part of the result least likely to
evaporate.

---

## D1 and D2 results — the identity fix, and the size of the hole

### D1: the naive detector was wrong, and by a lot

Resolved all 5,803 cached symbols against EDGAR (24 minutes, one request
each, now cached in `security_identity` so it never repeats).

The first version tested one thing: does cached history predate the
first filing of the company currently holding the ticker? That flagged
**605 symbols, and 91% were false positives** — XOM, BlackRock, Bunge,
Six Flags and hundreds more. Those companies re-registered as new legal
entities (redomiciling, holding-company restructures, mergers) and got
fresh CIKs while the same business kept trading under the same ticker
without missing a day.

**A new CIK is not a new company.** I built the detector on the
assumption that it was.

The fix requires a second signal: a genuinely recycled ticker leaves a
**trading gap**, because the old company delists and the new one lists
months or years later, while a reorganisation leaves none.

| test | flagged |
|---|---|
| CIK first-filing date alone | 605 |
| plus a real trading gap (>120 days) | **57** |

About 1% of the universe, not 10%. The 7-day "gaps" being flagged were
the weekly bar cadence.

Worth recording how close this came to doing damage: the first report
would have recommended trimming history for 605 symbols, which would
have discarded legitimate data for several hundred major names. What
caught it was reading the output rather than the count — XOM at the top
of a contamination list is visibly wrong.

### D2: the survivorship hole is the same order as the sample

Every delisting notice filed with the SEC from 2004 to 2026, taken from
the quarterly form indexes: **36,346 notices, 11,448 distinct
companies**, all free.

| window | names screened | delisted **and absent from our data** |
|---|---|---|
| 2005-2009 | 1,257 | **2,805** |
| 2010-2020 | 2,627 | 4,867 |
| 2021-2026 | 2,627 | 2,932 |

More companies left the 2005-2009 market than we ever looked at, by more
than two to one.

**This overstates the true hole** and the reason matters: Form 25 covers
every security removed, including ETFs, closed-end funds, preferred
shares, warrants and micro-caps that our universe filter would never
have screened. The relevant hole is smaller than 2,805.

It cannot be argued down to small, though, and that is the finding. The
missing population is the same order of magnitude as the measured one.
This is not a correction to the edges of a result; it is a question
about whether the result describes the market or describes the
survivors.

**Batch 16's registered criterion is therefore met.** The question was
whether the hole is large enough to justify buying prices for dead
companies, decided before paying. It is.

### What is still unresolved: the sign

Whether survivorship inflates or deflates our figures depends on why
companies left, and both directions are present. Acquisitions usually
completed at a premium, so their absence makes results look *worse*.
Failures make them look *better*. Everyone assumes the second dominates;
nobody here has checked.

Classification by filing history is running. It is a proxy and is
labelled as one: merger paperwork (S-4, 425, DEFM14A) before the
delisting notice indicates a deal, but **nothing in EDGAR's form types
marks a bankruptcy** — Chapter 11 appears inside an 8-K's items, which
the index does not expose. So "no merger paperwork" is a residual
bucket, not a synonym for failure, and must not be reported as one.

### Batch 10 result — R21, and volume confirmation as a participation tax

R21 is R20 with volume confirmation left *in*. Nothing else differs.

| window | R21 (volume kept) | R20 (volume dropped) | SPY |
|---|---|---|---|
| 2010-2020 | 2,971 trades, +9.39%/yr | 3,578 trades, **+10.34%** | +13.61% |
| 2021-2026 | 3,123 trades, +9.54%/yr | 3,800 trades, **+10.21%** | +11.78% |
| 2005-2009 | 1,158 trades, +9.46%/yr | 1,530 trades, **+9.69%** | +0.80% |

Dropping volume wins in all three windows, by 0.95, 0.67 and 0.23
points. Only the first is close to clearing its seed spread, so
individually none of these is decisive — but the direction is 3 for 3,
and the per-trade numbers say why.

**Per-trade quality is unchanged.** Win rate 42.1 vs 41.8, 37.4 vs 38.6,
42.0 vs 42.0. Mean +8.96 vs +9.07, +4.04 vs +4.48, +8.11 vs +7.87.
Mixed, small, no pattern.

**What the condition actually does is remove 17-20% of trades.** It
does not pick better ones; it picks fewer. And batch 14 already
established what that is worth: discarding signals at random was
comprehensively beaten by the mined filter, so thinning without
selection buys nothing and costs participation.

That is the third independent verdict on volume confirmation — the
per-condition analysis measured +1.84% either way, R16 dropped it with
no harm, and R21 now shows the cost of keeping it — and the first one
with a mechanism attached. It is a participation tax, not a filter.

**On the checklist as a whole.** Two of the nine conditions have now
been shown to measure nothing (volume, risk/reward), two of the three
non-negotiable vetoes never reject anything, and one mined threshold is
under suspicion of having the wrong sign. The parts of this system that
demonstrably carry information are a small minority of its apparent
complexity.

### D2 continued — why the missing companies left, and why it may not be what I said

9,625 companies absent from our universe, each checked against its full
EDGAR filing history for merger paperwork (S-4, 425, DEFM14A, SC 14D9,
SC TO-T) filed on or before its delisting notice. No errors.

| window | merger-related | everything else | merger share |
|---|---|---|---|
| 2005-2009 holdout | 1,509 | 1,296 | 54% |
| 2010-2020 derive | 2,765 | 1,633 | 63% |
| 2021-2026 test | 1,484 | 938 | 61% |
| **all** | **5,758** | **3,867** | **60%** |
| *2008 alone* | *337* | *330* | *51%* |

**The majority of missing companies were acquired, not failed** — in
every window. I have been describing survivorship bias as something that
inflates our results, which assumes the opposite composition. That
assumption is not supported here.

The 2008 column is a useful sanity check on the classifier: the crash
year is the most balanced at 51%, which is what should happen if the
method is tracking something real rather than returning noise.

### Four reasons to hold this loosely, and one that matters more than the rest

1. **"Everything else" is not "failed."** It holds going-private
   transactions, exchange transfers, voluntary deregistrations and
   reverse mergers alongside genuine failures. It is a residual, and
   reporting it as a failure count would overstate failures badly.
2. **Count is not magnitude.** A bankruptcy can take 100%; an
   acquisition premium is typically 20-40%. A 60/40 split by count can
   still be dominated by the smaller bucket, and nothing here measures
   severity.
3. **Merger paperwork is a proxy.** It establishes a deal was in
   progress, not that it closed at a premium.
4. **Our own selection interacts with this, asymmetrically.** The
   strategy buys Stage 2 — stocks already rising. A company heading for
   bankruptcy is in Stage 4 by then and the screener would rarely buy it
   at all, or would stop out early if it did. An acquisition target is
   frequently rising into the deal, which is exactly what this system
   buys, and the premium would land as a large winner. So the missing
   population is not missing *symmetrically*: we are more exposed to the
   acquisitions we cannot see than to the failures we would mostly have
   avoided.

Point 4 is the one that could flip the sign. It is also the one that
cannot be settled without prices for the dead companies, which is
precisely what the vendor supplies.

**Net effect on the Sharadar decision: the case is stronger, not
weaker.** The hole is the same order of magnitude as the sample, and
after this it is no longer safe to assume its direction — so the
correction cannot be estimated, only measured.

### Batch 11 result — void. The short side had no cap on its stop.

The run produced trades losing **2,573%**, **3,759%** and **10,444%**. A
short with a protective buy-stop cannot do that, so the numbers were a
defect rather than a finding, and none of them are reported here as
short-selling performance.

**The cause.** `short_conditions.MAX_SENSIBLE_STOP_PCT` existed and was
being measured — but only to set `risk_reward = False`. That is one
condition out of eight, and the 80% scoring ratio outvotes a single
failure, so the trade proceeded anyway. The check also sat inside
`if prior_low and price`, so whenever no target level was found it never
ran at all.

**Why it only bit the short side.** A long's stop sits below entry, so
even an absurd one costs at most the position. A short's sits *above*
and is unbounded. The engine entered APLD at $0.03 with its stop at a
prior resistance of $0.80 — a 26x risk, taken as a legitimate setup
because seven of eight conditions passed.

**Why it surfaced now.** The original floor of 7-of-8 was arithmetically
unreachable and admitted only 123 trades, which happened to exclude
every pathological setup. Correcting the floor admitted ten times as
many and exposed a second defect that had been sitting behind the first.
The floor-7 control arms in this very run look clean — worst case -33% —
which is exactly how the bug stayed hidden.

**The fix.** `run_short_backtest` now rejects any setup whose stop sits
more than MAX_SENSIBLE_STOP_PCT above entry — a hard rejection, not a
failed condition. On a 250-name sample the same configuration produces
183 trades, none losing more than 100%, worst case -14.3%.

Three regression tests, one of which anchors on the real APLD numbers
rather than an invented example.

**This is the third time stop placement has produced a plausible,
completely wrong result in this project**, after the two recorded in
my project notes. The pattern is consistent enough to be worth stating as a
rule: any change that alters which trades qualify should be followed by
checking the worst case, not just the average. Every one of these was
visible in the tail and invisible in the mean.

S7 re-runs against the corrected engine.

### Batch 12 result — R6 works as designed, on a problem smaller than I claimed

| window | no stall exit | stall at 13 weeks | stall at 26 weeks |
|---|---|---|---|
| 2010-2020 | +10.35%/yr | +10.34% (280 stalled) | +10.31% (7 stalled) |
| 2021-2026 | +10.17%/yr | **+10.73%** (274 stalled) | +10.44% (10 stalled) |
| 2005-2009 | +9.63%/yr | **+9.70%** (145 stalled) | +9.50% (5 stalled) |

**The registered signature appeared.** Mean per trade fell in all three
windows — +9.07 to +8.71, +4.48 to +4.45, +7.87 to +7.16 — exactly as
predicted, because the positions being cut are ones that might have
recovered. That is the mechanism working, and it is worth more than the
headline: had mean per trade *risen*, the expectation recorded in
advance said to be suspicious rather than pleased.

**The account gains are marginal.** +0.56 and +0.07 points in two
windows, flat in the third, against seed spreads of about 1. Directional
at best.

**The 26-week arm is inert.** Five to ten trades affected out of
thousands. Trade counts land identical to the control in two windows,
which under the standing rule demands checking whether the parameter
applied at all — it did, the log records the stalls, and there simply is
almost nothing to cut at that horizon.

### The hypothesis behind R6 was wrong

I built this on the claim that a position going sideways "holds capital
indefinitely — and with the hold cap removed, indefinitely is literal".
The control arm's own hold distribution says otherwise:

| | weeks |
|---|---|
| median hold | 12 |
| 75th percentile | 21 |
| 90th percentile | 29 |
| still open at 13 weeks | 44% |
| still open at 26 weeks | 13% |

Positions resolve quickly. Only 13% survive six months, so there was
never a large pool of dead capital to release, and a stall exit could
not have produced a large gain no matter where the threshold sat.

The reasoning was plausible and I did not check the hold distribution
before building it — a two-line query that was available the whole time
and would have predicted this result in advance. Worth recording as a
process note rather than a result: the cheap descriptive check belongs
*before* the expensive experiment, not after it.

R6a is kept as an option, off by default. It is directionally positive,
costs nothing when disabled, and its real value may be in a live
portfolio where holding a stalled position has an opportunity cost the
backtest cannot see.

### R24 result — the sign was right. I read the wrong metric.

| window | | trades | win | mean | account |
|---|---|---|---|---|---|
| derive | R20 (below the high) | 3,578 | 41.8% | +9.07% | **+10.34%** |
| | test removed | 4,658 | 44.5% | +8.77% | +11.03% |
| | inverted (near the high) | 3,437 | **48.5%** | +8.14% | +9.52% |
| test | R20 (below the high) | 3,800 | 38.6% | +4.48% | **+10.21%** |
| | test removed | 4,623 | 40.6% | +4.49% | +8.53% |
| | inverted (near the high) | 3,080 | **42.7%** | +3.95% | +9.11% |
| holdout | R20 (below the high) | 1,530 | 42.0% | +7.87% | **+9.69%** |
| | test removed | 1,831 | 41.6% | +6.63% | +8.50% |
| | inverted (near the high) | 1,207 | **43.8%** | +4.50% | +7.80% |

**Inverting raises win rate in all three windows and lowers account
return in all three.** Removing the condition helps only on derive and
hurts on both other windows. The original threshold, mined from the
winners, is the best of the three.

**Why the batch 8 reading was wrong.** I flagged this condition as
having a possible sign error because win rate fell as the required
discount widened. That was a real pattern and an irrelevant one. Buying
a stock that has pulled back from its high produces fewer winners and
*bigger* ones; buying near the high produces more winners and smaller
ones. Mean per trade moves opposite to win rate at every single row
above.

This project has already recorded that its returns are concentrated —
the top 25 trades carry 51% of profit under R20, and over 100% under the
baseline. A strategy living on a fat right tail is not improved by
trading magnitude for hit rate, and **win rate is close to worthless as
an objective here.** I know that, it is written down two sections
earlier, and I still read a win-rate gradient as evidence of quality.

The claim in the batch 8 write-up that "the 52-week-high condition points
the wrong way" is withdrawn. It points the right way. What it does is
trade hit rate for size, deliberately, which is what this strategy needs.

**One genuinely open thread.** Removing the condition was the best arm on
derive (+11.03%) and the worst-but-one elsewhere. That is the shape of
noise rather than a finding, but it does say the condition earns its
place mainly in the two windows it was not mined on — which is the right
way round, and mildly reassuring about the mining.

### S7 re-run — the fix works, and the short side does not

Worst case is now -14.7% to -15.0% in every arm, against the -15% cap.
The stop is being honoured; the previous run's -10,444% was the defect
and nothing else.

| window | floor 7 | floor 6 | floor 5 | SPY |
|---|---|---|---|---|
| 2005-2009 | 153 trades, **+2.09%/yr** | 987, +1.51% | 1,545, -1.39% | +0.80% |
| 2010-2020 | 442, -1.33% | 2,067, -3.10% | 3,238, -4.18% | +13.61% |
| 2021-2026 | 264, +1.08% | 995, -2.11% | 1,583, -6.64% | +11.78% |

Win rates run 14-23% with mean per trade negative almost everywhere. At
a 15% win rate the payoff ratio needs to be about 6:1 simply to break
even, and it isn't close.

**Loosening the floor makes it worse, monotonically, in all three
windows.** That is the opposite of the long side, where the mined filter
genuinely selects. Here the stricter floor was accidentally doing the
only useful work — and its 123-trade sample was what disguised the stop
defect in the first place.

### The answer to "I want money working in a bear market"

It already is, and not by shorting.

In 2005-2009 the short side's best configuration returned **+2.09%/yr**.
The plain long checklist returned **+8.06%** in the same window and R20
returned **+9.69%**, by sitting out 2008 (63 entries against 300+ in
normal years), collecting the cash yield, and buying the recovery hard
(570 entries in 2009).

So the honest comparison is not "do shorts make money" but "do shorts
beat cash plus the recovery", and they lose to it by six points a year
in the one window built to favour them.

**And this is the optimistic version.** No borrow fee is modelled
anywhere. Hard-to-borrow names — the ones most attractive to short —
carry the highest rates, so the cost is largest exactly where the setups
look best. Add squeeze risk, which this engine cannot represent at all.

**Practical blocker on top of the evidence:** short selling requires a
margin account. Mine is a cash account, so none of this is
tradeable as things stand regardless of what it measured.

### Recommendation: stop work on the short side

Three windows, nine configurations, consistently negative before costs
that would only make it worse, against a long side that handles the same
market conditions far better. The module stays in the tree with its
defect fixed and its results recorded, but it should not be developed
further unless something changes the premise.

If bear-market exposure beyond cash is wanted later, inverse ETFs need
no margin and no borrow, and would be a fresh question rather than a
continuation of this one.

---

## Batch 18 — K-nearest neighbour on the mined features. Registered 2026-08-02

For a new signal, retrieve the most similar historical setups and use
their outcomes. Non-parametric, needs no training, and interpretable in
a way the checklist is not: "this resembles these twenty, which did X."

### K1 — does neighbour retrieval beat ranking on relative strength alone?
That is the bar, not "does it beat random". Relative strength is the one
feature with a monotone gradient in all three windows, so a KNN that
merely rediscovers it has added complexity and nothing else.

**Guards, because three of these could each fake a result on their own:**

- **Temporal split.** Fit on entries 2009-2015, score on 2016-2020.
  Features exist only for the derivation window, so this is out of
  sample in *time* but not in regime. The stronger test needs features
  mined for the test and holdout windows and is queued separately.
- **Same-ticker neighbours excluded.** The same stock at adjacent weeks
  produces near-identical vectors with near-identical outcomes. Without
  this the model retrieves its own memories and scores brilliantly
  having learned nothing.
- **Scaling on fit-set statistics only.** Features span RS around 0-100,
  turnover in millions, and booleans. Unscaled, distance is whichever
  column has the largest units.
- **Tail probability, not mean.** The target is fat-tailed — the top 5%
  of trades carry 88-144% of profit — so the mean of k neighbours is
  dominated by whether one happened to be a monster. Predict the share
  of neighbours exceeding +50% instead, which matches how this strategy
  actually earns.

**Expectation:** KNN roughly matches RS-only ranking and does not beat
it. 26 features on 6,151 samples is thin, and today's evidence says one
feature carries most of the signal. Being wrong here would be more
interesting than being right.

### On the vector database
Not needed at this scale and recorded so it is not revisited by default.
Exact nearest-neighbour search over 6,151 x 26 floats is a 1.3MB array
and microseconds of numpy. Approximate-nearest-neighbour indexes are a
*speed* optimisation for millions of vectors under latency pressure;
here they would trade exactness for nothing.

The scale that would justify one is real but not yet built: features
mined at every bar across 2,627 symbols of daily history is roughly 14
million vectors. Revisit then, not before.

---

## M1 result — the drawdown claim was overstated, and in one window reversed

Open positions are now valued at each week's close instead of at cost,
and the percentage is measured against the running peak rather than
starting capital. Both were wrong, and both were wrong in the flattering
direction.

| window | | return | previously reported | **actual** | SPY |
|---|---|---|---|---|---|
| 2005-2009 | baseline | +8.22% | -7.1% | **-16.3%** | -54.6% |
| | R20 | +9.67% | -9.8% | **-26.3%** | -54.6% |
| 2010-2020 | baseline | +9.04% | -6.6% | **-20.5%** | -31.8% |
| | R20 | +10.51% | -9.0% | **-24.6%** | -31.8% |
| 2021-2026 | baseline | +6.37% | -13.0% | **-25.4%** | -23.9% |
| | R20 | +10.39% | -17.9% | **-32.5%** | -23.9% |

Real drawdowns are **two to three times** what this file has been
reporting throughout.

### What survives and what does not

**Survives:** the bear-market advantage is real and large. Through
2005-2009 R20 fell 26.3% against the index's 54.6%, and the plain
baseline fell 16.3%. That is the result the whole defensive case rested
on and it holds.

**Weakened:** 2010-2020 is now -24.6% against -31.8%. Better, but not
dramatically, and nothing like the 3x margin the cost-basis figure
implied.

**Reversed:** in 2021-2026 R20 fell **-32.5% against the index's
-23.9%** — worse, while also returning less (+10.39% against +11.78%).
In the most recent window this strategy was beaten on both axes.

### The claim I made, corrected

I described this as "index-like returns at roughly half the drawdown"
and as "a different risk profile". On honest measurement it is:

- a large drawdown advantage **in a crash**,
- a modest one in a long bull market,
- and **a disadvantage in the most recent five years**.

That is a much narrower claim. The strategy protects capital when the
market breaks; it does not otherwise ride smoother than the index, and
recently it rode rougher.

### Two bugs, both flattering, found in one change

1. **Positions carried at cost.** An unrealised loss showed nothing
   until the trade closed, so drawdown only ever saw damage already
   realised.
2. **Percentage against starting capital.** Once an account compounds,
   dividing a dollar fall by the original stake is meaningless — R20's
   2010-2020 figure printed as -113%, which is impossible unleveraged
   and is what exposed the error.

The second was caught only because the first made the numbers large
enough to look absurd. A -113% drawdown is obviously wrong; a -17% one
is not, and it had been sitting in this file unchallenged for the whole
project.

**Everything above this section that cites a drawdown is understated.**

---

## M6 result — the breakeven sweep, and a broker-agnostic cost model

Costs are now a `BrokerProfile` — commission per trade, per share and
percentage, minimums and caps, regulatory pass-throughs, borrow rate —
with Webull shipped as one profile among several rather than as the
assumption. A user drops in their own broker.

**The broker is not the problem.** Webull's schedule on a $1,000
position is $0.0305 round trip, about 0.003%, against a mean trade near
+8%. Modelling it exactly is close to pointless and was done anyway
because it costs nothing to be right.

**Spread and slippage are the problem**, and nobody charges them — they
are paid to the market. So the registered test was never a point
estimate; it is how much friction the edge survives.

$100,000 account, R20, Webull fees plus slippage charged on *both* sides:

| slippage per side | 2005-2009 | 2010-2020 | 2021-2026 |
|---|---|---|---|
| 0% | 9.55% | 10.50% | 10.43% |
| 0.05% | 9.47% | 10.31% | 9.84% |
| 0.25% | 8.75% | 9.85% | 9.13% |
| 0.50% | 8.09% | 9.22% | 7.78% |
| 1.00% | 6.45% | 7.79% | 5.19% |
| 2.00% | 3.02% | 4.19% | 0.69% |
| **buy and hold** | **0.80%** | **13.61%** | **11.78%** |

**Degradation is roughly linear** at about 2 points of annual return per
1% of per-side slippage. Nothing falls off a cliff, which is the good
news; nothing is immune either.

**The bear-market advantage survives heavy friction.** Through 2005-2009
the strategy still returns 3.02% against the index's 0.80% at a
punishing 2% per side. That is the one window where this system's case
lives, and it is the window most robust to cost.

**The bull-market windows were already behind at zero cost**, so cost
does not change that verdict, it only deepens it.

**What this means practically.** Large caps trade at spreads well under
0.1%, where the strategy loses well under a point a year. The small
community banks in this universe can run 1-2%, where it loses three to
five. That argues for a liquidity floor in the universe filter — which
is not currently registered and should be, because the alternative is a
strategy whose returns depend on names it cannot actually trade cheaply.

---

## Batch 19 — R25, the long side's stop ceiling. Registered 2026-08-03

The short-side stop defect has a twin on the long side, and I fixed one
without checking the other.

`MAX_SENSIBLE_STOP_PCT = 15` is the book's own number, not an
operational choice — recorded as such after the source was re-read.
`conditions.py` measures it and sets `stop_too_wide`. But that only
drives `risk_reward` to False: one condition of nine, which the 80%
scoring ratio outvotes.

**And R20 disables `risk_reward` outright**, so in the best rule this
project has, the stop-width check is not weakened — it is absent.

Measured consequences on the test window:

| | R20 | baseline |
|---|---|---|
| median implied stop distance | 36.1% | — |
| 90th percentile | 62.7% | — |
| trades losing more than 15% | **22.8%** | 10.9% |
| trades losing more than 30% | 4.9% | 1.9% |
| worst single loss | -83.1% | -71.7% |

R20 doubled the rate of oversized losses against the baseline, and it
did so as a side effect of dropping a condition that measured nothing
useful *as a condition* while carrying the only stop-width signal.

This is also exactly the objection I raised on 2026-08-02 — that
an $80 entry should never carry a $30 stop — which I answered by
confirming the constant was the book's and never checked whether the
engine honoured it.

### R25 — enforce the ceiling as a gate `[book]` `[defect]`
`run_backtest(max_stop_pct=...)` rejects any setup whose stop sits more
than that far below entry. A hard rejection, mirroring the short-side
fix. Default stays None so nothing already recorded changes.

Arms at 15% (the book), 20% and 25% (to see the shape), plus R20
unchanged as a control run last.

**Expectation, and it is not optimistic.** Trade count should fall
sharply — the median stop is 36%, so a 15% ceiling may remove most
setups. Drawdown should improve. **Return may well get worse**, because
this strategy's profit is concentrated in a fat right tail and wide
stops are what let winners survive early volatility. If return collapses
while drawdown improves, that is a real trade-off to present, not a
failure.

The wrong reading would be to treat a return drop as proof the ceiling
is bad. Losing 83% on a single position is not a risk profile anyone
chose; it is one nobody checked for.

---

## M2 result — risk-based sizing is a feature, not an improvement

Position size set so that being stopped out costs the same fraction of
the account each time, rather than committing a flat dollar amount
regardless of how far away the stop sits. Stop distance is recovered
from `r_multiple` (gain over risk) and `return_pct` (gain over entry),
whose ratio is risk over entry — no schema change needed.

$100,000 account, marked to market, no single position over a tenth of
the book.

| window | flat $1,000 | risk 0.5% | risk 1.0% | SPY |
|---|---|---|---|---|
| 2005-2009 | +9.67% / -26.3% | **+11.35%** / -27.6% | +9.19% / -29.0% | +0.80% |
| 2010-2020 | +10.51% / -24.6% | +11.70% / -24.3% | **+13.32%** / -28.8% | +13.61% |
| 2021-2026 | **+10.39%** / -32.5% | +8.67% / -38.9% | +10.05% / **-46.6%** | +11.78% |

**Not an improvement.** Returns rise in two windows and fall in the
third, while drawdown worsens in five of six comparisons — severely in
the most recent window, where 1% risk per trade produces a 46.6% fall
against the index's 23.9%.

The mechanism is straightforward once seen: sizing by risk puts far more
money into tight-stop setups, and with the cap at a tenth of the book
many positions sit at that cap. The result is a more concentrated
portfolio, which raises returns and drawdowns together. That is a
different risk profile, not a better one.

The test window is also **non-monotonic** — 0.5% risk does worse than
both flat sizing and 1% risk — which is the signature of noise rather
than a dose-response relationship.

### Why it stays in anyway
What I want out of this needs "what share of the stake goes into each",
so per-position sizing is a required output regardless of whether it
improves a backtest. What this result changes is the claim attached to
it: the feature ships as *a way to size positions*, not as a way to make
more money, and the flat stake remains the default because nothing here
justifies displacing it.

**The obvious next move is the one to avoid.** A smaller position cap
would probably tame the drawdowns and might turn this into a clean win.
Tuning the cap until the answer looks good, on windows I have already
read, is exactly how the mined thresholds got their credibility problem.
If this is worth pursuing it needs registering as its own test with the
cap swept in both directions.

---

## Risk-adjusted measures — and the number nobody had looked at

Not a registered test. The question was which ratio was being used, and
the answer was none: raw return beside raw drawdown, with one ad-hoc
return-over-drawdown calculation that was Calmar without the name.

Six measures now, because each fails differently. Calmar divides by the
single worst fall and so rests on one episode. Sterling averages the
three largest and Burke takes the root of their squared sum, both of
which survive one unlucky episode better. Sortino uses downside
*volatility* rather than drawdown, which matters because these returns
are violently right-skewed and Sharpe would penalise the upside the
strategy exists to capture. Ulcer combines depth with duration, and
Martin is return over ulcer.

Single seed, marked to market, $100,000 account.

| window | | return | maxDD | Calmar | Sterling | Burke | Sortino | Ulcer | Martin | weeks under water |
|---|---|---|---|---|---|---|---|---|---|---|
| 2005-2009 | R20 | +9.26% | -26.0% | 0.36 | 0.61 | 0.31 | 0.88 | 14.3 | 0.65 | 179 |
| | baseline | +8.19% | -16.5% | **0.50** | 0.63 | 0.35 | **1.01** | 8.6 | **0.96** | **114** |
| | SPY | +0.80% | -54.6% | 0.01 | 0.04 | 0.01 | 0.05 | 20.2 | 0.04 | 116 |
| 2010-2020 | R20 | +10.57% | -24.3% | 0.43 | 0.48 | 0.28 | 0.94 | 12.2 | 0.87 | 182 |
| | baseline | +8.72% | -21.1% | 0.41 | 0.51 | 0.29 | 1.00 | 8.9 | 0.98 | 96 |
| | SPY | +13.61% | -31.8% | 0.43 | **0.62** | **0.34** | **1.19** | **5.2** | **2.63** | **45** |
| 2021-2026 | R20 | +10.96% | -31.4% | 0.35 | 0.40 | 0.23 | 0.67 | 16.9 | 0.65 | 156 |
| | baseline | +6.09% | -25.7% | 0.24 | 0.29 | 0.16 | 0.52 | 13.9 | 0.44 | 133 |
| | SPY | +11.78% | -23.9% | **0.49** | **0.72** | **0.39** | **1.12** | **8.0** | **1.48** | **102** |

### Three findings, none of them comfortable

**1. Risk-adjusted, the strategy only wins in the crash.** Through
2005-2009 it beats the index on every measure by an enormous margin.
Over both bull windows the index wins on Sortino, Ulcer, Martin and time
under water, ties on Calmar in one and beats it in the other. The
earlier framing — index-like returns with a better risk profile — does
not survive contact with these.

**2. Time under water is the worst number in the project, and it had
never been measured.** R20 spends **156 to 182 weeks** below a prior
peak in every window. Three to three and a half years. The index spends
45 weeks in the 2010s and 102 recently. Depth was the wrong question:
this strategy is not mainly deeper underwater than the index, it is
underwater far longer, and no drawdown-depth ratio would have shown
that.

**3. The baseline beats R20 on risk-adjusted terms in two windows of
three.** Every improvement recorded in this file was measured in return.
On Calmar, Sortino, Martin and weeks under water the plain
nine-condition checklist is the better system in 2005-2009 and roughly
level in 2010-2020. **The tuning raised returns and degraded the ride**,
and I would not have noticed because I was never scoring the ride.

### What this changes
Return alone is no longer an adequate score for any future arm. The
comparison table should carry Martin and weeks-under-water beside CAGR,
because those are the two that would have contradicted my conclusions
earliest and did so the moment they were computed.

### K1 result — the direction is real, the size is not, and the test is weak

`screener/neighbours.py`. Fit on entries 2009-2015, scored on 2016-2020,
21 features, k=25, predicting the share of neighbours that returned more
than 50%.

Paired against ranking on relative strength alone, 60 samples of 400
signals each. Paired because both rankings score the *same* sample, so
the sampling noise that made the unpaired ranges useless cancels.

| | |
|---|---|
| KNN wins the pair | **47 of 60 (78%)** |
| mean advantage | +2.91 points |
| 5th-95th percentile | **-2.44 to +9.01** |

**The sign test says something is there.** 47 of 60 under a coin-flip
null is roughly a one-in-ten-thousand result.

**The magnitude interval says we cannot size it.** The band straddles
zero, and the registered criterion was explicit that this means no
finding. Both are true at once because the target is fat-tailed: KNN
more often puts better signals on top, and a handful of samples where
relative strength happened to catch a monster wipe out the average
advantage.

**And the test is weaker than it looks.** Features exist only for the
derivation window, so this is out of sample in *time* but not in regime
— 2016-2020 is the back half of the same bull market the rule was mined
in. A real answer needs the feature miner run over the test and holdout
windows, which is queued and is the only version worth quoting.

### What was wrong the first time
An exploratory pass produced a similar-looking result, which I then
dismissed on the grounds that the relative-strength baseline was
"mostly ordering missing values". That was wrong, and the output printed
directly above the claim contradicted it: 595 of 600 scored signals
carried a relative strength value. I had written the conclusion into the
print statement before reading the data.

The real defect was different and worth keeping: the feature filter
dropped any column with a single missing value anywhere, which excluded
relative strength itself over 50 gaps in 6,151 rows — the one feature
with a monotone gradient in all three windows. Missing values are now
imputed to the fit-set median per feature rather than costing a whole
column.

### On the vector database, settled
Not needed and recorded so it is not revisited by default. This index is
6,151 rows by 21 features — 1.3MB, and exact search takes milliseconds.
Approximate-nearest-neighbour infrastructure is a speed optimisation for
millions of vectors under latency pressure; here it would trade
exactness for nothing. Revisit if features are ever mined at every bar
across the daily history, which would be roughly 14 million vectors.

### R25 result — the book's stop rule is real risk control at a real cost

Monotonic in every window, on every measure, without exception. That is
the cleanest dose-response this project has produced.

| window | ceiling | trades | mean | worst trade | return | maxDD | Calmar | Martin | Sortino | weeks under |
|---|---|---|---|---|---|---|---|---|---|---|
| 2005-2009 | none | 1,530 | +7.87% | -70.3% | +9.26% | -26.0% | 0.36 | 0.65 | 0.88 | 179 |
| | 25% | 736 | +4.10% | -24.4% | +6.50% | -20.0% | 0.32 | 0.61 | 0.95 | 190 |
| | **15%** | 256 | +2.58% | **-14.7%** | +3.89% | **-9.0%** | **0.43** | **1.16** | **1.56** | **158** |
| 2010-2020 | none | 3,578 | +9.07% | -85.6% | +10.57% | -24.3% | **0.43** | **0.87** | **0.94** | 182 |
| | **15%** | 708 | +2.81% | **-15.0%** | +1.91% | **-7.9%** | 0.24 | 0.52 | 0.73 | 200 |
| 2021-2026 | none | 3,800 | +4.48% | -83.1% | +10.96% | -31.4% | 0.35 | 0.65 | 0.67 | 156 |
| | **15%** | 530 | +0.03% | **-14.8%** | +3.48% | **-7.9%** | **0.44** | **0.92** | **1.04** | **93** |

**The cap does exactly what it claims.** Worst single trade goes from
-70%, -86% and -83% to -14.7%, -15.0% and -14.8%. There is no ambiguity
about whether the mechanism works.

**Risk-adjusted, the book wins two windows of three** — and the
dissenter is the derivation window, the one every threshold in this
project was mined on and therefore the least trustworthy for judging.
The two windows never used for mining both favour enforcing the rule.

**One number is unique in this project.** Over 2021-2026 the 15% ceiling
spends 93 weeks under water against the index's 102. Nothing else built
here has ever beaten SPY on time under water.

**And the cost is severe.** Returns of 1.91% to 3.89% a year against an
index doing 12-18% in the bull windows. Trade count falls by 80%. This
is a deeply defensive configuration and only rational for someone who
weights drawdown avoidance far above return.

### What I would not conclude
That the ceiling should simply be switched on. The two effects are not
separable from this test: the cap removes wide-stop setups *and* removes
80% of all trades, so most of the return loss may be participation
rather than selection. The random-thinning control that settled the same
question for the mined filter — does this select, or merely thin? — has
not been run here and should be before anything is adopted.

Left off by default, as registered.

### R25 continued — the ceiling selects, and still is not worth it

The control the previous section said had to run before anything was
adopted. 30 random draws from the uncapped arm, matched to the capped
arm's trade count.

| window | | max drawdown | Martin |
|---|---|---|---|
| 2005-2009 | 15% ceiling | -9.0% | 1.16 |
| | random, same size | -8.1% (best -6.1%) | **1.74** |
| 2010-2020 | 15% ceiling | **-7.9%** (beats all 30) | 0.52 |
| | random, same size | -18.6% (best -11.7%) | **0.60** |
| 2021-2026 | 15% ceiling | **-7.9%** (beats all 30) | 0.92 |
| | random, same size | -13.4% (best -9.5%) | **1.01** |

**It genuinely selects on drawdown.** In two windows the ceiling beats
every one of thirty random draws of the same size. That is not thinning,
it is the rule doing what it claims.

**And random thinning still has a better Martin in all three windows.**
Taking the same number of trades at random delivers more return per unit
of pain than deliberately removing the wide-stop ones.

**Why, and it is the pattern this project keeps meeting.** The ceiling
truncates both tails. The right tail is worth more than the left tail
costs — the same setups that occasionally lose 85% are the ones that
occasionally return several hundred percent, and the top 5% of trades
carry 88-144% of all profit. Cutting the disasters cuts the monsters.

### Verdict
Not adopted, and the reason is now specific rather than cautious. The
book's stop rule is real risk control and a poor efficiency trade: it
buys drawdown reduction at a cost in return greater than the drawdown is
worth, on every risk-adjusted measure computed here.

It would be rational for someone whose binding constraint is drawdown
rather than return — someone who would abandon the strategy in a 30%
fall and therefore needs the 8% version to stay invested at all. That is
a real person and possibly the person this is being built for, which is
why the option stays in the engine rather than being removed.

**What this does not excuse.** The defect the ceiling was built to fix
is still a defect: the engine was taking trades with stops 36% below
entry and losing 85% on single positions because a check existed and was
never enforced. Declining to cap at 15% is not the same as having no
opinion about a stop at 36%. A wider ceiling — 25% or 30% — was never
tested against the thinning control and is the obvious next question.

### R25 closed — no ceiling width survives the thinning control

The open question was whether a wider ceiling would trade better than
15%. It does not, and neither does any width tested.

Martin ratio against 25 random draws matched on trade count:

| window | 25% | 20% | 15% |
|---|---|---|---|
| 2005-2009 | 0.61 vs 0.81 | 0.63 vs 1.09 | 1.16 vs 1.70 |
| 2010-2020 | 0.77 vs 0.74 | 0.78 vs 0.70 | 0.52 vs 0.59 |
| 2021-2026 | 0.72 vs 0.73 | 0.73 vs 0.85 | 0.92 vs 0.99 |

Eight of nine at or below the random median, and the two exceptions beat
only the median rather than the best draw — in the derivation window,
which is the one every threshold here was mined on.

**Closed: the stop ceiling is not an efficiency improvement at any width
tested.** It stays off by default and stays in the engine, because
genuine drawdown control is worth something to someone who would
otherwise abandon the strategy in a 30% fall. It is not worth anything
to someone maximising return per unit of pain.

**A performance defect found while running this.** `_price_index` was
rebuilt from the whole 5,809-symbol universe on every call to
simulate_fixed_capital, so scoring twenty-five draws rebuilt it
twenty-five times and the comparison timed out. Caching it made the run
fifteen times faster.

The first cache keyed on `id()`, which is unsafe: CPython reuses
addresses after garbage collection, so a temporary bar dict can inherit
the index built for a different one and positions get valued against
another symbol set entirely. A test caught it immediately by creating
two dicts that were collected between calls. The cache now holds a
reference to the dict itself, which prevents the address being reused
while the entry lives.

### The liquidity floor — withdrawn, the data says the opposite

The cost sweep noted that thin names pay 1-2% spreads against large
caps' 0.1%, and I concluded a liquidity floor belonged in the universe
filter. I never checked where the edge actually lives before recommending
it.

R20 trades split by dollar volume in the entry week:

| window | band | median volume | mean | at 1% slippage | top-5 share |
|---|---|---|---|---|---|
| 2010-2020 | thinnest 25% | $2.6M/wk | +10.26% | +8.25% | 51% |
| | middle 50% | $60.3M/wk | +7.43% | +5.42% | 13% |
| | most liquid 25% | $648.4M/wk | +11.42% | +9.42% | 28% |
| 2021-2026 | thinnest 25% | $19.1M/wk | **+13.23%** | **+11.22%** | 24% |
| | middle 50% | $172.2M/wk | +1.96% | -0.05% | 40% |
| | most liquid 25% | $1,594M/wk | **+0.46%** | -1.54% | **251%** |

**A liquidity floor would remove the best-performing band.** In the test
window the thinnest quartile returns +13.23% and survives 1% per-side
slippage at +11.22%, while the most liquid quartile returns +0.46% and
goes negative under the same cost.

That 251% is worth pausing on: in the most liquid quartile, the top five
trades account for more than all the profit, so the remaining 945 trades
collectively lose money. The large-cap end of this universe is not where
the strategy works.

**Recommendation withdrawn.** I proposed the floor from a cost argument
without checking the return side, which is the same error as reading a
win-rate gradient and calling the 52-week-high threshold wrong-signed —
reasoning from one number about a system whose behaviour lives in
another.

**What is real, and is a different problem.** Capacity, not spread. A
name trading $2.6M a week is about $500,000 a day; a $10,000 position is
2% of daily volume, which is tradeable, and a $200,000 position is not.
The edge partly lives in names that cannot absorb size. That constrains
how large this strategy can ever run, and it is worth knowing before the
account grows rather than after.

### D3 result — the edge does not survive much survivorship damage

We cannot price companies that no longer exist. We can ask how much
damage it would take to matter, by injecting phantom total losses at the
same timing profile as real trades.

| window | R20 | +2% total losses | +5% | +10% |
|---|---|---|---|---|
| 2005-2009 | +9.20% | +6.25% | +1.48% | -9.20% |
| 2010-2020 | +10.45% | +7.96% | +3.28% | -5.05% |
| 2021-2026 | +11.26% | +6.52% | -2.90% | -16.99% |

**Two percent of trades going to zero erases the advantage over the
index in two windows of three.** Five percent erases it everywhere.

The fragility is arithmetic rather than surprising: the measured edge is
about ten points a year on an account that recycles its capital many
times, so a wipeout costs the full stake where a normal loss costs a
fraction of it.

**Two caveats, pulling opposite ways.**

Total loss is the harshest assumption available. Our stops would catch a
company declining over months — a Stage 4 breakdown does not gap
straight to zero — so only overnight bankruptcy produces -100%. The true
average for a failed position is somewhere between the stop distance and
the full stake, which makes 2% of trades at -100% equivalent to a larger
fraction at a realistic severity.

Against that, the census found 2,805 companies delisted and absent from
a universe of 1,257 in 2005-2009 alone, and 40% of the missing were not
merger-related. The rate of undetected failures is not obviously below
the threshold that matters.

**This is the strongest argument yet for buying survivorship-free
prices.** Not because the correction is certainly large, but because the
sensitivity is steep enough that a correction we cannot measure is
capable of inverting the conclusion. Batch 16's registered criterion —
is the hole big enough to justify the subscription — now has a number
attached to it rather than an intuition.

**The neutral case is uninteresting by construction.** If the missing
names performed like the survivors, nothing changes, which is exactly
why that assumption cannot be used to reassure anyone.

### M7 result — two lines beat nine conditions, except when it matters most

| window | | trades | mean | return | maxDD | Martin | weeks under |
|---|---|---|---|---|---|---|---|
| 2005-2009 | M7 trend rule | 22,345 | +0.52% | **-3.81%** | **-53.9%** | -0.12 | 211 |
| | R20 nine conditions | 1,530 | +7.87% | **+9.26%** | -26.0% | 0.65 | 179 |
| | SPY | | | +0.80% | -54.6% | 0.04 | 116 |
| 2010-2020 | M7 trend rule | 56,496 | +6.57% | **+11.14%** | **-18.1%** | **1.34** | **136** |
| | R20 nine conditions | 3,578 | +9.07% | +10.57% | -24.3% | 0.87 | 182 |
| | SPY | | | +13.61% | -31.8% | 2.63 | 45 |
| 2021-2026 | M7 trend rule | 35,491 | +1.85% | **+19.38%** | -33.1% | **1.19** | 158 |
| | R20 nine conditions | 3,800 | +4.48% | +10.96% | -31.4% | 0.65 | 156 |
| | SPY | | | +11.78% | -23.9% | 1.48 | 102 |

**Price above its 30-week average and a positive 12-month return beats
the nine-condition checklist in both bull windows** — on return, on
Martin, and over 2010-2020 on drawdown and time under water too. Over
2021-2026 it returns +19.38% against the index's +11.78%, the only
configuration built here that has beaten buy-and-hold on raw return.

**And the crash destroys it.** -3.81% a year with a -53.9% drawdown,
which is the index's own -54.6% almost exactly. The rule has no regime
filter: it buys whatever is trending up, including on the way into a
collapse, and stage analysis's whole contribution is refusing to do
that.

So the machinery is not decoration, but its value is concentrated almost
entirely in the bear market — which is precisely where batch 9 located
the edge. In a bull market nine hand-tuned conditions are worse than two
lines.

**Per-trade quality tells the same story from the other side.** M7's
mean trade is +0.52%, +6.57% and +1.85% against R20's +7.87%, +9.07% and
+4.48%. The checklist picks better individual trades in every window.
M7 wins anyway on the account, because it finds ten to fifteen times as
many and keeps the capital working. Selectivity has been costing more
than it earned.

### M9 — the trend rule with the one gate that earns its keep `[data]`
Registered before running. M7 plus the market-stage condition: buy on
the simple trend rule, but only while the index itself is in an uptrend.

**Expectation:** the crash window is where this must show up. If M9 keeps
M7's bull-market returns and avoids the -53.9%, the nine conditions can
be replaced by two lines and one regime filter, and most of this project
is confirmed as decoration after all. If it does not, the checklist is
doing something subtler than regime detection and deserves more respect
than tonight's results give it.

---

## Applying Harvey, Liu & Zhu (2016) — nothing here clears the bar

The paper argues that because hundreds of factors have been tested
against the same data, the conventional t-statistic cutoff of 2.0 is far
too low, and a new factor needs **t > 3.0**. It also distinguishes
sharply between kinds of discovery: "a factor derived from a theory
should have a lower hurdle than a factor discovered from a purely
empirical exercise."

This project has run more than twenty-five arms against three windows,
and its central rule was mined from the winners.

t-statistics on weekly account returns:

| window | R20 (nine conditions) | M7 (two lines) |
|---|---|---|
| 2005-2009 | 1.63 | -0.65 |
| 2010-2020 | 2.31 | **3.17** |
| 2021-2026 | 1.34 | 1.97 |

**R20 never clears 3.0 and clears 2.0 once.** The only arm clearing 3.0
anywhere is M7 — the rule taken unchanged from the trend-following
literature, which by Harvey's own argument is entitled to the *lower*
hurdle and clears the higher one anyway.

The mined thresholds are the case the paper is most sceptical of, and
they do not approach either bar.

**Caveat, stated rather than buried.** t-statistics on weekly account
returns are not formally the same object as factor t-statistics in
cross-sectional asset pricing, so this is an application by analogy. The
multiple-testing logic transfers cleanly; the exact critical value may
not.

**What it changes.** Every pre-registered criterion in this file —
bootstrap 5th percentile above the baseline's mean, beat the index on
average capital — was set without any adjustment for the number of looks
taken. Those criteria are not wrong so much as unadjusted, and the
adjustment is large. Any future claim from this project should carry a
t-statistic and the count of arms run to date beside it.

---

## S1 result — the survivorship correction, measured at last

The true 2005 investable universe was 3,957 domestic common stocks with
at least $1M weekly volume. 2,725 of them (69%) have since delisted. Our
holdout universe was 1,257, of which only 964 appear in the true set —
so we were testing on roughly a fifth of the market, drawn entirely from
survivors, and missing GOOGL, Yahoo, Dell and Broadcom even among the
companies that lived.

Three universes, so the two defects separate: **A** our survivors, **C**
the point-in-time universe restricted to names still listed, **B** the
full point-in-time universe including the dead.

| rule | universe | trades | mean | return | maxDD | Martin | t |
|---|---|---|---|---|---|---|---|
| R20 | A survivors | 1,186 | +7.01% | **+8.19%** | -21.7% | 0.74 | 1.58 |
| | C PIT live | 1,426 | +6.43% | +7.21% | -21.0% | 0.61 | 1.38 |
| | **B PIT all** | 4,384 | +5.16% | **+4.39%** | -26.8% | **0.30** | 0.83 |
| M9 | A survivors | 13,334 | +1.08% | +3.39% | -12.1% | 0.53 | 0.98 |
| | C PIT live | 15,445 | +0.82% | +2.62% | -14.3% | 0.34 | 0.80 |
| | **B PIT all** | 39,205 | +0.65% | **+4.17%** | -16.3% | 0.47 | 1.21 |

Buy and hold SPY: +0.80%/yr.

### The tuned rule broke; the untuned one held

| | universe incompleteness (C-A) | survivorship (B-C) |
|---|---|---|
| R20 | -0.98 pts | **-2.82 pts** |
| M9 | -0.77 pts | **+1.55 pts** |

**R20 loses 47% of its annual return and 60% of its Martin ratio.** M9
improves slightly.

The mechanism is legible rather than lucky. R20's mined filter was
derived by ranking features against realised return across 6,151
derivation trades — every one of them on a company that still existed in
2026. The thresholds encode the characteristics of survivors. Confronted
with the companies that died, the filter degrades badly. M9 is two lines
from a 2012 paper with nothing fitted to anything, and it barely notices
the change.

That is an overfitting signature demonstrated on data rather than argued
from theory, and it is an argument for M9 over R20 independent of every
performance comparison in this file.

### What survives and what does not

**Survives:** the bear-market claim. Both rules beat buy-and-hold in the
crash window on an honest universe — +4.39% and +4.17% against +0.80%.
The margin falls from about 7 points to about 3.5, but the qualitative
finding holds for the first time on data that includes the bankruptcies.

**Does not:** any claim to statistical significance. Every t-statistic
is below 2, against the 2.88 that 25 tests require. Best is M9 at 1.21.

**Every result recorded above this section was measured on universe A**
and should be read as an overstatement of an unknown but now-bounded
size — roughly a 47% haircut for the mined rules, less for the simple
ones.

### Two defects found while running it

**Terminal delistings were being discarded.** A position held into a
delisting has no exit bar, so the engine marked it `still_open` and
`portfolio_sim` excluded it from scoring. That silently dropped 101 R20
and 631 M9 trades in arm B. Of the R20 ones, 73 of 88 were gains, median
+16.2%, worst -3.4% — the signature of acquisitions closing at a
premium. **We were counting the bankruptcies and discarding the
buyouts**, which made survivorship look worse than it is. Found by asking
what happens to shares in an acquisition.

**Sixteen trades entered on a company's final trading bar**, giving an
exit date equal to the entry date and a zero-length position. The
`open_count == 0` assertion in simulate_fixed_capital caught it — an
assertion added earlier when removing unreachable code, which has now
paid for itself.

---

## Batch 23 — the moving average nobody ever varied. Registered 2026-08-05

196 arms have been run in this project. **Not one varied the moving
average.** `MA_PERIOD = 30` has been treated as canonical for the entire
project because Weinstein said so, while we swept mined thresholds, stop
ceilings, volume ratios, evidence floors and hold caps around it.

R7 was registered long ago to compare SMA against WMA and EMA and was
never executed. `ema()` does not exist in moving_averages.py. The code
currently uses a WMA for slope direction while comparing price to an
SMA, an inconsistency nobody chose.

Batch 8 is the precedent that makes this urgent: the mined thresholds
turned out to sit on a plateau so flat their specific values carried no
information. **We do not know whether 30 weeks is a plateau or a peak.**
If it is a peak, it is a fitted parameter we inherited rather than
chose — and inherited fitting is still fitting.

### T1 — moving-average length, weekly `[structural]`
M9 with `ma_weeks` swept across 5, 8, 10, 15, 20, 25, 30, 35, 40, 50.
Momentum lookback held at 52 weeks so only one thing moves. Universe C
(point-in-time, still-listed) for tractable runtime; the comparison is
between lengths on a consistent universe, so composition bias affects
all arms equally.

**Criterion:** a plateau means 30 is arbitrary and any value in the
range serves — which would be reassuring, since it means the result does
not depend on a number we inherited. A peak at 30 would be more
troubling than gratifying: it would mean Weinstein's number is doing
work we cannot explain and cannot have discovered independently.

**Expectation:** a broad plateau between roughly 20 and 40 weeks, with
degradation at 5-10 (too noisy, whipsaw) and at 50 (too slow, gives back
too much). Genuinely uncertain below 15.

### T2 — moving-average type `[structural]`
The unrun R7, finally. SMA against WMA against EMA at the best length
from T1. Requires writing `ema()`, which does not exist.

### T3 — daily bars and a shorter clock `[data]`
The 30-week average is roughly 150 trading days. Sweep 20, 50, 100, 150
and 200 days on daily bars over the 2005-2009 window, checking stops
daily rather than weekly.

This is the test most aligned with what can actually be operated: daily
stop management is feasible, minute-by-minute is not. It needs a
Sharadar daily cache built for the point-in-time universe first, since
the existing daily cache is Webull's and carries the split corruption.

**Expectation:** worse than weekly after costs. Shorter clocks mean more
signals, more turnover, and our breakeven sweep says roughly two points
of annual return per 1% of per-side slippage. The interesting outcome
would be daily *matching* weekly, which would mean the clock is not what
matters.

### T4 — cash or the index `[structural]`
When the strategy is not in stocks it currently earns a fixed cash yield.
That is right when the market gate is off — 2008 is the case the gate
exists for — but wrong when the gate is on and there are simply no stock
signals, which is common given deployment runs 57-88%.

Policy to test: gate off means cash, gate on with no signals means SPY.
Also corrects a way the current model flatters us, crediting 3-4% on
idle cash through periods when the index returned 15%.

---

## T5 — the buy/hold spread, and what it actually does

Novy-Marx & Velikov call a buy/hold spread "the single most effective
simple cost mitigation strategy": require more to establish a position
than to maintain one. M9 used the same test for both, so a marginal
signal churned positions in and out.

Implemented as an entry band — price must exceed its moving average by
the band before entering, while the exit is unchanged. Universe C,
2005-2009.

| entry band | trades | mean | return | Martin | t |
|---|---|---|---|---|---|
| 0% (current) | 15,445 | +0.74% | +2.27% | 0.29 | 0.70 |
| 2% | 10,626 | +1.15% | +3.87% | 0.41 | 1.08 |
| 5% | 7,447 | +1.72% | +4.45% | 0.51 | 1.17 |
| 10% | 4,962 | +2.17% | +5.20% | 0.70 | 1.23 |
| 15% | 3,405 | +2.51% | **+6.77%** | **0.82** | **1.50** |

Monotonic on mean trade, annual return, Martin ratio and t-statistic
simultaneously. Still climbing at 15%, so the peak is not found.

### The mechanism, tested rather than assumed

Two explanations predict different things. A genuine buy/hold spread
cuts **repeat entries per ticker**. Momentum selection — which batch 8
already established is real — would instead pick **different tickers**
with similar repeat rates.

| band | tickers | entries per ticker | tickers entered 3+ times |
|---|---|---|---|
| 0% | 1,222 | **12.64** | 98.9% |
| 5% | 1,220 | 6.10 | 96.6% |
| 15% | 1,139 | **2.99** | 59.7% |

**Ticker count falls 7%; entries per ticker fall 76%.** The band trades
the same stocks far fewer times, which is whipsaw reduction and not
selection. I had argued this was probably momentum wearing different
clothes. It is not, and the test was cheap.

**12.64 entries per ticker at band zero** is the finding underneath the
finding. Over five years the strategy bought the same 1,222 names an
average of twelve times each. That is the churn LPHIQ's six attempts
were an instance of, not an outlier.

### Why this is not yet believable

Universe C excludes delisted names, and the validation cases —
LPHIQ +559.8% after five failed attempts, FRPT1 +693.1% after three,
VPHM +385.3% after one — are **all delisted**. They were never
candidates, so the check that matters could not run.

The band works by removing 78% of entries. The whole question is
whether it removes the failed attempts while keeping the sixth one that
pays. That evidence lives entirely in the names this universe excludes.

**T5b re-runs on universe B with bands extended to 30%**, since the
curve had not turned. Nothing here should be believed until it lands.

---

## T4 result — idle capital, and a window that cannot answer the question

`simulate_fixed_capital` now takes `park_in` (a fund to hold while cash
is idle) and `park_when` (a predicate deciding when parking is allowed).
The policy tested: gate off means cash, gate on with no signals means
SPY.

2005-2009, $100,000 account, cash credited 3%:

| arm | cash only | always SPY | SPY when gate on |
|---|---|---|---|
| M9 | **+3.88%** | +2.33% | +3.42% |
| R20 | +4.01% | +3.45% | **+5.31%** |

Regime-aware parking helps R20 by 1.30 points and costs M9 0.46. The
mechanism is legible: R20 takes 4,384 trades and leaves capital idle, so
parking it matters; M9 takes 39,205 and is mostly deployed whenever the
gate is on, so there is little left to park.

### This window cannot decide the question, and I ran it anyway

Over 2005-2009 SPY returned +0.99%/yr while cash was credited 3%. **Cash
beat the index by two points**, so "hold the index rather than cash" was
never going to look good here. Testing a parking policy only in the one
window where the index underperformed cash is close to meaningless, and
that was foreseeable before running it rather than after.

The windows that matter are 2010-2020 and 2021-2026, where the index
returned 13.61% and 11.78% against cash near zero. If parking does not
win there it is dead; this result says nothing either way.

### The cash rate is an anachronism of the same kind as the commissions
A flat 3% is wrong in both directions across this window: short rates
were near 5% in 2005-2007 and near 0.2% by 2009. It flatters cash early
and penalises it late. Wanted: a rate series rather than a constant,
which is the same fix as the era-aware broker profile and should be done
alongside it.

### T4 across all three windows, with parking costs charged

| window | universe | arm | cash | always | gated | B&H |
|---|---|---|---|---|---|---|
| 2005-2009 | corrected B | M9 | **+3.88%** | +1.78% | +2.90% | +0.99% |
| 2005-2009 | corrected B | R20 | +4.01% | +2.07% | **+4.49%** | +0.99% |
| 2010-2020 | survivor-biased | M9 | +10.95% | **+15.01%** | +11.98% | +13.77% |
| 2010-2020 | survivor-biased | R20 | +10.57% | **+15.54%** | +11.65% | +13.77% |
| 2021-2026 | survivor-biased | M9 | +18.61% | **+23.70%** | +20.16% | +12.15% |
| 2021-2026 | survivor-biased | R20 | +10.96% | **+16.21%** | +13.86% | +12.15% |

Always parking wins four of six. The regime-aware policy I designed
wins one. The clever idea lost to the dumb one, and the gate only earns
its keep in 2005-2009 — the sole window where sitting out was worth
anything.

### The policy is worth more than the strategy

Under cash-only, M9 and R20 *lose* to buy-and-hold in 2010-2020 by 2.82
and 3.20 points. Under always-parked they *beat* it by 1.24 and 1.77.
Same trades, same signals: the sign of the result is set by what idle
cash does.

The choice is worth 3-6 points a year. The strategy edge is worth about
one. Roughly 200 arms have been spent tuning entry rules that move the
headline by fractions of a point, while an unexamined default — cash
credited at a flat 3% — was quietly worth several times all of it. The
most consequential parameter in the system was one I had never
registered as a parameter.

### Two corrections to the first reading of this table

**"The only clean window gives the smallest edge" was wrong.** It came
from reading the always-parked column alone. Best-policy-per-window puts
2005-2009 at +2.89 and +3.50 over buy-and-hold, ahead of 2010-2020.

**But best-of-three is a selection.** Choosing the winning policy after
seeing the results inflates exactly as choosing the best entry rule from
200 does. Fixing one policy in advance — always-parked, which wins four
of six — gives the honest figures: **+0.79 and +1.08** in the clean
window, **+1.24 and +1.77** in 2010-2020, and +11.55 and +4.06 in
2021-2026. The defensible claim is one to two points a year, not the
headline.

### What still needs doing before any of this counts
- **2010-2020 and 2021-2026 run on the survivor-biased Webull universes**,
  which cost R20 47% of its return when corrected. The +11.55 is an
  artifact until re-run on Sharadar. The reversal between windows is
  confounded with a change of data source.
- **Parking friction is now charged** at 0.11% a leg — $1 plus a basis
  point of spread on a $1,000 stake — because modelling it as pure
  accrual was worth about a point a year on the busiest arm. It is
  charged only when the account is actually in the fund, so a policy
  that declines to park is not billed for trades it never made.
- **The flat cash rate remains an anachronism.** Wanted alongside the
  era-aware broker profile.

---

## W2 — the two dirty windows, re-run on corrected data

T4's edge over buy-and-hold in 2010-2020 and 2021-2026 came off the old
Webull universes. Re-run on point-in-time Sharadar universes rebuilt
under one explicit rule (domestic common stock, real exchange, listed at
the window start, usable bars), with the always-parked policy fixed in
advance:

| window | rule | universe | trades | always-parked | vs B&H |
|---|---|---|---|---|---|
| 2021-2026 | R20 | survivor-biased | 3,908 | +16.21% | +4.06% |
| 2021-2026 | R20 | **corrected** | 6,225 | +12.09% | **-0.06%** |
| 2021-2026 | M9 | survivor-biased | 29,235 | +23.70% | +11.55% |
| 2021-2026 | M9 | **corrected** | 40,067 | +4.35% | **-7.80%** |
| 2010-2020 | R20 | survivor-biased | 3,578 | +15.54% | +1.77% |
| 2010-2020 | R20 | **corrected** | 7,885 | +7.02% | **-6.75%** |

`w2_2010_M9` was still running when this was written and is deliberately
not reported. Its row count looked complete two hours before it was.

### Every edge over buy-and-hold was survivorship

The +11.55% flagged as "probably an artifact" was entirely an artifact.
M9 loses nineteen points in 2021-2026 on correction alone. Of the three
arms resolved so far, one ties the index and two lose to it by six to
eight points a year.

Set beside 2005-2009, where the corrected arms did beat buy-and-hold,
the shape is consistent: **this strategy beats the index only when the
index does badly.** It won the 2008 window and loses the two bull
windows by six to eight points a year. That is what a trend-following
stop-loss system structurally is — premiums paid in good years against a
payout in the crash — and it is not an edge, it is insurance with a
price attached.

### The confound that decides what to do next
The corrected universes are not merely less survivor-biased, they are
**3.3x larger** (1,257 names against ~4,100). They add the previously
missed small and micro caps as well as the dead ones. So an unknown part
of this collapse is trading names too small to trade rather than
survivorship as such. Those are different problems: one is fatal to the
method, the other is fixed with a liquidity filter.

S1 already has the shape that separates them — B adds the dead and the
missed, C restricts to names that still exist. The missing arm is a
liquidity-filtered universe (dollar volume floor at the point of entry),
run against both. Until that exists, "the strategy loses to buy-and-hold
in bull markets" is supported and "the method does not work" is not.

---

## T5b — the buy/hold spread on universe B

T5 ran on universe C and concluded the entry band cuts whipsaw rather
than selecting momentum, because entries per ticker fell 76% while the
ticker count fell only 7%. Universe B adds the companies that died,
which is where the multi-attempt names live (LPHIQ took five failed
entries before the sixth returned +559.8%).

2005-2009, $100k, always-parked. Buy and hold SPY: +0.99%/yr.

| band | trades | tickers | entries/ticker | win% | median% | CAGR | vs B&H |
|---|---|---|---|---|---|---|---|
| 0% | 39,205 | 3,723 | 10.53 | 18.2 | -1.72 | +1.78% | +0.79% |
| 10% | 13,533 | 3,656 | 3.70 | 33.4 | -6.26 | +1.92% | +0.93% |
| 15% | 9,648 | 3,476 | 2.78 | 35.4 | -6.37 | +1.68% | +0.69% |
| 20% | 6,826 | 3,082 | 2.21 | 36.9 | -6.47 | +4.51% | +3.52% |
| 25% | 4,904 | 2,617 | 1.87 | 38.1 | -6.91 | +4.46% | +3.47% |
| 30% | 3,552 | 2,143 | 1.66 | 39.4 | -7.37 | +4.36% | +3.37% |

Band 30 was re-run alone after the sweep died on a database lock in that
band; the partial rows were discarded rather than read. Alone, on a local
database, it took 652s for 3,552 trades against band 25's 2,754s for
4,904 — roughly three times faster per trade, which is the clearest
measure yet of what the shared synced database was costing.

### A plateau rather than a peak, and one step that does not fit

Bands 20, 25 and 30 land within 0.15 points of each other. That is the
shape a real effect makes: a single spiking band would be the signature
of fitting noise, and there is no spike here.

The step between 15% and 20% does not fit as cleanly — +1.68% to +4.51%
is most of the total effect arriving between two adjacent settings, when
every other neighbouring pair moves by fractions of a point. Either
there is a threshold there or it is a boundary artifact, and nothing in
this table distinguishes those. Worth a band at 17 or 18 before any of
this is leaned on.

### The mechanism survives, but weaker than T5 claimed

Entries per ticker fall 82% while the ticker count falls 30%. Churn is
still shed far faster than names, so the dominant effect is still the
dead space rather than selection — but on universe C the ticker count
fell **7%**, and 30% is a different claim. The band is dropping nearly a
third of the names outright.

The distribution is the part that reads cleanly as whipsaw. At band 0
the median trade loses 1.72% on an 18% win rate: a mass of tiny
stopped-out positions, which is what churn looks like from the inside.
At band 25 the win rate doubles to 38% while the median loss deepens,
because the small-loss churn has gone and what is left are positions
that had room to move.

**Wanted before this is believed:** the random-thinning control, re-run
on universe B. Removing 30% of names at random and seeing what it does
to the same figures is the only thing that separates "the band removed
churn" from "the band removed a third of the universe and any third
would have done". That control exists for universe C and was decisive
there; it has not been run here, and this is the universe where it
matters.

---

## W2b — was any of it ever significant?

W2 compared point estimates. This asks whether either side of that
comparison was distinguishable from noise.

**The first version of this test asked the wrong question.** I computed
`t = Sharpe x sqrt(years)` on the account's raw return, which for an
always-parked account is mostly a test of whether SPY beat zero. The
question is whether the strategy beats the *index*, so the statistic has
to be the information ratio on active return — strategy minus benchmark,
period by period.

| window | rule | universe | CAGR | IR | active t |
|---|---|---|---|---|---|
| 2021-2026 | R20 | survivor-biased | +16.21% | 0.17 | 0.43 |
| 2021-2026 | R20 | corrected | +12.09% | 0.10 | 0.25 |
| 2021-2026 | M9 | survivor-biased | +23.70% | 0.43 | 1.07 |
| 2021-2026 | M9 | corrected | +4.35% | -0.70 | **-1.66** |
| 2010-2020 | R20 | survivor-biased | +15.54% | 0.27 | 0.96 |
| 2010-2020 | R20 | corrected | +7.02% | -0.30 | **-1.07** |

### Nothing cleared 2.0, before or after

The +11.55% over buy-and-hold that W2 was written to investigate had an
active t of **1.07**. It was noise before the universe was corrected.
The correction did not destroy a real edge; it moved a point estimate
from positive-and-insignificant to negative-and-insignificant.

This tempers W2's own write-up. I called that result decisive. It is
decisive about the point estimate — the sign flips consistently across
all three arms — and it is not decisive about anything statistical,
because neither side reaches a conventional bar. The defensible sentence
is: **no window tested in this project has ever shown a statistically
significant edge over the index**, and correcting the universe removed
even the appearance of one.

Worth noting the corrected underperformance is not significant either.
"This loses to the index" is a direction supported by three of three
arms, not a measured quantity. What would settle it is more windows, and
the honest reading of a t of -1.66 across five years is that five years
cannot settle it.

---

## W3 — the liquidity filter does not rescue it

W2 left one way out: the corrected universes are 3.3x larger and include
thousands of names too small to trade, so the collapse might have been
microcaps rather than survivorship. This restricts the corrected
universe to names with median dollar volume above $1M a day over the
year *before* the window opens.

All figures always-parked, costs charged, active t against SPY.

| window | rule | universe | trades | CAGR | B&H | edge | maxDD | t |
|---|---|---|---|---|---|---|---|---|
| 2005 | R20 | all names | 5,670 | +4.57% | +0.99% | +3.58% | -45.8% | -0.05 |
| 2005 | M9 | all names | 45,899 | -0.24% | +0.99% | -1.23% | -35.3% | -0.43 |
| 2010 | R20 | all names | 7,885 | +7.02% | +13.77% | -6.75% | -43.6% | -1.07 |
| 2010 | M9 | all names | 89,070 | +12.82% | +13.77% | -0.95% | -27.7% | 0.25 |
| 2010 | R20 | liquid only | 2,878 | +14.67% | +13.77% | +0.91% | -32.2% | 0.29 |
| 2010 | M9 | liquid only | 51,823 | +11.28% | +13.77% | -2.49% | -29.1% | -0.25 |
| 2021 | R20 | all names | 6,225 | +12.09% | +12.15% | -0.06% | -55.8% | 0.25 |
| 2021 | M9 | all names | 40,067 | +4.35% | +12.15% | -7.81% | -30.7% | -1.66 |
| 2021 | R20 | liquid only | 3,668 | -0.07% | +12.15% | -12.23% | -48.9% | -1.40 |
| 2021 | M9 | liquid only | 29,528 | +5.74% | +12.15% | -6.41% | -26.7% | -1.55 |

### The filter helps in one window and hurts in the other

R20 over 2010-2020 goes from -6.75% to +0.91% when illiquid names are
removed. R20 over 2021-2026 goes the other way, from -0.06% to -12.23%.
M9 moves the opposite direction in each. There is no consistent story
here, which means the liquidity floor is not a fix — it is another
parameter with a window-dependent sign, and this project has enough of
those.

### The untuned rule now loses in all three windows
M9 is the honest rule — three conditions, taken from the literature,
never fitted. Corrected, it returns -1.23%, -0.95% and -7.81% against
buy-and-hold. R20, the rule mined from the winners, wins one window,
loses one badly and ties one.

Drawdowns are -28% to -56% throughout, against an index that fell about
as far. Whatever else is true, "index-like returns at half the drawdown"
is dead several times over.

**No arm anywhere in this table reaches |t| = 2.** Nothing here is
distinguishable from noise in either direction.

---

## A correction: two earlier arms lost rows and their results are withdrawn

Auditing logged trade counts against persisted rows found two arms
disagreeing:

| arm | logged | in database |
|---|---|---|
| s1r_B_pit_all_R20 | 5,383 | 4,422 |
| s1r_B_pit_all_M9 | 80,863 | 39,918 |

Every other arm checked matches exactly, including all of today's. The
engine does not duplicate trades — probing 45 and then 300 universe-B
names returns exactly as many unique keys as trades, and persists all of
them. So this is lost rows, not collapsed duplicates.

Both affected arms were written while the database was still inside the
Google Drive tree. A sync client reconciling a stale copy underneath an
open SQLite file would produce exactly this, and it is the failure mode
that prompted moving the database out. I cannot prove that retroactively
and I am not going to pretend otherwise.

**What this invalidates:** the 2005-2009 row of the T4 policy table was
computed from those two arms. Replaced by the w2_2005 arms above, and
the replacement changes a sign — M9 over 2005-2009 was reported at
+1.78% always-parked, beating buy-and-hold by 0.79 points. It is
actually **-0.24%, losing by 1.23**. The one window where the untuned
rule appeared to win, it does not.

---

## T3 — daily bars are worse, and that is operationally good news

Weekly bars are Weinstein's medium because that is what a chartist could
maintain by hand, not because anything established weekly as the right
sampling rate. Universe C, same window, same rule, only the bar interval
changed. Buy and hold: +0.99%/yr.

| days | trades | CAGR | vs B&H |
|---|---|---|---|
| 20 | 27,206 | -2.52% | -3.52% |
| 50 | 26,371 | -3.55% | -4.54% |
| 100 | 35,979 | -1.64% | -2.63% |
| 150 | 45,717 | -2.64% | -3.63% |
| 200 | 53,395 | -2.97% | -3.96% |

Every daily arm loses to the index, and every one is worse than its
weekly equivalent. The 150-day arm is the same rule as `t1_ma30` at a
different sampling rate and is **2.65 points worse**.

The mechanism is churn. A trailing stop checked on daily bars is tested
five times as often as one checked weekly, so positions are stopped out
sooner and re-entered more: 45,717 trades against 15,445 for the same
rule. That is the whipsaw T5 measured, arriving through the sampling
rate instead of the entry threshold.

**Practically: watching this more closely makes it worse.** For someone
who cannot sit in front of screens, that is the useful direction for
this result to point.

### The control I designed could not have worked
`t3_d150` was supposed to reproduce `t1_ma30`'s 15,445 trades as a units
check. It returned 45,717, and I nearly read that as a scaling bug —
but a daily stop genuinely fires more often, so the counts *should*
differ and the control cannot separate "units wrong" from "daily churns
more". Both predict more trades.

The right check compares the averages themselves: across 400 names the
150-day and 30-week averages differ by a median of **0.55%**, with all
400 inside 5%. The units are correct; the difference is real.

### Weekly, shorter is better
For comparison, on weekly bars: 5 weeks +0.67% over the index, 10 weeks
+1.63%, 20 weeks -0.54%, 30 weeks -0.98%, 40 weeks -2.52%. The canonical
30 is fourth of six, and the two shortest are the only ones that beat
buying the index.

---

## T5c — the entry band has a real mechanism

The control T5b needed. Band 25 finished on 2,617 of band 0's 3,723
names, so: take the band-0 rule unchanged, thin the universe at random
to 2,617, and see whether the improvement follows the *count* or the
*rule*. Three seeds.

| arm | trades | CAGR | vs B&H |
|---|---|---|---|
| random thin, seed 1 | 26,563 | +0.52% | -0.47% |
| random thin, seed 2 | 26,656 | +0.58% | -0.41% |
| random thin, seed 3 | 26,812 | -0.20% | -1.19% |
| **band 0**, all 3,723 names | 39,205 | **+1.78%** | +0.79% |
| **band 25**, 2,617 names | 4,904 | **+4.46%** | +3.47% |

**Removing 30% of the names at random makes it worse** — +1.78% falls to
+0.30% on average. Removing the same proportion *via the entry band*
makes it better, +1.78% to +4.46%. The three seeds span 0.78 points, so
the control is tight enough to carry the comparison.

This vindicates T5b's mechanism, which the ticker-count fall had put in
doubt. The band is not merely reducing participation; participation
reduction on its own costs about 1.5 points, and the band gains 2.7. It
is the one finding tonight that survived its own control.

---

## T5d — the 15-to-20 step is a ramp, not a threshold

T5b showed most of the band's effect arriving between two adjacent
settings while every other neighbouring pair moved by fractions of a
point. Either a real threshold sat between them or 20% was simply where
the grid landed. Bands 17 and 18 settle it.

| band | trades | tickers | entries/ticker | win% | CAGR | vs B&H | active t |
|---|---|---|---|---|---|---|---|
| 0% | 39,205 | 3,723 | 10.53 | 18.2 | +1.78% | +0.98% | -0.15 |
| 10% | 13,533 | 3,656 | 3.70 | 33.4 | +1.92% | +1.12% | -0.15 |
| 15% | 9,648 | 3,476 | 2.78 | 35.4 | +1.68% | +0.89% | -0.02 |
| **17%** | 8,407 | 3,333 | 2.52 | 36.0 | **+2.10%** | +1.31% | -0.07 |
| **18%** | 7,836 | 3,256 | 2.41 | 36.4 | **+2.95%** | +2.15% | 0.18 |
| 20% | 6,826 | 3,082 | 2.21 | 36.9 | +4.51% | +3.71% | 0.39 |
| 25% | 4,904 | 2,617 | 1.87 | 38.1 | +4.46% | +3.66% | 0.39 |
| 30% | 3,552 | 2,143 | 1.66 | 39.4 | +4.36% | +3.56% | -0.11 |

The two new bands fall between their neighbours and the curve climbs
monotonically: 1.68, 2.10, 2.95, 4.51, with increments of 0.42, 0.85 and
1.56. That is a ramp into a plateau, not a step. The apparent
discontinuity was the grid being too coarse between 15 and 20, which is
what a boundary artifact looks like and why the extra bands were run
rather than the shape being argued about.

### None of it is significant
Active t against SPY runs from -0.15 to +0.39 across all eight bands.
Every figure in the table is indistinguishable from noise. The shape is
consistent and the mechanism survived its thinning control, and neither
of those is the same as evidence. This is a plausible refinement, not a
demonstrated one.

### The benchmark moves with how weekly bars are built
Rebuilding the cache changed buy-and-hold for this window from the
+0.99% recorded earlier to +0.80%, and the daily source gives +0.48%.

The cause is bucketing. A weekly bar carries the *last* daily close of
its week, so the benchmark's starting price is 2005-01-07 at 79.87
rather than 2005-01-03 at 81.12. SPY fell that week, and the lower base
inflates the measured rate. The daily figure is the honest one: buy at
the first available close, sell at the last.

Half a point of slack sits under every "vs buy-and-hold" number in this
document. It does not change any ranking, because arms within a
comparison share a benchmark, and it does change the absolute claims.
**Wanted:** compute the benchmark from daily bars regardless of what the
strategy is sampled on.

---

## E1 — day of the week. Refuted, and it found a worse bug on the way

Registered before running: any effect would be under ~2%/yr gross,
unstable between halves, and gone after costs. Exploratory and
acknowledged as such — 5 days x 5 slices is 25 looks, so the Bonferroni
bar is t = 2.88.

### A one-day timing error was worth eleven points a year

The first pass compared each day's close with its own trailing average
and then collected *that same day's* return. The return is earned during
the day; the close does not exist until the day is over. Lagging the
signal so it uses only prices from the previous close changes the plain
200-day timing rule from **+19.48%/yr to +8.45%/yr**.

| window | lagged | buy and hold | edge | with lookahead |
|---|---|---|---|---|
| 2005-2026 | +8.45% | +10.97% | **-2.52** | +19.48% |
| 2005-2015 | +6.06% | +7.05% | -0.99 | +16.88% |
| 2015-2026 | +10.90% | +14.87% | -3.98 | +22.14% |
| 2010-2026, no 2008 | +9.66% | +14.15% | -4.49 | +20.88% |

Corrected, the timing rule loses to buying and holding in every window
while cutting the worst drawdown from -55% to -21%. That is the same
answer the rest of this register keeps giving: insurance, not an edge.

The lookahead version was stable across halves, survived removing 2008,
and held at 20bp costs. Every robustness check passed. **A defect that
passes robustness checks is what a defect looks like from the inside**,
and the only thing that caught it was the number being too good.

### No day effect survives a proper test
Testing a day against zero inside a trend filter mostly re-measures the
trend. Against the *other four days in the same regime*:

| regime | day | difference | t |
|---|---|---|---|
| down | Tue | +31.65bp | 1.99 |
| down | Mon | -28.61bp | -1.51 |
| up | Mon | +5.31bp | 1.63 |

Nothing reaches 2.88, or even 2.0.

### The tradeable version is a diluted trend filter
Sitting out one weekday while the index is below its average:

| rule | CAGR | vs B&H |
|---|---|---|
| sit out Mon | +12.56% | +1.65 |
| sit out Tue | +7.21% | -3.70 |
| sit out Fri | +10.72% | -0.19 |
| random 20% of days | +9.37 / +9.61 / +8.44% | -1.30 to -2.47 |

Monday is the only variant above buy-and-hold, on an underlying t of
-1.51, and it sits inside a five-day spread running from -3.70 to +1.65.
One draw of five looking good is what five draws do.

**Closed.** No day-of-week edge, and the exercise was worth it for the
lookahead alone.

---

## E2 — a SATA-shaped score. The attributes do not just fail to help, they cost

SATA is closed, so this is a ten-attribute proxy built from the six
categories its author discloses: price and moving averages, relative
strength against the index, momentum, volume, breakouts, overhead
resistance. Traded on the stated bands. Universe B, 2005-2009, equal
weight, weekly. SPY over the window: +0.80%/yr.

**Registered control, written before running:** "enter above 7, exit
below 3" is a hysteresis band, structurally identical to the buy/hold
spread already validated here, so a price-only band of similar
selectivity runs beside it. If the two match, the attributes are
decoration.

| rule | CAGR |
|---|---|
| score, enter >= 7, exit <= 3 | +4.47% |
| score, enter >= 6, exit <= 4 | +2.26% |
| score, enter >= 8, exit <= 2 | +3.55% |
| price band 0% (control) | +1.59% |
| price band 10% (control) | +4.32% |
| **price band 20% (control)** | **+7.65%** |

The prediction was too generous. A plain price-versus-30-week band at
20%, with no scoring at all, beats every version of the ten-attribute
score. And the score's best result is almost exactly a 10% price band.

So the score's performance is explained entirely by the dead zone it
incidentally creates, and a dead zone built on purpose does it better.
Nine extra attributes dilute the one that works. That is the same
mechanism T5 and T5c established, arriving by a different route.

**Limits:** one window, and a crash window at that; this is a proxy
rather than SATA; **no transaction costs are charged**, which flatters
whichever rule trades more; and no significance test — these are point
estimates.

---

## E3 — cyclicals and dividends. The rule subtracts value in every bucket

Each bucket held outright, against the same bucket traded with the trend
rule. Where the rule adds nothing, the bucket is a tilt.

| sector | hold | rule | rule adds |
|---|---|---|---|
| Healthcare | +13.33% | +6.99% | -6.34 |
| Energy | +12.77% | +11.05% | -1.72 |
| Basic Materials | +12.24% | +0.49% | -11.75 |
| Consumer Defensive | +11.53% | +7.55% | -3.98 |
| Industrials | +8.17% | -1.78% | -9.95 |
| Utilities | +7.78% | +4.20% | -3.58 |
| Technology | +7.59% | -0.39% | -7.98 |
| Communication Services | +3.36% | -4.76% | -8.12 |
| Real Estate | +2.28% | -13.20% | -15.48 |
| Consumer Cyclical | +1.42% | +0.37% | -1.05 |
| Financial Services | -4.88% | -10.63% | -5.75 |

**Sixteen buckets, sixteen negatives**, from -1.05 to -15.48. The sector
spread is large — Healthcare +13.33% against Financials -4.88% while the
index returned +0.80% — and every point of it is available by holding.
The rule earns none of it. That was the registered expectation and it
holds without exception.

### The dividend half is void on a units error
Quintile 1 came back with an average yield of **24.62%**, which is
impossible for common stock. Nominal dividends from the actions table
were divided by split-adjusted prices: for any name that later split,
the adjusted 2005 price is far below what it actually traded at, and the
ratio inflates accordingly. The quintiles are therefore not sorted by
yield and nothing is concluded from them.

Wanted: dividends adjusted on the same basis as the prices, or yields
read from a fundamentals table that computes them consistently.

---

## F1 — does a fundamental leg add anything the price legs do not?
### Registered 2026-08-11, before any data was looked at

The question behind it: if a name passes several screens, is that
stronger evidence than passing one? Only if the screens make
*independent* errors. This project has twice found they usually do not —
ten SATA-shaped attributes lost to a single price band, and TMFC
correlates 0.97 with SPY. Stacking correlated signals adds confidence
without adding information.

So the test is not "do three screens agree". It is whether the one
genuinely orthogonal ingredient carries signal the existing ones lack.

### Why fundamentals rather than a second price screen
Mapping CAN SLIM against what the current screen already measures:

| criterion | already covered? |
|---|---|
| N — new highs | yes, the 52-week-high test |
| L — leader not laggard | yes, Mansfield RS |
| M — market direction | yes, the market gate |
| S — supply and demand | partly, volume confirmation |
| **C, A — earnings growth** | **no** |
| **I — institutional sponsorship** | **no** |

Three of six are the same measurements under different names. Only
earnings growth and institutional ownership are new, and both sit unused
in `fundamentals` and `holdings`. A second momentum screen would re-ask
a question already answered; this asks a new one.

### Hypothesis, stated before looking
**H1.** Among names already passing the price screen, those in the top
quintile of earnings growth outperform the bottom quintile by more than
random selection of the same size.

**H0.** No difference beyond what random thinning produces.

**Prediction, on the record:** I expect H1 to fail, or to survive only
in the derivation window and die out of sample. Every added filter this
project has tested has cost more than it earned — four independent
routes to that finding — and the base rate for a new one working is low.
Writing that down now so a positive result cannot be reported as
expected and a negative one as obvious.

### Design
- **Universe:** the corrected point-in-time sets already built
  (`pitU_2010`, `pitU_2021`), so survivorship is handled from the start
  rather than discovered afterwards.
- **Point-in-time discipline:** fundamentals joined on `datekey`, never
  `calendardate`. A late filing carries an old calendardate, and joining
  on it would leak a figure that was not public on the checkpoint date.
  This is the same defect just fixed in the refresh path.
- **Derivation:** 2010-2020. **Holdout:** 2021-2026, reserved and not
  examined until the derivation result is written down.
- **Controls, both required:**
  1. *Random thinning* to the same surviving name count — the control
     that rescued the entry band in T5c and would have exposed the
     day-of-week result as a diluted trend filter.
  2. *Shuffled fundamentals* — the same screen with earnings figures
     randomly reassigned between tickers. Preserves every distributional
     property and destroys only the link to the company. If the real
     data does not beat the shuffle, the fundamental leg is decoration.
- **Benchmark:** buy-and-hold computed from **daily** bars, not weekly.
  Weekly bucketing moved the 2005-2009 benchmark by half a point and
  that error should not propagate into new work.
- **Significance:** active t against the index, reported alongside every
  figure. Given how many looks this project has taken, nothing below
  t = 3.0 will be described as a finding.

### What would count as each outcome
- **Support:** top quintile beats both controls in derivation *and*
  holdout, at t > 3.0.
- **Refuted:** fails either control, or survives derivation and dies in
  holdout — which is the outcome I expect.
- **Void:** if the fundamentals join turns out to leak, the arm is
  discarded rather than patched and re-read.

---

## D4 — the liquidity floor and quantised volume

Registered and run 2026-08-19, after finding that `filter_by_liquidity`
scores `close * volume`. That product is a level, not a ratio, so unlike
a return it has nothing to cancel a scale error. The question was whether
the floor had been admitting names it exists to exclude, which would put
W3's published conclusion in doubt — dollar volume is the one measure
where a price defect cannot divide out.

**Registered expectation: the floor is contaminated and W3 has to be
withdrawn.** That is not what happened, and the reasoning that produced
the expectation was wrong in an instructive way.

### What the data actually does

Vendor prices arrive already adjusted. The adjustment is correct: for a
reverse split, historical prices are divided by the split factor and
historical volumes multiplied by it, so `close * volume` is invariant and
liquidity looks the same either side of the split.

It stops being invariant when the multiplied volume falls below one
share, because volume is stored as a whole number and rounds up to a
floor of 1 instead of holding its true fractional value. The price keeps
its full inflated value; the volume it should be multiplied against does
not.

JAGX is the clearest case. Seven reverse splits between 2018 and 2026
give a cumulative factor near 8e-11, so its May 2015 close is carried at
$84,096,088,812 against a volume of exactly 1. Sixteen consecutive bars
around its 1-for-70 split in June 2019 all sit at volume 1, each
reporting $69M to $210M of turnover for a company that trades about
$100,000 a day now that the splits are behind it.

This is not a tail case. **2,790,333 of the archive's 46,254,680 price
bars sit on the volume floor (6.03%), across 5,265 of 21,941 tickers.**

| share of a ticker's bars on the floor | tickers |
|---|---|
| ≥ 10% | 5,265 |
| ≥ 25% | 2,956 |
| ≥ 50% | 1,114 |
| ≥ 75% | 195 |

### Why the floor survived it anyway

The inflation is real but it starts from a penny-stock price, so it
lands in the thousands rather than the millions. Measured over six
scoring windows spanning 1998 to 2025:

| scoring window | quantised names | median score | clearing the $1M floor |
|---|---|---|---|
| 1998 Q4 | 934 | $11,303 | 3 (0.3%) |
| 2003 Q4 | 634 | $7,171 | 8 (1.3%) |
| 2009 Q4 | 552 | $3,675 | 5 (0.9%) |
| 2015 Q4 | 389 | $4,126 | 13 (3.3%) |
| 2020 Q4 | 199 | $5,447 | 11 (5.5%) |
| 2025 Q1 | 170 | $6,183 | 2 (1.2%) |

So the defect pushes these names *up*, and still not far enough to reach
a floor set in the millions. Checked directly against the W3 arms: of
the 91 quantised tickers in the 2010 all-names arm, 90 were dropped by
the floor, and their median score was **$6,350** against a $1,000,000
threshold. The 2021 arm behaves the same way — 30 of 34 dropped, median
score $1,770.

| arm | tickers | quantised | their trades | mean return, clean | mean return, quantised |
|---|---|---|---|---|---|
| w2_2010_R20 | 2,467 | 91 (3.7%) | 476 (6.0%) | +2.675% | +8.222% |
| w3_2010_R20 | 1,150 | 1 (0.1%) | 1 (0.0%) | +4.308% | −33.466% |
| w2_2021_R20 | 2,579 | 34 (1.3%) | 98 (1.6%) | +1.033% | +29.909% |
| w3_2021_R20 | 1,610 | 4 (0.2%) | 8 (0.2%) | +0.977% | −11.659% |

All figures above are absolute per-trade returns, not an edge over the
index.

**W3's published conclusion stands unchanged.** The liquidity floor did
not admit these names; it removed almost all of them, on genuinely low
scores.

### The returns on these names are not defective either

The all-names arms show quantised tickers averaging +8.2% and +29.9%
absolute per trade against clean means near +1%, which looks like
contamination and is not. Of **3,295 trades on quantised-volume tickers
across four arms, 5 straddle a suspect-units jump** that no recorded
corporate action explains — and those five average −27% absolute. The
median trade on a quantised ticker is *negative* (−14.95% and −11.13%);
the mean is carried by a small number of genuine winners, the largest
being APLD's +4,058% absolute, already corroborated at 138x normal
volume.

Reverse-splitting is a marker for failing microcaps, and failing
microcaps are high-variance. That is a property of the names, not of the
data.

### What is actually at risk

A *threshold* on dollar volume survives this. A *ranking* does not. The
handful of names that clear the floor clear it by factors of 10^3 to
10^9 — JAGX scores $1.13 quadrillion a week in the 2020 window — so they
sort to the very top of any list ordered by liquidity. Nothing in this
project ranks by dollar volume today. The moment something does, it
would take these first.

### The fix

`market_core.liquidity` replaces the arithmetic. `dollar_volume()`
returns **None** rather than a number when the bars it would be computed
from are on the storage floor, because the true volume was destroyed by
rounding and cannot be recovered from adjusted data. Quantised bars are
excluded from the mean, and a name whose window is more than a quarter
quantised is reported as *unmeasurable* rather than *thin* — a data
fault should not be recorded as a judgement about tradability.

`filter_by_liquidity` now delegates to it. 19 tests, each confirmed to
fail against three separate mutations of the guard.

### What this cost and what it bought

The registered expectation was wrong and the published result needed no
correction, which makes this a negative result. It was still worth
running: the defect is real, it is large, and the reason it did no
damage here is a property of penny-stock prices rather than anything the
filter was designed to do. That is luck, and luck that is not written
down gets spent twice.

---

## D5 — return-window alignment (Chan, queue item 5)

Registered and run 2026-08-19. Chan's point is that a backtest can pass
every look-ahead check and still credit a position with return from
before the decision that bought it. `market_core.lookahead` cannot see
this: truncation catches a rule that *consults* future bars, and a rule
that decides correctly then books the wrong window decides identically
either way. Only the accounting differs. That is the gap the 200-day
rule fell through, where the leaky and the lagged versions both pass
truncation at 2,220 against 2,219 positions.

**Invariant:** the bar a position's return starts from must be at or
after the bar its decision was made on.

### The tolerance is not a fudge

Bar timestamps are not decision timestamps. Across all 1,785,881 trades
the distribution is sharply bimodal: 47.57% enter exactly on the
decision date, 52.43% enter one or two days before it, and **zero**
enter between one week and several months after. That gap is the
signature of a weekly bar stamped at its open being evaluated at a
checkpoint on its close. A tolerance of one bar interval separates the
convention from the fault; anything beyond it is a real violation.

### Result

**475 of 1,608,633 trades in the modern arms violate it — 0.030%.**

| family | arms | violations | note |
|---|---|---|---|
| w2 / w3 / t5b / t5c / t3 | 26 | **0** | every published survivorship, band and daily-bar figure |
| b* / wf* / t1* | 66 | 1–7 each | 147 tickers, leads of 139–391 days |
| s1 / s1r pit_all | 4 | 711 and 136 | already withdrawn for lost rows |
| earliest exploratory | 24 | 60–90% of trades | `as_of_date` logged as the run date; invariant unmeasurable |

**Every arm behind a published conclusion is clean.** That is the result
worth having, and it was not knowable before running this.

### Direction, stated carefully

Aggregated over the modern arms the violating trades average **+15.13%
absolute** against **+2.29%** for the rest — a 12.84-point excess, the
direction a genuine leak produces. That aggregate is misleading on its
own and the per-arm figures say why: the two arms with large violation
counts show *negative* excess (−0.56 and −1.24 points), and the whole
aggregate is carried by three trades in `b22_test_M9_trend_gated` at a
+140.37-point excess. So there is leak-shaped bias present, concentrated
in a handful of trades, moving the overall mean by roughly four
thousandths of a point.

My "first checkpoint" hypothesis for the mechanism was **wrong** — only
10.3% of violations sit at an arm's opening checkpoint. The mechanism is
still unidentified and is recorded in known-gaps rather than guessed at.

### The check

`market_core.alignment` — `violations()`, `report()`, `check()`. It
reports the excess as well as the count, because a check that only ever
says "failed" gets switched off. 20 tests, confirmed to fail against
three mutations, including one that deduplicated violations by content
and would have collapsed two identical trades into one.

`tests/test_return_alignment.py` pins the 26 published arms and asserts
the withdrawn arm still violates, so the check cannot quietly stop
detecting anything. It also asserts it examined at least 20 arms — a
test that passes because it looked at nothing reads as protection.

---

## B1 — the benchmark is the wrong index, and how much that is worth

Chan's objection, queue item 1: a benchmark has to match the securities
traded. This screen surfaces mid- and small-cap names and every figure in
this file is measured against SPY, so some part of every "edge" and every
"shortfall" is the size spread rather than the strategy.

Measured on daily dividend-adjusted bars over the declared windows:

| window | SPY | IWM | IJR | MDY | IWM − SPY |
|---|---|---|---|---|---|
| 2005-2009 | +0.48% | +0.80% | +1.55% | +3.24% | **+0.32pt** |
| 2010-2020 | +13.72% | +12.32% | +12.85% | +12.35% | **−1.40pt** |
| 2021-2026 | +12.99% | +6.13% | +7.80% | +9.27% | **−6.85pt** |

All absolute CAGR, not an edge over anything.

IWM is the right instrument rather than VTWO, which Chan's argument would
otherwise favour: VTWO's history starts 2010-09-22 and cannot reach the
2005 window at all. IWM covers 2000-05-26 onward. Its adjustment is clean
— `closeadj/close` runs 0.7131 to 1.0000 monotonically over 26 years,
about 1.3% a year of dividend accrual, which is what a small-cap ETF
should look like and is emphatically not the FTHI failure mode.

**The 2021 window is where this bites.** Published edges there run from
−0.06% to −12.23% against SPY. Against a size-matched index every one of
them improves by 6.85 points, which would turn the R20 all-names arm from
a tie into a win.

### The parking confound, and why it is smaller than it looks

The always-parked arms hold SPY whenever cash is idle, so measuring them
against IWM credits the strategy for a large-cap holding it actually
made. That objection is real and I expected it to sink the restatement.
It does not, for a reason worth recording: **deployment is 99.2%**. The
account is fully invested and turning away 3,832 of 6,225 signals for
want of capital, so there is almost nothing being parked. Swapping the
parking vehicle from SPY to IWM moves the result by about one point —
and moves it *up*, from +10.38% to +11.41%. The confound exists, it is
roughly a sixth of the size spread, and it runs in the strategy's favour
rather than against it.

### Why the table is not restated here

**The published portfolio-level figures cannot currently be reproduced.**
Against the same trades, the same code and either surviving bar cache,
`w2_2021_R20` returns +10.38% or +10.55% where the published figure is
+12.09%. A sweep over capital, stake and cash-yield does not close the
gap; the closest is 1.71 points short, and the result turns out to depend
only on the capital-to-stake ratio, so there is no configuration left to
find.

The cause is that `~/market-data/cache/weekly_sharadar.pkl` is a
**dangling symlink** into a scratch directory that no longer exists. That
was the cache the W2 and W3 arms were computed against. Every trade is
still in the database with its entry price, exit price and dates intact,
which is why the gap is 1.7 points rather than total — what is missing is
the bar series used to mark the 77 still-open positions and to run the
SPY parking leg.

So the size spread above is solid and the restated edge column is not.
Restating it needs every arm re-run under a pinned configuration against
a cache that will still be there afterwards. Registered as the next
runnable item rather than guessed at.

### What this changes about how arms get recorded

An arm that cannot be recomputed is a claim rather than a result. The
trade table records `parameter_set` but nothing about the data the run
consumed, so nothing failed loudly when the cache went away — the figures
simply became unverifiable, and stayed quotable. Recording a cache
identity and a row count against each arm would have caught this the
first time an arm was re-read.
