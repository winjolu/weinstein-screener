# Changelog

What has actually changed in this project, newest first.

There are no version numbers or releases yet — this is a single-user tool
that I run rather than ship, so entries are grouped by date instead. I'll
add versioning if that ever stops being true.

This file is deliberately backward-looking. Known gaps, deferred work and
technical debt live in [docs/known-gaps.md](docs/known-gaps.md), and the
provenance of the numeric thresholds lives in
[docs/parameter-calibration.md](docs/parameter-calibration.md). Keeping
them apart means this file can't go stale: what happened stays true,
whereas a list of intentions needs pruning to stay honest.

## [Unreleased]

### Added
- A portfolio layer, which is what turns this from a screener into
  something usable while holding positions. `screener/portfolio.py`
  tracks holdings and cost basis, maintains trailing stops that ratchet
  up only, and detects a stop being touched on the bar's *low* rather
  than its close — a stop is an order resting in the market and fills
  when price trades through it, not when the week happens to close
  below. Real holdings live in a gitignored `config/portfolio.json`;
  only the example is committed.
- A recommendation log, which is the first forward evidence this project
  has ever produced. Everything else recorded here is a backtest over
  history I have already read, on an engine whose defects keep
  surfacing; a row written before the outcome is known cannot be tuned
  afterwards. Suggestions declined are kept alongside those taken, and
  the outcome field stores text rather than a boolean so "bought half"
  and "waited a week" survive as themselves.
- `screener/daily_review.py`, the once-a-day check. Stops on weekdays,
  purchases only once the weekly bar has closed — a breakout read on a
  Wednesday sits on a bar with two days left to change its mind. Every
  suggestion commits to a share count, a price and a stop, because
  output that can't be checked against a chart can't be argued with or
  scored later.
- A broker-agnostic cost model. `screener/costs.py` carries commission
  per trade, per share and percentage, minimums, caps, regulatory
  pass-throughs and a borrow rate, with Webull as one profile among
  several rather than the assumption.
- Mark-to-market equity, risk-based position sizing, and a two-line
  time-series-momentum rule to run head to head against the nine-condition
  checklist.
- EDGAR identity resolution for all 5,803 cached symbols, plus every
  delisting notice filed with the SEC since 2004 — 36,346 of them across
  11,448 companies.
- Full daily bar history: 2,628 symbols, 9.9M bars back to 2005. Webull's
  1200-bar cap turned out to be per *request*, not a limit on depth; the
  `end_time` parameter pages backwards and reaches 1993.

### Fixed
- Every drawdown figure this project had reported was understated, some
  by three times. Open positions were carried at cost, so an unrealised
  loss showed nothing until the trade closed. A second bug sat behind
  it: the percentage was divided by *starting* capital, so a compounding
  account produced impossible readings — one printed as -113%, which is
  what finally exposed it. The corrected claim is narrower than the one
  I had been making: a large drawdown advantage in a crash, a modest one
  in a long bull market, and a disadvantage over the last five years.
- The book's 15% stop ceiling was measured everywhere and enforced
  nowhere, on both sides of the book. It only ever failed one condition
  of nine, which the 80% scoring ratio outvotes — and the best-performing
  rule disables that condition outright. On the short side, where the
  stop sits above entry and losses are unbounded, this produced trades
  losing 2,573% and 10,444%: the engine shorted a $0.03 stock with its
  stop at a prior resistance of $0.80. On the long side it produced a
  median stop 36% below entry and a worst single loss of -83%.
- A ticker is not a stable identity. Webull maps a symbol to whoever
  holds it now, so requesting GM with an end date in 2008 returns bars
  belonging to a company that no longer exists. EDGAR's CIK is the
  identifier a ticker isn't.

### Changed
- Mined signal features, universe definitions and delisting records now
  live in the database rather than scratch files. This was not
  housekeeping: the scratch files were deleted between sessions, and
  every batch script that read them would have failed. The database
  copies are what kept the work.

