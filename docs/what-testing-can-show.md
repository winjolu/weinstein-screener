# What this project's testing can and can't show

Deliberately in plain terms rather than in the vocabulary of the field.
A backtest result is only worth what its weakest assumption is worth, and
those assumptions are easy to lose track of once they're compressed into
jargon. So: for every number this project produces, what would it take
for that number to be lying?

## Yes, it's backtesting — that's the right word

Running a strategy over past data to see what it would have done is
called **backtesting**, and that's exactly what `backtest.py` does. The
name isn't in question. What's worth being careful about is that
"backtest" describes a *method*, not a *standard of evidence*. A
backtest can be done well or badly, and the difference doesn't show up
in the output — a broken one produces confident numbers in the same
format as a sound one. That's already happened here more than once.

Two things I'd assumed were the same are worth separating:

- **Trade statistics** — what the average signal was worth. Win rate,
  average return per trade. This is what `backtest_report` gives.
- **A portfolio simulation** — what an account running the strategy
  would actually have done, in dollars, over a calendar. Needs to know
  how many positions overlap, how much cash sat idle, and how long each
  trade tied money up. This is `portfolio_sim.py`.

The second is the one that decides whether to use real money, and it can
look very different from the first. A strategy can have a perfectly
respectable average trade and still lose to doing nothing, because the
average trade says nothing about how long the money was committed or how
much of it sat unused.

## The four ways a backtest lies

**1. Lookahead bias** — using information that wasn't available yet.
The classic version is evaluating a Monday using Friday's closing price.
This one is *handled*: `backtest.py` verifies by construction that
adding future bars to the input never changes a historical result, and
condition 5 is hard-coded to refuse the live sector snapshot because
that figure has no historical version in the API.

**2. Survivorship bias** — the universe is companies that still exist.
Anything that went bankrupt isn't in the instrument list, so it can never
be picked and can never lose money in a test. **This makes every result
here better than reality**, and worse the further back the window goes.
A test spanning 2008 is testing a version of history where Lehman
Brothers, Bear Stearns and Washington Mutual simply weren't available to
buy. Nothing in this project can fix that; the data source only knows
about current listings. It's a permanent asterisk, not an open task.

**3. Fitting the test to the data** — tuning a parameter until the
backtest looks good, then quoting that backtest as evidence the
parameter is good. That's circular, and it's the trap this project is
most exposed to, because most thresholds were chosen by looking at these
same windows. The defence is to change a parameter only when there's a
reason outside the numbers, which is why several measured "improvements"
here were deliberately not adopted.

**4. Too few trades** — already caught the hard way. A 29-trade sample
gave a 51.7% win rate; the same window at 200 tickers gave 39.5%. Those
aren't refinements of each other, they're different answers, and the
small one was more flattering. Anything resting on fewer than a few
hundred trades is a hint.

## Random sampling versus running the strategy

An obvious-seeming design is "pick random stocks at random dates and see
what happened." It's tempting but weaker than it looks, for a reason
worth writing down: the strategy doesn't pick random moments. It scans
continuously and acts whenever the checklist clears. Sampling random
dates estimates the same underlying thing with extra noise and no
benefit.

So the sampling here is over **stocks**, not over **time**. A random
sample of names, then every checkpoint for each of them, taking every
signal that fires. Within the sampled names that's the actual strategy
rather than an approximation of it.

## The only comparison that settles anything

**Does it beat buying the index and doing nothing?**

This is the number to lead with, and it's easy to skip past, because a
strategy showing a profit feels like a strategy that works. It isn't the
same thing. If the method returns 7% a year over a stretch where the S&P
returned 17%, then the method lost 10 points a year — and cost real
effort and real risk to do it.

Two honest complications on that comparison:

- Money isn't always in the market. Between signals it sits in cash, so
  the strategy isn't taking the same risk as being fully invested. That
  cuts both ways: lower returns, but also nothing at stake during the
  gaps. `portfolio_sim` reports the return against both peak capital and
  average capital for this reason; the truth is somewhere between.
- **A defensive method should lose in a bull market.** Stage analysis is
  built to sidestep large declines. In a stretch where the index only
  goes up, sitting in cash and stopping out on pullbacks is pure cost.
  Judging it only on 2022-2026 tests the half of the method that isn't
  the point. This is why the long window matters more than the extra
  years suggest.

## What this project still cannot tell me

- **Whether it works in a crash**, which is its entire claimed purpose.
  Condition 6 exists to keep me out of a Stage 4 market and has never
  been exercised against a real one with sector data present.
- **Whether the thresholds are right**, as opposed to not obviously
  wrong on the windows I happened to look at. See
  [parameter-calibration.md](parameter-calibration.md).
- **Anything about slippage, commissions, or fills.** Every simulated
  entry and exit happens at a price from a weekly bar. Real orders don't.
