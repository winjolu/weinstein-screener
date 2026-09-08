"""The conditioning logic behind I2, checked on constructed cases.

The returns machinery is I1's and is tested there. What is new here is
everything that decides *which* sales count as large or clustered, and
those are the parts where a plausible-looking mistake would produce a
plausible-looking finding.
"""
import unittest

import numpy as np
import pandas as pd

from market_core import costs, liquidity

from screener import insider_sales as sales


class ClusterSizeTest(unittest.TestCase):
    def _events(self, rows):
        return pd.DataFrame(rows, columns=["ticker", "filingdate", "ownername"])

    def test_distinct_people_are_counted_not_filings(self):
        """One insider filing four times in a week is one seller. Counting
        filings would make routine scheduled selling look like a stampede."""
        events = self._events([
            ("AAA", "2024-01-02", "same person"),
            ("AAA", "2024-01-03", "same person"),
            ("AAA", "2024-01-04", "same person"),
            ("AAA", "2024-01-05", "same person"),
        ])
        self.assertEqual(list(sales.cluster_sizes(events)), [1, 1, 1, 1])

    def test_the_window_is_trailing_not_centred(self):
        """The first filing cannot know about the second. A centred window
        would let a trade see sellers who had not filed yet."""
        events = self._events([
            ("AAA", "2024-01-01", "alice"),
            ("AAA", "2024-01-02", "bob"),
            ("AAA", "2024-01-03", "carol"),
        ])
        self.assertEqual(list(sales.cluster_sizes(events)), [1, 2, 3])

    def test_sellers_outside_the_window_drop_out(self):
        events = self._events([
            ("AAA", "2024-01-01", "alice"),
            ("AAA", "2024-03-01", "bob"),
        ])
        self.assertEqual(list(sales.cluster_sizes(events, window_days=30)), [1, 1])

    def test_companies_do_not_pool_with_each_other(self):
        events = self._events([
            ("AAA", "2024-01-01", "alice"),
            ("BBB", "2024-01-01", "bob"),
            ("AAA", "2024-01-02", "carol"),
        ])
        self.assertEqual(list(sales.cluster_sizes(events)), [1, 1, 2])


class MonthlyDecileTest(unittest.TestCase):
    def test_ranking_happens_inside_the_month_not_across_history(self):
        """A $1M sale is top-decile in a month of small sales and
        bottom-decile in a month of large ones. Pooling would rank by era."""
        small_month = [("2024-01-15", v) for v in range(1, 21)]
        big_month = [("2024-02-15", v) for v in range(1000, 1020)]
        events = pd.DataFrame(small_month + big_month,
                              columns=["filingdate", "value"])
        deciles = sales.monthly_decile(events, "value")
        january = deciles[events["filingdate"].str[:7] == "2024-01"]
        february = deciles[events["filingdate"].str[:7] == "2024-02"]
        self.assertEqual(january.max(), february.max())
        self.assertEqual(january.min(), february.min())

    def test_a_missing_measure_is_not_ranked_as_small(self):
        """NaN must stay NaN. Treating an uncomputable ratio as zero would
        silently fill the bottom decile with measurement failures."""
        events = pd.DataFrame({
            "filingdate": ["2024-01-01"] * 20,
            "value": list(range(1, 16)) + [np.nan] * 5,
        })
        deciles = sales.monthly_decile(events, "value")
        self.assertTrue(deciles[events["value"].isna()].isna().all())


class ShortReturnTest(unittest.TestCase):
    def test_the_sign_flips_and_borrow_is_subtracted(self):
        """A stock that fell 10% is a +10% short before costs, less the
        borrow, which comes off whether the short won or lost.

        63 trading days is about 91 calendar days, so 8% a year costs
        just over 2% here on the 360-day basis brokers use — a fifth of
        the gross move on a 10% fall, and the reason costing a short
        like a long flatters it badly.
        """
        won = sales.short_return_pct(-10.0, 63, costs.WEBULL_SHORT_HTB)
        self.assertAlmostEqual(won, 10.0 - 8.0 * 91.25 / 360, places=2)

    def test_a_losing_short_is_charged_borrow_too(self):
        lost = sales.short_return_pct(10.0, 63, costs.WEBULL_SHORT_HTB)
        self.assertLess(lost, -10.0)

    def test_a_higher_rate_costs_more(self):
        gc = sales.short_return_pct(-5.0, 63, costs.WEBULL_SHORT_GC)
        htb = sales.short_return_pct(-5.0, 63, costs.WEBULL_SHORT_HTB)
        self.assertGreater(gc, htb)

    def test_a_longer_hold_costs_more(self):
        short_hold = sales.short_return_pct(-5.0, 5, costs.WEBULL_SHORT_HTB)
        long_hold = sales.short_return_pct(-5.0, 63, costs.WEBULL_SHORT_HTB)
        self.assertGreater(short_hold, long_hold)


