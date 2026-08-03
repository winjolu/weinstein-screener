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
        # The most common way friction gets under-counted: you cross the
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