### Fixed
- A losing arm reported its annual return as a complex number. When
  realised losses exceed the capital base, the CAGR calculation takes a
  fractional power of a negative, and Python returns a complex value
  rather than raising — so the figure printed as "-1.89+26.38j%",
  formatted cleanly, and passed through every downstream format string.
  An account wiped out past zero is -100% a year and there is nothing
  further to compound.
- An experiment harness bug that nearly cost the only positive result of
  the night. `kwargs.pop()` against a module-level arm list consumed the
  value during the derivation phase, so the test phase silently fell back
  to the default and the weekly-checkpoint arm ran as the baseline —
  reporting byte-identical numbers. I would otherwise have written that
  weekly checkpoints fail out of sample, which is precisely the shape of
  a real finding and would have been false. Caught only by the standing
  rule that two arms agreeing exactly means a broken experiment rather
  than an inert change.

### Investigated, no change made
- **Ran the pre-registered tests on the full universe. Every arm failed,
  and the abandonment condition I wrote in advance has fired.**

  Six of eight registered rules, 2,627 mid-cap-or-larger names, derived
  on 2010-2020 and tested out of sample on 2021-2026. Best arm returned
  3.86% a year against the index's 11.78% — short by 7.9 points, on
  2,798 out-of-sample trades. This is no longer the small-sample
  ambiguity that muddied every earlier result; the baseline alone has
  6,151 derivation trades against the 273 everything used to rest on.

  Three findings I did not expect:

  **The baseline beat four of the five modifications**, including both
  rules taken straight from the book. R2 — hard gates instead of the
  8-of-9 score, the change I'd argued was the most important thing in
  the project — cut trades by 91% and returned +0.44% a year against the
  baseline's +3.47%. Restoring the source's own structure made it worse.

  **R5 was my pick to succeed and was the worst arm.** The argument was
  that it changes exits rather than removing trades, so unlike every
  filter it couldn't destroy the winners by excluding them. It destroyed
  them by capping them instead: banking half a position at 40% above the
  average takes the runners off exactly while they run. Out of sample it
  turned a +1.10% average trade into -0.12%.

  **R8 — curvature in the stage read — was the only arm to improve on
  the baseline, and did so in both windows** (+0.37 points a year in
  derivation, +0.39 out of sample, higher win rate in both). Consistency
  across an out-of-sample split is worth more than a bigger one-off
  number. It still isn't significant — its bootstrap 5th percentile sits
  below the baseline's mean — and 0.4 points does not touch a 7.9-point
  deficit.

  I also have to record that criterion (b) as I wrote it was nearly
  vacuous: it compares a resampled mean against the baseline's *median*,
  and on a distribution skewed this hard (median -3.84%, mean +1.10%)
  almost anything clears it. Every arm passed (b), including arms
  returning zero. It changes no verdict, since (a) fails for all of
  them, but I specified it in advance and got it wrong.

  What this does not show is that stage analysis doesn't work. It shows
  this implementation, on this universe, over these windows, with eight
  conditions and no costs, earned roughly a third of what owning the
  index earned. Every standing caveat — survivorship, no commissions,
  condition 5 unavailable — points the same way and would widen the gap.

  The one component that clearly works is unchanged: condition 6 kept
  the method out of the 2008 decline almost entirely, at a -9.7% worst
  drawdown against the index's -54.6%. The defence is real. It is bought
  with about two thirds of the return.

### Added
- `bar_cache.py`: the whole common-stock universe's weekly history, held
  locally. 5,808 symbols, 3.8 million bars, back to August 2003, in 350
  MB and about fifteen minutes.

  Every conclusion this project has reached has been limited by sample
  size rather than by method — the eleven-year study ran 100 names, and
  three of its 273 trades carried the entire profit, which is why every
  risk filter I tested destroyed the result by removing one of them. I
  had assumed the data was expensive to get. It isn't: the batch endpoint
  takes 20 symbols at 1200 bars, so the market is 291 calls away. The
  bottleneck was never acquisition.
