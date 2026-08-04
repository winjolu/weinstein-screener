# Briefing for a second-pass review

This project has been reviewed once already, in the sense that it was
forked from a less capable model and the fork immediately found material
defects: that the "8 of 9 conditions" rule was not in the source text at
all, that entry fills were being booked retroactively at a price worth
+1.11 points per trade — the entire measured edge — and that a
documented 1,200-bar API cap was never enforced, leaving one of the nine
conditions dead in every backtest reaching past 3.3 years.

Those were not stylistic disagreements. They were load-bearing errors
sitting in plain sight. The base rate says a fresh reviewer finds more.

## What would be most useful

**Two passes, with deliberately different inputs.**

### Pass 1 — replication. Do not read the code or these docs.

Take `data/sharadar.db` (SQLite, 46.3M daily bars, 1998-2026,
survivorship-free, 78,904 tickers with `permaticker` and `isdelisted`)
and compute this independently:

> Annualised return, 2005-2009, of buying US domestic common stocks
> priced above their 30-week moving average with a positive 12-month
> return, while SPY is also above its own 30-week average. $1,000
> positions, $100,000 capital, exit when either condition breaks.
> Universe: domestic common stocks with at least $1M average weekly
> dollar volume in Q4 2004.

We claim **+4.17%/yr**, against buy-and-hold SPY at +0.80%.

A number near ours is corroboration. A number far from ours means one of
us has a bug, and finding which is worth more than any amount of
commentary. Numbers disagree in ways prose cannot.

### Pass 2 — review. Read everything.

Here the documents are the point rather than a contaminant, because the
reasoning is what needs auditing. Specific questions, in order of value:

1. **What premise does this project accept without testing?** Seven
   load-bearing assumptions were found false in a single day — that
   stops fill at the stop price, that a price series ending means the
   position is still open, that a new SEC CIK means a new company, that
   slippage is flat across liquidity, that our universe represented the
   market, that bars were split-adjusted, that commissions were zero in
   2005. All had existed silently for weeks. The question is what is
   still on that list.

2. **Which conclusions flip if one assumption is wrong, and which
   assumption?**

3. **S1 shows R20 losing 47% of its return under survivorship correction
   while M9 gains.** The stated explanation is that R20's mined filter
   encoded survivor characteristics. Is that the best explanation, or is
   something else producing it?

4. **What would you check first if you suspected the headline result was
   wrong?**

## The claims worth checking

Everything else rests on these.

1. M9 (price above 30-week MA + positive 12-month return + same test on
   the index) beats the nine-condition checklist on Martin ratio in all
   three windows.
2. The strategy's edge is bear-market avoidance, and it is present in the
   *untuned* baseline, so it does not depend on any fitting.
3. Time under water is 132-182 weeks in every window — the largest
   practical obstacle, and larger than the index's.
4. Nothing clears t = 3.0 except M7 on the derivation window. Bonferroni
   for our 25 arms independently gives 2.88.
5. Survivorship costs the mined rules ~47% and the simple rule nothing.

## Known-weak areas, so time is not spent rediscovering them

- **Slippage is modelled as a flat percentage** across all names.
  Novy-Marx & Velikov's Appendix A warns specifically against
  extrapolating large-cap costs to small stocks linearly. Our edge
  concentrates in the thinnest quartile, so this understates cost
  exactly where the finding lives.
- **Commissions are modelled at zero** for every era, including 2005.
- **Stop exits fill at the stop price** even when the bar gapped through
  it. Costs 0.16-0.28 points per trade. Fix identified, not yet applied.
- **`funds` table is downloaded but not loaded**, so SPY benchmarks come
  from Webull while equities come from Sharadar.
- **The forward record is empty.** Every figure is a backtest.

## How to handle disagreement

Bring it back rather than adopting it. A dozen disputes in this project
have been settled by computing something, and that has been reliable
where argument has not. A reviewer's confident claim is a hypothesis,
not a verdict — which is exactly the standard this project applies to
its own output.
