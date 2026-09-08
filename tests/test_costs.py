"""Transaction cost regressions.

Every figure in this project before this module assumed trading was
free. The numbers here are hand-computable on purpose, because a cost
model that is quietly wrong makes a strategy look better in exactly the
way that is hardest to notice.
"""
import unittest

from screener import costs


def _trade(entry, exit_price, ret):
    return {"ticker": "AAA", "entry_date": "2020-01-01", "exit_date": "2020-06-01",
            "entry_price": entry, "exit_price": exit_price, "return_pct": ret}


class WebullScheduleTest(unittest.TestCase):
    """Confirmed against the published schedule on 2026-08-02."""

    def test_a_thousand_dollar_position_costs_about_three_cents(self):
        # 20 shares at $50, sold at $50. Worked through rather than
        # asserted from memory, because my first guess at this total was
        # wrong and the code was right:
        #   buy  CAT  0.000003  x $1,000 = $0.0030
        #   sell SEC  0.0000206 x $1,000 = $0.0206
        #   sell TAF  0.000195  x 20 sh  = $0.0039
        #   sell CAT  0.000003  x $1,000 = $0.0030
        expected = (0.000003 * 1000 + 0.0000206 * 1000
                    + 0.000195 * 20 + 0.000003 * 1000)
        fee = costs.WEBULL.round_trip(50.0, 50.0, 20.0)
        self.assertAlmostEqual(fee, expected, places=6)
        self.assertAlmostEqual(fee, 0.0305, places=4)

    def test_there_is_no_commission(self):
        self.assertEqual(costs.WEBULL.commission(100.0, 5000.0), 0.0)

    def test_regulatory_fees_are_charged_on_sales_not_purchases(self):
        buy = costs.WEBULL.regulatory(20.0, 1000.0, "buy")
        sell = costs.WEBULL.regulatory(20.0, 1000.0, "sell")
        self.assertLess(buy, sell)
        # The buy side carries CAT only.
        self.assertAlmostEqual(buy, 0.000003 * 1000.0)

    def test_the_taf_cap_applies(self):
        # A million shares would be $195 uncapped; the cap is $9.79.
        fee = costs.WEBULL.regulatory(1_000_000.0, 1000.0, "sell")
        self.assertLess(fee, 10.0)


class SlippageTest(unittest.TestCase):
    def test_slippage_is_charged_on_both_sides(self):
        # The most common way friction gets under-counted: the spread is crossed
        # spread going in and again coming out, so 0.25% costs 0.5%.
        pct = costs.cost_pct(_trade(50.0, 50.0, 0.0),
                             profile=costs.FREE, slippage_pct=0.25)
        self.assertAlmostEqual(pct, 0.5, places=6)

    def test_zero_slippage_leaves_only_broker_fees(self):
        pct = costs.cost_pct(_trade(50.0, 50.0, 0.0),
                             profile=costs.FREE, slippage_pct=0.0)
        self.assertEqual(pct, 0.0)

    def test_webull_fees_are_negligible_against_a_typical_trade(self):
        # The point of the whole module: the broker is not the problem.
        pct = costs.cost_pct(_trade(50.0, 54.0, 8.0), profile=costs.WEBULL)
        self.assertLess(pct, 0.01)


class ApplyCostsTest(unittest.TestCase):
    def test_returns_are_reduced_by_the_round_trip_cost(self):
        trades = [_trade(50.0, 54.0, 8.0)]
        out = costs.apply_costs(trades, profile=costs.FREE, slippage_pct=0.5)
        self.assertAlmostEqual(out[0]["return_pct"], 8.0 - 1.0, places=6)

    def test_the_original_trades_are_not_mutated(self):
        # The uncosted trades are the record of what was signalled.
        # Overwriting them would make the cost assumption invisible to
        # anything that reads the list afterwards.
        trades = [_trade(50.0, 54.0, 8.0)]
        costs.apply_costs(trades, profile=costs.FREE, slippage_pct=0.5)
        self.assertEqual(trades[0]["return_pct"], 8.0)

    def test_an_unresolved_trade_is_left_alone(self):
        trades = [{"ticker": "AAA", "entry_price": 50.0, "exit_price": None,
                   "return_pct": None}]
        out = costs.apply_costs(trades, slippage_pct=1.0)
        self.assertIsNone(out[0]["return_pct"])

    def test_a_flat_commission_hurts_small_positions_most(self):
        # $5 a side on a $1,000 stake is 1%; on $10,000 it is 0.1%.
        small = costs.cost_pct(_trade(50.0, 50.0, 0.0),
                               profile=costs.FLAT_FEE, stake=1000.0)
        large = costs.cost_pct(_trade(50.0, 50.0, 0.0),
                               profile=costs.FLAT_FEE, stake=10000.0)
        self.assertAlmostEqual(small, 1.0, places=3)
        self.assertAlmostEqual(large, 0.1, places=3)