- `run_backtest` reads from that cache and can skip the sector lookup.
  A 40-name run over 2010-2020 went from network-bound minutes to six
  seconds; 2,223 names projects to about six minutes against roughly
  forty hours. Sector strength can't resolve before ~2021 anyway, since
  daily bars cap at 4.8 years, so paying a call per ticker for it was
  buying nothing.

  A symbol missing from the cache now says so out loud. Silent exclusion
  is the failure this project has hit three times already — pagination
  truncating the universe at 40,000, one bad ticker killing nineteen good
  ones in a batch, the sector fetch dying inside a bare except — and a
  cache miss looks exactly like a stock that never qualified.
- `MAX_EXTENSION_ABOVE_MA_PCT`, a gate on how far above the 30-week
  average a stock may sit and still be buyable. Off by default. "Don't
  buy too late in an advance" is on the book's never-violate list and had
  no implementation; the only related check measured distance above the
  *breakout level*, which is a different quantity. Written as a gate
  rather than a tenth condition so it can't be outvoted by the other
  nine, which is the failure it exists to close.

  Measured at the bar a purchase fills on, not at the scan date. The
  first version used the scan date and was wrong in a way that looked
  plausible: scans see a breakout a median of four weeks late, so it
  rejected trades over a run-up that happened after the price paid, and
  it blocked re-entry after a stop-out, since a recovered stock is
  extended when next scanned. Armed at 40% it removed 226 of 273 trades
  and enabled no replacements at all.
- `docs/preregistered-tests.md`, written and committed before running
  any of it. I have now seen every result in this dataset, which makes me
  unable to tell a principled hypothesis from one I noticed in the
  output and am about to confirm on the same data. Each candidate rule is
  marked with its provenance — from the book, structural, or noticed in
  the data — since a rule taken from the source text cannot have been
  fitted to results, and one I spotted in a chart very much can.

### Changed
- Rewrote `docs/methodology.md` against the source text rather than
  against my own earlier summary of it, after a 62% loss in the
  liquidity segmentation turned out to be a trade the book forbids
  rather than a stop that failed.

  The summary had recorded a nine-condition checklist where "at least 8
  of 9 must be met". That rule isn't in the book. Its buying process is
  an ordered funnel whose steps discard candidates, and its list of
  conditions not to buy under is introduced as rules never to violate.
  Where it describes a setup it likes, all the criteria are met — it
  never counts them.

  The book also addresses the 8-of-9 construction directly, asking
  whether poor volume on a breakout can be overlooked when everything
  else is positive, and answering that it can't, because the missing
  confirmation is itself the danger signal. So the scoring model isn't
  an approximation of the method; it's the reasoning the method warns
  against.

  Also corrected: `MAX_SENSIBLE_STOP_PCT = 15` was documented here as
  arbitrary, a midpoint I'd split between two other figures. It is in
  fact the book's own stated limit, and framed as a rule about which
  stocks may be bought rather than a factor to weigh. It has been the
  least-trusted threshold in the project on the strength of a note I
  invented, while being the best-sourced one.

  Nothing in the code changed. The divergences are written up in
  known-gaps and methodology so the diagnosis is recorded before any of
  it is acted on.
- Confirmed the price bars are dividend-adjusted, by inspection: AGNC at
  a ~13% yield reads $1.52 in 2008 against $10.59 now, and the scaling
  factors for T and SPY each match their own yield compounded over their
  own span. Dividends and reinvestment were therefore already in every
  figure measured, on both the strategy and the buy-and-hold side, so
  none of those comparisons need revisiting. It does mean stage analysis
  is reading synthetic price levels, which matters most for high-yield
  names and makes the book's round-number rule unimplementable.

### Added
- `portfolio_sim.py`, which turns a list of simulated trades into what an
  account would have done: a fixed stake into every signal, tracked over
  a calendar, reported as a yearly rate against simply buying the index.
  Trade statistics answer "was each signal good" and that turns out to be
  a different question from "should I run this," because a respectable
  average trade says nothing about how long money was committed or how
  much of it sat idle. Reports return on both peak and average capital,
  since peak alone is unfairly harsh and average alone is unachievable.
