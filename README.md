# weinstein-screener

A backtesting and evaluation engine built to answer one question honestly:
**does this trading strategy actually work?**

It implements Stan Weinstein's stage-analysis method — a four-stage
classification of price action with a nine-condition entry checklist — and
then spends most of its effort trying to prove that implementation wrong.

## The headline result

**No.** Across 237 registered experiments and four independent lines of
attack, no configuration of this strategy has produced an edge over
buy-and-hold that is distinguishable from noise.

That is the finding. The engine exists to make it trustworthy.

| test | result |
|---|---|
| Correct for survivorship bias | one arm went from **+11.55%** over buy-and-hold to **−7.80%** |
| Significance on active return | **nothing** has ever reached \|t\| = 2 |
| Size-matched benchmark (Russell 2000 rather than S&P 500) | edges move by up to 6.85 points; **no arm reaches \|t\| = 2** |
| Deflated Sharpe over 237 trials (Bailey & López de Prado) | best arm falls from **0.998** to **0.535** — a coin flip |

The last row is the clearest statement of the whole project. The best arm's
Sharpe looks convincing in isolation. Priced for the fact that 237 variants
were tried to find it, it is indistinguishable from the best of 237 coin
flips.

## Why a negative result took this much machinery

Nearly every apparent edge this project found turned out to be a defect in
measurement. Each one is documented with the incident that produced it:

- **Survivorship bias.** 69% of companies trading in 2005 have since
  delisted. Correcting the universe erased every edge.
- **A look-ahead leak.** A 200-day timing rule returned +19.48%/yr, survived
  every robustness check, and was reading tomorrow's data. Only the number
  being too good gave it away.
- **Split-adjusted volume quantisation.** 6.03% of price bars in the vendor
  archive sit on a storage floor of one share, because reverse-split
  adjustment drove volume below 1 and it rounded up. One name reports
  $84 billion of turnover on a day it traded about $100,000.
- **Two data vintages.** Stored trade prices and a rebuilt bar cache
  disagreed by factors up to 50,000, because every corporate action rewrites
  the history behind it. The simulation that mixed them reported +5.03% a
  year beside a −98.3% drawdown — two numbers that cannot describe one
  account.

The engine now refuses each of these rather than reporting a plausible
number.

## Method

**Pre-registration.** Every experiment records its hypothesis, its success
criteria, and what would count as refutation, *before* it runs.
`docs/preregistered-tests.md` is append-only and includes the predictions
that turned out wrong.

**Controls.** Every filter is measured against random thinning to the same
sample size. Removing 30% of names at random cost 1.5 points a year;
removing the same share through the tested rule gained 2.7. Without the
control the two are indistinguishable.

**Provenance.** Each result records the data it consumed — cache path,
fingerprint, universe size, rule, and full account configuration. This was
added after the published figures became unreproducible when a bar cache
was deleted, and the numbers stayed quotable while quietly ceasing to be
checkable.

**Mutation testing.** Every guard is deliberately broken to confirm its
tests fail. A test that passes against broken code is worse than no test,
because it reads as protection.

## Architecture

```
screener/          strategy logic, backtest engine, portfolio simulation
market_core/       shared data layer, used by this and a sibling project
  ├ sharadar.py    vendor client with archival write guards
  ├ lookahead.py   truncation test for future-data leaks
  ├ vintage.py     refuses to mix data from two adjustment vintages
  ├ liquidity.py   dollar volume that returns None when unmeasurable
  ├ alignment.py   asserts returns begin after the decision that bought them
  ├ timeseries.py  stationarity, cointegration, half-life, HAC regression
  └ performance.py Sharpe, Deflated Sharpe, minimum track record, MAR
docs/              the full audit trail — see where-this-stands.md first
tests/             773 tests
```

The shared package exists because the same helper was written twice in two
projects and drifted. Two versions of a guard is worse than one.

## Stack

Python 3.13 · NumPy · pandas · SciPy · statsmodels · scikit-learn ·
Matplotlib · seaborn · SQLite

The strategy engine itself is deliberately dependency-light and readable
line by line, which is how most of the defects above were found. The
scientific stack carries the statistical work: Newey-West standard errors
for overlapping return windows, Augmented Dickey-Fuller and Engle-Granger
tests for the mean-reversion research, and the Bailey & López de Prado
results for discounting a Sharpe by the size of the search that found it.

## Running it

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e "$HOME/market-data/market-core"   # shared data layer

.venv/bin/python3 -m unittest discover -s tests -t .       # 773 tests
.venv/bin/python3 -m screener.run_screener --broad         # needs credentials
```

The shared package installs as a second step because pip does not expand
`~` in a requirements file and the checkout deliberately lives outside this
repository — two projects share it, so it belongs to neither.

Market data comes from Sharadar via a local archive and from Webull's
official OpenAPI. Credentials live in `.env`; see `.env.example`. Holdings
and watchlists are gitignored — only the example files are committed.

## Where to start reading

- `docs/where-this-stands.md` — the current state of belief in one page,
  including the claims that were withdrawn
- `docs/test-register.md` — every experiment, what it asked, how it resolved
- `docs/known-gaps.md` — what is untested, unbuilt, or deliberately deferred
- `docs/methodology.md` — the four stages and the nine-condition checklist

## Scope

This is a personal research project. It is not investment advice, it makes
no claim to profitability, and its central finding is that the strategy it
implements does not beat holding an index fund.
