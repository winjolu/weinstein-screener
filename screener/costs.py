"""What it costs to actually place the trades this screener suggests.

Every result recorded in this project so far assumes trading is free. It
isn't, and the two components behave completely differently:

**Broker fees** are small, knowable, and published. Webull's schedule on
a $1,000 position comes to about three cents round trip — against a mean
trade of roughly +8%, that is not a rounding error, it *is* the
rounding.

**Spread and slippage** are neither small nor published. Nobody charges
them; you pay them to the market by buying at the ask and selling at the
bid. On a liquid large cap that might be 0.05%. On the small community
banks in this universe it can be one or two percent, which against the
same +8% mean is a fifth of everything.

So the interesting question is not "what does my broker charge" — that
is answerable to the penny and barely matters. It is **how much friction
can this strategy survive**, which is why `breakeven_sweep` exists and
why slippage is a parameter rather than a constant.

Broker profiles are data rather than code so a user can drop in their
own. Webull ships as one profile among several, not as the assumption.
"""


class BrokerProfile:
    """A broker's cost structure.

    Every field defaults to zero, so a profile only states what it
    actually charges and an unspecified fee is absent rather than
    silently guessed.
    """

    def __init__(self, name, commission_per_trade=0.0, commission_per_share=0.0,
                 commission_pct=0.0, min_commission=0.0, max_commission=None,
                 sec_fee_rate=0.0, taf_per_share=0.0, taf_max=None,
                 cat_fee_rate=0.0, short_borrow_apr=0.0):
        self.name = name
        self.commission_per_trade = commission_per_trade
        self.commission_per_share = commission_per_share
        self.commission_pct = commission_pct
        self.min_commission = min_commission
        self.max_commission = max_commission
        # Regulatory pass-throughs. SEC and FINRA TAF are charged on
        # sales only; CAT applies to both sides. These are set by the
        # regulators and change periodically, so they belong in the
        # profile rather than hard-coded anywhere.
        self.sec_fee_rate = sec_fee_rate
        self.taf_per_share = taf_per_share
        self.taf_max = taf_max
        self.cat_fee_rate = cat_fee_rate
        self.short_borrow_apr = short_borrow_apr

    def commission(self, shares, value):
        fee = (self.commission_per_trade
               + self.commission_per_share * shares
               + self.commission_pct / 100.0 * value)
        if self.min_commission:
            fee = max(fee, self.min_commission)
        if self.max_commission is not None:
            fee = min(fee, self.max_commission)
        return fee

    def regulatory(self, shares, value, side):
        """`side` is 'buy' or 'sell'. Most of these are sell-side only."""
        fee = self.cat_fee_rate * value
        if side == "sell":
            fee += self.sec_fee_rate * value
            taf = self.taf_per_share * shares
            if self.taf_max is not None:
                taf = min(taf, self.taf_max)
            fee += taf
        return fee

    def round_trip(self, entry_price, exit_price, shares):
        """Total fees for opening and closing one position."""
        buy_value = entry_price * shares
        sell_value = exit_price * shares
        return (self.commission(shares, buy_value)
                + self.regulatory(shares, buy_value, "buy")
                + self.commission(shares, sell_value)
                + self.regulatory(shares, sell_value, "sell"))


# Confirmed against Webull's published schedule on 2026-08-02. Zero
# commission; the rest are regulatory pass-throughs they don't keep.
WEBULL = BrokerProfile(
    "Webull",
    sec_fee_rate=0.0000206,
    taf_per_share=0.000195,
    taf_max=9.79,
    cat_fee_rate=0.000003,
)

# A per-trade commission of the sort many brokers charged before 2019,
# kept so the sweep can show what this strategy's trade frequency would
# have cost under an older structure.
FLAT_FEE = BrokerProfile("Flat $5", commission_per_trade=5.0)

FREE = BrokerProfile("No fees")

PROFILES = {p.name: p for p in (WEBULL, FLAT_FEE, FREE)}


def cost_pct(trade, profile=WEBULL, slippage_pct=0.0, stake=1000.0):
    """Round-trip cost of one trade as a percentage of the stake.

    Slippage is charged on both sides — you cross the spread going in and
    again coming out — so a 0.25% figure costs 0.5% over the round trip.
    That doubling is the single most common way friction gets
    under-counted.
    """
    entry = trade.get("entry_price")
    exit_price = trade.get("exit_price")
    if not entry or not exit_price:
        return 0.0
    shares = stake / entry
    fees = profile.round_trip(entry, exit_price, shares)
    slip = slippage_pct / 100.0 * stake * 2
    return (fees + slip) / stake * 100.0


def apply_costs(trades, profile=WEBULL, slippage_pct=0.0, stake=1000.0):
    """Copies of `trades` with return_pct reduced by round-trip cost.

    Returns copies rather than mutating: the uncosted trades are the
    record of what the strategy signalled, and overwriting them would
    make the cost assumption invisible to anything reading later.
    """
    out = []
    for trade in trades:
        adjusted = dict(trade)
        if trade.get("return_pct") is not None:
            adjusted["return_pct"] = trade["return_pct"] - cost_pct(
                trade, profile, slippage_pct, stake)
        out.append(adjusted)
    return out