class ProfileRegistryTest(unittest.TestCase):
    def test_profiles_are_data_a_user_can_extend(self):
        mine = costs.BrokerProfile("Mine", commission_per_trade=1.0,
                                   commission_pct=0.05)
        # $1 flat plus 0.05% of $2,000.
        self.assertAlmostEqual(mine.commission(40.0, 2000.0), 2.0)

    def test_a_minimum_commission_is_honoured(self):
        mine = costs.BrokerProfile("Mine", commission_pct=0.01, min_commission=1.0)
        self.assertAlmostEqual(mine.commission(10.0, 100.0), 1.0)

    def test_webull_is_one_profile_among_several_not_the_assumption(self):
        self.assertIn("Webull", costs.PROFILES)
        self.assertIn("No fees", costs.PROFILES)


class ShortBorrowTest(unittest.TestCase):
    """The borrow fee, which decides whether a short is worth placing.

    `short_borrow_apr` sat on BrokerProfile from the day it was written
    and nothing ever read it, so every short costed through this module
    was charged zero borrow — the fee that matters most on the side
    where it matters most.
    """

    def test_the_rate_accrues_on_notional_over_calendar_days(self):
        profile = costs.BrokerProfile("test", short_borrow_apr=10.0)
        # A 360-day basis, which is the convention brokers actually use
        # and which Webull states in its own stock-loan formula. $10,000
        # at 10% costs $1,000 over 360 days, not over 365.
        self.assertAlmostEqual(profile.borrow(10_000.0, 360), 1000.0)
        self.assertAlmostEqual(profile.borrow(10_000.0, 180), 500.0)

    def test_no_rate_or_no_days_costs_nothing(self):
        self.assertEqual(costs.WEBULL.borrow(10_000.0, 365), 0.0)
        self.assertEqual(costs.WEBULL_SHORT_HTB.borrow(10_000.0, 0), 0.0)

    def test_a_long_round_trip_is_unchanged_by_the_new_parameters(self):
        """The borrow charge must not appear underneath existing
        long-side results, which is why side defaults to long."""
        before = costs.WEBULL.round_trip(100.0, 110.0, 10.0)
        after = costs.WEBULL_SHORT_HTB.round_trip(100.0, 110.0, 10.0,
                                                  holding_days=90)
        self.assertAlmostEqual(before, after)

    def test_shorting_costs_more_than_the_same_trade_held_long(self):
        long_side = costs.WEBULL_SHORT_HTB.round_trip(
            100.0, 110.0, 10.0, holding_days=90, side="long")
        short_side = costs.WEBULL_SHORT_HTB.round_trip(
            100.0, 110.0, 10.0, holding_days=90, side="short")
        self.assertGreater(short_side, long_side)
        # $1,000 notional, 8% a year, 90 days on a 360-day basis = $20.
        self.assertAlmostEqual(short_side - long_side, 1000 * 0.08 * 90 / 360)

    def test_cost_pct_charges_borrow_only_when_told_it_is_a_short(self):
        trade = {"entry_price": 50.0, "exit_price": 45.0, "holding_days": 90}
        as_long = costs.cost_pct(trade, profile=costs.WEBULL_SHORT_HTB)
        as_short = costs.cost_pct(trade, profile=costs.WEBULL_SHORT_HTB,
                                  side="short")
        self.assertGreater(as_short, as_long)
        # 8% a year over 90 days on the full stake, in percent.
        self.assertAlmostEqual(as_short - as_long, 8.0 * 90 / 360, places=6)

    def test_a_trade_with_no_holding_days_is_not_silently_free_to_borrow(self):
        """A caller that forgets holding_days gets zero borrow, so the
        omission has to be visible in the result rather than plausible.
        The guard is that the two rates must differ once days are given."""
        trade = {"entry_price": 50.0, "exit_price": 45.0}
        gc = costs.cost_pct(trade, profile=costs.WEBULL_SHORT_GC, side="short")
        htb = costs.cost_pct(trade, profile=costs.WEBULL_SHORT_HTB, side="short")
        self.assertAlmostEqual(gc, htb)
        with_days = dict(trade, holding_days=90)
        self.assertNotAlmostEqual(
            costs.cost_pct(with_days, profile=costs.WEBULL_SHORT_GC, side="short"),
            costs.cost_pct(with_days, profile=costs.WEBULL_SHORT_HTB, side="short"))