- `docs/what-testing-can-show.md` — the four ways a backtest lies, in
  plain terms, and which of them this project has actually closed off.

### Fixed
- Any backtest starting more than about 3.3 years back ran with condition
  5 unresolved at every single checkpoint. `run_backtest` sizes its daily
  sector request to span the whole test window, the server refuses any
  count above 1200 outright rather than truncating, and a bare `except`
  swallowed the refusal — so the run completed, produced trades, and
  looked exactly like a good one. Every count is now clamped and says so.
  I had the 1200 cap written down in the API reference already; knowing a
  limit and enforcing it turn out to be different things.
- Sector data was refetched per ticker during a backtest, so a 200-ticker
  run spent 200 identical requests on the same SPY daily series — about a
  third of its API budget and a third of its wall-clock time on data it
  already had. Memoised for the life of the process.
- The universe was screening instruments that stage analysis doesn't
  apply to, and they were topping the list. Preferred shares inherit
  their parent's sector and drift narrowly above a rising average, so
  the checklist passed them for entirely the wrong reasons — `AGNCL`,
  `AGNCO` and `ADAML` all scored 9 of 9, the highest in the market.
  Closed-end funds got in too, because the fund test keyed on a field
  only ETFs populate. `classify_security_types` now sorts the universe
  into common, fund, preferred, unit, warrant and right, and a scan
  takes common stock only. 10,163 screenable instruments resolve to
  5,816 common, 3,702 fund, 449 preferred and 196 unit; the actionable
  list went from 309 names to 234, and every one of those is now common
  stock carrying a real sector.

  Two conventions do the work and they needed different handling. The
  ` PR<letter>` notation is unambiguous, and my first attempt to
  corroborate it against a 100% margin requirement wrongly rescued 24
  genuine preferreds like `JPM PRC` that are liquid enough to be
  marginable. The five-letter Nasdaq suffix is the opposite case: it
  needs that corroboration, or `GOOGL` classifies as an Alphabet
  preferred.

  What I didn't use is the margin requirement on its own, which was my
  first idea and is wrong in the expensive direction: `GCBC`, `LARK`,
  `SBFG` and `ATLO` are ordinary community banks that also carry 100%
  margin, and they're exactly the small-cap Stage 2 names the screener
  exists to surface. Filtering on it would have deleted them silently.

### Added
- A reporting layer, `screener/report.py`, for reading back what a scan
  already found. The scan stores a full condition breakdown for every
  name reaching the prefilter and printed almost none of it; the only
  ways to see any of it were a 300-name terminal dump or hand-written
  SQL. Three views: `--ticker` for one name's checklist, stop, entry plan
  and scoring history; `--diff` for what changed between two scans, with
  Stage 1 to Stage 2 crossings called out first because that transition
  is the whole point of the method; and `--actionable` for the current
  shortlist grouped by sector rather than ranked flat, since the book's
  sequence is top-down and six names from one sector is itself a signal.
  Database only, no API calls, so it runs instantly and offline.
- Two `db` helpers the reports needed: scan dates, and results scoped to
  one scan. Diffing had no way to ask for a specific run.
- The book's own trailing-stop rule as `trailing_method='book'`: waits
  for a correction of at least 8-10%, holds off until the stock rallies
  back near its prior high, then places the stop under the correction
  low or the average depending on which is lower, and tightens onto the
  correction low once the average flattens into a likely Stage 3 top.

### Fixed
- A checkpoint predating a ticker's first bar left an empty series and
  crashed the evaluator — 318 silent "list index out of range" failures
  in a single backtest run, each one a discarded checkpoint. A stock
  that didn't exist yet is an unknown, not an error. Results were
  unaffected, since those checkpoints could never have produced trades.

