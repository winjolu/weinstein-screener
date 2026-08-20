# Test register

Every registered test, what it asked, and how it came out. The detail
and the pre-registered expectations live in `preregistered-tests.md`,
which is ordered by when things ran; this is ordered to make things findable.

**Update this file whenever a test is registered or resolves.**

## What the letters mean

The prefixes accumulated rather than being designed, so this is the
convention as it actually emerged.

| prefix | meaning |
|---|---|
| **R** | **Rule** — a change to the trading rule itself: entry, exit, stops, holding period, ranking. |
| **V** | **Volume** — a sub-family of R sweeping the volume-confirmation threshold. |
| **G** | **Gate** — the three "non-negotiable" veto conditions, asking whether each earns its veto. |
| **M** | **Mechanism** — infrastructure and modelling corrections rather than rule changes: sizing, costs, drawdown measurement. M7-M9 break the pattern by being rule tests, which is a naming mistake I did not fix in time. |
| **S** | **Overloaded, and a known defect.** S1-S2 are *data source* tests. S7 is the *short* side. Rename S7 to SH1 when next touched. |
| **D** | **Data integrity** — ticker identity, delisting census, survivorship bounding. |
| **B** | **Benchmark** — what the strategy is measured against. |
| **K** | **K-nearest neighbour** — the single machine-learning test. |

## Status legend

**adopted** in the current best rule · **rejected** measured and not
worth it · **closed** answered, no further work · **open** registered,
not yet run · **defect** revealed a bug rather than a result

---

## R — rule changes

| id | question | outcome |
|---|---|---|
| R1 | baseline | reference arm |
| R2 | hard gates instead of scoring ratio | rejected |
| R3 | 15% stop-distance limit as a purchase gate | superseded by R25 |
| R4 | extension gate at entry | **defect** — measured at scan date not fill bar, removed 226 of 273 trades and blocked all re-entry |
| R5 | extension-triggered partial profit-taking | rejected |
| R6 / R6a / R6b | stall exit at 13 and 26 weeks | works as designed, marginal; my stated premise about trapped capital was wrong |
| R7 | moving-average variant | rejected |
| R8 | curvature in stage detection | rejected |
| R9 | loosen the trailing stop | rejected — catastrophic at 15% |
| R10 | weekly rather than monthly checkpoints | **adopted** |
| R11 | continuation entries | rejected |
| R12 | the short side | superseded by S7 |
| R13 | remove the one-year maximum hold | **adopted** — this was the real participation constraint, not stop placement |
| R14 | weekly checkpoints + long max hold | **adopted** as the baseline |
| R15 | the mined entry filter | adopted, later found survivor-fitted by S1 |
| R16 | drop volume confirmation | no harm |
| R17 | drop the risk/reward ceiling | no harm |
| R18 | drop both | **defect** — the evidence floor made qualification arithmetically impossible |
| R19 | mined filter alone | positive on survivors |
| R20 | everything measured positive, combined | the tuned rule; **loses 47% under S1** |
| R21 | mined filter + drop risk/reward | volume confirmation is a participation tax: same quality, 17-20% fewer trades |
| R22 | fund the highest-scoring signals first | rejected — ranked on `conditions_met`, too coarse to carry information |
| R23 | random-thinning control | the mined filter genuinely selects — beats 40 of 40 random draws |
| R24 | drop or invert the 52-week-high requirement | rejected — the sign was right; I had read a win-rate gradient on a system that earns through magnitude |
| R25 | enforce the stop ceiling as a hard gate | **closed** — real risk control, poor trade; loses to random thinning on Martin at every width tested |

## V — volume threshold

| id | question | outcome |
|---|---|---|
| V1 | ratio 1.5x | volume measures nothing |
| V2 | ratio 1.0x | volume measures nothing |
| V3 | no volume requirement | volume measures nothing |
| V4 | the book's build-up pattern | volume measures nothing |

