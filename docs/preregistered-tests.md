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
