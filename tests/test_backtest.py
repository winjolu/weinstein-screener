"""Backtest regressions — chiefly the no-lookahead property.

This is the one that matters most for the backtest's credibility. The
whole engine is worthless if an evaluation "as of" a past date can see
bars that hadn't happened yet, and that failure is invisible in the
output: results simply look better than they should.

The property asserted here is the strong form. Rather than checking
that truncation happens, it checks that the answer is *identical*
whether or not future data was ever present in the input. If any future
bar leaked into a calculation, the two would diverge.
"""
import unittest

from screener import backtest, stop_loss
from tests.synthetic import bar, daily_dates, trending_bars, weekly_dates


def _sector(daily_bars_a, daily_bars_b):
    return {"sector": "Oil & Gas", "sector_etf_bars": daily_bars_a, "spy_bars": daily_bars_b}


class NoLookaheadTest(unittest.TestCase):
    def setUp(self):
        self.bars = trending_bars(150, 100.0, 0.7)
        self.index = trending_bars(150, 400.0, 0.3)
        self.etf = trending_bars(300, 50.0, 0.05, start="2023-01-03", daily=True)
        self.spy = trending_bars(300, 400.0, 0.04, start="2023-01-03", daily=True)

    def _truncate(self, bars, as_of):
        return [b for b in bars if b["time"][:10] <= as_of]

    def test_future_bars_cannot_change_an_as_of_evaluation(self):
        for idx in (60, 80, 100, 120):
            as_of = self.bars[idx]["time"][:10]

            with_future = backtest.evaluate_as_of(
                "T", as_of, self.bars, self.index, _sector(self.etf, self.spy)
            )
            without_future = backtest.evaluate_as_of(
                "T", as_of,
                self._truncate(self.bars, as_of), self._truncate(self.index, as_of),
                _sector(self._truncate(self.etf, as_of), self._truncate(self.spy, as_of)),
            )

            self.assertEqual(with_future["conditions"], without_future["conditions"], as_of)
            self.assertEqual(with_future["scoring"], without_future["scoring"], as_of)
            self.assertEqual(with_future["breakout_idx"], without_future["breakout_idx"], as_of)
            self.assertEqual(with_future["swing_stop"], without_future["swing_stop"], as_of)
            self.assertEqual(with_future["bars_used"], without_future["bars_used"], as_of)

    def test_sector_snapshot_is_never_used_for_a_past_date(self):
        """The live sector-overview figure has no as-of parameter, so using
        today's value for a historical date would be lookahead rather than
        imprecision. It must stay None.
        """
        as_of = self.bars[100]["time"][:10]
        result = backtest.evaluate_as_of(
            "T", as_of, self.bars, self.index, _sector(self.etf, self.spy)
        )
        detail = result["conditions_detail"]["sector_strength"]
        self.assertIsNone(detail.get("sector_strength_pct"))


class TruncationTest(unittest.TestCase):
    def test_keeps_the_as_of_date_itself(self):
        bars = trending_bars(10)
        as_of = bars[4]["time"][:10]
        kept = backtest._truncate_bars(bars, as_of)
        self.assertEqual(len(kept), 5)
        self.assertEqual(kept[-1]["time"][:10], as_of)


class SimulateTradeTest(unittest.TestCase):
    def _bars(self, closes):
        dates = weekly_dates(len(closes))
        return [bar(d, c * 1.02, c * 0.98, c) for d, c in zip(dates, closes)]

    def test_stop_exit_is_capped_at_one_r(self):
        """A stop-out should lose about the risk that was defined up front.
        Losing materially more means the stop isn't being honoured.
        """
        closes = [100.0] * 10 + [95.0, 90.0, 85.0, 80.0, 75.0]
        bars = self._bars(closes)
        entry_date = bars[9]["time"][:10]
        trade = backtest.simulate_trade(
            "T", entry_date, 100.0, swing_stop=95.0, swing_target=130.0, bars_full=bars,
        )
        self.assertEqual(trade["exit_reason"], "stop")
        self.assertLessEqual(trade["r_multiple"], 0.0)
        self.assertGreaterEqual(trade["r_multiple"], -1.6)

    def test_unresolved_trade_reports_still_open_without_inventing_a_return(self):
        closes = [100.0 + i * 0.05 for i in range(20)]
        bars = self._bars(closes)
        trade = backtest.simulate_trade(
            "T", bars[2]["time"][:10], bars[2]["close"],
            swing_stop=50.0, swing_target=500.0, bars_full=bars, max_hold_weeks=5,
        )
        self.assertTrue(trade["still_open"])
        self.assertIsNone(trade["return_pct"])
        self.assertIsNone(trade["r_multiple"])

    def test_unknown_entry_date_returns_none(self):
        self.assertIsNone(
            backtest.simulate_trade("T", "1999-01-01", 10.0, 9.0, 12.0, self._bars([10.0] * 5))
        )


