# Known Gaps and Deferred Work

What I know is wrong, missing, or deliberately postponed. Separate from
[CHANGELOG.md](../CHANGELOG.md) on purpose: that file records what
happened and can't go stale, whereas this one lies the moment something
gets fixed and nobody prunes it. If an item here is done, delete it.

Numeric thresholds have their own file —
[parameter-calibration.md](parameter-calibration.md) — since the question
there isn't "is this missing" but "how much evidence does this rest on".

## Correctness risks still open

**The universe prefilter is untested.** `_could_still_qualify` decides
which tickers get fully evaluated at all. It's derived as a necessary
condition — assume the pending sector lookup resolves favourably and ask
whether that could clear the bar — so in principle it can't discard a
real candidate. But I reasoned the swing rule through the same way and
testing it against the book's worked example caught a real error, so
reasoning alone has a poor track record here. A false negative in this
function is invisible: the ticker simply never appears.

**The fund/stock discriminator is only partly validated.** `is_fund`
keys on ETF-specific fields being populated, which I checked in aggregate
against fund-like names: 3,338 agreed, 16 didn't. I never inspected the
16, nor the 343 unflagged instruments whose names *do* look fund-like — I
assumed those are REITs and trusts. If the field is ever populated for an
ordinary company, that stock vanishes from the universe silently.

**Positional pairing of daily series.** Relative strength now pairs stock
and index by date, but the sector-ETF and SPY daily closes feeding
condition 5 are still zipped positionally. Verified identical over 30
sessions, so it isn't currently wrong, but it's the same latent bug in a
different place.

## Methodology not yet implemented

**Stop placement — investigated and closed, not a gap.** Mine sits at the
low of the recent consolidation, around 22% below entry on liquid names,
against the 5-6% in the book's worked examples. I chased that gap through
the lookback window, the entry basis, and a full rework that picked the
nearest level rather than the lowest, and none of them explain it. What
does: a 5% stop is inside ordinary weekly noise on modern equities, so
the book's percentages don't transfer to a weekly-bar screener even
though its placement principle does. Written up in
[parameter-calibration.md](parameter-calibration.md); recorded here only
so it doesn't get reopened as though it were still unexplained.

**The book's trailing rule is implemented but underperforms mine.**
Chased as the explanation for partial profit-taking failing, and it
isn't one: measured over 200 tickers, following the 30-week average
returns +2.86% a trade against −2.99% for the book's correction-based
rule. The rule is available as `trailing_method='book'` and stays there
because the failure is likely mine rather than the method's — the
confirmation threshold that decides when the stop may move is a number
I invented to operationalise "rallies back close to its prior peak",
and too strict a value produces precisely the symptom observed, which
is a stop that almost never moves. Worth revisiting by sweeping that
threshold rather than by rereading the book. See
[parameter-calibration.md](parameter-calibration.md).

**The short-side checklist.** Only a heuristic pointer exists in the
summary output. The book's rules aren't symmetric — volume confirmation
is required for a valid long breakout and explicitly not for a short
breakdown — so this can't be built by inverting the nine conditions. I'm
holding it until the market-stage read itself starts showing Stage 3 or
4, which is when it would actually be used.

**Base quality doesn't gate anything.** A base's width is measured and
reported, but a name can qualify on a 39%-wide "base" that isn't really a
consolidation. Reported rather than enforced, because I'd rather set that
threshold from data than invent another number.

**No stage-transition history.** A universe scan stores only the names
that could qualify, so there's no record of a stock crossing from Stage 1
into Stage 2 over successive weeks — which is exactly the transition the
method is built to catch. Storing all ~6,800 evaluations weekly would fix
it at a cost in database size.

## Measurement limitations

Backtest figures carry caveats that no amount of code will fix on their
own:

- Trades cluster heavily — five tickers made up roughly half of both
  samples measured so far.
- Every window tested sits inside a bull market. Condition 6 exists to
  keep you out of a Stage 4 market and has never been exercised against
  one.
- The universe is current listings only, so anything delisted is absent
  and results are survivorship-biased.
- Median R is negative in both samples: the typical trade is a small loss
  and the edge lives in the tail, which makes headline averages less
  stable than the trade count suggests.

## Technical debt

- **`--limit` takes a prefix, not a sample**, so a limited universe run
  is not representative of the market. Fine for smoke tests, misleading
  for anything else, and the help text doesn't say so.
- **Whether thin names *perform* as well is untested.** The liquidity
  floor now sits where data integrity breaks, and names reach the
  prefilter at the same rate regardless of liquidity — but qualifying at
  the same rate isn't the same as working out as well, and the backtest
  has never been segmented by liquidity to check.
- **`historical_levels` mislabels its windows.** On weekly bars, "5D" is
  a single bar and "all_time" means "as far back as the evaluation window
  reaches", not all time.
- **Condition-override plumbing uses monkeypatching.** `run_backtest`
  temporarily rebinds module constants. It restores them reliably, but a
  parameters object threaded through would be safer and self-documenting.

## Deliberately not built yet

These are premature rather than missing. Recording them so they don't get
re-litigated:

- **A GUI, or any rendered architecture diagram.** The condition logic is
  still moving — three of the nine conditions changed materially in a
  single week — so anything that pins down the current shape would
  document a snapshot that's already wrong. Worth doing once the
  checklist stops changing.
- **Trade execution.** The tool is read-only decision support. Order
  placement is a different risk category entirely and needs the screening
  logic to be trustworthy first.
- **Anything hosted or multi-user.** See
  [db-decision.md](db-decision.md); SQLite is the right answer until
  there's a second user or a live frontend, and neither is planned.
- **Automated scheduling.** Weekly bars mean a weekly cadence, which is
  cheap to run by hand and gives me a reason to look at the output rather
  than let it accumulate unread.
