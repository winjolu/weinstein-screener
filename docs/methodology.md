# Weinstein Stage Analysis — Methodology Summary

Condensed from "Secrets for Profiting in Bull and Bear Markets" by
Stan Weinstein. This is my own summary in my own words, not reproduced
text. For the original, see the book itself (not in this repo — kept
locally in reference/, gitignored).

**Rewritten 2026-07-28 after reading the source directly.** The previous
version of this file described a nine-condition checklist scored
"at least 8 of 9 must be met". That rule is not in the book, and the
book contradicts it explicitly — see "What the book actually says about
partial compliance" below. Everything downstream of that rule inherited
the error, so this file now records what the source says and
[known-gaps.md](known-gaps.md) records where the code still diverges.

## Four Stages

1. **Stage 1 (Accumulation):** Base-building after a decline. Tight
   consolidation, low volume, price bouncing off support, moving
   average flattening out.
2. **Stage 2 (Advance):** Markup. Breaks above resistance on volume,
   higher highs and higher lows, price above a rising average.
3. **Stage 3 (Distribution):** Topping. Rallies lose force, lower highs,
   volume divergence, the average flattens.
4. **Stage 4 (Decline):** Markdown. Breaks below support, lower lows
   and lower highs, price below a falling average.

## The buying process is a sequence, not a scorecard

The book presents buying as an ordered funnel, and the verbs matter —
each step *discards* candidates rather than scoring them:

1. Check the major trend of the overall market.
2. Find the few groups (sectors) that look best technically.
3. List stocks in those groups with bullish patterns currently in
   trading ranges, and write down the breakout price for each.
4. Discard any with overhead resistance nearby.
5. Narrow further on relative strength.
6. Place buy-stop orders, good-till-cancelled, for **half** the intended
   position at the breakout price.
7. If volume confirms on the breakout and contracts on the pullback, buy
   the **second half** on a pullback toward the breakout level.
8. If volume does not confirm, sell into the first rally. If it doesn't
   rally and falls back below the breakout, exit immediately.

## The never-violate list

Separately from the sequence above, the book gives a list of conditions
under which one simply does not buy, introduced with the instruction never
to violate any of them:

- Don't buy when the overall market trend is bearish.
- Don't buy a stock in a negative group.
- Don't buy a stock below its 30-week moving average.
- Don't buy a stock whose 30-week average is declining, even if price is
  above it.
- **Don't buy too late in an advance, far above the ideal entry point,
  no matter how bullish the stock looks.**
- Don't buy on a breakout with poor volume. If a resting buy-stop fills
  anyway, sell it quickly.
- Don't buy a stock with poor relative strength.
- Don't buy a stock with heavy overhead resistance nearby.
- Don't guess a bottom — buy breakouts above resistance instead.

## What the book actually says about partial compliance

This is the point the earlier version of this file got wrong, and it
isn't a matter of interpretation. The book poses a quiz question asking
whether, when every other factor is positive — market trend, group
strength, minimal resistance — a lack of volume confirmation can be
overlooked. The answer given is no: never overlook poor volume on a
breakout, because it signals the move lacks staying power.

That is precisely the reasoning a "8 of 9 conditions" rule encodes. The
book sets it up as the wrong answer. Where the book describes a setup it
approves of, it says *all* the criteria were fulfilled — it never counts
them or tolerates a shortfall.

## Stop placement

The book is emphatic that there is no correct fixed percentage, and that
placing stops at a standard 10-12-15% below the current price is bad
advice — the market has no knowledge of what I paid. Two anchors
determine the level instead: **the prior support level and the 30-week
moving average**. For the *initial* stop specifically, weight the prior
correction low more heavily than the average.

In practice that produces something like 8% below the purchase price in
one case and 12% or more in another. The percentage is an output, not an
input.

Three rules constrain it:

- **Never hold without a protective stop.** Enter a good-till-cancelled
  sell-stop as soon as the position is opened.
- **Calculate the stop before placing the buy order**, so that the
  resulting risk acts as a further filter on the candidate list.
- **Limit purchases to those where the initial stop is no more than 15%
  below the purchase price.** The book allows occasional exceptions for
  an outstanding pattern, but states this as the working limit, and
  frames it as a rule about which stocks one is permitted to buy —
  not as a factor to weigh.

That last rule is the direct answer to "how can a single trade lose
62%": under the book's method it cannot, because the purchase never
happens.

The book also gives a refinement: when the calculated stop lands on or
just above a round number, place it just *below* that number instead,
since buy orders accumulate at round numbers and a violation there is
genuinely meaningful. The same applies more weakly at halves.

## Trailing the stop

While price is above a rising 30-week average, give the position room.
Then:

1. Wait for the first substantial correction — at least 8-10%.
2. Do not move the stop yet. Wait until the correction ends and the
   stock rallies back near its prior high.
3. Then raise the stop: if breaking the correction low would also
   violate the 30-week average, use that level; if the correction low
   sits above the rising average, place the stop below the average.
4. Keep raising it as the average advances, repeating the same
   wait-for-the-rally discipline each time.
5. **Once the average stops rising and flattens**, a Stage 3 top becomes
   likely. From that point, tighten: move the stop under the correction
   low even when that sits above the average.

## Where my implementation departs from this

Recorded here so the divergence is visible from the methodology itself
rather than only from the code. Details and current status in
[known-gaps.md](known-gaps.md):

- The nine conditions are scored as a ratio with a 0.80 threshold, so any
  single condition may fail. The book treats them as gates.
- The 15% stop limit is implemented as one condition of nine rather than
  as a constraint on purchasing.
- "Don't buy too late in an advance" exists only as an advisory flag on
  the entry plan, measured against the breakout level rather than
  against the moving average.
- Price data is dividend-adjusted, so support, resistance and round
  numbers sit at synthetic levels rather than the ones traders acted on.
- The round-number refinement is not implemented at all.