## G — the non-negotiable vetoes

| id | question | outcome |
|---|---|---|
| G1 | price_above_ma not a veto | **zero trades change** |
| G2 | market_stage not a veto | 16 of 10,898 change |
| G3 | stage_setup not a veto | **zero trades change** |
| G4 | none of the three a veto | identical to G2 — only market_stage ever binds |

## M — mechanism and modelling

| id | question | outcome |
|---|---|---|
| M1 | mark-to-market equity | **defect** — drawdowns understated 2-3x; open losers were carried at cost and the percentage divided by starting capital |
| M2 | position sizing by risk not by dollar | built, not yet swept |
| M3 | exposure scaled by volatility and regime | **open** |
| M4 | add to winners | **open** |
| M5 | exit on relative-strength deterioration | **open** |
| M6 | transaction costs and the breakeven sweep | ~2 points of annual return per 1% per-side slippage; no cliff |
| M7 | two-line trend rule vs the nine conditions | beats the checklist in both bull windows, destroyed by the crash |
| M8 | momentum as a ranking rather than a gate | partially answered by K1 |
| M9 | trend rule + market-regime gate | **best rule** — beats the checklist on Martin in all three windows and survives S1 |

## S — data source, and the short side

| id | question | outcome |
|---|---|---|
| S1 | how much has survivorship inflated everything | R20 -47%, M9 +1.55 points. The tuned rule broke; the untuned one held |
| S2 | daily bars past the 1200-bar wall | moot — Webull pages back to 1993 for free once `end_time` is used |
| S7 | short side against a corrected evidence floor | **closed** — loses to cash-plus-recovery by six points a year in the window built to favour it |

## D — data integrity

| id | question | outcome |
|---|---|---|
| D1 | ticker contamination detector | **defect** — first version was 91% false positives; a new CIK is not a new company |
| D2 | delisting census from SEC filings | 36,346 notices, 11,448 companies; **60% were acquired, not failed** |
| D3 | bounding the survivorship damage | 2% of trades going to zero erases the edge in two windows of three |
| D4 | does quantised volume corrupt the dollar-volume liquidity floor | **closed** — defect is real and large (6% of all bars), W3 unaffected. A threshold survives it; a ranking would not |
| D5 | does any arm credit return from before the decision that bought it | **closed** — 0.030% of trades, and **zero** in every published arm. The gap truncation cannot reach |

## B — benchmark

| id | question | outcome |
|---|---|---|
| B1 | is the SPY benchmark the wrong index, and by how much | **partially closed** — size spread measured (IWM−SPY: +0.32, −1.40, **−6.85** points by window). Restatement blocked: the published portfolio figures no longer reproduce |

## K — machine learning

| id | question | outcome |
|---|---|---|
| K1 | does neighbour retrieval beat ranking on relative strength alone | direction real (47 of 60 paired samples), magnitude not (band straddles zero) |

---

## Standing rules these produced

- Verify an arm is complete before reading it. Misread four times.
- Two arms with identical results means a broken experiment, not an
  inert change — until proven otherwise.
- Score the ride, not just the destination: Martin and weeks-under-water
  beside CAGR. Return alone hid that the untuned baseline beats R20.
- Check the worst case after any change to which trades qualify. Three
  stop-placement defects were invisible in the mean.
- Register before running. The whole file is worthless otherwise.
- A level is not a ratio. Returns divide a scale error out; dollar
  volume, market cap and any other product of price and quantity do not.
  Check those separately after any finding about price integrity.
- An arm that cannot be recomputed is a claim, not a result. Record what
  data a run consumed, not just its parameters. A cache vanished and the
  W2/W3 figures became unverifiable without anything failing.
- Write down why a defect did *no* damage. D4's floor survived because
  penny-stock prices inflate into the thousands rather than the
  millions, which is luck rather than design — and unrecorded luck gets
  spent twice.
