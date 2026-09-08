# Queue

Ordered by what would change a decision, not by effort.

## Finished, recorded
- **W2** — corrected point-in-time universes for all three windows. Every
  edge over buy-and-hold disappeared; the untuned rule loses all three.
- **W2b** — significance on active return. Nothing ever cleared t = 2,
  before or after correction.
- **W3** — liquidity floor. Helps one window, hurts the other. Not a fix.
  Re-examined 2026-08-19 as D4 against a volume-quantisation defect and
  **unchanged** — the floor dropped the affected names rather than
  admitting them.
- **T3** — daily bars. Every arm worse than its weekly equivalent.
- **T5b** — the entry band on universe B. A plateau at 20-30%.
- **T5c** — random thinning. The band has a mechanism of its own.
- **T4** — idle capital. The policy is worth more than the strategy.

## Finished, not yet read
- **Bands 17 and 18** ran (8,407 and 7,836 trades) and were never
  analysed. They exist to settle whether the jump between 15% and 20% is
  a real threshold or an artifact of where the grid happened to land.
  Needs the weekly cache rebuilt first — a minute of work.

## From the Chan text, queued
Read in full 2026-08-14. Methodology is project-agnostic and belongs in
market_core; only chapter 7's strategy content would be a new project.

1. **Fix the benchmark.** Measured 2026-08-19 as B1: the size spread is
   +0.32, −1.40 and **−6.85** points by window, so the 2021 conclusions
   move materially. IWM rather than VTWO — VTWO starts 2010-09 and
   cannot reach the 2005 window. Restating the edge column is blocked
   on the re-run below.
2. **Demote CAGR; report Sharpe, maximum absolute drawdown and MAR.**
   `market_core.performance` now provides all three; what remains is
   changing the report templates to lead with them.
   His objection is the one that produced two figures here rather than
   one: the CAGR denominator is ambiguous, which is why peak capital and
   average capital both had to be reported. MAR is CAGR over maximum
   absolute drawdown and largely survives leverage.
3. ~~**Minimum backtest length, from Bailey.**~~ Done 2026-08-20 with C4.
   `minimum_track_record_length` returns **226 weeks (4.3 years)** for
   the best arm — the defined wait the forward log needed.
4. ~~**Deflated Sharpe Ratio (Bailey 2014).**~~ Done 2026-08-20 as C4.
   The best arm's probabilistic Sharpe of 0.998 falls to **0.535** once
   deflated over 237 trials. Implemented in `market_core.performance`
   alongside minimum track record length, which answers item 3.
5. ~~**Return-window alignment check.**~~ Done 2026-08-19 as D5.
   `market_core.alignment` asserts it; every published arm is clean at
   0 violations, against 0.030% across the modern arms overall.
6. **Five-parameter ceiling.** His rule of thumb counts entry and exit
   thresholds, holding period and lookbacks. We exceed it before
   accounting for the arms R20 was mined from.
7. **Ten-year data window.** He argues older data is unfittable through
   regime shifts, and that more data helps only for a stationary
   process. Directly at odds with how much weight 2005-2009 carries here.
8. **Quantpedia** (quantpedia.com) as a structured source of candidate
   strategies, in place of the ad-hoc route taken so far.
9. **Chapter 7 as a possible third project** — mean reversion,
   cointegration and pairs, on the same engine. Genuinely different
   content rather than another momentum variant.

## Event contracts — queued 2026-09-01

W1. **Kalshi's own API for historical event data.** Webull's API exposes
   settled *events* but purges the *instruments*: 112 of 113 settled
   KXHIGHNY events return zero strikes, direct symbol lookup returns
   empty, and bars on a constructed past symbol give UNSUPPORTED_SYMBOL.
   Only three dates exist at any time. Kalshi is the venue of record —
   these are KX-prefixed Kalshi contracts that Webull routes — and its
   public API documents settled-market history and candlesticks.
   **Build the archive to the same standard as sharadar.db**: append-only,
   frozen watermarks via `market_core.sharadar.assert_writable`, read-only
   opens everywhere but the refresh, one writer. Event contract history is
   *more* perishable than equity history — Webull already proves it gets
   deleted — so capture is urgent in a way the equity archive never was.

W2. **Record forward, starting now.** Daily snapshot of every weather
   series' strikes and quotes at 15:00-18:00 local. A month of clean
   self-captured data in a month, with no vendor gap and no purge risk.
   Cheap enough to run regardless of whether W1 succeeds, and it is the
   only source that cannot be taken away.

W3. **One manual observation tonight.** At 17:00 ET, once NYC has rolled
   over 2F off the day's max, read what the above-max buckets are asking.
   Base rate is 0.56% for NYC, 0.22% pooled across 20 cities. If they
   quote 1c the idea dies on fees and the answer cost five minutes.

W4. **Kalshi perpetual futures.** Whether Kalshi lists perps at all, and
   if so their funding mechanism and settlement. Unverified — do not
   assume the Alpha Stack's crypto-perp framing transfers.

## Crowding — queued behind the insider and Kalshi work

