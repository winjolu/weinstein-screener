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

- Tests for the universe prefilter and the fund/stock discriminator. Both
  currently fail by silently excluding things, which is the failure mode
  least likely to announce itself.
- A liquidity floor set from the measured distribution rather than the
  invented $5M placeholder.

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