class TrailingDollarVolumeTest(unittest.TestCase):
    def test_a_normal_series_gives_the_median_turnover(self):
        n = 80
        close = np.full(n, 10.0)
        volume = np.full(n, 1000.0)
        dates = np.array([f"2024-01-{i:02d}" for i in range(1, n + 1)])
        out = sales._trailing_dollar_volume(dates, close, volume, np.array([70]))
        self.assertAlmostEqual(out[0], 10_000.0)

    def test_quantised_volume_refuses_rather_than_inflating(self):
        """The reverse-split case: price inflated, volume rounded up to a
        floor of one share. The product is meaningless and must not be
        returned as a number."""
        n = 80
        close = np.full(n, 84_096_088_812.0)
        volume = np.full(n, 1.0)
        dates = np.array([f"2024-01-{i:02d}" for i in range(1, n + 1)])
        out = sales._trailing_dollar_volume(dates, close, volume, np.array([70]))
        self.assertTrue(np.isnan(out[0]))

    def test_a_few_quantised_bars_do_not_veto_a_measurable_name(self):
        n = 80
        close = np.full(n, 10.0)
        volume = np.full(n, 1000.0)
        volume[:5] = 1.0
        dates = np.array([f"2024-01-{i:02d}" for i in range(1, n + 1)])
        out = sales._trailing_dollar_volume(dates, close, volume, np.array([70]))
        self.assertAlmostEqual(out[0], 10_000.0)

    def test_the_thresholds_come_from_the_shared_module(self):
        """Restating these locally is how two copies of a rule drift."""
        self.assertEqual(liquidity.VOLUME_FLOOR, 1.0)
        self.assertEqual(liquidity.MAX_QUANTISED, 0.25)


class ShipwreckTest(unittest.TestCase):
    def _panel(self, last_close, n=400):
        dates = pd.date_range("2020-01-01", periods=n, freq="D").strftime("%Y-%m-%d").to_numpy()
        closes = np.linspace(100.0, last_close, n)
        return {"DEAD": {"date": dates, "closeadj": closes,
                         "close": closes, "volume": np.full(n, 1000.0)},
                "LIVE": {"date": pd.date_range("2020-01-01", periods=2000, freq="D")
                         .strftime("%Y-%m-%d").to_numpy(),
                         "closeadj": np.full(2000, 100.0),
                         "close": np.full(2000, 100.0),
                         "volume": np.full(2000, 1000.0)}}

    def test_a_collapse_counts_as_a_shipwreck(self):
        panel = self._panel(last_close=5.0)
        events = pd.DataFrame({"ticker": ["DEAD"], "filingdate": ["2020-06-01"]})
        out = sales.shipwreck_outcomes(events, panel)
        self.assertTrue(out["stopped_trading"][0])
        self.assertTrue(out["sank"][0])

    def test_a_takeover_stops_trading_without_sinking(self):
        """Roughly 60% of the companies that left this archive were
        acquired, usually at a premium. Counting those as shipwrecks would
        measure takeovers and report them as disasters."""
        panel = self._panel(last_close=150.0)
        events = pd.DataFrame({"ticker": ["DEAD"], "filingdate": ["2020-06-01"]})
        out = sales.shipwreck_outcomes(events, panel)
        self.assertTrue(out["stopped_trading"][0])
        self.assertFalse(out["sank"][0])

    def test_a_living_company_neither_stops_nor_sinks(self):
        panel = self._panel(last_close=5.0)
        events = pd.DataFrame({"ticker": ["LIVE"], "filingdate": ["2020-06-01"]})
        out = sales.shipwreck_outcomes(events, panel)
        self.assertFalse(out["stopped_trading"][0])
        self.assertTrue(out["resolved"][0])

    def test_a_filing_too_close_to_the_end_of_the_archive_is_unresolved(self):
        """The series ending because the data ends is not a delisting.
        Counting it as one would make every recent filing a disaster."""
        panel = self._panel(last_close=5.0)
        events = pd.DataFrame({"ticker": ["LIVE"], "filingdate": ["2025-05-01"]})
        out = sales.shipwreck_outcomes(events, panel)
        self.assertFalse(out["resolved"][0])
        self.assertFalse(out["stopped_trading"][0])


if __name__ == "__main__":
    unittest.main()
