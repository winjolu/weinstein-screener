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
