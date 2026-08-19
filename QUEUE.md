# Queue

Ordered by what would change a decision, not by effort.

## Finished, recorded
- **W2** — corrected point-in-time universes for all three windows. Every
  edge over buy-and-hold disappeared; the untuned rule loses all three.
- **W2b** — significance on active return. Nothing ever cleared t = 2,
  before or after correction.
- **W3** — liquidity floor. Helps one window, hurts the other. Not a fix.
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

1. **Fix the benchmark.** He is explicit that it must match the
   securities traded — a small-cap strategy against the Russell 2000,
   not the S&P 500. Our screen surfaces mid- and small-cap healthcare
   and every figure is measured against SPY, so part of what has been
   called an edge or a shortfall is just the size spread. VTWO is
   already held and is the right comparison.
2. **Demote CAGR; report Sharpe, maximum absolute drawdown and MAR.**
   His objection is the one that produced two figures here rather than
   one: the CAGR denominator is ambiguous, which is why peak capital and
   average capital both had to be reported. MAR is CAGR over maximum
   absolute drawdown and largely survives leverage.
3. **Minimum backtest length, from Bailey.** To be 95% confident a true
   Sharpe exceeds zero needs a backtest Sharpe of 1 over 681 points
   (~2.7 years daily); a backtest Sharpe of 2 needs only 174. It applies
   to paper trading too, which turns the forward log from an open-ended
   wait into a defined one.
4. **Deflated Sharpe Ratio (Bailey 2014).** Discounts a Sharpe by how
   many variants were tried to obtain it. This project has run 200+
   arms. The paper is already in reference/papers/.
5. **Return-window alignment check.** The gap the truncation test cannot
   close: verify that the return credited to a position begins at or
   after the moment the position was decided. That invariant is what the
   200-day rule violated, and neither existing check asserts it.
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

## Next, in order
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