### Investigated, no change made
- **The method sits out crashes exactly as advertised, and still loses
  to buying the index.** Two windows over 100 mid-cap-or-larger names,
  every signal taken, $1,000 a trade.

  | | 2015-2026 | 2005-2026 |
  |---|---|---|
  | trades | 273 | 373 |
  | win rate | 38.8% | 38.1% |
  | per trade | +1.00% | +1.72% |
  | account, per year | +0.9% to +2.4% | +1.2% to +3.3% |
  | SPY, per year | +12.4% | +10.4% |

  Condition 6 is vindicated and it's the clearest success here. The
  index spent 64 weeks below its 30-week average during the 2008
  decline; the method took one trade in that entire 18-month stretch out
  of 395. Across 21 years only 3.0% of entries happened with the index
  below its average, and worst equity drawdown was −9.7% against the
  index's −54.6%.

  What it costs is the rest of the result. Money sits in the market
  about 29% of the time, so the strategy behaves like a mostly-cash
  portfolio: small drawdown, and a return that over 2005-2026 is roughly
  what short-term treasuries paid, while carrying real equity risk.

  Profit is also concentrated past the point of meaning anything. Over
  2015-2026 the three best trades produced $2,657 of $2,729 total, so
  the remaining 270 trades made $72 between them; excluding the top
  five, the other 268 lost $1,102. Bootstrapping 100-trade runs out of
  that population, 27% of them lose money outright and the 5th-95th
  percentile range crosses zero — a hundred trades cannot distinguish
  this from luck.

  Standing caveats still apply and all point the same way: survivorship
  bias flatters these numbers, and the daily-bar cap meant condition 5
  was unresolved before ~2021, so most of both windows tested an
  eight-condition checklist rather than the current nine.
- **Partial profit-taking, settled properly this time — it's a wash, so
  the book's rule stays.** The earlier reading rested on ten trades that
  reached the target; this one has 83, and compares them pairwise rather
  than comparing arm averages, since 151 of the 254 trades never reach
  the target and are byte-identical across arms. Among the trades where
  the policy actually applies: selling everything at the target returns
  +19.83% a trade, selling half +19.18%, selling nothing +18.53%.

  Selling everything wins on 66% of individual trades, which reads like
  a result until the spread is accounted for — the mean gap over selling
  half is 0.4 standard errors from zero, i.e. indistinguishable from
  noise. The mechanism is visible in the medians (+17.92% against
  +15.49%): selling everything wins more often, selling half wins bigger
  when it wins, because the remaining half occasionally runs a long way.
  That is exactly the trade partial profit-taking is meant to make, and
  the two effects cancel.

  So the default is unchanged, but for a better reason than before. It
  was kept on the grounds that ten observations shouldn't overrule the
  source method; it's now kept because eight times that sample can't
  find a difference either.
- **Segmented the backtest by liquidity, which closes a question open
  since the floor was lowered — thin names are much worse, and stop
  distance is why.** Five bands, 45 tickers each. The $1-5M band lost
  15.14% a trade with 12 of 15 trades negative, and trimming both its
  best and worst trade makes it worse rather than better, so it isn't
  one disaster. Losses past −30% were 4 of 15 there against 0 of 55 in
  the $200M+ band.

  Every deep loser exited at or inside its planned risk, so the stop
  isn't failing — the planned risk is simply enormous. The stop sits at
  the consolidation low, and thin names consolidate raggedly, so the
  median stop runs 37-41% below entry under $50M a week against 16.5%
  above $200M. One stop-out therefore costs roughly 40% of the position
  on a thin name, exactly as designed. The 15% stop ceiling doesn't stop
  this, since failing condition 9 still leaves 7 of 8 others to qualify
  on.

  Also worth recording: no band showed a reliable edge. The $200M+ band
  returns +4.20% a trade, but a single +242% winner is the whole of it —
  trimmed, it's +0.18%, with 31 of 55 trades losing. Across all 167
  trades the stratified sample returns −1.42%, against roughly +2.85%
  for the liquid 198-ticker samples I'd been measuring on. The method's
  positive results have been coming from liquid names.
