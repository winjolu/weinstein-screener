"""Moving averages, checked against hand-computed numbers."""
import unittest

from screener import moving_averages



class EmaTest(unittest.TestCase):
    """Exponential average, against hand-computed numbers.

    Worked examples rather than my own reading of the formula, because
    the last time I checked an average against my understanding of the
    rule instead of against numbers, the rule was projecting from the
    wrong price and the tests all passed.
    """

    def test_warm_up_is_none_and_the_seed_is_the_simple_average(self):
        out = moving_averages.ema([1.0, 2.0, 3.0, 4.0], 3)
        self.assertEqual(out[0], None)
        self.assertEqual(out[1], None)
        self.assertAlmostEqual(out[2], 2.0)          # (1+2+3)/3

    def test_it_follows_the_textbook_recurrence(self):
        # k = 2/(3+1) = 0.5; seed 2.0; next = 4*0.5 + 2*0.5 = 3.0
        out = moving_averages.ema([1.0, 2.0, 3.0, 4.0], 3)
        self.assertAlmostEqual(out[3], 3.0)

    def test_a_flat_series_stays_flat(self):
        out = moving_averages.ema([5.0] * 10, 4)
        for v in out[3:]:
            self.assertAlmostEqual(v, 5.0)

    def test_it_reacts_faster_than_the_simple_average(self):
        # The reason to prefer it at all: on a step change the
        # exponential average moves first. A version that did not would
        # be indistinguishable from sma() in every arm it appeared in.
        series = [10.0] * 20 + [20.0] * 5
        e = moving_averages.ema(series, 10)
        s = moving_averages.sma(series, 10)
        self.assertGreater(e[-1], s[-1])

    def test_output_length_matches_the_other_averages(self):
        series = [float(i) for i in range(30)]
        self.assertEqual(len(moving_averages.ema(series, 10)),
                         len(moving_averages.sma(series, 10)))

    def test_too_few_values_gives_all_none_rather_than_a_short_list(self):
        # A short list would silently misalign with the bars it indexes.
        self.assertEqual(moving_averages.ema([1.0, 2.0], 5), [None, None])

    def test_a_nonpositive_period_raises(self):
        with self.assertRaises(ValueError):
            moving_averages.ema([1.0, 2.0, 3.0], 0)

    def test_the_new_value_gets_k_and_the_old_average_gets_one_minus_k(self):
        # Deliberately period 4, not 3. At period 3 the smoothing constant
        # is 2/(3+1) = 0.5, both weights are equal, and swapping them
        # changes nothing — a test written there passes against the
        # weighting being backwards. At period 4, k = 0.4:
        #   seed = (1+2+3+4)/4 = 2.5
        #   next = 5*0.4 + 2.5*0.6 = 3.5   (swapped would give 4.0)
        out = moving_averages.ema([1.0, 2.0, 3.0, 4.0, 5.0], 4)
        self.assertAlmostEqual(out[3], 2.5)
        self.assertAlmostEqual(out[4], 3.5)
