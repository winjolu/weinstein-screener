# References

The academic basis for the parts of this project that have one.

Worth being explicit about which parts those are. Stage analysis itself
comes from a trade book, not a literature — but several things measured
here turn out to be documented effects with names, and a few of this
project's mistakes are documented failure modes with names too. Both are
listed.

**The papers themselves are not in this repository.** They are
copyrighted by their publishers, and a university subscription licenses
reading them rather than redistributing them. Local copies live in
`reference/papers/`, which is gitignored, exactly as the Weinstein text
does. Citing work is the appropriate way to credit it; hosting it is
not, and would also breach the library terms that provided access.

Where a freely available version exists — a working paper, a preprint,
or an open-access journal — it is linked.

> Citations below were written from memory and the DOIs should be
> verified before this file is relied on for anything formal.

---

## On whether results like ours survive being looked for

These two are the most relevant papers in this list, and the least
comfortable. This project has now run more than twenty-five arms against
the same three windows.

**Harvey, C. R., Liu, Y., & Zhu, H. (2016). "…and the Cross-Section of
Expected Returns." *Review of Financial Studies*, 29(1), 5–68.**
doi:10.1093/rfs/hhv059 · free preprint on SSRN (2249314)

Because hundreds of factors have been tested against the same data, the
conventional significance bar is far too low; they argue for a t-statistic
above roughly 3.0 rather than 2.0. **Our pre-registered criteria were
never adjusted for the number of looks**, and should be re-derived
against this.

**Bailey, D. H., Borwein, J., López de Prado, M., & Zhu, Q. J. (2014).
"Pseudo-Mathematics and Financial Charlatanism: The Effects of Backtest
Overfitting on Out-of-Sample Performance." *Notices of the AMS*, 61(5),
458–471.** — open access, no subscription needed

Gives an expected amount of overfitting as a function of the number of
trials run. That number is computable for this project and has not been
computed.

## On survivorship, which D3 showed can invert our conclusions

**Brown, S. J., Goetzmann, W., Ibbotson, R. G., & Ross, S. A. (1992).
"Survivorship Bias in Performance Studies." *Review of Financial
Studies*, 5(4), 553–580.** doi:10.1093/rfs/5.4.553

The foundational treatment. Relevant because our own bound — 2% of
trades going to zero erases the edge in two windows of three — needs
comparing against published magnitudes.

## On momentum, which is what this system appears to be measuring

**Jegadeesh, N., & Titman, S. (1993). "Returns to Buying Winners and
Selling Losers: Implications for Stock Market Efficiency." *Journal of
Finance*, 48(1), 65–91.** doi:10.1111/j.1540-6261.1993.tb04702.x

Cross-sectional momentum. Mansfield relative strength is a momentum
measure, and batch 8 found it monotone on both win rate and mean in all
three windows — the strongest single result here.

**Moskowitz, T. J., Ooi, Y. H., & Pedersen, L. H. (2012). "Time Series
Momentum." *Journal of Financial Economics*, 104(2), 228–250.**
doi:10.1016/j.jfineco.2011.11.003

Hold an asset while its own trend is up. M7 is this rule in two lines,
and it beat the nine-condition checklist in both bull windows while
being destroyed by the crash — which is the documented profile.

**George, T. J., & Hwang, C.-Y. (2004). "The 52-Week High and Momentum
Investing." *Journal of Finance*, 59(5), 2145–2176.**
doi:10.1111/j.1540-6261.2004.00695.x

Proximity to the 52-week high predicts outperformance. R24 tested
whether our mined threshold had the wrong sign against this; it did not,
because the threshold trades hit rate for magnitude deliberately.

**Asness, C. S., Moskowitz, T. J., & Pedersen, L. H. (2013). "Value and
Momentum Everywhere." *Journal of Finance*, 68(3), 929–985.**
doi:10.1111/jofi.12021

## On machine learning, if that direction is ever taken

**Gu, S., Kelly, B., & Xiu, D. (2020). "Empirical Asset Pricing via
Machine Learning." *Review of Financial Studies*, 33(5), 2223–2273.**
doi:10.1093/rfs/hhaa009 · free as NBER Working Paper 25398

Wanted specifically for how they handled delisting returns and enforced
point-in-time on Compustat — the two problems blocking us.

**Green, J., Hand, J. R. M., & Zhang, X. F. (2017). "The Characteristics
that Provide Independent Information about Average U.S. Monthly Stock
Returns." *Review of Financial Studies*, 30(12), 4389–4436.**
doi:10.1093/rfs/hhx019

The 94 firm characteristics, with construction definitions.

**Welch, I., & Goyal, A. (2008). "A Comprehensive Look at the Empirical
Performance of Equity Premium Prediction." *Review of Financial
Studies*, 21(4), 1455–1508.** doi:10.1093/rfs/hhm014 — the macro
predictor data is maintained free on Goyal's own site.

## On the risk measures added 2026-08-03

**Martin, P. G., & McCann, B. B. (1989). *The Investor's Guide to
Fidelity Funds.* Wiley.** — where the Ulcer Index was introduced. Depth
and duration of drawdown in one number, and the measure that revealed
this strategy spends 156–182 weeks below a prior peak.

## Primary source for the method itself

**Weinstein, S. (1988). *Secrets for Profiting in Bull and Bear
Markets.* McGraw-Hill.** — not in this repository, and summarised in
`docs/methodology.md` in my own words rather than quoted.