- **Swept the book trailing stop's confirmation threshold, and my value
  was badly wrong — though the conclusion it supported still holds.**
  `CORRECTION_RECOVERY_PCT` decides how near its old high a stock must
  climb before the correction-based stop may move up. At my 3.0 the
  method returns −2.06% a trade; loosening it to 20 gives +1.26%. The
  reason is visible in how trades ended: at a 1% threshold 44.6% of
  positions never resolve at all, falling to 7.5% at 20%, because a stop
  that may not move is a stop that never closes anything. That is
  exactly the symptom I'd recorded without being able to explain.

  It doesn't rescue the method. The 30-week average returns +2.85% a
  trade over the same 198 tickers, so it stays the default and the
  earlier finding is unchanged — only its explanation is better.

  Left at 3.0 rather than retuned. Performance rises monotonically right
  up to a threshold so permissive the rule barely does anything, and a
  gate that works better the less it gates is an argument against the
  gate, not for a particular number. Picking the sweep's favourite would
  be fitting to one window. Recorded in known-gaps as a decision owed.
- **The book's trailing rule performs worse than following the average.**
  Across 200 tickers and roughly 220 resolved trades an arm: the 30-week
  average returns +2.86% a trade at a 2.24 payoff, swing lows −0.58%,
  and the book's rule −2.99%. Its stop moves so rarely that positions
  don't resolve at all. Default stays on the average. The likely fault
  is my confirmation threshold rather than the method — noted in
  known-gaps with the sweep that would settle it.
- **The 20-ticker samples I'd been deciding on were misleading.** The
  same window gave a 51.7% win rate and 1.61 payoff on 20 tickers
  against 39.5% and 2.24 on 200 — flattering the hit rate while hiding a
  better payoff profile.

### Fixed
- Re-running a backtest parameter set appended a second copy of every
  trade instead of replacing it. The report aggregates whatever rows
  exist, so the sample silently doubled — and these are the numbers I
  use to decide whether a parameter is worth keeping.
- The partial-exit fraction was bound as a default argument, so patching
  it to compare exit policies did nothing and both arms of an A/B ran
  identically. That reads as "this change makes no difference" rather
  than as a broken experiment, and I only caught it because two arms
  came back digit-for-digit identical.

### Changed
- Reaching the swing-rule target now sells half the position and leaves
  the rest to the trailing stop, which is what the book prescribes.
  Exiting fully at the target had been truncating every winner at its
  own measured objective.
- Liquidity floor lowered from an invented $5M to $1M, set where the
  data actually degrades. The old figure was excluding 2,286 names, 163
  of which would have reached the prefilter, without buying any signal
  quality.

### Investigated, no change made
- **Partial profit-taking doesn't improve results here.** Measured over
  the same window, taking the whole position off at the target beat
  taking half (+3.11% against +2.58% per trade), which beat letting it
  all run (+2.06%). I kept the book's half anyway: only ten of
  twenty-nine trades reached the target at all, so the comparison rests
  on ten observations in a bull market, which isn't enough to overrule
  the source method. The pattern suggests the lagging trailing stop is
  the real constraint, not the exit policy.
- **Pivot length 10 against 20**, the question left open since the
  parameter was first questioned. 20 came out ahead (+2.58% against
  +2.04% per trade), but 25 of 29 trades are common to both arms, so the
  difference rests on a handful of trades. Left at 20.

## 2026-07-26

### Added
- `--universe` mode: screens every tradable US listing rather than a list
  I wrote myself, which is the only way the tool can surface something I
  didn't already know to look at. Shaped as a funnel — metadata filter,
  then weekly bars in batches, then liquidity, then a bars-only scoring
  pass, and only then the per-ticker sector lookup — so the one expensive
  call is spent on the few hundred names that could still qualify. About
  a minute and a half for the whole market.
