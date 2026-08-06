# Queue

Ordered by what would change a decision, not by effort.

## Running now
- **w2_2010_M9** — last of the four corrected-universe arms. The other
  three are in and every one lost its edge over buy-and-hold.
- **t5b_band30** — the band the spread sweep died in, re-run alone.
- **t3** — the daily-bar sweep, 20/50/100/150/200 days.
- **w3** — corrected universe restricted to names liquid enough to
  trade. Decides whether W2's collapse was survivorship or microcaps.
- **t5c** — random-thinning control on universe B, queued behind the
  rest. Decides whether the entry band has a mechanism of its own.

## Next, in order
1. **Re-run T4's policy comparison on corrected arms only.** The
   published table mixes a corrected 2005-2009 with two survivor-biased
   windows. The conclusion held up but the table should not stand.
2. **A cash-rate series instead of a flat 3%.** Short rates ran near 5%
   in 2005-2007 and near 0.2% by 2009; a constant flatters cash early
   and penalises it late. Same anachronism as the commissions, and the
   same fix — do them together.
3. **Era-aware commissions** at roughly $1 a trade rather than $8.
4. **Corwin-Schultz spreads**, so slippage scales with each name's own
   liquidity rather than a flat assumption.
5. **T2 — MA type**, SMA against WMA against EMA. Needs `ema()`.
6. **Tight stop plus rebuy**, three arms.
7. **Forced liquidation on a regime flip.**
8. **Forward paper record.** Still empty. Every figure in this
   repository is a backtest.
9. **Replication and review pass.**

## Deferred with a reason
See docs/known-gaps.md. Two worth repeating here:
- The database sits in a synced folder and does one write transaction
  per trade. `SCREENER_DB` works around it; batching the inserts is the
  actual fix.
- Nothing has been traded. The strongest evidence this project could
  produce is the one kind it has none of.