X1. **Does institutional crowding explain momentum's failure here?**
   Raised by the Alpha Stack response: raw momentum is not the strategy,
   crowding-adjusted momentum is, and MSCI found that filtering the most
   over-owned names restored the risk/return profile through 2024.
   Testable from data already held — SF3 is entitled and `holdings`
   carries 79,638,808 rows.

   Runs **after** I1 (insiders) and after the Kalshi archive, because
   those two are orthogonal signals with mechanisms and this one is a
   refinement to a leg that has already failed.

   **Prediction, recorded now:** it fails. Roughly 10-15% that
   crowding-adjusted momentum beats raw momentum at |t| >= 2, under 5%
   that the combination beats buy-and-hold. Three reasons: momentum has
   no surviving edge in the corrected universe, so a better sort of
   nothing is still nothing; the crowding story is a mega-cap story and
   this universe is mostly small; and 13F data is quarterly with a
   45-day filing lag, so the positioning signal is up to 4.5 months
   stale at the moment it would be traded.

   **The one result that would change my mind**, written down so it
   cannot be claimed afterwards: an effect concentrated in the *loser
   tail* rather than the mean — most-crowded quintile underperforming
   badly while the rest is flat. That is what a forced-unwind mechanism
   should look like, and a mean-based test would miss it. Report the
   quintile spread, not just the average.

## Data we do not have, checked 2026-09-01

- **Sharadar options and futures: not entitled.** SEP, SFP and SF3 return
  data; OPT, SFO and FUT all return HTTP 403. Anything from Alpha Stack
  episode 3 that needs options or futures history is blocked on buying a
  dataset, not on writing code. SF3 being entitled matters separately —
  it is institutional holdings, the "I" in CAN SLIM, and F1 needs it.

## Next, in order
0a. ~~**Run I1 — the insider study, then retest it out of sample.**~~
   Pooled 2008-2026 run 2026-09-07: **partial**, code P beats all three
   controls at 5 and 21 trading days at |t| >= 3.0; at 63 days the
   shuffled-date control catches up completely, meaning the 63-day
   return is a company trait rather than filing-timing information.
   Retested 2023-2025 only (a single recent regime, chosen before
   running to avoid pooling across a financial crisis, a zero-rate
   decade and a pandemic crash and calling the average "the effect"):
   **still partial**, but for a different reason — 5 days replicates
   cleanly (|t| > 10 in both windows), 21 and 63 days are real by some
   comparisons in both windows but never clear all three controls
   together, and fail against a different control in each window. Full
   breakdown in docs/preregistered-tests.md. Not acted on. **Still
   outstanding before this moves past partial**: the Stata cross-check
   (free through CSUSM), the C4 deflation adjustment, and only then the
   two pre-registered follow-up splits (dollar size, insider role). F1 is
   also registered and unrun — it is in preregistered-tests.md but was
   never listed here, which is how a registered test gets forgotten.

0. ~~**Re-run every published arm under a pinned configuration.**~~ Done
   2026-08-20 as B2. Ten arms re-run on a rebuilt 10,227-ticker cache,
   reconstructed universes and one recorded configuration. W2 arms
   reproduce within 0.4%, W3 within 6.1%. No arm reaches |t| = 2 against
   SPY or IWM. The eleven T5b/T5c arms are closed by loss — the entry
   band they swept was never committed to tracked code.

0b. **Rebuild the daily cache and re-run T3.** The daily cache is a
   different vintage too (26-27% of T3 trades disagree with it). About
   15 minutes to rebuild windowed to 2004-2011, then 67 minutes of arms.
   The T3 conclusion survived recomputation on every arm checked, so
   this is confirmation rather than discovery.
1. **Re-run T4's policy table on corrected arms only.** The published
   version mixes one corrected window with two survivor-biased ones. All
   six w2 arms now exist, so this is arithmetic rather than compute.
2. **A cash-rate series instead of a flat 3%**, alongside **era-aware
   commissions** at roughly $1 a trade. Same anachronism, same fix.
3. **Corwin-Schultz spreads**, so slippage scales with each name's own
   liquidity rather than a flat assumption.
4. **T2 — MA type**, SMA against WMA against EMA. `ema()` is written and
   tested, so this is ready to run.
5. **Move the fund-price drift gate into the screener.** It exists only
   in scratch scripts. Any code touching fundprices without it will rank
   corrupt series at the top, which is how a 7,946,566% return reached a
   live screen.
6. **Tight stop plus rebuy**, three arms.
7. **Forced liquidation on a regime flip.**
8. **Score the forward log.** 25 rows written 2026-08-06: 15 buys, 7
   holds, 2 exits, 1 no-signal. Nothing to read until months have passed,
   which is the point of it.
9. **Replication and review pass.**

## Waiting on something outside this repo
- **SATA.** `indicator_readings` is built and empty. Needs scores read
  off charts for a spread of names — including low scorers and names I
  have no interest in owning, or the sample measures my judgement rather
  than the indicator.

## Housekeeping
- `data/` holds 8GB of leftovers inside the synced folder:
  `sharadar.db.driveback` at 6.3GB, `daily_bars.pkl` at 1.6GB,
  `weekly_bars.pkl` at 334MB, and `screener.db.moved-20260806`. The live
  database is in application support and the live market data is in
  ~/market-data, so these are all stale copies being uploaded for
  nothing.