class PartialProfitTakingTest(unittest.TestCase):
    """The target sells part of the position; the rest rides the trailing
    stop. Exiting fully at the target truncated every winner at its own
    measured objective, which quietly turned a trend-following method
    into a fixed-target one — and nothing in the suite covered the target
    path at all, which is why it went unnoticed.
    """

    def _bars(self, closes):
        dates = weekly_dates(len(closes))
        return [bar(d, c * 1.02, c * 0.98, c) for d, c in zip(dates, closes)]

    TARGET = 120.0

    def _run_past_target(self, **kw):
        # A 40-week warm-up so the 30-week MA the trailing stop rides
        # actually exists, then entry, a rally clean through the target,
        # and a decline deep enough to take the remainder out.
        closes = (
            [60.0 + i for i in range(40)]
            + [110.0, 125.0, 150.0, 175.0, 200.0, 160.0, 140.0, 120.0, 100.0, 95.0]
        )
        bars = self._bars(closes)
        return backtest.simulate_trade(
            "T", bars[39]["time"][:10], closes[39],
            swing_stop=90.0, swing_target=self.TARGET, bars_full=bars, **kw
        )

    def test_reaching_the_target_does_not_close_the_position(self):
        trade = self._run_past_target()
        self.assertEqual(trade["exit_reason"], "target_then_stop")
        # Exited later and lower than the target, which can only happen
        # if the remainder kept running after the target was reached.
        self.assertNotAlmostEqual(trade["exit_price"], self.TARGET, places=6)

    def test_blend_is_the_position_weighted_average_of_the_two_legs(self):
        """Verified against the ends of the range rather than an assumed
        remainder price: selling none must equal the trailing-stop exit,
        selling all must equal the target, and half must sit exactly
        between them."""
        none_taken = self._run_past_target(partial_exit_fraction=0.0)["exit_price"]
        all_taken = self._run_past_target(partial_exit_fraction=1.0)["exit_price"]
        half_taken = self._run_past_target(partial_exit_fraction=0.5)["exit_price"]

        self.assertAlmostEqual(all_taken, self.TARGET, places=6)
        self.assertAlmostEqual(half_taken, 0.5 * all_taken + 0.5 * none_taken, places=6)

    def test_the_module_default_is_patchable(self):
        """The fraction has to be read at call time. Bound as a default
        argument it fixes at import, so patching it to compare exit
        policies changes nothing and both arms of the A/B run identically
        — which looks like a null result rather than a broken test.
        """
        original = backtest.PARTIAL_EXIT_FRACTION
        try:
            backtest.PARTIAL_EXIT_FRACTION = 1.0
            self.assertAlmostEqual(self._run_past_target()["exit_price"], self.TARGET, places=6)
            backtest.PARTIAL_EXIT_FRACTION = 0.0
            self.assertNotAlmostEqual(self._run_past_target()["exit_price"], self.TARGET, places=6)
        finally:
            backtest.PARTIAL_EXIT_FRACTION = original

    def test_the_fraction_moves_the_blend_monotonically(self):
        prices = [
            self._run_past_target(partial_exit_fraction=f)["exit_price"]
            for f in (0.0, 0.25, 0.5, 0.75, 1.0)
        ]
        self.assertEqual(prices, sorted(prices), "blend should move steadily toward the target")

    def test_stopping_before_the_target_is_unaffected(self):
        closes = [100.0] * 5 + [95.0, 88.0, 80.0]
        bars = self._bars(closes)
        trade = backtest.simulate_trade(
            "T", bars[4]["time"][:10], 100.0,
            swing_stop=95.0, swing_target=130.0, bars_full=bars,
        )
        self.assertEqual(trade["exit_reason"], "stop")

    def test_a_banked_partial_does_not_make_an_open_trade_scoreable(self):
        """Half realised and half still running is not a finished trade;
        counting the unrealised remainder would flatter the result."""
        closes = [100.0] * 5 + [130.0, 135.0, 140.0]
        bars = self._bars(closes)
        trade = backtest.simulate_trade(
            "T", bars[4]["time"][:10], 100.0,
            swing_stop=90.0, swing_target=120.0, bars_full=bars, max_hold_weeks=3,
        )
        self.assertTrue(trade["still_open"])
        self.assertEqual(trade["exit_reason"], "target_then_open")
        self.assertIsNone(trade["return_pct"])


class TrailingStopTest(unittest.TestCase):
    def test_stop_ratchets_and_never_retreats(self):
        """A trailing stop that can move down isn't a trailing stop."""
        bars = trending_bars(120, 100.0, 1.5)
        entry_idx = 60
        previous = None
        for end in range(entry_idx + 5, len(bars) + 1, 5):
            trail = stop_loss.trailing_stop(bars[:end], bars[entry_idx]["close"], entry_idx)
            current = trail["ma_stop"]
            if current is not None and previous is not None:
                self.assertGreaterEqual(current, previous - 1e-9)
            if current is not None:
                previous = current

    def test_out_of_range_entry_returns_none(self):
        bars = trending_bars(20)
        self.assertIsNone(stop_loss.trailing_stop(bars, 100.0, None))
        self.assertIsNone(stop_loss.trailing_stop(bars, 100.0, 999))

    def test_short_side_ratchets_downward(self):
        bars = trending_bars(120, 200.0, -1.2)
        entry_idx = 60
        previous = None
        for end in range(entry_idx + 5, len(bars) + 1, 5):
            trail = stop_loss.short_trailing_stop(bars[:end], bars[entry_idx]["close"], entry_idx)
            current = trail["ma_stop"]
            if current is not None and previous is not None:
                self.assertLessEqual(current, previous + 1e-9)
            if current is not None:
                previous = current


if __name__ == "__main__":
    unittest.main()
