# Known Gaps and Deferred Work

What I know is wrong, missing, or deliberately postponed. Separate from
[CHANGELOG.md](../CHANGELOG.md) on purpose: that file records what
happened and can't go stale, whereas this one lies the moment something
gets fixed and nobody prunes it. If an item here is done, delete it.

Numeric thresholds have their own file —
[parameter-calibration.md](parameter-calibration.md) — since the question
there isn't "is this missing" but "how much evidence does this rest on".

## Two arms of the pre-registered batch never ran

R6 (trader's-way exits) and R7 (moving-average variants) need code that
doesn't exist. Six of eight were tested; these are recorded rather than
dropped so the denominator stays honest.

R6 is the more interesting of the two, and the case for it survives the
failed batch: it's the only registered rule that would sell on *time*
rather than on price — exiting a position that has gone sideways for
months. Everything tested so far only ever exits on a stop, so a trade
that stalls ties up capital indefinitely. R7 is cheap to build now that
`moving_averages` already has a weighted average.

**Read them against the run, though.** Six arms varied entries, exits,
gating and stage detection, and the spread between best and worst was
about four points a year against a deficit of eight. Nothing suggests a
seventh variation closes it.

## The checklist rewrite is no longer the priority (2026-07-29)

The section below records that the scoring model contradicts the book,
which is still true and still worth knowing. What changed is its
standing as a *fix*: R2 tested exactly that correction — hard gates
instead of the 8-of-9 ratio — and it made results worse, cutting trades
by 91% and returning +0.44% a year against the baseline's +3.47%.

So the divergence from the source is real, and closing it is not the
route to a working system. Keep the section for accuracy; don't read it
as a roadmap.

## The checklist doesn't match the book (found 2026-07-28)

These came out of reading the source directly rather than my own summary
of it. They sit above everything else in this file: the items below are
bugs in an implementation, these are the implementation being of the
wrong thing. Full detail in [methodology.md](methodology.md).

**The scoring model contradicts the book explicitly.** Scoring nine
conditions as a ratio and admitting anything at or above 0.80 means any
single condition may fail. The book poses that exact case — every factor
positive except volume confirmation — and answers that it must not be
overlooked, because the missing confirmation is itself the warning. Its
own checklist is a sequence of steps that discard candidates, and its
"don't buy" list is introduced as rules never to violate. Nowhere does
it count conditions or tolerate a shortfall.

Consequence: `ACTIONABLE_SCORE`, `MIN_RESOLVED_CONDITIONS` and
`NON_NEGOTIABLE_CONDITIONS` are all scaffolding around a model that
shouldn't exist. The last one is the tell — it was added because scoring
alone admitted setups that were obviously wrong, which is the design
failing and being patched instead of replaced.

**The 15% stop limit is a purchase rule, implemented as a scoring
factor.** The book says to work out the stop before placing the buy
order and to restrict purchases to those risking no more than 15%. Here
it fails condition 9 and nothing more, so a setup whose stop sits 60%
below entry still qualifies on 7 of the remaining 8. This is the direct
cause of the −62% and −63% trades in the liquidity segmentation: not a
stop that failed, but a purchase the method forbids.

**"Don't buy too late in an advance" isn't implemented.** It's on the
book's never-violate list. Here the only related check is an advisory
`extended` flag on the entry plan, and it measures distance above the
*breakout level* rather than above the moving average — two different
things. A stock can break out of a tight base that is itself 174% above
its 30-week average, read as barely extended, and carry a stop two
thirds of the way down the chart. `IMCC` did exactly that and lost 63%.

**Overhead resistance isn't checked.** The book says to discard
candidates with heavy resistance nearby — resistance *above* the entry,
capping the move. `resistance_breakout` checks that a level was cleared,
which is a different question. Nothing looks up.

**The round-number refinement is absent**, and can't be implemented on
the current data — see the dividend-adjustment item below.

## Price data is dividend-adjusted, which is right for returns and wrong for charts

Confirmed 2026-07-28 by inspection: historical bars are scaled down to
bake in reinvested dividends. `AGNC`, yielding around 13%, reads $1.52
in 2008 against $10.59 now; `T` is scaled by about 4.7x over 23 years
and `SPY` by about 1.55x, each matching its own yield compounded over
its own span. There is no unadjusted option on the bars endpoint,
though `get_corp_action` exposes dividend events, so an unadjusted
series could be reconstructed.

**Good news first: this means dividends are already accounted for on
both sides**, and DRIP is effectively modelled, so the backtest returns
and the buy-and-hold comparison are both total-return figures and remain
comparable. Nothing in the measured results needs revisiting.

The problem is the chart, not the arithmetic. Stage analysis reads crowd
behaviour at price levels people actually paid, and those levels have
been scaled away. Support, resistance and the 30-week average all sit on
a synthetic series, and the book's round-number rule — put the stop just
under $20 because orders pile up there — is not implementable, since
adjusted $20 was never a real price.

**Sized honestly, it's a smaller problem than that sounds.** The
screener looks back 104 weeks, so the distortion is bounded by roughly
two years of dividends: about 4% for a typical 2% yielder, 8% for a
utility, 28% for a mortgage REIT. Meaningful for high-yield names,
marginal for most. Ranked below the checklist items above, which are
costing 60% on individual trades today.

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
that it keeps me out of a Stage 4 market — is fully testable against
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

## The product this is becoming (stated 2026-08-02)

Recorded here rather than in the changelog because none of it is built.

A portfolio manager, not just a screener. It should hold my current
positions, suggest what to replace with what, say what share of the
stake each should take, maintain trailing stops on what I already own,
set initial stops on anything new, and keep scanning for prospects. I
check it once a day after the close, verify its suggestions against my
own charts, and tell it what I actually did.

**That last step is not a formality.** A record of suggested-versus-taken
is the only forward evidence this project will ever generate, and every
figure recorded anywhere in these docs is a backtest.

### What it reprioritises
Two items registered as refinements are now core features:

- **M2, risk-based sizing.** "What share goes into each" *is* the
  requested output, not an accuracy improvement to a backtest.
- **M8, ranking by relative strength.** "What to replace with what" is a
  ranking question. A pass/fail gate cannot answer it — and batch 8
  showed relative strength carries a monotone gradient in all three
  windows that a threshold discards.

### What it adds that does not exist
- **Portfolio state**: holdings, cost basis, live stop levels, and the
  suggested-versus-taken log.
- **Stop maintenance on open positions.** Trailing stops are computed
  inside the backtest and surfaced nowhere. Different code path.
- **A daily post-close run.** Worth being honest that the strategy is
  weekly-bar based, so a daily check mostly re-reads a bar still being
  formed. Useful for catching a stop, not for producing daily signals,
  and it should not be built to imply otherwise.

### Privacy requirement
Real holdings never enter the repository. Same pattern already used for
config/tickers.json and data/screener.db: a committed
`config/portfolio.example.json`, the real file gitignored.

### Broker-agnostic costs (supersedes M6 as written)
M6 hard-coded Webull's schedule. Generalise instead: a broker profile
carrying commission per trade, per share and percentage, regulatory
pass-throughs, minimums, and short borrow, with Webull shipped as one
profile among several. The breakeven sweep then answers "does this
survive at *this* broker" rather than at one specific broker, which is
the more useful question and no harder to build.

## Stretch features — revisit deliberately, not by default

### After-hours gap alert
Monitor open positions during extended hours and fire a hard alert on a
severe gap. Sized against 3.4M overnight gaps on liquid names, 2021-2026,
assuming 25 held positions:

| threshold | alerts per year |
|---|---|
| >=5% | 208 — nearly nightly, will be ignored |
| >=10% | 75 |
| **>=15%** | **42 — about weekly, the suggested start** |
| >=20% | 27 |

Median overnight gap is 0.60%, 99th percentile 11.29%, so 15% is
genuinely unusual.

**Threshold choice is the whole problem; the plumbing is trivial.** An
alert that fires 208 times a year is one I learn to dismiss, which is
worse than none because it creates false confidence.

Delivery, in order of whether I would actually notice: phone push
(ntfy.sh is free, one HTTP POST), macOS notification with sound, terminal
output (useless). Something has to be awake at 6pm for any of it.

**Frame it as information, not an execution trigger.** Extended-hours
spreads run 1-5%, and our edge sits in the thinnest quartile where there
is often no after-hours bid at all. Knowing a position gapped is worth
having. Concluding I must act tonight is how the alert costs more than
the gap did.

### Modelling after-hours trading in the backtest — decided against
The whole gap problem is worth 0.16 to 0.28 points per trade. Recovering
part of it through extended-hours exits, at 1-5% spreads, in names that
frequently have no bid, is not worth the modelling effort — and Sharadar
is end-of-day only, so it could not be tested rigorously anyway.

## The database lives in a synced folder

`data/screener.db` sits under the project, which is inside a Google
Drive CloudStorage folder. Two consequences, one of which has already
cost a run:

- **Concurrent arms fight for the lock.** A six-band sweep died on
  "database is locked" in its final band after four hours, because a
  second backtest was started while it ran. Five of six bands survived;
  the sixth was partial and had to be discarded. The connection timeout
  is now 60 seconds rather than Python's default 5.
- **Every trade is its own write transaction.** `insert_backtest_trade`
  does a DELETE then an INSERT per trade, so a 40,000-trade arm is
  80,000 transactions against a file the sync client is uploading
  underneath them. `SCREENER_DB` now redirects the path, so a long run
  writes to local disk and `merge_backtest_trades` folds it back.

Neither is fixed properly. The real fix is either moving the database
out of the synced tree or batching the inserts into one transaction per
arm, and the second is the better one.

**Update 2026-08-06:** the database has been moved to
`~/Library/Application Support/weinstein-screener/screener.db`. The
first attempt to copy it failed its own verification — row counts
differed by one, because a backtest still had the file open — so the
move was deferred behind the running arms and repeated once they
finished. The remaining half of this gap is real: inserts are still one
transaction per trade.

## Sharadar's fund `closeadj` is broken for distribution-heavy ETFs

Found while running a live screen, not by a test. FTHI ranked third in
the market on twelve-month momentum with a return of **7,946,566%**. Its
adjusted close a year earlier is recorded as $0.0003 against a real
price of $23.00 — the dividend adjustment has been divided toward zero.
FTSL and FTSM are the same. Seventy funds fail the check.

Stocks are unaffected: `prices` behaves correctly on every name tested.

The separator is drift in `closeadj/close` across the window. Healthy
series move a few percent; broken ones move by four or five orders of
magnitude. `tests/test_adjustment_integrity.py` pins both sides,
including the named broken funds — if Sharadar repairs them that test
fails, which is correct, because loosening the gate should be a
deliberate decision.

**Not fixed, only detected.** Any screen touching `fundprices` must
apply the drift gate or it will rank corrupt series at the top. Nothing
enforces that yet outside the scratch scripts.

## Splits are adjusted; 3% of cases warrant a look

639 splits since 2015 checked by comparing the close either side.
**96.6% show a ratio near 1**, meaning the series is adjusted. The 22
that do not are *not* unadjusted — none of them match their own split
factor, and several show large falls where an unadjusted reverse split
would show a rise. They are distressed microcaps that collapsed
immediately after reverse-splitting, which is a real price move.
