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
relative to owning the index, and the low drawdown is what you get in
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