- Ranking on the summary output. 236 names qualifying is a list nobody
  works through, so results sort by whether they're still entryable
  rather than already extended, then sector strength, then how much of
  the checklist resolved, then breakout freshness.
- A fund/stock discriminator, so ETFs no longer crowd out individual
  stocks. They carry no sector classification, and several are slices of
  the same sector firing as if they were independent signals.

### Fixed
- Instrument pagination silently truncated at 40,000. The real universe
  is 64,358, so every earlier candidate count was measured on a fraction
  of the market.
- Relative strength paired a stock against the index by position, which
  raised outright whenever a stock was younger than the index — 463
  recently listed names discarded behind an error that named the symptom
  and not the cause. Pairing is by date now, which is also simply
  correct: position-wise comparison misaligns the two series wherever
  there's a gap.
- Re-running a scan on the same day appended rather than replaced,
  leaving two rows per ticker for anything reading the history back.

## 2026-07-25

### Added
- A regression suite covering the checks I'd been running by hand, plus
  mutation testing to confirm the tests actually fail when the behaviour
  they cover is broken — which immediately caught a bug in one of my own
  tests.
- The wide-scan data layer: batched bar fetching at the server's
  twenty-symbol limit, universe discovery and caching, a client-side rate
  limiter, and caches for the sector lookups that were being repeated per
  ticker.
- `docs/parameter-calibration.md`, recording which thresholds rest on
  evidence and which are mine, and why the stop ceiling stays in the
  screener rather than moving to position sizing.

### Fixed
- Base and breakout detection was assumed rather than detected — the base
  was a hardcoded slice and breakouts were only looked for in the last
  eight weeks. Seven of fifteen tickers had no detectable breakout at
  all, which starved three conditions at once.
- Condition 9 was wrong three ways against the book's own worked example:
  the swing rule was anchored at the entry price rather than the prior
  peak, applied where its geometry doesn't hold, and paired with a stop
  that risked a third of the position.
- Evaluations could see different amounts of history depending on which
  caller asked, so the same stock on the same date scored differently
  through the live screener than through the backtest.

## 2026-07-24

### Added
- The backtesting engine, so parameter choices can be tested against
  outcomes instead of against tickers I already had opinions about.
  Point-in-time evaluation is verified by construction: adding future
  bars to the input never changes a historical result.
- Trailing stop-loss and entry-plan sizing for names that already
  qualify, with the short side present as stop-order logic only.
- A project permission allowlist for routine work, keeping an explicit
  gate on force-pushes, history rewrites, deletions and dependency
  installs.

### Fixed
- The in-progress weekly bar was contaminating every calculation. Volume
  was measured against a four-week average of complete weeks, so a
  partial week read as contraction — which is what produced the only
  "actionable" signal the tool had found to that point.
- Scoring treated "unknown" identically to "failed", so several tickers
  could never qualify regardless of setup quality.
- Sector strength compared every stock against itself because the sector
  map was keyed on a different taxonomy than the API returns.

## 2026-07-23

### Added
- The core screener: SQLite storage, Mansfield RS, Webull data fetching,
  the nine-condition checklist and the entry point that runs it.
- The indicators I use on my own charts — moving averages, rolling
  highs and lows, sector strength, and a pivot-based support and
  resistance read.
- `sector_scan.py`, for building a candidate list from the strongest
  sectors rather than a fixed personal watchlist.
- `docs/db-decision.md`, on why this uses SQLite rather than a hosted
  database.

### Changed
- Corrected the indicator approximations against the real chart sources
  once I had them, rather than leaving them as guesses.
- Stopped tracking my local project-instructions file and rewrote history
  to remove it entirely, rather than only ignoring it going forward.

## 2026-07-22

### Added
- Mansfield RS as a chart script, and confirmation that Webull's own
  scripting environment can't fetch a second symbol — which closes off
  building any relative-strength indicator natively there.

## 2026-07-20

### Added
- Initial scaffold: project structure, reference documentation, and the
  gitignore rules that keep credentials, real watchlists and local
  reference material out of a public repository.
