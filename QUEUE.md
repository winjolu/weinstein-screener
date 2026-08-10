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
