"""Nearest-neighbour ranking.

Four failure modes would each produce a convincing result from nothing:
retrieving the same stock's own adjacent weeks, letting one feature's
units dominate the distance, dropping a whole feature over a few missing
values, and predicting the mean of a fat-tailed target. Each gets a test
rather than a comment.
"""
import unittest

from screener import neighbours


def _row(ticker, ret, **features):
    row = {"ticker": ticker, "entry_date": "2020-01-01", "return_pct": ret}
    row.update(features)
    return row


class FeatureSelectionTest(unittest.TestCase):
    def test_bookkeeping_columns_are_not_features(self):
        names = neighbours.feature_names([_row("AAA", 10.0, rs=30.0)])
        self.assertIn("rs", names)
        for excluded in ("ticker", "entry_date", "return_pct"):
            self.assertNotIn(excluded, names)

    def test_booleans_count_as_features(self):
        names = neighbours.feature_names([_row("AAA", 10.0, above_ma=True)])
        self.assertIn("above_ma", names)

    def test_a_feature_missing_from_some_rows_is_still_used(self):
        # The bug this replaces: dropping any column with a single gap
        # threw out relative strength over 50 missing rows in 6,151 —
        # the one feature with a monotone gradient in all three windows.
        rows = [_row("AAA", 10.0, rs=30.0), _row("BBB", 5.0)]
        self.assertIn("rs", neighbours.feature_names(rows))

    def test_a_missing_value_is_imputed_rather_than_dropped(self):
        fit = [_row("AAA", 10.0, rs=10.0), _row("BBB", 5.0, rs=30.0)]
        index = neighbours.Index(fit)
        # The median of 10 and 30 is 20, which standardises to zero.
        encoded = index.encode(_row("CCC", 0.0))
        self.assertAlmostEqual(encoded[index.names.index("rs")], 0.0, places=6)


class ScalingTest(unittest.TestCase):
    def test_a_large_unit_feature_does_not_dominate_distance(self):
        # Turnover in millions against relative strength 0-100. Unscaled,
        # turnover decides every comparison on units alone.
        fit = [_row(f"F{i}", 0.0, rs=float(i), turnover=float(i) * 1_000_000)
               for i in range(20)]
        index = neighbours.Index(fit)
        spread = [abs(v) for v in index.encode(_row("Q", 0.0, rs=19.0,
                                                    turnover=19_000_000.0))]
        self.assertAlmostEqual(spread[index.names.index("rs")],
                               spread[index.names.index("turnover")], places=6)

    def test_a_constant_feature_does_not_divide_by_zero(self):
        fit = [_row(f"F{i}", 0.0, flat=1.0, rs=float(i)) for i in range(10)]
        index = neighbours.Index(fit)
        self.assertTrue(all(math_is_finite(v) for v in index.encode(fit[0])))


def math_is_finite(value):
    return value == value and abs(value) != float("inf")


class NeighbourTest(unittest.TestCase):
    def _fit(self):
        return [_row("AAA", 100.0, rs=90.0), _row("AAA", 95.0, rs=89.0),
                _row("BBB", -10.0, rs=10.0), _row("CCC", -5.0, rs=12.0)]

    def test_the_same_ticker_is_excluded_from_its_own_neighbours(self):
        # Without this the model retrieves its own memories: the same
        # stock a week apart has a near-identical vector and a
        # near-identical outcome.
        index = neighbours.Index(self._fit(), k=4)
        found = index.neighbours(_row("AAA", 0.0, rs=90.0))
        self.assertTrue(all(r["ticker"] != "AAA" for r in found))

    def test_same_ticker_exclusion_can_be_turned_off_deliberately(self):
        index = neighbours.Index(self._fit(), k=4)
        found = index.neighbours(_row("AAA", 0.0, rs=90.0), exclude_ticker=False)
        self.assertTrue(any(r["ticker"] == "AAA" for r in found))

    def test_nearest_really_is_nearest(self):
        index = neighbours.Index(self._fit(), k=1)
        found = index.neighbours(_row("ZZZ", 0.0, rs=11.0))
        self.assertIn(found[0]["ticker"], ("BBB", "CCC"))

    def test_tail_probability_counts_neighbours_beating_the_threshold(self):
        fit = [_row(f"W{i}", 100.0, rs=50.0) for i in range(5)]
        fit += [_row(f"L{i}", -10.0, rs=50.0) for i in range(5)]
        index = neighbours.Index(fit, k=10, threshold_pct=50.0)
        self.assertAlmostEqual(index.tail_probability(_row("Q", 0.0, rs=50.0)), 0.5)

    def test_tail_probability_not_the_mean_of_neighbours(self):
        # A single monster among losers must not make the group look
        # good. The mean would be strongly positive; the tail share is
        # one in five, which is the honest description.
        fit = [_row("M", 900.0, rs=50.0)] + [_row(f"L{i}", -10.0, rs=50.0)
                                             for i in range(4)]
        index = neighbours.Index(fit, k=5, threshold_pct=50.0)
        self.assertAlmostEqual(index.tail_probability(_row("Q", 0.0, rs=50.0)), 0.2)

    def test_no_usable_neighbours_scores_zero_rather_than_raising(self):
        index = neighbours.Index([_row("AAA", 10.0, rs=1.0)], k=5)
        self.assertEqual(index.tail_probability(_row("AAA", 0.0, rs=1.0)), 0.0)


class RankingTest(unittest.TestCase):
    def test_ranking_puts_setups_resembling_winners_first(self):
        fit = [_row(f"W{i}", 200.0, rs=90.0 + i) for i in range(10)]
        fit += [_row(f"L{i}", -20.0, rs=10.0 + i) for i in range(10)]
        index = neighbours.Index(fit, k=5, threshold_pct=50.0)
        candidates = [_row("LOW", 0.0, rs=12.0), _row("HIGH", 0.0, rs=92.0)]
        self.assertEqual(index.rank(candidates)[0]["ticker"], "HIGH")

    def test_the_top_decile_score_reads_the_best_slice(self):
        ranked = [_row(f"T{i}", 100.0) for i in range(2)]
        ranked += [_row(f"B{i}", -10.0) for i in range(18)]
        self.assertAlmostEqual(neighbours.top_decile_mean(ranked), 100.0)

    def test_an_empty_ranking_is_not_a_crash(self):
        self.assertNotEqual(neighbours.top_decile_mean([]),
                            neighbours.top_decile_mean([]))
