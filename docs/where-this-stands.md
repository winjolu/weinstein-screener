# Where this stands

Current state of belief, as of 2026-08-06. `preregistered-tests.md` is
the audit trail and records tests in the order they were run, including
the ones I got wrong and withdrew. This is the summary that sits on top
of it.

Read this first. Read that to check whether I am telling the
truth here.

---

## The one-paragraph version

This started as an implementation of Weinstein's stage analysis and has
become a test of it. The nine-condition checklist is dominated: a
two-line trend rule plus a market-regime filter beats it on
risk-adjusted terms in every window tested. The method's real
contribution turns out to be one thing — staying out of a falling market
— and it does that well.

**Survivorship has now been measured, and it was carrying the result.**
On point-in-time universes the advantage over buying the index survives
only in the window containing the crash. Across the 2010s and the
post-2021 recovery the strategy loses to the index by six to eight
points a year. What is left is not an edge but insurance: premiums paid
in good years against a payout in the bad one. That may still be worth
owning, and it is a different thing from what this project set out to
find. **No money should be committed on the strength of anything in this
repository.**

---

## What appears to be true

Ordered by how much correction each has survived.

**1. The method's value is bear-market avoidance, and that part is
real.** Over 2005-2009 the plain untuned checklist returned +8.19% a
year against the index's +0.80%, at a third of the drawdown. This
appears in the *baseline*, before any tuning, so it does not depend on
anything I fitted. It is the only finding that has survived every
correction made to the measurement.

**2. Simpler is better, and by a wide margin.** Price above its 30-week
average, a positive 12-month return, and the same test applied to the
index — three conditions — beats the nine-condition checklist on Martin
ratio in all three windows (0.80 vs 0.65, 1.45 vs 0.87, 1.25 vs 0.65)
and spends less time under water in each.

**3. Selectivity has been costing more than it earned.** Four
independent routes to the same conclusion: volume confirmation removes
17-20% of trades without improving their quality; the stop ceiling
removes 80% and loses to random thinning on Martin; tightening the mined
thresholds raises per-trade return while leaving account return flat;
and the trend rule picks *worse* individual trades than the checklist in
every window and wins anyway on ten to fifteen times the participation.
Under fixed capital with fat-tailed returns, a filter's value is
systematically overstated because backtests report per-trade statistics
while accounts experience participation.

**4. Relative strength carries a real gradient.** Monotone on both win
rate and mean per trade across all three windows, without exception.
Nothing else here has replicated that cleanly.

## What has been refuted, including by me

**"Index-like returns at half the drawdown."** I said this. It was
wrong. Open positions were valued at cost, so unrealised losses were
invisible, and the percentage was divided by starting capital rather
than the running peak. Real drawdowns are two to three times what was
reported, and over 2021-2026 the strategy fell *further* than the index
while returning less.

**"The 52-week-high threshold has the wrong sign."** Withdrawn. It
trades hit rate for magnitude deliberately, which is what a fat-tailed
strategy needs. I read a win-rate gradient as evidence of quality on a
system whose returns live in magnitude — after writing down two sections
earlier that win rate is nearly worthless here.

**"A liquidity floor belongs in the universe filter."** Withdrawn. The
thinnest quartile of names returns +13.23% in the test window and
survives 1% slippage; the most liquid quartile returns +0.46%. The floor
would have deleted the band the edge lives in. The real constraint is
capacity, not spread.

**"Shorting will provide bear-market exposure."** Closed. It loses to
sitting in cash and buying the recovery by six points a year in the one
window built to favour it, before borrow costs that are highest on
exactly the names that look most attractive.

**"Survivorship bias does not inflate our results."** Refuted, and it
was my claim. The acquisition reasoning was sound and the conclusion was
still wrong: 60% of the missing companies were acquired, acquisitions
usually leave at a premium, and correcting the universe *still* removed
the entire advantage over the index in both bull windows. R20 over
2010-2020 goes from +1.77% over buy-and-hold to -6.75%; M9 over
2021-2026 from +11.55% to -7.80%, a nineteen-point swing. I had flagged
that +11.55% as probably an artifact, which is the only part of this I
got right.

One qualification, which is a real one and not a hedge: the corrected
universes are also 3.3x larger, because point-in-time construction adds
the small names the old universe never contained as well as the dead
ones. Part of the collapse may be trading names too illiquid to trade.
The liquidity-filtered arm that separates these is running.

## What is unresolved, in order of how much it matters

**1. Whether anything survives the correction.** Survivorship is no
longer unresolved — it was measured and it inverted the result, exactly
as the phantom-loss injection predicted it would. What is unresolved is
whether a liquidity floor recovers any of it, or whether the method
simply does not beat the index outside a crash. Those are very different
outcomes and the arm deciding between them is running.

**1b. What idle capital does, which outweighs everything above.**
Holding the index rather than cash between positions is worth three to
six points a year. The entire strategy edge, at its most generous, was
worth about one. Roughly 200 arms have gone into tuning entry rules
while the largest lever in the system sat unregistered as a default —
and under cash-only the same trades that beat the index in the 2010s
lose to it.

**2. Statistical significance.** Harvey, Liu and Zhu (2016) argue a new
factor needs t > 3.0 rather than 2.0, because hundreds have been tried
against the same data, and that empirically-discovered factors need a
higher bar than theory-derived ones. This project has run 25+ arms and
mined its central rule from the winners. R20 never clears 3.0 and clears
2.0 once in three windows. The only arm clearing 3.0 anywhere is the
trend rule taken unchanged from the literature.

**3. Time under water.** 132-182 weeks below a prior peak in every
window, against the index's 45-102. Three years and more. This is the
largest practical obstacle to anyone actually holding this, and no
drawdown-depth measure reveals it — only Ulcer and duration do.

**4. Nothing has been traded, on paper or otherwise.** Every figure here
is a backtest. The forward-record infrastructure exists and has logged
nothing.

## What would change the conclusion

- **Survivorship measured and small.** Would make the bear-market
  finding trustworthy rather than provisional.
- **M9 holding up on data it has never seen.** Its three parameters are
  far harder to overfit than the checklist's twenty-five arms of
  searching, which is the strongest argument in its favour.
- **A forward record that matches the backtest.** The only evidence that
  cannot be tuned after the fact.

Any of those failing should end the project rather than prompt another
variant. The count of arms run is itself now a liability.

## What this repository is actually good for

Independent of whether the strategy works, the engine does things most
retail backtests do not: point-in-time evaluation with no lookahead,
mark-to-market drawdown, broker-agnostic transaction costs with a
breakeven sweep, six risk-adjusted measures including duration,
survivorship census from primary SEC filings, ticker-identity resolution
against permanent company identifiers, and a random-thinning control
that separates "this filter selects" from "this filter merely reduces
trade count".

That last one changed a conclusion three times. It is the piece I would
reuse first on any other strategy.
