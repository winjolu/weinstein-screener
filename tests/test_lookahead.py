"""The look-ahead detector, tested against strategies that do and don't cheat.

A detector that never fires is indistinguishable from a clean codebase,
so the honest tests here are the ones where it must catch something. The
cheating strategies below are deliberate: each reads a bar it could not
have seen, in a way that would look perfectly reasonable in review.
"""
import datetime
import unittest

from market_core import lookahead


def _bars(n=120, start="2024-01-01"):
    day = datetime.date.fromisoformat(start)
    out = []
    price = 100.0
    for i in range(n):
        price *= 1.004 if i % 3 else 0.995
        out.append({"time": (day + datetime.timedelta(days=i)).isoformat(),
                    "close": round(price, 4)})
    return out


UNIVERSE = {"AAA": _bars(), "BBB": _bars(start="2024-01-01")}


def honest(bars_by_symbol):
    """Buys when a bar closes above the mean of the ten bars before it.

    Reads only completed history, so removing the tail cannot change any
    earlier decision.
    """
    out = []
    for ticker, bars in bars_by_symbol.items():
        for i in range(10, len(bars)):
            window = [b["close"] for b in bars[i - 10:i]]
            if bars[i]["close"] > sum(window) / len(window):
                out.append({"ticker": ticker, "entry_date": bars[i]["time"][:10],
                            "entry_price": bars[i]["close"]})
    return out


def peeks_at_the_end(bars_by_symbol):
    """Buys only when the bar is below the final close of the whole series.

    The bug this imitates is ordinary: a threshold computed once from the
    entire dataset and then applied bar by bar. Nothing in the loop looks
    wrong.
    """
    out = []
    for ticker, bars in bars_by_symbol.items():
        final = bars[-1]["close"]
        for i in range(10, len(bars)):
            if bars[i]["close"] < final:
                out.append({"ticker": ticker, "entry_date": bars[i]["time"][:10],
                            "entry_price": bars[i]["close"]})
    return out


def prices_off_by_one_bar(bars_by_symbol):
    """Same entries as honest(), but records tomorrow's close as the fill.

    The entry set is identical, so a check comparing only which positions
    were taken would pass. Only comparing the values catches it.
    """
    out = []
    for ticker, bars in bars_by_symbol.items():
        for i in range(10, len(bars) - 1):
            window = [b["close"] for b in bars[i - 10:i]]
            if bars[i]["close"] > sum(window) / len(window):
                out.append({"ticker": ticker, "entry_date": bars[i]["time"][:10],
                            "entry_price": bars[i + 1]["close"]})
    return out


class TruncationTest(unittest.TestCase):
    def test_truncate_removes_exactly_the_tail(self):
        cut = lookahead.truncate(UNIVERSE, 20)
        self.assertEqual(len(cut["AAA"]), len(UNIVERSE["AAA"]) - 20)
        self.assertEqual(cut["AAA"][-1], UNIVERSE["AAA"][-21])

    def test_truncating_nothing_is_refused(self):
        # A check that removes no data compares a run against itself and
        # always passes.
        with self.assertRaises(ValueError):
            lookahead.truncate(UNIVERSE, 0)

    def test_a_series_shorter_than_the_cut_is_dropped(self):
        universe = dict(UNIVERSE, TINY=_bars(5))
        self.assertNotIn("TINY", lookahead.truncate(universe, 20))

    def test_the_cutoff_comes_from_the_reference_series(self):
        # A thin symbol has its own last bar; using it would cut earlier
        # than the strategy actually saw.
        universe = dict(UNIVERSE, THIN=_bars(40))
        cut = lookahead.cutoff_date(universe, 20, reference="AAA")
        self.assertEqual(cut.isoformat(), UNIVERSE["AAA"][-21]["time"][:10])


