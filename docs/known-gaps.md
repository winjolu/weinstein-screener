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

**The security-type classifier rests on two exchange conventions, and
one of them is only mostly reliable.** `classify_security_types` now
keeps preferreds, units, warrants and closed-end funds out of the scan,
which removed 75 of 309 actionable names. What it rests on:

- The ` PR<letter>` notation is unambiguous and I trust it outright.
- The five-letter Nasdaq suffix is not. It needs a tradability
  confirmation to avoid classifying `GOOGL` as an Alphabet preferred,
  and that confirmation is a 100% margin requirement — which is a
  *liquidity* signal being borrowed as a *type* signal. It happens to
  separate the cases I checked, but it isn't measuring the right thing,
  so a liquid preferred with a five-letter symbol and no ` PR` notation
  would be admitted, and an illiquid second share class could be
  wrongly excluded. `UONEK` (Urban One Class D) is the near-miss: it
  survives only because `K` is on the share-class exemption list.

The exemption list — A, B, C, K — is mine, derived from the cases I
found rather than from the convention's definition. A share class using
some other letter would be silently dropped.

**Validated against 52 hand-labelled symbols with no mismatches**, which
is reassuring but is 52 out of 10,163, and they're the cases I already
knew to look for. `--include-non-common` exists so the exclusion can be
measured rather than trusted.

**The reverse direction is still unchecked.** 16 instruments disagreed
with the old `is_fund` in an aggregate check and I never inspected them.
If an ETF field is ever populated for an ordinary company, that stock
disappears from the universe with no trace — and widening the fund test
to three fields widened that exposure too.

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

**`CORRECTION_RECOVERY_PCT = 3.0` is known-bad and awaiting a decision.**
The sweep is done and it confirmed the guess: 3.0 is far too strict, and
the book's trailing rule improves from −2.06% to +1.26% a trade as the
threshold loosens. At 1% nearly half of all positions never resolve,
because the stop can't move until the stock is within 1% of its old
high. The rule still loses to the 30-week average (+2.85%) even at its
best, so the default is unaffected — but the constant is left at a value
now known to be wrong, on a non-default code path, which is a trap for
whoever reads it next.

The decision it's waiting on isn't "what number": performance improves
monotonically all the way to a threshold so loose it barely constrains
anything, which argues the confirmation gate itself is the problem
rather than its calibration. Either set it to ~10%, which is at least
coherent with the 8-10% correction the rule already requires, or remove
the confirmation step and re-measure. Retuning it to the sweep's
favourite would be fitting the number to one window. See
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
method is built to catch. `report --diff` now surfaces the crossings it
*can* see, but it can only compare names that cleared the prefilter in
both scans, so a stock crossing into Stage 2 for the first time tends to
appear as an arrival rather than as a transition. Storing all ~6,800
evaluations weekly would fix it at a cost in database size.

## Measurement limitations

**Condition 5 can only resolve for the last ~4.8 years of any backtest.**
Sector strength is computed from daily bars, the server caps any request
at 1200 of them, and there is no paging parameter to reach further back.
So a test spanning 2015-2026 is running an eight-condition checklist for
its first six years and a nine-condition one after that. The two halves
aren't the same strategy, which limits what a long-window result can say
about the method as it currently stands.

**But condition 6 is not affected, and that's the one that matters most
for a long test.** The market-stage read comes from weekly index closes,
which reach back 23 years, so the claim the whole method rests on —
that it keeps you out of a Stage 4 market — is fully testable against
2008 even though sector strength isn't. A long-window result should
therefore be read as strong evidence about crash behaviour and weak
evidence about the checklist as currently configured.

Backtest figures carry caveats that no amount of code will fix on their
own:

- Trades cluster heavily — five tickers made up roughly half of both
  samples measured so far. Worse on the long window: of 273 trades over
  2015-2026, the top three produced $2,657 of $2,729 total profit, so
  the other 270 made $72 between them.
- ~~Every window tested sits inside a bull market.~~ **Condition 6 has
  now been exercised against a real Stage 4 market and it works.** Over
  2005-2026 the index spent 64 weeks below its 30-week average inside
  the 2008 decline, and the method entered exactly one trade in that
  18-month window out of 395 total. Across the whole 21 years only 3.0%
  of entries occurred with the index below its average. Worst equity
  drawdown was −9.7% against the index's −54.6%. The crash-avoidance
  claim is validated; what remains unvalidated is whether avoiding
  crashes at this cost is worthwhile, since the same runs return
  +1.2-3.3% a year against the index's +10.4%.
- The universe is current listings only, so anything delisted is absent
  and results are survivorship-biased.
- Median R is negative in both samples: the typical trade is a small loss
  and the edge lives in the tail, which makes headline averages less
  stable than the trade count suggests.

## Technical debt

- **`--limit` takes a prefix, not a sample**, so a limited universe run
  is not representative of the market. Fine for smoke tests, misleading
  for anything else, and the help text doesn't say so.
- **`report --diff` can't tell a market change from a scope change.** It
  compares two stored scans without knowing what arguments produced
  them, so diffing a `--limit`ed run against a full one reports the
  difference in coverage as names entering and leaving. The 07-26/07-27
  pair shows this: 85 arrivals and no departures, which is a wider scan
  rather than a market event. The scan doesn't record its own arguments,
  which is what would fix it.
- **Thin names perform much worse, and the reason is stop distance.**
  Measured 2026-07-28 across five liquidity bands, 45 tickers each. The
  $1-5M band returned −15.14% a trade with 12 of 15 trades losing;
  trimming both the best and worst trade makes it *worse* (−18.05%), so
  it's a bad population rather than one disaster. Deep losses past −30%
  were 4 of 15 in the thinnest band and 0 of 55 in the largest.

  The mechanism is not the stop failing — every deep loser exited at or
  inside its planned risk. It's that the planned risk was enormous to
  begin with, because the stop goes at the consolidation low and thin
  names consolidate raggedly:

  | band | median stop distance below entry |
  |---|---|
  | $1-5M | 37.1% |
  | $5-15M | 41.2% |
  | $15-50M | 36.5% |
  | $50-200M | 25.3% |
  | $200M+ | 16.5% |

  So a single stop-out on a thin name costs ~40% of the position, by
  design. `MAX_SENSIBLE_STOP_PCT = 15` does not prevent this: it fails
  condition 9 and nothing more, so a setup with a 40% stop still
  qualifies on 7 of the remaining 8 conditions. **The open question is
  now whether that ceiling should be a hard gate rather than one
  condition of nine** — see [parameter-calibration.md](parameter-calibration.md),
  where the ceiling's placement was decided on a different argument.

  The $1M floor itself is not the thing to change: it was set where data
  integrity breaks and that reasoning still holds. This is a separate,
  higher floor for *tradability*, or a gate on stop distance, and I'd
  rather fix the risk directly than proxy it through liquidity.

- **No liquidity band showed a reliable edge**, including the largest.
  $200M+ returned +4.20% a trade, but trimming its best and worst trade
  drops it to +0.18% — a single +242% winner is the entire result, and
  31 of its 55 trades lost money. Across all 167 trades in the
  stratified sample the method returned −1.42% a trade. That is a
  different sample from the 198-ticker runs that return around +2.85%,
  and the difference is itself informative: those samples are liquid,
  and the method's positive results have been coming from liquid names.
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