class DetectionTest(unittest.TestCase):
    def test_an_honest_strategy_passes(self):
        problems, n = lookahead.check(honest, UNIVERSE, drop_last=20, reference="AAA")
        self.assertEqual(problems, [])
        self.assertGreater(n, 0, "nothing was compared, so nothing was tested")

    def test_a_strategy_reading_the_final_bar_is_caught(self):
        with self.assertRaises(lookahead.LookaheadDetected):
            lookahead.check(peeks_at_the_end, UNIVERSE, drop_last=20, reference="AAA")

    def test_a_leak_in_the_price_alone_is_caught(self):
        # Identical entry dates, wrong fill price. Comparing only which
        # positions were taken would miss this entirely.
        with self.assertRaises(lookahead.LookaheadDetected):
            lookahead.check(prices_off_by_one_bar, UNIVERSE, drop_last=20,
                            reference="AAA")

    def test_records_after_the_cutoff_are_not_counted_as_differences(self):
        # The short run cannot produce them. Counting them would report
        # look-ahead for every strategy ever written.
        problems, _ = lookahead.check(honest, UNIVERSE, drop_last=40,
                                      reference="AAA", raises=False)
        self.assertEqual(problems, [])

    def test_an_empty_run_raises_rather_than_passing_quietly(self):
        # The archival guard found no watermark and permitted everything,
        # looking installed. A check with nothing to compare must fail.
        with self.assertRaises(lookahead.LookaheadDetected) as caught:
            lookahead.check(lambda bars: [], UNIVERSE, drop_last=20, reference="AAA")
        self.assertIn("nothing to compare", str(caught.exception))

    def test_raises_false_reports_instead_of_throwing(self):
        problems, _ = lookahead.check(peeks_at_the_end, UNIVERSE, drop_last=20,
                                      reference="AAA", raises=False)
        self.assertTrue(problems)

    def test_the_message_names_the_offending_positions(self):
        with self.assertRaises(lookahead.LookaheadDetected) as caught:
            lookahead.check(peeks_at_the_end, UNIVERSE, drop_last=20, reference="AAA")
        text = str(caught.exception)
        self.assertIn("AAA", text)
        self.assertIn("reading ahead", text)


class IntrabarDependenceTest(unittest.TestCase):
    """The failure truncation cannot see.

    A signal comparing close[i] against an average ending at i-1 produces
    identical positions whether or not the tail exists, so the truncation
    check passes while the strategy is still crediting itself with a move
    that predates its own information.
    """

    def test_truncation_does_not_catch_an_intrabar_leak(self):
        # Recorded rather than lamented: this is the real limit, and the
        # test exists so nobody re-reads the docstring as optimism.
        def leaky(bars_by_symbol):
            out = []
            for ticker, bars in bars_by_symbol.items():
                cl = [b["close"] for b in bars]
                for i in range(10, len(bars)):
                    if cl[i] > sum(cl[i - 10:i]) / 10:
                        out.append({"ticker": ticker,
                                    "entry_date": bars[i]["time"][:10],
                                    "entry_price": cl[i]})
            return out
        problems, n = lookahead.check(leaky, UNIVERSE, drop_last=20,
                                      reference="AAA", raises=False)
        self.assertEqual(problems, [], "truncation is not expected to catch this")
        self.assertGreater(n, 0)

    def test_the_diagnostic_does_catch_it(self):
        def leaky(bars_by_symbol):
            out = []
            for ticker, bars in bars_by_symbol.items():
                cl = [b["close"] for b in bars]
                for i in range(10, len(bars)):
                    if cl[i] > sum(cl[i - 10:i]) / 10:
                        out.append({"ticker": ticker,
                                    "entry_date": bars[i]["time"][:10],
                                    "entry_price": cl[i]})
            return out
        hits = lookahead.intrabar_dependence(leaky, UNIVERSE, "AAA", sample=12)
        self.assertTrue(hits, "a decision made from its own bar should be reported")

    def test_a_strategy_deciding_only_from_prior_bars_reports_nothing(self):
        def lagged(bars_by_symbol):
            out = []
            for ticker, bars in bars_by_symbol.items():
                cl = [b["close"] for b in bars]
                for i in range(11, len(bars)):
                    if cl[i - 1] > sum(cl[i - 11:i - 1]) / 10:
                        out.append({"ticker": ticker,
                                    "entry_date": bars[i]["time"][:10],
                                    "entry_price": cl[i - 1]})
            return out
        hits = lookahead.intrabar_dependence(lagged, UNIVERSE, "AAA", sample=12)
        self.assertEqual(hits, [])
